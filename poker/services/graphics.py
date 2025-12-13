"""
Графический движок для генерации изображений игровых столов.

Сейчас поддерживается покер: генерация стола с общими картами.
"""

from io import BytesIO
from pathlib import Path
from typing import List

from PIL import Image

from game.deck import Card
from config import RANK_SYMBOLS


ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
TABLE_BG = ASSETS_DIR / "table_bg.jpg"
CARDS_DIR = ASSETS_DIR / "cards"


def generate_poker_table(community_cards: List[Card]) -> BytesIO:
    """Сгенерировать изображение покерного стола с общими картами.

    Args:
        community_cards: список общих карт (0..5).

    Returns:
        BytesIO с готовым JPEG для отправки в Telegram.
    """

    base = Image.open(TABLE_BG).convert("RGBA")
    card_width, card_height = 140, 200

    cards_count = len(community_cards)
    if cards_count:
        # Рассчитываем стартовую позицию, чтобы 5 карт были по центру.
        total_width = cards_count * card_width + (cards_count - 1) * 24
        start_x = (base.width - total_width) // 2
        y = (base.height // 2) - (card_height // 2)

        suit_short = {
            "hearts": "h",
            "diamonds": "d",
            "clubs": "c",
            "spades": "s",
        }

        for index, card in enumerate(community_cards):
            rank_symbol = RANK_SYMBOLS.get(card.rank, str(card.rank))
            filename = f"{rank_symbol}{suit_short.get(card.suit, '')}.png"
            card_path = CARDS_DIR / filename
            card_image = Image.open(card_path).convert("RGBA")
            x = start_x + index * (card_width + 24)
            base.alpha_composite(card_image.resize((card_width, card_height)), (x, y))

    buffer = BytesIO()
    base.convert("RGB").save(buffer, format="JPEG", quality=90)
    buffer.seek(0)
    return buffer

