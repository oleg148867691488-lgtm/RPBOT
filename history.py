import sqlite3
import json
from datetime import datetime

DB_PATH = "rp_bot.db"

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица пользователей (страна, год)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            country TEXT,
            year INTEGER
        )
    ''')
    
    # Таблица экономики (бюджет, ресурсы)
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
    
    # Таблица вердиктов (для истории)
    c.execute('''
        CREATE TABLE IF NOT EXISTS verdicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            topic TEXT,
            verdict TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# === ПОЛЬЗОВАТЕЛИ ===
def save_country(user_id: int, country: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO users (user_id, country) VALUES (?, ?)', (user_id, country))
    conn.commit()
    conn.close()

def get_country(user_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT country FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def save_year(user_id: int, year: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO users (user_id, year) VALUES (?, ?)', (user_id, year))
    conn.commit()
    conn.close()

def get_year(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT year FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 2022

# === ЭКОНОМИКА ===
def get_economy(user_id: int):
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

def update_economy(user_id: int, budget: int = None, steel: int = None, oil: int = None, grain: int = None, gold: int = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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

# === ДИАЛОГИ ===
def save_dialog(chat_id: int, user_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO dialog_history (chat_id, user_id, role, content)
        VALUES (?, ?, ?, ?)
    ''', (chat_id, user_id, role, content))
    conn.commit()
    conn.close()

def get_dialog_history(chat_id: int, user_id: int, limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT role, content, timestamp FROM dialog_history
        WHERE chat_id = ? AND user_id = ?
        ORDER BY timestamp DESC LIMIT ?
    ''', (chat_id, user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows[::-1]  # В хронологическом порядке

# === ВЕРДИКТЫ ===
def save_verdict(user_id: int, topic: str, verdict: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO verdicts (user_id, topic, verdict)
        VALUES (?, ?, ?)
    ''', (user_id, topic, verdict))
    conn.commit()
    conn.close()

def get_verdicts(user_id: int, topic: str = None, limit: int = 10):
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

# === ОЧИСТКА ===
def clear_user_history(chat_id: int, user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM dialog_history WHERE chat_id = ? AND user_id = ?', (chat_id, user_id))
    conn.commit()
    conn.close()

def clear_all_history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM dialog_history')
    conn.commit()
    conn.close()

# === ИНИЦИАЛИЗАЦИЯ ===
init_db()
