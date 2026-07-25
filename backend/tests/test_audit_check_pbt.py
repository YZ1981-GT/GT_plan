"""审计检查 M0 属性测试（audit-check-review-gate-hardening Task 2.4）

用 hypothesis（fast profile，`@settings(max_examples=5)`）覆盖 design 的正确性属性
P1/P2/P3/P4/P5/P13。全部针对**真实被测纯函数**（不依赖 DB / 事件总线 / ORM）：

| 属性 | 被测函数（真实实现） | 模块 |
|------|---------------------|------|
| P1 通过率分母不含未覆盖 | `ProjectCheckSummary.from_items` | services/audit_check/models.py |
| P2 未覆盖存在时不呈现全绿 | `ProjectCheckSummary.from_items` | services/audit_check/models.py |
| P3 陈旧判定单调 + never_checked | `_compute_freshness` | routers/audit_check.py |
| P4 未检查底稿不计通过率 | `_resolve_wp_checks` | routers/audit_check.py |
| P5 同一勾稽单一口径 + 幂等 | `_merge_dedup` | services/audit_check/aggregator.py |
| P13 无 audit_checks 退回 fine_checks | `_resolve_wp_checks` | routers/audit_check.py |

strategies 保持简单（passed ∈ {True,False,None}；severity 枚举；float 用
`allow_nan=False, allow_infinity=False`），复用被测函数真实实现，不重写逻辑。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.routers.audit_check import _compute_freshness, _resolve_wp_checks
from app.services.audit_check.aggregator import _dedup_key, _merge_dedup
from app.services.audit_check.models import (
    SEVERITY_BLOCKING,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    AuditCheckItem,
    AuditCheckSource,
    ProjectCheckSummary,
)

# ═══════════════════════════════════════════
# 公共 strategies / helpers
# ═══════════════════════════════════════════

# passed 三态：True=通过 / False=未通过 / None=未覆盖(pending)
_PASSED = st.sampled_from([True, False, None])
_SEVERITY = st.sampled_from([SEVERITY_BLOCKING, SEVERITY_WARNING, SEVERITY_INFO])
# float：严格排除 nan / inf（任务约束）
_FLOAT = st.floats(allow_nan=False, allow_infinity=False, width=32)

_BASE_DT = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _mk_item(
    passed,
    *,
    severity: str = SEVERITY_INFO,
    source: str = AuditCheckSource.FINE_RULE.value,
    code: str = "X",
    wp_code: str = "D2",
    check_type: str = "balance",
) -> AuditCheckItem:
    """构造统一检查项（复用真实 dataclass，不重写字段语义）。"""
    return AuditCheckItem(
        code=code,
        source=source,
        wp_code=wp_code,
        severity=severity,
        check_type=check_type,
        description="d",
        message="m",
        produced_at="2026-01-01T00:00:00",
        passed=passed,
    )


# passed + severity 元组列表 → items
_ITEM_SPECS = st.lists(st.tuples(_PASSED, _SEVERITY), max_size=12)


def _items_from_specs(specs) -> list[AuditCheckItem]:
    return [_mk_item(p, severity=sev) for (p, sev) in specs]


# ═══════════════════════════════════════════
# P1: 通过率分母不含未覆盖
# ═══════════════════════════════════════════

@settings(max_examples=5)
@given(specs=_ITEM_SPECS)
def test_p1_pass_rate_denominator_excludes_uncovered(specs):
    """`decided == passed数 + failed数`；`pass_rate == passed/decided`（decided>0）
    或 None（decided==0）；未覆盖（passed=None）恒不进分母也不进分子。"""
    items = _items_from_specs(specs)
    s = ProjectCheckSummary.from_items(items)

    n_pass = sum(1 for p, _ in specs if p is True)
    n_fail = sum(1 for p, _ in specs if p is False)
    n_uncovered = sum(1 for p, _ in specs if p is None)

    # 计数正确
    assert s.total == len(specs)
    assert s.passed == n_pass
    assert s.failed == n_fail
    assert s.uncovered == n_uncovered

    # decided = passed数 + failed数（不含未覆盖）
    assert s.decided == n_pass + n_fail

    if s.decided > 0:
        # 分母=decided（不含 null），分子=passed（不含 null）
        assert abs(s.pass_rate - (n_pass / s.decided)) < 1e-9
    else:
        # decided==0 → pass_rate is None（非 0/全绿）
        assert s.pass_rate is None

    # 未覆盖既不进分母也不进分子：pass_rate 只由 passed/failed 决定，与 uncovered 数量无关
    baseline = [
        _mk_item(p, severity=sev) for (p, sev) in specs if p is not None
    ]
    s_no_uncovered = ProjectCheckSummary.from_items(baseline)
    assert s.pass_rate == s_no_uncovered.pass_rate
    assert s.decided == s_no_uncovered.decided
    assert s.passed == s_no_uncovered.passed
    assert s.failed == s_no_uncovered.failed


# ═══════════════════════════════════════════
# P2: 未覆盖存在时不呈现"全部通过"
# ═══════════════════════════════════════════

@settings(max_examples=5)
@given(specs=_ITEM_SPECS)
def test_p2_uncovered_does_not_inflate_full_pass(specs):
    """本项目 summary 无「全部通过」布尔字段；等价断言：`pass_rate == 1.0`
    当且仅当 `failed == 0 且 decided > 0`，与 uncovered 数量无关
    （uncovered 不会把 pass_rate 抬成 1.0）。"""
    items = _items_from_specs(specs)
    s = ProjectCheckSummary.from_items(items)

    # 全绿（pass_rate==1.0）⟺ 无未通过 且 有已判定项
    assert (s.pass_rate == 1.0) == (s.failed == 0 and s.decided > 0)

    # 存在未覆盖时：若无任何已判定通过项（passed==0），pass_rate 不可能是 1.0
    if s.uncovered > 0 and s.passed == 0:
        assert s.pass_rate != 1.0
        if s.decided == 0:
            # 全未覆盖 → None，不是全绿
            assert s.pass_rate is None


@settings(max_examples=5)
@given(
    n_pass=st.integers(min_value=0, max_value=6),
    n_uncovered=st.integers(min_value=1, max_value=6),
)
def test_p2_all_passed_plus_uncovered_still_not_none_but_uncovered_visible(n_pass, n_uncovered):
    """全部已判定项都通过 + 若干未覆盖：pass_rate==1.0（分母只含 passed），
    但 uncovered 仍如实计数呈现（不被吞没）。"""
    items = [_mk_item(True) for _ in range(n_pass)] + [
        _mk_item(None) for _ in range(n_uncovered)
    ]
    s = ProjectCheckSummary.from_items(items)
    assert s.uncovered == n_uncovered  # 未覆盖如实呈现
    if n_pass > 0:
        assert s.pass_rate == 1.0  # 分母不含 uncovered
        assert s.decided == n_pass
    else:
        assert s.pass_rate is None  # 全未覆盖 → 非全绿


# ═══════════════════════════════════════════
# P3: 陈旧判定单调 + never_checked
# ═══════════════════════════════════════════

@settings(max_examples=5)
@given(
    checked_off=st.integers(min_value=-500_000, max_value=500_000),
    updated_off=st.integers(min_value=-500_000, max_value=500_000),
)
def test_p3_stale_monotonic_when_both_parseable(checked_off, updated_off):
    """checked_at / updated_at 都可解析时：`stale == (updated > checked)`。"""
    checked_dt = _BASE_DT + timedelta(seconds=checked_off)
    updated_dt = _BASE_DT + timedelta(seconds=updated_off)
    pd = {"audit_checks_at": checked_dt.isoformat()}

    r = _compute_freshness(pd, updated_dt)

    assert r["stale"] == (updated_dt > checked_dt)
    assert r["never_checked"] is False  # checked_at 非空


@settings(max_examples=5)
@given(updated_off=st.integers(min_value=-500_000, max_value=500_000))
def test_p3_never_checked_when_missing(updated_off):
    """checked_at 缺失（无 audit_checks_at / fine_extracted_at）→
    never_checked=True 且 stale=False（fail-safe）。"""
    updated_dt = _BASE_DT + timedelta(seconds=updated_off)
    r = _compute_freshness({}, updated_dt)
    assert r["never_checked"] is True
    assert r["stale"] is False
    assert r["checked_at"] is None


@settings(max_examples=5)
@given(
    bad=st.text(min_size=1, max_size=12).filter(lambda s: "T" not in s and s.strip() != ""),
    updated_off=st.integers(min_value=-500_000, max_value=500_000),
)
def test_p3_unparseable_checked_at_not_stale(bad, updated_off):
    """checked_at 存在但无法解析 → stale=False（不误判过期），never_checked=False
    （曾检查，只是无法解析时间）。"""
    updated_dt = _BASE_DT + timedelta(seconds=updated_off)
    pd = {"audit_checks_at": bad}
    r = _compute_freshness(pd, updated_dt)
    assert r["stale"] is False
    assert r["never_checked"] is False  # raw 非空


@settings(max_examples=5)
@given(checked_off=st.integers(min_value=-500_000, max_value=500_000))
def test_p3_fine_extracted_at_fallback_and_unparseable_updated(checked_off):
    """checked_at 退回 legacy fine_extracted_at；updated_at 无法解析时 stale=False。"""
    checked_dt = _BASE_DT + timedelta(seconds=checked_off)
    pd = {"fine_extracted_at": checked_dt.isoformat()}
    # updated_at 传无法解析字符串 → updated_dt None → stale False
    r = _compute_freshness(pd, "garbage-not-a-date")
    assert r["never_checked"] is False
    assert r["checked_at"] == checked_dt.isoformat()
    assert r["stale"] is False


# ═══════════════════════════════════════════
# P4: 未检查底稿不计通过率
# ═══════════════════════════════════════════

@settings(max_examples=5)
@given(
    n_wp_empty=st.integers(min_value=0, max_value=4),
    checked_specs=st.lists(_PASSED, max_size=6),
)
def test_p4_unchecked_workpaper_contributes_no_items(n_wp_empty, checked_specs):
    """从未产生检查结果的底稿（parsed_data 空）经 `_resolve_wp_checks` 返回空 items，
    不贡献任何 check 项到汇总；仅有检查结果的底稿计入通过率。"""
    all_items: list[AuditCheckItem] = []

    # 未检查底稿：pd 为空 → 返回 ([], [])
    for i in range(n_wp_empty):
        check_dicts, items = _resolve_wp_checks({}, wp_code=f"K{i}", wp_id=f"wp-empty-{i}")
        assert check_dicts == []
        assert items == []
        all_items.extend(items)

    # 有检查结果的底稿（audit_checks 新字段）
    checked_pd = {
        "audit_checks": [
            _mk_item(p).to_dict() for p in checked_specs
        ],
        "audit_checks_at": "2026-07-25T00:00:00",
    }
    _, checked_items = _resolve_wp_checks(checked_pd, wp_code="E1", wp_id="wp-checked")
    all_items.extend(checked_items)

    # all_items 只含有检查结果底稿的项，未检查底稿零贡献
    assert len(all_items) == len(checked_specs)

    s = ProjectCheckSummary.from_items(all_items)
    n_pass = sum(1 for p in checked_specs if p is True)
    n_fail = sum(1 for p in checked_specs if p is False)
    assert s.total == len(checked_specs)
    assert s.decided == n_pass + n_fail
    # 未检查底稿不改变 decided（无论多少张空底稿）
    assert s.passed == n_pass


# ═══════════════════════════════════════════
# P5: 同一勾稽单一口径 + 去重幂等
# ═══════════════════════════════════════════

# 勾稽语义：tb（审定↔TB）/ detail（审定↔明细）
_SEM = st.sampled_from(["tb", "detail"])


def _cycle_item(sem: str, wp_code: str) -> AuditCheckItem:
    if sem == "tb":
        return _mk_item(
            False, source=AuditCheckSource.CYCLE_RECON.value,
            code=f"{wp_code}-RECON-TB", wp_code=wp_code, check_type="balance",
        )
    return _mk_item(
        False, source=AuditCheckSource.CYCLE_RECON.value,
        code=f"{wp_code}-RECON-DETAIL", wp_code=wp_code, check_type="cross_ref",
    )


def _fine_item(sem: str, wp_code: str) -> AuditCheckItem:
    if sem == "tb":
        return _mk_item(
            True, source=AuditCheckSource.FINE_RULE.value,
            code=f"{wp_code}-CHK-01", wp_code=wp_code, check_type="balance",
        )
    return _mk_item(
        True, source=AuditCheckSource.FINE_RULE.value,
        code=f"{wp_code}-CHK-03", wp_code=wp_code, check_type="cross_ref",
    )


@settings(max_examples=5)
@given(sem=_SEM, has_cycle=st.booleans())
def test_p5_dedup_at_most_one_per_semantic_and_prefers_cycle(sem, has_cycle):
    """同一 (wp_code, 勾稽语义) 存在 cycle_recon + fine_rule 时，去重后至多一条且
    保留 cycle_recon；无 cycle_recon 时保留 fine_rule（保守不误删）。"""
    wp_code = "K9-1"
    cyc = _cycle_item(sem, wp_code)
    fine = _fine_item(sem, wp_code)

    items = ([cyc] if has_cycle else []) + [fine]
    merged = _merge_dedup(items)

    # 同语义键唯一（cyc/fine 若都在则去重到一条）
    key = _dedup_key(cyc)
    assert key is not None
    assert key == _dedup_key(fine)  # 两侧同语义键

    same_sem = [it for it in merged if _dedup_key(it) == key]
    assert len(same_sem) == 1

    if has_cycle:
        # 保留 cycle_recon，丢弃 fine_rule
        assert same_sem[0].source == AuditCheckSource.CYCLE_RECON.value
        assert same_sem[0].code == cyc.code
    else:
        # 无对应 cycle_recon → 保留 fine_rule
        assert same_sem[0].source == AuditCheckSource.FINE_RULE.value


@settings(max_examples=5)
@given(
    sems=st.lists(_SEM, min_size=1, max_size=4),
    extra_reported=st.booleans(),
)
def test_p5_dedup_idempotent(sems, extra_reported):
    """`_merge_dedup(_merge_dedup(items)) == _merge_dedup(items)`（幂等），
    S6 上报项（tb_recon）不参与 fine_rule/cycle_recon 去重恒保留。"""
    wp_code = "K9-1"
    items: list[AuditCheckItem] = []
    for i, sem in enumerate(sems):
        items.append(_cycle_item(sem, wp_code))
        items.append(_fine_item(sem, wp_code))
    if extra_reported:
        # S6 上报项：_dedup_key 返回 None，不参与去重
        items.append(
            _mk_item(
                False, source=AuditCheckSource.TB_RECON.value,
                code="G7-REPORT-01", wp_code="G7", check_type="balance",
            )
        )

    once = _merge_dedup(items)
    twice = _merge_dedup(once)

    def _sig(lst):
        return sorted((it.source, it.code) for it in lst)

    assert _sig(once) == _sig(twice)  # 幂等

    # S6 上报项恒保留
    if extra_reported:
        assert any(it.code == "G7-REPORT-01" for it in once)
        assert any(it.code == "G7-REPORT-01" for it in twice)


# ═══════════════════════════════════════════
# P13: 无 audit_checks 退回 fine_checks（不报错）
# ═══════════════════════════════════════════

# fine_check legacy 项 dict strategy（passed 三态 + 简单字段）
_FINE_CHECK = st.builds(
    lambda passed, sev: {
        "code": "CHK-X",
        "type": "balance",
        "severity": sev,
        "passed": passed,
        "message": "m",
    },
    _PASSED,
    _SEVERITY,
)


@settings(max_examples=5)
@given(
    has_audit=st.booleans(),
    audit_specs=st.lists(_PASSED, max_size=5),
    fine_checks=st.lists(_FINE_CHECK, max_size=5),
)
def test_p13_backward_compat_fallback(has_audit, audit_specs, fine_checks):
    """`_resolve_wp_checks` 不抛异常；有 audit_checks（list）时用之（保留原 source），
    否则退回 fine_checks 补 source=fine_rule。"""
    pd: dict = {"fine_extracted_at": "2026-07-20T00:00:00"}
    if fine_checks:
        pd["fine_checks"] = fine_checks
    if has_audit:
        pd["audit_checks"] = [
            _mk_item(p, source=AuditCheckSource.CYCLE_RECON.value).to_dict()
            for p in audit_specs
        ]

    # 不抛异常
    check_dicts, items = _resolve_wp_checks(pd, wp_code="D2", wp_id="wp-1")

    if has_audit:
        # 用 audit_checks（即使空 list 也走此分支），保留原 source
        assert len(items) == len(audit_specs)
        for it in items:
            assert it.source == AuditCheckSource.CYCLE_RECON.value
    else:
        # 退回 legacy fine_checks，补 source=fine_rule
        assert len(items) == len(fine_checks)
        for it in items:
            assert it.source == AuditCheckSource.FINE_RULE.value
            assert it.wp_code == "D2"
            assert it.wp_id == "wp-1"
            assert it.produced_at == "2026-07-20T00:00:00"

    # check_dicts 与 items 一一对应
    assert len(check_dicts) == len(items)


@settings(max_examples=5)
@given(bad=st.one_of(st.none(), st.text(max_size=5), st.integers()))
def test_p13_non_list_audit_checks_falls_back(bad):
    """audit_checks 非 list（None/字符串/数字，异常缓存）→ 退回 fine_checks 分支不报错。"""
    pd = {
        "audit_checks": bad,
        "fine_checks": [
            {"code": "CHK-01", "type": "balance", "passed": True, "severity": "blocking",
             "message": "x"},
        ],
        "fine_extracted_at": "2026-07-20T00:00:00",
    }
    check_dicts, items = _resolve_wp_checks(pd, wp_code="E1", wp_id="wp-2")
    # 非 list → 退回 fine_checks
    assert len(items) == 1
    assert items[0].source == AuditCheckSource.FINE_RULE.value
    assert items[0].code == "CHK-01"
