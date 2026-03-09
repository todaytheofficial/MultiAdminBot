# main.py
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Message, BotCommand
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from handlers import admin, cards, battle, market, trade, pay, upgrade

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ================= ПОДКЛЮЧАЕМ РОУТЕРЫ =================

dp.include_router(admin.router)
dp.include_router(cards.router)
dp.include_router(battle.router)
dp.include_router(market.router)
dp.include_router(trade.router)
dp.include_router(pay.router)
dp.include_router(upgrade.router)

# ================= KEEP-ALIVE WEB SERVER =================

async def health_check(request):
    """Эндпоинт для проверки здоровья — не даёт Render усыпить сервис"""
    return web.Response(text="OK", status=200)


async def start_web_server():
    """Запуск веб-сервера для keep-alive"""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render использует переменную PORT
    import os
    port = int(os.getenv("PORT", 10000))
    
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Web server started on port {port}")


async def self_ping():
    """Пингуем сами себя каждые 10 минут чтобы не заснуть"""
    import os
    import aiohttp
    
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        logger.info("⚠️ RENDER_EXTERNAL_URL not set, self-ping disabled")
        return
    
    await asyncio.sleep(60)  # Ждём минуту после старта
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/health", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.debug("🏓 Self-ping OK")
        except Exception as e:
            logger.debug(f"Self-ping error: {e}")
        
        await asyncio.sleep(600)  # Каждые 10 минут


# ================= HELP COMMAND =================

@dp.message(Command("start", "help"))
async def start_help_command(message: Message):
    text = (
        "<b>🎴 Добро пожаловать!</b>\n\n"

        "<b>🎟️ БИЛЕТЫ И СПИНЫ</b>\n"
        "├ /ticket — получить билет (30 мин)\n"
        "├ /tickets — мои билеты\n"
        "├ /spin — прокрутка карты (КД 30 мин)\n"
        "└ /multispin — мультиспин (КД 1 час)\n\n"

         "<b>🃏 КАРТЫ</b>\n"
"├ /mycards — мои карты\n"
"├ /card [имя] — инфо о карте\n"
"├ /upgrade — улучшить карты 🔮\n"
"└ /collection — статистика коллекции\n\n" 
        "<b>💰 ЭКОНОМИКА</b>\n"
        "├ /balance — мой баланс\n"
        "├ /market — магазин\n"
        "└ /pay — передать ресурсы\n\n"

        "<b>🏟️ АРЕНА</b>\n"
        "├ /arena — начать бой\n"
        "├ /setdeck — выбрать колоду\n"
        "└ /mydeck — моя колода\n\n"

        "<b>🏆 РЕЙТИНГИ</b>\n"
        "└ /top — все рейтинги\n\n"

        "<b>🛡️ МОДЕРАЦИЯ</b>\n"
        "├ /warn, /unwarn, /warns\n"
        "├ /mute, /unmute\n"
        "├ /ban, /unban, /kick\n"
        "└ /rules, /setrules\n\n"

        "<b>🎖️ РАНГИ</b>\n"
        "├ /ranks — администрация\n"
        "├ /myrank — мой ранг\n"
        "├ /ranklist — все ранги\n"
        "└ /perms — права ранга\n\n"

        "<b>👑 АДМИН КОМАНДЫ</b>\n"
        "├ /promote, /demote\n"
        "├ /givecard, /givecoins, /givetickets\n"
        "└ /clearall — полный сброс\n\n"

        "<i>⚠️ Данные отдельные для каждой группы!</i>"
    )
    await message.reply(text)


async def set_commands():
    commands = [
        BotCommand(command="start", description="🚀 Начать / Помощь"),
        BotCommand(command="help", description="❓ Показать команды"),
        BotCommand(command="ticket", description="🎫 Получить билет"),
        BotCommand(command="tickets", description="🎟️ Мои билеты"),
        BotCommand(command="spin", description="🎰 Прокрутить карту"),
        BotCommand(command="multispin", description="🎰 Мультиспин"),
        BotCommand(command="mycards", description="🃏 Мои карты"),
        BotCommand(command="card", description="🔍 Инфо о карте"),
        BotCommand(command="collection", description="📊 Статистика коллекции"),
        BotCommand(command="top", description="🏆 Рейтинги"),
        BotCommand(command="balance", description="🪙 Мой баланс"),
        BotCommand(command="pay", description="💸 Передать ресурсы"),
        BotCommand(command="market", description="🛒 Магазин"),
        BotCommand(command="arena", description="🏟️ На арену"),
        BotCommand(command="setdeck", description="🃏 Выбрать колоду"),
        BotCommand(command="mydeck", description="📋 Моя колода"),
        BotCommand(command="warn", description="⚠️ Предупредить"),
        BotCommand(command="mute", description="🔇 Замутить"),
        BotCommand(command="ban", description="🔨 Забанить"),
        BotCommand(command="rules", description="📜 Правила чата"),
        BotCommand(command="ranks", description="🎖️ Администрация"),
        BotCommand(command="myrank", description="📊 Мой ранг"),
BotCommand(command="upgrade", description="🔮 Улучшить карты"),
    ]
    await bot.set_my_commands(commands)
    logger.info("✅ Команды установлены")


async def start_bot():
    logger.info("🚀 Бот запускается...")
    
    # Запускаем веб-сервер для keep-alive
    await start_web_server()
    
    await set_commands()

    # Фоновые задачи
    asyncio.create_task(battle.check_queue_periodically(bot))
    asyncio.create_task(self_ping())

    logger.info("✅ Бот готов к работе!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(start_bot())