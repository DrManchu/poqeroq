#!/usr/bin/env python3
"""
Скрипт для проверки работы бота
"""
import asyncio
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import config

async def test_bot():
    """Тестирование подключения к боту"""
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    try:
        print("🔄 Проверяю подключение к Telegram API...")
        bot_info = await bot.get_me()
        print(f"✅ Бот успешно подключен!")
        print(f"   ID: {bot_info.id}")
        print(f"   Имя: {bot_info.first_name}")
        print(f"   Username: @{bot_info.username}")
        print(f"   Может присоединяться к группам: {bot_info.can_join_groups}")
        print(f"   Может читать все сообщения: {bot_info.can_read_all_group_messages}")
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения к боту:")
        print(f"   {type(e).__name__}: {e}")
        print("\n💡 Возможные причины:")
        print("   1. Неправильный токен бота")
        print("   2. Токен был отозван через @BotFather")
        print("   3. Нет подключения к интернету")
        print("   4. Проблемы с DNS или файрволом")
        return False
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test_bot())
