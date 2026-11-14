"""
WORLDBANK.PY — данные Всемирного банка.

Исправлено по сравнению со старой версией:
- «ввп на душу» теперь реально находится (раньше «ввп» перехватывал его первым).
- «ukraine» больше не определяется как «uk» (Великобритания): ищем целые слова, длинные ключи первыми.
- Если за запрошенный год данных нет — берётся ближайший более ранний год (с пометкой).
- /top: из списка убраны агрегаты (World, High income, OECD …), остались только страны.
- Добавлены показатели: военные расходы, госдолг.
"""

import json
import logging
import re
from datetime import datetime

import httpx

from netclient import get_client

log = logging.getLogger(__name__)

WB = "https://api.worldbank.org/v2"

COUNTRIES = {
    "россия": "RUS", "рф": "RUS", "russia": "RUS",
    "сша": "USA", "соединенные штаты": "USA", "соединённые штаты": "USA", "америка": "USA", "usa": "USA",
    "китай": "CHN", "china": "CHN",
    "германия": "DEU", "germany": "DEU",
    "франция": "FRA", "france": "FRA",
    "великобритания": "GBR", "англия": "GBR", "uk": "GBR",
    "япония": "JPN", "japan": "JPN",
    "индия": "IND", "india": "IND",
    "бразилия": "BRA", "brazil": "BRA",
    "украина": "UKR", "ukraine": "UKR",
    "беларусь": "BLR", "belarus": "BLR",
    "казахстан": "KAZ", "kazakhstan": "KAZ",
    "финляндия": "FIN", "finland": "FIN",
    "швеция": "SWE", "sweden": "SWE",
    "турция": "TUR", "turkey": "TUR",
    "болгария": "BGR", "bulgaria": "BGR",
    "сербия": "SRB", "serbia": "SRB",
    "польша": "POL", "poland": "POL",
    "италия": "ITA", "italy": "ITA",
    "испания": "ESP", "spain": "ESP",
    "канада": "CAN", "canada": "CAN",
    "австралия": "AUS", "australia": "AUS",
    "мексика": "MEX", "mexico": "MEX",
    "южная корея": "KOR", "северная корея": "PRK",
    "иран": "IRN", "iran": "IRN",
    "израиль": "ISR", "israel": "ISR",
    "египет": "EGY", "egypt": "EGY",
    "саудовская аравия": "SAU",
    "норвегия": "NOR", "norway": "NOR",
    "чехия": "CZE", "венгрия": "HUN", "румыния": "ROU", "греция": "GRC",
    "нидерланды": "NLD", "швейцария": "CHE", "аргентина": "ARG",
    "юар": "ZAF", "индонезия": "IDN", "пакистан": "PAK",
    "узбекистан": "UZB", "азербайджан": "AZE", "армения": "ARM", "грузия": "GEO",
    "эстония": "EST", "латвия": "LVA", "литва": "LTU", "молдова": "MDA",
}

# ключ -> (код индикатора, тип значения)
INDICATORS = {
    "ввп на душу": ("NY.GDP.PCAP.CD", "usd_pc"),
    "ввп": ("NY.GDP.MKTP.CD", "usd"), "gdp": ("NY.GDP.MKTP.CD", "usd"),
    "население": ("SP.POP.TOTL", "people"),
    "инфляция": ("FP.CPI.TOTL.ZG", "pct"),
    "безработица": ("SL.UEM.TOTL.ZS", "pct"),
    "продолжительность жизни": ("SP.DYN.LE00.IN", "years"),
    "военные расходы": ("MS.MIL.XPND.CD", "usd"), "военный бюджет": ("MS.MIL.XPND.CD", "usd"),
    "госдолг": ("GC.DOD.TOTL.GD.ZS", "pct"),
}


def _kw_pattern(key: str) -> re.Pattern:
    key = key.lower()
    if " " in key or len(key) < 4 or not re.search(r"[а-яё]", key):
        pat = r"(?<!\w)" + re.escape(key) + r"(?!\w)"
    else:  # русские слова: допускаем окончания («россии», «китае», «инфляции»)
        pat = r"(?<!\w)" + re.escape(key[:-1]) + r"\w{0,2}(?!\w)"
    return re.compile(pat)


def _compile(d: dict) -> list:
    return [(_kw_pattern(k), v) for k, v in sorted(d.items(), key=lambda kv: -len(kv[0]))]


_COUNTRY_PATTERNS = _compile(COUNTRIES)
_INDICATOR_PATTERNS = _compile(INDICATORS)


def find_country(text: str):
    t = (text or "").lower()
    for pat, iso in _COUNTRY_PATTERNS:
        if pat.search(t):
            return iso
    return None


def find_indicator(text: str):
    t = (text or "").lower()
    for pat, val in _INDICATOR_PATTERNS:
        if pat.search(t):
            return val
    return None


def format_value(value: float, kind: str) -> str:
    if kind == "pct":
        return f"{value:.1f}%"
    if kind == "years":
        return f"{value:.1f} лет"
    if kind == "usd_pc":
        return f"{value:,.0f} $".replace(",", " ")
    if kind == "people":
        if value >= 1e9:
            return f"{value / 1e9:.2f} млрд чел."
        if value >= 1e6:
            return f"{value / 1e6:.1f} млн чел."
        return f"{value:,.0f} чел.".replace(",", " ")
    # usd
    if value >= 1e12:
        return f"{value / 1e12:.2f} трлн $"
    if value >= 1e9:
        return f"{value / 1e9:.1f} млрд $"
    if value >= 1e6:
        return f"{value / 1e6:.1f} млн $"
    return f"{value:,.0f} $".replace(",", " ")


async def _get_json(url: str, params: dict, timeout: float = 20.0):
    try:
        resp = await get_client().get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("World Bank ошибка: %s", type(e).__name__)
        return None


async def fetch_indicator(iso3: str, code: str, kind: str, year: int = None):
    """Последнее доступное значение показателя (не позже указанного года)."""
    last = year or datetime.now().year
    data = await _get_json(
        f"{WB}/country/{iso3}/indicator/{code}",
        {"format": "json", "per_page": 30, "date": f"{last - 8}:{last}"},
    )
    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        return None
    for rec in data[1]:  # от новых к старым
        if rec.get("value") is not None:
            note = ""
            if year and str(rec["date"]) != str(year):
                note = f" (данных за {year} нет, взят {rec['date']})"
            return (f"{rec['indicator']['value']} для {rec['country']['value']} "
                    f"({rec['date']}): {format_value(rec['value'], kind)}{note}")
    return None


async def get_economic_context(text: str):
    iso = find_country(text)
    ind = find_indicator(text)
    if not iso or not ind:
        return None
    m = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    year = int(m.group(1)) if m else None
    result = await fetch_indicator(iso, ind[0], ind[1], year)
    return f"[ДАННЫЕ WORLD BANK]: {result}" if result else None


# ---------------------------------------------------------------------
# ТОП СТРАН
# ---------------------------------------------------------------------

_real_countries = None


async def real_country_ids() -> set:
    """ISO3-коды настоящих стран (без агрегатов вроде World / High income)."""
    global _real_countries
    if _real_countries:
        return _real_countries
    data = await _get_json(f"{WB}/country", {"format": "json", "per_page": 400})
    ids = set()
    if isinstance(data, list) and len(data) > 1:
        for c in data[1] or []:
            if (c.get("region") or {}).get("id") != "NA":
                ids.add(c.get("id"))
    if ids:
        _real_countries = ids
    return ids


async def fetch_top(code: str, year: int, count: int):
    """Возвращает (список записей, год данных). Если за год пусто — ищет ближайший более ранний."""
    real = await real_country_ids()
    if not real:
        return [], year
    for y in (year, year - 1, year - 2, year - 3):
        data = await _get_json(
            f"{WB}/country/all/indicator/{code}",
            {"format": "json", "per_page": 400, "date": str(y)},
            timeout=30.0,
        )
        if not isinstance(data, list) or len(data) < 2 or not data[1]:
            continue
        rows = [r for r in data[1]
                if r.get("value") is not None and r.get("countryiso3code") in real]
        if len(rows) >= min(count, 5):
            rows.sort(key=lambda r: r["value"], reverse=True)
            return rows[:count], y
    return [], year


# ---------------------------------------------------------------------
# СРАВНЕНИЕ СТРАН (/vs)
# ---------------------------------------------------------------------

ISO_RU = {}
for _k, _iso in COUNTRIES.items():
    if _iso not in ISO_RU and re.search(r"[а-яё]", _k):
        ISO_RU[_iso] = _k.upper() if len(_k) <= 3 else _k.capitalize()

# (подпись, код, тип, что лучше: high/low)
VS_METRICS = [
    ("ВВП", "NY.GDP.MKTP.CD", "usd", "high"),
    ("На душу", "NY.GDP.PCAP.CD", "usd_pc", "high"),
    ("Население", "SP.POP.TOTL", "people", "high"),
    ("Воен.расх.", "MS.MIL.XPND.CD", "usd", "high"),
    ("Воен.% ВВП", "MS.MIL.XPND.GD.ZS", "pct", "high"),
    ("Инфляция", "FP.CPI.TOTL.ZG", "pct", "low"),
    ("Безработ.", "SL.UEM.TOTL.ZS", "pct", "low"),
    ("Жизнь, лет", "SP.DYN.LE00.IN", "years", "high"),
]


def find_countries(text: str) -> list:
    """Все страны из текста в порядке упоминания: ['RUS', 'USA']."""
    t = (text or "").lower()
    taken, found = [], []
    for pat, iso in _COUNTRY_PATTERNS:  # длинные ключи первыми
        for m in pat.finditer(t):
            if any(not (m.end() <= a or m.start() >= b) for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), iso))
    out = []
    for _, iso in sorted(found):
        if iso not in out:
            out.append(iso)
    return out


async def fetch_value(iso3: str, code: str, year: int = None):
    """(значение, год) последнего доступного значения не позже year, либо None."""
    last = year or datetime.now().year
    data = await _get_json(
        f"{WB}/country/{iso3}/indicator/{code}",
        {"format": "json", "per_page": 30, "date": f"{last - 8}:{last}"},
    )
    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        return None
    for rec in data[1]:
        if rec.get("value") is not None:
            return rec["value"], str(rec["date"])
    return None


# ---------------------------------------------------------------------
# Новые страны, появившиеся в РП (хранятся в БД, бот их запоминает)
# ---------------------------------------------------------------------

_custom = {}


def custom_countries() -> dict:
    return dict(_custom)


def _rebuild():
    global _COUNTRY_PATTERNS
    merged = dict(COUNTRIES)
    merged.update(_custom)
    _COUNTRY_PATTERNS = _compile(merged)


def _label(name: str) -> str:
    name = name.strip()
    return name[:1].upper() + name[1:]


def register_country(name: str) -> str:
    key = re.sub(r"\s+", " ", name.strip().lower())
    code = _custom.get(key) or "X_" + re.sub(r"\W+", "_", key.upper()).strip("_")
    _custom[key] = code
    ISO_RU[code] = _label(name)
    _rebuild()
    return code


def load_custom(raw):
    if not raw:
        return
    try:
        data = json.loads(raw)
    except ValueError:
        return
    for key, code in data.items():
        _custom[key] = code
        ISO_RU[code] = _label(key)
    _rebuild()
