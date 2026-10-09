# -*- coding: utf-8 -*-
r"""L 循环 foundation spec — 阶段 1：载体族与门控形态。

spec: l-cycle-sync-foundation-and-first-canary · Task 5~9
Properties: LF-P8 ~ LF-P12, LF-P46, LF-P47

═══ 运行 ═══

    .\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_l_foundation_p1_carriers_and_gates.py -v --tb=short
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

# ─── 路径常量 ──────────────────────────────────────────────────────────
_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
SRC_COMPOSABLES = FRONTEND / "composables"
DATA = BACKEND / "data"

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_l_cycle_manifest_slice.json"

SHARED_CARRIER = WP_COMPOSABLES / "useCycleHtmlOoDualMode.ts"
SHARED_BASE = WP_COMPOSABLES / "useWorkpaperEntryDualMode.ts"


# ─── 工具 ──────────────────────────────────────────────────────────────
def _load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _blank_keep_newlines(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(r"<!--.*?-->", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(
        r"(?<![:\w\"'`\\])//[^\n]*", lambda m: " " * len(m.group(0)), source
    )
    return source


def _vue_template(source: str) -> str:
    start = source.find("<template>")
    if start < 0:
        return ""
    end = source.rfind("</template>")
    if end < 0:
        return ""
    head = re.sub(r"[^\n]", " ", source[:start])
    return head + source[start : end + len("</template>")]


def _host_of(code: str) -> pathlib.Path:
    hits = sorted(p for p in WP_COMPONENTS.glob(f"Gt{code}*.vue"))
    assert len(hits) == 1, f"Gt{code}*.vue 应恰好 1 个宿主，实得 {[p.name for p in hits]}"
    return hits[0]


def _adjudication_tab(code: str) -> pathlib.Path:
    n = code[1:]
    return WP_COMPONENTS / f"l{n}" / "core" / f"L{n}TabAdjudication.vue"


def _wp_code_of(entry: dict) -> str:
    m = re.search(r"L(\d+)", str(entry["wp_code_pattern"]))
    assert m, f"wp_code_pattern={entry['wp_code_pattern']!r} 里没有 L+数字"
    return "L" + m.group(1)


_IMPORT_FORMS = (
    re.compile(r"""from\s*['"]([^'"\n]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"\n]+)['"]"""),
)


def _inside_double_quoted_string(line: str, pos: int) -> bool:
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
            p
            for p in FRONTEND.rglob("*")
            if p.is_file() and p.suffix in (".ts", ".vue", ".tsx", ".js")
        ]
    return _FE_FILES


def _resolve_spec(spec: str, importer: pathlib.Path) -> pathlib.Path | None:
    if spec.startswith("@/"):
        return FRONTEND / spec[2:]
    if spec.startswith("."):
        return (importer.parent / spec).resolve()
    return None


def _is_test_path(path: pathlib.Path) -> bool:
    p = path.as_posix()
    return "__tests__" in p or p.endswith((".spec.ts", ".test.ts"))


def _statement_edges_to(target: pathlib.Path) -> tuple[list[str], list[str]]:
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


# ─── fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def entries(manifest_slice: dict) -> list[dict]:
    return manifest_slice["independent_entries"]


# ═══════════════════════════════════════════════════════════════════════
# Task 5: 载体三分现算门（LC-2）
# Property: LF-P8, LF-P9
# ═══════════════════════════════════════════════════════════════════════
class TestTask5CarrierTripartition:
    """载体 kind 三分互斥求和 == 8。"""

    def test_carrier_kind_counts(self, entries: list[dict]) -> None:
        """三类互斥求和 == 8（LF-P8）。"""
        kinds = [e["dual_mode_carrier"]["kind"] for e in entries]
        shared = kinds.count("shared_cycle_composable")
        none_ = kinds.count("none")
        child = kinds.count("child_tab_dedicated_composable")
        assert shared == 2, f"shared_cycle_composable 应为 2，实得 {shared}"
        assert none_ == 2, f"none 应为 2，实得 {none_}"
        assert child == 4, f"child_tab_dedicated_composable 应为 4，实得 {child}"
        assert shared + none_ + child == 8

    def test_switch_is_redeemable_three_states(self, entries: list[dict]) -> None:
        """switch_is_redeemable 三态计数 2/2/4，null ≠ false（LF-P9）。"""
        true_count = sum(
            1 for e in entries if e["dual_mode_carrier"]["switch_is_redeemable"] is True
        )
        null_count = sum(
            1 for e in entries if e["dual_mode_carrier"]["switch_is_redeemable"] is None
        )
        false_count = sum(
            1 for e in entries if e["dual_mode_carrier"]["switch_is_redeemable"] is False
        )
        assert true_count == 2, f"true 应为 2，实得 {true_count}"
        assert null_count == 2, f"null 应为 2，实得 {null_count}"
        assert false_count == 4, f"false 应为 4，实得 {false_count}"


# ═══════════════════════════════════════════════════════════════════════
# Task 6: L5~L8 inert 三条件门（LC-2 / LC-15）
# Property: LF-P10
# ═══════════════════════════════════════════════════════════════════════
class TestTask6InertSwitchTripleCondition:
    """L5~L8 inert 三条件：segmented 有 / mode v-if 0 / GtOnlyOfficeSheet 0。"""

    @pytest.mark.parametrize("code", ["L5", "L6", "L7", "L8"])
    def test_inert_switch_was_present_now_removed(self, code: str) -> None:
        """BP-4 路线②已执行：inert 开关已从子 Tab 摘除，notice 已替代。"""
        tab = _adjudication_tab(code)
        assert tab.exists(), f"{tab} 不存在"
        raw = _cached_text(tab)
        # el-segmented 绑 dualMode 的已删，notice 已替代
        assert "GtEntrySyncCapabilityNotice" in raw, (
            f"{code} TabAdjudication 应有 notice 替代 inert 开关"
        )
        # 不应再有 dualMode 引用
        clean = _strip_comments(raw)
        assert "dualMode.mode" not in clean, (
            f"{code} 不应再有 dualMode.mode 绑定"
        )


# ═══════════════════════════════════════════════════════════════════════
# Task 7: L1/L2 redeemable 对照门
# Property: LF-P11
# ═══════════════════════════════════════════════════════════════════════
class TestTask7RedeemableContrast:
    """L1/L2 宿主有以 currentMode 为条件的 GtOnlyOfficeSheet 挂点。"""

    @pytest.mark.parametrize("code", ["L1", "L2"])
    def test_redeemable_host_has_oo_mount(self, code: str) -> None:
        host = _host_of(code)
        raw = _cached_text(host)
        clean = _strip_comments(raw)
        template = _vue_template(clean)

        # 有 GtOnlyOfficeSheet
        assert "GtOnlyOfficeSheet" in template, (
            f"{code} 宿主模板无 GtOnlyOfficeSheet"
        )
        # 有以 mode/currentMode 为条件的 v-if
        mode_gates = re.findall(
            r'v-if="[^"]*(?:currentMode|mode)[^"]*(?:onlyoffice|===)[^"]*"',
            template,
        )
        assert len(mode_gates) > 0, (
            f"{code} 宿主无以 currentMode 为条件的 OO 挂点"
        )


# ═══════════════════════════════════════════════════════════════════════
# Task 8: L3/L4 none 门 + L4 bondBranch（LC-15）
# Property: LF-P12
# ═══════════════════════════════════════════════════════════════════════
class TestTask8NoneCarrierAndBondBranch:
    """L3/L4 宿主不 import 任何 use*DualMode。"""

    @pytest.mark.parametrize("code", ["L3", "L4"])
    def test_no_dual_mode_import(self, code: str) -> None:
        host = _host_of(code)
        text = _cached_text(host)
        # 不 import 任何 use*DualMode
        imports = re.findall(r"use\w*DualMode", text)
        assert len(imports) == 0, (
            f"{code} 宿主 import 了 DualMode: {imports}"
        )

    @pytest.mark.parametrize("code", ["L3", "L4"])
    def test_has_v_else_oo_fallback(self, code: str) -> None:
        """有 v-else 兜底的 GtOnlyOfficeSheet（服务 GT_Custom）。
        L3/L4 可能有多个 OO 挂点——至少一个带 v-else 即满足 none 载体形态。"""
        host = _host_of(code)
        raw = _cached_text(host)
        clean = _strip_comments(raw)
        template = _vue_template(clean)
        oo_hits = list(re.finditer(r"<GtOnlyOfficeSheet", template))
        if len(oo_hits) == 0:
            return  # 无 OO 挂点也是合法的 none 状态
        # 至少一个挂点带 v-else（可能在下一行）
        has_v_else = False
        for hit in oo_hits:
            # 取命中点前后若干字符（含属性可能跨行）
            context = template[hit.start() : min(hit.start() + 300, len(template))]
            # 截取到该组件的闭合 /> 或 >
            close = context.find("/>")
            if close < 0:
                close = context.find(">")
            tag_text = context[: close + 2] if close >= 0 else context
            if "v-else" in tag_text:
                has_v_else = True
                break
        assert has_v_else, f"{code} 宿主无 v-else 兜底的 GtOnlyOfficeSheet"

    def test_l4_bond_branch_is_not_mode_switch(self) -> None:
        """L4 的 bondBranch el-segmented 不是模式开关（LC-15）。"""
        host = _host_of("L4")
        raw = _cached_text(host)
        clean = _strip_comments(raw)
        # bondBranch 的 segmented 存在
        assert "bondBranch" in clean, "L4 宿主应含 bondBranch"
        # 它的 el-segmented 不与 dualMode 关联
        for line in clean.split("\n"):
            if "el-segmented" in line and "bondBranch" in line:
                assert "dualMode" not in line, (
                    "bondBranch 的 el-segmented 不应与 dualMode 关联"
                )


# ═══════════════════════════════════════════════════════════════════════
# Task 9: 共享件消费面门（LC-2 邻域）
# Property: LF-P46, LF-P47
# ═══════════════════════════════════════════════════════════════════════
class TestTask9SharedCarrierConsumption:
    """共享载体 useCycleHtmlOoDualMode 窄生产边 3 → 改线后 1。"""

    def test_shared_carrier_has_3_prod_edges(self) -> None:
        """窄生产边 == 3（L1 宿主 + L2 宿主 + Shell）（LF-P46）。"""
        prod, _test = _statement_edges_to(SHARED_CARRIER)
        assert len(prod) == 3, (
            f"useCycleHtmlOoDualMode 窄生产边应为 3，实得 {len(prod)}：{prod}"
        )
        # 其中 2 条来自 L 宿主，1 条来自 Shell
        l_edges = [e for e in prod if "/GtL" in e]
        shell_edges = [e for e in prod if "CycleStandaloneProcedureShell" in e]
        assert len(l_edges) == 2, f"L 宿主边应为 2，实得 {l_edges}"
        assert len(shell_edges) == 1, f"Shell 边应为 1，实得 {shell_edges}"

    def test_shell_still_consumed_by_router(self) -> None:
        """Shell 被 GtCycleAProgramRouter 消费 ⇒ 不可删（LF-P46）。"""
        shell_path = WP_COMPONENTS / "shared" / "CycleStandaloneProcedureShell.vue"
        if not shell_path.exists():
            pytest.skip(f"Shell 不存在：{shell_path}")
        prod, _ = _statement_edges_to(shell_path)
        router_edges = [e for e in prod if "CycleAProgramRouter" in e or "ProgramRouter" in e]
        assert len(router_edges) > 0, (
            "CycleStandaloneProcedureShell 应被 Router 消费"
        )

    def test_shared_base_l_domain_contribution_is_zero(self) -> None:
        """useWorkpaperEntryDualMode 的 L 域贡献 == 0（LF-P47）。"""
        prod, _ = _statement_edges_to(SHARED_BASE)
        l_domain_edges = [
            e for e in prod
            if re.search(r"/l[1-8]/|/GtL[1-8]|/useL[1-8]", e)
        ]
        assert len(l_domain_edges) == 0, (
            f"共享基类 L 域贡献应为 0，实得 {len(l_domain_edges)}：{l_domain_edges}"
        )
