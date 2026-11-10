"""
BOT.PY — ТОЧКА ВХОДА РП-БОТА
=====================================
Запуск бота + Flask для health check на Render.
Регистрация всех команд + автоматическое обновление кэша админов групп.
"""

import logging
import os
from threading import Thread
from flask import Flask

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, TypeHandler, filters, ContextTypes
)

from config import BOT_TOKEN
from handlers import handle_message, verdict_command, ensure_chat_admins
from commands import (
    menu_command, help_command, stats_command, tags_command,
    savechat_command, saveworld_command, year_command,
    info_command, top_command, bulk_command, bulkworld_command,
    clear_history_command, clear_facts_command,
    menu_callback,
)

# =====================================================================
# ЛОГИРОВАНИЕ
# =====================================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# =====================================================================
# FLASK ДЛЯ HEALTH CHECK
# =====================================================================
app_web = Flask(__name__)


@app_web.route("/")
@app_web.route("/health")
def health_check():
    return "✅ FactBot жив и здоров!", 200


def run_web():
    port = int(os.environ.get("PORT", "10000"))
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app_web.run(host="0.0.0.0", port=port)


# =====================================================================
# ОБРАБОТЧИК ОШИБОК
# =====================================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)


# =====================================================================
# ГЛОБАЛЬНЫЙ ОБНОВИТЕЛЬ КЭША АДМИНОВ
# =====================================================================
async def update_admins_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """При любом апдейте в группе — проверяет/обновляет кэш админов."""
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        await ensure_chat_admins(update.effective_chat.id, context)


# =====================================================================
# ЗАПУСК
# =====================================================================
def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не задан в переменных окружения!")
        return

    # Flask в отдельном потоке
    thread = Thread(target=run_web)
    thread.daemon = True
    thread.start()
    logger.info(f"✅ Flask запущен на порту {os.environ.get('PORT', '10000')}")

    # Telegram-бот
    app = Application.builder().token(BOT_TOKEN).build()

    # === ГЛОБАЛЬНЫЙ ОБНОВИТЕЛЬ АДМИНОВ (group=-1, до всех остальных) ===
    app.add_handler(TypeHandler(Update, update_admins_handler), group=-1)

    # --- Админские / владельческие команды ---
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("savechat", savechat_command))
    app.add_handler(CommandHandler("saveworld", saveworld_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("tags", tags_command))
    app.add_handler(CommandHandler("year", year_command))
    app.add_handler(CommandHandler("clear_history", clear_history_command))
    app.add_handler(CommandHandler("clear_facts", clear_facts_command))

    # --- Массовый импорт (админ/владелец) ---
    app.add_handler(CommandHandler("bulk", bulk_command))
    app.add_handler(CommandHandler("bulkworld", bulkworld_command))

    # --- Публичные ---
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("top", top_command))

    # --- Вердикты (для всех, с лимитами) ---
    app.add_handler(CommandHandler("verdict", verdict_command))

    # --- Обычные сообщения (вопросы + #теги) ---
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

    # --- Кнопки инлайн-меню ---
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu_"))

    # --- Обработчик ошибок ---
    app.add_error_handler(error_handler)

    logger.info("✅ FactBot запущен. Слушаю сообщения...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
