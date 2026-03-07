# handlers/market.py
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
import asyncio

from config import EMOJI, CARDS, RARITY_COLORS, RARITY_NAMES, LIMITED_CARDS, FUSION_CARDS
from database import DatabaseManager

router = Router()

CARDS_PER_PAGE = 6  # Уменьшил для красоты


class SellCardStates(StatesGroup):
    waiting_for_price = State()


# ═══════════════════════════════════════════════
#  ХЕЛПЕРЫ
# ═══════════════════════════════════════════════

def is_group(msg: Message) -> bool:
    return msg.chat.type in ["group", "supergroup"]


def get_db(obj):
    if isinstance(obj, Message):
        return DatabaseManager.get_db(obj.chat.id)
    elif isinstance(obj, CallbackQuery):
        return DatabaseManager.get_db(obj.message.chat.id)
    return None


async def safe_edit(cb, text, kb=None):
    try:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            raise
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except:
            pass


def get_all_cards():
    return CARDS + LIMITED_CARDS + FUSION_CARDS


def find_card(name: str):
    for c in get_all_cards():
        if c["name"] == name:
            return c
    return None


RARITY_ORDER = {
    "mega_fused": 0, "mega": 1, "fused": 2, "limited": 3,
    "special": 4, "mythic": 5, "legendary": 6, "epic": 7, "rare": 8, "common": 9
}

MARKET_FEE = 10
QUICK_SELL_MULT = 0.05

SHOP_ITEMS = {
    "shield_1": {"name": "🛡️ Щит x1", "desc": "1 защита", "price": 150, "type": "shield", "val": 1, "emoji": "🛡️"},
    "shield_3": {"name": "🛡️ Щит x3", "desc": "3 защиты", "price": 300, "type": "shield", "val": 3, "emoji": "🛡️"},
    "shield_5": {"name": "🛡️ Щит x5", "desc": "5 защит", "price": 500, "type": "shield", "val": 5, "emoji": "🛡️"},
    "ticket_1": {"name": "🎫 Билет x1", "desc": "1 билет", "price": 50, "type": "ticket", "val": 1, "emoji": "🎫"},
    "ticket_5": {"name": "🎫 Билет x5", "desc": "5 билетов", "price": 220, "type": "ticket", "val": 5, "emoji": "🎫"},
    "ticket_10": {"name": "🎫 Билет x10", "desc": "10 билетов", "price": 400, "type": "ticket", "val": 10, "emoji": "🎫"},
    "ticket_25": {"name": "🎫 Билет x25", "desc": "Выгодно!", "price": 900, "type": "ticket", "val": 25, "emoji": "🎫"},
}


def get_base_price(card):
    power = card["attack"] + card["defense"]
    mult = {"common": 2, "rare": 4, "epic": 8, "legendary": 15, "mythic": 25,
            "special": 50, "mega": 60, "limited": 55, "fused": 80, "mega_fused": 120}
    return max(1, power * mult.get(card["rarity"], 2))


def get_quick_price(card):
    return max(1, int(get_base_price(card) * QUICK_SELL_MULT))


def group_cards(cards):
    groups = {}
    for c in cards:
        n = c["name"]
        if n not in groups:
            groups[n] = {"card": c, "count": 0}
        groups[n]["count"] += 1
    return sorted(groups.values(), key=lambda x: (RARITY_ORDER.get(x["card"]["rarity"], 99), -(x["card"]["attack"] + x["card"]["defense"])))


def make_pagination(page, total, prefix):
    if total <= 1:
        return []
    btns = []
    if page > 0:
        btns.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page-1}"))
    btns.append(InlineKeyboardButton(text=f"• {page+1}/{total} •", callback_data="noop"))
    if page < total - 1:
        btns.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page+1}"))
    return [btns]


# ═══════════════════════════════════════════════
#  ГЛАВНОЕ МЕНЮ МАГАЗИНА
# ═══════════════════════════════════════════════

def make_market_menu(db, uid):
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    mults = user.get("mults", 0) if user else 0
    cards_count = len(user.get("cards", [])) if user else 0
    
    listings = db.get_all_listings() or []
    other_listings = len([l for l in listings if l.get("seller_id") != uid])
    my_listings = len(db.get_my_listings(uid) or [])
    
    text = (
        f"╔══════════════════════╗\n"
        f"║     🏪 <b>МАГАЗИН</b>     ║\n"
        f"╠══════════════════════╣\n"
        f"║ 💰 <b>{coins:,}</b> монет\n"
        f"║ 💎 <b>{mults}</b> Mults\n"
        f"║ 🃏 <b>{cards_count}</b> карт\n"
        f"╚══════════════════════╝\n"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        # Рынок карт
        [InlineKeyboardButton(
            text=f"🃏 Карты игроков ({other_listings})" if other_listings else "🃏 Карты игроков",
            callback_data="m:cards"
        )],
        # Магазин предметов
        [
            InlineKeyboardButton(text="🛡️ Щиты", callback_data="m:shop:shields"),
            InlineKeyboardButton(text="🎫 Билеты", callback_data="m:shop:tickets"),
        ],
        # Продажа
        [
            InlineKeyboardButton(text="📤 Продать", callback_data="m:sell:0"),
            InlineKeyboardButton(text="⚡ Быстро", callback_data="m:qsell:0"),
        ],
        # Мои объявления и мусор
        [
            InlineKeyboardButton(
                text=f"📝 Мои ({my_listings})" if my_listings else "📝 Мои",
                callback_data="m:my:0"
            ),
            InlineKeyboardButton(text="🗑️ Мусор", callback_data="m:trash"),
        ],
        # Mults
        [InlineKeyboardButton(text="💎 Mults Shop", callback_data="mults_main")],
        # Закрыть
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="m:close")],
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
    
    text, kb = make_market_menu(db, uid)
    await msg.reply(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "m:back")
async def market_back(cb: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    db = get_db(cb)
    text, kb = make_market_menu(db, cb.from_user.id)
    await safe_edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data == "m:close")
async def market_close(cb: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    try:
        await cb.message.delete()
    except:
        pass
    await cb.answer()


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


# ═══════════════════════════════════════════════
#  МАГАЗИН ПРЕДМЕТОВ
# ═══════════════════════════════════════════════

@router.callback_query(F.data.startswith("m:shop:"))
async def shop_category(cb: CallbackQuery):
    cat = cb.data.split(":")[2]
    db = get_db(cb)
    user = db.get_user(cb.from_user.id)
    coins = user.get("coins", 0) if user else 0
    
    if cat == "shields":
        items = ["shield_1", "shield_3", "shield_5"]
        title = "🛡️ ЩИТЫ"
        desc = "Защита от поражений на арене"
    else:
        items = ["ticket_1", "ticket_5", "ticket_10", "ticket_25"]
        title = "🎫 БИЛЕТЫ"
        desc = "Для прокрутки карт"
    
    text = (
        f"╔══════════════════════╗\n"
        f"║     {title}     ║\n"
        f"╠══════════════════════╣\n"
        f"║ 💰 <b>{coins:,}</b> монет\n"
        f"╚══════════════════════╝\n\n"
        f"<i>{desc}</i>\n"
    )
    
    btns = []
    for iid in items:
        item = SHOP_ITEMS[iid]
        can_buy = coins >= item["price"]
        status = "✅" if can_buy else "❌"
        btns.append([InlineKeyboardButton(
            text=f"{status} {item['name']} — {item['price']} 🪙",
            callback_data=f"m:buy:{iid}"
        )])
    
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="m:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("m:buy:"))
async def shop_buy(cb: CallbackQuery):
    iid = cb.data.split(":")[2]
    item = SHOP_ITEMS.get(iid)
    if not item:
        return await cb.answer("❌ Не найдено!", show_alert=True)
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user or user.get("coins", 0) < item["price"]:
        return await cb.answer(f"❌ Нужно {item['price']} 🪙!", show_alert=True)
    
    db.remove_coins(uid, item["price"])
    
    if item["type"] == "ticket":
        db.add_tickets(uid, item["val"])
        result = f"🎫 +{item['val']} билетов"
    else:
        db.add_shields(uid, item["val"])
        result = f"🛡️ +{item['val']} щитов"
    
    text = (
        f"╔══════════════════════╗\n"
        f"║    ✅ <b>КУПЛЕНО!</b>    ║\n"
        f"╠══════════════════════╣\n"
        f"║ {item['emoji']} {item['name']}\n"
        f"║ 💰 -{item['price']} 🪙\n"
        f"║ {result}\n"
        f"╚══════════════════════╝"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё", callback_data=f"m:shop:{'shields' if item['type'] == 'shield' else 'tickets'}")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="m:back")],
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer(result, show_alert=True)


# ═══════════════════════════════════════════════
#  РЫНОК КАРТ ИГРОКОВ
# ═══════════════════════════════════════════════

@router.callback_query(F.data == "m:cards")
async def market_cards(cb: CallbackQuery):
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    
    listings = db.get_all_listings() or []
    listings = [l for l in listings if l.get("seller_id") != uid]
    
    if not listings:
        text = (
            f"╔══════════════════════╗\n"
            f"║   🃏 <b>КАРТЫ ИГРОКОВ</b>   ║\n"
            f"╠══════════════════════╣\n"
            f"║    📭 Пока пусто!    ║\n"
            f"╚══════════════════════╝\n\n"
            f"<i>Выстави свои карты!</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Продать карту", callback_data="m:sell:0")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="m:back")],
        ])
        await safe_edit(cb, text, kb)
        return await cb.answer()
    
    # Группируем по редкости
    all_cards = get_all_cards()
    by_rarity = {}
    for l in listings:
        card = find_card(l.get("card_name", ""))
        if card:
            r = card["rarity"]
            by_rarity[r] = by_rarity.get(r, 0) + 1
    
    text = (
        f"╔══════════════════════╗\n"
        f"║   🃏 <b>КАРТЫ ИГРОКОВ</b>   ║\n"
        f"╠══════════════════════╣\n"
        f"║ 💰 <b>{coins:,}</b> монет\n"
        f"║ 📦 <b>{len(listings)}</b> лотов\n"
        f"╚══════════════════════╝\n\n"
        f"<i>Выбери редкость:</i>"
    )
    
    btns = []
    for r in ["mega_fused", "mega", "fused", "limited", "special", "mythic", "legendary", "epic", "rare", "common"]:
        if r in by_rarity:
            rc = RARITY_COLORS.get(r, "⚪")
            rn = RARITY_NAMES.get(r, r)
            btns.append([InlineKeyboardButton(
                text=f"{rc} {rn} ({by_rarity[r]})",
                callback_data=f"m:list:{r}:0"
            )])
    
    btns.append([InlineKeyboardButton(text="📋 Все карты", callback_data="m:list:all:0")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="m:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("m:list:"))
async def market_list(cb: CallbackQuery):
    parts = cb.data.split(":")
    rarity = parts[2]
    page = int(parts[3])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    coins = user.get("coins", 0) if user else 0
    
    listings = db.get_all_listings() or []
    listings = [l for l in listings if l.get("seller_id") != uid]
    
    if rarity != "all":
        filtered = []
        for l in listings:
            card = find_card(l.get("card_name", ""))
            if card and card["rarity"] == rarity:
                filtered.append(l)
        listings = filtered
        title = RARITY_NAMES.get(rarity, rarity)
    else:
        title = "Все карты"
    
    if not listings:
        return await cb.answer("❌ Нет карт!", show_alert=True)
    
    listings.sort(key=lambda x: x.get("price", 0))
    
    total_pages = max(1, (len(listings) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = listings[page * CARDS_PER_PAGE:(page + 1) * CARDS_PER_PAGE]
    
    text = (
        f"╔══════════════════════╗\n"
        f"║  🃏 <b>{title}</b>  ║\n"
        f"╠══════════════════════╣\n"
        f"║ 💰 <b>{coins:,}</b> монет\n"
        f"║ 📦 <b>{len(listings)}</b> лотов\n"
        f"╚══════════════════════╝\n"
    )
    
    btns = []
    for l in page_items:
        card = find_card(l.get("card_name", ""))
        if not card:
            continue
        
        price = l.get("price", 0)
        lid = l.get("id", 0)
        rc = RARITY_COLORS.get(card["rarity"], "⚪")
        can_buy = "✅" if coins >= price else "❌"
        power = card["attack"] + card["defense"]
        
        btns.append([InlineKeyboardButton(
            text=f"{can_buy} {rc}{card['emoji']} {card['name'][:12]} 💪{power} — {price}🪙",
            callback_data=f"m:buycard:{lid}:{rarity}:{page}"
        )])
    
    btns.extend(make_pagination(page, total_pages, f"m:list:{rarity}"))
    btns.append([
        InlineKeyboardButton(text="🔄", callback_data=f"m:list:{rarity}:{page}"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="m:cards"),
    ])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("m:buycard:"))
async def market_buy_card(cb: CallbackQuery):
    parts = cb.data.split(":")
    lid = int(parts[2])
    rarity = parts[3]
    page = int(parts[4])
    
    db = get_db(cb)
    uid = cb.from_user.id
    
    listing = db.get_listing_by_id(lid)
    if not listing:
        return await cb.answer("❌ Уже продано!", show_alert=True)
    
    card = find_card(listing.get("card_name", ""))
    if not card:
        return await cb.answer("❌ Карта не найдена!", show_alert=True)
    
    price = listing.get("price", 0)
    seller_id = listing.get("seller_id")
    
    if seller_id == uid:
        return await cb.answer("❌ Это твоя карта!", show_alert=True)
    
    user = db.get_user(uid)
    if not user or user.get("coins", 0) < price:
        return await cb.answer(f"❌ Нужно {price} 🪙!", show_alert=True)
    
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
    seller = db.get_user(seller_id)
    seller_name = seller.get("first_name", "Игрок") if seller else "Игрок"
    
    text = (
        f"╔══════════════════════╗\n"
        f"║    ✅ <b>КУПЛЕНО!</b>    ║\n"
        f"╠══════════════════════╣\n"
        f"║ {rc} {card['emoji']} <b>{card['name']}</b>\n"
        f"║ 💪 {card['attack'] + card['defense']}\n"
        f"║ 💰 -{price} 🪙\n"
        f"║ 👤 Продавец: {seller_name}\n"
        f"╚══════════════════════╝"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Ещё карты", callback_data=f"m:list:{rarity}:{page}")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="m:back")],
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer("✅ Карта куплена!", show_alert=True)


# ═══════════════════════════════════════════════
#  ПРОДАЖА КАРТ
# ═══════════════════════════════════════════════

@router.callback_query(F.data.startswith("m:sell:"))
async def sell_menu(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Нет данных!", show_alert=True)
    
    cards = user.get("cards", [])
    if not cards:
        return await cb.answer("❌ Нет карт!", show_alert=True)
    
    grouped = group_cards(cards)
    total_pages = max(1, (len(grouped) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = grouped[page * CARDS_PER_PAGE:(page + 1) * CARDS_PER_PAGE]
    
    text = (
        f"╔══════════════════════╗\n"
        f"║   📤 <b>ПРОДАЖА</b>   ║\n"
        f"╠══════════════════════╣\n"
        f"║ 🃏 Карт: <b>{len(cards)}</b>\n"
        f"║ 📊 Комиссия: <b>{MARKET_FEE}%</b>\n"
        f"╚══════════════════════╝\n\n"
        f"<i>Выбери карту:</i>"
    )
    
    btns = []
    for item in page_items:
        c = item["card"]
        cnt = item["count"]
        rc = RARITY_COLORS.get(c["rarity"], "⚪")
        power = c["attack"] + c["defense"]
        price = get_base_price(c)
        
        # Метки
        mark = ""
        if c["rarity"] in ["mega_fused", "mega", "fused", "limited"]:
            mark = "⚠️"
        
        cnt_txt = f" x{cnt}" if cnt > 1 else ""
        
        btns.append([InlineKeyboardButton(
            text=f"{mark}{rc}{c['emoji']} {c['name'][:10]}{cnt_txt} 💪{power} ~{price}🪙",
            callback_data=f"m:sellpick:{c['name'][:20]}:{page}"
        )])
    
    btns.extend(make_pagination(page, total_pages, "m:sell"))
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="m:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("m:sellpick:"))
async def sell_pick(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    card_name = parts[2]
    return_page = int(parts[3])
    
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
    
    await state.set_state(SellCardStates.waiting_for_price)
    await state.update_data(card_name=card_name, owner_id=uid, return_page=return_page)
    
    # Варианты цен
    prices = [base_price // 2, base_price, base_price * 2, base_price * 3]
    prices = [p for p in prices if 1 <= p <= 1000000]
    
    text = (
        f"╔══════════════════════╗\n"
        f"║   📤 <b>ПРОДАЖА</b>   ║\n"
        f"╠══════════════════════╣\n"
        f"║ {rc} {card['emoji']} <b>{card['name']}</b>\n"
        f"║ 📊 {rn}\n"
        f"║ 💪 {card['attack'] + card['defense']}\n"
        f"╠══════════════════════╣\n"
        f"║ 💰 Рекоменд: <b>{base_price}</b> 🪙\n"
        f"║ 📉 Комиссия: <b>{MARKET_FEE}%</b>\n"
        f"╚══════════════════════╝\n\n"
        f"<i>Выбери цену или напиши свою:</i>"
    )
    
    btns = []
    row = []
    for p in prices:
        row.append(InlineKeyboardButton(text=f"{p} 🪙", callback_data=f"m:setprice:{card_name[:15]}:{p}"))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    
    btns.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"m:sell:{return_page}")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("m:setprice:"))
async def sell_set_price(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    card_name = parts[2]
    price = int(parts[3])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user or not any(c["name"] == card_name for c in user.get("cards", [])):
        await state.clear()
        return await cb.answer("❌ Карта не найдена!", show_alert=True)
    
    card = find_card(card_name)
    if not card:
        await state.clear()
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    # Выставляем на продажу
    db.remove_card_from_user(uid, card_name)
    db.add_listing(uid, card_name, price)
    
    await state.clear()
    
    fee = int(price * MARKET_FEE / 100)
    net = price - fee
    rc = RARITY_COLORS.get(card["rarity"], "⚪")
    
    text = (
        f"╔══════════════════════╗\n"
        f"║  ✅ <b>ВЫСТАВЛЕНО!</b>  ║\n"
        f"╠══════════════════════╣\n"
        f"║ {rc} {card['emoji']} <b>{card['name']}</b>\n"
        f"║ 💰 Цена: <b>{price}</b> 🪙\n"
        f"║ 📉 Комиссия: -{fee} 🪙\n"
        f"║ 💵 Получишь: <b>{net}</b> 🪙\n"
        f"╚══════════════════════╝"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Мои объявления", callback_data="m:my:0")],
        [InlineKeyboardButton(text="📤 Ещё продать", callback_data="m:sell:0")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="m:back")],
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer("✅ Выставлено!", show_alert=True)


@router.message(StateFilter(SellCardStates.waiting_for_price))
async def sell_price_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    if msg.from_user.id != data.get("owner_id"):
        return
    
    try:
        price = int(msg.text)
        if not 1 <= price <= 1000000:
            raise ValueError
    except:
        return await msg.reply("❌ Введи число от 1 до 1,000,000")
    
    card_name = data.get("card_name")
    card = find_card(card_name)
    
    if not card:
        await state.clear()
        return await msg.reply("❌ Карта не найдена!")
    
    db = DatabaseManager.get_db(msg.chat.id)
    user = db.get_user(msg.from_user.id)
    
    if not user or not any(c["name"] == card_name for c in user.get("cards", [])):
        await state.clear()
        return await msg.reply("❌ Карта не найдена!")
    
    # Проверка макс цены
    base = get_base_price(card)
    if price > base * 50:
        return await msg.reply(f"❌ Максимум: {base * 50} 🪙")
    
    # Выставляем
    db.remove_card_from_user(msg.from_user.id, card_name)
    db.add_listing(msg.from_user.id, card_name, price)
    
    await state.clear()
    
    fee = int(price * MARKET_FEE / 100)
    rc = RARITY_COLORS.get(card["rarity"], "⚪")
    
    await msg.reply(
        f"✅ <b>ВЫСТАВЛЕНО!</b>\n\n"
        f"{rc} {card['emoji']} <b>{card['name']}</b>\n"
        f"💰 Цена: <b>{price}</b> 🪙\n"
        f"💵 Получишь: <b>{price - fee}</b> 🪙",
        parse_mode="HTML"
    )


# ═══════════════════════════════════════════════
#  БЫСТРАЯ ПРОДАЖА
# ═══════════════════════════════════════════════

@router.callback_query(F.data.startswith("m:qsell:"))
async def quick_sell_menu(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Нет данных!", show_alert=True)
    
    cards = user.get("cards", [])
    if not cards:
        return await cb.answer("❌ Нет карт!", show_alert=True)
    
    grouped = group_cards(cards)
    total_pages = max(1, (len(grouped) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = grouped[page * CARDS_PER_PAGE:(page + 1) * CARDS_PER_PAGE]
    
    text = (
        f"╔══════════════════════╗\n"
        f"║  ⚡ <b>БЫСТРАЯ ПРОДАЖА</b>  ║\n"
        f"╠══════════════════════╣\n"
        f"║ 💰 <b>{user.get('coins', 0):,}</b> монет\n"
        f"║ 📉 <b>5%</b> от цены\n"
        f"╚══════════════════════╝\n"
    )
    
    btns = []
    for item in page_items:
        c = item["card"]
        cnt = item["count"]
        rc = RARITY_COLORS.get(c["rarity"], "⚪")
        qprice = get_quick_price(c)
        
        mark = ""
        if c["rarity"] in ["mega_fused", "mega", "fused", "limited", "special"]:
            mark = "⚠️"
        
        cnt_txt = f" x{cnt}" if cnt > 1 else ""
        
        btns.append([InlineKeyboardButton(
            text=f"{mark}{rc}{c['emoji']} {c['name'][:12]}{cnt_txt} = {qprice}🪙",
            callback_data=f"m:qdo:{c['name'][:20]}:{page}"
        )])
    
    btns.extend(make_pagination(page, total_pages, "m:qsell"))
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="m:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("m:qdo:"))
async def quick_sell_do(cb: CallbackQuery):
    parts = cb.data.split(":")
    card_name = parts[2]
    return_page = int(parts[3])
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user or not any(c["name"] == card_name for c in user.get("cards", [])):
        return await cb.answer("❌ Карта не найдена!", show_alert=True)
    
    card = find_card(card_name)
    if not card:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    # Редкие — подтверждение
    if card["rarity"] in ["mega_fused", "mega", "fused", "limited", "special"]:
        qprice = get_quick_price(card)
        rc = RARITY_COLORS.get(card["rarity"], "⚪")
        
        text = (
            f"⚠️ <b>ПОДТВЕРЖДЕНИЕ</b>\n\n"
            f"{rc} {card['emoji']} <b>{card['name']}</b>\n"
            f"💰 Получишь: <b>{qprice}</b> 🪙\n\n"
            f"<b>Это редкая карта! Уверен?</b>"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, продать", callback_data=f"m:qconfirm:{card_name[:20]}:{return_page}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"m:qsell:{return_page}"),
            ]
        ])
        
        await safe_edit(cb, text, kb)
        return await cb.answer()
    
    # Обычная продажа
    qprice = get_quick_price(card)
    db.remove_card_from_user(uid, card_name)
    db.add_coins(uid, qprice)
    
    await cb.answer(f"✅ +{qprice} 🪙", show_alert=True)
    
    # Обновляем меню
    cb.data = f"m:qsell:{return_page}"
    await quick_sell_menu(cb)


@router.callback_query(F.data.startswith("m:qconfirm:"))
async def quick_sell_confirm(cb: CallbackQuery):
    parts = cb.data.split(":")
    card_name = parts[2]
    return_page = int(parts[3])
    
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
    await cb.answer(f"✅ {rc} {card['name']} → +{qprice} 🪙", show_alert=True)
    
    cb.data = f"m:qsell:{return_page}"
    await quick_sell_menu(cb)


# ═══════════════════════════════════════════════
#  МОИ ОБЪЯВЛЕНИЯ
# ═══════════════════════════════════════════════

@router.callback_query(F.data.startswith("m:my:"))
async def my_listings(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])
    
    db = get_db(cb)
    uid = cb.from_user.id
    listings = db.get_my_listings(uid) or []
    
    if not listings:
        text = (
            f"╔══════════════════════╗\n"
            f"║  📝 <b>МОИ ОБЪЯВЛЕНИЯ</b>  ║\n"
            f"╠══════════════════════╣\n"
            f"║     📭 Пусто!     ║\n"
            f"╚══════════════════════╝"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Продать карту", callback_data="m:sell:0")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="m:back")],
        ])
        await safe_edit(cb, text, kb)
        return await cb.answer()
    
    total_pages = max(1, (len(listings) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    page_items = listings[page * CARDS_PER_PAGE:(page + 1) * CARDS_PER_PAGE]
    
    text = (
        f"╔══════════════════════╗\n"
        f"║  📝 <b>МОИ ОБЪЯВЛЕНИЯ</b>  ║\n"
        f"╠══════════════════════╣\n"
        f"║ 📦 Лотов: <b>{len(listings)}</b>\n"
        f"╚══════════════════════╝\n"
    )
    
    btns = []
    for l in page_items:
        card = find_card(l.get("card_name", ""))
        if not card:
            continue
        
        lid = l.get("id", 0)
        price = l.get("price", 0)
        rc = RARITY_COLORS.get(card["rarity"], "⚪")
        
        btns.append([InlineKeyboardButton(
            text=f"❌ {rc}{card['emoji']} {card['name'][:12]} — {price}🪙",
            callback_data=f"m:cancel:{lid}:{page}"
        )])
    
    btns.extend(make_pagination(page, total_pages, "m:my"))
    btns.append([
        InlineKeyboardButton(text="📤 Ещё", callback_data="m:sell:0"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="m:back"),
    ])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("m:cancel:"))
async def cancel_listing(cb: CallbackQuery):
    parts = cb.data.split(":")
    lid = int(parts[2])
    return_page = int(parts[3])
    
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
    
    await cb.answer(f"✅ {card['emoji']} {card['name']} возвращена!", show_alert=True)
    
    cb.data = f"m:my:{return_page}"
    await my_listings(cb)


# ═══════════════════════════════════════════════
#  ПРОДАЖА МУСОРА
# ═══════════════════════════════════════════════

TRASH_CATS = {
    "common": {"name": "Коммонки", "emoji": "⚪", "rars": ["common"]},
    "rare": {"name": "Рарки", "emoji": "🔵", "rars": ["rare"]},
    "both": {"name": "Оба типа", "emoji": "🗑️", "rars": ["common", "rare"]},
}


@router.callback_query(F.data == "m:trash")
async def trash_menu(cb: CallbackQuery):
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    cards = user.get("cards", [])
    if not cards:
        return await cb.answer("❌ Нет карт!", show_alert=True)
    
    text = (
        f"╔══════════════════════╗\n"
        f"║   🗑️ <b>ПРОДАЖА МУСОРА</b>   ║\n"
        f"╠══════════════════════╣\n"
        f"║ 💰 <b>{user.get('coins', 0):,}</b> монет\n"
        f"║ 📉 <b>5%</b> от цены\n"
        f"║ ⚠️ <i>По 1 карте останется!</i>\n"
        f"╚══════════════════════╝\n\n"
    )
    
    btns = []
    
    # Считаем дубли для каждой категории
    for cat_id, cat in TRASH_CATS.items():
        groups = {}
        for c in cards:
            if c["rarity"] in cat["rars"]:
                n = c["name"]
                if n not in groups:
                    groups[n] = {"card": c, "count": 0}
                groups[n]["count"] += 1
        
        dupes = sum(max(0, g["count"] - 1) for g in groups.values())
        total_price = sum(get_quick_price(g["card"]) * max(0, g["count"] - 1) for g in groups.values())
        
        if dupes > 0:
            btns.append([InlineKeyboardButton(
                text=f"{cat['emoji']} {cat['name']} дубли ({dupes}) = {total_price}🪙",
                callback_data=f"m:trashdo:{cat_id}"
            )])
    
    # Все дубли
    all_groups = {}
    for c in cards:
        n = c["name"]
        if n not in all_groups:
            all_groups[n] = {"card": c, "count": 0}
        all_groups[n]["count"] += 1
    
    all_dupes = sum(max(0, g["count"] - 1) for g in all_groups.values())
    all_price = sum(get_quick_price(g["card"]) * max(0, g["count"] - 1) for g in all_groups.values())
    
    if all_dupes > 0:
        btns.append([InlineKeyboardButton(
            text=f"🧹 ВСЕ дубли ({all_dupes}) = {all_price}🪙",
            callback_data="m:trashdo:all"
        )])
    
    if not btns:
        text += "<i>Нет дубликатов для продажи!</i>"
    
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="m:back")])
    
    await safe_edit(cb, text, InlineKeyboardMarkup(inline_keyboard=btns))
    await cb.answer()


@router.callback_query(F.data.startswith("m:trashdo:"))
async def trash_do(cb: CallbackQuery):
    cat_id = cb.data.split(":")[2]
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    cards = user.get("cards", [])
    target_rars = None if cat_id == "all" else TRASH_CATS.get(cat_id, {}).get("rars")
    
    # Группируем
    groups = {}
    for c in cards:
        n = c["name"]
        if n not in groups:
            groups[n] = {"card": c, "count": 0}
        groups[n]["count"] += 1
    
    # Продаём дубли
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
        f"╔══════════════════════╗\n"
        f"║    ✅ <b>ПРОДАНО!</b>    ║\n"
        f"╠══════════════════════╣\n"
        f"║ 🗑️ Карт: <b>{total_sold}</b>\n"
        f"║ 💰 +<b>{total_coins}</b> 🪙\n"
        f"║ 💵 Баланс: <b>{db.get_coins(uid):,}</b>\n"
        f"╚══════════════════════╝"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Ещё", callback_data="m:trash")],
        [InlineKeyboardButton(text="◀️ Магазин", callback_data="m:back")],
    ])
    
    await safe_edit(cb, text, kb)
    await cb.answer(f"✅ {total_sold} карт = +{total_coins} 🪙", show_alert=True)


# Для совместимости со старыми callback
@router.callback_query(F.data == "market_back")
async def old_market_back(cb: CallbackQuery, state: FSMContext = None):
    cb.data = "m:back"
    await market_back(cb, state)