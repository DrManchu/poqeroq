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

    builder.row(
        InlineKeyboardButton(
            text="🪑 Сесть за стол",
            callback_data=create_callback_data("join", game_id)
        ),
        InlineKeyboardButton(
            text="🚪 Выйти",
            callback_data=create_callback_data("leave", game_id)
        )
    )

    if players_count >= config.MIN_PLAYERS:
        builder.row(
            InlineKeyboardButton(
                text="🚀 Начать игру",
                callback_data=create_callback_data("start", game_id)
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="🔄 Обновить",
            callback_data=create_callback_data("refresh", game_id)
        ),
        InlineKeyboardButton(
            text="🗑 Удалить стол",
            callback_data=create_callback_data("delete_table", game_id)
        )
    )

    return builder.as_markup()


def get_table_settings_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Клавиатура настроек стола"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🔔 Уведомл.",
            callback_data=create_callback_data("toggle_notifications", game_id)
        ),
        InlineKeyboardButton(
            text="💰 Блайнды",
            callback_data=create_callback_data("select_blinds", game_id)
        ),
        InlineKeyboardButton(
            text="🔄 Авто",
            callback_data=create_callback_data("toggle_auto_refresh", game_id)
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="✅ Открыть стол",
            callback_data=create_callback_data("open_table", game_id)
        )
    )

    return builder.as_markup()


def get_blinds_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора блайндов"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="25/50",
            callback_data=create_callback_data("set_blinds", game_id, f"25-50")
        ),
        InlineKeyboardButton(
            text="50/100",
            callback_data=create_callback_data("set_blinds", game_id, f"50-100")
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="100/200",
            callback_data=create_callback_data("set_blinds", game_id, f"100-200")
        ),
        InlineKeyboardButton(
            text="250/500",
            callback_data=create_callback_data("set_blinds", game_id, f"250-500")
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="↩️ Назад",
            callback_data=create_callback_data("back_to_settings", game_id)
        )
    )

    return builder.as_markup()


def get_confirm_delete_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления стола"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=create_callback_data("cancel", game_id)
        ),
        InlineKeyboardButton(
            text="✅ Да, удалить",
            callback_data=create_callback_data("confirm_delete", game_id)
        )
    )

    return builder.as_markup()


def get_confirm_fold_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения фолда"""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=create_callback_data("back", game_id)
        ),
        InlineKeyboardButton(
            text="✅ Да, фолд",
            callback_data=create_callback_data("confirm_fold", game_id)
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
    
    builder.row(
        InlineKeyboardButton(
            text="👁 Мои карты",
            callback_data=create_callback_data("cards", game_id)
        )
    )
    
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
    
    row3 = []
    min_raise_total = current_bet + config.BLINDS[1]
    if player_balance + player_bet > current_bet:
        row3.append(
            InlineKeyboardButton(
                text="⬆️ Рейз",
                callback_data=create_callback_data("raise_menu", game_id)
            )
        )
    
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
    
    raise_amounts = []
    
    for multiplier in [1, 2, 3, 5]:
        amount = current_bet + (big_blind * multiplier)
        if min_raise <= amount < max_raise:
            raise_amounts.append((f"+{big_blind * multiplier}", amount))
    
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
    
    row2 = []
    half_pot = current_bet + (pot // 2)
    if min_raise <= half_pot < max_raise:
        row2.append(
            InlineKeyboardButton(
                text="½ банка",
                callback_data=create_callback_data("raise", game_id, half_pot)
            )
        )
    
    full_pot = current_bet + pot
    if min_raise <= full_pot < max_raise:
        row2.append(
            InlineKeyboardButton(
                text="1x банк",
                callback_data=create_callback_data("raise", game_id, full_pot)
            )
        )
    
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
    """Клавиатура для наблюдателей"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="👁 Мои карты",
            callback_data=create_callback_data("cards", game_id)
        )
    )
    
    return builder.as_markup()


def get_showdown_keyboard(game_id: int, is_creator: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура экрана РЕЗУЛЬТАТОВ (после вскрытия)

    ВАЖНО: Это НЕ лобби! Это финальный экран с результатами игры.
    Только 2 кнопки:
    - Обновить стол (пересылает сообщение)
    - Вернуться в лобби (переводит всех в чистое лобби)
    """
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="🔄 Обновить стол",
            callback_data=create_callback_data("refresh", game_id)
        )
    )

    builder.row(
        InlineKeyboardButton(
            text="🏠 Вернуться в лобби",
            callback_data=create_callback_data("return_to_lobby", game_id)
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
    """Пустая клавиатура"""
    return InlineKeyboardMarkup(inline_keyboard=[])