"""
WORLDHOOKS.PY — что происходит после каждой новости, опубликованной в мировой чат:
  • биржа реагирует на смысл (месторождения, диверсии, блокады проливов);
  • референдум о независимости → новая страна;
  • вассальная зависимость (договор, капитуляция, освобождение) запоминается сама.
Выполняется в фоне, чтобы не задерживать публикацию.
"""
import asyncio
import logging
import re

log = logging.getLogger(__name__)
_tasks = set()


def schedule(bot, html_text: str):
    plain = re.sub(r"<[^>]+>", "", html_text or "")
    if plain.lstrip().startswith("📈 Рынок"):           # собственные сообщения-реакции не разбираем повторно
        return
    t = asyncio.ensure_future(after_publish(bot, plain))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def after_publish(bot, plain: str):
    from events import publish
    try:
        import marketfx
        line = await marketfx.apply_news(bot, plain)
        if line:
            await publish(bot, line)
    except Exception:
        log.exception("Реакция рынка на новость не удалась")
    try:
        import referendum
        await referendum.check_text(bot, plain)
    except Exception:
        log.exception("Разбор референдума не удался")
    try:
        import aiwars
        note = await aiwars.vassalize_from_text(plain)
        if note:
            await publish(bot, note)
    except Exception:
        log.exception("Разбор вассалитета не удался")
