"""Бот столовой для MAX. Запуск: python bot_max.py"""
from __future__ import annotations

import io
import logging
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, abort, jsonify, request
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from waitress import serve

import config
from database import (
    init_database,
    max_bind_group,
    max_clear_old_votes,
    max_get_class_votes,
    max_get_group_class,
    max_get_groups,
    max_get_teacher,
    max_get_teacher_classes,
    max_register_teacher,
    max_save_vote,
)
from max_api import MaxAPI, MaxAPIError
from menu import get_menu_for_date, get_menu_compact_for_date


logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger('canteen.max')

STATUSES = {
    'paid': 'платно',
    'free': 'бесплатно',
}
STATUS_LABELS = {
    'платно': 'Платно',
    'бесплатно': 'Бесплатно',
}
VOTE_COMMANDS = {
    '/paid': 'платно', 'paid': 'платно', 'платно': 'платно',
    '/free': 'бесплатно', 'free': 'бесплатно', 'бесплатно': 'бесплатно',
}
HELP_TEXT = (
    '🍽 Бот столовой MAX\n\n'
    'В классной группе:\n'
    '/menu — меню и команды голосования\n'
    '/paid — питаюсь платно\n'
    '/free — питаюсь бесплатно\n'
    '/status — проверить свой выбор\n\n'
    'Учителю: откройте личный диалог с ботом и отправьте /register_teacher КЛАСС. '
    'Ежедневный отчёт придёт туда же.'
)


def local_now():
    return datetime.now(ZoneInfo(config.MAX_TIMEZONE))


def normalize_class_name(value):
    value = str(value or '').strip().upper()
    if not value or len(value) > 24 or not re.fullmatch(r'[\wА-ЯЁа-яё .-]+', value):
        return None
    return value


def extract_user_id(sender):
    if not isinstance(sender, dict):
        return None
    user_id = sender.get('user_id', sender.get('id'))
    return str(user_id) if user_id is not None else None


def display_name(sender):
    if not isinstance(sender, dict):
        return 'Ученик'
    first = str(sender.get('first_name') or '').strip()
    last = str(sender.get('last_name') or '').strip()
    name = ' '.join(part for part in (first, last) if part)
    name = name or str(sender.get('name') or sender.get('username') or '').strip()
    return name[:120] if name else 'Ученик'


def message_text(message):
    body = message.get('body') or {}
    if isinstance(body, dict):
        return str(body.get('text') or '').strip()
    return str(message.get('text') or '').strip()


def group_id_from_update(update, message):
    recipient = message.get('recipient') or {}
    if not isinstance(recipient, dict):
        recipient = {}
    return update.get('chat_id') or recipient.get('chat_id') or message.get('chat_id')


def build_report(class_name, report_date, votes):
    counts = {status: sum(vote['status'] == status for vote in votes) for status in STATUS_LABELS}
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Питание'
    sheet.append([f'Питание класса {class_name}', report_date])
    sheet['A1'].font = Font(bold=True, size=14, color='FFFFFF')
    sheet['B1'].font = Font(bold=True, color='FFFFFF')
    sheet['A1'].fill = PatternFill('solid', fgColor='2F75B5')
    sheet['B1'].fill = PatternFill('solid', fgColor='2F75B5')
    sheet.append(['Всего проголосовало', len(votes)])
    for status, label in STATUS_LABELS.items():
        sheet.append([label, counts[status]])
    sheet.append([])
    sheet.append(['Имя', 'Категория питания'])
    for cell in sheet[sheet.max_row]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill('solid', fgColor='D9EAF7')

    status_order = {'платно': 0, 'бесплатно': 1}
    for vote in sorted(votes, key=lambda row: (status_order.get(row['status'], 9), row['student_name'].casefold())):
        sheet.append([vote['student_name'], STATUS_LABELS.get(vote['status'], vote['status'])])
    sheet.column_dimensions['A'].width = 34
    sheet.column_dimensions['B'].width = 24
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical='center')
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue(), counts


def report_summary(class_name, report_date, votes, counts):
    return (
        f'📊 Отчёт по питанию — {class_name}, {report_date}\n'
        f'Всего проголосовало: {len(votes)}\n'
        f'Платно: {counts["платно"]} · Бесплатно: {counts["бесплатно"]} · '
        f'Не обедает: {counts["не обедает"]}'
    )


class MaxCanteenBot:
    def __init__(self, api=None, admin_ids=None):
        self.api = api or MaxAPI()
        configured_ids = admin_ids
        if configured_ids is None:
            configured_ids = (value.strip() for value in config.MAX_ADMIN_IDS.split(','))
        self.admin_ids = {str(value) for value in configured_ids if str(value).strip()}

    def is_admin(self, user_id):
        return str(user_id) in self.admin_ids

    def _is_group_admin_for_class(self, class_name, user_id):
        for group in max_get_groups():
            if group['class_name'] != class_name:
                continue
            try:
                response = self.api.get_chat_admins(group['chat_id'])
            except MaxAPIError as exc:
                logger.info('Не удалось проверить администратора чата %s: %s', group['chat_id'], exc)
                continue
            members = response if isinstance(response, list) else response.get('members', [])
            for member in members or []:
                member_user = member.get('user') or member
                member_id = member_user.get('user_id', member_user.get('id'))
                if member_id is not None and str(member_id) == str(user_id):
                    return True
        return False

    def _send(self, target_id, text, direct=False):
        return self.api.send_message(
            target_id,
            text,
            recipient_type='user_id' if direct else 'chat_id',
        )

    def _register_teacher(self, user_id, sender, class_arg):
        if not class_arg:
            self._send(user_id, 'Использование: /register_teacher КЛАСС', direct=True)
            return
        class_name = normalize_class_name(class_arg)
        if not class_name:
            self._send(user_id, 'Не понял название класса. Пример: /register_teacher 7А', direct=True)
            return
        if not self.is_admin(user_id) and not self._is_group_admin_for_class(class_name, user_id):
            self._send(
                user_id,
                'Назначить учителя может администратор бота или администратор привязанной группы класса. '
                'Если проверка MAX недоступна, добавьте ваш MAX ID в MAX_ADMIN_IDS.',
                direct=True,
            )
            return
        success = max_register_teacher(
            class_name,
            user_id,
            display_name(sender),
            allow_replace=self.is_admin(user_id),
        )
        if not success:
            self._send(
                user_id,
                f'Для класса {class_name} уже назначен другой учитель. Заменить его может администратор бота.',
                direct=True,
            )
            return
        self._send(
            user_id,
            f'✅ Вы зарегистрированы для класса {class_name}. Ежедневный отчёт будет отправляться в этот MAX-диалог.',
            direct=True,
        )

    def _deliver_report(self, class_name, target_user_id=None):
        teacher = max_get_teacher(class_name)
        target_user_id = str(target_user_id or (teacher or {}).get('user_id') or '')
        if not target_user_id:
            logger.warning('Не назначен учитель класса %s', class_name)
            return False
        today = local_now().date().isoformat()
        votes = max_get_class_votes(class_name, today)
        if not votes:
            self._send(target_user_id, f'За {today} в классе {class_name} голосов пока нет.', direct=True)
            return True
        file_bytes, counts = build_report(class_name, today, votes)
        summary = report_summary(class_name, today, votes, counts)
        file_class = re.sub(r'[^A-Za-z0-9_-]+', '_', class_name).strip('_') or 'class'
        filename = f'canteen_{file_class}_{today}.xlsx'
        self.api.send_file(target_user_id, filename, file_bytes, caption=summary)
        logger.info('Отправлен дневной отчёт класса %s', class_name)
        for group in max_get_groups():
            if group['class_name'] == class_name:
                try:
                    self._send(
                        group['chat_id'],
                        f'📊 Голосование закрыто. В {class_name} проголосовало {len(votes)} человек. '
                        f'Платно: {counts["платно"]} · Бесплатно: {counts["бесплатно"]} · '
                        f'Не обедает: {counts["не обедает"]}',
                    )
                except MaxAPIError as exc:
                    logger.error('Не удалось отправить сводку в чат %s: %s', group['chat_id'], exc)
        return True

    def handle_update(self, update):
        if not isinstance(update, dict):
            return
        update_type = update.get('update_type')
        if update_type == 'bot_added':
            if update.get('is_channel'):
                return
            chat_id = update.get('chat_id')
            if chat_id is not None:
                self._send(
                    chat_id,
                    'Привет! Чтобы привязать эту беседу к классу, администратор бота должен отправить '
                    '/bind_class КЛАСС. Например: /bind_class 7А. Голосования до привязки не принимаются.',
                )
            return
        if update_type == 'bot_started':
            user = update.get('user') or {}
            user_id = extract_user_id(user)
            if user_id:
                self._send(user_id, HELP_TEXT, direct=True)
            return
        if update_type != 'message_created':
            return

        message = update.get('message') or {}
        if not isinstance(message, dict):
            return
        sender = message.get('sender') or update.get('user') or {}
        user_id = extract_user_id(sender)
        if not user_id or sender.get('is_bot'):
            return
        text = message_text(message)
        if not text:
            return
        parts = text.split(maxsplit=1)
        command = parts[0].split('@', 1)[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ''
        chat_id = group_id_from_update(update, message)
        direct = chat_id is None

        if command in {'/start', '/help', 'help', '/id'}:
            if command == '/id':
                identity = f'Ваш MAX user_id: {user_id}' if direct else f'ID этой беседы: {chat_id}'
                self._send(user_id if direct else chat_id, identity, direct=direct)
            else:
                self._send(chat_id or user_id, HELP_TEXT, direct=direct)
            return

        if command == '/bind_class':
            if direct or chat_id is None:
                self._send(user_id, 'Эту команду отправьте в классной группе: /bind_class 7А.', direct=True)
                return
            if not self.is_admin(user_id):
                self._send(chat_id, 'Привязать группу может только администратор бота.')
                return
            class_name = normalize_class_name(argument)
            if not class_name:
                self._send(chat_id, 'Укажите класс, например: /bind_class 7А')
                return
            try:
                details = self.api.get_chat(chat_id)
                group_name = details.get('title') or f'MAX chat {chat_id}'
            except MaxAPIError:
                group_name = f'MAX chat {chat_id}'
            max_bind_group(str(chat_id), group_name, class_name)
            self._send(chat_id, f'✅ Беседа привязана к классу {class_name}. Для выбора используйте /paid, /free или /no_meal.')
            return

        if command == '/register_teacher':
            if not direct:
                self._send(chat_id, 'Учитель должен зарегистрироваться в личном диалоге: /register_teacher 7А.')
                return
            self._register_teacher(user_id, sender, argument)
            return

        if command == '/report':
            if not direct:
                self._send(chat_id, 'Для конфиденциальности отчёт можно запросить только в личном диалоге с ботом.')
                return
            requested_class = normalize_class_name(argument) if argument else None
            if argument and not requested_class:
                self._send(user_id, 'Не понял название класса. Пример: /report 7А', direct=True)
                return
            classes = [requested_class] if requested_class else max_get_teacher_classes(user_id)
            if requested_class and not self.is_admin(user_id):
                classes = [name for name in classes if name in max_get_teacher_classes(user_id)]
            if not classes:
                self._send(user_id, 'Для этого класса у вас нет доступа к отчётам.', direct=True)
                return
            for class_name in classes:
                try:
                    self._deliver_report(class_name, target_user_id=user_id)
                except MaxAPIError as exc:
                    logger.error('Не удалось сформировать или доставить отчёт класса %s: %s', class_name, exc)
                    self._send(user_id, f'Не удалось отправить отчёт класса {class_name}. Попробуйте позже.', direct=True)
            return

        if direct:
            self._send(user_id, HELP_TEXT, direct=True)
            return

        class_name = max_get_group_class(str(chat_id))
        if command == '/menu':
            if not class_name:
                self._send(chat_id, 'Сначала администратор должен привязать беседу командой /bind_class КЛАСС.')
                return
            menu = get_menu_compact_for_date(local_now().date()).replace('**', '')
            self._send(chat_id, f'{menu}\n\nВаш выбор: /paid, /free или /no_meal.')
            return
        if command == '/status':
            if not class_name:
                self._send(chat_id, 'Беседа ещё не привязана к классу.')
                return
            today = local_now().date().isoformat()
            vote = next((item for item in max_get_class_votes(class_name, today) if item['user_id'] == user_id), None)
            self._send(chat_id, 'Сегодня ваш голос уже сохранён.' if vote else 'Сегодня вы ещё не голосовали.')
            return

        status = VOTE_COMMANDS.get(command) or VOTE_COMMANDS.get(text.casefold())
        if not status:
            return
        if not class_name:
            self._send(chat_id, 'Беседа ещё не привязана к классу, поэтому голос не сохранён.')
            return
        max_save_vote(class_name, user_id, display_name(sender), status, local_now().date().isoformat())
        self._send(chat_id, '✅ Голос учтён. Изменить его можно повторной командой.')

    def send_daily_menu(self):
        today = local_now().date()
        menu = get_menu_compact_for_date(today).replace('**', '')
        for group in max_get_groups():
            try:
                self._send(
                    group['chat_id'],
                    f'{menu}\n\n'
                    'Отметьте выбор командой /paid, /free или /no_meal.',
                )
                time.sleep(0.55)
            except MaxAPIError as exc:
                logger.error('Не удалось отправить меню в чат %s: %s', group['chat_id'], exc)

    def send_daily_reports(self):
        today = local_now().date().isoformat()
        class_names = sorted({group['class_name'] for group in max_get_groups()})
        for class_name in class_names:
            if not max_get_teacher(class_name):
                logger.warning('Для класса %s не назначен учитель; отчёт оставлен в базе на сегодня', class_name)
                continue
            try:
                self._deliver_report(class_name)
            except MaxAPIError as exc:
                logger.error('Не удалось доставить отчёт класса %s: %s', class_name, exc)
            time.sleep(0.55)
        # Удаляем только предыдущие дни; сегодняшние голоса сохраняются до следующего дня.
        max_clear_old_votes(today)


def create_app(service=None):
    app = Flask(__name__)
    bot_service = service or MaxCanteenBot()

    @app.post('/webhook')
    def max_webhook():
        expected_secret = config.MAX_WEBHOOK_SECRET
        received_secret = request.headers.get('X-Max-Bot-Api-Secret', '')
        if not expected_secret or received_secret != expected_secret:
            abort(403)
        update = request.get_json(silent=True)
        if not isinstance(update, dict):
            abort(400)
        try:
            bot_service.handle_update(update)
        except Exception:
            logger.exception('Ошибка при обработке MAX webhook')
            abort(500)
        return jsonify(ok=True)

    return app


def configured_admins():
    return [part.strip() for part in config.MAX_ADMIN_IDS.split(',') if part.strip()]


def ensure_webhook_subscription(api):
    url = config.MAX_WEBHOOK_URL.strip()
    secret = config.MAX_WEBHOOK_SECRET.strip()
    if not url.startswith('https://'):
        raise RuntimeError('MAX_WEBHOOK_URL должен быть публичным HTTPS-адресом, например https://bot.example.ru/webhook')
    if urlparse(url).path != '/webhook' or urlparse(url).query or urlparse(url).fragment:
        raise RuntimeError('MAX_WEBHOOK_URL должен указывать ровно на путь /webhook без query-параметров')
    if not re.fullmatch(r'[A-Za-z0-9_-]{5,256}', secret):
        raise RuntimeError('MAX_WEBHOOK_SECRET должен содержать 5–256 символов: A-Z, a-z, 0-9, _ или -')
    current = api.get_subscriptions()
    subscriptions = current if isinstance(current, list) else current.get('subscriptions', [])
    desired = {'message_created', 'bot_added', 'bot_started'}
    existing = next((item for item in subscriptions if item.get('url') == url), None)
    if existing and desired.issubset(set(existing.get('update_types') or [])):
        return
    api.subscribe(url, secret)


def run_scheduler(service):
    scheduler = BackgroundScheduler(timezone=ZoneInfo(config.MAX_TIMEZONE))
    menu_hour, menu_minute = map(int, config.MAX_MENU_TIME.split(':'))
    report_hour, report_minute = map(int, config.MAX_REPORT_TIME.split(':'))
    scheduler.add_job(service.send_daily_menu, 'cron', day_of_week='mon-fri', hour=menu_hour,
                      minute=menu_minute, id='max_daily_menu', replace_existing=True, max_instances=1)
    scheduler.add_job(service.send_daily_reports, 'cron', day_of_week='mon-fri', hour=report_hour,
                      minute=report_minute, id='max_daily_reports', replace_existing=True, max_instances=1)
    scheduler.add_job(lambda: max_clear_old_votes(local_now().date().isoformat()), 'cron', hour=0,
                      minute=5, id='max_vote_cleanup', replace_existing=True, max_instances=1)
    scheduler.start()
    return scheduler


def run_long_polling(service, api):
    logger.warning('Используется Long Polling для разработки. Для production настройте MAX_WEBHOOK_URL на HTTPS.')
    marker = None
    while True:
        try:
            result = api.get_updates(marker=marker, timeout=60)
            for update in result.get('updates', []):
                service.handle_update(update)
            marker = result.get('marker', marker)
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception('Ошибка Long Polling; повтор через 3 секунды')
            time.sleep(3)


def main():
    if not config.MAX_BOT_TOKEN:
        raise SystemExit('Задайте MAX_BOT_TOKEN в переменных окружения.')
    api = MaxAPI()
    init_database()
    try:
        api.set_commands()
    except MaxAPIError as exc:
        logger.warning('MAX не принял список команд; ручной ввод команд остаётся доступен: %s', exc)
    service = MaxCanteenBot(api=api, admin_ids=configured_admins())
    max_clear_old_votes(local_now().date().isoformat())
    scheduler = run_scheduler(service)
    try:
        if config.MAX_WEBHOOK_URL:
            ensure_webhook_subscription(api)
            logger.info('MAX webhook активен: %s', config.MAX_WEBHOOK_URL)
            serve(create_app(service), host=config.MAX_WEBHOOK_HOST, port=config.MAX_WEBHOOK_PORT, threads=8)
        else:
            run_long_polling(service, api)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == '__main__':
    main()
