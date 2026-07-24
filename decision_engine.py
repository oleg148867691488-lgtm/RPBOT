"""
DECISION ENGINE — МОЗГ ФЮРЕРА (IRON MAN MODE)
===============================================
Бот сам принимает ВСЕ решения как гениальный стратег.
Уровень: Iron Man (20+ ходов наперёд)
Характер: Фюрер 1936, но без тупых ошибок.
"""

import random
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from telegram import Bot
from telegram.ext import ContextTypes

from config import (
    ADMIN_ID,
    saved_chats,
    bot_stopped,
    AI_MODE,
    NEWS_INTERVAL_MINUTES,
    DECISION_INTERVAL_MINUTES
)
from ai_manager import ai
from history import (
    get_country,
    get_year,
    get_economy,
    update_economy,
    init_economy,
    save_country,
    save_year
)

# =====================================================================
# ГЛОБАЛЬНОЕ СОСТОЯНИЕ МИРА
# =====================================================================

class WorldState:
    """Хранит информацию о всех странах и отношениях"""
    
    def __init__(self):
        self.countries: Dict[str, dict] = {}  # страна → {армия, экономика, технологии}
        self.wars: Dict[str, dict] = {}        # war_id → {участники, статус, потери}
        self.alliances: Dict[str, list] = {}    # страна → [союзники]
        self.sanctions: Dict[str, list] = {}    # страна → [кто ввёл санкции]
        self.marionettes: Dict[str, str] = {}   # марионетка → хозяин
        self.annexed: Dict[str, str] = {}       # аннексированная → кем
        self.news_history: List[str] = []       # последние новости
        self.turn: int = 0                      # номер хода
        
        # Технологии (уровни 1-10)
        self.technologies = {
            "infantry": 1,      # пехота
            "tanks": 1,         # танки
            "artillery": 1,     # артиллерия
            "airforce": 1,      # авиация
            "navy": 1,          # флот
            "air_defense": 1,   # ПВО
            "drones": 1,        # дроны
            "cyber": 1,         # кибервойска
            "nuclear": 0,       # ядерное оружие (0 = нет)
            "space": 1,         # спутники/космос
        }
        
        # Инфраструктура
        self.infrastructure = {
            "factories": 1,         # заводы
            "research_labs": 1,     # лаборатории
            "hospitals": 1,         # госпитали
            "airbases": 1,          # авиабазы
            "ports": 0,             # порты
            "bunkers": 1,           # бункеры/укрепления
        }
    
    def get_power_rating(self, country: str) -> float:
        """Вычисляет рейтинг силы страны (0-100)"""
        if country not in self.countries:
            return 0
        
        c = self.countries[country]
        
        # Военная мощь
        military = (
            c.get("army_size", 0) * 0.3 +
            c.get("tanks", 0) * 0.5 +
            c.get("aircraft", 0) * 0.7 +
            c.get("ships", 0) * 0.4 +
            c.get("nukes", 0) * 10.0
        ) / 10000
        
        # Экономика
        economy = c.get("gdp", 0) / 1_000_000_000_000  # в триллионах
        
        # Технологии
        tech = sum(c.get("tech_levels", {}).values()) / 10
        
        # Союзники
        allies = len(self.alliances.get(country, [])) * 5
        
        return min(100, military * 0.5 + economy * 0.3 + tech * 0.1 + allies * 0.1)


# Глобальное состояние
world = WorldState()

# =====================================================================
# ТИПЫ МЕСТНОСТИ И ПОГОДЫ
# =====================================================================

TERRAIN_TYPES = {
    "plain": {
        "name": "равнина",
        "tank_mod": 1.5,
        "infantry_mod": 1.0,
        "air_mod": 1.0,
        "defense_bonus": 1.0,
    },
    "hills": {
        "name": "холмы",
        "tank_mod": 0.8,
        "infantry_mod": 1.1,
        "air_mod": 0.9,
        "defense_bonus": 1.3,
    },
    "forest": {
        "name": "лес",
        "tank_mod": 0.5,
        "infantry_mod": 1.3,
        "air_mod": 0.6,
        "defense_bonus": 1.8,
    },
    "mountains": {
        "name": "горы",
        "tank_mod": 0.1,
        "infantry_mod": 0.7,
        "air_mod": 0.5,
        "defense_bonus": 5.0,
    },
    "urban": {
        "name": "город",
        "tank_mod": 0.3,
        "infantry_mod": 1.5,
        "air_mod": 0.4,
        "defense_bonus": 3.0,
    },
    "desert": {
        "name": "пустыня",
        "tank_mod": 1.2,
        "infantry_mod": 0.8,
        "air_mod": 1.0,
        "defense_bonus": 0.8,
    },
    "swamp": {
        "name": "болото",
        "tank_mod": 0.2,
        "infantry_mod": 0.6,
        "air_mod": 0.8,
        "defense_bonus": 1.5,
    },
    "tundra": {
        "name": "тундра/зима",
        "tank_mod": 0.4,
        "infantry_mod": 0.5,
        "air_mod": 0.3,
        "defense_bonus": 1.2,
    },
}

WEATHER_TYPES = {
    "clear": {"name": "ясно", "air_mod": 1.0, "infantry_mod": 1.0, "supply_mod": 1.0},
    "rain": {"name": "дождь", "air_mod": 0.6, "infantry_mod": 0.9, "supply_mod": 0.8},
    "storm": {"name": "шторм", "air_mod": 0.2, "infantry_mod": 0.7, "supply_mod": 0.5},
    "snow": {"name": "снег", "air_mod": 0.3, "infantry_mod": 0.5, "supply_mod": 0.4},
    "fog": {"name": "туман", "air_mod": 0.1, "infantry_mod": 0.8, "supply_mod": 0.9},
}


# =====================================================================
# ДЕРЕВО РЕШЕНИЙ (20 ХОДОВ НАПЕРЁД)
# =====================================================================

class DecisionTree:
    """Просчитывает варианты на много ходов вперёд"""
    
    def __init__(self, max_depth: int = 20):
        self.max_depth = max_depth
        self.best_path = []
        self.best_score = -float("inf")
    
    async def evaluate(
        self,
        country: str,
        depth: int = 0,
        path: List[str] = None
    ) -> float:
        """
        Рекурсивно оценивает все варианты.
        Возвращает score (чем выше, тем лучше).
        """
        if path is None:
            path = []
        
        if depth >= self.max_depth:
            return self._calculate_score(country)
        
        my_power = world.get_power_rating(country)
        
        # Варианты действий
        options = []
        
        # 1. Экономическое развитие
        options.append(("develop_economy", 0.8))
        
        # 2. Военное развитие
        options.append(("develop_military", 0.7))
        
        # 3. Технологии
        options.append(("research_tech", 0.6))
        
        # 4. Дипломатия (если есть с кем)
        if len(world.countries) > 1:
            options.append(("diplomacy", 0.5))
        
        # 5. Война (только если преимущество > 60%)
        for target in world.countries:
            if target != country and target not in world.annexed:
                target_power = world.get_power_rating(target)
                if my_power > target_power * 1.5:
                    options.append((f"attack_{target}", 0.3))
        
        # 6. Аннексия марионетки
        for puppet, master in world.marionettes.items():
            if master == country:
                options.append((f"annex_{puppet}", 0.4))
        
        # Оцениваем каждый вариант
        best_option_score = -float("inf")
        best_option = None
        
        for option, base_prob in options:
            # Симулируем результат
            simulated_score = self._simulate_option(country, option, depth)
            
            # Рекурсивно смотрим дальше
            future_score = await self.evaluate(country, depth + 1, path + [option])
            
            total_score = simulated_score * 0.4 + future_score * 0.6
            
            if total_score > best_option_score:
                best_option_score = total_score
                best_option = option
        
        if depth == 0 and best_option:
            self.best_path = [best_option] + path
        
        return best_option_score
    
    def _simulate_option(self, country: str, option: str, depth: int) -> float:
        """Примерная оценка результата действия"""
        if option == "develop_economy":
            return 10.0 + depth * 0.5
        elif option == "develop_military":
            return 8.0 + depth * 0.3
        elif option == "research_tech":
            return 12.0 + depth * 0.7
        elif option == "diplomacy":
            return 6.0 + depth * 0.2
        elif option.startswith("attack_"):
            target = option.replace("attack_", "")
            my_power = world.get_power_rating(country)
            target_power = world.get_power_rating(target)
            if my_power > target_power * 2:
                return 20.0
            elif my_power > target_power * 1.5:
                return 10.0
            else:
                return -50.0  # Рискованно!
        elif option.startswith("annex_"):
            return 15.0
        
        return 0.0
    
    def _calculate_score(self, country: str) -> float:
        """Финальная оценка позиции"""
        power = world.get_power_rating(country)
        economy = world.countries.get(country, {}).get("gdp", 0) / 1e9
        tech = sum(world.technologies.values())
        allies = len(world.alliances.get(country, []))
        enemies = len(world.sanctions.get(country, []))
        
        return power * 2 + economy * 0.1 + tech * 0.5 + allies * 3 - enemies * 2


# =====================================================================
# ОСНОВНОЙ ЦИКЛ ПРИНЯТИЯ РЕШЕНИЙ
# =====================================================================

async def decision_loop(context=None):
    """
    ГЛАВНЫЙ ЦИКЛ.
    Запускается каждые DECISION_INTERVAL_MINUTES минут.
    Бот анализирует мир и принимает ВСЕ решения.
    """
    
    if bot_stopped:
        return
    
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    economy = get_economy(ADMIN_ID)
    
    if not economy:
        init_economy(ADMIN_ID)
        economy = get_economy(ADMIN_ID)
    
    world.turn += 1
    
    print(f"\n{'='*50}")
    print(f"🔄 ХОД {world.turn} | {country} | {year}")
    print(f"{'='*50}")
    
    # ============================================================
    # 1. АНАЛИЗ ТЕКУЩЕЙ СИТУАЦИИ
    # ============================================================
    
    # Собираем информацию о мире
    my_power = world.get_power_rating(country)
    enemies = list(world.sanctions.get(country, []))
    allies = world.alliances.get(country, [])
    wars_active = [w for w in world.wars.values() if w.get("status") == "active"]
    
    print(f"📊 Мощь: {my_power:.1f}/100")
    print(f"🤝 Союзники: {allies}")
    print(f"⚔️ Враги: {enemies}")
    print(f"🔥 Активные войны: {len(wars_active)}")
    print(f"💰 Бюджет: ${economy['budget']:,}")
    
    # ============================================================
    # 2. ЭКОНОМИЧЕСКИЕ РЕШЕНИЯ
    # ============================================================
    
    await economic_decisions(context, country, economy)
    
    # ============================================================
    # 3. ТЕХНОЛОГИЧЕСКИЕ РЕШЕНИЯ
    # ============================================================
    
    await tech_decisions(context, country, economy)
    
    # ============================================================
    # 4. ДИПЛОМАТИЧЕСКИЕ РЕШЕНИЯ
    # ============================================================
    
    await diplomatic_decisions(context, country, economy)
    
    # ============================================================
    # 5. ВОЕННЫЕ РЕШЕНИЯ
    # ============================================================
    
    await military_decisions(context, country, economy)
    
    # ============================================================
    # 6. СТРАТЕГИЧЕСКОЕ ПЛАНИРОВАНИЕ
    # ============================================================
    
    # Просчитываем дерево решений на 20 ходов
    tree = DecisionTree(max_depth=20)
    await tree.evaluate(country)
    
    if tree.best_path:
        print(f"🎯 Лучший путь: {' → '.join(tree.best_path[:5])}")
    
    # ============================================================
    # 7. ОТПРАВКА НОВОСТЕЙ (если накопились)
    # ============================================================
    
    if world.news_history:
        await send_accumulated_news(context, country)
    
    print(f"✅ Ход {world.turn} завершён\n")


# =====================================================================
# ЭКОНОМИЧЕСКИЕ РЕШЕНИЯ
# =====================================================================

async def economic_decisions(context, country: str, economy: dict):
    """Умное управление экономикой"""
    
    budget = economy['budget']
    steel = economy['steel']
    oil = economy['oil']
    
    # Если денег мало (< 5 млн) — продаём ресурсы
    if budget < 5_000_000:
        if steel > 1000:
            sell_amount = min(500, steel - 500)
            price = random.randint(600, 800)
            update_economy(
                ADMIN_ID,
                budget=budget + sell_amount * price,
                steel=steel - sell_amount
            )
            world.news_history.append(
                f"📉 *{country}* продала {sell_amount} тонн стали за ${sell_amount * price:,} "
                f"для пополнения бюджета."
            )
    
    # Если денег много (> 100 млн) — инвестируем
    elif budget > 100_000_000:
        invest_amount = min(budget - 50_000_000, random.randint(10_000_000, 50_000_000))
        
        # Выбираем куда инвестировать
        options = ["factories", "research_labs", "hospitals", "airbases", "bunkers"]
        choice = random.choice(options)
        
        world.infrastructure[choice] += 1
        update_economy(ADMIN_ID, budget=budget - invest_amount)
        
        world.news_history.append(
            f"🏗️ *{country}* инвестировала ${invest_amount:,} в строительство "
            f"{choice} (уровень {world.infrastructure[choice]})."
        )


# =====================================================================
# ТЕХНОЛОГИЧЕСКИЕ РЕШЕНИЯ
# =====================================================================

async def tech_decisions(context, country: str, economy: dict):
    """Разработка новых технологий"""
    
    budget = economy['budget']
    
    # Шанс разработки зависит от количества лабораторий
    labs = world.infrastructure.get("research_labs", 1)
    research_chance = min(0.3, 0.05 * labs)
    
    if random.random() < research_chance and budget > 10_000_000:
        # Выбираем технологию для разработки
        available_techs = [
            t for t, level in world.technologies.items()
            if level < 10 and t != "nuclear"
        ]
        
        if available_techs:
            tech = random.choice(available_techs)
            cost = (world.technologies[tech] + 1) * 5_000_000  # +5 млн за уровень
            
            if budget > cost:
                world.technologies[tech] += 1
                update_economy(ADMIN_ID, budget=budget - cost)
                
                world.news_history.append(
                    f"🔬 *{country}* разработала {tech} уровень {world.technologies[tech]}! "
                    f"Стоимость: ${cost:,}."
                )
                
                # Если технология крутая — спрашиваем AI про описание
                if world.technologies[tech] >= 5:
                    description = await ai.ask_groq(
                        f"Ты — {country}. Ты только что разработал {tech} уровня {world.technologies[tech]}. "
                        f"Опиши эту технологию одним предложением на русском. Будь реалистичным.",
                        system_prompt=ai.get_rp_system_prompt(),
                        temperature=0.7,
                        max_tokens=150
                    )
                    world.news_history.append(f"📡 *Описание:* {description}")


# =====================================================================
# ДИПЛОМАТИЧЕСКИЕ РЕШЕНИЯ
# =====================================================================

async def diplomatic_decisions(context, country: str, economy: dict):
    """Умная дипломатия"""
    
    my_power = world.get_power_rating(country)
    allies = world.alliances.get(country, [])
    
    # Если нет союзников — ищем
    if not allies and len(world.countries) > 1:
        for target_name, target_data in world.countries.items():
            if target_name != country and target_name not in world.annexed:
                target_power = world.get_power_rating(target_name)
                
                # Предлагаем союз только если это выгодно
                if target_power > 20 and random.random() < 0.3:
                    world.alliances.setdefault(country, []).append(target_name)
                    world.alliances.setdefault(target_name, []).append(country)
                    
                    world.news_history.append(
                        f"🤝 *{country}* предложила союз стране *{target_name}*."
                    )
                    break
    
    # Если есть враги — думаем о санкциях через ООН
    enemies = list(world.sanctions.get(country, []))
    if enemies and random.random() < 0.2:
        target = enemies[0]
        world.news_history.append(
            f"🏛️ *{country}* инициировала санкции против *{target}* в ООН."
        )
    
    # Если мы марионетка — оцениваем шансы на бунт
    if country in world.marionettes:
        master = world.marionettes[country]
        master_power = world.get_power_rating(master)
        
        # Если мы стали сильнее хозяина — БУНТ!
        if my_power > master_power * 1.2:
            world.news_history.append(
                f"🔥 *{country}* поднимает ВОССТАНИЕ против {master}!"
            )
            del world.marionettes[country]
            
            # Шанс на успех
            if my_power > master_power * 1.5:
                world.news_history.append(f"✅ Восстание успешно! {country} свободна!")
                # Можем даже захватить бывшего хозяина
                if random.random() < 0.3:
                    world.marionettes[master] = country
                    world.news_history.append(f"👑 Теперь {master} — марионетка {country}!")
            else:
                world.news_history.append(f"❌ Восстание подавлено. Репрессии усиливаются.")
                my_power *= 0.5  # Потери


# =====================================================================
# ВОЕННЫЕ РЕШЕНИЯ
# =====================================================================

async def military_decisions(context, country: str, economy: dict):
    """Гениальные военные решения"""
    
    my_power = world.get_power_rating(country)
    budget = economy['budget']
    
    # Проверяем активные войны
    for war_id, war in list(world.wars.items()):
        if war.get("status") != "active":
            continue
        
        attacker = war.get("attacker")
        defender = war.get("defender")
        
        # Если мы участвуем
        if country in [attacker, defender]:
            enemy = defender if country == attacker else attacker
            enemy_power = world.get_power_rating(enemy)
            
            # Оцениваем местность
            terrain = war.get("terrain", "plain")
            weather = war.get("weather", "clear")
            
            terrain_data = TERRAIN_TYPES.get(terrain, TERRAIN_TYPES["plain"])
            weather_data = WEATHER_TYPES.get(weather, WEATHER_TYPES["clear"])
            
            # Модификаторы
            tank_effectiveness = terrain_data["tank_mod"] * weather_data["air_mod"]
            air_effectiveness = terrain_data["air_mod"] * weather_data["air_mod"]
            
            # Если горы + зима = НЕВОЗМОЖНО наступать
            if terrain == "mountains" and weather in ["snow", "storm"]:
                world.news_history.append(
                    f"⛔ *{country}*: наступление невозможно! Горы и {weather_data['name']} "
                    f"блокируют все войска. Переходим к обороне."
                )
                war["strategy"] = "defense"
                continue
            
            # Если равнина + ясно = ИДЕАЛЬНО для блицкрига
            if terrain == "plain" and weather == "clear" and my_power > enemy_power * 1.3:
                world.news_history.append(
                    f"⚡ *{country}* начинает БЛИЦКРИГ против {enemy}!"
                )
                war["strategy"] = "blitzkrieg"
                
                # Блицкриг даёт бонус
                success_chance = 0.8 if my_power > enemy_power * 2 else 0.5
                if random.random() < success_chance:
                    world.news_history.append(f"💥 Блицкриг успешен! {enemy} разгромлена!")
                    
                    # Аннексия или марионетка
                    if random.random() < 0.6:
                        world.annexed[enemy] = country
                        world.news_history.append(f"🏴 {enemy} АННЕКСИРОВАНА {country}!")
                    else:
                        world.marionettes[enemy] = country
                        world.news_history.append(f"🎭 {enemy} становится марионеткой {country}.")
                    
                    war["status"] = "ended"
                    continue
            
            # Стандартный бой
            await fight_battle(war, country, enemy, terrain_data, weather_data)
    
    # Если нет активных войн — ищем возможности
    if not [w for w in world.wars.values() if w.get("status") == "active"]:
        await look_for_war_opportunities(context, country, my_power, budget)


async def fight_battle(war: dict, country: str, enemy: str, terrain: dict, weather: dict):
    """Один такт боя с учётом всех факторов"""
    
    attacker = war["attacker"]
    defender = war["defender"]
    
    # Силы сторон
    attacker_power = world.get_power_rating(attacker)
    defender_power = world.get_power_rating(defender)
    
    # Модификаторы
    if country == attacker:
        attack_mod = terrain.get("infantry_mod", 1.0) * weather.get("infantry_mod", 1.0)
        defense_mod = terrain["defense_bonus"] * weather.get("supply_mod", 1.0)
    else:
        attack_mod = terrain.get("infantry_mod", 1.0) * weather.get("infantry_mod", 1.0)
        defense_mod = terrain["defense_bonus"] * weather.get("supply_mod", 1.0) * 1.5
    
    # Потери (реалистичные)
    attacker_losses = int((defender_power * defense_mod * 0.1) * random.uniform(0.8, 1.2))
    defender_losses = int((attacker_power * attack_mod * 0.08) * random.uniform(0.8, 1.2))
    
    war["attacker_losses"] = war.get("attacker_losses", 0) + attacker_losses
    war["defender_losses"] = war.get("defender_losses", 0) + defender_losses
    
    # Кто выигрывает такт
    if attacker_losses < defender_losses:
        world.news_history.append(
            f"⚔️ {attacker} наступает! Потери: {attacker} -{attacker_losses}, {defender} -{defender_losses}"
        )
    else:
        world.news_history.append(
            f"🛡️ {defender} обороняется! Потери: {attacker} -{attacker_losses}, {defender} -{defender_losses}"
        )


async def look_for_war_opportunities(context, country: str, my_power: float, budget: int):
    """Ищем кого бы захватить (умно)"""
    
    # Не нападаем если бюджет маленький
    if budget < 50_000_000:
        return
    
    # Ищем слабые цели
    targets = []
    for target_name in world.countries:
        if target_name == country:
            continue
        if target_name in world.annexed:
            continue
        if target_name in world.marionettes:
            continue
        if target_name in world.alliances.get(country, []):
            continue  # Не нападаем на союзников
        
        target_power = world.get_power_rating(target_name)
        
        # Цель должна быть слабее в 1.5 раза минимум
        if target_power > 0 and my_power > target_power * 1.5:
            # Учитываем союзников цели
            target_allies = world.alliances.get(target_name, [])
            total_enemy_power = target_power + sum(
                world.get_power_rating(a) for a in target_allies
            )
            
            # Даже с союзниками враг должен быть слабее
            if my_power > total_enemy_power * 1.2:
                targets.append((target_name, target_power))
    
    if not targets:
        return
    
    # Выбираем самую слабую цель
    targets.sort(key=lambda x: x[1])
    target_name, target_power = targets[0]
    
    # 30% шанс объявить войну (не каждый ход)
    if random.random() < 0.3:
        war_id = f"{country}_{target_name}_{world.turn}"
        
        # Выбираем местность цели
        terrain = random.choice(list(TERRAIN_TYPES.keys()))
        
        world.wars[war_id] = {
            "attacker": country,
            "defender": target_name,
            "reason": "Стратегическая необходимость",
            "status": "active",
            "strategy": "balanced",
            "terrain": terrain,
            "weather": random.choice(list(WEATHER_TYPES.keys())),
            "attacker_losses": 0,
            "defender_losses": 0,
            "started_at": world.turn,
        }
        
        # Генерируем причину войны через AI
        reason = await ai.ask_groq(
            f"Ты — {country}. Ты объявляешь войну {target_name}. "
            f"Придумай ОДНУ реалистичную причину для войны (дипломатическую). "
            f"Одним предложением на русском.",
            system_prompt=ai.get_rp_system_prompt(),
            temperature=0.8,
            max_tokens=100
        )
        
        world.wars[war_id]["reason"] = reason
        
        world.news_history.append(
            f"⚔️ *{country}* объявляет войну *{target_name}*!\n"
            f"📌 Причина: {reason}\n"
            f"🌍 Местность: {TERRAIN_TYPES[terrain]['name']}"
        )
        
        # Отправляем в военный чат
        if context and saved_chats.get("war"):
            try:
                await context.bot.send_message(
                    chat_id=saved_chats["war"],
                    text=world.news_history[-1]
                )
            except:
                pass


# =====================================================================
# ОТПРАВКА НОВОСТЕЙ
# =====================================================================

async def send_accumulated_news(context, country: str):
    """Отправка накопленных новостей в новостной чат"""
    
    if not context or not saved_chats.get("news"):
        world.news_history.clear()
        return
    
    for news in world.news_history[:3]:  # Максимум 3 новости за раз
        try:
            await context.bot.send_message(
                chat_id=saved_chats["news"],
                text=f"📰 *Новости {country}*\n\n{news}",
                parse_mode="Markdown"
            )
            await asyncio.sleep(1)
        except Exception as e:
            print(f"❌ Ошибка отправки новости: {e}")
    
    world.news_history = world.news_history[3:]  # Убираем отправленные


# =====================================================================
# ИНИЦИАЛИЗАЦИЯ МИРА
# =====================================================================

async def init_world():
    """Инициализация мира при старте бота"""
    
    country = get_country(ADMIN_ID) or "Швейцария"
    
    # Получаем информацию о своей стране через интернет
    print(f"🌍 Исследуем {country}...")
    info = await ai.research_country(country)
    
    world.countries[country] = {
        "name": country,
        "army_size": 100000,
        "tanks": 1000,
        "aircraft": 500,
        "ships": 50,
        "nukes": 0,
        "gdp": 1_000_000_000_000,  # 1 триллион (условно)
        "tech_levels": world.technologies.copy(),
        "info": info.get("summary", ""),
    }
    
    # Добавляем несколько соседних стран для контекста
    neighbors = {
        "Франция": {"army_size": 200000, "gdp": 3_000_000_000_000},
        "Германия": {"army_size": 180000, "gdp": 4_500_000_000_000},
        "Италия": {"army_size": 160000, "gdp": 2_000_000_000_000},
        "Польша": {"army_size": 120000, "gdp": 700_000_000_000},
        "Австрия": {"army_size": 50000, "gdp": 480_000_000_000},
        "Чехия": {"army_size": 30000, "gdp": 280_000_000_000},
    }
    
    for name, data in neighbors.items():
        if name != country:
            world.countries[name] = {
                **data,
                "tanks": data["army_size"] // 100,
                "aircraft": data["army_size"] // 200,
                "ships": 20,
                "nukes": 0,
                "tech_levels": {k: random.randint(1, 5) for k in world.technologies},
            }
    
    # Случайные отношения
    for c in world.countries:
        if c != country and random.random() < 0.3:
            world.alliances.setdefault(country, []).append(c)
            world.alliances.setdefault(c, []).append(country)
    
    print(f"✅ Мир инициализирован: {len(world.countries)} стран")
    return info


# =====================================================================
# ФУНКЦИЯ ДЛЯ ТЕСТА
# =====================================================================

async def test_decision_engine():
    """Тест Decision Engine"""
    print("=" * 50)
    print("ТЕСТ DECISION ENGINE")
    print("=" * 50)
    
    # Инициализация
    await init_world()
    
    # Запуск одного цикла
    await decision_loop()
    
    # Статистика
    print(f"\n📊 Страны: {len(world.countries)}")
    print(f"⚔️ Войны: {len(world.wars)}")
    print(f"🤝 Альянсы: {len(world.alliances)}")
    print(f"🎭 Марионетки: {len(world.marionettes)}")
    print(f"🏴 Аннексии: {len(world.annexed)}")


if __name__ == "__main__":
    asyncio.run(test_decision_engine())
