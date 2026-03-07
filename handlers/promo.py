# handlers/promo.py
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from config import EMOJI, CARDS, LIMITED_CARDS, FUSION_CARDS, BOT_CREATOR_IDS, BOT_CREATORS, RARITY_COLORS
from database import DatabaseManager

router = Router()

# ═══════════════════════════════════════════════
#  ОБЫЧНЫЕ ПРОМОКОДЫ (без лимита активаций)
# ═══════════════════════════════════════════════

PROMO_CODES = {
    # ── ТОПОВЫЙ ──
    "todayaidk": {
        "coins": 200,
        "tickets": 10,
        "mults": 5,
        "cards": ["Gojo Satoru"],
        "description": "🌟 МЕГА-КОД: 200 монет + 10 билетов + 5 Mults + Gojo Satoru"
    },

    # ── ХОРОШИЕ ──
    "rumstop": {
        "coins": 20,
        "tickets": 3,
        "description": "20 монет + 3 билета"
    },
    "tea": {
        "coins": 50,
        "tickets": 2,
        "cards": ["Gojo Satoru", "Gojo Tea"],
        "description": "50 монет + 2 билета + Gojo Satoru + Gojo Tea"
    },
    "mahoraga": {
        "coins": 20,
        "tickets": 1,
        "cards": ["Mahoraga"],
        "description": "20 монет + 1 билет + карта Mahoraga"
    },

    # ── СРЕДНИЕ ──
    "sf": {
        "coins": 30,
        "cards": ["ArbuzMegumi"],
        "description": "30 монет + ArbuzMegumi"
    },
    "dep": {
        "coins": 30,
        "cards": ["SaserHakari"],
        "description": "30 монет + SaserHakari"
    },
    "chainsaw": {
        "coins": 40,
        "tickets": 2,
        "cards": ["Denji"],
        "description": "40 монет + 2 билета + Denji"
    },
    "sukuna": {
        "coins": 35,
        "tickets": 1,
        "description": "35 монет + 1 билет"
    },
    "cursed": {
        "coins": 25,
        "tickets": 3,
        "description": "25 монет + 3 билета"
    },
    "jujutsu": {
        "tickets": 5,
        "description": "5 билетов"
    },
    "pochita": {
        "coins": 15,
        "tickets": 2,
        "description": "15 монет + 2 билета"
    },

    # ── МЕМНЫЕ / СЛАБЫЕ ──
    "apsnlox": {
        "coins": 1,
        "limited_cards": ["APSN Nobara"],
        "description": "1 монета + APSN Nobara (лимитка лол)"
    },
    "nub": {
        "coins": 1,
        "description": "1 монета. Ты нуб 🤡"
    },

    # ── СЕКРЕТНЫЕ ──
    "megafusion": {
        "mults": 3,
        "tickets": 2,
        "description": "3 Mults + 2 билета (секрет!)"
    },
    "infinity": {
        "coins": 100,
        "mults": 2,
        "description": "100 монет + 2 Mults"
    },
    "domainexpansion": {
        "coins": 75,
        "tickets": 5,
        "mults": 1,
        "description": "75 монет + 5 билетов + 1 Mults"
    },
}

# ═══════════════════════════════════════════════
#  АДМИНСКИЕ ПРОМОКОДЫ (с налогом и лимитом)
# ═══════════════════════════════════════════════

ADMIN_PROMO_CODES = {
    "admin": {
        "coins": 5500,
        "tickets": 0,
        "mults": 0,
        "cards": [],
        "tax_coins_percent": 50,      # Забирает 50% монет у не-создателей
        "tax_tickets_percent": 30,    # Забирает 30% билетов
        "tax_mults_percent": 25,      # Забирает 25% мультов
        "steal_card_rarity": ["epic", "legendary", "mythic", "special", "mega", "fused", "mega_fused"],  # Крадёт редкую карту
        "max_uses": None,             # Безлимит (None = без ограничений)
        "current_uses": 0,
        "description": "👑 АДМИН-КОД: 5500 монет (но с налогом для обычных игроков)"
    },
}

# Хранилище динамически созданных админских промокодов
DYNAMIC_ADMIN_CODES = {}


def is_group_chat(message: Message) -> bool:
    return message.chat.type in ["group", "supergroup"]


def get_db(message_or_callback):
    if isinstance(message_or_callback, Message):
        return DatabaseManager.get_db(message_or_callback.chat.id)
    elif isinstance(message_or_callback, CallbackQuery):
        return DatabaseManager.get_db(message_or_callback.message.chat.id)
    return None


def is_bot_creator(user_id: int, username: str = None) -> bool:
    """Проверка, является ли пользователь создателем бота"""
    if user_id in BOT_CREATOR_IDS:
        return True
    if username and username in BOT_CREATORS:
        return True
    return False


def find_card_by_name(card_name: str, card_list: list) -> dict | None:
    """Найти карту по имени в списке."""
    for c in card_list:
        if c["name"].lower() == card_name.lower():
            return c
    return None


def find_card_anywhere(card_name: str) -> dict | None:
    """Найти карту по имени во всех списках"""
    for card_list in [CARDS, LIMITED_CARDS, FUSION_CARDS]:
        card = find_card_by_name(card_name, card_list)
        if card:
            return card
    return None


def get_admin_code(code: str) -> dict | None:
    """Получить админский промокод"""
    if code in ADMIN_PROMO_CODES:
        return ADMIN_PROMO_CODES[code]
    if code in DYNAMIC_ADMIN_CODES:
        return DYNAMIC_ADMIN_CODES[code]
    return None


def use_admin_code_activation(code: str) -> bool:
    """Использовать одну активацию админского кода. Возвращает True если успешно."""
    admin_code = None
    code_storage = None
    
    if code in ADMIN_PROMO_CODES:
        admin_code = ADMIN_PROMO_CODES[code]
        code_storage = ADMIN_PROMO_CODES
    elif code in DYNAMIC_ADMIN_CODES:
        admin_code = DYNAMIC_ADMIN_CODES[code]
        code_storage = DYNAMIC_ADMIN_CODES
    
    if not admin_code:
        return False
    
    max_uses = admin_code.get("max_uses")
    
    # Если лимит None — безлимитный
    if max_uses is None:
        return True
    
    current = admin_code.get("current_uses", 0)
    
    if current >= max_uses:
        return False  # Лимит исчерпан
    
    # Увеличиваем счётчик
    code_storage[code]["current_uses"] = current + 1
    return True


def get_remaining_uses(code: str) -> str:
    """Получить оставшееся количество активаций"""
    admin_code = get_admin_code(code)
    if not admin_code:
        return "?"
    
    max_uses = admin_code.get("max_uses")
    if max_uses is None:
        return "∞"
    
    current = admin_code.get("current_uses", 0)
    remaining = max(0, max_uses - current)
    return str(remaining)


# ═══════════════════════════════════════════════
#  АДМИНСКИЕ КОМАНДЫ
# ═══════════════════════════════════════════════

@router.message(Command("createpromo", "addpromo"))
async def create_promo_command(message: Message):
    """
    Создание админского промокода с лимитом активаций
    
    Формат: /createpromo КОД ЛИМИТ [награды] [налог]
    
    Примеры:
    /createpromo vip 100 coins:1000 tax:30
    /createpromo gift 50 coins:500 tickets:10 tax:20
    /createpromo mega 10 coins:5000 mults:10 card:Sukuna tax:50
    """
    user_id = message.from_user.id
    username = message.from_user.username
    
    if not is_bot_creator(user_id, username):
        return await message.reply(f"{EMOJI['cross']} <b>Только для создателей бота!</b>", parse_mode="HTML")
    
    args = message.text.split()
    
    if len(args) < 3:
        help_text = (
            "🔧 <b>СОЗДАНИЕ АДМИН-ПРОМОКОДА</b>\n\n"
            "<b>Формат:</b>\n"
            "<code>/createpromo КОД ЛИМИТ [награды] [налог]</code>\n\n"
            "<b>Параметры:</b>\n"
            "• <code>КОД</code> — название промокода\n"
            "• <code>ЛИМИТ</code> — кол-во активаций (0 = безлимит)\n\n"
            "<b>Награды:</b>\n"
            "• <code>coins:1000</code> — монеты\n"
            "• <code>tickets:10</code> — билеты\n"
            "• <code>mults:5</code> — мульты\n"
            "• <code>shields:5</code> — щиты\n"
            "• <code>card:Название</code> — карта\n\n"
            "<b>Налог (для не-создателей):</b>\n"
            "• <code>tax:30</code> — забирает 30% ресурсов\n"
            "• <code>stealcard:yes</code> — крадёт редкую карту\n\n"
            "<b>Примеры:</b>\n"
            "<code>/createpromo vip 100 coins:1000 tax:30</code>\n"
            "<code>/createpromo mega 10 coins:5000 mults:10 tax:50 stealcard:yes</code>\n"
            "<code>/createpromo free 0 tickets:5</code> — безлимит, без налога"
        )
        return await message.reply(help_text, parse_mode="HTML")
    
    promo_code = args[1].lower()
    
    # Проверяем лимит
    try:
        max_uses = int(args[2])
        if max_uses == 0:
            max_uses = None  # Безлимит
    except ValueError:
        return await message.reply("❌ Лимит должен быть числом! (0 = безлимит)", parse_mode="HTML")
    
    # Проверяем, не существует ли уже
    if promo_code in PROMO_CODES or promo_code in ADMIN_PROMO_CODES or promo_code in DYNAMIC_ADMIN_CODES:
        return await message.reply(
            f"❌ <b>Промокод '{promo_code}' уже существует!</b>",
            parse_mode="HTML"
        )
    
    # Парсим параметры
    rewards = {
        "coins": 0,
        "tickets": 0,
        "mults": 0,
        "shields": 0,
        "cards": [],
        "tax_coins_percent": 0,
        "tax_tickets_percent": 0,
        "tax_mults_percent": 0,
        "steal_card_rarity": [],
        "max_uses": max_uses,
        "current_uses": 0,
    }
    
    for arg in args[3:]:
        if ":" in arg:
            key, value = arg.split(":", 1)
            key = key.lower()
            
            if key == "coins" and value.isdigit():
                rewards["coins"] = int(value)
            elif key == "tickets" and value.isdigit():
                rewards["tickets"] = int(value)
            elif key == "mults" and value.isdigit():
                rewards["mults"] = int(value)
            elif key == "shields" and value.isdigit():
                rewards["shields"] = int(value)
            elif key == "card":
                rewards["cards"].append(value)
            elif key == "tax" and value.isdigit():
                tax = min(90, max(0, int(value)))  # 0-90%
                rewards["tax_coins_percent"] = tax
                rewards["tax_tickets_percent"] = tax
                rewards["tax_mults_percent"] = tax
            elif key == "stealcard" and value.lower() in ["yes", "true", "1"]:
                rewards["steal_card_rarity"] = ["epic", "legendary", "mythic", "special", "mega", "fused", "mega_fused", "limited"]
    
    # Проверяем что есть хоть какая-то награда
    if rewards["coins"] == 0 and rewards["tickets"] == 0 and rewards["mults"] == 0 and not rewards["cards"]:
        return await message.reply(
            "❌ <b>Укажи хотя бы одну награду!</b>\n\n"
            "Пример: <code>/createpromo test 100 coins:500</code>",
            parse_mode="HTML"
        )
    
    # Формируем описание
    desc_parts = []
    if rewards["coins"]: desc_parts.append(f"{rewards['coins']} монет")
    if rewards["tickets"]: desc_parts.append(f"{rewards['tickets']} билетов")
    if rewards["mults"]: desc_parts.append(f"{rewards['mults']} Mults")
    if rewards["shields"]: desc_parts.append(f"{rewards['shields']} щитов")
    if rewards["cards"]: desc_parts.append(f"карты: {', '.join(rewards['cards'])}")
    
    rewards["description"] = " + ".join(desc_parts)
    
    # Сохраняем
    DYNAMIC_ADMIN_CODES[promo_code] = rewards
    
    # Формируем ответ
    tax = rewards["tax_coins_percent"]
    limit_text = f"{max_uses} активаций" if max_uses else "безлимит"
    tax_text = f"налог {tax}%" if tax > 0 else "без налога"
    steal_text = " + крадёт карту" if rewards["steal_card_rarity"] else ""
    
    text = (
        f"✅ <b>АДМИН-ПРОМОКОД СОЗДАН!</b>\n\n"
        f"Код: <code>{promo_code}</code>\n"
        f"Лимит: <b>{limit_text}</b>\n"
        f"Награды: {rewards['description']}\n"
        f"Налог: <b>{tax_text}{steal_text}</b>\n\n"
        f"💡 Активация: <code>/promo {promo_code}</code>"
    )
    
    await message.reply(text, parse_mode="HTML")


@router.message(Command("deletepromo", "delpromo", "removepromo"))
async def delete_promo_command(message: Message):
    """Удаление динамического промокода"""
    user_id = message.from_user.id
    username = message.from_user.username
    
    if not is_bot_creator(user_id, username):
        return await message.reply(f"{EMOJI['cross']} <b>Только для создателей бота!</b>", parse_mode="HTML")
    
    args = message.text.split()
    
    if len(args) < 2:
        return await message.reply(
            "🗑️ <b>Удаление промокода</b>\n\n"
            "Формат: <code>/deletepromo КОД</code>",
            parse_mode="HTML"
        )
    
    promo_code = args[1].lower()
    
    if promo_code in DYNAMIC_ADMIN_CODES:
        del DYNAMIC_ADMIN_CODES[promo_code]
        await message.reply(f"✅ Админ-промокод <code>{promo_code}</code> удалён!", parse_mode="HTML")
    elif promo_code in ADMIN_PROMO_CODES:
        await message.reply(
            f"❌ <code>{promo_code}</code> — встроенный админ-код, его нельзя удалить!",
            parse_mode="HTML"
        )
    elif promo_code in PROMO_CODES:
        await message.reply(
            f"❌ <code>{promo_code}</code> — обычный промокод, его нельзя удалить!",
            parse_mode="HTML"
        )
    else:
        await message.reply(f"❌ Промокод <code>{promo_code}</code> не найден!", parse_mode="HTML")


@router.message(Command("listpromos", "promolist", "promocodes"))
async def list_promos_command(message: Message):
    """Список всех промокодов (для админов)"""
    user_id = message.from_user.id
    username = message.from_user.username
    
    if not is_bot_creator(user_id, username):
        return await message.reply(f"{EMOJI['cross']} <b>Только для создателей бота!</b>", parse_mode="HTML")
    
    text = "📋 <b>ВСЕ ПРОМОКОДЫ</b>\n\n"
    
    # Обычные промокоды
    text += "<b>🎫 Обычные:</b>\n"
    for code in list(PROMO_CODES.keys())[:10]:
        text += f"• <code>{code}</code>\n"
    if len(PROMO_CODES) > 10:
        text += f"<i>...ещё {len(PROMO_CODES) - 10}</i>\n"
    
    # Встроенные админские
    text += "\n<b>👑 Админские (встроенные):</b>\n"
    for code, data in ADMIN_PROMO_CODES.items():
        remaining = get_remaining_uses(code)
        tax = data.get("tax_coins_percent", 0)
        text += f"• <code>{code}</code> — {remaining} акт., налог {tax}%\n"
    
    # Созданные админские
    if DYNAMIC_ADMIN_CODES:
        text += "\n<b>➕ Созданные:</b>\n"
        for code, data in DYNAMIC_ADMIN_CODES.items():
            remaining = get_remaining_uses(code)
            tax = data.get("tax_coins_percent", 0)
            coins = data.get("coins", 0)
            text += f"• <code>{code}</code> — {remaining} акт., {coins}🪙, налог {tax}%\n"
    
    total = len(PROMO_CODES) + len(ADMIN_PROMO_CODES) + len(DYNAMIC_ADMIN_CODES)
    text += f"\n📊 Всего: {total}"
    
    await message.reply(text, parse_mode="HTML")


@router.message(Command("resetpromo"))
async def reset_promo_command(message: Message):
    """Сброс счётчика активаций админского промокода"""
    user_id = message.from_user.id
    username = message.from_user.username
    
    if not is_bot_creator(user_id, username):
        return await message.reply(f"{EMOJI['cross']} <b>Только для создателей бота!</b>", parse_mode="HTML")
    
    args = message.text.split()
    
    if len(args) < 2:
        return await message.reply(
            "🔄 <b>Сброс активаций</b>\n\n"
            "Формат: <code>/resetpromo КОД</code>",
            parse_mode="HTML"
        )
    
    promo_code = args[1].lower()
    
    if promo_code in ADMIN_PROMO_CODES:
        ADMIN_PROMO_CODES[promo_code]["current_uses"] = 0
        await message.reply(f"✅ Счётчик <code>{promo_code}</code> сброшен!", parse_mode="HTML")
    elif promo_code in DYNAMIC_ADMIN_CODES:
        DYNAMIC_ADMIN_CODES[promo_code]["current_uses"] = 0
        await message.reply(f"✅ Счётчик <code>{promo_code}</code> сброшен!", parse_mode="HTML")
    else:
        await message.reply(f"❌ Админ-промокод <code>{promo_code}</code> не найден!", parse_mode="HTML")


# ═══════════════════════════════════════════════
#  ОСНОВНАЯ КОМАНДА /promo
# ═══════════════════════════════════════════════

@router.message(Command("promo"))
async def promo_command(message: Message):
    """Обработка команды /promo [код]"""
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    args = message.text.split()
    if len(args) < 2:
        text = (
            "🎫 <b>ПРОМОКОДЫ</b>\n\n"
            "Используй: <code>/promo КОД</code>\n\n"
            "💡 Коды можно найти в каналах, от админов и в секретных местах!\n\n"
            "<i>Каждый код можно использовать только 1 раз!</i>"
        )
        return await message.reply(text, parse_mode="HTML")

    promo_input = args[1]
    promo_key = promo_input.lower()

    user_id = message.from_user.id
    username = message.from_user.username
    db = get_db(message)

    # Создаём пользователя если нет
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, message.from_user.username, message.from_user.first_name)
        user = db.get_user(user_id)

    # Проверяем использование (работает для всех типов кодов)
    if db.user_used_promo_code(user_id, promo_key):
        return await message.reply(
            "❌ <b>Этот промокод уже использован!</b>\n\n"
            "Каждый код можно использовать только 1 раз.",
            parse_mode="HTML"
        )

    # ══════════════════════════════════════════
    #  ПРОВЕРЯЕМ АДМИНСКИЙ ПРОМОКОД
    # ══════════════════════════════════════════
    
    admin_code = get_admin_code(promo_key)
    
    if admin_code:
        # Проверяем лимит активаций
        max_uses = admin_code.get("max_uses")
        current_uses = admin_code.get("current_uses", 0)
        
        if max_uses is not None and current_uses >= max_uses:
            return await message.reply(
                f"❌ <b>Промокод исчерпан!</b>\n\n"
                f"Код <code>{promo_input}</code> уже активирован максимальное количество раз ({max_uses}).",
                parse_mode="HTML"
            )
        
        # Используем активацию
        if not use_admin_code_activation(promo_key):
            return await message.reply("❌ <b>Ошибка активации!</b>", parse_mode="HTML")
        
        # Проверяем, является ли создателем бота
        is_creator = is_bot_creator(user_id, username)
        
        reward_text = ""
        tax_text = ""
        
        # ══════════════════════════════════════════
        #  ВЫДАЁМ НАГРАДЫ
        # ══════════════════════════════════════════
        
        # Монеты
        if admin_code.get("coins", 0) > 0:
            coins = admin_code["coins"]
            db.add_coins(user_id, coins)
            reward_text += f"💰 <b>+{coins}</b> 🪙\n"
        
        # Билеты
        if admin_code.get("tickets", 0) > 0:
            tickets = admin_code["tickets"]
            db.add_spin_tickets(user_id, tickets)
            reward_text += f"🎫 <b>+{tickets}</b> билетов\n"
        
        # Mults
        if admin_code.get("mults", 0) > 0:
            mults = admin_code["mults"]
            db.add_mults(user_id, mults)
            reward_text += f"💎 <b>+{mults}</b> Mults\n"
        
        # Щиты
        if admin_code.get("shields", 0) > 0:
            shields = admin_code["shields"]
            db.add_shields(user_id, shields)
            reward_text += f"🛡️ <b>+{shields}</b> щитов\n"
        
        # Карты
        if admin_code.get("cards"):
            for card_name in admin_code["cards"]:
                card = find_card_anywhere(card_name)
                if card:
                    card_to_add = {
                        "name": card["name"],
                        "rarity": card["rarity"],
                        "attack": card["attack"],
                        "defense": card["defense"],
                        "emoji": card["emoji"]
                    }
                    db.add_card(user_id, card_to_add)
                    rc = RARITY_COLORS.get(card["rarity"], "⚪")
                    reward_text += f"🃏 <b>{rc} {card['emoji']} {card['name']}</b>\n"
        
        # ══════════════════════════════════════════
        #  ПРИМЕНЯЕМ НАЛОГ (если не создатель)
        # ══════════════════════════════════════════
        
        if not is_creator:
            stolen_coins = 0
            stolen_tickets = 0
            stolen_mults = 0
            stolen_card = None
            
            # Налог на монеты
            tax_coins = admin_code.get("tax_coins_percent", 0)
            if tax_coins > 0:
                current_coins = db.get_coins(user_id)
                steal_amount = int(current_coins * tax_coins / 100)
                if steal_amount > 0:
                    db.remove_coins(user_id, steal_amount)
                    stolen_coins = steal_amount
            
            # Налог на билеты
            tax_tickets = admin_code.get("tax_tickets_percent", 0)
            if tax_tickets > 0:
                current_tickets = db.get_spin_tickets(user_id)
                steal_amount = int(current_tickets * tax_tickets / 100)
                if steal_amount > 0:
                    for _ in range(steal_amount):
                        db.use_spin_ticket(user_id)
                    stolen_tickets = steal_amount
            
            # Налог на мульты
            tax_mults = admin_code.get("tax_mults_percent", 0)
            if tax_mults > 0:
                current_mults = user.get("mults", 0)
                steal_amount = int(current_mults * tax_mults / 100)
                if steal_amount > 0:
                    db.remove_mults(user_id, steal_amount)
                    stolen_mults = steal_amount
            
            # Кража карты
            steal_rarities = admin_code.get("steal_card_rarity", [])
            if steal_rarities:
                # Обновляем данные пользователя
                user = db.get_user(user_id)
                user_cards = user.get("cards", [])
                rare_cards = [c for c in user_cards if c.get("rarity") in steal_rarities]
                if rare_cards:
                    stolen_card = random.choice(rare_cards)
                    db.remove_card_from_user(user_id, stolen_card["name"])
            
            # Формируем текст налога
            if stolen_coins > 0:
                tax_text += f"💸 <b>-{stolen_coins}</b> монет (налог)\n"
            if stolen_tickets > 0:
                tax_text += f"🎫 <b>-{stolen_tickets}</b> билетов (налог)\n"
            if stolen_mults > 0:
                tax_text += f"💎 <b>-{stolen_mults}</b> Mults (налог)\n"
            if stolen_card:
                rc = RARITY_COLORS.get(stolen_card.get("rarity", ""), "⚪")
                tax_text += f"🃏 <b>{rc} {stolen_card.get('emoji', '')} {stolen_card['name']}</b> ИЗЪЯТА!\n"
        
        # Отмечаем как использованный
        db.use_promo_code(user_id, promo_key)
        
        # Оставшиеся активации
        remaining = get_remaining_uses(promo_key)
        
        # Формируем ответ
        if is_creator:
            header = "👑👑👑 <b>АДМИН-КОД АКТИВИРОВАН!</b> 👑👑👑"
            footer = "\n\n😎 <i>Ты создатель — налог не применяется!</i>"
        else:
            if tax_text:
                header = "⚠️ <b>ПРОМОКОД АКТИВИРОВАН!</b> ⚠️"
                footer = "\n\n💀 <i>С тебя взят налог за использование админского кода!</i>"
            else:
                header = "🎉 <b>ПРОМОКОД АКТИВИРОВАН!</b>"
                footer = ""
        
        text = f"{header}\n\n"
        text += f"Код: <code>{promo_input}</code>\n\n"
        
        if reward_text:
            text += "<b>Получено:</b>\n"
            text += reward_text
        
        if tax_text:
            text += "\n<b>Налог:</b>\n"
            text += tax_text
        
        text += footer
        text += f"\n\n📊 Осталось активаций: <b>{remaining}</b>"
        
        await message.reply(text, parse_mode="HTML")
        return

    # ══════════════════════════════════════════
    #  ОБЫЧНЫЙ ПРОМОКОД
    # ══════════════════════════════════════════
    
    if promo_key not in PROMO_CODES:
        return await message.reply("❌ <b>Неверный промокод!</b>", parse_mode="HTML")

    rewards = PROMO_CODES[promo_key]
    reward_text = ""

    # Монеты
    if "coins" in rewards:
        coins = rewards["coins"]
        db.add_coins(user_id, coins)
        reward_text += f"💰 <b>+{coins}</b> 🪙\n"

    # Билеты
    if "tickets" in rewards:
        tickets = rewards["tickets"]
        db.add_spin_tickets(user_id, tickets)
        reward_text += f"🎫 <b>+{tickets}</b> билетов\n"

    # Mults
    if "mults" in rewards:
        mults_amount = rewards["mults"]
        db.add_mults(user_id, mults_amount)
        reward_text += f"💎 <b>+{mults_amount}</b> Mults\n"

    # Обычные карты
    if "cards" in rewards:
        for card_name in rewards["cards"]:
            card = find_card_anywhere(card_name)
            if card:
                card_to_add = {
                    "name": card["name"],
                    "rarity": card["rarity"],
                    "attack": card["attack"],
                    "defense": card["defense"],
                    "emoji": card["emoji"]
                }
                db.add_card(user_id, card_to_add)
                rc = RARITY_COLORS.get(card["rarity"], "⚪")
                reward_text += f"🃏 <b>{rc} {card['emoji']} {card['name']}</b>\n"
            else:
                reward_text += f"⚠️ Карта '{card_name}' не найдена\n"

    # Лимитированные карты
    if "limited_cards" in rewards:
        for card_name in rewards["limited_cards"]:
            card = find_card_by_name(card_name, LIMITED_CARDS)
            if card:
                card_to_add = {
                    "name": card["name"],
                    "rarity": card["rarity"],
                    "attack": card["attack"],
                    "defense": card["defense"],
                    "emoji": card["emoji"]
                }
                db.add_card(user_id, card_to_add)
                reward_text += f"⏳ <b>{card['emoji']} {card['name']}</b> (LIMITED!)\n"
            else:
                reward_text += f"⚠️ Лимитка '{card_name}' не найдена\n"

    # Отмечаем как использованный
    db.use_promo_code(user_id, promo_key)

    # Специальные заголовки
    if promo_key == "todayaidk":
        header = "🌟🌟🌟 <b>Тудей бог!</b> 🌟🌟🌟"
    elif promo_key == "apsnlox":
        header = "🤡 <b>ПРОМОКОД АКТИВИРОВАН!</b> 🤡"
    elif promo_key == "nub":
        header = "💀 <b>Серьёзно? Ну ладно...</b> 💀"
    elif "mults" in rewards and rewards.get("mults", 0) >= 5:
        header = "💎💎💎 <b>МЕГА-КОД!</b> 💎💎💎"
    elif "mults" in rewards:
        header = "💎 <b>ПРОМОКОД АКТИВИРОВАН!</b> 💎"
    else:
        header = "🎉 <b>ПРОМОКОД АКТИВИРОВАН!</b>"

    text = f"{header}\n\n"
    text += f"Код: <code>{promo_input}</code>\n\n"
    text += "<b>Награды:</b>\n"
    text += reward_text
    text += "\n✅ <i>Код сохранён в истории</i>"

    await message.reply(text, parse_mode="HTML")


@router.message(Command("mypromos", "usedpromos"))
async def my_promos_command(message: Message):
    """Показать использованные промокоды"""
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")
    
    db = get_db(message)
    user_id = message.from_user.id
    
    user = db.get_user(user_id)
    if not user:
        return await message.reply("❌ Ты ещё не зарегистрирован! Используй /start")
    
    used_promos = user.get("used_promo_codes", [])
    
    if not used_promos:
        text = (
            "📋 <b>Использованные промокоды</b>\n\n"
            "<i>Ты ещё не использовал ни одного промокода!</i>\n\n"
            "💡 Активируй код: <code>/promo КОД</code>"
        )
    else:
        text = f"📋 <b>Использованные промокоды ({len(used_promos)})</b>\n\n"
        for code in used_promos[-20:]:
            text += f"• <code>{code}</code>\n"
        if len(used_promos) > 20:
            text += f"\n<i>...и ещё {len(used_promos) - 20}</i>"
    
    await message.reply(text, parse_mode="HTML")