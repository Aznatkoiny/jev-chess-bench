"""Synthetic integration and durable-accounting checks; no measured Jev calls."""

import copy
import io
import math

import chess.pgn
import pytest

from chessbench.match import play_game
from chessbench.players import DeterministicPlayer, PlayerError
from chessbench.rating import score_of, summary, uncertainty, update
from chessbench.store import Store


def record(**overrides):
    return {"id": "game-1", "run_id": "run-1", "index": 0, "pair_index": 0,
            "opening_moves": [], "jev_color": "white", **overrides}


LIMITS = {"max_plies": 100, "game_seconds": 10}


def test_deterministic_match_completes_and_checkpoints_replayable_game():
    checkpoints = []
    result = play_game(record(), {
        "white": DeterministicPlayer(script=["f2f3", "g2g4"]),
        "black": DeterministicPlayer(script=["e7e5", "d8h4"]),
    }, LIMITS, lambda game: checkpoints.append(copy.deepcopy(game)))
    assert result["status"] == "completed"
    assert result["result"] == "0-1"
    assert [m["uci"] for m in result["moves"]] == ["f2f3", "e7e5", "g2g4", "d8h4"]
    assert len(result["attempts"]) == 2
    assert checkpoints[0]["status"] == "running"
    assert checkpoints[-1]["status"] == "completed"
    replay = chess.pgn.read_game(io.StringIO(result["pgn"]))
    assert replay.end().board().fen() == result["final_fen"]
    assert replay.headers["Result"] == "0-1"


def test_adapter_receives_game_facts_without_private_runner_or_engine_metadata():
    seen = []

    class Observer:
        def choose(self, observation):
            seen.append(copy.deepcopy(observation))
            return {"move": "e2e4", "latency_ms": 1, "attempts": []}

    result = play_game(record(engine_evaluation="SECRET ENGINE ADVICE", admin_token="SECRET TOKEN"),
                       {"white": Observer(), "black": DeterministicPlayer()},
                       {"max_plies": 1, "game_seconds": 10})
    assert len(seen[0]["legal_moves"]) == 20
    assert "engine_evaluation" not in seen[0]
    assert "admin_token" not in seen[0]
    assert result["status"] == "censored"


@pytest.mark.parametrize("kind", ["invalid_response", "timeout", "infrastructure", "budget"])
def test_failed_player_has_no_substitute_no_chess_score_and_preserved_attempt(kind):
    class Failure:
        closed = False

        def choose(self, observation):
            raise PlayerError(kind, "synthetic failure", attempts=[{"status": kind, "usage": {"inputTokens": 17}}])

        def close(self):
            self.closed = True

    failure = Failure()
    result = play_game(record(), {"white": failure, "black": DeterministicPlayer()}, LIMITS)
    assert result["status"] == "failed"
    assert result["result"] == "*"
    assert result["moves"] == []
    assert result["attempts"][0]["usage"]["inputTokens"] == 17
    assert score_of(result) is None
    assert failure.closed
    assert summary([result])["completed"] == 0


def test_ply_cap_is_censored_never_a_draw_or_rating_observation():
    result = play_game(record(), {"white": DeterministicPlayer(), "black": DeterministicPlayer()},
                       {"max_plies": 2, "game_seconds": 10})
    assert result["status"] == "censored"
    assert result["termination"] == "ply_limit"
    assert result["result"] == "*"
    totals = summary([result])
    assert totals["draws"] == totals["completed"] == totals["sample_size"] == 0
    assert totals["score_rate"] is None


def test_game_time_cap_rejects_a_move_returned_after_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("chessbench.match.time.monotonic", lambda: now[0])

    class SlowMate:
        def choose(self, observation):
            now[0] += 3
            return {"move": "d8h4", "latency_ms": 3000, "attempts": [{"status": "ok"}]}

    result = play_game(record(opening_moves=["f2f3", "e7e5", "g2g4"], jev_color="black"),
                       {"white": DeterministicPlayer(), "black": SlowMate()},
                       {"max_plies": 100, "game_seconds": 2})
    assert result["status"] == "censored"
    assert result["termination"] == "game_time_limit"
    assert result["result"] == "*"
    assert result["moves"] == []
    assert result["attempts"] == [{"status": "ok"}]


def test_adapter_cannot_bypass_rules_by_mutating_its_candidate_list():
    class MutatingAdapter:
        def choose(self, observation):
            observation["legal_moves"].append("e2e5")
            return {"move": "e2e5", "latency_ms": 1, "attempts": []}

    result = play_game(record(), {"white": MutatingAdapter(), "black": DeterministicPlayer()}, LIMITS)
    assert result["status"] == "failed"
    assert result["failure_kind"] == "invalid_response"
    assert result["moves"] == []


def test_reservations_survive_reopening_and_enforce_run_and_lifetime_caps(tmp_path):
    path = tmp_path / "results.sqlite"
    store = Store(path)
    store.reserve("a", "a1", .002, run_limit=.004, lifetime_limit=.006)
    store.db.close()
    store = Store(path)
    assert store.reserved("a") == pytest.approx(.002)
    store.reserve("a", "a1", .002, run_limit=.004, lifetime_limit=.006)
    with pytest.raises(PlayerError, match="ceiling"):
        store.reserve("a", "a2", .002, run_limit=.004, lifetime_limit=.006)
    store.reserve("b", "b1", .002, run_limit=.004, lifetime_limit=.006)
    with pytest.raises(PlayerError, match="ceiling"):
        store.reserve("b", "b1", .002, run_limit=.004, lifetime_limit=.006)
    assert store.reserved() == pytest.approx(.006)
    assert store.db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 3
    store.db.close()


@pytest.mark.parametrize("amount", [-1, 0, math.nan, math.inf])
def test_invalid_reservations_cannot_create_budget_credit(tmp_path, amount):
    store = Store(tmp_path / "results.sqlite")
    with pytest.raises((ValueError, PlayerError)):
        store.reserve("a", "a1", amount, run_limit=1)
    assert store.reserved() == 0
    store.db.close()


def test_run_snapshots_and_publication_sequences_are_durable(tmp_path):
    path = tmp_path / "results.sqlite"
    store = Store(path)
    run = {"id": "r", "config": {"model": "synthetic"}, "games": []}
    store.save(run)
    assert store.sequence("r") == 1
    run["games"].append({"id": "g", "status": "running"})
    store.save(run)
    store.db.close()
    reopened = Store(path)
    assert reopened.load("r") == run
    assert reopened.sequence("r") == 2
    reopened.db.close()


def test_elo_uses_documented_anchor_and_is_idempotent_after_reopen(tmp_path):
    path = tmp_path / "results.sqlite"
    store = Store(path)
    store.rate("g1", "pool-a", 1)
    assert store.history("pool-a")[0]["rating"] == 1012
    store.db.close()
    store = Store(path)
    store.rate("g1", "pool-a", 1)
    store.rate("g2", "pool-a", 0)
    history = store.history("pool-a")
    assert len(history) == 2
    assert history[-1]["rating"] == pytest.approx(update(1012, 0))
    assert [row["n"] for row in history] == [1, 2]
    assert store.history("pool-b") == []
    store.db.close()


def paired_games(results):
    return [record(id=f"g{i}", index=i, pair_index=i // 2,
                   status="completed", result=result,
                   jev_color="white" if i % 2 == 0 else "black")
            for i, result in enumerate(results)]


def test_uncertainty_counts_complete_color_pairs_and_keeps_boundary_unbounded():
    games = paired_games(["0-1", "1-0", "0-1", "1-0"])
    interval = uncertainty(games)
    assert interval["pairs"] == 2
    assert interval["score_low"] == 0
    assert interval["low"] is None
    assert interval["score_high"] > .9
    assert interval["high"] > 1000
    assert uncertainty(games[:1])["pairs"] == 0


def test_uncertainty_does_not_call_two_same_color_games_a_pair():
    games = paired_games(["1-0", "1-0"])
    games[1]["jev_color"] = "white"
    assert uncertainty(games)["pairs"] == 0


def test_summary_separates_chess_results_failures_and_cost_provenance():
    games = paired_games(["1-0", "1/2-1/2"])
    games += [record(id="failed", index=2, status="failed", result="*", failure_kind="infrastructure")]
    games[0].update(attempts=[
        {"status": "invalid_response", "usage": {"inputTokens": 20}, "estimated_cost_usd": .00001},
        {"status": "ok", "usage": {"inputTokens": 30, "outputTokens": 4}, "observed_cost_usd": .00002},
    ], moves=[{"player": "jev", "latency_ms": 100}, {"player": "opponent", "latency_ms": 1}])
    totals = summary(games, reserved=.004)
    assert (totals["wins"], totals["draws"], totals["losses"], totals["failed"]) == (1, 1, 0, 1)
    assert totals["score_rate"] == .75
    assert totals["invalid_response_rate"] == .5
    assert totals["input_tokens"] == 50 and totals["output_tokens"] == 4
    assert totals["observed_cost_usd"] == .00002
    assert totals["cost_observed_attempts"] == 1
    assert totals["estimated_cost_usd"] == .00001
    assert totals["reserved_cost_usd"] == .004
    assert totals["median_latency_ms"] == 100
