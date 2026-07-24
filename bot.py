"""
BOT.PY — RP БОТ ДЛЯ RENDER (ФИНАЛ)
=====================================
Автономная страна с ИИ (Iron Man режим).
Содержит /tension для мировой напряжённости.
"""

import asyncio
import logging
import os
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# =====================================================================
# КОНФИГУРАЦИЯ
# =====================================================================
from config import (
    BOT_TOKEN,
    NEWS_INTERVAL_MINUTES,
    DECISION_INTERVAL_MINUTES,
    ADMIN_ID,
    saved_chats,
    bot_stopped
)

# =====================================================================
# КОМАНДЫ
# =====================================================================
from commands import (
    start_command,
    tension_command,
    country_command,
    year_command,
    research_command,
    status_command,
    savechatnews_command,
    savechatwar_command,
    savechatoon_command,
    stop_command,
    start_bot_command,
    wipe_command,
    admin_help_command,
    force_news_command,
    force_decision_command,
    force_war_command,
    force_peace_command,
    force_trade_command,
    force_ally_command,
    force_sanctions_command,
    add_money_command,
    set_power_command,
    debug_ai_command,
    debug_world_command,
)

# =====================================================================
# ОБРАБОТЧИК СООБЩЕНИЙ
# =====================================================================
from handlers import handle_message

# =====================================================================
# МОДУЛИ
# =====================================================================
from news import generate_news_task, generate_news, send_news_to_chat
from decision_engine import decision_loop, init_world, world
from history import init_db, get_country

# =====================================================================
# НАСТРОЙКА ЛОГГИРОВАНИЯ
# =====================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =====================================================================
# СОЗДАНИЕ ПРИЛОЖЕНИЯ
# =====================================================================
app = Application.builder().token(BOT_TOKEN).build()

# =====================================================================
# РЕГИСТРАЦИЯ КОМАНД
# =====================================================================

# Публичные
app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("tension", tension_command))

# Админские основные
app.add_handler(CommandHandler("country", country_command))
app.add_handler(CommandHandler("year", year_command))
app.add_handler(CommandHandler("research", research_command))
app.add_handler(CommandHandler("status", status_command))
app.add_handler(CommandHandler("savechatnews", savechatnews_command))
app.add_handler(CommandHandler("savechatwar", savechatwar_command))
app.add_handler(CommandHandler("savechatoon", savechatoon_command))
app.add_handler(CommandHandler("stop", stop_command))
app.add_handler(CommandHandler("start_bot", start_bot_command))
app.add_handler(CommandHandler("wipe", wipe_command))

# Админские скрытые (тесты)
app.add_handler(CommandHandler("admin", admin_help_command))
app.add_handler(CommandHandler("force_news", force_news_command))
app.add_handler(CommandHandler("force_decision", force_decision_command))
app.add_handler(CommandHandler("force_war", force_war_command))
app.add_handler(CommandHandler("force_peace", force_peace_command))
app.add_handler(CommandHandler("force_trade", force_trade_command))
app.add_handler(CommandHandler("force_ally", force_ally_command))
app.add_handler(CommandHandler("force_sanctions", force_sanctions_command))
app.add_handler(CommandHandler("addmoney", add_money_command))
app.add_handler(CommandHandler("setpower", set_power_command))
app.add_handler(CommandHandler("debug_ai", debug_ai_command))
app.add_handler(CommandHandler("debug_world", debug_world_command))

# =====================================================================
# ОБРАБОТЧИК ВСЕХ ТЕКСТОВЫХ СООБЩЕНИЙ
# =====================================================================
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# =====================================================================
# ОБРАБОТЧИК ОШИБОК
# =====================================================================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка при обработке {update}: {context.error}")
    
    if update and update.message:
        user_id = update.message.from_user.id
        try:
            if user_id == ADMIN_ID:
                error_text = str(context.error)[:500] if context.error else "Неизвестная ошибка"
                await update.message.reply_text(
                    f"❌ *Ошибка:*\n```\n{error_text}\n```",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Внутренняя ошибка.")
        except:
            pass
    
    if context.error:
        logger.error(f"Детали: {context.error.__class__.__name__}: {context.error}")

app.add_error_handler(error_handler)

# =====================================================================
# ИНИЦИАЛИЗАЦИЯ ПРИ ЗАПУСКЕ
# =====================================================================
async def on_startup():
    """Действия при запуске бота"""
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК RP-БОТА (RENDER)")
    logger.info("=" * 50)
    
    # База данных
    try:
        init_db()
        logger.info("✅ База данных")
    except Exception as e:
        logger.error(f"❌ БД: {e}")
    
    # Мир
    try:
        await init_world()
        logger.info("✅ Мир инициализирован")
    except Exception as e:
        logger.warning(f"⚠️ Мир: {e}")
    
    # Планировщик
    try:
        scheduler = AsyncIOScheduler()
        
        scheduler.add_job(
            lambda: asyncio.create_task(generate_news_task(app)),
            trigger=IntervalTrigger(minutes=NEWS_INTERVAL_MINUTES),
            id="news_job",
            replace_existing=True
        )
        
        scheduler.add_job(
            lambda: asyncio.create_task(decision_loop(app)),
            trigger=IntervalTrigger(minutes=DECISION_INTERVAL_MINUTES),
            id="decision_job",
            replace_existing=True
        )
        
        scheduler.start()
        logger.info(f"✅ Планировщик (новости: {NEWS_INTERVAL_MINUTES}мин, решения: {DECISION_INTERVAL_MINUTES}мин)")
    except Exception as e:
        logger.error(f"❌ Планировщик: {e}")
    
    # Уведомление админу
    try:
        country = get_country(ADMIN_ID) or "не выбрана"
        
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "✅ *RP-Бот запущен на Render!*\n\n"
                f"🌍 Страна: *{country}*\n"
                f"📰 Новости: каждые {NEWS_INTERVAL_MINUTES} мин\n"
                f"🧠 Решения: каждые {DECISION_INTERVAL_MINUTES} мин\n\n"
                "📋 *Админ-панель:*\n"
                "/admin — все команды\n"
                "/status — статус\n"
                "/tension — мировая напряжённость\n"
                "/force\\_news — тест новости\n"
                "/force\\_decision — тест решений\n"
                "/debug\\_world — состояние мира\n\n"
                "💬 Игроки влияют через чаты\n"
                "Бот САМ принимает решения"
            ),
            parse_mode="MarkdownV2"
        )
        logger.info("✅ Уведомление админу отправлено")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось уведомить админа: {e}")
    
    logger.info("=" * 50)
    logger.info("✅ БОТ ЗАПУЩЕН")
    logger.info("=" * 50)

# =====================================================================
# ТОЧКА ВХОДА
# =====================================================================
if __name__ == "__main__":
    # Аргументы командной строки
    console_mode = "--console" in sys.argv
    bot_only = "--bot-only" in sys.argv
    
    if console_mode:
        print("🎮 Запуск в режиме консоли...")
        
        async def run_console():
            # Простая консоль для тестов
            print("\n" + "=" * 60)
            print("🎮 КОНСОЛЬ АДМИНА RP-БОТА")
            print("=" * 60)
            print("Команды: help, status, tension, news, decision, war, peace,")
            print("         trade, ally, sanctions, addmoney, setpower, world, ai, quit")
            print("=" * 60 + "\n")
            
            while True:
                try:
                    cmd = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("🎮 > ")
                    )
                    cmd = cmd.strip()
                    if not cmd:
                        continue
                    
                    parts = cmd.split(maxsplit=2)
                    action = parts[0].lower()
                    
                    if action == "help":
                        print("\n📋 КОМАНДЫ:")
                        print("  status, tension, news, decision, war СТРАНА ПРИЧИНА, peace,")
                        print("  trade РЕСУРС КОЛВО, ally СТРАНА, sanctions СТРАНА,")
                        print("  addmoney СУММА, setpower ЧИСЛО, world, ai ВОПРОС, quit\n")
                    
                    elif action == "status":
                        country = get_country(ADMIN_ID) or "не выбрана"
                        from history import get_year, get_economy
                        year = get_year(ADMIN_ID) or "?"
                        economy = get_economy(ADMIN_ID)
                        power = world.get_power_rating(country) if hasattr(world, 'get_power_rating') else 0
                        
                        print(f"\n📊 СТАТУС")
                        print(f"  🌍 Страна: {country}")
                        print(f"  📅 Год: {year} | Месяц: {world.month}")
                        print(f"  💪 Сила: {power:.1f}/100 | 🌍 Напряжённость: {world.world_tension:.1f}%")
                        print(f"  🔄 Ходов: {world.turn} | ⏸️ Остановлен: {'да' if bot_stopped else 'нет'}")
                        
                        if economy:
                            print(f"  💰 Бюджет: ${economy['budget']:,}")
                            print(f"  🔩 Сталь: {economy['steel']} | 🛢️ Нефть: {economy['oil']}")
                        print()
                    
                    elif action == "tension":
                        print("🌍 Анализирую напряжённость...")
                        data = await world.calculate_world_tension_ai()
                        print(f"  Напряжённость: {data.get('tension', 0):.1f}%")
                        print(f"  Статус: {data.get('status', '?')}")
                        print(f"  Тренд: {data.get('trend', '?')}")
                        print(f"  Война оправдана: {data.get('can_justify_war', False)}")
                        print(f"  Ядерка разрешена: {data.get('can_use_nukes', False)}\n")
                    
                    elif action == "news":
                        print("🔄 Генерирую новость...")
                        news_text = await generate_news()
                        print(f"\n📰 {news_text}\n")
                    
                    elif action == "decision":
                        print("🧠 Запускаю цикл решений...")
                        await decision_loop(None)
                        print("✅ Цикл завершён\n")
                    
                    elif action == "war":
                        if len(parts) < 2:
                            print("❌ war СТРАНА ПРИЧИНА\n")
                        else:
                            target = parts[1]
                            reason = parts[2] if len(parts) > 2 else "Тестовая война"
                            from war import declare_war_command
                            await declare_war_command(update=None, context=None, args=[target, reason])
                            print(f"⚔️ Война объявлена: {target}\n")
                    
                    elif action == "peace":
                        from war import active_wars
                        count = len(active_wars)
                        active_wars.clear()
                        print(f"🕊️ Завершено войн: {count}\n")
                    
                    elif action == "trade":
                        if len(parts) < 3:
                            print("❌ trade РЕСУРС КОЛВО\n")
                        else:
                            resource = parts[1].lower()
                            amount = int(parts[2])
                            from economy import PRICES
                            if resource in PRICES:
                                from history import get_economy, update_economy
                                eco = get_economy(ADMIN_ID)
                                if eco and eco.get(resource, 0) >= amount:
                                    price = PRICES[resource] * amount
                                    update_economy(ADMIN_ID, budget=eco['budget'] + price, **{resource: eco[resource] - amount})
                                    print(f"✅ Продано {amount} {resource} за ${price:,}\n")
                    
                    elif action == "ally":
                        if len(parts) < 2:
                            print("❌ ally СТРАНА\n")
                        else:
                            target = parts[1]
                            country = get_country(ADMIN_ID) or "Швейцария"
                            world.alliances.setdefault(country, []).append(target)
                            world.alliances.setdefault(target, []).append(country)
                            print(f"🤝 Союз с {target}\n")
                    
                    elif action == "sanctions":
                        if len(parts) < 2:
                            print("❌ sanctions СТРАНА\n")
                        else:
                            target = parts[1]
                            country = get_country(ADMIN_ID) or "Швейцария"
                            world.sanctions.setdefault(target, []).append(country)
                            print(f"🚫 Санкции против {target}\n")
                    
                    elif action == "addmoney":
                        if len(parts) < 2:
                            print("❌ addmoney СУММА\n")
                        else:
                            from history import get_economy, update_economy
                            eco = get_economy(ADMIN_ID)
                            if eco:
                                update_economy(ADMIN_ID, budget=eco['budget'] + int(parts[1]))
                                print(f"💰 Добавлено ${int(parts[1]):,}\n")
                    
                    elif action == "setpower":
                        if len(parts) < 2:
                            print("❌ setpower ЧИСЛО\n")
                        else:
                            power = float(parts[1])
                            country = get_country(ADMIN_ID) or "Швейцария"
                            if country in world.countries:
                                world.countries[country]["army_size"] = int(power * 10000)
                                world.countries[country]["gdp"] = power * 100_000_000_000
                                print(f"💪 Сила {country} = {power}/100\n")
                    
                    elif action == "world":
                        print(f"\n🌍 МИР: {len(world.countries)} стран")
                        for name in list(world.countries.keys())[:10]:
                            print(f"  {name}: сила {world.get_power_rating(name):.1f}/100")
                        print(f"  ⚔️ Войн: {len(world.wars)} | 🤝 Союзов: {sum(len(v) for v in world.alliances.values())//2}")
                        print(f"  🌍 Напряжённость: {world.world_tension:.1f}%\n")
                    
                    elif action == "ai":
                        if len(parts) < 2:
                            print("❌ ai ВОПРОС\n")
                        else:
                            question = " ".join(parts[1:])
                            print("🤔 Думаю...")
                            from ai_manager import ai
                            answer = await ai.ask_groq(question, system_prompt=ai.get_rp_system_prompt(), temperature=0.7, max_tokens=500)
                            print(f"\n🤖 {answer}\n")
                    
                    elif action in ["quit", "exit", "q"]:
                        print("👋 Выход из консоли...\n")
                        break
                    
                    else:
                        print(f"❌ Неизвестная команда: {action}")
                        print("  Введите 'help' для списка команд\n")
                
                except KeyboardInterrupt:
                    print("\n👋 Выход...\n")
                    break
                except Exception as e:
                    print(f"❌ Ошибка: {e}\n")
        
        asyncio.run(run_console())
    
    else:
        # Параметры для Render
        port = int(os.environ.get("PORT", "8080"))
        webhook_url = os.environ.get("WEBHOOK_URL", None)
        
        async def main():
            await on_startup()
            
            if webhook_url:
                logger.info(f"🔗 Запуск с вебхуком: {webhook_url}")
                await app.run_webhook(
                    listen="0.0.0.0",
                    port=port,
                    webhook_url=webhook_url,
                    drop_pending_updates=True
                )
            else:
                logger.info("🔄 Запуск с поллингом")
                await app.run_polling(drop_pending_updates=True)
        
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен")
