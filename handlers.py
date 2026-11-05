"""
HANDLERS.PY — ЛОГИКА РП-БОТА
=====================================
- Сбор фактов через #тег
- Вопросы с памятью и поиском
- Вердикты через deepseek-r1
- Fallback по 3 ключам Groq + Gemini
- Суммаризация истории через llama-3.1
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
# УТИЛИТЫ
# =====================================================================

def is_admin(user_id: int, username: str) -> bool:
    if user_id == ADMIN_ID:
        return True
    if username and ADMIN_USERNAME and username.lower() == ADMIN_USERNAME.lower():
        return True
    return False


def get_facts_chat_id() -> int:
    """Актуальный ID чата для фактов: из settings, иначе из ENV."""
    saved = db.get_setting("facts_chat_id")
    if saved:
        try:
            return int(saved)
        except ValueError:
            pass
    return FACTS_CHAT_ID


# =====================================================================
# GROQ С FALLBACK
# =====================================================================

async def call_groq(primary_key: str, model: str, messages: list, temperature: float = 0.3) -> str | None:
    """Пробует primary_key, при 429/ошибке — перебирает остальные ключи из GROQ_ALL_KEYS."""
    keys_to_try = [primary_key] + [k for k in GROQ_ALL_KEYS if k != primary_key]
    keys_to_try = [k for k in keys_to_try if k]  # убираем None

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


# =====================================================================
# GEMINI (крайний fallback)
# =====================================================================

async def call_gemini(messages: list, temperature: float = 0.3) -> str | None:
    if not GEMINI_KEY:
        return None

    system_prompt = ""
    contents = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt += msg["content"] + "\n"
        else:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

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


# =====================================================================
# OLLAMA (веб-поиск)
# =====================================================================

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
            return "\n".join([
                f"• {r.get('title', 'Без названия')}: {r.get('content', '')[:300]}"
                for r in results[:3]
            ])
    except Exception as e:
        print(f"⚠️ Ollama ошибка: {str(e)[:80]}")
        return None


# =====================================================================
# СУММАРИЗАЦИЯ ИСТОРИИ
# =====================================================================

async def maybe_summarize_history(chat_id: int, user_id: int):
    """Если активной истории слишком много — сжимает старые сообщения в резюме."""
    count = db.count_active_history(chat_id, user_id)
    if count < HISTORY_SUMMARIZE_THRESHOLD:
        return

    old_msgs = db.get_old_messages_for_summary(chat_id, user_id, batch=HISTORY_SUMMARIZE_BATCH)
    if not old_msgs:
        return

    dialog_text = "\n".join([f"{m['role']}: {m['content']}" for m in old_msgs])

    summary = await call_groq(
        GROQ_KEY_SUMMARY, MODEL_SUMMARY,
        [
            {"role": "system", "content": "Сожми диалог в 3-5 предложений. Сохрани все числа, имена, ключевые решения и факты. Не добавляй ничего от себя."},
            {"role": "user", "content": dialog_text}
        ],
        temperature=0.3
    )

    if not summary:
        return  # не удалось сжать — оставляем как есть

    # Архивируем старые, добавляем резюме
    db.archive_messages([m["id"] for m in old_msgs])
    db.add_history(chat_id, user_id, "system", f"[СЖАТАЯ ИСТОРИЯ] {summary}", is_summary=True)


# =====================================================================
# СБОР ФАКТОВ (#тег)
# =====================================================================

async def save_fact_from_message(update: Update, text: str) -> bool:
    """Парсит '#тег текст' и сохраняет. Возвращает True, если факт сохранён."""
    if not text.startswith("#"):
        return False

    # Проверка: пишем только в разрешённом чате или админом
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""

    allowed_chat = get_facts_chat_id()
    if chat_id != allowed_chat and not is_admin(user_id, username):
        return False

    # Парсинг "#тег текст"
    match = re.match(r"^#([\w\-]+)\s+(.+)$", text, re.DOTALL)
    if not match:
        return False

    tag = match.group(1).lower()
    fact_text = match.group(2).strip()

    # Ищем год в скобках (2002) или в конце
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


# =====================================================================
# ОТВЕТ НА ВОПРОС
# =====================================================================

async def answer_question(update: Update, text: str) -> str:
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""

    # Антиспам
    if not db.check_cooldown(user_id, COOLDOWN_DIALOG):
        return None

    # Сохраняем вопрос в историю
    db.add_history(chat_id, user_id, "user", text)

    # Сжимаем историю, если накопилось
    await maybe_summarize_history(chat_id, user_id)

    # Собираем контекст
    history = db.get_history(chat_id, user_id, limit=HISTORY_CONTEXT_LIMIT)

    # Ищем релевантные факты
    all_tags = db.get_all_tags()
    relevant_facts = []
    text_lower = text.lower()

    for t in all_tags:
        if t["tag"] in text_lower:
            facts = db.get_facts_by_tag(t["tag"])
            relevant_facts.extend(facts)

    # Формируем system prompt
    system_parts = [
        "Ты — аналитический РП-бот. Отвечай кратко, по делу, только на русском.",
        "Используй ТОЛЬКО предоставленные факты. НЕ ВЫДУМЫВАЙ числа, даты и события.",
        "Если фактов недостаточно — честно скажи об этом.",
    ]

    if relevant_facts:
        facts_str = "\n".join([
            f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f.get("year") else "")
            for f in relevant_facts[:20]
        ])
        system_parts.append(f"\nФАКТЫ ИЗ БАЗЫ:\n{facts_str}")
    else:
        # Фактов нет — пробуем поиск в интернете
        search_result = await search_web(text)
        if search_result:
            system_parts.append(f"\nРЕЗУЛЬТАТЫ ПОИСКА (используй осторожно, это не факты из базы):\n{search_result}")
        else:
            system_parts.append("\nВ базе нет фактов по этой теме, и поиск в интернете не дал результатов. Скажи, что данных нет.")

    system_prompt = "\n".join(system_parts)

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[:-1]:  # последнее сообщение — текущий вопрос, добавим ниже
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": text})

    # Пробуем Groq (с fallback), потом Gemini
    answer = await call_groq(GROQ_KEY_MAIN, MODEL_MAIN, messages, temperature=0.5)
    if not answer:
        answer = await call_gemini(messages, temperature=0.5)
    if not answer:
        return "❌ Все модели недоступны. Попробуй позже."

    db.add_history(chat_id, user_id, "assistant", answer)
    return answer


# =====================================================================
# ВЕРДИКТ (/verdict)
# =====================================================================

async def verdict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""
    chat_id = update.message.chat.id

    if not is_admin(user_id, username):
        await update.message.reply_text("❌ Только админ может делать вердикты.")
        return

    if not db.check_cooldown(user_id, COOLDOWN_VERDICT, is_verdict=True):
        await update.message.reply_text(f"⏳ Подожди {int(COOLDOWN_VERDICT)} сек перед новым вердиктом.")
        return

    # Текст: из reply или из команды
    raw = update.message.text or ""
    text = raw.replace("/verdict", "").strip()

    if not text and update.message.reply_to_message:
        text = update.message.reply_to_message.text or ""

    if not text:
        await update.message.reply_text(
            "❌ Используй: `/verdict текст ситуации [год]`\n"
            "Или ответь на сообщение: `/verdict [год]`",
            parse_mode="Markdown"
        )
        return

    # Извлекаем год (в конце текста)
    year = None
    ym = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", text)
    if ym:
        year = int(ym.group(1))
        text = text[:ym.start()].strip()

    await update.message.reply_text("⏳ Анализирую ситуацию и готовлю вердикт...")

    # Собираем ВСЕ релевантные факты (все теги, что упомянуты в тексте)
    all_tags = db.get_all_tags()
    relevant_facts = []
    text_lower = text.lower()
    for t in all_tags:
        if t["tag"] in text_lower:
            relevant_facts.extend(db.get_facts_by_tag(t["tag"]))

    facts_str = "\n".join([
        f"- [{f['tag']}] {f['text']}" + (f" (год: {f['year']})" if f.get("year") else "")
        for f in relevant_facts[:30]
    ]) if relevant_facts else "Нет сохранённых фактов по этой теме."

    system_prompt = (
        "Ты — Гейм-Мастер геополитической РП-игры. Делаешь вердикт по ситуации.\n\n"
        "ФОРМАТ ОТВЕТА (строго):\n"
        "**📊 ОЦЕНКА:** [0-100] — одно предложение почему.\n"
        "**⚠️ РИСКИ:**\n• [риск 1]\n• [риск 2]\n• [риск 3]\n"
        "**💡 ПРЕДЛОЖЕНИЯ:**\n• [предложение 1]\n• [предложение 2]\n• [предложение 3]\n\n"
        "ПРАВИЛА:\n"
        "1. Используй ТОЛЬКО предоставленные факты и текст ситуации.\n"
        "2. НЕ ВЫДУМЫВАЙ числа (ВВП, армия, бюджеты) — если их нет в фактах, не пиши.\n"
        "3. Учитывай современную геополитическую обстановку 2026 года (многополярный мир, санкции, СВО и т.д.).\n"
        "4. Если в тексте есть УЛЬТИМАТУМ (требования, сроки, угрозы) — добавь раздел "
        "**🎯 ОТВЕТ АДРЕСАТА:** [как вероятно ответит другая сторона, 2-3 предложения].\n\n"
        f"ФАКТЫ ИЗ БАЗЫ:\n{facts_str}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Ситуация: {text}" + (f"\nГод: {year}" if year else "")},
    ]

    verdict = await call_groq(GROQ_KEY_VERDICT, MODEL_VERDICT, messages, temperature=0.6)
    if not verdict:
        verdict = await call_gemini(messages, temperature=0.6)
    if not verdict:
        await update.message.reply_text("❌ Не удалось получить вердикт. Попробуй позже.")
        return

    # Определяем тег для сохранения: первый упомянутый тег, иначе "вердикт"
    save_tag = "вердикт"
    for t in all_tags:
        if t["tag"] in text_lower:
            save_tag = t["tag"]
            break

    # Сохраняем вердикт как факт
    fact_text = f"[ВЕРДИКТ] {text[:300]} → {verdict[:400]}"
    db.add_fact(save_tag, fact_text, user_id, username, year, is_verdict=True)

    header = f"⚖️ **ВЕРДИКТ**" + (f" (год: {year})" if year else "")
    await update.message.reply_text(f"{header}\n\n{verdict}", parse_mode="Markdown")


# =====================================================================
# ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА
# =====================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""

    # === СБОР ФАКТОВ (#тег текст) ===
    if text.startswith("#"):
        saved = await save_fact_from_message(update, text)
        if saved:
            # Тихо подтверждаем только в личке, в чате молчим
            if update.message.chat.type == "private":
                await update.message.reply_text("✅ Запомнил.")
        return

    # === ГДЕ ОТВЕЧАТЬ ===
    # В личке админа — отвечаем всегда
    # В чате фактов — отвечаем всегда
    # В остальных группах — только если упомянули "свит" или бота
    facts_chat_id = get_facts_chat_id()
    is_private = update.message.chat.type == "private"
    is_facts_chat = (chat_id == facts_chat_id)
    is_mentioned = (
        re.search(r"\b(свит|бот)\b", text, re.IGNORECASE)
        or (context.bot.username and context.bot.username.lower() in text.lower())
    )

    if not (is_private or is_facts_chat or is_mentioned):
        return

    # === ОТВЕТ НА ВОПРОС ===
    answer = await answer_question(update, text)
    if answer:
        await update.message.reply_text(answer)
