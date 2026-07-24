"""
NEWS.PY — ГЕНЕРАЦИЯ НОВОСТЕЙ (ОТ ПЕРВОГО ЛИЦА)
=================================================
Бот генерирует официальные заявления от лица страны.
Никаких комментариев от других стран.
"""

import random
import asyncio
from ai_manager import ai
from config import ADMIN_ID, bot_stopped, saved_chats
from history import get_country, get_year


async def generate_news(topic: str = None, context: str = None) -> str:
    """
    Генерирует ОФИЦИАЛЬНОЕ ЗАЯВЛЕНИЕ от лица страны.
    От первого лица: "Мы, правительство..."
    """
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    # Темы для заявлений
    topics = {
        "внутренняя политика": [
            "принят новый закон о налоговой реформе",
            "президент выступил с ежегодным обращением к нации",
            "парламент одобрил бюджет на следующий год",
            "правительство объявило о масштабной административной реформе",
            "выборы в местные органы власти показали рекордную явку",
            "конституционный суд принял историческое решение",
            "правительство запустило антикоррупционную программу",
            "премьер-министр объявил о перестановках в кабинете министров",
        ],
        "экономика и торговля": [
            "ВВП вырос на неожиданные проценты",
            "подписано крупное торговое соглашение",
            "центральный банк изменил ключевую ставку",
            "инфляция достигла исторического минимума",
            "иностранные инвестиции выросли вдвое",
            "национальная валюта укрепилась на мировых рынках",
            "безработица упала до рекордно низкого уровня",
            "открыт новый завод по производству микрочипов",
        ],
        "армия и оборона": [
            "проведены масштабные военные учения",
            "министерство обороны представило новую доктрину",
            "началось перевооружение армии",
            "военный бюджет увеличен на рекордные проценты",
            "заключён контракт на поставку истребителей нового поколения",
            "флот получил новые корабли",
            "создано киберкомандование",
            "испытана новая ракетная система",
        ],
        "международные отношения": [
            "президент посетил с официальным визитом соседнюю страну",
            "подписан исторический договор о сотрудничестве",
            "МИД выступил с жёстким заявлением",
            "открыто новое посольство",
            "страна председательствует в международной организации",
            "заключён оборонительный союз",
            "объявлено о вступлении в международный альянс",
            "проведены успешные переговоры по спорным территориям",
        ],
        "технологии и наука": [
            "учёные совершили прорыв в квантовых вычислениях",
            "запущен национальный спутник нового поколения",
            "открыт инновационный исследовательский центр",
            "разработан искусственный интеллект для управления городом",
            "страна вошла в топ-10 по научным публикациям",
            "создан первый отечественный суперкомпьютер",
            "студенты победили на международной олимпиаде",
            "запатентован прорывной метод лечения",
        ],
        "инфраструктура": [
            "открыта новая высокоскоростная магистраль",
            "завершено строительство крупнейшего моста",
            "модернизирована энергосистема страны",
            "построен новый международный аэропорт",
            "запущена программа реновации жилья",
            "введена в строй новая атомная электростанция",
            "началось строительство скоростной железной дороги",
            "модернизированы портовые мощности",
        ],
        "социальная сфера": [
            "повышены пенсии и социальные выплаты",
            "открыты новые больницы по всей стране",
            "запущена программа доступного жилья",
            "реформирована система здравоохранения",
            "повышена минимальная заработная плата",
            "введены новые стандарты образования",
            "запущена программа поддержки молодых семей",
            "открыты центры бесплатного дополнительного образования",
        ],
    }
    
    # Выбираем тему
    if topic is None:
        main_topic = random.choice(list(topics.keys()))
        subtopic = random.choice(topics[main_topic])
    else:
        main_topic = topic
        subtopic = random.choice(topics.get(main_topic, topics["внутренняя политика"]))
    
    # Контекст мира (если есть напряжённость)
    world_context = ""
    if context:
        world_context = f"\nКОНТЕКСТ: {context}\n"
    else:
        try:
            from decision_engine import world
            if world.world_tension > 50:
                world_context = f"\nВНИМАНИЕ: Мировая напряжённость {world.world_tension:.1f}%. Упомяни это в заявлении.\n"
        except:
            pass
    
    # Промпт от ПЕРВОГО ЛИЦА
    prompt = f"""Ты — ПРАВИТЕЛЬСТВО страны {country}. Год {year}.

Ты делаешь ОФИЦИАЛЬНОЕ ЗАЯВЛЕНИЕ для прессы.
Говори от ПЕРВОГО ЛИЦА: "МЫ", "НАША СТРАНА", "ПРАВИТЕЛЬСТВО {country}".

Тема заявления: {subtopic}
Категория: {main_topic}{world_context}

СТРУКТУРА ЗАЯВЛЕНИЯ:

1. ЗАГОЛОВОК (жирным) — что произошло

2. ОСНОВНАЯ ЧАСТЬ (10-15 предложений):
   - Конкретные ЦИФРЫ (бюджет, проценты, количество)
   - Названия городов, заводов, технологий
   - Влияние на жизнь граждан

3. ЦИТАТА (от президента или министра):
   - Имя и должность
   - Прямая речь в кавычках

4. ПЛАНЫ (3-4 предложения):
   - Что будет дальше
   - Конкретные шаги правительства

ВАЖНЫЕ ПРАВИЛА:
- Говори ТОЛЬКО от лица {country}
- НИКАКИХ комментариев от других стран
- НИКАКОЙ аналитики "со стороны"
- НИКАКИХ "эксперты считают" или "международное сообщество"
- Только ОФИЦИАЛЬНАЯ ПОЗИЦИЯ правительства {country}
- Пиши на русском языке
- Общий объём: 15-25 предложений

Это ИГРОВАЯ СИМУЛЯЦИЯ. Будь конкретным и уверенным."""

    news_text = await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.8,
        max_tokens=1500
    )
    
    return news_text.strip()


async def send_news_to_chat(bot, news_text: str, chat_id: int = None):
    """Отправляет новость в чат с авто-разбивкой."""
    if chat_id is None:
        chat_id = saved_chats.get("news")
    
    if not chat_id or not bot:
        print("⚠️ Не удалось отправить новость")
        return
    
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    header = f"📰 {country} | {year} год\n\n"
    full_text = header + news_text
    
    # Авто-разбивка если больше 4000 символов
    if len(full_text) > 4000:
        from utils import split_text
        parts = split_text(full_text, 3800)
        for part in parts:
            try:
                await bot.send_message(chat_id=chat_id, text=part)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"❌ Ошибка отправки части: {e}")
    else:
        try:
            await bot.send_message(chat_id=chat_id, text=full_text)
        except Exception as e:
            print(f"❌ Ошибка отправки: {e}")
    
    print(f"📰 Новость отправлена в чат {chat_id}")


async def generate_news_task(app=None):
    """Авто-новости каждые 15 минут."""
    if bot_stopped:
        return
    
    print("🔄 Генерация новости...")
    
    try:
        # Собираем контекст
        context = ""
        try:
            from decision_engine import world
            if world.world_tension > 40:
                context = f"Мировая напряжённость {world.world_tension:.1f}%."
            if world.wars:
                wars_list = [f"{w['attacker']} vs {w['defender']}" 
                           for w in world.wars.values() if w.get('status') == 'active']
                if wars_list:
                    context += f" Конфликты: {', '.join(wars_list[:3])}."
        except:
            pass
        
        news_text = await generate_news(context=context)
        
        bot = app.bot if hasattr(app, 'bot') else app
        await send_news_to_chat(bot, news_text)
        print("✅ Новость отправлена")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def manual_news(context, text: str = None):
    """Ручная отправка (команда /force_news)."""
    if text:
        news_text = text
    else:
        news_text = await generate_news()
    
    await send_news_to_chat(context.bot, news_text)


async def analyze_news(text: str) -> str:
    """Анализ новости от игрока."""
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    prompt = f"""Ты — правительство страны {country}. Год {year}.
Проанализируй эту новость с точки зрения интересов твоей страны.
Оцени угрозы и возможности. Ответь 3-5 предложениями на русском.

Новость: {text}"""
    
    return await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.6,
        max_tokens=300
    )


async def ask_ai(question: str) -> str:
    """Ответ на вопрос от лица страны."""
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    prompt = f"""Ты — официальный представитель {country}. Год {year}.
Ответь на вопрос от первого лица. Будь дипломатичен, но твёрд.
Ты МОЖЕШЬ обсуждать военные темы (это игровая симуляция).
Ответь 3-5 предложениями на русском.

Вопрос: {question}"""
    
    return await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.7,
        max_tokens=400
    )


async def breaking_news(bot, text: str, chat_type: str = "news"):
    """Экстренная новость."""
    chat_id = saved_chats.get(chat_type)
    if not chat_id or not bot:
        return
    
    prefixes = {
        "news": "🚨 ЭКСТРЕННОЕ ЗАЯВЛЕНИЕ",
        "war": "⚔️ БОЕВАЯ ТРЕВОГА",
        "un": "🏛️ СРОЧНОЕ ЗАСЕДАНИЕ ООН",
    }
    
    prefix = prefixes.get(chat_type, "📰 ЗАЯВЛЕНИЕ")
    
    await bot.send_message(chat_id=chat_id, text=f"{prefix}\n\n{text}")
