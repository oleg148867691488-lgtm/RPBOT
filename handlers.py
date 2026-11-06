"""
HANDLERS.PY — ЛОГИКА РП-БОТА (ФИНАЛ, ВРЕМЯ ПО МСК)
=====================================
- Симуляция времени РП: смена дня в 00:00 МСК, 1 реальный день = ~15.2 дня РП
- /verdict доступен всем (с кулдауном и лимитом)
- World Bank для точных экономических данных
- В группах бот отвечает ТОЛЬКО по @упоминанию или реплаю
"""

import re
import time
import httpx
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from config import (
    ADMIN_ID, ADMIN_USERNAME, FACTS_CHAT_ID,
    GROQ_URL, GROQ_KEY_MAIN, GROQ_KEY_VERDICT, GROQ_KEY_SUMMARY, GROQ_ALL_KEYS,
    MODEL_MAIN, MODEL_VERDICT, MODEL_SUMMARY,
    GEMINI_KEY, GEMINI_URL_TEMPLATE,
    OLLAMA_KEY, OLLAMA_URL,
    COOLDOWN_DIALOG, COOLDOWN_VERDICT,
    HISTORY_CONTEXT_LIMIT, HISTORY_SUMMARIZE_THRESHOLD, HISTORY_SUMMARIZE_BATCH,
)
import database as db


# =====================================================================
# СИМУЛЯЦИЯ ВРЕМЕНИ РП (ПРИВЯЗКА К 00:00 МСК)
# =====================================================================

def get_rp_datetime() -> dict:
    """
    Симуляция времени РП, привязанная к реальной полуночи МСК.
    Каждый реальный день в 00:00 МСК = +15.208 дней РП.
    365 дней РП проходят за 24 реальных дня.
    """
    saved_year = db.get_setting("rp_year")
    saved_start = db.get_setting("rp_start_time")
    empty = {"year": None, "month": None, "day": None, "hour": None,
             "full": None, "elapsed_hours": 0, "rp_days": 0, "real_msk": None,
             "days_to_new_year": None}
    if not saved_year or not saved_start:
        return empty
    try:
        base_year = int(saved_year)
        start_ts = float(saved_start)
    except (ValueError, TypeError):
        return empty

    # Реальное время МСК
    try:
        import pytz
        msk_tz = pytz.timezone("Europe/Moscow")
        now_msk = datetime.now(msk_tz)
    except ImportError:
        from datetime import timezone
        msk_tz = timezone(timedelta(hours=3))
        now_msk = datetime.now(msk_tz)

    # Реальная дата старта (из timestamp)
    start_msk = datetime.fromtimestamp(start_ts, msk_tz)

    # Полночь старта (если старт был не в полночь, первый день начинается со следующей полуночи)
    start_midnight = start_msk.replace(hour=0, minute=0, second=0, microsecond=0)
    if start_msk.hour > 0 or start_msk.minute > 0 or start_msk.second > 0:
        start_midnight += timedelta(days=1)

    now_midnight = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)

    real_days_passed = (now_midnight - start_midnight).days
    if real_days_passed < 0:
        real_days_passed = 0

    # Дни РП: 365/24 ≈ 15.208 дней РП за 1 реальный день
    rp_days_passed = real_days_passed * (365 / 24)

    # Плавное движение внутри текущего реального дня
    hours_since_midnight = now_msk.hour + now_msk.minute / 60 + now_msk.second / 3600
    rp_hours_today = hours_since_midnight * (365 / 24 / 24)
    rp_days_total = rp_days_passed + (rp_hours_today / 24)

    start_date = datetime(base_year, 1, 1)
    rp_date = start_date + timedelta(days=rp_days_total)

    days_in_year = 365
    days_since_year_start = rp_days_total % days_in_year
    days_to_new_year = days_in_year - days_since_year_start

    return {
        "year": rp_date.year,
        "month": rp_date.month,
        "day": rp_date.day,
        "hour": rp_date.hour,
        "full": rp_date.strftime("%d.%m.%Y %H:%M"),
        "elapsed_hours": (now_msk - start_msk).total_seconds() / 3600,
        "rp_days": rp_days_total,
        "real_msk": now_msk.strftime("%d.%m.%Y %H:%M:%S"),
        "days_to_new_year": days_to_new_year,
    }


# =====================================================================
# РАЗБИВКА ДЛИННЫХ СООБЩЕНИЙ
# =====================================================================

def split_text(text: str, max_length: int = 4000) -> list[str]:
    if len(text) <= max_length:
        return [text]
    parts = []
    paragraphs = text.split("\n\n")
    current_part = ""
    for p in paragraphs:
        if len(p) > max_length:
            lines = p.split("\n")
            for line in lines:
                if len(current_part) + len(line) + 1 <= max_length:
                    current_part += line + "\n"
                else:
                    if current_part:
                        parts.append(current_part.strip())
                    current_part = line + "\n"
        else:
            if len(current_part) + len(p) + 2 <= max_length:
                current_part += p + "\n\n"
            else:
                if current_part:
                    parts.append(current_part.strip())
                current_part = p + "\n\n"
    if current_part:
        parts.append(current_part.strip())
    return parts


# =====================================================================
# WORLD BANK
# =====================================================================

WB_BASE_URL = "https://api.worldbank.org/v2"

COUNTRY_CODES = {
    "россия": "RUS", "рф": "RUS", "russia": "RUS",
    "сша": "USA", "соединенные штаты": "USA", "америка": "USA", "usa": "USA",
    "китай": "CHN", "china": "CHN",
    "германия": "DEU", "germany": "DEU",
    "франция": "FRA", "france": "FRA",
    "великобритания": "GBR", "англия": "GBR", "uk": "GBR",
    "япония": "JPN", "japan": "JPN",
    "индия": "IND", "india": "IND",
    "бразилия": "BRA", "brazil": "BRA",
    "украина": "UKR", "ukraine": "UKR",
    "беларусь": "BLR", "belarus": "BLR",
    "казахстан": "KAZ", "kazakhstan": "KAZ",
    "финляндия": "FIN", "finland": "FIN",
    "швеция": "SWE", "sweden": "SWE",
    "турция": "TUR", "turkey": "TUR",
    "болгария": "BGR", "bulgaria": "BGR",
    "сербия": "SRB", "serbia": "SRB",
}

INDICATOR_CODES = {
    "ввп": "NY.GDP.MKTP.CD", "gdp": "NY.GDP.MKTP.CD",
    "ввп на душу": "NY.GDP.PCAP.CD",
    "население": "SP.POP.TOTL",
    "инфляция": "FP.CPI.TOTL.ZG",
    "безработица": "SL.UEM.TOTL.ZS",
    "продолжительность жизни": "SP.DYN.LE00.IN",
}


def is_admin(user_id: int, username: str) -> bool:
    if user_id == ADMIN_ID:
        return True
    if username and ADMIN_USERNAME and username.lower() == ADMIN_USERNAME.lower():
        return True
    return False


def get_facts_chat_id() -> int:
    saved = db.get_setting("facts_chat_id")
    if saved:
        try:
            return int(saved)
        except ValueError:
            pass
    return FACTS_CHAT_ID


async def fetch_world_bank_data(country_code: str, indicator_code: str, year: int = None) -> str | None:
    url = f"{WB_BASE_URL}/country/{country_code}/indicator/{indicator_code}"
    params = {"format": "json", "per_page": 100}
    if year:
        params["date"] = str(year)
    else:
        params["MRV"] = 1
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, list) or len(data) < 2:
                return None
            records = data[1]
            if not records:
                return None
            valid_records = [r for r in records if r.get("value") is not None]
            if not valid_records:
                return None
            record = valid_records[0]
            value = record["value"]
            date = record["date"]
            indicator_name = record["indicator"]["value"]
            country_name = record["country"]["value"]
            if indicator_code in ["FP.CPI.TOTL.ZG", "SL.UEM.TOTL.ZS"]:
                formatted_value = f"{value:.1f}%"
            else:
                formatted_value = f"{value:,.0f}".replace(",", " ")
            return f"{indicator_name} для {country_name} ({date}): {formatted_value}"
    except Exception as e:
        print(f"⚠️ World Bank ошибка: {str(e)[:80]}")
        return None


async def get_economic_context(text: str) -> str | None:
    text_lower = text.lower()
    found_country_code = None
    for country_name, code in COUNTRY_CODES.items():
        if country_name in text_lower:
            found_country_code = code
            break
    if not found_country_code:
        return None
    found_indicator_code = None
    for indicator_name, code in INDICATOR_CODES.items():
        if indicator_name in text_lower:
            found_indicator_code = code
            break
    if not found_indicator_code:
        return None
    year = None
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if year_match:
        year = int(year_match.group(1))
    result = await fetch_world_bank_data(found_country_code, found_indicator_code, year)
    if result:
        return f"[ДАННЫЕ WORLD BANK]: {result}"
    return None


async def call_groq(primary_key: str, model: str, messages: list, temperature: float = 0.3) -> str | None:
    keys_to_try = [primary_key] + [k for k in GROQ_ALL_KEYS if k != primary_key]
    keys_to_try = [k for k in keys_to_try if k]
    for i, key in enumerate(keys_to_try):
        try:
            data = {"model": model, "temperature": temperature, "messages": messages}
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(GROQ_URL, headers=headers, json=data)
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                print(f"⚠️ Groq ключ #{i+1} ({model}): {resp.status_code}")
        except Exception as e:
            print(f"⚠️ Groq ошибка #{i+1}: {str(e)[:80]}")
    return None


async def call_gemini(messages: list, temperature: float = 0.3) -> str | None:
    if not GEMINI_KEY:
        return None
    system_prompt = ""
    contents = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt += msg["content"] + "\n"
        else:
            contents.append({"role": "user" if msg["role"] == "user" else "model",
                             "parts": [{"text": msg["content"]}]})
    payload = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if system_prompt:
        payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
    try:
        url = GEMINI_URL_TEMPLATE.format(key=GEMINI_KEY)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            print(f"⚠️ Gemini: {resp.status_code}")
    except Exception as e:
        print(f"⚠️ Gemini ошибка: {str(e)[:80]}")
    return None


async def search_web(query: str) -> str | None:
    if not OLLAMA_KEY:
        return None
    try:
        headers = {"Authorization": f"Bearer {OLLAMA_KEY}"}
        data = {"query": query, "max_results": 3}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(OLLAMA_URL, headers=headers, json=data)
            if resp.status_code != 200:
                return None
            results = resp.json().get("results", [])
            if not results:
                return None
            return "\n".join([f"• {r.get('title', 'Без названия')}: {r.get('content', '')[:300]}" for r in results[:3]])
    except Exception as e:
        print(f"⚠️ Ollama ошибка: {str(e)[:80]}")
        return None


async def maybe_summarize_history(chat_id: int, user_id: int):
    count = db.count_active_history(chat_id, user_id)
    if count < HISTORY_SUMMARIZE_THRESHOLD:
        return
    old_msgs = db.get_old_messages_for_summary(chat_id, user_id, batch=HISTORY_SUMMARIZE_BATCH)
    if not old_msgs:
        return
    dialog_text = "\n".join([f"{m['role']}: {m['content']}" for m in old_msgs])
    summary = await call_groq(
        GROQ_KEY_SUMMARY, MODEL_SUMMARY,
        [{"role": "system", "content": "Сожми диалог в 3-5 предложений. Сохрани все числа, имена, ключевые решения и факты. Не добавляй ничего от себя."},
         {"role": "user", "content": dialog_text}],
        temperature=0.3
    )
    if not summary:
        return
    db.archive_messages([m["id"] for m in old_msgs])
    db.add_history(chat_id, user_id, "system", f"[СЖАТАЯ ИСТОРИЯ] {summary}", is_summary=True)


async def save_fact_from_message(update: Update, text: str) -> bool:
    if not text.startswith("#"):
        return False
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""
    allowed_chat = get_facts_chat_id()
    if chat_id != allowed_chat and not is_admin(user_id, username):
        return False
    match = re.match(r"^#([\w\-]+)\s+(.+)$", text, re.DOTALL)
    if not match:
        return False
    tag = match.group(1).lower()
    fact_text = match.group(2).strip()
    year = None
    ym = re.search(r"\((\d{4})\)", fact_text)
    if ym:
        year = int(ym.group(1))
    else:
        ym = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", fact_text)
        if ym:
            year = int(ym.group(1))
    db.add_fact(tag, fact_text, user_id, username, year)
    db.add_history(chat_id, user_id, "user", text)
    return True


async def answer_question(update: Update, text: str) -> str:
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    if not db.check_cooldown(user_id, COOLDOWN_DIALOG):
        return None
    db.add_history(chat_id, user_id, "user", text)
    await maybe_summarize_history(chat_id, user_id)
    history = db.get_history(chat_id, user_id, limit=HISTORY_CONTEXT_LIMIT)

    wb_context = await get_economic_context(text)
    all_tags = db.get_all_tags()
    relevant_facts = []
    text_lower = text.lower()
    for t in all_tags:
        if t["tag"] in text_lower:
            relevant_facts.extend(db.get_facts_by_tag(t["tag"]))

    rp = get_rp_datetime()
    date_line = f"Сейчас в РП: {rp['day']} числа, {rp['month']} месяца, {rp['hour']}:00, {rp['year']} год. " if rp["year"] else ""

    system_parts = [
        f"Ты — аналитический РП-бот. {date_line}Отвечай кратко, по делу, только на русском.",
        "ПРИОРИТЕТ 1: Если есть ФАКТЫ ИЗ БАЗЫ — используй их.",
        "ПРИОРИТЕТ 2: Если в базе нет факта, но он есть в РЕАЛЬНОЙ ИСТОРИИ до 2020 года — используй его.",
        "ПРИОРИТЕТ 3: Если есть ДАННЫЕ WORLD BANK — используй их для точных цифр.",
        "🚨 КРИТИЧЕСКОЕ ПРАВИЛО: НЕ используй знания о событиях 2024–2026 годов. Если фактов в базе нет и в реальной истории до 2020 их тоже нет — скажи 'В базе знаний нет данных по этой теме. Добавь факты через #тег'.",
    ]

    if relevant_facts:
        facts_str = "\n".join([f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f['year'] else "") for f in relevant_facts[:20]])
        system_parts.append(f"\nФАКТЫ ИЗ БАЗЫ:\n{facts_str}")
    if wb_context:
        system_parts.append(f"\n{wb_context}")
    if not relevant_facts and not wb_context:
        system_parts.append("\nВ базе нет фактов. НЕ используй знания о 2024–2026. Скажи: 'В базе знаний нет данных. Добавь факты через #тег'.")

    system_prompt = "\n".join(system_parts)
    messages = [{"role": "system", "content": system_prompt}]
    for h in history[:-1]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": text})

    answer = await call_groq(GROQ_KEY_MAIN, MODEL_MAIN, messages, temperature=0.5)
    if not answer:
        answer = await call_gemini(messages, temperature=0.5)
    if not answer:
        return "❌ Все модели недоступны. Попробуй позже."
    db.add_history(chat_id, user_id, "assistant", answer)
    return answer


# =====================================================================
# ВЕРДИКТ ДЛЯ ВСЕХ (С ЛИМИТАМИ)
# =====================================================================

async def verdict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""
    is_adm = is_admin(user_id, username)

    cooldown = 15.0 if is_adm else 60.0
    if not db.check_cooldown(user_id, cooldown, is_verdict=True):
        await update.message.reply_text(f"⏳ Подожди {int(cooldown)} сек перед новым вердиктом.")
        return

    daily_limit = 100 if is_adm else 5
    today = datetime.utcnow().strftime("%Y-%m-%d")
    limit_key = f"verdict_limit_{user_id}_{today}"
    used_today = int(db.get_setting(limit_key, "0"))

    if used_today >= daily_limit:
        await update.message.reply_text(f"⏳ Дневной лимит вердиктов исчерпан ({daily_limit}/{daily_limit}). Попробуй завтра.")
        return

    raw = update.message.text or ""
    text = raw.replace("/verdict", "").strip()
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or ""
    if not text:
        await update.message.reply_text("❌ Используй: `/verdict текст ситуации [год]`", parse_mode="Markdown")
        return

    rp = get_rp_datetime()
    year = None
    ym = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", text)
    if ym:
        year = int(ym.group(1))
        text = text[:ym.start()].strip()
    else:
        year = rp["year"]

    date_context = ""
    if year and rp["month"] and rp["day"]:
        date_context = f"Сейчас в РП: {rp['day']} числа, {rp['month']} месяца, {rp['hour']}:00, {year} год.\n"
    elif year:
        date_context = f"Сейчас в РП: {year} год.\n"

    year_display = f" ({year})" if year else ""

    await update.message.reply_text("⏳ Готовлю детальный вердикт...")

    all_tags = db.get_all_tags()
    relevant_facts = []
    text_lower = text.lower()
    for t in all_tags:
        if t["tag"] in text_lower:
            relevant_facts.extend(db.get_facts_by_tag(t["tag"]))

    wb_context = await get_economic_context(text)
    facts_str = "\n".join([f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f['year'] else "") for f in relevant_facts[:30]]) if relevant_facts else "Нет сохранённых фактов."

    system_prompt = (
        f"Ты — строгий Гейм-Мастер геополитической РП-игры.\n"
        f"{date_context}\n"
        "ТВОЯ ГЛАВНАЯ ЗАДАЧА — проверить заявку на NRP, СВЕРИВ ЕЁ С ФАКТАМИ ИЗ БАЗЫ И С РЕАЛЬНОЙ ИСТОРИЕЙ. Только потом — вердикт.\n\n"
        "🔍 ПРОВЕРКА NRP:\n"
        "1. Прочитай ВСЕ факты из базы ниже.\n"
        "2. Сверь заявку с фактами и реальной историей:\n"
        "   • Если игрок пишет «промышленность выросла в 10 раз», а в базе НЕТ заводов, НО в реальности они были — допустимо.\n"
        "   • Если игрок пишет «армия 5 млн», а в базе НЕТ мобилизации, НО в реальности она была — допустимо.\n"
        "   • Если игрок пишет «500 кораблей за год», а в базе и реальности не было верфей — NRP.\n"
        "   • Если игрок пишет «технология X», а её не было в указанный год — NRP.\n"
        "3. Если NRP — ответь ТОЛЬКО так: '🚨 NRP: [причина]. Согласно базе и реальной истории, [что есть]. Для роста нужны: [какие действия].'\n\n"
        "✅ Если NRP нет — выдай полный вердикт по формату ниже.\n\n"
        "ФОРМАТ:\n"
        f"Вердикт: [Название]{year_display}\n\n"
        "Общая оценка: [Оценка/10] — краткое резюме.\n\n"
        "1. [Аспект]\nВердикт: [Оценка/10].\n• Плюс: [плюсы]\n• Риск: [риски]\n\n"
        "Итоговый вердикт:\n• [Аспект]: [Оценка/10]\n• Общий итог: [Оценка/10]\n\n"
        "Рекомендации:\n1. [Рекомендация]\n2. [Рекомендация]\n3. [Рекомендация]\n\n"
        "ПРАВИЛА:\n1. Только предоставленные факты.\n2. НЕ ВЫДУМЫВАЙ числа.\n3. NRP — только физически невозможное.\n\n"
        f"📚 ФАКТЫ ИЗ БАЗЫ:\n{facts_str}"
    )
    if wb_context:
        system_prompt += f"\n\n{wb_context}"

    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Ситуация: {text}"}]

    verdict = await call_groq(GROQ_KEY_VERDICT, MODEL_VERDICT, messages, temperature=0.6)
    if not verdict:
        verdict = await call_gemini(messages, temperature=0.6)
    if not verdict:
        await update.message.reply_text("❌ Не удалось получить вердикт. Попробуй позже.")
        return

    save_tag = "вердикт"
    for t in all_tags:
        if t["tag"] in text_lower:
            save_tag = t["tag"]
            break
    if not is_adm:
        save_tag = f"игрок_{save_tag}"

    fact_text = f"[ВЕРДИКТ] {text[:300]} → {verdict[:400]}"
    db.add_fact(save_tag, fact_text, user_id, username, year, is_verdict=True)
    db.set_setting(limit_key, str(used_today + 1))

    parts = split_text(verdict, max_length=4000)
    for part in parts:
        try:
            await update.message.reply_text(part, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(part)


# =====================================================================
# ОСНОВНОЙ ОБРАБОТЧИК
# =====================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    chat_id = update.message.chat.id

    if text.startswith("#"):
        saved = await save_fact_from_message(update, text)
        if saved and update.message.chat.type == "private":
            await update.message.reply_text("✅ Запомнил.")
        return

    is_private = update.message.chat.type == "private"
    is_reply_to_bot = (
        update.message.reply_to_message
        and update.message.reply_to_message.from_user
        and update.message.reply_to_message.from_user.id == context.bot.id
    )
    is_mention = (context.bot.username and f"@{context.bot.username.lower()}" in text.lower())

    if not (is_private or is_reply_to_bot or is_mention):
        return

    answer = await answer_question(update, text)
    if answer:
        for part in split_text(answer, max_length=4000):
            try:
                await update.message.reply_text(part, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(part)
