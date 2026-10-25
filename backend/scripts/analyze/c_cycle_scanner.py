# -*- coding: utf-8 -*-
r"""C 循环（控制测试）域扫描器 -- Foundation spec 任务 1~5。

C 域与 B 域的核心差异：
  - 只有 2 条 in-scope entry（B 域 10 条），14 个维度逐项相反
  - 按首字母切域只得 1 条（漏主体 gt-c-control-test，pattern_less）
  - 载体二分（host_inline_segmented 1 + no_carrier 1）
  - 36 本模板册 100% xlsx（唯一纯 xlsx 域）
  - 28 码 → c-control-test、1 码 → c22-itgc-bundle
  - 行身份 CLEAN（step.num 业务键），idx 14 处全属 UI 局部（非缺陷）

用法::

    ..\\.venv\\Scripts\\python.exe backend/scripts/analyze/c_cycle_scanner.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# 路径
# ═══════════════════════════════════════════════════════════════════════════
ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
TEMPLATE_DIR = BACKEND / "wp_templates" / "C"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
_SLICE_PATH = DATA / "workpaper_sync_abcs_cycle_manifest_slice.json"
_WP_CODE_OVERRIDES = BACKEND / "app" / "data" / "wp_code_overrides.json"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# 复用 A 域 scanner 的基础设施
sys.path.insert(0, str(BACKEND / "scripts" / "analyze"))
from a_cycle_scanner import (  # noqa: E402
    strip_comments,
    scan_xlsx_formulas,
    scan_xlsx_footer_raw_xml,
    scan_endpoint_literals,
    scan_structural_zeros,
    import_closure,
    channel_of_host,
    sha256_file,
    parse_oo_mounts,
    classify_mode_carrier,
    scan_archived_specs,
    check_procedure_sheet_key_router,
)


# ═══════════════════════════════════════════════════════════════════════════
# C 域常量
# ═══════════════════════════════════════════════════════════════════════════

# 2 条 in-scope entry 的 entry_id（精确匹配 requirements.md）
C_ENTRY_IDS = [
    "xlsx/gt-c-control-test",
    "xlsx/gt-c22-itgc-bundle",
]

# canary
CANARY_ENTRY_ID = "xlsx/gt-c-control-test"

# 统一的 BP 阻塞列表
C_DOMAIN_BLOCKED_BY = ["BP-1", "BP-2", "BP-3", "BP-4", "BP-5", "BP-7", "BP-8"]

# C22 额外背负 BP-10
C22_BLOCKED_BY = sorted(C_DOMAIN_BLOCKED_BY + ["BP-10"])

# 28 个映射到 c-control-test 的真实 wp_code（主册 + -2 偏差评价）
C_CONTROL_TEST_WP_CODES = sorted([
    f"C{n}" for n in range(2, 16)
] + [
    f"C{n}-2" for n in range(2, 16)
])  # 14 主 + 14 偏差 = 28

# C22 只有 1 个 wp_code
C22_WP_CODES = ["C22"]

# 排除的 7 本册
EXCLUDED_BOOKS = [
    "C1 企业层面控制测试.xlsx",
    "C21 具有信息技术专业技能的项目组成员.xlsx",
    "C21-1  IT审计发现汇总表.xlsx",
    "C23 会计分录 - 控制测试.xlsx",
    "C24 会计分录 - 细节测试.xlsx",
    "C25 利用内审工作.xlsx",
    "C26 信息处理控制测试.xlsx",
]

# pattern_less 5 条的 override 反查结果
PATTERN_LESS_OVERRIDE_RESULTS = {
    "c-control-test": 28,
    "c22-itgc-bundle": 1,
    "a-program-console": 32,
    "cf-verification": 1,
    "custom": 0,
}


# ═══════════════════════════════════════════════════════════════════════════
# slice 加载与域切分
# ═══════════════════════════════════════════════════════════════════════════

def load_slice() -> dict:
    return json.loads(_SLICE_PATH.read_bytes())


def load_overrides() -> dict[str, str]:
    """加载 wp_code_overrides.json → {wp_code: componentType}。"""
    return json.loads(_WP_CODE_OVERRIDES.read_bytes())


def c_domain_entries_by_entry_id(entries: list[dict]) -> list[dict]:
    """从 slice 的 independent_entries 中提取 C 域 2 条 entry。

    🔴 不能按 wp_code_patterns 首字母切域（CC-1 反转）——
    gt-c-control-test 的 patterns 是空数组，首字母切域会漏掉它。
    必须按 entry_id 精确匹配。
    """
    return [e for e in entries if e["entry_id"] in C_ENTRY_IDS]


def c_domain_entries_by_first_letter(entries: list[dict]) -> list[dict]:
    """仅按首字母切域（验证会漏主体的反例）。"""
    result = []
    for e in entries:
        patterns = e.get("wp_code_patterns", [])
        if patterns:
            first = patterns[0]
            if first and first[0].upper() == "C":
                result.append(e)
    return result


def c_entry_by_id(entries: list[dict]) -> dict[str, dict]:
    return {e["entry_id"]: e for e in entries}


# ═══════════════════════════════════════════════════════════════════════════
# override 反查
# ═══════════════════════════════════════════════════════════════════════════

def override_reverse_lookup(
    overrides: dict[str, str], component_type: str
) -> list[str]:
    """从 overrides 中找到映射到 component_type 的所有 wp_code。"""
    return sorted(
        code for code, ct in overrides.items()
        if ct == component_type
    )


def pattern_less_entries(entries: list[dict]) -> list[dict]:
    """提取 wp_code_patterns 为空数组的 entry。"""
    return [e for e in entries if not e.get("wp_code_patterns")]


# ═══════════════════════════════════════════════════════════════════════════
# strict 域文件集（CC-57）
# ═══════════════════════════════════════════════════════════════════════════

# ^GtC\d（漏主体 GtCControlTest.vue）
_C_STRICT_DIGIT_RE = re.compile(r"^(?:use|Gt)C\d")
# 扩展：^GtC[A-Z]（命中 GtCControlTest.vue）
_C_STRICT_ALPHA_RE = re.compile(r"^(?:use|Gt)C[A-Z]")
_C_LOWER_RE = re.compile(r"^c\d")
_C_DIR_RE = re.compile(r"/c(?:ControlTest|22)")


def is_c_domain_file(path: Path) -> bool:
    """判断前端文件是否属于 C 域（strict 域）。"""
    rel = ""
    if path.is_relative_to(WP_COMPONENTS):
        rel = path.relative_to(WP_COMPONENTS).as_posix()
    if _C_DIR_RE.search(rel):
        return True
    name = path.name
    if _C_STRICT_DIGIT_RE.match(name) or _C_STRICT_ALPHA_RE.match(name):
        return True
    if _C_LOWER_RE.match(name):
        return True
    return False


def scan_c_domain_files(
    *, include_tests: bool = False
) -> tuple[list[Path], list[Path]]:
    """扫描 C 域前端文件。"""
    prod: list[Path] = []
    test: list[Path] = []
    for p in WP_COMPONENTS.rglob("*"):
        if not p.is_file() or p.suffix not in (".vue", ".ts", ".tsx"):
            continue
        if not is_c_domain_file(p):
            continue
        if "__tests__" in p.parts or p.name.endswith(".spec.ts"):
            test.append(p)
        else:
            prod.append(p)
    return (prod, test) if include_tests else (prod, [])


# ═══════════════════════════════════════════════════════════════════════════
# C 域模板目录统计
# ═══════════════════════════════════════════════════════════════════════════

def scan_c_templates() -> dict[str, Any]:
    """扫描 C 域模板目录。"""
    if not TEMPLATE_DIR.exists():
        return {"total": 0, "xlsx": 0, "docx": 0, "xlsm": 0, "files": []}
    files = [
        f for f in TEMPLATE_DIR.rglob("*")
        if f.is_file() and f.suffix.lower() in (".xlsx", ".docx", ".xlsm")
    ]
    xlsx = [f for f in files if f.suffix.lower() == ".xlsx"]
    docx = [f for f in files if f.suffix.lower() == ".docx"]
    xlsm = [f for f in files if f.suffix.lower() == ".xlsm"]
    return {
        "total": len(files),
        "xlsx": len(xlsx),
        "docx": len(docx),
        "xlsm": len(xlsm),
        "files": files,
    }


def c_template_resolution(wp_code: str) -> dict[str, Any]:
    """测试 wp_code 模板解析。"""
    if not TEMPLATE_DIR.exists():
        return {"code": wp_code, "result": "error", "books_count": 0}
    candidates = []
    for f in TEMPLATE_DIR.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in (".xlsx", ".xlsm", ".docx"):
            continue
        stem = f.stem
        if stem == wp_code or stem.startswith(f"{wp_code} ") or stem.startswith(f"{wp_code}-"):
            candidates.append(f)
    if not candidates:
        return {"code": wp_code, "result": "none", "books_count": 0}
    return {
        "code": wp_code,
        "result": "ok" if len(candidates) == 1 else "ambiguous",
        "books_count": len(candidates),
        "books": [c.name for c in candidates],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 成对册分析
# ═══════════════════════════════════════════════════════════════════════════

def paired_book_analysis() -> dict[str, Any]:
    """分析主册 C{n} 与偏差册 C{n}-2 的对称性。

    返回 {main: [...], deviation: [...], paired_count}。
    """
    tmpl = scan_c_templates()
    files = tmpl.get("files", [])

    main_books: list[Path] = []
    dev_books: list[Path] = []

    for f in files:
        stem = f.stem
        # C{n}-2 偏差评价册
        if re.match(r"C\d+-2\b", stem):
            dev_books.append(f)
        # C{n} 主册（不含 -2 后缀，也不含 C21/C22/C23 等特殊册）
        elif re.match(r"C\d+\b", stem) and not re.match(r"C(?:2[1-6]|1)\b", stem):
            main_books.append(f)

    return {
        "main": sorted(main_books, key=lambda f: f.name),
        "deviation": sorted(dev_books, key=lambda f: f.name),
        "paired_count": min(len(main_books), len(dev_books)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 行身份扫描器（CC-53，须双向变异——禁照抄 B 轮）
# ═══════════════════════════════════════════════════════════════════════════

# N 轮形态正则
_N_FORM_ITEM_ID_RE = re.compile(r'\$\{[A-Za-z_]+\}-\$\{(?:index|idx|i)\}')
_M_FORM_ROW_RE = re.compile(r'row-\$\{[a-zA-Z_]+\}')

# 函数参数式行下标
_FUNC_PARAM_ROWINDEX_RE = re.compile(r'\b(?:rowIndex|row_index)\b')
_FUNC_PARAM_IDX_RE = re.compile(r'\bidx\b')

# item_id 构造中含 idx（真缺陷标记）
# 🔴 只匹配显式的 item_id 赋值/模板串中含 ${idx}：
#   - `C${n}-ctrl-${idx}-field` 模式
#   - item_id = ... idx ...（同一行赋值 + idx）
# 禁匹配 CSS 中的 `${idx}` 或无关模板串
_ITEM_ID_WITH_IDX_RE = re.compile(
    r'item_id\s*[:=]\s*`[^`]*\$\{(?:idx|index)\}[^`]*`'
)


def scan_row_identity_c_domain(
    prod_files: list[Path],
) -> dict[str, Any]:
    """扫描 C 域行身份形态。

    🔴 C 域须区分两类：
      类 A（缺陷）：idx 进入 item_id 构造或持久化键
      类 B（非缺陷）：idx 仅作内存数组索引 / splice / Dialog 参数

    返回：
      - n_form_hits, m_form_hits: 预期 0
      - rowIndex_hits, idx_total_hits: 总 idx 命中
      - idx_in_item_id_hits: 类 A 命中（预期 0）
      - idx_ui_only_hits: 类 B 命中
      - label_as_key_hits: label 作渲染 key
    """
    stats: dict[str, Any] = {
        "n_form_hits": 0,
        "m_form_hits": 0,
        "rowIndex_hits": 0,
        "idx_total_hits": 0,
        "idx_in_item_id_hits": 0,
        "idx_ui_only_hits": 0,
        "label_as_key_hits": 0,
        "details": [],
    }

    label_key_re = re.compile(r':key\s*=\s*["\'].*?\b(?:row\.name|grp\.label)\b')

    for f in prod_files:
        if f.suffix not in (".vue", ".ts"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        clean = strip_comments(text)

        n_hits = len(_N_FORM_ITEM_ID_RE.findall(clean))
        m_hits = len(_M_FORM_ROW_RE.findall(clean))
        ri_hits = len(_FUNC_PARAM_ROWINDEX_RE.findall(clean))
        idx_hits = len(_FUNC_PARAM_IDX_RE.findall(clean))
        # 类 A：idx 出现在 item_id 构造中
        item_id_idx = len(_ITEM_ID_WITH_IDX_RE.findall(clean))
        lk_hits = len(label_key_re.findall(text))

        if any([n_hits, m_hits, ri_hits, idx_hits, lk_hits]):
            stats["n_form_hits"] += n_hits
            stats["m_form_hits"] += m_hits
            stats["rowIndex_hits"] += ri_hits
            stats["idx_total_hits"] += idx_hits
            stats["idx_in_item_id_hits"] += item_id_idx
            stats["idx_ui_only_hits"] += (idx_hits - item_id_idx)
            stats["label_as_key_hits"] += lk_hits
            stats["details"].append({
                "file": f.name,
                "n_form": n_hits, "m_form": m_hits,
                "rowIndex": ri_hits, "idx_total": idx_hits,
                "idx_in_item_id": item_id_idx,
                "label_as_key": lk_hits,
            })

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# wp_index 扫描（C 域 29 码全 n=4）
# ═══════════════════════════════════════════════════════════════════════════

def scan_wp_index_c_domain() -> dict[str, int]:
    """扫描 wp_index 中 C 域 29 码各出现多少行。"""
    wp_index_path = DATA / "wp_account_mapping.json"
    if not wp_index_path.exists():
        return {}
    data = json.loads(wp_index_path.read_bytes())
    all_codes = C_CONTROL_TEST_WP_CODES + C22_WP_CODES  # 29 码
    counts: dict[str, int] = {}
    if isinstance(data, list):
        for row in data:
            code = row.get("wp_code", "")
            if code in all_codes:
                counts[code] = counts.get(code, 0) + 1
    elif isinstance(data, dict):
        for code in all_codes:
            if code in data:
                val = data[code]
                counts[code] = len(val) if isinstance(val, list) else 1
    return counts


# ═══════════════════════════════════════════════════════════════════════════
# 空分母清册（CC-20）
# ═══════════════════════════════════════════════════════════════════════════

def scan_c_structural_zeros(
    prod_files: list[Path],
) -> dict[str, int]:
    """扫描 C 域 17 项结构性零。"""
    results: dict[str, int] = {}

    for f in prod_files:
        if f.suffix not in (".vue", ".ts"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        clean = strip_comments(text)

        # 逐项扫描
        results["confirm"] = results.get("confirm", 0) + clean.count("ElMessageBox.confirm")
        results["removeRow"] = results.get("removeRow", 0) + (
            clean.count("removeRow") + clean.count("deleteRow")
        )
        results["derived_total"] = results.get("derived_total", 0) + (
            clean.count("derived_total") + clean.count(".reduce(")
        )
        results["prefill"] = results.get("prefill", 0) + clean.count("prefill")
        results["publish_to_tb"] = results.get("publish_to_tb", 0) + clean.count("publish-to-tb")
        results["count_key"] = results.get("count_key", 0) + len(
            re.findall(r"['\"]count['\"]", clean)
        )
        results["notice_sync"] = results.get("notice_sync", 0) + clean.count(
            "GtEntrySyncCapabilityNotice"
        )
        results["resolve_procedure_sheet_key"] = results.get(
            "resolve_procedure_sheet_key", 0
        ) + clean.count("resolveProcedureSheetKey")
        results["onlyoffice_health"] = results.get("onlyoffice_health", 0) + clean.count(
            "onlyoffice/health"
        )
        results["localstorage_mode"] = results.get("localstorage_mode", 0) + len(
            re.findall(r"localStorage.*mode|mode.*localStorage", clean)
        )

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 全域模板深度扫描（CC-9, CC-21, CC-32, CC-35, CC-36, CC-62, CC-67）
# ═══════════════════════════════════════════════════════════════════════════

def deep_scan_all_c_templates() -> dict[str, Any]:
    """深度扫描 C 域全部 36 本 xlsx 模板册。

    返回全域聚合 + 逐册明细。使用 a_cycle_scanner 的 scan_xlsx_formulas
    和 scan_xlsx_footer_raw_xml。
    """
    tmpl = scan_c_templates()
    files = tmpl.get("files", [])

    per_book: list[dict[str, Any]] = []
    total_dn = 0
    total_dn_broken = 0
    total_fx = 0
    total_sheets = 0
    total_fx_sheets = 0
    hidden_sheets = 0
    ref_sheets: list[str] = []  # 参考型 sheet 名
    all_sheet_names: list[str] = []
    max_ghost_in_scope = 0
    max_ghost_all = 0

    for f in sorted(files, key=lambda p: p.name):
        try:
            info = scan_xlsx_formulas(f)
        except Exception as exc:
            per_book.append({"file": f.name, "error": str(exc)})
            continue

        # 逐 sheet 统计
        book_fx = info["total_formulas"]
        book_dn = info["defined_names_total"]
        book_dn_broken = info["defined_names_broken"]

        # 超列引用（公式里引用列 > max_column 的情况简化为含 #REF! 的 definedName）
        # 实际超列引用需要独立正则扫描公式文本

        # 幽灵行 = max_row - last_value_row
        book_max_ghost = 0
        for sh in info["sheets"]:
            all_sheet_names.append(sh["name"])
            if sh["hidden"]:
                hidden_sheets += 1
            # 参考型 sheet
            if "选项清单列表" in sh["name"] or "示例-评价控制偏差" in sh["name"]:
                ref_sheets.append(sh["name"])

        total_dn += book_dn
        total_dn_broken += book_dn_broken
        total_fx += book_fx
        total_sheets += info["sheet_count"]
        total_fx_sheets += info["fx_sheet_count"]

        # 判断册是否在排除名单
        excluded = f.name in EXCLUDED_BOOKS

        per_book.append({
            "file": f.name,
            "sheet_count": info["sheet_count"],
            "formulas": book_fx,
            "fx_sheets": info["fx_sheet_count"],
            "dn_total": book_dn,
            "dn_broken": book_dn_broken,
            "excluded": excluded,
        })

    # footer 扫描
    footer_counts = {"no_container": 0, "has_content": 0, "container_no_footer": 0}
    footer_contents: set[str] = set()
    for f in sorted(files, key=lambda p: p.name):
        try:
            footers = scan_xlsx_footer_raw_xml(f)
        except Exception:
            continue
        for item in footers:
            if not item["has_header_footer_container"]:
                footer_counts["no_container"] += 1
            elif item["odd_footer_values"]:
                footer_counts["has_content"] += 1
                for v in item["odd_footer_values"]:
                    footer_contents.add(v.strip())
            else:
                footer_counts["container_no_footer"] += 1

    # 成对册分析
    main_stats: list[dict] = []
    dev_stats: list[dict] = []
    for b in per_book:
        name = b.get("file", "")
        if "error" in b:
            continue
        if re.match(r"C\d+-2\b", name.split(".")[0]):
            dev_stats.append(b)
        elif re.match(r"C\d+ ", name) and not re.match(r"C(?:1|2[1-6])\b", name.split()[0]):
            main_stats.append(b)

    return {
        "total_books": len(files),
        "total_sheets": total_sheets,
        "total_formulas": total_fx,
        "total_fx_sheets": total_fx_sheets,
        "total_defined_names": total_dn,
        "total_dn_broken": total_dn_broken,
        "hidden_sheets": hidden_sheets,
        "ref_sheets": ref_sheets,
        "ref_sheet_count": len(ref_sheets),
        "unique_sheet_names": len(set(all_sheet_names)),
        "all_sheet_names_count": len(all_sheet_names),
        "footer_no_container": footer_counts["no_container"],
        "footer_has_content": footer_counts["has_content"],
        "footer_container_no_footer": footer_counts["container_no_footer"],
        "footer_content_types": sorted(footer_contents),
        "main_books": main_stats,
        "dev_books": dev_stats,
        "per_book": per_book,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 自检入口
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("C 域 scanner 自检")
    sl = load_slice()
    entries = c_domain_entries_by_entry_id(sl["independent_entries"])
    print(f"  C 域 entry（精确匹配）: {len(entries)}")

    letter_entries = c_domain_entries_by_first_letter(sl["independent_entries"])
    print(f"  C 域 entry（首字母切域）: {len(letter_entries)}")

    overrides = load_overrides()
    for ct, expected in PATTERN_LESS_OVERRIDE_RESULTS.items():
        codes = override_reverse_lookup(overrides, ct)
        c_codes = [c for c in codes if c.startswith("C") and not c.startswith("C0")]
        print(f"  override '{ct}' → C 域 {len(c_codes)} 码（总 {len(codes)}）")

    tmpl = scan_c_templates()
    print(f"  模板目录: total={tmpl['total']} xlsx={tmpl['xlsx']} "
          f"docx={tmpl['docx']} xlsm={tmpl['xlsm']}")

    prod, _ = scan_c_domain_files()
    print(f"  C 域前端文件: {len(prod)}")

    ri = scan_row_identity_c_domain(prod)
    print(f"  行身份: n_form={ri['n_form_hits']} m_form={ri['m_form_hits']} "
          f"rowIndex={ri['rowIndex_hits']} idx_total={ri['idx_total_hits']} "
          f"idx_in_item_id={ri['idx_in_item_id_hits']}")
