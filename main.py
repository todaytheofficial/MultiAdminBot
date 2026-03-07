# main.py
import asyncio
import logging
import json
import os
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, BotCommand, ChatPermissions, Update
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, EMOJI
from handlers import admin, cards, battle, market, trade, daily, promo, quests, mults, rp, pay
from database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ================= MIDDLEWARE ДЛЯ СТАТИСТИКИ СООБЩЕНИЙ =================

class MessageStatsMiddleware(BaseMiddleware):
    """Middleware для записи статистики сообщений."""
    async def __call__(self, handler, event: Update, data: dict):
        message: Message = getattr(event, 'message', None)
        if message and message.text and message.chat and message.from_user:
            try:
                if not message.text.startswith("/"):
                    db = DatabaseManager.get_group_db(message.chat.id)
                    db.record_message(message.from_user.id)
            except Exception as e:
                logger.debug(f"Message stats middleware error: {e}")
        return await handler(event, data)


# ================= ПОДКЛЮЧАЕМ РОУТЕРЫ =================

dp.include_router(admin.router)
dp.include_router(cards.router)
dp.include_router(battle.router)
dp.include_router(market.router)
dp.include_router(trade.router)
dp.include_router(daily.router)
dp.include_router(promo.router)
dp.include_router(quests.router)
dp.include_router(mults.router)
dp.include_router(rp.router)
dp.include_router(pay.router)  # <-- НОВЫЙ РОУТЕР

dp.update.middleware(MessageStatsMiddleware())


# ================= НАСТРОЙКИ =================
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://multiadmin.onrender.com")
STATS_UPDATE_INTERVAL = 300


# ================= STATS COLLECTOR =================

async def collect_stats() -> dict:
    total_users = 0
    total_cards = 0
    total_battles = 0
    total_mults_global = 0
    total_fusions_global = 0
    groups = 0
    cards_by_rarity = {}

    try:
        for group_db in DatabaseManager.get_all_group_dbs():
            groups += 1
            conn = group_db.get_connection()
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT COUNT(DISTINCT user_id) FROM users")
                r = cursor.fetchone()
                total_users += r[0] if r and r[0] else 0
            except:
                pass

            try:
                cursor.execute("SELECT cards FROM users WHERE cards IS NOT NULL AND cards != '[]'")
                for row in cursor.fetchall():
                    try:
                        cl = json.loads(row[0] or '[]')
                        total_cards += len(cl)
                        for card in cl:
                            rar = card.get('rarity', 'common')
                            cards_by_rarity[rar] = cards_by_rarity.get(rar, 0) + 1
                    except:
                        pass
            except:
                pass

            try:
                cursor.execute("SELECT COUNT(*) FROM battles")
                r = cursor.fetchone()
                total_battles += r[0] if r and r[0] else 0
            except:
                pass

            try:
                cursor.execute("SELECT COALESCE(SUM(COALESCE(total_mults_earned, 0)), 0) FROM users")
                r = cursor.fetchone()
                total_mults_global += r[0] if r and r[0] else 0
            except:
                pass

            try:
                cursor.execute("SELECT COALESCE(SUM(COALESCE(total_fusions, 0)), 0) FROM users")
                r = cursor.fetchone()
                total_fusions_global += r[0] if r and r[0] else 0
            except:
                pass

            conn.close()
    except Exception as e:
        logger.error(f"Ошибка сбора статистики: {e}")

    return {
        "groups": groups,
        "users": total_users,
        "total_cards": total_cards,
        "battles": total_battles,
        "total_mults": total_mults_global,
        "total_fusions": total_fusions_global,
        "cards_by_rarity": cards_by_rarity,
        "updated_at": datetime.now().isoformat()
    }


async def send_stats_to_website(stats: dict) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{WEBSITE_URL}/api/update-stats",
                json=stats,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                return response.status == 200
    except aiohttp.ClientConnectorError:
        logger.debug("Сайт недоступен")
        return False
    except Exception as e:
        logger.error(f"Ошибка отправки статистики: {e}")
        return False


async def stats_collector_loop():
    await asyncio.sleep(10)
    while True:
        try:
            stats = await collect_stats()
            success = await send_stats_to_website(stats)
            if success:
                logger.info(
                    f"📊 Статистика: {stats['groups']} групп, "
                    f"{stats['users']} юзеров, {stats['total_cards']} карт"
                )
        except Exception as e:
            logger.error(f"Ошибка в stats_collector_loop: {e}")
        await asyncio.sleep(STATS_UPDATE_INTERVAL)


# ================= PUNISHMENT CHECKER =================

async def check_expired_punishments():
    while True:
        try:
            for group_db in DatabaseManager.get_all_group_dbs():
                expired = group_db.get_expired_punishments()
                for p in expired:
                    try:
                        if p["punishment_type"] == "mute":
                            await bot.restrict_chat_member(
                                p["chat_id"], p["user_id"],
                                permissions=ChatPermissions(
                                    can_send_messages=True,
                                    can_send_media_messages=True,
                                    can_send_other_messages=True,
                                    can_add_web_page_previews=True
                                )
                            )
                        elif p["punishment_type"] == "ban":
                            await bot.unban_chat_member(p["chat_id"], p["user_id"])
                        group_db.deactivate_punishment(p["id"])
                    except Exception as e:
                        logger.error(f"Error removing punishment: {e}")
                        group_db.deactivate_punishment(p["id"])
        except Exception as e:
            logger.error(f"Error in check_expired_punishments: {e}")
        await asyncio.sleep(30)


# ================= ТОП ЧАТА =================

@dp.message(Command("topchat", "chattop", "топчат"))
async def cmd_top_chat(message: Message):
    """Топ чата — кто больше всех писал в чате."""
    chat_id = message.chat.id
    db = DatabaseManager.get_group_db(chat_id)

    medals = ["🥇", "🥈", "🥉"]
    txt = "🏆 <b>Топ активности чата</b>\n\n"

    has_data = False

    try:
        top_today = db.get_top_messages_today(10)
        if top_today:
            has_data = True
            txt += "💬 <b>Сегодня:</b>\n"
            for i, u in enumerate(top_today, 1):
                name = f"#{u['user_id']}"
                try:
                    member = await message.chat.get_member(u['user_id'])
                    name = member.user.first_name or name
                except:
                    pass
                m = medals[i - 1] if i <= 3 else f"{i}."
                txt += f"  {m} {name} — <b>{u['count']}</b> сообщений\n"
            txt += "\n"
    except Exception as e:
        logger.debug(f"Top today error: {e}")

    try:
        top_month = db.get_top_messages_month(10)
        if top_month:
            has_data = True
            txt += "📊 <b>За месяц:</b>\n"
            for i, u in enumerate(top_month, 1):
                name = f"#{u['user_id']}"
                try:
                    member = await message.chat.get_member(u['user_id'])
                    name = member.user.first_name or name
                except:
                    pass
                m = medals[i - 1] if i <= 3 else f"{i}."
                txt += f"  {m} {name} — <b>{u['count']}</b> сообщений\n"
            txt += "\n"
    except Exception as e:
        logger.debug(f"Top month error: {e}")

    try:
        top_all = db.get_top_messages_all_time(10)
        if top_all:
            has_data = True
            txt += "📈 <b>За всё время:</b>\n"
            for i, u in enumerate(top_all, 1):
                name = f"#{u['user_id']}"
                try:
                    member = await message.chat.get_member(u['user_id'])
                    name = member.user.first_name or name
                except:
                    pass
                m = medals[i - 1] if i <= 3 else f"{i}."
                txt += f"  {m} {name} — <b>{u['count']}</b> сообщений\n"
    except Exception as e:
        logger.debug(f"Top all time error: {e}")

    if not has_data:
        txt += "📭 Пока пусто! Пишите в чат, и статистика появится."

    await message.reply(txt)


# ================= HELP COMMAND =================

@dp.message(Command("start", "help"))
async def start_help_command(message: Message):
    text = (
        "<b>🎴 Добро пожаловать!</b>\n\n"

        "<b>📅 ЕЖЕДНЕВНОЕ</b>\n"
        "├ /daily — ежедневная награда\n"
        "└ /quests — квесты\n\n"

        "<b>🎟️ БИЛЕТЫ И СПИНЫ</b>\n"
        "├ /ticket — получить билет (30 мин)\n"
        "├ /tickets — мои билеты\n"
        "├ /spin — прокрутка\n"
        "├ /multispin — мультиспин\n"
        "├ /fusionspin — fusion спин (5 🎫 + 3 💎)\n"
        "└ /pity — счётчики гарантий\n\n"

        "<b>🎰 КАЗИНО</b>\n"
        "└ /casino — рулетка (ставь монеты!)\n\n"

        "<b>🃏 КАРТЫ</b>\n"
        "├ /mycards — мои карты\n"
        "├ /cards — все карты\n"
        "├ /card [имя] — инфо о карте\n"
        "├ /collection — статистика\n"
        "├ /limited — лимитки\n"
        "└ /topcards — топ карт\n\n"

        "<b>💎 MULTS И FUSION</b>\n"
        "├ /mults — меню Mults\n"
        "├ /exchange [кол-во] — монеты → Mults\n"
        "├ /fusion — соединение карт\n"
        "└ 📊 Курс: 100 🪙 = 1 💎\n\n"

        "<b>💰 ЭКОНОМИКА</b>\n"
        "├ /balance — мой баланс\n"
        "├ /market — магазин\n"
        "└ /pay — передать ресурсы\n\n"

        "<b>🏟️ АРЕНА</b>\n"
        "├ /arena — начать бой\n"
        "├ /setdeck — выбрать колоду\n"
        "├ /mydeck — моя колода\n"
        "├ /rating — топ игроков\n"
        "├ /profile — профиль\n"
        "└ /setbio — описание\n\n"

        "<b>🏆 РЕЙТИНГИ</b>\n"
        "├ /top — все рейтинги\n"
        "└ /topchat — топ активности\n\n"

        "<b>🎖️ РАНГИ</b>\n"
        "├ /ranks — администрация\n"
        "├ /myrank — мой ранг\n"
        "├ /ranklist — все ранги\n"
        "└ /perms — права ранга\n\n"

        "<b>🛡️ МОДЕРАЦИЯ</b>\n"
        "├ /warn, /unwarn, /warns\n"
        "├ /mute, /unmute\n"
        "├ /ban, /unban, /kick\n"
        "└ /rules, /setrules\n\n"

        "<b>💕 РП КОМАНДЫ</b>\n"
        "├ обнять, поцеловать, ударить...\n"
        "├ /rpstat — статистика РП\n"
        "├ /брак — предложить\n"
        "├ /развод — расторгнуть\n"
        "└ /браки — все браки\n\n"

        "<b>🎫 ПРОМОКОДЫ</b>\n"
        "└ /promo [код] — активировать\n\n"

        "<b>👑 АДМИН КОМАНДЫ</b>\n"
        "├ /promote, /demote\n"
        "├ /givecard, /givecoins, /givetickets\n"
        "├ /boostspin — буст удачи\n"
        "├ /createpromo — создать промо\n"
        "├ /resetcd — сброс кд\n"
        "└ /clearall — полный сброс\n\n"

        "<b>🎯 ГАРАНТИИ (PITY)</b>\n"
        "├ Epic: 15 спинов\n"
        "├ Legendary: 40 спинов\n"
        "└ Mythic: 100 спинов\n\n"

        "<i>⚠️ Данные отдельные для каждой группы!</i>"
    )
    await message.reply(text, parse_mode="HTML")


async def set_commands():
    commands = [
        BotCommand(command="start", description="🚀 Начать / Помощь"),
        BotCommand(command="help", description="❓ Показать команды"),
        BotCommand(command="daily", description="📅 Ежедневная награда"),
        BotCommand(command="quests", description="📋 Ежедневные квесты"),
        BotCommand(command="ticket", description="🎫 Получить билет"),
        BotCommand(command="tickets", description="🎟️ Мои билеты"),
        BotCommand(command="spin", description="🎰 Прокрутить карту"),
        BotCommand(command="multispin", description="🎰 Мультиспин"),
        BotCommand(command="casino", description="🎰 Казино-рулетка"),
        BotCommand(command="fusionspin", description="🔮 Fusion спин"),
        BotCommand(command="pity", description="🎯 Счётчики гарантий"),
        BotCommand(command="mycards", description="🃏 Мои карты"),
        BotCommand(command="cards", description="📋 Все карты"),
        BotCommand(command="card", description="🔍 Инфо о карте"),
        BotCommand(command="limited", description="⏳ Лимитированные карты"),
        BotCommand(command="collection", description="📊 Статистика коллекции"),
        BotCommand(command="top", description="🏆 Рейтинги"),
        BotCommand(command="topchat", description="💬 Топ активности чата"),
        BotCommand(command="balance", description="🪙 Мой баланс"),
        BotCommand(command="pay", description="💸 Передать ресурсы"),
        BotCommand(command="market", description="🛒 Магазин"),
        BotCommand(command="mults", description="💎 Меню Mults"),
        BotCommand(command="exchange", description="💱 Обменять монеты на Mults"),
        BotCommand(command="fusion", description="🔮 Соединение карт"),
        BotCommand(command="arena", description="🏟️ На арену"),
        BotCommand(command="setdeck", description="🃏 Выбрать колоду"),
        BotCommand(command="mydeck", description="📋 Моя колода"),
        BotCommand(command="rating", description="📈 Топ игроков"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="setbio", description="✏️ Изменить био"),
        BotCommand(command="ranks", description="🎖️ Администрация"),
        BotCommand(command="myrank", description="📊 Мой ранг"),
        BotCommand(command="rules", description="📜 Правила чата"),
        BotCommand(command="promo", description="🎫 Промокоды"),
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ Команды установлены")


async def main():
    logger.info("🚀 Бот запускается...")
    await set_commands()

    asyncio.create_task(check_expired_punishments())
    asyncio.create_task(battle.check_queue_periodically(bot))
    asyncio.create_task(stats_collector_loop())

    logger.info("✅ Бот готов к работе!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")