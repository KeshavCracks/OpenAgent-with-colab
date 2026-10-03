from openagent.agent.scheduler import SchedulerStore, tick


def test_add_and_list(tmp_path):
    store = SchedulerStore(tmp_path / "schedule.json")
    task = store.add("nightly-tests", 3600, "shell:pytest -q")
    tasks = store.list()
    assert len(tasks) == 1
    assert tasks[0].id == task.id
    assert tasks[0].action == "shell:pytest -q"


def test_task_not_due_before_interval_elapses(tmp_path):
    store = SchedulerStore(tmp_path / "schedule.json")
    store.add("daily", 86400, "skill:research-citations")
    due_immediately = store.due()
    assert len(due_immediately) == 1  # next_run_at defaults to creation time == now


def test_tick_runs_due_tasks_and_reschedules(tmp_path):
    store = SchedulerStore(tmp_path / "schedule.json")
    store.add("task-a", 100, "shell:echo hi")
    calls = []

    def runner(task):
        calls.append(task.name)
        return {"ran": True}

    # the task's next_run_at defaults to its creation time, so it is due "now"
    results = tick(store, runner)
    assert len(results) == 1
    assert calls == ["task-a"]

    ran_at = store.list()[0].last_run_at

    # immediately after running, it should not be due again
    assert store.due(now=ran_at + 0.5) == []
    # but is due again after its interval elapses
    assert len(store.due(now=ran_at + 101)) == 1


def test_disabled_task_never_due(tmp_path):
    store = SchedulerStore(tmp_path / "schedule.json")
    task = store.add("disabled-task", 1, "shell:echo hi")
    tasks = store._load()
    tasks[0]["enabled"] = False
    store._save(tasks)
    assert store.due(now=999999) == []


def test_remove_task(tmp_path):
    store = SchedulerStore(tmp_path / "schedule.json")
    task = store.add("to-remove", 60, "shell:echo hi")
    assert store.remove(task.id) is True
    assert store.list() == []
    assert store.remove(task.id) is False
