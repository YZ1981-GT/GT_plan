"""D4 C1 同步契约 + C2 公式契约 冻结守卫测试
（governance spec d4-dual-mode-formula-governance Task 2 / Task 3）。

- C1 (Property 2)：HTML/Excel 同一 commit boundary；三方合并；durable ack≠applied；
  模式切换不发布。**Validates: Requirements 2.1, 2.2, 2.3**
- C2 (Property 3)：公式 key 五元组用 wp_id；preset/custom/effective/missing/corrupted/
  stale/blocked 分态；F-SHELL 白名单；CAS；no-eval。**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

测试跑真源守卫（main() 返回 0）+ 直接断言契约结构 + 变异反向自检。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]


def _load_guard(name: str):
    path = _BACKEND / "scripts" / "check" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_{name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_sync_guard = _load_guard("check_d4_sync_contract")
_formula_guard = _load_guard("check_d4_formula_contract")


def _contract(fname: str) -> dict:
    return json.loads((_BACKEND / "data" / fname).read_text(encoding="utf-8"))


# ═══════════════════════════════ C1 sync ═══════════════════════════════


class TestSyncContract:
    def test_guard_green(self) -> None:
        assert _sync_guard.main() == 0

    def test_shared_commit_boundary_declared(self) -> None:
        c = _contract("d4_sync_contract_frozen.json")
        scb = c["shared_commit_boundary"]
        assert scb["backend"]["class"] == "ContentMutationService"
        assert scb["frontend"]["composable"] == "useWorkpaperSyncBridge"

    def test_durable_ack_not_applied_invariant(self) -> None:
        c = _contract("d4_sync_contract_frozen.json")
        inv = c["invariants"]["durable_ack_not_applied"]["frontend_evidence"]
        assert inv["in_flight_states_include_applied"] is True

    def test_three_way_conflict_shape(self) -> None:
        c = _contract("d4_sync_contract_frozen.json")
        shape = c["invariants"]["field_level_auto_merge"]["backend_evidence"]["three_way_shape"]
        assert shape == ["base", "current", "incoming"]

    def test_no_publish_on_mode_switch(self) -> None:
        c = _contract("d4_sync_contract_frozen.json")
        ev = c["invariants"]["no_publish_on_mode_switch"]["d4_evidence"]
        assert ev["adjudication_publish_fn"] == "publishAdjudicated"
        assert ev["publish_is_explicit_button"] is True


# ═══════════════════════════════ C2 formula ═══════════════════════════════


class TestFormulaContract:
    def test_guard_green(self) -> None:
        assert _formula_guard.main() == 0

    def test_definition_identity_uses_wp_id_five_tuple(self) -> None:
        c = _contract("d4_formula_contract_frozen.json")
        di = c["definition_identity"]
        assert di["key_fields"] == [
            "wp_id",
            "stable_sheet_key",
            "row_key",
            "field_key",
            "custom",
        ]
        assert di["preset_version_is_not_identity"] is True

    def test_state_vocabulary_covers_all_states(self) -> None:
        c = _contract("d4_formula_contract_frozen.json")
        states = set(c["state_vocabulary"])
        assert {"preset", "custom", "effective", "missing", "corrupted", "stale", "blocked"} <= states

    def test_definition_ssot_is_persisted_five_tuple(self) -> None:
        """真·公式定义 SSOT = formula_management，已持久化且按五元键（Req 3.1 已满足）。"""
        c = _contract("d4_formula_contract_frozen.json")
        ds = c["definition_ssot"]
        assert ds["resolver_fn"] == "resolve_effective_formula"
        assert set(ds["states"]) == {
            "custom", "preset", "preset_missing", "corrupt", "stale", "blocked",
        }
        pp = ds["preset_persistence"]
        assert pp["persisted"] is True
        assert pp["keyed_by_identity_five_tuple"] is True

    def test_toolbar_v2_cas_and_audit_gate(self) -> None:
        c = _contract("d4_formula_contract_frozen.json")
        eng = c["user_formula_toolbar_v2"]
        assert eng["cas_field"] == "baseVersion"
        assert eng["conflict_shape"] == ["base", "current", "incoming"]
        gate = eng["audit_gate"]["commit_gate"]
        assert "绝不 warn-then-commit" in gate
        assert "回滚" in gate
        # 工具栏 v2 是独立的 in-memory 路径，非定义 SSOT
        assert eng["in_memory_only"] is True

    def test_capability_gate_fail_closed(self) -> None:
        c = _contract("d4_formula_contract_frozen.json")
        cap = c["capability_gate"]
        assert cap["action"] == "formulaEditUser"
        assert cap["fail_closed"] is True
        assert cap["owner_epoch_race_guard"] is True

    def test_ssot_status_accurate(self) -> None:
        """ssot_status 如实：定义 SSOT 已持久化五元键（Req 3.1 由 owner spec 交付）。"""
        c = _contract("d4_formula_contract_frozen.json")
        st = c["ssot_status"]
        assert st["d4_1_definition_ssot_persisted"] is True
        assert st["d4_1_definition_ssot_keyed_by_five_tuple"] is True
        assert st["owner_of_definition_ssot"]  # 有明确归属


# ═══════════════════════════════ 变异反向自检 ═══════════════════════════════


class TestMutationReverseChecks:
    def test_sync_guard_catches_missing_symbol(self, monkeypatch) -> None:
        """把桥文件读成空 → durable-ack 判据面缺失必被拦。"""
        orig = _sync_guard._read

        def fake_read(p):
            if "useWorkpaperSyncBridge" in str(p):
                return ""
            return orig(p)

        monkeypatch.setattr(_sync_guard, "_read", fake_read)
        assert _sync_guard.main() == 1

    def test_formula_guard_catches_missing_engine(self, monkeypatch) -> None:
        orig = _formula_guard._read

        def fake_read(p):
            if "user_formula_v2" in str(p):
                return ""
            return orig(p)

        monkeypatch.setattr(_formula_guard, "_read", fake_read)
        assert _formula_guard.main() == 1
