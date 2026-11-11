"""
UI.PY — новый интерфейс бота прямо в Telegram: одно сообщение, которое «живёт» и перелистывается кнопками.

🏠 Главная (дашборд)  → 🌍 Страны · 🏆 Топы · ⚖️ Вердикт · 📅 Время РП · 📖 Помощь · 🛠 Админ-панель
Весь интерфейс использует callback_data с префиксом "ui:" (до 64 байт, поэтому теги передаются хэшем).
"""

import hashlib
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton as B
from telegram import InlineKeyboardMarkup as M
from telegram import Update
from telegram.ext import ContextTypes

import auth
import commands as cmd
import config as C
import database as db
from auth import is_owner, is_staff
from handlers import facts_target, normal_tag_names, world_target
from rptime import get_rp_datetime, now_msk
from textutils import Cooldown, esc, shorten
from tg import edit_html, safe_reply, thread_id_of
from worldbank import fetch_top, format_value

log = logging.getLogger(__name__)
_ci_cd = Cooldown()

HOME = [B("🏠 Меню", callback_data="ui:home")]

# ключ: (код World Bank, тип значения, полное название, короткое название, эмодзи)
METRICS = {
    "g": ("NY.GDP.MKTP.CD", "usd", "ВВП", "ВВП", "💰"),
    "p": ("NY.GDP.PCAP.CD", "usd_pc", "ВВП на душу населения", "На душу", "👤"),
    "n": ("SP.POP.TOTL", "people", "Население", "Население", "👥"),
    "a": ("MS.MIL.XPND.CD", "usd", "Военные расходы", "Армия", "🪖"),
}


# =====================================================================
# МЕЛОЧИ
# =====================================================================

def kb(*rows) -> M:
    return M([list(r) for r in rows if r])


def bar(frac: float, n: int = 10) -> str:
    k = max(0, min(n, round(frac * n)))
    return "▰" * k + "▱" * (n - k)


def tag_hash(tag: str) -> str:
    return hashlib.md5(tag.encode("utf-8")).hexdigest()[:8]


async def find_tag(h: str):
    for t in await db.arun(db.get_all_tags):
        if tag_hash(t["tag"]) == h:
            return t
    return None


def greeting() -> str:
    h = now_msk().hour
    if h < 5:
        return "🌙 Доброй ночи"
    if h < 12:
        return "🌅 Доброе утро"
    if h < 18:
        return "☀️ Добрый день"
    return "🌆 Добрый вечер"


# =====================================================================
# ЭКРАНЫ
# =====================================================================

async def home_screen(user):
    s = await db.arun(db.get_stats)
    rp = get_rp_datetime()
    lines = [
        "╭──────────────────────╮",
        "      🌐 <b>RP BOT AI</b>",
        "╰──────────────────────╯",
        f"{greeting()}, <b>{esc(user.first_name or 'друг')}</b>!",
        "",
    ]
    if rp["year"]:
        frac = 1 - (rp["days_to_new_year"] or 0) / 365
        lines += [f"📅 <b>{rp['full']}</b> <i>по РП</i>", f"<code>{bar(frac)}</code> {int(frac * 100)}% года", ""]
    else:
        lines += ["📅 <i>Год РП не задан</i>", ""]
    lines += [
        f"📚 <b>{s['total']}</b> фактов  ·  🏷 <b>{s['tags']}</b> тегов  ·  ⚖️ <b>{s['verdicts']}</b> вердиктов",
        "",
        "<i>Выбери раздел 👇</i>",
    ]
    rows = [
        [B("🌍 Страны", callback_data="ui:cs:0"), B("🏆 Топы", callback_data="ui:top")],
        [B("⚖️ Вердикт", callback_data="ui:vd"), B("📅 Время РП", callback_data="ui:rp")],
        [B("📖 Помощь", callback_data="ui:hp")],
    ]
    if is_staff(user.id):
        rows.append([B("🛠 Админ-панель", callback_data="ui:ad")])
    return "\n".join(lines), kb(*rows)


async def top_screen(m: str, n: int, y: int):
    code, kind, label, short, emoji = METRICS[m]
    rows, used = await fetch_top(code, y, n)
    lines = [f"🏆 <b>ТОП-{n} · {emoji} {esc(label.upper())}</b>"]
    lines.append(f"📅 <i>{used} год" + (f" (за {y} данных нет)" if used != y else "") + "</i>\n")
    if rows:
        mx = rows[0]["value"] or 1
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(rows):
            medal = medals[i] if i < 3 else f"<b>{i + 1}.</b>"
            lines.append(f"{medal} {esc(r['country']['value'])}")
            lines.append(f"      <code>{bar(r['value'] / mx, 8)}</code> {format_value(r['value'], kind)}")
    else:
        lines.append("❌ Данные недоступны (World Bank не ответил или нет данных). Попробуй другой год.")

    metric_row = [B(("• " if k == m else "") + f"{v[4]} {v[3]}", callback_data=f"ui:top:{k}:{n}:{y}")
                  for k, v in METRICS.items()]
    count_row = [B(("• " if c == n else "") + f"Топ-{c}", callback_data=f"ui:top:{m}:{c}:{y}") for c in (5, 10, 20)]
    cur = datetime.now().year
    year_row = [B(f"⏪ {max(1960, y - 5)}", callback_data=f"ui:top:{m}:{n}:{max(1960, y - 5)}"),
                B(f"‹ {max(1960, y - 1)}", callback_data=f"ui:top:{m}:{n}:{max(1960, y - 1)}"),
                B(f"{min(cur, y + 1)} ›", callback_data=f"ui:top:{m}:{n}:{min(cur, y + 1)}"),
                B(f"{min(cur, y + 5)} ⏩", callback_data=f"ui:top:{m}:{n}:{min(cur, y + 5)}")]
    return "\n".join(lines), kb(metric_row[:2], metric_row[2:], count_row, year_row, HOME)


async def countries_screen(page: int):
    names = normal_tag_names(await db.arun(db.get_all_tags))
    per = 8
    pages = max(1, (len(names) + per - 1) // per)
    page = min(max(page, 0), pages - 1)
    tags = {t["tag"]: t for t in await db.arun(db.get_all_tags)}
    chunk = names[page * per:(page + 1) * per]
    text = (f"🌍 <b>СТРАНЫ И ТЕМЫ</b>\n\nТегов в базе: <b>{len(names)}</b> · стр. {page + 1}/{pages}\n"
            "<i>Открой тег, чтобы увидеть сводку.</i>") if names else \
        "🌍 <b>СТРАНЫ И ТЕМЫ</b>\n\n📭 База пока пуста.\nДобавь факт: <code>#россия ВВП 250 млрд</code>"
    btns = [B(f"#{shorten(t, 14)} · {tags[t]['cnt']}", callback_data=f"ui:ct:{tag_hash(t)}") for t in chunk]
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    nav = []
    if page > 0:
        nav.append(B("◀️", callback_data=f"ui:cs:{page - 1}"))
    if page < pages - 1:
        nav.append(B("▶️", callback_data=f"ui:cs:{page + 1}"))
    return text, kb(*rows, nav, HOME)


async def tag_screen(h: str, staff: bool):
    t = await find_tag(h)
    if not t:
        return "❌ Тег не найден (возможно, его удалили).", kb([B("⬅️ К списку", callback_data="ui:cs:0")], HOME)
    last = await db.arun(db.get_recent_facts, [t["tag"]], 1, False)
    lines = [f"🏷 <b>#{esc(t['tag'])}</b>", "",
             f"📚 Записей: <b>{t['cnt']}</b>  ·  ⚖️ вердиктов: <b>{t['verdicts']}</b>"]
    if last:
        lines += ["", "🕘 <b>Последний факт:</b>", f"<i>{esc(shorten(last[0]['text'], 300))}</i>"]
    rows = [[B("🧾 Сводка ИИ", callback_data=f"ui:ci:{h}")]]
    if staff:
        rows.append([B("📄 Все факты", callback_data=f"ui:ft:{h}:0")])
    rows.append([B("⬅️ К списку", callback_data="ui:cs:0"), HOME[0]])
    return "\n".join(lines), kb(*rows)


async def facts_screen(h: str, page: int):
    t = await find_tag(h)
    if not t:
        return await countries_screen(0)
    per = 5
    total = t["cnt"]
    pages = max(1, (total + per - 1) // per)
    page = min(max(page, 0), pages - 1)
    rows = await db.arun(db.get_facts_page, t["tag"], page * per, per)
    lines = [f"📄 <b>#{esc(t['tag'])}</b> · стр. {page + 1}/{pages}", ""]
    for i, r in enumerate(rows, 1):
        mark = "⚖️" if r["is_verdict"] else "▪️"
        year = f" <i>({r['year']})</i>" if r["year"] else ""
        lines.append(f"{mark} <b>{i}.</b> {esc(shorten(r['text'], 220))}{year}")
    del_row = [B(f"🗑 {i}", callback_data=f"ui:df:{r['id']}:{h}:{page}") for i, r in enumerate(rows, 1)]
    nav = []
    if page > 0:
        nav.append(B("◀️", callback_data=f"ui:ft:{h}:{page - 1}"))
    nav.append(B(f"{page + 1}/{pages}", callback_data=f"ui:ft:{h}:{page}"))
    if page < pages - 1:
        nav.append(B("▶️", callback_data=f"ui:ft:{h}:{page + 1}"))
    return "\n".join(lines), kb(del_row, nav, [B("⬅️ К тегу", callback_data=f"ui:ct:{h}"), HOME[0]])


async def verdict_screen(user):
    staff = is_staff(user.id)
    limit = C.VERDICT_LIMIT_STAFF if staff else C.VERDICT_LIMIT_PLAYER
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    used = await db.arun(db.get_usage, user.id, today, "verdict")
    pause = C.COOLDOWN_VERDICT_STAFF if staff else C.COOLDOWN_VERDICT_PLAYER
    text = (
        "⚖️ <b>ВЕРДИКТ ГЕЙМ-МАСТЕРА</b>\n\n"
        "Нейросеть сверяет заявку с базой фактов, прошлыми вердиктами и мировыми новостями "
        "и ищет NRP.\n\n"
        "<b>Как запросить:</b>\n"
        "▫️ <code>/verdict текст ситуации [год]</code>\n"
        "▫️ <code>/verdict</code> ответом на сообщение\n"
        "▫️ можно добавить <code>#теги</code> — бот возьмёт факты по ним\n\n"
        f"📊 <b>Сегодня:</b> <code>{bar(used / limit if limit else 1)}</code> {used}/{limit}\n"
        f"⏱ Пауза между вердиктами: {int(pause)} с"
    )
    return text, kb(HOME)


def rp_screen():
    rp = get_rp_datetime()
    if not rp["year"]:
        return "📅 <b>ВРЕМЯ РП</b>\n\n⚠️ Год РП не установлен.\nАдмин: <code>/year 2010</code>", kb(HOME)
    frac = 1 - (rp["days_to_new_year"] or 0) / 365
    hours_left = (rp["days_to_new_year"] or 0) / C.RP_DAYS_PER_REAL_HOUR
    text = (
        "📅 <b>ВРЕМЯ РП</b>\n\n"
        f"🗓 <b>{rp['full']}</b>\n"
        f"<code>{bar(frac, 12)}</code> {int(frac * 100)}% года\n\n"
        f"🎯 До Нового года РП: <b>{rp['days_to_new_year']}</b> дн. (≈ {hours_left:.1f} ч реального времени)\n"
        f"🕐 Сейчас по МСК: {rp['real_msk']}\n"
        f"⏱ Прошло с запуска: {rp['elapsed_hours']:.1f} ч = {rp['rp_days']:.0f} дн. РП\n\n"
        "<i>24 реальных часа = 1 год РП</i>"
    )
    return text, kb([B("🔄 Обновить", callback_data="ui:rp")], HOME)


async def admin_screen(user):
    s = await db.arun(db.get_stats)
    role = "👑 Владелец" if is_owner(user.id) else "🛡 Админ"
    fc, _ = facts_target()
    wc, _ = world_target()
    text = (
        f"🛠 <b>АДМИН-ПАНЕЛЬ</b>  ·  {role}\n\n"
        f"📚 Фактов: <b>{s['total']}</b>  ⚖️ Вердиктов: <b>{s['verdicts']}</b>  🏷 Тегов: <b>{s['tags']}</b>\n"
        f"💾 Тема фактов: {'✅' if fc else '❌'}   🌍 Тема мировых: {'✅' if wc else '❌'}"
    )
    rows = [
        [B("🏷 База по тегам", callback_data="ui:cs:0"), B("📊 Статистика", callback_data="ui:st")],
        [B("💾 Эта тема = факты", callback_data="ui:sf"), B("🌍 Эта тема = мировые", callback_data="ui:sw")],
        [B("📍 Где храним?", callback_data="ui:wh"), B("👥 Админы", callback_data="ui:ads")],
        [B("📥 Импорт", callback_data="ui:im"), B("📦 Экспорт", callback_data="ui:ex")],
        [B("🧹 Очистить мою историю", callback_data="ui:ch")],
    ]
    if is_owner(user.id):
        rows.append([B("☢️ Опасная зона", callback_data="ui:dz")])
    rows.append(HOME)
    return text, kb(*rows)


def admins_text() -> str:
    owners = ", ".join(f"<code>{i}</code>" for i in sorted(C.OWNER_IDS)) or "—"
    staff = ", ".join(f"<code>{i}</code>" for i in auth.staff_list()) or "—"
    return (f"👥 <b>АДМИНЫ БОТА</b>\n\n👑 Владельцы: {owners}\n🛡 Админы: {staff}\n\n"
            "Добавить: <code>/addadmin ID</code> (владелец)\nУбрать: <code>/deladmin ID</code>")


IMPORT_TEXT = (
    "📥 <b>ИМПОРТ ФАКТОВ</b>\n\n"
    "▫️ Ответь командой <code>/bulk</code> на длинное сообщение — нейросеть разобьёт его на факты с тегами.\n"
    "▫️ Для мировых новостей: <code>/bulkworld</code>.\n"
    "▫️ Один факт вручную: <code>#тег текст (год)</code> в теме для фактов."
)


# =====================================================================
# ВХОД И МАРШРУТИЗАЦИЯ
# =====================================================================

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = await home_screen(update.effective_user)
    await safe_reply(update.effective_message, text, reply_markup=markup)


async def ui_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    p = (q.data or "").split(":")
    kind = p[1] if len(p) > 1 else "home"
    user = q.from_user
    staff, owner = is_staff(user.id), is_owner(user.id)

    toast = None
    if kind == "ci":
        wait = _ci_cd.hit(user.id, 20)
        if wait:
            await q.answer(f"⏳ Подожди {int(wait) + 1} с", show_alert=False)
            return
        toast = "⏳ Готовлю сводку, это займёт до минуты…"
    await q.answer(toast)

    staff_only = {"ad", "st", "wh", "sf", "sw", "ads", "ex", "im", "ch", "ft", "df", "dy"}
    if (kind in staff_only and not staff) or (kind in ("dz", "cy") and not owner):
        await edit_html(q, "❌ Доступ закрыт.", kb(HOME))
        return

    back_admin = kb([B("⬅️ В админ-панель", callback_data="ui:ad"), HOME[0]])

    if kind == "home":
        text, markup = await home_screen(user)
        await edit_html(q, text, markup)

    elif kind == "top":
        rp = get_rp_datetime()
        m = p[2] if len(p) > 2 and p[2] in METRICS else "g"
        n = int(p[3]) if len(p) > 3 and p[3].isdigit() else 10
        y = int(p[4]) if len(p) > 4 and p[4].isdigit() else (rp["year"] or 2010)
        y = min(max(y, 1960), datetime.now().year)
        await edit_html(q, "⏳ <i>Загружаю данные World Bank…</i>")
        text, markup = await top_screen(m, n, y)
        await edit_html(q, text, markup)

    elif kind == "cs":
        text, markup = await countries_screen(int(p[2]) if len(p) > 2 and p[2].isdigit() else 0)
        await edit_html(q, text, markup)

    elif kind == "ct":
        text, markup = await tag_screen(p[2], staff)
        await edit_html(q, text, markup)

    elif kind == "ci":
        t = await find_tag(p[2])
        if t:
            context.args = [t["tag"]]
            await cmd.info_command(update, context)

    elif kind == "ft":
        text, markup = await facts_screen(p[2], int(p[3]))
        await edit_html(q, text, markup)

    elif kind == "df":
        fact = await db.arun(db.get_fact, int(p[2]))
        if not fact:
            text, markup = await facts_screen(p[3], int(p[4]))
        else:
            text = f"🗑 <b>Удалить эту запись?</b>\n\n<i>{esc(shorten(fact['text'], 400))}</i>"
            markup = kb([B("✅ Удалить", callback_data=f"ui:dy:{p[2]}:{p[3]}:{p[4]}"),
                         B("↩️ Отмена", callback_data=f"ui:ft:{p[3]}:{p[4]}")])
        await edit_html(q, text, markup)

    elif kind == "dy":
        await db.arun(db.delete_fact, int(p[2]))
        text, markup = await facts_screen(p[3], int(p[4]))
        await edit_html(q, text, markup)

    elif kind == "vd":
        text, markup = await verdict_screen(user)
        await edit_html(q, text, markup)

    elif kind == "rp":
        text, markup = rp_screen()
        await edit_html(q, text, markup)

    elif kind == "hp":
        await edit_html(q, cmd.text_help(context.bot.username or ""), kb(HOME))

    elif kind == "ad":
        text, markup = await admin_screen(user)
        await edit_html(q, text, markup)

    elif kind == "st":
        await edit_html(q, await cmd.text_stats(), back_admin)

    elif kind == "wh":
        await edit_html(q, cmd.text_where_save(), back_admin)

    elif kind in ("sf", "sw"):
        text = await cmd._save_target("facts" if kind == "sf" else "world", q.message.chat,
                                      thread_id_of(q.message), context)
        await edit_html(q, text, back_admin)

    elif kind == "ads":
        await edit_html(q, admins_text(), back_admin)

    elif kind == "im":
        await edit_html(q, IMPORT_TEXT, back_admin)

    elif kind == "ex":
        await cmd.export_command(update, context)

    elif kind == "ch":
        await db.arun(db.clear_history, q.message.chat.id, user.id)
        await edit_html(q, "🧹 <b>Твоя история диалога очищена.</b>", back_admin)

    elif kind == "dz":
        await edit_html(
            q,
            "☢️ <b>ОПАСНАЯ ЗОНА</b>\n\nУдалить <b>ВСЕ</b> факты и вердикты? Это необратимо.\n"
            "<i>Сначала сделай экспорт (📦).</i>",
            kb([B("☢️ Да, стереть всё", callback_data="ui:cy")], [B("↩️ Отмена", callback_data="ui:ad")]),
        )

    elif kind == "cy":
        await db.arun(db.clear_all_facts)
        await edit_html(q, "🗑 <b>База фактов полностью очищена.</b>", back_admin)
