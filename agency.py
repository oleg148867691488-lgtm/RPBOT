"""
AGENCY.PY — собственное разведывательное агентство игрока.

• /hire — агентов нужно НАНИМАТЬ за деньги: приходят кандидаты с резюме (имя, прошлое, навыки, лояльность, цена).
• /train — навыки можно прокачивать за деньги: Внедрение, Скрытность, Аналитика, Финансы, Техника (до 10).
• /hq — прокачка самого «здания»: Штаб (больше мест), Технический отдел (успех операций), Шифровальный отдел
  (меньше риск провала), Академия (дешевле обучение, сильнее кандидаты). Уровни постоянные — не слабеют.
• /fire — уволить агента; /agents — вся агентура, штаб и счета.
Платить можно только ЧИСТЫМИ деньгами (их добывают через /divert + /launder; новичку выдаётся стартовый бюджет).
"""

import json
import logging
import random
import time

import database as db
import ops
from llm import ask
from textutils import esc, parse_json, shorten
from tg import safe_reply
from worldbank import ISO_RU

log = logging.getLogger(__name__)

STARTER = 3_000_000.0
POOL_TTL = 12 * 3600
SKILLS = {"infiltration": "Внедрение", "stealth": "Скрытность", "analysis": "Аналитика", "finance": "Финансы", "tech": "Техника"}
SHORT = {"infiltration": "Внедр.", "stealth": "Скрыт.", "analysis": "Аналит.", "finance": "Фин.", "tech": "Техн."}
SKILL_ALIAS = {"внедр": "infiltration", "infil": "infiltration", "скрыт": "stealth", "steal": "stealth", "аналит": "analysis",
               "analy": "analysis", "финанс": "finance", "fin": "finance", "техн": "tech", "tech": "tech"}
HQ_TRACKS = {
    "hq": ("🏢 Штаб-квартира", 400_000, "+2 места для агентов за уровень"),
    "tech": ("🔬 Технический отдел", 500_000, "+2% к успеху операций за уровень"),
    "cipher": ("🔐 Шифровальный отдел", 450_000, "−6% к риску провала за уровень"),
    "academy": ("🎓 Академия", 350_000, "−10% к цене обучения, кандидаты сильнее"),
}
HQ_ALIAS = {"штаб": "hq", "hq": "hq", "тех": "tech", "tech": "tech", "шифр": "cipher", "cipher": "cipher", "академ": "academy", "academy": "academy"}
MAX_LEVEL, MAX_SKILL = 5, 10

FIRST_M = ["Андрей", "Виктор", "Павел", "Станислав", "Георгий", "Артём", "Тимур", "Роман", "Игорь", "Леонид"]
FIRST_F = ["Ольга", "Мария", "Ирина", "Елена", "Наталья", "Лидия", "Вера", "Софья", "Анна", "Дарья"]
LAST_M = ["Волков", "Орлов", "Морозов", "Зайцев", "Ермаков", "Ковалёв", "Беляев", "Гусев", "Савельев", "Комаров"]
LAST_F = ["Соколова", "Лебедева", "Крылова", "Фомина", "Власова", "Тарасова", "Никитина", "Мельникова", "Романова", "Журавлёва"]
BACKGROUNDS = [
    ("бывший таможенный инспектор", "infiltration"), ("помощник дипломата", "stealth"), ("банковский аналитик", "finance"),
    ("шифровальщик связи", "tech"), ("журналист-международник", "analysis"), ("инженер оборонного НИИ", "tech"),
    ("архивариус министерства", "infiltration"), ("следователь по экономическим делам", "finance"),
    ("переводчик при посольстве", "analysis"), ("бывший офицер контрразведки", "stealth"),
]


# ---------------------------------------------------------------- навыки и бонусы

def parse_skills(raw) -> dict:
    try:
        j = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        j = {}
    out = {}
    for k in SKILLS:
        try:
            out[k] = max(0, min(MAX_SKILL, int(j.get(k, 0) or 0)))
        except (TypeError, ValueError):
            out[k] = 0
    return out


def skills_line(sk: dict) -> str:
    return " · ".join(f"{SHORT[k]} {sk[k]}" for k in SKILLS)


async def best_skill(owner_id: int, skill: str) -> int:
    rows = list(await db.arun(db.list_recruits, owner_id)) + [a for a in await db.arun(db.list_agents, owner_id) if a["active"]]
    return max([parse_skills(r.get("skills"))[skill] for r in rows] or [0])


async def op_bonus(owner_id: int, skill: str) -> float:
    """Прибавка к шансу успеха: технический отдел + лучший агент по нужному навыку."""
    hq = await db.arun(db.get_hq, owner_id)
    return 0.02 * hq["tech"] + 0.015 * await best_skill(owner_id, skill)


def risk_factor(cipher: int, stealth: int) -> float:
    """Множитель риска провала (1.0 — без бонусов): шифровальный отдел и скрытность агента снижают его."""
    return max(0.3, 1 - 0.06 * cipher) * max(0.4, 1 - 0.05 * stealth)


async def agent_risk_mult(ag: dict, cache: dict = None) -> float:
    cache = cache if cache is not None else {}
    owner = ag["owner_id"]
    if owner not in cache:
        cache[owner] = (await db.arun(db.get_hq, owner))["cipher"]
    return risk_factor(cache[owner], parse_skills(ag.get("skills"))["stealth"])


# ---------------------------------------------------------------- кандидаты

def gen_candidate(academy: int, rng=random) -> dict:
    bg, spec = rng.choice(BACKGROUNDS)
    skills = {k: max(1, min(8, round(rng.gauss(3 + 0.4 * academy, 1.1)))) for k in SKILLS}
    skills[spec] = min(MAX_SKILL, skills[spec] + rng.randint(2, 4))
    loyalty = rng.randint(30, 90)
    price = int((60_000 + 30_000 * sum(skills.values()) * (1 + loyalty / 300)) / 1000) * 1000
    female = rng.random() < 0.5
    name = (f"{rng.choice(FIRST_F)} {rng.choice(LAST_F)}" if female else f"{rng.choice(FIRST_M)} {rng.choice(LAST_M)}")
    return {"name": name, "background": bg, "skills": json.dumps(skills), "loyalty": loyalty, "price": price, "bio": ""}


def _template_bio(c: dict) -> str:
    sk = parse_skills(c["skills"])
    top = max(sk, key=sk.get)
    mood = "надёжен и немногословен" if c["loyalty"] >= 65 else "амбициозен, но на него не всегда можно положиться"
    return f"{c['background'].capitalize()}. Сильная сторона — {SKILLS[top].lower()}. {mood.capitalize()}."


async def write_bios(cands: list):
    """Короткие резюме пишет нейросеть (если не ответила — шаблон)."""
    payload = [{"имя": c["name"], "прошлое": c["background"], "навыки": parse_skills(c["skills"]), "лояльность": c["loyalty"]} for c in cands]
    raw = await ask("summary", [
        {"role": "system", "content": (
            "Ты — кадровик разведслужбы РП-игры. Для каждого кандидата напиши краткое резюме (2 предложения, до 200 символов): "
            "биография и характер по данным; лояльность 30-50 — ненадёжный, 51-70 — обычный, 71+ — преданный. Не используй реальных "
            'людей. Ответь ТОЛЬКО JSON: {"bios": ["...", ...]} в том же порядке.')},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], temperature=0.8)
    bios = (parse_json(raw) or {}).get("bios")
    bios = bios if isinstance(bios, list) else []
    for i, c in enumerate(cands):
        c["bio"] = shorten(str(bios[i]), 220) if i < len(bios) and bios[i] else _template_bio(c)


# ---------------------------------------------------------------- деньги

def _starter(uid: int) -> bool:
    if db.get_setting(f"starter_{uid}"):
        return False
    db.add_funds(uid, "Бюджет разведки", 0.0, STARTER)
    db.set_setting(f"starter_{uid}", "1")
    return True


async def clean_total(uid: int) -> float:
    return sum(r["clean"] for r in await db.arun(db.get_funds, uid))


def usd(x: float) -> str:
    return f"${x:,.0f}".replace(",", " ")


async def _capacity(uid: int):
    hq = await db.arun(db.get_hq, uid)
    owned = len(await db.arun(db.list_recruits, uid)) + len([a for a in await db.arun(db.list_agents, uid) if a["active"]])
    return hq, owned, 3 + 2 * hq["hq"]


def _ref(text: str):
    t = (text or "").strip().upper()
    if t[:1] in ("A", "R") and t[1:].isdigit():
        return t[0], int(t[1:])
    if t.isdigit():
        return "A", int(t)
    return None, 0


async def _private(update) -> bool:
    msg = update.effective_message
    if msg.chat.type != "private":
        await safe_reply(msg, "🔒 Это закрытая информация — только в <b>личке</b> с ботом.")
        return False
    return True


def _card(c: dict, idx: int = None) -> str:
    sk = parse_skills(c["skills"])
    head = f"👤 <b>{('#' + str(idx) + ' ') if idx else ''}{esc(c['name'])}</b>"
    price = f" · цена <b>{usd(c['price'])}</b>" if c.get("price") else ""
    return (f"{head}{price}\n   <i>{esc(c.get('bio') or '')}</i>\n   {skills_line(sk)} · лояльность {c.get('loyalty', 50)}")


# ---------------------------------------------------------------- команды

async def hire_command(update, context):
    msg, user = update.effective_message, update.effective_user
    if not await _private(update):
        return
    starter = await db.arun(_starter, user.id)
    args = context.args or []
    hq, owned, cap = await _capacity(user.id)
    if args and args[0].lower() in ("new", "нов", "новые"):
        if not await db.arun(db.spend_clean, user.id, 50_000):
            await safe_reply(msg, "❌ Обновить список кандидатов стоит $50 000 чистыми — не хватает денег.")
            return
        await db.arun(db.clear_candidates, user.id)
    pool = await db.arun(db.get_candidates, user.id, time.time() - POOL_TTL)
    if args and args[0].isdigit():
        idx = int(args[0])
        if not pool or not 1 <= idx <= len(pool):
            await safe_reply(msg, "❌ Нет кандидата с таким номером. Список: <code>/hire</code>")
            return
        if owned >= cap:
            await safe_reply(msg, f"❌ В агентстве нет мест ({owned}/{cap}). Прокачай штаб: <code>/hq</code> или уволи: <code>/fire</code>.")
            return
        c = pool[idx - 1]
        if not await db.arun(db.spend_clean, user.id, c["price"]):
            await safe_reply(msg, f"❌ Не хватает чистых денег: нужно {usd(c['price'])}, у тебя {usd(await clean_total(user.id))}.")
            return
        rid = await db.arun(db.add_recruit, user.id, c["name"], c["bio"], c["skills"], c["loyalty"])
        await db.arun(db.delete_candidate, c["id"])
        await safe_reply(msg, f"✅ <b>Нанят:</b> {esc(c['name'])} (резерв <code>R{rid}</code>)\n{_card(c)}\n\n"
                              "Назначить на задание — <code>/spy</code> (внедрить в правительство). Учить — <code>/train R" + str(rid) + " навык</code>.")
        return
    if not pool:
        cands = [gen_candidate(hq["academy"]) for _ in range(3)]
        await write_bios(cands)
        await db.arun(db.clear_candidates, user.id)
        await db.arun(db.add_candidates, user.id, cands)
        pool = await db.arun(db.get_candidates, user.id, 0)
    lines = ["🧑‍💼 <b>КАНДИДАТЫ</b>", f"💰 Чистые деньги: <b>{usd(await clean_total(user.id))}</b> · мест в агентстве: {owned}/{cap}"]
    if starter:
        lines.append(f"🎁 <i>Стартовый бюджет разведки: {usd(STARTER)} чистыми.</i>")
    lines += ["", *[_card(c, i) for i, c in enumerate(pool, 1)], "",
              "Нанять: <code>/hire 2</code> · новый список ($50 000): <code>/hire new</code>"]
    await safe_reply(msg, "\n".join(lines))


async def train_command(update, context):
    msg, user = update.effective_message, update.effective_user
    if not await _private(update):
        return
    args = context.args or []
    kind, rid = _ref(args[0]) if args else (None, 0)
    skill = next((v for k, v in SKILL_ALIAS.items() if len(args) > 1 and args[1].lower().startswith(k)), None)
    if not kind or not skill:
        await safe_reply(msg, "Используй: <code>/train A5 скрытность</code> или <code>/train R2 техника</code>\n"
                              "Навыки: внедрение, скрытность, аналитика, финансы, техника. ID смотри в /agents.")
        return
    row = await db.arun(db.get_agent if kind == "A" else db.get_recruit, rid)
    if not row or (row.get("owner_id") != user.id):
        await safe_reply(msg, "❌ Это не твой агент (или такого нет).")
        return
    sk = parse_skills(row.get("skills"))
    if sk[skill] >= MAX_SKILL:
        await safe_reply(msg, f"ℹ️ Навык «{SKILLS[skill]}» уже на максимуме ({MAX_SKILL}).")
        return
    hq = await db.arun(db.get_hq, user.id)
    cost = int(100_000 * 1.6 ** sk[skill] * (1 - 0.1 * hq["academy"]) / 1000) * 1000
    if not await db.arun(db.spend_clean, user.id, cost):
        await safe_reply(msg, f"❌ Не хватает чистых денег: обучение стоит {usd(cost)}, у тебя {usd(await clean_total(user.id))}.")
        return
    sk[skill] += 1
    await db.arun(db.set_agent_skills if kind == "A" else db.set_recruit_skills, rid, json.dumps(sk))
    await safe_reply(msg, f"🎓 <b>{esc(row.get('name') or 'Агент')}</b>: «{SKILLS[skill]}» → <b>{sk[skill]}/{MAX_SKILL}</b> (−{usd(cost)})")


async def hq_command(update, context):
    msg, user = update.effective_message, update.effective_user
    if not await _private(update):
        return
    await db.arun(_starter, user.id)
    hq = await db.arun(db.get_hq, user.id)
    args = context.args or []
    if len(args) >= 2 and args[0].lower() in ("up", "upgrade", "улучшить", "прокачать"):
        track = next((v for k, v in HQ_ALIAS.items() if args[1].lower().startswith(k)), None)
        if not track:
            await safe_reply(msg, "❌ Не понял, что улучшать: штаб, техотдел, шифровальный отдел или академию.")
            return
        lvl = hq[track]
        if lvl >= MAX_LEVEL:
            await safe_reply(msg, "ℹ️ Это уже максимальный уровень.")
            return
        cost = int(HQ_TRACKS[track][1] * 1.9 ** lvl / 1000) * 1000
        if not await db.arun(db.spend_clean, user.id, cost):
            await safe_reply(msg, f"❌ Не хватает чистых денег: нужно {usd(cost)}, у тебя {usd(await clean_total(user.id))}.")
            return
        await db.arun(db.set_hq_level, user.id, track, lvl + 1)
        hq[track] = lvl + 1
        await safe_reply(msg, f"🏗 <b>{HQ_TRACKS[track][0]}</b> → уровень <b>{lvl + 1}/{MAX_LEVEL}</b> (−{usd(cost)})")
        return
    lines = ["🏛 <b>ШТАБ АГЕНТСТВА</b>", f"💰 Чистые деньги: <b>{usd(await clean_total(user.id))}</b>", ""]
    for k, (title, base, eff) in HQ_TRACKS.items():
        lvl = hq[k]
        nxt = "макс." if lvl >= MAX_LEVEL else usd(int(base * 1.9 ** lvl / 1000) * 1000)
        lines.append(f"{title} · <code>{'▰' * lvl}{'▱' * (MAX_LEVEL - lvl)}</code> {lvl}/{MAX_LEVEL}\n   <i>{eff}</i> · след. уровень: {nxt}")
    lines += ["", "Улучшить: <code>/hq up техотдел</code> (штаб · техотдел · шифр · академия)",
              "<i>Уровни штаба и разведка страны — постоянные, со временем не слабеют.</i>"]
    await safe_reply(msg, "\n".join(lines))


async def fire_command(update, context):
    msg, user = update.effective_message, update.effective_user
    if not await _private(update):
        return
    kind, rid = _ref((context.args or [""])[0])
    if not kind:
        await safe_reply(msg, "Используй: <code>/fire A5</code> или <code>/fire R2</code> (ID — в /agents)")
        return
    row = await db.arun(db.get_agent if kind == "A" else db.get_recruit, rid)
    if not row or row.get("owner_id") != user.id:
        await safe_reply(msg, "❌ Это не твой агент (или такого нет).")
        return
    if kind == "A":
        await db.arun(db.burn_agent, rid)
    else:
        await db.arun(db.delete_recruit, rid)
    await safe_reply(msg, f"🚪 {esc(row.get('name') or 'Агент')} уволен.")


async def agents_command(update, context):
    msg, user = update.effective_message, update.effective_user
    if not await _private(update):
        return
    await db.arun(_starter, user.id)
    hq, owned, cap = await _capacity(user.id)
    planted = [a for a in await db.arun(db.list_agents, user.id) if a["active"]]
    recruits = await db.arun(db.list_recruits, user.id)
    lines = [f"🕴 <b>ТВОЁ АГЕНТСТВО</b> · мест {owned}/{cap} · 💰 {usd(await clean_total(user.id))}"]
    if planted:
        lines += ["", "<b>В правительствах:</b>"]
        for a in planted[:12]:
            sk = parse_skills(a.get("skills"))
            asleep = " 😴" if (a.get("dormant_until") or 0) > time.time() else ""
            lines.append(f"<code>A{a['id']}</code> {esc(a.get('name') or 'Агент')}{asleep} → {esc(ISO_RU.get(a['target'], a['target']))}, "
                         f"ранг {a['rank']}/3, лояльн. {a.get('loyalty') or 50}\n   {skills_line(sk)}")
    if recruits:
        lines += ["", "<b>В резерве:</b>"]
        for r in recruits[:8]:
            lines.append(f"<code>R{r['id']}</code> {esc(r['name'])} · {skills_line(parse_skills(r['skills']))} · лояльн. {r['loyalty']}")
    if not planted and not recruits:
        lines.append("\nПока никого нет. Нанять: <code>/hire</code>")
    lines += ["", f"Штаб: 🏢{hq['hq']} 🔬{hq['tech']} 🔐{hq['cipher']} 🎓{hq['academy']} — <code>/hq</code>",
              "Нанять <code>/hire</code> · учить <code>/train</code> · уволить <code>/fire</code> · спать <code>/agent sleep A5 6</code>"]
    await safe_reply(msg, "\n".join(lines)[:3900])


async def givefunds_command(update, context):
    from auth import is_staff
    msg = update.effective_message
    if not is_staff(update.effective_user.id):
        await safe_reply(msg, "❌ Только для админов.")
        return
    args = context.args or []
    amount = ops.parse_budget(" ".join(args[1:])) if len(args) > 1 else 0
    if not args or not args[0].isdigit() or not amount:
        await safe_reply(msg, "Используй: <code>/givefunds ID_игрока 5млн</code> — выдать чистые деньги разведки.")
        return
    await db.arun(db.add_funds, int(args[0]), "Бюджет разведки", 0.0, float(amount))
    await safe_reply(msg, f"✅ Игроку <code>{args[0]}</code> выдано {usd(amount)} чистыми.")
