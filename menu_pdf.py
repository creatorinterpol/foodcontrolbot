"""
Модуль для работы с картинками меню
Использует заранее сгенерированные изображения страниц меню (легковесный режим без PyMuPDF)
"""
import os
from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).parent
MENU_PDF_PATH = BASE_DIR / "Меню 01_09_2026.pdf"
MENU_IMAGES_DIR = BASE_DIR / "menu_images"
MENU_IMAGES_PDF_DIR = BASE_DIR / "menu_images_pdf"


def get_current_week_cycle() -> int:
    """Определяет номер текущей недели в цикле (1 или 2)"""
    today = date.today()
    start_date = date(2026, 9, 1)
    if today < start_date:
        start_date = date(2025, 9, 1)

    days_passed = (today - start_date).days
    weeks_passed = days_passed // 7
    cycle_week = (weeks_passed % 2) + 1
    return cycle_week


def setup_pdf_images_directory():
    """Создает директории при необходимости"""
    MENU_IMAGES_DIR.mkdir(exist_ok=True)
    MENU_IMAGES_PDF_DIR.mkdir(exist_ok=True)


def get_today_menu_image() -> str:
    """Получает изображение меню на сегодня"""
    today = date.today()
    weekday = today.weekday()

    if weekday >= 5:
        return None

    cycle_week = get_current_week_cycle()

    day_names = {
        0: 'понедельник',
        1: 'вторник',
        2: 'среда',
        3: 'четверг',
        4: 'пятница'
    }

    day_name = day_names.get(weekday)
    if not day_name:
        return None

    filename = f"{day_name}_2.jpg" if cycle_week == 2 else f"{day_name}.jpg"

    img_path = MENU_IMAGES_DIR / filename
    if img_path.exists():
        return str(img_path)

    page_number = weekday if cycle_week == 1 else (6 + weekday)
    pdf_img_path = MENU_IMAGES_PDF_DIR / f"page_{page_number}.png"
    if pdf_img_path.exists():
        return str(pdf_img_path)

    return None


def check_pdf_available() -> bool:
    today_img = get_today_menu_image()
    return today_img is not None or MENU_PDF_PATH.exists()


def get_pdf_info() -> dict:
    return {
        "status": "ready",
        "images_dir": str(MENU_IMAGES_DIR),
        "pdf_exists": MENU_PDF_PATH.exists()
    }
