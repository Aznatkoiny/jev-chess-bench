# Jev interface and benchmark controls

Verified against live official sources on 2026-09-20. Jev is a learned general decision model, not a chess engine. This application gives it only player-visible chess information and asks it to select its own move. It does not give Jev opponent recommendations, engine scores, ranked candidates, or a preselected shortlist.

## Model and supported interface

The live [Vercel model catalog](https://ai-gateway.vercel.sh/v1/models) returns `typesafe-ai/jev`, type `evaluation`, specification `v4`, context window `32000`, input price `0.000000042` USD/token ($0.042/million), and output price `0`. Both no-training and zero-retention capabilities are listed, but capability does not imply the account has paid-plan access to zero retention.

The official [Vercel evaluation documentation](https://vercel.com/docs/ai-gateway/modalities/evaluation) supports `POST https://ai-gateway.vercel.sh/v1/evaluate`. This is the endpoint the Python adapter uses. OpenAI chat/completions, Anthropic Messages, and Cohere compatibility endpoints do not support this modality. JavaScript can alternatively use `experimental_evaluate` in AI SDK 7.0.105 or later. Installed local source was inspected at AI SDK `7.0.105`; its Gateway adapter uses `/v4/ai/evaluation-model`. The Python implementation avoids depending on that internal protocol.

[TypeSafe models documentation](https://docs.typesafe.ai/models) currently identifies upstream stable Jev as `jev-1.13.0`. The Gateway catalog exposes only `typesafe-ai/jev`, not a version-pinned upstream ID. Record the response model, routing metadata, timestamps, request schema, and prompt to make runs auditable. This cannot guarantee identical weights on a future rerun; no unsupported Gateway model variant is invented.

Jev's evaluation interface exposes no documented temperature, random seed, or maximum generated-token setting. These are recorded as unsupported, rather than assigned misleading values. One Choice returns its highest-probability option. Model confidence is distinct from chess strength and is not used to substitute moves.

## Exact request shape

```json
{
  "model": "typesafe-ai/jev",
  "state": {
    "game": "chess",
    "fen": "current FEN from python-chess",
    "initial_fen": "initial FEN",
    "side_to_move": "white",
    "history_uci": [],
    "history_san": [],
    "draw": {"halfmove_clock": 0, "current_repetitions": 1},
    "check": false,
    "legal_moves": ["d2d4", "e2e4"]
  },
  "questions": {
    "move": {
      "type": "choice",
      "instructions": "Full immutable prompt is INSTRUCTIONS in chessbench/jev.py and is saved with every attempt.",
      "criteria": {"d2d4": null, "e2e4": null}
    }
  },
  "providerOptions": {
    "gateway": {"only": ["typesafe-ai"], "disallowPromptTraining": true}
  }
}
```

The abbreviated two-move example illustrates the schema only. Real requests include **every** legal move, sorted lexicographically in UCI notation, and every observation field provided by the game rules module. Underpromotion is a separate option for each promotion piece. Draw history, claim policy, and repetition counts come from the game authority. Authentication is a server-side Bearer header and is never stored with this request record.

[TypeSafe Choice documentation](https://docs.typesafe.ai/primitives/choice) explicitly supports up to **255** options and recommends providing the full candidate set. The adapter supports all 255; input above that ceiling fails before inference, without removing options. It also refuses a serialized request above 28,000 bytes as a conservative guard below the 32k token context. This includes the entire request, not only the state. An oversized observation stops the game as an infrastructure failure instead of silently deleting history or legal moves. A transport smoke test with a large legal candidate set remains necessary to confirm actual Gateway acceptance.

## Failures, timeout, and spending

Jev rounds displayed probabilities to **two decimal places**. This is explicit in the [official Vercel TypeSafe adapter source](https://github.com/vercel/ai/blob/main/packages/typesafe-ai/src/typesafe-ai-evaluation-model.ts) and [official provider README](https://github.com/vercel/ai/blob/main/packages/typesafe-ai/README.md), which inject `rounding: { probabilityDecimals: 2, scoreDecimals: 2 }`. The [AI SDK evaluation documentation](https://ai-sdk.dev/docs/ai-sdk-core/evaluation) explains that a valid rounded distribution can sum to 0.99. When the Gateway HTTP response omits `rounding.probabilityDecimals`, this Jev-specific adapter therefore uses the documented default of 2; an explicit valid Gateway declaration overrides it. Sum tolerance is `0.000001 + option_count × 0.5 × 10^(-decimals)`. Exact answer IDs, exactly one listed legal move, complete candidate coverage, finite probabilities in [0,1], and highest-probability selection remain mandatory. Raw probabilities are preserved without renormalization. Each attempt records its applied precision and the source under `response_validation`, separately from unmodified raw metadata.

The first two-game live smoke run predates this rounding correction. Its strict sum validator incorrectly classified some legal responses summing to 0.99 as invalid and retried them. Preserve that run and all its raw attempt records as a **pre-fix diagnostic**, separate from the corrected smoke and tournament; do not interpret its validator-generated invalid count as model failures or edit historical records.

Every decision allows at most two total attempts, with a 10-second total response deadline and a 2-second delay before the second attempt. An isolated daemon transport also uses a 10-second socket timeout. The total response deadline covers slow DNS and slow-drip responses; a late result is discarded and can never become a move. Remote inference cancellation is not guaranteed, so a timeout keeps its full spending reservation and unknown billing status. Malformed JSON, missing/extra answer IDs, a non-Choice response, a selection absent from the exact move list, or a malformed probability distribution count as invalid responses. Exhaustion raises `PlayerError` with every attempt preserved. No move is substituted. HTTP 429/5xx and network errors may retry; HTTP 400/401/402/403/404 stop as infrastructure failures without retry. Timeouts remain distinguishable from malformed model answers and chess outcomes. The match executor determines the recorded terminal policy for each category.

Before **every** attempted request, including retries, the adapter requires a reservation callback to reserve **$0.002** against the run's fixed spending ceiling. This exceeds the catalog price of a full 32,000-input-token request ($0.001344). Reservations are never released during the run, including for timeouts or rejected calls whose billing status is unknown. Missing budget control prevents inference. A separate cumulative API call count and game/ply limits bound execution even if model prices are promotional or free. Recheck live pricing before starting a later run; if a full context costs more than the reserve, increase the reservation before inference.

Each attempt preserves status, elapsed time, request, raw response (credential redacted), usage, reservation, response cost, and generation ID if provided. `providerMetadata.gateway.cost` is observed response-reported cost; `inputTokens × 0.000000042` is a separate catalog-price estimate. Missing observed cost remains unknown and is never silently treated as zero. Failure attempts can consume tokens or money; reservations remain charged to the local run budget even when the provider returns no accounting.

The [Vercel reporting documentation](https://vercel.com/docs/ai-gateway/observability-and-spend/custom-reporting) says `/v1/report` requires Pro or Enterprise. Per-response usage/cost metadata works independently of that reporting endpoint. All raw response metadata is retained so the experiment can audit `gateway.cost`, `marketCost`, `surchargeCost`, `gatewayCost`, routing, provider version information if supplied, and `generationId`.

## Synthetic verification and actual evidence

`tests/test_jev.py` uses injected synthetic transports. These verify complete candidate delivery, retry limits, invalid-response rejection, spending reservation ordering, cost distinctions, key redaction, and failure records. They are not Jev performance results. Real benchmark records are produced only by successful authenticated requests to the Vercel endpoint after deterministic game/harness validation.
