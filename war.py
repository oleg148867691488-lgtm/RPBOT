"""
WAR.PY — СИСТЕМА ВОЙНЫ
=======================
Исправленная версия: update=None больше не ломает бота.
"""

import random
import asyncio
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID, saved_chats
from history import get_country, get_year, get_economy, update_economy

# =====================================================================
# ХРАНИЛИЩЕ АКТИВНЫХ ВОЙН
# =====================================================================
active_wars = {}

# =====================================================================
# ОБЪЯВЛЕНИЕ ВОЙНЫ
# =====================================================================

async def declare_war_command(
    update: Optional[Update] = None,
    context: ContextTypes.DEFAULT_TYPE = None,
    args: list = None
):
    """
    Объявить войну другой стране.
    
    Может вызываться:
    - Из команды /war (update есть)
    - Из decision_engine (update=None, args передаются)
    """
    
    # Определяем user_id в зависимости от источника вызова
    if update is not None:
        user_id = update.message.from_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Доступ запрещён.")
            return
        if args is None:
            args = context.args
        chat_id = update.message.chat.id
    else:
        user_id = ADMIN_ID
        chat_id = saved_chats.get("war") or saved_chats.get("news")
    
    # Проверяем аргументы
    if not args or len(args) < 2:
        if update:
            await update.message.reply_text(
                "❌ Используйте: /war [страна-противник] [причина]"
            )
        return
    
    defender = args[0]
    reason = " ".join(args[1:])
    
    attacker = get_country(user_id) or "неизвестная страна"
    year = get_year(user_id) or 2024
    
    # Проверяем, не воюем ли уже
    for war_id, war in active_wars.items():
        if war["status"] in ["active", "waiting_for_response"]:
            if war["attacker"] == attacker or war["defender"] == attacker:
                if update:
                    await update.message.reply_text(
                        f"❌ *{attacker}* уже участвует в войне с *{war['defender'] if war['attacker'] == attacker else war['attacker']}*.",
                        parse_mode="Markdown"
                    )
                return
            
            if war["defender"] == defender:
                if update:
                    await update.message.reply_text(
                        f"❌ *{defender}* уже воюет с *{war['attacker']}*.",
                        parse_mode="Markdown"
                    )
                return
    
    # Экономика атакующего
    economy = get_economy(user_id)
    if economy and economy['budget'] < 10_000_000:
        if update:
            await update.message.reply_text(
                f"❌ Недостаточно бюджета для войны. Нужно минимум $10,000,000, у вас ${economy['budget']:,}."
            )
        return
    
    # Создаём войну
    war_id = f"{attacker}_{defender}_{year}_{len(active_wars)}"
    
    # Силы сторон (реалистичные)
    attacker_army = random.randint(50, 150) * 1000
    defender_army = random.randint(30, 120) * 1000
    
    active_wars[war_id] = {
        "attacker": attacker,
        "defender": defender,
        "reason": reason,
        "year": year,
        "status": "waiting_for_response",
        "turns": 0,
        "attacker_losses": 0,
        "defender_losses": 0,
        "attacker_army": attacker_army,
        "defender_army": defender_army,
        "responded": False,
        "strategy": None,
        "chat_id": chat_id,
        "terrain": random.choice(["plain", "hills", "forest", "urban"]),
        "weather": random.choice(["clear", "rain", "fog"]),
        "war_type": "conventional",
    }
    
    # Сохраняем в историю
    from history import save_world_event
    save_world_event("war_declared", f"{attacker} объявил войну {defender}. Причина: {reason}", f"{attacker},{defender}")
    
    message = (
        f"⚔️ *ВОЙНА ОБЪЯВЛЕНА!*\n\n"
        f"📌 *{attacker}* объявляет войну *{defender}*!\n"
        f"📝 Причина: {reason}\n"
        f"📅 Год: {year}\n"
        f"💪 Силы: {attacker} — {attacker_army:,}, {defender} — {defender_army:,}\n\n"
        f"⏳ У {defender} есть 30 минут, чтобы ответить.\n"
        f"📌 Используйте `/respond согласиться` или `/respond отказаться`"
    )
    
    # Отправляем в чат
    if update:
        await update.message.reply_text(message, parse_mode="Markdown")
    
    # Отправляем в военный чат
    war_chat = saved_chats.get("war")
    if war_chat and context and context.bot:
        await context.bot.send_message(chat_id=war_chat, text=message, parse_mode="Markdown")
    
    # Запускаем таймер ответа
    if context:
        asyncio.create_task(war_response_timer(war_id, context))


# =====================================================================
# ТАЙМЕР ОТВЕТА НА ВОЙНУ
# =====================================================================

async def war_response_timer(war_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Ждёт 30 минут ответа. Если нет — бот решает сам."""
    
    await asyncio.sleep(30 * 60)  # 30 минут
    
    if war_id not in active_wars:
        return
    
    war = active_wars[war_id]
    
    if not war["responded"]:
        # Бот выбирает стратегию за защитника
        if war["defender_army"] > war["attacker_army"] * 1.5:
            strategy = "оборона"
        elif war["defender_army"] > war["attacker_army"]:
            strategy = "контрнаступление"
        else:
            strategy = "партизаны"
        
        war["strategy"] = strategy
        war["status"] = "active"
        war["responded"] = True
        
        # Уведомляем
        if context and context.bot:
            chat_id = war.get("chat_id") or saved_chats.get("war")
            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⏳ *{war['defender']}* не ответил на объявление войны!\n\n"
                        f"🤖 Бот выбрал стратегию: *{strategy}*\n"
                        f"⚔️ Война начинается автоматически!"
                    ),
                    parse_mode="Markdown"
                )
        
        # Запускаем цикл войны
        asyncio.create_task(war_loop(war_id, context))


# =====================================================================
# ОТВЕТ НА ВОЙНУ
# =====================================================================

async def respond_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответить на объявление войны"""
    user_id = update.message.from_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ Используйте: /respond [согласиться/отказаться]"
        )
        return
    
    action = args[0].lower()
    country = get_country(user_id) or "неизвестная страна"
    
    for war_id, war in active_wars.items():
        if war["defender"] == country and war["status"] == "waiting_for_response":
            war["responded"] = True
            
            if action in ["согласиться", "принять", "yes", "да"]:
                war["status"] = "active"
                war["strategy"] = "оборона"  # По умолчанию
                
                message = (
                    f"⚔️ *{country} ПРИНИМАЕТ ВЫЗОВ!*\n\n"
                    f"Война против *{war['attacker']}* начинается!\n"
                    f"Стратегия по умолчанию: оборона\n"
                    f"Изменить: /strategy [наступление/оборона/партизаны]\n\n"
                    f"💪 Силы: {war['attacker']} — {war['attacker_army']:,}, "
                    f"{war['defender']} — {war['defender_army']:,}"
                )
                
                await update.message.reply_text(message, parse_mode="Markdown")
                
                # Запускаем цикл войны
                asyncio.create_task(war_loop(war_id, context))
                return
            
            elif action in ["отказаться", "отказ", "no", "нет"]:
                war["status"] = "cancelled"
                
                message = (
                    f"🕊️ *{country} ОТКАЗАЛАСЬ от войны.*\n\n"
                    f"Конфликт с *{war['attacker']}* предотвращён.\n"
                    f"Потеря престижа: -10"
                )
                
                await update.message.reply_text(message, parse_mode="Markdown")
                
                # Удаляем войну через минуту
                await asyncio.sleep(60)
                if war_id in active_wars:
                    del active_wars[war_id]
                return
    
    await update.message.reply_text("❌ Нет активных запросов на войну для вашей страны.")


# =====================================================================
# СМЕНА СТРАТЕГИИ
# =====================================================================

async def strategy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сменить стратегию в активной войне"""
    user_id = update.message.from_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ Доступные стратегии:\n"
            "• `/strategy наступление` — атака всеми силами\n"
            "• `/strategy оборона` — укрепление позиций\n"
            "• `/strategy партизаны` — диверсии и засады\n"
            "• `/strategy контрнаступление` — дождаться и ударить\n"
            "• `/strategy блицкриг` — быстрый прорыв (если есть танки)",
            parse_mode="Markdown"
        )
        return
    
    strategy = args[0].lower()
    valid_strategies = ["наступление", "оборона", "партизаны", "контрнаступление", "блицкриг"]
    
    if strategy not in valid_strategies:
        await update.message.reply_text(
            f"❌ Неизвестная стратегия. Доступны: {', '.join(valid_strategies)}"
        )
        return
    
    country = get_country(user_id) or "неизвестная страна"
    
    for war_id, war in active_wars.items():
        if (war["attacker"] == country or war["defender"] == country) and war["status"] == "active":
            war["strategy"] = strategy
            await update.message.reply_text(
                f"✅ Стратегия изменена на: *{strategy}*\n"
                f"⚔️ Война: {war['attacker']} vs {war['defender']}",
                parse_mode="Markdown"
            )
            return
    
    await update.message.reply_text("❌ Ваша страна не участвует в активной войне.")


# =====================================================================
# ЦИКЛ ВОЙНЫ
# =====================================================================

async def war_loop(war_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Автоматический цикл войны (ходы каждые 4 минуты = 1 игровой день)"""
    
    while war_id in active_wars:
        war = active_wars[war_id]
        
        if war["status"] != "active":
            break
        
        war["turns"] += 1
        
        # Делаем ход
        result = await make_war_turn(war)
        
        # Отправляем результат
        chat_id = war.get("chat_id") or saved_chats.get("war")
        if chat_id and context and context.bot:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result,
                parse_mode="Markdown"
            )
        
        # Проверяем окончание
        if war["attacker_army"] < 10000 or war["defender_army"] < 10000:
            await end_war(war_id, context)
            break
        
        # Проверяем на затяжную войну (больше 20 ходов)
        if war["turns"] > 20:
            war["status"] = "stalemate"
            if context and context.bot:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"🤝 *Позиционный тупик!*\n\n"
                        f"Война между {war['attacker']} и {war['defender']} зашла в тупик.\n"
                        f"Обе стороны истощены. Предлагаются переговоры."
                    ),
                    parse_mode="Markdown"
                )
            break
        
        await asyncio.sleep(4 * 60)  # 4 минуты = 1 игровой день


# =====================================================================
# ХОД ВОЙНЫ
# =====================================================================

async def make_war_turn(war: dict) -> str:
    """Один такт боя с учётом стратегии, местности, погоды"""
    
    attacker = war["attacker"]
    defender = war["defender"]
    strategy = war.get("strategy", "наступление")
    terrain = war.get("terrain", "plain")
    weather = war.get("weather", "clear")
    
    # Модификаторы стратегий
    strategy_mods = {
        "наступление": {"attack": 1.3, "defense": 0.7, "risk": "high"},
        "оборона": {"attack": 0.6, "defense": 1.5, "risk": "low"},
        "партизаны": {"attack": 0.8, "defense": 1.2, "risk": "medium"},
        "контрнаступление": {"attack": 1.4, "defense": 0.6, "risk": "very_high"},
        "блицкриг": {"attack": 1.6, "defense": 0.4, "risk": "extreme"},
    }
    
    # Модификаторы местности
    terrain_mods = {
        "plain": {"tank": 1.5, "infantry": 1.0, "air": 1.0, "defense": 1.0},
        "hills": {"tank": 0.8, "infantry": 1.1, "air": 0.9, "defense": 1.3},
        "forest": {"tank": 0.5, "infantry": 1.3, "air": 0.6, "defense": 1.8},
        "mountains": {"tank": 0.1, "infantry": 0.7, "air": 0.5, "defense": 5.0},
        "urban": {"tank": 0.3, "infantry": 1.5, "air": 0.4, "defense": 3.0},
    }
    
    # Модификаторы погоды
    weather_mods = {
        "clear": {"air": 1.0, "infantry": 1.0, "supply": 1.0},
        "rain": {"air": 0.6, "infantry": 0.9, "supply": 0.8},
        "fog": {"air": 0.1, "infantry": 0.8, "supply": 0.9},
        "snow": {"air": 0.3, "infantry": 0.5, "supply": 0.4},
        "storm": {"air": 0.0, "infantry": 0.6, "supply": 0.3},
    }
    
    mod = strategy_mods.get(strategy, strategy_mods["наступление"])
    t_mod = terrain_mods.get(terrain, terrain_mods["plain"])
    w_mod = weather_mods.get(weather, weather_mods["clear"])
    
    # Расчёт потерь
    attack_power = (
        war["attacker_army"] * mod["attack"] * t_mod["infantry"] * w_mod["infantry"] *
        (0.6 + random.random() * 0.4)
    )
    defense_power = (
        war["defender_army"] * mod["defense"] * t_mod["defense"] * w_mod["supply"] *
        (0.5 + random.random() * 0.5)
    )
    
    # Определяем исход такта
    if attack_power > defense_power * 1.3:
        # Атакующий прорывается
        attacker_losses = int(war["attacker_army"] * random.uniform(0.05, 0.12))
        defender_losses = int(war["defender_army"] * random.uniform(0.15, 0.30))
        
        war["attacker_army"] = max(0, war["attacker_army"] - attacker_losses)
        war["defender_army"] = max(0, war["defender_army"] - defender_losses)
        war["attacker_losses"] += attacker_losses
        war["defender_losses"] += defender_losses
        
        return (
            f"⚔️ *Ход {war['turns']}: {attacker} НАСТУПАЕТ!*\n\n"
            f"💀 Потери:\n"
            f"• {attacker}: -{attacker_losses:,} (осталось {war['attacker_army']:,})\n"
            f"• {defender}: -{defender_losses:,} (осталось {war['defender_army']:,})\n\n"
            f"📊 Стратегия: {strategy} | Местность: {terrain} | Погода: {weather}"
        )
    
    elif defense_power > attack_power * 1.3:
        # Защитник отбивается
        attacker_losses = int(war["attacker_army"] * random.uniform(0.15, 0.30))
        defender_losses = int(war["defender_army"] * random.uniform(0.05, 0.12))
        
        war["attacker_army"] = max(0, war["attacker_army"] - attacker_losses)
        war["defender_army"] = max(0, war["defender_army"] - defender_losses)
        war["attacker_losses"] += attacker_losses
        war["defender_losses"] += defender_losses
        
        return (
            f"🛡️ *Ход {war['turns']}: {defender} ОБОРОНЯЕТСЯ!*\n\n"
            f"💀 Потери:\n"
            f"• {attacker}: -{attacker_losses:,} (осталось {war['attacker_army']:,})\n"
            f"• {defender}: -{defender_losses:,} (осталось {war['defender_army']:,})\n\n"
            f"📊 Стратегия: {strategy} | Местность: {terrain} | Погода: {weather}"
        )
    
    else:
        # Позиционный бой
        attacker_losses = int(war["attacker_army"] * random.uniform(0.05, 0.10))
        defender_losses = int(war["defender_army"] * random.uniform(0.05, 0.10))
        
        war["attacker_army"] = max(0, war["attacker_army"] - attacker_losses)
        war["defender_army"] = max(0, war["defender_army"] - defender_losses)
        war["attacker_losses"] += attacker_losses
        war["defender_losses"] += defender_losses
        
        return (
            f"🤝 *Ход {war['turns']}: ПОЗИЦИОННЫЙ БОЙ*\n\n"
            f"💀 Потери:\n"
            f"• {attacker}: -{attacker_losses:,} (осталось {war['attacker_army']:,})\n"
            f"• {defender}: -{defender_losses:,} (осталось {war['defender_army']:,})\n\n"
            f"📊 Стратегия: {strategy} | Местность: {terrain} | Погода: {weather}"
        )


# =====================================================================
# ЗАВЕРШЕНИЕ ВОЙНЫ
# =====================================================================

async def end_war(war_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Завершение войны и подведение итогов"""
    
    if war_id not in active_wars:
        return
    
    war = active_wars[war_id]
    war["status"] = "ended"
    
    # Определяем победителя
    if war["attacker_army"] > war["defender_army"] * 1.2:
        winner = war["attacker"]
        loser = war["defender"]
        result = "ПОБЕДА АТАКУЮЩЕГО"
    elif war["defender_army"] > war["attacker_army"] * 1.2:
        winner = war["defender"]
        loser = war["attacker"]
        result = "ПОБЕДА ЗАЩИТНИКА"
    else:
        winner = None
        loser = None
        result = "НИЧЬЯ"
    
    # Сохраняем в историю
    from history import save_world_event
    save_world_event(
        "war_ended",
        f"Война {war['attacker']} vs {war['defender']} завершена. {result}",
        f"{war['attacker']},{war['defender']}"
    )
    
    message = (
        f"🏁 *ВОЙНА ЗАВЕРШЕНА!*\n\n"
        f"⚔️ {war['attacker']} vs {war['defender']}\n"
        f"📊 Результат: *{result}*\n\n"
        f"💀 Общие потери:\n"
        f"• {war['attacker']}: {war['attacker_losses']:,}\n"
        f"• {war['defender']}: {war['defender_losses']:,}\n\n"
        f"💪 Оставшиеся силы:\n"
        f"• {war['attacker']}: {war['attacker_army']:,}\n"
        f"• {war['defender']}: {war['defender_army']:,}\n\n"
        f"🔄 Ходов: {war['turns']}"
    )
    
    chat_id = war.get("chat_id") or saved_chats.get("war")
    if chat_id and context and context.bot:
        await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
    
    # Удаляем войну через минуту
    await asyncio.sleep(60)
    if war_id in active_wars:
        del active_wars[war_id]


# =====================================================================
# СТАТУС ВОЙНЫ
# =====================================================================

async def war_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус войны"""
    user_id = update.message.from_user.id
    country = get_country(user_id) or "неизвестная страна"
    
    # Ищем войну с участием страны
    for war_id, war in active_wars.items():
        if war["attacker"] == country or war["defender"] == country:
            status_emoji = {
                "waiting_for_response": "⏳",
                "active": "⚔️",
                "ended": "🏁",
                "cancelled": "🕊️",
                "stalemate": "🤝",
            }
            emoji = status_emoji.get(war["status"], "❓")
            
            await update.message.reply_text(
                f"{emoji} *Статус войны*\n\n"
                f"⚔️ *{war['attacker']}* vs *{war['defender']}*\n"
                f"📌 Статус: {war['status']}\n"
                f"📅 Год: {war['year']}\n"
                f"🎯 Стратегия: {war.get('strategy', 'не выбрана')}\n"
                f"🌍 Местность: {war.get('terrain', 'равнина')}\n"
                f"🌤️ Погода: {war.get('weather', 'ясно')}\n"
                f"🔄 Ходов: {war['turns']}\n\n"
                f"💪 Силы:\n"
                f"• {war['attacker']}: {war['attacker_army']:,}\n"
                f"• {war['defender']}: {war['defender_army']:,}\n\n"
                f"💀 Потери:\n"
                f"• {war['attacker']}: {war['attacker_losses']:,}\n"
                f"• {war['defender']}: {war['defender_losses']:,}",
                parse_mode="Markdown"
            )
            return
    
    await update.message.reply_text("✅ Ваша страна не участвует в войнах.")


# =====================================================================
# ЗАПРОС МИРА
# =====================================================================

async def peace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запросить мир"""
    user_id = update.message.from_user.id
    country = get_country(user_id) or "неизвестная страна"
    
    for war_id, war in list(active_wars.items()):
        if war["attacker"] == country or war["defender"] == country:
            if war["status"] == "active":
                war["status"] = "ended"
                
                enemy = war["defender"] if war["attacker"] == country else war["attacker"]
                
                await update.message.reply_text(
                    f"🕊️ *{country} ЗАПРОСИЛА МИР!*\n\n"
                    f"Война с *{enemy}* завершена.",
                    parse_mode="Markdown"
                )
                
                # Удаляем
                await asyncio.sleep(10)
                if war_id in active_wars:
                    del active_wars[war_id]
                return
    
    await update.message.reply_text("❌ Ваша страна не участвует в активной войне.")
