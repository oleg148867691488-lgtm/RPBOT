import asyncio
import logging
import sys
import os
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# === НАШИ МОДУЛИ ===
from config import BOT_TOKEN, NEWS_INTERVAL_MINUTES
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
from decision_engine import decision_loop
from history import init_db

# === НАСТРОЙКА ЛОГГИРОВАНИЯ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === СОЗДАНИЕ ПРИЛОЖЕНИЯ ===
app = Application.builder().token(BOT_TOKEN).build()

# === КОМАНДЫ ===
app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("country", country_command))
app.add_handler(CommandHandler("year", year_command))
app.add_handler(CommandHandler("news", news_command))
app.add_handler(CommandHandler("savechatnews", savechatnews_command))
app.add_handler(CommandHandler("savechatwar", savechatwar_command))
app.add_handler(CommandHandler("savechatoon", savechatoon_command))
app.add_handler(CommandHandler("stop", stop_command))
app.add_handler(CommandHandler("start_bot", start_bot_command))

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === ЗАПУСК ===
if __name__ == "__main__":
    # Инициализация базы данных
    init_db()
    logger.info("✅ База данных инициализирована")
    
    # Запуск планировщика
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        generate_news_task,
        trigger=IntervalTrigger(minutes=NEWS_INTERVAL_MINUTES)
    )
    scheduler.add_job(
        decision_loop,
        trigger=IntervalTrigger(minutes=10)
    )
    scheduler.start()
    logger.info("✅ Планировщик запущен")
    
    # Запуск бота
    logger.info("✅ РП-бот запущен!")
    app.run_polling()
