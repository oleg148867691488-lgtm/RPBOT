"""GAMECMDS.PY — команды «живого мира»: /op /news /market /tension /mycountry /security /event /ops."""

import logging
import re
import time
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

import config as C
import database as db
import actions
import opsai
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


ORDER_PROMPT = {
    "terror": ("💣 <b>Теракт</b>\n\nОпиши операцию <b>своими словами</b>, одним сообщением: что и где задумано, "
               "кто исполнители, чем располагаете, от лица какой страны действуешь. Формат не важен.\n"
               "ИИ-ГМ сам поймёт весь план и оценит его: 🟢 хороший · 🟡 средний · 🔴 слабый. "
               "Чем лучше проработан план, тем выше шанс.\n<i>Жду твоё сообщение (10 минут).</i>"),
    "assassination": ("🎯 <b>Покушение</b>\n\nОпиши операцию <b>своими словами</b>, одним сообщением: на кого, "
                      "где, как задумано, чем располагаете, от лица какой страны действуешь. Формат не важен.\n"
                      "ИИ-ГМ сам поймёт весь план и оценит его: 🟢 хороший · 🟡 средний · 🔴 слабый. "
                      "Чем лучше проработан план, тем выше шанс.\n<i>Жду твоё сообщение (10 минут).</i>"),
}


async def _start_order(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    """Команда /terror или /op: с текстом — сразу в работу, без текста — ждём описание следующим сообщением."""
    msg = update.effective_message
    if mode == "terror" and msg.chat.type != "private":
        await safe_reply(msg, "🔒 Такие заказы принимаются только в <b>личке</b> с ботом — напиши мне туда.")
        return
    text = " ".join(context.args or []).strip()
    if text:
        await order_from_text(update, context, mode, text)
    elif msg.chat.type == "private":
        context.user_data["pending_order"] = (mode, time.time(), "")
        await safe_reply(msg, ORDER_PROMPT[mode])
    else:
        await safe_reply(msg, "✍️ Напиши <code>/op</code> мне в <b>личку</b> и опиши операцию своими словами "
                              "(или сразу в чате: <code>/op текст</code>).")


async def order_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str, text: str):
    """Описание операции получено (аргументом команды или следующим сообщением)."""
    msg, user = update.effective_message, update.effective_user
    terror = mode == "terror"
    if terror and not world_target()[0]:
        await safe_reply(msg, "❌ Тема мировых новостей не задана (админ: <code>/saveworld</code> в нужной теме).")
        return
    staff = is_staff(user.id)
    cd, limit, kind = ((C.TERROR_COOLDOWN_STAFF if staff else C.TERROR_COOLDOWN_PLAYER,
                        C.TERROR_LIMIT_STAFF if staff else C.TERROR_LIMIT_PLAYER, "terror") if terror else
                       (C.OP_COOLDOWN_STAFF if staff else C.OP_COOLDOWN_PLAYER,
                        C.OP_LIMIT_STAFF if staff else C.OP_LIMIT_PLAYER, "op"))
    wait = _op_cd.hit((user.id, kind), cd)
    if wait:
        await safe_reply(msg, f"⏳ Агенты ещё не вернулись. Подожди {int(wait) // 60 + 1} мин.")
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if await db.arun(db.get_usage, user.id, today, kind) >= limit:
        _op_cd.reset((user.id, kind))
        await safe_reply(msg, f"⏳ Лимит на сегодня исчерпан ({limit}/{limit}).")
        return

    status = await safe_reply(msg, "🕵️ <i>ГМ изучает план…</i>")
    try:
        spec, err = await opsai.parse_order(mode, text[:1800], world.mycountry(user.id))
        if err:                                    # уточняем и ждём дополнение — всё сказанное сохраняется
            _op_cd.reset((user.id, kind))
            if msg.chat.type == "private":
                context.user_data["pending_order"] = (mode, time.time(), text[:1800])
            await safe_reply(msg, f"❓ {esc(err)}.\nДопиши недостающее одним сообщением — я учту всё сказанное.")
            return
        report = await opsai.execute_attack(context.bot, user, spec, msg.chat.id, thread_id_of(msg))
    except Exception:
        _op_cd.reset((user.id, kind))
        raise
    finally:
        try:
            await status.delete()
        except Exception:
            pass
    await db.arun(db.inc_usage, user.id, today, kind)

    if msg.chat.type == "private":
        await safe_reply(msg, report)
        return
    try:
        await context.bot.send_message(user.id, report, parse_mode="HTML")
        await safe_reply(msg, "🕵️ Операция завершена. Отчёт отправлен тебе в личку, итог — в мировых новостях.")
    except Exception:
        await safe_reply(msg, report + "\n\n<i>(Напиши боту в личку /start — тогда отчёты приходят лично.)</i>")


async def op_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_order(update, context, "assassination")


async def terror_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_order(update, context, "terror")


# ---------------- войны ----------------

def _war_persist(a, b, start, year, t):
    ok = world.add_war(a, b) if start else world.end_war(a, b)
    if ok:
        na, nb = ISO_RU.get(a, a), ISO_RU.get(b, b)
        text = f"Идёт война между {na} и {nb}." if start else f"Война между {na} и {nb} завершена, заключён мир."
        db.add_fact(f"world_{na.lower()}", text, 0, "rp_war", year)
        world.save_tension(t)
    return ok


async def _war_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, start: bool):
    from events import publish
    from rptime import get_rp_datetime
    msg = update.effective_message
    isos = find_countries(" ".join(context.args or []))
    if len(isos) < 2:
        await safe_reply(msg, f"Используй: <code>/{'war' if start else 'peace'} Россия Украина</code>")
        return
    a, b = isos[0], isos[1]
    rp = get_rp_datetime()
    async with world.state_lock:
        t = world.tension()
        world.bump(t, a, 15 if start else -20)
        world.bump(t, b, 15 if start else -20)
        ok = await db.arun(_war_persist, a, b, start, rp.get("year"), t)
    na, nb = esc(ISO_RU.get(a, a)), esc(ISO_RU.get(b, b))
    if not ok:
        await safe_reply(msg, "ℹ️ Такая война уже идёт." if start else "ℹ️ Между этими странами войны нет.")
        return
    title = "⚔️ Война" if start else "🕊 Мир"
    text = (f"Между странами {na} и {nb} началась война. Вероятность терактов, диверсий и протестов растёт."
            if start else f"Война между {na} и {nb} завершена.")
    await publish(context.bot, f"🎭 <b>РП-СОБЫТИЕ · {title}</b>\n📍 {na} ↔ {nb}\n\n{text}")
    await safe_reply(msg, f"✅ {title}: {na} ↔ {nb}")


@staff_only
async def war_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _war_toggle(update, context, True)


@staff_only
async def peace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _war_toggle(update, context, False)


async def wars_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    w = world.wars()
    text = ("⚔️ <b>ВОЙНЫ</b>\n\n" + "\n".join(f"• {esc(ISO_RU.get(a, a))} ↔ {esc(ISO_RU.get(b, b))}" for a, b in w)
            if w else "🕊 Сейчас никто ни с кем не воюет.")
    await safe_reply(update.effective_message, text)
