import pytest

from openagent.orchestration.budgets import Budget, BudgetExceededError
from openagent.orchestration.patterns import PlannerWorkerReviewer, StepContract


def test_budget_tool_call_limit():
    budget = Budget(max_tool_calls=2)
    budget.record_tool_call()
    budget.record_tool_call()
    with pytest.raises(BudgetExceededError):
        budget.record_tool_call()


def test_budget_token_limit():
    budget = Budget(max_tokens=100)
    budget.record_tokens(60)
    with pytest.raises(BudgetExceededError):
        budget.record_tokens(60)


def test_budget_wall_clock_limit():
    budget = Budget(max_wall_seconds=0.001)
    import time
    time.sleep(0.01)
    with pytest.raises(BudgetExceededError):
        budget.check_wall_clock()


def test_step_succeeds_and_checkpoints():
    checkpoints = []
    orch = PlannerWorkerReviewer(on_checkpoint=lambda r: checkpoints.append(r.name))
    step = StepContract(name="build", action=lambda: 42, postconditions=[lambda out: out == 42])
    result = orch.run_step(step)
    assert result.ok is True
    assert result.output == 42
    assert checkpoints == ["build"]


def test_step_retries_then_succeeds():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient failure")
        return "ok"

    orch = PlannerWorkerReviewer()
    step = StepContract(name="flaky-step", action=flaky, max_retries=3)
    result = orch.run_step(step)
    assert result.ok is True
    assert result.attempts == 3


def test_step_fails_after_exhausting_retries_and_rolls_back():
    rollbacks = []
    orch = PlannerWorkerReviewer(on_rollback=lambda r: rollbacks.append(r.name))
    step = StepContract(name="always-fails", action=lambda: (_ for _ in ()).throw(RuntimeError("nope")), max_retries=1)
    result = orch.run_step(step)
    assert result.ok is False
    assert rollbacks == ["always-fails"]


def test_precondition_blocks_action():
    called = {"n": 0}

    def action():
        called["n"] += 1
        return 1

    step = StepContract(name="gated", action=action, preconditions=[lambda: False])
    orch = PlannerWorkerReviewer()
    result = orch.run_step(step)
    assert result.ok is False
    assert called["n"] == 0


def test_run_plan_stops_on_failure_by_default():
    orch = PlannerWorkerReviewer()
    steps = [
        StepContract(name="ok1", action=lambda: 1),
        StepContract(name="fail", action=lambda: (_ for _ in ()).throw(RuntimeError("x")), max_retries=0),
        StepContract(name="never-runs", action=lambda: 3),
    ]
    results = orch.run_plan(steps)
    assert [r.name for r in results] == ["ok1", "fail"]


def test_postcondition_failure_counts_as_failed_attempt():
    orch = PlannerWorkerReviewer()
    step = StepContract(name="bad-output", action=lambda: "wrong", postconditions=[lambda out: out == "right"],
                         max_retries=0)
    result = orch.run_step(step)
    assert result.ok is False
