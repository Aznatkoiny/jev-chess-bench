"""Chess rules and public observations, independent of players and ratings.

python-chess is the sole rules authority. The benchmark automatically claims
threefold repetition and the fifty-move rule once the *current* position meets
the condition. It does not claim a draw on an unplayed intended move. Automatic
fivefold/75-move rules and checkmate precedence still use python-chess directly.
No engine information belongs in a player observation.
"""

from collections import Counter
from typing import Any

import chess
import chess.pgn


DRAW_POLICY = "auto_claim_current_threefold_and_fifty_moves"


def new_board(opening_moves: list[str]) -> chess.Board:
    """Replay a legal UCI opening from standard chess's initial position."""
    board = chess.Board()
    for uci in opening_moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal opening move at ply {len(board.move_stack) + 1}: {uci}")
        board.push(move)
    return board


def observe(board: chess.Board) -> dict[str, Any]:
    """Return all information visible to a chess player, with every legal UCI move.

    The explicit initial position and full history preserve repetition and
    draw information that cannot be recovered from a current FEN alone.
    """
    if not board.is_valid():
        raise ValueError("Cannot observe an invalid chess position")
    replay = board.root()
    initial_fen = replay.fen()
    history_san: list[str] = []
    positions: Counter[str] = Counter()
    positions[" ".join(replay.fen().split()[:4])] += 1
    for move in board.move_stack:
        history_san.append(replay.san(move))
        replay.push(move)
        # Standard FEN's legal en-passant target plus castling rights capture
        # the rights relevant to repetition. Move clocks are excluded.
        positions[" ".join(replay.fen().split()[:4])] += 1
    current_key = " ".join(board.fen().split()[:4])
    return {
        "game": "chess",
        "observation_version": 1,
        "fen": board.fen(),
        "initial_fen": initial_fen,
        "board_ascii": str(board),
        "side_to_move": "white" if board.turn else "black",
        "history_uci": [move.uci() for move in board.move_stack],
        "history_san": history_san,
        "legal_moves": sorted(move.uci() for move in board.legal_moves),
        "move_notation": "UCI (from-square + to-square + optional promotion q/r/b/n)",
        "in_check": board.is_check(),
        "castling_rights": board.castling_xfen(),
        "en_passant_square": chess.square_name(board.ep_square) if board.has_legal_en_passant() else None,
        "fullmove_number": board.fullmove_number,
        "draw": {
            "policy": DRAW_POLICY,
            "halfmove_clock": board.halfmove_clock,
            "repetition_count": positions[current_key],
            "is_threefold_repetition": board.is_repetition(3),
            "is_fifty_moves": board.is_fifty_moves(),
            "can_claim_threefold": board.can_claim_threefold_repetition(),
            "can_claim_fifty_moves": board.can_claim_fifty_moves(),
            "claim_flags_include_an_intended_next_move": True,
            "is_insufficient_material": board.is_insufficient_material(),
            "is_fivefold_repetition": board.is_fivefold_repetition(),
            "is_seventyfive_moves": board.is_seventyfive_moves(),
        },
    }


def outcome(board: chess.Board) -> dict[str, Any] | None:
    """Return a completed chess result; resource limits never become draws here."""
    if not board.is_valid():
        raise ValueError("Cannot adjudicate an invalid chess position")
    result = board.outcome(claim_draw=False)
    if result is None and board.is_fifty_moves():
        result = chess.Outcome(chess.Termination.FIFTY_MOVES, None)
    if result is None and board.is_repetition(3):
        result = chess.Outcome(chess.Termination.THREEFOLD_REPETITION, None)
    if result is None:
        return None
    return {
        "result": result.result(),
        "winner": None if result.winner is None else "white" if result.winner else "black",
        "termination": result.termination.name.lower(),
    }


def pgn(board: chess.Board, headers: dict[str, Any]) -> str:
    """Export the complete move stack, including initial FEN for custom positions."""
    record = chess.pgn.Game.from_board(board)
    for key, value in headers.items():
        record.headers[key] = str(value)
    finished = outcome(board)
    if finished:
        record.headers["Result"] = finished["result"]
        record.headers.setdefault("Termination", finished["termination"])
    elif "Result" not in headers:
        record.headers["Result"] = "*"
    record.headers["DrawPolicy"] = DRAW_POLICY
    return record.accept(chess.pgn.StringExporter(headers=True, variations=False, comments=True)) + "\n"
