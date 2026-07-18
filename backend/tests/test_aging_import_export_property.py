# Feature: aging-config-enhancement, Property 12/13: 导出动态列头生成 / 导入 label 匹配
"""导入导出的 Property-Based Tests（hypothesis, max_examples=5）。

覆盖 design.md 中定义的 2 条正确性属性（后端动态列头 + label 匹配纯逻辑）：

- Property 12: Export header generation from bands
    对任意长度 N 的有效 segments，build_aging_headers 生成的列头包含全部 N 个段
    label，且带正确期间前缀（期初/期末未审/期末审定 for 3-period D2/K1/K3/G5/F1 → 3N 列头；
    期初/期末审定 for 2-period D3 → 2N 列头）。
                                                       — Validates Requirements 8.1
- Property 13: Import label matching maps correctly
    对任意带账龄 label 列头的导入行 + 任意匹配的项目账龄配置，match_import_aging 将每列值
    映射到 nested aging 结构中正确的 segment key；label 不匹配当前配置的列被跳过并报 warning。
                                                       — Validates Requirements 8.2, 8.3, 8.4

策略：build_aging_headers / aging_export_values / match_import_aging 均为无 DB 依赖的纯逻辑，
直接用 hypothesis 生成 segments + subject 驱动。段 label/key 保证唯一，以便验证「每列值映射到
正确 segment key」而非仅验证存在性。
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.aging_config_service import AgingSegment
from app.routers.wp_render_strategies._cycle_import_export_common import (
    AGING_PERIOD_LABELS,
    aging_export_values,
    build_aging_headers,
    match_import_aging,
    subject_aging_periods,
)

_PBT = settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# 期间 key → nested 字段名（与 _cycle_import_export_common._AGING_PERIOD_FIELD 对齐）
_PERIOD_FIELD = {"prior": "agingPrior", "current": "agingCurrent", "audited": "agingAudited"}

_THREE_PERIOD = ["D2", "K1", "K3", "G5", "F1"]
_TWO_PERIOD = ["D3"]

# 段 label 字母表：限定为中文/字母/数字，避免括号/空白干扰列头解析
st_label = st.text(
    alphabet="abcdefghij0123456789年月以内至上半以下季度",
    min_size=1,
    max_size=6,
)


@st.composite
def _segments(draw, min_size: int = 2, max_size: int = 10):
    """生成 min_size~max_size 个 label 与 key 均唯一的合法段。"""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    labels = draw(st.lists(st_label, min_size=n, max_size=n, unique=True))
    segs: list[AgingSegment] = []
    for i, lab in enumerate(labels):
        segs.append(
            AgingSegment(
                key=f"seg_{i}",
                label=lab,
                dayFrom=i * 100,
                dayTo=None if i == len(labels) - 1 else i * 100 + 99,
            )
        )
    return segs


st_three_subject = st.sampled_from(_THREE_PERIOD)
st_two_subject = st.sampled_from(_TWO_PERIOD)
st_any_subject = st.sampled_from(_THREE_PERIOD + _TWO_PERIOD)


# ─── Property 12: Export header generation from bands ────────────────────────


@_PBT
@given(segments=_segments(), subject=st_any_subject)
def test_property_12_export_header_count_and_labels(segments, subject):
    """Feature: aging-config-enhancement, Property 12: Export header generation from bands.

    build_aging_headers 生成 len(periods)×N 列头，含全部 N 个 label，
    每个期间前缀正确（3N for D2/K1/K3/G5/F1，2N for D3）。

    Validates: Requirements 8.1
    """
    periods = subject_aging_periods(subject)
    n = len(segments)
    expected_period_count = 3 if subject in _THREE_PERIOD else 2
    assert len(periods) == expected_period_count

    headers = build_aging_headers(segments, periods)

    # 列头总数 = N × 期间数
    assert len(headers) == n * expected_period_count

    # 每个 (period, segment) 组合产生一个 `{label}({period_label})` 列头
    header_set = set(headers)
    for period in periods:
        plabel = AGING_PERIOD_LABELS[period]
        for seg in segments:
            assert f"{seg.label}({plabel})" in header_set

    # 每个段 label 恰好出现「期间数」次
    for seg in segments:
        occur = sum(1 for h in headers if h.startswith(f"{seg.label}("))
        assert occur == expected_period_count

    # 列头无重复（label + key 唯一 → 列头唯一）
    assert len(header_set) == len(headers)


@_PBT
@given(segments=_segments(), subject=st_three_subject)
def test_property_12_three_period_has_all_three_prefixes(segments, subject):
    """Feature: aging-config-enhancement, Property 12: Export header generation from bands.

    3-period 科目（D2/K1/K3/G5）每段必含 期初/期末未审/期末审定 三个前缀列头。

    Validates: Requirements 8.1
    """
    headers = set(build_aging_headers(segments, subject_aging_periods(subject)))
    for seg in segments:
        assert f"{seg.label}(期初)" in headers
        assert f"{seg.label}(期末未审)" in headers
        assert f"{seg.label}(期末审定)" in headers


@_PBT
@given(segments=_segments(), subject=st_two_subject)
def test_property_12_two_period_has_only_prior_audited(segments, subject):
    """Feature: aging-config-enhancement, Property 12: Export header generation from bands.

    2-period 科目（D3）每段仅含 期初/期末审定，无 期末未审。

    Validates: Requirements 8.1
    """
    headers = set(build_aging_headers(segments, subject_aging_periods(subject)))
    for seg in segments:
        assert f"{seg.label}(期初)" in headers
        assert f"{seg.label}(期末审定)" in headers
        assert f"{seg.label}(期末未审)" not in headers


# ─── Property 13: Import label matching maps correctly ───────────────────────


@_PBT
@given(segments=_segments(), subject=st_any_subject)
def test_property_13_import_maps_each_label_to_correct_key(segments, subject):
    """Feature: aging-config-enhancement, Property 13: Import label matching maps correctly.

    对每个 (period, segment) 赋予唯一值 → match_import_aging 将其精确映射到
    nested aging 结构中正确的 segment key，无 unmatched。

    Validates: Requirements 8.2
    """
    periods = subject_aging_periods(subject)
    headers = build_aging_headers(segments, periods)

    # 为每个列头赋唯一值，验证映射到正确 (period, seg.key)
    lookup: dict[str, float] = {}
    expected: dict[str, dict[str, float]] = {}
    for pi, period in enumerate(periods):
        plabel = AGING_PERIOD_LABELS[period]
        field = _PERIOD_FIELD[period]
        expected[field] = {}
        for si, seg in enumerate(segments):
            val = float(pi * 1000 + si + 1)
            lookup[f"{seg.label}({plabel})"] = val
            expected[field][seg.key] = val

    aging, unmatched = match_import_aging(lookup.get, headers, segments, periods)

    assert unmatched == []
    assert set(aging.keys()) == set(expected.keys())
    for field, bucket in expected.items():
        assert aging[field] == bucket


@_PBT
@given(segments=_segments(), subject=st_any_subject, foreign_label=st_label)
def test_property_13_unmatched_columns_skipped_with_warning(segments, subject, foreign_label):
    """Feature: aging-config-enhancement, Property 13: Import label matching maps correctly.

    label 不属于当前配置的账龄列 → 出现在 unmatched（供上层报 warning + 跳过），
    且其值不进入 nested aging 结构。

    Validates: Requirements 8.3, 8.4
    """
    # foreign_label 必须与所有段 label 不同，才能构成"外来账龄列"
    existing = {seg.label for seg in segments}
    if foreign_label in existing:
        return  # 跳过退化样本（外来 label 恰好等于某段 label）

    periods = subject_aging_periods(subject)
    headers = build_aging_headers(segments, periods)
    foreign_header = f"{foreign_label}(期初)"  # 形如账龄列但不属当前配置
    actual_headers = headers + [foreign_header]

    lookup = {h: 1.0 for h in headers}
    lookup[foreign_header] = 999.0

    aging, unmatched = match_import_aging(lookup.get, actual_headers, segments, periods)

    # 外来账龄列被识别为 unmatched
    assert foreign_header in unmatched
    # 外来值未进入 nested 结构
    for field, bucket in aging.items():
        assert set(bucket.keys()) == {seg.key for seg in segments}
        assert 999.0 not in bucket.values()


@_PBT
@given(segments=_segments(min_size=3), subject=st_any_subject)
def test_property_13_old_template_missing_columns_zero_init(segments, subject):
    """Feature: aging-config-enhancement, Property 13: Import label matching maps correctly.

    配置变更后导入缺列的旧模板 → 缺失段初始化为 0（Requirement 8.4 按 label 尽力映射）。

    Validates: Requirements 8.4
    """
    periods = subject_aging_periods(subject)
    # 模拟旧模板只含前 2 段的列头
    present = segments[:2]
    partial_headers = build_aging_headers(present, periods)
    lookup = {h: 7.0 for h in partial_headers}

    aging, unmatched = match_import_aging(lookup.get, partial_headers, segments, periods)

    # 缺列不属"外来账龄"（它们本就是当前配置内的段），不进 unmatched
    assert unmatched == []
    for field in aging.values():
        # 每 period 都补齐全部段 key
        assert set(field.keys()) == {seg.key for seg in segments}
    # 命中段为 7.0，缺失段为 0.0
    present_keys = {s.key for s in present}
    for field in aging.values():
        for seg in segments:
            if seg.key in present_keys:
                assert field[seg.key] == 7.0
            else:
                assert field[seg.key] == 0.0


# ─── export → import 往返（Property 12 + 13 联合） ───────────────────────────


@_PBT
@given(segments=_segments(), subject=st_any_subject)
def test_property_12_13_export_import_roundtrip(segments, subject):
    """Feature: aging-config-enhancement, Property 13: Import label matching maps correctly.

    build_aging_headers + aging_export_values 导出 → match_import_aging 导入，
    nested aging 数据往返一致（导出列头与导入匹配使用同一套 label 格式）。

    Validates: Requirements 8.1, 8.2
    """
    periods = subject_aging_periods(subject)
    headers = build_aging_headers(segments, periods)

    src: dict[str, dict[str, float]] = {}
    for pi, period in enumerate(periods):
        field = _PERIOD_FIELD[period]
        src[field] = {seg.key: float(pi * 10 + si + 1) for si, seg in enumerate(segments)}

    values = aging_export_values(src, segments, periods)
    assert len(values) == len(headers)

    lookup = {h: v for h, v in zip(headers, values)}
    aging, unmatched = match_import_aging(lookup.get, headers, segments, periods)

    assert unmatched == []
    assert aging == src
