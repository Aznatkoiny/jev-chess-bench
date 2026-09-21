"""Synthetic timeline tests only; these are not model benchmark results."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("export_recording", Path(__file__).resolve().parents[1] / "scripts" / "export-recording.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def synthetic_timeline(games=9):
    events = []
    for index in range(games):
        start = index * 18 + 5
        events.append({"seconds": start, "gameIndex": index, "ply": 0, "phase": "intro"})
        events.extend({"seconds": start + 1 + (ply - 1) * .75, "gameIndex": index,
                       "ply": ply, "phase": "playing"} for ply in range(1, 21))
        events.append({"seconds": start + 16, "gameIndex": index, "ply": 20, "phase": "game_end"})
    events.append({"seconds": games * 18 + 9, "gameIndex": games - 1,
                   "ply": 20, "phase": "finished", "displayedGames": games})
    return events


def test_nine_intact_highlight_excerpts_keep_original_timing():
    ranges = exporter.edit_ranges(synthetic_timeline(), 174)
    assert ranges["full"]["start"] == 5
    assert ranges["full"]["end"] == pytest.approx(173.8)
    assert len(ranges["highlights"]) == 9
    assert sum(clip["duration"] for clip in ranges["highlights"]) < 140
    assert ranges["last_plies_selected"] == 10
    for index, clip in enumerate(ranges["highlights"]):
        assert clip["game_index"] == index
        assert clip["first_ply"] == 11
        assert clip["last_ply"] == 20
        assert clip["start"] == index * 18 + 13.5
        assert clip["duration"] == clip["end"] - clip["start"]


def test_tight_time_limit_uses_fewer_plies_without_acceleration():
    ranges = exporter.edit_ranges(synthetic_timeline(), 174, maximum_seconds=70)
    assert ranges["last_plies_selected"] < 10
    assert sum(clip["duration"] for clip in ranges["highlights"]) <= 69
    for clip in ranges["highlights"]:
        assert clip["duration"] == clip["end"] - clip["start"]


def test_missing_or_unfinished_games_are_rejected():
    with pytest.raises(ValueError, match="all 9 games"):
        exporter.edit_ranges(synthetic_timeline(8), 170)
    with pytest.raises(ValueError, match="finished event"):
        exporter.edit_ranges(synthetic_timeline()[:-1], 174)
    with pytest.raises(ValueError, match="game-end event"):
        exporter.edit_ranges([e for e in synthetic_timeline() if not (e["gameIndex"] == 3 and e["phase"] == "game_end")], 174)


def test_label_is_a_dependency_free_png(tmp_path):
    path = tmp_path / "label.png"
    exporter.banner_png(path, 1280, 9)
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
