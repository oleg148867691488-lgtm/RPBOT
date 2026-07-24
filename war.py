import random
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID
from history import get_country, get_year

# === ХРАНИЛИЩЕ АКТИВНЫХ ВОЙН ===
active_wars = {}

# === ОБЪЯВЛЕНИЕ ВОЙНЫ ===
async def declare_war_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Используйте: /war [страна-противник] [причина]")
        return

    defender = args[0]
    reason = " ".join(args[1:])
    
    attacker = get_country(user_id) or "неизвестная страна"
    year = get_year(user_id) or 2022

    # Проверяем, не идёт ли уже война
    for war in active_wars.values():
        if war["attacker"] == attacker or war["defender"] == attacker:
            await update.message.reply_text("❌ Вы уже участвуете в войне.")
            return
        if war["defender"] == defender or war["attacker"] == defender:
            await update.message.reply_text(f"❌ {defender} уже воюет с {war['attacker']}.")
            return

    # Создаём войну
    war_id = f"{attacker}_{defender}_{year}"
    active_wars[war_id] = {
        "attacker": attacker,
        "defender": defender,
        "reason": reason,
        "year": year,
        "status": "waiting_for_response",
        "turns": 0,
        "attacker_losses": 0,
        "defender_losses": 0,
        "attacker_army": random.randint(50, 100) * 1000,
        "defender_army": random.randint(30, 80) * 1000,
        "responded": False,
        "strategy": None,
        "chat_id": update.message.chat.id
    }

    await update.message.reply_text(
        f"⚔️ *{attacker} объявляет войну {defender}!*\n\n"
        f"📌 Причина: {reason}\n"
        f"📅 Год: {year}\n"
        f"⏳ У {defender} есть 30 минут, чтобы ответить.\n"
        f"📝 Напишите /respond [согласиться/отказаться]"
    )

    # Запускаем таймер ответа (30 минут)
    asyncio.create_task(war_response_timer(war_id, context))

# === ТАЙМЕР ОТВЕТА (30 МИНУТ) ===
async def war_response_timer(war_id: str, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(30 * 60)  # 30 минут
    
    if war_id not in active_wars:
        return
    
    war = active_wars[war_id]
    
    if not war["responded"]:
        if war["defender_army"] > war["attacker_army"] * 1.5:
            strategy = "оборона"
        else:
            strategy = "наступление"
        
        war["strategy"] = strategy
        war["status"] = "active"
        
        await context.bot.send_message(
            chat_id=war["chat_id"],
            text=(
                f"⏳ *{war['defender']} не ответил!*\n\n"
                f"🤖 Бот выбрал стратегию: *{strategy}*\n"
                f"⚔️ Война начинается!"
            )
        )
        
        asyncio.create_task(war_loop(war_id, context))

# === ОТВЕТ НА ВОЙНУ ===
async def respond_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("❌ Используйте: /respond [согласиться/отказаться]")
        return
    
    action = args[0].lower()
    country = get_country(user_id) or "неизвестная страна"
    
    for war_id, war in active_wars.items():
        if war["defender"] == country and war["status"] == "waiting_for_response":
            war["responded"] = True
            
            if action == "согласиться":
                war["status"] = "active"
                war["strategy"] = "оборона"
                await update.message.reply_text(
                    f"⚔️ *{country} принимает вызов!*\n\n"
                    f"Война начинается!\n"
                    f"Стратегия по умолчанию: оборона.\n"
                    f"Изменить: /strategy [наступление/оборона/партизаны]"
                )
                asyncio.create_task(war_loop(war_id, context))
                return
            
            elif action == "отказаться":
                del active_wars[war_id]
                await update.message.reply_text(
                    f"🕊️ *{country} отказалась от войны.*\n\n"
                    f"Конфликт предотвращён."
                )
                return
    
    await update.message.reply_text("❌ Нет активных запросов на войну для вашей страны.")

# === СМЕНА СТРАТЕГИИ ===
async def strategy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("❌ Используйте: /strategy [наступление/оборона/партизаны]")
        return
    
    strategy = args[0].lower()
    if strategy not in ["наступление", "оборона", "партизаны"]:
        await update.message.reply_text("❌ Доступные стратегии: наступление, оборона, партизаны")
        return
    
    country = get_country(user_id) or "неизвестная страна"
    
    for war in active_wars.values():
        if war["attacker"] == country or war["defender"] == country:
            if war["status"] != "active":
                await update.message.reply_text("❌ Война ещё не началась.")
                return
            war["strategy"] = strategy
            await update.message.reply_text(f"✅ Стратегия изменена на: *{strategy}*")
            return
    
    await update.message.reply_text("❌ Ваша страна не участвует в войне.")

# === ЦИКЛ ВОЙНЫ ===
async def war_loop(war_id: str, context: ContextTypes.DEFAULT_TYPE):
    while war_id in active_wars:
        war = active_wars[war_id]
        if war["status"] != "active":
            break
        
        result = await make_war_turn(war)
        await context.bot.send_message(chat_id=war["chat_id"], text=result)
        
        if war["attacker_army"] < 10000 or war["defender_army"] < 10000:
            await end_war(war_id, context)
            break
        
        await asyncio.sleep(4 * 60)

# === ХОД ВОЙНЫ ===
async def make_war_turn(war: dict) -> str:
    attacker = war["attacker"]
    defender = war["defender"]
    strategy = war.get("strategy", "наступление")
    
    modifiers = {
        "наступление": {"attack": 1.2, "defense": 0.8},
        "оборона": {"attack": 0.7, "defense": 1.3},
        "партизаны": {"attack": 0.9, "defense": 1.1}
    }
    mod = modifiers.get(strategy, {"attack": 1.0, "defense": 1.0})
    
    attack_power = war["attacker_army"] * mod["attack"] * (0.6 + random.random() * 0.2)
    defense_power = war["defender_army"] * mod["defense"] * (0.5 + random.random() * 0.3)
    
    if attack_power > defense_power * 1.2:
        loss_ratio = 0.1 + random.random() * 0.15
        attacker_losses = int(war["attacker_army"] * loss_ratio)
        defender_losses = int(war["defender_army"] * (0.2 + random.random() * 0.2))
        
        war["attacker_army"] -= attacker_losses
        war["defender_army"] -= defender_losses
        war["attacker_losses"] += attacker_losses
        war["defender_losses"] += defender_losses
        
        return (
            f"⚔️ *{attacker} наступает!*\n"
            f"📊 Потери: {attacker} — {attacker_losses:,}, {defender} — {defender_losses:,}\n"
            f"💪 Осталось: {attacker} — {war['attacker_army']:,}, {defender} — {war['defender_army']:,}"
        )
    elif defense_power > attack_power * 1.2:
        loss_ratio = 0.1 + random.random() * 0.15
        attacker_losses = int(war["attacker_army"] * (0.2 + random.random() * 0.2))
        defender_losses = int(war["defender_army"] * loss_ratio)
        
        war["attacker_army"] -= attacker_losses
        war["defender_army"] -= defender_losses
        war["attacker_losses"] += attacker_losses
        war["defender_losses"] += defender_losses
        
        return (
            f"🛡️ *{defender} отражает атаку!*\n"
            f"📊 Потери: {attacker} — {attacker_losses:,}, {defender} — {defender_losses:,}\n"
            f"💪 Осталось: {attacker} — {war['attacker_army']:,}, {defender} — {war['defender_army']:,}"
        )
    else:
        loss_ratio = 0.05 + random.random() * 0.1
        attacker_losses = int(war["attacker_army"] * loss_ratio)
        defender_losses = int(war["defender_army"] * loss_ratio)
        
        war["attacker_army"] -= attacker_losses
        war["defender_army"] -= defender_losses
        war["attacker_losses"] += attacker_losses
        war["defender_losses"] += defender_losses
        
        return (
            f"🤝 *Позиционная война!*\n"
            f"📊 Потери: {attacker} — {attacker_losses:,}, {defender} — {defender_losses:,}\n"
            f"💪 Осталось: {attacker} — {war['attacker_army']:,}, {defender} — {war['defender_army']:,}"
        )

# === ЗАВЕРШЕНИЕ ВОЙНЫ ===
async def end_war(war_id: str, context: ContextTypes.DEFAULT_TYPE):
    if war_id not in active_wars:
        return
    
    war = active_wars[war_id]
    war["status"] = "ended"
    
    if war["attacker_army"] > war["defender_army"]:
        winner = war["attacker"]
        loser = war["defender"]
    else:
        winner = war["defender"]
        loser = war["attacker"]
    
    await context.bot.send_message(
        chat_id=war["chat_id"],
        text=(
            f"🏁 *Война завершена!*\n\n"
            f"👑 Победитель: {winner}\n"
            f"💀 Потери: {war['attacker']} — {war['attacker_losses']:,}, {war['defender']} — {war['defender_losses']:,}\n"
            f"⚔️ Итог: {loser} признаёт поражение."
        )
    )
    
    del active_wars[war_id]

# === СТАТУС ВОЙНЫ ===
async def war_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    country = get_country(user_id) or "неизвестная страна"
    
    for war in active_wars.values():
        if war["attacker"] == country or war["defender"] == country:
            await update.message.reply_text(
                f"⚔️ *Статус войны:*\n\n"
                f"📌 {war['attacker']} vs {war['defender']}\n"
                f"🔄 Статус: {war['status']}\n"
                f"💀 Потери: {war['attacker']} — {war['attacker_losses']:,}, {war['defender']} — {war['defender_losses']:,}\n"
                f"💪 Осталось: {war['attacker']} — {war['attacker_army']:,}, {war['defender']} — {war['defender_army']:,}"
            )
            return
    
    await update.message.reply_text("✅ Ваша страна не участвует в войнах.")

# === ЗАПРОС МИРА ===
async def peace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    country = get_country(user_id) or "неизвестная страна"
    
    for war_id, war in active_wars.items():
        if war["attacker"] == country or war["defender"] == country:
            war["status"] = "ended"
            await update.message.reply_text(
                f"🕊️ *{country} запросила мир!*\n\n"
                f"Война с {war['attacker'] if war['defender'] == country else war['defender']} завершена."
            )
            del active_wars[war_id]
            return
    
    await update.message.reply_text("❌ Ваша страна не участвует в войнах.")
