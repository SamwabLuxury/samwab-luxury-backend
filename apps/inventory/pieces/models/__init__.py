"""The pieces app's tables, one module each (past about 300 lines a module is split)."""

from apps.inventory.pieces.models.media import Media
from apps.inventory.pieces.models.pieces import Piece, PieceMaterial

__all__ = ["Media", "Piece", "PieceMaterial"]
