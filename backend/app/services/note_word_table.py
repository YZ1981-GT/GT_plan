"""附注 Word 表格解析与种子表格比对（只读）。

spec: disclosure-note-template-word-realignment Task 1（design §2.1 / §2.4）

从 ``note_word_tree`` 拆出（行数门 800）：OOXML 合并单元格网格、表头行数、逻辑列、每列表头路径与行标签，
以及种子表 ↔ Word 表的逐张比对。``compare_tables`` 返回 ``(kind, key, detail)``，由 ``note_word_tree`` 包成 ``Diff``。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

__all__ = [
    "WordTable",
    "compare_tables",
    "iter_blocks",
    "norm_cell",
    "parse_word_table",
    "seed_header_paths",
    "seed_multi_header",
    "word_header_paths",
]

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(tag: str) -> str:
    return f"{{{_W}}}{tag}"


def iter_blocks(container: Any) -> Iterator[tuple[str, Any]]:
    """按文档顺序产出 ("p"|"tbl", 元素)；内容控件 ``w:sdt`` 下钻其 ``w:sdtContent``（平台导出的交付件每节都包在内容控件里）。"""
    for el in container.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""
        if tag in ("p", "tbl"):
            yield tag, el
        elif tag == "sdt":
            content = el.find(_q("sdtContent"))
            if content is not None:
                yield from iter_blocks(content)


@dataclass
class WordTable:
    caption: str  # 表前最近的非空段落（可能是节内小标题）
    columns: int
    header_rows: int
    leaf_headers: list[str]
    groups: list[str | None]  # 每列直接上级表头；单层表头为 None
    row_labels: list[str]  # 数据行首列非空文字
    header_paths: list[list[str]] = field(default_factory=list)  # 每列自上而下的非空表头文字
    #: 数据行按逻辑列取文字：[首列, 第 1 列, …]；单元格从本行本列起才取（横向 / 纵向合并的延续格为空串）
    rows: list[list[str]] = field(default_factory=list)


_WS = re.compile(r"\s+")


_CELL_TRANS = str.maketrans({"(": "（", ")": "）", ":": "："})


def norm_cell(text: str | None) -> str:
    """表头 / 行标签 / 表名比对键：去全部空白，括号与冒号统一为全角。"""
    return _WS.sub("", (text or "")).translate(_CELL_TRANS)


def _para_text(p_el: Any) -> str:
    return "".join(t.text or "" for t in p_el.iter(_q("t"))).strip()


def _table_grid(tbl_el: Any) -> tuple[int, int, dict, dict, dict]:
    """返回 (行数, 列数, grid[(r,c)]=owner, texts[owner], spans[owner]=(rowspan, colspan))。"""
    grid: dict[tuple[int, int], tuple[int, int]] = {}
    texts: dict[tuple[int, int], str] = {}
    spans: dict[tuple[int, int], tuple[int, int]] = {}
    open_v: dict[int, tuple[int, int]] = {}
    rows = tbl_el.findall(_q("tr"))
    ncols = 0
    for r, tr in enumerate(rows):
        c = 0
        trpr = tr.find(_q("trPr"))
        before = trpr.find(_q("gridBefore")) if trpr is not None else None
        if before is not None:
            c = int(before.get(_q("val"), "0") or 0)
        for tc in tr.findall(_q("tc")):
            tcpr = tc.find(_q("tcPr"))
            cs, vm = 1, None
            if tcpr is not None:
                gs = tcpr.find(_q("gridSpan"))
                if gs is not None:
                    cs = max(1, int(gs.get(_q("val"), "1") or 1))
                v = tcpr.find(_q("vMerge"))
                if v is not None:
                    vm = v.get(_q("val"), "continue")
            if vm == "continue" and c in open_v:
                owner = open_v[c]
                rs, ocs = spans[owner]
                spans[owner] = (rs + 1, ocs)
            else:
                owner = (r, c)
                texts[owner] = "\n".join(_para_text(p) for p in tc.findall(_q("p"))).strip()
                spans[owner] = (1, cs)
                for k in range(cs):
                    if vm == "restart":
                        open_v[c + k] = owner
                    else:
                        open_v.pop(c + k, None)
            for k in range(cs):
                grid[(r, c + k)] = owner
            c += cs
        ncols = max(ncols, c)
    return len(rows), ncols, grid, texts, spans


def _header_row_count(nrows: int, ncols: int, grid: dict, texts: dict, spans: dict) -> int:
    """表头行数。

    基于 ``sync_note_templates_from_word.detect_header_row_count``，多一条：横向合并的单元格（分组表头）
    之下必有一行子表头。原规则只看纵向延伸，首列未纵向合并的两级表头（「账龄」列下格留白）会被判成一行。
    之后照原规则从第 2 行起找「首列有字、无合并、不被上方覆盖」的行截断（数据行）。

    合并格只认有字的（R6.3）：空白的合并格既不撑开表头，也不让所在行免于截断 —— 数据行里两格一并的空白取数格
    （上市 五、9 存货组合 / 五、10 合同资产 / 五、11 持有待售 / 五、62 收入分解、国企 八、64 等表）原先让数据行算进
    表头。本行起始的格全空白（空白占位行）、首格从首列通栏（「商品价格风险」分类行）的行也是数据行。
    """
    max_covered = 0
    for (r0, c0), (rs, cs) in spans.items():
        if r0 < min(nrows, 5) and (rs > 1 or cs > 1) and texts.get((r0, c0)):
            max_covered = max(max_covered, r0 + rs - 1 + (1 if cs > 1 else 0))
    if max_covered == 0:
        return 1
    header_rows = max_covered + 1
    for r in range(1, header_rows):
        starts = {grid[(r, c)] for c in range(ncols) if (r, c) in grid and grid[(r, c)][0] == r}
        if starts and (not any(texts.get(o) for o in starts)
                       or any(o[1] == 0 and spans[o][1] >= ncols for o in starts)):
            header_rows = r
            break
        owner0 = grid.get((r, 0))
        if owner0 != (r, 0) or not texts.get(owner0):
            continue
        if any(texts.get(o) and (spans[o][0] > 1 or spans[o][1] > 1) for o in starts):
            continue
        if not any((r, c) in grid and grid[(r, c)][0] < r for c in range(ncols)):
            header_rows = r
            break
    return min(max(header_rows, 1), 4)


def _logical_columns(ncols: int, n_hdr: int, grid: dict) -> list[int]:
    """表头定义的逻辑列：相邻网格列在全部表头行属于同一单元格 ⇒ 并为一列（Word 手工拆格常多出网格列）。

    返回每个逻辑列的首个网格列下标。
    """
    starts: list[int] = []
    previous: tuple | None = None
    for c in range(ncols):
        owners = tuple(grid.get((r, c)) for r in range(n_hdr))
        if c == 0 or owners != previous:
            starts.append(c)
        previous = owners
    return starts


def _absorb(grid: dict, texts: dict, spans: dict, gap: tuple[int, int], into: tuple[int, int]) -> None:
    """空白格 ``gap`` 并进同一行相邻的单元格 ``into``（新单元格起点取左边，横向多占一列）。"""
    r = gap[0]
    owner, (rs, cs), text = (r, min(gap[1], into[1])), spans.pop(into), texts.pop(into)
    texts.pop(gap, None)
    spans.pop(gap, None)
    for key, value in list(grid.items()):
        if value in (gap, into):
            grid[key] = owner
    texts[owner], spans[owner] = text, (rs, cs + 1)


def _normalize_header_gaps(ncols: int, n_hdr: int, grid: dict, texts: dict, spans: dict) -> tuple[dict, dict, dict]:
    """Word 模板表头里没合并的空白单元格归一（种子格式 / 列路径都表达不了「留白的上级」，R6.3）：

    1. 下一行的子表头从它跨进相邻的分组表头（子表头只能挂在一个上级下）⇒ 并入那个分组；
    2. 正下方是一个列名：左邻是分组表头、右邻不是 ⇒ 列名属于左邻分组（并入左邻，如「本期变动情况」下的「其他变动」）；
       否则 ⇒ 列名是独立的一列（如「减值准备期初余额」），提到这一格（纵向合并）。左右都是分组时分不出，按独立列。

    四版 Word 里第 1 类只有上市存货按组合计提跌价准备四张表；全部出现处见
    ``tests/test_consol_note_seed_header_repair.py::TestWordHeaderRules``。返回新的三张表。
    """
    grid, texts, spans = dict(grid), dict(texts), dict(spans)

    def is_group(cell: tuple[int, int] | None, r: int) -> bool:
        if cell is None or cell[0] != r or spans[cell][1] < 2 or r + 1 >= n_hdr or not texts.get(cell):
            return False
        kids = {grid.get((r + 1, cc)) for cc in range(cell[1], cell[1] + spans[cell][1])}
        return len({k for k in kids if k is not None and k[0] == r + 1}) >= 2

    for r in range(max(n_hdr - 1, 0)):
        for c in range(ncols):
            gap, below = grid.get((r, c)), grid.get((r + 1, c))
            if gap != (r, c) or texts.get(gap) or spans.get(gap) != (1, 1) or below is None or below[0] != r + 1:
                continue
            straddled = next((
                other for nb, other in ((nb, grid.get((r, nb))) for nb in (c + 1, c - 1) if 0 <= nb < ncols)
                if other and other != gap and other[0] == r and spans[other][0] == 1 and texts.get(other)
                and grid.get((r + 1, nb)) == below
            ), None)
            if straddled is not None:
                _absorb(grid, texts, spans, gap, straddled)
                continue
            if not texts.get(below) or spans[below][1] != 1 or below[0] + spans[below][0] != n_hdr:
                continue  # 正下方不是一直到表头末行的单个列名
            left = grid.get((r, c - 1)) if c else None
            right = grid.get((r, c + 1)) if c + 1 < ncols else None
            # 左邻须与空白格同一个上级（上市 九、1:2 第 1 行：左邻「以摊余成本计量」属「期末余额」，空白格属「上年年末余额」）
            same_parent = r == 0 or (left is not None and grid.get((r - 1, left[1])) == grid.get((r - 1, c)))
            if same_parent and is_group(left, r) and not is_group(right, r):
                _absorb(grid, texts, spans, gap, left)
                continue
            texts[gap], spans[gap] = texts.pop(below), (n_hdr - r, 1)
            spans.pop(below, None)
            for rr in range(r, n_hdr):
                grid[(rr, c)] = gap
    return grid, texts, spans


def seed_multi_header(tbl_el: Any, cols: Sequence[int] | None = None) -> tuple[int, list[list[str]]]:
    """Word 表头 → 合并附注种子格式的多级表头：(表头行数, 每行每列文字)。按网格列（``cols`` 可指定种子各列对应的网格列）；
    单元格起点写字（去换行、去首尾空白）、合并延续格为空串。

    种子格式里空串 = 合并延续、表达不了留白：表头里没合并的空白格先按 ``_normalize_header_gaps`` 归一。
    """
    nrows, ncols, grid, texts, spans = _table_grid(tbl_el)
    n_hdr = min(_header_row_count(nrows, ncols, grid, texts, spans), nrows) if nrows else 0
    grid, texts, spans = _normalize_header_gaps(ncols, n_hdr, grid, texts, spans)
    cols = list(range(ncols)) if cols is None else list(cols)
    clean = lambda o: (texts.get(o) or "").replace("\n", "").strip()  # noqa: E731
    return n_hdr, [[clean((r, c)) if grid.get((r, c)) == (r, c) else "" for c in cols] for r in range(n_hdr)]


def parse_word_table(tbl_el: Any, caption: str) -> WordTable:
    nrows, ncols, grid, texts, spans = _table_grid(tbl_el)
    n_hdr = min(_header_row_count(nrows, ncols, grid, texts, spans), nrows) if nrows else 0
    grid, texts, spans = _normalize_header_gaps(ncols, n_hdr, grid, texts, spans)
    columns = _logical_columns(ncols, n_hdr, grid) if n_hdr else list(range(ncols))
    leaf: list[str] = []
    groups: list[str | None] = []
    paths: list[list[str]] = []
    for c in columns:
        path: list[str] = []
        seen: set[tuple[int, int]] = set()
        for r in range(n_hdr):
            owner = grid.get((r, c))
            if owner is None or owner in seen:
                continue
            seen.add(owner)
            if texts.get(owner):  # 空单元格（未纵向合并的留白）不算一级
                path.append(texts[owner])
        paths.append(path)
        leaf.append(path[-1] if path else "")
        groups.append(path[-2] if len(path) >= 2 else None)
    labels = []
    for r in range(n_hdr, nrows):
        owner = grid.get((r, 0))
        if owner is not None and owner[0] == r and texts.get(owner):
            labels.append(texts[owner])
    return WordTable(
        caption=caption, columns=len(columns), header_rows=n_hdr,
        leaf_headers=leaf, groups=groups, row_labels=labels, header_paths=paths,
        rows=[_data_row(r, columns, ncols, grid, texts) for r in range(n_hdr, nrows)],
    )


def _data_row(r: int, columns: Sequence[int], ncols: int, grid: dict, texts: dict) -> list[str]:
    """数据行按逻辑列取文字：逻辑列覆盖的网格列里，第一个从本行起始、有字的单元格（数据行常把一列拆成几格）。"""
    out: list[str] = []
    for i, start in enumerate(columns):
        end = columns[i + 1] if i + 1 < len(columns) else ncols
        text = ""
        for c in range(start, end):
            owner = grid.get((r, c))
            if owner == (r, c) and texts.get(owner):
                text = texts[owner].strip()
                break
        out.append(text)
    return out


def _clip(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _first_diff(a: list[str], b: list[str]) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"第 {i + 1} 项 种子「{x}」/ Word「{y}」"
    return f"种子 {len(a)} 项 / Word {len(b)} 项"


_PATH_SEP = re.compile(r"[-－/／]")


_TRAILING_DOT = re.compile(r"[.。．]+$")


#: 占位行：「……」「可无限量添加行」、纯序号（种子给名单类表预置 1~10 行，Word 是空行）
_PLACEHOLDER_ROW = re.compile(r"^[.…·．。\-—_]*$|添加行|^\d{1,3}$")


def _path_key(parts: list[str | None]) -> str:
    """多级表头列路径比对键：逐级去尾部句点后拼接，忽略「-」「/」分隔（种子把三级表头存成「中级-叶」）。"""
    return _PATH_SEP.sub("", "".join(_TRAILING_DOT.sub("", norm_cell(p)) for p in parts if p))


def seed_header_paths(table: dict[str, Any]) -> list[str]:
    """种子表每列的表头路径键：分组（``columns[].group`` 或 ``_column_groups``）+ 列名。"""
    headers = list(table.get("headers") or [])
    cols = [c for c in table.get("columns") or [] if isinstance(c, dict)]
    spans: dict[int, str] = {}
    for g in table.get("_column_groups") or []:
        if isinstance(g, dict) and isinstance(g.get("start"), int):
            for k in range(g["start"], g["start"] + int(g.get("span") or 1)):
                spans[k] = g.get("group") or ""
    out = []
    for i, header in enumerate(headers):
        col = cols[i] if len(cols) == len(headers) else {}
        group = col.get("group") or spans.get(i)
        out.append(_path_key([group, col.get("label") or header]))
    return out


def word_header_paths(table: WordTable) -> list[str]:
    return [_path_key(list(path)) for path in table.header_paths]


def _row_keys(labels: list[str | None]) -> list[str]:
    keys = [_TRAILING_DOT.sub("", norm_cell(x)).rstrip("：") for x in labels]
    return [k for k in keys if k and not _PLACEHOLDER_ROW.search(k)]


def compare_tables(key: str, seed_tables: list[dict], word_tables: list[WordTable]) -> list[tuple[str, str, str]]:
    """逐张比对（按表序）：表数、列数、每列表头路径（分组 + 列名）、行标签。

    - 不比表名：Word 表前段落多为编制指引或「续：」，不是表名（种子表名多为生成）。
    - 行标签忽略「……」「可无限量添加行」、纯序号类占位行。
    - 种子把部分宽表拆成「期末 / 续：期初」两张（``continuation_of_index``），Word 是一张：这类差异
      照实报出（表数 / 列数），不在比对里猜拆分语义——同一标记在种子里也用于「后续采用总额法 / 净额法」
      这类并列表，2026-10-16 试过按续表并组，误报反而从 96 / 20 升到 117 / 30。
    """
    out: list[tuple[str, str, str]] = []
    if len(seed_tables) != len(word_tables):
        out.append(("table_count", key, f"种子 {len(seed_tables)} 张 / Word {len(word_tables)} 张"))
    for i, (st, wt) in enumerate(zip(seed_tables, word_tables)):
        tkey = f"{key}#t{i}"
        s_paths, w_paths = seed_header_paths(st), word_header_paths(wt)
        if len(s_paths) != wt.columns:
            out.append(("table_columns", tkey, f"种子 {len(s_paths)} 列 / Word {wt.columns} 列：{_clip(wt.leaf_headers)}"))
        elif s_paths != w_paths:
            out.append(("table_headers", tkey, _first_diff(s_paths, w_paths)))
        s_rows = _row_keys([r.get("label") for r in st.get("rows") or [] if isinstance(r, dict)])
        w_rows = _row_keys(wt.row_labels)
        if s_rows != w_rows:
            out.append(("table_rows", tkey, _first_diff(s_rows, w_rows)))
    return out
