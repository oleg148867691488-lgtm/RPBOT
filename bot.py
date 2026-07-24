import asyncio
import logging
import sys
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# === НАШИ МОДУЛИ ===
from config import (
    BOT_TOKEN,
    ADMIN_ID,
    ADMIN_USERNAME,
    NEWS_INTERVAL_MINUTES,
    GROQ_API_KEY,
    GROQ_URL
)
from commands import (
    start_command,
    country_command,
    year_command,
    savechatnews_command,
    savechatwar_command,
    savechatoon_command,
    stop_command,
    start_bot_command,
    news_command,
    help_command,
    menu_command
)
from handlers import handle_message
from news import generate_news_task, generate_news, send_news_to_chat
from economy import balance_command, trade_command, trade_with_player, economy_stats, add_money_command
from war import (
    declare_war_command,
    respond_command,
    strategy_command,
    war_status_command,
    peace_command,
    active_wars
)
from diplomacy import (
    un_propose_command,
    vote_command,
    ally_command,
    accept_ally_command,
    sanctions_command,
    remove_sanctions_command,
    diplomacy_status_command
)
from history import init_db, get_country, get_year, get_economy
from decision_engine import decision_loop
from utils import is_admin, log_message

# === НАСТРОЙКА ЛОГГИРОВАНИЯ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ===
bot_stopped = False
scheduler = None

# === ФУНКЦИЯ ЗАПУСКА ПЛАНИРОВЩИКА ===
def start_scheduler():
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
        # Новости каждые 30 минут
        scheduler.add_job(
            generate_news_task,
            trigger=IntervalTrigger(minutes=NEWS_INTERVAL_MINUTES)
        )
        # Decision Engine каждые 10 минут
        scheduler.add_job(
            decision_loop,
            trigger=IntervalTrigger(minutes=10)
        )
        scheduler.start()
        logger.info("✅ Планировщик запущен")
    return scheduler

# === ФУНКЦИЯ ОСТАНОВКИ ПЛАНИРОВЩИКА ===
def stop_scheduler():
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler = None
        logger.info("🛑 Планировщик остановлен")

# === СОЗДАНИЕ ПРИЛОЖЕНИЯ ===
app = Application.builder().token(BOT_TOKEN).build()

# === КОМАНДЫ ===
# Основные команды
app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("menu", menu_command))

# Админ-команды
app.add_handler(CommandHandler("country", country_command))
app.add_handler(CommandHandler("year", year_command))
app.add_handler(CommandHandler("news", news_command))
app.add_handler(CommandHandler("savechatnews", savechatnews_command))
app.add_handler(CommandHandler("savechatwar", savechatwar_command))
app.add_handler(CommandHandler("savechatoon", savechatoon_command))
app.add_handler(CommandHandler("stop", stop_command))
app.add_handler(CommandHandler("start_bot", start_bot_command))

# Экономика
app.add_handler(CommandHandler("balance", balance_command))
app.add_handler(CommandHandler("trade", trade_command))
app.add_handler(CommandHandler("tradeplayer", trade_with_player))
app.add_handler(CommandHandler("economy_stats", economy_stats))
app.add_handler(CommandHandler("addmoney", add_money_command))

# Война
app.add_handler(CommandHandler("war", declare_war_command))
app.add_handler(CommandHandler("respond", respond_command))
app.add_handler(CommandHandler("strategy", strategy_command))
app.add_handler(CommandHandler("war_status", war_status_command))
app.add_handler(CommandHandler("peace", peace_command))

# Дипломатия
app.add_handler(CommandHandler("un_propose", un_propose_command))
app.add_handler(CommandHandler("vote", vote_command))
app.add_handler(CommandHandler("ally", ally_command))
app.add_handler(CommandHandler("accept_ally", accept_ally_command))
app.add_handler(CommandHandler("sanctions", sanctions_command))
app.add_handler(CommandHandler("remove_sanctions", remove_sanctions_command))
app.add_handler(CommandHandler("diplomacy_status", diplomacy_status_command))

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === ЗАПУСК ===
if __name__ == "__main__":
    try:
        # Инициализация базы данных
        init_db()
        logger.info("✅ База данных инициализирована")
        
        # Запуск планировщика
        start_scheduler()
        
        # Запуск бота
        logger.info("✅ РП-бот запущен!")
        app.run_polling()
        
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен вручную")
        stop_scheduler()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        stop_scheduler()
    finally:
        logger.info("🛑 Бот завершил работу")
