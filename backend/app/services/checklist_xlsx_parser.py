"""核对表 xlsx 解析器 — 将 A17-5-x 等 xlsx 核对表模板解析为结构化 JSON.

设计目标（PRE-4，completion-phase-infra）：
- **独立模块**，不扩展 `checklist_docx_parser.py`（输入格式不同：xlsx vs docx）。
- 输入：xlsx 模板 + 列映射（权威来源 `backend/data/a17_xlsx_audit.json`，由 PRE-4-0 产出）。
- 输出：`{ wp_code, title, sections, toc, stats }`，兼容前端 `GtChecklistTable.vue`。
- 缓存：mtime 缓存（同 docx parser 的做法）。

阶段 1（PRE-4-1）：A17-5-1 首版。两节结构：
- 「一、审计目标」objective_section（has_conclusion=false，纯文本 header，无填写列）
- 「二、核对程序」procedure_section（has_conclusion=true，actionable）

阶段 2（PRE-4-2）：扩展 A17-5-2~5-5（内控/IPO/新三板/函证）。各核对表列位置不同
（A17-5-1 结论在 D，其余在 E；参考列 A17-5-1=G、A17-5-2=H、A17-5-3/4/5 无），
parser 一律从 audit JSON `column_roles` 动态读取列角色，不硬编码；A17-5-4 多一个
`disclosure_chapter`（披露章节）列；A17-5-5 审计目标节 seq 可能为 null——均已容错。

每条核对程序条目 item_id = `A17-5-{x}-{seq:03d}`（对齐 persistence.md `A17-5-{x}-{seq}`）。

阶段 3（PRE-4-3）：A15-1、A14-1（来源 `a7_a15_xlsx_audit.json`）。
- **多 audit 源**：列映射权威源现为两份 JSON（`a17_xlsx_audit.json` + `a7_a15_xlsx_audit.json`），
  按 wp_code 在哪个 JSON 登记决定用哪个源（a17 优先，避免回归 A17-5-x）。
- **A15-1 持续经营调查表**（分章节问卷）：财务 11 / 经营 6 / 其他 4 + 调查结论。
  item_id 对齐 persistence.md：`A15-1-fin-01..11` / `A15-1-ops-01..06` / `A15-1-oth-01..04` / `A15-1-conclusion`。
  结构与 A17-5-x 两节不同（按 `sections` 行标记分组 + 重复表头行 `序号` 跳过）。
- **A14-1 内部控制缺陷汇总表**（动态行 grid）：双行表头（R5 主表头 + R6 子表头），
  认定 6 列矩阵 G/H/I/J/K/L = 存在发生/完整性/截止/权利和义务/计价和分摊/列报。
  按 persistence.md 定案：认定 6 列 → **remark JSON**（固定 schema，不拆列 item_id），
  item_id 模式 `A14-1-row-{nnn}` 自增。parser 输出 grid 模板（列定义 + 认定矩阵 +
  remark schema），不强套两节解析；`example-skip` 示例 sheet 跳过。

parser 按 audit entry 的 sheet 结构差异分派（grid → columns_main/columns_sub；
分章节问卷 → sections + checklist_rows_sample；两节 → objective_section/procedure_section）。
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl

logger = logging.getLogger(__name__)

# ─── 路径常量 ─────────────────────────────────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "wp_templates" / "A"
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
# 列映射权威源（两份 audit JSON）。a17 在前 → 同 wp_code 冲突时 a17 优先，避免 A17-5-x 回归。
_AUDIT_JSON_PATH = _DATA_DIR / "a17_xlsx_audit.json"
_AUDIT_JSON_PATHS = [
    _DATA_DIR / "a17_xlsx_audit.json",
    _DATA_DIR / "a7_a15_xlsx_audit.json",
]

# 内容列默认在 B（seq 在 A）；列映射 audit JSON 只标注填写/参考列角色（D/E/F/G）。
_DEFAULT_SEQ_COL = "A"
_DEFAULT_CONTENT_COL = "B"

# ─── 全局 mtime 缓存 ──────────────────────────────────────────────────────────
# wp_code → (xlsx_mtime, audit_mtime, parsed)
_CHECKLIST_XLSX_CACHE: dict[str, tuple[float, float, dict]] = {}
# audit JSON 解析缓存：(各源 mtime 元组) → { wp_code: entry }
_AUDIT_CONFIG_CACHE: tuple[tuple[float, ...], dict[str, dict]] | None = None


# ─── 列映射（audit JSON 权威源） ──────────────────────────────────────────────


def _audit_sources_mtime() -> tuple[float, ...]:
    """返回所有 audit 源文件的 mtime 元组（不存在记 0.0）——用作缓存键。"""
    return tuple(
        os.path.getmtime(p) if p.exists() else 0.0 for p in _AUDIT_JSON_PATHS
    )


def _load_audit_config() -> dict[str, dict]:
    """加载并合并所有 audit JSON（a17 + a7_a15），按 wp_code 索引（带 mtime 缓存）.

    返回 { wp_code: audit_entry }。多源合并规则：**靠前的源优先**
    （`_AUDIT_JSON_PATHS` 中 a17 在 a7_a15 之前 → A17-5-x 不会被覆盖）。
    任一源不存在/解析失败则跳过该源，不影响其余源。
    """
    global _AUDIT_CONFIG_CACHE

    mtimes = _audit_sources_mtime()
    if _AUDIT_CONFIG_CACHE is not None and _AUDIT_CONFIG_CACHE[0] == mtimes:
        return _AUDIT_CONFIG_CACHE[1]

    index: dict[str, dict] = {}
    # 逆序遍历：后面的源先写入，前面的源后写入覆盖 → 实现「靠前的源优先」。
    for path in reversed(_AUDIT_JSON_PATHS):
        if not path.exists():
            logger.warning("audit JSON 不存在: %s", path)
            continue
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:  # noqa: BLE001
            logger.warning("audit JSON 解析失败 (%s): %s", path.name, e)
            continue
        # audit JSON 顶层可能是 list 或 { "workpapers": [...] }
        entries = raw if isinstance(raw, list) else raw.get("workpapers", [])
        for entry in entries:
            if isinstance(entry, dict) and entry.get("wp_code"):
                index[entry["wp_code"]] = entry

    _AUDIT_CONFIG_CACHE = (mtimes, index)
    return index


def _get_audit_entry(wp_code: str) -> dict | None:
    """取某 wp_code 的 audit 配置条目."""
    return _load_audit_config().get(wp_code)


def _find_bundle_sheet(wp_code: str) -> tuple[dict, dict] | None:
    """bundle 子码别名解析（A11-2 / A11-3 等）.

    某些 wp_code 不是独立 xlsx，而是父 bundle xlsx 内的某个 sheet
    （如 A11-2/A11-3 是 `A11 期后事项程序表.xlsx` 内的两个调查问卷 sheet）。
    在 audit 索引中查找：某父条目的某 sheet 名以该 wp_code **结尾**
    （从 sheet 名末尾自动推导，不硬编码 sheet 名），返回 `(父条目, sheet 配置)`。
    仅匹配 component_type 为 checklist-table 的 sheet；找不到返回 None。
    """
    for entry in _load_audit_config().values():
        # 跳过本身即顶层 wp_code 的条目（独立底稿不当作 bundle 子码处理）。
        if entry.get("wp_code") == wp_code:
            continue
        for sheet in entry.get("sheets", []):
            if not isinstance(sheet, dict):
                continue
            if sheet.get("component_type") != "checklist-table":
                continue
            name = (sheet.get("name") or "").strip()
            if name.endswith(wp_code):
                return entry, sheet
    return None


# ─── 公开 API ─────────────────────────────────────────────────────────────────


def get_template_path(wp_code: str) -> Path | None:
    """根据 wp_code 前缀查找 xlsx 模板文件路径.

    优先用 audit JSON 中登记的 filename；其次按 bundle 子码（A11-2/A11-3）
    解析到父 bundle 文件；否则按文件名前缀匹配。
    """
    entry = _get_audit_entry(wp_code)
    if entry and entry.get("filename"):
        candidate = _TEMPLATE_DIR / entry["filename"]
        if candidate.exists():
            return candidate

    # bundle 子码（A11-2/A11-3）：返回父 bundle 文件路径（父条目 filename）。
    bundle = _find_bundle_sheet(wp_code)
    if bundle is not None:
        parent_entry, _sheet = bundle
        parent_filename = parent_entry.get("filename")
        if parent_filename:
            candidate = _TEMPLATE_DIR / parent_filename
            if candidate.exists():
                return candidate

    if not _TEMPLATE_DIR.exists():
        return None
    for f in _TEMPLATE_DIR.iterdir():
        if f.suffix.lower() == ".xlsx" and f.name.startswith(wp_code):
            return f
    return None


async def get_checklist_template(wp_code: str) -> dict:
    """获取解析后的 xlsx 核对表模板（带 mtime 缓存）.

    缓存键同时考虑 xlsx 文件与 audit JSON 的 mtime——任一变化即重新解析。
    """
    file_path = get_template_path(wp_code)
    if file_path is None:
        raise FileNotFoundError(f"未找到 xlsx 核对表模板文件: wp_code={wp_code}")

    xlsx_mtime = os.path.getmtime(file_path)
    # 取所有 audit 源 mtime 之和作为聚合缓存键（任一源变化即触发重解析）。
    audit_mtime = sum(_audit_sources_mtime())

    cached = _CHECKLIST_XLSX_CACHE.get(wp_code)
    if cached is not None:
        c_xlsx, c_audit, c_data = cached
        if c_xlsx == xlsx_mtime and c_audit == audit_mtime:
            return c_data

    parsed = parse_checklist_xlsx(file_path, wp_code)
    _CHECKLIST_XLSX_CACHE[wp_code] = (xlsx_mtime, audit_mtime, parsed)
    return parsed


def parse_checklist_xlsx(file_path: Path | str, wp_code: str) -> dict:
    """解析 xlsx 核对表模板，返回兼容 GtChecklistTable 的结构化 JSON.

    按 audit entry 的 sheet 结构差异分派：
    - A14-1：动态行 grid（columns_main + columns_sub 认定矩阵）→ `_parse_grid`。
    - A15-1：分章节问卷（sections + checklist_rows_sample）→ `_parse_sectioned_checklist`。
    - A17-5-x：两节结构（objective_section + procedure_section）→ `_parse_two_section`。
    """
    file_path = Path(file_path)
    entry = _get_audit_entry(wp_code)
    if entry is None:
        # bundle 子码（A11-2/A11-3）：无独立顶层 wp_code 条目，
        # 解析父 bundle 文件内的对应 sheet（单节调查问卷）。
        bundle = _find_bundle_sheet(wp_code)
        if bundle is not None:
            parent_entry, sheet_cfg = bundle
            return _parse_bundle_questionnaire(
                file_path, wp_code, parent_entry, sheet_cfg
            )
        raise ValueError(f"audit JSON 中未找到 wp_code 配置: {wp_code}")

    sheet_cfg = _select_sheet_config(entry)

    # 动态行 grid（A14-1）：双行表头 + 认定矩阵列。
    if sheet_cfg.get("columns_main") and sheet_cfg.get("columns_sub"):
        return _parse_grid(file_path, wp_code, entry, sheet_cfg)

    # 分章节问卷（A15-1）：sections 行标记 + 重复表头行。
    if sheet_cfg.get("sections") and sheet_cfg.get("checklist_rows_sample"):
        return _parse_sectioned_checklist(file_path, wp_code, entry, sheet_cfg)

    # 两节结构（A17-5-x）：审计目标 + 核对程序。
    return _parse_two_section(file_path, wp_code, entry)


# ─── 两节结构解析（A17-5-x） ─────────────────────────────────────────────────


def _parse_two_section(file_path: Path, wp_code: str, entry: dict) -> dict:
    """解析「审计目标 + 核对程序」两节结构的 xlsx 核对表.

    - objective_section（无 conclusion 列）→ 转为一个 section，items 为只读 header
      （type=header，不参与填写/统计）。
    - procedure_section（有 conclusion 列）→ 转为一个 section，items 为 actionable，
      每条带 item_id `{wp_code}-{seq:03d}` 与预置 wp_ref（来自 G 列）。

    解析以实物 xlsx 单元格为准，audit JSON 提供锚点行/列角色/item_id 模式作为权威映射。
    """
    sheet_cfg = _select_sheet_config(entry)
    sheet_name = sheet_cfg.get("name")

    wb = openpyxl.load_workbook(str(file_path), data_only=True, read_only=True)
    try:
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

        sections: list[dict] = []

        # 1) 审计目标节（纯说明，无填写列）
        obj_cfg = sheet_cfg.get("objective_section")
        if obj_cfg:
            obj_section = _parse_objective_section(ws, obj_cfg)
            if obj_section["items"]:
                sections.append(obj_section)

        # 2) 核对程序节（actionable）
        proc_cfg = sheet_cfg.get("procedure_section")
        if proc_cfg:
            proc_section = _parse_procedure_section(ws, proc_cfg, wp_code)
            if proc_section["items"]:
                sections.append(proc_section)
    finally:
        wb.close()

    toc = [
        {"id": s["id"], "title": s["title"], "applicable": None} for s in sections
    ]

    total_actionable = 0
    total_guidance = 0
    for sec in sections:
        for item in sec["items"]:
            if item["type"] == "actionable":
                total_actionable += 1
                total_guidance += len(item.get("children", []))

    return {
        "wp_code": wp_code,
        "title": _extract_title(wp_code, entry),
        "sections": sections,
        "toc": toc,
        "stats": {
            "total_actionable": total_actionable,
            "total_guidance": total_guidance,
            "total_sections": len(sections),
        },
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


def _select_sheet_config(entry: dict) -> dict:
    """从 audit entry 中选出主数据 sheet 配置.

    优先返回 checklist-table 类型；跳过 component_type 为 'skip' / 'example-skip'
    的 sheet（如 GT_Custom、示例 sheet）。
    """
    sheets = entry.get("sheets", [])
    _skip = {"skip", "example-skip"}
    for sheet in sheets:
        if isinstance(sheet, dict) and sheet.get("component_type") == "checklist-table":
            return sheet
    # 退化：返回首个非 skip sheet
    for sheet in sheets:
        if isinstance(sheet, dict) and sheet.get("component_type") not in _skip:
            return sheet
    return sheets[0] if sheets else {}


def _parse_objective_section(ws, obj_cfg: dict) -> dict:
    """解析审计目标节 → 只读 header items（无填写列）."""
    section_id = "S01"
    title = obj_cfg.get("title", "一、审计目标")
    items: list[dict] = []

    # audit JSON 直接登记了每条的 row + text；以实物单元格内容为准（B 列），
    # 文本缺失时回退到 audit JSON 的 text_preview。
    for idx, cfg_item in enumerate(obj_cfg.get("items", []), start=1):
        row = cfg_item.get("row")
        content = ""
        if row:
            content = _cell_str(ws, _DEFAULT_CONTENT_COL, row)
        if not content:
            content = cfg_item.get("text_preview", "") or cfg_item.get("text", "")
        if not content:
            continue
        seq = cfg_item.get("seq")
        seq_str = "" if seq is None else str(seq)
        items.append({
            "id": f"{section_id}-{idx:03d}",
            "type": "header",
            "standard_ref": seq_str,
            "content": content,
            "children": [],
        })

    return {"id": section_id, "title": title, "items": items}


def _parse_procedure_section(ws, proc_cfg: dict, wp_code: str) -> dict:
    """解析核对程序节 → actionable items（带 conclusion 填写列）."""
    section_id = "S02"
    title = proc_cfg.get("title", "二、核对程序")
    items: list[dict] = []

    # 列角色一律从 audit JSON column_roles 动态读取，不硬编码列字母。
    # 各核对表列位置不同（A17-5-1 参考在 G，A17-5-2 在 H，A17-5-3/4/5 无参考列），
    # A17-5-4 多一个「公开转让书披露章节」(disclosure_chapter) 列。
    roles = proc_cfg.get("column_roles", {})
    ref_col = roles.get("index_reference")  # 预置底稿索引号参考列（可能不存在）
    disc_col = roles.get("disclosure_chapter")  # 披露章节列（仅 A17-5-4）

    for cfg_item in proc_cfg.get("items", []):
        row = cfg_item.get("row")
        item_id = cfg_item.get("item_id")
        if not row or not item_id:
            continue

        # 内容以实物 B 列为准，缺失回退 content_preview。
        content = _cell_str(ws, _DEFAULT_CONTENT_COL, row)
        if not content:
            content = cfg_item.get("content_preview") or ""

        # 末行「项目负责经理确认：…」一类签字行（seq_label 是长句、content 为空）
        # 仍作为 actionable 保留（用户可标 conclusion），但内容取 seq_label 兜底。
        if not content:
            content = cfg_item.get("seq_label") or ""
        if not content:
            continue

        # 预置的底稿索引号参考 → wp_ref 默认值。仅当 audit JSON 登记了 index_reference
        # 列角色时才读实物，否则回退 audit JSON 的 preset_index_reference（多为空）。
        preset_ref = ""
        if ref_col:
            preset_ref = _cell_str(ws, ref_col, row)
        if not preset_ref:
            preset_ref = cfg_item.get("preset_index_reference", "")

        item: dict[str, Any] = {
            "id": item_id,
            "type": "actionable",
            "standard_ref": str(
                cfg_item.get("seq_label") or cfg_item.get("seq_no") or ""
            ),
            "content": content,
            "preset_wp_ref": preset_ref,
            "children": [],
        }

        # A17-5-4 特有：公开转让书披露章节列 → 预置 disclosure_chapter（可空）。
        if disc_col:
            item["preset_disclosure_chapter"] = _cell_str(ws, disc_col, row)

        items.append(item)

    return {"id": section_id, "title": title, "items": items}


# ─── 分章节问卷解析（A15-1 持续经营调查表） ─────────────────────────────────


# 章节标签关键字 → item_id 前缀（对齐 persistence.md fin/ops/oth）。
_A15_SECTION_PREFIX = [
    ("财务", "fin"),
    ("经营", "ops"),
    ("其他", "oth"),
]


def _a15_section_prefix(label: str, positional_idx: int) -> str:
    """根据章节标签关键字（财务/经营/其他）映射 item_id 前缀；缺省按序回退。"""
    for keyword, prefix in _A15_SECTION_PREFIX:
        if keyword in label:
            return prefix
    # 回退：按非结论章节出现顺序取 fin/ops/oth
    fallback = ["fin", "ops", "oth"]
    return fallback[positional_idx] if positional_idx < len(fallback) else f"sec{positional_idx + 1}"


def _parse_sectioned_checklist(
    file_path: Path, wp_code: str, entry: dict, sheet_cfg: dict
) -> dict:
    """解析「分章节问卷」结构（A15-1）.

    audit JSON `sections` 给出每节锚点行与标签；带 `type=="conclusion"` 的为结论节。
    每节数据行：col A=序号（数字）、col B=条目内容、col D=是否存在（conclusion 填写列）、
    col E=说明（remark）。重复表头行（col A=="序号"）跳过。

    item_id 模式（对齐 persistence.md）：
    - 财务 `A15-1-fin-{nn}` / 经营 `A15-1-ops-{nn}` / 其他 `A15-1-oth-{nn}`
    - 结论 `A15-1-conclusion`（单条）
    """
    cfg_sections = sorted(sheet_cfg.get("sections", []), key=lambda s: s.get("row", 0))
    max_row = sheet_cfg.get("max_row", 0)
    cols = {c.get("label", ""): c.get("col") for c in sheet_cfg.get("columns", [])}
    # 列角色：是否存在 → conclusion 填写列；说明 → remark 列。
    concl_col = cols.get("是否存在", "D")
    remark_col = cols.get("说明", "E")

    wb = openpyxl.load_workbook(str(file_path), data_only=True, read_only=True)
    sections: list[dict] = []
    try:
        ws = wb[sheet_cfg["name"]] if sheet_cfg.get("name") in wb.sheetnames else wb.active

        # 计算每节的行区间 [start, end)。
        non_conclusion_idx = 0
        for i, sec in enumerate(cfg_sections):
            start = sec.get("row", 0) + 1
            # 下一节锚点行即本节终点；末节延伸到 max_row。
            end = (
                cfg_sections[i + 1].get("row", max_row + 1)
                if i + 1 < len(cfg_sections)
                else max_row + 1
            )
            label = sec.get("label", "").strip()
            is_conclusion = sec.get("type") == "conclusion"

            if is_conclusion:
                # 结论节：可能跨多个 conclusion 锚点行（A15-1 有 row32 标签 + row33 问句）。
                # 仅在首个 conclusion 锚点处建一条 A15-1-conclusion，避免重复。
                if any(
                    s.get("type") == "conclusion" and s.get("row", 0) < sec.get("row", 0)
                    for s in cfg_sections
                ):
                    continue
                conclusion_section = _build_a15_conclusion_section(
                    ws, wp_code, cfg_sections, max_row
                )
                if conclusion_section["items"]:
                    sections.append(conclusion_section)
                continue

            prefix = _a15_section_prefix(label, non_conclusion_idx)
            non_conclusion_idx += 1
            section_id = f"S{len(sections) + 1:02d}"
            items: list[dict] = []
            seq_counter = 0
            for row in range(start, end):
                seq_val = _cell_str(ws, _DEFAULT_SEQ_COL, row)
                content = _cell_str(ws, _DEFAULT_CONTENT_COL, row)
                # 跳过重复表头行（序号列内容为"序号"）与空行。
                if not content or seq_val == "序号":
                    continue
                if not seq_val.isdigit():
                    # 非数字序号且无内容关联 → 视为标签/空行跳过
                    continue
                seq_counter += 1
                items.append({
                    "id": f"{wp_code}-{prefix}-{seq_counter:02d}",
                    "type": "actionable",
                    "standard_ref": seq_val,
                    "content": content,
                    "conclusion_col": concl_col,
                    "remark_col": remark_col,
                    "children": [],
                })
            sections.append({"id": section_id, "title": label, "items": items})
    finally:
        wb.close()

    toc = [{"id": s["id"], "title": s["title"], "applicable": None} for s in sections]
    total_actionable = sum(
        1 for sec in sections for it in sec["items"] if it["type"] == "actionable"
    )

    return {
        "wp_code": wp_code,
        "title": _extract_title(wp_code, entry),
        "mode": "sectioned-checklist",
        "sections": sections,
        "toc": toc,
        "stats": {
            "total_actionable": total_actionable,
            "total_guidance": 0,
            "total_sections": len(sections),
        },
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_a15_conclusion_section(
    ws, wp_code: str, cfg_sections: list[dict], max_row: int
) -> dict:
    """构建 A15-1 调查结论节（单条 actionable，item_id=A15-1-conclusion）.

    结论问句取最后一个 conclusion 锚点行的标签（如「审计程序是否识别出…」）；
    若仅一个 conclusion 锚点则用其标签。
    """
    conclusion_rows = [s for s in cfg_sections if s.get("type") == "conclusion"]
    # 标题用首个 conclusion 锚点（"调查结论："）。
    title = conclusion_rows[0].get("label", "调查结论").rstrip("：:").strip()
    # 问句内容：优先最后一个 conclusion 锚点的标签（实际问句行）。
    question = conclusion_rows[-1].get("label", "").strip()
    if len(conclusion_rows) == 1:
        # 仅一个锚点时尝试读其下一行作为问句。
        row = conclusion_rows[0].get("row", 0) + 1
        cell = _cell_str(ws, _DEFAULT_SEQ_COL, row) or _cell_str(
            ws, _DEFAULT_CONTENT_COL, row
        )
        if cell:
            question = cell
    items = [{
        "id": f"{wp_code}-conclusion",
        "type": "actionable",
        "standard_ref": "",
        "content": question or title,
        "conclusion_col": None,
        "remark_col": None,
        "children": [],
    }]
    return {"id": "S99", "title": title, "items": items}


# ─── bundle 单节调查问卷解析（A11-2 / A11-3） ────────────────────────────────


def _parse_bundle_questionnaire(
    file_path: Path, wp_code: str, parent_entry: dict, sheet_cfg: dict
) -> dict:
    """解析 bundle 内的单节调查问卷 sheet（A11-2 / A11-3）.

    这些 wp_code 不是独立 xlsx，而是父 bundle（`A11 期后事项程序表.xlsx`）内的
    某个 sheet（期后事项调查问卷 / 期后内控事项调查问卷）。结构为单节问卷：
    - col A=序号（仅数字行作 actionable）、col B=调查内容、
      col D=适用情况（conclusion 填写列）、col F=简要说明（remark）。
    - 引导句行（如「在资产负债表日至…止，贵公司」，A 列空/非数字）、
      落款行（被调查人/日期/*注）等 **非 actionable**，跳过。

    item_id 模式：`{wp_code}-{seq:02d}`（如 A11-2-01..13、A11-3-01..06），
    对齐 persistence.md。输出复用单节 checklist 形态（sections/toc/stats）。
    """
    sheet_name = (sheet_cfg.get("name") or "").strip()
    cols = {c.get("label", ""): c.get("col") for c in sheet_cfg.get("columns", [])}
    # 列角色：适用情况 → conclusion 填写列；简要说明 → remark 列。
    concl_col = cols.get("适用情况", "D")
    remark_col = cols.get("简要说明", "F")
    max_row = sheet_cfg.get("max_row", 0)
    header_row = sheet_cfg.get("header_row", 5)

    wb = openpyxl.load_workbook(str(file_path), data_only=True, read_only=True)
    items: list[dict] = []
    try:
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

        seq_counter = 0
        # 数据行从表头行之后开始扫描到 max_row。
        for row in range(header_row + 1, max_row + 1):
            seq_val = _cell_str(ws, _DEFAULT_SEQ_COL, row)
            content = _cell_str(ws, _DEFAULT_CONTENT_COL, row)
            # 仅 A 列为数字序号的行作 actionable；引导句/落款/注释行跳过。
            if not seq_val.isdigit():
                continue
            if not content:
                continue
            seq_counter += 1
            items.append({
                "id": f"{wp_code}-{seq_counter:02d}",
                "type": "actionable",
                "standard_ref": seq_val,
                "content": content,
                "conclusion_col": concl_col,
                "remark_col": remark_col,
                "children": [],
            })
    finally:
        wb.close()

    section = {"id": "S01", "title": sheet_name or wp_code, "items": items}
    toc = [{"id": section["id"], "title": section["title"], "applicable": None}]

    return {
        "wp_code": wp_code,
        "title": sheet_name or _extract_title(wp_code, parent_entry),
        "mode": "checklist",
        "bundle_parent": parent_entry.get("wp_code"),
        "bundle_sheet": sheet_name,
        "sections": [section],
        "toc": toc,
        "stats": {
            "total_actionable": len(items),
            "total_guidance": 0,
            "total_sections": 1,
        },
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── 动态行 grid 解析（A14-1 内部控制缺陷汇总表） ───────────────────────────


# 认定子列（col → remark.assertions 键）。顺序与 columns_sub G/H/I/J/K/L 一致。
_A14_ASSERTION_KEYS = {
    "存在/发生": "existence",
    "完整性": "completeness",
    "截止": "cutoff",
    "权利和义务": "rights_obligations",
    "计价和分摊/准确性": "valuation_allocation",
    "列报": "presentation",
}

# 主列 label → remark JSON 字段（persistence.md A14-1 固定 schema）。
_A14_MAIN_FIELD = {
    "缺陷编号": "defect_no",
    "相关业务流程、应用系统": "process",
    "内部控制缺陷描述及影响": "description",
    "补偿性控制": "compensating_control",
}


def _parse_grid(file_path: Path, wp_code: str, entry: dict, sheet_cfg: dict) -> dict:
    """解析「动态行 grid」结构（A14-1 内部控制缺陷汇总表）.

    双行表头（R5 主表头 + R6 子表头），认定 6 列矩阵 G/H/I/J/K/L。按 persistence.md：
    认定 6 列 → remark JSON 固定 schema，不拆列 item_id；行模板 item_id `A14-1-row-{nnn}`。

    输出 `mode="grid"`，前端据此渲染动态行 grid（区别于 checklist 两节/分章节）。
    不强套两节解析。`example-skip` 示例 sheet 已在 `_select_sheet_config` 跳过。
    """
    columns_main = sheet_cfg.get("columns_main", [])
    columns_sub = sheet_cfg.get("columns_sub", [])

    # 认定矩阵子列 → 有序 assertion 列表。
    assertion_cols = [c.get("col") for c in columns_sub]
    assertions = []
    for c in columns_sub:
        label = c.get("label", "")
        key = _A14_ASSERTION_KEYS.get(label) or _slugify_assertion(label)
        assertions.append({"col": c.get("col"), "label": label, "key": key})

    # 主列：认定列（columns_sub 所在的 G）展开为子列；其余作为普通列。
    assertion_anchor = assertion_cols[0] if assertion_cols else None
    grid_columns: list[dict] = []
    for col in columns_main:
        col_letter = col.get("col")
        label = col.get("label", "")
        field = _A14_MAIN_FIELD.get(label)
        entry_col: dict[str, Any] = {"col": col_letter, "label": label}
        if field:
            entry_col["remark_field"] = field
        # 财务报表认定主列 → 标记为认定矩阵锚点（展开子列）。
        # 仅匹配子列锚点列字母或精确「财务报表认定」标签，避免误命中「缺陷认定结论」等含"认定"列。
        if col_letter == assertion_anchor or label == "财务报表认定":
            entry_col["is_assertion_matrix"] = True
            entry_col["assertions"] = assertions
        grid_columns.append(entry_col)

    # remark JSON 固定 schema（persistence.md）。
    remark_schema = {
        "defect_no": "string",
        "process": "string",
        "description": "string",
        "assertions": {a["key"]: "Y|N|NA" for a in assertions},
        "compensating_control": "string",
    }

    # 跳过的示例 sheet 名（如有）。
    example_sheets = [
        s.get("name")
        for s in entry.get("sheets", [])
        if isinstance(s, dict) and s.get("component_type") == "example-skip"
    ]

    grid = {
        "header_row": sheet_cfg.get("header_row"),
        "sub_header_row": sheet_cfg.get("sub_header_row"),
        "columns": grid_columns,
        "assertions": assertions,
        "remark_schema": remark_schema,
        "row_id_pattern": f"{wp_code}-row-{{nnn}}",
        "row_id_prefix": f"{wp_code}-row-",
        "example_sheets_skipped": example_sheets,
        "footnotes": [
            f.get("text_preview", "") for f in sheet_cfg.get("footnotes", [])
        ],
    }

    return {
        "wp_code": wp_code,
        "title": _extract_title(wp_code, entry),
        "mode": "grid",
        "grid": grid,
        # grid 模式无固定 checklist 章节；保持字段存在以兼容前端通用消费。
        "sections": [],
        "toc": [],
        "stats": {
            "total_actionable": 0,
            "total_guidance": 0,
            "total_sections": 0,
        },
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


def _slugify_assertion(label: str) -> str:
    """认定子列 label → 安全 key（未在映射表中时的兜底）。"""
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", label).strip("_").lower()
    return slug or "assertion"


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────


def _cell_str(ws, col: str, row: int) -> str:
    """读取单元格字符串内容（去空白）；空/None 返回空串."""
    try:
        value = ws[f"{col}{row}"].value
    except Exception:  # noqa: BLE001
        return ""
    if value is None:
        return ""
    return str(value).strip()


def _extract_title(wp_code: str, entry: dict) -> str:
    """从 audit entry / 文件名提取核对表标题."""
    filename = entry.get("filename", "")
    if filename:
        stem = Path(filename).stem
        # 去掉 wp_code 前缀
        title = re.sub(rf"^{re.escape(wp_code)}\s*", "", stem).strip()
        if title:
            return title
    return "审计工作完成核对表"


def invalidate_cache(wp_code: str | None = None) -> None:
    """手动清除缓存（用于测试或强制刷新）."""
    global _AUDIT_CONFIG_CACHE
    if wp_code:
        _CHECKLIST_XLSX_CACHE.pop(wp_code, None)
    else:
        _CHECKLIST_XLSX_CACHE.clear()
    _AUDIT_CONFIG_CACHE = None


# ─── render-config 集成辅助（2026-06-18 补） ──────────────────────────────────


def is_xlsx_checklist(wp_code: str) -> bool:
    """判断 wp_code 是否属于 xlsx 核对表（有 audit JSON 配置或模板文件存在）.

    render-config 用此函数决定调 xlsx parser 还是 docx parser。
    """
    # 有 audit 配置 → xlsx 核对表
    if _get_audit_entry(wp_code) is not None:
        return True
    # bundle 子码（A11-2/A11-3）
    if _find_bundle_sheet(wp_code) is not None:
        return True
    # 模板文件存在
    return get_template_path(wp_code) is not None


# 别名：render-config 导入兼容
get_checklist_xlsx_template = get_checklist_template
