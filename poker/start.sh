#!/bin/bash
# Скрипт для запуска покерного бота

cd "$(dirname "$0")"

echo "🃏 Запуск покерного бота..."

# Проверка зависимостей
if ! python3 -c "import aiogram" 2>/dev/null; then
    echo "⚠️  Установка зависимостей..."
    pip3 install -r requirements.txt
fi

# Запуск бота
python3 bot.py
