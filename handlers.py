"""
HANDLERS.PY — ЛОГИКА РП-БОТА (ФИНАЛ)
=====================================
- Время: 2 часа = месяц РП, 24 часа = год РП
- Авто-NRP при #тег (отметка владельца)
- Два чата: факты и мировые (приоритет у фактов)
- Кэш админов групп
- /bulk — массовый импорт
- /verdict: 25/день игрокам (30 сек), 100/день админам (15 сек)
- Ответ: база → World Bank → интернет → общие знания
"""

import re
import os
import json
import time
import httpx
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from config import (
    ADMIN_ID, ADMIN_USERNAME, FACTS_CHAT_ID,
    RP_OWNER_ID, RP_OWNER_USERNAME,
    GROQ_URL, GROQ_KEY_MAIN, GROQ_KEY_VERDICT, GROQ_KEY_SUMMARY, GROQ_ALL_KEYS,
    MODEL_MAIN, MODEL_VERDICT, MODEL_SUMMARY,
    GEMINI_KEY, GEMINI_URL_TEMPLATE,
    OLLAMA_KEY, OLLAMA_URL,
    COOLDOWN_DIALOG, COOLDOWN_VERDICT,
    HISTORY_CONTEXT_LIMIT, HISTORY_SUMMARIZE_THRESHOLD, HISTORY_SUMMARIZE_BATCH,
)
import database as db


# =====================================================================
# КЭШ АДМИНОВ ГРУПП
# =====================================================================

def get_chat_admin_ids(chat_id: int) -> list:
    saved = db.get_setting(f"chat_admins_{chat_id}")
    if saved:
        try:
            return json.loads(saved)
        except Exception:
            pass
    return []


def is_chat_admin(chat_id: int, user_id: int) -> bool:
    return user_id in get_chat_admin_ids(chat_id)


async def ensure_chat_admins(chat_id: int, context):
    if chat_id >= 0:
        return
    ts_key = f"chat_admins_ts_{chat_id}"
    last_ts = db.get_setting(ts_key, "0")
    try:
        if time.time() - float(last_ts) < 3600:
            return
    except Exception:
        pass
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [a.user.id for a in admins if not a.user.is_bot]
        db.set_setting(f"chat_admins_{chat_id}", json.dumps(admin_ids))
        db.set_setting(ts_key, str(time.time()))
        print(f"✅ Кэш админов {chat_id}: {len(admin_ids)} шт.")
    except Exception as e:
        print(f"⚠️ Не удалось получить админов {chat_id}: {e}")


# =====================================================================
# ПРОВЕРКА ПРАВ
# =====================================================================

def is_admin(user_id: int, username: str, chat_id: int = None) -> bool:
    if user_id == ADMIN_ID:
        return True
    if RP_OWNER_ID and user_id == RP_OWNER_ID:
        return True
    if username and ADMIN_USERNAME and username.lower() == ADMIN_USERNAME.lower():
        return True
    saved = db.get_setting("saved_admin_ids")
    if saved:
        try:
            ids = json.loads(saved)
            if user_id in ids:
                return True
        except Exception:
            pass
    if chat_id and is_chat_admin(chat_id, user_id):
        return True
    return False


def tag_in_text(tag: str, text: str) -> bool:
    text = text.lower()
    tag = tag.lower()
    if tag in text:
        return True
    if len(tag) > 3 and tag[:-1] in text:
        return True
    if len(tag) > 4 and tag[:-2] in text:
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


def get_world_chat_id() -> int:
    saved = db.get_setting("world_chat_id")
    if saved:
        try:
            return int(saved)
        except ValueError:
            pass
    return 0


# =====================================================================
# ВРЕМЯ РП
# =====================================================================

def get_rp_datetime() -> dict:
    saved_year = db.get_setting("rp_year")
    saved_start = db.get_setting("rp_start_time")
    saved_month = db.get_setting("rp_start_month", "1")
    saved_day = db.get_setting("rp_start_day", "1")

    empty = {"year": None, "month": None, "day": None, "hour": None,
             "full": None, "elapsed_hours": 0, "rp_days": 0, "real_msk": None,
             "days_to_new_year": None}
    if not saved_year or not saved_start:
        return empty
    try:
        base_year = int(saved_year)
        start_ts = float(saved_start)
        base_month = int(saved_month)
        base_day = int(saved_day)
    except (ValueError, TypeError):
        return empty

    try:
        import pytz
        msk_tz = pytz.timezone("Europe/Moscow")
        now_msk = datetime.now(msk_tz)
    except ImportError:
        from datetime import timezone
        msk_tz = timezone(timedelta(hours=3))
        now_msk = datetime.now(msk_tz)

    elapsed_real_hours = (now_msk.timestamp() - start_ts) / 3600
    if elapsed_real_hours < 0:
        elapsed_real_hours = 0

    speed = 365 / 24
    rp_days_total = elapsed_real_hours * speed

    start_date = datetime(base_year, base_month, base_day)
    rp_date = start_date + timedelta(days=rp_days_total)

    next_year_date = datetime(rp_date.year + 1, 1, 1)
    days_to_new_year = (next_year_date - rp_date).days

    return {
        "year": rp_date.year,
        "month": rp_date.month,
        "day": rp_date.day,
        "hour": rp_date.hour,
        "full": rp_date.strftime("%d.%m.%Y %H:%M"),
        "elapsed_hours": elapsed_real_hours,
        "rp_days": rp_days_total,
        "real_msk": now_msk.strftime("%d.%m.%Y %H:%M:%S"),
        "days_to_new_year": days_to_new_year,
    }


# =====================================================================
# РАЗБИВКА ТЕКСТА
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


# =====================================================================
# LLM
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


# =====================================================================
# БЫСТРЫЙ NRP
# =====================================================================

async def quick_nrp_check(text: str, year: int = None) -> str | None:
    text_lower = text.lower()
    has_money = bool(re.search(r"\d+\s*(млрд|трлн|млн|тыс)", text_lower))
    has_keywords = any(w in text_lower for w in ["технология", "программа", "проект", "армия", "оружие", "завод", "флот"])

    if not (has_money or has_keywords):
        return None

    prompt = (
        f"Проверь факт на NRP (нарушение реализма) для РП 2010-х годов.\n"
        f"Факт: {text}\n"
        + (f"Год: {year}\n" if year else "")
        + "NRP — это ТОЛЬКО физическая невозможность:\n"
        "- Технологии будущего (телепортация, варп-двигатели, лазерные винтовки 12 кг)\n"
        "- Нереалистичные числа (500 млн танков, 1 млрд солдат)\n"
        "- Мгновенное строительство (за день построил 100 заводов)\n"
        "ПОЛИТИЧЕСКИЕ РЕШЕНИЯ (кто кому что передал, кто с кем объединился) — это НЕ NRP. Это РП.\n"
        "Если факт физически невозможен — ответь ТОЛЬКО: 'NRP: [краткая причина]'.\n"
        "Если реалистичен — ответь ТОЛЬКО: 'OK'."
    )

    messages = [
        {"role": "system", "content": "Ты — строгий Гейм-Мастер. Проверяешь факты на реализм."},
        {"role": "user", "content": prompt}
    ]
    result = await call_groq(GROQ_KEY_MAIN, MODEL_MAIN, messages, temperature=0.1)
    if result and "NRP" in result.upper():
        return result.strip()
    return None


# =====================================================================
# ИСТОРИЯ
# =====================================================================

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


# =====================================================================
# СОХРАНЕНИЕ ФАКТОВ (ПРИОРИТЕТ У ФАКТОВ)
# =====================================================================

async def save_fact_from_message(update: Update, text: str) -> bool:
    if not text.startswith("#"):
        return False
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""

    facts_chat = get_facts_chat_id()
    world_chat = get_world_chat_id()
    is_facts = (chat_id == facts_chat)
    # Приоритет у фактов: если чат уже сохранён как факты, он НЕ считается мировым
    is_world = (chat_id == world_chat) and world_chat != 0 and not is_facts

    if not (is_facts or is_world or is_admin(user_id, username, chat_id)):
        return False

    match = re.match(r"^((?:#[\w\-]+\s*)+)(.+)$", text, re.DOTALL)
    if not match:
        return False

    tags = re.findall(r"#([\w\-]+)", match.group(1))
    fact_text = match.group(2).strip()
    if not tags:
        return False

    year = None
    ym = re.search(r"\((\d{4})\)", fact_text)
    if ym:
        year = int(ym.group(1))
    else:
        ym = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", fact_text)
        if ym:
            year = int(ym.group(1))

    for tag in tags:
        save_tag = f"world_{tag.lower()}" if is_world else tag.lower()
        db.add_fact(save_tag, fact_text, user_id, username, year)

    db.add_history(chat_id, user_id, "user", text)

    nrp = await quick_nrp_check(fact_text, year)
    if nrp:
        warning = f"🚨 **NRP:** {nrp}"
        if RP_OWNER_USERNAME:
            warning += f"\n\n⚠️ @{RP_OWNER_USERNAME}, проверь."
        await update.message.reply_text(warning, parse_mode="Markdown")
    else:
        if update.message.chat.type == "private":
            await update.message.reply_text("✅ Запомнил.")

    return True


# =====================================================================
# МАССОВЫЙ ИМПОРТ
# =====================================================================

async def bulk_import(update: Update, text: str, is_world: bool = False) -> int:
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""

    prompt = (
        f"Разбей следующий текст на отдельные факты для РП-базы знаний.\n"
        f"Каждый факт — одна строка в формате: #тег факт (год)\n"
        f"Теги: #страна или #тема (например #россия, #нато, #экономика, #армия).\n"
        f"Год в скобках в конце, если известен: (2010)\n"
        f"Можно ставить несколько тегов в начале строки.\n"
        f"НЕ добавляй ничего от себя. Только список фактов, каждая с новой строки.\n\n"
        f"ТЕКСТ:\n{text}"
    )

    messages = [
        {"role": "system", "content": "Ты — парсер фактов для РП. Разбиваешь текст на отдельные факты с тегами. Отвечаешь только списком фактов."},
        {"role": "user", "content": prompt}
    ]

    result = await call_groq(GROQ_KEY_MAIN, MODEL_MAIN, messages, temperature=0.2)
    if not result:
        result = await call_gemini(messages, temperature=0.2)
    if not result:
        return 0

    saved = 0
    for line in result.split("\n"):
        line = line.strip()
        if not line.startswith("#"):
            continue

        match = re.match(r"^((?:#[\w\-]+\s*)+)(.+)$", line, re.DOTALL)
        if not match:
            continue

        tags = re.findall(r"#([\w\-]+)", match.group(1))
        fact_text = match.group(2).strip()
        if not tags or len(fact_text) < 10:
            continue

        year = None
        ym = re.search(r"\((\d{4})\)", fact_text)
        if ym:
            year = int(ym.group(1))
        else:
            ym = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", fact_text)
            if ym:
                year = int(ym.group(1))

        for tag in tags:
            save_tag = f"world_{tag.lower()}" if is_world else tag.lower()
            db.add_fact(save_tag, fact_text, user_id, username, year)
        saved += 1

    return saved


# =====================================================================
# ОТВЕТ НА ВОПРОС (БАЗА → WB → ИНТЕРНЕТ → ОБЩИЕ ЗНАНИЯ)
# =====================================================================

async def answer_question(update: Update, text: str) -> str:
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    if not db.check_cooldown(user_id, COOLDOWN_DIALOG):
        return None
    db.add_history(chat_id, user_id, "user", text)
    await maybe_summarize_history(chat_id, user_id)
    history = db.get_history(chat_id, user_id, limit=HISTORY_CONTEXT_LIMIT)

    # ШАГ 1: факты из базы
    all_tags = db.get_all_tags()
    relevant_facts = []
    for t in all_tags:
        if not t["tag"].startswith("world_") and tag_in_text(t["tag"], text):
            relevant_facts.extend(db.get_facts_by_tag(t["tag"]))

    # ШАГ 2: World Bank
    wb_context = await get_economic_context(text)

    rp = get_rp_datetime()
    date_line = f"Сейчас в РП: {rp['day']} числа, {rp['month']} месяца, {rp['hour']}:00, {rp['year']} год. " if rp["year"] else ""

    system_parts = [
        f"Ты — аналитический РП-бот. {date_line}Отвечай кратко, по делу, только на русском.",
    ]

    # ШАГ 3: приоритет источников
    if relevant_facts:
        # Есть факты — используем ТОЛЬКО их
        facts_str = "\n".join([
            f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f['year'] else "")
            for f in relevant_facts[:20]
        ])
        system_parts.append(f"ФАКТЫ ИЗ БАЗЫ (используй ТОЛЬКО их):\n{facts_str}")
        if wb_context:
            system_parts.append(f"\nДОПОЛНИТЕЛЬНО (World Bank):\n{wb_context}")
        system_parts.append(
            "\n⚠️ Отвечай ТОЛЬКО на основе фактов из базы. "
            "Если чего-то нет — скажи 'нет данных по этому пункту'. "
            "НЕ выдумывай и НЕ используй свои знания."
        )

    elif wb_context:
        # Фактов нет, но есть World Bank
        system_parts.append(
            f"В базе нет фактов, но есть данные World Bank:\n{wb_context}\n\n"
            f"Используй их и укажи источник как 'World Bank'."
        )

    else:
        # ШАГ 4: идём в интернет
        search_result = await search_web(text)
        if search_result:
            system_parts.append(
                f"В базе нет фактов, использован поиск в интернете.\n"
                f"РЕЗУЛЬТАТЫ ПОИСКА:\n{search_result}\n\n"
                f"Ответь на основе этих результатов. Пометь ответ как '(из интернета)'."
            )
        else:
            # ШАГ 5: общие знания LLM
            system_parts.append(
                "В базе нет фактов, поиск в интернете не дал результатов.\n"
                "Ответь на основе общих знаний (до 2020 года). "
                "ОБЯЗАТЕЛЬНО пометь ответ как '(общие данные, не из базы)'. "
                "НЕ используй знания о событиях 2024–2026 годов."
            )

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
# ВЕРДИКТ (РЕПЛАЙ / КОМАНДА / ГОД)
# =====================================================================

async def verdict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""
    chat_id = update.message.chat.id
    is_adm = is_admin(user_id, username, chat_id)

    cooldown = 15.0 if is_adm else 30.0
    if not db.check_cooldown(user_id, cooldown, is_verdict=True):
        await update.message.reply_text(f"⏳ Подожди {int(cooldown)} сек перед новым вердиктом.")
        return

    daily_limit = 100 if is_adm else 25
    today = datetime.utcnow().strftime("%Y-%m-%d")
    limit_key = f"verdict_limit_{user_id}_{today}"
    used_today = int(db.get_setting(limit_key, "0"))

    if used_today >= daily_limit:
        await update.message.reply_text(f"⏳ Дневной лимит вердиктов исчерпан ({daily_limit}/{daily_limit}). Попробуй завтра.")
        return

    # === ПАРСИНГ: реплай или команда ===
    raw = update.message.text or ""
    cmd_text = raw.replace("/verdict", "").strip()
    reply_text = ""
    if update.message.reply_to_message and update.message.reply_to_message.text:
        reply_text = update.message.reply_to_message.text

    year = None
    if reply_text:
        text = reply_text
        ym = re.search(r"\b(19\d{2}|20\d{2})\b", cmd_text)
        if ym:
            year = int(ym.group(1))
        if not year:
            ym2 = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", reply_text)
            if ym2:
                year = int(ym2.group(1))
                text = reply_text[:ym2.start()].strip()
    else:
        text = cmd_text
        ym = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", text)
        if ym:
            year = int(ym.group(1))
            text = text[:ym.start()].strip()

    if not text or len(text) < 5:
        await update.message.reply_text(
            "❌ Используй один из вариантов:\n"
            "• `/verdict текст ситуации [год]`\n"
            "• `/verdict` в ответ на сообщение\n"
            "• `/verdict 2010` в ответ на сообщение",
            parse_mode="Markdown"
        )
        return

    rp = get_rp_datetime()
    if not year:
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
    world_facts = []
    for t in all_tags:
        if t["tag"].startswith("world_"):
            world_facts.extend(db.get_facts_by_tag(t["tag"]))
        elif tag_in_text(t["tag"], text):
            relevant_facts.extend(db.get_facts_by_tag(t["tag"]))

    regular_facts = []
    previous_verdicts = []
    for f in relevant_facts:
        if "[ВЕРДИКТ]" in f["text"]:
            previous_verdicts.append(f)
        else:
            regular_facts.append(f)

    regular_facts = regular_facts[:20]
    previous_verdicts = sorted(previous_verdicts, key=lambda x: x["created_at"], reverse=True)[:10]
    world_facts = sorted(world_facts, key=lambda x: x["created_at"], reverse=True)[:15]

    facts_str = "\n".join([
        f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f['year'] else "")
        for f in regular_facts
    ]) if regular_facts else "Нет обычных фактов."

    verdicts_str = "\n".join([
        f"- (год {f['year'] or '?'}) {f['text']}"
        for f in previous_verdicts
    ]) if previous_verdicts else "Прошлых вердиктов нет."

    world_str = "\n".join([
        f"- [{f['tag'].replace('world_', '')}] {f['text']}" + (f" (год: {f['year']})" if f['year'] else "")
        for f in world_facts
    ]) if world_facts else "Мировых новостей нет."

    wb_context = await get_economic_context(text)

    system_prompt = (
        f"Ты — строгий Гейм-Мастер геополитической РП-игры.\n"
        f"{date_context}\n"
        "ТВОЯ ГЛАВНАЯ ЗАДАЧА — проверить заявку на NRP, СВЕРИВ ЕЁ С ФАКТАМИ ИЗ БАЗЫ, "
        "С ПРОШЛЫМИ ВЕРДИКТАМИ, С МИРОВЫМИ НОВОСТЯМИ И С РЕАЛЬНОЙ ИСТОРИЕЙ.\n\n"
        "🔍 ПРОВЕРКА NRP:\n"
        "1. Прочитай ВСЕ факты, все прошлые вердикты и все мировые новости ниже.\n"
        "2. Сверь заявку с фактами, мировой обстановкой и реальной историей.\n"
        "3. NRP — это ТОЛЬКО физическая невозможность:\n"
        "   • Технологии будущего (телепортация, варп-двигатели, лазерные винтовки 12 кг)\n"
        "   • Нереалистичные числа (500 млн танков, 1 млрд солдат)\n"
        "   • Мгновенное строительство (за день построил 100 заводов)\n"
        "   • Анахронизмы (технология, которой не было в указанный год)\n"
        "4. ПОЛИТИЧЕСКИЕ РЕШЕНИЯ (передача командования, объединение стран, союзы, реформы) — это НЕ NRP. Это нормальный ход РП. Оценивай их с точки зрения рисков и последствий, но НЕ отклоняй как NRP.\n"
        "5. Если NRP — ответь ТОЛЬКО так: '🚨 NRP: [причина]. Согласно базе и реальной истории, [что есть]. Для роста нужны: [какие действия].'\n\n"
        "✅ Если NRP нет — выдай полный вердикт по формату ниже.\n\n"
        "🧮 УЧЁТ ПРОШЛЫХ ВЕРДИКТОВ:\n"
        "- Если в прошлых вердиктах уже выделялся бюджет — СУММИРУЙ его с новым.\n"
        "- Если прошлый вердикт ставил цель — упомяни, продолжается ли она.\n\n"
        "🌍 УЧЁТ МИРОВЫХ НОВОСТЕЙ:\n"
        "- Обязательно учитывай глобальную обстановку (войны, распады, союзы) при оценке рисков.\n\n"
        "ФОРМАТ:\n"
        f"Вердикт: [Название]{year_display}\n\n"
        "Общая оценка: [Оценка/10] — краткое резюме.\n\n"
        "1. [Аспект]\nВердикт: [Оценка/10].\n• Плюс: [плюсы]\n• Риск: [риски]\n\n"
        "Итоговый вердикт:\n• [Аспект]: [Оценка/10]\n• Общий итог: [Оценка/10]\n"
        "• Учёт прошлого: [связь с прошлыми вердиктами]\n"
        "• Мировая обстановка: [как влияет]\n\n"
        "Рекомендации:\n1. [Рекомендация]\n2. [Рекомендация]\n3. [Рекомендация]\n\n"
        "ПРАВИЛА:\n1. Только предоставленные факты и вердикты.\n2. НЕ ВЫДУМЫВАЙ числа.\n3. NRP — только физически невозможное.\n\n"
        "═══════════════════════════════════════════\n"
        f"📚 ОБЫЧНЫЕ ФАКТЫ ИЗ БАЗЫ:\n{facts_str}\n\n"
        f"⚖️ ПРОШЛЫЕ ВЕРДИКТЫ:\n{verdicts_str}\n\n"
        f"🌍 МИРОВЫЕ НОВОСТИ:\n{world_str}"
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

    if "🚨 NRP" in verdict and RP_OWNER_USERNAME:
        verdict += f"\n\n⚠️ @{RP_OWNER_USERNAME}, проверь на NRP."

    save_tag = "вердикт"
    for t in all_tags:
        if not t["tag"].startswith("world_") and tag_in_text(t["tag"], text):
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
        await save_fact_from_message(update, text)
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
