# main.py
import asyncio
import logging
import json
import os
import aiohttp
from aiohttp import web
from datetime import datetime
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message, BotCommand, ChatPermissions, Update
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, EMOJI
from handlers import admin, cards, battle, market, trade, daily, promo, quests, mults, rp, pay, stock
from database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ═══════════════════════════════════════════════
#  ВЕБ-СЕРВЕР ДЛЯ RENDER
# ═══════════════════════════════════════════════

web_app = web.Application()


async def health_check(request):
    return web.Response(text="OK")


web_app.router.add_get("/", health_check)
web_app.router.add_get("/health", health_check)


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
dp.include_router(pay.router)
dp.include_router(stock.router)

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
            try:
                # Для MongoDB
                users = list(group_db._col("users").find())
                total_users += len(users)
                
                for user in users:
                    cards_list = user.get("cards", [])
                    total_cards += len(cards_list)
                    for card in cards_list:
                        rar = card.get("rarity", "common")
                        cards_by_rarity[rar] = cards_by_rarity.get(rar, 0) + 1
                    
                    total_mults_global += user.get("total_mults_earned", 0)
                    total_fusions_global += user.get("total_fusions", 0)
                
                total_battles += group_db._col("battles").count_documents({})
            except Exception as e:
                logger.debug(f"Stats collect error for group: {e}")
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


# ═══════════════════════════════════════════════
#  ЗАПУСК БОТА (для Render)
# ═══════════════════════════════════════════════

async def start_bot():
    """Запуск бота в фоне"""
    await asyncio.sleep(2)
    logger.info("🚀 Бот запускается...")
    await set_commands()

    asyncio.create_task(check_expired_punishments())
    asyncio.create_task(battle.check_queue_periodically(bot))
    asyncio.create_task(stats_collector_loop())

    logger.info("✅ Бот готов к работе!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def on_startup(app):
    """При старте веб-сервера запускаем бота"""
    asyncio.create_task(start_bot())


web_app.on_startup.append(on_startup)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🌐 Web server starting on port {port}...")
    web.run_app(web_app, host="0.0.0.0", port=port)