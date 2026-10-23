"""Миграция: добавление колонки class_name в user_roles"""
from database import get_db_connection

def migrate():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE user_roles ADD COLUMN class_name TEXT")
        conn.commit()
        print("✅ Колонка class_name добавлена")
    except Exception as e:
        if "already exists" in str(e) or "duplicate column" in str(e).lower():
            print("⚠️ Колонка class_name уже существует")
        else:
            print(f"❌ Ошибка: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
