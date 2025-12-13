"""
Миграция: добавление поля pot_contributions для фикса банков
"""
import aiosqlite
import asyncio
import os
import shutil
from datetime import datetime

DB_PATH = "poker_bot.db"

async def migrate():
    # 1. Делаем бэкап
    if os.path.exists(DB_PATH):
        backup_path = f"poker_bot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, backup_path)
        print(f"✅ Создана резервная копия: {backup_path}")

    async with aiosqlite.connect(DB_PATH) as db:
        # 2. Проверяем колонки
        cursor = await db.execute("PRAGMA table_info(games)")
        columns = {row[1] for row in await cursor.fetchall()}

        # 3. Добавляем pot_contributions
        if 'pot_contributions' not in columns:
            print("Добавление поля pot_contributions...")
            await db.execute("ALTER TABLE games ADD COLUMN pot_contributions TEXT DEFAULT '{}'")
            print("✅ Успешно добавлено!")
        else:
            print("⏭ Поле уже существует.")

        await db.commit()
        print("\n🎉 Готово! Теперь перезапустите бота.")

if __name__ == "__main__":
    asyncio.run(migrate())