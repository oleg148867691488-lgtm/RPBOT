import os
import json
from dotenv import load_dotenv

load_dotenv()

# === AI ТОКЕНЫ ===
GROQ_KEYS = [
    os.getenv("GROQ_KEY_1"),
    os.getenv("GROQ_KEY_2"),
    os.getenv("GROQ_KEY_3"),
    os.getenv("GROQ_KEY_4"),
    os.getenv("GROQ_KEY_5"),
]
GEMINI_KEY = os.getenv("GEMINI_KEY")
OLLAMA_KEY = os.getenv("OLLAMA_KEY")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")  # или URL на Render

# === АДМИН ===
ADMIN_ID = 7184396483
ADMIN_USERNAME = "cakemogus"

# === НАСТРОЙКИ ===
NEWS_INTERVAL_MINUTES = 30
MAX_HISTORY = 50

# === ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ ДЛЯ ОСТАНОВКИ ===
bot_stopped = False

# === ФАЙЛ ДЛЯ СОХРАНЁННЫХ ЧАТОВ ===
SAVED_CHATS_FILE = "saved_chats.json"

def load_saved_chats():
    if os.path.exists(SAVED_CHATS_FILE):
        try:
            with open(SAVED_CHATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"news": None, "war": None, "un": None}
    return {"news": None, "war": None, "un": None}

def save_saved_chats(chats):
    with open(SAVED_CHATS_FILE, "w", encoding="utf-8") as f:
        json.dump(chats, f, ensure_ascii=False, indent=2)

saved_chats = load_saved_chats()
