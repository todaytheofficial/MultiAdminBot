# handlers/mults.py
"""
Система Mults — премиум валюта
- Обмен монет на Mults
- Магазин за Mults (бусты, билеты, щиты)
- Fusion карты (соединение двух карт)
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
import asyncio
import logging
from datetime import datetime, timedelta

from config import (
    EMOJI, CARDS, FUSION_CARDS, FUSION_RECIPES,
    MULTS_EXCHANGE_RATE, FUSION_COST_MULTS, MULTS_SHOP_ITEMS,
    RARITY_COLORS, RARITY_NAMES
)
from database import DatabaseManager

router = Router()
logger = logging.getLogger(__name__)

PER_PAGE = 5

# Стоимость MEGA Fusion
MEGA_FUSION_COST_MULTS = 10


# ══════════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ══════════════════════════════════════════════════════════════

def is_group(message: Message) -> bool:
    return message.chat.type in ["group", "supergroup"]


def is_group_cb(callback: CallbackQuery) -> bool:
    return callback.message.chat.type in ["group", "supergroup"]


def get_db(message: Message):
    return DatabaseManager.get_db(message.chat.id)


def get_db_cb(callback: CallbackQuery):
    return DatabaseManager.get_db(callback.message.chat.id)


def check_owner(callback: CallbackQuery, owner_id: int) -> bool:
    return callback.from_user.id == owner_id


def encode_cb(prefix: str, owner_id: int, *args) -> str:
    parts = [prefix, str(owner_id)] + [str(a) for a in args]
    return ":".join(parts)


def decode_cb(data: str) -> list:
    return data.split(":")


async def safe_edit(callback: CallbackQuery, text: str, kb=None):
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            logger.warning(f"Edit failed: {e}")
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"safe_edit error: {e}")


def get_card_by_name(name: str) -> dict | None:
    """Найти карту по имени (обычную или fusion)"""
    for card in CARDS:
        if card["name"] == name:
            return card
    for card in FUSION_CARDS:
        if card["name"] == name:
            return card
    return None


def user_has_card(user: dict, card_name: str) -> bool:
    """Проверить есть ли карта у пользователя"""
    return any(c.get("name") == card_name for c in user.get("cards", []))


def count_user_card(user: dict, card_name: str) -> int:
    """Сколько таких карт у пользователя"""
    return sum(1 for c in user.get("cards", []) if c.get("name") == card_name)


def get_card_power(card: dict) -> int:
    return card.get("attack", 0) + card.get("defense", 0)


def is_mega_fusion(card1_name: str, card2_name: str) -> bool:
    """Проверяет, является ли fusion мега-фьюжном"""
    card1 = get_card_by_name(card1_name)
    card2 = get_card_by_name(card2_name)
    if not card1 or not card2:
        return False
    return card1.get("rarity") == "mega" and card2.get("rarity") == "mega"


def get_fusion_cost(card1_name: str, card2_name: str) -> int:
    """Возвращает стоимость fusion в Mults"""
    if is_mega_fusion(card1_name, card2_name):
        return MEGA_FUSION_COST_MULTS
    return FUSION_COST_MULTS


# ══════════════════════════════════════════════════════════════
#  ГЛАВНОЕ МЕНЮ MULTS
# ══════════════════════════════════════════════════════════════

def build_mults_main_text(user: dict, owner_id: int) -> tuple:
    """Главное меню Mults"""
    coins = user.get("coins", 0)
    mults = user.get("mults", 0)
    
    # Активные бусты
    boosts_text = ""
    luck_boost = user.get("luck_boost", 1.0)
    luck_until = user.get("luck_boost_until")
    if luck_boost > 1.0 and luck_until:
        try:
            until_dt = datetime.fromisoformat(luck_until) if isinstance(luck_until, str) else luck_until
            if until_dt > datetime.now():
                remaining = until_dt - datetime.now()
                hours = int(remaining.total_seconds() // 3600)
                mins = int((remaining.total_seconds() % 3600) // 60)
                boosts_text = f"\n🍀 <b>Буст удачи x{luck_boost}</b> — {hours}ч {mins}м\n"
        except:
            pass
    
    text = (
        f"💎 <b>MULTS</b>\n\n"
        f"💰 Монеты: <b>{coins}</b> 🪙\n"
        f"💎 Mults: <b>{mults}</b>\n"
        f"{boosts_text}\n"
        f"📊 Курс: <b>{MULTS_EXCHANGE_RATE}</b> 🪙 = <b>1</b> 💎\n\n"
        f"Выбери действие:"
    )
    
    oid = owner_id
    buttons = [
        [InlineKeyboardButton(text="💱 Обменять монеты", 
                              callback_data=encode_cb("mex", oid))],
        [InlineKeyboardButton(text="🛒 Магазин Mults", 
                              callback_data=encode_cb("msh", oid, 0))],
        [InlineKeyboardButton(text="🔮 Fusion карты", 
                              callback_data=encode_cb("mfu", oid, 0))],
        [InlineKeyboardButton(text="📜 Рецепты Fusion", 
                              callback_data=encode_cb("mfr", oid, 0))],
        [InlineKeyboardButton(text="◀️ Назад в магазин", 
                              callback_data="market_back")]
    ]
    
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════════
#  ОБМЕН МОНЕТ НА MULTS
# ══════════════════════════════════════════════════════════════

def build_exchange_text(user: dict, owner_id: int) -> tuple:
    """Меню обмена монет на Mults"""
    coins = user.get("coins", 0)
    mults = user.get("mults", 0)
    
    max_exchange = coins // MULTS_EXCHANGE_RATE
    
    text = (
        f"💱 <b>ОБМЕН МОНЕТ → MULTS</b>\n\n"
        f"💰 Твои монеты: <b>{coins}</b> 🪙\n"
        f"💎 Твои Mults: <b>{mults}</b>\n\n"
        f"📊 Курс: <b>{MULTS_EXCHANGE_RATE}</b> 🪙 = <b>1</b> 💎\n"
        f"📦 Максимум: <b>{max_exchange}</b> 💎\n\n"
        f"Выбери количество:"
    )
    
    oid = owner_id
    buttons = []
    
    amounts = [1, 5, 10, 25, 50, 100]
    row = []
    for amt in amounts:
        cost = amt * MULTS_EXCHANGE_RATE
        if coins >= cost:
            row.append(InlineKeyboardButton(
                text=f"{amt} 💎 ({cost} 🪙)",
                callback_data=encode_cb("mexdo", oid, amt)
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)
    
    if max_exchange > 0:
        buttons.append([InlineKeyboardButton(
            text=f"🔄 Всё ({max_exchange} 💎)",
            callback_data=encode_cb("mexdo", oid, max_exchange)
        )])
    
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад",
        callback_data=encode_cb("mma", oid)
    )])
    
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════════
#  МАГАЗИН ЗА MULTS
# ══════════════════════════════════════════════════════════════

def build_mults_shop_text(user: dict, owner_id: int, page: int = 0) -> tuple:
    """Магазин товаров за Mults"""
    mults = user.get("mults", 0)
    
    items = list(MULTS_SHOP_ITEMS.items())
    total_pages = max(1, (len(items) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    
    start = page * PER_PAGE
    end = start + PER_PAGE
    page_items = items[start:end]
    
    text = (
        f"🛒 <b>МАГАЗИН MULTS</b>\n\n"
        f"💎 Твои Mults: <b>{mults}</b>\n\n"
    )
    
    for item_id, item in page_items:
        price = item["price_mults"]
        can_buy = "✅" if mults >= price else "❌"
        text += f"{can_buy} {item['name']} — <b>{price}</b> 💎\n"
        text += f"   <i>{item['description']}</i>\n\n"
    
    oid = owner_id
    buttons = []
    
    for item_id, item in page_items:
        price = item["price_mults"]
        if mults >= price:
            buttons.append([InlineKeyboardButton(
                text=f"🛒 {item['name']} ({price} 💎)",
                callback_data=encode_cb("msby", oid, item_id)
            )])
    
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀️", callback_data=encode_cb("msh", oid, page - 1)))
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶️", callback_data=encode_cb("msh", oid, page + 1)))
        buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад",
        callback_data=encode_cb("mma", oid)
    )])
    
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════════
#  FUSION — РЕЦЕПТЫ
# ══════════════════════════════════════════════════════════════

def build_fusion_recipes_text(user: dict, owner_id: int, page: int = 0) -> tuple:
    """Список рецептов Fusion"""
    recipes = list(FUSION_RECIPES.items())
    total_pages = max(1, (len(recipes) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    
    start = page * PER_PAGE
    end = start + PER_PAGE
    page_recipes = recipes[start:end]
    
    text = (
        f"📜 <b>РЕЦЕПТЫ FUSION</b>\n\n"
        f"💰 Стоимость:\n"
        f"   • Обычный: <b>{FUSION_COST_MULTS}</b> 💎\n"
        f"   • MEGA: <b>{MEGA_FUSION_COST_MULTS}</b> 💎\n\n"
    )
    
    for (card1, card2), result in page_recipes:
        has1 = "✅" if user_has_card(user, card1) else "❌"
        has2 = "✅" if user_has_card(user, card2) else "❌"
        
        result_card = get_card_by_name(result)
        result_emoji = result_card.get("emoji", "🔮") if result_card else "🔮"
        result_power = get_card_power(result_card) if result_card else "?"
        
        is_mega = is_mega_fusion(card1, card2)
        mega_badge = " 🌌" if is_mega else ""
        
        text += f"{has1} <b>{card1}</b> + {has2} <b>{card2}</b>{mega_badge}\n"
        text += f"   → {result_emoji} <b>{result}</b> (💪{result_power})\n\n"
    
    oid = owner_id
    buttons = []
    
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀️", callback_data=encode_cb("mfr", oid, page - 1)))
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶️", callback_data=encode_cb("mfr", oid, page + 1)))
        buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(
        text="🔮 Соединить карты",
        callback_data=encode_cb("mfu", oid, 0)
    )])
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад",
        callback_data=encode_cb("mma", oid)
    )])
    
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════════
#  FUSION — ДОСТУПНЫЕ СОЕДИНЕНИЯ
# ══════════════════════════════════════════════════════════════

def get_available_fusions(user: dict) -> list:
    """Получить список доступных fusion для пользователя"""
    available = []
    cards = user.get("cards", [])
    card_names = [c.get("name") for c in cards]
    
    for (card1, card2), result in FUSION_RECIPES.items():
        if card1 in card_names and card2 in card_names:
            result_card = get_card_by_name(result)
            if result_card:
                available.append({
                    "card1": card1,
                    "card2": card2,
                    "result": result,
                    "result_card": result_card
                })
    
    return available


def build_fusion_menu_text(user: dict, owner_id: int, page: int = 0) -> tuple:
    """Меню доступных Fusion"""
    mults = user.get("mults", 0)
    available = get_available_fusions(user)
    
    if not available:
        text = (
            f"🔮 <b>FUSION</b>\n\n"
            f"😔 У тебя нет подходящих пар карт!\n\n"
            f"📜 Посмотри рецепты и собери нужные карты:\n"
            f"• /spin — крутить рулетку\n"
            f"• /shop — купить карты\n"
        )
        buttons = [
            [InlineKeyboardButton(text="📜 Рецепты", 
                                  callback_data=encode_cb("mfr", owner_id, 0))],
            [InlineKeyboardButton(text="◀️ Назад", 
                                  callback_data=encode_cb("mma", owner_id))]
        ]
        return text, InlineKeyboardMarkup(inline_keyboard=buttons)
    
    total_pages = max(1, (len(available) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    
    start = page * PER_PAGE
    end = start + PER_PAGE
    page_fusions = available[start:end]
    
    text = (
        f"🔮 <b>FUSION — СОЕДИНЕНИЕ КАРТ</b>\n\n"
        f"💎 Mults: <b>{mults}</b>\n\n"
        f"💰 Стоимость:\n"
        f"   • Обычный: <b>{FUSION_COST_MULTS}</b> 💎\n"
        f"   • MEGA: <b>{MEGA_FUSION_COST_MULTS}</b> 💎\n\n"
        f"<b>Доступные соединения ({len(available)}):</b>\n\n"
    )
    
    oid = owner_id
    buttons = []
    
    for i, fusion in enumerate(page_fusions, start=start):
        card1 = get_card_by_name(fusion["card1"])
        card2 = get_card_by_name(fusion["card2"])
        result = fusion["result_card"]
        
        e1 = card1.get("emoji", "🃏") if card1 else "🃏"
        e2 = card2.get("emoji", "🃏") if card2 else "🃏"
        er = result.get("emoji", "🔮")
        
        cost = get_fusion_cost(fusion["card1"], fusion["card2"])
        is_mega = is_mega_fusion(fusion["card1"], fusion["card2"])
        mega_badge = " 🌌" if is_mega else ""
        can_afford = mults >= cost
        status = "✅" if can_afford else f"❌ ({cost}💎)"
        
        text += f"{status}{mega_badge} {e1} <b>{fusion['card1']}</b> + {e2} <b>{fusion['card2']}</b>\n"
        text += f"   → {er} <b>{fusion['result']}</b> (💪{get_card_power(result)}) [{cost}💎]\n\n"
        
        if can_afford:
            btn_text = f"{'🌌' if is_mega else '🔮'} {fusion['card1'][:10]}+{fusion['card2'][:10]}"
            buttons.append([InlineKeyboardButton(
                text=btn_text,
                callback_data=encode_cb("mfudo", oid, i)
            )])
    
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="◀️", callback_data=encode_cb("mfu", oid, page - 1)))
        nav_row.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                text="▶️", callback_data=encode_cb("mfu", oid, page + 1)))
        buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton(
        text="📜 Все рецепты",
        callback_data=encode_cb("mfr", oid, 0)
    )])
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад",
        callback_data=encode_cb("mma", oid)
    )])
    
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════════
#  КОМАНДЫ
# ══════════════════════════════════════════════════════════════

@router.message(Command("mults"))
@router.message(Command("премиум"))
async def cmd_mults(message: Message):
    """Главное меню Mults"""
    if not is_group(message):
        return await message.reply(f"{EMOJI['cross']} Команда работает только в группах!")
    
    db = get_db(message)
    user_id = message.from_user.id
    
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, message.from_user.username, message.from_user.first_name)
        user = db.get_user(user_id)
    
    text, kb = build_mults_main_text(user, user_id)
    await message.reply(text, parse_mode="HTML", reply_markup=kb)


@router.message(Command("fusion"))
@router.message(Command("фьюжн"))
async def cmd_fusion(message: Message):
    """Меню Fusion"""
    if not is_group(message):
        return await message.reply(f"{EMOJI['cross']} Команда работает только в группах!")
    
    db = get_db(message)
    user_id = message.from_user.id
    
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, message.from_user.username, message.from_user.first_name)
        user = db.get_user(user_id)
    
    text, kb = build_fusion_menu_text(user, user_id, 0)
    await message.reply(text, parse_mode="HTML", reply_markup=kb)


@router.message(Command("recipes"))
@router.message(Command("рецепты"))
async def cmd_recipes(message: Message):
    """Рецепты Fusion"""
    if not is_group(message):
        return await message.reply(f"{EMOJI['cross']} Команда работает только в группах!")
    
    db = get_db(message)
    user_id = message.from_user.id
    
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, message.from_user.username, message.from_user.first_name)
        user = db.get_user(user_id)
    
    text, kb = build_fusion_recipes_text(user, user_id, 0)
    await message.reply(text, parse_mode="HTML", reply_markup=kb)


# ══════════════════════════════════════════════════════════════
#  CALLBACK HANDLERS
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "mults_main")
async def cb_mults_main_simple(callback: CallbackQuery):
    """Вход из магазина (без owner_id в callback)"""
    if not is_group_cb(callback):
        return await callback.answer("❌ Только в группах!", show_alert=True)
    
    db = get_db_cb(callback)
    user_id = callback.from_user.id
    
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, callback.from_user.username, callback.from_user.first_name)
        user = db.get_user(user_id)
    
    text, kb = build_mults_main_text(user, user_id)
    await safe_edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("mma:"))
async def cb_mults_main(callback: CallbackQuery):
    parts = decode_cb(callback.data)
    try:
        owner_id = int(parts[1])
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    if not check_owner(callback, owner_id):
        return await callback.answer("❌ Это не твоё меню!", show_alert=True)
    
    db = get_db_cb(callback)
    user = db.get_user(owner_id)
    
    if not user:
        return await callback.answer("❌ Профиль не найден!", show_alert=True)
    
    text, kb = build_mults_main_text(user, owner_id)
    await safe_edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("mex:"))
async def cb_exchange_menu(callback: CallbackQuery):
    parts = decode_cb(callback.data)
    try:
        owner_id = int(parts[1])
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    if not check_owner(callback, owner_id):
        return await callback.answer("❌ Это не твоё меню!", show_alert=True)
    
    db = get_db_cb(callback)
    user = db.get_user(owner_id)
    
    if not user:
        return await callback.answer("❌ Профиль не найден!", show_alert=True)
    
    text, kb = build_exchange_text(user, owner_id)
    await safe_edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("mexdo:"))
async def cb_exchange_do(callback: CallbackQuery):
    parts = decode_cb(callback.data)
    try:
        owner_id = int(parts[1])
        amount = int(parts[2])
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    if not check_owner(callback, owner_id):
        return await callback.answer("❌ Это не твоё меню!", show_alert=True)
    
    db = get_db_cb(callback)
    user = db.get_user(owner_id)
    
    if not user:
        return await callback.answer("❌ Профиль не найден!", show_alert=True)
    
    cost = amount * MULTS_EXCHANGE_RATE
    coins = user.get("coins", 0)
    
    if coins < cost:
        return await callback.answer(f"❌ Нужно {cost} 🪙!", show_alert=True)
    
    try:
        db.remove_coins(owner_id, cost)
        db.add_mults(owner_id, amount)
    except Exception as e:
        logger.error(f"Exchange error for user {owner_id}: {e}")
        return await callback.answer("❌ Ошибка при обмене!", show_alert=True)
    
    user = db.get_user(owner_id)
    new_coins = user.get("coins", 0)
    new_mults = user.get("mults", 0)
    
    text = (
        f"✅ <b>ОБМЕН УСПЕШЕН!</b>\n\n"
        f"💰 -{cost} 🪙\n"
        f"💎 +{amount} Mults\n\n"
        f"💰 Монеты: <b>{new_coins}</b>\n"
        f"💎 Mults: <b>{new_mults}</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💱 Ещё", callback_data=encode_cb("mex", owner_id))],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=encode_cb("mma", owner_id))]
    ])
    
    await safe_edit(callback, text, kb)
    await callback.answer(f"✅ +{amount} 💎")


@router.callback_query(F.data.startswith("msh:"))
async def cb_mults_shop(callback: CallbackQuery):
    parts = decode_cb(callback.data)
    try:
        owner_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    if not check_owner(callback, owner_id):
        return await callback.answer("❌ Это не твоё меню!", show_alert=True)
    
    db = get_db_cb(callback)
    user = db.get_user(owner_id)
    
    if not user:
        return await callback.answer("❌ Профиль не найден!", show_alert=True)
    
    text, kb = build_mults_shop_text(user, owner_id, page)
    await safe_edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("msby:"))
async def cb_mults_shop_buy(callback: CallbackQuery):
    parts = decode_cb(callback.data)
    try:
        owner_id = int(parts[1])
        item_id = parts[2]
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    if not check_owner(callback, owner_id):
        return await callback.answer("❌ Это не твоё меню!", show_alert=True)
    
    item = MULTS_SHOP_ITEMS.get(item_id)
    if not item:
        return await callback.answer("❌ Товар не найден!", show_alert=True)
    
    db = get_db_cb(callback)
    user = db.get_user(owner_id)
    
    if not user:
        return await callback.answer("❌ Профиль не найден!", show_alert=True)
    
    price = item["price_mults"]
    mults = user.get("mults", 0)
    
    if mults < price:
        return await callback.answer(f"❌ Нужно {price} 💎!", show_alert=True)
    
    try:
        db.remove_mults(owner_id, price)
    except Exception as e:
        logger.error(f"Buy mults item error: {e}")
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    result_text = ""
    item_type = item["type"]
    value = item["value"]
    
    try:
        if item_type == "tickets":
            db.add_tickets(owner_id, value)
            result_text = f"🎫 +{value} билетов"
        elif item_type == "shields":
            db.add_shields(owner_id, value)
            result_text = f"🛡️ +{value} щитов"
        elif item_type == "coins":
            db.add_coins(owner_id, value)
            result_text = f"💰 +{value} монет"
        elif item_type == "boost":
            duration = item.get("duration", 6)
            until = datetime.now() + timedelta(hours=duration)
            db.set_luck_boost(owner_id, value, until.isoformat())
            result_text = f"🍀 Буст удачи x{value} на {duration}ч"
        elif item_type == "fusion":
            current_tokens = user.get("fusion_tokens", 0)
            db.update_user(owner_id, {"fusion_tokens": current_tokens + value})
            result_text = f"🔮 +{value} токенов Fusion"
        else:
            result_text = f"✅ {item['name']}"
    except Exception as e:
        logger.error(f"Apply item error: {e}")
        db.add_mults(owner_id, price)
        return await callback.answer("❌ Ошибка при получении товара!", show_alert=True)
    
    user = db.get_user(owner_id)
    new_mults = user.get("mults", 0)
    
    text = (
        f"✅ <b>КУПЛЕНО!</b>\n\n"
        f"{item['name']}\n"
        f"💎 -{price} Mults\n\n"
        f"{result_text}\n\n"
        f"💎 Остаток: <b>{new_mults}</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Ещё", callback_data=encode_cb("msh", owner_id, 0))],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=encode_cb("mma", owner_id))]
    ])
    
    await safe_edit(callback, text, kb)
    await callback.answer(f"✅ {result_text}")


@router.callback_query(F.data.startswith("mfr:"))
async def cb_fusion_recipes(callback: CallbackQuery):
    parts = decode_cb(callback.data)
    try:
        owner_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    if not check_owner(callback, owner_id):
        return await callback.answer("❌ Это не твоё меню!", show_alert=True)
    
    db = get_db_cb(callback)
    user = db.get_user(owner_id)
    
    if not user:
        return await callback.answer("❌ Профиль не найден!", show_alert=True)
    
    text, kb = build_fusion_recipes_text(user, owner_id, page)
    await safe_edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("mfu:"))
async def cb_fusion_menu(callback: CallbackQuery):
    parts = decode_cb(callback.data)
    try:
        owner_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    if not check_owner(callback, owner_id):
        return await callback.answer("❌ Это не твоё меню!", show_alert=True)
    
    db = get_db_cb(callback)
    user = db.get_user(owner_id)
    
    if not user:
        return await callback.answer("❌ Профиль не найден!", show_alert=True)
    
    text, kb = build_fusion_menu_text(user, owner_id, page)
    await safe_edit(callback, text, kb)
    await callback.answer()


@router.callback_query(F.data.startswith("mfudo:"))
async def cb_fusion_do(callback: CallbackQuery):
    parts = decode_cb(callback.data)
    try:
        owner_id = int(parts[1])
        fusion_index = int(parts[2])
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    if not check_owner(callback, owner_id):
        return await callback.answer("❌ Это не твоё меню!", show_alert=True)
    
    db = get_db_cb(callback)
    user = db.get_user(owner_id)
    
    if not user:
        return await callback.answer("❌ Профиль не найден!", show_alert=True)
    
    available = get_available_fusions(user)
    
    if fusion_index < 0 or fusion_index >= len(available):
        return await callback.answer("❌ Соединение недоступно!", show_alert=True)
    
    fusion = available[fusion_index]
    card1_name = fusion["card1"]
    card2_name = fusion["card2"]
    result_name = fusion["result"]
    result_card = fusion["result_card"]
    
    cost = get_fusion_cost(card1_name, card2_name)
    is_mega = is_mega_fusion(card1_name, card2_name)
    
    mults = user.get("mults", 0)
    fusion_tokens = user.get("fusion_tokens", 0)
    
    use_token = False
    if not is_mega and fusion_tokens > 0:
        use_token = True
    elif mults < cost:
        return await callback.answer(f"❌ Нужно {cost} 💎!", show_alert=True)
    
    if not user_has_card(user, card1_name) or not user_has_card(user, card2_name):
        return await callback.answer("❌ Карты не найдены!", show_alert=True)
    
    try:
        if use_token:
            db.update_user(owner_id, {"fusion_tokens": fusion_tokens - 1})
        else:
            db.remove_mults(owner_id, cost)
        
        db.remove_card_from_user(owner_id, card1_name)
        db.remove_card_from_user(owner_id, card2_name)
        
        db.add_card(owner_id, {
            "name": result_card["name"],
            "rarity": result_card.get("rarity", "fused"),
            "attack": result_card.get("attack", 100),
            "defense": result_card.get("defense", 80),
            "emoji": result_card.get("emoji", "🔮"),
            "description": result_card.get("description", "Fusion карта")
        })
        
    except Exception as e:
        logger.error(f"Fusion error for user {owner_id}: {e}")
        return await callback.answer("❌ Ошибка при соединении!", show_alert=True)
    
    user = db.get_user(owner_id)
    new_mults = user.get("mults", 0)
    
    card1 = get_card_by_name(card1_name)
    card2 = get_card_by_name(card2_name)
    e1 = card1.get("emoji", "🃏") if card1 else "🃏"
    e2 = card2.get("emoji", "🃏") if card2 else "🃏"
    er = result_card.get("emoji", "🔮")
    
    rarity = result_card.get("rarity", "fused")
    rarity_color = RARITY_COLORS.get(rarity, "🔮")
    rarity_name = RARITY_NAMES.get(rarity, "Fused")
    power = get_card_power(result_card)
    
    payment_text = "🔮 -1 токен Fusion" if use_token else f"💎 -{cost} Mults"
    mega_text = "\n\n🌌 <b>MEGA FUSION!</b>" if is_mega else ""
    
    text = (
        f"🔮 <b>FUSION УСПЕШЕН!</b>{mega_text}\n\n"
        f"{e1} {card1_name} + {e2} {card2_name}\n"
        f"       ⬇️\n"
        f"{er} <b>{result_name}</b>\n"
        f"{rarity_color} {rarity_name}\n"
        f"💪 Сила: <b>{power}</b>\n\n"
        f"{payment_text}\n"
        f"💎 Остаток: <b>{new_mults}</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔮 Ещё Fusion", callback_data=encode_cb("mfu", owner_id, 0))],
        [InlineKeyboardButton(text="🃏 Мои карты", callback_data=encode_cb("mc", owner_id, "rarity", 0))],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=encode_cb("mma", owner_id))]
    ])
    
    await safe_edit(callback, text, kb)
    await callback.answer(f"{'🌌' if is_mega else '🔮'} {result_name}!", show_alert=True)


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()