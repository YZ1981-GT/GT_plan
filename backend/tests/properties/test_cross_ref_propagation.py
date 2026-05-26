"""Property 4 PBT: 跨底稿引用传播

**Validates: Requirements 3.11.4 + 3.11.5 + 3.11.6**

七条核心 property（hypothesis 生成 (wp_code, sheet_name, html_data, value_change)）：

- Property 4a (无变化无传播): 当 ``old_html_data == new_html_data`` 且 ``old`` 非 None
  时，``detect_changes`` 返回 ``[]``（没有引用因此被传播）。
- Property 4b (None old 视为首次保存): 当 ``old_html_data is None`` 时，所有匹配
  的引用规则全部进入 affected 列表（首次保存场景需广播一次给下游）。
- Property 4c (引用规则忠实复现): 任何被 emit 的 ``CrossRefChange`` 的 ``ref_id`` /
  ``source_wp_code`` / ``target_wp_code`` 都来自已加载的引用规则（不会凭空捏造）。
- Property 4d (changed_cells 过滤): 当 ``changed_cells`` 非空时，emit 的引用规则
  其 ``source_cell`` 要么在 ``changed_cells`` 内，要么本身就是 falsy
  （即引用规则未指定 source_cell，按 service 当前语义不被 cell-level filter 排除）。
- Property 4e (sheet 过滤): 当引用规则的 ``source_sheet`` 已指定，``sheet_name``
  必须与之相等；不相等时该引用不会被 emit。
- Property 4f (确定性 / 纯函数): 同一 (wp_code, sheet_name, old, new, changed_cells)
  多次调用 ``detect_changes`` 返回 deep-equal 结果，无副作用。
- Property 4g (无规则空集): 当 ``_references`` 加载为空（受控 mock）时，
  ``detect_changes`` 永远返回 ``[]``。

Spec: ``.kiro/specs/workpaper-html-renderer/``

Notes:
- 纯函数测试：直接注入合成 ``_references`` 短路 JSON 加载，不触发 DB / FastAPI / SSE。
- 合成 ref 集合（``SYNTHETIC_REFS``）扁平 schema（``target_wp`` / ``target_sheet`` /
  ``target_cell`` 三个独立 key），与 ``CrossRefService.detect_changes`` 当前消费方式
  对齐（线上 ``cross_wp_references.json`` 嵌套 ``targets`` 列表是另一回事）。
- ``max_examples=50`` + ``suppress_health_check=[HealthCheck.too_slow]``：dict 生成略慢。
"""

from __future__ import annotations

import copy
from typing import Any

from hypothesis import HealthCheck, assume, given, settings as h_settings
from hypothesis import strategies as st

from app.services.cross_ref_service import CrossRefChange, CrossRefService


# ─── 合成引用规则集合 ───────────────────────────────────────────────────────

# 覆盖 6 个常见 wp_code（D2 / E1 / F2 / G7 / D2A / H1），含：
# - source_sheet 指定（精确 sheet 过滤）
# - source_sheet=None（任意 sheet 都触发）
# - 同一 source_wp 多个不同 source_cell（changed_cells filter 测试）
# - D2 / D2A 共享前缀（source_wp.startswith 行为：wp_code="D2" 同时匹配 D2 和 D2A，
#   wp_code="D2A" 仅匹配 D2A）
SYNTHETIC_REFS: list[dict] = [
    {
        "ref_id": "T-01",
        "source_wp": "D2",
        "source_sheet": "审定表D2-1",
        "source_cell": "K15",
        "target_wp": "K8",
        "target_sheet": "审定表K8-1",
        "target_cell": "D1",
    },
    {
        "ref_id": "T-02",
        "source_wp": "D2",
        "source_sheet": "审定表D2-1",
        "source_cell": "L20",
        "target_wp": "F2",
        "target_sheet": "审定表F2-1",
        "target_cell": "C5",
    },
    {
        "ref_id": "T-03",
        "source_wp": "D2A",
        "source_sheet": "明细D2A-2",
        "source_cell": "B10",
        "target_wp": "A1",
        "target_sheet": "资产负债表",
        "target_cell": "BS-007",
    },
    {
        "ref_id": "T-04",
        "source_wp": "E1",
        "source_sheet": "余额调节E1-1",
        "source_cell": "C5",
        "target_wp": "K8",
        "target_sheet": "审定表K8-1",
        "target_cell": "D2",
    },
    {
        "ref_id": "T-05",
        "source_wp": "F2",
        "source_sheet": "盘点F2-3",
        "source_cell": "D8",
        "target_wp": "C12",
        "target_sheet": "存货附注",
        "target_cell": "A3",
    },
    {
        "ref_id": "T-06",
        "source_wp": "G7",
        "source_sheet": "测算G7-1",
        "source_cell": "E10",
        "target_wp": "A1",
        "target_sheet": "利润表",
        "target_cell": "IS-005",
    },
    # source_sheet=None：任意 sheet 都匹配（仅靠 wp_code + source_cell 过滤）
    {
        "ref_id": "T-07",
        "source_wp": "D2",
        "source_sheet": None,
        "source_cell": "M30",
        "target_wp": "N5",
        "target_sheet": "税费附注",
        "target_cell": "B1",
    },
    # source_cell=None：cell-level filter 不生效（任何 changed_cells 都不过滤掉它）
    {
        "ref_id": "T-08",
        "source_wp": "H1",
        "source_sheet": "折旧分配H1-13",
        "source_cell": None,
        "target_wp": "K8",
        "target_sheet": "审定表K8-1",
        "target_cell": "D5",
    },
]


# ─── Helper ─────────────────────────────────────────────────────────────────


def _new_service_with_refs(refs: list[dict]) -> CrossRefService:
    """构造受控 CrossRefService（短路 JSON 加载，注入合成 refs）"""
    svc = CrossRefService()
    svc._references = list(refs)  # copy 防御
    return svc


def _expected_matching_refs(
    refs: list[dict],
    wp_code: str,
    sheet_name: str,
    changed_cells: list[str] | None = None,
) -> list[dict]:
    """复刻 detect_changes 的过滤逻辑（用于断言 emit 集合）"""
    matched: list[dict] = []
    for ref in refs:
        source_wp = ref.get("source_wp", "")
        if not source_wp.startswith(wp_code):
            continue
        ref_source_sheet = ref.get("source_sheet")
        if ref_source_sheet and ref_source_sheet != sheet_name:
            continue
        ref_source_cell = ref.get("source_cell")
        if changed_cells and ref_source_cell:
            if ref_source_cell not in changed_cells:
                continue
        matched.append(ref)
    return matched


def _ref_ids(changes: list[CrossRefChange]) -> set[str]:
    return {c.ref_id for c in changes}


# ─── Hypothesis Strategies ──────────────────────────────────────────────────

# 与 SYNTHETIC_REFS 对齐的 wp_code / sheet 词汇
_WP_CODES: list[str] = ["D2", "E1", "F2", "G7", "D2A", "H1", "K8", "X1"]  # 含 X1 制造无匹配
_SHEET_NAMES: list[str] = [
    "审定表D2-1",
    "明细D2A-2",
    "余额调节E1-1",
    "盘点F2-3",
    "测算G7-1",
    "折旧分配H1-13",
    "未知sheet",
]
_CELL_ADDRS: list[str] = ["K15", "L20", "B10", "C5", "D8", "E10", "M30", "A1", "Z99"]

st_wp_code = st.sampled_from(_WP_CODES)
st_sheet_name = st.sampled_from(_SHEET_NAMES)
st_cell_addr = st.sampled_from(_CELL_ADDRS)

# cell value：标量（数字 / 短字符串 / None）
st_cell_value = st.one_of(
    st.integers(min_value=-9999, max_value=9999),
    st.text(min_size=0, max_size=8),
    st.none(),
)


# 简单的 html_data 嵌套 dict：{"sheet1": {"K15": value, ...}, ...}
st_html_data = st.dictionaries(
    keys=st.sampled_from(["sheet1", "sheet2", "审定表D2-1"]),
    values=st.dictionaries(
        keys=st_cell_addr,
        values=st_cell_value,
        min_size=0,
        max_size=4,
    ),
    min_size=0,
    max_size=3,
)


@st.composite
def st_value_change(draw) -> tuple[Any, Any]:
    """生成一对不相等的 (old, new) 值"""
    old = draw(st_cell_value)
    new = draw(st_cell_value)
    assume(old != new)
    return (old, new)


# changed_cells 策略：可选的 cell 列表
st_changed_cells = st.one_of(
    st.none(),
    st.lists(st_cell_addr, min_size=0, max_size=4),
)


# ─── Property 4a: old == new → 空 affected 列表 ─────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    wp_code=st_wp_code,
    sheet_name=st_sheet_name,
    html_data=st_html_data,
    changed_cells=st_changed_cells,
)
def test_property_4a_no_change_no_propagation(
    wp_code: str,
    sheet_name: str,
    html_data: dict,
    changed_cells: list[str] | None,
) -> None:
    """**Validates: Requirements 3.11.4** — 无变化即无传播

    当 ``old_html_data is not None`` 且 ``old == new`` 时（深拷贝相等），
    ``detect_changes`` 必返回 ``[]``，不向任何下游底稿广播。
    """
    svc = _new_service_with_refs(SYNTHETIC_REFS)

    old = copy.deepcopy(html_data)
    new = copy.deepcopy(html_data)
    assert old == new  # 防御性自检

    affected = svc.detect_changes(
        wp_code=wp_code,
        sheet_name=sheet_name,
        old_html_data=old,
        new_html_data=new,
        changed_cells=changed_cells,
    )

    assert affected == [], (
        f"old==new 时不应广播任何 cross-ref，实际 {[c.to_dict() for c in affected]!r} "
        f"(wp_code={wp_code!r}, sheet_name={sheet_name!r})"
    )


# ─── Property 4b: old=None → 所有匹配 refs 全部 emit ────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    wp_code=st_wp_code,
    sheet_name=st_sheet_name,
    new_html=st_html_data,
    changed_cells=st_changed_cells,
)
def test_property_4b_none_old_emits_all_matching_refs(
    wp_code: str,
    sheet_name: str,
    new_html: dict,
    changed_cells: list[str] | None,
) -> None:
    """**Validates: Requirements 3.11.5** — 首次保存视为变更

    ``old_html_data is None`` 表示首次保存，service 应把所有匹配
    (wp_code prefix + sheet_name + changed_cells) 的引用规则全部 emit
    给下游订阅方做一次刷新。
    """
    svc = _new_service_with_refs(SYNTHETIC_REFS)

    affected = svc.detect_changes(
        wp_code=wp_code,
        sheet_name=sheet_name,
        old_html_data=None,
        new_html_data=new_html,
        changed_cells=changed_cells,
    )

    expected = _expected_matching_refs(
        SYNTHETIC_REFS, wp_code, sheet_name, changed_cells
    )

    assert _ref_ids(affected) == {r["ref_id"] for r in expected}, (
        f"old=None 时 emit 集合不等于期望匹配集合：\n"
        f"  expected ref_ids={sorted(r['ref_id'] for r in expected)}\n"
        f"  actual   ref_ids={sorted(_ref_ids(affected))}\n"
        f"  (wp_code={wp_code!r}, sheet_name={sheet_name!r}, "
        f"changed_cells={changed_cells!r})"
    )


# ─── Property 4c: emit 的引用必须来自加载的规则集 ──────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    wp_code=st_wp_code,
    sheet_name=st_sheet_name,
    old_html=st.one_of(st.none(), st_html_data),
    value_change=st_value_change(),
    changed_cells=st_changed_cells,
)
def test_property_4c_emitted_refs_are_faithful(
    wp_code: str,
    sheet_name: str,
    old_html: dict | None,
    value_change: tuple[Any, Any],
    changed_cells: list[str] | None,
) -> None:
    """**Validates: Requirements 3.11.4** — 引用规则忠实复现

    任何被 emit 的 ``CrossRefChange``，其 ``ref_id`` / ``source_wp_code`` /
    ``target_wp_code`` 都必须出现在 ``_references`` 里（不会凭空捏造）。
    """
    svc = _new_service_with_refs(SYNTHETIC_REFS)

    # 用 value_change 构造一个真的有变化的 new_html
    old, new_val = value_change
    new_html = copy.deepcopy(old_html) if old_html is not None else {}
    # 在某个 sheet 上塞一个变化值（即便 old is None 也无所谓）
    new_html.setdefault("sheet1", {})["K15"] = new_val
    if old_html is not None and old_html.get("sheet1", {}).get("K15") == new_val:
        # 避免 old/new 在 K15 巧合相等 —— 改塞另一个绝对独特的标记
        new_html["sheet1"]["K15"] = ("__pbt_marker__", new_val)

    affected = svc.detect_changes(
        wp_code=wp_code,
        sheet_name=sheet_name,
        old_html_data=old_html,
        new_html_data=new_html,
        changed_cells=changed_cells,
    )

    # 建立 ref_id → ref dict 用于反查
    ref_by_id = {r["ref_id"]: r for r in SYNTHETIC_REFS}
    valid_ref_ids = set(ref_by_id.keys())
    valid_source_wps = {r["source_wp"] for r in SYNTHETIC_REFS}
    valid_target_wps = {r["target_wp"] for r in SYNTHETIC_REFS}

    for change in affected:
        assert isinstance(change, CrossRefChange), (
            f"emit 类型异常：{type(change).__name__}"
        )
        assert change.ref_id in valid_ref_ids, (
            f"emit ref_id={change.ref_id!r} 不在加载规则集 {valid_ref_ids}"
        )
        assert change.source_wp_code in valid_source_wps, (
            f"emit source_wp_code={change.source_wp_code!r} 凭空捏造，"
            f"合法集合 {valid_source_wps}"
        )
        assert change.target_wp_code in valid_target_wps, (
            f"emit target_wp_code={change.target_wp_code!r} 凭空捏造，"
            f"合法集合 {valid_target_wps}"
        )
        # ref_id 与 target_wp_code 必须匹配规则表的同一条
        ref = ref_by_id[change.ref_id]
        assert change.target_wp_code == ref["target_wp"], (
            f"emit target_wp_code={change.target_wp_code!r} 与 ref {change.ref_id!r} "
            f"的 target_wp={ref['target_wp']!r} 不一致"
        )
        # source_wp_code 与 ref.source_wp 一致（service 直接 echo）
        assert change.source_wp_code == ref["source_wp"], (
            f"emit source_wp_code={change.source_wp_code!r} 与 ref {change.ref_id!r} "
            f"的 source_wp={ref['source_wp']!r} 不一致"
        )


# ─── Property 4d: changed_cells 过滤 ───────────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    wp_code=st_wp_code,
    sheet_name=st_sheet_name,
    changed_cells=st.lists(st_cell_addr, min_size=1, max_size=3),
)
def test_property_4d_changed_cells_filter(
    wp_code: str,
    sheet_name: str,
    changed_cells: list[str],
) -> None:
    """**Validates: Requirements 3.11.4** — changed_cells cell-level 过滤

    当 ``changed_cells`` 非空时，emit 的每条 ``CrossRefChange`` 对应的引用规则
    其 ``source_cell`` 必须满足下列之一：
      - 在 ``changed_cells`` 列表内（精确命中）
      - 本身为 falsy（service 当前语义：未指定 cell 的规则不被 cell-level filter 排除）
    """
    svc = _new_service_with_refs(SYNTHETIC_REFS)

    # old=None 触发"全量首次广播"路径，最大化 emit 候选集，便于断言过滤效果
    affected = svc.detect_changes(
        wp_code=wp_code,
        sheet_name=sheet_name,
        old_html_data=None,
        new_html_data={"sheet1": {"K15": 1}},
        changed_cells=changed_cells,
    )

    ref_by_id = {r["ref_id"]: r for r in SYNTHETIC_REFS}
    for change in affected:
        ref = ref_by_id[change.ref_id]
        ref_source_cell = ref.get("source_cell")
        # 满足"在 changed_cells 内 OR 规则本身没指定 source_cell"
        ok = (
            (ref_source_cell and ref_source_cell in changed_cells)
            or not ref_source_cell
        )
        assert ok, (
            f"emit ref={change.ref_id!r} source_cell={ref_source_cell!r} 既不在 "
            f"changed_cells={changed_cells!r} 内，也不是 falsy，过滤逻辑被违反"
        )


# ─── Property 4e: source_sheet 过滤 ────────────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    wp_code=st_wp_code,
    sheet_name=st_sheet_name,
)
def test_property_4e_source_sheet_filter(
    wp_code: str,
    sheet_name: str,
) -> None:
    """**Validates: Requirements 3.11.4** — sheet-level 过滤

    引用规则若已指定 ``source_sheet``，emit 时的 ``sheet_name`` 必须与之相等；
    ``source_sheet=None`` 的规则不受此约束（任意 sheet 都触发）。
    """
    svc = _new_service_with_refs(SYNTHETIC_REFS)

    affected = svc.detect_changes(
        wp_code=wp_code,
        sheet_name=sheet_name,
        old_html_data=None,
        new_html_data={"sheet1": {"K15": 1}},
        changed_cells=None,
    )

    ref_by_id = {r["ref_id"]: r for r in SYNTHETIC_REFS}
    for change in affected:
        ref = ref_by_id[change.ref_id]
        ref_source_sheet = ref.get("source_sheet")
        if ref_source_sheet:
            assert ref_source_sheet == sheet_name, (
                f"emit ref={change.ref_id!r} source_sheet={ref_source_sheet!r} != "
                f"sheet_name={sheet_name!r}，sheet-level 过滤被违反"
            )
        # ref_source_sheet falsy 时无约束


# ─── Property 4f: 确定性（纯函数） ─────────────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    wp_code=st_wp_code,
    sheet_name=st_sheet_name,
    old_html=st.one_of(st.none(), st_html_data),
    new_html=st_html_data,
    changed_cells=st_changed_cells,
)
def test_property_4f_deterministic(
    wp_code: str,
    sheet_name: str,
    old_html: dict | None,
    new_html: dict,
    changed_cells: list[str] | None,
) -> None:
    """**Validates: Requirements 3.11.6** — 纯函数，无副作用

    同一 ``(wp_code, sheet_name, old, new, changed_cells)`` 多次调用
    ``detect_changes`` 必须返回结构相等的 affected 列表（顺序也保持），
    且不修改输入参数。
    """
    svc = _new_service_with_refs(SYNTHETIC_REFS)

    old_snapshot = copy.deepcopy(old_html)
    new_snapshot = copy.deepcopy(new_html)
    cells_snapshot = copy.deepcopy(changed_cells)

    r1 = svc.detect_changes(wp_code, sheet_name, old_html, new_html, changed_cells)
    r2 = svc.detect_changes(wp_code, sheet_name, old_html, new_html, changed_cells)
    r3 = svc.detect_changes(wp_code, sheet_name, old_html, new_html, changed_cells)

    # 序列化对比，避免对象身份差异
    d1 = [c.to_dict() for c in r1]
    d2 = [c.to_dict() for c in r2]
    d3 = [c.to_dict() for c in r3]

    assert d1 == d2 == d3, (
        f"detect_changes 不是纯函数：\n  call1={d1!r}\n  call2={d2!r}\n  call3={d3!r}"
    )

    # 输入参数未被修改
    assert old_html == old_snapshot, "detect_changes 修改了 old_html_data"
    assert new_html == new_snapshot, "detect_changes 修改了 new_html_data"
    assert changed_cells == cells_snapshot, "detect_changes 修改了 changed_cells"


# ─── Property 4g: 空规则集 → 空 affected ───────────────────────────────────


@h_settings(max_examples=50, deadline=None,
            suppress_health_check=[HealthCheck.too_slow])
@given(
    wp_code=st_wp_code,
    sheet_name=st_sheet_name,
    old_html=st.one_of(st.none(), st_html_data),
    new_html=st_html_data,
    changed_cells=st_changed_cells,
)
def test_property_4g_empty_refs_returns_empty(
    wp_code: str,
    sheet_name: str,
    old_html: dict | None,
    new_html: dict,
    changed_cells: list[str] | None,
) -> None:
    """**Validates: Requirements 3.11.4** — 无规则即无传播

    当 ``_references`` 为空（mock 引用文件缺失或被刻意清空），
    ``detect_changes`` 永远返回 ``[]``，不会因 old/new 差异产生幽灵广播。
    """
    svc = _new_service_with_refs([])  # 空引用集

    affected = svc.detect_changes(
        wp_code=wp_code,
        sheet_name=sheet_name,
        old_html_data=old_html,
        new_html_data=new_html,
        changed_cells=changed_cells,
    )

    assert affected == [], (
        f"空引用集应返回 []，实际 {[c.to_dict() for c in affected]!r}"
    )


# ─── 单元测试：边界 case（PBT 互补） ────────────────────────────────────────


def test_d2_prefix_matches_d2a_intentionally() -> None:
    """wp_code='D2' 因 startswith 同时匹配 source_wp='D2' 和 'D2A'

    复刻 service 当前语义：``source_wp.startswith(wp_code)``。"""
    svc = _new_service_with_refs(SYNTHETIC_REFS)
    affected = svc.detect_changes(
        wp_code="D2",
        sheet_name="审定表D2-1",  # 仅 D2 ref 的 source_sheet 命中
        old_html_data=None,
        new_html_data={"sheet1": {"K15": 1}},
        changed_cells=None,
    )
    ids = _ref_ids(affected)
    # T-01 / T-02 / T-07 都是 source_wp='D2'，且 sheet 匹配（T-07 source_sheet=None
    # 任意 sheet 都匹配）；T-03 source_wp='D2A' 但 source_sheet='明细D2A-2' ≠ 当前
    # sheet '审定表D2-1'，被过滤掉
    assert ids == {"T-01", "T-02", "T-07"}, ids


def test_d2a_prefix_does_not_match_d2() -> None:
    """wp_code='D2A' 仅匹配 source_wp='D2A'（不会反向匹配 'D2'）"""
    svc = _new_service_with_refs(SYNTHETIC_REFS)
    affected = svc.detect_changes(
        wp_code="D2A",
        sheet_name="明细D2A-2",
        old_html_data=None,
        new_html_data={"sheet1": {"K15": 1}},
        changed_cells=None,
    )
    ids = _ref_ids(affected)
    assert ids == {"T-03"}, ids


def test_no_match_wp_code_returns_empty() -> None:
    """wp_code='X1' 在 SYNTHETIC_REFS 中无任何 source_wp 匹配 → []"""
    svc = _new_service_with_refs(SYNTHETIC_REFS)
    affected = svc.detect_changes(
        wp_code="X1",
        sheet_name="审定表D2-1",
        old_html_data=None,
        new_html_data={"sheet1": {"K15": 1}},
        changed_cells=None,
    )
    assert affected == []


def test_changed_cells_filters_out_other_cells() -> None:
    """changed_cells=['K15'] → T-01 命中，T-02 (source_cell=L20) 不命中"""
    svc = _new_service_with_refs(SYNTHETIC_REFS)
    affected = svc.detect_changes(
        wp_code="D2",
        sheet_name="审定表D2-1",
        old_html_data=None,
        new_html_data={"sheet1": {"K15": 1}},
        changed_cells=["K15"],
    )
    ids = _ref_ids(affected)
    # T-01 (source_cell=K15) 命中；T-02 (L20) / T-07 (M30) 被 cell-level filter 排除
    assert ids == {"T-01"}, ids


def test_h1_no_source_cell_not_filtered_by_changed_cells() -> None:
    """T-08 source_cell=None → 任何 changed_cells 都不会过滤掉它"""
    svc = _new_service_with_refs(SYNTHETIC_REFS)
    affected = svc.detect_changes(
        wp_code="H1",
        sheet_name="折旧分配H1-13",
        old_html_data=None,
        new_html_data={"sheet1": {"K15": 1}},
        changed_cells=["NEVER_MATCH"],
    )
    ids = _ref_ids(affected)
    assert ids == {"T-08"}, ids


def test_old_equals_new_returns_empty() -> None:
    """old == new 即便有匹配规则也返回 []"""
    svc = _new_service_with_refs(SYNTHETIC_REFS)
    same = {"sheet1": {"K15": 100}}
    affected = svc.detect_changes(
        wp_code="D2",
        sheet_name="审定表D2-1",
        old_html_data=copy.deepcopy(same),
        new_html_data=copy.deepcopy(same),
        changed_cells=None,
    )
    assert affected == []


def test_old_differs_from_new_emits_matching_refs() -> None:
    """old != new 且有匹配规则 → emit"""
    svc = _new_service_with_refs(SYNTHETIC_REFS)
    affected = svc.detect_changes(
        wp_code="D2",
        sheet_name="审定表D2-1",
        old_html_data={"sheet1": {"K15": 100}},
        new_html_data={"sheet1": {"K15": 200}},
        changed_cells=None,
    )
    ids = _ref_ids(affected)
    # T-01 / T-02 / T-07（D2 source_wp + sheet 匹配 / source_sheet=None）
    assert ids == {"T-01", "T-02", "T-07"}, ids
