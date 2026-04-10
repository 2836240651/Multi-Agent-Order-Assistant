from __future__ import annotations

import json
from pathlib import Path

from evals.runner import run_week3_evaluation


def main() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "run"
    result = run_week3_evaluation(output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
