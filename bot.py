"""
BOT.PY — RP БОТ ДЛЯ RENDER (ФИНАЛ)
=====================================
Автономная страна с ИИ (Iron Man режим).
python-telegram-bot v22 + Python 3.14.
"""

import asyncio
import logging
import os
import sys
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

from config import (
    BOT_TOKEN,
    NEWS_INTERVAL_MINUTES,
    DECISION_INTERVAL_MINUTES,
    ADMIN_ID,
    saved_chats,
    bot_stopped
)

from commands import (
    start_command,
    tension_command,
    country_command,
    year_command,
    research_command,
    status_command,
    savechatnews_command,
    savechatwar_command,
    savechatoon_command,
    stop_command,
    start_bot_command,
    wipe_command,
    admin_help_command,
    force_news_command,
    force_decision_command,
    force_war_command,
    force_peace_command,
    force_trade_command,
    force_ally_command,
    force_sanctions_command,
    add_money_command,
    set_power_command,
    debug_ai_command,
    debug_world_command,
)

from handlers import handle_message
from news import generate_news_task
from decision_engine import decision_loop, init_world, world
from history import init_db, get_country

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Application.builder().token(BOT_TOKEN).build()

# Публичные
app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("tension", tension_command))

# Админские основные
app.add_handler(CommandHandler("country", country_command))
app.add_handler(CommandHandler("year", year_command))
app.add_handler(CommandHandler("research", research_command))
app.add_handler(CommandHandler("status", status_command))
app.add_handler(CommandHandler("savechatnews", savechatnews_command))
app.add_handler(CommandHandler("savechatwar", savechatwar_command))
app.add_handler(CommandHandler("savechatoon", savechatoon_command))
app.add_handler(CommandHandler("stop", stop_command))
app.add_handler(CommandHandler("start_bot", start_bot_command))
app.add_handler(CommandHandler("wipe", wipe_command))

# Админские тестовые
app.add_handler(CommandHandler("admin", admin_help_command))
app.add_handler(CommandHandler("force_news", force_news_command))
app.add_handler(CommandHandler("force_decision", force_decision_command))
app.add_handler(CommandHandler("force_war", force_war_command))
app.add_handler(CommandHandler("force_peace", force_peace_command))
app.add_handler(CommandHandler("force_trade", force_trade_command))
app.add_handler(CommandHandler("force_ally", force_ally_command))
app.add_handler(CommandHandler("force_sanctions", force_sanctions_command))
app.add_handler(CommandHandler("addmoney", add_money_command))
app.add_handler(CommandHandler("setpower", set_power_command))
app.add_handler(CommandHandler("debug_ai", debug_ai_command))
app.add_handler(CommandHandler("debug_world", debug_world_command))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.message:
        try:
            if update.message.from_user.id == ADMIN_ID:
                await update.message.reply_text(f"❌ Ошибка:\n```\n{str(context.error)[:500]}\n```", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Внутренняя ошибка.")
        except:
            pass

app.add_error_handler(error_handler)

async def on_startup():
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК RP-БОТА")
    logger.info("=" * 50)
    
    try:
        init_db()
        logger.info("✅ База данных")
    except Exception as e:
        logger.error(f"❌ БД: {e}")
    
    try:
        await init_world()
        logger.info("✅ Мир инициализирован")
    except Exception as e:
        logger.warning(f"⚠️ Мир: {e}")
    
    try:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            lambda: asyncio.create_task(generate_news_task(app)),
            trigger=IntervalTrigger(minutes=NEWS_INTERVAL_MINUTES),
            id="news_job", replace_existing=True
        )
        scheduler.add_job(
            lambda: asyncio.create_task(decision_loop(app)),
            trigger=IntervalTrigger(minutes=DECISION_INTERVAL_MINUTES),
            id="decision_job", replace_existing=True
        )
        scheduler.start()
        logger.info(f"✅ Планировщик")
    except Exception as e:
        logger.error(f"❌ Планировщик: {e}")
    
    try:
        country = get_country(ADMIN_ID) or "не выбрана"
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ Бот запущен!\n🌍 Страна: {country}\n/admin — команды"
        )
    except Exception as e:
        logger.warning(f"⚠️ Уведомление: {e}")
    
    logger.info("✅ БОТ ЗАПУЩЕН")

# =====================================================================
# ЗАПУСК
# =====================================================================
if __name__ == "__main__":
    app.post_init = on_startup
    
    port = int(os.environ.get("PORT", "8080"))
    webhook_url = os.environ.get("WEBHOOK_URL", None)
    
    if webhook_url:
        logger.info(f"🔗 Вебхук: {webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
            drop_pending_updates=True
        )
    else:
        logger.info("🔄 Поллинг")
        app.run_polling(drop_pending_updates=True)
