"""
Точка входа Telegram покер-бота
"""

import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import config
from database import db

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('poker_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Хранилище активных таймеров игр
active_timers: dict = {}


async def on_startup() -> None:
    """Действия при запуске бота"""
    logger.info("Запуск покер-бота...")

    # Подключение к базе данных
    await db.connect()

    # Получаем информацию о боте
    try:
        bot_info = await bot.get_me()
        logger.info(f"Бот запущен: @{bot_info.username}")
    except Exception as e:
        logger.error(f"Не удалось получить информацию о боте: {e}")
        logger.info("Бот продолжит попытки подключения...")

    # Регистрируем команды бота
    try:
        from aiogram.types import BotCommand
        commands = [
            BotCommand(command="poker", description="🎮 Создать новый покерный стол"),
            BotCommand(command="table", description="🃏 Показать текущий стол"),
            BotCommand(command="balance", description="💰 Проверить баланс"),
            BotCommand(command="stats", description="📊 Статистика игрока"),
            BotCommand(command="give", description="🎁 Передать фишки"),
            BotCommand(command="top", description="🏆 Топ игроков"),
            BotCommand(command="help", description="ℹ️ Помощь"),
            BotCommand(command="closetable", description="🚪 Закрыть стол")
        ]
        await bot.set_my_commands(commands)
        logger.info("Команды бота зарегистрированы")
    except Exception as e:
        logger.error(f"Не удалось зарегистрировать команды: {e}")

    # ВОССТАНОВЛЕНИЕ АКТИВНЫХ ИГР
    try:
        from handlers.commands import restore_active_games
        await restore_active_games(bot)
    except Exception as e:
        logger.error(f"Ошибка восстановления игр: {e}")


async def on_shutdown() -> None:
    """Действия при остановке бота"""
    logger.info("Остановка покер-бота...")
    
    # Отмена всех активных таймеров
    for timer in active_timers.values():
        timer.cancel()
    
    # Закрытие соединения с БД
    await db.disconnect()
    
    # Закрытие сессии бота
    await bot.session.close()
    
    logger.info("Бот остановлен")


async def main() -> None:
    """Главная функция запуска"""

    print("1. Начинаю запуск...")
    logger.info("Запуск главной функции бота")

    # Регистрируем хуки запуска/остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    print("2. Подключаю роутеры...")
    logger.info("Регистрация роутеров")

    # Импортируем и регистрируем роутеры
    try:
        from handlers.commands import router as commands_router
        from handlers.menu import router as menu_router
        from handlers.callbacks import router as callbacks_router

        dp.include_router(menu_router)
        dp.include_router(commands_router)
        dp.include_router(callbacks_router)
        print("3. Роутеры подключены!")
        logger.info("Роутеры успешно подключены")
    except ImportError as e:
        print(f"ОШИБКА ИМПОРТА: {e}")
        logger.error(f"Ошибка импорта роутеров: {e}")
        raise

    print("4. Запускаю polling...")
    logger.info("Запуск long polling")

    # Запуск поллинга
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query"]
        )
    except Exception as e:
        logger.error(f"Ошибка во время polling: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")