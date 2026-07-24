import random
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID
from history import get_country, get_year

# === ХРАНИЛИЩА ===
un_sessions = {}  # Активные сессии ООН
alliances = {}    # Союзы между странами
sanctions = {}    # Активные санкции

# === ПРЕДЛОЖИТЬ РЕЗОЛЮЦИЮ В ООН ===
async def un_propose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Используйте: /un_propose [текст резолюции]")
        return

    text = " ".join(args)
    country = get_country(user_id) or "Швейцария"
    year = get_year(user_id) or 2022

    session_id = f"un_{user_id}_{year}_{len(un_sessions)}"
    un_sessions[session_id] = {
        "proposer": country,
        "text": text,
        "year": year,
        "votes_for": 0,
        "votes_against": 0,
        "status": "voting",
        "voters": []
    }

    await update.message.reply_text(
        f"🏛️ *{country} предлагает резолюцию в ООН:*\n\n"
        f"📄 {text}\n\n"
        f"📅 Год: {year}\n"
        f"🗳️ Голосование началось!\n"
        f"📝 Напишите /vote [за/против] чтобы проголосовать."
    )

# === ГОЛОСОВАНИЕ В ООН ===
async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args

    if not args:
        await update.message.reply_text("❌ Используйте: /vote [за/против]")
        return

    vote = args[0].lower()
    if vote not in ["за", "против"]:
        await update.message.reply_text("❌ Используйте 'за' или 'против'.")
        return

    # Ищем активную сессию ООН
    for session_id, session in un_sessions.items():
        if session["status"] == "voting":
            if user_id in session["voters"]:
                await update.message.reply_text("❌ Вы уже проголосовали.")
                return

            if vote == "за":
                session["votes_for"] += 1
            else:
                session["votes_against"] += 1
            session["voters"].append(user_id)

            await update.message.reply_text(
                f"✅ Голос принят: *{vote}*.\n"
                f"📊 Текущий счёт: ЗА — {session['votes_for']}, ПРОТИВ — {session['votes_against']}"
            )
            return

    await update.message.reply_text("❌ Нет активных голосований в ООН.")

# === ЗАВЕРШЕНИЕ ГОЛОСОВАНИЯ (АВТОМАТИЧЕСКИ) ===
async def un_voting_timer(session_id: str):
    await asyncio.sleep(60 * 5)  # 5 минут на голосование

    if session_id not in un_sessions:
        return

    session = un_sessions[session_id]
    session["status"] = "ended"

    if session["votes_for"] > session["votes_against"]:
        result = "✅ Резолюция ПРИНЯТА!"
    else:
        result = "❌ Резолюция ОТКЛОНЕНА!"

    # Отправляем результат в чат
    from commands import saved_chats
    chat_id = saved_chats.get("un")
    if chat_id:
        await app.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🏛️ *Итоги голосования в ООН:*\n\n"
                f"📄 {session['text']}\n"
                f"📊 ЗА: {session['votes_for']}, ПРОТИВ: {session['votes_against']}\n"
                f"📌 {result}"
            )
        )

    del un_sessions[session_id]

# === ПРЕДЛОЖИТЬ СОЮЗ ===
async def ally_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Используйте: /ally [страна] [тип союза]")
        return

    target = args[0]
    alliance_type = args[1] if len(args) > 1 else "торговый"

    country = get_country(user_id) or "Швейцария"
    
    alliance_id = f"{country}_{target}_{len(alliances)}"
    alliances[alliance_id] = {
        "country1": country,
        "country2": target,
        "type": alliance_type,
        "active": True
    }

    await update.message.reply_text(
        f"🤝 *{country} предлагает {alliance_type} союз с {target}!*\n\n"
        f"📝 Если {target} согласится, союз будет заключён."
    )

# === ПРИНЯТЬ СОЮЗ ===
async def accept_ally_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    country = get_country(user_id) or "Швейцария"

    for alliance_id, alliance in alliances.items():
        if alliance["country2"] == country and alliance["active"]:
            alliance["active"] = True
            await update.message.reply_text(
                f"✅ *{country} принял союз с {alliance['country1']}!*\n\n"
                f"📌 Тип: {alliance['type']}\n"
                f"🤝 Союз заключён!"
            )
            return

    await update.message.reply_text("❌ Нет активных предложений о союзе.")

# === ВВЕСТИ САНКЦИИ ===
async def sanctions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Используйте: /sanctions [страна] [причина]")
        return

    target = args[0]
    reason = " ".join(args[1:])
    country = get_country(user_id) or "Швейцария"

    sanctions[target] = {
        "imposed_by": country,
        "reason": reason,
        "active": True
    }

    await update.message.reply_text(
        f"🚫 *{country} вводит санкции против {target}!*\n\n"
        f"📌 Причина: {reason}\n"
        f"⚠️ Теперь {target} не может торговать с {country}."
    )

# === СНЯТЬ САНКЦИИ ===
async def remove_sanctions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ Используйте: /remove_sanctions [страна]")
        return

    target = args[0]
    if target in sanctions:
        del sanctions[target]
        await update.message.reply_text(f"✅ Санкции против {target} сняты.")
    else:
        await update.message.reply_text(f"❌ Санкции против {target} не найдены.")

# === СТАТУС ДИПЛОМАТИИ ===
async def diplomacy_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🌍 *Дипломатическая обстановка:*\n\n"

    if alliances:
        text += "🤝 *Активные союзы:*\n"
        for alliance in alliances.values():
            if alliance["active"]:
                text += f"• {alliance['country1']} — {alliance['country2']} ({alliance['type']})\n"
    else:
        text += "🤝 Активных союзов нет.\n"

    if sanctions:
        text += "\n🚫 *Активные санкции:*\n"
        for target, info in sanctions.items():
            if info["active"]:
                text += f"• {target} (ввёл: {info['imposed_by']}, причина: {info['reason']})\n"
    else:
        text += "\n🚫 Активных санкций нет.\n"

    if un_sessions:
        text += "\n🏛️ *Активные сессии ООН:*\n"
        for session in un_sessions.values():
            if session["status"] == "voting":
                text += f"• {session['proposer']}: {session['text'][:50]}... (ЗА: {session['votes_for']}, ПРОТИВ: {session['votes_against']})\n"
    else:
        text += "\n🏛️ Активных сессий ООН нет."

    await update.message.reply_text(text)
