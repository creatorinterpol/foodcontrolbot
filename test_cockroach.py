"""Тест подключения к CockroachDB"""
import os
from database import init_database, max_save_vote, max_get_class_votes

# Установи переменные окружения перед запуском:
# set DATABASE_TYPE=cockroach
# set DATABASE_URL=postgres://...

print("🔌 Тест CockroachDB")
print(f"Тип БД: {os.getenv('DATABASE_TYPE', 'sqlite')}")

try:
    print("\n1️⃣ Инициализация таблиц...")
    init_database()
    print("✅ Таблицы созданы")

    print("\n2️⃣ Тестовый голос...")
    max_save_vote('2026-10-22', '7А', '12345', 'Тест Тестов', 'платно')
    print("✅ Голос сохранён")

    print("\n3️⃣ Чтение голосов...")
    votes = max_get_class_votes('2026-10-22', '7А')
    print(f"✅ Найдено голосов: {len(votes)}")
    for v in votes:
        print(f"  - {v[1]}: {v[2]}")

    print("\n🎉 Всё работает!")

except Exception as e:
    print(f"\n❌ Ошибка: {e}")
