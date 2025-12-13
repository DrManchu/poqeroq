"""
Работа с базой данных SQLite
"""

import aiosqlite
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from config import config

logger = logging.getLogger(__name__)


class Database:
    """Асинхронный менеджер базы данных"""
    
    def __init__(self, db_path: str = config.DATABASE_PATH):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self) -> None:
        """Подключение к базе данных"""
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info(f"Подключено к базе данных: {self.db_path}")
    
    async def disconnect(self) -> None:
        """Отключение от базы данных"""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Отключено от базы данных")
    
    @property
    def connection(self) -> aiosqlite.Connection:
        """Получить соединение"""
        if not self._connection:
            raise RuntimeError("База данных не подключена")
        return self._connection
    
    async def _create_tables(self) -> None:
        """Создание таблиц"""
        
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance INTEGER DEFAULT 10000,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                total_won INTEGER DEFAULT 0,
                total_lost INTEGER DEFAULT 0,
                best_win INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER,
                status TEXT DEFAULT 'waiting',
                pot INTEGER DEFAULT 0,
                current_bet INTEGER DEFAULT 0,
                dealer_index INTEGER DEFAULT 0,
                current_player_index INTEGER DEFAULT 0,
                community_cards TEXT DEFAULT '[]',
                deck TEXT DEFAULT '[]',
                creator_id INTEGER,
                notifications_enabled BOOLEAN DEFAULT TRUE,
                blinds_small INTEGER DEFAULT 50,
                blinds_big INTEGER DEFAULT 100,
                auto_refresh_enabled BOOLEAN DEFAULT TRUE,
                pot_distributed BOOLEAN DEFAULT FALSE,
                stats_updated BOOLEAN DEFAULT FALSE,
                pot_contributions TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS game_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                seat_position INTEGER NOT NULL,
                hole_cards TEXT DEFAULT '[]',
                current_bet INTEGER DEFAULT 0,
                total_bet INTEGER DEFAULT 0,
                is_folded BOOLEAN DEFAULT FALSE,
                is_all_in BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(game_id, user_id),
                UNIQUE(game_id, seat_position)
            )
        """)

        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS game_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
            )
        """)
        
        await self.connection.commit()
    
    # === МЕТОДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ===
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with self.connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        async with self.connection.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def create_user(self, user_id: int, username: str, first_name: str = None) -> Dict[str, Any]:
        await self.connection.execute(
            """INSERT OR IGNORE INTO users (user_id, username, first_name, balance)
               VALUES (?, ?, ?, ?)""",
            (user_id, username, first_name, config.STARTING_BALANCE)
        )
        await self.connection.commit()
        return await self.get_user(user_id)
    
    async def get_or_create_user(self, user_id: int, username: str, first_name: str = None) -> Dict[str, Any]:
        user = await self.get_user(user_id)
        if not user:
            user = await self.create_user(user_id, username, first_name)
        else:
            updates = []
            params = []
            if user['username'] != username:
                updates.append("username = ?")
                params.append(username)
            if first_name and user.get('first_name') != first_name:
                updates.append("first_name = ?")
                params.append(first_name)

            if updates:
                params.append(user_id)
                await self.connection.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?",
                    params
                )
                await self.connection.commit()
        return user
    
    async def update_balance(self, user_id: int, amount: int) -> int:
        await self.connection.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await self.connection.commit()
        user = await self.get_user(user_id)
        return user['balance'] if user else 0
    
    async def set_balance(self, user_id: int, balance: int) -> None:
        await self.connection.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (balance, user_id)
        )
        await self.connection.commit()
    
    async def increment_games_played(self, user_id: int) -> None:
        await self.connection.execute(
            "UPDATE users SET games_played = games_played + 1 WHERE user_id = ?",
            (user_id,)
        )
        await self.connection.commit()
    
    async def increment_games_won(self, user_id: int) -> None:
        await self.connection.execute(
            "UPDATE users SET games_won = games_won + 1 WHERE user_id = ?",
            (user_id,)
        )
        await self.connection.commit()

    async def update_win_stats(self, user_id: int, amount: int) -> None:
        await self.connection.execute(
            """UPDATE users
               SET total_won = total_won + ?,
                   best_win = MAX(best_win, ?)
               WHERE user_id = ?""",
            (amount, amount, user_id)
        )
        await self.connection.commit()

    async def update_loss_stats(self, user_id: int, amount: int) -> None:
        await self.connection.execute(
            "UPDATE users SET total_lost = total_lost + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await self.connection.commit()

    async def get_top_players(self, chat_id: int = None, limit: int = 10) -> List[Dict[str, Any]]:
        async with self.connection.execute(
            """SELECT user_id, username, first_name, balance, games_played, games_won 
               FROM users ORDER BY balance DESC LIMIT ?""",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # === МЕТОДЫ ДЛЯ ИГР ===
    
    async def get_active_game(self, chat_id: int) -> Optional[Dict[str, Any]]:
        async with self.connection.execute(
            """SELECT * FROM games 
               WHERE chat_id = ? AND status != 'finished'
               ORDER BY created_at DESC LIMIT 1""",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                game = dict(row)
                game['community_cards'] = json.loads(game['community_cards'])
                game['deck'] = json.loads(game['deck'])
                # Загружаем pot_contributions если есть
                if 'pot_contributions' in game and game['pot_contributions']:
                    game['pot_contributions'] = json.loads(game['pot_contributions'])
                else:
                    game['pot_contributions'] = {}
                return game
            return None
    
    async def create_game(self, chat_id: int) -> int:
        cursor = await self.connection.execute(
            """INSERT INTO games (chat_id, status, created_at) 
               VALUES (?, 'waiting', ?)""",
            (chat_id, datetime.now())
        )
        await self.connection.commit()
        return cursor.lastrowid
    
    async def update_game(self, game_id: int, **kwargs) -> None:
        if 'community_cards' in kwargs:
            kwargs['community_cards'] = json.dumps(kwargs['community_cards'])
        if 'deck' in kwargs:
            kwargs['deck'] = json.dumps(kwargs['deck'])
        if 'pot_contributions' in kwargs:
            kwargs['pot_contributions'] = json.dumps(kwargs['pot_contributions'])
        
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [game_id]
        
        await self.connection.execute(
            f"UPDATE games SET {set_clause} WHERE game_id = ?",
            values
        )
        await self.connection.commit()
    
    async def finish_game(self, game_id: int) -> None:
        await self.update_game(game_id, status='finished')

    # === МЕТОДЫ ДЛЯ СООБЩЕНИЙ ===

    async def add_game_message(self, game_id: int, chat_id: int, message_id: int) -> None:
        try:
            await self.connection.execute(
                """INSERT INTO game_messages (game_id, chat_id, message_id)
                   VALUES (?, ?, ?)""",
                (game_id, chat_id, message_id)
            )
            await self.connection.commit()
        except Exception as e:
            logger.error(f"Ошибка добавления сообщения: {e}")

    async def get_game_messages(self, game_id: int) -> List[int]:
        async with self.connection.execute(
            "SELECT message_id FROM game_messages WHERE game_id = ? ORDER BY created_at",
            (game_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def clear_game_messages(self, game_id: int) -> None:
        await self.connection.execute(
            "DELETE FROM game_messages WHERE game_id = ?",
            (game_id,)
        )
        await self.connection.commit()

    # === МЕТОДЫ ДЛЯ ИГРОКОВ В ИГРЕ ===
    
    async def add_player_to_game(self, game_id: int, user_id: int, seat: int) -> bool:
        try:
            await self.connection.execute(
                """INSERT INTO game_players (game_id, user_id, seat_position)
                   VALUES (?, ?, ?)""",
                (game_id, user_id, seat)
            )
            await self.connection.commit()
            return True
        except aiosqlite.IntegrityError:
            return False
    
    async def remove_player_from_game(self, game_id: int, user_id: int) -> None:
        await self.connection.execute(
            "DELETE FROM game_players WHERE game_id = ? AND user_id = ?",
            (game_id, user_id)
        )
        await self.connection.commit()
    
    async def get_game_players(self, game_id: int) -> List[Dict[str, Any]]:
        async with self.connection.execute(
            """SELECT gp.*, u.username, u.first_name, u.balance as user_balance
               FROM game_players gp
               JOIN users u ON gp.user_id = u.user_id
               WHERE gp.game_id = ?
               ORDER BY gp.seat_position""",
            (game_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            players = []
            for row in rows:
                player = dict(row)
                player['hole_cards'] = json.loads(player['hole_cards'])
                players.append(player)
            return players
    
    async def update_player(self, game_id: int, user_id: int, **kwargs) -> None:
        if 'hole_cards' in kwargs:
            kwargs['hole_cards'] = json.dumps(kwargs['hole_cards'])
        
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [game_id, user_id]
        
        await self.connection.execute(
            f"UPDATE game_players SET {set_clause} WHERE game_id = ? AND user_id = ?",
            values
        )
        await self.connection.commit()

db = Database()