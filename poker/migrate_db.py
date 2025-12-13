#!/usr/bin/env python3
"""
Скрипт миграции базы данных
Удаляет UNIQUE constraint который вызывал ошибки
"""
import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = "poker_bot.db"

def migrate():
    """Выполнить миграцию"""

    if not os.path.exists(DB_PATH):
        print(f"❌ База данных {DB_PATH} не найдена")
        print("   Миграция не требуется для новой установки")
        return

    # Создаем бэкап
    backup_path = f"{DB_PATH}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"📦 Создаю резервную копию: {backup_path}")
    shutil.copy2(DB_PATH, backup_path)

    print("🔧 Начинаю миграцию...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Проверяем наличие таблицы games
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='games'")
        if not cursor.fetchone():
            print("✅ Таблица games не найдена, миграция не требуется")
            return

        # Создаем временную таблицу без UNIQUE constraint
        print("   Создаю новую структуру таблицы...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games_new (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER,
                status TEXT DEFAULT 'waiting',
                pot INTEGER DEFAULT 0,
                current_bet INTEGER DEFAULT 0,
                dealer_index INTEGER DEFAULT 0,
                current_player_index INTEGER DEFAULT 0,
                community_cards TEXT DEFAULT '[]',
                deck TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Копируем данные
        print("   Копирую данные...")
        cursor.execute("""
            INSERT INTO games_new
            SELECT game_id, chat_id, message_id, status, pot, current_bet,
                   dealer_index, current_player_index, community_cards, deck, created_at
            FROM games
        """)

        # Удаляем старую таблицу
        print("   Удаляю старую таблицу...")
        cursor.execute("DROP TABLE games")

        # Переименовываем новую таблицу
        print("   Переименовываю новую таблицу...")
        cursor.execute("ALTER TABLE games_new RENAME TO games")

        conn.commit()
        print("✅ Миграция завершена успешно!")
        print(f"   Резервная копия сохранена в: {backup_path}")

    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        conn.rollback()
        print("   Восстанавливаю из резервной копии...")
        conn.close()
        shutil.copy2(backup_path, DB_PATH)
        print("✅ База данных восстановлена из резервной копии")
    finally:
        conn.close()

if __name__ == "__main__":
    print("🗄️  МИГРАЦИЯ БАЗЫ ДАННЫХ")
    print("=" * 50)
    migrate()
