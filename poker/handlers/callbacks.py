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
from game.deck import format_card, cards_from_list
from handlers.commands import active_games, game_timers, save_game, get_or_load_game
from ui.messages import (
    format_game_table, format_showdown_message, format_waiting_message,
    format_player_cards_alert, format_winner_no_showdown, format_table_settings,
    format_enhanced_cards
)
from ui.keyboards import (
    get_game_keyboard, get_raise_keyboard, get_showdown_keyboard,
    get_waiting_keyboard, get_spectator_keyboard, get_table_settings_keyboard,
    get_blinds_keyboard, get_confirm_delete_keyboard, get_confirm_fold_keyboard
)
from config import config
from utils.helpers import parse_callback_data, get_display_name
from utils.permissions import can_manage_table

logger = logging.getLogger(__name__)
router = Router()

# Хранилище таймеров ходов
turn_timers: dict[int, asyncio.Task] = {}

# Хранилище таймеров закрытия пустых столов
empty_table_timers: dict[int, asyncio.Task] = {}


async def delete_notification_after_delay(bot: Bot, chat_id: int, message_id: int, delay_seconds: int) -> None:
    """Удалить уведомление после задержки"""
    await asyncio.sleep(delay_seconds)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.debug(f"Не удалось удалить уведомление {message_id}: {e}")


async def close_empty_table_after_delay(bot: Bot, game_id: int, chat_id: int, delay_seconds: int) -> None:
    """Закрыть пустой стол после задержки, если никто не вернулся"""
    await asyncio.sleep(delay_seconds)

    # Проверяем, есть ли теперь игроки
    game = await get_or_load_game(chat_id)
    if game and game.game_id == game_id and len(game.players) == 0:
        # Стол всё ещё пуст - закрываем и удаляем все сообщения
        message_ids = await db.get_game_messages(game_id)
        for msg_id in message_ids:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")

        await db.clear_game_messages(game_id)
        await db.finish_game(game_id)
        if chat_id in active_games:
            del active_games[chat_id]

        logger.info(f"Пустой стол {game_id} автоматически закрыт")

    # Удаляем таймер из хранилища
    if game_id in empty_table_timers:
        del empty_table_timers[game_id]


@router.callback_query(F.data.startswith("join:"))
async def cb_join(callback: CallbackQuery) -> None:
    """Присоединение к столу"""
    
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    
    if game.get_player(user_id):
        await callback.answer("⚠️ Вы уже за столом!", show_alert=True)
        return
    
    if len(game.players) >= config.MAX_PLAYERS:
        await callback.answer("⚠️ Стол заполнен!", show_alert=True)
        return
    
    # Получаем пользователя
    user = await db.get_or_create_user(user_id, username, first_name)
    
    if user['balance'] <= 0:
         await callback.answer(f"⚠️ У вас нет фишек!", show_alert=True)
         return

    if user['balance'] < config.BLINDS[1]:
        await callback.answer(f"⚠️ Мало фишек! Минимум: {config.BLINDS[1]}", show_alert=True)
        return
    
    # Добавляем игрока
    seat = len(game.players)
    player = Player(
        user_id=user_id,
        username=username,
        first_name=first_name,
        seat_position=seat,
        balance=user['balance']
    )
    # Если лобби - игрок активен, если игра/результаты - ждет следующей
    player.is_active = (game.status == GameStatus.WAITING)
    
    game.players.append(player)
    await db.add_player_to_game(game_id, user_id, seat)

    if game_id in empty_table_timers:
        empty_table_timers[game_id].cancel()
        del empty_table_timers[game_id]

    # Если мы в лобби - обновляем сообщение
    if game.status == GameStatus.WAITING:
        msg_text = format_waiting_message(game, game.players, None)
        keyboard = get_waiting_keyboard(game_id, len(game.players))
        await callback.message.edit_text(msg_text, reply_markup=keyboard)
    else:
        # Если игра идет или результаты - просто уведомляем
        await callback.answer(f"✅ Вы сели за стол! Игра начнется в следующей раздаче.")


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
    
    # 1. Если игра завершена (Showdown) - просто выходим
    if game.status in [GameStatus.SHOWDOWN, GameStatus.FINISHED]:
        winnings_text = ""
        current_win = getattr(player, 'current_win', 0)
        
        if current_win > 0:
            winnings_text = f". 💰 Вы забрали: {current_win}"
            await db.set_balance(user_id, player.balance)

        game.remove_player(user_id)
        await save_game(game)
        
        # Если остался < 2 игроков, сбрасываем стол в лобби
        if len(game.players) < 2:
            game.reset_to_lobby()
            await save_game(game)
            msg_text = format_waiting_message(game, game.players, None)
            keyboard = get_waiting_keyboard(game_id, len(game.players))
            await callback.message.edit_text(msg_text, reply_markup=keyboard)
        else:
            await update_game_message(callback.bot, game)
            
        await callback.answer(f"👋 Вы покинули стол{winnings_text}")
        return

    # 2. Если Лобби (WAITING)
    if game.status == GameStatus.WAITING:
        game.remove_player(user_id)
        await db.remove_player_from_game(game.game_id, user_id)
        
        if player in game.players:
            game.players.remove(player)

        await save_game(game)
        
        if not game.players:
            if game_id in empty_table_timers:
                empty_table_timers[game_id].cancel()

            from ui.keyboards import InlineKeyboardMarkup, InlineKeyboardButton
            from utils.helpers import create_callback_data

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🪑 Сесть за стол",
                    callback_data=create_callback_data("join", game_id)
                )]
            ])

            await callback.message.edit_text(
                "👥 <b>Все игроки покинули стол</b>\n\n"
                "🕐 Стол автоматически закроется через 10 секунд...",
                reply_markup=keyboard
            )

            task = asyncio.create_task(
                close_empty_table_after_delay(callback.bot, game_id, chat_id, 10)
            )
            empty_table_timers[game_id] = task
        else:
            msg_text = format_waiting_message(game, game.players, None)
            keyboard = get_waiting_keyboard(game_id, len(game.players))
            await callback.message.edit_text(msg_text, reply_markup=keyboard)

        await callback.answer("👋 Вы покинули стол")

    # 3. Активная игра (Фолд при выходе)
    else:
        game.remove_player(user_id)
        await save_game(game)
        
        await callback.answer(f"👋 Вы покинули стол (фолд)")
        await update_game_message(callback.bot, game)


@router.callback_query(F.data.startswith("start:"))
async def cb_start(callback: CallbackQuery) -> None:
    """Начало игры"""

    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    game = await get_or_load_game(chat_id)

    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return

    # Любой игрок за столом может начать
    if not game.get_player(user_id):
         await callback.answer("⚠️ Вы должны сидеть за столом!", show_alert=True)
         return

    if game.status != GameStatus.WAITING:
        await callback.answer("⚠️ Игра уже началась!", show_alert=True)
        return

    if len(game.players) < config.MIN_PLAYERS:
        await callback.answer(f"⚠️ Нужно минимум {config.MIN_PLAYERS} игрока!", show_alert=True)
        return

    # Отменяем таймер ожидания (если был)
    if game_id in game_timers:
        game_timers[game_id].cancel()
        del game_timers[game_id]

    await callback.answer("🚀 Игра начинается!")
    await start_game(callback.bot, chat_id, game)


async def start_game(bot: Bot, chat_id: int, game: PokerGame) -> None:
    """Запуск игры"""

    logger.info(f"Запуск игры {game.game_id}")

    if game.notifications_enabled:
        from utils.helpers import get_mention
        player_mentions = " ".join([get_mention(p.first_name, p.username, p.user_id) for p in game.players])
        notification = f"🎮 <b>Игра начинается!</b>\n\nИгроки: {player_mentions}\n\nУдачи! 🍀"
        try:
            sent_msg = await bot.send_message(chat_id=chat_id, text=notification)
            asyncio.create_task(delete_notification_after_delay(bot, chat_id, sent_msg.message_id, 30))
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о начале игры: {e}")

    for p in game.players:
        p.is_active = True

    game.start_hand()
    await save_game(game)
    await update_game_message(bot, game)
    await start_turn_timer(bot, game)


async def update_game_message(bot: Bot, game: PokerGame, time_remaining: int = None) -> None:
    """Обновить сообщение игры"""
    
    if time_remaining is None:
        time_remaining = config.TURN_TIMEOUT
    
    if game.status == GameStatus.SHOWDOWN:
        winners = game.determine_winners()
        msg_text = format_showdown_message(game, game.players, winners)
        keyboard = get_showdown_keyboard(game.game_id)

        if not game.stats_updated:
            game.stats_updated = True
            logger.info(f"Игра {game.game_id}: обновление статистики после showdown")

            for winner, amount, _ in winners:
                await db.increment_games_won(winner.user_id)
                net_win = amount - winner.total_bet
                if net_win > 0:
                    await db.update_win_stats(winner.user_id, net_win)
                winner.current_win = amount 
                
            for player in game.players:
                await db.increment_games_played(player.user_id)
                if player.total_bet > 0 and not any(w[0].user_id == player.user_id for w in winners):
                    await db.update_loss_stats(player.user_id, player.total_bet)
                await db.set_balance(player.user_id, player.balance)

            await save_game(game)
        
    elif len(game.active_players) <= 1:
        winner = game.active_players[0] if game.active_players else None

        if winner and not game.pot_distributed:
            game.pot_distributed = True
            game.stats_updated = True
            logger.info(f"Игра {game.game_id}: распределение банка без вскрытия")

            uncalled_bet = 0
            if winner.current_bet > 0:
                max_opponent_bet = max(
                    (p.current_bet for p in game.players if p.is_folded),
                    default=0
                )
                if winner.current_bet > max_opponent_bet:
                    uncalled_bet = winner.current_bet - max_opponent_bet
                    winner.balance += uncalled_bet
                    game.pot -= uncalled_bet

            winner_pot = game.pot
            winner.balance += winner_pot
            winner.current_win = winner_pot

            await db.set_balance(winner.user_id, winner.balance)
            await db.increment_games_won(winner.user_id)
            
            net_win = winner_pot - winner.total_bet
            if net_win > 0:
                await db.update_win_stats(winner.user_id, net_win)

            for player in game.players:
                await db.increment_games_played(player.user_id)
                if player.user_id != winner.user_id and player.total_bet > 0:
                    await db.update_loss_stats(player.user_id, player.total_bet)

            await save_game(game)

            msg_text = format_winner_no_showdown(winner, winner_pot)
        elif winner:
            winner_pot = 0 
            msg_text = format_winner_no_showdown(winner, winner_pot)
        else:
            msg_text = "⚠️ Все игроки вышли!"

        game.status = GameStatus.FINISHED
        keyboard = get_showdown_keyboard(game.game_id)
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
    if game.game_id in turn_timers:
        turn_timers[game.game_id].cancel()

    task = asyncio.create_task(turn_timer_task(bot, game))
    turn_timers[game.game_id] = task


async def turn_timer_task(bot: Bot, game: PokerGame) -> None:
    """Задача таймера хода"""
    remaining = config.TURN_TIMEOUT
    update_interval = config.TIMER_UPDATE_INTERVAL
    
    while remaining > 0:
        await asyncio.sleep(min(update_interval, remaining))
        remaining -= update_interval
        
        current_game = active_games.get(game.chat_id)
        if not current_game or current_game.game_id != game.game_id:
            return
        
        if current_game.status in [GameStatus.FINISHED, GameStatus.SHOWDOWN, GameStatus.WAITING]:
            return
        
        await update_game_message(bot, current_game, max(0, remaining))
    
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
    if len(game.active_players) <= 1:
        await update_game_message(bot, game)
        await save_game(game)
        return
    
    if not game.next_player():
        if not game.advance_stage():
            await update_game_message(bot, game)
            await save_game(game)
            return
    
    await save_game(game)
    await update_game_message(bot, game)
    await start_turn_timer(bot, game)


@router.callback_query(F.data.startswith("cards:"))
async def cb_cards(callback: CallbackQuery) -> None:
    """Показать карты игрока"""
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    try:
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

        text = format_enhanced_cards(player, game.community_cards)
        await callback.answer(text, show_alert=True)
    except Exception as e:
        logger.exception(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ ПОКАЗЕ КАРТ: {e}")
        await callback.answer("⚠️ Ошибка показа карт (см. логи)", show_alert=True)


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
    if game.status in [GameStatus.SHOWDOWN, GameStatus.FINISHED, GameStatus.WAITING]:
        await callback.answer("⚠️ Раздача завершена!", show_alert=True)
        return
    if not game.current_player or game.current_player.user_id != user_id:
        await callback.answer("⚠️ Сейчас не ваш ход!", show_alert=True)
        return

    player = game.current_player
    initial_stack = player.balance + player.current_bet
    bet_percentage = (player.current_bet / initial_stack * 100) if initial_stack > 0 else 0

    if bet_percentage > 20:
        from utils.helpers import format_chips
        msg_text = (
            f"⚠️ <b>Подтверждение фолда</b>\n\n"
            f"Вы уже вложили {format_chips(player.current_bet)} "
            f"({bet_percentage:.1f}% стека) в эту раздачу.\n\n"
            f"Вы уверены, что хотите сбросить карты?"
        )
        keyboard = get_confirm_fold_keyboard(game_id)
        await callback.message.edit_text(msg_text, reply_markup=keyboard)
        await callback.answer()
        return

    success, msg = game.player_fold(user_id)
    if not success:
        await callback.answer(f"⚠️ {msg}", show_alert=True)
        return

    await callback.answer("❌ Вы сбросили карты")
    await process_after_action(callback.bot, game)


@router.callback_query(F.data.startswith("confirm_fold:"))
async def cb_confirm_fold(callback: CallbackQuery) -> None:
    """Подтверждение фолда"""
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
    if game.status in [GameStatus.SHOWDOWN, GameStatus.FINISHED, GameStatus.WAITING]:
        await callback.answer("⚠️ Раздача завершена!", show_alert=True)
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
    if game.status in [GameStatus.SHOWDOWN, GameStatus.FINISHED, GameStatus.WAITING]:
        await callback.answer("⚠️ Раздача завершена!", show_alert=True)
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
    if game.status in [GameStatus.SHOWDOWN, GameStatus.FINISHED, GameStatus.WAITING]:
        await callback.answer("⚠️ Раздача завершена!", show_alert=True)
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
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    game = await get_or_load_game(chat_id)

    if not game:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return
    if game.current_player and game.current_player.user_id != user_id:
        await callback.answer("⏳ Сейчас ход другого игрока")
        return

    await update_game_message(callback.bot, game)
    await callback.answer()


@router.callback_query(F.data.startswith("new_hand:"))
async def cb_new_hand(callback: CallbackQuery) -> None:
    """Новая раздача"""
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    game = await get_or_load_game(chat_id)

    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return

    # Любой игрок может начать
    if not game.get_player(user_id):
        await callback.answer("⚠️ Новую раздачу могут начать только игроки за столом!", show_alert=True)
        return

    players_with_chips = [p for p in game.players if p.balance >= config.BLINDS[1]]

    if not players_with_chips:
        await callback.answer("⚠️ Ни у кого нет фишек!", show_alert=True)
        return

    game.players = players_with_chips

    if len(game.players) < config.MIN_PLAYERS:
         game.status = GameStatus.WAITING
         game.pot = 0
         game.community_cards = []
         await save_game(game)
         
         msg_text = format_waiting_message(game, game.players, None)
         keyboard = get_waiting_keyboard(game_id, len(game.players))
         
         await db.clear_game_messages(game_id)
         
         await callback.message.edit_text(msg_text, reply_markup=keyboard)
         await callback.answer("🔄 Ожидание игроков...")
         return

    game.move_dealer()

    if game.auto_refresh_enabled:
        message_ids = await db.get_game_messages(game_id)
        for msg_id in message_ids:
            try:
                await callback.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")

        await db.clear_game_messages(game_id)
        await callback.answer("🔄 Новая раздача!")
        temp_msg = await callback.bot.send_message(chat_id=chat_id, text="⏳ Начинается новая раздача...")
        game.message_id = temp_msg.message_id
        await db.add_game_message(game_id, chat_id, temp_msg.message_id)
        await start_game(callback.bot, chat_id, game)
    else:
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
    
    message_ids = await db.get_game_messages(game_id)
    for msg_id in message_ids:
        try:
            await callback.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")

    await db.clear_game_messages(game_id)
    await db.finish_game(game_id)
    if chat_id in active_games:
        del active_games[chat_id]

    if game_id in game_timers:
        game_timers[game_id].cancel()
        del game_timers[game_id]
    if game_id in turn_timers:
        turn_timers[game_id].cancel()
        del turn_timers[game_id]

    await callback.bot.send_message(chat_id, "🚪 Стол закрыт.")
    await callback.answer("✅ Стол закрыт")


@router.callback_query(F.data.startswith("refresh:"))
async def cb_refresh(callback: CallbackQuery) -> None:
    """Обновить отображение стола"""
    action, game_id, params = parse_callback_data(callback.data)
    chat_id = callback.message.chat.id
    
    game = await get_or_load_game(chat_id)
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return

    if game.status in [GameStatus.WAITING, GameStatus.SHOWDOWN, GameStatus.FINISHED]:
        for player in game.players:
            user_data = await db.get_user(player.user_id)
            if user_data:
                player.balance = user_data['balance']
    
    from ui.keyboards import get_game_keyboard, get_spectator_keyboard, get_showdown_keyboard
    from ui.messages import format_game_table
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from utils.helpers import create_callback_data

    if game.status == GameStatus.WAITING:
        msg_text = format_waiting_message(game, game.players, None)
        keyboard = get_waiting_keyboard(game_id, len(game.players))
    elif game.status == GameStatus.SHOWDOWN:
        winners = game.determine_winners()
        msg_text = format_showdown_message(game, game.players, winners)
        keyboard = get_showdown_keyboard(game.game_id)
    else:
        msg_text = format_game_table(game, game.players, None)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=create_callback_data("refresh", game.game_id))]
        ])

    message_ids = await db.get_game_messages(game_id)
    for msg_id in message_ids:
        try:
            await callback.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")
    await db.clear_game_messages(game_id)

    try:
        new_message = await callback.bot.send_message(chat_id=chat_id, text=msg_text, reply_markup=keyboard)
        game.message_id = new_message.message_id
        await save_game(game)
        await db.add_game_message(game_id, chat_id, new_message.message_id)
        await callback.answer("🔄 Обновлено!")
    except Exception as e:
        logger.error(f"Ошибка при отправке: {e}")
        await callback.answer("⚠️ Ошибка обновления", show_alert=True)


@router.callback_query(F.data.startswith("toggle_notifications:"))
async def cb_toggle_notifications(callback: CallbackQuery) -> None:
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    chat_id = callback.message.chat.id

    game = await get_or_load_game(chat_id)
    if not game or game.game_id != game_id:
        await callback.answer("⚠️ Игра не найдена!", show_alert=True)
        return

    if not can_manage_table(user_id, username, game.creator_id):
        await callback.answer("⚠️ Только организатор может изменить настройки!", show_alert=True)
        return

    game.notifications_enabled = not game.notifications_enabled
    await save_game(game)

    msg_text = format_table_settings(game, username, first_name)
    keyboard = get_table_settings_keyboard(game_id)
    await callback.message.edit_text(msg_text, reply_markup=keyboard)
    await callback.answer(f"🔔 Уведомления {'включены' if game.notifications_enabled else 'выключены'}")


@router.callback_query(F.data.startswith("select_blinds:"))
async def cb_select_blinds(callback: CallbackQuery) -> None:
    action, game_id, params = parse_callback_data(callback.data)
    chat_id = callback.message.chat.id
    game = await get_or_load_game(chat_id)
    if not game: return
    
    msg_text = (f"💰 <b>Выбор блайндов</b>\n\nТекущие: {game.blinds_small}/{game.blinds_big}\n\nВыберите размер:")
    keyboard = get_blinds_keyboard(game_id)
    await callback.message.edit_text(msg_text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("set_blinds:"))
async def cb_set_blinds(callback: CallbackQuery) -> None:
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    chat_id = callback.message.chat.id

    if not params: return
    try: small, big = map(int, params[0].split('-'))
    except: return

    game = await get_or_load_game(chat_id)
    if not game: return

    if not can_manage_table(user_id, username, game.creator_id):
        await callback.answer("⚠️ Только организатор может изменить настройки!", show_alert=True)
        return

    game.blinds_small = small
    game.blinds_big = big
    await save_game(game)

    msg_text = format_table_settings(game, username, first_name)
    keyboard = get_table_settings_keyboard(game_id)
    await callback.message.edit_text(msg_text, reply_markup=keyboard)
    await callback.answer(f"💰 Блайнды установлены: {small}/{big}")


@router.callback_query(F.data.startswith("toggle_auto_refresh:"))
async def cb_toggle_auto_refresh(callback: CallbackQuery) -> None:
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    chat_id = callback.message.chat.id

    game = await get_or_load_game(chat_id)
    if not game: return

    if not can_manage_table(user_id, username, game.creator_id):
        await callback.answer("⚠️ Только организатор может изменить настройки!", show_alert=True)
        return

    game.auto_refresh_enabled = not game.auto_refresh_enabled
    await save_game(game)

    msg_text = format_table_settings(game, username, first_name)
    keyboard = get_table_settings_keyboard(game_id)
    await callback.message.edit_text(msg_text, reply_markup=keyboard)
    await callback.answer(f"🔄 Авто-обновление {'включено' if game.auto_refresh_enabled else 'выключено'}")


@router.callback_query(F.data.startswith("back_to_settings:"))
async def cb_back_to_settings(callback: CallbackQuery) -> None:
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    chat_id = callback.message.chat.id

    game = await get_or_load_game(chat_id)
    if not game: return

    msg_text = format_table_settings(game, username, first_name)
    keyboard = get_table_settings_keyboard(game_id)
    await callback.message.edit_text(msg_text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("open_table:"))
async def cb_open_table(callback: CallbackQuery) -> None:
    """Открытие стола - добавление создателя и переход к ожиданию игроков"""
    action, game_id, params = parse_callback_data(callback.data)
    user_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    chat_id = callback.message.chat.id

    game = await get_or_load_game(chat_id)
    if not game: return

    if not can_manage_table(user_id, username, game.creator_id):
        await callback.answer("⚠️ Только организатор может открыть стол!", show_alert=True)
        return

    user = await db.get_or_create_user(user_id, username, first_name)
    if user['balance'] < game.big_blind:
        await callback.answer(f"⚠️ Недостаточно фишек! Минимум: {game.big_blind}", show_alert=True)
        return

    if not game.get_player(user_id):
        seat = len(game.players)
        # ИСПРАВЛЕНИЕ: Использование именованных аргументов для предотвращения ошибки
        player = Player(
            user_id=user_id,
            username=username,
            first_name=first_name,
            seat_position=seat,
            balance=user['balance']
        )
        game.players.append(player)
        await db.add_player_to_game(game_id, user_id, seat)

    await save_game(game)
    msg_text = format_waiting_message(game, game.players, None)
    keyboard = get_waiting_keyboard(game_id, len(game.players))
    await callback.message.edit_text(msg_text, reply_markup=keyboard)
    await callback.answer("✅ Стол открыт! Ожидание игроков...")


@router.callback_query(F.data.startswith("delete_table:"))
async def cb_delete_table(callback: CallbackQuery) -> None:
    action, game_id, params = parse_callback_data(callback.data)
    game = await get_or_load_game(callback.message.chat.id)
    if not game: return

    if not can_manage_table(callback.from_user.id, callback.from_user.username, game.creator_id):
        await callback.answer("⚠️ Только организатор может удалить стол!", show_alert=True)
        return

    msg_text = ("⚠️ <b>Удаление стола</b>\n\nВы уверены, что хотите удалить стол?\nВсе игроки будут исключены.")
    keyboard = get_confirm_delete_keyboard(game_id)
    await callback.message.edit_text(msg_text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_confirm_delete(callback: CallbackQuery) -> None:
    action, game_id, params = parse_callback_data(callback.data)
    chat_id = callback.message.chat.id
    
    # Сначала очистка
    message_ids = await db.get_game_messages(game_id)
    for msg_id in message_ids:
        # Пропускаем текущее сообщение, чтобы его отредактировать
        if msg_id == callback.message.message_id: continue
        try: await callback.bot.delete_message(chat_id, msg_id)
        except: pass

    await db.clear_game_messages(game_id)
    await db.finish_game(game_id)
    if chat_id in active_games: del active_games[chat_id]
    if game_id in game_timers: game_timers[game_id].cancel()
    if game_id in turn_timers: turn_timers[game_id].cancel()
    
    # Редактируем сообщение и ставим таймер удаления
    await callback.message.edit_text("🗑 Стол удален.")
    asyncio.create_task(delete_notification_after_delay(callback.bot, chat_id, callback.message.message_id, 30))
    await callback.answer("✅ Стол удален")


@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(callback: CallbackQuery) -> None:
    action, game_id, params = parse_callback_data(callback.data)
    chat_id = callback.message.chat.id
    
    # Редактируем сообщение на "Отменено" и удаляем через 30 сек
    await callback.message.edit_text("❌ Отменено")
    asyncio.create_task(delete_notification_after_delay(callback.bot, chat_id, callback.message.message_id, 30))
    await callback.answer("❌ Отменено")