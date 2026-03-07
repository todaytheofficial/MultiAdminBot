# handlers/pay.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import EMOJI
from database import DatabaseManager

router = Router()


def is_group(msg: Message) -> bool:
    return msg.chat.type in ["group", "supergroup"]


def get_db(msg: Message):
    return DatabaseManager.get_db(msg.chat.id)


class PayStates(StatesGroup):
    waiting_amount = State()


@router.message(Command("pay", "give", "transfer", "подарить", "передать"))
async def cmd_pay(msg: Message, state: FSMContext):
    """Передать ресурсы другому игроку"""
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    
    db = get_db(msg)
    uid = msg.from_user.id
    
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    
    # Проверяем, есть ли реплай
    if not msg.reply_to_message:
        return await msg.reply(
            "💸 <b>ПЕРЕДАЧА РЕСУРСОВ</b>\n\n"
            "Ответь на сообщение игрока и напиши:\n"
            "<code>/pay coins 100</code> — передать 100 монет\n"
            "<code>/pay tickets 5</code> — передать 5 билетов\n"
            "<code>/pay mults 2</code> — передать 2 мультов\n\n"
            "Или просто <code>/pay</code> в ответ на сообщение",
            parse_mode="HTML"
        )
    
    target = msg.reply_to_message.from_user
    target_id = target.id
    target_name = target.first_name or target.username or "Игрок"
    
    # Нельзя самому себе
    if target_id == uid:
        return await msg.reply(f"{EMOJI['cross']} Нельзя передать самому себе!")
    
    # Нельзя ботам
    if target.is_bot:
        return await msg.reply(f"{EMOJI['cross']} Нельзя передать боту!")
    
    # Создаём получателя если нет
    if not db.get_user(target_id):
        db.create_user(target_id, target.username, target.first_name)
    
    # Парсим аргументы
    args = msg.text.split()
    
    # Если указаны аргументы: /pay coins 100
    if len(args) >= 3:
        resource_type = args[1].lower()
        try:
            amount = int(args[2])
        except ValueError:
            return await msg.reply(f"{EMOJI['cross']} Укажи число!")
        
        if amount <= 0:
            return await msg.reply(f"{EMOJI['cross']} Сумма должна быть больше 0!")
        
        # Выполняем передачу
        result = await execute_transfer(db, uid, target_id, target_name, resource_type, amount, msg)
        return
    
    # Иначе показываем меню выбора
    user = db.get_user(uid)
    coins = user.get("coins", 0)
    tickets = db.get_spin_tickets(uid)
    mults = user.get("mults", 0)
    
    await state.set_state(PayStates.waiting_amount)
    await state.update_data(target_id=target_id, target_name=target_name)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🪙 Монеты ({coins})", callback_data="pay_select:coins"),
        ],
        [
            InlineKeyboardButton(text=f"🎫 Билеты ({tickets})", callback_data="pay_select:tickets"),
        ],
        [
            InlineKeyboardButton(text=f"💎 Mults ({mults})", callback_data="pay_select:mults"),
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="pay_cancel"),
        ]
    ])
    
    await msg.reply(
        f"💸 <b>ПЕРЕДАЧА РЕСУРСОВ</b>\n\n"
        f"👤 Кому: <b>{target_name}</b>\n\n"
        f"<b>Твои ресурсы:</b>\n"
        f"🪙 Монеты: <b>{coins}</b>\n"
        f"🎫 Билеты: <b>{tickets}</b>\n"
        f"💎 Mults: <b>{mults}</b>\n\n"
        f"Что передать?",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("pay_select:"))
async def pay_select_resource(callback: CallbackQuery, state: FSMContext):
    """Выбор типа ресурса"""
    resource = callback.data.split(":")[1]
    
    data = await state.get_data()
    target_id = data.get("target_id")
    target_name = data.get("target_name", "Игрок")
    
    if not target_id:
        await state.clear()
        return await callback.answer("❌ Ошибка! Начни заново.", show_alert=True)
    
    db = DatabaseManager.get_db(callback.message.chat.id)
    uid = callback.from_user.id
    user = db.get_user(uid)
    
    if resource == "coins":
        available = user.get("coins", 0)
        emoji = "🪙"
        name = "монет"
    elif resource == "tickets":
        available = db.get_spin_tickets(uid)
        emoji = "🎫"
        name = "билетов"
    elif resource == "mults":
        available = user.get("mults", 0)
        emoji = "💎"
        name = "Mults"
    else:
        return await callback.answer("❌ Неизвестный ресурс!", show_alert=True)
    
    if available <= 0:
        return await callback.answer(f"❌ У тебя нет {name}!", show_alert=True)
    
    await state.update_data(resource=resource, available=available)
    
    # Кнопки с быстрыми суммами
    amounts = []
    if available >= 10:
        amounts.append(10)
    if available >= 50:
        amounts.append(50)
    if available >= 100:
        amounts.append(100)
    if available >= 500:
        amounts.append(500)
    
    buttons = []
    row = []
    for amt in amounts:
        row.append(InlineKeyboardButton(text=f"{amt}", callback_data=f"pay_amount:{amt}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text=f"🎲 ВСЁ ({available})", callback_data=f"pay_amount:{available}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="pay_back")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await callback.message.edit_text(
            f"💸 <b>ПЕРЕДАЧА {emoji}</b>\n\n"
            f"👤 Кому: <b>{target_name}</b>\n"
            f"📦 Ресурс: <b>{emoji} {name}</b>\n"
            f"💰 Доступно: <b>{available}</b>\n\n"
            f"Выбери сумму или напиши число:",
            parse_mode="HTML",
            reply_markup=kb
        )
    except:
        pass
    
    await callback.answer()


@router.callback_query(F.data.startswith("pay_amount:"))
async def pay_amount_selected(callback: CallbackQuery, state: FSMContext):
    """Выбрана сумма"""
    try:
        amount = int(callback.data.split(":")[1])
    except:
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    data = await state.get_data()
    target_id = data.get("target_id")
    target_name = data.get("target_name", "Игрок")
    resource = data.get("resource")
    available = data.get("available", 0)
    
    if not target_id or not resource:
        await state.clear()
        return await callback.answer("❌ Ошибка! Начни заново.", show_alert=True)
    
    if amount > available:
        return await callback.answer(f"❌ Недостаточно! Доступно: {available}", show_alert=True)
    
    if amount <= 0:
        return await callback.answer("❌ Сумма должна быть больше 0!", show_alert=True)
    
    # Подтверждение
    if resource == "coins":
        emoji = "🪙"
        name = "монет"
    elif resource == "tickets":
        emoji = "🎫"
        name = "билетов"
    else:
        emoji = "💎"
        name = "Mults"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"pay_confirm:{amount}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="pay_cancel"),
        ]
    ])
    
    try:
        await callback.message.edit_text(
            f"💸 <b>ПОДТВЕРЖДЕНИЕ</b>\n\n"
            f"👤 Кому: <b>{target_name}</b>\n"
            f"📦 Ресурс: <b>{emoji} {name}</b>\n"
            f"💰 Сумма: <b>{amount}</b>\n\n"
            f"Подтвердить передачу?",
            parse_mode="HTML",
            reply_markup=kb
        )
    except:
        pass
    
    await state.update_data(amount=amount)
    await callback.answer()


@router.callback_query(F.data.startswith("pay_confirm:"))
async def pay_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение передачи"""
    data = await state.get_data()
    target_id = data.get("target_id")
    target_name = data.get("target_name", "Игрок")
    resource = data.get("resource")
    amount = data.get("amount", 0)
    
    await state.clear()
    
    if not target_id or not resource or amount <= 0:
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    db = DatabaseManager.get_db(callback.message.chat.id)
    uid = callback.from_user.id
    
    # Проверяем ресурсы ещё раз
    user = db.get_user(uid)
    if not user:
        return await callback.answer("❌ Ошибка!", show_alert=True)
    
    if resource == "coins":
        available = user.get("coins", 0)
        emoji = "🪙"
        name = "монет"
    elif resource == "tickets":
        available = db.get_spin_tickets(uid)
        emoji = "🎫"
        name = "билетов"
    else:
        available = user.get("mults", 0)
        emoji = "💎"
        name = "Mults"
    
    if amount > available:
        return await callback.answer(f"❌ Недостаточно! Доступно: {available}", show_alert=True)
    
    # Выполняем передачу
    success = False
    
    if resource == "coins":
        db.remove_coins(uid, amount)
        db.add_coins(target_id, amount)
        success = True
    elif resource == "tickets":
        # Убираем билеты у отправителя
        for _ in range(amount):
            if not db.use_spin_ticket(uid):
                break
        # Добавляем получателю
        db.add_spin_tickets(target_id, amount)
        success = True
    elif resource == "mults":
        if db.remove_mults(uid, amount):
            db.add_mults(target_id, amount)
            success = True
    
    if not success:
        return await callback.answer("❌ Ошибка передачи!", show_alert=True)
    
    # Квест
    try:
        from handlers.quests import update_quest_progress
        update_quest_progress(db, uid, "pay", 1)
    except:
        pass
    
    sender_name = callback.from_user.first_name or "Игрок"
    
    try:
        await callback.message.edit_text(
            f"✅ <b>ПЕРЕДАЧА УСПЕШНА!</b>\n\n"
            f"👤 От: <b>{sender_name}</b>\n"
            f"👤 Кому: <b>{target_name}</b>\n"
            f"📦 Ресурс: <b>{emoji} {name}</b>\n"
            f"💰 Сумма: <b>{amount}</b>\n\n"
            f"💸 <i>Ресурсы переданы!</i>",
            parse_mode="HTML"
        )
    except:
        pass
    
    await callback.answer(f"✅ Передано {amount} {emoji}!", show_alert=True)


@router.callback_query(F.data == "pay_back")
async def pay_back(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору ресурса"""
    data = await state.get_data()
    target_id = data.get("target_id")
    target_name = data.get("target_name", "Игрок")
    
    if not target_id:
        await state.clear()
        try:
            await callback.message.delete()
        except:
            pass
        return await callback.answer()
    
    db = DatabaseManager.get_db(callback.message.chat.id)
    uid = callback.from_user.id
    user = db.get_user(uid)
    
    coins = user.get("coins", 0) if user else 0
    tickets = db.get_spin_tickets(uid)
    mults = user.get("mults", 0) if user else 0
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🪙 Монеты ({coins})", callback_data="pay_select:coins")],
        [InlineKeyboardButton(text=f"🎫 Билеты ({tickets})", callback_data="pay_select:tickets")],
        [InlineKeyboardButton(text=f"💎 Mults ({mults})", callback_data="pay_select:mults")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="pay_cancel")],
    ])
    
    try:
        await callback.message.edit_text(
            f"💸 <b>ПЕРЕДАЧА РЕСУРСОВ</b>\n\n"
            f"👤 Кому: <b>{target_name}</b>\n\n"
            f"<b>Твои ресурсы:</b>\n"
            f"🪙 Монеты: <b>{coins}</b>\n"
            f"🎫 Билеты: <b>{tickets}</b>\n"
            f"💎 Mults: <b>{mults}</b>\n\n"
            f"Что передать?",
            parse_mode="HTML",
            reply_markup=kb
        )
    except:
        pass
    
    await callback.answer()


@router.callback_query(F.data == "pay_cancel")
async def pay_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена передачи"""
    await state.clear()
    try:
        await callback.message.edit_text("❌ <b>Передача отменена</b>", parse_mode="HTML")
    except:
        pass
    await callback.answer()


async def execute_transfer(db, sender_id: int, target_id: int, target_name: str, 
                          resource_type: str, amount: int, msg: Message):
    """Выполнить передачу через текстовую команду"""
    user = db.get_user(sender_id)
    if not user:
        return await msg.reply(f"{EMOJI['cross']} Ты не зарегистрирован!")
    
    # Определяем ресурс
    if resource_type in ["coins", "монеты", "coin", "c"]:
        available = user.get("coins", 0)
        emoji = "🪙"
        name = "монет"
        res = "coins"
    elif resource_type in ["tickets", "ticket", "билеты", "билет", "t"]:
        available = db.get_spin_tickets(sender_id)
        emoji = "🎫"
        name = "билетов"
        res = "tickets"
    elif resource_type in ["mults", "mult", "мульты", "м", "m"]:
        available = user.get("mults", 0)
        emoji = "💎"
        name = "Mults"
        res = "mults"
    else:
        return await msg.reply(
            f"{EMOJI['cross']} Неизвестный ресурс!\n\n"
            f"Доступно: <code>coins</code>, <code>tickets</code>, <code>mults</code>",
            parse_mode="HTML"
        )
    
    if amount > available:
        return await msg.reply(f"{EMOJI['cross']} Недостаточно! У тебя: {available} {emoji}")
    
    if amount <= 0:
        return await msg.reply(f"{EMOJI['cross']} Сумма должна быть больше 0!")
    
    # Выполняем
    success = False
    
    if res == "coins":
        db.remove_coins(sender_id, amount)
        db.add_coins(target_id, amount)
        success = True
    elif res == "tickets":
        for _ in range(amount):
            db.use_spin_ticket(sender_id)
        db.add_spin_tickets(target_id, amount)
        success = True
    elif res == "mults":
        if db.remove_mults(sender_id, amount):
            db.add_mults(target_id, amount)
            success = True
    
    if not success:
        return await msg.reply(f"{EMOJI['cross']} Ошибка передачи!")
    
    sender_name = msg.from_user.first_name or "Игрок"
    
    await msg.reply(
        f"✅ <b>ПЕРЕДАЧА УСПЕШНА!</b>\n\n"
        f"👤 От: <b>{sender_name}</b>\n"
        f"👤 Кому: <b>{target_name}</b>\n"
        f"📦 Ресурс: <b>{emoji} {name}</b>\n"
        f"💰 Сумма: <b>{amount}</b>",
        parse_mode="HTML"
    )