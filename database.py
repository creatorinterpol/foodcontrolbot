"""
Слой работы с базой данных (SQLite/CockroachDB)
"""
import sqlite3
from datetime import date
from typing import List, Dict
from contextlib import contextmanager
import config

try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class PostgresCursorWrapper:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=None):
        import re
        sql = re.sub(r'\bREPLACE\s+INTO\b', 'UPSERT INTO', sql, flags=re.IGNORECASE)
        if params is not None:
            sql = sql.replace('?', '%s')
            self._cur.execute(sql, params)
        else:
            self._cur.execute(sql)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def close(self):
        if hasattr(self._cur, 'closed') and not self._cur.closed:
            self._cur.close()


class PostgresConnectionWrapper:
    """Обертка для соединения psycopg2, обеспечивающая совместимость с интерфейсом sqlite3."""
    def __init__(self, conn):
        self._conn = conn
        self._cur = None

    def execute(self, sql, params=None):
        self._cur = self.cursor()
        return self._cur.execute(sql, params)

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._cur:
            self._cur.close()
        if hasattr(self._conn, 'closed') and not self._conn.closed:
            self._conn.close()


def get_db_connection():
    """Возвращает подключение к БД: CockroachDB или SQLite"""
    if config.DATABASE_TYPE == 'cockroach':
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError('psycopg2 не установлен')
        return PostgresConnectionWrapper(psycopg2.connect(config.DATABASE_URL))
    else:
        return get_db_connection()


@contextmanager
def _max_connection():
    """Открывает и гарантированно закрывает соединение для MAX-таблиц."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Инициализация базы данных и создание таблиц"""
    conn = get_db_connection()

    cursor = conn.cursor()

    # Таблица голосов учеников
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            date TEXT NOT NULL,
            class_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (date, class_name, user_id)
        )
    ''')

    # Таблица привязки учителей к классам
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teacher_classes (
            id SERIAL PRIMARY KEY,
            class_name TEXT NOT NULL UNIQUE,
            teacher_tg_id TEXT NOT NULL,
            teacher_name TEXT,
            group_chat_id TEXT,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица групп
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            chat_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица студентов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            user_id TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            class_name TEXT,
            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица ролей пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            class_name TEXT,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS max_votes (
            vote_date TEXT NOT NULL,
            class_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (vote_date, class_name, user_id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS max_groups (
            chat_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS max_teachers (
            class_name TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            teacher_name TEXT
        )
    ''')

    conn.commit()
    conn.close()


def max_bind_group(chat_id: str, group_name: str, class_name: str):
    with _max_connection() as conn:
        conn.execute('''
            INSERT INTO max_groups (chat_id, group_name, class_name)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                group_name = excluded.group_name,
                class_name = excluded.class_name
        ''', (str(chat_id), group_name, class_name))


def max_get_group_class(chat_id: str):
    with _max_connection() as conn:
        row = conn.execute('SELECT class_name FROM max_groups WHERE chat_id = ?', (str(chat_id),)).fetchone()
        return row[0] if row else None


def max_get_groups():
    with _max_connection() as conn:
        rows = conn.execute('SELECT chat_id, group_name, class_name FROM max_groups ORDER BY class_name').fetchall()
        return [{'chat_id': row[0], 'group_name': row[1], 'class_name': row[2]} for row in rows]


def max_register_teacher(class_name: str, user_id: str, teacher_name: str, allow_replace: bool = False):
    with _max_connection() as conn:
        existing = conn.execute(
            'SELECT user_id FROM max_teachers WHERE class_name = ?', (class_name,)
        ).fetchone()
        if existing and existing[0] != str(user_id) and not allow_replace:
            return False
        conn.execute('''
            INSERT INTO max_teachers (class_name, user_id, teacher_name)
            VALUES (?, ?, ?)
            ON CONFLICT(class_name) DO UPDATE SET
                user_id = excluded.user_id,
                teacher_name = excluded.teacher_name
        ''', (class_name, str(user_id), teacher_name))
        return True


def max_get_teacher(class_name: str):
    with _max_connection() as conn:
        row = conn.execute('SELECT user_id, teacher_name FROM max_teachers WHERE class_name = ?', (class_name,)).fetchone()
        return {'user_id': row[0], 'teacher_name': row[1]} if row else None


def max_get_teacher_classes(user_id: str):
    with _max_connection() as conn:
        rows = conn.execute(
            'SELECT class_name FROM max_teachers WHERE user_id = ? ORDER BY class_name',
            (str(user_id),),
        ).fetchall()
        return [row[0] for row in rows]


def max_save_vote(class_name: str, user_id: str, student_name: str, status: str, vote_date: str = None):
    vote_date = vote_date or date.today().strftime('%Y-%m-%d')
    with _max_connection() as conn:
        conn.execute('''
            INSERT INTO max_votes (vote_date, class_name, user_id, student_name, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(vote_date, class_name, user_id) DO UPDATE SET
                student_name = excluded.student_name,
                status = excluded.status
        ''', (vote_date, class_name, str(user_id), student_name, status))


def max_get_class_votes(class_name: str, vote_date: str = None):
    vote_date = vote_date or date.today().strftime('%Y-%m-%d')
    with _max_connection() as conn:
        rows = conn.execute('''
            SELECT user_id, student_name, status FROM max_votes
            WHERE vote_date = ? AND class_name = ? ORDER BY student_name
        ''', (vote_date, class_name)).fetchall()
        return [{'user_id': row[0], 'student_name': row[1], 'status': row[2]} for row in rows]


def max_clear_old_votes(keep_date: str = None):
    keep_date = keep_date or date.today().strftime('%Y-%m-%d')
    with _max_connection() as conn:
        conn.execute('DELETE FROM max_votes WHERE vote_date < ?', (keep_date,))


def save_vote(class_name: str, user_id: str, student_name: str, status: str, vote_date: str = None):
    """
    Сохранение или обновление голоса ученика

    Args:
        class_name: Название класса (например, "7А")
        user_id: Telegram ID пользователя
        student_name: Фамилия и имя ученика
        status: Статус питания ("платно", "бесплатно", "не обедает")
        vote_date: Дата голосования (по умолчанию сегодня)
    """
    if vote_date is None:
        vote_date = date.today().strftime("%Y-%m-%d")

    conn = get_db_connection()
    cursor = conn.cursor()

    # REPLACE автоматически обновляет запись при совпадении PRIMARY KEY
    cursor.execute('''
        REPLACE INTO votes (date, class_name, user_id, student_name, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (vote_date, class_name, user_id, student_name, status))

    conn.commit()
    conn.close()


def get_class_votes(class_name: str, vote_date: str = None) -> List[Dict]:
    """
    Получение всех голосов класса за указанную дату

    Args:
        class_name: Название класса
        vote_date: Дата (по умолчанию сегодня)

    Returns:
        Список словарей с данными учеников
    """
    if vote_date is None:
        vote_date = date.today().strftime("%Y-%m-%d")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT user_id, student_name, status
        FROM votes
        WHERE date = ? AND class_name = ?
        ORDER BY student_name
    ''', (vote_date, class_name))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            'user_id': row[0],
            'student_name': row[1],
            'status': row[2]
        }
        for row in rows
    ]




def register_teacher(class_name: str, teacher_tg_id: str, teacher_name: str = None, group_chat_id: str = None):
    """
    Регистрация учителя для класса

    Args:
        class_name: Название класса (например, "7А")
        teacher_tg_id: Telegram ID учителя
        teacher_name: ФИ учителя (опционально)
        group_chat_id: ID группы класса в Telegram (опционально)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        REPLACE INTO teacher_classes (class_name, teacher_tg_id, teacher_name, group_chat_id)
        VALUES (?, ?, ?, ?)
    ''', (class_name, teacher_tg_id, teacher_name, group_chat_id))

    conn.commit()
    conn.close()


def get_teacher_by_class(class_name: str) -> Dict:
    """
    Получение данных учителя по названию класса

    Args:
        class_name: Название класса

    Returns:
        Словарь с данными учителя или None
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT teacher_tg_id, teacher_name, group_chat_id, class_name
        FROM teacher_classes
        WHERE class_name = ?
    ''', (class_name,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'teacher_tg_id': row[0],
            'teacher_name': row[1],
            'group_chat_id': row[2],
            'class_name': row[3]
        }
    return None


def get_teacher_classes(teacher_tg_id: str) -> List[str]:
    """
    Получение всех классов учителя

    Args:
        teacher_tg_id: Telegram ID учителя

    Returns:
        Список названий классов
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT class_name
        FROM teacher_classes
        WHERE teacher_tg_id = ?
    ''', (teacher_tg_id,))

    rows = cursor.fetchall()
    conn.close()

    return [row[0] for row in rows]


def update_group_chat_id(class_name: str, group_chat_id: str):
    """
    Обновление ID группы класса

    Args:
        class_name: Название класса
        group_chat_id: ID группы в Telegram
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE teacher_classes
        SET group_chat_id = ?
        WHERE class_name = ?
    ''', (group_chat_id, class_name))

    conn.commit()
    conn.close()


def init_group(chat_id: str, group_name: str, class_name: str):
    """
    Инициализация группы при добавлении туда бота

    Args:
        chat_id: ID группы в Telegram
        group_name: Название группы
        class_name: Название класса (определено из названия группы)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Таблица групп
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            chat_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            class_name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        REPLACE INTO groups (chat_id, group_name, class_name)
        VALUES (?, ?, ?)
    ''', (str(chat_id), group_name, class_name))

    conn.commit()
    conn.close()


def get_class_by_chat(chat_id: str) -> str:
    """
    Получение названия класса по ID группы

    Args:
        chat_id: ID группы в Telegram

    Returns:
        Название класса или None
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT class_name FROM groups WHERE chat_id = ?
    ''', (str(chat_id),))

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def save_student(user_id: str, first_name: str, last_name: str, class_name: str = None):
    """
    Сохранение информации об ученике

    Args:
        user_id: Telegram ID
        first_name: Имя
        last_name: Фамилия
        class_name: Класс (опционально)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Таблица студентов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            user_id TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            class_name TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        REPLACE INTO students (user_id, first_name, last_name, class_name)
        VALUES (?, ?, ?, ?)
    ''', (str(user_id), first_name, last_name, class_name))

    conn.commit()
    conn.close()


def get_all_groups() -> List[Dict]:
    """
    Получение всех групп, в которых есть бот

    Returns:
        Список словарей с данными групп
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT chat_id, group_name, class_name
        FROM groups
        ORDER BY class_name
    ''')

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            'chat_id': row[0],
            'group_name': row[1],
            'class_name': row[2]
        }
        for row in rows
    ]


def get_all_students_in_class(class_name: str) -> List[Dict]:
    """
    Получение всех студентов класса

    Args:
        class_name: Название класса

    Returns:
        Список словарей с данными студентов
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT user_id, first_name, last_name
        FROM students
        WHERE class_name = ?
        ORDER BY last_name, first_name
    ''', (class_name,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            'user_id': row[0],
            'first_name': row[1],
            'last_name': row[2]
        }
        for row in rows
    ]


def is_user_teacher(user_tg_id: str) -> bool:
    """
    Проверка, является ли пользователь зарегистрированным учителем

    Args:
        user_tg_id: Telegram ID пользователя

    Returns:
        True если пользователь является учителем
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COUNT(*) FROM teacher_classes
        WHERE teacher_tg_id = ?
    ''', (user_tg_id,))

    count = cursor.fetchone()[0]
    conn.close()

    return count > 0


def get_teacher_classes(user_tg_id: str) -> List[str]:
    """
    Получение списка классов, закрепленных за учителем

    Args:
        user_tg_id: Telegram/VK ID пользователя

    Returns:
        Список названий классов
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT class_name FROM teacher_classes
        WHERE teacher_tg_id = ?
        ORDER BY class_name
    ''', (user_tg_id,))

    rows = cursor.fetchall()
    conn.close()

    return [row[0] for row in rows]

