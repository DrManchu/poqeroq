"""
Модуль работы с колодой карт
"""

import random
from typing import List, Tuple, Optional
from dataclasses import dataclass

from config import SUIT_EMOJI, RANK_SYMBOLS


@dataclass
class Card:
    """Класс игральной карты"""
    rank: int      # 2-14 (14 = Туз)
    suit: str      # hearts, diamonds, clubs, spades
    
    def __str__(self) -> str:
        """Строковое представление карты"""
        return f"{RANK_SYMBOLS[self.rank]}{SUIT_EMOJI[self.suit]}"
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Card):
            return False
        return self.rank == other.rank and self.suit == other.suit
    
    def __hash__(self) -> int:
        return hash((self.rank, self.suit))
    
    def __lt__(self, other) -> bool:
        """Сравнение карт по рангу"""
        return self.rank < other.rank
    
    def to_dict(self) -> dict:
        """Сериализация в словарь"""
        return {"rank": self.rank, "suit": self.suit}
    
    @classmethod
    def from_dict(cls, data: dict) -> "Card":
        """Десериализация из словаря"""
        return cls(rank=data["rank"], suit=data["suit"])
    
    def formatted(self) -> str:
        """Форматированное отображение для сообщений"""
        return f"[ {self} ]"


class Deck:
    """Колода карт"""
    
    SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
    RANKS = list(range(2, 15))  # 2-14 (14 = Туз)
    
    def __init__(self):
        self.cards: List[Card] = []
        self.reset()
    
    def reset(self) -> None:
        """Создать новую полную колоду и перемешать её"""
        self.cards = [
            Card(rank=rank, suit=suit) 
            for suit in self.SUITS 
            for rank in self.RANKS
        ]
        self.shuffle()
    
    def shuffle(self) -> None:
        """Перемешать колоду"""
        random.shuffle(self.cards)
    
    def deal(self, count: int = 1) -> List[Card]:
        """Раздать карты с верха колоды"""
        if count > len(self.cards):
            raise ValueError(f"Недостаточно карт в колоде: {len(self.cards)} < {count}")
        
        dealt = self.cards[:count]
        self.cards = self.cards[count:]
        return dealt
    
    def deal_one(self) -> Card:
        """Раздать одну карту"""
        return self.deal(1)[0]
    
    def burn(self) -> Card:
        """Сжечь карту (убрать с верха колоды)"""
        return self.deal_one()
    
    def remaining(self) -> int:
        """Количество оставшихся карт"""
        return len(self.cards)
    
    def to_list(self) -> List[dict]:
        """Сериализация в список словарей"""
        return [card.to_dict() for card in self.cards]
    
    @classmethod
    def from_list(cls, data: List[dict]) -> "Deck":
        """Десериализация из списка словарей"""
        deck = cls()
        # ВАЖНО: При загрузке не сбрасываем, а берем как есть
        deck.cards = [Card.from_dict(card_data) for card_data in data]
        return deck


def cards_to_list(cards: List[Card]) -> List[dict]:
    """Конвертировать список карт в список словарей для JSON"""
    return [card.to_dict() for card in cards]


def cards_from_list(data: List[dict]) -> List[Card]:
    """Конвертировать список словарей в список карт"""
    return [Card.from_dict(card_data) for card_data in data]


def format_cards(cards: List[Card], hidden: bool = False) -> str:
    """Форматировать карты для отображения"""
    if not cards:
        return "[ — ]"
    
    if hidden:
        return " ".join(["[ 🂠 ]"] * len(cards))
    
    return " ".join(card.formatted() for card in cards)


def format_community_cards(cards: List[Card]) -> str:
    """Форматировать общие карты стола (с пустыми слотами)"""
    result = []
    for i in range(5):
        if i < len(cards):
            result.append(cards[i].formatted())
        else:
            result.append("[ — ]")
    return " ".join(result)


def create_and_shuffle_deck() -> Deck:
    """Создать и перемешать новую колоду"""
    deck = Deck()
    deck.shuffle()
    return deck

def format_card(card) -> str:
    """
    Преобразует объект Card или кортеж в строку.
    Используется в handlers/callbacks.py.
    """
    if card is None:
        return "[?]"
    return str(card)