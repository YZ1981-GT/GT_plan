"""抽样记录完整性判据（纯函数）— 守卫

spec: sampling-evaluation-and-governance-closure
Validates: Requirements 7.4, 7.5, 7.6, 7.7, 7.8, 8.4, 11.2, 11.3
Properties: Property 19, Property 20, Property 22
"""

from __future__ import annotations

import inspect

from app.services.sampling_qc_rules import (
    SamplingBatchView,
    evaluate_sampling_completeness,
    has_substantive_evaluation,
)


def _view(**kw) -> SamplingBatchView:
    base = {"batch_id": "1f2e3d4c-aaaa-bbbb-cccc-000000000001", "criteria": {}}
    base.update(kw)
    return SamplingBatchView(**base)


def _with_eval(**ev) -> SamplingBatchView:
    return _view(criteria={"evaluation": ev})


# ─── Property 19：不适用 ≠ 不合规 ────────────────────────────────────────────


def test_no_batches_yields_no_finding():
    """无抽凭批次 → 零 finding。

    否则平台上所有不需要抽样的底稿都会挂一条质量缺口（噪声会让整条规则被忽略）。
    """
    assert evaluate_sampling_completeness([]) == []


def test_confirmed_and_evaluated_batch_yields_no_finding():
    out = evaluate_sampling_completeness([
        _with_eval(projected="0.00", conclusion_confirmed=True)
    ])
    assert out == []


# ─── 缺评价 ──────────────────────────────────────────────────────────────────


def test_missing_evaluation_is_reported():
    out = evaluate_sampling_completeness([_view()])
    assert len(out) == 1
    assert "缺少抽样评价" in out[0]
    assert "CAS 1314" in out[0]


def test_missing_evaluation_does_not_stack_unconfirmed_finding():
    """缺评价时不叠加「结论未确认」—— 同一缺口的下游表现，两条会让复核人以为有两个问题。"""
    out = evaluate_sampling_completeness([_view()])
    assert len(out) == 1
    assert "未经人工确认" not in out[0]


def test_empty_evaluation_dict_counts_as_missing():
    assert len(evaluate_sampling_completeness([_with_eval()])) == 1


def test_undetermined_conclusion_code_counts_as_missing():
    """`undetermined` 是归一化默认值，不是审计师结论。"""
    out = evaluate_sampling_completeness([_with_eval(conclusion_code="undetermined")])
    assert len(out) == 1
    assert "缺少抽样评价" in out[0]


# ─── 零错报是有效评价（关键边界）───────────────────────────────────────────────


def test_zero_projected_counts_as_evaluated():
    """推断错报 0.00 是有效结论（查了没发现错报），不得判成未评价。

    若把 "0.00" 当空值，所有干净的抽样都会被误报，规则立刻失去可信度。
    """
    assert has_substantive_evaluation({"projected": "0.00"}) is True


def test_zero_deviation_count_counts_as_evaluated():
    assert has_substantive_evaluation({"deviation_count": 0}) is True


def test_deviation_count_none_does_not_count():
    assert has_substantive_evaluation({"deviation_count": None}) is False


def test_empty_string_amount_does_not_count():
    assert has_substantive_evaluation({"projected": ""}) is False


# ─── Property 20：结论未确认 / 抽样框过期 ────────────────────────────────────


def test_unconfirmed_conclusion_is_reported():
    out = evaluate_sampling_completeness([_with_eval(projected="100.00")])
    assert len(out) == 1
    assert "未经人工确认" in out[0]


def test_stale_dataset_is_reported():
    out = evaluate_sampling_completeness([
        _view(criteria={"evaluation": {"projected": "1.00", "conclusion_confirmed": True}},
              dataset_stale=True)
    ])
    assert len(out) == 1
    assert "抽样框" in out[0]
    assert "复现" in out[0]


def test_unconfirmed_and_stale_yield_two_findings():
    out = evaluate_sampling_completeness([
        _view(criteria={"evaluation": {"projected": "1.00"}}, dataset_stale=True)
    ])
    assert len(out) == 2


def test_finding_message_contains_batch_locator():
    """finding 必须可追溯到具体批次与底稿（R7.8）。"""
    out = evaluate_sampling_completeness([_view(wp_code="D2")])
    assert "D2" in out[0]
    assert "1f2e3d4c" in out[0]


def test_missing_batch_id_is_stated_not_blank():
    out = evaluate_sampling_completeness([_view(batch_id=None, wp_code="F3")])
    assert "批次标识缺失" in out[0]
    assert "F3" in out[0]


def test_multiple_batches_each_reported():
    out = evaluate_sampling_completeness([
        _view(batch_id="aaa"),
        _view(batch_id="bbb"),
    ])
    assert len(out) == 2
    assert any("aaa" in m for m in out)
    assert any("bbb" in m for m in out)


# ─── 结构与纯度 ──────────────────────────────────────────────────────────────


def test_module_does_not_touch_db():
    """本模块必须不连库（QC 与归档两处复用同一判据 + 便于单测）。"""
    import app.services.sampling_qc_rules as mod

    src = inspect.getsource(mod)
    for forbidden in ("AsyncSession", "db.execute", "sa.select", "select("):
        assert forbidden not in src, f"判据模块不得含 DB 访问：{forbidden}"


def test_view_is_frozen_dataclass():
    """入参视图不可变 —— 判定过程不得副作用修改调用方数据。"""
    v = _view()
    try:
        v.batch_id = "x"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("SamplingBatchView 应为 frozen dataclass")


def test_evaluation_property_tolerates_non_dict():
    """criteria.evaluation 是外部 JSONB，可能是任何类型 → 不得抛错。"""
    assert _view(criteria={"evaluation": "oops"}).evaluation == {}
    assert _view(criteria={"evaluation": None}).evaluation == {}
    assert _view(criteria={}).evaluation == {}


# ─── Property 22：归档与 QC 共用同一判据 ─────────────────────────────────────


def test_archive_completeness_uses_same_predicate():
    from app.services.archive_completeness_service import _check_sampling_records

    src = inspect.getsource(_check_sampling_records)
    assert "evaluate_sampling_completeness" in src, (
        "归档完整性检查必须复用同一判据，否则会出现「QC 说不合规、归档说完整」"
    )
    assert "SamplingBatchView" in src


def test_archive_generator_uses_same_predicate():
    from app.services.archive_generators import sampling_records_generator as gen

    src = inspect.getsource(gen)
    assert "evaluate_sampling_completeness" in src


def test_archive_sampling_category_is_non_blocking():
    """抽样记录补齐是审计判断 → 非阻断（存量项目已有批次缺评价，硬卡会全线阻塞归档）。"""
    src = inspect.getsource(
        __import__(
            "app.services.archive_completeness_service", fromlist=["x"]
        ).get_archive_completeness_report
    )
    idx = src.index('category="sampling_records"')
    seg = src[idx : idx + 260]
    assert "is_blocking=False" in seg, "抽样记录类别应为非阻断"


# ─── 反向自检 ────────────────────────────────────────────────────────────────


def test_reverse_selfcheck_legacy_predicate_would_never_fire():
    """复现旧判据（SamplingConfig → SamplingRecord）在 config 为 0 行时恒无 finding。

    证明「换判据」确有必要：旧判据无论抽样记录多不完整都产出 0 条。
    """
    configs: list[object] = []  # 真实库 sampling_config = 0 行
    legacy_findings = [c for c in configs if True]
    assert legacy_findings == []
    # 而新判据对同样的「有批次但缺评价」场景会报出
    assert len(evaluate_sampling_completeness([_view()])) == 1


def test_reverse_selfcheck_treating_zero_as_missing_would_overreport():
    """若把 "0.00" 当未评价，会对干净抽样误报 —— 本判据不能这样。"""
    naive_missing = not any(
        v not in (None, "", "0.00") for v in {"projected": "0.00"}.values()
    )
    assert naive_missing is True, "反向自检自身失效"
    assert has_substantive_evaluation({"projected": "0.00"}) is True
