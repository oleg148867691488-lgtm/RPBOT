"""
BOT.PY — RP БОТ ДЛЯ RENDER (ФИНАЛ)
=====================================
Автономная страна с ИИ (Iron Man режим).
Игроки влияют через чаты, бот сам принимает решения.
Админ-панель только для тебя (по ADMIN_ID).
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
    ADMIN_USERNAME,
    saved_chats,
    bot_stopped
)

# =====================================================================
# КОМАНДЫ
# =====================================================================
from commands import (
    # Публичные
    start_command,
    # Админские основные
    country_command,
    year_command,
    savechatnews_command,
    savechatwar_command,
    savechatoon_command,
    stop_command,
    start_bot_command,
    wipe_command,
    research_command,
    status_command,
    # Админские для тестов
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

# === ПУБЛИЧНЫЕ (ДОСТУПНЫ ВСЕМ) ===
app.add_handler(CommandHandler("start", start_command))

# === АДМИНСКИЕ ОСНОВНЫЕ ===
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

# === АДМИНСКИЕ ДЛЯ ТЕСТОВ (СКРЫТЫЕ) ===
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
    """Логирование ошибок с уведомлением админа"""
    logger.error(f"Ошибка при обработке {update}: {context.error}")
    
    if update and update.message:
        user_id = update.message.from_user.id
        try:
            if user_id == ADMIN_ID:
                # Админу показываем детали
                error_text = str(context.error)[:500] if context.error else "Неизвестная ошибка"
                await update.message.reply_text(
                    f"❌ *Ошибка:*\n```\n{error_text}\n```",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Внутренняя ошибка. Администратор уведомлён.")
        except:
            pass
    
    if context.error:
        logger.error(f"Детали: {context.error.__class__.__name__}: {context.error}")

app.add_error_handler(error_handler)

# =====================================================================
# КОНСОЛЬ АДМИНА (ДЛЯ ТЕСТОВ НА СЕРВЕРЕ)
# =====================================================================
async def admin_console():
    """
    Интерактивная консоль для тестов.
    Запускается при локальной разработке.
    На Render не запускается (там --bot-only).
    """
    print("\n" + "=" * 60)
    print("🎮 КОНСОЛЬ АДМИНА RP-БОТА")
    print("=" * 60)
    print("Команды: help, status, news, decision, war, peace,")
    print("         trade, ally, sanctions, addmoney, setpower,")
    print("         world, ai, quit")
    print("=" * 60 + "\n")
    
    while True:
        try:
            # Асинхронный ввод
            cmd = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("🎮 > ")
            )
            
            cmd = cmd.strip()
            if not cmd:
                continue
            
            parts = cmd.split(maxsplit=2)
            action = parts[0].lower()
            
            # === HELP ===
            if action == "help":
                print("\n📋 ДОСТУПНЫЕ КОМАНДЫ:")
                print("  status              — статус бота")
                print("  news                — сгенерировать новость")
                print("  decision            — запустить цикл решений")
                print("  war СТРАНА ПРИЧИНА  — объявить войну")
                print("  peace               — завершить все войны")
                print("  trade РЕСУРС КОЛВО — продать ресурс")
                print("  ally СТРАНА         — заключить союз")
                print("  sanctions СТРАНА    — ввести санкции")
                print("  addmoney СУММА      — добавить денег")
                print("  setpower ЧИСЛО      — установить силу (0-100)")
                print("  world               — состояние мира")
                print("  ai ВОПРОС           — спросить ИИ")
                print("  quit                — выход\n")
            
            # === STATUS ===
            elif action == "status":
                country = get_country(ADMIN_ID) or "не выбрана"
                from history import get_year, get_economy
                year = get_year(ADMIN_ID) or "?"
                economy = get_economy(ADMIN_ID)
                power = world.get_power_rating(country) if hasattr(world, 'get_power_rating') else 0
                
                print(f"\n📊 СТАТУС БОТА")
                print(f"  🌍 Страна: {country}")
                print(f"  📅 Год: {year} | Месяц: {world.month}")
                print(f"  💪 Сила: {power:.1f}/100")
                print(f"  🔄 Ходов: {world.turn}")
                print(f"  ⏸️ Остановлен: {'да' if bot_stopped else 'нет'}")
                
                if economy:
                    print(f"\n  💰 Бюджет: ${economy['budget']:,}")
                    print(f"  🔩 Сталь: {economy['steel']} | 🛢️ Нефть: {economy['oil']}")
                    print(f"  🌾 Зерно: {economy['grain']} | 🥇 Золото: {economy['gold']}")
                
                wars = [w for w in world.wars.values() if w.get('status') == 'active']
                print(f"\n  ⚔️ Активных войн: {len(wars)}")
                for war in wars:
                    print(f"    • {war['attacker']} vs {war['defender']}")
                
                allies = world.alliances.get(country, [])
                print(f"  🤝 Союзников: {len(allies)}")
                if allies:
                    print(f"    • {', '.join(allies)}")
                print()
            
            # === NEWS ===
            elif action == "news":
                print("🔄 Генерирую новость...")
                news_text = await generate_news()
                print(f"\n📰 {news_text}\n")
                
                if saved_chats.get("news") and app.bot:
                    await app.bot.send_message(
                        chat_id=saved_chats["news"],
                        text=f"📰 *Новости*\n\n{news_text}",
                        parse_mode="Markdown"
                    )
                    print("✅ Отправлено в новостной чат\n")
            
            # === DECISION ===
            elif action == "decision":
                print("🧠 Запускаю цикл решений...")
                await decision_loop(app)
                print("✅ Цикл завершён\n")
            
            # === WAR ===
            elif action == "war":
                if len(parts) < 2:
                    print("❌ Укажите: war СТРАНА ПРИЧИНА\n")
                else:
                    target = parts[1]
                    reason = parts[2] if len(parts) > 2 else "Тестовая война"
                    
                    from war import declare_war_command
                    await declare_war_command(
                        update=None,
                        context=app,
                        args=[target, reason]
                    )
                    print(f"⚔️ Война объявлена: {target}\n")
            
            # === PEACE ===
            elif action == "peace":
                from war import active_wars
                count = len(active_wars)
                active_wars.clear()
                print(f"🕊️ Завершено войн: {count}\n")
            
            # === TRADE ===
            elif action == "trade":
                if len(parts) < 3:
                    print("❌ Укажите: trade РЕСУРС КОЛВО\n")
                else:
                    resource = parts[1].lower()
                    try:
                        amount = int(parts[2])
                    except ValueError:
                        print("❌ Количество должно быть числом\n")
                        continue
                    
                    from economy import PRICES
                    if resource not in PRICES:
                        print(f"❌ Ресурс '{resource}' не найден. Доступны: {', '.join(PRICES.keys())}\n")
                        continue
                    
                    from history import get_economy, update_economy
                    eco = get_economy(ADMIN_ID)
                    
                    if not eco:
                        print("❌ Экономика не инициализирована\n")
                        continue
                    
                    if eco.get(resource, 0) < amount:
                        print(f"❌ Недостаточно {resource}. У вас: {eco.get(resource, 0)}\n")
                        continue
                    
                    price = PRICES[resource] * amount
                    update_economy(
                        ADMIN_ID,
                        budget=eco['budget'] + price,
                        **{resource: eco[resource] - amount}
                    )
                    print(f"✅ Продано {amount} {resource} за ${price:,}\n")
            
            # === ALLY ===
            elif action == "ally":
                if len(parts) < 2:
                    print("❌ Укажите: ally СТРАНА\n")
                else:
                    target = parts[1]
                    country = get_country(ADMIN_ID) or "Швейцария"
                    world.alliances.setdefault(country, []).append(target)
                    world.alliances.setdefault(target, []).append(country)
                    print(f"🤝 Союз с {target} заключён\n")
            
            # === SANCTIONS ===
            elif action == "sanctions":
                if len(parts) < 2:
                    print("❌ Укажите: sanctions СТРАНА\n")
                else:
                    target = parts[1]
                    country = get_country(ADMIN_ID) or "Швейцария"
                    world.sanctions.setdefault(target, []).append(country)
                    print(f"🚫 Санкции против {target} введены\n")
            
            # === ADDMONEY ===
            elif action == "addmoney":
                if len(parts) < 2:
                    print("❌ Укажите: addmoney СУММА\n")
                else:
                    try:
                        amount = int(parts[1])
                    except ValueError:
                        print("❌ Сумма должна быть числом\n")
                        continue
                    
                    from history import get_economy, update_economy
                    eco = get_economy(ADMIN_ID)
                    if eco:
                        update_economy(ADMIN_ID, budget=eco['budget'] + amount)
                        print(f"💰 Добавлено ${amount:,}\n")
            
            # === SETPOWER ===
            elif action == "setpower":
                if len(parts) < 2:
                    print("❌ Укажите: setpower ЧИСЛО\n")
                else:
                    try:
                        power = float(parts[1])
                    except ValueError:
                        print("❌ Сила должна быть числом (0-100)\n")
                        continue
                    
                    country = get_country(ADMIN_ID) or "Швейцария"
                    if country in world.countries:
                        world.countries[country]["army_size"] = int(power * 10000)
                        world.countries[country]["gdp"] = power * 100_000_000_000
                        print(f"💪 Сила {country} установлена на {power}/100\n")
            
            # === WORLD ===
            elif action == "world":
                print("\n🌍 СОСТОЯНИЕ МИРА")
                print(f"  Стран: {len(world.countries)}")
                for name in list(world.countries.keys())[:15]:
                    power = world.get_power_rating(name)
                    profile = world.country_profiles.get(name)
                    profile_type = profile.profile_type if profile else "?"
                    print(f"    {name}: сила {power:.1f}/100 ({profile_type})")
                
                print(f"\n  ⚔️ Войны: {len(world.wars)}")
                for war in list(world.wars.values())[:5]:
                    print(f"    {war['attacker']} vs {war['defender']} — {war['status']}")
                
                print(f"  🤝 Союзы: {sum(len(v) for v in world.alliances.values()) // 2}")
                print(f"  🎭 Марионетки: {len(world.marionettes)}")
                print(f"  🏴 Аннексии: {len(world.annexed)}")
                print(f"  🔬 Технологии: {sum(world.technologies.values())} уровней")
                print()
            
            # === AI ===
            elif action == "ai":
                if len(parts) < 2:
                    print("❌ Укажите: ai ВОПРОС\n")
                else:
                    question = parts[1] if len(parts) > 1 else " ".join(parts[1:])
                    print("🤔 Думаю...")
                    from ai_manager import ai
                    answer = await ai.ask_groq(
                        question,
                        system_prompt=ai.get_rp_system_prompt(),
                        temperature=0.7,
                        max_tokens=500
                    )
                    print(f"\n🤖 {answer}\n")
            
            # === QUIT ===
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
                "/force\\_news — тест новости\n"
                "/force\\_decision — тест решений\n"
                "/force\\_war \\[страна\\] — тест войны\n"
                "/debug\\_world — состояние мира\n\n"
                "💬 Игроки влияют через чаты\n"
                "Бот САМ принимает решения"
            ),
            parse_mode="MarkdownV2"
        )
        logger.info(f"✅ Уведомление админу отправлено")
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
        # Только консоль (без бота)
        print("🎮 Запуск в режиме консоли...")
        asyncio.run(admin_console())
    
    else:
        # Параметры для Render
        port = int(os.environ.get("PORT", "8080"))
        webhook_url = os.environ.get("WEBHOOK_URL", None)
        
        async def main():
            """Главная функция"""
            await on_startup()
            
            if not bot_only:
                # Локальная разработка: консоль + бот
                console_task = asyncio.create_task(admin_console())
            
            # Запуск бота
            if webhook_url:
                # Продакшен (Render с вебхуком)
                logger.info(f"🔗 Запуск с вебхуком: {webhook_url}")
                await app.run_webhook(
                    listen="0.0.0.0",
                    port=port,
                    webhook_url=webhook_url,
                    drop_pending_updates=True
                )
            else:
                # Разработка (поллинг)
                logger.info("🔄 Запуск с поллингом")
                await app.run_polling(drop_pending_updates=True)
        
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен")
