#!/usr/bin/env python3
"""A 循环（报表/调整）域扫描器 — Foundation spec 任务 1。

实现域切分：按 wp_code_patterns[0] 首字母切 46 = A20/B10/C1/S10/无码5。
实现 strict 域四路取并（目录段 / ^(?:use|Gt)?A\\d / ^a\\d 小写 / ^a\\d+-）。
行身份六族分类、mode 门控三层递归回溯、docx/xlsx format 分流等。

用法::

    ..\\.venv\\Scripts\\python.exe backend/scripts/analyze/a_cycle_scanner.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

try:
    import openpyxl
except ImportError:
    print("ERROR: pip install openpyxl")
    sys.exit(1)

try:
    import docx as python_docx  # python-docx
except ImportError:
    python_docx = None  # type: ignore[assignment]

# ════════════════════════════════════════════════════════════════════════════
# 路径
# ════════════════════════════════════════════════════════════════════════════
ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
TEMPLATE_DIR = BACKEND / "wp_templates" / "A"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
SLICE_PATH = DATA / "workpaper_sync_abcs_cycle_manifest_slice.json"
DELETION_PLAN_PATH = DATA / "workpaper_sync_abcs_cycle_deletion_plan.json"

# ════════════════════════════════════════════════════════════════════════════
# 注释剥离（保留行号）
# ════════════════════════════════════════════════════════════════════════════
_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*|<!--.*?-->", re.S)


def _blank_keep_newlines(match: re.Match[str]) -> str:
    """把注释替换为等长空白，保留换行符以维持行号一致。"""
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_comments(source: str) -> str:
    """剥注释但保留行号（同长空白替换，禁删行式）。"""
    return _COMMENT_RE.sub(_blank_keep_newlines, source)


# ════════════════════════════════════════════════════════════════════════════
# 载入 slice / deletion_plan
# ════════════════════════════════════════════════════════════════════════════

def load_slice() -> dict:
    return json.loads(SLICE_PATH.read_bytes())


def load_deletion_plan() -> dict:
    return json.loads(DELETION_PLAN_PATH.read_bytes())


# ════════════════════════════════════════════════════════════════════════════
# 域切分：46 → A20 / B10 / C1 / S10 / 无码5
# ════════════════════════════════════════════════════════════════════════════

def domain_split(entries: list[dict]) -> dict[str, list[dict]]:
    """按 wp_code_patterns[0] 首字母分域。

    🔴 禁按 entry_id 猜域 —— gt-c-control-test 的 wp_code_patterns 是空数组。
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        patterns = e.get("wp_code_patterns", [])
        if not patterns:
            buckets["pattern_less"].append(e)
        else:
            letter = patterns[0][0].upper()
            buckets[letter].append(e)
    return dict(buckets)


def a_domain_entries(entries: list[dict]) -> list[dict]:
    """提取 A 域 20 条 entry。"""
    split = domain_split(entries)
    return split.get("A", [])


# ════════════════════════════════════════════════════════════════════════════
# strict 域文件集：四路取并（AC-5）
# ════════════════════════════════════════════════════════════════════════════

# 大写文件名：^(use|Gt)?A\d…
_UPPER_RE = re.compile(r"^(?:use|Gt)?A\d")
# 🔴 小写前缀：^a\d… —— 仅大写漏 34 个
_LOWER_RE = re.compile(r"^a\d")
# componentType 式：^a\d+-
_CT_RE = re.compile(r"^a\d+-")


def is_a_domain_file(path: Path) -> bool:
    """判断给定前端文件是否属于 A 域（strict 四路取并）。

    四路：
    1. 路径含 /a{n}/ 或 /a{n}-{m}/ 目录段
    2. 文件名匹配 ^(use|Gt)?A\\d（大写）
    3. 文件名匹配 ^a\\d（小写）
    4. 文件名匹配 ^a\\d+-（componentType 式）
    """
    rel = path.relative_to(WP_COMPONENTS).as_posix() if path.is_relative_to(WP_COMPONENTS) else ""
    # 路径 1：目录段 /a{digit}/
    if re.search(r"/a\d+(?:-\d+)?/", rel):
        return True
    name = path.name
    # 路径 2：大写前缀
    if _UPPER_RE.match(name):
        return True
    # 路径 3：小写前缀
    if _LOWER_RE.match(name):
        return True
    # 路径 4：componentType 式
    if _CT_RE.match(name):
        return True
    return False


def is_a_domain_file_upper_only(path: Path) -> bool:
    """仅大写分支的域判定——用于变异证明（应漏 34 个）。"""
    rel = path.relative_to(WP_COMPONENTS).as_posix() if path.is_relative_to(WP_COMPONENTS) else ""
    if re.search(r"/a\d+(?:-\d+)?/", rel):
        return True
    name = path.name
    if _UPPER_RE.match(name):
        return True
    return False


def scan_a_domain_files(*, include_tests: bool = False) -> tuple[list[Path], list[Path]]:
    """扫描 A 域全部前端文件，返回 (生产文件, 测试文件)。"""
    prod, test = [], []
    for p in sorted(WP_COMPONENTS.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix not in (".vue", ".ts", ".tsx", ".js"):
            continue
        if not is_a_domain_file(p):
            continue
        if "__tests__" in p.parts or p.name.endswith((".spec.ts", ".test.ts")):
            test.append(p)
        else:
            prod.append(p)
    if include_tests:
        return prod, test
    return prod, test


def scan_a_domain_files_upper_only(*, include_tests: bool = False) -> tuple[list[Path], list[Path]]:
    """仅大写分支——用于变异证明。"""
    prod, test = [], []
    for p in sorted(WP_COMPONENTS.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix not in (".vue", ".ts", ".tsx", ".js"):
            continue
        if not is_a_domain_file_upper_only(p):
            continue
        if "__tests__" in p.parts or p.name.endswith((".spec.ts", ".test.ts")):
            test.append(p)
        else:
            prod.append(p)
    return prod, test


# ════════════════════════════════════════════════════════════════════════════
# 门控判据：祖先链 × 递归 v-else 链头回溯（AC-13）
# ════════════════════════════════════════════════════════════════════════════

MODE_RE = re.compile(r"\b\w*[Mm]ode\b")


class _VueGateParser(HTMLParser):
    """解析 Vue SFC <template> 部分的元素属性，追踪父子/兄弟关系。

    🔴 关键设计：对每个节点入栈时保存其所在层的兄弟列表快照，
    这样在回溯祖先的 v-else 链头时能访问到正确的兄弟上下文。
    """

    def __init__(self, target_tag: str = "GtOnlyOfficeSheet") -> None:
        super().__init__()
        self.target_tag = target_tag
        # stack: [{tag, attrs, siblings_at_entry}] —— siblings_at_entry 是入栈时兄弟列表的引用
        self._stack: list[dict] = []
        # 每层维护一个兄弟列表（栈式）
        self._sibling_stack: list[list[dict]] = [[]]
        self.mounts: list[dict] = []

    def _attrs_dict(self, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {k: (v or "") for k, v in attrs}

    @staticmethod
    def _chain_head_in(attrs: dict, siblings: list[dict]) -> dict | None:
        """对 v-else / v-else-if 节点，在给定兄弟列表中回溯链头的 v-if。"""
        if "v-else" not in attrs and "v-else-if" not in attrs:
            return None
        for prev in reversed(siblings):
            if prev is attrs:
                continue  # 跳过自身
            if "v-if" in prev:
                return prev
        return None

    def _effective_conds_with_siblings(self, attrs: dict, siblings: list[dict]) -> list[str]:
        """节点的有效条件：自身 v-*/: 绑定 + 链头 v-if 值。"""
        conds = [v for k, v in attrs.items() if k.startswith((":", "v-")) and v]
        head = self._chain_head_in(attrs, siblings)
        if head and "v-if" in head:
            conds.append(head["v-if"])
        return conds

    def _record(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = self._attrs_dict(attrs_list)
        # 记录到当前层兄弟列表
        current_siblings = self._sibling_stack[-1] if self._sibling_stack else []
        current_siblings.append(attrs)

        if tag.lower() == self.target_tag.lower() or tag == self.target_tag:
            # 收集自身条件（在当前兄弟层）
            self_conds = self._effective_conds_with_siblings(attrs, current_siblings)
            # 收集全部祖先的条件（每个祖先用其入栈时保存的兄弟列表）
            ancestor_conds: list[str] = []
            for anc in self._stack:
                anc_attrs = anc["attrs"]
                anc_siblings = anc["siblings_at_entry"]
                ancestor_conds.extend(
                    self._effective_conds_with_siblings(anc_attrs, anc_siblings)
                )
            all_conds = ancestor_conds + self_conds
            has_mode = any(MODE_RE.search(c) for c in all_conds)
            self.mounts.append({
                "tag": tag,
                "attrs": attrs,
                "ancestor_conds": ancestor_conds,
                "self_conds": self_conds,
                "has_mode_gate": has_mode,
            })

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(tag, attrs)
        cur_attrs = self._attrs_dict(attrs)
        # 入栈时保存当前层兄弟列表的引用（此时 attrs 已在列表中）
        current_siblings = self._sibling_stack[-1] if self._sibling_stack else []
        self._stack.append({
            "tag": tag,
            "attrs": cur_attrs,
            "siblings_at_entry": list(current_siblings),  # 快照
        })
        # 新建子层兄弟列表
        self._sibling_stack.append([])

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1]["tag"].lower() == tag.lower():
            self._stack.pop()
            if len(self._sibling_stack) > 1:
                self._sibling_stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(tag, attrs)


def parse_oo_mounts(source: str) -> list[dict]:
    """解析 Vue SFC 中 GtOnlyOfficeSheet 挂点的门控状态。"""
    # 取 <template> 区域
    m = re.search(r"<template\b[^>]*>(.*)</template>", source, re.S)
    if not m:
        return []
    template_text = m.group(1)
    parser = _VueGateParser("GtOnlyOfficeSheet")
    parser.feed(template_text)
    return parser.mounts


def parse_oo_mounts_self_only(source: str) -> list[dict]:
    """只看挂点自身属性的门控（版本 1，用于变异证明）。"""
    m = re.search(r"<template\b[^>]*>(.*)</template>", source, re.S)
    if not m:
        return []
    template_text = m.group(1)
    results = []
    for match in re.finditer(
        r"<GtOnlyOfficeSheet\b([^>]*)(?:/>|>)", template_text, re.S | re.I
    ):
        attr_str = match.group(1)
        has_mode = bool(MODE_RE.search(attr_str))
        results.append({"has_mode_gate": has_mode, "method": "self_only"})
    return results


# ════════════════════════════════════════════════════════════════════════════
# mode 载体二分（AC-41）
# ════════════════════════════════════════════════════════════════════════════

def classify_mode_carrier(source: str) -> str | None:
    """判定 modeOptions 的形态：'string_array' / 'object_array' / None。"""
    stripped = strip_comments(source)
    # 形态 2：对象数组（{label, value}）
    if re.search(r"modeOptions\s*[:=].*?\[\s*\{", stripped, re.S):
        return "object_array"
    # 形态 1：字符串数组
    if re.search(r"modeOptions\s*[:=].*?\[\s*['\"]", stripped, re.S):
        return "string_array"
    return None


# ════════════════════════════════════════════════════════════════════════════
# 权威册 format 分流（AC-38）
# ════════════════════════════════════════════════════════════════════════════

def scan_a_templates() -> dict[str, Any]:
    """扫描 A 目录权威册，返回 xlsx/docx/无册 分类统计。"""
    result: dict[str, Any] = {
        "all_files": [],
        "xlsx_files": [],
        "docx_files": [],
        "xlsx_count": 0,
        "docx_count": 0,
        "total_count": 0,
    }
    if not TEMPLATE_DIR.exists():
        return result

    for p in sorted(TEMPLATE_DIR.rglob("*")):
        if not p.is_file():
            continue
        if p.name.startswith("~$"):
            continue
        result["all_files"].append(p)
        if p.suffix.lower() in (".xlsx", ".xlsm"):
            result["xlsx_files"].append(p)
        elif p.suffix.lower() in (".docx", ".doc"):
            result["docx_files"].append(p)
    result["xlsx_count"] = len(result["xlsx_files"])
    result["docx_count"] = len(result["docx_files"])
    result["total_count"] = len(result["all_files"])
    return result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def scan_xlsx_formulas(xlsx_path: Path) -> dict[str, Any]:
    """扫描 xlsx 册的公式格和 definedName。"""
    wb = openpyxl.load_workbook(str(xlsx_path), data_only=False)
    sheets_info = []
    total_fx = 0
    fx_sheets = 0
    for ws in wb.worksheets:
        fx_count = 0
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("=") and len(cell.value) > 1:
                    fx_count += 1
        sheets_info.append({
            "name": ws.title,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "formula_count": fx_count,
            "hidden": ws.sheet_state != "visible",
        })
        total_fx += fx_count
        if fx_count > 0:
            fx_sheets += 1

    # definedName
    dn_list = list(wb.defined_names)
    dn_total = len(dn_list)
    broken = 0
    for dn_name in dn_list:
        try:
            dn = wb.defined_names[dn_name]
            val = dn.attr_text if hasattr(dn, "attr_text") else str(dn.value if hasattr(dn, "value") else "")
            if "#REF!" in val or not val:
                broken += 1
        except Exception:
            broken += 1

    wb.close()
    return {
        "sheets": sheets_info,
        "total_formulas": total_fx,
        "fx_sheet_count": fx_sheets,
        "sheet_count": len(sheets_info),
        "defined_names_total": dn_total,
        "defined_names_broken": broken,
    }


def scan_xlsx_footer_raw_xml(xlsx_path: Path) -> list[dict]:
    """用 raw XML 读取 footer（禁用 openpyxl ws.oddFooter）。"""
    results = []
    with zipfile.ZipFile(str(xlsx_path)) as z:
        sheet_files = sorted(
            n for n in z.namelist()
            if re.match(r"xl/worksheets/sheet\d+\.xml$", n)
        )
        for sf in sheet_files:
            xml_text = z.read(sf).decode("utf-8")
            has_container = "<headerFooter" in xml_text
            odd_footer_matches = re.findall(r"<oddFooter>(.*?)</oddFooter>", xml_text, re.S)
            results.append({
                "sheet_file": sf,
                "has_header_footer_container": has_container,
                "odd_footer_values": odd_footer_matches,
            })
    return results


# ════════════════════════════════════════════════════════════════════════════
# docx 册扫描（AC-39，合并单元格去重）
# ════════════════════════════════════════════════════════════════════════════

def scan_docx_structure(docx_path: Path) -> dict[str, Any]:
    """用 python-docx 扫描 docx 结构：表格/段落/合并单元格。"""
    if python_docx is None:
        return {"error": "python-docx not installed"}
    doc = python_docx.Document(str(docx_path))
    tables_info = []
    total_cells = 0
    total_merged = 0
    for tbl in doc.tables:
        cell_count = 0
        unique_tc_ids: set[int] = set()
        for row in tbl.rows:
            for cell in row.cells:
                cell_count += 1
                unique_tc_ids.add(id(cell._tc))
        merged = cell_count - len(unique_tc_ids)
        tables_info.append({
            "rows": len(tbl.rows),
            "cols": len(tbl.columns),
            "cell_count": cell_count,
            "unique_tc_count": len(unique_tc_ids),
            "merged_refs": merged,
            "merged_pct": round(merged / cell_count * 100, 1) if cell_count > 0 else 0.0,
        })
        total_cells += cell_count
        total_merged += merged

    paragraphs = [p.text for p in doc.paragraphs]
    non_empty_paras = [p for p in paragraphs if p.strip()]
    sections = len(doc.sections)

    return {
        "tables": tables_info,
        "table_count": len(tables_info),
        "total_cells": total_cells,
        "total_merged": total_merged,
        "merged_pct": round(total_merged / total_cells * 100, 1) if total_cells > 0 else 0.0,
        "paragraph_count": len(paragraphs),
        "non_empty_paragraph_count": len(non_empty_paras),
        "section_count": sections,
        "first_paragraph": paragraphs[0] if paragraphs else "",
    }


# ════════════════════════════════════════════════════════════════════════════
# 写路径 / 端点扫描
# ════════════════════════════════════════════════════════════════════════════

def scan_endpoint_literals(files: list[Path]) -> dict[str, Any]:
    """扫描前端文件中的端点字面量命中。"""
    patterns = {
        "publish_to_tb": re.compile(r"publish-to-tb"),
        "trial_balance_writeback": re.compile(r"trial-balance/writeback"),
        "checklist_responses": re.compile(r"/checklist-responses"),
        "field_overrides": re.compile(r"/field-overrides|/api/workpapers/field-overrides"),
        "custom_cells": re.compile(r"/custom-cells"),
        "confirm": re.compile(r"ElMessageBox\.confirm"),
        "health": re.compile(r"/api/onlyoffice/health|/health"),
    }
    results: dict[str, dict] = {k: {"count": 0, "files": []} for k in patterns}

    for f in files:
        try:
            text = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for name, pat in patterns.items():
            hits = pat.findall(text)
            if hits:
                results[name]["count"] += len(hits)
                results[name]["files"].append(str(f))

    return results


# ════════════════════════════════════════════════════════════════════════════
# 结构性零扫描
# ════════════════════════════════════════════════════════════════════════════

def scan_structural_zeros(files: list[Path]) -> dict[str, int]:
    """扫描 A 域结构性零项（23 项）。"""
    patterns = {
        "trial_balance_writeback": re.compile(r"trial-balance/writeback"),
        "ref_dead_formula": re.compile(r"#REF!"),
        "onlyoffice_literal": re.compile(r"'onlyoffice'|\"onlyoffice\""),
        "removeRow": re.compile(r"\bremoveRow\b"),
        "useChecklistPersistence": re.compile(r"\buseChecklistPersistence\b"),
        "contract_ocr": re.compile(r"contract-ocr"),
        "onlyoffice_config": re.compile(r"onlyoffice-config"),
        "useAdjustmentCentralSync": re.compile(r"\buseAdjustmentCentralSync\b"),
        "http_put": re.compile(r"\bhttp\.put\b"),
        "api_put": re.compile(r"\bapi\.put\b"),
        "useWpDualMode": re.compile(r"\buseWpDualMode\b"),
        "useWorkpaperEntryDualMode": re.compile(r"\buseWorkpaperEntryDualMode\b"),
        "GtEntrySyncCapabilityNotice": re.compile(r"\bGtEntrySyncCapabilityNotice\b"),
    }
    counts: dict[str, int] = {k: 0 for k in patterns}
    for f in files:
        try:
            text = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for name, pat in patterns.items():
            counts[name] += len(pat.findall(text))
    return counts


# ════════════════════════════════════════════════════════════════════════════
# import 闭包（深度 3）
# ════════════════════════════════════════════════════════════════════════════

_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|"""
    r"""(?:require|import)\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.S,
)


def resolve_import(spec: str, importer: Path) -> Path | None:
    """解析相对 import 路径。"""
    if not spec.startswith("."):
        return None
    base = importer.parent / spec
    for ext in ("", ".ts", ".vue", ".tsx", ".js", "/index.ts", "/index.vue"):
        candidate = base.parent / (base.name + ext) if ext else base
        if candidate.exists():
            return candidate.resolve()
    return None


def import_closure(host_path: Path, maxdepth: int = 3) -> list[Path]:
    """收集宿主的 import 闭包（深度 3）。"""
    visited: set[Path] = {host_path.resolve()}
    frontier = [host_path.resolve()]
    for _ in range(maxdepth):
        next_frontier = []
        for fp in frontier:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in _IMPORT_RE.finditer(text):
                spec = m.group(1) or m.group(2)
                resolved = resolve_import(spec, fp)
                if resolved and resolved not in visited:
                    visited.add(resolved)
                    next_frontier.append(resolved)
        frontier = next_frontier
    return sorted(visited)


def channel_of_host(host_path: Path) -> str:
    """通过 import 闭包检测宿主的持久化通道。"""
    closure = import_closure(host_path)
    channels = []
    for fp in closure:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "/checklist-responses" in text:
            channels.append("checklist_responses")
        if "/field-overrides" in text or "/api/workpapers/field-overrides" in text:
            channels.append("field_overrides")
        if "/custom-cells" in text:
            channels.append("custom_cells")
    # 去重并排序
    seen: set[str] = set()
    unique = []
    for c in channels:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return "+".join(unique) if unique else "unknown"


# ════════════════════════════════════════════════════════════════════════════
# 归档区扫描（AC-25）
# ════════════════════════════════════════════════════════════════════════════

def scan_archived_specs() -> list[dict]:
    """扫描归档区 A 循环相关 spec，统计完成度。"""
    archive_root = ROOT / ".kiro" / "specs" / "_archive"
    if not archive_root.exists():
        return []
    keywords = [
        "a1", "a3", "a5", "a8", "a9",
        "report", "adjust", "cashflow", "goodwill",
        "consolidat", "kam", "governance", "checklist", "deficiency",
    ]
    results = []
    for spec_dir in sorted(archive_root.rglob("*")):
        if not spec_dir.is_dir():
            continue
        tasks_file = spec_dir / "tasks.md"
        if not tasks_file.exists():
            continue
        name_lower = spec_dir.name.lower()
        if not any(kw in name_lower for kw in keywords):
            continue
        try:
            text = tasks_file.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        # 统计 [ ] 和 [x] 数量
        total = len(re.findall(r"- \[[ x]\]", text))
        done = len(re.findall(r"- \[x\]", text))
        results.append({
            "name": spec_dir.name,
            "path": str(spec_dir),
            "total": total,
            "done": done,
            "complete": total == done if total > 0 else None,
        })
    return results


# ════════════════════════════════════════════════════════════════════════════
# resolveProcedureSheetKey 接入检测（AC-28）
# ════════════════════════════════════════════════════════════════════════════

def check_procedure_sheet_key_router() -> dict:
    """检查 resolveProcedureSheetKey.ts 中是否有 A 分支。"""
    # 🔴 实际路径在 utils/ 下，不在 composables/ 下
    target = FRONTEND / "utils" / "resolveProcedureSheetKey.ts"
    if not target.exists():
        # 兜底：搜索
        candidates = list(FRONTEND.rglob("resolveProcedureSheetKey.ts"))
        candidates = [c for c in candidates if "__tests__" not in str(c)]
        if candidates:
            target = candidates[0]
        else:
            return {"exists": False, "lines": 0, "has_a_branch": False}
    text = target.read_text(encoding="utf-8", errors="replace")
    lines = len(text.split("\n"))
    # 检查是否有 A 域相关的分支（排除注释行）
    stripped = strip_comments(text)
    has_a = bool(re.search(r"['\"]A\d", stripped))
    return {"exists": True, "lines": lines, "has_a_branch": has_a}


# ════════════════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 72)
    print("A 循环域扫描器")
    print("=" * 72)

    # 1. 域切分
    sl = load_slice()
    entries = sl["independent_entries"]
    split = domain_split(entries)
    print(f"\n总 entry 数: {len(entries)}")
    for k, v in sorted(split.items()):
        print(f"  {k}: {len(v)}")

    # 2. A 域文件集
    prod, test = scan_a_domain_files(include_tests=True)
    print(f"\nA 域文件: 生产 {len(prod)}, 测试 {len(test)}, 合计 {len(prod) + len(test)}")

    prod_upper, test_upper = scan_a_domain_files_upper_only(include_tests=True)
    print(f"仅大写分支: 生产 {len(prod_upper)}, 测试 {len(test_upper)}, 合计 {len(prod_upper) + len(test_upper)}")
    print(f"小写分支贡献: {len(prod) + len(test) - len(prod_upper) - len(test_upper)} 个")

    # 3. 模板统计
    tmpl = scan_a_templates()
    print(f"\nA 目录权威册: 合计 {tmpl['total_count']} = xlsx {tmpl['xlsx_count']} + docx {tmpl['docx_count']}")

    # 4. 路由接入
    router = check_procedure_sheet_key_router()
    print(f"\nresolveProcedureSheetKey: {router['lines']} 行, A 分支: {router['has_a_branch']}")

    print("\n扫描完成。")


if __name__ == "__main__":
    main()
