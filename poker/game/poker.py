"""
Основной класс покерной игры
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict

from game.deck import Deck, Card, cards_to_list, cards_from_list, format_community_cards
from game.player import Player
from game.evaluator import HandEvaluator, compare_hands
from config import config
# Импорт базы данных нужен внутри методов, чтобы избежать циклических ссылок,
# или передавать данные извне. Здесь мы будем предполагать, что sync вызывается извне.

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
    eligible_players: List[int]


@dataclass
class PokerGame:
    """Класс покерной игры"""

    game_id: int
    chat_id: int

    status: GameStatus = GameStatus.WAITING
    message_id: Optional[int] = None

    deck: Deck = field(default_factory=Deck)
    community_cards: List[Card] = field(default_factory=list)

    players: List[Player] = field(default_factory=list)
    dealer_index: int = 0
    current_player_index: int = 0

    pot: int = 0
    current_bet: int = 0
    last_raiser_index: Optional[int] = None
    min_raise: int = config.BLINDS[1]

    pot_contributions: Dict[int, int] = field(default_factory=lambda: defaultdict(int))

    side_pots: List[SidePot] = field(default_factory=list)
    players_acted_this_round: set = field(default_factory=set)
    last_action_text: str = ""

    creator_id: Optional[int] = None
    notifications_enabled: bool = True
    blinds_small: int = 50
    blinds_big: int = 100
    auto_refresh_enabled: bool = True

    pot_distributed: bool = False
    stats_updated: bool = False
    winners_calculated: bool = False

    # Кэш результатов showdown (чтобы не пересчитывать и не модифицировать балансы повторно)
    winners_cache: Optional[List[Tuple['Player', int, str]]] = None

    @property
    def small_blind(self) -> int:
        return self.blinds_small

    @property
    def big_blind(self) -> int:
        return self.blinds_big
    
    @property
    def active_players(self) -> List[Player]:
        return [p for p in self.players if p.is_in_hand]
    
    @property
    def players_can_act(self) -> List[Player]:
        return [p for p in self.players if p.can_act]
    
    @property
    def current_player(self) -> Optional[Player]:
        if not self.players:
            return None
        return self.players[self.current_player_index]
    
    @property
    def dealer(self) -> Optional[Player]:
        if not self.players:
            return None
        return self.players[self.dealer_index]
    
    def get_player(self, user_id: int) -> Optional[Player]:
        for player in self.players:
            if player.user_id == user_id:
                return player
        return None
    
    def get_player_index(self, user_id: int) -> int:
        for i, player in enumerate(self.players):
            if player.user_id == user_id:
                return i
        return -1
    
    def add_player(self, player: Player) -> bool:
        if len(self.players) >= config.MAX_PLAYERS:
            return False
        if self.get_player(player.user_id):
            return False
        self.players.append(player)
        return True
    
    def remove_player(self, user_id: int) -> bool:
        player = self.get_player(user_id)
        if player:
            player.is_active = False
            player.is_folded = True
            return True
        return False
    
    def reset_to_lobby(self) -> None:
        """Сброс игры в состояние лобби (если осталось мало игроков)"""
        self.status = GameStatus.WAITING
        self.pot = 0
        self.current_bet = 0
        self.community_cards = []
        self.deck = Deck() # Новая колода
        self.pot_contributions = defaultdict(int)
        self.pot_distributed = False
        self.stats_updated = False
        self.winners_calculated = False
        self.winners_cache = None
        self.last_action_text = ""
        
        # Сбрасываем флаги игроков
        for p in self.players:
            p.reset_for_new_hand()
            p.is_active = True # В лобби все активны

    def _add_to_pot(self, user_id: int, amount: int) -> None:
        self.pot += amount
        self.pot_contributions[user_id] += amount

    def start_hand(self) -> None:
        logger.info(f"Игра {self.game_id}: начало раздачи")

        self.pot = 0
        self.current_bet = 0
        self.community_cards = []
        self.side_pots = []
        self.last_raiser_index = None
        self.min_raise = self.big_blind
        self.last_action_text = ""
        self.players_acted_this_round = set()
        
        self.pot_contributions = defaultdict(int)
        self.pot_distributed = False
        self.stats_updated = False
        self.winners_calculated = False
        self.winners_cache = None

        for player in self.players:
            player.reset_for_new_hand()

        self.deck = Deck()
        self.deck.shuffle()

        for player in self.players:
            if player.is_active:
                player.hole_cards = self.deck.deal(2)

        self._post_blinds()
        self.status = GameStatus.PREFLOP
        self._set_first_player_preflop()
    
    def _post_blinds(self) -> None:
        num_players = len([p for p in self.players if p.is_active])
        if num_players < 2: return
        
        if num_players == 2:
            sb_index = self.dealer_index
            bb_index = (self.dealer_index + 1) % len(self.players)
        else:
            sb_index = (self.dealer_index + 1) % len(self.players)
            bb_index = (self.dealer_index + 2) % len(self.players)
        
        while not self.players[sb_index].is_active:
            sb_index = (sb_index + 1) % len(self.players)
        while not self.players[bb_index].is_active or bb_index == sb_index:
            bb_index = (bb_index + 1) % len(self.players)
        
        sb_player = self.players[sb_index]
        bb_player = self.players[bb_index]
        
        sb_amount = sb_player.place_bet(self.small_blind)
        self._add_to_pot(sb_player.user_id, sb_amount)

        bb_amount = bb_player.place_bet(self.big_blind)
        self._add_to_pot(bb_player.user_id, bb_amount)
        
        self.current_bet = self.big_blind
        sb_player.last_action = f"мб {sb_amount}"
        bb_player.last_action = f"бб {bb_amount}"
        
        logger.info(f"Блайнды: {sb_player.username} ({sb_amount}), {bb_player.username} ({bb_amount})")
    
    def _set_first_player_preflop(self) -> None:
        num_players = len([p for p in self.players if p.is_active])
        if num_players == 2:
            self.current_player_index = self.dealer_index
        else:
            self.current_player_index = (self.dealer_index + 3) % len(self.players)
        self._advance_to_next_active()
    
    def _advance_to_next_active(self) -> None:
        start = self.current_player_index
        while True:
            if self.current_player and self.current_player.can_act:
                break
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
            if self.current_player_index == start:
                break
    
    def next_player(self) -> bool:
        if self._is_round_complete():
            return False
        
        start = self.current_player_index
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
        
        while self.current_player_index != start:
            player = self.current_player
            if player and player.can_act:
                if self.last_raiser_index is not None:
                    if self.current_player_index == self.last_raiser_index:
                        return False
                return True
            self.current_player_index = (self.current_player_index + 1) % len(self.players)
        return False
    
    def _is_round_complete(self) -> bool:
        active = self.active_players
        if len(active) <= 1: return True

        can_act = [p for p in active if p.can_act]
        if len(can_act) == 0: return True

        for player in can_act:
            if player.current_bet < self.current_bet:
                return False

        for player in can_act:
            if player.user_id not in self.players_acted_this_round:
                return False

        if self.status == GameStatus.PREFLOP:
            bb_index = self._get_bb_index()
            bb_player = self.players[bb_index]
            if bb_player.can_act and bb_player.current_bet == self.big_blind:
                if not bb_player.last_action or bb_player.last_action.startswith("бб"):
                    if self.current_bet == self.big_blind:
                        return False
        return True
    
    def _get_bb_index(self) -> int:
        num_players = len([p for p in self.players if p.is_active])
        if num_players == 2:
            return (self.dealer_index + 1) % len(self.players)
        return (self.dealer_index + 2) % len(self.players)
    
    def player_fold(self, user_id: int) -> Tuple[bool, str]:
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно сбросить карты"
        player.fold()
        self.players_acted_this_round.add(user_id)
        self.last_action_text = f"@{player.username} сбрасывает карты ❌"
        return True, self.last_action_text
    
    def player_check(self, user_id: int) -> Tuple[bool, str]:
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно сделать чек"
        if player.current_bet < self.current_bet:
            return False, "Нельзя чекнуть, нужно уравнять ставку"
        player.check()
        self.players_acted_this_round.add(user_id)
        self.last_action_text = f"@{player.username} чек 📞"
        return True, self.last_action_text
    
    def player_call(self, user_id: int) -> Tuple[bool, str]:
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно уравнять ставку"
        amount_to_call = self.current_bet - player.current_bet
        if amount_to_call <= 0:
            return self.player_check(user_id)
        actual = player.call(amount_to_call)
        self._add_to_pot(user_id, actual)
        self.players_acted_this_round.add(user_id)
        if player.is_all_in:
            self.last_action_text = f"@{player.username} идёт олл-ин! 🔥 {player.total_bet} 🪙"
        else:
            self.last_action_text = f"@{player.username} колл {actual} 🪙"
        return True, self.last_action_text
    
    def player_raise(self, user_id: int, total_amount: int) -> Tuple[bool, str]:
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно повысить ставку"
        min_total = self.current_bet + self.min_raise
        if total_amount < min_total and total_amount < player.balance + player.current_bet:
            return False, f"Минимальный рейз: {min_total} 🪙"
        if total_amount >= player.balance + player.current_bet:
            return self.player_all_in(user_id)
        raise_amount = total_amount - self.current_bet
        added = player.raise_bet(total_amount)
        self._add_to_pot(user_id, added)
        self.current_bet = player.current_bet
        self.min_raise = raise_amount
        self.last_raiser_index = self.get_player_index(user_id)
        self.players_acted_this_round = {user_id}
        self.last_action_text = f"@{player.username} рейз до {self.current_bet} 🪙 ⬆️"
        return True, self.last_action_text
    
    def player_all_in(self, user_id: int) -> Tuple[bool, str]:
        player = self.get_player(user_id)
        if not player or not player.can_act:
            return False, "Невозможно пойти олл-ин"
        added = player.all_in()
        self._add_to_pot(user_id, added)
        if player.current_bet > self.current_bet:
            raise_amount = player.current_bet - self.current_bet
            self.current_bet = player.current_bet
            self.min_raise = max(self.min_raise, raise_amount)
            self.last_raiser_index = self.get_player_index(user_id)
            self.players_acted_this_round = {user_id}
        else:
            self.players_acted_this_round.add(user_id)
        self.last_action_text = f"@{player.username} идёт олл-ин! 🔥 {player.total_bet} 🪙"
        return True, self.last_action_text
    
    def advance_stage(self) -> bool:
        active = self.active_players
        if len(active) <= 1:
            self.status = GameStatus.SHOWDOWN
            return False
        
        for player in self.players:
            player.reset_for_new_round()

        self.current_bet = 0
        self.last_raiser_index = None
        self.min_raise = self.big_blind
        self.players_acted_this_round = set()
        
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
        
        self._set_first_player_postflop()
        
        can_act = [p for p in self.active_players if p.can_act]
        if len(can_act) <= 1:
            return self.advance_stage()
        
        return True
    
    def _deal_flop(self) -> None:
        self.deck.burn()
        self.community_cards = self.deck.deal(3)
    
    def _deal_turn(self) -> None:
        self.deck.burn()
        self.community_cards.extend(self.deck.deal(1))
    
    def _deal_river(self) -> None:
        self.deck.burn()
        self.community_cards.extend(self.deck.deal(1))
    
    def _set_first_player_postflop(self) -> None:
        self.current_player_index = (self.dealer_index + 1) % len(self.players)
        self._advance_to_next_active()
    
    def determine_winners(self) -> List[Tuple[Player, int, str]]:
        """
        КРИТИЧЕСКИ ВАЖНО: Эта функция ТОЛЬКО ВЫЧИСЛЯЕТ победителей и суммы.
        Она НЕ МОДИФИЦИРУЕТ балансы игроков и статус игры!
        Фактическое начисление денег происходит в handlers/callbacks.py в защищённом блоке.
        """
        # Используем кэш, если уже вычисляли
        if self.winners_cache is not None:
            return self.winners_cache

        active = self.active_players

        if len(active) == 1:
            winner = active[0]
            winnings = self.pot
            result = [(winner, winnings, "Остальные сбросили")]
            self.winners_cache = result
            return result

        player_hands = {}
        for player in active:
            hand_result = player.get_hand_result(self.community_cards)
            player_hands[player.user_id] = hand_result

        bets = self.pot_contributions
        unique_bets = sorted(list(set(b for b in bets.values() if b > 0)))

        current_pot_level = 0
        winners_map = defaultdict(int)
        refund_map = defaultdict(int)  # Отдельно отслеживаем возврат "лишних" денег

        logger.info(f"Начало расчета банка. Вклады: {dict(bets)}")

        for bet_amount in unique_bets:
            contribution = bet_amount - current_pot_level
            if contribution <= 0: continue

            side_pot_amount = 0
            contributors = []
            active_contributors = []

            for player in self.players:
                invested = bets[player.user_id]
                player_contrib = 0
                if invested >= bet_amount:
                    player_contrib = contribution
                elif invested > current_pot_level:
                    player_contrib = invested - current_pot_level

                if player_contrib > 0:
                    side_pot_amount += player_contrib
                    contributors.append(player)
                    if player.is_in_hand:
                        active_contributors.append(player)

            if not active_contributors:
                pass
            elif len(active_contributors) == 1:
                # ВОЗВРАТ: только один человек может претендовать на этот side pot
                winner = active_contributors[0]
                refund_map[winner.user_id] += side_pot_amount
                logger.info(f"Refund {side_pot_amount} to {winner.username}")
            else:
                # ВЫИГРЫШ: несколько претендентов соревнуются за side pot
                sorted_contributors = sorted(
                    active_contributors,
                    key=lambda p: player_hands[p.user_id],
                    reverse=True
                )

                best_hand_result = player_hands[sorted_contributors[0].user_id]
                pot_winners = [
                    p for p in sorted_contributors
                    if player_hands[p.user_id] == best_hand_result
                ]

                share = side_pot_amount // len(pot_winners)
                remainder = side_pot_amount % len(pot_winners)

                for i, w in enumerate(pot_winners):
                    win = share + (1 if i < remainder else 0)
                    winners_map[w.user_id] += win

            current_pot_level = bet_amount

        # Формируем результаты БЕЗ модификации балансов
        final_results = []

        # Сначала добавляем РЕАЛЬНЫХ победителей (кто выиграл side pot в конкурентной борьбе)
        for uid, amount in winners_map.items():
            if amount > 0:
                player = self.get_player(uid)
                hand_res = player_hands.get(uid)
                desc = hand_res.description if hand_res else "Победа"
                final_results.append((player, amount, desc))

        # Потом добавляем возвраты (кто получил деньги обратно без конкуренции)
        for uid, amount in refund_map.items():
            if amount > 0:
                player = self.get_player(uid)
                # Если у игрока уже есть выигрыш, добавляем к нему возврат
                existing = next((r for r in final_results if r[0].user_id == uid), None)
                if existing:
                    # Обновляем сумму
                    idx = final_results.index(existing)
                    total = existing[1] + amount
                    final_results[idx] = (existing[0], total, existing[2])
                else:
                    # Новая запись - это чистый возврат
                    final_results.append((player, amount, "Возврат ставки"))

        final_results.sort(key=lambda x: x[1], reverse=True)

        # Сохраняем в кэш
        self.winners_cache = final_results
        return final_results
    
    def move_dealer(self) -> None:
        self.dealer_index = (self.dealer_index + 1) % len(self.players)
        while not self.players[self.dealer_index].is_active:
            self.dealer_index = (self.dealer_index + 1) % len(self.players)
    
    def to_db_data(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "message_id": self.message_id,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "dealer_index": self.dealer_index,
            "current_player_index": self.current_player_index,
            "community_cards": cards_to_list(self.community_cards),
            "deck": self.deck.to_list(),
            "creator_id": self.creator_id,
            "notifications_enabled": self.notifications_enabled,
            "blinds_small": self.blinds_small,
            "blinds_big": self.blinds_big,
            "auto_refresh_enabled": self.auto_refresh_enabled,
            "pot_distributed": self.pot_distributed,
            "stats_updated": self.stats_updated,
            "pot_contributions": dict(self.pot_contributions) 
        }