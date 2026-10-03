import pytest

from openagent.models.registry import load_registry
from openagent.runtime.router import ModelRouter, VramBudgetExceededError


def test_load_for_plan_phase_loads_default_planner():
    registry = load_registry()
    router = ModelRouter(registry, vram_budget_gb=40)
    entry = router.load_for_phase("plan")
    assert entry.id == registry.default_model_id
    assert entry.id in router.resident_ids()


def test_small_embedding_model_stays_resident_alongside_large():
    registry = load_registry()
    router = ModelRouter(registry, vram_budget_gb=40)
    router.load_for_phase("plan")
    router.load_for_phase("embed")
    assert len(router.resident_ids()) == 2


def test_switching_large_model_evicts_previous_large_model():
    registry = load_registry()
    router = ModelRouter(registry, vram_budget_gb=40)
    router.load_for_phase("plan")
    router.load_for_phase("embed")
    router.load_for_phase("route")  # clef, decision_router role, also >=8GB "large"
    large_ids = [mid for mid in router.resident_ids()
                 if router._is_large(registry.get(mid))]
    assert len(large_ids) == 1
    # the small embedding model should not have been touched
    assert any(not router._is_large(registry.get(mid)) for mid in router.resident_ids())


def test_reloading_same_phase_is_a_noop_cache_hit():
    registry = load_registry()
    router = ModelRouter(registry, vram_budget_gb=40)
    router.load_for_phase("plan")
    first_log_len = len(router.swap_log)
    router.load_for_phase("plan")
    assert len(router.swap_log) == first_log_len


def test_budget_exceeded_raises_and_does_not_mutate_state():
    registry = load_registry()
    router = ModelRouter(registry, vram_budget_gb=5)
    with pytest.raises(VramBudgetExceededError):
        router.load_for_phase("plan")
    assert router.resident_ids() == []


def test_unload_all_clears_residency():
    registry = load_registry()
    router = ModelRouter(registry, vram_budget_gb=40)
    router.load_for_phase("plan")
    router.load_for_phase("embed")
    router.unload_all()
    assert router.resident_ids() == []
