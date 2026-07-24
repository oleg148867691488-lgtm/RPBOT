import re
import datetime
import pytz
from config import ADMIN_ID

# === РАЗБИВКА ДЛИННЫХ СООБЩЕНИЙ (ДЛЯ TELEGRAM) ===
def split_text(text: str, max_len: int = 4096) -> list:
    """
    Разбивает длинный текст на части, чтобы не превысить лимит Telegram (4096 символов).
    """
    if len(text) <= max_len:
        return [text]
    
    parts = []
    lines = text.split('\n')
    current_part = ""
    
    for line in lines:
        if len(current_part) + len(line) + 1 <= max_len:
            current_part += line + "\n"
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = line + "\n"
    
    if current_part:
        parts.append(current_part.strip())
    
    return parts

# === ПРОВЕРКА АДМИНА ===
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# === ГЕНЕРАТОР МЕСЯЦА ПО МСК ===
def get_rp_month() -> str:
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.datetime.now(tz)
    hour = now.hour
    month_index = (hour // 2) % 12
    months = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
    ]
    return months[month_index]

# === ГЕНЕРАТОР ВРЕМЕНИ (ДЛЯ НОВОСТЕЙ) ===
def get_current_time() -> str:
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.datetime.now(tz)
    return now.strftime("%d.%m.%Y %H:%M")

# === ИЗВЛЕЧЕНИЕ КЛЮЧЕВЫХ СЛОВ ===
def extract_keywords(text: str, min_len: int = 4, max_words: int = 5) -> list:
    words = re.findall(r'[\w]+', text.lower())
    stop_words = {
        'что', 'как', 'для', 'это', 'так', 'вот', 'если', 'то', 'на', 'с', 'по',
        'из', 'у', 'о', 'об', 'без', 'до', 'за', 'при', 'через', 'между', 'среди', 'про'
    }
    keywords = [w for w in words if w not in stop_words and len(w) >= min_len]
    return list(set(keywords))[:max_words]

# === ФОРМАТИРОВАНИЕ ЧИСЕЛ ===
def format_number(num: int) -> str:
    return f"{num:,}".replace(",", " ")

# === ПРОВЕРКА, ЕСТЬ ЛИ КЛЮЧЕВОЕ СЛОВО ===
def has_keyword(text: str, keywords: list) -> bool:
    for kw in keywords:
        if kw.lower() in text.lower():
            return True
    return False

# === ФИЛЬТР ДЛЯ НОВОСТЕЙ ===
def sanitize_news(text: str) -> str:
    # Убираем лишние пробелы и переносы
    text = re.sub(r'\s+', ' ', text)
    # Убираем недопустимые символы
    text = re.sub(r'[^\w\s\.,!?\-]', '', text)
    return text.strip()

# === ЛОГИРОВАНИЕ ===
def log_message(user_id: int, action: str, details: str = ""):
    timestamp = get_current_time()
    print(f"[{timestamp}] Пользователь {user_id}: {action} {details}")
