# Measured benchmark — September 20, 2026 (America/New_York)

The requested app is live at [jev-chess-bench.vercel.app](https://jev-chess-bench.vercel.app). [Source](https://github.com/Aznatkoiny/jev-chess-bench) is available in the public **GPL-3.0-or-later** GitHub repository (initially created private, then opened at the user’s request). The publicly viewable results below come from actual Vercel AI Gateway requests, with no engine advice supplied to Jev.

Tournament **b4dd6ed2-68d6-4484-85e2-18078c16a20b** ran from **2026-09-21T00:22:22.256017+00:00** to **2026-09-21T00:23:34.803154+00:00** (72.55 seconds). [Hosted full run](https://jev-chess-bench.vercel.app/api/runs?id=b4dd6ed2-68d6-4484-85e2-18078c16a20b) · [local full archive](b4dd6ed2-68d6-4484-85e2-18078c16a20b/run.json) · [frozen protocol](../config.json) · [methodology](../docs/methodology.md).

| Run | Completed / planned | Jev W / D / L | Score rate | Failed / censored | Invalid / attempts | Median / p95 successful move latency |
| --- | --- | --- | --- | --- | --- | --- |
| Corrected smoke (unrated) | 2 / 2 | 0 / 0 / 2 | 0.0% | 0 / 0 | 0 / 47 | 319.3 / 391.2 ms |
| Tournament | 8 / 8 | 0 / 0 / 8 | 0.0% | 0 / 0 | 0 / 163 | 313.1 / 482.4 ms |

Every tournament game ended in checkmate. One request received **HTTP 429** and succeeded on its prescribed retry; there were **0 infrastructure-failed games, 0 timeouts, and 0 invalid Jev responses**. The successful-turn latency includes retries and their delays; it is not provider compute time. All 162 successful Jev choices were executed exactly as returned.

## Costs and tokens

| Metric | Tournament | Corrected smoke |
| --- | ---: | ---: |
| Input tokens returned | 225,793 | 67,972 |
| Output tokens returned | 34,030 | 10,850 |
| Response-reported Gateway cost | $0.00 | $0.00 |
| Cost/usage coverage | 162 of 163 attempts | 47 of 47 attempts |
| Catalog-price estimate | $0.00948331 | $0.00285482 |
| Conservative budget reserved | $0.326 | $0.094 |
| Predeclared reservation ceiling | $2.00 | $0.60 |

The 429 response supplied no usage/cost accounting; its cost is **unknown**, not asserted zero. Estimates apply $0.042 per million reported input tokens and $0 per output token and exclude that unreported request. Response-reported zero is not an invoice reconciliation. Spark, Vercel Function and Blob infrastructure billing is not included. The dedicated Gateway key has a nonrenewing $5 quota and 30-day expiry. Total conservative reservations across the probe, diagnostic smoke, corrected smoke, tournament and browser verification smoke are **$0.552**; these are budget allocations, not observed charges.

## Provisional relative rating

Jev's persistent online Elo is **914.7 after 8 rated games**, initialized at 1000 against a fixed 1000 opponent anchor, K=24. It is **provisional and relative to this benchmark opponent pool**. It is not FIDE, Chess.com or Lichess Elo. Stockfish's skill setting has no assumed human calibration.

With four complete color pairs, the conservative 95% paired Hoeffding **score** interval is **0%–67.9%**. Mapping its endpoints to performance against the arbitrary 1000 anchor gives **negative infinity to 1130.2**. This is a score-equivalent performance interval, **not a confidence interval around 914.7**. It is intentionally broad: eight games against one engine configuration cannot establish a precise or transferable chess rating. Between-pair independence is assumed conditional on these chosen openings; they do not represent every chess position.

## Opponent and model

- **Jev:** learned decision model `typesafe-ai/jev`; Vercel `POST /v1/evaluate`; one Choice over every legal UCI move. Provider restricted to TypeSafe; prompt training disallowed; standard retention. Temperature and seed unsupported. The Gateway alias does not pin immutable upstream weights.
- **Stockfish 16:** GPLv3-or-later CPU chess engine with NNUE evaluation, Ubuntu `16-1build1` arm64. Skill Level 0, depth 4, Threads 1, Hash 16 MiB, MultiPV 1, UCI_LimitStrength=false; fresh process per game and clear hash each turn; no book/tablebases. Seed unsupported.
- **Rules:** `chess==1.11.2`, Python 3.12.3. Source revision `b96f62329bec3e5cf0d11f97bde6844bd2e269ab`. Engine SHA256 `1dfbbeaf1d7e0309dbd96aa6726332ff83944ba87d06aac7d3ba912c89c4b2a8`. Pool `9e4aae9c1c0ce4356fff`. Full prompts, raw responses, supported settings and response metadata are in the archives.
- **Limits:** 8 games / 4 paired starts; 160 played plies and 1200 seconds/game; 7200 seconds/run. Two Jev attempts, 10 seconds each, 2-second retry delay. No fallback moves. Stop on budget exhaustion or two infrastructure-failed games. Censored/failed games are not chess draws/losses and are not rated.

| Game | Paired starting position | Jev color | Jev result | Played plies after opening | Termination |
| --- | --- | --- | --- | --- | --- |
| 1 | Initial position | white | Loss | 34 | checkmate |
| 2 | Initial position | black | Loss | 59 | checkmate |
| 3 | Open game | white | Loss | 20 | checkmate |
| 4 | Open game | black | Loss | 43 | checkmate |
| 5 | Queen pawn | white | Loss | 44 | checkmate |
| 6 | Queen pawn | black | Loss | 33 | checkmate |
| 7 | English opening | white | Loss | 54 | checkmate |
| 8 | English opening | black | Loss | 41 | checkmate |

## Verification and diagnostic evidence

87 Python tests and 4 Node API tests pass; GitHub [CI run 35547418872](https://github.com/Aznatkoiny/jev-chess-bench/actions/runs/35547418872) passed. These include synthetic rules/players/transports and are kept separate from measured games. The native pre-model Spark check completed a 58-ply seeded-player game against real Stockfish. The real 48-candidate [Gateway probe](interface-probe.json) selected `e5f7` with the entire legal set supplied; it is not a game or Elo observation.

The first two-game [diagnostic smoke](8572d63b-88c3-4e25-acc5-b83cb0afeec3/run.json) is retained separately. It exposed an adapter assumption: documented 2-decimal probabilities can sum to 0.99 even with a valid selected move. Two legal choices were needlessly retried. The adapter was fixed from official source before the corrected smoke and tournament; the diagnostic's original attempts are preserved and its outcomes are not pooled into the tournament.

Independent archive verification replayed all 14 actual games and 275 attempts, including the browser verification smoke, checking complete candidate sets (up to 48 in a game), PGN/final-FEN agreement, complete move delivery and exact execution of Jev choices. The additional 48-candidate probe is outside those counts.

Hosted browser checks cover actual match data, first/next/play/jump/replay controls, PGN and raw download, desktop/mobile layout, protected-execution rejection, and result persistence after reload. The DGX Spark connection is verified by hosted heartbeat, fetched queue, completed Gateway games and uploaded archives, rather than SSH access alone. The worker's data and rating/spending ledger are durable SQLite/WAL; private Blob holds the public-serving mirror. Paid execution requires the operator token. Source and archive scans found no configured credentials.

## Rerun

The Spark user service is `jev-chess-bench.service`. Its directory is `/home/aznatkoiny/Documents/projects/jev-chess-bench`; preserve `data/` across restarts. In the public app, open **Run a protected benchmark**, supply the operator token, run smoke, then run tournament. The local operator-token file is outside Git at `output/admin_token`, mode 0600. Do not paste it into chat or add it to source control.

```sh
python3 scripts/enqueue.py smoke --token-file output/admin_token
# Inspect the completed smoke before launching the next paid comparison.
python3 scripts/enqueue.py tournament --token-file output/admin_token
```

Review the current model price before a later run. The existing lifetime reservation cap remains in force; creating a new run does not reset it. Public artifacts use `/api/artifact?id=RUN_ID&game=0` and `/api/pgn?id=RUN_ID&game=0`. Reproduce all local checks and deployment steps from the [README](../README.md). Run `.venv/bin/python scripts/verify_records.py results` to audit the saved records.

## Final browser execution and persistence check

A separate two-game smoke run **2db919a8-608b-43d1-8912-03e00c4f7f13** was predeclared with a $0.60 reservation ceiling and queued through the actual protected browser form. It completed 2 games (0 W / 0 D / 2 L), with 26 valid Jev responses, no failed/censored games and $0.052 reserved. These games are unrated and do not extend the 8-game tournament. The operator token cleared after submission and was absent from local/session storage. Automatic polling advanced from the new run's empty queued board to its actual 17-ply position, independently matched against the saved FEN. [Browser evidence](browser-live-verification.json) retains the earlier tournament frame and explicitly excludes it from this live-run proof.

After the tournament, an idle worker restart preserved 3 runs, 8 ratings and $0.500 of reservations exactly, without another request. The later browser test accounts for the additional $0.052. Public archive/PGN endpoints and browser reload retain the original tournament results. The final app redeployment preserves the same external Blob records.
