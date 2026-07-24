"""
КОНФИГУРАЦИЯ БОТА
==================
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

# AI ТОКЕНЫ
GROQ_KEYS = [
    os.getenv("GROQ_KEY_1"),
    os.getenv("GROQ_KEY_2"),
    os.getenv("GROQ_KEY_3"),
    os.getenv("GROQ_KEY_4"),
    os.getenv("GROQ_KEY_5"),
]

GEMINI_KEY = os.getenv("GEMINI_KEY")
OLLAMA_KEY = os.getenv("OLLAMA_KEY")

# URL API
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

# TELEGRAM
BOT_TOKEN = os.getenv("BOT_TOKEN")

# АДМИН
ADMIN_ID = int(os.getenv("ADMIN_ID", "7184396483"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "cakemogus")

# НАСТРОЙКИ
NEWS_INTERVAL_MINUTES = int(os.getenv("NEWS_INTERVAL_MINUTES", "15"))
DECISION_INTERVAL_MINUTES = int(os.getenv("DECISION_INTERVAL_MINUTES", "10"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "50"))

# ГЛОБАЛЬНЫЕ
bot_stopped = False
AI_MODE = "iron_man"

# ЧАТЫ
SAVED_CHATS_FILE = "saved_chats.json"

def load_saved_chats() -> dict:
    if os.path.exists(SAVED_CHATS_FILE):
        try:
            with open(SAVED_CHATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {"news": data.get("news"), "war": data.get("war"), "un": data.get("un")}
        except:
            pass
    return {"news": None, "war": None, "un": None}

def save_saved_chats(chats: dict) -> None:
    try:
        with open(SAVED_CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(chats, f, ensure_ascii=False, indent=2)
    except:
        pass

saved_chats = load_saved_chats()

def check_config() -> bool:
    errors = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN не задан!")
    valid_groq = [k for k in GROQ_KEYS if k]
    if not valid_groq:
        errors.append("Нет ни одного GROQ_KEY!")
    if errors:
        print("❌ ОШИБКИ КОНФИГУРАЦИИ:")
        for e in errors:
            print(f"   - {e}")
        return False
    print("✅ Конфигурация загружена успешно")
    print(f"   Groq ключей: {len(valid_groq)}")
    print(f"   Gemini: {'✅' if GEMINI_KEY else '❌'}")
    print(f"   Ollama: {'✅' if OLLAMA_KEY else '❌'}")
    print(f"   Новости каждые: {NEWS_INTERVAL_MINUTES} мин")
    print(f"   Decision Engine каждые: {DECISION_INTERVAL_MINUTES} мин")
    return True

if __name__ != "__main__":
    check_config()
