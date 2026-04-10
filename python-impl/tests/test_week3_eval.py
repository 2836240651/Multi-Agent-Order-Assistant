from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evals.cases import build_week3_cases
from evals.runner import run_week3_evaluation


class Week3EvalTests(unittest.TestCase):
    def test_case_builder_has_expected_volume(self):
        cases = build_week3_cases()
        self.assertGreaterEqual(len(cases), 200)
        self.assertEqual(cases[0].expected_action, "order_query")

    def test_runner_generates_report_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_week3_evaluation(Path(tmpdir))
            self.assertIn("current_v3", result["summary"])
            self.assertTrue(Path(result["results_path"]).exists())
            self.assertTrue(Path(result["report_path"]).exists())


if __name__ == "__main__":
    unittest.main()
