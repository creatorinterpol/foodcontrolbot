"""
Тестовый бот - локальная версия для проверки без интернета
"""
from database import save_vote, get_class_votes
from menu import get_today_menu
from reports import generate_daily_stats, generate_excel_report
import config
from datetime import date

print("🤖 Тестовый режим бота\n")

# Тест 1: Проверка меню
print("=" * 50)
print("ТЕСТ 1: Получение меню на сегодня")
print("=" * 50)
menu = get_today_menu()
print(menu)
print()

# Тест 2: Сохранение голосов
print("=" * 50)
print("ТЕСТ 2: Сохранение голосов учеников")
print("=" * 50)

test_votes = [
    ("8848536754", "Иванов Иван", "платно"),
    ("1234567890", "Петров Петр", "бесплатно"),
    ("9876543210", "Сидоров Сергей", "не обедает"),
    ("1111111111", "Смирнова Елена", "платно"),
    ("2222222222", "Кузнецова Анна", "платно"),
]

for user_id, name, status in test_votes:
    save_vote(config.DEFAULT_CLASS, user_id, name, status)
    print(f"✅ Сохранен голос: {name} ({status})")

print()

# Тест 3: Получение статистики
print("=" * 50)
print("ТЕСТ 3: Получение статистики")
print("=" * 50)
stats = generate_daily_stats(config.DEFAULT_CLASS)
print(stats)
print()

# Тест 4: Генерация Excel
print("=" * 50)
print("ТЕСТ 4: Генерация Excel-отчета")
print("=" * 50)
try:
    excel_file = generate_excel_report(config.DEFAULT_CLASS)
    print(f"✅ Excel-файл создан: {excel_file}")
    print(f"   Вы можете открыть его в папке 'reports'")
except Exception as e:
    print(f"❌ Ошибка при создании Excel: {e}")

print()

# Тест 5: Получение голосов из БД
print("=" * 50)
print("ТЕСТ 5: Данные из базы данных")
print("=" * 50)
votes = get_class_votes(config.DEFAULT_CLASS)
print(f"Всего голосов: {len(votes)}\n")
for vote in votes:
    print(f"  • {vote['student_name']}: {vote['status']}")

print()
print("=" * 50)
print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
print("=" * 50)
print(f"\n📁 Excel-отчет сохранен в папке: reports/")
print(f"💾 База данных: {config.DATABASE_PATH}")
