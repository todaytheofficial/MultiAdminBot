# handlers/cards.py
import random
import os
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, ChatMemberOwner
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
import asyncio
from typing import Dict, Set
import g4f

g4f.debug.version_check = False

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
        self.cd = {"spin": 3, "ticket": 2, "command": 1, "callback": 0.5}

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
        await send_card(msg, card, caption, reply)
    except TelegramBadRequest:
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


def get_random_card(boost=1.0, uid=None, cid=None):
    db = DatabaseManager.get_db(cid) if cid else None

    # Pity system
    if uid and db:
        pity = db.get_pity_counters(uid)
        for r, th in [("mythic", 100), ("legendary", 40), ("epic", 15)]:
            if pity[f"since_{r}"] >= PITY_THRESHOLDS.get(r, th):
                cards = [c for c in CARDS if c["rarity"] == r]
                if cards:
                    db.reset_pity_for_rarity(uid, r)
                    return random.choice(cards)

    # Limited cards
    if db:
        lim = [c for c in LIMITED_CARDS if check_limited(c) and db.get_limited_card_count(c["name"]) < c.get("max_copies", 999)]
        if lim and random.random() < 0.02 * boost:
            c = random.choice(lim)
            if uid:
                db.issue_limited_card(c["name"], uid)
                db.reset_pity_for_rarity(uid, "limited")
            return c

    # Regular roll
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


@router.message(Command("givetickets", "giveticket"))
async def cmd_give_tickets(msg: Message, bot: Bot):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    if not await is_admin(msg, bot):
        return await msg.reply(f"{EMOJI['cross']} Нет прав!")

    db, args = get_db(msg), msg.text.split()
    tid, name, amount = None, None, 1

    if msg.reply_to_message:
        t = msg.reply_to_message.from_user
        tid, name = t.id, t.first_name
        if len(args) > 1:
            amount = int(args[1]) if args[1].isdigit() else 1
    elif len(args) > 1 and args[1].startswith("@"):
        u = DatabaseManager.get_global_db().find_by_username(args[1][1:])
        if not u:
            return await msg.reply(f"{EMOJI['cross']} Не найден!")
        tid, name = u['user_id'], u.get('first_name', args[1])
        if len(args) > 2:
            amount = int(args[2]) if args[2].isdigit() else 1

    if not tid:
        return await msg.reply("🎫 <code>/givetickets @user [кол-во]</code>", parse_mode="HTML")

    amount = max(1, min(100, amount))
    if not db.get_user(tid):
        db.create_user(tid, None, name)
    db.add_spin_tickets(tid, amount)
    await msg.reply(f"🎫 <b>Выдано!</b>\n👤 {name}\n➕ {amount} билетов\n🎟️ Всего: {db.get_spin_tickets(tid)}", parse_mode="HTML")


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

    boost = DatabaseManager.get_global_db().get_spin_boost(uid)
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
    count = max(2, min(200, int(args[1]))) if len(args) > 1 and args[1].isdigit() else 5
    tickets = db.get_spin_tickets(uid)

    if tickets < 2:
        return await msg.reply(f"🎟️ <b>Минимум 2 билета!</b>\nУ тебя: {tickets}", parse_mode="HTML")

    count = min(count, tickets)
    boost = DatabaseManager.get_global_db().get_spin_boost(uid)

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

    txt = f"📊 <b>КОЛЛЕКЦИЯ</b>\n\n"
    txt += f"📦 Карт: <b>{len(cards)}</b>\n"
    txt += f"🎯 Уникальных: <b>{unique}/{total}</b> ({unique*100//total}%)\n\n"

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
    boost = DatabaseManager.get_global_db().get_spin_boost(uid)

    txt = f"💰 <b>Баланс</b>\n\n"
    txt += f"🪙 Монеты: <b>{user.get('coins', 0)}</b>\n"
    txt += f"💎 Mults: <b>{user.get('mults', 0)}</b>\n"
    txt += f"🃏 Карт: <b>{len(user.get('cards', []))}</b>\n"
    txt += f"🎟️ Билетов: <b>{db.get_spin_tickets(uid)}</b>\n"
    txt += f"🛡️ Щитов: <b>{db.get_shields(uid)}</b>\n"
    if boost > 1:
        txt += f"\n🍀 <b>Удача: x{boost}</b>\n"
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


# ================== ADMIN ==================

@router.message(Command("givecard"))
async def cmd_givecard(msg: Message, bot: Bot):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    if not await is_admin(msg, bot):
        return await msg.reply(f"{EMOJI['cross']} Нет прав!")

    db, args = get_db(msg), msg.text.split(maxsplit=2)
    tid, name, card_name = None, None, None

    if msg.reply_to_message:
        t = msg.reply_to_message.from_user
        tid, name = t.id, t.first_name
        card_name = args[1] if len(args) > 1 else None
    elif len(args) > 2 and args[1].startswith("@"):
        u = DatabaseManager.get_global_db().find_by_username(args[1][1:])
        if u:
            tid, name, card_name = u['user_id'], u.get('first_name'), args[2]

    if not card_name:
        return await msg.reply("🎁 <code>/givecard @user карта</code>", parse_mode="HTML")

    card = find_card(card_name)
    if not card:
        return await msg.reply(f"{EMOJI['cross']} Карта не найдена!")

    if not db.get_user(tid):
        db.create_user(tid, None, name)
    db.add_card(tid, {"name": card["name"], "rarity": card["rarity"], "attack": card["attack"], "defense": card["defense"], "emoji": card["emoji"]})

    await send_card(msg, card, f"🎁 <b>Выдано!</b>\n👤 {name}\n\n{format_card(card)}")


@router.message(Command("givecoins"))
async def cmd_givecoins(msg: Message, bot: Bot):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    if not await is_admin(msg, bot):
        return await msg.reply(f"{EMOJI['cross']} Нет прав!")

    db, args = get_db(msg), msg.text.split()
    tid, name, amount = None, None, 100

    if msg.reply_to_message:
        t = msg.reply_to_message.from_user
        tid, name = t.id, t.first_name
        if len(args) > 1 and args[1].isdigit():
            amount = int(args[1])
    elif len(args) > 1 and args[1].startswith("@"):
        u = DatabaseManager.get_global_db().find_by_username(args[1][1:])
        if u:
            tid, name = u['user_id'], u.get('first_name')
        if len(args) > 2 and args[2].isdigit():
            amount = int(args[2])

    if not tid:
        return await msg.reply("🪙 <code>/givecoins @user [кол-во]</code>", parse_mode="HTML")

    amount = max(1, min(1000000, amount))
    if not db.get_user(tid):
        db.create_user(tid, None, name)
    db.add_coins(tid, amount)

    await msg.reply(f"🪙 <b>Выдано!</b>\n👤 {name}\n➕ {amount} 🪙\n💰 Баланс: {db.get_coins(tid)}", parse_mode="HTML")


@router.message(Command("boostspin", "giveluck", "удача"))
async def cmd_boostspin(msg: Message, bot: Bot):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    if not await is_admin(msg, bot):
        return await msg.reply(f"{EMOJI['cross']} Нет прав!")

    args = msg.text.split()
    tid, name, mult, hours = None, None, 2.0, 24

    if msg.reply_to_message:
        t = msg.reply_to_message.from_user
        tid, name = t.id, t.first_name
        if len(args) > 1:
            mult = float(args[1]) if args[1].replace('.', '').isdigit() else 2.0
        if len(args) > 2:
            hours = int(args[2]) if args[2].isdigit() else 24
    elif len(args) > 1 and args[1].startswith("@"):
        u = DatabaseManager.get_global_db().find_by_username(args[1][1:])
        if u:
            tid, name = u['user_id'], u.get('first_name')
        if len(args) > 2:
            mult = float(args[2]) if args[2].replace('.', '').isdigit() else 2.0
        if len(args) > 3:
            hours = int(args[3]) if args[3].isdigit() else 24

    if not tid:
        return await msg.reply("🍀 <code>/boostspin @user [множитель] [часы]</code>\n\nУдача влияет на:\n• Шансы редких карт\n• Шансы в казино\n• Шансы Fusion карт", parse_mode="HTML")

    mult, hours = max(1.0, min(10.0, mult)), max(1, min(720, hours))
    DatabaseManager.get_global_db().set_spin_boost(tid, mult, hours)

    await msg.reply(f"🍀 <b>Удача выдана!</b>\n👤 {name}\n📈 x{mult} на {hours}ч\n\n<i>Влияет на спины, казино и fusion!</i>", parse_mode="HTML")


@router.message(Command("resetcd"))
async def cmd_resetcd(msg: Message, bot: Bot):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    if not await is_admin(msg, bot):
        return await msg.reply(f"{EMOJI['cross']} Нет прав!")

    db = get_db(msg)
    if msg.reply_to_message:
        tid = msg.reply_to_message.from_user.id
        name = msg.reply_to_message.from_user.first_name
    else:
        return await msg.reply("Ответь на сообщение!")

    if not db.get_user(tid):
        return await msg.reply("Пользователь не найден!")
    db.reset_free_ticket_cooldown(tid)
    await msg.reply(f"✅ Кулдаун сброшен для {name}!")


# ══════════════════════════════════════════════════════════════
#  КАЗИНО-РУЛЕТКА С УДАЧЕЙ (БЕЗ АНИМАЦИИ)
# ══════════════════════════════════════════════════════════════

ROULETTE_BETS = {
    "red": {"name": "🔴 Красное", "mult": 2, "nums": [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]},
    "black": {"name": "⚫ Чёрное", "mult": 2, "nums": [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]},
    "green": {"name": "🟢 Зеро", "mult": 35, "nums": [0]},
    "odd": {"name": "🔷 Нечёт", "mult": 2, "nums": [1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35]},
    "even": {"name": "🔶 Чёт", "mult": 2, "nums": [2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36]},
    "low": {"name": "⬇️ 1-18", "mult": 2, "nums": list(range(1,19))},
    "high": {"name": "⬆️ 19-36", "mult": 2, "nums": list(range(19,37))},
    "d1": {"name": "1️⃣ 1-12", "mult": 3, "nums": list(range(1,13))},
    "d2": {"name": "2️⃣ 13-24", "mult": 3, "nums": list(range(13,25))},
    "d3": {"name": "3️⃣ 25-36", "mult": 3, "nums": list(range(25,37))},
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


@router.message(Command("casino", "казино", "roulette"))
async def cmd_casino(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")

    db = get_db(msg)
    uid = msg.from_user.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)

    user = db.get_user(uid)
    coins = user.get("coins", 0)
    boost = DatabaseManager.get_global_db().get_spin_boost(uid)

    luck_txt = f"\n🍀 <b>Удача: x{boost}</b> — шанс выше!" if boost > 1 else ""

    await msg.reply(
        f"🎰 <b>КАЗИНО</b>\n\n"
        f"💰 Баланс: <b>{coins}</b> 🪙{luck_txt}\n\n"
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
        user = db.get_user(uid)
        coins = user.get("coins", 0) if user else 0
        boost = DatabaseManager.get_global_db().get_spin_boost(uid)
        luck_txt = f"\n🍀 <b>Удача: x{boost}</b>" if boost > 1 else ""

        try:
            await cb.message.edit_text(
                f"🎰 <b>КАЗИНО</b>\n\n💰 Баланс: <b>{coins}</b> 🪙{luck_txt}\n\nВыбери ставку:",
                parse_mode="HTML",
                reply_markup=casino_main_kb()
            )
        except:
            pass
        return await cb.answer()

    if action in ROULETTE_BETS:
        db = get_db(cb)
        uid = cb.from_user.id
        user = db.get_user(uid)
        coins = user.get("coins", 0) if user else 0
        boost = DatabaseManager.get_global_db().get_spin_boost(uid)

        bet = ROULETTE_BETS[action]
        luck_txt = f"\n🍀 Удача: x{boost}" if boost > 1 else ""

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
            [InlineKeyboardButton(text="🎲 ALL-IN", callback_data=f"casbet:{action}:allin")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="cas:menu")],
        ])

        try:
            await cb.message.edit_text(
                f"🎰 <b>{bet['name']}</b> (x{bet['mult']})\n\n"
                f"💰 Баланс: <b>{coins}</b> 🪙{luck_txt}\n\n"
                f"Сколько ставишь?",
                parse_mode="HTML",
                reply_markup=kb
            )
        except:
            pass
        return await cb.answer()

    await cb.answer("❌ Ошибка!", show_alert=True)


@router.callback_query(F.data.startswith("casbet:"))
async def casino_play(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) < 3:
        return await cb.answer("❌ Ошибка!", show_alert=True)

    bet_type, amount_str = parts[1], parts[2]

    if bet_type not in ROULETTE_BETS:
        return await cb.answer("❌ Ошибка!", show_alert=True)

    db = get_db(cb)
    uid = cb.from_user.id
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
    boost = DatabaseManager.get_global_db().get_spin_boost(uid)

    # ═══════════════════════════════════════════════
    #  УДАЧА ВЛИЯЕТ НА ШАНС ВЫИГРЫША!
    # ═══════════════════════════════════════════════

    # Базовый шанс = количество выигрышных чисел / 37
    base_win_chance = len(bet["nums"]) / 37

    # С удачей шанс увеличивается (но не больше 95%)
    # x2 удача = +50% к шансу, x3 = +100%, x5 = +200%
    boosted_chance = min(0.95, base_win_chance * (1 + (boost - 1) * 0.5))

    # Крутим!
    if random.random() < boosted_chance:
        # ВЫИГРЫШ - выбираем случайное число из выигрышных
        result = random.choice(bet["nums"])
        is_win = True
    else:
        # ПРОИГРЫШ - выбираем число НЕ из выигрышных
        losing_nums = [n for n in range(37) if n not in bet["nums"]]
        result = random.choice(losing_nums) if losing_nums else random.randint(0, 36)
        is_win = False

    result_color = get_num_color(result)

    if is_win:
        winnings = bet_amount * bet["mult"]

        # Бонус от удачи к выигрышу
        if boost > 1:
            bonus = int(bet_amount * (boost - 1) * 0.1)
            winnings += bonus
            bonus_txt = f" (+{bonus} бонус)"
        else:
            bonus_txt = ""

        db.add_coins(uid, winnings)
        profit = winnings - bet_amount
        quest(db, uid, "earn_coins", winnings)

        if result == 0:
            header = "🟢🎉 <b>ЗЕРО!!!</b> 🎉🟢"
        else:
            header = "✅ <b>ВЫИГРЫШ!</b>"

        luck_info = f"\n🍀 Удача x{boost} — шанс был {int(boosted_chance*100)}%!" if boost > 1 else ""

        txt = (
            f"{header}\n\n"
            f"🎱 Выпало: {result_color} <b>{result}</b>\n"
            f"🎯 Ставка: {bet['name']}\n"
            f"💵 Ставка: {bet_amount} 🪙\n"
            f"💰 Выигрыш: <b>{winnings}</b> 🪙{bonus_txt}\n"
            f"📈 Профит: <b>+{profit}</b> 🪙{luck_info}\n\n"
            f"💵 Баланс: <b>{db.get_coins(uid)}</b> 🪙"
        )
    else:
        luck_info = f"\n🍀 Удача x{boost} не помогла..." if boost > 1 else ""

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
        buttons.append([InlineKeyboardButton(text=f"🔄 Повтор ({bet_amount})", callback_data=f"casbet:{bet_type}:{bet_amount}")])
    buttons.append([InlineKeyboardButton(text="🎰 Новая ставка", callback_data="cas:menu")])
    buttons.append([InlineKeyboardButton(text="❌ Выйти", callback_data="cas:close")])

    try:
        await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except:
        await cb.message.answer(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    await cb.answer()


# ══════════════════════════════════════════════════════════════
#  FUSIONSPIN С УДАЧЕЙ — МЕГА ЛЕГКО ПАДАЕТ!
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
    TICKET_COST = 5
    MULTS_COST = 3

    boost = DatabaseManager.get_global_db().get_spin_boost(uid)

    # ═══════════════════════════════════════════════
    #  ШАНСЫ С УДАЧЕЙ
    # ═══════════════════════════════════════════════

    # Базовые шансы
    base_mega = 3  # 3%
    base_fused = 70  # 70%
    # Остальное = ничего

    # С удачей x2: mega = 6%, fused = 85%
    # С удачей x5: mega = 15%, fused = 80%
    # С удачей x10: mega = 30%, fused = 65%
    mega_chance = min(50, base_mega * boost)  # До 50% максимум
    fused_chance = min(90, base_fused + (boost - 1) * 5)  # +5% за каждый x1

    if tickets < TICKET_COST:
        return await msg.reply(
            f"🔮 <b>FUSION СПИН</b>\n\n"
            f"Нужно: <b>{TICKET_COST}</b> 🎫 + <b>{MULTS_COST}</b> 💎\n"
            f"У тебя: <b>{tickets}</b> 🎫\n\n"
            f"<b>Шансы</b>" + (f" (🍀 x{boost}):" if boost > 1 else ":") + "\n"
            f"├ 🌌 MEGA Fused — <b>{mega_chance:.1f}%</b>\n"
            f"├ 🔮 Fused — <b>{fused_chance:.1f}%</b>\n"
            f"└ 💨 Ничего — <b>{100 - mega_chance - fused_chance:.1f}%</b>",
            parse_mode="HTML"
        )

    if mults < MULTS_COST:
        return await msg.reply(
            f"🔮 <b>FUSION СПИН</b>\n\n"
            f"Нужно: <b>{MULTS_COST}</b> 💎\n"
            f"У тебя: <b>{mults}</b> 💎\n\n"
            f"/mults — получить Mults",
            parse_mode="HTML"
        )

    for _ in range(TICKET_COST):
        if not db.use_spin_ticket(uid):
            return await msg.reply(f"{EMOJI['cross']} Ошибка!")

    if not db.remove_mults(uid, MULTS_COST):
        return await msg.reply(f"{EMOJI['cross']} Ошибка!")

    try:
        from config import FUSION_CARDS
    except ImportError:
        db.add_spin_tickets(uid, TICKET_COST)
        db.add_mults(uid, MULTS_COST)
        return await msg.reply(f"{EMOJI['cross']} Fusion карты недоступны!")

    if not FUSION_CARDS:
        db.add_spin_tickets(uid, TICKET_COST)
        db.add_mults(uid, MULTS_COST)
        return await msg.reply(f"{EMOJI['cross']} Нет Fusion карт!")

    regular = [c for c in FUSION_CARDS if c.get("rarity") == "fused"]
    mega = [c for c in FUSION_CARDS if c.get("rarity") == "mega_fused"]

    # Крутим с учётом шансов
    roll = random.uniform(0, 100)

    if roll <= mega_chance and mega:
        card = random.choice(mega)
        is_mega = True
        got_card = True
    elif roll <= mega_chance + fused_chance and regular:
        card = random.choice(regular)
        is_mega = False
        got_card = True
    else:
        got_card = False
        card = None
        is_mega = False

    if got_card and card:
        user = db.get_user(uid)
        is_dupe = any(c["name"] == card["name"] for c in user.get("cards", []))

        db.add_card(uid, {
            "name": card["name"],
            "rarity": card["rarity"],
            "attack": card["attack"],
            "defense": card["defense"],
            "emoji": card["emoji"],
            "obtained_at": datetime.now().isoformat()
        })

        base_coins = (card["attack"] + card["defense"]) // 2
        coin_reward = int(base_coins * boost) if boost > 1 else base_coins
        if is_dupe:
            coin_reward += coin_reward // 2
        db.add_coins(uid, coin_reward)

        quest(db, uid, "spin", 1)
        quest(db, uid, "earn_coins", coin_reward)

        header = SPIN_HEADERS.get(card["rarity"], "🔮 <b>FUSION!</b>\n\n")

        caption = header + format_card(card)
        caption += f"\n\n🪙 <b>+{coin_reward}</b>" + (" <i>(дубль!)</i>" if is_dupe else "")
        if boost > 1:
            caption += f"\n🍀 Удача x{boost} помогла!"
        caption += f"\n\n💸 -{TICKET_COST} 🎫 -{MULTS_COST} 💎"
        caption += f"\n🎟️ Осталось: <b>{db.get_spin_tickets(uid)}</b>"
        caption += f"\n💎 Mults: <b>{db.get_mults(uid)}</b>"

        await send_card(msg, card, caption)

    else:
        base_consolation = random.randint(30, 80)
        consolation = int(base_consolation * boost) if boost > 1 else base_consolation
        db.add_coins(uid, consolation)

        luck_txt = f"\n🍀 Удача x{boost} не сработала..." if boost > 1 else ""

        await msg.reply(
            f"🔮 <b>FUSION СПИН</b>\n\n"
            f"💨 <b>Не повезло...</b>{luck_txt}\n\n"
            f"🪙 Утешение: <b>+{consolation}</b>\n\n"
            f"💸 -{TICKET_COST} 🎫 -{MULTS_COST} 💎\n"
            f"🎟️ Осталось: <b>{db.get_spin_tickets(uid)}</b>\n"
            f"💎 Mults: <b>{db.get_mults(uid)}</b>\n\n"
            f"<i>Шанс MEGA был {mega_chance:.1f}%, пробуй ещё!</i>",
            parse_mode="HTML"
        )


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

    boost = DatabaseManager.get_global_db().get_spin_boost(msg.from_user.id)
    pity = db.get_pity_counters(msg.from_user.id)

    txt = f"📊 <b>СТАТИСТИКА</b>\n\n🃏 Карт: <b>{len(cards)}</b>\n"
    if boost > 1:
        txt += f"🍀 <b>Удача: x{boost}</b>\n"
    txt += "\n"

    for r in ["mega", "mega_fused", "limited", "fused", "special", "mythic", "legendary", "epic", "rare", "common"]:
        if r in rarities:
            txt += f"{RARITY_COLORS.get(r, '⚪')} {RARITY_NAMES.get(r, r)}: {rarities[r]}\n"

    txt += f"\n🎯 <b>Pity:</b>\n"
    txt += f"Epic: {pity['since_epic']}/15\n"
    txt += f"Leg: {pity['since_legendary']}/40\n"
    txt += f"Mythic: {pity['since_mythic']}/100"

    await msg.reply(txt, parse_mode="HTML")