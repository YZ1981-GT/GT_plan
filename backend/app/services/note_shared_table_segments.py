"""附注共享表的「段」解析 —— 行级合并的段边界真源（纯函数 + 模板缓存）。

**什么是共享表**

同一张附注子表内按科目分段、每段归属不同循环的表。全库实测 **29 张**
（`note_template_listed.json` 23 张 / `note_template_soe.json` 6 张），
判据 = 同一表的 ``rows[]`` 中出现 ≥2 个不同的 ``report_row_code``。代表性的：

- listed ``五、73`` / soe ``八、92`` 外币货币性项目（3 / 5 段：货币资金 · 应收账款 ·
  短期借款 · 长期借款 · 应付债券 → E1 / D2 / K / L）
- listed ``五、82``（+「续：」表）/ soe ``八、93`` 所有权或使用权受到限制的资产
  （6 / 7 段 → E1 / D1 / D2 / F2 / H1 / H2 / H3）
- listed ``五、81`` 现金流量表补充资料 · 资产负债表中的列报项目（3 段 → K / L）
- soe ``八、81`` 筹资活动产生的各项负债的变动情况（4 段 → K / L）

**为什么不新造段标识**

模板的**段首行已经带** ``report_row_code``（listed 2888 行中 95 行 / soe 1879 行中 26 行，
且恰好落在这些共享表的段首）→ 段归属在模板里已经声明好了，读它即可：

    段 = 从带 ``report_row_code`` 的行起，到下一个带 ``report_row_code`` 的行之前；
    末段到表尾；首个段首行之前的行（表内说明行等）不属于任何段。

**🔴 变体不可由章节号推导**

实测 20 个章节号同时存在于两份模板、其中 **13 个标题不同**
（``八、1`` listed = 政府补助 / soe = **货币资金**；``五、42`` listed = 其他应付款）。
故必须由 ``current_standard`` 前缀定变体，见 :func:`resolve_template_variant`。
查错模板 → 算出错误段边界 → 覆盖错误的行区间。

spec: .kiro/specs/disclosure-note-row-level-merge/ Requirements 2.1~2.7 / Property 4, 18
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

#: 模板变体（与 `note_template_{variant}.json` 文件名一致）
VARIANT_LISTED = "listed"
VARIANT_SOE = "soe"
VARIANTS: tuple[str, ...] = (VARIANT_LISTED, VARIANT_SOE)

#: 段归属戳的行内键名。**行内元数据键，不是表键** ——
#: `_count_rows_synced` 跳过的是 `_` 前缀的**表**键，两者别混。
SEG_KEY = "_seg"

#: 判定「多段共享表」的最小段数
MIN_SHARED_SEGMENTS = 2


#: 「无主行」判据 —— 表级汇总行**不属于任何段**（合计 / 小计 / 金融资产小计 …）。
#: 🔴 实测 13 个段的尾部挂着这类行（`五、32`×2 / `五、71` / `八、81` / `八、91` /
#: `三、` 章 8 个）。若把它们算进末段，owner 一推数据就会**把合计行删掉**。
#: 段内的 `……` / `可无限量添加行` **不是**无主行 —— 那是该段留给 owner 的可扩行。
_TOTAL_ROW_TYPES = frozenset({"total", "header_label"})

#: **显式**声明「本行不属于任何段」的 `row_type`。
#:
#: 用于表级兜底行 —— 如 soe `八、93 受限资产` 末行「其他」：它紧随
#: `BS-029 在建工程` 段之后，既不是合计行（`data_end` 的既有判据抓不到）
#: 也不是该段的可扩行，若算进段内，H2 一推数据就把它删掉。
#: 「其他」这个标签本身**不能**全局判定（`五、30`/`八、31` 递延所得税表里的
#: 「其他」是段内合法明细行），故只认模板的显式声明。
#:
#: spec: restricted-assets-note-row-scope-rollout Requirement 2
UNOWNED_ROW_TYPE = "unowned"


def _is_orphan_total(row: Any) -> bool:
    """该行是否是不属于任何段的表级汇总行/表头假行。"""
    if not isinstance(row, Mapping):
        return False
    if row.get("is_total") is True:
        return True
    return str(row.get("row_type") or "").strip() in _TOTAL_ROW_TYPES


def _is_unowned_row(row: Any) -> bool:
    """该行是否被模板**显式**声明为无主行（`row_type == "unowned"`）。"""
    if not isinstance(row, Mapping):
        return False
    return str(row.get("row_type") or "").strip() == UNOWNED_ROW_TYPE


@dataclass(frozen=True)
class Segment:
    """共享表内归属单一循环的连续行区间。

    Attributes:
        row_code: 段首行的 ``report_row_code``（如货币资金段 = ``BS-002``）。
        label: 段首行标签（如「货币资金」），供溯源展示与守卫可读性。
        start: 段首行在 ``rows[]`` 的下标（**含**）。
        end: 段止下标（**不含**）—— 到下一个段首前 / 表尾。
        data_end: **可写区**右界（不含）。等于 ``end`` 减去段尾连续的表级汇总行
            （合计/小计/表头假行）。行级合并替换的是 ``[start, data_end)``，
            使合计行在 owner 推送后原样保留。无汇总行时 ``data_end == end``
            （E1 外币表五个段皆如此 → 引入前后逐字等价）。
    """

    row_code: str
    label: str
    start: int
    end: int
    data_end: int = -1

    def __post_init__(self) -> None:  # dataclass frozen 下用 object.__setattr__
        if self.data_end < 0:
            object.__setattr__(self, "data_end", self.end)

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def data_length(self) -> int:
        return self.data_end - self.start


# ─────────────────────────────────────────────────────────────────────────────
# 纯函数（无 DB / 无 IO）
# ─────────────────────────────────────────────────────────────────────────────


def _row_code_of(row: Any) -> str:
    """行的 ``report_row_code``（非 dict / 缺字段 / 空白 → ``""``）。"""
    if not isinstance(row, Mapping):
        return ""
    return str(row.get("report_row_code") or "").strip()


def _label_of(row: Any) -> str:
    if not isinstance(row, Mapping):
        return ""
    return str(row.get("label") or "").strip()


def split_segments(rows: Sequence[Any] | None) -> list[Segment]:
    """按 ``report_row_code`` 切段。**纯函数**（Requirement 2.1 / 2.5）。

    首个段首行之前的行不属于任何段（不产出 Segment），故段区间的并集是
    「首个段首行 → 表尾」而不是整个 ``rows``。

    Examples:
        >>> rows = [
        ...     {"label": "货币资金", "report_row_code": "BS-002"},
        ...     {"label": "其中：美元"},
        ...     {"label": "应收账款", "report_row_code": "BS-006"},
        ... ]
        >>> [(s.row_code, s.start, s.end) for s in split_segments(rows)]
        [('BS-002', 0, 2), ('BS-006', 2, 3)]
    """
    items = list(rows or [])
    starts = [(i, _row_code_of(r)) for i, r in enumerate(items)]
    heads = [(i, code) for i, code in starts if code]
    raw: list[tuple[int, str, int]] = []  # (start, code, end)
    for pos, (idx, code) in enumerate(heads):
        end = heads[pos + 1][0] if pos + 1 < len(heads) else len(items)
        raw.append((idx, code, end))

    def _tail_total_len(start: int, end: int) -> int:
        n = 0
        while end - 1 - n > start and _is_orphan_total(items[end - 1 - n]):
            n += 1
        return n

    tails = [_tail_total_len(s, e) for s, _c, e in raw]
    # 🔴 区分**段级小计**与**表级合计**（判据是数据驱动的，不靠配置）：
    #   - 若**每个段**尾部都有汇总行 → 那是各段自己的小计（如 `五、30`/`八、31`
    #     递延所得税的「资产小计 / 负债小计」）→ 属段内，owner 应当能覆盖它
    #   - 否则，表最后一行的汇总行是**表级合计** → 不属任何段，必须保留
    per_segment_subtotals = len(tails) >= MIN_SHARED_SEGMENTS and all(t > 0 for t in tails)

    out: list[Segment] = []
    for pos, (idx, code, end) in enumerate(raw):
        data_end = end
        is_last = pos == len(raw) - 1
        if not per_segment_subtotals and is_last and end == len(items) and tails[pos]:
            data_end = end - tails[pos]
        # 段内**首个** `unowned` 行进一步收窄可写区（Requirement 2.5：
        # 不跨越保留 —— 否则 owner 数据会被这一行劈成两段，顺序不可控）
        for j in range(idx + 1, data_end):
            if _is_unowned_row(items[j]):
                data_end = j
                break
        out.append(
            Segment(
                row_code=code,
                label=_label_of(items[idx]),
                start=idx,
                end=end,
                data_end=data_end,
            )
        )
    return out


def find_segment(rows: Sequence[Any] | None, owner_row_code: str) -> Segment | None:
    """取 ``owner_row_code`` 对应的段（查不到返 ``None`` → 调用方 fail closed）。

    同一 ``row_code`` 在一张表里出现多次时取**首个**（模板不应如此，但不崩）。
    """
    want = str(owner_row_code or "").strip()
    if not want:
        return None
    for seg in split_segments(rows):
        if seg.row_code == want:
            return seg
    return None


def segment_row_codes(rows: Sequence[Any] | None) -> list[str]:
    """该表的段 ``row_code`` 清单（保序去重）。供守卫校验 ``owner_row_code`` 合法性。"""
    out: list[str] = []
    for seg in split_segments(rows):
        if seg.row_code not in out:
            out.append(seg.row_code)
    return out


def is_shared_rows(rows: Sequence[Any] | None) -> bool:
    """该表是否**多段共享表**（≥2 个不同 ``report_row_code``）。"""
    return len(segment_row_codes(rows)) >= MIN_SHARED_SEGMENTS


def stamp_baseline_rows(rows: Sequence[Any] | None) -> list[dict]:
    """模板骨架 → 带 ``_seg`` 戳的基线行（**标签保留、数值置空**）。

    Requirement 4.1 / 4.4：首次同步时用它作基线，使非 owner 段在附注里仍有骨架可见。
    ``_seg`` 由段首行的 ``report_row_code`` 向下传播到下一个段首之前；
    首个段首之前的行 ``_seg`` 为空串（不属任何段，行级合并不会动它们）。

    只保留 ``label`` / ``is_total`` / ``row_type`` 这类**结构性**字段；
    模板行上的 ``report_row_code`` / ``account_codes`` 是**模板元数据不落库**
    （落库靠 ``_seg`` 戳），数值列一律不预置（保持「空」而不是 0）。
    """
    items = list(rows or [])
    # 段尾汇总行的 `_seg` 留空 —— 它不属于任何 owner。这样 `find_stamped_window`
    # 定位出的连续区间天然止于合计行之前，与 `Segment.data_end` 口径一致。
    orphan_idx = {
        i
        for seg in split_segments(items)
        for i in range(seg.data_end, seg.end)
    }
    current = ""
    out: list[dict] = []
    for idx, row in enumerate(items):
        code = _row_code_of(row)
        if code:
            current = code
        base: dict[str, Any] = {
            "label": _label_of(row),
            SEG_KEY: "" if idx in orphan_idx else current,
        }
        if isinstance(row, Mapping):
            if row.get("is_total"):
                base["is_total"] = True
            row_type = str(row.get("row_type") or "").strip()
            if row_type and row_type != "data":
                base["row_type"] = row_type
        out.append(base)
    return out


def find_stamped_window(rows: Sequence[Any] | None, owner_row_code: str) -> tuple[int, int] | None:
    """在**落库行**里按 ``_seg`` 戳定位 owner 段的**首个连续区间**。

    Requirement 3.4：模板的 ``report_row_code`` 不随数据落库，且「其中：美元 / 欧元 /
    港币」这些标签在多个段里重复出现（全局按标签匹配必然串段），故落库侧靠 ``_seg``。

    历史脏数据里 owner 的行可能不连续 → 取首个连续段并由调用方 warning
    （不做全局重排，那会改动他段顺序）。查不到返 ``None``。
    """
    want = str(owner_row_code or "").strip()
    if not want:
        return None
    items = list(rows or [])
    start = None
    for i, row in enumerate(items):
        seg = str(row.get(SEG_KEY) or "").strip() if isinstance(row, Mapping) else ""
        if seg == want:
            if start is None:
                start = i
        elif start is not None:
            return (start, i)
    if start is not None:
        return (start, len(items))
    return None


def has_discontiguous_stamp(rows: Sequence[Any] | None, owner_row_code: str) -> bool:
    """owner 的 ``_seg`` 行是否**不连续**（供 warning，不阻断）。"""
    want = str(owner_row_code or "").strip()
    if not want:
        return False
    idx = [
        i for i, r in enumerate(rows or [])
        if isinstance(r, Mapping) and str(r.get(SEG_KEY) or "").strip() == want
    ]
    if len(idx) <= 1:
        return False
    return idx[-1] - idx[0] + 1 != len(idx)


def resolve_template_variant(
    current_standard: str | None, source_template: Any = None
) -> str | None:
    """决定查哪份 ``note_template``。返回 ``"listed"`` / ``"soe"`` / ``None``。

    🔴 **禁止按章节号推导**（Requirement 2.6）：实测 20 个章节号同时存在于两份模板、
    其中 13 个标题不同（``八、1`` listed = 政府补助 / soe = 货币资金；
    ``五、42`` listed = 其他应付款）。查错模板 → 段边界全错。

    优先级：``current_standard`` 前缀 > ``source_template`` > ``None``。
    ``source_template`` 只作兜底 —— 它有实证错配（项目 ``2aa00f57`` 的 ``五、1``
    记的是 ``soe``，而 ``五、1`` 是上市编号）。

    ``None`` 表示无法确定 → 调用方 **fail closed**（Requirement 2.7）。
    """
    cs = str(current_standard or "").strip().lower()
    if cs.startswith(VARIANT_LISTED):
        return VARIANT_LISTED
    if cs.startswith(VARIANT_SOE):
        return VARIANT_SOE
    st = getattr(source_template, "value", source_template)
    st = str(st or "").strip().lower()
    if st in VARIANTS:
        return st
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 模板读取（lru_cache；查不到一律返 None → 调用方 fail closed）
# ─────────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=4)
def _template_doc(variant: str) -> dict:
    """整份模板 JSON（文件缺失/损坏 → ``{}``）。"""
    path = _DATA_DIR / f"note_template_{variant}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:  # pragma: no cover - 环境异常
        logger.warning("note_shared_table_segments: load note_template_%s failed: %s", variant, err)
        return {}


@lru_cache(maxsize=512)
def template_rows(variant: str, section_number: str, table_name: str) -> tuple[Any, ...] | None:
    """模板某表的行集（元组以便 ``lru_cache``）。查不到返 ``None``。

    🔴 ``variant`` 必须由 :func:`resolve_template_variant` 得来，**不可由章节号推导**。
    """
    if variant not in VARIANTS:
        return None
    num = str(section_number or "").strip()
    name = str(table_name or "").strip()
    if not num or not name:
        return None
    for sec in _template_doc(variant).get("sections") or []:
        if not isinstance(sec, dict):
            continue
        if str(sec.get("section_number") or "").strip() != num:
            continue
        for tbl in sec.get("tables") or []:
            if isinstance(tbl, dict) and str(tbl.get("name") or "").strip() == name:
                return tuple(tbl.get("rows") or [])
    return None


def resolve_segment_window(
    variant: str, section_number: str, table_name: str, owner_row_code: str
) -> Segment | None:
    """段窗口（模板口径）。查不到表 / 查不到 ``owner_row_code`` → ``None``（fail closed）。"""
    rows = template_rows(variant, section_number, table_name)
    if rows is None:
        return None
    return find_segment(rows, owner_row_code)


def is_shared_table(variant: str, section_number: str, table_name: str) -> bool:
    """该表是否多段共享表 —— 供守卫判定「该不该带 ``_row_scope``」。"""
    rows = template_rows(variant, section_number, table_name)
    return is_shared_rows(rows) if rows is not None else False


def template_baseline_rows(
    variant: str, section_number: str, table_name: str
) -> list[dict] | None:
    """首次同步用的基线行（带 ``_seg`` 戳）。查不到表返 ``None``。"""
    rows = template_rows(variant, section_number, table_name)
    if rows is None:
        return None
    return stamp_baseline_rows(rows)


def iter_shared_tables(variant: str):
    """遍历该变体的全部多段共享表。

    Yields:
        ``(section_number, section_title, table_name, rows, segments)``
    """
    for sec in _template_doc(variant).get("sections") or []:
        if not isinstance(sec, dict):
            continue
        num = str(sec.get("section_number") or "").strip()
        title = str(sec.get("section_title") or "").strip()
        for tbl in sec.get("tables") or []:
            if not isinstance(tbl, dict):
                continue
            rows = list(tbl.get("rows") or [])
            segs = split_segments(rows)
            codes = {s.row_code for s in segs}
            if len(codes) < MIN_SHARED_SEGMENTS:
                continue
            yield num, title, str(tbl.get("name") or "").strip(), rows, segs


__all__ = [
    "MIN_SHARED_SEGMENTS",
    "SEG_KEY",
    "UNOWNED_ROW_TYPE",
    "VARIANTS",
    "VARIANT_LISTED",
    "VARIANT_SOE",
    "Segment",
    "find_segment",
    "find_stamped_window",
    "has_discontiguous_stamp",
    "is_shared_rows",
    "is_shared_table",
    "iter_shared_tables",
    "resolve_segment_window",
    "resolve_template_variant",
    "segment_row_codes",
    "split_segments",
    "stamp_baseline_rows",
    "template_baseline_rows",
    "template_rows",
]
