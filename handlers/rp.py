# handlers/rp.py
import random
import logging
import re
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from database import DatabaseManager

logger = logging.getLogger(__name__)
router = Router()

RP_ACTIONS = {
    "обнять": {
        "emoji": "🤗",
        "self": ["{user} обнял(а) себя 🥺"],
        "target": ["{user} крепко обнял(а) {target} 🤗", "{user} нежно обнимает {target} 💕", "{user} прижал(а) {target} к себе 🫂"],
        "all": ["{user} обнял(а) весь чат! 🤗"],
    },
    "поцеловать": {
        "emoji": "💋",
        "self": ["{user} поцеловал(а) зеркало 💋"],
        "target": ["{user} поцеловал(а) {target} 💋", "{user} страстно целует {target} 😘", "{user} чмокнул(а) {target} в щёчку 💕"],
        "all": ["{user} целует всех! 💋"],
    },
    "ударить": {
        "emoji": "👊",
        "self": ["{user} ударил(а) себя 😵"],
        "target": ["{user} ударил(а) {target}! 👊", "{user} врезал(а) {target}! 💥", "{user} дал(а) {target} по щам! 💢"],
        "all": ["{user} бьёт всех! 👊"],
    },
    "избить": {
        "emoji": "💀",
        "self": ["{user} избил(а) себя 😰"],
        "target": ["{user} избил(а) {target}! 💀", "{user} отметелил(а) {target}! 🤕", "{user} навалял(а) {target}! 😵"],
        "all": ["{user} избивает всех! 💀"],
    },
    "выебать": {
        "emoji": "🔞",
        "self": ["{user} сам(а) с собой 🌚"],
        "target": ["{user} выебал(а) {target}! 🔞", "{user} оприходовал(а) {target}! 🫦"],
        "all": ["{user} устроил(а) оргию! 🔞"],
    },
    "принудить": {
        "emoji": "⛓️",
        "self": ["{user} принудил(а) себя ⛓️"],
        "target": ["{user} принудил(а) {target}! ⛓️", "{user} заставил(а) {target} подчиниться! 😈"],
        "all": ["{user} принуждает всех! ⛓️"],
    },
    "связать": {
        "emoji": "🪢",
        "self": ["{user} связал(а) себя 🪢"],
        "target": ["{user} связал(а) {target}! 🪢", "{user} привязал(а) {target}! 😈"],
        "all": ["{user} связал(а) всех! 🪢"],
    },
    "отлизать": {
        "emoji": "👅",
        "self": ["{user} сам(а) себе 👅"],
        "target": ["{user} отлизал(а) {target}! 👅", "{user} вылизывает {target}! 🫦"],
        "all": ["{user} лижет всех! 👅"],
    },
    "уебать": {
        "emoji": "💥",
        "self": ["{user} уебал(а) себя! 💥"],
        "target": ["{user} уебал(а) {target}! 💥", "{user} вырубил(а) {target}! 🤜", "{user} мощно уебал(а) {target}! 💀"],
        "all": ["{user} уебал(а) всех! 💥"],
    },
    "погладить": {
        "emoji": "🥰",
        "self": ["{user} погладил(а) себя 🥰"],
        "target": ["{user} погладил(а) {target} 🥰", "{user} гладит {target} по головке 💆"],
        "all": ["{user} гладит всех! 🥰"],
    },
    "укусить": {
        "emoji": "😬",
        "self": ["{user} укусил(а) себя 😬"],
        "target": ["{user} укусил(а) {target}! 😬", "{user} впился(-ась) в {target}! 🦷"],
        "all": ["{user} кусает всех! 😬"],
    },
    "шлёпнуть": {
        "emoji": "🍑",
        "self": ["{user} шлёпнул(а) себя 🍑"],
        "target": ["{user} шлёпнул(а) {target}! 🍑", "{user} дал(а) {target} по попе! 😏"],
        "all": ["{user} шлёпает всех! 🍑"],
    },
}

RP_KEYWORDS = list(RP_ACTIONS.keys())

_rp_words = "|".join(RP_KEYWORDS) + "|шлепнуть"
RP_REGEX = re.compile(rf"^[!]?({_rp_words})", re.IGNORECASE)


def mention(user) -> str:
    if hasattr(user, "from_user"):
        user = user.from_user
    return f'<a href="tg://user?id={user.id}">{user.first_name or "?"}</a>'


def parse_cmd(text: str):
    if not text:
        return None, None
    t = text.strip().lstrip("/!").strip()
    low = t.lower()
    if low.startswith("шлепнуть"):
        return "шлёпнуть", t[8:].strip() or None
    for kw in RP_KEYWORDS:
        if low.startswith(kw):
            rest = t[len(kw):].strip()
            if not rest or t[len(kw):len(kw) + 1] in ("", " "):
                return kw, rest or None
    return None, None


async def do_rp(msg: Message, action: str, arg: str = None):
    a = RP_ACTIONS.get(action)
    if not a:
        return
    u = mention(msg.from_user)
    reply = msg.reply_to_message

    if arg and arg.lower() in ("всех", "всем", "все", "all"):
        txt = random.choice(a["all"]).format(user=u)
    elif reply and reply.from_user and not arg:
        t = reply.from_user
        if t.id == msg.from_user.id:
            txt = random.choice(a["self"]).format(user=u)
        else:
            txt = random.choice(a["target"]).format(user=u, target=mention(t))
            save_stat(msg.chat.id, msg.from_user.id, t.id, action)
    elif arg:
        txt = random.choice(a["target"]).format(user=u, target=arg)
    else:
        txt = random.choice(a["self"]).format(user=u)

    await msg.reply(f"{a['emoji']} {txt}")


def save_stat(chat_id, user_id, target_id, action):
    try:
        db = DatabaseManager.get_group_db(chat_id)
        db.ensure_rp_tables()
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO rp_stats(user_id,target_id,action,count) VALUES(?,?,?,1) "
            "ON CONFLICT(user_id,target_id,action) DO UPDATE SET count=count+1",
            (user_id, target_id, action))
        conn.commit()
        conn.close()
    except:
        pass


# ============ РП КОМАНДЫ С / ============

@router.message(Command("обнять"))
async def c1(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "обнять", a)

@router.message(Command("поцеловать"))
async def c2(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "поцеловать", a)

@router.message(Command("ударить"))
async def c3(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "ударить", a)

@router.message(Command("избить"))
async def c4(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "избить", a)

@router.message(Command("выебать"))
async def c5(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "выебать", a)

@router.message(Command("принудить"))
async def c6(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "принудить", a)

@router.message(Command("связать"))
async def c7(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "связать", a)

@router.message(Command("отлизать"))
async def c8(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "отлизать", a)

@router.message(Command("уебать"))
async def c9(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "уебать", a)

@router.message(Command("погладить"))
async def c10(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "погладить", a)

@router.message(Command("укусить"))
async def c11(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "укусить", a)

@router.message(Command("шлёпнуть", "шлепнуть"))
async def c12(m: Message):
    _, a = parse_cmd(m.text); await do_rp(m, "шлёпнуть", a)


# ============ БРАКИ ============

def mdb(chat_id):
    db = DatabaseManager.get_group_db(chat_id)
    db.ensure_marriage_tables()
    return db


@router.message(Command("брак", "marry"))
async def cmd_marry(msg: Message):
    reply = msg.reply_to_message
    if not reply or not reply.from_user:
        return await msg.reply("💍 Ответьте на сообщение человека!")
    target = reply.from_user
    user = msg.from_user
    if target.id == user.id:
        return await msg.reply("❌ Нельзя жениться на себе!")
    if target.is_bot:
        return await msg.reply("❌ Нельзя жениться на боте!")

    db = mdb(msg.chat.id)
    if db.get_marriage(user.id):
        return await msg.reply("❌ Вы уже в браке! /развод")
    if db.get_marriage(target.id):
        return await msg.reply(f"❌ {mention(target)} уже в браке!")

    try:
        conn = db.get_connection()
        conn.execute("DELETE FROM marriage_proposals WHERE proposer_id=? AND target_id=? AND status='pending'",
                     (user.id, target.id))
        conn.commit()
        conn.close()
    except:
        pass

    pid = db.create_proposal(user.id, target.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💍 Принять", callback_data=f"mY_{pid}_{user.id}_{target.id}"),
        InlineKeyboardButton(text="💔 Отказать", callback_data=f"mN_{pid}_{user.id}_{target.id}"),
    ]])
    await msg.reply(
        f"💍 <b>Предложение!</b>\n\n{mention(user)} предлагает {mention(target)} брак! 💕\n\n{mention(target)}, ваш ответ?",
        reply_markup=kb)


@router.callback_query(F.data.startswith("mY_"))
async def cb_marry_yes(cb: CallbackQuery):
    parts = cb.data.split("_")
    if len(parts) != 4:
        return await cb.answer("Ошибка", show_alert=True)
    try:
        pid, uid, tid = int(parts[1]), int(parts[2]), int(parts[3])
    except:
        return await cb.answer("Ошибка", show_alert=True)
    if cb.from_user.id != tid:
        return await cb.answer("Не вам!", show_alert=True)

    db = mdb(cb.message.chat.id)
    prop = db.get_proposal_by_id(pid)
    if not prop or prop.get("status") != "pending":
        return await cb.answer("Неактуально", show_alert=True)
    if db.get_marriage(uid):
        db.update_proposal_status(pid, "expired")
        return await cb.answer("Отправитель в браке!", show_alert=True)
    if db.get_marriage(tid):
        db.update_proposal_status(pid, "expired")
        return await cb.answer("Вы в браке!", show_alert=True)

    db.create_marriage(uid, tid)
    db.update_proposal_status(pid, "accepted")
    pn = f'<a href="tg://user?id={uid}">?</a>'
    try:
        pn = mention((await cb.message.chat.get_member(uid)).user)
    except:
        pass
    await cb.message.edit_text(f"💒 {pn} 💍 {mention(cb.from_user)}\n\n🎉 Поздравляем! 🥂")
    await cb.answer("💍 Брак!")


@router.callback_query(F.data.startswith("mN_"))
async def cb_marry_no(cb: CallbackQuery):
    parts = cb.data.split("_")
    if len(parts) != 4:
        return await cb.answer("Ошибка", show_alert=True)
    try:
        pid, uid, tid = int(parts[1]), int(parts[2]), int(parts[3])
    except:
        return await cb.answer("Ошибка", show_alert=True)
    if cb.from_user.id != tid:
        return await cb.answer("Не вам!", show_alert=True)

    mdb(cb.message.chat.id).update_proposal_status(pid, "rejected")
    pn = f'<a href="tg://user?id={uid}">?</a>'
    try:
        pn = mention((await cb.message.chat.get_member(uid)).user)
    except:
        pass
    await cb.message.edit_text(f"💔 {mention(cb.from_user)} отказал(а) {pn} 😢")
    await cb.answer("💔")


@router.message(Command("развод", "divorce"))
async def cmd_divorce(msg: Message):
    db = mdb(msg.chat.id)
    mar = db.get_marriage(msg.from_user.id)
    if not mar:
        return await msg.reply("❌ Вы не в браке!")
    pid = mar["partner_id"]
    try:
        days = (datetime.now() - datetime.fromisoformat(mar["married_at"])).days
    except:
        days = 0
    pn = f'<a href="tg://user?id={pid}">партнёр</a>'
    try:
        pn = mention((await msg.chat.get_member(pid)).user)
    except:
        pass
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💔 Да", callback_data=f"dY_{msg.from_user.id}_{pid}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"dN_{msg.from_user.id}"),
    ]])
    await msg.reply(f"💔 Развестись с {pn}? Вместе {days} дн.", reply_markup=kb)


@router.callback_query(F.data.startswith("dY_"))
async def cb_div_yes(cb: CallbackQuery):
    parts = cb.data.split("_")
    if len(parts) != 3:
        return await cb.answer("Ошибка", show_alert=True)
    try:
        uid, pid = int(parts[1]), int(parts[2])
    except:
        return await cb.answer("Ошибка", show_alert=True)
    if cb.from_user.id != uid:
        return await cb.answer("Не ваше!", show_alert=True)
    mdb(cb.message.chat.id).delete_marriage(uid)
    pn = f'<a href="tg://user?id={pid}">бывший(-ая)</a>'
    try:
        pn = mention((await cb.message.chat.get_member(pid)).user)
    except:
        pass
    await cb.message.edit_text(f"💔 {mention(cb.from_user)} и {pn} разведены 😢")
    await cb.answer("💔")


@router.callback_query(F.data.startswith("dN_"))
async def cb_div_no(cb: CallbackQuery):
    parts = cb.data.split("_")
    if len(parts) != 2:
        return await cb.answer("Ошибка", show_alert=True)
    try:
        uid = int(parts[1])
    except:
        return await cb.answer("Ошибка", show_alert=True)
    if cb.from_user.id != uid:
        return await cb.answer("Не ваше!", show_alert=True)
    await cb.message.edit_text("💕 Развод отменён!")
    await cb.answer("💕")


@router.message(Command("браки", "marriages"))
async def cmd_marriages(msg: Message):
    db = mdb(msg.chat.id)
    marriages = db.get_all_marriages()
    if not marriages:
        return await msg.reply("💔 Браков нет!")
    txt = "💒 <b>Браки чата:</b>\n\n"
    for i, m in enumerate(marriages, 1):
        try:
            days = (datetime.now() - datetime.fromisoformat(m["married_at"])).days
        except:
            days = 0
        n1 = n2 = "?"
        try:
            n1 = mention((await msg.chat.get_member(m["user1_id"])).user)
        except:
            n1 = f'<a href="tg://user?id={m["user1_id"]}">Юзер</a>'
        try:
            n2 = mention((await msg.chat.get_member(m["user2_id"])).user)
        except:
            n2 = f'<a href="tg://user?id={m["user2_id"]}">Юзер</a>'
        txt += f"{i}. {n1} 💍 {n2} — {days} дн.\n"
    await msg.reply(txt)


@router.message(Command("парочка", "пара"))
async def cmd_pair(msg: Message):
    db = mdb(msg.chat.id)
    mar = db.get_marriage(msg.from_user.id)
    if not mar:
        return await msg.reply("💔 Вы не в браке! /брак (ответом)")
    pid = mar["partner_id"]
    try:
        ma = datetime.fromisoformat(mar["married_at"])
        days = (datetime.now() - ma).days
        ds = ma.strftime('%d.%m.%Y')
    except:
        days, ds = 0, "?"
    pn = f'<a href="tg://user?id={pid}">Партнёр</a>'
    try:
        pn = mention((await msg.chat.get_member(pid)).user)
    except:
        pass
    if days < 7:
        rank = "💕 Молодожёны"
    elif days < 30:
        rank = "💑 Пара"
    elif days < 90:
        rank = "💞 Крепкая пара"
    elif days < 180:
        rank = "💖 Влюблённые"
    elif days < 365:
        rank = "💝 Неразлучные"
    else:
        rank = "👑 Легенды"
    await msg.reply(f"💍 <b>Брак</b>\n\n👤 {mention(msg.from_user)}\n💕 {pn}\n\n📅 {ds}\n⏳ {days} дн.\n🏅 {rank}")


# ============ СТАТА РП ============

@router.message(Command("рпстат", "rpstats"))
async def cmd_stats(msg: Message):
    db = DatabaseManager.get_group_db(msg.chat.id)
    db.ensure_rp_tables()
    uid = msg.from_user.id
    name = msg.from_user.first_name
    if msg.reply_to_message and msg.reply_to_message.from_user:
        uid = msg.reply_to_message.from_user.id
        name = msg.reply_to_message.from_user.first_name
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT action, SUM(count) FROM rp_stats WHERE user_id=? GROUP BY action ORDER BY SUM(count) DESC",
                (uid,))
    done = cur.fetchall()
    cur.execute("SELECT action, SUM(count) FROM rp_stats WHERE target_id=? GROUP BY action ORDER BY SUM(count) DESC",
                (uid,))
    got = cur.fetchall()
    conn.close()

    txt = f"📊 <b>РП — {name}</b>\n\n"
    if done:
        txt += "🎬 <b>Сделал:</b>\n"
        for a, c in done:
            txt += f"  {RP_ACTIONS.get(a, {}).get('emoji', '❓')} {a}: {c}\n"
    if got:
        txt += "\n🎯 <b>Получил:</b>\n"
        for a, c in got:
            txt += f"  {RP_ACTIONS.get(a, {}).get('emoji', '❓')} {a}: {c}\n"
    if not done and not got:
        txt += "Пусто"
    await msg.reply(txt)


# ============ ТЕКСТ БЕЗ / (ПОСЛЕДНИЙ!) ============

@router.message(F.text.func(lambda text: bool(RP_REGEX.match(text.strip()))))
async def txt_rp(msg: Message):
    t = (msg.text or "").strip()
    if t.startswith("/"):
        return
    action, arg = parse_cmd(t)
    if action:
        await do_rp(msg, action, arg)