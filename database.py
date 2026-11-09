"""
DATABASE.PY — БАЗА ЗНАНИЙ (TURSO С АВТОПЕРЕПОДКЛЮЧЕНИЕМ)
"""

import os
import time
from datetime import datetime
from config import TURSO_DATABASE_URL, TURSO_AUTH_TOKEN


# =====================================================================
# ПОДКЛЮЧЕНИЕ
# =====================================================================

_conn = None


def get_conn():
    """Создаёт новое соединение с Turso."""
    global _conn
    import libsql
    if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
        _conn = libsql.connect(
            database=TURSO_DATABASE_URL,
            auth_token=TURSO_AUTH_TOKEN
        )
    else:
        _conn = libsql.connect("facts.db")
    return _conn


def close_conn():
    """Закрывает текущее соединение (если есть)."""
    global _conn
    if _conn:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None


def execute_with_retry(query: str, params: tuple = (), max_retries: int = 1):
    """
    Выполняет запрос с автоматическим переподключением.
    Если Turso вернул 'stream not found' — пересоздаёт соединение и повторяет.
    """
    global _conn
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            if _conn is None:
                _conn = get_conn()

            cur = _conn.cursor()
            cur.execute(query, params)

            if cur.description:
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                _conn.commit()
                return [dict(zip(columns, row)) for row in rows]

            _conn.commit()
            return []

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            if "stream not found" in error_str or "hrana" in error_str or "404" in error_str:
                print(f"⚠️ Stream error (попытка {attempt+1}/{max_retries+1}): {e}")
                close_conn()
                continue
            else:
                raise

    raise last_error


# =====================================================================
# ИНИЦИАЛИЗАЦИЯ ТАБЛИЦ
# =====================================================================

def init_db():
    execute_with_retry("""
    CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag TEXT NOT NULL,
        text TEXT NOT NULL,
        author_id INTEGER,
        author_name TEXT,
        year INTEGER,
        is_verdict INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)
    execute_with_retry("CREATE INDEX IF NOT EXISTS idx_facts_tag ON facts(tag);")
    execute_with_retry("CREATE INDEX IF NOT EXISTS idx_facts_verdict ON facts(is_verdict);")

    execute_with_retry("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        is_summary INTEGER DEFAULT 0,
        is_archived INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)
    execute_with_retry("CREATE INDEX IF NOT EXISTS idx_history_user ON history(chat_id, user_id, is_archived);")

    execute_with_retry("""
    CREATE TABLE IF NOT EXISTS cooldowns (
        user_id INTEGER PRIMARY KEY,
        last_request REAL NOT NULL DEFAULT 0,
        last_verdict REAL NOT NULL DEFAULT 0
    );
    """)

    execute_with_retry("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)


# =====================================================================
# SETTINGS
# =====================================================================

def set_setting(key: str, value: str):
    execute_with_retry(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value)
    )


def get_setting(key: str, default: str = None):
    rows = execute_with_retry("SELECT value FROM settings WHERE key = ?", (key,))
    return rows[0]["value"] if rows else default


# =====================================================================
# ФАКТЫ
# =====================================================================

def add_fact(tag: str, text: str, author_id: int = 0, author_name: str = "",
             year: int = None, is_verdict: bool = False) -> int:
    execute_with_retry(
        """INSERT INTO facts (tag, text, author_id, author_name, year, is_verdict, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (tag.lower().strip(), text.strip(), author_id, author_name, year,
         1 if is_verdict else 0, datetime.utcnow().isoformat())
    )
    rows = execute_with_retry("SELECT last_insert_rowid() AS id;")
    return rows[0]["id"] if rows else 0


def get_facts_by_tag(tag: str, include_verdicts: bool = True, limit: int = 200):
    tag = tag.lower().strip()
    if include_verdicts:
        return execute_with_retry(
            "SELECT * FROM facts WHERE tag = ? ORDER BY is_verdict DESC, created_at ASC LIMIT ?",
            (tag, limit)
        )
    return execute_with_retry(
        "SELECT * FROM facts WHERE tag = ? AND is_verdict = 0 ORDER BY created_at ASC LIMIT ?",
        (tag, limit)
    )


def get_all_tags():
    return execute_with_retry(
        """SELECT tag, COUNT(*) AS cnt, COALESCE(SUM(is_verdict), 0) AS verdicts
           FROM facts GROUP BY tag ORDER BY cnt DESC"""
    )


def search_facts(query: str, limit: int = 50):
    return execute_with_retry(
        "SELECT * FROM facts WHERE text LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f"%{query}%", limit)
    )


def clear_by_tag(tag: str) -> int:
    execute_with_retry("DELETE FROM facts WHERE tag = ?", (tag.lower().strip(),))
    return 1


def clear_all_facts():
    execute_with_retry("DELETE FROM facts")


def get_stats():
    total = execute_with_retry("SELECT COUNT(*) AS cnt FROM facts;")[0]["cnt"]
    verdicts = execute_with_retry("SELECT COUNT(*) AS cnt FROM facts WHERE is_verdict = 1;")[0]["cnt"]
    tags = execute_with_retry("SELECT COUNT(DISTINCT tag) AS cnt FROM facts;")[0]["cnt"]
    return {"total": total, "verdicts": verdicts, "tags": tags}


# =====================================================================
# ИСТОРИЯ
# =====================================================================

def add_history(chat_id: int, user_id: int, role: str, content: str, is_summary: bool = False):
    execute_with_retry(
        """INSERT INTO history (chat_id, user_id, role, content, is_summary, is_archived, created_at)
           VALUES (?, ?, ?, ?, ?, 0, ?)""",
        (chat_id, user_id, role, content, 1 if is_summary else 0, datetime.utcnow().isoformat())
    )


def get_history(chat_id: int, user_id: int, limit: int = 15):
    rows = execute_with_retry(
        """SELECT role, content, is_summary FROM history
           WHERE chat_id = ? AND user_id = ? AND is_archived = 0
           ORDER BY id DESC LIMIT ?""",
        (chat_id, user_id, limit)
    )
    return list(reversed(rows))


def get_old_messages_for_summary(chat_id: int, user_id: int, batch: int = 20):
    return execute_with_retry(
        """SELECT id, role, content FROM history
           WHERE chat_id = ? AND user_id = ? AND is_archived = 0 AND is_summary = 0
           ORDER BY id ASC LIMIT ?""",
        (chat_id, user_id, batch)
    )


def archive_messages(message_ids: list):
    for mid in message_ids:
        execute_with_retry("UPDATE history SET is_archived = 1 WHERE id = ?", (mid,))


def count_active_history(chat_id: int, user_id: int) -> int:
    rows = execute_with_retry(
        "SELECT COUNT(*) AS cnt FROM history WHERE chat_id = ? AND user_id = ? AND is_archived = 0",
        (chat_id, user_id)
    )
    return rows[0]["cnt"] if rows else 0


def clear_history(chat_id: int = None, user_id: int = None):
    if chat_id and user_id:
        execute_with_retry("DELETE FROM history WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    elif chat_id:
        execute_with_retry("DELETE FROM history WHERE chat_id = ?", (chat_id,))
    else:
        execute_with_retry("DELETE FROM history")


# =====================================================================
# КУЛДАУНЫ
# =====================================================================

def check_cooldown(user_id: int, cooldown_seconds: float, is_verdict: bool = False) -> bool:
    now = time.time()
    rows = execute_with_retry("SELECT last_request, last_verdict FROM cooldowns WHERE user_id = ?", (user_id,))

    if rows:
        last = rows[0]["last_verdict"] if is_verdict else rows[0]["last_request"]
        if now - last < cooldown_seconds:
            return False
        if is_verdict:
            execute_with_retry("UPDATE cooldowns SET last_verdict = ? WHERE user_id = ?", (now, user_id))
        else:
            execute_with_retry("UPDATE cooldowns SET last_request = ? WHERE user_id = ?", (now, user_id))
    else:
        execute_with_retry(
            "INSERT INTO cooldowns (user_id, last_request, last_verdict) VALUES (?, ?, ?)",
            (user_id, 0 if is_verdict else now, now if is_verdict else 0)
        )
    return True


# === Инициализация при импорте ===
try:
    init_db()
except Exception as e:
    print(f"⚠️ Не удалось инициализировать Turso: {e}")
