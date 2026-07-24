import re
from telegram import Update
from telegram.ext import ContextTypes
from config import saved_chats, ADMIN_ID
from news import analyze_news
from commands import bot_stopped

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # === ЕСЛИ БОТ ОСТАНОВЛЕН ===
    if bot_stopped:
        return

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
        # Если в сообщении есть # — это новость, бот комментирует
        if "#" in text:
            comment = await analyze_news(text)
            await update.message.reply_text(comment)
        # Если кто-то упомянул бота или написал "свит" (для совместимости)
        elif context.bot.username in text or "свит" in text.lower():
            # Убираем упоминание из текста
            question = re.sub(rf"@{context.bot.username}\s*", "", text)
            question = re.sub(r"свит\s*", "", question, flags=re.IGNORECASE).strip()
            if question:
                # Отвечаем на вопрос через ИИ
                from news import ask_ai
                reply = await ask_ai(question)
                await update.message.reply_text(reply)

    # === ВОЕННЫЙ ЧАТ ===
    elif chat_type == "war":
        # Если сообщение содержит ключевые слова о войне
        if any(word in text.lower() for word in ["война", "атака", "наступление", "оборона"]):
            from war import analyze_war_message
            reply = await analyze_war_message(text)
            await update.message.reply_text(reply)

    # === ЧАТ ООН ===
    elif chat_type == "un":
        # Если сообщение содержит дипломатические ключевые слова
        if any(word in text.lower() for word in ["предлагаю", "голосование", "санкции", "резолюция"]):
            from diplomacy import analyze_diplomacy
            reply = await analyze_diplomacy(text)
            await update.message.reply_text(reply)

    # === ОБЫЧНЫЙ ЧАТ (НЕ СОХРАНЁННЫЙ) ===
    else:
        # Если бота упомянули — отвечаем
        if context.bot.username in text or "свит" in text.lower():
            question = re.sub(rf"@{context.bot.username}\s*", "", text)
            question = re.sub(r"свит\s*", "", question, flags=re.IGNORECASE).strip()
            if question:
                from news import ask_ai
                reply = await ask_ai(question)
                await update.message.reply_text(reply)
