import random
import asyncio
from config import ADMIN_ID
from history import get_country, get_year, get_economy, update_economy
from war import active_wars, declare_war_command
from diplomacy import alliances, sanctions

# === ГЛАВНЫЙ ЦИКЛ ПРИНЯТИЯ РЕШЕНИЙ ===
async def decision_loop(context):
    """
    Запускается каждые 10 минут.
    Бот анализирует ситуацию и принимает решения.
    """
    if bot_stopped:
        return
    
    country = get_country(ADMIN_ID) or "неизвестная страна"
    year = get_year(ADMIN_ID) or 2022
    economy = get_economy(ADMIN_ID)
    
    if not economy:
        return
    
    budget = economy['budget']
    
    # === 1. ЕСЛИ ДЕНЕГ МАЛО (МЕНЬШЕ 5 МЛН) — ТОРГОВАТЬ ===
    if budget < 5_000_000:
        await trade_decision(context, country, economy)
    
    # === 2. ЕСЛИ ДЕНЕГ МНОГО (БОЛЬШЕ 50 МЛН) — ИНВЕСТИРОВАТЬ ===
    elif budget > 50_000_000:
        await invest_decision(context, country, economy)
    
    # === 3. ЕСЛИ НЕТ АКТИВНЫХ ВОЙН — РЕШИТЬ, НАПАДАТЬ ИЛИ НЕТ ===
    if not active_wars:
        await war_decision(context, country, economy)
    
    # === 4. ЕСЛИ ЕСТЬ ВРАГИ — ВВЕСТИ САНКЦИИ ===
    if random.random() < 0.3:  # 30% шанс
        await sanctions_decision(context, country)
    
    # === 5. ЕСЛИ НЕТ СОЮЗНИКОВ — ПРЕДЛОЖИТЬ СОЮЗ ===
    if not alliances:
        await ally_decision(context, country)

# === 1. РЕШЕНИЕ О ТОРГОВЛЕ ===
async def trade_decision(context, country, economy):
    # Продаём ресурсы, если их много
    if economy['steel'] > 5000:
        amount = random.randint(100, 500)
        price = random.randint(600, 800)
        await context.bot.send_message(
            chat_id=saved_chats.get("news"),
            text=(
                f"📰 *{country} продаёт сталь!*\n\n"
                f"🔩 {amount} тонн по ${price}/тонна.\n"
                f"💰 Общая стоимость: ${amount * price:,}\n"
                f"📝 Напишите /trade купить steel {amount} чтобы купить."
            )
        )
        update_economy(ADMIN_ID, steel=economy['steel'] - amount, budget=economy['budget'] + (amount * price))

# === 2. РЕШЕНИЕ ОБ ИНВЕСТИЦИЯХ ===
async def invest_decision(context, country, economy):
    amount = random.randint(1_000_000, 5_000_000)
    update_economy(ADMIN_ID, budget=economy['budget'] - amount)
    
    await context.bot.send_message(
        chat_id=saved_chats.get("news"),
        text=(
            f"📰 *{country} инвестирует в экономику!*\n\n"
            f"💰 Выделено ${amount:,} на развитие инфраструктуры.\n"
            f"📈 Ожидается рост ВВП в следующем году."
        )
    )

# === 3. РЕШЕНИЕ О ВОЙНЕ ===
async def war_decision(context, country, economy):
    # Если денег больше 20 млн и армия сильная — напасть на случайную страну
    if economy['budget'] > 20_000_000 and random.random() < 0.2:  # 20% шанс
        enemies = ["Франция", "Германия", "Польша", "Италия", "Турция"]
        target = random.choice(enemies)
        
        await context.bot.send_message(
            chat_id=saved_chats.get("war"),
            text=(
                f"⚔️ *{country} рассматривает возможность войны с {target}!*\n\n"
                f"📌 Причина: Экономический конфликт.\n"
                f"⏳ До принятия решения осталось 10 минут."
            )
        )
        
        # Даём игроку время отреагировать
        await asyncio.sleep(10 * 60)  # 10 минут
        
        # Если игрок не отменил — начинаем войну
        if target not in active_wars:
            await declare_war_command(
                update=None,
                context=context,
                args=[target, "Экономический конфликт"]
            )

# === 4. РЕШЕНИЕ О САНКЦИЯХ ===
async def sanctions_decision(context, country):
    target = random.choice(["Франция", "Германия", "Польша", "Италия", "Турция"])
    
    await context.bot.send_message(
        chat_id=saved_chats.get("un"),
        text=(
            f"🚫 *{country} предлагает ввести санкции против {target}!*\n\n"
            f"📌 Причина: Нарушение международных соглашений.\n"
            f"📝 Напишите /vote [за/против] чтобы проголосовать."
        )
    )

# === 5. РЕШЕНИЕ О СОЮЗЕ ===
async def ally_decision(context, country):
    allies = ["Франция", "Германия", "Польша", "Италия", "Турция"]
    target = random.choice(allies)
    
    await context.bot.send_message(
        chat_id=saved_chats.get("un"),
        text=(
            f"🤝 *{country} предлагает союз с {target}!*\n\n"
            f"📌 Тип: Военный союз.\n"
            f"📝 Напишите /accept_ally чтобы принять."
        )
    )
