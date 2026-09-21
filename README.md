# Jev Chess Benchmark

A chess benchmark with a public match viewer, PGN replay and export, retained model responses, and provisional ratings. Jev selects its own legal moves through **Vercel AI Gateway**. Its opponent is **Stockfish 16**, an adjustable CPU chess engine with NNUE evaluation. Stockfish never supplies recommendations or evaluations to Jev.

Verified publication: [public app](https://jev-chess-bench.vercel.app) · [open-source repository](https://github.com/Aznatkoiny/jev-chess-bench). **The public app and real Gateway benchmark are verified.** Jev scored **0 wins, 0 draws, 8 losses** in the tournament; provisional relative Elo **914.7**. Read the [measured report and limitations](results/REPORT.md), including the separately retained diagnostic smoke, exact costs, raw records and verification evidence.

## Experiment

[config.json](config.json) records the protocol before inference. [Methodology](docs/methodology.md) explains scoring, exclusions, uncertainty and provenance. [Jev interface](docs/jev-interface.md) records the verified evaluation API, complete legal candidate set and bounded failure policy.

| Stage | Configuration |
| --- | --- |
| Rules and harness | Synthetic deterministic players; no paid calls or measured Jev scores |
| Gateway smoke | 2 games, both colors from the initial position; $0.60 reservation ceiling; unrated |
| Tournament | 8 games, 4 paired positions with colors swapped; $2.00 reservation ceiling |
| Content recording | 9 unrated games, 4 color pairs plus an initial-position game with Jev White; $2.50 reservation ceiling |
| Jev | `typesafe-ai/jev`, `POST https://ai-gateway.vercel.sh/v1/evaluate` |
| Opponent | Stockfish 16, Ubuntu `16-1build1` arm64, Skill Level 0, depth 4, 1 thread, 16 MiB hash |
| Turn policy | Jev: 2 attempts maximum, 10 seconds each, 2-second retry delay; engine: 2-second watchdog |
| Other limits | 160 played plies after the opening, 1,200 seconds/game, 7,200 seconds/run; stop at 2 infrastructure failures or spending exhaustion |
| Cost protection | $0.002 durable reservation before every attempted inference, including retries; $5 cumulative worker reservation ceiling |
| Rating | Start at 1000; fixed opponent anchor 1000; K=24; completed tournament chess results only |

The rating is **provisional and relative to this benchmark's opponent pool**. It is not FIDE, Chess.com or Lichess Elo. Skill Level 0 is an engine setting, not a human Elo calibration. The paired performance interval and online Elo history measure different things; small samples cannot establish a precise rating.

## Recording real games

The recorded [nine-game content run](results/dc99df96-7d9b-4c4d-a39d-f3d8b5fb0c58/REPORT.md) produced eight checkmate losses and one failed game. All 394 played moves were captured; the full video is 5:36 and the labeled highlights are 1:34. This run is separate from the rated tournament.

The [recording view](https://jev-chess-bench.vercel.app/record.html) plays every received move in order at 0.75 seconds per ply. It buffers batched updates and switches from LIVE CAPTURE to RECORDED RUN when the worker finishes. The actual Jev decision latency is shown separately. Content games retain their raw results but never change Elo.

With Playwright and Chrome installed, start capture before queuing exactly one new nine-game run:

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/playwright BROWSER_CHANNEL=chrome \
BENCH_OPERATOR_TOKEN_FILE=/private/path/to/operator-token \
BENCH_VIDEO_DIR=output/video/content-nine node scripts/record-content.cjs
```

The controller reads the operator token only in Node, keeps it out of the browser, and never automatically retries a queue request. It saves the run plan, an actual 1280×720 browser video, a timeline, and verification that every recorded FEN was displayed in order. Set `BENCH_EXISTING_RUN_ID` to capture a previous run without paid inference. Manual viewing uses `/record.html?run=RUN_ID&autoplay=1&pace=750`; Space pauses playback.

After capture, `python3 scripts/export-recording.py output/video/content-nine` uses FFmpeg to produce a full H.264 MP4 and a labeled highlights MP4 under 140 seconds. Highlights select the final moves from every game at the captured pace. The exporter retains exact edit ranges and source hashes in `export-metadata.json`. A failed game remains a failure in both videos; it is not replaced by another paid game or counted as a chess loss.

## Local validation

Use Python 3.12+ and Node.js 24. The pinned `chess==1.11.2` package is the importable library maintained by the python-chess project; the `python-chess==1.999` package is a compatibility metapackage and is unnecessary.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
npm ci
npm test
npm run build
npm run dev
```

The development viewer opens at [localhost:4328](http://127.0.0.1:4328). Public data APIs need a real Vercel Blob store and server environment variables; a local static page by itself is not an end-to-end deployment. Python tests inject synthetic players/transports, so they do not require a Gateway key or consume inference budget.

The checks cover special moves, draw rules and checkmate precedence, complete observations, legal move validation, deterministic finished games, PGN round trips, deadline/censoring behavior, failed moves without substitution, durable spending limits, idempotent rating history, paired uncertainty and credential redaction. The initial validation gate passed 70 automated checks and a native Stockfish game against a seeded synthetic player on Spark, ending in checkmate after 58 plies. These are game/harness validation, not Jev performance results. The synthetic UCI fixture is a protocol test, not a measured chess opponent.

## Hosted operation

Vercel serves the browser and short Node API requests. A single persistent Linux worker runs the matches on the DGX Spark and polls the public app over outbound HTTPS. This avoids placing a long match inside a Vercel function. Stockfish uses a CPU core; Spark's value here is durable worker hosting, not GPU acceleration. Jev inference still goes through Vercel AI Gateway.

The worker saves progress and permanent spending reservations in SQLite/WAL before publishing. Private Vercel Blob stores queued jobs, numbered snapshots and raw per-game archives. Read APIs deliberately expose benchmark records and PGNs; private storage does not make the published chess records confidential. Credentials are absent from those records.

Configure Vercel server variables:

| Variable | Purpose |
| --- | --- |
| `BLOB_READ_WRITE_TOKEN` | Private Blob store access; server only |
| `ADMIN_TOKEN` | Operator authorization to queue paid runs; at least 32 characters |
| `WORKER_TOKEN` | Dedicated worker authentication; at least 32 characters and different from the operator token |

Configure the worker's private `.env` from [.env.example](.env.example), or inject equivalent process environment variables:

| Variable | Purpose |
| --- | --- |
| `AI_GATEWAY_API_KEY` | Gateway inference key; worker only |
| `BENCH_APP_URL` | Verified deployed HTTPS app URL |
| `WORKER_TOKEN` | Same dedicated worker token configured on Vercel |
| `STOCKFISH_PATH` | Full executable path, normally `/usr/games/stockfish` |
| `BENCH_DATA_DIR` | Durable writable data directory; keep it across worker restarts and redeploys |

On Ubuntu 24.04 arm64, reproduce the selected engine package and record its identity:

```sh
sudo apt-get install stockfish=16-1build1
dpkg-query -W stockfish
sha256sum /usr/games/stockfish
git rev-parse HEAD > REVISION
.venv/bin/python -m chessbench.worker
```

Run the worker under the host's persistent service manager for unattended use. For a single poll cycle, use `.venv/bin/python -m chessbench.worker --once`. A filesystem lock permits one worker per data directory. Keep the same SQLite database to retain the lifetime spending ceiling and rating history. A crash during inference stops the interrupted run on restart; it does not replay an ambiguously billed request. Queue a new run after investigating the retained record.

The app's worker status and a completed hosted smoke match verify the Spark-to-Vercel path. SSH access alone does not verify this connection. Keep worker credentials off the public frontend, browser storage and source control. The execution form uses the operator's supplied token only for an authorized request.

## Rerun

1. Recheck the current model catalog and per-token price against the saved protocol. Verify the selected engine binary/version. Run the synthetic checks before changing adapters or game rules.
2. Start the durable worker with the server configuration above. Verify that the app reports a recent heartbeat.
3. In the app's operator controls, choose **Gateway smoke** and supply the operator token. Inspect the actual Gateway responses and complete game records.
4. Choose **Tournament** only after smoke verification. The server accepts the frozen run kinds; clients cannot choose larger budgets, custom model IDs or arbitrary inference payloads.
5. Review the run's results, failures, costs, paired interval and PGNs. Reload the app and download a raw game record to verify persistence.

The equivalent operator API is `POST /api/runs`, JSON `{"kind":"smoke"}` or `{"kind":"tournament"}`, with an `Authorization: Bearer ...` header. The provided helper reads `ADMIN_TOKEN` from the environment without placing its value in command-line arguments:

```sh
.venv/bin/python scripts/enqueue.py smoke --url "$BENCH_APP_URL"
# After smoke verification:
.venv/bin/python scripts/enqueue.py tournament --url "$BENCH_APP_URL"
```

Alternatively, pass `--token-file /private/path/to/operator-token` to read a protected token file. The helper prints the queued run ID and frozen configuration, never the token.

Public endpoints are `GET /api/runs`, `GET /api/runs?id=RUN_ID`, `GET /api/artifact?id=RUN_ID&game=0`, and `GET /api/pgn?id=RUN_ID&game=0`. Game indexes in URLs start at zero. Raw artifacts contain request states and responses, usage and timing metadata, plus full game records. The worker also retains `archives/RUN_ID/game-N.json`, `game-N.pgn` and `run.json` below `BENCH_DATA_DIR`.

Changing model behavior, opponent settings, openings, limits or rating rules creates a different comparison. Update and freeze the config, change the protocol version when adapter semantics change, rerun validation, redeploy both components and preserve the earlier archives. Gateway's Jev alias does not provide immutable upstream weights; record timestamps and response metadata rather than promising byte-for-byte model reproducibility.

## Code boundaries and future games

`chessbench/game.py` owns rules and player-visible observations; `players.py` and `jev.py` own adapters; `match.py` executes one match; `rating.py` evaluates chess results; `store.py` persists state and accounting; `worker.py` coordinates hosted execution. `public/` contains the viewer, and `api/` contains the public and protected endpoints.

Only chess is implemented. A future poker game would need a new game-specific state and an observation function parameterized by the acting player, which omits opponents' private cards. The match executor must never pass that full internal state into an adapter or public snapshot. Poker should define its own payoffs and uncertainty treatment instead of reusing chess W/D/L or Elo blindly. No unused poker framework is included.

## License

This application's source is available under **GPL-3.0-or-later**, compatible with its python-chess dependency. See [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md) for dependencies and upstream source links. The public repository includes the harness, viewer, tests, and raw measured games. Jev is accessed through Vercel AI Gateway; no Jev model weights are distributed.
