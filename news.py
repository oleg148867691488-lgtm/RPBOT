import httpx
import random
from config import GROQ_API_KEY, GROQ_URL, ADMIN_ID
from history import get_country, get_year
from commands import bot_stopped

# === ГЕНЕРАЦИЯ НОВОСТИ ЧЕРЕЗ ИИ ===
async def generate_news():
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2022

    prompt = (
        f"Ты — {country} в {year} году. Придумай краткую новость от лица страны. "
        f"Новость должна быть на русском, 2-3 предложения. "
        f"Тема: события в мире, политика, экономика, война или дипломатия."
    )

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=data)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        # Если Groq упал — запасные новости
        return random.choice([
            f"📰 *{country}* объявила о новых экономических реформах в {year} году.",
            f"📰 В {country} прошли масштабные учения вооружённых сил.",
            f"📰 {country} подписала торговое соглашение с соседями.",
            f"📰 В {country} началась программа модернизации инфраструктуры."
        ])

# === ОТПРАВКА НОВОСТИ В ЧАТ ===
async def send_news_to_chat(context, news_text):
    from config import saved_chats
    chat_id = saved_chats.get("news")
    if chat_id:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📰 *Новость:*\n\n{news_text}"
        )

# === ЗАДАЧА ДЛЯ ПЛАНИРОВЩИКА ===
async def generate_news_task():
    if bot_stopped:
        return
    news = await generate_news()
    # Отправляем в новостной канал
    from config import saved_chats
    chat_id = saved_chats.get("news")
    if chat_id:
        await app.bot.send_message(
            chat_id=chat_id,
            text=f"📰 *Новость дня:*\n\n{news}"
        )

# === АНАЛИЗ НОВОСТИ ОТ ИГРОКА ===
async def analyze_news(text: str):
    prompt = (
        f"Ты — аналитик. Проанализируй эту новость и дай краткий комментарий "
        f"от лица страны (нейтрально, но с лёгкой иронией).\n\n"
        f"Новость: {text}"
    )

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.5,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=data)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except:
        return "📰 Комментарий временно недоступен."

# === ОБЫЧНЫЙ ОТВЕТ НА ВОПРОС ===
async def ask_ai(question: str):
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2022

    prompt = (
        f"Ты — {country} в {year} году. Отвечай на вопросы от лица страны. "
        f"Говори с лёгким акцентом, но без 'месье'. Отвечай кратко, по делу.\n\n"
        f"Вопрос: {question}"
    )

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.5,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(GROQ_URL, headers=headers, json=data)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except:
        return "❌ Ошибка: не удалось получить ответ."
