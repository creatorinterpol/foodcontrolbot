# Подготовка к Amvera

## 1. Переменные окружения (.env на Amvera)

```
# Telegram
TELEGRAM_BOT_TOKEN=ваш_токен_тг

# Database (CockroachDB на Amvera)
DATABASE_TYPE=cockroach
DATABASE_URL=postgresql://user:password@amvera-host:26257/school_db?sslmode=require

# Пути
REPORTS_DIR=/tmp/reports

# Коды доступа
ACCESS_CODE_TEACHER=1234
ACCESS_CODE_ZAVHOZ=5678

# Telegram - для bot.py
TELEGRAM_BOT_TOKEN=ваш_токен_тг_бота
```

## 2. Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

## 3. requirements.txt

```
pyTelegramBotAPI==4.14.0
psycopg2-binary==2.9.9
python-dotenv==1.0.0
pandas==2.0.0
openpyxl==3.1.0
APScheduler==3.10.4
requests==2.31.0
```

## 4. Шаги на Amvera

1. Создать проект
2. Связать репо (GitHub/GitLab)
3. Добавить переменные окружения (из пункта 1)
4. Развернуть контейнер

## Для MAX бота - аналогично, но с MAX_BOT_TOKEN
