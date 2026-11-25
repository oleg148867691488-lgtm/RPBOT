"""
UI.PY — новый интерфейс бота прямо в Telegram: одно сообщение, которое «живёт» и перелистывается кнопками.

🏠 Главная (дашборд)  → 🌍 Страны · 🏆 Топы · ⚖️ Вердикт · 📅 Время РП · 📖 Помощь · 🛠 Админ-панель
Весь интерфейс использует callback_data с префиксом "ui:" (до 64 байт, поэтому теги передаются хэшем).
"""

import asyncio
import time
import hashlib
import logging
import re
from datetime import datetime, timezone

from telegram import InlineKeyboardButton as B
from telegram import InlineKeyboardMarkup as M
from telegram import Update
from telegram.ext import ContextTypes

import auth
import commands as cmd
import world
import config as C
import database as db
from auth import is_owner, is_staff
from events import EMOJI, EVENTS, MODE_NAMES, PER_DAY, create_event
from handlers import facts_target, normal_tag_names, world_target
from rptime import get_rp_datetime, now_msk
from textutils import Cooldown, esc, match_tags, shorten
from tg import edit_html, safe_reply, thread_id_of
from worldbank import (
    ISO_RU, VS_METRICS, fetch_top, fetch_value, find_countries, format_value,
)

log = logging.getLogger(__name__)
_ci_cd = Cooldown()
_vs_cd = Cooldown()

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

from style import LINE, level, meter, quote, quote_html, title as hdr


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
    lines = [hdr("👑", "RP BOT AI", "штаб мира"),
             f"{greeting()}, <b>{esc(user.first_name or 'друг')}</b>!", ""]
    if rp["year"]:
        frac = 1 - (rp["days_to_new_year"] or 0) / 365
        lines += [f"📅 <b>{rp['full']}</b> <i>по РП</i>", f"<code>{bar(frac)}</code> {int(frac * 100)}% года", ""]
    else:
        lines += ["📅 <i>Год РП не задан</i>", ""]
    lines.append(quote_html(f"📚 <b>{s['total']}</b> фактов\n🏷 <b>{s['tags']}</b> тегов\n⚖️ <b>{s['verdicts']}</b> вердиктов"))
    last = await db.arun(db.get_world_events, 1, 0, None)
    if last:
        lines.append(f"📰 <i>{esc(shorten(last[0]['text'].split(chr(10))[0], 80))}</i>")
    lines += ["", "<i>Выбери раздел 👇</i>"]
    rows = [
        [B("🌍 Страны", callback_data="ui:cs:0"), B("🏆 Топы", callback_data="ui:top")],
        [B("📰 Новости", callback_data="ui:nw:a:0"), B("📈 Биржа", callback_data="ui:mk")],
        [B("🌡 Напряжённость", callback_data="ui:tn"), B("🛡 Моя страна", callback_data="ui:mc")],
        [B("🕵️ Операции", callback_data="ui:op"), B("⚖️ Вердикт", callback_data="ui:vd")],
        [B("📅 Время РП", callback_data="ui:rp"), B("📖 Помощь", callback_data="ui:hp")],
    ]
    if is_staff(user.id):
        rows.append([B("🛠 Админ-панель", callback_data="ui:ad")])
    return "\n".join(lines), kb(*rows)


async def top_screen(m: str, n: int, y: int):
    code, kind, label, short, emoji = METRICS[m]
    rows, used = await fetch_top(code, y, n)
    lines = [hdr("🏆", f"Топ-{n}: {label}", f"{used} год" + (f" (за {y} данных нет)" if used != y else "")), ""]
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
            "<i>Открой тег: сводка и таймлайн.</i>\n\n"
            "⚔️ Сравнить страны: <code>/vs Россия США</code>\n🕰 Хроника: <code>/timeline Россия</code>") if names else \
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
    rows = [[B("🧾 Сводка ИИ", callback_data=f"ui:ci:{h}"), B("🕰 Таймлайн", callback_data=f"ui:tl:{h}:0")]]
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
        [B("🎲 События мира", callback_data="ui:ev"), B("📜 Журнал ГМ", callback_data="ui:ol")],
        [B("↩️ Откат новости", callback_data="ui:rb:0")],
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
    elif kind == "vs":
        wait = _vs_cd.hit(user.id, 4)
        if wait:
            await q.answer(f"⏳ Подожди {int(wait) + 1} с")
            return
    await q.answer(toast)

    staff_only = {"ad", "st", "wh", "sf", "sw", "ads", "ex", "im", "ch", "ft", "df", "dy", "ev", "evm", "evr", "evk", "evb", "evi", "ol", "rb", "rby", "rbn", "fb", "fby", "fbn", "rqa", "rqd", "rqn"}
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

    elif kind == "tl":
        text, markup = await timeline_screen(p[2], int(p[3]))
        await edit_html(q, text, markup)

    elif kind == "vs":
        await edit_html(q, "⏳ <i>Сравниваю страны…</i>")
        text, markup = await vs_screen(p[2], p[3], int(p[4]))
        await edit_html(q, text, markup)

    elif kind == "nw":
        text, markup = await news_screen(p[2] if len(p) > 2 else "a", int(p[3]) if len(p) > 3 and p[3].isdigit() else 0)
        await edit_html(q, text, markup)

    elif kind == "mk":
        text, markup = market_screen()
        await edit_html(q, text, markup)

    elif kind == "mc":
        text, markup = await country_screen(user)
        await edit_html(q, text, markup)

    elif kind == "tn":
        text, markup = tension_screen()
        await edit_html(q, text, markup)

    elif kind == "op":
        text, markup = await ops_screen(user)
        await edit_html(q, text, markup)

    elif kind == "ev":
        text, markup = events_admin_screen()
        await edit_html(q, text, markup)

    elif kind == "evm":
        if len(p) > 2 and p[2] in PER_DAY:
            await db.arun(db.set_setting, "events_mode", p[2])
        text, markup = events_admin_screen()
        await edit_html(q, text, markup)

    elif kind in ("evr", "evk", "evb"):
        if not world_target()[0]:
            await edit_html(q, "❌ Тема мировых новостей не задана. Открой нужную тему и нажми «🌍 Эта тема = мировые».",
                            kb([B("⬅️ Назад", callback_data="ui:ev")]))
        elif kind == "evb":
            await edit_html(q, "⏳ <i>Генерирую 3 события подряд…</i>")
            heads = []
            for _ in range(3):
                r = await create_event(context.bot)
                heads.append(f"✅ {esc(r['head'])}" if r else "❌ не получилось")
            await edit_html(q, "\n".join(heads), kb([B("🎲×3 ещё", callback_data="ui:evb")], [B("⬅️ Назад", callback_data="ui:ev")]))
        else:
            ev_kind = p[2] if kind == "evk" and len(p) > 2 and p[2] in EVENTS else None
            await edit_html(q, "⏳ <i>Генерирую событие…</i>")
            r = await create_event(context.bot, ev_kind)
            msg_text = f"✅ Опубликовано: <b>{esc(r['head'])}</b>" if r else "❌ Не получилось (нейросеть не ответила, попробуй ещё раз)."
            again = f"ui:evk:{ev_kind}" if ev_kind else "ui:evr"
            await edit_html(q, msg_text, kb([B("🎲 Ещё одно", callback_data=again)], [B("⬅️ Назад", callback_data="ui:ev")]))

    elif kind == "evi":
        if not world_target()[0]:
            await edit_html(q, "❌ Тема мировых новостей не задана. Открой нужную тему и нажми «🌍 Эта тема = мировые».",
                            kb([B("⬅️ Назад", callback_data="ui:ev")]))
        else:
            context.user_data["pending_news_idea"] = time.time()
            await edit_html(q, "💡 <b>Напиши идею новости</b> одним сообщением (10 минут) — бот сам оформит её в заметку, "
                               "подберёт вид события и страну, учтёт обстановку и эпоху.\n"
                               "Например: «в Германии нашли подделку выборов» или «обвал нефти из-за ОПЕК».",
                            kb([B("↩️ Отмена", callback_data="ui:ev")]))

    elif kind == "ol":
        text, markup = await ops_log_screen()
        await edit_html(q, text, markup)

    elif kind == "rb":
        text, markup = await rollback_screen(int(p[2]) if len(p) > 2 and p[2].isdigit() else 0)
        await edit_html(q, text, markup)

    elif kind == "fb":
        off = int(p[2]) if len(p) > 2 and p[2].isdigit() else 0
        aid = int(p[3]) if len(p) > 3 and p[3].lstrip("-").isdigit() else None
        text, markup = await post_rollback_screen(off, aid)
        await edit_html(q, text, markup)

    elif kind == "fbn":
        await edit_html(q, "↩️ Откат поста отменён.", kb([B("🏠 Меню", callback_data="ui:home")]))

    elif kind == "fby":                              # старая кнопка: теперь ведёт на второе подтверждение
        text, markup = await rq_screen("p", int(p[2]), 2)
        await edit_html(q, text, markup)

    elif kind == "rqa":                              # «Да» → просим подтвердить ещё раз
        text, markup = await rq_screen(p[2] if len(p) > 2 and p[2] in ("e", "p") else "e",
                                       int(p[3]) if len(p) > 3 and p[3].isdigit() else 0, 2)
        await edit_html(q, text, markup)

    elif kind == "rqd":                              # второе «Да» → откат
        k = p[2] if len(p) > 2 else ""
        rid = int(p[3]) if len(p) > 3 and p[3].isdigit() else 0
        if k == "e":
            result = await world.rollback_event(rid)
        elif k == "p":
            result = await world.rollback_post(rid)
        else:
            result = "❌ Непонятно, что откатывать."
        await edit_html(q, result, kb(HOME))

    elif kind == "rqn":
        await edit_html(q, "↩️ Откат отменён, ничего не тронуто.", kb(HOME))

    elif kind == "rbn":
        await edit_html(q, "↩️ Откат отменён.", kb([B("🏠 Меню", callback_data="ui:home")]))

    elif kind == "rby":                              # старая кнопка: теперь ведёт на второе подтверждение
        text, markup = await rq_screen("e", int(p[2]), 2)
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


# =====================================================================
# 🕰 ТАЙМЛАЙН
# =====================================================================

def _timeline_line(r: dict) -> str:
    if r["is_verdict"]:
        situation = r["text"].replace("[ВЕРДИКТ]", "").split("→")[0].strip()
        return f"⚖️ <i>{esc(shorten(situation, 110))}</i>"
    return f"▪️ {esc(shorten(r['text'], 170))}"


async def timeline_screen(h: str, page: int):
    t = await find_tag(h)
    if not t:
        return "❌ Тег не найден.", kb([B("⬅️ К списку", callback_data="ui:cs:0")], HOME)
    per = 12
    pages = max(1, (t["cnt"] + per - 1) // per)
    page = min(max(page, 0), pages - 1)
    rows = await db.arun(db.get_timeline, t["tag"], page * per, per)
    lines = [f"🕰 <b>ТАЙМЛАЙН · #{esc(t['tag'])}</b>", f"<i>стр. {page + 1}/{pages} · записей: {t['cnt']}</i>"]
    last = object()
    for r in rows:
        if r["year"] != last:
            last = r["year"]
            lines.append(f"\n📅 <b>{last if last else 'Без даты'}</b>")
        lines.append(_timeline_line(r))
    nav = []
    if page > 0:
        nav.append(B("◀️", callback_data=f"ui:tl:{h}:{page - 1}"))
    nav.append(B(f"{page + 1}/{pages}", callback_data=f"ui:tl:{h}:{page}"))
    if page < pages - 1:
        nav.append(B("▶️", callback_data=f"ui:tl:{h}:{page + 1}"))
    return "\n".join(lines), kb(nav, [B("⬅️ К тегу", callback_data=f"ui:ct:{h}"), HOME[0]])


async def timeline_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    query = " ".join(context.args or []).strip().lower()
    if not query:
        await safe_reply(msg, "Используй: <code>/timeline Россия</code>")
        return
    names = normal_tag_names(await db.arun(db.get_all_tags))
    matched = match_tags(names, query)
    if not matched:
        hints = [n for n in names if query[:3] in n][:8]
        extra = ("\nПохожие теги: " + ", ".join(f"<code>#{esc(n)}</code>" for n in hints)) if hints else ""
        await safe_reply(msg, f"❌ По запросу «{esc(query)}» тегов нет.{extra}")
        return
    tag = query if query in matched else matched[0]
    text, markup = await timeline_screen(tag_hash(tag), 0)
    await safe_reply(msg, text, reply_markup=markup)


# =====================================================================
# ⚔️ СРАВНЕНИЕ СТРАН
# =====================================================================

async def vs_screen(a: str, b: str, y: int):
    y = min(max(y, 1960), datetime.now().year)
    na, nb = ISO_RU.get(a, a), ISO_RU.get(b, b)
    res = await asyncio.gather(*[
        fetch_value(iso, code, y) for _, code, _, _ in VS_METRICS for iso in (a, b)
    ])
    if not any(res):
        return ("❌ World Bank не вернул данных для этих стран. Попробуй другой год.",
                kb([B(f"⏪ {y - 5}", callback_data=f"ui:vs:{a}:{b}:{max(1960, y - 5)}")], HOME))

    w = 12

    def cell(v, kind):
        if not v:
            return "—"
        return format_value(v[0], kind).replace(" чел.", "").replace(" лет", "")

    table = [f"{'':{w}} {shorten(na, 11):<{w}} {shorten(nb, 11):<{w}}"]
    wins = {a: 0, b: 0}
    for i, (label, _code, kind, better) in enumerate(VS_METRICS):
        va, vb = res[2 * i], res[2 * i + 1]
        ma = mb = ""
        if va and vb and va[0] != vb[0]:
            a_wins = (va[0] > vb[0]) if better == "high" else (va[0] < vb[0])
            if a_wins:
                ma, wins[a] = "▲", wins[a] + 1
            else:
                mb, wins[b] = "▲", wins[b] + 1
        table.append(f"{label:<{w}} {cell(va, kind) + ma:<{w}} {cell(vb, kind) + mb:<{w}}")

    if wins[a] == wins[b]:
        verdict = "🤝 Паритет по показателям"
    else:
        lead = a if wins[a] > wins[b] else b
        verdict = f"🏆 Впереди: <b>{esc(ISO_RU.get(lead, lead))}</b> — {max(wins.values())} из {len(VS_METRICS)}"

    names = normal_tag_names(await db.arun(db.get_all_tags))
    counts = {}
    tags = {t["tag"]: t["cnt"] for t in await db.arun(db.get_all_tags)}
    for iso, nm in ((a, na), (b, nb)):
        counts[iso] = sum(tags[t] for t in match_tags(names, nm.lower()))

    text = (
        f"⚔️ <b>{esc(na)} vs {esc(nb)}</b>  ·  📅 {y}\n"
        f"<pre>{esc(chr(10).join(table))}</pre>\n"
        f"{verdict}\n"
        f"📚 Фактов в базе РП: <b>{counts[a]}</b> — <b>{counts[b]}</b>\n"
        "<i>▲ — лучше. Данные World Bank, ближайший доступный год.</i>"
    )
    nav = [B(f"⏪ {max(1960, y - 5)}", callback_data=f"ui:vs:{a}:{b}:{max(1960, y - 5)}"),
           B(f"‹ {max(1960, y - 1)}", callback_data=f"ui:vs:{a}:{b}:{max(1960, y - 1)}"),
           B(f"{y + 1} ›", callback_data=f"ui:vs:{a}:{b}:{y + 1}"),
           B(f"{y + 5} ⏩", callback_data=f"ui:vs:{a}:{b}:{y + 5}")]
    return text, kb(nav, HOME)


async def vs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = " ".join(context.args or [])
    ym = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    rp = get_rp_datetime()
    year = int(ym.group(1)) if ym else (rp["year"] or 2010)
    isos = find_countries(text.replace(ym.group(0), " ") if ym else text)
    if len(isos) < 2:
        await safe_reply(msg, "Используй: <code>/vs Россия США [год]</code>\nНужны две страны из списка World Bank.")
        return
    wait = _vs_cd.hit(update.effective_user.id, 4)
    if wait:
        await safe_reply(msg, f"⏳ Подожди {int(wait) + 1} с.")
        return
    status = await safe_reply(msg, "⏳ <i>Сравниваю страны…</i>")
    text_out, markup = await vs_screen(isos[0], isos[1], year)
    await safe_reply(msg, text_out, reply_markup=markup)
    try:
        await status.delete()
    except Exception:
        pass


# =====================================================================
# 📰 НОВОСТИ · 📈 БИРЖА · 🌡 НАПРЯЖЁННОСТЬ · 🕵️ ОПЕРАЦИИ · 🎲 СОБЫТИЯ
# =====================================================================

KIND_GROUPS = {
    "a": None,
    "t": ["terror", "incident", "shock", "attack", "military", "war", "spy", "coup", "drills", "separatism", "embassy", "leak"],
    "e": ["market", "cyber", "strike", "trade_war", "disaster", "pandemic", "energy", "harvest", "recession", "industrial", "blackout"],
    "s": ["protest", "propaganda", "death", "decree", "corruption", "election", "refugees", "crime"],
    "p": ["diplomacy", "alliance", "discovery", "sport", "culture", "tech", "space", "boom", "aid", "holiday"],
}


async def news_screen(f: str = "a", page: int = 0):
    f = f if f in KIND_GROUPS else "a"
    kinds = KIND_GROUPS[f]
    per = 4
    total = await db.arun(db.count_world_events, kinds)
    pages = max(1, (total + per - 1) // per)
    page = min(max(page, 0), pages - 1)
    rows = await db.arun(db.get_world_events, per, page * per, kinds)
    lines = [hdr("📰", "Мировые новости", f"страница {page + 1} из {pages} · всего {total}"), ""]
    if not rows:
        lines.append("📭 Пока тихо. Админ может включить события: 🛠 → 🎲 События мира.")
    for r in rows:
        head, _, body = r["text"].partition("\n")
        where = ISO_RU.get(r["country"], r["country"] or "")
        year = f", {r['rp_year']}" if r["rp_year"] else ""
        lines.append(f"{EMOJI.get(r['kind'], '📰')} <b>{esc(head)}</b>")
        lines.append(quote(shorten(body, 240)))
        lines.append(f"<i>📍 {esc(where)}{year}</i>\n")
    names = [("a", "Все"), ("t", "🔥 Конфликты"), ("e", "💹 Экономика"), ("s", "👥 Общество"), ("p", "🕊 Позитив")]
    filt = [B(("• " if k == f else "") + n, callback_data=f"ui:nw:{k}:0") for k, n in names]
    nav = []
    if page > 0:
        nav.append(B("◀️", callback_data=f"ui:nw:{f}:{page - 1}"))
    nav.append(B(f"{page + 1}/{pages}", callback_data=f"ui:nw:{f}:{page}"))
    if page < pages - 1:
        nav.append(B("▶️", callback_data=f"ui:nw:{f}:{page + 1}"))
    return "\n".join(lines), kb(filt[:3], filt[3:], nav, HOME)


def market_screen():
    m = world.market()
    lines = [hdr("📈", "Биржа", "игровые котировки"), ""]
    year = get_rp_datetime().get("year") or 2010
    for k, (name, _s, _v, _d) in world.ASSETS.items():
        if not world.asset_active(k, year):          # в 1918-м нет ни биткоина, ни EUR/USD
            continue
        h = m["h"][k]
        ch = world.change_pct(h)
        arrow = "🟢▲" if ch > 0.05 else "🔴▼" if ch < -0.05 else "⚪️▬"
        lines.append(f"{name}  <b>{world.fmt_price(k, h[-1])}</b>  {arrow} {ch:+.1f}%")
        lines.append(f"<code>{world.spark(h[-16:])}</code>")
    lines.append("\n<i>Котировки живут сами и дёргаются от мировых событий.</i>")
    return "\n".join(lines), kb([B("🔄 Обновить", callback_data="ui:mk")], HOME)


def tension_screen():
    t = sorted(world.tension().items(), key=lambda kv: -kv[1])[:12]
    lines = [hdr("🌡", "Напряжённость стран", "чем выше шкала, тем ближе кризис"), ""]
    if world.wars():
        lines += ["⚔️ <b>Войны:</b> " + "; ".join(f"{esc(ISO_RU.get(a, a))} ↔ {esc(ISO_RU.get(b, b))}" for a, b in world.wars()), ""]
    if not t:
        lines.append("🟢 В мире спокойно.")
    for iso, v in t:
        icon, word = level(v)
        lines.append(f"{icon} <b>{esc(ISO_RU.get(iso, iso))}</b> · <i>{word}</i>\n      <code>{bar(v / 100, 10)}</code> {v:.0f}/100")
    lines.append("\n" + quote("Растёт от событий и операций, со временем остывает. Влияет на шансы событий и защиту целей."))
    return "\n".join(lines), kb([B("🔄 Обновить", callback_data="ui:tn")], HOME)


async def ops_screen(user):
    staff = is_staff(user.id)
    limit = C.OP_LIMIT_STAFF if staff else C.OP_LIMIT_PLAYER
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    used = await db.arun(db.get_usage, user.id, today, "op")
    mine = world.mycountry(user.id)
    text = (
        "🕵️ <b>ТАЙНЫЕ ОПЕРАЦИИ</b>\n\n"
        "Напиши команду и <b>опиши операцию своими словами</b> — формат не важен. ИИ-ГМ сам поймёт цель, "
        "место, заказчика и бюджет, оценит весь план (🟢 хороший · 🟡 средний · 🔴 слабый) и посчитает потери.\n"
        "💣 Теракт (в личке): <code>/terror</code>\n🎯 Покушение: <code>/op</code>\n"
        "⚔️ В странах, ведущих войну, шанс выше. В новостях — только должности, без имён.\n\n"
        "▫️ чем сильнее защита цели и меньше бюджет — тем ниже шанс\n"
        "▫️ при провале (и даже при успехе) исполнителей могут взять\n"
        "▫️ заказчика могут раскрыть, назвать чужую страну или не найти следов\n"
        "▫️ итог: отчёт тебе, новость в мировую ленту, журнал — ГМ\n"
        "🛡 Защита страны считается из новостей: напиши в теме фактов "
        "<code>#франция усилил охрану президента</code> — ИИ-ГМ сам оценит, шансы на тебя упадут\n"
        "\n"
        f"🏳️ Твоя страна: <b>{esc(ISO_RU.get(mine, mine)) if mine else 'не задана'}</b> "
        "<i>(/mycountry Россия)</i>\n"
        f"📊 Сегодня: <code>{bar(used / limit if limit else 1)}</code> {used}/{limit}"
    )
    return text, kb([B("🌡 Напряжённость", callback_data="ui:tn")], HOME)


def events_admin_screen():
    mode = db.get_setting("events_mode", "off")
    wc, _ = world_target()
    text = (
        "🎲 <b>СОБЫТИЯ МИРА</b>\n\n"
        f"Режим: <b>{esc(MODE_NAMES.get(mode, mode))}</b>\n"
        f"Тема мировых: {'✅' if wc else '❌ не задана (/saveworld)'}\n\n"
        "Бот сам публикует более 35 видов событий: от биржи, спорта, культуры и технологий до терактов, "
        "эпидемий, дипломатических скандалов и переворотов (самые тяжёлые — реже всего). "
        "В событиях участвуют не только страны с игроками, но и десятки других. Режимы — от тихого (~2 в день) до «Хаоса» (~30 в день).\n"
        "<i>Реальных людей по имени нет — только должности и вымышленные персонажи.</i>\n\n"
        "👇 Выбери вид для разовой генерации, запусти сразу несколько или дай свою идею — бот оформит её сам."
    )
    row = [B(("• " if k == mode else "") + MODE_NAMES[k].split(" (")[0], callback_data=f"ui:evm:{k}") for k in PER_DAY]
    kinds = [B(f"{EVENTS[k]['emoji']} {EVENTS[k]['name']}", callback_data=f"ui:evk:{k}") for k in EVENTS]
    krows = [kinds[i:i + 3] for i in range(0, len(kinds), 3)]
    return text, kb(row[:2], row[2:4], row[4:6], row[6:], *krows,
                    [B("🎲 Случайное", callback_data="ui:evr"), B("🎲×3", callback_data="ui:evb")],
                    [B("💡 Своя идея", callback_data="ui:evi")],
                    [B("⬅️ В админ-панель", callback_data="ui:ad"), HOME[0]])


async def ops_log_screen():
    rows = await db.arun(db.get_ops, 10)
    lines = ["📜 <b>ЖУРНАЛ ГМ · операции</b>", ""]
    if not rows:
        lines.append("Пока пусто.")
    icons = {"killed": "✅", "wounded": "🩹", "failed": "❌", "major": "💥", "partial": "🔸", "foiled": "❌", "success": "✅", "fail": "❌"}
    for r in rows:
        lines.append(f"{icons.get(r['outcome'], '•')} <code>#{r['id']}</code> {esc(ISO_RU.get(r['actor'], r['actor']))} → "
                     f"{esc(ISO_RU.get(r['target'], r['target']))} · {esc(r['role'])} · ${r['budget']:,}\n"
                     f"      <i>{esc(shorten(r['summary'] or '', 90))}</i> · {esc(r['user_name'] or '')}")
    return "\n".join(lines), kb([B("⬅️ В админ-панель", callback_data="ui:ad"), HOME[0]])


async def country_screen(user):
    iso = world.mycountry(user.id)
    if not iso:
        return ("🛡 <b>МОЯ СТРАНА</b>\n\nСтрана не задана.\nУкажи: <code>/mycountry Россия</code>", kb(HOME))
    st = world.cstate(iso)
    tens = world.tension().get(iso, 0.0)
    acts = await db.arun(db.get_player_actions, iso, 3)
    caps = world.CAPS
    rows = [("👑 Охрана высших лиц", "top"), ("🏛 Охрана чиновников", "gov"), ("👥 Охрана прочих", "civil"),
            ("🕵️ Разведка", "intel")]
    lines = [hdr("🛡", f"Моя страна: {ISO_RU.get(iso, iso)}"), "",
             f"🏳️ Базовая защита (задаёт ГМ): <b>{world.security(iso)}</b>/100  ·  общее усиление: <b>{st['sec']:+.0f}</b>",
             f"🌡 Напряжённость: <code>{bar(tens / 100)}</code> {tens:.0f}/100", ""]
    for label, k in rows:
        extra = f" · уровень {world.intel_level(iso)}/5" if k == "intel" else ""
        lines.append(f"{label}{extra}\n      <code>{bar(st[k] / caps[k][1], 10)}</code> {st[k]:.0f}/{caps[k][1]:.0f}")
    if acts:
        lines += ["", "📜 <b>Последние решения:</b>"] + [f"▪️ {esc(shorten(a['summary'] or '', 100))}" for a in acts]
    lines += ["", "<i>Усилить охрану: <code>/action усилил охрану президента</code>. Прокачать разведку: "
                  "<code>/intel 300к</code>. Усиления слабеют со временем.</i>"]
    return "\n".join(lines), kb([B("🔄 Обновить", callback_data="ui:mc")], HOME)


async def rollback_target_view(kind: str, rid: int):
    """Описание того, что откатываем: новость мира ('e') или пост игрока ('p'). None — уже нет в базе."""
    import json as _json
    if kind == "e":
        r = await db.arun(db.get_world_event, rid)
        if not r:
            return None
        head, _, body = r["text"].partition("\n")
        lines = [f"{EMOJI.get(r['kind'], '📰')} <b>{esc(head)}</b>", esc(shorten(body, 320)),
                 f"<i>📍 {esc(ISO_RU.get(r['country'], r['country'] or ''))} · {r['rp_year'] or ''} · новость #{r['id']}</i>"]
        try:
            eff = _json.loads(r.get("effects") or "{}")
        except ValueError:
            eff = {}
        lines.append("<i>Будут отменены: лента, мировой факт" + (", напряжённость, биржа и защита." if eff else
                     " (последствия старой новости не сохранялись).") + "</i>")
        return "\n".join(lines)
    r = await db.arun(db.get_fact, rid)
    if not r:
        return None
    tags = await db.arun(db.get_post_tags, r["author_id"], r["text"])
    return "\n".join([f"👤 <b>{esc(r['author_name'] or 'без ника')}</b> (<code>{r['author_id']}</code>)",
                      f"🏷 {esc(' '.join('#' + t for t in tags) or '#' + r['tag'])} · {r['year'] or 'год не указан'} · пост #{r['id']}",
                      esc(shorten(r["text"], 400)),
                      "<i>Пост исчезнет из базы фактов по всем тегам; если из-за него ГМ менял защиту страны — это тоже отменится.</i>"])


async def rq_screen(kind: str, rid: int, step: int):
    """Двойное подтверждение отката. Шаг 1: «Да/Нет». Шаг 2: «Точно?» — кнопки поменяны местами, чтобы не промахнуться."""
    body = await rollback_target_view(kind, rid)
    if not body:
        return "❌ Уже откачено или не найдено.", kb(HOME)
    if step == 1:
        return (hdr("↩️", "Откатить это?") + "\n" + body,
                kb([B("✅ Да", callback_data=f"ui:rqa:{kind}:{rid}"), B("❌ Нет", callback_data="ui:rqn")]))
    return (hdr("⚠️", "Точно откатить?", "это нельзя отменить") + "\n" + body,
            kb([B("❌ Отмена", callback_data="ui:rqn"), B("⚠️ ДА, ОТКАТИТЬ", callback_data=f"ui:rqd:{kind}:{rid}")]))


async def post_rollback_screen(offset: int = 0, author_id=None):
    """«Откатить этот пост игрока? Да / Нет» — листай кнопками к более старым постам, можно только посты одного автора."""
    offset = max(0, offset)
    rows = await db.arun(db.get_fact_log, 1, offset, author_id)
    who = f" · автор <code>{author_id}</code>" if author_id else ""
    if not rows:
        return f"↩️ <b>ОТКАТ ПОСТОВ</b>{who}\n\nОткатывать нечего — постов нет.", kb(HOME)
    r = rows[0]
    tags = await db.arun(db.get_post_tags, r["author_id"], r["text"])
    tag_line = " ".join("#" + t for t in tags) or "#" + r["tag"]
    lines = ["↩️ <b>Откатить этот пост?</b>" + who, "",
             f"👤 <b>{esc(r['author_name'] or 'без ника')}</b> (<code>{r['author_id']}</code>)",
             f"🏷 {esc(tag_line)} · {r['year'] or 'год не указан'} · #{r['id']}",
             esc(shorten(r["text"], 400)), "",
             "<i>Пост исчезнет из базы фактов по всем тегам. Если ГМ из-за него менял защиту страны — это тоже отменится "
             "(напряжённость не откатывается).</i>"]
    suf = f":{author_id}" if author_id else ""
    nav = []
    if offset > 0:
        nav.append(B("◀️ Новее", callback_data=f"ui:fb:{offset - 1}{suf}"))
    nav.append(B("Старше ▶️", callback_data=f"ui:fb:{offset + 1}{suf}"))
    rows_kb = [[B("✅ Да, откатить", callback_data=f"ui:rqa:p:{r['id']}"), B("❌ Нет", callback_data="ui:fbn")], nav]
    if not author_id and r["author_id"]:
        rows_kb.append([B("👤 Только посты этого автора", callback_data=f"ui:fb:0:{r['author_id']}")])
    return "\n".join(lines), kb(*rows_kb, HOME)


async def rollback_screen(offset: int = 0):
    """«Откатить эту новость? Да / Нет» — листай кнопками к более старым новостям."""
    import json as _json
    offset = max(0, offset)
    rows = await db.arun(db.get_world_events, 1, offset, None)
    if not rows:
        return "↩️ <b>ОТКАТ</b>\n\nОткатывать нечего — в ленте нет новостей.", kb(HOME)
    r = rows[0]
    head, _, body = r["text"].partition("\n")
    try:
        eff = _json.loads(r.get("effects") or "{}")
    except ValueError:
        eff = {}
    lines = ["↩️ <b>Откатить эту новость?</b>", "",
             f"{EMOJI.get(r['kind'], '📰')} <b>{esc(head)}</b>", esc(shorten(body, 320)),
             f"<i>📍 {esc(ISO_RU.get(r['country'], r['country'] or ''))} · {r['rp_year'] or ''} · #{r['id']}</i>", ""]
    if eff:
        bits = [f"🌡 {esc(ISO_RU.get(i, i))} {-d:+.0f}" for i, d in list(eff.get("tension", {}).items())[:4]]
        bits += [f"{world.ASSETS[a][0]} {(-s * 100):+.1f}%" for a, s in eff.get("market", {}).items() if a in world.ASSETS]
        lines.append("<b>Будет отменено:</b> " + (" · ".join(bits) or "—"))
    else:
        lines.append("<i>Для старой новости откатятся только лента и мировой факт.</i>")
    nav = []
    if offset > 0:
        nav.append(B("◀️ Новее", callback_data=f"ui:rb:{offset - 1}"))
    nav.append(B("Старше ▶️", callback_data=f"ui:rb:{offset + 1}"))
    return "\n".join(lines), kb([B("✅ Да, откатить", callback_data=f"ui:rqa:e:{r['id']}"),
                                 B("❌ Нет", callback_data="ui:rbn")], nav, HOME)
