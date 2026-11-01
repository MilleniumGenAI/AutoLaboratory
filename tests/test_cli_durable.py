from __future__ import annotations

try:
    import support  # noqa: F401
except ImportError:
    from tests import support  # noqa: F401

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autoresearch_runtime.commands import baseline, recover, resume, trial


class DurableCliDispatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = SimpleNamespace(
            lab_id="b5ef9c01-3a58-4ca8-a63c-4eb79216a912",
            state_dir=Path(self.temp.name) / "state",
        )

    def test_sync_mutating_commands_use_the_common_durable_operation_path(self):
        with patch("autoresearch_runtime.commands.baseline.resolve_config", return_value=self.config), \
             patch("autoresearch_runtime.commands.baseline.run_durable_operation", return_value={"status": "accepted"}) as run:
            baseline.run(SimpleNamespace(), None)
            run.assert_called_once_with(self.config, "baseline", {})

        run_id = "trial-0001"
        with patch("autoresearch_runtime.commands.resume.resolve_config", return_value=self.config), \
             patch("autoresearch_runtime.commands.resume.run_durable_operation", return_value={"status": "rejected"}) as run:
            resume.run(SimpleNamespace(run_id=run_id), None)
            run.assert_called_once_with(self.config, "resume", {"run_id": run_id})

        with patch("autoresearch_runtime.commands.recover.resolve_config", return_value=self.config), \
             patch("autoresearch_runtime.commands.recover.run_durable_operation", return_value={"interrupted": []}) as run:
            recover.run(SimpleNamespace(), None)
            run.assert_called_once_with(self.config, "recover", {"restore_candidate": True})

    def test_trial_start_enqueues_the_normalized_hypothesis_once(self):
        raw = {"title": "A", "observation": "B", "expected_effect": "C", "evidence": ["D"], "unknown": "dropped"}
        args = SimpleNamespace(trial_command="start", hypothesis_json=json.dumps(raw), confirmed=True)
        with patch("autoresearch_runtime.commands.trial.resolve_config", return_value=self.config), \
             patch("autoresearch_runtime.commands.trial.enqueue_and_start_operation",
                   return_value={"operation_id": "op-1", "status": "queued"}) as enqueue:
            result = trial.run(args, None)
        enqueue.assert_called_once()
        _lab_id, command, params, _key = enqueue.call_args.args
        self.assertEqual(command, "trial")
        self.assertEqual(params, {
            "hypothesis": {"title": "A", "observation": "B", "expected_effect": "C", "evidence": ["D"]},
            "confirmed": True,
        })
        self.assertEqual(result, {"started": True, "operation_id": "op-1", "status": "queued"})


if __name__ == "__main__":
    unittest.main()
