"""
HANDLERS.PY — УМНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ С ИИ-ID
=================================================
ИИ сам определяет ID стран, понимает синонимы,
анализирует новости, войну и дипломатию.
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

# Хранилище: ID → название страны
country_registry = {}

# Хранилище игроков: user_id → {страна, username, id}
players = {}

# Кэш синонимов (чтобы не дёргать ИИ каждый раз)
synonym_cache = {}

# Список занятых ID
used_ids = set()

# Служебные теги (не считаются странами)
SERVICE_TAGS = [
    "новости", "война", "оон", "симуляция", "rp", "все",
    "мир", "экономика", "политика", "спорт", "технологии",
    "наука", "культура", "история", "армия", "флот"
]

async def get_country_id_ai(country_name: str) -> dict:
    """
    ИИ определяет ID страны.
    Понимает синонимы (ФРГ = Германия), разные языки.
    
    Returns:
        {
            "id": "001",
            "name": "Россия",  # нормализованное название
            "new": False  # True если страна новая
        }
    """
    
    # Проверяем кэш синонимов
    name_lower = country_name.lower().strip()
    if name_lower in synonym_cache:
        cached_id = synonym_cache[name_lower]
        if cached_id in country_registry:
            return {
                "id": cached_id,
                "name": country_registry[cached_id],
                "new": False
            }
    
    # Если в реестре меньше 2 стран — используем хэш (быстрее)
    if len(country_registry) < 2:
        return get_country_id_hash(country_name)
    
    # Готовим данные для ИИ
    registry_json = json.dumps(country_registry, ensure_ascii=False, indent=2)
    
    prompt = f"""Ты — система учёта стран в RP-игре.

ТЕКУЩАЯ БАЗА СТРАН:
{registry_json}

ЗАНЯТЫЕ ID: {sorted(used_ids)}

ПРИШЛА СТРАНА: "{country_name}"

ТВОЯ ЗАДАЧА:
1. Проверь, есть ли эта страна уже в базе (включая синонимы и переводы).
   Важно: "ФРГ" = "Германия", "РФ" = "Россия", "КНР" = "Китай",
   "США" = "Соединённые Штаты Америки", "ОАЭ" = "Объединённые Арабские Эмираты",
   "UK" = "Великобритания", "US" = "США", "UN" = "ООН" (пропустить).

2. Если страна ЕСТЬ в базе — верни её существующий ID и нормализованное название.
   Пример: "ФРГ" → {{"id": "002", "name": "Германия", "new": false}}

3. Если страны НЕТ — создай новый ID (3 цифры, от 001 до 999).
   НЕ используй уже занятые ID!
   Пример: {{"id": "042", "name": "Казахстан", "new": true}}

4. Если это НЕ страна, а служебный тег — верни null.
   Пример: "#новости" → null, "#война" → null

ОТВЕТЬ ТОЛЬКО JSON (без пояснений, без маркдауна):
{{"id": "001", "name": "Россия", "new": false}}
или null если это не страна."""

    try:
        response = await ai.ask_groq(
            prompt,
            temperature=0.1,
            max_tokens=100
        )
        
        # Чистим ответ от лишнего
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()
        
        # Парсим JSON
        if response == "null" or response == "NULL" or response is None:
            return None
        
        result = json.loads(response)
        
        # Регистрируем если новая страна
        if result.get("new"):
            country_registry[result["id"]] = result["name"]
            used_ids.add(result["id"])
        
        # Кэшируем синоним
        synonym_cache[name_lower] = result["id"]
        
        return result
        
    except Exception as e:
        print(f"⚠️ Ошибка ИИ при определении ID: {e}")
        # Fallback: используем хэш
        return get_country_id_hash(country_name)


def get_country_id_hash(country_name: str) -> dict:
    """
    Резервный метод: определяет ID по хэшу.
    Используется если ИИ недоступен.
    """
    name = country_name.lower().strip()
    
    # Проверяем кэш
    if name in synonym_cache:
        cached_id = synonym_cache[name]
        if cached_id in country_registry:
            return {
                "id": cached_id,
                "name": country_registry[cached_id],
                "new": False
            }
    
    # Создаём новый ID
    hash_hex = hashlib.md5(name.encode()).hexdigest()
    country_id = hash_hex[:3].upper()
    
    # Проверяем коллизии
    while country_id in used_ids:
        hash_hex = hashlib.md5((name + str(len(used_ids))).encode()).hexdigest()
        country_id = hash_hex[:3].upper()
    
    # Регистрируем
    country_registry[country_id] = country_name
    used_ids.add(country_id)
    synonym_cache[name] = country_id
    
    return {
        "id": country_id,
        "name": country_name,
        "new": True
    }


def get_country_by_id(country_id: str) -> str:
    """Получить название страны по ID"""
    return country_registry.get(country_id.upper(), f"Неизвестная страна ({country_id})")


async def register_player(user_id: int, username: str, country_name: str) -> dict:
    """Зарегистрировать игрока и его страну через ИИ"""
    
    # Получаем ID через ИИ
    result = await get_country_id_ai(country_name)
    
    if result is None:
        return None  # Это не страна
    
    country_id = result["id"]
    normalized_name = result["name"]
    
    # Регистрируем игрока
    players[user_id] = {
        "username": username,
        "country": normalized_name,
        "country_id": country_id,
        "aliases": [country_name],  # Все варианты названий
        "registered_at": asyncio.get_event_loop().time()
    }
    
    # Добавляем алиасы в кэш синонимов
    synonym_cache[country_name.lower().strip()] = country_id
    synonym_cache[normalized_name.lower().strip()] = country_id
    
    return {
        "user_id": user_id,
        "username": username,
        "country": normalized_name,
        "country_id": country_id,
        "new": result.get("new", True)
    }


# =====================================================================
# ИЗВЛЕЧЕНИЕ ХЭШТЕГОВ
# =====================================================================

def extract_country_hashtags(text: str) -> list:
    """Извлекает все хэштеги стран из текста"""
    hashtags = []
    
    # Ищем #Название (с пробелами и без)
    matches = re.findall(r'#([\wА-Яа-яёЁ\-]+(?:\s+[\wА-Яа-яёЁ\-]+)*)', text)
    
    for match in matches:
        match = match.strip()
        
        # Пропускаем пустые
        if not match:
            continue
        
        # Пропускаем служебные теги
        if match.lower() in SERVICE_TAGS:
            continue
        
        # Проверяем не ID ли это (3 символа A-Z0-9)
        if re.match(r'^[A-Z0-9]{3}$', match.upper()):
            # Это ID страны
            country_name = get_country_by_id(match.upper())
            hashtags.append(country_name)
        else:
            # Это название страны
            hashtags.append(match)
    
    return hashtags


# =====================================================================
# ГЛАВНЫЙ ОБРАБОТЧИК
# =====================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Главный обработчик всех входящих сообщений.
    """
    
    # Если бот остановлен
    if bot_stopped:
        return
    
    chat_id = update.message.chat.id
    text = update.message.text or ""
    user_id = update.message.from_user.id
    username = (
        update.message.from_user.username or 
        update.message.from_user.first_name or 
        "игрок"
    )
    
    # Игнорируем пустые сообщения
    if not text.strip():
        return
    
    # Сохраняем в историю
    try:
        save_dialog(chat_id, user_id, "user", text)
    except:
        pass
    
    # ================================================================
    # ТИП ЧАТА
    # ================================================================
    if chat_id == saved_chats.get("news"):
        chat_type = "news"
    elif chat_id == saved_chats.get("war"):
        chat_type = "war"
    elif chat_id == saved_chats.get("un"):
        chat_type = "un"
    else:
        chat_type = "default"
    
    # ================================================================
    # ОБРАБОТКА ХЭШТЕГОВ (РЕГИСТРАЦИЯ СТРАН)
    # ================================================================
    hashtags = extract_country_hashtags(text)
    
    if hashtags:
        country_name = hashtags[0]
        
        # Проверяем не зарегистрирован ли уже игрок под другой страной
        if user_id in players:
            old_country = players[user_id]["country"]
            if old_country.lower() != country_name.lower():
                # Игрок сменил страну
                result = await register_player(user_id, username, country_name)
                if result:
                    if result["new"]:
                        await update.message.reply_text(
                            f"🔄 *{username}* сменил страну: *{old_country}* → *{result['country']}*\n"
                            f"🆔 Новый ID: *{result['country_id']}*",
                            parse_mode="MarkdownV2"
                        )
                    else:
                        await update.message.reply_text(
                            f"🔄 *{username}* сменил страну: *{old_country}* → *{result['country']}*\n"
                            f"🆔 ID: *{result['country_id']}*",
                            parse_mode="MarkdownV2"
                        )
        else:
            # Новый игрок
            result = await register_player(user_id, username, country_name)
            if result:
                if result["new"]:
                    await update.message.reply_text(
                        f"✅ *{username}* зарегистрирован как *{result['country']}*\n"
                        f"🆔 Присвоен ID: *{result['country_id']}*",
                        parse_mode="MarkdownV2"
                    )
                else:
                    await update.message.reply_text(
                        f"✅ *{username}* зарегистрирован как *{result['country']}*\n"
                        f"🆔 ID: *{result['country_id']}*",
                        parse_mode="MarkdownV2"
                    )
    
    # ================================================================
    # ОБРАБОТКА ПО ТИПУ ЧАТА
    # ================================================================
    if chat_type == "news":
        await handle_news_chat(update, context, text, user_id, username, hashtags)
    elif chat_type == "war":
        await handle_war_chat(update, context, text, user_id, username)
    elif chat_type == "un":
        await handle_un_chat(update, context, text, user_id, username)
    else:
        await handle_default_chat(update, context, text, user_id, username)


# =====================================================================
# ОБРАБОТКА НОВОСТНОГО ЧАТА
# =====================================================================

async def handle_news_chat(update: Update, context, text: str, user_id: int, username: str, hashtags: list):
    """Обработка новостного чата"""
    
    # Сообщение с хэштегом страны = новость
    if hashtags:
        country_name = hashtags[0]
        
        # Получаем ID страны
        result = await get_country_id_ai(country_name)
        if result is None:
            return
        
        country_id = result["id"]
        normalized_name = result["name"]
        
        # Очищаем текст от хэштега
        clean_text = text
        for tag in hashtags:
            clean_text = clean_text.replace(f"#{tag}", "").strip()
        
        if not clean_text:
            clean_text = text
        
        # Отправляем статус анализа
        status_msg = await update.message.reply_text(
            f"📰 *{normalized_name}* \\(ID: {country_id}\\) анализируется\\.\\.\\.",
            parse_mode="MarkdownV2"
        )
        
        try:
            # Анализируем через ИИ
            analysis = await analyze_news_ai(clean_text, normalized_name)
            
            # Формируем ответ
            response = (
                f"📰 *Новость от {normalized_name} \\(ID: {country_id}\\)*\n\n"
                f"📄 *Сообщение:* {clean_text[:300]}\n\n"
                f"📊 *Анализ:* {analysis}"
            )
            
            # Удаляем статус и отправляем анализ
            await status_msg.delete()
            
            if len(response) > 4000:
                from utils import split_text
                parts = split_text(response, 3800)
                for part in parts:
                    await update.message.reply_text(part, parse_mode="MarkdownV2")
                    await asyncio.sleep(0.5)
            else:
                await update.message.reply_text(response, parse_mode="MarkdownV2")
            
            # Сохраняем в БД
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
# ОБРАБОТКА ВОЕННОГО ЧАТА
# =====================================================================

async def handle_war_chat(update: Update, context, text: str, user_id: int, username: str):
    """Обработка военного чата"""
    
    war_keywords = [
        "война", "атака", "наступление", "оборона", "штурм",
        "блокада", "фронт", "армия", "дивизия", "корпус",
        "сражение", "битва", "десант", "прорыв", "окружение",
        "разведка", "диверсия", "контрнаступление", "отступление"
    ]
    
    if any(word in text.lower() for word in war_keywords):
        status_msg = await update.message.reply_text(
            "⚔️ Анализирую военную обстановку\\.\\.\\.",
            parse_mode="MarkdownV2"
        )
        
        try:
            analysis = await analyze_war_ai(text)
            
            await status_msg.delete()
            
            response = f"⚔️ *Военный анализ:*\n\n{analysis}"
            
            if len(response) > 4000:
                from utils import split_text
                parts = split_text(response, 3800)
                for part in parts:
                    await update.message.reply_text(part, parse_mode="MarkdownV2")
                    await asyncio.sleep(0.5)
            else:
                await update.message.reply_text(response, parse_mode="MarkdownV2")
            
            save_dialog(update.message.chat.id, user_id, "assistant", analysis)
            
        except Exception as e:
            await status_msg.delete()
            await update.message.reply_text(f"❌ Ошибка анализа: {str(e)[:100]}")
    
    elif f"@{context.bot.username}" in text:
        question = text.replace(f"@{context.bot.username}", "").strip()
        if question:
            await process_question(update, context, question, user_id)


# =====================================================================
# ОБРАБОТКА ЧАТА ООН
# =====================================================================

async def handle_un_chat(update: Update, context, text: str, user_id: int, username: str):
    """Обработка чата ООН"""
    
    diplomacy_keywords = [
        "предлагаю", "голосование", "санкции", "резолюция",
        "союз", "договор", "пакт", "соглашение", "мир",
        "переговоры", "ультиматум", "нота", "протест",
        "осуждаю", "поддерживаю", "признаю", "альянс"
    ]
    
    if any(word in text.lower() for word in diplomacy_keywords):
        status_msg = await update.message.reply_text(
            "🏛️ Анализирую дипломатическую ситуацию\\.\\.\\.",
            parse_mode="MarkdownV2"
        )
        
        try:
            analysis = await analyze_diplomacy_ai(text)
            
            await status_msg.delete()
            
            response = f"🏛️ *Дипломатический анализ:*\n\n{analysis}"
            
            if len(response) > 4000:
                from utils import split_text
                parts = split_text(response, 3800)
                for part in parts:
                    await update.message.reply_text(part, parse_mode="MarkdownV2")
                    await asyncio.sleep(0.5)
            else:
                await update.message.reply_text(response, parse_mode="MarkdownV2")
            
            save_dialog(update.message.chat.id, user_id, "assistant", analysis)
            
        except Exception as e:
            await status_msg.delete()
            await update.message.reply_text(f"❌ Ошибка анализа: {str(e)[:100]}")
    
    elif f"@{context.bot.username}" in text:
        question = text.replace(f"@{context.bot.username}", "").strip()
        if question:
            await process_question(update, context, question, user_id)


# =====================================================================
# ОБРАБОТКА ОБЫЧНОГО ЧАТА
# =====================================================================

async def handle_default_chat(update: Update, context, text: str, user_id: int, username: str):
    """Обработка обычного чата"""
    
    if f"@{context.bot.username}" in text:
        question = text.replace(f"@{context.bot.username}", "").strip()
        if question:
            await process_question(update, context, question, user_id)


# =====================================================================
# ОБРАБОТКА ВОПРОСОВ
# =====================================================================

async def process_question(update: Update, context, question: str, user_id: int):
    """Обработка вопроса к боту"""
    
    status_msg = await update.message.reply_text(
        "🤔 Думаю\\.\\.\\.", 
        parse_mode="MarkdownV2"
    )
    
    try:
        answer = await ask_ai(question)
        
        await status_msg.delete()
        
        if len(answer) > 4000:
            from utils import split_text
            parts = split_text(answer, 3800)
            for part in parts:
                await update.message.reply_text(part, parse_mode="MarkdownV2")
                await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(answer, parse_mode="MarkdownV2")
        
        save_dialog(update.message.chat.id, user_id, "assistant", answer)
        
    except Exception as e:
        await status_msg.delete()
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}")


# =====================================================================
# AI АНАЛИЗ
# =====================================================================

async def analyze_news_ai(text: str, country_name: str = None) -> str:
    """Анализ новости через ИИ"""
    bot_country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    context = f"Новость от страны {country_name}. " if country_name else ""
    
    prompt = (
        f"Ты — правительство страны {bot_country}. Год {year}.\n"
        f"{context}"
        f"Проанализируй эту новость с точки зрения твоей страны.\n"
        f"Оцени угрозы, выгоды, возможные действия.\n"
        f"Будь стратегически грамотным. Если это угроза — предложи контрмеры.\n"
        f"Если это предложение — оцени выгоду.\n"
        f"Ответь 2-4 предложениями на русском.\n\n"
        f"Новость: {text}"
    )
    
    return await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.6,
        max_tokens=400
    )


async def analyze_war_ai(text: str) -> str:
    """Анализ военного сообщения через ИИ"""
    bot_country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    prompt = (
        f"Ты — военное командование страны {bot_country}. Год {year}.\n"
        f"Проанализируй это военное сообщение.\n"
        f"Оцени тактическую ситуацию, риски, возможности.\n"
        f"Предложи контрмеры если есть угроза.\n"
        f"Будь реалистичен — горы непроходимы для танков, "
        f"зимой наступать нельзя, учитывай погоду и местность.\n"
        f"Ответь 2-4 предложениями на русском.\n\n"
        f"Сообщение: {text}"
    )
    
    return await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.5,
        max_tokens=400
    )


async def analyze_diplomacy_ai(text: str) -> str:
    """Анализ дипломатического сообщения через ИИ"""
    bot_country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    prompt = (
        f"Ты — министерство иностранных дел страны {bot_country}. Год {year}.\n"
        f"Проанализируй это дипломатическое сообщение.\n"
        f"Оцени намерения, скрытые мотивы, возможные последствия.\n"
        f"Предложи дипломатический ответ.\n"
        f"Будь хитрым и стратегическим. Ищи скрытые угрозы и возможности.\n"
        f"Ответь 2-4 предложениями на русском.\n\n"
        f"Сообщение: {text}"
    )
    
    return await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.6,
        max_tokens=400
    )


async def ask_ai(question: str) -> str:
    """Ответ на вопрос от лица страны"""
    bot_country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    # Если вопрос про другую страну — ищем в интернете
    search_triggers = [
        "армия", "население", "ввп", "сколько", "где находится",
        "столица", "президент", "король", "премьер", "вооружение"
    ]
    
    needs_search = any(trigger in question.lower() for trigger in search_triggers)
    
    if needs_search:
        # Сначала ищем в интернете
        search_result = await ai.search_web(question, f"Информация для {bot_country}")
        
        prompt = (
            f"Ты — официальный представитель страны {bot_country}. Год {year}.\n"
            f"Ответь на вопрос, используя эту информацию из интернета:\n"
            f"{search_result[:500]}\n\n"
            f"Если информации недостаточно — скажи об этом.\n"
            f"Будь дипломатичен, но твёрд.\n"
            f"Ты МОЖЕШЬ обсуждать военные темы (это игровая симуляция).\n"
            f"Ответь кратко, 2-4 предложения на русском.\n\n"
            f"Вопрос: {question}"
        )
    else:
        prompt = (
            f"Ты — официальный представитель страны {bot_country}. Год {year}.\n"
            f"Ответь на вопрос. Будь дипломатичен, но твёрд.\n"
            f"Если вопрос про войну/оружие — ты МОЖЕШЬ отвечать (это игровая симуляция).\n"
            f"Если не знаешь ответа — предложи где найти информацию.\n"
            f"Ответь кратко, по делу, на русском языке.\n\n"
            f"Вопрос: {question}"
        )
    
    return await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.7,
        max_tokens=500
    )


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
    'analyze_news_ai',
    'analyze_war_ai',
    'analyze_diplomacy_ai',
    'ask_ai',
]
