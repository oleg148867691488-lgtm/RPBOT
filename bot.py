"""
RP BOT — АВТОНОМНАЯ СТРАНА С ИИ
=================================
Iron Man режим. Бот сам управляет страной.
Игроки могут влиять через чаты и команды.
"""

import asyncio
import logging
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

# =====================================================================
# КОНФИГУРАЦИЯ
# =====================================================================
from config import (
    BOT_TOKEN,
    NEWS_INTERVAL_MINUTES,
    DECISION_INTERVAL_MINUTES,
    ADMIN_ID,
    ADMIN_USERNAME,
    saved_chats,
    bot_stopped
)

# =====================================================================
# ИМПОРТ КОМАНД
# =====================================================================
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
    wipe_command,
    research_command,
    status_command,
)

# =====================================================================
# ИМПОРТ ОБРАБОТЧИКОВ
# =====================================================================
from handlers import handle_message

# =====================================================================
# ИМПОРТ МОДУЛЕЙ
# =====================================================================
from news import generate_news_task
from decision_engine import decision_loop, init_world
from history import init_db

# =====================================================================
# НАСТРОЙКА ЛОГГИРОВАНИЯ
# =====================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =====================================================================
# ДИСКЛЕЙМЕР
# =====================================================================
DISCLAIMER = """
⚠️ *ДИСКЛЕЙМЕР*

Этот бот — игровая историческая симуляция (RP).
Все персонажи, события, войны, санкции и действия 
являются ВЫМЫШЛЕННЫМИ и происходят в рамках игры.

Любые совпадения с реальными событиями случайны.
Насилие, война и дипломатия — часть игровой механики, 
а не призыв к действиям в реальной жизни.

Бот управляется ИИ в режиме Iron Man.
Стратегия адаптируется под выбранную страну.
"""

# =====================================================================
# СОЗДАНИЕ ПРИЛОЖЕНИЯ
# =====================================================================
app = Application.builder().token(BOT_TOKEN).build()

# =====================================================================
# РЕГИСТРАЦИЯ КОМАНД
# =====================================================================

# Основные
app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("country", country_command))
app.add_handler(CommandHandler("year", year_command))
app.add_handler(CommandHandler("news", news_command))
app.add_handler(CommandHandler("research", research_command))
app.add_handler(CommandHandler("status", status_command))

# Чаты
app.add_handler(CommandHandler("savechatnews", savechatnews_command))
app.add_handler(CommandHandler("savechatwar", savechatwar_command))
app.add_handler(CommandHandler("savechatoon", savechatoon_command))

# Управление ботом
app.add_handler(CommandHandler("stop", stop_command))
app.add_handler(CommandHandler("start_bot", start_bot_command))
app.add_handler(CommandHandler("wipe", wipe_command))

# Экономика
from economy import (
    balance_command,
    trade_command,
    trade_with_player,
    add_money_command,
    economy_stats
)
app.add_handler(CommandHandler("balance", balance_command))
app.add_handler(CommandHandler("trade", trade_command))
app.add_handler(CommandHandler("tradeplayer", trade_with_player))
app.add_handler(CommandHandler("addmoney", add_money_command))
app.add_handler(CommandHandler("economy", economy_stats))

# Война
from war import (
    declare_war_command,
    respond_command,
    strategy_command,
    war_status_command,
    peace_command
)
app.add_handler(CommandHandler("war", declare_war_command))
app.add_handler(CommandHandler("respond", respond_command))
app.add_handler(CommandHandler("strategy", strategy_command))
app.add_handler(CommandHandler("war_status", war_status_command))
app.add_handler(CommandHandler("peace", peace_command))

# Дипломатия
from diplomacy import (
    un_propose_command,
    vote_command,
    ally_command,
    accept_ally_command,
    sanctions_command,
    remove_sanctions_command,
    diplomacy_status_command
)
app.add_handler(CommandHandler("un_propose", un_propose_command))
app.add_handler(CommandHandler("vote", vote_command))
app.add_handler(CommandHandler("ally", ally_command))
app.add_handler(CommandHandler("accept_ally", accept_ally_command))
app.add_handler(CommandHandler("sanctions", sanctions_command))
app.add_handler(CommandHandler("remove_sanctions", remove_sanctions_command))
app.add_handler(CommandHandler("diplomacy", diplomacy_status_command))

# =====================================================================
# ОБРАБОТЧИК СООБЩЕНИЙ (ВСЕ ТЕКСТОВЫЕ)
# =====================================================================
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# =====================================================================
# ОБРАБОТЧИК ОШИБОК
# =====================================================================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логирование ошибок"""
    logger.error(f"Ошибка при обработке {update}: {context.error}")
    
    if update and update.message:
        await update.message.reply_text(
            "❌ Произошла внутренняя ошибка. Админ уже уведомлён."
        )

app.add_error_handler(error_handler)

# =====================================================================
# ФУНКЦИЯ СТАРТА
# =====================================================================
async def on_startup():
    """Действия при запуске бота"""
    logger.info("🚀 Запуск RP-бота...")
    
    # Инициализация базы данных
    init_db()
    logger.info("✅ База данных инициализирована")
    
    # Инициализация мира (исследование страны)
    try:
        await init_world()
        logger.info("✅ Мир инициализирован")
    except Exception as e:
        logger.warning(f"⚠️ Мир инициализирован с базовыми настройками: {e}")
    
    # Запуск планировщика
    scheduler = AsyncIOScheduler()
    
    # Новости каждые NEWS_INTERVAL_MINUTES минут
    scheduler.add_job(
        lambda: asyncio.create_task(generate_news_task(app)),
        trigger=IntervalTrigger(minutes=NEWS_INTERVAL_MINUTES),
        id="news_job",
        replace_existing=True
    )
    
    # Decision Engine каждые DECISION_INTERVAL_MINUTES минут
    scheduler.add_job(
        lambda: asyncio.create_task(decision_loop(app)),
        trigger=IntervalTrigger(minutes=DECISION_INTERVAL_MINUTES),
        id="decision_job",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info(f"✅ Планировщик запущен (новости: {NEWS_INTERVAL_MINUTES}мин, решения: {DECISION_INTERVAL_MINUTES}мин)")
    
    # Уведомление админу
    try:
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "✅ *RP-бот запущен!*\n\n"
                f"🌍 Страна: определяется\n"
                f"📰 Новости каждые: {NEWS_INTERVAL_MINUTES} мин\n"
                f"🧠 Решения каждые: {DECISION_INTERVAL_MINUTES} мин\n"
                f"🎮 Режим: Iron Man\n\n"
                "Команды:\n"
                "/country [страна] — выбрать страну\n"
                "/year [год] — установить год\n"
                "/status — статус бота"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление админу: {e}")
    
    logger.info("✅ RP-бот полностью запущен!")

# =====================================================================
# ТОЧКА ВХОДА
# =====================================================================
if __name__ == "__main__":
    # Устанавливаем политику событийного цикла для Windows
    if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Запускаем бота
    logger.info("🤖 Загрузка RP-бота...")
    app.run_polling(
        on_startup=lambda: asyncio.create_task(on_startup()),
        drop_pending_updates=True  # Не обрабатываем старые сообщения
    )
