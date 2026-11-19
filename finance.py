"""
FINANCE.PY — деньги шпионажа: агент ранга 3 может выводить часть казны страны (/divert), а выведенное
можно отмыть через другой счёт (/launder). Чем крупнее перевод за раз, тем выше риск: агента могут
спалить, часть денег заморозить, начаться расследование. Мелкими частями безопаснее, но дольше.

Плюс: "слежка" (/compromise) — рискованная попытка агента добыть компромат на чиновников цели вместо
прямой кражи; при частичном провале не проваливает всё, а даёт компромат — он потом ослабляет
контрразведку цели во всех шпионских действиях (см. world.leverage в spy.py).
Агента можно на время "усыпить" (/agent sleep) — он не действует и его не ловят, или повысить до
следующего ранга (/agent promote), если у него уже есть опыт (успешные операции).
"""

import logging
import math
import random
import time

import config as C
import database as db
import ops
import world
from auth import is_staff
from events import build_context, format_event, publish, schedule_followup
from llm import ask
from rptime import get_rp_datetime
from spy import REVEAL_TXT, _gm_log, _reveal
from textutils import esc, parse_json, shorten
from tg import safe_reply
from worldbank import ISO_RU, find_countries

log = logging.getLogger(__name__)

DEFAULT_TREASURY = 20_000_000.0


def treasury(iso: str) -> dict:
    tr = world.get_treasury(iso)
    if not tr:
        world.set_treasury(iso, DEFAULT_TREASURY)
        tr = world.get_treasury(iso)
    return tr


def _active_agent(user_id: int, target: str, min_rank: int = 1):
    agents = [a for a in db.list_agents(user_id) if a["active"] and a["target"] == target
              and a["rank"] >= min_rank and (a.get("dormant_until") or 0) <= time.time()]
    return max(agents, key=lambda a: a["rank"]) if agents else None


def _risk(amount: float, base: float, ci: float) -> float:
    r_amount = min(0.55, 0.15 * math.log10(amount / 10_000 + 1))
    r_share = min(0.3, (amount / max(base, 1.0)) * 3)
    return max(0.02, min(0.9, 0.05 + r_amount + r_share + ci / 300))


# =====================================================================
# /divert — вывод средств из казны страны через агента
# =====================================================================

async def divert_command(update, context):
    msg, user = update.effective_message, update.effective_user
    if msg.chat.type != "private":
        await safe_reply(msg, "🔒 Финансовые операции — только в <b>личке</b> с ботом.")
        return
    args = context.args or []
    if len(args) < 2:
        await safe_reply(msg, "Используй: <code>/divert Россия 500к</code> — увести деньги из казны страны, где "
                              "у тебя есть агент 3 уровня, на свой счёт (можно указать счёт: "
                              "<code>/divert Россия 500к Швейцария</code>).\nНужен агент: <code>/spy</code> → внедрение, ранг 3.")
        return
    isos = find_countries(args[0])
    if not isos:
        await safe_reply(msg, "❌ Не вижу такую страну.")
        return
    target = isos[0]
    amount = ops.parse_budget(" ".join(args[1:2]))
    if not amount or amount < 1000:
        await safe_reply(msg, "❌ Укажи сумму, например <code>500к</code> или <code>2 млн</code>.")
        return
    dest = " ".join(args[2:]).strip() or ISO_RU.get(target, target) + " (собств. счёт)"

    ag = _active_agent(user.id, target, min_rank=3)
    if not ag:
        await safe_reply(msg, f"❌ Нет действующего агента 3 уровня в правительстве страны "
                              f"<b>{esc(ISO_RU.get(target, target))}</b> (спящие и раскрытые не считаются).")
        return

    tr = treasury(target)
    amount = min(amount, tr["cur"] * 0.5)
    if amount < 1000:
        await safe_reply(msg, "❌ В казне почти ничего не осталось брать.")
        return

    t0 = world.tension()
    ci = world.security(target) + world.cstate(target)["sec"] + 0.5 * world.cstate(target)["gov"] \
        + t0.get(target, 0) * 0.1 - world.leverage(user.id, target) * 3
    p_burn = _risk(amount, tr["base"], max(0.0, ci)) * (1.3 - 0.1 * ag["rank"])
    caught = random.random() < max(0.03, min(0.9, p_burn))
    share = amount / max(tr["base"], 1.0)

    async with world.state_lock:
        world.add_treasury(target, -amount)
        if caught:
            clawback = amount * random.uniform(0.3, 0.7)
            world.add_treasury(target, clawback)
            amount -= clawback
        else:
            clawback = 0.0
        if amount > 0:
            await db.arun(db.add_funds, user.id, dest, amount, 0.0)
        t = world.tension()
        world.bump(t, target, min(12.0, share * 40))
        await db.arun(world.save_tension, t)

    report = [f"💰 <b>ВЫВОД СРЕДСТВ</b>\n",
              f"🏳️ Источник: <b>{esc(ISO_RU.get(target, target))}</b> (агент ранга {ag['rank']})",
              f"🏦 Назначение: <b>{esc(dest)}</b>  ·  Запрошено: <b>${amount + clawback if caught else amount:,.0f}</b>".replace(",", " ")]

    if caught:
        await db.arun(db.burn_agent, ag["id"])
        revealed = await _reveal({"actor": "?", "target": target}, random.random() < 0.5)
        scandal = revealed == "sponsor"
        report.append(f"\n🚨 <b>Операцию заметили!</b> ${clawback:,.0f} заморожено и возвращено в казну.".replace(",", " "))
        report.append(f"☠️ Агент раскрыт и выведен из строя.\n{REVEAL_TXT[revealed]}")
        if scandal:
            rp = get_rp_datetime()
            h, b = "Коррупционный скандал", f"В стране {ISO_RU.get(target, target)} раскрыто хищение из казны через внедрённого агента."
            await publish(context.bot, format_event("corruption", [target], rp, h, b))
            report.append("📢 Скандал попал в мировые новости.")
        if amount > 0:
            report.append(f"\n✅ Всё же удалось увести: <b>${amount:,.0f}</b> (грязные) на счёт «{esc(dest)}».".replace(",", " "))
    else:
        report.append(f"\n✅ <b>Успешно.</b> На счёт «{esc(dest)}» зачислено <b>${amount:,.0f}</b> (грязные).".replace(",", " "))
        report.append("<i>Деньги не отмыты — используй /launder, чтобы пустить их в дело.</i>")

    out = "\n".join(report)
    await safe_reply(msg, out)
    await _gm_log(context.bot, user, out.replace("ВЫВОД СРЕДСТВ", f"ВЫВОД СРЕДСТВ · от {esc(user.first_name or user.id)}"))


# =====================================================================
# /launder — отмывание денег через другой счёт
# =====================================================================

async def launder_command(update, context):
    msg, user = update.effective_message, update.effective_user
    if msg.chat.type != "private":
        await safe_reply(msg, "🔒 Финансовые операции — только в <b>личке</b> с ботом.")
        return
    args = context.args or []
    rows = {r["iso"]: r for r in await db.arun(db.get_funds, user.id)}
    if len(args) < 2:
        lines = ["Используй: <code>/launder Швейцария 300к</code> — отмыть грязные деньги со счёта через другой банк."]
        if rows:
            lines.append("\n💰 <b>Твои счета:</b>")
            lines += [f"• «{esc(k)}»: грязных ${v['dirty']:,.0f}, чистых ${v['clean']:,.0f}".replace(",", " ") for k, v in rows.items()]
        await safe_reply(msg, "\n".join(lines))
        return
    src = args[0]
    if src not in rows or rows[src]["dirty"] < 1:
        await safe_reply(msg, f"❌ На счёте «{esc(src)}» нет грязных денег.")
        return
    amount = min(ops.parse_budget(" ".join(args[1:])) or 0, rows[src]["dirty"])
    if amount < 1000:
        await safe_reply(msg, "❌ Укажи сумму не меньше 1000, не превышающую остаток на счёте.")
        return

    fee = min(0.35, 0.15 + 0.10 * math.log10(amount / 50_000 + 1))
    risk = min(0.4, 0.08 * math.log10(amount / 20_000 + 1))
    caught = random.random() < max(0.02, risk)
    clean = amount * (1 - fee)

    if caught:
        lost = amount * random.uniform(0.3, 0.6)
        await db.arun(db.add_funds, user.id, src, -lost, 0.0)
        out = (f"🏦 <b>ОТМЫВАНИЕ · {esc(src)}</b>\n\n🚨 Банк заподозрил неладное и заблокировал часть перевода.\n"
               f"❌ Потеряно: <b>${lost:,.0f}</b>. Остаток грязных вернулся на счёт.".replace(",", " "))
    else:
        await db.arun(db.add_funds, user.id, src, -amount, clean)
        out = (f"🏦 <b>ОТМЫВАНИЕ · {esc(src)}</b>\n\n✅ Отмыто <b>${amount:,.0f}</b> → получено "
               f"<b>${clean:,.0f}</b> чистыми (комиссия {fee * 100:.0f}%).".replace(",", " "))
    await safe_reply(msg, out)


async def funds_command(update, context):
    msg = update.effective_message
    if msg.chat.type != "private":
        await safe_reply(msg, "🔒 Счета показываются только в личке с ботом.")
        return
    rows = await db.arun(db.get_funds, update.effective_user.id)
    if not rows:
        await safe_reply(msg, "💰 У тебя пока нет никаких счетов. Начни с <code>/divert</code>.")
        return
    lines = ["💰 <b>ТВОИ СЧЕТА</b>\n"] + [
        f"🏦 «{esc(r['iso'])}»: грязных <b>${r['dirty']:,.0f}</b>, чистых <b>${r['clean']:,.0f}</b>".replace(",", " ")
        for r in rows]
    await safe_reply(msg, "\n".join(lines))


# =====================================================================
# /compromise — рискованная слежка ради компромата (а не прямой кражи)
# =====================================================================

async def compromise_command(update, context):
    msg, user = update.effective_message, update.effective_user
    if msg.chat.type != "private":
        await safe_reply(msg, "🔒 Такие операции — только в личке с ботом.")
        return
    text = " ".join(context.args or [])
    isos = find_countries(text)
    if not isos:
        await safe_reply(msg, "Используй: <code>/compromise Россия</code> — агент (любого ранга в этой стране) "
                              "попробует добыть компромат на чиновников вместо прямой кражи.")
        return
    target = isos[0]
    ag = _active_agent(user.id, target)
    if not ag:
        await safe_reply(msg, f"❌ Нет действующего агента в правительстве <b>{esc(ISO_RU.get(target, target))}</b>.")
        return
    t0 = world.tension()
    ci = max(0.0, world.security(target) + world.cstate(target)["sec"] + 0.5 * world.cstate(target)["gov"]
             + t0.get(target, 0) * 0.1 - world.leverage(user.id, target) * 3)
    p_ok = max(0.1, min(0.7, 0.35 + 0.05 * ag["rank"] - ci / 300))
    r = random.random()
    tn = ISO_RU.get(target, target)
    if r < p_ok:
        await db.arun(world.add_leverage, user.id, target, 1)
        out = (f"🕵️ <b>КОМПРОМАТ · {esc(tn)}</b>\n\n✅ Агент добыл материал на местных чиновников.\n"
               f"🗝 Компромат: <b>{world.leverage(user.id, target)}/5</b> — ослабляет контрразведку этой страны во всех "
               "будущих шпионских операциях против неё.")
    elif r < p_ok + 0.25:
        out = f"🕵️ <b>КОМПРОМАТ · {esc(tn)}</b>\n\n🔸 Ничего существенного найти не удалось в этот раз."
    else:
        await db.arun(db.burn_agent, ag["id"])
        out = f"🕵️ <b>КОМПРОМАТ · {esc(tn)}</b>\n\n❌ Агент попался при сборе материала и выведен из строя."
    await safe_reply(msg, out)
    await _gm_log(context.bot, user, out)


# =====================================================================
# /agent sleep · /agent promote
# =====================================================================

async def agent_manage_command(update, context):
    msg, user = update.effective_message, update.effective_user
    args = context.args or []
    if len(args) < 2 or not args[1].isdigit():
        await safe_reply(msg, "Используй: <code>/agent sleep ID часы</code> или <code>/agent promote ID</code>\n"
                              "(ID смотри в /agents)")
        return
    agent_id = int(args[1])
    ag = await db.arun(db.get_agent, agent_id)
    if not ag or ag["owner_id"] != user.id:
        await safe_reply(msg, "❌ Это не твой агент (или такого нет).")
        return
    if args[0] == "sleep":
        hours = float(args[2]) if len(args) > 2 and args[2].replace(".", "", 1).isdigit() else 6.0
        hours = max(1.0, min(72.0, hours))
        await db.arun(db.set_dormant, agent_id, time.time() + hours * 3600)
        await safe_reply(msg, f"😴 Агент «залёг на дно» на {hours:.0f} ч. Не действует, но его и не ловят.")
    elif args[0] == "promote":
        if ag["rank"] >= 3:
            await safe_reply(msg, "ℹ️ Уже максимальный ранг (3).")
            return
        p_ok = 0.5 - 0.1 * ag["rank"]
        if random.random() < p_ok:
            await db.arun(db.set_agent_rank, agent_id, ag["rank"] + 1)
            await safe_reply(msg, f"🎉 Агент повышен до ранга <b>{ag['rank'] + 1}/3</b>.")
        else:
            burned = random.random() < 0.3
            if burned:
                await db.arun(db.burn_agent, agent_id)
                await safe_reply(msg, "❌ Попытка продвижения провалилась, агент попал под подозрение и выведен из строя.")
            else:
                await safe_reply(msg, "❌ Повышение не удалось в этот раз, можно попробовать снова позже.")
    else:
        await safe_reply(msg, "Используй: <code>/agent sleep ID часы</code> или <code>/agent promote ID</code>")
