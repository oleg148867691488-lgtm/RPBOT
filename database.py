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
    CREATE TABLE IF NOT EXISTS daily_usage (
        user_id INTEGER NOT NULL,
        day TEXT NOT NULL,
        kind TEXT NOT NULL,
        cnt INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, day, kind)
    )""")

    # Уборка мусора: старые лимиты и архивная история
    old_day = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    execute("DELETE FROM daily_usage WHERE day < ?", (old_day,))
    execute("DELETE FROM settings WHERE key LIKE 'verdict_limit_%'")  # хвосты старой версии
    old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    execute("DELETE FROM history WHERE is_archived = 1 AND created_at < ?", (old_ts,))

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
