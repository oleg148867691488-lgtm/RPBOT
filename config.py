"""
CONFIG.PY — настройки РП-бота.
Все секреты берутся ТОЛЬКО из переменных окружения (см. .env.example).
Имена переменных окружения те же, что были раньше (BOT_TOKEN, GROQ_KEY_1..3,
TURSO_URL, TURSO_KEY, OLLAMA_KEY, GEMINI_KEY, ...), так что настройки на Render менять не нужно.
"""

import os


def _int(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _csv(name: str, default) -> list:
    raw = os.getenv(name)
    if not raw:
        return list(default)
    return [x.strip() for x in raw.split(",") if x.strip()]


# === TELEGRAM ===
BOT_TOKEN = os.getenv("BOT_TOKEN")

# === ВЛАДЕЛЬЦЫ (полный доступ). Лучше задать через переменные окружения. ===
ADMIN_ID = _int("ADMIN_ID", 8283458488)
RP_OWNER_ID = _int("RP_OWNER_ID", 7598252516)
OWNER_IDS = frozenset(i for i in (ADMIN_ID, RP_OWNER_ID) if i)
RP_OWNER_USERNAME = os.getenv("RP_OWNER_USERNAME", "").lstrip("@")
DEVELOPER_USERNAME = os.getenv("DEVELOPER_USERNAME", "cakemogus").lstrip("@")

# Чат для сбора фактов (запасной вариант, если не сохранён через /savechat)
FACTS_CHAT_ID = _int("FACTS_CHAT_ID", 0)

# === GROQ (до 3 ключей с разных аккаунтов) ===
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_KEY_MAIN = os.getenv("GROQ_KEY_1")      # основной диалог
GROQ_KEY_VERDICT = os.getenv("GROQ_KEY_2")   # вердикты
GROQ_KEY_SUMMARY = os.getenv("GROQ_KEY_3")   # сжатие истории
GROQ_KEYS = [k for k in (GROQ_KEY_MAIN, GROQ_KEY_VERDICT, GROQ_KEY_SUMMARY) if k]
PRIMARY_KEY = {"main": GROQ_KEY_MAIN, "verdict": GROQ_KEY_VERDICT, "summary": GROQ_KEY_SUMMARY}

# Цепочки моделей: пробуем по порядку. Можно переопределить через env (через запятую).
# Если модели не существует, бот запомнит это на 30 минут и не будет долбиться в неё.
MODELS = {
    "main": _csv("MODELS_MAIN", ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]),
    "verdict": _csv("MODELS_VERDICT", ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]),
    "summary": _csv("MODELS_SUMMARY", ["openai/gpt-oss-20b"]),
}

# === GEMINI (запасной вариант) ===
GEMINI_KEY = os.getenv("GEMINI_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")  # gemini-2.0-flash отключён Google
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# === OLLAMA (веб-поиск) ===
OLLAMA_KEY = os.getenv("OLLAMA_KEY")
OLLAMA_URL = "https://ollama.com/api/web_search"

# === TURSO (если не заданы — локальный SQLite-файл facts.db) ===
TURSO_URL = os.getenv("TURSO_URL")
TURSO_KEY = os.getenv("TURSO_KEY")

# === ПОВЕДЕНИЕ ===
COOLDOWN_DIALOG = _float("COOLDOWN_DIALOG", 3.0)
COOLDOWN_VERDICT_STAFF = _float("COOLDOWN_VERDICT_STAFF", 15.0)
COOLDOWN_VERDICT_PLAYER = _float("COOLDOWN_VERDICT_PLAYER", 30.0)
VERDICT_LIMIT_STAFF = _int("VERDICT_LIMIT_STAFF", 100)
VERDICT_LIMIT_PLAYER = _int("VERDICT_LIMIT_PLAYER", 25)
BULK_COOLDOWN = _float("BULK_COOLDOWN", 180.0)

MAX_INPUT_CHARS = 3000               # обрезка входного текста (бесплатный Groq: лимит 7-8 тыс. токенов/мин)
HISTORY_CONTEXT_LIMIT = 15           # сколько последних сообщений идёт в промпт
HISTORY_SUMMARIZE_THRESHOLD = 30     # при скольких сообщениях запускать сжатие
HISTORY_SUMMARIZE_BATCH = 20         # сколько старых сообщений сжимать за раз

# === ВРЕМЯ РП: 24 реальных часа = 365 дней РП (2 часа ≈ 1 месяц) ===
RP_DAYS_PER_REAL_HOUR = 365 / 24

# Keep-alive для бесплатного Render (пингует сам себя). Обычно берётся автоматически.
KEEPALIVE_URL = os.getenv("KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL")
