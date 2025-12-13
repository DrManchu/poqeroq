"""
Утилиты для проверки прав доступа
"""
from typing import Optional
from config import config


def is_admin(user) -> bool:
    """Проверить, является ли пользователь администратором бота"""
    if not user.username:
        return False
    return user.username.lower() in config.ADMIN_USERNAMES


def can_manage_table(user_id: int, username: Optional[str], creator_id: Optional[int]) -> bool:
    """
    Проверить, может ли пользователь управлять столом

    Управлять столом могут:
    - Создатель стола (creator_id)
    - Администраторы бота (config.ADMIN_USERNAMES)
    """
    # Создатель стола
    is_creator = creator_id is not None and user_id == creator_id

    # Администратор бота
    is_bot_admin = username and username.lower() in config.ADMIN_USERNAMES

    return is_creator or is_bot_admin
