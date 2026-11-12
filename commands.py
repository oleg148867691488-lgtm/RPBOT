"""
COMMANDS.PY — команды и инлайн-меню.

Публичные: /start /help /verdict /info /top /year (просмотр) /myid
Админы:    /menu /stats /tags /facts /find /delfact /export /bulk /bulkworld
           /year <год> /savechat /saveworld /clear_history /admins
Владельцы: /clear_facts /deltag /addadmin /deladmin
"""

import functools
import io
import json
import logging
import re
import time
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ContextTypes

import auth
import config as C
import database as db
from auth import is_owner, is_staff
from handlers import (
    _dedupe, bulk_import, facts_target, normal_tag_names, world_target,
)
from llm import ask, search_web
from rptime import get_rp_datetime, set_rp_year
from textutils import Cooldown, esc, md_to_html, match_tags, shorten, split_text, tag_matches
from tg import edit_html, reply_llm, safe_reply, send_typing, thread_id_of
from worldbank import COUNTRIES, format_value, fetch_top, get_economic_context

log = logging.getLogger(__name__)

SEP = "──────────────────────────"
_bulk_cd = Cooldown()


# =====================================================================
# ДЕКОРАТОРЫ ДОСТУПА
# =====================================================================

def staff_only(fn):
    @functools.wraps(fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or not is_staff(user.id):
            await safe_reply(update.effective_message, "❌ Только для админа/владельца.")
            return
        return await fn(update, context)
    return wrapper


def owner_only(fn):
    @functools.wraps(fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or not is_owner(user.id):
            await safe_reply(update.effective_message, "❌ Только для владельца бота.")
            return
        return await fn(update, context)
    return wrapper


# =====================================================================
# КЛАВИАТУРЫ И ТЕКСТЫ
# =====================================================================

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
         InlineKeyboardButton("🏷 Теги", callback_data="menu_tags")],
        [InlineKeyboardButton("💾 Тема фактов", callback_data="menu_savechat"),
         InlineKeyboardButton("🌍 Тема мировых", callback_data="menu_saveworld")],
        [InlineKeyboardButton("📍 Где храним?", callback_data="menu_wheresave"),
         InlineKeyboardButton("📅 Время РП", callback_data="menu_year")],
        [InlineKeyboardButton("🧹 Очистить историю", callback_data="menu_clear_history"),
         InlineKeyboardButton("🗑 Очистить базу", callback_data="menu_clear_facts")],
        [InlineKeyboardButton("❓ Помощь", callback_data="menu_help")],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад в меню", callback_data="menu_main")]])


def text_main(bot_username: str = "") -> str:
    mention = f"@{bot_username}" if bot_username else "@бот"
    return (
        "🤖 <b>RP BOT AI</b>\n\n"
        "📌 <b>Основные команды:</b>\n"
        "├ <code>#тег факт</code> — добавить факт\n"
        f"├ <code>{esc(mention)}, что там у...</code> — вопрос\n"
        "├ <code>/verdict текст [год]</code> — вердикт\n"
        "├ <code>/info страна</code> — сводка по стране\n"
        "├ <code>/top 10 ввп</code> — топ стран\n"
        "└ <code>/bulk</code> — массовый импорт\n\n"
        "🛠 <b>Админ-панель:</b> жми кнопки ниже 👇\n\n"
        f"{SEP}\n"
        f"💡 <i>Разработчик: @{esc(C.DEVELOPER_USERNAME)}</i>"
    )


def text_help(bot_username: str = "") -> str:
    mention = f"@{bot_username}" if bot_username else "@бот"
    return (
        "📖 <b>ПОМОЩЬ</b>\n\n"
        "🔹 <b>Сбор фактов</b>\n"
        "В теме, сохранённой через /savechat:\n"
        "<code>#россия ВВП 250 млрд (2002)</code>\n"
        "→ Бот запомнит. Если NRP — отметит владельца. Можно несколько тегов: <code>#россия #армия ...</code>\n\n"
        "🔹 <b>Мировые новости</b>\n"
        "В теме /saveworld: <code>#НАТО начал распад (2010)</code>\n"
        "→ Сохранится как мировая и учтётся в вердиктах.\n\n"
        "🔹 <b>Вопросы</b>\n"
        f"<code>{esc(mention)}, расскажи про Россию</code> (в личке можно без @)\n\n"
        "🔹 <b>Вердикты</b>\n"
        "<code>/verdict Ввести санкции против США 2008</code>\n"
        "Или командой <code>/verdict</code> в ответ на сообщение.\n"
        f"Игроки: {C.VERDICT_LIMIT_PLAYER}/день (пауза {int(C.COOLDOWN_VERDICT_PLAYER)} с), "
        f"админы: {C.VERDICT_LIMIT_STAFF}/день ({int(C.COOLDOWN_VERDICT_STAFF)} с).\n\n"
        "🔹 <b>Страны</b>\n"
        "<code>/info Россия</code> — сводка: база → World Bank → интернет.\n"
        "<code>/top 10 ввп</code>, <code>/top 5 население 2010</code>, "
        "<code>/top ввп на душу</code>, <code>/top 10 армия</code>.\n\n"
        "🔹 <b>Сравнение и хроника</b>\n"
        "<code>/vs Россия США [год]</code> — таблица экономики и армии рядом.\n"
        "<code>/timeline Россия</code> — хронология фактов и вердиктов по годам.\n\n"
        "🔹 <b>Мир живёт</b>\n"
        "<code>/news</code> · <code>/market</code> · <code>/tension</code> — события, биржа, напряжённость.\n"
        "<code>/op президент США 100к от Франции</code> — тайная операция (должность, бюджет, заказчик).\n"
        "<code>/mycountry Россия</code> — твоя страна по умолчанию.\n"
        "<code>#франция усилил охрану президента</code> — новость с тегом: ИИ-ГМ сам пересчитает защиту страны.\n"
        "<code>/terror Франция 200к от Германии</code> — теракт (только в личке с ботом).\n\n"
        "🔹 <b>Время РП</b>\n"
        "<code>/year</code> — показать дату РП. Админ: <code>/year 2010</code> — задать.\n"
        "24 реальных часа = 1 год РП (2 часа ≈ месяц).\n\n"
        "🔹 <b>Для админов</b>\n"
        "/menu · /stats · /tags · /facts тег · /find текст · /delfact id · /export\n"
        "/bulk и /bulkworld (реплаем на длинный текст) · /savechat · /saveworld\n"
        "/clear_history · /admins · /ops\n"
        "/event [тип] [страна] — событие вручную · /security страна 0-100 — защита страны\n"
        "🔹 <b>Для владельцев</b>\n"
        "/clear_facts · /deltag тег · /addadmin · /deladmin\n\n"
        "ℹ️ /myid — узнать свой ID и ID чата/темы."
    )


async def text_stats() -> str:
    s = await db.arun(db.get_stats)
    return (
        "📊 <b>СТАТИСТИКА</b>\n\n"
        f"📚 Всего фактов: <b>{s['total']}</b>\n"
        f"⚖️ Вердиктов: <b>{s['verdicts']}</b>\n"
        f"🏷 Уникальных тегов: <b>{s['tags']}</b>\n\n{SEP}"
    )


async def text_tags() -> str:
    tags = await db.arun(db.get_all_tags)
    if not tags:
        return "🏷 <b>ТЕГИ</b>\n\n📭 База пуста. Добавь первый факт:\n<code>#россия ВВП 250 млрд</code>"
    lines, world_count, shown = ["🏷 <b>ТЕГИ</b>\n"], 0, 0
    for t in tags:
        if t["tag"].startswith("игрок_"):
            continue
        if t["tag"].startswith("world_"):
            world_count += 1
            continue
        if shown < 40:
            lines.append(f"▪️ <b>#{esc(t['tag'])}</b> — {t['cnt']} ({t['verdicts']} верд.)")
            shown += 1
    if world_count:
        lines.append(f"\n🌍 Мировых тегов: <b>{world_count}</b>")
    lines.append(SEP)
    return "\n".join(lines)


def text_where_save() -> str:
    fc, ft = facts_target()
    wc, wt = world_target()
    f = f"<code>{fc}</code>" + (f" / тема: {ft}" if ft else "") if fc else "❌ не сохранён"
    w = f"<code>{wc}</code>" + (f" / тема: {wt}" if wt else "") if wc else "❌ не сохранён"
    return (
        "📍 <b>ТЕМЫ ДЛЯ СБОРА</b>\n\n"
        f"📚 Факты: {f}\n🌍 Мировые: {w}\n\n"
        "Сменить: <code>/savechat</code> или <code>/saveworld</code> в нужной теме."
    )


def text_year() -> str:
    rp = get_rp_datetime()
    if not rp["year"]:
        return "📅 <b>ВРЕМЯ РП</b>\n\n⚠️ Год РП не установлен.\nАдмин: <code>/year 2010</code>"
    return (
        "📅 <b>ВРЕМЯ РП</b>\n\n"
        f"📆 <b>Дата в РП:</b> {rp['full']}\n"
        f"🕐 Реальное МСК: {rp['real_msk']}\n"
        f"⏱ Прошло (реал): {rp['elapsed_hours']:.2f} ч.\n"
        f"📊 Дней РП прошло: {rp['rp_days']:.1f}\n"
        f"🎯 До смены года: {rp['days_to_new_year']} дн. РП\n\n"
        "⚡ 1 реальный час ≈ 15.2 дня РП · 24 часа = 1 год РП"
    )


# =====================================================================
# ПРОСТЫЕ КОМАНДЫ
# =====================================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update.message, text_help(context.bot.username or ""))


@staff_only
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update.message, text_main(context.bot.username or ""), reply_markup=main_menu_keyboard())


@staff_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update.message, await text_stats())


@staff_only
async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update.message, await text_tags())


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user = update.message, update.effective_user
    await safe_reply(
        msg,
        f"🆔 Твой ID: <code>{user.id}</code>\n"
        f"💬 ID чата: <code>{msg.chat.id}</code>\n"
        f"🧵 ID темы: <code>{thread_id_of(msg)}</code>",
    )


# =====================================================================
# РАБОТА С БАЗОЙ (админ)
# =====================================================================

def _fact_line(f: dict, with_tag: bool = False) -> str:
    mark = "⚖️" if f["is_verdict"] else "•"
    tag = f" <b>#{esc(f['tag'])}</b>" if with_tag else ""
    year = f" <i>({f['year']})</i>" if f.get("year") else ""
    return f"{mark} <code>{f['id']}</code>{tag} {esc(shorten(f['text'], 150))}{year}"


@staff_only
async def facts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, args = update.message, context.args or []
    if not args:
        await safe_reply(msg, "Используй: <code>/facts тег [страница]</code>")
        return
    tag = args[0].lstrip("#").lower()
    page = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
    total = await db.arun(db.count_facts_by_tag, tag)
    if not total:
        await safe_reply(msg, f"❌ Тег <b>#{esc(tag)}</b> не найден. Список тегов: /tags")
        return
    per = 10
    pages = (total + per - 1) // per
    page = min(max(page, 1), pages)
    rows = await db.arun(db.get_facts_page, tag, (page - 1) * per, per)
    lines = [f"🏷 <b>#{esc(tag)}</b> — записей: {total}, стр. {page}/{pages}\n"]
    lines += [_fact_line(r) for r in rows]
    lines.append(f"\nУдалить запись: <code>/delfact id</code>"
                 + (f" · дальше: <code>/facts {esc(tag)} {page + 1}</code>" if page < pages else ""))
    await safe_reply(msg, "\n".join(lines))


@staff_only
async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    query = " ".join(context.args or []).strip()
    if len(query) < 2:
        await safe_reply(msg, "Используй: <code>/find текст</code>")
        return
    rows = await db.arun(db.search_facts, query, 15)
    if not rows:
        await safe_reply(msg, f"🔎 По запросу «{esc(query)}» ничего не найдено.")
        return
    await safe_reply(msg, f"🔎 <b>Найдено (последние {len(rows)}):</b>\n\n" +
                     "\n".join(_fact_line(r, with_tag=True) for r in rows))


@staff_only
async def delfact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, args = update.message, context.args or []
    if not args or not args[0].isdigit():
        await safe_reply(msg, "Используй: <code>/delfact id</code> (id видно в /facts и /find)")
        return
    ok = await db.arun(db.delete_fact, int(args[0]))
    await safe_reply(msg, "🗑 Запись удалена." if ok else "❌ Запись с таким id не найдена.")


@owner_only
async def deltag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, args = update.message, context.args or []
    if not args:
        await safe_reply(msg, "Используй: <code>/deltag тег</code>")
        return
    tag = args[0].lstrip("#").lower()
    n = await db.arun(db.delete_tag, tag)
    await safe_reply(msg, f"🗑 Удалено записей по тегу <b>#{esc(tag)}</b>: {n}" if n
                     else f"❌ Тег <b>#{esc(tag)}</b> не найден.")


@staff_only
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    rows = await db.arun(db.export_facts)
    if not rows:
        await safe_reply(msg, "📭 База пуста — экспортировать нечего.")
        return
    data = json.dumps(rows, ensure_ascii=False, indent=1).encode("utf-8")
    name = f"rpbot_facts_{datetime.now(timezone.utc):%Y%m%d_%H%M}.json"
    await msg.reply_document(
        document=InputFile(io.BytesIO(data), filename=name),
        caption=f"📦 Резервная копия базы: {len(rows)} записей.",
    )


@staff_only
async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await db.arun(db.clear_history, msg.chat.id, msg.from_user.id)
    await safe_reply(msg, "🧹 <b>История диалога очищена.</b>")


@owner_only
async def clear_facts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(
        update.message,
        "⚠️ <b>ВНИМАНИЕ!</b>\n\nУдалить <b>ВСЕ</b> факты и вердикты? Это необратимо.\n"
        "(Совет: сначала сделай /export.)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, удалить", callback_data="menu_clear_facts_confirm")],
            [InlineKeyboardButton("⬅️ Отмена", callback_data="menu_cancel")],
        ]),
    )


# =====================================================================
# АДМИНЫ БОТА
# =====================================================================

def _target_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        return msg.reply_to_message.from_user.id
    args = context.args or []
    if args and args[0].lstrip("-").isdigit():
        return int(args[0])
    return None


@owner_only
async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = _target_user_id(update, context)
    if not uid:
        await safe_reply(update.message, "Используй: <code>/addadmin ID</code> или реплаем на сообщение человека.")
        return
    n = await db.arun(auth.add_bot_admins, [uid])
    await safe_reply(update.message, f"✅ Админ добавлен: <code>{uid}</code>" if n
                     else f"ℹ️ <code>{uid}</code> уже админ (или владелец).")


@owner_only
async def deladmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = _target_user_id(update, context)
    if not uid:
        await safe_reply(update.message, "Используй: <code>/deladmin ID</code> или реплаем на сообщение.")
        return
    ok = await db.arun(auth.remove_bot_admin, uid)
    await safe_reply(update.message, f"🗑 Админ удалён: <code>{uid}</code>" if ok
                     else f"❌ <code>{uid}</code> не найден в списке админов.")


@staff_only
async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owners = ", ".join(f"<code>{i}</code>" for i in sorted(C.OWNER_IDS)) or "—"
    staff = ", ".join(f"<code>{i}</code>" for i in auth.staff_list()) or "—"
    await safe_reply(update.message, f"👑 <b>Владельцы:</b> {owners}\n🛡 <b>Админы:</b> {staff}")


# =====================================================================
# ТЕМЫ ДЛЯ СБОРА (/savechat, /saveworld)
# =====================================================================

async def _import_chat_admins(chat, context) -> int:
    """Админы группы становятся админами бота (как и раньше, но добавляются, а не затирают список)."""
    if chat.id >= 0:
        return 0
    try:
        admins = await context.bot.get_chat_administrators(chat.id)
    except Exception as e:
        log.warning("Не удалось получить админов группы %s: %s", chat.id, e)
        return 0
    ids = [a.user.id for a in admins if not a.user.is_bot]
    if ids:
        await db.arun(auth.add_bot_admins, ids)
    return len(ids)


async def _save_target(kind: str, chat, thread_id: int, context) -> str:
    other_chat, other_thread = world_target() if kind == "facts" else facts_target()
    if other_chat and chat.id == other_chat and thread_id == other_thread:
        other = "мировые" if kind == "facts" else "факты"
        return (f"❌ Эта тема уже сохранена как <b>{other}</b>.\n"
                f"Используй <b>другую тему</b>.")
    prefix = "facts" if kind == "facts" else "world"
    await db.arun(db.set_setting, f"{prefix}_chat_id", str(chat.id))
    await db.arun(db.set_setting, f"{prefix}_thread_id", str(thread_id))

    title = esc(chat.title or "Личка")
    topic = f" (тема #{thread_id})" if thread_id else ""
    if kind == "facts":
        n = await _import_chat_admins(chat, context)
        extra = f"\n👥 Админов группы добавлено в админы бота: <b>{n}</b>" if n else ""
        return (f"✅ <b>ТЕМА ФАКТОВ СОХРАНЕНА</b>\n\n📌 Чат: <b>{title}</b>{topic}\n"
                f"🆔 ID: <code>{chat.id}</code> / тема: <code>{thread_id}</code>{extra}\n\n"
                "Факты с <code>#тегом</code> собираются <b>только в этой теме</b>.")
    return (f"🌍 <b>ТЕМА МИРОВЫХ СОХРАНЕНА</b>\n\n📌 Чат: <b>{title}</b>{topic}\n"
            f"🆔 ID: <code>{chat.id}</code> / тема: <code>{thread_id}</code>\n\n"
            "Мировые новости с <code>#тегом</code> собираются <b>только здесь</b>.")


@staff_only
async def savechat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await safe_reply(msg, await _save_target("facts", msg.chat, thread_id_of(msg), context))


@staff_only
async def saveworld_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    await safe_reply(msg, await _save_target("world", msg.chat, thread_id_of(msg), context))


# =====================================================================
# /year
# =====================================================================

async def year_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, args = update.message, context.args or []
    if not args:
        await safe_reply(msg, text_year())
        return
    if not is_staff(update.effective_user.id):
        await safe_reply(msg, "❌ Менять год может только админ/владелец.")
        return
    try:
        year = int(args[0])
        if not 1900 <= year <= 2100:
            raise ValueError
    except ValueError:
        await safe_reply(msg, "❌ Год должен быть числом от 1900 до 2100. Пример: <code>/year 2010</code>")
        return
    now = await db.arun(set_rp_year, year)
    await safe_reply(
        msg,
        f"📅 <b>Год РП установлен на {year}.</b>\n\n"
        f"🕐 Старт: сейчас ({now.day} числа, {now.month} месяца, {year} год).\n"
        "⚡ 2 реальных часа = 1 месяц РП, 24 часа = 1 год РП.\n\nПроверить: /year",
    )


# =====================================================================
# /info
# =====================================================================

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    country = " ".join(context.args or []).strip()
    if not country:
        await safe_reply(msg, "❌ Используй: <code>/info Россия</code>")
        return
    country = country[:60]
    status = await safe_reply(msg, f"⏳ Собираю информацию по <b>{esc(country)}</b>...")
    await send_typing(context.bot, msg.chat.id, thread_id_of(msg))

    tag_rows = await db.arun(db.get_all_tags)
    matched = match_tags(normal_tag_names(tag_rows), country)
    facts = await db.arun(db.get_recent_facts, matched, 25, False) if matched else []
    if not facts:
        found = await db.arun(db.search_facts, country, 30)
        facts = [f for f in found if not f["is_verdict"] and not f["tag"].startswith(("world_", "игрок_"))]
    facts = list(reversed(_dedupe(facts)))

    wb_context = await get_economic_context(f"ВВП {country}")
    rp = get_rp_datetime()
    year_line = f"Сейчас в РП: {rp['year']} год. " if rp["year"] else ""

    if facts:
        facts_str = "\n".join(
            f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f["year"] else "") for f in facts
        )
        system_prompt = (
            f"Ты — аналитический РП-бот. {year_line}Составь сводку по стране {country} на основе фактов из базы.\n"
            "Структура: 1) Экономика (ВВП, бюджет). 2) Армия. 3) Политика. 4) Международное положение. 5) Ключевые события.\n"
            "Используй ТОЛЬКО предоставленные факты. НЕ ВЫДУМЫВАЙ числа. Если чего-то нет — пиши 'нет данных'.\n\n"
            f"ФАКТЫ ИЗ БАЗЫ:\n{facts_str}"
        )
        source = "база"
    else:
        web = await search_web(f"{country} экономика армия население ВВП {rp['year'] or 2010}")
        if not web:
            await safe_reply(
                msg,
                f"❌ В базе нет данных по стране <b>{esc(country)}</b>, и поиск в интернете ничего не дал.\n\n"
                f"Добавь факты через <code>#{esc(country.lower().replace(' ', '_'))} ...</code>",
            )
            return
        system_prompt = (
            f"Ты — аналитический РП-бот. {year_line}Составь сводку по стране {country} на основе результатов поиска.\n"
            "Структура: 1) Экономика (ВВП, население). 2) Армия. 3) Политика. 4) Международное положение.\n"
            "Помечай данные как '(из интернета)'.\n\n"
            f"РЕЗУЛЬТАТЫ ПОИСКА:\n{web}"
        )
        source = "интернет"

    if wb_context:
        system_prompt += f"\n\n{wb_context}"

    result = await ask("main", [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Дай сводку по стране {country}"},
    ], temperature=0.5)
    if not result:
        await safe_reply(msg, "❌ Не удалось получить ответ. Попробуй позже.")
        return

    header = f"🌍 <b>СВОДКА: {esc(country.upper())}</b> <i>(источник: {source})</i>\n\n"
    await reply_llm(msg, result, header=header)
    try:
        await status.delete()
    except Exception:
        pass


# =====================================================================
# /top
# =====================================================================

TOP_METRICS = [
    (("на душу",), "NY.GDP.PCAP.CD", "usd_pc", "ВВП на душу населения"),
    (("населен", "population"), "SP.POP.TOTL", "people", "населению"),
    (("арми", "военн", "оборон"), "MS.MIL.XPND.CD", "usd", "военным расходам"),
    (("ввп", "экономик", "gdp"), "NY.GDP.MKTP.CD", "usd", "ВВП"),
]
_TOP_STOP = {"стран", "страны", "по", "топ", "в", "года", "год", "г", "за"}
_SINGLE_COUNTRY_KEYS = [k for k in COUNTRIES if " " not in k]


def _pick_metric(rest: str):
    for keys, code, kind, label in TOP_METRICS:
        if any(k in rest for k in keys):
            return code, kind, label
    words = [w for w in rest.split() if w not in _TOP_STOP]
    if not words:
        return "NY.GDP.MKTP.CD", "usd", "ВВП"
    return None, None, " ".join(words)[:40]


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = " ".join(context.args or []).lower()

    rp = get_rp_datetime()
    ym = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    year = int(ym.group(1)) if ym else (rp["year"] or 2010)
    rest = text.replace(ym.group(0), " ", 1) if ym else text

    cm = re.search(r"\b(\d{1,2})\b", rest)           # год уже вырезан, поэтому он не примется за количество
    count = max(1, min(int(cm.group(1)), 30)) if cm else 10
    if cm:
        rest = rest.replace(cm.group(0), " ", 1)

    code, kind, label = _pick_metric(rest)
    status = await safe_reply(msg, f"⏳ Составляю топ-{count} стран по {esc(label)} на {year} год...")

    lines = []
    rows, used_year = [], year
    if code:
        rows, used_year = await fetch_top(code, year, count)
    if rows:
        note = f" — данных за {year} нет" if used_year != year else ""
        lines.append(f"📊 <b>ТОП-{len(rows)} СТРАН ПО {esc(label.upper())}</b> ({used_year} год{note})\n")
        lines.append("🌍 <b>World Bank:</b>")
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. {esc(r['country']['value'])} — {format_value(r['value'], kind)}")
    else:
        prompt = (
            f"Составь топ-{count} стран по показателю «{label}» на {year} год. "
            "Используй реальные исторические данные. "
            "Формат ответа — строго список: '1. Страна — значение'. Без вступлений."
        )
        llm_result = await ask("main", [
            {"role": "system", "content": "Ты — аналитик по геополитике. Выдаёшь рейтинги стран на основе реальных данных."},
            {"role": "user", "content": prompt},
        ], temperature=0.3)
        lines.append(f"📊 <b>ТОП-{count} СТРАН ПО {esc(label.upper())}</b> ({year} год)\n")
        if llm_result:
            lines.append("🤖 <b>По общим данным ИИ</b> <i>(может быть неточно)</i>:")
            lines.append(md_to_html(llm_result))
        else:
            lines.append("❌ Не удалось получить данные.")

    # Факты из базы РП по странам
    tag_rows = await db.arun(db.get_all_tags)
    country_tags = [t for t in normal_tag_names(tag_rows)
                    if any(tag_matches(t, [c]) for c in _SINGLE_COUNTRY_KEYS)]
    if country_tags:
        facts = await db.arun(db.get_recent_facts, country_tags[:30], 60, False)
        seen, shown = set(), []
        for f in facts:
            if f["tag"] not in seen:
                seen.add(f["tag"])
                shown.append(f)
            if len(shown) >= 8:
                break
        if shown:
            lines.append("\n📚 <b>Факты из базы РП:</b>")
            lines += [f"• [{esc(f['tag'])}] {esc(shorten(f['text'], 120))}" for f in shown]

    for part in split_text("\n".join(lines), 3500):
        await safe_reply(msg, part)
    try:
        await status.delete()
    except Exception:
        pass


# =====================================================================
# МАССОВЫЙ ИМПОРТ
# =====================================================================

async def _do_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE, is_world: bool):
    msg = update.message
    if not is_staff(msg.from_user.id):
        await safe_reply(msg, "❌ Только для админа/владельца.")
        return

    wait = _bulk_cd.hit(msg.from_user.id, C.BULK_COOLDOWN)
    if wait:
        await safe_reply(msg, f"⏳ Подожди ещё {int(wait) + 1} сек между массовыми импортами.")
        return

    text = ""
    if msg.reply_to_message and (msg.reply_to_message.text or msg.reply_to_message.caption):
        text = msg.reply_to_message.text or msg.reply_to_message.caption
    else:
        text = re.sub(r"^/bulk(world)?(@\w+)?", "", msg.text or "", flags=re.I).strip()

    if not text:
        _bulk_cd.reset(msg.from_user.id)
        await safe_reply(
            msg,
            "❌ Использование:\n• Ответь (реплай) на сообщение командой <code>/bulk</code>\n"
            "• Или: <code>/bulk текст</code>\n• Для мировых: <code>/bulkworld</code>",
        )
        return
    if len(text) < 50:
        _bulk_cd.reset(msg.from_user.id)
        await safe_reply(msg, "❌ Слишком короткий текст (< 50 символов).")
        return

    status = await safe_reply(msg, f"⏳ Разбираю текст ({len(text)} симв.) на факты... Это займёт 10–20 секунд.")
    await send_typing(context.bot, msg.chat.id, thread_id_of(msg))
    saved = await bulk_import(update, text, is_world=is_world)

    if saved == 0:
        _bulk_cd.reset(msg.from_user.id)
        await safe_reply(msg, "❌ Не удалось разбить текст на факты (или все они уже есть в базе).")
    else:
        kind = "мировых новостей" if is_world else "фактов"
        await safe_reply(msg, f"✅ <b>Импортировано {saved} {kind}.</b>\nПроверь /tags или /stats.")
    try:
        await status.delete()
    except Exception:
        pass


async def bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _do_bulk(update, context, is_world=False)


async def bulkworld_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _do_bulk(update, context, is_world=True)


# =====================================================================
# ИНЛАЙН-МЕНЮ
# =====================================================================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    chat = query.message.chat

    if not is_staff(user_id):
        await edit_html(query, "❌ Доступ закрыт.")
        return

    if data == "menu_main":
        await edit_html(query, text_main(context.bot.username or ""), main_menu_keyboard())
    elif data == "menu_cancel":
        await edit_html(query, "↩️ Отменено.")
    elif data == "menu_stats":
        await edit_html(query, await text_stats(), back_keyboard())
    elif data == "menu_tags":
        await edit_html(query, await text_tags(), back_keyboard())
    elif data == "menu_help":
        await edit_html(query, text_help(context.bot.username or ""), back_keyboard())
    elif data == "menu_wheresave":
        await edit_html(query, text_where_save(), back_keyboard())
    elif data == "menu_year":
        await edit_html(query, text_year(), back_keyboard())
    elif data in ("menu_savechat", "menu_saveworld"):
        kind = "facts" if data == "menu_savechat" else "world"
        text = await _save_target(kind, chat, thread_id_of(query.message), context)
        await edit_html(query, text, back_keyboard())
    elif data == "menu_clear_history":
        await db.arun(db.clear_history, chat.id, user_id)
        await edit_html(query, "🧹 <b>История диалога очищена.</b>", back_keyboard())
    elif data == "menu_clear_facts":
        if not is_owner(user_id):
            await edit_html(query, "❌ Очистить всю базу может только владелец.", back_keyboard())
            return
        await edit_html(
            query,
            "⚠️ <b>ВНИМАНИЕ!</b>\n\nУдалить <b>ВСЕ</b> факты и вердикты? Это необратимо.\n"
            "(Совет: сначала сделай /export.)",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, удалить", callback_data="menu_clear_facts_confirm")],
                [InlineKeyboardButton("⬅️ Отмена", callback_data="menu_main")],
            ]),
        )
    elif data == "menu_clear_facts_confirm":
        if not is_owner(user_id):
            await edit_html(query, "❌ Очистить всю базу может только владелец.", back_keyboard())
            return
        await db.arun(db.clear_all_facts)
        await edit_html(query, "🗑 <b>База фактов полностью очищена.</b>", back_keyboard())
