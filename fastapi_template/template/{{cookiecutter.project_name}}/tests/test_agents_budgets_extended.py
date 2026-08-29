import time

import pytest

from {{cookiecutter.project_name}}.agents.budgets import Budget, BudgetExhausted, BudgetTracker


def test_token_budget_exhaustion() -> None:
    tracker = BudgetTracker(Budget(max_tokens=100))
    tracker.add_usage(tokens=50)
    with pytest.raises(BudgetExhausted):
        tracker.add_usage(tokens=51)


def test_cost_budget_exhaustion() -> None:
    tracker = BudgetTracker(Budget(max_cost_usd=0.5))
    tracker.add_usage(cost_usd=0.4)
    with pytest.raises(BudgetExhausted):
        tracker.add_usage(cost_usd=0.11)


def test_step_budget_still_works() -> None:
    tracker = BudgetTracker(Budget(max_steps=2))
    tracker.step()
    tracker.step()
    with pytest.raises(BudgetExhausted):
        tracker.step()
