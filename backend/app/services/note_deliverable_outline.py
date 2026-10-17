"""附注交付件「模板轮廓」与显示编号：报表附注列、附注正文交叉引用、导出提醒同源计算。

为什么需要（spec ``deliverable-trio-generation-accuracy``，2026-10-16 真实数据实测）
--------------------------------------------------------------------------------
- 附注 docx 模板的一级标题（章）与块标题（节）都用 Word 自动编号：显示章号 = 一级标题
  位次，节号 = 本章内保留下来的节标题位次。单体国企模板没有合并专用章，「财务报表主要项目
  注释」显示为「七、」，章节编码（内部章号）却是「八」；无数据 / 未勾选的块被删除后，后续
  节号自动顺延。报表附注列写「八、10」，交付件里却是「七、9」。
- 上市模板「财务报表项目附注」章有 21 个块外标题（公允价值变动收益、信用减值损失…）：
  种子把这些节放在会计政策章，模板没有 ``##SECTION##`` 标记，但它们同样参与 Word 编号。
- 旧 ``report_row_note_mapping.json`` 按编码映射，而报表模板占位与库内报表是两套编号，
  映射里 21 行还指向会计政策章（「存货」→「四、存货」）。

本模块只读模板与附注数据，不改库。保留判定与附注交付件一键预设同口径：有数据
（``note_has_data``）且不在跳过条件内（``should_skip_empty_section``）。

与另外两个编号模块分工
--------------------
- ``note_section_numbering.compute_section_numbers``：按库内编号前缀分组编连续号（``{{seq}}`` / API）；
- ``note_section_numbering_service``：会计政策树编号；
- 本模块：以交付件模板为准的显示编号。
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import UUID

logger = logging.getLogger(__name__)

__all__ = [
    "FsNoteRefPlan",
    "NoteTemplateOutline",
    "OutlineRegion",
    "TemplateNoteMatcher",
    "build_fs_note_ref_plan",
    "chinese_numeral",
    "container_orders",
    "fs_region_balances",
    "fs_zero_region_orders",
    "load_fs_row_amounts",
    "load_note_template_outline",
    "note_is_kept",
    "note_skip_dict",
    "number_regions",
    "parse_note_template_outline",
    "region_is_kept",
    "title_key",
]

SECTION_CODE_INDEX_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "audit_report_templates"
    / "section_code_index.json"
)

_OPEN_RE = re.compile(r"^##SECTION:(.+?)##$")
_CLOSE_RE = re.compile(r"^##/SECTION:(.+?)##$")
_HEADING_RE = re.compile(r"^(?:heading|标题)\s*(\d)", re.IGNORECASE)
#: 母公司 / 公司财务报表主要项目注释（合并口径的母公司个别报表附注章）
_PARENT_CHAPTER_RE = re.compile(r"^(?:母公司|公司)财务报表")
#: 报表项目注释章：国企「财务报表主要项目注释」、上市「（合并）财务报表项目附注」
_MAIN_CHAPTER_RE = re.compile(r"财务报表(?:主要)?项目(?:注释|附注)")
_CONNECTORS = ("和", "及", "与", "、")

_CN_DIGITS = "零一二三四五六七八九"


def chinese_numeral(n: int) -> str:
    """1 → 一、10 → 十、11 → 十一、20 → 二十、99 → 九十九（章号够用）。"""
    if n <= 0:
        return str(n)
    if n < 10:
        return _CN_DIGITS[n]
    if n < 20:
        return "十" + (_CN_DIGITS[n - 10] if n > 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        return _CN_DIGITS[tens] + "十" + (_CN_DIGITS[ones] if ones else "")
    return str(n)


def title_key(text: Any) -> str:
    """节标题 / 报表行名的比对键。

    在报表行名规范化（NFKC、去空白 / 序号 / 标记 / 「（…填列）」）之上，再去掉模板标题常见的
    尾部括注（「（以下不适用的，请删除）」「（按费用性质列示）」「（单位：万股）」「（披露格式参考
    附注五、4）」）、【…】批注与「X、」手工编号。
    """
    from app.services.report_template_binding import normalize_row_label

    s = unicodedata.normalize("NFKC", str(text or ""))
    s = re.sub(r"【[^】]*】", "", s)
    key, _markers = normalize_row_label(s)
    key = re.sub(r"^[A-Za-z]、", "", key)
    while True:
        new = re.sub(r"\([^()]*\)$", "", key)
        if new == key:
            break
        key = new
    return key.rstrip(":")


# ---------------------------------------------------------------------------
# 模板轮廓
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutlineRegion:
    """模板里一个「节」：``##SECTION##`` 块（有编码）或块外同级标题（编码为 ``None``）。"""

    order: int
    code: str | None
    title: str
    key: str
    chapter_pos: int  # 所在一级标题位次（1 起；0 = 首个一级标题之前）
    style: str
    chapter_title: str = ""
    #: 节内模板子标题与表题文字（含块结束标记之后的块尾内容）：交付过滤删正文里与之重复的短行
    structure: tuple[str, ...] = ()
    #: 节标题占 Word 自动编号；显式取消编号的（「（1）一年内到期的长期借款」numId=0）是上一节的分项，不占节号
    numbered: bool = True

    @property
    def filter_titles(self) -> tuple[str, ...]:
        """正文首行重复判定额外比对的标题：所在章标题、模板节标题。"""
        return tuple(t for t in (self.chapter_title, self.title) if t)


@dataclass
class NoteTemplateOutline:
    """附注 docx 模板轮廓。"""

    chapters: list[str] = field(default_factory=list)
    regions: list[OutlineRegion] = field(default_factory=list)
    #: 块编码前缀（内部章号，如「八」）→ 所在一级标题位次
    chapter_pos_of_prefix: dict[str, int] = field(default_factory=dict)

    def chapter_display(self) -> dict[str, str]:
        """内部章号 → 显示章号（如单体国企「八」→「七」）。"""
        return {p: chinese_numeral(pos) for p, pos in self.chapter_pos_of_prefix.items()}

    def chapter_prefix_of(self, pos: int) -> str | None:
        hits = [p for p, q in self.chapter_pos_of_prefix.items() if q == pos]
        return hits[0] if len(hits) == 1 else None

    def regions_in(self, pos: int) -> list[OutlineRegion]:
        return [r for r in self.regions if r.chapter_pos == pos]

    def find_chapter(self, pattern: re.Pattern[str], *, exclude: re.Pattern[str] | None = None) -> int | None:
        for i, title in enumerate(self.chapters, 1):
            t = re.sub(r"\s+", "", unicodedata.normalize("NFKC", title))
            if exclude is not None and exclude.search(t):
                continue
            if pattern.search(t):
                return i
        return None

    @property
    def main_chapter_pos(self) -> int | None:
        return self.find_chapter(_MAIN_CHAPTER_RE, exclude=_PARENT_CHAPTER_RE)

    @property
    def parent_chapter_pos(self) -> int | None:
        return self.find_chapter(_PARENT_CHAPTER_RE)


def _style_names(doc) -> dict[str, str]:
    out: dict[str, str] = {}
    for s in doc.styles:
        sid = getattr(s, "style_id", None)
        if sid:
            out[sid] = s.name or ""
    return out


def _para_style(el, names: dict[str, str]) -> str:
    from docx.oxml.ns import qn

    ppr = el.find(qn("w:pPr"))
    if ppr is None:
        return ""
    ps = ppr.find(qn("w:pStyle"))
    if ps is None:
        return ""
    return names.get(ps.get(qn("w:val")), ps.get(qn("w:val")) or "")


def _heading_level(style: str) -> int | None:
    m = _HEADING_RE.match((style or "").strip())
    return int(m.group(1)) if m else None


def _para_text(el) -> str:
    from docx.oxml.ns import qn

    return "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()


def parse_note_template_outline(doc) -> NoteTemplateOutline:
    """从已加载的附注模板（未填充）解析轮廓。"""
    from docx.oxml.ns import qn

    from app.services.note_template_block_fill import numbering_disabled, structure_like

    names = _style_names(doc)
    #: ("block"/"loose", 索引) → 标题占节号（显式取消编号 numId=0 的不占：标题文字自带「（1）」「1、」）
    numbered: dict[tuple[str, int], bool] = {}
    out = NoteTemplateOutline()
    h1 = 0
    open_code: str | None = None
    open_has_region = False
    block_regions: list[tuple[str, str, str, int]] = []  # (code, title, style, pos)
    loose: list[tuple[int, str, str, int]] = []  # (seq, title, style, pos)
    sequence: list[tuple[str, int]] = []  # ("block"/"loose", 索引) —— 保持文档顺序
    prefix_votes: dict[str, Counter] = {}
    #: 节内结构标题：("block", 块编码) / ("loose", 序) → [子标题 / 表题]；块尾内容归最近关闭的块
    structure: dict[tuple[str, Any], list[str]] = {}
    owner: tuple[str, Any] | None = None

    for el in doc.element.body.iterchildren():
        if el.tag != qn("w:p"):
            continue
        text = _para_text(el)
        m = _OPEN_RE.match(text)
        if m:
            open_code = m.group(1).strip()
            open_has_region = False
            owner = ("block", open_code)
            continue
        if _CLOSE_RE.match(text):
            open_code = None  # owner 不清：块尾内容（参考表的表题）仍归这个块
            continue
        style = _para_style(el, names)
        level = _heading_level(style)
        if level == 1:
            h1 += 1
            out.chapters.append(text)
            if open_code:
                prefix_votes.setdefault(open_code.split("、")[0], Counter())[h1] += 1
            else:
                owner = None
            continue
        if open_code is not None and not open_has_region and "、" in open_code \
                and text and not text.startswith("{{") and level is not None:
            block_regions.append((open_code, text, style, h1))
            sequence.append(("block", len(block_regions) - 1))
            numbered[("block", len(block_regions) - 1)] = not numbering_disabled(el)
            prefix_votes.setdefault(open_code.split("、")[0], Counter())[h1] += 1
            open_has_region = True
            continue
        if open_code is None and text and level is not None and level >= 2:
            loose.append((len(loose), text, style, h1))
            sequence.append(("loose", len(loose) - 1))
            numbered[("loose", len(loose) - 1)] = not numbering_disabled(el)
            owner = ("loose", len(loose) - 1)
            continue
        if owner is not None and text and not text.startswith(("{{", "##")):
            if (level is not None and level >= 2) or (level is None and structure_like(text)):
                structure.setdefault(owner, []).append(text)

    # 每章块标题样式（多数）；块外段落只认同章同样式的标题为「节」
    chapter_style: dict[int, str] = {}
    by_pos: dict[int, Counter] = {}
    for _code, _t, st, pos in block_regions:
        by_pos.setdefault(pos, Counter())[st] += 1
    for pos, cnt in by_pos.items():
        chapter_style[pos] = cnt.most_common(1)[0][0]

    def _chapter(pos: int) -> str:
        return out.chapters[pos - 1] if 0 < pos <= len(out.chapters) else ""

    # 块外的下级标题（样式不是本章节标题样式）不成节：它和它下面的表题归前一个块外节
    last_loose: int | None = None
    for kind, idx in sequence:
        if kind != "loose":
            last_loose = None
            continue
        _seq, title, st, pos = loose[idx]
        if chapter_style.get(pos) == st:
            last_loose = idx
        elif last_loose is not None:
            structure.setdefault(("loose", last_loose), []).extend([title, *structure.get(("loose", idx), [])])

    order = 0
    for kind, idx in sequence:
        if kind == "block":
            code, title, st, pos = block_regions[idx]
            out.regions.append(OutlineRegion(order, code, title, title_key(title), pos, st, _chapter(pos),
                                             tuple(structure.get(("block", code), ())),
                                             numbered.get(("block", idx), True)))
            order += 1
        else:
            _seq, title, st, pos = loose[idx]
            if chapter_style.get(pos) != st:
                continue
            out.regions.append(OutlineRegion(order, None, title, title_key(title), pos, st, _chapter(pos),
                                             tuple(structure.get(("loose", idx), ())),
                                             numbered.get(("loose", idx), True)))
            order += 1
    for prefix, votes in prefix_votes.items():
        out.chapter_pos_of_prefix[prefix] = votes.most_common(1)[0][0]
    return out


@lru_cache(maxsize=8)
def _outline_cached(path: str, mtime: float) -> NoteTemplateOutline:  # noqa: ARG001 — mtime 作缓存键
    from docx import Document

    return parse_note_template_outline(Document(path))


def load_note_template_outline(template_type: str | None, report_scope: str | None) -> NoteTemplateOutline | None:
    """按准则 + 口径读附注模板轮廓（文件改动即失效）；模板缺失返回 ``None``。

    模板路径经 ``note_word_exporter.resolve_note_template_path``（附注域里唯一经 manifest 定位模板的地方）。
    """
    from app.services.note_word_exporter import resolve_note_template_path

    p = resolve_note_template_path(template_type, report_scope)
    if p is None:
        return None
    return _outline_cached(str(p), p.stat().st_mtime)


def number_regions(outline: NoteTemplateOutline, kept: Callable[[OutlineRegion], bool]) -> dict[int, str]:
    """保留下来的节按章内顺序连续编号 → ``{region.order: "七、9"}``（与 Word 自动编号一致）。

    标题取消了自动编号的节（「（1）一年内到期的长期借款」）不占节号、也没有自己的编号。
    """
    out: dict[int, str] = {}
    counters: Counter = Counter()
    for r in outline.regions:
        if not kept(r) or not r.numbered:
            continue
        counters[r.chapter_pos] += 1
        out[r.order] = f"{chinese_numeral(r.chapter_pos)}、{counters[r.chapter_pos]}"
    return out


def container_orders(outline: NoteTemplateOutline, kept_orders: set[int]) -> set[int]:
    """保留下来的分项节（标题不自动编号）的上级节：同章内前面最近的自动编号节。

    模板把「一年内到期的非流动负债」与其分项「（1）一年内到期的长期借款」…拆成几个块：分项有内容而上级块
    没有时，上级标题仍须保留，否则分项挂到前一节（「其他应付款」）下面，节号也错位。附注导出与报表附注列共用。
    """
    out: set[int] = set()
    parent: OutlineRegion | None = None
    for r in outline.regions:
        if r.numbered:
            parent = r
            continue
        if parent is not None and parent.chapter_pos == r.chapter_pos and r.order in kept_orders:
            out.add(parent.order)
    return out - kept_orders


# ---------------------------------------------------------------------------
# 模板块 ↔ 库内附注
# ---------------------------------------------------------------------------


def load_section_code_index(variant_key: str) -> list[dict[str, Any]]:
    """``section_code_index.json`` 中某变体的 sections（缺失返回 []）。"""
    if not SECTION_CODE_INDEX_PATH.exists():
        return []
    try:
        data = json.loads(SECTION_CODE_INDEX_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        logger.warning("section_code_index.json 解析失败: %s", SECTION_CODE_INDEX_PATH)
        return []
    sections = data.get("variants", {}).get(variant_key, {}).get("sections", [])
    return [s for s in sections if isinstance(s, dict)]


class TemplateNoteMatcher:
    """模板块编码 / 块外标题 → 库内附注。

    按编码的规则与附注模板模式导出一致：编码精确 → 索引 ``legacy_aliases`` → 唯一 ``section_id``
    兜底（只认没被别的块按编码认领的附注）。块外标题只在「没有任何模板块认领」的附注里按标题
    键找，同内部章号优先，否则要求唯一。
    """

    def __init__(
        self,
        notes: Iterable[Any],
        index_sections: list[dict[str, Any]],
        block_codes: Iterable[str],
    ) -> None:
        self.notes = list(notes)
        self.block_codes = {(c or "").strip() for c in block_codes}
        self.by_section = {(getattr(n, "note_section", None) or "").strip(): n for n in self.notes}
        self.alias_to_code: dict[str, str] = {}
        self.sid_of_code: dict[str, Any] = {}
        for e in index_sections:
            code = (e.get("section_code") or "").strip()
            self.sid_of_code[code] = e.get("section_id")
            for alias in e.get("legacy_aliases", []) or []:
                a = (alias or "").strip()
                if a:
                    self.alias_to_code[a] = code
        self.by_sid: dict[str, list[Any]] = {}
        for n in self.notes:
            n_code = (getattr(n, "note_section", None) or "").strip()
            sid = getattr(n, "section_id", None)
            if sid and n_code not in self.block_codes and self.alias_to_code.get(n_code) not in self.block_codes:
                self.by_sid.setdefault(sid, []).append(n)
        claimed = {id(n) for n in (self.for_code(c) for c in self.block_codes) if n is not None}
        self.unclaimed_by_key: dict[str, list[Any]] = {}
        for n in self.notes:
            if id(n) in claimed:
                continue
            k = title_key(getattr(n, "section_title", None))
            if k:
                self.unclaimed_by_key.setdefault(k, []).append(n)

    def for_code(self, section_code: str | None) -> Any | None:
        code = (section_code or "").strip()
        if not code:
            return None
        note = self.by_section.get(code)
        if note is not None:
            return note
        for db_section, n in self.by_section.items():
            if self.alias_to_code.get(db_section) == code:
                return n
        cands = self.by_sid.get(self.sid_of_code.get(code) or "", [])
        return cands[0] if len(cands) == 1 else None

    def for_title(self, key: str, chapter_prefix: str | None = None) -> Any | None:
        cands = self.unclaimed_by_key.get(key or "", [])
        if chapter_prefix:
            same = [n for n in cands if (getattr(n, "note_section", "") or "").split("、")[0] == chapter_prefix]
            if len(same) == 1:
                return same[0]
        return cands[0] if len(cands) == 1 else None

    def for_region(self, outline: NoteTemplateOutline, region: OutlineRegion) -> Any | None:
        if region.code:
            return self.for_code(region.code)
        return self.for_title(region.key, outline.chapter_prefix_of(region.chapter_pos))


def note_skip_dict(note: Any) -> dict[str, Any]:
    """``should_skip_empty_section`` 的入参形状（与附注导出 ``_note_to_skip_dict`` 同口径）。"""
    status = getattr(note, "status", None)
    return {
        "is_deleted": getattr(note, "is_deleted", False),
        "status": getattr(status, "value", status),
        "is_empty": getattr(note, "is_empty", False),
        "text_content": getattr(note, "text_content", None),
        "table_data": getattr(note, "table_data", None),
    }


def note_is_kept(
    note: Any,
    *,
    skip_fn: Callable[[dict], bool] | None = None,
    region: OutlineRegion | None = None,
) -> bool:
    """交付口径的保留判定（附注导出与报表附注列共用一个谓词）：不在跳过条件内，且交付过滤后仍有内容。

    「有内容」= 结构化表格非空，或过滤后的正文非空（``note_deliverable_filter``）：只有大模型提示 /
    占位的章节不出现在交付件里，报表附注列也就不给它编号。给了模板节 ``region`` 时按导出渲染同一组标题过滤
    （所在章标题、节标题、节内子标题 / 表题）。``skip_fn`` 供附注导出传入本模块级的
    ``should_skip_empty_section``（测试按模块打桩）。
    """
    from app.services.note_deliverable_filter import note_has_deliverable_content

    if note is None:
        return False
    if skip_fn is None:
        from app.services.note_word_dynamic_styles import should_skip_empty_section as skip_fn
    if skip_fn(note_skip_dict(note)):
        return False
    if region is None:
        return note_has_deliverable_content(note)
    return note_has_deliverable_content(note, extra_titles=region.filter_titles, structure_titles=region.structure)


async def load_fs_row_amounts(db, project_id: UUID, year: int) -> list[tuple[str, float, float]]:
    """本项目审定报表（资产负债表 / 利润表）行 → ``[(行名, 本期, 上期)]``；读失败 / 类型不符的行跳过（fail-open）。"""
    from decimal import Decimal

    if db is None:
        return []
    try:
        import sqlalchemy as sa

        from app.models.report_models import FinancialReport, FinancialReportType

        async with db.begin_nested():  # SAVEPOINT：读失败不毒化调用方事务
            result = await db.execute(
                sa.select(
                    FinancialReport.row_name,
                    FinancialReport.current_period_amount,
                    FinancialReport.prior_period_amount,
                ).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.is_deleted == sa.false(),
                    FinancialReport.report_type.in_(
                        [FinancialReportType.balance_sheet, FinancialReportType.income_statement]
                    ),
                )
            )
            rows = result.all()
    except Exception:  # noqa: BLE001 — 报表未生成 / 测试替身
        logger.debug("FS rows unavailable for note keep rule", exc_info=True)
        return []

    def _num(v: Any) -> float:
        return float(v) if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) else 0.0

    out: list[tuple[str, float, float]] = []
    for row in rows if isinstance(rows, list) else []:
        try:
            name, cur, prior = row[0], row[1], row[2]
        except (TypeError, IndexError, KeyError):
            continue
        if isinstance(name, str) and name.strip():
            out.append((name, _num(cur), _num(prior)))
    return out


def fs_region_balances(outline: NoteTemplateOutline | None, rows: list[tuple[str, float, float]]) -> dict[int, bool]:
    """报表项目注释章里按行名对上报表行的节 → 是否有余额（对上的行本期或上期任一非 0）。"""
    if outline is None or not rows:
        return {}
    plan = FsNoteRefPlan(outline=outline, numbers={}, has_notes=True)
    out: dict[int, bool] = {}
    for name, cur, prior in rows:
        region = plan.region_for(name)
        if region is None:
            continue
        out[region.order] = out.get(region.order, False) or abs(cur) >= 0.005 or abs(prior) >= 0.005
    return out


def fs_zero_region_orders(outline: NoteTemplateOutline | None, rows: list[tuple[str, float, float]]) -> set[int]:
    """报表项目注释章里按行名对上报表行、且对上的行本期上期全为 0 的节（``region.order``）。"""
    return {order for order, nonzero in fs_region_balances(outline, rows).items() if not nonzero}


def region_is_kept(
    note: Any,
    region: OutlineRegion | None,
    fs_zero: set[int],
    *,
    skip_fn: Callable[[dict], bool] | None = None,
) -> bool:
    """节是否进交付件：``note_is_kept``；报表项目注释章里报表余额全为 0 的节还要求有非空结构化表格
    （只剩文字的零余额科目不出具，如「本期无交易性金融资产」）。"""
    if not note_is_kept(note, skip_fn=skip_fn, region=region):
        return False
    if region is not None and region.order in fs_zero:
        from app.services.note_deliverable_filter import structured_tables_nonempty

        return structured_tables_nonempty(note)
    return True


# ---------------------------------------------------------------------------
# 报表附注列
# ---------------------------------------------------------------------------


@dataclass
class FsNoteRefPlan:
    """报表附注列编号方案。"""

    outline: NoteTemplateOutline
    numbers: dict[int, str]
    has_notes: bool
    #: 报表模板编码 → (附注编码, 附注标题)（``report_row_note_mapping.json``）；只在节标题对不上、
    #: 且映射标题与本行行名一致时兜底（映射按编码登记，而模板与库内是两套编码，不可单凭编码采信）
    hints: dict[str, tuple[str, str]] = field(default_factory=dict)

    def region_for(self, label: str, *, parent: bool = False, hint_code: str | None = None) -> OutlineRegion | None:
        pos = self.outline.parent_chapter_pos if parent else self.outline.main_chapter_pos
        if pos is None:
            return None
        regions = self.outline.regions_in(pos)
        key = title_key(label)
        if key:
            exact = [r for r in regions if r.key == key]
            if exact:
                return exact[0]
            compound = [r for r in regions if any(r.key.startswith(key + c) for c in _CONNECTORS)]
            if len(compound) == 1:
                return compound[0]
        hint = self.hints.get(hint_code or "") if not parent else None
        if hint and key and title_key(hint[1]) == key:
            hit = [r for r in regions if r.code == hint[0]]
            if len(hit) == 1:
                return hit[0]
        return None

    def ref_for(self, label: str, *, parent: bool = False, hint_code: str | None = None) -> str | None:
        region = self.region_for(label, parent=parent, hint_code=hint_code)
        if region is None:
            return None
        return self.numbers.get(region.order)


async def build_fs_note_ref_plan(
    db,
    project_id: UUID,
    year: int,
    *,
    template_type: str | None,
    report_scope: str | None,
    hints: dict[str, tuple[str, str]] | None = None,
) -> FsNoteRefPlan | None:
    """读模板轮廓 + 本项目附注，求报表附注列编号方案；模板缺失返回 ``None``。"""
    import sqlalchemy as sa

    from app.models.report_models import DisclosureNote
    from app.services.note_section_catalog import build_variant_key, note_applies_to_report_scope

    outline = load_note_template_outline(template_type, report_scope)
    if outline is None:
        return None
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    notes = [
        n for n in result.scalars().all()
        if note_applies_to_report_scope(n.note_section, template_type, report_scope)
    ]
    matcher = TemplateNoteMatcher(
        notes,
        load_section_code_index(build_variant_key(template_type, report_scope)),
        [r.code for r in outline.regions if r.code],
    )
    # 与附注模板模式导出同一保留谓词（含报表零余额规则），编号才与交付件一致
    fs_zero = fs_zero_region_orders(outline, await load_fs_row_amounts(db, project_id, year))
    kept = {
        r.order for r in outline.regions
        if (r.code is None or note_applies_to_report_scope(r.code, template_type, report_scope))
        and region_is_kept(matcher.for_region(outline, r), r, fs_zero)
    }
    kept |= container_orders(outline, kept)
    numbers = number_regions(outline, lambda r: r.order in kept)
    return FsNoteRefPlan(outline=outline, numbers=numbers, has_notes=bool(notes), hints=dict(hints or {}))
