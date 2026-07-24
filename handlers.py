"""
HANDLERS.PY — УМНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
===========================================
ИИ определяет ID стран, понимает синонимы,
анализирует новости, войну и дипломатию.
Бот комментирует чужие новости от своей страны.
"""

import re
import json
import asyncio
import hashlib
from telegram import Update
from telegram.ext import ContextTypes
from config import saved_chats, bot_stopped, ADMIN_ID
from ai_manager import ai
from history import (
    get_country,
    get_year,
    save_dialog,
    get_dialog_history
)

# =====================================================================
# СИСТЕМА УМНЫХ ID (ЧЕРЕЗ ИИ)
# =====================================================================

country_registry = {}
players = {}
synonym_cache = {}
used_ids = set()

SERVICE_TAGS = [
    "новости", "война", "оон", "симуляция", "rp", "все",
    "мир", "экономика", "политика", "спорт", "технологии",
    "наука", "культура", "история", "армия", "флот"
]

async def get_country_id_ai(country_name: str) -> dict:
    name_lower = country_name.lower().strip()
    if name_lower in synonym_cache:
        cached_id = synonym_cache[name_lower]
        if cached_id in country_registry:
            return {"id": cached_id, "name": country_registry[cached_id], "new": False}
    
    if len(country_registry) < 2:
        return get_country_id_hash(country_name)
    
    try:
        prompt = f"""Ты — система учёта стран в RP-игре.
ТЕКУЩАЯ БАЗА: {json.dumps(country_registry, ensure_ascii=False)}
ЗАНЯТЫЕ ID: {sorted(used_ids)}
ПРИШЛА СТРАНА: "{country_name}"

Если страна есть в базе (включая синонимы: ФРГ=Германия, РФ=Россия) — верни её ID.
Если нет — создай новый ID (3 цифры).
Ответь ТОЛЬКО JSON: {{"id": "001", "name": "Россия", "new": false}} или null если это не страна."""

        response = await ai.ask_groq(prompt, temperature=0.1, max_tokens=100)
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()
        
        if response == "null" or response is None:
            return None
        
        result = json.loads(response)
        
        if result.get("new"):
            country_registry[result["id"]] = result["name"]
            used_ids.add(result["id"])
        
        synonym_cache[name_lower] = result["id"]
        return result
    except:
        return get_country_id_hash(country_name)


def get_country_id_hash(country_name: str) -> dict:
    name = country_name.lower().strip()
    if name in synonym_cache:
        cached_id = synonym_cache[name]
        if cached_id in country_registry:
            return {"id": cached_id, "name": country_registry[cached_id], "new": False}
    
    hash_hex = hashlib.md5(name.encode()).hexdigest()
    country_id = hash_hex[:3].upper()
    
    while country_id in used_ids:
        hash_hex = hashlib.md5((name + str(len(used_ids))).encode()).hexdigest()
        country_id = hash_hex[:3].upper()
    
    country_registry[country_id] = country_name
    used_ids.add(country_id)
    synonym_cache[name] = country_id
    
    return {"id": country_id, "name": country_name, "new": True}


def get_country_by_id(country_id: str) -> str:
    return country_registry.get(country_id.upper(), f"Неизвестная страна ({country_id})")


async def register_player(user_id: int, username: str, country_name: str) -> dict:
    result = await get_country_id_ai(country_name)
    if result is None:
        return None
    
    players[user_id] = {
        "username": username,
        "country": result["name"],
        "country_id": result["id"],
        "aliases": [country_name],
        "registered_at": asyncio.get_event_loop().time()
    }
    
    synonym_cache[country_name.lower().strip()] = result["id"]
    synonym_cache[result["name"].lower().strip()] = result["id"]
    
    return {"user_id": user_id, "username": username, "country": result["name"], 
            "country_id": result["id"], "new": result.get("new", True)}


def extract_country_hashtags(text: str) -> list:
    hashtags = []
    matches = re.findall(r'#([\wА-Яа-яёЁ\-]+(?:\s+[\wА-Яа-яёЁ\-]+)*)', text)
    
    for match in matches:
        match = match.strip()
        if not match or match.lower() in SERVICE_TAGS:
            continue
        if re.match(r'^[A-Z0-9]{3}$', match.upper()):
            hashtags.append(get_country_by_id(match.upper()))
        else:
            hashtags.append(match)
    
    return hashtags


# =====================================================================
# ГЛАВНЫЙ ОБРАБОТЧИК
# =====================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if bot_stopped:
        return
    
    chat_id = update.message.chat.id
    text = update.message.text or ""
    user_id = update.message.from_user.id
    username = update.message.from_user.username or update.message.from_user.first_name or "игрок"
    
    if not text.strip():
        return
    
    try:
        save_dialog(chat_id, user_id, "user", text)
    except:
        pass
    
    # Тип чата
    if chat_id == saved_chats.get("news"):
        chat_type = "news"
    elif chat_id == saved_chats.get("war"):
        chat_type = "war"
    elif chat_id == saved_chats.get("un"):
        chat_type = "un"
    else:
        chat_type = "default"
    
    # Хэштеги
    hashtags = extract_country_hashtags(text)
    
    if hashtags:
        country_name = hashtags[0]
        
        if user_id in players:
            old_country = players[user_id]["country"]
            if old_country.lower() != country_name.lower():
                result = await register_player(user_id, username, country_name)
                if result:
                    if result["new"]:
                        await update.message.reply_text(
                            f"🔄 {username} сменил страну: {old_country} → {result['country']}\n"
                            f"🆔 Новый ID: {result['country_id']}"
                        )
                    else:
                        await update.message.reply_text(
                            f"🔄 {username} сменил страну: {old_country} → {result['country']}\n"
                            f"🆔 ID: {result['country_id']}"
                        )
        else:
            result = await register_player(user_id, username, country_name)
            if result:
                if result["new"]:
                    await update.message.reply_text(
                        f"✅ {username} зарегистрирован как {result['country']}\n"
                        f"🆔 ID: {result['country_id']}"
                    )
                else:
                    await update.message.reply_text(
                        f"✅ {username} зарегистрирован как {result['country']}\n"
                        f"🆔 ID: {result['country_id']}"
                    )
    
    # Обработка по типу чата
    if chat_type == "news":
        await handle_news_chat(update, context, text, user_id, username, hashtags)
    elif chat_type == "war":
        await handle_war_chat(update, context, text, user_id, username)
    elif chat_type == "un":
        await handle_un_chat(update, context, text, user_id, username)
    else:
        await handle_default_chat(update, context, text, user_id, username)


# =====================================================================
# НОВОСТНОЙ ЧАТ
# =====================================================================

async def handle_news_chat(update: Update, context, text: str, user_id: int, username: str, hashtags: list):
    # Сообщение с хэштегом = новость от игрока
    if hashtags:
        country_name = hashtags[0]
        result = await get_country_id_ai(country_name)
        if result is None:
            return
        
        country_id = result["id"]
        normalized_name = result["name"]
        
        clean_text = text
        for tag in hashtags:
            clean_text = clean_text.replace(f"#{tag}", "").strip()
        
        if not clean_text:
            clean_text = text
        
        status_msg = await update.message.reply_text(f"📰 {normalized_name} (ID: {country_id}) анализируется...")
        
        try:
            # Бот комментирует от своей страны
            analysis = await analyze_news_ai(clean_text, normalized_name)
            
            await status_msg.delete()
            
            response = f"📰 Новость от {normalized_name} (ID: {country_id})\n\n{analysis}"
            await reply_long(update, response)
            
            save_dialog(update.message.chat.id, user_id, "assistant", analysis)
        except Exception as e:
            await status_msg.delete()
            await update.message.reply_text(f"❌ Ошибка анализа: {str(e)[:100]}")
    
    # Упоминание бота = вопрос
    elif f"@{context.bot.username}" in text:
        question = text.replace(f"@{context.bot.username}", "").strip()
        if question:
            await process_question(update, context, question, user_id)


# =====================================================================
# ВОЕННЫЙ ЧАТ
# =====================================================================

async def handle_war_chat(update: Update, context, text: str, user_id: int, username: str):
    war_keywords = ["война", "атака", "наступление", "оборона", "штурм", "блокада", 
                    "фронт", "армия", "дивизия", "сражение", "битва", "десант", "прорыв"]
    
    if any(word in text.lower() for word in war_keywords):
        status_msg = await update.message.reply_text("⚔️ Анализирую военную обстановку...")
        
        try:
            analysis = await analyze_war_ai(text)
            await status_msg.delete()
            await reply_long(update, f"⚔️ Военный анализ:\n\n{analysis}")
            save_dialog(update.message.chat.id, user_id, "assistant", analysis)
        except Exception as e:
            await status_msg.delete()
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")
    
    elif f"@{context.bot.username}" in text:
        question = text.replace(f"@{context.bot.username}", "").strip()
        if question:
            await process_question(update, context, question, user_id)


# =====================================================================
# ЧАТ ООН
# =====================================================================

async def handle_un_chat(update: Update, context, text: str, user_id: int, username: str):
    diplomacy_keywords = ["предлагаю", "голосование", "санкции", "резолюция", "союз",
                          "договор", "пакт", "соглашение", "мир", "переговоры", 
                          "ультиматум", "нота", "протест", "осуждаю", "поддерживаю"]
    
    if any(word in text.lower() for word in diplomacy_keywords):
        status_msg = await update.message.reply_text("🏛️ Анализирую дипломатическую ситуацию...")
        
        try:
            analysis = await analyze_diplomacy_ai(text)
            await status_msg.delete()
            await reply_long(update, f"🏛️ Дипломатический анализ:\n\n{analysis}")
            save_dialog(update.message.chat.id, user_id, "assistant", analysis)
        except Exception as e:
            await status_msg.delete()
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")
    
    elif f"@{context.bot.username}" in text:
        question = text.replace(f"@{context.bot.username}", "").strip()
        if question:
            await process_question(update, context, question, user_id)


# =====================================================================
# ОБЫЧНЫЙ ЧАТ
# =====================================================================

async def handle_default_chat(update: Update, context, text: str, user_id: int, username: str):
    if f"@{context.bot.username}" in text:
        question = text.replace(f"@{context.bot.username}", "").strip()
        if question:
            await process_question(update, context, question, user_id)


# =====================================================================
# ОБРАБОТКА ВОПРОСОВ
# =====================================================================

async def process_question(update: Update, context, question: str, user_id: int):
    status_msg = await update.message.reply_text("🤔 Думаю...")
    
    try:
        answer = await ask_ai(question)
        await status_msg.delete()
        await reply_long(update, answer)
        save_dialog(update.message.chat.id, user_id, "assistant", answer)
    except Exception as e:
        await status_msg.delete()
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


# =====================================================================
# ВСПОМОГАТЕЛЬНАЯ — ОТПРАВКА ДЛИННЫХ
# =====================================================================

async def reply_long(update: Update, text: str):
    """Отправляет длинное сообщение с авто-разбивкой."""
    if len(text) > 4000:
        from utils import split_text
        parts = split_text(text, 3800)
        for part in parts:
            await update.message.reply_text(part)
            await asyncio.sleep(0.5)
    else:
        await update.message.reply_text(text)


# =====================================================================
# AI АНАЛИЗ
# =====================================================================

async def analyze_news_ai(text: str, country_name: str = None) -> str:
    """Бот комментирует новость от имени своей страны."""
    bot_country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    context = f"Новость от страны {country_name}. " if country_name else ""
    
    prompt = f"""Ты — правительство страны {bot_country}. Год {year}.
{context}
Прокомментируй эту новость от лица твоей страны.
Оцени угрозы и возможности для {bot_country}.
Ответь 3-5 предложениями на русском. Говори "МЫ", "НАША СТРАНА".

Новость: {text}"""
    
    return await ai.ask_groq(prompt, system_prompt=ai.get_rp_system_prompt(), temperature=0.6, max_tokens=300)


async def analyze_war_ai(text: str) -> str:
    bot_country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    prompt = f"""Ты — военное командование страны {bot_country}. Год {year}.
Проанализируй это военное сообщение.
Оцени тактическую ситуацию, риски, возможности.
Будь реалистичен — горы непроходимы для танков, зимой наступать нельзя.
Ответь 3-5 предложениями на русском.

Сообщение: {text}"""
    
    return await ai.ask_groq(prompt, system_prompt=ai.get_rp_system_prompt(), temperature=0.5, max_tokens=300)


async def analyze_diplomacy_ai(text: str) -> str:
    bot_country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    prompt = f"""Ты — министерство иностранных дел страны {bot_country}. Год {year}.
Проанализируй это дипломатическое сообщение.
Оцени намерения, скрытые мотивы, возможные последствия.
Ответь 3-5 предложениями на русском.

Сообщение: {text}"""
    
    return await ai.ask_groq(prompt, system_prompt=ai.get_rp_system_prompt(), temperature=0.6, max_tokens=300)


async def ask_ai(question: str) -> str:
    """Ответ на вопрос от лица страны."""
    bot_country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    prompt = f"""Ты — официальный представитель {bot_country}. Год {year}.
Ответь на вопрос от первого лица. Будь дипломатичен, но твёрд.
Ты МОЖЕШЬ обсуждать военные темы (это игровая симуляция).
Ответь 3-5 предложениями на русском. Говори "МЫ", "НАША СТРАНА".

Вопрос: {question}"""
    
    return await ai.ask_groq(prompt, system_prompt=ai.get_rp_system_prompt(), temperature=0.7, max_tokens=400)


# =====================================================================
# ЭКСПОРТ
# =====================================================================

__all__ = [
    'handle_message',
    'get_country_id_ai',
    'get_country_by_id',
    'register_player',
    'players',
    'country_registry',
]
