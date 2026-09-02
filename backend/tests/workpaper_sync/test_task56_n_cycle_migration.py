# -*- coding: utf-8 -*-
r"""Task 56 守卫 —— N 循环（税项循环）Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 56
点名 Property：**3 / 23 / 69 / 70**；点名 AC：1.4 · 6.5 · 12.1 · 12.4 · **12.8** ·
12.10 · 12.11 · 12.12 · 14.1。

═══ 本轮与前十轮的判据差异（照抄 M/L 会假红的点）═══

tasks.md 正文点名三件事：**真实传输键**、**动态 identity**、**纯 OO entry**。第三件的实证
结论是 **N 循环没有纯 OO entry** —— 5 条 entry 逐一现读 owner 常量（`ITEM_PREFIX`）、读写站点
与后端路由三边，全部 `html_counterpart_verdict == "exists"` ⇒ AC 12.8 明文禁止
`single_onlyoffice`。「无对端不伪造映射」在本轮是**反向落法**：既不为凑数字硬裁 single，
也不为凑双向给这 5 条造字段映射（契约目录里现算 0 条属本 slice）。

八处形态差异（slice 的 `n_cycle_form_differences` 逐条冻结，本文件逐条现算）：

* **ND-1** `parent_duplicate_summary` 条件节**触发**（4 条子入口，全挂 N1）—— K/L/M 三轮
  各 0 条并各写了「未触发条件节必须缺席」的判据，照抄必假红。
* **ND-2** 三种 dual-mode 载体并存（per-entry composable / 薄封装共享基类 / 宿主内联）——
  M 十条全是一种形态；N 域**没有任何** `*EntryDualMode.ts`。
* **ND-3** 2 条 inert 开关是**宿主内联的空实现**（`onModeChange: () => {}`）—— L 的 inert 是
  「载体模块不可达」，按「载体是否 orphan」判会把 N4/N5 判成 redeemable。
* **ND-4** 宿主直调 legacy health 端点 **1 处**（N3 #L180）—— M/L 两轮都是 0。
* **ND-5** orphan 不止 dual-mode：8 个零生产边模块 / 1,325 行，含 V1/V2 业务孪生。
* **ND-6** sheet 名含**尾随空格**（`税金及附加审计程序表N4A `）与**缺右括号**
  （`附注披露信息（国企`）—— M 那轮是**前导**空格，strip 与全等两种写法各会毁掉一条判据。
* **ND-7** 跨册 sheet 码碰撞（`N3A` 一码两册；`O1A`/`O2A` 出现在 N 册）。
* **ND-8** 位置化持久化键只有 3 处且形态是 `${ITEM_PREFIX}-${index}`（**无 `row-` 中缀**）——
  M 的扫描器在 N 上现算 0 命中，会把 N 判成「无缺陷」。本文件对此有**反向断言**。

═══ 判据强度约定（沿用前十轮，逐条不放宽）═══

1. 裁决判据 = **AC 12.8 原文「无 HTML 对端」**，不是「adapter/contract/bundle 不存在」（AP-1）。
2. 四个 capability 枚举值都不成立 ⇒ 待裁决态（`capability: null` + 三字段齐备）。禁扩枚举。
3. `manifest_mirror` 判据 = 断言「**必须不一致**且已登记 BP」，不是断言相等。
4. 消费边 = **statement-position import 路径字面量**（`from '…'` 可独占一行），且排除
   **双引号字符串内**的匹配（`workpaperSyncLegacyBaseline.generated.ts` 的 JSON `"snippet"`
   含完整 `from '...'` 形态）。
5. orphan 判定用**可达性**而非入度；路径解析口径，禁 stem 相等。
6. 剥注释**保留行号**（同长空白替换，禁删行式）。
7. **source_ref 三边锁**：声明 → openpyxl 真读源 xlsx → impl 常量现读。**sheet 名不得 strip**。
8. AC 1.5 仅在裁出 `single_*` 时适用；本轮无 single ⇒ 生效 AC 1.4。
9. 「纯客户端」/「开关坏了」/「开关没有」都**不是**裁 `single_html` 的理由。
10. 分母为空的 Property **明确不宣称通过**（只断言前提 + 承载者存在）。
11. 存量欠账用 `pytest.mark.xfail(strict=True)`，禁 `pytest.skip`。
12. 计数一律**从来源节现算等值**；「某族 0 命中」也落成判据。
13. 任何 `declared_list` 与 `computed_list` 做**有序等值 + 无重复**双断言（Task 55 的 M23 教训）。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器）::

    .\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_task56_n_cycle_migration.py -q
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
from types import ModuleType
from typing import Any

import openpyxl
import pytest

# ════════════════════════════════════════════════════════════════════════════
# 路径与常量
# ════════════════════════════════════════════════════════════════════════════
_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
SVC = BACKEND / "app" / "services" / "workpaper_sync"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"

SLICE_PATH = DATA / "workpaper_sync_n_cycle_manifest_slice.json"
PLAN_PATH = DATA / "workpaper_sync_n_cycle_deletion_plan.json"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
FULL_MANIFEST = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY = DATA / "workpaper_sync_entry_overlay.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
CONTRACT_GUARD = _THIS.with_name("test_migration_paradigm_contract.py")
COVERAGE_GUARD = _THIS.with_name("test_slice_schema_validator_coverage.py")

TEMPLATE_DIR = BACKEND / "wp_templates"
TEMPLATE_INDEX = TEMPLATE_DIR / "_index.json"
N_TEMPLATE_DIR = TEMPLATE_DIR / "N"
REFERENCE_COPY_DIR = ROOT / "基础数据" / "致同通用审计程序及底稿模板（2025年修订）"

CHECKLIST_ROUTER = BACKEND / "app" / "routers" / "checklist_responses.py"
REGISTRY = SVC / "adapters" / "registry.py"
HTML_RENDERER_REGISTRY = WP_COMPONENTS / "htmlRendererRegistry.ts"
SHARED_BASE = WP_COMPOSABLES / "useWorkpaperEntryDualMode.ts"
SHARED_ROUTER = WP_COMPOSABLES / "shared" / "cycleSheetRouting.ts"
AC14_NOTICE_TS = WP_COMPONENTS / "sync" / "workpaperEntrySyncNotice.ts"
AC14_NOTICE_VUE = WP_COMPONENTS / "sync" / "GtEntrySyncCapabilityNotice.vue"

N_CODES = ("N1", "N2", "N3", "N4", "N5")
HTML_COUNTERPART_VERDICTS = ("none", "exists")

#: 四条 pilot 契约的 `review.entry_id` 实测值 —— 🔴 按 entry_id 判归属，不按文件名猜。
PILOT_CONTRACT_OWNERS = {
    "xlsx/b60/gt-b60-bundle",
    "xlsx/gt-d2-accounts-receivable",
    "xlsx/gt-g7-long-term-equity-main",
    "xlsx/gt-h1-fixed-assets",
}
#: 第 5 个契约文件是 candidate：`review_status == "candidate"` 且 `review.entry_id` 为 **null**。
#: 它是「candidate 不得注册生产 adapter」的反例分母 —— **不得**要求其 entry_id 非空。
CANDIDATE_CONTRACT_FILE = "_example.candidate.json"


# ════════════════════════════════════════════════════════════════════════════
# 基础工具
# ════════════════════════════════════════════════════════════════════════════
def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*|<!--.*?-->", re.S)


def _blank_keep_newlines(match: "re.Match[str]") -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def _strip_comments(source: str) -> str:
    """剥注释但**保留行号**（同长空白替换，禁删行式）。"""
    return _COMMENT_RE.sub(_blank_keep_newlines, source)


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


def _inside_double_quoted_string(line: str, pos: int) -> bool:
    """`pos` 是否落在**双引号字符串**内。

    🔴 `workpaperSyncLegacyBaseline.generated.ts` 的 JSON `"snippet"` 字段里含完整的
    ``from '...'`` 形态；不排除它，共享基类的边数结论会被污染。
    """
    depth = 0
    i = 0
    while i < pos and i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == '"':
            depth ^= 1
        i += 1
    return bool(depth)


#: 🔴 `from '…'` **可以独占一行**（多行 import 的收尾行）。只匹配「同一行里 import…from」
#: 会把 `import {\n  A,\n} from './x'` 整类漏掉 —— 本轮实测因此把 `n2SheetRouting.ts`
#: 误判成 orphan。
_IMPORT_FORMS = (
    re.compile(r"""from\s*['"]([^'"\n]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"\n]+)['"]"""),
)


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
    return sorted(set(prod)), sorted(set(test))


def _n_cycle_files() -> list[pathlib.Path]:
    """N 域生产文件（口径与 slice 的扫描分母逐字一致）。"""
    out: list[pathlib.Path] = []
    for p in sorted(WP_COMPONENTS.rglob("*")):
        if not p.is_file() or p.suffix not in (".ts", ".vue"):
            continue
        rel = p.relative_to(WP_COMPONENTS).as_posix()
        if "__tests__" in rel:
            continue
        if (re.match(r"^GtN\d", rel) or re.match(r"^n[1-5]/", rel)
                or re.match(r"^composables/useN\d", rel)
                or re.match(r"^composables/n[1-5]", rel)):
            out.append(p)
    return out


def _n_composables() -> list[pathlib.Path]:
    return sorted(
        p for p in WP_COMPOSABLES.glob("*.ts")
        if re.match(r"^(useN[1-5]|n[1-5])", p.name)
    )


def _rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _line_no_of(ref: str) -> int:
    m = re.search(r"#L(\d+)$", ref)
    assert m, f"source_ref 缺行号：{ref}"
    return int(m.group(1))


def _path_of(ref: str) -> pathlib.Path:
    return ROOT / ref.split("#L")[0]


def _line_at(ref: str) -> str:
    """现读 `path#Lnn` 指向的那一行（1-based）。"""
    path = _path_of(ref)
    assert path.is_file(), f"source_ref 指向的文件不存在：{ref}"
    lines = _cached_text(path).split("\n")
    n = _line_no_of(ref)
    assert 1 <= n <= len(lines), f"source_ref 行号越界：{ref}（文件共 {len(lines)} 行）"
    return lines[n - 1]


def _sheet_names(path: pathlib.Path) -> list[str]:
    """openpyxl 现读 sheet 名 —— 🔴 **不得 strip**（N4A 尾随空格是真实缺陷载体）。"""
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _formula_counts(path: pathlib.Path, *, data_only: bool = False) -> dict[str, int]:
    wb = openpyxl.load_workbook(path, data_only=data_only)
    try:
        out: dict[str, int] = {}
        for ws in wb.worksheets:
            n = 0
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        n += 1
            out[ws.title] = n
        return out
    finally:
        wb.close()


def _load_module(name: str, path: pathlib.Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"无法以 importlib 加载 {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry_of(slice_doc: dict, code: str) -> dict:
    for e in slice_doc["independent_entries"]:
        if e["wp_code_pattern"].startswith(code) and e["wp_code_pattern"][len(code):len(code) + 1].isalpha():
            return e
    raise AssertionError(f"slice 里找不到 {code} 的 entry")


def _code_of_entry(entry: dict) -> str:
    m = re.match(r"^(N\d+)", entry["wp_code_pattern"])
    assert m, entry["wp_code_pattern"]
    return m.group(1)


def _workbook_of(code: str, slice_doc: dict) -> pathlib.Path:
    for e in slice_doc["independent_entries"]:
        if _code_of_entry(e) == code:
            return N_TEMPLATE_DIR / e["template_ref"]["workbook"]
    raise AssertionError(code)


def _slice_letters_on_disk() -> list[pathlib.Path]:
    return sorted(DATA.glob("workpaper_sync_*_cycle_manifest_slice.json"))


# ════════════════════════════════════════════════════════════════════════════
# fixtures
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(SLICE_PATH)


@pytest.fixture(scope="module")
def deletion_plan() -> dict:
    return _load(PLAN_PATH)


@pytest.fixture(scope="module")
def paradigm() -> dict:
    return _load(PARADIGM_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return _load(FULL_MANIFEST)


@pytest.fixture(scope="module")
def n_files() -> list[pathlib.Path]:
    return _n_cycle_files()


# ════════════════════════════════════════════════════════════════════════════
# 判据零：守卫自身自检（工具错了，后面全部判据一起假）
# ════════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:

    def test_all_required_artifacts_exist(self) -> None:
        """**Validates: Requirements 12.4**"""
        for p in (SLICE_PATH, PLAN_PATH, PARADIGM_PATH, FULL_MANIFEST, OVERLAY,
                  CONTRACT_GUARD, COVERAGE_GUARD, CHECKLIST_ROUTER, REGISTRY,
                  HTML_RENDERER_REGISTRY, SHARED_BASE, SHARED_ROUTER,
                  AC14_NOTICE_TS, AC14_NOTICE_VUE, N_TEMPLATE_DIR):
            assert p.exists(), f"缺少产物：{p}"

    def test_strip_comments_hides_content_but_keeps_line_numbers(self) -> None:
        src = "a\n// hidden marker\nb\n/* x\ny */\nc\n"
        out = _strip_comments(src)
        assert "hidden marker" not in out
        assert len(out.split("\n")) == len(src.split("\n")), "剥注释改变了行数"

    def test_strip_comments_really_hides_a_commented_marker_in_an_n_host(self) -> None:
        """反向自检：N3 宿主里有一整段注释在讲「N3 没有披露 Tab」，剥注释后必须消失。"""
        raw = _cached_text(WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue")
        assert "N3TabDisclosure.vue" in raw, "N3 宿主里的那段注释不见了 ⇒ 本自检失去对象"
        assert "N3TabDisclosure.vue" not in _strip_comments(raw)

    def test_inside_double_quoted_string_detector_works_both_ways(self) -> None:
        line = 'x = "import a from \'./b\'"; import c from "./d"'
        first = line.index("import a")
        second = line.index("import c")
        assert _inside_double_quoted_string(line, first) is True
        assert _inside_double_quoted_string(line, second) is False

    def test_import_scanner_accepts_a_multiline_import(self) -> None:
        """🔴 本轮实测缺陷的自检：`from '…'` 独占一行时必须仍能定位。

        `GtN2TaxesPayable.vue` 的 `n2SheetRouting` import 是多行形态；只匹配
        「同一行 import…from」的扫描器会把它漏掉，进而把一个 live 模块判成 orphan。
        """
        prod, _ = _statement_edges_to(WP_COMPOSABLES / "n2SheetRouting.ts")
        assert prod, "n2SheetRouting.ts 现算生产边为空 ⇒ 多行 import 没被认出来"
        assert any("GtN2TaxesPayable.vue" in ref for ref in prod), prod
        host = _strip_comments(_cached_text(WP_COMPONENTS / "GtN2TaxesPayable.vue"))
        hit = [i for i, l in enumerate(host.split("\n"), 1) if "n2SheetRouting" in l]
        assert hit, "宿主里找不到 n2SheetRouting"
        assert not re.search(r"import[^\n]*from", host.split("\n")[hit[0] - 1]), (
            "该 import 已经变成单行形态 ⇒ 本自检失去对象，请换一个多行 import 的例子"
        )

    def test_resolve_spec_is_path_based_not_stem_based(self) -> None:
        importer = WP_COMPONENTS / "GtN1DeferredTaxAssets.vue"
        got = _resolve_spec("./composables/useN1DualMode", importer)
        assert got == (WP_COMPOSABLES / "useN1DualMode").resolve()
        assert _resolve_spec("vue", importer) is None

    def test_sheet_names_are_not_stripped(self, manifest_slice: dict) -> None:
        """🔴 ND-6：N4A 的**尾随空格**与国企 sheet 的**缺右括号**都必须原样保留。"""
        n4 = _sheet_names(_workbook_of("N4", manifest_slice))
        assert "税金及附加审计程序表N4A " in n4, n4
        assert "税金及附加审计程序表N4A" not in n4, "尾随空格被 strip 了 ⇒ BP-11 会凭空消失"
        n5 = _sheet_names(_workbook_of("N5", manifest_slice))
        assert "附注披露信息（国企" in n5, n5
        assert "附注披露信息（国企）" not in n5, "缺右括号的真名被补全了 ⇒ 判据失效"

    def test_formula_scan_needs_data_only_false(self, manifest_slice: dict) -> None:
        """扫描口径是判据不是巧合：`data_only=True` 必须得到 0。"""
        wb = _workbook_of("N3", manifest_slice)
        assert sum(_formula_counts(wb, data_only=False).values()) > 0
        assert sum(_formula_counts(wb, data_only=True).values()) == 0

    def test_n_cycle_denominator_is_non_vacuous(self, n_files: list[pathlib.Path]) -> None:
        assert len(n_files) >= 100, f"N 域生产文件只有 {len(n_files)} 个 ⇒ 扫描分母可疑"
        assert any(p.name.startswith("GtN") for p in n_files)
        assert any("/n1/" in p.as_posix() for p in n_files)

    def test_two_identity_families_are_distinct_scanners(self) -> None:
        """两族扫描器必须真的分得开，否则「两族」是同一族写两遍。"""
        render = _render_key_hits(_n_cycle_files())
        persist = _persist_key_hits(_n_cycle_files())
        assert render and persist, (render, persist)
        assert not ({h["site"] for h in render} & {h["site"] for h in persist}), (
            "两族站点集合相交 ⇒ 扫描器没分开"
        )

    def test_the_m_style_persistence_scanner_finds_nothing_in_n(self) -> None:
        """🔴 ND-8 的反向断言：M 那套 ``itemId: `…row-${n}…` `` 在 N 上现算 0 命中。

        没有这一条，「本轮换了扫描口径」只是自述；有了它，抄旧扫描器的人会看到 0 而知道
        必须换口径（而不是以为 N 没缺陷）。
        """
        rx = re.compile(r"""itemId\s*:\s*`[^`]*row-\$\{\s*(?:n|i|idx|index)\s*\}""")
        hits = [
            f"{_rel(p)}#L{i}"
            for p in _n_cycle_files()
            for i, line in enumerate(_strip_comments(_cached_text(p)).split("\n"), 1)
            if rx.search(line)
        ]
        assert hits == [], f"M 式扫描器在 N 上有命中 {hits} ⇒ 形态判断要重做"

    def test_display_sequence_is_not_counted_as_a_defect(self) -> None:
        """反向判据：展示序号族非空，且不与缺陷族相交。"""
        seq = _display_seq_sites(_n_cycle_files())
        assert seq, "展示序号族为空 ⇒ 反向判据空跑"
        defects = {h["site"] for h in _render_key_hits(_n_cycle_files())} | {
            h["site"] for h in _persist_key_hits(_n_cycle_files())}
        assert not (set(seq) & defects)


# ════════════════════════════════════════════════════════════════════════════
# 扫描器（两族缺陷 + 两族反向）
# ════════════════════════════════════════════════════════════════════════════
def _render_key_hits(files: list[pathlib.Path]) -> list[dict[str, str]]:
    """渲染键族：`(rowId|rowKey|id|key): <含下标的值>`，排除熵键（含 `Date.now`）。"""
    out: list[dict[str, str]] = []
    for p in files:
        for i, line in enumerate(_strip_comments(_cached_text(p)).split("\n"), 1):
            m = re.search(r"""\b(rowId|rowKey|id|key)\s*:\s*([^,}\n]+)""", line)
            if not m:
                continue
            value = m.group(2)
            if "Date.now" in value:
                continue
            if not re.search(r"\b(idx|index|i)\b", value):
                continue
            out.append({"site": f"{_rel(p)}#L{i}", "key": m.group(1), "value": value.strip()})
    return sorted(out, key=lambda d: d["site"])


def _persist_key_hits(files: list[pathlib.Path]) -> list[dict[str, str]]:
    """持久化键族：item_id 模板里含 `${n|i|idx|index}`（含 `${ITEM_PREFIX}-${index}` 形态）。"""
    out: list[dict[str, str]] = []
    generic = re.compile(
        r"""(?:itemId|item_id)\s*[:=]\s*`([^`]*\$\{\s*(?:n|i|idx|index)\s*\}[^`]*)`""")
    prefixed = re.compile(r"""`\$\{ITEM_PREFIX\}-\$\{\s*(n|i|idx|index)\s*\}`""")
    for p in files:
        for i, line in enumerate(_strip_comments(_cached_text(p)).split("\n"), 1):
            m = generic.search(line)
            if m:
                out.append({"site": f"{_rel(p)}#L{i}", "item_id_template": m.group(1)})
                continue
            m2 = prefixed.search(line)
            if m2:
                out.append({"site": f"{_rel(p)}#L{i}",
                            "item_id_template": "${ITEM_PREFIX}-${%s}" % m2.group(1)})
    return sorted(out, key=lambda d: d["site"])


def _display_seq_sites(files: list[pathlib.Path]) -> list[str]:
    rx = re.compile(r"""\bseq\b\s*[:=]\s*(?:i|idx|index)\s*\+\s*1""")
    return sorted(
        f"{_rel(p)}#L{i}"
        for p in files
        for i, line in enumerate(_strip_comments(_cached_text(p)).split("\n"), 1)
        if rx.search(line)
    )


def _entropy_key_sites(files: list[pathlib.Path]) -> list[dict[str, str]]:
    rx = re.compile(r"""`([a-z0-9-]+)-\$\{Date\.now\(\)\}""")
    out = []
    for p in files:
        for i, line in enumerate(_strip_comments(_cached_text(p)).split("\n"), 1):
            m = rx.search(line)
            if m:
                out.append({"site": f"{_rel(p)}#L{i}", "prefix": m.group(1)})
    return sorted(out, key=lambda d: d["site"])


_ARRAY_ADDRESSING = {
    "update_by_row_index": r"function (?:update|set)\w*\(\s*(?:rowIndex|index|idx)\s*:",
    "remove_by_row_index": r"function remove\w*\(\s*(?:rowIndex|index|idx)\s*:",
    "array_slot_write": r"\b(?:currentRows|rows|list|items)\s*\[\s*(?:rowIndex|index|idx|i)\s*\]",
    "filter_by_index": r"\.filter\(\s*\([^)]*\bi\b[^)]*\)\s*=>[^\n]*\bi\s*!==",
    "splice_by_index": r"\.splice\(\s*(?:rowIndex|index|idx|i)\s*,",
}


def _array_addressing_counts(files: list[pathlib.Path]) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, pat in _ARRAY_ADDRESSING.items():
        rx = re.compile(pat)
        out[name] = sum(
            1
            for p in files
            for line in _strip_comments(_cached_text(p)).split("\n")
            if rx.search(line)
        )
    return out


_HARDCODED = {
    "blankRows_literal_count": r"blankRows\s*\([^,)]*,\s*\d+\s*\)",
    "horizontal_company_column_literals": r"['\"]公司[1-9]['\"]|['\"]单位[1-9]['\"]",
    "column_key_uses_label": r"key:\s*(?:col\.|c\.)?label\b",
    "row_cell_key_uses_label": r"\[\s*(?:row|r)\.label\s*\]",
    "seed_placeholder_literal": r"['\"]项目[1-9N]['\"]",
    "positional_row_id_template": r"`row-\$\{\s*(?:i|idx|index)\s*\}`",
}


def _hardcoded_hits(files: list[pathlib.Path], name: str) -> list[str]:
    rx = re.compile(_HARDCODED[name])
    return sorted(
        f"{_rel(p)}#L{i}"
        for p in files
        for i, line in enumerate(_strip_comments(_cached_text(p)).split("\n"), 1)
        if rx.search(line)
    )


# ════════════════════════════════════════════════════════════════════════════
# 判据一：slice_scope 可复算（selection_rule 现算等值）
# ════════════════════════════════════════════════════════════════════════════
def _n_manifest_entries(full_manifest: dict) -> list[dict]:
    return [
        e for e in full_manifest["entries"]
        if e["document_type"] == "xlsx"
        and any(str(p).startswith("N") for p in e["wp_match"]["wp_code_patterns"])
    ]


class TestSliceScopeIsRecomputable:

    def test_selection_rule_recomputes_the_entry_set(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        按 selection_rule 从 manifest **现算** entry 集合，与 slice 做**有序等值 + 无重复**
        双断言（Task 55 的 M23 教训：只逐个断言「声明的成员合法」挡不住少写/写重复）。
        """
        computed = sorted(
            e["entry_id"] for e in _n_manifest_entries(full_manifest) if e["independent_entry"])
        declared = [e["entry_id"] for e in manifest_slice["independent_entries"]]
        assert len(declared) == len(set(declared)), f"slice 里 entry_id 重复：{declared}"
        assert sorted(declared) == computed, (sorted(declared), computed)

    def test_scope_counters_match_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """**Validates: Requirements 12.4**"""
        scope = manifest_slice["slice_scope"]
        n_all = _n_manifest_entries(full_manifest)
        assert scope["n_prefixed_entry_total"] == len(n_all)
        assert scope["n_prefixed_independent_total"] == len(
            [e for e in n_all if e["independent_entry"]])
        assert scope["independent_entry_count"] == len(manifest_slice["independent_entries"])
        assert scope["cycle"] == "N" and scope["document_type"] == "xlsx"
        for item in scope["excluded_from_slice"]:
            assert item["what"] and item["reason"] and item["verified_how"]

    def test_every_n_entry_is_xlsx(self, full_manifest: dict) -> None:
        """**Validates: Requirements 12.4**"""
        n_all = _n_manifest_entries(full_manifest)
        assert n_all, "N 前缀 entry 现算为 0 ⇒ 判据空跑"
        assert {e["document_type"] for e in n_all} == {"xlsx"}

    def test_there_is_no_n0_workbook_and_no_n0_entry(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        与 K/L 两轮相反：那两轮各有一本 K0/L0 在 `_index.json` 里却无 entry，N 循环两侧都是空。
        """
        assert [e["entry_id"] for e in full_manifest["entries"]
                if "n0" in e["entry_id"].lower()] == []
        idx = _load(TEMPLATE_INDEX)
        n_index = [it for it in idx["files"]
                   if str(it.get("relative_path", "")).replace("\\", "/").startswith("N/")]
        assert {it["wp_code"] for it in n_index} == set(N_CODES), n_index
        on_disk = {p.name for p in N_TEMPLATE_DIR.iterdir() if not p.name.startswith("~$")}
        assert {it["filename"] for it in n_index} == on_disk

    def test_parent_duplicate_children_recompute_and_the_section_is_present(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        🔴 ND-1：条件节 `parent_duplicate_summary` **触发**（K/L/M 三轮各 0 条、各写了
        「未触发条件节必须缺席」的判据 —— 照抄必假红）。
        """
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        computed = sorted(
            e["entry_id"] for e in full_manifest["entries"] if e.get("parent_entry_id") in ids)
        section = manifest_slice["parent_duplicate_summary"]
        declared = [c["entry_id"] for c in section["children"]]
        assert len(declared) == len(set(declared))
        assert sorted(declared) == computed, (sorted(declared), computed)
        assert manifest_slice["slice_scope"]["parent_duplicate_count"] == len(computed)
        assert section["counters"]["children_total"] == len(computed)
        for child in section["children"]:
            src = next(e for e in full_manifest["entries"]
                       if e["entry_id"] == child["entry_id"])
            assert src["independent_entry"] is False
            assert src["migration_state"] == "parent_duplicate"
            assert child["parent_entry_id"] == src["parent_entry_id"]
            assert child["host_path"] == src["host_path"]

    def test_children_have_no_write_channel_of_their_own_unlike_j(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        🔴 与 J1-8 那条子入口（自己 `http.put` 直写、构成父 entry 写路径双轨）**不同**：
        N 的 4 条子入口全部经父 entry 的 `useN1FormData` 写库。照抄 J 的「第二写路径」必假红。
        """
        section = manifest_slice["parent_duplicate_summary"]
        for child in section["children"]:
            body = _strip_comments(_cached_text(ROOT / child["host_path"]))
            writes = [i for i, line in enumerate(body.split("\n"), 1)
                      if re.search(r"\b(?:http|api)\.(?:put|post|patch)\s*\(", line)]
            assert writes == [], f"{child['entry_id']} 竟有自己的写站点 {writes}"
            assert "useN1FormData" in body, f"{child['entry_id']} 没有走父 entry 的持久化模块"
            assert child["own_oo_mount_site"]
            assert "<GtOnlyOfficeSheet" in body.split("\n")[
                _line_no_of(child["own_oo_mount_site"]) - 1]
        assert section["counters"]["children_with_own_write_channel"] == 0
        assert section["counters"]["children_with_own_oo_mount"] == len(section["children"])
        n1_tree = [p for p in (WP_COMPONENTS / "n1").rglob("*.vue") if p.is_file()]
        without_oo = [p for p in n1_tree
                      if "<GtOnlyOfficeSheet" not in _strip_comments(_cached_text(p))]
        assert section["counters"]["n1_subtree_components_total"] == len(n1_tree), (
            section["counters"]["n1_subtree_components_total"], len(n1_tree))
        assert section["counters"]["n1_subtree_components_without_oo_mount"] == len(without_oo)
        assert len(n1_tree) - len(without_oo) == len(section["children"]), (
            "「挂了 OO 的子组件数」必须恰等于 parent_duplicate 子入口数 —— "
            "不等说明 generator 的枚举口径与本判据不同"
        )

    def test_untriggered_conditional_sections_are_absent(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4**

        `currency_variant_model` 未触发 ⇒ 必须缺席（写一个空节就是 additive 死声明）。
        """
        assert "currency_variant_model" not in manifest_slice
        state = manifest_slice["paradigm_schema_conflict"]["new_section_not_in_schema"][
            "conditional_sections_state"]
        assert state["currency_variant_model"].startswith("not_triggered")
        assert state["parent_duplicate_summary"].startswith("triggered")
        assert state["dynamic_row_identity"].startswith("triggered")

    def test_host_module_edges_in_the_renderer_registry_are_real(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        可达性判据落在 `htmlRendererRegistry.ts` 的**模块边**上（不是符号名 grep）。
        """
        registry = _cached_text(HTML_RENDERER_REGISTRY)
        for entry in manifest_slice["independent_entries"]:
            host = ROOT / entry["host_path"]
            assert host.is_file(), entry["host_path"]
            prod, _ = _statement_edges_to(host)
            assert any(_rel(HTML_RENDERER_REGISTRY) in ref for ref in prod), (
                f"{entry['entry_id']} 的宿主在 registry 里没有模块边：{prod}"
            )
            assert f"./{host.name}" in registry
        assert manifest_slice["honest_adjudication_summary"][
            "reachable_hosts_in_cycle"] == len(manifest_slice["independent_entries"])

    def test_no_pilot_contract_belongs_to_the_n_cycle(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.1, 12.12**"""
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        owners: dict[str, Any] = {}
        for p in sorted(CONTRACT_DIR.glob("*.json")):
            owners[p.name] = (_load(p).get("review") or {}).get("entry_id")
        assert owners, "契约目录为空 ⇒ 这条判据是空跑"
        reviewed = {k: v for k, v in owners.items() if k != CANDIDATE_CONTRACT_FILE}
        assert set(reviewed.values()) == PILOT_CONTRACT_OWNERS, reviewed
        assert owners[CANDIDATE_CONTRACT_FILE] is None, (
            "candidate 契约的 review.entry_id 应为 null（反例分母，不得要求非空）"
        )
        assert _load(CONTRACT_DIR / CANDIDATE_CONTRACT_FILE)["review_status"] == "candidate"
        assert not (set(owners.values()) & ids)
        assert manifest_slice["slice_scope"]["excluded_pilot_entry_count"] == 0
        assert manifest_slice["honest_adjudication_summary"]["pilot_contract_published"] == 0

    def test_no_n_adapter_is_registered(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.4, 12.1** —— Property 3 的否定方向之一。"""
        registry = _cached_text(REGISTRY)
        assert not re.search(r"xlsx/gt-n\d", registry), "registry 里出现了 N adapter"
        for entry in manifest_slice["independent_entries"]:
            assert entry["adapter_id"] is None
        # 反向：registry 里**确实**有 pilot adapter ⇒ 判据非空跑
        assert any(owner in registry for owner in PILOT_CONTRACT_OWNERS), (
            "registry 里一个 pilot adapter 都找不到 ⇒ 这条判据是空跑"
        )


# ════════════════════════════════════════════════════════════════════════════
# 判据二：裁决合法性（AC 1.3 / 1.4 / 1.5 / 12.8 / 12.9 + AP-1）
# ════════════════════════════════════════════════════════════════════════════
class TestAdjudicationLegality:

    def test_every_entry_has_a_binary_html_counterpart_verdict(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.8**"""
        for e in manifest_slice["independent_entries"]:
            assert e["html_counterpart_verdict"] in HTML_COUNTERPART_VERDICTS, e["entry_id"]
            assert e["html_counterpart_source_refs"], e["entry_id"]

    def test_no_pure_oo_entry_exists_in_this_cycle(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.8**

        🔴 tasks.md 正文点名「纯 OO entry」。本轮的实证结论是**不存在** —— 5 条全是 exists。
        这一条把结论钉住：既不许把某条改成 `none` 而不改 source_refs（下方三边锁会红），
        也不许在 summary 里报出一个不存在的 `single_onlyoffice`。
        """
        verdicts = [e["html_counterpart_verdict"] for e in manifest_slice["independent_entries"]]
        assert verdicts == ["exists"] * len(verdicts), verdicts
        summary = manifest_slice["honest_adjudication_summary"]
        assert summary["html_counterpart_none"] == 0
        assert summary["html_counterpart_exists"] == len(verdicts)
        assert summary["adjudicated_as_single_onlyoffice"] == 0
        assert "没有纯 OO entry" in summary["reason"] or "不存在" in summary["reason"]

    def test_single_onlyoffice_requires_no_html_counterpart(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.8** —— AC 12.8 的唯一合法判据。"""
        for e in manifest_slice["independent_entries"]:
            if e["capability"] == "single_onlyoffice":
                assert e["html_counterpart_verdict"] == "none", e["entry_id"]

    def test_adjudication_reason_is_not_circular(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """**Validates: Requirements 12.8** —— AP-1 循环论证检测。"""
        ap1 = next(a for a in paradigm["adjudication_criteria"]["anti_patterns"]
                   if a["id"] == "AP-1")
        markers = ap1["circular_reason_markers"]
        assert markers, "AP-1 的 marker 清单为空 ⇒ 判据空跑"
        for e in manifest_slice["independent_entries"]:
            if e["capability"] != "single_onlyoffice":
                continue
            reason = e["adjudication"]["reason"] or ""
            hit = [m for m in markers if m in reason]
            assert not hit, f"{e['entry_id']} 的裁决理由是循环论证：{hit}"

    def test_capability_is_null_and_pending_fields_are_complete(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """**Validates: Requirements 1.3, 12.1** —— SR-3 右支逐字段。"""
        schema = paradigm["slice_schema"]
        enum = paradigm["adjudication_criteria"]["capability_enum"]
        assert set(enum) == {"bidirectional", "single_html", "single_onlyoffice", "unreachable"}
        required = schema["required_pending_verdict_fields"]
        semantics = schema["pending_verdict_field_semantics"]
        for e in manifest_slice["independent_entries"]:
            assert e["capability"] is None, e["entry_id"]
            for field in required:
                assert field in e, (e["entry_id"], field)
                kind = semantics[field]
                value = e[field]
                if kind == "non_empty_string":
                    assert isinstance(value, str) and value.strip(), (e["entry_id"], field)
                elif kind == "member_of_capability_enum":
                    assert value in enum, (e["entry_id"], field, value)
                elif kind == "non_empty_list":
                    assert isinstance(value, list) and value, (e["entry_id"], field)
                else:
                    raise AssertionError(f"未声明语义的 pending 字段：{field}")

    def test_capability_matches_honest_capability(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.3** —— SR-4。"""
        for e in manifest_slice["independent_entries"]:
            assert e["capability"] == e["adjudication"]["honest_capability"], e["entry_id"]

    def test_pending_entries_carry_no_identity(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.1** —— 待裁决/single 都不得挂五个身份字段。"""
        for e in manifest_slice["independent_entries"]:
            for field in ("adapter_id", "authority_model", "definition_bundle",
                          "instrumentation_candidate", "published_representation"):
                assert e[field] is None, (e["entry_id"], field)
            assert e["scenario_profile_id"] is None

    def test_adjudication_carries_both_negative_reasons(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.8, 12.9**"""
        for e in manifest_slice["independent_entries"]:
            adj = e["adjudication"]
            assert adj["not_single_html_because"] and adj["not_bidirectional_because"]
            assert e["template_ref"]["workbook"] in adj["not_single_html_because"], (
                f"{e['entry_id']} 的 not_single_html_because 没有引用它自己的权威册"
            )

    def test_broken_or_missing_switch_is_not_read_as_a_single_html_reason(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.9**

        🔴 N4/N5 的开关是空实现，正是最容易被误当成「裁 single_html」理由的形态。
        """
        ms = manifest_slice["mode_switch_resolution"]
        assert "开关坏了" in ms["why_this_is_not_a_reason_to_adjudicate_single"]
        inert = [eid for eid, v in ms["per_entry_verdict"].items() if v == "inert"]
        assert inert, "inert 集合为空 ⇒ 这条判据空跑"
        for eid in inert:
            e = next(x for x in manifest_slice["independent_entries"] if x["entry_id"] == eid)
            assert e["capability"] is None
            assert "inert" in e["adjudication"]["not_single_html_because"]

    def test_manifest_mirror_divergence_is_registered_not_silently_equal(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """**Validates: Requirements 1.3, 12.8**

        🔴 判据 = 断言「**必须不一致**且已登记 BP」，不是断言相等。
        """
        bp_ids = {b["id"] for b in manifest_slice["blocking_preconditions"]}
        assert "BP-9" in bp_ids
        src = {e["entry_id"]: e for e in full_manifest["entries"]}
        for e in manifest_slice["independent_entries"]:
            mirror = e["manifest_mirror"]
            upstream = src[e["entry_id"]]
            assert mirror["capability"] == upstream["capability"] == "single_onlyoffice"
            assert mirror["html_store"] == upstream["html_store"] == "unresolved"
            assert e["capability"] != mirror["capability"], (
                f"{e['entry_id']} 的 slice 裁决与 mirror 相同 ⇒ 分歧判据失效"
            )
            assert "BP-9" in mirror["why_not_adopted"]

    def test_ac15_is_declared_not_applicable_and_ac14_is_the_live_one(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.4, 1.5**"""
        summary = manifest_slice["honest_adjudication_summary"]
        assert summary["adjudicated_as_single_onlyoffice"] == 0
        assert summary["adjudicated_as_single_html"] == 0
        assert summary["adjudicated_as_unreachable"] == 0
        assert "AC 1.5" in summary["ac_15_not_applicable_because"]
        assert "AC 1.4" in manifest_slice["mode_switch_resolution"]["live_ac_is_1_4"]

    def test_ac14_notice_single_source_exists_and_is_consumed(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.4**

        单一真源必须存在**且真被消费**（死常量不算承载者）—— Property 3 的第四件事。
        """
        ts = _cached_text(AC14_NOTICE_TS)
        assert "SYNC_ADAPTER_REGISTERED_ENTRY_IDS" in ts
        m = re.search(
            r"SYNC_ADAPTER_REGISTERED_ENTRY_IDS[^=]*=\s*(\[[^\]]*\])", ts)
        assert m, "找不到 SYNC_ADAPTER_REGISTERED_ENTRY_IDS 的声明"
        assert m.group(1).strip() == "[]", (
            f"已注册 adapter 的 entry 清单不再为空：{m.group(1)} ⇒ Property 3 的前提变了"
        )
        body_after = ts[m.end():]
        assert "SYNC_ADAPTER_REGISTERED_ENTRY_IDS" in body_after, (
            "该常量在声明之后没有任何消费方 ⇒ 是死常量，AC 1.4 的门控形同虚设"
        )
        prod, _ = _statement_edges_to(AC14_NOTICE_VUE)
        assert len(prod) >= 20, f"提示组件生产消费方只有 {len(prod)} 个 ⇒ 平台侧判据可疑"
        gate = manifest_slice["mode_switch_resolution"]["ac14_notice_single_source"]
        assert gate["production_consumers"] == len(prod), (gate["production_consumers"], len(prod))
        assert gate["registered_entry_ids_is_empty"] is True

    def test_bp7_is_registered_because_no_n_host_mounts_the_notice(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.4**"""
        mounted = [
            e["entry_id"] for e in manifest_slice["independent_entries"]
            if "GtEntrySyncCapabilityNotice" in _strip_comments(
                _cached_text(ROOT / e["host_path"]))
        ]
        assert mounted == [], f"有 N 宿主挂了提示组件 {mounted} ⇒ BP-7 该解除了"
        assert manifest_slice["mode_switch_resolution"]["counters"][
            "entries_mounting_the_ac14_notice"] == 0
        bp7 = next(b for b in manifest_slice["blocking_preconditions"] if b["id"] == "BP-7")
        assert sorted(bp7["entries"]) == sorted(
            e["entry_id"] for e in manifest_slice["independent_entries"])

    def test_no_host_template_claims_bidirectional(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.4** —— Property 3 的否定方向之二。"""
        for e in manifest_slice["independent_entries"]:
            body = _strip_comments(_cached_text(ROOT / e["host_path"]))
            assert "可双向回写" not in body, e["entry_id"]
            assert e["ui_toolbar_gate"]["claims_bidirectional_in_template"] is False

    def test_all_blocking_preconditions_carry_task48_fields(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """**Validates: Requirements 12.1** —— `effective_from_task_48` 生效（56 ≥ 48）。"""
        extra = paradigm["slice_schema"]["effective_from_task_48"][
            "required_blocking_precondition"]
        base = paradigm["slice_schema"]["required_blocking_precondition"]
        one_of = paradigm["slice_schema"]["required_blocking_precondition_one_of"]
        for bp in manifest_slice["blocking_preconditions"]:
            for field in list(base) + list(extra):
                assert field in bp, (bp["id"], field)
            for group in one_of:
                assert any(k in bp for k in group), (bp["id"], group)
            assert bp["entries"], bp["id"]

    def test_every_blocking_precondition_is_referenced_by_someone(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.1**

        悬挂的 BP（没有任何 entry 引用）= 死登记；反向：entry 引用了不存在的 BP 也要红。
        """
        declared = {b["id"] for b in manifest_slice["blocking_preconditions"]}
        referenced: set[str] = set()
        for e in manifest_slice["independent_entries"]:
            referenced |= set(e["capability_target_blocked_by"])
        assert declared == referenced, (sorted(declared - referenced),
                                        sorted(referenced - declared))
        assert manifest_slice["honest_adjudication_summary"][
            "blocking_preconditions_total"] == len(declared)

    def test_entry_scoped_bps_only_name_their_own_entries(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.1, 12.10**

        entry 级 BP 的 `entries` 必须与「哪些 entry 的 blocked_by 里有它」双向一致。
        """
        by_bp: dict[str, set[str]] = {}
        for e in manifest_slice["independent_entries"]:
            for bp in e["capability_target_blocked_by"]:
                by_bp.setdefault(bp, set()).add(e["entry_id"])
        for bp in manifest_slice["blocking_preconditions"]:
            assert set(bp["entries"]) == by_bp[bp["id"]], (
                bp["id"], sorted(bp["entries"]), sorted(by_bp[bp["id"]]))

    def test_the_four_entry_scoped_bps_have_the_expected_shape(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.1**

        四条 N 特有的 entry 级 BP 各自的分母都必须非空且互不相同 ——
        全都指向 5 条 entry 就等于没有 entry 级 BP。
        """
        by_id = {b["id"]: b for b in manifest_slice["blocking_preconditions"]}
        all5 = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for bp_id in ("BP-4", "BP-5", "BP-8", "BP-10", "BP-12"):
            got = set(by_id[bp_id]["entries"])
            assert got, bp_id
            assert got != all5, f"{bp_id} 覆盖全部 entry ⇒ 它不是 entry 级 BP"
        assert set(by_id["BP-4"]["entries"]) == {"xlsx/gt-n3-deferred-tax-liabilities"}
        assert set(by_id["BP-5"]["entries"]) == {
            "xlsx/gt-n4-taxes-and-surcharges", "xlsx/gt-n5-income-tax-expense"}
        assert set(by_id["BP-12"]["entries"]) == {"xlsx/gt-n5-income-tax-expense"}
        assert set(by_id["BP-10"]["entries"]) == {
            "xlsx/gt-n1-deferred-tax-assets", "xlsx/gt-n3-deferred-tax-liabilities"}


# ════════════════════════════════════════════════════════════════════════════
# 判据三：HTML 对端 source-backed（AC 12.8 的实证基础 + 真实传输键）
# ════════════════════════════════════════════════════════════════════════════
class TestHtmlCounterpartIsSourceBacked:

    def test_source_refs_point_at_real_paths_and_lines(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.8**

        三边锁的第一边：声明指到的**行**必须现读得到（不是只验文件存在）。
        """
        for e in manifest_slice["independent_entries"]:
            for ref in e["html_counterpart_source_refs"]:
                assert _line_at(ref).strip(), f"{e['entry_id']} 的 {ref} 指到空行"

    def test_item_prefix_is_read_from_the_owner_constant(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.8**

        三边锁的第二/第三边：`ITEM_PREFIX` 从 impl **现读**，并与 slice 声明逐字相等。
        """
        for e in manifest_slice["independent_entries"]:
            hc = e["html_counterpart"]
            ref = hc["owner_constant_source_ref"]
            line = _line_at(ref)
            m = re.search(r"""const\s+ITEM_PREFIX\s*=\s*['"]([^'"]+)['"]""", line)
            assert m, f"{ref} 不是 ITEM_PREFIX 声明行：{line!r}"
            assert m.group(1) == hc["item_id_prefix"], (ref, m.group(1), hc["item_id_prefix"])
            assert hc["table_keys"] == [f"{_code_of_entry(e)}-{{sheet}}-{{field}}"]

    def test_read_write_and_filter_sites_are_the_real_calls(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.8**"""
        for e in manifest_slice["independent_entries"]:
            hc = e["html_counterpart"]
            read = _line_at(hc["read_source_ref"])
            assert "api.get(" in read and "checklist-responses" in read, read
            write = _line_at(hc["write_source_ref"])
            assert "api.put(" in write and "checklist-responses" in write, write
            filt = _line_at(hc["namespace_filter_source_ref"])
            assert "ITEM_PREFIX" in filt, filt
            second = _line_at(hc["second_write_channel_source_ref"])
            assert "trial-balance/writeback" in second, second

    def test_html_store_endpoint_exists_in_the_router(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.8**"""
        router = _cached_text(CHECKLIST_ROUTER).split("\n")
        for e in manifest_slice["independent_entries"]:
            assert e["html_counterpart"]["store"] == "checklist_responses"
        get_ref = "backend/app/routers/checklist_responses.py#L84"
        put_ref = "backend/app/routers/checklist_responses.py#L132"
        assert "@router.get(" in router[_line_no_of(get_ref) - 1]
        assert "@router.put(" in router[_line_no_of(put_ref) - 1]

    def test_no_n_host_imports_the_shared_checklist_persistence(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.8**

        🔴 K/J 的形态是「宿主 → useChecklistPersistence → PUT」；照抄到 N 上会 0 命中，
        被误读成「N 没有持久化」。本条把「N 域不经共享适配器」落成判据。
        """
        hits = [
            _rel(p) for p in _n_cycle_files()
            if "useChecklistPersistence" in _strip_comments(_cached_text(p))
        ]
        assert hits == [], hits
        assert manifest_slice["transport_key_resolution"]["shared_adapter_absent"][
            "recomputed_hits"] == 0
        assert manifest_slice["honest_adjudication_summary"][
            "hosts_importing_shared_checklist_persistence"] == 0

    def test_each_entry_has_its_own_persistence_module_with_live_edges(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.8, 12.12**"""
        for e in manifest_slice["independent_entries"]:
            module = ROOT / e["html_counterpart"]["owner_module"]
            assert module.is_file(), module
            prod, _ = _statement_edges_to(module)
            assert prod, f"{e['entry_id']} 的持久化模块无生产边 ⇒ 它是 orphan，对端结论要重判"
        assert manifest_slice["honest_adjudication_summary"][
            "per_entry_persistence_modules"] == len(manifest_slice["independent_entries"])

    def test_item_id_prefixes_are_pairwise_non_prefixing(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.12** —— `N1-` vs `N10-` 类风险的两两检查。"""
        prefixes = [e["html_counterpart"]["item_id_prefix"]
                    for e in manifest_slice["independent_entries"]]
        assert len(prefixes) == len(set(prefixes)), prefixes
        for a in prefixes:
            for b in prefixes:
                if a is b:
                    continue
                assert not a.startswith(b) and not b.startswith(a), (a, b)
        assert manifest_slice["cross_entry_isolation"]["item_id_prefixes"] == {
            _code_of_entry(e): e["html_counterpart"]["item_id_prefix"]
            for e in manifest_slice["independent_entries"]
        }

    def test_template_ref_resolves_and_digests_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.10, 12.8**"""
        idx = {it["filename"]: it for it in _load(TEMPLATE_INDEX)["files"]}
        for e in manifest_slice["independent_entries"]:
            ref = e["template_ref"]
            path = N_TEMPLATE_DIR / ref["workbook"]
            assert path.is_file(), path
            raw = path.read_bytes()
            assert len(raw) == ref["size"], (ref["workbook"], len(raw), ref["size"])
            assert hashlib.sha256(raw).hexdigest() == ref["sha256"], ref["workbook"]
            names = _sheet_names(path)
            assert len(names) == ref["sheet_count"]
            counts = _formula_counts(path)
            assert sum(counts.values()) == ref["formula_cells"], ref["workbook"]
            assert len([1 for v in counts.values() if v]) == ref["sheets_with_formula"]
            assert ref["in_runtime_index"] is True
            assert idx[ref["workbook"]]["wp_code"] == ref["index_wp_code"]

    def test_each_entry_has_its_own_workbook(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.12**"""
        books = [e["template_ref"]["workbook"] for e in manifest_slice["independent_entries"]]
        shas = [e["template_ref"]["sha256"] for e in manifest_slice["independent_entries"]]
        assert len(set(books)) == len(books) == len(set(shas))


# ════════════════════════════════════════════════════════════════════════════
# 判据四：真实传输键（tasks.md 点名项之一）
# ════════════════════════════════════════════════════════════════════════════
class TestTransportKeyResolution:

    def test_every_declaration_reads_its_owner_constant(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.1, 12.8**"""
        tk = manifest_slice["transport_key_resolution"]
        assert tk["declarations"], "传输键声明为空 ⇒ 本节空跑"
        for d in tk["declarations"]:
            line = _line_at(d["owner_constant_source"])
            assert d["owner_constant"].split(" / ")[0] in line, (d["id"], line)
            if d.get("owner_constant_value"):
                assert d["owner_constant_value"] in line, (d["id"], line)

    def test_declared_keys_all_exist_in_production_source(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.1**

        两侧都验：声明的每个键至少 1 命中；「按规律猜」的键各 0 命中。
        """
        files = _n_cycle_files()
        bodies = [_strip_comments(_cached_text(p)) for p in files]
        tk = manifest_slice["transport_key_resolution"]
        declared: list[str] = []
        for d in tk["declarations"]:
            declared.extend(d.get("keys") or [])
            declared.extend(d.get("extra_keys_in_same_tab") or [])
        assert declared, "声明键集合为空 ⇒ 判据空跑"
        for key in declared:
            if "{" in key or "}" in key:
                continue  # 模板形态由 test_runtime_derived_keys_expand_from_the_impl 覆盖
            assert any(key in b for b in bodies), f"声明的键 {key} 在 N 域生产源码里 0 命中"
        for guessed in tk["nonexistent_guessed_keys"]:
            hits = [_rel(p) for p, b in zip(files, bodies) if guessed in b]
            assert hits == [], f"「不存在的键」{guessed} 竟有命中 {hits} ⇒ 反向分母失效"

    def test_runtime_derived_keys_expand_from_the_impl(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.5, 12.1**

        🔴 `N1-1-adj-{index}` 是**模板形态**：展开值（`N1-1-adj-0` …）在源码里一个都不存在。
        判据改成两条：① 模板串在 owner 模块里现读命中；② 展开数 == impl 侧类别数组的现算长度。
        """
        tk = manifest_slice["transport_key_resolution"]
        d = next(x for x in tk["declarations"] if x.get("keys_are_runtime_derived"))
        owner = _cached_text(ROOT / d["owner_module"])
        assert "${ITEM_PREFIX}-${index}" in owner.replace(" ", ""), (
            "模板串在 owner 模块里找不到 ⇒ 声明的派生方式不成立"
        )
        cats_line_no = _line_no_of(d["key_expansion_source"])
        lines = owner.split("\n")
        assert "N1_ADJUDICATION_CATEGORIES" in lines[cats_line_no - 1]
        block = []
        for line in lines[cats_line_no:]:
            if line.strip().startswith("]"):
                break
            block.append(line)
        categories = re.findall(r"'([^']+)'", "\n".join(block))
        assert categories, "类别数组现算为空 ⇒ 展开判据空跑"
        assert len(d["key_expansion"]) == len(categories), (
            len(d["key_expansion"]), len(categories))
        assert d["key_expansion"] == [f"N1-1-adj-{i}" for i in range(len(categories))]
        # 反向：展开出的字面量**确实**不在源码里（这正是不能用字面量判据的原因）
        bodies = [_strip_comments(_cached_text(p)) for p in _n_cycle_files()]
        assert not any(d["key_expansion"][0] in b for b in bodies), (
            "展开后的字面量竟出现在源码里 ⇒ 派生形态变了，判据要重写"
        )

    def test_the_fabricated_v2_key_only_lives_in_the_orphan_module(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.1, 12.12**

        🔴 与 J 的 TK-6 同型：orphan 模块声明了生产从未写过的键形态。
        判据两侧：① 该键只在 orphan 自己里命中；② orphan 的生产边为 0。
        """
        tk = manifest_slice["transport_key_resolution"]
        d = next(x for x in tk["declarations"] if x.get("second_declaration_module"))
        key = d["second_declaration_value"]
        module = ROOT / d["second_declaration_module"]
        hits = [
            _rel(p) for p in _n_cycle_files()
            if key in _strip_comments(_cached_text(p))
        ]
        assert hits == [_rel(module)], (key, hits)
        prod, _ = _statement_edges_to(module)
        assert prod == [], f"{d['second_declaration_module']} 竟有生产边 {prod} ⇒ 它不再是 orphan"
        assert key in _line_at(d["second_declaration_source"])
        # 反向：V1 的键**确实**在生产里被写
        v1_key = next(k for k in d["keys"] if k == "N4-1-rows")
        v1_hits = [_rel(p) for p in _n_cycle_files()
                   if v1_key in _strip_comments(_cached_text(p))]
        assert len(v1_hits) >= 2, (v1_key, v1_hits)

    def test_n5_foreign_namespace_reads_are_read_only(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.12** —— Property 70 的 N 特有一条，两侧都验。"""
        tk = manifest_slice["transport_key_resolution"]
        d = next(x for x in tk["declarations"] if x.get("foreign_namespaces_read"))
        assert d["foreign_namespaces_verdict"] == "READ_ONLY_NOT_A_NAMESPACE_VIOLATION"
        for item in d["foreign_namespaces_read"]:
            line = _line_at(item["site"])
            assert item["key"] in line, item
            assert "item_id ===" in line, f"{item['site']} 不是只读比对形态：{line!r}"
        # 写侧：N5 的写键全部以 N5- 开头
        module = ROOT / d["owner_module"].replace("useN5FormData.ts", "useN5CrossSheet.ts")
        body = _strip_comments(_cached_text(module))
        written = sorted(set(re.findall(r"""_persistCrossData\(\s*['"]([^'"]+)['"]""", body)))
        assert written, "N5 的跨表写键现算为空 ⇒ 判据空跑"
        for key in written:
            assert key.startswith("N5-"), f"N5 写到了别人的命名空间：{key}"
        assert set(written) <= set(d["keys"]), (written, d["keys"])

    def test_transport_summary_counters_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.1**"""
        tk = manifest_slice["transport_key_resolution"]
        s = tk["summary"]
        decls = tk["declarations"]
        assert s["declarations_total"] == len(decls)
        assert s["entry_scoped_declarations"] == len([d for d in decls if d.get("entry_id")])
        assert s["declarations_resolved_clean"] == len(
            [d for d in decls if d["status"] == "resolved"])
        assert s["declarations_resolved_with_defect"] == len(
            [d for d in decls if d["status"] == "resolved_with_defect"])
        assert s["declarations_with_two_source_declarations"] == len(
            [d for d in decls if d.get("second_declaration_module")])
        assert s["declarations_total"] == (
            s["declarations_resolved_clean"] + s["declarations_resolved_with_defect"])


# ════════════════════════════════════════════════════════════════════════════
# 判据五：Property 23 —— 动态行身份（tasks.md 点名项之二）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty23DynamicRowIdentity:

    def test_section_declares_the_forbidden_kinds_and_two_layer_semantics(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 6.5**"""
        sec = manifest_slice["dynamic_row_identity"]
        forbidden = sec["forbidden_identity_kinds"]
        for kind in ("array_index", "display_sequence", "label_text",
                     "positional_persistence_key"):
            assert kind in forbidden, kind
        assert "row-" in sec["kind_semantics_note"], (
            "kind_semantics_note 必须写明 N 与 M 的形态差异（M 有 `row-` 中缀，N 没有）"
        )
        assert sec["tables"], "动态行表清单为空 ⇒ 条件节不该存在"

    def test_every_table_verdict_follows_from_its_kind(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.5**

        蕴含关系：kind 描述位置化 ⇒ DEFECT 且必须点名它违反的禁用值；
        kind 描述持久化稳定 id ⇒ CLEAN 且**不得**带 `violates_forbidden_identity_kind`。
        """
        forbidden = set(manifest_slice["dynamic_row_identity"]["forbidden_identity_kinds"])
        entry_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        seen: set[str] = set()
        for t in manifest_slice["dynamic_row_identity"]["tables"]:
            kind = t["row_identity"]["kind"]
            assert kind not in forbidden, (
                f"{t['table_key']} 的 kind 直接写成了禁用字面值 ⇒ 范式校验器会拒收整份 slice"
            )
            assert t["entry_id"] in entry_ids
            assert t["entry_id"] not in seen, "一个 entry 声明了两张主表 ⇒ 计数会重"
            seen.add(t["entry_id"])
            positional = ("positional" in kind) or ("array_position" in kind)
            if positional:
                assert t["verdict"] == "DEFECT", t["table_key"]
                assert t["row_identity"]["violates_forbidden_identity_kind"] in forbidden, (
                    t["table_key"], t["row_identity"].get("violates_forbidden_identity_kind"))
                assert "BP-8" in t["registered_as"], t["table_key"]
            else:
                assert t["verdict"] == "CLEAN", t["table_key"]
                assert "violates_forbidden_identity_kind" not in t["row_identity"]
                assert t["registered_as"] == []
        assert seen == entry_ids, "并非每条 entry 都声明了主动态行表"

    def test_defect_tables_source_refs_carry_the_expected_tokens(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 6.5**

        每条 source_ref 现读该行并断言行内含预期 token —— **不是**只验行存在。
        """
        tables = {t["table_key"]: t for t in manifest_slice["dynamic_row_identity"]["tables"]}
        n1 = tables["n1_adjudication_rows"]["row_identity"]
        assert "ITEM_PREFIX" in _line_at(n1["persistence_source_ref"])
        assert "${ITEM_PREFIX}-${index}" in _line_at(n1["persistence_source_ref"]).replace(" ", "")
        assert "${ITEM_PREFIX}-${i}" in _line_at(n1["index_binding_source_ref"]).replace(" ", "")
        assert "N1_ADJUDICATION_CATEGORIES" in _line_at(n1["source_ref"])

        n2 = tables["n2_manual_tax_rows"]["row_identity"]
        assert "manual-${idx}" in _line_at(n2["source_ref"]).replace(" ", "")
        assert "updateManualRow" in _line_at(n2["index_binding_source_ref"])
        assert "MANUAL_ROWS_ITEM_ID" in _line_at(n2["persistence_source_ref"])

        n5 = tables["n5_tax_adjustment_rows"]["row_identity"]
        assert "index: i + 1" in _line_at(n5["source_ref"])
        assert "rowIndex" in _line_at(n5["index_binding_source_ref"])
        assert "rowIndex" in _line_at(n5["removal_source_ref"])

    def test_clean_tables_really_address_rows_by_stable_id(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.5**

        🔴 CLEAN 的两张表是本 Property 的**反向分母**。它们的正面判据：
        身份字段是持久化的 id，且删改按 id 寻址（不是按下标）。
        """
        tables = {t["table_key"]: t for t in manifest_slice["dynamic_row_identity"]["tables"]}
        clean = [t for t in tables.values() if t["verdict"] == "CLEAN"]
        assert len(clean) >= 2, "CLEAN 反向分母不足 2 张 ⇒ 「有缺陷」的结论恒真"
        n3 = tables["n3_detail_rows"]["row_identity"]
        assert n3["identity_field"] == "id"
        assert "r.id ||" in _line_at(n3["source_ref"]), _line_at(n3["source_ref"])
        addressing = _line_at(n3["addressing_source_ref"])
        assert "rowId: string" in addressing, addressing
        assert "index" not in addressing, "N3-2 竟按 index 寻址 ⇒ 它不该是 CLEAN"
        n4 = tables["n4_detail_rows"]["row_identity"]
        # 🔴 N4-2 的身份字段叫 `rowKey` 而 N3-2 叫 `id` —— 字段名不得写死。
        assert n4["identity_field"] == "rowKey"
        n4_line = _line_at(n4["source_ref"])
        assert f"{n4['identity_field']}:" in n4_line, n4_line
        assert "Date.now" in n4_line, n4_line

    def test_the_unconsumed_render_key_really_has_no_consumer(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.5**

        N2-8 的位置化身份字段现在**无消费方** —— 两面都要说清：
        既断言它是位置化的（缺陷登记成立），也断言其模板里 `:key` 现算 0（当前不串行）。
        """
        inv = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        fam = inv["render_key_family"]
        assert len(fam) == 1, fam
        assert fam[0]["consumers_in_template"] == 0
        tab = WP_COMPONENTS / "n2" / "calc" / "N2TabOtherTaxCalc.vue"
        body = _strip_comments(_cached_text(tab))
        assert ":key" not in body, (
            "N2TabOtherTaxCalc.vue 出现了 `:key` ⇒ 那个位置化身份字段可能已被消费，"
            "缺陷等级要从 latent 升级为 live"
        )

    def test_two_families_and_the_reverse_families_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.5**

        四族现算与声明做**有序等值 + 无重复**双断言。
        """
        files = _n_cycle_files()
        inv = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]

        render_sites = [h["site"] for h in _render_key_hits(files)]
        declared_render = [h["site"] for h in inv["render_key_family"]]
        assert len(declared_render) == len(set(declared_render))
        assert sorted(declared_render) == sorted(render_sites), (declared_render, render_sites)

        persist_sites = [h["site"] for h in _persist_key_hits(files)]
        declared_persist = [h["site"] for h in inv["persistence_key_family"]]
        assert len(declared_persist) == len(set(declared_persist))
        assert sorted(declared_persist) == sorted(persist_sites), (declared_persist, persist_sites)

        seq = _display_seq_sites(files)
        assert sorted(inv["display_sequence_family"]) == seq
        assert len(inv["display_sequence_family"]) == len(set(inv["display_sequence_family"]))

        entropy = [h["site"] for h in _entropy_key_sites(files)]
        declared_entropy = [h["site"] for h in inv["generated_opaque_family"]]
        assert len(declared_entropy) == len(set(declared_entropy))
        assert sorted(declared_entropy) == sorted(entropy), (declared_entropy, entropy)

    def test_array_addressing_family_counts_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.5** —— N 的系统性形态（48 处）逐族等值。"""
        inv = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        computed = _array_addressing_counts(_n_cycle_files())
        declared = inv["array_addressing_family_counts"]
        assert set(declared) == set(computed), (sorted(declared), sorted(computed))
        assert declared == computed, (declared, computed)
        assert inv["counters"]["array_addressing_sites"] == sum(computed.values())
        assert all(v > 0 for v in computed.values()), computed

    def test_identity_counters_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.5**"""
        files = _n_cycle_files()
        sec = manifest_slice["dynamic_row_identity"]
        inv = sec["positional_identity_inventory"]
        c = inv["counters"]
        assert c["render_key_hits"] == len(_render_key_hits(files))
        assert c["persistence_key_hits"] == len(_persist_key_hits(files))
        assert c["display_sequence_sites"] == len(_display_seq_sites(files))
        assert c["generated_opaque_sites"] == len(_entropy_key_sites(files))
        assert c["defect_hits_total"] == c["render_key_hits"] + c["persistence_key_hits"]
        assert c["tables_total"] == len(sec["tables"])
        assert c["tables_with_defect"] == len(
            [t for t in sec["tables"] if t["verdict"] == "DEFECT"])
        assert c["tables_clean"] == len([t for t in sec["tables"] if t["verdict"] == "CLEAN"])
        assert c["tables_total"] == c["tables_with_defect"] + c["tables_clean"]
        defect_entries = {t["entry_id"] for t in sec["tables"] if t["verdict"] == "DEFECT"}
        assert c["entries_with_positional_identity_defects"] == len(defect_entries)
        assert c["entries_without_positional_identity_defects"] == (
            len(manifest_slice["independent_entries"]) - len(defect_entries))
        files_with = {h["site"].split("#")[0] for h in _render_key_hits(files)} | {
            h["site"].split("#")[0] for h in _persist_key_hits(files)}
        assert c["files_with_positional_identity_defect"] == len(files_with)

    def test_hardcoded_scan_is_all_zero_and_non_vacuous(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.4, 6.5**

        六族全 0 是**判据**不是缺席：分母 = N 域 135 个生产文件（现算非空）。
        """
        files = _n_cycle_files()
        scan = manifest_slice["dynamic_row_identity"]["hardcoded_pattern_scan"]
        assert set(scan["patterns"]) == set(_HARDCODED), (
            sorted(scan["patterns"]), sorted(_HARDCODED))
        for name, pattern in scan["patterns"].items():
            assert pattern == _HARDCODED[name], (name, pattern, _HARDCODED[name])
            hits = _hardcoded_hits(files, name)
            assert scan["hits"][name] == hits, (name, scan["hits"][name], hits)
            assert hits == [], (name, hits)
        c = scan["counters"]
        assert c["hardcoded_patterns_total"] == len(_HARDCODED)
        assert c["hardcoded_patterns_at_zero"] == len(_HARDCODED)
        assert c["hardcoded_pattern_hits_total"] == 0
        assert len(files) >= 100, "分母可疑 ⇒ 全 0 没有意义"


# ════════════════════════════════════════════════════════════════════════════
# 判据六：N 循环形态差异（ND-1..ND-8 逐条现算）
# ════════════════════════════════════════════════════════════════════════════
class TestNCycleFormDifferences:

    def test_all_differences_carry_a_recompute_recipe(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4**"""
        diffs = manifest_slice["n_cycle_form_differences"]
        assert diffs, "形态差异清单为空 ⇒ 本节空跑"
        ids = [d["id"] for d in diffs]
        assert ids == sorted(ids) and len(ids) == len(set(ids)), ids
        for d in diffs:
            for field in ("what", "why_not_copyable", "recompute_recipe", "value"):
                assert d.get(field), (d["id"], field)
        assert manifest_slice["honest_adjudication_summary"][
            "n_cycle_form_differences"] == len(diffs)

    def test_nd2_three_carrier_kinds_partition_the_hosts(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4**

        ND-2：三种载体形态。判据是**互补划分** —— import 载体模块的宿主与内联载体的宿主
        不重不漏，且 N 域**没有任何** `*EntryDualMode.ts`（M 的形态在 N 上不存在）。
        """
        def family(kind: str) -> str:
            """三个**载体族**（inert / real 都属 host_inline，是开关结论上的差别不是载体族）。"""
            return "host_inline" if kind.startswith("host_inline") else kind

        kinds: dict[str, list[str]] = {}
        for e in manifest_slice["independent_entries"]:
            kinds.setdefault(family(e["dual_mode_carrier"]["kind"]), []).append(e["entry_id"])
        assert len(kinds) == 3, kinds
        assert set(kinds) == {"host_inline", "per_entry_composable_three_modes",
                             "per_entry_wrapper_over_shared_base"}, sorted(kinds)
        for e in manifest_slice["independent_entries"]:
            carrier = e["dual_mode_carrier"]
            body = _strip_comments(_cached_text(ROOT / e["host_path"]))
            imports = bool(re.search(r"useN\dDualMode", body))
            # 🔴 判「内联」不能只看 `const dualMode =` —— N1 的 live 载体也长这样
            # （`const dualMode = useN1DualMode({...})`）。内联的两种真实形态是
            # **对象字面量**（N4/N5）与**裸 ref 三件套**（N3）。
            inline = bool(
                re.search(r"^\s*const dualMode\s*=\s*\{", body, re.M)
                or re.search(r"^\s*const renderMode\s*=\s*ref", body, re.M)
            )
            if carrier["kind"].startswith("host_inline"):
                assert inline and not imports, (e["entry_id"], imports, inline)
                assert carrier["module"] is None
            else:
                assert imports and not inline, (e["entry_id"], imports, inline)
                assert (ROOT / carrier["module"]).is_file()
                assert "useN" in _line_at(carrier["import_site"])
        assert list(WP_COMPOSABLES.glob("useN*EntryDualMode.ts")) == [], (
            "N 域出现了 M 式 `*EntryDualMode.ts` ⇒ ND-2 的形态判断要重做"
        )
        nd2 = next(d for d in manifest_slice["n_cycle_form_differences"] if d["id"] == "ND-2")
        assert nd2["value"] == len(kinds)

    def test_nd3_inert_switches_are_noop_callbacks(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.4, 12.9**

        ND-3：inert 的判据是「回调是空实现」+「mode 只有初始赋值」，
        **不是**「载体模块不可达」（那是 L 的形态）。
        """
        ms = manifest_slice["mode_switch_resolution"]
        inert = sorted(eid for eid, v in ms["per_entry_verdict"].items() if v == "inert")
        computed: list[str] = []
        for e in manifest_slice["independent_entries"]:
            body = _strip_comments(_cached_text(ROOT / e["host_path"]))
            if re.search(r"onModeChange\s*:\s*\(\)\s*=>\s*\{\s*\}", body):
                computed.append(e["entry_id"])
        assert sorted(computed) == inert, (sorted(computed), inert)
        for ev in ms["inert_evidence"]:
            assert re.search(r"onModeChange\s*:\s*\(\)\s*=>\s*\{\s*\}",
                             _line_at(ev["noop_callback_site"])), ev
            assert "const dualMode" in _line_at(ev["inline_carrier_site"]), ev
            mode_line = _line_at(ev["mode_ref_site"])
            assert "currentMode" in mode_line and "ref<" in mode_line, mode_line
            host_body = _strip_comments(_cached_text(_path_of(ev["mode_ref_site"])))
            # 🔴 `=(?!=)`：`currentMode.value === 'onlyoffice'`（模板门控）**不是**赋值。
            # 不排除它，这条反向判据会把每个 inert 宿主都判成「有赋值」。
            assert not re.search(r"currentMode\.value\s*=(?!=)", host_body), (
                f"{ev['entry_id']} 的 currentMode 有赋值 ⇒ 它不是 inert"
            )
            block = _oo_mount_block(host_body, _line_no_of(ev["mode_gated_oo_mount_site"]))
            assert "<GtOnlyOfficeSheet" in block, ev
            assert "currentMode" in block and "onlyoffice" in block, block
        assert ms["counters"]["entries_with_inert_switch"] == len(inert)
        nd3 = next(d for d in manifest_slice["n_cycle_form_differences"] if d["id"] == "ND-3")
        assert nd3["value"] == len(inert)

    def test_nd4_exactly_one_host_calls_the_legacy_health_endpoint(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        ND-4：M/L 两轮都是 0；照抄「无宿主直调」必假红。两侧都验：既算总数，也算逐 entry。
        """
        hits: dict[str, list[int]] = {}
        for e in manifest_slice["independent_entries"]:
            body = _strip_comments(_cached_text(ROOT / e["host_path"]))
            lines = [i for i, line in enumerate(body.split("\n"), 1)
                     if "/api/workpapers/onlyoffice/health" in line]
            if lines:
                hits[e["entry_id"]] = lines
        assert list(hits) == ["xlsx/gt-n3-deferred-tax-liabilities"], hits
        assert hits["xlsx/gt-n3-deferred-tax-liabilities"] == [180], hits
        assert manifest_slice["orphan_dual_mode_inventory"]["counters"][
            "hosts_calling_legacy_health_endpoint_directly"] == len(hits)
        nd4 = next(d for d in manifest_slice["n_cycle_form_differences"] if d["id"] == "ND-4")
        assert nd4["value"] == len(hits)

    def test_nd6_dirty_sheet_name_literals_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.10**"""
        audit = manifest_slice["sheet_granularity_and_router_audit"]
        dirty = audit["dirty_sheet_name_literals"]
        assert dirty, "脏字面量清单为空 ⇒ 本条空跑"
        for item in dirty:
            names = _sheet_names(N_TEMPLATE_DIR / item["workbook"])
            assert item["sheet"] in names, item
            if item["defect"] == "trailing_space":
                assert item["sheet"] != item["sheet"].rstrip()
                assert item["sheet"].rstrip() not in names
            elif item["defect"] == "missing_closing_paren":
                assert item["sheet"].count("（") == item["sheet"].count("）") + 1
                assert item["sheet"] + "）" not in names
            else:
                raise AssertionError(f"未登记的脏字面量类型：{item['defect']}")
        assert audit["counters"]["dirty_sheet_name_literals"] == len(dirty)
        nd6 = next(d for d in manifest_slice["n_cycle_form_differences"] if d["id"] == "ND-6")
        assert nd6["value"] == len(dirty)

    def test_nd7_sheet_code_collisions_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.10**

        ND-7：`N3A` 一码两册；`O1A`/`O2A` 出现在 N 册。两侧都验。
        """
        audit = manifest_slice["sheet_granularity_and_router_audit"]["sheet_code_collision_audit"]
        code_to_books: dict[str, set[str]] = {}
        for e in manifest_slice["independent_entries"]:
            wb = e["template_ref"]["workbook"]
            for name in _sheet_names(N_TEMPLATE_DIR / wb):
                # 🔴 不能用 `\b`：CJK 字符在 Python 里算 `\w`，`程序表N3A` 的 N 前面没有词边界
                # ⇒ 用 `\b([A-Z]\d+[A-Z])\b` 会 0 命中，碰撞判据恒真。
                for m in re.finditer(r"(?<![A-Za-z0-9])([A-Z]\d+[A-Z])(?![A-Za-z0-9])", name):
                    code_to_books.setdefault(m.group(1), set()).add(wb)
        assert code_to_books, "sheet 码现算为空 ⇒ 碰撞判据空跑"
        colliding = sorted(c for c, books in code_to_books.items() if len(books) > 1)
        declared = [c["code"] for c in audit["collisions"]]
        assert sorted(declared) == colliding, (declared, colliding)
        for c in audit["collisions"]:
            assert sorted(c["workbooks"]) == sorted(code_to_books[c["code"]])
        foreign = sorted(
            (c, sorted(books)) for c, books in code_to_books.items() if not c.startswith("N"))
        declared_foreign = sorted(
            (f["code"], [f["workbook"]]) for f in audit["foreign_letter_codes_in_n_workbooks"])
        assert declared_foreign == foreign, (declared_foreign, foreign)
        assert audit["counters"]["colliding_codes"] == len(colliding)
        assert audit["counters"]["foreign_letter_codes"] == len(foreign)
        nd7 = next(d for d in manifest_slice["n_cycle_form_differences"] if d["id"] == "ND-7")
        assert nd7["value"] == len(colliding) + len(foreign)


# ════════════════════════════════════════════════════════════════════════════
# 判据七：orphan 清册（AC 1.7）
# ════════════════════════════════════════════════════════════════════════════
class TestOrphanInventory:

    def test_declared_orphans_are_unreachable_and_the_set_matches(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.7**

        🔴 ND-5：orphan 全集用**可达性**现算（不是只扫 dual-mode 命名），
        与声明做**有序等值 + 无重复**双断言。
        """
        inv = manifest_slice["orphan_dual_mode_inventory"]
        declared = [m["file"] for m in inv["modules"]] + [
            m["file"] for m in inv["orphan_non_dual_mode_modules"]]
        assert len(declared) == len(set(declared)), declared
        computed: list[str] = []
        for module in _n_composables():
            prod, _ = _statement_edges_to(module)
            if not prod:
                computed.append(_rel(module))
        assert sorted(declared) == sorted(computed), (sorted(declared), sorted(computed))
        for m in inv["modules"] + inv["orphan_non_dual_mode_modules"]:
            path = ROOT / m["file"]
            assert path.is_file(), m["file"]
            assert m["lines"] == len(_cached_text(path).splitlines()), m["file"]
            assert m.get("production_consumers") in (0, [])

    def test_live_modules_edges_match_the_declared_value_both_ways(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.7**

        两侧都验（Task 54 的 M20 教训：只验「现算为 0」会让「声明 1、实际 0」通过）。
        """
        inv = manifest_slice["orphan_dual_mode_inventory"]
        for m in inv["live_modules"]:
            prod, _ = _statement_edges_to(ROOT / m["file"])
            assert sorted(m["production_consumers"]) == prod, (m["file"],
                                                               m["production_consumers"], prod)
            assert len(prod) > 0
            assert m["lines"] == len(_cached_text(ROOT / m["file"]).splitlines())

    def test_orphans_are_all_first_order_because_there_is_no_barrel(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.7**"""
        inv = manifest_slice["orphan_dual_mode_inventory"]
        assert not (WP_COMPOSABLES / "index.ts").exists(), "出现 barrel ⇒ 一阶结论要重算"
        assert inv["counters"]["orphan_barrels"] == 0
        assert inv["counters"]["orphan_dual_mode_second_order"] == 0
        assert inv["counters"]["orphan_dual_mode_first_order"] == inv["counters"][
            "orphan_dual_mode_modules"]

    def test_dual_mode_module_files_partition_into_orphan_and_live(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.7**"""
        inv = manifest_slice["orphan_dual_mode_inventory"]
        on_disk = sorted(_rel(p) for p in WP_COMPOSABLES.glob("useN*DualMode.ts"))
        orphan = sorted(m["file"] for m in inv["modules"])
        live = sorted(m["file"] for m in inv["live_modules"])
        assert not (set(orphan) & set(live))
        assert sorted(orphan + live) == on_disk, (sorted(orphan + live), on_disk)
        c = inv["counters"]
        assert c["dual_mode_module_files_total"] == len(on_disk)
        assert c["orphan_dual_mode_modules"] == len(orphan)
        assert c["live_dual_mode_modules"] == len(live)

    def test_the_v1_v2_twins_are_real_twins(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.7**

        ND-5 的关键一条：V2 是 orphan、V1 是 live（不是两个都 orphan、也不是两个都 live）。
        """
        inv = manifest_slice["orphan_dual_mode_inventory"]
        twins = [m for m in inv["orphan_non_dual_mode_modules"] if m["kind"] == "v1_v2_twin"]
        assert len(twins) == 2, twins
        for m in twins:
            assert m["live_twin"], m
            live = ROOT / m["live_twin"]
            assert live.is_file(), m["live_twin"]
            prod_live, _ = _statement_edges_to(live)
            assert prod_live, f"{m['live_twin']} 竟然也没有生产边 ⇒ V1/V2 的判断要重做"
            prod_orphan, _ = _statement_edges_to(ROOT / m["file"])
            assert prod_orphan == []
        assert inv["counters"]["orphan_v1_v2_twins"] == len(twins)

    def test_orphan_storage_keys_are_wp_unscoped_unlike_the_live_one(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.7**

        🔴 与 M 相反：M 的 live 路径 localStorage 键数为 0；N 的 live 路径有 1 个
        （N1 的 `n1-dual-mode:${wpId}`，按 wpId 分隔），而 3 个 orphan 的键**未按 wpId 分隔**。
        """
        inv = manifest_slice["orphan_dual_mode_inventory"]
        for m in inv["modules"]:
            body = _strip_comments(_cached_text(ROOT / m["file"]))
            assert m["localStorage_key"] in body, m["file"]
            assert m["storage_key_is_wp_scoped"] is False
            key_line = _line_at(m["localStorage_key_source_ref"])
            assert m["localStorage_key"] in key_line
            assert "wpId" not in key_line, (m["file"], key_line)
        live_n1 = next(m for m in inv["live_modules"] if m["file"].endswith("useN1DualMode.ts"))
        assert live_n1["storage_key_is_wp_scoped"] is True
        body = _strip_comments(_cached_text(ROOT / live_n1["file"]))
        assert re.search(r"\$\{STORAGE_KEY_PREFIX\}:\$\{wpId\.value\}", body), (
            "N1 的 live 键不再按 wpId 分隔 ⇒ 判据前提变了"
        )
        c = inv["counters"]
        assert c["orphan_modules_with_wp_unscoped_storage_key"] == len(inv["modules"])
        assert c["live_modules_with_wp_unscoped_storage_key"] == 0
        assert c["live_modules_with_storage_key"] == 1

    def test_legacy_endpoint_call_counts_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4**"""
        inv = manifest_slice["orphan_dual_mode_inventory"]
        c = inv["counters"]
        orphan_health = [m["file"] for m in inv["modules"]
                         if "/api/workpapers/onlyoffice/health"
                         in _strip_comments(_cached_text(ROOT / m["file"]))]
        assert c["orphan_modules_calling_legacy_health_endpoint"] == len(orphan_health)
        live_health = [m["file"] for m in inv["live_modules"]
                       if "/api/workpapers/onlyoffice/health"
                       in _strip_comments(_cached_text(ROOT / m["file"]))]
        assert c["live_modules_calling_legacy_health_endpoint"] == len(live_health)
        config = [m["file"] for m in inv["modules"] + inv["live_modules"]
                  if "onlyoffice-config" in _strip_comments(_cached_text(ROOT / m["file"]))]
        assert c["dual_mode_modules_calling_legacy_config_endpoint"] == len(config)

    def test_shared_base_edges_recompute_and_are_not_copied_from_m(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.7, 12.4**

        🔴 **不得照抄 M 那轮的 29**：本轮同口径现算，两栏（生产/测试）都验。
        """
        sb = manifest_slice["orphan_dual_mode_inventory"]["shared_base_preserved"]
        prod, test = _statement_edges_to(SHARED_BASE)
        assert sb["statement_production_consumers"] == len(prod), (
            sb["statement_production_consumers"], len(prod))
        assert sb["statement_test_consumers"] == len(test), (
            sb["statement_test_consumers"], len(test))
        assert sb["statement_consumers_total"] == len(prod) + len(test)
        n_edges = [r for r in prod if re.search(r"useN\d|GtN\d", r)]
        assert sorted(sb["n_cycle_consumer_sites"]) == sorted(n_edges), (
            sb["n_cycle_consumer_sites"], n_edges)
        assert sb["n_cycle_consumers"] == len(n_edges)
        assert sb["consumers_after_rewiring"] == len(prod) - len(n_edges)
        assert sb["consumers_after_rewiring"] > 0, "判据不得写成「删完剩 0」"
        assert "不得照抄" in sb["recompute_note"]

    def test_orphan_counters_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.7**"""
        inv = manifest_slice["orphan_dual_mode_inventory"]
        c = inv["counters"]
        dual = inv["modules"]
        other = inv["orphan_non_dual_mode_modules"]
        live = inv["live_modules"]
        assert c["orphan_dual_mode_lines_total"] == sum(m["lines"] for m in dual)
        assert c["orphan_non_dual_mode_lines_total"] == sum(m["lines"] for m in other)
        assert c["live_dual_mode_lines_total"] == sum(m["lines"] for m in live)
        assert c["orphan_modules_total"] == len(dual) + len(other)
        assert c["orphan_lines_total"] == (c["orphan_dual_mode_lines_total"]
                                          + c["orphan_non_dual_mode_lines_total"])
        assert c["orphan_non_dual_mode_modules"] == len(other)
        assert c["orphan_modules_with_fabricated_key_shape"] == len(
            [m for m in other if m.get("fabricated_key")])
        inline_hosts = [
            e["entry_id"] for e in manifest_slice["independent_entries"]
            if e["dual_mode_carrier"]["kind"].startswith("host_inline")
        ]
        assert c["hosts_with_inline_dual_mode"] == len(inline_hosts)
        obj_literal = [
            e["entry_id"] for e in manifest_slice["independent_entries"]
            if re.search(r"^\s*const dualMode\s*=\s*\{", _strip_comments(
                _cached_text(ROOT / e["host_path"])), re.M)
        ]
        assert c["hosts_with_inline_dual_mode_object_literal"] == len(obj_literal)


# ════════════════════════════════════════════════════════════════════════════
# 判据八：sheet 粒度与 router（AC 12.4 / 6.10）
# ════════════════════════════════════════════════════════════════════════════
#: Python 侧等价复算 `composables/shared/cycleSheetRouting.ts` 的 `makeCycleSheetRouter`。
#: 🔴 常量与正则**从源码现读**（见 `_router_opts` / `_soe_tokens`），不是抄一份到这里。
def _soe_tokens() -> list[str]:
    body = _cached_text(SHARED_ROUTER)
    m = re.search(r"SOE_TOKENS\s*=\s*\[([^\]]*)\]", body)
    assert m, "找不到 SOE_TOKENS"
    return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]


def _shared_router_constants() -> dict[str, str]:
    body = _cached_text(SHARED_ROUTER)
    out = {}
    for name in ("SHEET_DISCLOSURE_LISTED", "SHEET_DISCLOSURE_SOE", "SHEET_INDEX"):
        m = re.search(rf"{name}\s*=\s*'([^']+)'", body)
        assert m, name
        out[name] = m.group(1)
    return out


def _router_opts(module_name: str) -> dict[str, Any]:
    body = _cached_text(WP_COMPOSABLES / module_name)
    code = re.search(r"codeRe:\s*/(.+?)/,", body)
    html = re.search(r"htmlCodeRe:\s*/(.+?)/,", body)
    bare = re.search(r"bareCodes:\s*\[([^\]]*)\]", body)
    early = re.findall(r"normalized === '([^']+)'", body)
    assert code and html, module_name
    return {
        "codeRe": code.group(1),
        "htmlCodeRe": html.group(1),
        "bare": [x.strip().strip("'\"") for x in (bare.group(1).split(",") if bare else [])
                 if x.strip()],
        "early_false": early,
    }


def _host_skips(host: str) -> list[str]:
    body = _strip_comments(_cached_text(WP_COMPONENTS / host))
    m = re.search(r"SKIP_SHEETS\s*=\s*\[([^\]]*)\]", body)
    return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()] if m else []


def _shared_normalize(name: str, code_re: str) -> str:
    k = _shared_router_constants()
    if "附注" in name:
        if "上市" in name:
            return k["SHEET_DISCLOSURE_LISTED"]
        if any(t in name for t in _soe_tokens()):
            return k["SHEET_DISCLOSURE_SOE"]
    if "底稿目录" in name:
        return k["SHEET_INDEX"]
    m = re.search(code_re, name)
    return m.group(1) if m else name


def _shared_is_html(norm: str, html_re: str, bare: list[str]) -> bool:
    k = _shared_router_constants()
    return bool(re.search(html_re, norm)) or norm in bare or norm in (
        k["SHEET_INDEX"], k["SHEET_DISCLOSURE_LISTED"], k["SHEET_DISCLOSURE_SOE"])


def _n1_normalize(name: str) -> str:
    if name == "GT_Custom":
        return "skip"
    m = re.search(r"N1-[1-5]", name)
    if m:
        return m.group(0)
    if re.search(r"N1A", name) or "程序表" in name:
        return "procedure"
    if "上市公司" in name:
        return "disclosure-listed"
    if "国企" in name or "国有企业" in name:
        return "disclosure-soe"
    if "底稿目录" in name or name in ("N1", ""):
        return "index"
    return name


def _n3_normalize(name: str) -> str:
    m = re.search(r"(N3A|N3-\d+|N3)", name)
    if m:
        return m.group(1)
    return "底稿目录" if "底稿目录" in name else name


def _oo_mount_block(body: str, tag_start_line: int) -> str:
    """从 `<GtOnlyOfficeSheet` 标签起始行取到它的闭合 `/>`（Vue 多行标签）。

    🔴 门控表达式（`v-if=…`）在**下一行**，只看标签起始那一行会把每个门控判据打红。
    """
    lines = body.split("\n")
    out = []
    for line in lines[tag_start_line - 1:tag_start_line + 19]:
        out.append(line)
        if "/>" in line or "</GtOnlyOfficeSheet>" in line:
            break
    return "\n".join(out)


class TestSheetGranularityAndRouter:

    def test_the_python_port_matches_the_declared_normalization(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        自检：Python 侧等价复算必须逐张 sheet 重现 slice 声明的 `normalized`。
        端口错了后面全部覆盖面判据一起假。
        """
        for e in manifest_slice["independent_entries"]:
            code = _code_of_entry(e)
            rows = e["sheet_granularity"]["per_sheet"]
            if code == "N1":
                got = [_n1_normalize(r["sheet"]) for r in rows]
            elif code == "N3":
                got = [_n3_normalize(r["sheet"]) for r in rows]
            else:
                opts = _router_opts(f"{code.lower()}SheetRouting.ts")
                got = [_shared_normalize(r["sheet"], opts["codeRe"]) for r in rows]
            assert got == [r["normalized"] for r in rows], (code, got)

    def test_per_sheet_table_equals_the_workbook_sheet_list(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.10, 12.4** —— 有序等值（顺序也是事实）。"""
        for e in manifest_slice["independent_entries"]:
            names = _sheet_names(N_TEMPLATE_DIR / e["template_ref"]["workbook"])
            declared = [r["sheet"] for r in e["sheet_granularity"]["per_sheet"]]
            assert declared == names, (e["entry_id"], declared, names)
            assert len(declared) == len(set(declared))

    def test_classification_is_a_closed_enum_and_renderers_exist(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        `html_child` / `html_program_console` 必须指到真实存在的组件文件；
        `oo_fallthrough` 必须给出四类之一的原因（无 `other` 兜底桶）。
        """
        audit = manifest_slice["sheet_granularity_and_router_audit"]
        allowed = set(audit["classification_enum"])
        reasons = set(audit["oo_fallthrough_classification"]["enum"])
        for e in manifest_slice["independent_entries"]:
            for r in e["sheet_granularity"]["per_sheet"]:
                assert r["classification"] in allowed, r
                if r["classification"] == "oo_fallthrough":
                    assert r["renderer"] is None
                    assert r["oo_reason"] in reasons, r
                else:
                    assert r["oo_reason"] is None
                    assert r["renderer"], r
                    cand = WP_COMPONENTS / r["renderer"]
                    assert cand.is_file(), (e["entry_id"], r["renderer"])

    def test_html_children_are_really_dispatched_by_the_host(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4**

        渲染层判据：声明的每个 `html_child` 组件必须在宿主里有**真实模块边**
        （不是符号名 grep）—— 只声明而模板零引用就是结构性死代码（G7 两级表头同型缺陷）。
        """
        for e in manifest_slice["independent_entries"]:
            host_body = _strip_comments(_cached_text(ROOT / e["host_path"]))
            for r in e["sheet_granularity"]["per_sheet"]:
                if r["classification"] == "oo_fallthrough":
                    continue
                comp = WP_COMPONENTS / r["renderer"]
                stem = comp.stem
                assert stem in host_body, (e["entry_id"], r["renderer"])
                assert re.search(rf"<{stem}\b", host_body), (
                    f"{e['entry_id']} 声明了 {stem} 却没有在模板里挂载 ⇒ 结构性死代码"
                )

    def test_sheet_coverage_counters_recompute_three_ways(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.10, 12.4**"""
        audit = manifest_slice["sheet_granularity_and_router_audit"]
        c = audit["counters"]
        rows = [r for e in manifest_slice["independent_entries"]
                for r in e["sheet_granularity"]["per_sheet"]]
        total = sum(len(_sheet_names(N_TEMPLATE_DIR / e["template_ref"]["workbook"]))
                    for e in manifest_slice["independent_entries"])
        assert c["authoritative_sheets_total"] == total == len(rows)
        html = [r for r in rows if r["classification"] == "html_child"]
        console = [r for r in rows if r["classification"] == "html_program_console"]
        oo = [r for r in rows if r["classification"] == "oo_fallthrough"]
        assert c["sheets_covered_by_html_child"] == len(html)
        assert c["sheets_rendered_by_program_console"] == len(console)
        assert c["sheets_falling_through_to_oo"] == len(oo)
        assert c["sheets_covered_by_html_side_total"] == len(html) + len(console)
        assert c["authoritative_sheets_total"] == (
            c["sheets_covered_by_html_side_total"] + c["sheets_falling_through_to_oo"])
        reason_counts: dict[str, int] = {}
        for r in oo:
            reason_counts[r["oo_reason"]] = reason_counts.get(r["oo_reason"], 0) + 1
        declared = audit["oo_fallthrough_classification"]["counts"]
        assert declared == reason_counts, (declared, reason_counts)
        assert set(declared) <= set(audit["oo_fallthrough_classification"]["enum"])
        for e in manifest_slice["independent_entries"]:
            sg = e["sheet_granularity"]
            per = sg["per_sheet"]
            assert sg["authoritative_sheet_count"] == len(per)
            assert sg["sheets_covered_by_html_child"] == len(
                [r for r in per if r["classification"] == "html_child"])
            assert sg["sheets_rendered_by_program_console"] == len(
                [r for r in per if r["classification"] == "html_program_console"])
            assert sg["sheets_falling_through_to_oo"] == [
                r["sheet"] for r in per if r["classification"] == "oo_fallthrough"]

    def test_router_kind_split_is_real(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4** —— BP-10 的前提：N1/N3 未采用共享路由。"""
        audit = manifest_slice["sheet_granularity_and_router_audit"]
        shared, inline = [], []
        for e in manifest_slice["independent_entries"]:
            sg = e["sheet_granularity"]
            body = _strip_comments(_cached_text(ROOT / e["host_path"]))
            uses_shared = bool(re.search(r"SheetRouting", body))
            if sg["router_kind"] == "shared_cycle_sheet_router":
                assert uses_shared, e["entry_id"]
                assert (ROOT / sg["router_module"]).is_file()
                prod, _ = _statement_edges_to(ROOT / sg["router_module"])
                assert any(e["host"] in ref for ref in prod), (e["entry_id"], prod)
                shared.append(e["entry_id"])
            else:
                assert not uses_shared, e["entry_id"]
                assert sg["router_module"] is None
                inline.append(e["entry_id"])
        assert audit["counters"]["hosts_using_shared_cycle_sheet_router"] == len(shared)
        assert audit["counters"]["hosts_using_host_inline_regex"] == len(inline)
        bp10 = next(b for b in manifest_slice["blocking_preconditions"] if b["id"] == "BP-10")
        assert sorted(bp10["entries"]) == sorted(inline)

    def test_n1_host_runs_the_code_regex_before_the_disclosure_check(self) -> None:
        """**Validates: Requirements 12.4** —— BP-10 的正面判据（形态在源码里真存在）。"""
        body = _strip_comments(_cached_text(WP_COMPONENTS / "GtN1DeferredTaxAssets.vue"))
        lines = body.split("\n")
        code_line = next(i for i, l in enumerate(lines, 1) if "N1-[1-5]" in l)
        disclosure_line = next(i for i, l in enumerate(lines, 1) if "上市公司" in l)
        assert code_line < disclosure_line, (
            "N1 宿主的披露判定已前置 ⇒ BP-10 该解除了（这条应改成 XPASS 提醒）"
        )

    def test_verdict_does_not_overclaim(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.9**"""
        verdict = manifest_slice["sheet_granularity_and_router_audit"]["verdict"]
        assert "single_html" in verdict and "不成立" in verdict
        assert "缺陷登记" in verdict, "verdict 必须写明「有 OO 承载 ≠ OO 可定位」"


# ════════════════════════════════════════════════════════════════════════════
# 判据九：模式开关与 AC 1.4（Property 3 的 UI 侧）
# ════════════════════════════════════════════════════════════════════════════
class TestModeSwitchResolution:

    def test_per_entry_verdicts_are_from_a_closed_enum(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.4**"""
        ms = manifest_slice["mode_switch_resolution"]
        allowed = set(ms["verdict_allowed_values"])
        assert set(ms["per_entry_verdict"].values()) <= allowed
        assert set(ms["per_entry_verdict"]) == {
            e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert ms["verdict_is_binary"] is False
        for e in manifest_slice["independent_entries"]:
            assert e["dual_mode_carrier"]["switch_verdict"] == ms["per_entry_verdict"][
                e["entry_id"]]

    def test_redeemable_switch_has_all_three_elements(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.4**

        三要素：`<el-segmented>` + mode 门控的 OO 挂载点 + 真会改 mode 的回调。
        """
        ms = manifest_slice["mode_switch_resolution"]
        redeemable = [eid for eid, v in ms["per_entry_verdict"].items() if v == "redeemable"]
        assert redeemable, "redeemable 集合为空 ⇒ 判据空跑"
        for eid in redeemable:
            e = next(x for x in manifest_slice["independent_entries"] if x["entry_id"] == eid)
            body = _strip_comments(_cached_text(ROOT / e["host_path"]))
            gate = e["ui_toolbar_gate"]
            assert "<el-segmented" in body.split("\n")[gate["segmented_sites_in_gate"][0] - 1]
            assert gate["mode_gated_oo_mount_sites"], eid
            for n in gate["mode_gated_oo_mount_sites"]:
                block = _oo_mount_block(body, n)
                assert "<GtOnlyOfficeSheet" in block, (eid, n)
                assert "onlyoffice" in block or "isOnlyOffice" in block, (eid, block)
            assert not re.search(r"onModeChange\s*:\s*\(\)\s*=>\s*\{\s*\}", body), eid

    def test_ui_toolbar_gate_anchors_are_resolvable(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.4**"""
        for e in manifest_slice["independent_entries"]:
            gate = e["ui_toolbar_gate"]
            assert "<el-segmented" in _line_at(gate["anchor"])
            assert gate["anchor_absent_because"] is None
            body = _strip_comments(_cached_text(ROOT / e["host_path"])).split("\n")
            computed = [i for i, l in enumerate(body, 1) if "<el-segmented" in l]
            assert gate["segmented_sites_in_gate"] == computed, (e["entry_id"], computed)
            oo = [i for i, l in enumerate(body, 1) if "<GtOnlyOfficeSheet" in l]
            assert gate["oo_mount_sites"] == oo, (e["entry_id"], gate["oo_mount_sites"], oo)
            assert e["mount_count"] == len(oo), (e["entry_id"], e["mount_count"], len(oo))

    def test_switch_counters_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.4**"""
        ms = manifest_slice["mode_switch_resolution"]
        c = ms["counters"]
        verdicts = list(ms["per_entry_verdict"].values())
        assert c["entries_with_redeemable_switch"] == verdicts.count("redeemable")
        assert c["entries_with_inert_switch"] == verdicts.count("inert")
        assert c["entries_with_no_switch_at_all"] == verdicts.count("no_switch")
        assert sum((c["entries_with_redeemable_switch"], c["entries_with_inert_switch"],
                    c["entries_with_no_switch_at_all"])) == len(verdicts)
        assert c["hosts_with_segmented_site"] == len(
            [e for e in manifest_slice["independent_entries"]
             if e["ui_toolbar_gate"]["segmented_sites_in_gate"]])
        assert c["hosts_with_oo_mount"] == len(
            [e for e in manifest_slice["independent_entries"]
             if e["ui_toolbar_gate"]["oo_mount_sites"]])
        assert c["hosts_claiming_bidirectional_in_template"] == 0


# ════════════════════════════════════════════════════════════════════════════
# 判据十：Property 69（evidence 与计数）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty69EvidenceAndCounters:

    def test_unverifiable_entries_carry_non_empty_reasons(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.10** —— SR-7。"""
        for e in manifest_slice["independent_entries"]:
            ev = e["evidence"]
            assert ev["verification_state"] == "UNVERIFIABLE", e["entry_id"]
            assert isinstance(ev["unverifiable_reasons"], list) and ev["unverifiable_reasons"]
        assert manifest_slice["honest_adjudication_summary"][
            "entries_left_unverifiable"] == len(manifest_slice["independent_entries"])

    def test_no_entry_claims_verified_without_a_run(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.10, 12.11, 14.1**"""
        for e in manifest_slice["independent_entries"]:
            ev = e["evidence"]
            assert ev["sync_test_run_id"] is None
            assert ev["required_scenario_set_digest"] is None
            assert ev["browser_case"] is None
            assert ev["contract_test"] == _rel(_THIS)

    def test_entry_scoped_bp_appears_only_in_its_own_reasons(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.10**

        两侧都验：BP 出现在它自己的 entry 的 reasons 里，且**不**出现在别人的。
        """
        by_id = {b["id"]: set(b["entries"]) for b in manifest_slice["blocking_preconditions"]}
        for e in manifest_slice["independent_entries"]:
            joined = "\n".join(e["evidence"]["unverifiable_reasons"])
            for bp_id, owners in by_id.items():
                mentioned = bool(re.search(rf"{bp_id}[：:]", joined))
                expected = e["entry_id"] in owners
                assert mentioned == expected, (e["entry_id"], bp_id, mentioned, expected)

    def test_summary_counters_recompute_from_the_entries(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.10**"""
        entries = manifest_slice["independent_entries"]
        s = manifest_slice["honest_adjudication_summary"]
        assert s["total_independent"] == len(entries)
        assert s["capability_verdict_pending"] == len([e for e in entries
                                                       if e["capability"] is None])
        assert s["html_counterpart_exists"] == len(
            [e for e in entries if e["html_counterpart_verdict"] == "exists"])
        assert s["html_counterpart_none"] == len(
            [e for e in entries if e["html_counterpart_verdict"] == "none"])
        for cap in ("bidirectional", "single_onlyoffice", "single_html", "unreachable"):
            assert s[f"adjudicated_as_{cap}"] == len(
                [e for e in entries if e["capability"] == cap])
        assert s["finalized_published_representations"] == len(
            [e for e in entries if e["published_representation"]])

    def test_template_counters_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.10, 12.10**"""
        s = manifest_slice["honest_adjudication_summary"]
        files = manifest_slice["authoritative_templates"]["files"]
        assert s["authoritative_template_files"] == len(files)
        assert s["authoritative_template_sheets_total"] == sum(f["sheet_count"] for f in files)
        assert s["authoritative_formula_cells_total"] == sum(f["formula_cells"] for f in files)
        assert s["authoritative_sheets_with_formula"] == sum(
            f["sheets_with_formula"] for f in files)
        owners = [f["belongs_to_entry"] for f in files]
        assert s["template_files_with_owner_entry"] == len([o for o in owners if o])
        assert s["template_files_without_owner_entry"] == len([o for o in owners if not o])
        for f in files:
            path = N_TEMPLATE_DIR / f["name"]
            assert f["sheet_names"] == _sheet_names(path), f["name"]

    def test_counting_notes_cover_every_summary_counter(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.10**

        🔴 元判据（Task 54 的 M28/M29 教训）：`counting_notes` 各族的并集必须**覆盖**
        summary 的全部数值键 —— 漏一族就等于那族可以随便填。
        """
        s = manifest_slice["honest_adjudication_summary"]
        notes = s["counting_notes"]
        covered: set[str] = set()
        for key, value in notes.items():
            if key == "why_this_key_exists":
                continue
            assert isinstance(value, list) and value, key
            covered |= set(value)
        numeric = {k for k, v in s.items() if isinstance(v, int)}
        missing = sorted(numeric - covered)
        assert missing == [], f"summary 有 {len(missing)} 个计数没有来源节声明：{missing}"
        stale = sorted(covered - numeric)
        assert stale == [], f"counting_notes 声明了不存在的计数：{stale}"

    def test_slice_counters_are_all_zero_except_unadjudicated(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.10, 12.13** —— SR-9。"""
        entries = manifest_slice["independent_entries"]
        counters = manifest_slice["honest_adjudication_summary"]["slice_counters"]
        assert counters["unadjudicated"] == len([e for e in entries if e["capability"] is None])
        for key in ("fake_bidirectional_claimed_verified", "bidirectional_unverified",
                    "stale_evidence"):
            assert counters[key] == 0, key
        assert "不得" in counters["note"]

    def test_property_denominators_declare_what_is_not_claimed(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.10, 12.12**

        分母为空的部分必须显式 `not_claimed_passing` 并给出承载者。
        """
        denom = manifest_slice["property_denominators"]
        for key in ("property_3", "property_23", "property_69", "property_70"):
            block = denom[key]
            assert block["what_it_asserts"] and block["n_cycle_denominator"]
            assert block["how_handled"]
            assert "not_claimed_passing" in block
            if block["not_claimed_passing"]:
                assert block.get("not_claimed_passing_part")
                assert block.get("carrier_for_the_empty_part") or key == "property_69"
        assert denom["not_claimed_at_all"], "「完全不宣称」清单为空 ⇒ 空分母重言式的门没关上"
        declared = {p["property"] for p in manifest_slice["properties_verified"]}
        assert declared == {3, 23, 69, 70}, declared


# ════════════════════════════════════════════════════════════════════════════
# 判据十一：Property 70（跨 entry 隔离）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty70CrossEntryIsolation:

    def test_all_slices_are_pairwise_disjoint(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.12**

        🔴 配对数**现算** `C(n,2)`，不写死（M 那轮 10 份 45 对，N 那轮 11 份 55 对，
        Task 57 的 A/B/C/S slice 落盘后 12 份 66 对）。
        """
        paths = _slice_letters_on_disk()
        assert len(paths) >= 12, [p.name for p in paths]
        sets: dict[str, set[str]] = {}
        for p in paths:
            doc = _load(p)
            sets[p.name] = {e["entry_id"] for e in doc["independent_entries"]}
        names = sorted(sets)
        pairs = 0
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                pairs += 1
                assert not (sets[a] & sets[b]), (a, b, sorted(sets[a] & sets[b]))
        expected = len(sets) * (len(sets) - 1) // 2
        assert pairs == expected, (pairs, expected)
        recipe = manifest_slice["cross_entry_isolation"]["pairwise_recipe"]
        assert str(expected) in recipe, (
            f"pairwise_recipe 里的对数与现算 {expected} 不符 ⇒ 数字被写死了"
        )

    def test_sibling_slices_declared_match_the_disk(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.12**

        🔴 兄弟 slice 必须收全（有序等值 + 无重复）。Task 57 的 A/B/C/S slice 落盘后由十份
        变十一份 —— **事实陈述**随分母更新，判据强度（declared == disk 的有序等值）一字未动。
        """
        declared = manifest_slice["sibling_slices"]
        assert len(declared) == len(set(declared)), declared
        on_disk = sorted(_rel(p) for p in _slice_letters_on_disk() if p != SLICE_PATH)
        assert sorted(declared) == on_disk, (sorted(declared), on_disk)
        assert len(declared) == 11, f"兄弟 slice 应为十一份，实为 {len(declared)}"

    def test_cross_entry_isolation_assertions_are_present(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.12**"""
        ce = manifest_slice["cross_entry_isolation"]
        assert ce["rule"] and ce["assertions"]
        joined = "\n".join(ce["assertions"])
        for token in ("belongs_to_entry", "review.entry_id", "candidate", "registry",
                      "template_ref", "item_id"):
            assert token in joined, token
        assert set(ce["production_contract_files"]) == {
            p.name for p in CONTRACT_DIR.glob("*.json") if p.name != CANDIDATE_CONTRACT_FILE}
        assert ce["candidate_contract_files"] == [CANDIDATE_CONTRACT_FILE]

    def test_template_owner_mapping_is_a_bijection(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.12** —— SR-8。"""
        files = manifest_slice["authoritative_templates"]["files"]
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        owners = [f["belongs_to_entry"] for f in files]
        assert None not in owners
        assert len(set(owners)) == len(owners) == len(ids)
        assert set(owners) == ids
        on_disk = {p.name for p in N_TEMPLATE_DIR.iterdir() if not p.name.startswith("~$")}
        assert {f["name"] for f in files} == on_disk
        assert [p.name for p in N_TEMPLATE_DIR.iterdir() if p.name.startswith("~$")] == []
        assert manifest_slice["authoritative_templates"]["reference_copy_status"] == (
            "absent_on_this_machine")
        assert REFERENCE_COPY_DIR.is_dir() is False, (
            "参考副本目录出现了 ⇒ reference_copy_status 要改，并加两处比对"
        )

    def test_deletion_plan_paths_are_globally_unique_and_disjoint(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        """**Validates: Requirements 12.12**"""
        mine: set[str] = set()
        for m in (deletion_plan["orphan_to_delete"]["dual_mode_modules"]
                  + deletion_plan["orphan_to_delete"]["non_dual_mode_modules"]
                  + deletion_plan["live_dual_mode_to_rewire_then_delete"]["modules"]):
            mine.add(m["file"])
        assert mine
        for p in _slice_letters_on_disk():
            plan = p.parent / p.name.replace("_manifest_slice", "_deletion_plan")
            if not plan.exists() or plan == PLAN_PATH:
                continue
            other = set(re.findall(r'"(audit-platform/[^"]+\.ts)"', plan.read_text(
                encoding="utf-8")))
            assert not (mine & other), (plan.name, sorted(mine & other))


# ════════════════════════════════════════════════════════════════════════════
# 判据十二：deletion plan 与 slice 一致
# ════════════════════════════════════════════════════════════════════════════
class TestDeletionPlanConsistency:

    def test_plan_entries_mirror_the_slice_adjudication(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        """**Validates: Requirements 1.7, 12.4**"""
        slice_by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        plan_ids = [e["entry_id"] for e in deletion_plan["entries"]]
        assert sorted(plan_ids) == sorted(slice_by_id)
        assert len(plan_ids) == len(set(plan_ids))
        for pe in deletion_plan["entries"]:
            se = slice_by_id[pe["entry_id"]]
            assert pe["capability_adjudication"] == se["capability"]
            assert pe["html_counterpart_verdict"] == se["html_counterpart_verdict"]
            assert pe["adjudication_reason"] == se["adjudication"]["reason"]
            assert pe["html_counterpart_source_refs"] == se["html_counterpart_source_refs"]
            assert pe["dual_mode_carrier_kind"] == se["dual_mode_carrier"]["kind"]
            assert pe["switch_verdict"] == se["dual_mode_carrier"]["switch_verdict"]
            assert pe["must_fix_before_wiring"] == se["capability_target_blocked_by"]

    def test_plan_three_classes_are_disjoint_and_cover_all_carriers(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        """**Validates: Requirements 1.7**

        🔴 三类删除对象（M 只有两类）：两两不相交，且并集覆盖 N 域全部载体。
        """
        orphan = {m["file"] for m in deletion_plan["orphan_to_delete"]["dual_mode_modules"]}
        other = {m["file"] for m in deletion_plan["orphan_to_delete"]["non_dual_mode_modules"]}
        live = {m["file"] for m in deletion_plan["live_dual_mode_to_rewire_then_delete"]["modules"]}
        hosts = {h["host"] for h in deletion_plan["host_inlined_carriers_to_remove"]["hosts"]}
        assert not (orphan & other) and not (orphan & live) and not (other & live)
        assert not ((orphan | other | live) & hosts)
        on_disk = {_rel(p) for p in WP_COMPOSABLES.glob("useN*DualMode.ts")}
        assert orphan | live == on_disk, (sorted(orphan | live), sorted(on_disk))
        inline_hosts = {
            e["host_path"] for e in manifest_slice["independent_entries"]
            if e["dual_mode_carrier"]["kind"].startswith("host_inline")}
        assert hosts == inline_hosts, (sorted(hosts), sorted(inline_hosts))

    def test_plan_orphans_can_be_deleted_before_step_9_but_live_cannot(
        self, deletion_plan: dict
    ) -> None:
        """**Validates: Requirements 1.7**"""
        assert deletion_plan["orphan_to_delete"]["can_delete_before_step_9"] is True
        assert deletion_plan["live_dual_mode_to_rewire_then_delete"][
            "can_delete_before_step_9"] is False
        assert deletion_plan["host_inlined_carriers_to_remove"][
            "can_delete_before_step_9"] is False
        for m in (deletion_plan["orphan_to_delete"]["dual_mode_modules"]
                  + deletion_plan["orphan_to_delete"]["non_dual_mode_modules"]):
            assert m["delete_before_step_9"] is True
        for m in deletion_plan["live_dual_mode_to_rewire_then_delete"]["modules"]:
            assert m["delete_before_step_9"] is False

    def test_plan_must_not_wire_to_are_the_orphan_files(self, deletion_plan: dict) -> None:
        """**Validates: Requirements 1.4, 12.1**"""
        orphan_all = {m["file"] for m in deletion_plan["orphan_to_delete"]["dual_mode_modules"]}
        orphan_all |= {m["file"]
                       for m in deletion_plan["orphan_to_delete"]["non_dual_mode_modules"]}
        union: set[str] = set()
        for e in deletion_plan["entries"]:
            assert e["must_not_wire_to"], e["entry_id"]
            assert set(e["must_not_wire_to"]) == set(e["orphan_files_to_delete_now"])
            assert set(e["must_not_wire_to"]) <= orphan_all, e["entry_id"]
            union |= set(e["must_not_wire_to"])
        assert union == orphan_all, sorted(orphan_all - union)

    def test_plan_counters_recompute(self, deletion_plan: dict) -> None:
        """**Validates: Requirements 1.7**"""
        c = deletion_plan["counters"]
        orphan = (deletion_plan["orphan_to_delete"]["dual_mode_modules"]
                  + deletion_plan["orphan_to_delete"]["non_dual_mode_modules"])
        live = deletion_plan["live_dual_mode_to_rewire_then_delete"]["modules"]
        hosts = deletion_plan["host_inlined_carriers_to_remove"]["hosts"]
        assert c["entries"] == len(deletion_plan["entries"])
        assert c["orphan_to_delete"] == len(orphan)
        assert c["orphan_lines_total"] == sum(m["lines"] for m in orphan)
        assert c["live_dual_mode_to_delete"] == len(live)
        assert c["live_dual_mode_lines_total"] == sum(m["lines"] for m in live)
        assert c["host_inlined_carriers_to_remove"] == len(hosts)
        assert c["hosts_with_inlined_second_implementation"] == len(hosts)
        assert c["inert_switch_blocks_to_remove"] == len(
            [e for e in deletion_plan["entries"] if e["inert_switch_block_to_remove"]])
        assert c["entries_with_redeemable_switch"] == len(
            [e for e in deletion_plan["entries"] if e["switch_verdict"] == "redeemable"])
        assert c["entries_with_inert_switch"] == len(
            [e for e in deletion_plan["entries"] if e["switch_verdict"] == "inert"])
        assert c["entries_with_must_not_wire_to"] == len(
            [e for e in deletion_plan["entries"] if e["must_not_wire_to"]])
        assert c["shared_base_consumers_after"] < c["shared_base_consumers_before"]
        assert c["legacy_health_endpoint_call_sites_after"] == 1
        oc = deletion_plan["orphan_to_delete"]["counters"]
        assert oc["modules_to_delete"] == len(orphan)
        assert oc["total_lines"] == oc["dual_mode_lines"] + oc["non_dual_mode_lines"]

    def test_plan_reason_is_not_circular(self, deletion_plan: dict, paradigm: dict) -> None:
        """**Validates: Requirements 12.8**"""
        ap1 = next(a for a in paradigm["adjudication_criteria"]["anti_patterns"]
                   if a["id"] == "AP-1")
        for e in deletion_plan["entries"]:
            if e["capability_adjudication"] != "single_onlyoffice":
                continue
            hit = [m for m in ap1["circular_reason_markers"] if m in e["adjudication_reason"]]
            assert not hit, (e["entry_id"], hit)

    def test_plan_excludes_the_authoritative_templates(self, deletion_plan: dict) -> None:
        """**Validates: Requirements 12.8**

        AC 12.8 后半句：不得修改模板制造对端 ⇒ 删除/修改清单里不许出现模板路径。
        """
        blob = json.dumps(deletion_plan, ensure_ascii=False)
        excluded = [x["what"] for x in deletion_plan["excluded_from_plan"]]
        assert any("权威模板" in x for x in excluded), excluded
        for m in (deletion_plan["orphan_to_delete"]["dual_mode_modules"]
                  + deletion_plan["orphan_to_delete"]["non_dual_mode_modules"]
                  + deletion_plan["live_dual_mode_to_rewire_then_delete"]["modules"]):
            assert not m["file"].startswith("backend/wp_templates"), m["file"]
        assert "AC 12.8" in blob

    def test_plan_declares_the_same_properties(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        """**Validates: Requirements 12.12**"""
        assert {p["property"] for p in deletion_plan["properties_verified"]} == {
            p["property"] for p in manifest_slice["properties_verified"]}
        assert deletion_plan["requirements_covered"] == manifest_slice["requirements_covered"]
        assert deletion_plan["sibling_slices"] == manifest_slice["sibling_slices"]


# ════════════════════════════════════════════════════════════════════════════
# 判据十三：范式合规（校验器 + digest 双向锁）
# ════════════════════════════════════════════════════════════════════════════
def _validator_module() -> ModuleType:
    return _load_module("_task56_slice_schema_validator_host", CONTRACT_GUARD)


class TestParadigmCompliance:

    def test_the_slice_passes_the_paradigm_nominated_validator(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.3, 12.1**"""
        violations = _validator_module().validate_slice_against_schema(manifest_slice)
        assert violations == [], violations

    def test_the_validator_really_catches_a_missing_pending_field(
        self, manifest_slice: dict
    ) -> None:
        """反向自检：校验器真会咬。"""
        broken = json.loads(json.dumps(manifest_slice, ensure_ascii=False))
        broken["independent_entries"][0].pop("capability_target_blocked_by")
        violations = _validator_module().validate_slice_against_schema(broken)
        assert any("capability_target_blocked_by" in v for v in violations), violations

    def test_the_validator_really_catches_a_counter_mismatch(self, manifest_slice: dict) -> None:
        broken = json.loads(json.dumps(manifest_slice, ensure_ascii=False))
        broken["honest_adjudication_summary"]["slice_counters"]["unadjudicated"] = 0
        violations = _validator_module().validate_slice_against_schema(broken)
        assert any("SR-9" in v for v in violations), violations

    def test_the_validator_really_catches_a_forbidden_identity_kind(
        self, manifest_slice: dict
    ) -> None:
        broken = json.loads(json.dumps(manifest_slice, ensure_ascii=False))
        broken["dynamic_row_identity"]["tables"][0]["row_identity"]["kind"] = "array_index"
        violations = _validator_module().validate_slice_against_schema(broken)
        assert any("forbidden_identity_kinds" in v for v in violations), violations

    def test_the_validator_really_catches_a_single_with_identity(
        self, manifest_slice: dict
    ) -> None:
        broken = json.loads(json.dumps(manifest_slice, ensure_ascii=False))
        entry = broken["independent_entries"][0]
        entry["capability"] = "single_onlyoffice"
        entry["adjudication"]["honest_capability"] = "single_onlyoffice"
        entry["adapter_id"] = "xlsx/gt-n1-fake"
        violations = _validator_module().validate_slice_against_schema(broken)
        assert any("SR-5" in v or "adapter_id" in v for v in violations), violations

    def test_paradigm_refs_and_task_number_are_right(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4**"""
        assert manifest_slice["task"] == "Task 56"
        assert manifest_slice["paradigm_ref"] == _rel(PARADIGM_PATH)
        assert manifest_slice["source_manifest"] == _rel(FULL_MANIFEST)
        assert manifest_slice["schema_version"] == "manifest-slice:v1"

    def test_task48_extra_entry_fields_are_present(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """**Validates: Requirements 12.1**"""
        extra = paradigm["slice_schema"]["effective_from_task_48"]["required_entry"]
        for e in manifest_slice["independent_entries"]:
            for field in extra:
                assert field in e, (e["entry_id"], field)

    def test_paradigm_bytes_are_untouched_by_this_task(self, paradigm: dict) -> None:
        """**Validates: Requirements 12.4**

        `/paradigm` 的 raw + canonical 双 digest 现算并与 `paradigm_registry` 的常量比对 ——
        改一个字节全红（本任务对范式 JSON **只读**）。
        """
        mod = _validator_module()
        registry = next(p for p in paradigm["paradigm_registry"]["paradigms"]
                        if p["alias"] == "legacy_deletion_paradigm")
        raw = mod.raw_block_digest(
            mod.extract_raw_json_block(mod.load_paradigm_raw(), "paradigm"))
        canonical = mod.canonical_digest(paradigm["paradigm"])
        assert raw == registry["frozen_raw_block_sha256"], "范式 /paradigm 的 raw 块字节变了"
        assert canonical == registry["frozen_canonical_sha256"], "范式 /paradigm 的 canonical 变了"
        assert len(paradigm["paradigm"]["steps"]) == registry["step_count"] == 7

    def test_new_sections_are_declared_as_non_conflicting(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4**"""
        conflict = manifest_slice["paradigm_schema_conflict"]
        assert conflict["residual_inconsistency"] is None
        declared = conflict["new_section_not_in_schema"]["sections"]
        assert len(declared) == len(set(declared))
        schema = _load(PARADIGM_PATH)["slice_schema"]
        schema_top = set(schema["required_top_level"])
        # 条件节由 schema 自己声明（触发才必填），不算「schema 外的追加节」
        schema_top |= {cs["section"] for cs in schema.get("conditional_sections", [])}
        # `paradigm_schema_conflict` 是 D~M 九轮既定的自述键，非本轮新增
        schema_top |= {"paradigm_schema_conflict"}
        extra = {k for k in manifest_slice if k not in schema_top and not k.startswith("_")}
        assert set(declared) == extra, (
            f"追加节未全部登记：多 {sorted(set(declared) - extra)}；漏 {sorted(extra - set(declared))}")
        assert "transport_key_resolution" in declared
        assert conflict["new_section_not_in_schema"]["the_one_that_is_new_this_round"]
        assert "不改" in conflict["new_section_not_in_schema"][
            "paradigm_json_is_read_only_here"]

    def test_unjudged_slices_registry_stays_empty(self) -> None:
        """**Validates: Requirements 1.3, 12.4**

        本轮新增的 slice 必须直接过 `_UNJUDGED_SLICES` 为空的覆盖面守卫（不许加豁免行）。
        """
        module = _load_module("_task56_coverage_host", COVERAGE_GUARD)
        assert module._UNJUDGED_SLICES == {}, module._UNJUDGED_SLICES
        rel = _rel(SLICE_PATH)
        ids = [p.id for p in module._SLICE_PARAMS]
        assert pathlib.Path(rel).stem in ids, (rel, ids)

    def test_requirements_and_properties_are_declared(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4**"""
        req = manifest_slice["requirements_covered"]
        for ac in ("1.4", "6.5", "12.1", "12.4", "12.8", "12.10", "12.11", "12.12", "14.1"):
            assert ac in req, ac
        assert len(req) == len(set(req))
