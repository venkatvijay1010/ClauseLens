"""Run the built-in, no-key benchmark and print a JSON report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.assessment import HeuristicAssessmentProvider, SafeAssessmentService
from app.services.evaluation import run_benchmark

if __name__ == "__main__":
    metrics = run_benchmark(SafeAssessmentService(HeuristicAssessmentProvider()))
    print(json.dumps(metrics, indent=2))
