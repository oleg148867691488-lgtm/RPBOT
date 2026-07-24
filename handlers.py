import re
from telegram import Update
from telegram.ext import ContextTypes
from config import saved_chats
from news import analyze_news, ask_ai

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    text = update.message.text
    user_id = update.message.from_user.id

    # === ОПРЕДЕЛЯЕМ ТИП ЧАТА ===
    if chat_id == saved_chats.get("news"):
        chat_type = "news"
    elif chat_id == saved_chats.get("war"):
        chat_type = "war"
    elif chat_id == saved_chats.get("un"):
        chat_type = "un"
    else:
        chat_type = "default"

    # === НОВОСТНОЙ ЧАТ ===
    if chat_type == "news":
        if "#" in text:
            comment = await analyze_news(text)
            await update.message.reply_text(comment)
        elif context.bot.username in text:
            question = re.sub(rf"@{context.bot.username}\s*", "", text).strip()
            if question:
                reply = await ask_ai(question)
                await update.message.reply_text(reply)

    # === ВОЕННЫЙ ЧАТ ===
    elif chat_type == "war":
        if any(word in text.lower() for word in ["война", "атака", "наступление", "оборона"]):
            from war import analyze_war_message
            reply = await analyze_war_message(text)
            await update.message.reply_text(reply)
        elif context.bot.username in text:
            question = re.sub(rf"@{context.bot.username}\s*", "", text).strip()
            if question:
                reply = await ask_ai(question)
                await update.message.reply_text(reply)

    # === ЧАТ ООН ===
    elif chat_type == "un":
        if any(word in text.lower() for word in ["предлагаю", "голосование", "санкции", "резолюция"]):
            from diplomacy import analyze_diplomacy
            reply = await analyze_diplomacy(text)
            await update.message.reply_text(reply)
        elif context.bot.username in text:
            question = re.sub(rf"@{context.bot.username}\s*", "", text).strip()
            if question:
                reply = await ask_ai(question)
                await update.message.reply_text(reply)

    # === ОБЫЧНЫЙ ЧАТ ===
    else:
        if context.bot.username in text:
            question = re.sub(rf"@{context.bot.username}\s*", "", text).strip()
            if question:
                reply = await ask_ai(question)
                await update.message.reply_text(reply)
