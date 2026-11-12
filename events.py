"""
EVENTS.PY — генератор мировых РП-событий.

Бот сам публикует в «тему мировых новостей» (/saveworld): теракты (редко), кибератаки, движения курса и
криптобиржи, митинги, забастовки, пропаганду, утраты (вымышленные деятели), инциденты-«казусы белли»
(очень редко) и мировые шоки (ещё реже). События меняют напряжённость стран и котировки биржи,
а текст сохраняется как мировой факт — поэтому /verdict и ответы бота их учитывают.

Правила безопасности (зашиты в промпт): реальных людей по имени нет — только должности и вымышленные
персонажи; никаких инструкций и подробностей насилия; все посты помечены «🎭 РП-событие».
"""

import asyncio
import logging
import random
import time

from telegram.constants import ParseMode

import config as C
import database as db
import world
from handlers import normal_tag_names, world_target
from llm import ask
from rptime import get_rp_datetime
from textutils import esc, shorten
from worldbank import ISO_RU, find_countries

log = logging.getLogger(__name__)

EVENTS = {
    "terror": dict(emoji="🕯", name="Теракт", weight=0.8, sev=(2, 5), two=False, tension=18,
                   shocks={"gold": .02, "oil": .015, "crypto": -.03},
                   brief="террористический акт (без деталей исполнения), реакция властей и общества"),
    "cyber": dict(emoji="💻", name="Кибератака", weight=4, sev=(1, 4), two=False, tension=4,
                  shocks={"crypto": -.015},
                  brief="хакерская атака на госструктуры или крупную компанию, последствия для сервисов (без технических деталей взлома)"),
    "market": dict(emoji="📈", name="Рынки", weight=5, sev=(1, 4), two=False, tension=0, shocks=None,
                   brief="резкое движение на бирже (курс валюты или криптобиржа), причины и реакция рынка"),
    "protest": dict(emoji="✊", name="Митинги", weight=5, sev=(1, 4), two=False, tension=6, shocks={},
                    brief="массовые митинги и протесты (экономика, политика или реформы)"),
    "strike": dict(emoji="🪧", name="Забастовка", weight=4, sev=(1, 3), two=False, tension=4, shocks={"oil": .008},
                   brief="забастовка профсоюзов, остановка отрасли или транспорта"),
    "propaganda": dict(emoji="📣", name="Пропаганда", weight=3, sev=(1, 3), two=True, tension=5, shocks={},
                       brief="информационная кампания госСМИ первой страны против второй (без цитат реальных людей)"),
    "death": dict(emoji="🕊", name="Утрата", weight=1.5, sev=(1, 3), two=False, tension=1, shocks={},
                  brief="смерть ВЫМЫШЛЕННОГО известного деятеля (учёный, артист, бывший министр, генерал); "
                        "это НЕ глава государства и НЕ реальный человек; причина естественная или несчастный случай"),
    "incident": dict(emoji="⚠️", name="Инцидент", weight=0.4, sev=(3, 5), two=True, tension=22,
                     shocks={"oil": .03, "gold": .02},
                     brief="пограничный или морской инцидент, способный стать казусом белли "
                           "(например, береговая охрана первой страны задержала судно второй); без подробностей боевых действий"),
    "shock": dict(emoji="🌐", name="Мировой шок", weight=0.15, sev=(5, 5), two=False, tension=10,
                  shocks={"gold": .06, "oil": .05, "crypto": -.08},
                  brief="крупнейший за десятилетие мировой кризис (масштабный теракт или потрясение, меняющее политику многих стран); без графических подробностей"),
}
EMOJI = {k: v["emoji"] for k, v in EVENTS.items()}
EMOJI["attack"] = "🎯"
EMOJI["decree"] = "🏛"

ALIASES = {
    "теракт": "terror", "терракт": "terror", "кибер": "cyber", "хакер": "cyber", "взлом": "cyber",
    "рынок": "market", "биржа": "market", "курс": "market", "крипт": "market",
    "митинг": "protest", "протест": "protest", "забастов": "strike", "пропаганд": "propaganda",
    "смерть": "death", "утрата": "death", "инцидент": "incident", "казус": "incident", "шок": "shock",
}
PER_DAY = {"off": 0, "calm": 2, "normal": 5, "hot": 10}
MODE_NAMES = {"off": "⏸ Выключены", "calm": "😴 Тихо (~2/день)", "normal": "📰 Норма (~5/день)", "hot": "🔥 Жарко (~10/день)"}

DEFAULT_COUNTRIES = ["RUS", "USA", "CHN", "DEU", "FRA", "GBR", "JPN", "IND", "BRA", "TUR"]
_last_event = 0.0
_queue: list = []   # отложенные последствия: (когда, тип, страны)

SYSTEM_PROMPT = (
    "Ты — редактор ВЫМЫШЛЕННОЙ новостной ленты ролевой геополитической игры (альтернативная история, {year} год). "
    "Пиши как короткую новостную заметку на русском: первая строка — заголовок до 90 символов, затем пустая строка "
    "и 2–4 предложения текста. ЖЁСТКИЕ ПРАВИЛА: не называй реальных людей по имени — только должности; "
    "если нужен персонаж, придумай вымышленное имя и не связывай его с реальным человеком; "
    "не приписывай слова реальным людям; не описывай способы насилия, взлома или изготовления чего-либо — "
    "никаких инструкций и натуралистичных подробностей; не называй точное число жертв больше порядка величины. "
    "Не добавляй пометок вроде «вымышлено» — их добавит система. Только заметка, без комментариев."
)


async def play_countries() -> list:
    """Страны, которые реально участвуют в РП (по тегам в базе)."""
    isos = []
    for row in await db.arun(db.get_all_tags):
        if row["tag"].startswith(("world_", "игрок_")):
            continue
        for iso in find_countries(row["tag"]):
            if iso not in isos:
                isos.append(iso)
    return isos if len(isos) >= 3 else DEFAULT_COUNTRIES


def _pick(pool: list, t: dict, exclude=()) -> str:
    items = [c for c in pool if c not in exclude]
    return random.choices(items, weights=[1 + t.get(c, 0) / 25 for c in items])[0]


def _market_shock(iso: str, sev: int):
    asset = world.CURRENCY_OF.get(iso, "crypto")
    pct = (0.02 * sev) * (3 if asset == "crypto" else 1)
    sign = random.choice([-1, 1])
    return asset, sign * pct


def _name(iso: str) -> str:
    return ISO_RU.get(iso, iso)


async def generate_text(ev: dict, kind: str, isos: list, sev: int, rp_year, extra: str):
    facts = await db.arun(db.get_world_facts, 3)
    ctx = "\n".join(f"- {shorten(f['text'], 160)}" for f in facts) or "нет"
    who = isos[0] if len(isos) == 1 else f"{isos[0]} → {isos[1]}"
    user = (f"Тип события: {ev['brief']}.\nСтрана: {who}.\nМасштаб: {sev} из 5.\n{extra}\n"
            f"Недавние мировые события (для связности, не повторяй их):\n{ctx}")
    text = await ask("summary", [
        {"role": "system", "content": SYSTEM_PROMPT.format(year=rp_year or "20xx")},
        {"role": "user", "content": user},
    ], temperature=0.9)
    return text.strip() if text else None


def split_headline(text: str):
    head, _, body = text.strip().partition("\n")
    head = head.strip(" #*«»\"").strip()
    return shorten(head, 100), body.strip()


def format_event(kind: str, isos: list, rp: dict, head: str, body: str, market_line: str = "") -> str:
    ev = EVENTS.get(kind)
    title = f"{ev['emoji']} {ev['name']}" if ev else {"attack": "🎯 Покушение", "decree": "🏛 Решение власти"}.get(kind, "📰 Событие")
    where = " ↔ ".join(esc(_name(i)) for i in isos)
    when = f" · 📅 {rp['full']}" if rp.get("full") else ""
    out = f"🎭 <b>РП-СОБЫТИЕ · {title}</b>\n📍 {where}{when}\n\n<b>{esc(head)}</b>\n{esc(body)}"
    if market_line:
        out += f"\n\n{market_line}"
    return out


async def publish(bot, html_text: str, chat_id: int = None, thread_id: int = 0) -> bool:
    if chat_id is None:
        chat_id, thread_id = world_target()
    if not chat_id:
        return False
    try:
        await bot.send_message(chat_id=chat_id, text=html_text, parse_mode=ParseMode.HTML,
                               message_thread_id=thread_id or None)
        return True
    except Exception as e:
        log.warning("Не удалось опубликовать событие: %s", e)
        return False


def _persist(kind, iso, sev, text, rp_year, fact_tag, fact_text, m, t):
    """Выполняется в потоке БД: событие, мировой факт, биржа и напряжённость."""
    db.add_world_event(kind, iso, sev, text, rp_year)
    db.add_fact(fact_tag, fact_text, 0, "rp_events", rp_year)
    world.save_market(m)
    world.save_tension(t)


async def create_event(bot, kind: str = None, isos: list = None, announce: bool = True):
    """Создаёт и публикует событие. Возвращает словарь с итогом или None (нет темы мировых/сбой модели)."""
    if announce and not world_target()[0]:
        return None
    kind = kind if kind in EVENTS else random.choices(
        list(EVENTS), weights=[EVENTS[k]["weight"] for k in EVENTS])[0]
    ev = EVENTS[kind]
    pool = await play_countries()

    async with world.state_lock:
        t = world.tension()
        isos = [i for i in (isos or []) if i][:2]
        if not isos:
            isos = [_pick(pool, t)]
        if ev["two"] and len(isos) < 2:
            if kind == "incident":  # инциденты чаще между «горячими» странами
                isos.append(_pick(pool, t, exclude=isos))
            else:
                isos.append(random.choice([c for c in pool if c not in isos]))
        if not ev["two"]:
            isos = isos[:1]
        sev = random.randint(*ev["sev"])
        rp = get_rp_datetime()

        shocks, extra, market_line = dict(ev["shocks"] or {}), "", ""
        if kind == "market":
            asset, move = _market_shock(isos[0], sev)
            shocks = {asset: move}
            name = world.ASSETS[asset][0]
            extra = f"Факт рынка: {name} {'вырос' if move > 0 else 'упал'} примерно на {abs(move) * 100:.0f}% за сутки."
        scaled = {k: v * sev / 3 for k, v in shocks.items()}

    text = await generate_text(ev, kind, isos, sev, rp.get("year"), extra)
    if not text:
        log.warning("Событие %s не создано: модель не ответила", kind)
        return None
    head, body = split_headline(text)
    if not body:
        head, body = ev["name"], head

    async with world.state_lock:
        t = world.tension()
        k = sev / 3
        world.bump(t, isos[0], ev["tension"] * k)
        if len(isos) > 1:
            world.bump(t, isos[1], ev["tension"] * 0.6 * k)
        if kind == "shock":
            for c in pool:
                world.bump(t, c, ev["tension"])
        elif kind == "terror":                       # международная реакция
            for c in random.sample([c for c in pool if c != isos[0]], min(2, len(pool) - 1)):
                world.bump(t, c, 3)
        m = world.market()
        world.tick_market(m, scaled)
        if scaled:
            parts = []
            for a, mv in scaled.items():
                parts.append(f"{world.ASSETS[a][0]} {'📈' if mv > 0 else '📉'} {mv * 100:+.1f}%")
            market_line = "<i>" + " · ".join(parts) + "</i>"
        full = f"{head}\n{body}"
        await db.arun(_persist, kind, isos[0], sev, full, rp.get("year"),
                      f"world_{_name(isos[0]).lower()}", shorten(f"{head}. {body}", 600), m, t)

    html_text = format_event(kind, isos, rp, head, body, market_line)
    posted = await publish(bot, html_text) if announce else False
    schedule_followup(kind, isos, sev)
    return {"kind": kind, "isos": isos, "head": head, "body": body, "sev": sev, "posted": posted, "html": html_text}


# что может случиться ПОСЛЕ события: (тип последствия, вероятность)
FOLLOW = {
    "terror": [("protest", 0.5), ("propaganda", 0.3), ("market", 0.3)],
    "attack": [("protest", 0.6), ("propaganda", 0.4), ("incident", 0.25)],
    "incident": [("propaganda", 0.6), ("market", 0.4)],
    "shock": [("market", 0.8), ("strike", 0.4), ("protest", 0.5)],
    "cyber": [("market", 0.2)],
}


def schedule_followup(src: str, isos: list, sev: int = 3, revealed: bool = False):
    """Ставит в очередь последствия события (через 15–90 минут). Работает только при включённых событиях."""
    if db.get_setting("events_mode", "off") == "off":
        return
    for kind, p in FOLLOW.get(src, []):
        if kind == "incident" and not revealed:
            continue
        if random.random() < p * (0.6 + sev / 10):
            _queue.append((time.time() + random.randint(900, 5400), kind, list(isos)))
    del _queue[20:]


async def tick(bot):
    """Один «тик» мира: биржа и напряжённость живут всегда, события — по режиму."""
    global _last_event
    async with world.state_lock:
        m = world.market()
        world.tick_market(m)
        t = world.tension()
        world.decay(t)
        cs = world.cstate_all()
        world.decay_cstate(cs)
        await db.arun(lambda: (world.save_market(m), world.save_tension(t), world.save_cstate_all(cs)))
    mode = db.get_setting("events_mode", "off")
    p = PER_DAY.get(mode, 0) / (86400 / max(60, C.EVENTS_TICK))
    if p and random.random() < p and time.time() - _last_event > 1200:
        if await create_event(bot):
            _last_event = time.time()
    now = time.time()
    for item in [x for x in _queue if x[0] <= now]:
        _queue.remove(item)
        await create_event(bot, item[1], item[2])


async def scheduler(bot):
    await asyncio.sleep(30)
    while True:
        try:
            await tick(bot)
        except Exception:
            log.exception("Ошибка тика мира")
        await asyncio.sleep(max(60, C.EVENTS_TICK))
