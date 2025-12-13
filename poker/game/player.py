"""
Модуль класса игрока в покер
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from game.deck import Card, cards_from_list, cards_to_list, format_cards
from game.evaluator import HandEvaluator, HandResult


@dataclass
class Player:
    """Класс игрока за покерным столом"""

    user_id: int
    username: str
    seat_position: int
    balance: int
    first_name: Optional[str] = None  # Имя пользователя для отображения

    # Карты игрока
    hole_cards: List[Card] = field(default_factory=list)
    
    # Ставки
    current_bet: int = 0      # Ставка в текущем раунде торговли
    total_bet: int = 0        # Всего вложено в банк за раздачу
    
    # Статус
    is_folded: bool = False
    is_all_in: bool = False
    is_active: bool = True
    
    # Дополнительно
    last_action: str = ""     # Последнее действие для отображения
    
    @property
    def is_in_hand(self) -> bool:
        """Игрок ещё в раздаче (не сфолдил и активен)"""
        return not self.is_folded and self.is_active
    
    @property
    def can_act(self) -> bool:
        """Игрок может совершить действие"""
        return self.is_in_hand and not self.is_all_in
    
    @property
    def effective_stack(self) -> int:
        """Эффективный стек (сколько ещё может поставить)"""
        return self.balance
    
    def get_hand_result(self, community_cards: List[Card]) -> Optional[HandResult]:
        """Получить результат комбинации"""
        if not self.hole_cards or self.is_folded:
            return None
        return HandEvaluator.evaluate(self.hole_cards, community_cards)
    
    def get_current_combination(self, community_cards: List[Card]) -> str:
        """Получить описание текущей комбинации"""
        return HandEvaluator.get_current_best(self.hole_cards, community_cards)
    
    def format_cards(self, hidden: bool = False) -> str:
        """Форматировать карты игрока"""
        if not self.hole_cards:
            return "[ 🂠 ] [ 🂠 ]"
        return format_cards(self.hole_cards, hidden=hidden)
    
    def place_bet(self, amount: int) -> int:
        """
        Сделать ставку
        
        Args:
            amount: Сумма ставки
            
        Returns:
            Фактическая сумма ставки (может быть меньше при олл-ине)
        """
        actual_amount = min(amount, self.balance)
        
        self.balance -= actual_amount
        self.current_bet += actual_amount
        self.total_bet += actual_amount
        
        if self.balance == 0:
            self.is_all_in = True
        
        return actual_amount
    
    def fold(self) -> None:
        """Сбросить карты"""
        self.is_folded = True
        self.last_action = "❌ Фолд"
    
    def call(self, amount_to_call: int) -> int:
        """
        Уравнять ставку
        
        Args:
            amount_to_call: Сумма для уравнивания
            
        Returns:
            Фактическая сумма колла
        """
        actual = self.place_bet(amount_to_call)
        if self.is_all_in:
            self.last_action = f"🔥 Олл-ин {self.total_bet}"
        else:
            self.last_action = f"✅ Колл {actual}"
        return actual
    
    def check(self) -> None:
        """Чек (пропуск без ставки)"""
        self.last_action = "📞 Чек"
    
    def raise_bet(self, total_amount: int) -> int:
        """
        Повысить ставку
        
        Args:
            total_amount: Общая сумма ставки (не добавка)
            
        Returns:
            Фактическая добавка к ставке
        """
        add_amount = total_amount - self.current_bet
        actual = self.place_bet(add_amount)
        
        if self.is_all_in:
            self.last_action = f"🔥 Олл-ин {self.total_bet}"
        else:
            self.last_action = f"⬆️ Рейз до {self.current_bet}"
        
        return actual
    
    def all_in(self) -> int:
        """
        Поставить всё
        
        Returns:
            Сумма олл-ина
        """
        amount = self.balance
        self.place_bet(amount)
        self.last_action = f"🔥 Олл-ин {self.total_bet}"
        return amount
    
    def reset_for_new_round(self) -> None:
        """Сброс для нового раунда торговли"""
        self.current_bet = 0
        self.last_action = ""
    
    def reset_for_new_hand(self) -> None:
        """Сброс для новой раздачи"""
        self.hole_cards = []
        self.current_bet = 0
        self.total_bet = 0
        self.is_folded = False
        self.is_all_in = False
        self.last_action = ""
    
    def get_status_emoji(self, is_current: bool = False, is_dealer: bool = False,
                         is_sb: bool = False, is_bb: bool = False) -> str:
        """Получить эмодзи статуса для отображения"""
        if self.is_folded:
            return "❌"
        if self.is_all_in:
            return "🔥"
        if is_current:
            return "⏳"
        if self.last_action:
            return "✅"
        return "👤"
    
    def get_position_label(self, is_dealer: bool = False,
                          is_sb: bool = False, is_bb: bool = False) -> str:
        """Получить метку позиции"""
        labels = []
        if is_dealer:
            labels.append("Ⓓ")
        if is_sb:
            labels.append("мб")
        if is_bb:
            labels.append("бб")
        return " ".join(labels)
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "seat_position": self.seat_position,
            "balance": self.balance,
            "first_name": self.first_name,
            "hole_cards": cards_to_list(self.hole_cards),
            "current_bet": self.current_bet,
            "total_bet": self.total_bet,
            "is_folded": self.is_folded,
            "is_all_in": self.is_all_in,
            "is_active": self.is_active,
            "last_action": self.last_action
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Player":
        """Десериализация из словаря"""
        player = cls(
            user_id=data["user_id"],
            username=data["username"],
            seat_position=data["seat_position"],
            balance=data["balance"],
            first_name=data.get("first_name")
        )
        player.hole_cards = cards_from_list(data.get("hole_cards", []))
        player.current_bet = data.get("current_bet", 0)
        player.total_bet = data.get("total_bet", 0)
        player.is_folded = data.get("is_folded", False)
        player.is_all_in = data.get("is_all_in", False)
        player.is_active = data.get("is_active", True)
        player.last_action = data.get("last_action", "")
        return player
    
    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "Player":
        """Создание из строки БД"""
        player = cls(
            user_id=row["user_id"],
            username=row["username"],
            seat_position=row["seat_position"],
            balance=row["user_balance"],
            first_name=row.get("first_name")
        )
        player.hole_cards = cards_from_list(row.get("hole_cards", []))
        player.current_bet = row.get("current_bet", 0)
        player.total_bet = row.get("total_bet", 0)
        player.is_folded = row.get("is_folded", False)
        player.is_all_in = row.get("is_all_in", False)
        player.is_active = row.get("is_active", True)
        return player
    
    def __repr__(self) -> str:
        return f"Player({self.username}, balance={self.balance}, folded={self.is_folded})"