# handlers/upgrade.py
import random
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from config import EMOJI, CARDS, RARITY_NAMES, RARITY_COLORS
from database import DatabaseManager

router = Router()
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════
#                   НАСТРОЙКИ
# ══════════════════════════════════════════════════

# Шансы апгрейда в зависимости от количества карт
UPGRADE_CHANCES = {
    3: 10.0,
    4: 12.5,
    5: 15.0,
    6: 20.0,
    7: 22.5,
    8: 25.0,
    9: 30.0,
    10: 40.0,
}

# Порядок редкостей (от низшей к высшей)
RARITY_ORDER = ["common", "rare", "epic", "legendary", "mythic", "special", "mega"]

# Какая редкость во что апгрейдится
UPGRADE_MAP = {
    "common": "rare",
    "rare": "epic",
    "epic": "legendary",
    "legendary": "mythic",
    "mythic": "special",
    "special": "mega",
}

# Стоимость апгрейда в монетах (защита от дюпа денег)
UPGRADE_COST = {
    "common": 0,        # common → rare: бесплатно
    "rare": 10,         # rare → epic: 10 монет
    "epic": 50,         # epic → legendary: 50 монет
    "legendary": 150,   # legendary → mythic: 150 монет
    "mythic": 500,      # mythic → special: 500 монет
    "special": 2000,    # special → mega: 2000 монет
}


# ══════════════════════════════════════════════════
#                    HELPERS
# ══════════════════════════════════════════════════

def is_group(msg):
    return msg.chat.type in ["group", "supergroup"]


def get_db(event):
    if isinstance(event, CallbackQuery):
        return DatabaseManager.get_db(event.message.chat.id)
    return DatabaseManager.get_db(event.chat.id)


def get_user_cards_by_rarity(user, rarity: str) -> int:
    """Считает количество карт определённой редкости у пользователя"""
    cards = user.get("cards", [])
    return sum(1 for c in cards if c.get("rarity") == rarity)


def get_random_card_of_rarity(rarity: str):
    """Возвращает случайную карту определённой редкости"""
    cards = [c for c in CARDS if c["rarity"] == rarity]
    if not cards:
        return None
    return random.choice(cards)


# ══════════════════════════════════════════════════
#                 UPGRADE COMMAND
# ══════════════════════════════════════════════════

@router.message(Command("upgrade"))
async def cmd_upgrade(msg: Message):
    """Главное меню апгрейда"""
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    
    db = get_db(msg)
    uid = msg.from_user.id
    
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    
    user = db.get_user(uid)
    cards = user.get("cards", [])
    
    if not cards:
        return await msg.reply(
            f"{EMOJI['cross']} У тебя нет карт!\n"
            f"💡 Используй /spin чтобы получить карты.",
            parse_mode="HTML"
        )
    
    # Считаем карты по редкостям
    rarity_counts = {}
    for c in cards:
        r = c.get("rarity", "common")
        rarity_counts[r] = rarity_counts.get(r, 0) + 1
    
    txt = (
        "🔮 <b>УЛУЧШЕНИЕ КАРТ</b>\n\n"
        "Закинь карты одной редкости — и с шансом\n"
        "получи карту <b>следующей</b> редкости!\n\n"
        "<b>📊 Шансы:</b>\n"
        "├ 3 карты → 10%\n"
        "├ 4 карты → 12.5%\n"
        "├ 5 карт → 15%\n"
        "├ 6 карт → 20%\n"
        "├ 7 карт → 22.5%\n"
        "├ 8 карт → 25%\n"
        "├ 9 карт → 30%\n"
        "└ 10 карт → 40%\n\n"
        "⚠️ <b>При неудаче карты сгорают!</b>\n\n"
        "Выбери редкость для улучшения:"
    )
    
    buttons = []
    for rarity in RARITY_ORDER:
        if rarity in UPGRADE_MAP and rarity in rarity_counts:
            count = rarity_counts[rarity]
            target = UPGRADE_MAP[rarity]
            cost = UPGRADE_COST.get(rarity, 0)
            
            rc = RARITY_COLORS.get(rarity, "⚪")
            target_name = RARITY_NAMES.get(target, target)
            
            status = "✅" if count >= 3 else "❌"
            cost_text = f" | 💰{cost}" if cost > 0 else ""
            
            buttons.append([InlineKeyboardButton(
                text=f"{status} {rc} {RARITY_NAMES.get(rarity, rarity)} ({count}) → {target_name}{cost_text}",
                callback_data=f"upg_select:{rarity}"
            )])
    
    if not buttons:
        return await msg.reply(
            f"🔮 <b>УЛУЧШЕНИЕ КАРТ</b>\n\n"
            f"{EMOJI['cross']} У тебя нет карт, которые можно улучшить!\n"
            f"(Карты редкости <b>Mega</b> — максимальные)",
            parse_mode="HTML"
        )
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await msg.reply(txt, parse_mode="HTML", reply_markup=kb)


# ══════════════════════════════════════════════════
#             ВЫБОР РЕДКОСТИ
# ══════════════════════════════════════════════════

@router.callback_query(F.data.startswith("upg_select:"))
async def cb_upgrade_select(cb: CallbackQuery):
    """Выбрана редкость — показываем варианты количества"""
    rarity = cb.data.split(":")[1]
    
    if rarity not in UPGRADE_MAP:
        return await cb.answer("❌ Эту редкость нельзя улучшить!", show_alert=True)
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Пользователь не найден!", show_alert=True)
    
    count = get_user_cards_by_rarity(user, rarity)
    
    if count < 3:
        return await cb.answer(
            f"❌ Нужно минимум 3 карты! У тебя: {count}",
            show_alert=True
        )
    
    target = UPGRADE_MAP[rarity]
    cost = UPGRADE_COST.get(rarity, 0)
    coins = user.get("coins", 0)
    
    rc = RARITY_COLORS.get(rarity, "⚪")
    tc = RARITY_COLORS.get(target, "⚪")
    
    txt = (
        f"🔮 <b>УЛУЧШЕНИЕ</b>\n\n"
        f"📦 {rc} <b>{RARITY_NAMES.get(rarity, rarity)}</b> → {tc} <b>{RARITY_NAMES.get(target, target)}</b>\n\n"
        f"🃏 Карт этой редкости: <b>{count}</b>\n"
    )
    
    if cost > 0:
        txt += f"💰 Стоимость: <b>{cost}</b> монет"
        if coins < cost:
            txt += f" ❌ <i>(у тебя {coins})</i>"
        else:
            txt += f" ✅"
        txt += "\n"
    
    txt += f"\n<b>Выбери количество карт:</b>\n"
    
    # Кнопки с количеством
    buttons = []
    row = []
    max_cards = min(count, 10)
    
    for n in range(3, max_cards + 1):
        chance = UPGRADE_CHANCES.get(n, 0)
        row.append(InlineKeyboardButton(
            text=f"{n} карт ({chance}%)",
            callback_data=f"upg_confirm:{rarity}:{n}"
        ))
        # По 2 кнопки в ряд
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="upg_back")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await cb.answer()


# ══════════════════════════════════════════════════
#             ПОДТВЕРЖДЕНИЕ АПГРЕЙДА
# ══════════════════════════════════════════════════

@router.callback_query(F.data.startswith("upg_confirm:"))
async def cb_upgrade_confirm(cb: CallbackQuery):
    """Подтверждение перед апгрейдом"""
    parts = cb.data.split(":")
    rarity = parts[1]
    count = int(parts[2])
    
    if rarity not in UPGRADE_MAP:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    if count < 3 or count > 10:
        return await cb.answer("❌ Неверное количество!", show_alert=True)
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    available = get_user_cards_by_rarity(user, rarity)
    if available < count:
        return await cb.answer(f"❌ Недостаточно карт! У тебя: {available}", show_alert=True)
    
    cost = UPGRADE_COST.get(rarity, 0)
    coins = user.get("coins", 0)
    
    if cost > 0 and coins < cost:
        return await cb.answer(f"❌ Не хватает монет! Нужно: {cost}, у тебя: {coins}", show_alert=True)
    
    target = UPGRADE_MAP[rarity]
    chance = UPGRADE_CHANCES.get(count, 10.0)
    
    rc = RARITY_COLORS.get(rarity, "⚪")
    tc = RARITY_COLORS.get(target, "⚪")
    
    txt = (
        f"⚠️ <b>ПОДТВЕРЖДЕНИЕ</b>\n\n"
        f"🃏 Сгорит: <b>{count}x</b> {rc} {RARITY_NAMES.get(rarity, rarity)}\n"
    )
    
    if cost > 0:
        txt += f"💰 Стоимость: <b>{cost}</b> монет\n"
    
    txt += (
        f"🎯 Шанс: <b>{chance}%</b>\n"
        f"🎁 Награда: <b>1x</b> {tc} {RARITY_NAMES.get(target, target)}\n\n"
        f"❗ <b>При неудаче карты сгорают!</b>\n\n"
        f"Ты уверен?"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Улучшить!",
                callback_data=f"upg_go:{rarity}:{count}"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"upg_select:{rarity}"
            )
        ]
    ])
    
    try:
        await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await cb.answer()


# ══════════════════════════════════════════════════
#               ВЫПОЛНЕНИЕ АПГРЕЙДА
# ══════════════════════════════════════════════════

@router.callback_query(F.data.startswith("upg_go:"))
async def cb_upgrade_go(cb: CallbackQuery):
    """Выполняем апгрейд!"""
    parts = cb.data.split(":")
    rarity = parts[1]
    count = int(parts[2])
    
    if rarity not in UPGRADE_MAP:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    if count < 3 or count > 10:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    # Финальные проверки
    available = get_user_cards_by_rarity(user, rarity)
    if available < count:
        return await cb.answer(f"❌ Недостаточно карт! У тебя: {available}", show_alert=True)
    
    cost = UPGRADE_COST.get(rarity, 0)
    coins = user.get("coins", 0)
    
    if cost > 0 and coins < cost:
        return await cb.answer(f"❌ Не хватает монет!", show_alert=True)
    
    target = UPGRADE_MAP[rarity]
    chance = UPGRADE_CHANCES.get(count, 10.0)
    
    # === ЗАБИРАЕМ РЕСУРСЫ ===
    
    # Снимаем монеты
    if cost > 0:
        if not db.remove_coins(uid, cost):
            return await cb.answer("❌ Не хватает монет!", show_alert=True)
    
    # Удаляем карты
    if not db.remove_cards_by_rarity(uid, rarity, count):
        # Возвращаем монеты если карты не удалились
        if cost > 0:
            db.add_coins(uid, cost)
        return await cb.answer("❌ Ошибка удаления карт!", show_alert=True)
    
    # === КРУТИМ РУЛЕТКУ ===
    
    roll = random.uniform(0, 100)
    success = roll <= chance
    
    rc = RARITY_COLORS.get(rarity, "⚪")
    tc = RARITY_COLORS.get(target, "⚪")
    
    if success:
        # Получаем случайную карту целевой редкости
        new_card = get_random_card_of_rarity(target)
        
        if not new_card:
            # Фоллбэк — если нет карт такой редкости
            if cost > 0:
                db.add_coins(uid, cost)
            return await cb.answer("❌ Нет карт этой редкости в базе!", show_alert=True)
        
        # Добавляем новую карту
        db.add_card(uid, {
            "name": new_card["name"],
            "rarity": new_card["rarity"],
            "attack": new_card["attack"],
            "defense": new_card["defense"],
            "emoji": new_card["emoji"],
            "obtained_at": datetime.now().isoformat(),
            "source": "upgrade"
        })
        
        power = new_card["attack"] + new_card["defense"]
        
        txt = (
            f"🎉🎉🎉 <b>УСПЕХ!</b> 🎉🎉🎉\n\n"
            f"🔮 Улучшение прошло успешно!\n\n"
            f"📦 Потрачено: <b>{count}x</b> {rc} {RARITY_NAMES.get(rarity, rarity)}\n"
        )
        
        if cost > 0:
            txt += f"💰 Стоимость: <b>{cost}</b> монет\n"
        
        txt += (
            f"\n🎁 <b>Получена карта:</b>\n"
            f"{tc} {new_card['emoji']} <b>{new_card['name']}</b>\n"
            f"├ ⚔️ Атака: {new_card['attack']}\n"
            f"├ 🛡️ Защита: {new_card['defense']}\n"
            f"└ 💪 Сила: {power}\n\n"
            f"🎯 Шанс был: <b>{chance}%</b> | Выпало: <b>{roll:.1f}</b>"
        )
    
    else:
        txt = (
            f"💥💥💥 <b>НЕУДАЧА!</b> 💥💥💥\n\n"
            f"🔮 Улучшение провалилось...\n\n"
            f"🗑️ Потеряно: <b>{count}x</b> {rc} {RARITY_NAMES.get(rarity, rarity)}\n"
        )
        
        if cost > 0:
            txt += f"💰 Потрачено: <b>{cost}</b> монет\n"
        
        txt += (
            f"\n🎯 Шанс был: <b>{chance}%</b> | Выпало: <b>{roll:.1f}</b>\n\n"
            f"💡 <i>Попробуй использовать больше карт\n"
            f"для повышения шанса!</i>"
        )
    
    # Кнопка "ещё раз"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔮 Улучшить ещё", callback_data=f"upg_select:{rarity}")],
        [InlineKeyboardButton(text="📋 Мои карты", callback_data="cards_r:all")]
    ])
    
    try:
        await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await cb.answer()


# ══════════════════════════════════════════════════
#                  КНОПКА НАЗАД
# ══════════════════════════════════════════════════

@router.callback_query(F.data == "upg_back")
async def cb_upgrade_back(cb: CallbackQuery):
    """Возврат в главное меню апгрейда"""
    db = get_db(cb)
    uid = cb.from_user.id
    user = db.get_user(uid)
    
    if not user:
        return await cb.answer("❌ Ошибка!", show_alert=True)
    
    # Считаем карты по редкостям
    cards = user.get("cards", [])
    rarity_counts = {}
    for c in cards:
        r = c.get("rarity", "common")
        rarity_counts[r] = rarity_counts.get(r, 0) + 1
    
    txt = (
        "🔮 <b>УЛУЧШЕНИЕ КАРТ</b>\n\n"
        "Закинь карты одной редкости — и с шансом\n"
        "получи карту <b>следующей</b> редкости!\n\n"
        "<b>📊 Шансы:</b>\n"
        "├ 3 карты → 10%\n"
        "├ 4 карты → 12.5%\n"
        "├ 5 карт → 15%\n"
        "├ 6 карт → 20%\n"
        "├ 7 карт → 22.5%\n"
        "├ 8 карт → 25%\n"
        "├ 9 карт → 30%\n"
        "└ 10 карт → 40%\n\n"
        "⚠️ <b>При неудаче карты сгорают!</b>\n\n"
        "Выбери редкость для улучшения:"
    )
    
    buttons = []
    for rarity in RARITY_ORDER:
        if rarity in UPGRADE_MAP and rarity in rarity_counts:
            count = rarity_counts[rarity]
            target = UPGRADE_MAP[rarity]
            cost = UPGRADE_COST.get(rarity, 0)
            
            rc = RARITY_COLORS.get(rarity, "⚪")
            target_name = RARITY_NAMES.get(target, target)
            
            status = "✅" if count >= 3 else "❌"
            cost_text = f" | 💰{cost}" if cost > 0 else ""
            
            buttons.append([InlineKeyboardButton(
                text=f"{status} {rc} {RARITY_NAMES.get(rarity, rarity)} ({count}) → {target_name}{cost_text}",
                callback_data=f"upg_select:{rarity}"
            )])
    
    if not buttons:
        txt += "\n❌ Нет карт для улучшения!"
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    
    try:
        await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await cb.answer()