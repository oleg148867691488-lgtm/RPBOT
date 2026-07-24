"""
COMMANDS.PY — ВСЕ КОМАНДЫ БОТА
===============================
Обработчики всех команд для RP-бота.
"""

import re
from telegram import Update
from telegram.ext import ContextTypes
from config import (
    ADMIN_ID, 
    ADMIN_USERNAME, 
    saved_chats, 
    save_saved_chats, 
    bot_stopped,
    BOT_TOKEN
)
from history import (
    save_country, 
    save_year, 
    get_country, 
    get_year,
    get_economy,
    init_economy,
    clear_all_history,
    clear_user_history
)
from news import generate_news, send_news_to_chat, ask_ai

# =====================================================================
# /START — ПРИВЕТСТВИЕ И ДИСКЛЕЙМЕР
# =====================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое сообщение с дисклеймером"""
    
    user_id = update.message.from_user.id
    is_admin = user_id == ADMIN_ID
    
    text = (
        "⚠️ *ДИСКЛЕЙМЕР*\n\n"
        "Этот бот — игровая историческая симуляция \\(RP\\)\\.\n"
        "Все персонажи, события, войны, санкции и действия \n"
        "являются ВЫМЫШЛЕННЫМИ и происходят в рамках игры\\.\n\n"
        "Любые совпадения с реальными событиями случайны\\.\n"
        "Насилие, война и дипломатия — часть игровой механики,\n"
        "а не призыв к действиям в реальной жизни\\.\n\n"
        "🎮 *RP\\-бот \\| Iron Man режим*\n\n"
    )
    
    if is_admin:
        text += (
            "👑 *Админ\\-панель:*\n"
            "/country \\[страна\\] — выбрать страну\n"
            "/year \\[год\\] — установить год\n"
            "/news \\[текст\\] — выпустить новость\n"
            "/research \\[страна\\] — исследовать страну\n"
            "/status — статус бота\n\n"
            "💬 *Чаты:*\n"
            "/savechatnews — сохранить чат для новостей\n"
            "/savechatwar — сохранить чат для войны\n"
            "/savechatoon — сохранить чат для ООН\n\n"
            "⚙️ *Управление:*\n"
            "/stop — остановить бота\n"
            "/start\\_bot — запустить бота\n"
            "/wipe — полный сброс\n\n"
            "💰 *Экономика:*\n"
            "/balance — баланс и ресурсы\n"
            "/trade \\[купить/продать\\] \\[ресурс\\] \\[кол\\-во\\] — торговля\n"
            "/tradeplayer @игрок \\[ресурс\\] \\[кол\\-во\\] \\[цена\\] — торговля с игроком\n"
            "/addmoney \\[сумма\\] — добавить деньги\n"
            "/economy — статистика экономики\n\n"
            "⚔️ *Война:*\n"
            "/war \\[страна\\] \\[причина\\] — объявить войну\n"
            "/respond \\[согласиться/отказаться\\] — ответ на войну\n"
            "/strategy \\[наступление/оборона/партизаны\\] — сменить стратегию\n"
            "/war\\_status — статус войны\n"
            "/peace — запросить мир\n\n"
            "🏛️ *Дипломатия:*\n"
            "/un\\_propose \\[текст\\] — предложить резолюцию в ООН\n"
            "/vote \\[за/против\\] — проголосовать\n"
            "/ally \\[страна\\] \\[тип\\] — предложить союз\n"
            "/accept\\_ally — принять союз\n"
            "/sanctions \\[страна\\] \\[причина\\] — ввести санкции\n"
            "/remove\\_sanctions \\[страна\\] — снять санкции\n"
            "/diplomacy — статус дипломатии"
        )
    else:
        text += (
            "📌 *Доступные команды:*\n"
            "/balance — мой баланс\n"
            "/trade \\[купить/продать\\] \\[ресурс\\] \\[кол\\-во\\] — торговля\n"
            "/tradeplayer @игрок \\[ресурс\\] \\[кол\\-во\\] \\[цена\\] — торговля с игроком\n"
            "/war\\_status — статус войны\n"
            "/respond \\[согласиться/отказаться\\] — ответ на войну\n"
            "/strategy \\[наступление/оборона/партизаны\\] — сменить стратегию\n"
            "/peace — запросить мир\n"
            "/vote \\[за/против\\] — голосовать в ООН\n"
            "/accept\\_ally — принять союз\n"
            "/diplomacy — статус дипломатии\n\n"
            "💬 Также вы можете писать в чаты:\n"
            "• \\#НазваниеСтраны — опубликовать новость\n"
            "• @botname вопрос — спросить бота"
        )
    
    await update.message.reply_text(
        text,
        parse_mode="MarkdownV2"
    )

# =====================================================================
# /COUNTRY — ВЫБОР СТРАНЫ
# =====================================================================
async def country_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбрать страну для бота (только админ)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Укажите страну\\. Пример: /country Россия\n\n"
            "🌍 Бот автоматически исследует страну и адаптирует стратегию\\.",
            parse_mode="MarkdownV2"
        )
        return
    
    country = " ".join(args)
    save_country(user_id, country)
    init_economy(user_id)
    
    await update.message.reply_text(
        f"✅ Страна изменена на: *{country}*\n\n"
        f"🔍 Бот исследует {country} и адаптирует стратегию\\.\\.\\.",
        parse_mode="MarkdownV2"
    )
    
    # Запускаем исследование страны
    from ai_manager import ai
    from decision_engine import world, CountryProfile
    
    await update.message.reply_text(f"🔍 Исследую {country}\\.\\.\\. Это займёт 15\\-20 секунд\\.", parse_mode="MarkdownV2")
    
    try:
        info = await ai.research_country(country)
        profile = CountryProfile(country, info)
        world.country_profiles[country] = profile
        
        await update.message.reply_text(
            f"🌍 *{country} — исследование завершено\\!*\n\n"
            f"📊 Профиль: *{profile.profile_type}*\n"
            f"💪 {profile.bonuses.get('description', '')}\n"
            f"⚠️ {profile.restrictions.get('description', '')}\n\n"
            f"📝 *Сводка:*\n{info['summary'][:500]}",
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Исследование не удалось: {str(e)[:100]}\n"
            f"Бот будет использовать базовую стратегию\\.",
            parse_mode="MarkdownV2"
        )

# =====================================================================
# /YEAR — УСТАНОВКА ГОДА
# =====================================================================
async def year_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить игровой год (только админ)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Укажите год\\. Пример: /year 1936", parse_mode="MarkdownV2")
        return
    
    try:
        year = int(args[0])
        if year < 1800 or year > 2100:
            await update.message.reply_text("❌ Год должен быть между 1800 и 2100\\.")
            return
        
        save_year(user_id, year)
        from decision_engine import world
        world.year = year
        
        await update.message.reply_text(
            f"✅ Год изменён на: *{year}*\n"
            f"📅 Месяц: *{world.month}*",
            parse_mode="MarkdownV2"
        )
    except ValueError:
        await update.message.reply_text("❌ Введите число\\. Пример: /year 1936", parse_mode="MarkdownV2")

# =====================================================================
# /NEWS — ВЫПУСТИТЬ НОВОСТЬ
# =====================================================================
async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выпустить новость (только админ)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    
    # Если нет аргументов — генерируем новость через AI
    if not args:
        await update.message.reply_text("🔄 Генерирую новость через AI\\.\\.\\.", parse_mode="MarkdownV2")
        news = await generate_news()
        await send_news_to_chat(context, news)
        await update.message.reply_text(f"✅ Новость сгенерирована и отправлена:\n\n{news}")
        return
    
    # Если есть текст — отправляем его
    text = " ".join(args)
    await send_news_to_chat(context, text)
    await update.message.reply_text("✅ Новость отправлена\\.")

# =====================================================================
# /SAVECHATNEWS — СОХРАНИТЬ НОВОСТНОЙ ЧАТ
# =====================================================================
async def savechatnews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить чат для новостей (только админ)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    saved_chats["news"] = update.message.chat.id
    save_saved_chats(saved_chats)
    
    await update.message.reply_text(
        "📰 *Новостной чат сохранён\\!*\n\n"
        "Сюда будут приходить:\n"
        "• Автоматические новости каждые 15 минут\n"
        "• Экстренные новости о войнах\n"
        "• Экономические отчёты\n\n"
        "Игроки могут писать сюда:\n"
        "• \\#НазваниеСтраны — опубликовать новость\n"
        "• @botname вопрос — спросить бота",
        parse_mode="MarkdownV2"
    )

# =====================================================================
# /SAVECHATWAR — СОХРАНИТЬ ВОЕННЫЙ ЧАТ
# =====================================================================
async def savechatwar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить чат для войны (только админ)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    saved_chats["war"] = update.message.chat.id
    save_saved_chats(saved_chats)
    
    await update.message.reply_text(
        "⚔️ *Военный чат сохранён\\!*\n\n"
        "Сюда будут приходить:\n"
        "• Объявления о войнах\n"
        "• Ходы сражений\n"
        "• Результаты битв\n"
        "• Предложения о мире\n\n"
        "Команды:\n"
        "/war — объявить войну\n"
        "/respond — ответить на войну\n"
        "/strategy — сменить стратегию\n"
        "/war\\_status — статус войны\n"
        "/peace — запросить мир",
        parse_mode="MarkdownV2"
    )

# =====================================================================
# /SAVECHATOON — СОХРАНИТЬ ЧАТ ООН
# =====================================================================
async def savechatoon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить чат для ООН (только админ)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    saved_chats["un"] = update.message.chat.id
    save_saved_chats(saved_chats)
    
    await update.message.reply_text(
        "🏛️ *Чат ООН сохранён\\!*\n\n"
        "Сюда будут приходить:\n"
        "• Предложения резолюций\n"
        "• Голосования\n"
        "• Санкции\n"
        "• Дипломатические ноты\n\n"
        "Команды:\n"
        "/un\\_propose — предложить резолюцию\n"
        "/vote — проголосовать\n"
        "/ally — предложить союз\n"
        "/accept\\_ally — принять союз\n"
        "/sanctions — ввести санкции\n"
        "/remove\\_sanctions — снять санкции\n"
        "/diplomacy — статус дипломатии",
        parse_mode="MarkdownV2"
    )

# =====================================================================
# /STOP — ОСТАНОВИТЬ БОТА
# =====================================================================
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Остановить бота (только админ)"""
    global bot_stopped
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    import config
    config.bot_stopped = True
    
    await update.message.reply_text(
        "🛑 *Бот остановлен\\.*\n\n"
        "• Новости не генерируются\n"
        "• Decision Engine остановлен\n"
        "• Бот не отвечает на сообщения\n\n"
        "Для запуска используйте /start\\_bot",
        parse_mode="MarkdownV2"
    )

# =====================================================================
# /START_BOT — ЗАПУСТИТЬ БОТА
# =====================================================================
async def start_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запустить бота (только админ)"""
    global bot_stopped
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    import config
    config.bot_stopped = False
    
    await update.message.reply_text(
        "✅ *Бот запущен\\!*\n\n"
        "• Новости генерируются\n"
        "• Decision Engine работает\n"
        "• Бот отвечает на сообщения",
        parse_mode="MarkdownV2"
    )

# =====================================================================
# /WIPE — ПОЛНЫЙ СБРОС
# =====================================================================
async def wipe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полный сброс памяти бота (только админ)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    # Очистка базы данных
    clear_all_history()
    
    # Очистка сохранённых чатов
    save_saved_chats({"news": None, "war": None, "un": None})
    saved_chats["news"] = None
    saved_chats["war"] = None
    saved_chats["un"] = None
    
    # Сброс состояния мира
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
    
    # Сброс технологий
    for key in world.technologies:
        world.technologies[key] = 1 if key != "nuclear" else 0
    
    # Сброс инфраструктуры
    for key in world.infrastructure:
        world.infrastructure[key] = 1 if key != "ports" else 0
    
    # Сброс флага остановки
    import config
    config.bot_stopped = False
    
    await update.message.reply_text(
        "🗑️ *ВАЙП ВЫПОЛНЕН\\!*\n\n"
        "✅ История очищена\n"
        "✅ Чаты сброшены\n"
        "✅ Войны удалены\n"
        "✅ Технологии сброшены\n"
        "✅ Бот готов к новой игре\n\n"
        "📌 Используйте:\n"
        "/country \\[страна\\] — выбрать новую страну\n"
        "/year \\[год\\] — установить год\n"
        "/savechatnews — настроить новостной чат\n"
        "/savechatwar — настроить военный чат\n"
        "/savechatoon — настроить чат ООН",
        parse_mode="MarkdownV2"
    )

# =====================================================================
# /RESEARCH — ИССЛЕДОВАТЬ СТРАНУ
# =====================================================================
async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Исследовать любую страну через интернет (только админ)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Укажите страну\\. Пример: /research Франция\n\n"
            "Бот найдёт информацию:\n"
            "• Армия и вооружение\n"
            "• Экономика и ВВП\n"
            "• Политическое устройство\n"
            "• География и климат\n"
            "• Международные отношения",
            parse_mode="MarkdownV2"
        )
        return
    
    country = " ".join(args)
    await update.message.reply_text(
        f"🔍 Исследую *{country}*\\.\\.\\.\n"
        f"Это займёт 15\\-20 секунд\\. Ожидайте\\.\\.\\.",
        parse_mode="MarkdownV2"
    )
    
    from ai_manager import ai
    
    try:
        info = await ai.research_country(country)
        
        summary = info.get("summary", "Информация не найдена")
        
        # Отправляем результат (с учётом лимита Telegram)
        text = f"🌍 *Сводка по стране {country}:*\n\n{summary}"
        
        if len(text) > 4000:
            from utils import split_text
            parts = split_text(text, 3800)
            for i, part in enumerate(parts):
                await update.message.reply_text(
                    part,
                    parse_mode="MarkdownV2" if i == 0 else "Markdown"
                )
                await asyncio.sleep(0.5)
        else:
            await update.message.reply_text(text, parse_mode="MarkdownV2")
        
        # Предлагаем установить эту страну
        await update.message.reply_text(
            f"💡 Чтобы играть за {country}, используйте:\n"
            f"`/country {country}`",
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка при исследовании: {str(e)[:200]}"
        )

# =====================================================================
# /STATUS — СТАТУС БОТА
# =====================================================================
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать полный статус бота (только админ)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    from decision_engine import world
    from ai_manager import ai
    
    country = get_country(user_id) or "не выбрана"
    year = get_year(user_id) or "не установлен"
    economy = get_economy(user_id)
    
    text = (
        f"📊 *СТАТУС БОТА*\n\n"
        f"🌍 Страна: *{country}*\n"
        f"📅 Год: *{year}*\n"
        f"📆 Месяц: *{world.month}*\n"
        f"🔄 Ходов: *{world.turn}*\n"
        f"⏸️ Остановлен: *{'да' if bot_stopped else 'нет'}*\n\n"
    )
    
    # Экономика
    if economy:
        text += (
            f"💰 *Экономика:*\n"
            f"Бюджет: ${economy['budget']:,}\n"
            f"🔩 Сталь: {economy['steel']} т\\.\n"
            f"🛢️ Нефть: {economy['oil']} т\\.\n"
            f"🌾 Зерно: {economy['grain']} т\\.\n"
            f"🥇 Золото: {economy['gold']} унций\n\n"
        )
    
    # Профиль страны
    profile = world.country_profiles.get(country)
    if profile:
        text += (
            f"📊 *Профиль:* {profile.profile_type}\n"
            f"💪 {profile.bonuses.get('description', '')}\n"
            f"⚠️ {profile.restrictions.get('description', '')}\n\n"
        )
    
    # Сила
    power = world.get_power_rating(country)
    text += f"💪 Сила: *{power:.1f}/100*\n\n"
    
    # Войны
    active_wars = [w for w in world.wars.values() if w.get("status") == "active"]
    text += f"⚔️ Активных войн: *{len(active_wars)}*\n"
    for war in active_wars:
        text += f"• {war['attacker']} vs {war['defender']} — {war.get('strategy', 'нет')}\n"
    
    # Союзники
    allies = world.alliances.get(country, [])
    text += f"\n🤝 Союзников: *{len(allies)}*\n"
    for ally in allies:
        text += f"• {ally}\n"
    
    # Марионетки
    puppets = [p for p, m in world.marionettes.items() if m == country]
    text += f"\n🎭 Марионеток: *{len(puppets)}*\n"
    for puppet in puppets:
        text += f"• {puppet}\n"
    
    # Аннексии
    annexed = [a for a, m in world.annexed.items() if m == country]
    text += f"\n🏴 Аннексий: *{len(annexed)}*\n"
    for a in annexed:
        text += f"• {a}\n"
    
    # Технологии
    text += f"\n🔬 *Технологии:*\n"
    for tech, level in world.technologies.items():
        text += f"• {tech}: уровень {level}\n"
    
    # Инфраструктура
    text += f"\n🏗️ *Инфраструктура:*\n"
    for infra, level in world.infrastructure.items():
        text += f"• {infra}: уровень {level}\n"
    
    # AI статистика
    text += f"\n🤖 *AI Статистика:*\n"
    text += f"• Groq вызовов: {ai.stats['groq_calls']}\n"
    text += f"• Gemini вызовов: {ai.stats['gemini_calls']}\n"
    text += f"• Ollama вызовов: {ai.stats['ollama_calls']}\n"
    text += f"• Rate limits: {ai.stats['rate_limits_hit']}\n"
    text += f"• Ошибок: {ai.stats['errors']}\n"
    
    # Отправляем частями если нужно
    if len(text) > 4000:
        from utils import split_text
        parts = split_text(text, 3800)
        for i, part in enumerate(parts):
            await update.message.reply_text(
                part,
                parse_mode="MarkdownV2" if i == 0 else "Markdown"
            )
            await asyncio.sleep(0.5)
    else:
        await update.message.reply_text(text, parse_mode="MarkdownV2")


# =====================================================================
# ИМПОРТ ДЛЯ SPLIT_TEXT
# =====================================================================
import asyncio
