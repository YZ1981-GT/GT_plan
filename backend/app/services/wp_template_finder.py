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


def _wp_code_filename_prefix_ok(filename: str, wp_code: str) -> bool:
    """filename 以 wp_code 开头，且 wp_code 之后紧跟的不是数字。

    避免「E1-2」误命中「E1-26至E1-32...」（字符串前缀碰撞：E1-2 是 E1-26 的前缀）。
    仍允许 `-`/空白/「至」/中文/字母后缀（如 D2→D2-1至D2-4、A9→A9-1、E1→E1-14）。

    同类真实碰撞（本函数的存在理由）::

        D4-1  vs  "D4-12 营业收入-合同检查…"      → False（'2' 是数字）
        D4-2  vs  "D4-21营业收入-关联方检查…"      → False
        F2-2  vs  "F2-29至F2-35 …检查类…"          → False
        F2-2  vs  "F2-21至F2-26 …盘点类…"          → False
        D4-1  vs  "D4-1至D4-4 营业收入 - 审定表…"  → True （'至' 非数字）
    """
    if not filename.startswith(wp_code):
        return False
    rest = filename[len(wp_code):]
    return not rest[:1].isdigit()


#: 旧名别名（2026-07 引入时叫 `_code_prefix_boundary_ok`）。保留以免模块外引用断裂。
_code_prefix_boundary_ok = _wp_code_filename_prefix_ok


#: 整册合并本文件名：`{编码}[空格?]{中文短名}`，编码后（最多一个空格后）跟 CJK，
#: 无 `-子号`、无「至」。现存三例：``D4收入底稿.xlsx`` / ``D4 收入底稿.xlsx`` / ``F2存货.xlsx``。
#:
#: 🔴 2026-09-19：空格形态**必须**被认成整册本。原注释写「权威惯例是不带空格的那份
#: （带空格那份是工作树新增）」——该前提已失效：``git ls-files`` 实测两份**都已入库**，
#: 且带空格那份才是权威：
#:
#: * ``D4 收入底稿.xlsx``（199176 B, sha ``b8fb92d4…``）= sync 契约 ``d4.revenue_detail``
#:   的 ``TemplateRef`` 钉住的那份，且 ``xl/workbook.xml`` **无** ``<externalReference>``
#:   （``scripts/fix/sanitize_d4_template_external_links.py`` 就是净化它的，旁边留有
#:   ``.preclean.bak``）；
#: * ``D4收入底稿.xlsx``（352950 B）未净化，带 36 个 ``xl/externalLinks/`` 部件。
#:
#: 本模块保持**纯路径解析**（不读 xlsx 字节），所以「净化与否」的取舍不在这里做：本函数
#: 只负责**枚举候选**（见 :func:`find_whole_workbook_templates`），由需要字节事实的调用方
#: （`wp_onlyoffice_router._resolve_whole_workbook_template`）挑选。
_WHOLE_EXCEL_NAME_RE = re.compile(r"^[A-Z]+\d+ ?[\u4e00-\u9fff]")


def _is_whole_excel_template_name(name: str) -> bool:
    """是否为「整册合并本」文件名（与范围式拆分包互斥）。

    True ::

        D4收入底稿.xlsx
        D4 收入底稿.xlsx
        F2存货.xlsx

    False ::

        D4-1至D4-4 营业收入 - 审定表明细表.xlsx      # 编码后是 '-'
        F2-1至F2-14 存货实质性程序-审定表明细表类.xlsx # 同上
        D4-33至D4-36 其他业务收入.xlsx                # 同上
    """
    if not name:
        return False
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return bool(_WHOLE_EXCEL_NAME_RE.match(stem))


def find_whole_workbook_templates(wp_code: str) -> tuple[Path, ...]:
    """该 wp_code 的**全部**整册合并本候选，确定性排序（纯路径解析，不读 xlsx 字节）。

    整册本**不在** ``_index.json`` 里（索引只收范围式拆分包），因此只能扫权威目录。
    这也是它必须走独立入口的原因：普通链路（``find_template_file`` /
    ``find_all_template_files``）全部以索引为准，天然不会返回整册本。

    前缀用 :func:`_wp_code_filename_prefix_ok` 而非裸 ``startswith``，避免
    ``D4`` 命中假想的 ``D40…``。

    返回**多个**而不是一个：D4 目录下同时存在净化前后两份同名整册本，而「哪份可用」是
    字节事实（有无 ``<externalReference>``），不能在纯路径层裁决。排序按
    ``(名字长度, 名字)``，不依赖目录枚举顺序。
    """
    if not wp_code:
        return ()
    subdir = TEMPLATES_DIR / wp_code[0]
    if not subdir.exists():
        return ()
    hits = [
        f
        for f in subdir.iterdir()
        if f.suffix.lower() in (".xlsx", ".xlsm")
        and _wp_code_filename_prefix_ok(f.name, wp_code)
        and _is_whole_excel_template_name(f.name)
    ]
    hits.sort(key=lambda p: (len(p.name), p.name))
    return tuple(hits)


def find_whole_workbook_template(wp_code: str) -> Path | None:
    """该 wp_code 的整册合并本**首个**候选（纯路径口径）。

    🔴 需要「可用的那份」（无断链外部引用）的调用方**不要**用本函数，用
    ``wp_onlyoffice_router._resolve_whole_workbook_template`` —— 它在本函数的候选集上
    加一道字节判据。本函数保留是为了让纯路径场景（无需读 xlsx）仍有入口。
    """
    candidates = find_whole_workbook_templates(wp_code)
    return candidates[0] if candidates else None


#: 主模板优先级阶梯（**按序**，前一级命中即不看后一级）。
#:
#: 🔴 「审定」必须**严格高于**「常规程序」，不能像原来那样 `or` 成同一级：
#: 索引里 ``wp_code == "D4"`` 有 8 条拆分包，其中 ``D4-12 营业收入-合同检查
#: （Leap-常规程序）.xlsx`` 排在 ``D4-1至D4-4 … 审定表明细表（Leap-常规程序）.xlsx``
#: 之前，两者都含「常规程序」⇒ 同级下由**索引顺序**决定结果，D4 拿到了「合同检查」。
#: F2 同理拿到了「会计政策」。
#:
#: 用「审定」而不是「审定表」：F2 的主表叫「审定**明细**表类」，不含连续三字「审定表」。
_PRIMARY_TEMPLATE_TIERS: tuple[str, ...] = ("审定", "常规程序")


def _pick_by_tier(names_to_paths: list[tuple[str, Path]]) -> Path | None:
    """按 :data:`_PRIMARY_TEMPLATE_TIERS` 逐级挑选；同级内按 (名字长度, 名字) 定序。

    同级内显式排序而不是「取遍历到的第一个」：后者让结果依赖索引/目录枚举顺序，
    正是 D4/F2 错配的机制。
    """
    for tier in _PRIMARY_TEMPLATE_TIERS:
        hits = [(n, p) for n, p in names_to_paths if tier in n]
        if hits:
            hits.sort(key=lambda item: (len(item[0]), item[0]))
            return hits[0][1]
    return None


#: 实质性程序表码：``D4A`` / ``F2A`` / ``K3A`` 这类「主码 + **A**」编码。磁盘上没有自己的
#: 模板文件，载体就是主码的主工作簿（程序表是主工作簿里的一个 sheet）。
#:
#: 🔴 后缀**只认 `A`**，不能放宽成任意字母。`H1F` / `G7L` / `G7E` 形状相同但语义完全不同：
#: 它们是渲染宿主组件名（``GtH1FixedAssets`` / ``GtG7LongTermEquityMain``）被
#: ``WP_CODE_EXTRACTION_PATTERN`` 机械抽出来的**产物**，不是真 wp_code。
#: ``pilot_h1_grouped_dynamic`` / ``pilot_g7_two_level_dynamic`` 的选型门把
#: 「这些码在 finder 上解析不到任何文件」当作可打红判据（零回退的最强形态是根本没有回退），
#: 一旦它们能解析到东西，契约的 source_ref 就可能指向另一份底稿的单元格。
_PROGRAM_TABLE_CODE_RE = re.compile(r"^([A-Z]+\d+)A$")

#: 渲染 schema 目录：``{wp_code}.yaml`` 是该码的**配置真源**，自带 ``template_path``。
_RENDER_SCHEMA_DIR = BACKEND_DIR / "data" / "ledger_adapters" / "wp_render_schema"


def _has_own_render_schema(wp_code: str) -> bool:
    """该码是否有独立 render schema（配置真源已指定模板 ⇒ finder 不得再猜）。

    ``D2A`` / ``E1A`` / ``G7A`` 属于这一类：``D2A.yaml`` 明确声明了 ``template_path``，
    平台渲染它时以该 YAML 为唯一真源。此时 finder 若还去回落主码工作簿，就多出一个
    与配置并列的第二真源 —— ``pilot_d2_large_json`` 的选型门正是拿
    「``find_template_file("D2A")`` 解析不到」来锁这件事。
    """
    if not wp_code:
        return False
    return (_RENDER_SCHEMA_DIR / f"{wp_code}.yaml").is_file()


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
        # 优先级阶梯：审定 > 常规程序（见 _PRIMARY_TEMPLATE_TIERS 的理由）
        existing = [
            (e["filename"], TEMPLATES_DIR / e["relative_path"])
            for e in candidates
            if (TEMPLATES_DIR / e["relative_path"]).exists()
        ]
        tiered = _pick_by_tier(existing)
        if tiered is not None:
            return tiered
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
        # 同一优先级阶梯（边界匹配：wp_code 后不得紧跟数字，避免 E1-2 命中 E1-26）
        on_disk = [
            (f.name, f)
            for f in sorted(template_subdir.iterdir())
            if _wp_code_filename_prefix_ok(f.name, wp_code)
            and f.suffix.lower() in (".xlsx", ".xlsm")
        ]
        tiered = _pick_by_tier(on_disk)
        if tiered is not None:
            return tiered
        # 其次最短文件名
        for f in sorted(template_subdir.iterdir(), key=lambda x: len(x.name)):
            if _wp_code_filename_prefix_ok(f.name, wp_code) and f.suffix.lower() in (".xlsx", ".xlsm"):
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

    # ── 实质性程序表码回落（D4A / F2A / K3A …）──────────────────────────────
    #
    # 放在**所有**匹配之后，纯加法：这类码磁盘上没有自己的文件（原先一路走到底返回
    # None），载体是主码的主工作簿。若将来真出现 `D4A …xlsx`，上面的分支会先命中，
    # 本回落不生效。
    #
    # 两道收窄，缺一条就会踩到别的 spec 的判据（见两个常量/函数各自的说明）：
    #   * 后缀只认 `A` —— 否则 `H1F` / `G7L` / `G7E` 这些**名字提取产物**也被回落；
    #   * 跳过有独立 render schema 的码 —— 否则 `D2A` 的配置真源旁边多出第二真源。
    #
    # 递归调 `find_template_file_unresolved` 而非模块全局 `find_template_file`：
    # 后者在模块末尾被重绑定成覆盖层薄封装，权威侧递归到它会穿出覆盖层
    # （与 `find_all_template_files` 调 `find_template_file_any_unresolved` 同理）。
    program_table = _PROGRAM_TABLE_CODE_RE.match(wp_code)
    if program_table and not _has_own_render_schema(wp_code):
        return find_template_file_unresolved(program_table.group(1))

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
