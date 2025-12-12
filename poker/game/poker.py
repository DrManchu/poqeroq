"""
Основной класс покерной игры
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field

from game.deck import Deck, Card, cards_to_list, cards_from_list, format_community_cards
from game.player import Player
from game.evaluator import HandEvaluator, compare_hands
from config import config

logger = logging.getLogger(__name__)


class GameStatus(Enum):
    """Статусы игры"""
    WAITING = "waiting"
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    FINISHED = "finished"


@dataclass
class SidePot:
    """Боковой банк"""
    amount: int
    eligible_players: List[int]  # user_ids игроков, претендующих на банк


@dataclass 
class PokerGame:
    """Класс покерной игры"""
    
    game_id: int
    chat_id: int
    
    # Состояние игры
    status: GameStatus = GameStatus.WAITING
    message_id: Optional[int] = None
    
    # Колода и общие карты
    deck: Deck = field(default_factory=Deck)
    community_cards: List[Card] = field(default_factory=list)
    
    # Игроки
    players: List[Player] = field(default_factory=list)
    dealer_index: int = 0
    current_player_index: int = 0
    
    # Банк и ставки
    pot: int = 0
    current_bet: int = 0
    last_raiser_index: Optional[int] = None
    min_raise: int = config.BLINDS[1]  # Минимальный рейз = большой блайнд
    
    # Боковые банки для олл-инов
    side_pots: List[SidePot] = field(default_factory=list)
    
    # Последнее действие (для сообщений)
    last_action_text: str = ""
    
    @property
    def small_blind(self) -> int:
        return config.BLINDS[0]
    
    @property
    def big_blind(self) -> int:
        return config.BLINDS[1]
    
    @property
    def active_players(self) -> List[Player]:
        """Игроки, которые ещё в раздаче"""
        return [p for p in self.players if p.is_in_hand]
    
    @property
    def players_can_act(self) -> List[Player]:
        """Игроки, которые могут действовать"""
        return [p for p in self.players if p.can_act]
    
    @property
    def current_player(self) -> Optional[Player]:
        """Текущий игрок"""
        if not self.players:
            return None
        return self.players[self.current_player_index]
    
    @property
    def dealer(self) -> Optional[Player]:
        """Дилер"""
        if not self.players:
            return None
        return self.players[self.dealer_index]
    
    def get_player(self, user_id: int) -> Optional[Player]:
        """Найти игрока по user_id"""
        for player in self.players:
            if player.user_id == user_id:
                return player
        return None
    
    def get_player_index(self, user_id: int) -> int:
        """Получить индекс игрока"""
        for i, player in enumerate(self.players):
            if player.user_id == user_id:
                return i
        return -1
    
    # === УПРАВЛЕНИЕ ИГРОКАМИ ===
    
    def add_player(self, player: Player) -> bool:
        """Добавить игрока"""
        if len(self.players) >= config.MAX_PLAYERS:
            return False
        if self.get_player(player.user_id):
            return False
        self.players.append(player)
        return True
    
    def remove_player(self, user_id: int) -> bool:
        """Удалить игрока"""
        player = self.get_player(user_id)
        if player:
            player.is_active = False
            player.is_folded = True
            return True
        return False
    
    # === НАЧАЛО ИГРЫ ===
    
    def start_hand(self) -> None:
        """Начать новую раздачу"""
        logger.info(f"Игра {self.game_id}: начало раздачи")
        
        # Сброс состояния
        self.pot = 0
        self.current_bet = 0
        self.community_cards = []
        self.side_pots = []
        self.last_raiser_index = None
        self.min_raise = self.big_blind
        
        # Сброс игроков
        for player in self.players:
            player.reset_for_new_hand()
        
        # Создаём и перемешиваем колоду
        self.deck = Deck()
        self.deck.shuffle()
        
        # Раздаём карты
        for player in self.players:
            if player.is_active:
                player.hole_cards = self.deck.deal(2)
        
        # Выставляем блайнды
        self._post_blinds()
        
        # Устанавливаем статус
        self.status = GameStatus.PREFLOP
        
        # Определяем первого игрока (после ББ)
        self._set_first_player_preflop()
    
    def _post_blinds(self) -> None:
        """Выставить блайнды"""
        num_players = len([p for p in self.players if p.is_active])
        
        if num_players < 2:
            return
        
        # Позиции блайндов
        if num_players == 2:
            # Heads-up: дилер = SB
            sb_index = self.dealer_index
            bb_index = (self.dealer_index + 1) % len(self.players)
        else:
            sb_index = (self.dealer_index + 1) % len(self.players)
            bb_index = (self.dealer_index + 2) % len(self.players)
        
        # Пропускаем неактивных
        while not self.players[sb_index].is_active:
            sb_index = (sb_index + 1) % len(self.players)
        while not self.players[bb_index].is_active or bb_index == sb_index:
            bb_index = (bb_index + 1) % len(self.players)
        
        # Ставим блайнды
        sb_player = self.players[sb_index]
        bb_player = self.players[bb_index]
        
        sb_amount = sb_player.place_bet(self.small_blind)
        bb_amount = bb_player.place_bet(self.big_blind)
        
        self.pot = sb_amount + bb_amount
        self.current_bet = self.big_blind
        
        sb_player.last_action = f"мб {sb_amount}"
        bb_player.last_action = f"бб {bb_amount}"
        
        logger.info(f"Блайнды: {sb_player.username} ({sb_amount}), {bb_player.username} ({bb_amount})")
    
    def _set_first_player_preflop(self) -> None:
        """Установить первого игрока на префлопе (UTG)"""
        num_players = len([p for p in self.players if p.is_active])
        
        if num_players == 2:
            # Heads-up: SB/дилер ходит первым
            self.current_player_index = self.dealer_index
        else:
            # UTG = после BB
            self.current_player_index = (self.dealer_index + 3) % len(self.players)
        
        # Находим первого активного игрока
        self._advance_to_next_active()
    
    # === УПРАВЛЕНИЕ ХОДАМИ ===
    
    def _advance_to_next_active(self) -> None:
        """Перейти к следующему активному игроку"""
        start = self.current_player_index
        while True:
            if self.current_player and self.current_player.can_act:
                break
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
            if self.current_player_index == start:
                break
    
    def next_player(self) -> bool:
        """
        Перейти к следующему игроку
        
        Returns:
            True если раунд продолжается, False если раунд окончен
        """
        if self._is_round_complete():
            return False
        
        start = self.current_player_index
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
        
        # Ищем следующего активного игрока
        while self.current_player_index != start:
            player = self.current_player
            if player and player.can_act:
                # Проверяем, не закончился ли круг
                if self.last_raiser_index is not None:
                    if self.current_player_index == self.last_raiser_index:
                        return False
                return True
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
        
        return False
    
    def _is_round_complete(self) -> bool:
        """Проверить, завершён ли раунд торговли"""
        active = self.active_players
        
        # Все сфолдили кроме одного
        if len(active) <= 1:
            return True
        
        # Все в олл-ине или сфолдили
        can_act = [p for p in active if p.can_act]
        if len(can_act) == 0:
            return True
        
        # Проверяем, все ли уравняли ставки
        for player in can_act:
            if player.current_bet < self.current_bet:
                return False
        
        # На префлопе BB имеет право на опцию
        if self.status == GameStatus.PREFLOP:
            bb_index = self._get_bb_index()
            bb_player = self.players[bb_index]
            if bb_player.can_act and bb_player.current_bet == self.big_blind:
                if not bb_player.last_action or bb_player.last_action.startswith("бб"):
                    # BB ещё не действовал (кроме обязательной ставки)
                    if self.current_bet == self.big_blind:
                        return False
        
        return True
    
    def _get_bb_index(self) -> int:
        """Получить индекс большого блайнда"""
        num_players = len([p for p in self.players if p.is_active])
        if num_players == 2:
            return (self.dealer_index + 1) % len(self.players)
        return (self.dealer_index + 2) % len(self.players)
    
    # === ДЕЙСТВИЯ ИГРОКОВ ===
    
    def player_fold(self, user_id: int) -> Tuple[bool, str]:
        """Игрок сбрасывает карты"""
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно сбросить карты"
        
        player.fold()
        self.last_action_text = f"@{player.username} сбрасывает карты ❌"
        
        logger.info(f"Игра {self.game_id}: {player.username} фолд")
        return True, self.last_action_text
    
    def player_check(self, user_id: int) -> Tuple[bool, str]:
        """Игрок делает чек"""
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно сделать чек"
        
        if player.current_bet < self.current_bet:
            return False, "Нельзя чекнуть, нужно уравнять ставку"
        
        player.check()
        self.last_action_text = f"@{player.username} чек 📞"
        
        logger.info(f"Игра {self.game_id}: {player.username} чек")
        return True, self.last_action_text
    
    def player_call(self, user_id: int) -> Tuple[bool, str]:
        """Игрок уравнивает ставку"""
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно уравнять ставку"
        
        amount_to_call = self.current_bet - player.current_bet
        if amount_to_call <= 0:
            return self.player_check(user_id)
        
        actual = player.call(amount_to_call)
        self.pot += actual
        
        if player.is_all_in:
            self.last_action_text = f"@{player.username} идёт олл-ин! 🔥 {player.total_bet} 🪙"
        else:
            self.last_action_text = f"@{player.username} колл {actual} 🪙"
        
        logger.info(f"Игра {self.game_id}: {player.username} колл {actual}")
        return True, self.last_action_text
    
    def player_raise(self, user_id: int, total_amount: int) -> Tuple[bool, str]:
        """Игрок повышает ставку"""
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно повысить ставку"
        
        # Проверяем минимальный рейз
        min_total = self.current_bet + self.min_raise
        if total_amount < min_total and total_amount < player.balance + player.current_bet:
            return False, f"Минимальный рейз: {min_total} 🪙"
        
        # Если ставим больше чем есть - олл-ин
        if total_amount >= player.balance + player.current_bet:
            return self.player_all_in(user_id)
        
        raise_amount = total_amount - self.current_bet
        added = player.raise_bet(total_amount)
        
        self.pot += added
        self.current_bet = player.current_bet
        self.min_raise = raise_amount
        self.last_raiser_index = self.get_player_index(user_id)
        
        self.last_action_text = f"@{player.username} рейз до {self.current_bet} 🪙 ⬆️"
        
        logger.info(f"Игра {self.game_id}: {player.username} рейз до {self.current_bet}")
        return True, self.last_action_text
    
    def player_all_in(self, user_id: int) -> Tuple[bool, str]:
        """Игрок идёт олл-ин"""
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно пойти олл-ин"
        
        all_in_amount = player.balance
        total_bet = player.current_bet + all_in_amount
        
        added = player.all_in()
        self.pot += added
        
        # Обновляем текущую ставку если олл-ин больше
        if player.current_bet > self.current_bet:
            raise_amount = player.current_bet - self.current_bet
            self.current_bet = player.current_bet
            self.min_raise = max(self.min_raise, raise_amount)
            self.last_raiser_index = self.get_player_index(user_id)
        
        self.last_action_text = f"@{player.username} идёт олл-ин! 🔥 {player.total_bet} 🪙"
        
        logger.info(f"Игра {self.game_id}: {player.username} олл-ин {player.total_bet}")
        return True, self.last_action_text
    
    # === ПЕРЕХОДЫ МЕЖДУ РАУНДАМИ ===
    
    def advance_stage(self) -> bool:
        """
        Перейти к следующему этапу игры
        
        Returns:
            True если игра продолжается, False если игра окончена
        """
        # Проверяем, остался ли один игрок
        active = self.active_players
        if len(active) <= 1:
            self.status = GameStatus.SHOWDOWN
            return False
        
        # Сбрасываем ставки раунда
        for player in self.players:
            player.reset_for_new_round()
        
        self.current_bet = 0
        self.last_raiser_index = None
        self.min_raise = self.big_blind
        
        # Переход к следующему этапу
        if self.status == GameStatus.PREFLOP:
            self._deal_flop()
            self.status = GameStatus.FLOP
        elif self.status == GameStatus.FLOP:
            self._deal_turn()
            self.status = GameStatus.TURN
        elif self.status == GameStatus.TURN:
            self._deal_river()
            self.status = GameStatus.RIVER
        elif self.status == GameStatus.RIVER:
            self.status = GameStatus.SHOWDOWN
            return False
        
        # Устанавливаем первого игрока (после дилера)
        self._set_first_player_postflop()
        
        # Проверяем, могут ли игроки действовать
        can_act = [p for p in self.active_players if p.can_act]
        if len(can_act) <= 1:
            # Все в олл-ине, переходим к следующему этапу
            return self.advance_stage()
        
        return True
    
    def _deal_flop(self) -> None:
        """Раздать флоп"""
        self.deck.burn()
        self.community_cards = self.deck.deal(3)
        logger.info(f"Игра {self.game_id}: флоп {self.community_cards}")
    
    def _deal_turn(self) -> None:
        """Раздать тёрн"""
        self.deck.burn()
        self.community_cards.extend(self.deck.deal(1))
        logger.info(f"Игра {self.game_id}: тёрн {self.community_cards[-1]}")
    
    def _deal_river(self) -> None:
        """Раздать ривер"""
        self.deck.burn()
        self.community_cards.extend(self.deck.deal(1))
        logger.info(f"Игра {self.game_id}: ривер {self.community_cards[-1]}")
    
    def _set_first_player_postflop(self) -> None:
        """Установить первого игрока после флопа (первый после дилера)"""
        self.current_player_index = (self.dealer_index + 1) % len(self.players)
        self._advance_to_next_active()
    
    # === ОПРЕДЕЛЕНИЕ ПОБЕДИТЕЛЯ ===
    
    def determine_winners(self) -> List[Tuple[Player, int, str]]:
        """
        Определить победителей и распределить банк
        
        Returns:
            Список кортежей (игрок, выигрыш, комбинация)
        """
        active = self.active_players
        
        # Если остался один игрок
        if len(active) == 1:
            winner = active[0]
            winnings = self.pot
            winner.balance += winnings
            return [(winner, winnings, "Остальные сбросили")]
        
        # Оцениваем руки
        results = []
        for player in active:
            hand_result = player.get_hand_result(self.community_cards)
            if hand_result:
                results.append((player.user_id, hand_result, player))
        
        # Сортируем по силе руки
        results.sort(key=lambda x: x[1], reverse=True)
        
        # Распределяем банк (упрощённо, без side pots)
        # TODO: Добавить полную логику side pots
        
        winners_data = []
        
        # Находим лучшую руку
        if results:
            best_hand = results[0][1]
            winners = [(uid, hr, p) for uid, hr, p in results if hr == best_hand]
            
            # Делим банк между победителями
            share = self.pot // len(winners)
            remainder = self.pot % len(winners)
            
            for i, (uid, hand_result, player) in enumerate(winners):
                win_amount = share + (1 if i < remainder else 0)
                player.balance += win_amount
                winners_data.append((player, win_amount, hand_result.description))
        
        self.status = GameStatus.FINISHED
        return winners_data
    
    def move_dealer(self) -> None:
        """Передвинуть кнопку дилера"""
        self.dealer_index = (self.dealer_index + 1) % len(self.players)
        while not self.players[self.dealer_index].is_active:
            self.dealer_index = (self.dealer_index + 1) % len(self.players)
    
    # === СЕРИАЛИЗАЦИЯ ===
    
    def to_db_data(self) -> Dict[str, Any]:
        """Данные для сохранения в БД"""
        return {
            "status": self.status.value,
            "message_id": self.message_id,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "dealer_index": self.dealer_index,
            "current_player_index": self.current_player_index,
            "community_cards": cards_to_list(self.community_cards),
            "deck": self.deck.to_list()
        }