"""
HISTORY.PY — БАЗА ДАННЫХ (ПОЛНАЯ ВЕРСИЯ)
==========================================
Сохранение пользователей, экономики, диалогов,
вердиктов, мировых событий, технологий,
и ПОЛНОГО СОСТОЯНИЯ МИРА.
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Tuple, Dict

DB_PATH = "rp_bot.db"

# =====================================================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# =====================================================================

def init_db():
    """Создаёт все таблицы если их нет"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            country TEXT,
            year INTEGER DEFAULT 2024
        )
    ''')
    
    # Таблица экономики
    c.execute('''
        CREATE TABLE IF NOT EXISTS economy (
            user_id INTEGER PRIMARY KEY,
            budget INTEGER DEFAULT 10000000,
            steel INTEGER DEFAULT 1000,
            oil INTEGER DEFAULT 500,
            grain INTEGER DEFAULT 2000,
            gold INTEGER DEFAULT 100
        )
    ''')
    
    # Таблица истории диалогов
    c.execute('''
        CREATE TABLE IF NOT EXISTS dialog_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица вердиктов
    c.execute('''
        CREATE TABLE IF NOT EXISTS verdicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            topic TEXT,
            verdict TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица мировых событий
    c.execute('''
        CREATE TABLE IF NOT EXISTS world_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            description TEXT,
            countries_involved TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица технологий
    c.execute('''
        CREATE TABLE IF NOT EXISTS technologies (
            tech_name TEXT PRIMARY KEY,
            level INTEGER DEFAULT 1
        )
    ''')
    
    # Таблица состояния мира (НОВАЯ)
    c.execute('''
        CREATE TABLE IF NOT EXISTS world_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# =====================================================================
# ПОЛЬЗОВАТЕЛИ
# =====================================================================

def save_country(user_id: int, country: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO users (user_id, country) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET country = ?
    ''', (user_id, country, country))
    conn.commit()
    conn.close()

def save_year(user_id: int, year: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO users (user_id, year) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET year = ?
    ''', (user_id, year, year))
    conn.commit()
    conn.close()

def save_country_and_year(user_id: int, country: str, year: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO users (user_id, country, year) VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET country = ?, year = ?
    ''', (user_id, country, year, country, year))
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

def get_user_info(user_id: int) -> Dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT country, year FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return {"country": row[0], "year": row[1]} if row else {"country": None, "year": 2024}

# =====================================================================
# ЭКОНОМИКА
# =====================================================================

def get_economy(user_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT budget, steel, oil, grain, gold FROM economy WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"budget": row[0], "steel": row[1], "oil": row[2], "grain": row[3], "gold": row[4]}
    return None

def init_economy(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO economy (user_id, budget, steel, oil, grain, gold)
        VALUES (?, 10000000, 1000, 500, 2000, 100)
    ''', (user_id,))
    conn.commit()
    conn.close()

def update_economy(user_id: int, budget: int = None, steel: int = None,
                   oil: int = None, grain: int = None, gold: int = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO economy (user_id) VALUES (?)', (user_id,))
    
    updates = []
    params = []
    if budget is not None:
        updates.append("budget = ?")
        params.append(budget)
    if steel is not None:
        updates.append("steel = ?")
        params.append(steel)
    if oil is not None:
        updates.append("oil = ?")
        params.append(oil)
    if grain is not None:
        updates.append("grain = ?")
        params.append(grain)
    if gold is not None:
        updates.append("gold = ?")
        params.append(gold)
    
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
    c.execute('''
        INSERT INTO dialog_history (chat_id, user_id, role, content)
        VALUES (?, ?, ?, ?)
    ''', (chat_id, user_id, role, content))
    conn.commit()
    conn.close()

def get_dialog_history(chat_id: int, user_id: int = None, limit: int = 50) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if user_id:
        c.execute('''
            SELECT role, content, timestamp FROM dialog_history
            WHERE chat_id = ? AND user_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (chat_id, user_id, limit))
    else:
        c.execute('''
            SELECT role, content, timestamp FROM dialog_history
            WHERE chat_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (chat_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows[::-1]

# =====================================================================
# ВЕРДИКТЫ
# =====================================================================

def save_verdict(user_id: int, topic: str, verdict: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO verdicts (user_id, topic, verdict)
        VALUES (?, ?, ?)
    ''', (user_id, topic, verdict))
    conn.commit()
    conn.close()

def get_verdicts(user_id: int, topic: str = None, limit: int = 10) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if topic:
        c.execute('''
            SELECT topic, verdict, timestamp FROM verdicts
            WHERE user_id = ? AND topic LIKE ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (user_id, f'%{topic}%', limit))
    else:
        c.execute('''
            SELECT topic, verdict, timestamp FROM verdicts
            WHERE user_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

# =====================================================================
# МИРОВЫЕ СОБЫТИЯ
# =====================================================================

def save_world_event(event_type: str, description: str, countries_involved: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO world_events (event_type, description, countries_involved)
        VALUES (?, ?, ?)
    ''', (event_type, description, countries_involved))
    conn.commit()
    conn.close()

def get_world_events(event_type: str = None, limit: int = 20) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if event_type:
        c.execute('''
            SELECT event_type, description, countries_involved, timestamp
            FROM world_events WHERE event_type = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (event_type, limit))
    else:
        c.execute('''
            SELECT event_type, description, countries_involved, timestamp
            FROM world_events ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

# =====================================================================
# ТЕХНОЛОГИИ
# =====================================================================

def save_technology(tech_name: str, level: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO technologies (tech_name, level) VALUES (?, ?)
        ON CONFLICT(tech_name) DO UPDATE SET level = ?
    ''', (tech_name, level, level))
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
# СОХРАНЕНИЕ И ЗАГРУЗКА ВСЕГО МИРА
# =====================================================================

def save_world_state(world_data: dict):
    """Сохраняет всё состояние мира в БД."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS world_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Сохраняем каждую часть мира как JSON
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('countries', json.dumps(world_data.get('countries', {}))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('wars', json.dumps(world_data.get('wars', {}))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('alliances', json.dumps(world_data.get('alliances', {}))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('sanctions', json.dumps(world_data.get('sanctions', {}))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('marionettes', json.dumps(world_data.get('marionettes', {}))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('annexed', json.dumps(world_data.get('annexed', {}))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('technologies', json.dumps(world_data.get('technologies', {}))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('infrastructure', json.dumps(world_data.get('infrastructure', {}))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('world_tension', str(world_data.get('world_tension', 0.0))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('turn', str(world_data.get('turn', 0))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('year', str(world_data.get('year', 2024))))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('month', world_data.get('month', 'январь')))
    c.execute('INSERT OR REPLACE INTO world_state (key, value) VALUES (?, ?)',
              ('news_history', json.dumps(world_data.get('news_history', []))))
    
    conn.commit()
    conn.close()
    print("💾 Мир сохранён в БД")


def load_world_state() -> dict:
    """Загружает состояние мира из БД."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS world_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    c.execute('SELECT key, value FROM world_state')
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return {}
    
    data = {}
    for key, value in rows:
        if key in ['countries', 'wars', 'alliances', 'sanctions', 'marionettes', 
                    'annexed', 'technologies', 'infrastructure', 'news_history']:
            try:
                data[key] = json.loads(value)
            except:
                data[key] = {}
        elif key in ['world_tension']:
            try:
                data[key] = float(value)
            except:
                data[key] = 0.0
        elif key in ['turn']:
            try:
                data[key] = int(value)
            except:
                data[key] = 0
        elif key == 'year':
            try:
                data[key] = int(value)
            except:
                data[key] = 2024
        else:
            data[key] = value
    
    return data

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
    """Полная очистка всего (для вайпа)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM dialog_history')
    c.execute('DELETE FROM verdicts')
    c.execute('DELETE FROM world_events')
    c.execute('DELETE FROM users')
    c.execute('DELETE FROM economy')
    c.execute('DELETE FROM technologies')
    c.execute('DELETE FROM world_state')
    conn.commit()
    conn.close()
    print("🗑️ Вся история очищена")

# =====================================================================
# АВТО-ИНИЦИАЛИЗАЦИЯ
# =====================================================================

try:
    init_db()
except Exception as e:
    print(f"⚠️ Ошибка инициализации БД: {e}")

# =====================================================================
# ЭКСПОРТ
# =====================================================================

__all__ = [
    'init_db',
    'save_country',
    'save_year',
    'save_country_and_year',
    'get_country',
    'get_year',
    'get_user_info',
    'get_economy',
    'init_economy',
    'update_economy',
    'save_dialog',
    'get_dialog_history',
    'save_verdict',
    'get_verdicts',
    'save_world_event',
    'get_world_events',
    'save_technology',
    'get_all_technologies',
    'save_world_state',
    'load_world_state',
    'clear_user_history',
    'clear_all_history',
]
