"""
Обработчики inline-кнопок покерного бота
"""

import asyncio
import logging
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from database import db
from game.poker import PokerGame, GameStatus
from game.player import Player
from game.deck import cards_from_list
from handlers.commands import active_games, game_timers, save_game, get_or_load_game
from ui.messages import (
    format_game_table, format_showdown_message, format_waiting_message,
    format_player_cards_alert, format_winner_no_showdown
)
from ui.keyboards import (
    get_game_keyboard, get_raise_keyboard, get_showdown_keyboard,
    get_waiting_keyboard, get_spectator_keyboard
)
from config import config
from utils.helpers import parse_callback_data

logger = logging.getLogger(__name__)
router = Router()

# Хранилище таймеров ходов
turn_timers: dict[int, asyncio.Task] = {}


@router.callback_query(F.data.startswith("join:"))
async def cb_join(callback: CallbackQuery) -> None:
    """Присоединение к столу"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    if game.status != GameStatus.WAITING:
        await callback.answer("⚠️ Игра уже началась!", show_alert=True)
        return
    
    if game.get_player(user_id):
        await callback.answer("⚠️ Вы уже за столом!", show_alert=True)
        return
    
    if len(game.players) >= config.MAX_PLAYERS:
        await callback.answer("⚠️ Стол заполнен!", show_alert=True)
        return
    
    # Получаем пользователя
    user = await db.get_or_create_user(user_id, username)
    
    if user['balance'] < config.BLINDS[1]:
        await callback.answer(f"⚠️ Недостаточно фишек! Минимум: {config.BLINDS[1]}", show_alert=True)
        return
    
    # Добавляем игрока
    seat = len(game.players)
    player = Player(
        user_id=user_id,
        username=username,
        seat_position=seat,
        balance=user['balance']
    )
    game.players.append(player)
    await db.add_player_to_game(game_id, user_id, seat)
    
    # Обновляем сообщение
    msg_text = format_waiting_message(game, game.players, config.JOIN_TIMEOUT)
    keyboard = get_waiting_keyboard(game_id, len(game.players))
    
    await callback.message.edit_text(msg_text, reply_markup=keyboard)
    await callback.answer(f"✅ Вы сели за стол! Место #{seat + 1}")


@router.callback_query(F.data.startswith("leave:"))
async def cb_leave(callback: CallbackQuery) -> None:
    """Выход из-за стола"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    player = game.get_player(user_id)
    if not player:
        await callback.answer("⚠️ Вы не за столом!", show_alert=True)
        return
    
    if game.status == GameStatus.WAITING:
        game.players.remove(player)
        await db.remove_player_from_game(game_id, user_id)
        
        if not game.players:
            await db.finish_game(game_id)
            if chat_id in active_games:
                del active_games[chat_id]
            await callback.message.edit_text("⚠️ Стол закрыт — все игроки вышли.")
        else:
            msg_text = format_waiting_message(game, game.players, config.JOIN_TIMEOUT)
            keyboard = get_waiting_keyboard(game_id, len(game.players))
            await callback.message.edit_text(msg_text, reply_markup=keyboard)
        
        await callback.answer("👋 Вы покинули стол")
    else:
        # Автофолд во время игры
        game.remove_player(user_id)
        await save_game(game)
        await callback.answer("👋 Вы покинули стол (автофолд)")
        await update_game_message(callback.bot, game)


@router.callback_query(F.data.startswith("start:"))
async def cb_start(callback: CallbackQuery) -> None:
    """Начало игры"""
    
    action, game_id, params = parse_callback_data(callback.data)
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    if game.status != GameStatus.WAITING:
        await callback.answer("⚠️ Игра уже началась!", show_alert=True)
        return
    
    if len(game.players) < config.MIN_PLAYERS:
        await callback.answer(f"⚠️ Нужно минимум {config.MIN_PLAYERS} игрока!", show_alert=True)
        return
    
    # Отменяем таймер ожидания
    if game_id in game_timers:
        game_timers[game_id].cancel()
        del game_timers[game_id]
    
    await callback.answer("🚀 Игра начинается!")
    await start_game(callback.bot, chat_id, game)


async def start_game(bot: Bot, chat_id: int, game: PokerGame) -> None:
    """Запуск игры"""
    
    logger.info(f"Запуск игры {game.game_id}")
    
    # Начинаем раздачу
    game.start_hand()
    
    # Сохраняем
    await save_game(game)
    
    # Обновляем сообщение
    await update_game_message(bot, game)
    
    # Запускаем таймер хода
    await start_turn_timer(bot, game)


async def update_game_message(bot: Bot, game: PokerGame, time_remaining: int = None) -> None:
    """Обновить сообщение игры"""
    
    if time_remaining is None:
        time_remaining = config.TURN_TIMEOUT
    
    # Формируем сообщение и клавиатуру
    if game.status == GameStatus.SHOWDOWN:
        # Определяем победителей
        winners = game.determine_winners()
        msg_text = format_showdown_message(game, game.players, winners)
        keyboard = get_showdown_keyboard(game.game_id)
        
        # Обновляем статистику
        for winner, amount, _ in winners:
            await db.increment_games_won(winner.user_id)
        for player in game.players:
            await db.increment_games_played(player.user_id)
            await db.set_balance(player.user_id, player.balance)
        
    elif len(game.active_players) <= 1:
        # Победа без вскрытия
        winner = game.active_players[0] if game.active_players else None
        if winner:
            winner.balance += game.pot
            await db.set_balance(winner.user_id, winner.balance)
            await db.increment_games_won(winner.user_id)
            msg_text = format_winner_no_showdown(winner, game.pot)
        else:
            msg_text = "⚠️ Все игроки вышли!"
        
        game.status = GameStatus.FINISHED
        keyboard = get_showdown_keyboard(game.game_id)
        
        for player in game.players:
            await db.increment_games_played(player.user_id)
    else:
        msg_text = format_game_table(game, game.players, time_remaining)
        
        current = game.current_player
        if current and current.can_act:
            can_check = current.current_bet >= game.current_bet
            keyboard = get_game_keyboard(
                game.game_id,
                game.current_bet,
                current.current_bet,
                current.balance,
                can_check
            )
        else:
            keyboard = get_spectator_keyboard(game.game_id)
    
    try:
        await bot.edit_message_text(
            chat_id=game.chat_id,
            message_id=game.message_id,
            text=msg_text,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Ошибка обновления сообщения: {e}")


async def start_turn_timer(bot: Bot, game: PokerGame) -> None:
    """Запуск таймера хода"""
    
    # Отменяем предыдущий таймер
    if game.game_id in turn_timers:
        turn_timers[game.game_id].cancel()
    
    # Запускаем новый
    task = asyncio.create_task(turn_timer_task(bot, game))
    turn_timers[game.game_id] = task


async def turn_timer_task(bot: Bot, game: PokerGame) -> None:
    """Задача таймера хода"""
    
    remaining = config.TURN_TIMEOUT
    update_interval = config.TIMER_UPDATE_INTERVAL
    
    while remaining > 0:
        await asyncio.sleep(min(update_interval, remaining))
        remaining -= update_interval
        
        # Проверяем, та ли ещё игра
        current_game = active_games.get(game.chat_id)
        if not current_game or current_game.game_id != game.game_id:
            return
        
        if current_game.status in [GameStatus.FINISHED, GameStatus.SHOWDOWN, GameStatus.WAITING]:
            return
        
        # Обновляем сообщение
        await update_game_message(bot, current_game, max(0, remaining))
    
    # Таймаут — автофолд
    current_game = active_games.get(game.chat_id)
    if not current_game or current_game.game_id != game.game_id:
        return
    
    if current_game.status in [GameStatus.FINISHED, GameStatus.SHOWDOWN, GameStatus.WAITING]:
        return
    
    current_player = current_game.current_player
    if current_player and current_player.can_act:
        current_game.player_fold(current_player.user_id)
        current_game.last_action_text = f"⏱ @{current_player.username} — автофолд (время вышло)"
        await process_after_action(bot, current_game)


async def process_after_action(bot: Bot, game: PokerGame) -> None:
    """Обработка после действия игрока"""
    
    # Проверяем, остался ли один игрок
    if len(game.active_players) <= 1:
        await update_game_message(bot, game)
        await save_game(game)
        return
    
    # Переход к следующему игроку
    if not game.next_player():
        # Раунд завершён
        if not game.advance_stage():
            # Игра завершена
            await update_game_message(bot, game)
            await save_game(game)
            return
    
    # Продолжаем игру
    await save_game(game)
    await update_game_message(bot, game)
    await start_turn_timer(bot, game)


@router.callback_query(F.data.startswith("cards:"))
async def cb_cards(callback: CallbackQuery) -> None:
    """Показать карты игрока"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    player = game.get_player(user_id)
    if not player:
        await callback.answer("⚠️ Вы не за столом!", show_alert=True)
        return
    
    if not player.hole_cards:
        await callback.answer("⚠️ Карты ещё не розданы!", show_alert=True)
        return
    
    text = format_player_cards_alert(player, game.community_cards)
    await callback.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("fold:"))
async def cb_fold(callback: CallbackQuery) -> None:
    """Фолд"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    # Проверяем, что это ход игрока
    if not game.current_player or game.current_player.user_id != user_id:
        await callback.answer("⚠️ Сейчас не ваш ход!", show_alert=True)
        return
    
    success, msg = game.player_fold(user_id)
    if not success:
        await callback.answer(f"⚠️ {msg}", show_alert=True)
        return
    
    await callback.answer("❌ Вы сбросили карты")
    await process_after_action(callback.bot, game)


@router.callback_query(F.data.startswith("check:"))
async def cb_check(callback: CallbackQuery) -> None:
    """Чек"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    if not game.current_player or game.current_player.user_id != user_id:
        await callback.answer("⚠️ Сейчас не ваш ход!", show_alert=True)
        return
    
    success, msg = game.player_check(user_id)
    if not success:
        await callback.answer(f"⚠️ {msg}", show_alert=True)
        return
    
    await callback.answer("📞 Чек")
    await process_after_action(callback.bot, game)


@router.callback_query(F.data.startswith("call:"))
async def cb_call(callback: CallbackQuery) -> None:
    """Колл"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    if not game.current_player or game.current_player.user_id != user_id:
        await callback.answer("⚠️ Сейчас не ваш ход!", show_alert=True)
        return
    
    success, msg = game.player_call(user_id)
    if not success:
        await callback.answer(f"⚠️ {msg}", show_alert=True)
        return
    
    await callback.answer("✅ Колл")
    await process_after_action(callback.bot, game)


@router.callback_query(F.data.startswith("raise_menu:"))
async def cb_raise_menu(callback: CallbackQuery) -> None:
    """Меню рейза"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    if not game.current_player or game.current_player.user_id != user_id:
        await callback.answer("⚠️ Сейчас не ваш ход!", show_alert=True)
        return
    
    player = game.current_player
    
    keyboard = get_raise_keyboard(
        game_id,
        game.current_bet,
        player.current_bet,
        player.balance,
        game.pot,
        game.big_blind
    )
    
    msg_text = format_game_table(game, game.players, config.TURN_TIMEOUT)
    
    await callback.message.edit_text(msg_text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("raise:"))
async def cb_raise(callback: CallbackQuery) -> None:
    """Рейз на определённую сумму"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    if not params:
        await callback.answer("⚠️ Ошибка параметров", show_alert=True)
        return
    
    amount = int(params[0])
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    if not game.current_player or game.current_player.user_id != user_id:
        await callback.answer("⚠️ Сейчас не ваш ход!", show_alert=True)
        return
    
    success, msg = game.player_raise(user_id, amount)
    if not success:
        await callback.answer(f"⚠️ {msg}", show_alert=True)
        return
    
    await callback.answer(f"⬆️ Рейз до {amount}")
    await process_after_action(callback.bot, game)


@router.callback_query(F.data.startswith("allin:"))
async def cb_allin(callback: CallbackQuery) -> None:
    """Олл-ин"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    if not game.current_player or game.current_player.user_id != user_id:
        await callback.answer("⚠️ Сейчас не ваш ход!", show_alert=True)
        return
    
    success, msg = game.player_all_in(user_id)
    if not success:
        await callback.answer(f"⚠️ {msg}", show_alert=True)
        return
    
    await callback.answer("🔥 Олл-ин!")
    await process_after_action(callback.bot, game)


@router.callback_query(F.data.startswith("back:"))
async def cb_back(callback: CallbackQuery) -> None:
    """Назад к основному меню"""
    
    action, game_id, params = parse_callback_data(callback.data)
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    await update_game_message(callback.bot, game)
    await callback.answer()


@router.callback_query(F.data.startswith("new_hand:"))
async def cb_new_hand(callback: CallbackQuery) -> None:
    """Новая раздача"""
    
    action, game_id, params = parse_callback_data(callback.data)
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    # Проверяем количество игроков с фишками
    players_with_chips = [p for p in game.players if p.balance >= game.big_blind and p.is_active]
    
    if len(players_with_chips) < config.MIN_PLAYERS:
        await callback.answer("⚠️ Недостаточно игроков с фишками!", show_alert=True)
        await callback.message.edit_text(
            "🏁 <b>Игра окончена!</b>\n\n"
            "Недостаточно игроков с фишками для продолжения.\n"
            "Используйте /poker для новой игры."
        )
        await db.finish_game(game_id)
        if chat_id in active_games:
            del active_games[chat_id]
        return
    
    # Удаляем игроков без фишек
    game.players = players_with_chips
    
    # Двигаем дилера
    game.move_dealer()
    
    # Начинаем новую раздачу
    await callback.answer("🔄 Новая раздача!")
    await start_game(callback.bot, chat_id, game)


@router.callback_query(F.data.startswith("close:"))
async def cb_close(callback: CallbackQuery) -> None:
    """Закрыть стол"""
    
    action, game_id, params = parse_callback_data(callback.data)
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    # Закрываем игру
    await db.finish_game(game_id)
    if chat_id in active_games:
        del active_games[chat_id]
    
    # Отменяем таймеры
    if game_id in game_timers:
        game_timers[game_id].cancel()
        del game_timers[game_id]
    if game_id in turn_timers:
        turn_timers[game_id].cancel()
        del turn_timers[game_id]
    
    await callback.message.edit_text("🚪 Стол закрыт.")
    await callback.answer("Стол закрыт")