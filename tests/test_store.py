from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator.domain import AgentResult, Scope, Usage
from orchestrator.store import StateStore


class StoreTests(unittest.TestCase):
    def test_routing_outcomes_are_attributed_to_the_output_round(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store = StateStore(workspace / "state.db")
            run_id = store.create_run(
                workflow="security-research-forum",
                task="Review a router.",
                workspace=workspace,
                scope=Scope(
                    authorization={},
                    targets=(str(workspace),),
                    allowed_actions=("local-testing",),
                ),
            )
            for round_number, model, decision in (
                (1, "gpt-5.6-high", "revise"),
                (2, "opus-5-bounded", "accept"),
            ):
                store.event(
                    run_id,
                    "round.started",
                    None,
                    {"round": round_number, "mode": "live"},
                )
                store.save_agent_result(
                    run_id,
                    round_number,
                    f"worker-{round_number}",
                    AgentResult(
                        persona="engineer",
                        model=model,
                        backend="test",
                        raw="{}",
                        parsed={},
                        status="completed",
                        usage=Usage(),
                    ),
                )
                store.event(
                    run_id,
                    "round.completed",
                    "judge",
                    {"round": round_number, "decision": decision},
                )

            outcomes = {
                row["model"]: row for row in store.routing_outcomes()
            }

            self.assertEqual(outcomes["gpt-5.6-high"]["terminal_calls"], 1)
            self.assertEqual(outcomes["gpt-5.6-high"]["accepted_calls"], 0)
            self.assertEqual(outcomes["opus-5-bounded"]["terminal_calls"], 1)
            self.assertEqual(outcomes["opus-5-bounded"]["accepted_calls"], 1)

            observations = {
                row["model"]: row for row in store.routing_observations()
            }
            self.assertEqual(
                observations["gpt-5.6-high"]["task"],
                "Review a router.",
            )
            self.assertEqual(observations["gpt-5.6-high"]["reward"], 0.5)
            self.assertEqual(observations["opus-5-bounded"]["reward"], 1.0)

    def test_native_queue_outcomes_are_idempotent_and_train_router(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.db")
            queue = [
                {
                    "id": "unit-1",
                    "round": 1,
                    "persona": "engineer",
                    "model": "gpt-5.6-high",
                    "status": "accepted",
                },
                {
                    "id": "unit-2",
                    "round": 1,
                    "persona": "verifier",
                    "model": "fable-5-bounded",
                    "status": "blocked",
                },
            ]

            first = store.record_native_outcome(
                workflow_run_id="native-test",
                bead_id="orch-test",
                task="Implement and verify the parser.",
                decision="accept",
                queue=queue,
            )
            duplicate = store.record_native_outcome(
                workflow_run_id="native-test",
                bead_id="orch-test",
                task="Implement and verify the parser.",
                decision="accept",
                queue=queue,
            )

            self.assertEqual(first, 2)
            self.assertEqual(duplicate, 0)
            outcomes = {
                row["model"]: row for row in store.routing_outcomes()
            }
            self.assertEqual(outcomes["gpt-5.6-high"]["accepted_calls"], 1)
            self.assertEqual(
                outcomes["fable-5-bounded"]["format_successes"],
                0,
            )
            observations = {
                row["model"]: row for row in store.routing_observations()
            }
            self.assertEqual(observations["gpt-5.6-high"]["reward"], 1.0)
            self.assertEqual(observations["fable-5-bounded"]["reward"], 0.0)
