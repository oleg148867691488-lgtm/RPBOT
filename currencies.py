"""
CURRENCIES.PY — новые валюты, которые создают страны, и их курс на бирже.

Курс = сколько единиц валюты стоит 1 РП-доллар (как у рубля: чем число больше, тем валюта слабее).
Курс тянется к «справедливому» уровню, который зависит от:
  • золотого запаса страны (больше золота — крепче валюта);
  • напряжённости вокруг страны и войн (чем хуже обстановка и действия в стране — тем слабее валюта);
плюс небольшие случайные колебания и мгновенная реакция на события в стране.
Хранится в настройках (JSON), отдельной таблицы не нужно.
"""
import json
import math
import random
import re

import database as db
import world
from auth import is_staff
from textutils import esc
from tg import safe_reply
from worldbank import ISO_RU, find_countries

KEY = "custom_currencies"
CODE_RE = re.compile(r"^[A-ZА-ЯЁ]{3,4}$")
RESERVED = {"USD", "EUR", "GBP", "RUB", "CNY", "JPY", "CHF", "TRY", "RPC", "NVC", "ETX", "BTC", "ETH", "GLD", "XAU", "XAG", "OIL"}
MAX_GOLD = 100_000.0


# ---------------------------------------------------------------- хранилище

def load() -> dict:
    raw = db.get_setting(KEY)
    try:
        d = json.loads(raw) if raw else {}
    except ValueError:
        d = {}
    return d if isinstance(d, dict) else {}


def _save(d: dict):
    db.set_setting(KEY, json.dumps(d, ensure_ascii=False))


def _name(iso: str) -> str:
    return ISO_RU.get(iso, iso)


def default_rate(gold: float) -> float:
    """Стартовый курс по золотому запасу: больше золота — крепче валюта (меньше единиц за доллар)."""
    return round(max(0.2, 40.0 / (1.0 + gold / 100.0)), 3)


def _target(c: dict) -> float:
    t = world.tension().get(c["iso"], 0.0)
    war = 0.25 if world.at_war(c["iso"]) else 0.0
    g = max(0.1, min(10.0, c["gold"] / max(1.0, c["gold0"])))
    return c["base"] * (g ** -0.35) * (1.0 + 0.006 * t + war)


# ---------------------------------------------------------------- операции (вызывать через db.arun)

def create(code: str, name: str, iso: str, creator: int, gold: float, base: float = None, year=None):
    """Возвращает (ok, сообщение или запись)."""
    code = code.upper()
    d = load()
    if not CODE_RE.match(code):
        return False, "Код валюты — 3–4 буквы (например, <code>НОВР</code> или <code>NVR</code>)."
    if code in RESERVED or code in d:
        return False, f"Код <b>{esc(code)}</b> уже занят."
    if any(c["iso"] == iso for c in d.values()):
        return False, f"У страны <b>{esc(_name(iso))}</b> уже есть своя валюта."
    gold = max(0.0, min(MAX_GOLD, gold))
    base = base if base and base > 0 else default_rate(gold)
    rec = {"name": name, "iso": iso, "creator": creator, "year": year, "gold": gold, "gold0": max(1.0, gold),
           "base": round(base, 4), "rate": round(base, 4), "h": [round(base, 4)]}
    d[code] = rec
    _save(d)
    return True, rec


def delete(code: str) -> bool:
    d = load()
    if code.upper() not in d:
        return False
    del d[code.upper()]
    _save(d)
    return True


def set_gold(iso: str, tons: float, relative: bool):
    """Меняет золотой запас валюты страны. Возвращает (код, было, стало) или None."""
    d = load()
    for code, c in d.items():
        if c["iso"] == iso:
            old = c["gold"]
            new = max(0.0, min(MAX_GOLD, old + tons if relative else tons))
            c["gold"] = new
            # мгновенная реакция курса: ровно половина того, что даст полный пересчёт
            k = (max(0.1, new / max(1.0, old)) if old else 1.0) ** -0.175
            c["rate"] = round(max(0.01, c["rate"] * k), 4)
            c["h"] = (c["h"] + [c["rate"]])[-24:]
            _save(d)
            return code, old, new
    return None


def tick():
    """Шаг рынка: курс тянется к справедливому уровню плюс немного случайности."""
    d = load()
    if not d:
        return
    for c in d.values():
        new = c["rate"] * math.exp(random.gauss(0, 0.006))
        new += (_target(c) - new) * 0.12
        c["rate"] = round(max(new, c["base"] * 0.02), 4)
        c["h"] = (c["h"] + [c["rate"]])[-24:]
    _save(d)


def react_all(deltas: dict):
    """События в стране: рост напряжённости ослабляет её валюту, спад — укрепляет."""
    d = load()
    changed = False
    for c in d.values():
        dt = deltas.get(c["iso"])
        if not dt:
            continue
        pct = max(-6.0, min(8.0, dt * 0.35))
        c["rate"] = round(max(c["rate"] * (1 + pct / 100), c["base"] * 0.02), 4)
        c["h"] = (c["h"] + [c["rate"]])[-24:]
        changed = True
    if changed:
        _save(d)


# ---------------------------------------------------------------- отображение

def _g(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def _fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ") if x >= 1000 else (f"{x:.2f}" if x >= 10 else f"{x:.3f}")


def render_lines() -> list:
    """Строки для экрана биржи. Пусто, если новых валют нет."""
    d = load()
    if not d:
        return []
    out = ["", "🪙 <b>Новые валюты</b> <i>(единиц за $1)</i>"]
    for code, c in sorted(d.items()):
        h = c["h"]
        ch = (h[0] / h[-1] - 1) * 100 if len(h) > 1 and h[-1] else 0.0     # сила валюты: меньше единиц за $1 — крепче
        arrow = "🟢▲" if ch > 0.05 else "🔴▼" if ch < -0.05 else "⚪️▬"
        out.append(f"<b>{esc(code)}</b> · {esc(c['name'])} <i>({esc(_name(c['iso']))})</i>")
        out.append(f"   <b>{_fmt(c['rate'])}</b> {arrow} {ch:+.1f}% · 🥇 {_g(c['gold'])} т")
        out.append(f"   <code>{world.spark(h[-16:])}</code>")
    return out


# ---------------------------------------------------------------- команды

def _num(s: str):
    try:
        return float(s.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


async def newcurrency_command(update, context):
    """/newcurrency КОД Название [золото 500] [курс 12] [страна Франция] — создать валюту своей страны."""
    msg, user = update.effective_message, update.effective_user
    args = context.args or []
    if len(args) < 2:
        await safe_reply(msg, "🪙 <b>Новая валюта</b>\n"
                              "<code>/newcurrency НОВР Новый рубль золото 500</code>\n"
                              "• <b>золото</b> — золотой запас в тоннах (от него зависит курс);\n"
                              "• <b>курс</b> — стартовая цена за $1 (по желанию, иначе посчитается по золоту);\n"
                              "• <b>страна</b> — только для админов (игрок создаёт валюту своей страны).\n"
                              "<i>У страны может быть одна валюта.</i>")
        return
    code, rest = args[0], " ".join(args[1:])
    gold = rate = None
    m = re.search(r"золот\w*\s+(\d[\d.,]*)(?:\s*(?:тонн\w*|т\b))?", rest, re.I)
    if m:
        gold = _num(m.group(1))
        rest = rest.replace(m.group(0), " ")
    m = re.search(r"курс\s+([\d.,]+)", rest, re.I)
    if m:
        rate = _num(m.group(1))
        rest = rest.replace(m.group(0), " ")
    iso = None
    m = re.search(r"страна\s+(.+)$", rest, re.I)
    if m:
        if not is_staff(user.id):
            await safe_reply(msg, "❌ Валюту другой страны создают только админы.")
            return
        found = find_countries(m.group(1))
        iso = found[0] if found else None
        rest = rest[:m.start()]
        if not iso:
            await safe_reply(msg, "❌ Не понял, какая страна.")
            return
    iso = iso or world.mycountry(user.id)
    if not iso:
        await safe_reply(msg, "❌ Сначала выбери свою страну (<code>/mycountry Страна</code>).")
        return
    name = re.sub(r"\s+", " ", rest).strip()[:30] or f"Валюта {code.upper()}"
    if gold is None:
        await safe_reply(msg, "❌ Укажи золотой запас: <code>золото 500</code> (в тоннах). От него зависит курс валюты.")
        return
    from rptime import get_rp_datetime
    ok, res = await db.arun(create, code, name, iso, user.id, gold, rate, get_rp_datetime().get("year"))
    if not ok:
        await safe_reply(msg, f"❌ {res}")
        return
    text = (f"🪙 <b>Новая валюта</b>\n━━━━━━━━━━━━━━━━\n"
            f"<b>{esc(_name(iso))}</b> вводит <b>{esc(name)}</b> (<code>{esc(code.upper())}</code>).\n"
            f"🥇 Золотой запас: <b>{_g(res['gold'])} т</b> · курс <b>{_fmt(res['rate'])}</b> за $1\n"
            "<i>Курс зависит от золотого запаса, напряжённости и событий в стране. Смотри в разделе «Биржа».</i>")
    await safe_reply(msg, text)
    try:                                                 # заодно в мировой чат
        from events import publish
        await publish(context.bot, text)
    except Exception:
        pass


async def goldreserve_command(update, context):
    """/goldreserve Страна 500 | +50 | -30 — админ меняет золотой запас валюты страны."""
    msg = update.effective_message
    if not is_staff(update.effective_user.id):
        await safe_reply(msg, "❌ Только для админов.")
        return
    text = " ".join(context.args or [])
    isos = find_countries(text)
    m = re.search(r"([+-]?)\s*(\d[\d.,]*)\s*(?:т\b|тонн\w*)?\s*$", text)
    if not isos or not m or _num(m.group(2)) is None:
        await safe_reply(msg, "Используй: <code>/goldreserve Франция 800</code> (задать), <code>/goldreserve Франция +50</code> или <code>-30</code>")
        return
    val = _num(m.group(2))
    rel = bool(m.group(1))
    res = await db.arun(set_gold, isos[0], -val if m.group(1) == "-" else val, rel)
    if not res:
        await safe_reply(msg, f"ℹ️ У страны {esc(_name(isos[0]))} нет своей валюты. Её создают командой /newcurrency.")
        return
    code, old, new = res
    await safe_reply(msg, f"🥇 Золотой запас <b>{esc(code)}</b> ({esc(_name(isos[0]))}): {_g(old)} → <b>{_g(new)} т</b>. Курс пересчитан.")


async def delcurrency_command(update, context):
    msg = update.effective_message
    if not is_staff(update.effective_user.id):
        await safe_reply(msg, "❌ Только для админов.")
        return
    code = (context.args or [""])[0]
    ok = await db.arun(delete, code) if code else False
    await safe_reply(msg, f"🗑 Валюта <b>{esc(code.upper())}</b> удалена." if ok else "ℹ️ Такой валюты нет. Пример: <code>/delcurrency НОВР</code>")


async def currency_command(update, context):
    lines = render_lines()
    await safe_reply(update.effective_message, "\n".join(["🪙 <b>Валюты стран</b>"] + lines[1:]) if lines else
                     "🪙 Новых валют пока нет. Создать: <code>/newcurrency КОД Название золото 500</code>")
