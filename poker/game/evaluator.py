"""
Модуль оценки покерных комбинаций
Определяет лучшую 5-карточную комбинацию из 7 карт
"""

from typing import List, Tuple, Optional
from itertools import combinations
from collections import Counter
from dataclasses import dataclass

from game.deck import Card
from config import HAND_NAMES, RANK_NAMES


@dataclass
class HandResult:
    """Результат оценки руки"""
    rank: int                    # Ранг комбинации (1-10)
    values: Tuple[int, ...]      # Значения для сравнения
    name: str                    # Название комбинации
    description: str             # Подробное описание
    best_cards: List[Card]       # Лучшие 5 карт
    
    def __lt__(self, other: "HandResult") -> bool:
        """Сравнение комбинаций"""
        if self.rank != other.rank:
            return self.rank < other.rank
        return self.values < other.values
    
    def __eq__(self, other: "HandResult") -> bool:
        return self.rank == other.rank and self.values == other.values
    
    def __le__(self, other: "HandResult") -> bool:
        return self < other or self == other


class HandEvaluator:
    """Оценщик покерных комбинаций"""
    
    # Ранги комбинаций
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10
    
    @classmethod
    def evaluate(cls, hole_cards: List[Card], community_cards: List[Card]) -> HandResult:
        """
        Оценить лучшую комбинацию из 7 карт (2 карманные + 5 общих)
        
        Args:
            hole_cards: Карманные карты игрока (2 карты)
            community_cards: Общие карты на столе (3-5 карт)
            
        Returns:
            HandResult с лучшей комбинацией
        """
        all_cards = hole_cards + community_cards
        
        if len(all_cards) < 5:
            # Недостаточно карт, возвращаем что есть
            return cls._evaluate_five(all_cards + [Card(2, 'spades')] * (5 - len(all_cards)))
        
        # Перебираем все комбинации из 5 карт
        best_result = None
        for five_cards in combinations(all_cards, 5):
            result = cls._evaluate_five(list(five_cards))
            if best_result is None or result > best_result:
                best_result = result
        
        return best_result
    
    @classmethod
    def _evaluate_five(cls, cards: List[Card]) -> HandResult:
        """Оценить комбинацию из ровно 5 карт"""
        
        # Сортируем по рангу (убывание)
        sorted_cards = sorted(cards, key=lambda c: c.rank, reverse=True)
        ranks = [c.rank for c in sorted_cards]
        suits = [c.suit for c in sorted_cards]
        
        # Подсчёт рангов и мастей
        rank_counts = Counter(ranks)
        suit_counts = Counter(suits)
        
        # Проверяем флеш
        is_flush = max(suit_counts.values()) == 5
        
        # Проверяем стрит
        is_straight, straight_high = cls._check_straight(ranks)
        
        # Группируем ранги по количеству
        count_groups = {}
        for rank, count in rank_counts.items():
            if count not in count_groups:
                count_groups[count] = []
            count_groups[count].append(rank)
        
        # Сортируем группы по рангу (убывание)
        for count in count_groups:
            count_groups[count].sort(reverse=True)
        
        # Определяем комбинацию
        
        # Роял-флеш
        if is_flush and is_straight and straight_high == 14:
            return HandResult(
                rank=cls.ROYAL_FLUSH,
                values=(14,),
                name=HAND_NAMES[10],
                description="Роял-флеш!",
                best_cards=sorted_cards
            )
        
        # Стрит-флеш
        if is_flush and is_straight:
            return HandResult(
                rank=cls.STRAIGHT_FLUSH,
                values=(straight_high,),
                name=HAND_NAMES[9],
                description=f"Стрит-флеш до {RANK_NAMES[straight_high]}",
                best_cards=sorted_cards
            )
        
        # Каре
        if 4 in count_groups:
            quad_rank = count_groups[4][0]
            kicker = count_groups.get(1, [0])[0]
            return HandResult(
                rank=cls.FOUR_OF_A_KIND,
                values=(quad_rank, kicker),
                name=HAND_NAMES[8],
                description=f"Каре {RANK_NAMES[quad_rank]}",
                best_cards=sorted_cards
            )
        
        # Фулл-хаус
        if 3 in count_groups and 2 in count_groups:
            trips_rank = count_groups[3][0]
            pair_rank = count_groups[2][0]
            return HandResult(
                rank=cls.FULL_HOUSE,
                values=(trips_rank, pair_rank),
                name=HAND_NAMES[7],
                description=f"Фулл-хаус: {RANK_NAMES[trips_rank]} и {RANK_NAMES[pair_rank]}",
                best_cards=sorted_cards
            )
        
        # Флеш
        if is_flush:
            return HandResult(
                rank=cls.FLUSH,
                values=tuple(ranks),
                name=HAND_NAMES[6],
                description=f"Флеш до {RANK_NAMES[ranks[0]]}",
                best_cards=sorted_cards
            )
        
        # Стрит
        if is_straight:
            return HandResult(
                rank=cls.STRAIGHT,
                values=(straight_high,),
                name=HAND_NAMES[5],
                description=f"Стрит до {RANK_NAMES[straight_high]}",
                best_cards=sorted_cards
            )
        
        # Тройка
        if 3 in count_groups:
            trips_rank = count_groups[3][0]
            kickers = count_groups.get(1, [0, 0])[:2]
            return HandResult(
                rank=cls.THREE_OF_A_KIND,
                values=(trips_rank,) + tuple(kickers),
                name=HAND_NAMES[4],
                description=f"Тройка {RANK_NAMES[trips_rank]}",
                best_cards=sorted_cards
            )
        
        # Две пары
        if 2 in count_groups and len(count_groups[2]) >= 2:
            pairs = count_groups[2][:2]
            kicker = count_groups.get(1, [0])[0]
            return HandResult(
                rank=cls.TWO_PAIR,
                values=(pairs[0], pairs[1], kicker),
                name=HAND_NAMES[3],
                description=f"Две пары: {RANK_NAMES[pairs[0]]} и {RANK_NAMES[pairs[1]]}",
                best_cards=sorted_cards
            )
        
        # Пара
        if 2 in count_groups:
            pair_rank = count_groups[2][0]
            kickers = count_groups.get(1, [0, 0, 0])[:3]
            return HandResult(
                rank=cls.PAIR,
                values=(pair_rank,) + tuple(kickers),
                name=HAND_NAMES[2],
                description=f"Пара {RANK_NAMES[pair_rank]}",
                best_cards=sorted_cards
            )
        
        # Старшая карта
        return HandResult(
            rank=cls.HIGH_CARD,
            values=tuple(ranks),
            name=HAND_NAMES[1],
            description=f"Старшая карта: {RANK_NAMES[ranks[0]]}",
            best_cards=sorted_cards
        )
    
    @classmethod
    def _check_straight(cls, ranks: List[int]) -> Tuple[bool, int]:
        """
        Проверить наличие стрита
        
        Returns:
            (is_straight, high_card)
        """
        unique_ranks = sorted(set(ranks), reverse=True)
        
        if len(unique_ranks) < 5:
            return False, 0
        
        # Обычный стрит
        for i in range(len(unique_ranks) - 4):
            window = unique_ranks[i:i+5]
            if window[0] - window[4] == 4:
                return True, window[0]
        
        # Стрит A-2-3-4-5 (колесо)
        if set([14, 5, 4, 3, 2]).issubset(set(unique_ranks)):
            return True, 5  # Старшая карта - 5
        
        return False, 0
    
    @classmethod
    def get_current_best(cls, hole_cards: List[Card], community_cards: List[Card]) -> str:
        """
        Получить описание текущей лучшей комбинации
        (для показа игроку во время игры)
        """
        if not community_cards:
            # Только карманные карты
            if len(hole_cards) == 2:
                if hole_cards[0].rank == hole_cards[1].rank:
                    return f"👆 Пара {RANK_NAMES[hole_cards[0].rank]}"
                else:
                    high = max(hole_cards[0].rank, hole_cards[1].rank)
                    return f"🃏 Старшая: {RANK_NAMES[high]}"
            return "🃏 Ожидание карт..."
        
        result = cls.evaluate(hole_cards, community_cards)
        return f"{result.name}"


def compare_hands(results: List[Tuple[int, HandResult]]) -> List[List[int]]:
    """
    Сравнить руки нескольких игроков
    
    Args:
        results: Список кортежей (user_id, HandResult)
        
    Returns:
        Список списков user_id победителей (группы при сплите)
    """
    if not results:
        return []
    
    # Сортируем по силе руки (убывание)
    sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
    
    # Группируем равные руки
    winners = []
    current_group = [sorted_results[0][0]]
    current_hand = sorted_results[0][1]
    
    for user_id, hand_result in sorted_results[1:]:
        if hand_result == current_hand:
            current_group.append(user_id)
        else:
            winners.append(current_group)
            current_group = [user_id]
            current_hand = hand_result
    
    winners.append(current_group)
    return winners


# Тестирование
if __name__ == "__main__":
    from game.deck import Deck, format_cards
    
    deck = Deck()
    deck.shuffle()
    
    # Раздаём тестовые руки
    hole1 = deck.deal(2)
    hole2 = deck.deal(2)
    
    community = deck.deal(5)
    
    print(f"Рука 1: {format_cards(hole1)}")
    print(f"Рука 2: {format_cards(hole2)}")
    print(f"Стол: {format_cards(community)}")
    print()
    
    result1 = HandEvaluator.evaluate(hole1, community)
    result2 = HandEvaluator.evaluate(hole2, community)
    
    print(f"Игрок 1: {result1.name} - {result1.description}")
    print(f"Игрок 2: {result2.name} - {result2.description}")
    
    if result1 > result2:
        print("\n🏆 Игрок 1 побеждает!")
    elif result2 > result1:
        print("\n🏆 Игрок 2 побеждает!")
    else:
        print("\n🤝 Ничья! Сплит банка.")