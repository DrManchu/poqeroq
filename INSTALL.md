# 🔧 Инструкция по установке

## Быстрое решение проблемы "No module named 'aiogram'"

### Шаг 1: Перейдите в папку проекта

```bash
cd /path/to/poqeroq/poker
```

Замените `/path/to/poqeroq` на реальный путь к проекту.

### Шаг 2: Установите зависимости

Выполните одну из команд:

**Вариант 1 (рекомендуется):**
```bash
pip3 install -r requirements.txt
```

**Вариант 2 (если pip3 не найден):**
```bash
python3 -m pip install -r requirements.txt
```

**Вариант 3 (если нужны права root):**
```bash
sudo pip3 install -r requirements.txt
```

**Вариант 4 (установка конкретных пакетов):**
```bash
pip3 install aiogram==3.4.1 aiosqlite==0.19.0
```

### Шаг 3: Проверьте установку

```bash
python3 -c "import aiogram; import aiosqlite; print('✅ Все установлено!')"
```

Если видите `✅ Все установлено!` - отлично, переходите к шагу 4.

### Шаг 4: Запустите диагностику снова

```bash
python3 diagnose.py
```

Теперь должно быть 6/6 проверок пройдено!

---

## 🐛 Возможные проблемы и решения

### Проблема: "command not found: pip3"

**Решение:**
```bash
# Установите pip
sudo apt-get update
sudo apt-get install python3-pip

# Или на CentOS/RHEL
sudo yum install python3-pip
```

### Проблема: "Permission denied"

**Решение 1 - использовать sudo:**
```bash
sudo pip3 install -r requirements.txt
```

**Решение 2 - использовать виртуальное окружение (рекомендуется):**
```bash
# Создайте виртуальное окружение
python3 -m venv venv

# Активируйте его
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt

# Запустите бота
python bot.py
```

### Проблема: "No module named 'pip'"

**Решение:**
```bash
# Установите pip
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py

# Затем установите зависимости
pip3 install -r requirements.txt
```

### Проблема: Версия Python < 3.11

**Решение:**
```bash
# Проверьте версию
python3 --version

# Если версия старая, обновите Python
sudo apt-get update
sudo apt-get install python3.11

# Или используйте pyenv для управления версиями Python
```

---

## ✅ Полная пошаговая установка

### 1. Клонируйте или скачайте проект

```bash
git clone https://github.com/ВАШ_USERNAME/poqeroq.git
cd poqeroq/poker
```

### 2. Создайте виртуальное окружение (опционально, но рекомендуется)

```bash
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

### 4. Настройте токен бота

Откройте `config.py` и вставьте ваш токен:

```python
BOT_TOKEN: str = "ВАШ_ТОКЕН_ОТ_BOTFATHER"
```

### 5. Проверьте подключение

```bash
python3 test_bot.py
```

Должно появиться:
```
✅ Бот успешно подключен!
   ID: ...
   Username: @ваш_бот
```

### 6. Запустите полную диагностику

```bash
python3 diagnose.py
```

Должно быть: `Проверок пройдено: 6/6`

### 7. Запустите бота

```bash
python3 bot.py
```

Или используйте удобный скрипт:

```bash
chmod +x start.sh
./start.sh
```

---

## 🚀 Запуск бота в фоне (production)

### Вариант 1: screen

```bash
screen -S poker_bot
python3 bot.py
# Нажмите Ctrl+A, затем D для отключения

# Вернуться к боту:
screen -r poker_bot
```

### Вариант 2: tmux

```bash
tmux new -s poker_bot
python3 bot.py
# Нажмите Ctrl+B, затем D для отключения

# Вернуться:
tmux attach -t poker_bot
```

### Вариант 3: systemd (рекомендуется для production)

Создайте файл `/etc/systemd/system/poker-bot.service`:

```ini
[Unit]
Description=Telegram Poker Bot
After=network.target

[Service]
Type=simple
User=ваш_пользователь
WorkingDirectory=/path/to/poqeroq/poker
ExecStart=/usr/bin/python3 /path/to/poqeroq/poker/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Затем:

```bash
sudo systemctl daemon-reload
sudo systemctl enable poker-bot
sudo systemctl start poker-bot
sudo systemctl status poker-bot

# Просмотр логов:
sudo journalctl -u poker-bot -f
```

### Вариант 4: nohup (простой вариант)

```bash
nohup python3 bot.py > bot.log 2>&1 &

# Просмотр логов:
tail -f bot.log

# Остановка:
pkill -f bot.py
```

---

## 📞 Нужна помощь?

Если что-то не работает:

1. Запустите `python3 diagnose.py` и отправьте вывод
2. Проверьте лог-файл `poker_bot.log`
3. Убедитесь что у вас есть интернет: `curl -I https://api.telegram.org`

Удачи! 🃏
