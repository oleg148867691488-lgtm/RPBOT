import httpx
import random
import asyncio
from typing import Optional, List, Dict
from config import GROQ_KEYS, GEMINI_KEY, OLLAMA_KEY, GROQ_URL, GEMINI_URL, OLLAMA_URL

class AIManager:
    def __init__(self):
        self.groq_keys = [k for k in GROQ_KEYS if k]  # только рабочие ключи
        self.current_key_index = 0
        self.rate_limited_keys = {}  # ключ → время разблокировки
        
    def _get_next_groq_key(self):
        """Round-robin с учётом rate-limit"""
        now = asyncio.get_event_loop().time()
        
        # Убираем ключи, которые ещё в rate-limit
        available_keys = [
            k for k in self.groq_keys 
            if k not in self.rate_limited_keys or self.rate_limited_keys[k] < now
        ]
        
        if not available_keys:
            # Ждём ближайший доступный
            wait_time = min(self.rate_limited_keys.values()) - now
            return None, wait_time
        
        key = available_keys[self.current_key_index % len(available_keys)]
        self.current_key_index += 1
        return key, 0
    
    def _mark_rate_limited(self, key: str):
        """Помечаем ключ как недоступный на 60 секунд"""
        loop = asyncio.get_event_loop()
        self.rate_limited_keys[key] = loop.time() + 60
    
    async def ask_groq(
        self, 
        prompt: str, 
        system_prompt: str = None,
        temperature: float = 0.7,
        model: str = "llama-3.3-70b-versatile",
        max_retries: int = 3
    ) -> str:
        """Запрос к Groq с автоматическим переключением ключей"""
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        for attempt in range(max_retries):
            key, wait_time = self._get_next_groq_key()
            
            if key is None:
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time + 1)
                    continue
                return "❌ Все AI-ключи недоступны. Попробуйте позже."
            
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": model,
                "temperature": temperature,
                "messages": messages
            }
            
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(GROQ_URL, headers=headers, json=data)
                    
                    if resp.status_code == 429:  # Rate limit
                        self._mark_rate_limited(key)
                        continue
                    
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]["content"]
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    return f"❌ Ошибка AI: {str(e)}"
                await asyncio.sleep(1)
        
        return "❌ Не удалось получить ответ от AI."
    
    async def search_web(self, query: str, country_context: str = None) -> str:
        """Поиск в интернете: сначала Ollama, если фейл → Gemini"""
        
        # === Попытка через Ollama ===
        if OLLAMA_KEY:
            try:
                result = await self._search_ollama(query, country_context)
                if result and "ошибка" not in result.lower():
                    return result
            except:
                pass
        
        # === Fallback на Gemini ===
        if GEMINI_KEY:
            try:
                result = await self._search_gemini(query, country_context)
                if result:
                    return result
            except:
                pass
        
        return "❌ Не удалось выполнить поиск в интернете."
    
    async def _search_ollama(self, query: str, context: str = None) -> str:
        """Поиск через Ollama (локальную или хостинг)"""
        prompt = f"Найди информацию в интернете: {query}"
        if context:
            prompt = f"Контекст: {context}\n\nНайди информацию: {query}"
        
        data = {
            "model": "llama3.2",  # или другая модель
            "prompt": prompt,
            "stream": False
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(OLLAMA_URL, json=data)
            resp.raise_for_status()
            return resp.json()["response"]
    
    async def _search_gemini(self, query: str, context: str = None) -> str:
        """Поиск через Gemini с grounding"""
        prompt = f"""Тебе нужно найти актуальную информацию по запросу. 
        Используй поиск в интернете (Google Search).
        
        Запрос: {query}"""
        
        if context:
            prompt = f"Контекст: {context}\n\n{prompt}"
        
        url = f"{GEMINI_URL}?key={GEMINI_KEY}"
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "tools": [{"googleSearch": {}}]  # Включаем Google Search
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=data)
            resp.raise_for_status()
            result = resp.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
    
    async def research_country(self, country: str) -> Dict:
        """Исследовать страну через интернет и вернуть сводку"""
        queries = [
            f"{country} армия численность вооружение 2024",
            f"{country} экономика ВВП бюджет 2024",
            f"{country} политика президент правительство 2024",
            f"{country} международные отношения союзники 2024"
        ]
        
        results = {}
        for query in queries:
            info = await self.search_web(query, f"Информация о стране {country}")
            results[query] = info
            await asyncio.sleep(2)  # Пауза между запросами
        
        # Собираем сводку через Groq
        summary_prompt = f"""На основе следующей информации о стране {country}, 
        составь краткую сводку (5-7 предложений) для РП-игры.
        
        Информация:
        {chr(10).join([f'- {k}: {v[:200]}' for k, v in results.items()])}
        
        Формат: население, армия, экономика, политика, международные отношения."""
        
        summary = await self.ask_groq(summary_prompt, temperature=0.5)
        
        return {
            "country": country,
            "summary": summary,
            "detailed": results
        }

# === ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ===
ai = AIManager()
