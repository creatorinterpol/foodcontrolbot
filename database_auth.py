"""
Функции для работы с авторизацией пользователей
"""
from database import get_db_connection


def save_user_role(user_id: str, role: str, class_name: str = None):
    """Сохранение роли пользователя и класса"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Попытка UPDATE, если не сработает - INSERT
        cursor.execute(
            'UPDATE user_roles SET role = %s, class_name = %s WHERE user_id = %s',
            (role, class_name, user_id)
        )

        if cursor.rowcount == 0:
            cursor.execute(
                'INSERT INTO user_roles (user_id, role, class_name) VALUES (%s, %s, %s)',
                (user_id, role, class_name)
            )
    except:
        # Для SQLite
        cursor.execute('''
            REPLACE INTO user_roles (user_id, role, class_name)
            VALUES (?, ?, ?)
        ''', (user_id, role, class_name))

    conn.commit()
    conn.close()


def get_user_role(user_id: str) -> str:
    """Получение роли пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT role FROM user_roles WHERE user_id = %s', (user_id,))
    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def get_user_class(user_id: str) -> str:
    """Получение класса пользователя"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT class_name FROM user_roles WHERE user_id = %s', (user_id,))
    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def delete_user_role(user_id: str):
    """Удаление роли пользователя (выход)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM user_roles WHERE user_id = %s', (user_id,))

    conn.commit()
    conn.close()



