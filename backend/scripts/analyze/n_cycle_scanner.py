#!/usr/bin/env python3
"""N 循环（税费）域扫描器 —— Foundation spec 任务 1。

实现 strict 域三路取并（目录段 / 大写文件名 / 小写 n{1..5} 前缀 / nCycle 内容引用），
行身份六族分类，removeRow 归类四元组，模板几何统计等。

用法::

    ..\\.venv\\Scripts\\python.exe backend/scripts/analyze/n_cycle_scanner.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Any

try:
    import openpyxl
except ImportError:
    print("ERROR: pip install openpyxl")
    sys.exit(1)

# ════════════════════════════════════════════════════════════════════════════
# 路径
# ════════════════════════════════════════════════════════════════════════════
ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
TEMPLATE_DIR = BACKEND / "wp_templates" / "N"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"

N_CODES = ("N1", "N2", "N3", "N4", "N5")

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
# 域文件集：strict 三路取并（NC-5）
# ════════════════════════════════════════════════════════════════════════════

# 大写文件名：GtN[1-5]… 或 useN[1-5]… 或 N[1-5]…
_UPPER_RE = re.compile(r"^(?:use|Gt)?N[1-5](?![0-9])(?:[A-Z]|[-.]|$)")
# 🔴 小写前缀：n[1-5][A-Z]… —— M 轮缺此分支，漏 35 个
_LOWER_RE = re.compile(r"^n[1-5][A-Z]")
# nCycle 内容引用判据（nCycleTaxConsistency.ts 等 nCycle 开头但不含 /n[1-5]/ 目录段）
_N_KEY_REF_RE = re.compile(r"['\"]N[1-5]-")


def is_n_domain_file(path: Path, *, check_content: bool = True) -> bool:
    """判断给定前端文件是否属于 N 域（strict 三路取并）。

    三路：
    1. 路径含 /n[1-5]/ 目录段
    2. 文件名匹配大写前缀 ^(use|Gt)?N[1-5]…
    3. 文件名匹配小写前缀 ^n[1-5][A-Z]…
    4. （可选）内容含 N 键引用且文件名以 nCycle 开头
    """
    rel = path.relative_to(WP_COMPONENTS).as_posix() if path.is_relative_to(WP_COMPONENTS) else path.name
    # 路径 1：目录段
    if re.search(r"/n[1-5]/", rel):
        return True
    name = path.name
    # 路径 2：大写文件名
    if _UPPER_RE.match(name):
        return True
    # 路径 3：小写前缀
    if _LOWER_RE.match(name):
        return True
    # 路径 4：内容引用
    if check_content and name.startswith("nCycle"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if _N_KEY_REF_RE.search(text):
                return True
        except OSError:
            pass
    return False


def scan_n_domain_files(*, include_tests: bool = False) -> tuple[list[Path], list[Path]]:
    """扫描 N 域全部前端文件，返回 (生产文件, 测试文件)。"""
    prod: list[Path] = []
    test: list[Path] = []
    for p in sorted(WP_COMPONENTS.rglob("*")):
        if not p.is_file() or p.suffix not in (".ts", ".vue", ".tsx", ".js"):
            continue
        is_test = "__tests__" in p.as_posix() or p.name.endswith((".spec.ts", ".test.ts"))
        if not is_n_domain_file(p, check_content=True):
            continue
        if is_test:
            test.append(p)
        else:
            prod.append(p)
    return prod, test


def scan_n_domain_files_without_lower(*, include_tests: bool = False) -> tuple[list[Path], list[Path]]:
    """变异证明：去掉小写分支后的扫描结果。"""
    prod: list[Path] = []
    test: list[Path] = []

    def _is_n_no_lower(path: Path) -> bool:
        rel = path.relative_to(WP_COMPONENTS).as_posix() if path.is_relative_to(WP_COMPONENTS) else path.name
        if re.search(r"/n[1-5]/", rel):
            return True
        if _UPPER_RE.match(path.name):
            return True
        # 🔴 不包含小写分支
        if path.name.startswith("nCycle"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if _N_KEY_REF_RE.search(text):
                    return True
            except OSError:
                pass
        return False

    for p in sorted(WP_COMPONENTS.rglob("*")):
        if not p.is_file() or p.suffix not in (".ts", ".vue", ".tsx", ".js"):
            continue
        is_test = "__tests__" in p.as_posix() or p.name.endswith((".spec.ts", ".test.ts"))
        if not _is_n_no_lower(p):
            continue
        if is_test:
            test.append(p)
        else:
            prod.append(p)
    return prod, test


# ════════════════════════════════════════════════════════════════════════════
# 行身份六族分类（NC-6 / NC-7 / NC-8）
# ════════════════════════════════════════════════════════════════════════════

# E 族稳定身份标记
_E_FAMILY_RE = re.compile(r"\b(?:rowId|rowKey|\.id)\b")
# B 族位置化标记
_B_FAMILY_RE = re.compile(r"\b(?:index|idx|\$index|\.length)\b")

# removeRow 签名归类
_REMOVE_ROW_RE = re.compile(r"removeRow\s*\(([^)]+)\)")


def classify_remove_row_arg(first_arg: str) -> str:
    """对 removeRow 的第一个参数进行归类。"""
    arg = first_arg.strip()
    if re.search(r"rowId|rowKey|\.id\b", arg):
        return "by_rowid"
    if re.search(r"index|idx|\$index|\.length", arg):
        return "by_index"
    return "other"


def scan_row_identity(files: list[Path]) -> dict[str, Any]:
    """扫描行身份六族分布和 removeRow 归类。"""
    # 六族计数器
    family_a = 0  # 位置化：${PREFIX}-${index}
    family_b = 0  # 数组位置寻址
    family_c = 0  # 展示序号
    family_d = 0  # 熵键
    family_e = 0  # 稳定身份（rowId/rowKey/.id）
    family_m = 0  # M 式 row-${n} 中缀

    e_files: set[str] = set()
    remove_row_signatures: dict[str, int] = defaultdict(int)
    remove_row_by_type: dict[str, int] = {"by_rowid": 0, "by_index": 0, "other": 0}
    total_remove_row = 0

    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stripped = strip_comments(text)

        # E 族
        e_hits = len(_E_FAMILY_RE.findall(stripped))
        if e_hits > 0:
            family_e += e_hits
            e_files.add(p.relative_to(ROOT).as_posix())

        # B 族：数组位置寻址
        b_hits = len(re.findall(r"\[\s*(?:index|idx)\s*\]", stripped))
        family_b += b_hits

        # D 族：熵键（Date.now / Math.random / uuid）
        d_hits = len(re.findall(r"(?:Date\.now|Math\.random|uuid)", stripped))
        family_d += d_hits

        # C 族：展示序号
        c_hits = len(re.findall(r"(?:序号|#|index\s*\+\s*1)", stripped))
        family_c += c_hits

        # M 式 row-${n} 中缀：只匹配纯数字模板 row-${数字变量}
        # 排除 row-${Date.now()} / row-${Math.random()} / row-${item.taxType} 这些熵键
        m_hits = len(re.findall(r"row-\$\{(?:n|i|idx|index|count)\}", stripped))
        family_m += m_hits

        # A 族：${PREFIX}-${index} 形态
        a_hits = len(re.findall(r"\$\{[^}]+\}-\$\{(?:index|idx|i)\}", stripped))
        family_a += a_hits

        # removeRow 归类
        for match in _REMOVE_ROW_RE.finditer(stripped):
            total_remove_row += 1
            arg = match.group(1).split(",")[0].strip()
            classification = classify_remove_row_arg(arg)
            remove_row_by_type[classification] += 1
            # 取签名种类
            sig = arg[:50]  # 截断长签名
            remove_row_signatures[sig] += 1

    return {
        "families": {
            "A_positional_template": family_a,
            "B_array_addressing": family_b,
            "C_display_ordinal": family_c,
            "D_entropy_key": family_d,
            "E_stable_identity": family_e,
            "E_files": len(e_files),
            "M_row_dash_n": family_m,
        },
        "remove_row": {
            "total": total_remove_row,
            "by_type": dict(remove_row_by_type),
            "signature_count": len(remove_row_signatures),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# 模板几何扫描
# ════════════════════════════════════════════════════════════════════════════

def scan_n_templates() -> dict[str, Any]:
    """扫描 N 循环全部 5 本 xlsx 模板的 sheet 几何信息。"""
    results: dict[str, Any] = {}
    total_sheets = 0
    total_formulas = 0
    sheets_with_fx = 0

    if not TEMPLATE_DIR.exists():
        return {"error": f"Template dir not found: {TEMPLATE_DIR}"}

    for xlsx in sorted(TEMPLATE_DIR.glob("*.xlsx")):
        if xlsx.name.startswith("~$"):
            continue
        wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=False)
        entry_data: dict[str, Any] = {
            "file": xlsx.name,
            "sha256": hashlib.sha256(xlsx.read_bytes()).hexdigest(),
            "size": xlsx.stat().st_size,
            "sheets": [],
        }
        for sn in wb.sheetnames:
            ws = wb[sn]
            sheet_info: dict[str, Any] = {
                "name": sn,
                "max_row": ws.max_row or 0,
                "max_col": ws.max_column or 0,
                "hidden": ws.sheet_state != "visible",
            }
            # 公式扫描
            formula_count = 0
            naked_if_count = 0
            has_fx = False
            last_value_col = 0
            for row in ws.iter_rows():
                for cell in row:
                    val = cell.value
                    if isinstance(val, str) and val.startswith("=") and len(val) > 1:
                        formula_count += 1
                        has_fx = True
                        if val.upper().startswith("=IF("):
                            naked_if_count += 1
                    if val is not None and cell.column and cell.column > last_value_col:
                        last_value_col = cell.column
            sheet_info["formula_count"] = formula_count
            sheet_info["naked_if_count"] = naked_if_count
            sheet_info["last_value_col"] = last_value_col
            sheet_info["ghost_cols"] = (ws.max_column or 0) - last_value_col if last_value_col > 0 else 0
            entry_data["sheets"].append(sheet_info)
            total_sheets += 1
            total_formulas += formula_count
            if has_fx:
                sheets_with_fx += 1
        wb.close()
        results[xlsx.stem] = entry_data

    return {
        "entries": results,
        "totals": {
            "sheets": total_sheets,
            "formulas": total_formulas,
            "sheets_with_fx": sheets_with_fx,
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# 超列引用扫描（NC-32 wp_code 与 A1 同形）
# ════════════════════════════════════════════════════════════════════════════
_QUOTED_SEGMENT_RE = re.compile(r"'[^']*'!")
_CHINESE_SHEET_RE = re.compile(r"[\u4e00-\u9fff][^!]*!")
_FUNC_NAME_RE = re.compile(r"[A-Z]+\(")

# A1 引用模式
_COL_REF_RE = re.compile(r"(?<![A-Z0-9_!])([A-Z]{1,3})(\d+)")


def col_index(col_str: str) -> int:
    """Excel 列字母转数字索引，如 A→1, N→14, IV→256。"""
    result = 0
    for ch in col_str:
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result


def scan_overflow_col_refs(templates: dict[str, Any]) -> dict[str, Any]:
    """扫描超列引用三族。"""
    family_a1: list[dict] = []  # 真缺陷
    family_a2: list[dict] = []  # 结构残留
    family_b: list[dict] = []   # 合法
    raw_hits = 0

    for entry_name, entry_data in templates.get("entries", {}).items():
        xlsx_path = TEMPLATE_DIR / f"{entry_name}.xlsx"
        if not xlsx_path.exists():
            continue
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=False)
        for sheet_info in entry_data.get("sheets", []):
            sn = sheet_info["name"]
            max_col = sheet_info["max_col"]
            if max_col == 0:
                continue
            ws = wb[sn]
            overflow_by_col: dict[str, list[str]] = defaultdict(list)
            for row in ws.iter_rows():
                for cell in row:
                    val = cell.value
                    if not isinstance(val, str) or not val.startswith("="):
                        continue
                    # 剔除引号段、中文 sheet 名段
                    cleaned = _QUOTED_SEGMENT_RE.sub("", val)
                    cleaned = _CHINESE_SHEET_RE.sub("", cleaned)
                    for m in _COL_REF_RE.finditer(cleaned):
                        col_letter = m.group(1)
                        # 排除函数名
                        if _FUNC_NAME_RE.match(col_letter + "("):
                            continue
                        ci = col_index(col_letter)
                        if ci > max_col:
                            raw_hits += 1
                            ref = f"{sn} {cell.coordinate}"
                            overflow_by_col[col_letter].append(ref)

            for col_letter, refs in overflow_by_col.items():
                hit = {
                    "entry": entry_name,
                    "sheet": sn,
                    "col": col_letter,
                    "col_index": col_index(col_letter),
                    "max_col": max_col,
                    "refs": refs,
                    "count": len(refs),
                }
                # SUM 区间终点 → 合法（族 B）
                # 整列同形且无反向分母 → 结构残留（族 A2）
                # 有反向分母 → 真缺陷（族 A1）
                # 简化判据：引用数 > 5 且全在同一列 → A2
                if len(refs) > 5:
                    family_a2.append(hit)
                elif len(refs) == 1:
                    family_a1.append(hit)
                else:
                    # 需进一步判定
                    family_b.append(hit)
        wb.close()

    return {
        "a1_defects": family_a1,
        "a2_structural": family_a2,
        "b_legitimate": family_b,
        "raw_hits": raw_hits,
        "correct_total": len(family_a1) + len(family_a2) + len(family_b),
    }


# ════════════════════════════════════════════════════════════════════════════
# transport_key 解析（NC-30）
# ════════════════════════════════════════════════════════════════════════════
_ITEM_PREFIX_RE = re.compile(r"""(?:ITEM_PREFIX|TRANSPORT_KEY_PREFIX)\s*=\s*['"]([^'"]+)['"]""")
_TRANSPORT_KEY_RE = re.compile(r"""['"](N[1-5]-[^'"]+)['"]""")


def scan_transport_keys(files: list[Path]) -> dict[str, Any]:
    """扫描 N 域的 transport_key owner 声明。"""
    owners: dict[str, list[str]] = defaultdict(list)
    all_keys: set[str] = set()

    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stripped = strip_comments(text)
        rel = p.relative_to(ROOT).as_posix()

        # ITEM_PREFIX 声明
        for m in _ITEM_PREFIX_RE.finditer(stripped):
            prefix = m.group(1)
            if prefix.startswith("N"):
                owners[prefix].append(rel)

        # 直接字面量键
        for m in _TRANSPORT_KEY_RE.finditer(stripped):
            key = m.group(1)
            all_keys.add(key)

    return {
        "owners": {k: sorted(set(v)) for k, v in owners.items()},
        "owner_count": sum(len(v) for v in owners.values()),
        "all_keys": sorted(all_keys),
    }


# ════════════════════════════════════════════════════════════════════════════
# 结构性零扫描
# ════════════════════════════════════════════════════════════════════════════

def scan_structural_zeros(files: list[Path]) -> dict[str, int]:
    """扫描 16 项结构性零。"""
    items: dict[str, int] = {
        "trial-balance/writeback": 0,
        "#REF!_dead_formula": 0,
        "*EntryDualMode.ts": 0,
        "useChecklistPersistence": 0,
        "contract-ocr": 0,
        "GtEntrySyncCapabilityNotice": 0,
        "http.put": 0,
        "api.put": 0,
        "loose_only": 0,
        "M_style_row_dash_n": 0,
    }

    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stripped = strip_comments(text)

        if "trial-balance/writeback" in stripped:
            items["trial-balance/writeback"] += 1
        if "#REF!" in stripped:
            items["#REF!_dead_formula"] += 1
        # 🔴 判据是文件名匹配 *EntryDualMode.ts，不是内容引用
        if p.name.endswith("EntryDualMode.ts"):
            items["*EntryDualMode.ts"] += 1
        if "useChecklistPersistence" in stripped:
            items["useChecklistPersistence"] += 1
        if "contract-ocr" in stripped:
            items["contract-ocr"] += 1
        if "GtEntrySyncCapabilityNotice" in stripped:
            items["GtEntrySyncCapabilityNotice"] += 1
        if "http.put" in stripped:
            items["http.put"] += 1
        if "api.put" in stripped:
            items["api.put"] += 1
        if re.search(r"row-\$\{[^}]+\}", stripped):
            items["M_style_row_dash_n"] += 1

    return items


# ════════════════════════════════════════════════════════════════════════════
# 端点字面量扫描（NC-3）
# ════════════════════════════════════════════════════════════════════════════

def scan_endpoint_literals(files: list[Path]) -> dict[str, Any]:
    """扫描 publish-to-tb 和 trial-balance/writeback 的命中情况。"""
    publish_code = 0
    publish_comment = 0
    writeback_code = 0
    writeback_comment = 0

    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stripped = strip_comments(text)

        pub_in_stripped = len(re.findall(r"publish-to-tb", stripped))
        pub_in_raw = len(re.findall(r"publish-to-tb", text))
        publish_code += pub_in_stripped
        publish_comment += (pub_in_raw - pub_in_stripped)

        wb_in_stripped = len(re.findall(r"trial-balance/writeback", stripped))
        wb_in_raw = len(re.findall(r"trial-balance/writeback", text))
        writeback_code += wb_in_stripped
        writeback_comment += (wb_in_raw - wb_in_stripped)

    return {
        "publish-to-tb": {"code": publish_code, "comment": publish_comment},
        "trial-balance/writeback": {"code": writeback_code, "comment": writeback_comment},
    }


# ════════════════════════════════════════════════════════════════════════════
# definedName 扫描（NC-9）
# ════════════════════════════════════════════════════════════════════════════

def scan_defined_names() -> dict[str, Any]:
    """扫描 N 循环模板的 definedName 及 broken 数量。"""
    results: dict[str, dict] = {}
    total_dn = 0
    total_broken = 0

    for xlsx in sorted(TEMPLATE_DIR.glob("*.xlsx")):
        if xlsx.name.startswith("~$"):
            continue
        wb = openpyxl.load_workbook(xlsx, data_only=False)
        entry_dn: list[dict] = []
        # 兼容新旧版 openpyxl：新版无 definedNameList 属性
        dn_list = getattr(wb.defined_names, "definedNameList", None)
        if dn_list is None:
            # 新版 openpyxl：DefinedNameDict 可直接迭代
            dn_list = list(wb.defined_names.values()) if hasattr(wb.defined_names, "values") else []
        for dn in dn_list:
            name = dn.name
            value = str(dn.attr_text) if hasattr(dn, "attr_text") else str(dn.value)
            is_broken = "#REF!" in value
            entry_dn.append({
                "name": name,
                "value": value[:120],
                "broken": is_broken,
            })
        wb.close()
        broken_count = sum(1 for d in entry_dn if d["broken"])
        results[xlsx.stem] = {
            "total": len(entry_dn),
            "broken": broken_count,
            "details": entry_dn,
        }
        total_dn += len(entry_dn)
        total_broken += broken_count

    return {
        "per_entry": results,
        "total": total_dn,
        "broken": total_broken,
    }


# ════════════════════════════════════════════════════════════════════════════
# footer 三态扫描（NC-36）
# ════════════════════════════════════════════════════════════════════════════

def scan_footers() -> dict[str, Any]:
    """扫描 N 循环模板的 footer 三态（正常 &P/&N / 缺斜杠 &P&N / 无 footer）。

    🔴 A 轮教训：openpyxl 的 ws.oddFooter 在遇到无法解析的 footer 时会静默返回空。
    此处使用 raw XML 对账补充。
    """
    import zipfile
    import xml.etree.ElementTree as ET

    normal = 0  # &P/&N
    missing_slash = 0  # &P&N（缺斜杠）
    no_footer = 0
    details: list[dict] = []

    for xlsx in sorted(TEMPLATE_DIR.glob("*.xlsx")):
        if xlsx.name.startswith("~$"):
            continue
        # 用 raw XML 读 footer
        with zipfile.ZipFile(xlsx) as zf:
            for name in zf.namelist():
                if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                    continue
                content = zf.read(name).decode("utf-8", errors="replace")
                root = ET.fromstring(content)
                ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                odd_footer = root.find(".//x:oddFooter", ns)
                if odd_footer is not None and odd_footer.text:
                    ft = odd_footer.text
                    if "&P" in ft and "&N" in ft:
                        if "/" in ft or "／" in ft:
                            normal += 1
                            details.append({"file": xlsx.stem, "sheet_xml": name, "footer": ft[:60], "type": "normal"})
                        else:
                            missing_slash += 1
                            details.append({"file": xlsx.stem, "sheet_xml": name, "footer": ft[:60], "type": "missing_slash"})
                    else:
                        # 有 footer 但不是标准分页格式
                        normal += 1
                        details.append({"file": xlsx.stem, "sheet_xml": name, "footer": ft[:60], "type": "other"})
                else:
                    no_footer += 1
                    details.append({"file": xlsx.stem, "sheet_xml": name, "footer": None, "type": "none"})

    return {
        "normal": normal,
        "missing_slash": missing_slash,
        "no_footer": no_footer,
        "total": normal + missing_slash + no_footer,
        "details": details,
    }


# ════════════════════════════════════════════════════════════════════════════
# 主函数
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 72)
    print("N-Cycle Scanner — Foundation spec 任务 1")
    print("=" * 72)

    # 1. 域文件集
    prod, test = scan_n_domain_files()
    prod_no_lower, test_no_lower = scan_n_domain_files_without_lower()
    print(f"\n域文件集：生产 {len(prod)} / 测试 {len(test)} / 合计 {len(prod) + len(test)}")
    print(f"  去掉小写分支后：生产 {len(prod_no_lower)} / 测试 {len(test_no_lower)} / 合计 {len(prod_no_lower) + len(test_no_lower)}")
    missed = set(p.name for p in prod) - set(p.name for p in prod_no_lower)
    print(f"  漏掉文件数：{len(missed)} 生产 / {len(set(p.name for p in test) - set(p.name for p in test_no_lower))} 测试")

    # 2. 行身份六族
    identity = scan_row_identity(prod)
    print(f"\n行身份六族：")
    for k, v in identity["families"].items():
        print(f"  {k}: {v}")
    print(f"  removeRow 总计: {identity['remove_row']['total']}")
    for k, v in identity["remove_row"]["by_type"].items():
        print(f"    {k}: {v}")

    # 3. 模板几何
    templates = scan_n_templates()
    if "error" not in templates:
        t = templates["totals"]
        print(f"\n模板几何：sheets {t['sheets']} / 公式格 {t['formulas']} / 带 fx {t['sheets_with_fx']}")
        for name, entry in templates["entries"].items():
            print(f"  {name}: {len(entry['sheets'])} sheets, sha256={entry['sha256'][:16]}…")
    else:
        print(f"\n模板几何：{templates['error']}")

    # 4. transport_key
    tk = scan_transport_keys(prod)
    print(f"\ntransport_key：{tk['owner_count']} 处 owner 声明")
    for prefix, locations in tk["owners"].items():
        print(f"  {prefix}: {locations}")

    # 5. 端点字面量
    endpoints = scan_endpoint_literals(prod)
    print(f"\n端点字面量：")
    for ep, counts in endpoints.items():
        print(f"  {ep}: CODE {counts['code']} / CMT {counts['comment']}")

    # 6. 结构性零
    zeros = scan_structural_zeros(prod)
    print(f"\n结构性零（{sum(1 for v in zeros.values() if v == 0)}/{len(zeros)} 项为零）：")
    for k, v in zeros.items():
        print(f"  {k}: {v}")

    # 7. definedName
    dn = scan_defined_names()
    print(f"\ndefinedName：总 {dn['total']} / broken {dn['broken']}")
    for name, info in dn["per_entry"].items():
        print(f"  {name}: {info['total']} / broken {info['broken']}")

    # 8. footer 三态
    footers = scan_footers()
    print(f"\nfooter 三态：正常 {footers['normal']} / 缺斜杠 {footers['missing_slash']} / 无 {footers['no_footer']} = {footers['total']}")

    # 输出 JSON
    report = {
        "domain_files": {
            "production": len(prod),
            "test": len(test),
            "total": len(prod) + len(test),
            "without_lower_branch": {
                "production": len(prod_no_lower),
                "test": len(test_no_lower),
                "missed_production": len(missed),
            },
        },
        "row_identity": identity,
        "templates": templates,
        "transport_keys": tk,
        "endpoints": endpoints,
        "structural_zeros": zeros,
        "defined_names": dn,
        "footers": footers,
    }

    out_path = DATA / "n_cycle_scanner_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n报告已输出到：{out_path}")


if __name__ == "__main__":
    main()
