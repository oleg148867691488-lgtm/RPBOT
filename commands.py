"""
COMMANDS.PY — КОМАНДЫ И МЕНЮ РП-БОТА
=====================================
/menu, /help, /stats, /tags, /savechat, /year, /clear_history, /clear_facts
+ инлайн-кнопки для навигации.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_ID, ADMIN_USERNAME, FACTS_CHAT_ID
import database as db


# =====================================================================
# ПРОВЕРКА АДМИНА
# =====================================================================

def is_admin(user_id: int, username: str) -> bool:
    if user_id == ADMIN_ID:
        return True
    if username and ADMIN_USERNAME and username.lower() == ADMIN_USERNAME.lower():
        return True
    return False


# =====================================================================
# КЛАВИАТУРЫ
# =====================================================================

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
            InlineKeyboardButton("🏷 Теги", callback_data="menu_tags"),
        ],
        [
            InlineKeyboardButton("💾 Сохранить этот чат", callback_data="menu_savechat"),
            InlineKeyboardButton("📍 Где храним факты?", callback_data="menu_wheresave"),
        ],
        [
            InlineKeyboardButton("📅 Время РП", callback_data="menu_year"),
        ],
        [
            InlineKeyboardButton("🧹 Очистить историю", callback_data="menu_clear_history"),
            InlineKeyboardButton("🗑 Очистить базу", callback_data="menu_clear_facts"),
        ],
        [
            InlineKeyboardButton("❓ Помощь", callback_data="menu_help"),
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="menu_main")]
    ])


# =====================================================================
# ТЕКСТЫ ЭКРАНОВ
# =====================================================================

def text_main():
    return (
        "╔══════════════════════════════╗\n"
        "║   🤖  **RP BOT AI**          ║\n"
        "╚══════════════════════════════╝\n\n"
        "📌 **Основные команды:**\n"
        "├ `#тег факт` — добавить факт в базу\n"
        "├ `@RPAIBOTIK_BOT, что там у...` — задать вопрос\n"
        "└ `/verdict текст год` — получить вердикт\n\n"
        "🛠 **Админ-панель:**\n"
        "└ Жми кнопки ниже 👇\n\n"
        "──────────────────────────────\n"
        "💡 _Разработчик: @cakemogus_"
    )


def text_help():
    return (
        "╔══════════════════════════════╗\n"
        "║      📖  **ПОМОЩЬ**          ║\n"
        "╚══════════════════════════════╝\n\n"
        "🔹 **Сбор фактов:**\n"
        "Пиши в чате, сохранённом через `/savechat`:\n"
        "`#россия ВВП 250 млрд (2002)`\n"
        "→ Бот запомнит факт про Россию за 2002 год.\n\n"
        "🔹 **Вопросы:**\n"
        "`@RPAIBOTIK_BOT, расскажи про Россию`\n"
        "→ В чате фактов можно писать просто: `расскажи про Россию`\n"
        "→ Бот найдёт все факты по тегу и ответит.\n\n"
        "🔹 **Вердикты:**\n"
        "`/verdict Ввести санкции против США 2008`\n"
        "или ответь на сообщение командой `/verdict 2008`\n"
        "→ Бот выдаст: оценку, риски, предложения.\n\n"
        "🔹 **Сохранение чата:**\n"
        "`/savechat` — сделать этот чат хранилищем фактов.\n\n"
        "🔹 **Время РП:**\n"
        "`/year 2010` — установить стартовый год РП.\n"
        "→ Дальше время идёт автоматически: 1 реальный час ≈ 15 дней РП.\n"
        "`/year` — показать текущую дату в РП.\n\n"
        "──────────────────────────────\n"
        "💡 _Совет: указывай год в (скобках) — бот поймёт._"
    )


def text_stats():
    stats = db.get_stats()
    return (
        "╔══════════════════════════════╗\n"
        "║     📊  **СТАТИСТИКА**       ║\n"
        "╚══════════════════════════════╝\n\n"
        f"📚 Всего фактов: **{stats['total']}**\n"
        f"⚖️ Вердиктов: **{stats['verdicts']}**\n"
        f"🏷 Уникальных тегов: **{stats['tags']}**\n\n"
        "──────────────────────────────"
    )


def text_tags():
    tags = db.get_all_tags()
    if not tags:
        return (
            "╔══════════════════════════════╗\n"
            "║       🏷  **ТЕГИ**           ║\n"
            "╚══════════════════════════════╝\n\n"
            "📭 База пуста. Добавь первый факт:\n"
            "`#россия ВВП 250 млрд`"
        )
    
    lines = [
        "╔══════════════════════════════╗",
        "║       🏷  **ТЕГИ**           ║",
        "╚══════════════════════════════╝",
        ""
    ]
    for t in tags[:30]:
        lines.append(f"▪️ **#{t['tag']}** — {t['cnt']} фактов ({t['verdicts']} вердиктов)")
    
    if len(tags) > 30:
        lines.append(f"\n…и ещё {len(tags) - 30} тегов.")
    
    lines.append("──────────────────────────────")
    return "\n".join(lines)


def text_where_save():
    saved = db.get_setting("facts_chat_id")
    if saved:
        return (
            "╔══════════════════════════════╗\n"
            "║    📍 **ЧАТ ДЛЯ ФАКТОВ**     ║\n"
            "╚══════════════════════════════╝\n\n"
            f"Текущий чат для сбора фактов:\n"
            f"`{saved}`\n\n"
            "Если хочешь сменить — напиши `/savechat` в нужном чате."
        )
    elif FACTS_CHAT_ID:
        return (
            "╔══════════════════════════════╗\n"
            "║    📍 **ЧАТ ДЛЯ ФАКТОВ**     ║\n"
            "╚══════════════════════════════╝\n\n"
            f"Используется fallback из ENV:\n"
            f"`{FACTS_CHAT_ID}`\n\n"
            "Напиши `/savechat` в нужном чате, чтобы зафиксировать явно."
        )
    else:
        return (
            "╔══════════════════════════════╗\n"
            "║    📍 **ЧАТ ДЛЯ ФАКТОВ**     ║\n"
            "╚══════════════════════════════╝\n\n"
            "⚠️ Чат ещё не сохранён!\n\n"
            "Напиши `/savechat` в чате, где хочешь собирать факты."
        )


def text_year():
    from handlers import get_rp_datetime
    rp = get_rp_datetime()
    if rp["year"]:
        return (
            "╔══════════════════════════════╗\n"
            "║      📅 **ВРЕМЯ РП**         ║\n"
            "╚══════════════════════════════╝\n\n"
            f"📆 Дата: **{rp['full']}** (МСК)\n"
            f"🕐 Час: {rp['hour']}:00\n\n"
            "⚡ Скорость: 1 реальный час ≈ 15 дней РП.\n"
            "Дата обновляется автоматически.\n\n"
            "Сменить стартовый год: `/year 2010`"
        )
    else:
        return (
            "╔══════════════════════════════╗\n"
            "║      📅 **ВРЕМЯ РП**         ║\n"
            "╚══════════════════════════════╝\n\n"
            "⚠️ Год РП не установлен.\n\n"
            "Напиши `/year 2010`, чтобы запустить симуляцию времени."
        )


# =====================================================================
# КОМАНДЫ
# =====================================================================

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username):
        await update.message.reply_text("❌ Команда только для админа.")
        return
    await update.message.reply_text(
        text_main(),
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(text_help(), parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username):
        await update.message.reply_text("❌ Команда только для админа.")
        return
    await update.message.reply_text(text_stats(), parse_mode="Markdown")


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username):
        await update.message.reply_text("❌ Команда только для админа.")
        return
    await update.message.reply_text(text_tags(), parse_mode="Markdown")


async def savechat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username):
        await update.message.reply_text("❌ Команда только для админа.")
        return
    
    chat_id = update.message.chat.id
    chat_title = update.message.chat.title or "Личка"
    
    db.set_setting("facts_chat_id", str(chat_id))
    
    await update.message.reply_text(
        "╔══════════════════════════════╗\n"
        "║   ✅ **ЧАТ СОХРАНЁН**        ║\n"
        "╚══════════════════════════════╝\n\n"
        f"📌 Чат: **{chat_title}**\n"
        f"🆔 ID: `{chat_id}`\n\n"
        "Теперь бот будет собирать факты с `#тег` **только в этом чате**.",
        parse_mode="Markdown"
    )


async def year_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers import get_rp_datetime
    import time
    
    if not is_admin(update.message.from_user.id, update.message.from_user.username):
        await update.message.reply_text("❌ Только админ может менять год.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(text_year(), parse_mode="Markdown")
        return

    try:
        year = int(args[0])
        if year < 1900 or year > 2100:
            await update.message.reply_text("❌ Год должен быть от 1900 до 2100.")
            return
    except ValueError:
        await update.message.reply_text("❌ Укажи год числом. Пример: `/year 2010`", parse_mode="Markdown")
        return

    db.set_setting("rp_year", str(year))
    db.set_setting("rp_start_time", str(time.time()))

    await update.message.reply_text(
        f"📅 **Год РП установлен на {year}.**\n\n"
        f"🕐 Старт: сейчас (МСК).\n"
        f"⚡ Скорость: 1 реальный час ≈ 15 дней РП.\n\n"
        f"Дата будет меняться автоматически.\n"
        f"Проверить текущую дату: `/year`",
        parse_mode="Markdown"
    )


async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username):
        await update.message.reply_text("❌ Команда только для админа.")
        return
    db.clear_history(update.message.chat.id, update.message.from_user.id)
    await update.message.reply_text("🧹 *История диалога очищена.*", parse_mode="Markdown")


async def clear_facts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id, update.message.from_user.username):
        await update.message.reply_text("❌ Команда только для админа.")
        return
    db.clear_all_facts()
    await update.message.reply_text("🗑 *База фактов полностью очищена.*", parse_mode="Markdown")


# =====================================================================
# ОБРАБОТЧИК ИНЛАЙН-КНОПОК
# =====================================================================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or ""
    
    if not is_admin(user_id, username):
        await query.edit_message_text("❌ Доступ отозван.")
        return
    
    data = query.data
    
    if data == "menu_main":
        await query.edit_message_text(text_main(), reply_markup=main_menu_keyboard(), parse_mode="Markdown")
    elif data == "menu_stats":
        await query.edit_message_text(text_stats(), reply_markup=back_keyboard(), parse_mode="Markdown")
    elif data == "menu_tags":
        await query.edit_message_text(text_tags(), reply_markup=back_keyboard(), parse_mode="Markdown")
    elif data == "menu_help":
        await query.edit_message_text(text_help(), reply_markup=back_keyboard(), parse_mode="Markdown")
    elif data == "menu_wheresave":
        await query.edit_message_text(text_where_save(), reply_markup=back_keyboard(), parse_mode="Markdown")
    elif data == "menu_year":
        await query.edit_message_text(text_year(), reply_markup=back_keyboard(), parse_mode="Markdown")
    elif data == "menu_savechat":
        chat_id = query.message.chat.id
        chat_title = query.message.chat.title or "Личка"
        db.set_setting("facts_chat_id", str(chat_id))
        await query.edit_message_text(
            "╔══════════════════════════════╗\n"
            "║   ✅ **ЧАТ СОХРАНЁН**        ║\n"
            "╚══════════════════════════════╝\n\n"
            f"📌 Чат: **{chat_title}**\n"
            f"🆔 ID: `{chat_id}`\n\n"
            "Теперь факты с `#тег` собираются **только здесь**.",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_clear_history":
        db.clear_history(query.message.chat.id, user_id)
        await query.edit_message_text(
            "🧹 *История диалога очищена.*\n\nВернись в меню или продолжай.",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_clear_facts":
        await query.edit_message_text(
            "⚠️ *ВНИМАНИЕ!*\n\n"
            "Ты собираешься удалить **ВСЕ** факты и вердикты.\n"
            "Это действие необратимо.\n\n"
            "Точно уверен?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, удалить", callback_data="menu_clear_facts_confirm")],
                [InlineKeyboardButton("⬅️ Отмена", callback_data="menu_main")],
            ]),
            parse_mode="Markdown"
        )
    elif data == "menu_clear_facts_confirm":
        db.clear_all_facts()
        await query.edit_message_text(
            "🗑 *База фактов полностью очищена.*",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
