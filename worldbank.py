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
    if key.startswith("="):                      # точное слово без окончаний (мали, чад, нигер — чтобы не цеплять «мало»)
        return re.compile(r"(?<!\w)" + re.escape(key[1:]) + r"(?!\w)")
    if not re.search(r"[а-яё]", key):
        pat = r"(?<!\w)" + re.escape(key) + r"(?!\w)"
    elif re.search(r"[\s\-—–]", key):           # несколько слов: у каждого длинного допускаем окончание («новой зеландии», «южной кореи»)
        parts = [p for p in re.split(r"[\s\-—–]+", key) if p]
        pats = [re.escape(p[:-2] if len(p) >= 5 else p[:-1]) + r"\w{0,3}" if len(p) >= 4 else re.escape(p) for p in parts]
        pat = r"(?<!\w)" + r"[\s\-—–]+".join(pats) + r"(?!\w)"
    elif len(key) < 4:
        pat = r"(?<!\w)" + re.escape(key) + r"(?!\w)"
    else:  # русские слова: допускаем окончания («россии», «китае», «инфляции»)
        pat = r"(?<!\w)" + re.escape(key[:-1]) + r"\w{0,2}(?!\w)"
    return re.compile(pat)


def _compile(d: dict) -> list:
    return [(_kw_pattern(k), v) for k, v in sorted(d.items(), key=lambda kv: -len(kv[0]))]


COUNTRIES.update({
    "британия": "GBR", "бутан": "BTN", "непал": "NPL", "монголия": "MNG", "афганистан": "AFG", "ирак": "IRQ",
    "сирия": "SYR", "ливан": "LBN", "иордания": "JOR", "йемен": "YEM", "оман": "OMN", "катар": "QAT", "кувейт": "KWT",
    "оаэ": "ARE", "таиланд": "THA", "вьетнам": "VNM", "лаос": "LAO", "камбоджа": "KHM", "мьянма": "MMR", "бирма": "MMR",
    "филиппины": "PHL", "малайзия": "MYS", "сингапур": "SGP", "бангладеш": "BGD", "шри-ланка": "LKA", "куба": "CUB",
    "венесуэла": "VEN", "колумбия": "COL", "перу": "PER", "чили": "CHL", "боливия": "BOL", "эквадор": "ECU",
    "уругвай": "URY", "парагвай": "PRY", "португалия": "PRT", "австрия": "AUT", "бельгия": "BEL", "дания": "DNK",
    "ирландия": "IRL", "исландия": "ISL", "словакия": "SVK", "словения": "SVN", "хорватия": "HRV", "босния": "BIH",
    "албания": "ALB", "македония": "MKD", "черногория": "MNE", "кипр": "CYP", "мальта": "MLT", "люксембург": "LUX",
    "алжир": "DZA", "ливия": "LBY", "тунис": "TUN", "марокко": "MAR", "судан": "SDN", "эфиопия": "ETH",
    "нигерия": "NGA", "кения": "KEN", "танзания": "TZA", "ангола": "AGO", "гана": "GHA", "новая зеландия": "NZL",
    "таджикистан": "TJK", "киргизия": "KGZ", "туркменистан": "TKM", "тайвань": "TWN", "сербия": "SRB", "тибет": "TIB",
})
COUNTRIES.update({
    'андорра': 'AND',
    'антигуа и барбуда': 'ATG',
    'антигуа': 'ATG',
    'багамы': 'BHS',
    'багамские острова': 'BHS',
    'бахрейн': 'BHR',
    'барбадос': 'BRB',
    'белиз': 'BLZ',
    'бенин': 'BEN',
    'ботсвана': 'BWA',
    'бруней': 'BRN',
    'буркина-фасо': 'BFA',
    'буркина фасо': 'BFA',
    'бурунди': 'BDI',
    'кабо-верде': 'CPV',
    'кабо верде': 'CPV',
    'камерун': 'CMR',
    'центральноафриканская республика': 'CAF',
    '=цар': 'CAF',
    '=чад': 'TCD',
    'коморы': 'COM',
    'коморские острова': 'COM',
    'республика конго': 'COG',
    'конго-браззавиль': 'COG',
    'демократическая республика конго': 'COD',
    'др конго': 'COD',
    '=конго': 'COD',
    'коста-рика': 'CRI',
    'коста рика': 'CRI',
    'кот-д’ивуар': 'CIV',
    "кот-д'ивуар": 'CIV',
    'берег слоновой кости': 'CIV',
    'джибути': 'DJI',
    'доминика': 'DMA',
    'доминиканская республика': 'DOM',
    'доминикана': 'DOM',
    'сальвадор': 'SLV',
    'экваториальная гвинея': 'GNQ',
    'эритрея': 'ERI',
    'эсватини': 'SWZ',
    'свазиленд': 'SWZ',
    'фиджи': 'FJI',
    'габон': 'GAB',
    'гамбия': 'GMB',
    'гренада': 'GRD',
    'гватемала': 'GTM',
    'гвинея-бисау': 'GNB',
    'гвинея бисау': 'GNB',
    'гвинея': 'GIN',
    'гайана': 'GUY',
    'гаити': 'HTI',
    'гондурас': 'HND',
    'ямайка': 'JAM',
    'кирибати': 'KIR',
    'лесото': 'LSO',
    'либерия': 'LBR',
    'лихтенштейн': 'LIE',
    'мадагаскар': 'MDG',
    'малави': 'MWI',
    'мальдивы': 'MDV',
    '=мали': 'MLI',
    'маршалловы острова': 'MHL',
    'мавритания': 'MRT',
    'маврикий': 'MUS',
    'микронезия': 'FSM',
    'монако': 'MCO',
    'мозамбик': 'MOZ',
    'намибия': 'NAM',
    'науру': 'NRU',
    'никарагуа': 'NIC',
    '=нигер': 'NER',
    'палау': 'PLW',
    'панама': 'PAN',
    'папуа — новая гвинея': 'PNG',
    'папуа-новая гвинея': 'PNG',
    'папуа новая гвинея': 'PNG',
    'новая гвинея': 'PNG',
    'папуа': 'PNG',
    'сент-китс и невис': 'KNA',
    'сент-люсия': 'LCA',
    'сент-винсент и гренадины': 'VCT',
    'самоа': 'WSM',
    'сан-марино': 'SMR',
    'сан-томе и принсипи': 'STP',
    'сенегал': 'SEN',
    'сейшелы': 'SYC',
    'сьерра-леоне': 'SLE',
    'соломоновы острова': 'SLB',
    'сомали': 'SOM',
    'южный судан': 'SSD',
    'суринам': 'SUR',
    'восточный тимор': 'TLS',
    'тимор-лесте': 'TLS',
    'тонга': 'TON',
    'тринидад и тобаго': 'TTO',
    'тувалу': 'TUV',
    'уганда': 'UGA',
    'вануату': 'VUT',
    'ватикан': 'VAT',
    'замбия': 'ZMB',
    'зимбабве': 'ZWE',
    'палестина': 'PSE',
    'руанда': 'RWA',
})
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

# названия новых стран для вывода (ISO_RU берёт первый ключ, а он может быть служебным)
NEW_NAMES = {'AND': 'Андорра', 'ATG': 'Антигуа и Барбуда', 'BHS': 'Багамы', 'BHR': 'Бахрейн', 'BRB': 'Барбадос', 'BLZ': 'Белиз', 'BEN': 'Бенин', 'BWA': 'Ботсвана', 'BRN': 'Бруней', 'BFA': 'Буркина-Фасо', 'BDI': 'Бурунди', 'CPV': 'Кабо-Верде', 'CMR': 'Камерун', 'CAF': 'ЦАР', 'TCD': 'Чад', 'COM': 'Коморы', 'COG': 'Республика Конго', 'COD': 'ДР Конго', 'CRI': 'Коста-Рика', 'CIV': 'Кот-д’Ивуар', 'DJI': 'Джибути', 'DMA': 'Доминика', 'DOM': 'Доминиканская Республика', 'SLV': 'Сальвадор', 'GNQ': 'Экваториальная Гвинея', 'ERI': 'Эритрея', 'SWZ': 'Эсватини', 'FJI': 'Фиджи', 'GAB': 'Габон', 'GMB': 'Гамбия', 'GRD': 'Гренада', 'GTM': 'Гватемала', 'GNB': 'Гвинея-Бисау', 'GIN': 'Гвинея', 'GUY': 'Гайана', 'HTI': 'Гаити', 'HND': 'Гондурас', 'JAM': 'Ямайка', 'KIR': 'Кирибати', 'LSO': 'Лесото', 'LBR': 'Либерия', 'LIE': 'Лихтенштейн', 'MDG': 'Мадагаскар', 'MWI': 'Малави', 'MDV': 'Мальдивы', 'MLI': 'Мали', 'MHL': 'Маршалловы Острова', 'MRT': 'Мавритания', 'MUS': 'Маврикий', 'FSM': 'Микронезия', 'MCO': 'Монако', 'MOZ': 'Мозамбик', 'NAM': 'Намибия', 'NRU': 'Науру', 'NIC': 'Никарагуа', 'NER': 'Нигер', 'PLW': 'Палау', 'PAN': 'Панама', 'PNG': 'Папуа — Новая Гвинея', 'KNA': 'Сент-Китс и Невис', 'LCA': 'Сент-Люсия', 'VCT': 'Сент-Винсент и Гренадины', 'WSM': 'Самоа', 'SMR': 'Сан-Марино', 'STP': 'Сан-Томе и Принсипи', 'SEN': 'Сенегал', 'SYC': 'Сейшелы', 'SLE': 'Сьерра-Леоне', 'SLB': 'Соломоновы Острова', 'SOM': 'Сомали', 'SSD': 'Южный Судан', 'SUR': 'Суринам', 'TLS': 'Восточный Тимор', 'TON': 'Тонга', 'TTO': 'Тринидад и Тобаго', 'TUV': 'Тувалу', 'UGA': 'Уганда', 'VUT': 'Вануату', 'VAT': 'Ватикан', 'ZMB': 'Замбия', 'ZWE': 'Зимбабве', 'PSE': 'Палестина', 'RWA': 'Руанда'}
ISO_RU.update(NEW_NAMES)
for _iso, _n in list(ISO_RU.items()):                   # «Южная корея» → «Южная Корея»
    if " " in _n and _iso not in NEW_NAMES and _n == _n.capitalize():
        ISO_RU[_iso] = " ".join(w.capitalize() for w in _n.split())

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
