import os
from dotenv import load_dotenv

load_dotenv()

# === ТОКЕН ТЕЛЕГРАМА ===
BOT_TOKEN = os.getenv("BOT_TOKEN")

# === API-КЛЮЧИ ===
GROQ_KEYS = [
    os.getenv("GROQ_KEY_1"),
    os.getenv("GROQ_KEY_2"),
    os.getenv("GROQ_KEY_3"),
    os.getenv("GROQ_KEY_4"),
    os.getenv("GROQ_KEY_5"),
]
OLLAMA_KEY = os.getenv("OLLAMA_KEY")
GEMINI_KEY = os.getenv("GEMINI_KEY")

# === АДМИН ===
ADMIN_ID = 7184396483

# === СТАРТОВЫЕ ПАРАМЕТРЫ (их можно менять под сценарий) ===
START_YEAR = 2022  # Стартовый год
START_BUDGET = 10_000_000  # 10 млн $ (можно изменить)
START_ARMY = 50_000  # 50 тыс. солдат
START_TANKS = 100
START_PLANES = 20
START_SHIPS = 5

# === ОГРАНИЧЕНИЯ (чтобы бот не делал глупостей) ===
MAX_OPERATION_SIZE = 0.5  # Не более 50% армии на одну операцию
MINIMUM_DEFENSE = 0.3     # Минимум 30% армии на оборону

# === ФУНКЦИИ ДЛЯ ПОЛУЧЕНИЯ РЕАЛЬНЫХ ЦЕН ===
async def get_real_price(resource: str) -> int:
    """
    Запрашивает актуальную цену ресурса через Ollama или Gemini.
    Возвращает цену в $ за тонну (или унцию для золота).
    """
    # Сначала пробуем Ollama
    try:
        # Здесь будет реальный запрос к Ollama с поиском в интернете
        price = await ollama_search_price(resource)
        if price:
            return price
    except:
        pass
    
    # Если Ollama не справилась — пробуем Gemini
    try:
        price = await gemini_search_price(resource)
        if price:
            return price
    except:
        pass
    
    # Если всё упало — возвращаем примерную цену (как запасной вариант)
    fallback_prices = {
        "steel": 700,
        "oil": 80,
        "grain": 220,
        "gold": 2000
    }
    return fallback_prices.get(resource, 500)
