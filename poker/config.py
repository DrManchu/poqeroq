"""
Конфигурация покерного бота
"""

import os
from dataclasses import dataclass
from typing import Tuple


@dataclass
class Config:
    """Настройки бота"""
    
    # Токен бота (получить у @BotFather)
    BOT_TOKEN: str = "8454996475:AAHE7ZqJ8FZIoP_Jj88fsLPpEIi5ZVAW5JE"
    
    # Путь к базе данных
    DATABASE_PATH: str = "poker_bot.db"
    
    # Блайнды (малый, большой)
    BLINDS: Tuple[int, int] = (50, 100)
    
    # Начальный баланс игрока
    STARTING_BALANCE: int = 10000
    
    # Лимиты игроков за столом
    MIN_PLAYERS: int = 2
    MAX_PLAYERS: int = 8
    
    # Таймауты (в секундах)
    JOIN_TIMEOUT: int = 60       # Время на присоединение к столу
    TURN_TIMEOUT: int = 60       # Время на принятие решения
    NEXT_HAND_DELAY: int = 10    # Пауза между раздачами
    TIMER_UPDATE_INTERVAL: int = 10  # Интервал обновления таймера
    
    # Минимальный рейз (множитель большого блайнда)
    MIN_RAISE_MULTIPLIER: int = 2


# Глобальный экземпляр конфига
config = Config()


# Эмодзи для карт
SUIT_EMOJI = {
    'hearts': '♥️',
    'diamonds': '♦️', 
    'clubs': '♣️',
    'spades': '♠️'
}

# Названия мастей на русском
SUIT_NAMES = {
    'hearts': 'черви',
    'diamonds': 'бубны',
    'clubs': 'трефы', 
    'spades': 'пики'
}

# Названия рангов
RANK_NAMES = {
    14: 'Туз',
    13: 'Король',
    12: 'Дама',
    11: 'Валет',
    10: '10',
    9: '9',
    8: '8',
    7: '7',
    6: '6',
    5: '5',
    4: '4',
    3: '3',
    2: '2'
}

# Короткие обозначения рангов
RANK_SYMBOLS = {
    14: 'A',
    13: 'K',
    12: 'Q',
    11: 'J',
    10: '10',
    9: '9',
    8: '8',
    7: '7',
    6: '6',
    5: '5',
    4: '4',
    3: '3',
    2: '2'
}

# Названия комбинаций
HAND_NAMES = {
    10: '🏆 Роял-флеш',
    9: '👑 Стрит-флеш',
    8: '🔥 Каре',
    7: '🏠 Фулл-хаус',
    6: '🎨 Флеш',
    5: '📊 Стрит',
    4: '🎯 Тройка',
    3: '✌️ Две пары',
    2: '👆 Пара',
    1: '🃏 Старшая карта'
}