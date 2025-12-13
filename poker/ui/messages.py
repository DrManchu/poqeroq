"""
Модуль форматирования сообщений покерного бота
"""

from typing import List, Optional, Tuple
from game.poker import PokerGame, GameStatus
from game.player import Player
from game.deck import format_cards, format_community_cards, Card
from game.evaluator import HandEvaluator
from utils.helpers import (
    format_chips, escape_html,
    get_place_emoji, EMOJI, get_display_name, get_mention
)
from config import config


def format_waiting_message(
    game: PokerGame,
    players: List[Player],
    time_remaining: Optional[int] = None,
    creator_username: Optional[str] = None
) -> str:
    """Сообщение ожидания игроков"""

    lines = [
        f"{EMOJI['poker']} <b>ПОКЕРНЫЙ СТОЛ</b>",
        ""
    ]

    # Показываем организатора
    if game.creator_id:
        # Ищем создателя среди игроков
        creator = next((p for p in players if p.user_id == game.creator_id), None)
        if creator:
            creator_name = get_display_name(creator.first_name, creator.username)
            lines.append(f"👑 Организатор: {creator_name}")
            lines.append("")

    lines.extend([
        f"👥 Игроки ({len(players)}/{config.MAX_PLAYERS}):",
        "━━━━━━━━━━━━━━━━━━━━━━"
    ])

    if players:
        for i, player in enumerate(players, 1):
            player_name = get_display_name(player.first_name, player.username)
            lines.append(f"  • {player_name} — {format_chips(player.balance)} 🪙")
    else:
        lines.append("  <i>Пока никого нет...</i>")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    if len(players) < config.MIN_PLAYERS:
        lines.append(f"⏳ Ожидание игроков...")
        lines.append(f"   Минимум {config.MIN_PLAYERS} игрока для начала")
    else:
        lines.append("✅ Можно начинать игру!")

    lines.append("")
    lines.append(f"💰 Блайнды: {game.blinds_small}/{game.blinds_big} 🪙")

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
        is_current_turn = (i == game.current_player_index and game.status not in [GameStatus.SHOWDOWN, GameStatus.FINISHED])

        # Рамка сверху для текущего игрока
        if is_current_turn and player.can_act:
            lines.append("▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️")

        line = format_player_line(
            player=player,
            is_current=is_current_turn,
            is_dealer=(i == game.dealer_index),
            is_sb=(i == _get_sb_index(game, players)),
            is_bb=(i == _get_bb_index(game, players))
        )
        lines.append(line)

        # Таймер под текущим игроком
        if is_current_turn and player.can_act and time_remaining is not None:
            lines.append(f"⏱ Осталось: {time_remaining} сек")

        # Рамка снизу для текущего игрока
        if is_current_turn and player.can_act:
            lines.append("▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️▶️")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    
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
    name = get_display_name(player.first_name, player.username)
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
        player_name = get_display_name(player.first_name, player.username)

        if hand_result:
            lines.append(f"👤 {player_name}: {cards_str}")
            lines.append(f"   └ {hand_result.name}: {hand_result.description}")
        else:
            lines.append(f"👤 {player_name}: {cards_str}")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # Победители
    if len(winners) == 1:
        winner, amount, combo = winners[0]
        winner_name = get_display_name(winner.first_name, winner.username)
        lines.append("")
        lines.append(f"🎉 <b>Победитель:</b> {winner_name}")
        lines.append(f"💰 <b>Выигрыш:</b> {format_chips(amount)} 🪙")
        lines.append(f"🃏 {combo}")
    else:
        lines.append("")
        lines.append(f"🎉 <b>Победители (сплит):</b>")
        for winner, amount, combo in winners:
            winner_name = get_display_name(winner.first_name, winner.username)
            lines.append(f"  • {winner_name}: {format_chips(amount)} 🪙")
    
    lines.append("")
    lines.append("<i>Новая раздача через 10 секунд...</i>")
    
    return "\n".join(lines)


def format_winner_no_showdown(winner: Player, pot: int) -> str:
    """Сообщение о победе без вскрытия"""

    winner_name = get_display_name(winner.first_name, winner.username)

    lines = [
        f"{EMOJI['winner']} <b>ПОБЕДА!</b>",
        "",
        f"Все сбросили карты.",
        "",
        f"🎉 <b>Победитель:</b> {winner_name}",
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


def format_balance_message(username: str, user_id: int, balance: int, games_played: int, games_won: int, first_name: str = None) -> str:
    """Сообщение с балансом игрока"""

    win_rate = (games_won / games_played * 100) if games_played > 0 else 0
    display_name = get_display_name(first_name, username)

    lines = [
        f"💰 <b>Баланс игрока</b>",
        "",
        f"👤 {display_name}",
        "",
        f"🪙 Фишки: <b>{format_chips(balance)}</b>",
        f"🎮 Игр сыграно: {games_played}",
        f"🏆 Побед: {games_won}",
        f"📊 Винрейт: {win_rate:.1f}%"
    ]

    return "\n".join(lines)


def format_stats_message(user: dict) -> str:
    """Сообщение с детальной статистикой игрока"""

    username = user.get('username', 'Unknown')
    first_name = user.get('first_name')
    user_id = user.get('user_id', 0)
    balance = user.get('balance', 0)
    games_played = user.get('games_played', 0)
    games_won = user.get('games_won', 0)
    total_won = user.get('total_won', 0)
    total_lost = user.get('total_lost', 0)
    best_win = user.get('best_win', 0)

    win_rate = (games_won / games_played * 100) if games_played > 0 else 0
    net_profit = total_won - total_lost
    display_name = get_display_name(first_name, username)

    lines = [
        f"📊 <b>Статистика игрока</b>",
        "",
        f"👤 {display_name}",
        "",
        f"💰 <b>Баланс:</b> {format_chips(balance)} 🪙",
        "",
        f"🎮 <b>Игры:</b>",
        f"  • Сыграно: {games_played}",
        f"  • Побед: {games_won}",
        f"  • Винрейт: {win_rate:.1f}%",
        "",
        f"💵 <b>Финансы:</b>",
        f"  • Выиграно: +{format_chips(total_won)} 🪙",
        f"  • Проиграно: -{format_chips(total_lost)} 🪙",
        f"  • Чистая прибыль: {'+' if net_profit >= 0 else ''}{format_chips(net_profit)} 🪙",
        f"  • Лучший выигрыш: {format_chips(best_win)} 🪙"
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
            name = get_display_name(player.get('first_name'), player.get('username'))
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
/table — Показать текущий стол
/closetable — Удалить стол (организатор)
/balance — Посмотреть баланс
/stats — Детальная статистика
/give — Передать фишки игроку
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


def format_table_settings(
    game: PokerGame,
    creator_username: str,
    creator_first_name: str = None
) -> str:
    """Сообщение настроек стола"""

    notifications_status = "ВКЛ" if game.notifications_enabled else "ВЫКЛ"
    auto_refresh_status = "ВКЛ" if game.auto_refresh_enabled else "ВЫКЛ"
    creator_name = get_display_name(creator_first_name, creator_username)

    lines = [
        f"⚙️ <b>НАСТРОЙКИ СТОЛА</b>",
        "",
        f"👑 Организатор: {creator_name}",
        "",
        f"🔔 Уведомления о ходе: <b>{notifications_status}</b>",
        f"💰 Блайнды: <b>{game.blinds_small}/{game.blinds_big}</b>",
        f"🔄 Автообновление: <b>{auto_refresh_status}</b>"
    ]

    return "\n".join(lines)


def format_enhanced_cards(
    player: Player,
    community_cards: List[Card]
) -> str:
    """Расширенная информация о картах для alert"""

    from game.deck import format_card

    # Карты игрока
    hole_str = "  ".join([f"[ {format_card(card)} ]" for card in player.hole_cards])

    lines = [
        "🎴 Твои карты:",
        "",
        hole_str,
        ""
    ]

    # Карты на столе
    if community_cards:
        community_str = "  ".join([f"[ {format_card(card)} ]" for card in community_cards])
        # Добавляем пустые слоты
        empty_slots = 5 - len(community_cards)
        if empty_slots > 0:
            community_str += "  " + "  ".join(["[ — ]"] * empty_slots)

        lines.append(f"📊 На столе: {community_str}")
        lines.append("")

        # Текущая комбинация
        combo = player.get_current_combination(community_cards)
        lines.append(f"👑 Комбинация: {combo}")
    else:
        lines.append("📊 На столе: [ — ]  [ — ]  [ — ]  [ — ]  [ — ]")
        lines.append("")

        # Проверка карманных карт
        if len(player.hole_cards) == 2:
            if player.hole_cards[0].rank == player.hole_cards[1].rank:
                lines.append("👆 Карманная пара!")
            elif player.hole_cards[0].suit == player.hole_cards[1].suit:
                lines.append("🎨 Одномастные карты")

    return "\n".join(lines)


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