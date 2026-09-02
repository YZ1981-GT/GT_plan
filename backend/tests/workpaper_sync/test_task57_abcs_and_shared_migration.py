# -*- coding: utf-8 -*-
r"""Task 57 守卫 —— A/B/C/S 与跨循环共享 Excel 独立 entry 迁移（Wave 5 Excel lane 收口）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 57
点名 Property：**3 / 22 / 69 / 70**；点名 AC：1.4 · **1.6** · 6.4 · 12.1 · 12.4 · 12.8 ·
12.9 · 12.10 · 12.11 · 12.12 · 14.1。

═══ 本轮与前十一轮的判据差异（照抄 N/M 会假红的点）═══

tasks.md 正文点名四件事，前十一轮**都没有**：

1. **按 componentType/持久化通道分组**（不是按 wp_code 前缀逐条列）。两维都必须现读：
   componentType 从 `htmlRendererRegistry.ts` 的**模块边**解析（禁按符号名 grep），持久化通道
   从宿主 import 闭包里的真实 HTTP 站点得到。
2. **跨循环函证复用 adapter，不复制合同**（AC 1.6）。落成可复算判据：同一 adapter 被 N 个循环
   入口复用时 contract 归属必须是 **1 份**而不是 N 份。
3. **Property 22（动态列 key 与 label 解耦）首次拿到非空分母** —— I~N 六轮都以「分母为空、不宣称
   通过」收场；本轮实测 7 处动态列 + 3 处 label 作 key，结论 **PARTIAL**。
4. **只投影既有业务模型**（程序表 / 控制判断 / 动态宽表 / 附件+OCR），不得新造业务字段。

十二处形态差异（slice 的 `abcs_form_differences` 逐条冻结，本文件逐条现算）：

* **AD-1** 范围横跨四个字母 **+ `wp_code_patterns` 为空数组的 5 条跨循环共享宿主** —— 照抄
  「wp_code 前缀 == 单字母」会漏这 5 条。
* **AD-2** **B60 是本轮字母范围内的 pilot** ⇒ `excluded_pilot_entry_count` 首次非 0。
* **AD-3** 权威册**大量是 docx**（16/19 条静态可解析 entry）⇒ 对 docx 册**不能**跑 openpyxl。
* **AD-4** 27/46 条的 `:sheet-name` 是运行时表达式 ⇒ 册↔entry 只能是**单射**不是双射。
* **AD-5** 开关形态 42 redeemable + **0 inert** + 4 无开关 —— 照抄 N 的 inert 判据恒空跑。
* **AD-6** 门控必须**真解析祖先链**（`html.parser`）：缩进式推断在本轮 26/43 假阴。
* **AD-7** 跨循环函证族是本轮唯一必须处置的「无 entry」对象。
* **AD-8** Property 22 分母首次非空。
* **AD-9** 一 adapter 服务 N 个 wp_code 的极端形态（`c-control-test` 一条 entry 覆盖 28 个码）。
* **AD-10** 共享基类边数现算 26+1（M=29 / N=27）—— **每轮现算，禁照抄**。
* **AD-11** `parent_duplicate_summary` **不触发**（in-scope 0；与 K/L/M 同、与 N 相反）。
* **AD-12** 分组是二维的（13 组 / 9 家族 / 5 通道）。

另有本轮独有的 `dual_mode_carrier_inventory`：**per-entry dual-mode composable 现算 0 个**
（全域 113 个 `*DualMode*.ts` 无一属 A/B/C/S）⇒ 照抄 N 的「orphan dual-mode 模块」判据恒空跑。

═══ 判据强度约定（沿用前十一轮，逐条不放宽）═══

1. 裁决判据 = **AC 12.8 原文「无 HTML 对端」**，不是「adapter/contract/bundle 不存在」（AP-1）。
2. 四个 capability 枚举值都不成立 ⇒ 待裁决态（`capability: null` + 三字段齐备）。禁扩枚举。
3. `manifest_mirror` 判据 = 断言「**必须不一致**且已登记 BP」，不是断言相等。
4. 消费边 = **statement-position import 路径字面量**（`from '…'` **可独占一行**），且排除
   **双引号字符串内**的匹配。
5. orphan 判定用**可达性**而非入度；路径解析口径，禁 stem 相等；**barrel 入边仍是边**。
6. 剥注释**保留行号**（同长空白替换）。
7. **source_ref 三边锁**：声明 → 磁盘真读 → impl 常量现读。**sheet 名不得 strip**。
8. AC 1.5 仅在裁出 `single_*` 时适用；本轮无 single ⇒ 生效 AC 1.4。
9. 「纯客户端」/「开关坏了」/「没有开关」都**不是**裁 `single_html` 的理由。
10. 分母为空的 Property **明确不宣称通过**（只断言前提 + 承载者存在）。
11. 计数一律**从来源节现算等值**；「某族 0 命中」也落成判据。
12. 任何 `declared` 与 `computed` 列表做**有序等值 + 无重复**双断言（Task 55 的 M23 教训）。
13. CJK 在 Python 里算 `\w` ⇒ 提取码不能用 `\b`（Task 56 的教训）。

用法（仓库根；本仓库 PATH 上的 `python` 可能指向坏掉的解释器）::

    .\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_task57_abcs_and_shared_migration.py -q
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
from collections import Counter, defaultdict
from html.parser import HTMLParser
from types import ModuleType
from typing import Any

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

SLICE_PATH = DATA / "workpaper_sync_abcs_cycle_manifest_slice.json"
PLAN_PATH = DATA / "workpaper_sync_abcs_cycle_deletion_plan.json"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
FULL_MANIFEST = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY = DATA / "workpaper_sync_entry_overlay.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
CONTRACT_GUARD = _THIS.with_name("test_migration_paradigm_contract.py")
COVERAGE_GUARD = _THIS.with_name("test_slice_schema_validator_coverage.py")

TEMPLATE_DIR = BACKEND / "wp_templates"
TEMPLATE_INDEX = TEMPLATE_DIR / "_index.json"
WP_CODE_OVERRIDES = BACKEND / "app" / "data" / "wp_code_overrides.json"
OO_ROUTER = BACKEND / "app" / "routers" / "wp_onlyoffice_router.py"
TEMPLATE_FINDER = BACKEND / "app" / "services" / "wp_template_finder.py"
REGISTRY = SVC / "adapters" / "registry.py"
HTML_RENDERER_REGISTRY = WP_COMPONENTS / "htmlRendererRegistry.ts"
SHARED_BASE = WP_COMPOSABLES / "useWorkpaperEntryDualMode.ts"
AC14_NOTICE_TS = WP_COMPONENTS / "sync" / "workpaperEntrySyncNotice.ts"
AC14_NOTICE_VUE = WP_COMPONENTS / "sync" / "GtEntrySyncCapabilityNotice.vue"

ABCS = ("A", "B", "C", "S")
HTML_COUNTERPART_VERDICTS = ("none", "exists")
CONFIRMATION_CYCLES = ("D", "E", "F", "G", "H", "K", "L")

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
    ``from '...'`` 形态；不排除它，共享载体的边数结论会被污染。
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
#: 会把 `import {\n  A,\n} from './x'` 整类漏掉（Task 56 因此把一个 live 模块误判成 orphan）。
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


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_module(name: str, path: pathlib.Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"无法以 importlib 加载 {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _slice_paths_on_disk() -> list[pathlib.Path]:
    return sorted(DATA.glob("workpaper_sync_*_cycle_manifest_slice.json"))


# ════════════════════════════════════════════════════════════════════════════
# registry 模块边解析（分组键第一维）
# ════════════════════════════════════════════════════════════════════════════
def _registry_pairs() -> list[tuple[str, pathlib.Path, int]]:
    """`(componentType, 组件磁盘路径, registry 行号)` —— 🔴 两种 `component:` 写法都要认。

    registry 里有**两种**写法：提升的 `const X = defineAsyncComponent(...)` 与内联
    `component: defineAsyncComponent(() => import('...'))`。只认一种会漏掉 94/211 条
    （首版实测），进而让分组键的第一维对一半 entry 退化成「不在 registry 里」。
    """
    src = _cached_text(HTML_RENDERER_REGISTRY)
    lines = src.split("\n")
    local2rel: dict[str, str] = {}
    for m in re.finditer(
        r"^const\s+(\w+)\s*=\s*defineAsyncComponent\(\s*\(\)\s*=>\s*import\(\s*'([^']+)'\s*\)\s*\)",
        src, re.M,
    ):
        local2rel[m.group(1)] = m.group(2)
    out: list[tuple[str, pathlib.Path, int]] = []
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*componentType:\s*'([^']+)',?\s*$", ln)
        if not m:
            continue
        ct, rel = m.group(1), None
        for j in range(i + 1, min(i + 8, len(lines))):
            mi = re.search(
                r"component:\s*defineAsyncComponent\(\s*\(\)\s*=>\s*import\(\s*'([^']+)'", lines[j])
            if mi:
                rel = mi.group(1)
                break
            ml = re.match(r"^\s*component:\s*(\w+),?\s*$", lines[j])
            if ml:
                rel = local2rel.get(ml.group(1))
                break
        if rel:
            out.append((ct, (HTML_RENDERER_REGISTRY.parent / rel).resolve(), i + 1))
    return out


def _component_types_of(host_path: str) -> list[str]:
    host = (ROOT / host_path).resolve()
    return sorted(ct for ct, p, _ln in _registry_pairs() if p == host)


def _ct_to_wp_codes() -> dict[str, list[str]]:
    ovr = _load(WP_CODE_OVERRIDES)
    out: dict[str, list[str]] = defaultdict(list)
    for code, ct in ovr.items():
        if isinstance(ct, str):
            out[ct].append(code)
    return {k: sorted(v) for k, v in out.items()}


# ════════════════════════════════════════════════════════════════════════════
# Vue 模板真解析（mode 门控判据）
# ════════════════════════════════════════════════════════════════════════════
#: 🔴 `mode` 的真实写法不止一种：`renderMode` / `dualMode` / `activeMode` / `editorMode` /
#: `currentMode` 都在生产源码里出现。只认字面 `mode` 会把 39/43 个宿主判成「无门控」。
MODE_TOKENS = re.compile(r"\b\w*[Mm]ode\b")
_COND_ATTRS = ("v-if", "v-else-if", "v-else", "v-show")


class _VueTemplateParser(HTMLParser):
    """真解析 `<template>` 段以取得**真实祖先链**。

    🔴 缩进式祖先推断在手写 Vue 模板里不可靠：`GtB1Evaluation.vue` 的
    `<template v-if="mode === '结构化视图'">`（L21）与它的子元素 `<el-alert v-if="riskAlert">`
    （L22）**同为缩进 4**，按缩进找兄弟会命中子元素并把整条判成「无 mode 门控」。
    """

    VOID = {"br", "hr", "img", "input", "meta", "link", "source", "track", "wbr",
            "area", "base", "col", "embed", "param"}

    def __init__(self, target: str) -> None:
        super().__init__(convert_charrefs=False)
        self.target = target
        self.stack: list[tuple[str, dict, dict | None]] = []
        self.hits: list[tuple[int, dict, list[tuple[dict, dict | None]], dict | None]] = []
        self._siblings: list[list[dict]] = [[]]

    def _chain_head(self, attrs: dict) -> dict | None:
        if "v-else" not in attrs and "v-else-if" not in attrs:
            return None
        for prev in reversed(self._siblings[-1]):
            if "v-if" in prev:
                return prev
            if "v-else-if" in prev:
                continue
            break
        return None

    def _record(self, tag: str, attrs: dict, head: dict | None) -> None:
        if tag != self.target:
            return
        anc = [(a, h) for _t, a, h in self.stack]
        self.hits.append((self.getpos()[0], attrs, anc, head))

    def handle_starttag(self, tag, attrs):  # noqa: D102
        a = {k: (v if v is not None else "") for k, v in attrs}
        head = self._chain_head(a)
        self._record(tag, a, head)
        self._siblings[-1].append(a)
        if tag.lower() in self.VOID:
            return
        self.stack.append((tag, a, head))
        self._siblings.append([])

    def handle_startendtag(self, tag, attrs):  # noqa: D102
        a = {k: (v if v is not None else "") for k, v in attrs}
        head = self._chain_head(a)
        self._record(tag, a, head)
        self._siblings[-1].append(a)

    def handle_endtag(self, tag):  # noqa: D102
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                del self._siblings[i + 1:]
                return


def _attrs_have_mode_conditional(a: dict) -> bool:
    return any(k in a and MODE_TOKENS.search(a[k] or "") for k in ("v-if", "v-else-if", "v-show"))


def _parse_oo_mounts(src: str) -> list[dict]:
    """解析 template 段里所有 `GtOnlyOfficeSheet` 挂载点及其真实祖先链。"""
    m = re.search(r"<template>", src)
    if not m:
        return []
    end = src.find("\n</template>")
    body = src[m.start(): end + len("\n</template>")] if end != -1 else src
    offset = src[: m.start()].count("\n")
    p = _VueTemplateParser("gtonlyofficesheet")
    try:
        p.feed(body)
    except Exception:  # noqa: BLE001 - 手写模板可能触发解析器边界，退化为已收集的命中
        pass
    out = []
    for line, own, anc, head in p.hits:
        pairs = [(own, head)] + list(anc)
        gated = False
        gate_exprs: list[str] = []
        for a, h in pairs:
            if _attrs_have_mode_conditional(a):
                gated = True
                gate_exprs += [a.get(k, "") for k in ("v-if", "v-else-if", "v-show")
                               if k in a and MODE_TOKENS.search(a[k] or "")]
                break
            if ("v-else" in a or "v-else-if" in a) and h is not None:
                expr = h.get("v-if") or h.get("v-else-if") or ""
                if MODE_TOKENS.search(expr):
                    gated = True
                    gate_exprs.append(expr)
                    break
        out.append({
            "line": line + offset,
            "mode_gated": gated,
            "gate_expressions": gate_exprs,
            "gate_mode_vars": sorted({
                m.group(1) for e in gate_exprs for m in re.finditer(r"\b(\w*[Mm]ode)\b", e)}),
            "has_any_conditional": any(any(k in a for k in _COND_ATTRS) for a, _h in pairs),
            "sheet_name_literal": own.get("sheet-name"),
            "sheet_name_expr": own.get(":sheet-name"),
        })
    return out


def _tag_block_from(lines: list[str], start_1based: int, span: int = 16) -> str:
    """从第 `start_1based` 行（1-based）起取整个标签块（到第一个 `>`）。"""
    blob = "\n".join(lines[start_1based - 1: start_1based - 1 + span])
    end = blob.find(">")
    return blob[: end + 1] if end != -1 else blob


def _host_gate(host_path: str) -> dict:
    src = _strip_comments(_cached_text(ROOT / host_path))
    lines = src.split("\n")
    parsed = _parse_oo_mounts(src)
    return {
        "segmented_sites": [i for i, l in enumerate(lines, 1) if "<el-segmented" in l],
        "mode_radio_sites": [i for i, l in enumerate(lines, 1)
                             if "<el-radio-group" in l and MODE_TOKENS.search(l)],
        "oo_mount_sites": [m["line"] for m in parsed],
        "mode_gated_oo_mount_sites": sorted({m["line"] for m in parsed if m["mode_gated"]}),
        "gate_mode_vars": sorted({v for m in parsed for v in m["gate_mode_vars"]}),
        "sheet_fallthrough_sites": sorted({
            m["line"] for m in parsed if not m["mode_gated"] and m["has_any_conditional"]}),
        "mounts_ac14_notice": "GtEntrySyncCapabilityNotice" in src,
        "claims_bidirectional_in_template": "可双向回写" in src,
        "calls_legacy_health": "/api/workpapers/onlyoffice/health" in src,
        "calls_legacy_config": "onlyoffice-config" in src,
        "literals": sorted({m["sheet_name_literal"] for m in parsed if m["sheet_name_literal"]}),
        "exprs": sorted({m["sheet_name_expr"] for m in parsed if m["sheet_name_expr"]}),
    }


# ════════════════════════════════════════════════════════════════════════════
# 持久化通道（分组键第二维）
# ════════════════════════════════════════════════════════════════════════════
_CHANNELS = {
    "checklist_responses": re.compile(r"/checklist-responses"),
    "field_overrides": re.compile(r"/api/workpapers/field-overrides"),
    "custom_cells": re.compile(r"/custom-cells"),
}


def _local_imports(host: pathlib.Path) -> list[pathlib.Path]:
    out = []
    src = _strip_comments(_cached_text(host))
    for rx in _IMPORT_FORMS:
        for m in rx.finditer(src):
            base = _resolve_spec(m.group(1), host)
            if base is None:
                continue
            for cand in (base, pathlib.Path(str(base) + ".ts"),
                         pathlib.Path(str(base) + ".vue"), base / "index.ts"):
                if cand.is_file():
                    out.append(cand)
                    break
    return sorted(set(out))


_CLOSURE_CACHE: dict[str, list[pathlib.Path]] = {}


def _closure(host_path: str, maxdepth: int = 3) -> list[pathlib.Path]:
    if host_path in _CLOSURE_CACHE:
        return _CLOSURE_CACHE[host_path]
    host = ROOT / host_path
    seen = {host}
    frontier = [host]
    for _ in range(maxdepth):
        nxt = []
        for f in frontier:
            for g in _local_imports(f):
                if g not in seen:
                    seen.add(g)
                    nxt.append(g)
        frontier = nxt
        if not frontier:
            break
    _CLOSURE_CACHE[host_path] = sorted(seen)
    return _CLOSURE_CACHE[host_path]


def _channel_of(host_path: str) -> str:
    hit = []
    for name, rx in _CHANNELS.items():
        for f in _closure(host_path):
            if rx.search(_strip_comments(_cached_text(f))):
                hit.append(name)
                break
    order = ["checklist_responses", "field_overrides", "custom_cells"]
    keys = [k for k in order if k in hit]
    return "+".join(keys) if keys else "none_detected"


# ════════════════════════════════════════════════════════════════════════════
# selection_rule 现算
# ════════════════════════════════════════════════════════════════════════════
def _letters(codes: Any) -> set[str]:
    out = set()
    for c in codes or []:
        m = re.match(r"^([A-Za-z])", c or "")
        if m:
            out.add(m.group(1).upper())
    return out


def _recompute_selection(full_manifest: dict) -> list[str]:
    """按 slice 的 selection_rule 从 manifest **现算** entry 集合。"""
    out = []
    for e in full_manifest["entries"]:
        if e.get("document_type") != "xlsx" or e.get("independent_entry") is not True:
            continue
        pats = (e.get("wp_match") or {}).get("wp_code_patterns") or []
        if not ((_letters(pats) & set(ABCS)) or not pats):
            continue
        if e["entry_id"] in PILOT_CONTRACT_OWNERS:
            continue
        out.append(e["entry_id"])
    return out


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


# ════════════════════════════════════════════════════════════════════════════
# 判据零：守卫自身自检（工具错了，后面全部判据一起假）
# ════════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:

    def test_all_required_artifacts_exist(self) -> None:
        """**Validates: Requirements 12.4**"""
        for p in (SLICE_PATH, PLAN_PATH, PARADIGM_PATH, FULL_MANIFEST, OVERLAY,
                  CONTRACT_GUARD, COVERAGE_GUARD, HTML_RENDERER_REGISTRY, SHARED_BASE,
                  AC14_NOTICE_TS, AC14_NOTICE_VUE, WP_CODE_OVERRIDES, OO_ROUTER,
                  TEMPLATE_FINDER, TEMPLATE_INDEX, REGISTRY):
            assert p.exists(), f"缺少产物：{p}"
        for letter in ABCS:
            assert (TEMPLATE_DIR / letter).is_dir(), f"权威模板目录缺失：{letter}"

    def test_strip_comments_hides_content_but_keeps_line_numbers(self) -> None:
        src = "a\n// hidden marker\nb\n/* x\ny */\nc\n"
        out = _strip_comments(src)
        assert "hidden marker" not in out
        assert len(out.split("\n")) == len(src.split("\n")), "剥注释改变了行数"

    def test_strip_comments_really_hides_a_commented_marker_in_an_abcs_host(self) -> None:
        """反向自检：A101 宿主头部注释里写着「el-segmented 双模式」，剥注释后必须消失。"""
        raw = _cached_text(WP_COMPONENTS / "GtA101GovernanceCommunication.vue")
        assert "el-segmented 双模式" in raw, "A101 宿主里的那段注释不见了 ⇒ 本自检失去对象"
        assert "el-segmented 双模式" not in _strip_comments(raw)

    def test_inside_double_quoted_string_detector_works_both_ways(self) -> None:
        line = 'x = "import a from \'./b\'"; import c from "./d"'
        assert _inside_double_quoted_string(line, line.index("import a")) is True
        assert _inside_double_quoted_string(line, line.index("import c")) is False

    def test_import_scanner_accepts_a_multiline_import(self) -> None:
        """🔴 `from '…'` 独占一行时必须仍能定位（Task 56 实测缺陷的自检）。

        `GtB50RiskAssessment.vue` 对 `composables/b50Completeness` 的 import 是**多行**形态
        （收尾行只有 `} from './composables/b50Completeness'`）。只匹配「同一行里 import…from」
        的扫描器会把它整类漏掉，进而把一个 live 模块判成 orphan。
        """
        target = WP_COMPOSABLES / "b50Completeness.ts"
        assert target.is_file(), f"自检对象不存在：{target}"
        prod, _ = _statement_edges_to(target)
        assert prod, "b50Completeness 现算生产边为空 ⇒ 多行 import 没被认出来"
        hit = [r for r in prod if "GtB50RiskAssessment.vue" in r]
        assert hit, prod
        line = _line_at(hit[0])
        assert not re.search(r"\bimport\b[^\n]*\bfrom\b", line), (
            f"该 import 已变成单行形态 ⇒ 本自检失去对象：{line.strip()[:120]!r}"
        )
        assert line.strip().startswith("} from"), line.strip()[:120]

    def test_resolve_spec_is_path_based_not_stem_based(self) -> None:
        importer = WP_COMPONENTS / "GtB50RiskAssessment.vue"
        got = _resolve_spec("./composables/useWorkpaperEntryDualMode", importer)
        assert got == (WP_COMPOSABLES / "useWorkpaperEntryDualMode").resolve()
        assert _resolve_spec("vue", importer) is None

    def test_registry_parser_sees_both_component_forms(self) -> None:
        """🔴 registry 有两种 `component:` 写法；只认一种会漏掉近一半条目。"""
        src = _cached_text(HTML_RENDERER_REGISTRY)
        declared = len(re.findall(r"^\s*componentType:\s*'([^']+)'", src, re.M))
        parsed = _registry_pairs()
        assert len(parsed) == declared, (
            f"registry 声明 {declared} 条 componentType，解析出 {len(parsed)} 条 ⇒ 解析器漏了"
        )
        hoisted = sum(
            1 for _ct, _p, ln in parsed
            if re.match(r"^\s*component:\s*\w+,?\s*$", src.split("\n")[ln])
        )
        inline = len(parsed) - hoisted
        assert hoisted > 0 and inline > 0, (
            f"两种写法必须都非空（hoisted={hoisted} inline={inline}）⇒ 否则「都要认」这条判据空跑"
        )

    def test_ancestor_chain_parser_beats_indentation_heuristics(self) -> None:
        """🔴 AD-6 的自检：B1Evaluation 的门控在**祖先** `<template v-if="mode …">` 上。"""
        gate = _host_gate("audit-platform/frontend/src/components/workpaper/GtB1Evaluation.vue")
        assert gate["oo_mount_sites"], "B1Evaluation 里找不到 GtOnlyOfficeSheet 挂载点"
        assert gate["mode_gated_oo_mount_sites"], (
            "B1Evaluation 的 OO 挂载点被判成「无 mode 门控」⇒ 祖先链解析失效（缩进式假阴复发）"
        )
        src = _strip_comments(_cached_text(WP_COMPONENTS / "GtB1Evaluation.vue"))
        lines = src.split("\n")
        gate_line = next(
            (i for i, l in enumerate(lines, 1) if re.search(r"<template v-if=\"mode ===", l)), None)
        assert gate_line is not None, "B1Evaluation 的祖先门控写法变了 ⇒ 本自检失去对象"
        mount = gate["oo_mount_sites"][0]
        assert gate_line < mount, "门控行应在挂载点之前"
        own_tag = lines[mount - 1]
        assert not MODE_TOKENS.search(own_tag), (
            "该挂载点自身标签行已含 mode token ⇒ 本自检失去对象（改一个门控在祖先上的例子）"
        )

    def test_mode_token_regex_covers_the_real_variable_names(self) -> None:
        """🔴 只认字面 `mode` 会漏掉 renderMode / dualMode / activeMode。"""
        for name in ("mode", "renderMode", "dualMode", "activeMode", "editorMode", "currentMode"):
            assert MODE_TOKENS.search(f"{name} === 'x'"), name
        assert not MODE_TOKENS.search("readonly === true")

    def test_mode_assignment_regex_is_not_fooled_by_equality(self) -> None:
        """🔴 `currentMode.value === 'x'` 不是赋值。"""
        rx = re.compile(r"\b\w*[Mm]ode(\.value)?\s*=(?!=)")
        assert rx.search("mode.value = 'html'")
        assert not rx.search("currentMode.value === 'html'")

    def test_channel_scanner_separates_the_three_channels(self) -> None:
        """三个通道必须真的分得开，否则「二维分组」的第二维是常量。"""
        got = {
            _channel_of("audit-platform/frontend/src/components/workpaper/GtCustomWpEditor.vue"),
            _channel_of("audit-platform/frontend/src/components/workpaper/GtA3ConsolidationConsole.vue"),
            _channel_of("audit-platform/frontend/src/components/workpaper/GtA101GovernanceCommunication.vue"),
        }
        assert got == {"custom_cells", "field_overrides", "checklist_responses"}, got

    def test_abcs_denominator_is_non_vacuous(self, full_manifest: dict) -> None:
        computed = _recompute_selection(full_manifest)
        assert len(computed) >= 40, f"A/B/C/S 现算只有 {len(computed)} 条 ⇒ 扫描分母可疑"
        assert len(set(computed)) == len(computed), "现算集合有重复"

    def test_the_n_style_per_entry_dual_mode_scanner_finds_nothing_here(self) -> None:
        """🔴 AD/inventory 的反向断言：N 那套 per-entry dual-mode 扫描器在本轮 0 命中。

        没有这一条，「本轮换了载体形态」只是自述；有了它，抄旧扫描器的人会看到 0 而知道
        必须换口径（而不是以为 A/B/C/S 没有 legacy）。
        """
        hits = sorted(
            p.name for p in WP_COMPOSABLES.glob("*.ts")
            if re.match(r"^use[ABCS]\d.*DualMode\.ts$", p.name)
        )
        assert hits == [], f"A/B/C/S per-entry dual-mode 模块现算有命中 {hits} ⇒ 形态判断要重做"
        everything = sorted(p.name for p in WP_COMPOSABLES.rglob("*.ts") if "DualMode" in p.name)
        assert len(everything) >= 100, (
            f"全域 DualMode 模块只有 {len(everything)} 个 ⇒ 反向分母可疑（本条要证明「别的循环有、"
            "本轮没有」，分母必须非空）"
        )

    def test_docx_templates_must_not_be_read_by_openpyxl(self, manifest_slice: dict) -> None:
        """🔴 AD-3 的自检：docx 册非空，且对它跑 openpyxl 会抛异常 ⇒ 判据必须按 format 分流。"""
        import openpyxl

        docx = [f for f in manifest_slice["authoritative_templates"]["files"]
                if f["format"] in ("docx", "doc")]
        assert docx, "docx 册现算为 0 ⇒ AD-3 失去对象"
        sample = TEMPLATE_DIR / docx[0]["name"]
        assert sample.is_file()
        with pytest.raises(Exception):
            openpyxl.load_workbook(sample, read_only=True)


# ════════════════════════════════════════════════════════════════════════════
# 判据一：slice_scope 可复算
# ════════════════════════════════════════════════════════════════════════════
class TestSliceScopeIsRecomputable:

    def test_selection_rule_recomputes_the_entry_set(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        🔴 有序等值 + 无重复**双断言**（Task 55 的 M23 教训：只逐元素比会漏掉集合层错误）。
        """
        declared = [e["entry_id"] for e in manifest_slice["independent_entries"]]
        computed = _recompute_selection(full_manifest)
        assert sorted(declared) == sorted(computed), (
            f"多写 {sorted(set(declared) - set(computed))} / 漏写 {sorted(set(computed) - set(declared))}"
        )
        assert len(set(declared)) == len(declared), "independent_entries 有重复 entry_id"
        assert set(declared) == set(computed)

    def test_pattern_less_shared_hosts_are_included(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 AD-1：`wp_code_patterns` 为空数组的 5 条跨循环共享宿主必须在 slice 里。"""
        pattern_less = sorted(
            e["entry_id"] for e in full_manifest["entries"]
            if e.get("document_type") == "xlsx" and e.get("independent_entry") is True
            and not ((e.get("wp_match") or {}).get("wp_code_patterns") or [])
        )
        assert len(pattern_less) == manifest_slice["slice_scope"]["pattern_less_shared_total"]
        declared = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert set(pattern_less) <= declared, (
            f"漏收跨循环共享宿主：{sorted(set(pattern_less) - declared)}"
        )
        for e in manifest_slice["independent_entries"]:
            if e["entry_id"] in pattern_less:
                assert e["wp_code_pattern"] is None
                assert e["wp_code_pattern_absent_because"], e["entry_id"]

    def test_letter_bucket_counts_recompute(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        scope = manifest_slice["slice_scope"]
        buckets: Counter = Counter()
        for e in full_manifest["entries"]:
            if e.get("document_type") != "xlsx" or e.get("independent_entry") is not True:
                continue
            pats = (e.get("wp_match") or {}).get("wp_code_patterns") or []
            if not pats:
                buckets["pattern_less_shared"] += 1
                continue
            for L in _letters(pats) & set(ABCS):
                buckets[L] += 1
        assert dict(buckets) == scope["letter_bucket_counts"], (buckets, scope["letter_bucket_counts"])
        assert scope["abcs_letter_hit_total"] == sum(buckets[L] for L in ABCS)
        xlsx_indep = sum(
            1 for e in full_manifest["entries"]
            if e.get("document_type") == "xlsx" and e.get("independent_entry") is True)
        assert scope["xlsx_independent_total_in_manifest"] == xlsx_indep

    def test_covered_by_d_to_n_slices_recomputes_and_is_disjoint(
        self, manifest_slice: dict
    ) -> None:
        """本 slice 的 entry 与 D~N 十一份 slice 覆盖面不相交，且覆盖数现算等值。"""
        covered: set[str] = set()
        for p in _slice_paths_on_disk():
            if p == SLICE_PATH:
                continue
            for e in _load(p)["independent_entries"]:
                covered.add(e["entry_id"])
        assert manifest_slice["slice_scope"]["covered_by_d_to_n_slices"] == len(covered)
        mine = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert not (mine & covered), f"与既有 slice 重叠：{sorted(mine & covered)}"

    def test_b60_is_the_excluded_pilot_and_the_contract_denominator_is_non_vacuous(
        self, manifest_slice: dict
    ) -> None:
        """🔴 AD-2：B60 是本轮字母范围内的 pilot；契约归属按 `review.entry_id` 判。"""
        owners: dict[str, str | None] = {}
        for p in sorted(CONTRACT_DIR.glob("*.json")):
            doc = _load(p)
            owners[p.name] = ((doc.get("review") or {}).get("entry_id"))
        assert set(v for v in owners.values() if v) == PILOT_CONTRACT_OWNERS, owners
        assert owners[CANDIDATE_CONTRACT_FILE] is None, (
            "candidate 契约的 review.entry_id 不再是 null ⇒ 反例分母失效"
        )
        candidate = _load(CONTRACT_DIR / CANDIDATE_CONTRACT_FILE)
        assert candidate.get("review_status") == "candidate"
        in_range = {
            o for o in PILOT_CONTRACT_OWNERS
            if o.startswith("xlsx/b60/") or _letters([o.split("/")[-1][3:5].upper()]) & set(ABCS)
        }
        assert "xlsx/b60/gt-b60-bundle" in in_range
        assert manifest_slice["slice_scope"]["excluded_pilot_entry_count"] == 1
        mine = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert not (mine & PILOT_CONTRACT_OWNERS), "pilot 混进了 independent_entries"

    def test_parent_duplicate_section_is_absent_because_in_scope_count_is_zero(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 AD-11：与 N 相反 —— 本轮 in-scope parent_duplicate 为 0 ⇒ 条件节必须缺席。"""
        mine = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        children = [e["entry_id"] for e in full_manifest["entries"]
                    if e.get("parent_entry_id") in mine]
        assert children == [], f"in-scope parent_duplicate 子入口现算非空：{children}"
        assert manifest_slice["slice_scope"]["in_scope_parent_duplicate_count"] == 0
        assert "parent_duplicate_summary" not in manifest_slice, (
            "未触发的条件节必须缺席（照抄 N 那轮的完整节即假红）"
        )
        global_children = sum(
            1 for e in full_manifest["entries"] if e.get("migration_state") == "parent_duplicate")
        assert manifest_slice["slice_scope"]["global_parent_duplicate_count"] == global_children
        assert global_children == 43, (
            f"AC 1.6 原文写「43 个父组件重复入口」，现算 {global_children} ⇒ 事实漂移需更新登记"
        )

    def test_untriggered_conditional_sections_are_absent(self, manifest_slice: dict, paradigm: dict) -> None:
        declared_absent = set(
            manifest_slice["paradigm_schema_conflict"]["new_section_not_in_schema"][
                "conditional_sections_absent"])
        declared_present = set(
            manifest_slice["paradigm_schema_conflict"]["new_section_not_in_schema"][
                "conditional_sections_present"])
        all_sections = {cs["section"] for cs in paradigm["slice_schema"]["conditional_sections"]}
        assert declared_present | declared_absent == all_sections, (
            declared_present, declared_absent, all_sections)
        for s in declared_absent:
            assert s not in manifest_slice, f"声明缺席的条件节 {s} 实际存在"
        for s in declared_present:
            assert s in manifest_slice, f"声明存在的条件节 {s} 实际缺席"

    def test_no_abcs_adapter_is_registered(self, manifest_slice: dict, full_manifest: dict) -> None:
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        for e in manifest_slice["independent_entries"]:
            assert e["adapter_id"] is None, e["entry_id"]
            assert by_id[e["entry_id"]].get("adapter_id") is None, (
                f"manifest 里 {e['entry_id']} 的 adapter_id 已非空 ⇒ slice 的 null 过时了"
            )


# ════════════════════════════════════════════════════════════════════════════
# 判据二：分组（本轮点名项 1）
# ════════════════════════════════════════════════════════════════════════════
class TestEntryGroupsAreRecomputable:

    def test_component_type_is_read_from_the_registry_module_edge(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 12.4**

        🔴 componentType 必须按**模块边**解析，不按符号名 grep。
        """
        for e in manifest_slice["independent_entries"]:
            computed = _component_types_of(e["host_path"])
            assert e["component_types"] == computed, (
                f"{e['entry_id']}: 声明 {e['component_types']} != 现算 {computed}"
            )
            for ct, ln in (e["component_type_registry_lines"] or {}).items():
                assert ln is not None, f"{e['entry_id']}: {ct} 缺 registry 行号"
                line = _cached_text(HTML_RENDERER_REGISTRY).split("\n")[ln - 1]
                assert f"'{ct}'" in line, f"{e['entry_id']}: registry#L{ln} 不是 {ct} 的声明行：{line!r}"

    def test_persistence_channel_is_read_from_real_http_sites(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            computed = _channel_of(e["host_path"])
            assert e["html_counterpart"]["store"] == computed, (
                f"{e['entry_id']}: 声明通道 {e['html_counterpart']['store']} != 现算 {computed}"
            )

    def test_group_membership_recomputes_from_both_dimensions(self, manifest_slice: dict) -> None:
        groups = manifest_slice["entry_groups"]
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        seen: set[str] = set()
        for g in groups["groups"]:
            assert g["entry_ids"] == sorted(g["entry_ids"]), f"{g['group_id']} 未排序"
            assert len(set(g["entry_ids"])) == len(g["entry_ids"]), f"{g['group_id']} 有重复"
            assert g["entry_count"] == len(g["entry_ids"])
            for eid in g["entry_ids"]:
                assert eid not in seen, f"{eid} 出现在多个分组"
                seen.add(eid)
                e = by_id[eid]
                assert e["group_id"] == g["group_id"], (
                    f"{eid} 的 group_id={e['group_id']} 与所属分组 {g['group_id']} 不符")
                assert e["component_type_family"] == g["component_type_family"]
                assert _channel_of(e["host_path"]) == g["persistence_channel"]
            assert g["component_types"] == sorted({
                ct for eid in g["entry_ids"] for ct in by_id[eid]["component_types"]})
        assert seen == set(by_id), "分组未覆盖全部 entry"

    def test_group_counters_recompute(self, manifest_slice: dict) -> None:
        groups = manifest_slice["entry_groups"]
        c = groups["counters"]
        assert c["group_count"] == groups["group_count"] == len(groups["groups"])
        assert c["entry_count"] == len(manifest_slice["independent_entries"])
        assert c["families"] == len({g["component_type_family"] for g in groups["groups"]})
        assert c["channels"] == len({g["persistence_channel"] for g in groups["groups"]})
        assert c["groups_with_more_than_one_entry"] == sum(
            1 for g in groups["groups"] if g["entry_count"] > 1)
        assert c["singleton_groups"] == sum(1 for g in groups["groups"] if g["entry_count"] == 1)
        assert c["group_count"] == c["groups_with_more_than_one_entry"] + c["singleton_groups"]

    def test_grouping_is_not_by_wp_code_letter(self, manifest_slice: dict) -> None:
        """🔴 分组**不得**退化成「按 wp_code 字母硬分」—— 否则本轮点名项没落实。"""
        groups = manifest_slice["entry_groups"]["groups"]
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        multi_letter = 0
        for g in groups:
            letters = set()
            for eid in g["entry_ids"]:
                pat = by_id[eid]["wp_code_pattern"]
                letters.add(pat[0].upper() if pat else "?")
            if len(letters) > 1:
                multi_letter += 1
        letter_groups = defaultdict(set)
        for eid, e in by_id.items():
            pat = e["wp_code_pattern"]
            letter_groups[pat[0].upper() if pat else "?"].add(e["group_id"])
        split_letters = sum(1 for L, gs in letter_groups.items() if len(gs) > 1)
        assert split_letters >= 2, (
            f"只有 {split_letters} 个字母被拆进多个分组 ⇒ 分组与「按字母分」几乎同构，"
            "本轮点名的「按 componentType/持久化通道分组」没落实"
        )

    def test_family_rules_are_declared_and_exhaustive(self, manifest_slice: dict) -> None:
        groups = manifest_slice["entry_groups"]
        declared = {r["family"] for r in groups["component_type_family_rules"]}
        used = {g["component_type_family"] for g in groups["groups"]}
        assert used <= declared, f"用到了未声明规则的家族：{sorted(used - declared)}"

    def test_multi_component_type_and_registry_absent_families_are_real(
        self, manifest_slice: dict
    ) -> None:
        """AD-9 / BP-11 / BP-12：两个特殊家族必须有真实承载者。"""
        by_family = defaultdict(list)
        for e in manifest_slice["independent_entries"]:
            by_family[e["component_type_family"]].append(e)
        multi = by_family.get("multi_component_type_single_host", [])
        assert multi, "multi_component_type_single_host 家族为空 ⇒ BP-11 无承载者"
        for e in multi:
            assert len(_component_types_of(e["host_path"])) > 1, e["entry_id"]
        absent = by_family.get("not_in_html_renderer_registry", [])
        assert absent, "not_in_html_renderer_registry 家族为空 ⇒ BP-12 无承载者"
        for e in absent:
            assert _component_types_of(e["host_path"]) == [], e["entry_id"]

    def test_one_adapter_serves_many_wp_codes(self, manifest_slice: dict) -> None:
        """AD-9：`c-control-test` 一条 entry 覆盖 28 个 wp_code；`a-program-console` 32 个。"""
        ct2codes = _ct_to_wp_codes()
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        cctl = by_id["xlsx/gt-c-control-test"]
        assert cctl["component_types"] == ["c-control-test"]
        assert cctl["wp_code_count_via_component_type"] == len(ct2codes["c-control-test"])
        assert cctl["wp_codes_via_component_type"] == ct2codes["c-control-test"]
        assert cctl["wp_code_count_via_component_type"] >= 20, (
            "c-control-test 的 wp_code 数骤降 ⇒ AD-9 的事实漂移"
        )
        prog = [f for f in manifest_slice["business_model_projection"]["families"]
                if f["family"] == "program_table"][0]
        assert prog["wp_code_count"] == len(ct2codes["a-program-console"])


# ════════════════════════════════════════════════════════════════════════════
# 判据三：裁决合法性（AP-1 / SR-3 / SR-4 / SR-5）
# ════════════════════════════════════════════════════════════════════════════
class TestAdjudicationLegality:

    def test_every_entry_has_a_binary_html_counterpart_verdict(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.8**"""
        for e in manifest_slice["independent_entries"]:
            assert e["html_counterpart_verdict"] in HTML_COUNTERPART_VERDICTS, e["entry_id"]
            assert e["html_counterpart_source_refs"], e["entry_id"]

    def test_no_pure_oo_entry_exists_in_this_slice(self, manifest_slice: dict) -> None:
        """🔴 AC 12.8 的判据是「无 HTML 对端」；本轮 46 条现算全部 exists ⇒ 禁 single_onlyoffice。"""
        for e in manifest_slice["independent_entries"]:
            computed = _channel_of(e["host_path"])
            assert computed != "none_detected", (
                f"{e['entry_id']}: 现算持久化通道为空 ⇒ verdict 可能应为 none，需重新调查"
            )
            assert e["html_counterpart_verdict"] == "exists", e["entry_id"]
            assert e["capability"] != "single_onlyoffice", e["entry_id"]

    def test_single_onlyoffice_requires_no_html_counterpart(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            if e["capability"] == "single_onlyoffice":
                assert e["html_counterpart_verdict"] == "none", e["entry_id"]

    def test_adjudication_reason_is_not_circular(self, manifest_slice: dict, paradigm: dict) -> None:
        """**Validates: Requirements 12.8** —— AP-1：禁用「本任务产物尚不存在」当裁决理由。"""
        ap1 = next(a for a in paradigm["adjudication_criteria"]["anti_patterns"]
                   if a["id"] == "AP-1")
        markers = ap1["circular_reason_markers"]
        for e in manifest_slice["independent_entries"]:
            if e["capability"] != "single_onlyoffice":
                continue
            blob = json.dumps(e["adjudication"], ensure_ascii=False)
            hit = [m for m in markers if m in blob]
            assert not hit, f"{e['entry_id']} 的裁决理由是循环论证：{hit}"

    def test_capability_is_null_and_pending_fields_are_complete(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """**Validates: Requirements 1.3** —— SR-3 右支三字段齐备。"""
        schema = paradigm["slice_schema"]
        fields = schema["required_pending_verdict_fields"]
        enum = paradigm["adjudication_criteria"]["capability_enum"]
        bp_ids = {b["id"] for b in manifest_slice["blocking_preconditions"]}
        for e in manifest_slice["independent_entries"]:
            assert e["capability"] is None, e["entry_id"]
            for f in fields:
                assert f in e, f"{e['entry_id']} 缺 {f}"
            assert isinstance(e["capability_verdict_stage"], str)
            assert e["capability_verdict_stage"].strip()
            assert e["capability_target"] in enum, e["entry_id"]
            assert isinstance(e["capability_target_blocked_by"], list)
            assert e["capability_target_blocked_by"], e["entry_id"]
            unknown = set(e["capability_target_blocked_by"]) - bp_ids
            assert not unknown, f"{e['entry_id']} 引用了不存在的 BP：{sorted(unknown)}"

    def test_capability_matches_honest_capability(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            assert e["capability"] == e["adjudication"]["honest_capability"], e["entry_id"]

    def test_pending_entries_carry_no_identity(self, manifest_slice: dict, paradigm: dict) -> None:
        for f in paradigm["slice_schema"]["presence_required_value_may_be_null"]:
            for e in manifest_slice["independent_entries"]:
                assert f in e, f"{e['entry_id']} 缺键 {f}"
                assert e[f] is None, f"{e['entry_id']}.{f} 非 null"

    def test_adjudication_carries_both_negative_reasons(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            adj = e["adjudication"]
            assert adj["not_single_html_because"], e["entry_id"]
            assert adj["not_bidirectional_because"], e["entry_id"]

    def test_broken_or_missing_switch_is_not_read_as_a_single_html_reason(
        self, manifest_slice: dict
    ) -> None:
        """🔴 「没有开关」不是 AC 12.9 的判据；4 条无开关 entry 仍是待裁决。"""
        switch = manifest_slice["mode_switch_resolution"]
        no_switch = switch["no_switch_entries"]
        assert no_switch, "无开关 entry 现算为空 ⇒ AD-5 失去对象"
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        for eid in no_switch:
            e = by_id[eid]
            assert e["capability"] is None, eid
            assert "BP-10" in e["capability_target_blocked_by"], eid
            gate = _host_gate(e["host_path"])
            assert not gate["segmented_sites"] and not gate["mode_radio_sites"], eid
            assert gate["oo_mount_sites"], f"{eid} 连 OO 挂载点都没有 ⇒ 形态判断要重做"
        assert switch["why_no_switch_is_not_a_reason_to_adjudicate_single"]

    def test_docx_authoritative_template_is_not_read_as_single_html(
        self, manifest_slice: dict
    ) -> None:
        """🔴 AD-3 / BP-9：docx 权威册那 16 条是最像 single_html 的候选，实测不成立。"""
        docx_entries = [e for e in manifest_slice["independent_entries"]
                        if e["template_ref"].get("workbook_format") in ("docx", "doc")]
        assert docx_entries, "docx 权威册 entry 现算为空 ⇒ AD-3 / BP-9 失去对象"
        for e in docx_entries:
            assert e["capability"] is None, e["entry_id"]
            assert "BP-9" in e["capability_target_blocked_by"], e["entry_id"]
        router = _strip_comments(_cached_text(OO_ROUTER))
        assert re.search(r'_ext\s+in\s+\(\s*"doc"\s*,\s*"docx"', router), (
            "wp_onlyoffice_router 不再按扩展名把 docx 交给 OO ⇒ 「OO 侧有真实业务价值」这个"
            "结论的实证消失，BP-9 的说法要重写"
        )

    def test_manifest_mirror_divergence_is_registered_not_silently_equal(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 判据是「**必须不一致**且已登记 BP-3」，不是断言相等。"""
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        bp3 = next(b for b in manifest_slice["blocking_preconditions"] if b["id"] == "BP-3")
        for e in manifest_slice["independent_entries"]:
            src = by_id[e["entry_id"]]
            mirror = e["manifest_mirror"]
            assert mirror["capability"] == src.get("capability")
            assert mirror["html_store"] == src.get("html_store")
            assert mirror["capability"] != e["capability"], (
                f"{e['entry_id']}: mirror 与本 slice 的 capability 一致了 ⇒ BP-3 该解除"
            )
            assert mirror["why_not_adopted"], e["entry_id"]
            assert e["entry_id"] in bp3["entries"], e["entry_id"]

    def test_ac15_is_declared_not_applicable_and_ac14_is_the_live_one(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.4**"""
        s = manifest_slice["honest_adjudication_summary"]
        assert s["ac_15_not_applicable_because"]
        assert manifest_slice["mode_switch_resolution"]["live_ac_is_1_4"]
        for e in manifest_slice["independent_entries"]:
            gate = _host_gate(e["host_path"])
            assert not gate["claims_bidirectional_in_template"], (
                f"{e['entry_id']} 的模板里出现「可双向回写」⇒ 直接违反 AC 1.4"
            )

    def test_ac14_notice_single_source_exists_and_is_consumed_out_of_scope(
        self, manifest_slice: dict
    ) -> None:
        """🔴 分母非空：notice 组件被 40+ 个**非本 slice**宿主挂载 ⇒ 本轮 0 挂载是真缺口。"""
        node = manifest_slice["mode_switch_resolution"]["ac14_notice_single_source"]
        assert (ROOT / node["ts"]).is_file() and (ROOT / node["vue"]).is_file()
        prod, _ = _statement_edges_to(AC14_NOTICE_VUE)
        assert node["out_of_scope_consumer_count"] == len(prod), (
            f"声明 {node['out_of_scope_consumer_count']} 现算 {len(prod)}"
        )
        assert len(prod) >= 20, "notice 组件的非本 slice 消费方骤降 ⇒ 判据分母可疑"
        hosts = {e["host_path"] for e in manifest_slice["independent_entries"]}
        in_scope = [r for r in prod if r.split("#")[0] in hosts]
        assert node["in_scope_consumer_count"] == len(in_scope) == 0
        for e in manifest_slice["independent_entries"]:
            assert not _host_gate(e["host_path"])["mounts_ac14_notice"], e["entry_id"]
            assert "BP-7" in e["capability_target_blocked_by"], e["entry_id"]

    def test_all_blocking_preconditions_carry_task48_fields(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        extra = paradigm["slice_schema"]["effective_from_task_48"]["required_blocking_precondition"]
        for bp in manifest_slice["blocking_preconditions"]:
            for f in extra:
                assert f in bp and bp[f], f"{bp['id']} 缺/空 {f}"
            assert bp.get("consequence") or bp.get("observable_consequences"), bp["id"]
            for ref in bp["source_refs"]:
                p = ROOT / ref.split("#")[0]
                assert p.exists(), f"{bp['id']} 的 source_ref 不存在：{ref}"

    def test_every_blocking_precondition_is_referenced_by_someone(
        self, manifest_slice: dict
    ) -> None:
        """一条 BP 不被任何 entry 或章节引用 = 哑登记。"""
        referenced: set[str] = set()
        for e in manifest_slice["independent_entries"]:
            referenced |= set(e["capability_target_blocked_by"])
            for r in e["evidence"]["unverifiable_reasons"]:
                m = re.match(r"^(BP-\d+)", r)
                if m:
                    referenced.add(m.group(1))
        blob = json.dumps(
            {k: v for k, v in manifest_slice.items() if k != "blocking_preconditions"},
            ensure_ascii=False)
        for bp in manifest_slice["blocking_preconditions"]:
            if bp["id"] in referenced:
                continue
            assert bp.get("referenced_by_section"), f"{bp['id']} 无 entry 引用且未声明章节"
            assert bp["id"] in blob or bp["referenced_by_section"].split(".")[0] in manifest_slice, (
                f"{bp['id']} 声明的章节 {bp['referenced_by_section']} 不存在"
            )

    def test_entry_scoped_bps_only_name_their_own_entries(self, manifest_slice: dict) -> None:
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        for bp in manifest_slice["blocking_preconditions"]:
            for eid in bp.get("entries") or []:
                assert eid in by_id, f"{bp['id']} 点名了 slice 外的 entry {eid}"
                if bp["id"].startswith("BP-1") and bp["id"] in ("BP-14",):
                    continue
                assert bp["id"] in by_id[eid]["capability_target_blocked_by"], (
                    f"{bp['id']} 点名 {eid}，但该 entry 的 blocked_by 里没有它"
                )


# ════════════════════════════════════════════════════════════════════════════
# 判据四：HTML 对端 source-backed
# ════════════════════════════════════════════════════════════════════════════
class TestHtmlCounterpartIsSourceBacked:

    def test_source_refs_point_at_real_paths_and_lines(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.8**"""
        for e in manifest_slice["independent_entries"]:
            for ref in e["html_counterpart_source_refs"]:
                line = _line_at(ref)
                assert line.strip(), f"{e['entry_id']} 的 source_ref 指向空行：{ref}"

    def test_read_and_write_sites_are_the_real_calls(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            hc = e["html_counterpart"]
            if hc.get("read_source_ref"):
                line = _line_at(hc["read_source_ref"])
                assert "checklist-responses" in line and re.search(r"\.get\s*[(<]", line), (
                    f"{e['entry_id']} 的 read_source_ref 不是真读调用：{line.strip()[:120]!r}"
                )
            if hc.get("write_source_ref"):
                line = _line_at(hc["write_source_ref"])
                assert "checklist-responses" in line and re.search(r"\.(put|post)\s*[(<]", line), (
                    f"{e['entry_id']} 的 write_source_ref 不是真写调用：{line.strip()[:120]!r}"
                )

    def test_item_prefix_constants_are_read_from_the_owner_module(
        self, manifest_slice: dict
    ) -> None:
        """🔴 前缀常量必须现读 owner 模块的字面量，不按命名规律推断。"""
        checked = 0
        for e in manifest_slice["independent_entries"]:
            for pre in e["html_counterpart"].get("item_prefix_constants") or []:
                line = _line_at(pre["ref"])
                assert pre["name"] in line, (
                    f"{e['entry_id']}: {pre['ref']} 不是 {pre['name']} 的声明行：{line.strip()[:120]!r}")
                assert f"'{pre['value']}'" in line or f'"{pre["value"]}"' in line \
                    or f"`{pre['value']}`" in line, (
                    f"{e['entry_id']}: {pre['name']} 的字面量与声明不符：{line.strip()[:120]!r}")
                checked += 1
        assert checked > 0, "一个前缀常量都没核到 ⇒ 本条判据空跑"

    def test_channel_source_refs_really_contain_the_channel_literal(
        self, manifest_slice: dict
    ) -> None:
        for e in manifest_slice["independent_entries"]:
            for name, refs in e["html_counterpart"]["channel_source_refs"].items():
                rx = _CHANNELS[name]
                for ref in refs:
                    assert rx.search(_line_at(ref)), (
                        f"{e['entry_id']}: {name} 的 source_ref {ref} 那行没有该通道字面量")

    def test_template_ref_digests_recompute_for_resolvable_entries(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 6.10** —— 权威册 digest 现算比对，任一漂移 fail closed。"""
        resolved = 0
        for e in manifest_slice["independent_entries"]:
            tr = e["template_ref"]
            if tr["resolution_kind"] != "literal_sheet_name":
                assert tr.get("why_null"), e["entry_id"]
                continue
            if tr.get("workbook") is None:
                assert tr.get("why_null"), e["entry_id"]
                continue
            p = TEMPLATE_DIR / tr["workbook"]
            assert p.is_file(), f"{e['entry_id']} 的权威册不存在：{tr['workbook']}"
            assert p.stat().st_size == tr["size"], f"{e['entry_id']} 权威册 size 漂移"
            assert _sha256(p) == tr["sha256"], f"{e['entry_id']} 权威册 sha256 漂移"
            resolved += 1
        assert resolved >= 15, f"只有 {resolved} 条 entry 的权威册可现算 ⇒ 判据分母可疑"

    def test_literal_sheet_names_are_really_in_the_host(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            tr = e["template_ref"]
            if tr["resolution_kind"] != "literal_sheet_name":
                continue
            gate = _host_gate(e["host_path"])
            assert tr["sheet_name_literal"] in gate["literals"], (
                f"{e['entry_id']}: 声明字面量 {tr['sheet_name_literal']!r} 不在宿主的挂载点上")

    def test_runtime_expression_entries_really_have_no_literal(self, manifest_slice: dict) -> None:
        """AD-4 的反向判据：27 条声明为运行时表达式的 entry 必须真的没有字面量。"""
        n = 0
        for e in manifest_slice["independent_entries"]:
            if e["template_ref"]["resolution_kind"] != "runtime_sheet_name_expression":
                continue
            gate = _host_gate(e["host_path"])
            assert gate["literals"] == [], (
                f"{e['entry_id']} 声明为运行时表达式却有字面量 {gate['literals']}")
            assert gate["exprs"], f"{e['entry_id']} 既无字面量也无表达式 ⇒ 形态判断错"
            assert e["template_ref"]["sheet_name_exprs"] == gate["exprs"]
            n += 1
        assert n == manifest_slice["honest_adjudication_summary"][
            "entries_with_runtime_sheet_name_expression"]

    def test_template_resolution_uses_the_real_impl_resolver(self, manifest_slice: dict) -> None:
        """🔴 三边锁第三边：声明的册必须与 impl resolver 现算一致。"""
        finder = _load_module("_t57_finder", TEMPLATE_FINDER)
        for e in manifest_slice["independent_entries"]:
            tr = e["template_ref"]
            if tr["resolution_kind"] != "literal_sheet_name":
                continue
            got = finder.find_template_file_any(tr["sheet_name_literal"])
            expected = tr.get("workbook")
            if expected is None:
                assert got is None, (
                    f"{e['entry_id']}: 声明解析为 None，impl 现算得到 {got}")
            else:
                assert got is not None, f"{e['entry_id']}: impl 现算为 None"
                assert got.relative_to(TEMPLATE_DIR).as_posix() == expected, (
                    f"{e['entry_id']}: 声明 {expected} != impl 现算 "
                    f"{got.relative_to(TEMPLATE_DIR).as_posix()}")

    def test_authoritative_template_enumeration_matches_disk(self, manifest_slice: dict) -> None:
        tpl = manifest_slice["authoritative_templates"]
        declared = sorted(f["name"] for f in tpl["files"])
        computed: list[str] = []
        for letter in ABCS:
            for p in sorted((TEMPLATE_DIR / letter).iterdir()):
                if p.is_file() and not p.name.startswith("~$"):
                    computed.append(f"{letter}/{p.name}")
        computed += list(tpl["confirmation_workbook_refs"])
        assert declared == sorted(computed), (
            f"多写 {sorted(set(declared) - set(computed))[:5]} / "
            f"漏写 {sorted(set(computed) - set(declared))[:5]}")
        assert len(set(declared)) == len(declared), "模板清单有重复"

    def test_template_digests_and_formats_recompute(self, manifest_slice: dict) -> None:
        for f in manifest_slice["authoritative_templates"]["files"]:
            p = TEMPLATE_DIR / f["name"]
            assert p.is_file(), f["name"]
            assert p.stat().st_size == f["size"], f["name"]
            assert _sha256(p) == f["sha256"], f["name"]
            assert f["format"] == p.suffix.lower().lstrip("."), f["name"]

    def test_lock_file_policy_and_reference_copy_are_recomputed(
        self, manifest_slice: dict
    ) -> None:
        """🔴 参考副本状态必须现算 `is_dir()`，不得照抄上一轮。"""
        tpl = manifest_slice["authoritative_templates"]
        locks = [p.name for letter in ABCS for p in (TEMPLATE_DIR / letter).iterdir()
                 if p.is_file() and p.name.startswith("~$")]
        assert str(len(locks)) in tpl["lock_file_policy"], (
            f"锁文件现算 {len(locks)} 个，与声明文本不符：{tpl['lock_file_policy']}")
        ref_dir = ROOT / "基础数据" / "致同通用审计程序及底稿模板（2025年修订）"
        expected = "present" if ref_dir.is_dir() else "absent_on_this_machine"
        assert tpl["reference_copy_status"] == expected

    def test_format_distribution_recomputes(self, manifest_slice: dict) -> None:
        """🔴 AD-3：A/B/C/S 的格式分布必须现算（D~N 全是 xlsx，本轮不是）。"""
        tpl = manifest_slice["authoritative_templates"]
        for letter in ABCS:
            got = Counter(
                p.suffix.lower().lstrip(".") for p in (TEMPLATE_DIR / letter).iterdir()
                if p.is_file() and not p.name.startswith("~$"))
            assert dict(got) == tpl["format_distribution"][letter], (letter, got)
        assert any(v.get("docx") for v in tpl["format_distribution"].values()), (
            "四个目录都没有 docx ⇒ AD-3 的前提不成立，需重写")

    def test_template_owner_mapping_is_injective_not_bijective(self, manifest_slice: dict) -> None:
        """🔴 AD-4：本轮是**单射**不是双射（27 条运行时解析的 entry 无册）。"""
        owners = [f["belongs_to_entry"] for f in manifest_slice["authoritative_templates"]["files"]
                  if f["belongs_to_entry"]]
        assert len(owners) == len(set(owners)), "两本册指向同一 entry ⇒ 单射被破坏"
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert set(owners) <= ids, f"册指向 slice 外 entry：{sorted(set(owners) - ids)}"
        assert len(owners) < len(ids), (
            "册↔entry 变成满射了 ⇒ AD-4 的「单射不是双射」前提消失，判据要升级")
        for f in manifest_slice["authoritative_templates"]["files"]:
            if f["belongs_to_entry"] is None:
                assert f.get("excluded_reason"), f["name"]
                assert f.get("excluded_reason_class"), f["name"]


# ════════════════════════════════════════════════════════════════════════════
# 判据五：AC 1.6 跨循环函证复用（本轮点名项 2）
# ════════════════════════════════════════════════════════════════════════════
def _confirmation_component_types() -> list[str]:
    src = _cached_text(HTML_RENDERER_REGISTRY)
    return sorted(set(re.findall(r"^\s*componentType:\s*'(confirmation-[^']+)'", src, re.M)))


def _confirmation_workbooks_on_disk() -> list[str]:
    out = []
    for letter in CONFIRMATION_CYCLES:
        d = TEMPLATE_DIR / letter
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            #: 🔴 CJK 在 Python 里算 `\w` ⇒ 提取码不能用 `\b`（Task 56 的教训）。
            if p.is_file() and not p.name.startswith("~$") and re.match(rf"^{letter}0[\s\-]", p.name):
                out.append(f"{letter}/{p.name}")
    return sorted(out)


class TestAc16ConfirmationAdapterReuse:

    def test_component_types_and_workbooks_recompute(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.6, 12.4**"""
        node = manifest_slice["confirmation_adapter_reuse"]
        cts = _confirmation_component_types()
        assert node["component_type_count"] == len(cts), (node["component_type_count"], len(cts))
        declared = [f["component_type"] for f in node["families"]]
        assert declared == cts, (declared, cts)
        assert len(set(declared)) == len(declared)
        wbs = _confirmation_workbooks_on_disk()
        assert node["workbook_count"] == len(wbs)
        assert sorted(w["rel"] for w in node["workbooks"]) == wbs

    def test_wp_codes_per_component_type_recompute(self, manifest_slice: dict) -> None:
        node = manifest_slice["confirmation_adapter_reuse"]
        ct2codes = _ct_to_wp_codes()
        total_ascii = 0
        total_cjk = 0
        for fam in node["families"]:
            codes = ct2codes.get(fam["component_type"], [])
            assert fam["wp_codes"] == codes, fam["component_type"]
            ascii_codes = [c for c in codes if re.match(r"^[A-Z]0", c)]
            cjk = [c for c in codes if c not in ascii_codes]
            assert fam["ascii_wp_codes"] == ascii_codes, fam["component_type"]
            assert fam["cjk_alias_keys"] == cjk, fam["component_type"]
            assert fam["cycles"] == sorted({c[0] for c in ascii_codes}), fam["component_type"]
            assert fam["cycle_count"] == len(fam["cycles"])
            total_ascii += len(ascii_codes)
            total_cjk += len(cjk)
        assert node["ascii_wp_code_count"] == total_ascii
        assert node["cjk_alias_key_count"] == total_cjk
        assert total_cjk > 0, (
            "🔴 中文表名别名键现算为 0 ⇒ 「override 表里还有中文键」这条事实漂移了；"
            "它是「循环归属只能靠 ^[A-Z]0 提取」的非空反向分母"
        )
        assert node["cycles"] == sorted({c for f in node["families"] for c in f["cycles"]})

    def test_the_family_really_has_no_entry_and_no_contract(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 AC 1.6 的核心：0 entry / 0 contract 是**实算**，不是「没查」。"""
        node = manifest_slice["confirmation_adapter_reuse"]
        ids = [e["entry_id"].lower() for e in full_manifest["entries"]]
        for letter in CONFIRMATION_CYCLES:
            hits = [i for i in ids if f"{letter.lower()}0" in i]
            assert hits == [], f"{letter}0 现算命中 entry：{hits}"
        assert node["entry_count_in_source_manifest"] == 0
        # 契约归属只能是 manifest 的 entry_id；而函证族在 manifest 里 0 条 entry（上面已证）
        # ⇒ 不存在任何一份契约能归属该族。两步推导，不用「entry_id 里含某子串」这类脆弱判据。
        owners = {
            ((_load(p).get("review") or {}).get("entry_id")) for p in CONTRACT_DIR.glob("*.json")}
        non_null = {o for o in owners if o}
        all_ids = {e["entry_id"] for e in full_manifest["entries"]}
        assert non_null <= all_ids, f"契约归属指向 manifest 外的 entry_id：{sorted(non_null - all_ids)}"
        assert non_null == PILOT_CONTRACT_OWNERS, non_null
        assert node["contract_count_attributed_to_the_family"] == 0

    def test_reuse_arithmetic_recomputes_and_is_not_a_vacuous_denominator(
        self, manifest_slice: dict
    ) -> None:
        """🔴 「1 份 vs N 份」的算术必须现算，且分母非空。"""
        node = manifest_slice["confirmation_adapter_reuse"]
        arith = node["reuse_arithmetic"]
        fams = node["families"]
        shared = [f for f in fams if f["cycle_count"] > 1]
        assert arith["contracts_if_one_per_cycle_entry_point"] == sum(
            f["cycle_count"] for f in fams)
        assert arith["contracts_if_adapter_is_reused"] == len(fams)
        assert arith["contracts_if_one_per_cycle_entry_point_shared_only"] == sum(
            f["cycle_count"] for f in shared)
        assert arith["contracts_if_adapter_is_reused_shared_only"] == len(shared)
        assert arith["actual_contracts_today"] == 0
        assert node["shared_component_type_count"] == len(shared)
        # 非空分母：复用比必须 > 1，否则「1 份 vs N 份」是重言式
        assert arith["contracts_if_one_per_cycle_entry_point"] > arith[
            "contracts_if_adapter_is_reused"], (
            "按循环入口计数与按 adapter 计数相等 ⇒ 没有任何 adapter 被多循环复用，AC 1.6 的判据空跑"
        )
        assert len(shared) >= 5, f"跨循环共享的 adapter 只有 {len(shared)} 个 ⇒ 分母可疑"

    def test_bp13_carries_the_family(self, manifest_slice: dict) -> None:
        bp = next(b for b in manifest_slice["blocking_preconditions"] if b["id"] == "BP-13")
        assert bp["entries"] == []
        assert bp["referenced_by_section"] == "confirmation_adapter_reuse"
        assert "AC 1.6" in bp["blocks"]

    def test_confirmation_workbooks_are_registered_but_unowned(self, manifest_slice: dict) -> None:
        tpl = manifest_slice["authoritative_templates"]
        refs = set(tpl["confirmation_workbook_refs"])
        assert refs == set(_confirmation_workbooks_on_disk())
        for f in tpl["files"]:
            if f["name"] in refs:
                assert f["belongs_to_entry"] is None, f["name"]
                assert f["excluded_reason_class"] == \
                    "confirmation_family_shared_across_cycles_no_entry", f["name"]


# ════════════════════════════════════════════════════════════════════════════
# 判据六：Property 22（本轮点名项 3）
# ════════════════════════════════════════════════════════════════════════════
def _scope_vue_files(manifest_slice: dict) -> list[pathlib.Path]:
    out: set[pathlib.Path] = set()
    for e in manifest_slice["independent_entries"]:
        host = ROOT / e["host_path"]
        out.add(host)
        if host.parent != WP_COMPONENTS:
            out |= {
                p for p in host.parent.rglob("*")
                if p.is_file() and p.suffix == ".vue" and "__tests__" not in p.as_posix()
            }
    return sorted(out)


def _dynamic_column_sites(manifest_slice: dict) -> list[dict]:
    out = []
    for e in manifest_slice["independent_entries"]:
        host = ROOT / e["host_path"]
        files = [host]
        if host.parent != WP_COMPONENTS:
            files += [p for p in sorted(host.parent.rglob("*"))
                      if p.is_file() and p.suffix == ".vue" and "__tests__" not in p.as_posix()]
        for f in files:
            blob = _strip_comments(_cached_text(f))
            for m in re.finditer(
                r"<el-table-column\b[^>]{0,400}?v-for\s*=\s*\"([^\"]+)\"[^>]{0,400}?>", blob, re.S
            ):
                tag = m.group(0)
                key = re.search(r""":key\s*=\s*"([^"]+)\"""", tag)
                label = re.search(r""":label\s*=\s*"([^"]+)\"""", tag)
                out.append({
                    "entry_id": e["entry_id"],
                    "site": f"{_rel(f)}#L{blob[: m.start()].count(chr(10)) + 1}",
                    "v_for": m.group(1),
                    "key_binding": key.group(1) if key else None,
                    "label_binding": label.group(1) if label else None,
                })
    return out


def _label_as_key_sites(manifest_slice: dict) -> list[dict]:
    out = []
    for e in manifest_slice["independent_entries"]:
        host = ROOT / e["host_path"]
        files = [host]
        if host.parent != WP_COMPONENTS:
            files += [p for p in sorted(host.parent.rglob("*"))
                      if p.is_file() and p.suffix == ".vue" and "__tests__" not in p.as_posix()]
        for f in files:
            for i, line in enumerate(_strip_comments(_cached_text(f)).split("\n"), 1):
                m = re.search(r""":key\s*=\s*"([^"]*\.(?:label|name|title))\"""", line)
                if m:
                    out.append({"entry_id": e["entry_id"], "site": f"{_rel(f)}#L{i}",
                                "key_binding": m.group(1)})
    return out


class TestProperty22DynamicColumnIdentity:

    def test_the_denominator_is_non_empty_and_recomputes(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 6.2**

        🔴 本 spec 里 Property 22 **首次拿到非空分母**（I~N 六轮都是空分母不宣称）。
        """
        node = manifest_slice["dynamic_column_identity"]
        cols = _dynamic_column_sites(manifest_slice)
        labels = _label_as_key_sites(manifest_slice)
        assert node["dynamic_column_site_count"] == len(cols), (
            node["dynamic_column_site_count"], len(cols))
        assert node["label_as_key_site_count"] == len(labels)
        assert node["denominator_is_non_empty"] is True
        assert cols, "动态列站点现算为空 ⇒ 分母空跑，本 Property 不得宣称任何结论"
        declared_sites = [c["site"] for c in node["dynamic_column_sites"]]
        assert declared_sites == [c["site"] for c in cols]
        assert len(set(declared_sites)) == len(declared_sites)
        assert [s["site"] for s in node["label_as_key_sites"]] == [s["site"] for s in labels]

    def test_ac_6_4_text_is_verbatim(self, manifest_slice: dict) -> None:
        """AC 6.4 原文逐字（禁转述）。"""
        node = manifest_slice["dynamic_column_identity"]
        req = (ROOT / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
               / "requirements.md").read_text(encoding="utf-8")
        hit = [l.strip()[len("6.4. "):] for l in req.split("\n") if l.strip().startswith("6.4. ")]
        assert hit, "requirements.md 里找不到 AC 6.4"
        assert node["ac_6_4_text"] == hit[0], (node["ac_6_4_text"], hit[0])

    def test_every_dynamic_column_keeps_key_and_label_separate(self, manifest_slice: dict) -> None:
        """列这一层：`:key` 与 `:label` 必须**分别绑定**（AC 6.4 前半句）。"""
        cols = _dynamic_column_sites(manifest_slice)
        same = [c for c in cols if c["key_binding"] and c["label_binding"]
                and c["key_binding"] == c["label_binding"]]
        assert same == [], f"有列把 key 与 label 绑成同一表达式：{same}"
        label_keyed = [c for c in cols if c["key_binding"]
                       and re.search(r"\.(label|name|title)\b", c["key_binding"])]
        assert label_keyed == [], f"有列用可改 label 作 key：{label_keyed}"

    def test_the_three_defects_are_real_and_registered(self, manifest_slice: dict) -> None:
        """三处缺陷逐条现读源码验证（不是自述）。"""
        node = manifest_slice["dynamic_column_identity"]
        assert len(node["defects"]) == 3
        ids = {d["id"] for d in node["defects"]}
        assert ids == {"P22-D1", "P22-D2", "P22-D3"}
        by_id = {d["id"]: d for d in node["defects"]}

        d1 = by_id["P22-D1"]
        line = _line_at(d1["site"])
        assert re.search(r"v-for=\"\(_, i\) in 5\"", line), line.strip()[:140]
        assert ':key="i"' in line, "A38 的列 key 不再是裸下标 ⇒ P22-D1 可解除"
        assert re.search(r"recoverable\.dcf\.cash_flows\[i\]", _line_at(d1["value_binding_site"]))

        d2 = by_id["P22-D2"]
        assert "peer1" in _line_at(d2["site"])
        col_line = _line_at(d2["column_source_ref"])
        assert "industry_comparison" in col_line
        blob = _strip_comments(_cached_text(ROOT / HOSTS_B14))
        assert "'peer2'" in blob and "'peer3'" not in blob, (
            "B14 行业对标已支持第 3 家对标公司 ⇒ P22-D2 可解除"
        )

        d3 = by_id["P22-D3"]
        assert d3["sites"], "P22-D3 的站点为空"
        for s in d3["sites"]:
            assert re.search(r""":key\s*=\s*"[^"]*\.(label|name|title)\"""", _line_at(s)), s

        for d in node["defects"]:
            assert "BP-14" in d["registered_as"]
        bp = next(b for b in manifest_slice["blocking_preconditions"] if b["id"] == "BP-14")
        assert "Property 22" in bp["blocks"] and "AC 6.4" in bp["blocks"]

    def test_the_verdict_does_not_overclaim(self, manifest_slice: dict) -> None:
        """🔴 分母非空但有缺陷 ⇒ 结论必须是 PARTIAL，不得写成通过。"""
        node = manifest_slice["dynamic_column_identity"]
        assert "PARTIAL" in node["verdict"]
        den = manifest_slice["property_denominators"]["property_22"]
        assert den["denominator_is_empty"] is False
        assert "PARTIAL" in den["claim"]
        pv = next(p for p in manifest_slice["properties_verified"] if p["property"] == 22)
        assert "PARTIAL" in pv["claim"]

    def test_property_23_is_not_claimed(self, manifest_slice: dict) -> None:
        """🔴 本轮点名的是 Property 22 而**不是** 23（前六轮点名 23）。"""
        props = {p["property"] for p in manifest_slice["properties_verified"]}
        assert props == {3, 22, 69, 70}, props
        assert any("Property 23" in s
                   for s in manifest_slice["property_denominators"]["not_claimed_at_all"])


HOSTS_B14 = "audit-platform/frontend/src/components/workpaper/GtB14DueDiligenceReport.vue"


# ════════════════════════════════════════════════════════════════════════════
# 判据七：dynamic_row_identity 条件节
# ════════════════════════════════════════════════════════════════════════════
class TestDynamicRowIdentity:

    def test_section_declares_forbidden_kinds_and_no_table_uses_them(
        self, manifest_slice: dict
    ) -> None:
        node = manifest_slice["dynamic_row_identity"]
        assert node["forbidden_identity_kinds"]
        for t in node["tables"]:
            assert t["row_identity"]["kind"] not in node["forbidden_identity_kinds"], t["table_key"]

    def test_every_table_verdict_follows_from_its_kind(self, manifest_slice: dict) -> None:
        node = manifest_slice["dynamic_row_identity"]
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for t in node["tables"]:
            assert t["entry_id"] in ids, t["table_key"]
            ri = t["row_identity"]
            if t["verdict"] == "DEFECT":
                assert ri.get("violates_forbidden_identity_kind") in node["forbidden_identity_kinds"], (
                    t["table_key"])
                assert t["registered_as"], t["table_key"]
            else:
                assert t["verdict"] == "CLEAN", t["table_key"]
                assert not ri.get("violates_forbidden_identity_kind"), t["table_key"]
                assert t["registered_as"] == [], t["table_key"]

    def test_all_row_identity_source_refs_resolve(self, manifest_slice: dict) -> None:
        for t in manifest_slice["dynamic_row_identity"]["tables"]:
            assert _line_at(t["row_count_source"]).strip(), t["table_key"]
            for k, v in t["row_identity"].items():
                if k.endswith("source_ref") and v:
                    assert _line_at(v).strip(), f"{t['table_key']}.{k}"

    def test_defect_tables_source_refs_carry_the_expected_tokens(
        self, manifest_slice: dict
    ) -> None:
        """🔴 缺陷 source_ref 那行必须真的含缺陷形态（防「指错行」）。"""
        expect = {
            "b14_chapter_table_rows": r"rowIndex",
            "b23_sub_rows": r"\bidx\b",
            "b50_account_assertion_matrix_rows": r"row\.name",
        }
        for t in manifest_slice["dynamic_row_identity"]["tables"]:
            if t["verdict"] != "DEFECT":
                continue
            pat = expect[t["table_key"]]
            line = _line_at(t["row_identity"]["source_ref"])
            assert re.search(pat, line), f"{t['table_key']}: {line.strip()[:140]!r} 不含 {pat}"

    def test_clean_tables_really_address_rows_by_stable_id(self, manifest_slice: dict) -> None:
        for t in manifest_slice["dynamic_row_identity"]["tables"]:
            if t["verdict"] != "CLEAN":
                continue
            f = t["row_identity"]["identity_field"]
            assert f, t["table_key"]
            line = _line_at(t["row_identity"]["source_ref"])
            assert f in line, f"{t['table_key']}: {line.strip()[:140]!r} 不含身份字段 {f}"
            assert not re.search(r"\$index|\bidx\b|\bindex\b", line), (
                f"{t['table_key']} 声明 CLEAN 但 source_ref 那行含下标：{line.strip()[:140]!r}")

    def test_the_n_style_positional_persistence_scanner_finds_nothing_here(self) -> None:
        """🔴 AD 反向断言：N 那套 ``itemId: `…-${index}` `` 扫描器在本轮 0 命中。"""
        rx = re.compile(r"""itemId\s*:\s*`[^`]*\$\{\s*(?:n|i|idx|index)\s*\}""")
        hits = []
        for p in WP_COMPONENTS.rglob("*"):
            if not p.is_file() or p.suffix not in (".ts", ".vue"):
                continue
            rel = p.relative_to(WP_COMPONENTS).as_posix()
            if "__tests__" in rel:
                continue
            if not (re.match(r"^Gt[ABCS]\d", rel) or re.match(r"^s\d", rel)
                    or re.match(r"^b60/", rel) or re.match(r"^composables/use[ABCS]\d", rel)):
                continue
            for i, line in enumerate(_strip_comments(_cached_text(p)).split("\n"), 1):
                if rx.search(line):
                    hits.append(f"{_rel(p)}#L{i}")
        assert hits == [], f"N 式位置化持久化键扫描器在本轮有命中 {hits} ⇒ 形态判断要重做"

    def test_row_identity_counters_recompute(self, manifest_slice: dict) -> None:
        node = manifest_slice["dynamic_row_identity"]
        c = node["counters"]
        assert c["tables_total"] == len(node["tables"])
        assert c["tables_with_defect"] == sum(1 for t in node["tables"] if t["verdict"] == "DEFECT")
        assert c["tables_clean"] == sum(1 for t in node["tables"] if t["verdict"] == "CLEAN")
        assert c["tables_total"] == c["tables_with_defect"] + c["tables_clean"]
        assert c["entries_with_defect"] == len({
            t["entry_id"] for t in node["tables"] if t["verdict"] == "DEFECT"})


# ════════════════════════════════════════════════════════════════════════════
# 判据八：mode_switch_resolution（AC 1.4）
# ════════════════════════════════════════════════════════════════════════════
class TestModeSwitchResolution:

    def test_per_entry_verdicts_are_from_a_closed_enum_and_recompute(
        self, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.4**"""
        node = manifest_slice["mode_switch_resolution"]
        allowed = set(node["verdict_allowed_values"])
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        assert set(node["per_entry_verdict"]) == set(by_id)
        for eid, verdict in node["per_entry_verdict"].items():
            assert verdict in allowed, (eid, verdict)
            gate = _host_gate(by_id[eid]["host_path"])
            has_switch = bool(gate["segmented_sites"] or gate["mode_radio_sites"])
            gated = bool(gate["mode_gated_oo_mount_sites"])
            expected = ("redeemable" if has_switch and gated
                        else "inert" if has_switch else "no_switch_at_all")
            assert verdict == expected, f"{eid}: 声明 {verdict} 现算 {expected}"
            assert by_id[eid]["dual_mode_carrier"]["switch_verdict"] == verdict

    def test_redeemable_switch_has_all_three_elements(self, manifest_slice: dict) -> None:
        node = manifest_slice["mode_switch_resolution"]
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        n = 0
        for eid, verdict in node["per_entry_verdict"].items():
            if verdict != "redeemable":
                continue
            gate = _host_gate(by_id[eid]["host_path"])
            assert gate["segmented_sites"] or gate["mode_radio_sites"], eid
            assert gate["mode_gated_oo_mount_sites"], eid
            #: 🔴 第三要素必须是「**开关写的正是门控那个变量**」。
            #: 只问「文件里有没有任何 `xxxMode = `」会被 `const editorMode = ref(...)`
            #: 这类**声明**满足 ⇒ 把开关的 v-model 换成别的名字仍然全绿（首版实测 M18 判 GREEN）。
            assert gate["gate_mode_vars"], f"{eid}: 门控表达式里取不到 mode 变量名"
            src = _strip_comments(_cached_text(ROOT / by_id[eid]["host_path"]))
            lines = src.split("\n")
            #: 🔴 `<el-segmented>` 常写成**多行**（`GtA112DualChecklist.vue` 的 `v-model`
            #: 在标签起始行的**下一行**）⇒ 必须取整个标签块，只看起始行会假红。
            blocks = [_tag_block_from(lines, i)
                      for i in gate["segmented_sites"] + gate["mode_radio_sites"]]
            bound_syms: set[str] = set()
            for b in blocks:
                bound_syms |= set(re.findall(
                    r"""v-model\s*=\s*["']\s*([\w.]+?)(?:\.value)?\s*["']""", b))
                bound_syms |= set(re.findall(
                    r"""@(?:change|update:model-value)\s*=\s*["']\s*([\w.]+)""", b))
            #: 绑定值可能是**点路径**（`dualMode.onModeChange` —— 共享载体对象上的回调）⇒
            #: 根段也算绑定符号，否则用共享载体的宿主会假红。
            bound_syms |= {s.split(".")[0] for s in bound_syms}
            assert bound_syms, f"{eid}: 开关标签块里取不到 v-model / @change 绑定的符号"
            gate_vars = set(gate["gate_mode_vars"])
            #: 🔴 判据必须把「开关绑的符号」与「门控用的变量」**串起来**：
            #: 只问「文件里有没有任何 `xxxMode = `」会被 `const editorMode = ref(...)` 的**声明**
            #: 甚至别处一次无关的 `editorMode.value = 'structured'` 满足 ⇒ 把开关的 v-model 换成
            #: 别的名字仍然全绿（首版实测 M18 判 GREEN）。两条合法链：
            #: ① 绑的就是门控变量本身；② 绑的符号被宿主 `watch(...)` 接住（切换走副作用改门控变量，
            #:    `GtA51CashflowAudit.vue` 的 `viewMode → watch → switchToExcel → mode.value`）。
            direct = bool(bound_syms & gate_vars)
            watched = any(
                re.search(rf"watch\(\s*(\(\s*\)\s*=>\s*)?{re.escape(s)}\b", src)
                for s in bound_syms)
            assert direct or watched, (
                f"{eid}: 开关绑定 {sorted(bound_syms)}，门控变量 {sorted(gate_vars)}，"
                "两者既不相同也没有 watch 把前者接住 ⇒ 第三要素不成立"
                "（开关切了也不会改变 OO 挂载点的显示）")
            n += 1
        assert n == node["counters"]["entries_with_redeemable_switch"]
        assert n >= 30, f"redeemable 只有 {n} 条 ⇒ 分母可疑"

    def test_inert_family_is_empty_and_that_is_a_recomputed_fact(
        self, manifest_slice: dict
    ) -> None:
        """🔴 AD-5：本轮 inert = 0（与 N 的 2 条相反）—— 0 也要落成判据。"""
        node = manifest_slice["mode_switch_resolution"]
        assert node["counters"]["entries_with_inert_switch"] == 0
        inert = [k for k, v in node["per_entry_verdict"].items() if v == "inert"]
        assert inert == []
        noop = []
        for e in manifest_slice["independent_entries"]:
            src = _strip_comments(_cached_text(ROOT / e["host_path"]))
            if re.search(r"onModeChange\s*:\s*\(\s*\)\s*=>\s*\{\s*\}", src):
                noop.append(e["entry_id"])
        assert noop == [], f"N 式 inert 形态（空 onModeChange）在本轮有命中 {noop}"

    def test_switch_counters_recompute(self, manifest_slice: dict) -> None:
        node = manifest_slice["mode_switch_resolution"]
        c = node["counters"]
        ents = manifest_slice["independent_entries"]
        gates = {e["entry_id"]: _host_gate(e["host_path"]) for e in ents}
        assert c["hosts_with_segmented_site"] == sum(
            1 for g in gates.values() if g["segmented_sites"])
        assert c["hosts_with_oo_mount"] == sum(1 for g in gates.values() if g["oo_mount_sites"])
        assert c["oo_mounts_total"] == sum(len(g["oo_mount_sites"]) for g in gates.values())
        assert c["oo_mounts_mode_gated"] == sum(
            len(g["mode_gated_oo_mount_sites"]) for g in gates.values())
        assert c["oo_mounts_sheet_fallthrough"] == sum(
            len(g["sheet_fallthrough_sites"]) for g in gates.values())
        assert c["oo_mounts_total"] == c["oo_mounts_mode_gated"] + c["oo_mounts_sheet_fallthrough"], (
            "OO 挂载点必须被两类角色完全划分（无 unconditional 剩余）")
        assert c["hosts_calling_legacy_health_endpoint_directly"] == sum(
            1 for g in gates.values() if g["calls_legacy_health"])
        assert c["hosts_calling_legacy_config_endpoint_directly"] == sum(
            1 for g in gates.values() if g["calls_legacy_config"])
        assert c["entries_mounting_the_ac14_notice"] == 0
        assert c["hosts_claiming_bidirectional_in_template"] == 0
        assert (c["entries_with_redeemable_switch"] + c["entries_with_inert_switch"]
                + c["entries_with_no_switch_at_all"]) == len(ents)

    def test_health_endpoint_callers_are_non_vacuous(self, manifest_slice: dict) -> None:
        """🔴 本轮**有** 15 个宿主直调 legacy health（M/L 两轮都是 0）—— 非零也要落成判据。"""
        c = manifest_slice["mode_switch_resolution"]["counters"]
        assert c["hosts_calling_legacy_health_endpoint_directly"] > 0, (
            "现算 0 个宿主直调 health ⇒ 该计数的事实漂移了")
        assert c["hosts_calling_legacy_config_endpoint_directly"] == 0, (
            "现算有宿主直调 onlyoffice-config ⇒ 需登记新 BP")


# ════════════════════════════════════════════════════════════════════════════
# 判据九：dual_mode_carrier_inventory + 只投影既有业务模型（本轮点名项 4）
# ════════════════════════════════════════════════════════════════════════════
class TestDualModeCarrierInventory:

    def test_shared_carrier_edges_recompute_both_ways(self, manifest_slice: dict) -> None:
        """🔴 每轮现算，禁照抄（M=29 / N=27 / 本轮=26+1）；声明与现算**两侧都验**。"""
        inv = manifest_slice["dual_mode_carrier_inventory"]
        hosts = {e["host_path"] for e in manifest_slice["independent_entries"]}
        for name, node in inv["shared_carriers"].items():
            p = ROOT / node["module"]
            assert p.is_file(), name
            prod, test = _statement_edges_to(p)
            assert node["production_edges"] == prod, (name, node["production_edge_count"], len(prod))
            assert node["production_edge_count"] == len(prod)
            assert node["test_edge_count"] == len(test)
            in_scope = [r for r in prod if r.split("#")[0] in hosts]
            assert node["in_scope_edges"] == in_scope, name
            assert node["in_scope_edge_count"] == len(in_scope)
            assert node["out_of_scope_edge_count"] == len(prod) - len(in_scope)
            barrel = [r for r in prod if "/index.ts#" in r]
            assert node["barrel_edges"] == barrel, name
            assert node["becomes_orphan_after_rewire"] == (len(prod) - len(in_scope) == 0), name

    def test_carrier_kind_partitions_the_entries(self, manifest_slice: dict) -> None:
        inv = manifest_slice["dual_mode_carrier_inventory"]
        c = inv["counters"]
        ents = manifest_slice["independent_entries"]
        kinds = Counter(e["dual_mode_carrier"]["kind"] for e in ents)
        assert c["entries_on_shared_carrier"] == kinds.get("shared_carrier_via_thin_wrapper", 0)
        assert c["entries_host_inline"] == kinds.get("host_inline_segmented", 0)
        assert c["entries_with_no_carrier"] == kinds.get("no_carrier", 0)
        assert sum(kinds.values()) == len(ents)
        assert c["shared_carriers_total"] == len(inv["shared_carriers"])
        owner: dict[str, str] = {}
        for name, node in inv["shared_carriers"].items():
            for r in node["in_scope_edges"]:
                owner[r.split("#")[0]] = name
        for e in ents:
            declared = e["dual_mode_carrier"]["shared_carrier_module"]
            assert declared == owner.get(e["host_path"]), e["entry_id"]
            if declared:
                assert e["dual_mode_carrier"]["kind"] == "shared_carrier_via_thin_wrapper"

    def test_no_per_entry_dual_mode_composable_exists(self, manifest_slice: dict) -> None:
        inv = manifest_slice["dual_mode_carrier_inventory"]
        assert inv["per_entry_dual_mode_composables"] == 0
        hits = [p.name for p in WP_COMPOSABLES.glob("*.ts")
                if re.match(r"^use[ABCS]\d.*DualMode\.ts$", p.name)]
        assert hits == []
        every = [p.name for p in WP_COMPOSABLES.rglob("*.ts") if "DualMode" in p.name]
        assert inv["all_dual_mode_modules_in_repo"] == len(every), (
            f"声明 {inv['all_dual_mode_modules_in_repo']} 现算 {len(every)}")

    def test_orphan_after_rewire_is_exactly_one(self, manifest_slice: dict) -> None:
        inv = manifest_slice["dual_mode_carrier_inventory"]
        got = sorted(n for n, v in inv["shared_carriers"].items()
                     if v["becomes_orphan_after_rewire"])
        assert inv["counters"]["carriers_becoming_orphan_after_rewire"] == len(got)
        assert got == ["useWpDualMode.ts"], got

    def test_barrel_edges_are_still_edges(self, manifest_slice: dict) -> None:
        """🔴 barrel 入边仍是边：只剩 barrel 的模块是**潜在** orphan，不是可立即删。"""
        inv = manifest_slice["dual_mode_carrier_inventory"]
        node = inv["shared_carriers"]["factories/createDualMode.ts"]
        assert node["barrel_edges"], "createDualMode 的 barrel 入边现算为空 ⇒ 本判据失去对象"
        assert node["becomes_orphan_after_rewire"] is False
        for r in node["barrel_edges"]:
            assert r.endswith(tuple(f"#L{i}" for i in range(1, 400))) or "#L" in r
            assert "/index.ts#" in r


class TestBusinessModelProjection:

    def test_every_family_is_project_only_and_invents_no_field(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.4** —— 只投影既有业务模型。"""
        node = manifest_slice["business_model_projection"]
        assert node["counters"]["families_total"] == len(node["families"]) == 4
        assert node["counters"]["new_business_fields_invented"] == 0
        ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for fam in node["families"]:
            assert fam["projection_verdict"].startswith("PROJECT_ONLY"), fam["family"]
            assert set(fam["in_scope_entry_ids"]) <= ids, fam["family"]
            assert fam["in_scope_entry_ids"], fam["family"]
            model = fam["existing_business_model"]
            assert model, fam["family"]
        assert node["counters"]["families_project_only"] == sum(
            1 for f in node["families"] if f["projection_verdict"].startswith("PROJECT_ONLY"))
        assert node["counters"]["families_deliberately_not_mapped"] == sum(
            1 for f in node["families"] if f.get("deliberately_not_mapped"))

    def test_owner_modules_exist_on_disk(self, manifest_slice: dict) -> None:
        for fam in manifest_slice["business_model_projection"]["families"]:
            for m in fam["existing_business_model"].get("owner_modules") or []:
                assert (ROOT / m).is_file(), f"{fam['family']}: owner 模块不存在 {m}"

    def test_program_and_control_wp_code_counts_recompute(self, manifest_slice: dict) -> None:
        ct2codes = _ct_to_wp_codes()
        for fam in manifest_slice["business_model_projection"]["families"]:
            ct = fam.get("component_type")
            if not ct:
                continue
            assert fam["wp_code_count"] == len(ct2codes[ct]), (fam["family"], ct)
            assert fam["wp_code_count"] > 20, (
                f"{fam['family']} 的 wp_code 数骤降 ⇒ 「一 adapter 多入口」的事实漂移")

    def test_attachment_family_is_deliberately_not_mapped(self, manifest_slice: dict) -> None:
        """宁缺勿造：附件/OCR 有意不映射，且这件事必须显式声明。"""
        fam = next(f for f in manifest_slice["business_model_projection"]["families"]
                   if f["family"] == "attachment_and_ocr")
        assert fam["deliberately_not_mapped"] is True
        assert "不映射" in fam["projection_verdict"]
        found = 0
        for eid in fam["in_scope_entry_ids"]:
            e = next(x for x in manifest_slice["independent_entries"] if x["entry_id"] == eid)
            host = ROOT / e["host_path"]
            files = [host]
            if host.parent != WP_COMPONENTS:
                files += [p for p in host.parent.rglob("*")
                          if p.is_file() and p.suffix in (".ts", ".vue")]
            if any("<el-upload" in _strip_comments(_cached_text(f)) for f in files):
                found += 1
        assert found >= 3, f"声明的附件族 entry 里只有 {found} 条真有 <el-upload> ⇒ 分母可疑"


# ════════════════════════════════════════════════════════════════════════════
# 判据十：Property 69（evidence）与 summary 计数
# ════════════════════════════════════════════════════════════════════════════
class TestProperty69EvidenceAndCounters:

    def test_unverifiable_entries_carry_non_empty_reasons(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 13.5** —— SR-7。"""
        for e in manifest_slice["independent_entries"]:
            ev = e["evidence"]
            if ev["verification_state"] == "UNVERIFIABLE":
                assert ev["unverifiable_reasons"], e["entry_id"]
                assert all(r.strip() for r in ev["unverifiable_reasons"]), e["entry_id"]

    def test_no_entry_claims_verified_without_a_run(self, manifest_slice: dict) -> None:
        """反向命题：没有 run 的 entry 不得声称 verified。"""
        for e in manifest_slice["independent_entries"]:
            ev = e["evidence"]
            if ev["sync_test_run_id"] is None:
                assert ev["verification_state"] != "VERIFIED", e["entry_id"]
                assert ev["required_scenario_set_digest"] is None, e["entry_id"]
                assert ev["browser_case"] is None and ev["contract_test"] is None, e["entry_id"]

    def test_unverifiable_reasons_mirror_the_blocked_by_list(self, manifest_slice: dict) -> None:
        for e in manifest_slice["independent_entries"]:
            got = [re.match(r"^(BP-\d+)", r).group(1) for r in e["evidence"]["unverifiable_reasons"]]
            assert got == e["capability_target_blocked_by"], e["entry_id"]

    def test_summary_counters_recompute_from_the_entries(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """**Validates: Requirements 12.1** —— SR-1 / SR-2 / SR-9。"""
        s = manifest_slice["honest_adjudication_summary"]
        ents = manifest_slice["independent_entries"]
        assert s["total_independent"] == len(ents) == \
            manifest_slice["slice_scope"]["independent_entry_count"]
        for cap in paradigm["adjudication_criteria"]["capability_enum"]:
            assert s[f"adjudicated_as_{cap}"] == sum(1 for e in ents if e["capability"] == cap)
        assert s["capability_verdict_pending"] == sum(1 for e in ents if e["capability"] is None)
        assert s["slice_counters"]["unadjudicated"] == s["capability_verdict_pending"]
        assert s["html_counterpart_exists"] == sum(
            1 for e in ents if e["html_counterpart_verdict"] == "exists")
        assert s["html_counterpart_none"] == sum(
            1 for e in ents if e["html_counterpart_verdict"] == "none")
        assert s["entries_left_unverifiable"] == sum(
            1 for e in ents if e["evidence"]["verification_state"] == "UNVERIFIABLE")
        assert s["blocking_preconditions_total"] == len(manifest_slice["blocking_preconditions"])
        assert s["reachable_hosts_in_scope"] == len(ents)
        assert s["entries_with_registry_component_type"] == sum(1 for e in ents if e["component_types"])
        assert s["entries_without_registry_component_type"] == sum(
            1 for e in ents if not e["component_types"])
        assert s["entries_with_multiple_component_types"] == sum(
            1 for e in ents if len(e["component_types"]) > 1)
        assert s["registry_component_type_total"] == len(_registry_pairs())

    def test_channel_counters_recompute(self, manifest_slice: dict) -> None:
        s = manifest_slice["honest_adjudication_summary"]
        ch = Counter(e["html_counterpart"]["store"] for e in manifest_slice["independent_entries"])
        assert s["entries_on_checklist_responses_only"] == ch.get("checklist_responses", 0)
        assert s["entries_on_field_overrides_only"] == ch.get("field_overrides", 0)
        assert s["entries_on_custom_cells_only"] == ch.get("custom_cells", 0)
        assert s["entries_on_checklist_plus_field_overrides"] == ch.get(
            "checklist_responses+field_overrides", 0)
        assert s["entries_on_all_three_channels"] == ch.get(
            "checklist_responses+field_overrides+custom_cells", 0)
        assert sum(ch.values()) == len(manifest_slice["independent_entries"])

    def test_template_counters_recompute(self, manifest_slice: dict) -> None:
        s = manifest_slice["honest_adjudication_summary"]
        tpl = manifest_slice["authoritative_templates"]
        assert s["authoritative_template_files"] == len(tpl["files"])
        assert s["template_files_with_owner_entry"] == sum(
            1 for f in tpl["files"] if f["belongs_to_entry"])
        assert s["template_files_without_owner_entry"] == sum(
            1 for f in tpl["files"] if not f["belongs_to_entry"])
        assert s["authoritative_template_files"] == (
            s["template_files_with_owner_entry"] + s["template_files_without_owner_entry"])
        assert s["authoritative_template_roots"] == len(tpl["roots"])
        assert s["confirmation_workbooks_registered"] == len(tpl["confirmation_workbook_refs"])
        kinds = Counter(e["template_ref"]["resolution_kind"]
                        for e in manifest_slice["independent_entries"])
        assert s["entries_with_literal_sheet_name"] == kinds["literal_sheet_name"]
        assert s["entries_with_runtime_sheet_name_expression"] == kinds[
            "runtime_sheet_name_expression"]
        fmts = Counter(e["template_ref"].get("workbook_format")
                       for e in manifest_slice["independent_entries"])
        assert s["entries_whose_authoritative_workbook_is_docx"] == fmts.get("docx", 0)
        assert s["entries_whose_authoritative_workbook_is_xlsx"] == fmts.get("xlsx", 0)
        assert s["entries_whose_authoritative_workbook_is_unresolved"] == fmts.get(None, 0)

    def test_counting_notes_cover_every_summary_counter(self, manifest_slice: dict) -> None:
        """🔴 覆盖面元判据（Task 54 的 M28/M29 教训）：并集必须覆盖全部数值键。"""
        s = manifest_slice["honest_adjudication_summary"]
        notes = s["counting_notes"]
        assert notes.get("coverage_meta_rule"), "counting_notes 缺覆盖面元规则"
        numeric = [k for k, v in s.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)]
        assert numeric, "summary 里没有数值键 ⇒ 判据空跑"
        blob = " || ".join(notes.values())
        missing = [k for k in numeric if k not in blob]
        assert missing == [], f"counting_notes 未覆盖：{missing}"

    def test_slice_counters_are_all_zero_except_unadjudicated(self, manifest_slice: dict) -> None:
        c = manifest_slice["honest_adjudication_summary"]["slice_counters"]
        assert c["fake_bidirectional_claimed_verified"] == 0
        assert c["bidirectional_unverified"] == 0
        assert c["stale_evidence"] == 0
        assert c["unadjudicated"] == len(manifest_slice["independent_entries"])
        assert c["how_to_read"], "计数为 0 的含义必须写明（禁解读为「已具备双向能力」）"

    def test_property_denominators_declare_what_is_not_claimed(self, manifest_slice: dict) -> None:
        dens = manifest_slice["property_denominators"]
        for key in ("property_3", "property_22", "property_69", "property_70"):
            node = dens[key]
            assert node["claim"], key
            assert isinstance(node["denominator_is_empty"], bool), key
            if node["denominator_is_empty"]:
                assert "不宣称通过" in node["claim"], key
                assert node["denominator_value"] == 0, key
            else:
                assert node["denominator_value"] > 0, key
        assert dens["not_claimed_at_all"]
        assert dens["ac_1_6_denominator"]["confirmation_reuse_denominator"]


# ════════════════════════════════════════════════════════════════════════════
# 判据十一：Property 70（跨 entry 隔离）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty70CrossEntryIsolation:

    def test_all_slices_are_pairwise_disjoint(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 12.10**

        🔴 配对数必须**现算** `len(sets)*(len(sets)-1)//2`，不得写死。
        """
        paths = _slice_paths_on_disk()
        sets: dict[str, set[str]] = {}
        for p in paths:
            sets[p.name] = {e["entry_id"] for e in _load(p)["independent_entries"]}
        assert SLICE_PATH.name in sets, "本 slice 未被 scan_glob 命中 ⇒ 命名不符 `*_cycle_manifest_slice.json`"
        names = sorted(sets)
        pairs = 0
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                overlap = sets[a] & sets[b]
                assert not overlap, f"{a} 与 {b} 重叠：{sorted(overlap)}"
                pairs += 1
        expected = len(sets) * (len(sets) - 1) // 2
        assert pairs == expected, (pairs, expected)
        assert manifest_slice["cross_entry_isolation"]["slice_count_including_self"] == len(sets)
        assert str(expected) in manifest_slice["cross_entry_isolation"]["pairwise_recipe"]

    def test_sibling_slices_declared_match_the_disk(self, manifest_slice: dict) -> None:
        declared = manifest_slice["sibling_slices"]
        computed = [_rel(p) for p in _slice_paths_on_disk() if p != SLICE_PATH]
        assert declared == sorted(computed), (declared, sorted(computed))
        assert len(declared) == 11, f"兄弟 slice 现算 {len(declared)} 份（应为 D~N 十一份）"
        for r in declared:
            assert (ROOT / r).is_file(), r

    def test_cross_entry_isolation_assertions_are_present(self, manifest_slice: dict) -> None:
        iso = manifest_slice["cross_entry_isolation"]
        assert iso["rule"] and isinstance(iso["assertions"], list) and iso["assertions"]
        assert iso["production_contract_files"] and iso["candidate_contract_files"]
        on_disk = sorted(p.name for p in CONTRACT_DIR.glob("*.json"))
        assert sorted(iso["production_contract_files"] + iso["candidate_contract_files"]) == on_disk

    def test_deletion_plan_paths_are_globally_unique_and_disjoint(
        self, deletion_plan: dict
    ) -> None:
        mine: set[str] = set()
        for key in ("delete_files", "delete_after_rewire", "latent_orphan_after_rewire"):
            for item in deletion_plan.get(key) or []:
                mine.add(item["path"] if isinstance(item, dict) else item)
        others: set[str] = set()
        for p in sorted(DATA.glob("workpaper_sync_*_deletion_plan.json")):
            if p == PLAN_PATH:
                continue
            blob = _load(p)
            for key in ("delete_files", "delete_after_rewire"):
                for item in blob.get(key) or []:
                    others.add(item["path"] if isinstance(item, dict) else item)
        assert not (mine & others), f"与既有 plan 的删除路径重叠：{sorted(mine & others)}"


# ════════════════════════════════════════════════════════════════════════════
# 判据十二：deletion plan 一致性
# ════════════════════════════════════════════════════════════════════════════
class TestDeletionPlanConsistency:

    def test_plan_mirrors_the_slice(self, deletion_plan: dict, manifest_slice: dict) -> None:
        assert deletion_plan["slice_ref"] == _rel(SLICE_PATH)
        assert deletion_plan["task"] == manifest_slice["task"] == "Task 57"
        assert deletion_plan["requirements_covered"] == manifest_slice["requirements_covered"]
        assert deletion_plan["properties_verified"] == [
            p["property"] for p in manifest_slice["properties_verified"]]

    def test_delete_files_is_empty_and_that_is_recomputed(self, deletion_plan: dict) -> None:
        """🔴 空数组是实算结果：现算 orphan dual-mode 模块数 == 0。"""
        assert deletion_plan["delete_files"] == []
        assert deletion_plan["delete_files_is_empty_because"]
        assert deletion_plan["counters"]["orphan_dual_mode_modules"] == 0
        assert deletion_plan["counters"]["per_entry_dual_mode_composables"] == 0
        hits = [p.name for p in WP_COMPOSABLES.glob("*.ts")
                if re.match(r"^use[ABCS]\d.*DualMode\.ts$", p.name)]
        assert hits == []

    def test_delete_after_rewire_is_non_empty_and_justified(
        self, deletion_plan: dict, manifest_slice: dict
    ) -> None:
        """**Validates: Requirements 1.7**"""
        items = deletion_plan["delete_after_rewire"]
        assert items, "delete_after_rewire 为空 ⇒ 「改线即可删」的结论消失，需重新核算"
        hosts = {e["host_path"] for e in manifest_slice["independent_entries"]}
        for it in items:
            p = ROOT / it["path"]
            assert p.is_file(), it["path"]
            prod, _ = _statement_edges_to(p)
            assert it["production_edge_count"] == len(prod), it["path"]
            in_scope = [r for r in prod if r.split("#")[0] in hosts]
            assert it["in_scope_edge_count"] == len(in_scope) == len(prod), (
                f"{it['path']} 仍有非本 slice 生产边 ⇒ 不得列入 delete_after_rewire")
            assert it["blocked_by"], it["path"]

    def test_latent_orphan_keeps_barrel_edges(self, deletion_plan: dict) -> None:
        for it in deletion_plan["latent_orphan_after_rewire"]:
            assert it["remaining_edges_after_rewire"], it["path"]
            for r in it["remaining_edges_after_rewire"]:
                assert "/index.ts#" in r, r
            assert it["why_not_in_delete_after_rewire"]

    def test_must_rewire_covers_every_host_exactly_once(
        self, deletion_plan: dict, manifest_slice: dict
    ) -> None:
        hosts = sorted({e["host_path"] for e in manifest_slice["independent_entries"]})
        declared = [x["host"] for x in deletion_plan["must_rewire"]]
        assert declared == sorted(declared), "must_rewire 未排序"
        assert len(set(declared)) == len(declared), "must_rewire 有重复宿主"
        assert declared == hosts, (set(declared) ^ set(hosts))
        by_host = defaultdict(list)
        for e in manifest_slice["independent_entries"]:
            by_host[e["host_path"]].append(e["entry_id"])
        for x in deletion_plan["must_rewire"]:
            assert x["entry_ids"] == sorted(by_host[x["host"]]), x["host"]
            assert x["blocked_by"], x["host"]

    def test_must_not_delete_files_all_exist(self, deletion_plan: dict) -> None:
        for x in deletion_plan["must_not_delete"]:
            assert (ROOT / x["path"]).is_file(), x["path"]
            assert x["why"] and x["recompute"], x["path"]
        assert deletion_plan["counters"]["must_not_delete"] == len(deletion_plan["must_not_delete"])

    def test_plan_reason_is_not_circular(self, deletion_plan: dict, paradigm: dict) -> None:
        ap1 = next(a for a in paradigm["adjudication_criteria"]["anti_patterns"]
                   if a["id"] == "AP-1")
        assert ap1["id"] == "AP-1"
        #: 🔴 允许 markdown 加粗标记落在两个词之间（`不是**裁决理由`）—— 连续子串判据会假红。
        disclaimer = re.compile(r"不是\*{0,2}裁决理由")
        assert disclaimer.search(deletion_plan["reason"]), (
            "计划的 reason 必须显式声明它**不是**裁决理由（AP-1）")
        markers = [m for m in ap1["circular_reason_markers"] if m in deletion_plan["reason"]]
        if markers:
            assert disclaimer.search(deletion_plan["reason"]), markers

    def test_plan_excludes_the_authoritative_templates(
        self, deletion_plan: dict, manifest_slice: dict
    ) -> None:
        """AP-2：不得为满足数字修改或删除权威模板。"""
        node = deletion_plan["must_not_delete_templates"]
        assert node["roots"] == manifest_slice["authoritative_templates"]["roots"]
        assert node["file_count"] == len(manifest_slice["authoritative_templates"]["files"])
        assert node["confirmation_workbooks"] == \
            manifest_slice["authoritative_templates"]["confirmation_workbook_refs"]
        deleted = {it["path"] for it in deletion_plan["delete_after_rewire"]}
        for r in node["roots"]:
            assert not any(d.startswith(r) for d in deleted)

    def test_plan_counters_recompute(self, deletion_plan: dict, manifest_slice: dict) -> None:
        c = deletion_plan["counters"]
        assert c["delete_files"] == len(deletion_plan["delete_files"])
        assert c["delete_after_rewire"] == len(deletion_plan["delete_after_rewire"])
        assert c["latent_orphan_after_rewire"] == len(deletion_plan["latent_orphan_after_rewire"])
        assert c["must_rewire_hosts"] == len(deletion_plan["must_rewire"])
        assert c["must_rewire_entries"] == len(manifest_slice["independent_entries"])
        inv = manifest_slice["dual_mode_carrier_inventory"]
        assert c["shared_dual_mode_carriers"] == inv["counters"]["shared_carriers_total"]
        assert c["entries_on_shared_carrier"] == inv["counters"]["entries_on_shared_carrier"]
        assert c["entries_host_inline"] == inv["counters"]["entries_host_inline"]
        assert c["entries_with_no_carrier"] == inv["counters"]["entries_with_no_carrier"]
        prod, test = _statement_edges_to(SHARED_BASE)
        assert c["shared_base_production_edges"] == len(prod)
        hosts = {e["host_path"] for e in manifest_slice["independent_entries"]}
        assert c["shared_base_in_scope_edges"] == len(
            [r for r in prod if r.split("#")[0] in hosts])


# ════════════════════════════════════════════════════════════════════════════
# 判据十三：形态差异与范式合规
# ════════════════════════════════════════════════════════════════════════════
class TestFormDifferences:

    def test_all_differences_carry_a_recompute_recipe(self, manifest_slice: dict) -> None:
        diffs = manifest_slice["abcs_form_differences"]
        assert len(diffs) >= 10, f"形态差异只登记了 {len(diffs)} 条"
        ids = [d["id"] for d in diffs]
        assert ids == sorted(ids, key=lambda x: int(x.split("-")[1])), "AD 编号未按序"
        assert len(set(ids)) == len(ids)
        for d in diffs:
            assert d["what"] and d["why_not_copyable"] and d["recompute_recipe"], d["id"]
            assert "value" in d, d["id"]

    def test_ad1_scope_arithmetic_closes(self, manifest_slice: dict, full_manifest: dict) -> None:
        d = next(x for x in manifest_slice["abcs_form_differences"] if x["id"] == "AD-1")
        v = d["value"]
        assert v["xlsx_independent_total"] == sum(
            1 for e in full_manifest["entries"]
            if e.get("document_type") == "xlsx" and e.get("independent_entry") is True)
        covered = set()
        for p in _slice_paths_on_disk():
            if p == SLICE_PATH:
                continue
            covered |= {e["entry_id"] for e in _load(p)["independent_entries"]}
        assert v["covered_by_d_to_n"] == len(covered)
        assert v["this_slice"] == len(manifest_slice["independent_entries"])
        assert v["abcs_letter_hits"] - v["excluded_pilot"] + v["pattern_less_shared"] == v["this_slice"]

    def test_ad10_shared_base_edges_are_recomputed_not_copied(self, manifest_slice: dict) -> None:
        """🔴 每轮现算，禁照抄（M=29 / N=27）。"""
        d = next(x for x in manifest_slice["abcs_form_differences"] if x["id"] == "AD-10")
        prod, test = _statement_edges_to(SHARED_BASE)
        assert d["value"]["production"] == len(prod)
        assert d["value"]["test"] == len(test)
        hosts = {e["host_path"] for e in manifest_slice["independent_entries"]}
        in_scope = [r for r in prod if r.split("#")[0] in hosts]
        assert d["value"]["in_scope"] == len(in_scope)
        assert sorted(d["value"]["in_scope_hosts"]) == sorted(
            pathlib.Path(r.split("#")[0]).name for r in in_scope)
        assert d["value"]["production"] not in (29,), (
            "共享基类生产边现算等于 M 那轮冻结的 29 ⇒ 需确认是真相等还是照抄")

    def test_ad12_grouping_counters_match_the_group_section(self, manifest_slice: dict) -> None:
        d = next(x for x in manifest_slice["abcs_form_differences"] if x["id"] == "AD-12")
        assert d["value"] == manifest_slice["entry_groups"]["counters"]


def _validator_module() -> ModuleType:
    return _load_module("_t57_paradigm_contract", CONTRACT_GUARD)


class TestParadigmCompliance:

    def test_the_slice_passes_the_paradigm_nominated_validator(self, manifest_slice: dict) -> None:
        """**Validates: Requirements 1.3, 12.1**"""
        mod = _validator_module()
        problems = mod.validate_slice_against_schema(manifest_slice)
        assert problems == [], "\n".join("  !! " + p for p in problems)

    def test_the_validator_really_catches_a_missing_pending_field(
        self, manifest_slice: dict
    ) -> None:
        mod = _validator_module()
        broken = json.loads(json.dumps(manifest_slice))
        broken["independent_entries"][0].pop("capability_target")
        problems = mod.validate_slice_against_schema(broken)
        assert any("capability_target" in p for p in problems), problems

    def test_the_validator_really_catches_a_counter_mismatch(self, manifest_slice: dict) -> None:
        mod = _validator_module()
        broken = json.loads(json.dumps(manifest_slice))
        broken["honest_adjudication_summary"]["total_independent"] += 1
        problems = mod.validate_slice_against_schema(broken)
        assert any("SR-1" in p for p in problems), problems

    def test_the_validator_really_catches_a_forbidden_identity_kind(
        self, manifest_slice: dict
    ) -> None:
        mod = _validator_module()
        broken = json.loads(json.dumps(manifest_slice))
        broken["dynamic_row_identity"]["tables"][0]["row_identity"]["kind"] = "array_index"
        problems = mod.validate_slice_against_schema(broken)
        assert any("forbidden_identity_kinds" in p for p in problems), problems

    def test_the_validator_really_catches_a_single_with_identity(
        self, manifest_slice: dict
    ) -> None:
        mod = _validator_module()
        broken = json.loads(json.dumps(manifest_slice))
        e = broken["independent_entries"][0]
        e["capability"] = "single_onlyoffice"
        e["adjudication"]["honest_capability"] = "single_onlyoffice"
        e["adapter_id"] = "fake"
        problems = mod.validate_slice_against_schema(broken)
        assert any("SR-5" in p for p in problems), problems

    def test_paradigm_refs_and_task_number_are_right(self, manifest_slice: dict) -> None:
        assert manifest_slice["paradigm_ref"] == _rel(PARADIGM_PATH)
        assert manifest_slice["source_manifest"] == _rel(FULL_MANIFEST)
        assert manifest_slice["schema_version"] == "manifest-slice:v1"
        mod = _validator_module()
        assert mod._task_number(manifest_slice) == 57

    def test_task48_extra_entry_fields_are_present(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        extra = paradigm["slice_schema"]["effective_from_task_48"]["required_entry"]
        for e in manifest_slice["independent_entries"]:
            for f in extra:
                assert f in e, f"{e['entry_id']} 缺 Task 48 起必填字段 {f}"

    def test_paradigm_bytes_are_untouched_by_this_task(self, paradigm: dict) -> None:
        """🔴 范式 JSON 是只读约束：`raw_block_digest` + `canonical_digest` 双向锁死。"""
        mod = _validator_module()
        reg = next(p for p in paradigm["paradigm_registry"]["paradigms"]
                   if p["alias"] == "legacy_deletion_paradigm")
        raw = PARADIGM_PATH.read_text(encoding="utf-8")
        assert mod.raw_block_digest(raw, "paradigm") == reg["frozen_raw_block_sha256"]
        assert mod.canonical_digest(paradigm["paradigm"]) == reg["frozen_canonical_sha256"]
        assert len(paradigm["paradigm"]["steps"]) == reg["step_count"] == 7
        assert 57 in paradigm["slice_schema"]["applies_to_tasks"]
        assert 57 in paradigm["definition_producer_paradigm"]["applies_to_tasks"]

    def test_new_sections_are_declared_as_non_conflicting(self, manifest_slice: dict) -> None:
        node = manifest_slice["paradigm_schema_conflict"]["new_section_not_in_schema"]
        for s in node["sections"]:
            assert s in manifest_slice, f"声明的新增节 {s} 不存在"
        assert node["why_not_a_conflict"]
        assert manifest_slice["paradigm_schema_conflict"]["residual_inconsistency"] is None

    def test_unjudged_slices_registry_stays_empty(self) -> None:
        """`_UNJUDGED_SLICES` 必须仍为空 —— 新 slice 不得靠加豁免通过。"""
        mod = _load_module("_t57_coverage", COVERAGE_GUARD)
        assert mod._UNJUDGED_SLICES == {}, mod._UNJUDGED_SLICES

    def test_coverage_guard_docstring_states_twelve_slices(self) -> None:
        """事实陈述随分母更新（11 → 12）；判据强度不变。"""
        src = COVERAGE_GUARD.read_text(encoding="utf-8")
        assert "**12 份**" in src, (
            "test_slice_schema_validator_coverage.py 的事实陈述未更新到 12 份"
        )
        assert ">= 2" in src, "覆盖面判据的强度（>= 2）被改动了"

    def test_requirements_and_properties_are_declared(self, manifest_slice: dict) -> None:
        req = manifest_slice["requirements_covered"]
        for ac in ("1.4", "1.6", "6.4", "12.1", "12.4", "12.8", "12.9", "12.10", "12.11", "12.12",
                   "14.1"):
            assert ac in req, f"tasks.md 点名的 AC {ac} 未登记"
        props = {p["property"] for p in manifest_slice["properties_verified"]}
        assert props == {3, 22, 69, 70}
        for p in manifest_slice["properties_verified"]:
            assert p["validates_requirement"] and p["claim"] and p["see"]
