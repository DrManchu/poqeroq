#!/usr/bin/env python3
"""
Скрипт миграции базы данных - добавление полей статистики
Добавляет total_won, total_lost, best_win в таблицу users
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
        # Проверяем наличие таблицы users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            print("✅ Таблица users не найдена, миграция не требуется")
            return

        # Проверяем, существуют ли уже колонки
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]

        columns_to_add = []
        if 'total_won' not in columns:
            columns_to_add.append(('total_won', 'INTEGER DEFAULT 0'))
        if 'total_lost' not in columns:
            columns_to_add.append(('total_lost', 'INTEGER DEFAULT 0'))
        if 'best_win' not in columns:
            columns_to_add.append(('best_win', 'INTEGER DEFAULT 0'))

        if not columns_to_add:
            print("✅ Все колонки уже существуют, миграция не требуется")
            return

        # Добавляем колонки
        for col_name, col_def in columns_to_add:
            print(f"   Добавляю колонку {col_name}...")
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")

        conn.commit()
        print("✅ Миграция завершена успешно!")
        print(f"   Добавлено колонок: {len(columns_to_add)}")
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
    print("🗄️  МИГРАЦИЯ БАЗЫ ДАННЫХ - ДОБАВЛЕНИЕ СТАТИСТИКИ")
    print("=" * 50)
    migrate()
