"""Player adapters: deterministic harness fixtures and an independent UCI engine.

Adapters choose exactly one observation candidate. They never replace an invalid
choice with another player's move. A StockfishPlayer belongs to one game, has a
fresh engine process, and clears its hash before every turn for consistent local
and durable-worker execution. No analysis information leaves this adapter.
"""

from __future__ import annotations

import random
import time
from typing import Any, Protocol

import chess
import chess.engine


class PlayerError(Exception):
    def __init__(self, kind: str, message: str, *, attempts: list | None = None):
        super().__init__(message)
        self.kind = kind
        self.attempts = attempts if attempts is not None else []


class Player(Protocol):
    """Future games can define their own player-visible observation dictionaries."""

    def choose(self, observation: dict[str, Any]) -> dict[str, Any]: ...


def _attempt(started: float, status: str, **extra: Any) -> dict[str, Any]:
    return {"attempt": 1, "status": status, "latency_ms": round((time.monotonic() - started) * 1000, 3), **extra}


class DeterministicPlayer:
    """Seeded random legal moves or an exact script, used only for harness tests."""

    def __init__(self, seed: int = 0, script: list[str] | None = None):
        self.random = random.Random(seed)
        self.script = iter(script) if script is not None else None
        self.seed = seed

    def choose(self, observation: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        legal = observation["legal_moves"]
        try:
            move = next(self.script) if self.script is not None else self.random.choice(legal)
        except (StopIteration, IndexError):
            raise PlayerError("invalid_response", "No scripted or legal move available", attempts=[_attempt(started, "invalid_response")]) from None
        if move not in legal:
            raise PlayerError("invalid_response", "Script selected a move outside the legal candidate set", attempts=[_attempt(started, "invalid_response", response=move)])
        attempt = _attempt(started, "ok", response=move)
        return {"move": move, "latency_ms": attempt["latency_ms"], "attempts": [attempt]}

    def close(self) -> None:
        pass


class StockfishPlayer:
    """CPU chess engine baseline, not a standalone learned move-selection model.

    Stockfish includes an NNUE evaluation network within its search engine.
    Skill Level intentionally randomizes weakened play; no seed is exposed by
    the standard UCI options, so the recorded seed is explicitly unsupported.
    """

    def __init__(self, executable: str | list[str], skill_level: int = 0, depth: int = 4, timeout_seconds: float = 2):
        if not 0 <= skill_level <= 20 or depth < 1 or timeout_seconds <= 0:
            raise ValueError("Invalid Stockfish strength or timeout settings")
        self.executable = executable
        self.skill_level = skill_level
        self.depth = depth
        self.timeout_seconds = timeout_seconds
        self.engine: chess.engine.SimpleEngine | None = None
        self.game_token = object()
        self.metadata: dict[str, Any] = {
            "kind": "chess_engine_with_nnue",
            "engine_id": None,
            "license": "GPL-3.0-or-later",
            "settings": {"Threads": 1, "Hash": 16, "Skill Level": skill_level, "UCI_LimitStrength": False, "MultiPV": 1, "depth": depth, "watchdog_seconds": timeout_seconds, "clear_hash_each_turn": True, "opening_book": None, "tablebases": None},
            "seed": None,
            "seed_support": "not exposed by standard Stockfish UCI",
        }

    def _remaining(self, started: float) -> float:
        remaining = self.timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Stockfish turn watchdog exceeded")
        return remaining

    def _board(self, observation: dict[str, Any]) -> chess.Board:
        board = chess.Board(observation["initial_fen"])
        for uci in observation["history_uci"]:
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                raise ValueError("Observation history contains an illegal move")
            board.push(move)
        if not board.is_valid() or board.fen() != observation["fen"]:
            raise ValueError("Observation history and position disagree")
        if sorted(move.uci() for move in board.legal_moves) != observation["legal_moves"]:
            raise ValueError("Observation candidate set is incomplete or inconsistent")
        return board

    def choose(self, observation: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        try:
            board = self._board(observation)
            if self.engine is None:
                self.engine = chess.engine.SimpleEngine.popen_uci(self.executable, timeout=self._remaining(started))
                self.metadata["engine_id"] = dict(self.engine.id)
                self.engine.timeout = self._remaining(started)
                # python-chess manages MultiPV=1 itself for play().
                self.engine.configure({"Threads": 1, "Hash": 16, "Skill Level": self.skill_level, "UCI_LimitStrength": False})
            self.engine.timeout = self._remaining(started)
            self.engine.configure({"Clear Hash": None})
            self.engine.timeout = self._remaining(started)
            played = self.engine.play(board, chess.engine.Limit(depth=self.depth), game=self.game_token, info=chess.engine.INFO_NONE)
            self._remaining(started)
            move = played.move.uci() if played.move is not None else None
            if move not in observation["legal_moves"]:
                raise PlayerError("invalid_response", "Engine did not select a listed legal move", attempts=[_attempt(started, "invalid_response", response=move)])
            attempt = _attempt(started, "ok", response=move)
            return {"move": move, "latency_ms": attempt["latency_ms"], "attempts": [attempt]}
        except PlayerError:
            self.close()
            raise
        except TimeoutError:
            self.close()
            raise PlayerError("timeout", "Stockfish turn watchdog exceeded", attempts=[_attempt(started, "timeout")]) from None
        except chess.engine.EngineError as exc:
            self.close()
            # python-chess can reject an illegal UCI bestmove before returning it.
            kind = "invalid_response" if "illegal uci" in str(exc).lower() or "invalid uci" in str(exc).lower() else "infrastructure"
            raise PlayerError(kind, f"Stockfish protocol failure: {exc}", attempts=[_attempt(started, kind)]) from None
        except (OSError, ValueError, KeyError) as exc:
            self.close()
            raise PlayerError("infrastructure", f"Stockfish unavailable or observation inconsistent: {exc}", attempts=[_attempt(started, "infrastructure")]) from None

    def close(self) -> None:
        if self.engine is not None:
            self.engine.close()
            self.engine = None

    def __enter__(self) -> StockfishPlayer:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
