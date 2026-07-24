import asyncio
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

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

logging.basicConfig(level=logging.INFO)

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

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === ЗАПУСК ===
if __name__ == "__main__":
    # Запускаем планировщик ПОСЛЕ того, как цикл запущен
    async def main():
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            generate_news_task,
            trigger=IntervalTrigger(minutes=NEWS_INTERVAL_MINUTES)
        )
        scheduler.start()
        
        print("✅ РП-бот запущен!")
        await app.run_polling()
    
    asyncio.run(main())
