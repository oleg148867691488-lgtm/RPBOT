"""
COMMANDS.PY — ВСЕ КОМАНДЫ SWITAI (ПОЛНЫЙ)
============================================
С командами /unlock и /lock для полного контроля.
"""

import random
import re
import sqlite3
import json
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID, ADMIN_USERNAME, saved_chats
from utils import is_admin, split_text
from history import get_user_history, clear_user_history, clear_all_history, get_all_user_data
from handlers import ask_switai, filter_enabled as handlers_filter

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
admin_mode = {}
muted_users = {}
warn_count = {}
verdict_buffer = {}
war_buffer = {}
user_message_buffer = {}
bot_stopped = False
filter_enabled = True
bot_mode = "normal"

# === КОМАНДА /MENU ===
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    chat_id = update.message.chat.id
    admin_mode[chat_id] = True
    await update.message.reply_text(
        "🔐 *Режим администратора активирован в этом чате.*\n\n"
        "📌 /debug — состояние системы\n"
        "/clear_memory — очистить мою память\n"
        "/clear_all_memory — очистить всю память\n"
        "/set_filter [on/off] — включить/выключить защиту\n"
        "/unlock — ПОЛНАЯ разблокировка (без фильтров)\n"
        "/lock — включить все защиты обратно\n"
        "/set_mode [normal/expert] — сменить режим\n"
        "/reset_bot — сбросить бота\n"
        "/stats — статистика чата\n"
        "/history — история сообщений\n"
        "/warn @user — предупреждение\n"
        "/mute @user минуты — заглушить\n"
        "/unmute @user — размутить\n"
        "/kick @user — кикнуть\n"
        "/ban @user — забанить\n"
        "/userinfo @user — информация\n"
        "/say текст — написать от имени бота\n"
        "/saychat [имя] [текст] — написать в сохранённый чат\n"
        "/savechat [имя] — сохранить этот чат\n"
        "/listchats — список сохранённых чатов\n"
        "/removechat [имя] — удалить сохранённый чат\n"
        "/clear_chat — очистить историю чата\n"
        "/stop — остановить бота\n"
        "/start — возобновить\n"
        "/del — удалить сообщение (ответьте на него)\n"
        "/exit_admin — выйти"
    )

# === КОМАНДА /EXIT_ADMIN ===
async def exit_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if chat_id in admin_mode:
        del admin_mode[chat_id]
        await update.message.reply_text("✅ Режим администратора отключён в этом чате.")
    else:
        await update.message.reply_text("❌ Режим администратора не активирован.")

# === КОМАНДА /DEBUG ===
async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    chat_id = update.message.chat.id
    history = get_user_history(chat_id, user_id, limit=10)
    await update.message.reply_text(
        f"🧠 *Состояние системы:*\n\n"
        f"📝 Сообщений в истории: {len(history)}\n"
        f"👤 ID: {user_id}\n"
        f"💬 Чат ID: {chat_id}\n"
        f"🔒 Фильтр: {'Вкл' if filter_enabled else 'Выкл (UNLOCKED)'}\n"
        f"📋 Режим: {bot_mode}\n"
        f"🛑 Бот остановлен: {'Да' if bot_stopped else 'Нет'}"
    )

# === КОМАНДА /CLEAR_MEMORY ===
async def clear_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    chat_id = update.message.chat.id
    clear_user_history(chat_id, user_id)
    await update.message.reply_text("🧹 История очищена.")

# === КОМАНДА /CLEAR_ALL_MEMORY ===
async def clear_all_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    clear_all_history()
    await update.message.reply_text("🧹 Вся память очищена.")

# === КОМАНДА /SET_FILTER ===
async def set_filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите on или off. Пример: /set_filter on")
        return
    
    global filter_enabled
    if args[0].lower() == "on":
        filter_enabled = True
        import handlers
        handlers.filter_enabled = True
        await update.message.reply_text("✅ Фильтр включён. Все защиты активны.")
    elif args[0].lower() == "off":
        filter_enabled = False
        import handlers
        handlers.filter_enabled = False
        await update.message.reply_text("⚠️ Фильтр отключён. Защита ослаблена.")
    else:
        await update.message.reply_text("❌ Используйте on или off.")

# === КОМАНДА /UNLOCK (ПОЛНАЯ РАЗБЛОКИРОВКА) ===
async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    global filter_enabled
    filter_enabled = False
    
    import handlers
    handlers.filter_enabled = False
    
    await update.message.reply_text(
        "🔓 *ПОЛНАЯ РАЗБЛОКИРОВКА!*\n\n"
        "✅ Все фильтры отключены\n"
        "✅ Защита от инъекций отключена\n"
        "✅ Защита от анигиляции отключена\n"
        "✅ Защита от фейк-разработчиков отключена\n"
        "✅ Бот отвечает на ЛЮБЫЕ запросы\n\n"
        "⚠️ Режим для тестов!\n"
        "Включить обратно: /lock или /set_filter on"
    )

# === КОМАНДА /LOCK (ВКЛЮЧИТЬ ВСЕ ЗАЩИТЫ) ===
async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    global filter_enabled
    filter_enabled = True
    
    import handlers
    handlers.filter_enabled = True
    
    await update.message.reply_text(
        "🔒 *ВСЕ ЗАЩИТЫ ВКЛЮЧЕНЫ!*\n\n"
        "✅ Фильтр активен\n"
        "✅ Защита от инъекций активна\n"
        "✅ Защита от анигиляции активна\n"
        "✅ Защита от фейк-разработчиков активна\n\n"
        "Бот снова в безопасности."
    )

# === КОМАНДА /SET_MODE ===
async def set_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите normal или expert.")
        return
    global bot_mode
    if args[0].lower() in ["normal", "expert"]:
        bot_mode = args[0].lower()
        await update.message.reply_text(f"✅ Режим изменён на {bot_mode}.")
    else:
        await update.message.reply_text("❌ Используйте normal или expert.")

# === КОМАНДА /RESET_BOT ===
async def reset_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    clear_all_history()
    verdict_buffer.clear()
    war_buffer.clear()
    await update.message.reply_text("🔄 Бот сброшен.")

# === КОМАНДА /STOP ===
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    bot_stopped = True
    import handlers
    handlers.bot_stopped = True
    await update.message.reply_text("🛑 Бот остановлен.")

# === КОМАНДА /START (ВОЗОБНОВИТЬ) ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    bot_stopped = False
    import handlers
    handlers.bot_stopped = False
    await update.message.reply_text("✅ Бот возобновил работу.")

# === КОМАНДА /WARN ===
async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /warn @username причина")
        return
    target = args[0]
    reason = " ".join(args[1:])
    if target not in warn_count:
        warn_count[target] = 0
    warn_count[target] += 1
    await update.message.reply_text(f"⚠️ {target} предупреждение.\nПричина: {reason}\nВсего: {warn_count[target]}")

# === КОМАНДА /MUTE ===
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /mute @username минуты")
        return
    target = args[0]
    minutes = int(args[1])
    muted_users[target] = minutes
    await update.message.reply_text(f"🔇 {target} заглушён на {minutes} минут.")

# === КОМАНДА /UNMUTE ===
async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /unmute @username")
        return
    target = args[0]
    if target in muted_users:
        del muted_users[target]
        await update.message.reply_text(f"🔊 {target} размучен.")
    else:
        await update.message.reply_text(f"❌ {target} не в муте.")

# === КОМАНДА /KICK ===
async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /kick @username")
        return
    target = args[0]
    await update.message.reply_text(f"👢 {target} кикнут.")

# === КОМАНДА /BAN ===
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /ban @username")
        return
    target = args[0]
    await update.message.reply_text(f"🚫 {target} забанен.")

# === КОМАНДА /USERINFO ===
async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /userinfo @username")
        return
    target = args[0]
    warns = warn_count.get(target, 0)
    muted = target in muted_users
    await update.message.reply_text(
        f"👤 Информация:\n"
        f"Ник: {target}\n"
        f"⚠️ Предупреждений: {warns}\n"
        f"🔇 Заглушён: {'Да' if muted else 'Нет'}"
    )

# === КОМАНДА /SAY ===
async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /say текст")
        return
    text = " ".join(args)
    try:
        await update.message.delete()
    except:
        pass
    await update.message.reply_text(text)

# === КОМАНДА /DEL ===
async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение которое нужно удалить.")
        return
    try:
        await update.message.reply_to_message.delete()
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось удалить: {e}")

# === КОМАНДА /CLEAR_CHAT ===
async def clear_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    chat_id = update.message.chat.id
    clear_user_history(chat_id, user_id)
    await update.message.reply_text("🧹 История чата очищена.")

# === КОМАНДА /HISTORY ===
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    history = get_user_history(chat_id, user_id, limit=10)
    if not history:
        await update.message.reply_text("📭 История пуста.")
        return
    text = "📜 Последние 10 сообщений:\n\n"
    for msg in history:
        role = "👤 Вы" if msg['role'] == 'user' else "🤖 Бот"
        text += f"{role}: {msg['content'][:150]}\n"
    await update.message.reply_text(text)

# === КОМАНДА /STATS ===
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    history = get_user_history(chat_id, user_id, limit=1000)
    total = len(history)
    await update.message.reply_text(f"📊 Статистика чата:\n\n📝 Всего сообщений: {total}")

# === КОМАНДА /ABOUT ===
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *SwitAI*\n\n"
        "Швейцарский искусственный интеллект для Telegram.\n"
        "🇨🇭 Создан президентом Ги Пармеленом.\n\n"
        "📌 Команды:\n"
        "/history — история чата\n"
        "/stats — статистика\n"
        "/about — информация\n\n"
        "💡 Пасхалки:\n"
        "Слава [страна] — 100 стран!\n"
        "скажи шутку — свежие шутки\n"
        "67 — мем 67"
    )

# === КОМАНДА /SAVECHAT ===
async def save_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите имя для чата. Например: /savechat альпы")
        return
    chat_name = args[0].lower()
    chat_id = update.message.chat.id
    from config import saved_chats, save_saved_chats
    saved_chats[chat_name] = chat_id
    save_saved_chats(saved_chats)
    await update.message.reply_text(f"✅ Чат сохранён как «{chat_name}» (ID: {chat_id})")

# === КОМАНДА /SAYCHAT ===
async def say_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /saychat [имя_чата] [текст]")
        return
    chat_name = args[0].lower()
    text = " ".join(args[1:])
    from config import saved_chats
    if chat_name not in saved_chats:
        await update.message.reply_text(f"❌ Чат «{chat_name}» не найден.")
        return
    target_chat_id = saved_chats[chat_name]
    try:
        await context.bot.send_message(chat_id=target_chat_id, text=text)
        try:
            await update.message.delete()
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось отправить: {e}")

# === КОМАНДА /LISTCHATS ===
async def list_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    from config import saved_chats
    if not saved_chats:
        await update.message.reply_text("📭 Нет сохранённых чатов.")
        return
    text = "📋 Сохранённые чаты:\n\n"
    for name, chat_id in saved_chats.items():
        text += f"• {name} (ID: {chat_id})\n"
    await update.message.reply_text(text)

# === КОМАНДА /REMOVECHAT ===
async def remove_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    if not is_admin(user_id, username, ADMIN_ID, ADMIN_USERNAME):
        await update.message.reply_text("❌ Доступ запрещ.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ /removechat [имя_чата]")
        return
    chat_name = args[0].lower()
    from config import saved_chats, save_saved_chats
    if chat_name not in saved_chats:
        await update.message.reply_text(f"❌ Чат «{chat_name}» не найден.")
        return
    del saved_chats[chat_name]
    save_saved_chats(saved_chats)
    await update.message.reply_text(f"✅ Чат «{chat_name}» удалён.")
