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
    bot_info = await bot.get_me()
    logger.info(f"Бот запущен: @{bot_info.username}")


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
    
    # Регистрируем хуки запуска/остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    print("2. Подключаю роутеры...")
    
    # Импортируем и регистрируем роутеры
    try:
        from handlers.commands import router as commands_router
        from handlers.callbacks import router as callbacks_router
        
        dp.include_router(commands_router)
        dp.include_router(callbacks_router)
        print("3. Роутеры подключены!")
    except ImportError as e:
        print(f"ОШИБКА ИМПОРТА: {e}")
    
    print("4. Запускаю polling...")
    
    # Запуск поллинга
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query"]
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")