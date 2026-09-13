# -*- coding: utf-8 -*-
"""Task 2 守卫：curated-entry builder + 共享 profile 锁的行为级单测。

spec: `workpaper-sync-curated-entry-facility`
Requirements 1.1, 1.2, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4

只针对 Task 2 的两个新函数做行为测试（不触及 build_manifest 集成，那是 Task 3）：

- `_build_curated_entries(overlay, *, discovered_host_paths, discovery_entry_ids)`
- `_assert_profile_in_expected(...)`（discovery 与 curated 共用的 profile-vs-expected 锁）

每条 fail-closed 门都有一条实际调用该函数、断言抛 `ManifestGenerationError` 的用例；
happy path 断言 emit 出的 entry 与 discovery-entry schema 同构（`_REQUIRED_ENTRY_FIELDS`
全覆盖 + `mounts == []` 不参与 template_ast 挂载核对）。fixture 用 design §2.2 的 D4-9
curated 声明形状，且 host_path 指向真实存在的 discovered host。
"""
from __future__ import annotations

import copy
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_GENERATOR_PATH = _BACKEND / "scripts" / "gen" / "generate_workpaper_sync_manifest.py"

_D4_9_HOST = "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    return _load(_GENERATOR_PATH, "curated_builder_generator")


def _d4_9_declaration() -> dict[str, Any]:
    """design §2.2 的 D4-9 curated 声明形状（bidirectional + 全证据）。"""
    return {
        "entry_id": "xlsx/gt-d4-customer-structure",
        "host_path": _D4_9_HOST,
        "curated_reason": (
            "one dynamic GtOnlyOfficeSheet host backs D4-1/2/3/9; "
            "D4-9 needs its own contract+adapter"
        ),
        "document_type": "xlsx",
        "wp_match": {
            "wp_code_patterns": ["D4-9"],
            "component_types": [],
            "sheet_literals": ["重要客户结构分析D4-9"],
            "sheet_expressions": [],
            "source_host": _D4_9_HOST,
        },
        "html_store": "D4-9-data",
        "canonical_resolver": "d4_customer_structure_projection",
        "adapter_id": "d4.customer_structure",
        "capability": "bidirectional",
        "migration_state": "curated_bidirectional",
        "expected_profile": {
            "editability": ["editable"],
            "room_model": ["shared"],
            "scenario_profile_ids": ["xlsx.editable.shared.single.room_service_wired.v1"],
        },
        "profile": {
            "editability": "editable",
            "room_model": "shared",
            "scenario_profile_id": "xlsx.editable.shared.single.room_service_wired.v1",
        },
        "evidence": {
            "review_status": "curated_reviewed",
            "contract_test": "backend/tests/workpaper_sync/test_d4_9_task3_contract.py",
            "browser_case": None,
            "legacy_reasons": [],
        },
    }


def _overlay_with(declaration: dict[str, Any] | None) -> dict[str, Any]:
    overlay: dict[str, Any] = {}
    if declaration is not None:
        overlay["curated_entries"] = [declaration]
    return overlay


_HOSTS = {_D4_9_HOST}
_DISCOVERY_IDS = {"xlsx/gt-d4-operating-revenue", "docx/gt-a10-bundle"}


def _build(gen: ModuleType, declaration: dict[str, Any] | None) -> list[dict[str, Any]]:
    return gen._build_curated_entries(
        _overlay_with(declaration),
        discovered_host_paths=_HOSTS,
        discovery_entry_ids=_DISCOVERY_IDS,
    )


class TestHappyPath:
    def test_bidirectional_full_evidence_emits_schema_matching_entry(self, gen: ModuleType) -> None:
        """Req 1.1/1.2/2.1：全证据 bidirectional 声明 emit 出与 discovery 同构 entry。"""
        entries = _build(gen, _d4_9_declaration())
        assert len(entries) == 1
        entry = entries[0]
        # 与 discovery-entry schema 同构：所有必填字段齐全。
        assert not (gen._REQUIRED_ENTRY_FIELDS - entry.keys())
        assert entry["entry_id"] == "xlsx/gt-d4-customer-structure"
        assert entry["host_path"] == _D4_9_HOST
        assert entry["capability"] == "bidirectional"
        assert entry["adapter_id"] == "d4.customer_structure"
        assert entry["independent_entry"] is True
        assert entry["parent_entry_id"] is None
        # curated entry 不携带 template_ast mounts ⇒ 不参与 mount 核对。
        assert entry["mounts"] == []
        assert entry["editability"] == "editable"
        assert entry["room_model"] == "shared"
        assert entry["scenario_profile"]["profile_id"] == (
            "xlsx.editable.shared.single.room_service_wired.v1"
        )

    def test_absent_curated_entries_returns_empty(self, gen: ModuleType) -> None:
        """无 curated_entries 键 ⇒ 返回空（加法不变量的前提）。"""
        assert _build(gen, None) == []
        assert gen._build_curated_entries(
            {"curated_entries": []},
            discovered_host_paths=_HOSTS,
            discovery_entry_ids=_DISCOVERY_IDS,
        ) == []


class TestFailClosedGates:
    def test_collision_with_discovery_entry_id_fails(self, gen: ModuleType) -> None:
        """Req 1.4：curated entry_id 撞 discovery id ⇒ fail closed。"""
        decl = _d4_9_declaration()
        decl["entry_id"] = "xlsx/gt-d4-operating-revenue"  # 已在 _DISCOVERY_IDS
        with pytest.raises(gen.ManifestGenerationError, match="collides with a discovery"):
            _build(gen, decl)

    def test_duplicate_curated_entry_id_fails(self, gen: ModuleType) -> None:
        """Req 1.4：两条 curated 声明同 id ⇒ fail closed。"""
        decl = _d4_9_declaration()
        overlay = {"curated_entries": [decl, copy.deepcopy(decl)]}
        with pytest.raises(gen.ManifestGenerationError, match="duplicate curated entry_id"):
            gen._build_curated_entries(
                overlay,
                discovered_host_paths=_HOSTS,
                discovery_entry_ids=_DISCOVERY_IDS,
            )

    def test_missing_host_fails(self, gen: ModuleType) -> None:
        """Req 1.5：host_path 不是 discovered host ⇒ fail closed。"""
        decl = _d4_9_declaration()
        decl["host_path"] = "audit-platform/frontend/src/components/workpaper/DoesNotExist.vue"
        with pytest.raises(gen.ManifestGenerationError, match="not produced by discovery"):
            _build(gen, decl)

    def test_bidirectional_without_adapter_fails(self, gen: ModuleType) -> None:
        """Req 2.2：bidirectional 但缺 adapter_id ⇒ fail closed。"""
        decl = _d4_9_declaration()
        decl["adapter_id"] = ""
        with pytest.raises(gen.ManifestGenerationError, match="requires a non-empty adapter_id"):
            _build(gen, decl)

    def test_bidirectional_without_contract_test_fails(self, gen: ModuleType) -> None:
        """Req 2.2：bidirectional 但缺 contract-test 证据 ⇒ fail closed。"""
        decl = _d4_9_declaration()
        decl["evidence"] = {**decl["evidence"], "contract_test": None}
        with pytest.raises(gen.ManifestGenerationError, match="requires evidence.contract_test"):
            _build(gen, decl)

    def test_bidirectional_unresolved_html_store_fails(self, gen: ModuleType) -> None:
        """Req 2.2：bidirectional 但 html_store 未解析 ⇒ fail closed。"""
        decl = _d4_9_declaration()
        decl["html_store"] = "unresolved"
        with pytest.raises(gen.ManifestGenerationError, match="requires a resolved html_store"):
            _build(gen, decl)

    def test_unreviewed_fails(self, gen: ModuleType) -> None:
        """Req 2.4：review_status 空 ⇒ fail closed。"""
        decl = _d4_9_declaration()
        decl["evidence"] = {**decl["evidence"], "review_status": ""}
        with pytest.raises(gen.ManifestGenerationError, match="not reviewed"):
            _build(gen, decl)

    def test_invalid_capability_fails(self, gen: ModuleType) -> None:
        """Req 2.1：capability 不在允许集 ⇒ fail closed。"""
        decl = _d4_9_declaration()
        decl["capability"] = "totally_made_up"
        with pytest.raises(gen.ManifestGenerationError, match="invalid capability"):
            _build(gen, decl)

    def test_profile_vs_expected_mismatch_fails(self, gen: ModuleType) -> None:
        """Req 2.3：declared profile 不在 reviewed expected_profile ⇒ fail closed。"""
        decl = _d4_9_declaration()
        decl["profile"] = {**decl["profile"], "editability": "readonly"}  # expected 只允许 editable
        with pytest.raises(gen.ManifestGenerationError, match="not in the reviewed set"):
            _build(gen, decl)

    def test_unknown_key_rejected(self, gen: ModuleType) -> None:
        """声明含未知键 ⇒ fail closed（禁止悄悄夹带未审字段）。"""
        decl = _d4_9_declaration()
        decl["surprise"] = "unexpected"
        with pytest.raises(gen.ManifestGenerationError, match="unknown keys"):
            _build(gen, decl)

    def test_missing_required_field_fails(self, gen: ModuleType) -> None:
        """缺任一必填字段 ⇒ fail closed。"""
        decl = _d4_9_declaration()
        del decl["canonical_resolver"]
        with pytest.raises(gen.ManifestGenerationError, match="misses required fields"):
            _build(gen, decl)

    def test_invalid_migration_state_fails(self, gen: ModuleType) -> None:
        """migration_state 必须是 curated_* 家族之一（不能冒充 discovery 状态）。"""
        decl = _d4_9_declaration()
        decl["migration_state"] = "legacy_fake_bidirectional"
        with pytest.raises(gen.ManifestGenerationError, match="migration_state must be one of"):
            _build(gen, decl)


class TestSharedProfileHelper:
    """_assert_profile_in_expected 是 discovery 与 curated 共用的 profile 锁。"""

    def test_value_in_expected_passes(self, gen: ModuleType) -> None:
        gen._assert_profile_in_expected(
            entry_id="e1",
            profile_values={
                "editability": ("editable", "fact"),
                "room_model": ("shared", "fact"),
                "scenario_profile_ids": ("xlsx.editable.shared.single.room_service_wired.v1", "fact"),
            },
            expectation={
                "editability": ["editable"],
                "room_model": ["shared"],
                "scenario_profile_ids": ["xlsx.editable.shared.single.room_service_wired.v1"],
            },
            origin="test",
            label="unit",
        )

    def test_value_not_in_expected_raises(self, gen: ModuleType) -> None:
        with pytest.raises(gen.ManifestGenerationError, match="not in the reviewed set"):
            gen._assert_profile_in_expected(
                entry_id="e1",
                profile_values={
                    "editability": ("readonly", "fact"),
                    "room_model": ("shared", "fact"),
                    "scenario_profile_ids": ("x", "fact"),
                },
                expectation={
                    "editability": ["editable"],
                    "room_model": ["shared"],
                    "scenario_profile_ids": ["x"],
                },
                origin="test",
                label="unit",
            )

    def test_expectation_missing_field_raises(self, gen: ModuleType) -> None:
        with pytest.raises(gen.ManifestGenerationError, match="misses"):
            gen._assert_profile_in_expected(
                entry_id="e1",
                profile_values={
                    "editability": ("editable", "fact"),
                    "room_model": ("shared", "fact"),
                    "scenario_profile_ids": ("x", "fact"),
                },
                expectation={"editability": ["editable"], "room_model": ["shared"]},
                origin="test",
                label="unit",
            )

    def test_expectation_unknown_key_raises(self, gen: ModuleType) -> None:
        with pytest.raises(gen.ManifestGenerationError, match="unknown keys"):
            gen._assert_profile_in_expected(
                entry_id="e1",
                profile_values={
                    "editability": ("editable", "fact"),
                    "room_model": ("shared", "fact"),
                    "scenario_profile_ids": ("x", "fact"),
                },
                expectation={
                    "editability": ["editable"],
                    "room_model": ["shared"],
                    "scenario_profile_ids": ["x"],
                    "bogus": ["nope"],
                },
                origin="test",
                label="unit",
            )
