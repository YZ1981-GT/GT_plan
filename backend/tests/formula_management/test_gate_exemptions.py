"""Task 2.2 · B15 redirect-materiality 正式豁免登记的可伪证校验测试。

spec formula-manager-closure，design ADR-FMC-03 / §5 步骤 2 / §7.3。

验收判据：
  * 门禁读取豁免登记，redirect-materiality 三字段齐全（owner/reason/expires_at）
    且校验通过 → 从非 redirect 分母剔除。
  * 变异反证（删条目 → 计入分母）：登记里没有该条目时，exempted_keys 不含它。
  * 反向断言：条目存在且有效时，exempted_keys 含它（未注入变异时不误红）。
  * 防空转：verify_against 缺值 / wp_code 在运行时 override 抽不到值 → probe_empty 失效。
  * 可伪证：expires_at 过期、运行时 override 口径变化 → 失效（不是加一行就绿的后门）。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta

import pytest

from app.services.formula_management.gate_exemptions import (
    EXEMPTIONS_PATH,
    GateExemption,
    exempted_keys,
    load_exemptions,
    validate_exemption,
)

# 运行时 override 口径真源（与 wp_render_config.py 的 redirect-materiality 分支一致）。
_LIVE_OVERRIDES = {"B15": "redirect-materiality"}
_FUTURE = (date.today() + timedelta(days=365)).isoformat()


def _b15_exemption(**overrides) -> GateExemption:
    base = GateExemption(
        key="redirect-materiality",
        kind="redirect",
        owner="workpaper-rendering",
        reason="B15 重定向到重要性模块，不渲染工作底稿 toolbar，无当前页公式入口。",
        expires_at=_FUTURE,
        verify_against={
            "wp_code": "B15",
            "override_component_type": "redirect-materiality",
            "delegated_module": "materiality",
            "target_path": "/materiality",
        },
    )
    return replace(base, **overrides) if overrides else base


# ─── 登记文件真实存在且含 B15 ────────────────────────────────────────────────


def test_registry_file_exists_and_registers_b15():
    """登记文件存在、可解析，且含 redirect-materiality 条目，三字段齐全。"""
    assert EXEMPTIONS_PATH.exists(), "豁免登记文件缺失"
    exemptions = load_exemptions()
    b15 = next((e for e in exemptions if e.key == "redirect-materiality"), None)
    assert b15 is not None, "登记里应有 redirect-materiality"
    # 三字段齐全（owner/reason/expires_at）
    assert b15.owner.strip()
    assert b15.reason.strip()
    assert b15.expires_at
    assert b15.verify_against.get("wp_code") == "B15"


def test_registered_b15_passes_validation_against_live_overrides():
    """登记文件里的 B15 对运行时真实 override 表校验通过（不只对合成数据）。"""
    exemptions = load_exemptions()
    b15 = next(e for e in exemptions if e.key == "redirect-materiality")
    res = validate_exemption(b15)  # overrides=None → 现读 wp_code_overrides.json 活数据
    assert res.valid, f"登记的 B15 应对活数据校验通过，实际 {res.reason_code}: {res.detail}"


# ─── 反向断言：有效条目被剔除（未注入变异时不误红）─────────────────────────


def test_valid_b15_is_in_exempted_keys(tmp_path):
    """反向断言：条目存在且有效 → exempted_keys 含 redirect-materiality。"""
    reg = tmp_path / "ex.json"
    reg.write_text(
        json.dumps({"schema_version": 1, "exemptions": [
            {
                "key": "redirect-materiality", "kind": "redirect",
                "owner": "workpaper-rendering", "reason": "r", "expires_at": _FUTURE,
                "verify_against": {
                    "wp_code": "B15", "override_component_type": "redirect-materiality",
                    "delegated_module": "materiality", "target_path": "/materiality",
                },
            }
        ]}),
        encoding="utf-8",
    )
    keys = exempted_keys(reg, overrides=_LIVE_OVERRIDES)
    assert "redirect-materiality" in keys


# ─── 变异反证：删掉条目 → 该项计入分母（不在豁免集）──────────────────────


def test_mutation_delete_entry_removes_from_exempted_keys(tmp_path):
    """删掉豁免条目 → redirect-materiality 不再被剔除（计入分母 → 门禁相应断言红）。"""
    reg = tmp_path / "ex.json"
    reg.write_text(
        json.dumps({"schema_version": 1, "exemptions": []}),  # 条目被删
        encoding="utf-8",
    )
    keys = exempted_keys(reg, overrides=_LIVE_OVERRIDES)
    assert "redirect-materiality" not in keys, "删条目后不得仍在豁免集"


# ─── 可伪证：过期 / 字段缺失 / 事实不符 ──────────────────────────────────


def test_expired_exemption_is_invalid():
    past = (date.today() - timedelta(days=1)).isoformat()
    res = validate_exemption(_b15_exemption(expires_at=past), overrides=_LIVE_OVERRIDES)
    assert not res.valid and res.reason_code == "expired"


def test_missing_expires_at_is_invalid():
    res = validate_exemption(_b15_exemption(expires_at=None), overrides=_LIVE_OVERRIDES)
    assert not res.valid and res.reason_code == "fields_missing"


def test_empty_owner_is_invalid():
    res = validate_exemption(_b15_exemption(owner="  "), overrides=_LIVE_OVERRIDES)
    assert not res.valid and res.reason_code == "fields_missing"


def test_empty_reason_is_invalid():
    res = validate_exemption(_b15_exemption(reason=""), overrides=_LIVE_OVERRIDES)
    assert not res.valid and res.reason_code == "fields_missing"


def test_override_drift_invalidates_exemption():
    """可伪证：若 B15 运行时 override 不再是 redirect-materiality → 豁免失效。"""
    drifted = {"B15": "b-index"}  # 口径漂移
    res = validate_exemption(_b15_exemption(), overrides=drifted)
    assert not res.valid and res.reason_code == "fact_mismatch"


def test_redirect_target_drift_invalidates_exemption():
    """可伪证：redirect 目标登记与运行时口径不符（如改成别的模块）→ 失效。"""
    bad_target = _b15_exemption(verify_against={
        "wp_code": "B15", "override_component_type": "redirect-materiality",
        "delegated_module": "consolidation_hub", "target_path": "/consol",
    })
    res = validate_exemption(bad_target, overrides=_LIVE_OVERRIDES)
    assert not res.valid and res.reason_code == "fact_mismatch"


# ─── 防空转断言：判据抽不到值一律失效（不静默放行）──────────────────────


def test_probe_empty_when_verify_against_missing_keys():
    thin = _b15_exemption(verify_against={"wp_code": "B15"})  # 缺其余必填键
    res = validate_exemption(thin, overrides=_LIVE_OVERRIDES)
    assert not res.valid and res.reason_code == "probe_empty"


def test_probe_empty_when_wp_code_absent_in_runtime_overrides():
    """声明的 wp_code 在运行时 override 表抽不到值 → probe_empty（不静默放行）。"""
    res = validate_exemption(_b15_exemption(), overrides={})  # 空 override 表
    assert not res.valid and res.reason_code == "probe_empty"


def test_probe_empty_when_verify_against_entirely_absent():
    res = validate_exemption(_b15_exemption(verify_against={}), overrides=_LIVE_OVERRIDES)
    # verify_against 为空 → 先命中 fields_missing（三字段齐全校验里含 verify_against 存在）
    assert not res.valid and res.reason_code == "fields_missing"


# ─── 坏登记文件必须炸出来（门禁不吞）─────────────────────────────────────


def test_malformed_registry_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"no_exemptions_key": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_exemptions(bad)
