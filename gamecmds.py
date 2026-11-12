"""GAMECMDS.PY — команды «живого мира»: /op /news /market /tension /mycountry /security /event /ops."""

import logging
import re
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

import config as C
import database as db
import actions
import ops
import ui
import world
from auth import is_staff
from commands import staff_only
from events import ALIASES, create_event
from handlers import world_target
from textutils import Cooldown, esc
from tg import safe_reply, thread_id_of
from worldbank import ISO_RU, find_countries

log = logging.getLogger(__name__)
_op_cd = Cooldown()
_act_cd = Cooldown()

OP_USAGE = ("Используй: <code>/op президент США 100к от Франции</code>\n"
            "должность цели · страна цели · бюджет · «от» страна-заказчик\n"
            "(заказчика можно не писать, если задан <code>/mycountry</code>)")


async def op_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    text = " ".join(context.args or []).strip()
    if not text:
        await safe_reply(msg, OP_USAGE)
        return
    op, err = ops.parse_op(text, world.mycountry(user.id))
    if err:
        await safe_reply(msg, f"❌ {esc(err)}.\n\n{OP_USAGE}")
        return

    staff = is_staff(user.id)
    wait = _op_cd.hit(user.id, C.OP_COOLDOWN_STAFF if staff else C.OP_COOLDOWN_PLAYER)
    if wait:
        await safe_reply(msg, f"⏳ Агенты ещё не вернулись. Подожди {int(wait) + 1} с.")
        return
    limit = C.OP_LIMIT_STAFF if staff else C.OP_LIMIT_PLAYER
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if await db.arun(db.get_usage, user.id, today, "op") >= limit:
        _op_cd.reset(user.id)
        await safe_reply(msg, f"⏳ Лимит операций на сегодня исчерпан ({limit}/{limit}).")
        return

    status = await safe_reply(msg, "🕵️ <i>Операция запущена…</i>")
    try:
        report = await ops.execute_op(context.bot, user, op, msg.chat.id, thread_id_of(msg))
    except Exception:
        _op_cd.reset(user.id)
        raise
    await db.arun(db.inc_usage, user.id, today, "op")

    sent = False
    try:
        await context.bot.send_message(user.id, report, parse_mode="HTML")
        sent = True
    except Exception:
        pass
    if sent and msg.chat.type != "private":
        await safe_reply(msg, "🕵️ Операция завершена. Отчёт отправлен тебе в личку, итог — в мировых новостях.")
    elif not sent:
        await safe_reply(msg, report + "\n\n<i>(Напиши боту в личку /start — тогда отчёты приходят лично.)</i>")
    try:
        await status.delete()
    except Exception:
        pass


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = await ui.news_screen("a", 0)
    await safe_reply(update.effective_message, text, reply_markup=markup)


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = ui.market_screen()
    await safe_reply(update.effective_message, text, reply_markup=markup)


async def tension_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = ui.tension_screen()
    await safe_reply(update.effective_message, text, reply_markup=markup)


async def mycountry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    text = " ".join(context.args or [])
    if not text:
        mine = world.mycountry(user.id)
        await safe_reply(msg, f"🏳️ Твоя страна: <b>{esc(ISO_RU.get(mine, mine))}</b>\nСменить: <code>/mycountry Россия</code>"
                         if mine else "🏳️ Страна не задана. Пример: <code>/mycountry Россия</code>")
        return
    isos = find_countries(text)
    if not isos:
        await safe_reply(msg, "❌ Не нашёл такую страну в списке.")
        return
    await db.arun(world.set_mycountry, user.id, isos[0])
    await safe_reply(msg, f"✅ Твоя страна: <b>{esc(ISO_RU.get(isos[0], isos[0]))}</b>")


@staff_only
async def security_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = " ".join(context.args or [])
    isos = find_countries(text)
    if not isos:
        await safe_reply(msg, "Используй: <code>/security Россия 80</code> (0–100, по умолчанию 50)")
        return
    m = re.search(r"\b(\d{1,3})\b", text)
    name = esc(ISO_RU.get(isos[0], isos[0]))
    if not m:
        await safe_reply(msg, f"🛡 Защита страны <b>{name}</b>: {world.security(isos[0])}/100")
        return
    await db.arun(world.set_security, isos[0], int(m.group(1)))
    await safe_reply(msg, f"🛡 Защита страны <b>{name}</b> теперь {world.security(isos[0])}/100")


@staff_only
async def event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = " ".join(context.args or []).lower()
    kind = next((v for k, v in ALIASES.items() if k in text), None)
    isos = find_countries(text)
    if not world_target()[0]:
        await safe_reply(msg, "❌ Сначала задай тему мировых новостей: <code>/saveworld</code> в нужной теме.")
        return
    status = await safe_reply(msg, "⏳ <i>Генерирую событие…</i>")
    r = await create_event(context.bot, kind, isos)
    if r:
        await safe_reply(msg, f"✅ Опубликовано: <b>{esc(r['head'])}</b>")
    else:
        await safe_reply(msg, "❌ Не получилось (нейросеть не ответила). Проверь ключи и лимиты Groq.")
    try:
        await status.delete()
    except Exception:
        pass


@staff_only
async def ops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, markup = await ui.ops_log_screen()
    await safe_reply(update.effective_message, text, reply_markup=markup)


async def action_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    text = " ".join(context.args or []).strip()
    if len(text) < 8:
        await safe_reply(msg, "Используй: <code>/action усилил охрану президента</code>\n"
                              "Опиши словами, что делает твоя страна — нейросеть-ГМ сама оценит эффект.")
        return
    iso = world.mycountry(user.id)
    if not iso:
        await safe_reply(msg, "🏳️ Сначала задай свою страну: <code>/mycountry Россия</code>")
        return
    staff = is_staff(user.id)
    wait = _act_cd.hit(user.id, C.ACTION_COOLDOWN_STAFF if staff else C.ACTION_COOLDOWN_PLAYER)
    if wait:
        await safe_reply(msg, f"⏳ ГМ ещё занят. Подожди {int(wait) + 1} с.")
        return
    limit = C.ACTION_LIMIT_STAFF if staff else C.ACTION_LIMIT_PLAYER
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if await db.arun(db.get_usage, user.id, today, "act") >= limit:
        _act_cd.reset(user.id)
        await safe_reply(msg, f"⏳ Лимит решений на сегодня исчерпан ({limit}/{limit}).")
        return
    status = await safe_reply(msg, "⚖️ <i>ГМ рассматривает решение…</i>")
    try:
        report, ok = await actions.run_action(context.bot, user, iso, text[:500], msg.chat.id, thread_id_of(msg))
    except Exception:
        _act_cd.reset(user.id)
        raise
    if ok:
        await db.arun(db.inc_usage, user.id, today, "act")
    else:
        _act_cd.reset(user.id)
    await safe_reply(msg, report)
    try:
        await status.delete()
    except Exception:
        pass


TERROR_USAGE = ("Используй: <code>/terror Франция 200к от Германии</code>\n"
                "страна цели · бюджет · «от» страна-заказчик (или задай <code>/mycountry</code>)\n"
                "Объект по желанию: <i>транспорт, госучреждение, инфраструктура, площадь</i>")
_terror_cd = Cooldown()


async def terror_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    if msg.chat.type != "private":
        await safe_reply(msg, "🔒 Такие заказы принимаются только в <b>личке</b> с ботом — напиши мне туда.")
        return
    text = " ".join(context.args or []).strip()
    if not text:
        await safe_reply(msg, TERROR_USAGE)
        return
    if not world_target()[0]:
        await safe_reply(msg, "❌ Тема мировых новостей не задана (админ: <code>/saveworld</code> в нужной теме).")
        return
    op, err = ops.parse_op(text, world.mycountry(user.id))
    if err:
        await safe_reply(msg, f"❌ {esc(err)}.\n\n{TERROR_USAGE}")
        return
    staff = is_staff(user.id)
    wait = _terror_cd.hit(user.id, C.TERROR_COOLDOWN_STAFF if staff else C.TERROR_COOLDOWN_PLAYER)
    if wait:
        await safe_reply(msg, f"⏳ Ячейка ещё не готова. Подожди {int(wait) // 60 + 1} мин.")
        return
    limit = C.TERROR_LIMIT_STAFF if staff else C.TERROR_LIMIT_PLAYER
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if await db.arun(db.get_usage, user.id, today, "terror") >= limit:
        _terror_cd.reset(user.id)
        await safe_reply(msg, f"⏳ Лимит заказов на сегодня исчерпан ({limit}/{limit}).")
        return
    status = await safe_reply(msg, "🕵️ <i>Заказ принят…</i>")
    try:
        report = await ops.execute_terror(context.bot, user, op, ops.terror_category(text.lower()))
    except Exception:
        _terror_cd.reset(user.id)
        raise
    await db.arun(db.inc_usage, user.id, today, "terror")
    await safe_reply(msg, report)
    try:
        await status.delete()
    except Exception:
        pass
