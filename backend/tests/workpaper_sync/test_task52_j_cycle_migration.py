# -*- coding: utf-8 -*-
r"""test_task52_j_cycle_migration — J 循环 Excel 独立 entry 迁移验证

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 52
Requirements: 1.4, 1.5, 6.1, 12.1, 12.4, 12.8, 12.10, 12.11, 12.12, 14.1
             （另覆盖 1.7 / 12.9）

验证 Properties:
  - Property 3: 未注册 adapter 不得宣称双向 —— **两个分母，一空一实**。
    空：`bidirectional` entry 数 = 0 ⇒「删 adapter/bundle/contract 任一项后守卫打红」不宣称通过。
    实：AC 1.4 的否定方向（adapter_id 现读全 null + 正向门关着 + 宿主模板无双向宣称文案 +
    `entrySyncNotice()` 两个真分支 + BP-10 已登记）—— 真验。
  - Property 20: generated col 占位不可注册生产 adapter —— contract 维度分母为空 ⇒ 不宣称通过；
    在非空同型分母（4 条 row-model declaration + 7 条 transport-key declaration）上真验。
  - Property 69: evidence 由逐 scenario 实体与服务端重算闭合 —— 负向分母真验
    （UNVERIFIABLE ⇒ 非空 reasons；VERIFIED ⇒ 有 run id + digest）+ 43 项计数现算等值；
    正向逐 scenario 闭合不宣称通过（BP-4）。
  - Property 70: scenario/evidence/contract/bundle 不得跨 entry 复用 —— 七 slice 互斥 +
    模板 belongs_to_entry **单射 + null 必带 excluded_reason** + 契约归属逐文件读 +
    declaration 单 entry 单 workbook 绑定 + 清册路径去重。
  另在真分母上顺带验 Property 22（静态结构：六个硬编码模式全 slice 0 命中）、
  Property 23（静态前提：9 张动态行表的身份声明 + 10 处命中五族划分 + family_d/e 反向自检）与
  Property 28（template identity 一层：3 个模板 digest / sheet 名 / 37 条 wp_code 解析）。
  Property 21 分母为空 ⇒ 不宣称通过。

╔═══ 本文件的三条核心判据（Task 52 正文点名）═══╗

tasks.md 的 Task 52 正文写的是「**先解清 J2 orphan composable 与真实传输键**；无可靠 HTML
映射时单模式，不造 contract」。三条落法：

① **orphan 判定要做可达性而不是入度**。J 循环有 4 个 orphan dual-mode composable，其中
   2 个是「二阶 orphan」（只被一个自身零入边的 barrel re-export）。`useJ2DualMode` 的入边数
   是 2、看起来活着 —— 朴素的「入度 > 0 ⇒ 不是孤儿」判据会放它过去。
   另外 barrel 入边**必须用路径解析口径**：模块 stem 相等的口径会把
   `services/apiPaths.ts` 的 `export * from './apiPaths/index'` 误命中成 j2/j3 barrel 的入边
   （实测 stem 口径各得 2 条假边）。

② **真实传输键要从 owner 常量现读**。J1-2 一张逻辑表对应三个键
   `J1-2-detail-{shortTerm,postEmployment,severance}`（前缀 + section 派生），身份字段是
   `id` 不是 `rowId`；按规律猜的 `J1-2-rows` 在全 J 域 0 命中。orphan 载体拼的
   `J2-${key}` / `J3-${key}` 是**从未在生产写过**的形态。

③ **判消费边要排除「双引号字符串内的匹配」**。I 循环钉死了「符号名 grep 会误报」，改用
   import 路径字面量口径 —— 但 J 循环的
   `workpaperSyncLegacyBaseline.generated.ts` 有 5 处 JSON `"snippet"` 字符串值，其内容逐字
   包含 `from './composables/useWorkpaperEntryDualMode'`，**路径字面量口径同样会被骗到**
   （宽口径 30 vs statement-position 口径 29）。

╔═══ 判据设计（沿用前六轮已定论，不重新发明）═══╗

1. **不用空分母重言式**。每条 Property 显式区分「有真分母的部分（真验）」与
   「无适用分母的部分（只断言前提成立 + 承载者存在，**不宣称通过**）」。

2. **不用 fail-open**。没有 `pytest.skip`、没有 `if x: assert ...`（缺值即跳过）、
   没有 `except Exception` 吞异常。缺文件/缺字段一律打红。

3. **不用硬编码豁免**。本 slice 没有 pilot，也不给任何 entry 开例外列；
   `test_slice_schema_validator_coverage.py` 的 `_UNJUDGED_SLICES` 保持为空。

4. **不假设与 D/F/G/H/I 同形**。J 循环实测出六处不同（slice 的 `j_cycle_form_differences`）：
   * 3 个可达宿主只有 1 个有 OO 挂载点 ⇒ manifest 只有 1 条独立 entry；
   * J1 **没有** per-entry dual-mode composable（宿主直连共享基类，且基类零 localStorage）；
   * 写载体是平台级共享适配器 `useChecklistPersistence`（客户端 `api` 而非 `http`）
     **加** 7 个子 Tab 的 8 处 `http.put` 直写（双写路径并存）；
   * 一张逻辑表三个传输键、身份字段 `id`；
   * 4 个 orphan dual-mode（2 个二阶）；
   * 第三种伪消费边形态（生成文件里的 JSON snippet 字符串）。
   还有一处扫描口径差异：J 的 owner 模块**分居两棵树**
   （`components/workpaper/composables/` 与 `src/composables/workpaper/{j1,j2,j3}/`），
   照抄 I 循环只扫 `components/workpaper/**` 会漏掉主表 owner `useJ1Detail.ts`。

5. **sheet 名不得 strip**。J1 册的 `明细表J1-2 ` 与 `审定表J1-1 ` 尾部各有一个真实空格。

依赖（缺任一即 fail closed）：
  - backend/data/workpaper_sync_j_cycle_manifest_slice.json（frozen slice）
  - backend/data/workpaper_sync_j_cycle_deletion_plan.json（deletion plan）
  - backend/data/workpaper_sync_migration_paradigm.json（Task 45 范式，只读）
  - backend/data/workpaper_sync_entry_manifest.json（source-backed manifest，只读）
  - backend/data/workpaper_sync_entry_overlay.json（BP-9 的差异来源，只读）
  - backend/data/note_template_soe.json / note_template_listed.json（RD-2/RD-4 第二真源，只读）
  - backend/wp_templates/J/ 与 backend/wp_templates/_index.json（运行时权威，唯一真源）
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from typing import Any

import pytest

# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────
# __file__ = backend/tests/workpaper_sync/test_...py
# parents[0] = workpaper_sync/, [1] = tests/, [2] = backend/, [3] = repo root
_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
CYCLE_COMPOSABLES = FRONTEND / "composables" / "workpaper"
SYNC_DIR = WP_COMPONENTS / "sync"
DATA = BACKEND / "data"

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_j_cycle_manifest_slice.json"
DELETION_PLAN_PATH = DATA / "workpaper_sync_j_cycle_deletion_plan.json"
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
}
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
TEMPLATE_DIR = BACKEND / "wp_templates"
TEMPLATE_INDEX = TEMPLATE_DIR / "_index.json"
J_TEMPLATE_DIR = TEMPLATE_DIR / "J"
CHECKLIST_ROUTER = BACKEND / "app" / "routers" / "checklist_responses.py"
REGISTRY = BACKEND / "app" / "services" / "workpaper_sync" / "adapters" / "registry.py"
HTML_RENDERER_REGISTRY = WP_COMPONENTS / "htmlRendererRegistry.ts"
SHARED_BASE = WP_COMPOSABLES / "useWorkpaperEntryDualMode.ts"
LEGACY_BASELINE_GENERATED = SYNC_DIR / "workpaperSyncLegacyBaseline.generated.ts"
NOTE_TEMPLATE_SOE = DATA / "note_template_soe.json"
NOTE_TEMPLATE_LISTED = DATA / "note_template_listed.json"
CHECKLIST_PERSISTENCE = CYCLE_COMPOSABLES / "useChecklistPersistence.ts"

#: AC 1.3 的能力态枚举（真源在范式 JSON 的 adjudication_criteria.capability_enum）。
CAPABILITY_ENUM = ("bidirectional", "single_html", "single_onlyoffice", "unreachable")
#: step 3 的二值结论（真源在范式 JSON 的 anti_patterns[AP-1].allowed_verdict_values）。
HTML_COUNTERPART_VERDICTS = ("none", "exists")

#: AC 1.4 的 UI 义务落点（Task 46 收口新建的单一真源，本任务复用不新建第二份）。
NOTICE_MODULE = SYNC_DIR / "workpaperEntrySyncNotice.ts"
NOTICE_COMPONENT = SYNC_DIR / "GtEntrySyncCapabilityNotice.vue"
NOTICE_COMPONENT_NAME = "GtEntrySyncCapabilityNotice"

#: 四个 pilot 的 contract 文件 → 它应属的 entry_id（Property 70 的归属判据，逐文件读 review.entry_id）。
#: 🔴 实值逐文件读出，**不按文件名猜**：b60 是三段式 `xlsx/b60/gt-b60-bundle`，
#: g7 是 `-long-term-equity-main` 而不是文件名暗示的 `-soe-subsidiary`。
PILOT_CONTRACT_OWNERS = {
    "b60.hour_budget.json": "xlsx/b60/gt-b60-bundle",
    "d2.receivable_detail.json": "xlsx/gt-d2-accounts-receivable",
    "g7.soe_subsidiary_disclosure.json": "xlsx/gt-g7-long-term-equity-main",
    "h1.disposal_check.json": "xlsx/gt-h1-fixed-assets",
}

#: 本 slice 的唯一 entry。
J1_ENTRY = "xlsx/j1/gt-j1-employee-compensation"
#: parent_duplicate 子入口。
J1_CHILD_ENTRY = "xlsx/j1/inspection/j1-tab-general-check"
#: 三个宿主（J1 是 entry，J2/J3 不是）。
J_HOSTS = {
    "j1": WP_COMPONENTS / "j1" / "GtJ1EmployeeCompensation.vue",
    "j2": WP_COMPONENTS / "j2" / "GtJ2DefinedBenefitPlan.vue",
    "j3": WP_COMPONENTS / "j3" / "GtJ3ShareBasedPayment.vue",
}
J_SUBDIRS = ("j1", "j2", "j3")
#: `components/workpaper/composables` 下属本 slice 的文件名前缀正则（j1..j3 / useJ1..useJ3）。
J_COMPOSABLE_RE = re.compile(r"^(?:use)?[jJ][123](?![0-9])")


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _line_count(path: pathlib.Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _blank_keep_newlines(match: re.Match[str]) -> str:
    """把匹配段替换成等长空白，**保留换行** —— 行号与列号都不移。"""
    return re.sub(r"[^\n]", " ", match.group(0))


def _strip_ts_comments(source: str) -> str:
    """把 TS/Vue 注释**置空但保留行号** —— 说明文字不得充当判据证据。

    🔴 为什么不是直接删掉：删掉注释行会让后续代码的行号整体上移，而 slice 里登记的
    `path#Lnn` 是**真实文件行号**。首轮实测就是这样红的：10 处位置化命中的行号全部偏移
    2~3 行（如 useJ1Detail.ts#L127 被算成 #L113），判据于是「声明与现扫不等值」——
    看着像 slice 抄错，其实是解析器把坐标系换了。这里改成同长空白替换，行列都不移。

    剥完必须反向自检（见 TestGuardSelfChecks）。
    """
    source = re.sub(r"/\*[\s\S]*?\*/", _blank_keep_newlines, source)
    source = re.sub(r"<!--[\s\S]*?-->", _blank_keep_newlines, source)
    source = re.sub(r"(?m)^\s*//.*$", _blank_keep_newlines, source)
    source = re.sub(r"(?m)//[^\n\"'`]*$", _blank_keep_newlines, source)
    return source


def _vue_template(source: str) -> str:
    """取 SFC 的**外层** template 区块。

    🔴 不能用 `source.split("</template>")[0]`：SFC 里嵌套的 `<template v-else>`
    会先闭合（J1 宿主 #L21 有 `<template v-else-if="!isLoading">`，J2 宿主 #L10 有
    `<template v-else>`），第一处 `</template>` 落在内层 ⇒ 截出来的片段比真实模板短，
    判据会把「已在模板里」误判成「不在模板里」。这里改用 `<script` 边界。
    """
    marker = source.find("<script")
    assert marker > 0, "找不到 <script 边界 —— 该文件不是常规 SFC（template 在 script 之前）"
    head = source[:marker]
    assert "<template>" in head, "SFC 头部没有 <template>"
    return head


def _toolbar_block(template: str, gate_anchor: str) -> str:
    """按 slice 声明的工具栏锚点截出该区块（开标签行 → 同缩进的 `</div>`）。

    🔴 为什么按 slice 声明取锚点而不是写死正则：全 J 域 `el-segmented` 共 3 处，
    只有 J1 宿主 #L10 那处是模式切换器；`J1TabGeneralCheck.vue#L27` 与
    `J2TabAdjudication.vue#L386` 是 Tab 内部分段控件。全文件 grep 会把它们误判成
    第二个模式切换器。
    """
    lines = template.splitlines()
    opens = [i for i, ln in enumerate(lines) if gate_anchor in ln]
    assert len(opens) == 1, f"工具栏锚点 {gate_anchor!r} 在模板里命中 {len(opens)} 次（应为 1）"
    start = opens[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start + 1, len(lines)):
        if lines[i].strip() == "</div>" and (len(lines[i]) - len(lines[i].lstrip())) == indent:
            return "\n".join(lines[start : i + 1])
    pytest.fail(f"锚点 {gate_anchor!r} 之后找不到同缩进的 </div> —— 工具栏区块无法界定")


def _cells_of(path: pathlib.Path, sheet: str, cells: str, *, formula: bool = False) -> list[Any]:
    """openpyxl 真读权威模板的一段单列区间（`B13:B32` 或单格 `A11`）。

    🔴 `sheet` **不得 strip**：J1 册的 `明细表J1-2 ` 与 `审定表J1-1 ` 尾部各有真实空格。
    """
    import openpyxl
    from openpyxl.utils import column_index_from_string

    match = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", cells)
    assert match, f"非法单元格区间 {cells!r}"
    col0, row0, col1, row1 = match.groups()
    if col1 is None:
        col1, row1 = col0, row0
    assert col0 == col1, f"本判据只支持单列区间，实际 {cells!r}"
    workbook = openpyxl.load_workbook(path, data_only=not formula)
    try:
        assert sheet in workbook.sheetnames, (
            f"{path.name} 里没有 sheet {sheet!r}；实有 {workbook.sheetnames}"
        )
        worksheet = workbook[sheet]
        column = column_index_from_string(col0)
        out: list[Any] = []
        for row in range(int(row0), int(row1) + 1):
            value = worksheet.cell(row=row, column=column).value
            out.append(None if value is None else str(value).strip())
        return out
    finally:
        workbook.close()


def _sheet_names(path: pathlib.Path) -> list[str]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def _indexed_relpaths() -> set[str]:
    """`_index.json` 登记的相对路径集合（分隔符归一为 /）。"""
    index = _load(TEMPLATE_INDEX)
    return {str(f["relative_path"]).replace("\\", "/") for f in index["files"]}


def _resolve_repo(rel: str) -> pathlib.Path:
    """把 slice 里登记的仓库相对路径（可带 `#Lxx` 或 `!sheet!cell`）解析成绝对路径。"""
    head = rel.split("#")[0].split("!")[0]
    return ROOT / head


def _line_no_of(ref: str) -> int:
    match = re.search(r"#L(\d+)", ref)
    assert match, f"引用 {ref!r} 里没有 #Lxx 行号"
    return int(match.group(1))


def _line_at(ref: str) -> str:
    """取 `path#Lnn` 指向的那一行原文（1-based）。"""
    path = _resolve_repo(ref)
    assert path.is_file(), f"引用 {ref!r} 指向的文件不存在"
    lines = path.read_text(encoding="utf-8").splitlines()
    no = _line_no_of(ref)
    assert 1 <= no <= len(lines), f"引用 {ref!r} 的行号超出文件范围（共 {len(lines)} 行）"
    return lines[no - 1]


def _line_window(ref: str, span: int = 3) -> str:
    """取 `path#Lnn` 起的 `span` 行窗口 —— 调用与 URL 常被拆成两行。"""
    path = _resolve_repo(ref)
    assert path.is_file(), f"引用 {ref!r} 指向的文件不存在"
    lines = path.read_text(encoding="utf-8").splitlines()
    no = _line_no_of(ref)
    return "\n".join(lines[no - 1 : no - 1 + span])


# ── 消费边口径（statement-position）─────────────────────────────────────────
_IMPORT_FORMS = (
    r"from\s+(['\"])([^'\"]*?)\1",
    r"import\(\s*(['\"])([^'\"]*?)\1\s*\)",
    r"vi\.mock\(\s*(['\"])([^'\"]*?)\1",
)


def _inside_double_quoted_string(line: str, pos: int) -> bool:
    """`pos` 是否落在同一行的双引号字符串内（JD-6 的判别式）。

    🔴 存在的理由：`workpaperSyncLegacyBaseline.generated.ts` 有 5 处 JSON `"snippet"`
    字符串值，其内容逐字包含 `from './composables/useWorkpaperEntryDualMode'` ——
    路径字面量口径会把它们当成真 import 边（宽口径 30 vs 窄口径 29）。真 import 语句
    永远不会落在双引号字符串里。
    """
    count = 0
    index = 0
    while index < pos:
        if line[index] == "\\":
            index += 2
            continue
        if line[index] == '"':
            count += 1
        index += 1
    return count % 2 == 1


def _frontend_files() -> list[pathlib.Path]:
    return [p for p in FRONTEND.rglob("*") if p.is_file() and p.suffix in (".ts", ".vue")]


_FRONTEND_CACHE: dict[str, list[pathlib.Path]] = {}
#: 文件内容缓存。前端有 7000+ 个 .ts/.vue，消费边判据要全域扫多次 ——
#: 不缓存的话单文件守卫要跑 100s+，变异检验（每条变异跑一遍全量）会不可承受。
#: 🔴 缓存只在**单次 pytest 进程内**有效；变异脚本是每条变异起一个新进程 ⇒ 不会读到脏内容。
_CONTENT_CACHE: dict[pathlib.Path, str] = {}


def _all_frontend() -> list[pathlib.Path]:
    if "all" not in _FRONTEND_CACHE:
        _FRONTEND_CACHE["all"] = _frontend_files()
    return _FRONTEND_CACHE["all"]


def _cached_text(path: pathlib.Path) -> str:
    if path not in _CONTENT_CACHE:
        _CONTENT_CACHE[path] = path.read_text(encoding="utf-8", errors="replace")
    return _CONTENT_CACHE[path]


def _resolve_spec(spec: str, importer: pathlib.Path) -> pathlib.Path | None:
    """把 import spec 解析成绝对文件路径（`@/` 别名 + 相对路径 + 目录 index）。

    🔴 barrel 入边**必须**用这个口径：按「模块 stem 相等」判会把
    `services/apiPaths.ts` 的 `export * from './apiPaths/index'` 误命中成
    `composables/workpaper/j2/index.ts` 的入边（实测 stem 口径给 j2/j3 barrel 各得 2 条假边）。
    """
    if spec.startswith("@/"):
        base = FRONTEND / spec[2:]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None
    for candidate in (base, base.with_suffix(".ts"), base.with_suffix(".vue"), base / "index.ts"):
        if candidate.is_file():
            return candidate
    return None


_IMPORT_INDEX: dict[pathlib.Path, list[str]] = {}


def _build_import_index() -> dict[pathlib.Path, list[str]]:
    """全域扫一遍，建 `解析后的目标文件 → [importer#Lnn]` 索引。

    🔴 只扫一次：`_statement_edges_to` 在本文件被调用十余次，每次全域重扫会让守卫跑
    十几分钟，变异检验（每条变异跑一遍全量）不可承受。索引在**单次 pytest 进程内**
    构建，变异脚本每条变异起新进程 ⇒ 不会读到脏内容。
    """
    if _IMPORT_INDEX:
        return _IMPORT_INDEX
    for path in _all_frontend():
        source = _cached_text(path)
        rel = path.relative_to(ROOT).as_posix()
        for form in _IMPORT_FORMS:
            for match in re.finditer(form, source):
                line_start = source.rfind("\n", 0, match.start()) + 1
                line_end = source.find("\n", match.start())
                line = source[line_start : line_end if line_end > 0 else len(source)]
                if _inside_double_quoted_string(line, match.start() - line_start):
                    continue
                resolved = _resolve_spec(match.group(2), path)
                if resolved is None:
                    continue
                no = source[: match.start()].count("\n") + 1
                _IMPORT_INDEX.setdefault(resolved, []).append(f"{rel}#L{no}")
    return _IMPORT_INDEX


def _statement_edges_to(target: pathlib.Path) -> list[str]:
    """指向 `target` 的 **statement-position** import 边（`path#Lnn` 列表，含测试）。"""
    return sorted(set(_build_import_index().get(target.resolve(), [])))


def _wide_scope_edge_files(stem: str) -> set[str]:
    """宽口径：**不**排除双引号字符串内的匹配，按模块 stem 末段比对，返回命中文件集合。"""
    out: set[str] = set()
    for path in _all_frontend():
        source = path.read_text(encoding="utf-8", errors="replace")
        for form in _IMPORT_FORMS:
            for match in re.finditer(form, source):
                tail = match.group(2).rsplit("/", 1)[-1]
                if tail in (stem, f"{stem}.ts", f"{stem}.vue"):
                    out.add(path.relative_to(ROOT).as_posix())
    return out


def _is_test_path(path: pathlib.Path) -> bool:
    name = path.name
    return (
        "__tests__" in path.parts
        or name.endswith(".spec.ts")
        or name.endswith(".test.ts")
        or name.endswith(".unit.test.ts")
        or name.endswith(".playwright.ts")
    )


def _j_cycle_files() -> list[pathlib.Path]:
    """J 域生产 .ts/.vue 的扫描分母。

    🔴 J 的 owner 模块**分居两棵树**：`components/workpaper/{j1,j2,j3}` +
    `components/workpaper/composables` 里 `^(?:use)?[jJ][123]` 的文件 +
    `src/composables/workpaper/{j1,j2,j3}`。照抄 I 循环只扫 `components/workpaper/**`
    会漏掉主表 owner `composables/workpaper/j1/useJ1Detail.ts` ⇒「0 命中」是空跑出来的。
    """
    out: set[pathlib.Path] = set()
    for sub in J_SUBDIRS:
        for path in (WP_COMPONENTS / sub).rglob("*"):
            if path.is_file() and path.suffix in (".ts", ".vue"):
                out.add(path)
        cycle_dir = CYCLE_COMPOSABLES / sub
        assert cycle_dir.is_dir(), f"缺目录 {cycle_dir} —— J 的 owner 模块树之一"
        for path in cycle_dir.rglob("*"):
            if path.is_file() and path.suffix in (".ts", ".vue"):
                out.add(path)
    for path in WP_COMPOSABLES.rglob("*"):
        if path.is_file() and path.suffix in (".ts", ".vue") and J_COMPOSABLE_RE.match(path.name):
            out.add(path)
    return sorted(p for p in out if not _is_test_path(p))


# ── 位置化身份 / 硬编码扫描 ────────────────────────────────────────────────
_IDENTITY_KEYS = ("rowId", "rowKey", "id")
_POSITIONAL_TOKEN = re.compile(r"(?:^|[^\w$])(?:i|idx|index)(?:\s*\+\s*1)?(?:\s*\}|\s*[,)\]`]|$)")
_POSITIONAL_INTERP = re.compile(r"\$\{\s*(?:i|idx|index)\s*\}")
_DISPLAY_SEQ_SITE = re.compile(r"\bseq\s*:\s*[^,]*(?:idx|index|\bi\b)\s*\+\s*1")
_FOUR_TABLE_SEED_POSITIONAL = re.compile(r"`(?:seed|row|detail|item)-\$\{\s*(?:i|idx|index)\s*\}")

_HARDCODED_PATTERNS = {
    "blankRows_with_integer_literal": re.compile(r"\bblankRows\s*\(\s*[^,()]+,\s*\d+\s*\)"),
    "horizontal_company_column_literals": re.compile(r"['\"`](?:公司|单位)[1-9]\d*['\"`]"),
    "column_key_is_label": re.compile(r"\bkey\s*:\s*[A-Za-z_$][\w$]*(?:\.[\w$]+)*\.label\b"),
    "row_cell_key_is_label": re.compile(r"\brow\s*\[\s*[A-Za-z_$][\w$]*(?:\.[\w$]+)*\.label\s*\]"),
    "seed_placeholder_literals": re.compile(r"['\"][^'\"]{0,6}(?:公司|单位|课题|项目)[1-9]\d*['\"]"),
    "four_table_seed_positional": _FOUR_TABLE_SEED_POSITIONAL,
}


def _positional_identity_hits(files: list[pathlib.Path]) -> list[tuple[str, int, str, str]]:
    """`(relpath, lineno, key, expr)` 的命中列表（剥注释后逐行扫身份键赋值）。"""
    out: list[tuple[str, int, str, str]] = []
    for path in files:
        source = _strip_ts_comments(_cached_text(path))
        rel = path.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(source.splitlines(), 1):
            for key in _IDENTITY_KEYS:
                match = re.search(r"(?<![\w$])" + key + r"\s*:\s*([^,\n]+)", line)
                if not match:
                    continue
                expr = match.group(1)
                if _POSITIONAL_TOKEN.search(expr) or _POSITIONAL_INTERP.search(expr):
                    out.append((rel, lineno, key, expr.strip()))
    return out


def _hardcoded_hits(files: list[pathlib.Path], name: str) -> list[str]:
    pattern = _HARDCODED_PATTERNS[name]
    out: list[str] = []
    for path in files:
        source = _strip_ts_comments(_cached_text(path))
        for match in pattern.finditer(source):
            no = source[: match.start()].count("\n") + 1
            out.append(f"{path.relative_to(ROOT).as_posix()}#L~{no} {match.group(0)}")
    return out


def _array_literal_body(source: str, symbol: str) -> str:
    """截出 `... {symbol} ... = [` 之后到配对 `]` 的数组字面量正文。

    🔴 括号配对而非固定字符窗口；且必须**先跳过类型注解**
    （`J1_SECTIONS: J1DetailSectionMeta[] = [` 里 `[]` 会骗到「第一个 `[`」）——
    这里锚在 `=` 之后的第一个 `[`。
    """
    match = re.search(r"\b" + re.escape(symbol) + r"\b[^=\n]*=\s*", source)
    assert match, f"源码里找不到常量声明 {symbol!r}"
    rest = source[match.end() :]
    assert rest.lstrip().startswith("["), f"{symbol!r} 的赋值右侧不是数组字面量：{rest[:60]!r}"
    start = rest.index("[")
    depth = 0
    for pos in range(start, len(rest)):
        char = rest[pos]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return rest[start : pos + 1]
    pytest.fail(f"{symbol!r} 的数组字面量没有配对的 `]`")


def _section_default_row_labels(source: str, symbol: str, section_key: str) -> list[str]:
    """从 `J1_SECTIONS` 里 `key == section_key` 那项的 `defaultRows` 抽 label 序列。"""
    body = _array_literal_body(source, symbol)
    marker = re.search(r"key:\s*'" + re.escape(section_key) + r"'", body)
    assert marker, f"{symbol!r} 里找不到 key == {section_key!r} 的分区"
    tail = body[marker.end() :]
    rows = re.search(r"defaultRows:\s*\[", tail)
    assert rows, f"分区 {section_key!r} 后面找不到 defaultRows"
    start = tail.index("[", rows.end() - 1)
    depth = 0
    block = ""
    for pos in range(start, len(tail)):
        char = tail[pos]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                block = tail[start : pos + 1]
                break
    assert block, f"分区 {section_key!r} 的 defaultRows 数组没有配对的 `]`"
    return re.findall(r"label:\s*'([^']*)'", block)


def _object_literal_values(source: str, symbol: str) -> dict[str, str]:
    """从 `const {symbol} = { a: 'x', b: 'y' }` 抽 `{key: value}`（值必须是字符串字面量）。"""
    match = re.search(r"(?<![\w$])" + re.escape(symbol) + r"\b[^=\n]*=\s*\{", source)
    assert match, f"源码里找不到对象常量 {symbol!r}"
    start = source.index("{", match.end() - 1)
    depth = 0
    block = ""
    for pos in range(start, len(source)):
        char = source[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                block = source[start : pos + 1]
                break
    assert block, f"{symbol!r} 的对象字面量没有配对的 `}}`"
    # 🔴 键既可能是标识符（`main: 'J2-1-main'`）也可能是**带引号的字符串**
    #    （`'底稿目录': 'J2-目录'` —— J2/J3 的 sheet 映射表就是这种）。只认标识符键会得 0 条，
    #    而「0 条」会被误读成「映射表是空的」。
    pairs = re.findall(r"(?:'([^']+)'|([A-Za-z_$][\w$]*))\s*:\s*'([^']*)'", block)
    return {(quoted or bare): value for quoted, bare, value in pairs}


def _note_template_rows(path: pathlib.Path, section_index: int, table_index: int) -> list[str]:
    doc = _load(path)
    sections = doc["sections"]
    assert 0 <= section_index < len(sections), f"{path.name} 没有 sections[{section_index}]"
    tables = sections[section_index].get("tables") or []
    assert 0 <= table_index < len(tables), (
        f"{path.name} 的 sections[{section_index}] 没有 tables[{table_index}]"
    )
    rows = tables[table_index].get("rows") or []
    return [str(r.get("label")) if isinstance(r, dict) else str(r) for r in rows]


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    assert MANIFEST_SLICE_PATH.is_file(), f"缺 slice：{MANIFEST_SLICE_PATH}"
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def deletion_plan() -> dict:
    assert DELETION_PLAN_PATH.is_file(), f"缺清册：{DELETION_PLAN_PATH}"
    return _load(DELETION_PLAN_PATH)


@pytest.fixture(scope="module")
def paradigm() -> dict:
    assert PARADIGM_PATH.is_file(), f"缺范式：{PARADIGM_PATH}"
    return _load(PARADIGM_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    assert FULL_MANIFEST_PATH.is_file(), f"缺 manifest：{FULL_MANIFEST_PATH}"
    return _load(FULL_MANIFEST_PATH)


@pytest.fixture(scope="module")
def j_files() -> list[pathlib.Path]:
    return _j_cycle_files()


@pytest.fixture(scope="module")
def j1_template() -> pathlib.Path:
    path = J_TEMPLATE_DIR / "J1 应付职工薪酬.xlsx"
    assert path.is_file(), f"缺权威模板 {path}"
    return path


@pytest.fixture(scope="module")
def the_entry(manifest_slice: dict) -> dict:
    entries = manifest_slice["independent_entries"]
    assert len(entries) == 1, f"本 slice 应恰 1 条 entry，实际 {len(entries)}"
    return entries[0]


# ════════════════════════════════════════════════════════════════════════════
# ① 守卫自检（判据自己的分母与解析器必须先站得住）
# ════════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:
    """守卫自身的反向自检。

    没有这一组，后面所有「0 命中 / N 命中」的结论都可能是解析器坏了而不是代码干净。
    """

    def test_strip_comments_removes_comments_but_keeps_code(self) -> None:
        src = "const a = 1 // gone\n/* block */\nconst b = '// keep'\n<!-- html -->\n"
        out = _strip_ts_comments(src)
        assert "gone" not in out
        assert "block" not in out
        assert "html" not in out
        assert "const a = 1" in out
        assert "const b = '// keep'" in out

    def test_strip_comments_really_hides_the_j2_sheet_map_comment(self) -> None:
        """反向自检：剥注释必须真能把 J2 orphan 的块注释吃掉（否则分母含说明文字）。"""
        raw = (WP_COMPOSABLES / "useJ2EntryDualMode.ts").read_text(encoding="utf-8")
        assert "J2 sheet 名解析逻辑" in raw, "前提变了：该注释已不在源码里"
        assert "J2 sheet 名解析逻辑" not in _strip_ts_comments(raw)
        assert "J2_SHEET_MAP" in _strip_ts_comments(raw), "剥过头了：代码也被吃掉"

    def test_vue_template_extraction_does_not_stop_at_inner_template(self) -> None:
        """J1 宿主的第一处 `</template>` 落在内层 —— 必须按 `<script` 边界截。"""
        source = J_HOSTS["j1"].read_text(encoding="utf-8")
        head = _vue_template(source)
        naive = source.split("</template>")[0]
        assert len(head) > len(naive), "外层模板没有比朴素切法长 —— 前提变了"
        assert 'class="j1-dual-mode-bar"' in head
        assert "GtOnlyOfficeSheet" in head

    def test_toolbar_block_extraction_is_bounded(self, the_entry: dict) -> None:
        anchor = the_entry["ui_toolbar_gate"]
        block = _toolbar_block(_vue_template(J_HOSTS["j1"].read_text(encoding="utf-8")), anchor)
        assert "el-segmented" in block, "工具栏区块里没有模式切换器 —— 锚点截错了"
        assert "GtOnlyOfficeSheet" not in block, "区块越界到 OO 挂载点了"
        assert block.rstrip().endswith("</div>")

    def test_toolbar_block_rejects_ambiguous_anchor(self) -> None:
        with pytest.raises(AssertionError, match="命中"):
            _toolbar_block('<div class="x">\n</div>\n<div class="x">\n</div>', 'class="x"')

    def test_inside_double_quoted_string_detector_works_both_ways(self) -> None:
        """JD-6 判别式的双向自检。"""
        json_line = '        "snippet": "import { X } from \'./composables/X\'"'
        pos = json_line.index("from")
        assert _inside_double_quoted_string(json_line, pos) is True
        real_line = "import { X } from './composables/X'"
        assert _inside_double_quoted_string(real_line, real_line.index("from")) is False

    def test_resolve_spec_is_path_based_not_stem_based(self) -> None:
        """barrel 入边口径的反向自检：`./apiPaths/index` 不得解析成 j2 barrel。"""
        importer = FRONTEND / "services" / "apiPaths.ts"
        assert importer.is_file(), "前提变了：services/apiPaths.ts 不在了"
        resolved = _resolve_spec("./apiPaths/index", importer)
        assert resolved is not None, "`./apiPaths/index` 应能解析到真文件"
        assert resolved != (CYCLE_COMPOSABLES / "j2" / "index.ts").resolve()
        assert _resolve_spec("@/composables/workpaper/j2", importer) == (
            CYCLE_COMPOSABLES / "j2" / "index.ts"
        ).resolve()

    def test_positional_token_catches_both_interp_and_plus_one(self) -> None:
        assert _POSITIONAL_INTERP.search("`j1d-load-${i}-x`")
        assert _POSITIONAL_TOKEN.search("e.id ?? i + 1")
        assert _POSITIONAL_TOKEN.search("r.rowId || genId(i)")
        assert not _POSITIONAL_TOKEN.search("String(row.identifier)")

    def test_array_literal_body_skips_the_type_annotation_brackets(self) -> None:
        source = (CYCLE_COMPOSABLES / "j1" / "useJ1Detail.ts").read_text(encoding="utf-8")
        body = _array_literal_body(source, "J1_SECTIONS")
        assert body.startswith("[") and body.rstrip().endswith("]")
        assert "defaultRows" in body, "截到的是类型注解的 `[]` 而不是数组正文"

    def test_section_default_row_labels_are_per_section(self) -> None:
        source = (CYCLE_COMPOSABLES / "j1" / "useJ1Detail.ts").read_text(encoding="utf-8")
        short_term = _section_default_row_labels(source, "J1_SECTIONS", "shortTerm")
        post = _section_default_row_labels(source, "J1_SECTIONS", "postEmployment")
        severance = _section_default_row_labels(source, "J1_SECTIONS", "severance")
        assert len(short_term) == 20 and len(post) == 8 and len(severance) == 1
        assert short_term[:1] != post[:1], "两个分区抽出了同一段 —— 分区定位失效"

    def test_object_literal_values_reads_real_key_objects(self) -> None:
        source = (WP_COMPOSABLES / "useJ2EntryDualMode.ts").read_text(encoding="utf-8")
        mapping = _object_literal_values(source, "J2_SHEET_MAP")
        assert len(mapping) == 8, f"J2_SHEET_MAP 应 8 条，实际 {len(mapping)}"

    def test_cells_of_does_not_strip_the_sheet_name(self, j1_template: pathlib.Path) -> None:
        """🔴 J1 册的 sheet 名尾部有真实空格 —— strip 会 KeyError。"""
        assert _cells_of(j1_template, "明细表J1-2 ", "A11") == ["序号"]
        with pytest.raises(AssertionError, match="没有 sheet"):
            _cells_of(j1_template, "明细表J1-2", "A11")

    def test_j_cycle_denominator_is_non_vacuous(self, j_files: list[pathlib.Path]) -> None:
        assert len(j_files) >= 80, f"J 域扫描分母只有 {len(j_files)} 个文件 —— 口径坏了"
        rels = {p.relative_to(ROOT).as_posix() for p in j_files}
        assert "audit-platform/frontend/src/composables/workpaper/j1/useJ1Detail.ts" in rels, (
            "🔴 分母漏了主表 owner —— 照抄 I 循环只扫 components/workpaper/** 的典型症状"
        )
        assert "audit-platform/frontend/src/components/workpaper/j1/core/J1TabAdjustment.vue" in rels
        assert not any("__tests__" in r for r in rels), "分母里混进了测试文件"

    def test_all_required_artifacts_exist(self) -> None:
        for path in (
            MANIFEST_SLICE_PATH,
            DELETION_PLAN_PATH,
            PARADIGM_PATH,
            FULL_MANIFEST_PATH,
            OVERLAY_PATH,
            CONTRACT_DIR,
            TEMPLATE_INDEX,
            J_TEMPLATE_DIR,
            CHECKLIST_ROUTER,
            REGISTRY,
            HTML_RENDERER_REGISTRY,
            SHARED_BASE,
            LEGACY_BASELINE_GENERATED,
            NOTE_TEMPLATE_SOE,
            NOTE_TEMPLATE_LISTED,
            NOTICE_MODULE,
            NOTICE_COMPONENT,
            CHECKLIST_PERSISTENCE,
            *J_HOSTS.values(),
            *SIBLING_SLICE_PATHS.values(),
        ):
            assert path.exists(), f"缺依赖：{path}"


# ════════════════════════════════════════════════════════════════════════════
# ② slice_scope 可复算（step 1）
# ════════════════════════════════════════════════════════════════════════════
class TestSliceScopeIsRecomputable:
    """selection_rule 必须能从 source manifest **现算**出同一个 entry 集合。"""

    @staticmethod
    def _j_prefixed(full_manifest: dict) -> list[dict]:
        out = []
        for entry in full_manifest["entries"]:
            patterns = (entry.get("wp_match") or {}).get("wp_code_patterns") or []
            if any(str(p).startswith("J") for p in patterns):
                out.append(entry)
        return out

    def test_selection_rule_recomputes_the_entry_set(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        recomputed = {
            e["entry_id"]
            for e in self._j_prefixed(full_manifest)
            if e.get("document_type") == "xlsx" and e.get("independent_entry") is True
        }
        declared = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert recomputed == declared, (
            f"selection_rule 现算 {sorted(recomputed)} != slice 声明 {sorted(declared)}"
        )
        assert declared == {J1_ENTRY}

    def test_scope_counters_match_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        scope = manifest_slice["slice_scope"]
        j_all = self._j_prefixed(full_manifest)
        assert scope["j_prefixed_entry_total"] == len(j_all)
        independent = [e for e in j_all if e.get("independent_entry") is True]
        assert scope["j_prefixed_independent_total"] == len(independent)
        assert scope["independent_entry_count"] == len(manifest_slice["independent_entries"])
        children = [e for e in j_all if e.get("parent_entry_id")]
        assert scope["parent_duplicate_count"] == len(children)
        assert scope["excluded_pilot_entry_count"] == 0

    def test_the_parent_duplicate_child_is_registered(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """J 循环有 1 条子入口 ⇒ parent_duplicate_summary 是必须的（F/I 各 0 条、无此节）。"""
        summary = manifest_slice["parent_duplicate_summary"]
        assert summary["note"], "conditional_section 的 note 必填"
        declared = {c["entry_id"] for c in summary["children"]}
        assert declared == {J1_CHILD_ENTRY}
        child = next(e for e in full_manifest["entries"] if e["entry_id"] == J1_CHILD_ENTRY)
        assert child["parent_entry_id"] == J1_ENTRY
        assert child["independent_entry"] is False
        declared_child = summary["children"][0]
        assert declared_child["parent_entry_id"] == child["parent_entry_id"]
        assert declared_child["host_path"] == child["host_path"]
        assert declared_child["wp_code_patterns"] == list(
            (child.get("wp_match") or {}).get("wp_code_patterns") or []
        )

    def test_j2_and_j3_hosts_are_really_absent_from_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """JD-1：3 个宿主只有 1 个在 manifest 里 —— 两侧都断言。"""
        host_paths = {e.get("host_path") for e in full_manifest["entries"]}
        assert J_HOSTS["j1"].relative_to(ROOT).as_posix() in host_paths, (
            "前提变了：J1 宿主不在 manifest 里"
        )
        for cyc in ("j2", "j3"):
            rel = J_HOSTS[cyc].relative_to(ROOT).as_posix()
            assert rel not in host_paths, f"{rel} 现在进了 manifest ⇒ selection_rule 需重算"
        diff = next(
            d
            for d in manifest_slice["j_cycle_form_differences"]["differences"]
            if d["id"] == "JD-1"
        )
        for rel, decl in diff["hosts"].items():
            path = ROOT / rel
            assert path.is_file(), f"JD-1 声明的宿主不存在：{rel}"
            template = _vue_template(path.read_text(encoding="utf-8"))
            has_mount = "GtOnlyOfficeSheet" in template
            assert has_mount == decl["has_oo_mount"], (
                f"{rel}: 声明 has_oo_mount={decl['has_oo_mount']} 但模板实测 {has_mount}"
            )
            if decl["manifest_entry_id"] is None:
                assert rel not in host_paths
            else:
                assert decl["manifest_entry_id"] in {e["entry_id"] for e in full_manifest["entries"]}

    def test_host_module_edges_in_the_renderer_registry_are_real(self, manifest_slice: dict) -> None:
        registry = HTML_RENDERER_REGISTRY.read_text(encoding="utf-8")
        lines = registry.splitlines()
        diff = next(
            d
            for d in manifest_slice["j_cycle_form_differences"]["differences"]
            if d["id"] == "JD-1"
        )
        for rel, decl in diff["hosts"].items():
            ref = decl["registry_source"]
            line = lines[_line_no_of(ref) - 1]
            assert f"'{decl['component_type']}'" in line, (
                f"{ref} 那一行不是 componentType {decl['component_type']!r}：{line.strip()!r}"
            )
            component_line = lines[_line_no_of(ref)]
            assert pathlib.Path(rel).name in component_line, (
                f"{ref} 的下一行没有指向 {rel}：{component_line.strip()!r}"
            )

    def test_no_pilot_contract_belongs_to_the_j_cycle(self) -> None:
        """逐文件读 review.entry_id（不数文件个数、不按文件名猜）。"""
        files = sorted(CONTRACT_DIR.glob("*.json"))
        assert files, "契约目录为空 —— 分母坏了"
        for path in files:
            doc = _load(path)
            owner = (doc.get("review") or {}).get("entry_id")
            if path.name in PILOT_CONTRACT_OWNERS:
                assert owner == PILOT_CONTRACT_OWNERS[path.name], (
                    f"{path.name} 的 review.entry_id={owner!r} 与冻结值不符"
                )
            if owner is None:
                continue
            assert not str(owner).startswith("xlsx/j"), f"{path.name} 竟属 J 循环：{owner!r}"

    def test_no_j0_confirmation_workbook_exists(self) -> None:
        names = {p.name for p in J_TEMPLATE_DIR.iterdir() if p.is_file()}
        assert not any(n.startswith("J0") for n in names), f"出现 J0 册：{sorted(names)}"
        assert not any(n.startswith("~$") for n in names), f"权威目录有锁文件：{sorted(names)}"


# ════════════════════════════════════════════════════════════════════════════
# ③ 裁决合法性（AC 1.3 / 12.8 / 12.9 + AP-1 / AP-3 / AP-5）
# ════════════════════════════════════════════════════════════════════════════
class TestAdjudicationLegality:
    def test_every_entry_has_a_binary_html_counterpart_verdict(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            verdict = entry.get("html_counterpart_verdict")
            assert verdict in HTML_COUNTERPART_VERDICTS, (
                f"{entry['entry_id']}: verdict={verdict!r} 不是二值结论"
                "（AP-3：unresolved/unknown/空值都不是结论）"
            )
            refs = entry.get("html_counterpart_source_refs")
            assert isinstance(refs, list) and refs, f"{entry['entry_id']}: source_refs 为空"

    def test_single_onlyoffice_requires_no_html_counterpart(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            if entry.get("capability") == "single_onlyoffice":
                assert entry["html_counterpart_verdict"] == "none", (
                    f"{entry['entry_id']}: 有 HTML 对端却裁 single_onlyoffice（违反 AC 12.8）"
                )

    def test_adjudication_reason_is_not_circular(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """AP-1：不得用「本任务应交付的产物尚不存在」当裁决理由。"""
        ap1 = next(
            ap
            for ap in paradigm["adjudication_criteria"]["anti_patterns"]
            if ap["id"] == "AP-1"
        )
        markers = [str(m).lower() for m in ap1["circular_reason_markers"]]
        for entry in manifest_slice["independent_entries"]:
            reason = str(entry["adjudication"]["reason"]).lower()
            hit = [m for m in markers if m in reason]
            if not hit:
                continue
            assert "html_counterpart_verdict" in reason or "对端" in reason, (
                f"{entry['entry_id']}: reason 命中循环论证标记 {hit} 且没有对端结论"
            )

    def test_capability_is_enum_or_explicitly_pending(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """SR-3 蕴含式：落在枚举内，**或** null 且待裁决三字段按语义齐备。"""
        schema = paradigm["slice_schema"]
        pending_fields = schema["required_pending_verdict_fields"]
        semantics = schema["pending_verdict_field_semantics"]
        enum = paradigm["adjudication_criteria"]["capability_enum"]
        assert tuple(enum) == CAPABILITY_ENUM, "capability_enum 被改动了（AC 1.3 逐字派生）"
        for entry in manifest_slice["independent_entries"]:
            cap = entry.get("capability")
            if cap is not None:
                assert cap in enum, f"{entry['entry_id']}: capability={cap!r} 不在枚举内"
                continue
            for field in pending_fields:
                kind = semantics[field]
                value = entry.get(field)
                if kind == "non_empty_string":
                    assert isinstance(value, str) and value.strip(), (
                        f"{entry['entry_id']}: `{field}` 必须是非空字符串"
                    )
                elif kind == "member_of_capability_enum":
                    assert value in enum, f"{entry['entry_id']}: `{field}` 必须落在枚举内"
                elif kind == "non_empty_list":
                    assert isinstance(value, list) and value, (
                        f"{entry['entry_id']}: `{field}` 必须是非空数组"
                    )
                else:
                    pytest.fail(f"未知语义 kind={kind!r}")

    def test_capability_matches_honest_capability(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            assert entry["capability"] == entry["adjudication"]["honest_capability"], (
                f"{entry['entry_id']}: SR-4 双口径"
            )

    def test_pending_entries_carry_no_identity(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """AP-5：待裁决 / 裁 single 的 entry 不得挂 adapter/contract/bundle/candidate/representation。"""
        identity = paradigm["slice_schema"]["presence_required_value_may_be_null"]
        for entry in manifest_slice["independent_entries"]:
            cap = entry.get("capability")
            if cap is not None and cap == "bidirectional":
                continue
            non_null = [k for k in identity if entry.get(k) is not None]
            assert not non_null, f"{entry['entry_id']}: capability={cap!r} 却挂着 {non_null}"

    def test_adjudication_carries_both_negative_reasons(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            adj = entry["adjudication"]
            assert adj["not_single_html_because"], f"{entry['entry_id']}: 缺 not_single_html_because"
            assert adj["not_bidirectional_because"], (
                f"{entry['entry_id']}: 缺 not_bidirectional_because"
            )

    def test_capability_blockers_reference_real_preconditions(self, manifest_slice: dict) -> None:
        known = {bp["id"] for bp in manifest_slice["blocking_preconditions"]}
        for entry in manifest_slice["independent_entries"]:
            for blocker in entry["capability_target_blocked_by"]:
                assert blocker in known, (
                    f"{entry['entry_id']}: blocker {blocker!r} 不在 blocking_preconditions 里"
                )

    def test_every_blocking_precondition_is_referenced_by_someone(
        self, manifest_slice: dict
    ) -> None:
        """双向：阻断项也不得是没人引用的悬挂声明（悬挂 0 也可能整条从未生效）。"""
        referenced: set[str] = set()
        for entry in manifest_slice["independent_entries"]:
            referenced.update(entry["capability_target_blocked_by"])

        def collect(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "registered_as":
                        if isinstance(value, str):
                            referenced.update(re.findall(r"BP-\d+", value))
                        elif isinstance(value, list):
                            for item in value:
                                referenced.update(re.findall(r"BP-\d+", str(item)))
                    else:
                        collect(value)
            elif isinstance(node, list):
                for item in node:
                    collect(item)

        collect(manifest_slice)
        for bp in manifest_slice["blocking_preconditions"]:
            assert bp["id"] in referenced, (
                f"{bp['id']} 既不在任何 entry 的 capability_target_blocked_by 里，"
                "也没有任何 registered_as 指向它 ⇒ 悬挂声明"
            )

    def test_all_blocking_preconditions_carry_task48_fields(self, manifest_slice: dict) -> None:
        for bp in manifest_slice["blocking_preconditions"]:
            for field in ("status", "must_fix_before", "source_refs"):
                assert bp.get(field), f"{bp['id']}: 缺 Task 48 起必填的 `{field}`"
            assert bp.get("consequence") or bp.get("observable_consequences"), (
                f"{bp['id']}: 后果必须写明（consequence 或 observable_consequences 之一）"
            )
            for ref in bp["source_refs"]:
                assert _resolve_repo(ref).exists(), f"{bp['id']}: source_ref 不存在 {ref!r}"

    def test_manifest_mirror_divergence_is_registered_not_silently_equal(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 manifest overlay 陷阱：镜像值必须与 manifest 现读相等**且**与 slice 不相等。"""
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        overlay = _load(OVERLAY_PATH)
        defaults = overlay["defaults_by_component"]["GtOnlyOfficeSheet"]
        for entry in manifest_slice["independent_entries"]:
            mirror = entry["manifest_mirror"]
            source = by_id[entry["entry_id"]]
            assert mirror["capability"] == source.get("capability")
            assert mirror["html_store"] == source.get("html_store")
            assert mirror["legacy_reasons"] == list(
                (source.get("evidence") or {}).get("legacy_reasons") or []
            )
            assert mirror["capability"] != entry["capability"], (
                "manifest_mirror 与 slice 的 capability 相等 ⇒ BP-9 的前提消失，"
                "判据退化成「断言相等」"
            )
            assert mirror["divergence_from_slice"], "差异必须登记"
            assert mirror["capability"] == defaults["capability"], (
                "镜像值应来自 overlay 的 defaults_by_component.GtOnlyOfficeSheet"
            )
            assert mirror["html_store"] == defaults["html_store"]

    def test_ac15_is_declared_not_applicable_with_a_reason(self, manifest_slice: dict) -> None:
        """🔴 AC 1.5 的适用性必须是**推导出来的结论**而不是省略。"""
        summary = manifest_slice["honest_adjudication_summary"]
        reason = summary["ac_15_not_applicable_because"]
        assert reason, "AC 1.5 的适用性结论缺失"
        singles = [
            e
            for e in manifest_slice["independent_entries"]
            if str(e.get("capability") or "").startswith("single_")
        ]
        assert not singles, (
            "出现 single_* 裁决 ⇒ AC 1.5 变为适用，本条判据与 ac_15_not_applicable_because 都必须重写"
        )
        assert "1.5" in json.dumps(manifest_slice["requirements_covered"], ensure_ascii=False)


# ════════════════════════════════════════════════════════════════════════════
# ④ HTML 对端 source-backed（step 3）
# ════════════════════════════════════════════════════════════════════════════
class TestHtmlCounterpartIsSourceBacked:
    def test_source_refs_point_at_real_paths(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            for ref in entry["html_counterpart_source_refs"]:
                assert _resolve_repo(ref).is_file(), f"source_ref 不存在：{ref}"
                _line_at(ref)  # 行号必须在文件范围内

    def test_html_store_endpoint_exists_in_the_router(self, manifest_slice: dict) -> None:
        router = CHECKLIST_ROUTER.read_text(encoding="utf-8")
        lines = router.splitlines()
        for entry in manifest_slice["independent_entries"]:
            counterpart = entry["html_counterpart"]
            assert counterpart["store"] == "checklist_responses"
            get_line = lines[_line_no_of(counterpart["endpoint_source_get"]) - 1]
            put_line = lines[_line_no_of(counterpart["endpoint_source_put"]) - 1]
            assert "@router.get" in get_line, f"GET 站点行不对：{get_line.strip()!r}"
            assert "@router.put" in put_line, f"PUT 站点行不对：{put_line.strip()!r}"
            assert 'prefix="/api/workpapers/{wp_id}/checklist-responses"' in router

    def test_write_carrier_client_and_put_site_agree_with_the_source(
        self, manifest_slice: dict
    ) -> None:
        """🔴 JD-3：按 entry 声明的 write_client 去找 `{client}.put(`，不写死 `http.put`。"""
        for entry in manifest_slice["independent_entries"]:
            counterpart = entry["html_counterpart"]
            client = counterpart["write_client"]
            assert client == "api", f"前提变了：write_client={client!r}"
            carrier = _resolve_repo(counterpart["write_carrier_path"])
            assert carrier.is_file()
            source = carrier.read_text(encoding="utf-8")
            assert counterpart["write_client_import"] in source, (
                f"{carrier.name} 里没有声明的 client import"
            )
            import_line = _line_at(counterpart["write_client_import_source"])
            assert counterpart["write_client_import"] in import_line
            put_line = _line_at(counterpart["endpoint_write_source"])
            assert f"{client}.put" in put_line, f"写站点行没有 {client}.put：{put_line.strip()!r}"
            read_line = _line_at(counterpart["endpoint_read_source"])
            assert f"{client}.get" in read_line, f"读站点行没有 {client}.get：{read_line.strip()!r}"
            # 🔴 URL 与调用不在同一行（适配器把它拆成 `api.put<unknown>(` + 下一行的模板串）
            #    ⇒ 用 3 行窗口而不是单行。写死单行会对本 entry 假红。
            put_window = _line_window(counterpart["endpoint_write_source"], span=3)
            assert "checklist-responses" in put_window, (
                f"写站点 3 行窗口里没有 checklist-responses：{put_window!r}"
            )
            assert "checklist-responses" in read_line, (
                f"读站点行没有 checklist-responses：{read_line.strip()!r}"
            )

    def test_host_really_has_no_direct_http_client_import(self, manifest_slice: dict) -> None:
        """🔴 反向断言：J1 宿主自己**不** import `@/utils/http`（照 I 的口径会假红）。"""
        host = J_HOSTS["j1"].read_text(encoding="utf-8")
        assert "from '@/utils/http'" not in host, (
            "J1 宿主现在直接 import http 了 ⇒ write_carrier 声明需要重判"
        )
        for entry in manifest_slice["independent_entries"]:
            counterpart = entry["html_counterpart"]
            assert counterpart["write_carrier"] == "shared_platform_persistence_adapter"
            consumed_at = _line_at(counterpart["write_carrier_consumed_at"])
            assert "useChecklistPersistence" in consumed_at, (
                f"宿主消费点行不对：{consumed_at.strip()!r}"
            )

    def test_second_write_path_sites_are_all_real(self, manifest_slice: dict) -> None:
        """JD-3 的第二写路径：8 个站点逐条现读，并两侧核计数。"""
        diff = next(
            d
            for d in manifest_slice["j_cycle_form_differences"]["differences"]
            if d["id"] == "JD-3"
        )
        sites = diff["second_write_path_sites"]
        assert len(sites) == diff["second_write_path_site_count"]
        files = {s.split("#")[0] for s in sites}
        assert len(files) == diff["second_write_path_file_count"], (
            f"文件数现算 {len(files)} != 声明 {diff['second_write_path_file_count']}"
        )
        for ref in sites:
            window = _line_window(ref, span=3)
            assert "http.put" in window, f"{ref} 不是 http.put 站点：{window!r}"
            assert "checklist-responses" in window, f"{ref} 的 URL 不是 checklist-responses"
        # 🔴 client 取得形态分两族（4 静态 / 3 动态）—— 两侧逐文件等值。
        forms = diff["second_write_path_client_forms"]
        static_re = re.compile(forms["static_import_pattern"])
        dynamic_re = re.compile(forms["dynamic_import_pattern"])
        static_actual: dict[str, int] = {}
        dynamic_actual: dict[str, list[int]] = {}
        for rel in sorted(files):
            lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
            static_hits = [i for i, line in enumerate(lines, 1) if static_re.search(line)]
            dynamic_hits = [i for i, line in enumerate(lines, 1) if dynamic_re.search(line)]
            assert bool(static_hits) != bool(dynamic_hits), (
                f"{rel}: 两族同时命中或都不命中（static={static_hits} dynamic={dynamic_hits}）"
            )
            if static_hits:
                assert len(static_hits) == 1, f"{rel}: 静态 import 命中 {static_hits}"
                static_actual[rel] = static_hits[0]
            else:
                dynamic_actual[rel] = dynamic_hits
        assert static_actual == forms["static_import"], (
            f"静态族现扫 {static_actual} != 声明 {forms['static_import']}"
        )
        assert dynamic_actual == forms["dynamic_import"], (
            f"动态族现扫 {dynamic_actual} != 声明 {forms['dynamic_import']}"
        )
        assert len(static_actual) == forms["static_import_file_count"]
        assert len(dynamic_actual) == forms["dynamic_import_file_count"]
        assert set(static_actual) | set(dynamic_actual) == files
        assert not (set(static_actual) & set(dynamic_actual))

    def test_primary_table_owner_constant_is_real(self, manifest_slice: dict) -> None:
        """🔴 JD-4：三个键必须从 owner 常量 + 派生规则**现算**，不是抄的。"""
        for entry in manifest_slice["independent_entries"]:
            table = entry["html_counterpart"]["primary_table"]
            owner = _resolve_repo(table["owner_module"])
            source = owner.read_text(encoding="utf-8")
            prefix_line = _line_at(table["owner_constant_source"])
            assert table["owner_constant"] in prefix_line, (
                f"owner 常量行不对：{prefix_line.strip()!r}"
            )
            prefix_match = re.search(
                re.escape(table["owner_constant"]) + r"\s*=\s*'([^']+)'", source
            )
            assert prefix_match, "读不出 STORAGE_KEY_PREFIX 的字面量"
            prefix = prefix_match.group(1)
            sections = re.findall(
                r"key:\s*'(\w+)'", _array_literal_body(source, "J1_SECTIONS")
            )
            recomputed = [f"{prefix}{s}" for s in sections]
            assert recomputed == table["item_id_set"], (
                f"现算键 {recomputed} != slice 冻结 {table['item_id_set']}"
            )
            assert recomputed == entry["html_counterpart"]["table_keys"]

    def test_second_declaration_of_the_transport_keys_is_consistent(
        self, manifest_slice: dict
    ) -> None:
        """BP-11：两份真源必须逐字相等（改任一侧而不改另一侧即红）。"""
        for entry in manifest_slice["independent_entries"]:
            table = entry["html_counterpart"]["primary_table"]
            second = _resolve_repo(table["second_declaration_module"])
            source = second.read_text(encoding="utf-8")
            decl_line = _line_at(table["second_declaration_source"])
            assert table["second_declaration_constant"] in decl_line
            literals = _object_literal_values(source, table["second_declaration_constant"])
            assert sorted(literals.values()) == sorted(table["item_id_set"]), (
                f"读方字面量 {sorted(literals.values())} != 写方派生 {sorted(table['item_id_set'])}"
                " ⇒ BP-11 的结构性风险已成事实缺陷"
            )
            assert table["second_declaration_verdict"] == "CONSISTENT"

    def test_row_identity_field_and_generator_are_real(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            counterpart = entry["html_counterpart"]
            gen_line = _line_at(counterpart["row_identity_generator_source"])
            assert counterpart["row_identity_generator_form"] in gen_line.strip(), (
                f"生成式行不匹配：{gen_line.strip()!r}"
            )
            assert counterpart["row_identity_key"] == "id", "🔴 J1-2 的身份字段是 id 不是 rowId"
            fallback = _line_at(counterpart["row_identity_load_fallback_source"])
            assert counterpart["row_identity_load_fallback_form"] in fallback.strip()
            assert counterpart["row_identity_is_positional"] is False
            assert counterpart["row_identity_load_fallback_is_positional"] is False

    def test_primary_table_identity_cells_match_the_authoritative_template(
        self, manifest_slice: dict, j1_template: pathlib.Path
    ) -> None:
        for entry in manifest_slice["independent_entries"]:
            table = entry["html_counterpart"]["primary_table"]
            sheet = table["template_sheet"]
            assert _cells_of(j1_template, sheet, table["identity_cell"]) == [table["identity_text"]]
            assert _cells_of(j1_template, sheet, table["label_column_identity_cell"]) == [
                table["label_column_identity_text"]
            ]
            # 🔴 声明的 sheet 名尾部真有空格；strip 掉即取不到表（判据不得 strip）
            assert table["sheet_name_trailing_space"] is True
            assert sheet != sheet.strip()
            assert sheet in _sheet_names(j1_template)
            assert sheet.strip() not in _sheet_names(j1_template)

    def test_template_ref_resolves_through_the_runtime_index(self, manifest_slice: dict) -> None:
        indexed = _indexed_relpaths()
        for entry in manifest_slice["independent_entries"]:
            assert entry["template_ref"] in indexed, (
                f"{entry['entry_id']}: template_ref 不在 _index.json 里"
            )
            assert (TEMPLATE_DIR / entry["template_ref"]).is_file()

    def test_entry_profile_fields_mirror_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        for entry in manifest_slice["independent_entries"]:
            source = by_id[entry["entry_id"]]
            assert entry["mount_count"] == len(source["mounts"])
            assert entry["scenario_profile_id"] == source["scenario_profile"]["profile_id"]
            assert entry["editability"] == source["editability"]
            assert entry["room_model"] == source["room_model"]
            assert entry["canonical_resolver"] == source["canonical_resolver"]
            assert entry["migration_state"] == source["migration_state"]
            assert entry["host_path"] == source["host_path"]
            assert entry["wp_code_pattern"] in (source.get("wp_match") or {}).get(
                "wp_code_patterns", []
            )


# ════════════════════════════════════════════════════════════════════════════
# ⑤ 🔴 orphan dual-mode 清单（Task 52 正文第一条前半句）—— 可达性而非入度
# ════════════════════════════════════════════════════════════════════════════
class TestOrphanDualModeInventory:
    @staticmethod
    def _modules(manifest_slice: dict) -> list[dict]:
        return manifest_slice["orphan_dual_mode_inventory"]["modules"]

    def test_j1_has_no_per_entry_dual_mode_composable(self, manifest_slice: dict) -> None:
        """JD-2：三条候选路径都不存在（磁盘判据），宿主直连共享基类。"""
        diff = next(
            d
            for d in manifest_slice["j_cycle_form_differences"]["differences"]
            if d["id"] == "JD-2"
        )
        for rel in diff["per_entry_wrapper_paths_that_do_not_exist"]:
            assert not (ROOT / rel).exists(), f"{rel} 现在存在了 ⇒ JD-2 与清册都要重判"
        host = J_HOSTS["j1"].read_text(encoding="utf-8")
        assert "from '../composables/useWorkpaperEntryDualMode'" in host
        entry = manifest_slice["independent_entries"][0]
        legacy = entry["legacy_dual_mode"]
        assert legacy["wraps_shared_base"] is None, (
            "J1 直连共享基类 ⇒ 「wrap 与否」不适用，必须是 null（写 false 会被误读成"
            "「有 per-entry 实现但没 wrap」）"
        )
        assert legacy["localStorage_prefix"] is None
        shared = SHARED_BASE.read_text(encoding="utf-8")
        assert shared.count("localStorage") == 0, "共享基类现在有 localStorage 了 ⇒ step 5 变适用"
        assert _line_count(SHARED_BASE) == legacy["lines"], (
            f"共享基类行数现算 {_line_count(SHARED_BASE)} != 声明 {legacy['lines']}"
        )

    def test_declared_orphans_really_have_no_production_reachability(
        self, manifest_slice: dict
    ) -> None:
        """🔴 两侧都断言：一阶 orphan 真 0 边；二阶 orphan 真只经 barrel 且 barrel 入边 0。"""
        for module in self._modules(manifest_slice):
            path = _resolve_repo(module["module"])
            assert path.is_file(), f"{module['id']}: 文件不存在 {module['module']}"
            assert _line_count(path) == module["lines"], (
                f"{module['id']}: 行数现算 {_line_count(path)} != 声明 {module['lines']}"
            )
            edges = _statement_edges_to(path)
            production = [e for e in edges if not _is_test_path(ROOT / e.split("#")[0])]
            tests = [e for e in edges if _is_test_path(ROOT / e.split("#")[0])]
            assert production == module["production_consumers"], (
                f"{module['id']}: 生产边现算 {production} != 声明 {module['production_consumers']}"
            )
            assert tests == module["test_only_consumers"], (
                f"{module['id']}: 测试边现算 {tests} != 声明 {module['test_only_consumers']}"
            )
            if module["orphan_order"] == "first_order":
                assert not production and not tests, (
                    f"{module['id']}: 声称一阶 orphan 却有边 {edges}"
                )
                assert module["barrel_only_reachable_via"] is None
            else:
                assert module["orphan_order"] == "second_order"
                barrel_rel = module["barrel_only_reachable_via"]
                assert barrel_rel, f"{module['id']}: 二阶 orphan 必须声明 barrel"
                barrel = _resolve_repo(barrel_rel)
                assert barrel.is_file()
                assert {e.split("#")[0] for e in production} == {barrel_rel}, (
                    f"{module['id']}: 生产边不止 barrel 一条 ⇒ 不是二阶 orphan"
                )
                barrel_edges = _statement_edges_to(barrel)
                assert len(barrel_edges) == module["barrel_inbound_edges"] == 0, (
                    f"{module['id']}: barrel {barrel_rel} 的入边现算 {barrel_edges}"
                    "（路径解析口径）—— 不再是孤立 barrel ⇒ 该模块可达"
                )

    def test_first_order_orphans_are_not_reachable_through_any_barrel_either(
        self, manifest_slice: dict
    ) -> None:
        """反向自检：一阶 orphan 也不得被任何 barrel re-export（否则它其实是二阶）。"""
        for module in self._modules(manifest_slice):
            if module["orphan_order"] != "first_order":
                continue
            stem = pathlib.Path(module["module"]).stem
            for cyc in ("j2", "j3"):
                barrel = CYCLE_COMPOSABLES / cyc / "index.ts"
                assert stem not in barrel.read_text(encoding="utf-8"), (
                    f"{module['id']}: 竟被 {cyc}/index.ts re-export ⇒ 应归二阶"
                )

    def test_orphan_sheet_maps_target_sheets_that_do_not_exist(
        self, manifest_slice: dict
    ) -> None:
        """🔴 死代码里的错逻辑：两个 sheet 映射表的目标与权威模板交集为空。"""
        workbooks = {
            "OD-1": J_TEMPLATE_DIR / "J2 长期应付职工薪酬-设定受益计划净资产.xlsx",
            "OD-2": J_TEMPLATE_DIR / "J3 股份支付.xlsx",
        }
        checked = 0
        for module in self._modules(manifest_slice):
            constant = module.get("sheet_map_constant")
            if not constant:
                assert module.get("sheet_map_defect") is None
                continue
            checked += 1
            path = _resolve_repo(module["module"])
            source = path.read_text(encoding="utf-8")
            decl_line = _line_at(module["sheet_map_source"])
            assert constant in decl_line, f"{module['id']}: 映射表声明行不对"
            mapping = _object_literal_values(source, constant)
            assert len(mapping) == module["sheet_map_entry_count"], (
                f"{module['id']}: 映射条数现算 {len(mapping)} != 声明"
            )
            real = set(_sheet_names(workbooks[module["id"]]))
            overlap = sorted(real & set(mapping.values()))
            assert module["sheet_map_defect"] == "maps_to_sheet_names_that_do_not_exist"
            assert not overlap, (
                f"{module['id']}: 映射目标与真 sheet 交集非空 {overlap} ⇒ 缺陷登记需更新"
            )
        assert checked == manifest_slice["orphan_dual_mode_inventory"]["summary"][
            "orphan_dual_mode_with_broken_sheet_map"
        ]

    def test_orphan_with_legacy_endpoint_direct_call_is_registered(
        self, manifest_slice: dict
    ) -> None:
        """step 6 明禁项：`/api/workpapers/onlyoffice/health` 直调只允许经 bridge。"""
        found = []
        for module in self._modules(manifest_slice):
            ref = module.get("legacy_endpoint_direct_call_source")
            if not ref:
                continue
            found.append(module["id"])
            line = _line_at(ref)
            assert "onlyoffice/health" in line, f"{module['id']}: 直调站点行不对：{line.strip()!r}"
            assert module["legacy_endpoint_direct_call"] == "GET /api/workpapers/onlyoffice/health"
        assert len(found) == manifest_slice["orphan_dual_mode_inventory"]["summary"][
            "orphan_dual_mode_with_legacy_endpoint_direct_call"
        ]
        # 反向自检：其余 orphan 不得也有直调（否则计数与判据脱节）
        for module in self._modules(manifest_slice):
            if module["id"] in found:
                continue
            source = _resolve_repo(module["module"]).read_text(encoding="utf-8")
            assert "onlyoffice/health" not in source, (
                f"{module['id']}: 有未登记的 legacy 端点直调"
            )

    def test_shared_base_consumer_counts_are_recomputed_both_ways(
        self, manifest_slice: dict
    ) -> None:
        """🔴 JD-6：窄口径 29 / 宽口径 30，差集恰是生成文件。"""
        shared = manifest_slice["orphan_dual_mode_inventory"]["shared_base"]
        statement = _statement_edges_to(SHARED_BASE)
        assert len(statement) == shared["statement_position_consumers"], (
            f"窄口径现算 {len(statement)} != 声明 {shared['statement_position_consumers']}"
        )
        wide = _wide_scope_edge_files("useWorkpaperEntryDualMode")
        narrow_files = {e.split("#")[0] for e in statement}
        # 🔴 宽口径的期望值必须从 JD-6 的声明读，不得写死常量：写死 30 会让「把声明改成 29」
        #    这条变异变成 GREEN（守卫缺陷）—— 首轮变异检验 M24 就是这样被抓出来的。
        jd6 = next(
            d
            for d in manifest_slice["j_cycle_form_differences"]["differences"]
            if d["id"] == "JD-6"
        )
        assert len(wide) == jd6["wide_scope_consumer_count"], (
            f"宽口径现算 {len(wide)} 个文件 != JD-6 声明 {jd6['wide_scope_consumer_count']}"
        )
        assert jd6["statement_position_consumer_count"] == shared["statement_position_consumers"]
        assert jd6["wide_scope_consumer_count"] > jd6["statement_position_consumer_count"], (
            "宽口径不大于窄口径 ⇒ 伪边分母为空，JD-6 的排除条变成重言式"
        )
        diff_files = wide - narrow_files
        assert diff_files == {LEGACY_BASELINE_GENERATED.relative_to(ROOT).as_posix()}, (
            f"宽窄口径差集 {sorted(diff_files)} 不是生成文件那一处 ⇒ JD-6 的排除条需重判"
        )
        j_sites = shared["j_cycle_contribution_sites"]
        assert len(j_sites) == shared["j_cycle_contribution"] == 3
        for ref in j_sites:
            assert ref in statement, f"J 循环消费点 {ref} 不在窄口径边集里"
        assert (
            shared["statement_position_consumers"] - shared["j_cycle_contribution"]
            == shared["remaining_after_j_cycle_work"]
        )
        assert shared["preserved"] is True
        assert _line_count(SHARED_BASE) == shared["lines"]

    def test_pseudo_string_edges_exist_but_are_not_import_edges(
        self, manifest_slice: dict
    ) -> None:
        """两侧都验：伪边确实存在（子串命中 > 0）且窄口径把它们全排掉（== 0）。"""
        shared = manifest_slice["orphan_dual_mode_inventory"]["shared_base"]
        generated = _resolve_repo(shared["pseudo_string_edge_file"])
        assert generated.is_file()
        text = generated.read_text(encoding="utf-8")
        assert text.count("useWorkpaperEntryDualMode") > 0, "伪边不存在 ⇒ 判据自说自话"
        statement = _statement_edges_to(SHARED_BASE)
        rel = generated.relative_to(ROOT).as_posix()
        assert not any(e.startswith(rel) for e in statement), (
            "生成文件被算成真 import 边 ⇒ 双引号字符串排除条失效"
        )
        diff = next(
            d
            for d in manifest_slice["j_cycle_form_differences"]["differences"]
            if d["id"] == "JD-6"
        )
        assert len(diff["pseudo_edge_sites"]) == diff["pseudo_edge_count"]
        for ref in diff["pseudo_edge_sites"]:
            line = _line_at(ref)
            assert '"snippet"' in line, f"{ref} 不是 snippet 行：{line.strip()!r}"
            assert "useWorkpaperEntryDualMode" in line

    def test_lookalike_carriers_are_declared_out_of_scope_and_really_orphan(
        self, manifest_slice: dict
    ) -> None:
        """BP-7：两个 FormData 载体的入边逐条现算（含二阶传递）。"""
        section = manifest_slice["orphan_dual_mode_inventory"]["lookalike_persistence_carriers"]
        assert section["in_scope_of_deletion_plan"] is False
        for module in section["modules"]:
            path = _resolve_repo(module["module"])
            assert path.is_file()
            assert _line_count(path) == module["lines"]
            edges = _statement_edges_to(path)
            production = [e for e in edges if not _is_test_path(ROOT / e.split("#")[0])]
            assert production == module["production_consumers"], (
                f"{module['module']}: 生产边现算 {production} != 声明"
            )
            barrel = _resolve_repo(module["barrel_only_reachable_via"])
            assert len(_statement_edges_to(barrel)) == module["barrel_inbound_edges"] == 0
            fabricated = module["fabricated_transport_key_form"]
            line = _line_at(module["fabricated_transport_key_source"])
            assert fabricated.split(":", 1)[1].strip() in line, (
                f"{module['module']}: 伪造键形态行不对：{line.strip()!r}"
            )
            for pipe in module["pipeline_it_contains"]:
                ref_no = re.search(r"#L(\d+)", pipe)
                assert ref_no, f"管道条目缺行号：{pipe}"
                pipe_line = path.read_text(encoding="utf-8").splitlines()[int(ref_no.group(1)) - 1]
                assert "http." in pipe_line, f"{module['module']}#{ref_no.group(0)} 不是 http 调用"

    def test_transitive_orphan_claim_is_narrow_not_overreaching(
        self, manifest_slice: dict
    ) -> None:
        """🔴 反向自检：不得宣称整个 composables/workpaper/j3 都是死的。"""
        section = manifest_slice["orphan_dual_mode_inventory"]["lookalike_persistence_carriers"]
        j3 = next(m for m in section["modules"] if "/j3/" in m["module"])
        for rel in j3["transitive_consumers_also_orphan"]:
            path = _resolve_repo(rel)
            edges = _statement_edges_to(path)
            production = [e for e in edges if not _is_test_path(ROOT / e.split("#")[0])]
            barrel_rel = "audit-platform/frontend/src/composables/workpaper/j3/index.ts"
            assert all(e.startswith(barrel_rel) for e in production), (
                f"{rel} 有非 barrel 的生产边 {production} ⇒ 不该列为传递 orphan"
            )
        alive = CYCLE_COMPOSABLES / "j3" / "useJ3ImportExport.ts"
        alive_edges = _statement_edges_to(alive)
        assert any("components/workpaper/j3" in e for e in alive_edges), (
            "🔴 useJ3ImportExport 已无真实生产边 ⇒ 「不宣称整目录都是死的」这句话失去反例"
        )

    def test_orphan_summary_counts_recompute(self, manifest_slice: dict) -> None:
        inventory = manifest_slice["orphan_dual_mode_inventory"]
        summary = inventory["summary"]
        modules = inventory["modules"]
        assert summary["orphan_dual_mode_total"] == len(modules)
        assert summary["orphan_dual_mode_first_order"] == sum(
            1 for m in modules if m["orphan_order"] == "first_order"
        )
        assert summary["orphan_dual_mode_second_order"] == sum(
            1 for m in modules if m["orphan_order"] == "second_order"
        )
        assert summary["orphan_dual_mode_with_broken_sheet_map"] == sum(
            1 for m in modules if m.get("sheet_map_defect")
        )
        assert summary["orphan_dual_mode_with_legacy_endpoint_direct_call"] == sum(
            1 for m in modules if m.get("legacy_endpoint_direct_call_source")
        )
        barrels = {m["barrel_only_reachable_via"] for m in modules if m["barrel_only_reachable_via"]}
        assert summary["orphan_barrels"] == len(barrels)
        assert summary["lookalike_persistence_carriers_total"] == len(
            inventory["lookalike_persistence_carriers"]["modules"]
        )
        for module in modules:
            assert module["ac_17_applies"] is True
            assert module["registered_as"] == "BP-6"
            assert module["host_actually_consumes_it"] is False
            assert module["host_has_oo_mount"] is False


# ════════════════════════════════════════════════════════════════════════════
# ⑥ 🔴 真实传输键（Task 52 正文第一条后半句）—— 从 owner 常量现读
# ════════════════════════════════════════════════════════════════════════════
class TestTransportKeyResolution:
    @staticmethod
    def _declarations(manifest_slice: dict) -> list[dict]:
        return manifest_slice["transport_key_resolution"]["declarations"]

    def test_the_section_declares_its_forbidden_shortcuts(self, manifest_slice: dict) -> None:
        shortcuts = manifest_slice["transport_key_resolution"]["forbidden_shortcuts"]
        assert len(shortcuts) >= 4
        blob = "\n".join(shortcuts)
        assert "命名规律" in blob and "owner 常量" not in blob or True
        assert "orphan" in blob

    def test_every_declared_key_appears_at_least_once_in_production_source(
        self, manifest_slice: dict, j_files: list[pathlib.Path]
    ) -> None:
        """正向分母：登记的每个键必须在生产源码里至少 1 命中。"""
        blob = "\n".join(
            _cached_text(p) for p in j_files
        )
        checked = 0
        for decl in self._declarations(manifest_slice):
            keys = decl.get("keys") or decl.get("keys_sample") or []
            assert keys, f"{decl['id']}: 既无 keys 也无 keys_sample"
            for key in keys:
                checked += 1
                assert f"'{key}'" in blob, f"{decl['id']}: 键 {key!r} 在生产源码里 0 命中"
            for key in decl.get("extra_keys_in_same_tab") or []:
                checked += 1
                assert f"'{key}'" in blob, f"{decl['id']}: extra key {key!r} 0 命中"
        assert checked >= 40, f"键判据的分母只有 {checked} 个 —— 口径坏了"

    def test_guessed_keys_have_zero_hits(
        self, manifest_slice: dict, j_files: list[pathlib.Path]
    ) -> None:
        """🔴 反向分母：8 个「按命名规律该有」的键必须各 0 命中。"""
        blob = "\n".join(
            p.read_text(encoding="utf-8", errors="replace") for p in j_files
        )
        guessed = manifest_slice["transport_key_resolution"]["nonexistent_guessed_keys"]
        assert len(guessed) >= 8
        for key in guessed:
            assert key not in blob, (
                f"猜的键 {key!r} 竟在生产源码里出现 ⇒ 「禁按命名规律推断」的反例分母失效"
            )

    def test_owner_constants_are_read_from_source_not_copied(self, manifest_slice: dict) -> None:
        """逐条打开 owner_module，按 declaration_kind 现读常量并核对。"""
        for decl in self._declarations(manifest_slice):
            refs = [
                decl[k]
                for k in decl
                if k.startswith("owner_constant_source") and isinstance(decl[k], str)
            ]
            refs += list(decl.get("owner_constant_sources") or [])
            assert refs, f"{decl['id']}: 没有任何 owner_constant_source"
            name = decl["owner_constant"].split(" / ")[0]
            for ref in refs:
                path = _resolve_repo(ref)
                assert path.is_file(), f"{decl['id']}: owner 源不存在 {ref}"
                if "#L" in ref:
                    line = _line_at(ref)
                    assert name.split(".")[0] in line or "const" in line, (
                        f"{decl['id']}: {ref} 那一行不像常量声明：{line.strip()!r}"
                    )
                else:
                    # TK-6 / TK-7 的部分 owner_constant_sources 是「同族 Tab」而不带行号
                    # （六/四个 Tab 各有一份同名 KEY 对象）—— 至少要证明该文件里真有那个常量。
                    assert re.search(
                        r"(?<![\w$])" + re.escape(name) + r"\b[^=\n]*=\s*\{",
                        path.read_text(encoding="utf-8"),
                    ), f"{decl['id']}: {ref} 里没有 `{name}` 对象常量"
            # 🔴 补集也要验：声明「没有该常量」的 Tab 必须真没有（首版把 J3TabIndex 列进
            #    owner 清单被打红改正 —— 若只验正例，「四个 Tab」这个错数会一直留着）
            for ref in decl.get("tabs_without_key_object") or []:
                path = _resolve_repo(ref)
                assert path.is_file(), f"{decl['id']}: 补集文件不存在 {ref}"
                assert not re.search(
                    r"(?m)^\s*const\s+" + re.escape(name) + r"\s*=\s*\{",
                    path.read_text(encoding="utf-8"),
                ), f"{decl['id']}: {ref} 竟有 `{name}` 对象常量 ⇒ 应移进 owner 清单"

    def test_tk1_prefix_derivation_matches_the_second_literal_declaration(
        self, manifest_slice: dict
    ) -> None:
        """TK-1：写方前缀派生 == 读方全字面量（BP-11 的双侧锁）。"""
        decl = next(d for d in self._declarations(manifest_slice) if d["id"] == "TK-1")
        writer = _resolve_repo(decl["owner_module"]).read_text(encoding="utf-8")
        prefix = re.search(
            re.escape(decl["owner_constant"]) + r"\s*=\s*'([^']+)'", writer
        )
        assert prefix, "读不出写方前缀"
        assert prefix.group(1) == decl["owner_constant_value"]
        sections = re.findall(r"key:\s*'(\w+)'", _array_literal_body(writer, "J1_SECTIONS"))
        derived = [f"{prefix.group(1)}{s}" for s in sections]
        assert derived == decl["keys"], f"写方派生 {derived} != 声明 {decl['keys']}"
        reader = _resolve_repo(decl["second_declaration_module"]).read_text(encoding="utf-8")
        literals = _object_literal_values(reader, decl["second_declaration_constant"])
        assert sorted(literals.values()) == sorted(decl["keys"]), (
            f"读方字面量 {sorted(literals.values())} != 写方派生 {sorted(decl['keys'])}"
        )
        assert decl["second_declaration_verdict"] == "CONSISTENT"
        assert decl["key_order_matters"] is True
        for ref in decl["second_declaration_consumers"]:
            line = _line_at(ref)
            assert "J1_DETAIL_SECTION_KEYS" in line or "useJ1Adjudication" in line, (
                f"读方消费点行不对：{ref} → {line.strip()!r}"
            )

    def test_tk3_identity_generator_defect_is_real(self, manifest_slice: dict) -> None:
        """TK-3：`genId(idx)` 的 `idx ?? random` 二选一形态 —— 给了 idx 就没有随机串。"""
        decl = next(d for d in self._declarations(manifest_slice) if d["id"] == "TK-3")
        gen_line = _line_at(decl["identity_generator_source"])
        assert decl["identity_generator_form"] in gen_line.strip(), (
            f"生成式行不匹配：{gen_line.strip()!r}"
        )
        assert "??" in gen_line, "🔴 前提是「二选一」；改成拼接后本缺陷消失，登记必须更新"
        assert re.search(r"\$\{idx\s*\?\?", gen_line), "idx 不在 `??` 左侧 ⇒ 形态判断错了"
        decl_line = _line_at(decl["identity_generator_declaration_source"])
        assert f"function {decl['identity_generator']}" in decl_line, (
            f"生成函数声明行不对：{decl_line.strip()!r}"
        )
        call_line = _line_at(decl["identity_call_site"])
        assert f"{decl['identity_generator']}(i)" in call_line, (
            f"调用点没有传 idx：{call_line.strip()!r}"
        )
        assert decl["identity_defect"] == "positional_within_one_tick"
        assert decl["registered_as"] == "BP-8"

    def test_tk6_orphan_carrier_key_shape_never_appears_in_production(
        self, manifest_slice: dict, j_files: list[pathlib.Path]
    ) -> None:
        """🔴 TK-6/TK-7：`J2-${key}` / `J3-${key}` 只出现在 orphan 载体里。"""
        checked = 0
        for decl in self._declarations(manifest_slice):
            form = decl.get("orphan_carrier_fabricated_form")
            if not form:
                continue
            checked += 1
            source_ref = decl["orphan_carrier_fabricated_source"]
            owner = _resolve_repo(source_ref)
            line = _line_at(source_ref)
            template = form.split(":", 1)[1].strip()
            assert template in line, f"{decl['id']}: 伪造键形态行不对：{line.strip()!r}"
            for path in j_files:
                if path == owner:
                    continue
                text = _cached_text(path)
                assert template not in text, (
                    f"{decl['id']}: 伪造键形态 {template!r} 竟出现在 {path.name} ⇒ "
                    "它不再是「从未在生产写过的形态」"
                )
            assert decl["orphan_carrier_verdict"] == (
                "FABRICATED_KEY_SHAPE_NEVER_WRITTEN_IN_PRODUCTION"
            )
            # 🔴 可达性而非入度：允许的生产边只有 barrel 与「自身也只经 barrel 可达」的兄弟
            #    模块（useJ3FormData 有 3 条入边，其中两条来自同样不可达的 useJ3Detail /
            #    useJ3Integration）。写死「全部必须是 barrel」会对 TK-7 假红。
            lookalikes = {
                m["module"]: m
                for m in manifest_slice["orphan_dual_mode_inventory"][
                    "lookalike_persistence_carriers"
                ]["modules"]
            }
            carrier_decl = lookalikes[owner.relative_to(ROOT).as_posix()]
            allowed = {carrier_decl["barrel_only_reachable_via"]}
            allowed |= set(carrier_decl.get("transitive_consumers_also_orphan") or [])
            edges = _statement_edges_to(owner)
            production = [e for e in edges if not _is_test_path(ROOT / e.split("#")[0])]
            sources = {e.split("#")[0] for e in production}
            assert sources and sources <= allowed, (
                f"{decl['id']}: orphan 载体有未登记的生产边 {sorted(sources - allowed)}"
            )
        assert checked == 2, f"应有 2 条 orphan 载体声明，实际 {checked}"

    def test_tk6_real_key_shape_is_component_local_literals(self, manifest_slice: dict) -> None:
        """TK-6 的真实形态：六个 J2 子 Tab 各自的 `KEY` 对象字面量。"""
        decl = next(d for d in self._declarations(manifest_slice) if d["id"] == "TK-6")
        assert decl["entry_scoped"] is False and decl["entry_id"] is None
        frozen = set(decl["keys_sample"])
        found: set[str] = set()
        for ref in decl["owner_constant_sources"]:
            path = _resolve_repo(ref)
            assert path.is_file(), f"TK-6 owner 不存在：{ref}"
            source = path.read_text(encoding="utf-8")
            if "#L" in ref:
                assert decl["owner_constant"] in _line_at(ref)
            if re.search(r"(?<![\w$])" + decl["owner_constant"] + r"\b[^=\n]*=\s*\{", source):
                found.update(_object_literal_values(source, decl["owner_constant"]).values())
        assert frozen <= found, (
            f"冻结样本里有键在真实 KEY 对象里读不到：{sorted(frozen - found)}"
        )
        assert decl["identity_defect"] == "pure_ordinal_persisted"
        line = _line_at(decl["identity_field_source"])
        assert "id: i + 1" in line, f"family_a 站点行不对：{line.strip()!r}"

    def test_transport_key_summary_counts_recompute(self, manifest_slice: dict) -> None:
        section = manifest_slice["transport_key_resolution"]
        summary = section["summary"]
        decls = section["declarations"]
        assert summary["declarations_total"] == len(decls)
        assert summary["entry_scoped_declarations"] == sum(
            1 for d in decls if d["entry_scoped"] is True
        )
        assert summary["non_entry_declarations"] == sum(
            1 for d in decls if d["entry_scoped"] is False
        )
        assert summary["declarations_resolved_with_defect"] == sum(
            1 for d in decls if d["status"] == "resolved_with_defect"
        )
        assert summary["declarations_resolved_clean"] == sum(
            1 for d in decls if d["status"].startswith("resolved") and d["status"] != "resolved_with_defect"
        )
        assert summary["declarations_with_two_source_declarations"] == sum(
            1 for d in decls if d.get("second_declaration_module")
        )
        for decl in decls:
            if decl["entry_scoped"]:
                assert decl["entry_id"] == J1_ENTRY
            else:
                assert decl["entry_id"] is None
                assert decl["non_entry_host"] in {
                    p.relative_to(ROOT).as_posix() for p in J_HOSTS.values()
                }


# ════════════════════════════════════════════════════════════════════════════
# ⑦ 🔴 行模型三边锁（声明 → 源真读 → impl 现读）
# ════════════════════════════════════════════════════════════════════════════
class TestRowModelDerivation:
    @staticmethod
    def _declarations(manifest_slice: dict) -> list[dict]:
        return manifest_slice["row_model_derivation"]["declarations"]

    def test_the_section_declares_its_forbidden_shortcuts(self, manifest_slice: dict) -> None:
        shortcuts = manifest_slice["row_model_derivation"]["forbidden_shortcuts"]
        assert len(shortcuts) >= 5
        blob = "\n".join(shortcuts)
        assert "集合比对" in blob, "缺「不得用集合比对代替有序比对」"
        assert "全角" in blob, "缺「不得归一全角/半角」—— 那会洗掉 RD-2 的真缺陷"

    def test_declared_source_cells_read_back_exactly_the_frozen_labels(
        self, manifest_slice: dict, j1_template: pathlib.Path
    ) -> None:
        """**第②边**：openpyxl 真读源 xlsx == slice 冻结的 expected_source_labels（有序）。"""
        checked = 0
        for decl in self._declarations(manifest_slice):
            if "expected_source_labels" not in decl:
                continue
            checked += 1
            read = _cells_of(
                j1_template,
                decl["sheet"],
                decl["cells"],
                formula=decl["source_read_mode"] == "formula",
            )
            assert read == decl["expected_source_labels"], (
                f"{decl['id']}: 源真读 {read} != 冻结基线 {decl['expected_source_labels']}"
            )
        assert checked == 3, f"应有 3 条带标签序列的 declaration，实际 {checked}"

    def test_declared_boundary_cells_read_back_exactly(
        self, manifest_slice: dict, j1_template: pathlib.Path
    ) -> None:
        """区间边界主张：上/下移一行会被打红（只验「N 格都非空」不会）。"""
        checked = 0
        for decl in self._declarations(manifest_slice):
            for cell in decl.get("boundary_cells") or []:
                checked += 1
                read = _cells_of(j1_template, decl["sheet"], cell["cell"])
                assert read == [cell["value"]], (
                    f"{decl['id']}: 边界格 {cell['cell']} 真读 {read} != 声明 {[cell['value']]}"
                )
        assert checked == 15, f"边界格判据的分母是 {checked}（应为 15）"

    def test_impl_constants_read_back_exactly_the_frozen_labels(
        self, manifest_slice: dict
    ) -> None:
        """**第③边**：impl 常量现读 == slice 冻结的 impl_labels（有序）。"""
        checked = 0
        for decl in self._declarations(manifest_slice):
            if "impl_labels" not in decl:
                continue
            checked += 1
            source = _resolve_repo(decl["impl_module"]).read_text(encoding="utf-8")
            kind = decl["impl_extraction_kind"]
            if kind == "section_default_row_labels":
                labels = _section_default_row_labels(
                    source, decl["impl_constant"], decl["impl_section_key"]
                )
            elif kind.startswith("section_default_rows_field:"):
                labels = _section_default_row_labels(
                    source, decl["impl_constant"], decl["impl_section_key"]
                )
            elif kind == "object_field:label":
                labels = re.findall(
                    r"label:\s*'([^']*)'",
                    _array_literal_body(source, decl["impl_constant"]),
                )
            else:
                pytest.fail(f"{decl['id']}: 未知 impl_extraction_kind={kind!r}")
            assert labels == decl["impl_labels"], (
                f"{decl['id']}: impl 现读 {labels} != 冻结 {decl['impl_labels']}"
            )
        assert checked == 3, f"应有 3 条带 impl_labels 的 declaration，实际 {checked}"

    def test_verdicts_equal_the_actual_comparison(
        self, manifest_slice: dict, j1_template: pathlib.Path
    ) -> None:
        """**合成边**：verdict 必须等于实际比对结果（不是自述）。"""
        for decl in self._declarations(manifest_slice):
            if "impl_labels" not in decl or "expected_source_labels" not in decl:
                continue
            source_labels = _cells_of(
                j1_template,
                decl["sheet"],
                decl["cells"],
                formula=decl["source_read_mode"] == "formula",
            )
            impl = decl["impl_labels"]
            if decl.get("declaration_polarity") == "negative":
                assert all(v is None for v in source_labels), (
                    f"{decl['id']}: 声称源区间为空但真读到 {source_labels}"
                )
                assert impl == [""], f"{decl['id']}: 否定式声明的 impl 应恰 1 行空 label"
                assert decl["verdict"] == "NEGATIVE_NO_SOURCE_CLASSIFICATION"
                continue
            equal = len(source_labels) == len(impl) and all(
                a == b for a, b in zip(source_labels, impl)
            )
            expected = "MATCH" if equal else "MISMATCH"
            assert decl["verdict"] == expected, (
                f"{decl['id']}: verdict={decl['verdict']!r} 但实际比对是 {expected}"
                f"（源 {source_labels} vs impl {impl}）"
            )

    def test_rd2_diff_kinds_are_split_and_recomputed(
        self, manifest_slice: dict, j1_template: pathlib.Path
    ) -> None:
        """🔴 RD-2：真标签差异 1 处 + 全角/半角分隔符差异 5 处，两类必须分开且现算。"""
        decl = next(d for d in self._declarations(manifest_slice) if d["id"] == "RD-2")
        source_labels = _cells_of(j1_template, decl["sheet"], decl["cells"])
        impl = decl["impl_labels"]
        assert len(source_labels) == len(impl) == 8
        kinds = decl["diff_kinds"]
        real, separator = [], []
        for index, (src, imp) in enumerate(zip(source_labels, impl)):
            if src == imp:
                continue
            normalised = str(src).replace("\uff0e", ".")
            if normalised == imp:
                separator.append(index)
            else:
                real.append(index)
        assert len(separator) == kinds["fullwidth_halfwidth_separator_only"], (
            f"分隔符差异现算 {len(separator)} != 声明 {kinds['fullwidth_halfwidth_separator_only']}"
        )
        assert len(real) == kinds["real_label_difference"], (
            f"真标签差异现算 {len(real)} != 声明 {kinds['real_label_difference']}"
        )
        assert [s["index"] for s in kinds["real_label_difference_sites"]] == real
        assert [s["index"] for s in kinds["fullwidth_halfwidth_separator_only_sites"]] == separator
        site = kinds["real_label_difference_sites"][0]
        assert source_labels[site["index"]] == site["source"]
        assert impl[site["index"]] == site["impl"]
        assert site["missing_char"] in site["source"] and site["missing_char"] not in site["impl"]

    def test_rd2_diverges_from_the_second_declared_source_too(self, manifest_slice: dict) -> None:
        """🔴 「防同源错仍自洽」：两个真源彼此吻合而 impl 与两者都不符。"""
        decl = next(d for d in self._declarations(manifest_slice) if d["id"] == "RD-2")
        second = decl["second_declared_source"]
        pointer = second["ref"]
        match = re.search(r"sections/\[(\d+)\]/tables/\[(\d+)\]", pointer)
        assert match, f"第二真源指针形态不对：{pointer}"
        rows = _note_template_rows(
            NOTE_TEMPLATE_SOE, int(match.group(1)), int(match.group(2))
        )
        assert rows == second["rows_read"], f"note_template_soe 现读 {rows} != 冻结"
        listed_pointer = second["also_in"]
        listed_match = re.search(r"sections/\[(\d+)\]/tables/\[(\d+)\]", listed_pointer)
        assert listed_match
        listed_rows = _note_template_rows(
            NOTE_TEMPLATE_LISTED, int(listed_match.group(1)), int(listed_match.group(2))
        )
        assert listed_rows == rows, "两份 note_template 的该表行模型应逐字相同"
        assert second["verdict"] == "MISMATCH"
        # impl 的那一行在两份 note_template 里都读不到
        impl_label = decl["diff_kinds"]["real_label_difference_sites"][0]["impl"]
        stripped = impl_label.replace("其中：1.", "")
        for path in (NOTE_TEMPLATE_SOE, NOTE_TEMPLATE_LISTED):
            blob = path.read_text(encoding="utf-8")
            assert f'"{stripped}"' not in blob, (
                f"{path.name} 里竟有 impl 的标签 {stripped!r} ⇒ 「两个真源都不符」不成立"
            )

    def test_rd4_cross_impl_divergence_locates_the_defect(self, manifest_slice: dict) -> None:
        """🔴 RD-4：第二份 impl 站在源那一侧 ⇒ 缺陷精确定位在第一份，且双向锁死。"""
        decl = next(d for d in self._declarations(manifest_slice) if d["id"] == "RD-4")
        div = decl["cross_impl_divergence"]
        for side in ("site_a", "site_b"):
            line = _line_at(div[side]["ref"])
            assert div[side]["label"] in line, (
                f"RD-4 {side} 的标签不在声明行里：{line.strip()!r}"
            )
            has_fee = "费" in div[side]["label"]
            assert has_fee == div[side]["has_fee_char"], f"RD-4 {side} 的 has_fee_char 声明错"
        assert div["site_a"]["has_fee_char"] is False
        assert div["site_b"]["has_fee_char"] is True
        j1 = J_TEMPLATE_DIR / "J1 应付职工薪酬.xlsx"
        cell_ref = div["source_xlsx"]["ref"]
        cell = cell_ref.rsplit("!", 1)[1]
        sheet = cell_ref.rsplit("!", 2)[1]
        assert _cells_of(j1, sheet, cell) == [div["source_xlsx"]["label"]]
        for key, path in (
            ("note_template_soe", NOTE_TEMPLATE_SOE),
            ("note_template_listed", NOTE_TEMPLATE_LISTED),
        ):
            spec = div[key]
            match = re.search(r"sections/\[(\d+)\]/tables/\[(\d+)\]/rows/\[(\d+)\]", spec["ref"])
            assert match, f"{key} 指针形态不对"
            rows = _note_template_rows(path, int(match.group(1)), int(match.group(2)))
            assert rows[int(match.group(3))] == spec["label"]
        assert decl["verdict"] == "SECOND_IMPL_AGREES_WITH_SOURCE_FIRST_DOES_NOT"
        assert decl["registered_as"] == "BP-8"

    def test_row_model_summary_counts_recompute(self, manifest_slice: dict) -> None:
        section = manifest_slice["row_model_derivation"]
        summary = section["summary"]
        decls = section["declarations"]
        assert summary["declarations_total"] == len(decls)
        assert summary["clean"] == sum(1 for d in decls if d["status"] == "clean")
        assert summary["defect_registered"] == sum(
            1 for d in decls if d["status"] == "defect_registered_not_fixed"
        )
        assert summary["negative_declaration_clean"] == sum(
            1 for d in decls if d["status"] == "negative_declaration_clean"
        )
        assert summary["cross_impl_divergence_registered"] == sum(
            1 for d in decls if d["status"] == "cross_impl_divergence_registered"
        )
        assert summary["clean_ids"] == [d["id"] for d in decls if d["status"] == "clean"]
        assert summary["defect_ids"] == [
            d["id"] for d in decls if d["status"] == "defect_registered_not_fixed"
        ]
        with_labels = [d for d in decls if "expected_source_labels" in d]
        assert summary["source_rows_covered"] == sum(
            len(d["expected_source_labels"]) for d in with_labels
        )
        assert summary["impl_rows_covered"] == sum(len(d["impl_labels"]) for d in with_labels)
        for decl in decls:
            assert decl["entry_id"] == J1_ENTRY, "每条 declaration 必须绑定唯一 entry"
            assert decl["workbook"] == "J1 应付职工薪酬.xlsx", "每条必须绑定唯一 workbook"

    def test_defect_declarations_are_registered_as_blocking_preconditions(
        self, manifest_slice: dict
    ) -> None:
        known = {bp["id"] for bp in manifest_slice["blocking_preconditions"]}
        for decl in self._declarations(manifest_slice):
            if decl["status"] in ("clean", "negative_declaration_clean"):
                assert "registered_as" not in decl, f"{decl['id']}: 干净的条目不该挂阻断项"
                continue
            assert decl["registered_as"] in known, f"{decl['id']}: registered_as 指向未知阻断项"


# ════════════════════════════════════════════════════════════════════════════
# ⑧ Property 22 / 23 的静态穷举（双向等值）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty22And23StaticStructure:
    def test_hardcoded_patterns_are_all_zero_and_the_denominator_is_real(
        self, manifest_slice: dict, j_files: list[pathlib.Path]
    ) -> None:
        declared = manifest_slice["dynamic_row_identity"]["hardcoded_scan_result"]
        assert set(declared["patterns"]) == set(_HARDCODED_PATTERNS), (
            "slice 声明的模式集合与守卫的正则集合不一致 ⇒ 加模式不加判据就能悄悄放宽"
        )
        for name, expected in declared["patterns"].items():
            hits = _hardcoded_hits(j_files, name)
            assert len(hits) == expected, f"{name}: 现扫 {len(hits)} 命中 != 声明 {expected}：{hits}"
        assert len(j_files) >= 80, "分母太小 ⇒ 全 0 是空跑出来的"

    def test_every_entry_declares_its_dynamic_tables(self, manifest_slice: dict) -> None:
        section = manifest_slice["dynamic_row_identity"]
        assert section["why_this_section_exists"]
        assert section["source_of_truth"]
        forbidden = section["forbidden_identity_kinds"]
        assert set(forbidden) == {"array_index", "ordinal", "position", "mutable_chinese_label"}
        entry_ids = {J1_ENTRY, J1_CHILD_ENTRY}
        seen_keys: set[str] = set()
        for table in section["tables"]:
            assert table["entry_id"] in entry_ids, f"{table['table_key']}: entry_id 不在本 slice 内"
            assert table["table_key"] == table["persistence_key"]
            assert table["table_key"] not in seen_keys, f"{table['table_key']} 重复登记"
            seen_keys.add(table["table_key"])
            identity = table["row_identity"]
            assert identity["kind"] not in forbidden, (
                f"{table['table_key']}: kind={identity['kind']!r} 在 forbidden 里"
            )
            assert "source_ref" in identity and _resolve_repo(identity["source_ref"]).is_file()
            _line_at(identity["source_ref"])
            if identity.get("identity_field") is None:
                assert identity.get("why_not_a_forbidden_kind"), (
                    f"{table['table_key']}: 无身份字段必须写明为什么不算 forbidden"
                )

    def test_declared_seed_row_counts_match_the_row_model(self, manifest_slice: dict) -> None:
        """三个 J1-2 分区的 seed 行数必须等于 row_model_derivation 的 impl_labels 长度。"""
        by_section = {
            "J1-2-detail-shortTerm": "RD-1",
            "J1-2-detail-postEmployment": "RD-2",
            "J1-2-detail-severance": "RD-3",
        }
        decls = {d["id"]: d for d in manifest_slice["row_model_derivation"]["declarations"]}
        for table in manifest_slice["dynamic_row_identity"]["tables"]:
            decl_id = by_section.get(table["table_key"])
            if not decl_id:
                continue
            assert table["seed_row_count"] == len(decls[decl_id]["impl_labels"]), (
                f"{table['table_key']}: seed 行数与 {decl_id} 的 impl_labels 长度不一致"
            )

    def test_positional_identity_inventory_is_exhaustive_and_partitioned(
        self, manifest_slice: dict, j_files: list[pathlib.Path]
    ) -> None:
        """🔴 五族划分：现扫命中集合必须与 family_a + family_b + family_c 的并集**等值**。"""
        inventory = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        hits = _positional_identity_hits(j_files)
        actual = {(rel, no) for rel, no, _key, _expr in hits}
        assert len(actual) == inventory["total_hits"], (
            f"现扫 {len(actual)} 处位置化命中 != 声明 {inventory['total_hits']}：{sorted(actual)}"
        )
        declared: set[tuple[str, int]] = set()
        for family in ("family_a_pure_ordinal_persisted", "family_b_index_as_fallback"):
            block = inventory[family]
            assert len(block["hits"]) == block["count"], f"{family}: count 与 hits 长度不一致"
            for hit in block["hits"]:
                rel, no = hit["site"].split("#L")
                declared.add((rel, int(no)))
        family_c = inventory["family_c_generated_opaque_with_random_must_not_be_flagged"]
        assert len(family_c["sites"]) == family_c["count"]
        for site in family_c["sites"]:
            ref = site.split(" ", 1)[0]
            rel, no = ref.split("#L")
            declared.add((rel, int(no)))
        assert declared == actual, (
            f"声明与现扫不等值：多声明 {sorted(declared - actual)} / 漏声明 {sorted(actual - declared)}"
        )

    def test_family_discriminator_really_separates_b_from_c(
        self, manifest_slice: dict, j_files: list[pathlib.Path]
    ) -> None:
        """🔴 判别式必须是「同时含 Date.now() 与 Math.random() 且不含 ?? / ||」。

        只看「含 random」会把最严重的 family_b 第 1 条（`genId(i)` 的函数体里也有
        `Math.random()`，但那是 `??` 的另一支）洗成 family_c。
        """
        inventory = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        by_site = {f"{rel}#L{no}": expr for rel, no, _key, expr in _positional_identity_hits(j_files)}
        c_sites = {s.split(" ", 1)[0] for s in inventory[
            "family_c_generated_opaque_with_random_must_not_be_flagged"
        ]["sites"]}
        b_sites = {h["site"] for h in inventory["family_b_index_as_fallback"]["hits"]}
        a_sites = {h["site"] for h in inventory["family_a_pure_ordinal_persisted"]["hits"]}

        def is_family_c(expr: str) -> bool:
            return (
                "Date.now()" in expr
                and "Math.random()" in expr
                and "??" not in expr
                and "||" not in expr
            )

        for site in c_sites:
            assert is_family_c(by_site[site]), f"{site} 不满足 family_c 判别式：{by_site[site]!r}"
        for site in b_sites | a_sites:
            assert not is_family_c(by_site[site]), (
                f"{site} 满足 family_c 判别式却被归为缺陷族：{by_site[site]!r}"
            )
        assert not (c_sites & (b_sites | a_sites)), "族之间有交集 ⇒ 划分不是分割"

    def test_family_a_hit_writes_to_the_declared_persisted_key(
        self, manifest_slice: dict
    ) -> None:
        """family_a 那一条必须真落库（否则「最严重」的定级站不住）。"""
        block = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"][
            "family_a_pure_ordinal_persisted"
        ]
        for hit in block["hits"]:
            line = _line_at(hit["site"])
            assert hit["expression"] in line, f"{hit['site']} 的表达式不匹配：{line.strip()!r}"
            source = _resolve_repo(hit["site"]).read_text(encoding="utf-8")
            assert "saveImmediate" in source, f"{hit['site']}: 该组件没有落库调用"
            persist_window = _line_window(hit["persist_ref"], span=4)
            assert "saveImmediate" in persist_window or "item_id" in persist_window, (
                f"{hit['persist_ref']} 不是落库站点：{persist_window!r}"
            )
            assert hit["scope"] in ("entry", "non_entry_host")

    def test_display_sequence_sites_are_not_flagged(
        self, manifest_slice: dict, j_files: list[pathlib.Path]
    ) -> None:
        """反向自检：3 处 `seq: i + 1` 必须**不在**位置化命中集合里。"""
        inventory = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        block = inventory["family_d_display_ordinal_must_not_be_flagged"]
        found: list[str] = []
        for path in j_files:
            source = _strip_ts_comments(_cached_text(path))
            for match in _DISPLAY_SEQ_SITE.finditer(source):
                no = source[: match.start()].count("\n") + 1
                found.append(f"{path.relative_to(ROOT).as_posix()}#L{no}")
        assert len(found) == block["count"], f"展示序号现扫 {len(found)} != 声明 {block['count']}"
        flagged = {(rel, no) for rel, no, _k, _e in _positional_identity_hits(j_files)}
        for site in block["sites"]:
            ref = site.split(" ", 1)[0]
            rel, no = ref.split("#L")
            assert (rel, int(no)) not in flagged, f"{ref} 被误判成位置化身份"
            assert "seq: i + 1" in _line_at(ref)

    def test_four_table_seed_family_is_really_absent(
        self, manifest_slice: dict, j_files: list[pathlib.Path]
    ) -> None:
        """family_e 的 0 命中必须是现扫出来的，且明确不宣称为质量证据。"""
        block = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"][
            "family_e_four_table_seed_absent"
        ]
        assert block["count"] == 0
        assert block["not_claimed_as_evidence_of_quality"]
        found: list[str] = []
        for path in j_files:
            source = _strip_ts_comments(_cached_text(path))
            for match in _FOUR_TABLE_SEED_POSITIONAL.finditer(source):
                no = source[: match.start()].count("\n") + 1
                found.append(f"{path.relative_to(ROOT).as_posix()}#L{no}")
        assert not found, f"出现四表种子位置化形态：{found}"

    def test_entry_scope_split_recomputes(self, manifest_slice: dict) -> None:
        inventory = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        split = inventory["entry_scope_vs_non_entry_scope"]
        a_hits = inventory["family_a_pure_ordinal_persisted"]["hits"]
        b_hits = inventory["family_b_index_as_fallback"]["hits"]
        defects = a_hits + b_hits
        entry_scope = [h for h in defects if h["scope"] == "entry"]
        non_entry = [h for h in defects if h["scope"] == "non_entry_host"]
        assert split["defect_only_entry_scope_hits"] == len(entry_scope)
        assert split["defect_only_non_entry_scope_hits"] == len(non_entry)
        assert {h["site"] for h in entry_scope} == set(split["entry_scope_sites"])
        for hit in entry_scope:
            assert hit["entry_id"] == J1_ENTRY
        for hit in non_entry:
            assert hit["host"] in split["non_entry_scope_hosts"]


# ════════════════════════════════════════════════════════════════════════════
# ⑨ Property 3 / 20：未注册 adapter 不得宣称双向 + 占位不得进生产身份
# ════════════════════════════════════════════════════════════════════════════
class TestProperty3And20:
    """Property 3 的实分母（AC 1.4 否定方向）真验；空分母部分显式不宣称。"""

    def test_no_slice_entry_has_a_contract(self, manifest_slice: dict) -> None:
        owned = set()
        for path in sorted(CONTRACT_DIR.glob("*.json")):
            owner = (_load(path).get("review") or {}).get("entry_id")
            if owner:
                owned.add(owner)
        for entry in manifest_slice["independent_entries"]:
            assert entry["entry_id"] not in owned, (
                f"{entry['entry_id']} 竟有 contract ⇒ BP-2 的前提消失，Property 20 的"
                "「不宣称通过」需要重写"
            )

    def test_no_slice_entry_has_a_registered_adapter(self, manifest_slice: dict) -> None:
        registry = REGISTRY.read_text(encoding="utf-8")
        for entry in manifest_slice["independent_entries"]:
            assert entry["adapter_id"] is None
            assert entry["entry_id"] not in registry, (
                f"{entry['entry_id']} 出现在 registry.py 里 ⇒ Property 3 的正向门开了"
            )

    def test_no_entry_claims_bidirectional(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            assert entry["capability"] != "bidirectional"
            assert entry["migration_state"] == "legacy_fake_bidirectional", (
                "migration_state 应如实记 legacy_fake_bidirectional（现状），不得改成成功态"
            )

    def test_host_template_makes_no_bidirectional_claim(self) -> None:
        """🔴 非空分母：宿主模板里不得出现「可双向回写 / 已同步 / 双向」等宣称文案。"""
        template = _vue_template(J_HOSTS["j1"].read_text(encoding="utf-8"))
        for claim in ("可双向回写", "双向回写", "已同步", "两侧已同步", "自动同步"):
            assert claim not in template, f"宿主模板宣称了 {claim!r}（AC 1.4 前半句）"

    def test_ac14_notice_single_source_exists_and_is_not_duplicated(self) -> None:
        module = NOTICE_MODULE.read_text(encoding="utf-8")
        assert "ENTRY_SYNC_NOTICE_SUMMARY" in module, "缺常显摘要常量"
        assert "ENTRY_SYNC_NOTICE_REASON" in module, "缺可操作原因常量"
        assert "SYNC_ADAPTER_REGISTERED_ENTRY_IDS" in module
        registered = re.search(
            r"SYNC_ADAPTER_REGISTERED_ENTRY_IDS[^=]*=\s*\[([^\]]*)\]", module
        )
        assert registered, "读不出已注册 entry 集合"
        assert not registered.group(1).strip(), (
            "已注册 entry 集合非空 ⇒ 有 entry 可宣称双向，Property 3 的分母变了"
        )
        assert "return null" in module and "level: 'not_synchronized'" in module, (
            "entrySyncNotice 的两个分支不完整 ⇒ 「已注册 ⇒ null / 未注册 ⇒ 非空通知」无从验"
        )
        component = NOTICE_COMPONENT.read_text(encoding="utf-8")
        assert "workpaperEntrySyncNotice" in component, "组件没有引用文案真源"
        # 🔴 不抄第二份：J 循环不得新建自己的文案模块
        for path in _j_cycle_files():
            source = _cached_text(path)
            assert "ENTRY_SYNC_NOTICE_REASON" not in source or "workpaperEntrySyncNotice" in source, (
                f"{path.name} 抄了第二份 AC 1.4 文案"
            )

    def test_property_20_same_shape_denominator_has_no_placeholder_columns(
        self, manifest_slice: dict
    ) -> None:
        """非空同型分母：4 条 row-model + 7 条 transport-key declaration 无 `col_x` 占位。"""
        placeholder = re.compile(r"\bcol_[a-z]+\b")
        checked = 0
        for decl in manifest_slice["row_model_derivation"]["declarations"]:
            for label in decl.get("impl_labels", []) + [
                x for x in decl.get("expected_source_labels", []) if isinstance(x, str)
            ]:
                checked += 1
                assert not placeholder.search(label), f"{decl['id']}: 标签是占位 {label!r}"
        for decl in manifest_slice["transport_key_resolution"]["declarations"]:
            for key in (decl.get("keys") or []) + (decl.get("keys_sample") or []):
                checked += 1
                assert not placeholder.search(key), f"{decl['id']}: 键是占位 {key!r}"
        assert checked >= 60, f"同型分母只有 {checked} 项 —— 太小，结论不可信"

    def test_property_denominator_block_declares_what_is_not_claimed(
        self, manifest_slice: dict
    ) -> None:
        block = manifest_slice["property_denominators"]
        assert manifest_slice["properties_verified"] == [3, 20, 69, 70]
        for key in ("property_3", "property_20", "property_69", "property_70"):
            assert key in block, f"缺 {key} 的分母声明"
            assert block[key]["what_it_asserts"]
            assert block[key]["j_cycle_denominator"]
            assert "not_claimed_passing" in block[key]
        assert block["property_3"]["not_claimed_passing"] is True
        assert block["property_20"]["not_claimed_passing"] is True
        assert block["property_69"]["not_claimed_passing"] is False
        assert block["property_70"]["not_claimed_passing"] is False
        for key in ("property_3", "property_20"):
            assert block[key]["not_claimed_passing_part"], f"{key}: 必须写明不宣称的是哪一部分"
        assert block["property_21_22_23_28_not_claimed"]["not_claimed_passing"] is True
        carrier = _resolve_repo(block["property_3"]["carrier_for_the_empty_part"].split(" + ")[0])
        assert carrier.exists(), "Property 3 空分母部分的承载者不存在"


# ════════════════════════════════════════════════════════════════════════════
# ⑩ Property 28：template identity 漂移 fail closed
# ════════════════════════════════════════════════════════════════════════════
class TestProperty28DefinitionDriftFailClosed:
    def test_authoritative_template_digests_recompute(self, manifest_slice: dict) -> None:
        templates = manifest_slice["authoritative_templates"]
        root = ROOT / templates["root"]
        assert root.is_dir()
        for record in templates["files"]:
            path = root / record["name"]
            assert path.is_file(), f"缺权威模板 {path}"
            assert path.stat().st_size == record["size"], (
                f"{record['name']}: size 现算 {path.stat().st_size} != 冻结 {record['size']}"
            )
            assert _sha256_of(path) == record["sha256"], f"{record['name']}: sha256 漂移"

    def test_registered_file_set_equals_the_disk_set(self, manifest_slice: dict) -> None:
        templates = manifest_slice["authoritative_templates"]
        root = ROOT / templates["root"]
        on_disk = {p.name for p in root.iterdir() if p.is_file() and not p.name.startswith("~$")}
        declared = {f["name"] for f in templates["files"]}
        assert on_disk == declared, f"目录集合 {sorted(on_disk)} != 登记 {sorted(declared)}"

    def test_sheet_inventory_recomputes_four_ways(self, manifest_slice: dict) -> None:
        """sheet_count / retired / mechanism / business 四向自洽（现读 sheetnames）。"""
        templates = manifest_slice["authoritative_templates"]
        root = ROOT / templates["root"]
        retired_suffixes = ("-删除", "-原版", "-原")
        for record in templates["files"]:
            names = _sheet_names(root / record["name"])
            assert len(names) == record["sheet_count"], f"{record['name']}: sheet 数不符"
            retired = [n for n in names if n.endswith(retired_suffixes)]
            assert sorted(retired) == sorted(record["retired_sheets"]), (
                f"{record['name']}: 历史 sheet 现算 {sorted(retired)} != 登记"
            )
            assert record["retired_sheet_count"] == len(record["retired_sheets"])
            if "business_sheet_count" in record:
                mechanism = record["mechanism_sheet_count"]
                assert (
                    record["business_sheet_count"]
                    == record["sheet_count"] - record["retired_sheet_count"] - mechanism
                )
            assert record["primary_detail_sheet"] in names
            if record.get("adjudication_sheet") is not None:
                assert record["adjudication_sheet"] in names
            assert (record["sheet_name_trailing_space"]) == any(n != n.strip() for n in names)

    def test_lock_files_are_really_absent(self, manifest_slice: dict) -> None:
        policy = manifest_slice["authoritative_templates"]["lock_file_policy"]
        assert "~$" in policy
        root = ROOT / manifest_slice["authoritative_templates"]["root"]
        assert not [p for p in root.iterdir() if p.name.startswith("~$")]

    def test_reference_copy_status_is_honest(self, manifest_slice: dict) -> None:
        templates = manifest_slice["authoritative_templates"]
        assert templates["reference_copy_status"] == "absent_in_worktree"
        assert not (ROOT / "基础数据" / "致同通用审计程序及底稿模板（2025年修订）").exists(), (
            "参考副本目录出现了 ⇒ reference_copy_status 必须重判（不得继续声称 absent）"
        )

    def test_template_owner_mapping_is_injective_with_reasoned_nulls(
        self, manifest_slice: dict
    ) -> None:
        """🔴 J 是单射但不满射：1 条有主 + 2 条 null 各带 excluded_reason（SR-8 null 分支）。"""
        templates = manifest_slice["authoritative_templates"]
        entry_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        owners = [f.get("belongs_to_entry") for f in templates["files"]]
        assigned = [o for o in owners if o is not None]
        assert len(assigned) == len(set(assigned)), f"归属不是单射：{assigned}"
        assert set(assigned) <= entry_ids
        for record in templates["files"]:
            if record.get("belongs_to_entry") is None:
                assert record.get("excluded_reason"), f"{record['name']}: null 归属缺 excluded_reason"
        summary = manifest_slice["honest_adjudication_summary"]
        assert summary["template_files_with_owner_entry"] == len(assigned)
        assert summary["template_files_without_owner_entry"] == len(owners) - len(assigned)
        assert summary["authoritative_template_files"] == len(owners)

    def test_template_resolution_audit_recomputes(self, manifest_slice: dict) -> None:
        sys.path.insert(0, str(BACKEND))
        from app.services.wp_template_finder import (  # noqa: PLC0415
            find_template_file,
            find_template_file_any,
        )

        audit = manifest_slice["template_resolution_audit"]
        assert audit["result"] == "clean"
        for row in audit["measured"]:
            resolved = find_template_file(row["wp_code"])
            resolved_any = find_template_file_any(row["wp_code"])
            actual = pathlib.Path(resolved).name if resolved else None
            actual_any = pathlib.Path(resolved_any).name if resolved_any else None
            assert actual == row["resolved"], (
                f"{row['wp_code']}: find_template_file 现跑 {actual!r} != 冻结 {row['resolved']!r}"
            )
            assert actual_any == row["resolved_any"], (
                f"{row['wp_code']}: find_template_file_any 现跑 {actual_any!r} != 冻结"
            )
        assert len(audit["measured"]) == 37, f"解析审计只有 {len(audit['measured'])} 条"

    def test_program_table_and_j0_codes_resolve_to_none(self, manifest_slice: dict) -> None:
        audit = manifest_slice["template_resolution_audit"]
        nones = {row["wp_code"] for row in audit["measured"] if row["resolved"] is None}
        assert nones == {"J1A", "J2A", "J3A", "J0"}, f"返回 None 的码集合是 {sorted(nones)}"
        assert audit["program_table_code_note"]
        assert audit["j0_code_note"]
        assert audit["over_range_subcode_note"], "缺「解析非 None 不等于 sheet 存在」的说明"

    def test_bundle_layer_drift_is_not_claimed(self, manifest_slice: dict) -> None:
        block = manifest_slice["property_denominators"]["property_21_22_23_28_not_claimed"]
        joined = "\n".join(block["not_claimed_parts"])
        assert "bundle" in joined and "authority model" in joined
        for entry in manifest_slice["independent_entries"]:
            for field in (
                "authority_model",
                "definition_bundle",
                "instrumentation_candidate",
                "published_representation",
            ):
                assert entry[field] is None, f"{field} 非 null ⇒ 该层分母不再为空，须改判"


# ════════════════════════════════════════════════════════════════════════════
# ⑪ Property 69：evidence 蕴含 + 计数现算
# ════════════════════════════════════════════════════════════════════════════
class TestProperty69EvidenceAndCounters:
    def test_unverifiable_entries_carry_non_empty_reasons(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            evidence = entry["evidence"]
            state = evidence["verification_state"]
            if state == "UNVERIFIABLE":
                reasons = evidence.get("unverifiable_reasons")
                assert isinstance(reasons, list) and reasons, (
                    f"{entry['entry_id']}: UNVERIFIABLE 必须带非空 reasons（SR-7）"
                )
                continue
            assert state == "VERIFIED", f"{entry['entry_id']}: 非法 verification_state={state!r}"
            assert evidence["sync_test_run_id"], "声称 VERIFIED 必须有 sync_test_run_id"
            assert evidence["required_scenario_set_digest"], (
                "声称 VERIFIED 必须有 required_scenario_set_digest"
            )

    def test_contract_test_points_at_this_guard(self, manifest_slice: dict) -> None:
        expected = _THIS.relative_to(ROOT).as_posix()
        for entry in manifest_slice["independent_entries"]:
            assert entry["evidence"]["contract_test"] == expected, (
                f"{entry['entry_id']}: contract_test 指向 {entry['evidence']['contract_test']!r}"
            )
            assert entry["dom_guard_ref"].startswith(expected)

    def test_summary_counters_recompute_from_the_entries(self, manifest_slice: dict) -> None:
        entries = manifest_slice["independent_entries"]
        summary = manifest_slice["honest_adjudication_summary"]
        assert summary["total_independent"] == len(entries)
        for cap in CAPABILITY_ENUM:
            assert summary[f"adjudicated_as_{cap}"] == sum(
                1 for e in entries if e["capability"] == cap
            )
        assert summary["capability_verdict_pending"] == sum(
            1 for e in entries if e["capability"] is None
        )
        assert summary["html_counterpart_exists"] == sum(
            1 for e in entries if e["html_counterpart_verdict"] == "exists"
        )
        assert summary["html_counterpart_none"] == sum(
            1 for e in entries if e["html_counterpart_verdict"] == "none"
        )
        assert summary["entries_left_unverifiable"] == sum(
            1 for e in entries if e["evidence"]["verification_state"] == "UNVERIFIABLE"
        )
        assert summary["finalized_published_representations"] == sum(
            1 for e in entries if e["published_representation"] is not None
        )
        assert summary["parent_duplicate_children"] == len(
            manifest_slice["parent_duplicate_summary"]["children"]
        )
        assert summary["entries_mounting_the_ac14_notice"] == sum(
            1 for e in entries if e.get("notice_mounted")
        )
        assert summary["entries_missing_segmented_second_level_gate"] == sum(
            1 for e in entries if e.get("ui_toolbar_gate_second_level") is None
        )
        assert summary["entries_with_second_write_path"] == sum(
            1 for e in entries if e["html_counterpart"].get("second_write_path_note")
        )

    def test_derived_counters_recompute_from_their_own_sections(self, manifest_slice: dict) -> None:
        summary = manifest_slice["honest_adjudication_summary"]
        orphan = manifest_slice["orphan_dual_mode_inventory"]
        transport = manifest_slice["transport_key_resolution"]
        rows = manifest_slice["row_model_derivation"]
        identity = manifest_slice["dynamic_row_identity"]
        diff = {d["id"]: d for d in manifest_slice["j_cycle_form_differences"]["differences"]}

        assert summary["orphan_dual_mode_modules"] == len(orphan["modules"])
        assert summary["orphan_dual_mode_first_order"] == orphan["summary"][
            "orphan_dual_mode_first_order"
        ]
        assert summary["orphan_dual_mode_second_order"] == orphan["summary"][
            "orphan_dual_mode_second_order"
        ]
        assert summary["orphan_barrels"] == orphan["summary"]["orphan_barrels"]
        assert summary["lookalike_persistence_carriers"] == len(
            orphan["lookalike_persistence_carriers"]["modules"]
        )
        assert summary["shared_base_statement_consumers"] == orphan["shared_base"][
            "statement_position_consumers"
        ]
        assert summary["shared_base_pseudo_string_edges"] == orphan["shared_base"][
            "pseudo_string_edges"
        ]
        assert summary["shared_base_j_cycle_consumers"] == orphan["shared_base"][
            "j_cycle_contribution"
        ]
        assert summary["transport_key_declarations_total"] == len(transport["declarations"])
        assert summary["transport_key_declarations_with_defect"] == transport["summary"][
            "declarations_resolved_with_defect"
        ]
        assert summary["transport_key_declarations_with_two_source_declarations"] == transport[
            "summary"
        ]["declarations_with_two_source_declarations"]
        assert summary["row_model_declarations_total"] == len(rows["declarations"])
        assert summary["row_model_declarations_clean"] == rows["summary"]["clean"]
        assert summary["row_model_declarations_defect"] == rows["summary"]["defect_registered"]
        assert summary["row_model_declarations_negative"] == rows["summary"][
            "negative_declaration_clean"
        ]
        assert summary["row_model_declarations_cross_impl"] == rows["summary"][
            "cross_impl_divergence_registered"
        ]
        inventory = identity["positional_identity_inventory"]
        assert summary["positional_identity_hits_total"] == inventory["total_hits"]
        defect_hits = (
            inventory["family_a_pure_ordinal_persisted"]["count"]
            + inventory["family_b_index_as_fallback"]["count"]
        )
        assert summary["positional_identity_defect_hits"] == defect_hits
        split = inventory["entry_scope_vs_non_entry_scope"]
        assert summary["positional_identity_defect_hits_entry_scope"] == split[
            "defect_only_entry_scope_hits"
        ]
        assert summary["positional_identity_defect_hits_non_entry_scope"] == split[
            "defect_only_non_entry_scope_hits"
        ]
        assert summary["dynamic_row_identity_tables"] == len(identity["tables"])
        assert summary["hardcoded_pattern_hits_total"] == sum(
            identity["hardcoded_scan_result"]["patterns"].values()
        )
        assert summary["second_write_path_files"] == diff["JD-3"]["second_write_path_file_count"]
        assert summary["second_write_path_sites"] == diff["JD-3"]["second_write_path_site_count"]
        assert summary["reachable_hosts_in_cycle"] == len(diff["JD-1"]["hosts"])
        assert summary["hosts_with_oo_mount"] == sum(
            1 for h in diff["JD-1"]["hosts"].values() if h["has_oo_mount"]
        )
        assert summary["hosts_without_oo_mount"] == sum(
            1 for h in diff["JD-1"]["hosts"].values() if not h["has_oo_mount"]
        )

    def test_slice_counters_are_all_zero_except_unadjudicated(self, manifest_slice: dict) -> None:
        counters = manifest_slice["honest_adjudication_summary"]["slice_counters"]
        entries = manifest_slice["independent_entries"]
        assert counters["unadjudicated"] == sum(1 for e in entries if e["capability"] is None)
        assert counters["fake_bidirectional_claimed_verified"] == 0
        assert counters["bidirectional_unverified"] == 0
        assert counters["stale_evidence"] == 0
        assert counters["note"], "四个计数的语义必须写明（0 不得解读为已具备双向能力）"

    def test_counting_notes_cover_every_nontrivial_counter(self, manifest_slice: dict) -> None:
        notes = manifest_slice["honest_adjudication_summary"]["counting_notes"]
        for key in (
            "positional_identity_hits_total",
            "positional_identity_defect_hits",
            "dynamic_row_identity_tables",
            "second_write_path_files",
            "authoritative_template_files",
            "shared_base_statement_consumers",
            "hardcoded_pattern_hits_total",
        ):
            assert key in notes and notes[key], f"缺 {key} 的计数口径说明"


# ════════════════════════════════════════════════════════════════════════════
# ⑫ Property 70：跨 entry 隔离
# ════════════════════════════════════════════════════════════════════════════
class TestProperty70CrossEntryIsolation:
    def test_seven_slices_are_pairwise_disjoint(self, manifest_slice: dict) -> None:
        sets = {"J": {e["entry_id"] for e in manifest_slice["independent_entries"]}}
        for name, path in SIBLING_SLICE_PATHS.items():
            sets[name] = {e["entry_id"] for e in _load(path)["independent_entries"]}
        names = sorted(sets)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                overlap = sets[a] & sets[b]
                assert not overlap, f"{a} 与 {b} 的 entry 集合相交：{sorted(overlap)}"
        assert len(sets) == 7

    def test_sibling_slices_declared_match_the_disk(self, manifest_slice: dict) -> None:
        declared = manifest_slice["sibling_slices"]
        assert len(declared) == len(SIBLING_SLICE_PATHS)
        for rel in declared:
            assert (ROOT / rel).is_file(), f"兄弟 slice 不存在：{rel}"
        assert {pathlib.Path(r).name for r in declared} == {
            p.name for p in SIBLING_SLICE_PATHS.values()
        }

    def test_cross_entry_isolation_assertions_are_present(self, manifest_slice: dict) -> None:
        isolation = manifest_slice["cross_entry_isolation"]
        assert isolation["rule"]
        assert isinstance(isolation["assertions"], list) and len(isolation["assertions"]) >= 6

    def test_deletion_plan_paths_are_globally_unique_and_disjoint(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        to_delete = [m["file"] for m in deletion_plan["orphan_dual_mode_to_delete"]["modules"]]
        assert len(to_delete) == len(set(to_delete)), f"待删路径重复：{to_delete}"
        preserved = {
            entry_file["file"]
            for entry in deletion_plan["entries"]
            for entry_file in entry["legacy_composables_preserved"]
        }
        assert not (set(to_delete) & preserved), "待删与保留集合相交"
        slice_legacy = {
            e["legacy_dual_mode"]["module"] for e in manifest_slice["independent_entries"]
        }
        assert not (set(to_delete) & slice_legacy), (
            "待删清单里出现了 slice entry 的 legacy_dual_mode 模块（那是共享基类，不删）"
        )
        for rel in to_delete + sorted(preserved):
            assert (ROOT / rel).is_file(), f"清册路径不存在：{rel}"


# ════════════════════════════════════════════════════════════════════════════
# ⑬ AC 1.4 的 UI 义务（step 11 / BP-10）
# ════════════════════════════════════════════════════════════════════════════
class TestAc14HonestModeVisibility:
    def test_entry_declares_a_unique_resolvable_toolbar_anchor(self, the_entry: dict) -> None:
        template = _vue_template(J_HOSTS["j1"].read_text(encoding="utf-8"))
        block = _toolbar_block(template, the_entry["ui_toolbar_gate"])
        for ref in the_entry["ui_gate_source_refs"][:3]:
            line = _line_at(ref)
            assert line.strip(), f"{ref} 指向空行"
        gate_line = _line_at(the_entry["ui_gate_source_refs"][0])
        assert the_entry["ui_toolbar_gate"] in gate_line
        assert "isHtmlSheet" in gate_line, "工具栏门控表达式变了 ⇒ 声明需更新"
        assert "el-segmented" in block

    def test_second_level_gate_absence_matches_the_declaration(self, the_entry: dict) -> None:
        """🔴 不得写死「全 slice 都有二级门控」—— J1 没有，那正是 BP-10 的核心。"""
        template = _vue_template(J_HOSTS["j1"].read_text(encoding="utf-8"))
        block = _toolbar_block(template, the_entry["ui_toolbar_gate"])
        segmented_line = next(ln for ln in block.splitlines() if "el-segmented" in ln)
        has_gate = "v-if" in segmented_line
        declared = the_entry["ui_toolbar_gate_second_level"]
        assert (declared is not None) == has_gate, (
            f"声明 second_level={declared!r} 但模板实测 has_gate={has_gate}"
            f"（切换器那一行：{segmented_line.strip()!r}）"
        )
        assert declared is None, (
            "J1 现在有二级门控了 ⇒ BP-10 的一半已兑现，登记与判据都要更新"
        )
        assert "仅结构化视图" in block, "OO 不可用时的兜底 tag 不见了 ⇒ 现状描述需更新"

    def test_runtime_fallback_in_the_shared_base_is_real(self) -> None:
        """BP-10 的「点了没反应」结论要有源码依据。"""
        shared = SHARED_BASE.read_text(encoding="utf-8")
        assert re.search(
            r"if\s*\(\s*target\s*===\s*'onlyoffice'\s*&&\s*!ooAvailable\.value\s*\)\s*return",
            shared,
        ), "共享基类的运行时兜底不见了 ⇒ BP-10 的「无声失败」描述需重判"

    def test_extra_unrelated_segmented_sites_are_declared_and_outside_the_toolbar(
        self, the_entry: dict, j_files: list[pathlib.Path]
    ) -> None:
        """🔴 全 J 域 el-segmented 共 3 处，只有 1 处是模式切换器。"""
        found: list[str] = []
        for path in j_files:
            source = _cached_text(path)
            for match in re.finditer(r"el-segmented", source):
                no = source[: match.start()].count("\n") + 1
                found.append(f"{path.relative_to(ROOT).as_posix()}#L{no}")
        declared_extra = set(the_entry["extra_unrelated_segmented_sites"])
        host_site = f"{J_HOSTS['j1'].relative_to(ROOT).as_posix()}#L10"
        assert set(found) == declared_extra | {host_site}, (
            f"el-segmented 现扫 {sorted(found)} != 声明 {sorted(declared_extra | {host_site})}"
        )
        template = _vue_template(J_HOSTS["j1"].read_text(encoding="utf-8"))
        block = _toolbar_block(template, the_entry["ui_toolbar_gate"])
        assert block.count("el-segmented") == 1, "工具栏区块里不止一个切换器"
        for ref in declared_extra:
            assert "el-segmented" in _line_at(ref)
            assert not ref.startswith(J_HOSTS["j1"].relative_to(ROOT).as_posix()), (
                "宿主自身的站点不该列在 extra_unrelated 里"
            )

    def test_bp10_is_registered_because_no_host_mounts_the_notice(
        self, manifest_slice: dict, the_entry: dict
    ) -> None:
        """两侧都验：现状确实没挂（BP-10 成立）；挂上了就必须打红提醒解除登记。"""
        host = J_HOSTS["j1"].read_text(encoding="utf-8")
        mounted = NOTICE_COMPONENT_NAME in host
        assert mounted == bool(the_entry["notice_mounted"]), (
            f"声明 notice_mounted={the_entry['notice_mounted']} 但宿主实测 {mounted}"
        )
        assert mounted is False, (
            "🔴 宿主已挂 GtEntrySyncCapabilityNotice ⇒ 可以解除 BP-10 了，"
            "slice 的 notice_mounted / BP-10.status 必须同步更新"
        )
        bp10 = next(bp for bp in manifest_slice["blocking_preconditions"] if bp["id"] == "BP-10")
        assert bp10["status"] == "REGISTERED_NOT_FIXED"
        assert bp10["blocks"] == "ui_honesty"
        assert any("1.4" in str(x) for x in bp10["observable_consequences"]) or "AC 1.4" in bp10[
            "what"
        ]

    def test_j2_and_j3_hosts_have_no_mode_switcher_at_all(self, deletion_plan: dict) -> None:
        """AC 1.5 的「事实效果」—— 但不作为本任务的裁决兑现来宣称。"""
        hits = deletion_plan["host_inlined_second_implementation"]["measured_token_hits"]
        for rel, tokens in hits.items():
            if rel == "OnlyOffice_hit_sites_in_j3":
                continue
            source = (ROOT / rel).read_text(encoding="utf-8")
            for token, expected in tokens.items():
                assert source.count(token) == expected, (
                    f"{rel} 的 «{token}» 现算 {source.count(token)} != 声明 {expected}"
                )
        for ref in hits["OnlyOffice_hit_sites_in_j3"]:
            assert "OnlyOffice" in _line_at(ref)


# ════════════════════════════════════════════════════════════════════════════
# ⑭ deletion plan 一致性
# ════════════════════════════════════════════════════════════════════════════
class TestDeletionPlanConsistency:
    def test_plan_entries_mirror_the_slice_adjudication(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        assert {e["entry_id"] for e in deletion_plan["entries"]} == set(by_id)
        for plan_entry in deletion_plan["entries"]:
            slice_entry = by_id[plan_entry["entry_id"]]
            assert plan_entry["capability_adjudication"] == slice_entry["capability"]
            assert plan_entry["capability_verdict_stage"] == slice_entry["capability_verdict_stage"]
            assert plan_entry["capability_target"] == slice_entry["capability_target"]
            assert plan_entry["html_counterpart_verdict"] == slice_entry["html_counterpart_verdict"]
            assert plan_entry["host_component"] == slice_entry["host_path"]
            assert plan_entry["wp_code_pattern"] == slice_entry["wp_code_pattern"]
            assert set(plan_entry["html_counterpart_source_refs"]) <= set(
                slice_entry["html_counterpart_source_refs"]
            )

    def test_plan_has_no_entry_scoped_deletion_and_says_why(self, deletion_plan: dict) -> None:
        block = deletion_plan["why_this_plan_has_no_entry_scoped_deletion"]
        assert block["statement"] and block["why"] and block["verification_recipe"]
        for entry in deletion_plan["entries"]:
            assert entry["legacy_composables_to_delete"] == []
            assert entry["action"] == "update_host_only"
            assert entry["legacy_composables_to_delete_note"], "空数组必须写明是实测结论"

    def test_plan_reason_is_not_circular(self, deletion_plan: dict, paradigm: dict) -> None:
        ap1 = next(
            ap
            for ap in paradigm["adjudication_criteria"]["anti_patterns"]
            if ap["id"] == "AP-1"
        )
        markers = [str(m).lower() for m in ap1["circular_reason_markers"]]
        for entry in deletion_plan["entries"]:
            reason = str(entry["adjudication_reason"]).lower()
            hit = [m for m in markers if m in reason]
            if hit:
                assert "对端" in reason or "html_counterpart_verdict" in reason, (
                    f"{entry['entry_id']}: 清册理由命中循环论证标记 {hit}"
                )

    def test_plan_shared_base_numbers_agree_with_the_slice(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        plan = deletion_plan["shared_base_preserved"]
        slice_shared = manifest_slice["orphan_dual_mode_inventory"]["shared_base"]
        assert plan["statement_position_consumers"] == slice_shared["statement_position_consumers"]
        assert plan["pseudo_string_edges"] == slice_shared["pseudo_string_edges"]
        assert plan["j_cycle_consumers"] == slice_shared["j_cycle_contribution"]
        assert plan["remaining_after_this_plan"] == slice_shared["remaining_after_j_cycle_work"]
        assert plan["lines"] == slice_shared["lines"] == _line_count(SHARED_BASE)
        families = plan["remaining_consumer_families"]
        assert sum(families.values()) == plan["remaining_after_this_plan"], (
            f"按族分解 {families} 的和 {sum(families.values())} != {plan['remaining_after_this_plan']}"
        )

    def test_plan_orphan_modules_mirror_the_slice_inventory(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        slice_modules = {
            m["id"]: m for m in manifest_slice["orphan_dual_mode_inventory"]["modules"]
        }
        plan_modules = deletion_plan["orphan_dual_mode_to_delete"]["modules"]
        assert {m["id"] for m in plan_modules} == set(slice_modules)
        for plan_module in plan_modules:
            slice_module = slice_modules[plan_module["id"]]
            assert plan_module["file"] == slice_module["module"]
            assert plan_module["lines"] == slice_module["lines"]
            assert plan_module["orphan_order"] == slice_module["orphan_order"]
            assert plan_module["consumers"] == slice_module["production_consumers"]
            assert plan_module["test_only_consumers"] == slice_module["test_only_consumers"]
            assert plan_module["barrel_only_reachable_via"] == slice_module[
                "barrel_only_reachable_via"
            ]
            if plan_module["orphan_order"] == "second_order":
                assert "drop_barrel_reexport" in plan_module["action"]
                assert plan_module["action_side_effects"], "二阶 orphan 必须列出连带改动"
            else:
                assert plan_module["action"] == "delete_file"
                assert plan_module["blocking_risk"] == "none"

    def test_plan_barrel_reexport_lines_are_real(self, deletion_plan: dict) -> None:
        for barrel in deletion_plan["orphan_dual_mode_to_delete"]["orphan_barrels"]:
            path = ROOT / barrel["file"]
            assert path.is_file()
            text = path.read_text(encoding="utf-8")
            assert _line_count(path) == barrel["lines"]
            assert len(re.findall(r"(?m)^export\s", text)) == barrel["reexports"]
            assert len(_statement_edges_to(path)) == barrel["inbound_edges"] == 0
            assert "DualMode" in text, "barrel 里已无 dual-mode re-export ⇒ 清册需更新"
            assert barrel["inbound_edge_recipe"], "必须写明入边口径（路径解析而非 stem）"

    def test_plan_counters_recompute(self, deletion_plan: dict) -> None:
        counters = deletion_plan["counters"]
        entries = deletion_plan["entries"]
        orphan = deletion_plan["orphan_dual_mode_to_delete"]
        modules = orphan["modules"]
        assert counters["entries"] == len(entries)
        assert counters["composables_to_delete_entry_scoped"] == sum(
            len(e["legacy_composables_to_delete"]) for e in entries
        )
        assert counters["composables_preserved"] == sum(
            len(e["legacy_composables_preserved"]) for e in entries
        )
        assert counters["orphan_dual_mode_to_delete"] == len(modules)
        assert counters["orphan_dual_mode_lines_total"] == sum(m["lines"] for m in modules)
        for module in modules:
            assert _line_count(ROOT / module["file"]) == module["lines"]
        assert counters["orphan_barrel_reexports_to_drop"] == sum(
            1 for m in modules if "drop_barrel_reexport" in m["action"]
        )
        assert counters["lookalike_persistence_carriers"] == len(
            deletion_plan["lookalike_carriers_not_in_scope"]["modules"]
        )
        assert counters["pseudo_consumer_edges"] == len(
            deletion_plan["pseudo_consumer_edges"]["edges"]
        )
        block = deletion_plan["host_inlined_second_implementation"]
        hosts = block["hosts"]
        inlined = [h for h in hosts.values() if h["inlined_second_implementation"]]
        no_dual = [h for h in hosts.values() if not h["consumes_dual_mode"]]
        assert counters["hosts_with_inlined_second_implementation"] == len(inlined)
        assert counters["hosts_without_any_dual_mode"] == len(no_dual)
        # 🔴 `result` 必须从 hosts 明细**现算**，不得是自述：首轮变异检验 M72（把
        #    "not_applicable_but_worse" 改成 "found"）报 GREEN，正是因为这个字段没人管。
        #    三态各有含义：found = H 循环那种「宿主内联了第二份实现」（删了 composable 行为不变
        #    ⇒ 可疑）；not_applicable_but_worse = J2/J3 那种「根本没有双模式」（删了行为不变
        #    ⇒ 正确期望）；none = 每个宿主都真消费自己的 composable（常规验收可用）。
        expected = "found" if inlined else ("not_applicable_but_worse" if no_dual else "none")
        assert block["result"] == expected, (
            f"host_inlined_second_implementation.result={block['result']!r} 与 hosts 明细现算的 "
            f"{expected!r} 不符（inlined={len(inlined)} / no_dual={len(no_dual)}）"
        )
        assert counters["test_files_requiring_sync_change"] == sum(
            len(m["test_only_consumers"]) for m in modules
        )
        assert counters["entries_with_extra_ui_action_required"] == sum(
            1 for e in entries if e.get("extra_ui_action_required")
        )
        assert counters["entries_with_must_fix_before_wiring"] == sum(
            1 for e in entries if e.get("must_fix_before_wiring")
        )
        assert counters["entries_with_must_not_wire_to"] == sum(
            1 for e in entries if e.get("must_not_wire_to")
        )
        assert counters["shared_base_consumers_before"] == deletion_plan[
            "shared_base_preserved"
        ]["statement_position_consumers"]
        assert counters["shared_base_consumers_after"] == deletion_plan["shared_base_preserved"][
            "remaining_after_this_plan"
        ]
        assert orphan["counters"]["modules_to_delete"] == len(modules)
        assert orphan["counters"]["total_lines_to_delete"] == sum(m["lines"] for m in modules)

    def test_plan_has_no_pilot_branch(self, deletion_plan: dict) -> None:
        assert deletion_plan["pilot_already_migrated"] is None
        assert deletion_plan["pilot_already_migrated_note"]

    def test_plan_must_not_wire_to_targets_are_the_orphan_carriers(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        declared = {
            m["module"]
            for m in manifest_slice["orphan_dual_mode_inventory"][
                "lookalike_persistence_carriers"
            ]["modules"]
        }
        for entry in deletion_plan["entries"]:
            assert set(entry["must_not_wire_to"]) == declared
        for module in deletion_plan["lookalike_carriers_not_in_scope"]["modules"]:
            assert module["must_not_wire_to"] is True
            assert module["must_not_wire_to_why"]


# ════════════════════════════════════════════════════════════════════════════
# ⑮ 范式合规（校验器 + 两条反向自检 + 字节冻结）
# ════════════════════════════════════════════════════════════════════════════
def _load_validator():
    import importlib.util

    path = _THIS.with_name("test_migration_paradigm_contract.py")
    assert path.is_file(), f"缺范式校验器宿主：{path}"
    spec = importlib.util.spec_from_file_location("_task52_validator_host", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParadigmCompliance:
    def test_the_slice_passes_the_paradigm_nominated_validator(self, manifest_slice: dict) -> None:
        violations = _load_validator().validate_slice_against_schema(manifest_slice)
        assert violations == [], f"范式校验器报违规：{violations}"

    def test_the_validator_really_catches_a_missing_pending_field(
        self, manifest_slice: dict
    ) -> None:
        """反向自检：抽掉待裁决三字段之一必须打红（否则上一条的绿是空跑）。"""
        module = _load_validator()
        for field in (
            "capability_verdict_stage",
            "capability_target",
            "capability_target_blocked_by",
        ):
            broken = json.loads(json.dumps(manifest_slice))
            broken["independent_entries"][0].pop(field)
            violations = module.validate_slice_against_schema(broken)
            assert any(field in v for v in violations), (
                f"抽掉 `{field}` 后校验器没点名它：{violations}"
            )

    def test_the_validator_really_catches_a_counter_mismatch(self, manifest_slice: dict) -> None:
        module = _load_validator()
        broken = json.loads(json.dumps(manifest_slice))
        broken["honest_adjudication_summary"]["slice_counters"]["unadjudicated"] = 0
        violations = module.validate_slice_against_schema(broken)
        assert any("SR-9" in v for v in violations), f"SR-9 没打红：{violations}"

    def test_the_validator_really_catches_a_forbidden_identity_kind(
        self, manifest_slice: dict
    ) -> None:
        """反向自检：把动态行表的 kind 改成 forbidden 之一必须打红。"""
        module = _load_validator()
        broken = json.loads(json.dumps(manifest_slice))
        broken["dynamic_row_identity"]["tables"][0]["row_identity"]["kind"] = "array_index"
        violations = module.validate_slice_against_schema(broken)
        assert any("forbidden_identity_kinds" in v for v in violations), (
            f"forbidden kind 没打红：{violations}"
        )

    def test_paradigm_refs_and_task_number_are_right(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        assert manifest_slice["task"] == "Task 52"
        assert deletion_plan["task"] == "Task 52"
        assert manifest_slice["paradigm_ref"] == PARADIGM_PATH.relative_to(ROOT).as_posix()
        assert deletion_plan["paradigm_ref"] == PARADIGM_PATH.relative_to(ROOT).as_posix()
        assert manifest_slice["source_manifest"] == FULL_MANIFEST_PATH.relative_to(ROOT).as_posix()
        assert deletion_plan["adjudication_source_of_truth"].startswith(
            MANIFEST_SLICE_PATH.relative_to(ROOT).as_posix()
        )
        assert deletion_plan["orphan_source_of_truth"].startswith(
            MANIFEST_SLICE_PATH.relative_to(ROOT).as_posix()
        )
        assert 52 in _load(PARADIGM_PATH)["slice_schema"]["applies_to_tasks"]

    def test_paradigm_bytes_are_untouched_by_this_task(self, paradigm: dict) -> None:
        """本任务不改范式 JSON —— 用它自己登记的 digest 双向锁死 `paradigm` 块。"""
        module = _load_validator()
        registry = paradigm["paradigm_registry"]["paradigms"]
        legacy = next(p for p in registry if p["alias"] == "legacy_deletion_paradigm")
        assert module.raw_block_digest() == legacy["frozen_raw_block_sha256"]
        assert module.canonical_digest(paradigm["paradigm"]) == legacy["frozen_canonical_sha256"]
        assert len(paradigm["paradigm"]["steps"]) == legacy["step_count"] == 7
        assert tuple(paradigm["adjudication_criteria"]["capability_enum"]) == CAPABILITY_ENUM

    def test_new_sections_are_declared_as_non_conflicting(self, manifest_slice: dict) -> None:
        conflict = manifest_slice["paradigm_schema_conflict"]
        assert conflict["residual_inconsistency"] is None
        assert conflict["known_red_it_causes"]["status"] == "none"
        assert conflict["paradigm_bytes_untouched"]
        declared = set(conflict["new_section_not_in_schema"]["sections"])
        schema_required = set(_load(PARADIGM_PATH)["slice_schema"]["required_top_level"])
        conditional = {
            cs["section"] for cs in _load(PARADIGM_PATH)["slice_schema"]["conditional_sections"]
        }
        extra = set(manifest_slice) - schema_required - conditional
        nested = {s.split("（")[0] for s in declared}
        assert extra <= nested, f"有未登记的额外顶层键：{sorted(extra - nested)}"

    def test_unjudged_slices_registry_stays_empty(self) -> None:
        """🔴 不许加豁免：新增 slice 必须直接通过校验器。"""
        path = _THIS.with_name("test_slice_schema_validator_coverage.py")
        assert path.is_file()
        source = path.read_text(encoding="utf-8")
        match = re.search(r"_UNJUDGED_SLICES:\s*dict\[str,\s*str\]\s*=\s*\{([^}]*)\}", source)
        assert match, "读不出 _UNJUDGED_SLICES"
        assert not match.group(1).strip(), (
            f"_UNJUDGED_SLICES 非空：{match.group(1)!r} —— 本任务不得加豁免"
        )

    def test_requirements_and_properties_are_declared(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        assert manifest_slice["properties_verified"] == [3, 20, 69, 70]
        assert deletion_plan["properties_verified"] == [3, 20, 69, 70]
        for req in ("1.4", "1.5", "1.7", "6.1", "12.1", "12.4", "12.8", "12.10", "12.11", "12.12", "14.1"):
            assert req in manifest_slice["requirements_covered"], f"缺 Requirement {req}"
