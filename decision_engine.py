"""
DECISION ENGINE — МОЗГ ФЮРЕРА (IRON MAN MODE)
===============================================
Адаптивный ИИ-правитель для ЛЮБОЙ страны.
Характер: Гениальный стратег, не повторяет ошибок истории.
"""

import random
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import pytz

from config import (
    ADMIN_ID,
    saved_chats,
    bot_stopped,
    DECISION_INTERVAL_MINUTES
)
from ai_manager import ai
from history import (
    get_country,
    get_year,
    get_economy,
    update_economy,
    init_economy,
    save_country
)

# =====================================================================
# ВРЕМЯ И МЕСЯЦ
# =====================================================================

def get_rp_month() -> str:
    """Определяет игровой месяц по реальному часу (МСК)"""
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz)
    hour = now.hour
    month_index = (hour // 2) % 12
    months = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
    ]
    return months[month_index]

def get_current_season() -> str:
    """Определяет сезон по игровому месяцу"""
    month = get_rp_month()
    seasons = {
        "декабрь": "winter", "январь": "winter", "февраль": "winter",
        "март": "spring", "апрель": "spring", "май": "spring",
        "июнь": "summer", "июль": "summer", "август": "summer",
        "сентябрь": "autumn", "октябрь": "autumn", "ноябрь": "autumn",
    }
    return seasons.get(month, "summer")

def get_season_effects() -> dict:
    """Возвращает модификаторы для текущего сезона"""
    season = get_current_season()
    effects = {
        "winter": {
            "attack_mod": 0.5,
            "defense_mod": 0.8,
            "supply_mod": 0.4,
            "air_mod": 0.3,
            "tank_mod": 0.4,
            "description": "❄️ Зима: наступление затруднено, техника замерзает"
        },
        "spring": {
            "attack_mod": 0.8,
            "defense_mod": 1.0,
            "supply_mod": 0.7,
            "air_mod": 0.7,
            "tank_mod": 0.6,
            "description": "🌱 Весна: распутица, но лучше чем зимой"
        },
        "summer": {
            "attack_mod": 1.3,
            "defense_mod": 1.0,
            "supply_mod": 1.2,
            "air_mod": 1.2,
            "tank_mod": 1.3,
            "description": "☀️ Лето: идеальное время для наступления!"
        },
        "autumn": {
            "attack_mod": 0.9,
            "defense_mod": 1.1,
            "supply_mod": 0.8,
            "air_mod": 0.8,
            "tank_mod": 0.9,
            "description": "🍂 Осень: дожди, но ещё можно воевать"
        },
    }
    return effects.get(season, effects["summer"])

# =====================================================================
# ТИПЫ СТРАН И ИХ ОСОБЕННОСТИ
# =====================================================================

class CountryProfile:
    """Профиль страны — определяет стиль игры"""
    
    def __init__(self, name: str, info: dict = None):
        self.name = name
        self.info = info or {}
        self.profile_type = self._determine_type()
        self.bonuses = self._get_bonuses()
        self.restrictions = self._get_restrictions()
    
    def _determine_type(self) -> str:
        """Определяет тип страны по названию и данным"""
        name_lower = self.name.lower()
        
        # Горные страны
        mountain_countries = ["швейцария", "австрия", "непал", "тибет", "бутан", "андорра"]
        if any(c in name_lower for c in mountain_countries):
            return "mountain_fortress"
        
        # Островные страны
        island_countries = ["великобритания", "япония", "индонезия", "филиппины", "мадагаскар"]
        if any(c in name_lower for c in island_countries):
            return "naval_power"
        
        # Малые страны
        micro_countries = ["люксембург", "ватикан", "монако", "лихтенштейн", "сан-марино", "мальта"]
        if any(c in name_lower for c in micro_countries):
            return "micro_state"
        
        # Крупные державы
        superpowers = ["сша", "китай", "россия", "индия"]
        if any(c in name_lower for c in superpowers):
            return "superpower"
        
        # Военные державы
        military_powers = ["германия", "франция", "турция", "израиль", "пакистан", "бразилия"]
        if any(c in name_lower for c in military_powers):
            return "military_power"
        
        # Экономические центры
        economic_centers = ["сингапур", "оаэ", "катар", "швеция", "нидерланды", "бельгия"]
        if any(c in name_lower for c in economic_centers):
            return "economic_center"
        
        return "regional_power"
    
    def _get_bonuses(self) -> dict:
        """Бонусы в зависимости от типа страны"""
        bonuses = {
            "mountain_fortress": {
                "defense": 3.0,
                "guerilla": 2.0,
                "attrition": 1.5,
                "description": "🏔️ Горная крепость: защита x3, партизаны x2"
            },
            "naval_power": {
                "navy": 2.0,
                "trade": 1.5,
                "blockade": 1.8,
                "description": "🚢 Морская держава: флот x2, торговля x1.5"
            },
            "micro_state": {
                "stealth": 2.5,
                "diplomacy": 2.0,
                "banking": 2.5,
                "description": "🏦 Микро-государство: банки x2.5, дипломатия x2"
            },
            "superpower": {
                "military": 1.5,
                "economy": 1.5,
                "tech": 1.3,
                "description": "💪 Сверхдержава: армия x1.5, экономика x1.5"
            },
            "military_power": {
                "army": 1.4,
                "blitzkrieg": 1.3,
                "production": 1.3,
                "description": "⚔️ Военная держава: армия x1.4, блицкриг x1.3"
            },
            "economic_center": {
                "trade": 2.0,
                "tech_speed": 1.5,
                "influence": 1.8,
                "description": "💰 Экономический центр: торговля x2, технологии x1.5"
            },
            "regional_power": {
                "balanced": 1.1,
                "adaptation": 1.2,
                "description": "🏛️ Региональная держава: сбалансированное развитие"
            },
        }
        return bonuses.get(self.profile_type, bonuses["regional_power"])
    
    def _get_restrictions(self) -> dict:
        """Ограничения в зависимости от типа страны"""
        restrictions = {
            "mountain_fortress": {
                "max_tanks": 0.3,
                "max_airforce": 0.5,
                "description": "⚠️ Танки и авиация неэффективны в горах"
            },
            "naval_power": {
                "max_land_army": 0.7,
                "description": "⚠️ Сухопутная армия ограничена"
            },
            "micro_state": {
                "max_army_size": 0.05,
                "max_nukes": 0,
                "description": "⚠️ Армия ограничена размером страны"
            },
            "superpower": {
                "diplomatic_penalty": 0.7,
                "description": "⚠️ Все боятся гегемона"
            },
            "military_power": {
                "diplomatic_penalty": 0.8,
                "description": "⚠️ Соседи насторожены"
            },
            "economic_center": {
                "max_military": 0.6,
                "description": "⚠️ Фокус на экономике, не на войне"
            },
            "regional_power": {
                "description": "✅ Нет серьёзных ограничений"
            },
        }
        return restrictions.get(self.profile_type, {"description": "✅ Нет ограничений"})

# =====================================================================
# ГЛОБАЛЬНОЕ СОСТОЯНИЕ МИРА (ОБНОВЛЁННОЕ)
# =====================================================================

class WorldState:
    """Хранит информацию о всех странах и отношениях"""
    
    def __init__(self):
        self.countries: Dict[str, dict] = {}
        self.country_profiles: Dict[str, CountryProfile] = {}
        self.wars: Dict[str, dict] = {}
        self.alliances: Dict[str, list] = {}
        self.sanctions: Dict[str, list] = {}
        self.marionettes: Dict[str, str] = {}
        self.annexed: Dict[str, str] = {}
        self.news_history: List[str] = []
        self.turn: int = 0
        self.year: int = 2024
        self.month: str = "январь"
        
        # Технологии (уровни 1-10)
        self.technologies = {
            "infantry": 1,
            "tanks": 1,
            "artillery": 1,
            "airforce": 1,
            "navy": 1,
            "air_defense": 1,
            "drones": 1,
            "cyber": 1,
            "nuclear": 0,
            "space": 1,
        }
        
        # Инфраструктура
        self.infrastructure = {
            "factories": 1,
            "research_labs": 1,
            "hospitals": 1,
            "airbases": 1,
            "ports": 0,
            "bunkers": 1,
            "mountain_forts": 0,
        }
    
    def get_power_rating(self, country: str) -> float:
        """Вычисляет рейтинг силы страны (0-100) с учётом профиля"""
        if country not in self.countries:
            return 0
        
        c = self.countries[country]
        profile = self.country_profiles.get(country)
        bonuses = profile.bonuses if profile else {}
        
        # Базовая военная мощь
        military = (
            c.get("army_size", 0) * 0.3 * bonuses.get("army", 1.0) * bonuses.get("military", 1.0) +
            c.get("tanks", 0) * 0.5 * bonuses.get("army", 1.0) +
            c.get("aircraft", 0) * 0.7 * bonuses.get("airforce", 1.0) +
            c.get("ships", 0) * 0.4 * bonuses.get("navy", 1.0) +
            c.get("nukes", 0) * 10.0
        ) / 10000
        
        # Экономика
        economy = c.get("gdp", 0) / 1_000_000_000_000 * bonuses.get("economy", 1.0)
        
        # Технологии
        tech = sum(self.technologies.values()) / 10 * bonuses.get("tech", 1.0)
        
        # Союзники
        allies = len(self.alliances.get(country, [])) * 5 * bonuses.get("diplomacy", 1.0)
        
        return min(100, military * 0.5 + economy * 0.3 + tech * 0.1 + allies * 0.1)
    
    def get_effective_terrain(self, country: str) -> str:
        """Определяет эффективный тип местности с учётом инфраструктуры"""
        profile = self.country_profiles.get(country)
        if not profile:
            return "plain"
        
        # Горные крепости всегда имеют бонус гор
        if profile.profile_type == "mountain_fortress":
            forts = self.infrastructure.get("mountain_forts", 0)
            if forts > 0:
                return "mountains"  # Искусственные укрепления как горы
        
        return "plain"

# Глобальное состояние
world = WorldState()

# =====================================================================
# ТИПЫ МЕСТНОСТИ И ПОГОДЫ (БЕЗ ИЗМЕНЕНИЙ)
# =====================================================================

TERRAIN_TYPES = {
    "plain": {"name": "равнина", "tank_mod": 1.5, "infantry_mod": 1.0, "air_mod": 1.0, "defense_bonus": 1.0},
    "hills": {"name": "холмы", "tank_mod": 0.8, "infantry_mod": 1.1, "air_mod": 0.9, "defense_bonus": 1.3},
    "forest": {"name": "лес", "tank_mod": 0.5, "infantry_mod": 1.3, "air_mod": 0.6, "defense_bonus": 1.8},
    "mountains": {"name": "горы", "tank_mod": 0.1, "infantry_mod": 0.7, "air_mod": 0.5, "defense_bonus": 5.0},
    "urban": {"name": "город", "tank_mod": 0.3, "infantry_mod": 1.5, "air_mod": 0.4, "defense_bonus": 3.0},
    "desert": {"name": "пустыня", "tank_mod": 1.2, "infantry_mod": 0.8, "air_mod": 1.0, "defense_bonus": 0.8},
    "swamp": {"name": "болото", "tank_mod": 0.2, "infantry_mod": 0.6, "air_mod": 0.8, "defense_bonus": 1.5},
    "tundra": {"name": "тундра/зима", "tank_mod": 0.4, "infantry_mod": 0.5, "air_mod": 0.3, "defense_bonus": 1.2},
}

WEATHER_TYPES = {
    "clear": {"name": "ясно", "air_mod": 1.0, "infantry_mod": 1.0, "supply_mod": 1.0},
    "rain": {"name": "дождь", "air_mod": 0.6, "infantry_mod": 0.9, "supply_mod": 0.8},
    "storm": {"name": "шторм", "air_mod": 0.2, "infantry_mod": 0.7, "supply_mod": 0.5},
    "snow": {"name": "снег", "air_mod": 0.3, "infantry_mod": 0.5, "supply_mod": 0.4},
    "fog": {"name": "туман", "air_mod": 0.1, "infantry_mod": 0.8, "supply_mod": 0.9},
}

# =====================================================================
# ОСНОВНОЙ ЦИКЛ ПРИНЯТИЯ РЕШЕНИЙ (АДАПТИВНЫЙ)
# =====================================================================

async def decision_loop(context=None):
    """
    ГЛАВНЫЙ ЦИКЛ IRON MAN.
    Адаптируется под ЛЮБУЮ страну.
    Запускается каждые DECISION_INTERVAL_MINUTES минут.
    """
    
    if bot_stopped:
        return
    
    country = get_country(ADMIN_ID) or "Швейцария"
    world.year = get_year(ADMIN_ID) or 2024
    world.month = get_rp_month()
    economy = get_economy(ADMIN_ID)
    
    if not economy:
        init_economy(ADMIN_ID)
        economy = get_economy(ADMIN_ID)
    
    # Обновляем профиль страны (вдруг сменили)
    if country not in world.country_profiles:
        world.country_profiles[country] = CountryProfile(country)
    
    profile = world.country_profiles[country]
    season_effects = get_season_effects()
    world.turn += 1
    
    print(f"\n{'='*50}")
    print(f"🔄 ХОД {world.turn} | {country} | {world.month} {world.year}")
    print(f"📊 Профиль: {profile.profile_type} — {profile.bonuses.get('description', '')}")
    print(f"{'='*50}")
    
    # ============================================================
    # 1. АНАЛИЗ СИТУАЦИИ
    # ============================================================
    my_power = world.get_power_rating(country)
    enemies = list(world.sanctions.get(country, []))
    allies = world.alliances.get(country, [])
    wars_active = [w for w in world.wars.values() if w.get("status") == "active"]
    
    print(f"📊 Мощь: {my_power:.1f}/100 | Сезон: {season_effects['description']}")
    print(f"🤝 Союзники: {allies} | ⚔️ Враги: {enemies}")
    print(f"💰 Бюджет: ${economy['budget']:,}")
    
    # ============================================================
    # 2. АДАПТИВНАЯ СТРАТЕГИЯ
    # ============================================================
    
    if profile.profile_type == "micro_state":
        # Микро-государства НЕ воюют — используют дипломатию и банки
        await micro_state_strategy(context, country, economy, profile)
    
    elif profile.profile_type == "mountain_fortress":
        # Горные крепости: оборона, измот врага
        await mountain_strategy(context, country, economy, profile, season_effects)
    
    elif profile.profile_type == "naval_power":
        # Морские державы: блокады, торговля, десанты
        await naval_strategy(context, country, economy, profile, season_effects)
    
    elif profile.profile_type == "superpower":
        # Сверхдержавы: доминирование, прокси-войны
        await superpower_strategy(context, country, economy, profile, season_effects)
    
    elif profile.profile_type == "military_power":
        # Военные державы: блицкриги, технологии
        await military_strategy(context, country, economy, profile, season_effects)
    
    elif profile.profile_type == "economic_center":
        # Экономики: скупать ослабших, давить санкциями
        await economic_strategy(context, country, economy, profile)
    
    else:
        # Региональные державы: сбалансированно
        await balanced_strategy(context, country, economy, profile, season_effects)
    
    # ============================================================
    # 3. ТЕХНОЛОГИИ И ИНФРАСТРУКТУРА (ДЛЯ ВСЕХ)
    # ============================================================
    await tech_decisions(context, country, economy, profile)
    await infrastructure_decisions(context, country, economy, profile)
    
    # ============================================================
    # 4. ОТПРАВКА НОВОСТЕЙ
    # ============================================================
    if world.news_history:
        await send_accumulated_news(context, country)
    
    print(f"✅ Ход {world.turn} завершён\n")

# =====================================================================
# СТРАТЕГИИ ДЛЯ РАЗНЫХ ТИПОВ СТРАН
# =====================================================================

async def micro_state_strategy(context, country: str, economy: dict, profile: CountryProfile):
    """Стратегия микро-государства: банки, дипломатия, шпионаж"""
    
    budget = economy['budget']
    banking_bonus = profile.bonuses.get("banking", 2.0)
    
    # Доход от банков
    bank_income = int(5_000_000 * banking_bonus * (1 + world.turn * 0.01))
    update_economy(ADMIN_ID, budget=budget + bank_income)
    
    if world.turn % 5 == 0:  # Каждые 5 ходов
        world.news_history.append(
            f"🏦 *{country}* заработал ${bank_income:,} на банковских операциях."
        )
    
    # Ищем кому предложить финансовые услуги
    for target in world.countries:
        if target != country and random.random() < 0.2:
            world.news_history.append(
                f"💰 *{country}* предлагает {target} выгодные кредиты."
            )

async def mountain_strategy(context, country: str, economy: dict, profile: CountryProfile, season):
    """Стратегия горной крепости: непробиваемая оборона"""
    
    budget = economy['budget']
    defense_bonus = profile.bonuses.get("defense", 3.0)
    
    # Строим горные форты
    if budget > 10_000_000 and random.random() < 0.3:
        cost = 8_000_000
        world.infrastructure["mountain_forts"] += 1
        update_economy(ADMIN_ID, budget=budget - cost)
        world.news_history.append(
            f"🏔️ *{country}* укрепила горные перевалы! "
            f"Оборона x{defense_bonus * (1 + world.infrastructure['mountain_forts'] * 0.2):.1f}"
        )
    
    # Предупреждаем врагов
    if world.turn % 7 == 0:
        world.news_history.append(
            f"⚠️ *{country}*: 'Альпы неприступны. Не пытайтесь.'"
        )

async def naval_strategy(context, country: str, economy: dict, profile: CountryProfile, season):
    """Стратегия морской державы: флот, блокады, колонии"""
    pass  # Будет дополнено

async def superpower_strategy(context, country: str, economy: dict, profile: CountryProfile, season):
    """Стратегия сверхдержавы: глобальное доминирование"""
    pass  # Будет дополнено

async def military_strategy(context, country: str, economy: dict, profile: CountryProfile, season):
    """Стратегия военной державы: блицкриги"""
    
    my_power = world.get_power_rating(country)
    budget = economy['budget']
    
    # Если лето и мы сильны — ищем цель
    if season["attack_mod"] > 1.0 and my_power > 50:
        await look_for_war_opportunities(context, country, my_power, budget, profile, season)

async def economic_strategy(context, country: str, economy: dict, profile: CountryProfile):
    """Стратегия экономического центра: скупка активов"""
    pass  # Будет дополнено

async def balanced_strategy(context, country: str, economy: dict, profile: CountryProfile, season):
    """Сбалансированная стратегия: всего понемногу"""
    pass  # Будет дополнено

# =====================================================================
# ТЕХНОЛОГИИ (АДАПТИВНЫЕ)
# =====================================================================

async def tech_decisions(context, country: str, economy: dict, profile: CountryProfile):
    """Разработка технологий с учётом профиля страны"""
    
    budget = economy['budget']
    labs = world.infrastructure.get("research_labs", 1)
    tech_speed = profile.bonuses.get("tech_speed", 1.0)
    
    research_chance = min(0.4, 0.05 * labs * tech_speed)
    
    if random.random() < research_chance and budget > 10_000_000:
        # Выбираем технологию, подходящую для профиля
        tech_priorities = get_tech_priorities(profile)
        
        available = [t for t in tech_priorities if world.technologies.get(t, 1) < 10]
        if available:
            tech = random.choice(available[:3])  # Приоритет первым трём
            cost = (world.technologies[tech] + 1) * 5_000_000
            
            if budget > cost:
                world.technologies[tech] += 1
                update_economy(ADMIN_ID, budget=budget - cost)
                world.news_history.append(
                    f"🔬 *{country}* улучшила {tech} до уровня {world.technologies[tech]}!"
                )

def get_tech_priorities(profile: CountryProfile) -> list:
    """Возвращает приоритетные технологии для типа страны"""
    priorities = {
        "mountain_fortress": ["air_defense", "infantry", "drones", "artillery", "cyber"],
        "naval_power": ["navy", "airforce", "drones", "cyber", "space"],
        "micro_state": ["cyber", "drones", "space", "air_defense", "infantry"],
        "superpower": ["nuclear", "space", "airforce", "navy", "tanks"],
        "military_power": ["tanks", "airforce", "artillery", "drones", "infantry"],
        "economic_center": ["cyber", "drones", "space", "airforce", "navy"],
        "regional_power": ["infantry", "tanks", "artillery", "airforce", "air_defense"],
    }
    return priorities.get(profile.profile_type, ["infantry", "tanks", "airforce"])

# =====================================================================
# ИНФРАСТРУКТУРА
# =====================================================================

async def infrastructure_decisions(context, country: str, economy: dict, profile: CountryProfile):
    """Строительство инфраструктуры с учётом профиля"""
    
    budget = economy['budget']
    
    if budget > 20_000_000:
        # Приоритеты строительства
        build_priorities = get_build_priorities(profile)
        
        choice = random.choice(build_priorities[:3])
        cost = 15_000_000
        
        if budget > cost:
            world.infrastructure[choice] = world.infrastructure.get(choice, 1) + 1
            update_economy(ADMIN_ID, budget=budget - cost)
            world.news_history.append(
                f"🏗️ *{country}* построила {choice} (уровень {world.infrastructure[choice]})"
            )

def get_build_priorities(profile: CountryProfile) -> list:
    """Приоритеты строительства для типа страны"""
    priorities = {
        "mountain_fortress": ["bunkers", "mountain_forts", "hospitals", "factories"],
        "naval_power": ["ports", "airbases", "factories", "research_labs"],
        "micro_state": ["research_labs", "hospitals", "bunkers"],
        "superpower": ["factories", "airbases", "ports", "research_labs"],
        "military_power": ["factories", "airbases", "bunkers", "research_labs"],
        "economic_center": ["research_labs", "factories", "ports"],
        "regional_power": ["factories", "airbases", "hospitals", "research_labs"],
    }
    return priorities.get(profile.profile_type, ["factories", "research_labs"])

# =====================================================================
# ПОИСК ВОЗМОЖНОСТЕЙ ДЛЯ ВОЙНЫ
# =====================================================================

async def look_for_war_opportunities(context, country: str, my_power: float, budget: int, profile: CountryProfile, season: dict):
    """Ищем кого бы захватить (умно, с учётом профиля и сезона)"""
    
    # Микро-государства не нападают
    if profile.profile_type == "micro_state":
        return
    
    # Зимой не нападаем если не сверхдержава
    if season["attack_mod"] < 0.6 and profile.profile_type != "superpower":
        return
    
    # Не нападаем если бюджет маленький
    if budget < 50_000_000:
        return
    
    targets = []
    for target_name in world.countries:
        if target_name == country:
            continue
        if target_name in world.annexed or target_name in world.marionettes:
            continue
        if target_name in world.alliances.get(country, []):
            continue
        
        target_power = world.get_power_rating(target_name)
        target_profile = world.country_profiles.get(target_name)
        
        # Горные крепости не атакуем
        if target_profile and target_profile.profile_type == "mountain_fortress":
            world.news_history.append(
                f"⛔ *{country}* отказывается от атаки на {target_name}: горы неприступны."
            )
            continue
        
        # Цель должна быть слабее с учётом её бонусов защиты
        target_defense = target_profile.bonuses.get("defense", 1.0) if target_profile else 1.0
        effective_target_power = target_power * target_defense / season["attack_mod"]
        
        if my_power > effective_target_power * 1.5:
            targets.append((target_name, target_power, target_defense))
    
    if not targets:
        return
    
    # Выбираем самую слабую цель
    targets.sort(key=lambda x: x[1])
    target_name, target_power, target_defense = targets[0]
    
    if random.random() < 0.3:
        war_id = f"{country}_{target_name}_{world.turn}"
        
        terrain = "plain"
        if target_defense > 1.5:
            terrain = "hills"
        elif target_defense > 2.5:
            terrain = "mountains"
        
        # Причина войны через AI
        reason = await ai.ask_groq(
            f"Ты — {country}. Ты хочешь объявить войну {target_name}. "
            f"Твой профиль: {profile.profile_type}. Придумай ОДНУ реалистичную причину. "
            f"Учти что сейчас {world.month} {world.year} года ({season['description']}).",
            system_prompt=ai.get_rp_system_prompt(),
            temperature=0.8,
            max_tokens=100
        )
        
        world.wars[war_id] = {
            "attacker": country,
            "defender": target_name,
            "reason": reason,
            "status": "active",
            "strategy": "blitzkrieg" if season["attack_mod"] > 1.0 else "balanced",
            "terrain": terrain,
            "weather": "snow" if "зима" in season["description"] else "clear",
            "attacker_losses": 0,
            "defender_losses": 0,
            "started_at": world.turn,
        }
        
        world.news_history.append(
            f"⚔️ *{country}* объявляет войну *{target_name}*!\n"
            f"📌 Причина: {reason}\n"
            f"🌍 Местность: {TERRAIN_TYPES[terrain]['name']}\n"
            f"🌤️ Сезон: {season['description']}"
        )
        
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
    
    for news in world.news_history[:3]:
        try:
            await context.bot.send_message(
                chat_id=saved_chats["news"],
                text=f"📰 *{country} | {world.month} {world.year}*\n\n{news}",
                parse_mode="Markdown"
            )
            await asyncio.sleep(1)
        except Exception as e:
            print(f"❌ Ошибка отправки новости: {e}")
    
    world.news_history = world.news_history[3:]

# =====================================================================
# ИНИЦИАЛИЗАЦИЯ МИРА (АДАПТИВНАЯ)
# =====================================================================

async def init_world():
    """Инициализация мира с исследованием страны через интернет"""
    
    country = get_country(ADMIN_ID) or "Швейцария"
    world.year = get_year(ADMIN_ID) or 2024
    world.month = get_rp_month()
    
    print(f"🌍 Исследуем {country}...")
    info = await ai.research_country(country)
    
    # Создаём профиль
    profile = CountryProfile(country, info)
    world.country_profiles[country] = profile
    
    # Определяем стартовые параметры на основе профиля
    if profile.profile_type == "micro_state":
        army_size = 5000
        tanks = 10
        gdp = 50_000_000_000
    elif profile.profile_type == "superpower":
        army_size = 1_000_000
        tanks = 5000
        gdp = 20_000_000_000_000
    elif profile.profile_type == "mountain_fortress":
        army_size = 50000
        tanks = 100
        gdp = 500_000_000_000
    elif profile.profile_type == "military_power":
        army_size = 300_000
        tanks = 2000
        gdp = 2_000_000_000_000
    elif profile.profile_type == "naval_power":
        army_size = 150_000
        tanks = 500
        gdp = 2_500_000_000_000
    elif profile.profile_type == "economic_center":
        army_size = 50000
        tanks = 200
        gdp = 5_000_000_000_000
    else:
        army_size = 100_000
        tanks = 1000
        gdp = 1_000_000_000_000
    
    world.countries[country] = {
        "name": country,
        "army_size": army_size,
        "tanks": tanks,
        "aircraft": army_size // 200,
        "ships": 100 if profile.profile_type == "naval_power" else 20,
        "nukes": 5000 if profile.profile_type == "superpower" else 0,
        "gdp": gdp,
        "tech_levels": world.technologies.copy(),
        "info": info.get("summary", ""),
    }
    
    # Соседи
    neighbors = {
        "Франция": {"army_size": 200000, "gdp": 3_000_000_000_000},
        "Германия": {"army_size": 180000, "gdp": 4_500_000_000_000},
        "Италия": {"army_size": 160000, "gdp": 2_000_000_000_000},
        "Польша": {"army_size": 120000, "gdp": 700_000_000_000},
        "Австрия": {"army_size": 50000, "gdp": 480_000_000_000},
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
            world.country_profiles[name] = CountryProfile(name)
    
    print(f"✅ Мир инициализирован: {len(world.countries)} стран")
    print(f"📊 Профиль {country}: {profile.profile_type}")
    print(f"💪 Бонусы: {profile.bonuses.get('description', '')}")
    print(f"⚠️ Ограничения: {profile.restrictions.get('description', '')}")
    
    return info

# =====================================================================
# ТЕСТ
# =====================================================================

async def test_decision_engine():
    """Тест Decision Engine"""
    print("=" * 50)
    print("ТЕСТ DECISION ENGINE (АДАПТИВНЫЙ)")
    print("=" * 50)
    
    await init_world()
    await decision_loop()
    
    country = get_country(ADMIN_ID) or "Швейцария"
    profile = world.country_profiles.get(country)
    
    print(f"\n📊 Итоговая статистика:")
    print(f"   Страна: {country}")
    print(f"   Профиль: {profile.profile_type if profile else 'неизвестно'}")
    print(f"   Сила: {world.get_power_rating(country):.1f}/100")
    print(f"   Месяц: {world.month} {world.year}")
    print(f"   Новостей: {len(world.news_history)}")

if __name__ == "__main__":
    asyncio.run(test_decision_engine())
