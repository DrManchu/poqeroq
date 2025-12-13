"""
Миграция: добавление множественных сообщений и first_name
- Создание таблицы game_messages для отслеживания всех сообщений стола
- Добавление поля first_name в таблицу users
"""

import aiosqlite
import asyncio
import os
import shutil
from datetime import datetime

DB_PATH = "poker_bot.db"


async def migrate():
    """Выполнение миграции"""

    # Создаем резервную копию
    if os.path.exists(DB_PATH):
        backup_path = f"poker_bot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, backup_path)
        print(f"✅ Создана резервная копия: {backup_path}")

    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем существующую структуру
        cursor = await db.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in await cursor.fetchall()}

        # 1. Добавляем first_name в users, если его нет
        if 'first_name' not in user_columns:
            print("Добавление поля first_name в таблицу users...")
            await db.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
            print("✅ Поле first_name добавлено")
        else:
            print("⏭ Поле first_name уже существует")

        # 2. Создаем таблицу game_messages
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='game_messages'"
        )
        table_exists = await cursor.fetchone()

        if not table_exists:
            print("Создание таблицы game_messages...")
            await db.execute("""
                CREATE TABLE game_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
                )
            """)

            # Создаем индексы для быстрого поиска
            await db.execute(
                "CREATE INDEX idx_game_messages_game_id ON game_messages(game_id)"
            )
            await db.execute(
                "CREATE INDEX idx_game_messages_chat_id ON game_messages(chat_id)"
            )

            print("✅ Таблица game_messages создана")

            # 3. Переносим существующие message_id из games в game_messages
            print("Перенос существующих message_id...")
            cursor = await db.execute("""
                SELECT game_id, chat_id, message_id
                FROM games
                WHERE message_id IS NOT NULL
            """)
            existing_messages = await cursor.fetchall()

            for game_id, chat_id, message_id in existing_messages:
                await db.execute("""
                    INSERT INTO game_messages (game_id, message_id, chat_id)
                    VALUES (?, ?, ?)
                """, (game_id, message_id, chat_id))

            print(f"✅ Перенесено {len(existing_messages)} сообщений")
        else:
            print("⏭ Таблица game_messages уже существует")

        await db.commit()
        print("\n🎉 Миграция успешно завершена!")


if __name__ == "__main__":
    print("=== Миграция: Множественные сообщения и first_name ===\n")
    asyncio.run(migrate())
