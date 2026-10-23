"""
Конфигурация бота для автоматизации школьной столовой
"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Загружаем .env принудительно перезаписывая переменные терминала
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# Секреты передаются только через переменные окружения.
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# MAX Bot API
MAX_BOT_TOKEN = os.getenv('MAX_BOT_TOKEN')
MAX_API_BASE_URL = 'https://platform-api2.max.ru'
MAX_WEBHOOK_URL = os.getenv('MAX_WEBHOOK_URL', '')
MAX_WEBHOOK_SECRET = os.getenv('MAX_WEBHOOK_SECRET', '')
MAX_WEBHOOK_HOST = os.getenv('MAX_WEBHOOK_HOST', '0.0.0.0')
MAX_WEBHOOK_PORT = int(os.getenv('MAX_WEBHOOK_PORT', '8080'))
MAX_MENU_TIME = os.getenv('MAX_MENU_TIME', '08:00')
MAX_REPORT_TIME = os.getenv('MAX_REPORT_TIME', '14:00')
MAX_TIMEZONE = os.getenv('MAX_TIMEZONE', 'Europe/Moscow')
MAX_ADMIN_IDS = os.getenv('MAX_ADMIN_IDS', '')

# Получить токен: https://vk.com/dev
VK_TOKEN = os.getenv('VK_BOT_TOKEN', 'YOUR_VK_TOKEN_HERE')
VK_GROUP_ID = os.getenv('VK_GROUP_ID', 'YOUR_GROUP_ID')  # ID группы ВК (числовой)

# ID администратора бота (для доступа к команде /report)
# Узнать свой ID можно через @userinfobot
ADMIN_IDS = [8848536754]  # Список Telegram ID администраторов

# Коды доступа для ролей
ACCESS_CODE_TEACHER = os.getenv('ACCESS_CODE_TEACHER', '1234')  # Код для учителей
ACCESS_CODE_ZAVHOZ = os.getenv('ACCESS_CODE_ZAVHOZ', '5678')    # Код для завхоза

# Название класса по умолчанию (можно расширить для мультиклассовости)
DEFAULT_CLASS = "7А"

# Настройки расписания (время в формате HH:MM)
SCHEDULE_MENU_TIME = "14:00"      # Время отправки меню днем
SCHEDULE_REPORT_TIME = "20:00"    # Время отправки отчета вечером

# Часовой пояс (для корректной работы планировщика)
TIMEZONE = "Europe/Moscow"

# Путь к базе данных
DATABASE_PATH = os.getenv('DATABASE_PATH', os.path.join(BASE_DIR, 'school_canteen.db'))

# CockroachDB
DATABASE_TYPE = os.getenv('DATABASE_TYPE', 'sqlite')
DATABASE_URL = os.getenv('DATABASE_URL', '')

# Путь для сохранения отчетов
REPORTS_DIR = os.getenv('REPORTS_DIR', os.path.join(BASE_DIR, 'reports'))

# Путь к папке с картинками меню (2-недельное меню)
MENU_IMAGES_DIR = "menu_images"

# Настройки прокси для VPN
# Если HappVPN или другой VPN не работает автоматически, раскомментируйте и установите:
# Примеры:
# PROXY_URL = 'socks5://127.0.0.1:1080'      # Для SOCKS5 прокси
# PROXY_URL = 'http://127.0.0.1:8080'        # Для HTTP прокси
# PROXY_URL = 'https://127.0.0.1:8443'       # Для HTTPS прокси
PROXY_URL = os.getenv('HTTPS_PROXY') or os.getenv('HTTP_PROXY') or None
