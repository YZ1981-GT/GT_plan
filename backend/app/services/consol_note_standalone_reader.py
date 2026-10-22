"""单体附注表格读取层 —— 合并附注明细映射（V186 链路）唯一的来源读取。

合并附注的个别数从各子企业的单体附注拉取（不从试算表取数）。读的必须是单体附注页面 /
Word 导出实际显示的那张表：

1. ``effective_table_data``：workpaper 来源先把 ``sub_table_data`` 投影成 ``_tables``
   （与编辑器、Word 导出、就绪判定同一口径），其余来源直接读 ``_tables``；
2. 选表：合并章节经 ``consol_note_section_mapping`` 映射到单体章节号与子表名。按表名匹配
   （去空白 / 去「（1）」类序号），映射没给表名时按合并表标题匹配；单体章节只有一张表时
   直接用它。多张表又没有依据时不猜，返回原因；
3. 认列：两侧表头都解析成列路径（多级表头逐级拼接，期末 / 期初同义词归一），按路径匹配；
   单体续表（「（续：期初数）」）提供期初列；比例 / 比率列不加总；匹配不唯一的列不填，
   列名回报给用户。

产出 V186 标准来源行 ``{label, row_type, values}``：``values[k]`` 对应合并模板第 ``k+1``
列（第 0 列是行名）。合计 / 小计行由 apply 按本表数据重算，不信任来源合计。

spec: consol-note-pull-from-standalone（收口到 consol-note-detail-template-and-mapping）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

__all__ = [
    "SourceTable",
    "consol_column_paths",
    "standalone_column_paths",
    "pick_standalone_table",
    "read_source_table",
]

_WS_RE = re.compile(r"[\s\u3000]+")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_PAREN = str.maketrans({"（": "(", "）": ")", "％": "%", "：": ":", "，": ","})
# 表名开头的序号：（1） (2) 1、 一、 1. 等；以及「其中，」「其中：」引导语
_ENUM_RE = re.compile(r"^(?:\([0-9一二三四五六七八九十]+\)|[0-9一二三四五六七八九十]+[、.．])")
_LEAD_RE = re.compile(r"^其中[:,]?")
# 比例 / 比率类列：跨企业加总没有意义，交给公式或手工
_RATIO_RE = re.compile(r"比例|比率|率\(|率$|%")

END_TOKEN = "§END"
PRIOR_TOKEN = "§PRIOR"

# 期末 / 本期同一位置；期初 / 上期同一位置（与 note_writer 列名词表同源）
_END_WORDS = frozenset({
    "期末余额", "期末数", "期末", "期末金额", "期末账面价值", "期末公允价值",
    "本期发生额", "本期金额", "本期数", "本期", "本年发生额", "本年金额", "本年数", "本年",
})
_PRIOR_WORDS = frozenset({
    "期初余额", "期初数", "期初", "期初金额", "期初账面价值", "期初公允价值",
    "年初余额", "年初数", "年初金额", "上年年末余额", "上年年末数", "上年年末",
    "上期发生额", "上期金额", "上期数", "上期", "上年发生额", "上年金额", "上年数", "上年",
})
# 同义的列分组名（单体模板与合并模板措辞不一）
_SEGMENT_ALIASES = {"账面金额": "账面余额"}


def _norm(text: Any) -> str:
    """去 HTML 换行与全部空白，全角括号 / 百分号 / 冒号归一为半角。"""
    return _WS_RE.sub("", _BR_RE.sub("", str(text or ""))).translate(_PAREN)


def _canon(segment: Any) -> str:
    s = _norm(segment)
    if s in _END_WORDS:
        return END_TOKEN
    if s in _PRIOR_WORDS:
        return PRIOR_TOKEN
    return _SEGMENT_ALIASES.get(s, s)


def _table_key(name: Any) -> str:
    """表名比较键：规范化后去掉开头序号与「其中，」引导语。"""
    return _LEAD_RE.sub("", _ENUM_RE.sub("", _norm(name)))


def _to_number(value: Any) -> float | int | None:
    """单元格 → 数值；空 / 非数值 → None（文本列、占位符 X.XX 都不参与加总）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if value == value else None  # NaN
    if isinstance(value, dict):  # 带元数据的单元格
        return _to_number(value.get("value", value.get("manual_value")))
    s = str(value).strip().replace(",", "").replace("，", "")
    if not s or s in ("-", "—", "－"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ─── 列路径 ──────────────────────────────────────────────────────────────────


def _group_at(groups: Any, col: int) -> str:
    if not isinstance(groups, list):
        return ""
    for g in groups:
        if not isinstance(g, dict):
            continue
        try:
            start, span = int(g.get("start", 0)), int(g.get("span", 1))
        except (TypeError, ValueError):
            continue
        if start <= col < start + span:
            return str(g.get("group") or "")
    return ""


def _multi_header_raw_paths(multi_header: list) -> list[list[str]]:
    """多级表头逐列拼路径（第 0 列是行名，不参与）。

    上层空格沿用左侧（横向合并）；下层空格只在与左侧同一父级时沿用左侧，父级不同视为
    纵向合并（该列在这一层没有名字）。
    """
    layers = [list(r) for r in multi_header if isinstance(r, (list, tuple))]
    width = max((len(r) for r in layers), default=0)
    paths: list[list[str]] = [[] for _ in range(width)]
    for depth, layer in enumerate(layers):
        before = [tuple(p) for p in paths]
        carried = ""
        for ci in range(1, width):
            raw = layer[ci] if ci < len(layer) else ""
            cell = str(raw) if raw is not None and _norm(raw) else ""
            if not cell:
                if depth == 0 or (ci >= 2 and before[ci] == before[ci - 1]):
                    cell = carried
            carried = cell
            if cell:
                paths[ci].append(cell)
    return paths


def _raw_column_paths(table: dict) -> list[list[str]]:
    """每列的原始表头路径（第 0 列为空）。多级表头优先：部分模板的 ``headers`` 与之错位。"""
    headers = list(table.get("headers") or [])
    mh = table.get("multi_header")
    if isinstance(mh, list) and len(mh) >= 2:
        raw = _multi_header_raw_paths(mh)
        width = max(len(headers), len(raw))
        return [[]] + [raw[ci] if ci < len(raw) else [] for ci in range(1, width)]
    groups = table.get("_column_groups")
    out: list[list[str]] = [[]]
    for ci in range(1, len(headers)):
        h = str(headers[ci] or "")
        segs = [s for s in h.split("/") if _norm(s)] if "/" in h else ([h] if _norm(h) else [])
        group = _group_at(groups, ci)
        if group and "/" not in h and (not segs or _norm(group) != _norm(segs[0])):
            segs = [group] + segs
        out.append(segs)
    return out


def column_paths(table: dict) -> list[tuple[str, ...]]:
    """每列的规范化路径（期末 / 期初同义词归一为位置记号）；第 0 列为空元组。"""
    return [tuple(_canon(s) for s in segs) for segs in _raw_column_paths(table)]


# 两侧共用同一解析（单体 ``_tables`` 用 headers + _column_groups，合并模板多为 multi_header）
consol_column_paths = column_paths
standalone_column_paths = column_paths


def _column_label(table: dict, col: int) -> str:
    raw = _raw_column_paths(table)
    return "/".join(_norm(s) for s in raw[col]) if col < len(raw) else f"第{col}列"


def _has_period(path: tuple[str, ...]) -> bool:
    return any(seg in (END_TOKEN, PRIOR_TOKEN) for seg in path)


def _rule_exact(target: tuple, source: tuple, ctx: str | None) -> bool:
    return source == target


def _rule_period_context(target: tuple, source: tuple, ctx: str | None) -> bool:
    """单体表本身只含一个期间（表名「（期末数）」/ 续表「（续：期初数）」）时补上期间层。"""
    return bool(ctx) and bool(source) and not _has_period(source) and (ctx,) + source == target


def _rule_suffix(target: tuple, source: tuple, ctx: str | None) -> bool:
    """单体表省略了非期间的分组层（如合并「账面余额/金额」↔ 单体「金额」）。"""
    n = len(source)
    return 0 < n < len(target) and target[-n:] == source and not _has_period(target[:-n])


def _rule_prefix(target: tuple, source: tuple, ctx: str | None) -> bool:
    """合并表多一层非期间的说明（如「第一阶段/未来12个月预期信用损失」↔ 单体「第一阶段」）。"""
    n = len(source)
    return 0 < n < len(target) and target[:n] == source and not _has_period(target[n:])


# 强 → 弱；弱规则只在强规则零命中时才试，且同一单体列被多列认领即全部放弃
_RULES = (_rule_exact, _rule_period_context, _rule_suffix, _rule_prefix)


def _match_columns(
    target_paths: list[tuple[str, ...]],
    candidates: list[tuple[list[tuple[str, ...]], str | None]],
) -> tuple[dict[int, tuple[int, int]], list[int], list[int]]:
    """合并模板列 → (候选表序号, 单体列号)。

    逐条规则找候选，第一条有命中的规则若命中不唯一即放弃（弱规则不得推翻强规则的歧义）；
    同一单体列被多列认领也放弃。返回 (列映射, 未匹配列, 比率列)。
    """
    claims: dict[int, tuple[int, int]] = {}
    ratio: list[int] = []
    for c in range(1, len(target_paths)):
        path = target_paths[c]
        if not path:
            continue
        if _RATIO_RE.search(path[-1]):
            ratio.append(c)
            continue
        for rule in _RULES:
            hits = [
                (pos, s)
                for pos, (paths, ctx) in enumerate(candidates)
                for s in range(1, len(paths))
                if rule(path, paths[s], ctx)
            ]
            if hits:
                if len(hits) == 1:
                    claims[c] = hits[0]
                break
    owners: dict[tuple[int, int], int] = {}
    for hit in claims.values():
        owners[hit] = owners.get(hit, 0) + 1
    col_map = {c: hit for c, hit in claims.items() if owners[hit] == 1}
    unmatched = [c for c in range(1, len(target_paths)) if c not in col_map and c not in ratio]
    return col_map, unmatched, ratio


# ─── 选表 ────────────────────────────────────────────────────────────────────

_PERIOD_SUFFIX_RE = re.compile(r"\((?:续[^()]*|期末[^()]*|期初[^()]*)\)$")


def _base_key(name: Any) -> str:
    """去掉表名末尾的「（期末数）」「（续：期初数）」，用于把续表认回主表。"""
    return _PERIOD_SUFFIX_RE.sub("", _table_key(name))


def _is_continuation(name: Any) -> bool:
    return "续" in _table_key(name)


def _table_period(name: Any) -> str | None:
    key = _table_key(name)
    if "期初" in key or "上年" in key:
        return PRIOR_TOKEN
    if "期末" in key:
        return END_TOKEN
    return None


_FUZZY_TABLE_RATIO = 0.9


def _match_table_name(cands: list[tuple[int, dict]], want: str) -> tuple[list[int], str]:
    """按表名找候选表，返回 (命中序号, 命中方式)。逐级：规范化相等 → 去期间后缀相等 → 高相似度。

    后两级只在续表 / 非续表同类之间比（「（续：期初数）」不冒充主表）。不做包含匹配：
    「货币资金」包含于「受限制的货币资金明细」，包含匹配会取错表。
    """
    key = _table_key(want)
    exact = [i for i, t in cands if _table_key(t.get("name")) == key]
    if exact:
        return exact, "exact"
    same_kind = [(i, t) for i, t in cands if _is_continuation(t.get("name")) == _is_continuation(want)]
    base = _base_key(want)
    by_base = [i for i, t in same_kind if base and _base_key(t.get("name")) == base]
    if by_base:
        return by_base, "base"
    scored = sorted(
        ((SequenceMatcher(None, key, _table_key(t.get("name"))).ratio(), i) for i, t in same_kind),
        reverse=True,
    )
    if scored and scored[0][0] >= _FUZZY_TABLE_RATIO and (len(scored) == 1 or scored[1][0] < _FUZZY_TABLE_RATIO):
        return [scored[0][1]], "fuzzy"
    return [], ""


def pick_standalone_table(
    tables: list[Any],
    *,
    table_name: str | None = None,
    title: str | None = None,
    section_title: str | None = None,
) -> tuple[int | None, str | None]:
    """在单体章节的表格里找合并章节对应的那一张。返回 (序号, None) 或 (None, 中文原因)。

    依据依次是映射给出的子表名、合并表标题（见 ``_match_table_name``）。都对不上时：
    映射没给表名且单体章节只有一张表 → 用它；单体章节只有一张**无名**表（旧单表格式）且
    要的就是该章节主表（子表名 = 单体章节标题）→ 用它。多张表又没有依据时不猜。
    列能否对上由 ``_match_columns`` 再把一道关：表名对上但列对不上的不会填数。
    """
    cands = [(i, t) for i, t in enumerate(tables) if isinstance(t, dict)]
    if not cands:
        return None, "单体附注该章节没有表格"
    for want in (table_name, title):
        if not _table_key(want):
            continue
        hits, _how = _match_table_name(cands, str(want))
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, f"单体附注有多张同名表「{want}」，无法确定取哪一张"
    if len(cands) == 1:
        only = cands[0][1]
        if not table_name:
            return cands[0][0], None
        if not _norm(only.get("name")) and section_title and _table_key(table_name) == _table_key(section_title):
            return cands[0][0], None
    want = table_name or title or ""
    return None, f"单体附注该章节有 {len(cands)} 张表，没有与「{want}」对应的表"


# ─── 读取 ────────────────────────────────────────────────────────────────────


@dataclass
class SourceTable:
    """一家企业一个合并章节的来源读取结果。"""

    rows: list[dict[str, Any]] = field(default_factory=list)
    table_name: str | None = None
    matched_columns: list[int] = field(default_factory=list)
    unmatched_columns: list[str] = field(default_factory=list)
    ratio_columns: list[str] = field(default_factory=list)
    reason: str | None = None  # 没读到来源行时的中文原因
    # missing（未生成）/ not_applicable（本期无此情形）/ no_source（合并特有章节）/
    # unreadable（有附注但读不出表）；空 = 按 rows 推断
    status: str = ""

    def to_status(self) -> dict[str, Any]:
        return {
            "status": self.status or ("found" if self.rows else "unreadable"),
            "reason": self.reason,
            "table_name": self.table_name,
            "row_count": len(self.rows),
            "unmatched_columns": self.unmatched_columns,
            "ratio_columns": self.ratio_columns,
        }


_SKIP_ROW_TYPES = frozenset({"expandable", "dynamic_anchor", "dynamic_marker_end"})


def _row_label(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("label") or "").strip()
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "").strip()
    return ""


def _row_values(row: Any) -> list[Any]:
    if isinstance(row, dict):
        vals = row.get("values")
        return list(vals) if isinstance(vals, (list, tuple)) else []
    if isinstance(row, (list, tuple)):
        return list(row[1:])
    return []


def _source_row_type(row: Any, label: str) -> str | None:
    """合计 / 小计 / 数据；可扩位等占位行返回 None（不进来源行）。"""
    if isinstance(row, dict):
        rt = str(row.get("row_type") or "").strip()
        if rt in _SKIP_ROW_TYPES:
            return None
        if rt in ("total", "subtotal"):
            return rt
        if row.get("is_total") is True:
            return "total"
    key = _norm(label).rstrip(":")
    if key in ("合计", "总计"):
        return "total"
    if key.endswith("小计"):
        return "subtotal"
    return "data"


def _tables_of(table_data: Any) -> list[Any]:
    """用户在单体附注里看到的表格（workpaper 来源先投影 sub_table_data）。"""
    from app.services.note_content_utils import effective_table_data

    etd = effective_table_data(table_data) if isinstance(table_data, dict) else None
    if not isinstance(etd, dict) or not etd:
        return []
    tables = etd.get("_tables")
    if isinstance(tables, list) and tables:
        return tables
    if isinstance(etd.get("rows"), list) and etd["rows"]:  # 无 _tables 的旧单表格式
        return [{
            "name": etd.get("name"),
            "headers": etd.get("headers") or [],
            "rows": etd["rows"],
            "_column_groups": etd.get("_column_groups"),
        }]
    return []


def read_source_table(
    table_data: Any,
    *,
    consol_table: dict | None,
    table_name: str | None = None,
    title: str | None = None,
    section_title: str | None = None,
) -> SourceTable:
    """读一家企业单体附注章节里与合并章节对应的表，按合并模板列对齐成标准来源行。

    ``consol_table`` 为合并附注模板表（``find_table``）；缺失时按单体表自身列输出。
    ``section_title`` 为单体章节标题（旧单表格式的表没有名字时用来确认是主表）。
    """
    tables = _tables_of(table_data)
    if not tables:
        return SourceTable(reason="单体附注该章节没有表格数据")
    idx, why = pick_standalone_table(
        tables, table_name=table_name, title=title, section_title=section_title,
    )
    if idx is None:
        return SourceTable(reason=why)
    primary = tables[idx]

    base = _base_key(primary.get("name"))
    continuations = [
        i for i, t in enumerate(tables)
        if i != idx and isinstance(t, dict) and _is_continuation(t.get("name"))
        and _base_key(t.get("name")) == base
    ]
    primary_ctx = _table_period(primary.get("name"))
    if primary_ctx is None and continuations and not _is_continuation(primary.get("name")):
        primary_ctx = END_TOKEN  # 有「续：期初」续表的主表承载期末
    candidate_tables = [primary] + [tables[i] for i in continuations]
    candidates = [(column_paths(primary), primary_ctx)] + [
        (column_paths(tables[i]), _table_period(tables[i].get("name"))) for i in continuations
    ]

    target = consol_table if isinstance(consol_table, dict) and consol_table.get("headers") else primary
    target_paths = column_paths(target)
    # 合并表只有一个期间（如「期末数/账面余额…」整表都是期末）而单体表表头不带期间：单体表就是该期间
    top_periods = {p[0] for p in target_paths[1:] if p and p[0] in (END_TOKEN, PRIOR_TOKEN)}
    if (
        candidates[0][1] is None and len(top_periods) == 1
        and not any(_has_period(p) for p in candidates[0][0][1:])
    ):
        candidates[0] = (candidates[0][0], next(iter(top_periods)))
    col_map, unmatched, ratio = _match_columns(target_paths, candidates)

    # 续表按「行名 + 同名序号」与主表对行
    cont_rows: list[dict[tuple[str, int], Any]] = [{}]
    for t in candidate_tables[1:]:
        index: dict[tuple[str, int], Any] = {}
        seen: dict[str, int] = {}
        for r in t.get("rows") or []:
            key = _norm(_row_label(r))
            if not key:
                continue
            index[(key, seen.get(key, 0))] = r
            seen[key] = seen.get(key, 0) + 1
        cont_rows.append(index)

    out: list[dict[str, Any]] = []
    seen_labels: dict[str, int] = {}
    for r in primary.get("rows") or []:
        label = _row_label(r)
        key = _norm(label)
        if not key:
            continue
        rt = _source_row_type(r, label)
        if rt is None:
            continue
        occurrence = (key, seen_labels.get(key, 0))
        seen_labels[key] = occurrence[1] + 1
        values: list[float | int | None] = [None] * max(len(target_paths) - 1, 0)
        for c, (pos, s) in col_map.items():
            src = r if pos == 0 else cont_rows[pos].get(occurrence)
            if src is None:
                continue
            vals = _row_values(src)
            values[c - 1] = _to_number(vals[s - 1]) if 0 <= s - 1 < len(vals) else None
        out.append({"label": label, "row_type": rt, "values": values})

    return SourceTable(
        rows=out,
        table_name=str(primary.get("name") or "") or None,
        matched_columns=sorted(col_map),
        unmatched_columns=[_column_label(target, c) for c in unmatched],
        ratio_columns=[_column_label(target, c) for c in ratio],
        reason=None if out else "单体附注对应表格没有行",
    )
