"""
MARKET.PY — игровой рынок: курсы валют и крипта, которые «живут» сами и реагируют на события.
Это СИМУЛЯЦИЯ для РП (не реальные котировки): случайное блуждание + возврат к исходному уровню.
Крипта вымышленная (RP-Coin, NovaCoin, EtherX). Курсы валют — к условному РП-доллару (USD).
"""

import json
import math
import random

import database as db

# символ: (название, стартовая цена, волатильность за тик)
CURRENCIES = {
    "EUR": ("Евро", 0.75, 0.010),
    "GBP": ("Фунт", 0.64, 0.011),
    "RUB": ("Рубль", 30.0, 0.016),
    "CNY": ("Юань", 6.8, 0.004),
    "JPY": ("Иена", 90.0, 0.010),
    "CHF": ("Франк", 1.0, 0.008),
    "TRY": ("Лира", 1.55, 0.018),
}
CRYPTO = {
    "RPC": ("RP-Coin", 120.0, 0.06),
    "NVC": ("NovaCoin", 8.5, 0.09),
    "ETX": ("EtherX", 45.0, 0.08),
}
ISO_CURRENCY = {
    "RUS": "RUB", "CHN": "CNY", "JPN": "JPY", "GBR": "GBP", "TUR": "TRY", "CHE": "CHF",
    "FRA": "EUR", "DEU": "EUR", "ITA": "EUR", "ESP": "EUR", "NLD": "EUR", "FIN": "EUR", "GRC": "EUR",
}
_ALL = {**CURRENCIES, **CRYPTO}
SPARK = "▁▂▃▄▅▆▇█"


def _spec(symbol: str):
    return _ALL[symbol]


def ensure_market():
    for sym, (_name, price, _vol) in _ALL.items():
        kind = "fx" if sym in CURRENCIES else "crypto"
        db.execute("INSERT OR IGNORE INTO market (symbol, kind, price, history, updated_at) VALUES (?, ?, ?, ?, ?)",
                   (sym, kind, price, json.dumps([price]), db._now()))


def _save(sym: str, price: float, hist: list):
    db.execute("UPDATE market SET price = ?, history = ?, updated_at = ? WHERE symbol = ?",
               (price, json.dumps(hist[-24:]), db._now(), sym))


def tick():
    """Один шаг рынка (вызывается раз в ~20 минут)."""
    for r in db.execute("SELECT * FROM market"):
        if r["symbol"] not in _ALL:
            continue
        _name, start, vol = _spec(r["symbol"])
        new = r["price"] * math.exp(random.gauss(0, vol))
        new += (start - new) * 0.01          # мягкий возврат к исходному уровню
        new = max(new, start * 0.02)
        _save(r["symbol"], new, json.loads(r["history"]) + [new])


def apply_shock(sym: str, pct: float) -> list:
    """Мгновенный скачок цены (от событий). 'CRYPTO' — вся крипта. Возвращает [(символ, было, стало)]."""
    syms = list(CRYPTO) if sym == "CRYPTO" else ([sym] if sym in _ALL else [])
    out = []
    for s in syms:
        rows = db.execute("SELECT * FROM market WHERE symbol = ?", (s,))
        if not rows:
            continue
        k = random.uniform(0.7, 1.3) if sym == "CRYPTO" else 1.0
        old = rows[0]["price"]
        new = max(old * (1 + pct * k / 100), _spec(s)[1] * 0.02)
        _save(s, new, json.loads(rows[0]["history"]) + [new])
        out.append((s, old, new))
    return out


def fmt_price(sym: str, price: float) -> str:
    if sym in CRYPTO:
        return f"{price:,.2f}".replace(",", " ")
    return f"{price:.1f}" if price >= 100 else (f"{price:.2f}" if price >= 10 else f"{price:.3f}")


def sparkline(values: list, n: int = 10) -> str:
    v = values[-n:]
    lo, hi = min(v), max(v)
    if hi - lo < 1e-12:
        return SPARK[3] * len(v)
    return "".join(SPARK[min(7, int((x - lo) / (hi - lo) * 7.999))] for x in v)


def get_snapshot() -> list:
    out = []
    for r in db.execute("SELECT * FROM market ORDER BY kind, symbol"):
        if r["symbol"] not in _ALL:
            continue
        hist = json.loads(r["history"])
        prev = hist[-2] if len(hist) > 1 else hist[0]
        out.append({"symbol": r["symbol"], "name": _spec(r["symbol"])[0], "kind": r["kind"],
                    "price": r["price"], "change": (r["price"] / prev - 1) * 100 if prev else 0.0,
                    "spark": sparkline(hist)})
    return out
