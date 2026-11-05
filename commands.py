"""
COMMANDS.PY — КОМАНДЫ И МЕНЮ РП-БОТА
=====================================
Красивое инлайн-меню с кнопками.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_ID, ADMIN_USERNAME
import database as db


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
        "║   🤖  **SWITAI — РП-БОТ**    ║\n"
        "╚══════════════════════════════╝\n\n"
        "📌 **Основные команды:**\n"
        "├ `#тег факт` — добавить факт в базу\n"
        "├ `Свит, что там у...` — задать вопрос\n"
        "└ `/verdict текст год` — получить вердикт\n\n"
        "🛠 **Админ-панель:**\n"
        "└ Жми кнопки ниже 👇\n\n"
        "──────────────────────────────\n"
        "💡 _Разработчик: @cakemogus_"
    )


def text_help():
    return (
        "╔══════════════════════════════╗\n"
        "║      📖  **ПОМОЩЬ**         ║\n"
        "╚══════════════════════════════╝\n\n"
        "🔹 **Сбор фактов:**\n"
        "Пиши в чате с ботом или в специальном чате:\n"
        "`#россия ВВП 250 млрд (2002)`\n"
        "→ Бот запомнит факт про Россию за 2002 год.\n\n"
        "🔹 **Вопросы:**\n"
        "`Свит, расскажи про Россию`\n"
        "→ Бот найдёт все факты по тегу и ответит.\n"
        "→ Если фактов нет — поищет в интернете.\n\n"
        "🔹 **Вердикты:**\n"
        "`/verdict Ввести санкции против США 2008`\n"
        "или ответь на сообщение командой `/verdict 2008`\n"
        "→ Бот выдаст: оценку, риски, предложения.\n"
        "→ Вердикт сохранится и будет учтён в будущем.\n\n"
        "──────────────────────────────\n"
        "💡 _Совет: указывай год в (скобках) — бот поймёт._"
    )


def text_stats():
    stats = db.get_stats()
    return (
        "╔══════════════════════════════╗\n"
        "║     📊  **СТАТИСТИКА**      ║\n"
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
            "║       🏷  **ТЕГИ**          ║\n"
            "╚══════════════════════════════╝\n\n"
            "📭 База пуста. Добавь первый факт:\n"
            "`#россия ВВП 250 млрд`"
        )
    
    lines = [
        "╔══════════════════════════════╗",
        "║       🏷  **ТЕГИ**          ║",
        "╚══════════════════════════════╝",
        ""
    ]
    for t in tags[:30]:  # максимум 30 тегов
        lines.append(f"▪️ **#{t['tag']}** — {t['cnt']} фактов ({t['verdicts']} вердиктов)")
    
    if len(tags) > 30:
        lines.append(f"\n…и ещё {len(tags) - 30} тегов.")
    
    lines.append("──────────────────────────────")
    return "\n".join(lines)


# =====================================================================
# КОМАНДЫ
# =====================================================================

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню."""
    if not is_admin(update.message.from_user.id, update.message.from_user.username):
        await update.message.reply_text("❌ Команда только для админа.")
        return
    await update.message.reply_text(
        text_main(),
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь — доступна всем."""
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
    """Реагирует на нажатия кнопок в меню."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or ""
    
    if not is_admin(user_id, username):
        await query.edit_message_text("❌ Доступ отозван.")
        return
    
    data = query.data
    
    if data == "menu_main":
        await query.edit_message_text(
            text_main(),
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_stats":
        await query.edit_message_text(
            text_stats(),
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_tags":
        await query.edit_message_text(
            text_tags(),
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_help":
        await query.edit_message_text(
            text_help(),
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_clear_history":
        db.clear_history(update.effective_chat.id, user_id)
        await query.edit_message_text(
            "🧹 *История диалога очищена.*\n\nВернись в меню или продолжай работу.",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_clear_facts":
        # Требуем подтверждение — опасная операция!
        await query.edit_message_text(
            "⚠️ *ВНИМАНИЕ!*\n\n"
            "Ты собираешься удалить **ВСЕ** факты и вердикты из базы.\n"
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
