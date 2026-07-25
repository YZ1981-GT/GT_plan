"""审计检查 M0 属性测试（audit-check-review-gate-hardening Task 2.4）

用 hypothesis（`@settings(max_examples=5)`）锁定 M0 阶段的正确性属性（design §Correctness
Properties）：

- P1  通过率分母不含未覆盖（Requirements 5.2）
      `ProjectCheckSummary.from_items` 的 `pass_rate` 分母恒 = passed+failed(decided)，
      未覆盖（passed=None）不进分母/分子；decided=0 时 pass_rate=None。
- P2  未覆盖存在时不呈现"全部通过"（Requirements 5.4）
      uncovered>0 ⇒ passed != total（pass_rate=1.0 也不代表 total 全通过）；
      汇总 dict 无 all_passed 布尔全绿字段。
- P3  陈旧判定单调 + never_checked（Requirements 1.2/1.3）
      `_compute_freshness`：checked_at 空 ⇒ never_checked=True 且 stale=False；
      两侧均可解析 ⇒ stale == (updated>checked)；解析失败 ⇒ stale=False 不抛。
- P4  未检查底稿不计通过率（Requirements 1.3/5.1）
      仅非空 checks 底稿决定汇总；空 checks 底稿不改变 decided/passed/failed/uncovered。
- P5  同一勾稽单一口径（Requirements 4.3）
      `_merge_dedup` 对同一 (wp_code, 勾稽语义) 合并后至多一条（cycle_recon > fine_rule），
      且对已去重结果再去重（幂等）结果不变。
- P13 向后兼容（Requirements 10.4）
      无 audit_checks 退回 legacy fine_checks 不报错；每项补 source=fine_rule；check 数守恒。

本文件测「不变量/属性」，非重复具体样例；策略生成边界值（0/负/大数/None/空串/非法时间）。
被测函数均为同步纯函数，无需 async fixture / DB。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

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

_FINE = AuditCheckSource.FINE_RULE.value
_CYCLE = AuditCheckSource.CYCLE_RECON.value

_PASSED = st.sampled_from([True, False, None])
_SEVERITY = st.sampled_from([SEVERITY_BLOCKING, SEVERITY_WARNING, SEVERITY_INFO])


def _mk(
    passed,
    *,
    severity=SEVERITY_INFO,
    source=_FINE,
    wp_code="W",
    code="X",
    check_type="balance",
) -> AuditCheckItem:
    return AuditCheckItem(
        code=code,
        source=source,
        wp_code=wp_code,
        severity=severity,
        check_type=check_type,
        description="d",
        message="m",
        produced_at="",
        passed=passed,
    )


_ITEM = st.builds(_mk, _PASSED, severity=_SEVERITY)


# ═══════════════════════════════════════════
# P1 通过率分母不含未覆盖
# ═══════════════════════════════════════════

@given(items=st.lists(_ITEM, max_size=25))
@settings(max_examples=5, deadline=None)
def test_p1_pass_rate_denominator_excludes_uncovered(items):
    s = ProjectCheckSummary.from_items(items)

    exp_passed = sum(1 for it in items if it.passed is True)
    exp_failed = sum(1 for it in items if it.passed is False)
    exp_uncovered = sum(1 for it in items if it.passed is None)

    # total / 三态计数
    assert s.total == len(items)
    assert s.passed == exp_passed
    assert s.failed == exp_failed
    assert s.uncovered == exp_uncovered

    # decided = passed + failed，未覆盖绝不进分母
    assert s.decided == exp_passed + exp_failed
    assert s.decided + s.uncovered == s.total

    if s.decided == 0:
        # decided=0（含空列表 / 全未覆盖）→ pass_rate=None，不是 0/绿灯
        assert s.pass_rate is None
    else:
        # 分子=passed，分母=decided（不含 uncovered）；exact 相等
        assert s.pass_rate == s.passed / s.decided
        assert 0.0 <= s.pass_rate <= 1.0


# ═══════════════════════════════════════════
# P2 未覆盖存在时不呈现"全部通过"
# ═══════════════════════════════════════════

@given(items=st.lists(_ITEM, max_size=25))
@settings(max_examples=5, deadline=None)
def test_p2_uncovered_never_all_green(items):
    s = ProjectCheckSummary.from_items(items)
    d = s.to_dict()

    # 汇总用数值口径表达，无 all_passed / 全绿 布尔字段
    assert "all_passed" not in d
    assert "all_green" not in d
    assert set(d.keys()) == {
        "total", "decided", "passed", "failed", "uncovered", "pass_rate", "blocking_open",
    }

    # 核心属性：有未覆盖项时 passed 必 < total（pass_rate=1.0 也不代表 total 全通过）
    if s.uncovered > 0:
        assert s.passed < s.total
        if s.pass_rate == 1.0:
            # 已判定全通过，但仍有未覆盖 → 绝不等同"total 全通过"
            assert s.passed != s.total


# ═══════════════════════════════════════════
# P3 陈旧判定单调 + never_checked
# ═══════════════════════════════════════════

# 非法时间串（fromisoformat 无法解析；避免纯日期 "2026-07-25" 这类合法 iso）
_ILLEGAL = st.sampled_from(
    ["not-a-date", "2026-13-99", "??", "abc", "2026/07/25", "2026年07月", "  "]
)


@st.composite
def _dt_variant(draw):
    """生成 (raw_value, expected_utc_instant_or_None)。

    覆盖 None / 空串 / 非法串 / aware iso / naive iso / Z 后缀 —— 后三者都表示同一 UTC 瞬时，
    经 `_parse_iso` 解析应得到相同 instant。
    """
    kind = draw(st.sampled_from(["none", "empty", "illegal", "aware", "naive", "zsuffix"]))
    if kind == "none":
        return None, None
    if kind == "empty":
        return "", None
    if kind == "illegal":
        return draw(_ILLEGAL), None
    base = draw(
        st.datetimes(
            min_value=datetime(2000, 1, 1),
            max_value=datetime(2035, 12, 31),
        )
    )  # naive datetime
    inst = base.replace(tzinfo=timezone.utc)  # 朴素视为 UTC（与 _to_aware 一致）
    if kind == "aware":
        raw = inst.isoformat()          # ...+00:00
    elif kind == "naive":
        raw = base.isoformat()          # 无时区 → _to_aware 补 UTC → 同一 instant
    else:  # zsuffix
        raw = base.isoformat() + "Z"    # ...Z → 解析为 +00:00 → 同一 instant
    return raw, inst


@given(checked=_dt_variant(), updated=_dt_variant(), use_fine_key=st.booleans())
@settings(max_examples=5, deadline=None)
def test_p3_freshness_monotonic_and_never_checked(checked, updated, use_fine_key):
    checked_raw, checked_inst = checked
    updated_raw, updated_inst = updated

    pd: dict = {}
    if checked_raw is not None:
        # checked_at 来源：audit_checks_at（新）或 legacy fine_extracted_at 均可
        pd["fine_extracted_at" if use_fine_key else "audit_checks_at"] = checked_raw

    # 不应抛异常
    result = _compute_freshness(pd, updated_raw)

    # never_checked ⟺ checked_at 原始值 falsy（None/空串）
    expected_never = not bool(checked_raw)
    assert result["never_checked"] == expected_never
    assert isinstance(result["stale"], bool)

    if expected_never or checked_inst is None or updated_inst is None:
        # 未检查 或 任一无法解析 → stale=False（fail-safe，不抛）
        assert result["stale"] is False
    else:
        # 两侧均可解析 → stale 单调等于 updated > checked
        assert result["stale"] == (updated_inst > checked_inst)


# ═══════════════════════════════════════════
# P4 未检查底稿不计通过率
# ═══════════════════════════════════════════

@st.composite
def _cache_check_dict(draw):
    """生成 audit_checks 缓存项 dict（AuditCheckItem.to_dict 形态子集）。"""
    return {
        "code": draw(st.sampled_from(["C1", "C2", "CHK-01", "CHK-03"])),
        "source": draw(st.sampled_from([_FINE, _CYCLE])),
        "wp_code": "W",
        "severity": draw(_SEVERITY),
        "check_type": draw(st.sampled_from(["balance", "cross_ref", "reconciliation"])),
        "passed": draw(_PASSED),
        "message": "m",
    }


@given(
    checked_pds=st.lists(
        st.lists(_cache_check_dict(), min_size=1, max_size=5), max_size=5
    ),
    unchecked_count=st.integers(min_value=0, max_value=6),
    empty_shape=st.sampled_from(["empty_dict", "empty_list", "unrelated"]),
)
@settings(max_examples=5, deadline=None)
def test_p4_unchecked_workpaper_not_counted(checked_pds, unchecked_count, empty_shape):
    items_checked: list[AuditCheckItem] = []
    for i, checks in enumerate(checked_pds):
        pd = {"audit_checks": checks}
        _, items = _resolve_wp_checks(pd, wp_code="W", wp_id=f"c{i}")
        items_checked.extend(items)

    items_all = list(items_checked)
    for j in range(unchecked_count):
        # 未检查底稿：无 audit_checks 且无 fine_checks → 空
        if empty_shape == "empty_dict":
            pd_empty: dict = {}
        elif empty_shape == "empty_list":
            pd_empty = {"audit_checks": []}
        else:
            pd_empty = {"some_other_key": 123}
        cd, items = _resolve_wp_checks(pd_empty, wp_code="W", wp_id=f"e{j}")
        # 未检查底稿不贡献任何 check 项
        assert cd == []
        assert items == []
        items_all.extend(items)

    s_all = ProjectCheckSummary.from_items(items_all)
    s_checked = ProjectCheckSummary.from_items(items_checked)

    # 空 checks 底稿不改变任何汇总统计
    assert s_all == s_checked


# ═══════════════════════════════════════════
# P5 同一勾稽单一口径（去重至多一条 / 幂等）
# ═══════════════════════════════════════════

def _cycle_tb(wp):
    return _mk(None, source=_CYCLE, wp_code=wp, code=f"{wp}-RECON-TB", check_type="balance")


def _cycle_detail(wp):
    return _mk(None, source=_CYCLE, wp_code=wp, code=f"{wp}-RECON-DETAIL", check_type="cross_ref")


def _cycle_adj(wp):
    # RECON-ADJ 语义键为 None（不参与去重，须保留）
    return _mk(None, source=_CYCLE, wp_code=wp, code=f"{wp}-RECON-ADJ", check_type="analysis")


def _fine_chk01(wp):
    return _mk(False, source=_FINE, wp_code=wp, code="CHK-01", check_type="balance")


def _fine_chk03(wp):
    return _mk(True, source=_FINE, wp_code=wp, code="CHK-03", check_type="cross_ref")


def test_p5_dedup_tb_specific_and_idempotent():
    """具体构造（task 指名）：cycle_recon -RECON-TB + fine_rule CHK-01 balance → 至多一条。"""
    items = [_fine_chk01("K9"), _cycle_tb("K9")]
    merged = _merge_dedup(items)
    # 同一 (K9, audited_vs_tb) 只留 cycle_recon，丢弃 fine_rule 快照
    assert len(merged) == 1
    assert merged[0].source == _CYCLE
    assert merged[0].code == "K9-RECON-TB"
    # 幂等：再次去重结果不变
    assert _merge_dedup(merged) == merged


def test_p5_dedup_detail_specific():
    """审定↔明细语义：cycle_recon -RECON-DETAIL 覆盖 fine_rule CHK-03 cross_ref。"""
    items = [_fine_chk03("N2"), _cycle_detail("N2")]
    merged = _merge_dedup(items)
    assert len(merged) == 1
    assert merged[0].source == _CYCLE


def test_p5_dedup_keeps_uncovered_semantics():
    """RECON-ADJ（语义键 None）与无 cycle 覆盖的 fine_rule 均保留（保守不误删）。"""
    items = [_cycle_adj("K9"), _fine_chk01("D2")]  # 不同 wp / 无同键 cycle
    merged = _merge_dedup(items)
    assert len(merged) == 2


@st.composite
def _dedup_scenario(draw):
    wps = draw(
        st.lists(
            st.sampled_from(["K9", "N2", "D2", "G1", "K1"]),
            unique=True,
            min_size=1,
            max_size=5,
        )
    )
    items: list[AuditCheckItem] = []
    for wp in wps:
        # 每 wp 每语义至多一 cycle_recon + 一 fine_rule（对齐聚合器真实产出）
        if draw(st.booleans()):
            items.append(_cycle_tb(wp))
        if draw(st.booleans()):
            items.append(_fine_chk01(wp))
        if draw(st.booleans()):
            items.append(_cycle_detail(wp))
        if draw(st.booleans()):
            items.append(_fine_chk03(wp))
        if draw(st.booleans()):
            items.append(_cycle_adj(wp))  # None 语义键
    return items


@given(items=_dedup_scenario())
@settings(max_examples=5, deadline=None)
def test_p5_dedup_at_most_one_per_semantic_and_idempotent(items):
    merged = _merge_dedup(items)

    # 结果是输入子集，不增项
    assert len(merged) <= len(items)

    # 同一 (wp_code, 勾稽语义) 非 None 键合并后至多一条
    key_counts = Counter(k for k in (_dedup_key(it) for it in merged) if k is not None)
    assert all(c <= 1 for c in key_counts.values())

    # 全部 cycle_recon 项保留（去重只丢被覆盖的 fine_rule）
    n_cycle_in = sum(1 for it in items if it.source == _CYCLE)
    n_cycle_out = sum(1 for it in merged if it.source == _CYCLE)
    assert n_cycle_out == n_cycle_in

    # 被同键 cycle_recon 覆盖的 fine_rule 一律不出现
    cycle_keys = {
        _dedup_key(it) for it in items
        if it.source == _CYCLE and _dedup_key(it) is not None
    }
    for it in merged:
        if it.source == _FINE:
            k = _dedup_key(it)
            assert k is None or k not in cycle_keys

    # 幂等：再次去重结果完全一致
    assert _merge_dedup(merged) == merged


# ═══════════════════════════════════════════
# P13 向后兼容（无 audit_checks 退回 fine_checks 不报错）
# ═══════════════════════════════════════════

@st.composite
def _legacy_fine_check(draw):
    """随机 legacy fine_checks 项：字段任意缺失、passed 三态。"""
    d: dict = {}
    if draw(st.booleans()):
        d["code"] = draw(st.sampled_from(["CHK-01", "CHK-12", "CHK-13", ""]))
    if draw(st.booleans()):
        d["type"] = draw(st.sampled_from(["balance", "cross_ref", "aging", "completeness"]))
    if draw(st.booleans()):
        d["severity"] = draw(_SEVERITY)
    if draw(st.booleans()):
        d["passed"] = draw(_PASSED)
    if draw(st.booleans()):
        d["message"] = draw(st.text(max_size=20))
    if draw(st.booleans()):
        # 边界数值：0 / 负 / 大数
        d["diff"] = draw(st.sampled_from([0.0, -12.5, 1e12, None]))
    return d


# fine_checks 列表：合法 dict 项 + 偶发非 dict 脏项（应被过滤）
_LEGACY_OR_GARBAGE = st.one_of(
    _legacy_fine_check(),
    st.none(),
    st.integers(),
    st.text(max_size=5),
)


@given(
    fine_checks=st.lists(_LEGACY_OR_GARBAGE, max_size=15),
    fine_extracted_at=st.sampled_from(["", "2026-07-25T08:00:00+00:00", "bad-time", None]),
)
@settings(max_examples=5, deadline=None)
def test_p13_fallback_to_fine_checks_no_throw(fine_checks, fine_extracted_at):
    # 无 audit_checks 字段 → 退回 legacy fine_checks
    pd: dict = {"fine_checks": fine_checks}
    if fine_extracted_at is not None:
        pd["fine_extracted_at"] = fine_extracted_at

    # 不抛异常
    check_dicts, items = _resolve_wp_checks(pd, wp_code="E1", wp_id="wp-1")

    dict_count = sum(1 for x in fine_checks if isinstance(x, dict))
    # check 数守恒（仅合法 dict 项计入，脏项被过滤）
    assert len(items) == dict_count
    assert len(check_dicts) == dict_count

    # 每项补 source=fine_rule + 归属 wp
    assert all(it.source == _FINE for it in items)
    assert all(it.wp_code == "E1" for it in items)
    assert all(it.wp_id == "wp-1" for it in items)
    # 展示 dict 也带 source=fine_rule
    assert all(cd.get("source") == _FINE for cd in check_dicts)


def test_p13_empty_parsed_data_no_checks():
    """完全空 parsed_data（无 audit_checks 无 fine_checks）→ 空，不报错。"""
    check_dicts, items = _resolve_wp_checks({}, wp_code="D2", wp_id="wp-x")
    assert check_dicts == []
    assert items == []


def test_p13_audit_checks_present_short_circuits_fallback():
    """含 audit_checks（即使空列表）→ 用新字段不退回 fine_checks。"""
    pd = {"audit_checks": [], "fine_checks": [{"code": "CHK-01", "passed": False}]}
    check_dicts, items = _resolve_wp_checks(pd, wp_code="D2", wp_id="wp-y")
    # audit_checks=[] 短路，不读 legacy fine_checks
    assert check_dicts == []
    assert items == []
