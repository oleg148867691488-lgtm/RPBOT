"""
ECONOMY.PY — РЕАЛИСТИЧНАЯ ЭКОНОМИКА
=====================================
Без читов. Армия зависит от населения и ВВП.
Если нет данных в интернете — ИИ оценивает сам.
"""

import random
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

# =====================================================================
# ЦЕНЫ НА РЕСУРСЫ (РЕАЛИСТИЧНЫЕ)
# =====================================================================

PRICES = {
    "steel": 700,      # $ за тонну
    "oil": 80,         # $ за баррель
    "grain": 220,      # $ за тонну
    "gold": 2000,      # $ за унцию
    "uranium": 5000,   # $ за кг
    "microchips": 50000,  # $ за партию
}

# =====================================================================
# БАЗОВЫЕ ДАННЫЕ ПО СТРАНАМ (ЗАГЛУШКИ)
# =====================================================================

# Если интернет недоступен — используем примерные оценки
# Данные: население (млн), ВВП (трлн $), армия (тыс), танки, самолёты, корабли
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
}

# =====================================================================
# ПОЛУЧЕНИЕ ДАННЫХ О СТРАНЕ (ИНТЕРНЕТ ИЛИ ОЦЕНКА)
# =====================================================================

async def get_country_data(country_name: str) -> Dict:
    """
    Получает реальные данные о стране.
    Сначала ищет в интернете, если нет — оценивает через ИИ.
    Если ИИ недоступен — использует заглушки.
    """
    
    # Проверяем локальный кэш
    if country_name in COUNTRY_ESTIMATES:
        print(f"📊 Использую кэшированные данные для {country_name}")
        return COUNTRY_ESTIMATES[country_name]
    
    # Пробуем найти в интернете
    try:
        search_query = (
            f"{country_name} численность армии население ВВП "
            f"количество танков самолётов кораблей 2024"
        )
        
        search_result = await ai.search_web(search_query, f"Военная статистика {country_name}")
        
        if search_result and "ошибка" not in search_result.lower():
            # Просим ИИ извлечь цифры
            prompt = f"""
Из этого текста извлеки ТОЛЬКО JSON с данными о стране {country_name}:

{search_result[:1000]}

Формат JSON:
{{
    "population": число в миллионах (например 144.0),
    "gdp": число в триллионах долларов (например 1.8),
    "army": численность армии в тысячах (например 900),
    "tanks": количество танков (например 3000),
    "aircraft": количество самолётов (например 4000),
    "ships": количество кораблей (например 300)
}}

Если точных цифр нет — дай ПРИМЕРНУЮ оценку на основе похожих стран.
Ответь ТОЛЬКО JSON, без пояснений.
"""
            
            response = await ai.ask_groq(prompt, temperature=0.1, max_tokens=200)
            
            # Парсим JSON
            import json
            import re
            
            # Ищем JSON в ответе
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                data = json.loads(json_match.group())
                
                # Сохраняем в кэш
                COUNTRY_ESTIMATES[country_name] = data
                print(f"✅ Данные для {country_name} получены из интернета")
                return data
    
    except Exception as e:
        print(f"⚠️ Ошибка поиска данных для {country_name}: {e}")
    
    # Если интернет не помог — ИИ оценивает сам
    try:
        prompt = f"""
Ты — военный аналитик. Дай ПРИМЕРНУЮ оценку для страны {country_name}.

НЕ ИЩИ в интернете. Просто оцени на основе:
- Географического положения
- Размера страны
- Экономического развития
- Исторического контекста
- Похожих стран

Формат JSON:
{{
    "population": число в миллионах,
    "gdp": число в триллионах долларов,
    "army": численность армии в тысячах,
    "tanks": примерное количество танков,
    "aircraft": примерное количество самолётов,
    "ships": примерное количество кораблей
}}

Будь РЕАЛИСТИЧНЫМ. Не завышай цифры.
Для маленьких стран — маленькая армия.
Для бедных стран — слабая экономика.
Ответь ТОЛЬКО JSON.
"""
        
        response = await ai.ask_groq(prompt, temperature=0.3, max_tokens=200)
        
        import json
        import re
        
        json_match = re.search(r'\{[^}]+\}', response)
        if json_match:
            data = json.loads(json_match.group())
            COUNTRY_ESTIMATES[country_name] = data
            print(f✅ Оценка для {country_name} сгенерирована ИИ")
            return data
    
    except Exception as e:
        print(f"⚠️ Ошибка оценки через ИИ: {e}")
    
    # АБСОЛЮТНЫЙ FALLBACK: базовые цифры
    fallback = {
        "population": 10.0,
        "gdp": 0.1,
        "army": 50,
        "tanks": 100,
        "aircraft": 50,
        "ships": 10
    }
    COUNTRY_ESTIMATES[country_name] = fallback
    print(f"⚠️ Использую FALLBACK для {country_name}")
    return fallback


# =====================================================================
# РАСЧЁТ ВОЕННОГО БЮДЖЕТА
# =====================================================================

def calculate_military_budget(gdp: float, army_size: float) -> int:
    """
    Реалистичный расчёт военного бюджета.
    
    Args:
        gdp: ВВП в триллионах долларов
        army_size: размер армии в тысячах
    
    Returns:
        Военный бюджет в долларах
    """
    # Средний % ВВП на оборону: 2-4%
    gdp_total = gdp * 1_000_000_000_000  # переводим в доллары
    
    if army_size > 1000:
        defense_pct = random.uniform(3.0, 5.0)
    elif army_size > 200:
        defense_pct = random.uniform(2.0, 4.0)
    else:
        defense_pct = random.uniform(1.0, 3.0)
    
    return int(gdp_total * defense_pct / 100)


# =====================================================================
# ПОЛУЧЕНИЕ ЭКОНОМИКИ ИГРОКА
# =====================================================================

def get_user_economy(user_id: int) -> Dict:
    """Получить экономику пользователя (с авто-инициализацией)"""
    economy = get_economy(user_id)
    if not economy:
        init_economy(user_id)
        economy = get_economy(user_id)
    return economy


# =====================================================================
# ИНИЦИАЛИЗАЦИЯ СТРАНЫ (ВЫЗЫВАЕТСЯ ПРИ /COUNTRY)
# =====================================================================

async def init_country_economy(user_id: int, country_name: str):
    """
    Инициализирует экономику страны на основе РЕАЛЬНЫХ данных.
    Вызывается при смене страны.
    """
    # Получаем данные о стране
    data = await get_country_data(country_name)
    
    # Рассчитываем военный бюджет
    military_budget = calculate_military_budget(data["gdp"], data["army"])
    
    # Ресурсы пропорционально размеру страны
    population = data["population"]  # в миллионах
    gdp = data["gdp"]  # в триллионах
    
    # Стартовый бюджет = военный бюджет
    budget = military_budget
    
    # Ресурсы зависят от населения и ВВП
    steel = int(population * gdp * 500)  # тонн
    oil = int(population * gdp * 200)    # баррелей
    grain = int(population * 2000)       # тонн
    gold = int(gdp * 100)                # унций
    
    # Минимальные значения
    steel = max(steel, 10)
    oil = max(oil, 10)
    grain = max(grain, 100)
    gold = max(gold, 1)
    
    # Сохраняем в БД
    conn = __import__('sqlite3').connect("rp_bot.db")
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO economy (user_id, budget, steel, oil, grain, gold)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, budget, steel, oil, grain, gold))
    conn.commit()
    conn.close()
    
    print(f"✅ Экономика {country_name} инициализирована:")
    print(f"   Бюджет: ${budget:,}")
    print(f"   Сталь: {steel} т, Нефть: {oil} барр, Зерно: {grain} т, Золото: {gold} унц")
    
    return {
        "budget": budget,
        "steel": steel,
        "oil": oil,
        "grain": grain,
        "gold": gold,
        "country_data": data
    }


# =====================================================================
# КОМАНДА: БАЛАНС
# =====================================================================

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать баланс и ресурсы"""
    user_id = update.message.from_user.id
    economy = get_user_economy(user_id)
    country = get_country(user_id) or "неизвестная страна"
    
    # Получаем данные о стране
    data = COUNTRY_ESTIMATES.get(country, {})
    army_size = data.get("army", "?")
    tanks = data.get("tanks", "?")
    aircraft = data.get("aircraft", "?")
    
    text = (
        f"💰 *Экономика {country}*\n\n"
        f"📊 *Бюджет:* ${economy['budget']:,}\n\n"
        f"📦 *Ресурсы:*\n"
        f"🔩 Сталь: {economy['steel']} т.\n"
        f"🛢️ Нефть: {economy['oil']} барр.\n"
        f"🌾 Зерно: {economy['grain']} т.\n"
        f"🥇 Золото: {economy['gold']} унций\n\n"
        f"💪 *Военный потенциал:*\n"
        f"👥 Армия: {army_size} тыс.\n"
        f"🔫 Танки: {tanks}\n"
        f"✈️ Самолёты: {aircraft}"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown")


# =====================================================================
# КОМАНДА: ТОРГОВЛЯ
# =====================================================================

async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Купить/продать ресурсы"""
    user_id = update.message.from_user.id
    args = context.args
    
    if len(args) < 3:
        await update.message.reply_text(
            "❌ Используйте: /trade [купить/продать] [ресурс] [количество]\n"
            "Пример: `/trade купить steel 100`\n\n"
            f"Доступные ресурсы: {', '.join(PRICES.keys())}",
            parse_mode="Markdown"
        )
        return
    
    action = args[0].lower()
    resource = args[1].lower()
    
    try:
        amount = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ Количество должно быть числом.")
        return
    
    if resource not in PRICES:
        await update.message.reply_text(
            f"❌ Ресурс '{resource}' не найден. Доступны: {', '.join(PRICES.keys())}"
        )
        return
    
    economy = get_user_economy(user_id)
    price = PRICES[resource]
    total_cost = price * amount
    
    if action == "купить":
        if economy['budget'] < total_cost:
            await update.message.reply_text(
                f"❌ Недостаточно денег.\n"
                f"Нужно: ${total_cost:,}\n"
                f"У вас: ${economy['budget']:,}"
            )
            return
        
        update_economy(
            user_id,
            budget=economy['budget'] - total_cost,
            **{resource: economy[resource] + amount}
        )
        
        await update.message.reply_text(
            f"✅ Куплено {amount} {resource} за ${total_cost:,}.\n"
            f"💰 Остаток: ${economy['budget'] - total_cost:,}"
        )
    
    elif action == "продать":
        if economy[resource] < amount:
            await update.message.reply_text(
                f"❌ У вас только {economy[resource]} {resource}."
            )
            return
        
        update_economy(
            user_id,
            budget=economy['budget'] + total_cost,
            **{resource: economy[resource] - amount}
        )
        
        await update.message.reply_text(
            f"✅ Продано {amount} {resource} за ${total_cost:,}.\n"
            f"💰 Теперь: ${economy['budget'] + total_cost:,}"
        )
    
    else:
        await update.message.reply_text("❌ Используйте 'купить' или 'продать'.")


# =====================================================================
# КОМАНДА: ТОРГОВЛЯ МЕЖДУ ИГРОКАМИ
# =====================================================================

async def trade_with_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Торговля между игроками"""
    user_id = update.message.from_user.id
    args = context.args
    
    if len(args) < 4:
        await update.message.reply_text(
            "❌ Используйте: /tradeplayer @игрок [ресурс] [количество] [цена]\n"
            "Пример: `/tradeplayer @Player steel 100 700`",
            parse_mode="Markdown"
        )
        return
    
    target_username = args[0].replace("@", "")
    resource = args[1].lower()
    
    try:
        amount = int(args[2])
        price_per_unit = int(args[3])
    except ValueError:
        await update.message.reply_text("❌ Количество и цена должны быть числами.")
        return
    
    if resource not in PRICES:
        await update.message.reply_text(f"❌ Неизвестный ресурс: {resource}")
        return
    
    # Ищем второго игрока
    try:
        target_member = await context.bot.get_chat_member(
            update.message.chat.id, 
            f"@{target_username}"
        )
        target_id = target_member.user.id
    except:
        await update.message.reply_text(f"❌ Игрок @{target_username} не найден в чате.")
        return
    
    economy_seller = get_user_economy(user_id)
    economy_buyer = get_user_economy(target_id)
    
    total_cost = price_per_unit * amount
    
    # Проверки
    if economy_seller[resource] < amount:
        await update.message.reply_text(
            f"❌ У вас только {economy_seller[resource]} {resource}."
        )
        return
    
    if economy_buyer['budget'] < total_cost:
        await update.message.reply_text(
            f"❌ У @{target_username} недостаточно денег (нужно ${total_cost:,})."
        )
        return
    
    # Проводим сделку
    update_economy(
        user_id,
        budget=economy_seller['budget'] + total_cost,
        **{resource: economy_seller[resource] - amount}
    )
    update_economy(
        target_id,
        budget=economy_buyer['budget'] - total_cost,
        **{resource: economy_buyer[resource] + amount}
    )
    
    seller_name = update.message.from_user.username or "игрок"
    
    await update.message.reply_text(
        f"✅ *Сделка завершена!*\n\n"
        f"@{seller_name} продал {amount} {resource}\n"
        f"@{target_username} за ${total_cost:,}\n"
        f"Цена: ${price_per_unit} за единицу",
        parse_mode="Markdown"
    )


# =====================================================================
# КОМАНДА: ДОБАВИТЬ ДЕНЬГИ (ТОЛЬКО АДМИН)
# =====================================================================

async def add_money_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить деньги (только админ, для тестов)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите сумму. Пример: /addmoney 1000000")
        return
    
    try:
        amount = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Введите число.")
        return
    
    economy = get_user_economy(user_id)
    update_economy(user_id, budget=economy['budget'] + amount)
    
    await update.message.reply_text(
        f"✅ Добавлено ${amount:,}.\n"
        f"💰 Новый бюджет: ${economy['budget'] + amount:,}"
    )


# =====================================================================
# КОМАНДА: СТАТИСТИКА ЭКОНОМИКИ
# =====================================================================

async def economy_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расширенная статистика экономики"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    country = get_country(user_id) or "не выбрана"
    economy = get_user_economy(user_id)
    data = COUNTRY_ESTIMATES.get(country, {})
    
    text = (
        f"📊 *Экономика {country}:*\n\n"
        f"💰 Бюджет: ${economy['budget']:,}\n\n"
        f"📦 *Ресурсы:*\n"
        f"🔩 Сталь: {economy['steel']} т.\n"
        f"🛢️ Нефть: {economy['oil']} барр.\n"
        f"🌾 Зерно: {economy['grain']} т.\n"
        f"🥇 Золото: {economy['gold']} унций\n\n"
        f"🌍 *Данные страны:*\n"
        f"👥 Население: {data.get('population', '?')} млн\n"
        f"📈 ВВП: ${data.get('gdp', '?')} трлн\n"
        f"💪 Армия: {data.get('army', '?')} тыс.\n"
        f"🔫 Танки: {data.get('tanks', '?')}\n"
        f"✈️ Самолёты: {data.get('aircraft', '?')}\n"
        f"🚢 Корабли: {data.get('ships', '?')}"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown")
