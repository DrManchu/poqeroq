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
        
        # Таблица пользователей
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 10000,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица игр
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, status) 
            )
        """)
        
        # Таблица игроков в игре
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
        
        await self.connection.commit()
        logger.info("Таблицы базы данных созданы/проверены")
    
    # === МЕТОДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ===
    
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить пользователя по ID"""
        async with self.connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def create_user(self, user_id: int, username: str) -> Dict[str, Any]:
        """Создать нового пользователя"""
        await self.connection.execute(
            """INSERT OR IGNORE INTO users (user_id, username, balance) 
               VALUES (?, ?, ?)""",
            (user_id, username, config.STARTING_BALANCE)
        )
        await self.connection.commit()
        return await self.get_user(user_id)
    
    async def get_or_create_user(self, user_id: int, username: str) -> Dict[str, Any]:
        """Получить пользователя или создать нового"""
        user = await self.get_user(user_id)
        if not user:
            user = await self.create_user(user_id, username)
        else:
            # Обновляем username если изменился
            if user['username'] != username:
                await self.connection.execute(
                    "UPDATE users SET username = ? WHERE user_id = ?",
                    (username, user_id)
                )
                await self.connection.commit()
                user['username'] = username
        return user
    
    async def update_balance(self, user_id: int, amount: int) -> int:
        """Изменить баланс пользователя (+ добавить, - вычесть)"""
        await self.connection.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await self.connection.commit()
        user = await self.get_user(user_id)
        return user['balance'] if user else 0
    
    async def set_balance(self, user_id: int, balance: int) -> None:
        """Установить баланс пользователя"""
        await self.connection.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (balance, user_id)
        )
        await self.connection.commit()
    
    async def increment_games_played(self, user_id: int) -> None:
        """Увеличить счётчик сыгранных игр"""
        await self.connection.execute(
            "UPDATE users SET games_played = games_played + 1 WHERE user_id = ?",
            (user_id,)
        )
        await self.connection.commit()
    
    async def increment_games_won(self, user_id: int) -> None:
        """Увеличить счётчик выигранных игр"""
        await self.connection.execute(
            "UPDATE users SET games_won = games_won + 1 WHERE user_id = ?",
            (user_id,)
        )
        await self.connection.commit()
    
    async def get_top_players(self, chat_id: int = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить топ игроков по балансу"""
        # Если нужна фильтрация по чату - можно добавить JOIN с game_players
        async with self.connection.execute(
            """SELECT user_id, username, balance, games_played, games_won 
               FROM users ORDER BY balance DESC LIMIT ?""",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # === МЕТОДЫ ДЛЯ ИГР ===
    
    async def get_active_game(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Получить активную игру в чате"""
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
                return game
            return None
    
    async def get_game(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Получить игру по ID"""
        async with self.connection.execute(
            "SELECT * FROM games WHERE game_id = ?", (game_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                game = dict(row)
                game['community_cards'] = json.loads(game['community_cards'])
                game['deck'] = json.loads(game['deck'])
                return game
            return None
    
    async def create_game(self, chat_id: int) -> int:
        """Создать новую игру"""
        cursor = await self.connection.execute(
            """INSERT INTO games (chat_id, status, created_at) 
               VALUES (?, 'waiting', ?)""",
            (chat_id, datetime.now())
        )
        await self.connection.commit()
        return cursor.lastrowid
    
    async def update_game(self, game_id: int, **kwargs) -> None:
        """Обновить данные игры"""
        # Сериализация JSON полей
        if 'community_cards' in kwargs:
            kwargs['community_cards'] = json.dumps(kwargs['community_cards'])
        if 'deck' in kwargs:
            kwargs['deck'] = json.dumps(kwargs['deck'])
        
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [game_id]
        
        await self.connection.execute(
            f"UPDATE games SET {set_clause} WHERE game_id = ?",
            values
        )
        await self.connection.commit()
    
    async def delete_game(self, game_id: int) -> None:
        """Удалить игру"""
        await self.connection.execute(
            "DELETE FROM games WHERE game_id = ?", (game_id,)
        )
        await self.connection.commit()
    
    async def finish_game(self, game_id: int) -> None:
        """Завершить игру"""
        await self.update_game(game_id, status='finished')
    
    # === МЕТОДЫ ДЛЯ ИГРОКОВ В ИГРЕ ===
    
    async def add_player_to_game(self, game_id: int, user_id: int, seat: int) -> bool:
        """Добавить игрока в игру"""
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
        """Удалить игрока из игры"""
        await self.connection.execute(
            "DELETE FROM game_players WHERE game_id = ? AND user_id = ?",
            (game_id, user_id)
        )
        await self.connection.commit()
    
    async def get_game_players(self, game_id: int) -> List[Dict[str, Any]]:
        """Получить всех игроков в игре"""
        async with self.connection.execute(
            """SELECT gp.*, u.username, u.balance as user_balance
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
    
    async def get_player_in_game(self, game_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить игрока в конкретной игре"""
        async with self.connection.execute(
            """SELECT gp.*, u.username, u.balance as user_balance
               FROM game_players gp
               JOIN users u ON gp.user_id = u.user_id
               WHERE gp.game_id = ? AND gp.user_id = ?""",
            (game_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                player = dict(row)
                player['hole_cards'] = json.loads(player['hole_cards'])
                return player
            return None
    
    async def update_player(self, game_id: int, user_id: int, **kwargs) -> None:
        """Обновить данные игрока в игре"""
        if 'hole_cards' in kwargs:
            kwargs['hole_cards'] = json.dumps(kwargs['hole_cards'])
        
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [game_id, user_id]
        
        await self.connection.execute(
            f"UPDATE game_players SET {set_clause} WHERE game_id = ? AND user_id = ?",
            values
        )
        await self.connection.commit()
    
    async def get_active_players(self, game_id: int) -> List[Dict[str, Any]]:
        """Получить активных игроков (не сфолдивших)"""
        players = await self.get_game_players(game_id)
        return [p for p in players if not p['is_folded'] and p['is_active']]
    
    async def get_players_count(self, game_id: int) -> int:
        """Получить количество игроков в игре"""
        async with self.connection.execute(
            "SELECT COUNT(*) as count FROM game_players WHERE game_id = ?",
            (game_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row['count'] if row else 0
    
    async def get_next_seat(self, game_id: int) -> int:
        """Получить следующее свободное место"""
        async with self.connection.execute(
            "SELECT MAX(seat_position) as max_seat FROM game_players WHERE game_id = ?",
            (game_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return (row['max_seat'] + 1) if row and row['max_seat'] is not None else 0
    
    async def reset_round_bets(self, game_id: int) -> None:
        """Сбросить ставки текущего раунда для всех игроков"""
        await self.connection.execute(
            "UPDATE game_players SET current_bet = 0 WHERE game_id = ?",
            (game_id,)
        )
        await self.connection.commit()


# Глобальный экземпляр базы данных
db = Database()