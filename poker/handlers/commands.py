"""
Обработчики команд покерного бота
"""

import asyncio
import logging
from typing import Optional
from collections import defaultdict

from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command, CommandStart

from database import db
from game.poker import PokerGame, GameStatus
from game.player import Player
from game.deck import cards_from_list, cards_to_list
from ui.messages import (
    format_waiting_message, format_balance_message,
    format_top_players, format_help_message, format_error_message,
    format_table_settings, format_stats_message
)
from ui.keyboards import get_waiting_keyboard, get_table_settings_keyboard, get_spectator_keyboard, get_game_keyboard, get_confirm_delete_keyboard
from config import config
from utils.helpers import get_display_name, get_mention, create_callback_data
from utils.permissions import can_manage_table, is_admin

logger = logging.getLogger(__name__)
router = Router()

# Хранилище активных игр в памяти
active_games: dict[int, PokerGame] = {}

# Хранилище таймеров
game_timers: dict[int, asyncio.Task] = {}


async def get_or_load_game(chat_id: int) -> Optional[PokerGame]:
    """Получить игру из памяти или загрузить из БД"""
    if chat_id in active_games:
        return active_games[chat_id]
    
    game_data = await db.get_active_game(chat_id)
    if not game_data:
        return None
    
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

    game.creator_id = game_data.get('creator_id')
    game.notifications_enabled = game_data.get('notifications_enabled', True)
    game.blinds_small = game_data.get('blinds_small', 50)
    game.blinds_big = game_data.get('blinds_big', 100)
    game.auto_refresh_enabled = game_data.get('auto_refresh_enabled', True)

    game.pot_distributed = game_data.get('pot_distributed', False)
    game.stats_updated = game_data.get('stats_updated', False)

    if 'pot_contributions' in game_data and game_data['pot_contributions']:
        game.pot_contributions = defaultdict(int, {int(k): v for k, v in game_data['pot_contributions'].items()})
    else:
        game.pot_contributions = defaultdict(int)

    players_data = await db.get_game_players(game_data['game_id'])
    for p_data in players_data:
        player = Player.from_db_row(p_data)
        game.players.append(player)
    
    active_games[chat_id] = game
    return game


async def restore_active_games(bot: Bot) -> None:
    """Восстановить активные игры после перезагрузки"""
    logger.info("🔄 Восстановление активных игр...")
    try:
        async with db.connection.execute(
            "SELECT chat_id FROM games WHERE status != 'finished'"
        ) as cursor:
            rows = await cursor.fetchall()
            
        count = 0
        for row in rows:
            chat_id = row[0]
            game = await get_or_load_game(chat_id)
            if game:
                count += 1
                if game.status not in [GameStatus.WAITING, GameStatus.FINISHED, GameStatus.SHOWDOWN]:
                    from handlers.callbacks import start_turn_timer
                    await start_turn_timer(bot, game)
                    logger.info(f"   Восстановлен таймер для игры {game.game_id} в чате {chat_id}")
        
        logger.info(f"✅ Восстановлено активных игр: {count}")
    except Exception as e:
        logger.error(f"Ошибка при восстановлении игр: {e}")


async def save_game(game: PokerGame) -> None:
    """Сохранить игру в БД"""
    await db.update_game(game.game_id, **game.to_db_data())

    for player in game.players:
        await db.update_player(
            game.game_id,
            player.user_id,
            hole_cards=cards_to_list(player.hole_cards),
            current_bet=player.current_bet,
            total_bet=player.total_bet,
            is_folded=player.is_folded,
            is_all_in=player.is_all_in,
            is_active=player.is_active
        )
        await db.set_balance(player.user_id, player.balance)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    user = await db.get_or_create_user(user_id, username, first_name)

    await message.answer(
        f"🃏 <b>Добро пожаловать в Техасский Холдем!</b>\n\n"
        f"Ваш баланс: <b>{user['balance']:,}</b> 🪙\n\n"
        f"Используйте /poker в групповом чате, чтобы создать стол.\n"
        f"Команда /help покажет правила игры."
    )


@router.message(Command("poker"))
async def cmd_poker(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("🃏 Эта команда работает только в групповых чатах!")
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    existing_game = await get_or_load_game(chat_id)
    if existing_game and existing_game.status != GameStatus.FINISHED:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from utils.helpers import create_callback_data

        status_text = {
            GameStatus.WAITING: "ожидание игроков",
            GameStatus.PREFLOP: "игра (префлоп)",
            GameStatus.FLOP: "игра (флоп)",
            GameStatus.TURN: "игра (терн)",
            GameStatus.RIVER: "игра (ривер)",
            GameStatus.SHOWDOWN: "вскрытие"
        }.get(existing_game.status, "активна")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Обновить текущий стол",
                callback_data=create_callback_data("refresh", existing_game.game_id)
            )],
            [InlineKeyboardButton(
                text="🗑 Удалить и создать новый",
                callback_data=create_callback_data("delete_table", existing_game.game_id)
            )]
        ])

        sent_msg = await message.answer(
            f"⚠️ <b>В чате уже есть активный стол</b>\n\n"
            f"Статус: {status_text}\n\n"
            f"Выберите действие:",
            reply_markup=keyboard
        )
        await db.add_game_message(existing_game.game_id, chat_id, sent_msg.message_id)
        return
    
    user = await db.get_or_create_user(user_id, username, first_name)
    
    if user['balance'] < config.BLINDS[1]:
        await message.answer(
            f"⚠️ Недостаточно фишек для игры!\n"
            f"Ваш баланс: {user['balance']} 🪙\n"
            f"Минимум: {config.BLINDS[1]} 🪙"
        )
        return
    
    game_id = await db.create_game(chat_id)

    game = PokerGame(
        game_id=game_id,
        chat_id=chat_id,
        creator_id=user_id
    )

    active_games[chat_id] = game
    await save_game(game)

    msg_text = format_table_settings(game, username, first_name)
    keyboard = get_table_settings_keyboard(game_id)

    sent_message = await message.answer(msg_text, reply_markup=keyboard)

    game.message_id = sent_message.message_id
    await db.update_game(game_id, message_id=sent_message.message_id)
    await db.add_game_message(game_id, chat_id, sent_message.message_id)

    logger.info(f"Создана игра {game_id} в чате {chat_id} пользователем {username}")


@router.message(Command("join"))
async def cmd_join(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("🃏 Эта команда работает только в групповых чатах!")
        return
    
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    game = await get_or_load_game(chat_id)
    
    if not game or game.status == GameStatus.FINISHED:
        await message.answer("⚠️ Нет активной игры. Используйте /poker")
        return
    
    # Разрешаем join во время showdown, чтобы сесть на след. игру
    if game.status != GameStatus.WAITING and game.status != GameStatus.SHOWDOWN:
        await message.answer("⚠️ Игра уже идет! Подождите окончания раздачи.")
        return
    
    if game.get_player(user_id):
        await message.answer("⚠️ Вы уже за столом!")
        return
    
    if len(game.players) >= config.MAX_PLAYERS:
        await message.answer("⚠️ Стол заполнен!")
        return
    
    user = await db.get_or_create_user(user_id, username)
    
    if user['balance'] < config.BLINDS[1]:
        await message.answer(f"⚠️ Недостаточно фишек! Минимум: {config.BLINDS[1]} 🪙")
        return
    
    seat = len(game.players)
    player = Player(
        user_id=user_id,
        username=username,
        first_name=first_name,
        seat_position=seat,
        balance=user['balance']
    )
    # Если заходим не в WAITING, то игрок неактивен в текущей раздаче
    player.is_active = (game.status == GameStatus.WAITING)

    game.players.append(player)
    await db.add_player_to_game(game.game_id, user_id, seat)
    
    try:
        # Обновляем сообщение только если это лобби
        if game.status == GameStatus.WAITING:
            msg_text = format_waiting_message(game, game.players, config.JOIN_TIMEOUT)
            keyboard = get_waiting_keyboard(game.game_id, len(game.players))
            
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game.message_id,
                text=msg_text,
                reply_markup=keyboard
            )
        else:
            await message.answer("✅ Вы сели за стол! Игра начнется в следующей раздаче.")

    except Exception as e:
        logger.warning(f"Ошибка обновления сообщения: {e}")
    
    await message.delete()


@router.message(Command("leave"))
async def cmd_leave(message: Message) -> None:
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
        game.players.remove(player)
        await db.remove_player_from_game(game.game_id, user_id)
        
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
            await db.finish_game(game.game_id)
            del active_games[chat_id]
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=game.message_id,
                text="⚠️ Стол закрыт — все игроки вышли."
            )
    else:
        # Если игра идет или результаты - вызываем callback логику (просто помечаем на выход)
        # Но через команду проще просто сказать "используйте кнопку" или сделать автофолд
        game.remove_player(user_id)
        await save_game(game)
        await message.answer(f"👋 {get_display_name(player.first_name, player.username)} покидает стол")
    
    await message.delete()


@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    user = await db.get_or_create_user(user_id, username, first_name)

    text = format_balance_message(
        username=username,
        user_id=user_id,
        balance=user['balance'],
        games_played=user['games_played'],
        games_won=user['games_won'],
        first_name=first_name
    )

    await message.answer(text)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    user = await db.get_or_create_user(user_id, username, first_name)

    text = format_stats_message(user)

    await message.answer(text)


@router.message(Command("give"))
async def cmd_give(message: Message) -> None:
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    chat_id = message.chat.id

    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    if not args:
        await message.answer("⚠️ Использование: /give @username сумма")
        return

    # 1. Проверка: Нельзя передавать во время раздачи!
    game = active_games.get(chat_id)
    if game and game.status not in [GameStatus.WAITING, GameStatus.FINISHED, GameStatus.SHOWDOWN]:
        player = game.get_player(user_id)
        if player and player.is_in_hand:
            await message.answer("⚠️ Нельзя передавать фишки во время раздачи!")
            return

    target_user_id = None
    target_username = None
    
    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username
        try: amount = int(args[0])
        except: return
    elif len(args) >= 2:
        target_mention = args[0].lstrip('@')
        try: amount = int(args[1])
        except: return
        target_user = await db.get_user_by_username(target_mention)
        if not target_user: return
        target_user_id = target_user['user_id']
        target_username = target_user['username']
    else:
        return

    if target_user_id == user_id: return
    if amount <= 0: return

    sender = await db.get_or_create_user(user_id, username, first_name)
    if sender['balance'] < amount:
        await message.answer("⚠️ Недостаточно фишек!")
        return

    await db.update_balance(user_id, -amount)
    await db.update_balance(target_user_id, amount)

    # ОБНОВЛЕНИЕ ПАМЯТИ
    if game:
        p_sender = game.get_player(user_id)
        p_target = game.get_player(target_user_id)
        if p_sender: p_sender.balance -= amount
        if p_target: p_target.balance += amount
        if game.status == GameStatus.WAITING:
            msg = format_waiting_message(game, game.players, None)
            from ui.keyboards import get_waiting_keyboard
            kb = get_waiting_keyboard(game.game_id, len(game.players))
            try: await message.bot.edit_message_text(chat_id, game.message_id, text=msg, reply_markup=kb)
            except: pass

    await message.answer(f"✅ Перевод {amount} 🪙 выполнен для {target_username}!")


@router.message(Command("top"))
async def cmd_top(message: Message) -> None:
    players = await db.get_top_players(limit=10)
    text = format_top_players(players)
    await message.answer(text)


@router.message(Command("table"))
async def cmd_table(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("🃏 Эта команда работает только в групповых чатах!")
        return

    chat_id = message.chat.id
    game = await get_or_load_game(chat_id)

    if not game:
        await message.answer("⚠️ Нет активной игры. Используйте /poker")
        return

    if game.message_id:
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=game.message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить старое сообщение: {e}")

    creator_username = None
    if game.creator_id:
        creator = game.get_player(game.creator_id)
        if creator:
            creator_username = creator.username
        else:
            creator_user = await db.get_user(game.creator_id)
            if creator_user:
                creator_username = creator_user['username']

    if game.status == GameStatus.WAITING:
        msg_text = format_waiting_message(game, game.players, None, creator_username)
        keyboard = get_waiting_keyboard(game.game_id, len(game.players))
    else:
        from ui.messages import format_game_table
        msg_text = format_game_table(game, game.players, None)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from utils.helpers import create_callback_data
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=create_callback_data("refresh", game.game_id))]
        ])

    sent_message = await message.answer(msg_text, reply_markup=keyboard)

    game.message_id = sent_message.message_id
    await db.update_game(game.game_id, message_id=sent_message.message_id)
    await db.add_game_message(game.game_id, chat_id, sent_message.message_id)


@router.message(Command("closetable"))
async def cmd_closetable(message: Message) -> None:
    if message.chat.type == "private":
        await message.answer("🃏 Эта команда работает только в групповых чатах!")
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username

    game = await get_or_load_game(chat_id)

    if not game:
        await message.answer("⚠️ Нет активной игры!")
        return

    # ВАЖНОЕ ИЗМЕНЕНИЕ: Запрет удаления активного стола
    if game.status not in [GameStatus.WAITING, GameStatus.FINISHED, GameStatus.SHOWDOWN]:
        await message.answer(
            "⚠️ <b>Нельзя удалить стол во время активной игры!</b>\n"
            "Фишки игроков находятся в банке.\n"
            "Дождитесь окончания раздачи."
        )
        return

    if not can_manage_table(user_id, username, game.creator_id):
        await message.answer("⚠️ Только организатор стола может удалить стол!")
        return

    from ui.keyboards import get_confirm_delete_keyboard

    confirm_text = (
        "⚠️ <b>Удалить стол?</b>\n\n"
        "Все игроки будут убраны, игра завершится.\n"
    )

    await message.answer(
        confirm_text,
        reply_markup=get_confirm_delete_keyboard(game.game_id)
    )


@router.message(Command("addchips"))
async def cmd_addchips(message: Message) -> None:
    if not is_admin(message.from_user):
        await message.answer("⚠️ У вас нет прав администратора")
        return

    args = message.text.split()[1:]
    if not args:
        await message.answer("⚠️ Использование: /addchips сумма [@username]")
        return

    try:
        amount = int(args[0])
    except ValueError:
        await message.answer("⚠️ Сумма должна быть числом")
        return

    target_user_id = message.from_user.id
    if len(args) > 1:
        u = await db.get_user_by_username(args[1].lstrip('@'))
        if u: target_user_id = u['user_id']
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id

    await db.update_balance(target_user_id, amount)
    
    # Обновляем память активной игры
    chat_id = message.chat.id
    game = active_games.get(chat_id)
    if game:
        p = game.get_player(target_user_id)
        if p: p.balance += amount

    await message.answer(f"💎 Добавлено {amount} фишек.")


@router.message(Command("removechips"))
async def cmd_removechips(message: Message) -> None:
    if not is_admin(message.from_user): return
    args = message.text.split()[1:]
    if not args: return
    try: amount = int(args[0])
    except: return

    target_user_id = message.from_user.id
    if len(args) > 1:
        u = await db.get_user_by_username(args[1].lstrip('@'))
        if u: target_user_id = u['user_id']
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id

    await db.update_balance(target_user_id, -amount)
    
    chat_id = message.chat.id
    game = active_games.get(chat_id)
    if game:
        p = game.get_player(target_user_id)
        if p: p.balance -= amount

    await message.answer(f"🗑 Снято {amount} фишек.")


@router.message(Command("setbalance"))
async def cmd_setbalance(message: Message) -> None:
    if not is_admin(message.from_user): return
    args = message.text.split()[1:]
    if not args: return
    try: amount = int(args[0])
    except: return

    target_user_id = message.from_user.id
    if len(args) > 1:
        u = await db.get_user_by_username(args[1].lstrip('@'))
        if u: target_user_id = u['user_id']
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id

    await db.set_balance(target_user_id, amount)
    
    chat_id = message.chat.id
    game = active_games.get(chat_id)
    if game:
        p = game.get_player(target_user_id)
        if p: p.balance = amount

    await message.answer(f"⚖️ Баланс установлен: {amount}")


@router.message(Command("admin_reset"))
async def cmd_admin_reset(message: Message) -> None:
    if not is_admin(message.from_user): return
    # ... логика сброса (можно оставить старую версию, если используется)
    # ... или использовать setbalance
    await message.answer("Используйте /setbalance")


@router.message(Command("admin_balance"))
async def cmd_admin_balance(message: Message) -> None:
    if not is_admin(message.from_user): return
    await message.answer("Используйте /setbalance")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(format_help_message())