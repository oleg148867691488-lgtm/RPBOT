"""
HISTORY.PY — БАЗА ДАННЫХ + JSON СОХРАНЕНИЕ МИРА
=================================================
SQLite для пользователей/диалогов.
JSON файл для состояния мира (в /data на Render).
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Tuple, Dict

DB_PATH = "rp_bot.db"

# Путь к JSON файлу мира (Render Disk)
DATA_DIR = os.environ.get("RENDER_DATA_DIR", ".")
WORLD_FILE = os.path.join(DATA_DIR, "world_state.json")

# =====================================================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# =====================================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, country TEXT, year INTEGER DEFAULT 2024)''')
    c.execute('''CREATE TABLE IF NOT EXISTS economy (user_id INTEGER PRIMARY KEY, budget INTEGER DEFAULT 10000000, steel INTEGER DEFAULT 1000, oil INTEGER DEFAULT 500, grain INTEGER DEFAULT 2000, gold INTEGER DEFAULT 100)''')
    c.execute('''CREATE TABLE IF NOT EXISTS dialog_history (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS verdicts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, topic TEXT, verdict TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS world_events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, description TEXT, countries_involved TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS technologies (tech_name TEXT PRIMARY KEY, level INTEGER DEFAULT 1)''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# =====================================================================
# ПОЛЬЗОВАТЕЛИ
# =====================================================================

def save_country(user_id: int, country: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO users (user_id, country) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET country = ?', (user_id, country, country))
    conn.commit()
    conn.close()

def save_year(user_id: int, year: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO users (user_id, year) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET year = ?', (user_id, year, year))
    conn.commit()
    conn.close()

def get_country(user_id: int) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT country FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_year(user_id: int) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT year FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 2024

# =====================================================================
# ЭКОНОМИКА
# =====================================================================

def get_economy(user_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT budget, steel, oil, grain, gold FROM economy WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return {"budget": row[0], "steel": row[1], "oil": row[2], "grain": row[3], "gold": row[4]} if row else None

def init_economy(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO economy (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def update_economy(user_id: int, budget: int = None, steel: int = None, oil: int = None, grain: int = None, gold: int = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO economy (user_id) VALUES (?)', (user_id,))
    updates = []
    params = []
    if budget is not None:
        updates.append("budget = ?"); params.append(budget)
    if steel is not None:
        updates.append("steel = ?"); params.append(steel)
    if oil is not None:
        updates.append("oil = ?"); params.append(oil)
    if grain is not None:
        updates.append("grain = ?"); params.append(grain)
    if gold is not None:
        updates.append("gold = ?"); params.append(gold)
    if updates:
        params.append(user_id)
        c.execute(f'UPDATE economy SET {", ".join(updates)} WHERE user_id = ?', params)
        conn.commit()
    conn.close()

# =====================================================================
# ДИАЛОГИ
# =====================================================================

def save_dialog(chat_id: int, user_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO dialog_history (chat_id, user_id, role, content) VALUES (?, ?, ?, ?)', (chat_id, user_id, role, content))
    conn.commit()
    conn.close()

def get_dialog_history(chat_id: int, user_id: int = None, limit: int = 50) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if user_id:
        c.execute('SELECT role, content, timestamp FROM dialog_history WHERE chat_id = ? AND user_id = ? ORDER BY timestamp DESC LIMIT ?', (chat_id, user_id, limit))
    else:
        c.execute('SELECT role, content, timestamp FROM dialog_history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?', (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows[::-1]

# =====================================================================
# ВЕРДИКТЫ
# =====================================================================

def save_verdict(user_id: int, topic: str, verdict: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO verdicts (user_id, topic, verdict) VALUES (?, ?, ?)', (user_id, topic, verdict))
    conn.commit()
    conn.close()

def get_verdicts(user_id: int, topic: str = None, limit: int = 10) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if topic:
        c.execute('SELECT topic, verdict, timestamp FROM verdicts WHERE user_id = ? AND topic LIKE ? ORDER BY timestamp DESC LIMIT ?', (user_id, f'%{topic}%', limit))
    else:
        c.execute('SELECT topic, verdict, timestamp FROM verdicts WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

# =====================================================================
# МИРОВЫЕ СОБЫТИЯ
# =====================================================================

def save_world_event(event_type: str, description: str, countries_involved: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO world_events (event_type, description, countries_involved) VALUES (?, ?, ?)', (event_type, description, countries_involved))
    conn.commit()
    conn.close()

def get_world_events(event_type: str = None, limit: int = 20) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if event_type:
        c.execute('SELECT event_type, description, countries_involved, timestamp FROM world_events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?', (event_type, limit))
    else:
        c.execute('SELECT event_type, description, countries_involved, timestamp FROM world_events ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

# =====================================================================
# ТЕХНОЛОГИИ
# =====================================================================

def save_technology(tech_name: str, level: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO technologies (tech_name, level) VALUES (?, ?) ON CONFLICT(tech_name) DO UPDATE SET level = ?', (tech_name, level, level))
    conn.commit()
    conn.close()

def get_all_technologies() -> Dict[str, int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT tech_name, level FROM technologies')
    rows = c.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

# =====================================================================
# СОХРАНЕНИЕ МИРА В JSON (НЕ СТИРАЕТСЯ НА RENDER)
# =====================================================================

def save_world_state(world_data: dict):
    """Сохраняет мир в JSON файл."""
    # Создаём директорию если нужно
    os.makedirs(os.path.dirname(WORLD_FILE) if os.path.dirname(WORLD_FILE) else ".", exist_ok=True)
    
    # Ограничиваем историю новостей
    if 'news_history' in world_data and len(world_data['news_history']) > 50:
        world_data['news_history'] = world_data['news_history'][-50:]
    
    try:
        with open(WORLD_FILE, "w", encoding="utf-8") as f:
            json.dump(world_data, f, ensure_ascii=False, indent=2)
        print(f"💾 Мир сохранён в {WORLD_FILE} (ход {world_data.get('turn', 0)})")
    except Exception as e:
        print(f"❌ Ошибка сохранения мира: {e}")


def load_world_state() -> dict:
    """Загружает мир из JSON файла."""
    if not os.path.exists(WORLD_FILE):
        print(f"📭 Файл {WORLD_FILE} не найден, создаю новый мир")
        return {}
    
    try:
        with open(WORLD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Восстанавливаем типы
        if 'world_tension' in data:
            data['world_tension'] = float(data['world_tension'])
        if 'turn' in data:
            data['turn'] = int(data['turn'])
        if 'year' in data:
            data['year'] = int(data['year'])
        
        print(f"📥 Мир загружен из {WORLD_FILE} (ход {data.get('turn', 0)})")
        return data
    except Exception as e:
        print(f"⚠️ Ошибка загрузки мира: {e}")
        return {}

# =====================================================================
# ОЧИСТКА
# =====================================================================

def clear_user_history(chat_id: int, user_id: int = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if user_id:
        c.execute('DELETE FROM dialog_history WHERE chat_id = ? AND user_id = ?', (chat_id, user_id))
    else:
        c.execute('DELETE FROM dialog_history WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def clear_all_history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM dialog_history')
    c.execute('DELETE FROM verdicts')
    c.execute('DELETE FROM world_events')
    c.execute('DELETE FROM users')
    c.execute('DELETE FROM economy')
    c.execute('DELETE FROM technologies')
    conn.commit()
    conn.close()
    
    # Удаляем файл мира
    if os.path.exists(WORLD_FILE):
        os.remove(WORLD_FILE)
    
    print("🗑️ Вся история очищена")

# =====================================================================
# АВТО-ИНИЦИАЛИЗАЦИЯ
# =====================================================================

try:
    init_db()
except Exception as e:
    print(f"⚠️ Ошибка инициализации БД: {e}")
