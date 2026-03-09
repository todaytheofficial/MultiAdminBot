# handlers/admin.py
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatMemberAdministrator, ChatMemberOwner, ChatPermissions
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, timedelta
import re

from config import EMOJI, RANKS, PERMISSION_DESCRIPTIONS
from database import DatabaseManager

router = Router()

BOT_CREATOR_IDS = [6378314368]


def is_bot_creator(user_id: int) -> bool:
    return user_id in BOT_CREATOR_IDS


def is_group_chat(message: Message) -> bool:
    return message.chat.type in ["group", "supergroup"]


def get_db(message: Message):
    return DatabaseManager.get_db(message.chat.id)


async def is_owner_or_creator(message: Message, bot: Bot) -> bool:
    if is_bot_creator(message.from_user.id):
        return True
    if message.chat.type in ["group", "supergroup"]:
        try:
            member = await bot.get_chat_member(message.chat.id, message.from_user.id)
            if isinstance(member, ChatMemberOwner):
                return True
        except Exception:
            pass
    return False


async def get_target_user(message: Message, bot: Bot) -> tuple:
    args = message.text.split() if message.text else []
    global_db = DatabaseManager.get_global_db()

    if message.reply_to_message:
        target = message.reply_to_message.from_user
        remaining = " ".join(args[1:]) if len(args) > 1 else ""
        return target.id, target.first_name, target.username, remaining, None

    if len(args) > 1:
        arg = args[1]
        if arg.startswith("@"):
            username = arg[1:]
            user_data = global_db.find_by_username(username)
            if user_data:
                remaining = " ".join(args[2:]) if len(args) > 2 else ""
                return user_data['user_id'], user_data.get('first_name') or username, username, remaining, None
            else:
                return None, None, None, None, f"Пользователь @{username} не найден!"
        try:
            user_id = int(arg)
            try:
                chat = await bot.get_chat(user_id)
                remaining = " ".join(args[2:]) if len(args) > 2 else ""
                return user_id, chat.first_name or str(user_id), chat.username, remaining, None
            except Exception:
                db = get_db(message)
                user = db.get_user(user_id)
                if user:
                    remaining = " ".join(args[2:]) if len(args) > 2 else ""
                    return user_id, user.get("first_name", str(user_id)), user.get("username"), remaining, None
                remaining = " ".join(args[2:]) if len(args) > 2 else ""
                return user_id, str(user_id), None, remaining, None
        except ValueError:
            pass

    return None, None, None, None, "Ответь на сообщение или укажи @username / ID"


def parse_duration(text: str) -> tuple:
    if not text:
        return None, None, text
    text = text.strip()
    patterns = [
        (r'^(\d+)\s*d\b', 1440, 'дн.'),
        (r'^(\d+)\s*h\b', 60, 'ч.'),
        (r'^(\d+)\s*m\b', 1, 'мин.'),
    ]
    text_lower = text.lower()
    for pattern, multiplier, suffix in patterns:
        match = re.match(pattern, text_lower, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            minutes = value * multiplier
            time_str = f"{value} {suffix}"
            remaining = text[match.end():].strip()
            return minutes, time_str, remaining
    return None, None, text


def parse_args_after_target(message: Message, remaining_args: str) -> tuple:
    duration = None
    duration_str = None
    reason = "Не указана"
    if not remaining_args or not remaining_args.strip():
        return duration, duration_str, reason
    remaining_args = remaining_args.strip()
    minutes, time_str, remaining_text = parse_duration(remaining_args)
    if minutes:
        duration = minutes
        duration_str = time_str
        if remaining_text:
            reason = remaining_text
    else:
        reason = remaining_args
    return duration, duration_str, reason


async def try_restrict_member(bot: Bot, chat_id: int, user_id: int, until_date: datetime = None) -> tuple:
    try:
        await bot.restrict_chat_member(
            chat_id, user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        return True, None
    except TelegramBadRequest as e:
        error = str(e).lower()
        if "not enough rights" in error:
            return False, "Боту нужны права администратора!"
        elif "user is an administrator" in error:
            return False, "Нельзя ограничить администратора!"
        else:
            return False, str(e)
    except Exception as e:
        return False, str(e)


async def try_unrestrict_member(bot: Bot, chat_id: int, user_id: int) -> tuple:
    try:
        await bot.restrict_chat_member(
            chat_id, user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        return True, None
    except Exception as e:
        return False, str(e)


async def try_ban_member(bot: Bot, chat_id: int, user_id: int, until_date: datetime = None) -> tuple:
    try:
        if until_date:
            await bot.ban_chat_member(chat_id, user_id, until_date=until_date)
        else:
            await bot.ban_chat_member(chat_id, user_id)
        return True, None
    except TelegramBadRequest as e:
        error = str(e).lower()
        if "not enough rights" in error:
            return False, "Боту нужны права администратора!"
        elif "user is an administrator" in error:
            return False, "Нельзя забанить администратора!"
        else:
            return False, str(e)
    except Exception as e:
        return False, str(e)


async def try_unban_member(bot: Bot, chat_id: int, user_id: int) -> tuple:
    try:
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        return True, None
    except Exception as e:
        return False, str(e)


async def try_kick_member(bot: Bot, chat_id: int, user_id: int) -> tuple:
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        return True, None
    except TelegramBadRequest as e:
        error = str(e).lower()
        if "not enough rights" in error:
            return False, "Боту нужны права администратора!"
        elif "user is an administrator" in error:
            return False, "Нельзя кикнуть администратора!"
        else:
            return False, str(e)
    except Exception as e:
        return False, str(e)


async def get_user_permissions(message: Message, bot: Bot, user_id: int = None) -> dict:
    if user_id is None:
        user_id = message.from_user.id

    if is_bot_creator(user_id):
        return {
            "level": 99,
            "permissions": ["all"],
            "is_bot_creator": True,
            "rank_name": "Создатель бота",
            "rank_emoji": "💠"
        }

    if is_group_chat(message):
        try:
            member = await bot.get_chat_member(message.chat.id, user_id)
            db = get_db(message)

            if isinstance(member, ChatMemberOwner):
                rank = db.get_user_rank(user_id)
                if rank["rank_level"] < 6:
                    db.set_user_rank(user_id, 6, "Владелец")
                return {
                    "level": 6,
                    "permissions": ["all"],
                    "is_owner": True,
                    "rank_name": RANKS[6]["name"],
                    "rank_emoji": RANKS[6]["emoji"]
                }
            elif isinstance(member, ChatMemberAdministrator):
                rank = db.get_user_rank(user_id)
                if rank["rank_level"] < 3:
                    return {
                        "level": 3,
                        "permissions": RANKS[3]["permissions"],
                        "is_tg_admin": True,
                        "rank_name": RANKS[3]["name"],
                        "rank_emoji": RANKS[3]["emoji"]
                    }
        except Exception:
            pass

    db = get_db(message)
    rank = db.get_user_rank(user_id)
    rank_level = rank["rank_level"]
    rank_data = RANKS.get(rank_level, RANKS[0])

    return {
        "level": rank_level,
        "permissions": rank_data["permissions"],
        "is_bot_creator": False,
        "is_owner": False,
        "rank_name": rank_data["name"],
        "rank_emoji": rank_data["emoji"]
    }


def has_permission(permissions: dict, required: str) -> bool:
    perms = permissions.get("permissions", [])
    if "all" in perms:
        return True
    return required in perms


def can_promote_to(permissions: dict, target_rank: int) -> bool:
    if has_permission(permissions, "all"):
        return True
    for i in range(target_rank, 0, -1):
        if has_permission(permissions, f"promote_{i}"):
            return target_rank <= i
    return False


def mention_user(user_id: int, first_name: str, username: str = None) -> str:
    name = first_name or username or str(user_id)
    return f'<a href="tg://user?id={user_id}">{name}</a>'


def parse_rank_from_text(text: str) -> tuple:
    if not text:
        return 1, ""
    text = text.strip()
    rank_names = {
        "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
        "модератор": 2, "админ": 4, "владелец": 5,
    }
    parts = text.split(maxsplit=1)
    first_part = parts[0].lower()
    if first_part in rank_names:
        rank_level = rank_names[first_part]
        custom_title = parts[1] if len(parts) > 1 else ""
        return rank_level, custom_title
    try:
        rank_level = int(first_part)
        if 1 <= rank_level <= 5:
            custom_title = parts[1] if len(parts) > 1 else ""
            return rank_level, custom_title
    except ValueError:
        pass
    return 1, text


# ═══════════════════════════════════════════════════════════
#                          РАНГИ
# ═══════════════════════════════════════════════════════════

@router.message(Command("promote"))
async def promote_user(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    if perms["level"] < 4 and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нужен ранг {RANKS[4]['emoji']} {RANKS[4]['name']} или выше!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        ranks_text = "\n".join([f"  {info['emoji']} <code>{level}</code> — {info['name']}" for level, info in RANKS.items() if 0 < level < 6])
        return await message.reply(
            f"{EMOJI['promote']} <b>Повышение</b>\n\n"
            f"<b>Использование:</b>\n"
            f"<code>/promote @user [ранг] [титул]</code>\n\n"
            f"<b>Ранги:</b>\n{ranks_text}",
            parse_mode="HTML"
        )

    if target_id == message.from_user.id:
        return await message.reply(f"{EMOJI['cross']} Нельзя повысить себя!")

    new_rank, custom_title = parse_rank_from_text(remaining_args)
    new_rank = max(1, min(5, new_rank))

    if not can_promote_to(perms, new_rank) and perms["level"] < 6:
        return await message.reply(f"{EMOJI['cross']} У тебя нет прав на это!")

    if new_rank >= perms["level"] and perms["level"] < 99:
        return await message.reply(f"{EMOJI['cross']} Нельзя повысить до своего ранга или выше!")

    db = get_db(message)
    target_rank = db.get_user_rank(target_id)

    if target_rank["rank_level"] >= perms["level"] and perms["level"] < 99:
        return await message.reply(f"{EMOJI['cross']} Нельзя изменять ранг равного или старшего!")

    if not db.get_user(target_id):
        db.create_user(target_id, username, first_name)

    DatabaseManager.get_global_db().update_user(target_id, username, first_name)
    db.set_user_rank(target_id, new_rank, custom_title, message.from_user.id)

    rank_info = RANKS[new_rank]
    old_rank_info = RANKS.get(target_rank["rank_level"], RANKS[0])

    tg_status = ""
    try:
        await bot.promote_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            can_delete_messages=new_rank >= 1,
            can_restrict_members=new_rank >= 1,
            can_pin_messages=new_rank >= 2,
            can_invite_users=new_rank >= 2,
            can_manage_video_chats=new_rank >= 3,
            can_promote_members=new_rank >= 5 and perms["level"] >= 6,
            can_change_info=new_rank >= 4
        )
        if custom_title:
            try:
                await bot.set_chat_administrator_custom_title(
                    chat_id=message.chat.id,
                    user_id=target_id,
                    custom_title=custom_title[:16]
                )
            except Exception:
                pass
        tg_status = "\n\n✅ <i>Права Telegram выданы</i>"
    except Exception:
        tg_status = "\n\n⚠️ <i>Права Telegram не выданы</i>"

    title_text = f"\n🏷️ Титул: <b>{custom_title}</b>" if custom_title else ""

    await message.reply(
        f"{EMOJI['promote']} <b>ПОВЫШЕНИЕ!</b>\n\n"
        f"👤 {mention_user(target_id, first_name, username)}\n"
        f"📊 {old_rank_info['emoji']} → {rank_info['emoji']} <b>{rank_info['name']}</b>"
        f"{title_text}\n\n"
        f"👮 {message.from_user.mention_html()}{tg_status}",
        parse_mode="HTML"
    )


@router.message(Command("demote"))
@router.message(Command("demote"))
async def demote_user(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    # Проверяем право demote ИЛИ уровень 4+
    if not has_permission(perms, "demote") and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нужен ранг {RANKS[4]['emoji']} {RANKS[4]['name']} или выше!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply(
            f"{EMOJI['demote']} <b>Понижение</b>\n\n"
            f"<code>/demote @user</code> — на 1 ранг\n"
            f"<code>/demote @user 0</code> — снять ранг",
            parse_mode="HTML"
        )

    if target_id == message.from_user.id:
        return await message.reply(f"{EMOJI['cross']} Нельзя понизить себя!")

    db = get_db(message)
    target_rank = db.get_user_rank(target_id)

    # Нельзя понизить равного или старшего
    if target_rank["rank_level"] >= perms["level"] and perms["level"] < 99:
        return await message.reply(
            f"{EMOJI['cross']} Нельзя понизить "
            f"{RANKS.get(target_rank['rank_level'], RANKS[0])['emoji']} "
            f"{RANKS.get(target_rank['rank_level'], RANKS[0])['name']}!"
        )

    # Если цель — участник (0), нечего понижать
    if target_rank["rank_level"] == 0:
        return await message.reply(f"{EMOJI['cross']} Это обычный участник, понижать некуда!")

    # Определяем новый ранг
    new_rank = max(0, target_rank["rank_level"] - 1)
    
    # Если указан конкретный ранг
    if remaining_args:
        try:
            requested_rank = int(remaining_args.split()[0])
            # Можно понизить только до ранга ниже своего
            if requested_rank >= perms["level"] and perms["level"] < 99:
                return await message.reply(f"{EMOJI['cross']} Нельзя понизить до своего ранга или выше!")
            # Нельзя понизить выше текущего ранга цели
            new_rank = max(0, min(target_rank["rank_level"] - 1, requested_rank))
        except ValueError:
            pass

    db.set_user_rank(target_id, new_rank, "", message.from_user.id)

    rank_info = RANKS.get(new_rank, RANKS[0])
    old_rank_info = RANKS.get(target_rank["rank_level"], RANKS[0])

    # Снимаем права в Telegram
    tg_status = ""
    try:
        if new_rank == 0:
            await bot.promote_chat_member(
                chat_id=message.chat.id,
                user_id=target_id,
                can_delete_messages=False,
                can_restrict_members=False,
                can_pin_messages=False,
                can_invite_users=False,
                can_manage_video_chats=False,
                can_promote_members=False,
                can_change_info=False
            )
            tg_status = "\n\n✅ <i>Права Telegram сняты</i>"
        else:
            # Обновляем права согласно новому рангу
            await bot.promote_chat_member(
                chat_id=message.chat.id,
                user_id=target_id,
                can_delete_messages=new_rank >= 1,
                can_restrict_members=new_rank >= 1,
                can_pin_messages=new_rank >= 2,
                can_invite_users=new_rank >= 2,
                can_manage_video_chats=new_rank >= 3,
                can_promote_members=False,
                can_change_info=new_rank >= 4
            )
            tg_status = "\n\n✅ <i>Права Telegram обновлены</i>"
    except Exception as e:
        tg_status = f"\n\n⚠️ <i>Права Telegram не изменены</i>"

    await message.reply(
        f"{EMOJI['demote']} <b>ПОНИЖЕНИЕ</b>\n\n"
        f"👤 {mention_user(target_id, first_name, username)}\n"
        f"📊 {old_rank_info['emoji']} → {rank_info['emoji']} <b>{rank_info['name']}</b>\n\n"
        f"👮 {message.from_user.mention_html()}{tg_status}",
        parse_mode="HTML"
    )


@router.message(Command("ranks", "staff", "admins"))
async def show_ranks(message: Message):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    db = get_db(message)
    ranks = db.get_chat_ranks()

    if not ranks:
        return await message.reply(f"{EMOJI['rank']} Нет администрации!\n/promote для назначения", parse_mode="HTML")

    by_rank = {}
    for r in ranks:
        level = r["rank_level"]
        if level not in by_rank:
            by_rank[level] = []
        by_rank[level].append(r)

    text = f"{EMOJI['crown']} <b>АДМИНИСТРАЦИЯ</b>\n\n"

    for level in sorted(by_rank.keys(), reverse=True):
        rank_info = RANKS[level]
        text += f"{rank_info['emoji']} <b>{rank_info['name']}:</b>\n"
        for user in by_rank[level]:
            name = user["first_name"] or user["username"] or "Пользователь"
            title = f" • <i>{user['custom_title']}</i>" if user["custom_title"] else ""
            text += f"   └ {name}{title}\n"
        text += "\n"

    await message.reply(text, parse_mode="HTML")


@router.message(Command("myrank"))
async def show_my_rank(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    text = f"{perms['rank_emoji']} <b>Твой ранг:</b> {perms['rank_name']}"

    if perms.get("is_bot_creator"):
        text += f"\n\n💠 <i>Создатель бота</i>"
    elif perms.get("is_owner"):
        text += f"\n\n🏆 <i>Владелец группы</i>"

    await message.reply(text, parse_mode="HTML")


@router.message(Command("ranklist"))
async def show_all_ranks(message: Message):
    text = f"{EMOJI['rank']} <b>РАНГИ</b>\n\n"

    for level, info in RANKS.items():
        if level == 99:
            continue
        text += f"{info['emoji']} <b>{info['name']}</b> (ур.{level})\n"

    text += f"\n💠 <b>Создатель бота</b> (ур.99)"

    await message.reply(text, parse_mode="HTML")


@router.message(Command("perms"))
async def show_permissions(message: Message, bot: Bot):
    args = message.text.split() if message.text else []

    if len(args) > 1:
        try:
            target_level = int(args[1])
        except Exception:
            target_level = None
    else:
        perms = await get_user_permissions(message, bot)
        target_level = perms["level"]

    if target_level not in RANKS:
        return await message.reply(f"{EMOJI['cross']} Ранг не найден!")

    rank_info = RANKS[target_level]
    text = f"{rank_info['emoji']} <b>{rank_info['name']}</b>\n\n"

    if "all" in rank_info["permissions"]:
        text += f"👑 <b>ВСЕ ПРАВА</b>"
    elif rank_info["permissions"]:
        for perm in rank_info["permissions"]:
            desc = PERMISSION_DESCRIPTIONS.get(perm, perm)
            text += f"• {desc}\n"
    else:
        text += "<i>Нет прав</i>"

    await message.reply(text, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════
#                         ПРАВИЛА
# ═══════════════════════════════════════════════════════════

@router.message(Command("rules"))
async def show_rules(message: Message):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    db = get_db(message)
    rules = db.get_rules()

    if rules:
        await message.reply(f"{EMOJI['rules']} <b>ПРАВИЛА</b>\n\n{rules}", parse_mode="HTML")
    else:
        await message.reply(f"{EMOJI['rules']} Правила не установлены", parse_mode="HTML")


@router.message(Command("setrules"))
async def set_rules(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    if not has_permission(perms, "set_rules") and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нет прав!")

    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) < 2:
        return await message.reply(
            f"📜 <b>Установка правил</b>\n\n<code>/setrules текст правил</code>",
            parse_mode="HTML"
        )

    db = get_db(message)
    db.set_rules(args[1])
    await message.reply(f"{EMOJI['check']} Правила установлены!")


# ═══════════════════════════════════════════════════════════
#                           WARN
# ═══════════════════════════════════════════════════════════

@router.message(Command("warn"))
async def warn_user(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    if not has_permission(perms, "warn") and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нет прав!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply(
            f"{EMOJI['warn']} <b>Варн</b>\n\n"
            f"<code>/warn @user</code>\n"
            f"<code>/warn @user причина</code>",
            parse_mode="HTML"
        )

    if target_id == message.from_user.id:
        return await message.reply(f"{EMOJI['cross']} Нельзя варнить себя!")

    target_perms = await get_user_permissions(message, bot, target_id)
    if target_perms["level"] >= perms["level"] and perms["level"] < 99:
        return await message.reply(f"{EMOJI['cross']} Нельзя варнить {target_perms['rank_emoji']} {target_perms['rank_name']}!")

    duration, duration_str, reason = parse_args_after_target(message, remaining_args)

    if not duration_str:
        duration_str = "навсегда"

    db = get_db(message)

    if not db.get_user(target_id):
        db.create_user(target_id, username, first_name)

    duration_hours = duration / 60 if duration else None
    db.add_warning(target_id, reason, message.from_user.id, int(duration_hours) if duration_hours else None)
    warns = db.get_warnings(target_id)

    warn_bar = "🔴" * min(warns, 3) + "⚪" * max(0, 3 - warns)

    text = (
        f"{EMOJI['warn']} <b>ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
        f"👤 {mention_user(target_id, first_name, username)}\n"
        f"📝 {reason}\n"
        f"⏰ {duration_str}\n\n"
        f"[{warn_bar}] {warns}/3\n\n"
        f"👮 {message.from_user.mention_html()}"
    )

    if warns >= 3:
        success, ban_error = await try_ban_member(bot, message.chat.id, target_id)
        if success:
            db.clear_warnings(target_id)
            text += f"\n\n{EMOJI['ban']} <b>АВТОБАН!</b>"
        else:
            text += f"\n\n⚠️ Автобан не удался: {ban_error}"
            db.clear_warnings(target_id)

    await message.reply(text, parse_mode="HTML")


@router.message(Command("unwarn"))
async def unwarn_user(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    if not has_permission(perms, "unwarn") and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нет прав!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply(
            f"{EMOJI['check']} <b>Снятие варна</b>\n\n"
            f"<code>/unwarn @user</code> — снять 1\n"
            f"<code>/unwarn @user all</code> — снять все",
            parse_mode="HTML"
        )

    db = get_db(message)
    clear_all = remaining_args and remaining_args.lower() in ["all", "все"]

    if clear_all:
        db.clear_warnings(target_id)
        await message.reply(f"{EMOJI['check']} Все варны сняты с {mention_user(target_id, first_name, username)}!", parse_mode="HTML")
    else:
        if db.get_warnings(target_id) == 0:
            return await message.reply("Нет варнов!")
        db.remove_one_warning(target_id)
        warns = db.get_warnings(target_id)
        await message.reply(f"{EMOJI['check']} -1 варн! Осталось: {warns}/3", parse_mode="HTML")


@router.message(Command("warns"))
async def view_warns(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        target_id = message.from_user.id
        first_name = message.from_user.first_name
        username = message.from_user.username
    elif not has_permission(perms, "view_warns") and target_id != message.from_user.id:
        target_id = message.from_user.id
        first_name = message.from_user.first_name
        username = message.from_user.username

    db = get_db(message)
    warns = db.get_warnings_list(target_id)
    count = len(warns)

    if count == 0:
        return await message.reply(f"{EMOJI['check']} Нет варнов!")

    warn_bar = "🔴" * min(count, 3) + "⚪" * max(0, 3 - count)
    text = f"⚠️ <b>{first_name}</b> [{warn_bar}] {count}/3\n\n"

    for i, w in enumerate(warns[:5], 1):
        exp = ""
        if w.get("expires_at"):
            try:
                exp_time = datetime.fromisoformat(w["expires_at"])
                exp = f" (до {exp_time.strftime('%d.%m %H:%M')})"
            except Exception:
                pass
        text += f"{i}. {w['reason']}{exp}\n"

    await message.reply(text, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════
#                           MUTE
# ═══════════════════════════════════════════════════════════

@router.message(Command("mute"))
async def mute_user(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    if not has_permission(perms, "mute") and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нет прав!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply(
            f"{EMOJI['mute']} <b>Мут</b>\n\n"
            f"<code>/mute @user</code> — 1 час\n"
            f"<code>/mute @user 30m причина</code>",
            parse_mode="HTML"
        )

    if target_id == message.from_user.id:
        return await message.reply(f"{EMOJI['cross']} Нельзя замутить себя!")

    target_perms = await get_user_permissions(message, bot, target_id)
    if target_perms["level"] >= perms["level"] and perms["level"] < 99:
        return await message.reply(f"{EMOJI['cross']} Нельзя мутить {target_perms['rank_emoji']} {target_perms['rank_name']}!")

    duration, duration_str, reason = parse_args_after_target(message, remaining_args)

    if not duration:
        duration = 60
        duration_str = "1 ч."

    duration = max(1, min(525600, duration))
    until_date = datetime.now() + timedelta(minutes=duration)

    success, error_msg = await try_restrict_member(bot, message.chat.id, target_id, until_date)

    if success:
        db = get_db(message)
        db.add_punishment(target_id, "mute", reason, message.from_user.id, duration)

        await message.reply(
            f"{EMOJI['mute']} <b>MUTE</b>\n\n"
            f"👤 {mention_user(target_id, first_name, username)}\n"
            f"⏰ {duration_str}\n"
            f"📝 {reason}\n\n"
            f"👮 {message.from_user.mention_html()}",
            parse_mode="HTML"
        )
    else:
        await message.reply(f"{EMOJI['cross']} Не удалось замутить: {error_msg}", parse_mode="HTML")


@router.message(Command("unmute"))
async def unmute_user(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    if not has_permission(perms, "unmute") and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нет прав!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply("<code>/unmute @user</code>", parse_mode="HTML")

    success, error_msg = await try_unrestrict_member(bot, message.chat.id, target_id)

    if success:
        db = get_db(message)
        db.remove_punishment(target_id, "mute")
        await message.reply(f"{EMOJI['check']} {mention_user(target_id, first_name, username)} размучен!", parse_mode="HTML")
    else:
        await message.reply(f"{EMOJI['cross']} Ошибка: {error_msg}")


# ═══════════════════════════════════════════════════════════
#                            BAN
# ═══════════════════════════════════════════════════════════

@router.message(Command("ban"))
async def ban_user(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    if not has_permission(perms, "ban") and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нет прав!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply(
            f"{EMOJI['ban']} <b>Бан</b>\n\n"
            f"<code>/ban @user</code> — навсегда\n"
            f"<code>/ban @user причина</code>",
            parse_mode="HTML"
        )

    if target_id == message.from_user.id:
        return await message.reply(f"{EMOJI['cross']} Нельзя забанить себя!")

    target_perms = await get_user_permissions(message, bot, target_id)
    if target_perms["level"] >= perms["level"] and perms["level"] < 99:
        return await message.reply(f"{EMOJI['cross']} Нельзя банить {target_perms['rank_emoji']} {target_perms['rank_name']}!")

    duration, duration_str, reason = parse_args_after_target(message, remaining_args)

    if not duration_str:
        duration_str = "навсегда"

    until_date = None
    if duration:
        until_date = datetime.now() + timedelta(minutes=duration)

    success, error_msg = await try_ban_member(bot, message.chat.id, target_id, until_date)

    if success:
        db = get_db(message)
        db.add_punishment(target_id, "ban", reason, message.from_user.id, duration)

        await message.reply(
            f"{EMOJI['ban']} <b>BAN</b>\n\n"
            f"👤 {mention_user(target_id, first_name, username)}\n"
            f"⏰ {duration_str}\n"
            f"📝 {reason}\n\n"
            f"👮 {message.from_user.mention_html()}",
            parse_mode="HTML"
        )
    else:
        await message.reply(f"{EMOJI['cross']} Не удалось забанить: {error_msg}", parse_mode="HTML")


@router.message(Command("unban"))
async def unban_user(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    if not has_permission(perms, "unban") and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нет прав!")

    args = message.text.split() if message.text else []

    if len(args) < 2:
        return await message.reply("<code>/unban @user</code>", parse_mode="HTML")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error and len(args) > 1:
        try:
            target_id = int(args[1])
            first_name = str(target_id)
            username = None
        except Exception:
            return await message.reply(f"{EMOJI['cross']} {error}")

    success, error_msg = await try_unban_member(bot, message.chat.id, target_id)

    if success:
        db = get_db(message)
        db.remove_punishment(target_id, "ban")
        await message.reply(f"{EMOJI['check']} {mention_user(target_id, first_name, username)} разбанен!", parse_mode="HTML")
    else:
        await message.reply(f"{EMOJI['cross']} Ошибка: {error_msg}")


@router.message(Command("kick"))
async def kick_user(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    perms = await get_user_permissions(message, bot)

    if not has_permission(perms, "kick") and not has_permission(perms, "all"):
        return await message.reply(f"{EMOJI['cross']} Нет прав!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply("<code>/kick @user</code>", parse_mode="HTML")

    if target_id == message.from_user.id:
        return await message.reply(f"{EMOJI['cross']} Нельзя кикнуть себя!")

    target_perms = await get_user_permissions(message, bot, target_id)
    if target_perms["level"] >= perms["level"] and perms["level"] < 99:
        return await message.reply(f"{EMOJI['cross']} Нельзя кикнуть равного или старшего!")

    success, error_msg = await try_kick_member(bot, message.chat.id, target_id)

    if success:
        await message.reply(f"👢 {mention_user(target_id, first_name, username)} кикнут!", parse_mode="HTML")
    else:
        await message.reply(f"{EMOJI['cross']} Ошибка: {error_msg}")


# ═══════════════════════════════════════════════════════════
#                    КОМАНДЫ ВЫДАЧИ РЕСУРСОВ
# ═══════════════════════════════════════════════════════════

@router.message(Command("givetickets"))
async def give_tickets_command(message: Message, bot: Bot):
    if not await is_owner_or_creator(message, bot):
        return await message.reply(f"{EMOJI['cross']} Только владелец или создатель бота!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply("<code>/givetickets @user количество</code>", parse_mode="HTML")

    amount = 1
    if remaining_args:
        try:
            amount = int(remaining_args.split()[0])
        except ValueError:
            pass

    amount = max(1, min(1000, amount))

    db = get_db(message)
    if not db.get_user(target_id):
        db.create_user(target_id, username, first_name)

    db.add_tickets(target_id, amount)
    new_tickets = db.get_user(target_id).get("spin_tickets", 0)

    await message.reply(
        f"🎟️ <b>БИЛЕТЫ ВЫДАНЫ!</b>\n\n"
        f"👤 {mention_user(target_id, first_name, username)}\n"
        f"➕ +{amount} 🎟️\n"
        f"💰 Всего: {new_tickets}\n\n"
        f"👮 {message.from_user.mention_html()}",
        parse_mode="HTML"
    )


@router.message(Command("givecoins"))
async def give_coins_command(message: Message, bot: Bot):
    if not await is_owner_or_creator(message, bot):
        return await message.reply(f"{EMOJI['cross']} Только владелец или создатель бота!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply("<code>/givecoins @user количество</code>", parse_mode="HTML")

    amount = 100
    if remaining_args:
        try:
            amount = int(remaining_args.split()[0])
        except ValueError:
            pass

    amount = max(1, min(1000000, amount))

    db = get_db(message)
    if not db.get_user(target_id):
        db.create_user(target_id, username, first_name)

    db.add_coins(target_id, amount)
    new_coins = db.get_user(target_id).get("coins", 0)

    await message.reply(
        f"🪙 <b>МОНЕТЫ ВЫДАНЫ!</b>\n\n"
        f"👤 {mention_user(target_id, first_name, username)}\n"
        f"➕ +{amount} 🪙\n"
        f"💰 Всего: {new_coins}\n\n"
        f"👮 {message.from_user.mention_html()}",
        parse_mode="HTML"
    )


@router.message(Command("givecard"))
async def give_card_command(message: Message, bot: Bot):
    if not await is_owner_or_creator(message, bot):
        return await message.reply(f"{EMOJI['cross']} Только владелец или создатель бота!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply("<code>/givecard @user название_карты</code>", parse_mode="HTML")

    if not remaining_args:
        return await message.reply(f"{EMOJI['cross']} Укажи название карты!")

    card_name = remaining_args.strip()

    from config import CARDS
    found_card = None

    for card in CARDS:
        if card["name"].lower() == card_name.lower():
            found_card = card.copy()
            break

    if not found_card:
        for card in CARDS:
            if card_name.lower() in card["name"].lower():
                found_card = card.copy()
                break

    if not found_card:
        return await message.reply(f"{EMOJI['cross']} Карта «{card_name}» не найдена!", parse_mode="HTML")

    db = get_db(message)
    if not db.get_user(target_id):
        db.create_user(target_id, username, first_name)

    db.add_card(target_id, found_card)

    rarity_emoji = {
        "common": "⚪", "rare": "🔵", "epic": "🟣", "legendary": "🟡",
        "mythic": "🔴", "special": "💎", "mega": "🌌"
    }.get(found_card.get("rarity", "common"), "⚪")

    await message.reply(
        f"🃏 <b>КАРТА ВЫДАНА!</b>\n\n"
        f"👤 {mention_user(target_id, first_name, username)}\n"
        f"🎴 {rarity_emoji} <b>{found_card['name']}</b>\n"
        f"⚔️ ATK: {found_card.get('attack', 0)} | 🛡️ DEF: {found_card.get('defense', 0)}\n\n"
        f"👮 {message.from_user.mention_html()}",
        parse_mode="HTML"
    )


@router.message(Command("clearall"))
async def clear_user_all(message: Message, bot: Bot):
    if not is_group_chat(message):
        return await message.reply(f"{EMOJI['cross']} Только в группах!")

    if not await is_owner_or_creator(message, bot):
        return await message.reply(f"{EMOJI['cross']} Только владелец или создатель бота!")

    target_id, first_name, username, remaining_args, error = await get_target_user(message, bot)

    if error:
        return await message.reply("<code>/clearall @user</code>", parse_mode="HTML")

    db = get_db(message)
    user = db.get_user(target_id)
    if not user:
        return await message.reply(f"{EMOJI['cross']} Пользователь не найден!")

    old_cards = len(user.get("cards", []))
    old_coins = user.get("coins", 0)
    old_rating = user.get("rating", 0)

    db.clear_user_all(target_id)

    await message.reply(
        f"⚠️ <b>ПОЛНЫЙ СБРОС!</b>\n\n"
        f"👤 {mention_user(target_id, first_name, username)}\n\n"
        f"🃏 Карт: {old_cards}\n"
        f"🪙 Монет: {old_coins}\n"
        f"⭐ Рейтинг: {old_rating}\n\n"
        f"👮 {message.from_user.mention_html()}",
        parse_mode="HTML"
    )