"""
Модуль для работы с картинками меню
Двухнедельное циклическое меню (10 рабочих дней)
"""
import os
from datetime import date, timedelta
import config


def get_menu_image_path() -> str:
    """
    Определяет путь к картинке меню на сегодня

    Меню циклическое двухнедельное:
    - Неделя 1: понедельник.jpg, вторник.jpg, ..., пятница.jpg
    - Неделя 2: понедельник_2.jpg, вторник_2.jpg, ..., пятница_2.jpg

    Returns:
        Путь к файлу картинки или None если выходной
    """
    today = date.today()
    weekday = today.weekday()  # 0 = понедельник, 6 = воскресенье

    # Если выходной (суббота или воскресенье)
    if weekday >= 5:
        return None

    # Определяем неделю (четная/нечетная по номеру недели в году)
    week_number = today.isocalendar()[1]
    is_even_week = (week_number % 2 == 0)

    # Названия дней недели
    day_names = {
        0: 'понедельник',
        1: 'вторник',
        2: 'среда',
        3: 'четверг',
        4: 'пятница'
    }

    day_name = day_names[weekday]

    # Формируем имя файла
    if is_even_week:
        filename = f"{day_name}_2.jpg"
    else:
        filename = f"{day_name}.jpg"

    filepath = os.path.join(config.MENU_IMAGES_DIR, filename)

    # Проверяем существование файла
    if os.path.exists(filepath):
        return filepath
    else:
        # Если файл не найден, возвращаем путь-заглушку
        return None


def get_menu_image_for_day(weekday: int, week: int = 1) -> str:
    """
    Получить путь к картинке меню для конкретного дня

    Args:
        weekday: День недели (0-4, понедельник-пятница)
        week: Номер недели (1 или 2)

    Returns:
        Путь к файлу картинки
    """
    day_names = {
        0: 'понедельник',
        1: 'вторник',
        2: 'среда',
        3: 'четверг',
        4: 'пятница'
    }

    if weekday not in day_names:
        return None

    day_name = day_names[weekday]

    if week == 2:
        filename = f"{day_name}_2.jpg"
    else:
        filename = f"{day_name}.jpg"

    return os.path.join(config.MENU_IMAGES_DIR, filename)


def is_weekend() -> bool:
    """
    Проверка, является ли сегодня выходным

    Returns:
        True если суббота или воскресенье
    """
    today = date.today()
    return today.weekday() >= 5


def setup_menu_images_directory():
    """
    Создает директорию для картинок меню и файл README
    """
    if not os.path.exists(config.MENU_IMAGES_DIR):
        os.makedirs(config.MENU_IMAGES_DIR)

    readme_path = os.path.join(config.MENU_IMAGES_DIR, 'README.txt')

    if not os.path.exists(readme_path):
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write("""Папка для хранения картинок меню

Двухнедельное циклическое меню (10 файлов):

НЕДЕЛЯ 1 (нечетная по номеру недели в году):
- понедельник.jpg
- вторник.jpg
- среда.jpg
- четверг.jpg
- пятница.jpg

НЕДЕЛЯ 2 (четная по номеру недели в году):
- понедельник_2.jpg
- вторник_2.jpg
- среда_2.jpg
- четверг_2.jpg
- пятница_2.jpg

Формат файлов: JPG, PNG, WEBP
Рекомендуемый размер: 800x600 или 1024x768

Пример создания картинки меню:
1. Откройте любой графический редактор (Photoshop, Figma, Canva)
2. Создайте изображение с меню на день
3. Сохраните с соответствующим названием
4. Положите файл в эту папку

Бот автоматически определит нужную картинку по дню недели и неделе.
""")
