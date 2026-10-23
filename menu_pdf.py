"""
Модуль для работы с PDF меню
Извлекает страницы из PDF и конвертирует их в изображения для отправки
"""
import os
from pathlib import Path
from datetime import date
from pypdf import PdfReader
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# Путь к PDF файлу с меню
MENU_PDF_PATH = Path(__file__).parent / "Меню 01_09_2026.pdf"
MENU_IMAGES_DIR = Path(__file__).parent / "menu_images_pdf"


def get_current_week_cycle() -> int:
    """
    Определяет номер текущей недели в цикле (1 или 2)
    Начинает отсчет с 1 сентября 2026 года

    Returns:
        1 или 2 - номер недели в цикле
    """
    today = date.today()
    # Начало учебного года
    start_date = date(2026, 9, 1)

    # Если сегодня до начала учебного года, считаем от прошлого года
    if today < start_date:
        start_date = date(2025, 9, 1)

    # Количество недель с начала учебного года
    days_passed = (today - start_date).days
    weeks_passed = days_passed // 7

    # Цикл из 2 недель
    cycle_week = (weeks_passed % 2) + 1
    return cycle_week


def setup_pdf_images_directory():
    """Создает директорию для хранения изображений из PDF"""
    MENU_IMAGES_DIR.mkdir(exist_ok=True)


def get_pdf_page_as_image(page_number: int) -> str:
    """
    Извлекает страницу из PDF и сохраняет как изображение

    Args:
        page_number: Номер страницы (0-based)

    Returns:
        Путь к сохраненному изображению или None
    """
    if not MENU_PDF_PATH.exists():
        return None

    if not PYMUPDF_AVAILABLE:
        return None

    setup_pdf_images_directory()

    try:
        # Открываем PDF
        doc = fitz.open(str(MENU_PDF_PATH))

        if page_number >= len(doc):
            return None

        # Извлекаем страницу
        page = doc[page_number]

        # Конвертируем в изображение (150 DPI)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

        # Сохраняем
        image_path = MENU_IMAGES_DIR / f"page_{page_number}.png"
        pix.save(str(image_path))

        doc.close()
        return str(image_path)

    except Exception as e:
        print(f"Ошибка при извлечении страницы {page_number}: {e}")
        return None


def get_today_menu_image() -> str:
    """
    Получает изображение меню на сегодня из PDF

    Returns:
        Путь к изображению или None
    """
    today = date.today()
    weekday = today.weekday()  # 0 = понедельник, 6 = воскресенье

    # Выходные - нет меню
    if weekday in [5, 6]:
        return None

    # Определяем неделю в цикле
    cycle_week = get_current_week_cycle()

    # Страницы в PDF:
    # Неделя 1: Пн-Пт (страницы 0-4)
    # Неделя 2: Пн-Пт (страницы 5-9)
    if cycle_week == 1:
        page_number = weekday  # 0-4 (Пн-Пт)
    else:
        page_number = 5 + weekday  # 5-9 (Пн-Пт второй недели)

    return get_pdf_page_as_image(page_number)


def check_pdf_available() -> bool:
    """Проверяет доступность PDF и PyMuPDF"""
    return MENU_PDF_PATH.exists() and PYMUPDF_AVAILABLE


def get_pdf_info() -> dict:
    """Получает информацию о PDF файле"""
    if not MENU_PDF_PATH.exists():
        return {"error": "PDF файл не найден"}

    try:
        reader = PdfReader(str(MENU_PDF_PATH))
        return {
            "pages": len(reader.pages),
            "path": str(MENU_PDF_PATH),
            "pymupdf_available": PYMUPDF_AVAILABLE
        }
    except Exception as e:
        return {"error": str(e)}
