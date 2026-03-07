# handlers/daily.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from datetime import datetime, timedelta
import random

from database import DatabaseManager
from config import DAILY_REWARDS, CARDS, RARITY_NAMES, EMOJI

router = Router()


def get_user_name(user) -> str:
    if user.username:
        return f"@{user.username}"
    return user.first_name or f"User {user.id}"


def _try_update_quest(db, user_id, quest_type, amount=1, extra_data=None):
    """Безопасное обновление квестов"""
    try:
        from handlers.quests import update_quest_progress
        update_quest_progress(db, user_id, quest_type, amount, extra_data)
    except Exception:
        pass


@router.message(Command("daily"))
async def daily_command(message: Message):
    if message.chat.type == "private":
        await message.reply("❌ Эта команда работает только в группах!")
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    db = DatabaseManager.get_db(chat_id)

    db.create_user(user_id, message.from_user.username, message.from_user.first_name)

    daily_info = db.get_daily_info(user_id)

    if not daily_info["can_claim"]:
        next_claim = daily_info.get("next_claim")
        if next_claim:
            now = datetime.now()
            if isinstance(next_claim, datetime):
                delta = next_claim - now
                hours = int(delta.total_seconds() // 3600)
                minutes = int((delta.total_seconds() % 3600) // 60)
                time_str = f"{hours}ч {minutes}мин" if hours > 0 else f"{minutes}мин"
            else:
                time_str = "скоро"
        else:
            time_str = "завтра"

        await message.reply(
            f"❌ <b>Вы уже забрали награду сегодня!</b>\n\n"
            f"⏰ Следующая через: <b>{time_str}</b>\n"
            f"🔥 Стрик: <b>{daily_info['streak']} дней</b>",
            parse_mode="HTML"
        )
        return

    result = db.claim_daily(user_id)
    if not result["success"]:
        await message.reply("❌ Не удалось забрать награду.")
        return

    streak = result["streak"]
    reward = DAILY_REWARDS.get(streak, DAILY_REWARDS[1])

    tickets = reward.get("tickets", 0)
    coins = reward.get("coins", 0)
    bonus_card_chance = reward.get("bonus_card_chance", 0)

    if tickets > 0:
        db.add_spin_tickets(user_id, tickets)
    if coins > 0:
        db.add_coins(user_id, coins)

    # Квесты
    _try_update_quest(db, user_id, "daily_claim", 1)
    if coins > 0:
        _try_update_quest(db, user_id, "earn_coins", coins)

    text_lines = [
        f"🎁 <b>ЕЖЕДНЕВНАЯ НАГРАДА!</b>",
        f"",
        f"🔥 День стрика: <b>{streak}/7</b>",
        f"",
        f"<b>Получено:</b>",
    ]

    if tickets > 0:
        text_lines.append(f"🎟️ Билеты: <b>+{tickets}</b>")
    if coins > 0:
        text_lines.append(f"🪙 Монеты: <b>+{coins}</b>")

    bonus_card = None
    if bonus_card_chance > 0 and random.random() < bonus_card_chance:
        rare_cards = [c for c in CARDS if c["rarity"] in ["rare", "epic"]]
        if rare_cards:
            bonus_card = random.choice(rare_cards)
            card_copy = bonus_card.copy()
            card_copy["obtained_at"] = datetime.now().isoformat()
            db.add_card(user_id, card_copy)
            rarity_name = RARITY_NAMES.get(bonus_card["rarity"], bonus_card["rarity"])
            text_lines.append(f"🃏 Бонусная карта: <b>{bonus_card['emoji']} {bonus_card['name']}</b> ({rarity_name})")
            _try_update_quest(db, user_id, "get_card_rarity", 1, {"rarity": bonus_card["rarity"]})

    text_lines.append("")
    text_lines.append("<b>📅 Прогресс недели:</b>")
    streak_visual = ""
    for day in range(1, 8):
        if day <= streak:
            streak_visual += "🟢"
        else:
            streak_visual += "⚪"
    text_lines.append(streak_visual)

    next_day = streak + 1 if streak < 7 else 1
    next_reward = DAILY_REWARDS.get(next_day, DAILY_REWARDS[1])
    text_lines.append("")
    text_lines.append(f"📦 Завтра: {next_reward['description']}")

    if streak == 7:
        text_lines.append("")
        text_lines.append("🎉 <b>Неделя завершена! Стрик сбросится.</b>")

    await message.reply("\n".join(text_lines), parse_mode="HTML")


@router.message(Command("pity"))
async def pity_command(message: Message):
    if message.chat.type == "private":
        await message.reply("❌ Только в группах!")
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    db = DatabaseManager.get_db(chat_id)
    db.create_user(user_id, message.from_user.username, message.from_user.first_name)

    pity = db.get_pity_counters(user_id)
    epic_threshold = 15
    legendary_threshold = 40
    mythic_threshold = 100

    epic_progress = min(pity["since_epic"], epic_threshold)
    legendary_progress = min(pity["since_legendary"], legendary_threshold)
    mythic_progress = min(pity["since_mythic"], mythic_threshold)

    def make_progress_bar(current: int, max_val: int, length: int = 10) -> str:
        filled = int((current / max_val) * length)
        empty = length - filled
        return "█" * filled + "░" * empty

    text = (
        f"🎯 <b>СЧЁТЧИКИ ГАРАНТИЙ</b>\n"
        f"<i>Для {get_user_name(message.from_user)}</i>\n\n"
        f"🟣 <b>Epic</b> (гарантия на {epic_threshold})\n"
        f"├ Прогресс: {epic_progress}/{epic_threshold}\n"
        f"└ {make_progress_bar(epic_progress, epic_threshold)}\n\n"
        f"🟡 <b>Legendary</b> (гарантия на {legendary_threshold})\n"
        f"├ Прогресс: {legendary_progress}/{legendary_threshold}\n"
        f"└ {make_progress_bar(legendary_progress, legendary_threshold)}\n\n"
        f"🔴 <b>Mythic</b> (гарантия на {mythic_threshold})\n"
        f"├ Прогресс: {mythic_progress}/{mythic_threshold}\n"
        f"└ {make_progress_bar(mythic_progress, mythic_threshold)}\n\n"
        f"📊 <b>Всего спинов:</b> {pity['total']}\n\n"
        f"<i>💡 Счётчик сбрасывается при получении карты соответствующей редкости или выше</i>"
    )

    await message.reply(text, parse_mode="HTML")


@router.message(Command("limited"))
async def limited_cards_command(message: Message):
    from config import LIMITED_CARDS

    if message.chat.type == "private":
        await message.reply("❌ Только в группах!")
        return

    chat_id = message.chat.id
    db = DatabaseManager.get_db(chat_id)
    now = datetime.now()

    available = []
    upcoming = []

    for card in LIMITED_CARDS:
        try:
            available_from = datetime.strptime(card["available_from"], "%Y-%m-%d")
            available_until = datetime.strptime(card["available_until"], "%Y-%m-%d")
            issued_count = db.get_limited_card_count(card["name"])
            max_copies = card.get("max_copies", 999)
            card_info = {
                **card, "issued": issued_count, "remaining": max_copies - issued_count,
                "from": available_from, "until": available_until,
            }
            if now < available_from:
                upcoming.append(card_info)
            elif now > available_until or issued_count >= max_copies:
                pass
            else:
                available.append(card_info)
        except Exception:
            continue

    text_lines = ["⏳ <b>ЛИМИТИРОВАННЫЕ КАРТЫ</b>\n"]
    if available:
        text_lines.append("🟢 <b>Доступны сейчас:</b>")
        for card in available:
            days_left = (card["until"] - now).days
            text_lines.append(
                f"\n{card['emoji']} <b>{card['name']}</b>\n"
                f"├ ⚔️ {card['attack']} / 🛡️ {card['defense']}\n"
                f"├ 📦 Осталось: {card['remaining']}/{card.get('max_copies', '?')}\n"
                f"└ ⏰ Ещё {days_left} дн."
            )
    else:
        text_lines.append("🔴 <i>Нет доступных лимитированных карт</i>")

    if upcoming:
        text_lines.append("\n\n🟡 <b>Скоро:</b>")
        for card in upcoming[:3]:
            days_until = (card["from"] - now).days
            text_lines.append(f"\n{card['emoji']} <b>{card['name']}</b>\n└ 📅 Через {days_until} дн.")

    text_lines.append("\n\n<i>💡 Лимитки выпадают во время спина в период доступности!</i>")
    await message.reply("\n".join(text_lines), parse_mode="HTML")