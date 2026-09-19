"""G1-3 请求路径复验宿主的 seam/行为测试。不连库、不写库。

用内存桩替换 observer/registry 请求路径与 DB 读，验证六个封闭结算格各自可达，且：

* 未跑迁移（无历史 generation）→ `migration_not_run`，不误报通过；
* observer drift → `drift`；
* registry 未注册 / adapter 不一致 → `registry_mismatch`；
* generation 未增 → `version_domain_violation`；
* observer + registry 都通过且版本正交 → `verified`。
"""
import asyncio
import importlib.util
import types
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend/scripts/check/check_rehash_request_path_recheck.py"


def _load_module() -> types.ModuleType:
    import sys

    name = "g1_3_recheck_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rc = _load_module()

ENTRY = "xlsx/gt-test"
WP = uuid.uuid4()
PROJ = uuid.uuid4()


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """按 SQL 关键字回答两类查询：current 行 + generation 列表。"""

    def __init__(self, *, current, generations):
        self._current = current
        self._generations = generations

    async def execute(self, statement, params=None):  # noqa: ANN001
        text = str(statement)
        if "ORDER BY generation DESC" in text:
            return _Result([{"generation": g} for g in self._generations])
        if "current_representation_id" in text:
            return _Result([self._current] if self._current else [])
        if "WHERE id = :id" in text:
            # observer 前的整行读取：返回一份 shape 齐全的 row（observer 已被 monkeypatch，
            # 此处只需让 `full` 非 None，字段值不参与被 patch 的 observer）。
            return _Result([self._full_row()] if self._current else [])
        return _Result([])

    def _full_row(self):
        return {name: "x" for name in (
            "id", "wp_id", "entry_id", "content_version_id", "generation", "document_type",
            "artifact_id", "artifact_sha256", "definition_bundle_id",
            "definition_bundle_sha256", "authority_model_definition_id",
            "authority_model_definition_sha256", "adapter_id", "adapter_build_digest",
            "structure_hash", "identity_inventory_sha256")}


def _current_row(generation: int, revision: int = 7):
    return {
        "id": str(uuid.uuid4()),
        "wp_id": str(WP),
        "generation": generation,
        "content_version_id": str(uuid.uuid4()),
        "content_revision": revision,
        "project_id": str(PROJ),
    }


def _patch_observer(monkeypatch, *, adapter_id="a.x", raises=None):
    import app.services.workpaper_sync.published_identity_observer as obs

    async def _observe(**kwargs):
        if raises is not None:
            raise raises
        defs = types.SimpleNamespace(
            adapter_build=types.SimpleNamespace(adapter_id=adapter_id))
        return types.SimpleNamespace(definitions=defs)

    monkeypatch.setattr(obs, "observe_published_frozen_definitions", _observe)


def _patch_registry(monkeypatch, *, reasons=None, adapter_id="a.x", resolve_raises=None):
    import app.services.workpaper_sync.adapters.registry as reg

    class _Reg:
        async def register_from_manifest(self, *, session):
            return types.SimpleNamespace(reasons=reasons or {})

        def resolve_for_entry(self, entry_id):
            if resolve_raises is not None:
                raise resolve_raises
            return types.SimpleNamespace(adapter_id=adapter_id)

    monkeypatch.setattr(reg, "build_production_registry", lambda **k: _Reg())


def _run(session):
    return asyncio.run(
        rc.recheck_entry(session, entry_id=ENTRY, project_id=PROJ, wp_id=WP))


def test_no_history_generation_is_migration_not_run(monkeypatch):
    session = _FakeSession(current=_current_row(1), generations=[1])
    out = _run(session)
    assert out.state == "migration_not_run"


def test_observer_drift_is_reported(monkeypatch):
    from app.services.workpaper_sync.published_identity_observer import (
        ObservationStage,
        ObservedIdentityDriftError,
    )
    _patch_observer(monkeypatch, raises=ObservedIdentityDriftError(
        "hash mismatch",
        stage=ObservationStage.observe_workbook,
        context={"stage": ObservationStage.observe_workbook.value},
    ))
    session = _FakeSession(current=_current_row(2), generations=[1, 2])
    out = _run(session)
    assert out.state == "drift"
    assert out.error_code == "observed_identity_drift"


def test_generation_not_advanced_is_version_violation(monkeypatch):
    # current generation == prior hint（两个相等 generation 不可能，用 current<=prior 构造）
    session = _FakeSession(current=_current_row(2), generations=[2, 3])
    # prior hint = 倒数第二 = 2，current = 2 => 未增
    out = _run(session)
    assert out.state == "version_domain_violation"
    assert out.error_code == "generation_not_advanced"


def test_registry_unregistered_is_mismatch(monkeypatch):
    _patch_observer(monkeypatch, adapter_id="a.x")
    _patch_registry(monkeypatch, reasons={ENTRY: "no approved bundle"})
    session = _FakeSession(current=_current_row(2), generations=[1, 2])
    out = _run(session)
    assert out.state == "registry_mismatch"
    assert out.error_code == "entry_not_registered"


def test_adapter_disagreement_is_mismatch(monkeypatch):
    _patch_observer(monkeypatch, adapter_id="a.x")
    _patch_registry(monkeypatch, adapter_id="b.y")
    session = _FakeSession(current=_current_row(2), generations=[1, 2])
    out = _run(session)
    assert out.state == "registry_mismatch"
    assert out.error_code == "adapter_id_disagree"


def test_all_paths_pass_is_verified(monkeypatch):
    _patch_observer(monkeypatch, adapter_id="a.x")
    _patch_registry(monkeypatch, adapter_id="a.x")
    session = _FakeSession(current=_current_row(2), generations=[1, 2])
    out = _run(session)
    assert out.state == "verified"
    assert out.observed_generation == 2
    assert out.prior_generation == 1
    assert out.content_revision == 7
    assert out.resolved_adapter_id == "a.x"


def test_not_published_when_no_current(monkeypatch):
    session = _FakeSession(current=None, generations=[])
    out = _run(session)
    assert out.state == "not_published"


def test_states_vocabulary_is_closed():
    for s in ("verified", "drift", "registry_mismatch", "version_domain_violation",
              "not_published", "migration_not_run", "blocked"):
        assert s in rc.RECHECK_STATES
