"""
VK Bot для автоматизации школьной столовой
Отправляет меню, собирает голоса, генерирует отчеты
Поддерживает работу с несколькими беседами одновременно
"""
import os
import logging
import time
import re
from datetime import datetime
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

import config
from menu import get_today_menu, get_today_menu_compact
from menu_images import get_menu_image_path, is_weekend, setup_menu_images_directory
from database import (
    save_vote, register_teacher, get_teacher_by_class,
    init_group, get_class_by_chat, save_student,
    get_all_groups, get_all_students_in_class, is_user_teacher
)
from reports import generate_daily_stats, generate_excel_report, get_group_statistics_text

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация VK API
vk_session = vk_api.VkApi(token=config.VK_TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, config.VK_GROUP_ID)

# Планировщик задач
scheduler = BackgroundScheduler(timezone=pytz.timezone(config.TIMEZONE))


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def send_message(peer_id, message, keyboard=None, attachment=None):
    """
    Отправка сообщения в VK

    Args:
        peer_id: ID беседы/пользователя
        message: Текст сообщения
        keyboard: Клавиатура VK (опционально)
        attachment: Вложение (фото, документ)
    """
    try:
        params = {
            'peer_id': peer_id,
            'message': message,
            'random_id': get_random_id()
        }

        if keyboard:
            params['keyboard'] = keyboard.get_keyboard()

        if attachment:
            params['attachment'] = attachment

        vk.messages.send(**params)
        logger.info(f"Сообщение отправлено в {peer_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения в {peer_id}: {e}")


def upload_photo(peer_id, photo_path):
    """
    Загрузка фото для сообщения

    Args:
        peer_id: ID беседы
        photo_path: Путь к файлу

    Returns:
        Строка attachment для отправки
    """
    try:
        upload = vk_api.VkUpload(vk_session)
        photo = upload.photo_messages(photo_path, peer_id=peer_id)[0]
        return f"photo{photo['owner_id']}_{photo['id']}"
    except Exception as e:
        logger.error(f"Ошибка при загрузке фото: {e}")
        return None


def upload_document(peer_id, doc_path, title):
    """
    Загрузка документа

    Args:
        peer_id: ID беседы
        doc_path: Путь к файлу
        title: Название файла

    Returns:
        Строка attachment для отправки
    """
    try:
        upload = vk_api.VkUpload(vk_session)
        doc = upload.document_message(doc_path, title=title, peer_id=peer_id)
        doc_data = doc['doc']
        return f"doc{doc_data['owner_id']}_{doc_data['id']}"
    except Exception as e:
        logger.error(f"Ошибка при загрузке документа: {e}")
        return None


def create_voting_keyboard():
    """Клавиатура для голосования"""
    keyboard = VkKeyboard(inline=True)
    keyboard.add_button('💳 Платно', color=VkKeyboardColor.PRIMARY, payload={"action": "vote", "status": "платно"})
    keyboard.add_button('🆓 Бесплатно', color=VkKeyboardColor.POSITIVE, payload={"action": "vote", "status": "бесплатно"})
    return keyboard


def get_conversation_class_name(peer_id):
    """
    Получить название класса по ID беседы

    Args:
        peer_id: ID беседы в VK

    Returns:
        Название класса или None
    """
    class_name = get_class_by_chat(str(peer_id))

    if not class_name:
        # Попытка определить из названия беседы
        try:
            conversation = vk.messages.getConversationsById(peer_ids=peer_id)
            if conversation['items']:
                title = conversation['items'][0]['chat_settings']['title']
                match = re.search(r'(\d+)[а-яА-Я]', title)
                if match:
                    class_name = match.group(0).upper()
                    init_group(str(peer_id), title, class_name)
                    logger.info(f"Автоматически определен класс {class_name} для беседы {peer_id}")
        except Exception as e:
            logger.error(f"Ошибка при получении названия беседы: {e}")

    return class_name or config.DEFAULT_CLASS


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

def handle_start(event):
    """Приветственное сообщение"""
    peer_id = event.obj.message['peer_id']

    # Проверяем, в беседе ли мы
    is_chat = peer_id > 2000000000

    if is_chat:
        message = ("🤖 Привет! Я бот для управления питанием школьной столовой.\n\n"
                   "Используйте команду 'меню' для голосования о питании!")
    else:
        message = """👋 Привет! Я бот для автоматизации школьной столовой.

📋 Доступные команды:
• меню — Показать меню на сегодня и проголосовать
• статистика — Показать текущую статистику по классу
• отчет — Получить отчет о питании (только для учителей)

👨‍🏫 Для учителей:
• учитель <класс> — Зарегистрироваться как учитель
Пример: учитель 7А

🕐 Автоматический режим:
• Каждый день в 14:00 я присылаю меню и кнопки для голосования
• В 20:00 отправляю отчет классному руководителю

Приятного аппетита! 🍽"""

    send_message(peer_id, message)


def handle_menu(event):
    """Отправка меню с кнопками для голосования"""
    peer_id = event.obj.message['peer_id']

    # Проверка на выходной
    if is_weekend():
        send_message(peer_id, "🏖 Сегодня выходной день — столовая не работает.\n\nПриятных выходных!")
        return

    keyboard = create_voting_keyboard()

    # Отправка компактного меню текстом (без картинок)
    menu_text = get_today_menu_compact()
    send_message(peer_id, f"{menu_text}\n\n👇 Выберите вариант питания:", keyboard)


def handle_stats(event):
    """Показать текущую статистику"""
    peer_id = event.obj.message['peer_id']

    try:
        class_name = get_conversation_class_name(peer_id)
        stats_text = generate_daily_stats(class_name)
        send_message(peer_id, stats_text)
    except Exception as e:
        logger.error(f"Ошибка при генерации статистики: {e}")
        send_message(peer_id, "❌ Ошибка при получении статистики. Попробуйте позже.")


def handle_report(event):
    """Отправка полного отчета (только для учителей)"""
    peer_id = event.obj.message['peer_id']
    user_id = event.obj.message['from_id']

    # Проверка прав
    is_admin = user_id in config.ADMIN_IDS
    is_teacher = is_user_teacher(str(user_id))

    if not (is_admin or is_teacher):
        send_message(
            peer_id,
            "⛔️ У вас нет прав для выполнения этой команды.\n\n"
            "Эта команда доступна только учителям и администраторам.\n"
            "Если вы учитель, зарегистрируйтесь: учитель <класс>"
        )
        return

    try:
        # Для учителя - получить его класс
        if is_teacher and not is_admin:
            from database import get_teacher_classes
            classes = get_teacher_classes(str(user_id))
            if not classes:
                send_message(peer_id, "❌ Не найден класс, закрепленный за вами.")
                return
            class_name = classes[0]
        else:
            class_name = get_conversation_class_name(peer_id)

        # Генерация статистики
        stats_text = generate_daily_stats(class_name)
        send_message(peer_id, stats_text)

        # Генерация Excel
        excel_path = generate_excel_report(class_name)
        attachment = upload_document(peer_id, excel_path, f"Отчет_{class_name}.xlsx")

        if attachment:
            send_message(peer_id, f"📊 Детальный отчет по классу {class_name}", attachment=attachment)

        logger.info(f"Отчет отправлен пользователю {user_id} (класс {class_name})")

    except Exception as e:
        logger.error(f"Ошибка при генерации отчета: {e}")
        send_message(peer_id, "❌ Ошибка при создании отчета. Попробуйте позже.")


def handle_register_teacher(event, class_name):
    """Регистрация учителя"""
    peer_id = event.obj.message['peer_id']
    user_id = event.obj.message['from_id']

    try:
        # Получение информации о пользователе
        user_info = vk.users.get(user_ids=user_id)[0]
        teacher_name = f"{user_info['last_name']} {user_info['first_name']}"

        register_teacher(
            class_name=class_name.upper(),
            teacher_tg_id=str(user_id),
            teacher_name=teacher_name,
            group_chat_id=None
        )

        send_message(
            peer_id,
            f"✅ Вы зарегистрированы как учитель класса {class_name.upper()}!\n\n"
            f"📊 Отчеты о питании будут приходить вам в личные сообщения.\n"
            f"📌 Статистика будет отправляться в беседы класса."
        )

        logger.info(f"Учитель {teacher_name} ({user_id}) зарегистрирован для класса {class_name}")

    except Exception as e:
        logger.error(f"Ошибка при регистрации учителя: {e}")
        send_message(peer_id, "❌ Ошибка при регистрации. Попробуйте позже.")


def handle_vote(event, status):
    """Обработка голосования"""
    peer_id = event.obj.message['peer_id']
    user_id = event.obj.message['from_id']

    try:
        # Получение информации о пользователе
        user_info = vk.users.get(user_ids=user_id)[0]
        first_name = user_info.get('first_name', '')
        last_name = user_info.get('last_name', '')
        student_name = f"{last_name} {first_name}".strip()

        if not student_name:
            student_name = f"Пользователь {user_id}"

        # Определение класса
        class_name = get_conversation_class_name(peer_id)

        # Сохранение данных студента
        save_student(str(user_id), first_name, last_name, class_name)

        # Сохранение голоса
        save_vote(
            class_name=class_name,
            user_id=str(user_id),
            student_name=student_name,
            status=status
        )

        # Формирование ответа
        status_emoji = {
            'платно': '💳',
            'бесплатно': '🆓',
            'не обедает': '❌'
        }
        emoji = status_emoji.get(status, '✅')

        send_message(peer_id, f"{emoji} Ваш выбор сохранен: {status.upper()}")

        logger.info(f"Голос сохранен: {student_name} ({user_id}) - {status} (класс {class_name})")

    except Exception as e:
        logger.error(f"Ошибка при обработке голоса: {e}")
        send_message(peer_id, "❌ Ошибка при сохранении. Попробуйте еще раз.")


# ==================== ОБРАБОТКА СОБЫТИЙ ====================

def handle_message_event(event):
    """Обработка callback от кнопок"""
    try:
        payload = event.obj.payload
        action = payload.get('action')

        if action == 'vote':
            status = payload.get('status')
            handle_vote(event, status)

    except Exception as e:
        logger.error(f"Ошибка при обработке callback: {e}")


def handle_chat_invite(event):
    """Обработка добавления бота в беседу"""
    peer_id = event.obj.message['peer_id']

    try:
        # Получение информации о беседе
        conversation = vk.messages.getConversationsById(peer_ids=peer_id)
        if conversation['items']:
            title = conversation['items'][0]['chat_settings']['title']

            # Парсинг названия для определения класса
            match = re.search(r'(\d+)[а-яА-Я]', title)
            class_name = match.group(0).upper() if match else "Unknown"

            # Инициализация беседы
            init_group(str(peer_id), title, class_name)

            # Получение количества участников
            members_count = conversation['items'][0]['chat_settings']['members_count']

            welcome_msg = f"""✅ Привет! Я добавлен в беседу {title}

🎓 Определённый класс: {class_name}
👥 Участников в беседе: {members_count}

📋 Что я умею:
• Отправлю меню на сегодня
• Соберу голоса о питании (платно/бесплатно/не обедают)
• Отправлю результаты учителю в Excel
• Покажу статистику в беседе

🍽 Давайте начнём! Каждый день в 14:00 я буду отправлять меню.

Команды: меню, статистика"""

            send_message(peer_id, welcome_msg)
            logger.info(f"Бот добавлен в беседу {title} (класс {class_name})")

    except Exception as e:
        logger.error(f"Ошибка при обработке добавления в беседу: {e}")


# ==================== АВТОМАТИЧЕСКИЕ ЗАДАЧИ ====================

def scheduled_send_menu():
    """Автоматическая отправка меню в заданное время"""
    logger.info("Запуск автоматической отправки меню")

    try:
        groups = get_all_groups()

        if not groups:
            logger.warning("Нет зарегистрированных бесед для отправки меню")
            return

        for group_data in groups:
            peer_id = int(group_data['chat_id'])
            class_name = group_data['class_name']

            # Проверка на выходной
            if is_weekend():
                send_message(peer_id, "🏖 Сегодня выходной день — столовая не работает.\n\nПриятных выходных!")
                continue

            # Получение меню
            menu_image_path = get_menu_image_path()
            keyboard = create_voting_keyboard()

            if menu_image_path and os.path.exists(menu_image_path):
                attachment = upload_photo(peer_id, menu_image_path)
                if attachment:
                    send_message(peer_id, f"🍽 Меню класса {class_name}\n\n👇 Выберите вариант питания:", keyboard, attachment)
                else:
                    menu_text = get_today_menu()
                    send_message(peer_id, f"📋 Меню класса {class_name}\n\n{menu_text}\n\n👇 Выберите вариант питания:", keyboard)
            else:
                menu_text = get_today_menu()
                send_message(peer_id, f"📋 Меню класса {class_name}\n\n{menu_text}\n\n👇 Выберите вариант питания:", keyboard)

            time.sleep(1)

        logger.info(f"Меню отправлено в {len(groups)} бесед")

    except Exception as e:
        logger.error(f"Ошибка при автоотправке меню: {e}")


def scheduled_send_report():
    """Автоматическая отправка отчета в заданное время"""
    logger.info("Запуск автоматической отправки отчетов")

    try:
        from datetime import date as date_module

        today = date_module.today().strftime("%Y-%m-%d")

        # Получение всех бесед
        groups = get_all_groups()

        if not groups:
            logger.warning("Нет зарегистрированных бесед для отправки отчетов")
            return

        # Группируем по классам
        classes_dict = {}
        for group_data in groups:
            class_name = group_data['class_name']
            peer_id = int(group_data['chat_id'])
            if class_name not in classes_dict:
                classes_dict[class_name] = []
            classes_dict[class_name].append(peer_id)

        # Для каждого класса отправляем отчет
        for class_name, peer_ids in classes_dict.items():
            try:
                teacher_data = get_teacher_by_class(class_name)

                if not teacher_data:
                    logger.warning(f"Учитель для класса {class_name} не найден")
                    continue

                teacher_vk_id = int(teacher_data['teacher_tg_id'])

                # 1. Отправка Excel учителю
                try:
                    excel_path = generate_excel_report(class_name, today)
                    attachment = upload_document(teacher_vk_id, excel_path, f"Отчет_{class_name}_{today}.xlsx")

                    if attachment:
                        send_message(teacher_vk_id, f"📊 Список питающихся в {class_name} ({today})", attachment=attachment)

                    logger.info(f"Excel-отчет отправлен учителю {teacher_vk_id} для класса {class_name}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке Excel для {class_name}: {e}")

                # 2. Отправка статистики во все беседы класса
                for peer_id in peer_ids:
                    try:
                        stats_text = get_group_statistics_text(class_name, today)
                        send_message(peer_id, stats_text)
                        logger.info(f"Статистика отправлена в беседу {peer_id} (класс {class_name})")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке статистики в беседу {peer_id}: {e}")

                time.sleep(1)

            except Exception as e:
                logger.error(f"Ошибка при обработке класса {class_name}: {e}")

        logger.info("Отчеты успешно отправлены")

    except Exception as e:
        logger.error(f"Ошибка при автоотправке отчетов: {e}")


def setup_scheduler():
    """Настройка планировщика задач"""
    try:
        menu_hour, menu_minute = map(int, config.SCHEDULE_MENU_TIME.split(':'))
        report_hour, report_minute = map(int, config.SCHEDULE_REPORT_TIME.split(':'))

        scheduler.add_job(
            scheduled_send_menu,
            CronTrigger(hour=menu_hour, minute=menu_minute, day_of_week='mon-fri'),
            id='send_menu',
            replace_existing=True
        )

        scheduler.add_job(
            scheduled_send_report,
            CronTrigger(hour=report_hour, minute=report_minute, day_of_week='mon-fri'),
            id='send_report',
            replace_existing=True
        )

        scheduler.start()
        logger.info("Планировщик успешно запущен")
        logger.info(f"Меню будет отправляться в {config.SCHEDULE_MENU_TIME}")
        logger.info(f"Отчет будет отправляться в {config.SCHEDULE_REPORT_TIME}")

    except Exception as e:
        logger.error(f"Ошибка при настройке планировщика: {e}")


# ==================== ЗАПУСК БОТА ====================

def main():
    """Главная функция запуска бота"""
    logger.info("Запуск VK бота для автоматизации школьной столовой")

    # Инициализация БД
    from database import init_database
    init_database()
    logger.info("База данных инициализирована")

    # Создание папки для картинок
    setup_menu_images_directory()
    logger.info("Папка для картинок меню подготовлена")

    # Проверка токена
    if not hasattr(config, 'VK_TOKEN') or config.VK_TOKEN == 'YOUR_VK_TOKEN_HERE':
        logger.error("⚠️ VK токен не установлен! Измените значение в config.py")
        return

    # Настройка планировщика
    setup_scheduler()

    # Запуск бота
    logger.info("Бот готов к работе. Ожидание событий...")

    for event in longpoll.listen():
        try:
            if event.type == VkBotEventType.MESSAGE_NEW:
                message_text = event.obj.message.get('text', '').lower().strip()

                if message_text in ['начать', 'start', 'привет', 'помощь']:
                    handle_start(event)
                elif message_text == 'меню':
                    handle_menu(event)
                elif message_text == 'статистика':
                    handle_stats(event)
                elif message_text == 'отчет':
                    handle_report(event)
                elif message_text.startswith('учитель '):
                    class_name = message_text.replace('учитель ', '').strip()
                    handle_register_teacher(event, class_name)
                elif message_text in ['платно', '💳 платно']:
                    handle_vote(event, 'платно')
                elif message_text in ['бесплатно', '🆓 бесплатно']:
                    handle_vote(event, 'бесплатно')
                elif message_text in ['не обедаю', '❌ не обедаю']:
                    handle_vote(event, 'не обедает')

            elif event.type == VkBotEventType.MESSAGE_EVENT:
                handle_message_event(event)

            elif event.type == VkBotEventType.GROUP_JOIN:
                handle_chat_invite(event)

        except Exception as e:
            logger.error(f"Ошибка при обработке события: {e}")


if __name__ == '__main__':
    main()
