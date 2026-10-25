"""
Функции для работы с авторизацией пользователей
Оснащены быстрым in-memory кэшем для мгновенного ответа бота (0 мс)
"""
from database import get_db_connection

# Быстрый оперативный кэш ролей и классов в оперативной памяти
_ROLES_CACHE = {}  # {user_id: {'role': role, 'class_name': class_name}}


def save_user_role(user_id: str, role: str, class_name: str = None):
    """Сохранение роли пользователя и класса"""
    user_id = str(user_id)
    _ROLES_CACHE[user_id] = {'role': role, 'class_name': class_name}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
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
        cursor.execute('''
            REPLACE INTO user_roles (user_id, role, class_name)
            VALUES (?, ?, ?)
        ''', (user_id, role, class_name))

    conn.commit()
    conn.close()


def get_user_role(user_id: str) -> str:
    """Получение роли пользователя (с проверкой кэша)"""
    user_id = str(user_id)
    if user_id in _ROLES_CACHE:
        return _ROLES_CACHE[user_id].get('role')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT role, class_name FROM user_roles WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        if row:
            _ROLES_CACHE[user_id] = {'role': row[0], 'class_name': row[1]}
            return row[0]
        else:
            _ROLES_CACHE[user_id] = {'role': None, 'class_name': None}
            return None
    except Exception:
        pass
    finally:
        conn.close()

    return None


def get_user_class(user_id: str) -> str:
    """Получение класса пользователя (с проверкой кэша)"""
    user_id = str(user_id)
    if user_id in _ROLES_CACHE and _ROLES_CACHE[user_id].get('class_name') is not None:
        return _ROLES_CACHE[user_id].get('class_name')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT role, class_name FROM user_roles WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        if row:
            _ROLES_CACHE[user_id] = {'role': row[0], 'class_name': row[1]}
            return row[1]
    except Exception:
        pass
    finally:
        conn.close()

    return None


def delete_user_role(user_id: str):
    """Удаление роли пользователя (выход)"""
    user_id = str(user_id)
    _ROLES_CACHE.pop(user_id, None)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('DELETE FROM user_roles WHERE user_id = %s', (user_id,))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()