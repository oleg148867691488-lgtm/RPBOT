"""
STYLE.PY — единый визуальный язык бота: заголовки, цитаты-блоки, шкалы и уровни.
Только то, что понимает Telegram в HTML: <b>, <i>, <code>, <blockquote>, <blockquote expandable>.
"""
from textutils import esc

LINE = "━━━━━━━━━━━━━━━━"
THIN = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"


def title(emoji: str, text: str, sub: str = "") -> str:
    """Заголовок экрана: эмодзи, жирный текст, подпись курсивом и линия."""
    out = f"{emoji} <b>{esc(text)}</b>"
    if sub:
        out += f"\n<i>{esc(sub)}</i>"
    return out + f"\n{LINE}"


def quote(text: str, expandable: bool = False) -> str:
    """Цитата-блок (текст экранируется здесь)."""
    tag = "blockquote expandable" if expandable else "blockquote"
    return f"<{tag}>{esc(text)}</blockquote>"


def quote_html(html: str, expandable: bool = False) -> str:
    """Цитата-блок из уже готового HTML (экранировать нужно самому)."""
    tag = "blockquote expandable" if expandable else "blockquote"
    return f"<{tag}>{html}</blockquote>"


def meter(value: float, hi: float = 100.0, n: int = 10) -> str:
    k = max(0, min(n, round((value / hi if hi else 0) * n)))
    return "▰" * k + "▱" * (n - k)


def level(v: float):
    """Уровень напряжённости 0–100: (значок, слово)."""
    if v < 25:
        return "🟢", "спокойно"
    if v < 50:
        return "🟡", "тревожно"
    if v < 75:
        return "🟠", "опасно"
    return "🔴", "критично"
