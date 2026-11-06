
"""
BOT.PY — ТОЧКА ВХОДА РП-БОТА
=====================================
Запуск бота + Flask для health check на Render.
"""

import logging
import os
from threading import Thread
from flask import Flask

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

from config import BOT_TOKEN
from handlers import handle_message, verdict_command
from commands import (
    menu_command, help_command, stats_command, tags_command,
    savechat_command, year_command,
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

    # --- Админские команды ---
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("savechat", savechat_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("tags", tags_command))
    app.add_handler(CommandHandler("year", year_command))
    app.add_handler(CommandHandler("clear_history", clear_history_command))
    app.add_handler(CommandHandler("clear_facts", clear_facts_command))

    # --- Публичные ---
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("start", help_command))

    # --- Вердикты (доступны всем, с лимитами) ---
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
