"""
COMMANDS.PY — КОМАНДЫ И МЕНЮ РП-БОТА
=====================================
/menu, /help, /stats, /tags, /savechat, /saveworld, /info,
/year, /bulk, /bulkworld, /clear_history, /clear_facts
+ инлайн-кнопки.
"""

import os
import re
import json
import time
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import (
    ADMIN_ID, ADMIN_USERNAME, FACTS_CHAT_ID,
    RP_OWNER_ID, RP_OWNER_USERNAME,
    GROQ_URL, GROQ_KEY_MAIN, MODEL_MAIN,
    OLLAMA_KEY, OLLAMA_URL,
    GEMINI_KEY,
)
import database as db


# =====================================================================
# ПРОВЕРКА ПРАВ
# =====================================================================

def is_admin(user_id: int, username: str, chat_id: int = None) -> bool:
    if user_id == ADMIN_ID:
        return True
    if RP_OWNER_ID and user_id == RP_OWNER_ID:
        return True
    if username and ADMIN_USERNAME and username.lower() == ADMIN_USERNAME.lower():
        return True
    saved = db.get_setting("saved_admin_ids")
    if saved:
        try:
            ids = json.loads(saved)
            if user_id in ids:
                return True
        except Exception:
            pass
    if chat_id:
        from handlers import is_chat_admin
        if is_chat_admin(chat_id, user_id):
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
            InlineKeyboardButton("💾 Чат фактов", callback_data="menu_savechat"),
            InlineKeyboardButton("🌍 Чат мировых", callback_data="menu_saveworld"),
        ],
        [
            InlineKeyboardButton("📍 Где храним?", callback_data="menu_wheresave"),
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
# ТЕКСТЫ
# =====================================================================

def text_main():
    return (
        "╔══════════════════════════════╗\n"
        "║   🤖  **RP BOT AI**          ║\n"
        "╚══════════════════════════════╝\n\n"
        "📌 **Основные команды:**\n"
        "├ `#тег факт` — добавить факт\n"
        "├ `@RPAIBOTIK_BOT, что там у...` — вопрос\n"
        "├ `/verdict текст [год]` — вердикт\n"
        "├ `/info страна` — сводка по стране\n"
        "└ `/bulk` — массовый импорт\n\n"
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
        "В чате, сохранённом через `/savechat`:\n"
        "`#россия ВВП 250 млрд (2002)`\n"
        "→ Бот запомнит. Если NRP — отметит владельца.\n\n"
        "🔹 **Мировые новости:**\n"
        "В чате `/saveworld`:\n"
        "`#НАТО начал распад (2010)`\n"
        "→ Сохранится как мировая. Учтётся в вердиктах.\n\n"
        "🔹 **Вопросы:**\n"
        "`@RPAIBOTIK_BOT, расскажи про Россию`\n"
        "→ В личке можно без @.\n\n"
        "🔹 **Вердикты:**\n"
        "`/verdict Ввести санкции против США 2008`\n"
        "→ Оценка, риски, предложения.\n"
        "→ Учитывает прошлые вердикты и мировые новости.\n"
        "→ Игроки: 25/день (30 сек), админы: 100/день (15 сек).\n\n"
        "🔹 **Массовый импорт:**\n"
        "`/bulk` реплаем на большое сообщение — разобьёт на факты.\n"
        "`/bulkworld` — то же для мировых.\n"
        "Кулдаун: 3 минуты.\n\n"
        "🔹 **Инфо о стране:**\n"
        "`/info Россия` — база → World Bank → интернет.\n\n"
        "🔹 **Чаты:**\n"
        "`/savechat` — чат фактов (запоминает админов).\n"
        "`/saveworld` — чат мировых новостей.\n\n"
        "🔹 **Время РП:**\n"
        "`/year 2010` — установить год.\n"
        "→ 2 реальных часа = 1 месяц РП.\n"
        "→ 24 реальных часа = 1 год РП.\n\n"
        "──────────────────────────────\n"
        "💡 _Год в (скобках) — бот поймёт._"
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
    world_count = 0
    for t in tags:
        if t['tag'].startswith("игрок_"):
            continue
        if t['tag'].startswith("world_"):
            world_count += 1
            continue
        lines.append(f"▪️ **#{t['tag']}** — {t['cnt']} фактов ({t['verdicts']} верд.)")
        if len(lines) > 32:
            break
    
    if world_count:
        lines.append(f"\n🌍 Мировых тегов: **{world_count}**")
    
    lines.append("──────────────────────────────")
    return "\n".join(lines)


def text_where_save():
    facts = db.get_setting("facts_chat_id")
    world = db.get_setting("world_chat_id")
    lines = [
        "╔══════════════════════════════╗",
        "║   📍 **ЧАТЫ ДЛЯ СБОРА**      ║",
        "╚══════════════════════════════╝",
        ""
    ]
    lines.append(f"📚 Факты: `{facts}`" if facts else "📚 Факты: ❌ не сохранён")
    lines.append(f"🌍 Мировые: `{world}`" if world else "🌍 Мировые: ❌ не сохранён")
    lines.append("")
    lines.append("Сменить: `/savechat` или `/saveworld`.")
    return "\n".join(lines)


def text_year():
    from handlers import get_rp_datetime
    rp = get_rp_datetime()
    if rp["year"]:
        return (
            "╔══════════════════════════════╗\n"
            "║      📅 **ВРЕМЯ РП**         ║\n"
            "╚══════════════════════════════╝\n\n"
            f"📆 **Дата в РП:** {rp['full']}\n"
            f"📅 Год: {rp['year']}\n\n"
            f"🕐 Реальное МСК: {rp['real_msk']}\n"
            f"⏱ Прошло (реал): {rp['elapsed_hours']:.2f} ч.\n"
            f"📊 Дней РП прошло: {rp['rp_days']:.1f}\n"
            f"🎯 До смены года: {rp['days_to_new_year']} дней РП\n\n"
            "⚡ 1 реальный час = ~15.2 дней РП.\n"
            "📅 2 реальных часа = 1 месяц РП.\n"
            "🎯 24 реальных часа = 1 год РП.\n\n"
            "Сменить год: `/year 2010`"
        )
    else:
        return (
            "╔══════════════════════════════╗\n"
            "║      📅 **ВРЕМЯ РП**         ║\n"
            "╚══════════════════════════════╝\n\n"
            "⚠️ Год РП не установлен.\n\n"
            "Напиши `/year 2010`, чтобы запустить."
        )


# =====================================================================
# КОМАНДЫ
# =====================================================================

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if not is_admin(update.message.from_user.id, update.message.from_user.username, chat_id):
        await update.message.reply_text("❌ Только для админа/владельца.")
        return
    await update.message.reply_text(
        text_main(),
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(text_help(), parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if not is_admin(update.message.from_user.id, update.message.from_user.username, chat_id):
        await update.message.reply_text("❌ Только для админа/владельца.")
        return
    await update.message.reply_text(text_stats(), parse_mode="Markdown")


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if not is_admin(update.message.from_user.id, update.message.from_user.username, chat_id):
        await update.message.reply_text("❌ Только для админа/владельца.")
        return
    await update.message.reply_text(text_tags(), parse_mode="Markdown")


async def _save_chat_admins(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    admin_ids = []
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for a in admins:
            if not a.user.is_bot:
                admin_ids.append(a.user.id)
    except Exception as e:
        print(f"⚠️ Не удалось получить админов группы: {e}")
    if admin_ids:
        db.set_setting("saved_admin_ids", json.dumps(admin_ids))
    return admin_ids


async def savechat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if not is_admin(update.message.from_user.id, update.message.from_user.username, chat_id):
        await update.message.reply_text("❌ Только для админа/владельца.")
        return
    
    chat_title = update.message.chat.title or "Личка"
    db.set_setting("facts_chat_id", str(chat_id))
    admins = await _save_chat_admins(chat_id, context)
    
    await update.message.reply_text(
        "╔══════════════════════════════╗\n"
        "║   ✅ **ЧАТ ФАКТОВ СОХРАНЁН** ║\n"
        "╚══════════════════════════════╝\n\n"
        f"📌 Чат: **{chat_title}**\n"
        f"🆔 ID: `{chat_id}`\n"
        f"👥 Админов запомнено: **{len(admins)}**\n\n"
        "Теперь факты с `#тег` собираются **только здесь**.",
        parse_mode="Markdown"
    )


async def saveworld_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if not is_admin(update.message.from_user.id, update.message.from_user.username, chat_id):
        await update.message.reply_text("❌ Только для админа/владельца.")
        return
    
    chat_title = update.message.chat.title or "Личка"
    db.set_setting("world_chat_id", str(chat_id))
    
    await update.message.reply_text(
        "╔══════════════════════════════╗\n"
        "║ 🌍 **ЧАТ МИРОВЫХ СОХРАНЁН**  ║\n"
        "╚══════════════════════════════╝\n\n"
        f"📌 Чат: **{chat_title}**\n"
        f"🆔 ID: `{chat_id}`\n\n"
        "Теперь мировые новости с `#тег` собираются **только здесь**.\n"
        "Бот учитывает их при вердиктах.",
        parse_mode="Markdown"
    )


async def year_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime
    chat_id = update.message.chat.id
    
    if not is_admin(update.message.from_user.id, update.message.from_user.username, chat_id):
        await update.message.reply_text("❌ Только админ/владелец может менять год.")
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

    try:
        import pytz
        now_msk = datetime.now(pytz.timezone("Europe/Moscow"))
    except ImportError:
        from datetime import timezone, timedelta
        now_msk = datetime.now(timezone(timedelta(hours=3)))

    db.set_setting("rp_year", str(year))
    db.set_setting("rp_start_time", str(time.time()))
    db.set_setting("rp_start_month", str(now_msk.month))
    db.set_setting("rp_start_day", str(now_msk.day))

    await update.message.reply_text(
        f"📅 **Год РП установлен на {year}.**\n\n"
        f"🕐 Старт: сейчас ({now_msk.day} числа, {now_msk.month} месяца, {year} год).\n"
        f"⚡ 1 реальный час = ~15.2 дней РП.\n"
        f"📅 2 реальных часа = 1 месяц РП.\n"
        f"🎯 24 реальных часа = 1 год РП.\n\n"
        f"Проверить: `/year`",
        parse_mode="Markdown"
    )


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers import call_groq, call_gemini, search_web, get_economic_context, get_rp_datetime, split_text
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Используй: `/info Россия`", parse_mode="Markdown")
        return
    
    country = " ".join(args).strip()
    await update.message.reply_text(f"⏳ Собираю информацию по **{country}**...", parse_mode="Markdown")
    
    all_tags = db.get_all_tags()
    country_lower = country.lower()
    relevant_facts = []
    for t in all_tags:
        if not t["tag"].startswith("world_") and country_lower in t["tag"]:
            relevant_facts.extend(db.get_facts_by_tag(t["tag"]))
    
    wb_context = await get_economic_context(f"ВВП {country}")
    
    rp = get_rp_datetime()
    year_line = f"Сейчас в РП: {rp['year']} год. " if rp["year"] else ""
    
    if relevant_facts:
        facts_str = "\n".join([
            f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f['year'] else "")
            for f in relevant_facts[:25]
        ])
        system_prompt = (
            f"Ты — аналитический РП-бот. {year_line}Составь сводку по стране **{country}** на основе фактов из базы.\n"
            "Структура: 1) Экономика (ВВП, бюджет). 2) Армия. 3) Политика. 4) Международное положение. 5) Ключевые события.\n"
            "Используй ТОЛЬКО предоставленные факты. НЕ ВЫДУМЫВАЙ числа. Если чего-то нет — пиши 'нет данных'.\n\n"
            f"ФАКТЫ ИЗ БАЗЫ:\n{facts_str}"
        )
        source = "база"
    else:
        web_result = await search_web(f"{country} экономика армия население ВВП 2010")
        if not web_result:
            await update.message.reply_text(
                f"❌ В базе нет данных по стране **{country}**, и поиск в интернете не дал результатов.\n\n"
                f"Добавь факты через `#{country_lower} ...`",
                parse_mode="Markdown"
            )
            return
        
        system_prompt = (
            f"Ты — аналитический РП-бот. {year_line}Составь сводку по стране **{country}** на основе результатов поиска.\n"
            "Структура: 1) Экономика (ВВП, население). 2) Армия. 3) Политика. 4) Международное положение.\n"
            "Помечай данные как '(из интернета)'.\n\n"
            f"РЕЗУЛЬТАТЫ ПОИСКА:\n{web_result}"
        )
        source = "интернет"
    
    if wb_context:
        system_prompt += f"\n\n{wb_context}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Дай сводку по стране {country}"}
    ]
    
    result = await call_groq(GROQ_KEY_MAIN, MODEL_MAIN, messages, temperature=0.5)
    if not result:
        result = await call_gemini(messages, temperature=0.5)
    if not result:
        await update.message.reply_text("❌ Не удалось получить ответ.")
        return
    
    header = f"🌍 **СВОДКА: {country.upper()}** _(источник: {source})_\n\n"
    full = header + result
    for part in split_text(full, max_length=4000):
        try:
            await update.message.reply_text(part, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(part)


async def _do_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE, is_world: bool = False):
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""

    if not is_admin(user_id, username, chat_id):
        await update.message.reply_text("❌ Только для админа/владельца.")
        return

    cooldown_key = f"bulk_cooldown_{user_id}"
    last = db.get_setting(cooldown_key, "0")
    try:
        if time.time() - float(last) < 180:
            await update.message.reply_text("⏳ Подожди 3 минуты между массовыми импортами.")
            return
    except Exception:
        pass

    text = ""
    if update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text
    else:
        raw = update.message.text or ""
        for cmd in ["/bulkworld", "/bulk"]:
            if raw.startswith(cmd):
                text = raw[len(cmd):].strip()
                break

    if not text:
        await update.message.reply_text(
            "❌ Использование:\n"
            "• Ответь (реплай) на сообщение командой `/bulk`\n"
            "• Или: `/bulk <текст>`\n"
            "• Для мировых: `/bulkworld`\n\n"
            "Бот разобьёт текст на факты через LLM.",
            parse_mode="Markdown"
        )
        return

    if len(text) < 50:
        await update.message.reply_text("❌ Слишком короткий текст (< 50 символов).")
        return

    await update.message.reply_text(
        f"⏳ Разбираю текст ({len(text)} символов) на факты...\n"
        f"Это займёт 10-20 секунд."
    )

    from handlers import bulk_import
    saved = await bulk_import(update, text, is_world=is_world)

    if saved == 0:
        await update.message.reply_text("❌ Не удалось разбить текст. Попробуй переформулировать.")
    else:
        kind = "мировых новостей" if is_world else "фактов"
        db.set_setting(cooldown_key, str(time.time()))
        await update.message.reply_text(
            f"✅ **Импортировано {saved} {kind}.**\n"
            f"Проверь `/tags` или `/stats`.",
            parse_mode="Markdown"
        )


async def bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _do_bulk(update, context, is_world=False)


async def bulkworld_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _do_bulk(update, context, is_world=True)


async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if not is_admin(update.message.from_user.id, update.message.from_user.username, chat_id):
        await update.message.reply_text("❌ Только для админа/владельца.")
        return
    db.clear_history(update.message.chat.id, update.message.from_user.id)
    await update.message.reply_text("🧹 *История диалога очищена.*", parse_mode="Markdown")


async def clear_facts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    if not is_admin(update.message.from_user.id, update.message.from_user.username, chat_id):
        await update.message.reply_text("❌ Только для админа/владельца.")
        return
    db.clear_all_facts()
    await update.message.reply_text("🗑 *База фактов полностью очищена.*", parse_mode="Markdown")


# =====================================================================
# ИНЛАЙН-КНОПКИ
# =====================================================================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or ""
    chat_id = query.message.chat.id
    
    if not is_admin(user_id, username, chat_id):
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
        chat_title = query.message.chat.title or "Личка"
        db.set_setting("facts_chat_id", str(chat_id))
        admins = await _save_chat_admins(chat_id, context)
        await query.edit_message_text(
            "╔══════════════════════════════╗\n"
            "║   ✅ **ЧАТ ФАКТОВ СОХРАНЁН** ║\n"
            "╚══════════════════════════════╝\n\n"
            f"📌 Чат: **{chat_title}**\n"
            f"🆔 ID: `{chat_id}`\n"
            f"👥 Админов: **{len(admins)}**\n\n"
            "Факты с `#тег` — только здесь.",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_saveworld":
        chat_title = query.message.chat.title or "Личка"
        db.set_setting("world_chat_id", str(chat_id))
        await query.edit_message_text(
            "╔══════════════════════════════╗\n"
            "║ 🌍 **ЧАТ МИРОВЫХ СОХРАНЁН**  ║\n"
            "╚══════════════════════════════╝\n\n"
            f"📌 Чат: **{chat_title}**\n"
            f"🆔 ID: `{chat_id}`\n\n"
            "Мировые с `#тег` — только здесь.",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_clear_history":
        db.clear_history(chat_id, user_id)
        await query.edit_message_text(
            "🧹 *История диалога очищена.*",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
    elif data == "menu_clear_facts":
        await query.edit_message_text(
            "⚠️ *ВНИМАНИЕ!*\n\n"
            "Удалить **ВСЕ** факты и вердикты?\n"
            "Это необратимо.",
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
