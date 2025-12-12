"""
Модуль Inline-клавиатур для покерного бота
"""

from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config
from utils.helpers import create_callback_data, format_chips


def get_waiting_keyboard(game_id: int, players_count: int) -> InlineKeyboardMarkup:
    """Клавиатура ожидания игроков"""
    builder = InlineKeyboardBuilder()
    
    # Кнопка присоединения
    builder.row(
        InlineKeyboardButton(
            text="🪑 Сесть за стол",
            callback_data=create_callback_data("join", game_id)
        )
    )
    
    # Кнопка начала игры (если достаточно игроков)
    if players_count >= config.MIN_PLAYERS:
        builder.row(
            InlineKeyboardButton(
                text="🚀 Начать игру",
                callback_data=create_callback_data("start", game_id)
            )
        )
    
    # Кнопка выхода
    builder.row(
        InlineKeyboardButton(
            text="🚪 Покинуть стол",
            callback_data=create_callback_data("leave", game_id)
        )
    )
    
    return builder.as_markup()


def get_game_keyboard(
    game_id: int,
    current_bet: int,
    player_bet: int,
    player_balance: int,
    can_check: bool = False
) -> InlineKeyboardMarkup:
    """Клавиатура для хода игрока"""
    builder = InlineKeyboardBuilder()
    
    amount_to_call = current_bet - player_bet
    
    # Первый ряд: Мои карты
    builder.row(
        InlineKeyboardButton(
            text="👁 Мои карты",
            callback_data=create_callback_data("cards", game_id)
        )
    )
    
    # Второй ряд: Фолд + Колл/Чек
    row2 = [
        InlineKeyboardButton(
            text="❌ Фолд",
            callback_data=create_callback_data("fold", game_id)
        )
    ]
    
    if can_check or amount_to_call <= 0:
        row2.append(
            InlineKeyboardButton(
                text="📞 Чек",
                callback_data=create_callback_data("check", game_id)
            )
        )
    else:
        call_amount = min(amount_to_call, player_balance)
        if call_amount >= player_balance:
            row2.append(
                InlineKeyboardButton(
                    text=f"🔥 Олл-ин {format_chips(player_balance)}",
                    callback_data=create_callback_data("allin", game_id)
                )
            )
        else:
            row2.append(
                InlineKeyboardButton(
                    text=f"✅ Колл {format_chips(call_amount)}",
                    callback_data=create_callback_data("call", game_id)
                )
            )
    
    builder.row(*row2)
    
    # Третий ряд: Рейз + Олл-ин
    row3 = []
    
    # Рейз доступен если есть достаточно фишек
    min_raise_total = current_bet + config.BLINDS[1]
    if player_balance + player_bet > current_bet:
        row3.append(
            InlineKeyboardButton(
                text="⬆️ Рейз",
                callback_data=create_callback_data("raise_menu", game_id)
            )
        )
    
    # Олл-ин
    if player_balance > 0 and amount_to_call < player_balance:
        row3.append(
            InlineKeyboardButton(
                text=f"🔥 Олл-ин {format_chips(player_balance + player_bet)}",
                callback_data=create_callback_data("allin", game_id)
            )
        )
    
    if row3:
        builder.row(*row3)
    
    return builder.as_markup()


def get_raise_keyboard(
    game_id: int,
    current_bet: int,
    player_bet: int,
    player_balance: int,
    pot: int,
    big_blind: int
) -> InlineKeyboardMarkup:
    """Клавиатура выбора размера рейза"""
    builder = InlineKeyboardBuilder()
    
    min_raise = current_bet + big_blind
    max_raise = player_bet + player_balance
    
    # Быстрые суммы рейза
    raise_amounts = []
    
    # +BB, +2BB, +3BB, +5BB
    for multiplier in [1, 2, 3, 5]:
        amount = current_bet + (big_blind * multiplier)
        if min_raise <= amount < max_raise:
            raise_amounts.append((f"+{big_blind * multiplier}", amount))
    
    # Первый ряд: маленькие рейзы
    row1 = []
    for label, amount in raise_amounts[:4]:
        row1.append(
            InlineKeyboardButton(
                text=label,
                callback_data=create_callback_data("raise", game_id, amount)
            )
        )
    if row1:
        builder.row(*row1)
    
    # Второй ряд: процент от банка
    row2 = []
    
    # 1/2 банка
    half_pot = current_bet + (pot // 2)
    if min_raise <= half_pot < max_raise:
        row2.append(
            InlineKeyboardButton(
                text="½ банка",
                callback_data=create_callback_data("raise", game_id, half_pot)
            )
        )
    
    # Полный банк
    full_pot = current_bet + pot
    if min_raise <= full_pot < max_raise:
        row2.append(
            InlineKeyboardButton(
                text="1x банк",
                callback_data=create_callback_data("raise", game_id, full_pot)
            )
        )
    
    # 2x банка
    double_pot = current_bet + (pot * 2)
    if min_raise <= double_pot < max_raise:
        row2.append(
            InlineKeyboardButton(
                text="2x банк",
                callback_data=create_callback_data("raise", game_id, double_pot)
            )
        )
    
    if row2:
        builder.row(*row2)
    
    # Третий ряд: Олл-ин и Назад
    builder.row(
        InlineKeyboardButton(
            text=f"🔥 Олл-ин {format_chips(max_raise)}",
            callback_data=create_callback_data("allin", game_id)
        ),
        InlineKeyboardButton(
            text="↩️ Назад",
            callback_data=create_callback_data("back", game_id)
        )
    )
    
    return builder.as_markup()


def get_spectator_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для наблюдателей (не их ход)"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="👁 Мои карты",
            callback_data=create_callback_data("cards", game_id)
        )
    )
    
    return builder.as_markup()


def get_showdown_keyboard(game_id: int, is_creator: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура после вскрытия"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="🔄 Новая раздача",
            callback_data=create_callback_data("new_hand", game_id)
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="🚪 Покинуть стол",
            callback_data=create_callback_data("leave", game_id)
        )
    )
    
    return builder.as_markup()


def get_not_enough_players_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Клавиатура когда недостаточно игроков"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="🪑 Сесть за стол",
            callback_data=create_callback_data("join", game_id)
        )
    )
    
    builder.row(
        InlineKeyboardButton(
            text="❌ Закрыть стол",
            callback_data=create_callback_data("close", game_id)
        )
    )
    
    return builder.as_markup()


def get_confirm_keyboard(game_id: int, action: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="✅ Да",
            callback_data=create_callback_data(f"confirm_{action}", game_id)
        ),
        InlineKeyboardButton(
            text="❌ Нет",
            callback_data=create_callback_data("back", game_id)
        )
    )
    
    return builder.as_markup()


def get_empty_keyboard() -> InlineKeyboardMarkup:
    """Пустая клавиатура (убрать кнопки)"""
    return InlineKeyboardMarkup(inline_keyboard=[])