"""
RPTIME.PY — время внутри РП (по московскому времени, привязано к настоящим часам).

• Каждые реальные сутки по МСК = 1 год РП: в 00:00 МСК наступает Новый год (год +1).
• Год делится на 12 равных месяцев по 2 часа: 00–02 — январь, 02–04 — февраль, …, 10–12 — июнь, 12–14 — июль, …
• Внутри месяца идут дни и часы РП пропорционально прошедшему времени.
Команда /year ГОД задаёт, какой год РП идёт СЕЙЧАС (в этот реальный день).
"""

import calendar
import logging
from datetime import date, datetime, time as dtime, timedelta, timezone

import config as C
import database as db

log = logging.getLogger(__name__)

_EMPTY = {
    "year": None, "month": None, "day": None, "hour": None, "full": None,
    "elapsed_hours": 0.0, "rp_days": 0.0, "real_msk": None, "days_to_new_year": None,
}


def now_msk() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Moscow"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=3)))


def set_rp_year(year: int):
    """Сейчас идёт указанный год РП. Синхронная — выполнять через db.arun."""
    n = now_msk()
    db.set_setting("rp_year", str(year))
    db.set_setting("rp_anchor_date", n.date().isoformat())
    return n


def _anchor(now: datetime) -> date:
    raw = db.get_setting("rp_anchor_date")
    if raw:
        return date.fromisoformat(raw)
    st = db.get_setting("rp_start_time")           # базы старой версии
    return datetime.fromtimestamp(float(st), tz=now.tzinfo).date() if st else now.date()


def get_rp_datetime() -> dict:
    saved_year = db.get_setting("rp_year")
    if not saved_year:
        return dict(_EMPTY)
    try:
        base = int(saved_year)
        now = now_msk()
        anchor = _anchor(now)
        year = base + (now.date() - anchor).days
        f = (now.hour * 3600 + now.minute * 60 + now.second) / 86400        # доля реальных суток = доля года
        m = min(11, int(f * 12))                                              # месяц меняется каждые 2 часа
        g = f * 12 - m
        dim = calendar.monthrange(year, m + 1)[1]
        dayf = g * dim
        day = min(dim, 1 + int(dayf))
        rest = (dayf % 1) * 24
        hour, minute = int(rest), int((rest % 1) * 60)
        dt = datetime(year, m + 1, day, hour, minute)
        total = 366 if calendar.isleap(year) else 365
        doy = sum(calendar.monthrange(year, i)[1] for i in range(1, m + 1)) + dayf
        elapsed = (now - datetime.combine(anchor, dtime(0, 0), tzinfo=now.tzinfo)).total_seconds() / 3600
        return {
            "year": year, "month": m + 1, "day": day, "hour": hour,
            "full": dt.strftime("%d.%m.%Y %H:%M"),
            "elapsed_hours": max(0.0, elapsed), "rp_days": max(0.0, elapsed) * C.RP_DAYS_PER_REAL_HOUR,
            "real_msk": now.strftime("%d.%m.%Y %H:%M:%S"),
            "days_to_new_year": max(0, int(total - doy)),
        }
    except (ValueError, TypeError, OverflowError) as e:
        log.warning("Не удалось посчитать время РП: %s", e)
        return dict(_EMPTY)
