# bot.py
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
import asyncio
import logging
import signal
import uvicorn
import config
from database import db
from handlers import purchase, main_menu
from webhook_server import app as webhook_app
from notifications import notifications_loop

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="profile", description="👤 Мой профиль"),
        BotCommand(command="referrals", description="👥 Рефералы"),
    ]
    await bot.set_my_commands(commands)


async def main():
    print("🚀 Запуск бота...")

    await db.init_db()
    print("✅ База данных инициализирована")

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(main_menu.router)
    dp.include_router(purchase.router)
    print("✅ Роутеры подключены")

    await set_commands(bot)
    print("✅ Команды установлены")

    # Uvicorn-сервер запускаем как asyncio-задачу В ТОМ ЖЕ event loop,
    # что и polling (а не в отдельном потоке) — иначе systemd не может
    # дождаться корректного завершения процесса по SIGTERM и убивает
    # его по таймауту (TimeoutStopSec).
    uvicorn_config = uvicorn.Config(
        webhook_app,
        host=config.WEBHOOK_HOST,
        port=config.WEBHOOK_PORT,
        log_level="info",
    )
    server = uvicorn.Server(uvicorn_config)
    # uvicorn по умолчанию сам пытается поставить обработчики сигналов —
    # отключаем, обработку сигналов делаем централизованно ниже
    server.install_signal_handlers = lambda: None

    webhook_task = asyncio.create_task(server.serve(), name="webhook_server")
    notifications_task = asyncio.create_task(notifications_loop(bot), name="notifications_loop")
    print(f"🌐 Webhook сервер запущен на порту {config.WEBHOOK_PORT}")

    stop_event = asyncio.Event()

    def _handle_shutdown_signal(sig_name: str):
        logger.info(f"🛑 Получен сигнал {sig_name}, начинаю остановку...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_shutdown_signal, sig.name)

    print("🎯 Запуск polling...")
    polling_task = asyncio.create_task(dp.start_polling(bot), name="polling")
    stop_future = asyncio.ensure_future(stop_event.wait())

    # Ждём либо сигнал остановки, либо аварийное завершение одной из задач
    done, pending = await asyncio.wait(
        {polling_task, webhook_task, notifications_task, stop_future},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if not stop_future.done():
        stop_future.cancel()

    logger.info("🔻 Останавливаю все задачи...")

    server.should_exit = True
    await dp.stop_polling()

    for task in (polling_task, webhook_task, notifications_task):
        if not task.done():
            task.cancel()

    await asyncio.gather(polling_task, webhook_task, notifications_task, return_exceptions=True)

    await bot.session.close()
    logger.info("✅ Бот корректно остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()