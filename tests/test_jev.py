"""Synthetic transport tests. These are not measured Jev games or model results."""
import copy
import json
import time
import unittest
import urllib.error

from chessbench.jev import (
    GatewayHTTPError, GatewayResponseError, JevPlayer, MODEL_ID,
    RESERVE_USD_PER_ATTEMPT, build_request, validate_answer,
)
from chessbench.players import PlayerError


OBSERVATION = {
    "game": "chess", "fen": "position supplied by rules library",
    "initial_fen": "start", "side_to_move": "white",
    "legal_moves": ["e2e4", "d2d4"],
    "history_uci": [], "history_san": [],
    "draw": {"halfmove_clock": 0, "current_repetitions": 1}, "check": False,
}


def answer(move="e2e4", **extra):
    return {"model": MODEL_ID, "answers": {"move": {"type": "choice", "choice": move}}, **extra}


class JevTests(unittest.TestCase):
    def player(self, events, **kwargs):
        self.calls, self.reservations, self.sleeps = [], [], []

        def transport(payload, key, timeout):
            self.calls.append((payload, timeout))
            event = events.pop(0)
            if isinstance(event, Exception):
                raise event
            return event

        return JevPlayer("synthetic-secret", transport=transport,
                         reserve=lambda amount: self.reservations.append(amount),
                         sleep=self.sleeps.append, **kwargs)

    def test_full_observation_and_candidates_are_unchanged_except_sorted_order(self):
        original = copy.deepcopy(OBSERVATION)
        request = build_request(original)
        self.assertEqual(request["model"], MODEL_ID)
        self.assertEqual(list(request["questions"]["move"]["criteria"]), ["d2d4", "e2e4"])
        self.assertEqual(set(request["questions"]["move"]["criteria"]), set(original["legal_moves"]))
        self.assertEqual(request["state"]["draw"], original["draw"])
        self.assertEqual(original, OBSERVATION)
        self.assertEqual(request["providerOptions"]["gateway"], {
            "only": ["typesafe-ai"], "disallowPromptTraining": True,
        })

    def test_all_255_criteria_accepted_256_rejected_without_truncation(self):
        # Candidate-capacity test, not a claim that these moves are jointly legal.
        moves = [a + b + c + d for a in "abcdefgh" for b in "12345678"
                 for c in "abcdefgh" for d in "12345678" if a+b != c+d]
        obs = {**OBSERVATION, "legal_moves": moves[:255]}
        self.assertEqual(len(build_request(obs)["questions"]["move"]["criteria"]), 255)
        with self.assertRaises(PlayerError) as caught:
            build_request({**obs, "legal_moves": moves[:256]})
        self.assertEqual(caught.exception.kind, "infrastructure")
        self.assertIn("refusing to truncate", str(caught.exception))

    def test_complete_history_never_silently_truncated(self):
        with self.assertRaises(PlayerError):
            build_request({**OBSERVATION, "history_san": ["x" * 30000]})

    def test_success_records_usage_observed_cost_and_estimate_separately(self):
        raw = answer(usage={"inputTokens": 1000, "outputTokens": 50},
                     providerMetadata={"gateway": {"cost": "0", "generationId": "gen-synthetic"}})
        result = self.player([raw]).choose(OBSERVATION)
        self.assertEqual(result["move"], "e2e4")
        attempt = result["attempts"][0]
        self.assertEqual(attempt["usage"], {"inputTokens": 1000, "outputTokens": 50})
        self.assertEqual(attempt["observed_cost_usd"], 0)
        self.assertAlmostEqual(attempt["estimated_cost_usd"], 0.000042)
        self.assertEqual(self.reservations, [RESERVE_USD_PER_ATTEMPT])
        self.assertEqual(self.calls[0][1], 10)

    def test_missing_cost_and_usage_remain_unknown(self):
        attempt = self.player([answer()]).choose(OBSERVATION)["attempts"][0]
        self.assertEqual(attempt["usage"], {})
        self.assertIsNone(attempt["observed_cost_usd"])
        self.assertIsNone(attempt["estimated_cost_usd"])

    def test_invalid_choice_retry_uses_same_complete_observation(self):
        result = self.player([answer("h1h8"), answer("d2d4")]).choose(OBSERVATION)
        self.assertEqual(result["move"], "d2d4")
        self.assertEqual([a["status"] for a in result["attempts"]], ["invalid_response", "ok"])
        self.assertEqual(self.calls[0][0], self.calls[1][0])
        self.assertEqual(self.sleeps, [2])
        self.assertEqual(self.reservations, [0.002, 0.002])

    def test_invalid_exhaustion_has_no_substitute_move(self):
        with self.assertRaises(PlayerError) as caught:
            self.player([answer("h1h8"), answer("h1h8")]).choose(OBSERVATION)
        self.assertEqual(caught.exception.kind, "invalid_response")
        self.assertEqual(len(caught.exception.attempts), 2)
        self.assertNotIn("move", caught.exception.__dict__)

    def test_rate_limit_and_server_failures_are_retryable_infrastructure(self):
        for status in (429, 500, 503):
            with self.subTest(status=status):
                result = self.player([GatewayHTTPError(status, {"error": "busy"}), answer()]).choose(OBSERVATION)
                self.assertEqual(result["attempts"][0]["status"], "infrastructure")
                self.assertEqual(result["attempts"][0]["http_status"], status)
                self.assertEqual(len(self.calls), 2)

    def test_access_and_client_errors_fail_without_retry(self):
        for status in (400, 401, 402, 403, 404):
            with self.subTest(status=status):
                with self.assertRaises(PlayerError) as caught:
                    self.player([GatewayHTTPError(status)]).choose(OBSERVATION)
                self.assertEqual(caught.exception.kind, "infrastructure")
                self.assertEqual(len(caught.exception.attempts), 1)
                self.assertEqual(self.sleeps, [])

    def test_timeouts_remain_distinct_from_malformed_answers(self):
        with self.assertRaises(PlayerError) as caught:
            self.player([TimeoutError(), urllib.error.URLError(TimeoutError())]).choose(OBSERVATION)
        self.assertEqual(caught.exception.kind, "timeout")
        self.assertEqual([a["status"] for a in caught.exception.attempts], ["timeout", "timeout"])

    def test_late_provider_completion_never_becomes_a_move(self):
        def slow_transport(*_):
            time.sleep(.1)
            return answer()

        player = JevPlayer("synthetic-secret", transport=slow_transport, reserve=lambda _: True,
                           timeout=.01, max_attempts=1)
        started = time.monotonic()
        with self.assertRaises(PlayerError) as caught:
            player.choose(OBSERVATION)
        self.assertEqual(caught.exception.kind, "timeout")
        self.assertLess(time.monotonic() - started, .09)
        self.assertEqual(caught.exception.attempts[0]["reserved_cost_usd"], .002)

    def test_accounting_rejects_nonnumeric_or_nonfinite_costs(self):
        for cost in (True, "nan", "inf", -1, {}, 10 ** 1000):
            with self.subTest(cost_type=type(cost).__name__):
                result = self.player([answer(providerMetadata={"gateway": {"cost": cost}})]).choose(OBSERVATION)
                self.assertIsNone(result["attempts"][0]["observed_cost_usd"])

    def test_network_errors_do_not_expose_exception_text(self):
        with self.assertRaises(PlayerError) as caught:
            self.player([OSError("synthetic-secret"), OSError("synthetic-secret")]).choose(OBSERVATION)
        self.assertNotIn("synthetic-secret", repr(caught.exception.attempts))

    def test_raw_failures_redact_credential(self):
        result = self.player([GatewayHTTPError(500, {"error": "synthetic-secret"}), answer()]).choose(OBSERVATION)
        self.assertNotIn("synthetic-secret", repr(result))

    def test_reservation_happens_before_any_provider_call(self):
        player = self.player([answer()])
        player.reserve = lambda _: False
        with self.assertRaises(PlayerError) as caught:
            player.choose(OBSERVATION)
        self.assertEqual(caught.exception.kind, "budget")
        self.assertEqual(self.calls, [])
        self.assertEqual(caught.exception.attempts, [])

    def test_retry_reservation_failure_preserves_first_attempt(self):
        player = self.player([answer("h1h8")])
        count = 0

        def reserve(amount):
            nonlocal count
            count += 1
            return count == 1

        player.reserve = reserve
        with self.assertRaises(PlayerError) as caught:
            player.choose(OBSERVATION)
        self.assertEqual(caught.exception.kind, "budget")
        self.assertEqual(len(caught.exception.attempts), 1)
        self.assertEqual(len(self.calls), 1)

    def test_missing_key_or_budget_callback_prevents_calls(self):
        for player in (JevPlayer(key="", reserve=lambda _: None), JevPlayer(key="synthetic-secret")):
            with self.assertRaises(PlayerError):
                player.choose(OBSERVATION)

    def test_invalid_probability_distributions_are_rejected(self):
        bad = [
            {"e2e4": 1}, {"e2e4": 0.2, "d2d4": 0.2},
            {"e2e4": float("nan"), "d2d4": 0},
            {"e2e4": True, "d2d4": 0}, {"e2e4": 0.1, "d2d4": 0.9},
        ]
        for probabilities in bad:
            with self.subTest(probabilities=probabilities):
                raw = answer()
                raw["answers"]["move"]["probabilities"] = probabilities
                with self.assertRaises(GatewayResponseError):
                    validate_answer(raw, OBSERVATION["legal_moves"])

    def test_nonfinite_raw_response_can_still_be_persisted_as_failure(self):
        raw = answer()
        raw["answers"]["move"]["probabilities"] = {"e2e4": float("nan"), "d2d4": 0}
        result = self.player([raw, answer()]).choose(OBSERVATION)
        json.dumps(result, allow_nan=False)
        self.assertEqual(result["attempts"][0]["status"], "invalid_response")

    def test_declared_rounding_and_ties_are_supported(self):
        raw = answer(rounding={"probabilityDecimals": 2})
        raw["answers"]["move"]["probabilities"] = {"e2e4": 0.5, "d2d4": 0.5}
        self.assertEqual(validate_answer(raw, OBSERVATION["legal_moves"]), "e2e4")

    def test_missing_rounding_uses_documented_typesafe_two_decimals(self):
        raw = answer()
        raw["answers"]["move"]["probabilities"] = {"e2e4": .5, "d2d4": .49}
        result = self.player([raw]).choose(OBSERVATION)
        attempt = result["attempts"][0]
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(attempt["status"], "ok")
        self.assertEqual(attempt["response_validation"]["probability_decimals"], 2)
        self.assertEqual(attempt["response_validation"]["rounding_source"], "typesafe_documented_default")
        self.assertAlmostEqual(attempt["response_validation"]["probability_sum_tolerance"], .010001)
        self.assertNotIn("rounding", attempt["raw"])
        self.assertEqual(attempt["raw"]["answers"]["move"]["probabilities"], {"e2e4": .5, "d2d4": .49})

    def test_documented_rounding_accepts_valid_under_and_over_sums(self):
        moves = ["e2e4", "d2d4", "g1f3"]
        for values in ([.33, .33, .33], [.34, .34, .33]):
            raw = answer()
            raw["answers"]["move"]["probabilities"] = dict(zip(moves, values))
            self.assertEqual(validate_answer(raw, moves), "e2e4")

    def test_explicit_finer_rounding_overrides_jev_default(self):
        raw = answer(rounding={"probabilityDecimals": 4})
        raw["answers"]["move"]["probabilities"] = {"e2e4": .5, "d2d4": .49}
        with self.assertRaises(GatewayResponseError):
            validate_answer(raw, OBSERVATION["legal_moves"])

    def test_rounding_does_not_allow_illegal_choice_or_nonmaximal_selection(self):
        raw = answer("h1h8")
        raw["answers"]["move"]["probabilities"] = {"e2e4": .5, "d2d4": .49}
        with self.assertRaises(GatewayResponseError):
            validate_answer(raw, OBSERVATION["legal_moves"])
        raw["answers"]["move"]["choice"] = "d2d4"
        with self.assertRaises(GatewayResponseError):
            validate_answer(raw, OBSERVATION["legal_moves"])

    def test_rounding_errors_larger_than_half_unit_per_option_still_fail(self):
        raw = answer()
        raw["answers"]["move"]["probabilities"] = {"e2e4": .5, "d2d4": .48}
        with self.assertRaises(GatewayResponseError):
            validate_answer(raw, OBSERVATION["legal_moves"])


if __name__ == "__main__":
    unittest.main()
