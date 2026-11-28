"""
GEO.PY — география для войн и давления: сухопутные границы, регионы и достижимость.

Страны воюют с соседями и страной из того же региона куда охотнее, чем с кем-то на другом конце света;
анклавы вроде Ватикана достать можно только через окружающую страну, остальным остаётся десант (ВДВ).
Для стран, которых нет в таблице (придуманных в РП), расстояние неизвестно — считаем их «в соседних регионах».
"""
# страна → регион
REGION = {}
for _reg, _codes in {
    "NAM": "USA CAN MEX", "CAR": "CUB ATG BHS BRB BLZ CRI DMA DOM SLV GRD GTM HTI HND JAM KNA LCA VCT NIC PAN TTO",
    "SAM": "ARG BOL BRA CHL COL ECU PRY PER URY VEN GUY SUR",
    "WEU": "FRA ESP PRT GBR IRL BEL NLD LUX CHE AUT DEU ITA MLT VAT SMR AND LIE MCO",
    "NEU": "NOR SWE FIN DNK ISL",
    "CEU": "POL CZE SVK HUN SVN",
    "BAL": "ALB BIH HRV MKD MNE SRB GRC BGR ROU CYP",
    "EEU": "RUS UKR BLR MDA EST LVA LTU",
    "CAU": "ARM AZE GEO",
    "CAS": "KAZ KGZ TJK TKM UZB AFG",
    "ME": "TUR IRN IRQ SYR LBN JOR ISR SAU ARE QAT KWT OMN YEM BHR PSE",
    "NAF": "DZA EGY LBY MAR TUN SDN",
    "SSA": "AGO ETH GHA KEN NGA TZA ZAF LSO BEN BWA BFA BDI CPV CMR CAF TCD COM COG COD CIV DJI GNQ ERI SWZ GAB GMB GIN GNB LBR MDG MWI MLI MRT MUS MOZ NAM NER RWA STP SEN SYC SLE SOM SSD TGO UGA ZMB ZWE",
    "SAS": "BGD BTN IND LKA NPL PAK MDV",
    "SEA": "IDN KHM LAO MMR MYS PHL SGP THA VNM BRN TLS",
    "EAS": "CHN JPN KOR PRK MNG TWN TIB",
    "OCE": "AUS NZL PNG FJI KIR MHL FSM NRU PLW WSM SLB TON TUV VUT",
}.items():
    for _c in _codes.split():
        REGION[_c] = _reg

# соседние регионы (симметрично)
_ADJ = ["WEU-NEU", "WEU-CEU", "WEU-NAF", "WEU-BAL", "CEU-EEU", "CEU-BAL", "CEU-NEU", "EEU-NEU", "EEU-CAU", "EEU-CAS", "EEU-EAS",
        "EEU-BAL", "BAL-ME", "BAL-NAF", "CAU-ME", "CAU-CAS", "CAS-ME", "CAS-SAS", "CAS-EAS", "ME-NAF", "ME-SAS", "ME-SSA",
        "NAF-SSA", "SAS-SEA", "SAS-EAS", "SEA-EAS", "SEA-OCE", "NAM-CAR", "NAM-SAM", "CAR-SAM"]
REG_ADJ = {}
for _p in _ADJ:
    _a, _b = _p.split("-")
    REG_ADJ.setdefault(_a, set()).add(_b)
    REG_ADJ.setdefault(_b, set()).add(_a)

# сухопутные границы (дальше достраиваются симметрично)
_BORDERS = {
    "AFG": "IRN PAK TKM UZB TJK CHN", "ALB": "GRC MKD MNE", "ARE": "SAU OMN", "ARG": "BOL BRA CHL PRY URY",
    "ARM": "AZE GEO IRN TUR", "AUT": "CZE DEU HUN ITA SVK SVN CHE", "AZE": "GEO IRN RUS TUR", "BEL": "FRA DEU LUX NLD",
    "BGD": "IND MMR", "BGR": "GRC MKD ROU SRB TUR", "BIH": "HRV MNE SRB", "BLR": "LVA LTU POL RUS UKR",
    "BOL": "BRA CHL PRY PER", "BRA": "COL PRY PER URY VEN", "BTN": "CHN IND", "CAN": "USA", "CHE": "FRA DEU ITA",
    "CHL": "PER", "CHN": "BTN IND KAZ KGZ LAO MNG MMR NPL PAK PRK RUS TJK VNM TIB", "COL": "ECU PER VEN",
    "CZE": "DEU POL SVK", "DEU": "CZE DNK FRA LUX NLD POL", "DZA": "LBY MAR TUN", "ECU": "PER", "EGY": "ISR LBY SDN",
    "ESP": "FRA PRT", "EST": "LVA RUS", "ETH": "KEN SDN", "FIN": "NOR RUS SWE", "FRA": "ITA LUX", "GBR": "IRL",
    "GEO": "RUS TUR", "GRC": "MKD TUR", "HRV": "HUN SRB SVN MNE", "HUN": "ROU SRB SVK SVN UKR", "IDN": "MYS",
    "IND": "MMR NPL PAK TIB", "IRN": "IRQ PAK TKM TUR", "IRQ": "JOR KWT SAU SYR TUR", "ISR": "JOR LBN SYR",
    "ITA": "SVN VAT SMR", "JOR": "SAU SYR", "KAZ": "KGZ RUS TKM UZB", "KEN": "TZA", "KGZ": "TJK UZB", "KHM": "LAO THA VNM",
    "KOR": "PRK", "KWT": "SAU", "LAO": "MMR THA VNM", "LBN": "SYR", "LBY": "SDN TUN", "LTU": "LVA POL RUS", "LUX": "FRA",
    "LVA": "RUS", "MDA": "ROU UKR", "MEX": "USA", "MKD": "SRB", "MMR": "THA", "MNE": "SRB", "MNG": "RUS", "MYS": "SGP THA",
    "NOR": "RUS SWE", "NPL": "TIB", "OMN": "SAU YEM", "PAK": "CHN", "POL": "RUS SVK UKR", "PRK": "RUS", "PRY": "BRA",
    "QAT": "SAU", "ROU": "SRB UKR", "RUS": "UKR", "SAU": "YEM", "SDN": "ETH", "SRB": "ROU", "SVK": "UKR", "SYR": "TUR",
    "TIB": "BTN", "TJK": "UZB", "TKM": "UZB", "TUN": "LBY", "TUR": "IRN", "UKR": "SVK", "URY": "BRA", "UZB": "AFG",
    "VNM": "CHN", "ZAF": "LSO",

    "PNG": "IDN", "TLS": "IDN", "BRN": "MYS", "GUY": "VEN BRA SUR", "SUR": "BRA", "CRI": "NIC PAN", "GTM": "MEX BLZ HND SLV",
    "HND": "NIC SLV", "PAN": "COL CRI", "HTI": "DOM", "SEN": "GMB MLI MRT GIN GNB", "GIN": "SLE LBR CIV MLI GNB", "MLI": "MRT NER BFA CIV",
    "NER": "NGA BEN BFA TCD", "TCD": "SDN CAF CMR NGA", "CMR": "NGA CAF GNQ GAB COG", "COD": "AGO ZMB TZA RWA BDI UGA CAF COG SSD",
    "ZMB": "ZWE MOZ MWI AGO TZA NAM BWA", "ZWE": "MOZ BWA ZAF", "MOZ": "MWI TZA ZAF SWZ", "NAM": "AGO ZMB BWA ZAF", "BWA": "ZAF",
    "UGA": "KEN TZA RWA SSD", "SSD": "SDN ETH KEN CAF", "SOM": "ETH KEN DJI", "ERI": "ETH SDN DJI", "PSE": "ISR EGY JOR",
    "AND": "FRA ESP", "MCO": "FRA", "LIE": "CHE AUT", "GAB": "COG GNQ CMR", "GHA": "CIV BFA TGO", "TGO": "BEN BFA GHA", "NGA": "BEN",
    "ETH": "DJI SOM", "RWA": "BDI TZA UGA",
}
NB = {}
for _a, _lst in _BORDERS.items():
    for _b in _lst.split():
        NB.setdefault(_a, set()).add(_b)
        NB.setdefault(_b, set()).add(_a)

# анклавы: страна → окружающая её страна (до них доберётся по земле только она)
ENCLAVES = {"VAT": "ITA", "SMR": "ITA", "LSO": "ZAF"}

_WEIGHT = {"border": 1.0, "region": 0.35, "near": 0.06, "far": 0.003, "unknown": 0.1}     # как охотно выбирают такую цель
_PROJ = {"border": 1.0, "region": 0.8, "near": 0.55, "far": 0.3, "unknown": 0.6}          # какая доля силы достаёт до цели
_HOW = {"border": "сухопутная граница", "region": "один регион: через соседей и по морю", "near": "соседние регионы: нужен флот и авиация",
        "far": "другой край света: только флот, авиация и десант", "unknown": "расстояние неизвестно"}


def relation(a: str, b: str) -> str:
    """border | region | near | far | unknown | air (анклав, который не достать по земле)."""
    if b in ENCLAVES:
        return "border" if ENCLAVES[b] == a else "air"
    if a in ENCLAVES:
        return "border" if ENCLAVES[a] == b else "air"
    if b in NB.get(a, ()):
        return "border"
    ra, rb = REGION.get(a), REGION.get(b)
    if not ra or not rb:
        return "unknown"
    if ra == rb:
        return "region"
    return "near" if rb in REG_ADJ.get(ra, ()) else "far"


def weight(a: str, b: str) -> float:
    """Множитель шанса выбрать b целью для a."""
    rel = relation(a, b)
    return 0.03 if rel == "air" else _WEIGHT[rel]


def projection(a: str, b: str) -> tuple:
    """(доля силы, достающая до цели; пояснение). Анклав без общей границы достаётся только десантом (ВДВ)."""
    rel = relation(a, b)
    if rel == "air":
        return 0.03, "цель — анклав: по земле её не достать, только десантом (ВДВ)"
    return _PROJ[rel], _HOW[rel]


def how(a: str, b: str) -> str:
    return projection(a, b)[1]


def can_occupy(a: str, b: str) -> bool:
    """Может ли a в одиночку занять и присоединить b: нужна общая граница или один регион."""
    return relation(a, b) in ("border", "region")


# ---- новые государства (после референдумов): наследуют регион родительской страны и граничат с ней
def register(iso: str, parent: str):
    """Пишет в БД (вызывать через db.arun)."""
    import json

    import database as db
    REGION[iso] = REGION.get(parent) or REGION.get(iso, "")
    if not REGION[iso]:
        REGION.pop(iso, None)
    NB.setdefault(iso, set()).add(parent)
    NB.setdefault(parent, set()).add(iso)
    try:
        data = json.loads(db.get_setting("geo_custom") or "[]")
    except ValueError:
        data = []
    if [iso, parent] not in data:
        data.append([iso, parent])
        db.set_setting("geo_custom", json.dumps(data))


def load_dynamic(raw):
    """При запуске бота: вернуть в таблицу новые государства."""
    import json
    try:
        for iso, parent in json.loads(raw or "[]"):
            REGION[iso] = REGION.get(parent) or REGION.get(iso, "")
            if not REGION[iso]:
                REGION.pop(iso, None)
            NB.setdefault(iso, set()).add(parent)
            NB.setdefault(parent, set()).add(iso)
    except (ValueError, TypeError):
        pass
