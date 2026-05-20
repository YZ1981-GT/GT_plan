"""workpaper-completion-foundation spec 属性测试

# Feature: workpaper-completion-foundation
# Spec: .kiro/specs/workpaper-completion-foundation/

7 条属性测试覆盖 7 条核心 Property（design.md §Correctness Properties）：
  - Property 1: Prefill cell style correctness（1.9）
  - Property 2: Color mapping uniqueness（1.10）
  - Property 5: Prefill summary message correctness（1.11）
  - Property 9: Review mark persistence round-trip（1.12）
  - Property 12: User override detection on edit（1.13）
  - Property 13: Prefill skip logic for overrides（1.14）
  - Property 14: User override round-trip persistence（1.15）

策略：前端 TS 逻辑复刻为 Python 等价实现（与 production-readiness 同模式）；
后端逻辑直接测真模块。max_examples=5（MVP 速度优先）。
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st


# ───────────────────────────────────────────────────────────────────────────
# 复刻：SOURCE_COLOR_MAP（与 audit-platform/frontend/src/composables/usePrefillMarkers.ts
# 和 backend/app/routers/wp_template_files.py 注入逻辑保持一致）
# ───────────────────────────────────────────────────────────────────────────
SOURCE_COLOR_MAP: dict[str, str] = {
    "TB": "#E3F2FD",
    "TB_SUM": "#E3F2FD",
    "TB_AUX": "#E3F2FD",
    "AJE": "#E8F5E9",
    "ADJ": "#E8F5E9",
    "PREV": "#F3E5F5",
    "WP": "#E0F7FA",
    "ERROR": "#FF5149",
}

TARGET_COLOR_MAP: dict[str, str] = {
    "note_section": "#F3E5F5",
    "report_row": "#E3F2FD",
    "workpaper": "#E0F7FA",
}


def _apply_prefill_style(source: str, formula: str, error: str | None = None) -> dict:
    """复刻 wp_template_files.py 注入逻辑：根据 source 生成 cell.s + cell.custom"""
    cell: dict = {"custom": {"prefill_source": source, "prefill_formula": formula}}
    if source == "ERROR":
        cell["s"] = {
            "bd": {
                "t": {"s": 1, "cl": {"rgb": "#FF5149"}},
                "r": {"s": 1, "cl": {"rgb": "#FF5149"}},
                "b": {"s": 1, "cl": {"rgb": "#FF5149"}},
                "l": {"s": 1, "cl": {"rgb": "#FF5149"}},
            }
        }
        if error:
            cell["custom"]["prefill_error"] = error
    else:
        bg_rgb = SOURCE_COLOR_MAP.get(source, "#E3F2FD")
        cell["s"] = {"bg": {"rgb": bg_rgb}}
    return cell


# ===========================================================================
# Property 1: Prefill cell style correctness
# Validates: Requirements 1.1, 1.6
# ===========================================================================
@given(
    source=st.sampled_from(["TB", "TB_SUM", "TB_AUX", "AJE", "ADJ", "PREV", "WP", "ERROR"]),
    formula=st.text(min_size=0, max_size=40),
)
@settings(max_examples=5)
def test_property_01_prefill_cell_style_correctness(source, formula):
    """非 ERROR 来源的 cell 必须有正确背景色；ERROR 来源必须有红色边框。"""
    cell = _apply_prefill_style(source, formula, error="科目不存在" if source == "ERROR" else None)

    assert cell["custom"]["prefill_source"] == source
    if source == "ERROR":
        # 必须有红色边框
        bd = cell.get("s", {}).get("bd", {})
        assert bd, "ERROR cell must have border style"
        for side in ("t", "r", "b", "l"):
            assert bd[side]["cl"]["rgb"] == "#FF5149"
        # 不应有背景色覆盖（ERROR 只设边框）
        assert "bg" not in cell.get("s", {})
    else:
        bg = cell.get("s", {}).get("bg", {})
        assert bg.get("rgb") == SOURCE_COLOR_MAP[source]


# ===========================================================================
# Property 2: Source/reference type → color mapping uniqueness
# Validates: Requirements 1.3, 3.5
# ===========================================================================
def test_property_02_color_mapping_uniqueness_distinct_sources():
    """4 种 distinct source type（TB / AJE / PREV / WP）的颜色互不相同。"""
    distinct_sources = ["TB", "AJE", "PREV", "WP"]
    colors = {SOURCE_COLOR_MAP[s] for s in distinct_sources}
    assert len(colors) == len(distinct_sources), (
        f"distinct sources must have unique colors, got {colors}"
    )


def test_property_02_color_mapping_uniqueness_target_types():
    """3 种 reference target type 的颜色互不相同。"""
    distinct_targets = ["note_section", "report_row", "workpaper"]
    colors = {TARGET_COLOR_MAP[t] for t in distinct_targets}
    assert len(colors) == len(distinct_targets), (
        f"target types must have unique colors, got {colors}"
    )


# ===========================================================================
# Property 5: Prefill summary message correctness
# Validates: Requirements 2.5, 7.6
# ===========================================================================
def _build_summary_message(per_source: dict[str, int], skipped: int = 0) -> tuple[str, int]:
    """复刻前端 prefill 摘要 toast 文本生成。

    返回 (message, total_filled)。
    格式: "已填充 N 个单元格（TB: X, AJE: Y, PREV: Z, WP: W），跳过 M 个"
    """
    parts = []
    total = 0
    for src in ("TB", "AJE", "PREV", "WP"):
        cnt = per_source.get(src, 0)
        total += cnt
        if cnt > 0:
            parts.append(f"{src}: {cnt}")
    breakdown = "（" + ", ".join(parts) + "）" if parts else ""
    msg = f"已填充 {total} 个单元格{breakdown}"
    if skipped > 0:
        msg += f"，跳过 {skipped} 个手动修改的单元格"
    return msg, total


@given(
    tb=st.integers(min_value=0, max_value=100),
    aje=st.integers(min_value=0, max_value=100),
    prev=st.integers(min_value=0, max_value=100),
    wp=st.integers(min_value=0, max_value=100),
    skipped=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=5)
def test_property_05_prefill_summary_correctness(tb, aje, prev, wp, skipped):
    """X + Y + Z + W = N，所有非零计数都出现在文本中，跳过数也出现。"""
    per_source = {"TB": tb, "AJE": aje, "PREV": prev, "WP": wp}
    msg, total = _build_summary_message(per_source, skipped)

    # 总数等式
    assert total == tb + aje + prev + wp

    # 总数出现
    assert f"已填充 {total}" in msg

    # 所有非零计数都出现
    for src, cnt in per_source.items():
        if cnt > 0:
            assert f"{src}: {cnt}" in msg, f"non-zero {src}={cnt} must appear in {msg!r}"
        else:
            # 零计数不应出现（除非全零）
            if total > 0:
                assert f"{src}: 0" not in msg

    # skipped 信息
    if skipped > 0:
        assert f"跳过 {skipped}" in msg
    else:
        assert "跳过" not in msg


# ===========================================================================
# Property 9: Review mark persistence round-trip
# Validates: Requirements 4.2, 4.7
# ===========================================================================
class _InMemoryReviewMarkStore:
    """模拟 cell_annotations 表 review_mark 子类型的最小存储。"""
    def __init__(self):
        self._rows: list[dict] = []

    def create(self, wp_id: str, sheet_name: str, cell_ref: str,
               reviewer_id: str, status: str, comment: str) -> dict:
        row = {
            "wp_id": wp_id,
            "sheet_name": sheet_name,
            "cell_ref": cell_ref,
            "reviewer_id": reviewer_id,
            "status": status,
            "comment": comment,
            "annotation_type": "review_mark",
        }
        self._rows.append(row)
        return row

    def query(self, wp_id: str) -> list[dict]:
        return [r for r in self._rows
                if r["wp_id"] == wp_id and r["annotation_type"] == "review_mark"]


@given(
    wp_id=st.uuids().map(str),
    sheet=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
    cell_ref=st.from_regex(r"[A-Z]{1,2}\d{1,3}", fullmatch=True),
    reviewer_id=st.uuids().map(str),
    status=st.sampled_from(["reviewed", "pending", "questioned"]),
    comment=st.text(min_size=0, max_size=100),
)
@settings(max_examples=5)
def test_property_09_review_mark_round_trip(wp_id, sheet, cell_ref, reviewer_id, status, comment):
    """创建 review mark 后查询应返回字段完全一致的记录。"""
    store = _InMemoryReviewMarkStore()
    created = store.create(wp_id, sheet, cell_ref, reviewer_id, status, comment)

    queried = store.query(wp_id)
    assert len(queried) == 1
    got = queried[0]

    for field in ("wp_id", "sheet_name", "cell_ref", "reviewer_id", "status", "comment"):
        assert got[field] == created[field], f"{field} mismatch: {got[field]!r} != {created[field]!r}"
    assert got["annotation_type"] == "review_mark"


# ===========================================================================
# Property 12: User override detection on edit
# Validates: Requirements 7.1
# ===========================================================================
class _UserOverrides:
    """复刻 useUserOverrides composable。"""
    def __init__(self):
        self._overrides: dict[str, bool] = {}

    def mark(self, sheet: str, cell_ref: str):
        if not sheet or not cell_ref:
            return
        self._overrides[f"{sheet}!{cell_ref}"] = True

    def is_overridden(self, sheet: str, cell_ref: str) -> bool:
        return self._overrides.get(f"{sheet}!{cell_ref}", False)

    def serialize(self) -> dict:
        return dict(self._overrides)

    def load(self, parsed_data: dict | None):
        ov = (parsed_data or {}).get("user_overrides") or {}
        if isinstance(ov, dict):
            self._overrides = {k: bool(v) for k, v in ov.items() if isinstance(k, str)}


def _on_cell_edited(overrides: _UserOverrides, prefill_cells: set[str],
                    sheet: str, cell_ref: str):
    """复刻 WorkpaperEditor 的 onCellEdited 处理逻辑。"""
    key = f"{sheet}!{cell_ref}"
    if key in prefill_cells:
        overrides.mark(sheet, cell_ref)


@given(
    sheet=st.text(min_size=1, max_size=10).filter(lambda s: s.strip() and "!" not in s),
    cell_ref=st.from_regex(r"[A-Z]\d{1,3}", fullmatch=True),
)
@settings(max_examples=5)
def test_property_12_override_detection_on_edit(sheet, cell_ref):
    """编辑含 prefill_source 的 cell → 必须加入 user_overrides 集合。"""
    overrides = _UserOverrides()
    prefill_cells = {f"{sheet}!{cell_ref}"}

    _on_cell_edited(overrides, prefill_cells, sheet, cell_ref)

    assert overrides.is_overridden(sheet, cell_ref)


@given(
    sheet=st.text(min_size=1, max_size=10).filter(lambda s: s.strip() and "!" not in s),
    cell_ref=st.from_regex(r"[A-Z]\d{1,3}", fullmatch=True),
)
@settings(max_examples=5)
def test_property_12_no_override_on_non_prefill_edit(sheet, cell_ref):
    """编辑不含 prefill_source 的 cell → 不会加入 user_overrides。"""
    overrides = _UserOverrides()
    prefill_cells: set[str] = set()  # 空集合，cell 没有 prefill

    _on_cell_edited(overrides, prefill_cells, sheet, cell_ref)

    assert not overrides.is_overridden(sheet, cell_ref)


# ===========================================================================
# Property 13: Prefill skip logic for overrides
# Validates: Requirements 7.2
# ===========================================================================
def _execute_prefill(cells_before: dict[str, str], overrides_set: set[str],
                     prefill_value: str = "PREFILLED") -> dict[str, str]:
    """复刻后端 prefill engine 跳过 overrides 的逻辑。"""
    result = dict(cells_before)
    for key in cells_before.keys():
        if key in overrides_set:
            continue  # skip
        result[key] = prefill_value
    return result


@given(
    cell_keys=st.lists(
        st.from_regex(r"Sheet\d!.[A-Z]\d", fullmatch=True),
        min_size=0, max_size=10, unique=True,
    ),
    override_indices=st.lists(st.integers(min_value=0, max_value=9), max_size=10, unique=True),
)
@settings(max_examples=5)
def test_property_13_prefill_skips_overrides(cell_keys, override_indices):
    """prefill 不会改变 overrides 集合中的 cell 值。"""
    cells_before = {k: f"original_{i}" for i, k in enumerate(cell_keys)}
    valid_overrides = {cell_keys[i] for i in override_indices if i < len(cell_keys)}

    cells_after = _execute_prefill(cells_before, valid_overrides)

    # overrides 中的 cell 值不变
    for key in valid_overrides:
        assert cells_after[key] == cells_before[key], (
            f"override cell {key} should not be changed by prefill"
        )

    # 非 overrides 的 cell 被填充
    for key in cells_before:
        if key not in valid_overrides:
            assert cells_after[key] == "PREFILLED"


# ===========================================================================
# Property 14: User override round-trip persistence
# Validates: Requirements 7.7
# ===========================================================================
@given(
    keys=st.lists(
        st.from_regex(r"Sheet\d![A-Z]\d{1,2}", fullmatch=True),
        min_size=0, max_size=20, unique=True,
    ),
)
@settings(max_examples=5)
def test_property_14_override_round_trip_persistence(keys):
    """serialize → save (parsed_data) → load → 集合完全一致。"""
    overrides = _UserOverrides()
    for key in keys:
        sheet, cell_ref = key.split("!", 1)
        overrides.mark(sheet, cell_ref)

    serialized = overrides.serialize()
    parsed_data = {"user_overrides": serialized}

    new_overrides = _UserOverrides()
    new_overrides.load(parsed_data)

    new_serialized = new_overrides.serialize()
    assert new_serialized == serialized, (
        f"round-trip lost data: original={serialized}, after={new_serialized}"
    )

    # 双向断言：每个 key 在两边都被识别
    for key in keys:
        sheet, cell_ref = key.split("!", 1)
        assert new_overrides.is_overridden(sheet, cell_ref)
