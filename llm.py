"""
LLM.PY — запросы к Groq (цепочка моделей × ключей), Gemini и веб-поиску Ollama.

Что исправлено по сравнению со старой версией:
- Вырезаются блоки <think>…</think> (Qwen3 отдаёт «рассуждения» прямо в ответе).
- Несуществующая модель (404/400) запоминается на 30 минут и пропускается,
  а не опрашивается 3 раза подряд по всем ключам при каждом сообщении.
- При лимите (429) сразу берётся следующий ключ, потом следующая модель.
- Общий httpx-клиент, внятные логи вместо print.
"""

import logging
import re
import time

import httpx

import config as C
from netclient import get_client

log = logging.getLogger(__name__)

_dead_models: dict = {}   # model -> до какого времени пропускаем
_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


def clean(text: str) -> str:
    text = _THINK_RE.sub("", text or "")
    if "</think>" in text:               # «хвост» без открывающего тега
        text = text.split("</think>")[-1]
    return text.strip()


async def call_groq(role: str, messages: list, temperature: float = 0.3):
    """role: 'main' | 'verdict' | 'summary'. Возвращает текст или None."""
    primary = C.PRIMARY_KEY.get(role)
    keys = [k for k in [primary] + C.GROQ_KEYS if k]
    keys = list(dict.fromkeys(keys))
    if not keys:
        log.warning("Groq: не задан ни один ключ GROQ_KEY_1..3")
        return None

    for model in C.MODELS.get(role, C.MODELS["main"]):
        if _dead_models.get(model, 0) > time.time():
            continue
        for i, key in enumerate(keys, 1):
            payload = {"model": model, "temperature": temperature, "messages": messages}
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            try:
                resp = await get_client().post(C.GROQ_URL, headers=headers, json=payload)
            except httpx.HTTPError as e:
                log.warning("Groq #%d (%s): сетевая ошибка %s", i, model, type(e).__name__)
                continue

            if resp.status_code == 200:
                try:
                    content = clean(resp.json()["choices"][0]["message"].get("content") or "")
                except (KeyError, IndexError, ValueError):
                    continue
                if content:
                    return content
                continue

            body = resp.text[:300]
            if resp.status_code in (400, 404) and "model" in body.lower():
                _dead_models[model] = time.time() + 1800
                log.error("Groq: модель %s недоступна (%s): %s. Пропускаю на 30 мин.",
                          model, resp.status_code, body)
                break  # к следующей модели
            log.warning("Groq #%d (%s) status=%s: %s", i, model, resp.status_code, body)
    return None


async def call_gemini(messages: list, temperature: float = 0.3):
    if not C.GEMINI_KEY:
        return None
    system_prompt, contents = "", []
    for m in messages:
        if m["role"] == "system":
            system_prompt += m["content"] + "\n"
        else:
            contents.append({
                "role": "user" if m["role"] == "user" else "model",
                "parts": [{"text": m["content"]}],
            })
    if not contents:
        contents = [{"role": "user", "parts": [{"text": system_prompt or "Привет"}]}]
        system_prompt = ""
    payload = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if system_prompt:
        payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
    try:
        resp = await get_client().post(
            C.GEMINI_URL.format(model=C.GEMINI_MODEL),
            params={"key": C.GEMINI_KEY}, json=payload,
        )
        if resp.status_code == 200:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            return clean("".join(p.get("text", "") for p in parts)) or None
        log.warning("Gemini status=%s: %s", resp.status_code, resp.text[:300])
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        log.warning("Gemini ошибка: %s", type(e).__name__)
    return None


async def ask(role: str, messages: list, temperature: float = 0.3):
    """Groq (цепочка) -> Gemini. Возвращает текст или None."""
    result = await call_groq(role, messages, temperature)
    if result:
        return result
    log.warning("Groq не ответил (роль %s), пробую Gemini", role)
    return await call_gemini(messages, temperature)


async def search_web(query: str):
    """Веб-поиск через Ollama (если задан OLLAMA_KEY)."""
    if not C.OLLAMA_KEY:
        return None
    try:
        resp = await get_client().post(
            C.OLLAMA_URL,
            headers={"Authorization": f"Bearer {C.OLLAMA_KEY}"},
            json={"query": query[:400], "max_results": 3},
            timeout=30.0,
        )
        if resp.status_code != 200:
            return None
        results = resp.json().get("results", [])[:3]
        if not results:
            return None
        return "\n".join(
            f"• {r.get('title', 'Без названия')}: {(r.get('content') or '')[:300]}" for r in results
        )
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Ollama ошибка: %s", type(e).__name__)
        return None
