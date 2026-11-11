"""
TG.PY — безопасная отправка сообщений.

Все «интерфейсные» тексты бота — в HTML (строки из БД и ввод пользователей экранируются через esc()).
Ответы нейросети конвертируются через md_to_html(); если Telegram всё равно не принял разметку,
сообщение уходит обычным текстом — так ответ больше никогда не теряется из-за символов _ или *.
"""

import html
import logging
import re

from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest

from textutils import md_to_html, split_text

log = logging.getLogger(__name__)


def thread_id_of(message) -> int:
    """ID темы форума. Для обычных чатов и реплаев — 0 (в старой версии реплаи ломали сохранение фактов)."""
    if message is not None and getattr(message, "is_topic_message", False):
        return message.message_thread_id or 0
    return 0


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def safe_reply(message, text: str, *, plain: bool = False, **kwargs):
    """reply_text с запасным вариантом без разметки, если Telegram не смог её разобрать."""
    if plain:
        return await message.reply_text(text, **kwargs)
    try:
        return await message.reply_text(text, parse_mode=ParseMode.HTML, **kwargs)
    except BadRequest as e:
        low = str(e).lower()
        if "parse" in low or "entit" in low:
            log.warning("HTML не принят Telegram, отправляю как текст: %s", e)
            return await message.reply_text(_strip_html(text), **kwargs)
        raise


async def reply_llm(message, text: str, header: str = ""):
    """Отправляет ответ нейросети частями, с безопасным форматированием."""
    parts = split_text(text, 3300)
    for i, part in enumerate(parts):
        body = md_to_html(part)
        if i == 0 and header:
            body = header + body
        await safe_reply(message, body)


async def edit_html(query, text: str, reply_markup=None):
    """edit_message_text для callback-кнопок; игнорирует «message is not modified»."""
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return
        raise


async def send_typing(bot, chat_id: int, thread_id: int = 0):
    try:
        await bot.send_chat_action(
            chat_id=chat_id, action=ChatAction.TYPING, message_thread_id=thread_id or None
        )
    except Exception:
        pass
