# handlers/market.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
import asyncio

from config import EMOJI, CARDS, RARITY_COLORS, RARITY_NAMES
from database import DatabaseManager

router = Router()

PER_PAGE = 8


class SellStates(StatesGroup):
    waiting_price = State()


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
        except Exception:
            pass
    except Exception:
        pass


def find_card(name):
    for c in CARDS:
        if c["name"] == name:
            return c
    return None


RARITY_ORDER = {
    "mega": 1, "special": 4, "mythic": 5, "legendary": 6, "epic": 7, "rare": 8, "common": 9
}

MARKET_FEE = 10
QUICK_SELL_PERCENT = 5


def get_base_price(card):
    power = card["attack"] + card["defense"]
    mult = {
        "common": 2, "rare": 4, "epic": 8, "legendary": 15, "mythic": 25,
        "special": 50, "mega": 60
    }
    return max(1, power * mult.get(card["rarity"], 2))


def get_quick_price(card):
    return max(1, int(get_base_price(card) * QUICK_SELL_PERCENT / 100))


def group_cards(cards):
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
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def get_ticket_price(amount: int) -> int:
    if amount <= 0:
        return 0
    total = 0
    remaining = amount
    tier1 = min(remaining, 10)
    total += tier1 * 50
    remaining -= tier1
    if remaining > 0:
        tier2 = min(remaining, 40)
        total += tier2 * 55
        remaining -= tier2
    if remaining > 0:
        tier3 = min(remaining, 50)
        total += tier3 * 60
        remaining -= tier3
    if remaining > 0:
        tier4 = min(remaining, 400)
        total += tier4 * 70
        remaining -= tier4
    if remaining > 0:
        total += remaining * 80
    return total


def get_max_tickets_for_coins(coins: int) -> int:
    if coins <= 0:
        return 0
    low, high = 0, coins // 50 + 1
    while low < high:
        mid = (low + high + 1) // 2
        if get_ticket_price(mid) <= coins:
            low = mid
        else:
            high = mid - 1
    return low


def get_shield_price(amount: int) -> int:
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


def build_main_menu(db, uid):
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    tickets = user.get("spin_tickets", 0) if user else 0
    shields = user.get("shields", 0) if user else 0
    cards_count = len(user.get("cards", [])) if user else 0

    listings = db.get_all_listings() or []
    other_listings = len([l for l in listings if l.get("seller_id") != uid])
    my_listings = len(db.get_my_listings(uid) or [])

    text = (
        f"🏪 <b>МАГАЗИН</b>\n\n"
        f"💰 Монеты: <b>{coins:,}</b>\n"
        f"🎫 Билеты: <b>{tickets}</b>\n"
        f"🛡 Щиты: <b>{shields}</b>\n"
        f"🃏 Карты: <b>{cards_count}</b>\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎫 Билеты", callback_data="sh:tickets"),
            InlineKeyboardButton(text="🛡 Щиты", callback_data="sh:shields"),
        ],
        [InlineKeyboardButton(
            text=f"🃏 Карты игроков" + (f" ({other_listings})" if other_listings else ""),
            callback_data="sh:market:0"
        )],
        [
            InlineKeyboardButton(text="📤 Продать", callback_data="sh:sell:0"),
            InlineKeyboardButton(text="⚡ Быстро", callback_data="sh:quick:0"),
        ],
        [
            InlineKeyboardButton(
                text=f"📝 Мои лоты" + (f" ({my_listings})" if my_listings else ""),
                callback_data="sh:my:0"
            ),
            InlineKeyboardButton(text="🗑 Дубли", callback_data="sh:trash"),
        ],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="sh:close")],
    ])

    return text, kb


@router.message(Command("market", "shop"))
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
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


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
        f"<b>📊 Цены:</b>\n"
        f"• 1-10 шт: <b>50</b> 🪙/шт\n"
        f"• 11-50 шт: <b>55</b> 🪙/шт\n"
        f"• 51-100 шт: <b>60</b> 🪙/шт\n\n"
        f"💡 Максимум: <b>{max_tickets}</b> шт"
    )

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

    if max_tickets > 0:
        all_price = get_ticket_price(max_tickets)
        btns.append([InlineKeyboardButton(
            text=f"🔥 ВСЁ: {max_tickets}🎫 = {format_num(all_price)}🪙",
            callback_data=f"sh:buyt:{max_tickets}"
        )])

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

    text = (
        f"✅ <b>КУПЛЕНО!</b>\n\n"
        f"🎫 +{amount} билетов\n"
        f"💰 -{format_num(price)} монет\n\n"
        f"💰 Баланс: <b>{new_coins:,}</b>\n"
        f"🎫 Билетов: <b>{new_tickets}</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 Ещё билеты", callback_data="sh:tickets")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="sh:back")],
    ])

    await safe_edit(cb, text, kb)
    await cb.answer(f"✅ +{amount} 🎫")


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
        f"<b>📊 Цены:</b>\n"
        f"• 1-5 шт: <b>150</b> 🪙/шт\n"
        f"• 6-20 шт: <b>170</b> 🪙/шт\n\n"
        f"💡 Максимум: <b>{max_shields}</b> шт"
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
        text = f"🃏 <b>КАРТЫ ИГРОКОВ</b>\n\n📭 Пока пусто!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Продать карту", callback_data="sh:sell:0")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")],
        ])
        await safe_edit(cb, text, kb)
        return await cb.answer()

    listings.sort(key=lambda x: x.get("price", 0))

    total_pages = max(1, (len(listings) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = listings[page * PER_PAGE:(page + 1) * PER_PAGE]

    text = f"🃏 <b>КАРТЫ ИГРОКОВ</b>\n\n💰 Твои монеты: <b>{coins:,}</b>\n📦 Лотов: <b>{len(listings)}</b>\n\n"

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

    text = f"📤 <b>ПРОДАЖА КАРТ</b>\n\n🃏 Карт: <b>{len(cards)}</b>\n📉 Комиссия: <b>{MARKET_FEE}%</b>\n\n"

    btns = []
    for item in page_items:
        c = item["card"]
        cnt = item["count"]
        rc = RARITY_COLORS.get(c["rarity"], "⚪")
        base_price = get_base_price(c)
        cnt_txt = f" x{cnt}" if cnt > 1 else ""

        btns.append([InlineKeyboardButton(
            text=f"{rc}{c['emoji']} {c['name'][:10]}{cnt_txt} ~{base_price}🪙",
            callback_data=f"sh:sellpick:{c['name'][:20]}"
        )])

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
async def cb_sell_pick(cb: CallbackQuery):
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

    prices = [int(base_price * 0.5), base_price, int(base_price * 1.5), base_price * 2]
    prices = list(set(p for p in prices if 1 <= p <= 10000000))
    prices.sort()

    text = (
        f"📤 <b>ПРОДАЖА</b>\n\n"
        f"{rc} {card['emoji']} <b>{card['name']}</b>\n"
        f"📊 {rn} | 💪 {power}\n\n"
        f"💰 Рекомендуемая цена: <b>{base_price}</b> 🪙\nВыбери цену:"
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

    db.remove_card_from_user(uid, card_name)
    db.add_listing(uid, card_name, price)

    fee = int(price * MARKET_FEE / 100)
    net = price - fee
    rc = RARITY_COLORS.get(card["rarity"], "⚪")

    text = (
        f"✅ <b>ВЫСТАВЛЕНО!</b>\n\n"
        f"{rc} {card['emoji']} <b>{card['name']}</b>\n"
        f"💰 Цена: <b>{format_num(price)}</b> 🪙\n"
        f"💵 Получишь: <b>{net}</b> 🪙"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Мои лоты", callback_data="sh:my:0")],
        [InlineKeyboardButton(text="📤 Ещё продать", callback_data="sh:sell:0")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="sh:back")],
    ])

    await safe_edit(cb, text, kb)
    await cb.answer("✅ Выставлено!")


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

    text = f"⚡ <b>БЫСТРАЯ ПРОДАЖА</b>\n\n📉 Цена: <b>{QUICK_SELL_PERCENT}%</b> от базовой\n\n"

    btns = []
    for item in page_items:
        c = item["card"]
        cnt = item["count"]
        rc = RARITY_COLORS.get(c["rarity"], "⚪")
        qprice = get_quick_price(c)
        cnt_txt = f" x{cnt}" if cnt > 1 else ""

        btns.append([InlineKeyboardButton(
            text=f"{rc}{c['emoji']} {c['name'][:10]}{cnt_txt} = {qprice}🪙",
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

    qprice = get_quick_price(card)
    db.remove_card_from_user(uid, card_name)
    db.add_coins(uid, qprice)

    await cb.answer(f"✅ {card['emoji']} {card['name'][:10]} → +{qprice} 🪙", show_alert=True)

    cb.data = "sh:quick:0"
    await cb_quick_menu(cb)


@router.callback_query(F.data.startswith("sh:my:"))
async def cb_my_listings(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])

    db = get_db(cb)
    uid = cb.from_user.id
    listings = db.get_my_listings(uid) or []

    if not listings:
        text = f"📝 <b>МОИ ЛОТЫ</b>\n\n📭 Пусто!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Продать карту", callback_data="sh:sell:0")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")],
        ])
        await safe_edit(cb, text, kb)
        return await cb.answer()

    total_pages = max(1, (len(listings) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = listings[page * PER_PAGE:(page + 1) * PER_PAGE]

    text = f"📝 <b>МОИ ЛОТЫ</b>\n\n📦 Активных: <b>{len(listings)}</b>\n\n"

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

    groups = {}
    for c in cards:
        n = c["name"]
        if n not in groups:
            groups[n] = {"card": c, "count": 0}
        groups[n]["count"] += 1

    categories = {
        "common": {"name": "⚪ Коммонки", "rars": ["common"], "dupes": 0, "coins": 0},
        "rare": {"name": "🔵 Рарки", "rars": ["rare"], "dupes": 0, "coins": 0},
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
        text = f"🗑 <b>ПРОДАЖА ДУБЛЕЙ</b>\n\n✅ Нет дубликатов!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="sh:back")]
        ])
        await safe_edit(cb, text, kb)
        return await cb.answer()

    text = f"🗑 <b>ПРОДАЖА ДУБЛЕЙ</b>\n\n⚠️ <i>По 1 копии останется!</i>\n"

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
        "all": None,
    }

    target_rars = categories.get(cat_id)

    groups = {}
    for c in cards:
        n = c["name"]
        if n not in groups:
            groups[n] = {"card": c, "count": 0}
        groups[n]["count"] += 1

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