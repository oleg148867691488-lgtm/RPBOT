"""
ECONOMY.PY — РЕАЛИСТИЧНАЯ ЭКОНОМИКА
=====================================
Без читов. Армия зависит от населения и ВВП.
Если нет данных в интернете — ИИ оценивает сам.
"""

import random
import json
import re
from typing import Dict, Optional
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID
from history import (
    get_economy,
    init_economy,
    update_economy,
    get_country,
    get_year
)
from ai_manager import ai

# Цены на ресурсы
PRICES = {
    "steel": 700,
    "oil": 80,
    "grain": 220,
    "gold": 2000,
    "uranium": 5000,
    "microchips": 50000,
}

# Примерные данные по странам (заглушки)
COUNTRY_ESTIMATES = {
    "Россия": {"population": 144, "gdp": 1.8, "army": 900, "tanks": 3000, "aircraft": 4000, "ships": 300},
    "США": {"population": 334, "gdp": 26.9, "army": 1400, "tanks": 6000, "aircraft": 13000, "ships": 490},
    "Китай": {"population": 1410, "gdp": 17.7, "army": 2000, "tanks": 5000, "aircraft": 5000, "ships": 700},
    "Германия": {"population": 84, "gdp": 4.5, "army": 180, "tanks": 300, "aircraft": 400, "ships": 80},
    "Франция": {"population": 68, "gdp": 3.0, "army": 200, "tanks": 400, "aircraft": 500, "ships": 180},
    "Великобритания": {"population": 67, "gdp": 3.3, "army": 150, "tanks": 200, "aircraft": 400, "ships": 150},
    "Индия": {"population": 1428, "gdp": 3.5, "army": 1400, "tanks": 4000, "aircraft": 2000, "ships": 150},
    "Япония": {"population": 125, "gdp": 4.2, "army": 240, "tanks": 600, "aircraft": 700, "ships": 150},
    "Турция": {"population": 85, "gdp": 1.1, "army": 400, "tanks": 2000, "aircraft": 500, "ships": 150},
    "Италия": {"population": 59, "gdp": 2.2, "army": 160, "tanks": 200, "aircraft": 300, "ships": 180},
    "Швейцария": {"population": 8.7, "gdp": 0.9, "army": 20, "tanks": 100, "aircraft": 50, "ships": 0},
    "Ватикан": {"population": 0.0008, "gdp": 0.0003, "army": 0.1, "tanks": 0, "aircraft": 0, "ships": 0},
    "Люксембург": {"population": 0.65, "gdp": 0.08, "army": 1, "tanks": 0, "aircraft": 0, "ships": 0},
    "Польша": {"population": 37, "gdp": 0.8, "army": 150, "tanks": 600, "aircraft": 200, "ships": 40},
    "Украина": {"population": 33, "gdp": 0.17, "army": 500, "tanks": 800, "aircraft": 200, "ships": 20},
    "Израиль": {"population": 9.3, "gdp": 0.5, "army": 170, "tanks": 1000, "aircraft": 600, "ships": 60},
    "КНДР": {"population": 26, "gdp": 0.03, "army": 1200, "tanks": 4000, "aircraft": 500, "ships": 400},
    "Южная Корея": {"population": 52, "gdp": 1.7, "army": 600, "tanks": 2000, "aircraft": 800, "ships": 200},
    "Бразилия": {"population": 215, "gdp": 2.1, "army": 360, "tanks": 400, "aircraft": 600, "ships": 100},
    "Австралия": {"population": 26, "gdp": 1.7, "army": 60, "tanks": 50, "aircraft": 200, "ships": 50},
    "Казахстан": {"population": 19, "gdp": 0.22, "army": 70, "tanks": 300, "aircraft": 100, "ships": 0},
    "Беларусь": {"population": 9.2, "gdp": 0.07, "army": 45, "tanks": 500, "aircraft": 200, "ships": 0},
    "Испания": {"population": 47, "gdp": 1.5, "army": 120, "tanks": 300, "aircraft": 400, "ships": 140},
    "Канада": {"population": 38, "gdp": 2.1, "army": 70, "tanks": 80, "aircraft": 300, "ships": 60},
    "Швеция": {"population": 10.5, "gdp": 0.6, "army": 30, "tanks": 100, "aircraft": 200, "ships": 30},
    "Норвегия": {"population": 5.5, "gdp": 0.5, "army": 25, "tanks": 40, "aircraft": 100, "ships": 50},
}


async def get_country_data(country_name: str) -> Dict:
    """Получает данные о стране: интернет → ИИ → заглушки."""
    
    if country_name in COUNTRY_ESTIMATES:
        print(f"Использую кэшированные данные для {country_name}")
        return COUNTRY_ESTIMATES[country_name]
    
    # Пробуем интернет
    try:
        search_query = f"{country_name} численность армии население ВВП количество танков самолётов кораблей 2024"
        search_result = await ai.search_web(search_query, f"Военная статистика {country_name}")
        
        if search_result and "NO_DATA" not in search_result and len(search_result) > 50:
            prompt = f"""Из этого текста извлеки ТОЛЬКО JSON с данными о стране {country_name}:
{search_result[:1000]}

Формат: {{"population": 144.0, "gdp": 1.8, "army": 900, "tanks": 3000, "aircraft": 4000, "ships": 300}}
Если точных цифр нет — дай ПРИМЕРНУЮ оценку. Ответь ТОЛЬКО JSON."""
            
            response = await ai.ask_groq(prompt, temperature=0.1, max_tokens=200)
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                data = json.loads(json_match.group())
                COUNTRY_ESTIMATES[country_name] = data
                print(f"Данные для {country_name} получены из интернета")
                return data
    except Exception as e:
        print(f"Ошибка поиска данных для {country_name}: {e}")
    
    # ИИ оценивает сам
    try:
        prompt = f"""Ты — военный аналитик. Дай ПРИМЕРНУЮ оценку для страны {country_name}.
Оцени на основе географии, размера, экономики. Будь РЕАЛИСТИЧНЫМ.
Для маленьких стран — маленькая армия. Для бедных — слабая экономика.

Формат JSON: {{"population": 10.0, "gdp": 0.1, "army": 50, "tanks": 100, "aircraft": 50, "ships": 10}}
Ответь ТОЛЬКО JSON."""
        
        response = await ai.ask_groq(prompt, temperature=0.3, max_tokens=200)
        json_match = re.search(r'\{[^}]+\}', response)
        if json_match:
            data = json.loads(json_match.group())
            COUNTRY_ESTIMATES[country_name] = data
            print(f"Оценка для {country_name} сгенерирована ИИ")
            return data
    except Exception as e:
        print(f"Ошибка оценки через ИИ: {e}")
    
    # Заглушка
    fallback = {"population": 10.0, "gdp": 0.1, "army": 50, "tanks": 100, "aircraft": 50, "ships": 10}
    COUNTRY_ESTIMATES[country_name] = fallback
    print(f"Использую FALLBACK для {country_name}")
    return fallback


def calculate_military_budget(gdp: float, army_size: float) -> int:
    gdp_total = gdp * 1_000_000_000_000
    if army_size > 1000:
        defense_pct = random.uniform(3.0, 5.0)
    elif army_size > 200:
        defense_pct = random.uniform(2.0, 4.0)
    else:
        defense_pct = random.uniform(1.0, 3.0)
    return int(gdp_total * defense_pct / 100)


def get_user_economy(user_id: int) -> Dict:
    economy = get_economy(user_id)
    if not economy:
        init_economy(user_id)
        economy = get_economy(user_id)
    return economy


async def init_country_economy(user_id: int, country_name: str):
    """Инициализирует экономику страны на основе РЕАЛЬНЫХ данных."""
    data = await get_country_data(country_name)
    military_budget = calculate_military_budget(data["gdp"], data["army"])
    
    population = data["population"]
    gdp = data["gdp"]
    
    budget = military_budget
    steel = max(int(population * gdp * 500), 10)
    oil = max(int(population * gdp * 200), 10)
    grain = max(int(population * 2000), 100)
    gold = max(int(gdp * 100), 1)
    
    import sqlite3
    conn = sqlite3.connect("rp_bot.db")
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO economy (user_id, budget, steel, oil, grain, gold) VALUES (?, ?, ?, ?, ?, ?)',
              (user_id, budget, steel, oil, grain, gold))
    conn.commit()
    conn.close()
    
    print(f"Экономика {country_name} инициализирована: бюджет ${budget:,}")
    return {"budget": budget, "steel": steel, "oil": oil, "grain": grain, "gold": gold, "country_data": data}


# =====================================================================
# КОМАНДЫ
# =====================================================================

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    economy = get_user_economy(user_id)
    country = get_country(user_id) or "неизвестная страна"
    data = COUNTRY_ESTIMATES.get(country, {})
    
    text = (
        f"Экономика {country}\n\n"
        f"Бюджет: ${economy['budget']:,}\n\n"
        f"Ресурсы:\n"
        f"Сталь: {economy['steel']} т.\n"
        f"Нефть: {economy['oil']} барр.\n"
        f"Зерно: {economy['grain']} т.\n"
        f"Золото: {economy['gold']} унций\n\n"
        f"Военный потенциал:\n"
        f"Армия: {data.get('army', '?')} тыс.\n"
        f"Танки: {data.get('tanks', '?')}\n"
        f"Самолёты: {data.get('aircraft', '?')}"
    )
    await update.message.reply_text(text)


async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    
    if len(args) < 3:
        await update.message.reply_text("Используйте: /trade [купить/продать] [ресурс] [количество]\nПример: /trade купить steel 100")
        return
    
    action = args[0].lower()
    resource = args[1].lower()
    try:
        amount = int(args[2])
    except ValueError:
        await update.message.reply_text("Количество должно быть числом.")
        return
    
    if resource not in PRICES:
        await update.message.reply_text(f"Ресурс '{resource}' не найден. Доступны: {', '.join(PRICES.keys())}")
        return
    
    economy = get_user_economy(user_id)
    price = PRICES[resource]
    total_cost = price * amount
    
    if action == "купить":
        if economy['budget'] < total_cost:
            await update.message.reply_text(f"Недостаточно денег. Нужно ${total_cost:,}, у вас ${economy['budget']:,}")
            return
        update_economy(user_id, budget=economy['budget'] - total_cost, **{resource: economy[resource] + amount})
        await update.message.reply_text(f"Куплено {amount} {resource} за ${total_cost:,}.")
    
    elif action == "продать":
        if economy[resource] < amount:
            await update.message.reply_text(f"У вас только {economy[resource]} {resource}.")
            return
        update_economy(user_id, budget=economy['budget'] + total_cost, **{resource: economy[resource] - amount})
        await update.message.reply_text(f"Продано {amount} {resource} за ${total_cost:,}.")
    else:
        await update.message.reply_text("Используйте 'купить' или 'продать'.")


async def trade_with_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    
    if len(args) < 4:
        await update.message.reply_text("Используйте: /tradeplayer @игрок [ресурс] [количество] [цена]")
        return
    
    target_username = args[0].replace("@", "")
    resource = args[1].lower()
    try:
        amount = int(args[2])
        price_per_unit = int(args[3])
    except ValueError:
        await update.message.reply_text("Количество и цена должны быть числами.")
        return
    
    if resource not in PRICES:
        await update.message.reply_text(f"Неизвестный ресурс: {resource}")
        return
    
    try:
        target_member = await context.bot.get_chat_member(update.message.chat.id, f"@{target_username}")
        target_id = target_member.user.id
    except:
        await update.message.reply_text(f"Игрок @{target_username} не найден в чате.")
        return
    
    economy_seller = get_user_economy(user_id)
    economy_buyer = get_user_economy(target_id)
    total_cost = price_per_unit * amount
    
    if economy_seller[resource] < amount:
        await update.message.reply_text(f"У вас только {economy_seller[resource]} {resource}.")
        return
    if economy_buyer['budget'] < total_cost:
        await update.message.reply_text(f"У @{target_username} недостаточно денег.")
        return
    
    update_economy(user_id, budget=economy_seller['budget'] + total_cost, **{resource: economy_seller[resource] - amount})
    update_economy(target_id, budget=economy_buyer['budget'] - total_cost, **{resource: economy_buyer[resource] + amount})
    
    seller_name = update.message.from_user.username or "игрок"
    await update.message.reply_text(f"Сделка: @{seller_name} продал {amount} {resource} @{target_username} за ${total_cost:,}")


async def add_money_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Укажите сумму: /addmoney 1000000")
        return
    
    try:
        amount = int(args[0])
    except ValueError:
        await update.message.reply_text("Введите число.")
        return
    
    economy = get_user_economy(ADMIN_ID)
    update_economy(ADMIN_ID, budget=economy['budget'] + amount)
    await update.message.reply_text(f"Добавлено ${amount:,}.")


async def economy_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("Доступ запрещён.")
        return
    
    country = get_country(ADMIN_ID) or "не выбрана"
    economy = get_user_economy(ADMIN_ID)
    data = COUNTRY_ESTIMATES.get(country, {})
    
    text = (
        f"Экономика {country}:\n\n"
        f"Бюджет: ${economy['budget']:,}\n\n"
        f"Ресурсы:\n"
        f"Сталь: {economy['steel']} т.\n"
        f"Нефть: {economy['oil']} барр.\n"
        f"Зерно: {economy['grain']} т.\n"
        f"Золото: {economy['gold']} унций\n\n"
        f"Данные страны:\n"
        f"Население: {data.get('population', '?')} млн\n"
        f"ВВП: ${data.get('gdp', '?')} трлн\n"
        f"Армия: {data.get('army', '?')} тыс.\n"
        f"Танки: {data.get('tanks', '?')}\n"
        f"Самолёты: {data.get('aircraft', '?')}\n"
        f"Корабли: {data.get('ships', '?')}"
    )
    await update.message.reply_text(text)
