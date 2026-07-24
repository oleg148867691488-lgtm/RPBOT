"""
NEWS.PY — ГЕНЕРАЦИЯ И ОТПРАВКА НОВОСТЕЙ
=========================================
Новости каждые 15 минут (8 за 2 игровых месяца).
Интегрировано с ai_manager и decision_engine.
"""

import random
import asyncio
from ai_manager import ai
from config import ADMIN_ID, bot_stopped, saved_chats
from history import get_country, get_year

# =====================================================================
# ГЕНЕРАЦИЯ НОВОСТИ
# =====================================================================

async def generate_news(topic: str = None) -> str:
    """
    Генерирует новость от лица страны через Groq.
    
    Args:
        topic: конкретная тема (если None — случайная)
    
    Returns:
        Текст новости
    """
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    # Темы новостей
    topics = [
        "политика и внутренние дела",
        "экономика и торговля",
        "армия и военные учения",
        "международные отношения",
        "технологии и наука",
        "дипломатия и переговоры",
        "инфраструктура и строительство",
        "культура и общество",
    ]
    
    if topic is None:
        topic = random.choice(topics)
    
    prompt = (
        f"Ты — государственное информационное агентство страны {country}. Год {year}.\n"
        f"Сгенерируй КРАТКУЮ новость (2-3 предложения) на тему: {topic}.\n"
        f"Новость должна быть реалистичной, соответствовать духу страны.\n"
        f"Пиши официальным тоном, на русском языке.\n"
        f"Не используй Markdown.\n\n"
        f"Формат: просто текст новости, без заголовков и подписей."
    )
    
    news_text = await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.8,
        max_tokens=300
    )
    
    return news_text.strip()


# =====================================================================
# ОТПРАВКА НОВОСТИ В ЧАТ
# =====================================================================

async def send_news_to_chat(bot, news_text: str, chat_id: int = None):
    """
    Отправляет новость в указанный чат.
    
    Args:
        bot: экземпляр бота (Application.bot)
        news_text: текст новости
        chat_id: ID чата (если None — берёт из saved_chats)
    """
    if chat_id is None:
        chat_id = saved_chats.get("news")
    
    if not chat_id or not bot:
        print("⚠️ Не удалось отправить новость: нет chat_id или bot")
        return
    
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    # Форматируем сообщение
    message = (
        f"📰 *Новости {country}*\n"
        f"📅 {year} год\n\n"
        f"{news_text}\n\n"
        f"_#симуляция #rp_"
    )
    
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown"
        )
        print(f"📰 Новость отправлена в чат {chat_id}")
    except Exception as e:
        print(f"❌ Ошибка отправки новости: {e}")


# =====================================================================
# ЗАДАЧА ДЛЯ ПЛАНИРОВЩИКА (АВТО-НОВОСТИ)
# =====================================================================

async def generate_news_task(app=None):
    """
    Задача для планировщика.
    Вызывается каждые 15 минут.
    
    Args:
        app: экземпляр Application (или None если вызывается из scheduler)
    """
    if bot_stopped:
        print("⏸️ Новости остановлены (бот на паузе)")
        return
    
    print(f"🔄 Генерация авто-новости...")
    
    try:
        # Генерируем новость
        news_text = await generate_news()
        
        # Получаем бота
        if app is None:
            from bot import app as bot_app
            bot = bot_app.bot
        elif hasattr(app, 'bot'):
            bot = app.bot
        else:
            bot = app
        
        # Отправляем
        await send_news_to_chat(bot, news_text)
        print(f"✅ Авто-новость отправлена")
        
    except Exception as e:
        print(f"❌ Ошибка в generate_news_task: {e}")


# =====================================================================
# РУЧНАЯ ОТПРАВКА НОВОСТИ (ДЛЯ КОМАНДЫ /NEWS)
# =====================================================================

async def manual_news(context, text: str = None):
    """
    Ручная отправка новости (из команды /news).
    
    Args:
        context: контекст из команды
        text: текст новости (если None — сгенерировать)
    """
    if text:
        news_text = text
    else:
        news_text = await generate_news()
    
    bot = context.bot
    chat_id = context.message.chat.id if hasattr(context, 'message') else None
    
    # Если это ответ на команду — отправляем и в текущий чат, и в новостной
    if chat_id:
        await send_news_to_chat(bot, news_text, chat_id)
    
    # Отправляем в новостной чат
    news_chat_id = saved_chats.get("news")
    if news_chat_id and news_chat_id != chat_id:
        await send_news_to_chat(bot, news_text, news_chat_id)


# =====================================================================
# АНАЛИЗ НОВОСТИ ОТ ИГРОКА
# =====================================================================

async def analyze_news(text: str) -> str:
    """
    Анализирует новость от игрока.
    Используется в handlers.py и commands.py.
    
    Args:
        text: текст новости
    
    Returns:
        Анализ от лица страны
    """
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    prompt = (
        f"Ты — правительство страны {country}. Год {year}.\n"
        f"Проанализируй эту новость. Оцени угрозы, выгоды, скрытые мотивы.\n"
        f"Будь стратегически грамотным, с лёгкой иронией.\n"
        f"Ответь 2-4 предложениями на русском языке.\n\n"
        f"Новость: {text}"
    )
    
    return await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.6,
        max_tokens=300
    )


# =====================================================================
# ОТВЕТ НА ВОПРОС (ОТ ЛИЦА СТРАНЫ)
# =====================================================================

async def ask_ai(question: str) -> str:
    """
    Ответ на вопрос от лица страны.
    Используется в handlers.py.
    
    Args:
        question: вопрос игрока
    
    Returns:
        Ответ от лица страны
    """
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    # Проверяем нужно ли искать в интернете
    search_triggers = [
        "сколько", "армия", "население", "ввп", "где", "кто",
        "президент", "столица", "вооружение", "техника", "танки"
    ]
    
    needs_search = any(trigger in question.lower() for trigger in search_triggers)
    
    if needs_search:
        # Ищем в интернете
        search_result = await ai.search_web(question, f"Информация для {country}")
        
        prompt = (
            f"Ты — официальный представитель {country}. Год {year}.\n"
            f"Ответь на вопрос, используя эту информацию:\n"
            f"{search_result[:500]}\n\n"
            f"Будь дипломатичен. Ты МОЖЕШЬ обсуждать военные темы (это игра).\n"
            f"Ответь кратко, 2-4 предложения на русском.\n\n"
            f"Вопрос: {question}"
        )
    else:
        prompt = (
            f"Ты — официальный представитель {country}. Год {year}.\n"
            f"Ответь на вопрос. Будь дипломатичен, но твёрд.\n"
            f"Ты МОЖЕШЬ обсуждать военные темы (это игровая симуляция).\n"
            f"Ответь кратко, по делу, на русском.\n\n"
            f"Вопрос: {question}"
        )
    
    return await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.7,
        max_tokens=500
    )


# =====================================================================
# ЭКСТРЕННАЯ НОВОСТЬ
# =====================================================================

async def breaking_news(bot, text: str, chat_type: str = "news"):
    """
    Экстренная новость (война, санкции, союзы).
    
    Args:
        bot: экземпляр бота
        text: текст новости
        chat_type: "news", "war", или "un"
    """
    chat_id = saved_chats.get(chat_type)
    
    if not chat_id or not bot:
        return
    
    prefixes = {
        "news": "🚨 *ЭКСТРЕННАЯ НОВОСТЬ*",
        "war": "⚔️ *БОЕВАЯ ТРЕВОГА*",
        "un": "🏛️ *СРОЧНОЕ ЗАСЕДАНИЕ ООН*",
    }
    
    prefix = prefixes.get(chat_type, "📰 *НОВОСТЬ*")
    
    message = f"{prefix}\n\n{text}"
    
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"❌ Ошибка экстренной новости: {e}")


# =====================================================================
# ТЕСТ
# =====================================================================

async def test_news():
    """Тест генерации новостей"""
    print("=" * 50)
    print("ТЕСТ NEWS")
    print("=" * 50)
    
    # Тест генерации
    print("\n📰 Генерация новости:")
    news = await generate_news()
    print(f"   {news}")
    
    # Тест анализа
    print("\n📊 Анализ новости:")
    analysis = await analyze_news("Франция объявила о повышении налогов на 50%")
    print(f"   {analysis}")
    
    # Тест вопроса
    print("\n💬 Ответ на вопрос:")
    answer = await ask_ai("Какая у вас армия?")
    print(f"   {answer}")


if __name__ == "__main__":
    asyncio.run(test_news())
