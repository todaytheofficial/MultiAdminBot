# handlers/battle.py
import random
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from config import EMOJI, RARITY_COLORS, RARITY_NAMES, ARENA_SETTINGS
from database import DatabaseManager

router = Router()

active_battles = set()
queue_lock = asyncio.Lock()


def is_group_chat(message: Message) -> bool:
    return message.chat.type in ["group", "supergroup"]


def get_db(message_or_callback):
    if isinstance(message_or_callback, Message):
        return DatabaseManager.get_db(message_or_callback.chat.id)
    elif isinstance(message_or_callback, CallbackQuery):
        return DatabaseManager.get_db(message_or_callback.message.chat.id)
    return None


def get_user_name(user_data: dict) -> str:
    return user_data.get("first_name") or user_data.get("username") or "Игрок"


def find_card_in_collection(cards: list, card_name: str) -> dict | None:
    for card in cards:
        if card["name"] == card_name:
            return card
    return None


def calculate_battle_power(card: dict) -> dict:
    base_attack = card["attack"]
    base_defense = card["defense"]

    luck_min = ARENA_SETTINGS.get("luck_factor_min", 0.85)
    luck_max = ARENA_SETTINGS.get("luck_factor_max", 1.15)

    attack_luck = random.uniform(luck_min, luck_max)
    defense_luck = random.uniform(luck_min, luck_max)

    final_attack = int(base_attack * attack_luck)
    final_defense = int(base_defense * defense_luck)

    crit_chance = ARENA_SETTINGS.get("critical_hit_chance", 0.1)
    crit_multiplier = ARENA_SETTINGS.get("critical_multiplier", 1.5)
    is_crit = random.random() < crit_chance

    if is_crit:
        final_attack = int(final_attack * crit_multiplier)

    dodge_chance = ARENA_SETTINGS.get("dodge_chance", 0.05)
    is_dodge = random.random() < dodge_chance

    return {
        "attack": final_attack,
        "defense": final_defense,
        "is_crit": is_crit,
        "is_dodge": is_dodge,
        "total_power": final_attack + final_defense
    }


def simulate_round(card1: dict, card2: dict, round_num: int) -> dict:
    power1 = calculate_battle_power(card1)
    power2 = calculate_battle_power(card2)

    damage1_to_2 = max(0, power1["attack"] - power2["defense"] // 2)
    damage2_to_1 = max(0, power2["attack"] - power1["defense"] // 2)

    if power2["is_dodge"]:
        damage1_to_2 = 0
    if power1["is_dodge"]:
        damage2_to_1 = 0

    if damage1_to_2 > damage2_to_1:
        winner = 1
    elif damage2_to_1 > damage1_to_2:
        winner = 2
    else:
        if power1["total_power"] > power2["total_power"]:
            winner = 1
        elif power2["total_power"] > power1["total_power"]:
            winner = 2
        else:
            winner = random.choice([1, 2])

    return {
        "round": round_num,
        "card1_power": power1,
        "card2_power": power2,
        "damage1_to_2": damage1_to_2,
        "damage2_to_1": damage2_to_1,
        "winner": winner
    }


def simulate_battle(cards1: list, cards2: list) -> dict:
    battle_log = []
    player1_wins = 0
    player2_wins = 0

    num_rounds = min(len(cards1), len(cards2))

    for i in range(num_rounds):
        round_result = simulate_round(cards1[i], cards2[i], i + 1)
        battle_log.append({
            "card1": cards1[i],
            "card2": cards2[i],
            **round_result
        })

        if round_result["winner"] == 1:
            player1_wins += 1
        else:
            player2_wins += 1

    if player1_wins > player2_wins:
        overall_winner = 1
    elif player2_wins > player1_wins:
        overall_winner = 2
    else:
        overall_winner = random.choice([1, 2])

    return {
        "battle_log": battle_log,
        "player1_wins": player1_wins,
        "player2_wins": player2_wins,
        "overall_winner": overall_winner,
        "total_rounds": num_rounds
    }


def format_battle_log(battle_result: dict, player1_name: str, player2_name: str) -> str:
    text = ""

    for round_data in battle_result["battle_log"]:
        card1 = round_data["card1"]
        card2 = round_data["card2"]
        power1 = round_data["card1_power"]
        power2 = round_data["card2_power"]
        winner = round_data["winner"]

        rarity1 = RARITY_COLORS.get(card1["rarity"], "⚪")
        rarity2 = RARITY_COLORS.get(card2["rarity"], "⚪")

        text += f"\n<b>Раунд {round_data['round']}</b>\n"

        crit1 = " 💥КРИТ!" if power1["is_crit"] else ""
        dodge1 = " 💨УВОРОТ!" if power1["is_dodge"] else ""
        text += f"{rarity1} {card1['emoji']} {card1['name']}{crit1}{dodge1}\n"
        text += f"   ⚔️{power1['attack']} 🛡️{power1['defense']}\n"

        text += f"   ⚡ VS ⚡\n"

        crit2 = " 💥КРИТ!" if power2["is_crit"] else ""
        dodge2 = " 💨УВОРОТ!" if power2["is_dodge"] else ""
        text += f"{rarity2} {card2['emoji']} {card2['name']}{crit2}{dodge2}\n"
        text += f"   ⚔️{power2['attack']} 🛡️{power2['defense']}\n"

        winner_name = player1_name if winner == 1 else player2_name
        text += f"   🏆 Победа: <b>{winner_name}</b>\n"

    return text


def get_best_cards(cards: list, count: int = 3) -> list:
    sorted_cards = sorted(cards, key=lambda x: x["attack"] + x["defense"], reverse=True)
    return sorted_cards[:count]


# ================== КОМАНДЫ АРЕНЫ ==================

@router.message(Command("arena"))
async def arena_command(message: Message):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Арена работает только в группах!")

    user_id = message.from_user.id
    db = get_db(message)

    if not db.get_user(user_id):
        db.create_user(user_id, message.from_user.username, message.from_user.first_name)

    DatabaseManager.get_global_db().update_user(
        user_id, message.from_user.username, message.from_user.first_name
    )

    user = db.get_user(user_id)
    cards = user.get("cards", [])
    cards_needed = ARENA_SETTINGS.get("cards_per_battle", 3)

    if len(cards) < cards_needed:
        return await message.reply(
            f"⚔️ <b>АРЕНА</b>\n\n"
            f"Для участия нужно минимум <b>{cards_needed}</b> карты!\n"
            f"У тебя: <b>{len(cards)}</b>\n\n"
            f"💡 /spin — получить карты",
            parse_mode="HTML"
        )

    if db.is_in_queue(user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Покинуть очередь", callback_data="arena_leave")]
        ])
        return await message.reply(
            f"⏳ <b>Ты уже в очереди!</b>\n\nОжидание противника...",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    arena_cards = db.get_arena_cards(user_id)

    if len(arena_cards) < cards_needed:
        best_cards = get_best_cards(cards, cards_needed)
        arena_cards = [c["name"] for c in best_cards]
        db.set_arena_cards(user_id, arena_cards)

    valid_cards = []
    for card_name in arena_cards:
        card = find_card_in_collection(cards, card_name)
        if card:
            valid_cards.append(card_name)

    if len(valid_cards) < cards_needed:
        best_cards = get_best_cards(cards, cards_needed)
        arena_cards = [c["name"] for c in best_cards]
        db.set_arena_cards(user_id, arena_cards)

    db.join_arena_queue(user_id, arena_cards)

    cards_text = ""
    total_power = 0
    for card_name in arena_cards:
        card = find_card_in_collection(cards, card_name)
        if card:
            power = card["attack"] + card["defense"]
            total_power += power
            rarity_color = RARITY_COLORS.get(card["rarity"], "⚪")
            cards_text += f"{rarity_color} {card['emoji']} {card['name']} (💪{power})\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Сменить колоду", callback_data="arena_change_deck")],
        [InlineKeyboardButton(text="❌ Покинуть очередь", callback_data="arena_leave")]
    ])

    queue = db.get_arena_queue()
    queue_count = len(queue)

    await message.reply(
        f"⚔️ <b>АРЕНА</b>\n\n"
        f"✅ Ты в очереди!\n"
        f"👥 В очереди: <b>{queue_count}</b>\n\n"
        f"<b>Твоя колода:</b>\n{cards_text}"
        f"💪 Общая сила: <b>{total_power}</b>\n\n"
        f"⏳ Ожидание противника...",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.message(Command("setdeck"))
async def set_deck_command(message: Message):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    user_id = message.from_user.id
    db = get_db(message)

    if not db.get_user(user_id):
        db.create_user(user_id, message.from_user.username, message.from_user.first_name)

    user = db.get_user(user_id)
    cards = user.get("cards", [])
    cards_needed = ARENA_SETTINGS.get("cards_per_battle", 3)

    if len(cards) < cards_needed:
        return await message.reply(
            f"🃏 <b>КОЛОДА ДЛЯ АРЕНЫ</b>\n\n"
            f"Нужно минимум <b>{cards_needed}</b> карты!\n"
            f"У тебя: <b>{len(cards)}</b>",
            parse_mode="HTML"
        )

    unique_cards = {}
    for card in cards:
        name = card["name"]
        if name not in unique_cards:
            unique_cards[name] = card

    sorted_cards = sorted(unique_cards.values(), key=lambda x: x["attack"] + x["defense"], reverse=True)

    keyboard_buttons = []
    current_deck = db.get_arena_cards(user_id)

    for card in sorted_cards[:12]:
        power = card["attack"] + card["defense"]
        rarity_color = RARITY_COLORS.get(card["rarity"], "⚪")
        is_selected = card["name"] in current_deck
        check = "✅ " if is_selected else ""
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{check}{rarity_color} {card['emoji']} {card['name']} (💪{power})",
                callback_data=f"deck_toggle:{card['name'][:30]}"
            )
        ])

    keyboard_buttons.append([InlineKeyboardButton(text="🔝 Авто-выбор лучших", callback_data="deck_auto")])
    keyboard_buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data="deck_done")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    current_text = ""
    if current_deck:
        current_text = f"\n<b>Текущая колода ({len(current_deck)}/{cards_needed}):</b>\n"
        for card_name in current_deck:
            card = find_card_in_collection(cards, card_name)
            if card:
                rarity_color = RARITY_COLORS.get(card["rarity"], "⚪")
                current_text += f"{rarity_color} {card['emoji']} {card['name']}\n"

    await message.reply(
        f"🃏 <b>ВЫБОР КОЛОДЫ ДЛЯ АРЕНЫ</b>\n\n"
        f"Выбери <b>{cards_needed}</b> карты для боёв:{current_text}",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("deck_toggle:"))
async def toggle_deck_card(callback: CallbackQuery):
    card_name = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    db = get_db(callback)

    user = db.get_user(user_id)
    if not user:
        return await callback.answer("Ошибка!", show_alert=True)

    cards = user.get("cards", [])
    current_deck = db.get_arena_cards(user_id)
    cards_needed = ARENA_SETTINGS.get("cards_per_battle", 3)

    card = find_card_in_collection(cards, card_name)
    if not card:
        return await callback.answer("У тебя нет этой карты!", show_alert=True)

    if card_name in current_deck:
        current_deck.remove(card_name)
        await callback.answer(f"❌ {card_name} убрана")
    else:
        if len(current_deck) >= cards_needed:
            return await callback.answer(f"Колода полная!", show_alert=True)
        current_deck.append(card_name)
        await callback.answer(f"✅ {card_name} добавлена")

    db.set_arena_cards(user_id, current_deck)
    await _refresh_deck_message(callback, user_id, db)


async def _refresh_deck_message(callback: CallbackQuery, user_id: int, db):
    user = db.get_user(user_id)
    cards = user.get("cards", [])
    current_deck = db.get_arena_cards(user_id)
    cards_needed = ARENA_SETTINGS.get("cards_per_battle", 3)

    unique_cards = {}
    for c in cards:
        name = c["name"]
        if name not in unique_cards:
            unique_cards[name] = c

    sorted_cards = sorted(unique_cards.values(), key=lambda x: x["attack"] + x["defense"], reverse=True)

    keyboard_buttons = []
    for c in sorted_cards[:12]:
        power = c["attack"] + c["defense"]
        rarity_color = RARITY_COLORS.get(c["rarity"], "⚪")
        is_selected = c["name"] in current_deck
        check = "✅ " if is_selected else ""
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{check}{rarity_color} {c['emoji']} {c['name']} (💪{power})",
                callback_data=f"deck_toggle:{c['name'][:30]}"
            )
        ])

    keyboard_buttons.append([InlineKeyboardButton(text="🔝 Авто-выбор лучших", callback_data="deck_auto")])
    keyboard_buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data="deck_done")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    current_text = ""
    if current_deck:
        current_text = f"\n<b>Текущая колода ({len(current_deck)}/{cards_needed}):</b>\n"
        for cn in current_deck:
            c = find_card_in_collection(cards, cn)
            if c:
                rarity_color = RARITY_COLORS.get(c["rarity"], "⚪")
                current_text += f"{rarity_color} {c['emoji']} {c['name']}\n"

    try:
        await callback.message.edit_text(
            f"🃏 <b>ВЫБОР КОЛОДЫ ДЛЯ АРЕНЫ</b>\n\n"
            f"Выбери <b>{cards_needed}</b> карты для боёв:{current_text}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception:
        pass


@router.callback_query(F.data == "deck_auto")
async def auto_select_deck(callback: CallbackQuery):
    user_id = callback.from_user.id
    db = get_db(callback)

    user = db.get_user(user_id)
    if not user:
        return await callback.answer("Ошибка!", show_alert=True)

    cards = user.get("cards", [])
    cards_needed = ARENA_SETTINGS.get("cards_per_battle", 3)

    best_cards = get_best_cards(cards, cards_needed)
    arena_cards = [c["name"] for c in best_cards]
    db.set_arena_cards(user_id, arena_cards)

    await callback.answer(f"✅ Выбраны {cards_needed} лучших!")
    await _refresh_deck_message(callback, user_id, db)


@router.callback_query(F.data == "deck_done")
async def deck_done(callback: CallbackQuery):
    user_id = callback.from_user.id
    db = get_db(callback)

    current_deck = db.get_arena_cards(user_id)
    cards_needed = ARENA_SETTINGS.get("cards_per_battle", 3)

    if len(current_deck) < cards_needed:
        return await callback.answer(f"Выбери ещё {cards_needed - len(current_deck)} карт!", show_alert=True)

    user = db.get_user(user_id)
    cards = user.get("cards", [])

    cards_text = ""
    total_power = 0
    for card_name in current_deck:
        card = find_card_in_collection(cards, card_name)
        if card:
            power = card["attack"] + card["defense"]
            total_power += power
            rarity_color = RARITY_COLORS.get(card["rarity"], "⚪")
            cards_text += f"{rarity_color} {card['emoji']} {card['name']} (💪{power})\n"

    await callback.message.edit_text(
        f"✅ <b>КОЛОДА СОХРАНЕНА!</b>\n\n"
        f"<b>Твоя колода:</b>\n{cards_text}"
        f"💪 Общая сила: <b>{total_power}</b>\n\n"
        f"⚔️ /arena — на арену!",
        parse_mode="HTML"
    )
    await callback.answer("Колода сохранена!")


@router.message(Command("mydeck"))
async def show_my_deck(message: Message):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    user_id = message.from_user.id
    db = get_db(message)

    user = db.get_user(user_id)
    if not user:
        return await message.reply("Сначала используй /spin!")

    cards = user.get("cards", [])
    arena_cards = db.get_arena_cards(user_id)
    cards_needed = ARENA_SETTINGS.get("cards_per_battle", 3)

    if not arena_cards:
        return await message.reply(
            f"🃏 <b>ТВОЯ КОЛОДА</b>\n\nКолода не выбрана!\n\n💡 /setdeck — выбрать карты",
            parse_mode="HTML"
        )

    cards_text = ""
    total_power = 0
    for card_name in arena_cards:
        card = find_card_in_collection(cards, card_name)
        if card:
            power = card["attack"] + card["defense"]
            total_power += power
            rarity_color = RARITY_COLORS.get(card["rarity"], "⚪")
            cards_text += f"{rarity_color} {card['emoji']} {card['name']} (💪{power})\n"

    await message.reply(
        f"🃏 <b>ТВОЯ КОЛОДА ({len(arena_cards)}/{cards_needed})</b>\n\n"
        f"{cards_text}"
        f"💪 Общая сила: <b>{total_power}</b>\n\n"
        f"⚔️ /arena — на арену!\n🔄 /setdeck — изменить",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "arena_leave")
async def leave_arena_queue(callback: CallbackQuery):
    user_id = callback.from_user.id
    db = get_db(callback)

    if not db.is_in_queue(user_id):
        return await callback.answer("Ты не в очереди!", show_alert=True)

    db.leave_arena_queue(user_id)

    await callback.message.edit_text(
        f"❌ <b>Ты покинул очередь</b>\n\n⚔️ /arena — вернуться",
        parse_mode="HTML"
    )
    await callback.answer("Очередь покинута")


@router.callback_query(F.data == "arena_change_deck")
async def change_deck_from_queue(callback: CallbackQuery):
    user_id = callback.from_user.id
    db = get_db(callback)

    db.leave_arena_queue(user_id)
    await callback.answer("Выбери новую колоду")
    await _refresh_deck_message(callback, user_id, db)


# ================== ПРОВЕРКА ОЧЕРЕДИ ==================

async def check_queue_periodically(bot: Bot):
    while True:
        try:
            for group_db in DatabaseManager.get_all_group_dbs():
                await process_arena_queue(bot, group_db)
        except Exception as e:
            print(f"Error in arena queue check: {e}")
        await asyncio.sleep(5)


async def process_arena_queue(bot: Bot, db):
    async with queue_lock:
        queue = db.get_arena_queue()

        if len(queue) < 2:
            return

        player1_data = queue[0]
        player2_data = queue[1]

        player1_id = player1_data["user_id"]
        player2_id = player2_data["user_id"]

        battle_key = tuple(sorted([player1_id, player2_id]))
        if battle_key in active_battles:
            return

        active_battles.add(battle_key)

    try:
        db.leave_arena_queue(player1_id)
        db.leave_arena_queue(player2_id)

        player1 = db.get_user(player1_id)
        player2 = db.get_user(player2_id)

        if not player1 or not player2:
            return

        player1_name = get_user_name(player1)
        player2_name = get_user_name(player2)

        player1_card_names = player1_data.get("cards", [])
        player2_card_names = player2_data.get("cards", [])

        player1_cards = []
        player2_cards = []

        for name in player1_card_names:
            card = find_card_in_collection(player1.get("cards", []), name)
            if card:
                player1_cards.append(card)

        for name in player2_card_names:
            card = find_card_in_collection(player2.get("cards", []), name)
            if card:
                player2_cards.append(card)

        if not player1_cards or not player2_cards:
            return

        battle_result = simulate_battle(player1_cards, player2_cards)

        winner_id = player1_id if battle_result["overall_winner"] == 1 else player2_id
        loser_id = player2_id if battle_result["overall_winner"] == 1 else player1_id
        winner_name = player1_name if battle_result["overall_winner"] == 1 else player2_name
        loser_name = player2_name if battle_result["overall_winner"] == 1 else player1_name

        rating_win = ARENA_SETTINGS.get("rating_win_base", 25)
        rating_lose = ARENA_SETTINGS.get("rating_lose_base", 15)
        coins_win = ARENA_SETTINGS.get("coins_per_win", 15)
        coins_lose = ARENA_SETTINGS.get("coins_per_lose", 3)

        loser_had_shield = db.use_shield(loser_id)
        if loser_had_shield:
            rating_lose = 0

        db.update_rating(winner_id, rating_win, True)
        db.update_rating(loser_id, -rating_lose, False)
        db.add_coins(winner_id, coins_win)
        db.add_coins(loser_id, coins_lose)

        text = f"⚔️ <b>БОЙ ЗАВЕРШЁН!</b>\n\n"
        text += f"👤 <b>{player1_name}</b> VS <b>{player2_name}</b> 👤\n"
        text += f"━━━━━━━━━━━━━━━━━━━━"
        text += format_battle_log(battle_result, player1_name, player2_name)
        text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 <b>СЧЁТ:</b> {battle_result['player1_wins']} - {battle_result['player2_wins']}\n\n"
        text += f"🏆 <b>ПОБЕДИТЕЛЬ: {winner_name}!</b>\n\n"
        text += f"<b>Награды:</b>\n"
        text += f"👑 {winner_name}: +{rating_win}⭐ +{coins_win}🪙\n"

        if loser_had_shield:
            text += f"🛡️ {loser_name}: 0⭐ (щит!) +{coins_lose}🪙\n"
        else:
            text += f"💔 {loser_name}: -{rating_lose}⭐ +{coins_lose}🪙\n"

        try:
            await bot.send_message(db.chat_id, text, parse_mode="HTML")
        except Exception as e:
            print(f"Error sending battle result: {e}")

    finally:
        active_battles.discard(battle_key)