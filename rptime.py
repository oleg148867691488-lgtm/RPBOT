"""
RPTIME.PY — время внутри РП.
24 реальных часа = 365 дней РП (2 часа ≈ 1 месяц). Отсчёт идёт от момента /year.
Исправлено: 29 февраля / 31-е число больше не роняют расчёт (дата корректно подгоняется).
"""

import logging
import time
from datetime import datetime, timedelta, timezone

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


def _safe_date(year: int, month: int, day: int) -> datetime:
    while day > 0:
        try:
            return datetime(year, month, day)
        except ValueError:
            day -= 1
    return datetime(year, 1, 1)


def set_rp_year(year: int):
    """Запускает отсчёт РП с указанного года (синхронная, выполнять через db.arun)."""
    n = now_msk()
    db.set_setting("rp_year", str(year))
    db.set_setting("rp_start_time", str(time.time()))
    db.set_setting("rp_start_month", str(n.month))
    db.set_setting("rp_start_day", str(n.day))
    return n


def get_rp_datetime() -> dict:
    saved_year = db.get_setting("rp_year")
    saved_start = db.get_setting("rp_start_time")
    if not saved_year or not saved_start:
        return dict(_EMPTY)
    try:
        base_year = int(saved_year)
        start_ts = float(saved_start)
        base_month = int(db.get_setting("rp_start_month", "1"))
        base_day = int(db.get_setting("rp_start_day", "1"))
        now = now_msk()
        elapsed_h = max(0.0, (now.timestamp() - start_ts) / 3600)
        rp_days = elapsed_h * C.RP_DAYS_PER_REAL_HOUR
        rp_date = _safe_date(base_year, base_month, base_day) + timedelta(days=rp_days)
        next_year = datetime(rp_date.year + 1, 1, 1)
        return {
            "year": rp_date.year,
            "month": rp_date.month,
            "day": rp_date.day,
            "hour": rp_date.hour,
            "full": rp_date.strftime("%d.%m.%Y %H:%M"),
            "elapsed_hours": elapsed_h,
            "rp_days": rp_days,
            "real_msk": now.strftime("%d.%m.%Y %H:%M:%S"),
            "days_to_new_year": (next_year - rp_date).days,
        }
    except (ValueError, TypeError, OverflowError) as e:
        log.warning("Не удалось посчитать время РП: %s", e)
        return dict(_EMPTY)
