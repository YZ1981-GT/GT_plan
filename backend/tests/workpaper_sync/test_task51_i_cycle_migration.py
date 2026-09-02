# -*- coding: utf-8 -*-
r"""test_task51_i_cycle_migration — I 循环 Excel 独立 entry 迁移验证

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 51
Requirements: 6.1, 6.2, 6.10, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1
             （另覆盖 1.4 / 1.7 / 12.8 / 12.9）

验证 Properties:
  - Property 20: generated col 占位不可注册生产 adapter —— **contract 维度分母为空 ⇒ 不宣称通过**；
    只断言前提（本 slice contract 数 = 0，逐文件读 review.entry_id）+ 承载者存在，
    并在**非空的同型分母**（8 条 classification declaration 的 key/label 分离）上真验。
  - Property 28: immutable definition 漂移 fail closed —— 真分母：6 个模板 digest 现算 +
    目录集合等值 + 31 条 wp_code 解析（含 `I{n}A` / `I0` 断言 None 两组否定式）。
    bundle / instrumentation / contract / authority model 四层分母为空 ⇒ 不宣称通过。
  - Property 69: evidence 由逐 scenario 实体与服务端重算闭合 —— 负向分母真验
    （UNVERIFIABLE ⇒ 非空 reasons；VERIFIED ⇒ 有 run id + digest）+ 22 项计数现算等值；
    正向逐 scenario 闭合不宣称通过（BP-4）。
  - Property 70: scenario/evidence/contract/bundle 不得跨 entry 复用 —— 六 slice 互斥 +
    模板 belongs_to_entry **双射** + 契约归属逐文件读 + declaration 单 entry 绑定 + 清册去重。
  另在真分母上顺带验 Property 22（静态结构：label-as-key 全 slice 0 命中）与
  Property 23（静态前提：6 个身份生成器 + 6 条位置化命中三族划分 + 20 处展示序号反向自检 +
  四表种子 0 命中）。Property 21 分母为空 ⇒ 不宣称通过。

╔═══ 本文件的核心判据：source_ref 三边锁（Task 51 正文第一条）═══╗

tasks.md 的 Task 51 正文写的是「分类/行模型由源 xlsx 真源派生，source_ref 守卫**含源标签**，
防同源错仍自洽」。前五个循环的守卫只验「source_ref 指向的 sheet/cell 存在」—— 那留了一个洞：
**声明的 cell 与实现的常量同时错成一致时判据仍自洽**。本文件把判据补成三边：

  ① 声明：slice 的 `classification_row_model_derivation.declarations[].declared_source_ref`
  ② 源真读：openpyxl 打开权威模板、真读那段 cells，得到字面标签序列
  ③ 实现：按 `impl_extraction_kind` 从 impl_module 抽出常量里的标签序列

守卫断言 ②==③（有序，不是集合）**且** ②== slice 冻结的 `expected_source_labels`
**且** `verdict` == 实际比对结果。三边任一被单独改动都会打红：
  - 改了模板 → ② 变，与 ① 冻结值不符 ⇒ 红
  - 改了 impl 常量 → ③ 变，与 ② 不符 ⇒ 红
  - 同时改声明与 impl（同源错）→ ② 不变，仍与 ③ 不符 ⇒ 红  ← 这是新增的那条边

╔═══ 判据设计（沿用前五轮已定论，不重新发明）═══╗

1. **不用空分母重言式**。每条 Property 显式区分「有真分母的部分（真验）」与
   「无适用分母的部分（只断言前提成立 + 承载者存在，**不宣称通过**）」。

2. **不用 fail-open**。没有 `pytest.skip`、没有 `if x: assert ...`（缺值即跳过）、
   没有 `except Exception` 吞异常。缺文件/缺字段一律打红。

3. **不用硬编码豁免**。本 slice 没有 pilot，也不给任何 entry 开例外列。

4. **不假设与 D/F/G/H 同形**。I 循环实测出五处不同（slice 的 `i_cycle_form_differences`）：
   * 写载体 5:1 偏斜（5 条宿主内联 / 只有 I5 走 FormData composable，且该宿主无 client import）；
   * **没有一条 entry 的宿主直接 GET /checklist-responses**（全走 render-config），
     照抄 H 的「载体里必须有 checklist GET」会对 6 条全假红；
   * I6 的主表键与身份字段双双例外（`I6-2-detail-rows` / `id`，另有 legacy 键读兼容）；
   * **I2 的工具栏没有 el-segmented 二级门控**（其余 5 条有）—— 写死「全 slice 都有」
     会让判据在 I2 上静默恒真，恰好漏掉最严重的一条；
   * 两个 FormData composable 生产零消费（useI4FormData / useI6FormData）。

5. **判归属一律用 import 路径字面量，不用符号名 grep**。I 循环有 4 处
   `* - Follow useI{n}DualMode pattern` 注释会被符号名口径报成 composable→composable 的
   消费边（见 TestOrphanComposablesAndPseudoConsumers 的两侧断言）。

依赖（缺任一即 fail closed）：
  - backend/data/workpaper_sync_i_cycle_manifest_slice.json（frozen slice）
  - backend/data/workpaper_sync_i_cycle_deletion_plan.json（deletion plan）
  - backend/data/workpaper_sync_migration_paradigm.json（Task 45 范式，只读）
  - backend/data/workpaper_sync_entry_manifest.json（source-backed manifest，只读）
  - backend/data/note_template_soe.json / note_template_listed.json（BP-7/BP-8 的第二真源，只读）
  - backend/wp_templates/I/ 与 backend/wp_templates/_index.json（运行时权威，唯一真源）
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any, Callable

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
COMPOSABLES = WP_COMPONENTS / "composables"
SYNC_DIR = WP_COMPONENTS / "sync"
DATA = BACKEND / "data"

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_i_cycle_manifest_slice.json"
DELETION_PLAN_PATH = DATA / "workpaper_sync_i_cycle_deletion_plan.json"
PARADIGM_PATH = DATA / "workpaper_sync_migration_paradigm.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
OVERLAY_PATH = DATA / "workpaper_sync_entry_overlay.json"
SIBLING_SLICE_PATHS = {
    "D": DATA / "workpaper_sync_d_cycle_manifest_slice.json",
    "E": DATA / "workpaper_sync_e_cycle_manifest_slice.json",
    "F": DATA / "workpaper_sync_f_cycle_manifest_slice.json",
    "G": DATA / "workpaper_sync_g_cycle_manifest_slice.json",
    "H": DATA / "workpaper_sync_h_cycle_manifest_slice.json",
}
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
TEMPLATE_DIR = BACKEND / "wp_templates"
TEMPLATE_INDEX = TEMPLATE_DIR / "_index.json"
I_TEMPLATE_DIR = TEMPLATE_DIR / "I"
CHECKLIST_ROUTER = BACKEND / "app" / "routers" / "checklist_responses.py"
REGISTRY = BACKEND / "app" / "services" / "workpaper_sync" / "adapters" / "registry.py"
HTML_RENDERER_REGISTRY = WP_COMPONENTS / "htmlRendererRegistry.ts"
SHARED_BASE = COMPOSABLES / "useWorkpaperEntryDualMode.ts"
NOTE_TEMPLATE_SOE = DATA / "note_template_soe.json"
NOTE_TEMPLATE_LISTED = DATA / "note_template_listed.json"

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
#: g7 是 `-long-term-equity-main` 而不是文件名暗示的 `-soe-subsidiary`。首轮按文件名猜错两条。
PILOT_CONTRACT_OWNERS = {
    "b60.hour_budget.json": "xlsx/b60/gt-b60-bundle",
    "d2.receivable_detail.json": "xlsx/gt-d2-accounts-receivable",
    "g7.soe_subsidiary_disclosure.json": "xlsx/gt-g7-long-term-equity-main",
    "h1.disposal_check.json": "xlsx/gt-h1-fixed-assets",
}

#: 本 slice 覆盖的循环子目录（i1..i6），用于组织「全 I 循环」扫描的分母。
I_SUBDIRS = ("i1", "i2", "i3", "i4", "i5", "i6")
#: composables 里属本 slice 的文件名前缀正则（i1..i6 / useI1..useI6）。
I_COMPOSABLE_RE = re.compile(r"(?:use)?[iI][1-6](?![0-9])")


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_ts_comments(source: str) -> str:
    """剥掉 TS/Vue 注释 —— 说明文字不得充当判据证据。

    🔴 剥完必须反向自检（见 TestGuardSelfChecks）。本文件对它的依赖很重：
    「I 循环 0 处 label-as-key」这条穷举判据的分母就是剥注释后的正文 —— 剥不干净会假红
    （i1CategoryScope.ts 的注释里逐字写着 `不用中文 label 作键`），剥过头会假绿。
    """
    source = re.sub(r"/\*[\s\S]*?\*/", "", source)
    source = re.sub(r"(?m)^\s*//.*$", "", source)
    source = re.sub(r"(?m)//[^\n\"'`]*$", "", source)
    source = re.sub(r"<!--[\s\S]*?-->", "", source)
    return source


def _vue_template(source: str) -> str:
    """取 SFC 的**外层** template 区块。

    🔴 不能用 `source.split("</template>")[0]`：SFC 里嵌套的 `<template v-else>`
    会先闭合（I 循环 6 个宿主全都在 #L30 有 `<template v-else-if=...>`），第一处
    `</template>` 落在内层 ⇒ 截出来的片段比真实模板短，判据会把「已在模板里」误判成
    「不在模板里」。这里改用 `<script` 边界。
    """
    marker = source.find("<script")
    assert marker > 0, "找不到 <script 边界 —— 该文件不是常规 SFC（template 在 script 之前）"
    head = source[:marker]
    assert "<template>" in head, "SFC 头部没有 <template>"
    return head


def _toolbar_block(template: str, gate_anchor: str) -> str:
    """按 slice 声明的工具栏锚点截出该区块（开标签行 → 同缩进的 `</div>`）。

    🔴 为什么按 slice 声明取锚点而不是写死正则：I 循环 6 个宿主的工具栏 class 与门控
    表达式逐个不同（i1..i6 各自的 class + I2 的 `showHtmlToolbar` vs 其余的
    `isHtmlSheet && currentSheet !== 'I{n}'`）。写死任一种会让其余的判据静默恒真
    （挂载点根本不在被搜的区块里也不报错）。另外 I1#L171 与 I4#L142 各有一个 Tab 内部
    分段用的 `el-segmented` —— 全文件 grep 会把它误判成第二个模式切换器。
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
    """openpyxl 真读权威模板的一段单列区间（`A9:A19` 或单格 `A11`）。

    :param formula: True ⇒ `data_only=False` 读公式串（CD-7 的披露行标签本身是公式）；
                    False ⇒ `data_only=True` 读缓存值（CD-1/CD-3/CD-4 是字面文本）。
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


def _array_literal_body(source: str, symbol: str) -> str:
    """截出 `... {symbol} ... = [` 之后到配对 `]` 的数组字面量正文。

    🔴 括号配对而非固定字符窗口：I5 的常量项带嵌套对象与三处 `navigateHint`，
    固定窗口会截断；且必须**先跳过类型注解**（`I5_BUILTIN_CATEGORIES: I5BuiltinCategory[] = [`
    里 `[]` 会骗到「第一个 `[`」）—— 这里锚在 `=` 之后的第一个 `[`。
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


def _function_return_array_body(source: str, func: str) -> str:
    """截出 `function {func}(...) { return [ ... ] }` 里的数组字面量正文。"""
    match = re.search(r"\bfunction\s+" + re.escape(func) + r"\s*\(", source)
    assert match, f"源码里找不到函数 {func!r}"
    rest = source[match.end() :]
    ret = rest.find("return")
    assert ret > 0, f"{func!r} 函数体里没有 return"
    tail = rest[ret:]
    start = tail.index("[")
    depth = 0
    for pos in range(start, len(tail)):
        char = tail[pos]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return tail[start : pos + 1]
    pytest.fail(f"{func!r} 的 return 数组没有配对的 `]`")


def _extract_impl_labels(source: str, symbol: str, kind: str) -> list[str]:
    """按声明的 `impl_extraction_kind` 从 impl 模块抽出标签序列（有序）。

    kind 取值（真源 = slice 的 declarations[].impl_extraction_kind）：
      * `object_field:<field>`      —— 数组里逐项的 `<field>: '<中文>'`
      * `bare_string_literals`      —— 数组里的裸字符串字面量
      * `call_arg_field:<field>`    —— 函数 return 数组里逐个调用实参的 `<field>: '<中文>'`
      * `none`                      —— impl 无分类常量（否定式声明，调用方不该走到这里）
    """
    body_source = _strip_ts_comments(source)
    if kind.startswith("object_field:"):
        field = kind.split(":", 1)[1]
        body = _array_literal_body(body_source, symbol)
        return re.findall(re.escape(field) + r"\s*:\s*'([^']*)'", body)
    if kind == "bare_string_literals":
        body = _array_literal_body(body_source, symbol)
        return re.findall(r"'([^']*)'", body)
    if kind.startswith("call_arg_field:"):
        field = kind.split(":", 1)[1]
        body = _function_return_array_body(body_source, symbol)
        return re.findall(re.escape(field) + r"\s*:\s*'([^']*)'", body)
    raise AssertionError(f"未知的 impl_extraction_kind {kind!r} —— 判据 fail closed，不放宽")


def _value_expr_after_key(line: str, key: str) -> str | None:
    """截出 `key:` 之后**属于它自己**的值表达式（到同层逗号 / 行尾止）。

    🔴 为什么不能拿整行当判据：I 循环 20 处 `seq: raw.seq ?? idx + 1` / `seq: i + 1` 与
    身份字段常在同一个对象字面量里 —— 按整行判会把它们全报成位置化行身份
    （G 循环在 G12、H 循环在 H3/H6 上各踩过一次）。
    """
    match = re.search(r"\b" + re.escape(key) + r"\s*\??\s*:", line)
    if not match:
        return None
    rest = line[match.end() :]
    depth = 0
    in_tmpl = False
    for pos, char in enumerate(rest):
        if char == "`":
            in_tmpl = not in_tmpl
            continue
        if in_tmpl:
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                return rest[:pos]
            depth -= 1
        elif char == "," and depth == 0:
            return rest[:pos]
    return rest


#: 位置化身份 token —— 命中即说明身份值由数组下标 / 序号派生（forbidden 三种之一）。
#: 🔴 比 H 循环的口径多两支：`(?:\|\||\?\?)\s*(?:i|idx|index)\s*[\})]`（不带 `+ 1` 的
#: 纯兜底，I 循环有 4 处 `${r.rowId || i}`）。H 的口径只认带 `+ 1` 的，照抄会漏掉那 4 处。
_POSITIONAL_IDENTITY_TOKEN = re.compile(
    r"\$\{\s*i\s*\}"
    r"|\$\{\s*idx\s*\}"
    r"|\$\{\s*index\s*\}"
    r"|\$\{\s*seq\s*\}"
    r"|(?:\|\||\?\?)\s*(?:i|idx|index)\s*(?:\+\s*1)?\s*[\}\),]"
    r"|(?:\|\||\?\?)\s*String\(\s*(?:i|idx|index)"
    r"|\bindexOf\("
)

#: 身份字段名候选 —— I 循环实测两族（rowId 五条 / id 一条），另留 rowKey 供将来。
_IDENTITY_KEYS = ("rowId", "rowKey", "id")

#: 「列 key 用 label」两种形态（Property 22 的反例分母）。
_COLUMN_KEY_IS_LABEL = re.compile(r"\bkey\s*:\s*[A-Za-z_$][\w$]*(?:\.[\w$]+)*\.label\b")
_ROW_CELL_KEY_IS_LABEL = re.compile(r"\brow\s*\[\s*[A-Za-z_$][\w$]*(?:\.[\w$]+)*\.label\s*\]")
#: 「动态区骨架行数写死」形态：`blankRows(<expr>, <整数字面量>)`。
_BLANK_ROWS_FIXED = re.compile(r"\bblankRows\s*\(\s*[^,()]+,\s*\d+\s*\)")
#: 「按公司/单位横向展开写死列名」形态（严口径：引号紧贴）。
_HORIZONTAL_COLUMN_LITERAL = re.compile(r"['\"`](?:公司|单位)[1-9]\d*['\"`]")
#: 放宽引号前缀后的种子行名形态（CD-6 的 `可比公司1/2/3`）。
_SEED_COMPANY_LITERAL = re.compile(r"['\"][^'\"]{0,6}(?:公司|单位|课题|项目)[1-9]\d*['\"]")
#: 四表种子位置化形态（H 循环 BP-6 的形态；I 循环实测 0 处，这个 0 是判据的一部分）。
_FOUR_TABLE_SEED_POSITIONAL = re.compile(r"`(?:seed|row|detail|item)-\$\{\s*(?:i|idx|index)\s*\}")
#: 展示序号站点（family_c 的反向自检分母）。
_DISPLAY_SEQ_SITE = re.compile(r"\bseq\s*:\s*[^,]*(?:idx|index|\bi\b)\s*\+\s*1")


def _i_cycle_files() -> list[pathlib.Path]:
    """「全 I 循环」扫描的分母：i1..i6 子目录 + 本 slice 的 composables + GtI*.vue。

    分母**现扫**而不是写死清单 —— 新增文件自动进入，改判据不必改守卫。
    排除 `__tests__`（测试文件里的示例数据不是生产判据）。
    """
    out: set[pathlib.Path] = set()
    for name in I_SUBDIRS:
        directory = WP_COMPONENTS / name
        assert directory.is_dir(), f"缺 I 循环子目录 {directory}"
        out |= {
            p
            for p in directory.rglob("*")
            if p.is_file() and p.suffix in (".ts", ".vue") and "__tests__" not in p.as_posix()
        }
    for path in COMPOSABLES.rglob("*"):
        if not (path.is_file() and path.suffix == ".ts"):
            continue
        if "__tests__" in path.as_posix():
            continue
        if I_COMPOSABLE_RE.match(path.name):
            out.add(path)
    out |= {p for p in WP_COMPONENTS.glob("GtI[1-6]*.vue")}
    return sorted(out)


def _positional_identity_hits(files: list[pathlib.Path]) -> list[tuple[str, int, str, str]]:
    """穷举「身份字段的值由位置派生」的命中，返回 `(相对路径, 行号, 身份键, 表达式)`。"""
    hits: list[tuple[str, int, str, str]] = []
    for path in files:
        source = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT).as_posix()
        for no, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("*") or stripped.startswith("//"):
                continue
            for key in _IDENTITY_KEYS:
                expr = _value_expr_after_key(line, key)
                if expr is not None and _POSITIONAL_IDENTITY_TOKEN.search(expr):
                    hits.append((rel, no, key, expr.strip()))
                    break
    return hits


def _label_key_hits(files: list[pathlib.Path]) -> dict[str, list[str]]:
    """穷举「label 当 key」的命中（剥注释后），按两种形态分别返回 `文件#Lxx` 列表。"""
    out: dict[str, list[str]] = {"column_key_is_label": [], "row_cell_key_is_label": []}
    for path in files:
        body = _strip_ts_comments(path.read_text(encoding="utf-8", errors="replace"))
        rel = path.relative_to(ROOT).as_posix()
        for no, line in enumerate(body.splitlines(), 1):
            if _COLUMN_KEY_IS_LABEL.search(line):
                out["column_key_is_label"].append(f"{rel}#L{no}")
            if _ROW_CELL_KEY_IS_LABEL.search(line):
                out["row_cell_key_is_label"].append(f"{rel}#L{no}")
    return out


def _import_specifier_consumers(module_stem: str) -> list[str]:
    """全前端 src 里 **import 路径字面量**含 `module_stem` 的文件（排除自身）。

    🔴 这是「真消费边」口径，不是符号名口径。I 循环有 4 处
    `* - Follow useI{n}DualMode pattern` 注释，符号名口径会把它们报成消费方。
    形态覆盖 `from '<...>'` / `import('<...>')` / `vi.mock('<...>')` / `require('<...>')`
    —— 都落在「引号里的路径字面量」这一个模式上。
    """
    pattern = re.compile(r"['\"][^'\"]*/" + re.escape(module_stem) + r"(?:\.ts)?['\"]")
    out: list[str] = []
    for path in FRONTEND.rglob("*"):
        if not (path.is_file() and path.suffix in (".ts", ".vue")):
            continue
        if path.stem == module_stem:
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            out.append(path.relative_to(ROOT).as_posix())
    return sorted(out)


def _symbol_name_mentions(symbol: str) -> list[str]:
    """全前端 src 里出现 `symbol` 字样但**不是** import 边的文件（用于反向自检）。"""
    real = set(_import_specifier_consumers(symbol))
    out: list[str] = []
    for path in FRONTEND.rglob("*"):
        if not (path.is_file() and path.suffix in (".ts", ".vue")):
            continue
        if path.stem == symbol:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in real:
            continue
        if symbol in path.read_text(encoding="utf-8", errors="replace"):
            out.append(rel)
    return sorted(out)


def _strip_null_placeholder_columns(window: str) -> str:
    """把 `conclusion: null` / `remark: undefined` 这类**显式空占位**从写入点窗口剔除。

    🔴 `payload_column_mode` 判的是「业务内容写进哪一列」，而 `conclusion: null` 恰恰是
    「**不**往这列写内容」。I 循环 5 条 entry 的写入点都是
    `items: [{ item_id, conclusion: null, remark: strVal }]` —— 只看 token `conclusion:`
    在不在窗口里，会把它们全误判成 dual_write（G 循环 G2 踩过同一个坑）。剔除只针对
    **字面 null / undefined**，I4 的真分流写（`conclusion: isStatusMarker ? strVal : null`）
    不会被剔掉。
    """
    return re.sub(r"\b(remark|conclusion)\s*:\s*(?:null|undefined)\s*,?", "", window)


def _write_site_window(path: pathlib.Path, line_no: int, span: int = 6) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lo = max(0, line_no - 1 - span)
    hi = min(len(lines), line_no + span)
    return "\n".join(lines[lo:hi])


def _line_no_of(ref: str) -> int:
    match = re.search(r"#L(\d+)", ref)
    assert match, f"引用 {ref!r} 里没有 #Lxx 行号"
    return int(match.group(1))


def _client_probe(client: str, verb: str) -> Callable[[str], bool]:
    """按 slice 登记的 HTTP 客户端标识拼探针。

    🔴 不写成「`api.` 或 `http.` 二选一」的固定并集：那样任一 entry 的绑定名改了都不会红
    （另一族还在，并集恒真）。这里按**该 entry 自己声明的**标识拼正则。
    """
    esc = re.escape(client)

    def probe(source: str) -> bool:
        return bool(re.search(rf"{esc}\.{verb}\(\s*`[^`]*checklist-responses`", source))

    return probe


def _note_template_labels(path: pathlib.Path, needle: str) -> set[str]:
    """在 note_template JSON 全文里精确匹配某个标签，返回命中的 JSON Pointer 集合。"""
    doc = _load(path)
    hits: set[str] = set()

    def walk(node: Any, ptr: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{ptr}/{key}")
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, f"{ptr}/[{idx}]")
        elif str(node).strip() == needle:
            hits.add(ptr)

    walk(doc, "")
    return hits


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────
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
def i_files() -> list[pathlib.Path]:
    return _i_cycle_files()


# ════════════════════════════════════════════════════════════════════════════
# 判据零：守卫自身的反向自检（判据缺陷比代码缺陷更贵）
# ════════════════════════════════════════════════════════════════════════════
class TestGuardSelfChecks:
    """每个抽取/扫描 helper 都要有「故意写错必失败」的反向自检。

    没有这一组，下面所有「实测 N 处」的判据都可能是 helper 恒返回空导致的假绿。
    """

    def test_strip_comments_removes_comments_but_keeps_code(self) -> None:
        src = "const a = 1 // tail\n/* block */\nconst b = 2\n"
        out = _strip_ts_comments(src)
        assert "const a = 1" in out and "const b = 2" in out
        assert "tail" not in out and "block" not in out

    def test_strip_comments_does_not_eat_string_literals(self) -> None:
        src = "const url = 'https://x/y'\n"
        assert "https://x/y" in _strip_ts_comments(src)

    def test_strip_comments_really_hides_the_i1_label_key_comment(self) -> None:
        """i1CategoryScope.ts 的注释里逐字写着「不用中文 label 作键」——
        label-as-key 的穷举判据分母必须剥掉它，否则那条注释本身会被算成命中。"""
        raw = (COMPOSABLES / "i1CategoryScope.ts").read_text(encoding="utf-8")
        assert "label 作键" in raw, "前置变了：该注释已不在源码里，判据需重新校准"
        assert "label 作键" not in _strip_ts_comments(raw)

    def test_vue_template_extraction_does_not_stop_at_inner_template(self) -> None:
        """6 个宿主都在模板中段有 `<template v-else-if=...>` —— 用第一处 `</template>`
        截会漏掉后半段。这里断言外层 template 的长度真的覆盖到 `<script` 之前。"""
        for name in _host_names():
            src = (WP_COMPONENTS / name).read_text(encoding="utf-8")
            head = _vue_template(src)
            naive = src.split("</template>")[0]
            assert len(head) > len(naive), f"{name}: 外层 template 截取没有比朴素切法更长"

    def test_toolbar_block_extraction_is_bounded(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            name = entry["host"]
            anchor = _gate_anchor(entry)
            block = _toolbar_block(_vue_template((WP_COMPONENTS / name).read_text(encoding="utf-8")), anchor)
            assert block.count("<div") >= 1
            assert block.rstrip().endswith("</div>")
            assert "GtOnlyOfficeSheet" not in block, (
                f"{name}: 工具栏区块越界到了 OO 挂载点 —— 边界判定失效"
            )

    def test_toolbar_block_rejects_ambiguous_anchor(self) -> None:
        template = "<template>\n  <div class=\"x\">\n  </div>\n  <div class=\"x\">\n  </div>\n</template>"
        with pytest.raises(AssertionError, match="命中 2 次"):
            _toolbar_block(template, 'class="x"')

    def test_value_expr_after_key_is_scoped_to_its_own_key(self) -> None:
        line = "{ ...raw, rowId: raw.rowId ?? gen(), seq: raw.seq ?? idx + 1 }"
        assert _value_expr_after_key(line, "rowId") == " raw.rowId ?? gen()"
        assert "idx + 1" not in (_value_expr_after_key(line, "rowId") or "")
        assert "idx + 1" in (_value_expr_after_key(line, "seq") or "")

    def test_positional_token_catches_the_fallback_without_plus_one(self) -> None:
        """🔴 I 循环特有：4 处 `${r.rowId || i}` 不带 `+ 1`。H 循环的口径只认带 `+ 1` 的
        形态，照抄会漏掉这 4 处 —— 这条自检把「口径已加宽」锁死。"""
        assert _POSITIONAL_IDENTITY_TOKEN.search("`bv-${r.rowId || i}`")
        assert _POSITIONAL_IDENTITY_TOKEN.search("`cgu-${i}`")
        assert _POSITIONAL_IDENTITY_TOKEN.search("String(r.rowId || `cgu-${idx}`)")
        assert not _POSITIONAL_IDENTITY_TOKEN.search("`row-${Date.now()}-${Math.random()}`")

    def test_array_literal_body_skips_the_type_annotation_brackets(self) -> None:
        """`I5_BUILTIN_CATEGORIES: I5BuiltinCategory[] = [` 里的 `[]` 会骗到
        「第一个 `[`」—— 这条自检锁死「锚在 `=` 之后」。"""
        src = "export const X: Foo[] = [\n  { name: 'a' },\n]\n"
        body = _array_literal_body(src, "X")
        assert body.startswith("[") and body.endswith("]")
        assert "name: 'a'" in body
        assert "Foo" not in body

    def test_impl_extraction_kinds_are_all_dispatchable(self, manifest_slice: dict) -> None:
        """未知 kind 必须 fail closed —— 加字段不加语义不能悄悄放宽。"""
        with pytest.raises(AssertionError, match="未知的 impl_extraction_kind"):
            _extract_impl_labels("const X = []", "X", "some_new_kind")
        declared = {d["impl_extraction_kind"] for d in manifest_slice[
            "classification_row_model_derivation"
        ]["declarations"]}
        for kind in declared:
            assert kind == "none" or kind.startswith(
                ("object_field:", "bare_string_literals", "call_arg_field:")
            ), f"slice 里出现了 dispatch 不认识的 kind {kind!r}"

    def test_import_specifier_consumers_is_path_literal_not_symbol_name(self) -> None:
        """两侧都验：useI1DualMode 的真 import 边只有宿主（+ 测试），而符号名口径会
        多出 useI3DualMode.ts（那只是注释）。"""
        real = _import_specifier_consumers("useI1DualMode")
        mentions = _symbol_name_mentions("useI1DualMode")
        assert any("GtI1IntangibleAssets.vue" in r for r in real), real
        assert any("useI3DualMode.ts" in m for m in mentions), mentions
        assert not any("useI3DualMode.ts" in r for r in real), (
            "符号名口径污染了 import 边判据 —— useI3DualMode 只是在注释里提到它"
        )

    def test_null_placeholder_stripper_only_removes_literal_nulls(self) -> None:
        assert "conclusion" not in _strip_null_placeholder_columns("conclusion: null, remark: v")
        assert "conclusion" in _strip_null_placeholder_columns(
            "conclusion: isStatusMarker ? strVal : null, remark: strVal"
        )

    def test_client_probe_is_client_specific(self) -> None:
        src = "await http.put(`/api/workpapers/${id}/checklist-responses`, {})"
        assert _client_probe("http", "put")(src)
        assert not _client_probe("api", "put")(src)

    def test_i_cycle_denominator_is_non_vacuous(self, i_files: list[pathlib.Path]) -> None:
        assert len(i_files) >= 200, f"I 循环扫描分母只有 {len(i_files)} 个文件 —— 现扫失效"
        names = {p.name for p in i_files}
        for host in _host_names():
            assert host in names, f"分母里缺宿主 {host}"

    def test_all_required_artifacts_exist(self) -> None:
        for path in (
            MANIFEST_SLICE_PATH,
            DELETION_PLAN_PATH,
            PARADIGM_PATH,
            FULL_MANIFEST_PATH,
            OVERLAY_PATH,
            TEMPLATE_INDEX,
            CHECKLIST_ROUTER,
            REGISTRY,
            HTML_RENDERER_REGISTRY,
            SHARED_BASE,
            NOTICE_MODULE,
            NOTICE_COMPONENT,
            NOTE_TEMPLATE_SOE,
            NOTE_TEMPLATE_LISTED,
            I_TEMPLATE_DIR,
        ):
            assert path.exists(), f"缺依赖 {path}"
        for name, path in SIBLING_SLICE_PATHS.items():
            assert path.exists(), f"缺兄弟 slice {name}: {path}"


def _host_names() -> tuple[str, ...]:
    return (
        "GtI1IntangibleAssets.vue",
        "GtI2DevelopmentExpenditure.vue",
        "GtI3Goodwill.vue",
        "GtI4LongTermPrepaid.vue",
        "GtI5OtherNoncurrentAssets.vue",
        "GtI6ResearchDevelopmentExpense.vue",
    )


def _gate_anchor(entry: dict) -> str:
    """把 slice 的 `ui_toolbar_gate`（形如 `class="i1-header-toolbar"`）取成模板锚点。"""
    gate = entry["ui_toolbar_gate"]
    match = re.search(r'class="([^"]+)"', gate)
    assert match, f"{entry['entry_id']}: ui_toolbar_gate 不是 class 锚点形态：{gate!r}"
    return f'class="{match.group(1)}"'


# ════════════════════════════════════════════════════════════════════════════
# 判据一：slice_scope 可复算（step 1）
# ════════════════════════════════════════════════════════════════════════════
class TestSliceScopeIsRecomputable:
    """selection_rule 必须能从 source manifest **现算**出同一集合。

    手抄的清单等于自由文本 —— 改了 manifest 也不会打红。
    """

    @staticmethod
    def _i_prefixed(full_manifest: dict) -> list[dict]:
        return [
            e
            for e in full_manifest["entries"]
            if any(str(p).startswith("I") for p in e.get("wp_match", {}).get("wp_code_patterns", []))
        ]

    def test_selection_rule_recomputes_the_entry_set(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        computed = {
            e["entry_id"]
            for e in self._i_prefixed(full_manifest)
            if e["document_type"] == "xlsx" and e["independent_entry"] is True
        }
        declared = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert computed == declared, (
            f"selection_rule 现算集合与 slice 不符：只在 manifest={sorted(computed - declared)}，"
            f"只在 slice={sorted(declared - computed)}"
        )

    def test_scope_counters_match_the_manifest(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        prefixed = self._i_prefixed(full_manifest)
        scope = manifest_slice["slice_scope"]
        assert scope["i_prefixed_entry_total"] == len(prefixed)
        assert scope["i_prefixed_independent_total"] == sum(
            1 for e in prefixed if e["independent_entry"] is True
        )
        assert scope["excluded_pilot_entry_count"] == 0
        assert scope["parent_duplicate_count"] == 0

    def test_no_i_entry_is_a_parent_duplicate_child(self, full_manifest: dict) -> None:
        """🔴「0 条 parent_duplicate」是判据的一部分，不是省略：D 有 31 条、H 有 5 条。"""
        for entry in self._i_prefixed(full_manifest):
            assert entry["parent_entry_id"] is None, (
                f"{entry['entry_id']} 有 parent_entry_id ⇒ slice 的 parent_duplicate_count=0 失效"
            )
            assert entry["independent_entry"] is True

    def test_no_i_entry_is_a_word_channel(self, full_manifest: dict) -> None:
        for entry in self._i_prefixed(full_manifest):
            assert entry["document_type"] == "xlsx", f"{entry['entry_id']} 不是 xlsx"

    def test_the_slice_has_no_parent_duplicate_summary_section(self, manifest_slice: dict) -> None:
        """conditional_section 的 trigger 不成立时**不得**加空节（additive 死数据）。"""
        assert "parent_duplicate_summary" not in manifest_slice

    def test_no_pilot_contract_belongs_to_the_i_cycle(self) -> None:
        """「I 循环没有 pilot」这条排除项必须实证，不能假设。"""
        for name, owner in PILOT_CONTRACT_OWNERS.items():
            path = CONTRACT_DIR / name
            assert path.exists(), f"缺 pilot 契约 {name}"
            doc = _load(path)
            actual = doc["review"]["entry_id"]
            assert actual == owner, f"{name}: review.entry_id={actual!r} 应为 {owner!r}"
            assert not actual.startswith("xlsx/gt-i"), f"{name} 竟属 I 循环 —— 排除项失效"
        # 🔴 反向自检：文件名与 entry_id **不同构**（b60 三段式 / g7 是 -main）。
        # 这条锁住「不能按文件名猜 entry_id」这个结论 —— 首轮就是按文件名猜错了两条。
        assert PILOT_CONTRACT_OWNERS["b60.hour_budget.json"] == "xlsx/b60/gt-b60-bundle"
        assert PILOT_CONTRACT_OWNERS["g7.soe_subsidiary_disclosure.json"] == (
            "xlsx/gt-g7-long-term-equity-main"
        )

    def test_no_i0_confirmation_workbook_exists(self) -> None:
        """excluded_from_slice 第 2 条声称「没有 I0」—— 现扫证实。"""
        names = {p.name for p in I_TEMPLATE_DIR.iterdir() if not p.name.startswith("~$")}
        assert not any(n.startswith("I0") for n in names), f"竟有 I0 模板：{sorted(names)}"


# ════════════════════════════════════════════════════════════════════════════
# 判据二：裁决合法性（step 4 / AC 12.8 / 12.9 / AP-1 / SR-3..SR-7）
# ════════════════════════════════════════════════════════════════════════════
class TestAdjudicationLegality:
    def test_every_entry_has_a_binary_html_counterpart_verdict(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            verdict = entry.get("html_counterpart_verdict")
            assert verdict in HTML_COUNTERPART_VERDICTS, (
                f"{entry['entry_id']}: html_counterpart_verdict={verdict!r} 不是二值结论"
                "（AP-3：unresolved / unknown / 空值都不是结论）"
            )
            refs = entry.get("html_counterpart_source_refs")
            assert isinstance(refs, list) and refs, f"{entry['entry_id']}: source_refs 为空"

    def test_single_onlyoffice_requires_no_html_counterpart(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            if entry["capability"] == "single_onlyoffice":
                assert entry["html_counterpart_verdict"] == "none", (
                    f"{entry['entry_id']}: 裁 single_onlyoffice 但有 HTML 对端（违反 AC 12.8）"
                )

    def test_adjudication_reason_is_not_circular(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """AP-1：不得只以「本任务应交付的产物尚不存在」当裁决理由。"""
        ap1 = next(
            ap
            for ap in paradigm["adjudication_criteria"]["anti_patterns"]
            if ap["id"] == "AP-1"
        )
        markers = [str(m).lower() for m in ap1["circular_reason_markers"]]
        for entry in manifest_slice["independent_entries"]:
            reason = str(entry["adjudication"]["reason"]).lower()
            hit = [m for m in markers if m in reason]
            if hit:
                assert "html_counterpart_verdict" in reason or "对端" in reason, (
                    f"{entry['entry_id']}: reason 命中循环论证标记 {hit} 且没有对端结论"
                )

    def test_capability_is_enum_or_explicitly_pending(
        self, manifest_slice: dict, paradigm: dict
    ) -> None:
        """SR-3 蕴含式：落在枚举内，或为 null 且待裁决三字段按语义齐备。"""
        schema = paradigm["slice_schema"]
        pending_fields = schema["required_pending_verdict_fields"]
        semantics = schema["pending_verdict_field_semantics"]
        for entry in manifest_slice["independent_entries"]:
            cap = entry["capability"]
            if cap is not None:
                assert cap in CAPABILITY_ENUM, f"{entry['entry_id']}: capability={cap!r} 自造能力态"
                continue
            for field in pending_fields:
                assert field in entry, f"{entry['entry_id']}: capability 为 null 但缺 {field}"
                kind = semantics[field]
                value = entry[field]
                if kind == "non_empty_string":
                    assert isinstance(value, str) and value.strip(), f"{entry['entry_id']}.{field}"
                elif kind == "member_of_capability_enum":
                    assert value in CAPABILITY_ENUM, f"{entry['entry_id']}.{field}={value!r}"
                elif kind == "non_empty_list":
                    assert isinstance(value, list) and value, f"{entry['entry_id']}.{field}"
                else:
                    pytest.fail(f"未声明语义的 pending 字段 {field}（fail closed）")

    def test_capability_matches_honest_capability(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            assert entry["capability"] == entry["adjudication"]["honest_capability"], (
                f"{entry['entry_id']}: SR-4 双口径"
            )

    def test_pending_entries_carry_no_identity(self, manifest_slice: dict) -> None:
        """SR-5 / AP-5：未裁决与裁 single 的 entry 都不得挂 adapter/contract/bundle。"""
        identity = (
            "adapter_id",
            "authority_model",
            "definition_bundle",
            "instrumentation_candidate",
            "published_representation",
        )
        for entry in manifest_slice["independent_entries"]:
            cap = entry["capability"]
            if cap == "bidirectional":
                continue
            non_null = [k for k in identity if entry.get(k) is not None]
            assert not non_null, f"{entry['entry_id']}: capability={cap!r} 却挂着 {non_null}"

    def test_adjudication_carries_both_negative_reasons(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            adj = entry["adjudication"]
            for key in ("not_single_html_because", "not_bidirectional_because"):
                assert str(adj.get(key, "")).strip(), f"{entry['entry_id']}: {key} 为空"

    def test_capability_blockers_reference_real_preconditions(self, manifest_slice: dict) -> None:
        known = {bp["id"] for bp in manifest_slice["blocking_preconditions"]}
        for entry in manifest_slice["independent_entries"]:
            for bid in entry["capability_target_blocked_by"]:
                assert bid in known, f"{entry['entry_id']}: 引用了不存在的阻断项 {bid}"

    def test_every_entry_scoped_blocker_has_a_carrier(self, manifest_slice: dict) -> None:
        """entry 级阻断项（BP-5..BP-8）必须真有承载 entry —— 反之亦然（两侧都断言）。"""
        # 🔴 BP-8 覆盖两条 entry（I6 的 I6_DETAIL_DEFAULT_CATEGORIES 与 I4 的 CATEGORY_OPTIONS，
        # 同一缺陷类「分类枚举含无真源标签」）。I4 那一条是三边锁的 impl 侧现读把初版声明证伪后新增的。
        expected = {
            "BP-5": {"xlsx/gt-i4-long-term-prepaid", "xlsx/gt-i6-research-development-expense"},
            "BP-6": {"xlsx/gt-i3-goodwill", "xlsx/gt-i1-intangible-assets"},
            "BP-7": {"xlsx/gt-i1-intangible-assets"},
            "BP-8": {"xlsx/gt-i4-long-term-prepaid", "xlsx/gt-i6-research-development-expense"},
        }
        actual: dict[str, set[str]] = {k: set() for k in expected}
        for entry in manifest_slice["independent_entries"]:
            for bid in entry["capability_target_blocked_by"]:
                if bid in actual:
                    actual[bid].add(entry["entry_id"])
        assert actual == expected, f"entry 级阻断项承载面漂移：{actual}"

    def test_all_blocking_preconditions_carry_task48_fields(self, manifest_slice: dict) -> None:
        for bp in manifest_slice["blocking_preconditions"]:
            for key in ("id", "blocks", "what", "status", "must_fix_before", "source_refs"):
                assert key in bp and bp[key], f"{bp.get('id')}: 缺 {key}"
            assert "consequence" in bp or "observable_consequences" in bp, (
                f"{bp['id']}: 后果必须写明（one-of 组）"
            )
            for ref in bp["source_refs"]:
                assert _resolve_repo(ref).exists(), f"{bp['id']}: source_ref 不存在 {ref}"

    def test_manifest_mirror_divergence_is_registered_not_silently_equal(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        """🔴 manifest overlay 陷阱：断言 slice 与 manifest **必须不一致**，且该不一致已登记为 BP。

        断言相等会强迫作者把 slice 改成 manifest 的错值（或手改 source-backed 生成物）。
        """
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        overlay_default = _load(OVERLAY_PATH)["defaults_by_component"]["GtOnlyOfficeSheet"]
        registered = {bp["id"] for bp in manifest_slice["blocking_preconditions"]}
        assert "BP-9" in registered, "manifest 分歧未登记为 BP-9"
        for entry in manifest_slice["independent_entries"]:
            live = by_id[entry["entry_id"]]
            mirror = entry["manifest_mirror"]
            assert mirror["capability"] == live["capability"], (
                f"{entry['entry_id']}: manifest_mirror 与 manifest 现值不符（镜像已过期）"
            )
            assert mirror["html_store"] == live["html_store"]
            assert mirror["capability"] == overlay_default["capability"], (
                f"{entry['entry_id']}: 该值不是来自 overlay 的组件级默认值 —— BP-9 的因果链断了"
            )
            assert entry["capability"] != live["capability"], (
                f"{entry['entry_id']}: slice 与 manifest 竟然一致 —— BP-9 的分歧前提不成立，"
                "要么 manifest 被手改了，要么 slice 抄了 manifest 的错值"
            )
            assert "BP-9" in str(mirror["divergence_from_slice"])


# ════════════════════════════════════════════════════════════════════════════
# 判据三：HTML 对端是 source-backed（step 3）
# ════════════════════════════════════════════════════════════════════════════
class TestHtmlCounterpartIsSourceBacked:
    def test_source_refs_point_at_real_paths(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            for ref in entry["html_counterpart_source_refs"]:
                assert _resolve_repo(ref).exists(), f"{entry['entry_id']}: 不存在的 source_ref {ref}"

    def test_html_store_endpoint_exists_in_the_router(self, manifest_slice: dict) -> None:
        router = CHECKLIST_ROUTER.read_text(encoding="utf-8")
        assert "checklist-responses" in router or "checklist_responses" in router
        for entry in manifest_slice["independent_entries"]:
            assert entry["html_counterpart"]["store"] == "checklist_responses"

    def test_write_carrier_client_and_put_site_agree_with_the_source(
        self, manifest_slice: dict
    ) -> None:
        for entry in manifest_slice["independent_entries"]:
            counterpart = entry["html_counterpart"]
            path = _resolve_repo(counterpart["write_carrier_path"])
            assert path.exists(), f"{entry['entry_id']}: write_carrier_path 不存在"
            source = path.read_text(encoding="utf-8")
            client = counterpart["write_client"]
            assert _client_probe(client, "put")(source), (
                f"{entry['entry_id']}: 声明 write_client={client!r} 但 {path.name} 里没有对应的 PUT"
            )
            line_no = _line_no_of(counterpart["endpoint_write_source"])
            window = _write_site_window(path, line_no)
            assert "checklist-responses" in window, (
                f"{entry['entry_id']}: endpoint_write_source 指的行附近没有 checklist-responses"
            )

    def test_write_carrier_families_cover_every_entry_exactly_once(
        self, manifest_slice: dict
    ) -> None:
        families = manifest_slice["i_cycle_form_differences"]["differences"][0]["entries_by_family"]
        listed = [eid for group in families.values() for eid in group]
        assert len(listed) == len(set(listed)), "写载体分族有重复 entry"
        assert set(listed) == {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for family, group in families.items():
            for eid in group:
                entry = next(e for e in manifest_slice["independent_entries"] if e["entry_id"] == eid)
                assert entry["html_counterpart"]["write_carrier"] == family, (
                    f"{eid}: 分族 {family} 与 entry 声明的 write_carrier 不符"
                )

    def test_i5_host_really_has_no_http_client_import(self, manifest_slice: dict) -> None:
        """🔴 反向断言：I5 是唯一 formdata_composable 载体，其宿主**没有** client import。

        写死「全宿主都有 client import」会让 I5 静默通过。
        """
        i5 = next(
            e for e in manifest_slice["independent_entries"]
            if e["entry_id"] == "xlsx/gt-i5-other-noncurrent-assets"
        )
        assert i5["html_counterpart"]["write_carrier"] == "formdata_composable"
        host = (WP_COMPONENTS / i5["host"]).read_text(encoding="utf-8")
        assert not re.search(r"(?m)^\s*import\s+http\s+from", host), (
            "I5 宿主竟 import 了 http —— 载体归属声明失效"
        )
        assert not re.search(r"(?m)^\s*import\s*\{[^}]*\bapi\b[^}]*\}\s*from", host)
        for other in manifest_slice["independent_entries"]:
            if other["entry_id"] == i5["entry_id"]:
                continue
            other_host = (WP_COMPONENTS / other["host"]).read_text(encoding="utf-8")
            assert re.search(r"(?m)^\s*import\s+http\s+from", other_host), (
                f"{other['entry_id']}: 声明 host_inline 但宿主没有 http import"
            )

    def test_no_host_does_a_direct_checklist_get(self, manifest_slice: dict) -> None:
        """🔴 ID-2 的核心实况：**0 条** entry 的宿主直接 GET /checklist-responses。

        这个 0 是判据的一部分 —— H 循环有 4 条，照抄 H 的口径会对 6 条全假红。
        """
        for entry in manifest_slice["independent_entries"]:
            host = (WP_COMPONENTS / entry["host"]).read_text(encoding="utf-8")
            assert not re.search(r"\.get\(\s*`[^`]*checklist-responses`", host), (
                f"{entry['entry_id']}: 宿主竟直接 GET checklist-responses ⇒ ID-2 的实况漂移"
            )

    def test_read_carrier_matches_its_declared_family(self, manifest_slice: dict) -> None:
        diffs = manifest_slice["i_cycle_form_differences"]["differences"]
        id2 = next(d for d in diffs if d["id"] == "ID-2")
        by_family = id2["entries_by_read_carrier"]
        forced = id2["force_component_type_values"]
        listed = [eid for group in by_family.values() for eid in group]
        assert set(listed) == {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert len(listed) == len(set(listed))
        for entry in manifest_slice["independent_entries"]:
            family = entry["html_counterpart"]["read_carrier"]
            assert entry["entry_id"] in by_family[family]
            path = _resolve_repo(entry["html_counterpart"]["read_carrier_path"])
            source = path.read_text(encoding="utf-8")
            assert re.search(r"\.get\(\s*`[^`]*render-config`", source), (
                f"{entry['entry_id']}: {path.name} 里没有 render-config 的 GET"
            )
            if family == "host_inline_render_config_refetch":
                assert "props.htmlData" in source, f"{entry['entry_id']}: 缺 props.htmlData 读取"
                expected = forced[entry["entry_id"]]
                assert f"force_component_type: '{expected}'" in source, (
                    f"{entry['entry_id']}: 缺 force_component_type: '{expected}'"
                )
            else:
                assert entry["entry_id"] not in forced, (
                    f"{entry['entry_id']}: 非 host_inline 族却登记了 force_component_type"
                )

    def test_payload_column_mode_matches_the_write_site(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            counterpart = entry["html_counterpart"]
            path = _resolve_repo(counterpart["payload_write_site"])
            window = _strip_null_placeholder_columns(
                _write_site_window(path, _line_no_of(counterpart["payload_write_site"]))
            )
            mode = counterpart["payload_column_mode"]
            has_conclusion = "conclusion" in window
            if mode == "remark_only_conclusion_null":
                assert not has_conclusion, (
                    f"{entry['entry_id']}: 声明 remark_only 但写入点有真 conclusion 赋值"
                )
            elif mode == "dual_write_remark_and_conclusion_for_status_marker":
                assert has_conclusion, (
                    f"{entry['entry_id']}: 声明分流写 conclusion 但写入点剥掉空占位后没有它"
                )
                assert "isStatusMarker" in window or "completion" in window, (
                    f"{entry['entry_id']}: 分流条件（状态标记正则）不在写入点窗口内"
                )
            elif mode == "passthrough_remark_and_conclusion":
                # 🔴 I5 独有：载体不决定写哪一列，两列都从入参 ChecklistItem 透传。
                assert has_conclusion, (
                    f"{entry['entry_id']}: 声明 passthrough 但写入点剥掉空占位后没有 conclusion"
                )
                assert re.search(r"conclusion:\s*item\.conclusion", window), (
                    f"{entry['entry_id']}: 不是从入参透传 conclusion —— passthrough 声明失效"
                )
                assert re.search(r"remark:\s*item\.remark", window)
                assert "isStatusMarker" not in window, (
                    f"{entry['entry_id']}: 竟有分流条件 —— 应登记为 dual_write_* 而非 passthrough"
                )
            else:
                pytest.fail(f"{entry['entry_id']}: 未知 payload_column_mode={mode!r}（fail closed）")

    def test_primary_table_owner_constant_is_real(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            primary = entry["html_counterpart"]["primary_table"]
            module = _resolve_repo(primary["owner_module"])
            assert module.exists(), f"{entry['entry_id']}: owner_module 不存在"
            body = _strip_ts_comments(module.read_text(encoding="utf-8"))
            const = primary["owner_constant"]
            item_id = primary["item_id"]
            assert primary["owner_declaration_kind"] == "module_constant"
            assert re.search(
                r"\bconst\s+" + re.escape(const) + r"\s*=\s*['\"]" + re.escape(item_id) + r"['\"]",
                body,
            ), f"{entry['entry_id']}: {module.name} 里没有 const {const} = '{item_id}'"

    def test_i6_legacy_alias_key_is_still_read_compatible(self, manifest_slice: dict) -> None:
        """🔴 ID-4：I6 的键与身份字段双双例外，且 legacy 读兼容不能悄悄消失。"""
        keys = manifest_slice["i_cycle_form_differences"]["differences"][3]["keys"]
        i6 = keys["xlsx/gt-i6-research-development-expense"]
        assert i6["item_id"] == "I6-2-detail-rows"
        assert i6["identity_field"] == "id"
        body = _strip_ts_comments((COMPOSABLES / "useI6Detail.ts").read_text(encoding="utf-8"))
        assert re.search(
            r"\bconst\s+" + re.escape(i6["legacy_alias_constant"]) + r"\s*=\s*['\"]"
            + re.escape(i6["legacy_alias_value"]) + r"['\"]",
            body,
        ), "useI6Detail.ts 里的 LEGACY_STORAGE_KEY 读兼容不见了 —— 历史数据会读不出"
        for eid, meta in keys.items():
            if eid == "xlsx/gt-i6-research-development-expense":
                continue
            assert meta["identity_field"] == "rowId", f"{eid}: ID-4 的两族划分漂移"
            assert re.fullmatch(r"I[1-5]-2-rows", meta["item_id"]), f"{eid}: 主表键命名漂移"

    def test_primary_table_identity_cell_matches_the_authoritative_template(
        self, manifest_slice: dict
    ) -> None:
        """🔴 三边锁的第一处应用：声明的 `sheet!cell` 真读出来必须等于声明的 `identity_text`。"""
        for entry in manifest_slice["independent_entries"]:
            primary = entry["html_counterpart"]["primary_table"]
            template = TEMPLATE_DIR / primary["template_relative_path"]
            assert template.exists(), f"{entry['entry_id']}: 模板不存在 {template}"
            values = _cells_of(template, primary["template_sheet"], primary["identity_cell"])
            assert values == [primary["identity_text"]], (
                f"{entry['entry_id']}: {primary['template_sheet']}!{primary['identity_cell']} "
                f"真读为 {values!r}，声明为 {primary['identity_text']!r}"
            )

    def test_template_ref_resolves_through_the_runtime_index(self, manifest_slice: dict) -> None:
        indexed = _indexed_relpaths()
        for entry in manifest_slice["independent_entries"]:
            ref = entry["template_ref"]
            assert (TEMPLATE_DIR / ref).exists(), f"{entry['entry_id']}: 模板不存在 {ref}"
            assert ref in indexed, f"{entry['entry_id']}: {ref} 不在 _index.json 里"

    def test_host_has_a_real_module_edge_in_the_renderer_registry(
        self, manifest_slice: dict
    ) -> None:
        """🔴 判「入口可达」落到 registry 的**模块边**，不按符号名 grep。"""
        registry = HTML_RENDERER_REGISTRY.read_text(encoding="utf-8")
        forced = manifest_slice["i_cycle_form_differences"]["differences"][1][
            "force_component_type_values"
        ]
        for entry in manifest_slice["independent_entries"]:
            stem = entry["host"].removesuffix(".vue")
            edge = re.search(
                r"defineAsyncComponent\(\s*\(\)\s*=>\s*import\(\s*['\"][^'\"]*"
                + re.escape(stem)
                + r"\.vue['\"]\s*\)",
                registry,
            )
            assert edge, f"{entry['entry_id']}: registry 里没有指向 {stem}.vue 的模块边"
            if entry["entry_id"] in forced:
                component_type = forced[entry["entry_id"]]
                assert f"componentType: '{component_type}'" in registry, (
                    f"{entry['entry_id']}: registry 里没有 componentType {component_type!r}"
                )

    def test_second_write_path_is_real(self, manifest_slice: dict) -> None:
        """ID-1 的 I2 第二写路径必须真存在且真有消费方（否则是死代码，不该登记成写路径）。"""
        second = manifest_slice["i_cycle_form_differences"]["differences"][0]["second_write_path"]
        assert set(second) == {"xlsx/gt-i2-development-expenditure"}
        declared = second["xlsx/gt-i2-development-expenditure"]
        path = _resolve_repo(declared)
        assert path.exists()
        source = path.read_text(encoding="utf-8")
        line_no = _line_no_of(declared)
        assert "checklist-responses" in _write_site_window(path, line_no)
        consumers = _import_specifier_consumers(path.stem)
        production = [c for c in consumers if "__tests__" not in c]
        assert production, f"{path.name} 被登记为第二写路径但生产零消费 —— 那是死代码"


# ════════════════════════════════════════════════════════════════════════════
# 判据四：分类/行模型由源 xlsx 真源派生 —— source_ref 三边锁（Task 51 正文第一条）
# ════════════════════════════════════════════════════════════════════════════
class TestClassificationRowModelDerivation:
    """本文件的核心。三边：声明 → 源真读 → impl 常量。

    「防同源错仍自洽」的实现方式：`expected_source_labels` 是 slice 里**冻结**的第三方
    基线，`impl_labels` 是 slice 里冻结的实现快照，两者都要与**现读**的源/impl 比对。
    改声明+改 impl（同源错）不会改变现读的源标签 ⇒ 仍然打红。
    """

    @staticmethod
    def _declarations(manifest_slice: dict) -> list[dict]:
        section = manifest_slice["classification_row_model_derivation"]
        return section["declarations"]

    def test_the_section_declares_its_forbidden_shortcuts(self, manifest_slice: dict) -> None:
        section = manifest_slice["classification_row_model_derivation"]
        for key in ("why_this_section_exists", "how_to_verify", "forbidden_shortcuts", "declarations", "summary"):
            assert key in section, f"classification_row_model_derivation 缺 {key}"
        assert len(section["forbidden_shortcuts"]) >= 4

    def test_every_declaration_has_the_machine_readable_dispatch_fields(
        self, manifest_slice: dict
    ) -> None:
        for dec in self._declarations(manifest_slice):
            for key in (
                "id",
                "entry_id",
                "impl_extraction_kind",
                "source_read_mode",
                "workbook",
                "sheet",
                "verdict",
                "status",
            ):
                assert key in dec, f"{dec.get('id')}: 缺 {key}"
            assert dec["source_read_mode"] in ("value", "formula")

    def test_declaration_entry_ids_are_all_in_the_slice(self, manifest_slice: dict) -> None:
        known = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for dec in self._declarations(manifest_slice):
            assert dec["entry_id"] in known, f"{dec['id']}: entry_id 不属本 slice"

    def test_declared_source_cells_read_back_exactly_the_frozen_labels(
        self, manifest_slice: dict
    ) -> None:
        """🔴 三边锁的第②边：openpyxl 真读源 cells == slice 冻结的 expected_source_labels。

        改了权威模板而不改声明 ⇒ 打红。这条独立于 impl，是「源侧基线」。
        """
        checked = 0
        for dec in self._declarations(manifest_slice):
            expected = dec.get("expected_source_labels")
            if expected is None:
                continue
            workbook = I_TEMPLATE_DIR / dec["workbook"]
            assert workbook.exists(), f"{dec['id']}: 模板不存在 {workbook}"
            got = _cells_of(
                workbook,
                dec["sheet"],
                dec["cells"],
                formula=dec["source_read_mode"] == "formula",
            )
            assert got == expected, (
                f"{dec['id']}: 源真读 {dec['sheet']}!{dec['cells']} = {got!r}，"
                f"slice 冻结为 {expected!r}"
            )
            checked += 1
        assert checked >= 6, f"只核了 {checked} 条 declaration 的源侧基线 —— 分母缩水"

    def test_impl_constants_read_back_exactly_the_frozen_labels(
        self, manifest_slice: dict
    ) -> None:
        """🔴 三边锁的第③边：现读 impl 常量 == slice 冻结的 impl_labels。

        改了 impl 常量而不改声明 ⇒ 打红。
        """
        checked = 0
        for dec in self._declarations(manifest_slice):
            kind = dec["impl_extraction_kind"]
            if kind == "none":
                assert dec["impl_constant"] is None, f"{dec['id']}: kind=none 但 impl_constant 非空"
                assert dec["impl_labels"] == [], f"{dec['id']}: kind=none 但 impl_labels 非空"
                continue
            module = _resolve_repo(dec["impl_module"])
            assert module.exists(), f"{dec['id']}: impl_module 不存在"
            got = _extract_impl_labels(
                module.read_text(encoding="utf-8"), dec["impl_constant"], kind
            )
            assert got == dec["impl_labels"], (
                f"{dec['id']}: impl 现读 {got!r}，slice 冻结为 {dec['impl_labels']!r}"
            )
            checked += 1
        assert checked == 6, f"impl 侧核了 {checked} 条（应为 6：CD-1/2/3/4/6/8）"

    def test_verdicts_equal_the_actual_comparison(self, manifest_slice: dict) -> None:
        """🔴 三边锁的合成边：`verdict` 必须等于「源真读 vs impl 现读」的实际结果。

        把 MISMATCH 写成 MATCH（或反之）⇒ 打红。这是「声明与实现同错」唯一挡不住的漏洞
        的补丁：verdict 不是自述，是可复算的。
        """
        for dec in self._declarations(manifest_slice):
            kind = dec["impl_extraction_kind"]
            if kind == "none":
                assert dec["verdict"] in (
                    "NO_IMPL_CLASSIFICATION_BY_DESIGN",
                    "SOURCE_ITSELF_DERIVES_FROM_DETAIL",
                ), f"{dec['id']}: kind=none 却给了实体 verdict {dec['verdict']!r}"
                continue
            source = dec.get("expected_source_labels_normalized") or dec.get("expected_source_labels")
            impl = dec["impl_labels"]
            if source is None:
                assert dec["verdict"] == "HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF", (
                    f"{dec['id']}: 没有 source_ref 却不是 HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF"
                )
                assert dec["declared_source_ref"] is None
                continue
            if source == impl:
                assert dec["verdict"] == "MATCH", f"{dec['id']}: 实际相等但 verdict={dec['verdict']!r}"
            elif impl[: len(source)] == source:
                assert dec["verdict"] == "PREFIX_MATCH_WITH_UNSOURCED_TAIL", (
                    f"{dec['id']}: 实际是前缀相等但 verdict={dec['verdict']!r}"
                )
            else:
                assert dec["verdict"] == "MISMATCH", (
                    f"{dec['id']}: 实际不符但 verdict={dec['verdict']!r}"
                )

    def test_cd2_diverges_from_both_declared_sources(self, manifest_slice: dict) -> None:
        """BP-7 的双真源否证：note_template_soe 里 impl 独有的三个标签必须命中 0 处。

        🔴 两侧都断言：impl-only 的标签在附注模板里 0 处（否证 impl），
        source-only 的标签在附注模板里 >0 处（证实源侧口径）。
        """
        cd2 = next(d for d in self._declarations(manifest_slice) if d["id"] == "CD-2")
        assert cd2["verdict"] == "MISMATCH"
        source = cd2["expected_source_labels_normalized"]
        impl = cd2["impl_labels"]
        impl_only = sorted(set(impl) - set(source))
        source_only = sorted(set(source) - set(impl))
        assert impl_only == ["房屋使用权", "探矿权", "特许权", "采矿权"], impl_only
        assert source_only == ["住房使用权", "特许经营权", "矿产权"], source_only
        for label in impl_only:
            hits = _note_template_labels(NOTE_TEMPLATE_SOE, label)
            assert not hits, f"CD-2: impl 独有标签 {label!r} 竟在 note_template_soe 里命中 {len(hits)} 处"
        for label in source_only:
            hits = _note_template_labels(NOTE_TEMPLATE_SOE, label)
            assert hits, f"CD-2: 源标签 {label!r} 在 note_template_soe 里 0 命中 —— 第二真源前提失效"

    def test_cd2_legacy_key_map_collapses_two_impl_categories(self, manifest_slice: dict) -> None:
        """BP-7 的后果之一：exploration 与 mining 共享一个标准 key ⇒ 稳定 key 不再单射。"""
        body = _strip_ts_comments((COMPOSABLES / "i1CategoryScope.ts").read_text(encoding="utf-8"))
        match = re.search(r"I1_LEGACY_KEY_MAP[^=]*=\s*\{([\s\S]*?)\n\}", body)
        assert match, "找不到 I1_LEGACY_KEY_MAP"
        pairs = dict(re.findall(r"(\w+)\s*:\s*'([^']*)'", match.group(1)))
        assert pairs.get("exploration") == pairs.get("mining") == "mining_right", (
            f"BP-7 的「两条 impl 分类共享一个标准 key」前提漂移：{pairs}"
        )

    def test_cd4_unsourced_tail_has_zero_hits_in_every_authoritative_source(
        self, manifest_slice: dict
    ) -> None:
        """BP-8：`设计费` / `装备调试费` 在 6 本权威模板与两份附注模板里命中 0 处。

        🔴 `委外研发费` 单独处理 —— 它在 I2-7 有 4 处**列头**命中，是「有字但不是 I6 行类别」，
        判据必须区分「0 命中」与「只在别的语境命中」，否则修好一个就红。
        """
        cd4 = next(d for d in self._declarations(manifest_slice) if d["id"] == "CD-4")
        assert cd4["verdict"] == "PREFIX_MATCH_WITH_UNSOURCED_TAIL"
        source = cd4["expected_source_labels"]
        tail = cd4["impl_labels"][len(source) :]
        assert tail == ["设计费", "装备调试费", "委外研发费", "其他"], tail
        for label in ("设计费", "装备调试费"):
            for note in (NOTE_TEMPLATE_SOE, NOTE_TEMPLATE_LISTED):
                assert not _note_template_labels(note, label), (
                    f"CD-4: {label!r} 竟在 {note.name} 里有命中 —— BP-8 的「零真源」前提漂移"
                )
        i6_hits = self._xlsx_exact_hits(I_TEMPLATE_DIR / cd4["workbook"], "委外研发费")
        assert not i6_hits, f"CD-4: 委外研发费 在 I6 册里竟有命中 {i6_hits}"
        i2_hits = self._xlsx_exact_hits(I_TEMPLATE_DIR / "I2 开发支出.xlsx", "委外研发费")
        assert i2_hits, "CD-4: 委外研发费 在 I2 册里 0 命中 —— 「只在别的语境命中」的对照失效"
        assert all(ref.startswith("研发项目构成明细表I2-7!") for ref in i2_hits), i2_hits

    def test_cd4_source_extension_rows_are_really_blank(self, manifest_slice: dict) -> None:
        """BP-8 的另一半：源模板 A13:A18 必须真是空白可扩位（不是有名分类）。"""
        workbook = I_TEMPLATE_DIR / "I6 研发费用.xlsx"
        blanks = _cells_of(workbook, "明细表I6-2", "A13:A18")
        assert blanks == [None] * 6, f"I6-2!A13:A18 不再是空白：{blanks!r}"
        assert _cells_of(workbook, "明细表I6-2", "A19") == ["合计"]

    def test_cd3_boundary_cells_are_what_the_slice_says(self) -> None:
        """CD-3 的区间边界主张（A10 标题 / A21 可扩位 / A22 合计 / A23 第二区段）必须真成立。

        🔴 这条防的是「区间选错但恰好对齐」：把 A11:A20 改成 A12:A21 也能凑出 10 个值。
        """
        workbook = I_TEMPLATE_DIR / "I5 其他非流动资产.xlsx"
        assert _cells_of(workbook, "明细表I5-2", "A10") == ["其他非流动资产原值："]
        assert _cells_of(workbook, "明细表I5-2", "A21") == ["……"]
        assert _cells_of(workbook, "明细表I5-2", "A22") == ["合计"]
        assert _cells_of(workbook, "明细表I5-2", "A23") == ["减值准备："]

    def test_cd1_boundary_cells_are_what_the_slice_says(self) -> None:
        """CD-1 同理：底稿目录 A8 是标题行、A20 是可扩位。"""
        workbook = I_TEMPLATE_DIR / "I1 无形资产、累计摊销及减值准备.xlsx"
        head = _cells_of(workbook, "底稿目录", "A8")
        assert head and "无形资产类别设置" in str(head[0]), head
        assert _cells_of(workbook, "底稿目录", "A20") == ["……"]

    def test_negative_declarations_really_have_no_impl_copy(self, manifest_slice: dict) -> None:
        """CD-5 的否定式：源模板的可改名占位**不得**被抄进前端常量。

        🔴 没有这条，「照源模板补全分类常量」这个动作不会被任何正向判据触发。
        🔴 首轮把 CD-8（I4）也放在这里，被本条打红 —— `useI4Detail.CATEGORY_OPTIONS` 真的存在。
        改正后 CD-8 成了带源比对的实体声明（见 test_cd8_...），否定式只剩 CD-5。
        """
        dec = next(d for d in self._declarations(manifest_slice) if d["id"] == "CD-5")
        assert dec["verdict"] == "NO_IMPL_CLASSIFICATION_BY_DESIGN"
        assert dec["impl_constant"] is None
        assert dec["expected_source_labels"] == ["课题", "课题1", "课题2", "课题3"]
        body = _strip_ts_comments((COMPOSABLES / "useI2Detail.ts").read_text(encoding="utf-8"))
        for placeholder in ("课题1", "课题2", "课题3"):
            assert placeholder not in body, (
                f"CD-5: useI2Detail.ts 里出现了源模板占位 {placeholder!r} —— 占位被抄成了常量"
            )
        negatives = [
            d
            for d in self._declarations(manifest_slice)
            if d["verdict"] == "NO_IMPL_CLASSIFICATION_BY_DESIGN"
        ]
        assert [d["id"] for d in negatives] == ["CD-5"], (
            f"否定式声明集合漂移：{[d['id'] for d in negatives]}"
        )

    def test_cd8_i4_category_enum_has_an_unsourced_tail(self, manifest_slice: dict) -> None:
        """CD-8（据守卫打红改正后的实体声明）：I4 的 `CATEGORY_OPTIONS` 尾部 3 条零真源。"""
        dec = next(d for d in self._declarations(manifest_slice) if d["id"] == "CD-8")
        assert dec["verdict"] == "PREFIX_MATCH_WITH_UNSOURCED_TAIL"
        assert dec["impl_constant"] == "CATEGORY_OPTIONS"
        assert dec["registered_as"] == "BP-8"
        source = dec["expected_source_labels"]
        impl = dec["impl_labels"]
        assert source == ["使用权资产改良及维护支出"]
        assert impl[: len(source)] == source
        tail = impl[len(source) :]
        assert tail == ["租入固定资产改良支出", "固定资产大修理支出", "开办费", "其他", ""], tail
        # 第 2~4 条：全 6 本权威模板 + 两份 note_template 精确匹配 0 命中
        for label in ("租入固定资产改良支出", "固定资产大修理支出", "开办费"):
            for workbook in sorted(I_TEMPLATE_DIR.iterdir()):
                if workbook.name.startswith("~$"):
                    continue
                hits = self._xlsx_exact_hits(workbook, label)
                assert not hits, f"CD-8: {label!r} 竟在 {workbook.name} 里命中 {hits}"
            for note in (NOTE_TEMPLATE_SOE, NOTE_TEMPLATE_LISTED):
                assert not _note_template_labels(note, label), (
                    f"CD-8: {label!r} 竟在 {note.name} 里有命中 —— 「零真源」前提漂移"
                )
        # 第 1 条：源 xlsx 与两份 note_template 都能命中（否证性对照，防判据只会报 0）
        assert self._xlsx_exact_hits(I_TEMPLATE_DIR / dec["workbook"], source[0]) == [
            "明细表I4-2!A11"
        ]
        for note in (NOTE_TEMPLATE_SOE, NOTE_TEMPLATE_LISTED):
            assert _note_template_labels(note, source[0]), (
                f"CD-8: 源标签在 {note.name} 里 0 命中 —— 第二真源前提失效"
            )
        # 源侧留白：A12 起为空（即源里没有第 2..4 类）
        assert _cells_of(I_TEMPLATE_DIR / dec["workbook"], "明细表I4-2", "A12:A14") == [None] * 3

    def test_cd7_source_labels_are_formulas_pointing_at_the_detail_sheet(
        self, manifest_slice: dict
    ) -> None:
        """CD-7：源模板自己声明「披露行由明细行派生」—— 真读必须是公式串而非字面标签。"""
        dec = next(d for d in self._declarations(manifest_slice) if d["id"] == "CD-7")
        assert dec["source_read_mode"] == "formula"
        got = _cells_of(I_TEMPLATE_DIR / dec["workbook"], dec["sheet"], dec["cells"], formula=True)
        assert got == dec["expected_source_labels"]
        for value in got:
            assert str(value).startswith("='明细表I3-2'!A"), value

    def test_cd6_seed_literal_count_is_locked_both_ways(self, manifest_slice: dict) -> None:
        """CD-6：`可比公司1/2/3` 命中数必须**恰好 3**（多一条 = 扩了写死种子，少一条 = 已改动态但登记未删）。"""
        dec = next(d for d in self._declarations(manifest_slice) if d["id"] == "CD-6")
        assert dec["status"] == "scanned_and_classified_not_a_defect"
        body = _strip_ts_comments((COMPOSABLES / "i2AnalysisModel.ts").read_text(encoding="utf-8"))
        hits = _SEED_COMPANY_LITERAL.findall(body)
        assert len(hits) == 3, f"可比公司N 种子字面量命中 {len(hits)} 处（应为 3）：{hits}"
        got = _extract_impl_labels(body, "defaultPerCapitaPeers", dec["impl_extraction_kind"])
        assert got == dec["impl_labels"]
        assert "rowId: partial?.rowId || _id(" in body.replace("\n", " ") or re.search(
            r"rowId:\s*partial\?\.rowId\s*\|\|\s*_id\(", body
        ), "CD-6 的「行身份不是位置化」前提失效 —— 它就该升级为缺陷"

    def test_summary_status_counts_recompute(self, manifest_slice: dict) -> None:
        section = manifest_slice["classification_row_model_derivation"]
        summary = section["summary"]
        decs = section["declarations"]
        by_status: dict[str, list[str]] = {}
        for dec in decs:
            by_status.setdefault(dec["status"], []).append(dec["id"])
        assert summary["declarations_total"] == len(decs) == 8
        assert sorted(by_status.get("clean", [])) == sorted(summary["clean_ids"])
        assert sorted(by_status.get("defect_registered_not_fixed", [])) == sorted(summary["defect_ids"])
        assert sorted(by_status.get("scanned_and_classified_not_a_defect", [])) == sorted(
            summary["classified_not_defect_ids"]
        )
        # 🔴 4/3/1 而不是初版写的 5/2/1：CD-8 从「否定式 clean」改判为「实体 defect」
        # （守卫的 impl 侧现读把它证伪，见 test_cd8_i4_category_enum_has_an_unsourced_tail）。
        assert len(summary["clean_ids"]) == 4
        assert len(summary["defect_ids"]) == 3
        assert len(summary["classified_not_defect_ids"]) == 1
        assert summary["clean"] == 4 and summary["defect_registered"] == 3

    def test_defect_declarations_are_registered_as_blocking_preconditions(
        self, manifest_slice: dict
    ) -> None:
        known = {bp["id"] for bp in manifest_slice["blocking_preconditions"]}
        for dec in self._declarations(manifest_slice):
            if dec["status"] != "defect_registered_not_fixed":
                assert "registered_as" not in dec or dec.get("registered_as") is None, (
                    f"{dec['id']}: 非缺陷却登记了 BP"
                )
                continue
            bp = dec["registered_as"]
            assert bp in known, f"{dec['id']}: registered_as={bp} 不在 blocking_preconditions 里"

    @staticmethod
    def _xlsx_exact_hits(path: pathlib.Path, needle: str) -> list[str]:
        """在一本工作簿里逐格精确匹配，返回 `sheet!coord` 列表。"""
        import openpyxl

        workbook = openpyxl.load_workbook(path, data_only=False)
        try:
            out: list[str] = []
            for sheet in workbook.sheetnames:
                worksheet = workbook[sheet]
                for row in worksheet.iter_rows():
                    for cell in row:
                        if cell.value is not None and str(cell.value).strip() == needle:
                            out.append(f"{sheet}!{cell.coordinate}")
            return out
        finally:
            workbook.close()


# ════════════════════════════════════════════════════════════════════════════
# 判据五：Property 22 / 23 的静态部分（真分母）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty22StaticStructure:
    """动态列 key 与 label 解耦 —— I 循环的分母是「穷举扫描结果为 0」+ I1 的 `{key}_{seq}` 正例。"""

    def test_label_as_key_hits_are_exactly_zero(
        self, manifest_slice: dict, i_files: list[pathlib.Path]
    ) -> None:
        declared = manifest_slice["dynamic_row_identity"]["hardcoded_scan_result"]["patterns"]
        hits = _label_key_hits(i_files)
        assert len(hits["column_key_is_label"]) == declared["column_key_is_label"] == 0, (
            f"label 当列 key 命中：{hits['column_key_is_label']}"
        )
        assert len(hits["row_cell_key_is_label"]) == declared["row_cell_key_is_label"] == 0, (
            f"row[label] 命中：{hits['row_cell_key_is_label']}"
        )

    def test_i1_disclosure_sync_boundary_keeps_the_stable_key(self) -> None:
        """🔴 H8 恰恰是在附注同步边界上把稳定 key 降级成 label 的。I1 这里保住了 —— 断言它真保住。"""
        body = _strip_ts_comments((COMPOSABLES / "i1DisclosureSyncPayload.ts").read_text(encoding="utf-8"))
        assert "i1CategoryColumnKey" in body, "i1DisclosureSyncPayload 不再调用稳定 key 生成器"
        assert re.search(r"key:\s*i1CatColKey\(", body), "列 key 不再走 i1CatColKey"
        scope = _strip_ts_comments((COMPOSABLES / "i1CategoryScope.ts").read_text(encoding="utf-8"))
        assert re.search(r"return\s*`\$\{slot\.key\}_\$\{slot\.seq\}`", scope), (
            "i1CategoryColumnKey 不再是 `{slot.key}_{slot.seq}` 形态"
        )

    def test_no_hardcoded_blank_rows_or_horizontal_columns(
        self, manifest_slice: dict, i_files: list[pathlib.Path]
    ) -> None:
        declared = manifest_slice["dynamic_row_identity"]["hardcoded_scan_result"]["patterns"]
        blank: list[str] = []
        horizontal: list[str] = []
        for path in i_files:
            body = _strip_ts_comments(path.read_text(encoding="utf-8", errors="replace"))
            rel = path.relative_to(ROOT).as_posix()
            for no, line in enumerate(body.splitlines(), 1):
                if _BLANK_ROWS_FIXED.search(line):
                    blank.append(f"{rel}#L{no}")
                if _HORIZONTAL_COLUMN_LITERAL.search(line):
                    horizontal.append(f"{rel}#L{no}")
        assert len(blank) == declared["blankRows_with_integer_literal"] == 0, blank
        assert len(horizontal) == declared["horizontal_company_column_literals"] == 0, horizontal

    def test_seed_company_literal_count_matches_the_declaration(
        self, manifest_slice: dict, i_files: list[pathlib.Path]
    ) -> None:
        """放宽引号约束后的 3 处（CD-6）—— 双向锁死，多一处少一处都红。"""
        declared = manifest_slice["dynamic_row_identity"]["hardcoded_scan_result"]["patterns"][
            "hardcoded_peer_company_seed_literals"
        ]
        hits: list[str] = []
        for path in i_files:
            body = _strip_ts_comments(path.read_text(encoding="utf-8", errors="replace"))
            rel = path.relative_to(ROOT).as_posix()
            for no, line in enumerate(body.splitlines(), 1):
                if _SEED_COMPANY_LITERAL.search(line):
                    hits.append(f"{rel}#L{no}")
        assert len(hits) == declared == 3, f"种子公司名字面量命中 {hits}（声明 {declared}）"
        assert all("i2AnalysisModel.ts" in h for h in hits), hits


class TestProperty23RowIdentityStaticPrereq:
    """动态行身份不使用下标 —— 静态前提：穷举命中与三族划分必须逐条等值。"""

    def test_every_entry_declares_its_identity_key_and_generator(
        self, manifest_slice: dict
    ) -> None:
        for entry in manifest_slice["independent_entries"]:
            counterpart = entry["html_counterpart"]
            key = counterpart["row_identity_key"]
            ref = counterpart["row_identity_generator_source"]
            path = _resolve_repo(ref)
            assert path.exists(), f"{entry['entry_id']}: 生成点文件不存在 {ref}"
            lines = path.read_text(encoding="utf-8").splitlines()
            line = lines[_line_no_of(ref) - 1]
            expr = _value_expr_after_key(line, key)
            assert expr is not None, (
                f"{entry['entry_id']}: {ref} 那行没有 `{key}:` —— 身份字段名或行号漂移"
            )
            declared_form = counterpart["row_identity_generator_form"]
            assert declared_form in line, (
                f"{entry['entry_id']}: {ref} 那行不含声明的生成式 {declared_form!r}，实际 {line.strip()!r}"
            )
            assert not _POSITIONAL_IDENTITY_TOKEN.search(expr), (
                f"{entry['entry_id']}: primary table 的行身份竟是位置化的：{expr!r}"
            )
            assert counterpart["row_identity_is_positional"] is False
            # module_function 族还要核 helper 定义点与它的形态（generateRowId() 本身不含随机源）
            helper_ref = counterpart.get("row_identity_generator_helper_source")
            if helper_ref is not None:
                assert counterpart["row_identity_generator"] == "module_function"
                helper_path = _resolve_repo(helper_ref)
                helper_line = helper_path.read_text(encoding="utf-8").splitlines()[
                    _line_no_of(helper_ref) - 1
                ]
                assert counterpart["row_identity_generator_helper_form"] in helper_line, (
                    f"{entry['entry_id']}: helper 生成式与 {helper_ref} 那行不符：{helper_line.strip()!r}"
                )
                assert "Math.random" in helper_line and "Date.now" in helper_line
            else:
                assert "Math.random" in expr or "Date.now" in expr, (
                    f"{entry['entry_id']}: 非 helper 族的身份生成式不含随机源：{expr!r}"
                )

    def test_positional_identity_inventory_is_exhaustive_and_partitioned(
        self, manifest_slice: dict, i_files: list[pathlib.Path]
    ) -> None:
        inventory = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        hits = _positional_identity_hits(i_files)
        actual = {f"{rel}#L{no}" for rel, no, _key, _expr in hits}
        declared: set[str] = set()
        for hit in inventory["family_a_pure_index_persisted"]["hits"]:
            declared.add(hit["site"])
        for hit in inventory["family_b_index_as_fallback"]["hits"]:
            declared.add(hit["site"])
        declared.add("audit-platform/frontend/src/components/workpaper/i3/impairment/I3TabRecoverableTest.vue#L686")
        assert actual == declared, (
            f"位置化命中集合漂移：多={sorted(actual - declared)} 少={sorted(declared - actual)}"
        )
        assert len(actual) == inventory["total_hits"] == 6
        assert inventory["family_a_pure_index_persisted"]["count"] == 1
        assert inventory["family_b_index_as_fallback"]["count"] == 4

    def test_family_a_hit_writes_to_the_declared_persisted_key(self, manifest_slice: dict) -> None:
        """family_a 的那条必须真落库 —— 否则它不该是最严重的一族。"""
        hit = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"][
            "family_a_pure_index_persisted"
        ]["hits"][0]
        path = _resolve_repo(hit["site"])
        body = path.read_text(encoding="utf-8")
        line = body.splitlines()[_line_no_of(hit["site"]) - 1]
        assert "cgu-${i}" in line, f"family_a 的表达式漂移：{line.strip()!r}"
        assert "_persistSection('cgu_allocation')" in body, "落库调用不见了 —— 该条已非持久化身份"
        assert re.search(
            r"options\?\.onSave\?\.\(\s*`\$\{prefix\}-\$\{sectionKey\}-rows`", body
        ), "_persistSection 的键拼接形态漂移"
        for const, value in (("ITEM_PREFIX_LISTED", "I3-disc-listed"), ("ITEM_PREFIX_SOE", "I3-disc-soe")):
            assert re.search(
                r"\b" + const + r"\s*=\s*['\"]" + re.escape(value) + r"['\"]", body
            ), f"{const} 的值漂移 —— BP-6 的 writes_to_key 声明失效"

    def test_display_sequence_sites_are_not_flagged(
        self, manifest_slice: dict, i_files: list[pathlib.Path]
    ) -> None:
        """🔴 反向自检：20 处展示序号**不得**被位置化判据点名（否则口径回到「整行判」）。"""
        inventory = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        family_c = inventory["family_c_display_ordinal_must_not_be_flagged"]
        seq_sites: list[str] = []
        for path in i_files:
            rel = path.relative_to(ROOT).as_posix()
            for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if _DISPLAY_SEQ_SITE.search(line):
                    seq_sites.append(f"{rel}#L{no}")
        assert len(seq_sites) == family_c["count"] == 20, (
            f"展示序号站点 {len(seq_sites)} 处（声明 {family_c['count']}）：{seq_sites}"
        )
        flagged = {f"{rel}#L{no}" for rel, no, _k, _e in _positional_identity_hits(i_files)}
        overlap = sorted(set(seq_sites) & flagged)
        assert not overlap, f"展示序号被位置化判据误报：{overlap}"

    def test_four_table_seed_family_is_really_absent(
        self, manifest_slice: dict, i_files: list[pathlib.Path]
    ) -> None:
        """🔴 family_d 的 0 是判据的一部分：H 循环有 3 条，I 循环 0 条。"""
        declared = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"][
            "family_d_four_table_seed_absent"
        ]
        hits: list[str] = []
        for path in i_files:
            rel = path.relative_to(ROOT).as_posix()
            for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if _FOUR_TABLE_SEED_POSITIONAL.search(line):
                    hits.append(f"{rel}#L{no}")
        assert len(hits) == declared["count"] == 0, f"竟出现四表种子位置化身份：{hits}"

    def test_dynamic_row_identity_tables_cover_every_entry(self, manifest_slice: dict) -> None:
        section = manifest_slice["dynamic_row_identity"]
        tables = section["tables"]
        covered = {t["entry_id"] for t in tables}
        assert covered == {e["entry_id"] for e in manifest_slice["independent_entries"]}
        assert len(tables) == len(covered) == 6
        forbidden = set(section["forbidden_identity_kinds"])
        for table in tables:
            identity = table["row_identity"]
            assert identity["kind"] not in forbidden, f"{table['table_key']}: kind 落在禁用集合里"
            assert _resolve_repo(identity["source_ref"]).exists()
            entry = next(
                e for e in manifest_slice["independent_entries"] if e["entry_id"] == table["entry_id"]
            )
            assert table["table_key"] == entry["html_counterpart"]["primary_table"]["item_id"]
            assert identity["identity_field"] == entry["html_counterpart"]["row_identity_key"]


# ════════════════════════════════════════════════════════════════════════════
# 判据六：孤儿 composable 与「注释伪消费边」（BP-5 / ID-3）
# ════════════════════════════════════════════════════════════════════════════
class TestOrphanComposablesAndPseudoConsumers:
    def test_declared_dual_mode_consumers_match_the_source(self, manifest_slice: dict) -> None:
        """两侧都断言：声明的生产/测试消费方真有，且没有第三方。"""
        for entry in manifest_slice["independent_entries"]:
            legacy = entry["legacy_dual_mode"]
            module = _resolve_repo(legacy["module"])
            assert module.exists(), f"{entry['entry_id']}: legacy composable 不存在"
            assert len(module.read_text(encoding="utf-8").splitlines()) == legacy["lines"], (
                f"{entry['entry_id']}: {module.name} 行数与声明不符"
            )
            assert (
                "useWorkpaperEntryDualMode" not in module.read_text(encoding="utf-8")
            ) == (legacy["wraps_shared_base"] is False)
            real = set(_import_specifier_consumers(module.stem))
            declared = set(legacy["consumers"]) | set(legacy.get("test_only_consumers") or [])
            assert real == declared, (
                f"{entry['entry_id']}: 真 import 边 {sorted(real)} != 声明 {sorted(declared)}"
            )
            assert legacy["host_consumes_it"] is True
            assert any(entry["host"] in c for c in legacy["consumers"])
            assert legacy["localStorage_prefix"] in module.read_text(encoding="utf-8")

    def test_mention_only_edges_are_not_import_edges(self, manifest_slice: dict) -> None:
        """🔴 4 处注释提及：两侧都验（符号名命中 > 0 且 import 边命中 == 0）。"""
        plan_edges = _load(DELETION_PLAN_PATH)["comment_only_pseudo_consumer_edges"]["edges"]
        assert len(plan_edges) == 4
        for edge in plan_edges:
            module = edge["mentioned_module"]
            path = _resolve_repo(edge["mentioned_in"])
            assert path.exists(), f"{edge['mentioned_in']} 不存在"
            source = path.read_text(encoding="utf-8")
            assert module in source, f"{path.name}: 竟没有提到 {module} —— 声明过期"
            assert not re.search(
                r"['\"][^'\"]*/" + re.escape(module) + r"(?:\.ts)?['\"]", source
            ), f"{path.name}: 竟有指向 {module} 的 import 路径字面量 —— 它不是「仅提及」"
            assert edge["is_import_edge"] is False
            line = source.splitlines()[_line_no_of(edge["mentioned_in"]) - 1]
            assert edge["text"].strip() in line.strip(), f"{edge['mentioned_in']}: 注释原文漂移"

    def test_declared_orphan_formdata_composables_really_have_no_consumer(
        self, manifest_slice: dict
    ) -> None:
        diffs = manifest_slice["i_cycle_form_differences"]["differences"]
        id3 = next(d for d in diffs if d["id"] == "ID-3")
        for orphan in id3["orphan_modules"]:
            module = _resolve_repo(orphan["module"])
            assert module.exists(), f"{orphan['module']} 不存在"
            source = module.read_text(encoding="utf-8")
            assert len(source.splitlines()) == orphan["lines"]
            real = _import_specifier_consumers(module.stem)
            # 🔴 两侧都断言：不能只写 `real == []`（那样把声明改成「有消费方」不会打红 ——
            # 变异 M36 首轮就判 GREEN 抓出了这个守卫缺陷）。判据是「声明集合 == 现算集合」，
            # 于是「声称零消费的真零」与「声称有消费方就必须真有」两个方向同时锁死。
            declared = list(orphan["production_consumers"]) + list(orphan["test_only_consumers"])
            assert sorted(real) == sorted(declared), (
                f"{module.name}: 真 import 边 {sorted(real)} != 声明 {sorted(declared)}"
            )
            assert declared == [], (
                f"{module.name}: 被登记为孤儿却声明了消费方 {declared} —— "
                "若它真有消费方，应从 orphan_modules 移到 non_orphan_formdata_modules"
            )
            mentions = _symbol_name_mentions(module.stem)
            assert sorted(mentions) == sorted(orphan["mention_only"]), (
                f"{module.name}: 仅提及集合漂移 {mentions}"
            )
            assert orphan["has_checklist_put"] is bool(
                re.search(r"\.put\(\s*`[^`]*checklist-responses`", source)
            )
            assert orphan["has_checklist_get"] is bool(
                re.search(r"\.get\(\s*`[^`]*checklist-responses`", source)
            )
            assert orphan["has_tb_writeback"] is ("trial-balance/writeback" in source)

    def test_non_orphan_formdata_composables_are_not_registered_as_orphans(
        self, manifest_slice: dict
    ) -> None:
        """另一侧：声称有消费方的 4 个真有，且条数相等（防「把活的记成孤儿」）。"""
        diffs = manifest_slice["i_cycle_form_differences"]["differences"]
        id3 = next(d for d in diffs if d["id"] == "ID-3")
        orphan_stems = {_resolve_repo(o["module"]).stem for o in id3["orphan_modules"]}
        for item in id3["non_orphan_formdata_modules"]:
            stem = pathlib.Path(item["module"]).stem
            assert stem not in orphan_stems, f"{stem} 同时被登记为孤儿与非孤儿"
            real = _import_specifier_consumers(stem)
            production = [c for c in real if "__tests__" not in c]
            assert len(production) == item["production_consumers"], (
                f"{stem}: 生产消费方 {len(production)} 个，声明 {item['production_consumers']} 个：{production}"
            )

    def test_shared_base_is_not_consumed_by_the_i_cycle(self, deletion_plan: dict) -> None:
        preserved = deletion_plan["shared_base_preserved"]
        assert _resolve_repo(preserved["file"]).exists()
        for n in range(1, 7):
            module = COMPOSABLES / f"useI{n}DualMode.ts"
            source = module.read_text(encoding="utf-8")
            assert not re.search(
                r"['\"][^'\"]*/useWorkpaperEntryDualMode(?:\.ts)?['\"]", source
            ), f"{module.name} 竟 import 了共享基类 —— shared_base_preserved 的前提失效"

    def test_no_host_inlined_second_implementation(self, deletion_plan: dict) -> None:
        """🔴 「没有」也要落成判据：H 循环有 4 条，I 循环 0 条。"""
        section = deletion_plan["host_inlined_second_implementation"]
        assert section["result"] == "none"
        assert section["hosts"] if False else True  # 该键在 result=none 时不必存在
        for name in _host_names():
            source = (WP_COMPONENTS / name).read_text(encoding="utf-8")
            assert not re.search(r"localStorage\.(?:get|set)Item\(\s*['\"`][^'\"`]*dual-mode", source), (
                f"{name}: 宿主直接读写 dual-mode localStorage ⇒ 内联了第二份实现"
            )
            assert re.search(r"const\s+dualMode\s*=\s*useI[1-6]DualMode\(", source), (
                f"{name}: 宿主没有从自己的 composable 取 dualMode"
            )


# ════════════════════════════════════════════════════════════════════════════
# 判据七：Property 20 / 21 —— 分母为空，**不宣称通过**
# ════════════════════════════════════════════════════════════════════════════
class TestProperty20And21NotClaimed:
    """只断言两件可复核的事：① 前提成立（本 slice contract 数 = 0）；② 承载者存在。

    🔴 前提一旦不成立（有人给 I entry 发了契约），这里立刻打红，要求在此补齐字段级判据。
    """

    def test_no_slice_entry_has_a_contract(self, manifest_slice: dict) -> None:
        slice_ids = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        found: list[str] = []
        for path in sorted(CONTRACT_DIR.glob("*.json")):
            doc = _load(path)
            owner = (doc.get("review") or {}).get("entry_id")
            if owner in slice_ids:
                found.append(f"{path.name} → {owner}")
        assert not found, f"本 slice 竟已有 contract：{found} —— 需在此补字段级判据"

    def test_contract_review_status_is_top_level_in_every_contract(self) -> None:
        """前五轮已定论：`review_status` 在顶层。这条锁住那个结论不被悄悄改成嵌套。"""
        for path in sorted(CONTRACT_DIR.glob("*.json")):
            if path.name.startswith("_example"):
                continue
            doc = _load(path)
            assert "review_status" in doc, f"{path.name}: review_status 不在顶层"

    def test_property_21_carrier_exists(self) -> None:
        carrier = BACKEND / "tests" / "workpaper_sync" / "test_task13_contract_registry.py"
        assert carrier.exists(), "Property 21 的字段级判据承载者不存在"

    def test_no_slice_entry_has_a_registered_adapter(
        self, manifest_slice: dict, full_manifest: dict
    ) -> None:
        by_id = {e["entry_id"]: e for e in full_manifest["entries"]}
        for entry in manifest_slice["independent_entries"]:
            assert by_id[entry["entry_id"]]["adapter_id"] is None
            assert entry["adapter_id"] is None

    def test_registry_delivered_contracts_contain_no_slice_entry(
        self, manifest_slice: dict
    ) -> None:
        registry = REGISTRY.read_text(encoding="utf-8")
        for entry in manifest_slice["independent_entries"]:
            assert entry["entry_id"] not in registry, (
                f"{entry['entry_id']} 出现在 adapters/registry.py 里"
            )

    def test_no_col_placeholder_in_the_classification_constants(
        self, manifest_slice: dict
    ) -> None:
        """Property 20 的**非空同型分母**：分类常量里不得出现 `col_[a-z]+` 无语义占位。"""
        section = manifest_slice["classification_row_model_derivation"]
        checked = 0
        for dec in section["declarations"]:
            if dec["impl_constant"] is None:
                continue
            body = _strip_ts_comments(_resolve_repo(dec["impl_module"]).read_text(encoding="utf-8"))
            hits = re.findall(r"['\"]col_[a-z]+['\"]", body)
            assert not hits, f"{dec['id']}: 分类模块里有无语义占位 {hits}"
            checked += 1
        assert checked == 6, f"同型分母只核了 {checked} 条（应为 6）"

    def test_property_denominator_block_declares_what_is_not_claimed(
        self, manifest_slice: dict
    ) -> None:
        denominators = manifest_slice["property_denominators"]
        assert denominators["property_20"]["not_claimed_passing"] is True
        assert denominators["property_20"]["not_claimed_passing_part"]
        assert denominators["property_21_22_23_not_claimed"]["not_claimed_passing"] is True
        assert denominators["property_28"]["not_claimed_passing"] is False
        assert denominators["property_28"]["not_claimed_passing_part"]
        assert denominators["property_69"]["not_claimed_passing"] is False
        assert denominators["property_69"]["not_claimed_passing_part"]
        assert denominators["property_70"]["not_claimed_passing"] is False
        assert manifest_slice["properties_verified"] == [20, 28, 69, 70]


# ════════════════════════════════════════════════════════════════════════════
# 判据八：Property 28 —— template identity 漂移 fail closed（真分母）
# ════════════════════════════════════════════════════════════════════════════
class TestProperty28DefinitionDriftFailClosed:
    def test_authoritative_template_digests_recompute(self, manifest_slice: dict) -> None:
        templates = manifest_slice["authoritative_templates"]
        root = ROOT / templates["root"]
        assert root.is_dir()
        for record in templates["files"]:
            path = root / record["name"]
            assert path.exists(), f"缺模板 {record['name']}"
            assert path.stat().st_size == record["size"], f"{record['name']}: size 漂移"
            assert _sha256_of(path) == record["sha256"], f"{record['name']}: sha256 漂移"
            assert len(_sheet_names(path)) == record["sheet_count"], (
                f"{record['name']}: sheet 数漂移"
            )
            assert record["primary_detail_sheet"] in _sheet_names(path)
            rel = (path.relative_to(TEMPLATE_DIR)).as_posix()
            assert (rel in _indexed_relpaths()) is record["in_runtime_index"]

    def test_registered_file_set_equals_the_disk_set(self, manifest_slice: dict) -> None:
        templates = manifest_slice["authoritative_templates"]
        root = ROOT / templates["root"]
        disk = {p.name for p in root.iterdir() if p.is_file() and not p.name.startswith("~$")}
        declared = {f["name"] for f in templates["files"]}
        assert disk == declared, f"登记集合与磁盘不符：多={sorted(declared - disk)} 少={sorted(disk - declared)}"

    def test_lock_files_are_really_absent(self, manifest_slice: dict) -> None:
        root = ROOT / manifest_slice["authoritative_templates"]["root"]
        locks = [p.name for p in root.iterdir() if p.name.startswith("~$")]
        assert not locks, f"权威目录里有 Office 锁文件（用户可能开着 WPS 且有未保存改动）：{locks}"

    def test_reference_copy_status_is_honest(self, manifest_slice: dict) -> None:
        """参考副本不在工作树时如实登记 absent，不当豁免。"""
        status = manifest_slice["authoritative_templates"]["reference_copy_status"]
        reference = ROOT / "基础数据" / "致同通用审计程序及底稿模板（2025年修订）"
        if reference.exists():
            assert status != "absent_in_worktree", (
                "参考副本回到工作树了 —— 应改成双处比对并更新本字段"
            )
        else:
            assert status == "absent_in_worktree", f"参考副本不存在但登记为 {status!r}"

    def test_template_owner_mapping_is_a_bijection(self, manifest_slice: dict) -> None:
        """🔴 I 循环是**双射**（6 文件 ↔ 6 entry，无 null 项）—— 比 F/G/H 更严。"""
        templates = manifest_slice["authoritative_templates"]["files"]
        owners = [f["belongs_to_entry"] for f in templates]
        assert all(o is not None for o in owners), "有 belongs_to_entry 为 null 的条目"
        assert len(owners) == len(set(owners)) == 6, "belongs_to_entry 非单射"
        assert set(owners) == {e["entry_id"] for e in manifest_slice["independent_entries"]}, (
            "belongs_to_entry 非满射"
        )
        for entry in manifest_slice["independent_entries"]:
            record = next(f for f in templates if f["belongs_to_entry"] == entry["entry_id"])
            assert entry["template_ref"].endswith(record["name"])

    def test_template_resolution_audit_recomputes(self, manifest_slice: dict) -> None:
        """31 条 wp_code 现跑 wp_template_finder 并与冻结结果等值比对。"""
        import sys

        if str(BACKEND) not in sys.path:
            sys.path.insert(0, str(BACKEND))
        from app.services.wp_template_finder import (  # type: ignore[import-not-found]
            find_template_file,
            find_template_file_any,
        )

        audit = manifest_slice["template_resolution_audit"]
        assert audit["result"] == "clean"
        for record in audit["measured"]:
            code = record["wp_code"]
            expected = record["resolved"]
            for func in (find_template_file, find_template_file_any):
                got = func(code)
                got_name = pathlib.Path(got).name if got else None
                assert got_name == expected, (
                    f"{code}: {func.__name__} 返回 {got_name!r}，冻结值 {expected!r}"
                )

    def test_program_table_and_i0_codes_resolve_to_none(self) -> None:
        """🔴 否定式判据：`I{n}A` 是册内 sheet、`I0` 册不存在，两者都必须解析成 None。"""
        import sys

        if str(BACKEND) not in sys.path:
            sys.path.insert(0, str(BACKEND))
        from app.services.wp_template_finder import (  # type: ignore[import-not-found]
            find_template_file,
            find_template_file_any,
        )

        for code in ("I1A", "I2A", "I3A", "I4A", "I5A", "I6A", "I0"):
            for func in (find_template_file, find_template_file_any):
                got = func(code)
                assert got is None, f"{code}: {func.__name__} 竟解析出 {got!r}（应为 None）"

    def test_bundle_layer_drift_is_not_claimed(self, manifest_slice: dict) -> None:
        """bundle / instrumentation / contract / authority model 四层分母为空 ⇒ 不宣称通过。"""
        part = manifest_slice["property_denominators"]["property_28"]["not_claimed_passing_part"]
        for token in ("bundle", "instrumentation", "contract", "authority model"):
            assert token in part, f"property_28 的未宣称部分没提到 {token}"
        for entry in manifest_slice["independent_entries"]:
            assert entry["definition_bundle"] is None
            assert entry["instrumentation_candidate"] is None
            assert entry["authority_model"] is None


# ════════════════════════════════════════════════════════════════════════════
# 判据九：Property 69 —— evidence 负向蕴含 + 计数现算
# ════════════════════════════════════════════════════════════════════════════
class TestProperty69EvidenceAndCounters:
    def test_unverifiable_entries_carry_non_empty_reasons(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            evidence = entry["evidence"]
            for key in (
                "browser_case",
                "contract_test",
                "sync_test_run_id",
                "required_scenario_set_digest",
                "verification_state",
            ):
                assert key in evidence, f"{entry['entry_id']}: evidence 缺 {key}"
            if evidence["verification_state"] == "UNVERIFIABLE":
                reasons = evidence.get("unverifiable_reasons")
                assert isinstance(reasons, list) and reasons, f"{entry['entry_id']}: SR-7"
            else:
                assert evidence["sync_test_run_id"], f"{entry['entry_id']}: 声称已验收却无 run id"
                assert evidence["required_scenario_set_digest"]

    def test_contract_test_points_at_this_guard(self, manifest_slice: dict) -> None:
        for entry in manifest_slice["independent_entries"]:
            ref = entry["evidence"]["contract_test"]
            assert ref == "backend/tests/workpaper_sync/test_task51_i_cycle_migration.py"
            assert _resolve_repo(ref).exists()
            assert _resolve_repo(entry["dom_guard_ref"].split("::")[0]).exists()

    def test_summary_counters_recompute_from_the_entries(self, manifest_slice: dict) -> None:
        entries = manifest_slice["independent_entries"]
        summary = manifest_slice["honest_adjudication_summary"]
        assert summary["total_independent"] == len(entries) == 6
        assert manifest_slice["slice_scope"]["independent_entry_count"] == len(entries)
        for cap in CAPABILITY_ENUM:
            assert summary[f"adjudicated_as_{cap}"] == sum(
                1 for e in entries if e["capability"] == cap
            )
        pending = sum(1 for e in entries if e["capability"] is None)
        assert summary["capability_verdict_pending"] == pending
        assert summary["slice_counters"]["unadjudicated"] == pending
        assert summary["html_counterpart_exists"] == sum(
            1 for e in entries if e["html_counterpart_verdict"] == "exists"
        )
        assert summary["html_counterpart_none"] == sum(
            1 for e in entries if e["html_counterpart_verdict"] == "none"
        )
        assert summary["entries_left_unverifiable"] == sum(
            1 for e in entries if e["evidence"]["verification_state"] == "UNVERIFIABLE"
        )
        assert summary["entries_with_host_inline_write_carrier"] == sum(
            1 for e in entries if e["html_counterpart"]["write_carrier"] == "host_inline"
        )
        assert summary["entries_with_formdata_composable_write_carrier"] == sum(
            1 for e in entries if e["html_counterpart"]["write_carrier"] == "formdata_composable"
        )
        assert summary["authoritative_template_files"] == len(
            manifest_slice["authoritative_templates"]["files"]
        )
        assert summary["parent_duplicate_children"] == 0
        assert summary["pilot_contract_published"] == 0
        assert summary["finalized_published_representations"] == 0

    def test_derived_counters_recompute_from_their_own_sections(
        self, manifest_slice: dict
    ) -> None:
        summary = manifest_slice["honest_adjudication_summary"]
        section = manifest_slice["classification_row_model_derivation"]
        inventory = manifest_slice["dynamic_row_identity"]["positional_identity_inventory"]
        diffs = manifest_slice["i_cycle_form_differences"]["differences"]
        id3 = next(d for d in diffs if d["id"] == "ID-3")
        id5 = next(d for d in diffs if d["id"] == "ID-5")
        assert summary["classification_declarations_total"] == len(section["declarations"])
        assert summary["classification_declarations_clean"] == len(section["summary"]["clean_ids"])
        assert summary["classification_declarations_defect"] == len(section["summary"]["defect_ids"])
        assert summary["classification_declarations_classified_not_defect"] == len(
            section["summary"]["classified_not_defect_ids"]
        )
        assert summary["positional_identity_hits_total"] == inventory["total_hits"]
        assert summary["entries_with_orphan_production_formdata_composable"] == len(
            id3["orphan_modules"]
        )
        assert summary["entries_missing_segmented_second_level_gate"] == sum(
            1 for meta in id5["gates"].values() if meta["segmented_second_level_gate"] is None
        )
        assert summary["entries_with_source_derived_classification_verified"] == len(
            section["summary"]["entries_with_source_derived_classification"]
        )
        assert summary["entries_with_no_impl_constant_at_all"] == len(
            section["summary"]["entries_with_no_impl_constant_at_all"]
        )
        assert summary["entries_with_impl_constant_declarations"] == len(
            section["summary"]["entries_with_impl_constant_declarations"]
        )
        # 🔴 两个清单必须互补且覆盖全部 6 条 entry（否则「有/无常量」会漏 entry 或双记）
        with_const = set(section["summary"]["entries_with_impl_constant_declarations"])
        without_const = set(section["summary"]["entries_with_no_impl_constant_at_all"])
        assert not (with_const & without_const), sorted(with_const & without_const)
        assert with_const | without_const == {
            e["entry_id"] for e in manifest_slice["independent_entries"]
        }
        # 「有分类常量」必须与 declarations 里 impl_constant 非空的 entry 集合一致
        declared_const_entries = {
            d["entry_id"] for d in section["declarations"] if d["impl_constant"] is not None
        }
        assert declared_const_entries == with_const, (
            f"declarations 现算 {sorted(declared_const_entries)} != 清单 {sorted(with_const)}"
        )
        mismatch_entries = {
            d["entry_id"]
            for d in section["declarations"]
            if d["status"] == "defect_registered_not_fixed"
        }
        assert summary["entries_with_classification_source_mismatch"] == len(mismatch_entries) == 3
        assert summary["entries_whose_host_does_a_checklist_get"] == 0
        assert "counting_notes" in summary and len(summary["counting_notes"]) >= 3

    def test_slice_counters_are_all_zero_except_unadjudicated(self, manifest_slice: dict) -> None:
        counters = manifest_slice["honest_adjudication_summary"]["slice_counters"]
        assert counters["unadjudicated"] == 6
        assert counters["fake_bidirectional_claimed_verified"] == 0
        assert counters["bidirectional_unverified"] == 0
        assert counters["stale_evidence"] == 0
        assert "不得解读为" in counters["note"], "四个 0 的语义说明不见了"


# ════════════════════════════════════════════════════════════════════════════
# 判据十：Property 70 —— 跨 entry 隔离
# ════════════════════════════════════════════════════════════════════════════
class TestProperty70CrossEntryIsolation:
    def test_six_slices_are_pairwise_disjoint(self, manifest_slice: dict) -> None:
        mine = {e["entry_id"] for e in manifest_slice["independent_entries"]}
        for name, path in SIBLING_SLICE_PATHS.items():
            other = {e["entry_id"] for e in _load(path)["independent_entries"]}
            overlap = mine & other
            assert not overlap, f"I slice 与 {name} slice 交集非空：{sorted(overlap)}"

    def test_sibling_slices_declared_match_the_disk(self, manifest_slice: dict) -> None:
        declared = set(manifest_slice["sibling_slices"])
        actual = {p.relative_to(ROOT).as_posix() for p in SIBLING_SLICE_PATHS.values()}
        assert declared == actual, f"sibling_slices 声明与实际不符：{declared ^ actual}"

    def test_cross_entry_isolation_assertions_are_present(self, manifest_slice: dict) -> None:
        isolation = manifest_slice["cross_entry_isolation"]
        assert isolation["rule"]
        assert isinstance(isolation["assertions"], list) and len(isolation["assertions"]) >= 7

    def test_each_declaration_binds_a_single_entry_and_workbook(self, manifest_slice: dict) -> None:
        """declaration 的 workbook 必须属于它自己那条 entry 的 template_ref（唯一例外是 CD-4 的否证引用）。"""
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        for dec in manifest_slice["classification_row_model_derivation"]["declarations"]:
            entry = by_id[dec["entry_id"]]
            assert entry["template_ref"].endswith(dec["workbook"]), (
                f"{dec['id']}: workbook {dec['workbook']!r} 不属 {dec['entry_id']} 的 template_ref"
            )

    def test_deletion_plan_paths_are_globally_unique_and_disjoint(self, deletion_plan: dict) -> None:
        files: list[str] = []
        ids: list[str] = []
        for entry in deletion_plan["entries"]:
            ids.append(entry["entry_id"])
            files += [f["file"] for f in entry["legacy_composables_to_delete"]]
        assert len(ids) == len(set(ids)) == 6
        assert len(files) == len(set(files)) == 6
        for name, path in SIBLING_SLICE_PATHS.items():
            sibling_plan = DATA / f"workpaper_sync_{name.lower()}_cycle_deletion_plan.json"
            assert sibling_plan.exists(), f"缺兄弟 deletion plan {sibling_plan.name}"
            other_files = {
                f["file"]
                for e in _load(sibling_plan)["entries"]
                for f in e.get("legacy_composables_to_delete", [])
            }
            overlap = set(files) & other_files
            assert not overlap, f"与 {name} 的 deletion plan 有共同待删文件：{sorted(overlap)}"


# ════════════════════════════════════════════════════════════════════════════
# 判据十一：AC 1.4 的 UI 义务（step 11 / BP-10）
# ════════════════════════════════════════════════════════════════════════════
class TestAc14HonestModeVisibility:
    def test_notice_single_source_exists_and_is_not_duplicated(self) -> None:
        assert NOTICE_MODULE.exists() and NOTICE_COMPONENT.exists()
        duplicates = [
            p.relative_to(ROOT).as_posix()
            for p in WP_COMPONENTS.rglob("*EntrySyncCapabilityNotice*")
            if p.is_file() and p != NOTICE_COMPONENT
        ]
        assert not duplicates, f"文案/组件被抄了第二份：{duplicates}"

    def test_every_entry_declares_a_unique_resolvable_toolbar_anchor(
        self, manifest_slice: dict
    ) -> None:
        anchors = set()
        for entry in manifest_slice["independent_entries"]:
            anchor = _gate_anchor(entry)
            assert anchor not in anchors, f"工具栏锚点重复：{anchor}"
            anchors.add(anchor)
            template = _vue_template((WP_COMPONENTS / entry["host"]).read_text(encoding="utf-8"))
            block = _toolbar_block(template, anchor)
            assert "el-segmented" in block, f"{entry['entry_id']}: 工具栏区块里没有模式切换器"

    def test_second_level_gate_presence_matches_the_declaration(self, manifest_slice: dict) -> None:
        """🔴 I2 声明「无二级门控」，其余 5 条声明「有」—— 任一条翻转即红。

        写死「全 slice 都有二级门控」会让判据在 I2 上静默恒真，恰好漏掉最严重的一条。
        """
        gates = next(
            d for d in manifest_slice["i_cycle_form_differences"]["differences"] if d["id"] == "ID-5"
        )["gates"]
        assert set(gates) == {e["entry_id"] for e in manifest_slice["independent_entries"]}
        missing = 0
        for entry in manifest_slice["independent_entries"]:
            meta = gates[entry["entry_id"]]
            template = _vue_template((WP_COMPONENTS / entry["host"]).read_text(encoding="utf-8"))
            block = _toolbar_block(template, _gate_anchor(entry))
            declared_gate = meta["segmented_second_level_gate"]
            has_gate = bool(re.search(r"v-if=\"dualMode\.isOoAvailable\.value\"", block))
            if declared_gate is None:
                missing += 1
                assert not has_gate, (
                    f"{entry['entry_id']}: 声明无二级门控但模板里有 —— 声明已过期（BP-10 应可解除）"
                )
                assert meta["fallback_tag"] is False
                assert "仅结构化视图" not in block
            else:
                assert has_gate, f"{entry['entry_id']}: 声明有二级门控 {declared_gate!r} 但模板里没有"
                assert meta["fallback_tag"] is True
                assert "仅结构化视图" in block, f"{entry['entry_id']}: 缺 OO 不可用兜底 tag"
            first_gate = meta["toolbar_gate"]
            assert first_gate in template, f"{entry['entry_id']}: 一级门控表达式 {first_gate!r} 不在模板里"
        assert missing == 1, f"缺二级门控的 entry 数为 {missing}（应为 1，即 I2）"

    def test_extra_unrelated_segmented_sites_are_declared_and_outside_the_toolbar(
        self, manifest_slice: dict
    ) -> None:
        """I1#L171 / I4#L142 的 el-segmented 是 Tab 内部分段 —— 必须登记且不在工具栏区块内。

        🔴 没有这条，「全文件 grep el-segmented」的错口径会被当成合理判据。
        """
        gates = next(
            d for d in manifest_slice["i_cycle_form_differences"]["differences"] if d["id"] == "ID-5"
        )["gates"]
        for entry in manifest_slice["independent_entries"]:
            meta = gates[entry["entry_id"]]
            source = (WP_COMPONENTS / entry["host"]).read_text(encoding="utf-8")
            lines = source.splitlines()
            all_sites = [i + 1 for i, ln in enumerate(lines) if "<el-segmented" in ln]
            block = _toolbar_block(_vue_template(source), _gate_anchor(entry))
            in_toolbar = block.count("<el-segmented")
            assert in_toolbar == 1, f"{entry['entry_id']}: 工具栏区块里有 {in_toolbar} 个 el-segmented"
            extra = meta["extra_unrelated_segmented_at"]
            if extra is None:
                assert len(all_sites) == 1, (
                    f"{entry['entry_id']}: 声明无额外 el-segmented 但全文件有 {all_sites}"
                )
            else:
                assert len(all_sites) == 2, (
                    f"{entry['entry_id']}: 声明有额外 el-segmented 但全文件有 {all_sites}"
                )
                assert f"L{all_sites[1]}" == extra, (
                    f"{entry['entry_id']}: 额外站点行号漂移 {all_sites[1]} vs 声明 {extra}"
                )

    def test_bp10_is_registered_because_no_host_mounts_the_notice(
        self, manifest_slice: dict
    ) -> None:
        """AC 1.4 的义务未兑现 —— 断言「未挂载」这个实况 + 它已登记为 BP-10。

        🔴 这不是把缺陷说成通过：判据锁的是「登记与实况一致」。哪天真挂上了，这条会打红，
        提示作者来解除 BP-10（两个方向都锁死）。
        """
        registered = {bp["id"] for bp in manifest_slice["blocking_preconditions"]}
        assert "BP-10" in registered
        for entry in manifest_slice["independent_entries"]:
            source = (WP_COMPONENTS / entry["host"]).read_text(encoding="utf-8")
            assert NOTICE_COMPONENT_NAME not in source, (
                f"{entry['entry_id']}: 宿主已挂 {NOTICE_COMPONENT_NAME} —— BP-10 可以解除了，"
                "请把它从 blocking_preconditions 移除并改这条判据"
            )
            assert "workpaperEntrySyncNotice" not in source
            for ref in entry["ui_gate_source_refs"]:
                assert _resolve_repo(ref).exists(), f"{entry['entry_id']}: ui_gate_source_ref 不存在 {ref}"


# ════════════════════════════════════════════════════════════════════════════
# 判据十二：deletion plan 与 slice 同源
# ════════════════════════════════════════════════════════════════════════════
class TestDeletionPlanConsistency:
    def test_plan_entries_mirror_the_slice_adjudication(
        self, manifest_slice: dict, deletion_plan: dict
    ) -> None:
        by_id = {e["entry_id"]: e for e in manifest_slice["independent_entries"]}
        assert {e["entry_id"] for e in deletion_plan["entries"]} == set(by_id)
        for plan_entry in deletion_plan["entries"]:
            entry = by_id[plan_entry["entry_id"]]
            assert plan_entry["capability_adjudication"] == entry["capability"]
            assert plan_entry["capability_verdict_stage"] == entry["capability_verdict_stage"]
            assert plan_entry["capability_target"] == entry["capability_target"]
            assert plan_entry["html_counterpart_verdict"] == entry["html_counterpart_verdict"]
            assert plan_entry["wp_code_pattern"] == entry["wp_code_pattern"]
            assert plan_entry["host_component"] == entry["host_path"]
            assert plan_entry["localStorage_prefix"] == entry["legacy_dual_mode"]["localStorage_prefix"]
            for ref in plan_entry["html_counterpart_source_refs"]:
                assert _resolve_repo(ref).exists(), f"{plan_entry['entry_id']}: {ref} 不存在"

    def test_plan_reason_is_not_circular(self, deletion_plan: dict, paradigm: dict) -> None:
        ap1 = next(
            ap for ap in paradigm["adjudication_criteria"]["anti_patterns"] if ap["id"] == "AP-1"
        )
        markers = [str(m).lower() for m in ap1["circular_reason_markers"]]
        for plan_entry in deletion_plan["entries"]:
            reason = str(plan_entry["adjudication_reason"]).lower()
            hit = [m for m in markers if m in reason]
            if hit:
                assert "对端" in reason or "html_counterpart_verdict" in reason, (
                    f"{plan_entry['entry_id']}: 清册理由循环论证 {hit}"
                )

    def test_plan_counters_recompute(self, deletion_plan: dict) -> None:
        entries = deletion_plan["entries"]
        counters = deletion_plan["counters"]
        assert counters["entries"] == len(entries)
        assert counters["composables_to_delete"] == sum(
            len(e["legacy_composables_to_delete"]) for e in entries
        )
        assert counters["composables_preserved"] == sum(
            len(e.get("legacy_composables_preserved") or []) for e in entries
        )
        assert counters["test_files_requiring_sync_change"] == sum(
            len(f.get("test_only_consumers") or [])
            for e in entries
            for f in e["legacy_composables_to_delete"]
        )
        assert counters["entries_with_extra_ui_action_required"] == sum(
            1 for e in entries if "extra_ui_action_required" in e
        )
        assert counters["entries_with_must_fix_before_wiring"] == sum(
            1 for e in entries if "must_fix_before_wiring" in e
        )
        assert counters["entries_with_must_not_wire_to"] == sum(
            1 for e in entries if "must_not_wire_to" in e
        )
        assert counters["hosts_with_inlined_second_implementation"] == 0
        assert counters["comment_only_pseudo_consumer_edges"] == len(
            deletion_plan["comment_only_pseudo_consumer_edges"]["edges"]
        )
        assert counters["orphan_production_formdata_composables"] == len(
            deletion_plan["orphan_production_formdata_composables"]["modules"]
        )

    def test_plan_has_no_pilot_branch(self, deletion_plan: dict) -> None:
        assert deletion_plan["pilot_already_migrated"] is None
        assert deletion_plan["pilot_already_migrated_note"]

    def test_i5_carrier_is_explicitly_preserved(self, deletion_plan: dict) -> None:
        """I5 的真载体 useI5FormData **绝不能删** —— 这条锁住那个例外。"""
        i5 = next(
            e for e in deletion_plan["entries"]
            if e["entry_id"] == "xlsx/gt-i5-other-noncurrent-assets"
        )
        preserved = [f["file"] for f in i5["legacy_composables_preserved"]]
        assert preserved == [
            "audit-platform/frontend/src/components/workpaper/composables/useI5FormData.ts"
        ]
        for other in deletion_plan["entries"]:
            to_delete = [f["file"] for f in other["legacy_composables_to_delete"]]
            assert not any("FormData" in f for f in to_delete), (
                f"{other['entry_id']}: FormData composable 被误列入待删"
            )


# ════════════════════════════════════════════════════════════════════════════
# 判据十三：范式合规（范式点名的校验器 + 反向自检）
# ════════════════════════════════════════════════════════════════════════════
class TestParadigmCompliance:
    def test_the_slice_passes_the_paradigm_nominated_validator(self, manifest_slice: dict) -> None:
        """范式 JSON 点名的校验器必须真的走过本 slice，且违规数为 0。"""
        validator = _load_validator()
        violations = validator(manifest_slice)
        assert violations == [], f"范式校验器报违规：{violations}"

    def test_the_validator_really_catches_a_missing_pending_field(
        self, manifest_slice: dict
    ) -> None:
        """🔴 反向自检：抽掉 capability_verdict_stage 后校验器必须**点名它**。

        防校验器被短路成恒返回空列表（那样上一条就是假绿）。
        """
        validator = _load_validator()
        broken = json.loads(json.dumps(manifest_slice))
        del broken["independent_entries"][0]["capability_verdict_stage"]
        violations = validator(broken)
        assert violations, "抽掉必填字段后校验器仍返回空 —— 它被短路了"
        assert any("capability_verdict_stage" in v for v in violations), violations

    def test_the_validator_really_catches_a_counter_mismatch(self, manifest_slice: dict) -> None:
        """反向自检之二：篡改 unadjudicated 计数必须触发 SR-9。"""
        validator = _load_validator()
        broken = json.loads(json.dumps(manifest_slice))
        broken["honest_adjudication_summary"]["slice_counters"]["unadjudicated"] = 0
        violations = validator(broken)
        assert any("SR-9" in v for v in violations), violations

    def test_paradigm_refs_and_task_number_are_right(self, manifest_slice: dict, paradigm: dict) -> None:
        assert manifest_slice["task"] == "Task 51"
        assert manifest_slice["schema_version"] == paradigm["slice_schema"]["target_schema_version"]
        assert 51 in paradigm["slice_schema"]["applies_to_tasks"]
        assert 51 in paradigm["definition_producer_paradigm"]["applies_to_tasks"]
        assert _resolve_repo(manifest_slice["paradigm_ref"]).exists()
        assert _resolve_repo(manifest_slice["source_manifest"]).exists()

    def test_paradigm_bytes_are_untouched_by_this_task(self, paradigm: dict) -> None:
        """本任务不改范式字节：capability_enum 仍是四值，legacy paradigm 仍是 7 步。"""
        assert paradigm["adjudication_criteria"]["capability_enum"] == list(CAPABILITY_ENUM)
        assert len(paradigm["paradigm"]["steps"]) == 7
        assert len(paradigm["definition_producer_paradigm"]["steps"]) == 12

    def test_new_sections_are_declared_as_non_conflicting(self, manifest_slice: dict) -> None:
        conflict = manifest_slice["paradigm_schema_conflict"]
        assert conflict["residual_inconsistency"] is None
        assert conflict["known_red_it_causes"]["status"] == "none"
        declared_new = set(conflict["new_section_not_in_schema"]["sections"])
        assert "classification_row_model_derivation" in declared_new
        assert conflict["new_section_not_in_schema"]["why_not_a_conflict"]
        assert conflict["new_section_not_in_schema"]["how_it_is_still_locked"]

    def test_unjudged_slices_registry_stays_empty(self) -> None:
        """`_UNJUDGED_SLICES` 必须保持 `{}` —— 本 slice 不加豁免。"""
        coverage = BACKEND / "tests" / "workpaper_sync" / "test_slice_schema_validator_coverage.py"
        body = coverage.read_text(encoding="utf-8")
        match = re.search(r"_UNJUDGED_SLICES:\s*dict\[str,\s*str\]\s*=\s*\{([^}]*)\}", body)
        assert match, "找不到 _UNJUDGED_SLICES 声明"
        assert not match.group(1).strip(), f"_UNJUDGED_SLICES 非空：{match.group(1)!r}"


def _load_validator():
    """从 importlib 加载被范式点名的校验器（复用它，不另写一份）。"""
    import importlib.util

    path = BACKEND / "tests" / "workpaper_sync" / "test_migration_paradigm_contract.py"
    spec = importlib.util.spec_from_file_location("_task51_validator_host", path)
    assert spec and spec.loader, f"无法从 importlib 加载 {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_slice_against_schema
