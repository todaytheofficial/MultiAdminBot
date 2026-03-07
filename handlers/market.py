# handlers/market.py
"""
Полный реворк маркета
- Удобный интерфейс без рамок
- Покупка на все деньги
- Умное ценообразование
"""

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
import asyncio
import math

from config import EMOJI, CARDS, RARITY_COLORS, RARITY_NAMES, LIMITED_CARDS, FUSION_CARDS
from database import DatabaseManager

router = Router()

PER_PAGE = 8


class SellStates(StatesGroup):
    waiting_price = State()


# ═══════════════════════════════════════════════════════════════
#                         УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════

def is_group(msg):
    return msg.chat.type in ["group", "supergroup"]


def get_db(obj):
    if isinstance(obj, Message):
        return DatabaseManager.get_db(obj.chat.id)
    return DatabaseManager.get_db(obj.message.chat.id)


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


def get_all_cards():
    return CARDS + LIMITED_CARDS + FUSION_CARDS


def find_card(name):
    for c in get_all_cards():
        if c["name"] == name:
            return c
    return None


RARITY_ORDER = {
    "mega_fused": 0, "mega": 1, "fused": 2, "limited": 3,
    "special": 4, "mythic": 5, "legendary": 6, "epic": 7, "rare": 8, "common": 9
}

# Комиссия рынка
MARKET_FEE = 10  # 10%

# Быстрая продажа — процент от базовой цены
QUICK_SELL_PERCENT = 5  # 5%


def get_base_price(card):
    """Базовая цена карты"""
    power = card["attack"] + card["defense"]
    mult = {
        "common": 2, "rare": 4, "epic": 8, "legendary": 15, "mythic": 25,
        "special": 50, "mega": 60, "limited": 55, "fused": 80, "mega_fused": 120
    }
    return max(1, power * mult.get(card["rarity"], 2))


def get_quick_price(card):
    """Цена быстрой продажи"""
    return max(1, int(get_base_price(card) * QUICK_SELL_PERCENT / 100))


def group_cards(cards):
    """Группировка карт по имени"""
    groups = {}
    for c in cards:
        n = c["name"]
        if n not in groups:
            groups[n] = {"card": c, "count": 0}
        groups[n]["count"] += 1
    return sorted(
        groups.values(),
        key=lambda x: (RARITY_ORDER.get(x["card"]["rarity"], 99), -(x["card"]["attack"] + x["card"]["defense"]))
    )


def format_num(n):
    """Форматирование чисел: 1000000 -> 1M"""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


# ═══════════════════════════════════════════════════════════════
#                    ЦЕНЫ НА БИЛЕТЫ (ПРОГРЕССИВНЫЕ)
# ═══════════════════════════════════════════════════════════════

def get_ticket_price(amount: int) -> int:
    """
    Прогрессивная цена билетов:
    - 1-10: 50 монет за билет
    - 11-50: 55 монет
    - 51-100: 60 монет
    - 101-500: 70 монет
    - 500+: 80 монет
    """
    if amount <= 0:
        return 0
    
    total = 0
    remaining = amount
    
    # Первые 10 по 50
    tier1 = min(remaining, 10)
    total += tier1 * 50
    remaining -= tier1
    
    # 11-50 по 55
    if remaining > 0:
        tier2 = min(remaining, 40)
        total += tier2 * 55
        remaining -= tier2
    
    # 51-100 по 60
    if remaining > 0:
        tier3 = min(remaining, 50)
        total += tier3 * 60
        remaining -= tier3
    
    # 101-500 по 70
    if remaining > 0:
        tier4 = min(remaining, 400)
        total += tier4 * 70
        remaining -= tier4
    
    # 500+ по 80
    if remaining > 0:
        total += remaining * 80
    
    return total


def get_max_tickets_for_coins(coins: int) -> int:
    """Сколько билетов можно купить за монеты"""
    if coins <= 0:
        return 0
    
    # Бинарный поиск
    low, high = 0, coins // 50 + 1
    while low < high:
        mid = (low + high + 1) // 2
        if get_ticket_price(mid) <= coins:
            low = mid
        else:
            high = mid - 1
    return low


def get_avg_ticket_price(amount: int) -> float:
    """Средняя цена за билет"""
    if amount <= 0:
        return 50
    return get_ticket_price(amount) / amount


# ═══════════════════════════════════════════════════════════════
#                    ЦЕНЫ НА ЩИТЫ (ПРОГРЕССИВНЫЕ)
# ═══════════════════════════════════════════════════════════════

def get_shield_price(amount: int) -> int:
    """
    Прогрессивная цена щитов:
    - 1-5: 150 монет
    - 6-20: 170 монет
    - 21+: 200 монет
    """
    if amount <= 0:
        return 0
    
    total = 0
    remaining = amount
    
    tier1 = min(remaining, 5)
    total += tier1 * 150
    remaining -= tier1
    
    if remaining > 0:
        tier2 = min(remaining, 15)
        total += tier2 * 170
        remaining -= tier2
    
    if remaining > 0:
        total += remaining * 200
    
    return total


def get_max_shields_for_coins(coins: int) -> int:
    """Сколько щитов можно купить за монеты"""
    if coins <= 0:
        return 0
    
    low, high = 0, coins // 150 + 1
    while low < high:
        mid = (low + high + 1) // 2
        if get_shield_price(mid) <= coins:
            low = mid
        else:
            high = mid - 1
    return low


# ═══════════════════════════════════════════════════════════════
#                       ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════════════════════════

def build_main_menu(db, uid):
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    mults = user.get("mults", 0) if user else 0
    tickets = user.get("spin_tickets", 0) if user else 0
    shields = user.get("shields", 0) if user else 0
    cards_count = len(user.get("cards", [])) if user else 0
    
    listings = db.get_all_listings() or []
    other_listings = len([l for l in listings if l.get("seller_id") != uid])
    my_listings = len(db.get_my_listings(uid) or [])
    
    text = (
        f"🏪 <b>МАГАЗИН</b>\n\n"
        f"💰 Монеты: <b>{coins:,}</b>\n"
        f"💎 Mults: <b>{mults}</b>\n"
        f"🎫 Билеты: <b>{tickets}</b>\n"
        f"🛡 Щиты: <b>{shields}</b>\n"
        f"🃏 Карты: <b>{cards_count}</b>\n"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        # Покупка
        [
            InlineKeyboardButton(text="🎫 Билеты", callback_data="sh:tickets"),
            InlineKeyboardButton(text="🛡 Щиты", callback_data="sh:shields"),
        ],
        # Рынок
        [InlineKeyboardButton(
            text=f"🃏 Карты игроков" + (f" ({other_listings})" if other_listings else ""),
            callback_data="sh:market:0"
        )],
        # Продажа
        [
            InlineKeyboardButton(text="📤 Продать", callback_data="sh:sell:0"),
            InlineKeyboardButton(text="⚡ Быстро", callback_data="sh:quick:0"),
        ],
        # Мои и мусор
        [
            InlineKeyboardButton(
                text=f"📝 Мои лоты" + (f" ({my_listings})" if my_listings else ""),
                callback_data="sh:my:0"
            ),
            InlineKeyboardButton(text="🗑 Дубли", callback_data="sh:trash"),
        ],
        # Mults
        [InlineKeyboardButton(text="💎 Mults Shop", callback_data="mults_main")],
        [InlineKeyboardButton(text="📦 Stock", callback_data="sh:stock")],
        # Закрыть
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="sh:close")],
    ])
    
    return text, kb


@router.message(Command("market", "shop", "магазин"))
async def cmd_market(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    
    db = get_db(msg)
    uid = msg.from_user.id
    
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    
    text, kb = build_main_menu(db, uid)
    await msg.reply(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "sh:back")
async def cb_back(cb: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    db = get_db(cb)
    text, kb = build_main_menu(db, cb.from_user.id)
    await safe_edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data == "sh:close")
async def cb_close(cb: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    try:
        await cb.message.delete()
    except:
        pass
    await cb.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


# ═══════════════════════════════════════════════════════════════
#                      ПОКУПКА БИЛЕТОВ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "sh:tickets")
async def cb_tickets_menu(cb: CallbackQuery):
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    tickets = user.get("spin_tickets", 0) if user else 0
    
    max_tickets = get_max_tickets_for_coins(coins)
    
    text = (
        f"🎫 <b>БИЛЕТЫ</b>\n\n"
        f"💰 Монеты: <b>{coins:,}</b>\n"
        f"🎫 Билетов: <b>{tickets}</b>\n\n"
        f"<b>📊 Цены (прогрессивные):</b>\n"
        f"• 1-10 шт: <b>50</b> 🪙/шт\n"
        f"• 11-50 шт: <b>55</b> 🪙/шт\n"
        f"• 51-100 шт: <b>60</b> 🪙/шт\n"
        f"• 101-500 шт: <b>70</b> 🪙/шт\n"
        f"• 500+ шт: <b>80</b> 🪙/шт\n\n"
        f"💡 Максимум за твои монеты: <b>{max_tickets}</b> шт"
    )
    
    # Кнопки быстрой покупки
    amounts = [1, 5, 10, 25, 50, 100]
    btns = []
    row = []
    
    for amt in amounts:
        price = get_ticket_price(amt)
        if coins >= price:
            row.append(InlineKeyboardButton(
                text=f"{amt}🎫 = {format_num(price)}🪙",
                callback_data=f"sh:buyt:{amt}"
            ))
            if len(row) == 2:
                btns.append(row)
                row = []
    
    if row:
        btns.append(row)
    
    # Купить на все
    if max_tickets > 0:
        all_price = get_ticket_price(max_tickets)
        btns.append([InlineKeyboardButton(
            text=f"🔥 ВСЁ: {max_tickets}🎫 = {format_num(all_price)}🪙",
            callback_data=f"sh:buyt:{max_tickets}"
        )])
    
    # Ввести своё количество
    btns.append([InlineKeyboardButton(text="✏️ Своё количество", callback_data="sh:tcustom")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("sh:buyt:"))
async def cb_buy_tickets(cb: CallbackQuery):
    amount = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    
    price = get_ticket_price(amount)
    
    if coins < price:
        return await cb.answer(f"❌ Нужно {format_num(price)} 🪙!", show_alert=True)
    
    db.remove_coins(uid, price)
    db.add_tickets(uid, amount)
    
    new_coins = db.get_coins(uid)
    new_tickets = db.get_spin_tickets(uid)
    avg_price = price / amount
    
    text = (
        f"✅ <b>КУПЛЕНО!</b>\n\n"
        f"🎫 +{amount} билетов\n"
        f"💰 -{format_num(price)} монет\n"
        f"📊 Средняя цена: {avg_price:.1f} 🪙/шт\n\n"
        f"💰 Баланс: <b>{new_coins:,}</b>\n"
        f"🎫 Билетов: <b>{new_tickets}</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 Ещё билеты", callback_data="sh:tickets")],
        [InlineKeyboardButton(text="🎰 Крутить /spin", callback_data="sh:close")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="sh:back")],
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer(f"✅ +{amount} 🎫")


@router.callback_query(F.data == "sh:tcustom")
async def cb_tickets_custom(cb: CallbackQuery, state: FSMContext):
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    max_tickets = get_max_tickets_for_coins(coins)
    
    text = (
        f"✏️ <b>Введи количество билетов</b>\n\n"
        f"💰 Твои монеты: <b>{coins:,}</b>\n"
        f"📦 Максимум: <b>{max_tickets}</b> шт\n\n"
        f"Напиши число (1 - {max_tickets}):"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="sh:tickets")]
    ])
    
    await state.set_state(SellStates.waiting_price)
    await state.update_data(mode="buy_tickets", owner_id=uid)
    
    await safe_edit(cb, text, kb)
    await cb.answer()


# ═══════════════════════════════════════════════════════════════
#                       ПОКУПКА ЩИТОВ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "sh:shields")
async def cb_shields_menu(cb: CallbackQuery):
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    shields = user.get("shields", 0) if user else 0
    
    max_shields = get_max_shields_for_coins(coins)
    
    text = (
        f"🛡 <b>ЩИТЫ</b>\n\n"
        f"💰 Монеты: <b>{coins:,}</b>\n"
        f"🛡 Щитов: <b>{shields}</b>\n\n"
        f"<b>📊 Цены (прогрессивные):</b>\n"
        f"• 1-5 шт: <b>150</b> 🪙/шт\n"
        f"• 6-20 шт: <b>170</b> 🪙/шт\n"
        f"• 21+ шт: <b>200</b> 🪙/шт\n\n"
        f"💡 Максимум: <b>{max_shields}</b> шт\n\n"
        f"<i>Щит защищает от поражения на арене</i>"
    )
    
    amounts = [1, 3, 5, 10, 20]
    btns = []
    row = []
    
    for amt in amounts:
        price = get_shield_price(amt)
        if coins >= price:
            row.append(InlineKeyboardButton(
                text=f"{amt}🛡 = {price}🪙",
                callback_data=f"sh:buys:{amt}"
            ))
            if len(row) == 2:
                btns.append(row)
                row = []
    
    if row:
        btns.append(row)
    
    if max_shields > 0:
        all_price = get_shield_price(max_shields)
        btns.append([InlineKeyboardButton(
            text=f"🔥 ВСЁ: {max_shields}🛡 = {format_num(all_price)}🪙",
            callback_data=f"sh:buys:{max_shields}"
        )])
    
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("sh:buys:"))
async def cb_buy_shields(cb: CallbackQuery):
    amount = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    
    price = get_shield_price(amount)
    
    if coins < price:
        return await cb.answer(f"❌ Нужно {price} 🪙!", show_alert=True)
    
    db.remove_coins(uid, price)
    db.add_shields(uid, amount)
    
    new_coins = db.get_coins(uid)
    new_shields = db.get_shields(uid)
    
    text = (
        f"✅ <b>КУПЛЕНО!</b>\n\n"
        f"🛡 +{amount} щитов\n"
        f"💰 -{price} монет\n\n"
        f"💰 Баланс: <b>{new_coins:,}</b>\n"
        f"🛡 Щитов: <b>{new_shields}</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡 Ещё щиты", callback_data="sh:shields")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="sh:back")],
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer(f"✅ +{amount} 🛡")


# ═══════════════════════════════════════════════════════════════
#                      РЫНОК КАРТ ИГРОКОВ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("sh:market:"))
async def cb_market_cards(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    
    listings = db.get_all_listings() or []
    listings = [l for l in listings if l.get("seller_id") != uid]
    
    if not listings:
        text = (
            f"🃏 <b>КАРТЫ ИГРОКОВ</b>\n\n"
            f"📭 Пока пусто!\n\n"
            f"<i>Выстави свои карты на продажу</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Продать карту", callback_data="sh:sell:0")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")],
        ])
        await safe_edit(cb, text, kb)
        return await cb.answer()
    
    # Сортируем по цене
    listings.sort(key=lambda x: x.get("price", 0))
    
    total_pages = max(1, (len(listings) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = listings[page * PER_PAGE:(page + 1) * PER_PAGE]
    
    text = (
        f"🃏 <b>КАРТЫ ИГРОКОВ</b>\n\n"
        f"💰 Твои монеты: <b>{coins:,}</b>\n"
        f"📦 Лотов: <b>{len(listings)}</b>\n\n"
    )
    
    btns = []
    for l in page_items:
        card = find_card(l.get("card_name", ""))
        if not card:
            continue
        
        price = l.get("price", 0)
        lid = l.get("id")
        rc = RARITY_COLORS.get(card["rarity"], "⚪")
        power = card["attack"] + card["defense"]
        can = "✅" if coins >= price else "❌"
        
        btns.append([InlineKeyboardButton(
            text=f"{can} {rc}{card['emoji']} {card['name'][:12]} 💪{power} = {format_num(price)}🪙",
            callback_data=f"sh:buyc:{lid}"
        )])
    
    # Пагинация
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"sh:market:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"sh:market:{page+1}"))
        btns.append(nav)
    
    btns.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"sh:market:{page}")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("sh:buyc:"))
async def cb_buy_card(cb: CallbackQuery):
    lid = cb.data.split(":")[2]
    
    db = get_db(cb)
    uid = cb.from_user.id
    
    listing = db.get_listing_by_id(lid)
    if not listing:
        return await cb.answer("❌ Уже продано!", show_alert=True)
    
    card = find_card(listing.get("card_name", ""))
    if not card:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    price = listing.get("price", 0)
    seller_id = listing.get("seller_id")
    
    if seller_id == uid:
        return await cb.answer("❌ Это твоя карта!", show_alert=True)
    
    user = db.get_user(uid)
    if not user or user.get("coins", 0) < price:
        return await cb.answer(f"❌ Нужно {format_num(price)} 🪙!", show_alert=True)
    
    # Покупка
    fee = int(price * MARKET_FEE / 100)
    db.remove_coins(uid, price)
    db.add_coins(seller_id, price - fee)
    db.add_card(uid, {
        "name": card["name"],
        "rarity": card["rarity"],
        "attack": card["attack"],
        "defense": card["defense"],
        "emoji": card["emoji"]
    })
    db.remove_listing(lid)
    
    rc = RARITY_COLORS.get(card["rarity"], "⚪")
    rn = RARITY_NAMES.get(card["rarity"], card["rarity"])
    power = card["attack"] + card["defense"]
    
    text = (
        f"✅ <b>КУПЛЕНО!</b>\n\n"
        f"{rc} {card['emoji']} <b>{card['name']}</b>\n"
        f"📊 {rn} | 💪 {power}\n"
        f"💰 -{format_num(price)} монет\n\n"
        f"💰 Баланс: <b>{db.get_coins(uid):,}</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Ещё карты", callback_data="sh:market:0")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="sh:back")],
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer("✅ Карта куплена!")


# ═══════════════════════════════════════════════════════════════
#                         ПРОДАЖА КАРТ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("sh:sell:"))
async def cb_sell_menu(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    cards = user.get("cards", [])
    if not cards:
        return await cb.answer("❌ Нет карт!", show_alert=True)
    
    grouped = group_cards(cards)
    total_pages = max(1, (len(grouped) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = grouped[page * PER_PAGE:(page + 1) * PER_PAGE]
    
    text = (
        f"📤 <b>ПРОДАЖА КАРТ</b>\n\n"
        f"🃏 Карт: <b>{len(cards)}</b>\n"
        f"📉 Комиссия: <b>{MARKET_FEE}%</b>\n\n"
        f"<i>Выбери карту для продажи:</i>\n"
    )
    
    btns = []
    for item in page_items:
        c = item["card"]
        cnt = item["count"]
        rc = RARITY_COLORS.get(c["rarity"], "⚪")
        power = c["attack"] + c["defense"]
        base_price = get_base_price(c)
        
        # Предупреждение для редких
        warn = "⚠️" if c["rarity"] in ["mega_fused", "mega", "fused", "limited", "special"] else ""
        cnt_txt = f" x{cnt}" if cnt > 1 else ""
        
        btns.append([InlineKeyboardButton(
            text=f"{warn}{rc}{c['emoji']} {c['name'][:10]}{cnt_txt} ~{base_price}🪙",
            callback_data=f"sh:sellpick:{c['name'][:20]}"
        )])
    
    # Пагинация
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"sh:sell:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"sh:sell:{page+1}"))
        btns.append(nav)
    
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("sh:sellpick:"))
async def cb_sell_pick(cb: CallbackQuery, state: FSMContext):
    card_name = cb.data.split(":")[2]
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user or not any(c["name"] == card_name for c in user.get("cards", [])):
        return await cb.answer("❌ Карта не найдена!", show_alert=True)
    
    card = find_card(card_name)
    if not card:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    base_price = get_base_price(card)
    rc = RARITY_COLORS.get(card["rarity"], "⚪")
    rn = RARITY_NAMES.get(card["rarity"], card["rarity"])
    power = card["attack"] + card["defense"]
    
    # Варианты цен
    prices = [
        int(base_price * 0.5),
        base_price,
        int(base_price * 1.5),
        base_price * 2,
        base_price * 3
    ]
    prices = list(set(p for p in prices if 1 <= p <= 10000000))
    prices.sort()
    
    text = (
        f"📤 <b>ПРОДАЖА</b>\n\n"
        f"{rc} {card['emoji']} <b>{card['name']}</b>\n"
        f"📊 {rn} | 💪 {power}\n\n"
        f"💰 Рекомендуемая цена: <b>{base_price}</b> 🪙\n"
        f"📉 Комиссия: <b>{MARKET_FEE}%</b>\n\n"
        f"Выбери цену:"
    )
    
    btns = []
    row = []
    for p in prices[:6]:
        fee = int(p * MARKET_FEE / 100)
        net = p - fee
        row.append(InlineKeyboardButton(
            text=f"{format_num(p)}🪙 (={format_num(net)})",
            callback_data=f"sh:dosell:{card_name[:15]}:{p}"
        ))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    
    btns.append([InlineKeyboardButton(text="✏️ Своя цена", callback_data=f"sh:custprice:{card_name[:15]}")])
    btns.append([InlineKeyboardButton(text="❌ Отмена", callback_data="sh:sell:0")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("sh:dosell:"))
async def cb_do_sell(cb: CallbackQuery):
    parts = cb.data.split(":")
    card_name = parts[2]
    price = int(parts[3])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user or not any(c["name"] == card_name for c in user.get("cards", [])):
        return await cb.answer("❌ Карта не найдена!", show_alert=True)
    
    card = find_card(card_name)
    if not card:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    # Выставляем
    db.remove_card_from_user(uid, card_name)
    db.add_listing(uid, card_name, price)
    
    fee = int(price * MARKET_FEE / 100)
    net = price - fee
    rc = RARITY_COLORS.get(card["rarity"], "⚪")
    
    text = (
        f"✅ <b>ВЫСТАВЛЕНО!</b>\n\n"
        f"{rc} {card['emoji']} <b>{card['name']}</b>\n"
        f"💰 Цена: <b>{format_num(price)}</b> 🪙\n"
        f"📉 Комиссия: -{fee} 🪙\n"
        f"💵 Получишь: <b>{net}</b> 🪙"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Мои лоты", callback_data="sh:my:0")],
        [InlineKeyboardButton(text="📤 Ещё продать", callback_data="sh:sell:0")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="sh:back")],
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer("✅ Выставлено!")


@router.callback_query(F.data.startswith("sh:custprice:"))
async def cb_custom_price(cb: CallbackQuery, state: FSMContext):
    card_name = cb.data.split(":")[2]
    
    card = find_card(card_name)
    if not card:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    base_price = get_base_price(card)
    max_price = base_price * 50
    
    text = (
        f"✏️ <b>Введи цену</b>\n\n"
        f"📊 Рекомендуемая: <b>{base_price}</b> 🪙\n"
        f"📈 Максимум: <b>{format_num(max_price)}</b> 🪙\n\n"
        f"Напиши число:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="sh:sell:0")]
    ])
    
    await state.set_state(SellStates.waiting_price)
    await state.update_data(mode="sell_card", card_name=card_name, owner_id=cb.from_user.id, max_price=max_price)
    
    await safe_edit(cb, text, kb)
    await cb.answer()


# ═══════════════════════════════════════════════════════════════
#                      БЫСТРАЯ ПРОДАЖА
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("sh:quick:"))
async def cb_quick_menu(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    cards = user.get("cards", [])
    if not cards:
        return await cb.answer("❌ Нет карт!", show_alert=True)
    
    grouped = group_cards(cards)
    total_pages = max(1, (len(grouped) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = grouped[page * PER_PAGE:(page + 1) * PER_PAGE]
    
    text = (
        f"⚡ <b>БЫСТРАЯ ПРОДАЖА</b>\n\n"
        f"💰 Монеты: <b>{user.get('coins', 0):,}</b>\n"
        f"📉 Цена: <b>{QUICK_SELL_PERCENT}%</b> от базовой\n\n"
        f"<i>Мгновенная продажа боту:</i>\n"
    )
    
    btns = []
    for item in page_items:
        c = item["card"]
        cnt = item["count"]
        rc = RARITY_COLORS.get(c["rarity"], "⚪")
        qprice = get_quick_price(c)
        
        warn = "⚠️" if c["rarity"] in ["mega_fused", "mega", "fused", "limited", "special"] else ""
        cnt_txt = f" x{cnt}" if cnt > 1 else ""
        total = qprice * cnt
        
        btns.append([InlineKeyboardButton(
            text=f"{warn}{rc}{c['emoji']} {c['name'][:10]}{cnt_txt} = {qprice}🪙" + (f" (всего {total})" if cnt > 1 else ""),
            callback_data=f"sh:qsell:{c['name'][:20]}"
        )])
    
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"sh:quick:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"sh:quick:{page+1}"))
        btns.append(nav)
    
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("sh:qsell:"))
async def cb_quick_sell(cb: CallbackQuery):
    card_name = cb.data.split(":")[2]
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user or not any(c["name"] == card_name for c in user.get("cards", [])):
        return await cb.answer("❌ Карта не найдена!", show_alert=True)
    
    card = find_card(card_name)
    if not card:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    # Подтверждение для редких
    if card["rarity"] in ["mega_fused", "mega", "fused", "limited", "special", "mythic"]:
        qprice = get_quick_price(card)
        rc = RARITY_COLORS.get(card["rarity"], "⚪")
        rn = RARITY_NAMES.get(card["rarity"], card["rarity"])
        
        text = (
            f"⚠️ <b>ПОДТВЕРЖДЕНИЕ</b>\n\n"
            f"{rc} {card['emoji']} <b>{card['name']}</b>\n"
            f"📊 {rn}\n"
            f"💰 Получишь: <b>{qprice}</b> 🪙\n\n"
            f"<b>Это редкая карта! Уверен?</b>"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"sh:qconfirm:{card_name[:20]}"),
                InlineKeyboardButton(text="❌ Нет", callback_data="sh:quick:0"),
            ]
        ])
        
        await safe_edit(cb, text, kb)
        return await cb.answer()
    
    # Обычная продажа
    qprice = get_quick_price(card)
    db.remove_card_from_user(uid, card_name)
    db.add_coins(uid, qprice)
    
    await cb.answer(f"✅ {card['emoji']} {card['name'][:10]} → +{qprice} 🪙", show_alert=True)
    
    # Обновляем меню
    cb.data = "sh:quick:0"
    await cb_quick_menu(cb)


@router.callback_query(F.data.startswith("sh:qconfirm:"))
async def cb_quick_confirm(cb: CallbackQuery):
    card_name = cb.data.split(":")[2]
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user or not any(c["name"] == card_name for c in user.get("cards", [])):
        return await cb.answer("❌ Карта не найдена!", show_alert=True)
    
    card = find_card(card_name)
    if not card:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    qprice = get_quick_price(card)
    db.remove_card_from_user(uid, card_name)
    db.add_coins(uid, qprice)
    
    rc = RARITY_COLORS.get(card["rarity"], "⚪")
    await cb.answer(f"✅ {rc} {card['name'][:10]} → +{qprice} 🪙", show_alert=True)
    
    cb.data = "sh:quick:0"
    await cb_quick_menu(cb)


# ═══════════════════════════════════════════════════════════════
#                       МОИ ЛОТЫ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("sh:my:"))
async def cb_my_listings(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    listings = db.get_my_listings(uid) or []
    
    if not listings:
        text = (
            f"📝 <b>МОИ ЛОТЫ</b>\n\n"
            f"📭 Пусто!\n\n"
            f"<i>Выстави карты на продажу</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Продать карту", callback_data="sh:sell:0")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")],
        ])
        await safe_edit(cb, text, kb)
        return await cb.answer()
    
    total_pages = max(1, (len(listings) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = listings[page * PER_PAGE:(page + 1) * PER_PAGE]
    
    text = (
        f"📝 <b>МОИ ЛОТЫ</b>\n\n"
        f"📦 Активных: <b>{len(listings)}</b>\n\n"
        f"<i>Нажми чтобы снять с продажи:</i>\n"
    )
    
    btns = []
    for l in page_items:
        card = find_card(l.get("card_name", ""))
        if not card:
            continue
        
        lid = l.get("id")
        price = l.get("price", 0)
        rc = RARITY_COLORS.get(card["rarity"], "⚪")
        
        btns.append([InlineKeyboardButton(
            text=f"❌ {rc}{card['emoji']} {card['name'][:12]} = {format_num(price)}🪙",
            callback_data=f"sh:cancel:{lid}"
        )])
    
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"sh:my:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"sh:my:{page+1}"))
        btns.append(nav)
    
    btns.append([
        InlineKeyboardButton(text="📤 Ещё", callback_data="sh:sell:0"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back"),
    ])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("sh:cancel:"))
async def cb_cancel_listing(cb: CallbackQuery):
    lid = cb.data.split(":")[2]
    
    db = get_db(cb)
    uid = cb.from_user.id
    
    listing = db.get_listing_by_id(lid)
    if not listing:
        return await cb.answer("❌ Не найдено!", show_alert=True)
    
    if listing.get("seller_id") != uid:
        return await cb.answer("❌ Не твоё!", show_alert=True)
    
    card = find_card(listing.get("card_name", ""))
    if not card:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    # Возвращаем карту
    db.add_card(uid, {
        "name": card["name"],
        "rarity": card["rarity"],
        "attack": card["attack"],
        "defense": card["defense"],
        "emoji": card["emoji"]
    })
    db.remove_listing(lid)
    
    await cb.answer(f"✅ {card['emoji']} {card['name'][:10]} возвращена!", show_alert=True)
    
    cb.data = "sh:my:0"
    await cb_my_listings(cb)


# ═══════════════════════════════════════════════════════════════
#                      ПРОДАЖА ДУБЛЕЙ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "sh:trash")
async def cb_trash_menu(cb: CallbackQuery):
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    cards = user.get("cards", [])
    if not cards:
        return await cb.answer("❌ Нет карт!", show_alert=True)
    
    # Группируем
    groups = {}
    for c in cards:
        n = c["name"]
        if n not in groups:
            groups[n] = {"card": c, "count": 0}
        groups[n]["count"] += 1
    
    # Считаем дубли по категориям
    categories = {
        "common": {"name": "⚪ Коммонки", "rars": ["common"], "dupes": 0, "coins": 0},
        "rare": {"name": "🔵 Рарки", "rars": ["rare"], "dupes": 0, "coins": 0},
        "epic": {"name": "🟣 Эпики", "rars": ["epic"], "dupes": 0, "coins": 0},
        "low": {"name": "🗑 Common+Rare", "rars": ["common", "rare"], "dupes": 0, "coins": 0},
        "all": {"name": "🧹 ВСЕ дубли", "rars": None, "dupes": 0, "coins": 0},
    }
    
    for name, g in groups.items():
        dupes = g["count"] - 1
        if dupes <= 0:
            continue
        
        qp = get_quick_price(g["card"]) * dupes
        r = g["card"]["rarity"]
        
        categories["all"]["dupes"] += dupes
        categories["all"]["coins"] += qp
        
        for cat_id, cat in categories.items():
            if cat_id == "all":
                continue
            if cat["rars"] and r in cat["rars"]:
                cat["dupes"] += dupes
                cat["coins"] += qp
    
    if categories["all"]["dupes"] == 0:
        text = (
            f"🗑 <b>ПРОДАЖА ДУБЛЕЙ</b>\n\n"
            f"✅ Нет дубликатов!\n\n"
            f"<i>По одной копии каждой карты останется</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")]
        ])
        await safe_edit(cb, text, kb)
        return await cb.answer()
    
    text = (
        f"🗑 <b>ПРОДАЖА ДУБЛЕЙ</b>\n\n"
        f"💰 Монеты: <b>{user.get('coins', 0):,}</b>\n"
        f"📉 Цена: <b>{QUICK_SELL_PERCENT}%</b> от базовой\n\n"
        f"⚠️ <i>По 1 копии каждой карты останется!</i>\n"
    )
    
    btns = []
    for cat_id, cat in categories.items():
        if cat["dupes"] > 0:
            btns.append([InlineKeyboardButton(
                text=f"{cat['name']} ({cat['dupes']}) = {format_num(cat['coins'])}🪙",
                callback_data=f"sh:trashdo:{cat_id}"
            )])
    
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("sh:trashdo:"))
async def cb_trash_do(cb: CallbackQuery):
    cat_id = cb.data.split(":")[2]
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    cards = user.get("cards", [])
    
    categories = {
        "common": ["common"],
        "rare": ["rare"],
        "epic": ["epic"],
        "low": ["common", "rare"],
        "all": None,
    }
    
    target_rars = categories.get(cat_id)
    
    # Группируем
    groups = {}
    for c in cards:
        n = c["name"]
        if n not in groups:
            groups[n] = {"card": c, "count": 0}
        groups[n]["count"] += 1
    
    # Продаём
    total_sold = 0
    total_coins = 0
    
    for name, g in groups.items():
        if target_rars and g["card"]["rarity"] not in target_rars:
            continue
        
        dupes = g["count"] - 1
        if dupes > 0:
            qp = get_quick_price(g["card"])
            for _ in range(dupes):
                db.remove_card_from_user(uid, name)
            total_sold += dupes
            total_coins += qp * dupes
    
    if total_sold == 0:
        return await cb.answer("❌ Нечего продавать!", show_alert=True)
    
    db.add_coins(uid, total_coins)
    
    text = (
        f"✅ <b>ПРОДАНО!</b>\n\n"
        f"🗑 Карт: <b>{total_sold}</b>\n"
        f"💰 +<b>{format_num(total_coins)}</b> монет\n\n"
        f"💰 Баланс: <b>{db.get_coins(uid):,}</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Ещё", callback_data="sh:trash")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="sh:back")],
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer(f"✅ {total_sold} карт = +{format_num(total_coins)} 🪙")


# ═══════════════════════════════════════════════════════════════
#                    ОБРАБОТКА ВВОДА ТЕКСТА
# ═══════════════════════════════════════════════════════════════

@router.message(StateFilter(SellStates.waiting_price))
async def handle_price_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    
    if msg.from_user.id != data.get("owner_id"):
        return
    
    mode = data.get("mode")
    
    try:
        amount = int(msg.text.replace(" ", "").replace(",", ""))
        if amount <= 0:
            raise ValueError
    except:
        return await msg.reply("❌ Введи положительное число!")
    
    db = DatabaseManager.get_db(msg.chat.id)
    uid = msg.from_user.id
    user = db.get_user(uid)
    
    if mode == "buy_tickets":
        coins = user.get("coins", 0) if user else 0
        max_tickets = get_max_tickets_for_coins(coins)
        
        if amount > max_tickets:
            return await msg.reply(f"❌ Максимум {max_tickets} билетов за твои монеты!")
        
        price = get_ticket_price(amount)
        
        if coins < price:
            return await msg.reply(f"❌ Нужно {format_num(price)} 🪙!")
        
        db.remove_coins(uid, price)
        db.add_tickets(uid, amount)
        
        await state.clear()
        
        avg = price / amount
        await msg.reply(
            f"✅ <b>КУПЛЕНО!</b>\n\n"
            f"🎫 +{amount} билетов\n"
            f"💰 -{format_num(price)} монет\n"
            f"📊 Средняя: {avg:.1f} 🪙/шт\n\n"
            f"💰 Баланс: <b>{db.get_coins(uid):,}</b>\n"
            f"🎫 Билетов: <b>{db.get_spin_tickets(uid)}</b>",
            parse_mode="HTML"
        )
    
    elif mode == "sell_card":
        card_name = data.get("card_name")
        max_price = data.get("max_price", 10000000)
        
        if amount > max_price:
            return await msg.reply(f"❌ Максимум {format_num(max_price)} 🪙!")
        
        if not any(c["name"] == card_name for c in user.get("cards", [])):
            await state.clear()
            return await msg.reply("❌ Карта не найдена!")
        
        card = find_card(card_name)
        if not card:
            await state.clear()
            return await msg.reply("❌ Ошибка!")
        
        db.remove_card_from_user(uid, card_name)
        db.add_listing(uid, card_name, amount)
        
        await state.clear()
        
        fee = int(amount * MARKET_FEE / 100)
        net = amount - fee
        rc = RARITY_COLORS.get(card["rarity"], "⚪")
        
        await msg.reply(
            f"✅ <b>ВЫСТАВЛЕНО!</b>\n\n"
            f"{rc} {card['emoji']} <b>{card['name']}</b>\n"
            f"💰 Цена: <b>{format_num(amount)}</b> 🪙\n"
            f"💵 Получишь: <b>{net}</b> 🪙",
            parse_mode="HTML"
        )


# ═══════════════════════════════════════════════════════════════
#                    СОВМЕСТИМОСТЬ
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "market_back")
async def old_market_back(cb: CallbackQuery, state: FSMContext = None):
    await cb_back(cb, state)


@router.callback_query(F.data == "m:back")
async def old_m_back(cb: CallbackQuery, state: FSMContext = None):
    await cb_back(cb, state)