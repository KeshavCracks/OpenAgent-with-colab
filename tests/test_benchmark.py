from openagent.benchmark.tasks.default_suite import build_default_suite


def test_default_suite_all_pass_offline():
    harness = build_default_suite()
    results = harness.run_all(model_id="fake-model")
    assert len(results) == 5
    assert all(r["passed"] for r in results), results


def test_compare_across_models():
    harness = build_default_suite()
    results_a = harness.run_all(model_id="model-a")
    results_b = harness.run_all(model_id="model-b")
    report = harness.compare({"model-a": results_a, "model-b": results_b})
    assert report["model-a"]["pass_rate"] == 1.0
    assert report["model-b"]["pass_rate"] == 1.0
    assert "smoke" in report["model-a"]["by_category"]
