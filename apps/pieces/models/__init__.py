"""The pieces app's tables, one module each (past about 300 lines a module is split)."""

from apps.pieces.models.media import Media
from apps.pieces.models.pieces import Piece, PieceMaterial

__all__ = ["Media", "Piece", "PieceMaterial"]
