# handlers/cards.py
import random
import os
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, ChatMemberOwner
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
import asyncio
from typing import Dict, Set

from config import (
    EMOJI, CARDS, RARITY_CHANCES, RARITY_NAMES, RARITY_COLORS,
    CARDS_IMAGES_PATH, BOT_CREATORS, PITY_THRESHOLDS, LIMITED_CARDS,
    RARITY_ORDER, CHAINSAW_CARDS, FUSION_CARDS
)
from database import DatabaseManager

router = Router()
logger = logging.getLogger(__name__)


# ================== HELPERS ==================

class AntiSpam:
    def __init__(self):
        self.last_action: Dict[int, Dict[str, datetime]] = {}
        self.warnings: Dict[int, int] = {}
        self.blocked: Set[int] = set()
        self.cd = {"spin": 3, "ticket": 2, "command": 1, "callback": 0.5, "casino": 2}

    def check(self, uid: int, action: str) -> tuple:
        if uid in self.blocked:
            return False, 9999
        now = datetime.now()
        cd = self.cd.get(action, 1)
        if uid not in self.last_action:
            self.last_action[uid] = {}
        last = self.last_action[uid].get(action)
        if last and (now - last).total_seconds() < cd:
            self.warnings[uid] = self.warnings.get(uid, 0) + 1
            if self.warnings[uid] >= 10:
                self.blocked.add(uid)
                asyncio.create_task(self._unblock(uid))
            return False, int(cd - (now - last).total_seconds()) + 1
        self.last_action[uid][action] = now
        self.warnings[uid] = 0
        return True, 0

    async def _unblock(self, uid: int):
        await asyncio.sleep(300)
        self.blocked.discard(uid)
        self.warnings[uid] = 0


antispam = AntiSpam()

COIN_REWARDS = {
    "common": (1, 3), "rare": (3, 6), "epic": (6, 12), "legendary": (12, 25),
    "mythic": (25, 50), "special": (50, 100), "mega": (100, 200),
    "limited": (75, 150), "fused": (80, 160), "mega_fused": (150, 300)
}

SPIN_HEADERS = {
    "mega": "🌌🌌🌌 <b>MEGA!!!</b> 🌌🌌🌌\n\n",
    "mega_fused": "🌌🔮🌌 <b>MEGA FUSION!!!</b> 🌌🔮🌌\n\n",
    "limited": "⏳⏳⏳ <b>LIMITED!!!</b> ⏳⏳⏳\n\n",
    "special": "💎💎💎 <b>SPECIAL!!!</b> 💎💎💎\n\n",
    "mythic": "🔴🔴🔴 <b>MYTHIC!!</b> 🔴🔴🔴\n\n",
    "legendary": "🟡🟡🟡 <b>LEGENDARY!</b> 🟡🟡🟡\n\n",
    "fused": "🔮🔮🔮 <b>FUSION!</b> 🔮🔮🔮\n\n",
    "epic": "🟣🟣 <b>EPIC!</b> 🟣🟣\n\n",
    "rare": "🔵 <b>RARE!</b> 🔵\n\n",
    "common": "🎰 <b>Прокрутка!</b>\n\n",
}


def is_group(msg):
    return msg.chat.type in ["group", "supergroup"]


def get_db(event):
    if isinstance(event, CallbackQuery):
        return DatabaseManager.get_db(event.message.chat.id)
    return DatabaseManager.get_db(event.chat.id)


def get_chat_id(event):
    if isinstance(event, CallbackQuery):
        return event.message.chat.id
    return event.chat.id


def get_coins(r):
    return random.randint(*COIN_REWARDS.get(r, (1, 3)))


def is_csm(c):
    return c.get("name") in CHAINSAW_CARDS or c.get("anime") == "Chainsaw Man"


def find_card(name: str):
    n = name.lower().strip()
    for lst in [CARDS, LIMITED_CARDS, FUSION_CARDS]:
        for c in lst:
            if c["name"].lower() == n or n in c["name"].lower():
                return c
    return None


def format_card(c, details=True):
    r = RARITY_NAMES.get(c["rarity"], c["rarity"])
    p = c["attack"] + c["defense"]
    t = f"{c['emoji']} <b>{c['name']}</b>\n├ {r}\n├ ⚔️ {c['attack']}\n├ 🛡️ {c['defense']}\n└ 💪 {p}"
    if details:
        if c.get("anime"):
            t += f"\n\n🎬 <i>{c['anime']}</i>"
        if c.get("description"):
            t += f"\n📝 <i>{c['description']}</i>"
    return t


def get_img_path(c):
    if not c.get("image"):
        return None
    p = os.path.join(CARDS_IMAGES_PATH, c["image"])
    return p if os.path.exists(p) else None


async def send_card(msg, card, caption, reply=True):
    try:
        img = get_img_path(card)
        if img:
            try:
                f = FSInputFile(img)
                await (msg.reply_photo if reply else msg.answer_photo)(photo=f, caption=caption, parse_mode="HTML")
                return
            except:
                pass
        await (msg.reply if reply else msg.answer)(caption, parse_mode="HTML")
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await send_card(msg, card, caption, reply)
        except:
            pass
    except:
        pass


async def is_admin(msg: Message, bot: Bot):
    if msg.from_user.username in BOT_CREATORS:
        return True
    if msg.chat.type in ["group", "supergroup"]:
        try:
            m = await bot.get_chat_member(msg.chat.id, msg.from_user.id)
            return isinstance(m, ChatMemberOwner)
        except:
            pass
    return False


def quest(db, uid, t, a=1, e=None):
    try:
        from handlers.quests import update_quest_progress
        update_quest_progress(db, uid, t, a, e)
    except:
        pass


def check_limited(c):
    try:
        now = datetime.now()
        return datetime.strptime(c["available_from"], "%Y-%m-%d") <= now <= datetime.strptime(c["available_until"], "%Y-%m-%d")
    except:
        return False


def get_total_luck_boost(db, uid: int, chat_id: int = None) -> float:
    """Получить буст удачи для конкретной группы"""
    # Локальный буст (магазин / giveluck)
    shop_boost = 1.0
    user = db.get_user(uid)
    if user:
        luck_boost = user.get("luck_boost", 1.0)
        luck_until = user.get("luck_boost_until")
        if luck_boost > 1.0 and luck_until:
            try:
                until_dt = datetime.fromisoformat(luck_until) if isinstance(luck_until, str) else luck_until
                if until_dt > datetime.now():
                    shop_boost = luck_boost
                else:
                    db.remove_luck_boost(uid)
            except:
                pass

    # Админский буст — привязан к chat_id
    admin_boost = 1.0
    if chat_id:
        admin_boost = DatabaseManager.get_global_db().get_spin_boost(uid, chat_id)
    return max(shop_boost, admin_boost)


def get_casino_win_chance(boost: float, bet_type: str = "x2") -> float:
    """
    Шанс выигрыша в казино.
    
    x2 ставки (red/black/odd/even/low/high):
      без удачи=50%, x2=55%, x3=60%, x5=65%, макс 95%
    
    x3 ставки (d1/d2/d3):
      без удачи=32%, растёт пропорционально
    
    x35 ставка (green/зеро):
      без удачи=2.7%, растёт медленно
    """
    if bet_type == "x2":
        base = 0.50
        if boost <= 1.0:
            return base
        # x2→55%, x3→60%, x5→65%: линейная 50 + 3.75*(boost-1)
        chance = base + 0.0375 * (boost - 1.0)
        return min(0.95, chance)
    elif bet_type == "x3":
        base = 0.324
        if boost <= 1.0:
            return base
        chance = base + 0.0375 * (boost - 1.0)
        return min(0.80, chance)
    elif bet_type == "x35":
        base = 0.027
        if boost <= 1.0:
            return base
        chance = base + 0.01 * (boost - 1.0)
        return min(0.30, chance)
    return 0.50


def get_random_card(boost=1.0, uid=None, cid=None):
    db = DatabaseManager.get_db(cid) if cid else None

    if uid and db:
        pity = db.get_pity_counters(uid)
        for r, th in [("mythic", 100), ("legendary", 40), ("epic", 15)]:
            if pity[f"since_{r}"] >= PITY_THRESHOLDS.get(r, th):
                cards = [c for c in CARDS if c["rarity"] == r]
                if cards:
                    db.reset_pity_for_rarity(uid, r)
                    return random.choice(cards)

    if db:
        lim = [c for c in LIMITED_CARDS if check_limited(c) and db.get_limited_card_count(c["name"]) < c.get("max_copies", 999)]
        if lim and random.random() < 0.02 * boost:
            c = random.choice(lim)
            if uid:
                db.issue_limited_card(c["name"], uid)
                db.reset_pity_for_rarity(uid, "limited")
            return c

    chances = {r: min(100, ch * boost) if r in ["special", "mega", "mythic", "legendary"] else ch for r, ch in RARITY_CHANCES.items()}
    roll, cum = random.uniform(0, 100), 0
    rarity = "common"
    for r in ["mega", "special", "mythic", "legendary", "epic", "rare", "common"]:
        cum += chances.get(r, 0)
        if roll <= cum:
            rarity = r
            break

    cards = [c for c in CARDS if c["rarity"] == rarity] or [c for c in CARDS if c["rarity"] == "common"]

    if uid and db:
        db.increment_pity(uid)
        if RARITY_ORDER.get(rarity, 0) >= RARITY_ORDER.get("epic", 2):
            db.reset_pity_for_rarity(uid, rarity)

    return random.choice(cards)


# ================== TICKET COMMANDS ==================

@router.message(Command("ticket", "getticket"))
async def cmd_ticket(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    db, uid = get_db(msg), msg.from_user.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    DatabaseManager.get_global_db().update_user(uid, msg.from_user.username, msg.from_user.first_name)

    can, rem = db.check_and_give_free_ticket(uid)
    tickets = db.get_spin_tickets(uid)
    if can:
        quest(db, uid, "collect_ticket", 1)
        await msg.reply(f"🎫 <b>Билет получен!</b>\n\n🎟️ Билетов: <b>{tickets}</b>\n💡 /spin", parse_mode="HTML")
    else:
        await msg.reply(f"⏰ Подожди <b>{rem}</b> мин.\n🎟️ Билетов: <b>{tickets}</b>", parse_mode="HTML")


@router.message(Command("tickets"))
async def cmd_tickets(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    db, uid = get_db(msg), msg.from_user.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    t, r = db.get_spin_tickets(uid), db.get_time_until_free_ticket(uid)
    txt = f"🎟️ <b>Билеты: {t}</b>\n\n"
    txt += f"⏰ Бесплатный через: <b>{r}</b> мин." if r > 0 else "✅ /ticket — получить билет"
    await msg.reply(txt, parse_mode="HTML")


# ================== SPIN COMMANDS ==================

@router.message(Command("spin"))
async def cmd_spin(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")

    db, uid, cid = get_db(msg), msg.from_user.id, msg.chat.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    DatabaseManager.get_global_db().update_user(uid, msg.from_user.username, msg.from_user.first_name)

    tickets = db.get_spin_tickets(uid)
    if tickets <= 0:
        r = db.get_time_until_free_ticket(uid)
        return await msg.reply(f"🎟️ <b>Нет билетов!</b>\n⏰ Через: <b>{r}</b> мин." if r > 0 else "🎟️ <b>Нет билетов!</b>\n✅ /ticket", parse_mode="HTML")

    if not db.use_spin_ticket(uid):
        return await msg.reply(f"{EMOJI['cross']} Ошибка!")

    boost = get_total_luck_boost(db, uid, cid)
    card = get_random_card(boost, uid, cid)
    user = db.get_user(uid)
    is_dupe = any(c["name"] == card["name"] for c in user.get("cards", []))

    db.add_card(uid, {"name": card["name"], "rarity": card["rarity"], "attack": card["attack"], "defense": card["defense"], "emoji": card["emoji"], "obtained_at": datetime.now().isoformat()})

    coins = get_coins(card["rarity"])
    if is_dupe:
        coins += coins // 2
    db.add_coins(uid, coins)

    quest(db, uid, "spin", 1)
    quest(db, uid, "get_card_rarity", 1, {"rarity": card["rarity"]})
    quest(db, uid, "earn_coins", coins)

    pity = db.get_pity_counters(uid)
    caption = SPIN_HEADERS.get(card["rarity"], SPIN_HEADERS["common"]) + format_card(card)
    if is_csm(card):
        caption += "\n\n🪚 <b>Сезон Бензопила!</b>"
    caption += f"\n\n🪙 <b>+{coins}</b>" + (" <i>(дубль!)</i>" if is_dupe else "")
    if boost > 1:
        caption += f"\n🍀 Удача: x{boost}"
    caption += f"\n🎟️ Билетов: <b>{db.get_spin_tickets(uid)}</b>"
    caption += f"\n\n🎯 <i>Epic {pity['since_epic']}/15 | Leg {pity['since_legendary']}/40</i>"

    await send_card(msg, card, caption)


@router.message(Command("multispin", "ms"))
async def cmd_multispin(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")

    uid = msg.from_user.id
    ok, rem = antispam.check(uid, "spin")
    if not ok:
        return await msg.reply(f"⏱️ {rem} сек.") if rem > 2 else None

    db, cid = get_db(msg), msg.chat.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    DatabaseManager.get_global_db().update_user(uid, msg.from_user.username, msg.from_user.first_name)

    args = msg.text.split()
    count = max(2, min(500, int(args[1]))) if len(args) > 1 and args[1].isdigit() else 5
    tickets = db.get_spin_tickets(uid)

    if tickets < 2:
        return await msg.reply(f"🎟️ <b>Минимум 2 билета!</b>\nУ тебя: {tickets}", parse_mode="HTML")

    count = min(count, tickets)
    boost = get_total_luck_boost(db, uid, cid)

    used, cards, total_coins, best = 0, [], 0, None
    user_cards = db.get_user(uid).get("cards", [])

    for _ in range(count):
        if not db.use_spin_ticket(uid):
            break
        used += 1
        card = get_random_card(boost, uid, cid)
        is_dupe = any(c["name"] == card["name"] for c in user_cards + cards)
        db.add_card(uid, {"name": card["name"], "rarity": card["rarity"], "attack": card["attack"], "defense": card["defense"], "emoji": card["emoji"]})
        cards.append(card)
        coins = get_coins(card["rarity"])
        if is_dupe:
            coins += coins // 2
        total_coins += coins
        db.add_coins(uid, coins)
        if not best or (card["attack"] + card["defense"]) > (best["attack"] + best["defense"]):
            best = card

    if not used:
        return await msg.reply(f"{EMOJI['cross']} Ошибка!")

    quest(db, uid, "spin", used)
    quest(db, uid, "multispin", 1)
    quest(db, uid, "earn_coins", total_coins)

    rarities = {}
    for c in cards:
        rarities[c["rarity"]] = rarities.get(c["rarity"], 0) + 1

    txt = f"🎰🎰🎰 <b>МУЛЬТИСПИН x{used}!</b> 🎰🎰🎰\n\n"
    for r in ["mega", "limited", "special", "mythic", "legendary", "epic", "rare", "common"]:
        if r in rarities:
            rc = RARITY_COLORS.get(r, "⚪")
            txt += f"{rc} {RARITY_NAMES.get(r, r)} x{rarities[r]}\n"

    txt += "\n<b>📋 Карты:</b>\n"
    for i, c in enumerate(cards[:15], 1):
        txt += f"{i}. {RARITY_COLORS.get(c['rarity'], '⚪')} {c['emoji']} {c['name']} (💪{c['attack']+c['defense']})\n"
    if len(cards) > 15:
        txt += f"<i>...ещё {len(cards)-15}</i>\n"

    if best:
        txt += f"\n👑 <b>Лучшая:</b> {best['emoji']} {best['name']}\n"
    txt += f"\n🪙 <b>+{total_coins}</b>"
    if boost > 1:
        txt += f"\n🍀 Удача: x{boost}"
    txt += f"\n🎟️ Осталось: <b>{db.get_spin_tickets(uid)}</b>"

    pity = db.get_pity_counters(uid)
    txt += f"\n\n🎯 <i>Epic {pity['since_epic']}/15 | Leg {pity['since_legendary']}/40</i>"

    await send_card(msg, best, txt) if best else await msg.reply(txt, parse_mode="HTML")


# ================== CARD COMMANDS ==================

@router.message(Command("mycards"))
async def cmd_mycards(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    db, uid = get_db(msg), msg.from_user.id
    user = db.get_user(uid)
    if not user or not user.get("cards"):
        return await msg.reply(f"{EMOJI['card']} Нет карт!\n/ticket → /spin", parse_mode="HTML")

    cards = user["cards"]
    counts = {}
    for c in cards:
        counts[c["rarity"]] = counts.get(c["rarity"], 0) + 1

    btns = []
    for r in ["mega", "mega_fused", "limited", "fused", "special", "mythic", "legendary", "epic", "rare", "common"]:
        if r in counts:
            btns.append(InlineKeyboardButton(text=f"{RARITY_COLORS.get(r, '⚪')} {RARITY_NAMES.get(r, r)} ({counts[r]})", callback_data=f"cards_r:{r}"))

    kb = [[b] for b in btns] + [[InlineKeyboardButton(text="📋 Все", callback_data="cards_r:all")]]
    await msg.reply(f"{EMOJI['card']} <b>Карты ({len(cards)})</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("cards_r:"))
async def cb_cards_rarity(cb: CallbackQuery):
    r = cb.data.split(":")[1]
    db = get_db(cb)
    user = db.get_user(cb.from_user.id)
    if not user or not user.get("cards"):
        return await cb.answer("Нет карт!", show_alert=True)

    cards = user["cards"] if r == "all" else [c for c in user["cards"] if c["rarity"] == r]
    if not cards:
        return await cb.answer("Пусто!", show_alert=True)

    unique = {}
    for c in cards:
        if c["name"] not in unique:
            unique[c["name"]] = {"card": c, "count": 0}
        unique[c["name"]]["count"] += 1

    sorted_cards = sorted(unique.values(), key=lambda x: -(x["card"]["attack"] + x["card"]["defense"]))

    txt = f"{EMOJI['card']} <b>{RARITY_NAMES.get(r, 'Все')} ({len(cards)})</b>\n\n"
    for item in sorted_cards[:15]:
        c, cnt = item["card"], item["count"]
        txt += f"{RARITY_COLORS.get(c['rarity'], '⚪')} {c['emoji']} {c['name']} (💪{c['attack']+c['defense']}){f' x{cnt}' if cnt > 1 else ''}\n"
    if len(sorted_cards) > 15:
        txt += f"<i>...ещё {len(sorted_cards)-15}</i>"

    try:
        await cb.message.edit_text(txt, parse_mode="HTML")
    except:
        pass
    await cb.answer()


@router.message(Command("card"))
async def cmd_card(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        return await msg.reply(f"{EMOJI['info']} <code>/card название</code>", parse_mode="HTML")

    card = find_card(args[1])
    if not card:
        return await msg.reply(f"{EMOJI['cross']} Не найдена!\n/cards /mults", parse_mode="HTML")

    db = get_db(msg)
    user = db.get_user(msg.from_user.id)
    count = sum(1 for c in user.get("cards", []) if c["name"] == card["name"]) if user else 0

    caption = f"{EMOJI['gem']} <b>Карта</b>\n\n" + format_card(card)
    if card.get("rarity") in ["fused", "mega_fused"]:
        caption += "\n\n🔮 <b>Fusion!</b> Только через /fusionspin"
    elif is_csm(card):
        caption += "\n\n🪚 <b>Сезон Бензопила!</b>"
    caption += f"\n\n📦 У тебя: <b>{count}</b>"

    await send_card(msg, card, caption)


@router.message(Command("cards", "allcards"))
async def cmd_cards(msg: Message):
    txt = f"{EMOJI['card']} <b>ВСЕ КАРТЫ ({len(CARDS)})</b>\n\n"
    for r in ["mega", "special", "mythic", "legendary", "epic", "rare", "common"]:
        lst = [c for c in CARDS if c["rarity"] == r]
        if lst:
            txt += f"<b>{RARITY_NAMES[r]}</b> ({RARITY_CHANCES.get(r, 0)}%):\n"
            for c in sorted(lst, key=lambda x: -(x["attack"]+x["defense"]))[:5]:
                txt += f"  {c['emoji']} {c['name']} (💪{c['attack']+c['defense']})\n"
            if len(lst) > 5:
                txt += f"  <i>...ещё {len(lst)-5}</i>\n"
            txt += "\n"
    txt += "💡 /limited /fusionspin"
    await msg.reply(txt, parse_mode="HTML")


@router.message(Command("collection"))
async def cmd_collection(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    db = get_db(msg)
    user = db.get_user(msg.from_user.id)
    if not user:
        return await msg.reply(f"{EMOJI['card']} /spin!")

    cards = user.get("cards", [])
    unique = len(set(c["name"] for c in cards))
    total = len(CARDS)

    txt = f"📊 <b>КОЛЛЕКЦИЯ</b>\n\n📦 Карт: <b>{len(cards)}</b>\n🎯 Уникальных: <b>{unique}/{total}</b> ({unique*100//total}%)\n\n"
    if cards:
        best = max(cards, key=lambda x: x["attack"]+x["defense"])
        txt += f"👑 <b>Лучшая:</b> {best['emoji']} {best['name']} (💪{best['attack']+best['defense']})"

    await msg.reply(txt, parse_mode="HTML")


# ================== BALANCE ==================

@router.message(Command("balance", "coins", "bal"))
async def cmd_balance(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    db, uid = get_db(msg), msg.from_user.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)

    user = db.get_user(uid)
    boost = get_total_luck_boost(db, uid, msg.chat.id)

    txt = f"💰 <b>Баланс</b>\n\n"
    txt += f"🪙 Монеты: <b>{user.get('coins', 0)}</b>\n"
    txt += f"💎 Mults: <b>{user.get('mults', 0)}</b>\n"
    txt += f"🃏 Карт: <b>{len(user.get('cards', []))}</b>\n"
    txt += f"🎟️ Билетов: <b>{db.get_spin_tickets(uid)}</b>\n"
    txt += f"🛡️ Щитов: <b>{db.get_shields(uid)}</b>\n"
    if boost > 1:
        txt += f"\n🍀 <b>Удача: x{boost}</b>\n"
        casino_chance = get_casino_win_chance(boost, "x2")
        txt += f"🎰 Шанс казино (x2): <b>{int(casino_chance * 100)}%</b>\n"
    txt += f"\n🔮 Fusions: <b>{user.get('total_fusions', 0)}</b>\n"
    txt += f"💎 Всего Mults: <b>{user.get('total_mults_earned', 0)}</b>\n\n"
    txt += "<i>💱 /exchange | 🔮 /fusionspin | 💎 /mults</i>"

    await msg.reply(txt, parse_mode="HTML")


# ================== TOP ==================

@router.message(Command("top"))
async def cmd_top(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Карты", callback_data="top_cards")],
        [InlineKeyboardButton(text="🪙 Монеты", callback_data="top_coins")],
        [InlineKeyboardButton(text="💪 Сила", callback_data="top_power")],
        [InlineKeyboardButton(text="⚔️ Арена", callback_data="top_arena")],
    ])
    await msg.reply("🏆 <b>РЕЙТИНГИ</b>", parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("top_"))
async def cb_top(cb: CallbackQuery):
    t = cb.data.split("_")[1]
    db = get_db(cb)
    medals = ["🥇", "🥈", "🥉"]

    if t == "cards":
        data = db.get_top_by_cards(10)
        txt = "🃏 <b>ТОП ПО КАРТАМ</b>\n\n"
        for i, u in enumerate(data):
            txt += f"{medals[i] if i < 3 else f'{i+1}.'} {u.get('first_name', '?')} — {u.get('cards_count', 0)} карт\n"
    elif t == "coins":
        data = db.get_top_by_coins(10)
        txt = "🪙 <b>ТОП ПО МОНЕТАМ</b>\n\n"
        for i, u in enumerate(data):
            txt += f"{medals[i] if i < 3 else f'{i+1}.'} {u.get('first_name', '?')} — {u.get('coins', 0)} 🪙\n"
    elif t == "power":
        all_cards = CARDS + FUSION_CARDS
        data = sorted(all_cards, key=lambda x: x["attack"]+x["defense"], reverse=True)[:10]
        txt = "💪 <b>СИЛЬНЕЙШИЕ КАРТЫ</b>\n\n"
        for i, c in enumerate(data):
            txt += f"{medals[i] if i < 3 else f'{i+1}.'} {c['emoji']} {c['name']} — 💪{c['attack']+c['defense']}\n"
    else:
        data = db.get_top_players(10)
        txt = "⚔️ <b>ТОП АРЕНЫ</b>\n\n"
        for i, u in enumerate(data):
            txt += f"{medals[i] if i < 3 else f'{i+1}.'} {u.get('first_name', '?')} — ⭐{u.get('rating', 0)}\n"

    if not data:
        txt += "Пока пусто!"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="top_menu")]])
    try:
        await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    except:
        pass
    await cb.answer()


@router.callback_query(F.data == "top_menu")
async def cb_top_menu(cb: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Карты", callback_data="top_cards")],
        [InlineKeyboardButton(text="🪙 Монеты", callback_data="top_coins")],
        [InlineKeyboardButton(text="💪 Сила", callback_data="top_power")],
        [InlineKeyboardButton(text="⚔️ Арена", callback_data="top_arena")],
    ])
    try:
        await cb.message.edit_text("🏆 <b>РЕЙТИНГИ</b>", parse_mode="HTML", reply_markup=kb)
    except:
        pass
    await cb.answer()


# ══════════════════════════════════════════════════════════════
#  КАЗИНО-РУЛЕТКА
# ══════════════════════════════════════════════════════════════

ROULETTE_BETS = {
    "red": {"name": "🔴 Красное", "mult": 2, "mult_type": "x2", "nums": [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]},
    "black": {"name": "⚫ Чёрное", "mult": 2, "mult_type": "x2", "nums": [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]},
    "green": {"name": "🟢 Зеро", "mult": 35, "mult_type": "x35", "nums": [0]},
    "odd": {"name": "🔷 Нечёт", "mult": 2, "mult_type": "x2", "nums": [1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35]},
    "even": {"name": "🔶 Чёт", "mult": 2, "mult_type": "x2", "nums": [2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36]},
    "low": {"name": "⬇️ 1-18", "mult": 2, "mult_type": "x2", "nums": list(range(1,19))},
    "high": {"name": "⬆️ 19-36", "mult": 2, "mult_type": "x2", "nums": list(range(19,37))},
    "d1": {"name": "1️⃣ 1-12", "mult": 3, "mult_type": "x3", "nums": list(range(1,13))},
    "d2": {"name": "2️⃣ 13-24", "mult": 3, "mult_type": "x3", "nums": list(range(13,25))},
    "d3": {"name": "3️⃣ 25-36", "mult": 3, "mult_type": "x3", "nums": list(range(25,37))},
}


def get_num_color(n: int) -> str:
    if n == 0:
        return "🟢"
    return "🔴" if n in ROULETTE_BETS["red"]["nums"] else "⚫"


def casino_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔴 x2", callback_data="cas:red"),
            InlineKeyboardButton(text="⚫ x2", callback_data="cas:black"),
            InlineKeyboardButton(text="🟢 x35", callback_data="cas:green"),
        ],
        [
            InlineKeyboardButton(text="🔷 Нечёт", callback_data="cas:odd"),
            InlineKeyboardButton(text="🔶 Чёт", callback_data="cas:even"),
        ],
        [
            InlineKeyboardButton(text="⬇️ 1-18", callback_data="cas:low"),
            InlineKeyboardButton(text="⬆️ 19-36", callback_data="cas:high"),
        ],
        [
            InlineKeyboardButton(text="1️⃣ x3", callback_data="cas:d1"),
            InlineKeyboardButton(text="2️⃣ x3", callback_data="cas:d2"),
            InlineKeyboardButton(text="3️⃣ x3", callback_data="cas:d3"),
        ],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="cas:close")],
    ])


@router.message(Command("casino", "roulette"))
async def cmd_casino(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")

    db, uid, cid = get_db(msg), msg.from_user.id, msg.chat.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)

    user = db.get_user(uid)
    coins = user.get("coins", 0)
    boost = get_total_luck_boost(db, uid, cid)

    ch_x2 = get_casino_win_chance(boost, "x2")
    ch_x3 = get_casino_win_chance(boost, "x3")
    ch_x35 = get_casino_win_chance(boost, "x35")

    if boost > 1:
        luck_txt = (
            f"\n🍀 <b>Удача: x{boost}</b>"
            f"\n📊 🔴⚫ <b>{int(ch_x2*100)}%</b> | x3 <b>{int(ch_x3*100)}%</b> | 🟢 <b>{ch_x35*100:.1f}%</b>"
        )
    else:
        luck_txt = f"\n📊 🔴⚫ <b>50%</b> | x3 <b>32%</b> | 🟢 <b>2.7%</b>"

    await msg.reply(
        f"🎰 <b>КАЗИНО</b>\n\n"
        f"💰 Баланс: <b>{coins}</b> 🪙{luck_txt}\n\n"
        f"<i>🍀 Удача повышает шанс!</i>\n"
        f"<i>x2→55% | x3→60% | x5→65% (для x2 ставок)</i>\n\n"
        f"Выбери ставку:",
        parse_mode="HTML",
        reply_markup=casino_main_kb()
    )


@router.callback_query(F.data.startswith("cas:"))
async def casino_cb(cb: CallbackQuery):
    action = cb.data.split(":")[1]

    if action == "close":
        try:
            await cb.message.delete()
        except:
            pass
        return await cb.answer()

    if action == "menu":
        db = get_db(cb)
        uid = cb.from_user.id
        cid = cb.message.chat.id
        user = db.get_user(uid)
        coins = user.get("coins", 0) if user else 0
        boost = get_total_luck_boost(db, uid, cid)
        ch = get_casino_win_chance(boost, "x2")

        luck_txt = f"\n🍀 x{boost} → {int(ch*100)}%" if boost > 1 else ""

        try:
            await cb.message.edit_text(
                f"🎰 <b>КАЗИНО</b>\n\n💰 Баланс: <b>{coins}</b> 🪙{luck_txt}\n\nВыбери ставку:",
                parse_mode="HTML", reply_markup=casino_main_kb()
            )
        except:
            pass
        return await cb.answer()

    if action in ROULETTE_BETS:
        db = get_db(cb)
        uid = cb.from_user.id
        cid = cb.message.chat.id
        user = db.get_user(uid)
        coins = user.get("coins", 0) if user else 0
        boost = get_total_luck_boost(db, uid, cid)
        bet = ROULETTE_BETS[action]
        ch = get_casino_win_chance(boost, bet["mult_type"])

        luck_txt = f"\n🍀 x{boost} → шанс {ch*100:.1f}%" if boost > 1 else f"\n📊 Шанс: {ch*100:.1f}%"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="10", callback_data=f"casbet:{action}:10"),
                InlineKeyboardButton(text="50", callback_data=f"casbet:{action}:50"),
                InlineKeyboardButton(text="100", callback_data=f"casbet:{action}:100"),
            ],
            [
                InlineKeyboardButton(text="250", callback_data=f"casbet:{action}:250"),
                InlineKeyboardButton(text="500", callback_data=f"casbet:{action}:500"),
                InlineKeyboardButton(text="1000", callback_data=f"casbet:{action}:1000"),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="cas:menu")],
        ])

        try:
            await cb.message.edit_text(
                f"🎰 <b>{bet['name']}</b> (x{bet['mult']})\n\n"
                f"💰 Баланс: <b>{coins}</b> 🪙{luck_txt}\n\nСколько ставишь?",
                parse_mode="HTML", reply_markup=kb
            )
        except:
            pass
        return await cb.answer()

    await cb.answer("❌", show_alert=True)


@router.callback_query(F.data.startswith("casbet:"))
async def casino_play(cb: CallbackQuery):
    uid = cb.from_user.id
    ok, rem = antispam.check(uid, "casino")
    if not ok:
        return await cb.answer(f"⏱️ {rem} сек!", show_alert=True)

    parts = cb.data.split(":")
    if len(parts) < 3:
        return await cb.answer("❌", show_alert=True)

    bet_type, amount_str = parts[1], parts[2]
    if bet_type not in ROULETTE_BETS:
        return await cb.answer("❌", show_alert=True)

    db = get_db(cb)
    cid = cb.message.chat.id
    user = db.get_user(uid)
    if not user:
        return await cb.answer("❌ /start!", show_alert=True)

    coins = user.get("coins", 0)
    bet_amount = coins if amount_str == "allin" else int(amount_str)

    if bet_amount <= 0:
        return await cb.answer("❌ Нет монет!", show_alert=True)
    if bet_amount > coins:
        return await cb.answer(f"❌ У тебя {coins} 🪙!", show_alert=True)
    if bet_amount < 10:
        return await cb.answer("❌ Минимум 10!", show_alert=True)

    db.remove_coins(uid, bet_amount)

    bet = ROULETTE_BETS[bet_type]
    boost = get_total_luck_boost(db, uid, cid)
    win_chance = get_casino_win_chance(boost, bet["mult_type"])

    is_win = random.random() < win_chance

    if is_win:
        result = random.choice(bet["nums"])
    else:
        losing_nums = [n for n in range(37) if n not in bet["nums"]]
        result = random.choice(losing_nums) if losing_nums else random.randint(0, 36)

    result_color = get_num_color(result)
    chance_pct = win_chance * 100

    if is_win:
        winnings = bet_amount * bet["mult"]
        db.add_coins(uid, winnings)
        profit = winnings - bet_amount
        quest(db, uid, "earn_coins", winnings)

        if result == 0 and bet_type == "green":
            header = "🟢🎉 <b>ЗЕРО!!! ДЖЕКПОТ!</b> 🎉🟢"
        elif bet["mult"] >= 3:
            header = "🎉🎉 <b>КРУПНЫЙ ВЫИГРЫШ!</b> 🎉🎉"
        else:
            header = "✅ <b>ВЫИГРЫШ!</b>"

        luck_info = f"\n🍀 x{boost} → шанс {chance_pct:.1f}%" if boost > 1 else ""

        txt = (
            f"{header}\n\n"
            f"🎱 Выпало: {result_color} <b>{result}</b>\n"
            f"🎯 Ставка: {bet['name']}\n"
            f"💵 Поставил: {bet_amount} 🪙\n"
            f"💰 Получил: <b>{winnings}</b> 🪙\n"
            f"📈 Профит: <b>+{profit}</b> 🪙{luck_info}\n\n"
            f"💵 Баланс: <b>{db.get_coins(uid)}</b> 🪙"
        )
    else:
        luck_info = f"\n🍀 x{boost} (шанс {chance_pct:.1f}%)" if boost > 1 else ""

        txt = (
            f"❌ <b>МИМО!</b>\n\n"
            f"🎱 Выпало: {result_color} <b>{result}</b>\n"
            f"🎯 Ставка: {bet['name']}\n"
            f"💸 Потеряно: <b>-{bet_amount}</b> 🪙{luck_info}\n\n"
            f"💵 Баланс: <b>{db.get_coins(uid)}</b> 🪙"
        )

    new_bal = db.get_coins(uid)
    buttons = []
    if new_bal >= bet_amount:
        buttons.append([InlineKeyboardButton(text=f"🔄 Повтор ({bet_amount} 🪙)", callback_data=f"casbet:{bet_type}:{bet_amount}")])
    if new_bal >= 10:
        buttons.append([InlineKeyboardButton(text="🎰 Новая ставка", callback_data="cas:menu")])
    buttons.append([InlineKeyboardButton(text="❌ Выйти", callback_data="cas:close")])

    try:
        await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except:
            pass
    except:
        pass

    await cb.answer()


# ══════════════════════════════════════════════════════════════
#  FUSION SPIN
# ══════════════════════════════════════════════════════════════

@router.message(Command("fusionspin", "fspin"))
async def cmd_fusionspin(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")

    uid = msg.from_user.id
    ok, rem = antispam.check(uid, "spin")
    if not ok:
        return await msg.reply(f"⏱️ {rem} сек.") if rem > 2 else None

    db, cid = get_db(msg), msg.chat.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    DatabaseManager.get_global_db().update_user(uid, msg.from_user.username, msg.from_user.first_name)

    tickets = db.get_spin_tickets(uid)
    mults = db.get_mults(uid)
    TICKET_COST, MULTS_COST = 5, 3

    boost = get_total_luck_boost(db, uid, cid)
    mega_chance = min(50, 3 * boost)
    fused_chance = min(90, 70 + (boost - 1) * 5)

    if tickets < TICKET_COST:
        return await msg.reply(
            f"🔮 <b>FUSION СПИН</b>\n\nНужно: <b>{TICKET_COST}</b> 🎫 + <b>{MULTS_COST}</b> 💎\nУ тебя: <b>{tickets}</b> 🎫\n\n"
            f"<b>Шансы</b>" + (f" (🍀 x{boost}):" if boost > 1 else ":") + f"\n├ 🌌 MEGA — <b>{mega_chance:.1f}%</b>\n├ 🔮 Fused — <b>{fused_chance:.1f}%</b>\n└ 💨 Ничего — <b>{100-mega_chance-fused_chance:.1f}%</b>",
            parse_mode="HTML"
        )

    if mults < MULTS_COST:
        return await msg.reply(f"🔮 <b>FUSION СПИН</b>\n\nНужно: <b>{MULTS_COST}</b> 💎\nУ тебя: <b>{mults}</b> 💎\n\n/mults", parse_mode="HTML")

    for _ in range(TICKET_COST):
        if not db.use_spin_ticket(uid):
            return await msg.reply(f"{EMOJI['cross']} Ошибка!")

    if not db.remove_mults(uid, MULTS_COST):
        return await msg.reply(f"{EMOJI['cross']} Ошибка!")

    if not FUSION_CARDS:
        db.add_spin_tickets(uid, TICKET_COST)
        db.add_mults(uid, MULTS_COST)
        return await msg.reply(f"{EMOJI['cross']} Нет Fusion карт!")

    regular = [c for c in FUSION_CARDS if c.get("rarity") == "fused"]
    mega = [c for c in FUSION_CARDS if c.get("rarity") == "mega_fused"]

    roll = random.uniform(0, 100)

    if roll <= mega_chance and mega:
        card = random.choice(mega)
        got_card = True
    elif roll <= mega_chance + fused_chance and regular:
        card = random.choice(regular)
        got_card = True
    else:
        got_card = False
        card = None

    if got_card and card:
        user = db.get_user(uid)
        is_dupe = any(c["name"] == card["name"] for c in user.get("cards", []))
        db.add_card(uid, {"name": card["name"], "rarity": card["rarity"], "attack": card["attack"], "defense": card["defense"], "emoji": card["emoji"], "obtained_at": datetime.now().isoformat()})

        base_coins = (card["attack"] + card["defense"]) // 2
        coin_reward = int(base_coins * boost) if boost > 1 else base_coins
        if is_dupe:
            coin_reward += coin_reward // 2
        db.add_coins(uid, coin_reward)

        quest(db, uid, "spin", 1)
        quest(db, uid, "earn_coins", coin_reward)

        caption = SPIN_HEADERS.get(card["rarity"], "🔮 <b>FUSION!</b>\n\n") + format_card(card)
        caption += f"\n\n🪙 <b>+{coin_reward}</b>" + (" <i>(дубль!)</i>" if is_dupe else "")
        if boost > 1:
            caption += f"\n🍀 x{boost}"
        caption += f"\n\n💸 -{TICKET_COST}🎫 -{MULTS_COST}💎\n🎟️ <b>{db.get_spin_tickets(uid)}</b> | 💎 <b>{db.get_mults(uid)}</b>"
        await send_card(msg, card, caption)
    else:
        consolation = int(random.randint(30, 80) * (boost if boost > 1 else 1))
        db.add_coins(uid, consolation)
        luck_txt = f"\n🍀 x{boost} не сработала..." if boost > 1 else ""
        await msg.reply(
            f"🔮 <b>FUSION СПИН</b>\n\n💨 <b>Не повезло...</b>{luck_txt}\n\n🪙 +<b>{consolation}</b>\n\n"
            f"💸 -{TICKET_COST}🎫 -{MULTS_COST}💎\n🎟️ <b>{db.get_spin_tickets(uid)}</b> | 💎 <b>{db.get_mults(uid)}</b>\n\n"
            f"<i>Шанс MEGA: {mega_chance:.1f}%</i>",
            parse_mode="HTML"
        )


# ══════════════════════════════════════════════════════════════
#  MULTI FUSION SPIN
# ══════════════════════════════════════════════════════════════

@router.message(Command("multifusion", "mfspin", "mf"))
async def cmd_multi_fusion(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")

    uid = msg.from_user.id
    ok, rem = antispam.check(uid, "spin")
    if not ok:
        return await msg.reply(f"⏱️ {rem} сек.") if rem > 2 else None

    db, cid = get_db(msg), msg.chat.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    DatabaseManager.get_global_db().update_user(uid, msg.from_user.username, msg.from_user.first_name)

    args = msg.text.split()
    count = max(2, min(500, int(args[1]))) if len(args) > 1 and args[1].isdigit() else 3

    TPC, MPC = 10, 5
    total_tickets = TPC * count
    total_mults = MPC * count
    tickets = db.get_spin_tickets(uid)
    mults = db.get_mults(uid)

    base_boost = get_total_luck_boost(db, uid, cid)
    effective_boost = 1.0 + (base_boost - 1.0) * 0.3
    mega_chance = min(15, 1.0 * effective_boost)
    fused_chance = min(60, 40.0 * effective_boost)

    if tickets < total_tickets or mults < total_mults:
        mx = min(tickets // TPC, mults // MPC)
        return await msg.reply(
            f"🔮💀 <b>MULTI FUSION</b>\n\n❌ Мало ресурсов!\n\n"
            f"Нужно: {total_tickets}🎫 + {total_mults}💎\nУ тебя: {tickets}🎫 + {mults}💎\n\n"
            f"{'✅ Можешь: <b>'+str(mx)+'</b>' if mx > 0 else '❌ Копи!'}\n<code>/mf [кол-во]</code>",
            parse_mode="HTML"
        )

    for _ in range(total_tickets):
        if not db.use_spin_ticket(uid):
            return await msg.reply(f"{EMOJI['cross']} Ошибка!")
    if not db.remove_mults(uid, total_mults):
        db.add_spin_tickets(uid, total_tickets)
        return await msg.reply(f"{EMOJI['cross']} Ошибка!")
    if not FUSION_CARDS:
        db.add_spin_tickets(uid, total_tickets)
        db.add_mults(uid, total_mults)
        return await msg.reply(f"{EMOJI['cross']} Нет Fusion карт!")

    regular = [c for c in FUSION_CARDS if c.get("rarity") == "fused"]
    mega = [c for c in FUSION_CARDS if c.get("rarity") == "mega_fused"]

    results = {"mega": [], "fused": [], "nothing": 0}
    total_coins, best_card = 0, None
    user_cards = db.get_user(uid).get("cards", [])
    new_cards = []

    for _ in range(count):
        roll = random.uniform(0, 100)
        if roll <= mega_chance and mega:
            card = random.choice(mega)
            results["mega"].append(card)
            new_cards.append(card)
        elif roll <= mega_chance + fused_chance and regular:
            card = random.choice(regular)
            results["fused"].append(card)
            new_cards.append(card)
        else:
            results["nothing"] += 1
            total_coins += random.randint(10, 30)
            continue

        is_dupe = any(c["name"] == card["name"] for c in user_cards + new_cards[:-1])
        db.add_card(uid, {"name": card["name"], "rarity": card["rarity"], "attack": card["attack"], "defense": card["defense"], "emoji": card["emoji"], "obtained_at": datetime.now().isoformat()})
        cr = (card["attack"] + card["defense"]) // 3
        if is_dupe:
            cr += cr // 2
        total_coins += cr
        if not best_card or (card["attack"]+card["defense"]) > (best_card["attack"]+best_card["defense"]):
            best_card = card

    db.add_coins(uid, total_coins)
    quest(db, uid, "spin", count)
    quest(db, uid, "earn_coins", total_coins)

    mc, fc, nc = len(results["mega"]), len(results["fused"]), results["nothing"]
    header = "🌌💀 <b>MULTI FUSION — MEGA!!!</b> 💀🌌" if mc > 0 else ("🔮💀 <b>MULTI FUSION</b> 💀🔮" if fc > 0 else "💀💨 <b>MULTI FUSION — ПРОВАЛ!</b> 💨💀")

    txt = f"{header}\n\n🎰 Спинов: <b>{count}</b>\n💸 -{total_tickets}🎫 -{total_mults}💎\n\n"
    if mc: txt += f"🌌 MEGA: <b>{mc}</b>\n"
    if fc: txt += f"🔮 Fused: <b>{fc}</b>\n"
    if nc: txt += f"💨 Пусто: <b>{nc}</b>\n"

    all_won = results["mega"] + results["fused"]
    if all_won:
        txt += f"\n<b>🃏 Карты:</b>\n"
        for i, c in enumerate(all_won[:10], 1):
            txt += f"{i}. {'🌌' if c['rarity']=='mega_fused' else '🔮'} {c['emoji']} {c['name']} (💪{c['attack']+c['defense']})\n"
        if len(all_won) > 10:
            txt += f"<i>...ещё {len(all_won)-10}</i>\n"

    txt += f"\n🪙 <b>+{total_coins}</b>\n🎟️ <b>{db.get_spin_tickets(uid)}</b> | 💎 <b>{db.get_mults(uid)}</b>"

    if best_card:
        await send_card(msg, best_card, txt)
    else:
        await msg.reply(txt, parse_mode="HTML")


# ══════════════════════════════════════════════════════════════
#  СТАТИСТИКА
# ══════════════════════════════════════════════════════════════

@router.message(Command("spinstats", "stats"))
async def cmd_stats(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    db = get_db(msg)
    user = db.get_user(msg.from_user.id)
    if not user or not user.get("cards"):
        return await msg.reply("📊 /spin сначала!")

    cards = user["cards"]
    rarities = {}
    for c in cards:
        rarities[c["rarity"]] = rarities.get(c["rarity"], 0) + 1

    boost = get_total_luck_boost(db, msg.from_user.id, msg.chat.id)
    pity = db.get_pity_counters(msg.from_user.id)

    txt = f"📊 <b>СТАТИСТИКА</b>\n\n🃏 Карт: <b>{len(cards)}</b>\n"
    if boost > 1:
        txt += f"🍀 <b>Удача: x{boost}</b>\n🎰 Казино (x2): <b>{int(get_casino_win_chance(boost, 'x2')*100)}%</b>\n"
    txt += "\n"

    for r in ["mega", "mega_fused", "limited", "fused", "special", "mythic", "legendary", "epic", "rare", "common"]:
        if r in rarities:
            txt += f"{RARITY_COLORS.get(r, '⚪')} {RARITY_NAMES.get(r, r)}: {rarities[r]}\n"

    txt += f"\n🎯 Epic: {pity['since_epic']}/15 | Leg: {pity['since_legendary']}/40 | Myth: {pity['since_mythic']}/100"
    await msg.reply(txt, parse_mode="HTML")


@router.message(Command("fusionhelp", "fhelp"))
async def cmd_fusion_help(msg: Message):
    await msg.reply(
        f"🔮 <b>FUSION СПИНЫ</b>\n\n"
        f"<b>1️⃣ /fusionspin</b> — 5🎫+3💎\n├ 🌌 MEGA ~3% | 🔮 Fused ~70%\n\n"
        f"<b>2️⃣ /multifusion</b> 💀 — 10🎫+5💎/спин\n├ 🌌 MEGA ~1% | 🔮 Fused ~40%\n\n"
        f"<code>/mf 5</code> — 5 спинов",
        parse_mode="HTML"
    )