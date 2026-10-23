"""Загрузка фото меню"""
import os
from telebot import types

def setup_menu_upload(bot):
    """Настройка загрузки фото меню"""

    @bot.message_handler(commands=['upload_menu'])
    def upload_menu_start(message):
        user_id = str(message.from_user.id)
        from database_auth import get_user_role

        if get_user_role(user_id) != "Завхоз":
            bot.send_message(message.chat.id, "⛔️ Только завхоз может загружать меню")
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("1-4 классы", callback_data="menu_1-4"))
        markup.add(types.InlineKeyboardButton("5-11 классы", callback_data="menu_5-11"))

        bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
    def choose_category(call):
        category = call.data.split("_")[1]
        msg = bot.send_message(call.message.chat.id, f"Отправьте фото для {category} классов (название файла = класс, например 1A.jpg)")
        bot.register_next_step_handler(msg, lambda m: save_menu_photo(m, category))

    def save_menu_photo(message, category):
        if not message.photo:
            bot.send_message(message.chat.id, "❌ Отправьте фото")
            return

        msg = bot.send_message(message.chat.id, "Укажите класс (например: 1A, 5B):")
        bot.register_next_step_handler(msg, lambda m: download_and_save(m, message.photo, category))

    def download_and_save(message, photo, category):
        class_name = message.text.strip().upper()

        # Создание директории
        dir_path = f"menu_images/{category}"
        os.makedirs(dir_path, exist_ok=True)

        # Скачивание фото
        file_info = bot.get_file(photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Сохранение
        file_path = f"{dir_path}/{class_name}.jpg"
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)

        bot.send_message(message.chat.id, f"✅ Фото для класса {class_name} загружено")
