"""
DECISION ENGINE — МОЗГ ФЮРЕРА (IRON MAN MODE)
===============================================
Адаптивный ИИ-правитель для ЛЮБОЙ страны.
С ИИ-анализом мировой напряжённости.
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
    month = get_rp_month()
    seasons = {
        "декабрь": "winter", "январь": "winter", "февраль": "winter",
        "март": "spring", "апрель": "spring", "май": "spring",
        "июнь": "summer", "июль": "summer", "август": "summer",
        "сентябрь": "autumn", "октябрь": "autumn", "ноябрь": "autumn",
    }
    return seasons.get(month, "summer")

def get_season_effects() -> dict:
    season = get_current_season()
    effects = {
        "winter": {"attack_mod": 0.5, "defense_mod": 0.8, "supply_mod": 0.4, "air_mod": 0.3, "tank_mod": 0.4, "description": "❄️ Зима: наступление затруднено"},
        "spring": {"attack_mod": 0.8, "defense_mod": 1.0, "supply_mod": 0.7, "air_mod": 0.7, "tank_mod": 0.6, "description": "🌱 Весна: распутица"},
        "summer": {"attack_mod": 1.3, "defense_mod": 1.0, "supply_mod": 1.2, "air_mod": 1.2, "tank_mod": 1.3, "description": "☀️ Лето: идеальное время!"},
        "autumn": {"attack_mod": 0.9, "defense_mod": 1.1, "supply_mod": 0.8, "air_mod": 0.8, "tank_mod": 0.9, "description": "🍂 Осень: дожди"},
    }
    return effects.get(season, effects["summer"])

# =====================================================================
# ТИПЫ СТРАН
# =====================================================================

class CountryProfile:
    def __init__(self, name: str, info: dict = None):
        self.name = name
        self.info = info or {}
        self.profile_type = self._determine_type()
        self.bonuses = self._get_bonuses()
        self.restrictions = self._get_restrictions()
    
    def _determine_type(self) -> str:
        name_lower = self.name.lower()
        if any(c in name_lower for c in ["швейцария", "австрия", "непал", "тибет", "бутан"]):
            return "mountain_fortress"
        if any(c in name_lower for c in ["великобритания", "япония", "индонезия"]):
            return "naval_power"
        if any(c in name_lower for c in ["люксембург", "ватикан", "монако", "лихтенштейн"]):
            return "micro_state"
        if any(c in name_lower for c in ["сша", "китай", "россия", "индия"]):
            return "superpower"
        if any(c in name_lower for c in ["германия", "франция", "турция", "израиль"]):
            return "military_power"
        if any(c in name_lower for c in ["сингапур", "оаэ", "катар", "швеция"]):
            return "economic_center"
        return "regional_power"
    
    def _get_bonuses(self) -> dict:
        bonuses = {
            "mountain_fortress": {"defense": 3.0, "guerilla": 2.0, "description": "🏔️ Горная крепость"},
            "naval_power": {"navy": 2.0, "trade": 1.5, "description": "🚢 Морская держава"},
            "micro_state": {"stealth": 2.5, "diplomacy": 2.0, "banking": 2.5, "description": "🏦 Микро-государство"},
            "superpower": {"military": 1.5, "economy": 1.5, "tech": 1.3, "description": "💪 Сверхдержава"},
            "military_power": {"army": 1.4, "blitzkrieg": 1.3, "description": "⚔️ Военная держава"},
            "economic_center": {"trade": 2.0, "tech_speed": 1.5, "description": "💰 Экономический центр"},
            "regional_power": {"balanced": 1.1, "description": "🏛️ Региональная держава"},
        }
        return bonuses.get(self.profile_type, bonuses["regional_power"])
    
    def _get_restrictions(self) -> dict:
        restrictions = {
            "mountain_fortress": {"max_tanks": 0.3, "description": "⚠️ Танки неэффективны в горах"},
            "naval_power": {"max_land_army": 0.7, "description": "⚠️ Сухопутная армия ограничена"},
            "micro_state": {"max_army_size": 0.05, "description": "⚠️ Армия ограничена размером"},
            "superpower": {"diplomatic_penalty": 0.7, "description": "⚠️ Все боятся гегемона"},
            "military_power": {"diplomatic_penalty": 0.8, "description": "⚠️ Соседи насторожены"},
            "economic_center": {"max_military": 0.6, "description": "⚠️ Фокус на экономике"},
            "regional_power": {"description": "✅ Нет ограничений"},
        }
        return restrictions.get(self.profile_type, {"description": "✅ Нет ограничений"})

# =====================================================================
# МИР
# =====================================================================

class WorldState:
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
        self.world_tension: float = 0.0
        
        self.technologies = {
            "infantry": 1, "tanks": 1, "artillery": 1, "airforce": 1,
            "navy": 1, "air_defense": 1, "drones": 1, "cyber": 1,
            "nuclear": 0, "space": 1,
        }
        
        self.infrastructure = {
            "factories": 1, "research_labs": 1, "hospitals": 1,
            "airbases": 1, "ports": 0, "bunkers": 1, "mountain_forts": 0,
        }
    
    def get_power_rating(self, country: str) -> float:
        if country not in self.countries:
            return 0
        c = self.countries[country]
        profile = self.country_profiles.get(country)
        bonuses = profile.bonuses if profile else {}
        
        military = (
            c.get("army_size", 0) * 0.3 * bonuses.get("army", 1.0) +
            c.get("tanks", 0) * 0.5 +
            c.get("aircraft", 0) * 0.7 +
            c.get("ships", 0) * 0.4 +
            c.get("nukes", 0) * 10.0
        ) / 10000
        
        economy = c.get("gdp", 0) / 1_000_000_000_000
        tech = sum(self.technologies.values()) / 10
        allies = len(self.alliances.get(country, [])) * 5
        
        return min(100, military * 0.5 + economy * 0.3 + tech * 0.1 + allies * 0.1)
    
    # ================================================================
    # НАПРЯЖЁННОСТЬ (ИИ)
    # ================================================================
    
    async def calculate_world_tension_ai(self) -> dict:
        """ИИ сам определяет мировую напряжённость"""
        
        active_wars = [w for w in self.wars.values() if w.get('status') == 'active']
        war_descriptions = []
        for war in active_wars[:5]:
            war_descriptions.append(f"- {war['attacker']} vs {war['defender']}")
        
        alliances_summary = []
        for c, allies_list in list(self.alliances.items())[:5]:
            if allies_list:
                alliances_summary.append(f"- {c}: союз с {', '.join(allies_list[:3])}")
        
        sanctions_summary = []
        for target, imposers in list(self.sanctions.items())[:5]:
            sanctions_summary.append(f"- Против {target}: санкции от {', '.join(imposers[:3])}")
        
        recent_news = self.news_history[-5:] if self.news_history else ["Новостей нет"]
        
        prompt = f"""Ты — аналитик мировой напряжённости. Год {self.year}.

Активные войны ({len(active_wars)}):
{chr(10).join(war_descriptions) if war_descriptions else 'Нет активных войн'}

Союзы:
{chr(10).join(alliances_summary) if alliances_summary else 'Нет союзов'}

Санкции:
{chr(10).join(sanctions_summary) if sanctions_summary else 'Нет санкций'}

Последние новости:
{chr(10).join(f'- {n[:100]}' for n in recent_news)}

Определи уровень мировой напряжённости от 0 до 100%.
Учти исторический контекст года (1939-1945 = высокая, 1914-1918 = высокая).

Формат ответа — ТОЛЬКО JSON:
{{"tension": 65.5, "status": "Предвоенное время", "description": "Кратко почему (1 предложение)", "can_justify_war": true, "can_intervene": true, "can_use_nukes": false, "trend": "rising"}}

Ответь ТОЛЬКО JSON, без пояснений."""

        try:
            import json, re
            response = await ai.ask_groq(prompt, system_prompt=ai.get_rp_system_prompt(), temperature=0.3, max_tokens=300)
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                data = json.loads(json_match.group())
                self.world_tension = data.get('tension', 50)
                return data
        except Exception as e:
            print(f"⚠️ Ошибка ИИ напряжённости: {e}")
        
        self.world_tension = min(100, len(active_wars) * 15)
        return {"tension": self.world_tension, "status": "Неопределённо", "description": "ИИ не смог оценить", "can_justify_war": self.world_tension >= 25, "can_intervene": self.world_tension >= 50, "can_use_nukes": self.world_tension >= 90, "trend": "stable"}
    
    def can_justify_war(self, country: str, target: str) -> tuple:
        """Проверяет может ли страна оправдать войну"""
        if target in self.alliances.get(country, []):
            return False, "🤝 Цель — ваш союзник"
        if target in self.marionettes and self.marionettes[target] == country:
            return False, "🎭 Цель — ваша марионетка"
        if target in self.annexed:
            return False, "🏴 Цель уже аннексирована"
        
        if self.world_tension >= 75:
            return True, "💀 Мировой хаос — война без оправданий"
        elif self.world_tension >= 50:
            return True, f"⚠️ Высокая напряжённость ({self.world_tension:.1f}%)"
        elif self.world_tension >= 25:
            return True, f"⚡ Достаточная напряжённость ({self.world_tension:.1f}%)"
        else:
            return False, f"🕊️ Слишком мирное время ({self.world_tension:.1f}%)"

# Глобальное состояние
world = WorldState()

# =====================================================================
# ТИПЫ МЕСТНОСТИ
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
# ОСНОВНОЙ ЦИКЛ
# =====================================================================

async def decision_loop(context=None):
    if bot_stopped:
        return
    
    country = get_country(ADMIN_ID) or "Швейцария"
    world.year = get_year(ADMIN_ID) or 2024
    world.month = get_rp_month()
    economy = get_economy(ADMIN_ID)
    
    if not economy:
        init_economy(ADMIN_ID)
        economy = get_economy(ADMIN_ID)
    
    if country not in world.country_profiles:
        world.country_profiles[country] = CountryProfile(country)
    
    profile = world.country_profiles[country]
    season_effects = get_season_effects()
    world.turn += 1
    
    # Обновляем напряжённость через ИИ
    if world.turn % 3 == 0 or world.turn == 1:
        try:
            tension_data = await world.calculate_world_tension_ai()
            print(f"🌍 Напряжённость: {tension_data.get('tension', 0):.1f}% — {tension_data.get('status', '?')}")
        except:
            pass
    
    print(f"\n{'='*50}")
    print(f"🔄 ХОД {world.turn} | {country} | {world.month} {world.year}")
    print(f"📊 Профиль: {profile.profile_type} | Сила: {world.get_power_rating(country):.1f}/100")
    print(f"🌍 Напряжённость: {world.world_tension:.1f}%")
    print(f"{'='*50}")
    
    my_power = world.get_power_rating(country)
    enemies = list(world.sanctions.get(country, []))
    allies = world.alliances.get(country, [])
    wars_active = [w for w in world.wars.values() if w.get('status') == 'active']
    
    # Экономика
    await economic_decisions(context, country, economy)
    
    # Технологии
    await tech_decisions(context, country, economy, profile)
    
    # Инфраструктура
    await infrastructure_decisions(context, country, economy, profile)
    
    # Военные решения (с проверкой напряжённости)
    await military_decisions(context, country, economy, profile, season_effects)
    
    # Отправка новостей
    if world.news_history:
        await send_accumulated_news(context, country)
    
    print(f"✅ Ход {world.turn} завершён\n")

# =====================================================================
# ЭКОНОМИКА
# =====================================================================

async def economic_decisions(context, country: str, economy: dict):
    budget = economy['budget']
    steel = economy['steel']
    
    if budget < 5_000_000 and steel > 1000:
        sell_amount = min(500, steel - 500)
        price = random.randint(600, 800)
        update_economy(ADMIN_ID, budget=budget + sell_amount * price, steel=steel - sell_amount)
        world.news_history.append(f"📉 *{country}* продала {sell_amount} тонн стали за ${sell_amount * price:,}")
    
    elif budget > 100_000_000:
        invest_amount = min(budget - 50_000_000, random.randint(10_000_000, 50_000_000))
        options = ["factories", "research_labs", "hospitals", "airbases", "bunkers"]
        choice = random.choice(options)
        world.infrastructure[choice] = world.infrastructure.get(choice, 1) + 1
        update_economy(ADMIN_ID, budget=budget - invest_amount)
        world.news_history.append(f"🏗️ *{country}* инвестировала ${invest_amount:,} в {choice}")

# =====================================================================
# ТЕХНОЛОГИИ
# =====================================================================

async def tech_decisions(context, country: str, economy: dict, profile: CountryProfile):
    budget = economy['budget']
    labs = world.infrastructure.get("research_labs", 1)
    tech_speed = profile.bonuses.get("tech_speed", 1.0)
    research_chance = min(0.4, 0.05 * labs * tech_speed)
    
    if random.random() < research_chance and budget > 10_000_000:
        priorities = {
            "mountain_fortress": ["air_defense", "infantry", "drones"],
            "naval_power": ["navy", "airforce", "drones"],
            "micro_state": ["cyber", "drones", "space"],
            "superpower": ["nuclear", "space", "airforce"],
            "military_power": ["tanks", "airforce", "artillery"],
            "economic_center": ["cyber", "drones", "space"],
            "regional_power": ["infantry", "tanks", "airforce"],
        }
        tech_list = priorities.get(profile.profile_type, ["infantry", "tanks", "airforce"])
        available = [t for t in tech_list if world.technologies.get(t, 1) < 10]
        
        if available:
            tech = random.choice(available[:3])
            cost = (world.technologies[tech] + 1) * 5_000_000
            
            if budget > cost:
                world.technologies[tech] += 1
                update_economy(ADMIN_ID, budget=budget - cost)
                world.news_history.append(f"🔬 *{country}* улучшила {tech} до уровня {world.technologies[tech]}!")

# =====================================================================
# ИНФРАСТРУКТУРА
# =====================================================================

async def infrastructure_decisions(context, country: str, economy: dict, profile: CountryProfile):
    budget = economy['budget']
    
    if budget > 20_000_000:
        priorities = {
            "mountain_fortress": ["bunkers", "mountain_forts", "hospitals"],
            "naval_power": ["ports", "airbases", "factories"],
            "micro_state": ["research_labs", "hospitals"],
            "superpower": ["factories", "airbases", "ports"],
            "military_power": ["factories", "airbases", "bunkers"],
            "economic_center": ["research_labs", "factories"],
            "regional_power": ["factories", "airbases", "hospitals"],
        }
        build_list = priorities.get(profile.profile_type, ["factories", "research_labs"])
        choice = random.choice(build_list[:3])
        cost = 15_000_000
        
        if budget > cost:
            world.infrastructure[choice] = world.infrastructure.get(choice, 1) + 1
            update_economy(ADMIN_ID, budget=budget - cost)
            world.news_history.append(f"🏗️ *{country}* построила {choice} (уровень {world.infrastructure[choice]})")

# =====================================================================
# ВОЕННЫЕ РЕШЕНИЯ (С НАПРЯЖЁННОСТЬЮ)
# =====================================================================

async def military_decisions(context, country: str, economy: dict, profile: CountryProfile, season: dict):
    my_power = world.get_power_rating(country)
    budget = economy['budget']
    
    # Проверяем активные войны
    for war_id, war in list(world.wars.items()):
        if war.get("status") != "active":
            continue
        
        if country in [war["attacker"], war["defender"]]:
            # Война уже идёт — просто продолжаем
            continue
    
    # Ищем возможности для войны (с учётом напряжённости)
    if profile.profile_type == "micro_state":
        return  # Микро-государства не нападают
    
    if season["attack_mod"] < 0.6 and profile.profile_type != "superpower":
        return  # Зимой не нападаем
    
    if budget < 50_000_000:
        return  # Нет денег на войну
    
    targets = []
    for target_name in world.countries:
        if target_name == country:
            continue
        if target_name in world.annexed or target_name in world.marionettes:
            continue
        if target_name in world.alliances.get(country, []):
            continue
        
        # Проверяем напряжённость
        can_justify, reason = world.can_justify_war(country, target_name)
        if not can_justify:
            continue
        
        target_power = world.get_power_rating(target_name)
        target_profile = world.country_profiles.get(target_name)
        target_defense = target_profile.bonuses.get("defense", 1.0) if target_profile else 1.0
        effective_power = target_power * target_defense / season["attack_mod"]
        
        if my_power > effective_power * 1.5:
            targets.append((target_name, target_power))
    
    if not targets:
        return
    
    targets.sort(key=lambda x: x[1])
    target_name, target_power = targets[0]
    
    if random.random() < 0.3:
        war_id = f"{country}_{target_name}_{world.turn}"
        
        can_justify, reason = world.can_justify_war(country, target_name)
        
        world.wars[war_id] = {
            "attacker": country,
            "defender": target_name,
            "reason": reason,
            "status": "active",
            "strategy": "blitzkrieg" if season["attack_mod"] > 1.0 else "balanced",
            "terrain": "plain",
            "weather": "snow" if "зима" in season["description"] else "clear",
            "attacker_losses": 0,
            "defender_losses": 0,
            "started_at": world.turn,
        }
        
        world.news_history.append(
            f"⚔️ *{country}* объявляет войну *{target_name}*!\n"
            f"📌 Причина: {reason}\n"
            f"🌍 Напряжённость: {world.world_tension:.1f}%\n"
            f"🌤️ Сезон: {season['description']}"
        )
        
        if context and saved_chats.get("war"):
            try:
                await context.bot.send_message(chat_id=saved_chats["war"], text=world.news_history[-1])
            except:
                pass

# =====================================================================
# ОТПРАВКА НОВОСТЕЙ
# =====================================================================

async def send_accumulated_news(context, country: str):
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
# ИНИЦИАЛИЗАЦИЯ
# =====================================================================

async def init_world():
    country = get_country(ADMIN_ID) or "Швейцария"
    world.year = get_year(ADMIN_ID) or 2024
    world.month = get_rp_month()
    
    print(f"🌍 Исследуем {country}...")
    info = await ai.research_country(country)
    
    profile = CountryProfile(country, info)
    world.country_profiles[country] = profile
    
    if profile.profile_type == "micro_state":
        army_size, tanks, gdp = 5000, 10, 50_000_000_000
    elif profile.profile_type == "superpower":
        army_size, tanks, gdp = 1_000_000, 5000, 20_000_000_000_000
    elif profile.profile_type == "mountain_fortress":
        army_size, tanks, gdp = 50000, 100, 500_000_000_000
    elif profile.profile_type == "military_power":
        army_size, tanks, gdp = 300_000, 2000, 2_000_000_000_000
    elif profile.profile_type == "naval_power":
        army_size, tanks, gdp = 150_000, 500, 2_500_000_000_000
    elif profile.profile_type == "economic_center":
        army_size, tanks, gdp = 50000, 200, 5_000_000_000_000
    else:
        army_size, tanks, gdp = 100_000, 1000, 1_000_000_000_000
    
    world.countries[country] = {
        "name": country, "army_size": army_size, "tanks": tanks,
        "aircraft": army_size // 200, "ships": 100 if profile.profile_type == "naval_power" else 20,
        "nukes": 5000 if profile.profile_type == "superpower" else 0,
        "gdp": gdp, "tech_levels": world.technologies.copy(),
        "info": info.get("summary", ""),
    }
    
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
                **data, "tanks": data["army_size"] // 100,
                "aircraft": data["army_size"] // 200, "ships": 20, "nukes": 0,
                "tech_levels": {k: random.randint(1, 5) for k in world.technologies},
            }
            world.country_profiles[name] = CountryProfile(name)
    
    print(f"✅ Мир инициализирован: {len(world.countries)} стран")
    return info
