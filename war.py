import random
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID
from history import get_country, get_year, save_dialog, get_dialog_history

# === ХРАНИЛИЩЕ АКТИВНЫХ ВОЙН ===
active_wars = {}

# === СТРУКТУРА ВОЙНЫ ===
# {
#   "war_id": {
#       "attacker": "Германия",
#       "defender": "Россия",
#       "start_date": "2026-07-24",
#       "status": "preparing",  # preparing, active, ended
#       "turns": 0,
#       "attacker_losses": 0,
#       "defender_losses": 0
#   }
# }

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
    
    attacker = get_country(user_id) or "Швейцария"
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
        "status": "preparing",
        "turns": 0,
        "attacker_losses": 0,
        "defender_losses": 0,
        "attacker_army": random.randint(50, 100) * 1000,
        "defender_army": random.randint(30, 80) * 1000
    }

    await update.message.reply_text(
        f"⚔️ *{attacker} объявляет войну {defender}!*\n\n"
        f"📌 Причина: {reason}\n"
        f"📅 Год: {year}\n"
        f"🔄 Статус: Подготовка (4 месяца)\n"
        f"⏳ Война начнётся через 8 часов."
    )

    # Запускаем таймер подготовки
    asyncio.create_task(war_preparation(war_id, update, context))

# === ПОДГОТОВКА К ВОЙНЕ (4 МЕСЯЦА = 8 ЧАСОВ) ===
async def war_preparation(war_id: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(8 * 60 * 60)  # 8 часов
    
    if war_id not in active_wars:
        return
    
    war = active_wars[war_id]
    war["status"] = "active"
    
    await update.message.reply_text(
        f"⚔️ *Война началась!*\n\n"
        f"{war['attacker']} атакует {war['defender']}.\n"
        f"📊 Силы: {war['attacker']} — {war['attacker_army']:,} солдат, {war['defender']} — {war['defender_army']:,} солдат."
    )
    
    # Запускаем цикл войны
    asyncio.create_task(war_loop(war_id, update, context))

# === ЦИКЛ ВОЙНЫ (ХОДЫ) ===
async def war_loop(war_id: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    while war_id in active_wars:
        war = active_wars[war_id]
        if war["status"] != "active":
            break
        
        # Делаем ход
        result = await make_war_turn(war)
        await update.message.reply_text(result)
        
        # Проверяем, не закончилась ли война
        if war["attacker_army"] < 10000 or war["defender_army"] < 10000:
            await end_war(war_id, update, context)
            break
        
        # Ждём 1 игровой день (4 минуты реального времени)
        await asyncio.sleep(4 * 60)

# === ХОД ВОЙНЫ ===
async def make_war_turn(war: dict) -> str:
    attacker = war["attacker"]
    defender = war["defender"]
    
    # Расчёт силы
    attack_power = war["attacker_army"] * (0.6 + random.random() * 0.2)
    defense_power = war["defender_army"] * (0.5 + random.random() * 0.3)
    
    # Определяем результат
    if attack_power > defense_power * 1.2:
        # Атакующий побеждает
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
        # Защитник побеждает
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
        # Ничья
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
async def end_war(war_id: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if war_id not in active_wars:
        return
    
    war = active_wars[war_id]
    war["status"] = "ended"
    
    # Определяем победителя
    if war["attacker_army"] > war["defender_army"]:
        winner = war["attacker"]
        loser = war["defender"]
    else:
        winner = war["defender"]
        loser = war["attacker"]
    
    await update.message.reply_text(
        f"🏁 *Война завершена!*\n\n"
        f"👑 Победитель: {winner}\n"
        f"💀 Потери: {war['attacker']} — {war['attacker_losses']:,}, {war['defender']} — {war['defender_losses']:,}\n"
        f"⚔️ Итог: {loser} признаёт поражение."
    )
    
    # Удаляем войну из активных
    del active_wars[war_id]

# === СТАТУС ВОЙНЫ ===
async def war_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    country = get_country(user_id) or "Швейцария"
    
    # Ищем войну, в которой участвует страна
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
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    country = get_country(user_id) or "Швейцария"
    
    # Ищем войну, где страна является участником
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
