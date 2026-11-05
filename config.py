import os

# === ТОКЕН БОТА ===
BOT_TOKEN = os.getenv("BOT_TOKEN")

# === ID ЧАТА ДЛЯ СБОРА ФАКТОВ ===
# ВАЖНО: бот должен быть в этом чате, лучше админом
FACTS_CHAT_ID = int(os.getenv("FACTS_CHAT_ID", "0"))

# === АДМИН ===
ADMIN_ID = int(os.getenv("ADMIN_ID", "8283458488"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "cakemogus")

# === GROQ (3 ключа с разных аккаунтов) ===
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

GROQ_KEY_MAIN    = os.getenv("GROQ_KEY_1")   # основной диалог
GROQ_KEY_VERDICT = os.getenv("GROQ_KEY_2")   # вердикты
GROQ_KEY_SUMMARY = os.getenv("GROQ_KEY_3")   # суммаризация истории

# Список всех ключей для fallback-перебора (если основной упал)
GROQ_ALL_KEYS = [k for k in [GROQ_KEY_MAIN, GROQ_KEY_VERDICT, GROQ_KEY_SUMMARY] if k]

# === МОДЕЛИ ===
MODEL_MAIN    = "openai/gpt-oss-120b"
MODEL_VERDICT = "deepseek-r1-distill-llama-70b"
MODEL_SUMMARY = "llama-3.1-8b-instant"

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
COOLDOWN_VERDICT   = 15.0   # сек между вердиктами
HISTORY_CONTEXT_LIMIT        = 15   # сколько последних сообщений идёт в промпт
HISTORY_SUMMARIZE_THRESHOLD  = 30   # при скольких сообщениях запускать сжатие
HISTORY_SUMMARIZE_BATCH      = 20   # сколько старых сообщений сжимать за раз
