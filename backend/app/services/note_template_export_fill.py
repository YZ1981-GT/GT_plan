"""附注模板模式导出编排（spec ``deliverable-trio-generation-accuracy`` §2；由 ``NoteWordExporter`` 搬出）。

模板块 ↔ 库内附注对应 → 未对应 / 未勾选 / 无交付内容的块删除（一级标题保留）→ 保留块按模板结构重建 → 章级附注
放进空章 → 正文交叉引用按交付编号改写 → 空分节合并 → 导出提醒。块级 docx 操作在 ``note_template_block_fill``
及其拆出模块；保留谓词与报表附注列同源（``note_deliverable_outline``）。

依赖注入（``TemplateFillHooks``）：块扫描 / 删块（``word_doc_utils``，附注域不直接依赖）、口径判定与空章节判定
（导出器按调用时的模块名传入，测试 monkeypatch 照旧生效）、模板正文字体回调。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa

from app.services.note_content_utils import note_has_data

if TYPE_CHECKING:
    from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)

__all__ = ["TemplateFillHooks", "fill_template_blocks", "note_display_label", "template_header_values"]

#: 章级附注编号（只有章号：「九」「十一」）
_CHAPTER_ONLY_RE = re.compile(r"^[一二三四五六七八九十]{1,3}$")


def note_display_label(note_section: str | None, section_title: str | None) -> str:
    """导出提醒里的章节称呼：编号 + 标题；按名称编码的章节（「四、存货」）编号已含标题，不再重复成「四、存货 存货」。"""
    code = (note_section or "").strip()
    title = (section_title or "").strip()
    if not title or code.endswith(title):
        return code
    return f"{code} {title}".strip()


def _titles_close(a: str | None, b: str | None) -> bool:
    """章名相近（字集合 Jaccard ≥ 0.5）：「关联方及关联交易」≈「关联方关系及其交易」，「公司基本情况」≈「公司（企业）基本情况」。"""
    from app.services.note_deliverable_outline import title_key

    ka, kb = set(title_key(a or "")), set(title_key(b or ""))
    return bool(ka and kb) and len(ka & kb) / len(ka | kb) >= 0.5


@dataclass(frozen=True)
class TemplateFillHooks:
    """导出器注入的依赖（见模块说明）。"""

    scan_blocks: Callable[[Any], list[Any]]
    delete_block: Callable[[Any], None]
    applies_to_scope: Callable[[str | None, str, str], bool]
    skip_fn: Callable[[dict], bool]
    run_style: Callable[[Any, bool], None]


async def template_header_values(db: Any, project_id: UUID, year: int) -> dict[str, str]:
    """页眉页脚占位（``{{company_full_name}}`` / ``{{audit_year}}``）的项目值；读失败只填年度。"""
    values = {"audit_year": str(year)}
    if db is None:
        return values
    try:
        from app.models.core import Project

        async with db.begin_nested():  # SAVEPOINT：读失败不毒化导出会话
            row = (
                await db.execute(
                    sa.select(Project.client_name, Project.name).where(Project.id == project_id)
                )
            ).first()
        # 编制单位用公司全称 client_name（与报表表头同口径）；project.name 兜底
        name = next(
            (v.strip() for v in (tuple(row) if row is not None else ()) if isinstance(v, str) and v.strip()),
            "",
        )
        if name:
            values["company_full_name"] = name
    except Exception:  # noqa: BLE001 — 测试替身 / 项目缺失
        logger.debug("note header values unavailable", exc_info=True)
    return values


def fill_template_blocks(
    exporter: Any,
    doc: Any,
    notes: list[DisclosureNote],
    index_sections: list[dict[str, Any]],
    *,
    hooks: TemplateFillHooks,
    header_values: dict[str, str],
    fs_amounts: list[tuple[str, float, float]],
    template_type: str,
    report_scope: str,
    selected: list[str] | None,
) -> tuple[list[str], Any]:
    """模板块 ↔ 库内附注：未对应 / 未勾选 / 无交付内容的块删除（一级标题保留），保留块按模板结构重建。

    保留谓词与轮廓编号和报表附注列（``note_deliverable_outline.build_fs_note_ref_plan``）同源：
    报表「附注」列写的编号就是交付件里的章节号。返回 ``(保留块编号, 交付统计)``。

    ``exporter`` 提供 ``_render_table`` / ``_effective_table_data``（表格渲染与导出器同口径）；
    ``header_values`` / ``fs_amounts`` 由调用方先读好（本函数不访问数据库）。
    """
    import app.services.note_template_block_fill as tbf
    from app.services.note_deliverable_filter import FilterStats, make_block_filter, structured_tables_nonempty
    from app.services.note_deliverable_outline import (
        TemplateNoteMatcher,
        container_orders,
        fs_region_balances,
        note_is_kept,
        number_regions,
        parse_note_template_outline,
    )

    report = tbf.DeliveryReport()
    names = tbf.style_map(doc)
    styles = tbf.styles_by_id(doc)
    try:
        outline = parse_note_template_outline(doc)  # 未改动的模板：与报表附注列读同一份轮廓
    except Exception:  # noqa: BLE001 — 轮廓失败只影响块外标题与编号映射
        logger.warning("附注模板轮廓解析失败，按块编号导出", exc_info=True)
        outline = None
    loose = tbf.wrap_loose_regions(doc, outline) if outline is not None else {}
    tbf.absorb_trailing_content(doc)
    tbf.strip_loose_guidance(doc, names)
    tbf.replace_doc_placeholders(doc, header_values)
    report.boilerplate_pending.extend(tbf.fill_boilerplate(doc, names, header_values.get("company_full_name")))
    blocks = hooks.scan_blocks(doc)

    coded = [b.section_code for b in blocks if not b.section_code.startswith(tbf.LOOSE_PREFIX)]
    coded_set = set(coded)
    matcher = TemplateNoteMatcher(notes, index_sections, coded)
    region_of: dict[str, Any] = {}
    for r in outline.regions if outline is not None else []:
        if r.code and r.code not in region_of:
            region_of[r.code] = r
    balances = fs_region_balances(outline, fs_amounts)
    fs_zero = {order for order, nonzero in balances.items() if not nonzero}

    def _label(note, region) -> str:
        if note is not None:
            return note_display_label(note.note_section, note.section_title)
        return region.title if region is not None else ""

    plans: list[tuple[Any, Any, Any, bool]] = []
    used: set[int] = set()
    for block in blocks:
        code = block.section_code
        if code.startswith(tbf.LOOSE_PREFIX):
            region = loose.get(code)
            note = matcher.for_region(outline, region) if region is not None else None
        else:
            # 口径排除：standalone 导出删除 consolidated_only 章节块（design §7 / 需求 12）
            if not hooks.applies_to_scope(code, template_type, report_scope):
                hooks.delete_block(block)
                continue
            region = region_of.get(code)
            note = matcher.for_code(code)
        if note is not None and id(note) in used:
            note = None  # 同一附注只进一个块
        # 与报表附注列同一谓词：按模板节的章标题 / 节标题 / 子标题 / 表题过滤后判有无内容
        content_ok = note is not None and note_is_kept(note, skip_fn=hooks.skip_fn, region=region)
        has_table = note is not None and structured_tables_nonempty(note)
        keep = content_ok and not (region is not None and region.order in fs_zero and not has_table)
        if note is not None:
            used.add(id(note))
            if content_ok and not keep:
                report.fs_zero_dropped.append(_label(note, region))
        if region is not None and balances.get(region.order) and not has_table:
            report.fs_balance_without_table.append(region.title)
        plans.append((block, note, region, keep))

    dropped_fs = set(report.fs_zero_dropped)
    unclaimed: list[DisclosureNote] = []
    for n in notes:
        if id(n) in used:
            # 勾选了、编辑器里有数据，但交付过滤后只剩提示 / 占位（或报表零余额）而未导出
            if (selected and not any(n is p[1] and p[3] for p in plans)
                    and note_has_data(n) and _label(n, None) not in dropped_fs):
                report.selected_not_exported.append(_label(n, None))
            continue
        code = (n.note_section or "").strip()
        if matcher.alias_to_code.get(code) in coded_set:
            continue  # 旧编号（「五、1」→「八、1」）的重复附注：模板块已由新编号附注认领
        if note_is_kept(n, skip_fn=hooks.skip_fn):
            unclaimed.append(n)

    # 分项节（标题不自动编号）有内容而上级节没有：上级节只留标题（与报表附注列同一规则 container_orders）
    base_kept = {r.order for _b, _n, r, k in plans if k and r is not None}
    containers = container_orders(outline, base_kept) if outline is not None else set()
    plans = [(b, n, r, True) if (not k and r is not None and r.order in containers) else (b, n, r, k)
             for b, n, r, k in plans]

    layouts = {id(p[0]): tbf.block_layout(p[0], names) for p in plans}
    title_order = tbf.capture_title_order(doc, layouts.values(), names)
    kept_orders = {r.order for _b, _n, r, k in plans if k and r is not None}
    numbers = number_regions(outline, lambda r: r.order in kept_orders) if outline is not None else {}

    kept_codes: list[str] = []
    text_elements: list[Any] = []
    display: dict[str, str] = {}
    for block, note, region, keep in plans:
        if not keep:
            tbf.keep_only_h1(block, names)
            continue
        code = block.section_code
        if code.startswith(tbf.LOOSE_PREFIX) and note is not None:  # 块外标题认领了附注 → 按附注编号落锚点 / 章节状态
            code = (note.note_section or "").strip() or code
            tbf.rename_block_markers(block, code)
        fstats = FilterStats()
        lay = layouts[id(block)]
        # 正文过滤与保留判定同一组标题：所在章标题、节标题（正文首行重复）+ 节内子标题 / 表题（正文里的重复短行）
        if region is not None:
            extra, structure = region.filter_titles, region.structure
        else:
            extra, structure = (tbf.paragraph_text(lay.title),), tuple(tbf.structure_titles(lay))
        rebuilt = tbf.rebuild_block(
            doc, block, note, exporter=exporter, run_style=hooks.run_style,
            text_filter=make_block_filter(note, fstats, extra_titles=extra, structure_titles=structure),
            names=names, styles=styles, layout=lay,
        )
        if not code.startswith(tbf.LOOSE_PREFIX):  # 无附注的块外上级节只留标题：不落锚点 / 章节状态
            kept_codes.append(code)
        text_elements.extend(rebuilt.text_elements)
        if fstats.dropped_lines or fstats.dropped_tables:
            report.filtered_lines += fstats.dropped_lines + fstats.dropped_tables
            report.filtered_sections.append(_label(note, region))
        if fstats.placeholders_left:
            report.placeholder_sections.append(_label(note, region))
        report.tables_rendered += rebuilt.stats.tables_rendered
        report.extra_tables += rebuilt.stats.extra_tables
        if region is not None and region.order in numbers:
            for c in (region.code, getattr(note, "note_section", None)):
                if c:
                    display[c.strip()] = numbers[region.order]
    tbf.transfer_title_restarts(title_order, styles)
    tbf.renumber_literal_titles(title_order, styles)

    # 章级附注（编号只有章号「九」）：该章模板块都没有可出具内容时，放在章标题之后（design §2.5）；
    # 其余模板无位置的附注只提醒不追加 —— 真实项目里它们是章级大模型综述 / 旧编号重复 / 指引误导入
    heads = tbf.chapter_contents(doc, names)
    for n in unclaimed:
        code = (n.note_section or "").strip()
        chapter_only = bool(_CHAPTER_ONLY_RE.match(code))
        not_placed = report.chapter_text_unplaced if chapter_only else report.unplaced
        pos = outline.chapter_pos_of_prefix.get(code) if outline is not None and chapter_only else None
        # 章号对上还要章名相近：上市 / 国企章号含义不同（国企「三」= 准则声明，上市「三」= 会计政策）
        if (pos is None or pos > len(heads) or heads[pos - 1][1]
                or not _titles_close(n.section_title, tbf.paragraph_text(heads[pos - 1][0]))):
            not_placed.append(_label(n, None))
            continue
        block = tbf.insert_synthetic_block(heads[pos - 1][0], code)
        fstats = FilterStats()
        rebuilt = tbf.rebuild_block(
            doc, block, n, exporter=exporter, run_style=hooks.run_style,
            text_filter=make_block_filter(n, fstats), names=names, styles=styles,
        )
        if not (rebuilt.stats.text_rendered or rebuilt.stats.tables_rendered):
            for el in (block.open_el, block.close_el):
                if el.getparent() is not None:
                    el.getparent().remove(el)
            not_placed.append(_label(n, None))
            continue
        heads[pos - 1] = (heads[pos - 1][0], True)
        kept_codes.append(code)
        text_elements.extend(rebuilt.text_elements)
        if fstats.placeholders_left:
            report.placeholder_sections.append(_label(n, None))

    # 正文交叉引用按交付件实际章节号改写（单体国企「附注八、10」→「七、9」）
    for e in index_sections:
        target = display.get((e.get("section_code") or "").strip())
        for alias in (e.get("legacy_aliases") or []) if target else []:
            if alias and alias.strip() not in display:
                display[alias.strip()] = target
    _changed, dangling = tbf.rewrite_cross_refs(text_elements, display)
    known = set(region_of) | {(n.note_section or "").strip() for n in notes}
    report.dangling_refs.extend(c for c in dangling if c in known)
    tbf.collapse_empty_sections(doc)
    report.empty_chapters.extend(tbf.empty_chapters(doc, names))
    return kept_codes, report
