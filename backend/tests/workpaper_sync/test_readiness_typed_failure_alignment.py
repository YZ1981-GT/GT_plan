"""readiness 的 reason code 必须与 registry/domain 的 typed failure 一一对齐（tasks 2.4）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure`

缺陷现场：`_evaluate_runtime` 原先只按 `not_registered` / `not_ready` 子串二分，其余全部压成
`RUNTIME_REGISTRATION_FAILED`。而真库实测的运行时失败是**五类不同成因**（见
`evidence/phase4-pending-runtime-readiness.json`）：

| error_code | 成因 | 用户下一步完全不同 |
|---|---|---|
| `sync_contract_structure_drift` | 契约声明结构与已发布版本不符 | 重新发布 definitions |
| `published_identity_observed_drift` | 冻结受管结构与实测不一致 | 重投影产新版本 |
| `published_identity_frozen_child_unusable` | 冻结插桩缺反读锚点 | 重新插桩 |
| `entry_source_fact_unavailable` | 无挂载点事实 | 先让入口真实挂载 |
| `sync_phase5_e1_selection_invalid` | wp_code 匹配域不一致 | 修匹配域 |

压成一句「同步定义校验失败」⇒ 用户拿不到可操作原因（AC 1.5），也正是 Task 2.4 点名禁止的
「不得合并成泛化未注册」。

判据：
1. 真库实测过的 typed error_code **全部**在显式映射表里，且各自映射到**互不相同**的
   reason code（合并回同一个即红）；
2. 每个 reason code 都有中文 message + next_action，且两者不同（next_action 必须是动作）；
3. 「指针悬空」与「bundle 不是同一份」不得共用 error_code；
4. 兜底仍在，但命中兜底的 error_code 不得属于已知集合。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.workpaper_sync import entry_readiness as R

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = (
    ROOT / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
    "/evidence/phase4-pending-runtime-readiness.json"
)


def _observed_error_codes() -> set[str]:
    """真库 probe 实测到的 typed error_code（现读证据，不手抄）。"""
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    return {
        str(row["error_code"])
        for row in doc.get("results") or []
        if row.get("error_code")
    }


# ════════════════════════════════════════════════════════════════════════════


def test_observed_denominator_is_not_empty() -> None:
    observed = _observed_error_codes()
    assert len(observed) >= 4, f"实测 error_code 只有 {sorted(observed)} —— 分母过小"


@pytest.mark.parametrize("error_code", sorted(_observed_error_codes()))
def test_every_observed_failure_has_an_explicit_reason(error_code: str) -> None:
    assert error_code in R._RUNTIME_FAILURE_REASONS, (
        f"{error_code} 没有显式 reason 映射 —— 它会落进泛化兜底，"
        "用户拿不到可操作原因（Task 2.4 明禁）"
    )
    code = R.runtime_failure_reason_code(error_code)
    assert code != "RUNTIME_REGISTRATION_FAILED", (
        f"{error_code} 仍被映射成泛化 reason"
    )


def test_observed_failures_do_not_collapse_into_one_reason() -> None:
    """五类成因必须落在互不相同的 reason 上 —— 合并回去即红。"""
    observed = sorted(_observed_error_codes())
    codes = [R.runtime_failure_reason_code(item) for item in observed]
    assert len(set(codes)) == len(codes), (
        f"不同成因被合并：{dict(zip(observed, codes))}"
    )


def test_dangling_pointer_and_bundle_mismatch_are_distinct_codes() -> None:
    assert R.EntryReadinessNotFound.error_code != R.DefinitionBundleMismatch.error_code
    assert issubclass(R.DefinitionBundleMismatch, Exception)


@pytest.mark.parametrize("reason_code", sorted(set(R._RUNTIME_FAILURE_REASONS.values())))
def test_every_mapped_reason_has_chinese_message_and_action(reason_code: str) -> None:
    reason = R._reason(reason_code, "probe_detail")
    assert reason.code == reason_code
    assert reason.message.strip(), f"{reason_code} 缺 message"
    assert reason.next_action.strip(), f"{reason_code} 缺 next_action"
    assert reason.message != reason.next_action, (
        f"{reason_code} 的 message 与 next_action 相同 —— next_action 必须是动作"
    )
    assert "probe_detail" in reason.next_action, "detail 没被带进 next_action"


def test_slot_invalid_has_its_own_reason() -> None:
    """typed slots 不完整是独立成因，不得共用泛化码。"""
    reason = R._reason("DEFINITION_SLOT_INVALID")
    assert reason.code == "DEFINITION_SLOT_INVALID"
    assert "slot" in reason.next_action.lower() or "slot" in reason.message.lower()


def test_fallback_only_catches_unknown_codes() -> None:
    assert R.runtime_failure_reason_code("brand_new_unregistered_code") == (
        "RUNTIME_REGISTRATION_FAILED"
    )
    # 族前缀仍有效（registry 的 *_not_registered / *_not_ready 有多个具体码）
    assert R.runtime_failure_reason_code("adapter_not_registered") == "ADAPTER_NOT_READY"
    assert R.runtime_failure_reason_code("something_not_ready") == "ADAPTER_NOT_READY"
    # 已知集合里的码一个都不许落兜底
    for error_code in _observed_error_codes():
        assert R.runtime_failure_reason_code(error_code) != "RUNTIME_REGISTRATION_FAILED"


def test_mapping_table_has_no_unknown_reason_codes() -> None:
    """映射表的目标 reason 必须都在 `_reason` 的词表里（写错名字即红）。"""
    for error_code, reason_code in R._RUNTIME_FAILURE_REASONS.items():
        R._reason(reason_code)  # KeyError 即打红
        assert reason_code.isupper(), f"{error_code} → {reason_code} 命名不符约定"
