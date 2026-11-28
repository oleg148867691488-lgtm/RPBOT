"""
MARKETFX.PY — рынок реагирует на смысл мировых новостей.

  • Страна нашла месторождение — предложение растёт, цена этого ресурса падает.
  • Месторождение или трубопровод подорваны — вероятно (но не наверняка), цена растёт.
  • Блокада пролива или залива — цены на то, что через него идёт (нефть, газ, зерно…), вероятно растут, а фондовый рынок слабеет.

Вызывается после каждой опубликованной в мировой чат новости (events.publish → worldhooks.after_publish).
Без ИИ: словарь ресурсов и шаблоны, поэтому дёшево и предсказуемо.
"""
import logging
import random
import re

import database as db
import world

log = logging.getLogger(__name__)

ASSET_WORDS = {
    "oil": r"нефт\w*|нефтепровод\w*", "gas": r"газ\w*|газопровод\w*|спг\b", "coal": r"угол\w+|угольн\w+",
    "gold": r"золот\w+", "silver": r"серебр\w+", "copper": r"медь\b|меди\b|медн\w+", "iron": r"железн\w+ руд\w+|железорудн\w+",
    "aluminum": r"алюмин\w+|бокси\w+", "nickel": r"никел\w+", "zinc": r"цинк\w*", "tin": r"олов\w+", "platinum": r"платин\w+",
    "lithium": r"лити\w+", "rare": r"редкозем\w+", "wheat": r"пшениц\w+|зерн\w+", "rice": r"\bрис\w*", "corn": r"кукуруз\w+",
    "sugar": r"сахар\w*", "coffee": r"кофе\b", "steel": r"сталь\b|стали\b|металлург\w+",
}
DISCOVERY_RE = re.compile(r"(?:нашл\w+|обнаруж\w+|открыл\w*|открыт\w+|разведал\w*)\s+(?:\w+\s+){0,3}(?:месторожден|залежи|запас)\w*|"
                          r"новое\s+месторожден\w+|крупн\w+\s+месторожден\w+|месторожден\w+\s+(?:открыт|найден|обнаружен)", re.I)
SABOTAGE_RE = re.compile(r"подорв\w+|диверси\w+|взрыв\w*\s+(?:на\s+)?(?:\w+\s+){0,2}(?:нефте|газо|трубопровод|месторожден|скважин|шахт|рудник|промысл)|"
                         r"уничтож\w+\s+(?:\w+\s+){0,2}(?:месторожден|скважин|шахт|рудник|нефтепровод|газопровод|промысл)|"
                         r"атак\w+\s+на\s+(?:\w+\s+){0,2}(?:месторожден|промысл|шахт|нефтепровод|газопровод)|"
                         r"поврежд\w+\s+(?:\w+\s+){0,2}(?:нефте|газо)провод", re.I)
BLOCKADE_RE = re.compile(r"блокад\w+|(?:перекры\w+|закры\w+|минирова\w+|заблокир\w+)\s+(?:\w+\s+){0,2}(?:пролив|залив)", re.I)
STRAITS = [  # (шаблон названия, [(актив, доля от базового шока)])
    (r"ормузск\w+|персидск\w+\s+залив\w*", [("oil", 1.0), ("gas", 0.8)]),
    (r"малакк\w+", [("oil", 0.7), ("rice", 0.3), ("steel", 0.3)]),
    (r"баб-эль-мандебск\w+|суэцк\w+|красн\w+\s+мор\w+", [("oil", 0.7), ("gas", 0.4), ("coffee", 0.4)]),
    (r"босфор\w*|дарданелл\w*|чёрн\w+\s+мор\w+", [("wheat", 1.0), ("corn", 0.8), ("oil", 0.4)]),
    (r"тайваньск\w+\s+пролив\w*", [("lithium", 0.6), ("rare", 0.6)]),
    (r"гибралтар\w*|ла-манш\w*|ламанш\w*", [("oil", 0.3), ("steel", 0.3)]),
]
NAMES = {k: v[0] for k, v in world.ASSETS.items()}


def _assets_in(text: str) -> list:
    return [a for a, pat in ASSET_WORDS.items() if re.search(pat, text, re.I)]


def effects_from_text(text: str) -> dict:
    """{актив: доля изменения цены} по смыслу новости. Пусто, если новость рынка не касается."""
    out = {}
    low = text.lower()
    found = _assets_in(low)
    if DISCOVERY_RE.search(low) and found:                       # нашли — цена падает
        for a in found[:2]:
            out[a] = out.get(a, 0.0) - random.uniform(0.02, 0.06)
    if SABOTAGE_RE.search(low) and found and random.random() < 0.75:   # подорвали — цена, скорее всего, растёт
        for a in found[:2]:
            out[a] = out.get(a, 0.0) + random.uniform(0.03, 0.08)
    if BLOCKADE_RE.search(low) and random.random() < 0.85:      # блокада пролива или залива
        base = random.uniform(0.03, 0.09)
        hit = False
        for pat, assets in STRAITS:
            if re.search(pat, low):
                hit = True
                for a, share in assets:
                    out[a] = out.get(a, 0.0) + base * share
        if not hit:                                             # пролив не назван — берём упомянутые ресурсы или нефть
            for a in (found[:2] or ["oil"]):
                out[a] = out.get(a, 0.0) + base * 0.6
        out["stocks"] = out.get("stocks", 0.0) - random.uniform(0.005, 0.02)
    return {a: round(v, 4) for a, v in out.items() if a in world.ASSETS and abs(v) > 1e-4}


def describe(effects: dict) -> str:
    parts = [f"{NAMES.get(a, a)} {'▲' if v > 0 else '▼'} ~{abs(v) * 100:.0f}%" for a, v in effects.items() if a != "stocks" or abs(v) >= 0.01]
    return "📈 <i>Рынок отреагировал: " + ", ".join(parts) + "</i>" if parts else ""


async def apply_news(bot, plain_text: str) -> str:
    """Применяет эффект новости к бирже. Возвращает строку для чата (или пусто)."""
    eff = effects_from_text(plain_text)
    if not eff:
        return ""
    async with world.state_lock:
        m = world.tick_market(world.market(), eff)
        await db.arun(world.save_market, m)
    return describe(eff)
