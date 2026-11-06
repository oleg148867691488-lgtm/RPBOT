import os

# === ТОКЕН БОТА ===
BOT_TOKEN = os.getenv("BOT_TOKEN")

# === ID ЧАТА ДЛЯ СБОРА ФАКТОВ (fallback, если не сохранён через /savechat) ===
FACTS_CHAT_ID = int(os.getenv("FACTS_CHAT_ID", "0"))

# === АДМИН (ты) ===
ADMIN_ID = int(os.getenv("ADMIN_ID", "8283458488"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "cakemogus")

# === ВЛАДЕЛЕЦ РП (Леклерк) ===
# Узнать ID через @userinfobot
RP_OWNER_ID = int(os.getenv("RP_OWNER_ID", "0"))
RP_OWNER_USERNAME = os.getenv("RP_OWNER_USERNAME", "")

# === GROQ (3 ключа с разных аккаунтов) ===
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

GROQ_KEY_MAIN    = os.getenv("GROQ_KEY_1")   # основной диалог
GROQ_KEY_VERDICT = os.getenv("GROQ_KEY_2")   # вердикты
GROQ_KEY_SUMMARY = os.getenv("GROQ_KEY_3")   # суммаризация истории

# Список всех ключей для fallback-перебора
GROQ_ALL_KEYS = [k for k in [GROQ_KEY_MAIN, GROQ_KEY_VERDICT, GROQ_KEY_SUMMARY] if k]

# === МОДЕЛИ ===
MODEL_MAIN    = "qwen/qwen3.8-27b"          # быстрая и умная для диалога
MODEL_VERDICT = "openai/gpt-oss-120b"       # мощная для глубокого анализа
MODEL_SUMMARY = "openai/gpt-oss-20b"        # самая быстрая для сжатия

# === GEMINI (опционально, как крайний fallback) ===
GEMINI_KEY = os.getenv("GEMINI_KEY")
GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent?key={key}"
)

# === OLLAMA (веб-поиск) ===
OLLAMA_KEY = os.getenv("OLLAMA_KEY")
OLLAMA_URL = "https://ollama.com/api/web_search"

# === TURSO (база данных) ===
TURSO_DATABASE_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN   = os.getenv("TURSO_KEY")

# === НАСТРОЙКИ ПОВЕДЕНИЯ ===
COOLDOWN_DIALOG    = 3.0    # сек между обычными сообщениями
COOLDOWN_VERDICT   = 15.0   # сек между вердиктами (для админа, для игроков 30 сек в handlers)
HISTORY_CONTEXT_LIMIT        = 15   # сколько последних сообщений идёт в промпт
HISTORY_SUMMARIZE_THRESHOLD  = 30   # при скольких сообщениях запускать сжатие
HISTORY_SUMMARIZE_BATCH      = 20   # сколько старых сообщений сжимать за раз
