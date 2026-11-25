"""Benchmarking infrastructure for Skillora skills.

BenchmarkRunner executes a skill against many scenarios, measures latency,
token usage (mocked), accuracy (via success rate), and exports results to CSV.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from .core import Skill, SkillResult


class BenchmarkReport(BaseModel):
    """Structured benchmark results."""

    accuracy: float = Field(..., ge=0.0, le=1.0)
    mean_latency: float = Field(..., ge=0.0)
    mean_tokens: float = Field(..., ge=0.0)
    total_runs: int
    details: List[Dict[str, Any]] = Field(default_factory=list)

    def save_csv(self, path: Path) -> None:
        """Export benchmark data to CSV.

        If detailed per-scenario data exists, writes a full report.
        Otherwise writes a summary row.

        Args:
            path: Output CSV file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        if self.details:
            fieldnames = ["scenario_id", "success", "latency_s", "tokens", "error"]
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for idx, item in enumerate(self.details, start=1):
                    row = {
                        "scenario_id": idx,
                        "success": item.get("success", False),
                        "latency_s": f"{item.get('latency', 0.0):.4f}",
                        "tokens": item.get("tokens", 0),
                        "error": item.get("error", ""),
                    }
                    writer.writerow(row)
        else:
            # Summary only
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["metric", "value"])
                writer.writerow(["accuracy", f"{self.accuracy:.4f}"])
                writer.writerow(["mean_latency_s", f"{self.mean_latency:.4f}"])
                writer.writerow(["mean_tokens", f"{self.mean_tokens:.1f}"])
                writer.writerow(["total_runs", str(self.total_runs)])


class BenchmarkRunner:
    """Runs a skill against a list of scenario contexts and aggregates metrics.

    Accuracy is currently derived from the success flag on SkillResult.
    Latency and token counts are measured / estimated. Real-world usage
    would replace the mock judge with an LLM evaluator.
    """

    def run(self, skill: Skill, scenarios: List[Dict[str, Any]]) -> BenchmarkReport:
        """Execute benchmark.

        Args:
            skill: Skill instance to benchmark.
            scenarios: List of context dictionaries.

        Returns:
            BenchmarkReport with statistics.

        Raises:
            TypeError: If skill is not a Skill.
            ValueError: If scenarios is empty or malformed.
        """
        if not isinstance(skill, Skill):
            raise TypeError(
                f"Expected Skill instance, received {type(skill).__name__}. "
                "Wrap with @skill or inherit from Skill."
            )
        if not scenarios or not isinstance(scenarios, list):
            raise ValueError("scenarios must be a non-empty list of dicts")

        latencies: List[float] = []
        token_counts: List[int] = []
        successes = 0
        details: List[Dict[str, Any]] = []

        for i, scenario in enumerate(scenarios):
            if not isinstance(scenario, dict):
                raise ValueError(f"Scenario at index {i} must be a dict, got {type(scenario)}")

            start = time.perf_counter()
            try:
                result: SkillResult = skill.execute(scenario)
                latency = time.perf_counter() - start

                success = isinstance(result, SkillResult) and result.success
                if success:
                    successes += 1

                # Mock token usage based on output size (real implementation would count LLM tokens)
                output_str = str(result.output) if result.output is not None else ""
                tokens = 45 + (len(output_str) // 3) + (15 if success else 5)

                latencies.append(latency)
                token_counts.append(tokens)

                details.append(
                    {
                        "scenario": scenario,
                        "success": success,
                        "latency": latency,
                        "tokens": tokens,
                        "output_preview": str(result.output)[:80]
                        + ("..." if len(str(result.output)) > 80 else ""),
                    }
                )
            except Exception as exc:
                latency = time.perf_counter() - start
                latencies.append(latency)
                token_counts.append(20)
                details.append(
                    {
                        "scenario": scenario,
                        "success": False,
                        "latency": latency,
                        "tokens": 20,
                        "error": str(exc),
                    }
                )

        total = len(scenarios)
        accuracy = successes / total if total > 0 else 0.0
        mean_latency = sum(latencies) / total if total > 0 else 0.0
        mean_tokens = sum(token_counts) / total if total > 0 else 0.0

        return BenchmarkReport(
            accuracy=round(accuracy, 4),
            mean_latency=round(mean_latency, 4),
            mean_tokens=round(mean_tokens, 2),
            total_runs=total,
            details=details,
        )
