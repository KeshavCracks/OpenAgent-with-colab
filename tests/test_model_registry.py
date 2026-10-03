import pytest

from openagent.models.registry import RegistryError, load_registry, select_for_phase


def test_registry_loads_and_validates():
    registry = load_registry()
    assert registry.default_model_id == "qwen3.8-27b-gguf-q4km"
    assert "qwen3.8-27b-gguf-q4km" in registry.ids()


def test_default_model_is_available_and_apache():
    registry = load_registry()
    default = registry.default()
    assert default.status == "available"
    assert default.raw["license"] == "Apache-2.0"


def test_every_available_gguf_has_pinned_sha256_and_revision():
    registry = load_registry()
    for m in registry.available():
        if m.source.get("format") == "gguf":
            assert m.sha256, f"{m.id} missing pinned sha256"
            assert len(m.sha256) == 64
            assert m.revision, f"{m.id} missing pinned revision"


def test_orcasaq2_is_gated_and_not_gate_passed():
    registry = load_registry()
    entry = registry.get("orcasaq2-cyber-27b-uncensored")
    assert entry.status == "gated"
    assert entry.requires_authenticated_download is True
    assert entry.gate_passed is False


def test_clef_is_decision_router_only():
    registry = load_registry()
    entry = registry.get("cloudflare-clef-27b")
    assert entry.role == ["decision_router"]
    assert "planner" not in entry.role
    assert "executor" not in entry.role


def test_deephat_is_not_qwen35_family():
    registry = load_registry()
    entry = registry.get("deephat-v1-7b-official")
    assert entry.raw["architecture"] != "qwen3_5"
    assert entry.raw["family"] == "deephat-v1"


def test_select_for_phase_returns_default_when_eligible():
    registry = load_registry()
    entry = select_for_phase(registry, "plan")
    assert entry.id == registry.default_model_id


def test_select_for_phase_embedding():
    registry = load_registry()
    entry = select_for_phase(registry, "embed")
    assert "embedding" in entry.role


def test_select_for_phase_unknown_raises():
    registry = load_registry()
    with pytest.raises(ValueError):
        select_for_phase(registry, "not_a_real_phase")


def test_fits_hardware_budget():
    registry = load_registry()
    q4 = registry.get("qwen3.8-27b-gguf-q4km")
    assert q4.fits(vram_gb=15, ram_gb=12) is True
    assert q4.fits(vram_gb=8, ram_gb=12) is False


def test_registry_rejects_bad_status(tmp_path):
    bad_yaml = tmp_path / "bad_registry.yaml"
    bad_yaml.write_text(
        "schema_version: 1\ndefault_model_id: a\nmodels:\n"
        "  - id: a\n    role: [planner]\n    status: not_a_real_status\n"
        "    source: {}\n    license: MIT\n    benchmark_status: vendor_claims_unverified\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError):
        load_registry(bad_yaml)
