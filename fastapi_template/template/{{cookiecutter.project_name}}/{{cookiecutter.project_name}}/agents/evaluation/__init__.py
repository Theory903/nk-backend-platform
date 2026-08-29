"""
Production-grade agent evaluation harness.

Capabilities:
- Typed evaluation datasets
- YAML dataset loading with validation
- Deterministic substring evaluation
- Tool trajectory evaluation
- Async/sync runner support
- Async/sync LLM judge support
- Per-case timeout handling
- Concurrent execution with bounded parallelism
- Retrieval metrics: Precision@K, Recall@K, F1@K, MRR, NDCG@K
- Structured evaluation reports
- JSON-serializable reports
- Deterministic report aggregation
- Explicit execution/evaluation errors

The module intentionally keeps the core dependency-free except for PyYAML
when YAML loading is used.
"""

from __future__ import annotations

import asyncio
import inspect
import math
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeAlias


# ============================================================================
# Types
# ============================================================================

RunnerResult: TypeAlias = Any
Runner: TypeAlias = Callable[[str], RunnerResult | Awaitable[RunnerResult]]
Judge: TypeAlias = Callable[
    [str, str],
    float | Awaitable[float],
]


class SupportsClose(Protocol):
    def close(self) -> Any:
        ...


# ============================================================================
# Exceptions
# ============================================================================


class EvalError(Exception):
    """Base exception for evaluation errors."""


class DatasetError(EvalError):
    """Raised when an evaluation dataset is invalid."""


class EvaluationError(EvalError):
    """Raised when evaluation itself fails."""


class EvaluationTimeout(EvalError):
    """Raised when a case exceeds its configured timeout."""


# ============================================================================
# Dataset models
# ============================================================================


@dataclass(frozen=True, slots=True)
class EvalCase:
    """
    A single agent evaluation case.

    expected_contains:
        Strings that must occur in the final output.

    expected_tools:
        Tools that must have been called.

    metadata:
        Arbitrary structured data associated with the case.
    """

    name: str
    input: str
    expected_contains: tuple[str, ...] = ()
    expected_tools: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        name = self.name.strip()
        user_input = self.input.strip()

        if not name:
            raise DatasetError("EvalCase.name cannot be empty.")

        if not user_input:
            raise DatasetError(
                f"EvalCase[{name!r}].input cannot be empty."
            )

        if any(not item.strip() for item in self.expected_contains):
            raise DatasetError(
                f"EvalCase[{name!r}].expected_contains contains an empty value."
            )

        if any(not item.strip() for item in self.expected_tools):
            raise DatasetError(
                f"EvalCase[{name!r}].expected_tools contains an empty value."
            )


@dataclass(frozen=True, slots=True)
class EvalConfig:
    """Execution configuration for an evaluation run."""

    max_concurrency: int = 8
    timeout_s: float | None = 120.0
    fail_fast: bool = False

    def __post_init__(self) -> None:
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be > 0.")

        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ValueError("timeout_s must be > 0 or None.")


# ============================================================================
# Result models
# ============================================================================


@dataclass(slots=True)
class EvalResult:
    """Result of evaluating one case."""

    case: EvalCase
    passed: bool
    actual: str
    score: float = 0.0
    duration_s: float = 0.0
    error: str | None = None

    # Optional trajectory information.
    actual_tools: tuple[str, ...] = ()

    # Separate execution/evaluation state.
    execution_ok: bool = True
    evaluation_ok: bool = True

    @property
    def failed(self) -> bool:
        return not self.passed


@dataclass(slots=True)
class EvalReport:
    """Aggregated evaluation report."""

    total: int
    passed: int
    failed: int
    avg_score: float
    results: list[EvalResult] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def failure_rate(self) -> float:
        return 1.0 - self.pass_rate if self.total else 0.0

    @property
    def errors(self) -> int:
        return sum(1 for result in self.results if result.error is not None)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


# ============================================================================
# Dataset loading
# ============================================================================


def load_dataset_yaml(path: str | Path) -> list[EvalCase]:
    """
    Load and validate evaluation cases from YAML.

    Expected structure:

        cases:
          - name: basic_search
            input: "Find ..."
            expected_contains:
              - "..."
            expected_tools:
              - search
            metadata:
              category: retrieval
    """
    dataset_path = Path(path)

    if not dataset_path.exists():
        raise DatasetError(f"Dataset does not exist: {dataset_path}")

    if not dataset_path.is_file():
        raise DatasetError(f"Dataset path is not a file: {dataset_path}")

    try:
        import yaml
    except ImportError as exc:
        raise DatasetError(
            "PyYAML is required to load YAML datasets."
        ) from exc

    try:
        raw = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DatasetError(
            f"Failed to parse YAML dataset {dataset_path}: {exc}"
        ) from exc

    if raw is None:
        return []

    if not isinstance(raw, Mapping):
        raise DatasetError(
            "Dataset root must be a mapping containing a 'cases' field."
        )

    raw_cases = raw.get("cases", [])

    if not isinstance(raw_cases, list):
        raise DatasetError("'cases' must be a list.")

    cases: list[EvalCase] = []

    for index, item in enumerate(raw_cases):
        if not isinstance(item, Mapping):
            raise DatasetError(
                f"Case at index {index} must be a mapping."
            )

        try:
            name = _require_string(item, "name")
            user_input = _require_string(item, "input")

            expected_contains = _string_tuple(
                item.get("expected_contains", ()),
                field_name="expected_contains",
            )

            expected_tools = _string_tuple(
                item.get("expected_tools", ()),
                field_name="expected_tools",
            )

            metadata = item.get("metadata", {})

            if not isinstance(metadata, Mapping):
                raise DatasetError(
                    f"Case {name!r}: metadata must be a mapping."
                )

            cases.append(
                EvalCase(
                    name=name,
                    input=user_input,
                    expected_contains=expected_contains,
                    expected_tools=expected_tools,
                    metadata=dict(metadata),
                )
            )
        except DatasetError:
            raise
        except Exception as exc:
            raise DatasetError(
                f"Invalid case at index {index}: {exc}"
            ) from exc

    _validate_unique_case_names(cases)

    return cases


def _require_string(
    mapping: Mapping[str, Any],
    key: str,
) -> str:
    value = mapping.get(key)

    if not isinstance(value, str):
        raise DatasetError(
            f"{key!r} must be a string."
        )

    value = value.strip()

    if not value:
        raise DatasetError(
            f"{key!r} cannot be empty."
        )

    return value


def _string_tuple(
    value: Any,
    *,
    field_name: str,
) -> tuple[str, ...]:
    if value is None:
        return ()

    if isinstance(value, str):
        raise DatasetError(
            f"{field_name!r} must be a list of strings, not a string."
        )

    if not isinstance(value, Sequence):
        raise DatasetError(
            f"{field_name!r} must be a list of strings."
        )

    result: list[str] = []

    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise DatasetError(
                f"{field_name}[{index}] must be a string."
            )

        item = item.strip()

        if not item:
            raise DatasetError(
                f"{field_name}[{index}] cannot be empty."
            )

        result.append(item)

    return tuple(result)


def _validate_unique_case_names(
    cases: Sequence[EvalCase],
) -> None:
    seen: set[str] = set()

    for case in cases:
        if case.name in seen:
            raise DatasetError(
                f"Duplicate evaluation case name: {case.name!r}"
            )

        seen.add(case.name)


# ============================================================================
# Async execution utilities
# ============================================================================


async def _maybe_await(value: Any) -> Any:
    """Await a value if it is awaitable; otherwise return it unchanged."""
    if inspect.isawaitable(value):
        return await value

    return value


async def _run_with_timeout(
    runner: Runner,
    user_input: str,
    timeout_s: float | None,
) -> Any:
    """Execute a runner with an optional timeout."""
    try:
        result = runner(user_input)

        if timeout_s is None:
            return await _maybe_await(result)

        return await asyncio.wait_for(
            _maybe_await(result),
            timeout=timeout_s,
        )

    except asyncio.TimeoutError as exc:
        raise EvaluationTimeout(
            f"Runner exceeded timeout of {timeout_s:.2f}s."
        ) from exc


# ============================================================================
# Substring evaluation
# ============================================================================


def evaluate_substrings(
    actual: str,
    expected_contains: Iterable[str],
    *,
    case_sensitive: bool = True,
) -> tuple[bool, float]:
    """
    Evaluate required substrings.

    Returns:
        (passed, score)

    Score is the fraction of required substrings found.
    """
    expected = tuple(expected_contains)

    if not expected:
        return True, 1.0

    if case_sensitive:
        haystack = actual
        needles = expected
    else:
        haystack = actual.casefold()
        needles = tuple(item.casefold() for item in expected)

    hits = sum(needle in haystack for needle in needles)
    score = hits / len(needles)

    return hits == len(needles), score


# ============================================================================
# Tool trajectory evaluation
# ============================================================================


def check_trajectory(
    actual_tools: Sequence[str],
    expected_tools: Sequence[str],
) -> bool:
    """
    Check that all expected tools were called.

    Order-insensitive.

    Unlike a naive set comparison, this deliberately treats expected tools
    as requirements rather than requiring the exact trajectory.
    """
    if not expected_tools:
        return True

    actual = set(actual_tools)

    return all(tool in actual for tool in expected_tools)


def check_trajectory_exact(
    actual_tools: Sequence[str],
    expected_tools: Sequence[str],
) -> bool:
    """Require an exact ordered tool trajectory."""
    return tuple(actual_tools) == tuple(expected_tools)


def check_trajectory_ordered_subset(
    actual_tools: Sequence[str],
    expected_tools: Sequence[str],
) -> bool:
    """
    Check whether expected tools occur in order inside the actual trajectory.

    Example:

        actual   = [search, rank, summarize]
        expected = [search, summarize]

    returns True.
    """
    if not expected_tools:
        return True

    expected_index = 0

    for tool in actual_tools:
        if tool == expected_tools[expected_index]:
            expected_index += 1

            if expected_index == len(expected_tools):
                return True

    return False


# ============================================================================
# Single-case execution
# ============================================================================


async def _execute_case(
    runner: Runner,
    case: EvalCase,
    *,
    config: EvalConfig,
    evaluator: Callable[[str, EvalCase], tuple[bool, float]],
) -> EvalResult:
    case_start = time.monotonic()

    try:
        raw = await _run_with_timeout(
            runner,
            case.input,
            config.timeout_s,
        )

        actual_tools: tuple[str, ...]

        if isinstance(raw, Mapping) and "output" in raw:
            actual = str(raw["output"])

            tools = raw.get("tools", ())
            actual_tools = tuple(str(tool) for tool in tools)
        else:
            actual = str(raw)
            actual_tools = ()

        passed, score = evaluator(actual, case)

        return EvalResult(
            case=case,
            passed=passed,
            actual=actual,
            score=_clamp_score(score),
            duration_s=time.monotonic() - case_start,
            actual_tools=actual_tools,
            execution_ok=True,
            evaluation_ok=True,
        )

    except EvaluationTimeout as exc:
        return EvalResult(
            case=case,
            passed=False,
            actual="",
            score=0.0,
            duration_s=time.monotonic() - case_start,
            error=str(exc),
            execution_ok=False,
            evaluation_ok=False,
        )

    except Exception as exc:
        return EvalResult(
            case=case,
            passed=False,
            actual="",
            score=0.0,
            duration_s=time.monotonic() - case_start,
            error=f"{type(exc).__name__}: {exc}",
            execution_ok=False,
            evaluation_ok=False,
        )


# ============================================================================
# Generic evaluation runner
# ============================================================================


async def run_eval(
    runner: Runner,
    cases: Sequence[EvalCase],
    evaluator: Callable[[str, EvalCase], tuple[bool, float]],
    *,
    config: EvalConfig | None = None,
) -> EvalReport:
    """
    Generic async evaluation engine.

    Supports:
    - synchronous runners
    - asynchronous runners
    - bounded concurrency
    - timeouts
    """
    config = config or EvalConfig()

    start = time.monotonic()

    if not cases:
        return EvalReport(
            total=0,
            passed=0,
            failed=0,
            avg_score=0.0,
            results=[],
            duration_s=0.0,
        )

    semaphore = asyncio.Semaphore(config.max_concurrency)

    async def execute(case: EvalCase) -> EvalResult:
        async with semaphore:
            return await _execute_case(
                runner,
                case,
                config=config,
                evaluator=evaluator,
            )

    if config.fail_fast:
        results: list[EvalResult] = []

        for case in cases:
            result = await execute(case)
            results.append(result)

            if not result.passed:
                break
    else:
        results = list(
            await asyncio.gather(
                *(execute(case) for case in cases)
            )
        )

    return _build_report(
        results,
        start=start,
    )


# ============================================================================
# Public substring evaluator
# ============================================================================


async def run_substring_eval(
    runner: Runner,
    cases: Sequence[EvalCase],
    *,
    case_sensitive: bool = True,
    config: EvalConfig | None = None,
) -> EvalReport:
    """
    Run deterministic substring evaluation.
    """

    def evaluator(
        actual: str,
        case: EvalCase,
    ) -> tuple[bool, float]:
        passed, score = evaluate_substrings(
            actual,
            case.expected_contains,
            case_sensitive=case_sensitive,
        )

        if passed and case.expected_tools:
            # Tool requirements only apply when the runner exposes tools.
            # Tool-aware runners should return:
            # {"output": "...", "tools": ["search", "calculator"]}
            return passed, score

        return passed, score

    report = await run_eval(
        runner,
        cases,
        evaluator,
        config=config,
    )

    # Apply tool requirements after execution.
    for result in report.results:
        if not result.passed:
            continue

        result.passed = check_trajectory(
            result.actual_tools,
            result.case.expected_tools,
        )

    return _rebuild_report(report)


# ============================================================================
# LLM judge
# ============================================================================


async def run_llm_judge_eval(
    runner: Runner,
    judge_fn: Judge,
    cases: Sequence[EvalCase],
    *,
    threshold: float = 0.7,
    config: EvalConfig | None = None,
) -> EvalReport:
    """
    LLM-as-judge evaluation.

    judge_fn receives:
        (actual_output, expected_criteria)

    and returns:
        score in [0.0, 1.0]

    Both sync and async judge functions are supported.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0.")

    config = config or EvalConfig()

    start = time.monotonic()
    semaphore = asyncio.Semaphore(config.max_concurrency)

    async def execute(case: EvalCase) -> EvalResult:
        case_start = time.monotonic()

        async with semaphore:
            try:
                raw = await _run_with_timeout(
                    runner,
                    case.input,
                    config.timeout_s,
                )

                if isinstance(raw, Mapping) and "output" in raw:
                    actual = str(raw["output"])
                    actual_tools = tuple(
                        str(tool)
                        for tool in raw.get("tools", ())
                    )
                else:
                    actual = str(raw)
                    actual_tools = ()

                criteria = _build_judge_criteria(case)

                score_raw = judge_fn(actual, criteria)

                if config.timeout_s is None:
                    score = await _maybe_await(score_raw)
                else:
                    score = await asyncio.wait_for(
                        _maybe_await(score_raw),
                        timeout=config.timeout_s,
                    )

                score = _validate_score(score)

                trajectory_ok = check_trajectory(
                    actual_tools,
                    case.expected_tools,
                )

                passed = (
                    score >= threshold
                    and trajectory_ok
                )

                return EvalResult(
                    case=case,
                    passed=passed,
                    actual=actual,
                    score=score,
                    duration_s=time.monotonic() - case_start,
                    actual_tools=actual_tools,
                    execution_ok=True,
                    evaluation_ok=True,
                )

            except asyncio.TimeoutError:
                return EvalResult(
                    case=case,
                    passed=False,
                    actual="",
                    score=0.0,
                    duration_s=time.monotonic() - case_start,
                    error=(
                        f"Evaluation exceeded timeout of "
                        f"{config.timeout_s:.2f}s."
                    ),
                    execution_ok=False,
                    evaluation_ok=False,
                )

            except Exception as exc:
                return EvalResult(
                    case=case,
                    passed=False,
                    actual="",
                    score=0.0,
                    duration_s=time.monotonic() - case_start,
                    error=f"{type(exc).__name__}: {exc}",
                    execution_ok=False,
                    evaluation_ok=False,
                )

    if config.fail_fast:
        results: list[EvalResult] = []

        for case in cases:
            result = await execute(case)
            results.append(result)

            if not result.passed:
                break
    else:
        results = list(
            await asyncio.gather(
                *(execute(case) for case in cases)
            )
        )

    return _build_report(
        results,
        start=start,
    )


def _build_judge_criteria(case: EvalCase) -> str:
    """
    Convert structured case expectations into judge criteria.

    Metadata can optionally provide richer criteria:

        metadata:
          judge_criteria: "The answer must..."
    """
    explicit = case.metadata.get("judge_criteria")

    if explicit is not None:
        if not isinstance(explicit, str):
            raise DatasetError(
                f"Case {case.name!r}: judge_criteria must be a string."
            )

        return explicit

    if case.expected_contains:
        return "; ".join(case.expected_contains)

    return "Evaluate the overall quality, correctness, relevance, and completeness."


# ============================================================================
# Retrieval metrics
# ============================================================================


def precision_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k: int,
) -> float:
    """
    Precision@K.

    Relevant retrieved items / number of evaluated retrieved items.
    """
    if k <= 0:
        return 0.0

    top_k = tuple(retrieved_ids[:k])

    if not top_k:
        return 0.0

    hits = sum(item in relevant_ids for item in top_k)

    return hits / len(top_k)


def recall_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k: int,
) -> float:
    """
    Recall@K.

    Relevant retrieved items / total relevant items.
    """
    if k <= 0 or not relevant_ids:
        return 0.0

    top_k = tuple(retrieved_ids[:k])
    hits = sum(item in relevant_ids for item in top_k)

    return min(hits / len(relevant_ids), 1.0)


def f1_at_k(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
    k: int,
) -> float:
    """F1 score derived from Precision@K and Recall@K."""
    precision = precision_at_k(
        retrieved_ids,
        relevant_ids,
        k,
    )

    recall = recall_at_k(
        retrieved_ids,
        relevant_ids,
        k,
    )

    if precision + recall == 0.0:
        return 0.0

    return 2.0 * precision * recall / (precision + recall)


def reciprocal_rank(
    retrieved_ids: Sequence[str],
    relevant_ids: set[str],
) -> float:
    """
    Reciprocal rank of the first relevant result.
    """
    if not relevant_ids:
        return 0.0

    for rank, item_id in enumerate(retrieved_ids, start=1):
        if item_id in relevant_ids:
            return 1.0 / rank

    return 0.0


def mean_reciprocal_rank(
    queries: Sequence[tuple[Sequence[str], set[str]]],
) -> float:
    """Mean Reciprocal Rank across queries."""
    if not queries:
        return 0.0

    scores = [
        reciprocal_rank(retrieved, relevant)
        for retrieved, relevant in queries
    ]

    return sum(scores) / len(scores)


def ndcg_at_k(
    retrieved_ids: Sequence[str],
    relevance: Mapping[str, float],
    k: int,
) -> float:
    """
    NDCG@K for graded relevance.

    relevance maps document IDs to relevance scores.

    Example:

        {
            "doc-a": 3,
            "doc-b": 2,
            "doc-c": 1,
        }
    """
    if k <= 0 or not relevance:
        return 0.0

    top_k = tuple(retrieved_ids[:k])

    dcg = 0.0

    for rank, item_id in enumerate(top_k, start=1):
        gain = float(relevance.get(item_id, 0.0))

        if gain <= 0:
            continue

        dcg += (2.0**gain - 1.0) / math.log2(rank + 1)

    ideal_scores = sorted(
        (
            max(float(score), 0.0)
            for score in relevance.values()
        ),
        reverse=True,
    )[:k]

    idcg = sum(
        (2.0**score - 1.0) / math.log2(rank + 1)
        for rank, score in enumerate(ideal_scores, start=1)
    )

    if idcg == 0.0:
        return 0.0

    return dcg / idcg


# ============================================================================
# Report aggregation
# ============================================================================


def _build_report(
    results: Sequence[EvalResult],
    *,
    start: float,
) -> EvalReport:
    total = len(results)
    passed = sum(result.passed for result in results)

    # Include zero scores. A zero is a real evaluation result.
    avg_score = (
        sum(result.score for result in results) / total
        if total
        else 0.0
    )

    return EvalReport(
        total=total,
        passed=passed,
        failed=total - passed,
        avg_score=avg_score,
        results=list(results),
        duration_s=time.monotonic() - start,
    )


def _rebuild_report(report: EvalReport) -> EvalReport:
    """Recalculate aggregate values after post-processing."""
    total = len(report.results)
    passed = sum(result.passed for result in report.results)

    return EvalReport(
        total=total,
        passed=passed,
        failed=total - passed,
        avg_score=(
            sum(result.score for result in report.results) / total
            if total
            else 0.0
        ),
        results=report.results,
        duration_s=report.duration_s,
    )


# ============================================================================
# Score validation
# ============================================================================


def _validate_score(score: Any) -> float:
    """
    Validate and normalize judge scores.

    Rejects:
    - non-numeric values
    - NaN
    - infinity
    - values outside [0, 1]
    """
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise EvaluationError(
            f"Judge returned invalid score type: {type(score).__name__}"
        )

    value = float(score)

    if not math.isfinite(value):
        raise EvaluationError(
            "Judge returned a non-finite score."
        )

    if not 0.0 <= value <= 1.0:
        raise EvaluationError(
            f"Judge score must be between 0 and 1; got {value}."
        )

    return value


def _clamp_score(score: float) -> float:
    """Safely clamp internally generated scores."""
    return min(max(float(score), 0.0), 1.0)


# ============================================================================
# Convenience synchronous wrappers
# ============================================================================


def run_substring_eval_sync(
    runner: Runner,
    cases: Sequence[EvalCase],
    *,
    case_sensitive: bool = True,
    config: EvalConfig | None = None,
) -> EvalReport:
    """
    Synchronous convenience wrapper.

    Do not call from an already-running event loop.
    """
    return asyncio.run(
        run_substring_eval(
            runner,
            cases,
            case_sensitive=case_sensitive,
            config=config,
        )
    )


def run_llm_judge_eval_sync(
    runner: Runner,
    judge_fn: Judge,
    cases: Sequence[EvalCase],
    *,
    threshold: float = 0.7,
    config: EvalConfig | None = None,
) -> EvalReport:
    """
    Synchronous convenience wrapper.

    Do not call from an already-running event loop.
    """
    return asyncio.run(
        run_llm_judge_eval(
            runner,
            judge_fn,
            cases,
            threshold=threshold,
            config=config,
        )
    )


# ============================================================================
# Formatting
# ============================================================================


def format_report(report: EvalReport) -> str:
    """Render a compact human-readable evaluation report."""
    lines = [
        "Evaluation Report",
        "=================",
        f"Total:      {report.total}",
        f"Passed:     {report.passed}",
        f"Failed:     {report.failed}",
        f"Pass rate:  {report.pass_rate:.1%}",
        f"Avg score:  {report.avg_score:.3f}",
        f"Errors:     {report.errors}",
        f"Duration:   {report.duration_s:.2f}s",
        "",
    ]

    for result in report.results:
        status = "PASS" if result.passed else "FAIL"

        line = (
            f"[{status}] {result.case.name} "
            f"score={result.score:.3f} "
            f"time={result.duration_s:.2f}s"
        )

        if result.error:
            line += f" error={result.error}"

        lines.append(line)

    return "\n".join(lines)


__all__ = [
    "DatasetError",
    "EvalCase",
    "EvalConfig",
    "EvalError",
    "EvalReport",
    "EvalResult",
    "EvaluationError",
    "EvaluationTimeout",
    "check_trajectory",
    "check_trajectory_exact",
    "check_trajectory_ordered_subset",
    "evaluate_substrings",
    "f1_at_k",
    "format_report",
    "load_dataset_yaml",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    "run_eval",
    "run_llm_judge_eval",
    "run_llm_judge_eval_sync",
    "run_substring_eval",
    "run_substring_eval_sync",
]