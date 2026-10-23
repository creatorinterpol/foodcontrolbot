"""Telegram бот для теста CockroachDB"""
import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv(override=True)

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from database import init_database, max_save_vote, max_get_class_votes

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
PROXY_URL = os.getenv('HTTPS_PROXY', 'http://127.0.0.1:10809')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тест БД"""
    try:
        init_database()
        await update.message.reply_text("✅ Таблицы созданы")

        max_save_vote('7А', str(update.effective_user.id), update.effective_user.first_name, 'платно')
        await update.message.reply_text("✅ Голос сохранён")

        votes = max_get_class_votes('7А')
        msg = f"✅ Найдено голосов: {len(votes)}\n"
        for v in votes:
            name = v['student_name'] if isinstance(v, dict) else v[1]
            status = v['status'] if isinstance(v, dict) else v[2]
            msg += f"- {name}: {status}\n"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

def main():
    request = HTTPXRequest(proxy=PROXY_URL) if PROXY_URL else None
    builder = Application.builder().token(TOKEN)
    if request:
        builder = builder.request(request)
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
