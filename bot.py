# bot.py
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
import asyncio
import logging
import threading
import config
from database import db
from handlers import purchase, main_menu
from webhook_server import start_webhook_server

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

    # Запускаем webhook сервер в отдельном потоке
    webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
    webhook_thread.start()
    print(f"🌐 Webhook сервер запущен на порту {config.WEBHOOK_PORT}")

    print("🎯 Запуск polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()