"""Offline worker lifecycle tests. No provider, network, or engine inference."""
import copy

import pytest

from chessbench import worker as worker_module
from chessbench.players import PlayerError
from chessbench.store import Store
from chessbench.worker import CONFIG, Worker, pool_hash, public_snapshot


class FakeHosted:
    def __init__(self):
        self.calls = []

    def call(self, payload=None):
        self.calls.append(copy.deepcopy(payload))
        return {"ok": True, "jobs": []}


@pytest.fixture
def offline_worker(tmp_path):
    executable = tmp_path / "synthetic-engine-not-executable"
    executable.write_bytes(b"Synthetic binary hash fixture; never executed")
    store = Store(tmp_path / "benchmark.sqlite")
    hosted = FakeHosted()
    worker = Worker(store, hosted, tmp_path, str(executable))
    yield worker, store, hosted
    store.db.close()


def job(kind="smoke", identifier="synthetic-run"):
    return {"id": identifier, "kind": kind, "status": "queued", "games": [],
            "config": {**copy.deepcopy(CONFIG), **copy.deepcopy(CONFIG[kind])},
            "rating_history": [], "summary": None}


def forbid_inference(monkeypatch):
    def forbidden(*_, **__):
        raise AssertionError("Synthetic worker test attempted inference")

    monkeypatch.setattr(worker_module, "JevPlayer", forbidden)
    monkeypatch.setattr(worker_module, "StockfishPlayer", forbidden)
    monkeypatch.setattr(worker_module, "play_game", forbidden)


def test_public_snapshot_removes_raw_and_request_without_mutating_durable_run():
    run = {"id": "run", "games": [{"id": "game", "attempts": [{
        "status": "ok", "request": {"state": "full game"},
        "raw": {"answers": "provider response"}, "usage": {"inputTokens": 30},
        "observed_cost_usd": .00001, "generation_id": "gen-synthetic",
    }]}]}
    public = public_snapshot(run)
    assert "request" not in public["games"][0]["attempts"][0]
    assert "raw" not in public["games"][0]["attempts"][0]
    assert public["games"][0]["attempts"][0]["usage"] == {"inputTokens": 30}
    assert run["games"][0]["attempts"][0]["raw"] == {"answers": "provider response"}


@pytest.mark.parametrize("change", ["model", "price", "games", "kind"])
def test_queued_config_changes_are_rejected_before_any_inference(offline_worker, monkeypatch, change):
    worker, store, hosted = offline_worker
    queued = job()
    if change == "model":
        queued["config"]["model_id"] = "other/model"
    elif change == "price":
        queued["config"]["inference"]["input_usd_per_million"] = 0
    elif change == "games":
        queued["config"]["game_count"] = 100
    else:
        queued["kind"] = "arbitrary"
    forbid_inference(monkeypatch)
    worker.execute(queued)
    saved = store.load(queued["id"])
    assert saved["status"] == "stopped"
    assert "configuration" in saved["stop_reason"]
    assert saved["games"] == []
    assert store.reserved() == 0
    assert any(call["action"] == "snapshot" for call in hosted.calls)


def test_restart_stops_interrupted_game_without_replaying_paid_calls(offline_worker, monkeypatch):
    worker, store, hosted = offline_worker
    queued = job()
    interrupted = copy.deepcopy(queued)
    interrupted.update(status="running", pool_id=pool_hash(CONFIG), games=[{
        "id": "game-0", "run_id": queued["id"], "index": 0,
        "pair_index": 0, "jev_color": "white", "status": "running", "result": "*",
        "moves": [], "pgn": "[Result \"*\"]\n\n*", "attempts": [{
            "status": "ok", "request": {"state": "preserve me"},
            "raw": {"answers": "original model response"},
            "usage": {"inputTokens": 12}, "reserved_cost_usd": .002,
        }],
    }])
    store.save(interrupted)
    store.reserve(queued["id"], "game-0", .002, run_limit=.6)
    forbid_inference(monkeypatch)
    worker.execute(queued)
    saved = store.load(queued["id"])
    assert saved["status"] == "stopped"
    assert saved["games"][0]["status"] == "failed"
    assert saved["games"][0]["failure_kind"] == "worker_interrupted"
    assert saved["games"][0]["attempts"][0]["raw"]["answers"] == "original model response"
    assert store.reserved(queued["id"]) == pytest.approx(.002)
    assert store.history(pool_hash(CONFIG)) == []
    worker.execute(queued)
    assert store.reserved(queued["id"]) == pytest.approx(.002)


@pytest.mark.parametrize("status", ["completed", "failed", "censored", "stopped"])
def test_terminal_run_never_executes_again(offline_worker, monkeypatch, status):
    worker, store, hosted = offline_worker
    queued = job()
    store.save({**queued, "status": status})
    forbid_inference(monkeypatch)
    worker.execute(queued)
    assert store.load(queued["id"])["status"] == status
    assert store.reserved() == 0


def test_exhausted_lifetime_budget_stops_before_gateway_transport(offline_worker, monkeypatch):
    worker, store, hosted = offline_worker
    store.reserve("earlier-run", "earlier-game", 5, run_limit=5, lifetime_limit=5)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "synthetic-key-no-network")

    def forbidden_transport(*_, **__):
        raise AssertionError("Budget failure must precede Gateway transport")

    monkeypatch.setattr("chessbench.jev.request_gateway", forbidden_transport)

    class IdleEngine:
        def __init__(self, *_, **__):
            self.metadata = {"kind": "synthetic fixture"}

        def choose(self, observation):
            raise AssertionError("Jev's first turn should stop at the spending ceiling")

        def close(self):
            pass

    monkeypatch.setattr(worker_module, "StockfishPlayer", IdleEngine)
    queued = job()
    worker.execute(queued)
    saved = store.load(queued["id"])
    assert saved["status"] == "stopped"
    assert saved["stop_reason"] == "budget"
    assert len(saved["games"]) == 1
    assert saved["games"][0]["failure_kind"] == "budget"
    assert saved["games"][0]["moves"] == []
    assert saved["games"][0]["attempts"] == []
    assert store.reserved(queued["id"]) == 0
    assert store.reserved() == 5
    actions = [call["action"] for call in hosted.calls]
    assert actions.index("snapshot") < actions.index("archive")


def test_recorded_plan_is_published_before_starting_match(offline_worker, monkeypatch):
    worker, store, hosted = offline_worker
    captured = []

    class FixturePlayer:
        def __init__(self, *_, **__):
            self.metadata = {"kind": "synthetic"}

    def fake_match(game, players, limits, checkpoint):
        snapshots = [call for call in hosted.calls if call["action"] == "snapshot"]
        assert snapshots
        assert snapshots[0]["run"]["config"] == job()["config"]
        assert snapshots[0]["run"]["status"] == "running"
        assert store.load(game["run_id"])["config"] == job()["config"]
        captured.append((game["jev_color"], copy.deepcopy(game["opening_moves"])))
        game.update(status="completed", result="1/2-1/2", moves=[], attempts=[],
                    termination="synthetic_test_draw", pgn="[Result \"1/2-1/2\"]\n\n1/2-1/2")
        checkpoint(game)

    monkeypatch.setattr(worker_module, "JevPlayer", FixturePlayer)
    monkeypatch.setattr(worker_module, "StockfishPlayer", FixturePlayer)
    monkeypatch.setattr(worker_module, "play_game", fake_match)
    worker.execute(job())
    assert captured == [("white", []), ("black", [])]
    assert store.load("synthetic-run")["status"] == "completed"
    assert store.history(pool_hash(CONFIG)) == []  # Smoke never updates Elo.
    assert store.reserved() == 0
