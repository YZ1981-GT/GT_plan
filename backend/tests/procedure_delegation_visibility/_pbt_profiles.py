# Feature: procedure-delegation-visibility-isolation — Task 14 同源 smoke/correctness 双 profile 机制
"""同源（same-source）双 profile 机制 + 有效样例计数 + 覆盖矩阵报告支撑。

Task 14（组件 C17 Verification）核心：
  - **同一批 property 函数在两档运行**：smoke（``max_examples=5``，本地快速冒烟，**不得作为完成
    证据**）与 correctness（每 property ≥100 有效样例，CI 正确性验收）收集完全相同的 ``@given``
    property 函数——property 测试不再硬编码 ``max_examples``，改由当前加载的 Hypothesis profile
    驱动例数（见 ``backend/tests/conftest.py`` 注册的 ``smoke``/``correctness``/``fast`` profile）。
  - **每 property 输出有效样例数**：``count_examples(prop_id)`` 装饰器紧贴在 ``@given`` 之下包裹
    property 主体，主体每跑一个**有效样例**即计数一次（Hypothesis 丢弃的无效样例不进主体，故计数
    即有效样例数）；``write_report`` 落地 JSON，另配 ``--hypothesis-show-statistics`` 原始输出作为
    交叉证据 artifact。
  - **数据库语义仍跑 PostgreSQL**：本模块只提供 profile/计数/报告机制，不替代任何 SQL/事务/令牌
    属性的真实 PG 验证（那些属性函数在各自文件内经 ``run_isolated`` / ``session`` fixture 跑 PG）。

**prompt ↔ design 属性编号映射**（design.md 为唯一权威；prompt 用了另一套编号）见
``PROMPT_TO_DESIGN`` 与 ``PROPERTY_MATRIX``。
"""
from __future__ import annotations

import functools
import json
import os
from collections import Counter
from pathlib import Path
from typing import Callable

try:  # pragma: no cover - hypothesis 必装于测试环境
    from hypothesis import HealthCheck
    from hypothesis import settings as _hyp_settings
except Exception:  # noqa: BLE001
    _hyp_settings = None  # type: ignore
    HealthCheck = None  # type: ignore

SMOKE_MAX_EXAMPLES = 5
CORRECTNESS_MAX_EXAMPLES = int(os.environ.get("HYPOTHESIS_CORRECTNESS_EXAMPLES", "100"))


def _suppress():
    return [
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
        HealthCheck.function_scoped_fixture,
    ]


def register_profiles() -> None:
    """幂等注册 smoke / correctness / fast profile（隔离收集时的兜底；backend conftest 亦注册）。"""
    if _hyp_settings is None:
        return
    try:
        _hyp_settings.register_profile(
            "smoke", max_examples=SMOKE_MAX_EXAMPLES, deadline=None, suppress_health_check=_suppress()
        )
        _hyp_settings.register_profile(
            "correctness", max_examples=CORRECTNESS_MAX_EXAMPLES, deadline=None,
            suppress_health_check=_suppress(),
        )
        _hyp_settings.register_profile(
            "fast", max_examples=SMOKE_MAX_EXAMPLES, deadline=None, suppress_health_check=_suppress()
        )
    except Exception:  # noqa: BLE001 — 已注册即忽略
        pass


def active_profile_name() -> str:
    return os.environ.get("HYPOTHESIS_PROFILE", "fast")


def is_correctness() -> bool:
    return active_profile_name() == "correctness"


def is_smoke() -> bool:
    return active_profile_name() in ("smoke", "fast")


def target_examples() -> int:
    """当前 profile 下每 property 期望的有效样例数（smoke=5 / correctness>=100）。"""
    return CORRECTNESS_MAX_EXAMPLES if is_correctness() else SMOKE_MAX_EXAMPLES


def pbt_settings(**overrides):
    """profile 驱动的 ``@settings``：**不**硬编码 ``max_examples`` → 继承活动 profile 例数。

    仅固定 ``deadline`` 与 health-check 抑制，令同一 property 函数 smoke=5 / correctness>=100 运行。
    """
    if _hyp_settings is None:  # pragma: no cover
        raise RuntimeError("hypothesis unavailable")
    kw = {"deadline": None, "suppress_health_check": _suppress()}
    kw.update(overrides)
    return _hyp_settings(**kw)


# ---------------------------------------------------------------------------
# 有效样例计数（真实计数：装饰器紧贴 @given 之下，property 主体每有效样例调用一次）
# ---------------------------------------------------------------------------
VALID_EXAMPLE_COUNTS: Counter = Counter()


def count_examples(property_id: str) -> Callable:
    """紧贴在 ``@given`` 之下使用：包裹 property 主体，每跑一个有效样例计一次。

    用法::

        @given(x=st.integers())
        @count_examples("P16")
        @pbt_settings()  # (顺序不敏感：settings 亦可放 given 与本装饰器之间)
        def test_prop(x): ...

    ``functools.wraps`` 保留原签名，Hypothesis 仍按被包裹函数的参数名注入策略。
    """

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            VALID_EXAMPLE_COUNTS[property_id] += 1
            return fn(*args, **kwargs)

        return wrapper

    return deco


def record(property_id: str) -> None:
    """在 property 主体**首行**调用：每跑一个有效样例计一次（避免包裹 @given 的签名问题）。"""
    VALID_EXAMPLE_COUNTS[property_id] += 1


def reset_counts() -> None:
    VALID_EXAMPLE_COUNTS.clear()


# ---------------------------------------------------------------------------
# prompt ↔ design 属性编号映射（design.md 权威）
# ---------------------------------------------------------------------------
PROMPT_TO_DESIGN: dict[str, str] = {
    "prompt P1 分类/scope": "P1",
    "prompt P2/P3/P5 staff-user + same-person": "P2",
    "prompt P4 layers never overwrite/clear": "P3",
    "prompt P6 procedure binding unique/reject": "P4",
    "prompt P7 restricted visible set formula": "P5",
    "prompt P6 history immutable after rebind": "P6",
    "prompt P9 sheet 页面隔离 + P10 history current-version-only": "P7",
    "prompt P8 grant single kind / no splice": "P8",
    "prompt reviewer whitelist": "P9",
    "prompt binding/claim conflict": "P10",
    "prompt 429 pre-resolve + uniform 404": "P11",
    "prompt audit failure never changes contract": "P12",
    "prompt editor token bound through callback": "P13",
    "prompt list ordered pipeline": "P14",
    "prompt display never authorizes": "P15",
    "prompt HTTP/worker ledger equality": "P16",
    "prompt P17 permission-change epoch atomic": "P17",
    "prompt P18 revocation converges <=1s": "P18",
    "prompt P19 profile activation needs capacity": "P19",
    "prompt P20 evidence append-only/hash": "P20",
}

# design P# -> 已实现该 property 的 property-test node（同源批次；Task 14 统一收集）。
# 这些 @given 函数在 smoke/correctness 两档运行同一批次。
PROPERTY_MATRIX: dict[str, list[str]] = {
    "P1": ["test_role_classifier.py::TestProperty1ClassificationUniqueFailClosed::test_classification_matrix"],
    "P2": [
        "test_staff_user_mapping.py::TestProperty2StaffUserMapping::test_mapping_accepts_only_unique_active_bidirectional",
        "test_delegation_transaction_pbt.py::test_pbt_mapping_transaction_invariants",
    ],
    "P3": ["test_delegation_transaction_pbt.py::test_pbt_layers_never_overwrite"],
    "P4": ["test_procedure_wp_resolver.py::TestProperty4ProcedureBindingUniqueOrReject::test_unique_or_reject_no_mutation"],
    "P5": ["test_visibility_query.py::TestProperty5FixedSetFormula::test_visible_equals_delegated_union_history_intersect_scope"],
    "P6": ["test_visibility_query.py::TestProperty6HistoryImmutableAfterRebind::test_history_attribution_unchanged_by_rebind"],
    "P7": [
        "test_visibility_query.py::TestProperty7PageVisibilityAndHistoryReadonly::test_row_only_page_isolation",
        "test_visibility_query.py::TestProperty7PageVisibilityAndHistoryReadonly::test_history_grants_are_readonly",
        "test_procedure_wp_resolver.py::TestProperty7RowOnlySheetMapping::test_sheet_name_maps_unique_or_rejects",
    ],
    "P8": [
        "test_visibility_query.py::TestProperty8OneKnownKindPerGrant::test_each_grant_single_registered_kind",
    ],
    "P9": [
        "test_task14_property_gaps.py::test_p9_reviewer_whitelist_only",
        "test_wp_bound_gate.py::TestProperty9ReviewerWhitelist (example, PG, Task6)",
    ],
    "P10": [
        "test_task14_property_gaps.py::test_p10_binding_claim_conflict_fail_closed",
        "test_wp_bound_gate.py::TestProperty10BindingClaimConflict (example, PG, Task6)",
    ],
    "P11": ["test_wp_bound_gate.py::TestProperty11PBTUniformNotFound::test_deny_always_404_fixed_body"],
    "P12": [
        "test_task14_property_gaps.py::test_p12_audit_failure_never_changes_contract",
        "test_wp_bound_gate.py::TestProperty12AuditFailureContractStable (example, PG, Task6)",
    ],
    "P13": [
        "test_editor_security.py::TestEditorTokenPBT::test_valid_token_roundtrip",
        "test_editor_security.py::TestEditorTokenPBT::test_tampered_wp_always_rejected",
    ],
    "P14": ["test_workpaper_list_query.py::TestProperty14OrderedPipeline::test_pipeline_invariants"],
    "P15": [
        "test_task14_property_gaps.py::test_p15_display_and_client_identity_never_authorize",
        "test_workpaper_list_query.py::TestProperty15DisplayNeverAuthorizes (example, PG, Task8)",
    ],
    "P16": ["test_task14_property_gaps.py::test_p16_ledger_bidirectional_and_no_fake_pass"],
    "P17": ["test_delegation_transaction_pbt.py::test_pbt_epoch_monotonic_and_atomic"],
    "P18": ["test_task14_property_gaps.py::test_p18_revocation_converges_no_stale_allow"],
    "P19": ["test_task14_property_gaps.py::test_p19_profile_activation_requires_capacity_evidence"],
    "P20": ["test_task14_property_gaps.py::test_p20_evidence_append_only_hash_complete"],
}


def write_report(path: Path) -> dict:
    """落地有效样例计数 + profile + P1–P20 覆盖矩阵 JSON。"""
    payload = {
        # deterministic：不含时间戳 → 同一 profile+counts+matrix 产出稳定字节，
        # 避免每次 session 改写导致 manifest artifact hash 失效（frozen 快照才入 manifest）。
        "profile": active_profile_name(),
        "is_completion_evidence": is_correctness(),
        "target_examples_per_property": target_examples(),
        "smoke_max_examples": SMOKE_MAX_EXAMPLES,
        "correctness_max_examples": CORRECTNESS_MAX_EXAMPLES,
        "valid_example_counts": dict(sorted(VALID_EXAMPLE_COUNTS.items())),
        "prompt_to_design_property_map": PROMPT_TO_DESIGN,
        "property_matrix": PROPERTY_MATRIX,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
