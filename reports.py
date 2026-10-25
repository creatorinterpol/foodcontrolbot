"""
Генерация отчетов о питании
Создает текстовую статистику и Excel-файлы для классных руководителей
"""
import os
from datetime import date
from typing import Tuple
import pandas as pd
import config
from database import get_class_votes, get_all_groups


def get_school_stats(report_date: str = None) -> str:
    """Статистика по всей школе (начальная и старшая)"""
    if report_date is None:
        report_date = date.today().strftime("%Y-%m-%d")

    groups = get_all_groups()
    classes = set(g['class_name'] for g in groups)

    primary = {'eating': 0, 'paid': 0, 'free': 0, 'no_meal': 0}
    secondary = {'eating': 0, 'paid': 0, 'free': 0, 'no_meal': 0}

    for cls in classes:
        votes = get_class_votes(cls, report_date)
        is_primary = any(int(c) <= 4 for c in cls if c.isdigit())
        stats = primary if is_primary else secondary

        stats['paid'] += sum(1 for v in votes if v['status'] == 'платно')
        stats['free'] += sum(1 for v in votes if v['status'] == 'бесплатно')
        stats['no_meal'] += sum(1 for v in votes if v['status'] == 'не обедает')
        stats['eating'] += stats['paid'] + stats['free']

    date_obj = date.fromisoformat(report_date)
    formatted_date = date_obj.strftime("%d.%m.%Y")

    text = f"📊 **Питание школы** ({formatted_date})\n\n"
    text += f"🏫 **Начальная школа (1-4):**\n• Питается: {primary['eating']} (платно: {primary['paid']}, бесплатно: {primary['free']})\n• Не питаются: {primary['no_meal']}\n\n"
    text += f"📚 **Старшая школа (5-11):**\n• Питается: {secondary['eating']} (платно: {secondary['paid']}, бесплатно: {secondary['free']})\n• Не питаются: {secondary['no_meal']}"

    return text


def generate_daily_stats(class_name: str, report_date: str = None) -> str:
    """
    Генерация текстовой статистики по питанию класса

    Args:
        class_name: Название класса
        report_date: Дата отчета (по умолчанию сегодня)

    Returns:
        Отформатированный текст статистики
    """
    if report_date is None:
        report_date = date.today().strftime("%Y-%m-%d")

    votes = get_class_votes(class_name, report_date)

    # Подсчет по новым категориям
    total_breakfast_lunch = sum(1 for v in votes if v['status'] == 'завтрак_обед')
    total_lunch = sum(1 for v in votes if v['status'] == 'обед')
    total_breakfast_paid = sum(1 for v in votes if v['status'] == 'завтрак_платно')
    total_breakfast_free = sum(1 for v in votes if v['status'] == 'завтрак_льготы')
    total_eating = total_breakfast_lunch + total_lunch + total_breakfast_paid + total_breakfast_free

    # Форматирование даты для отображения
    date_obj = date.fromisoformat(report_date)
    formatted_date = date_obj.strftime("%d.%m.%Y")

    stats_text = f"""📊 **Питание: {class_name}** ({formatted_date})

• Завтрак+Обед: **{total_breakfast_lunch}**
• Обед: **{total_lunch}**
• Завтрак платно: **{total_breakfast_paid}**
• Завтрак льготы: **{total_breakfast_free}**

Всего питается: {total_eating} чел."""

    return stats_text


def generate_excel_report(class_name: str, report_date: str = None) -> str:
    """
    Генерация Excel-отчета с таблицей по категориям питания

    Args:
        class_name: Название класса
        report_date: Дата отчета (по умолчанию сегодня)

    Returns:
        Путь к созданному файлу
    """
    if report_date is None:
        report_date = date.today().strftime("%Y-%m-%d")

    votes = get_class_votes(class_name, report_date)

    # Категории питания
    categories = {
        'завтрак_обед': [],
        'обед': [],
        'завтрак_платно': [],
        'завтрак_льготы': [],
        'не_обедает': []
    }

    # Распределение по категориям
    for vote in votes:
        status = vote['status']
        if status in categories:
            categories[status].append(vote['student_name'])
        elif status == 'не обедает':
            categories['не_обедает'].append(vote['student_name'])

    # Сортировка внутри каждой категории
    for cat in categories:
        categories[cat].sort()

    # Определяем максимальное количество строк
    max_rows = max(len(v) for v in categories.values()) if any(categories.values()) else 1

    # Построение таблицы
    data = {}
    headers = {
        'завтрак_обед': 'Завтрак+Обед',
        'обед': 'Обед',
        'завтрак_платно': 'Завтрак платно',
        'завтрак_льготы': 'Завтрак льготы',
        'не_обедает': 'Не обедает'
    }

    for cat_key, cat_label in headers.items():
        data[cat_label] = []
        students = categories[cat_key]
        for i in range(max_rows):
            if i < len(students):
                data[cat_label].append('✓ ' + students[i])
            else:
                data[cat_label].append('')

    df = pd.DataFrame(data)

    # Создание директории для отчетов
    if not os.path.exists(config.REPORTS_DIR):
        os.makedirs(config.REPORTS_DIR)

    # Формирование имени файла
    filename = f"питание_{class_name}_{report_date}.xlsx"
    filepath = os.path.join(config.REPORTS_DIR, filename)

    # Экспорт в Excel с форматированием
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Питание')

        # Получение рабочего листа для форматирования
        worksheet = writer.sheets['Питание']

        # Автоподбор ширины колонок
        for idx, col in enumerate(df.columns, 1):
            max_length = max(
                df[col].astype(str).apply(len).max(),
                len(col),
                15
            )
            worksheet.column_dimensions[chr(64 + idx)].width = max_length + 2

    return filepath


def get_summary_stats(class_name: str, report_date: str = None) -> Tuple[int, int, int, int, int]:
    """
    Получение числовой статистики по новым категориям

    Args:
        class_name: Название класса
        report_date: Дата отчета

    Returns:
        Кортеж (завтрак_обед, обед, завтрак_платно, завтрак_льготы, всего_питается)
    """
    if report_date is None:
        report_date = date.today().strftime("%Y-%m-%d")

    votes = get_class_votes(class_name, report_date)

    total_breakfast_lunch = sum(1 for v in votes if v['status'] == 'завтрак_обед')
    total_lunch = sum(1 for v in votes if v['status'] == 'обед')
    total_breakfast_paid = sum(1 for v in votes if v['status'] == 'завтрак_платно')
    total_breakfast_free = sum(1 for v in votes if v['status'] == 'завтрак_льготы')
    total_eating = total_breakfast_lunch + total_lunch + total_breakfast_paid + total_breakfast_free

    return total_breakfast_lunch, total_lunch, total_breakfast_paid, total_breakfast_free, total_eating


def get_group_statistics_text(class_name: str, report_date: str = None) -> str:
    """
    Генерация краткой статистики для отправки в групповой чат

    Args:
        class_name: Название класса
        report_date: Дата отчета (по умолчанию сегодня)

    Returns:
        Отформатированный текст статистики для группы
    """
    if report_date is None:
        report_date = date.today().strftime("%Y-%m-%d")

    total_breakfast_lunch, total_lunch, total_breakfast_paid, total_breakfast_free, total_eating = get_summary_stats(class_name, report_date)

    # Форматирование даты для отображения
    date_obj = date.fromisoformat(report_date)
    formatted_date = date_obj.strftime("%d.%m.%Y")

    stats_text = f"""📊 Питание: {class_name} ({formatted_date})
• Завтрак+Обед: {total_breakfast_lunch}
• Обед: {total_lunch}
• Завтрак платно: {total_breakfast_paid}
• Завтрак льготы: {total_breakfast_free}

Всего питается: {total_eating} чел."""

    return stats_text
