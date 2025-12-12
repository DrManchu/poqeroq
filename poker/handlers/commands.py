"""
Обработчики команд покерного бота
"""

import asyncio
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart

from database import db
from game.poker import PokerGame, GameStatus
from game.player import Player
from game.deck import cards_from_list
from ui.messages import (
    format_waiting_message, format_balance_message,
    format_top_players, format_help_message, format_error_message
)
from ui.keyboards import get_waiting_keyboard
from config import config
from utils.helpers import format_username

logger = logging.getLogger(__name__)
router = Router()

# Хранилище активных игр в памяти
active_games: dict[int, PokerGame] = {}

# Хранилище таймеров
game_timers: dict[int, asyncio.Task] = {}


async def get_or_load_game(chat_id: int) -> Optional[PokerGame]:
    """Получить игру из памяти или загрузить из БД"""
    
    # Проверяем память
    if chat_id in active_games:
        return active_games[chat_id]
    
    # Загружаем из БД
    game_data = await db.get_active_game(chat_id)
    if not game_data:
        return None
    
    # Создаём объект игры
    game = PokerGame(
        game_id=game_data['game_id'],
        chat_id=chat_id
    )
    game.status = GameStatus(game_data['status'])
    game.message_id = game_data['message_id']
    game.pot = game_data['pot']
    game.current_bet = game_data['current_bet']
    game.dealer_index = game_data['dealer_index']
    game.current_player_index = game_data['current_player_index']
    game.community_cards = cards_from_list(game_data['community_cards'])
    
    # Загружаем игроков
    players_data = await db.get_game_players(game_data['game_id'])
    for p_data in players_data:
        player = Player.from_db_row(p_data)
        game.players.append(player)
    
    active_games[chat_id] = game
    return game


async def save_game(game: PokerGame) -> None:
    """Сохранить игру в БД"""
    await db.update_game(game.game_id, **game.to_db_data())
    
    # Сохраняем игроков
    for player in game.players:
        await db.update_player(
            game.game_id,
            player.user_id,
            hole_cards=player.hole_cards,
            current_bet=player.current_bet,
            total_bet=player.total_bet,
            is_folded=player.is_folded,
            is_all_in=player.is_all_in,
            is_active=player.is_active
        )
        # Обновляем баланс пользователя
        await db.set_balance(player.user_id, player.balance)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start"""
    
    user = await db.get_or_create_user(
        message.from_user.id,
        message.from_user.username or message.from_user.first_name
    )
    
    await message.answer(
        f"🃏 <b>Добро пожаловать в Техасский Холдем!</b>\n\n"
        f"Ваш баланс: <b>{user['balance']:,}</b> 🪙\n\n"
        f"Используйте /poker в групповом чате, чтобы создать стол.\n"
        f"Команда /help покажет правила игры."
    )


@router.message(Command("poker"))
async def cmd_poker(message: Message) -> None:
    """Создать новый стол"""
    
    # Проверяем, что это групповой чат
    if message.chat.type == "private":
        await message.answer("🃏 Эта команда работает только в групповых чатах!")
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    # Проверяем, есть ли активная игра
    existing_game = await get_or_load_game(chat_id)
    if existing_game and existing_game.status != GameStatus.FINISHED:
        await message.answer("⚠️ В этом чате уже идёт игра!")
        return
    
    # Создаём пользователя если нужно
    user = await db.get_or_create_user(user_id, username)
    
    # Проверяем баланс
    if user['balance'] < config.BLINDS[1]:
        await message.answer(
            f"⚠️ Недостаточно фишек для игры!\n"
            f"Ваш баланс: {user['balance']} 🪙\n"
            f"Минимум: {config.BLINDS[1]} 🪙"
        )
        return
    
    # Создаём игру
    game_id = await db.create_game(chat_id)
    
    game = PokerGame(
        game_id=game_id,
        chat_id=chat_id
    )
    
    # Добавляем создателя
    player = Player(
        user_id=user_id,
        username=username,
        seat_position=0,
        balance=user['balance']
    )
    game.players.append(player)
    await db.add_player_to_game(game_id, user_id, 0)
    
    # Сохраняем в память
    active_games[chat_id] = game
    
    # Отправляем сообщение
    msg_text = format_waiting_message(game, game.players, config.JOIN_TIMEOUT)
    keyboard = get_waiting_keyboard(game_id, len(game.players))
    
    sent_message = await message.answer(msg_text, reply_markup=keyboard)
    
    # Сохраняем ID сообщения
    game.message_id = sent_message.message_id
    await db.update_game(game_id, message_id=sent_message.message_id)
    
    # Запускаем таймер ожидания
    timer_task = asyncio.create_task(
        waiting_timer(message.bot, chat_id, game_id, config.JOIN_TIMEOUT)
    )
    game_timers[game_id] = timer_task
    
    logger.info(f"Создана игра {game_id} в чате {chat_id} пользователем {username}")


async def waiting_timer(bot, chat_id: int, game_id: int, total_seconds: int) -> None:
    """Таймер ожидания игроков"""
    
    remaining = total_seconds
    update_interval = config.TIMER_UPDATE_INTERVAL
    
    while remaining > 0:
        await asyncio.sleep(min(update_interval, remaining))
        remaining -= update_interval
        
        # Обновляем сообщение
        game = active_games.get(chat_id)
        if not game or game.game_id != game_id:
            return
        
        if game.status != GameStatus.WAITING:
            return
        
        try:
            msg_text = format_waiting_message(game, game.players, max(0, remaining))
            keyboard = get_waiting_keyboard(game_id, len(game.players))
            
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=game.message_id,
                text=msg_text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"Ошибка обновления таймера: {e}")
    
    # Время вышло
    game = active_games.get(chat_id)
    if not game or game.game_id != game_id or game.status != GameStatus.WAITING:
        return
    
    if len(game.players) >= config.MIN_PLAYERS:
        # Автозапуск
        from handlers.callbacks import start_game
        await start_game(bot, chat_id, game)
    else:
        # Отмена
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=game.message_id,
            text="⚠️ <b>Игра отменена</b>\n\nНедостаточно игроков. Используйте /poker для новой игры."
        )
        await db.finish_game(game_id)
        if chat_id in active_games:
            del active_games[chat_id]


@router.message(Command("join"))
async def cmd_join(message: Message) -> None:
    """Присоединиться к столу"""
    
    if message.chat.type == "private":
        await message.answer("🃏 Эта команда работает только в групповых чатах!")
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.status == GameStatus.FINISHED:
        await message.answer("⚠️ Нет активной игры. Используйте /poker")
        return
    
    if game.status != GameStatus.WAITING:
        await message.answer("⚠️ Игра уже началась!")
        return
    
    # Проверяем, не за столом ли уже
    if game.get_player(user_id):
        await message.answer("⚠️ Вы уже за столом!")
        return
    
    # Проверяем лимит игроков
    if len(game.players) >= config.MAX_PLAYERS:
        await message.answer("⚠️ Стол заполнен!")
        return
    
    # Получаем данные пользователя
    user = await db.get_or_create_user(user_id, username)
    
    if user['balance'] < config.BLINDS[1]:
        await message.answer(f"⚠️ Недостаточно фишек! Минимум: {config.BLINDS[1]} 🪙")
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
    await db.add_player_to_game(game.game_id, user_id, seat)
    
    # Обновляем сообщение
    try:
        msg_text = format_waiting_message(game, game.players, config.JOIN_TIMEOUT)
        keyboard = get_waiting_keyboard(game.game_id, len(game.players))
        
        await message.bot.edit_message_text(
            chat_id=chat_id,
            message_id=game.message_id,
            text=msg_text,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Ошибка обновления сообщения: {e}")
    
    await message.delete()


@router.message(Command("leave"))
async def cmd_leave(message: Message) -> None:
    """Покинуть стол"""
    
    if message.chat.type == "private":
        await message.answer("🃏 Эта команда работает только в групповых чатах!")
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    game = await get_or_load_game(chat_id)
    
    if not game:
        await message.answer("⚠️ Нет активной игры!")
        return
    
    player = game.get_player(user_id)
    if not player:
        await message.answer("⚠️ Вы не за столом!")
        return
    
    if game.status == GameStatus.WAITING:
        # Удаляем игрока полностью
        game.players.remove(player)
        await db.remove_player_from_game(game.game_id, user_id)
        
        # Обновляем сообщение
        if game.players:
            msg_text = format_waiting_message(game, game.players, config.JOIN_TIMEOUT)
            keyboard = get_waiting_keyboard(game.game_id, len(game.players))
            
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game.message_id,
                text=msg_text,
                reply_markup=keyboard
            )
        else:
            # Закрываем игру
            await db.finish_game(game.game_id)
            del active_games[chat_id]
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game.message_id,
                text="⚠️ Стол закрыт — все игроки вышли."
            )
    else:
        # Автофолд
        game.remove_player(user_id)
        await save_game(game)
        await message.answer(f"👋 {format_username(player.username, user_id)} покидает стол")
    
    await message.delete()


@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    """Показать баланс"""
    
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    user = await db.get_or_create_user(user_id, username)
    
    text = format_balance_message(
        username=username,
        user_id=user_id,
        balance=user['balance'],
        games_played=user['games_played'],
        games_won=user['games_won']
    )
    
    await message.answer(text)


@router.message(Command("top"))
async def cmd_top(message: Message) -> None:
    """Топ игроков"""
    
    players = await db.get_top_players(limit=10)
    text = format_top_players(players)
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Помощь"""
    await message.answer(format_help_message())