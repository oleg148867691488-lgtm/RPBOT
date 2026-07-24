"""
DIPLOMACY.PY — СИСТЕМА ДИПЛОМАТИИ
===================================
Исправленная версия: убран прямой вызов app.bot.
"""

import random
import asyncio
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID, saved_chats
from history import get_country, get_year, save_world_event

# =====================================================================
# ХРАНИЛИЩА
# =====================================================================

un_sessions = {}    # Активные сессии ООН
alliances = {}      # Союзы между странами
sanctions = {}      # Активные санкции

# =====================================================================
# ПРЕДЛОЖИТЬ РЕЗОЛЮЦИЮ В ООН
# =====================================================================

async def un_propose_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предложить резолюцию в ООН"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Используйте: /un_propose [текст резолюции]"
        )
        return
    
    text = " ".join(args)
    country = get_country(user_id) or "неизвестная страна"
    year = get_year(user_id) or 2024
    
    session_id = f"un_{user_id}_{year}_{len(un_sessions)}"
    un_sessions[session_id] = {
        "proposer": country,
        "text": text,
        "year": year,
        "votes_for": 0,
        "votes_against": 0,
        "status": "voting",
        "voters": []
    }
    
    # Сохраняем в историю
    save_world_event(
        "un_proposal",
        f"{country} предложил резолюцию: {text[:100]}",
        country
    )
    
    await update.message.reply_text(
        f"🏛️ *{country} предлагает резолюцию в ООН:*\n\n"
        f"📄 {text}\n\n"
        f"📅 Год: {year}\n"
        f"🗳️ Голосование началось! (5 минут)\n"
        f"📝 Используйте `/vote за` или `/vote против`",
        parse_mode="Markdown"
    )
    
    # Отправляем в чат ООН
    un_chat = saved_chats.get("un")
    if un_chat and context.bot:
        await context.bot.send_message(
            chat_id=un_chat,
            text=(
                f"🏛️ *{country} предлагает резолюцию:*\n\n"
                f"📄 {text}\n\n"
                f"🗳️ Голосуйте: `/vote за` или `/vote против`"
            ),
            parse_mode="Markdown"
        )
    
    # Запускаем таймер голосования
    asyncio.create_task(un_voting_timer(session_id, context))


# =====================================================================
# ГОЛОСОВАНИЕ В ООН
# =====================================================================

async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проголосовать в ООН"""
    user_id = update.message.from_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "❌ Используйте: /vote [за/против]"
        )
        return
    
    vote = args[0].lower()
    if vote not in ["за", "против"]:
        await update.message.reply_text("❌ Используйте 'за' или 'против'.")
        return
    
    # Ищем активную сессию
    for session_id, session in un_sessions.items():
        if session["status"] == "voting":
            if user_id in session["voters"]:
                await update.message.reply_text("❌ Вы уже проголосовали.")
                return
            
            if vote == "за":
                session["votes_for"] += 1
            else:
                session["votes_against"] += 1
            
            session["voters"].append(user_id)
            
            country = get_country(user_id) or "игрок"
            
            await update.message.reply_text(
                f"✅ Голос принят: *{vote}*\n"
                f"📊 ЗА: {session['votes_for']} | ПРОТИВ: {session['votes_against']}",
                parse_mode="Markdown"
            )
            return
    
    await update.message.reply_text("❌ Нет активных голосований в ООН.")


# =====================================================================
# ТАЙМЕР ГОЛОСОВАНИЯ
# =====================================================================

async def un_voting_timer(session_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Завершение голосования через 5 минут"""
    
    await asyncio.sleep(60 * 5)  # 5 минут
    
    if session_id not in un_sessions:
        return
    
    session = un_sessions[session_id]
    session["status"] = "ended"
    
    # Определяем результат
    if session["votes_for"] > session["votes_against"]:
        result = "✅ Резолюция ПРИНЯТА!"
        result_type = "accepted"
    elif session["votes_for"] == session["votes_against"]:
        result = "⚖️ РАВЕНСТВО ГОЛОСОВ. Резолюция ОТКЛОНЕНА."
        result_type = "tie"
    else:
        result = "❌ Резолюция ОТКЛОНЕНА!"
        result_type = "rejected"
    
    # Сохраняем в историю
    save_world_event(
        "un_vote_ended",
        f"Голосование по резолюции {session['proposer']}: {result_type}",
        session['proposer']
    )
    
    message = (
        f"🏛️ *ИТОГИ ГОЛОСОВАНИЯ ООН*\n\n"
        f"📄 {session['text']}\n"
        f"👤 Предложил: {session['proposer']}\n\n"
        f"📊 Результаты:\n"
        f"• ЗА: {session['votes_for']}\n"
        f"• ПРОТИВ: {session['votes_against']}\n\n"
        f"📌 {result}"
    )
    
    # Отправляем в чат ООН
    un_chat = saved_chats.get("un")
    if un_chat and context and context.bot:
        await context.bot.send_message(
            chat_id=un_chat,
            text=message,
            parse_mode="Markdown"
        )
    
    # Удаляем сессию через минуту
    await asyncio.sleep(60)
    if session_id in un_sessions:
        del un_sessions[session_id]


# =====================================================================
# ПРЕДЛОЖИТЬ СОЮЗ
# =====================================================================

async def ally_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предложить союз другой стране"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Используйте: /ally [страна] [тип союза]\n"
            "Типы: торговый, военный, оборонительный, полный"
        )
        return
    
    target = args[0]
    alliance_type = args[1] if len(args) > 1 else "торговый"
    
    valid_types = ["торговый", "военный", "оборонительный", "полный"]
    if alliance_type not in valid_types:
        await update.message.reply_text(
            f"❌ Неизвестный тип союза. Доступны: {', '.join(valid_types)}"
        )
        return
    
    country = get_country(user_id) or "неизвестная страна"
    
    alliance_id = f"{country}_{target}_{len(alliances)}"
    alliances[alliance_id] = {
        "country1": country,
        "country2": target,
        "type": alliance_type,
        "active": False,
        "proposed_by": country,
        "year": get_year(user_id) or 2024
    }
    
    # Сохраняем в историю
    save_world_event(
        "alliance_proposed",
        f"{country} предложил {alliance_type} союз стране {target}",
        f"{country},{target}"
    )
    
    await update.message.reply_text(
        f"🤝 *{country} предлагает {alliance_type} союз с {target}!*\n\n"
        f"📝 {target} может принять союз: `/accept_ally`",
        parse_mode="Markdown"
    )
    
    # Отправляем в чат ООН
    un_chat = saved_chats.get("un")
    if un_chat and context.bot:
        await context.bot.send_message(
            chat_id=un_chat,
            text=(
                f"🤝 *Дипломатическое предложение*\n\n"
                f"*{country}* предлагает *{alliance_type}* союз стране *{target}*."
            ),
            parse_mode="Markdown"
        )


# =====================================================================
# ПРИНЯТЬ СОЮЗ
# =====================================================================

async def accept_ally_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принять предложение о союзе"""
    user_id = update.message.from_user.id
    country = get_country(user_id) or "неизвестная страна"
    
    for alliance_id, alliance in alliances.items():
        if alliance["country2"] == country and not alliance["active"]:
            alliance["active"] = True
            
            # Сохраняем в историю
            save_world_event(
                "alliance_formed",
                f"{alliance['country1']} и {country} заключили {alliance['type']} союз",
                f"{alliance['country1']},{country}"
            )
            
            message = (
                f"✅ *СОЮЗ ЗАКЛЮЧЁН!*\n\n"
                f"🤝 *{country}* принял предложение *{alliance['country1']}*\n"
                f"📌 Тип: {alliance['type']}\n"
                f"📅 Год: {alliance['year']}\n\n"
                f"Теперь вы союзники!"
            )
            
            await update.message.reply_text(message, parse_mode="Markdown")
            
            # Отправляем в чат ООН
            un_chat = saved_chats.get("un")
            if un_chat and context.bot:
                await context.bot.send_message(
                    chat_id=un_chat,
                    text=message,
                    parse_mode="Markdown"
                )
            return
    
    await update.message.reply_text("❌ Нет активных предложений о союзе для вашей страны.")


# =====================================================================
# ВВЕСТИ САНКЦИИ
# =====================================================================

async def sanctions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввести санкции против страны"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Используйте: /sanctions [страна] [причина]"
        )
        return
    
    target = args[0]
    reason = " ".join(args[1:])
    country = get_country(user_id) or "неизвестная страна"
    
    sanctions[target] = {
        "imposed_by": country,
        "reason": reason,
        "active": True,
        "year": get_year(user_id) or 2024
    }
    
    # Сохраняем в историю
    save_world_event(
        "sanctions_imposed",
        f"{country} ввёл санкции против {target}. Причина: {reason}",
        f"{country},{target}"
    )
    
    await update.message.reply_text(
        f"🚫 *САНКЦИИ ВВЕДЕНЫ!*\n\n"
        f"• Против: *{target}*\n"
        f"• Кем: *{country}*\n"
        f"• Причина: {reason}\n"
        f"• Торговля заблокирована",
        parse_mode="Markdown"
    )
    
    # Отправляем в чат ООН
    un_chat = saved_chats.get("un")
    if un_chat and context.bot:
        await context.bot.send_message(
            chat_id=un_chat,
            text=(
                f"🚫 *{country} ввёл санкции против {target}*\n"
                f"📌 Причина: {reason}"
            ),
            parse_mode="Markdown"
        )


# =====================================================================
# СНЯТЬ САНКЦИИ
# =====================================================================

async def remove_sanctions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Снять санкции"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещён.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Используйте: /remove_sanctions [страна]"
        )
        return
    
    target = args[0]
    
    if target in sanctions:
        del sanctions[target]
        
        save_world_event(
            "sanctions_removed",
            f"Санкции против {target} сняты",
            target
        )
        
        await update.message.reply_text(f"✅ Санкции против *{target}* сняты.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Санкции против *{target}* не найдены.", parse_mode="Markdown")


# =====================================================================
# СТАТУС ДИПЛОМАТИИ
# =====================================================================

async def diplomacy_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать дипломатический статус"""
    user_id = update.message.from_user.id
    country = get_country(user_id) or "неизвестная страна"
    
    text = f"🌍 *Дипломатическая обстановка для {country}:*\n\n"
    
    # Союзы
    if alliances:
        text += "🤝 *Активные союзы:*\n"
        has_allies = False
        for alliance in alliances.values():
            if alliance["active"] and (alliance["country1"] == country or alliance["country2"] == country):
                partner = alliance["country2"] if alliance["country1"] == country else alliance["country1"]
                text += f"• {partner} — {alliance['type']} союз\n"
                has_allies = True
        if not has_allies:
            text += "• Нет активных союзов\n"
    else:
        text += "🤝 *Союзы:* нет\n"
    
    # Санкции
    text += "\n🚫 *Санкции:*\n"
    if sanctions:
        has_sanctions = False
        for target, info in sanctions.items():
            if info["active"]:
                if info["imposed_by"] == country:
                    text += f"• Против {target}: {info['reason'][:50]}\n"
                    has_sanctions = True
                elif target == country:
                    text += f"• Против вас от {info['imposed_by']}: {info['reason'][:50]}\n"
                    has_sanctions = True
        if not has_sanctions:
            text += "• Санкций нет\n"
    else:
        text += "• Санкций нет\n"
    
    # ООН
    text += "\n🏛️ *Активные сессии ООН:*\n"
    if un_sessions:
        has_sessions = False
        for session in un_sessions.values():
            if session["status"] == "voting":
                text += f"• {session['proposer']}: {session['text'][:50]}...\n"
                text += f"  ЗА: {session['votes_for']} | ПРОТИВ: {session['votes_against']}\n"
                has_sessions = True
        if not has_sessions:
            text += "• Нет активных голосований\n"
    else:
        text += "• Нет активных сессий\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")


# =====================================================================
# АНАЛИЗ ДИПЛОМАТИИ (ДЛЯ HANDLERS)
# =====================================================================

async def analyze_diplomacy(text: str) -> str:
    """
    Анализ дипломатического сообщения.
    Используется в handlers.py.
    """
    from ai_manager import ai
    
    country = get_country(ADMIN_ID) or "Швейцария"
    year = get_year(ADMIN_ID) or 2024
    
    prompt = (
        f"Ты — министерство иностранных дел страны {country}. Год {year}.\n"
        f"Проанализируй это дипломатическое сообщение.\n"
        f"Оцени намерения, скрытые мотивы, возможные последствия.\n"
        f"Предложи дипломатический ответ.\n"
        f"Будь хитрым и стратегическим.\n"
        f"Ответь 2-4 предложениями на русском.\n\n"
        f"Сообщение: {text}"
    )
    
    return await ai.ask_groq(
        prompt,
        system_prompt=ai.get_rp_system_prompt(),
        temperature=0.6,
        max_tokens=300
    )


# =====================================================================
# ЭКСПОРТ
# =====================================================================

__all__ = [
    'un_propose_command',
    'vote_command',
    'ally_command',
    'accept_ally_command',
    'sanctions_command',
    'remove_sanctions_command',
    'diplomacy_status_command',
    'analyze_diplomacy',
    'un_sessions',
    'alliances',
    'sanctions',
]
