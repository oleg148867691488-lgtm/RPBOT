import re
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID, saved_chats, save_saved_chats
from history import save_country, save_year, get_country, get_year
from news import generate_news, send_news_to_chat

# === ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ ДЛЯ ОСТАНОВКИ ===
bot_stopped = False

# === /START ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🇨🇭 *РП-бот запущен!*\n\n"
        "📌 Команды:\n"
        "/country [страна] — выбрать страну\n"
        "/year [год] — установить год\n"
        "/news [текст] — выпустить новость (только для админа)\n"
        "/savechatnews — сохранить этот чат для новостей\n"
        "/savechatwar — сохранить этот чат для войны\n"
        "/savechatoon — сохранить этот чат для ООН\n"
        "/stop — остановить бота\n"
        "/start_bot — запустить бота"
    )

# === /COUNTRY ===
async def country_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите страну. Пример: /country Россия")
        return

    country = " ".join(args)
    save_country(user_id, country)
    await update.message.reply_text(f"✅ Страна изменена на: *{country}*")

# === /YEAR ===
async def year_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите год. Пример: /year 2022")
        return

    try:
        year = int(args[0])
        save_year(user_id, year)
        await update.message.reply_text(f"✅ Год изменён на: *{year}*")
    except ValueError:
        await update.message.reply_text("❌ Введите число. Пример: /year 2022")

# === /SAVECHATNEWS ===
async def savechatnews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    saved_chats["news"] = update.message.chat.id
    save_saved_chats(saved_chats)
    await update.message.reply_text("📰 Новостной канал сохранён.")

# === /SAVECHATWAR ===
async def savechatwar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    saved_chats["war"] = update.message.chat.id
    save_saved_chats(saved_chats)
    await update.message.reply_text("⚔️ Военный кабинет сохранён.")

# === /SAVECHATOON ===
async def savechatoon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    saved_chats["un"] = update.message.chat.id
    save_saved_chats(saved_chats)
    await update.message.reply_text("🏛️ Кабинет ООН сохранён.")

# === /NEWS (РУЧНОЙ ВЫПУСК) ===
async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        # Если текста нет — генерируем новость автоматически
        news = await generate_news()
        await send_news_to_chat(context, news)
        await update.message.reply_text("✅ Новость сгенерирована и отправлена в новостной канал.")
        return

    # Если текст есть — отправляем его как новость
    text = " ".join(args)
    await send_news_to_chat(context, text)
    await update.message.reply_text("✅ Новость отправлена в новостной канал.")

# === /STOP ===
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещ.")
        return

    bot_stopped = True
    await update.message.reply_text("🛑 Бот остановлен. Все команды, кроме /start_bot, игнорируются.")

# === /START_BOT ===
async def start_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещ.")
        return

    bot_stopped = False
    await update.message.reply_text("✅ Бот возобновил работу.")
