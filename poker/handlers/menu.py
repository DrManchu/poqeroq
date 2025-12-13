"""Главное меню казино и маршрутизация по играм."""

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from database import db
from ui.keyboards import get_main_menu_keyboard, get_poker_menu_keyboard
from ui.messages import format_balance_message
from handlers import commands


router = Router()


def _main_menu_text() -> str:
    return (
        "🏰 <b>Казино Саши</b>\n"
        "Выбирайте игру и заходите за стол. Баланс общий для всех режимов."
    )


def _poker_menu_text() -> str:
    return (
        "🃏 <b>Покер</b>\n"
        "Создавайте стол в групповом чате или подключайтесь к активной партии."
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = await db.get_or_create_user(
        message.from_user.id, message.from_user.username, message.from_user.first_name
    )

    await message.answer(
        _main_menu_text(), reply_markup=get_main_menu_keyboard()
    )


@router.callback_query(F.data == "games:poker_menu")
async def cb_show_poker_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        _poker_menu_text(), reply_markup=get_poker_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "games:back")
async def cb_back_to_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        _main_menu_text(), reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.in_({"games:slots", "games:blackjack"}))
async def cb_coming_soon(callback: CallbackQuery) -> None:
    await callback.answer("Скоро...", show_alert=True)


@router.callback_query(F.data == "games:balance")
async def cb_show_balance(callback: CallbackQuery) -> None:
    user = await db.get_or_create_user(
        callback.from_user.id, callback.from_user.username, callback.from_user.first_name
    )
    text = format_balance_message(
        username=callback.from_user.username,
        user_id=callback.from_user.id,
        balance=user["balance"],
        games_played=user.get("games_played", 0),
        games_won=user.get("games_won", 0),
        first_name=callback.from_user.first_name,
    )
    await callback.answer(text, show_alert=True)


@router.callback_query(F.data == "poker:create")
async def cb_create_poker(callback: CallbackQuery) -> None:
    if callback.message.chat.type == "private":
        await callback.answer(
            "Создайте стол в групповом чате командой /poker", show_alert=True
        )
        return
    await commands.cmd_poker(callback.message)


@router.callback_query(F.data == "poker:table")
async def cb_find_table(callback: CallbackQuery) -> None:
    if callback.message.chat.type == "private":
        await callback.answer(
            "Покажу стол прямо в чате группы: используйте /table", show_alert=True
        )
        return
    await commands.cmd_table(callback.message)

