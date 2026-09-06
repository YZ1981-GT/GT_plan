"""底稿模板查找子模块（pass4 拆分自 wp_template_init_service）

职责：模板索引加载 + 按 wp_code 查找模板文件（xlsx/xlsm/docx/doc）+
sheet 名归一化 / 历史遗留 sheet 过滤工具。

逐字搬运自 wp_template_init_service.py，行为零变更。主文件 re-export 本模块
对外符号以保持 `from app.services.wp_template_init_service import ...` 导入路径不变。
"""
from __future__ import annotations

import functools
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
    """根据 wp_code 查找主模板文件（**权威目录**解析）

    优先匹配：含"审定表"或"常规程序"的文件 > 文件名最短的。
    对于多文件底稿（如 D2 有 D2-1至D2-4），返回审定表文件。
    对于子表（如 D2-2/E1-3），如果独立文件不存在，回退到主表文件
    （主表 xlsx 通常包含所有子表 sheet，如 "D2-1至D2-4 应收账款-审定表明细表"）。

    🔴 本函数体是**权威侧**解析。模块末尾会把同名的模块属性重绑定为「覆盖层优先」的
    薄封装，并把本函数留在 :data:`find_template_file_unresolved` 上（见文件末尾
    「公开入口 —— 覆盖层薄封装」一节的理由）。
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


# ---------------------------------------------------------------------------
# 子码判据（Task 58 / Requirement 9.4）
# ---------------------------------------------------------------------------
#
# 🔴 `^A\d+-\d+` 是**存量缺陷**，不是设计：它只把 A 类子码当子码，于是 `B2-1` /
# `B18-3-1` / `B40-1` 这类 B 子码落进下面「主程序表：xlsx 优先」分支，被
# `find_template_file()` 的「终极回退：用主表」抢到父级 XLSX。2026-08-29 逐条实测：
# 28 个 `word-template` wp_code 里 **9 个**（B18-3-1 / B18-3-2 / B2-1 / B2-11 /
# B2-3 / B2-6 / B2-8 / B40-1 / B40-2）磁盘上都有自己的 DOCX，却全部解析到父级 XLSX。
#
# 修法**不是**把这个正则改成字母类无关：那会让 `D2-2` / `E1-3` 这类 Excel 子表
# 也走子码分支，而它们的真实载体是范围式命名的父文件（`D2-1至D2-4 …xlsx`），子码
# 分支的同名前缀判据匹配不到 ⇒ 数百个 wp_code 解析成 None（实测过）。
#
# 正确修法是**只把 DOCX 那一步提到前面并让它字母类无关**（见
# `find_template_file_any` 的 ① 段）：`resolve_own_docx_or_none()` 按
# `canonical_paths.specificity_rank` 取最具体载体、且类型门只放 DOCX，所以
# * 有自己 DOCX 的子码（含 B/S）拿到自己的 DOCX；
# * 没有自己 DOCX 的子码（D2-2 等）原样落回下方既有 xlsx 链，行为零变化。
#
# 本常量保留 A-only 形态**只**用于「A 子码不得回退父级 XLSX」这条既有严格性
# （下方 ② 段），不再承担「是不是子码」的判断。
_LEGACY_A_ONLY_SUB_CODE_RE = re.compile(r"^A\d+-\d+")


def _resolve_most_specific_docx(wp_code: str) -> Path | None:
    """该 wp_code **自有**的最具体 DOCX 载体（Task 58 统一 Word resolver 的唯一入口）。

    委派 `workpaper_sync.word_resolution`，**不**在本模块复制具体度/类型判据 ——
    复制会让任一侧被短路都不改变行为（变异检验判 GREEN）。

    局部 import：`word_resolution` 依赖 `app.core.config`（读 `STORAGE_ROOT`），
    模块级 import 会让本模块在纯路径场景（无配置）下不可导入。
    """
    from app.services.workpaper_sync.word_resolution import resolve_own_docx_or_none

    return resolve_own_docx_or_none(wp_code)


def find_all_template_files(wp_code: str) -> list[Path]:
    """查找 wp_code 对应的所有模板文件（多文件底稿，**权威目录**解析）。

    A 子码分支调 ``find_template_file_any_unresolved`` 而不是公开入口，保持权威侧闭环
    —— 否则 ``resolve_all_templates`` 会经它再次进入覆盖层。
    """
    is_sub_code = bool(_LEGACY_A_ONLY_SUB_CODE_RE.match(wp_code))
    if is_sub_code:
        single = find_template_file_any_unresolved(wp_code)
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
    """Find template file of any format (xlsx/xlsm/docx/doc)（**权威目录**解析）

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

    # ── ① 所有适用 wp_code：自有 DOCX 优先（Requirement 9.4 / P40）─────────
    #
    # 提到 A-only 分支**之前**且字母类无关，是本次唯一的行为变更点。加法性质：
    # 命中即返回自己的 DOCX，不命中原样落回下方既有链（含 A 子码的 xlsx 严格分支
    # 与主码的 xlsx 优先分支），故 `D2-2` / `E1-3` 这类无自有 DOCX 的子码零变化。
    #
    # 桥只认 **exact-own** DOCX 且 **无自有工作簿**（见 `resolve_own_docx_or_none`）：
    # 放宽任一条都会倒转具体度或翻转格式，1539 个 wp_code 的全量比对实测过
    # （`B30-13-1` / `B60-1` 具体度倒转、`S33-1` 格式翻转）。
    most_specific_docx = _resolve_most_specific_docx(wp_code)
    if most_specific_docx is not None:
        return most_specific_docx

    # ── ② A 子码既有严格性：不得回退父程序表 XLSX ─────────────────────────
    is_sub_code = bool(_LEGACY_A_ONLY_SUB_CODE_RE.match(wp_code))

    if is_sub_code:
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
    result = find_template_file_unresolved(wp_code)
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


# ═══════════════════════════════════════════════════════════════════════════
# 公开入口 —— 覆盖层薄封装（spec excel-template-override-layer Task 8）
# ═══════════════════════════════════════════════════════════════════════════
#
# 上面三个 `def` 是**权威目录**解析。这里把它们各留一个 `*_unresolved` 别名给
# `wp_template_override` 当定位基准，再把三个**公开名**重绑定为「覆盖层优先」的薄封装。
#
# ## 🔴 为什么用「模块末尾重绑定」而不是把实现改名成 `*_unresolved`
#
# 改名试过，被一条既有判据打红：`test_task58_word_canonical_resolver.py` 的
# `test_finder_no_longer_uses_a_only_regex_for_sub_code_decision` 用 **AST** 断言
# 「名为 `find_template_file_any` 的 FunctionDef 里，对 `_resolve_most_specific_docx`
# 的调用早于 `_LEGACY_A_ONLY_SUB_CODE_RE.match`」—— 它锁的是「统一 Word resolver 没成
# 死代码」这件事。把实现改名后，该名字下的函数体变成三行薄封装，判据必红。
#
# 重绑定同时满足两侧：AST 看到的 `FunctionDef` 仍是原实现（Task 58 判据绿），
# 运行时的模块属性是覆盖层优先的 wrapper（Requirement 2.1 生效）。
#
# `functools.wraps` 保住 `__wrapped__`，于是 `inspect.signature` 仍报
# `(wp_code)` —— Requirement 2.3「签名与返回类型不变」也不破。
#
# ## 🔴 旧签名只能解析到事务所层，这是有意的
#
# 四层优先级是 `project > group_custom > firm_default > authoritative`，其中
# `project` / `group_custom` 需要 `project_id` / `group_id`。旧入口只收 `wp_code`，
# 所以经它解析时那两层**不参与**。这不是缺陷：Requirement 2.3 要求签名不变，给旧入口
# 加参数会波及全库约 50 个调用点。需要项目级覆盖的新代码直接用
# `wp_template_override.resolve_template(wp_code, project_id=..., group_id=...)`，
# 它同时给出 `origin` / `version_id` / `sha256`（Requirement 2.2）。
#
# 于是旧调用方**自动**获得事务所级覆盖（"改一次模板对所有项目生效"正是这个场景），
# 项目级覆盖要求调用方显式声明它在哪个项目里 —— 解析结果不再依赖隐式上下文。

#: 权威侧解析（不经覆盖层）。`wp_template_override` 用它们作定位基准与扩展名参照；
#: 若它回调公开入口就会成环。
find_template_file_unresolved = find_template_file
find_all_template_files_unresolved = find_all_template_files
find_template_file_any_unresolved = find_template_file_any


@functools.wraps(find_template_file_unresolved)
def _find_template_file_override_first(wp_code: str) -> Path | None:
    from app.services.wp_template_override import resolve_template

    resolution = resolve_template(wp_code)
    return resolution.path if resolution is not None else None


@functools.wraps(find_all_template_files_unresolved)
def _find_all_template_files_override_first(wp_code: str) -> list[Path]:
    from app.services.wp_template_override import resolve_all_templates

    return [r.path for r in resolve_all_templates(wp_code)]


@functools.wraps(find_template_file_any_unresolved)
def _find_template_file_any_override_first(wp_code: str) -> Path | None:
    from app.services.wp_template_override import resolve_template_any

    resolution = resolve_template_any(wp_code)
    return resolution.path if resolution is not None else None


_find_template_file_override_first.__doc__ = (
    "根据 wp_code 查找主模板文件（覆盖层优先，回落权威目录）。\n\n"
    "权威侧实现见 `find_template_file_unresolved`；带来源标记的版本见 "
    "`wp_template_override.resolve_template`。"
)
_find_all_template_files_override_first.__doc__ = (
    "查找 wp_code 对应的所有模板文件（覆盖层**逐份**优先，回落权威目录）。\n\n"
    "同一 wp_code 的多份权威文件里只覆盖了一份时，其余仍返回权威文件 —— "
    "整组一起换掉会让「改一份」变成「必须全改」。"
)
_find_template_file_any_override_first.__doc__ = (
    "Find template file of any format（覆盖层优先，回落权威目录）。\n\n"
    "权威侧实现见 `find_template_file_any_unresolved`。"
)

find_template_file = _find_template_file_override_first
find_all_template_files = _find_all_template_files_override_first
find_template_file_any = _find_template_file_any_override_first
