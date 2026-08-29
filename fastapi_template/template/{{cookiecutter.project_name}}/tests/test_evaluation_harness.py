"""Tests for evaluation harness: substring eval, LLM judge, retrieval metrics, trajectory."""
import pytest

from {{cookiecutter.project_name}}.agents.evaluation import (
    EvalCase,
    EvalReport,
    check_trajectory,
    precision_at_k,
    recall_at_k,
    run_substring_eval_sync as run_substring_eval,
)


class TestSubstringEval:
    def test_all_pass(self) -> None:
        cases = [
            EvalCase(name="greeting", input="say hi", expected_contains=["hello"]),
            EvalCase(name="math", input="2+2", expected_contains=["4"]),
        ]
        report = run_substring_eval(lambda inp: f"hello Response to: {inp} → 4", cases)
        assert report.passed == 2
        assert report.failed == 0
        assert report.pass_rate == 1.0

    def test_failure_detected(self) -> None:
        cases = [
            EvalCase(name="test", input="x", expected_contains=["MISSING_TOKEN"]),
        ]
        report = run_substring_eval(lambda inp: "no match here", cases)
        assert report.passed == 0
        assert report.failed == 1
        assert report.pass_rate == 0.0

    def test_runner_exception_captured(self) -> None:
        def bad_runner(inp: str) -> str:
            raise RuntimeError("LLM exploded")
        cases = [EvalCase(name="boom", input="trigger")]
        report = run_substring_eval(bad_runner, cases)
        assert report.failed == 1
        assert report.results[0].error is not None


class TestRetrievalMetrics:
    def test_precision_at_k_perfect(self) -> None:
        retrieved = ["a", "b", "c"]
        relevant = {"a", "b"}
        assert precision_at_k(retrieved, relevant, k=2) == 1.0

    def test_precision_at_k_partial(self) -> None:
        retrieved = ["a", "x", "b"]
        relevant = {"a", "b"}
        assert precision_at_k(retrieved, relevant, k=3) == pytest.approx(2/3)

    def test_recall_at_k_full(self) -> None:
        retrieved = ["a", "b", "c"]
        relevant = {"a", "b"}
        assert recall_at_k(retrieved, relevant, k=3) == 1.0

    def test_recall_at_k_partial(self) -> None:
        retrieved = ["a"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(retrieved, relevant, k=1) == pytest.approx(1/3)


class TestTrajectoryCheck:
    def test_expected_tools_called(self) -> None:
        actual = ["search_web", "read_file", "summarize"]
        expected = ["search_web", "summarize"]
        assert check_trajectory(actual, expected) is True

    def test_missing_tool_fails(self) -> None:
        actual = ["search_web"]
        expected = ["search_web", "write_file"]
        assert check_trajectory(actual, expected) is False

    def test_no_requirements_passes(self) -> None:
        assert check_trajectory(["anything"], []) is True


class TestEvalReport:
    def test_report_properties(self) -> None:
        from {{cookiecutter.project_name}}.agents.evaluation import EvalResult
        results = [
            EvalResult(case=EvalCase(name="a", input="x"), passed=True, actual="ok", score=0.9),
            EvalResult(case=EvalCase(name="b", input="y"), passed=False, actual="bad", score=0.3),
        ]
        report = EvalReport(total=2, passed=1, failed=1, avg_score=0.6, results=results)
        assert report.pass_rate == 0.5
        assert len(report.results) == 2
