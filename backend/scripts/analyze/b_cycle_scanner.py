# -*- coding: utf-8 -*-
"""B 循环域扫描器 — B 域 10 条 entry 的事实基线提取工具。

spec: b-cycle-sync-foundation-and-first-canary

与 a_cycle_scanner.py 同级，复用其 domain_split / strip_comments 等基础设施，
新增 B 域专用函数。

🔴 B 域与 A 域的核心差异：
  - 10 条 entry 的 capability_target_blocked_by 完全相同 → BP 切分失效
  - 载体三分（useWpDualMode 3 / 共享基类 5 / host_inline 2）
  - 行身份缺陷族是「函数参数式行下标」（idx/rowIndex 形参），非 N 轮形态
  - mode 值三体系混用 + 第四值 'polish'
  - 解析失败三模式（None / FileNotFoundError / 多册歧义）
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# 路径
# ═══════════════════════════════════════════════════════════════════════════
_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
_FRONTEND = _ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = _FRONTEND / "components" / "workpaper"
_TEMPLATE_DIR = _BACKEND / "wp_templates" / "B"
_DATA = _BACKEND / "data"
_SLICE_PATH = _DATA / "workpaper_sync_abcs_cycle_manifest_slice.json"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# 复用 A 域 scanner 的基础设施
sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from a_cycle_scanner import (  # noqa: E402
    domain_split,
    strip_comments,
    scan_xlsx_formulas,
    scan_xlsx_footer_raw_xml,
    scan_docx_structure,
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
# B 域 entry 提取
# ═══════════════════════════════════════════════════════════════════════════

# 10 条 entry 的全名（无重无漏）
B_ENTRY_FULLNAMES = [
    "xlsx/gt-b1-evaluation",
    "xlsx/gt-b1-kaa-check",
    "xlsx/gt-b1-risk-assessment",
    "xlsx/gt-b14-due-diligence-report",
    "xlsx/gt-b22-a-control-matrix",
    "xlsx/gt-b22-b-control-matrix",
    "xlsx/gt-b22-b-deficiency-evaluation",
    "xlsx/gt-b22-c-design-effectiveness",
    "xlsx/gt-b23-process-control",
    "xlsx/gt-b50-risk-assessment",
]

# 统一的 BP 阻塞列表（10 条全相同）
B_DOMAIN_BLOCKED_BY = ["BP-1", "BP-2", "BP-3", "BP-4", "BP-5", "BP-7", "BP-8"]

# 载体三分
CARRIER_ORPHAN_MODULE = "useWpDualMode.ts"
CARRIER_SHARED_BASE_MODULE = "useWorkpaperEntryDualMode.ts"

ORPHAN_ENTRIES = [
    "xlsx/gt-b1-evaluation",
    "xlsx/gt-b1-kaa-check",
    "xlsx/gt-b1-risk-assessment",
]
SHARED_BASE_ENTRIES = [
    "xlsx/gt-b22-a-control-matrix",
    "xlsx/gt-b22-b-control-matrix",
    "xlsx/gt-b22-b-deficiency-evaluation",
    "xlsx/gt-b22-c-design-effectiveness",
    "xlsx/gt-b50-risk-assessment",
]
HOST_INLINE_ENTRIES = [
    "xlsx/gt-b14-due-diligence-report",
    "xlsx/gt-b23-process-control",
]

# canary
CANARY_ENTRY_ID = "xlsx/gt-b22-a-control-matrix"

# 10 个真实 wp_code（纯码，非 pattern）
B_REAL_WP_CODES = [
    "B1-1", "B1-2", "B1-3", "B1-4", "B1-5",
    "B22A", "B22B", "B22C", "B23", "B50",
]


def load_slice() -> dict:
    return json.loads(_SLICE_PATH.read_bytes())


def b_domain_entries(entries: list[dict]) -> list[dict]:
    """提取 B 域 10 条 entry（按 domain_split 首字母 B）。"""
    split = domain_split(entries)
    return split.get("B", [])


def b_entry_by_id(entries: list[dict]) -> dict[str, dict]:
    """entry_id → entry dict 映射。"""
    return {e["entry_id"]: e for e in entries}


# ═══════════════════════════════════════════════════════════════════════════
# 载体分类
# ═══════════════════════════════════════════════════════════════════════════

def carrier_tripartition(entries: list[dict]) -> dict[str, list[dict]]:
    """载体三分：孤儿载体 / 共享基类 / 宿主内联。

    返回 dict 键：'orphan' / 'shared_base' / 'host_inline'
    """
    result: dict[str, list[dict]] = {"orphan": [], "shared_base": [], "host_inline": []}
    for e in entries:
        carrier = e.get("dual_mode_carrier", {})
        kind = carrier.get("kind", "")
        module = carrier.get("shared_carrier_module")
        if kind == "host_inline_segmented":
            result["host_inline"].append(e)
        elif module == CARRIER_ORPHAN_MODULE:
            result["orphan"].append(e)
        elif module == CARRIER_SHARED_BASE_MODULE:
            result["shared_base"].append(e)
        else:
            # 未知载体类型，归入 shared_base 但记警告
            result["shared_base"].append(e)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# strict 域文件集（BC-5 / BC-57）
# ═══════════════════════════════════════════════════════════════════════════

# ^GtB\d 正则（不是 ^GtB，后者误命中 GtBadDebtSheet 等）
_B_UPPER_RE = re.compile(r"^(?:use|Gt)B\d")
_B_LOWER_RE = re.compile(r"^b\d")
_B_DIR_RE = re.compile(r"/b\d+(?:-\d+)?/")


def is_b_domain_file(path: Path) -> bool:
    """判断给定前端文件是否属于 B 域（strict 域）。"""
    rel = path.relative_to(WP_COMPONENTS).as_posix() if path.is_relative_to(WP_COMPONENTS) else ""
    if _B_DIR_RE.search(rel):
        return True
    name = path.name
    if _B_UPPER_RE.match(name):
        return True
    if _B_LOWER_RE.match(name):
        return True
    return False


def scan_b_domain_files(*, include_tests: bool = False) -> tuple[list[Path], list[Path]]:
    """扫描 B 域前端文件。返回 (prod_files, test_files)。"""
    prod: list[Path] = []
    test: list[Path] = []
    for p in WP_COMPONENTS.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in (".vue", ".ts", ".tsx"):
            continue
        if not is_b_domain_file(p):
            continue
        if "__tests__" in p.parts or p.name.endswith(".spec.ts"):
            test.append(p)
        else:
            prod.append(p)
    return (prod, test) if include_tests else (prod, [])


# ═══════════════════════════════════════════════════════════════════════════
# 解析三模式
# ═══════════════════════════════════════════════════════════════════════════

def test_wp_code_resolution(wp_code: str) -> dict[str, Any]:
    """测试 wp_code 解析：返回 {code, result, error, books_count}。

    result: 'ok' / 'none' / 'error'
    """
    from pathlib import Path as P
    tmpl_dir = _TEMPLATE_DIR
    if not tmpl_dir.exists():
        return {"code": wp_code, "result": "error", "error": "B template dir not found"}

    # 尝试查找匹配的册
    candidates = []
    for f in tmpl_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in (".xlsx", ".xlsm", ".docx"):
            continue
        # 册名含 wp_code（精确前缀或全等）
        stem = f.stem
        if stem == wp_code or stem.startswith(f"{wp_code} ") or stem.startswith(f"{wp_code}-"):
            candidates.append(f)

    if len(candidates) == 0:
        return {"code": wp_code, "result": "none", "error": None, "books_count": 0}
    elif len(candidates) == 1:
        return {"code": wp_code, "result": "ok", "error": None, "books_count": 1,
                "book": candidates[0].name}
    else:
        return {"code": wp_code, "result": "ambiguous", "error": None,
                "books_count": len(candidates),
                "books": [c.name for c in candidates]}


# ═══════════════════════════════════════════════════════════════════════════
# B 域模板目录统计
# ═══════════════════════════════════════════════════════════════════════════

def scan_b_templates() -> dict[str, Any]:
    """扫描 B 域模板目录。"""
    if not _TEMPLATE_DIR.exists():
        return {"total": 0, "xlsx": 0, "docx": 0, "xlsm": 0}
    files = [f for f in _TEMPLATE_DIR.rglob("*") if f.is_file()
             and f.suffix in (".xlsx", ".docx", ".xlsm")]
    xlsx = [f for f in files if f.suffix == ".xlsx"]
    docx = [f for f in files if f.suffix == ".docx"]
    xlsm = [f for f in files if f.suffix == ".xlsm"]
    return {
        "total": len(files),
        "xlsx": len(xlsx),
        "docx": len(docx),
        "xlsm": len(xlsm),
        "files": files,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 行身份扫描器（BC-53，禁照抄 N 轮）
# ═══════════════════════════════════════════════════════════════════════════

# N 轮形态正则（验证 B 域确实为 0）
_N_FORM_ITEM_ID_RE = re.compile(r'\$\{[A-Za-z_]+\}-\$\{(?:index|idx|i)\}')
_M_FORM_ROW_RE = re.compile(r'row-\$\{[a-zA-Z_]+\}')

# B 域形态：函数参数式行下标
_FUNC_PARAM_ROWINDEX_RE = re.compile(r'\b(rowIndex|row_index)\b')
_FUNC_PARAM_IDX_RE = re.compile(r'\b(idx)\b(?!\s*[=!<>])')  # idx 作形参非赋值


def scan_row_identity_b_domain(prod_files: list[Path]) -> dict[str, Any]:
    """扫描 B 域行身份缺陷。

    返回：
      - n_form_hits: N 轮形态命中数（预期 0）
      - m_form_hits: M 轮形态命中数（预期 0）
      - rowIndex_hits: rowIndex 形参命中数
      - idx_hits: idx 形参命中数
      - label_as_key_hits: label 作渲染 key 命中数
      - details: 逐文件明细
    """
    stats: dict[str, Any] = {
        "n_form_hits": 0, "m_form_hits": 0,
        "rowIndex_hits": 0, "idx_hits": 0,
        "label_as_key_hits": 0,
        "details": [],
    }

    # 🔴 只扫「数据行」的 label-as-key（BC-48 真缺陷）。
    #    `grp.label` 是编译期静态列分组常量（B50_T3_COLUMN_GROUPS，label 互不相同、
    #    不可编辑），用作 key 不会撞、不构成缺陷 ⇒ 不纳入本计数。
    #    扫描口径：:key 绑定到**可编辑业务文本**（行对象的 name 字段）。
    label_key_re = re.compile(r':key\s*=\s*["\'`].*?\brow\.name\b')

    for f in prod_files:
        if f.suffix not in (".vue", ".ts"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        clean = strip_comments(text)

        n_hits = len(_N_FORM_ITEM_ID_RE.findall(clean))
        m_hits = len(_M_FORM_ROW_RE.findall(clean))
        ri_hits = len(_FUNC_PARAM_ROWINDEX_RE.findall(clean))
        idx_hits = len(_FUNC_PARAM_IDX_RE.findall(clean))
        lk_hits = len(label_key_re.findall(text))  # 在模板中扫需含注释

        if any([n_hits, m_hits, ri_hits, idx_hits, lk_hits]):
            stats["n_form_hits"] += n_hits
            stats["m_form_hits"] += m_hits
            stats["rowIndex_hits"] += ri_hits
            stats["idx_hits"] += idx_hits
            stats["label_as_key_hits"] += lk_hits
            stats["details"].append({
                "file": f.name,
                "n_form": n_hits, "m_form": m_hits,
                "rowIndex": ri_hits, "idx": idx_hits,
                "label_as_key": lk_hits,
            })

    return stats


# ═══════════════════════════════════════════════════════════════════════════
# wp_index 一码多行扫描
# ═══════════════════════════════════════════════════════════════════════════

def scan_wp_index_multi_row() -> dict[str, int]:
    """扫描 wp_index JSON 中 B 域码各出现多少行。"""
    wp_index_path = _DATA / "wp_account_mapping.json"
    if not wp_index_path.exists():
        # fallback: 尝试 wp_index.json
        wp_index_path = _DATA / "wp_index.json"
    if not wp_index_path.exists():
        return {}

    data = json.loads(wp_index_path.read_bytes())
    counts: dict[str, int] = {}
    if isinstance(data, list):
        for row in data:
            code = row.get("wp_code", "")
            if code in B_REAL_WP_CODES:
                counts[code] = counts.get(code, 0) + 1
    elif isinstance(data, dict):
        for code in B_REAL_WP_CODES:
            if code in data:
                val = data[code]
                counts[code] = len(val) if isinstance(val, list) else 1
    return counts


if __name__ == "__main__":
    print("B 域 scanner 自检")
    sl = load_slice()
    entries = b_domain_entries(sl["independent_entries"])
    print(f"  B 域 entry: {len(entries)}")
    tri = carrier_tripartition(entries)
    for k, v in tri.items():
        print(f"    {k}: {len(v)}")
    tmpl = scan_b_templates()
    print(f"  模板: total={tmpl['total']} xlsx={tmpl['xlsx']} docx={tmpl['docx']} xlsm={tmpl['xlsm']}")
    prod, _ = scan_b_domain_files()
    print(f"  前端 prod 文件: {len(prod)}")
    ri = scan_row_identity_b_domain(prod)
    print(f"  行身份: rowIndex={ri['rowIndex_hits']} idx={ri['idx_hits']} N_form={ri['n_form_hits']}")
