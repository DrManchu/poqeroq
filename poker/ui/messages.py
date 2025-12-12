"""
Модуль форматирования сообщений покерного бота
"""

from typing import List, Optional, Tuple
from game.poker import PokerGame, GameStatus
from game.player import Player
from game.deck import format_cards, format_community_cards, Card
from game.evaluator import HandEvaluator
from utils.helpers import (
    format_chips, format_username, escape_html, 
    get_place_emoji, EMOJI
)
from config import config


def format_waiting_message(
    game: PokerGame,
    players: List[Player],
    time_remaining: int
) -> str:
    """Сообщение ожидания игроков"""
    
    lines = [
        f"{EMOJI['poker']} <b>ТЕХАССКИЙ ХОЛДЕМ</b>",
        "",
        f"⏳ Ожидание игроков... ({time_remaining} сек)",
        "",
        f"👥 Игроки ({len(players)}/{config.MAX_PLAYERS}):",
        "━━━━━━━━━━━━━━━━━━━━━━"
    ]
    
    if players:
        for i, player in enumerate(players, 1):
            lines.append(f"  {i}. {format_username(player.username, player.user_id)} — {format_chips(player.balance)} 🪙")
    else:
        lines.append("  <i>Пока никого нет...</i>")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    if len(players) < config.MIN_PLAYERS:
        lines.append(f"⚠️ Минимум {config.MIN_PLAYERS} игрока для начала")
    else:
        lines.append("✅ Можно начинать игру!")
    
    lines.append("")
    lines.append(f"💰 Блайнды: {config.BLINDS[0]}/{config.BLINDS[1]} 🪙")
    
    return "\n".join(lines)


def format_game_table(
    game: PokerGame,
    players: List[Player],
    time_remaining: Optional[int] = None
) -> str:
    """Форматирование игрового стола"""
    
    status_names = {
        GameStatus.PREFLOP: "ПРЕФЛОП",
        GameStatus.FLOP: "ФЛОП",
        GameStatus.TURN: "ТЁРН",
        GameStatus.RIVER: "РИВЕР",
        GameStatus.SHOWDOWN: "ВСКРЫТИЕ"
    }
    
    stage_name = status_names.get(game.status, "")
    
    lines = [
        f"{EMOJI['poker']} <b>ТЕХАССКИЙ ХОЛДЕМ</b> — {stage_name}",
        "",
        f"💰 Банк: <b>{format_chips(game.pot)}</b> 🪙"
    ]
    
    if game.current_bet > 0:
        lines.append(f"📍 Ставка: <b>{format_chips(game.current_bet)}</b> 🪙")
    
    lines.append("")
    
    # Общие карты
    lines.append(f"🎴 Стол: {format_community_cards(game.community_cards)}")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    
    # Игроки
    for i, player in enumerate(players):
        line = format_player_line(
            player=player,
            is_current=(i == game.current_player_index and game.status not in [GameStatus.SHOWDOWN, GameStatus.FINISHED]),
            is_dealer=(i == game.dealer_index),
            is_sb=(i == _get_sb_index(game, players)),
            is_bb=(i == _get_bb_index(game, players))
        )
        lines.append(line)
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    
    # Таймер и текущий игрок
    if time_remaining is not None and game.status not in [GameStatus.SHOWDOWN, GameStatus.FINISHED, GameStatus.WAITING]:
        lines.append("")
        lines.append(f"⏱ Осталось: {time_remaining} сек")
    
    # Сообщение о ходе
    if game.status not in [GameStatus.SHOWDOWN, GameStatus.FINISHED, GameStatus.WAITING]:
        current = game.current_player
        if current and current.can_act:
            lines.append("")
            lines.append(f"👉 {format_username(current.username, current.user_id)}, твой ход!")
    
    # Последнее действие
    if game.last_action_text:
        lines.append("")
        lines.append(f"📢 {game.last_action_text}")
    
    return "\n".join(lines)


def format_player_line(
    player: Player,
    is_current: bool = False,
    is_dealer: bool = False,
    is_sb: bool = False,
    is_bb: bool = False
) -> str:
    """Форматирование строки игрока"""
    
    # Статус эмодзи
    if player.is_folded:
        status = "❌"
    elif player.is_all_in:
        status = "🔥"
    elif is_current:
        status = "⏳"
    elif player.last_action and not player.last_action.startswith(("мб", "бб")):
        status = "✅"
    else:
        status = "👤"
    
    # Позиция
    position_parts = []
    if is_dealer:
        position_parts.append("Ⓓ")
    if is_sb:
        position_parts.append("мб")
    if is_bb:
        position_parts.append("бб")
    position = " ".join(position_parts)
    
    # Имя и баланс
    name = format_username(player.username, player.user_id)
    balance = format_chips(player.balance)
    
    # Формируем строку
    line = f"{status} {name}"
    if position:
        line += f" {position}"
    line += f" {balance} 🪙"
    
    # Действие или текущая ставка
    if player.is_folded:
        line += " — <i>сброшено</i>"
    elif player.is_all_in:
        line += f" — олл-ин {format_chips(player.total_bet)}"
    elif player.current_bet > 0 and not is_current:
        line += f" — ставка {format_chips(player.current_bet)}"
    elif is_current:
        line += " — <b>думает...</b>"
    
    return line


def format_showdown_message(
    game: PokerGame,
    players: List[Player],
    winners: List[Tuple[Player, int, str]]
) -> str:
    """Сообщение вскрытия"""
    
    lines = [
        f"{EMOJI['winner']} <b>ВСКРЫТИЕ!</b>",
        "",
        f"🎴 Стол: {format_community_cards(game.community_cards)}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "<b>Руки игроков:</b>",
        ""
    ]
    
    # Показываем руки оставшихся игроков
    active_players = [p for p in players if not p.is_folded]
    for player in active_players:
        hand_result = player.get_hand_result(game.community_cards)
        cards_str = format_cards(player.hole_cards)
        
        if hand_result:
            lines.append(f"👤 {format_username(player.username, player.user_id)}: {cards_str}")
            lines.append(f"   └ {hand_result.name}: {hand_result.description}")
        else:
            lines.append(f"👤 {format_username(player.username, player.user_id)}: {cards_str}")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    
    # Победители
    if len(winners) == 1:
        winner, amount, combo = winners[0]
        lines.append("")
        lines.append(f"🎉 <b>Победитель:</b> {format_username(winner.username, winner.user_id)}")
        lines.append(f"💰 <b>Выигрыш:</b> {format_chips(amount)} 🪙")
        lines.append(f"🃏 {combo}")
    else:
        lines.append("")
        lines.append(f"🎉 <b>Победители (сплит):</b>")
        for winner, amount, combo in winners:
            lines.append(f"  • {format_username(winner.username, winner.user_id)}: {format_chips(amount)} 🪙")
    
    lines.append("")
    lines.append("<i>Новая раздача через 10 секунд...</i>")
    
    return "\n".join(lines)


def format_winner_no_showdown(winner: Player, pot: int) -> str:
    """Сообщение о победе без вскрытия"""
    
    lines = [
        f"{EMOJI['winner']} <b>ПОБЕДА!</b>",
        "",
        f"Все сбросили карты.",
        "",
        f"🎉 <b>Победитель:</b> {format_username(winner.username, winner.user_id)}",
        f"💰 <b>Выигрыш:</b> {format_chips(pot)} 🪙",
        "",
        "<i>Новая раздача через 10 секунд...</i>"
    ]
    
    return "\n".join(lines)


def format_player_cards_alert(
    player: Player,
    community_cards: List[Card]
) -> str:
    """Сообщение с картами игрока (для alert)"""
    
    cards_str = format_cards(player.hole_cards)
    
    lines = [
        "🎴 Твои карты:",
        "",
        f"  {cards_str}",
        ""
    ]
    
    # Текущая комбинация
    if community_cards:
        combo = player.get_current_combination(community_cards)
        lines.append(f"Комбинация: {combo}")
    else:
        # Только карманные карты
        if player.hole_cards and len(player.hole_cards) == 2:
            if player.hole_cards[0].rank == player.hole_cards[1].rank:
                lines.append(f"👆 Карманная пара!")
            elif player.hole_cards[0].suit == player.hole_cards[1].suit:
                lines.append(f"🎨 Одномастные карты")
    
    return "\n".join(lines)


def format_balance_message(username: str, user_id: int, balance: int, games_played: int, games_won: int) -> str:
    """Сообщение с балансом игрока"""
    
    win_rate = (games_won / games_played * 100) if games_played > 0 else 0
    
    lines = [
        f"💰 <b>Баланс игрока</b>",
        "",
        f"👤 {format_username(username, user_id)}",
        "",
        f"🪙 Фишки: <b>{format_chips(balance)}</b>",
        f"🎮 Игр сыграно: {games_played}",
        f"🏆 Побед: {games_won}",
        f"📊 Винрейт: {win_rate:.1f}%"
    ]
    
    return "\n".join(lines)


def format_top_players(players: List[dict]) -> str:
    """Сообщение с топом игроков"""
    
    lines = [
        f"🏆 <b>ТОП-10 ИГРОКОВ</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━"
    ]
    
    if not players:
        lines.append("<i>Пока нет игроков</i>")
    else:
        for i, player in enumerate(players, 1):
            emoji = get_place_emoji(i)
            name = format_username(player.get('username'), player.get('user_id', 0))
            balance = format_chips(player.get('balance', 0))
            wins = player.get('games_won', 0)
            
            lines.append(f"{emoji} {name}")
            lines.append(f"    💰 {balance} 🪙 | 🏆 {wins} побед")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    
    return "\n".join(lines)


def format_help_message() -> str:
    """Сообщение помощи"""
    
    return f"""
{EMOJI['poker']} <b>ТЕХАССКИЙ ХОЛДЕМ — ПОМОЩЬ</b>

<b>📋 Команды:</b>
/poker — Создать стол
/join — Присоединиться к столу
/leave — Покинуть стол  
/balance — Посмотреть баланс
/top — Топ игроков
/help — Эта справка

<b>🎮 Правила игры:</b>
• Каждому игроку раздаётся 2 карты
• 5 общих карт выкладываются на стол
• Составьте лучшую комбинацию из 5 карт

<b>🃏 Комбинации (от старшей к младшей):</b>
🏆 Роял-флеш — A K Q J 10 одной масти
👑 Стрит-флеш — 5 карт подряд одной масти
🔥 Каре — 4 одинаковых карты
🏠 Фулл-хаус — Тройка + Пара
🎨 Флеш — 5 карт одной масти
📊 Стрит — 5 карт подряд
🎯 Тройка — 3 одинаковых карты
✌️ Две пары — 2 + 2 одинаковых
👆 Пара — 2 одинаковых карты
🃏 Старшая карта — ничего

<b>💰 Ставки:</b>
• Малый блайнд: {config.BLINDS[0]} 🪙
• Большой блайнд: {config.BLINDS[1]} 🪙
• Начальный баланс: {format_chips(config.STARTING_BALANCE)} 🪙

<b>⏱ Таймауты:</b>
• На ход: {config.TURN_TIMEOUT} сек
• На присоединение: {config.JOIN_TIMEOUT} сек

Удачной игры! 🍀
"""


def format_error_message(error: str) -> str:
    """Сообщение об ошибке"""
    return f"⚠️ {error}"


def format_game_cancelled() -> str:
    """Сообщение об отмене игры"""
    return f"""
{EMOJI['warning']} <b>Игра отменена</b>

Недостаточно игроков для продолжения.
Используйте /poker чтобы создать новый стол.
"""


def _get_sb_index(game: PokerGame, players: List[Player]) -> int:
    """Получить индекс малого блайнда"""
    num_active = len([p for p in players if p.is_active])
    if num_active == 2:
        return game.dealer_index
    return (game.dealer_index + 1) % len(players)


def _get_bb_index(game: PokerGame, players: List[Player]) -> int:
    """Получить индекс большого блайнда"""
    num_active = len([p for p in players if p.is_active])
    if num_active == 2:
        return (game.dealer_index + 1) % len(players)
    return (game.dealer_index + 2) % len(players)