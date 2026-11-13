"""
WORLD.PY — состояние игрового мира: биржа, напряжённость стран, защита целей, «моя страна» игрока.
Всё хранится в таблице settings (JSON) и читается из кэша без обращения к сети.
Функции save_* пишут в БД — вызывать через db.arun().
"""

import asyncio
import json
import math
import random

import database as db

state_lock = asyncio.Lock()   # общий замок на изменение состояния мира (события, операции, тики)

# ключ: (название, старт, волатильность за тик, число знаков)
ASSETS = {
    "oil": ("🛢 Нефть Brent", 80.0, 0.012, 1),
    "gold": ("🥇 Золото", 1200.0, 0.008, 0),
    "usdrub": ("💵 USD/RUB", 30.0, 0.006, 2),
    "eurusd": ("💶 EUR/USD", 1.30, 0.004, 3),
    "usdcny": ("💴 USD/CNY", 6.80, 0.002, 3),
    "crypto": ("₿ Криптобиржа", 100.0, 0.045, 1),
}
CURRENCY_OF = {"RUS": "usdrub", "CHN": "usdcny", "DEU": "eurusd", "FRA": "eurusd",
               "ITA": "eurusd", "ESP": "eurusd", "NLD": "eurusd", "FIN": "eurusd", "GRC": "eurusd"}
SPARK = "▁▂▃▄▅▆▇█"


def _load(key: str, default):
    raw = db.get_setting(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        return default


# ---------------- биржа ----------------

def market() -> dict:
    m = _load("market", None)
    if not isinstance(m, dict) or "v" not in m or "h" not in m:
        m = {"v": {}, "h": {}}
    for k, a in ASSETS.items():
        m["v"].setdefault(k, a[1])
        m["h"].setdefault(k, [a[1]])
    return m


def tick_market(m: dict, shocks: dict = None) -> dict:
    shocks = shocks or {}
    for k, (_n, start, vol, _d) in ASSETS.items():
        v = m["v"][k] * math.exp(random.gauss(0, vol)) * (1 + shocks.get(k, 0.0))
        v += (start - v) * 0.002          # слабая тяга к стартовому уровню
        m["v"][k] = round(max(v, start * 0.05), 4)
        m["h"][k].append(m["v"][k])
        del m["h"][k][:-24]
    return m


def spark(values: list) -> str:
    lo, hi = min(values), max(values)
    if hi == lo:
        return SPARK[3] * len(values)
    return "".join(SPARK[int((v - lo) / (hi - lo) * 7)] for v in values)


def change_pct(h: list) -> float:
    return (h[-1] / h[0] - 1) * 100 if len(h) > 1 and h[0] else 0.0


def fmt_price(key: str, v: float) -> str:
    return f"{v:,.{ASSETS[key][3]}f}".replace(",", " ")


def save_market(m: dict):
    db.set_setting("market", json.dumps(m))


# ---------------- напряжённость ----------------

def tension() -> dict:
    return {k: float(v) for k, v in _load("tension", {}).items()}


def bump(t: dict, iso: str, delta: float):
    t[iso] = round(max(0.0, min(100.0, t.get(iso, 0.0) + delta)), 2)


def decay(t: dict, factor: float = 0.995):
    for k in list(t):
        t[k] = round(t[k] * factor, 2)
        if t[k] < 0.5:
            del t[k]


def save_tension(t: dict):
    db.set_setting("tension", json.dumps(t))


# ---------------- защита и «моя страна» ----------------

def security(iso: str) -> int:
    return int(_load("security", {}).get(iso, 50))


def set_security(iso: str, value: int):
    s = _load("security", {})
    s[iso] = max(0, min(100, int(value)))
    db.set_setting("security", json.dumps(s))


def mycountry(user_id: int):
    return _load("mycountry", {}).get(str(user_id))


def set_mycountry(user_id: int, iso: str):
    s = _load("mycountry", {})
    s[str(user_id)] = iso
    db.set_setting("mycountry", json.dumps(s))


# ---------------- усиления стран (результат /action) ----------------
# sec — общая защита, top/gov/civil — охрана высших лиц / чиновников / прочих, intel — разведка
CAPS = {"sec": (-20.0, 30.0), "top": (0.0, 40.0), "gov": (0.0, 40.0), "civil": (0.0, 30.0), "intel": (0.0, 30.0)}


def cstate_all() -> dict:
    return _load("cstate", {})


def cstate(iso: str) -> dict:
    st = {k: 0.0 for k in CAPS}
    st.update({k: float(v) for k, v in cstate_all().get(iso, {}).items() if k in CAPS})
    return st


def apply_action(st: dict, eff: dict) -> dict:
    """Применяет эффекты с убывающей отдачей и границами. Возвращает фактически применённое."""
    applied = {}
    for k, d in eff.items():
        lo, hi = CAPS[k]
        cur = st[k]
        if d > 0:
            d *= max(0.0, 1 - max(cur, 0.0) / hi)    # чем выше уровень, тем труднее расти
        new = round(max(lo, min(hi, cur + d)), 2)
        applied[k] = round(new - cur, 1)
        st[k] = new
    return applied


def save_cstate(iso: str, st: dict):
    allst = cstate_all()
    allst[iso] = st
    db.set_setting("cstate", json.dumps(allst))


def decay_cstate(allst: dict, factor: float = 0.998):
    for iso in list(allst):
        for k in list(allst[iso]):
            allst[iso][k] = round(allst[iso][k] * factor, 2)
        if all(abs(v) < 0.3 for v in allst[iso].values()):
            del allst[iso]


def save_cstate_all(allst: dict):
    db.set_setting("cstate", json.dumps(allst))


# ---------------- войны ----------------

def wars() -> list:
    return [tuple(p) for p in _load("wars", []) if len(p) == 2]


def at_war(iso: str) -> bool:
    return any(iso in p for p in wars())


def add_war(a: str, b: str) -> bool:
    w = wars()
    if (a, b) in w or (b, a) in w:
        return False
    w.append((a, b))
    db.set_setting("wars", json.dumps(w))
    return True


def end_war(a: str, b: str) -> bool:
    w = wars()
    new = [p for p in w if set(p) != {a, b}]
    if len(new) == len(w):
        return False
    db.set_setting("wars", json.dumps(new))
    return True
