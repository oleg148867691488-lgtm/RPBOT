import asyncio
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# === НАШИ МОДУЛИ ===
from config import BOT_TOKEN, NEWS_INTERVAL_MINUTES, bot_stopped
from commands import (
    start_command,
    country_command,
    year_command,
    savechatnews_command,
    savechatwar_command,
    savechatoon_command,
    stop_command,
    start_bot_command,
    news_command
)
from handlers import handle_message
from news import generate_news_task

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(level=logging.INFO)

# === СОЗДАЁМ ПРИЛОЖЕНИЕ ===
app = Application.builder().token(BOT_TOKEN).build()

# === КОМАНДЫ ===
app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("country", country_command))
app.add_handler(CommandHandler("year", year_command))
app.add_handler(CommandHandler("savechatnews", savechatnews_command))
app.add_handler(CommandHandler("savechatwar", savechatwar_command))
app.add_handler(CommandHandler("savechatoon", savechatoon_command))
app.add_handler(CommandHandler("stop", stop_command))
app.add_handler(CommandHandler("start_bot", start_bot_command))
app.add_handler(CommandHandler("news", news_command))

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === ПЛАНИРОВЩИК НОВОСТЕЙ ===
scheduler = AsyncIOScheduler()
scheduler.add_job(
    generate_news_task,
    trigger=IntervalTrigger(minutes=NEWS_INTERVAL_MINUTES)
)
scheduler.start()

# === ЗАПУСК ===
if __name__ == "__main__":
    print("✅ РП-бот запущен!")
    app.run_polling()
