# handlers/trade.py
import random
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import EMOJI, CARDS, LIMITED_CARDS, FUSION_CARDS, RARITY_COLORS, RARITY_NAMES
from database import DatabaseManager

router = Router()

# Объединённый список всех карт
ALL_CARDS = CARDS + LIMITED_CARDS + FUSION_CARDS

# Порядок редкостей (меньше = реже)
RARITY_ORDER = {
    "mega_fused": 0, "mega": 1, "fused": 2, "limited": 3, 
    "special": 4, "mythic": 5, "legendary": 6, "epic": 7, 
    "rare": 8, "common": 9
}

# Хранилище активных обменов
active_trades = {}

CARDS_PER_PAGE = 8


class TradeStates(StatesGroup):
    selecting_my_card = State()
    selecting_target = State()
    selecting_target_card = State()


def is_group(msg: Message) -> bool:
    return msg.chat.type in ["group", "supergroup"]


def get_db(event):
    if isinstance(event, Message):
        return DatabaseManager.get_db(event.chat.id)
    elif isinstance(event, CallbackQuery):
        return DatabaseManager.get_db(event.message.chat.id)
    return None


def get_chat_id(event):
    if isinstance(event, Message):
        return event.chat.id
    elif isinstance(event, CallbackQuery):
        return event.message.chat.id
    return None


def find_card_info(card_name: str) -> dict | None:
    """Найти информацию о карте во всех списках"""
    for card in ALL_CARDS:
        if card["name"] == card_name:
            return card
    return None


def group_user_cards(cards: list) -> list:
    """Группировка карт пользователя с подсчётом дубликатов"""
    groups = {}
    for card in cards:
        name = card["name"]
        if name not in groups:
            groups[name] = {"card": card, "count": 0}
        groups[name]["count"] += 1
    
    # Сортировка: сначала редкие, потом по силе
    sorted_cards = sorted(
        groups.values(),
        key=lambda x: (RARITY_ORDER.get(x["card"]["rarity"], 99), -(x["card"]["attack"] + x["card"]["defense"]))
    )
    return sorted_cards


def get_card_display(card: dict, count: int = 1) -> str:
    """Красивое отображение карты"""
    rc = RARITY_COLORS.get(card["rarity"], "⚪")
    power = card["attack"] + card["defense"]
    cnt = f" x{count}" if count > 1 else ""
    return f"{rc} {card['emoji']} {card['name']} (💪{power}){cnt}"


def paginate_buttons(page: int, total_pages: int, prefix: str) -> list:
    """Кнопки пагинации"""
    if total_pages <= 1:
        return []
    
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page-1}"))
    buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page+1}"))
    
    return [buttons] if buttons else []


# ═══════════════════════════════════════════════
#  КОМАНДА /trade
# ═══════════════════════════════════════════════

@router.message(Command("trade", "обмен"))
async def cmd_trade(msg: Message, state: FSMContext):
    """Начало торговли"""
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Торговля только в группах!")
    
    await state.clear()
    
    db = get_db(msg)
    uid = msg.from_user.id
    chat_id = msg.chat.id
    
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    
    DatabaseManager.get_global_db().update_user(uid, msg.from_user.username, msg.from_user.first_name)
    
    user = db.get_user(uid)
    cards = user.get("cards", [])
    
    if not cards:
        return await msg.reply(
            f"🔁 <b>ТОРГОВЛЯ</b>\n\n"
            f"❌ У тебя нет карт для обмена!\n\n"
            f"💡 /spin — получить карты",
            parse_mode="HTML"
        )
    
    # Сохраняем данные
    await state.set_state(TradeStates.selecting_my_card)
    await state.update_data(
        user_id=uid,
        chat_id=chat_id,
        page=0
    )
    
    await show_my_cards_page(msg, state, 0)


async def show_my_cards_page(msg_or_cb, state: FSMContext, page: int):
    """Показать страницу своих карт"""
    data = await state.get_data()
    uid = data.get("user_id")
    chat_id = data.get("chat_id")
    
    db = DatabaseManager.get_db(chat_id)
    user = db.get_user(uid)
    cards = user.get("cards", [])
    
    grouped = group_user_cards(cards)
    total_pages = max(1, (len(grouped) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    
    page_cards = grouped[page * CARDS_PER_PAGE:(page + 1) * CARDS_PER_PAGE]
    
    await state.update_data(page=page, grouped_cards=grouped)
    
    # Создаём кнопки
    buttons = []
    for i, item in enumerate(page_cards):
        card = item["card"]
        count = item["count"]
        idx = page * CARDS_PER_PAGE + i
        
        # Метка для редких
        warn = ""
        if card["rarity"] in ["limited", "fused", "mega_fused"]:
            warn = "⚠️"
        elif card["rarity"] in ["mega", "special"]:
            warn = "❗"
        
        buttons.append([InlineKeyboardButton(
            text=f"{warn}{get_card_display(card, count)}",
            callback_data=f"trade_my:{idx}"
        )])
    
    # Пагинация
    buttons.extend(paginate_buttons(page, total_pages, "trade_page"))
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="trade_cancel")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    text = (
        f"🔁 <b>ТОРГОВЛЯ</b>\n\n"
        f"🃏 Карт: <b>{len(cards)}</b> (уникальных: {len(grouped)})\n\n"
        f"<b>Выбери карту для обмена:</b>\n"
        f"<i>⚠️ — редкая, ❗ — очень редкая</i>"
    )
    
    if isinstance(msg_or_cb, Message):
        await msg_or_cb.reply(text, parse_mode="HTML", reply_markup=kb)
    else:
        try:
            await msg_or_cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except:
            pass


@router.callback_query(F.data.startswith("trade_page:"))
async def trade_page(cb: CallbackQuery, state: FSMContext):
    """Переключение страницы своих карт"""
    current_state = await state.get_state()
    if current_state != TradeStates.selecting_my_card.state:
        return await cb.answer("❌ Начни заново: /trade", show_alert=True)
    
    data = await state.get_data()
    if cb.from_user.id != data.get("user_id"):
        return await cb.answer("❌ Это не твой обмен!", show_alert=True)
    
    page = int(cb.data.split(":")[1])
    await show_my_cards_page(cb, state, page)
    await cb.answer()


@router.callback_query(F.data.startswith("trade_my:"))
async def trade_select_my_card(cb: CallbackQuery, state: FSMContext):
    """Выбор своей карты"""
    current_state = await state.get_state()
    if current_state != TradeStates.selecting_my_card.state:
        return await cb.answer("❌ Начни заново: /trade", show_alert=True)
    
    data = await state.get_data()
    if cb.from_user.id != data.get("user_id"):
        return await cb.answer("❌ Это не твой обмен!", show_alert=True)
    
    idx = int(cb.data.split(":")[1])
    grouped = data.get("grouped_cards", [])
    
    if idx >= len(grouped):
        return await cb.answer("❌ Карта не найдена!", show_alert=True)
    
    selected = grouped[idx]["card"]
    
    # Сохраняем выбранную карту
    await state.update_data(my_card=selected)
    await state.set_state(TradeStates.selecting_target)
    
    rc = RARITY_COLORS.get(selected["rarity"], "⚪")
    rn = RARITY_NAMES.get(selected["rarity"], selected["rarity"])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="trade_cancel")]
    ])
    
    await cb.message.edit_text(
        f"🔁 <b>ТОРГОВЛЯ</b>\n\n"
        f"<b>Твоя карта:</b>\n"
        f"{rc} {selected['emoji']} <b>{selected['name']}</b>\n"
        f"├ {rn}\n"
        f"├ ⚔️ {selected['attack']} | 🛡️ {selected['defense']}\n"
        f"└ 💪 {selected['attack'] + selected['defense']}\n\n"
        f"<b>Теперь ответь на сообщение игрока</b> с кем хочешь обменяться,\n"
        f"или введи его <code>@username</code>:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await cb.answer()


@router.message(TradeStates.selecting_target)
async def trade_select_target(msg: Message, state: FSMContext):
    """Выбор цели для обмена"""
    data = await state.get_data()
    owner_id = data.get("user_id")
    chat_id = data.get("chat_id")
    
    if msg.from_user.id != owner_id:
        return  # Игнорируем чужие сообщения
    
    db = DatabaseManager.get_db(chat_id)
    global_db = DatabaseManager.get_global_db()
    
    target_id = None
    target_name = None
    
    # Проверяем реплай
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
        target_id = target.id
        target_name = target.first_name or target.username or "Игрок"
        
        if not db.get_user(target_id):
            db.create_user(target_id, target.username, target.first_name)
        global_db.update_user(target_id, target.username, target.first_name)
    
    # Или по username
    elif msg.text and msg.text.startswith("@"):
        username = msg.text[1:].strip().lower()
        user_data = global_db.find_by_username(username)
        
        if user_data:
            target_id = user_data["user_id"]
            target_name = user_data.get("first_name", username)
            
            if not db.get_user(target_id):
                db.create_user(target_id, username, target_name)
    
    if not target_id:
        return await msg.reply(
            "❌ <b>Пользователь не найден!</b>\n\n"
            "💡 Попробуй:\n"
            "• Ответить на сообщение игрока\n"
            "• Убедиться, что он использовал бота",
            parse_mode="HTML"
        )
    
    if target_id == owner_id:
        return await msg.reply("❌ Нельзя обменяться с самим собой!")
    
    target_user = db.get_user(target_id)
    target_cards = target_user.get("cards", []) if target_user else []
    
    if not target_cards:
        return await msg.reply(f"❌ У <b>{target_name}</b> нет карт для обмена!", parse_mode="HTML")
    
    # Сохраняем цель
    await state.update_data(
        target_id=target_id,
        target_name=target_name,
        target_page=0
    )
    await state.set_state(TradeStates.selecting_target_card)
    
    await show_target_cards_page(msg, state, 0)


async def show_target_cards_page(msg_or_cb, state: FSMContext, page: int):
    """Показать карты цели"""
    data = await state.get_data()
    target_id = data.get("target_id")
    target_name = data.get("target_name")
    chat_id = data.get("chat_id")
    my_card = data.get("my_card")
    
    db = DatabaseManager.get_db(chat_id)
    target_user = db.get_user(target_id)
    target_cards = target_user.get("cards", []) if target_user else []
    
    grouped = group_user_cards(target_cards)
    total_pages = max(1, (len(grouped) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    
    page_cards = grouped[page * CARDS_PER_PAGE:(page + 1) * CARDS_PER_PAGE]
    
    await state.update_data(target_page=page, target_grouped=grouped)
    
    # Кнопки
    buttons = []
    for i, item in enumerate(page_cards):
        card = item["card"]
        count = item["count"]
        idx = page * CARDS_PER_PAGE + i
        
        warn = ""
        if card["rarity"] in ["limited", "fused", "mega_fused"]:
            warn = "⚠️"
        elif card["rarity"] in ["mega", "special"]:
            warn = "❗"
        
        buttons.append([InlineKeyboardButton(
            text=f"{warn}{get_card_display(card, count)}",
            callback_data=f"trade_target:{idx}"
        )])
    
    buttons.extend(paginate_buttons(page, total_pages, "trade_tpage"))
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="trade_back_my")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="trade_cancel")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    rc = RARITY_COLORS.get(my_card["rarity"], "⚪")
    
    text = (
        f"🔁 <b>ОБМЕН С {target_name}</b>\n\n"
        f"<b>Твоя карта:</b> {rc} {my_card['emoji']} {my_card['name']}\n\n"
        f"<b>Карты {target_name} ({len(target_cards)}):</b>\n"
        f"Выбери что хочешь получить:"
    )
    
    if isinstance(msg_or_cb, Message):
        await msg_or_cb.reply(text, parse_mode="HTML", reply_markup=kb)
    else:
        try:
            await msg_or_cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except:
            pass


@router.callback_query(F.data.startswith("trade_tpage:"))
async def trade_target_page(cb: CallbackQuery, state: FSMContext):
    """Переключение страницы карт цели"""
    data = await state.get_data()
    if cb.from_user.id != data.get("user_id"):
        return await cb.answer("❌ Это не твой обмен!", show_alert=True)
    
    page = int(cb.data.split(":")[1])
    await show_target_cards_page(cb, state, page)
    await cb.answer()


@router.callback_query(F.data == "trade_back_my")
async def trade_back_to_my(cb: CallbackQuery, state: FSMContext):
    """Назад к выбору своей карты"""
    data = await state.get_data()
    if cb.from_user.id != data.get("user_id"):
        return await cb.answer("❌ Это не твой обмен!", show_alert=True)
    
    await state.set_state(TradeStates.selecting_my_card)
    page = data.get("page", 0)
    await show_my_cards_page(cb, state, page)
    await cb.answer()


@router.callback_query(F.data.startswith("trade_target:"))
async def trade_select_target_card(cb: CallbackQuery, state: FSMContext, bot: Bot):
    """Выбор карты цели → отправка запроса"""
    data = await state.get_data()
    if cb.from_user.id != data.get("user_id"):
        return await cb.answer("❌ Это не твой обмен!", show_alert=True)
    
    idx = int(cb.data.split(":")[1])
    target_grouped = data.get("target_grouped", [])
    
    if idx >= len(target_grouped):
        return await cb.answer("❌ Карта не найдена!", show_alert=True)
    
    my_card = data.get("my_card")
    target_card = target_grouped[idx]["card"]
    target_id = data.get("target_id")
    target_name = data.get("target_name")
    chat_id = data.get("chat_id")
    initiator_id = data.get("user_id")
    
    db = DatabaseManager.get_db(chat_id)
    initiator = db.get_user(initiator_id)
    initiator_name = initiator.get("first_name", "Игрок") if initiator else "Игрок"
    
    # Создаём ID обмена
    trade_id = str(uuid.uuid4())[:8]
    
    active_trades[trade_id] = {
        "initiator_id": initiator_id,
        "initiator_name": initiator_name,
        "initiator_card": my_card,
        "target_id": target_id,
        "target_name": target_name,
        "target_card": target_card,
        "chat_id": chat_id
    }
    
    await state.clear()
    
    # Отправляем запрос цели
    rc1 = RARITY_COLORS.get(my_card["rarity"], "⚪")
    rc2 = RARITY_COLORS.get(target_card["rarity"], "⚪")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"trade_accept:{trade_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"trade_decline:{trade_id}")
        ]
    ])
    
    try:
        await bot.send_message(
            target_id,
            f"🔁 <b>ПРЕДЛОЖЕНИЕ ОБМЕНА</b>\n\n"
            f"👤 От: <b>{initiator_name}</b>\n\n"
            f"<b>Его карта:</b>\n"
            f"{rc1} {my_card['emoji']} <b>{my_card['name']}</b>\n"
            f"└ 💪 {my_card['attack'] + my_card['defense']}\n\n"
            f"<b>Твоя карта:</b>\n"
            f"{rc2} {target_card['emoji']} <b>{target_card['name']}</b>\n"
            f"└ 💪 {target_card['attack'] + target_card['defense']}\n\n"
            f"Принять обмен?",
            parse_mode="HTML",
            reply_markup=kb
        )
        
        await cb.message.edit_text(
            f"✅ <b>ЗАПРОС ОТПРАВЛЕН!</b>\n\n"
            f"👤 Кому: <b>{target_name}</b>\n\n"
            f"<b>Твоя карта:</b> {rc1} {my_card['emoji']} {my_card['name']}\n"
            f"<b>Его карта:</b> {rc2} {target_card['emoji']} {target_card['name']}\n\n"
            f"⏳ Ожидание ответа...",
            parse_mode="HTML"
        )
        
    except Exception as e:
        del active_trades[trade_id]
        await cb.message.edit_text(
            f"❌ <b>ОШИБКА</b>\n\n"
            f"Не удалось отправить запрос.\n"
            f"Возможно, игрок не начал диалог с ботом.\n\n"
            f"💡 Попроси его написать /start боту в личку",
            parse_mode="HTML"
        )
    
    await cb.answer()


# ═══════════════════════════════════════════════
#  ПРИНЯТИЕ / ОТКЛОНЕНИЕ
# ═══════════════════════════════════════════════

@router.callback_query(F.data.startswith("trade_accept:"))
async def trade_accept(cb: CallbackQuery, bot: Bot):
    """Принятие обмена"""
    trade_id = cb.data.split(":")[1]
    
    if trade_id not in active_trades:
        return await cb.message.edit_text(
            "❌ <b>Обмен не найден или истёк!</b>",
            parse_mode="HTML"
        )
    
    trade = active_trades[trade_id]
    
    if cb.from_user.id != trade["target_id"]:
        return await cb.answer("❌ Этот обмен не для тебя!", show_alert=True)
    
    db = DatabaseManager.get_db(trade["chat_id"])
    
    initiator = db.get_user(trade["initiator_id"])
    target = db.get_user(trade["target_id"])
    
    if not initiator or not target:
        del active_trades[trade_id]
        return await cb.message.edit_text("❌ Один из игроков не найден!", parse_mode="HTML")
    
    # Проверяем наличие карт
    i_cards = initiator.get("cards", [])
    t_cards = target.get("cards", [])
    
    i_has = any(c["name"] == trade["initiator_card"]["name"] for c in i_cards)
    t_has = any(c["name"] == trade["target_card"]["name"] for c in t_cards)
    
    if not i_has:
        del active_trades[trade_id]
        return await cb.message.edit_text(
            f"❌ У <b>{trade['initiator_name']}</b> больше нет этой карты!",
            parse_mode="HTML"
        )
    
    if not t_has:
        del active_trades[trade_id]
        return await cb.message.edit_text(
            f"❌ У тебя больше нет этой карты!",
            parse_mode="HTML"
        )
    
    # Выполняем обмен
    i_card = trade["initiator_card"]
    t_card = trade["target_card"]
    
    db.remove_card_from_user(trade["initiator_id"], i_card["name"])
    db.remove_card_from_user(trade["target_id"], t_card["name"])
    
    # Добавляем с полной информацией
    db.add_card(trade["initiator_id"], {
        "name": t_card["name"],
        "rarity": t_card["rarity"],
        "attack": t_card["attack"],
        "defense": t_card["defense"],
        "emoji": t_card["emoji"]
    })
    db.add_card(trade["target_id"], {
        "name": i_card["name"],
        "rarity": i_card["rarity"],
        "attack": i_card["attack"],
        "defense": i_card["defense"],
        "emoji": i_card["emoji"]
    })
    
    del active_trades[trade_id]
    
    rc1 = RARITY_COLORS.get(i_card["rarity"], "⚪")
    rc2 = RARITY_COLORS.get(t_card["rarity"], "⚪")
    
    # Уведомляем обоих
    await cb.message.edit_text(
        f"✅ <b>ОБМЕН ЗАВЕРШЁН!</b>\n\n"
        f"🔄 Ты получил: {rc1} {i_card['emoji']} <b>{i_card['name']}</b>\n"
        f"🔄 Ты отдал: {rc2} {t_card['emoji']} <b>{t_card['name']}</b>",
        parse_mode="HTML"
    )
    
    try:
        await bot.send_message(
            trade["initiator_id"],
            f"✅ <b>ОБМЕН ЗАВЕРШЁН!</b>\n\n"
            f"👤 С: <b>{trade['target_name']}</b>\n\n"
            f"🔄 Ты получил: {rc2} {t_card['emoji']} <b>{t_card['name']}</b>\n"
            f"🔄 Ты отдал: {rc1} {i_card['emoji']} <b>{i_card['name']}</b>",
            parse_mode="HTML"
        )
    except:
        pass
    
    await cb.answer("✅ Обмен завершён!")


@router.callback_query(F.data.startswith("trade_decline:"))
async def trade_decline(cb: CallbackQuery, bot: Bot):
    """Отклонение обмена"""
    trade_id = cb.data.split(":")[1]
    
    if trade_id not in active_trades:
        return await cb.message.edit_text("❌ Обмен не найден!", parse_mode="HTML")
    
    trade = active_trades[trade_id]
    
    if cb.from_user.id != trade["target_id"]:
        return await cb.answer("❌ Этот обмен не для тебя!", show_alert=True)
    
    del active_trades[trade_id]
    
    await cb.message.edit_text("❌ <b>Обмен отклонён</b>", parse_mode="HTML")
    
    try:
        await bot.send_message(
            trade["initiator_id"],
            f"❌ <b>ОБМЕН ОТКЛОНЁН</b>\n\n"
            f"<b>{trade['target_name']}</b> отклонил твоё предложение.",
            parse_mode="HTML"
        )
    except:
        pass
    
    await cb.answer()


@router.callback_query(F.data == "trade_cancel")
async def trade_cancel(cb: CallbackQuery, state: FSMContext):
    """Отмена обмена"""
    await state.clear()
    await cb.message.edit_text("❌ <b>Обмен отменён</b>", parse_mode="HTML")
    await cb.answer()


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()