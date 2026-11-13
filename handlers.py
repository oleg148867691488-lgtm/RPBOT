"""
HANDLERS.PY — логика РП-бота: факты (#теги), вопросы, вердикты, массовый импорт.

Смысл тот же, что и раньше, но:
- БД и сеть не блокируют бота; запросы к БД, истории и World Bank идут параллельно.
- В промпт попадают самые НОВЫЕ факты (раньше обрезались как раз новые).
- Теги ищутся по целым словам, а не по подстроке.
- Ответы нейросети безопасно форматируются (больше никаких падений из-за _ и *).
- Нет дублирования вопроса при сжатии истории; сжатие идёт в фоне, после ответа.
- NRP-проверка не срабатывает на «OK, это не NRP».
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

import config as C
import database as db
from auth import is_staff
from llm import ask, search_web
from rptime import get_rp_datetime
from textutils import (
    Cooldown, esc, fit_texts, match_tags, parse_fact_line, shorten,
)
from tg import reply_llm, safe_reply, send_typing, thread_id_of
from worldbank import get_economic_context

log = logging.getLogger(__name__)

_dialog_cd = Cooldown()
_verdict_cd = Cooldown()
_busy_verdict: set = set()
_summarizing: set = set()
_bg_tasks: set = set()

_SKIP_TAG_PREFIXES = ("world_", "игрок_")


# =====================================================================
# ВСПОМОГАТЕЛЬНОЕ
# =====================================================================

def spawn(coro):
    """Фоновая задача с сохранением ссылки (иначе её может собрать сборщик мусора)."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)

    def _done(t):
        _bg_tasks.discard(t)
        if not t.cancelled() and t.exception():
            log.error("Фоновая задача упала", exc_info=t.exception())

    task.add_done_callback(_done)
    return task


def _int_setting(key: str, default: int = 0) -> int:
    try:
        return int(db.get_setting(key, default))
    except (TypeError, ValueError):
        return default


def facts_target():
    return _int_setting("facts_chat_id", C.FACTS_CHAT_ID), _int_setting("facts_thread_id", 0)


def world_target():
    return _int_setting("world_chat_id", 0), _int_setting("world_thread_id", 0)


def _dedupe(rows: list) -> list:
    seen, out = set(), []
    for r in rows:
        if r["text"] in seen:
            continue
        seen.add(r["text"])
        out.append(r)
    return out


def _fmt_fact(f: dict, with_tag: bool = True) -> str:
    base = f"- [{f['tag']}] {f['text']}" if with_tag else f"- {f['text']}"
    return base + (f" (год: {f['year']})" if f.get("year") else "")


def normal_tag_names(tag_rows: list) -> list:
    return [r["tag"] for r in tag_rows if not r["tag"].startswith(_SKIP_TAG_PREFIXES)]


def _rp_date_line() -> str:
    rp = get_rp_datetime()
    if not rp["year"]:
        return ""
    return (f"Сейчас в РП: {rp['day']} числа, {rp['month']} месяца, {rp['hour']}:00, "
            f"{rp['year']} год. Не упоминай события позже {rp['year']} года. ")


# =====================================================================
# NRP-ПРОВЕРКА
# =====================================================================

_MONEY_RE = re.compile(r"\d+\s*(млрд|трлн|млн|тыс)")
_NRP_WORDS = ("технология", "программа", "проект", "армия", "оружие", "завод", "флот",
              "танк", "самол", "ракет", "ядерн", "дивизи")


async def quick_nrp_check(text: str, year: int = None):
    """Возвращает причину NRP или None. Проверяются только факты с числами/военно-технической лексикой."""
    low = text.lower()
    if not (_MONEY_RE.search(low) or any(w in low for w in _NRP_WORDS)):
        return None
    prompt = (
        "Проверь факт на NRP (нарушение реализма) для РП 2010-х годов.\n"
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
        {"role": "user", "content": prompt},
    ]
    result = await ask("main", messages, temperature=0.1)
    if result and result.strip().upper().startswith("NRP"):
        return re.sub(r"^NRP\s*[:\-—]?\s*", "", result.strip(), flags=re.I) or "нереалистично"
    return None


# =====================================================================
# СОХРАНЕНИЕ ФАКТОВ
# =====================================================================

def _store_fact(tags: list, fact_text: str, user_id: int, username: str, year, is_world: bool) -> int:
    """Синхронно (в потоке БД): сохраняет факт по каждому тегу, возвращает сколько новых записей."""
    added = 0
    for tag in tags:
        save_tag = f"world_{tag}" if is_world else tag
        if db.add_fact(save_tag, fact_text, user_id, username, year):
            added += 1
    return added


async def save_fact_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    msg = update.message
    chat_id = msg.chat.id
    thread_id = thread_id_of(msg)
    user = msg.from_user

    facts_chat, facts_thread = facts_target()
    world_chat, world_thread = world_target()
    is_facts = bool(facts_chat) and chat_id == facts_chat and thread_id == facts_thread
    is_world = (bool(world_chat) and chat_id == world_chat
                and thread_id == world_thread and not is_facts)

    if not (is_facts or is_world or is_staff(user.id)):
        return False

    parsed = parse_fact_line(text)
    if not parsed:
        if msg.chat.type == "private":
            await safe_reply(msg, "ℹ️ Формат: <code>#тег текст факта (год)</code>")
        return False
    tags, fact_text, year = parsed

    added = await db.arun(_store_fact, tags, fact_text, user.id, user.username or "", year, is_world)

    nrp = await quick_nrp_check(fact_text, year) if added else None
    if added and not nrp:
        from actions import analyze_fact           # ИИ-ГМ сам считает влияние новости на защиту страны
        spawn(analyze_fact(msg, tags, fact_text, user))
    if nrp:
        warning = f"🚨 <b>NRP:</b> {esc(nrp)}"
        if C.RP_OWNER_USERNAME:
            warning += f"\n\n⚠️ @{esc(C.RP_OWNER_USERNAME)}, проверь."
        await safe_reply(msg, warning)
    elif msg.chat.type == "private":
        await safe_reply(msg, "✅ Запомнил." if added else "ℹ️ Такой факт уже есть в базе.")
    elif added:
        try:
            await msg.set_reaction("👍")
        except Exception:
            pass
    return True


# =====================================================================
# МАССОВЫЙ ИМПОРТ
# =====================================================================

def _store_bulk(lines: list, user_id: int, username: str, is_world: bool) -> int:
    saved = 0
    for line in lines:
        parsed = parse_fact_line(line)
        if not parsed:
            continue
        tags, fact_text, year = parsed
        if len(fact_text) < 10:
            continue
        if _store_fact(tags, fact_text, user_id, username, year, is_world):
            saved += 1
    return saved


async def bulk_import(update: Update, text: str, is_world: bool = False) -> int:
    user = update.message.from_user
    prompt = (
        "Разбей следующий текст на отдельные факты для РП-базы знаний.\n"
        "Каждый факт — одна строка в формате: #тег факт (год)\n"
        "Теги: #страна или #тема (например #россия, #нато, #экономика, #армия).\n"
        "Год в скобках в конце, если известен: (2010)\n"
        "Можно ставить несколько тегов в начале строки.\n"
        "НЕ добавляй ничего от себя. Только список фактов, каждая с новой строки.\n\n"
        f"ТЕКСТ:\n{text[:C.MAX_INPUT_CHARS]}"
    )
    messages = [
        {"role": "system", "content": "Ты — парсер фактов для РП. Разбиваешь текст на отдельные факты с тегами. Отвечаешь только списком фактов."},
        {"role": "user", "content": prompt},
    ]
    result = await ask("main", messages, temperature=0.2)
    if not result:
        return 0
    lines = [ln.strip() for ln in result.split("\n") if ln.strip().startswith("#")]
    return await db.arun(_store_bulk, lines, user.id, user.username or "", is_world)


# =====================================================================
# ИСТОРИЯ (сжатие в фоне)
# =====================================================================

async def maybe_summarize_history(chat_id: int, user_id: int):
    key = (chat_id, user_id)
    if key in _summarizing:
        return
    _summarizing.add(key)
    try:
        count = await db.arun(db.count_active_history, chat_id, user_id)
        if count < C.HISTORY_SUMMARIZE_THRESHOLD:
            return
        old = await db.arun(db.get_old_messages_for_summary, chat_id, user_id, C.HISTORY_SUMMARIZE_BATCH)
        if not old:
            return
        prev = await db.arun(db.get_summary, chat_id, user_id)
        dialog = "\n".join(f"{m['role']}: {shorten(m['content'], 1500)}" for m in old)
        if prev:
            dialog = f"[Предыдущее резюме]: {prev}\n\n{dialog}"
        summary = await ask("summary", [
            {"role": "system", "content": "Сожми диалог в 3-5 предложений. Сохрани все числа, имена, ключевые решения и факты. Не добавляй ничего от себя."},
            {"role": "user", "content": dialog},
        ], temperature=0.3)
        if summary:
            await db.arun(db.save_summary, chat_id, user_id, summary, [m["id"] for m in old])
    finally:
        _summarizing.discard(key)


# =====================================================================
# ОТВЕТ НА ВОПРОС
# =====================================================================

async def answer_question(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    msg = update.message
    chat_id, user_id = msg.chat.id, msg.from_user.id

    if _dialog_cd.hit(user_id, C.COOLDOWN_DIALOG):
        return None

    bot_un = context.bot.username or ""
    question = re.sub(rf"@{re.escape(bot_un)}", "", text, flags=re.I).strip() if bot_un else text
    question = question[:C.MAX_INPUT_CHARS]
    if not question:
        return None

    await send_typing(context.bot, chat_id, thread_id_of(msg))

    tag_rows = await db.arun(db.get_all_tags)
    matched = match_tags(normal_tag_names(tag_rows), question)

    async def load_facts():
        if not matched:
            return [], []
        f = await db.arun(db.get_recent_facts, matched, 12, False)
        v = await db.arun(db.get_recent_facts, matched, 3, True)
        return f, v

    (facts, verdicts), (summary, history), wb_context = await asyncio.gather(
        load_facts(),
        db.arun(db.get_context, chat_id, user_id, C.HISTORY_CONTEXT_LIMIT),
        get_economic_context(question),
    )
    # Бесплатный Groq принимает ~7-8 тыс. токенов/мин, поэтому режем промпт по бюджету
    # (берём самые НОВЫЕ записи, дальше выводим от старых к новым).
    fact_lines = fit_texts([_fmt_fact(f) for f in _dedupe(facts)], 4000, 500)[::-1]
    verdict_lines = fit_texts([f"- {v['text']}" for v in verdicts], 1000, 350)[::-1]

    date_line = _rp_date_line()
    parts = [f"Ты — аналитический РП-бот. {date_line}Отвечай кратко, по делу, только на русском."]

    if fact_lines or verdict_lines:
        block = "\n".join(fact_lines)
        parts.append(f"ФАКТЫ ИЗ БАЗЫ (используй ТОЛЬКО их):\n{block or 'нет обычных фактов'}")
        if verdict_lines:
            parts.append("ПРОШЛЫЕ ВЕРДИКТЫ ГМ:\n" + "\n".join(verdict_lines))
        if wb_context:
            parts.append(f"ДОПОЛНИТЕЛЬНО (World Bank):\n{wb_context}")
        parts.append("⚠️ Отвечай ТОЛЬКО на основе фактов. Если чего-то нет — скажи 'нет данных'.")
    elif wb_context:
        parts.append(f"В базе нет фактов, но есть World Bank:\n{wb_context}")
    else:
        found = await search_web(question)
        if found:
            parts.append(f"РЕЗУЛЬТАТЫ ПОИСКА:\n{found}\n\nПометь ответ как '(из интернета)'.")
        else:
            parts.append("Ответь на основе общих знаний. Пометь '(общие данные, не из базы)'.")

    messages = [{"role": "system", "content": "\n".join(parts)}]
    if summary:
        messages.append({"role": "system", "content": f"[СЖАТАЯ ИСТОРИЯ ДИАЛОГА] {shorten(summary, 1200)}"})
    hist, used = [], 0
    for h in reversed(history):                    # берём самые свежие реплики в рамках бюджета
        if h["role"] not in ("user", "assistant"):
            continue
        c = shorten(h["content"], 600)
        if used + len(c) > 3000:
            break
        hist.append({"role": h["role"], "content": c})
        used += len(c)
    messages.extend(reversed(hist))
    messages.append({"role": "user", "content": question})

    answer = await ask("main", messages, temperature=0.5)
    if not answer:
        return "❌ Все модели недоступны. Попробуй позже."

    await db.arun(db.add_exchange, chat_id, user_id, question, answer)
    spawn(maybe_summarize_history(chat_id, user_id))
    return answer


# =====================================================================
# ВЕРДИКТ
# =====================================================================

def _parse_verdict_input(raw: str, reply_text: str):
    """Возвращает (текст_ситуации, год, хештеги). Логика разбора — как в старой версии."""
    cmd_text = re.sub(r"^/verdict(@\w+)?", "", raw, flags=re.I).strip()
    cmd_text = re.sub(r"@\w+", "", cmd_text).strip()

    source = reply_text or cmd_text
    hashtags = [h.lower() for h in re.findall(r"#([\w\-]+)", source)]

    cmd_text = re.sub(r"#[\w\-]+", "", cmd_text).strip()
    reply_text = re.sub(r"#[\w\-]+", "", reply_text).strip() if reply_text else ""

    year = None
    if reply_text:
        text = reply_text
        m = re.search(r"\b(19\d{2}|20\d{2})\b", cmd_text)
        if m:
            year = int(m.group(1))
        else:
            m2 = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", reply_text)
            if m2:
                year = int(m2.group(1))
                text = reply_text[:m2.start()].strip()
    else:
        text = cmd_text
        m = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", text)
        if m:
            year = int(m.group(1))
            text = text[:m.start()].strip()
    return text, year, hashtags


def _build_verdict_prompt(date_context: str, year_display: str, facts_str: str,
                          verdicts_str: str, world_str: str, wb_context) -> str:
    prompt = (
        "Ты — строгий Гейм-Мастер геополитической РП-игры.\n"
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
        "4. ПОЛИТИЧЕСКИЕ РЕШЕНИЯ (передача командования, объединение стран, союзы, реформы) — это НЕ NRP.\n"
        "5. Если NRP — ответь ТОЛЬКО так: '🚨 NRP: [причина].'\n\n"
        "✅ Если NRP нет — выдай полный вердикт по формату ниже.\n\n"
        "🧮 УЧЁТ ПРОШЛЫХ ВЕРДИКТОВ:\n"
        "- Если в прошлых вердиктах уже выделялся бюджет — СУММИРУЙ его с новым.\n"
        "- Если прошлый вердикт ставил цель — упомяни, продолжается ли она.\n\n"
        "🌍 УЧЁТ МИРОВЫХ НОВОСТЕЙ:\n"
        "- Учитывай глобальную обстановку при оценке рисков.\n\n"
        "ФОРМАТ:\n"
        f"Вердикт: [Название]{year_display}\n\n"
        "Общая оценка: [Оценка/10] — краткое резюме.\n\n"
        "1. [Аспект]\nВердикт: [Оценка/10].\n• Плюс: [плюсы]\n• Риск: [риски]\n\n"
        "Итоговый вердикт:\n• [Аспект]: [Оценка/10]\n• Общий итог: [Оценка/10]\n"
        "• Учёт прошлого: [связь]\n"
        "• Мировая обстановка: [как влияет]\n\n"
        "Рекомендации:\n1. [Рекомендация]\n2. [Рекомендация]\n3. [Рекомендация]\n\n"
        "ПРАВИЛА:\n1. Только предоставленные факты.\n2. НЕ ВЫДУМЫВАЙ числа.\n3. NRP — только физически невозможное.\n\n"
        "═══════════════════════════════════════════\n"
        f"📚 ОБЫЧНЫЕ ФАКТЫ:\n{facts_str}\n\n"
        f"⚖️ ПРОШЛЫЕ ВЕРДИКТЫ:\n{verdicts_str}\n\n"
        f"🌍 МИРОВЫЕ НОВОСТИ:\n{world_str}"
    )
    if wb_context:
        prompt += f"\n\n{wb_context}"
    return prompt


async def verdict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    chat_id = msg.chat.id
    staff = is_staff(user.id)

    reply_text = ""
    if msg.reply_to_message:
        reply_text = msg.reply_to_message.text or msg.reply_to_message.caption or ""
    text, year, hashtags = _parse_verdict_input(msg.text or "", reply_text)

    if not text or len(text) < 5:
        await safe_reply(
            msg,
            "❌ Используй один из вариантов:\n"
            "• <code>/verdict текст ситуации [год]</code>\n"
            "• <code>/verdict</code> в ответ на сообщение\n"
            "• <code>/verdict 2010</code> в ответ на сообщение",
        )
        return

    if user.id in _busy_verdict:
        await safe_reply(msg, "⏳ Твой предыдущий вердикт ещё готовится.")
        return

    cooldown = C.COOLDOWN_VERDICT_STAFF if staff else C.COOLDOWN_VERDICT_PLAYER
    wait = _verdict_cd.hit(user.id, cooldown)
    if wait:
        await safe_reply(msg, f"⏳ Подожди ещё {int(wait) + 1} сек перед новым вердиктом.")
        return

    daily_limit = C.VERDICT_LIMIT_STAFF if staff else C.VERDICT_LIMIT_PLAYER
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    used = await db.arun(db.get_usage, user.id, today, "verdict")
    if used >= daily_limit:
        await safe_reply(msg, f"⏳ Дневной лимит вердиктов исчерпан ({daily_limit}/{daily_limit}). Попробуй завтра.")
        return

    _busy_verdict.add(user.id)
    status = None
    try:
        if len(text) > 2000:
            text = text[:2000] + "... [текст обрезан]"

        rp = get_rp_datetime()
        if not year:
            year = rp["year"]
        if year and rp["month"] and rp["day"]:
            date_context = f"Сейчас в РП: {rp['day']} числа, {rp['month']} месяца, {rp['hour']}:00, {year} год.\n"
        elif year:
            date_context = f"Сейчас в РП: {year} год.\n"
        else:
            date_context = ""
        year_display = f" ({year})" if year else ""

        status = await safe_reply(msg, "⏳ Готовлю детальный вердикт...")
        await send_typing(context.bot, chat_id, thread_id_of(msg))

        tag_rows = await db.arun(db.get_all_tags)
        names = normal_tag_names(tag_rows)
        matched = list(dict.fromkeys([t for t in names if t in hashtags] + match_tags(names, text)))

        (regular, prev_verdicts, world), wb_context = await asyncio.gather(
            asyncio.gather(
                db.arun(db.get_recent_facts, matched, 10, False),
                db.arun(db.get_recent_facts, matched, 5, True),
                db.arun(db.get_world_facts, 10),
            ),
            get_economic_context(text),
        )
        # Бюджеты символов (≈ 3,5 тыс. токенов на всё) — иначе Groq отвечает 413 «Request too large».
        facts_str = "\n".join(
            fit_texts([_fmt_fact(f) for f in _dedupe(regular)], 2600, 450)[::-1]
        ) or "Нет обычных фактов."
        verdicts_str = "\n".join(
            fit_texts([f"- (год {v['year'] or '?'}) {v['text']}" for v in prev_verdicts], 1000, 350)[::-1]
        ) or "Прошлых вердиктов нет."
        world_str = "\n".join(
            fit_texts([_fmt_fact({**w, "tag": w["tag"][len("world_"):]}) for w in world], 1000, 250)[::-1]
        ) or "Мировых новостей нет."
        if wb_context:
            wb_context = shorten(wb_context, 300)

        system_prompt = _build_verdict_prompt(
            date_context, year_display, facts_str, verdicts_str, world_str, wb_context)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Ситуация: {text}"},
        ]

        verdict = await ask("verdict", messages, temperature=0.6)
        if not verdict:
            await safe_reply(msg, "❌ Не удалось получить вердикт. Все модели недоступны. Попробуй позже.")
            _verdict_cd.reset(user.id)  # попытка не удалась — кулдаун не тратим
            return

        is_nrp = "🚨 NRP" in verdict[:80]
        if is_nrp and C.RP_OWNER_USERNAME:
            verdict += f"\n\n⚠️ @{C.RP_OWNER_USERNAME}, проверь на NRP."

        # Отказы по NRP в базу НЕ пишем: иначе они попадут в «прошлые вердикты» и исказят следующие.
        if not is_nrp:
            save_tag = matched[0] if matched else "вердикт"
            if not staff:
                save_tag = f"игрок_{save_tag}"
            fact_text = f"[ВЕРДИКТ] {text[:300]} → {verdict[:400]}"
            await db.arun(db.add_fact, save_tag, fact_text, user.id, user.username or "", year, True)
        await db.arun(db.inc_usage, user.id, today, "verdict")

        if len(verdict) > 10000:
            verdict = verdict[:10000] + "\n\n…[вердикт обрезан]"
        await reply_llm(msg, verdict)
    finally:
        _busy_verdict.discard(user.id)
        if status is not None:
            try:
                await status.delete()
            except Exception:
                pass


# =====================================================================
# ОСНОВНОЙ ОБРАБОТЧИК ТЕКСТА
# =====================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text or not msg.from_user or msg.from_user.is_bot:
        return
    text = msg.text

    if msg.chat.type == "private" and not text.startswith("#"):
        pend = context.user_data.get("pending_order")          # (режим, время, уже сказанное)
        if pend and time.time() - pend[1] < 600:
            context.user_data.pop("pending_order", None)
            from gamecmds import order_from_text
            await order_from_text(update, context, pend[0], (pend[2] + "\n" + text).strip())
            return

    if text.startswith("#"):
        await save_fact_from_message(update, context, text)
        return

    is_private = msg.chat.type == "private"
    reply_to = msg.reply_to_message
    is_reply_to_bot = bool(reply_to and reply_to.from_user and reply_to.from_user.id == context.bot.id)
    is_mention = bool(context.bot.username and f"@{context.bot.username.lower()}" in text.lower())

    if not (is_private or is_reply_to_bot or is_mention):
        return

    answer = await answer_question(update, context, text)
    if answer:
        await reply_llm(msg, answer)
