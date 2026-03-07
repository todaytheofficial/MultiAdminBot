# handlers/quests.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from config import EMOJI, CARDS
from quest_config import get_daily_quests, is_new_day
from database import DatabaseManager

router = Router()


def is_group_chat(message: Message) -> bool:
    return message.chat.type in ["group", "supergroup"]


def get_db(source):
    """Получить БД для чата (принимает Message или CallbackQuery)"""
    if isinstance(source, CallbackQuery):
        return DatabaseManager.get_db(source.message.chat.id)
    return DatabaseManager.get_db(source.chat.id)


def get_quest_progress_text(quest):
    progress = quest.get('progress', 0)
    target = quest.get('target', 1)
    return f"{min(progress, target)}/{target}"


def get_quest_reward_text(quest):
    reward_type = quest.get('reward_type', 'coins')
    reward_amount = quest.get('reward_amount', 0)
    if reward_type == 'coins':
        return f"🪙 {reward_amount} монет"
    elif reward_type == 'tickets':
        return f"🎫 {reward_amount} билетов"
    return f"{reward_amount}"


def get_progress_bar(progress, target, length=10):
    """Красивый прогресс-бар"""
    filled = min(int(progress / target * length), length) if target > 0 else 0
    empty = length - filled
    return "█" * filled + "░" * empty


def ensure_user_quests(db, user_id, username=None, first_name=None):
    """Гарантирует наличие квестов у пользователя, обновляет если новый день"""
    if not db.get_user(user_id):
        db.create_user(user_id, username, first_name)

    user_quests = db.get_user_quests(user_id)

    if not user_quests or is_new_day(user_quests.get('last_reset', '')):
        new_quests = get_daily_quests()
        db.set_user_quests(user_id, {
            'quests': new_quests,
            'last_reset': __import__('datetime').date.today().isoformat()
        })
        user_quests = db.get_user_quests(user_id)

    return user_quests


def update_quest_progress(db, user_id, quest_type: str, amount: int = 1, extra_data: dict = None):
    """
    Обновляет прогресс квестов пользователя.
    
    quest_type: тип квеста (spin, collect_ticket, arena_battle, arena_win, 
                earn_coins, get_card_rarity, daily_claim, sell_card, buy_market, multispin)
    amount: сколько добавить к прогрессу
    extra_data: доп. данные (например, {"rarity": "epic"} для get_card_rarity)
    """
    user_quests = db.get_user_quests(user_id)
    if not user_quests:
        return

    # Проверяем не новый ли день
    if is_new_day(user_quests.get('last_reset', '')):
        return  # Квесты устарели, при следующем /quests обновятся

    quests = user_quests.get('quests', [])
    changed = False

    for quest in quests:
        if quest.get('claimed', False):
            continue

        if quest.get('type') != quest_type:
            continue

        # Для квеста на редкость карты — проверяем подходит ли редкость
        if quest_type == 'get_card_rarity' and extra_data:
            target_rarities = quest.get('target_rarity', [])
            card_rarity = extra_data.get('rarity', '')
            if card_rarity not in target_rarities:
                continue

        quest['progress'] = quest.get('progress', 0) + amount
        changed = True

    if changed:
        db.set_user_quests(user_id, user_quests)


@router.message(Command("quests"))
async def quests_command(message: Message):
    """Показать ежедневные квесты"""
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI.get('cross', '❌')} Квесты доступны только в группах!")

    user_id = message.from_user.id
    db = get_db(message)

    # Обновляем глобальную БД
    global_db = DatabaseManager.get_global_db()
    if global_db:
        global_db.update_user(user_id, message.from_user.username, message.from_user.first_name)

    user_quests = ensure_user_quests(
        db, user_id,
        message.from_user.username,
        message.from_user.first_name
    )

    quests = user_quests.get('quests', [])

    # Считаем статистику
    total = len(quests)
    completed = sum(1 for q in quests if q.get('progress', 0) >= q.get('target', 1))
    claimed = sum(1 for q in quests if q.get('claimed', False))

    text = f"📋 <b>ЕЖЕДНЕВНЫЕ КВЕСТЫ</b>  ({claimed}/{total} получено)\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━\n\n"

    keyboard_buttons = []

    for i, quest in enumerate(quests):
        quest_id = quest.get('id', f"quest_{i}")
        name = quest.get('name', 'Квест')
        description = quest.get('description', '')
        progress = quest.get('progress', 0)
        target = quest.get('target', 1)
        is_completed = progress >= target
        is_claimed = quest.get('claimed', False)
        reward_text = get_quest_reward_text(quest)

        # Статус иконка
        if is_claimed:
            icon = "✅"
            status = "Получено"
        elif is_completed:
            icon = "🎉"
            status = "Готово!"
        else:
            icon = "⏳"
            bar = get_progress_bar(progress, target)
            status = f"{bar} {min(progress, target)}/{target}"

        text += f"{icon} <b>{name}</b>\n"
        if description:
            text += f"   <i>{description}</i>\n"
        text += f"   {status}\n"
        text += f"   🎁 Награда: {reward_text}\n\n"

        # Кнопка для получения
        if is_completed and not is_claimed:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"🎁 Забрать: {name}",
                    callback_data=f"claimq:{user_id}:{quest_id}"
                )
            ])

    # Кнопка "Забрать всё"
    claimable_count = sum(1 for q in quests if q.get('progress', 0) >= q.get('target', 1) and not q.get('claimed', False))
    if claimable_count > 1:
        keyboard_buttons.insert(0, [
            InlineKeyboardButton(
                text=f"🎁 Забрать всё ({claimable_count})",
                callback_data=f"claimall:{user_id}"
            )
        ])

    # Кнопка обновить
    keyboard_buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"questrefresh:{user_id}")
    ])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None
    await message.reply(text, parse_mode="HTML", reply_markup=reply_markup)


@router.callback_query(F.data.startswith("questrefresh:"))
async def refresh_quests(callback: CallbackQuery):
    """Обновить список квестов"""
    try:
        owner_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)

    if callback.from_user.id != owner_id:
        return await callback.answer("❌ Это не твои квесты!", show_alert=True)

    user_id = callback.from_user.id
    db = get_db(callback)

    user_quests = ensure_user_quests(db, user_id)
    quests = user_quests.get('quests', [])

    total = len(quests)
    claimed = sum(1 for q in quests if q.get('claimed', False))

    text = f"📋 <b>ЕЖЕДНЕВНЫЕ КВЕСТЫ</b>  ({claimed}/{total} получено)\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━\n\n"

    keyboard_buttons = []

    for i, quest in enumerate(quests):
        quest_id = quest.get('id', f"quest_{i}")
        name = quest.get('name', 'Квест')
        description = quest.get('description', '')
        progress = quest.get('progress', 0)
        target = quest.get('target', 1)
        is_completed = progress >= target
        is_claimed = quest.get('claimed', False)
        reward_text = get_quest_reward_text(quest)

        if is_claimed:
            icon = "✅"
            status = "Получено"
        elif is_completed:
            icon = "🎉"
            status = "Готово!"
        else:
            icon = "⏳"
            bar = get_progress_bar(progress, target)
            status = f"{bar} {min(progress, target)}/{target}"

        text += f"{icon} <b>{name}</b>\n"
        if description:
            text += f"   <i>{description}</i>\n"
        text += f"   {status}\n"
        text += f"   🎁 Награда: {reward_text}\n\n"

        if is_completed and not is_claimed:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"🎁 Забрать: {name}",
                    callback_data=f"claimq:{user_id}:{quest_id}"
                )
            ])

    claimable_count = sum(1 for q in quests if q.get('progress', 0) >= q.get('target', 1) and not q.get('claimed', False))
    if claimable_count > 1:
        keyboard_buttons.insert(0, [
            InlineKeyboardButton(
                text=f"🎁 Забрать всё ({claimable_count})",
                callback_data=f"claimall:{user_id}"
            )
        ])

    keyboard_buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"questrefresh:{user_id}")
    ])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except:
        pass
    await callback.answer("🔄 Обновлено!")


@router.callback_query(F.data.startswith("claimq:"))
async def claim_quest_callback(callback: CallbackQuery):
    """Получить награду за один квест"""
    try:
        parts = callback.data.split(":")
        owner_id = int(parts[1])
        quest_id = parts[2]
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка данных!", show_alert=True)

    user_id = callback.from_user.id
    if user_id != owner_id:
        return await callback.answer("❌ Это не твои квесты!", show_alert=True)

    db = get_db(callback)
    user_quests = db.get_user_quests(user_id)

    if not user_quests:
        return await callback.answer("❌ Квесты не найдены!", show_alert=True)

    if is_new_day(user_quests.get('last_reset', '')):
        return await callback.answer("❌ Квесты обновились! Напиши /quests", show_alert=True)

    quests = user_quests.get('quests', [])
    quest = None
    for q in quests:
        if q.get('id') == quest_id:
            quest = q
            break

    if not quest:
        return await callback.answer("❌ Квест не найден!", show_alert=True)

    if quest.get('claimed', False):
        return await callback.answer("❌ Награда уже получена!", show_alert=True)

    if quest.get('progress', 0) < quest.get('target', 1):
        return await callback.answer("❌ Квест ещё не выполнен!", show_alert=True)

    # Выдаём награду
    reward_type = quest.get('reward_type', 'coins')
    reward_amount = quest.get('reward_amount', 0)
    reward_text = ""

    if reward_type == 'coins':
        db.add_coins(user_id, reward_amount)
        reward_text = f"🪙 {reward_amount} монет"
    elif reward_type == 'tickets':
        db.add_tickets(user_id, reward_amount)
        reward_text = f"🎫 {reward_amount} билетов"

    quest['claimed'] = True
    db.set_user_quests(user_id, user_quests)

    await callback.answer(f"🎉 Получено: {reward_text}!", show_alert=True)

    # Обновляем сообщение
    await refresh_quests_message(callback, user_id, db)


@router.callback_query(F.data.startswith("claimall:"))
async def claim_all_quests(callback: CallbackQuery):
    """Забрать все готовые награды"""
    try:
        owner_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        return await callback.answer("❌ Ошибка!", show_alert=True)

    user_id = callback.from_user.id
    if user_id != owner_id:
        return await callback.answer("❌ Это не твои квесты!", show_alert=True)

    db = get_db(callback)
    user_quests = db.get_user_quests(user_id)

    if not user_quests:
        return await callback.answer("❌ Квесты не найдены!", show_alert=True)

    if is_new_day(user_quests.get('last_reset', '')):
        return await callback.answer("❌ Квесты обновились! Напиши /quests", show_alert=True)

    quests = user_quests.get('quests', [])
    total_coins = 0
    total_tickets = 0
    claimed_count = 0

    for quest in quests:
        if quest.get('claimed', False):
            continue
        if quest.get('progress', 0) < quest.get('target', 1):
            continue

        reward_type = quest.get('reward_type', 'coins')
        reward_amount = quest.get('reward_amount', 0)

        if reward_type == 'coins':
            total_coins += reward_amount
        elif reward_type == 'tickets':
            db.add_spin_tickets(user_id, reward_amount)  # если метод называется так

        quest['claimed'] = True
        claimed_count += 1

    if claimed_count == 0:
        return await callback.answer("❌ Нет наград для получения!", show_alert=True)

    # Выдаём всё
    if total_coins > 0:
        db.add_coins(user_id, total_coins)
    if total_tickets > 0:
        db.add_tickets(user_id, total_tickets)

    db.set_user_quests(user_id, user_quests)

    parts = []
    if total_coins > 0:
        parts.append(f"🪙 {total_coins}")
    if total_tickets > 0:
        parts.append(f"🎫 {total_tickets}")

    reward_str = " + ".join(parts)
    await callback.answer(f"🎉 Получено ({claimed_count} квестов): {reward_str}!", show_alert=True)

    await refresh_quests_message(callback, user_id, db)


async def refresh_quests_message(callback: CallbackQuery, user_id: int, db):
    """Обновить сообщение с квестами после получения награды"""
    user_quests = db.get_user_quests(user_id)
    quests = user_quests.get('quests', [])

    total = len(quests)
    claimed = sum(1 for q in quests if q.get('claimed', False))

    text = f"📋 <b>ЕЖЕДНЕВНЫЕ КВЕСТЫ</b>  ({claimed}/{total} получено)\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━\n\n"

    keyboard_buttons = []

    for i, quest in enumerate(quests):
        quest_id = quest.get('id', f"quest_{i}")
        name = quest.get('name', 'Квест')
        description = quest.get('description', '')
        progress = quest.get('progress', 0)
        target = quest.get('target', 1)
        is_completed = progress >= target
        is_claimed = quest.get('claimed', False)
        reward_text = get_quest_reward_text(quest)

        if is_claimed:
            icon = "✅"
            status = "Получено"
        elif is_completed:
            icon = "🎉"
            status = "Готово!"
        else:
            icon = "⏳"
            bar = get_progress_bar(progress, target)
            status = f"{bar} {min(progress, target)}/{target}"

        text += f"{icon} <b>{name}</b>\n"
        if description:
            text += f"   <i>{description}</i>\n"
        text += f"   {status}\n"
        text += f"   🎁 Награда: {reward_text}\n\n"

        if is_completed and not is_claimed:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"🎁 Забрать: {name}",
                    callback_data=f"claimq:{user_id}:{quest_id}"
                )
            ])

    claimable_count = sum(1 for q in quests if q.get('progress', 0) >= q.get('target', 1) and not q.get('claimed', False))
    if claimable_count > 1:
        keyboard_buttons.insert(0, [
            InlineKeyboardButton(
                text=f"🎁 Забрать всё ({claimable_count})",
                callback_data=f"claimall:{user_id}"
            )
        ])

    keyboard_buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"questrefresh:{user_id}")
    ])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except:
        pass