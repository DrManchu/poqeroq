"""
Вспомогательные функции
"""

import re
from typing import Optional


def escape_html(text: str) -> str:
    """Экранировать HTML-спецсимволы"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def format_username(username: Optional[str], user_id: int) -> str:
    """Форматировать имя пользователя для отображения"""
    if username:
        return f"@{escape_html(username)}"
    return f"Игрок_{user_id}"


def format_chips(amount: int) -> str:
    """Форматировать количество фишек"""
    if amount >= 1000000:
        return f"{amount / 1000000:.1f}M"
    elif amount >= 1000:
        return f"{amount / 1000:.1f}K"
    return f"{amount:,}".replace(",", " ")


def format_chips_with_emoji(amount: int) -> str:
    """Форматировать фишки с эмодзи"""
    return f"{format_chips(amount)} 🪙"


def pluralize_chips(amount: int) -> str:
    """Склонение слова 'фишка'"""
    if amount % 10 == 1 and amount % 100 != 11:
        return "фишка"
    elif 2 <= amount % 10 <= 4 and (amount % 100 < 10 or amount % 100 >= 20):
        return "фишки"
    else:
        return "фишек"


def get_place_emoji(place: int) -> str:
    """Получить эмодзи для места в топе"""
    emojis = {
        1: "🥇",
        2: "🥈", 
        3: "🥉",
        4: "4️⃣",
        5: "5️⃣",
        6: "6️⃣",
        7: "7️⃣",
        8: "8️⃣",
        9: "9️⃣",
        10: "🔟"
    }
    return emojis.get(place, f"{place}.")


def parse_callback_data(data: str) -> tuple:
    """
    Разобрать callback_data
    
    Формат: action:game_id:param1:param2...
    """
    parts = data.split(":")
    action = parts[0]
    game_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    params = parts[2:] if len(parts) > 2 else []
    return action, game_id, params


def create_callback_data(action: str, game_id: int, *params) -> str:
    """Создать callback_data"""
    parts = [action, str(game_id)] + [str(p) for p in params]
    return ":".join(parts)


def calculate_pot_percentage(pot: int, percentage: float) -> int:
    """Рассчитать процент от банка (для ставок)"""
    return int(pot * percentage)


def round_to_blind(amount: int, big_blind: int) -> int:
    """Округлить сумму до ближайшего значения, кратного большому блайнду"""
    return (amount // big_blind) * big_blind


class Timer:
    """Простой класс для отслеживания таймаутов"""
    
    def __init__(self, seconds: int):
        self.seconds = seconds
        self.remaining = seconds
    
    def tick(self, elapsed: int = 1) -> int:
        """Уменьшить таймер, вернуть оставшееся время"""
        self.remaining = max(0, self.remaining - elapsed)
        return self.remaining
    
    def is_expired(self) -> bool:
        """Проверить, истёк ли таймер"""
        return self.remaining <= 0
    
    def reset(self) -> None:
        """Сбросить таймер"""
        self.remaining = self.seconds
    
    def format_remaining(self) -> str:
        """Форматировать оставшееся время"""
        minutes = self.remaining // 60
        seconds = self.remaining % 60
        if minutes > 0:
            return f"{minutes}:{seconds:02d}"
        return f"{seconds} сек"


# Эмодзи для разных событий
EMOJI = {
    "poker": "🃏",
    "money": "💰",
    "chips": "🪙",
    "winner": "🏆",
    "fold": "❌",
    "check": "📞",
    "call": "✅",
    "raise": "⬆️",
    "all_in": "🔥",
    "dealer": "Ⓓ",
    "thinking": "⏳",
    "timer": "⏱",
    "table": "🎴",
    "player": "👤",
    "crown": "👑",
    "party": "🎉",
    "warning": "⚠️",
    "info": "ℹ️",
    "star": "⭐",
    "fire": "🔥",
    "cards": "🎴",
    "sit": "🪑",
    "start": "🚀"
}


def get_emoji(name: str) -> str:
    """Получить эмодзи по имени"""
    return EMOJI.get(name, "")