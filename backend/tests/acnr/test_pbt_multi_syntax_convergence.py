# Feature: acnr, Property 4: 多语法一致性解析
"""Property-based test: 多语法一致性解析（同格殊途同归，含索引/公式/uri/tb 域委托）。

**Validates: Requirements 5.1, 5.3, 5.7, 11.2, 11.3, 14.4, 16.4, 22.3, 22.5**

验证规则:
- R5.1: resolve() 收到 formula_ref / uri / addr_id / index_ref 任一输入均可解析
- R5.3: 解析命中时返回 found=True + addr_id + entry_type + cell_address 等
- R5.7: 非 wp 域（tb/report/note/aux）经同一 resolve() 出口委托 V1 返回统一契约
- R11.2: 索引语法 TB:1001 与公式语法 TB('1001','审定数') 解析到同一目标
- R11.3: cell:D2-2!E100 解析为 addr_id D2/D2-2/E100
- R14.4: WP() 第三参为语义名时内部解析到 A1 坐标
- R16.4: 附注引用审定表/明细表数据经 resolve() 获取物理格
- R22.3: 消费者经 resolve() 访问任一域无需区分数据来自 L1 还是 V1
- R22.5: 无论数据来源均返回相同数据格式与行为

核心属性:
  对 CellCatalogEntry 中任一条目，使用 formula_ref / uri / addr_id / index_ref
  四种语法调用 full_resolve() 均应收敛到同一 canonical addr_id。
  TB 域: index TB:1001 和 formula TB('1001','审定数') 解析到同一目标。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis.strategies import sampled_from

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Load actual catalog data
# ---------------------------------------------------------------------------

_CATALOG_PATH = _BACKEND_ROOT / "data" / "acnr" / "global_catalog.json"
_catalog_data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
_ALL_CELLS: list[dict] = _catalog_data["cells"]

# 筛选可用于多语法收敛测试的条目:
# - 有 cell_address (非 semantic_only)
# - 有 formula_ref
# - 有 uri
# - domain 为 wp
_CONVERGENCE_CELLS_RAW = [
    c for c in _ALL_CELLS
    if c.get("cell_address")
    and c.get("formula_ref")
    and c.get("uri")
    and c.get("domain") == "wp"
    and not c.get("semantic_only")
]

# 从 sheets 构建索引（供 index_ref 构造和 formula_ref 可解析性预检）
_SHEETS: list[dict] = _catalog_data["sheets"]
_SHEET_BY_ADDR_ID: dict[str, dict] = {s["addr_id"]: s for s in _SHEETS}

# 构建 (parent_wp_code, sheet_name) → sheet 和 sheet_code 包含关系映射
# 用于预检 formula_ref 是否可解析
_SHEET_BY_PARENT_NAME: dict[tuple[str, str], dict] = {}
_SHEET_BY_PARENT_CODE: dict[tuple[str, str], dict] = {}
for _s in _SHEETS:
    _parent = _s.get("parent_wp_code", "")
    _name = _s.get("sheet_name", "")
    _code = _s.get("sheet_code", "")
    if _parent and _name:
        _SHEET_BY_PARENT_NAME[(_parent, _name)] = _s
    if _parent and _code:
        _SHEET_BY_PARENT_CODE[(_parent, _code)] = _s

import re as _re

_RE_WP_FORMULA = _re.compile(
    r"^(?:WP|PREV)\(\s*'([^']+)'\s*,\s*'([^']+)'\s*(?:,\s*'([^']+)')?\s*\)$"
)


def _formula_ref_is_resolvable(cell: dict) -> bool:
    """预检 formula_ref 是否能通过 catalog 解析（sheet_name 可匹配）。

    避免选取 formula_ref 中的 sheet_name 与 catalog 脱节的条目。
    """
    formula_ref = cell.get("formula_ref", "")
    m = _RE_WP_FORMULA.match(formula_ref)
    if not m:
        return False
    parent = m.group(1)
    sheet_name_in_formula = m.group(2)

    # 1. 精确匹配 sheet_name
    if (_parent_key := (parent, sheet_name_in_formula)) in _SHEET_BY_PARENT_NAME:
        return True
    # 2. 精确匹配 sheet_code
    if (parent, sheet_name_in_formula) in _SHEET_BY_PARENT_CODE:
        return True
    # 3. sheet_code 包含在 sheet_name_in_formula 中（最长匹配）
    best_len = 0
    for s in _SHEETS:
        if s.get("parent_wp_code") == parent:
            code = s.get("sheet_code", "")
            if code and code in sheet_name_in_formula and len(code) > best_len:
                best_len = len(code)
    if best_len > 0:
        return True
    # 4. 别名匹配
    for s in _SHEETS:
        if s.get("parent_wp_code") == parent:
            aliases = s.get("sheet_name_aliases", [])
            if sheet_name_in_formula in aliases:
                return True
    return False


def _uri_is_resolvable(cell: dict) -> bool:
    """预检 uri 是否能通过 catalog 解析。"""
    uri = cell.get("uri", "")
    if not uri.startswith("wp://"):
        return False
    body = uri[5:]
    if "#" not in body:
        return False
    path_part, _cell = body.rsplit("#", 1)
    parts = path_part.split("/")
    if len(parts) != 2:
        return False
    parent, sheet_name = parts
    # 同 formula_ref 的匹配逻辑
    if (parent, sheet_name) in _SHEET_BY_PARENT_NAME:
        return True
    if (parent, sheet_name) in _SHEET_BY_PARENT_CODE:
        return True
    best_len = 0
    for s in _SHEETS:
        if s.get("parent_wp_code") == parent:
            code = s.get("sheet_code", "")
            if code and code in sheet_name and len(code) > best_len:
                best_len = len(code)
    if best_len > 0:
        return True
    for s in _SHEETS:
        if s.get("parent_wp_code") == parent:
            aliases = s.get("sheet_name_aliases", [])
            if sheet_name in aliases:
                return True
    return False


def _build_index_ref(cell: dict) -> str | None:
    """从 CellCatalogEntry 构造 index_ref 语法 cell:{sheet_code}!{cell_address}。

    例: cell:D2-2!E100
    """
    parent_addr_id = cell.get("parent_addr_id", "")
    sheet_entry = _SHEET_BY_ADDR_ID.get(parent_addr_id)
    if not sheet_entry:
        return None
    sheet_code = sheet_entry.get("sheet_code", "")
    cell_address = cell.get("cell_address", "")
    if not sheet_code or not cell_address:
        return None
    return f"cell:{sheet_code}!{cell_address}"


def _index_ref_is_resolvable(cell: dict) -> bool:
    """预检 index_ref 是否可解析（sheet_code 在 catalog 中唯一存在）。"""
    parent_addr_id = cell.get("parent_addr_id", "")
    sheet_entry = _SHEET_BY_ADDR_ID.get(parent_addr_id)
    if not sheet_entry:
        return False
    sheet_code = sheet_entry.get("sheet_code", "")
    if not sheet_code:
        return False
    # sheet_code 必须唯一映射（否则 index_ref 解析会失败/ambiguous）
    code_matches = [s for s in _SHEETS if s.get("sheet_code") == sheet_code]
    return len(code_matches) == 1


# 综合过滤: 四种语法均可解析的条目
_CELLS_WITH_INDEX_REF = [
    c for c in _CONVERGENCE_CELLS_RAW
    if _build_index_ref(c) is not None
    and _formula_ref_is_resolvable(c)
    and _uri_is_resolvable(c)
    and _index_ref_is_resolvable(c)
]


# ---------------------------------------------------------------------------
# TB 域测试数据 — 用固定科目构造对比
# ---------------------------------------------------------------------------

# TB 域科目码列表（常见）
_TB_CODES = ["1001", "1002", "1122", "1221", "1501", "1601", "1701", "2202", "4001", "5001"]


# ---------------------------------------------------------------------------
# Helper: 运行 async full_resolve
# ---------------------------------------------------------------------------


def _run_resolve(**kwargs):
    """同步包装 async full_resolve。"""
    from app.services.acnr.resolver import full_resolve
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(full_resolve(**kwargs))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Property Test: 多语法一致性解析（wp 域 CellCatalogEntry）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    len(_CELLS_WITH_INDEX_REF) == 0,
    reason="No convergence-testable cell entries in catalog",
)
class TestMultiSyntaxConvergence:
    """Property 4: 对同一 CellCatalogEntry，四种语法收敛到同一 canonical addr_id。"""

    @given(cell=sampled_from(_CELLS_WITH_INDEX_REF))
    @settings(max_examples=10)
    def test_four_syntax_converge_to_same_addr_id(self, cell: dict):
        """四种语法（addr_id / formula_ref / uri / index_ref）均收敛到同一 canonical addr_id。

        R5.1: resolve() 接受四种语法
        R5.3: 命中返回 found=True + addr_id
        R11.3: cell:sheet_code!cell → addr_id
        R22.3, R22.5: 消费者无需区分来源
        """
        expected_addr_id = cell["addr_id"]
        formula_ref = cell["formula_ref"]
        uri = cell["uri"]
        index_ref = _build_index_ref(cell)

        # 1. resolve by addr_id directly
        r1 = _run_resolve(addr_id=expected_addr_id)
        assert r1.found, f"addr_id resolve 未命中: {expected_addr_id}"
        assert r1.addr_id == expected_addr_id, (
            f"addr_id 直接解析不收敛: expected={expected_addr_id}, got={r1.addr_id}"
        )

        # 2. resolve by formula_ref
        r2 = _run_resolve(formula_ref=formula_ref)
        assert r2.found, f"formula_ref resolve 未命中: {formula_ref}"
        assert r2.addr_id == expected_addr_id, (
            f"formula_ref 解析不收敛: expected={expected_addr_id}, "
            f"got={r2.addr_id}, formula_ref={formula_ref}"
        )

        # 3. resolve by uri
        r3 = _run_resolve(uri=uri)
        assert r3.found, f"uri resolve 未命中: {uri}"
        assert r3.addr_id == expected_addr_id, (
            f"uri 解析不收敛: expected={expected_addr_id}, got={r3.addr_id}, uri={uri}"
        )

        # 4. resolve by index_ref
        assert index_ref is not None
        r4 = _run_resolve(index_ref=index_ref)
        assert r4.found, f"index_ref resolve 未命中: {index_ref}"
        assert r4.addr_id == expected_addr_id, (
            f"index_ref 解析不收敛: expected={expected_addr_id}, "
            f"got={r4.addr_id}, index_ref={index_ref}"
        )

    @given(cell=sampled_from(_CELLS_WITH_INDEX_REF))
    @settings(max_examples=10)
    def test_all_four_syntax_return_same_entry_type(self, cell: dict):
        """四种语法解析结果的 entry_type 一致（均为 "cell"）。

        R5.3: 命中返回 entry_type
        """
        expected_addr_id = cell["addr_id"]
        formula_ref = cell["formula_ref"]
        uri = cell["uri"]
        index_ref = _build_index_ref(cell)

        r1 = _run_resolve(addr_id=expected_addr_id)
        r2 = _run_resolve(formula_ref=formula_ref)
        r3 = _run_resolve(uri=uri)
        r4 = _run_resolve(index_ref=index_ref)

        # 所有结果应 found=True 且 entry_type 一致
        results = [r1, r2, r3, r4]
        for r in results:
            assert r.found
        entry_types = {r.entry_type for r in results}
        assert len(entry_types) == 1, (
            f"entry_type 不一致: {[r.entry_type for r in results]}"
        )


# ---------------------------------------------------------------------------
# Property Test: TB 域委托一致性（R5.7, R11.2）
# ---------------------------------------------------------------------------


class TestTbDomainConvergence:
    """TB 域: index TB:xxxx 和 formula TB('xxxx','审定数') 解析到同一目标。"""

    @given(code=sampled_from(_TB_CODES))
    @settings(max_examples=10)
    def test_tb_index_and_formula_converge(self, code: str):
        """R11.2: TB:xxxx 与 TB('xxxx','审定数') 解析到同一目标。

        R5.7: 非 wp 域经同一 resolve() 出口委托 V1
        R22.3, R22.5: 消费者无需区分数据来源，返回统一格式
        """
        index_ref = f"TB:{code}"
        formula_ref = f"TB('{code}','审定数')"

        r_index = _run_resolve(index_ref=index_ref)
        r_formula = _run_resolve(formula_ref=formula_ref)

        # 两者都应该被识别为 TB 域并委托 V1（R5.7）
        # 即使 V1 实际数据不存在，两种语法应返回相同结构
        assert r_index.source_layer == "V1", (
            f"TB index_ref 未委托 V1: source_layer={r_index.source_layer}"
        )
        assert r_formula.source_layer == "V1", (
            f"TB formula_ref 未委托 V1: source_layer={r_formula.source_layer}"
        )

        # 若均命中，addr_id 应一致（收敛同一目标）
        if r_index.found and r_formula.found:
            assert r_index.addr_id == r_formula.addr_id, (
                f"TB 域收敛失败: index={r_index.addr_id}, formula={r_formula.addr_id}"
            )
            # URI 也应一致
            assert r_index.uri == r_formula.uri, (
                f"TB 域 URI 不一致: index={r_index.uri}, formula={r_formula.uri}"
            )
        elif r_index.found != r_formula.found:
            # 一个命中一个未命中 → 收敛失败
            pytest.fail(
                f"TB 域命中状态不一致: "
                f"index.found={r_index.found}, formula.found={r_formula.found}, "
                f"code={code}"
            )
