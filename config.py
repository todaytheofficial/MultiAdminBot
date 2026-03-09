import os
BOT_TOKEN = "8554883360:AAHgqNde6T6iaW26vINy7DmYg2N4BWgvIjs"

# Создатели бота - по ID (не username!)
BOT_CREATOR_IDS = [
    6378314368,  # Твой ID
]

# Для обратной совместимости (если где-то ещё используется по username)
BOT_CREATORS = [
    "Idkkkkktd",
    "rumsfeldddd"
]
CARDS_IMAGES_PATH = "cards_images"

EMOJI = {
    "fire": "🔥", "star": "⭐", "crown": "👑", "sword": "⚔️",
    "shield": "🛡️", "trophy": "🏆", "gem": "💎", "lightning": "⚡",
    "skull": "💀", "heart": "❤️‍🔥", "magic": "✨", "dragon": "🐉",
    "cool": "😎", "rage": "🤬", "win": "🎉", "lose": "😭",
    "card": "🃏", "spin": "🎰", "arena": "🏟️", "rating": "📊",
    "mute": "🔇", "ban": "🚫", "warn": "⚠️", "rules": "📜",
    "rank": "🎖️", "promote": "⬆️", "demote": "⬇️", "info": "ℹ️",
    "settings": "⚙️", "delete": "🗑️", "pin": "📌", "user": "👤",
    "admin": "👮", "mod": "🛡️", "time": "⏰", "check": "✅",
    "cross": "❌", "link": "🔗", "stats": "📈", "creator": "💠",
    "daily": "📅", "pity": "🎯", "limited": "⏳", "luck": "🍀",
}

RANKS = {
    0: {
        "name": "Участник",
        "emoji": "👤",
        "color": "⚪",
        "permissions": [],
        "description": "Обычный участник чата"
    },
    1: {
        "name": "Мл.Модератор",
        "emoji": "🔰",
        "color": "🟢",
        "permissions": ["mute", "warn", "delete_messages", "view_warns"],
        "description": "Младший модератор"
    },
    2: {
        "name": "Ст.Модератор",
        "emoji": "🛡️",
        "color": "🔵",
        "permissions": ["mute", "unmute", "warn", "unwarn", "delete_messages", "view_warns", "pin_messages", "slow_mode"],
        "description": "Старший модератор"
    },
    3: {
        "name": "Мл.Админ",
        "emoji": "⚔️",
        "color": "🟣",
        "permissions": ["mute", "unmute", "warn", "unwarn", "ban", "kick", "delete_messages", "view_warns", "pin_messages", "slow_mode", "set_rules", "invite_users"],
        "description": "Младший администратор"
    },
    4: {
        "name": "Гл.Админ",
        "emoji": "🔱",
        "color": "🟡",
        "permissions": [
            "mute", "unmute", "warn", "unwarn", "ban", "unban", "kick",
            "delete_messages", "view_warns", "pin_messages", "slow_mode",
            "set_rules", "invite_users", "promote_1", "promote_2", "promote_3",
            "demote",  # <-- ДОБАВЛЕНО
            "change_info", "manage_voice"
        ],
        "description": "Главный администратор"
    },
    5: {
        "name": "Со-Владелец",
        "emoji": "👑",
        "color": "🟠",
        "permissions": [
            "mute", "unmute", "warn", "unwarn", "ban", "unban", "kick",
            "delete_messages", "view_warns", "pin_messages", "slow_mode",
            "set_rules", "invite_users", "promote_1", "promote_2", "promote_3", "promote_4",
            "demote", "change_info", "manage_voice", "add_admins", "manage_chat"
        ],
        "description": "Со-владелец"
    },
    6: {
        "name": "Владелец",
        "emoji": "🏆",
        "color": "🔴",
        "permissions": ["all"],
        "description": "Владелец чата"
    },
    99: {
        "name": "Создатель бота",
        "emoji": "💠",
        "color": "🔷",
        "permissions": ["all"],
        "description": "Создатель бота"
    },
}

PERMISSION_DESCRIPTIONS = {
    "mute": "🔇 Мутить пользователей", "unmute": "🔊 Размучивать пользователей",
    "warn": "⚠️ Выдавать предупреждения", "unwarn": "✅ Снимать предупреждения",
    "ban": "🚫 Банить пользователей", "unban": "♻️ Разбанивать пользователей",
    "kick": "👢 Кикать пользователей", "delete_messages": "🗑️ Удалять сообщения",
    "view_warns": "👁️ Смотреть предупреждения", "pin_messages": "📌 Закреплять сообщения",
    "slow_mode": "🐌 Управлять медленным режимом", "set_rules": "📜 Устанавливать правила",
    "invite_users": "📨 Приглашать пользователей", "change_info": "✏️ Менять информацию чата",
    "manage_voice": "🎙️ Управлять голосовыми чатами", "add_admins": "👮 Добавлять админов Telegram",
    "manage_chat": "⚙️ Управлять настройками чата", "promote_1": "⬆️ Повышать до Мл.Модератора",
    "promote_2": "⬆️ Повышать до Ст.Модератора", "promote_3": "⬆️ Повышать до Мл.Админа",
    "promote_4": "⬆️ Повышать до Гл.Админа", "demote": "⬇️ Понижать пользователей",
    "all": "👑 ВСЕ ПРАВА",
}

DAILY_REWARDS = {
    1: {"tickets": 1, "coins": 10, "description": "1 билет + 10 монет"},
    2: {"tickets": 1, "coins": 15, "description": "1 билет + 15 монет"},
    3: {"tickets": 2, "coins": 20, "description": "2 билета + 20 монет"},
    4: {"tickets": 2, "coins": 25, "description": "2 билета + 25 монет"},
    5: {"tickets": 2, "coins": 30, "description": "2 билета + 30 монет"},
    6: {"tickets": 3, "coins": 40, "description": "3 билета + 40 монет"},
    7: {"tickets": 5, "coins": 100, "bonus_card_chance": 0.3, "description": "5 билетов + 100 монет + 30% шанс карты!"},
}

PITY_THRESHOLDS = {
    "epic": 15,
    "legendary": 40,
    "mythic": 100,
}

LIMITED_CARDS = [
    {
        "name": "Halloween Gojo", "rarity": "limited", "attack": 82, "defense": 68,
        "emoji": "🎃", "image": None, "anime": "Jujutsu Kaisen",
        "description": "Годжо в костюме на Хэллоуин! (Ограниченная)",
        "available_from": "2026-10-25", "available_until": "2026-11-05", "max_copies": 100
    },
    {
        "name": "New Year Sukuna", "rarity": "limited", "attack": 85, "defense": 70,
        "emoji": "🎆", "image": None, "anime": "Jujutsu Kaisen",
        "description": "Сукуна празднует Новый Год! (Ограниченная)",
        "available_from": "2026-01-26", "available_until": "2027-01-10", "max_copies": 150
    },
    {
        "name": "APSN Nobara", "rarity": "limited", "attack": 1, "defense": 1,
        "emoji": "🍊", "image": "apsn.jpg", "anime": "",
        "description": "Слабейшая карта lmao (Ограниченная)",
        "available_from": "2026-03-1", "available_until": "2026-03-4", "max_copies": 150
    },
    {
        "name": "Valentine Nobara", "rarity": "limited", "attack": 55, "defense": 48,
        "emoji": "💝", "image": None, "anime": "Jujutsu Kaisen",
        "description": "Нобара в День Святого Валентина! (Ограниченная)",
        "available_from": "2026-02-10", "available_until": "2026-02-20", "max_copies": 200
    },

]

ARENA_SETTINGS = {
    "cards_per_battle": 3, "luck_factor_min": 0.85, "luck_factor_max": 1.15,
    "critical_hit_chance": 0.1, "critical_multiplier": 1.5, "dodge_chance": 0.05,
    "rating_win_base": 25, "rating_lose_base": 15, "coins_per_win": 15, "coins_per_lose": 3,
}

CHAINSAW_CARDS = [
    "Young Aki", "Grape Devil", "Sea Cucumber Devil",
    "Zombie Devil", "Stone Devil",
    "Bat Devil", "Kobeni", "Galgali",
    "Power", "Aki", "Denji", "Beam", "Angel",
    "Makima", "Chainsaw Man", "Reze",
    "CHAINSAW DEVIL", "GUN DEVIL", "CONTROL DEVIL",
]

CARDS = [
    # ============ JUJUTSU KAISEN ============

    # COMMON
    {"name": "Panda", "rarity": "common", "attack": 12, "defense": 14, "emoji": "🐼", "image": "Panda.png", "anime": "Jujutsu Kaisen", "description": "Проклятый труп, созданный Ягой"},
    {"name": "Kechizu", "rarity": "common", "attack": 10, "defense": 10, "emoji": "👹", "image": None, "anime": "Jujutsu Kaisen", "description": "Младший из братьев Призрачной Утробы"},
    {"name": "Ui Ui", "rarity": "common", "attack": 8, "defense": 12, "emoji": "👦", "image": None, "anime": "Jujutsu Kaisen", "description": "Младший брат Мэй Мэй"},
    {"name": "Mai Zenin", "rarity": "common", "attack": 11, "defense": 9, "emoji": "🔫", "image": None, "anime": "Jujutsu Kaisen", "description": "Близнец Маки, владеет техникой Создания"},

    # RARE
    {"name": "Nobara", "rarity": "rare", "attack": 18, "defense": 14, "emoji": "🔨", "image": "Nobara.png", "anime": "Jujutsu Kaisen", "description": "Мастер техники Соломенной Куклы"},
    {"name": "Mei Mei", "rarity": "rare", "attack": 20, "defense": 16, "emoji": "🐦", "image": None, "anime": "Jujutsu Kaisen", "description": "Маг 1-го класса, повелительница воронов"},
    {"name": "Naobito", "rarity": "rare", "attack": 22, "defense": 14, "emoji": "⚡", "image": None, "anime": "Jujutsu Kaisen", "description": "Глава клана Дзэнин, мастер Проекции"},
    {"name": "Eso", "rarity": "rare", "attack": 19, "defense": 17, "emoji": "🩸", "image": None, "anime": "Jujutsu Kaisen", "description": "Средний брат Призрачной Утробы"},
    {"name": "Takuma Ino", "rarity": "rare", "attack": 19, "defense": 17, "emoji": "🦊", "image": None, "anime": "Jujutsu Kaisen", "description": "Помощник Нанами"},

    # EPIC
    {"name": "Finger Bearer", "rarity": "epic", "attack": 28, "defense": 24, "emoji": "👆", "image": None, "anime": "Jujutsu Kaisen", "description": "Проклятие, поглотившее палец Сукуны"},
    {"name": "Miguel", "rarity": "epic", "attack": 30, "defense": 22, "emoji": "⚔️", "image": None, "anime": "Jujutsu Kaisen", "description": "Африканский маг с легендарной верёвкой"},
    {"name": "Megumi", "rarity": "epic", "attack": 32, "defense": 26, "emoji": "🐕", "image": "Megumi.png", "anime": "Jujutsu Kaisen", "description": "Наследник техники Десяти Теней"},
    {"name": "Dagon", "rarity": "epic", "attack": 35, "defense": 28, "emoji": "🐙", "image": None, "anime": "Jujutsu Kaisen", "description": "Проклятие Особого класса, мастер воды"},
    {"name": "Naoya Zenin", "rarity": "epic", "attack": 33, "defense": 23, "emoji": "💨", "image": None, "anime": "Jujutsu Kaisen", "description": "Наследник клана Дзэнин, техника Проекции"},
    {"name": "Choso", "rarity": "epic", "attack": 34, "defense": 27, "emoji": "🩸", "image": None, "anime": "Jujutsu Kaisen", "description": "Старший брат Призрачной Утробы, мастер крови"},

    # LEGENDARY
    {"name": "Aoi Todo", "rarity": "legendary", "attack": 45, "defense": 38, "emoji": "👏", "image": "Aoi_Todo.png", "anime": "Jujutsu Kaisen", "description": "Мой лучший друг! Техника Буги-Вуги"},
    {"name": "Maki Zenin", "rarity": "legendary", "attack": 48, "defense": 35, "emoji": "🗡️", "image": None, "anime": "Jujutsu Kaisen", "description": "Достигла уровня Тодзи, мастер оружия"},
    {"name": "Yuji Itadori", "rarity": "legendary", "attack": 50, "defense": 42, "emoji": "👊", "image": "Yuji_Itadori.png", "anime": "Jujutsu Kaisen", "description": "Сосуд Сукуны, мастер рукопашного боя"},
    {"name": "Nanami", "rarity": "legendary", "attack": 46, "defense": 40, "emoji": "📏", "image": None, "anime": "Jujutsu Kaisen", "description": "Маг 1-го класса, техника Соотношения"},
    {"name": "Geto", "rarity": "legendary", "attack": 52, "defense": 44, "emoji": "👻", "image": None, "anime": "Jujutsu Kaisen", "description": "Мастер техники Поглощения Проклятий"},
    {"name": "Jogo", "rarity": "legendary", "attack": 55, "defense": 38, "emoji": "🌋", "image": None, "anime": "Jujutsu Kaisen", "description": "Проклятие Особого класса, повелитель огня"},
    {"name": "Yuki Tsukumo", "rarity": "legendary", "attack": 53, "defense": 45, "emoji": "⭐", "image": None, "anime": "Jujutsu Kaisen", "description": "Один из 4-х Магов Особого класса"},
    {"name": "Utahime Iori", "rarity": "legendary", "attack": 44, "defense": 41, "emoji": "🎤", "image": None, "anime": "Jujutsu Kaisen", "description": "Полу-маг 1-го класса, учитель в Киото"},
    {"name": "Toge Inumaki", "rarity": "legendary", "attack": 47, "defense": 39, "emoji": "🍙", "image": None, "anime": "Jujutsu Kaisen", "description": "Носитель Проклятой Речи"},
    {"name": "Hajime Kashimo", "rarity": "legendary", "attack": 51, "defense": 37, "emoji": "⚡", "image": None, "anime": "Jujutsu Kaisen", "description": "Сильнейший маг эпохи Эдо"},

    # MYTHIC
    {"name": "Mahito", "rarity": "mythic", "attack": 62, "defense": 50, "emoji": "🎭", "image": "Mahito.png", "anime": "Jujutsu Kaisen", "description": "Проклятие, рождённое из ненависти людей"},
    {"name": "Sukuna", "rarity": "mythic", "attack": 75, "defense": 60, "emoji": "👹", "image": None, "anime": "Jujutsu Kaisen", "description": "Король Проклятий, непревзойдённый"},
    {"name": "Meguna", "rarity": "mythic", "attack": 70, "defense": 58, "emoji": "😈", "image": None, "anime": "Jujutsu Kaisen", "description": "Мегуми, захваченный Сукуной"},
    {"name": "Gojo Satoru", "rarity": "mythic", "attack": 80, "defense": 65, "emoji": "👁️", "image": "Gojo_Satoru.png", "anime": "Jujutsu Kaisen", "description": "Сильнейший маг современности, Безграничность"},
    {"name": "Shinjuku Yuji", "rarity": "mythic", "attack": 72, "defense": 55, "emoji": "🔥", "image": None, "anime": "Jujutsu Kaisen", "description": "Юджи в финальной битве Синдзюку"},
    {"name": "Yuta Okkotsu", "rarity": "mythic", "attack": 78, "defense": 62, "emoji": "💀", "image": None, "anime": "Jujutsu Kaisen", "description": "Маг Особого класса, связанный с Рикой"},
    {"name": "Kinji Hakari", "rarity": "mythic", "attack": 76, "defense": 64, "emoji": "🎲", "image": None, "anime": "Jujutsu Kaisen", "description": "Маг с техникой Джекпот"},
    {"name": "Mahoraga", "rarity": "mythic", "attack": 82, "defense": 68, "emoji": "🗡️", "image": "Mahoraga.png", "anime": "Jujutsu Kaisen", "description": "Сильнейший Сикигами Десяти Теней"},

    # SPECIAL
    {"name": "Gojo Tea", "rarity": "special", "attack": 85, "defense": 70, "emoji": "🍵", "image": None, "anime": "Idku Log", "description": "Чай - это наш всеми любимый СоВладелец моих проектов, она любит чай кстати!"},
    {"name": "Rumsukuna", "rarity": "special", "attack": 88, "defense": 72, "emoji": "🍺", "image": None, "anime": "Idku Log", "description": "Румс - Владелец канала RumteZz! Но его тело было захвачено Сукуной..."},
    {"name": "Idkyuji", "rarity": "special", "attack": 92, "defense": 78, "emoji": "💠", "image": None, "anime": "Idku Log", "description": "Создатель этого бота, Спасибо ему!"},
    {"name": "SaserHakari", "rarity": "special", "attack": 90, "defense": 75, "emoji": "🎰", "image": None, "anime": "Sasers Kaisen", "description": "Сасер лучший друг Арбуза и мой тоже! Он любит депать..."},
    {"name": "ArbuzMegumi", "rarity": "special", "attack": 86, "defense": 74, "emoji": "🍉", "image": None, "anime": "Arbuz Kaisen", "description": "Арбуз мой лучший дружбан и в целом он крутой"},

    # MEGA (JJK)
    {"name": "Heian Sukuna", "rarity": "mega", "attack": 105, "defense": 88, "emoji": "👑", "image": "Heian_Sukuna.png", "anime": "Jujutsu Kaisen", "description": "Сукуна в своей истинной форме эпохи Хэйан — Король Проклятий в пике мощи"},
    {"name": "Hakari & Kirara", "rarity": "mega", "attack": 110, "defense": 98, "emoji": "👑", "image": "Hakari&Kirara.jpg", "anime": "Jujutsu Kaisen", "description": ""},

    # ============ CHAINSAW MAN (Бензопила) ============

    # COMMON
    {"name": "Young Aki", "rarity": "common", "attack": 11, "defense": 13, "emoji": "🧒", "image": None, "anime": "Chainsaw Man", "description": "Молодой Аки Хаякава до вступления в отряд охотников на демонов"},
    {"name": "Grape Devil", "rarity": "common", "attack": 9, "defense": 11, "emoji": "🍇", "image": None, "anime": "Chainsaw Man", "description": "Слабый демон виноградной лозы"},
    {"name": "Sea Cucumber Devil", "rarity": "common", "attack": 10, "defense": 12, "emoji": "🥒", "image": None, "anime": "Chainsaw Man", "description": "Демон морского огурца, не самый страшный противник"},

    # RARE
    {"name": "Zombie Devil", "rarity": "rare", "attack": 20, "defense": 18, "emoji": "🧟", "image": None, "anime": "Chainsaw Man", "description": "Демон зомби, способный поднимать мёртвых"},
    {"name": "Stone Devil", "rarity": "rare", "attack": 21, "defense": 19, "emoji": "🪨", "image": None, "anime": "Chainsaw Man", "description": "Демон камня, обращающий жертв в камень"},

    # EPIC
    {"name": "Bat Devil", "rarity": "epic", "attack": 30, "defense": 25, "emoji": "🦇", "image": None, "anime": "Chainsaw Man", "description": "Демон летучей мыши, огромный и свирепый"},
    {"name": "Kobeni", "rarity": "epic", "attack": 33, "defense": 28, "emoji": "😰", "image": None, "anime": "Chainsaw Man", "description": "Кобени Хигасияма — невероятно ловкая охотница, несмотря на свой страх"},
    {"name": "Galgali", "rarity": "epic", "attack": 31, "defense": 26, "emoji": "⚙️", "image": None, "anime": "Chainsaw Man", "description": "Демон насилия в теле человека, любит мирную жизнь"},

    # LEGENDARY
    {"name": "Power", "rarity": "legendary", "attack": 49, "defense": 36, "emoji": "🩸", "image": None, "anime": "Chainsaw Man", "description": "Демон крови, напарница Дэнджи и самопровозглашённый президент"},
    {"name": "Aki", "rarity": "legendary", "attack": 47, "defense": 40, "emoji": "🎯", "image": None, "anime": "Chainsaw Man", "description": "Аки Хаякава — охотник на демонов, контракт с Лисой и Проклятием"},
    {"name": "Denji", "rarity": "legendary", "attack": 52, "defense": 38, "emoji": "🔥", "image": None, "anime": "Chainsaw Man", "description": "Дэнджи — парень, слившийся с Почитой, человек-бензопила"},
    {"name": "Beam", "rarity": "legendary", "attack": 46, "defense": 37, "emoji": "🦈", "image": None, "anime": "Chainsaw Man", "description": "Демон акулы, преданный фанат Человека-Бензопилы"},
    {"name": "Angel", "rarity": "legendary", "attack": 50, "defense": 43, "emoji": "😇", "image": None, "anime": "Chainsaw Man", "description": "Демон-ангел, забирает продолжительность жизни прикосновением"},

    # MYTHIC
    {"name": "Makima", "rarity": "mythic", "attack": 78, "defense": 63, "emoji": "🐕‍🦺", "image": "makima.jpg", "anime": "Chainsaw Man", "description": "Демон контроля, манипулирующая всеми из тени. Гав."},
    {"name": "Chainsaw Man", "rarity": "mythic", "attack": 80, "defense": 60, "emoji": "🪚", "image": "chainsawman.jpg", "anime": "Chainsaw Man", "description": "Истинная форма Почиты — Герой Ада, пожирающий демонов навсегда"},
    {"name": "Reze", "rarity": "mythic", "attack": 74, "defense": 58, "emoji": "💣", "image": "reze.jpg", "anime": "Chainsaw Man", "description": "Девушка-бомба, гибрид демона бомбы, первая любовь Дэнджи"},

    # MEGA
    {"name": "CHAINSAW DEVIL", "rarity": "mega", "attack": 108, "defense": 90, "emoji": "🪚", "image": None, "anime": "Chainsaw Man", "description": "Демон Бензопилы в полной силе — Герой Ада, стирающий демонов из существования"},
    {"name": "GUN DEVIL", "rarity": "mega", "attack": 112, "defense": 85, "emoji": "🔫", "image": None, "anime": "Chainsaw Man", "description": "Демон Пистолета — убил 1.2 миллиона людей за 5 минут, воплощение страха оружия"},
    {"name": "CONTROL DEVIL", "rarity": "mega", "attack": 106, "defense": 95, "emoji": "🐾", "image": None, "anime": "Chainsaw Man", "description": "Истинная форма Макимы — Демон Контроля, один из сильнейших Праймал Девилов"},
]

ALL_RARITIES = ["common", "rare", "epic", "legendary", "mythic", "special", "mega", "limited"]

RARITY_CHANCES = {
    "common":    40.0,
    "rare":      30.0,
    "epic":      10.0,
    "legendary":  2.0,
    "mythic":     0.9,
    "special":    0.25,
    "mega":       0.1,
    "limited":    0.0,
}

RARITY_NAMES = {
    "common": "⚪ Common", "rare": "🔵 Rare", "epic": "🟣 Epic",
    "legendary": "🟡 Legendary", "mythic": "🔴 Mythic",
    "special": "💎 Special", "mega": "🌌 MEGA", "limited": "⏳ Limited",
}

RARITY_COLORS = {
    "common": "⚪", "rare": "🔵", "epic": "🟣", "legendary": "🟡",
    "mythic": "🔴", "special": "💎", "mega": "🌌", "limited": "⏳",
}

RARITY_ORDER = {
    "common": 0, "rare": 1, "epic": 2, "legendary": 3,
    "mythic": 4, "special": 5, "mega": 6, "limited": 7,
}

SHIELDS = {
    "wooden":  {"name": "Деревянный щит",   "price": 180,  "block_chance": 18, "damage_reduction": 25, "emoji": "🪵🛡️"},
    "iron":    {"name": "Железный щит",     "price": 420,  "block_chance": 26, "damage_reduction": 35, "emoji": "⚒️🛡️"},
    "steel":   {"name": "Стальной щит",     "price": 950,  "block_chance": 34, "damage_reduction": 45, "emoji": "🛠️🛡️"},
    "cursed":  {"name": "Проклятый щит",    "price": 2400, "block_chance": 42, "damage_reduction": 55, "emoji": "🖤🛡️"},
    "divine":  {"name": "Божественный щит", "price": 5800, "block_chance": 55, "damage_reduction": 70, "emoji": "✨🛡️"},
}

# ═══════════════════════════════════════════════
#  MULTS — НОВАЯ ВАЛЮТА
# ═══════════════════════════════════════════════

MULTS_EXCHANGE_RATE = 100  # 100 монет = 1 Mults
FUSION_COST_MULTS = 3      # 3 Mults за одно соединение
# ═══════════════════════════════════════════════
#  FUSION CARDS — ЭКСКЛЮЗИВНЫЕ КАРТЫ (НЕ ПАДАЮТ ИЗ СПИНА)
# ═══════════════════════════════════════════════

FUSION_CARDS = [
    # ══════════ ОБЫЧНЫЕ FUSION (Mythic + Mythic / Legendary + Legendary) ══════════
    {
        "name": "Hollow Purple Gojo",
        "rarity": "fused",
        "attack": 120,
        "defense": 95,
        "emoji": "🟣",
        "image": None,
        "anime": "Jujutsu Kaisen",
        "description": "Годжо использует Пустое Пурпурное — слияние Синего и Красного! (Эксклюзив Fusion)"
    },
    {
        "name": "Domain Sukuna",
        "rarity": "fused",
        "attack": 130,
        "defense": 100,
        "emoji": "🔮",
        "image": None,
        "anime": "Jujutsu Kaisen",
        "description": "Сукуна раскрывает Злонамеренную Скинию! (Эксклюзив Fusion)"
    },
    {
        "name": "Black Flash Yuji",
        "rarity": "fused",
        "attack": 115,
        "defense": 88,
        "emoji": "⚡",
        "image": None,
        "anime": "Jujutsu Kaisen",
        "description": "Юджи постиг Чёрную Вспышку! (Эксклюзив Fusion)"
    },
    {
        "name": "Cursed Womb Choso",
        "rarity": "fused",
        "attack": 105,
        "defense": 92,
        "emoji": "🩸",
        "image": None,
        "anime": "Jujutsu Kaisen",
        "description": "Чосо в полной форме Проклятой Утробы! (Эксклюзив Fusion)"
    },
    {
        "name": "Six Eyes Awakened",
        "rarity": "fused",
        "attack": 140,
        "defense": 110,
        "emoji": "👁️‍🗨️",
        "image": None,
        "anime": "Jujutsu Kaisen",
        "description": "Пробуждение Шести Глаз! (Эксклюзив Fusion)"
    },
    {
        "name": "Hybrid Denji",
        "rarity": "fused",
        "attack": 125,
        "defense": 90,
        "emoji": "🔥",
        "image": None,
        "anime": "Chainsaw Man",
        "description": "Дэнджи в полной гибридной форме! (Эксклюзив Fusion)"
    },
    {
        "name": "Blood Fiend Power",
        "rarity": "fused",
        "attack": 118,
        "defense": 85,
        "emoji": "🩸",
        "image": None,
        "anime": "Chainsaw Man",
        "description": "Пауэр — максимальная форма Демона Крови! (Эксклюзив Fusion)"
    },
    {
        "name": "Future Devil Aki",
        "rarity": "fused",
        "attack": 110,
        "defense": 95,
        "emoji": "⏰",
        "image": None,
        "anime": "Chainsaw Man",
        "description": "Аки с полным контрактом Демона Будущего! (Эксклюзив Fusion)"
    },
    {
        "name": "Cursed Chainsaw",
        "rarity": "fused",
        "attack": 135,
        "defense": 105,
        "emoji": "🪚",
        "image": None,
        "anime": "Crossover",
        "description": "Бензопила пропитанная проклятой энергией! (Эксклюзив Fusion)"
    },
    {
        "name": "Infinity Makima",
        "rarity": "fused",
        "attack": 145,
        "defense": 115,
        "emoji": "♾️",
        "image": None,
        "anime": "Crossover",
        "description": "Макима с Безграничностью Годжо! (Эксклюзив Fusion)"
    },
    
    # ══════════ MEGA FUSION (MEGA + MEGA) — УЛЬТРА РЕДКИЕ ══════════
    {
        "name": "KING OF CURSES",
        "rarity": "mega_fused",
        "attack": 200,
        "defense": 165,
        "emoji": "👑💀",
        "image": None,
        "anime": "Jujutsu Kaisen",
        "description": "Хейан Сукуна поглотил всех! Истинный Король Проклятий во всей мощи! (MEGA Fusion)"
    },
    {
        "name": "PRIMORDIAL FEAR",
        "rarity": "mega_fused",
        "attack": 210,
        "defense": 175,
        "emoji": "😱🔥",
        "image": None,
        "anime": "Chainsaw Man",
        "description": "Слияние трёх Праймал Девилов — воплощение первобытного страха человечества! (MEGA Fusion)"
    },
    {
        "name": "DEVIL SLAYER SUPREME",
        "rarity": "mega_fused",
        "attack": 195,
        "defense": 180,
        "emoji": "🪚⚔️",
        "image": None,
        "anime": "Chainsaw Man",
        "description": "Демон Бензопилы с оружием Демона Пистолета — абсолютный охотник! (MEGA Fusion)"
    },
    {
        "name": "DOMAIN OF HELL",
        "rarity": "mega_fused",
        "attack": 205,
        "defense": 170,
        "emoji": "🌌👹",
        "image": None,
        "anime": "Crossover",
        "description": "Сукуна и Демон Контроля объединили домены — врата в Ад открыты! (MEGA Fusion)"
    },
    {
        "name": "INFINITY CHAINSAW",
        "rarity": "mega_fused",
        "attack": 220,
        "defense": 185,
        "emoji": "♾️🪚",
        "image": None,
        "anime": "Crossover",
        "description": "Демон Бензопилы с Безграничностью — ничто не может его коснуться! (MEGA Fusion)"
    },
    {
        "name": "APOCALYPSE RIDER",
        "rarity": "mega_fused",
        "attack": 215,
        "defense": 190,
        "emoji": "🏍️💀",
        "image": None,
        "anime": "Crossover",
        "description": "Демон Пистолета верхом на Демоне Бензопилы — Всадник Апокалипсиса! (MEGA Fusion)"
    },
    {
        "name": "ABSOLUTE CONTROL",
        "rarity": "mega_fused",
        "attack": 190,
        "defense": 200,
        "emoji": "🐾👁️",
        "image": None,
        "anime": "Crossover",
        "description": "Демон Контроля с Шестью Глазами — абсолютное подчинение всего сущего! (MEGA Fusion)"
    },
    {
        "name": "ROYAL MASSACRE",
        "rarity": "mega_fused",
        "attack": 225,
        "defense": 160,
        "emoji": "👑🔫",
        "image": None,
        "anime": "Crossover",
        "description": "Хейан Сукуна с мощью Демона Пистолета — массовое уничтожение! (MEGA Fusion)"
    },
]

FUSION_RECIPES = {
    # ══════════ ОБЫЧНЫЕ РЕЦЕПТЫ ══════════
    ("Gojo Satoru", "Sukuna"):           "Hollow Purple Gojo",
    ("Sukuna", "Meguna"):                "Domain Sukuna",
    ("Yuji Itadori", "Shinjuku Yuji"):   "Black Flash Yuji",
    ("Choso", "Eso"):                    "Cursed Womb Choso",
    ("Gojo Satoru", "Yuta Okkotsu"):     "Six Eyes Awakened",
    ("Denji", "Chainsaw Man"):           "Hybrid Denji",
    ("Power", "Makima"):                 "Blood Fiend Power",
    ("Aki", "Angel"):                    "Future Devil Aki",
    ("Chainsaw Man", "Mahito"):          "Cursed Chainsaw",
    ("Makima", "Gojo Satoru"):           "Infinity Makima",
    
    ("Heian Sukuna", "Hakari & Kirara"):          "KING OF CURSES",
    
    ("CHAINSAW DEVIL", "GUN DEVIL"):              "DEVIL SLAYER SUPREME",
    ("GUN DEVIL", "CONTROL DEVIL"):               "PRIMORDIAL FEAR",
    ("CHAINSAW DEVIL", "CONTROL DEVIL"):          "APOCALYPSE RIDER",
    
    ("Heian Sukuna", "CONTROL DEVIL"):            "DOMAIN OF HELL",
    ("CHAINSAW DEVIL", "Hakari & Kirara"):        "INFINITY CHAINSAW", 
    ("Heian Sukuna", "GUN DEVIL"):                "ROYAL MASSACRE",
    ("CONTROL DEVIL", "Hakari & Kirara"):         "ABSOLUTE CONTROL",
}

# Стоимость MEGA Fusion выше!
MEGA_FUSION_COST_MULTS = 10  # 10 Mults за MEGA fusion (против 3 за обычный)

# Магазин за Mults — ДОРОГИЕ ЦЕНЫ
MULTS_SHOP_ITEMS = {
    "fusion_token": {
        "name": "🔮 Токен Соединения",
        "description": "Позволяет соединить 2 карты в эксклюзивную",
        "price_mults": 10,
        "type": "fusion",
        "value": 3
    },
    "ticket_pack_small": {
        "name": "🎫 Пак билетов x20",
        "description": "20 билетов для прокрутки",
        "price_mults": 35,
        "type": "tickets",
        "value": 20
    },
    "ticket_pack_big": {
        "name": "🎫 Мега-пак билетов x100",
        "description": "100 билетов для прокрутки",
        "price_mults": 250,
        "type": "tickets",
        "value": 100
    },
    "shield_pack": {
        "name": "🛡️ Пак щитов x10",
        "description": "10 щитов для арены",
        "price_mults": 8,
        "type": "shields",
        "value": 10
    },
    "super_shield": {
        "name": "🛡️ Мега-щит x25",
        "description": "25 щитов для арены",
        "price_mults": 18,
        "type": "shields",
        "value": 25
    },
    "luck_boost_x2": {
        "name": "🍀 Буст удачи x2",
        "description": "x2 к шансу редких карт на 6 часов",
        "price_mults": 10,
        "type": "boost",
        "value": 2.0,
        "duration": 6
    },
    "luck_boost_x3": {
        "name": "🍀 Супер-буст x3",
        "description": "x3 к шансу редких карт на 12 часов",
        "price_mults": 25,
        "type": "boost",
        "value": 3.0,
        "duration": 12
    },
    "luck_boost_x5": {
        "name": "🍀 МЕГА-буст x5",
        "description": "x5 к шансу редких карт на 24 часа",
        "price_mults": 50,
        "type": "boost",
        "value": 5.0,
        "duration": 24
    },
    "coin_pack_small": {
        "name": "💰 Пак монет 1000",
        "description": "1000 монет",
        "price_mults": 15,
        "type": "coins",
        "value": 1000
    },
    "coin_pack_big": {
        "name": "💰 Мега-пак 5000",
        "description": "5000 монет",
        "price_mults": 40,
        "type": "coins",
        "value": 5000
    },
}

# Добавить mega_fused редкость
RARITY_NAMES["fused"] = "🔮 Fused"
RARITY_NAMES["mega_fused"] = "🌌 MEGA Fused"

RARITY_COLORS["fused"] = "🔮"
RARITY_COLORS["mega_fused"] = "🌌"

RARITY_ORDER["fused"] = 8
RARITY_ORDER["mega_fused"] = 9  # Самая редкая!

RARITY_CHANCES["fused"] = 0.0
RARITY_CHANCES["mega_fused"] = 0.0