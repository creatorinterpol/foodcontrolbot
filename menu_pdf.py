"""
Модуль для работы с картинками меню (6-дневная учебная неделя)
Поддерживает как кириллические имена файлов, так и ASCII-алиасы (для надежности на Linux)
"""
import os
from pathlib import Path
from datetime import date
from menu import get_current_week_cycle, get_target_menu_date

BASE_DIR = Path(__file__).parent
MENU_IMAGES_DIR = BASE_DIR / "menu_images"
MENU_IMAGES_PDF_DIR = BASE_DIR / "menu_images_pdf"


def setup_pdf_images_directory():
    """Создает директории для картинок при необходимости"""
    try:
        MENU_IMAGES_DIR.mkdir(exist_ok=True)
        MENU_IMAGES_PDF_DIR.mkdir(exist_ok=True)
    except Exception:
        pass


def get_today_menu_image() -> str:
    """Получает путь к изображению меню на целевой учебный день"""
    target_date = get_target_menu_date()
    weekday = target_date.weekday()

    if weekday == 6:  # Воскресенье
        return None

    cycle_week = get_current_week_cycle(target_date)

    day_names = {
        0: 'понедельник',
        1: 'вторник',
        2: 'среда',
        3: 'четверг',
        4: 'пятница',
        5: 'суббота'
    }

    day_name = day_names.get(weekday, '')
    page_num = weekday if cycle_week == 1 else (6 + weekday)

    candidate_filenames = [
        f"day_{weekday}_week_{cycle_week}.jpg",
        f"page_{page_num}.jpg",
        f"{day_name}_2.jpg" if cycle_week == 2 else f"{day_name}.jpg",
        f"page_{page_num}.png"
    ]

    for search_dir in [MENU_IMAGES_DIR, MENU_IMAGES_PDF_DIR]:
        if search_dir.exists():
            for name in candidate_filenames:
                p = search_dir / name
                if p.exists():
                    return str(p)

    return None


def check_pdf_available() -> bool:
    return get_today_menu_image() is not None


def get_pdf_info() -> dict:
    return {
        "status": "ready",
        "images_dir": str(MENU_IMAGES_DIR),
        "today_image": get_today_menu_image()
    }