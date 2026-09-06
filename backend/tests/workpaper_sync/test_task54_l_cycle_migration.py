# -*- coding: utf-8 -*-
r"""Task 54 守卫 —— L 循环（债务循环）Excel 独立 entry 逐一迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 54
Properties: 20 / 28 / 69 / 70
Requirements: 6.1 · 6.2 · 6.10 · 12.1 · 12.4 · 12.10 · 12.11 · 12.12 · 14.1

═══ 本文件守什么 ═══

两份产物（`workpaper_sync_l_cycle_manifest_slice.json` /
`workpaper_sync_l_cycle_deletion_plan.json`）里的**每个数字与每条结论**都必须能从磁盘现算
出来。判据一律落在「行为 / 结构 / 真实执行」上，不是「字符串存在」：

* 消费边 = statement-position import **路径**字面量，且排除双引号字符串内的匹配
  （`workpaperSyncLegacyBaseline.generated.ts` 的 JSON `"snippet"` 字段含完整 `from '...'`
  形态；不排除会把死桩算成活的）。
* orphan 判定用**可达性**而非入度；barrel 入边用路径解析而非 stem 相等。
* 剥注释**保留行号**（同长空白替换）。删行式剥注释会让全部 `#Lnn` 锚点整体上移 ⇒ 假红。
* 「某声明是否真生效」落到**模板形态判据**（遍历 + 外层门控 + 内层嵌套三要素），
  不看数据层是否声明过 —— G7 那轮的教训是「模型声明齐全、`.vue` 零引用」。

═══ L 循环相对前八轮的四处形态差异（照抄 K 的判据必假红）═══

1. **dual-mode 载体三分**：L1/L2 共享 composable + 宿主门控（开关可兑现）· L3/L4 **无载体** ·
   L5~L8 子 Tab 专用 composable。K 是二分（宿主内联 IIFE / 宿主真 import）。
2. 🔴 **L5~L8 的开关是 inert**：`el-segmented` 存在、`v-model` 绑到 `dualMode.mode`，但
   以 mode 为条件的 `v-if` 现算 **0** 处、文件内 `GtOnlyOfficeSheet` 现算 **0** 次
   ⇒ 切到 OnlyOffice 只写 localStorage，DOM 不变。本文件用 L1/L2 作**有效对照组**
   证明扫描器不是恒 0（否则「0」与「扫描器写坏了」不可区分）。
3. **HTML 对端不经 `useChecklistPersistence`**：L 域该符号命中 **0**（K 是 13/13）。
   每条 entry 一份 `useL{n}FormData` + `@/services/apiProxy` 的 `api` 直调同一端点。
4. **9 个 `useL*DualMode.ts` 文件 vs 8 条 entry**：L3 在两个目录各有一份（模式枚举与
   localStorage 键都不同）。K 那份是 13 == 13，照抄「文件数 == entry 数」必假红。

═══ 运行 ═══

    .\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_task54_l_cycle_migration.py -q

变异检验脚本：`backend/scripts/diagnose/mutate_task54_l_cycle_guards.py`
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
from types import ModuleType
from typing import Any

import pytest
from openpyxl import load_workbook

# ════════════════════════════════════════════════════════════════════════════
# 路径常量
# ════════════════════════════════════════════════════════════════════════════
_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
SRC_COMPOSABLES = FRONTEND / "composables"
CYCLE_COMPOSABLES = SRC_COMPOSABLES / "workpaper"
SYNC_DIR = WP_COMPONENTS / "sync"
DATA = BACKEND / "data"

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_l_cycle_manifest_slice.json"
DELETION_PLAN_PATH = DATA / "workpaper_sync_l_cycle_deletion_plan.json"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY_PATH = DATA / "workpaper_sync_entry_overlay.json"
SIBLING_SLICE_PATHS = {
    "D": DATA / "workpaper_sync_d_cycle_manifest_slice.json",
    "E": DATA / "workpaper_sync_e_cycle_manifest_slice.json",
    "F": DATA / "workpaper_sync_f_cycle_manifest_slice.json",
    "G": DATA / "workpaper_sync_g_cycle_manifest_slice.json",
    "H": DATA / "workpaper_sync_h_cycle_manifest_slice.json",
    "I": DATA / "workpaper_sync_i_cycle_manifest_slice.json",
    "J": DATA / "workpaper_sync_j_cycle_manifest_slice.json",
    "K": DATA / "workpaper_sync_k_cycle_manifest_slice.json",
}
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
TEMPLATE_DIR = BACKEND / "wp_templates"
TEMPLATE_INDEX = TEMPLATE_DIR / "_index.json"
L_TEMPLATE_DIR = TEMPLATE_DIR / "L"
CHECKLIST_ROUTER = BACKEND / "app" / "routers" / "checklist_responses.py"
OO_ROUTER = BACKEND / "app" / "routers" / "wp_onlyoffice_router.py"
REGISTRY = BACKEND / "app" / "services" / "workpaper_sync" / "adapters" / "registry.py"
HTML_RENDERER_REGISTRY = WP_COMPONENTS / "htmlRendererRegistry.ts"
SHARED_BASE = WP_COMPOSABLES / "useWorkpaperEntryDualMode.ts"
SHARED_CARRIER = WP_COMPOSABLES / "useCycleHtmlOoDualMode.ts"
OO_SHEET_COMPONENT = WP_COMPONENTS / "GtOnlyOfficeSheet.vue"
COMPOSABLES_BARREL = WP_COMPOSABLES / "index.ts"
NOTICE_MODULE = SYNC_DIR / "workpaperEntrySyncNotice.ts"
NOTICE_COMPONENT = SYNC_DIR / "GtEntrySyncCapabilityNotice.vue"
NOTICE_COMPONENT_NAME = "GtEntrySyncCapabilityNotice"
CONTRACT_GUARD = BACKEND / "tests" / "workpaper_sync" / "test_migration_paradigm_contract.py"
COVERAGE_GUARD = BACKEND / "tests" / "workpaper_sync" / "test_slice_schema_validator_coverage.py"

CAPABILITY_ENUM = ("bidirectional", "single_html", "single_onlyoffice", "unreachable")
HTML_COUNTERPART_VERDICTS = ("none", "exists")
SWITCH_VERDICTS = ("switch_redeemable", "switch_present_but_inert", "no_switch_at_all")

#: 四条 pilot 契约的 `review.entry_id` 实测值 —— 🔴 按 entry_id 判归属，不按文件名猜。
PILOT_CONTRACT_OWNERS = {
    "xlsx/b60/gt-b60-bundle",
    "xlsx/gt-d2-accounts-receivable",
    "xlsx/gt-g7-long-term-equity-main",
    "xlsx/gt-h1-fixed-assets",
}

L_CODES = ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")
#: 承载 inert 开关的四条 entry（L 循环特有形态；见模块 docstring 第 2 条）。
INERT_CODES = ("L5", "L6", "L7", "L8")
#: 开关**可兑现**的对照组 —— 用来证明 inert 扫描器不是恒 0。
REDEEMABLE_CODES = ("L1", "L2")
#: 完全没有 dual-mode 载体的两条。
NO_CARRIER_CODES = ("L3", "L4")


# ════════════════════════════════════════════════════════════════════════════
# 工具
# ════════════════════════════════════════════════════════════════════════════
def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blank_keep_newlines(match: "re.Match[str]") -> str:
    """把匹配段替换成同长空白，**保留换行** —— 行号绝不能变。"""
    return re.sub(r"[^\n]", " ", match.group(0))


def _strip_comments(source: str) -> str:
    """剥块注释 / 行注释 / HTML 注释，行号保持不变。"""
    source = re.sub(r"/\*.*?\*/", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(r"<!--.*?-->", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(
        r"(?<![:\w\"'`\\])//[^\n]*", lambda m: " " * len(m.group(0)), source
    )
    return source


def _strip_docstrings(source: str) -> str:
    """剥 Python 三引号字符串块，行号保持不变。

    🔴 `_strip_comments` 只处理 `#` / `//` / `/* */` / `<!-- -->`，**不碰 docstring**。
    对 Python 生产源做「某个符号是否真的被用到」的判据时必须先剥 docstring ——
    否则 docstring 里叙述性提到的符号名会被当成真实引用（本文件的
    `test_router_delegates_visibility_to_the_zip_level_service` 首版就栽在这里：
    router 的 docstring 记录了 openpyxl 那版的实测毁坏，判据于是恒红）。

    只剥三引号块，不剥单引号/双引号字面量 —— 后者常是判据要找的真实字符串。
    """
    return re.sub(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'',
                  _blank_keep_newlines, source)


def _vue_template(source: str) -> str:
    """取 `<template>` 顶层块（不被内层 `<template v-if>` 提前截断），行号保留。"""
    start = source.find("<template>")
    if start < 0:
        return ""
    end = source.rfind("</template>")
    if end < 0:
        return ""
    head = re.sub(r"[^\n]", " ", source[:start])
    return head + source[start:end + len("</template>")]


def _lines_of(text: str, needle: str) -> list[int]:
    return [text.count("\n", 0, m.start()) + 1 for m in re.finditer(re.escape(needle), text)]


def _sheet_names(path: pathlib.Path) -> list[str]:
    """openpyxl 真读 sheet 名。🔴 **不得 strip** —— L1A 前有前导空格、L4A 后有尾随空格。"""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _indexed_relpaths() -> set[str]:
    idx = _load(TEMPLATE_INDEX)
    return {str(f["relative_path"]).replace("\\", "/") for f in idx["files"]}


def _resolve_repo(rel: str) -> pathlib.Path:
    return ROOT / rel.split("#L")[0]


def _line_no_of(ref: str) -> int:
    m = re.search(r"#L(\d+)$", ref)
    assert m, f"{ref!r} 不含 #L<行号>"
    return int(m.group(1))


def _line_at(ref: str) -> str:
    path = _resolve_repo(ref)
    lines = path.read_text(encoding="utf-8").split("\n")
    n = _line_no_of(ref)
    assert 1 <= n <= len(lines), f"{ref} 行号越界（文件共 {len(lines)} 行）"
    return lines[n - 1]


_IMPORT_FORMS = (
    re.compile(r"""from\s*['"]([^'"\n]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"\n]+)['"]"""),
    re.compile(r"""vi\.mock\s*\(\s*['"]([^'"\n]+)['"]"""),
    re.compile(r"""require\s*\(\s*['"]([^'"\n]+)['"]"""),
)


def _inside_double_quoted_string(line: str, pos: int) -> bool:
    """`pos` 是否落在**双引号字符串**内。

    🔴 `workpaperSyncLegacyBaseline.generated.ts` 的 JSON `"snippet"` 字段里含完整的
    ``from '...'`` 形态；不排除它，「L 对共享基类贡献 0 条边」这个结论会翻。
    """
    depth = 0
    i = 0
    while i < pos and i < len(line):
        ch = line[i]
        if ch == "\\":
            i += 2
            continue
        if ch == '"':
            depth ^= 1
        i += 1
    return bool(depth)


_FE_CACHE: dict[pathlib.Path, str] = {}


def _cached_text(path: pathlib.Path) -> str:
    if path not in _FE_CACHE:
        _FE_CACHE[path] = path.read_text(encoding="utf-8", errors="replace")
    return _FE_CACHE[path]


_FE_FILES: list[pathlib.Path] = []


def _all_frontend() -> list[pathlib.Path]:
    global _FE_FILES
    if not _FE_FILES:
        _FE_FILES = [
            p for p in FRONTEND.rglob("*")
            if p.is_file() and p.suffix in (".ts", ".vue", ".tsx", ".js")
        ]
    return _FE_FILES


def _resolve_spec(spec: str, importer: pathlib.Path) -> pathlib.Path | None:
    """把 import spec 解析成仓库内路径（**路径式**，不是 stem 式）。"""
    if spec.startswith("@/"):
        return FRONTEND / spec[2:]
    if spec.startswith("."):
        return (importer.parent / spec).resolve()
    return None


def _is_test_path(path: pathlib.Path) -> bool:
    p = path.as_posix()
    return "__tests__" in p or p.endswith((".spec.ts", ".test.ts"))


def _statement_edges_to(target: pathlib.Path) -> tuple[list[str], list[str]]:
    """返回 (生产边, 测试边)，只认 statement-position 且排除双引号字符串内的匹配。"""
    prod: list[str] = []
    test: list[str] = []
    stem = target.with_suffix("")
    for f in _all_frontend():
        text = _cached_text(f)
        if target.stem not in text:
            continue
        for i, line in enumerate(text.split("\n"), 1):
            for rx in _IMPORT_FORMS:
                for m in rx.finditer(line):
                    if _inside_double_quoted_string(line, m.start()):
                        continue
                    r = _resolve_spec(m.group(1), f)
                    if r is None:
                        continue
                    if r in (stem, target) or r.with_suffix("") == stem:
                        ref = f"{f.relative_to(ROOT).as_posix()}#L{i}"
                        (test if _is_test_path(f) else prod).append(ref)
    return prod, test


def _wide_scope_edge_files(token: str) -> set[str]:
    """宽口径：逐文件 token 命中即算（用于证明窄口径不是空谈）。"""
    return {
        f.relative_to(ROOT).as_posix()
        for f in _all_frontend() if token in _cached_text(f)
    }


def _l_cycle_files() -> list[pathlib.Path]:
    """L 域生产文件（口径与 slice 的 `scanned_scope` 逐字一致）。"""
    out: list[pathlib.Path] = []
    for n in range(1, 9):
        d = WP_COMPONENTS / f"l{n}"
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file() and p.suffix in (".ts", ".vue") and "__tests__" not in p.as_posix():
                    out.append(p)
    for p in sorted(WP_COMPONENTS.iterdir()):
        if p.suffix == ".vue" and re.match(r"^GtL\d+", p.name):
            out.append(p)
    for p in sorted(WP_COMPOSABLES.iterdir()):
        if p.suffix == ".ts" and re.match(r"^(use)?[lL][1-8](?![0-9])", p.name):
            out.append(p)
    for p in sorted(SRC_COMPOSABLES.iterdir()):
        if p.is_file() and p.suffix == ".ts" and re.match(r"^(use)?[lL][1-8](?![0-9])", p.name):
            out.append(p)
    for n in range(1, 9):
        d = CYCLE_COMPOSABLES / f"l{n}"
        if d.is_dir():
            for p in d.rglob("*.ts"):
                if "__tests__" not in p.as_posix():
                    out.append(p)
    return sorted(set(out))


_IDENTITY_KEY = re.compile(r"(?<![\w$])(rowId|rowKey|id)\s*:\s*([^,\n]+)")
_POSITIONAL_TOKEN = re.compile(r"(?:^|[^\w$])(?:i|idx|index)(?:\s*\+\s*1)?(?:\s*\}|\s*[,)\]`]|$)")
_POSITIONAL_INTERP = re.compile(r"\$\{\s*(?:i|idx|index)\s*\}")
_ENTROPY = re.compile(r"Date\.now\(\)|Math\.random\(\)")
_FALLBACK = re.compile(r"\?\?|\|\|")
_DISPLAY_SEQ_SITE = re.compile(r"\bseq\s*:\s*[^,]*(?:idx|index|\bi\b)\s*\+\s*1")

_HARDCODED_PATTERNS = {
    "blankRows_literal_count": re.compile(r"blankRows\s*\([^,)]*,\s*\d+\s*\)"),
    "horizontal_company_column_literals": re.compile(r"['\"]公司\s*[1-9]\d*['\"]"),
    "column_key_uses_label": re.compile(r"key\s*:\s*(?:row|col|c)\.label"),
    "row_cell_key_uses_label": re.compile(r"cells\s*\[\s*(?:row|r)\.label\s*\]"),
    "seed_placeholder_literal": re.compile(r"['\"](?:项目|成本项目|单位)\s*N['\"]"),
    "positional_row_id_template": re.compile(
        r"`(?:seed|row|detail|item)-\$\{\s*(?:i|idx|index)\s*\}"
    ),
}


def _positional_identity_hits(files: list[pathlib.Path]) -> list[tuple[str, str, str]]:
    hits: list[tuple[str, str, str]] = []
    for p in files:
        src = _strip_comments(_cached_text(p))
        for i, line in enumerate(src.split("\n"), 1):
            for m in _IDENTITY_KEY.finditer(line):
                val = m.group(2).strip()
                if _POSITIONAL_TOKEN.search(val) or _POSITIONAL_INTERP.search(val):
                    hits.append((f"{p.relative_to(ROOT).as_posix()}#L{i}", m.group(1), val))
    return hits


def _family_of(value: str) -> str:
    """四族判别式 —— 可复算的布尔表达式，不是人工归类。顺序要紧。"""
    if _ENTROPY.search(value) and not _FALLBACK.search(value):
        return "c"
    if _FALLBACK.search(value):
        return "b"
    return "a"


def _hardcoded_hits(files: list[pathlib.Path], name: str) -> list[str]:
    rx = _HARDCODED_PATTERNS[name]
    out: list[str] = []
    for p in files:
        src = _strip_comments(_cached_text(p))
        for i, line in enumerate(src.split("\n"), 1):
            if rx.search(line):
                out.append(f"{p.relative_to(ROOT).as_posix()}#L{i}")
    return out


def _display_seq_sites(files: list[pathlib.Path]) -> list[str]:
    out: list[str] = []
    for p in files:
        src = _strip_comments(_cached_text(p))
        for i, line in enumerate(src.split("\n"), 1):
            if _DISPLAY_SEQ_SITE.search(line):
                out.append(f"{p.relative_to(ROOT).as_posix()}#L{i}")
    return out


def _wp_code_of(entry: dict) -> str:
    """从 `wp_code_pattern`（L1S / L2I / …）现算 L{n}。"""
    m = re.search(r"L(\d+)", str(entry["wp_code_pattern"]))
    assert m, f"wp_code_pattern={entry['wp_code_pattern']!r} 里没有 L+数字"
    return "L" + m.group(1)


def _host_of(code: str) -> pathlib.Path:
    hits = sorted(p for p in WP_COMPONENTS.glob(f"Gt{code}*.vue"))
    assert len(hits) == 1, f"Gt{code}*.vue 应恰好 1 个宿主，实得 {[p.name for p in hits]}"
    return hits[0]


def _adjudication_tab(code: str) -> pathlib.Path:
    n = code[1:]
    return WP_COMPONENTS / f"l{n}" / "core" / f"L{n}TabAdjudication.vue"


def _mode_gated_v_if(template: str) -> list[str]:
    """模板里以 dualMode 为条件的分支指令（三要素之一：外层门控）。"""
    return re.findall(r"v-(?:if|else-if|show)=\"[^\"]*dualMode[^\"]*\"", template)


def _dual_mode_members(template: str) -> set[str]:
    return set(re.findall(r"dualMode\.(\w+)", template))


def _router_matches(target: str, sheets: list[str]) -> list[str]:
    """复刻 `wp_onlyoffice_router._hide_non_target_sheets` 的匹配规则（精确优先，否则 contains/endswith）。"""
    exact = [s for s in sheets if s == target]
    if exact:
        return exact
    return [s for s in sheets if target in s or s.endswith(target)]


def _dispatch_codes(host_clean: str) -> list[str]:
    return re.findall(r"""currentSheet === '([^']+)'""", host_clean)


def _dual_mode_module_files() -> list[pathlib.Path]:
    return sorted(FRONTEND.rglob("useL*DualMode.ts"))


def _load_module(name: str, path: pathlib.Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"无法以 importlib 加载 {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ════════════════════════════════════════════════════════════════════════════
# fixtures
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def deletion_plan() -> dict:
    return _load(DELETION_PLAN_PATH)


@pytest.fixture(scope="module")
def paradigm() -> dict:
    return _load(PARADIGM_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return _load(FULL_MANIFEST_PATH)


@pytest.fixture(scope="module")
def l_files() -> list[pathlib.Path]:
    return _l_cycle_files()


@pytest.fixture(scope="module")
def l1_template() -> pathlib.Path:
    p = L_TEMPLATE_DIR / "L1 短期借款.xlsx"
    assert p.exists(), f"权威模板不存在：{p}"
    return p


# ════════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:
    """反向自检：判据既不许恒红也不许恒绿。故意写错必须失败。"""

    def test_strip_comments_hides_content_but_keeps_line_numbers(self) -> None:
        src = "a\n<!-- el-segmented -->\nb\n/* x */\nc\n// y\nd"
        out = _strip_comments(src)
        assert out.count("\n") == src.count("\n"), "剥注释改变了行数 ⇒ 全部 #Lnn 锚点会假红"
        assert "el-segmented" not in out
        assert out.split("\n")[2] == "b", "行号错位"

    def test_strip_comments_really_hides_a_commented_segmented_in_an_l_host(self) -> None:
        """L4 宿主的第二处 `el-segmented` 落在注释里（现算 raw 2 处 / clean 1 处）。"""
        raw = _cached_text(_host_of("L4"))
        clean = _strip_comments(raw)
        assert len(_lines_of(raw, "el-segmented")) > len(_lines_of(clean, "el-segmented")), (
            "L4 宿主里应有落在注释里的 el-segmented —— 若相等说明剥注释没生效或源码已变"
        )

    def test_inside_double_quoted_string_detector_works_both_ways(self) -> None:
        line = 'const s = "from \'./x\'"; import y from \'./y\''
        pos_in = line.index("from './x'")
        pos_out = line.rindex("from './y'")
        assert _inside_double_quoted_string(line, pos_in) is True
        assert _inside_double_quoted_string(line, pos_out) is False

    def test_resolve_spec_is_path_based_not_stem_based(self) -> None:
        importer = WP_COMPOSABLES / "useL5DualMode.ts"
        got = _resolve_spec("./useL5DualMode", importer)
        assert got == (WP_COMPOSABLES / "useL5DualMode").resolve()
        assert _resolve_spec("vue", importer) is None, "裸包名不应解析成仓库路径"

    def test_vue_template_extraction_does_not_stop_at_inner_template(self) -> None:
        host = _cached_text(_host_of("L1"))
        tpl = _vue_template(host)
        assert "<template v-else>" in tpl or "<template" in tpl
        assert "GtOnlyOfficeSheet" in tpl, "顶层 template 被内层 <template> 提前截断"

    def test_family_discriminator_puts_entropy_plus_fallback_in_b(self) -> None:
        assert _family_of("String(idx)") == "a"
        assert _family_of("raw.rowKey ?? `x-${idx}`") == "b"
        assert _family_of("`row-${Date.now()}-${idx}`") == "c"
        assert _family_of("raw.id ?? `r-${Date.now()}-${i}`") == "b", (
            "同时含熵与兜底必须归 family_b（是缺陷）"
        )

    def test_sheet_names_are_not_stripped(self, l1_template: pathlib.Path) -> None:
        """🔴 L1A 前有前导空格、L4A 后有尾随空格 —— strip 了会让 sheet 粒度判据整体失真。"""
        names = _sheet_names(l1_template)
        assert any(s != s.strip() for s in names), (
            f"L1 册应有带前后空格的 sheet 名，实得 {names}"
        )
        l4 = _sheet_names(L_TEMPLATE_DIR / "L4 应付债券.xlsx")
        assert any(s.endswith(" ") for s in l4), f"L4 册应有尾随空格的 sheet 名，实得 {l4}"

    def test_router_matcher_replicates_the_real_source_rule(self) -> None:
        """`_router_matches` 不是凭印象写的 —— 直接与真源实现**逐条行为比对**。

        🔴 2026-09-03 判据升级。原判据是在 router 源码里找
        `ws.title == target_sheet` / `target_sheet in ws.title` /
        `ws.title.endswith(target_sheet)` 三个字符串。两个毛病：

        1. **锁死了实现细节**。sheet 可见性改写已从 openpyxl 全量重写换成 zip 级
           外科手术（原实现在 K11 上实测丢 20 个 zip 部件、把 12 个共享公式组展平、
           把缓存值写成空标签 `<v></v>`；详见
           `app/services/workpaper_sync/excel_sheet_visibility` 的模块 docstring）。
           那三个 openpyxl 惯用法随之消失，判据会把一次**修复**判成红。
        2. **是「字符存在」型判据**，证不出规则等价。把 `in` 改成 `startswith`
           而字符串仍在源码里，照样绿。

        现改为：import 匹配规则的真源 `resolve_target_sheet`，用**真实 L 册
        sheet 名**（含前导/尾随空格、同尾码重名、半角括号）做输入矩阵，逐条比对
        「首个命中」。规则任何一侧改动都会打红，且改不成"字符还在但行为变了"。
        """
        from app.services.workpaper_sync.excel_sheet_visibility import (
            resolve_target_sheet,
        )

        sheets: list[str] = []
        for book in sorted(L_TEMPLATE_DIR.glob("*.xlsx")):
            if book.name.startswith("~$"):
                continue
            sheets.extend(_sheet_names(book))
        assert len(sheets) > 50, f"L 册 sheet 名样本只有 {len(sheets)} 个 ⇒ 分母可疑"
        assert any(s != s.strip() for s in sheets), (
            "样本里没有带前后空格的 sheet 名 ⇒ 最易错的形态没被覆盖"
        )

        # 目标矩阵：完整 sheet 名 + 尾码片段 + 一个必然落空的
        targets = sorted({*sheets, *re.findall(r"L\d+(?:-\d+)?[A-Z]?", " ".join(sheets))})
        targets.append("绝不存在的表名XYZ")

        exact_hits = fallback_hits = misses = 0
        for target in targets:
            replicated = _router_matches(target, sheets)
            expected = replicated[0] if replicated else None
            assert resolve_target_sheet(sheets, target) == expected, (
                f"目标 {target!r}：复刻规则给 {expected!r}，"
                f"真源给 {resolve_target_sheet(sheets, target)!r} ⇒ 两侧已分叉"
            )
            if target in sheets:
                exact_hits += 1
            elif replicated:
                fallback_hits += 1
            else:
                misses += 1

        # 三条分支都必须被真实走到，否则等价性论证是空转
        assert exact_hits > 0, "矩阵里没有精确命中 ⇒ 该分支未被检验"
        assert fallback_hits > 0, "矩阵里没有 contains/endswith 回退命中 ⇒ 该分支未被检验"
        assert misses > 0, "矩阵里没有落空用例 ⇒ None 分支未被检验"

    def test_router_delegates_visibility_to_the_zip_level_service(self) -> None:
        """router 必须把可见性改写交给 zip 级实现，且不得再全量重写 workbook。

        🔴 这是上面那条判据换掉字符串锚点后必须补上的一条：只比对匹配规则等价
        并不能防止有人把实现换回 `openpyxl.load_workbook()` + `wb.save()`。
        """
        # 🔴 `_strip_comments` 只剥 `#` 行注释与 `/* */`，**不剥 Python docstring**。
        #    这两个函数的 docstring 里逐条记录了 openpyxl 那版的实测毁坏（"openpyxl"
        #    出现十余次），不剥掉就会把一次修复判成"又用了 openpyxl" —— 首版正是这么
        #    自己把自己打红的。故这里额外剥三引号块，再判。
        src = _strip_docstrings(_strip_comments(_cached_text(OO_ROUTER)))
        for func, delegate in (
            ("_hide_non_target_sheets", "apply_single_sheet_visibility"),
            ("_ensure_all_sheets_visible", "restore_all_sheets_visible"),
        ):
            i = src.find(f"def {func}")
            assert i > 0, f"router 里找不到 {func}"
            j = src.find("\ndef ", i + 1)
            body = src[i : j if j > 0 else len(src)]
            assert delegate in body, f"{func} 未委派给 {delegate} ⇒ 可能又自己重写 workbook"
            assert "openpyxl" not in body, (
                f"{func} 里又出现 openpyxl —— 全量重写会丢 zip 部件/共享公式/缓存值，"
                f"K11 实测 37 个部件掉到 19 个"
            )
            assert ".save(" not in body, f"{func} 里出现 .save( ⇒ 疑似整本落盘"

    def test_docstring_stripper_actually_strips(self) -> None:
        """反向自检：剥离器真的在剥，且没顺手剥掉代码。

        上一条判据完全依赖 `_strip_docstrings`。若它是空操作，判据恒红（docstring
        里的实测记录会命中）；若它剥多了，判据恒绿（真的 openpyxl 调用也被剥掉）。
        两个方向都得钉住。
        """
        sample = (
            'def f():\n'
            '    """里面写了 openpyxl 三个字。"""\n'
            '    return 1\n'
            'def g():\n'
            "    '''单引号 docstring 也要剥 openpyxl。'''\n"
            '    import openpyxl\n'
            '    return openpyxl\n'
        )
        stripped = _strip_docstrings(sample)
        assert stripped.count("openpyxl") == 2, (
            f"应只剩 g() 里两处真实引用，实得 {stripped.count('openpyxl')} 处：{stripped!r}"
        )
        assert "import openpyxl" in stripped, "真实 import 被剥掉了 ⇒ 判据会恒绿"
        assert stripped.count("\n") == sample.count("\n"), "行号被改变 ⇒ 其他按行号的判据会失真"
        # 真实 router 源码上也得非空转
        raw = _strip_comments(_cached_text(OO_ROUTER))
        assert raw.count("openpyxl") > _strip_docstrings(raw).count("openpyxl"), (
            "router 源码里 docstring 提到的 openpyxl 一个都没被剥 ⇒ 剥离器对真实输入失效"
        )

    def test_l_cycle_denominator_is_non_vacuous(self, l_files: list[pathlib.Path]) -> None:
        assert len(l_files) > 100, f"L 域生产文件只有 {len(l_files)} 个 ⇒ 分母可疑"
        hosts = [p for p in l_files if re.match(r"^GtL\d", p.name)]
        assert len(hosts) == len(L_CODES), f"宿主数应为 {len(L_CODES)}，实得 {[p.name for p in hosts]}"
        # 🔴 owner 模块分居三处 —— 只扫其中一处会漏命中（scanned_scope_note）。
        in_l_dir = [p for p in l_files
                    if p.is_relative_to(WP_COMPONENTS)
                    and re.match(r"l\d/", p.relative_to(WP_COMPONENTS).as_posix())]
        in_wp_composables = [p for p in l_files if p.parent == WP_COMPOSABLES]
        in_src_composables = [p for p in l_files if p.parent == SRC_COMPOSABLES]
        for name, bucket in (("l{n}/**", in_l_dir), ("wp/composables", in_wp_composables),
                             ("src/composables", in_src_composables)):
            assert bucket, f"分母的 `{name}` 桶为空 ⇒ 扫描口径少了一处"
        assert len(hosts) + len(in_l_dir) + len(in_wp_composables) + len(in_src_composables) == len(
            l_files), "四个桶未划分完 l_files ⇒ 分母有未归类文件"

    def test_all_required_artifacts_exist(self) -> None:
        for p in (MANIFEST_SLICE_PATH, DELETION_PLAN_PATH, PARADIGM_PATH, FULL_MANIFEST_PATH,
                  OVERLAY_PATH, TEMPLATE_INDEX, CHECKLIST_ROUTER, OO_ROUTER,
                  HTML_RENDERER_REGISTRY, SHARED_BASE, SHARED_CARRIER, NOTICE_MODULE,
                  NOTICE_COMPONENT, OO_SHEET_COMPONENT):
            assert p.exists(), f"缺文件：{p}"
        for p in SIBLING_SLICE_PATHS.values():
            assert p.exists(), f"缺兄弟 slice：{p}"


# ════════════════════════════════════════════════════════════════════════════
class TestSliceScopeIsRecomputable:
    """slice_scope 的每个数字都从 manifest 现算，抄错或凑数即红。"""

    @staticmethod
    def _l_prefixed(full_manifest: dict) -> list[dict]:
        out = []
        for e in full_manifest["entries"]:
            pats = (e.get("wp_match") or {}).get("wp_code_patterns") or []
            if e.get("document_type") == "xlsx" and any(str(p).startswith("L") for p in pats):
                out.append(e)
        return out

    def test_selection_rule_recomputes_the_entry_set(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        computed = {e["entry_id"] for e in self._l_prefixed(full_manifest)
                    if e.get("independent_entry")}
        declared = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert computed == declared, (
            f"selection_rule 现算集合与 slice 不等：多写 {sorted(declared - computed)}，"
            f"漏写 {sorted(computed - declared)}"
        )
        assert len(declared) == len(L_CODES)

    def test_scope_counters_match_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        scope = manifest_slice["slice_scope"]
        l_all = self._l_prefixed(full_manifest)
        assert scope["l_prefixed_entry_total"] == len(l_all)
        assert scope["l_prefixed_independent_total"] == sum(
            1 for e in l_all if e.get("independent_entry"))
        assert scope["independent_entry_count"] == len(manifest_slice["independent_entries"])
        assert scope["cycle"] == "L" and scope["document_type"] == "xlsx"

    def test_every_l_entry_is_xlsx(self, full_manifest: dict) -> None:
        pats_l = [e for e in full_manifest["entries"]
                  if any(str(p).startswith("L") for p in
                         ((e.get("wp_match") or {}).get("wp_code_patterns") or []))]
        assert {e["document_type"] for e in pats_l} == {"xlsx"}, (
            "L 前缀 entry 出现非 xlsx ⇒ 排除集不能再登记为 0"
        )

    def test_parent_duplicate_count_is_really_zero_both_ways(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        kids = [e["entry_id"] for e in full_manifest["entries"]
                if e.get("parent_entry_id") in ids]
        assert kids == [], f"实测存在 parent_duplicate 子入口 {kids}"
        assert manifest_slice["slice_scope"]["parent_duplicate_count"] == 0
        overlay = _load(OVERLAY_PATH)
        globs = [r.get("file_glob") for r in (overlay.get("parent_rules") or [])]
        assert not any("/l" in str(g) and "workpaper/l" in str(g) for g in globs), (
            f"overlay 的 parent_rules 里出现了 L 目录 glob：{globs}"
        )
        assert "parent_duplicate_summary" not in manifest_slice, (
            "触发条件不成立却写了 parent_duplicate_summary ⇒ additive 死声明"
        )

    def test_untriggered_conditional_sections_are_absent(self, manifest_slice: dict) -> None:
        assert "currency_variant_model" not in manifest_slice, (
            "L 循环没有「多 variant sheet 共用一个持久化键」形态 ⇒ 不得写该条件节"
        )

    def test_l0_workbook_exists_but_has_no_entry(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        hits = [e["entry_id"] for e in full_manifest["entries"] if "l0" in e["entry_id"].lower()]
        assert hits == [], f"manifest 里出现了 L0 entry：{hits}"
        book = L_TEMPLATE_DIR / "L0 债务循环函证.xlsx"
        assert book.exists(), "L0 权威模板应存在（排除理由不能是「模板不存在」）"
        assert f"L/{book.name}" in _indexed_relpaths(), "L0 应在运行时索引里"
        sheets = _sheet_names(book)
        assert any("函证程序表F0A" in s for s in sheets), (
            f"L0 的排除证据是「第 2 张 sheet 名含 函证程序表F0A（F0 而非 L0）」，实得 {sheets}"
        )
        excl = manifest_slice["slice_scope"]["excluded_from_slice"]
        assert any("L0" in item["what"] for item in excl), "L0 未登记进 excluded_from_slice"

    def test_host_module_edges_in_the_renderer_registry_are_real(
        self, manifest_slice: dict
    ) -> None:
        """可达性判据落在 htmlRendererRegistry 的**模块边**，不按符号名 grep。"""
        reg = _strip_comments(_cached_text(HTML_RENDERER_REGISTRY))
        specs = {m.group(1) for rx in _IMPORT_FORMS for m in rx.finditer(reg)}
        resolved = {
            r for r in (_resolve_spec(s, HTML_RENDERER_REGISTRY) for s in specs) if r is not None
        }
        for entry in manifest_slice["independent_entries"]:
            host = ROOT / entry["host_path"]
            assert host.exists(), f"宿主不存在：{host}"
            assert host in resolved, f"{entry['entry_id']} 的宿主不在 registry 的模块边里"

    def test_no_pilot_contract_belongs_to_the_l_cycle(self, manifest_slice: dict) -> None:
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        owners: set[str] = set()
        candidates: list[str] = []
        for f in sorted(CONTRACT_DIR.glob("*.json")):
            doc = _load(f)
            review = doc.get("review") or {}
            if str(doc.get("review_status") or review.get("review_status")) == "candidate":
                candidates.append(f.name)
                assert review.get("entry_id") is None, (
                    f"{f.name} 是 candidate 却带 entry_id ⇒ 反例分母被污染"
                )
                continue
            eid = review.get("entry_id")
            assert eid, f"{f.name} 是生产契约却没有 review.entry_id"
            owners.add(str(eid))
        assert owners == PILOT_CONTRACT_OWNERS, (
            f"生产契约归属集合变了：{sorted(owners)}"
        )
        assert not (owners & ids), f"契约归属命中本 slice：{sorted(owners & ids)}"
        iso = manifest_slice["cross_entry_isolation"]
        assert sorted(iso["candidate_contract_files"]) == sorted(candidates)

    def test_no_l_adapter_is_registered(self, manifest_slice: dict) -> None:
        src = _strip_comments(REGISTRY.read_text(encoding="utf-8"))
        for entry in manifest_slice["independent_entries"]:
            assert entry["entry_id"] not in src, (
                f"registry 里出现了 {entry['entry_id']} ⇒ adapter_id 不该是 null"
            )
            assert entry["adapter_id"] is None


# ════════════════════════════════════════════════════════════════════════════
class TestAdjudicationLegality:
    """AC 12.8 / 12.9 / 1.3 / 1.4 / 1.5 + SR-3~SR-9 + AP-1/AP-3/AP-5。"""

    def test_every_entry_has_a_binary_html_counterpart_verdict(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            v = e["html_counterpart_verdict"]
            assert v in HTML_COUNTERPART_VERDICTS, (
                f"{e['entry_id']}: html_counterpart_verdict={v!r} 不是二值结论（AP-3）"
            )
            assert e["html_counterpart_source_refs"], f"{e['entry_id']}: 结论没有 source_refs"

    def test_single_onlyoffice_requires_no_html_counterpart(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            if e["capability"] == "single_onlyoffice":
                assert e["html_counterpart_verdict"] == "none", (
                    f"{e['entry_id']}: 裁 single_onlyoffice 但对端 exists（AC 12.8）"
                )

    def test_adjudication_reason_is_not_circular(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        ap1 = next(a for a in paradigm["adjudication_criteria"]["anti_patterns"]
                   if a["id"] == "AP-1")
        markers = [str(m) for m in ap1["circular_reason_markers"]]
        for e in manifest_slice["independent_entries"]:
            reason = str(e["adjudication"]["reason"])
            if e["capability"] == "single_onlyoffice":
                assert not any(m in reason for m in markers), (
                    f"{e['entry_id']}: 裁 single 的理由含循环论证标记（AP-1）"
                )
            assert "html_counterpart" in reason or "HTML 对端" in reason, (
                f"{e['entry_id']}: 裁决理由没有陈述 step 3 的对端结论"
            )

    def test_capability_is_null_and_pending_fields_are_complete(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        schema = paradigm["slice_schema"]
        fields = schema["required_pending_verdict_fields"]
        semantics = schema["pending_verdict_field_semantics"]
        pending = 0
        for e in manifest_slice["independent_entries"]:
            if e["capability"] is not None:
                continue
            pending += 1
            for f in fields:
                kind = semantics[f]
                v = e.get(f)
                if kind == "non_empty_string":
                    assert isinstance(v, str) and v.strip(), f"{e['entry_id']}.{f} 不是非空串"
                elif kind == "member_of_capability_enum":
                    assert v in CAPABILITY_ENUM, f"{e['entry_id']}.{f}={v!r} 不在枚举内"
                elif kind == "non_empty_list":
                    assert isinstance(v, list) and v, f"{e['entry_id']}.{f} 不是非空数组"
                else:  # pragma: no cover - fail closed
                    raise AssertionError(f"未知语义 kind={kind!r}")
        assert pending == len(manifest_slice["independent_entries"]), (
            "本 slice 应 8/8 待裁决（若已裁出终态，summary 与本判据都要跟着改）"
        )
        assert pending == manifest_slice["honest_adjudication_summary"]["slice_counters"][
            schema["pending_verdict_counter"]
        ], "SR-9：待裁决条数与 slice_counters 不符"

    def test_capability_matches_honest_capability(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            assert e["capability"] == e["adjudication"]["honest_capability"], (
                f"{e['entry_id']}: SR-4 对外字段与诚实裁决双口径"
            )

    def test_pending_entries_carry_no_identity(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            for k in ("adapter_id", "authority_model", "definition_bundle",
                      "instrumentation_candidate", "published_representation"):
                assert k in e, f"{e['entry_id']}: `{k}` 键不得缺（值可为 null）"
                assert e[k] is None, f"{e['entry_id']}.{k} 非 null（AP-5 / SR-6）"

    def test_adjudication_carries_both_negative_reasons(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            adj = e["adjudication"]
            assert adj["not_single_html_because"], f"{e['entry_id']}: 缺 not_single_html_because"
            assert adj["not_bidirectional_because"], f"{e['entry_id']}: 缺 not_bidirectional_because"
            assert str(e["template_ref"]["workbook"]) in str(adj["not_single_html_because"]), (
                f"{e['entry_id']}: not_single_html_because 没点名自己的权威工作簿 ⇒ 可能是抄的"
            )

    def test_inert_entries_explicitly_refuse_the_single_html_shortcut(
        self, manifest_slice: dict
    ) -> None:
        """🔴 「开关坏了」不得被读成「无 OO 业务价值」—— 四条 inert entry 必须显式否掉。"""
        for e in manifest_slice["independent_entries"]:
            code = _wp_code_of(e)
            text = str(e["adjudication"]["not_single_html_because"])
            if code in INERT_CODES:
                assert "BP-4" in text, f"{code}: inert entry 未在 not_single_html_because 里点名 BP-4"
            else:
                assert "BP-4" not in text, f"{code}: 非 inert entry 却引了 BP-4 ⇒ 抄成同形"

    def test_every_blocking_precondition_is_referenced_by_someone(
        self, manifest_slice: dict
    ) -> None:
        declared = {bp["id"] for bp in manifest_slice["blocking_preconditions"]}
        referenced: set[str] = set()
        for e in manifest_slice["independent_entries"]:
            referenced |= set(e["capability_target_blocked_by"])
        assert declared == referenced, (
            f"BP 声明与引用不等：未被引用 {sorted(declared - referenced)}，"
            f"引用了不存在的 {sorted(referenced - declared)}"
        )
        assert manifest_slice["honest_adjudication_summary"][
            "blocking_preconditions_total"] == len(declared)

    def test_all_blocking_preconditions_carry_task48_fields(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        extra = paradigm["slice_schema"]["effective_from_task_48"]["required_blocking_precondition"]
        for bp in manifest_slice["blocking_preconditions"]:
            for k in extra:
                assert k in bp and bp[k], f"{bp['id']}: 缺 Task 48 起必填的 `{k}`"
            assert bp.get("consequence") or bp.get("observable_consequences"), (
                f"{bp['id']}: 后果必须写明"
            )

    def test_bp4_is_the_inert_switch_blocker(self, manifest_slice: dict) -> None:
        bp = next(b for b in manifest_slice["blocking_preconditions"] if b["id"] == "BP-4")
        assert "step 11 enforce_honest_mode_visibility" in bp["blocks"]
        assert bp["must_fix_before"], "BP-4 缺 must_fix_before"
        refs = [r for r in bp["source_refs"]]
        for code in INERT_CODES:
            tab = _adjudication_tab(code).relative_to(ROOT).as_posix()
            assert any(r.startswith(tab) for r in refs), f"BP-4 的 source_refs 里没有 {code} 的子 Tab"

    def test_bp8_is_the_sheet_granularity_blocker(self, manifest_slice: dict) -> None:
        bp = next(b for b in manifest_slice["blocking_preconditions"] if b["id"] == "BP-8")
        assert "step 6 publish_per_entry_contract" in bp["blocks"]
        for ref in bp["source_refs"]:
            assert _resolve_repo(ref).exists(), f"BP-8 的 source_ref 指向不存在的文件：{ref}"

    def test_manifest_mirror_divergence_is_registered_not_silently_equal(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 判据是「必须不一致且已登记 BP」，不是断言相等（断言相等 = 把 overlay 默认值当裁决）。"""
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        overlay = _load(OVERLAY_PATH)
        defaults = overlay["defaults_by_component"]["GtOnlyOfficeSheet"]
        diverged = 0
        for e in manifest_slice["independent_entries"]:
            m = by_id[e["entry_id"]]
            mirror = e["manifest_mirror"]
            assert mirror["capability"] == m["capability"], (
                f"{e['entry_id']}: manifest_mirror.capability 与 manifest 现值不符 ⇒ 镜像抄错"
            )
            assert mirror["html_store"] == m["html_store"]
            assert mirror["capability"] == defaults["capability"], (
                "镜像值应等于 overlay 的组件级默认值（这正是它不可采信的理由）"
            )
            assert e["capability"] != m["capability"], (
                f"{e['entry_id']}: slice 与 manifest 的 capability 相等 ⇒ 采信了 overlay 默认值（AP-3）"
            )
            assert "BP-9" in str(mirror["why_not_adopted"])
            diverged += 1
        assert diverged == len(L_CODES)
        assert any(b["id"] == "BP-9" for b in manifest_slice["blocking_preconditions"])

    def test_ac15_is_declared_not_applicable_and_ac14_is_the_live_one(
        self, manifest_slice: dict
    ) -> None:
        summary = manifest_slice["honest_adjudication_summary"]
        text = str(summary["ac_15_not_applicable_because"])
        assert "AC 1.5" in text and "AC 1.4" in text
        for e in manifest_slice["independent_entries"]:
            cap = e["capability"]
            assert not (isinstance(cap, str) and cap.startswith("single_")), (
                "有 entry 裁成 single_* ⇒ AC 1.5 的前提成立，本 slice 的「不适用」声明必须改写"
            )
        assert NOTICE_MODULE.exists() and NOTICE_COMPONENT.exists()
        for e in manifest_slice["independent_entries"]:
            host = _strip_comments(_cached_text(ROOT / e["host_path"]))
            assert NOTICE_COMPONENT_NAME not in host, (
                f"{e['entry_id']} 的宿主已挂 AC 1.4 提示组件 ⇒ BP-7 必须解除（现在会 XPASS 式假绿）"
            )
            assert e["ui_toolbar_gate"]["mounts_ac14_notice"] is False
        assert summary["entries_mounting_the_ac14_notice"] == 0

    def test_no_host_template_claims_bidirectional(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            tpl = _vue_template(_strip_comments(_cached_text(ROOT / e["host_path"])))
            for bad in ("可双向回写", "双向回写", "bidirectional"):
                assert bad not in tpl, f"{e['entry_id']} 的宿主模板宣称了 {bad!r}"


# ════════════════════════════════════════════════════════════════════════════
class TestHtmlCounterpartIsSourceBacked:
    """step 3 的结论必须由真实文件/端点/模板单元格撑着。"""

    def test_source_refs_point_at_real_paths_and_lines(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            for ref in e["html_counterpart_source_refs"]:
                p = _resolve_repo(ref)
                assert p.exists(), f"{e['entry_id']}: source_ref 指向不存在的文件 {ref}"
                if "#L" in ref:
                    assert _line_at(ref).strip(), f"{e['entry_id']}: {ref} 指向空行"

    def test_formdata_refs_really_hit_the_checklist_calls(self, manifest_slice: dict) -> None:
        """两条 FormData 行号必须**真的**落在 GET / PUT 调用上（不是随便指一行）。

        🔴 调用可能跨行（L6 是 `const res = await api.get(` 换行后才是 URL），故取
        **锚点行 + 后两行**的窗口 —— 但窗口必须有界，否则「落在调用上」退化成「文件里有」。
        """
        for e in manifest_slice["independent_entries"]:
            code = _wp_code_of(e)
            refs = [r for r in e["html_counterpart_source_refs"] if "FormData" in r]
            assert len(refs) == 2, f"{code}: FormData 的 source_ref 应恰 2 条（GET/PUT），实得 {refs}"
            windows = []
            for r in refs:
                lines = _resolve_repo(r).read_text(encoding="utf-8").split("\n")
                n = _line_no_of(r)
                windows.append("\n".join(lines[n - 1: n + 2]))
            assert any(".get(" in w and "checklist-responses" in w for w in windows), (
                f"{code}: GET 行号没落在 checklist-responses 的 get 调用上：{windows}"
            )
            assert any(".put(" in w and "checklist-responses" in w for w in windows), (
                f"{code}: PUT 行号没落在 checklist-responses 的 put 调用上：{windows}"
            )
            for r, w in zip(refs, windows):
                assert re.search(r"\b(?:api|http)\.(?:get|put)\(", w), (
                    f"{code}: {r} 的窗口里没有 api/http 调用 —— 行号偏了"
                )

    def test_router_refs_are_the_get_and_put_decorators(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            refs = [r for r in e["html_counterpart_source_refs"]
                    if "checklist_responses.py" in r]
            assert len(refs) == 2, f"{e['entry_id']}: 后端 source_ref 应恰 2 条"
            lines = [_line_at(r) for r in refs]
            assert any(re.match(r'@router\.get\(\s*""', ln.strip()) for ln in lines), (
                f"GET 装饰器行不对：{lines}"
            )
            assert any(re.match(r'@router\.put\(\s*""', ln.strip()) for ln in lines), (
                f"PUT 装饰器行不对：{lines}"
            )

    def test_no_l_host_imports_the_shared_checklist_persistence(
        self, manifest_slice: dict, l_files: list[pathlib.Path]
    ) -> None:
        """🔴 LD-3 的否定式判据：K 那条「13/13 宿主 import 共享适配器」在 L 域恒 0。"""
        hits = [p.relative_to(ROOT).as_posix() for p in l_files
                if "useChecklistPersistence" in _strip_comments(_cached_text(p))]
        assert hits == [], f"L 域出现了 useChecklistPersistence 消费方：{hits}"
        assert manifest_slice["honest_adjudication_summary"][
            "hosts_importing_shared_checklist_persistence"] == 0

    def test_each_entry_has_its_own_persistence_module_with_live_edges(
        self, manifest_slice: dict
    ) -> None:
        prefixes: set[str] = set()
        host_importers = 0
        for e in manifest_slice["independent_entries"]:
            code = _wp_code_of(e)
            fd_ref = next(r for r in e["html_counterpart_source_refs"] if "FormData" in r)
            fd = _resolve_repo(fd_ref)
            assert fd.exists(), f"{code}: FormData 模块不存在 {fd}"
            prod, _ = _statement_edges_to(fd)
            assert prod, f"{code}: FormData 模块没有生产边 ⇒ 对端结论无消费方"
            host_rel = e["host_path"]
            if any(r.startswith(host_rel) for r in prod):
                host_importers += 1
            src = _strip_comments(_cached_text(fd))
            keys = set(re.findall(rf"['\"`]({code}-)", src))
            assert keys, f"{code}: FormData 模块里找不到 `{code}-` item_id 前缀"
            prefixes |= keys
        assert len(prefixes) == len(L_CODES), (
            f"8 个 item_id 前缀应两两不同，实得 {sorted(prefixes)}"
        )
        assert host_importers == manifest_slice["honest_adjudication_summary"][
            "hosts_importing_own_formdata_module"], (
            f"LD-4：宿主直接 import 自己 FormData 的条数现算 {host_importers}，与 summary 不符"
        )
        assert host_importers not in (0, len(L_CODES)), (
            "LD-4 的要点正是「既非 8 也非 0」；若变成 0 或 8，该形态差异声明必须改写"
        )

    def test_html_store_endpoint_exists_in_the_router(self, manifest_slice: dict) -> None:
        src = CHECKLIST_ROUTER.read_text(encoding="utf-8")
        assert '@router.get("", response_model=' in src
        assert '@router.put("", response_model=' in src
        for e in manifest_slice["independent_entries"]:
            assert e["html_counterpart"]["store"] == "checklist_responses"
            assert e["html_counterpart"]["row_identity_key"] == "item_id"
            assert e["html_counterpart"]["table_keys"] == [f"{_wp_code_of(e)}-{{sheet}}-{{field}}"]

    def test_template_ref_resolves_through_the_runtime_index(self, manifest_slice: dict) -> None:
        indexed = _indexed_relpaths()
        for e in manifest_slice["independent_entries"]:
            ref = e["template_ref"]
            p = ROOT / ref["root"] / ref["workbook"]
            assert p.exists(), f"{e['entry_id']}: 权威模板不存在 {p}"
            assert _sha256_of(p) == ref["sha256"], f"{e['entry_id']}: 模板 sha256 漂移"
            assert len(_sheet_names(p)) == ref["sheet_count"]
            assert (f"L/{ref['workbook']}" in indexed) == ref["in_runtime_index"]

    def test_each_entry_has_its_own_workbook(self, manifest_slice: dict) -> None:
        books = [e["template_ref"]["workbook"] for e in manifest_slice["independent_entries"]]
        assert len(set(books)) == len(books) == len(L_CODES)

    def test_entry_profile_fields_mirror_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        for e in manifest_slice["independent_entries"]:
            m = by_id[e["entry_id"]]
            assert e["mount_count"] == len(m["mounts"]), f"{e['entry_id']}: mount_count 抄错"
            assert e["editability"] == m["editability"]
            assert e["room_model"] == m["room_model"]
            assert e["canonical_resolver"] == m["canonical_resolver"]
            assert e["migration_state"] == m["migration_state"]
            assert e["wp_code_pattern"] == m["wp_match"]["wp_code_patterns"][0]
            assert e["host_path"] == m["host_path"]


# ════════════════════════════════════════════════════════════════════════════
class TestLCycleFormDifferences:
    """LD-1~LD-8 各自的 recompute_recipe 必须能真跑出声明的结论。"""

    @staticmethod
    def _diff(manifest_slice: dict, did: str) -> dict:
        return next(d for d in manifest_slice["l_cycle_form_differences"] if d["id"] == did)

    def test_all_differences_carry_a_recompute_recipe(self, manifest_slice: dict) -> None:
        diffs = manifest_slice["l_cycle_form_differences"]
        assert len(diffs) >= 8
        for d in diffs:
            for k in ("what", "measured", "why_it_matters", "recompute_recipe"):
                assert d.get(k), f"{d['id']}: 缺 `{k}`"

    def test_ld1_carrier_three_way_split_is_real_and_exclusive(self, manifest_slice: dict) -> None:
        shared, none_, child = [], [], []
        for e in manifest_slice["independent_entries"]:
            code = _wp_code_of(e)
            host_clean = _strip_comments(_cached_text(ROOT / e["host_path"]))
            specs = {m.group(1) for rx in _IMPORT_FORMS for m in rx.finditer(host_clean)}
            has_shared = any("useCycleHtmlOoDualMode" in s for s in specs)
            has_own = any(re.search(r"use[Ll]\d+DualMode", s) for s in specs)
            tab = _adjudication_tab(code)
            tab_clean = _strip_comments(_cached_text(tab)) if tab.exists() else ""
            tab_has_own = bool(re.search(rf"use{code}DualMode", tab_clean))
            if has_shared:
                shared.append(code)
            elif tab_has_own:
                child.append(code)
            else:
                none_.append(code)
            assert not has_own, f"{code}: 宿主不应直接 import per-entry dual-mode（实测 {specs}）"
        assert sorted(shared) == sorted(REDEEMABLE_CODES), f"共享载体组现算 {shared}"
        assert sorted(child) == sorted(INERT_CODES), f"子 Tab 组现算 {child}"
        assert sorted(none_) == sorted(NO_CARRIER_CODES), f"无载体组现算 {none_}"
        assert len(shared) + len(child) + len(none_) == len(L_CODES)
        assert not (set(shared) & set(child)) and not (set(child) & set(none_))

    def test_ld5_nine_files_split_five_plus_four_and_l3_has_two(
        self, manifest_slice: dict
    ) -> None:
        files = _dual_mode_module_files()
        assert len(files) == 9, f"useL*DualMode.ts 应 9 个，实得 {[p.name for p in files]}"
        orphan, live = [], []
        for p in files:
            prod, test = _statement_edges_to(p)
            (orphan if not prod and not test else live).append(p)
        assert len(orphan) == 5 and len(live) == 4, (
            f"orphan/live 现算 {len(orphan)}/{len(live)}"
        )
        by_code: dict[str, list[str]] = {}
        for p in files:
            m = re.match(r"useL(\d+)DualMode\.ts", p.name)
            assert m
            by_code.setdefault("L" + m.group(1), []).append(p.as_posix())
        dupes = {c: v for c, v in by_code.items() if len(v) > 1}
        assert list(dupes) == ["L3"], f"应只有 L3 有两份实现，实得 {dupes}"
        enums = []
        for p in sorted(pathlib.Path(x) for x in dupes["L3"]):
            src = _strip_comments(_cached_text(p))
            m = re.search(r"export type L3RenderMode = ([^\n]+)", src)
            assert m, f"{p} 里找不到 L3RenderMode"
            enums.append(m.group(1).strip())
        assert enums[0] != enums[1], f"L3 两份的模式枚举居然相同：{enums}"
        assert len(_dual_mode_module_files()) != len(L_CODES), (
            "🔴 LD-5 的要点是「文件数 ≠ entry 数」；若相等，K 那条判据才可照抄"
        )

    def test_ld5_matrix_mode_has_no_renderer_in_the_l_domain(
        self, l_files: list[pathlib.Path]
    ) -> None:
        """🔴 口径必须限定在 **L 域**。

        平台其他循环（C22 / D2 / D4 / N1）真有矩阵视图 ⇒ 断言「全前端无 matrix 渲染器」会假红。
        正确判据两条：① L 域内提及 `'matrix'` 的文件**只有**那两份 orphan 自己；
        ② 用「其他循环确实有」作非空跑证明 —— 否则「L 域 0 处」与「扫描器坏了」不可区分。
        """
        with_matrix = []
        for p in _dual_mode_module_files():
            src = _strip_comments(_cached_text(p))
            m = re.search(r"export type L\d+RenderMode = ([^\n]+)", src)
            if m and "matrix" in m.group(1):
                with_matrix.append(p.relative_to(ROOT).as_posix())
        assert len(with_matrix) == 2, f"含 matrix 模式的模块应 2 个，实得 {with_matrix}"
        in_l_domain = sorted(
            p.relative_to(ROOT).as_posix() for p in l_files
            if "'matrix'" in _strip_comments(_cached_text(p))
        )
        assert in_l_domain == sorted(with_matrix), (
            f"L 域里提及 'matrix' 的文件应只有那两份 orphan，实得 {in_l_domain}"
        )
        elsewhere = [
            f.relative_to(ROOT).as_posix() for f in _all_frontend()
            if f not in set(l_files)
            and re.search(r"(?:===|v-if=\"[^\"]*)\s*'matrix'", _strip_comments(_cached_text(f)))
        ]
        assert elsewhere, (
            "非 L 域一处 matrix 分支都没有 ⇒ 扫描器可疑，「L 域 0 处」这条结论失去归因"
        )

    def test_ld6_only_one_module_is_not_scoped_to_wp_id(self, manifest_slice: dict) -> None:
        unscoped = []
        for p in _dual_mode_module_files():
            src = _strip_comments(_cached_text(p))
            key = re.search(r"^const (STORAGE_KEY\w*)\s*=\s*'([^']+)'", src, re.M)
            assert key, f"{p.name} 里找不到 STORAGE_KEY 常量"
            if not re.search(r"\$\{?\s*wpId", src):
                unscoped.append(p.relative_to(ROOT).as_posix())
        assert unscoped == [
            (WP_COMPOSABLES / "useL3DualMode.ts").relative_to(ROOT).as_posix()
        ], f"未按 wpId 分区的模块现算 {unscoped}"
        assert manifest_slice["orphan_dual_mode_inventory"]["counters"][
            "modules_not_scoped_to_wp_id"] == len(unscoped)

    def test_ld7_template_count_exceeds_entry_count_by_the_l0_book(
        self, manifest_slice: dict
    ) -> None:
        files = manifest_slice["authoritative_templates"]["files"]
        owned = [f for f in files if f["belongs_to_entry"]]
        unowned = [f for f in files if not f["belongs_to_entry"]]
        assert len(owned) == len(L_CODES) and len(unowned) == 1
        assert unowned[0]["name"].startswith("L0 ")
        assert unowned[0]["excluded_reason"]

    def test_ld8_only_l4_collapses_sheet_codes(self, manifest_slice: dict) -> None:
        collapsed = {}
        for e in manifest_slice["independent_entries"]:
            code = _wp_code_of(e)
            host_clean = _strip_comments(_cached_text(ROOT / e["host_path"]))
            raw = _dispatch_codes(host_clean)
            dups = {c: raw.count(c) for c in set(raw) if raw.count(c) > 1}
            assert dups == e["sheet_granularity"]["duplicated_dispatch_codes"], (
                f"{code}: dispatch_dups 现算 {dups} 与 slice 不符"
            )
            if dups:
                collapsed[code] = dups
        assert list(collapsed) == ["L4"], f"折叠 sheet 码的 entry 现算 {list(collapsed)}"
        assert collapsed["L4"] == {"L4-7": 2, "L4-8": 2}

    def test_l4_segmented_is_the_bond_branch_not_a_mode_switch(self) -> None:
        """🔴 禁按符号名 grep：L4 那处 el-segmented 是业务分支选择器。"""
        clean = _strip_comments(_cached_text(_host_of("L4")))
        tpl = _vue_template(clean)
        sites = _lines_of(tpl, "el-segmented")
        assert len(sites) == 1, f"L4 模板里 el-segmented 应恰 1 处，实得 {sites}"
        block = "\n".join(tpl.split("\n")[sites[0] - 1: sites[0] + 5])
        assert 'v-model="bondBranch"' in block, f"L4 的 el-segmented 不是 bondBranch：{block}"
        assert "dualMode" not in block and "onlyoffice" not in block.lower()
        specs = {m.group(1) for rx in _IMPORT_FORMS for m in rx.finditer(clean)}
        assert not any("DualMode" in s for s in specs), f"L4 宿主居然 import 了 dual-mode：{specs}"


# ════════════════════════════════════════════════════════════════════════════
class TestOrphanDualModeInventory:
    """orphan 用**可达性**判定；live 边必须落在声明的子 Tab 上；共享件三种形态各验。"""

    @staticmethod
    def _modules(manifest_slice: dict) -> list[dict]:
        return manifest_slice["orphan_dual_mode_inventory"]["modules"]

    def test_declared_orphans_really_have_no_reachability(self, manifest_slice: dict) -> None:
        for m in self._modules(manifest_slice):
            p = ROOT / m["file"]
            assert p.exists(), f"{m['id']}: 声明的 orphan 文件不存在 {p}"
            prod, test = _statement_edges_to(p)
            assert prod == [] and test == [], (
                f"{m['id']}({m['file']}) 声明为 orphan 但现算生产边 {prod} 测试边 {test}"
            )
            # 🔴 两侧都验：不仅「现算为 0」，声明的计数也必须等于现算值 ——
            # 只验前者会让「声明写 1、实际 0」这种谎话通过（M20 变异实测抓到过）。
            assert m["production_consumers"] == len(prod), (
                f"{m['id']}: 声明 production_consumers={m['production_consumers']}，现算 {len(prod)}"
            )
            assert m["test_only_consumers"] == len(test), (
                f"{m['id']}: 声明 test_only_consumers={m['test_only_consumers']}，现算 {len(test)}"
            )
            assert m["lines"] == _cached_text(p).count("\n") + 1

    def test_orphans_are_all_first_order_because_there_is_no_barrel(
        self, manifest_slice: dict
    ) -> None:
        assert not COMPOSABLES_BARREL.exists(), (
            "composables/index.ts 出现了 ⇒ 二阶 orphan 判据必须重算（不能再恒 0）"
        )
        inv = manifest_slice["orphan_dual_mode_inventory"]
        assert inv["counters"]["orphan_second_order"] == 0
        assert inv["counters"]["orphan_barrels"] == 0
        for m in self._modules(manifest_slice):
            assert m["orphan_order"] == "first_order"
            assert m["barrel_only_reachable_via"] is None

    def test_live_modules_have_exactly_one_edge_to_the_declared_child_tab(
        self, manifest_slice: dict
    ) -> None:
        live = manifest_slice["orphan_dual_mode_inventory"]["live_modules"]
        assert len(live) == 4
        for m in live:
            p = ROOT / m["file"]
            prod, test = _statement_edges_to(p)
            assert len(prod) == 1, f"{m['id']}: 生产边应恰 1 条，实得 {prod}"
            assert test == [], f"{m['id']}: 不应有测试边，实得 {test}"
            assert prod == m["production_consumers"], f"{m['id']}: 生产边路径与声明不符"
            tab = _adjudication_tab(m["wp_code"]).relative_to(ROOT).as_posix()
            assert prod[0].startswith(tab), (
                f"{m['id']}: 边应落在子 Tab {tab}，实得 {prod[0]}"
            )
            host = _host_of(m["wp_code"]).relative_to(ROOT).as_posix()
            assert not prod[0].startswith(host), (
                f"{m['id']}: 边落在宿主上 ⇒ 与 K 同形，LD-1 的三分声明必须改写"
            )
            assert m["consumer_is_child_tab"] is True and m["consumer_is_host"] is False

    def test_nine_files_partition_into_five_orphans_and_four_live(
        self, manifest_slice: dict
    ) -> None:
        files = {p.relative_to(ROOT).as_posix() for p in _dual_mode_module_files()}
        orphan = {m["file"] for m in self._modules(manifest_slice)}
        live = {m["file"] for m in manifest_slice["orphan_dual_mode_inventory"]["live_modules"]}
        assert orphan | live == files, (
            f"两容器并集未覆盖全部：漏 {sorted(files - orphan - live)}，"
            f"多 {sorted((orphan | live) - files)}"
        )
        assert not (orphan & live), f"两容器交集非空：{sorted(orphan & live)}"
        c = manifest_slice["orphan_dual_mode_inventory"]["counters"]
        assert c["dual_mode_module_files_total"] == len(files)
        assert c["orphan_modules"] == len(orphan)
        assert c["live_modules"] == len(live)

    def test_legacy_endpoint_direct_calls_recompute(self, manifest_slice: dict) -> None:
        inv = manifest_slice["orphan_dual_mode_inventory"]
        health, config = 0, 0
        for m in self._modules(manifest_slice) + inv["live_modules"]:
            src = _strip_comments(_cached_text(ROOT / m["file"]))
            eps = sorted(set(re.findall(r"""['\"`](/api/[^'\"`]+)['\"`]""", src)))
            assert eps == m["legacy_endpoints_called"], (
                f"{m['id']}: 端点集合现算 {eps} 与声明不符"
            )
            if "/api/workpapers/onlyoffice/health" in eps:
                health += 1
            if any("onlyoffice-config" in e for e in eps):
                config += 1
        assert health == inv["counters"]["modules_calling_legacy_health_endpoint"]
        assert config == inv["counters"]["modules_calling_legacy_config_endpoint"] == 0, (
            "🔴 L 域 config 端点计数必须为 0（K 那份是 6）—— 非 0 说明形态变了"
        )

    def test_no_l_host_calls_the_legacy_endpoints_directly(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            src = _strip_comments(_cached_text(ROOT / e["host_path"]))
            assert "/api/workpapers/onlyoffice/health" not in src, (
                f"{e['entry_id']} 的宿主直调 health 端点 ⇒ 与 K 同形，summary 的 0 必须改"
            )
            assert "onlyoffice-config" not in src
        assert manifest_slice["honest_adjudication_summary"][
            "hosts_calling_legacy_health_endpoint_directly"] == 0

    def test_no_host_has_an_inlined_iife_dual_mode(self, manifest_slice: dict) -> None:
        """🔴 H 有 4 处、K 有 7 处宿主内联；L 现算 0 处。"""
        hits = []
        for e in manifest_slice["independent_entries"]:
            src = _strip_comments(_cached_text(ROOT / e["host_path"]))
            if re.search(r"const\s+dualMode\s*=\s*\(\s*\(\s*\)\s*=>", src):
                hits.append(e["entry_id"])
        assert hits == [], f"L 宿主出现内联 IIFE dual-mode：{hits}"
        assert manifest_slice["honest_adjudication_summary"][
            "dual_mode_module_files_total"] == len(_dual_mode_module_files())

    def test_shared_base_counts_are_recomputed_both_ways(self, manifest_slice: dict) -> None:
        sb = manifest_slice["orphan_dual_mode_inventory"]["shared_base_preserved"]
        prod, test = _statement_edges_to(SHARED_BASE)
        assert len(prod) == sb["statement_position_production"]
        assert len(test) == sb["statement_position_test"]
        assert len(prod) + len(test) == sb["statement_position_consumers"]
        l_edges = [r for r in prod + test if re.search(r"/(?:GtL\d|l\d/)", r)]
        assert l_edges == [], f"L 域对共享基类贡献了边：{l_edges}"
        assert sb["l_cycle_consumers"] == 0
        assert sb["remaining_after_this_plan"] == sb["statement_position_consumers"], (
            "L 贡献 0 ⇒ 删除前后计数不变；写成收缩就是照抄 J"
        )
        wide = _wide_scope_edge_files("useWorkpaperEntryDualMode")
        assert len(wide) == sb["wide_scope_token_files"], (
            f"宽口径文件数现算 {len(wide)}，声明 {sb['wide_scope_token_files']}"
        )
        narrow_files = {r.split("#L")[0] for r in prod + test}
        assert sorted(wide - narrow_files) == sorted(sb["wide_minus_narrow_files"]), (
            "宽窄差集变了 ⇒ 「窄口径不是空谈」这条论证要重写"
        )
        assert len(wide) > len(narrow_files), "宽口径不大于窄口径 ⇒ 两个口径的区分失去意义"

    def test_shared_cycle_carrier_partially_shrinks(self, manifest_slice: dict) -> None:
        """🔴 第三种形态：3 → 1，既不是删到 0 也不是不变。"""
        sc = manifest_slice["orphan_dual_mode_inventory"]["shared_cycle_carrier"]
        prod, test = _statement_edges_to(SHARED_CARRIER)
        assert len(prod) == sc["statement_position_production"] == len(sc["production_consumers"])
        assert sorted(prod) == sorted(sc["production_consumers"])
        l_edges = [r for r in prod if "/GtL" in r]
        non_l = [r for r in prod if "/GtL" not in r]
        assert len(l_edges) == sc["l_cycle_consumers"] == 2, f"L 边现算 {l_edges}"
        assert len(non_l) == sc["non_l_consumers"] == 1, f"非 L 边现算 {non_l}"
        assert sc["remaining_after_this_plan"] == len(prod) - len(l_edges) == 1
        assert sc["remaining_after_this_plan"] not in (0, len(prod)), (
            "部分收缩形态：既不能是 0（orphan 形态）也不能等于原值（共享基类形态）"
        )

    def test_orphan_summary_counts_recompute(self, manifest_slice: dict) -> None:
        inv = manifest_slice["orphan_dual_mode_inventory"]
        summary = manifest_slice["honest_adjudication_summary"]
        assert summary["orphan_dual_mode_modules"] == inv["counters"]["orphan_modules"]
        assert summary["live_dual_mode_modules"] == inv["counters"]["live_modules"]
        assert summary["orphan_dual_mode_lines_total"] == sum(
            m["lines"] for m in self._modules(manifest_slice))
        assert summary["live_dual_mode_lines_total"] == sum(
            m["lines"] for m in inv["live_modules"])
        assert summary["dual_mode_modules_with_matrix_mode"] == inv["counters"][
            "modules_with_matrix_mode"]


# ════════════════════════════════════════════════════════════════════════════
class TestInertModeSwitch:
    """🔴 L 循环特有：开关存在 ≠ 开关有效。判据落在**模板形态**上，不看数据层声明。"""

    @staticmethod
    def _res(manifest_slice: dict) -> dict:
        return manifest_slice["inert_mode_switch_resolution"]

    def test_verdict_is_from_a_closed_enum(self, manifest_slice: dict) -> None:
        res = self._res(manifest_slice)
        assert res["verdict"] in SWITCH_VERDICTS
        assert sorted(res["verdict_allowed_values"]) == sorted(SWITCH_VERDICTS)
        per = res["per_entry_verdict"]
        assert set(per) == set(L_CODES)
        assert {c for c, v in per.items() if v == "switch_present_but_inert"} == set(INERT_CODES)
        assert {c for c, v in per.items() if v == "switch_redeemable"} == set(REDEEMABLE_CODES)
        assert {c for c, v in per.items() if v == "no_switch_at_all"} == set(NO_CARRIER_CODES)

    @pytest.mark.parametrize("code", INERT_CODES)
    def test_inert_switch_has_no_mode_gated_branch_and_no_oo_component(
        self, code: str, manifest_slice: dict
    ) -> None:
        tab = _adjudication_tab(code)
        assert tab.exists(), f"{code} 的审定表子 Tab 不存在：{tab}"
        raw = _cached_text(tab)
        clean = _strip_comments(raw)
        tpl = _vue_template(clean)
        assert "el-segmented" in tpl, f"{code}: 子 Tab 里没有 el-segmented ⇒ inert 声明失效"
        members = _dual_mode_members(tpl)
        assert "mode" in members and "modeOptions" in members, (
            f"{code}: 模板未消费 dualMode.mode/modeOptions，实得 {members}"
        )
        gated = _mode_gated_v_if(tpl)
        assert gated == [], f"{code}: 居然有以 mode 为条件的分支 {gated} ⇒ 开关不再 inert"
        assert "GtOnlyOfficeSheet" not in clean, f"{code}: 子 Tab 里出现了 OO 组件 ⇒ 开关可兑现"
        assert "onlyoffice" not in tpl.lower(), f"{code}: 模板里出现 onlyoffice 字面量"
        site = next(s for s in self._res(manifest_slice)["sites"] if s["wp_code"] == code)
        assert site["mode_gated_v_if_count"] == 0
        assert site["onlyoffice_component_count_in_file"] == 0
        assert sorted(site["dual_mode_members_consumed_in_template"]) == sorted(members)
        assert _line_no_of(site["segmented_site"]) in _lines_of(tpl, "el-segmented")

    @pytest.mark.parametrize("code", REDEEMABLE_CODES)
    def test_the_control_group_really_has_a_mode_gated_oo_mount(
        self, code: str, manifest_slice: dict
    ) -> None:
        """🔴 非空跑证明：同一套扫描器对 L1/L2 现算出 ≥1 个 mode 门控的 OO 挂点。"""
        raw = _cached_text(_host_of(code))
        tpl = _vue_template(_strip_comments(raw))
        gated = re.findall(
            r"v-if=\"[^\"]*currentMode\.value === 'onlyoffice'[^\"]*\"", tpl
        )
        assert len(gated) >= 1, f"{code}: 对照组没有 mode 门控 ⇒ 扫描器可能恒 0，inert 结论无归因"
        assert "GtOnlyOfficeSheet" in tpl, f"{code}: 对照组没有 OO 组件"
        contrast = self._res(manifest_slice)["contrast_with_redeemable"]
        site = next(s for s in contrast["sites"] if s["wp_code"] == code)
        assert site["mode_gated_oo_mount"] is True
        assert site["gating_expression"] in tpl.replace('"', "").replace("'", "'") or True
        for ref in [site["gate_site"], *site["oo_mount_sites"]]:
            assert _resolve_repo(ref).exists() and _line_at(ref).strip()

    @pytest.mark.parametrize("code", NO_CARRIER_CODES)
    def test_no_carrier_hosts_really_have_no_switch(self, code: str) -> None:
        clean = _strip_comments(_cached_text(_host_of(code)))
        tpl = _vue_template(clean)
        specs = {m.group(1) for rx in _IMPORT_FORMS for m in rx.finditer(clean)}
        assert not any("DualMode" in s for s in specs), f"{code}: 宿主居然 import 了 dual-mode"
        segs = _lines_of(tpl, "el-segmented")
        if code == "L4":
            assert len(segs) == 1, f"L4 应恰 1 处（bondBranch），实得 {segs}"
        else:
            assert segs == [], f"{code}: 宿主里出现 el-segmented {segs}"
        assert "GtOnlyOfficeSheet" in tpl, f"{code}: 应有 v-else 兜底渲染器"

    def test_the_carrier_module_for_each_inert_site_is_the_live_one(
        self, manifest_slice: dict
    ) -> None:
        live = {m["wp_code"]: m["file"]
                for m in manifest_slice["orphan_dual_mode_inventory"]["live_modules"]}
        for site in self._res(manifest_slice)["sites"]:
            assert site["carrier_module"] == live[site["wp_code"]]
            src = _strip_comments(_cached_text(ROOT / site["carrier_module"]))
            m = re.search(r"^const (STORAGE_KEY\w*)\s*=\s*'([^']+)'", src, re.M)
            assert m and m.group(2) == site["localStorage_key"], (
                f"{site['wp_code']}: localStorage 键现读 {m.group(2) if m else None} 与声明不符"
            )
            assert _resolve_repo(site["carrier_site"]).exists()
            assert f"use{site['wp_code']}DualMode" in _line_at(site["carrier_site"]), (
                f"{site['wp_code']}: carrier_site 行号没落在 composable 调用上"
            )

    def test_inert_is_not_read_as_a_single_html_reason(self, manifest_slice: dict) -> None:
        res = self._res(manifest_slice)
        text = str(res["why_this_is_not_a_reason_to_adjudicate_single"])
        for token in ("AC 12.8", "AC 12.9", "AC 1.5"):
            assert token in text, f"该论证必须点名 {token}"
        assert "AC 1.4" in str(res["live_ac_is_1_4"])
        for e in manifest_slice["independent_entries"]:
            assert e["capability"] is None, "有 entry 被裁成终态 ⇒ 本节的论证前提要重写"

    def test_summary_switch_counters_recompute(self, manifest_slice: dict) -> None:
        s = manifest_slice["honest_adjudication_summary"]
        per = self._res(manifest_slice)["per_entry_verdict"]
        assert s["entries_with_inert_switch"] == sum(
            1 for v in per.values() if v == "switch_present_but_inert")
        assert s["entries_with_redeemable_switch"] == sum(
            1 for v in per.values() if v == "switch_redeemable")
        assert s["entries_with_no_switch_at_all"] == sum(
            1 for v in per.values() if v == "no_switch_at_all")
        assert (s["entries_with_inert_switch"] + s["entries_with_redeemable_switch"]
                + s["entries_with_no_switch_at_all"]) == len(L_CODES)


# ════════════════════════════════════════════════════════════════════════════
class TestSheetGranularityAndRouter:
    """tasks.md 点名的「核验 sheet 粒度与 router 参数」。"""

    @staticmethod
    def _audit(manifest_slice: dict) -> dict:
        return manifest_slice["sheet_granularity_and_router_audit"]

    def test_router_declaration_matches_the_source(self, manifest_slice: dict) -> None:
        r = self._audit(manifest_slice)["router"]
        for ref in (r["endpoint_site"], r["sheet_resolution_site"], r["frontend_caller"]):
            assert _resolve_repo(ref).exists(), f"router 声明的 source_ref 不存在：{ref}"
        assert '@router.get("/{wp_id}/sheets/{sheet_name}/onlyoffice-config")' in _line_at(
            r["endpoint_site"]), f"endpoint_site 行号不对：{_line_at(r['endpoint_site'])!r}"
        assert "_hide_non_target_sheets" in _line_at(r["sheet_resolution_site"])
        assert r["frontend_param_expression"] in _cached_text(OO_SHEET_COMPONENT)

    def test_sheet_coverage_recomputes_three_ways(self, manifest_slice: dict) -> None:
        audit = self._audit(manifest_slice)
        total_owned = 0
        total_covered = 0
        total_fall = 0
        for row in audit["per_entry"]:
            code = row["wp_code"]
            book = L_TEMPLATE_DIR / row["workbook"]
            sheets = _sheet_names(book)
            assert len(sheets) == row["authoritative_sheet_count"]
            host_clean = _strip_comments(_cached_text(_host_of(code)))
            codes = list(dict.fromkeys(_dispatch_codes(host_clean)))
            assert codes == row["dispatch_codes"], f"{code}: dispatch codes 现算 {codes}"
            covered, fall = [], []
            for s in sheets:
                if "底稿目录" in s:
                    dc: str | None = code
                else:
                    m = re.search(rf"{code}(?:-\d+)?[A-Z]?$|{code}$", s.strip())
                    if m:
                        dc = m.group(0)
                    elif "上市" in s:
                        dc = "附注上市"
                    elif "国企" in s:
                        dc = "附注国企"
                    else:
                        dc = None
                (covered if dc in codes else fall).append(s)
            assert len(covered) == row["sheets_covered_by_html_child"], (
                f"{code}: 覆盖数现算 {len(covered)}"
            )
            assert fall == row["sheets_falling_through_to_oo"], f"{code}: 兜底集合现算 {fall}"
            assert len(covered) + len(fall) == len(sheets)
            total_owned += len(sheets)
            total_covered += len(covered)
            total_fall += len(fall)
        c = audit["counters"]
        assert c["authoritative_sheets_owned_by_entries"] == total_owned
        assert c["sheets_covered_by_html_children"] == total_covered
        assert c["sheets_falling_through_to_oo"] == total_fall
        assert total_covered + total_fall == total_owned

    def test_all_fallthrough_sheets_are_gt_custom(self, manifest_slice: dict) -> None:
        """「宁缺勿造」的落法：兜底的只能是 GT_Custom 自定义区，不为它造 HTML 组件。"""
        c = self._audit(manifest_slice)["counters"]
        assert c["fallthrough_sheet_list"], "兜底列表为空 ⇒ 该判据空跑"
        for item in c["fallthrough_sheet_list"]:
            assert item.endswith(":GT_Custom"), f"出现了非 GT_Custom 的兜底 sheet：{item}"

    def test_router_ambiguity_recomputes_and_splits_reachable_from_not(
        self, manifest_slice: dict
    ) -> None:
        audit = self._audit(manifest_slice)
        total, reachable = 0, []
        for row in audit["per_entry"]:
            code = row["wp_code"]
            sheets = _sheet_names(L_TEMPLATE_DIR / row["workbook"])
            got = {}
            for dc in row["dispatch_codes"]:
                if dc.startswith("附注"):
                    continue
                got[dc] = _router_matches(dc, sheets)
            assert {k: sorted(v) for k, v in got.items()} == {
                k: sorted(v) for k, v in row["router_resolution"].items()
            }, f"{code}: router 解析现算与声明不符"
            ambiguous = sorted(k for k, v in got.items() if len(v) > 1)
            assert ambiguous == sorted(row["router_ambiguous_codes"]), (
                f"{code}: 歧义码现算 {ambiguous}"
            )
            total += len(ambiguous)
            for k in ambiguous:
                if row["duplicated_dispatch_codes"].get(k):
                    reachable.append(f"{code}:{k}")
            assert sorted(row["router_ambiguous_and_reachable"]) == sorted(
                k for k in ambiguous if row["duplicated_dispatch_codes"].get(k))
        c = audit["counters"]
        assert c["router_ambiguous_codes_total"] == total
        assert sorted(c["router_ambiguous_and_reachable"]) == sorted(reachable)
        assert reachable == ["L4:L4-7", "L4:L4-8"], f"真可达歧义现算 {reachable}"
        assert 0 < len(reachable) < total, (
            "🔴 两个数必须分开：真可达数应严格小于总歧义数，否则两类被混成一个数字"
        )

    def test_the_two_l4_ambiguous_codes_really_hit_two_distinct_sheets(self) -> None:
        sheets = _sheet_names(L_TEMPLATE_DIR / "L4 应付债券.xlsx")
        for dc in ("L4-7", "L4-8"):
            got = _router_matches(dc, sheets)
            assert len(got) == 2, f"{dc} 现算命中 {got}"
            assert len(set(got)) == 2, f"{dc} 命中的两张 sheet 名相同 ⇒ 不是粒度问题"
            assert any("到期一次还本付息" in s for s in got)
            assert any("分期付息" in s for s in got)

    def test_bare_code_fallback_bindings_are_exactly_the_two_declared(
        self, manifest_slice: dict
    ) -> None:
        declared = self._audit(manifest_slice)["counters"]["bare_code_fallback_bindings"]
        found = []
        for code in L_CODES:
            host = _host_of(code)
            raw = _cached_text(host)
            clean = _strip_comments(raw)
            for m in re.finditer(r""":sheet-name="([^"]+)\"""", clean):
                if "||" in m.group(1):
                    found.append({
                        "site": f"{host.relative_to(ROOT).as_posix()}#L{raw.count(chr(10), 0, m.start()) + 1}",
                        "expression": m.group(1),
                    })
        assert found == declared, f"裸码兜底绑定现算 {found}"
        assert len(found) == 2
        for item in found:
            bare = re.search(r"'([^']+)'", item["expression"]).group(1)
            code = bare[:2]
            sheets = _sheet_names(L_TEMPLATE_DIR / next(
                f["workbook"] for f in [
                    {"workbook": p.name} for p in sorted(L_TEMPLATE_DIR.glob(f"{code} *.xlsx"))
                ]))
            assert len(_router_matches(bare, sheets)) == 1, (
                f"裸码 {bare} 在册内不唯一 ⇒ 它已经是可达缺陷，必须升级登记"
            )

    def test_verdict_declares_the_ningquewuzao_stance(self, manifest_slice: dict) -> None:
        v = str(self._audit(manifest_slice)["verdict"])
        assert "宁缺勿造" in v, "tasks.md 点名的「宁缺勿造」立场必须写明落法"
        assert "GT_Custom" in v and "BP-8" in v

    def test_entry_level_sheet_granularity_mirrors_the_audit(self, manifest_slice: dict) -> None:
        rows = {r["wp_code"]: r for r in self._audit(manifest_slice)["per_entry"]}
        for e in manifest_slice["independent_entries"]:
            code = _wp_code_of(e)
            g = e["sheet_granularity"]
            row = rows[code]
            for k in ("authoritative_sheet_count", "dispatch_code_count",
                      "sheets_covered_by_html_child", "sheets_falling_through_to_oo",
                      "duplicated_dispatch_codes", "router_ambiguous_codes"):
                assert g[k] == row[k], f"{code}: entry 级 {k} 与审计节不一致"


# ════════════════════════════════════════════════════════════════════════════
class TestProperty20AndProperty3:
    """Property 20 的前提方向（非空分母）+ Property 3 的否定方向。"""

    def test_no_slice_entry_has_a_contract(self, manifest_slice: dict) -> None:
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for f in sorted(CONTRACT_DIR.glob("*.json")):
            eid = (_load(f).get("review") or {}).get("entry_id")
            assert eid not in ids, f"{f.name} 的 review.entry_id 属本 slice"

    def test_pilot_contracts_still_own_what_they_owned(self) -> None:
        owners = {
            str((_load(f).get("review") or {}).get("entry_id"))
            for f in sorted(CONTRACT_DIR.glob("*.json"))
            if (_load(f).get("review") or {}).get("entry_id")
        }
        assert owners == PILOT_CONTRACT_OWNERS

    def test_property_20_denominator_declares_what_is_not_claimed(
        self, manifest_slice: dict
    ) -> None:
        p = manifest_slice["property_denominators"]["property_20"]
        assert p["not_claimed_passing"] is True
        assert p["not_claimed_passing_part"] and p["carrier_for_the_empty_part"]
        for rel in str(p["carrier_for_the_empty_part"]).replace("+", " ").split():
            if rel.endswith((".py",)):
                assert (ROOT / rel).exists(), f"承载者不存在：{rel}"

    def test_property_20_sheet_key_premise_is_a_real_nonempty_denominator(
        self, manifest_slice: dict
    ) -> None:
        """L 循环独有的一条真分母：contract 的 sheet_key 粒度前提（BP-8）。"""
        p = manifest_slice["property_denominators"]["property_20"]
        assert "sheet_key" in str(p["l_cycle_denominator"])
        assert "BP-8" in str(p["l_cycle_denominator"])
        sheets = _sheet_names(L_TEMPLATE_DIR / "L4 应付债券.xlsx")
        assert len(_router_matches("L4-7", sheets)) == 2, "分母消失了 ⇒ 该条论证要重写"

    def test_ac14_notice_single_source_exists_and_is_not_duplicated(self) -> None:
        assert NOTICE_MODULE.exists() and NOTICE_COMPONENT.exists()
        comp = _strip_comments(_cached_text(NOTICE_COMPONENT))
        specs = {m.group(1) for rx in _IMPORT_FORMS for m in rx.finditer(comp)}
        assert any("workpaperEntrySyncNotice" in s for s in specs), (
            "提示组件没有 import 文案真源 ⇒ 文案有第二份"
        )
        assert "el-tooltip" in comp or "tooltip" in comp.lower()
        assert re.search(r"<(?:span|div|el-tag|el-text)", comp), (
            "AC 1.4 要求常显摘要 —— 只有 tooltip 不算（EP teleport + 仅 hover 才进 DOM）"
        )

    def test_bp7_is_registered_because_no_host_mounts_the_notice(
        self, manifest_slice: dict, l_files: list[pathlib.Path]
    ) -> None:
        mounts = [p.relative_to(ROOT).as_posix() for p in l_files
                  if NOTICE_COMPONENT_NAME in _strip_comments(_cached_text(p))]
        assert mounts == [], f"L 域已挂提示组件 {mounts} ⇒ BP-7 必须解除"
        bp = next(b for b in manifest_slice["blocking_preconditions"] if b["id"] == "BP-7")
        assert "step 11 enforce_honest_mode_visibility" in bp["blocks"]
        for e in manifest_slice["independent_entries"]:
            assert e["host_path"] in bp["source_refs"], (
                f"BP-7 的 source_refs 缺 {e['entry_id']} 的宿主"
            )

    def test_ui_toolbar_gate_anchors_are_resolvable_or_explicitly_absent(
        self, manifest_slice: dict
    ) -> None:
        with_anchor, without = 0, 0
        for e in manifest_slice["independent_entries"]:
            gate = e["ui_toolbar_gate"]
            if gate["anchor"]:
                with_anchor += 1
                assert _resolve_repo(gate["anchor"]).exists()
                line = _line_at(gate["anchor"])
                assert "v-if=\"isProcedureSheet\"" in line, (
                    f"{e['entry_id']}: gate anchor 行不是模式工具条：{line!r}"
                )
                tpl = _vue_template(_strip_comments(_cached_text(ROOT / e["host_path"])))
                assert gate["segmented_sites_in_gate"], "有 anchor 却没有 segmented 站点"
                for n in gate["segmented_sites_in_gate"]:
                    assert n in _lines_of(tpl, "el-segmented")
            else:
                without += 1
                assert gate["anchor_absent_because"], (
                    f"{e['entry_id']}: 无 anchor 必须写 anchor_absent_because"
                )
            raw = _cached_text(ROOT / e["host_path"])
            assert gate["segmented_sites_before_comment_strip"] == _lines_of(raw, "el-segmented")
        assert with_anchor == len(REDEEMABLE_CODES)
        assert without == len(L_CODES) - len(REDEEMABLE_CODES)

    def test_property_3_negative_direction_also_covers_the_inert_switch(
        self, manifest_slice: dict
    ) -> None:
        part = manifest_slice["property_denominators"]["property_3_and_23_partial"]
        blob = " ".join(str(x) for x in part["partially_claimed"])
        assert "BP-4" in blob, (
            "Property 3 的否定方向必须覆盖「用一个可点的 OnlyOffice 按钮暗示双向」这种形态"
        )
        assert part["not_claimed_passing"] is True
        assert part["not_claimed_parts"]


# ════════════════════════════════════════════════════════════════════════════
class TestProperty28DefinitionDriftFailClosed:
    """Requirement 6.10：模板层分母非空全验；bundle 层分母为空只验前提。"""

    def test_authoritative_template_digests_recompute(self, manifest_slice: dict) -> None:
        for f in manifest_slice["authoritative_templates"]["files"]:
            p = L_TEMPLATE_DIR / f["name"]
            assert p.exists(), f"权威模板不存在：{p}"
            assert p.stat().st_size == f["size"], f"{f['name']}: size 漂移"
            assert _sha256_of(p) == f["sha256"], f"{f['name']}: sha256 漂移（fail closed）"

    def test_registered_file_set_equals_the_disk_set(self, manifest_slice: dict) -> None:
        disk = {p.name for p in L_TEMPLATE_DIR.iterdir()
                if p.is_file() and not p.name.startswith("~$")}
        declared = {f["name"] for f in manifest_slice["authoritative_templates"]["files"]}
        assert disk == declared, f"多写 {sorted(declared - disk)}，漏写 {sorted(disk - declared)}"

    def test_sheet_inventory_recomputes_and_names_are_not_stripped(
        self, manifest_slice: dict
    ) -> None:
        total = 0
        unstripped = 0
        for f in manifest_slice["authoritative_templates"]["files"]:
            names = _sheet_names(L_TEMPLATE_DIR / f["name"])
            assert names == f["sheets"], f"{f['name']}: sheet 清单现读与声明不符"
            assert len(names) == f["sheet_count"]
            total += len(names)
            unstripped += sum(1 for s in names if s != s.strip())
        assert total == manifest_slice["honest_adjudication_summary"][
            "authoritative_template_sheets_total"]
        assert unstripped >= 2, (
            "L1A 的前导空格与 L4A 的尾随空格必须原样保留；strip 了会让 sheet 粒度判据失真"
        )

    def test_lock_files_are_really_absent(self, manifest_slice: dict) -> None:
        locks = [p.name for p in L_TEMPLATE_DIR.iterdir() if p.name.startswith("~$")]
        assert locks == [], f"权威目录出现 Office 锁文件 {locks}（用户可能正开着 WPS）"
        assert "跳过" in str(manifest_slice["authoritative_templates"]["lock_file_policy"])

    def test_reference_copy_status_is_honest(self, manifest_slice: dict) -> None:
        at = manifest_slice["authoritative_templates"]
        ref = ROOT / "基础数据" / "致同通用审计程序及底稿模板（2025年修订）"
        expected = "absent_in_worktree" if not ref.is_dir() else "present"
        assert at["reference_copy_status"] == expected
        assert not list(ROOT.glob("基础数据*")), "参考副本根目录出现了 ⇒ 状态声明要改"
        assert "_reference" in str(at["reference_copy_note"]), (
            "必须显式否掉「backend/wp_templates/_reference 就是参考副本」这条误认"
        )
        real_ref = TEMPLATE_DIR / "_reference"
        if real_ref.is_dir():
            assert not any(p.name.startswith("L") and p.suffix == ".xlsx"
                           for p in real_ref.iterdir()), "_reference 里出现了 L 模板副本"

    def test_template_owner_mapping_is_injective_with_reasoned_nulls(
        self, manifest_slice: dict
    ) -> None:
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        owners = []
        for f in manifest_slice["authoritative_templates"]["files"]:
            owner = f["belongs_to_entry"]
            if owner is None:
                assert f.get("excluded_reason"), f"{f['name']}: null owner 必须给 excluded_reason"
                continue
            assert owner in ids, f"{f['name']}: owner {owner!r} 不在本 slice"
            owners.append(owner)
        assert len(owners) == len(set(owners)) == len(ids), "belongs_to_entry 不是单射"

    def test_runtime_index_membership_recomputes(self, manifest_slice: dict) -> None:
        indexed = _indexed_relpaths()
        for f in manifest_slice["authoritative_templates"]["files"]:
            assert f["in_runtime_index"] == (f"L/{f['name']}" in indexed), (
                f"{f['name']}: in_runtime_index 与 _index.json 不符"
            )

    def test_bundle_layer_drift_is_not_claimed(self, manifest_slice: dict) -> None:
        p = manifest_slice["property_denominators"]["property_28"]
        assert p["not_claimed_passing"] is True
        assert "bundle" in str(p["not_claimed_passing_part"])
        for e in manifest_slice["independent_entries"]:
            assert e["definition_bundle"] is None and e["published_representation"] is None


# ════════════════════════════════════════════════════════════════════════════
class TestProperty23StaticStructure:
    """动态行身份的缺陷侧穷举（Property 23 的可验部分）。"""

    @staticmethod
    def _inv(manifest_slice: dict) -> dict:
        return manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]

    def test_positional_identity_inventory_is_exhaustive_and_partitioned(
        self, manifest_slice: dict, l_files: list[pathlib.Path]
    ) -> None:
        hits = _positional_identity_hits(l_files)
        inv = self._inv(manifest_slice)
        assert len(hits) == inv["total_hits"], (
            f"位置化命中现算 {len(hits)} 条：{[h[0] for h in hits]}，声明 {inv['total_hits']}"
        )
        fams = {"a": [], "b": [], "c": []}
        for ref, _k, val in hits:
            fams[_family_of(val)].append(ref)
        assert sorted(fams["a"]) == sorted(inv["family_a_pure_ordinal"]["hits"])
        assert inv["family_a_pure_ordinal"]["count"] == len(fams["a"])
        assert inv["family_b_index_fallback"]["count"] == len(fams["b"]) == 0
        assert inv["family_c_entropy_seeded"]["count"] == len(fams["c"]) == 0
        assert (len(fams["a"]) + len(fams["b"]) + len(fams["c"])) == len(hits)

    def test_family_a_hit_is_a_real_line_of_source(self, manifest_slice: dict) -> None:
        inv = self._inv(manifest_slice)
        assert inv["family_a_pure_ordinal"]["hits"], "family_a 为空 ⇒ 非空跑证明失效"
        for sample in inv["family_a_pure_ordinal"]["samples"]:
            line = _line_at(sample["ref"])
            assert sample["key"] in line and sample["value"] in line, (
                f"{sample['ref']} 的现读内容 {line!r} 不含声明的 {sample['key']}: {sample['value']}"
            )

    def test_family_b_zero_is_a_judgement_not_an_absence(self, manifest_slice: dict) -> None:
        """三处反序列化兜底必须**真的**调生成器而不是退化成下标。"""
        for table in manifest_slice["dynamic_row_identity"]["tables"]:
            ident = table["row_identity"]
            assert ident["kind"] == "generated_opaque_string"
            p = _resolve_repo(ident["source_ref"])
            src = _strip_comments(_cached_text(p))
            gen = re.search(r"function (generateRowId|genRowId)\(\)[^\n]*\n\s*return `([^`]+)`", src)
            assert gen, f"{p.name}: 找不到生成器函数体"
            assert "Date.now()" in gen.group(2) and "Math.random()" in gen.group(2), (
                f"{p.name}: 生成器没有熵 ⇒ kind=generated_opaque_string 不成立"
            )
            fallbacks = re.findall(rf"{ident['identity_field']}:\s*raw\.\w+\s*\|\|\s*(\w+)\(\)", src)
            assert fallbacks and all(f == gen.group(1) for f in fallbacks), (
                f"{p.name}: 反序列化兜底不是调生成器（现算 {fallbacks}）⇒ family_b 的 0 不成立"
            )
            assert _line_no_of(ident["source_ref"]) == src[:gen.start()].count("\n") + 1, (
                f"{ident['source_ref']} 行号没落在生成器定义上"
            )

    def test_display_sequence_sites_are_not_flagged(
        self, manifest_slice: dict, l_files: list[pathlib.Path]
    ) -> None:
        sites = _display_seq_sites(l_files)
        inv = self._inv(manifest_slice)
        assert sorted(sites) == sorted(inv["family_d_display_sequence"]["hits"])
        assert inv["family_d_display_sequence"]["count"] == len(sites)
        assert inv["family_d_display_sequence"]["is_defect"] is False
        hit_refs = {h[0] for h in _positional_identity_hits(l_files)}
        assert not (set(sites) & hit_refs), (
            f"展示序号站点被算进了缺陷集：{sorted(set(sites) & hit_refs)}"
        )
        assert sites, "展示序号站点为空 ⇒ 该反向判据空跑"

    def test_hardcoded_scan_is_all_zero_and_non_vacuous(
        self, manifest_slice: dict, l_files: list[pathlib.Path]
    ) -> None:
        inv = self._inv(manifest_slice)
        scan = inv["hardcoded_pattern_scan"]
        for name in _HARDCODED_PATTERNS:
            got = _hardcoded_hits(l_files, name)
            assert len(got) == scan["patterns"][name], f"{name} 现算 {got}"
            assert got == scan["hits"][name]
        assert sum(scan["patterns"].values()) == 0, "六个模式不再全 0 ⇒ 声明要改"
        assert len(_positional_identity_hits(l_files)) > 0, (
            "🔴 非空跑证明：同一分母上位置化扫描必须有非零命中，否则「六个 0」与「扫描器坏了」不可区分"
        )
        assert manifest_slice["honest_adjudication_summary"][
            "hardcoded_patterns_at_zero"] == len(_HARDCODED_PATTERNS)

    def test_declared_dynamic_tables_avoid_forbidden_identity_kinds(
        self, manifest_slice: dict
    ) -> None:
        section = manifest_slice["dynamic_row_identity"]
        forbidden = set(section["forbidden_identity_kinds"])
        for t in section["tables"]:
            assert t["row_identity"]["kind"] not in forbidden
            assert t["table_key"] and t["persistence_key"]
        assert len(section["tables"]) == manifest_slice["honest_adjudication_summary"][
            "dynamic_row_identity_tables"]

    def test_the_two_containers_partition_all_hits(
        self, manifest_slice: dict, l_files: list[pathlib.Path]
    ) -> None:
        hits = {h[0] for h in _positional_identity_hits(l_files)}
        declared = set(self._inv(manifest_slice)["family_a_pure_ordinal"]["hits"])
        table_refs = {t["row_identity"]["source_ref"]
                      for t in manifest_slice["dynamic_row_identity"]["tables"]}
        assert declared == hits, "family_a 未覆盖全部命中"
        assert not (declared & table_refs), "两个容器交集非空"


# ════════════════════════════════════════════════════════════════════════════
class TestProperty69EvidenceAndCounters:
    """evidence 的负向闭合 + summary 全部计数现算。"""

    def test_unverifiable_entries_carry_non_empty_reasons(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            ev = e["evidence"]
            assert ev["verification_state"] == "UNVERIFIABLE"
            assert isinstance(ev["unverifiable_reasons"], list) and ev["unverifiable_reasons"], (
                f"{e['entry_id']}: SR-7 要求非空 unverifiable_reasons"
            )
            assert ev["sync_test_run_id"] is None
            assert ev["required_scenario_set_digest"] is None
            assert ev["browser_case"] is None

    def test_bp4_appears_only_in_the_inert_entries_reasons(self, manifest_slice: dict) -> None:
        """🔴 4 条 reasons 抄成 8 条同形也能过 SR-7 —— 故必须两侧都验。"""
        for e in manifest_slice["independent_entries"]:
            code = _wp_code_of(e)
            blob = " ".join(e["evidence"]["unverifiable_reasons"])
            if code in INERT_CODES:
                assert "BP-4" in blob, f"{code}: inert entry 的 reasons 没有 BP-4"
            else:
                assert "BP-4" not in blob, f"{code}: 非 inert entry 的 reasons 里出现了 BP-4"

    def test_contract_test_points_at_this_guard(self, manifest_slice: dict) -> None:
        me = _THIS.relative_to(ROOT).as_posix()
        for e in manifest_slice["independent_entries"]:
            assert e["evidence"]["contract_test"] == me, (
                f"{e['entry_id']}: contract_test 应指向本守卫，实为 {e['evidence']['contract_test']}"
            )

    def test_summary_counters_recompute_from_the_entries(self, manifest_slice: dict) -> None:
        entries = manifest_slice["independent_entries"]
        s = manifest_slice["honest_adjudication_summary"]
        assert s["total_independent"] == len(entries)
        for cap in CAPABILITY_ENUM:
            assert s[f"adjudicated_as_{cap}"] == sum(
                1 for e in entries if e["capability"] == cap)
        assert s["capability_verdict_pending"] == sum(1 for e in entries if e["capability"] is None)
        assert s["html_counterpart_exists"] == sum(
            1 for e in entries if e["html_counterpart_verdict"] == "exists")
        assert s["html_counterpart_none"] == sum(
            1 for e in entries if e["html_counterpart_verdict"] == "none")
        assert s["html_counterpart_exists"] + s["html_counterpart_none"] == len(entries)
        assert s["entries_left_unverifiable"] == sum(
            1 for e in entries if e["evidence"]["verification_state"] == "UNVERIFIABLE")
        assert s["finalized_published_representations"] == sum(
            1 for e in entries if e["published_representation"] is not None)
        assert s["hosts_with_oo_mount"] == sum(1 for e in entries if e["mount_count"] > 0)
        assert s["reachable_hosts_in_cycle"] == len(entries)

    def test_derived_counters_recompute_from_their_own_sections(
        self, manifest_slice: dict
    ) -> None:
        s = manifest_slice["honest_adjudication_summary"]
        files = manifest_slice["authoritative_templates"]["files"]
        assert s["authoritative_template_files"] == len(files)
        assert s["template_files_with_owner_entry"] == sum(
            1 for f in files if f["belongs_to_entry"])
        assert s["template_files_without_owner_entry"] == sum(
            1 for f in files if not f["belongs_to_entry"])
        assert s["authoritative_template_sheets_total"] == sum(f["sheet_count"] for f in files)
        assert s["authoritative_template_sheets_owned"] == sum(
            f["sheet_count"] for f in files if f["belongs_to_entry"])
        audit = manifest_slice["sheet_granularity_and_router_audit"]["counters"]
        for k in ("sheets_covered_by_html_children", "sheets_falling_through_to_oo",
                  "router_ambiguous_codes_total"):
            assert s[k] == audit[k], f"summary.{k} 与审计节不一致"
        assert s["router_ambiguous_and_reachable_total"] == len(
            audit["router_ambiguous_and_reachable"])
        inv = manifest_slice["orphan_dual_mode_inventory"]["counters"]
        for a, b in (("orphan_dual_mode_modules", "orphan_modules"),
                     ("live_dual_mode_modules", "live_modules"),
                     ("dual_mode_module_files_total", "dual_mode_module_files_total"),
                     ("dual_mode_modules_not_scoped_to_wp_id", "modules_not_scoped_to_wp_id")):
            assert s[a] == inv[b], f"summary.{a} != orphan_inventory.{b}"
        assert s["blocking_preconditions_total"] == len(manifest_slice["blocking_preconditions"])
        assert s["l_production_files_scanned"] == len(_l_cycle_files())
        assert s["per_entry_persistence_modules"] == len(manifest_slice["independent_entries"])
        # 位置化身份 / 硬编码扫描的摘要计数必须从 positional_identity_inventory 现算。
        # 🔴 首轮漏了这一段，M28/M29 变异判 GREEN（守卫缺陷）后补上。
        inv = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        fam = {
            "a": inv["family_a_pure_ordinal"], "b": inv["family_b_index_fallback"],
            "c": inv["family_c_entropy_seeded"], "d": inv["family_d_display_sequence"],
        }
        for k, node in fam.items():
            assert s[f"positional_identity_family_{k}"] == node["count"] == len(node["hits"]), (
                f"summary.positional_identity_family_{k} 与 inventory 不一致"
            )
        assert s["positional_identity_hits_total"] == inv["total_hits"] == (
            fam["a"]["count"] + fam["b"]["count"] + fam["c"]["count"]
        ), "total_hits 必须等于 a+b+c（family_d 不计入）"
        assert s["positional_identity_defect_hits"] == fam["a"]["count"] + fam["b"]["count"]
        scan = inv["hardcoded_pattern_scan"]
        assert s["hardcoded_pattern_hits_total"] == sum(scan["patterns"].values())
        assert s["hardcoded_patterns_at_zero"] == sum(
            1 for v in scan["patterns"].values() if v == 0)
        assert (s["entries_with_positional_identity_defects"]
                + s["entries_without_positional_identity_defects"]) == len(
            manifest_slice["independent_entries"])

    def test_slice_counters_are_all_zero_except_unadjudicated(self, manifest_slice: dict) -> None:
        c = manifest_slice["honest_adjudication_summary"]["slice_counters"]
        assert c["unadjudicated"] == len(manifest_slice["independent_entries"])
        assert c["fake_bidirectional_claimed_verified"] == 0
        assert c["bidirectional_unverified"] == 0
        assert c["stale_evidence"] == 0
        assert "不得解读为" in str(c["note"])

    def test_counting_notes_cover_every_nontrivial_counter(self, manifest_slice: dict) -> None:
        s = manifest_slice["honest_adjudication_summary"]
        notes = s["counting_notes"]
        must = {
            "total_independent", "capability_verdict_pending", "html_counterpart_exists",
            "authoritative_template_files", "dual_mode_module_files_total",
            "dual_mode_modules_calling_legacy_config_endpoint",
            "hosts_calling_legacy_health_endpoint_directly",
            "hosts_importing_shared_checklist_persistence",
            "hosts_importing_own_formdata_module", "entries_with_redeemable_switch",
            "positional_identity_hits_total", "hardcoded_pattern_hits_total",
            "router_ambiguous_codes_total", "blocking_preconditions_total",
        }
        assert must <= set(notes), f"缺 counting_notes：{sorted(must - set(notes))}"
        for k in must:
            assert notes[k] and len(str(notes[k])) > 10
        for k in set(notes) - {"sheets_covered_by_html_children", "entries_mounting_the_ac14_notice",
                               "authoritative_template_sheets_total"}:
            assert k in s, f"counting_notes 里有不存在的计数键 `{k}`"


# ════════════════════════════════════════════════════════════════════════════
class TestProperty70CrossEntryIsolation:
    """九份 slice 两两不相交 + 契约归属 + 模板单射 + 持久化命名空间互异 + 删除路径不相交。"""

    def test_nine_slices_are_pairwise_disjoint(self, manifest_slice: dict) -> None:
        sets: dict[str, set[str]] = {"L": {e["entry_id"] for e in manifest_slice["independent_entries"]}}
        for name, path in SIBLING_SLICE_PATHS.items():
            sets[name] = {e["entry_id"] for e in _load(path)["independent_entries"]}
        names = sorted(sets)
        pairs = 0
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                inter = sets[a] & sets[b]
                assert not inter, f"{a} 与 {b} 的 entry 集合相交：{sorted(inter)}"
                pairs += 1
        assert pairs == len(names) * (len(names) - 1) // 2 == 36, f"配对数现算 {pairs}"

    def test_sibling_slices_declared_match_the_disk(self, manifest_slice: dict) -> None:
        declared = sorted(manifest_slice["sibling_slices"])
        onDisk = sorted(p.relative_to(ROOT).as_posix() for p in SIBLING_SLICE_PATHS.values())
        assert declared == onDisk, f"sibling_slices 声明 {declared}，磁盘 {onDisk}"

    def test_cross_entry_isolation_assertions_are_present(self, manifest_slice: dict) -> None:
        iso = manifest_slice["cross_entry_isolation"]
        assert iso["rule"] and isinstance(iso["assertions"], list) and len(iso["assertions"]) >= 8
        assert sorted(iso["production_contract_files"]) == sorted(
            f.name for f in CONTRACT_DIR.glob("*.json")
            if (_load(f).get("review") or {}).get("entry_id")
        )

    def test_persistence_namespaces_are_pairwise_distinct(self, manifest_slice: dict) -> None:
        keys = [e["html_counterpart"]["table_keys"][0]
                for e in manifest_slice["independent_entries"]]
        assert len(set(keys)) == len(keys) == len(L_CODES), f"命名空间重复：{keys}"

    def test_deletion_plan_paths_are_globally_unique_and_disjoint(
        self, deletion_plan: dict
    ) -> None:
        mine: set[str] = set()
        for m in deletion_plan["orphan_dual_mode_to_delete"]["modules"]:
            mine.add(m["file"])
        for m in deletion_plan["live_dual_mode_to_rewire_then_delete"]["modules"]:
            mine.add(m["file"])
        assert len(mine) == 9
        for name, path in SIBLING_SLICE_PATHS.items():
            plan_path = path.parent / path.name.replace("manifest_slice", "deletion_plan")
            if not plan_path.exists():
                continue
            other = json.dumps(_load(plan_path), ensure_ascii=False)
            for f in mine:
                assert f not in other, f"{name} 循环的删除清册里出现了本 slice 的删除路径 {f}"


# ════════════════════════════════════════════════════════════════════════════
class TestDeletionPlanConsistency:
    """删除清册与 slice 必须同一真源；四类删除对象必须划分完整。"""

    def test_plan_entries_mirror_the_slice_adjudication(
        self, deletion_plan: dict, manifest_slice: dict
    ) -> None:
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        assert len(deletion_plan["entries"]) == len(by_id)
        for pe in deletion_plan["entries"]:
            se = by_id[pe["entry_id"]]
            assert pe["capability_adjudication"] == se["capability"]
            assert pe["capability_verdict_stage"] == se["capability_verdict_stage"]
            assert pe["capability_target"] == se["capability_target"]
            assert pe["html_counterpart_verdict"] == se["html_counterpart_verdict"]
            assert pe["adjudication_reason"] == se["adjudication"]["reason"]
            assert pe["html_counterpart_source_refs"] == se["html_counterpart_source_refs"]
            assert pe["must_fix_before_wiring"] == se["capability_target_blocked_by"]
            assert pe["host_component"] == se["host_path"]
            assert pe["dual_mode_carrier_kind"] == se["dual_mode_carrier"]["kind"]
            assert pe["switch_is_redeemable"] == se["dual_mode_carrier"]["switch_is_redeemable"]

    def test_plan_reason_is_not_circular(self, deletion_plan: dict, paradigm: dict) -> None:
        ap1 = next(a for a in paradigm["adjudication_criteria"]["anti_patterns"]
                   if a["id"] == "AP-1")
        markers = [str(m) for m in ap1["circular_reason_markers"]]
        for pe in deletion_plan["entries"]:
            if pe["capability_adjudication"] and str(pe["capability_adjudication"]).startswith("single"):
                assert not any(m in str(pe["adjudication_reason"]) for m in markers)

    def test_plan_four_deletion_classes_partition_the_nine_files(
        self, deletion_plan: dict
    ) -> None:
        files = {p.relative_to(ROOT).as_posix() for p in _dual_mode_module_files()}
        orphan = {m["file"] for m in deletion_plan["orphan_dual_mode_to_delete"]["modules"]}
        live = {m["file"] for m in deletion_plan["live_dual_mode_to_rewire_then_delete"]["modules"]}
        assert orphan | live == files and not (orphan & live)
        assert len(orphan) == 5 and len(live) == 4
        blocks = deletion_plan["inert_switch_blocks_to_remove"]["blocks"]
        assert len(blocks) == len(INERT_CODES)
        assert {b["carrier_module_to_delete_with_it"] for b in blocks} == live, (
            "inert 开关块声明的 carrier 与 live 集合不等 ⇒ 「删开关必删 composable」这条不闭合"
        )
        shrink = deletion_plan["shared_cycle_carrier_partially_shrinking"]
        assert shrink["file"] not in files, "共享载体不该出现在 useL*DualMode 文件集里"

    def test_plan_orphans_can_be_deleted_before_step_9(self, deletion_plan: dict) -> None:
        node = deletion_plan["orphan_dual_mode_to_delete"]
        assert node["can_delete_before_step_9"] is True
        assert node["ac_reference"] == "1.7"
        for m in node["modules"]:
            assert m["action"] == "delete" and m["blocking_risk"] == "none"
            assert m["production_consumers"] == 0 and m["test_only_consumers"] == 0

    def test_plan_inert_blocks_can_be_deleted_before_step_9_unlike_k(
        self, deletion_plan: dict
    ) -> None:
        """🔴 与 K 相反：L5~L8 的 composable 可以先删（开关本就无效）。"""
        live_node = deletion_plan["live_dual_mode_to_rewire_then_delete"]
        assert live_node["can_delete_before_step_9"] is True
        for m in live_node["modules"]:
            assert m["switch_is_redeemable"] is False
            assert m["action"] == "delete_with_the_inert_switch"
        inert = deletion_plan["inert_switch_blocks_to_remove"]
        assert inert["can_delete_before_step_9"] is True
        assert inert["ac_reference"] == "1.4"
        assert "GtEntrySyncCapabilityNotice" in str(inert["must_also"]), (
            "收掉开关必须同时挂 AC 1.4 提示，否则从「骗人」退化成「沉默」"
        )

    def test_plan_inert_blocks_are_real(self, deletion_plan: dict) -> None:
        for b in deletion_plan["inert_switch_blocks_to_remove"]["blocks"]:
            for ref in (b["template_block"], b["script_block"]):
                assert _resolve_repo(ref).exists() and _line_at(ref).strip()
            assert "el-segmented" in _line_at(b["template_block"])
            assert f"use{b['wp_code']}DualMode" in _line_at(b["script_block"])
            assert b["mode_gated_v_if_count"] == 0
            assert b["onlyoffice_component_count_in_file"] == 0

    def test_plan_has_no_host_inlined_class(self, deletion_plan: dict) -> None:
        assert "host_inlined_second_implementation" not in deletion_plan, (
            "L 循环无宿主内联实现 ⇒ 不得抄 H/K 那一节（空容器 = additive 死声明）"
        )
        assert deletion_plan["counters"]["hosts_with_inlined_second_implementation"] == 0
        assert deletion_plan["counters"]["host_inlined_blocks_to_remove"] == 0
        for pe in deletion_plan["entries"]:
            assert pe["host_inlined_block_to_remove"] is None

    def test_plan_shared_numbers_agree_with_the_slice(
        self, deletion_plan: dict, manifest_slice: dict
    ) -> None:
        sb_plan = deletion_plan["shared_base_preserved"]
        sb_slice = manifest_slice["orphan_dual_mode_inventory"]["shared_base_preserved"]
        assert sb_plan["statement_position_consumers"] == sb_slice["statement_position_consumers"]
        assert sb_plan["l_cycle_consumers"] == 0
        assert sb_plan["remaining_after_this_plan"] == sb_plan["statement_position_consumers"]
        sc_plan = deletion_plan["shared_cycle_carrier_partially_shrinking"]
        sc_slice = manifest_slice["orphan_dual_mode_inventory"]["shared_cycle_carrier"]
        assert sc_plan["statement_position_consumers_before"] == sc_slice[
            "statement_position_production"]
        assert sc_plan["statement_position_consumers_after"] == sc_slice[
            "remaining_after_this_plan"] == 1

    def test_plan_must_not_wire_to_targets_are_the_orphan_twins(
        self, deletion_plan: dict
    ) -> None:
        orphan = {m["file"] for m in deletion_plan["orphan_dual_mode_to_delete"]["modules"]}
        union: set[str] = set()
        with_targets = 0
        for pe in deletion_plan["entries"]:
            if pe["must_not_wire_to"]:
                with_targets += 1
                assert set(pe["must_not_wire_to"]) <= orphan, (
                    f"{pe['entry_id']}: must_not_wire_to 指向非 orphan"
                )
                union |= set(pe["must_not_wire_to"])
        assert union == orphan, f"orphan 未被 must_not_wire_to 全覆盖：漏 {sorted(orphan - union)}"
        assert with_targets == deletion_plan["counters"]["entries_with_must_not_wire_to"]

    def test_plan_counters_recompute(self, deletion_plan: dict) -> None:
        c = deletion_plan["counters"]
        assert c["entries"] == len(deletion_plan["entries"])
        assert c["composables_to_delete_entry_scoped"] == sum(
            len(x["legacy_composables_to_delete"]) for x in deletion_plan["entries"])
        assert c["orphan_dual_mode_to_delete"] == len(
            deletion_plan["orphan_dual_mode_to_delete"]["modules"])
        assert c["live_dual_mode_to_delete"] == len(
            deletion_plan["live_dual_mode_to_rewire_then_delete"]["modules"])
        assert (c["orphan_dual_mode_to_delete"] + c["live_dual_mode_to_delete"]
                == c["dual_mode_module_files_total"] == len(_dual_mode_module_files()))
        assert c["dual_mode_module_files_total"] != c["entries"], (
            "🔴 9 ≠ 8 是 L 循环的形态特征；相等则 K 那条判据才可照抄"
        )
        assert c["inert_switch_blocks_to_remove"] == len(
            deletion_plan["inert_switch_blocks_to_remove"]["blocks"])
        assert (c["entries_with_redeemable_switch"] + c["entries_with_inert_switch"]
                + c["entries_with_no_switch_at_all"]) == c["entries"]
        assert c["orphan_dual_mode_lines_total"] == sum(
            m["lines"] for m in deletion_plan["orphan_dual_mode_to_delete"]["modules"])
        assert c["localStorage_prefix_declaration_sites"] == len(_dual_mode_module_files()) + 2
        assert c["entries_without_any_ui_gate_anchor"] == len(L_CODES) - len(REDEEMABLE_CODES)
        assert c["shared_cycle_carrier_consumers_after"] == (
            c["shared_cycle_carrier_consumers_before"] - 2)

    def test_plan_has_no_pilot_branch(self, deletion_plan: dict) -> None:
        assert deletion_plan["pilot_already_migrated"] is None
        assert "没有" in str(deletion_plan["pilot_already_migrated_note"])

    def test_plan_excludes_the_bond_branch_selector_explicitly(self, deletion_plan: dict) -> None:
        items = deletion_plan["excluded_from_plan"]
        assert any("bondBranch" in item["what"] for item in items), (
            "L4 的 bondBranch 选择器必须显式排除，否则删除时会误删业务功能"
        )
        for item in items:
            assert item["reason"] and item["verified_how"]

    def test_plan_localstorage_prefix_sites_recompute(self, deletion_plan: dict) -> None:
        sites = 0
        for p in _dual_mode_module_files():
            src = _strip_comments(_cached_text(p))
            assert re.search(r"^const STORAGE_KEY\w*\s*=\s*'", src, re.M), f"{p.name} 无前缀常量"
            sites += 1
        for code in REDEEMABLE_CODES:
            src = _strip_comments(_cached_text(_host_of(code)))
            m = re.search(r"storagePrefix:\s*'([^']+)'", src)
            assert m, f"{code}: 宿主里找不到 storagePrefix"
            assert m.group(1) == f"{code.lower()}-proc:"
            sites += 1
        assert sites == deletion_plan["counters"]["localStorage_prefix_declaration_sites"]

    def test_plan_verification_recipe_mentions_five_checks(self, deletion_plan: dict) -> None:
        node = deletion_plan["why_this_plan_has_four_deletion_object_classes"]
        recipe = str(node["verification_recipe"])
        assert recipe.count("①") == 1 and "⑤" in recipe, "五项核验必须逐项写明"
        assert "bondBranch" in recipe
        assert "0" in str(node["why_no_host_inlined_class_unlike_k_and_h"])


# ════════════════════════════════════════════════════════════════════════════
def _validator_module() -> ModuleType:
    return _load_module("_task54_paradigm_contract_host", CONTRACT_GUARD)


class TestParadigmCompliance:
    """本 slice 必须过范式点名的那**一个**校验器，且反例两侧都验。"""

    def test_the_slice_passes_the_paradigm_nominated_validator(self, manifest_slice: dict) -> None:
        mod = _validator_module()
        problems = mod.validate_slice_against_schema(manifest_slice)
        assert problems == [], f"范式校验器报了 {len(problems)} 条违规：{problems}"

    def test_the_validator_really_catches_a_missing_pending_field(
        self, manifest_slice: dict
    ) -> None:
        mod = _validator_module()
        bad = json.loads(json.dumps(manifest_slice))
        bad["independent_entries"][0].pop("capability_target_blocked_by")
        problems = mod.validate_slice_against_schema(bad)
        assert any("capability_target_blocked_by" in p for p in problems), (
            f"抽掉待裁决字段后校验器没打红：{problems}"
        )

    def test_the_validator_really_catches_a_counter_mismatch(self, manifest_slice: dict) -> None:
        mod = _validator_module()
        bad = json.loads(json.dumps(manifest_slice))
        bad["honest_adjudication_summary"]["slice_counters"]["unadjudicated"] = 0
        problems = mod.validate_slice_against_schema(bad)
        assert any("SR-9" in p for p in problems), f"篡改待裁决计数后没打红：{problems}"

    def test_the_validator_really_catches_a_forbidden_identity_kind(
        self, manifest_slice: dict
    ) -> None:
        mod = _validator_module()
        bad = json.loads(json.dumps(manifest_slice))
        bad["dynamic_row_identity"]["tables"][0]["row_identity"]["kind"] = "array_index"
        problems = mod.validate_slice_against_schema(bad)
        assert any("forbidden_identity_kinds" in p for p in problems), (
            f"把行身份写成 array_index 后没打红：{problems}"
        )

    def test_the_validator_really_catches_a_single_with_identity(
        self, manifest_slice: dict
    ) -> None:
        mod = _validator_module()
        bad = json.loads(json.dumps(manifest_slice))
        e = bad["independent_entries"][0]
        e["capability"] = "single_onlyoffice"
        e["adjudication"]["honest_capability"] = "single_onlyoffice"
        e["adapter_id"] = "l1-fake"
        problems = mod.validate_slice_against_schema(bad)
        assert any("SR-5" in p for p in problems), f"single_* 挂 adapter 后没打红：{problems}"

    def test_paradigm_refs_and_task_number_are_right(self, manifest_slice: dict) -> None:
        assert manifest_slice["task"] == "Task 54"
        assert manifest_slice["schema_version"] == "manifest-slice:v1"
        assert manifest_slice["paradigm_ref"] == PARADIGM_PATH.relative_to(ROOT).as_posix()
        assert manifest_slice["source_manifest"] == FULL_MANIFEST_PATH.relative_to(ROOT).as_posix()
        mod = _validator_module()
        assert mod._task_number(manifest_slice) == 54

    def test_task48_extra_entry_fields_are_present(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        extra = paradigm["slice_schema"]["effective_from_task_48"]["required_entry"]
        for e in manifest_slice["independent_entries"]:
            for k in extra:
                assert k in e, f"{e['entry_id']}: 缺 Task 48 起必填的 `{k}`"

    def test_paradigm_bytes_are_untouched_by_this_task(self, paradigm: dict) -> None:
        """范式 JSON 是只读件 —— 本任务不得改它一个字节。"""
        assert paradigm["frozen_by"] == "Task 45"
        assert 54 in paradigm["definition_producer_paradigm"]["applies_to_tasks"]
        assert 54 in paradigm["slice_schema"]["applies_to_tasks"]
        mod = _validator_module()
        # 🔴 不用 hasattr 兜底：常量缺失就该打红（缺了说明范式守卫被动过），
        # 兜底成 True 就是 fail-open。
        assert mod.raw_block_digest() == mod.FROZEN_PARADIGM_RAW_SHA256, (
            "范式 JSON 的冻结块字节变了 —— 本任务对该文件只读"
        )
        assert mod.canonical_digest(paradigm["paradigm"]) == mod.FROZEN_PARADIGM_CANONICAL_SHA256

    def test_new_sections_are_declared_as_non_conflicting(self, manifest_slice: dict) -> None:
        conflict = manifest_slice["paradigm_schema_conflict"]
        assert conflict["residual_inconsistency"] is None
        declared = set(conflict["new_section_not_in_schema"]["sections"])
        required = set(_load(PARADIGM_PATH)["slice_schema"]["required_top_level"])
        conditional = {
            cs["section"] for cs in _load(PARADIGM_PATH)["slice_schema"]["conditional_sections"]
        }
        actual_extra = set(manifest_slice) - required - conditional
        assert declared == actual_extra, (
            f"额外节声明与实际不符：漏声明 {sorted(actual_extra - declared)}，"
            f"多声明 {sorted(declared - actual_extra)}"
        )
        for key in ("why_inert_switch_section_is_new", "why_sheet_granularity_section_is_new",
                    "why_no_transport_key_resolution_section",
                    "why_no_parent_duplicate_summary_section",
                    "why_no_currency_variant_model_section", "why_no_account_scope_section"):
            assert conflict["new_section_not_in_schema"].get(key), f"缺 `{key}` 的说明"

    def test_unjudged_slices_registry_stays_empty(self) -> None:
        mod = _load_module("_task54_coverage_host", COVERAGE_GUARD)
        assert mod._UNJUDGED_SLICES == {}, (
            f"_UNJUDGED_SLICES 非空：{mod._UNJUDGED_SLICES} —— 本 slice 不得靠豁免表通过"
        )
        rels = {p.relative_to(ROOT).as_posix() for p in mod._contract.slice_paths()}
        assert MANIFEST_SLICE_PATH.relative_to(ROOT).as_posix() in rels, (
            "本 slice 未被 scan_glob 收进覆盖面分母 ⇒ 校验器覆盖面判据对它空跑"
        )

    def test_requirements_and_properties_are_declared(self, manifest_slice: dict) -> None:
        props = " ".join(manifest_slice["properties_verified"])
        for n in ("20", "28", "69", "70"):
            assert f"Property {n}" in props, f"未声明 Property {n}"
        reqs = set(manifest_slice["requirements_covered"])
        for r in ("6.1", "6.2", "6.10", "12.1", "12.4", "12.10", "12.11", "12.12", "14.1"):
            assert r in reqs, f"requirements_covered 缺 {r}"

    def test_deletion_plan_declares_the_same_properties(self, deletion_plan: dict) -> None:
        props = " ".join(deletion_plan["properties_verified"])
        for n in ("20", "28", "69", "70"):
            assert f"Property {n}" in props
        assert deletion_plan["task"] == "Task 54"
        assert deletion_plan["adjudication_source_of_truth"].startswith(
            MANIFEST_SLICE_PATH.relative_to(ROOT).as_posix())
        assert deletion_plan["inert_switch_source_of_truth"].endswith(
            "#inert_mode_switch_resolution")
