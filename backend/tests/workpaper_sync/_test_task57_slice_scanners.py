# -*- coding: utf-8 -*-
"""Task 57 守卫的路径常量与源码扫描器（从 `test_task57_abcs_and_shared_migration.py` 拆出）。

拆分只为行数门：代码逐行原样搬来，判据仍在测试模块里。这里放的是**判据要用的读法**——
registry 模块边、OO 挂载点与门控祖先链、宿主 import 闭包里的持久化通道、source_ref 的内容锚点。
被测试模块与 4 个兄弟守卫（A / B / C / C22）共用；兄弟守卫仍从测试模块导入，测试模块再从这里导入。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
from collections import defaultdict
from collections.abc import Sequence
from html.parser import HTMLParser
from types import ModuleType
from typing import Any

from tests.workpaper_sync._test_task57_slice_drift_ledger import (
    _assert_declared_or_registered_drift,
)

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
#: 🔴 2026-09-14 更新：契约目录随 D 循环 adapter 迁移由 4 条增至 10 条（新增 D1/D3/D4/D5/D6/D7
#: 的 reviewed 生产契约），全部属 D/B/G/H 循环。逐文件读顶层 review.entry_id 的实证值。
PILOT_CONTRACT_OWNERS = {
    "xlsx/b60/gt-b60-bundle",
    "xlsx/gt-d1-notes-receivable",
    "xlsx/gt-d2-accounts-receivable",
    "xlsx/gt-d3-prepaid-accounts",
    "xlsx/gt-d4-operating-revenue",
    "xlsx/gt-d5-receivables-financing",
    "xlsx/gt-d6-contract-assets",
    "xlsx/gt-d7-contract-liabilities",
    "xlsx/gt-g7-long-term-equity-main",
    "xlsx/gt-h1-fixed-assets",
}
#: 契约目录共 11 个文件，第 11 个是 candidate：`review_status == "candidate"` 且 `review.entry_id`
#: 为 **null**。它是「candidate 不得注册生产 adapter」的反例分母 —— **不得**要求其 entry_id 非空。
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
    # 🔴 commit 82f58ea44 把集中式注册拆分到 registry/entries/*.ts 子模块。遍历主 registry +
    # 每个子文件，各自解析两种 component 写法（hoisted const / inline），import 相对路径以**各自
    # 文件目录**为基准 resolve（子模块里是 '../../GtXxx.vue'）。返回 (ct, 组件路径, 文件内行号,
    # 源文件) —— 加源文件维度让调用方能按正确文件判 hoisted/inline，不弱化。
    reg_files = [HTML_RENDERER_REGISTRY]
    entries_dir = HTML_RENDERER_REGISTRY.parent / "registry" / "entries"
    if entries_dir.is_dir():
        reg_files += sorted(entries_dir.glob("*.ts"))
    out: list[tuple[str, pathlib.Path, int, pathlib.Path]] = []
    for reg_file in reg_files:
        src = _cached_text(reg_file)
        lines = src.split("\n")
        local2rel: dict[str, str] = {}
        for m in re.finditer(
            r"^const\s+(\w+)\s*=\s*defineAsyncComponent\(\s*\(\)\s*=>\s*import\(\s*'([^']+)'\s*\)\s*\)",
            src, re.M,
        ):
            local2rel[m.group(1)] = m.group(2)
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
                out.append((ct, (reg_file.parent / rel).resolve(), i + 1, reg_file))
    return out


def _component_types_of(host_path: str) -> list[str]:
    host = (ROOT / host_path).resolve()
    return sorted(ct for ct, p, _ln, _sf in _registry_pairs() if p == host)


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


def _parse_oo_mounts(src: str, *, component: str = "gtonlyofficesheet") -> list[dict]:
    """解析 template 段里所有 `GtOnlyOfficeSheet` 挂载点及其真实祖先链。

    `component` 默认是冻结口径的载体；漂移台账核「载体已换成共享同步宿主」时传
    ``"workpapersynceditorhost"``，用同一套祖先链判据看新载体是否仍被 mode 开关门控。
    """
    m = re.search(r"<template>", src)
    if not m:
        return []
    end = src.find("\n</template>")
    body = src[m.start(): end + len("\n</template>")] if end != -1 else src
    offset = src[: m.start()].count("\n")
    p = _VueTemplateParser(component)
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
        "segmented_sites": [i for i, line in enumerate(lines, 1) if "<el-segmented" in line],
        "mode_radio_sites": [i for i, line in enumerate(lines, 1)
                             if "<el-radio-group" in line and MODE_TOKENS.search(line)],
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


_CLOSURE_CACHE: dict[tuple[str, int], list[pathlib.Path]] = {}

#: 接口路径登记表：只**声明**路径模板（`customCells: (wpId) => \`/api/workpapers/${wpId}/custom-cells\``），
#: 不发请求。🔴 不排除会误报：a173 为知识库上传 `import { knowledgeLibrary } from '@/services/apiPaths'`，
#: barrel 把 workpaper 登记表带进闭包深度 3 ⇒ 现算通道多出 custom_cells，而 a173 从不调它（2026-11-04 实测）。
#: 通道判据的原话是「闭包里的**真实 HTTP 站点**」，登记表不是站点。
_PATH_REGISTRY_FILES = (FRONTEND / "services" / "apiPaths.ts", FRONTEND / "services" / "apiPaths")


def _is_path_registry(path: pathlib.Path) -> bool:
    file, folder = _PATH_REGISTRY_FILES
    return path == file or folder in path.parents


def _closure(host_path: str, maxdepth: int = 3) -> list[pathlib.Path]:
    cache_key = (host_path, maxdepth)
    if cache_key in _CLOSURE_CACHE:
        return _CLOSURE_CACHE[cache_key]
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
    _CLOSURE_CACHE[cache_key] = sorted(seen)
    return _CLOSURE_CACHE[cache_key]


def _channel_of(host_path: str, maxdepth: int = 3) -> str:
    hit = []
    for name, rx in _CHANNELS.items():
        for f in _closure(host_path, maxdepth):
            if _is_path_registry(f):
                continue
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


def _confirmation_component_types() -> list[str]:
    # commit 82f58ea44 把注册拆分到 registry/entries/*.ts；confirmation- 的 componentType 声明
    # 可能落在子模块。遍历主 registry + 全部 entries 子模块合并文本再匹配。不弱化。
    src = _cached_text(HTML_RENDERER_REGISTRY)
    entries_dir = HTML_RENDERER_REGISTRY.parent / "registry" / "entries"
    if entries_dir.is_dir():
        for sub in sorted(entries_dir.glob("*.ts")):
            src += "\n" + _cached_text(sub)
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


HOSTS_B14 = "audit-platform/frontend/src/components/workpaper/GtB14DueDiligenceReport.vue"


def _validator_module() -> ModuleType:
    return _load_module("_t57_paradigm_contract", CONTRACT_GUARD)


def _delivered_contract_rows() -> tuple[Any, ...]:
    """交付台账 `DELIVERED_PER_ENTRY_CONTRACTS`（纯数据模块，不触发 registry 的重量级导入）。"""
    from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )

    return tuple(DELIVERED_PER_ENTRY_CONTRACTS)


def _delivered_contract_owners() -> list[str]:
    """交付台账登记的契约归属 entry_id（契约文件 `review.entry_id` 的单一真源）。"""
    return sorted(str(row["entry_id"]) for row in _delivered_contract_rows())


def _delivered_contract_ids() -> list[str]:
    return sorted(str(row["contract_id"]) for row in _delivered_contract_rows())


#: 交付时没写 `review` 元数据块的 reviewed 契约 —— 归属只能按 `contract_id` 查交付台账。
#: 🔴 只许变短，且不在守卫里顺手补：`review` 块在 canonical payload 里，补上就改了契约的
#:    definition_sha256 ⇒ 已发布底稿的冻结身份与生产契约脱钩、必须重发布（归该循环的 lane）。
CONTRACTS_WITHOUT_REVIEW_BLOCK = frozenset({"a51.cashflow_audit"})


def _contract_file_owners() -> dict[str, str | None]:
    """契约文件名 → 归属 entry_id（candidate 与辅助文件按文件自己写的，通常为 None）。

    reviewed 契约：`contract_id` 必须在交付台账里；写了 `review.entry_id` 的必须与台账按
    `contract_id` 查到的逐条相等；没写 `review` 块的必须恰好是 `CONTRACTS_WITHOUT_REVIEW_BLOCK`，
    归属取台账。
    """
    ledger = {str(row["contract_id"]): str(row["entry_id"]) for row in _delivered_contract_rows()}
    owners: dict[str, str | None] = {}
    without_block: set[str] = set()
    for path in sorted(CONTRACT_DIR.glob("*.json")):
        doc = _load(path)
        declared = (doc.get("review") or {}).get("entry_id")
        if doc.get("review_status") != "reviewed":
            owners[path.name] = declared
            continue
        contract_id = str(doc.get("contract_id"))
        assert contract_id in ledger, f"{path.name}: reviewed 契约 {contract_id} 不在交付台账里 ⇒ 有契约绕过台账"
        if declared:
            assert declared == ledger[contract_id], (
                f"{path.name}: review.entry_id={declared} 与交付台账的 {ledger[contract_id]} 不一致"
            )
        else:
            without_block.add(contract_id)
        owners[path.name] = declared or ledger[contract_id]
    assert without_block == CONTRACTS_WITHOUT_REVIEW_BLOCK, (
        f"没写 review 块的 reviewed 契约现算 {sorted(without_block)}，登记 {sorted(CONTRACTS_WITHOUT_REVIEW_BLOCK)} "
        "⇒ 新契约漏了 review 块，或已补齐的那份要从登记里删掉"
    )
    return owners


def _assert_ref_anchor(
    key: str,
    ref: str,
    *,
    needles: Sequence[str],
    regexes: Sequence[str] = (),
    forbid: Sequence[str] = (),
    unique: bool = True,
) -> None:
    """source_ref 的判据：**内容锚点**，不是行号相等。

    slice 里存的是 `路径#L行号`，行号随源码增删静默平移。原判据「那一行必须含某个 token」于是在
    源码正常演进后打红，报的却不是「锚点内容没了」而是「行号不对」—— 读者分不清是哪一种。

    现算结论只取几类（**不含行号**，免得再改一次文件就又漂一次）：
    * ``at_declared_line``：声明行仍满足锚点 ⇒ 原判据照旧成立；
    * ``moved``：声明行不满足，整份文件恰有一行满足 ⇒ 只是平移；
    * ``missing`` / ``ambiguous``：零行 / 多行满足 ⇒ 锚点内容真的没了 / 不唯一，须人工重新取证。
    * ``unique=False``（锚点本来就是「同文件可有多处」的形态，如通道字面量、读写调用）：声明行
      不满足时只分 ``present``（文件里仍有）/ ``missing`` —— 这类锚点分不出平移与另一处同形态，
      硬分 moved / ambiguous 只会把同一事实记成两种结论。
    除 ``at_declared_line`` 外都必须在漂移台账里点名。🔴 锚点要写得够具体：泛化的形态（只认
    「`:key` 绑了 `.name`」）在原站点修掉后会命中另一处同形态，被误判成 ``moved``。
    """
    assert needles or regexes, f"{key}: 锚点既无 needles 也无 regexes ⇒ 判据空转"
    path = _path_of(ref)
    assert path.is_file(), f"{key}: source_ref 指向的文件不存在：{ref}"
    wanted = [re.compile(r) for r in regexes]
    banned = [re.compile(r) for r in forbid]

    def _ok(line: str) -> bool:
        return (
            all(n in line for n in needles)
            and all(r.search(line) for r in wanted)
            and not any(r.search(line) for r in banned)
        )

    lines = _cached_text(path).split("\n")
    declared_no = _line_no_of(ref)
    declared_line = lines[declared_no - 1] if 1 <= declared_no <= len(lines) else ""
    if _ok(declared_line):
        observed = "at_declared_line"
    else:
        hits = [index + 1 for index, line in enumerate(lines) if _ok(line)]
        if not hits:
            observed = "missing"
        elif not unique:
            observed = "present"
        else:
            observed = "moved" if len(hits) == 1 else "ambiguous"
    _assert_declared_or_registered_drift(
        key,
        declared="at_declared_line",
        observed=observed,
        hint=(
            f"{_rel(path)} needles={list(needles)} regexes={list(regexes)} forbid={list(forbid)}；"
            f"声明行内容 {declared_line.strip()[:100]!r}"
        ),
    )
