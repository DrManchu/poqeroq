"""Реестр активных игровых сессий для единых ограничений по балансу."""

from collections import defaultdict
from typing import Iterable

_sessions: dict[int, dict[str, set[int]]] = defaultdict(lambda: {"users": set(), "type": ""})


def register_session(game_id: int, game_type: str, user_ids: Iterable[int]) -> None:
    entry = _sessions[game_id]
    entry["type"] = game_type
    entry["users"].update(user_ids)


def clear_session(game_id: int) -> None:
    _sessions.pop(game_id, None)


def user_has_active_session(user_id: int) -> bool:
    return any(user_id in entry["users"] for entry in _sessions.values())

