#!/usr/bin/env python3
"""
Скрипт диагностики проблем с ботом
"""
import sys
import os
import asyncio
from datetime import datetime

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def check_python_version():
    """Проверка версии Python"""
    print_header("1. Проверка версии Python")
    version = sys.version_info
    print(f"Python версия: {version.major}.{version.minor}.{version.micro}")

    if version.major < 3 or (version.major == 3 and version.minor < 11):
        print("❌ Требуется Python 3.11 или новее!")
        return False
    else:
        print("✅ Версия Python подходит")
        return True

def check_dependencies():
    """Проверка установленных зависимостей"""
    print_header("2. Проверка зависимостей")

    required = {
        'aiogram': '3.4.1',
        'aiosqlite': '0.19.0',
    }

    all_ok = True
    for package, expected_version in required.items():
        try:
            module = __import__(package)
            version = getattr(module, '__version__', 'unknown')
            print(f"✅ {package}: {version}")
        except ImportError:
            print(f"❌ {package}: НЕ УСТАНОВЛЕН!")
            all_ok = False

    if not all_ok:
        print("\n💡 Для установки зависимостей выполните:")
        print("   pip3 install -r requirements.txt")

    return all_ok

def check_config():
    """Проверка конфигурации"""
    print_header("3. Проверка конфигурации")

    try:
        from config import config

        print(f"Токен бота: {config.BOT_TOKEN[:10]}...{config.BOT_TOKEN[-10:]}")
        print(f"Длина токена: {len(config.BOT_TOKEN)} символов")

        if len(config.BOT_TOKEN) < 40:
            print("❌ Токен слишком короткий! Проверьте токен в config.py")
            return False

        print(f"✅ База данных: {config.DATABASE_PATH}")
        print(f"✅ Начальный баланс: {config.STARTING_BALANCE}")
        print(f"✅ Блайнды: {config.BLINDS}")
        print(f"✅ Игроки: {config.MIN_PLAYERS}-{config.MAX_PLAYERS}")

        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        return False

def check_files():
    """Проверка наличия необходимых файлов"""
    print_header("4. Проверка файлов")

    required_files = [
        'bot.py',
        'config.py',
        'database.py',
        'requirements.txt',
        'game/__init__.py',
        'game/deck.py',
        'game/evaluator.py',
        'game/player.py',
        'game/poker.py',
        'handlers/__init__.py',
        'handlers/callbacks.py',
        'handlers/commands.py',
        'ui/__init__.py',
        'ui/keyboards.py',
        'ui/messages.py',
        'utils/__init__.py',
        'utils/helpers.py',
    ]

    all_ok = True
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            print(f"❌ {file} - ОТСУТСТВУЕТ!")
            all_ok = False

    return all_ok

async def check_bot_connection():
    """Проверка подключения к Telegram API"""
    print_header("5. Проверка подключения к Telegram API")

    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from config import config

        bot = Bot(
            token=config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

        print("🔄 Подключение к API Telegram...")

        try:
            bot_info = await bot.get_me()
            print(f"✅ Бот успешно подключен!")
            print(f"   ID: {bot_info.id}")
            print(f"   Имя: {bot_info.first_name}")
            print(f"   Username: @{bot_info.username}")
            print(f"   Может присоединяться к группам: {bot_info.can_join_groups}")
            print(f"   Может читать все сообщения: {bot_info.can_read_all_group_messages}")

            await bot.session.close()
            return True
        except Exception as e:
            print(f"❌ Не удалось подключиться к Telegram API:")
            print(f"   {type(e).__name__}: {e}")
            print("\n💡 Возможные причины:")
            print("   1. Неправильный токен бота")
            print("   2. Токен был отозван через @BotFather")
            print("   3. Нет подключения к интернету")
            print("   4. Проблемы с DNS или файрволом")

            await bot.session.close()
            return False

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def check_database():
    """Проверка базы данных"""
    print_header("6. Проверка базы данных")

    try:
        from config import config
        db_path = config.DATABASE_PATH

        if os.path.exists(db_path):
            size = os.path.getsize(db_path)
            modified = datetime.fromtimestamp(os.path.getmtime(db_path))
            print(f"✅ База данных найдена: {db_path}")
            print(f"   Размер: {size} байт")
            print(f"   Изменена: {modified}")
        else:
            print(f"ℹ️  База данных будет создана при первом запуске: {db_path}")

        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def print_summary(results):
    """Вывод итогов"""
    print_header("ИТОГИ ДИАГНОСТИКИ")

    total = len(results)
    passed = sum(results.values())

    print(f"Проверок пройдено: {passed}/{total}")

    if passed == total:
        print("\n✅ Все проверки пройдены! Бот готов к запуску.")
        print("\nДля запуска используйте:")
        print("   python3 bot.py")
        print("   или")
        print("   ./start.sh")
    else:
        print("\n❌ Обнаружены проблемы. Исправьте их перед запуском бота.")
        print("\nНе пройдены проверки:")
        for name, result in results.items():
            if not result:
                print(f"   - {name}")

async def main():
    """Главная функция"""
    print(f"\n🔍 ДИАГНОСТИКА ПОКЕРНОГО БОТА")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = {}

    results['Python версия'] = check_python_version()
    results['Зависимости'] = check_dependencies()
    results['Конфигурация'] = check_config()
    results['Файлы проекта'] = check_files()
    results['База данных'] = check_database()
    results['Подключение к API'] = await check_bot_connection()

    print_summary(results)

if __name__ == "__main__":
    asyncio.run(main())
