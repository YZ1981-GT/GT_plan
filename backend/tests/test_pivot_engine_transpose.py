"""Unit tests for PivotEngine.transpose — Task 10.1（advanced-query-module）.

覆盖 R6.2（整表行列互换）与 R6.3（round-trip 对称性）：
- 基本行列互换（标签互换 + 单元格矩阵转置）。
- round-trip：``transpose(transpose(g)) == g``（值 / 行标签 / 列标签 / 行列顺序一致）。
- addr_id 保留、None 空值、Unicode 标签。
- 退化形态：空表、空数据但有标签、单行 / 单列。
- 纯函数性：不修改入参、结果不与入参共享 Cell 引用。

Validates: Requirements 6.2, 6.3
"""

from __future__ import annotations

from app.services.custom_query.pivot_engine import Cell, Grid, PivotEngine


def _grid(row_labels, col_labels, values, addr_ids=None):
    """构造 R×C well-formed Grid；values 为 R×C 值矩阵。"""
    cells = []
    for r, _ in enumerate(row_labels):
        row = []
        for c, _ in enumerate(col_labels):
            aid = None
            if addr_ids is not None:
                aid = addr_ids[r][c]
            row.append(Cell(value=values[r][c], addr_id=aid))
        cells.append(row)
    return Grid(row_labels=list(row_labels), col_labels=list(col_labels), cells=cells)


# ─────────────────────────────────────────────────────────────────────────────
# 基本转置
# ─────────────────────────────────────────────────────────────────────────────
def test_transpose_swaps_labels_and_matrix():
    eng = PivotEngine()
    g = _grid(
        ["r1", "r2"],
        ["c1", "c2", "c3"],
        [[1, 2, 3], [4, 5, 6]],
    )
    t = eng.transpose(g)

    assert t.row_labels == ["c1", "c2", "c3"]
    assert t.col_labels == ["r1", "r2"]
    assert t.n_rows == 3 and t.n_cols == 2
    # out[c][r] == in[r][c]
    assert [[cell.value for cell in row] for row in t.cells] == [
        [1, 4],
        [2, 5],
        [3, 6],
    ]


def test_transpose_preserves_addr_id():
    eng = PivotEngine()
    g = _grid(
        ["r1"],
        ["c1", "c2"],
        [[10, 20]],
        addr_ids=[["A1/S/c1", None]],
    )
    t = eng.transpose(g)
    assert t.cells[0][0].addr_id == "A1/S/c1"
    assert t.cells[1][0].addr_id is None
    assert t.cells[0][0].value == 10
    assert t.cells[1][0].value == 20


def test_transpose_handles_none_and_unicode():
    eng = PivotEngine()
    g = _grid(
        ["科目", "期间"],
        ["借方", "贷方"],
        [["现金", None], [None, "元"]],
    )
    t = eng.transpose(g)
    assert t.row_labels == ["借方", "贷方"]
    assert t.col_labels == ["科目", "期间"]
    assert t.cells[0][0].value == "现金"
    assert t.cells[0][1].value is None
    assert t.cells[1][1].value == "元"


# ─────────────────────────────────────────────────────────────────────────────
# round-trip（R6.3）
# ─────────────────────────────────────────────────────────────────────────────
def test_round_trip_basic():
    eng = PivotEngine()
    g = _grid(
        ["r1", "r2"],
        ["c1", "c2", "c3"],
        [[1, 2, 3], [4, 5, 6]],
        addr_ids=[["a", "b", None], [None, "e", "f"]],
    )
    assert eng.transpose(eng.transpose(g)) == g


def test_round_trip_single_row():
    eng = PivotEngine()
    g = _grid(["only"], ["c1", "c2"], [[7, 8]])
    assert eng.transpose(eng.transpose(g)) == g


def test_round_trip_single_col():
    eng = PivotEngine()
    g = _grid(["r1", "r2", "r3"], ["only"], [[1], [2], [3]])
    assert eng.transpose(eng.transpose(g)) == g


def test_round_trip_empty_grid():
    eng = PivotEngine()
    g = Grid(row_labels=[], col_labels=[], cells=[])
    assert eng.transpose(eng.transpose(g)) == g


def test_round_trip_labels_without_data():
    """退化：有列标签但无数据行（R=0, C=2）——依标签长度确定维度仍严格 round-trip。"""
    eng = PivotEngine()
    g = Grid(row_labels=[], col_labels=["c1", "c2"], cells=[])
    t = eng.transpose(g)
    # 转置后：2 行 0 列
    assert t.row_labels == ["c1", "c2"]
    assert t.col_labels == []
    assert t.cells == [[], []]
    assert eng.transpose(t) == g


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数性
# ─────────────────────────────────────────────────────────────────────────────
def test_transpose_does_not_mutate_input():
    eng = PivotEngine()
    g = _grid(["r1", "r2"], ["c1"], [[1], [2]], addr_ids=[["x"], ["y"]])
    snapshot = g.to_dict()
    eng.transpose(g)
    assert g.to_dict() == snapshot


def test_transpose_result_does_not_share_cell_refs():
    eng = PivotEngine()
    g = _grid(["r1"], ["c1"], [[1]], addr_ids=[["x"]])
    t = eng.transpose(g)
    # 修改结果 Cell 不应影响原 Grid（浅拷贝隔离）
    t.cells[0][0].value = 999
    assert g.cells[0][0].value == 1


def test_grid_dict_round_trip():
    g = _grid(["r1"], ["c1", "c2"], [[1, 2]], addr_ids=[["a", None]])
    assert Grid.from_dict(g.to_dict()) == g
