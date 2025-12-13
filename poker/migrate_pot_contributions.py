"""
Миграция: добавление поля pot_contributions для сохранения истории ставок
"""
import aiosqlite
import asyncio
import os
import shutil
from datetime import datetime

DB_PATH = "poker_bot.db"

async def migrate():
    if os.path.exists(DB_PATH):
        backup_path = f"poker_bot_backup_contributions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, backup_path)
        print(f"✅ Создана резервная копия: {backup_path}")

    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем структуру таблицы games
        cursor = await db.execute("PRAGMA table_info(games)")
        columns = {row[1] for row in await cursor.fetchall()}

        if 'pot_contributions' not in columns:
            print("Добавление поля pot_contributions в таблицу games...")
            # Добавляем как TEXT, так как будем хранить JSON
            await db.execute("ALTER TABLE games ADD COLUMN pot_contributions TEXT DEFAULT '{}'")
            print("✅ Поле pot_contributions добавлено")
        else:
            print("⏭ Поле pot_contributions уже существует")

        await db.commit()
        print("\n🎉 Миграция успешно завершена!")

if __name__ == "__main__":
    asyncio.run(migrate())