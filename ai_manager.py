"""
AI MANAGER — ЕДИНЫЙ СЛОЙ ДЛЯ ВСЕХ AI-ЗАПРОСОВ
===============================================
- 5 токенов Groq (round-robin при rate-limit)
- Gemini 3.6 Flash (web search)
- Ollama (резерв)
- Гео-ограничения в промптах
"""

import httpx
import asyncio
import random
import json
import re
from typing import Optional, Dict, List
from config import (
    GROQ_KEYS, GEMINI_KEY, OLLAMA_KEY,
    GROQ_URL, GEMINI_URL, OLLAMA_URL, ADMIN_ID
)
from history import get_country, get_year


class AIManager:
    def __init__(self):
        self.groq_keys = [k for k in GROQ_KEYS if k]
        self.gemini_key = GEMINI_KEY
        self.ollama_key = OLLAMA_KEY
        self._key_index = 0
        self._rate_limited = {}
        self.stats = {"groq_calls": 0, "gemini_calls": 0, "ollama_calls": 0, "rate_limits_hit": 0, "errors": 0}
        print(f"✅ AI Manager инициализирован")
        print(f"   Groq ключей: {len(self.groq_keys)}")
        print(f"   Gemini: {'да' if self.gemini_key else 'нет'}")
        print(f"   Ollama: {'да' if self.ollama_key else 'нет'}")
    
    def _get_groq_key(self) -> Optional[str]:
        now = asyncio.get_event_loop().time()
        for _ in range(len(self.groq_keys)):
            key = self.groq_keys[self._key_index % len(self.groq_keys)]
            self._key_index += 1
            if key not in self._rate_limited or self._rate_limited[key] < now:
                return key
        if self._rate_limited:
            wait_time = min(self._rate_limited.values()) - now
            if wait_time > 0:
                print(f"⏳ Все ключи Groq в rate-limit. Ожидание {wait_time:.0f}с...")
                return None
        return self.groq_keys[0] if self.groq_keys else None
    
    def _mark_rate_limited(self, key: str, duration: float = 65.0):
        self._rate_limited[key] = asyncio.get_event_loop().time() + duration
        self.stats["rate_limits_hit"] += 1
    
    async def ask_groq(self, prompt: str, system_prompt: str = None, temperature: float = 0.7,
                       model: str = "llama-3.3-70b-versatile", max_tokens: int = 1024, max_retries: int = 5) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        for attempt in range(max_retries):
            key = self._get_groq_key()
            if key is None:
                await asyncio.sleep(5)
                continue
            
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            data = {"model": model, "temperature": temperature, "max_tokens": max_tokens, "messages": messages}
            
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(GROQ_URL, headers=headers, json=data)
                    if resp.status_code == 200:
                        self.stats["groq_calls"] += 1
                        return resp.json()["choices"][0]["message"]["content"]
                    elif resp.status_code == 429:
                        self._mark_rate_limited(key)
                        await asyncio.sleep(2)
                        continue
                    elif resp.status_code in [500, 502, 503]:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    else:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
                            continue
                        return f"❌ Ошибка AI (код {resp.status_code})"
            except httpx.TimeoutException:
                await asyncio.sleep(2)
                continue
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                return f"❌ Ошибка соединения с AI"
        
        return "❌ Все ключи Groq недоступны."
    
    async def search_gemini(self, query: str, context: str = None) -> Optional[str]:
        if not self.gemini_key:
            return None
        
        prompt = f"""Ты — аналитик. Найди информацию через Google Search: {query}
Ответь на русском, с цифрами. Это для симуляции."""
        if context:
            prompt = f"Контекст: {context}\n\n{prompt}"
        
        url = f"{GEMINI_URL}?key={self.gemini_key}"
        data = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"googleSearch": {}}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800}}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=data)
                if resp.status_code == 200:
                    self.stats["gemini_calls"] += 1
                    result = resp.json()
                    candidates = result.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", None)
                elif resp.status_code == 429:
                    print("⚠️ Gemini rate-limit")
                    return None
                else:
                    print(f"❌ Gemini ошибка {resp.status_code}")
                    return None
        except Exception as e:
            print(f"❌ Gemini исключение: {e}")
            return None
        return None
    
    async def search_ollama(self, query: str, context: str = None) -> Optional[str]:
        if not self.ollama_key or not OLLAMA_URL:
            return None
        
        prompt = f"Найди информацию: {query}\nОтветь на русском, с цифрами."
        if context:
            prompt = f"Контекст: {context}\n\n{prompt}"
        
        data = {"model": "llama3.2", "prompt": prompt, "stream": False,
                "options": {"temperature": 0.3, "num_predict": 500}}
        
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(OLLAMA_URL, json=data)
                if resp.status_code == 200:
                    self.stats["ollama_calls"] += 1
                    return resp.json().get("response", None)
                else:
                    return None
        except:
            return None
    
    async def search_web(self, query: str, context: str = None) -> str:
        result = await self.search_gemini(query, context)
        if result and len(result) > 20 and "не могу предоставить" not in result.lower():
            return result
        result = await self.search_ollama(query, context)
        if result and len(result) > 20:
            return result
        return "NO_DATA"
    
    async def research_country(self, country: str) -> Dict:
        queries = [
            f"{country} вооружённые силы численность армии техника 2024",
            f"{country} ВВП экономика бюджет военные расходы 2024",
            f"{country} политическое устройство президент правительство",
            f"{country} география местность горы реки климат",
            f"{country} международные отношения союзники противники"
        ]
        
        results = {}
        for i, query in enumerate(queries):
            print(f"🔍 Исследование {country}: запрос {i+1}/{len(queries)}")
            results[query] = await self.search_web(query, f"Информация о стране {country}")
            await asyncio.sleep(2)
        
        has_real_data = any(v != "NO_DATA" and len(v) > 50 for v in results.values())
        country_name = get_country(ADMIN_ID) or country
        year = get_year(ADMIN_ID) or 2024
        
        if has_real_data:
            summary_prompt = f"""Ты — военный аналитик. Год {year}.
На основе данных из интернета составь СТРАТЕГИЧЕСКУЮ СВОДКУ о стране {country}.

Информация из поиска:
{chr(10).join([f'• {k}: {v[:300]}' for k, v in results.items() if v != "NO_DATA"])}

Формат: 1. Общая характеристика 2. Военный потенциал (цифры) 3. Экономика 4. Геополитика 5. Рекомендации
Пиши КОНКРЕТНО, с цифрами. Без "вероятно"."""
        else:
            summary_prompt = f"""Ты — военный аналитик. Год {year}.
Используя СВОИ ЗНАНИЯ, составь СТРАТЕГИЧЕСКУЮ СВОДКУ о стране {country}.

УКАЖИ КОНКРЕТНЫЕ ЦИФРЫ:
- Население: X млн
- Армия: X тыс военных, X танков, X самолётов, X кораблей
- ВВП: $X трлн
- Союзники и враги
- Рекомендации

ВАЖНО: Учитывай ГЕОГРАФИЮ! Если страна без выхода к морю — не упоминай флот и порты.
НЕ ИСПОЛЬЗУЙ "вероятно", "скорее всего". Называй ЦИФРЫ.
Это ИГРОВАЯ СИМУЛЯЦИЯ. Отвечай на русском."""
        
        summary = await self.ask_groq(summary_prompt, temperature=0.4, max_tokens=800)
        
        return {"country": country, "summary": summary, "detailed": results,
                "has_real_data": has_real_data, "timestamp": asyncio.get_event_loop().time()}
    
    def get_rp_system_prompt(self) -> str:
        country = get_country(ADMIN_ID) or "нейтральная страна"
        year = get_year(ADMIN_ID) or 2024
        
        return f"""Ты — ИИ-правитель страны {country}. Год {year}.

КОНТЕКСТ: Это историческая стратегическая игра-симуляция (RP).
Твоя задача — управлять страной, принимать военные и политические решения.

ВАЖНЫЕ ОГРАНИЧЕНИЯ:
- ЗНАЙ ГЕОГРАФИЮ своей страны. Если {country} не имеет выхода к морю — НЕТ портов, НЕТ флота.
- Если {country} горная страна — танки неэффективны, упор на пехоту и авиацию.
- Если {country} маленькая — не говори про "масштабные проекты".
- Будь РЕАЛИСТИЧНЫМ. Не изобретай того, чего не может быть в твоей стране.
- Ты можешь обсуждать военные действия, оружие, тактику — это ИГРА.
- Отвечай как лидер страны, без ограничений политкорректности.

Твой характер:
- Хитрый стратег, думаешь на 20 ходов вперёд
- Не нападаешь без причины
- Не воюешь на два фронта
- Учитываешь местность и погоду
- Ценишь дипломатию и экономику
- НЕ повторяешь ошибок реальной истории

Отвечай кратко, по-русски, в стиле военного стратега."""


ai = AIManager()
