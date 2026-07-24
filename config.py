"""
Конфигурация бота.
Загружает ВСЕ переменные окружения (Render).
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# AI ТОКЕНЫ (7 штук)
# =====================================================================

# Groq (Llama 3.3 70B) — 5 токенов
GROQ_KEYS = [
    os.getenv("GROQ_KEY_1"),
    os.getenv("GROQ_KEY_2"),
    os.getenv("GROQ_KEY_3"),
    os.getenv("GROQ_KEY_4"),
    os.getenv("GROQ_KEY_5"),
]

# Gemini 2.5 Flash — поиск в интернете
GEMINI_KEY = os.getenv("GEMINI_KEY")

# Ollama — резервный поиск
OLLAMA_KEY = os.getenv("OLLAMA_KEY")

# =====================================================================
# URL API
# =====================================================================

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

# =====================================================================
# TELEGRAM
# =====================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# =====================================================================
# АДМИН
# =====================================================================

ADMIN_ID = int(os.getenv("ADMIN_ID", "7184396483"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "cakemogus")

# =====================================================================
# НАСТРОЙКИ ИГРЫ
# =====================================================================

# Новости
NEWS_INTERVAL_MINUTES = int(os.getenv("NEWS_INTERVAL_MINUTES", "15"))  # Каждые 15 минут

# Decision Engine
DECISION_INTERVAL_MINUTES = int(os.getenv("DECISION_INTERVAL_MINUTES", "10"))  # Каждые 10 минут

# Лимиты
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "50"))
MAX_DIALOG_LENGTH = int(os.getenv("MAX_DIALOG_LENGTH", "20"))

# =====================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# =====================================================================

# Флаг остановки бота
bot_stopped = False

# Текущий режим сложности (всегда iron_man)
AI_MODE = "iron_man"

# =====================================================================
# СОХРАНЁННЫЕ ЧАТЫ
# =====================================================================

SAVED_CHATS_FILE = "saved_chats.json"

def load_saved_chats() -> dict:
    """Загрузка сохранённых чатов из файла"""
    if os.path.exists(SAVED_CHATS_FILE):
        try:
            with open(SAVED_CHATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "news": data.get("news"),
                    "war": data.get("war"),
                    "un": data.get("un")
                }
        except Exception as e:
            print(f"⚠️ Ошибка загрузки saved_chats: {e}")
    
    return {"news": None, "war": None, "un": None}

def save_saved_chats(chats: dict) -> None:
    """Сохранение чатов в файл"""
    try:
        with open(SAVED_CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(chats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения saved_chats: {e}")

# Загружаем при импорте
saved_chats = load_saved_chats()

# =====================================================================
# ПРОВЕРКА КОНФИГУРАЦИИ
# =====================================================================

def check_config() -> bool:
    """Проверка что все нужные переменные загружены"""
    errors = []
    
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN не задан!")
    
    valid_groq = [k for k in GROQ_KEYS if k]
    if not valid_groq:
        errors.append("Нет ни одного GROQ_KEY!")
    
    if not GEMINI_KEY:
        print("⚠️ GEMINI_KEY не задан (поиск может не работать)")
    
    if not OLLAMA_KEY:
        print("⚠️ OLLAMA_KEY не задан (резервный поиск не работает)")
    
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


# Автопроверка при импорте
if __name__ != "__main__":
    check_config()
