import random
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID
from history import get_economy, init_economy, update_economy

# === ЦЕНЫ НА РЕСУРСЫ ===
PRICES = {
    "steel": 700,   # $ за тонну
    "oil": 80,      # $ за тонну
    "grain": 220,   # $ за тонну
    "gold": 2000    # $ за унцию
}

# === ПОЛУЧЕНИЕ ЭКОНОМИКИ ПОЛЬЗОВАТЕЛЯ ===
def get_user_economy(user_id: int):
    economy = get_economy(user_id)
    if not economy:
        init_economy(user_id)
        economy = get_economy(user_id)
    return economy

# === ПОКАЗАТЬ БАЛАНС ===
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    economy = get_user_economy(user_id)
    
    text = (
        f"💰 *Бюджет:* ${economy['budget']:,}\n"
        f"🔩 *Сталь:* {economy['steel']} т.\n"
        f"🛢️ *Нефть:* {economy['oil']} т.\n"
        f"🌾 *Зерно:* {economy['grain']} т.\n"
        f"🥇 *Золото:* {economy['gold']} унций"
    )
    await update.message.reply_text(text)

# === ТОРГОВЛЯ ===
async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    
    if len(args) < 3:
        await update.message.reply_text(
            "❌ Используйте: /trade [купить/продать] [ресурс] [количество]\n"
            "Пример: /trade купить steel 100"
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
        await update.message.reply_text(f"❌ Ресурс '{resource}' не найден. Доступны: {', '.join(PRICES.keys())}")
        return
    
    economy = get_user_economy(user_id)
    price = PRICES[resource]
    total_cost = price * amount
    
    if action == "купить":
        if economy['budget'] < total_cost:
            await update.message.reply_text(f"❌ Недостаточно денег. Нужно ${total_cost:,}, у вас ${economy['budget']:,}")
            return
        
        # Проводим сделку
        update_economy(user_id, budget=economy['budget'] - total_cost, **{resource: economy[resource] + amount})
        await update.message.reply_text(
            f"✅ Куплено {amount} т. {resource} за ${total_cost:,}.\n"
            f"💰 Остаток: ${economy['budget'] - total_cost:,}"
        )
    
    elif action == "продать":
        if economy[resource] < amount:
            await update.message.reply_text(f"❌ У вас только {economy[resource]} т. {resource}")
            return
        
        update_economy(user_id, budget=economy['budget'] + total_cost, **{resource: economy[resource] - amount})
        await update.message.reply_text(
            f"✅ Продано {amount} т. {resource} за ${total_cost:,}.\n"
            f"💰 Теперь у вас: ${economy['budget'] + total_cost:,}"
        )
    
    else:
        await update.message.reply_text("❌ Используйте 'купить' или 'продать'.")

# === ТОРГОВЛЯ МЕЖДУ ИГРОКАМИ ===
async def trade_with_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    
    if len(args) < 4:
        await update.message.reply_text(
            "❌ Используйте: /tradeplayer @ник [ресурс] [количество] [цена]\n"
            "Пример: /tradeplayer @Player steel 100 700"
        )
        return
    
    target_username = args[0]
    resource = args[1].lower()
    try:
        amount = int(args[2])
        price = int(args[3])
    except ValueError:
        await update.message.reply_text("❌ Количество и цена должны быть числами.")
        return
    
    # Проверяем, есть ли такой пользователь в чате
    try:
        target_user = await context.bot.get_chat_member(update.message.chat.id, target_username)
        target_id = target_user.user.id
    except:
        await update.message.reply_text(f"❌ Пользователь {target_username} не найден в чате.")
        return
    
    # Проверяем ресурсы у покупателя
    economy = get_user_economy(user_id)
    if economy[resource] < amount:
        await update.message.reply_text(f"❌ У вас только {economy[resource]} т. {resource}")
        return
    
    # Проверяем бюджет у продавца
    target_economy = get_user_economy(target_id)
    total_cost = price * amount
    if target_economy['budget'] < total_cost:
        await update.message.reply_text(f"❌ У {target_username} недостаточно денег.")
        return
    
    # Проводим сделку
    update_economy(user_id, budget=economy['budget'] + total_cost, **{resource: economy[resource] - amount})
    update_economy(target_id, budget=target_economy['budget'] - total_cost, **{resource: target_economy[resource] + amount})
    
    await update.message.reply_text(
        f"✅ Сделка завершена!\n"
        f"@{update.message.from_user.username} продал {amount} т. {resource} за ${total_cost:,} пользователю {target_username}."
    )

# === СТАТИСТИКА ЭКОНОМИКИ (ТОЛЬКО ДЛЯ АДМИНА) ===
async def economy_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    from history import get_economy
    economy = get_user_economy(user_id)
    text = (
        f"📊 *Экономика Швейцарии:*\n\n"
        f"💰 Бюджет: ${economy['budget']:,}\n"
        f"🔩 Сталь: {economy['steel']} т.\n"
        f"🛢️ Нефть: {economy['oil']} т.\n"
        f"🌾 Зерно: {economy['grain']} т.\n"
        f"🥇 Золото: {economy['gold']} унций"
    )
    await update.message.reply_text(text)

# === ДОБАВЛЕНИЕ ДЕНЕГ (ДЛЯ ТЕСТОВ, ТОЛЬКО АДМИН) ===
async def add_money_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text(f"✅ Добавлено ${amount:,}. Теперь бюджет: ${economy['budget'] + amount:,}")
