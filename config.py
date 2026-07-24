import os
import re
import json
import sqlite3
import httpx
import asyncio
import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

# === ТОКЕНЫ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# === АДМИН ===
ADMIN_ID = 7184396483
ADMIN_USERNAME = "cakemogus"

# === НАСТРОЙКИ ===
NEWS_INTERVAL_MINUTES = 30
MAX_HISTORY = 50

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ (для всех модулей) ===
bot_stopped = False  # <--- СЮДА ПЕРЕНЕСЛИ

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
