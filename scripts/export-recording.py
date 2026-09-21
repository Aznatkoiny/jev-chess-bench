#!/usr/bin/env python3
"""Export an actual browser recording, preserving the recorded move timing.

No model calls, browser actions, network access, or third-party Python packages.
Requires ffmpeg/ffprobe with libx264. Output includes an auditable edit list.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zlib


def probe(path, executable):
    result = subprocess.run([executable, "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_name,codec_type,width,height,pix_fmt,r_frame_rate",
        "-of", "json", str(path)], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def edit_ranges(timeline, duration, expected_games=9, last_plies=10,
                maximum_seconds=140, offset=0):
    """Select intact excerpts; never synthesize positions or accelerate moves."""
    events = sorted(timeline, key=lambda event: event["seconds"])
    intros = [e for e in events if e.get("phase") == "intro"]
    finished = [e for e in events if e.get("phase") == "finished"]
    if not intros or not finished:
        raise ValueError("Capture must contain a first intro and a finished event")
    if finished[-1].get("displayedGames") != expected_games:
        raise ValueError(f"Capture did not display all {expected_games} games")
    def timestamp(event):
        return min(duration, max(0, float(event["seconds"]) + offset))
    full_start = timestamp(intros[0])
    full_end = min(duration, timestamp(finished[-1]) + 2.8)
    full = {"start": full_start, "end": full_end, "duration": full_end - full_start}
    if full["duration"] <= 0:
        raise ValueError("Capture and timeline have no overlapping finished recording")
    for count in range(last_plies, 0, -1):
        clips = []
        for index in range(expected_games):
            game_events = [e for e in events if e.get("gameIndex") == index]
            ending = next((e for e in game_events if e.get("phase") == "game_end"), None)
            if ending is None:
                raise ValueError(f"No game-end event for game {index + 1}")
            plays = [e for e in game_events if e.get("phase") == "playing"
                     and e.get("ply", 0) > 0 and e["seconds"] <= ending["seconds"]]
            if not plays:
                raise ValueError(f"Game {index + 1} has no recorded moves to highlight")
            final_ply = max(e["ply"] for e in plays)
            first_ply = max(1, final_ply - count + 1)
            first = next(e for e in plays if e["ply"] >= first_ply)
            start = timestamp(first)
            if index == expected_games - 1:
                end = full_end
            else:
                next_intro = next((e for e in intros if e.get("gameIndex") == index + 1), None)
                if next_intro is None:
                    raise ValueError(f"No transition to game {index + 2}")
                # Stop before the next game's title appears. Preserve up to 2 s
                # of the outcome display, including the last held board position.
                end = min(timestamp(next_intro), timestamp(ending) + 2)
            if end <= start:
                raise ValueError("A selected excerpt falls outside the source recording")
            clips.append({"game_index": index, "game_number": index + 1,
                          "first_ply": first_ply, "last_ply": final_ply,
                          "start": start, "end": end, "duration": end - start})
        # Leave one second for frame-grid rounding during concatenation.
        if sum(clip["duration"] for clip in clips) <= maximum_seconds - 1:
            return {"full": full, "highlights": clips, "last_plies_selected": count}
    raise ValueError("Nine intact endings exceed the requested highlight time limit; no speed-up applied")


_FONT = {
    "A": [14,17,17,31,17,17,17], "B": [30,17,17,30,17,17,30],
    "C": [14,17,16,16,16,17,14], "D": [30,17,17,17,17,17,30],
    "E": [31,16,16,30,16,16,31], "F": [31,16,16,30,16,16,16],
    "G": [14,17,16,23,17,17,15], "H": [17,17,17,31,17,17,17],
    "I": [14,4,4,4,4,4,14], "J": [7,2,2,2,18,18,12],
    "K": [17,18,20,24,20,18,17], "L": [16,16,16,16,16,16,31],
    "M": [17,27,21,21,17,17,17], "N": [17,25,21,19,17,17,17],
    "O": [14,17,17,17,17,17,14], "P": [30,17,17,30,16,16,16],
    "Q": [14,17,17,17,21,18,13], "R": [30,17,17,30,20,18,17],
    "S": [15,16,16,14,1,1,30], "T": [31,4,4,4,4,4,4],
    "U": [17,17,17,17,17,17,14], "V": [17,17,17,17,17,10,4],
    "W": [17,17,17,21,21,21,10], "X": [17,17,10,4,10,17,17],
    "Y": [17,17,10,4,4,4,4], "Z": [31,1,2,4,8,16,31],
    "0": [14,17,19,21,25,17,14], "1": [4,12,4,4,4,4,14],
    "2": [14,17,1,2,4,8,31], "3": [30,1,1,14,1,1,30],
    "4": [2,6,10,18,31,2,2], "5": [31,16,16,30,1,1,30],
    "6": [14,16,16,30,17,17,14], "7": [31,1,2,4,8,8,8],
    "8": [14,17,17,14,17,17,14], "9": [14,17,17,15,1,1,14],
    "|": [4,4,4,4,4,4,4], " ": [0,0,0,0,0,0,0],
}


def banner_png(path, width, games):
    """Readable 21px bitmap label in a separate 40px strip; no image dependencies."""
    height, scale = 40, 3
    label = f"HIGHLIGHTS | FINAL MOVES FROM {games} REAL GAMES"
    label_width = len(label) * 6 * scale - scale
    if label_width > width - 20:
        raise ValueError("Video is too narrow for the highlight label")
    pixels = bytearray(bytes((13, 17, 23)) * width * height)
    left, top = (width - label_width) // 2, (height - 7 * scale) // 2
    for char_index, char in enumerate(label):
        for row, bitmap in enumerate(_FONT[char]):
            for col in range(5):
                if bitmap & (1 << (4 - col)):
                    for dy in range(scale):
                        for dx in range(scale):
                            pixel = ((top + row * scale + dy) * width + left
                                     + char_index * 6 * scale + col * scale + dx) * 3
                            pixels[pixel:pixel + 3] = bytes((226, 232, 240))
    raw = b"".join(b"\x00" + pixels[row * width * 3:(row + 1) * width * 3]
                   for row in range(height))
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def encode(source, output, clips, executable, banner=None, maximum_bytes=512_000_000):
    duration = sum(clip["duration"] for clip in clips)
    # Constrain peak bitrate below the file budget with 10% mux/rounding margin.
    max_kbps = min(4000, math.floor(maximum_bytes * 8 * .9 / duration / 1000) - 128)
    if max_kbps < 300:
        raise ValueError("Recording is too long for the requested file-size budget")
    command = [executable, "-hide_banner", "-loglevel", "error", "-y"]
    filters = []
    for index, clip in enumerate(clips):
        command += ["-ss", f'{clip["start"]:.6f}', "-t", f'{clip["duration"]:.6f}', "-i", str(source)]
        filters.append(f"[{index}:v]setpts=PTS-STARTPTS,fps=30,setsar=1[v{index}]")
    if len(clips) == 1:
        joined = "v0"
    else:
        filters.append("".join(f"[v{i}]" for i in range(len(clips)))
                       + f"concat=n={len(clips)}:v=1:a=0[joined]")
        joined = "joined"
    audio_index = len(clips)
    if banner:
        command += ["-loop", "1", "-i", str(banner)]
        filters.append(f"[{joined}]pad=iw:ih+40:0:40:color=0x0d1117[padded]")
        filters.append(f"[padded][{len(clips)}:v]overlay=0:0:shortest=1[final]")
        joined = "final"
        audio_index += 1
    command += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-filter_complex_threads", "2", "-filter_complex", ";".join(filters),
                "-map", f"[{joined}]", "-map", f"{audio_index}:a", "-c:v", "libx264",
                "-preset", "fast", "-crf", "20", "-profile:v", "high", "-level:v", "4.1",
                "-pix_fmt", "yuv420p", "-threads", "4", "-maxrate", f"{max_kbps}k",
                "-bufsize", f"{max_kbps * 2}k", "-c:a", "aac", "-b:a", "128k",
                "-shortest", "-t", f"{duration:.6f}", "-movflags", "+faststart", str(output)]
    subprocess.run(command, check=True)
    if output.stat().st_size > maximum_bytes:
        raise ValueError(f"Export exceeded its {maximum_bytes}-byte size budget")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path("output/video/content-nine"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--timeline", type=Path)
    parser.add_argument("--games", type=int, default=9)
    parser.add_argument("--last-plies", type=int, default=10)
    parser.add_argument("--max-highlight-seconds", type=float, default=140)
    parser.add_argument("--timeline-offset", type=float, default=0,
                        help="Seconds to add to timeline times if source-video alignment was measured")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg")
    parser.add_argument("--ffprobe", default=shutil.which("ffprobe") or "/usr/local/bin/ffprobe")
    args = parser.parse_args()
    if args.games < 1 or args.last_plies < 1 or args.max_highlight_seconds < 2:
        parser.error("Games, plies and duration limits must be positive")
    directory = args.directory.resolve()
    source = (args.source or directory / "jev-nine-games-capture.webm").resolve()
    timeline_path = args.timeline or directory / "capture-timeline.json"
    recording = json.loads(timeline_path.read_text())
    if recording.get("errors"):
        raise ValueError("Capture reported browser errors; inspect before publishing")
    source_info = probe(source, args.ffprobe)
    duration = float(source_info["format"]["duration"])
    video = next(stream for stream in source_info["streams"] if stream["codec_type"] == "video")
    ranges = edit_ranges(recording["timeline"], duration, args.games, args.last_plies,
                         args.max_highlight_seconds, args.timeline_offset)
    directory.mkdir(parents=True, exist_ok=True)
    full = directory / "jev-nine-games-full.mp4"
    highlights = directory / "jev-nine-games-tweet-highlights.mp4"
    print(json.dumps({"event": "exporting", "full_seconds": ranges["full"]["duration"],
                      "highlight_seconds": sum(c["duration"] for c in ranges["highlights"])}), flush=True)
    encode(source, full, [ranges["full"]], args.ffmpeg)
    with tempfile.TemporaryDirectory(prefix="jev-recording-") as temporary:
        banner = Path(temporary) / "highlights-label.png"
        banner_png(banner, video["width"], args.games)
        encode(source, highlights, ranges["highlights"], args.ffmpeg, banner)
    full_info, highlights_info = probe(full, args.ffprobe), probe(highlights, args.ffprobe)
    if float(highlights_info["format"]["duration"]) > args.max_highlight_seconds:
        raise ValueError("Encoded highlights exceed the requested time limit")
    for info in (full_info, highlights_info):
        stream = next(s for s in info["streams"] if s["codec_type"] == "video")
        if stream["codec_name"] != "h264" or stream["pix_fmt"] != "yuv420p" or stream["r_frame_rate"] != "30/1":
            raise ValueError("Export codec verification failed")
    metadata = {"run_id": recording["run_id"], "source": str(source),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "capture_start": recording.get("capture_start"),
                "recording_type": "Actual browser viewport capture; model moves are displayed at the recorded pace",
                "editing": "Full: opening wait trimmed. Highlights: intact final-move excerpts from every game, with a separate label above the viewport. No acceleration or generated chess positions.",
                "timeline_offset_seconds": args.timeline_offset,
                "audio": "Silent AAC stereo; no narration recorded",
                "frame_rate": 30, "source_probe": source_info, "ranges": ranges,
                "outputs": {"full": {"path": str(full), "probe": full_info},
                            "highlights": {"path": str(highlights), "probe": highlights_info}}}
    metadata_path = directory / "export-metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"event": "exported", "full": str(full), "highlights": str(highlights),
                      "metadata": str(metadata_path)}), flush=True)


if __name__ == "__main__":
    main()
