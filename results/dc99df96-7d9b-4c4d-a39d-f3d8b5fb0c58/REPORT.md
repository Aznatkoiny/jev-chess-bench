# Nine-game content run — 20 September 2026

Real Gateway run `dc99df96-7d9b-4c4d-a39d-f3d8b5fb0c58`; separate from the original eight-game rated tournament. [Open run](https://jev-chess-bench.vercel.app/?run=dc99df96-7d9b-4c4d-a39d-f3d8b5fb0c58) · [Paced recording view](https://jev-chess-bench.vercel.app/record.html?run=dc99df96-7d9b-4c4d-a39d-f3d8b5fb0c58&autoplay=1&pace=750).

Nine attempted games: **0 wins, 0 draws, 8 checkmate losses; 1 failed game**, 394 played plies. Score rate across completed games: 0%. No infrastructure failures or censored games. Elo stays **914.7, eight rated tournament games**: this content run is unrated.

## Predeclared plan

Nine games: four opening pairs with colors swapped, then one unpaired initial-position game with Jev White (5 White, 4 Black). $2.50 run ceiling, $0.002 durable reservation per attempted inference, $5 lifetime worker ceiling. At most two attempts per decision, 10 seconds each, 2-second retry delay; 160 played plies/game, 1,200 seconds/game, 7,200 seconds/run; stop at two infrastructure failures or budget exhaustion. No engine move substitutions.

`typesafe-ai/jev` through Vercel AI Gateway `/v1/evaluate`, complete legal UCI Choice set, provider `typesafe-ai`, prompt training disabled; seed/temperature unsupported. Stockfish 16 engine, Skill 0, depth 4, one thread, 16 MiB hash, hash cleared per decision. Exact configuration/software/source revision are retained in `run.json`.

## Results

| Game | Jev color | Status | Result | Played plies | Termination |
| --- | --- | --- | --- | --- | --- |
| 1 | White | completed | 0-1 | 32 | checkmate |
| 2 | Black | completed | 1-0 | 49 | checkmate |
| 3 | White | completed | 0-1 | 30 | checkmate |
| 4 | Black | completed | 1-0 | 27 | checkmate |
| 5 | White | completed | 0-1 | 26 | checkmate |
| 6 | Black | failed | * | 25 | invalid_response |
| 7 | White | completed | 0-1 | 32 | checkmate |
| 8 | Black | completed | 1-0 | 53 | checkmate |
| 9 | White | completed | 0-1 | 120 | checkmate |

198 Gateway attempts; 3 invalid responses (1.52%). Median successful Jev decision latency 325.4ms, p95 561.4ms. 296,143 input tokens and 42,180 output tokens. Gateway response-reported cost **$0.00 across 198/198 attempts**; token-price estimate **$0.012438006**, distinct from observed billing; conservative spending reservation **$0.396**. Hosting costs excluded.

All three rejected responses selected legal moves but contradicted their own probability ordering. In game 6, the first response selected `c7c5` at 0.20 while `f8d8` was 0.21; the retry selected `f8d8` at 0.20 while `c7c5` was 0.21. This exhausted the frozen response-consistency policy and stopped the game as an operational forfeit, not a chess loss. In game 8, an analogous response retried successfully. The [documented Choice interface](https://docs.typesafe.ai/primitives/choice) states that the selected choice has the highest probability. Raw responses and these failures remain intact.

Only three complete color pairs enter this run's uncertainty calculation; the failed pair and ninth unpaired game do not. The 95% paired Hoeffding score interval is 0–78.41%, with an unbounded lower performance endpoint and upper 1224.0 against the arbitrary 1000 opponent anchor. It is conditional on the fixed suite, not a calibrated human Elo estimate. No new Elo history was created.

## Recording and verification

The browser recording started before this run was queued. The view displays every recorded move sequentially at 0.75 seconds per ply and shows actual inference latency separately; once the worker completes, its label changes from LIVE CAPTURE to RECORDED RUN. It preserves the failed game. The full MP4 retains every move; the highlights cut uses the final moves of each game at the same presentation pace, with no acceleration.

Hosted QA verifies nine selectable games, last-game replay and downloads, refusal of out-of-range game indices, anonymous viewing, and persistence after reload. Independent python-chess replay verifies every move, SAN, FEN, PGN, terminal outcome, complete legal candidate delivery and exact execution of each accepted Jev choice. Capture verification confirms all 394 played positions were displayed exactly once in order, with no browser or connection errors. `capture-verification.json` retains rendered FENs; `capture-timeline.json` retains the edit timeline. `export-metadata.json` retains exact edit ranges and codec metadata. Full MP4: 336.021 seconds, 1280×720, 7,759,088 bytes. Tweet highlights: 94.001 seconds, 1280×760, 2,397,669 bytes. Both use H.264/yuv420p at 30 fps with silent AAC audio, with no change to display speed. All nine endings appear in the highlights. `video-files.json` records output hashes. Videos themselves are local artifacts under `output/video/content-nine/`, excluded from source control.
