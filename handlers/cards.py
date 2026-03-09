# handlers/cards.py
import random
import os
import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.exceptions import TelegramRetryAfter
import asyncio
from typing import Dict, Set

from config import (
    EMOJI, CARDS, RARITY_CHANCES, RARITY_NAMES, RARITY_COLORS,
    CARDS_IMAGES_PATH
)
from database import DatabaseManager

router = Router()
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════
#                    НАСТРОЙКИ КД
# ══════════════════════════════════════════════════

SPIN_COOLDOWN_MINUTES = 30      # КД на /spin — 30 минут
MULTISPIN_COOLDOWN_MINUTES = 60  # КД на /multispin — 1 час
MULTISPIN_MAX = 50               # Максимум карт за один мультиспин


# ══════════════════════════════════════════════════
#                    HELPERS
# ══════════════════════════════════════════════════

class AntiSpam:
    def __init__(self):
        self.last_action: Dict[int, Dict[str, datetime]] = {}
        self.warnings: Dict[int, int] = {}
        self.blocked: Set[int] = set()
        self.cd = {"spin": 2, "ticket": 2, "command": 1}

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
}

SPIN_HEADERS = {
    "mega": "🌌🌌🌌 <b>MEGA!!!</b> 🌌🌌🌌\n\n",
    "special": "💎💎💎 <b>SPECIAL!!!</b> 💎💎💎\n\n",
    "mythic": "🔴🔴🔴 <b>MYTHIC!!</b> 🔴🔴🔴\n\n",
    "legendary": "🟡🟡🟡 <b>LEGENDARY!</b> 🟡🟡🟡\n\n",
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


def get_coins(r):
    return random.randint(*COIN_REWARDS.get(r, (1, 3)))


def find_card(name: str):
    n = name.lower().strip()
    for c in CARDS:
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
            except Exception:
                pass
        await (msg.reply if reply else msg.answer)(caption, parse_mode="HTML")
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await send_card(msg, card, caption, reply)
        except Exception:
            pass
    except Exception:
        pass


def get_random_card():
    roll, cum = random.uniform(0, 100), 0
    rarity = "common"
    for r in ["mega", "special", "mythic", "legendary", "epic", "rare", "common"]:
        cum += RARITY_CHANCES.get(r, 0)
        if roll <= cum:
            rarity = r
            break

    cards = [c for c in CARDS if c["rarity"] == rarity] or [c for c in CARDS if c["rarity"] == "common"]
    return random.choice(cards)


def format_time_remaining(minutes: int) -> str:
    """Форматирует оставшееся время"""
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        if mins > 0:
            return f"{hours}ч {mins}мин"
        return f"{hours}ч"
    return f"{minutes}мин"


# ══════════════════════════════════════════════════
#                 COOLDOWN HELPERS
# ══════════════════════════════════════════════════

def get_spin_cooldown(db, uid: int) -> int:
    """Возвращает оставшееся время КД на спин в минутах (0 = можно спинить)"""
    user = db.get_user(uid)
    if not user:
        return 0
    
    last_spin = user.get("last_spin_time")
    if not last_spin:
        return 0
    
    try:
        if isinstance(last_spin, str):
            last_spin = datetime.fromisoformat(last_spin)
        
        elapsed = (datetime.now() - last_spin).total_seconds() / 60
        remaining = SPIN_COOLDOWN_MINUTES - elapsed
        
        if remaining <= 0:
            return 0
        return int(remaining) + 1
    except Exception:
        return 0


def set_spin_cooldown(db, uid: int):
    """Устанавливает время последнего спина"""
    db.update_user_field(uid, "last_spin_time", datetime.now().isoformat())


def get_multispin_cooldown(db, uid: int) -> int:
    """Возвращает оставшееся время КД на мультиспин в минутах"""
    user = db.get_user(uid)
    if not user:
        return 0
    
    last_multispin = user.get("last_multispin_time")
    if not last_multispin:
        return 0
    
    try:
        if isinstance(last_multispin, str):
            last_multispin = datetime.fromisoformat(last_multispin)
        
        elapsed = (datetime.now() - last_multispin).total_seconds() / 60
        remaining = MULTISPIN_COOLDOWN_MINUTES - elapsed
        
        if remaining <= 0:
            return 0
        return int(remaining) + 1
    except Exception:
        return 0


def set_multispin_cooldown(db, uid: int):
    """Устанавливает время последнего мультиспина"""
    db.update_user_field(uid, "last_multispin_time", datetime.now().isoformat())


# ══════════════════════════════════════════════════
#                 TICKET COMMANDS
# ══════════════════════════════════════════════════

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
        await msg.reply(
            f"🎫 <b>Билет получен!</b>\n\n"
            f"🎟️ Билетов: <b>{tickets}</b>\n"
            f"💡 /spin или /multispin",
            parse_mode="HTML"
        )
    else:
        await msg.reply(
            f"⏰ Подожди <b>{rem}</b> мин.\n"
            f"🎟️ Билетов: <b>{tickets}</b>",
            parse_mode="HTML"
        )


@router.message(Command("tickets"))
async def cmd_tickets(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    
    db, uid = get_db(msg), msg.from_user.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    
    t = db.get_spin_tickets(uid)
    r = db.get_time_until_free_ticket(uid)
    
    # Проверяем КД
    spin_cd = get_spin_cooldown(db, uid)
    multispin_cd = get_multispin_cooldown(db, uid)
    
    txt = f"🎟️ <b>Билеты: {t}</b>\n\n"
    
    if r > 0:
        txt += f"🎫 Бесплатный через: <b>{r}</b> мин.\n"
    else:
        txt += f"✅ /ticket — получить билет\n"
    
    txt += f"\n<b>⏰ Кулдауны:</b>\n"
    
    if spin_cd > 0:
        txt += f"🎰 Спин: <b>{format_time_remaining(spin_cd)}</b>\n"
    else:
        txt += f"🎰 Спин: ✅ готов\n"
    
    if multispin_cd > 0:
        txt += f"🎰 Мультиспин: <b>{format_time_remaining(multispin_cd)}</b>\n"
    else:
        txt += f"🎰 Мультиспин: ✅ готов\n"
    
    await msg.reply(txt, parse_mode="HTML")


# ══════════════════════════════════════════════════
#                   SPIN COMMAND
# ══════════════════════════════════════════════════

@router.message(Command("spin"))
async def cmd_spin(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")

    db, uid = get_db(msg), msg.from_user.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    DatabaseManager.get_global_db().update_user(uid, msg.from_user.username, msg.from_user.first_name)

    # Проверяем КД
    spin_cd = get_spin_cooldown(db, uid)
    if spin_cd > 0:
        return await msg.reply(
            f"⏰ <b>Подожди!</b>\n\n"
            f"🎰 Спин доступен через: <b>{format_time_remaining(spin_cd)}</b>\n\n"
            f"💡 Используй /multispin для массовой прокрутки (КД 1 час)",
            parse_mode="HTML"
        )

    # Проверяем билеты
    tickets = db.get_spin_tickets(uid)
    if tickets <= 0:
        r = db.get_time_until_free_ticket(uid)
        txt = f"🎟️ <b>Нет билетов!</b>\n"
        if r > 0:
            txt += f"⏰ Бесплатный через: <b>{r}</b> мин."
        else:
            txt += f"✅ /ticket — получить билет"
        return await msg.reply(txt, parse_mode="HTML")

    if not db.use_spin_ticket(uid):
        return await msg.reply(f"{EMOJI['cross']} Ошибка!")

    # Устанавливаем КД
    set_spin_cooldown(db, uid)

    card = get_random_card()
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

    coins = get_coins(card["rarity"])
    if is_dupe:
        coins += coins // 2
    db.add_coins(uid, coins)

    caption = SPIN_HEADERS.get(card["rarity"], SPIN_HEADERS["common"]) + format_card(card)
    caption += f"\n\n🪙 <b>+{coins}</b>" + (" <i>(дубль!)</i>" if is_dupe else "")
    caption += f"\n🎟️ Билетов: <b>{db.get_spin_tickets(uid)}</b>"
    caption += f"\n⏰ След. спин через: <b>{SPIN_COOLDOWN_MINUTES} мин</b>"

    await send_card(msg, card, caption)


# ══════════════════════════════════════════════════
#                 MULTISPIN COMMAND
# ══════════════════════════════════════════════════

@router.message(Command("multispin", "ms"))
async def cmd_multispin(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")

    uid = msg.from_user.id
    ok, rem = antispam.check(uid, "spin")
    if not ok:
        if rem > 2:
            return await msg.reply(f"⏱️ Подожди {rem} сек.")
        return

    db = get_db(msg)
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)
    DatabaseManager.get_global_db().update_user(uid, msg.from_user.username, msg.from_user.first_name)

    # Проверяем КД на мультиспин
    multispin_cd = get_multispin_cooldown(db, uid)
    if multispin_cd > 0:
        return await msg.reply(
            f"⏰ <b>Подожди!</b>\n\n"
            f"🎰 Мультиспин доступен через: <b>{format_time_remaining(multispin_cd)}</b>\n\n"
            f"💡 КД на мультиспин: <b>1 час</b>",
            parse_mode="HTML"
        )

    # Парсим количество
    args = msg.text.split()
    requested = 5  # по умолчанию
    if len(args) > 1 and args[1].isdigit():
        requested = int(args[1])
    
    # Лимитируем (минимум 2, максимум MULTISPIN_MAX)
    count = max(2, min(MULTISPIN_MAX, requested))
    
    tickets = db.get_spin_tickets(uid)

    if tickets < 2:
        return await msg.reply(
            f"🎟️ <b>Минимум 2 билета!</b>\n"
            f"У тебя: <b>{tickets}</b>\n\n"
            f"💡 /ticket — получить билет",
            parse_mode="HTML"
        )

    # Ограничиваем по билетам
    count = min(count, tickets)

    # Устанавливаем КД ПЕРЕД спином
    set_multispin_cooldown(db, uid)

    used = 0
    cards = []
    total_coins = 0
    best = None
    user_cards = db.get_user(uid).get("cards", [])

    for _ in range(count):
        if not db.use_spin_ticket(uid):
            break
        used += 1
        
        card = get_random_card()
        is_dupe = any(c["name"] == card["name"] for c in user_cards + cards)
        
        db.add_card(uid, {
            "name": card["name"],
            "rarity": card["rarity"],
            "attack": card["attack"],
            "defense": card["defense"],
            "emoji": card["emoji"],
            "obtained_at": datetime.now().isoformat()
        })
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

    # Подсчёт редкостей
    rarities = {}
    for c in cards:
        rarities[c["rarity"]] = rarities.get(c["rarity"], 0) + 1

    txt = f"🎰🎰🎰 <b>МУЛЬТИСПИН x{used}!</b> 🎰🎰🎰\n\n"
    
    # Показываем редкости
    for r in ["mega", "special", "mythic", "legendary", "epic", "rare", "common"]:
        if r in rarities:
            rc = RARITY_COLORS.get(r, "⚪")
            txt += f"{rc} {RARITY_NAMES.get(r, r)}: <b>{rarities[r]}</b>\n"

    txt += f"\n<b>📋 Карты:</b>\n"
    
    # Показываем первые 15 карт
    for i, c in enumerate(cards[:15], 1):
        rc = RARITY_COLORS.get(c['rarity'], '⚪')
        txt += f"{i}. {rc} {c['emoji']} {c['name']} (💪{c['attack']+c['defense']})\n"
    
    if len(cards) > 15:
        txt += f"<i>...и ещё {len(cards)-15} карт</i>\n"

    if best:
        rc = RARITY_COLORS.get(best["rarity"], "⚪")
        txt += f"\n👑 <b>Лучшая:</b> {rc} {best['emoji']} {best['name']} (💪{best['attack']+best['defense']})\n"
    
    txt += f"\n🪙 <b>+{total_coins}</b> монет"
    txt += f"\n🎟️ Осталось: <b>{db.get_spin_tickets(uid)}</b>"
    txt += f"\n⏰ След. мультиспин через: <b>1 час</b>"

    # Отправляем с картинкой лучшей карты
    if best:
        await send_card(msg, best, txt)
    else:
        await msg.reply(txt, parse_mode="HTML")


# ══════════════════════════════════════════════════
#                  CARD COMMANDS
# ══════════════════════════════════════════════════

@router.message(Command("mycards"))
async def cmd_mycards(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    
    db, uid = get_db(msg), msg.from_user.id
    user = db.get_user(uid)
    if not user or not user.get("cards"):
        return await msg.reply(
            f"{EMOJI['card']} Нет карт!\n"
            f"/ticket → /spin",
            parse_mode="HTML"
        )

    cards = user["cards"]
    counts = {}
    for c in cards:
        counts[c["rarity"]] = counts.get(c["rarity"], 0) + 1

    btns = []
    for r in ["mega", "special", "mythic", "legendary", "epic", "rare", "common"]:
        if r in counts:
            btns.append(InlineKeyboardButton(
                text=f"{RARITY_COLORS.get(r, '⚪')} {RARITY_NAMES.get(r, r)} ({counts[r]})",
                callback_data=f"cards_r:{r}"
            ))

    kb = [[b] for b in btns] + [[InlineKeyboardButton(text="📋 Все", callback_data="cards_r:all")]]
    await msg.reply(
        f"{EMOJI['card']} <b>Карты ({len(cards)})</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


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
        rc = RARITY_COLORS.get(c['rarity'], '⚪')
        txt += f"{rc} {c['emoji']} {c['name']} (💪{c['attack']+c['defense']})"
        txt += f" x{cnt}\n" if cnt > 1 else "\n"
    
    if len(sorted_cards) > 15:
        txt += f"<i>...ещё {len(sorted_cards)-15}</i>"

    try:
        await cb.message.edit_text(txt, parse_mode="HTML")
    except Exception:
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
        return await msg.reply(f"{EMOJI['cross']} Не найдена!", parse_mode="HTML")

    db = get_db(msg)
    user = db.get_user(msg.from_user.id)
    count = sum(1 for c in user.get("cards", []) if c["name"] == card["name"]) if user else 0

    caption = f"{EMOJI['gem']} <b>Карта</b>\n\n" + format_card(card)
    caption += f"\n\n📦 У тебя: <b>{count}</b>"

    await send_card(msg, card, caption)


@router.message(Command("cards", "allcards"))
async def cmd_cards(msg: Message):
    txt = f"{EMOJI['card']} <b>ВСЕ КАРТЫ ({len(CARDS)})</b>\n\n"
    for r in ["mega", "special", "mythic", "legendary", "epic", "rare", "common"]:
        lst = [c for c in CARDS if c["rarity"] == r]
        if lst:
            txt += f"<b>{RARITY_NAMES.get(r, r)}</b> ({RARITY_CHANCES.get(r, 0)}%):\n"
            for c in sorted(lst, key=lambda x: -(x["attack"]+x["defense"]))[:5]:
                txt += f"  {c['emoji']} {c['name']} (💪{c['attack']+c['defense']})\n"
            if len(lst) > 5:
                txt += f"  <i>...ещё {len(lst)-5}</i>\n"
            txt += "\n"
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
    txt += f"🎯 Уникальных: <b>{unique}/{total}</b> ({unique*100//total if total else 0}%)\n\n"
    
    if cards:
        best = max(cards, key=lambda x: x["attack"]+x["defense"])
        rc = RARITY_COLORS.get(best["rarity"], "⚪")
        txt += f"👑 <b>Лучшая:</b> {rc} {best['emoji']} {best['name']} (💪{best['attack']+best['defense']})"

    await msg.reply(txt, parse_mode="HTML")


# ══════════════════════════════════════════════════
#                    BALANCE
# ══════════════════════════════════════════════════

@router.message(Command("balance", "coins", "bal"))
async def cmd_balance(msg: Message):
    if not is_group(msg):
        return await msg.reply(f"{EMOJI['cross']} Только в группах!")
    
    db, uid = get_db(msg), msg.from_user.id
    if not db.get_user(uid):
        db.create_user(uid, msg.from_user.username, msg.from_user.first_name)

    user = db.get_user(uid)
    
    # Кулдауны
    spin_cd = get_spin_cooldown(db, uid)
    multispin_cd = get_multispin_cooldown(db, uid)

    txt = f"💰 <b>Баланс</b>\n\n"
    txt += f"🪙 Монеты: <b>{user.get('coins', 0)}</b>\n"
    txt += f"🃏 Карт: <b>{len(user.get('cards', []))}</b>\n"
    txt += f"🎟️ Билетов: <b>{db.get_spin_tickets(uid)}</b>\n"
    txt += f"🛡️ Щитов: <b>{db.get_shields(uid)}</b>\n"
    
    txt += f"\n<b>⏰ Кулдауны:</b>\n"
    txt += f"🎰 Спин: " + (f"<b>{format_time_remaining(spin_cd)}</b>" if spin_cd > 0 else "✅") + "\n"
    txt += f"🎰 Мультиспин: " + (f"<b>{format_time_remaining(multispin_cd)}</b>" if multispin_cd > 0 else "✅")

    await msg.reply(txt, parse_mode="HTML")


# ══════════════════════════════════════════════════
#                      TOP
# ══════════════════════════════════════════════════

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
    data = []
    txt = ""

    if t == "cards":
        data = db.get_top_by_cards(10)
        txt = "🃏 <b>ТОП ПО КАРТАМ</b>\n\n"
        for i, u in enumerate(data):
            m = medals[i] if i < 3 else f"{i+1}."
            txt += f"{m} {u.get('first_name', '?')} — {u.get('cards_count', 0)} карт\n"
    elif t == "coins":
        data = db.get_top_by_coins(10)
        txt = "🪙 <b>ТОП ПО МОНЕТАМ</b>\n\n"
        for i, u in enumerate(data):
            m = medals[i] if i < 3 else f"{i+1}."
            txt += f"{m} {u.get('first_name', '?')} — {u.get('coins', 0)} 🪙\n"
    elif t == "power":
        data = sorted(CARDS, key=lambda x: x["attack"]+x["defense"], reverse=True)[:10]
        txt = "💪 <b>СИЛЬНЕЙШИЕ КАРТЫ</b>\n\n"
        for i, c in enumerate(data):
            m = medals[i] if i < 3 else f"{i+1}."
            txt += f"{m} {c['emoji']} {c['name']} — 💪{c['attack']+c['defense']}\n"
    else:  # arena
        data = db.get_top_players(10)
        txt = "⚔️ <b>ТОП АРЕНЫ</b>\n\n"
        for i, u in enumerate(data):
            m = medals[i] if i < 3 else f"{i+1}."
            txt += f"{m} {u.get('first_name', '?')} — ⭐{u.get('rating', 0)}\n"

    if not data:
        txt += "Пока пусто!"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="top_menu")]
    ])
    
    try:
        await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    except Exception:
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
    except Exception:
        pass
    await cb.answer()