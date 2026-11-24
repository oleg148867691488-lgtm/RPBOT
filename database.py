"""
DATABASE.PY — хранилище: Turso (libsql) или локальный SQLite.

Главное отличие от старой версии:
- ВСЕ обращения к БД идут через arun(): они выполняются в одном отдельном потоке,
  поэтому event loop бота больше не «замирает» на сетевых запросах к Turso,
  а соединение никогда не используется из разных потоков.
- Настройки кэшируются в памяти: get_setting() не ходит в сеть.
- Автопереподключение при обрывах соединения (stream not found и т.п.).

ВАЖНО: функции этого модуля синхронные. Из async-кода вызывай их так:
    rows = await db.arun(db.get_all_tags)
Исключение: get_setting() — читает кэш и вызывается напрямую.
"""

import asyncio
import functools
import json
import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import config as C

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db")
_lock = threading.RLock()
_conn = None

_RETRY_MARKERS = (
    "stream not found", "hrana", "404", "connection", "closed",
    "timed out", "timeout", "broken pipe", "expired", "reset by peer",
)


async def arun(fn, *args, **kwargs):
    """Выполнить синхронную функцию БД в выделенном потоке."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, functools.partial(fn, *args, **kwargs))


# =====================================================================
# ПОДКЛЮЧЕНИЕ
# =====================================================================

def _connect():
    if C.TURSO_URL and C.TURSO_KEY:
        import libsql
        return libsql.connect(database=C.TURSO_URL, auth_token=C.TURSO_KEY)
    return sqlite3.connect("facts.db", check_same_thread=False)


def close_conn():
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None


def execute(query: str, params: tuple = (), retries: int = 2) -> list:
    """Выполняет запрос. SELECT возвращает list[dict]. При обрыве соединения переподключается."""
    global _conn
    with _lock:
        for attempt in range(retries + 1):
            try:
                if _conn is None:
                    _conn = _connect()
                cur = _conn.cursor()
                cur.execute(query, params)
                rows = []
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                _conn.commit()
                return rows
            except Exception as e:
                msg = str(e).lower()
                if attempt < retries and any(m in msg for m in _RETRY_MARKERS):
                    log.warning("Turso: обрыв соединения (попытка %d/%d): %s", attempt + 1, retries + 1, str(e)[:100])
                    close_conn()
                    time.sleep(0.3 * (attempt + 1))
                    continue
                raise
    return []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# =====================================================================
# ИНИЦИАЛИЗАЦИЯ
# =====================================================================

def init_db():
    execute("""
    CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag TEXT NOT NULL,
        text TEXT NOT NULL,
        author_id INTEGER,
        author_name TEXT,
        year INTEGER,
        is_verdict INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    execute("CREATE INDEX IF NOT EXISTS idx_facts_tag ON facts(tag)")
    execute("CREATE INDEX IF NOT EXISTS idx_facts_verdict ON facts(is_verdict)")
    execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        is_summary INTEGER DEFAULT 0,
        is_archived INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    execute("CREATE INDEX IF NOT EXISTS idx_history_user ON history(chat_id, user_id, is_archived)")
    execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS world_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        kind TEXT NOT NULL,
        country TEXT,
        severity INTEGER DEFAULT 1,
        text TEXT NOT NULL,
        rp_year INTEGER,
        effects TEXT
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS ops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        user_id INTEGER,
        user_name TEXT,
        actor TEXT,
        target TEXT,
        role TEXT,
        budget INTEGER,
        outcome TEXT,
        revealed TEXT,
        summary TEXT
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS player_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        user_id INTEGER,
        user_name TEXT,
        country TEXT,
        text TEXT,
        summary TEXT,
        effects TEXT
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS daily_usage (
        user_id INTEGER NOT NULL,
        day TEXT NOT NULL,
        kind TEXT NOT NULL,
        cnt INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, day, kind)
    )""")

    execute("""
    CREATE TABLE IF NOT EXISTS country_state (
        country TEXT PRIMARY KEY,
        stability INTEGER NOT NULL DEFAULT 60,
        tension INTEGER NOT NULL DEFAULT 30,
        security INTEGER NOT NULL DEFAULT 5
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        countries TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        severity INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'draft',
        effects TEXT,
        secret TEXT,
        actor_id INTEGER,
        rp_date TEXT,
        created_at TEXT NOT NULL
    )""")
    execute("CREATE INDEX IF NOT EXISTS idx_events_status ON events(status, id)")
    execute("""
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        alive INTEGER NOT NULL DEFAULT 1
    )""")
    execute("CREATE TABLE IF NOT EXISTS player_country (user_id INTEGER PRIMARY KEY, country TEXT NOT NULL)")
    execute("""
    CREATE TABLE IF NOT EXISTS market (
        symbol TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        price REAL NOT NULL,
        history TEXT NOT NULL,
        updated_at TEXT
    )""")

    # Уборка мусора: старые лимиты и архивная история
    old_day = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    execute("DELETE FROM daily_usage WHERE day < ?", (old_day,))
    execute("DELETE FROM settings WHERE key LIKE 'verdict_limit_%'")  # хвосты старой версии
    old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    execute("DELETE FROM history WHERE is_archived = 1 AND created_at < ?", (old_ts,))

    _create_extra_tables()
    try:                                      # старые базы: добавляем колонку эффектов (нужна для отката)
        execute("ALTER TABLE world_events ADD COLUMN effects TEXT")
    except Exception:
        pass
    load_settings()


# =====================================================================
# SETTINGS (кэш в памяти)
# =====================================================================

_settings: dict = {}


def load_settings():
    global _settings
    rows = execute("SELECT key, value FROM settings")
    _settings = {r["key"]: r["value"] for r in rows}


def get_setting(key: str, default=None):
    """Читает кэш (без обращения к сети) — можно вызывать прямо из async-кода."""
    return _settings.get(key, default)


def set_setting(key: str, value: str):
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    _settings[key] = str(value)


def delete_setting(key: str):
    execute("DELETE FROM settings WHERE key = ?", (key,))
    _settings.pop(key, None)


# =====================================================================
# ФАКТЫ
# =====================================================================

_tags_cache = (0.0, [])


def _invalidate_tags():
    global _tags_cache
    _tags_cache = (0.0, [])


def add_fact(tag: str, text: str, author_id: int = 0, author_name: str = "",
             year: int = None, is_verdict: bool = False) -> int:
    """Добавляет факт. Возвращает id, либо 0 если точно такой факт уже есть."""
    tag = tag.lower().strip()
    text = text.strip()
    with _lock:
        if not is_verdict:
            dup = execute(
                "SELECT id FROM facts WHERE tag = ? AND text = ? AND is_verdict = 0 LIMIT 1",
                (tag, text),
            )
            if dup:
                return 0
        execute(
            "INSERT INTO facts (tag, text, author_id, author_name, year, is_verdict, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tag, text, author_id, author_name, year, 1 if is_verdict else 0, _now()),
        )
        rows = execute("SELECT last_insert_rowid() AS id")
    _invalidate_tags()
    return rows[0]["id"] if rows else 0


def get_facts_by_tag(tag: str, include_verdicts: bool = True, limit: int = 200) -> list:
    tag = tag.lower().strip()
    if include_verdicts:
        return execute("SELECT * FROM facts WHERE tag = ? ORDER BY id DESC LIMIT ?", (tag, limit))
    return execute(
        "SELECT * FROM facts WHERE tag = ? AND is_verdict = 0 ORDER BY id DESC LIMIT ?", (tag, limit)
    )


def get_facts_page(tag: str, offset: int = 0, limit: int = 10) -> list:
    return execute(
        "SELECT * FROM facts WHERE tag = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        (tag.lower().strip(), limit, offset),
    )


def count_facts_by_tag(tag: str) -> int:
    rows = execute("SELECT COUNT(*) AS c FROM facts WHERE tag = ?", (tag.lower().strip(),))
    return rows[0]["c"] if rows else 0


def get_recent_facts(tags: list, limit: int = 12, verdicts: bool = False) -> list:
    """Самые НОВЫЕ факты (или вердикты) по списку тегов — одним запросом."""
    tags = [t.lower().strip() for t in tags if t][:60]
    if not tags:
        return []
    ph = ",".join("?" * len(tags))
    return execute(
        f"SELECT * FROM facts WHERE tag IN ({ph}) AND is_verdict = ? ORDER BY id DESC LIMIT ?",
        (*tags, 1 if verdicts else 0, limit),
    )


def get_timeline(tag: str, offset: int = 0, limit: int = 12) -> list:
    """Записи тега по годам (без года — в конце)."""
    return execute(
        "SELECT id, text, year, is_verdict FROM facts WHERE tag = ? "
        "ORDER BY CASE WHEN year IS NULL THEN 1 ELSE 0 END, year, id LIMIT ? OFFSET ?",
        (tag.lower().strip(), limit, offset),
    )


def get_world_facts(limit: int = 10) -> list:
    return execute(
        "SELECT * FROM facts WHERE substr(tag, 1, 6) = 'world_' ORDER BY id DESC LIMIT ?", (limit,)
    )


def get_all_tags() -> list:
    """Теги со статистикой. Кэшируется на 20 секунд."""
    global _tags_cache
    ts, data = _tags_cache
    if time.time() - ts < 20:
        return data
    data = execute(
        "SELECT tag, COUNT(*) AS cnt, COALESCE(SUM(is_verdict), 0) AS verdicts "
        "FROM facts GROUP BY tag ORDER BY cnt DESC"
    )
    _tags_cache = (time.time(), data)
    return data


def search_facts(query: str, limit: int = 30) -> list:
    q = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return execute(
        "SELECT * FROM facts WHERE text LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",
        (f"%{q}%", limit),
    )


def get_fact(fact_id: int):
    rows = execute("SELECT * FROM facts WHERE id = ?", (fact_id,))
    return rows[0] if rows else None


def delete_fact(fact_id: int) -> bool:
    with _lock:
        if not get_fact(fact_id):
            return False
        execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    _invalidate_tags()
    return True


def delete_tag(tag: str) -> int:
    tag = tag.lower().strip()
    with _lock:
        n = count_facts_by_tag(tag)
        if n:
            execute("DELETE FROM facts WHERE tag = ?", (tag,))
    _invalidate_tags()
    return n


def clear_all_facts():
    execute("DELETE FROM facts")
    _invalidate_tags()


def export_facts() -> list:
    return execute("SELECT * FROM facts ORDER BY id")


def get_stats() -> dict:
    rows = execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(is_verdict), 0) AS verdicts, "
        "COUNT(DISTINCT tag) AS tags FROM facts"
    )
    r = rows[0] if rows else {}
    return {"total": r.get("total", 0), "verdicts": r.get("verdicts", 0), "tags": r.get("tags", 0)}


# =====================================================================
# ИСТОРИЯ ДИАЛОГОВ
# =====================================================================

def add_history(chat_id: int, user_id: int, role: str, content: str, is_summary: bool = False):
    execute(
        "INSERT INTO history (chat_id, user_id, role, content, is_summary, is_archived, created_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (chat_id, user_id, role, content, 1 if is_summary else 0, _now()),
    )


def add_exchange(chat_id: int, user_id: int, question: str, answer: str):
    with _lock:
        add_history(chat_id, user_id, "user", question)
        add_history(chat_id, user_id, "assistant", answer)


def get_summary(chat_id: int, user_id: int):
    rows = execute(
        "SELECT content FROM history WHERE chat_id = ? AND user_id = ? "
        "AND is_archived = 0 AND is_summary = 1 ORDER BY id DESC LIMIT 1",
        (chat_id, user_id),
    )
    return rows[0]["content"] if rows else None


def get_context(chat_id: int, user_id: int, limit: int = 15):
    """Возвращает (резюме_или_None, последние_сообщения_по_порядку)."""
    summary = get_summary(chat_id, user_id)
    rows = execute(
        "SELECT role, content FROM history WHERE chat_id = ? AND user_id = ? "
        "AND is_archived = 0 AND is_summary = 0 ORDER BY id DESC LIMIT ?",
        (chat_id, user_id, limit),
    )
    return summary, list(reversed(rows))


def count_active_history(chat_id: int, user_id: int) -> int:
    rows = execute(
        "SELECT COUNT(*) AS c FROM history WHERE chat_id = ? AND user_id = ? "
        "AND is_archived = 0 AND is_summary = 0",
        (chat_id, user_id),
    )
    return rows[0]["c"] if rows else 0


def get_old_messages_for_summary(chat_id: int, user_id: int, batch: int = 20) -> list:
    return execute(
        "SELECT id, role, content FROM history WHERE chat_id = ? AND user_id = ? "
        "AND is_archived = 0 AND is_summary = 0 ORDER BY id ASC LIMIT ?",
        (chat_id, user_id, batch),
    )


def save_summary(chat_id: int, user_id: int, summary: str, archived_ids: list):
    """Архивирует сжатые сообщения и старое резюме, сохраняет новое резюме."""
    with _lock:
        if archived_ids:
            ph = ",".join("?" * len(archived_ids))
            execute(f"UPDATE history SET is_archived = 1 WHERE id IN ({ph})", tuple(archived_ids))
        execute(
            "UPDATE history SET is_archived = 1 WHERE chat_id = ? AND user_id = ? "
            "AND is_summary = 1 AND is_archived = 0",
            (chat_id, user_id),
        )
        add_history(chat_id, user_id, "system", summary, is_summary=True)


def clear_history(chat_id: int = None, user_id: int = None):
    if chat_id and user_id:
        execute("DELETE FROM history WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    elif chat_id:
        execute("DELETE FROM history WHERE chat_id = ?", (chat_id,))
    else:
        execute("DELETE FROM history")


# =====================================================================
# ДНЕВНЫЕ ЛИМИТЫ
# =====================================================================

def get_usage(user_id: int, day: str, kind: str) -> int:
    rows = execute(
        "SELECT cnt FROM daily_usage WHERE user_id = ? AND day = ? AND kind = ?", (user_id, day, kind)
    )
    return rows[0]["cnt"] if rows else 0


def inc_usage(user_id: int, day: str, kind: str):
    execute(
        "INSERT INTO daily_usage (user_id, day, kind, cnt) VALUES (?, ?, ?, 1) "
        "ON CONFLICT(user_id, day, kind) DO UPDATE SET cnt = cnt + 1",
        (user_id, day, kind),
    )


# =====================================================================
# СОСТОЯНИЕ СТРАН (ключ — код ISO3, например RUS)
# =====================================================================

_DEFAULT_STATE = {"stability": 60, "tension": 30, "security": 5}


def get_state(iso: str) -> dict:
    rows = execute("SELECT * FROM country_state WHERE country = ?", (iso,))
    return rows[0] if rows else {"country": iso, **_DEFAULT_STATE}


def all_states() -> list:
    return execute("SELECT * FROM country_state")


def _save_state(iso, stab, tens, sec):
    execute(
        "INSERT INTO country_state (country, stability, tension, security) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(country) DO UPDATE SET stability = excluded.stability, "
        "tension = excluded.tension, security = excluded.security",
        (iso, max(0, min(100, int(stab))), max(0, min(100, int(tens))), max(0, min(10, int(sec)))),
    )


def bump_state(iso: str, d_stab: int = 0, d_tens: int = 0, d_sec: int = 0):
    with _lock:
        st = get_state(iso)
        _save_state(iso, st["stability"] + d_stab, st["tension"] + d_tens, st["security"] + d_sec)


def set_security(iso: str, value: int):
    with _lock:
        st = get_state(iso)
        _save_state(iso, st["stability"], st["tension"], value)


def decay_states(with_security: bool = False):
    """Стабильность и напряжённость медленно возвращаются к норме (60 / 30)."""
    execute(
        "UPDATE country_state SET "
        "stability = CASE WHEN stability < 60 THEN MIN(60, stability + 2) "
        "WHEN stability > 60 THEN MAX(60, stability - 2) ELSE 60 END, "
        "tension = CASE WHEN tension > 30 THEN MAX(30, tension - 2) "
        "WHEN tension < 30 THEN MIN(30, tension + 2) ELSE 30 END"
    )
    if with_security:
        execute("UPDATE country_state SET security = CASE WHEN security > 5 THEN security - 1 "
                "WHEN security < 5 THEN security + 1 ELSE 5 END")


# =====================================================================
# СОБЫТИЯ
# =====================================================================

def add_event(kind: str, countries: list, title: str, body: str, severity: int = 1,
              status: str = "draft", effects: dict = None, secret: dict = None,
              actor_id: int = None, rp_date: str = "") -> int:
    with _lock:
        execute(
            "INSERT INTO events (kind, countries, title, body, severity, status, effects, secret, "
            "actor_id, rp_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, json.dumps(countries), title, body, severity, status,
             json.dumps(effects or {}, ensure_ascii=False), json.dumps(secret or {}, ensure_ascii=False),
             actor_id, rp_date, _now()),
        )
        rows = execute("SELECT last_insert_rowid() AS id")
    return rows[0]["id"]


def get_event(event_id: int):
    rows = execute("SELECT * FROM events WHERE id = ?", (event_id,))
    return rows[0] if rows else None


def set_event_status(event_id: int, status: str):
    execute("UPDATE events SET status = ? WHERE id = ?", (status, event_id))


def list_events(status: str = "published", limit: int = 5, offset: int = 0) -> list:
    return execute("SELECT * FROM events WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                   (status, limit, offset))


def count_events(status: str = "published") -> int:
    rows = execute("SELECT COUNT(*) AS c FROM events WHERE status = ?", (status,))
    return rows[0]["c"] if rows else 0


def recent_events(limit: int = 10) -> list:
    return execute("SELECT * FROM events WHERE status = 'published' ORDER BY id DESC LIMIT ?", (limit,))


def list_user_ops(user_id: int, limit: int = 5) -> list:
    return execute("SELECT * FROM events WHERE actor_id = ? AND substr(kind, 1, 3) = 'op_' "
                   "ORDER BY id DESC LIMIT ?", (user_id, limit))


# =====================================================================
# ПЕРСОНАЖИ РП, СТРАНЫ ИГРОКОВ
# =====================================================================

def add_character(country: str, name: str, role: str) -> int:
    with _lock:
        execute("INSERT INTO characters (country, name, role, alive) VALUES (?, ?, ?, 1)", (country, name, role))
        rows = execute("SELECT last_insert_rowid() AS id")
    return rows[0]["id"]


def list_characters(country: str = None, alive_only: bool = True) -> list:
    sql, params = "SELECT * FROM characters WHERE 1 = 1", []
    if country:
        sql += " AND country = ?"
        params.append(country)
    if alive_only:
        sql += " AND alive = 1"
    return execute(sql + " ORDER BY id", tuple(params))


def kill_character(char_id: int) -> bool:
    rows = execute("SELECT id FROM characters WHERE id = ?", (char_id,))
    if not rows:
        return False
    execute("UPDATE characters SET alive = 0 WHERE id = ?", (char_id,))
    return True


def set_player_country(user_id: int, country: str):
    execute("INSERT INTO player_country (user_id, country) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET country = excluded.country", (user_id, country))


def get_player_country(user_id: int):
    rows = execute("SELECT country FROM player_country WHERE user_id = ?", (user_id,))
    return rows[0]["country"] if rows else None


# =====================================================================
# СОБЫТИЯ МИРА И ОПЕРАЦИИ
# =====================================================================

def add_world_event(kind: str, country: str, severity: int, text: str, rp_year: int = None, effects: str = None) -> int:
    with _lock:
        execute(
            "INSERT INTO world_events (ts, kind, country, severity, text, rp_year, effects) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), kind, country, severity, text, rp_year, effects),
        )
        rows = execute("SELECT last_insert_rowid() AS id")
    return rows[0]["id"] if rows else 0


def _kinds_sql(kinds):
    if not kinds:
        return "", ()
    return f" WHERE kind IN ({','.join('?' * len(kinds))})", tuple(kinds)


def get_world_events(limit: int = 4, offset: int = 0, kinds=None) -> list:
    where, params = _kinds_sql(kinds)
    return execute(f"SELECT * FROM world_events{where} ORDER BY id DESC LIMIT ? OFFSET ?", (*params, limit, offset))


def count_world_events(kinds=None) -> int:
    where, params = _kinds_sql(kinds)
    rows = execute(f"SELECT COUNT(*) AS c FROM world_events{where}", params)
    return rows[0]["c"] if rows else 0


def add_op(user_id, user_name, actor, target, role, budget, outcome, revealed, summary) -> int:
    with _lock:
        execute(
            "INSERT INTO ops (ts, user_id, user_name, actor, target, role, budget, outcome, revealed, summary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), user_id, user_name, actor, target, role, budget, outcome, revealed, summary),
        )
        rows = execute("SELECT last_insert_rowid() AS id")
    return rows[0]["id"] if rows else 0


def get_ops(limit: int = 10) -> list:
    return execute("SELECT * FROM ops ORDER BY id DESC LIMIT ?", (limit,))


def add_player_action(user_id, user_name, country, text, summary, effects_json) -> int:
    with _lock:
        execute(
            "INSERT INTO player_actions (ts, user_id, user_name, country, text, summary, effects) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), user_id, user_name, country, text, summary, effects_json),
        )
        rows = execute("SELECT last_insert_rowid() AS id")
    return rows[0]["id"] if rows else 0


def get_player_actions(country: str, limit: int = 3) -> list:
    return execute("SELECT * FROM player_actions WHERE country = ? ORDER BY id DESC LIMIT ?", (country, limit))


def get_world_event(event_id: int):
    rows = execute("SELECT * FROM world_events WHERE id = ?", (event_id,))
    return rows[0] if rows else None


def delete_world_event(event_id: int):
    execute("DELETE FROM world_events WHERE id = ?", (event_id,))


def get_fact_log(limit: int = 1, offset: int = 0, author_id=None) -> list:
    """Лента постов (фактов) игроков и админов — новые сверху. Можно отфильтровать по автору."""
    if author_id:
        return execute("SELECT * FROM facts WHERE is_verdict = 0 AND author_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                       (author_id, limit, offset))
    return execute("SELECT * FROM facts WHERE is_verdict = 0 ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))


def find_author_id(name: str):
    """id автора по @юзернейму (берём из последних его постов)."""
    rows = execute("SELECT author_id FROM facts WHERE lower(author_name) = ? AND author_id IS NOT NULL ORDER BY id DESC LIMIT 1",
                   (name.lower().lstrip("@"),))
    return rows[0]["author_id"] if rows else None


def get_post_tags(author_id, text: str) -> list:
    """Все теги, под которыми сохранён один и тот же пост (пост с несколькими #тегами лежит несколькими строками)."""
    rows = execute("SELECT tag FROM facts WHERE author_id = ? AND text = ? AND is_verdict = 0", (author_id, text))
    return [r["tag"] for r in rows]


def delete_post(author_id, text: str) -> int:
    """Удаляет пост целиком — по всем его тегам. Возвращает, сколько строк убрано."""
    with _lock:
        n = len(get_post_tags(author_id, text))
        if n:
            execute("DELETE FROM facts WHERE author_id = ? AND text = ? AND is_verdict = 0", (author_id, text))
    _invalidate_tags()
    return n


def find_player_action(user_id, text: str):
    """Решение ИИ-ГМ, принятое из-за этого поста (если новость задела защиту страны)."""
    rows = execute("SELECT * FROM player_actions WHERE user_id = ? AND text = ? ORDER BY id DESC LIMIT 1", (user_id, text))
    return rows[0] if rows else None


def delete_player_action(action_id: int):
    execute("DELETE FROM player_actions WHERE id = ?", (action_id,))


def delete_fact_by_text(tag: str, text: str):
    execute("DELETE FROM facts WHERE tag = ? AND text = ?", (tag.lower().strip(), text))
    _invalidate_tags()


# =====================================================================
# СЕКРЕТЫ (шпионаж) И ВОЙНЫ
# =====================================================================

def _create_extra_tables():
    execute("""CREATE TABLE IF NOT EXISTS secrets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, country TEXT NOT NULL, kind TEXT NOT NULL, level INTEGER NOT NULL,
        title TEXT, text TEXT NOT NULL, author_id INTEGER, created_at TEXT NOT NULL, source TEXT DEFAULT 'rp')""")
    execute("""CREATE TABLE IF NOT EXISTS loot (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, secret_id INTEGER, country TEXT, kind TEXT,
        title TEXT, text TEXT, ts TEXT NOT NULL)""")
    execute("""CREATE TABLE IF NOT EXISTS war_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT, a TEXT NOT NULL, b TEXT NOT NULL, front TEXT DEFAULT '',
        forces TEXT DEFAULT '', summary TEXT DEFAULT '', turn INTEGER DEFAULT 0, last_verdict REAL DEFAULT 0, control TEXT DEFAULT '', fnum TEXT DEFAULT '')""")
    execute("""CREATE TABLE IF NOT EXISTS war_moves (
        id INTEGER PRIMARY KEY AUTOINCREMENT, war_id INTEGER NOT NULL, user_id INTEGER, user_name TEXT, country TEXT,
        text TEXT NOT NULL, ts TEXT NOT NULL, processed INTEGER DEFAULT 0)""")
    execute("CREATE INDEX IF NOT EXISTS idx_war_moves ON war_moves(war_id, processed)")
    execute("""CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, actor TEXT, target TEXT NOT NULL,
        rank INTEGER NOT NULL, planted TEXT NOT NULL, active INTEGER DEFAULT 1)""")
    execute("""CREATE TABLE IF NOT EXISTS funds (
        user_id INTEGER NOT NULL, iso TEXT NOT NULL, dirty REAL DEFAULT 0, clean REAL DEFAULT 0, PRIMARY KEY (user_id, iso))""")
    execute("""CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, name TEXT, bio TEXT, skills TEXT,
        loyalty INTEGER, price REAL, created REAL)""")
    execute("""CREATE TABLE IF NOT EXISTS recruits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, name TEXT, bio TEXT, skills TEXT,
        loyalty INTEGER, hired REAL)""")
    execute("""CREATE TABLE IF NOT EXISTS hq (
        user_id INTEGER PRIMARY KEY, hq INTEGER DEFAULT 0, tech INTEGER DEFAULT 0, cipher INTEGER DEFAULT 0, academy INTEGER DEFAULT 0)""")
    for stmt in ("ALTER TABLE war_state ADD COLUMN control TEXT DEFAULT ''", "ALTER TABLE war_state ADD COLUMN fnum TEXT DEFAULT ''",
                 "ALTER TABLE secrets ADD COLUMN source TEXT DEFAULT 'rp'", "ALTER TABLE agents ADD COLUMN dormant_until REAL DEFAULT 0",
                 "ALTER TABLE agents ADD COLUMN name TEXT DEFAULT ''", "ALTER TABLE agents ADD COLUMN bio TEXT DEFAULT ''",
                 "ALTER TABLE agents ADD COLUMN skills TEXT DEFAULT ''", "ALTER TABLE agents ADD COLUMN loyalty INTEGER DEFAULT 50"):
        try:
            execute(stmt)
        except Exception:
            pass


def add_secret(country, kind, level, title, text, author_id, source="rp") -> int:
    with _lock:
        execute("INSERT INTO secrets (country, kind, level, title, text, author_id, created_at, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (country, kind, level, title, text, author_id, _now(), source))
        rows = execute("SELECT last_insert_rowid() AS id")
    return rows[0]["id"] if rows else 0


def list_secrets(country: str = None, limit: int = 30) -> list:
    if country:
        return execute("SELECT id, country, kind, level, title FROM secrets WHERE country = ? ORDER BY id DESC LIMIT ?", (country, limit))
    return execute("SELECT id, country, kind, level, title FROM secrets ORDER BY id DESC LIMIT ?", (limit,))


def find_secrets(country: str, kind: str = None, keyword: str = "") -> list:
    """Секреты страны; поиск по ключевым словам без учёта регистра (в SQLite LIKE не работает с кириллицей)."""
    q, params = "SELECT * FROM secrets WHERE country = ?", [country]
    if kind:
        q += " AND kind = ?"
        params.append(kind)
    rows = execute(q + " ORDER BY level ASC, id DESC LIMIT 300", tuple(params))
    words = [w[:5] for w in keyword.lower().replace("ё", "е").split() if len(w) >= 3]
    if words:
        rows = [r for r in rows if any(w in ((r["title"] or "") + " " + r["text"]).lower().replace("ё", "е") for w in words)]
    return rows[:5]


def delete_secret(secret_id: int) -> bool:
    rows = execute("SELECT id FROM secrets WHERE id = ?", (secret_id,))
    if rows:
        execute("DELETE FROM secrets WHERE id = ?", (secret_id,))
    return bool(rows)


def add_loot(user_id, secret_id, country, kind, title, text):
    execute("INSERT INTO loot (user_id, secret_id, country, kind, title, text, ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, secret_id, country, kind, title, text, _now()))


def get_loot(user_id: int, limit: int = 8) -> list:
    return execute("SELECT * FROM loot WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))


def war_get_or_create(a: str, b: str) -> int:
    with _lock:
        rows = execute("SELECT id FROM war_state WHERE (a = ? AND b = ?) OR (a = ? AND b = ?)", (a, b, b, a))
        if rows:
            return rows[0]["id"]
        execute("INSERT INTO war_state (a, b) VALUES (?, ?)", (a, b))
        return execute("SELECT last_insert_rowid() AS id")[0]["id"]


def war_get(war_id: int):
    rows = execute("SELECT * FROM war_state WHERE id = ?", (war_id,))
    return rows[0] if rows else None


def war_add_move(war_id, user_id, user_name, country, text) -> int:
    with _lock:
        execute("INSERT INTO war_moves (war_id, user_id, user_name, country, text, ts) VALUES (?, ?, ?, ?, ?, ?)",
                (war_id, user_id, user_name, country, text, _now()))
        return war_pending_count(war_id)


def war_pending(war_id: int, limit: int = 40) -> list:
    return execute("SELECT * FROM war_moves WHERE war_id = ? AND processed = 0 ORDER BY id ASC LIMIT ?", (war_id, limit))


def war_pending_count(war_id: int) -> int:
    rows = execute("SELECT COUNT(*) AS c FROM war_moves WHERE war_id = ? AND processed = 0", (war_id,))
    return rows[0]["c"] if rows else 0


def war_user_pending(war_id: int, user_id: int) -> int:
    rows = execute("SELECT COUNT(*) AS c FROM war_moves WHERE war_id = ? AND processed = 0 AND user_id = ?", (war_id, user_id))
    return rows[0]["c"] if rows else 0


def war_mark_processed(ids: list):
    if ids:
        execute(f"UPDATE war_moves SET processed = 1 WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))


def war_update(war_id, front, forces, summary, turn, ts, control=""):
    execute("UPDATE war_state SET front = ?, forces = ?, summary = ?, turn = ?, last_verdict = ?, control = ? WHERE id = ?",
            (front, forces, summary, turn, ts, control, war_id))


def war_front_for(iso: str) -> list:
    return execute("SELECT a, b, front FROM war_state WHERE (a = ? OR b = ?) AND front != '' ORDER BY id DESC LIMIT 2", (iso, iso))


def add_agent(owner_id, actor, target, rank, name="", bio="", skills="", loyalty=50) -> int:
    with _lock:
        execute("INSERT INTO agents (owner_id, actor, target, rank, planted, name, bio, skills, loyalty) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (owner_id, actor, target, rank, _now(), name, bio, skills, loyalty))
        return execute("SELECT last_insert_rowid() AS id")[0]["id"]


def list_agents(owner_id: int) -> list:
    return execute("SELECT * FROM agents WHERE owner_id = ? ORDER BY id DESC LIMIT 20", (owner_id,))


def active_agents() -> list:
    return execute("SELECT * FROM agents WHERE active = 1 LIMIT 100")


def burn_agent(agent_id: int):
    execute("UPDATE agents SET active = 0 WHERE id = ?", (agent_id,))


def agent_rank_sum(owner_id: int, target: str) -> int:
    rows = execute("SELECT COALESCE(SUM(rank), 0) AS s FROM agents WHERE owner_id = ? AND target = ? AND active = 1", (owner_id, target))
    return rows[0]["s"] if rows else 0


def loot_secret_ids(user_id: int) -> set:
    return {r["secret_id"] for r in execute("SELECT secret_id FROM loot WHERE user_id = ?", (user_id,))}


def get_secret(secret_id: int):
    rows = execute("SELECT * FROM secrets WHERE id = ?", (secret_id,))
    return rows[0] if rows else None


def war_set_fnum(war_id: int, fnum_json: str):
    execute("UPDATE war_state SET fnum = ? WHERE id = ?", (fnum_json, war_id))


def get_funds(user_id: int) -> list:
    return execute("SELECT iso, dirty, clean FROM funds WHERE user_id = ? AND (dirty > 0.5 OR clean > 0.5) ORDER BY dirty + clean DESC", (user_id,))


def add_funds(user_id: int, iso: str, dirty: float = 0.0, clean: float = 0.0):
    with _lock:
        rows = execute("SELECT dirty, clean FROM funds WHERE user_id = ? AND iso = ?", (user_id, iso))
        if rows:
            execute("UPDATE funds SET dirty = ?, clean = ? WHERE user_id = ? AND iso = ?",
                    (max(0.0, rows[0]["dirty"] + dirty), max(0.0, rows[0]["clean"] + clean), user_id, iso))
        else:
            execute("INSERT INTO funds (user_id, iso, dirty, clean) VALUES (?, ?, ?, ?)", (user_id, iso, max(0.0, dirty), max(0.0, clean)))


def get_agent(agent_id: int):
    rows = execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
    return rows[0] if rows else None


def set_agent_rank(agent_id: int, rank: int):
    execute("UPDATE agents SET rank = ? WHERE id = ?", (rank, agent_id))


def set_dormant(agent_id: int, until: float):
    execute("UPDATE agents SET dormant_until = ? WHERE id = ?", (until, agent_id))


# ---------------- кадры агентства ----------------

def add_candidates(owner_id: int, rows: list):
    for r in rows:
        execute("INSERT INTO candidates (owner_id, name, bio, skills, loyalty, price, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (owner_id, r["name"], r["bio"], r["skills"], r["loyalty"], r["price"], time.time()))


def get_candidates(owner_id: int, since: float) -> list:
    return execute("SELECT * FROM candidates WHERE owner_id = ? AND created > ? ORDER BY id", (owner_id, since))


def clear_candidates(owner_id: int):
    execute("DELETE FROM candidates WHERE owner_id = ?", (owner_id,))


def delete_candidate(cid: int):
    execute("DELETE FROM candidates WHERE id = ?", (cid,))


def add_recruit(owner_id, name, bio, skills_json, loyalty) -> int:
    with _lock:
        execute("INSERT INTO recruits (owner_id, name, bio, skills, loyalty, hired) VALUES (?, ?, ?, ?, ?, ?)",
                (owner_id, name, bio, skills_json, loyalty, time.time()))
        return execute("SELECT last_insert_rowid() AS id")[0]["id"]


def list_recruits(owner_id: int) -> list:
    return execute("SELECT * FROM recruits WHERE owner_id = ? ORDER BY id", (owner_id,))


def get_recruit(rid: int):
    rows = execute("SELECT * FROM recruits WHERE id = ?", (rid,))
    return rows[0] if rows else None


def delete_recruit(rid: int):
    execute("DELETE FROM recruits WHERE id = ?", (rid,))


def set_recruit_skills(rid: int, skills_json: str):
    execute("UPDATE recruits SET skills = ? WHERE id = ?", (skills_json, rid))


def set_agent_skills(aid: int, skills_json: str):
    execute("UPDATE agents SET skills = ? WHERE id = ?", (skills_json, aid))


def get_hq(user_id: int) -> dict:
    rows = execute("SELECT hq, tech, cipher, academy FROM hq WHERE user_id = ?", (user_id,))
    return dict(rows[0]) if rows else {"hq": 0, "tech": 0, "cipher": 0, "academy": 0}


def set_hq_level(user_id: int, track: str, level: int):
    assert track in ("hq", "tech", "cipher", "academy")
    with _lock:
        if not execute("SELECT 1 FROM hq WHERE user_id = ?", (user_id,)):
            execute("INSERT INTO hq (user_id) VALUES (?)", (user_id,))
        execute(f"UPDATE hq SET {track} = ? WHERE user_id = ?", (level, user_id))


def spend_clean(user_id: int, amount: float) -> bool:
    """Списывает чистые деньги со счетов (сначала с самых больших). False — не хватает."""
    with _lock:
        rows = execute("SELECT iso, clean FROM funds WHERE user_id = ? AND clean > 0 ORDER BY clean DESC", (user_id,))
        if sum(r["clean"] for r in rows) + 1e-6 < amount:
            return False
        left = amount
        for r in rows:
            take = min(r["clean"], left)
            execute("UPDATE funds SET clean = clean - ? WHERE user_id = ? AND iso = ?", (take, user_id, r["iso"]))
            left -= take
            if left <= 1e-6:
                break
        return True
