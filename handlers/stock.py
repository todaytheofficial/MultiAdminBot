# handlers/stock.py
"""
STOCK — Системный магазин карт
- Обновляется каждые 5 минут
- Рандомные карты по разным ценам
- Редкие карты за Mults, обычные за монеты
- Ограниченное количество каждой карты
"""

import random
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from config import EMOJI, CARDS, RARITY_COLORS, RARITY_NAMES, FUSION_CARDS
from database import DatabaseManager

router = Router()
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#                        НАСТРОЙКИ СТОКА
# ═══════════════════════════════════════════════════════════════

# Время обновления стока (в секундах)
STOCK_REFRESH_TIME = 300  # 5 минут

# Сколько карт в стоке
STOCK_SIZE = 8

# Шансы редкостей в стоке (должны = 100)
STOCK_RARITY_CHANCES = {
    "common": 35,      # 35%
    "rare": 30,        # 30%
    "epic": 18,        # 18%
    "legendary": 10,   # 10%
    "mythic": 4,       # 4%
    "special": 2,      # 2%
    "mega": 1,         # 1%
}

# Количество копий каждой карты в стоке
STOCK_COPIES = {
    "common": 5,
    "rare": 4,
    "epic": 3,
    "legendary": 2,
    "mythic": 1,
    "special": 1,
    "mega": 1,
    "fused": 1,
    "mega_fused": 1,
}

# Цены (базовый множитель к силе карты)
# За монеты
STOCK_COIN_PRICE = {
    "common": 3,       # сила * 3
    "rare": 5,         # сила * 5
    "epic": 8,         # сила * 8
}

# За Mults (редкие карты)
STOCK_MULTS_PRICE = {
    "legendary": 2,    # сила / 50 + 2
    "mythic": 5,       # сила / 40 + 5
    "special": 8,      # сила / 30 + 8
    "mega": 15,        # сила / 20 + 15
    "fused": 10,       # сила / 25 + 10
    "mega_fused": 25,  # сила / 15 + 25
}

# Хранилище стоков для каждого чата
_stocks = {}


# ═══════════════════════════════════════════════════════════════
#                         УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════

def is_group(msg):
    return msg.chat.type in ["group", "supergroup"]


def get_db(obj):
    if isinstance(obj, Message):
        return DatabaseManager.get_db(obj.chat.id)
    return DatabaseManager.get_db(obj.message.chat.id)


def get_chat_id(obj):
    if isinstance(obj, Message):
        return obj.chat.id
    return obj.message.chat.id


async def safe_edit(cb, text, kb=None):
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            raise
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except:
            pass
    except:
        pass


def format_num(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def get_card_power(card):
    return card.get("attack", 0) + card.get("defense", 0)


def get_stock_price(card):
    """Получить цену карты в стоке"""
    rarity = card.get("rarity", "common")
    power = get_card_power(card)
    
    # За монеты (common, rare, epic)
    if rarity in STOCK_COIN_PRICE:
        base = STOCK_COIN_PRICE[rarity]
        price = max(10, power * base)
        # Добавляем рандом ±20%
        price = int(price * random.uniform(0.8, 1.2))
        return {"type": "coins", "amount": price}
    
    # За Mults (legendary+)
    if rarity in STOCK_MULTS_PRICE:
        base = STOCK_MULTS_PRICE[rarity]
        divisor = {
            "legendary": 50,
            "mythic": 40,
            "special": 30,
            "mega": 20,
            "fused": 25,
            "mega_fused": 15,
        }.get(rarity, 30)
        
        price = max(1, power // divisor + base)
        # Рандом ±15%
        price = max(1, int(price * random.uniform(0.85, 1.15)))
        return {"type": "mults", "amount": price}
    
    # По умолчанию за монеты
    return {"type": "coins", "amount": max(10, power * 3)}


def pick_rarity():
    """Выбрать случайную редкость по шансам"""
    roll = random.uniform(0, 100)
    cumulative = 0
    
    for rarity, chance in STOCK_RARITY_CHANCES.items():
        cumulative += chance
        if roll <= cumulative:
            return rarity
    
    return "common"


def generate_stock_item():
    """Сгенерировать один товар для стока"""
    rarity = pick_rarity()
    
    # Выбираем карту этой редкости
    available = [c for c in CARDS if c.get("rarity") == rarity]
    
    # Иногда добавляем fusion карты
    if rarity in ["legendary", "mythic"] and random.random() < 0.1:
        fused = [c for c in FUSION_CARDS if c.get("rarity") == "fused"]
        if fused:
            available = fused
            rarity = "fused"
    
    if rarity == "mega" and random.random() < 0.3:
        mega_fused = [c for c in FUSION_CARDS if c.get("rarity") == "mega_fused"]
        if mega_fused:
            available = mega_fused
            rarity = "mega_fused"
    
    if not available:
        available = [c for c in CARDS if c.get("rarity") == "common"]
    
    card = random.choice(available)
    price_info = get_stock_price(card)
    copies = STOCK_COPIES.get(rarity, 3)
    
    return {
        "card": card.copy(),
        "price_type": price_info["type"],
        "price": price_info["amount"],
        "copies_left": copies,
        "copies_total": copies,
    }


def generate_stock(chat_id: int):
    """Сгенерировать новый сток для чата"""
    items = []
    used_names = set()
    
    # Гарантируем хотя бы 1 редкую карту
    guaranteed_rare = False
    
    for _ in range(STOCK_SIZE):
        for attempt in range(10):  # Пробуем избежать дублей
            item = generate_stock_item()
            name = item["card"]["name"]
            
            if name not in used_names:
                used_names.add(name)
                items.append(item)
                
                if item["card"]["rarity"] in ["legendary", "mythic", "special", "mega"]:
                    guaranteed_rare = True
                break
    
    # Если нет редкой — добавляем принудительно
    if not guaranteed_rare and len(items) < STOCK_SIZE:
        rare_cards = [c for c in CARDS if c.get("rarity") in ["legendary", "mythic"]]
        if rare_cards:
            card = random.choice(rare_cards)
            if card["name"] not in used_names:
                price_info = get_stock_price(card)
                items.append({
                    "card": card.copy(),
                    "price_type": price_info["type"],
                    "price": price_info["amount"],
                    "copies_left": 1,
                    "copies_total": 1,
                })
    
    # Сортируем: сначала за монеты, потом за mults, внутри по редкости
    rarity_order = {
        "common": 0, "rare": 1, "epic": 2, "legendary": 3,
        "mythic": 4, "special": 5, "fused": 6, "mega": 7, "mega_fused": 8
    }
    
    items.sort(key=lambda x: (
        0 if x["price_type"] == "coins" else 1,
        rarity_order.get(x["card"]["rarity"], 0)
    ))
    
    return {
        "items": items,
        "generated_at": datetime.now(),
        "expires_at": datetime.now() + timedelta(seconds=STOCK_REFRESH_TIME),
    }


def get_stock(chat_id: int):
    """Получить текущий сток (или создать новый)"""
    global _stocks
    
    now = datetime.now()
    
    if chat_id in _stocks:
        stock = _stocks[chat_id]
        if stock["expires_at"] > now:
            return stock
    
    # Генерируем новый
    _stocks[chat_id] = generate_stock(chat_id)
    return _stocks[chat_id]


def refresh_stock(chat_id: int):
    """Принудительно обновить сток"""
    global _stocks
    _stocks[chat_id] = generate_stock(chat_id)
    return _stocks[chat_id]


def get_time_until_refresh(stock):
    """Сколько секунд до обновления"""
    now = datetime.now()
    delta = stock["expires_at"] - now
    return max(0, int(delta.total_seconds()))


def format_time(seconds):
    """Форматировать время"""
    if seconds <= 0:
        return "сейчас"
    
    mins = seconds // 60
    secs = seconds % 60
    
    if mins > 0:
        return f"{mins}м {secs}с"
    return f"{secs}с"


# ═══════════════════════════════════════════════════════════════
#                      ОТОБРАЖЕНИЕ СТОКА
# ═══════════════════════════════════════════════════════════════

def build_stock_text(stock, user):
    """Построить текст стока"""
    coins = user.get("coins", 0) if user else 0
    mults = user.get("mults", 0) if user else 0
    
    time_left = get_time_until_refresh(stock)
    
    text = (
        f"🏪 <b>STOCK</b>\n\n"
        f"💰 Монеты: <b>{coins:,}</b>\n"
        f"💎 Mults: <b>{mults}</b>\n\n"
        f"⏱ Обновление через: <b>{format_time(time_left)}</b>\n"
        f"{'─' * 25}\n"
    )
    
    # Разделяем на за монеты и за mults
    coin_items = [i for i in stock["items"] if i["price_type"] == "coins" and i["copies_left"] > 0]
    mults_items = [i for i in stock["items"] if i["price_type"] == "mults" and i["copies_left"] > 0]
    sold_out = [i for i in stock["items"] if i["copies_left"] <= 0]
    
    if coin_items:
        text += "\n<b>💰 За монеты:</b>\n"
        for item in coin_items:
            card = item["card"]
            rc = RARITY_COLORS.get(card["rarity"], "⚪")
            power = get_card_power(card)
            copies = f"x{item['copies_left']}" if item["copies_left"] > 1 else ""
            can = "✅" if coins >= item["price"] else "❌"
            
            text += f"{can} {rc}{card['emoji']} {card['name'][:12]} 💪{power} — <b>{item['price']}</b>🪙 {copies}\n"
    
    if mults_items:
        text += "\n<b>💎 За Mults:</b>\n"
        for item in mults_items:
            card = item["card"]
            rc = RARITY_COLORS.get(card["rarity"], "⚪")
            rn = RARITY_NAMES.get(card["rarity"], "")
            power = get_card_power(card)
            copies = f"x{item['copies_left']}" if item["copies_left"] > 1 else ""
            can = "✅" if mults >= item["price"] else "❌"
            
            text += f"{can} {rc}{card['emoji']} {card['name'][:12]} 💪{power} — <b>{item['price']}</b>💎 {copies}\n"
    
    if sold_out:
        text += "\n<b>❌ Распродано:</b>\n"
        for item in sold_out[:3]:
            card = item["card"]
            rc = RARITY_COLORS.get(card["rarity"], "⚪")
            text += f"<s>{rc}{card['emoji']} {card['name'][:12]}</s>\n"
        if len(sold_out) > 3:
            text += f"<i>...и ещё {len(sold_out) - 3}</i>\n"
    
    if not coin_items and not mults_items:
        text += "\n📭 <b>Всё распродано!</b>\n<i>Жди обновления...</i>\n"
    
    return text


def build_stock_keyboard(stock, user):
    """Построить клавиатуру стока"""
    coins = user.get("coins", 0) if user else 0
    mults = user.get("mults", 0) if user else 0
    
    btns = []
    
    for idx, item in enumerate(stock["items"]):
        if item["copies_left"] <= 0:
            continue
        
        card = item["card"]
        rc = RARITY_COLORS.get(card["rarity"], "⚪")
        
        if item["price_type"] == "coins":
            can_buy = coins >= item["price"]
            price_txt = f"{item['price']}🪙"
        else:
            can_buy = mults >= item["price"]
            price_txt = f"{item['price']}💎"
        
        status = "✅" if can_buy else "🔒"
        copies_txt = f" ({item['copies_left']})" if item["copies_left"] > 1 else ""
        
        btns.append([InlineKeyboardButton(
            text=f"{status} {rc}{card['emoji']} {card['name'][:10]}{copies_txt} = {price_txt}",
            callback_data=f"stk:buy:{idx}"
        )])
    
    # Кнопки управления
    btns.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="stk:refresh"),
        InlineKeyboardButton(text="❌ Закрыть", callback_data="stk:close"),
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=btns)


# ═══════════════════════════════════════════════════════════════
#                         КОМАНДЫ
# ═══════════════════════════════════════════════════════════════

@router.message(Command("stock", "сток", "store"))
async def cmd_stock(msg: Message):
    """Открыть сток"""
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    
    db = get_db(msg)
    uid = msg.from_user.id
    chat_id = msg.chat.id
    
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    
    user = db.get_user(uid)
    stock = get_stock(chat_id)
    
    text = build_stock_text(stock, user)
    kb = build_stock_keyboard(stock, user)
    
    await msg.reply(text, parse_mode="HTML", reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
#                        CALLBACKS
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "stk:refresh")
async def cb_refresh(cb: CallbackQuery):
    """Обновить отображение (не сам сток!)"""
    db = get_db(cb)
    uid = cb.from_user.id
    chat_id = get_chat_id(cb)
    
    user = db.get_user(uid)
    stock = get_stock(chat_id)
    
    text = build_stock_text(stock, user)
    kb = build_stock_keyboard(stock, user)
    
    await safe_edit(cb, text, kb)
    await cb.answer("🔄 Обновлено!")


@router.callback_query(F.data == "stk:close")
async def cb_close(cb: CallbackQuery):
    """Закрыть сток"""
    try:
        await cb.message.delete()
    except:
        pass
    await cb.answer()


@router.callback_query(F.data.startswith("stk:buy:"))
async def cb_buy(cb: CallbackQuery):
    """Купить карту из стока"""
    idx = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    chat_id = get_chat_id(cb)
    
    user = db.get_user(uid)
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    stock = get_stock(chat_id)
    
    # Проверяем валидность индекса
    if idx < 0 or idx >= len(stock["items"]):
        return await cb.answer("❌ Товар не найден!", show_alert=True)
    
    item = stock["items"][idx]
    
    # Проверяем наличие
    if item["copies_left"] <= 0:
        return await cb.answer("❌ Распродано!", show_alert=True)
    
    card = item["card"]
    price = item["price"]
    price_type = item["price_type"]
    
    # Проверяем баланс
    if price_type == "coins":
        if user.get("coins", 0) < price:
            return await cb.answer(f"❌ Нужно {price} 🪙!", show_alert=True)
        db.remove_coins(uid, price)
        currency_emoji = "🪙"
    else:
        if user.get("mults", 0) < price:
            return await cb.answer(f"❌ Нужно {price} 💎!", show_alert=True)
        db.remove_mults(uid, price)
        currency_emoji = "💎"
    
    # Выдаём карту
    db.add_card(uid, {
        "name": card["name"],
        "rarity": card["rarity"],
        "attack": card["attack"],
        "defense": card["defense"],
        "emoji": card["emoji"],
    })
    
    # Уменьшаем количество
    item["copies_left"] -= 1
    
    # Обновляем отображение
    user = db.get_user(uid)
    text = build_stock_text(stock, user)
    kb = build_stock_keyboard(stock, user)
    
    rc = RARITY_COLORS.get(card["rarity"], "⚪")
    power = get_card_power(card)
    
    await safe_edit(cb, text, kb)
    await cb.answer(
        f"✅ Куплено!\n{rc} {card['emoji']} {card['name']}\n💪 {power} | -{price}{currency_emoji}",
        show_alert=True
    )


# ═══════════════════════════════════════════════════════════════
#                    ИНТЕГРАЦИЯ С МАГАЗИНОМ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "sh:stock")
async def cb_stock_from_shop(cb: CallbackQuery):
    """Открыть сток из магазина"""
    db = get_db(cb)
    uid = cb.from_user.id
    chat_id = get_chat_id(cb)
    
    user = db.get_user(uid)
    stock = get_stock(chat_id)
    
    text = build_stock_text(stock, user)
    kb = build_stock_keyboard(stock, user)
    
    # Добавляем кнопку назад в магазин
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="◀️ Магазин", callback_data="sh:back")
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer()


# ═══════════════════════════════════════════════════════════════
#                     АДМИН КОМАНДЫ
# ═══════════════════════════════════════════════════════════════

@router.message(Command("stockrefresh", "refreshstock"))
async def cmd_force_refresh(msg: Message):
    """Принудительно обновить сток (админ)"""
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    
    # Проверка прав
    from handlers.admin import is_owner_or_creator
    from aiogram import Bot
    
    bot = msg.bot
    if not await is_owner_or_creator(msg, bot):
        return await msg.reply(f"{EMOJI['cross']} Только админы!")
    
    chat_id = msg.chat.id
    stock = refresh_stock(chat_id)
    
    # Показываем что появилось
    items_info = []
    for item in stock["items"]:
        card = item["card"]
        rc = RARITY_COLORS.get(card["rarity"], "⚪")
        price_txt = f"{item['price']}🪙" if item["price_type"] == "coins" else f"{item['price']}💎"
        items_info.append(f"{rc}{card['emoji']} {card['name'][:10]} = {price_txt}")
    
    await msg.reply(
        f"🔄 <b>Сток обновлён!</b>\n\n" + "\n".join(items_info),
        parse_mode="HTML"
    )


@router.message(Command("stockadd"))
async def cmd_stock_add(msg: Message):
    """Добавить карту в сток (админ)"""
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    
    from handlers.admin import is_owner_or_creator
    bot = msg.bot
    
    if not await is_owner_or_creator(msg, bot):
        return await msg.reply(f"{EMOJI['cross']} Только админы!")
    
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        return await msg.reply(
            "📦 <b>Добавить карту в сток</b>\n\n"
            "<code>/stockadd название карты</code>",
            parse_mode="HTML"
        )
    
    card_name = args[1].strip()
    
    # Ищем карту
    all_cards = CARDS + FUSION_CARDS
    found = None
    for c in all_cards:
        if c["name"].lower() == card_name.lower():
            found = c
            break
    
    if not found:
        for c in all_cards:
            if card_name.lower() in c["name"].lower():
                found = c
                break
    
    if not found:
        return await msg.reply(f"❌ Карта «{card_name}» не найдена!")
    
    chat_id = msg.chat.id
    stock = get_stock(chat_id)
    
    # Добавляем
    price_info = get_stock_price(found)
    copies = STOCK_COPIES.get(found["rarity"], 2)
    
    stock["items"].append({
        "card": found.copy(),
        "price_type": price_info["type"],
        "price": price_info["amount"],
        "copies_left": copies,
        "copies_total": copies,
    })
    
    rc = RARITY_COLORS.get(found["rarity"], "⚪")
    price_txt = f"{price_info['amount']}🪙" if price_info["type"] == "coins" else f"{price_info['amount']}💎"
    
    await msg.reply(
        f"✅ <b>Добавлено в сток!</b>\n\n"
        f"{rc} {found['emoji']} <b>{found['name']}</b>\n"
        f"💰 Цена: {price_txt}\n"
        f"📦 Копий: {copies}",
        parse_mode="HTML"
    )