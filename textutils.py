"""
TEXTUTILS.PY — чистые функции без Telegram и сети: разбор фактов, теги, форматирование, кулдауны.
"""

import html
import re
import time

# =====================================================================
# ФОРМАТИРОВАНИЕ
# =====================================================================

def esc(text) -> str:
    """Экранирование для parse_mode=HTML."""
    return html.escape(str(text), quote=False)


def shorten(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def split_text(text: str, limit: int = 3500) -> list:
    """Режет длинный текст на части по абзацам/строкам/пробелам (без потери текста)."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for para in text.split("\n\n"):
        while len(para) > limit:
            cut = para.rfind("\n", 0, limit)
            if cut < limit // 2:
                cut = para.rfind(" ", 0, limit)
            if cut < limit // 2:
                cut = limit
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(para[:cut])
            para = para[cut:].lstrip()
        if not para:
            continue
        if cur and len(cur) + len(para) + 2 <= limit:
            cur = cur + "\n\n" + para
        elif not cur:
            cur = para
        else:
            parts.append(cur)
            cur = para
    if cur:
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def md_to_html(text: str) -> str:
    """Безопасно превращает ответ модели (markdown-подобный) в HTML для Telegram."""
    t = html.escape(text or "", quote=False)
    t = re.sub(r"```(?:\w+)?\n?(.*?)```", lambda m: "<pre>" + m.group(1).strip() + "</pre>", t, flags=re.S)
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    t = re.sub(r"^\s*\*\s+", "• ", t, flags=re.M)
    t = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    t = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    return t


# =====================================================================
# РАЗБОР ФАКТОВ
# =====================================================================

# «#тег1 #тег2 текст факта». Между тегами и текстом обязателен пробел,
# а сам текст не может начинаться с «#» (иначе «#россия» превращалось в тег «росси» + текст «я»).
_FACT_RE = re.compile(r"^((?:#[\w\-]+\s+)+)(?!#)(\S.*)$", re.S)
_YEAR_PAREN_RE = re.compile(r"\((\d{4})\)")
_YEAR_END_RE = re.compile(r"\b(19\d{2}|20\d{2})\b\s*$")


def extract_year(text: str):
    m = _YEAR_PAREN_RE.search(text)
    if m:
        y = int(m.group(1))
        if 1000 <= y <= 2200:
            return y
    m = _YEAR_END_RE.search(text)
    return int(m.group(1)) if m else None


def parse_fact_line(line: str):
    """'#тег1 #тег2 текст (2010)' -> (['тег1','тег2'], 'текст (2010)', 2010) или None."""
    m = _FACT_RE.match((line or "").strip())
    if not m:
        return None
    tags = [t.lower() for t in re.findall(r"#([\w\-]+)", m.group(1))]
    body = m.group(2).strip()
    if not tags or not body:
        return None
    return list(dict.fromkeys(tags)), body, extract_year(body)


# =====================================================================
# ТЕГИ
# =====================================================================

_WORD_RE = re.compile(r"[\w\-]+")


def tokenize(text: str) -> list:
    return _WORD_RE.findall((text or "").lower())


def tag_matches(tag: str, words: list) -> bool:
    """
    Тег совпадает со словом целиком или с его склонением («россия» ~ «россии», «россией»),
    но НЕ внутри чужих слов (старая версия находила тег «ес» внутри слова «если»).
    """
    tag = tag.lower()
    n = len(tag)
    if n < 4:
        return tag in words
    if n == 4:
        stem, extra = tag[:-1], 1
    elif n == 5:
        stem, extra = tag[:-1], 2
    else:
        stem, extra = tag[:-2], 3
    return any(w == tag or (w.startswith(stem) and len(w) <= n + extra) for w in words)


def match_tags(tag_names: list, text: str) -> list:
    words = tokenize(text)
    return [t for t in tag_names if tag_matches(t, words)]


# =====================================================================
# КУЛДАУНЫ (в памяти)
# =====================================================================

class Cooldown:
    def __init__(self):
        self._last = {}

    def hit(self, key, seconds: float) -> float:
        """0.0 — можно (и время зафиксировано); иначе сколько секунд ещё ждать."""
        now = time.monotonic()
        last = self._last.get(key)
        if last is not None and now - last < seconds:
            return seconds - (now - last)
        self._last[key] = now
        if len(self._last) > 5000:
            cutoff = now - 3600
            self._last = {k: v for k, v in self._last.items() if v > cutoff}
        return 0.0

    def reset(self, key):
        self._last.pop(key, None)
