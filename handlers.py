"""
HANDLERS.PY — ЛОГИКА РП-БОТА (С РАЗБИВКОЙ ДЛИННЫХ СООБЩЕНИЙ)
=====================================
"""

import re
import httpx
import asyncio
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
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ РАЗБИВКИ ТЕКСТА
# =====================================================================

def split_text(text: str, max_length: int = 4000) -> list[str]:
    """Разбивает длинный текст на части, не превышающие max_length."""
    if len(text) <= max_length:
        return [text]

    parts = []
    # Сначала пытаемся резать по абзацам (двойной перенос)
    paragraphs = text.split("\n\n")
    current_part = ""

    for p in paragraphs:
        # Если один абзац сам по себе больше лимита, режем по строкам
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
# КОНСТАНТЫ WORLD BANK
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

# =====================================================================
# УТИЛИТЫ
# =====================================================================

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

# =====================================================================
# WORLD BANK
# =====================================================================

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
            if resp.status_code != 200: return None
            data = resp.json()
            if not isinstance(data, list) or len(data) < 2: return None
            records = data[1]
            if not records: return None
            valid_records = [r for r in records if r.get("value") is not None]
            if not valid_records: return None
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
    if not found_country_code: return None

    found_indicator_code = None
    for indicator_name, code in INDICATOR_CODES.items():
        if indicator_name in text_lower:
            found_indicator_code = code
            break
    if not found_indicator_code: return None

    year = None
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if year_match: year = int(year_match.group(1))

    result = await fetch_world_bank_data(found_country_code, found_indicator_code, year)
    if result: return f"[ДАННЫЕ WORLD BANK]: {result}"
    return None

# =====================================================================
# GROQ / GEMINI / OLLAMA
# =====================================================================

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
    if not GEMINI_KEY: return None
    system_prompt = ""
    contents = []
    for msg in messages:
        if msg["role"] == "system": system_prompt += msg["content"] + "\n"
        else: contents.append({"role": "user" if msg["role"] == "user" else "model", "parts": [{"text": msg["content"]}]})

    payload = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if system_prompt: payload["system_instruction"] = {"parts": [{"text": system_prompt}]}

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
    if not OLLAMA_KEY: return None
    try:
        headers = {"Authorization": f"Bearer {OLLAMA_KEY}"}
        data = {"query": query, "max_results": 3}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(OLLAMA_URL, headers=headers, json=data)
            if resp.status_code != 200: return None
            results = resp.json().get("results", [])
            if not results: return None
            return "\n".join([f"• {r.get('title', 'Без названия')}: {r.get('content', '')[:300]}" for r in results[:3]])
    except Exception as e:
        print(f"⚠️ Ollama ошибка: {str(e)[:80]}")
        return None

# =====================================================================
# ИСТОРИЯ
# =====================================================================

async def maybe_summarize_history(chat_id: int, user_id: int):
    count = db.count_active_history(chat_id, user_id)
    if count < HISTORY_SUMMARIZE_THRESHOLD: return
    old_msgs = db.get_old_messages_for_summary(chat_id, user_id, batch=HISTORY_SUMMARIZE_BATCH)
    if not old_msgs: return
    dialog_text = "\n".join([f"{m['role']}: {m['content']}" for m in old_msgs])
    summary = await call_groq(
        GROQ_KEY_SUMMARY, MODEL_SUMMARY,
        [{"role": "system", "content": "Сожми диалог в 3-5 предложений. Сохрани все числа, имена, ключевые решения и факты. Не добавляй ничего от себя."},
         {"role": "user", "content": dialog_text}],
        temperature=0.3
    )
    if not summary: return
    db.archive_messages([m["id"] for m in old_msgs])
    db.add_history(chat_id, user_id, "system", f"[СЖАТАЯ ИСТОРИЯ] {summary}", is_summary=True)

# =====================================================================
# СБОР ФАКТОВ
# =====================================================================

async def save_fact_from_message(update: Update, text: str) -> bool:
    if not text.startswith("#"): return False
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""
    allowed_chat = get_facts_chat_id()
    if chat_id != allowed_chat and not is_admin(user_id, username): return False
    match = re.match(r"^#([\w\-]+)\s+(.+)$", text, re.DOTALL)
    if not match: return False
    tag = match.group(1).lower()
    fact_text = match.group(2).strip()
    year = None
    ym = re.search(r"\((\d{4})\)", fact_text)
    if ym: year = int(ym.group(1))
    else:
        ym = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", fact_text)
        if ym: year = int(ym.group(1))
    db.add_fact(tag, fact_text, user_id, username, year)
    db.add_history(chat_id, user_id, "user", text)
    return True

# =====================================================================
# ОТВЕТ НА ВОПРОС
# =====================================================================

async def answer_question(update: Update, text: str) -> str:
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    if not db.check_cooldown(user_id, COOLDOWN_DIALOG): return None
    db.add_history(chat_id, user_id, "user", text)
    await maybe_summarize_history(chat_id, user_id)
    history = db.get_history(chat_id, user_id, limit=HISTORY_CONTEXT_LIMIT)

    wb_context = await get_economic_context(text)
    all_tags = db.get_all_tags()
    relevant_facts = []
    text_lower = text.lower()
    for t in all_tags:
        if t["tag"] in text_lower: relevant_facts.extend(db.get_facts_by_tag(t["tag"]))

    system_parts = [
        "Ты — аналитический РП-бот. Отвечай кратко, по делу, только на русском.",
        "ПРИОРИТЕТ 1: Если есть ФАКТЫ ИЗ БАЗЫ — используй ТОЛЬКО их.",
        "ПРИОРИТЕТ 2: Если есть ДАННЫЕ WORLD BANK — используй их для точных цифр.",
        "ПРИОРИТЕТ 3: Если ничего нет — используй общие знания, но пометь '(общие данные)'.",
    ]

    if relevant_facts:
        facts_str = "\n".join([f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f.get("year") else "") for f in relevant_facts[:20]])
        system_parts.append(f"\nФАКТЫ ИЗ БАЗЫ:\n{facts_str}")
    if wb_context: system_parts.append(f"\n{wb_context}")
    if not relevant_facts and not wb_context:
        search_result = await search_web(text)
        if search_result: system_parts.append(f"\nРЕЗУЛЬТАТЫ ПОИСКА:\n{search_result}")
        else: system_parts.append("\nВ базе нет фактов, и поиск не дал результатов. Скажи, что данных нет.")

    system_prompt = "\n".join(system_parts)
    messages = [{"role": "system", "content": system_prompt}]
    for h in history[:-1]: messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": text})

    answer = await call_groq(GROQ_KEY_MAIN, MODEL_MAIN, messages, temperature=0.5)
    if not answer: answer = await call_gemini(messages, temperature=0.5)
    if not answer: return "❌ Все модели недоступны. Попробуй позже."
    db.add_history(chat_id, user_id, "assistant", answer)
    return answer

# =====================================================================
# ДЕТАЛЬНЫЙ ВЕРДИКТ (/verdict)
# =====================================================================

async def verdict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""
    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Только админ может делать вердикты.")
        return
    if not db.check_cooldown(user_id, COOLDOWN_VERDICT, is_verdict=True):
        await update.message.reply_text(f"⏳ Подожди {int(COOLDOWN_VERDICT)} сек.")
        return

    raw = update.message.text or ""
    text = raw.replace("/verdict", "").strip()
    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or ""
    if not text:
        await update.message.reply_text("❌ Используй: `/verdict текст ситуации [год]`", parse_mode="Markdown")
        return

    year = None
    ym = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", text)
    if ym:
        year = int(ym.group(1))
        text = text[:ym.start()].strip()
    
    year_display = f" ({year})" if year else ""
    year_context = f"ГОД: {year}\n" if year else ""

    await update.message.reply_text("⏳ Готовлю детальный вердикт...")

    all_tags = db.get_all_tags()
    relevant_facts = []
    text_lower = text.lower()
    for t in all_tags:
        if t["tag"] in text_lower: relevant_facts.extend(db.get_facts_by_tag(t["tag"]))

    wb_context = await get_economic_context(text)

    facts_str = "\n".join([f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f.get("year") else "") for f in relevant_facts[:30]]) if relevant_facts else "Нет сохранённых фактов."

    system_prompt = (
        f"Ты — строгий и реалистичный Гейм-Мастер геополитической РП-игры.\n"
        f"{year_context}\n"
        "Твоя задача — разобрать ситуацию по пунктам и выдать детальный аналитический вердикт.\n\n"
        "ФОРМАТ ОТВЕТА (строго соблюдай структуру):\n"
        f"Вердикт: [Краткое название ситуации]{year_display}\n\n"
        "Общая оценка: [Оценка/10] — краткое резюме (1-2 предложения).\n\n"
        "---\n\n"
        "1. [Первый аспект/пункт ситуации]\n"
        "Вердикт: [Оценка/10].\n"
        "• Плюс: [плюсы]\n"
        "• Риск: [риски]\n"
        "• Оценка: [Оценка/10].\n\n"
        "1.1. [Подпункт]\n"
        "Вердикт: [Оценка/10].\n"
        "• Плюс: [плюсы]\n"
        "• Риск: [риски]\n"
        "• Оценка: [Оценка/10].\n\n"
        "Итог по [Первому аспекту]: [Оценка/10]. [Краткий вывод]\n\n"
        "---\n\n"
        "2. [Второй аспект/пункт ситуации]\n"
        "(Аналогично распиши плюсы, риски и оценку)\n\n"
        "---\n\n"
        "Итоговый вердикт:\n"
        "• [Аспект 1]: [Оценка/10]\n"
        "• [Аспект 2]: [Оценка/10]\n"
        "• Общий итог: [Оценка/10]\n\n"
        "Рекомендации:\n"
        "1. [Рекомендация 1]\n"
        "2. [Рекомендация 2]\n"
        "3. [Рекомендация 3]\n\n"
        "ПРАВИЛА:\n"
        "1. Используй ТОЛЬКО предоставленные факты и текст ситуации.\n"
        "2. НЕ ВЫДУМЫВАЙ числа (ВВП, армия, бюджеты) — если их нет в фактах, оценивай логически.\n"
        "3. Будь реалистичен и строг. Учитывай геополитический контекст.\n\n"
        f"ФАКТЫ ИЗ БАЗЫ:\n{facts_str}"
    )
    if wb_context: system_prompt += f"\n\n{wb_context}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Ситуация: {text}"},
    ]

    verdict = await call_groq(GROQ_KEY_VERDICT, MODEL_VERDICT, messages, temperature=0.6)
    if not verdict: verdict = await call_gemini(messages, temperature=0.6)
    if not verdict:
        await update.message.reply_text("❌ Не удалось получить вердикт. Попробуй позже.")
        return

    save_tag = "вердикт"
    for t in all_tags:
        if t["tag"] in text_lower:
            save_tag = t["tag"]
            break

    fact_text = f"[ВЕРДИКТ] {text[:300]} → {verdict[:400]}"
    db.add_fact(save_tag, fact_text, user_id, username, year, is_verdict=True)

    # === ИСПОЛЬЗУЕМ НАШУ ФУНКЦИЮ РАЗБИВКИ ===
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
    if not update.message or not update.message.text: return
    text = update.message.text
    chat_id = update.message.chat.id

    if text.startswith("#"):
        saved = await save_fact_from_message(update, text)
        if saved and update.message.chat.type == "private":
            await update.message.reply_text("✅ Запомнил.")
        return

    facts_chat_id = get_facts_chat_id()
    is_private = update.message.chat.type == "private"
    is_facts_chat = (chat_id == facts_chat_id)
    is_reply_to_bot = (update.message.reply_to_message and update.message.reply_to_message.from_user and update.message.reply_to_message.from_user.id == context.bot.id)
    is_mention = (context.bot.username and f"@{context.bot.username.lower()}" in text.lower())

    if not (is_private or is_facts_chat or is_reply_to_bot or is_mention):
        return

    answer = await answer_question(update, text)
    if answer:
        # === ТАКЖЕ РАЗБИВАЕМ И ОБЫЧНЫЕ ОТВЕТЫ ===
        for part in split_text(answer, max_length=4000):
            try:
                await update.message.reply_text(part, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(part)
