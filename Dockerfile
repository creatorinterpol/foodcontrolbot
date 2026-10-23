FROM python:3.11-slim

WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Проверка что файлы на месте
RUN ls -la /app/*.py | head -5

# Запуск бота
CMD ["python", "bot.py"]
