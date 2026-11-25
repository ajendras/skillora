"""Testing utilities for Skillora skills.

TestGenerator creates deterministic test cases (and placeholders for LLM-as-judge
scenarios) from a skill's metadata. SkillTester executes those cases and returns
a report with pass rate and simulated judge score.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from .core import Skill, SkillResult


class TestCase(BaseModel):
    """Single test scenario for a skill."""

    description: str
    input: Dict[str, Any]
    expected_output: Any = None
    judge_prompt: str | None = None


class TestReport(BaseModel):
    """Aggregated test results."""

    pass_rate: float = Field(..., ge=0.0, le=1.0)
    judge_score: float = Field(..., ge=0.0, le=10.0)
    total_tests: int
    passed: int
    details: List[str] = Field(default_factory=list)


class TestGenerator:
    """Generates a battery of test cases from skill metadata.

    Produces both simple deterministic cases and synthetic LLM-judge prompts.
    """

    def generate(self, skill: Skill, count: int = 12) -> List[TestCase]:
        """Generate test cases for the provided skill.

        Args:
            skill: The skill under test.
            count: Number of test cases to generate (default 12).

        Returns:
            List of TestCase objects.

        Raises:
            TypeError: If skill is not a Skill instance.
            ValueError: If count is invalid.
        """
        if not isinstance(skill, Skill):
            raise TypeError("generate() expects a Skill instance")
        if count < 1:
            raise ValueError("count must be >= 1")
        if count > 100:
            count = 100  # reasonable cap

        meta = skill.metadata
        cases: List[TestCase] = []

        # Deterministic base patterns
        templates = [
            {"query": f"Basic usage of {meta.name}"},
            {"query": f"Edge case for {meta.name}", "edge": True},
            {"parameters": {"temperature": 0.7, "max_tokens": 100}},
            {"context": {"user_id": "test-user-123", "session": "abc"}},
            {},  # empty context test
        ]

        for i in range(count):
            template = templates[i % len(templates)].copy()
            if "query" in template:
                template["query"] += f" - variant {i + 1}"

            cases.append(
                TestCase(
                    description=f"{meta.name} test {i + 1}: {meta.description[:35]}...",
                    input=template,
                    expected_output=None,
                    judge_prompt=(
                        f"On a scale of 0-10, how well does the output fulfill: "
                        f"'{meta.description}'? Consider correctness, completeness, "
                        f"and safety."
                    ),
                )
            )

        return cases


class SkillTester:
    """Executes test cases against a skill and produces a scored report.

    Uses simple success/failure for unit tests and a deterministic mock for
    the 'LLM-as-judge' score.
    """

    def run(self, skill: Skill, test_cases: List[TestCase]) -> TestReport:
        """Run all test cases and compute aggregate metrics.

        Args:
            skill: Skill to test.
            test_cases: Generated test cases.

        Returns:
            TestReport with pass_rate, judge_score, and details.

        Raises:
            TypeError, ValueError: On invalid arguments.
        """
        if not isinstance(skill, Skill):
            raise TypeError("run() expects a Skill instance")
        if not test_cases:
            raise ValueError("test_cases cannot be empty")

        details: List[str] = []
        passed = 0
        judge_scores: List[float] = []

        for case in test_cases:
            start = time.perf_counter()
            try:
                if not isinstance(case.input, dict):
                    raise ValueError("TestCase.input must be a dict")

                result = skill.execute(case.input)
                latency = time.perf_counter() - start

                if not isinstance(result, SkillResult):
                    result = SkillResult(
                        success=False,
                        error="Did not return a SkillResult instance",
                    )

                if result.success:
                    passed += 1
                    judge = 8.2 if latency < 2.0 else 6.5
                    details.append(
                        f"PASS | {case.description} | latency={latency:.3f}s | judge={judge:.1f}"
                    )
                else:
                    judge = 2.5
                    details.append(
                        f"FAIL | {case.description} | error={result.error} | latency={latency:.3f}s"
                    )
                judge_scores.append(judge)
            except Exception as exc:
                latency = time.perf_counter() - start
                judge = 1.0
                details.append(
                    f"ERROR | {case.description} | exception={type(exc).__name__} | latency={latency:.3f}s"
                )
                judge_scores.append(judge)

        pass_rate = passed / len(test_cases)
        avg_judge = sum(judge_scores) / len(judge_scores)

        return TestReport(
            pass_rate=round(pass_rate, 3),
            judge_score=round(avg_judge, 1),
            total_tests=len(test_cases),
            passed=passed,
            details=details,
        )
