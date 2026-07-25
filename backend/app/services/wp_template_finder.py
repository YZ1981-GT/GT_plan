"""底稿模板查找子模块（pass4 拆分自 wp_template_init_service）

职责：模板索引加载 + 按 wp_code 查找模板文件（xlsx/xlsm/docx/doc）+
sheet 名归一化 / 历史遗留 sheet 过滤工具。

逐字搬运自 wp_template_init_service.py，行为零变更。主文件 re-export 本模块
对外符号以保持 `from app.services.wp_template_init_service import ...` 导入路径不变。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BACKEND_DIR / "wp_templates"
INDEX_FILE = TEMPLATES_DIR / "_index.json"

# 缓存模板索引
_index_cache: list[dict] | None = None

# Sheet 级独立模板：优先于「F2-21至F2-26」等包内近空 sheet。
# F2-22/F2-23 在线编辑应对齐通用底稿 G2-6-2 / G2-6-1（Word）。
_EXPLICIT_TEMPLATE_RELPATHS: dict[str, str] = {
    "F2-22": "F/F2-22 存货监盘计划.docx",
    "F2-23": "F/F2-23 存货监盘小结.docx",
}


# ---------------------------------------------------------------------------
# F2 / F3 多文件 sheet 合并去重工具（spec workpaper-d-sales-cycle, ADR D2 + D3）
# ---------------------------------------------------------------------------


def _normalize_sheet_name(name: str) -> str:
    """归一化 sheet 名（spec D2 ADR）。

    规则（按顺序）:
      1. 中文圆括号 `（…）` → 英文 `(…)`，并 strip 首尾空白
      2. 含 `GT_Custom` → 归一为 `"GT_Custom"`（多文件 GT 内部 sheet 视为同名）
      3. 含 `底稿目录` → 归一为 `"底稿目录"`（多文件底稿目录视为同名）
      4. 其他：剔除全部空白字符（含中间空格、tab、全角空格）后返回

    幂等：normalize(normalize(x)) == normalize(x)（PBT P2 验证）
    """
    if name is None:
        return ""
    n = str(name).replace("（", "(").replace("）", ")").strip()
    if "GT_Custom" in n:
        return "GT_Custom"
    if "底稿目录" in n:
        return "底稿目录"
    # 剔除内部所有空白（中英文、全角、tab、换行）以避免空格差异导致漏去重
    return re.sub(r"\s+", "", n)


def _should_skip_historical_sheet(name: str) -> bool:
    """判断是否为历史遗留 sheet（spec D3 ADR + F-F2 ADR-F3 + J-F1 — 应在归一化前过滤）。

    匹配规则（任一命中即跳过）:
      - 含 "修订前"（如 "主营业务收入审计程序表 D4A（修订前）"、"G1A-修订前"）
      - 含 "（原）" 或 "(原)"（如 "D7A（原）"、"D8A(原)"）
      - 含 G+数字 编号且含 "删除" 或 "移至"（F 循环新模式：F2-38/F2-47/F2-52
        含 "存货计价测试程序G2-8-删除"、"G2-8-4-移至分析类" 等历史遗留 sheet）
      - 以 "-删除" 结尾（J 循环通用模式：如 "股份支付检查表J1-10-删除"、
        "IPO企业股权激励工具关注的审计重点-删除"、"首发业务解答二-删除"）
      - 含 "（示例）"/"(示例)"，或以 "示例"/"示例）"/"示例)" 结尾（F 循环示例 sheet：
        "函证差异检查表（示例）"、"合同履约成本测试（示例）"、"访谈记录与核对示例"）
    """
    if name is None:
        return False
    s = str(name)
    if "修订前" in s or "（原）" in s or "(原)" in s:
        return True
    # F-F2 ADR-F3: G+数字编号 + 删除/移至（注意 G 不限于开头位置）
    if re.search(r"G\d+", s) and ("删除" in s or "移至" in s):
        return True
    # J-F1: 以 "-删除" 结尾的通用历史遗留模式（J 循环 5 个 sheet）
    if s.endswith("-删除"):
        return True
    # F-F2 ADR-F3: 示例 sheet（括号包裹或末尾）
    if "（示例）" in s or "(示例)" in s:
        return True
    if s.endswith("示例") or s.endswith("示例）") or s.endswith("示例)"):
        return True
    return False


def _load_index() -> list[dict]:
    """加载模板索引（带缓存）"""
    global _index_cache
    if _index_cache is not None:
        return _index_cache
    if not INDEX_FILE.exists():
        logger.warning("模板索引文件不存在: %s", INDEX_FILE)
        return []
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    _index_cache = data.get("files", [])
    return _index_cache


def _code_prefix_boundary_ok(filename: str, wp_code: str) -> bool:
    """filename 以 wp_code 开头，且 wp_code 之后紧跟的不是数字。

    避免「E1-2」误命中「E1-26至E1-32...」（字符串前缀碰撞：E1-2 是 E1-26 的前缀）。
    仍允许 `-`/空白/「至」/中文/字母后缀（如 D2→D2-1至D2-4、A9→A9-1、E1→E1-14）。
    """
    if not filename.startswith(wp_code):
        return False
    rest = filename[len(wp_code):]
    return not rest[:1].isdigit()


def find_template_file(wp_code: str) -> Path | None:
    """根据 wp_code 查找主模板文件

    优先匹配：含"审定表"或"常规程序"的文件 > 文件名最短的。
    对于多文件底稿（如 D2 有 D2-1至D2-4），返回审定表文件。
    对于子表（如 D2-2/E1-3），如果独立文件不存在，回退到主表文件
    （主表 xlsx 通常包含所有子表 sheet，如 "D2-1至D2-4 应收账款-审定表明细表"）。
    """
    index = _load_index()
    # 精确匹配
    candidates = [
        e for e in index
        if e["wp_code"] == wp_code and e["format"] in ("xlsx", "xlsm")
    ]
    if candidates:
        # 优先选择含"审定表"或"常规程序"的文件
        for c in candidates:
            if "审定表" in c["filename"] or "常规程序" in c["filename"]:
                full_path = TEMPLATES_DIR / c["relative_path"]
                if full_path.exists():
                    return full_path
        # 其次选择文件名最短的
        candidates.sort(key=lambda e: len(e["filename"]))
        rel_path = candidates[0]["relative_path"]
        full_path = TEMPLATES_DIR / rel_path
        if full_path.exists():
            return full_path

    # 模糊匹配：文件名以 wp_code 开头
    prefix = wp_code[0]
    template_subdir = TEMPLATES_DIR / prefix
    if template_subdir.exists():
        # 优先含"审定表"（边界匹配：wp_code 后不得紧跟数字，避免 E1-2 命中 E1-26）
        for f in sorted(template_subdir.iterdir()):
            if _code_prefix_boundary_ok(f.name, wp_code) and f.suffix.lower() in (".xlsx", ".xlsm"):
                if "审定表" in f.name or "常规程序" in f.name:
                    return f
        # 其次最短文件名
        for f in sorted(template_subdir.iterdir(), key=lambda x: len(x.name)):
            if _code_prefix_boundary_ok(f.name, wp_code) and f.suffix.lower() in (".xlsx", ".xlsm"):
                return f

        # 子表回退：如 D2-2 找不到，尝试包含范围式命名的文件（D2-1至D2-4）
        if "-" in wp_code:
            primary = wp_code.split("-")[0]
            sub_num = wp_code.split("-")[1]
            # 尝试解析为数字进行范围判断
            try:
                sub_num_int = int(re.sub(r"[A-Za-z]", "", sub_num))
            except (ValueError, TypeError):
                sub_num_int = None

            for f in sorted(template_subdir.iterdir()):
                if f.suffix.lower() not in (".xlsx", ".xlsm"):
                    continue
                # 匹配模式: 文件名含 "{primary}-N至{primary}-M" 且 sub_num 在范围内
                if f.name.startswith(primary + "-") and "至" in f.name:
                    # 从文件名提取范围: "D4-22至D4-32..." → start=22, end=32
                    range_match = re.search(
                        rf"{re.escape(primary)}-(\d+).*至.*{re.escape(primary)}-(\d+)",
                        f.name,
                    )
                    if range_match and sub_num_int is not None:
                        start = int(range_match.group(1))
                        end = int(range_match.group(2))
                        if start <= sub_num_int <= end:
                            return f
                    elif not range_match:
                        # 无法解析范围但文件名匹配模式，保守返回
                        return f
            # 终极回退：用主表
            for f in sorted(template_subdir.iterdir()):
                if f.name.startswith(primary + " ") and f.suffix.lower() in (".xlsx", ".xlsm"):
                    return f

    return None


def find_all_template_files(wp_code: str) -> list[Path]:
    """查找 wp_code 对应的所有模板文件（多文件底稿）"""
    is_sub_code = bool(re.match(r"^A\d+-\d+", wp_code))
    if is_sub_code:
        single = find_template_file_any(wp_code)
        return [single] if single else []

    index = _load_index()
    candidates = [
        e for e in index
        if e["wp_code"] == wp_code and e["format"] in ("xlsx", "xlsm", "docx")
    ]
    results = []
    for c in candidates:
        full_path = TEMPLATES_DIR / c["relative_path"]
        if full_path.exists():
            results.append(full_path)
    return results


def _match_filename_prefix(filename: str, wp_code: str) -> bool:
    """True if filename belongs to sub-code wp_code (A9-1向… or A10-1 …)."""
    if filename.startswith(f"{wp_code} "):
        return True
    if filename.startswith(wp_code) and re.match(rf"^{re.escape(wp_code)}(\s|[^-\d])", filename):
        return True
    return False


def _find_docx_on_disk(wp_code: str) -> Path | None:
    prefix = wp_code[0] if wp_code else ""
    subdir = TEMPLATES_DIR / prefix
    if not subdir.exists():
        return None
    matches = sorted(
        f for f in subdir.iterdir()
        if f.suffix.lower() in (".docx", ".doc") and _match_filename_prefix(f.name, wp_code)
    )
    return matches[0] if matches else None


def _find_docx_by_index_or_disk(wp_code: str) -> Path | None:
    index = _load_index()
    prefix_matches = [
        e for e in index
        if e["format"] in ("docx", "doc") and _match_filename_prefix(e["filename"], wp_code)
    ]
    if prefix_matches:
        prefix_matches.sort(key=lambda e: len(e["filename"]))
        full_path = TEMPLATES_DIR / prefix_matches[0]["relative_path"]
        if full_path.exists():
            return full_path
    return _find_docx_on_disk(wp_code)


def find_template_file_any(wp_code: str) -> Path | None:
    """Find template file of any format (xlsx/xlsm/docx/doc)

    P2-2: 扩展模板查找支持 docx/doc 格式。
    优先返回 xlsx/xlsm，其次 docx/doc。
    PRE-1: 子码 docx（索引挂父 wp_code）按文件名前缀 fallback；
    子码（A9-1 等）**禁止**回退到父程序表 xlsx。
    """
    explicit = _EXPLICIT_TEMPLATE_RELPATHS.get(wp_code)
    if explicit:
        path = TEMPLATES_DIR / explicit
        if path.exists():
            return path

    is_sub_code = bool(re.match(r"^A\d+-\d+", wp_code))

    if is_sub_code:
        # docx 子码优先（A9-1、A10-1…）
        docx = _find_docx_by_index_or_disk(wp_code)
        if docx:
            return docx
        # xlsx 子码（A7-1、A10-2…）：仅匹配同名前缀文件
        index = _load_index()
        xlsx_matches = [
            e for e in index
            if e["format"] in ("xlsx", "xlsm") and _match_filename_prefix(e["filename"], wp_code)
        ]
        if xlsx_matches:
            xlsx_matches.sort(key=lambda e: len(e["filename"]))
            full_path = TEMPLATES_DIR / xlsx_matches[0]["relative_path"]
            if full_path.exists():
                return full_path
        prefix = wp_code[0]
        subdir = TEMPLATES_DIR / prefix
        if subdir.exists():
            for f in sorted(subdir.iterdir()):
                if f.suffix.lower() in (".xlsx", ".xlsm") and _match_filename_prefix(f.name, wp_code):
                    return f
        return None

    # 主程序表：xlsx 优先
    result = find_template_file(wp_code)
    if result:
        return result
    index = _load_index()
    candidates = [
        e for e in index
        if e["wp_code"] == wp_code and e["format"] in ("docx", "doc")
    ]
    if candidates:
        rel_path = candidates[0]["relative_path"]
        full_path = TEMPLATES_DIR / rel_path
        if full_path.exists():
            return full_path
    return _find_docx_by_index_or_disk(wp_code)


def list_available_templates() -> list[dict]:
    """列出所有可用模板（供前端选择）"""
    index = _load_index()
    # 按 wp_code 去重，只返回主文件
    seen = set()
    result = []
    for e in sorted(index, key=lambda x: (x["wp_code"], len(x["filename"]))):
        code = e["wp_code"]
        if code in seen or code == "_ref":
            continue
        seen.add(code)
        result.append({
            "wp_code": code,
            "filename": e["filename"],
            "format": e["format"],
            "size_kb": e["size_kb"],
        })
    return result
