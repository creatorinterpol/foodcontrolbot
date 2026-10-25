import os
import platform

# На сервере Linux/Amvera полностью отключаем прокси, запросы к Telegram идут напрямую
if platform.system() != 'Windows':
    for k in list(os.environ.keys()):
        if 'proxy' in k.lower():
            os.environ.pop(k, None)
"""
Telegram-бот для автоматизации школьной столовой
Отправляет меню, собирает голоса, генерирует отчеты
Поддерживает работу с несколькими группами классов одновременно
"""
import os
import logging
import time
import re
from datetime import datetime
import telebot
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

import config
from menu import get_today_menu, get_today_menu_compact, get_current_week_cycle
from menu_images import get_menu_image_path, is_weekend, setup_menu_images_directory
from menu_pdf import get_today_menu_image, setup_pdf_images_directory, check_pdf_available
from menu_upload import setup_menu_upload
from database import (
    save_vote, register_teacher, get_teacher_by_class,
    init_group, get_class_by_chat, save_student,
    get_all_groups, get_all_students_in_class
)
from database_auth import save_user_role, get_user_role, get_user_class, delete_user_role
from reports import generate_daily_stats, generate_excel_report, get_group_statistics_text, get_school_stats
from telebot import apihelper

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота с поддержкой прокси
bot = telebot.TeleBot(config.TELEGRAM_TOKEN)

# Настройка прокси если он указан
if config.PROXY_URL:
    logger.info(f"Использование прокси: {config.PROXY_URL}")
    apihelper.proxy = {'https': config.PROXY_URL, 'http': config.PROXY_URL}
else:
    logger.info("Прокси не используется, прямое соединение")
    apihelper.proxy = None

# Планировщик задач
scheduler = BackgroundScheduler(timezone=pytz.timezone(config.TIMEZONE))

# Словарь для хранения ожидания ввода кода {user_id: role}
waiting_for_code = {}


# ==================== ОБРАБОТКА ДОБАВЛЕНИЯ В ГРУППУ ====================

@bot.message_handler(content_types=['new_chat_members'])
def handle_group_add(message):
    """Обработка события добавления бота в группу"""
    try:
        # Проверяем, добавлен ли сам бот
        for member in message.new_chat_members:
            if member.is_bot and member.id == bot.get_me().id:
                # Получение названия и ID группы
                group_name = message.chat.title or "Неизвестная группа"
                chat_id = str(message.chat.id)

                # Парсинг названия группы для определения класса
                # Ищем паттерны вроде "7А", "8б", "10-1" и т.д.
                import re
                match = re.search(r'(\d+)[а-яА-Я]', group_name)
                class_name = match.group(0).upper() if match else "Unknown"

                # Инициализация группы в БД
                from database import init_group
                init_group(chat_id, group_name, class_name)

                # Получение списка участников
                try:
                    try:
                        members = bot.get_chat_member_count(chat_id)
                    except Exception:
                        members = "неизвестно"

                    welcome_msg = f"""✅ Привет! Я добавлен в группу **{group_name}**

🎓 Определённый класс: **{class_name}**
👥 Участников в группе: {members}

📋 **Что я умею:**
• Отправлю меню на сегодня
• Соберу голоса о питании (платно/бесплатно/не обедают)
• Отправлю результаты учителю в Excel
• Покажу статистику в группе

🍽 Давайте начнём! Каждый день в {config.SCHEDULE_MENU_TIME} я буду отправлять меню."""
                    bot.send_message(chat_id, welcome_msg, parse_mode='Markdown')
                    logger.info(f"Бот добавлен в группу {group_name} (класс {class_name})")
                except Exception as e:
                    logger.error(f"Ошибка при получении информации о группе: {e}")
                    bot.send_message(chat_id, "⚠️ Бот добавлен, но возникла ошибка при инициализации.")

                break

    except Exception as e:
        logger.error(f"Ошибка при обработке добавления в группу: {e}")


# ==================== КОМАНДЫ БОТА ====================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Приветственное сообщение с выбором роли"""
    if message.chat.type in ['group', 'supergroup']:
        bot.send_message(
            message.chat.id,
            "🤖 Я бот для управления питанием школьной столовой. "
            "Используйте /menu для голосования о питании!"
        )
        return

    # Проверяем, авторизован ли уже пользователь
    user_id = str(message.from_user.id)
    role = get_user_role(user_id)

    if role:
        welcome_text = f"""👋 Вы авторизованы как: **{role}**

📋 **Доступные команды:**
/menu — Показать меню на сегодня
/stats — Статистика по классу
/report — Получить отчет о питании

Приятного аппетита! 🍽"""
        bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown')
    else:
        # Показываем выбор роли
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👨‍🏫 Учитель", callback_data="role_teacher"))
        markup.add(types.InlineKeyboardButton("🔧 Завхоз", callback_data="role_zavhoz"))

        bot.send_message(
            message.chat.id,
            "👋 Выберите вашу роль для доступа к боту:",
            reply_markup=markup
        )



@bot.message_handler(commands=['menu'])
def send_menu(message):
    """Отправка меню с кнопками для голосования и фото"""
    user_id = str(message.from_user.id)
    if not get_user_role(user_id):
        bot.send_message(message.chat.id, "⛔️ Сначала авторизуйтесь через /start")
        return

    # Проверка на выходной
    if is_weekend():
        bot.send_message(
            message.chat.id,
            "🏖 Сегодня выходной день — столовая не работает.\n\nПриятных выходных!"
        )
        return

    # Создание Inline-кнопок
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_paid = types.InlineKeyboardButton("💳 Платно", callback_data="vote_платно")
    btn_free = types.InlineKeyboardButton("🆓 Бесплатно", callback_data="vote_бесплатно")
    markup.add(btn_paid, btn_free)

    # Отправка меню текстом
    menu_text = get_today_menu_compact()
    bot.send_message(
        message.chat.id,
        f"{menu_text}\n\n👇 **Выберите вариант питания:**",
        reply_markup=markup,
        parse_mode='Markdown'
    )

    # Отправка фото меню если существует
    user_class = get_user_class(user_id)

    # Сначала пытаемся взять из PDF
    menu_image_path = get_today_menu_image()

    # Если нет в PDF, берём загруженное через /upload_menu
    if not menu_image_path or not os.path.exists(menu_image_path):
        menu_image_path = get_menu_image_path(user_class or config.DEFAULT_CLASS)

    if menu_image_path and os.path.exists(menu_image_path):
        try:
            with open(menu_image_path, 'rb') as photo:
                bot.send_photo(message.chat.id, photo, caption="📸 Фото меню")
        except Exception as e:
            logger.warning(f"Не удалось отправить фото меню: {e}")


def send_menu_to_group(chat_id, class_name):
    """Отправка меню в групповой чат с фото"""
    try:
        # Проверка на выходной
        if is_weekend():
            bot.send_message(
                chat_id,
                "🏖 Сегодня выходной день — столовая не работает.\n\nПриятных выходных!"
            )
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🥐🍽️ Завтрак+Обед", callback_data="vote_завтрак_обед"),
            types.InlineKeyboardButton("🍽️ Обед", callback_data="vote_обед")
        )
        markup.add(
            types.InlineKeyboardButton("🥐💳 Завтрак платно", callback_data="vote_завтрак_платно"),
            types.InlineKeyboardButton("🥐🆓 Завтрак льготы", callback_data="vote_завтрак_льготы")
        )
        markup.add(
            types.InlineKeyboardButton("❌ Не обедаю", callback_data="vote_не_обедает")
        )

        # Отправка компактного меню текстом
        menu_text = get_today_menu_compact()
        bot.send_message(
            chat_id,
            f"📋 **Меню класса {class_name}**\n\n{menu_text}\n\n👇 **Выберите вариант питания:**",
            reply_markup=markup,
            parse_mode='Markdown'
        )

        # Отправка фото меню если существует
        # Сначала пытаемся взять из PDF
        menu_image_path = get_today_menu_image()

        # Если нет в PDF, берём загруженное
        if not menu_image_path or not os.path.exists(menu_image_path):
            menu_image_path = get_menu_image_path(class_name)

        if menu_image_path and os.path.exists(menu_image_path):
            try:
                with open(menu_image_path, 'rb') as photo:
                    bot.send_photo(chat_id, photo, caption="📸 Фото меню")
                logger.info(f"Фото меню отправлено в группу {chat_id}")
            except Exception as e:
                logger.warning(f"Не удалось отправить фото меню: {e}")

        logger.info(f"Меню отправлено в группу {chat_id} (класс {class_name})")
    except Exception as e:
        logger.error(f"Ошибка при отправке меню в группу {chat_id}: {e}")


@bot.message_handler(commands=['stats'])
def send_stats(message):
    """Показать текущую статистику"""
    user_id = str(message.from_user.id)
    if not get_user_role(user_id):
        bot.send_message(message.chat.id, "⛔️ Сначала авторизуйтесь через /start")
        return

    user_class = get_user_class(user_id)

    try:
        if user_class:  # Учитель
            stats_text = generate_daily_stats(user_class)
        else:  # Завхоз
            stats_text = get_school_stats()
        bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка при генерации статистики: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Ошибка при получении статистики. Попробуйте позже."
        )


@bot.message_handler(commands=['report'])
def send_report(message):
    """Отправка полного отчета (только для учителей и завхоза)"""
    user_id = str(message.from_user.id)

    role = get_user_role(user_id)
    if not role:
        bot.send_message(message.chat.id, "⛔️ Сначала авторизуйтесь через /start")
        return

    try:
        # Определение класса для отчета
        args = message.text.split()
        if len(args) > 1:
            class_name = args[1].strip().upper()
        else:
            from database import get_class_by_chat
            group_class = get_class_by_chat(message.chat.id)
            class_name = group_class or config.DEFAULT_CLASS

        # Генерация текстовой статистики
        stats_text = generate_daily_stats(class_name)
        bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')

        # Генерация и отправка Excel-отчета
        excel_path = generate_excel_report(class_name)

        with open(excel_path, 'rb') as file:
            bot.send_document(
                message.chat.id,
                file,
                caption=f"📊 Детальный отчет по классу {class_name}"
            )

        logger.info(f"Отчет успешно отправлен пользователю {user_id} (класс {class_name})")

    except Exception as e:
        logger.error(f"Ошибка при генерации отчета: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Ошибка при создании отчета. Попробуйте позже."
        )


@bot.message_handler(commands=['register_teacher'])
def register_teacher_command(message):
    """Регистрация учителя для класса"""
    try:
        args = message.text.split()

        # Проверка формата команды
        if len(args) < 2:
            bot.send_message(
                message.chat.id,
                "❌ Ошибка! Используйте: /register_teacher <название_класса>\n"
                "Пример: /register_teacher 7А"
            )
            return

        class_name = args[1].upper()
        teacher_tg_id = str(message.from_user.id)
        teacher_name = f"{message.from_user.last_name or ''} {message.from_user.first_name or ''}".strip()

        # Сохранение в БД
        register_teacher(
            class_name=class_name,
            teacher_tg_id=teacher_tg_id,
            teacher_name=teacher_name,
            group_chat_id=None  # Будет добавлено позже
        )

        bot.send_message(
            message.chat.id,
            f"✅ Вы зарегистрированы как учитель класса {class_name}!\n\n"
            f"📊 Отчеты о питании будут приходить вам в личные сообщения.\n"
            f"📌 Статистика будет отправляться в групповой чат класса."
        )

        logger.info(f"Учитель {teacher_name} ({teacher_tg_id}) зарегистрирован для класса {class_name}")

    except Exception as e:
        logger.error(f"Ошибка при регистрации учителя: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Ошибка при регистрации. Попробуйте позже."
        )


@bot.message_handler(commands=['logout'])
def logout(message):
    """Выход из сессии"""
    user_id = str(message.from_user.id)
    if not get_user_role(user_id):
        bot.send_message(message.chat.id, "⛔️ Вы не авторизованы")
        return

    delete_user_role(user_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👨‍🏫 Учитель", callback_data="role_teacher"))
    markup.add(types.InlineKeyboardButton("🔧 Завхоз", callback_data="role_zavhoz"))

    bot.send_message(
        message.chat.id,
        "👋 Вы вышли из сессии\n\nВыберите вашу роль:",
        reply_markup=markup
    )
    logger.info(f"Пользователь {user_id} вышел из сессии")


@bot.message_handler(commands=['set_group'])
def set_group_chat(message):
    """Установка ID групповой беседы для отправки статистики"""
    try:
        args = message.text.split()

        if len(args) < 2:
            bot.send_message(
                message.chat.id,
                "❌ Ошибка! Используйте: /set_group <ID_чата>\n"
                "Пример: /set_group -1001234567890"
            )
            return

        group_chat_id = args[1]
        teacher_tg_id = str(message.from_user.id)

        # Получение класса учителя
        from database import get_teacher_classes
        classes = get_teacher_classes(teacher_tg_id)

        if not classes:
            bot.send_message(
                message.chat.id,
                "❌ Вы не зарегистрированы как учитель. "
                "Используйте /register_teacher <класс>"
            )
            return

        # Обновление ID группы для первого класса (или можно обновить все)
        from database import update_group_chat_id
        update_group_chat_id(classes[0], group_chat_id)

        bot.send_message(
            message.chat.id,
            f"✅ Групповой чат установлен для класса {classes[0]}!\n"
            f"📌 Статистика питания будет отправляться туда автоматически."
        )

    except Exception as e:
        logger.error(f"Ошибка при установке группового чата: {e}")


@bot.message_handler(commands=['bind_class'])
def bind_class_cmd(message):
    """Привязка класса к группе прямо из чата"""
    if message.chat.type not in ['group', 'supergroup']:
        bot.send_message(message.chat.id, "❌ Эту команду нужно вызывать в группе класса.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.send_message(message.chat.id, "❌ Укажите класс! Пример: `/bind_class 7А`", parse_mode='Markdown')
        return

    class_name = args[1].strip().upper()
    chat_id = str(message.chat.id)
    group_name = message.chat.title or "Группа"

    try:
        from database import init_group
        init_group(chat_id, group_name, class_name)
        bot.send_message(
            message.chat.id,
            f"✅ Группа успешно привязана к классу **{class_name}**!\n"
            f"Теперь можно использовать /menu для голосования.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка при привязке класса: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка при привязке: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Ошибка при установке. Попробуйте позже."
        )



# ==================== ОБРАБОТКА INLINE-КНОПОК ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_'))
def handle_vote(call):
    """Обработка голосования через Inline-кнопки"""
    try:
        # Извлечение статуса из callback_data
        status = call.data.replace('vote_', '')

        # Получение данных пользователя
        user_id = str(call.from_user.id)
        first_name = call.from_user.first_name or ""
        last_name = call.from_user.last_name or ""
        student_name = f"{last_name} {first_name}".strip()

        # Если имя пустое, использовать username
        if not student_name:
            student_name = call.from_user.username or f"Пользователь {user_id}"

        # Определение класса по ID группы
        from database import get_class_by_chat
        class_name = get_class_by_chat(call.message.chat.id)

        if not class_name:
            # Если не найдена группа, используем DEFAULT_CLASS
            class_name = config.DEFAULT_CLASS

        # Сохранение данных студента
        from database import save_student
        save_student(user_id, first_name, last_name, class_name)

        # Сохранение голоса в базу данных
        save_vote(
            class_name=class_name,
            user_id=user_id,
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

        response_text = f"{emoji} Ваш выбор сохранен: {status.upper()}"

        # Отправка уведомления пользователю
        bot.answer_callback_query(call.id, response_text)

        # Опционально: редактирование сообщения с отметкой о голосовании
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=call.message.reply_markup
            )
        except:
            pass  # Игнорируем ошибки редактирования

        logger.info(f"Голос сохранен: {student_name} ({user_id}) - {status} (класс {class_name})")

    except Exception as e:
        logger.error(f"Ошибка при обработке голоса: {e}")
        bot.answer_callback_query(
            call.id,
            "❌ Ошибка при сохранении. Попробуйте еще раз.",
            show_alert=True
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith('role_'))
def handle_role_selection(call):
    """Обработка выбора роли"""
    role = call.data.replace('role_', '')
    user_id = str(call.from_user.id)

    if role == "teacher":
        waiting_for_code[user_id] = ("teacher_code", None)
        msg = "👨‍🏫 Учитель\n\n🔐 Введите код доступа:"
    else:
        waiting_for_code[user_id] = ("zavhoz", None)
        msg = "🔧 Завхоз\n\n🔐 Введите код доступа:"

    bot.edit_message_text(msg, call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: str(m.from_user.id) in waiting_for_code)
def handle_access_code(message):
    """Обработка ввода кода доступа или класса"""
    user_id = str(message.from_user.id)
    state, data = waiting_for_code[user_id]
    text = message.text.strip()

    # Проверка кода для учителя
    if state == "teacher_code":
        if text == config.ACCESS_CODE_TEACHER:
            waiting_for_code[user_id] = ("teacher_class", None)
            bot.send_message(message.chat.id, "📝 Введите класс (7А, 8Б и т.д.):")
        else:
            bot.send_message(message.chat.id, "❌ Неверный код. Попробуйте снова или /start")
        return

    # Проверка кода для завхоза
    if state == "zavhoz":
        if text == config.ACCESS_CODE_ZAVHOZ:
            save_user_role(user_id, "Завхоз", None)
            del waiting_for_code[user_id]
            bot.send_message(message.chat.id, "✅ Авторизованы как **Завхоз**\n\nИспользуйте /help", parse_mode='Markdown')
            logger.info(f"Пользователь {user_id}: Завхоз")
        else:
            bot.send_message(message.chat.id, "❌ Неверный код. Попробуйте снова или /start")
        return

    # Выбор класса для учителя
    if state == "teacher_class":
        save_user_role(user_id, "Учитель", text.upper())
        del waiting_for_code[user_id]
        bot.send_message(message.chat.id, f"✅ Авторизованы как **Учитель** (класс **{text.upper()}**)\n\nИспользуйте /help", parse_mode='Markdown')
        logger.info(f"Пользователь {user_id}: Учитель {text.upper()}")


# ==================== АВТОМАТИЧЕСКИЕ ЗАДАЧИ ====================

def scheduled_send_menu():
    """Автоматическая отправка меню в заданное время"""
    logger.info("Запуск автоматической отправки меню")

    try:
        from datetime import datetime

        today = datetime.now()
        cycle_week = get_current_week_cycle()
        day_name = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][today.weekday()]

        groups = get_all_groups()
        if not groups:
            logger.warning("Нет зарегистрированных групп для отправки меню")
            return

        for group_data in groups:
            chat_id = group_data['chat_id']
            class_name = group_data['class_name']

            try:
                # Отправка фото меню ПЕРВЫМ с напоминанием
                menu_image_path = get_today_menu_image()
                if not menu_image_path or not os.path.exists(menu_image_path):
                    menu_image_path = get_menu_image_path(class_name)

                if menu_image_path and os.path.exists(menu_image_path):
                    try:
                        with open(menu_image_path, 'rb') as photo:
                            bot.send_photo(chat_id, photo, caption="⏰ **Голосуйте до 20:00!**\n📸 Фото меню", parse_mode='Markdown')
                        logger.info(f"Фото меню отправлено в {class_name}")
                    except Exception as e:
                        logger.warning(f"Не удалось отправить фото меню в {class_name}: {e}")
                else:
                    # Если фото нет, хотя бы отправим напоминание
                    bot.send_message(chat_id, "⏰ **Голосуйте до 20:00!**", parse_mode='Markdown')

                # Теперь отправка текста меню с кнопками
                menu_text = get_today_menu_compact()
                header = f"📋 **Меню класса {class_name}**\n📅 **Неделя {cycle_week}** | {day_name}\n\n"

                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton("🥐🍽️ Завтрак+Обед", callback_data="vote_завтрак_обед"),
                    types.InlineKeyboardButton("🍽️ Обед", callback_data="vote_обед")
                )
                markup.add(
                    types.InlineKeyboardButton("🥐💳 Завтрак платно", callback_data="vote_завтрак_платно"),
                    types.InlineKeyboardButton("🥐🆓 Завтрак льготы", callback_data="vote_завтрак_льготы")
                )
                markup.add(
                    types.InlineKeyboardButton("❌ Не обедаю", callback_data="vote_не_обедает")
                )

                bot.send_message(chat_id, f"{header}{menu_text}\n\n👇 **Выберите вариант питания:**",
                               reply_markup=markup, parse_mode='Markdown')

                logger.info(f"Меню отправлено в {class_name} (неделя {cycle_week})")
            except Exception as e:
                logger.error(f"Ошибка при отправке в {chat_id}: {e}")

            time.sleep(1)

    except Exception as e:
        logger.error(f"Ошибка при автоотправке меню: {e}")


def scheduled_send_report():
    """Автоматическая отправка отчета в заданное время"""
    logger.info("Запуск автоматической отправки отчетов")

    try:
        from database import get_all_groups, get_all_students_in_class
        from datetime import date as date_module

        today = date_module.today().strftime("%Y-%m-%d")

        # Получение всех зарегистрированных групп
        groups = get_all_groups()

        if not groups:
            logger.warning("Нет зарегистрированных групп для отправки отчетов")
            return

        # Группируем по классам (может быть несколько групп одного класса)
        classes_dict = {}
        for group_data in groups:
            class_name = group_data['class_name']
            chat_id = group_data['chat_id']
            if class_name not in classes_dict:
                classes_dict[class_name] = []
            classes_dict[class_name].append(chat_id)

        # Для каждого класса отправляем отчет
        for class_name, chat_ids in classes_dict.items():
            try:
                # Получение учителя класса
                teacher_data = get_teacher_by_class(class_name)

                if not teacher_data:
                    logger.warning(f"Учитель для класса {class_name} не найден")
                    continue

                teacher_tg_id = teacher_data['teacher_tg_id']

                # 1. Отправка Excel-отчета учителю в личные сообщения
                try:
                    excel_path = generate_excel_report(class_name, today)
                    with open(excel_path, 'rb') as file:
                        bot.send_document(
                            teacher_tg_id,
                            file,
                            caption=f"📊 Список питающихся в {class_name} ({today})"
                        )
                    logger.info(f"Excel-отчет отправлен учителю {teacher_tg_id} для класса {class_name}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке Excel-отчета для {class_name}: {e}")

                # 2. Отправка статистики учителю в личный чат
                try:
                    stats_text = get_group_statistics_text(class_name, today)
                    bot.send_message(teacher_tg_id, stats_text, parse_mode='Markdown')
                    logger.info(f"Статистика отправлена учителю {teacher_tg_id} (класс {class_name})")
                except Exception as e:
                    logger.error(f"Ошибка при отправке статистики учителю {teacher_tg_id}: {e}")

                time.sleep(1)  # Задержка между отправками

            except Exception as e:
                logger.error(f"Ошибка при обработке класса {class_name}: {e}")

        logger.info("Отчеты успешно отправлены")

    except Exception as e:
        logger.error(f"Ошибка при автоотправке отчетов: {e}")



def setup_scheduler():
    """Настройка планировщика"""
    try:
        # Парсим время из конфига
        menu_hour, menu_minute = map(int, config.SCHEDULE_MENU_TIME.split(':'))
        report_hour, report_minute = map(int, config.SCHEDULE_REPORT_TIME.split(':'))

        # Меню в заданное время (пн-сб)
        scheduler.add_job(
            scheduled_send_menu,
            CronTrigger(hour=menu_hour, minute=menu_minute, day_of_week='mon-sat'),
            id='send_menu',
            replace_existing=True
        )

        # Отчет в заданное время (пн-сб)
        scheduler.add_job(
            scheduled_send_report,
            CronTrigger(hour=report_hour, minute=report_minute, day_of_week='mon-sat'),
            id='send_report',
            replace_existing=True
        )

        scheduler.start()
        logger.info("Планировщик запущен")
        logger.info(f"Меню: каждый день в {config.SCHEDULE_MENU_TIME} (пн-сб)")
        logger.info(f"Отчет: каждый день в {config.SCHEDULE_REPORT_TIME} (пн-сб)")

        setup_menu_upload(bot)
        logger.info("Загрузка меню включена")

    except Exception as e:
        logger.error(f"Ошибка при настройке планировщика: {e}")


# ==================== ЗАПУСК БОТА ====================

def main():
    """Главная функция запуска бота"""
    logger.info("Запуск бота для автоматизации школьной столовой")

    # Инициализация базы данных
    from database import init_database
    init_database()
    logger.info("База данных инициализирована")

    # Создание папки для картинок меню
    setup_menu_images_directory()
    setup_pdf_images_directory()
    logger.info("Папка для картинок меню подготовлена")

    # Проверка токена
    if config.TELEGRAM_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("⚠️ Токен бота не установлен! Измените значение в config.py")
        return

    # Настройка планировщика
    setup_scheduler()

    # Запуск бота с автоматическим переподключением
    logger.info("Бот готов к работе. Ожидание команд...")

    while True:
        try:
            bot.infinity_polling(none_stop=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
            logger.info("Переподключение через 5 секунд...")
            time.sleep(5)


if __name__ == '__main__':
    main()
