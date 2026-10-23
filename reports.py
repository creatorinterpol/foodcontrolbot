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

    # Подсчет статистики
    total_paid = sum(1 for v in votes if v['status'] == 'платно')
    total_free = sum(1 for v in votes if v['status'] == 'бесплатно')
    total_no_meal = sum(1 for v in votes if v['status'] == 'не обедает')
    total_eating = total_paid + total_free

    # Форматирование даты для отображения
    date_obj = date.fromisoformat(report_date)
    formatted_date = date_obj.strftime("%d.%m.%Y")

    stats_text = f"""📊 **Питание: {class_name}** ({formatted_date})

• Всего питается: **{total_eating} чел.**
  — Платно: {total_paid}
  — Бесплатно: {total_free}
• Не питаются: {total_no_meal}

Всего проголосовало: {len(votes)} чел."""

    return stats_text


def generate_excel_report(class_name: str, report_date: str = None) -> str:
    """
    Генерация Excel-отчета со списком учеников класса

    Args:
        class_name: Название класса
        report_date: Дата отчета (по умолчанию сегодня)

    Returns:
        Путь к созданному файлу
    """
    if report_date is None:
        report_date = date.today().strftime("%Y-%m-%d")

    votes = get_class_votes(class_name, report_date)

    # Подготовка данных для DataFrame
    data = {
        'Фамилия и Имя': [v['student_name'] for v in votes],
        'Категория питания': [v['status'].capitalize() for v in votes]
    }

    df = pd.DataFrame(data)

    # Сортировка по алфавиту
    df = df.sort_values('Фамилия и Имя')

    # Создание директории для отчетов, если её нет
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
                len(col)
            )
            worksheet.column_dimensions[chr(64 + idx)].width = max_length + 2

    return filepath


def get_summary_stats(class_name: str, report_date: str = None) -> Tuple[int, int, int, int]:
    """
    Получение числовой статистики (для использования в коде)

    Args:
        class_name: Название класса
        report_date: Дата отчета

    Returns:
        Кортеж (всего_питается, платно, бесплатно, не_обедает)
    """
    if report_date is None:
        report_date = date.today().strftime("%Y-%m-%d")

    votes = get_class_votes(class_name, report_date)

    total_paid = sum(1 for v in votes if v['status'] == 'платно')
    total_free = sum(1 for v in votes if v['status'] == 'бесплатно')
    total_no_meal = sum(1 for v in votes if v['status'] == 'не обедает')
    total_eating = total_paid + total_free

    return total_eating, total_paid, total_free, total_no_meal


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

    total_eating, total_paid, total_free, total_no_meal = get_summary_stats(class_name, report_date)

    # Форматирование даты для отображения
    date_obj = date.fromisoformat(report_date)
    formatted_date = date_obj.strftime("%d.%m.%Y")

    stats_text = f"""📊 Питание: {class_name} ({formatted_date})
• Всего питается: {total_eating} чел.
  — Платно: {total_paid}
  — Бесплатно: {total_free}
• Не питаются: {total_no_meal}"""

    return stats_text
