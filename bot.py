import os
import asyncio
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# === НАСТРОЙКИ ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 7184396483

# === ХРАНИЛИЩА ===
saved_chats = {
    "news": None,   # Новостной канал
    "war": None,    # Военный кабинет
    "un": None,     # Кабинет ООН
}

current_country = None   # Текущая страна бота
current_year = 2022      # Текущий год

# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🇨🇭 *РП-бот запущен!*\n\n"
        "📌 Команды:\n"
        "/country [страна] — выбрать страну\n"
        "/year [год] — установить год\n"
        "/savechatnews — сохранить этот чат для новостей\n"
        "/savechatwar — сохранить этот чат для войны\n"
        "/savechatoon — сохранить этот чат для ООН\n"
        "/stop — остановить бота\n"
        "/start — запустить бота"
    )

async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите страну. Пример: /country Россия")
        return

    global current_country
    current_country = " ".join(args)
    await update.message.reply_text(f"✅ Страна изменена на: *{current_country}*")

async def year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите год. Пример: /year 2022")
        return

    global current_year
    current_year = int(args[0])
    await update.message.reply_text(f"✅ Год изменён на: *{current_year}*")

async def savechatnews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    saved_chats["news"] = update.message.chat.id
    await update.message.reply_text("📰 Новостной канал сохранён.")

async def savechatwar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    saved_chats["war"] = update.message.chat.id
    await update.message.reply_text("⚔️ Военный кабинет сохранён.")

async def savechatoon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    saved_chats["un"] = update.message.chat.id
    await update.message.reply_text("🏛️ Кабинет ООН сохранён.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    # Останавливаем планировщик
    scheduler.pause()
    await update.message.reply_text("🛑 Бот остановлен. Все команды, кроме /start, игнорируются.")

async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    # Запускаем планировщик
    scheduler.resume()
    await update.message.reply_text("✅ Бот возобновил работу.")

# === ГЕНЕРАЦИЯ НОВОСТЕЙ ===
async def generate_news():
    if not current_country:
        return "❌ Страна не выбрана. Используйте /country"

    # TODO: Здесь будет генерация новости через Groq
    return f"📰 *{current_country}* — новость за {current_year} год."

async def news_scheduler():
    chat_id = saved_chats.get("news")
    if chat_id:
        news = await generate_news()
        await app.bot.send_message(chat_id=chat_id, text=news)

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    text = update.message.text

    # Определяем тип чата
    if chat_id == saved_chats.get("news"):
        chat_type = "news"
    elif chat_id == saved_chats.get("war"):
        chat_type = "war"
    elif chat_id == saved_chats.get("un"):
        chat_type = "un"
    else:
        chat_type = "default"

    # Если это новостной чат — бот может комментировать
    if chat_type == "news" and "#" in text:
        await update.message.reply_text(f"📰 *Комментарий от {current_country}:*\n\nЯ прочитал эту новость. Интересно...")

# === ЗАПУСК ===
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("country", country))
    app.add_handler(CommandHandler("year", year))
    app.add_handler(CommandHandler("savechatnews", savechatnews))
    app.add_handler(CommandHandler("savechatwar", savechatwar))
    app.add_handler(CommandHandler("savechatoon", savechatoon))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("start_bot", start_bot))

    # Обработчик сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Планировщик новостей (4 раза в 2 часа = каждые 30 минут)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(news_scheduler, trigger=IntervalTrigger(minutes=30))
    scheduler.start()

    print("✅ РП-бот запущен!")
    app.run_polling()
