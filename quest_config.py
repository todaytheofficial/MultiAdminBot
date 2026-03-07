# quest_config.py
import random
from datetime import datetime, date

# Все доступные квесты
ALL_QUESTS = [
    {
        "id": "spin_3",
        "name": "🎰 Крутилка",
        "description": "Используй 3 спина",
        "type": "spin",
        "target": 3,
        "reward_type": "coins",
        "reward_amount": 50
    },
    {
        "id": "spin_7",
        "name": "🎰 Спин-мастер",
        "description": "Используй 7 спинов",
        "type": "spin",
        "target": 7,
        "reward_type": "coins",
        "reward_amount": 120
    },
    {
        "id": "spin_15",
        "name": "🎰 Спинатор",
        "description": "Используй 15 спинов",
        "type": "spin",
        "target": 15,
        "reward_type": "tickets",
        "reward_amount": 3
    },
    {
        "id": "collect_ticket_3",
        "name": "🎫 Собиратель билетов",
        "description": "Получи 3 бесплатных билета",
        "type": "collect_ticket",
        "target": 3,
        "reward_type": "coins",
        "reward_amount": 40
    },
    {
        "id": "collect_ticket_5",
        "name": "🎫 Билетный магнат",
        "description": "Получи 5 бесплатных билетов",
        "type": "collect_ticket",
        "target": 5,
        "reward_type": "coins",
        "reward_amount": 80
    },
    {
        "id": "arena_1",
        "name": "⚔️ Боец",
        "description": "Сыграй 1 бой на арене",
        "type": "arena_battle",
        "target": 1,
        "reward_type": "coins",
        "reward_amount": 60
    },
    {
        "id": "arena_3",
        "name": "⚔️ Гладиатор",
        "description": "Сыграй 3 боя на арене",
        "type": "arena_battle",
        "target": 3,
        "reward_type": "coins",
        "reward_amount": 150
    },
    {
        "id": "arena_win_1",
        "name": "🏆 Победитель",
        "description": "Выиграй 1 бой на арене",
        "type": "arena_win",
        "target": 1,
        "reward_type": "coins",
        "reward_amount": 80
    },
    {
        "id": "arena_win_3",
        "name": "🏆 Чемпион дня",
        "description": "Выиграй 3 боя на арене",
        "type": "arena_win",
        "target": 3,
        "reward_type": "tickets",
        "reward_amount": 2
    },
    {
        "id": "earn_coins_100",
        "name": "🪙 Копилка",
        "description": "Заработай 100 монет",
        "type": "earn_coins",
        "target": 100,
        "reward_type": "tickets",
        "reward_amount": 1
    },
    {
        "id": "earn_coins_300",
        "name": "🪙 Банкир",
        "description": "Заработай 300 монет",
        "type": "earn_coins",
        "target": 300,
        "reward_type": "tickets",
        "reward_amount": 3
    },
    {
        "id": "get_rare",
        "name": "💎 Редкая находка",
        "description": "Получи карту Rare или выше",
        "type": "get_card_rarity",
        "target": 1,
        "target_rarity": ["rare", "epic", "legendary", "mythic", "special", "mega", "limited"],
        "reward_type": "coins",
        "reward_amount": 60
    },
    {
        "id": "get_epic",
        "name": "💜 Эпическая удача",
        "description": "Получи карту Epic или выше",
        "type": "get_card_rarity",
        "target": 1,
        "target_rarity": ["epic", "legendary", "mythic", "special", "mega", "limited"],
        "reward_type": "coins",
        "reward_amount": 150
    },
    {
        "id": "daily_claim",
        "name": "📅 Ежедневка",
        "description": "Забери ежедневную награду",
        "type": "daily_claim",
        "target": 1,
        "reward_type": "coins",
        "reward_amount": 30
    },
    {
        "id": "sell_card_1",
        "name": "📤 Торговец",
        "description": "Продай 1 карту (рынок или быстрая)",
        "type": "sell_card",
        "target": 1,
        "reward_type": "coins",
        "reward_amount": 40
    },
    {
        "id": "sell_card_3",
        "name": "📤 Барыга",
        "description": "Продай 3 карты",
        "type": "sell_card",
        "target": 3,
        "reward_type": "tickets",
        "reward_amount": 1
    },
    {
        "id": "buy_market_1",
        "name": "🛒 Покупатель",
        "description": "Купи что-нибудь в магазине",
        "type": "buy_market",
        "target": 1,
        "reward_type": "coins",
        "reward_amount": 50
    },
    {
        "id": "multispin_1",
        "name": "🎰 Мультиспин",
        "description": "Используй мультиспин",
        "type": "multispin",
        "target": 1,
        "reward_type": "coins",
        "reward_amount": 70
    },
]

QUESTS_PER_DAY = 4


def get_daily_quests(seed=None):
    """Генерирует случайный набор квестов на день"""
    if seed is None:
        seed = date.today().isoformat()
    
    rng = random.Random(seed)
    
    # Выбираем квесты разных типов чтобы было разнообразие
    quest_types_seen = set()
    selected = []
    shuffled = list(ALL_QUESTS)
    rng.shuffle(shuffled)
    
    for quest in shuffled:
        qtype = quest["type"]
        if qtype not in quest_types_seen and len(selected) < QUESTS_PER_DAY:
            selected.append({
                "id": quest["id"],
                "name": quest["name"],
                "description": quest.get("description", ""),
                "type": quest["type"],
                "target": quest["target"],
                "reward_type": quest["reward_type"],
                "reward_amount": quest["reward_amount"],
                "target_rarity": quest.get("target_rarity"),
                "progress": 0,
                "claimed": False
            })
            quest_types_seen.add(qtype)
    
    # Если не хватает уникальных типов, добираем любые
    if len(selected) < QUESTS_PER_DAY:
        for quest in shuffled:
            if quest["id"] not in [s["id"] for s in selected] and len(selected) < QUESTS_PER_DAY:
                selected.append({
                    "id": quest["id"],
                    "name": quest["name"],
                    "description": quest.get("description", ""),
                    "type": quest["type"],
                    "target": quest["target"],
                    "reward_type": quest["reward_type"],
                    "reward_amount": quest["reward_amount"],
                    "target_rarity": quest.get("target_rarity"),
                    "progress": 0,
                    "claimed": False
                })
    
    return selected


def is_new_day(last_reset_str: str) -> bool:
    """Проверяет, нужно ли обновлять квесты (новый день)"""
    try:
        if not last_reset_str:
            return True
        last_reset = datetime.fromisoformat(last_reset_str).date()
        return date.today() > last_reset
    except (ValueError, TypeError):
        return True