"""
COMMANDS.PY — ВСЕ КОМАНДЫ БОТА (ПОЛНАЯ ВЕРСИЯ)
===============================================
Публичные + Админские + Скрытые для тестов.
Содержит /tension для мировой напряжённости.
"""

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import (
    ADMIN_ID,
    saved_chats,
    save_saved_chats,
    bot_stopped
)
from history import (
    save_country,
    save_year,
    get_country,
    get_year,
    get_economy,
    init_economy,
    clear_all_history,
    update_economy
)
from news import generate_news, send_news_to_chat
from ai_manager import ai

# =====================================================================
# ПРОВЕРКА АДМИНА
# =====================================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# =====================================================================
# /START — ПРИВЕТСТВИЕ (ПУБЛИЧНАЯ)
# =====================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if is_admin(user_id):
        text = (
            "⚠️ *ДИСКЛЕЙМЕР*\n\n"
            "Этот бот — игровая историческая симуляция \\(RP\\)\\.\n"
            "Все события вымышлены и происходят в рамках игры\\.\n\n"
            "👑 *Админ\\-панель:*\n"
            "/country \\[страна\\] — выбрать страну\n"
            "/year \\[год\\] — установить год\n"
            "/research \\[страна\\] — исследовать страну\n"
            "/status — статус бота\n"
            "/tension — мировая напряжённость\n"
            "/savechatnews — новостной чат\n"
            "/savechatwar — военный чат\n"
            "/savechatoon — чат ООН\n"
            "/stop — пауза\n"
            "/start\\_bot — продолжить\n"
            "/wipe — полный сброс\n"
            "/admin — все команды для тестов"
        )
    else:
        text = (
            "⚠️ *ДИСКЛЕЙМЕР*\n\n"
            "Этот бот — игровая историческая симуляция \\(RP\\)\\.\n"
            "Все события вымышлены и происходят в рамках игры\\.\n\n"
            "🤖 Бот управляет страной автоматически\\.\n"
            "Вы можете влиять через чаты:\n"
            "• Пишите новости с \\#НазваниеСтраны\n"
            "• Предлагайте сделки и союзы\n"
            "• Бот сам принимает решения\n\n"
            "📌 Доступные команды:\n"
            "/start — информация\n"
            "/tension — мировая напряжённость\n\n"
            "📌 Бот отвечает когда его тегают \\(@botname\\)"
        )
    
    await update.message.reply_text(text, parse_mode="MarkdownV2")

# =====================================================================
# /COUNTRY — ВЫБОР СТРАНЫ (АДМИН)
# =====================================================================

async def country_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите страну\\. Пример: `/country Россия`", parse_mode="MarkdownV2")
        return
    
    country = " ".join(args)
    user_id = update.message.from_user.id
    
    save_country(user_id, country)
    init_economy(user_id)
    
    await update.message.reply_text(f"✅ Страна изменена на: *{country}*\n🔍 Бот исследует {country}\\.\\.\\.", parse_mode="MarkdownV2")
    
    try:
        from decision_engine import world, CountryProfile
        from economy import init_country_economy
        
        info = await ai.research_country(country)
        profile = CountryProfile(country, info)
        world.country_profiles[country] = profile
        await init_country_economy(user_id, country)
        
        await update.message.reply_text(
            f"🌍 *{country} — готово\\!*\n\n📊 Профиль: *{profile.profile_type}*\n💪 {profile.bonuses.get('description', '')}\n⚠️ {profile.restrictions.get('description', '')}",
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Исследование не удалось: {str(e)[:100]}\nБот использует базовую стратегию\\.", parse_mode="MarkdownV2")

# =====================================================================
# /YEAR — УСТАНОВКА ГОДА (АДМИН)
# =====================================================================

async def year_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите год\\. Пример: `/year 1936`", parse_mode="MarkdownV2")
        return
    
    try:
        year = int(args[0])
        if year < 1800 or year > 2100:
            await update.message.reply_text("❌ Год должен быть между 1800 и 2100\\.")
            return
        
        save_year(update.message.from_user.id, year)
        from decision_engine import world
        world.year = year
        
        await update.message.reply_text(f"✅ Год изменён на: *{year}*\n📅 Месяц: *{world.month}*", parse_mode="MarkdownV2")
    except ValueError:
        await update.message.reply_text("❌ Введите число\\. Пример: `/year 1936`", parse_mode="MarkdownV2")

# =====================================================================
# /RESEARCH — ИССЛЕДОВАТЬ СТРАНУ (АДМИН)
# =====================================================================

async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите страну\\. Пример: `/research Франция`", parse_mode="MarkdownV2")
        return
    
    country = " ".join(args)
    await update.message.reply_text(f"🔍 Исследую *{country}*\\.\\.\\. Это займёт 15\\-20 секунд\\.", parse_mode="MarkdownV2")
    
    try:
        info = await ai.research_country(country)
        summary = info.get("summary", "Информация не найдена")
        
        if len(summary) > 4000:
            from utils import split_text
            parts = split_text(summary, 3800)
            for part in parts:
                await update.message.reply_text(part)
                await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(f"🌍 *{country}:*\n\n{summary}", parse_mode="MarkdownV2")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")

# =====================================================================
# /STATUS — СТАТУС БОТА (АДМИН)
# =====================================================================

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    from decision_engine import world
    
    country = get_country(ADMIN_ID) or "не выбрана"
    year = get_year(ADMIN_ID) or "?"
    economy = get_economy(ADMIN_ID)
    profile = world.country_profiles.get(country)
    power = world.get_power_rating(country)
    
    text = (
        f"📊 *СТАТУС БОТА*\n\n"
        f"🌍 Страна: *{country}*\n"
        f"📅 Год: *{year}* \\| Месяц: *{world.month}*\n"
        f"🔄 Ходов: *{world.turn}*\n"
        f"⏸️ Остановлен: *{'да' if bot_stopped else 'нет'}*\n"
        f"💪 Сила: *{power:.1f}/100*\n"
        f"🌍 Напряжённость: *{world.world_tension:.1f}%*\n"
    )
    
    if profile:
        text += f"\n📊 Профиль: *{profile.profile_type}*\n"
    
    if economy:
        text += f"\n💰 Бюджет: *${economy['budget']:,}*\n🔩 Сталь: {economy['steel']} \\| 🛢️ Нефть: {economy['oil']}\n🌾 Зерно: {economy['grain']} \\| 🥇 Золото: {economy['gold']}\n"
    
    active_wars = [w for w in world.wars.values() if w.get('status') == 'active']
    text += f"\n⚔️ Активных войн: *{len(active_wars)}*\n"
    for war in active_wars[:3]:
        text += f"• {war['attacker']} vs {war['defender']}\n"
    
    allies = world.alliances.get(country, [])
    text += f"\n🤝 Союзников: *{len(allies)}*\n"
    if allies:
        text += f"• {', '.join(allies[:5])}\n"
    
    text += f"\n🤖 Groq вызовов: *{ai.stats['groq_calls']}*\n🔍 Gemini: *{ai.stats['gemini_calls']}* \\| Ollama: *{ai.stats['ollama_calls']}*\n"
    
    await update.message.reply_text(text, parse_mode="MarkdownV2")

# =====================================================================
# /TENSION — МИРОВАЯ НАПРЯЖЁННОСТЬ (ПУБЛИЧНАЯ)
# =====================================================================

async def tension_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from decision_engine import world
    
    await update.message.reply_text("🌍 Анализирую мировую напряжённость\\.\\.\\.", parse_mode="MarkdownV2")
    
    data = await world.calculate_world_tension_ai()
    
    tension = data.get('tension', 0)
    status = data.get('status', 'Неизвестно')
    description = data.get('description', '')
    trend = data.get('trend', 'stable')
    
    trend_emoji = {"rising": "📈", "stable": "📊", "falling": "📉"}.get(trend, "📊")
    
    if tension < 25:
        color, world_status = "🟢", "МИР"
    elif tension < 50:
        color, world_status = "🟡", "НАПРЯЖЕНИЕ"
    elif tension < 75:
        color, world_status = "🟠", "ОПАСНОСТЬ"
    elif tension < 90:
        color, world_status = "🔴", "КРИЗИС"
    else:
        color, world_status = "⚫", "АПОКАЛИПСИС"
    
    bar_length = 20
    filled = int(bar_length * tension / 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    can_justify = data.get('can_justify_war', False)
    can_intervene = data.get('can_intervene', False)
    can_nukes = data.get('can_use_nukes', False)
    
    text = (
        f"{color} *МИРОВАЯ НАПРЯЖЁННОСТЬ*\n\n"
        fr"\[{bar}\] *{tension:.1f}%*\n"
        f"{trend_emoji} Тренд: *{trend}*\n\n"
        f"📊 Статус: *{world_status}*\n"
        f"📝 {description}\n\n"
        f"📌 *Текущие правила:*\n"
        f"• Оправдание войны: *{'✅ ДА' if can_justify else '❌ НЕТ'}*\n"
        f"• Вмешательство: *{'✅ ДА' if can_intervene else '❌ НЕТ'}*\n"
        f"• Ядерное оружие: *{'✅ РАЗРЕШЕНО' if can_nukes else '❌ ЗАПРЕЩЕНО'}*\n\n"
        f"💡 Чем выше напряжённость — тем легче оправдать войну\\!"
    )
    
    await update.message.reply_text(text, parse_mode="MarkdownV2")

# =====================================================================
# /SAVECHATNEWS — НОВОСТНОЙ ЧАТ (АДМИН)
# =====================================================================

async def savechatnews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    saved_chats["news"] = update.message.chat.id
    save_saved_chats(saved_chats)
    
    await update.message.reply_text("📰 *Новостной чат сохранён\\!*\n\nСюда будут приходить:\n• Новости каждые 15 минут\n• Анализ новостей игроков\n• Ответы на вопросы", parse_mode="MarkdownV2")

# =====================================================================
# /SAVECHATWAR — ВОЕННЫЙ ЧАТ (АДМИН)
# =====================================================================

async def savechatwar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    saved_chats["war"] = update.message.chat.id
    save_saved_chats(saved_chats)
    
    await update.message.reply_text("⚔️ *Военный чат сохранён\\!*\n\nСюда будут приходить:\n• Объявления о войнах\n• Ходы сражений\n• Результаты битв", parse_mode="MarkdownV2")

# =====================================================================
# /SAVECHATOON — ЧАТ ООН (АДМИН)
# =====================================================================

async def savechatoon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    saved_chats["un"] = update.message.chat.id
    save_saved_chats(saved_chats)
    
    await update.message.reply_text("🏛️ *Чат ООН сохранён\\!*\n\nСюда будут приходить:\n• Резолюции\n• Голосования\n• Санкции и союзы", parse_mode="MarkdownV2")

# =====================================================================
# /STOP — ОСТАНОВИТЬ БОТА (АДМИН)
# =====================================================================

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    import config
    config.bot_stopped = True
    
    await update.message.reply_text("🛑 *Бот остановлен\\.*\n\n• Новости не генерируются\n• Решения не принимаются\n• Сообщения игнорируются\n\nДля запуска: `/start\\_bot`", parse_mode="MarkdownV2")

# =====================================================================
# /START_BOT — ЗАПУСТИТЬ БОТА (АДМИН)
# =====================================================================

async def start_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    import config
    config.bot_stopped = False
    
    await update.message.reply_text("✅ *Бот запущен\\!*\n\n• Новости генерируются\n• Решения принимаются\n• Бот отвечает на сообщения", parse_mode="MarkdownV2")

# =====================================================================
# /WIPE — ПОЛНЫЙ СБРОС (АДМИН)
# =====================================================================

async def wipe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ Доступ запрещён\\.")
        return
    
    clear_all_history()
    save_saved_chats({"news": None, "war": None, "un": None})
    saved_chats["news"] = None
    saved_chats["war"] = None
    saved_chats["un"] = None
    
    from decision_engine import world
    world.countries.clear()
    world.country_profiles.clear()
    world.wars.clear()
    world.alliances.clear()
    world.sanctions.clear()
    world.marionettes.clear()
    world.annexed.clear()
    world.news_history.clear()
    world.turn = 0
    world.world_tension = 0.0
    
    for key in world.technologies:
        world.technologies[key] = 1 if key != "nuclear" else 0
    for key in world.infrastructure:
        world.infrastructure[key] = 1 if key != "ports" else 0
    
    import config
    config.bot_stopped = False
    
    await update.message.reply_text("🗑️ *ВАЙП ВЫПОЛНЕН\\!*\n\n✅ Всё сброшено\n📌 Используйте:\n`/country \\[страна\\]` — выбрать страну\n`/year \\[год\\]` — установить год\n`/savechatnews` — настроить чаты", parse_mode="MarkdownV2")

# =====================================================================
# СКРЫТЫЕ АДМИН-КОМАНДЫ ДЛЯ ТЕСТОВ
# =====================================================================

async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    text = (
        "🔧 *АДМИН-ПАНЕЛЬ*\n\n"
        "*Основные:*\n"
        "/country \\[страна\\] — выбрать страну\n"
        "/year \\[год\\] — установить год\n"
        "/research \\[страна\\] — исследовать\n"
        "/status — статус бота\n"
        "/tension — напряжённость\n"
        "/wipe — полный сброс\n"
        "/stop \\| /start\\_bot — пауза\n\n"
        "*Тесты:*\n"
        "/force\\_news — сгенерировать новость\n"
        "/force\\_decision — цикл решений\n"
        "/force\\_war \\[стр\\] \\[причина\\] — тест войны\n"
        "/force\\_peace — завершить войны\n"
        "/force\\_trade \\[рес\\] \\[кол\\] — продать\n"
        "/force\\_ally \\[стр\\] — союз\n"
        "/force\\_sanctions \\[стр\\] — санкции\n\n"
        "*Читы:*\n"
        "/addmoney \\[сумма\\] — деньги\n"
        "/setpower \\[0\\-100\\] — сила\n\n"
        "*Отладка:*\n"
        "/debug\\_ai \\[вопрос\\] — спросить ИИ\n"
        "/debug\\_world — состояние мира"
    )
    
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def force_news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    await update.message.reply_text("🔄 Генерирую\\.\\.\\.", parse_mode="MarkdownV2")
    news = await generate_news()
    await send_news_to_chat(context.bot, news)
    await update.message.reply_text(f"✅ Отправлено:\n\n{news}")


async def force_decision_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    await update.message.reply_text("🧠 Запускаю\\.\\.\\.", parse_mode="MarkdownV2")
    from decision_engine import decision_loop
    await decision_loop(context)
    await update.message.reply_text("✅ Цикл завершён")


async def force_war_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ `/force_war Страна Причина`", parse_mode="MarkdownV2")
        return
    
    from war import declare_war_command
    await declare_war_command(update, context, args)
    await update.message.reply_text(f"⚔️ Война с *{args[0]}* инициирована", parse_mode="MarkdownV2")


async def force_peace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    from war import active_wars
    count = len(active_wars)
    active_wars.clear()
    await update.message.reply_text(f"🕊️ Завершено войн: *{count}*", parse_mode="MarkdownV2")


async def force_trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ `/force_trade steel 500`", parse_mode="MarkdownV2")
        return
    
    resource = args[0].lower()
    try:
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Количество — число")
        return
    
    from economy import PRICES
    
    if resource not in PRICES:
        await update.message.reply_text(f"❌ Ресурс {resource} не найден")
        return
    
    eco = get_economy(ADMIN_ID)
    if not eco or eco.get(resource, 0) < amount:
        await update.message.reply_text(f"❌ Недостаточно {resource}")
        return
    
    price = PRICES[resource] * amount
    update_economy(ADMIN_ID, budget=eco['budget'] + price, **{resource: eco[resource] - amount})
    await update.message.reply_text(f"✅ Продано {amount} {resource} за ${price:,}")


async def force_ally_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ `/force_ally Германия`", parse_mode="MarkdownV2")
        return
    
    target = args[0]
    from decision_engine import world
    country = get_country(ADMIN_ID) or "Швейцария"
    
    world.alliances.setdefault(country, []).append(target)
    world.alliances.setdefault(target, []).append(country)
    
    await update.message.reply_text(f"🤝 Союз с *{target}* заключён", parse_mode="MarkdownV2")


async def force_sanctions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ `/force_sanctions Китай`", parse_mode="MarkdownV2")
        return
    
    target = args[0]
    from decision_engine import world
    country = get_country(ADMIN_ID) or "Швейцария"
    
    world.sanctions.setdefault(target, []).append(country)
    await update.message.reply_text(f"🚫 Санкции против *{target}*", parse_mode="MarkdownV2")


async def add_money_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ `/addmoney 1000000`", parse_mode="MarkdownV2")
        return
    
    try:
        amount = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Сумма — число")
        return
    
    eco = get_economy(ADMIN_ID)
    if eco:
        update_economy(ADMIN_ID, budget=eco['budget'] + amount)
        await update.message.reply_text(f"💰 Добавлено *${amount:,}*", parse_mode="MarkdownV2")


async def set_power_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ `/setpower 85`", parse_mode="MarkdownV2")
        return
    
    try:
        power = float(args[0])
    except ValueError:
        await update.message.reply_text("❌ Число 0-100")
        return
    
    from decision_engine import world
    country = get_country(ADMIN_ID) or "Швейцария"
    
    if country in world.countries:
        world.countries[country]["army_size"] = int(power * 10000)
        world.countries[country]["gdp"] = power * 100_000_000_000
        await update.message.reply_text(f"💪 Сила *{country}* = *{power}/100*", parse_mode="MarkdownV2")


async def debug_ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ `/debug_ai вопрос`", parse_mode="MarkdownV2")
        return
    
    question = " ".join(args)
    await update.message.reply_text("🤔 Думаю\\.\\.\\.", parse_mode="MarkdownV2")
    
    answer = await ai.ask_groq(question, system_prompt=ai.get_rp_system_prompt(), temperature=0.7, max_tokens=500)
    await update.message.reply_text(f"🤖 {answer}")


async def debug_world_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return
    
    from decision_engine import world
    
    text = "🌍 *СОСТОЯНИЕ МИРА*\n\n"
    text += f"Стран: *{len(world.countries)}*\n"
    
    for name in list(world.countries.keys())[:10]:
        power = world.get_power_rating(name)
        text += f"• {name}: сила {power:.1f}/100\n"
    
    text += f"\n⚔️ Войн: *{len(world.wars)}*\n"
    for war in list(world.wars.values())[:5]:
        text += f"• {war['attacker']} vs {war['defender']}: {war['status']}\n"
    
    text += f"\n🤝 Союзов: *{sum(len(v) for v in world.alliances.values()) // 2}*\n"
    text += f"🎭 Марионеток: *{len(world.marionettes)}*\n"
    text += f"🏴 Аннексий: *{len(world.annexed)}*\n"
    text += f"🌍 Напряжённость: *{world.world_tension:.1f}%*\n"
    
    await update.message.reply_text(text, parse_mode="MarkdownV2")
