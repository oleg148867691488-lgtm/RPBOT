"""
BOT.PY — точка входа РП-бота.
Запуск: python bot.py   (Flask поднимается рядом для health-check на Render)

Что нового по сравнению со старой версией:
- concurrent_updates=True: бот обрабатывает сообщения параллельно. Раньше одно долгое обращение
  к нейросети (до 2 минут) вешало бота для ВСЕХ пользователей.
- Инициализация БД при старте с повторами, а не при импорте с «проглоченной» ошибкой.
- Keep-alive для бесплатного Render, меню команд, уведомление владельца о серьёзных ошибках.
"""

import asyncio
import logging
import os
import time
from threading import Thread

from flask import Flask
from telegram import BotCommand, Update
from telegram.error import Conflict, NetworkError
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)

import commands as cmd
import config as C
import database as db
import events
import agency
import agencyui
import referendum
import aiwars
import currencies
import finance
import gamecmds as gc
import ui
import wars
import worldbank
from handlers import handle_message, verdict_command
from netclient import close_client, get_client

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("rpbot")


# =====================================================================
# FLASK (health check)
# =====================================================================

web = Flask(__name__)


@web.route("/")
@web.route("/health")
def health():
    return "✅ RP Bot жив и здоров!", 200


def run_web():
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    web.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))


# =====================================================================
# ФОНОВЫЕ ЗАДАЧИ И ЗАПУСК
# =====================================================================

async def keepalive():
    """Раз в 10 минут пингует собственный URL, чтобы бесплатный Render не засыпал."""
    while True:
        await asyncio.sleep(600)
        try:
            await get_client().get(C.KEEPALIVE_URL, timeout=15)
        except Exception as e:
            log.debug("keepalive: %s", type(e).__name__)


async def post_init(app: Application):
    last_err = None
    for attempt in range(1, 4):
        try:
            await db.arun(db.init_db)
            last_err = None
            break
        except Exception as e:
            last_err = e
            log.error("Не удалось инициализировать БД (попытка %d/3): %s", attempt, e)
            await asyncio.sleep(3 * attempt)
    if last_err:
        raise RuntimeError("База данных недоступна — запуск остановлен") from last_err

    worldbank.load_custom(db.get_setting("custom_countries"))
    import geo
    geo.load_dynamic(db.get_setting("geo_custom"))                       # новые государства после референдумов
    await app.bot.set_my_commands([
        BotCommand("menu", "Главное меню"),
        BotCommand("help", "Помощь"),
        BotCommand("verdict", "Вердикт по ситуации"),
        BotCommand("otvet", "Ответ страны на любое обращение"),
        BotCommand("info", "Сводка по стране"),
        BotCommand("top", "Топ стран"),
        BotCommand("vs", "Сравнить две страны"),
        BotCommand("news", "Мировые новости"),
        BotCommand("market", "Биржа"),
        BotCommand("op", "Тайная операция"),
        BotCommand("spy", "Шпионаж: кража секретов"),
        BotCommand("intel", "Прокачать разведку страны"),
        BotCommand("divert", "Вывести деньги через агента"),
        BotCommand("launder", "Отмыть деньги"),
        BotCommand("funds", "Твои счета"),
        BotCommand("hire", "Нанять агента"),
        BotCommand("hq", "Штаб агентства"),
        BotCommand("war", "Войны: ходы и меню"),
        BotCommand("war_verdict", "Вердикт по войне"),
        BotCommand("action", "Решение своей страны"),
        BotCommand("timeline", "Хроника страны/темы"),
        BotCommand("year", "Дата в РП"),
        BotCommand("myid", "Мой ID"),
    ])
    if C.KEEPALIVE_URL:
        app.bot_data["keepalive_task"] = asyncio.create_task(keepalive())
        log.info("Keep-alive включён: %s", C.KEEPALIVE_URL)
    app.bot_data["events_task"] = asyncio.create_task(events.scheduler(app.bot))
    me = await app.bot.get_me()
    log.info("✅ RP Bot запущен как @%s", me.username)


async def post_shutdown(app: Application):
    for name in ("keepalive_task", "events_task"):
        task = app.bot_data.get(name)
        if task:
            task.cancel()
    await close_client()
    await db.arun(db.close_conn)


_last_notify = 0.0


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    global _last_notify
    err = context.error
    if isinstance(err, Conflict):
        log.error("Conflict: запущено два экземпляра бота с одним токеном!")
        return
    if isinstance(err, NetworkError):  # включает TimedOut — временные сетевые сбои
        log.warning("Сетевая ошибка Telegram: %s", err)
        return
    log.error("Необработанная ошибка", exc_info=err)

    if isinstance(update, Update) and update.effective_message and update.effective_chat:
        text = update.effective_message.text or ""
        if update.effective_chat.type == "private" or text.startswith("/"):
            try:
                await update.effective_message.reply_text("⚠️ Что-то пошло не так. Попробуй ещё раз чуть позже.")
            except Exception:
                pass

    if C.ADMIN_ID and time.time() - _last_notify > 300:
        _last_notify = time.time()
        try:
            await context.bot.send_message(C.ADMIN_ID, f"⚠️ Ошибка бота:\n{type(err).__name__}: {str(err)[:400]}")
        except Exception:
            pass


def main():
    if not C.BOT_TOKEN:
        log.error("❌ BOT_TOKEN не задан в переменных окружения!")
        return

    Thread(target=run_web, daemon=True).start()
    log.info("✅ Flask запущен на порту %s", os.environ.get("PORT", "10000"))

    app = (
        Application.builder()
        .token(C.BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # --- Публичные ---
    app.add_handler(CommandHandler(["start", "menu"], ui.menu_command))
    app.add_handler(CommandHandler("help", cmd.help_command))
    app.add_handler(CommandHandler("timeline", ui.timeline_command))
    app.add_handler(CommandHandler("vs", ui.vs_command))
    app.add_handler(CommandHandler("op", gc.op_command))
    app.add_handler(CommandHandler(["action", "do"], gc.action_command))
    app.add_handler(CommandHandler("terror", gc.terror_command))
    app.add_handler(CommandHandler("war", wars.war_command))
    app.add_handler(CommandHandler("war_verdict", wars.verdict_command))
    app.add_handler(CommandHandler("spy", gc.spy_command))
    app.add_handler(CommandHandler("loot", gc.loot_command))
    app.add_handler(CommandHandler(["agents", "agency"], agencyui.agents_ui_command))      # агентство с кнопками
    app.add_handler(CommandHandler("hire", agency.hire_command))
    app.add_handler(CommandHandler("train", agency.train_command))
    app.add_handler(CommandHandler("hq", agency.hq_command))
    app.add_handler(CommandHandler("fire", agency.fire_command))
    app.add_handler(CommandHandler("givefunds", agency.givefunds_command))
    app.add_handler(CommandHandler("intel", gc.intel_command))
    app.add_handler(CommandHandler("divert", finance.divert_command))
    app.add_handler(CommandHandler("launder", finance.launder_command))
    app.add_handler(CommandHandler("funds", finance.funds_command))
    app.add_handler(CommandHandler("compromise", finance.compromise_command))
    app.add_handler(CommandHandler("agent", finance.agent_manage_command))
    app.add_handler(CommandHandler("treasury", gc.treasury_command))
    app.add_handler(CommandHandler("secrets", gc.secrets_command))
    app.add_handler(CommandHandler("delsecret", gc.delsecret_command))
    app.add_handler(CommandHandler("peace", gc.peace_command))
    app.add_handler(CommandHandler("wars", gc.wars_command))
    app.add_handler(CommandHandler("addcountry", gc.addcountry_command))
    app.add_handler(CommandHandler(["rollback", "otkat"], gc.rollback_command))
    app.add_handler(CommandHandler(["rollbackpost", "otkatpost"], gc.rollbackpost_command))
    app.add_handler(CommandHandler("autosecret", gc.autosecret_command))
    app.add_handler(CommandHandler("strict", gc.strict_command))
    app.add_handler(CommandHandler("aiwar", aiwars.aiwar_command))
    app.add_handler(CommandHandler("reach", aiwars.reach_command))
    app.add_handler(CommandHandler("alliance", aiwars.alliance_command))
    app.add_handler(CommandHandler("unalliance", aiwars.unalliance_command))
    app.add_handler(CommandHandler("alliances", aiwars.alliances_command))
    app.add_handler(CommandHandler("vassal", aiwars.vassal_command))
    app.add_handler(CommandHandler("referendum", referendum.referendum_command))
    app.add_handler(CommandHandler("unvassal", aiwars.unvassal_command))
    app.add_handler(CommandHandler("vassals", aiwars.vassals_command))
    app.add_handler(CommandHandler("annex", aiwars.annex_command))
    app.add_handler(CommandHandler("unannex", aiwars.unannex_command))
    app.add_handler(CommandHandler(["newcurrency", "newvaluta"], currencies.newcurrency_command))
    app.add_handler(CommandHandler("goldreserve", currencies.goldreserve_command))
    app.add_handler(CommandHandler("delcurrency", currencies.delcurrency_command))
    app.add_handler(CommandHandler(["currency", "valuty"], currencies.currency_command))
    app.add_handler(CommandHandler(["otvet", "ultimatum"], gc.otvet_command))
    app.add_handler(CommandHandler("news", gc.news_command))
    app.add_handler(CommandHandler("market", gc.market_command))
    app.add_handler(CommandHandler("tension", gc.tension_command))
    app.add_handler(CommandHandler("mycountry", gc.mycountry_command))
    app.add_handler(CommandHandler("security", gc.security_command))
    app.add_handler(CommandHandler("event", gc.event_command))
    app.add_handler(CommandHandler("newsidea", gc.newsidea_command))
    app.add_handler(CommandHandler("ops", gc.ops_command))
    app.add_handler(CommandHandler("verdict", verdict_command))
    app.add_handler(CommandHandler("info", cmd.info_command))
    app.add_handler(CommandHandler("top", cmd.top_command))
    app.add_handler(CommandHandler("year", cmd.year_command))
    app.add_handler(CommandHandler("myid", cmd.myid_command))

    # --- Админские ---
    app.add_handler(CommandHandler("stats", cmd.stats_command))
    app.add_handler(CommandHandler("tags", cmd.tags_command))
    app.add_handler(CommandHandler("facts", cmd.facts_command))
    app.add_handler(CommandHandler("find", cmd.find_command))
    app.add_handler(CommandHandler("delfact", cmd.delfact_command))
    app.add_handler(CommandHandler("export", cmd.export_command))
    app.add_handler(CommandHandler("savechat", cmd.savechat_command))
    app.add_handler(CommandHandler("saveworld", cmd.saveworld_command))
    app.add_handler(CommandHandler("bulk", cmd.bulk_command))
    app.add_handler(CommandHandler("bulkworld", cmd.bulkworld_command))
    app.add_handler(CommandHandler("clear_history", cmd.clear_history_command))
    app.add_handler(CommandHandler("admins", cmd.admins_command))

    # --- Только владельцы ---
    app.add_handler(CommandHandler("clear_facts", cmd.clear_facts_command))
    app.add_handler(CommandHandler("deltag", cmd.deltag_command))
    app.add_handler(CommandHandler("addadmin", cmd.addadmin_command))
    app.add_handler(CommandHandler("deladmin", cmd.deladmin_command))

    # --- Обычные сообщения (вопросы + #теги) и кнопки меню ---
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(ui.ui_callback, pattern=r"^ui:"))
    app.add_handler(CallbackQueryHandler(agencyui.callback, pattern=r"^ag:"))
    app.add_handler(CallbackQueryHandler(aiwars.callback, pattern=r"^aw:"))
    app.add_handler(CallbackQueryHandler(wars.war_callback, pattern=r"^war:"))
    app.add_handler(CallbackQueryHandler(cmd.menu_callback, pattern=r"^menu_"))
    app.add_error_handler(error_handler)

    app.run_polling(allowed_updates=["message", "callback_query"], drop_pending_updates=True)


if __name__ == "__main__":
    main()
