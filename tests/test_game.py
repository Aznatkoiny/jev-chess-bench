"""Synthetic rules and adapter checks, never measured Jev benchmark results."""

import io
import json
import sys
import textwrap

import chess
import chess.pgn
import pytest

from chessbench import game
from chessbench.players import DeterministicPlayer, PlayerError, StockfishPlayer


def test_initial_observation_contains_all_twenty_legal_moves_and_no_evaluation():
    board = game.new_board([])
    obs = game.observe(board)
    assert obs["legal_moves"] == sorted(move.uci() for move in board.legal_moves)
    assert len(obs["legal_moves"]) == 20
    assert obs["side_to_move"] == "white"
    assert obs["fen"] == chess.STARTING_FEN
    assert obs["history_uci"] == obs["history_san"] == []
    assert not any(word in json.dumps(obs) for word in ["centipawn", '"evaluation"', '"bestmove"'])
    assert game.outcome(board) is None


def test_opening_replay_and_observation_preserve_full_history_without_mutation():
    moves = ["e2e4", "c7c5", "g1f3", "d7d6"]
    board = game.new_board(moves)
    before = (board.fen(), list(board.move_stack))
    obs = game.observe(board)
    assert obs["history_uci"] == moves
    assert obs["history_san"] == ["e4", "c5", "Nf3", "d6"]
    assert obs["initial_fen"] == chess.STARTING_FEN
    assert (board.fen(), board.move_stack) == before


@pytest.mark.parametrize("moves", [["e2e5"], ["0000"], ["Nf3"]])
def test_illegal_null_and_non_uci_opening_moves_are_rejected(moves):
    with pytest.raises(ValueError):
        game.new_board(moves)


def test_castling_moves_rook_and_king_and_updates_rights():
    board = game.new_board(["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"])
    assert "e1g1" in game.observe(board)["legal_moves"]
    board.push_uci("e1g1")
    assert board.piece_at(chess.G1) == chess.Piece(chess.KING, chess.WHITE)
    assert board.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)
    assert not board.has_castling_rights(chess.WHITE)


def test_castling_through_check_is_absent_from_observation():
    board = chess.Board("k4r2/8/8/8/8/8/8/4K2R w K - 0 1")
    assert board.is_valid()
    assert "e1g1" not in game.observe(board)["legal_moves"]


def test_en_passant_capture_removes_the_passed_pawn():
    board = game.new_board(["e2e4", "a7a6", "e4e5", "d7d5"])
    assert "e5d6" in game.observe(board)["legal_moves"]
    assert game.observe(board)["en_passant_square"] == "d6"
    board.push_uci("e5d6")
    assert board.piece_at(chess.D5) is None
    assert board.piece_at(chess.D6) == chess.Piece(chess.PAWN, chess.WHITE)


def test_en_passant_exposing_king_is_not_legal():
    board = chess.Board("k3r3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert "e5d6" not in game.observe(board)["legal_moves"]


@pytest.mark.parametrize("piece", ["q", "r", "b", "n"])
def test_all_four_promotions_are_preserved(piece):
    board = chess.Board("7k/P7/8/8/8/8/8/7K w - - 0 1")
    assert {"a7a8q", "a7a8r", "a7a8b", "a7a8n"}.issubset(game.observe(board)["legal_moves"])
    board.push_uci("a7a8" + piece)
    assert board.piece_at(chess.A8).symbol().lower() == piece


def test_fools_mate_is_a_black_win_and_survives_pgn_roundtrip():
    board = game.new_board(["f2f3", "e7e5", "g2g4", "d8h4"])
    result = game.outcome(board)
    assert result == {"result": "0-1", "winner": "black", "termination": "checkmate"}
    exported = game.pgn(board, {"White": "Synthetic white", "Black": "Synthetic black"})
    replay = chess.pgn.read_game(io.StringIO(exported))
    assert replay.headers["Result"] == "0-1"
    assert replay.end().board().fen() == board.fen()


def test_stalemate_is_a_draw_not_a_loss():
    result = game.outcome(chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"))
    assert result == {"result": "1/2-1/2", "winner": None, "termination": "stalemate"}


def test_insufficient_material_is_a_draw():
    result = game.outcome(chess.Board("7k/8/8/8/8/8/8/K7 w - - 0 1"))
    assert result["termination"] == "insufficient_material"


def test_threefold_is_claimed_only_after_third_occurrence_exists():
    cycle = ["g1f3", "g8f6", "f3g1", "f6g8"]
    board = game.new_board(cycle + cycle[:3])
    assert game.observe(board)["draw"]["can_claim_threefold"] is True
    assert game.outcome(board) is None
    board.push_uci(cycle[3])
    assert game.observe(board)["draw"]["repetition_count"] == 3
    assert game.outcome(board)["termination"] == "threefold_repetition"


def test_fifty_move_draw_waits_until_current_clock_reaches_one_hundred():
    board = chess.Board("7k/8/8/8/8/8/8/KR6 w - - 99 51")
    assert game.observe(board)["draw"]["can_claim_fifty_moves"] is True
    assert game.outcome(board) is None
    board.push_uci("b1b2")
    assert game.outcome(board)["termination"] == "fifty_moves"


def test_automatic_seventyfive_move_draw_is_recognized():
    result = game.outcome(chess.Board("7k/8/8/8/8/8/8/KR6 w - - 150 76"))
    assert result["termination"] == "seventyfive_moves"


def test_automatic_fivefold_repetition_is_recognized():
    board = game.new_board(["g1f3", "g8f6", "f3g1", "f6g8"] * 4)
    assert game.outcome(board)["termination"] == "fivefold_repetition"


def test_checkmate_takes_precedence_over_fifty_move_draw():
    board = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 100 51")
    assert game.outcome(board)["termination"] == "checkmate"


def test_custom_initial_fen_is_retained_in_pgn_and_observation():
    board = chess.Board("7k/P7/8/8/8/8/8/7K w - - 0 1")
    initial = board.fen()
    board.push_uci("a7a8n")
    assert game.observe(board)["initial_fen"] == initial
    replay = chess.pgn.read_game(io.StringIO(game.pgn(board, {})))
    assert replay.headers["FEN"] == initial
    assert replay.end().board().fen() == board.fen()


def test_invalid_board_is_rejected_before_observation():
    with pytest.raises(ValueError):
        game.observe(chess.Board.empty())


def test_seeded_players_are_reproducible_and_always_legal():
    first, second = DeterministicPlayer(seed=42), DeterministicPlayer(seed=42)
    board = game.new_board([])
    for _ in range(30):
        if game.outcome(board):
            break
        obs = game.observe(board)
        left, right = first.choose(obs), second.choose(obs)
        assert left["move"] == right["move"]
        assert left["move"] in obs["legal_moves"]
        assert left["attempts"][0]["status"] == "ok"
        board.push_uci(left["move"])


def test_scripted_players_execute_known_mate_with_no_model_calls():
    white = DeterministicPlayer(script=["f2f3", "g2g4"])
    black = DeterministicPlayer(script=["e7e5", "d8h4"])
    board = game.new_board([])
    while game.outcome(board) is None:
        player = white if board.turn else black
        board.push_uci(player.choose(game.observe(board))["move"])
    assert game.outcome(board)["termination"] == "checkmate"


def test_bad_or_exhausted_script_fails_without_substitution():
    for script in (["e2e5"], []):
        with pytest.raises(PlayerError) as exc:
            DeterministicPlayer(script=script).choose(game.observe(game.new_board([])))
        assert exc.value.kind == "invalid_response"
        assert len(exc.value.attempts) == 1


@pytest.fixture
def fake_engine(tmp_path):
    """A local UCI protocol fixture, not a chess baseline or measured result."""
    script = tmp_path / "synthetic_uci.py"
    log = tmp_path / "commands.txt"
    script.write_text(textwrap.dedent('''\
        import sys
        from pathlib import Path
        log = Path(sys.argv[1])
        for raw in sys.stdin:
            command = raw.strip()
            with log.open("a") as f:
                f.write(command + "\\n")
            if command == "uci":
                print("id name SyntheticUCI 1.0")
                print("option name Threads type spin default 1 min 1 max 4")
                print("option name Hash type spin default 16 min 1 max 128")
                print("option name Skill Level type spin default 20 min 0 max 20")
                print("option name UCI_LimitStrength type check default false")
                print("option name MultiPV type spin default 1 min 1 max 4")
                print("option name Clear Hash type button")
                print("uciok", flush=True)
            elif command == "isready":
                print("readyok", flush=True)
            elif command.startswith("go"):
                print("bestmove e2e4", flush=True)
            elif command == "quit":
                break
    '''))
    return [sys.executable, str(script), str(log)], log


def test_engine_uses_requested_depth_and_clears_hash_each_turn(fake_engine):
    command, log = fake_engine
    with StockfishPlayer(command) as player:
        obs = game.observe(game.new_board([]))
        assert player.choose(obs)["move"] == "e2e4"
        assert player.choose(obs)["move"] == "e2e4"
        assert player.metadata["engine_id"]["name"] == "SyntheticUCI 1.0"
    commands = log.read_text().splitlines()
    assert "setoption name Skill Level value 0" in commands
    assert commands.count("setoption name Clear Hash") == 2
    assert commands.count("go depth 4") == 2
    assert "ucinewgame" in commands


def test_engine_missing_executable_is_infrastructure_failure():
    with pytest.raises(PlayerError) as exc:
        StockfishPlayer("/nonexistent/stockfish").choose(game.observe(game.new_board([])))
    assert exc.value.kind == "infrastructure"


def test_engine_watchdog_catches_unresponsive_process():
    player = StockfishPlayer([sys.executable, "-c", "import time; time.sleep(10)"], timeout_seconds=0.05)
    with pytest.raises(PlayerError) as exc:
        player.choose(game.observe(game.new_board([])))
    assert exc.value.kind == "timeout"
    player.close()


def test_engine_cannot_use_a_different_position_or_truncated_candidate_list(fake_engine):
    command, _ = fake_engine
    obs = game.observe(game.new_board([]))
    obs["legal_moves"] = obs["legal_moves"][:-1]
    with StockfishPlayer(command) as player:
        with pytest.raises(PlayerError) as exc:
            player.choose(obs)
    assert exc.value.kind == "infrastructure"


def test_engine_invalid_selection_fails_without_another_players_move(fake_engine):
    command, _ = fake_engine
    obs = game.observe(game.new_board(["d2d4"]))
    with StockfishPlayer(command) as player:
        with pytest.raises(PlayerError) as exc:
            player.choose(obs)
    assert exc.value.kind == "invalid_response"
