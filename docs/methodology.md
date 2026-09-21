# Benchmark protocol and interpretation

This protocol measures Jev's decisions against one frozen Stockfish configuration. Configuration and preflight evidence precede measured inference. There are no synthetic results in the measured tournament. The source of truth for current values is [config.json](../config.json); this document describes protocol version 1.

## Validation stages

First validate game rules and match execution with deterministic players and known outcomes. These tests cover normal moves, castling through check, en passant and discovered check, all promotions, checkmate, stalemate, insufficient material, repetition, move-clock draws, game-record replay, candidate integrity and bounded failures. Then validate real engine execution and Gateway acceptance of the complete observation/candidate schema. Then play two real smoke games with colors swapped. Finally, run the predeclared eight-game tournament and verify the deployed viewer and durable archives. A passed test transport is not a Gateway smoke result.

## Opponent and reproducibility

The baseline is native **Stockfish 16**, using Ubuntu's `16-1build1` arm64 package. It is an open-source search engine that incorporates an NNUE evaluation network, not a standalone learned policy. It provides a practical adjustable opponent with a stable UCI interface. It needs no GPU; the DGX Spark supplies persistent CPU execution and disk storage. [Stockfish 16 source](https://github.com/official-stockfish/Stockfish/tree/sf_16), [Ubuntu package identification](https://manpages.ubuntu.com/manpages/noble/man6/stockfish.6.html), [UCI documentation](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html).

| Engine parameter | Frozen value |
| --- | --- |
| Skill Level | 0 |
| Search | `go depth 4` |
| Threads | 1 |
| Hash | 16 MiB |
| MultiPV | 1, managed by python-chess's play interface |
| UCI_LimitStrength | false; no UCI_Elo target |
| Engine watchdog | 2 seconds per decision including startup/configuration |
| Process/hash policy | Fresh instance for each game; clear hash before every turn |
| Opening book / tablebases | None |
| Random seed | Unsupported by standard Stockfish UCI |

Skill Level intentionally randomizes weaker choices. Its numerical value does not mean a human Elo, and a fixed depth does not mean all variations receive equal search depth. Report the exact configuration instead of assigning the engine a supposedly absolute rating. [Stockfish FAQ](https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html).

The worker retains Python/platform and `chess` versions, the Stockfish executable's SHA-256 hash, source revision from `REVISION`, actual UCI engine identity, settings and full run configuration. The package is pinned to `chess==1.11.2`; JavaScript dependencies are locked by `package-lock.json`. `typesafe-ai/jev` is the verified Gateway evaluation model ID. Its upstream weights are not pinned by that public alias; neither temperature nor seed is documented for this interface. Save provider/model metadata and generation IDs when returned. See [Jev interface verification](jev-interface.md) and [Vercel evaluation documentation](https://vercel.com/docs/ai-gateway/modalities/evaluation).

## Information supplied to players

[python-chess](https://python-chess.readthedocs.io/en/latest/core.html) is the authority for legal moves, state transitions and outcomes. Jev receives current and initial FEN, side to move, ASCII board, full UCI and SAN history, check status, castling/en-passant rights, the move clock, repetition count and draw policy. Every currently legal move appears in lexicographically sorted UCI notation. Promotion choices remain distinct. An immutable copy of the same full candidate set becomes the evaluation Choice criteria.

The interface accepts at most 255 choices and the adapter rejects an oversized candidate set before inference. It also rejects a serialized request above 28,000 bytes. Neither check removes a move or truncates history. The failure remains explicit. No opponent recommendations, engine search scores or evaluations enter the Jev observation. The executor separately validates the returned move against the rules board, even if an adapter mutates its own observation.

Draws are automatically claimed once the **current** position has occurred three times or the current clock reaches 100 halfmoves without a pawn move or capture. A draw is not preclaimed because an unplayed intended move would make it available. The observation distinguishes current conditions from python-chess's claim-on-next-move flags. Automatic fivefold repetition, 75-move draws, stalemate and insufficient material also use the rules library. Checkmate takes precedence. PGNs record `DrawPolicy`.

## Frozen schedule and limits

Smoke consists of two unrated games from the initial position. The tournament consists of eight games, four position pairs. Jev is White in the first game of each pair and Black in the second. The same legal opening sequence starts both games:

| Pair | Position | UCI opening moves |
| --- | --- | --- |
| 1 | Initial position | None |
| 2 | Open game | `e2e4 e7e5 g1f3 b8c6` |
| 3 | Queen pawn | `d2d4 d7d5 c2c4 e7e6` |
| 4 | English opening | `c2c4 e7e5 b1c3 g8f6` |

These short fixed openings provide a small varied suite and preserve full draw history. They are not a representative sample of every chess position. Color pairing reduces opening/color confounding. No performance-based early stopping or configuration adjustment occurs within the comparison.

The smoke reservation ceiling is $0.60; tournament ceiling is $2.00; the worker's persistent cumulative ceiling is $5. Every request attempt reserves $0.002 before its network call. Each game permits 160 plies **after** the opening and 1,200 seconds. The run budget is 7,200 seconds. Jev permits two attempts per turn, 10 seconds each and a 2-second retry delay; no model-based or engine-based fallback exists. Runs stop at budget exhaustion, the time limit or two infrastructure-failed games. Completed snapshots and the frozen plan are published before any paid tournament call.

Failed publication between games stops further spending until the durable run is reconciled. A worker restart during a run marks unfinished play interrupted and stops that run, retaining reservations. This avoids silently issuing the same ambiguously billed inference again. The same data directory must survive restarts for spending history to remain effective.

## Outcomes, failure accounting and costs

Only a rules-completed game contributes a chess win, draw or loss. An exhausted malformed/invalid Jev response or model timeout is a failed game with a separately reported operational forfeit; it is not silently converted into a chess loss or a replacement move. HTTP/network failures, worker/engine problems, unavailable funds and harness exceptions are infrastructure failures. Move or wall-clock limits yield a **censored** game, never a draw. Their PGN result remains `*`.

The score rate is `(wins + 0.5 × draws) / completed_games`. Always report completed, failed and censored counts with it. Excluding censored/failed games can introduce selection bias if long or difficult positions are more likely to fail; a small complete-case score should not be generalized to every scheduled game.

Invalid-response rate uses invalid attempts divided by all recorded Jev attempts, including retries. Move latency is the end-to-end time of a successful Jev decision, including any retry and delay; median and p95 use recorded Jev moves only. Failed-attempt latencies remain in raw artifacts and are not represented as successful move latencies. Token usage sums returned input/output token counts across all attempts where provided.

Observed cost sums response-reported `providerMetadata.gateway.cost` only where supplied. Its coverage count accompanies it. An unavailable cost stays unknown. The separate token-price estimate uses returned input tokens × $0.042/million; output price is recorded as zero in the verified catalog. Conservatively reserved cost is a ceiling allocation, not an invoice, and includes calls with unknown billing outcomes. Actual infrastructure billing for the Spark, Vercel functions and Blob is outside these inference-cost totals. See [Vercel model catalog](https://ai-gateway.vercel.sh/v1/models).

## Persistent Elo and uncertainty

Every new comparison pool initializes Jev at **1000** and fixes its Stockfish opponent anchor at **1000**. This anchor is arbitrary. After each completed tournament game in execution order:

```text
S = 1 for a win, 0.5 for a draw, 0 for a loss
E = 1 / (1 + 10^((1000 - R) / 400))
R_next = R + 24 × (S - E)
```

Smoke games, synthetic checks, failures and censored games do not update ratings. SQLite stores each unique game ID once together with its pool, score, resulting rating and timestamp. Display the cumulative rated sample size. The comparison pool hash includes protocol/model, opponent, inference, limits, opening suite, draw/failure policies, rating rules, source fingerprints of game/model/engine adapters, the chess library version and the actual engine binary hash. Changing a relevant setting or implementation starts a separate history. Increment the protocol version when adapter semantics change.

The online rating is a deterministic history of updates, with dependence on initialization, K and game order. It is **not** a precise statistical estimate after a handful of games.

For uncertainty, complete opposite-color pairs supply observations `X_i = (S_white + S_black) / 2` in `[0,1]`. Incomplete pairs are excluded from this interval, and pair count is displayed. Assuming independence **between** pairs, conditional on the fixed suite, the conservative two-sided 95% Hoeffding score interval is:

```text
half_width = sqrt(log(40) / (2 × number_of_complete_pairs))
score_low  = max(0, mean(X) - half_width)
score_high = min(1, mean(X) + half_width)
```

No independence between the two colors within a pair is required. The bound follows [Hoeffding's bounded-variable result](https://www.cs.rpi.edu/academics/courses/spring06/random/hoefding.pdf). Color-paired observations also reflect the motivation behind [Stockfish Fishtest's pentanomial match model](https://official-stockfish.github.io/docs/fishtest-wiki/Fishtest-Mathematics.html), although this application uses the simpler conservative bound rather than implementing Fishtest's statistical tests.

For display only, transform score endpoints to an **Elo-equivalent performance interval against the fixed pool anchor**:

```text
performance(p) = 1000 + 400 × log10(p / (1-p))
```

At `p=0` the lower endpoint is negative infinity; at `p=1` the upper endpoint is positive infinity. JSON uses `null` for these unbounded endpoints. No complete pair means no finite performance interval. This transformed interval is **not a confidence interval around the online Elo update value**. With four pairs the interval will be very wide and can be unbounded. It does not justify precise skill claims, and missing outcomes or dependence across pairs weaken inferential interpretation further.

## Execution, public access and archives

The public viewer and API run on Vercel; functions are configured for short requests with a 30-second duration. Matches execute on the persistent DGX Spark worker. The worker makes outbound authenticated HTTPS requests to the app, so public inbound access to Spark is unnecessary. A real heartbeat, queued job, completed Gateway match and reloaded archived record are the hosted connection checks. This design is motivated by [Vercel function duration constraints](https://vercel.com/docs/functions/limitations).

SQLite/WAL durably stores run records, reservations and Elo. Vercel Blob is configured private; server endpoints serve selected public snapshots, raw benchmark game records and PGNs. Separate bearer tokens protect operator queueing and worker writes. A public visitor may watch, replay or download results but cannot start paid inference. The paid API accepts only the smoke/tournament kinds and freezes configuration server-side. Private source control and private storage credentials do not prevent intentional public reading of chess benchmark artifacts. [Blob SDK documentation](https://vercel.com/docs/vercel-blob/using-blob-sdk).

Retain the run config and pool ID, run/game IDs, source revision and executable hash, actual engine ID/options, initial and final position, all UCI/SAN moves and PGN, every Jev request/response without credentials, latency/status/retry metadata, token/cost fields, failures, timestamps and rating history. These support replay and auditing. Exact inference reproduction remains limited by an unversioned Gateway model alias and unsupported random seeds.

The application implements chess only. Rules and observations stay separate from player adapters, match execution, persistence and evaluation. For a future hidden-information game, add a game-specific observation builder that filters internal state by acting player, and define appropriate payoffs and uncertainty independently. Do not reuse chess's fully public state or rating assumptions for poker.
