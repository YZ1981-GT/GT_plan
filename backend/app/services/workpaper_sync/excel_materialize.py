# -*- coding: utf-8 -*-
"""Excel identity-aware **materializer**（Task 38 的写入侧核心）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 38
Requirements: 3.4, 3.5, 6.3, 6.4, 6.5, 6.6, 6.9, 6.11, 6.15, 6.16, 6.17, 6.18, 8.10, 8.11, 8.12
Properties: **P9** / **P22** / **P23** / **P24** / **P29** / **P65** / **P66** / **P67**

═══ 一、方向只能是 38 → 37 ═══

Task 37（:mod:`app.services.workpaper_sync.excel_extract`）先于本模块落地，并用
:func:`~app.services.workpaper_sync.excel_extract.assert_no_materializer_dependency`
以**真实 import 图**断言它不 import 本模块。本模块反过来大量复用它：

* identity 定位（`resolve_managed_region` / `managed_tables_of` / `RowIdentityScan`）—— 本
  模块**不**自己解析 Excel Table ↔ sheet 关联，也不自己判空/重复/tombstone UUID；
* 受管字段列解析（`_resolve_field_column` 的语义由 Task 37 的 `ExcelIdentityBinding`
  承载，动态列缺实测绑定即 fail closed）；
* 三个共用 verifier 与唯一 commit 前置门 `verify_before_commit`（在
  :mod:`excel_rematerialize` 里调用）。

具体做法：materialize 的**第一件事**就是对 substrate 跑一次 Task 37 的
:func:`extract_projection`。它一次给齐四样本模块必需的东西 —— `region`（受管矩形与
sheet part）、`scan`（Excel 行号 ↔ row identity，含为 OO 新增行 minted 的新 ID）、
`formula_inventory`（受管格的公式文本）、`identity_inventory`。于是「哪一行是哪个身份」
在整条链上只有一份实现，写入侧不可能与读取侧对不上。

═══ 二、写入语义按 `FieldMode` 分四支，四支各自可达且各有专属异常 ═══

=====================  ==========================================  ==========================
mode                   写什么                                       写不了时
=====================  ==========================================  ==========================
``editable``           projection 值取代整格内容（含模板里原有公式）    :class:`EditableCellWriteError`
``auto_source``        服务端值写成字面量；模板里若是公式即契约漂移       :class:`ProtectedRegionWriteError`
``formula``            **只**改缓存 ``<v>``，``<f>`` 逐字保留          :class:`ProtectedRegionWriteError`
``word_only``          xlsx 不适用，跳过                              —
=====================  ==========================================  ==========================

`formula` 这一支的写法是被两侧夹出来的，不是随便选的：

* Task 15 的 `_assert_roundtrip_equivalent` 比对**全部**受管字段（不只 editable），所以
  公式格反读出来的缓存值必须等于 merged projection 的值 ⇒ 必须写 ``<v>``；
* AC 6.6 要求公式结果不得被覆盖、公式本体受保护 ⇒ 不得动 ``<f>``；
* Task 37 的 `_classify_protected_tamper` 在「公式文本未变」时把缓存值差异判为重算结果，
  所以只改 ``<v>`` 不会被误报成篡改。

三者叠起来只剩「保 ``<f>``、改 ``<v>``」一条路。design §Materialize 第 7 条
「formula/auto-source 写服务端值并保护」说的就是这件事。

═══ 三、zip-level 定点修改是默认，openpyxl 要 capability 证明 ═══

design §Materialize 末段：「优先使用 zip-level OOXML 定点修改。只有 template capability
manifest 明确 ``openpyxl_safe`` 且探针覆盖所有关键部件时才允许 openpyxl roundtrip；含
drawing/chart/pivot/macro 的文件默认禁止全量重写。」

:func:`select_write_strategy` 把这句话做成**可执行判据**，而且两边都用实测事实：

* 「这个文件里有没有 drawing/chart/pivot/macro」——
  :func:`measure_part_facts` 直接扫 zip 条目名，不信任任何声明；
* 「探针覆盖了哪些关键部件」—— :func:`probe_uncovered_aspects` 从 Task 5 的载体契约
  ``visible_equivalence.not_covered`` 读，不在本模块抄第二份清单。

实测结论（`backend/wp_templates` 全量 351 个 xlsx 里 182 个含 drawing、1 个含 chart，
探针本身对 pivot/VBA/外链/条件格式四项是 ``not_covered``）：**生产上没有一个模板能通过
这道门**，openpyxl 全量重写在真实模板上恒被拒。这不是把分支写死成不可达 —— 它由
capability + 实测部件双条件构成，两个条件都能被单独 falsify（守卫各测一条）。

═══ 四、不做什么（以及为什么这些拒绝是判据而不是偷懒）═══

1. **插行需要显式计划 + shift-aware 验证；算不出可安全执行的计划仍 fail closed。**

   ⚠ 2026-09-04 修正（spec `excel-structural-row-insertion-and-shift-aware-verification`）。
   本条原文是「**不做**结构性插行/删行」，理由是 Task 37 的 `verify_unmanaged_regions` 把
   受管 sheet 的结构块逐字节锁死，任何行位移必然被判成漂移。那个理由现在不成立了 ——
   verifier 接受一份**写盘之前冻结的** :class:`~app.services.workpaper_sync.excel_row_shift.RowShiftPlan`
   并按它反向归一化行号，于是「与声明一致的位移」判等价、「声明之外的任何改动」仍判漂移。
   **判据没有被放宽，只是变得能表达"预期"。**

   现在的语义：:func:`plan_managed_writes` 的第 6.2 步由 orphan 身份数算插行计划
   （插入点 = 最后一个既有数据行 +1，插入数 = orphan 数，样式源 = 最后一个既有数据行），
   算得出就插、算不出就抛 :class:`RowSetDivergenceError`。**五类**不可安全执行情形各自可达、
   两两可分辨（消息里带各自的 `error_code` 片段）：

   a. 受管 sheet 上出现清单外的位移敏感元素（``excel_row_shift_unlisted_structure``）
   b. 样式来源行缺失（``excel_row_shift_style_source_missing``）
   c. 共享公式组成员跨度与主格不一致（``excel_row_shift_shared_formula_span_mismatch``）
      / 横向组无法按行 fill-down（``excel_row_shift_shared_formula_orientation_unsupported``）
   d. 插入点或样式源越界（``excel_row_shift_plan_range_invalid`` / ``…_plan_count_invalid``）
   e. 🔴 **契约声明的静态行落在插入点及其之下**（``contract_static_row_below_insertion``）
      —— 本 spec 实施中实测发现，design.md 未覆盖。插行会把那些格整体推下去，而 Task 37 的
      extract 仍按契约 ``cell.static_row`` 反读固定行号 ⇒ 在旧行号上读到一个**新插入的空行**
      （静默取空值）。K11 契约的 ``k11_footer/tb_amount`` 在 ``B27``、追加插行的插入点是 26
      ⇒ **K11 在读侧跟随落地之前不可安全插行**。解除条件 = extract 侧的静态行定位也变成
      位移感知（读写两侧一起改）。

   注意 OO 侧插行**不**走这条路：OO 已经把物理行建好了，Task 37 会给它 mint 一个新
   identity，本模块只负责把那个 UUID 字面量落到隐藏列里。

   **结构性删行**仍然不做（本 spec Requirement 12.1 明列排除，已由
   `excel-workbook-wide-row-change-propagation` 承接）。
2. **共享公式主格只允许按预期位移扩张区间，永不被换成字面量**。
   ``<f t="shared" ref="H8:H25" si="1">`` 的主格一旦被换成字面量，H9..H25 全组失效。
   契约把这种格声明成 editable 时直接拒（:class:`SharedFormulaMasterWriteError`），
   因为「写坏 18 行公式」不该由反读门事后发现。

   ⚠ 2026-09-04 修正（spec `excel-structural-row-insertion-and-shift-aware-verification`
   Requirement 4.4 / 4.8）：本条原文是「**不改**共享公式主格」，现在收窄为「不换成字面量」。
   结构性插行允许把主格的 ``ref`` 与公式文本内区间按**预期位移量**平移，并在契约声明
   ``footer_anchor.carries_total_formula`` 时把合计区间末行**扩张**到覆盖新插入行。
   两件事都是「区间随受管区间伸缩」，不是「把公式换掉」—— 主格本身一个字符都没被替换。
   扩张之外的任何主格改写仍然禁止；未声明 ``carries_total_formula`` 的 footer 一律不改写
   （Requirement 4.5），:func:`assert_footer_formula_covers_managed_rows` 保持 fail-closed。
3. **不 commit、不切 pointer、不递增 revision**。本模块只产出 staged 文件与
   :class:`~app.services.workpaper_sync.adapters.base.MaterializeResult`；发布由
   `ContentMutationService` / `RepresentationService` 唯一控制。
4. **不写模板库**。:func:`materialize_projection` 只吃 substrate 路径与输出路径，并在
   写盘前用 :func:`assert_output_outside_template_library` 实测输出不落在
   ``backend/wp_templates/`` 之下（Requirement 9.9）。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
import dataclasses
from dataclasses import dataclass, field as dataclass_field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from openpyxl.utils import column_index_from_string

from app.services.workpaper_sync.adapters.base import (
    FieldValue,
    MaterializeResult,
    Projection,
    SubstrateRole,
    assert_substrate_usable,
)
from app.services.workpaper_sync.contracts import (
    FieldMode,
    FieldSpec,
    SyncContract,
    TableSpec,
    ValueType,
)
from app.services.workpaper_sync.excel_entry_gate import FrozenEntryDefinitions
from app.services.workpaper_sync.excel_instrumentation import normalized_structure_hash
from app.services.workpaper_sync.excel_extract import (
    ExcelIdentityBinding,
    ExcelExtractOutcome,
    ManagedRegion,
    RowIdentityScan,
    RuntimeIdentityInventory,
    assert_engine_entry_definitions,
    extract_projection,
    managed_tables_of,
    read_runtime_binding_pairs,
    read_runtime_identity_inventory,
    resolve_managed_region,
)
from app.services.workpaper_sync.excel_row_shift import (
    RowShiftError,
    RowShiftPlan,
    ShiftReport,
    shift_sheet_rows,
)
from app.services.workpaper_sync.excel_workbook_row_change import (
    plan_workbook_row_change_for_insert,
)
from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.merge import ValueNormalizationError, normalize_value
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState, SyncDomainError

__all__ = [
    # 异常
    "ExcelMaterializeError",
    "EditableCellWriteError",
    "ProtectedRegionWriteError",
    "SharedFormulaMasterWriteError",
    "RowIdentityWriteError",
    "DynamicColumnWriteError",
    "FooterAnchorDriftError",
    "FooterFormulaRangeError",
    "RowSetDivergenceError",
    "WriteStrategyForbiddenError",
    "TemplateLibraryWriteError",
    "FAILURE_KINDS",
    # capability 与写入策略
    "ExcelWriteStrategy",
    "WorkbookPartFacts",
    "ExcelWriteCapability",
    "PROTECTED_PART_ASPECTS",
    "CAPABILITY_REQUIRED_PROBE_ASPECTS",
    "measure_part_facts",
    "probe_uncovered_aspects",
    "select_write_strategy",
    "WriteStrategyDecision",
    # 计划
    "CellWriteKind",
    "CellWrite",
    "MaterializePlan",
    "plan_managed_writes",
    "assert_dynamic_column_binding_usable",
    "assert_footer_anchor_stable",
    "assert_footer_formula_covers_managed_rows",
    # 写盘
    "apply_plan_zip",
    "apply_plan_zip_with_report",
    "assert_shifted_footer_gates",
    "apply_plan_openpyxl",
    "assert_output_outside_template_library",
    "TEMPLATE_LIBRARY_MARKER",
    # 入口
    "ExcelMaterializeOutcome",
    "materialize_projection",
]


# ═══════════════════════════════════════════════════════════════════════════
# 0. 常量
# ═══════════════════════════════════════════════════════════════════════════

#: 运行时**不得**写入的目录标记（Requirement 9.9：模板库只读）。
TEMPLATE_LIBRARY_MARKER: Final[str] = "wp_templates"

#: Task 5 载体契约 `visible_equivalence.not_covered` 的取值文件（单一真源）。
_CARRIER_CONTRACT: Final[Path] = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "onlyoffice_excel_identity_carrier_contract.json"
)

#: 「含这些部件即禁止全量重写」——design §Materialize 末段列的四类。
PROTECTED_PART_ASPECTS: Final[tuple[str, ...]] = ("drawing", "chart", "pivot", "macro")

#: openpyxl 全量重写要求探针**已覆盖**的关键部件。任一条在 Task 5 契约里是
#: `not_covered` 就不许开门 —— 「未取证」与「已证明安全」不是一回事。
CAPABILITY_REQUIRED_PROBE_ASPECTS: Final[tuple[str, ...]] = (
    "pivot_table",
    "vba_macro",
    "external_link_workbooks",
    "conditional_formatting_and_data_validation",
)

#: zip 条目名 → part aspect 的判据（实测部件名，不看任何声明）。
_PART_ASPECT_PATTERNS: Final[Mapping[str, re.Pattern[str]]] = {
    "drawing": re.compile(r"^xl/(drawings/|media/)"),
    "chart": re.compile(r"^xl/charts/"),
    "pivot": re.compile(r"^xl/pivot(Tables|Cache)/"),
    "macro": re.compile(r"^xl/vbaProject\.bin$"),
    "external_link": re.compile(r"^xl/externalLinks/"),
    "table": re.compile(r"^xl/tables/"),
}

#: 单个 `<c r="COORD" .../>` / `<c r="COORD" ...>…</c>`。
#:
#: 🔴 自闭合分支必须在前、属性段必须**惰性**（`[^>]*?`）。Task 37 的 fixture 已经实测过
#: 贪心写法的后果：`[^>]*` 会吃掉 `s="56"/`，随后 `>.*?</c>` 从下一格开始一路吞到**下一个**
#: `</c>`，把紧邻的隐藏 UUID 格整个吃掉。
_CELL_RE_TPL: Final[str] = (
    '(?:<c r="{coord}"(?P<selfattrs>(?:\\s[^>]*?)?)/>)'
    '|(?:<c r="{coord}"(?P<attrs>(?:\\s[^>]*?)?)>(?P<body>.*?)</c>)'
)
#: 「这个渲染结果是数值字面量吗」——决定公式格要不要带 `t="str"`。
_NUMERIC_LITERAL_RE: Final[re.Pattern[str]] = re.compile(
    r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
)
_ANY_CELL_RE: Final[re.Pattern[str]] = re.compile(
    r'<c r="([A-Z]+)(\d+)"(?:\s[^>]*?)?/>|<c r="([A-Z]+)(\d+)"(?:\s[^>]*?)?>.*?</c>',
    re.S,
)
_ROW_RE_TPL: Final[str] = r'(<row r="{row}"(?:\s[^>]*?)?>)(?P<body>.*?)(</row>)'
_ROW_SELF_CLOSING_TPL: Final[str] = r'<row r="{row}"(?:\s[^>]*?)?/>'
_FORMULA_RE: Final[re.Pattern[str]] = re.compile(r"<f(?P<fattrs>(?:\s[^>]*?)?)(?:/>|>(?P<text>.*?)</f>)", re.S)
_VALUE_RE: Final[re.Pattern[str]] = re.compile(r"<v>.*?</v>|<v/>", re.S)
_INLINE_RE: Final[re.Pattern[str]] = re.compile(r"<is>.*?</is>", re.S)
#: 公式里的 A1 区间（`SUM(B7:B25)` 的 `B7:B25`）。绝对引用的 `$` 一并吃掉。
_RANGE_IN_FORMULA_RE: Final[re.Pattern[str]] = re.compile(
    r"\$?(?P<c1>[A-Z]{1,3})\$?(?P<r1>\d+):\$?(?P<c2>[A-Z]{1,3})\$?(?P<r2>\d+)"
)
_XML_ESCAPES: Final[tuple[tuple[str, str], ...]] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)


def _xml_escape(text: str) -> str:
    out = text
    for raw, encoded in _XML_ESCAPES:
        out = out.replace(raw, encoded)
    return out


#: 🔴 Task 42 新增：XML **数字字符引用**（`&#21512;` / `&#x5408;`）。
#:
#: 存在的理由是一条实测缺陷：`backend/wp_templates/` 下 369 个工作簿里有 **10 个**（含
#: Task 40 的 `B60-1 审计项目工时预算与控制表.xlsx`、Task 43 的 `G7 长期股权投资.xlsx`
#: 与 Task 42 的 `H1 固定资产.xlsx`）**没有** `sharedStrings.xml`，把非 ASCII 内联文本
#: 一律写成数字字符引用 —— 例如 footer 那格是
#: `<c r="A28" t="inlineStr"><is><t>&#21512;&#35745;</t></is></c>`。
#: :func:`_xml_unescape` 原本只还原五个具名实体，对这类文本原样返回 `'&#21512;&#35745;'`，
#: 于是 :func:`_find_marker_row` 在列 A 上找不到 marker `合计`，
#: :func:`assert_footer_anchor_stable` 抛 `FooterAnchorDriftError` ⇒ 这 10 个工作簿的
#: materialize 全线不可用（footer 合计公式区间覆盖判据也就无从执行）。
_NUMERIC_CHAR_REF: Final[re.Pattern[str]] = re.compile(r"&#(x[0-9a-fA-F]+|\d+);")


def _decode_numeric_char_refs(text: str) -> str:
    """还原 XML 数字字符引用（Task 42 新增；见 :data:`_NUMERIC_CHAR_REF` 的实测理由）。

    刻意**不**用 `html.unescape`：它还会把 `&nbsp;` 之类 HTML 专有实体一起换掉，而那些在
    XML 里是未定义实体，静默替换会让「文档非法」这一事实消失。
    """

    def _one(match: re.Match[str]) -> str:
        token = match.group(1)
        try:
            code = int(token[1:], 16) if token[0] in "xX" else int(token)
        except ValueError:  # pragma: no cover - 正则已限定形态
            return match.group(0)
        # 超出 Unicode 范围/非法码位一律原样保留：静默丢字符比留下引用更难查。
        return chr(code) if 0 < code <= 0x10FFFF else match.group(0)

    return _NUMERIC_CHAR_REF.sub(_one, text)


def _xml_unescape(text: str) -> str:
    # 🔴 Task 42 追加的一行：数字字符引用必须先还原（`&amp;#39;` 不会被误判 —— 它的 `#`
    #    前面是 `;` 而不是 `&`，正则匹配不上，随后具名实体那一趟才把它还原成字面
    #    `&#39;`）。
    out = _decode_numeric_char_refs(text)
    for raw, encoded in reversed(_XML_ESCAPES):
        out = out.replace(encoded, raw)
    return out.replace("&apos;", "'")


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常 —— 一条禁令一个类型一个 error_code
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本 spec 已三次实测「多条判据共用一个 error code ⇒ 靠前的分支永久不可达 ⇒ 只断言
#    类型的守卫判 GREEN」。Task 37 因此把三条 verifier 失败拆成三个类型；写入侧同样
#    不许合并：「写 editable 失败 / 动态 UUID 写入失败 / footer 位移 / 公式区被覆盖」
#    在生产诊断里是四件完全不同的事。


class ExcelMaterializeError(SyncDomainError):
    """Task 38 写入侧域基类。"""

    error_code = "excel_materialize_failed"


class EditableCellWriteError(ExcelMaterializeError):
    """editable 受管格写不进去（行/格在 sheet XML 里定位不到、值无法规范化）。"""

    error_code = "excel_materialize_editable_write_failed"


class ProtectedRegionWriteError(ExcelMaterializeError):
    """受保护区域（formula / auto-source）与契约声明不符，或将被非法覆盖（AC 6.6）。"""

    error_code = "excel_materialize_protected_region_violation"


class SharedFormulaMasterWriteError(ExcelMaterializeError):
    """契约要求写入的格是共享公式**主格**，写它会让整组成员失效。

    与 :class:`ProtectedRegionWriteError` 严格分开：后者是「契约说受保护却被改」，
    本类是「契约说 editable，但 OOXML 上这一格是别人的公式源」—— 两种成因、两种修法
    （改契约 vs 改模板）。合并成一个类型后其中一条永远不可分辨。
    """

    error_code = "excel_materialize_shared_formula_master_write"


class RowIdentityWriteError(ExcelMaterializeError):
    """动态行 identity（含 Task 37 minted 的新 ID）写不进隐藏 UUID 列。"""

    error_code = "excel_materialize_row_identity_write_failed"


class DynamicColumnWriteError(ExcelMaterializeError):
    """动态列 `{slot}_{seq}` 绑定不可用（键不符契约 identity 模板、或两个 slot 撞同一列）。"""

    error_code = "excel_materialize_dynamic_column_binding_unusable"


class FooterAnchorDriftError(ExcelMaterializeError):
    """footer 标记行与 representation 冻结的 `GT_FOOTER_ROW` 不符（footer 下移）。"""

    error_code = "excel_materialize_footer_anchor_drift"


class FooterFormulaRangeError(ExcelMaterializeError):
    """footer 合计公式的区间没覆盖当前受管行区间（插行后合计漏算）。"""

    error_code = "excel_materialize_footer_formula_range_stale"


class RowSetDivergenceError(ExcelMaterializeError):
    """merged projection 的行集与 substrate 的物理行集不一致，需结构性插删行。"""

    error_code = "excel_materialize_row_set_divergence"


class WriteStrategyForbiddenError(ExcelMaterializeError):
    """要求 openpyxl 全量重写，但 capability / 探针覆盖两条件未同时满足。"""

    error_code = "excel_materialize_write_strategy_forbidden"


class TemplateLibraryWriteError(ExcelMaterializeError):
    """输出路径落在 `backend/wp_templates/` 之下（Requirement 9.9：模板库运行时只读）。"""

    error_code = "excel_materialize_template_library_write"


#: 写入侧失败形态的**登记清单**：`error_code` → 触发条件（一句话，用于运维诊断）。
#:
#: 🔴 它存在的唯一理由是让「共享错误码让较早分支永久不可达」这个假绿形态可被 falsify。
#: 守卫的做法（Task 58 `test_failure_kinds_are_reachable_and_mutually_distinct` 范式）：
#: 把每一种 kind 在真实模板上**各真触发一次**，收集实际抛出的 `error_code` 集合，然后
#: 与本清单**双向等值** + 断言基数 == 登记条数。
#:
#: 这比「每类各测一遍」强：后者在两类被合并成同一个 code 时**全部仍绿**（两条用例都只
#: 断言「抛了 ExcelMaterializeError」或「抛了某个类型」，而合并后靠前的分支永不可达）。
#:
#: 本清单**手写**而不是从类反推 —— 从类反推就成了自证式同义反复（改类也自动改期望）。
FAILURE_KINDS: Final[Mapping[str, str]] = {
    "excel_materialize_editable_write_failed": (
        "editable 受管格定位不到或 projection 值无法按契约 value_type 规范化"
    ),
    "excel_materialize_protected_region_violation": (
        "契约与模板对受保护格（formula / auto_source）的声明不符，继续写会覆盖公式"
    ),
    "excel_materialize_shared_formula_master_write": (
        "契约声明 editable 的格在 OOXML 上是共享公式主格，覆盖它会让整组成员失效"
    ),
    "excel_materialize_row_identity_write_failed": (
        "Task 37 minted 的新行身份不在 merged projection 行集里，写入侧不得自行决定去留"
    ),
    "excel_materialize_dynamic_column_binding_unusable": (
        "动态列缺实测绑定、键不符 `{slot}_{seq}` identity 模板，或两个 slot 撞同一列"
    ),
    "excel_materialize_footer_anchor_drift": (
        "footer marker 实测行号与 representation 冻结的 GT_FOOTER_ROW 不一致（footer 下移）"
    ),
    "excel_materialize_footer_formula_range_stale": (
        "footer 合计公式的区间没覆盖当前受管行区间（插行后合计漏算）"
    ),
    "excel_materialize_row_set_divergence": (
        "merged projection 的行身份在 substrate 上没有物理行，需要结构性插行"
    ),
    "excel_materialize_write_strategy_forbidden": (
        "openpyxl 全量重写未获 capability + 探针覆盖双条件放行却被调用"
    ),
    "excel_materialize_template_library_write": (
        "输出路径落在 `backend/wp_templates/` 之下（模板库运行时只读）"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# 2. capability 与写入策略门
# ═══════════════════════════════════════════════════════════════════════════


class ExcelWriteStrategy(str, Enum):
    """写入方式。默认恒为 :attr:`zip_patch`。"""

    #: zip 级定点改字节：只碰受管格所在的 sheet part 与隐藏 UUID 列。
    zip_patch = "zip_patch"
    #: openpyxl 全量 roundtrip：只有 capability 清单证明安全的模板才开放。
    openpyxl_roundtrip = "openpyxl_roundtrip"


@dataclass(frozen=True)
class WorkbookPartFacts:
    """一份 artifact 的**实测**部件事实。判据来源是 zip 条目名，不是任何声明。"""

    entry_count: int
    aspect_counts: Mapping[str, int]

    @property
    def protected_aspects_present(self) -> tuple[str, ...]:
        return tuple(
            aspect
            for aspect in PROTECTED_PART_ASPECTS
            if self.aspect_counts.get(aspect, 0) > 0
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_count": self.entry_count,
            "aspect_counts": dict(sorted(self.aspect_counts.items())),
            "protected_aspects_present": list(self.protected_aspects_present),
        }


def measure_part_facts(artifact: Path) -> WorkbookPartFacts:
    """扫 zip 条目名得出「这个文件里到底有什么部件」。

    刻意**不**接受调用方传入的声明：capability manifest 说「没有 drawing」而文件里有
    一个 `xl/drawings/vmlDrawing1.vml` 时，必须以文件为准。
    """
    counts: dict[str, int] = {aspect: 0 for aspect in _PART_ASPECT_PATTERNS}
    with zipfile.ZipFile(artifact) as zf:
        names = [name for name in zf.namelist() if not name.endswith("/")]
    for name in names:
        for aspect, pattern in _PART_ASPECT_PATTERNS.items():
            if pattern.match(name):
                counts[aspect] += 1
    return WorkbookPartFacts(entry_count=len(names), aspect_counts=counts)


@dataclass(frozen=True)
class ExcelWriteCapability:
    """一个模板的写入 capability 声明。

    刻意做成**必须由调用方显式给出的值对象**而不是一份可选数据文件：数据文件缺省时
    「openpyxl 分支在生产上不可达」会退化成「分支恒不可达」（假绿第④源）。做成值对象后
    两个条件（声明 + 实测部件）各自都能被守卫单独 falsify。
    """

    template_relative_path: str
    openpyxl_safe: bool = False
    #: 该模板的探针已覆盖的关键部件（取值必须来自真实 probe 证据）。
    probe_covered_aspects: frozenset[str] = dataclass_field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not str(self.template_relative_path or "").strip():
            raise WriteStrategyForbiddenError(
                "ExcelWriteCapability.template_relative_path 不得为空 —— capability 必须"
                "绑定到具体模板，不得声明成「所有模板都安全」"
            )


def probe_uncovered_aspects(path: Path | None = None) -> frozenset[str]:
    """Task 5 载体契约里 `probe_verdict != passed` 的 `visible_equivalence.not_covered` 项。

    这是「探针覆盖了什么」的**唯一真源**（`backend/data/
    onlyoffice_excel_identity_carrier_contract.json`）。本模块不抄第二份清单 —— 抄一份
    就会出现「契约里改成 not_covered、代码里还是老样子」的第二真源。
    """
    target = path or _CARRIER_CONTRACT
    payload = json.loads(target.read_text(encoding="utf-8"))
    not_covered = payload.get("visible_equivalence", {}).get("not_covered", [])
    return frozenset(
        str(item.get("aspect"))
        for item in not_covered
        if str(item.get("probe_verdict")) != "passed" and item.get("aspect")
    )


@dataclass(frozen=True)
class WriteStrategyDecision:
    """策略裁决 + 逐条理由。理由进 operation error detail 与 evidence。"""

    strategy: ExcelWriteStrategy
    facts: WorkbookPartFacts
    refusals: tuple[str, ...]

    @property
    def openpyxl_allowed(self) -> bool:
        return self.strategy is ExcelWriteStrategy.openpyxl_roundtrip

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "openpyxl_allowed": self.openpyxl_allowed,
            "refusals": list(self.refusals),
            "facts": self.facts.as_dict(),
        }


def select_write_strategy(
    *,
    artifact: Path,
    capability: ExcelWriteCapability | None = None,
    uncovered_probe_aspects: frozenset[str] | None = None,
) -> WriteStrategyDecision:
    """zip-level 定点修改是默认；openpyxl 全量重写要同时满足三条。

    三条判据各自独立、各自可被 falsify：

    1. capability 清单必须**显式**声明 `openpyxl_safe`（缺 capability 即拒）；
    2. 文件里实测**没有** drawing / chart / pivot / macro（design 明列的四类）；
    3. Task 5 探针对 :data:`CAPABILITY_REQUIRED_PROBE_ASPECTS` 的每一项都不是
       `not_covered`，且 capability 自己声明覆盖了它们。

    任一条不满足即回落 zip patch，并把原因逐条记下来 —— 「静默回落」会让「以为开了
    openpyxl 其实没开」这类问题查不出来。
    """
    facts = measure_part_facts(artifact)
    uncovered = (
        uncovered_probe_aspects
        if uncovered_probe_aspects is not None
        else probe_uncovered_aspects()
    )
    refusals: list[str] = []
    if capability is None or not capability.openpyxl_safe:
        refusals.append(
            "capability 未声明 openpyxl_safe —— 全量重写默认禁止"
            "（design §Materialize：含 drawing/chart/pivot/macro 的文件默认禁止全量重写）"
        )
    present = facts.protected_aspects_present
    if present:
        refusals.append(
            f"实测含受保护部件 {list(present)}（部件计数 "
            f"{ {k: v for k, v in sorted(facts.aspect_counts.items()) if v} }）—— "
            "openpyxl 全量重写会丢失/重写它们"
        )
    blocked = sorted(set(CAPABILITY_REQUIRED_PROBE_ASPECTS) & set(uncovered))
    if blocked:
        refusals.append(
            f"Task 5 探针对 {blocked} 仍是 not_covered —— 「未取证」不等于「已证明安全」"
        )
    if capability is not None:
        missing = sorted(
            aspect
            for aspect in CAPABILITY_REQUIRED_PROBE_ASPECTS
            if aspect not in capability.probe_covered_aspects
        )
        if missing:
            refusals.append(f"capability 未声明已覆盖关键部件 {missing}")
    strategy = (
        ExcelWriteStrategy.zip_patch if refusals else ExcelWriteStrategy.openpyxl_roundtrip
    )
    return WriteStrategyDecision(
        strategy=strategy, facts=facts, refusals=tuple(refusals)
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 写入计划
# ═══════════════════════════════════════════════════════════════════════════


class CellWriteKind(str, Enum):
    """一处写入的形态。五类各自对应一条 OOXML 写法，互不重叠。"""

    #: 整格取代成数值字面量（`<v>`，无 `t`）。
    number_literal = "number_literal"
    #: 整格取代成 **OOXML 真布尔格**（`t="b"` + `<v>1</v>` / `<v>0</v>`）。
    #:
    #: 🔴 BP-22：原先 `boolean` 与 amount/integer/rate/ratio 一起归 `number_literal`，
    #: 落盘 `<c r="AK13"><v>1</v></c>`（无 `t`）⇒ extract 用 openpyxl 读回 **int 1** ⇒
    #: `merge.normalize_value(1, boolean)` 明令拒绝折叠 0/1 ⇒ **每一行**该字段都产出一条
    #: `type_normalization_failure`。D2 实测 13/13 行全中，首版发布因此卡在
    #: `roundtrip_verified`（`ValueNormalizationError: 实得 0`）。
    #:
    #: 修的是**写入形态**而不是放宽 `normalize_value`：那条拒绝是对的 —— 0/1 与 'True'
    #: 折叠会让「整数 1 被当成 true」这类真实类型错误静默通过。OOXML 本来就有布尔格类型，
    #: openpyxl 写真 `bool` 时也正是落 `t="b"`（实测），读回是真 `bool` ⇒ 往返自洽。
    #:
    #: `None` 不落 `<v>`：写成**空格**（保留 `s=` 样式）。`<v>0</v>` 会把「未填」变成
    #: 「填了 false」—— 对「是否函证」这类审计字段是实质性的语义错误。
    boolean_literal = "boolean_literal"
    #: 整格取代成内联字符串（`t="inlineStr"` + `<is><t>`；刻意不动 sharedStrings）。
    inline_text = "inline_text"
    #: **只**改缓存值，`<f>` 逐字保留（受保护公式格）。
    cached_value_only = "cached_value_only"
    #: 隐藏 UUID 列的 row identity 字面量。
    row_identity = "row_identity"


@dataclass(frozen=True)
class CellWrite:
    """一处受管写入。`stable_field_key` 空串表示这是 identity 列写入。"""

    coord: str
    kind: CellWriteKind
    value: Any
    stable_field_key: str = ""
    row_key: str = ""
    mode: FieldMode | None = None
    #: 仅 :attr:`CellWriteKind.cached_value_only` 用：`<f>` 的 **应有**文本。
    #:
    #: 🔴 非空表示「substrate 上这一格的公式文本与 intended 不符，必须还原」。OO→HTML 方向的
    #: substrate 是 incoming，公式文本可能已被 OO 改写（`=G7-D7` → `=G7-D7+1`，缓存值不变）。
    #: 只改 `<v>` 会把被改写的 `<f>` 逐字带进 staged result，而 `verify_formula_regions` 用
    #: 同一份 incoming 当 baseline 时是「篡改比篡改」⇒ 恒通过。AC 6.6 要求 current 公式与值
    #: 都不变，所以受保护格的 `<f>` 必须由 **base representation** 的 intended 文本决定。
    formula_text: str = ""

    @property
    def is_identity(self) -> bool:
        return self.kind is CellWriteKind.row_identity


@dataclass(frozen=True)
class MaterializePlan:
    """一次 materialize 要落的全部写入 + 必须保持不变的公式清册。"""

    sheet_part: str
    sheet_name: str
    writes: tuple[CellWrite, ...]
    #: stable key → 必须逐字保留的公式文本（受保护 formula 格）。
    preserved_formulas: Mapping[str, str]
    #: `table_key` → (`{slot}_{seq}` → Excel 列)。只作审计记录，解析由 Task 37 承担。
    dynamic_column_columns: Mapping[str, Mapping[str, str]]
    footer_marker_row: int | None = None
    # ── 结构性插行（spec excel-structural-row-insertion-and-shift-aware-verification）──
    #: 本次要执行的结构性插行声明。`None` = 不插行（零位移路径与本 spec 之前逐字节相同）。
    #:
    #: 🔴 它是**写盘之前冻结的声明**，不是事后观测：`verify_unmanaged_regions` 与 footer
    #: 两门都拿同一份 plan 做归一化/求值，于是「与声明一致的位移」判等价、「声明之外的
    #: 任何改动」仍判漂移。事后从 diff 推断位移量等于让被检查对象自己声明自己合法。
    row_shift: RowShiftPlan | None = None
    #: 契约声明「携带合计公式」的行号（位移**前**口径）。只有这些行的公式区间会被扩张。
    total_formula_rows: tuple[int, ...] = ()
    #: 受管 Excel Table 的 zip part —— 插行后它的 `ref` 行区间要随之增长。
    #: `assert_identity_inventory_retained` 明确「行区间随插删行变化属合法」，
    #: 而 `_classify_parts` 把 `xl/tables/**` 整类排除，所以这不是未管理区域漂移。
    table_part: str = ""
    # ── 工作簿级传播（spec excel-workbook-wide-row-change-propagation）────
    #: 本次插行要在**引用侧 sheet** 上做的传播声明。`None` = 无跨 sheet 引用指向受管
    #: sheet，或本次不插行 ⇒ 代码路径与本 spec 之前逐字节相同。
    #:
    #: 🔴 与 :attr:`row_shift` 同源同相：都是**写盘之前冻结的声明**。apply 按它改引用侧，
    #: `verify_unmanaged_regions` 按它归一化，两侧用的是**同一份**声明。于是「与声明一致的
    #: 传播」判等价、「声明之外的任何改动」仍判漂移 —— 事后从 diff 推断传播量等于让被检查
    #: 对象自己声明自己合法（design.md 拒绝方案第 3 条）。
    #:
    #: ⚠ 类型写成 `Any` 而不是 `WorkbookRowChangePlan`：N1 反向 import 本模块的
    #: `_write_entries` 会成环。运行时类型由 `assert_workbook_plan_consistent` 校验。
    workbook_row_change: Any | None = None

    @property
    def field_writes(self) -> tuple[CellWrite, ...]:
        return tuple(w for w in self.writes if not w.is_identity)

    @property
    def identity_writes(self) -> tuple[CellWrite, ...]:
        return tuple(w for w in self.writes if w.is_identity)

    @property
    def coords(self) -> tuple[str, ...]:
        return tuple(w.coord for w in self.writes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sheet_part": self.sheet_part,
            "sheet_name": self.sheet_name,
            "write_count": len(self.writes),
            "field_write_count": len(self.field_writes),
            "identity_write_count": len(self.identity_writes),
            "kind_counts": {
                kind.value: sum(1 for w in self.writes if w.kind is kind)
                for kind in CellWriteKind
            },
            "preserved_formula_count": len(self.preserved_formulas),
            "footer_marker_row": self.footer_marker_row,
            "row_shift": None if self.row_shift is None else self.row_shift.as_dict(),
            "total_formula_rows": list(self.total_formula_rows),
            "table_part": self.table_part,
            "workbook_row_change": (
                None
                if self.workbook_row_change is None
                else self.workbook_row_change.as_dict()
            ),
            "dynamic_column_columns": {
                table: dict(sorted(mapping.items()))
                for table, mapping in sorted(self.dynamic_column_columns.items())
            },
        }


# ─────────────────────────────────────────────────────────────────────────
# 3.1 zip 级 sheet XML 读取（写入侧自己的 XML 访问层）
# ─────────────────────────────────────────────────────────────────────────


def _read_entries(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _write_entries(entries: Mapping[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name, payload in entries.items():
            out.writestr(name, payload)
    return buf.getvalue()


@dataclass(frozen=True)
class _CellView:
    """一格的原样切片：整段 XML、属性串、body、公式文本与共享公式 ref。"""

    coord: str
    raw: str
    attrs: str
    body: str
    formula_text: str | None
    shared_ref: str | None
    #: `<f ...>` 的属性串（含前导空格）。还原公式文本时逐字保留它。
    formula_attrs: str = ""

    @property
    def style(self) -> str:
        found = re.search(r'\bs="(\d+)"', self.attrs)
        return found.group(1) if found else ""

    @property
    def has_formula(self) -> bool:
        return "<f" in self.body


def _cell_view(xml: str, coord: str) -> _CellView | None:
    pattern = re.compile(_CELL_RE_TPL.format(coord=re.escape(coord)), re.S)
    found = pattern.search(xml)
    if found is None:
        return None
    attrs = found.group("selfattrs") or found.group("attrs") or ""
    body = found.group("body") or ""
    formula = _FORMULA_RE.search(body)
    text: str | None = None
    shared_ref: str | None = None
    formula_attrs = ""
    if formula is not None:
        raw_text = formula.group("text")
        text = _xml_unescape(raw_text) if raw_text else ""
        formula_attrs = formula.group("fattrs") or ""
        ref = re.search(r'\bref="([^"]+)"', formula_attrs)
        shared_ref = ref.group(1) if ref else None
    return _CellView(
        coord=coord,
        raw=found.group(0),
        attrs=attrs,
        body=body,
        formula_text=text,
        shared_ref=shared_ref,
        formula_attrs=formula_attrs,
    )


def _cell_xml(*, coord: str, style: str, write: CellWrite) -> str:
    """按写入形态渲染一格。**恒带回原样式 `s=`**（AC 3.5：样式必须保留）。"""
    style_attr = f' s="{style}"' if style else ""
    if write.kind is CellWriteKind.inline_text:
        text = _xml_escape("" if write.value is None else str(write.value))
        return (
            f'<c r="{coord}"{style_attr} t="inlineStr">'
            f'<is><t xml:space="preserve">{text}</t></is></c>'
        )
    if write.kind is CellWriteKind.row_identity:
        text = _xml_escape(str(write.value))
        return (
            f'<c r="{coord}"{style_attr} t="inlineStr">'
            f"<is><t>{text}</t></is></c>"
        )
    if write.kind is CellWriteKind.boolean_literal:
        # BP-22：OOXML 真布尔格。`None` 写成**空格**而不是 `<v>0</v>` ——
        # 后者会把「未填」变成「填了 false」（见 CellWriteKind.boolean_literal 注释）。
        if write.value is None:
            return f'<c r="{coord}"{style_attr}/>'
        if not isinstance(write.value, bool):
            raise EditableCellWriteError(
                f"受管格 {coord}（{write.stable_field_key or 'identity'}）声明 "
                f"value_type=boolean，但落盘值是 {type(write.value).__name__} "
                f"{write.value!r} —— 真布尔格只接受 `bool` 或 `None`。"
                "0/1 不得当布尔写入（那正是 BP-22 修掉的形态：写成数值格后 extract 读回 "
                "int，`normalize_value` 拒绝折叠 ⇒ 每行一条 type_normalization_failure）"
            )
        return f'<c r="{coord}"{style_attr} t="b"><v>{1 if write.value else 0}</v></c>'
    return f'<c r="{coord}"{style_attr}><v>{_render_number(write.value)}</v></c>'


def _render_number(value: Any) -> str:
    if value is None:
        return "0"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return repr(value) if value != int(value) else str(int(value))
    return str(value)


def _replace_cached_value(view: _CellView, value: Any, formula_text: str = "") -> str:
    """把 `<v>` 换成服务端值；`<f>` 的**属性**（含 `t="shared" si=`）逐字保留。

    `formula_text` 非空时额外把 `<f>` 的**文本**还原成它 —— 见
    :attr:`CellWrite.formula_text` 的注释：OO 改写过的公式文本不得进 staged result。
    属性保留是刻意的：共享公式的 `ref`/`si` 决定整组成员的翻译关系，换掉它们会让 H9..H25
    全组失效，而那是「写坏 18 行公式」而不是「还原一格」。
    """
    rendered = f"<v>{_render_number(value)}</v>"
    body = view.body
    if formula_text:
        replacement = f"<f{view.formula_attrs}>{_xml_escape(formula_text)}</f>"
        patched, count = _FORMULA_RE.subn(replacement, body, count=1)
        if count != 1:
            raise ProtectedRegionWriteError(
                f"受保护格 {view.coord} 的 `<f>` 还原失败（未命中）—— 不得把被改写的公式"
                "带进 staged result（AC 6.6）"
            )
        body = patched
    if _VALUE_RE.search(body):
        body = _VALUE_RE.sub(rendered, body, count=1)
    else:
        # OO 有时把公式格写成只有 `<f>` 而没有缓存 `<v>`（尚未重算）。此时必须**补**一个，
        # 否则 Task 15 的全字段等值门反读不到值，整次发布被挡掉。
        body = body + rendered
    # 结果是数值 ⇒ 去掉 `t="str"` 之类的过期文本标记，否则 Excel 把数字当字符串。
    attrs = re.sub(r'\s+t="[^"]*"', "", view.attrs)
    if not _NUMERIC_LITERAL_RE.fullmatch(_render_number(value)):
        # 反过来：结果是文本时必须**带上** `t="str"`。模板里确实存在文本型公式格
        # （K11 实测 A7 是 `s="47" t="str"` + `<f>'明细表K11-2'!B11</f>`），无条件剥掉
        # 类型标记会让 Excel 把中文项目名当数字解析 ⇒ 打开即报错。
        attrs = f'{attrs} t="str"'
    return f'<c r="{view.coord}"{attrs}>{body}</c>'


def _patch_sheet_xml(xml: str, writes: Sequence[CellWrite]) -> str:
    """在 sheet XML 上定点写受管格。缺格按列序插入、缺行按行序插入。"""
    for write in writes:
        column = re.match(r"[A-Z]+", write.coord)
        row_match = re.search(r"\d+$", write.coord)
        if column is None or row_match is None:
            raise EditableCellWriteError(f"非法坐标 {write.coord!r}")
        row = int(row_match.group(0))
        view = _cell_view(xml, write.coord)
        if view is not None:
            if write.kind is CellWriteKind.cached_value_only:
                new = _replace_cached_value(view, write.value, write.formula_text)
            else:
                new = _cell_xml(coord=write.coord, style=view.style, write=write)
            xml = xml.replace(view.raw, new, 1)
            continue
        if write.kind is CellWriteKind.cached_value_only:
            raise ProtectedRegionWriteError(
                f"受保护公式格 {write.coord} 在 substrate 里不存在 —— 不得凭空造一个公式格"
                f"（stable key {write.stable_field_key!r}）"
            )
        new = _cell_xml(coord=write.coord, style="", write=write)
        xml = _insert_cell(xml, row=row, column=column.group(0), cell_xml=new)
    return xml


def _insert_cell(xml: str, *, row: int, column: str, cell_xml: str) -> str:
    self_closing = re.search(_ROW_SELF_CLOSING_TPL.format(row=row), xml)
    if self_closing is not None:
        raw = self_closing.group(0)
        return xml.replace(raw, raw[:-2] + ">" + cell_xml + "</row>", 1)
    row_pat = re.compile(_ROW_RE_TPL.format(row=row), re.S)
    found = row_pat.search(xml)
    if found is None:
        return _insert_row(xml, row=row, cell_xml=cell_xml)
    body = found.group("body")
    target = column_index_from_string(column)
    out: list[str] = []
    inserted = False
    for match in _ANY_CELL_RE.finditer(body):
        letters = match.group(1) or match.group(3)
        if not inserted and column_index_from_string(letters) > target:
            out.append(cell_xml)
            inserted = True
        out.append(match.group(0))
    if not inserted:
        out.append(cell_xml)
    start, end = found.span("body")
    return xml[:start] + "".join(out) + xml[end:]


def _insert_row(xml: str, *, row: int, cell_xml: str) -> str:
    """按行序插入一整行。**不位移**任何既有行（结构性插行见模块 docstring 第四节）。"""
    new_row = f'<row r="{row}">{cell_xml}</row>'
    rows = [(int(m.group(1)), m.start()) for m in re.finditer(r'<row r="(\d+)"', xml)]
    for number, offset in rows:
        if number > row:
            return xml[:offset] + new_row + xml[offset:]
    if "</sheetData>" not in xml:
        raise EditableCellWriteError(
            f"sheet XML 缺 </sheetData>，无法插入第 {row} 行"
        )
    return xml.replace("</sheetData>", f"{new_row}</sheetData>", 1)


# ─────────────────────────────────────────────────────────────────────────
# 3.2 动态列 / footer 的写入前置判据
# ─────────────────────────────────────────────────────────────────────────


def assert_dynamic_column_binding_usable(
    *, contract: SyncContract, binding: ExcelIdentityBinding
) -> Mapping[str, Mapping[str, str]]:
    """动态列绑定的两条写入前置判据（Property 22）。

    1. **键必须符合契约声明的 identity 模板**（默认 `{slot}_{seq}`）。可改的公司 label
       绝不能当键 —— 那是 Requirement 6.4 明令禁止的；
    2. **同一张表的两个 slot 不得映射到同一列**。重复 label 是合法输入（两家单位可能
       同名），但两个 slot 落进一列会让后写的静默覆盖先写的，审计上表现为「一家单位的
       数据凭空消失」。

    返回实际生效的绑定，供 :class:`MaterializePlan` 记录。
    """
    out: dict[str, Mapping[str, str]] = {}
    for sheet in contract.sheets:
        for table in sheet.tables:
            if table.dynamic_columns is None:
                continue
            bound = dict(binding.dynamic_column_columns.get(table.table_key, {}))
            if not bound:
                raise DynamicColumnWriteError(
                    f"契约表 {table.table_key!r} 声明了 dynamic_columns "
                    f"(identity={table.dynamic_columns.identity!r})，但 identity binding "
                    "没给 `{slot}_{seq}` → Excel 列的实测绑定 —— 写入侧不得按声明列右移猜"
                )
            pattern = _identity_pattern(table.dynamic_columns.identity)
            bad_keys = sorted(key for key in bound if not pattern.fullmatch(key))
            if bad_keys:
                raise DynamicColumnWriteError(
                    f"契约表 {table.table_key!r} 的动态列键 {bad_keys} 不符契约声明的 identity "
                    f"模板 {table.dynamic_columns.identity!r} —— 可改的公司/单位 label 不得作"
                    "列 identity（Requirement 6.4 / Property 22）"
                )
            by_column: dict[str, list[str]] = {}
            for key, column in sorted(bound.items()):
                by_column.setdefault(column, []).append(key)
            collided = {c: k for c, k in by_column.items() if len(k) > 1}
            if collided:
                first_column = sorted(collided)[0]
                raise DynamicColumnWriteError(
                    f"契约表 {table.table_key!r} 的动态列 {collided[first_column]} 都绑定到列 "
                    f"{first_column} —— 两个 `{{slot}}_{{seq}}` 落进同一列时后写的会静默覆盖"
                    "先写的（重复 label 合法，重复列不合法）"
                )
            out[table.table_key] = bound
    return out


def _identity_pattern(identity: str) -> re.Pattern[str]:
    """把契约的 identity 模板（如 `{slot}_{seq}`）编译成键校验正则。

    `{slot}` = 非空的小写标识片段；`{seq}` = 十进制序号。刻意不接受任意字符 —— 否则
    `公司甲_1` 这种带 label 的键也会通过，Property 22 的判据就空转了。
    """
    escaped = re.escape(identity)
    escaped = escaped.replace(re.escape("{slot}"), r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*?")
    escaped = escaped.replace(re.escape("{seq}"), r"\d+")
    return re.compile(escaped)


def assert_footer_anchor_stable(
    *,
    entries: Mapping[str, bytes],
    sheet_part: str,
    contract: SyncContract,
    runtime_binding: Mapping[str, str],
    row_shift: RowShiftPlan | None = None,
) -> int | None:
    """footer 标记行必须与 representation 冻结的 `GT_FOOTER_ROW` 一致（AC 6.9 / 6.3）。

    判据用两个**互相独立**的载体交叉验证：

    * 可见侧 —— 契约 `footer_anchor` 的 marker 在 `search_column` 上的实际行号；
    * 冻结侧 —— Task 17 写进隐藏 `_GT_SYNC` 的 `GT_FOOTER_ROW`，由 Task 37 的
      :func:`~app.services.workpaper_sync.excel_extract.read_runtime_binding_pairs`
      读出后作为 `runtime_binding` 传进来（本模块不自己解析那张 sheet —— 首版抄了一份
      `r:id="(rId\\d+)"` 的 sheet 定位，而 Task 17 的关系 id 是 `rIdGTSYNC`，于是恒读空、
      把「sheet 定位失败」误报成「缺 GT_FOOTER_ROW」）。

    两者不一致即 footer 已下移（OO 在受管区域内插了行）。此时**fail closed**而不是跟着
    marker 写：Task 37 的 extract 仍按契约 `static_row` 反读，跟着写会让「写在 28 行、
    反读 27 行」这条静默错值路径出现。跟随 footer 需要读写两侧一起改，登记为后续任务。

    契约没声明 footer_anchor 的表返回 `None`（不是判据空转 —— 没有 footer 就没有下移
    问题；守卫用「声明了 footer 的契约」这一支）。

    ═══ `row_shift`：位移感知（Requirement 7.1~7.3）═══

    Spec: excel-structural-row-insertion-and-shift-aware-verification

    判据由「实测 == 冻结」改为「实测 == 冻结 + **声明**位移量」。用的是写盘之前冻结的
    `plan.count`，不是从 diff 事后推断的观测值 —— 于是「不明原因的下移」照旧被拦住：
    实测 29 行而声明插 2 行、冻结 27 行 ⇒ 27+2=29 通过；若实测 30 行则不等，仍抛
    :class:`FooterAnchorDriftError`。

    🔴 `row_shift=None` 时判据**逐字相同**（Requirement 7.2）；返回值语义不变
    （`None` = 契约无 footer 声明，Requirement 7.6）。

    🔴 位移量只在 footer 落在**插入点及其之下**时才计入。footer 在插入点之上时插行不会
    动它 —— 一律加 `count` 会把「footer 本来就不该动」的场合判成漂移。判定用
    `plan.shift(frozen)` 而不是 `frozen + plan.count`：前者自带这个边界，后者要在调用侧
    再写一遍 if（写两遍就会漂移）。
    """
    anchors = [
        table.footer_anchor
        for sheet in contract.sheets
        for table in sheet.tables
        if table.footer_anchor is not None
    ]
    if not anchors:
        return None
    anchor = anchors[0]
    xml = entries[sheet_part].decode("utf-8")
    shared = _shared_strings(entries)
    observed = _find_marker_row(
        xml, column=anchor.search_column, marker=anchor.marker, shared=shared
    )
    if observed is None:
        raise FooterAnchorDriftError(
            f"契约声明的 footer marker {anchor.marker!r} 在列 {anchor.search_column} 上"
            "一处都找不到 —— footer anchor 是 AC 6.3 要求契约表达的结构之一，"
            "定位不到即结构漂移，不得按固定行号继续写"
        )
    frozen = runtime_binding.get("GT_FOOTER_ROW")
    if frozen is None:
        raise FooterAnchorDriftError(
            "runtime binding 里没有 GT_FOOTER_ROW（实测键 "
            f"{sorted(runtime_binding)[:8]}）—— footer 位置缺冻结预期，"
            "无法判断它有没有下移"
        )
    raw_frozen = str(frozen).strip()
    if row_shift is None:
        if str(observed) != raw_frozen:
            raise FooterAnchorDriftError(
                f"footer marker {anchor.marker!r} 实测在第 {observed} 行，representation 冻结的 "
                f"GT_FOOTER_ROW={frozen} —— footer 已下移。写入侧 fail closed：Task 37 的 extract "
                "仍按契约 static_row 反读，跟着 marker 写会造成「写在新行、反读旧行」的静默错值"
            )
        return observed

    if not raw_frozen.isdigit():
        raise FooterAnchorDriftError(
            f"runtime binding 的 GT_FOOTER_ROW={frozen!r} 不是行号 —— 位移感知判据要拿它做"
            "算术，非数字形态不得当成「随便什么都行」继续（Requirement 7.1）"
        )
    frozen_row = int(raw_frozen)
    expected = row_shift.shift(frozen_row)
    if observed != expected:
        raise FooterAnchorDriftError(
            f"footer marker {anchor.marker!r} 实测在第 {observed} 行，"
            f"representation 冻结的 GT_FOOTER_ROW={frozen_row}，"
            f"本次声明的预期位移 +{expected - frozen_row} 行"
            f"（插入点 {row_shift.insert_at}，插 {row_shift.count} 行）"
            f"⇒ 预期落在第 {expected} 行 —— 三者不一致即 footer 有**声明之外**的下移。"
            "写入侧 fail closed：Task 37 的 extract 仍按契约 static_row 反读，"
            "跟着 marker 写会造成「写在新行、反读旧行」的静默错值"
        )
    return observed


def _shared_strings(entries: Mapping[str, bytes]) -> list[str]:
    blob = entries.get("xl/sharedStrings.xml")
    if blob is None:
        return []
    xml = blob.decode("utf-8")
    out: list[str] = []
    for item in re.findall(r"<si>(.*?)</si>", xml, re.S):
        out.append(_xml_unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", item, re.S))))
    return out


def _find_marker_row(
    xml: str, *, column: str, marker: str, shared: Sequence[str]
) -> int | None:
    """在指定列上找 marker 文本所在行（支持 sharedString / inlineStr / str 三种载体）。"""
    for match in re.finditer(
        r'<c r="' + re.escape(column) + r'(\d+)"(?P<attrs>(?:\s[^>]*?)?)>(?P<body>.*?)</c>',
        xml,
        re.S,
    ):
        row = int(match.group(1))
        attrs = match.group("attrs") or ""
        body = match.group("body")
        text: str | None = None
        if 't="s"' in attrs:
            index = re.search(r"<v>(\d+)</v>", body)
            if index is not None and int(index.group(1)) < len(shared):
                text = shared[int(index.group(1))]
        elif 't="inlineStr"' in attrs:
            inline = re.search(r"<t[^>]*>(.*?)</t>", body, re.S)
            text = _xml_unescape(inline.group(1)) if inline else None
        else:
            value = re.search(r"<v>(.*?)</v>", body, re.S)
            text = _xml_unescape(value.group(1)) if value else None
        if text is not None and text.strip() == marker:
            return row
    return None


def assert_footer_formula_covers_managed_rows(
    *,
    entries: Mapping[str, bytes],
    sheet_part: str,
    footer_row: int,
    region: ManagedRegion,
    row_shift: RowShiftPlan | None = None,
    carries_total_formula: bool = False,
) -> tuple[str, ...]:
    """footer 合计公式的区间必须覆盖当前受管行区间（design §Materialize 第 7 条）。

    真实形态（K11 实测）：footer 的 `SUM(B7:B25)` 是 `t="shared" si="3"` 的主格，
    C26..G26 是无文本的组成员。OO 在受管区域**末尾**插行时 Table ref 会从 `A7:N25` 长到
    `A7:N26`，而 `SUM(B7:B25)` **不会**跟着长 —— 合计从此漏算新行。这是一条真实的审计
    缺陷类，必须打红而不是发布出去。

    只检查**有公式文本**的格（共享公式主格）：组成员的区间由主格 translation 决定，行跨度
    与主格一致，因此主格覆盖到了，成员也覆盖到了。

    返回被检查过的坐标清单 —— 空清单意味着这条判据本次没检查任何东西，调用方据此
    区分「通过」与「空转」。

    ═══ `row_shift` / `carries_total_formula`（Requirements 4.4 / 5.4 / 7.4 / 7.5）═══

    Spec: excel-structural-row-insertion-and-shift-aware-verification

    * `row_shift` 非空时用**位移后**的受管区末行（`region.last_row + count`）求值
      （Requirement 7.4）。合计区间已按 Requirement 4.4 扩张 ⇒ 通过；未扩张 ⇒ 仍报
      :class:`FooterFormulaRangeError`（Requirement 7.5）。
    * `carries_total_formula` 为真但该 footer 行**一处公式都没有** ⇒ fail closed
      （Requirement 5.4）：契约声明「这一行有合计公式」而模板上没有，说明两者已经对不上，
      此时静默通过会让「扩张分支永远不执行」变成一个看不见的空转 —— 真实误用形态就是
      「把某个标签行当成合计行传进来」（K11 的 27 行 `A27` 是 `t="s"` 文本、B27..J27 全空，
      拿它当 `footer_row` 时旧实现静默返回空 tuple）。

      ⚠ 顺带更正一处曾写错的实测事实：K11 的 footer **anchor** marker 与合计公式**同在
      26 行**（`GT_FOOTER_ROW = 26`，`B26:G26` 就是 `SUM(B7:B25)` 的主格）。27 行只是一个
      恰好没有公式的标签行，不是 anchor；`test_task37.FOOTER_ROW = 27` 指的是契约里另一处
      静态字段行。冻结事实一律现读 `read_runtime_binding_pairs`，不从别的常量名推。

    `row_shift=None` 且 `carries_total_formula=False` 时行为逐字相同（纯增量），
    返回值语义不变（Requirement 7.6）。
    """
    xml = entries[sheet_part].decode("utf-8")
    row_match = re.search(_ROW_RE_TPL.format(row=footer_row), xml, re.S)
    # 🔴 位移后的受管区末行由**声明**位移量派生，不从 diff 观测 —— 观测值等于让被检查
    #    对象自己声明自己合法。
    effective_last_row = (
        region.last_row + row_shift.count if row_shift is not None else region.last_row
    )
    if row_match is None:
        raise FooterFormulaRangeError(
            f"footer 行 {footer_row} 在 sheet XML 里不存在 —— 合计行缺失，无法证明合计覆盖"
            f"受管行区间 {region.first_row}..{effective_last_row}"
        )
    checked: list[str] = []
    for match in _ANY_CELL_RE.finditer(row_match.group("body")):
        coord = f"{match.group(1) or match.group(3)}{footer_row}"
        view = _cell_view(xml, coord)
        if view is None or not view.formula_text:
            continue
        checked.append(coord)
        for span in _RANGE_IN_FORMULA_RE.finditer(view.formula_text):
            first, last = int(span.group("r1")), int(span.group("r2"))
            if first > region.first_row or last >= effective_last_row:
                continue
            raise FooterFormulaRangeError(
                f"footer 格 {coord} 的公式 {view.formula_text!r} 区间只到第 {last} 行，"
                f"而受管行区间已到第 {effective_last_row} 行"
                + (
                    f"（含本次声明的 +{row_shift.count} 行插入）"
                    if row_shift is not None
                    else ""
                )
                + f" —— 合计漏算 {effective_last_row - last} 行。"
                "本 spec 只允许按**预期位移**扩张该区间（Requirement 4.4，需契约声明 "
                "`carries_total_formula`）；未扩张即 fail closed 交人工处理"
            )
    if carries_total_formula and not checked:
        raise FooterFormulaRangeError(
            f"契约声明 footer 携带合计公式（`carries_total_formula=true`），但第 {footer_row} 行"
            "上一处带公式文本的格都没有 —— 声明与模板不符（Requirement 5.4）。"
            "静默通过会让「合计区间扩张」这条分支永远不执行，而那是个看不见的空转："
            "K11 实测 footer **anchor** 在 27 行（纯文本标签），真正带 `SUM(B7:B25)` 的是 26 行"
        )
    return tuple(checked)


# ─────────────────────────────────────────────────────────────────────────
# 3.3 计划构造
# ─────────────────────────────────────────────────────────────────────────


def _instantiate(stable_key: str, row_identity: str) -> str:
    return stable_key.replace("{row_uuid}", row_identity)


def _formula_body(text: str) -> str:
    """公式的 OOXML 形态：去掉**一个**前导 `=`。

    Task 37 的 `formula_inventory` 走 openpyxl（`data_only=False`），值形如 ``=G7-D7``（这是
    openpyxl 的用户可见形态，也是它筛选公式格的判据：`startswith("=")`）；而 OOXML 的
    ``<f>`` 内容**不带** `=`。两侧不换算就会写出 ``<f>=G7-D7</f>``，Excel 打开后是
    ``==G7-D7``。本任务首轮实测踩过（守卫
    `test_reported_tamper_proceeds_and_keeps_the_template_formula` 当场打红）。
    """
    return text[1:] if text.startswith("=") else text


def _write_kind_for(spec: FieldSpec) -> CellWriteKind:
    if spec.mode is FieldMode.formula:
        return CellWriteKind.cached_value_only
    # 🔴 BP-22：`boolean` 必须**先于**数值族判定，且落 OOXML 真布尔格 `t="b"`。
    #    归到 `number_literal` 时落盘无 `t` ⇒ extract 读回 int ⇒ `normalize_value` 拒绝
    #    折叠 0/1 ⇒ 每行一条 `type_normalization_failure`（D2 实测 13/13 行全中）。
    if spec.value_type is ValueType.boolean:
        return CellWriteKind.boolean_literal
    if spec.value_type in (
        ValueType.amount,
        ValueType.integer,
        ValueType.rate,
        ValueType.ratio,
    ):
        return CellWriteKind.number_literal
    return CellWriteKind.inline_text


def _normalised_write_value(field: FieldValue, spec: FieldSpec, coord: str) -> Any:
    """把 projection 值规范化成落盘值。规范化失败即 fail visible。

    复用 `merge.normalize_value` 的**同一套**口径：写入侧若自己写一套，「merge 认为等值、
    反读认为不等值」就会变成无法解释的发布失败。
    """
    try:
        return normalize_value(field.value, spec.value_type)
    except ValueNormalizationError as exc:
        raise EditableCellWriteError(
            f"受管格 {coord}（{spec.stable_field_key}）的值 {field.value!r} 无法按 "
            f"{spec.value_type.value} 规范化: {exc} —— 不得写一个自己都读不懂的值"
        ) from exc


def plan_managed_writes(
    *,
    projection: Projection,
    contract: SyncContract,
    binding: ExcelIdentityBinding,
    region: ManagedRegion,
    scan: RowIdentityScan,
    substrate_entries: Mapping[str, bytes],
    substrate_formulas: Mapping[str, str],
    runtime_binding: Mapping[str, str],
    intended_formulas: Mapping[str, str] | None = None,
) -> MaterializePlan:
    """算出「往哪些格写什么」。纯函数：不碰磁盘、不改 `substrate_entries`。

    执行顺序即判据（不可交换）：

    1. 动态列绑定前置判据（Property 22）；
    2. footer anchor 与冻结 `GT_FOOTER_ROW` 交叉验证（footer 下移 fail closed）；
    3. footer 合计公式区间覆盖当前受管行区间；
    4. 行集一致性（merged projection 的行身份必须都有物理行）；
    5. 逐字段按 mode 生成写入，并对受保护格/共享公式主格施加禁令；
    6. minted row identity 落隐藏 UUID 列。

    2/3 放在字段写入**之前**：结构漂移时一格都不该写。

    `intended_formulas` 是受保护格 `<f>` 的**应有**文本（OO→HTML 方向取 application 冻结的
    base representation）。缺省为 `substrate_formulas`，即 HTML→OO 方向「substrate 自己就是
    权威」。给了它之后，substrate 上被改写过的公式会被还原 —— 见 :attr:`CellWrite.formula_text`。
    """
    dynamic_columns = assert_dynamic_column_binding_usable(
        contract=contract, binding=binding
    )

    # ── 6.2 结构性插行计划 —— **必须排在 footer 两门之前** ────────────
    #
    # 两门要用位移后的区间求值，而位移量在这里才产生。顺序反了就会拿旧区间判新结构。
    dynamic_table, static_tables = managed_tables_of(contract, binding=binding)
    physical = dict(scan.row_identity_by_row)
    row_of_identity: dict[str, int] = {}
    for row, identity in sorted(physical.items()):
        row_of_identity.setdefault(identity, row)

    wanted = tuple(projection.row_keys.get(dynamic_table.table_key, ()))
    orphan = [identity for identity in wanted if identity not in row_of_identity]

    row_shift: RowShiftPlan | None = None
    total_formula_rows: tuple[int, ...] = ()
    table_part = ""
    shifted_xml: str | None = None
    if orphan:
        row_shift, total_formula_rows, table_part, shifted_xml = _plan_row_shift(
            orphan=orphan,
            contract=contract,
            region=region,
            scan=scan,
            substrate_entries=substrate_entries,
            runtime_binding=runtime_binding,
        )
        # 插入行数**必须**恰等于 orphan 数（Requirement 2.6 / Property 5）。
        if row_shift.count != len(orphan):
            raise RowSetDivergenceError(
                f"位移计划声明插 {row_shift.count} 行，而 merged projection 上没有物理行的"
                f"身份是 {len(orphan)} 个 —— 两者必须恰好相等，否则新行与身份对不上"
            )
        # orphan 身份按**声明顺序**落进新行区间；行号只用于定位，不作身份
        # （Requirement 6.5 / Property 23：永不含数组下标语义）。
        for offset, identity in enumerate(orphan):
            row_of_identity[identity] = row_shift.insert_at + offset

    # ── 6.3 受管区域按 count 重构；footer 两门一律用新区间 ──────────
    effective_region = (
        region
        if row_shift is None
        else dataclasses.replace(region, last_row=region.last_row + row_shift.count)
    )

    # ── 6.4 / 6.5 footer 两门 ───────────────────────────────────────
    #
    # 🔴 **计划期的两门跑在 substrate 上，而 substrate 还没被位移** ⇒ 这里**不得**传
    #    `row_shift`。首版传了，H1 实测当场打红：marker 实测在冻结行 28、计划要插 1 行，
    #    判据于是期待 29 —— 而位移发生在 apply 阶段，substrate 上它当然还在 28。
    #
    #    两个参数的正确用法是**分两相**：
    #      计划期（substrate，位移前）→ 判「实测 == 冻结」「合计覆盖当前区间」
    #      apply 后（staged，位移后）→ 判「实测 == 冻结 + 声明位移」「合计覆盖位移后区间」
    #    后一相在 `materialize_projection` 里做（:func:`assert_shifted_footer_gates`）。
    footer_row = assert_footer_anchor_stable(
        entries=substrate_entries,
        sheet_part=region.sheet_part,
        contract=contract,
        runtime_binding=runtime_binding,
    )
    anchor = next(
        (
            table.footer_anchor
            for sheet in contract.sheets
            for table in sheet.tables
            if table.footer_anchor is not None
        ),
        None,
    )
    if footer_row is not None:
        assert_footer_formula_covers_managed_rows(
            entries=substrate_entries,
            sheet_part=region.sheet_part,
            footer_row=footer_row,
            region=region,
            carries_total_formula=bool(anchor and anchor.carries_total_formula),
        )
        # ── 第六类拒绝理由：插行会让合计漏算，而契约没授权扩张 ──────
        #
        # 判据形态是「拿位移后的区间预演一次」：若 substrate 上的 footer 公式覆盖不到
        # 位移后的末行，而契约又没声明 `carries_total_formula`，那么这次插行的产物会是
        # 一张**合计漏算新行**的审计底稿。这一支必须在写盘之前拦住。
        #
        # 契约声明了扩张时这里的报错是**预期**的（扩张在 apply 阶段发生），故吞掉并
        # 交给 apply 后那一相复核 —— 不吞的话「声明扩张」这条路径永远走不通。
        if row_shift is not None:
            try:
                assert_footer_formula_covers_managed_rows(
                    entries=substrate_entries,
                    sheet_part=region.sheet_part,
                    footer_row=footer_row,
                    region=region,
                    row_shift=row_shift,
                )
            except FooterFormulaRangeError as exc:
                if not (anchor and anchor.carries_total_formula):
                    raise RowSetDivergenceError(
                        "[contract_total_formula_not_extendable] merged projection 的行身份 "
                        f"{list(orphan[:3])}（共 {len(orphan)} 个）在 substrate 上没有物理行，"
                        f"需要插 {row_shift.count} 行；但 footer 的合计区间覆盖不到位移后的末行 "
                        f"{effective_region.last_row}，而契约**没有**声明 "
                        "`footer_anchor.carries_total_formula` ⇒ 引擎无权扩张它。"
                        f"照插会产出一张合计漏算 {row_shift.count} 行的审计底稿。"
                        f"原始判据：{exc}"
                    ) from exc

    # ── 6.6 行集一致性：orphan 已被 6.2 消化，此时必须为空 ─────────
    still_missing = [
        identity for identity in wanted if identity not in row_of_identity
    ]
    if still_missing:
        raise RowSetDivergenceError(
            f"merged projection 的行身份 {still_missing[:3]}（共 {len(still_missing)} 个）"
            "在位移计划消化之后**仍然**没有物理行 —— 位移计划与 orphan 集合不一致，"
            "不得带着对不上的行集继续写入"
        )

    # 🔴 逐字段判据（`formula` 模式要求该格已有公式、`auto_source` 要求它**不是**公式、
    #    editable 不得落在共享公式主格上）必须对着**位移后**的形态求值：新插入行在
    #    substrate 上不存在，拿 substrate 求 `_cell_view` 会报「H27 没有公式」——
    #    那是问错了 artifact，不是契约漂移。零位移时两者是同一份字节。
    xml = (
        shifted_xml
        if shifted_xml is not None
        else substrate_entries[region.sheet_part].decode("utf-8")
    )
    intended_map: Mapping[str, str] = (
        substrate_formulas if intended_formulas is None else intended_formulas
    )
    writes: list[CellWrite] = []
    preserved: dict[str, str] = {}

    def _emit(spec: FieldSpec, table: TableSpec, row: int, identity: str) -> None:
        column = _resolve_column(spec, table=table, region=region, binding=binding)
        coord = f"{column}{row}"
        key = _instantiate(spec.stable_field_key, identity)
        field = projection.get(key)
        if field is None:
            return
        view = _cell_view(xml, coord)
        restore = ""
        if spec.mode is FieldMode.formula:
            if view is None or not view.has_formula:
                raise ProtectedRegionWriteError(
                    f"契约把 {key!r} 声明为 formula，但 substrate 的 {coord} 没有公式 —— "
                    "契约/模板漂移，不得凭空写一个公式或把它当字面量覆盖（AC 6.6）"
                )
            observed = substrate_formulas.get(key, view.formula_text or "")
            intended = intended_map.get(key, observed)
            preserved[key] = intended
            if intended and _formula_body(intended) != _formula_body(observed):
                if not (view.formula_text or ""):
                    raise ProtectedRegionWriteError(
                        f"受保护格 {coord}（{key}）的公式与 base representation 不符"
                        f"（应为 {intended!r}，实测 {observed!r}），但它在 OOXML 上是共享公式"
                        f"组的**成员**（`<f t=\"shared\" si=...` 无文本）—— 成员的公式由主格"
                        "翻译而来，逐格还原不了；这种形态意味着主格被改写、整组已失效，"
                        "必须人工裁决而不是悄悄写回一格（AC 6.6）"
                    )
                restore = _formula_body(intended)
        elif spec.mode is FieldMode.auto_source:
            if view is not None and view.has_formula:
                raise ProtectedRegionWriteError(
                    f"契约把 {key!r} 声明为 auto_source（服务端字面量），但 substrate 的 "
                    f"{coord} 是公式 {view.formula_text!r} —— 写字面量会毁掉模板公式；"
                    "契约与模板必须先对齐（AC 6.6 / 3.5）"
                )
        elif view is not None and view.shared_ref and ":" in (view.shared_ref or ""):
            raise SharedFormulaMasterWriteError(
                f"契约把 {key!r} 声明为 {spec.mode.value}，但 {coord} 是共享公式主格 "
                f"(ref={view.shared_ref})—— 覆盖主格会让整组成员失效；"
                "该格要么改契约声明成 formula，要么先在模板里解开共享公式"
            )
        writes.append(
            CellWrite(
                coord=coord,
                kind=_write_kind_for(spec),
                value=_normalised_write_value(field, spec, coord),
                stable_field_key=key,
                row_key=identity,
                mode=spec.mode,
                formula_text=restore,
            )
        )

    for static_table in static_tables:
        for spec in static_table.fields:
            if spec.cell is None or spec.cell.static_row is None:
                continue
            _emit(spec, static_table, spec.cell.static_row, "")

    for identity in wanted:
        row = row_of_identity[identity]
        for spec in dynamic_table.fields:
            if spec.cell is None or spec.cell.row_from != "row_identity":
                continue
            _emit(spec, dynamic_table, row, identity)

    # ── 6.8a 新插入行的 row identity 必须落进隐藏 UUID 列 ──────────
    #
    # 🔴 不写的后果不是「少一列数据」而是**身份丢失**：反读时那几行的 UUID 列是空的，
    #    `_scan_row_identities` 按 `delete_policy=tombstone` 给它**重新 mint 一个新 ID**，
    #    于是 roundtrip 比对里 projection 声明的身份与实测身份对不上 —— 症状是
    #    「反读不等值」，真因却是「插行时没写身份」，两者相距很远。
    #
    #    minted 身份走下面那条既有分支（它们的物理行 Task 37 已经建好了）；
    #    这里处理的是**本次由我们插出来的**行。
    if row_shift is not None:
        for offset, identity in enumerate(orphan):
            writes.append(
                CellWrite(
                    coord=f"{region.uuid_column}{row_shift.insert_at + offset}",
                    kind=CellWriteKind.row_identity,
                    value=identity,
                    row_key=identity,
                )
            )

    for row, minted in sorted(scan.minted_by_row.items()):
        if minted not in set(wanted):
            raise RowIdentityWriteError(
                f"Task 37 为第 {row} 行 minted 了 identity {minted!r}，但 merged projection "
                "的行集里没有它 —— OO 新增行的身份必须先经三方 merge 进入 projection，"
                "写入侧不得自行决定要不要保留它"
            )
        writes.append(
            CellWrite(
                coord=f"{region.uuid_column}{row}",
                kind=CellWriteKind.row_identity,
                value=minted,
                row_key=minted,
            )
        )

    # ── 6.9 工作簿级传播声明（spec excel-workbook-wide-row-change-propagation）──
    #
    # 🔴 排在这里（计划期最后、写盘之前）而不是 apply 期：声明必须**先于**任何字节写入
    #    冻结，apply 与 verify 才能共用同一份。在 apply 期现扫等于事后观测。
    #
    #    零位移时不扫：不插行就没有行号变化要传播，代码路径与本 spec 之前逐字节相同
    #    （与 `row_shift is None` 同一条纪律）。
    workbook_row_change = None
    if row_shift is not None:
        workbook_row_change = plan_workbook_row_change_for_insert(
            substrate_entries,
            managed_sheet_name=region.sheet_name,
            managed_sheet_part=region.sheet_part,
            insert_at=row_shift.insert_at,
            count=row_shift.count,
            style_from=row_shift.style_from,
            region_first_row=region.first_row,
            region_last_row=region.last_row,
        )

    return MaterializePlan(
        sheet_part=region.sheet_part,
        sheet_name=region.sheet_name,
        writes=tuple(writes),
        preserved_formulas=dict(sorted(preserved.items())),
        dynamic_column_columns=dynamic_columns,
        footer_marker_row=footer_row,
        row_shift=row_shift,
        total_formula_rows=total_formula_rows,
        table_part=table_part,
        workbook_row_change=workbook_row_change,
    )


# ─────────────────────────────────────────────────────────────────────────
# 3.4 结构性插行计划（spec excel-structural-row-insertion-and-shift-aware-verification）
# ─────────────────────────────────────────────────────────────────────────
#
# 🔴 残余 fail-closed 分支的语义（Requirement 8.1~8.5）：
#
# `RowSetDivergenceError` **保留**。它从「一律拒绝插行」变成「算不出可安全执行的插行计划
# 时拒绝」。五类不可安全执行情形各自可达、两两可分辨 —— 每一类在消息里带自己的
# `error_code` 片段（`excel_row_shift_*` / `contract_static_row_below_insertion`），
# 于是「只断言抛了 RowSetDivergenceError」的守卫抓不住把两类合并的改动。


def _managed_table_part(entries: Mapping[str, bytes], *, table_name: str) -> str:
    """受管 Excel Table 的 zip part。找不到即 fail closed。

    插行后必须把它的 `ref` 行区间一起长上去，否则新行落在 Table 之外 ⇒ 反读时
    `resolve_managed_region` 仍返回旧区间，新行**根本不进 projection**（静默丢数据）。
    """
    # 🔴 part 名**不得**假设成 `tableN.xml`：H1 的注入产物实测叫
    #    `xl/tables/tableGtRowId.xml`。首版按 `table\d+\.xml` 匹配，于是在 H1 上定位不到，
    #    把「Table 名对不上」误报成「part 缺失」——同一类「手搓命名假设」的坑本 spec
    #    已在 sheet 定位上踩过一次（属性顺序不保证 / sheet 名含中文）。
    for name in sorted(entries):
        if not re.match(r"xl/tables/[^/]+\.xml$", name):
            continue
        xml = entries[name].decode("utf-8", errors="replace")
        for attr in ("displayName", "name"):
            found = re.search(rf'\b{attr}="([^"]*)"', xml)
            if found is not None and found.group(1) == table_name:
                return name
    return ""


def _static_rows_at_or_below(
    *, contract: SyncContract, insert_at: int
) -> tuple[tuple[str, str], ...]:
    """契约声明的**静态行**里落在插入点及其之下的那些（第五类拒绝理由）。

    🔴 这一条是本 spec 实施中实测发现的，design.md 未覆盖：

    `plan_managed_writes` 对静态字段用契约的 `cell.static_row` 逐格定位，而 Task 37 的
    extract **也**用同一个固定行号反读。插行把 `static_row >= insert_at` 的格整体推下去
    之后，两侧就对不上了 —— extract 在旧行号上读到的是一个**新插入的空行**，
    于是静默取到空值。这正是原实现对 footer 下移 fail closed 的理由（源码注释原文：
    「跟随 footer 需要读写两侧一起改，登记为后续任务」）。

    本 spec 的 Requirement 7.1 允许 footer marker 按声明位移，若不同时拦住这一条，
    就等于把那条静默错值路径放开了。

    实测：K11 契约的 `k11_footer/tb_amount` 在 **B27**，而追加插行的插入点是 26
    ⇒ K11 在读侧跟随落地之前**不可安全插行**。这不是缺陷而是正确的 fail closed；
    解除条件 = extract 侧的静态行定位也变成位移感知（读写两侧一起改）。
    """
    return tuple(
        (spec.stable_field_key, f"{spec.cell.column}{spec.cell.static_row}")
        for sheet in contract.sheets
        for table in sheet.tables
        for spec in table.fields
        if spec.cell is not None
        and spec.cell.static_row is not None
        and spec.cell.static_row >= insert_at
    )


def _static_row_reason(offenders: Sequence[tuple[str, str]], insert_at: int) -> str:
    return (
        f"契约声明的静态格 {list(offenders[:3])}（共 {len(offenders)} 个）落在插入点 "
        f"{insert_at} 及其之下 —— 插行会把它们整体推下去，而 Task 37 的 extract 仍按契约 "
        "`static_row` 反读固定行号，于是在旧行号上读到一个**新插入的空行**（静默取空值）。"
        "解除条件：extract 侧的静态行定位同样变成位移感知（读写两侧一起改）"
    )


def _plan_row_shift(
    *,
    orphan: Sequence[str],
    contract: SyncContract,
    region: ManagedRegion,
    scan: RowIdentityScan,
    substrate_entries: Mapping[str, bytes],
    runtime_binding: Mapping[str, str],
) -> tuple[RowShiftPlan, tuple[int, ...], str, str]:
    """由 orphan 身份数算出**可安全执行**的插行计划。

    Returns:
        `(计划, 契约声明带合计公式的行号, 受管 Table 的 zip part, 位移后的 sheet XML)`

    🔴 位移后的 XML 一并返回，不是顺手：计划期的逐字段判据（`formula` 模式要求该格
    在 substrate 上**已有公式**）必须对着**位移后**的形态求值 —— 新插入行在 substrate 上
    根本不存在，拿 substrate 求 `_cell_view` 会报「H27 没有公式」，而那是问错了 artifact。
    这与 footer 两门的两相划分同源：计划期看到的结构必须是「本次写入将要落在的那个结构」。

    Raises:
        RowSetDivergenceError: 任一类不可安全执行情形。消息里带该类专属的 `error_code`
            片段，五类两两可分辨（Requirement 8.4 / 8.5）。
    """
    # 🔴 每一条拒绝消息都必须带 **orphan 身份清单**（Requirement 8.2「在消息中给出具体
    #    拒绝原因」）：拒绝的起因是「这几个身份在 substrate 上没有物理行」，只报「插行不可
    #    安全执行」的话，排查要从头复现一遍才知道是哪几行。既有守卫也按身份名匹配消息。
    def _reject(code: str, detail: str) -> RowSetDivergenceError:
        return RowSetDivergenceError(
            f"[{code}] merged projection 的行身份 {list(orphan[:3])}（共 {len(orphan)} 个）"
            f"在 substrate 上没有物理行，需要结构性插行；但该插行**不可安全执行**：{detail}"
        )

    last_data_row = max(scan.row_identity_by_row) if scan.row_identity_by_row else region.last_row
    if last_data_row > region.last_row:
        raise _reject(
            "excel_row_shift_plan_range_invalid",
            f"实测最后一个数据行 {last_data_row} 落在受管区域末行 {region.last_row} 之外 —— "
            "受管区域与物理行集已不自洽，不得据此算插入点",
        )
    insert_at = last_data_row + 1
    offenders = _static_rows_at_or_below(contract=contract, insert_at=insert_at)
    if offenders:
        raise _reject("contract_static_row_below_insertion", _static_row_reason(offenders, insert_at))

    try:
        plan = RowShiftPlan(
            insert_at=insert_at,
            count=len(orphan),
            style_from=last_data_row,
            table_key=region.table_key,
        )
    except RowShiftError as exc:
        raise _reject(
            type(exc).error_code,
            f"算不出合法的插行计划（插入点 {insert_at}、插 {len(orphan)} 行、"
            f"样式源 {last_data_row}）：{exc}",
        ) from exc

    anchor = next(
        (
            table.footer_anchor
            for sheet in contract.sheets
            for table in sheet.tables
            if table.footer_anchor is not None
        ),
        None,
    )
    total_formula_rows: tuple[int, ...] = ()
    if anchor is not None and anchor.carries_total_formula:
        raw = str(runtime_binding.get("GT_FOOTER_ROW", "")).strip()
        if not raw.isdigit():
            raise _reject(
                "excel_row_shift_plan_range_invalid",
                "契约声明 footer 携带合计公式，但 runtime binding 的 "
                f"GT_FOOTER_ROW={raw!r} 不是行号 —— 无从确定该扩张哪一行的区间",
            )
        # 🔴 取**冻结声明**而不是现场搜 marker：扩张的目标行必须是声明值，
        #    从 substrate 观测出来的行号会把「footer 已被人挪过」当成合法。
        total_formula_rows = (int(raw),)

    table_part = _managed_table_part(substrate_entries, table_name=region.table_name)
    if not table_part:
        raise _reject(
            "excel_row_shift_table_part_missing",
            f"受管 Excel Table {region.table_name!r} 的 part 在 zip 里定位不到"
            f"（实测 {sorted(n for n in substrate_entries if n.startswith('xl/tables/'))}）—— "
            "插行后 Table ref 无从增长，新行会落在受管区域之外并被静默丢弃",
        )

    # 🔴 **干跑**一次纯函数位移来验证可安全执行。产物丢弃 —— 真正的位移在
    #    `apply_plan_zip` 里发生（Property 9：计划期失败 ⇒ 零产物）。
    #    干跑而不是「等写盘时再抛」的理由：结构判据必须先于任何字节写入。
    try:
        shifted_xml, _ = shift_sheet_rows(
            substrate_entries[region.sheet_part].decode("utf-8"),
            plan,
            total_formula_rows=total_formula_rows,
        )
    except RowShiftError as exc:
        raise _reject(type(exc).error_code, str(exc)) from exc

    return plan, total_formula_rows, table_part, shifted_xml


def _resolve_column(
    spec: FieldSpec,
    *,
    table: TableSpec,
    region: ManagedRegion,
    binding: ExcelIdentityBinding,
) -> str:
    """受管字段的 Excel 列。

    动态列走 `binding.dynamic_column_columns` 的**实测绑定**（`{slot}_{seq}` → 列），
    静态列走契约声明列。与 Task 37 `_resolve_field_column` 同一套语义 —— 两侧若各写一套
    就会出现「写在 E 列、反读 F 列」。本函数只在 Task 38 需要的形态上实现，并由
    `test_column_resolution_agrees_with_extractor` 与 Task 37 双向锁死。
    """
    cell = spec.cell
    if cell is None:
        raise EditableCellWriteError(
            f"受管字段 {spec.stable_field_key!r} 缺 cell 声明 —— 契约校验器本应拦住"
        )
    if table.dynamic_columns is None or spec.column_key is None:
        return cell.column
    bound = binding.dynamic_column_columns.get(table.table_key, {})
    column = bound.get(spec.column_key)
    if not column:
        raise DynamicColumnWriteError(
            f"契约表 {table.table_key!r} 的动态列 {spec.column_key!r} 没有实测列绑定"
            f"（已绑定 {sorted(bound)}）—— 不得按声明列右移猜（Requirement 6.4）"
        )
    if not region.contains_column(column):
        raise DynamicColumnWriteError(
            f"动态列 {spec.column_key!r} 绑定到 {column}，落在 Table ref "
            f"{region.table_ref} 的列跨度之外"
        )
    return column


# ═══════════════════════════════════════════════════════════════════════════
# 4. 写盘
# ═══════════════════════════════════════════════════════════════════════════


def assert_output_outside_template_library(output: Path) -> None:
    """输出路径不得落在 `backend/wp_templates/` 之下（Requirement 9.9）。

    判据是**解析后的绝对路径分量**，不是字符串前缀比较：`..` 拼出来的路径靠字符串比较
    看不出来。
    """
    resolved = output.resolve()
    if TEMPLATE_LIBRARY_MARKER in resolved.parts:
        raise TemplateLibraryWriteError(
            f"materialize 输出 {resolved} 落在模板库（路径分量含 "
            f"{TEMPLATE_LIBRARY_MARKER!r}）—— 运行时不得写回 `backend/wp_templates/`，"
            "它是唯一权威源（Requirement 9.9 / 6.13）"
        )


def apply_plan_zip(source_bytes: bytes, plan: MaterializePlan) -> bytes:
    """zip 级定点修改：只改受管 sheet part，其它条目**逐字节原样搬运**。

    本函数是**简facade**，丢掉 :class:`ShiftReport`。需要报告的调用方走
    :func:`apply_plan_zip_with_report` —— 两者共用同一份实现，不是两条路径。
    保留这个签名是为了让既有调用点与守卫逐字不变（`plan.row_shift is None` 时行为与本 spec
    之前完全相同）。
    """
    data, _ = apply_plan_zip_with_report(source_bytes, plan)
    return data


def apply_plan_zip_with_report(
    source_bytes: bytes, plan: MaterializePlan
) -> tuple[bytes, ShiftReport | None]:
    """zip 级定点修改 + 结构性插行。返回 `(新字节, ShiftReport | None)`。

    ═══ 阶段顺序不可交换（Requirements 2.3 / 3.2）═══

    Spec: excel-structural-row-insertion-and-shift-aware-verification

    1. **位移排最先** —— `shift_sheet_rows`（含合计区间扩张）。
    2. Table ref 行区间随之增长。
    3. 最后才 `_patch_sheet_xml` 写格。

    🔴 为什么位移必须先于写格：写格阶段用 `_cell_view` 按**坐标**定位，而
    `plan_managed_writes` 算出来的坐标已经是**位移后**的行号（orphan 身份落在
    `insert_at..insert_at+count-1`）。先写格再位移会让同一次遍历里前后坐标语义不一致 ⇒
    静默错位（design.md 拒绝方案第 5 条）。

    🔴 `plan.row_shift is None` 时代码路径与本 spec 之前**逐字节相同**：不解析 Table part、
    不调位移函数、`ShiftReport` 为 `None`（Property 3）。
    """
    entries = _read_entries(source_bytes)
    if plan.sheet_part not in entries:
        raise EditableCellWriteError(
            f"受管 sheet part {plan.sheet_part!r} 不在 substrate zip 里"
        )
    xml = entries[plan.sheet_part].decode("utf-8")

    report: ShiftReport | None = None
    if plan.row_shift is not None:
        # 阶段 1：位移 + 合计扩张（纯函数，同输入恒得同输出）
        xml, report = shift_sheet_rows(
            xml, plan.row_shift, total_formula_rows=plan.total_formula_rows
        )
        # 阶段 2：Table ref 随之增长 —— 不长的话新行落在受管区域之外，
        #        反读时 `resolve_managed_region` 仍返回旧区间 ⇒ 新行被静默丢弃。
        entries = _grow_managed_table_ref(entries, plan=plan)
        # 阶段 2b：**引用侧** sheet 与 definedNames 的工作簿级传播。
        #
        # 🔴 顺序在写格**之前**、位移之后：传播只改行号，与写格的坐标无关；但若排在写格
        #    之后，写格产生的新字节会进入传播的输入 ⇒ 声明与实测的对账口径就不再是
        #    「计划期冻结的那份」。
        entries = _apply_workbook_propagation(entries, plan=plan)
        # 阶段 2c：隐藏 `_GT_SYNC` 的 runtime binding 重冻结。
        #
        # 🔴 排在与 Table ref 增长同一相：Table `ref` 已经长了、footer 已经在 apply 后
        #    位移，若 `_GT_SYNC` 仍冻结 instrumentation 时刻的骨架态，之后每次 runtime
        #    materialize 都会拿位移过的 artifact 当 substrate 却按骨架值校验 footer ⇒
        #    永久 `excel_materialize_footer_anchor_drift`（实测 D2：插入 717 行后 footer
        #    在 755、冻结仍是 26）。三个坐标与 Table ref 必须**同源**增长。
        #
        #    排在写格之前 ⇒ 写格产生的新字节不进重冻结的输入，与阶段 2b 的对账口径一致。
        entries = _refresh_gt_sync_runtime_binding(
            entries, plan=plan, source_bytes=source_bytes
        )

    # 阶段 3：写格（坐标已是位移后行号）
    entries[plan.sheet_part] = _patch_sheet_xml(xml, plan.writes).encode("utf-8")
    return _write_entries(entries), report


def _apply_workbook_propagation(
    entries: dict[str, bytes], *, plan: MaterializePlan
) -> dict[str, bytes]:
    """按 `plan.workbook_row_change` 的**声明**改引用侧 sheet 与 definedNames。

    🔴 **逐条按声明改，不重跑扫描。** 计划期已经把「改哪些位置、改成什么」冻结进
    `PropagationEntry`；这里若重新扫一遍再改，apply 与 plan 就成了两个真源，
    而 `verify_unmanaged_regions` 的归一化只认 plan 那一份 ⇒ 任何不一致都会表现为
    「验证判漂移」而真因是「apply 没按声明做」。

    `plan.workbook_row_change is None` 时逐字节不动（零传播路径）。
    """
    change = plan.workbook_row_change
    if change is None:
        return entries
    from app.services.workpaper_sync.excel_workbook_row_change import (
        PropagationDriftError,
        _escape,
    )

    by_part: dict[str, list[Any]] = {}
    for entry in change.propagations:
        by_part.setdefault(entry.part, []).append(entry)

    for part, part_entries in sorted(by_part.items()):
        if part == plan.sheet_part:
            # 受管 sheet 自身的引用由 `shift_sheet_rows` 处理（裸引用 + 自限定），
            # 不在这里重复改 —— 重复会双重位移。
            continue
        if part not in entries:
            raise PropagationDriftError(
                f"计划声明要改 {part}，但它不在 substrate zip 里 —— "
                "声明与 artifact 不匹配，不得带着对不上的计划写盘"
            )
        text = entries[part].decode("utf-8")
        # 长的先替换：短的 ref_before 可能是长的子串（`!A2` ⊂ `!A25`）
        pairs: dict[tuple[str, str], int] = {}
        for entry in part_entries:
            key = (entry.ref_before, entry.ref_after)
            pairs[key] = pairs.get(key, 0) + 1
        applied = 0
        for before, after in sorted(pairs, key=lambda kv: len(kv[0]), reverse=True):
            for cand_before, cand_after in (
                (_escape(before), _escape(after)),
                (before, after),
            ):
                hits = text.count(cand_before)
                if hits:
                    text = text.replace(cand_before, cand_after)
                    applied += hits
                    break
        declared = len(part_entries)
        if applied != declared:
            raise PropagationDriftError(
                f"{part}：声明 {declared} 处传播，实际只改了 {applied} 处 —— "
                "计划期扫到的引用在 apply 期找不到（artifact 在两相之间被动过？）"
            )
        entries[part] = text.encode("utf-8")
    return entries


def assert_shifted_footer_gates(
    *,
    staged_bytes: bytes,
    plan: MaterializePlan,
    contract: SyncContract,
    region: ManagedRegion,
    runtime_binding: Mapping[str, str],
) -> int | None:
    """位移**之后**在 staged 产物上复核 footer 两门（Requirements 7.1 / 7.4）。

    Spec: excel-structural-row-insertion-and-shift-aware-verification

    ═══ 为什么必须是独立的第二相 ═══

    计划期的两门跑在 substrate 上，而 substrate 还没被位移 —— 在那里要求「实测 == 冻结 +
    位移」是错的（H1 实测当场打红：marker 在冻结行 28、计划插 1 行，判据期待 29）。
    位移后的判据只有在**已位移的产物**上才有意义：

    * footer marker 必须恰好落在 `冻结 + 声明位移` 上 —— 多一行少一行都是声明之外的下移；
    * 合计区间必须覆盖位移后的受管末行 —— 契约声明了 `carries_total_formula` 时它已在
      位移阶段被扩张，没声明时计划期第六类拒绝理由早就拦住了。

    🔴 调用点放在 `os.replace` **之前**：判据不过即零产物（Property 9）。
    """
    if plan.row_shift is None:
        return None
    entries = _read_entries(staged_bytes)
    footer_row = assert_footer_anchor_stable(
        entries=entries,
        sheet_part=plan.sheet_part,
        contract=contract,
        runtime_binding=runtime_binding,
        row_shift=plan.row_shift,
    )
    if footer_row is None:
        return None
    anchor = next(
        (
            table.footer_anchor
            for sheet in contract.sheets
            for table in sheet.tables
            if table.footer_anchor is not None
        ),
        None,
    )
    assert_footer_formula_covers_managed_rows(
        entries=entries,
        sheet_part=plan.sheet_part,
        footer_row=footer_row,
        region=region,
        row_shift=plan.row_shift,
        carries_total_formula=bool(anchor and anchor.carries_total_formula),
    )
    return footer_row


def _grow_managed_table_ref(
    entries: dict[str, bytes], *, plan: MaterializePlan
) -> dict[str, bytes]:
    """把受管 Excel Table 的 `ref` 末行按 `plan.row_shift.count` 长上去。

    只改 `ref` 的**行**分量，列跨度逐字保留 —— `assert_identity_inventory_retained`
    只锁列跨度，「行区间随插删行变化属合法」。`_classify_parts` 又把 `xl/tables/**`
    整类排除，所以这不是未管理区域漂移。

    Table part 在计划期就已定位（`_plan_row_shift` → `_managed_table_part`），
    这里不再现搜 —— 现搜等于把「定位失败」推到写盘期，而那时已经有字节落地了。
    """
    shift = plan.row_shift
    assert shift is not None, "调用方保证"
    part = plan.table_part
    if not part or part not in entries:
        raise RowSetDivergenceError(
            f"[excel_row_shift_table_part_missing] 计划里的 Table part {part!r} 不在 zip 里 —— "
            "插行后 Table ref 无从增长，新行会落在受管区域之外并被静默丢弃"
        )
    xml = entries[part].decode("utf-8")
    changed = 0

    def _one(match: re.Match[str]) -> str:
        nonlocal changed
        head, tail = match.group("ref").split(":", 1)
        head_col, head_row = re.sub(r"\d", "", head), int(re.sub(r"\D", "", head) or 0)
        tail_col, tail_row = re.sub(r"\d", "", tail), int(re.sub(r"\D", "", tail) or 0)

        # 首行：落在插入点及其之下 ⇒ 整体下移（`plan.shift` 自带这个边界）。
        new_head_row = shift.shift(head_row)
        # 末行：两种形态**同一个算式**，判据是 `tail_row >= insert_at - 1`
        #   ① `tail_row >= insert_at`      → 末行被推下去 ⇒ +count（位移）
        #   ② `tail_row == insert_at - 1`  → **追加插行**：新行紧贴 Table 末行之后，
        #                                     Table 必须长上去把它们包进来 ⇒ +count（增长）
        # 🔴 首版写成 `if tail_row < insert_at: 不动`，把形态 ② 判成了「不动」——
        #    而追加插行**恰好**总是形态 ②（`insert_at = 最后一个数据行 + 1`），
        #    于是每一次真实插行都撞「ref 一处都没长」。
        new_tail_row = (
            tail_row + shift.count if tail_row >= shift.insert_at - 1 else tail_row
        )
        if (new_head_row, new_tail_row) == (head_row, tail_row):
            return match.group(0)
        changed += 1
        return (
            f'{match.group("prefix")}{head_col}{new_head_row}:'
            f'{tail_col}{new_tail_row}"'
        )

    xml_new = re.sub(
        r'(?P<prefix>\bref=")(?P<ref>[A-Z]{1,3}\d+:[A-Z]{1,3}\d+)"', _one, xml
    )
    if not changed:
        raise RowSetDivergenceError(
            f"[excel_row_shift_table_ref_not_grown] Table part {part} 的 ref 一处都没长"
            f"（插入点 {shift.insert_at}，插 {shift.count} 行，实测 ref: "
            f"{re.findall(r'ref=\"[^\"]+\"', xml)[:3]}）—— 新行会落在受管区域之外，"
            "反读时静默丢数据"
        )
    entries[part] = xml_new.encode("utf-8")
    return entries


def _gt_sync_sheet_part(entries: dict[str, bytes], source_bytes: bytes) -> str:
    """定位隐藏 `_GT_SYNC` 部件；定位不到即 fail closed。

    走 `read_runtime_binding_pairs` 的**唯一读侧入口**定位（Requirement 6.14），不在本
    模块抄第二份 workbook rels 解析 —— 那会出现「Task 17 改了载体形态、本模块还是老
    定位」的第二真源，且症状是静默读空。
    """
    from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME
    from app.services.workpaper_sync.excel_extract import read_runtime_binding_pairs

    import zipfile

    with zipfile.ZipFile(io.BytesIO(source_bytes)) as zf:
        read_runtime_binding_pairs(zf)  # 先校验载体存在（缺失会自己抛语义化错误）
        part = _sheet_parts_for(zf).get(GT_SYNC_SHEET_NAME)
    if part is None:
        raise RowSetDivergenceError(
            "[excel_row_shift_gt_sync_part_missing] 隐藏 metadata sheet 在 workbook 清册里"
            "定位不到 —— runtime binding 是 representation 身份的一部分，"
            "无法重冻结即 fail closed"
        )
    return part


def _sheet_parts_for(zf: zipfile.ZipFile) -> dict[str, str]:
    """复用 extract 侧的 sheet 定位（唯一真源），避免本模块第二次手写 rels 解析。"""
    from app.services.workpaper_sync.excel_extract import _sheet_parts

    return _sheet_parts(zf)


def _refresh_gt_sync_runtime_binding(
    entries: dict[str, bytes], *, plan: MaterializePlan, source_bytes: bytes
) -> dict[str, bytes]:
    """按 `plan.row_shift` 重冻结隐藏 `_GT_SYNC` 的受管结构坐标。

    ═══ 为什么这一步不可少 ═════════════════════════════════════════════════════

    结构性插行会把受管区末行、footer、row UUID 区间整体推下去，Table `ref` 也在
    阶段 2 跟着长了。但 `_GT_SYNC` 冻结的是 **instrumentation 时刻的骨架态**（例如
    D2：`GT_FOOTER_ROW=26`、`GT_ROW_UUID_LAST_ROW=24`，而插入 717 行后 footer 实测在
    755、UUID 末行是 753）。全库只有 `excel_instrumentation` 一处写这些键，插行后
    没有任何地方重冻结 ⇒ 三个后果：

    * 之后每次 runtime `materialize` 拿位移过的 artifact 当 substrate，却仍按骨架值校验
      footer ⇒ 永久 `excel_materialize_footer_anchor_drift`（实测 D2 就停在这里）；
    * `verify_unmanaged_regions` / identity 反读的坐标声明与物理结构不同源，「声明与实况
      不符」本身是一类缺陷（见 `excel_typography_rows` 模块 docstring）；
    * representation 的可重现性依赖这些冻结值 ⇒ 错值会被当成合法身份冻结下来。

    🔴 只改**受位移影响**的键，其余键逐字保留 —— 那些是 instrumentation 阶段的
    模板事实（`GT_TEMPLATE_SHA256` 等），插行不该动它们。

    🔴 `plan.row_shift is None` 时调用方不会进来（与 `_grow_managed_table_ref` 同相）。

    Spec: published-representation-production-path-and-lane-adjudication
    """
    shift = plan.row_shift
    assert shift is not None, "调用方保证"

    from app.services.workpaper_sync.excel_instrumentation import _gt_sync_sheet_xml

    part = _gt_sync_sheet_part(entries, source_bytes)
    if part not in entries:
        raise RowSetDivergenceError(
            f"[excel_row_shift_gt_sync_part_missing] 隐藏 metadata sheet 定位到部件"
            f" {part!r}，但它不在待写入的 entries 里 —— 无法重冻结即 fail closed"
        )
    xml = entries[part].decode("utf-8")

    import re as _re

    pairs: list[tuple[str, str]] = []
    for m in _re.finditer(
        r'<c r="A(\d+)"[^>]*>\s*<is>\s*<t[^>]*>(.*?)</t>', xml, _re.S
    ):
        row = int(m.group(1))
        key = _unesc(m.group(2))
        val_m = _re.search(
            r'<c r="B' + str(row) + r'"[^>]*>\s*<is>\s*<t[^>]*>(.*?)</t>', xml, _re.S
        )
        value = _unesc(val_m.group(1)) if val_m else ""
        pairs.append((key, value))

    if not pairs:
        raise RowSetDivergenceError(
            f"[excel_row_shift_gt_sync_empty] 隐藏 metadata sheet（部件 {part}）里"
            "一对 key/value 都读不到 —— 载体形态与写侧不符，不得当成「未冻结任何绑定」继续"
        )

    pair_map = dict(pairs)
    uuid_col = str(pair_map.get("GT_ROW_UUID_COLUMN") or "")
    table_ref = str(pair_map.get("GT_MANAGED_TABLE_REF") or "")
    old_last_row = _to_int(dict(pairs).get("GT_ROW_UUID_LAST_ROW"), what="GT_ROW_UUID_LAST_ROW")
    old_footer_row = _to_int(
        dict(pairs).get("GT_FOOTER_ROW"), what="GT_FOOTER_ROW", required=False
    )

    new_pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in pairs:
        seen.add(key)
        if key == "GT_ROW_UUID_LAST_ROW":
            # 末行同样适用「追加插行紧贴末行之后 ⇒ 必须包进来」的边界（见
            # `_grow_managed_table_ref` 的同名算式），与 Table ref 增长保持同源。
            new_value = str(old_last_row + shift.count if old_last_row >= shift.insert_at - 1 else old_last_row)
        elif key == "GT_FOOTER_ROW" and old_footer_row is not None:
            # `shift.shift()` 自带「footer 在插入点之上时不动」的边界 ⇒ 不在这里写 if。
            new_value = str(shift.shift(old_footer_row))
        elif key == "GT_MANAGED_RANGE":
            new_value = _grow_range_string(value, shift) if value else value
        elif key == "GT_MANAGED_TABLE_REF":
            new_value = _grow_range_string(value, shift) if value else value
        else:
            new_value = value
        new_pairs.append((key, new_value))

    # ── 模板更新预留 ─────────────────────────────────────────────────
    #
    # `GT_TEMPLATE_SHA256` 冻结的是「模板字节」，插行只改受管区结构坐标 ⇒ 两者必须
    # 分离，否则模板升级时无法区分「模板变了」与「数据行数变了」：
    #   * `GT_LAST_SHIFT`      —— 本 artifact 相对模板骨架的**累计**位移声明
    #                            （含插入点与行数），模板升级后可据此重放；
    #   * `GT_STRUCTURE_FINGERPRINT` —— 位移**后**的受管结构坐标摘要（不含数据值），
    #                            模板变了但行数不变 ⇒ 走行位移重放而非重新发布；
    #                            模板变了且行数也变 ⇒ 提示重新发布，不被静默当成数据漂移。
    last_shift = dict(new_pairs).get("GT_LAST_SHIFT") or ""
    total_inserted = len([p for p in (last_shift.split("|") if last_shift else []) if p]) if last_shift else 0
    try:
        total_inserted = int(last_shift.split("|")[-1]) if last_shift else 0
    except ValueError:
        total_inserted = 0
    total_inserted += shift.count

    fingerprint = _structure_fingerprint(
        last_row=old_last_row + (
            shift.count if old_last_row >= shift.insert_at - 1 else 0
        ),
        footer_row=shift.shift(old_footer_row) if old_footer_row is not None else 0,
        uuid_col=uuid_col,
        table_ref=table_ref,
    )

    for extra in (
        ("GT_LAST_SHIFT", f"{shift.insert_at}|{shift.count}|{total_inserted}"),
        ("GT_STRUCTURE_FINGERPRINT", fingerprint),
    ):
        if extra[0] in seen:
            new_pairs = [(k, (extra[1] if k == extra[0] else v)) for k, v in new_pairs]
        else:
            new_pairs.append(extra)

    entries[part] = _gt_sync_sheet_xml(new_pairs)
    return entries


def _unesc(text: str) -> str:
    """XML 文本反转义（与 extract 侧 `_xml_unescape` 同语义，键值均为纯文本）。"""
    from app.services.workpaper_sync.excel_extract import _xml_unescape

    return _xml_unescape(text)


def _to_int(raw: str | None, *, what: str, required: bool = True) -> int | None:
    """runtime binding 值 → int；非数字即 fail closed（与 footer 判据的口径一致）。"""
    if raw is None:
        if required:
            raise RowSetDivergenceError(
                f"[excel_row_shift_binding_missing] runtime binding 缺 {what} —— "
                "受管结构坐标无从重冻结，不得当成「没有该坐标」继续"
            )
        return None
    text = str(raw).strip()
    if not text.isdigit():
        raise RowSetDivergenceError(
            f"[excel_row_shift_binding_invalid] runtime binding 的 {what}={text!r} 不是行号"
            " —— 位移算术需要整数值"
        )
    return int(text)


def _grow_range_string(raw: str, shift: "RowShiftPlan") -> str:
    """`A13:AM24` 形态 → 末行按插行增长。首行按 `shift.shift` 位移。

    算式与 `_grow_managed_table_ref` 逐条对齐：首行落插入点及其之下 ⇒ 整体下移；
    末行 `>= insert_at - 1` ⇒ 追加插行也要包进来（追加总是这种形态）。
    """
    import re as _re

    m = _re.match(r"^(?P<hc>[A-Z]{1,3})(?P<hr>\d+):(?P<tc>[A-Z]{1,3})(?P<tr>\d+)$", raw.strip())
    if m is None:
        raise RowSetDivergenceError(
            f"[excel_row_shift_range_invalid] runtime binding 的受管区 {raw!r} 不是 A1 区间"
            " —— 无从按插行增长"
        )
    head_row = int(m.group("hr"))
    tail_row = int(m.group("tr"))
    new_head = shift.shift(head_row)
    new_tail = tail_row + shift.count if tail_row >= shift.insert_at - 1 else tail_row
    return f"{m.group('hc')}{new_head}:{m.group('tc')}{new_tail}"


def _structure_fingerprint(
    *, last_row: int, footer_row: int, uuid_col: str, table_ref: str
) -> str:
    """位移后的受管结构坐标摘要（**不含数据值**）。

    与 `GT_TEMPLATE_SHA256`（模板字节）分离，是「模板更新」的可判据：
    模板变了但指纹可重放 ⇒ 走行位移；模板变了且行数也变 ⇒ 提示重新发布。
    """
    import hashlib
    import json

    payload = json.dumps(
        {
            "last_row": last_row,
            "footer_row": footer_row,
            "uuid_col": uuid_col,
            "table_ref": table_ref,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def apply_plan_openpyxl(
    source: Path,
    plan: MaterializePlan,
    output: Path,
    *,
    decision: WriteStrategyDecision,
) -> None:
    """openpyxl 全量 roundtrip。**只有** :func:`select_write_strategy` 放行时才可调用。

    保留这条路径的理由：策略门若指向一个未实现的分支，那道门就是装饰品 —— 「被允许时
    会发生什么」必须真实可测（守卫用它证明「被放行的模板上这条路径真的能写出受管格」）。

    🔴 `decision` 是**必填**参数并在函数入口 fail closed，不是靠调用方自觉：把「只有放行
    时才可调用」写在 docstring 里等于没有判据 —— 任何新调用点漏判就直接全量重写一个含
    drawing/chart/pivot 的工作簿，而那类丢失要等未管理区域比对才发现（且 openpyxl 重写
    连 `verify_unmanaged_regions` 的 before/after 都会一起变，诊断指向完全错误的地方）。
    """
    if not decision.openpyxl_allowed:
        raise WriteStrategyForbiddenError(
            "openpyxl 全量重写未获放行，却被直接调用 —— 拒绝理由："
            + "；".join(decision.refusals or ("(策略未给出理由)",))
        )
    import openpyxl

    wb = openpyxl.load_workbook(source, data_only=False)
    try:
        if plan.sheet_name not in wb.sheetnames:
            raise EditableCellWriteError(
                f"受管 sheet {plan.sheet_name!r} 不在 workbook 里（{wb.sheetnames}）"
            )
        ws = wb[plan.sheet_name]
        for write in plan.writes:
            cell = ws[write.coord]
            if write.kind is CellWriteKind.cached_value_only:
                # openpyxl 不保留「公式 + 缓存值」两者 ⇒ 公式格只能保公式本体。
                continue
            cell.value = write.value
        wb.save(output)
    finally:
        wb.close()


# ═══════════════════════════════════════════════════════════════════════════
# 5. 入口
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ExcelMaterializeOutcome:
    """一次 materialize 的全部产物。**不含**任何发布/提交面。"""

    result: MaterializeResult
    plan: MaterializePlan
    strategy: WriteStrategyDecision
    substrate_view: ExcelExtractOutcome
    staged_identity_inventory: RuntimeIdentityInventory
    #: 交给 Task 37 `verify_before_commit` 的 `baseline_formulas`：substrate 侧受保护格的
    #: 公式文本。它是「staged result 里这些格**应该**还是什么公式」的唯一依据。
    intended_formulas: Mapping[str, str]
    #: 结构性插行的**逐阶段实测计数**。`None` = 本次没插行。
    #:
    #: 🔴 存在的唯一理由是让守卫能断言「这条分支真的执行了」而不是「没报错」：一个什么
    #: 都没做的位移函数在「产物能打开」这类判据下照样通过（spec
    #: excel-structural-row-insertion-and-shift-aware-verification）。
    shift_report: ShiftReport | None = None

    @property
    def output_path(self) -> Path:
        return self.result.output_path

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_sha256": self.result.artifact_sha256,
            "structure_hash": self.result.structure_hash,
            "identity_inventory_sha256": self.result.identity_inventory_sha256,
            "managed_field_count": self.result.managed_field_count,
            "plan": self.plan.as_dict(),
            "strategy": self.strategy.as_dict(),
            "intended_formula_count": len(self.intended_formulas),
            "substrate_identity_inventory_sha256": (
                self.substrate_view.identity_inventory.inventory_digest
            ),
            "staged_identity_inventory_sha256": (
                self.staged_identity_inventory.inventory_digest
            ),
            "shift_report": (
                None if self.shift_report is None else self.shift_report.as_dict()
            ),
        }


def materialize_projection(
    *,
    substrate: Path,
    projection: Projection,
    output: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    substrate_role: SubstrateRole | str,
    substrate_kind: ArtifactKind | str,
    substrate_state: ArtifactState | str,
    capability: ExcelWriteCapability | None = None,
    intended_formulas: Mapping[str, str] | None = None,
    limits: SyncLimits | None = None,
) -> ExcelMaterializeOutcome:
    """把 projection 写进 substrate 的**副本**，产出 staged 文件。

    执行顺序即判据（不可交换）：

    1. **frozen 身份门**（Task 36 `assert_engine_entry_definitions`）—— candidate /
       unapproved bundle / contract digest 漂移在写第一个字节之前就被拒；
    2. **substrate 准入**（Task 13 `assert_substrate_usable`）—— quarantined incoming 与
       upgrade candidate 在 engine 入口拒绝（AC 8.10）；
    3. **输出路径不得落在模板库**；
    4. **读 substrate 的 identity 与公式**（Task 37 `extract_projection`）；
    5. **写入策略裁决**（zip patch 默认）；
    6. **算写入计划**（含 footer / 动态列 / 行集三道结构判据）；
    7. **写临时文件再原子改名**成 `output` —— 校验失败时盘上不会留半成品
       （Property 9 的文件侧）；
    8. **反读 staged 产物的 identity inventory**，证明 minted UUID 真的落盘了。

    1 与 2 的先后是有意的：身份门失败时连 substrate 都不该被打开。
    """
    lim = limits or load_limits()
    assert_engine_entry_definitions(definitions)
    assert_substrate_usable(
        role=substrate_role, artifact_kind=substrate_kind, artifact_state=substrate_state
    )
    assert_output_outside_template_library(output)

    substrate_view = extract_projection(
        artifact=substrate,
        definitions=definitions,
        binding=binding,
        substrate_role=substrate_role,
        artifact_kind=substrate_kind,
        artifact_state=substrate_state,
        limits=lim,
    )
    strategy = select_write_strategy(artifact=substrate, capability=capability)
    source_bytes = substrate.read_bytes()
    entries = _read_entries(source_bytes)
    with zipfile.ZipFile(substrate) as zf:
        runtime_binding = read_runtime_binding_pairs(
            zf, metadata_sheet=binding.metadata_sheet
        )
    plan = plan_managed_writes(
        projection=projection,
        contract=definitions.contract,
        binding=binding,
        region=substrate_view.region,
        scan=substrate_view.scan,
        substrate_entries=entries,
        substrate_formulas=substrate_view.formula_inventory,
        runtime_binding=runtime_binding,
        intended_formulas=intended_formulas,
    )

    tmp = output.with_name(output.name + ".materializing")
    output.parent.mkdir(parents=True, exist_ok=True)
    shift_report: ShiftReport | None = None
    try:
        if strategy.strategy is ExcelWriteStrategy.openpyxl_roundtrip:
            if plan.row_shift is not None:
                # 🔴 openpyxl 全量重写与结构性插行不得叠加：openpyxl 实测在 K11 上丢 18 个
                #    zip 部件、把 12 个共享公式组摊平（见本模块 §四第 4 条与
                #    excel_sheet_visibility 的模块 docstring）。位移逻辑是 zip 级定点改写，
                #    与它混用会让「位移正确」与「重写毁坏」互相掩盖。
                raise RowSetDivergenceError(
                    "[excel_row_shift_strategy_conflict] 本次需要结构性插行，但写入策略选中了 "
                    "openpyxl 全量重写 —— 两者不得叠加：位移是 zip 级定点改写，"
                    "openpyxl 重写会丢部件并摊平共享公式组，两类问题会互相掩盖"
                )
            apply_plan_openpyxl(substrate, plan, tmp, decision=strategy)
        else:
            staged, shift_report = apply_plan_zip_with_report(source_bytes, plan)
            if plan.row_shift is not None:
                # 🔴 apply 后的**位移后**相：这才是 Requirement 7.1「实测 == 冻结 + 预期
                #    位移」与 7.4「用位移后区间求值」真正成立的地方。
                #    放在 `os.replace` **之前** ⇒ 判据不过就零产物（Property 9）。
                assert_shifted_footer_gates(
                    staged_bytes=staged,
                    plan=plan,
                    contract=definitions.contract,
                    region=substrate_view.region,
                    runtime_binding=runtime_binding,
                )
            tmp.write_bytes(staged)
        os.replace(tmp, output)
    finally:
        if tmp.exists():
            tmp.unlink()

    staged_bytes = output.read_bytes()
    staged_inventory = _staged_identity_inventory(
        staged_bytes=staged_bytes,
        output=output,
        definitions=definitions,
        binding=binding,
        limits=lim,
    )
    return ExcelMaterializeOutcome(
        result=MaterializeResult(
            output_path=output,
            document_type=definitions.contract.document_type,
            artifact_sha256=hashlib.sha256(staged_bytes).hexdigest(),
            structure_hash=normalized_structure_hash(staged_bytes),
            identity_inventory_sha256=staged_inventory.inventory_digest,
            managed_field_count=len(plan.field_writes),
            # 🔴 BP-23：把**写盘前冻结的**三个结构性声明随产物一起带出去，
            #    让 `verify_unmanaged_regions` 的三个归一化入参真有生产调用方喂它们。
            #    此前它们生产零消费 ⇒ 任何插行 entry 的未管理区域比对必打红
            #    （D2 实测：238 → 632 项）。声明来自 `plan`，与 apply 用的是**同一份**，
            #    因此不是「事后从 diff 推断」（那等于让被检查对象自证合法）。
            row_shift=plan.row_shift,
            total_formula_rows=plan.total_formula_rows,
            workbook_row_change=plan.workbook_row_change,
        ),
        plan=plan,
        strategy=strategy,
        substrate_view=substrate_view,
        staged_identity_inventory=staged_inventory,
        intended_formulas=dict(sorted(plan.preserved_formulas.items())),
        shift_report=shift_report,
    )


def _staged_identity_inventory(
    *,
    staged_bytes: bytes,
    output: Path,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    limits: SyncLimits,
) -> RuntimeIdentityInventory:
    """反读 staged 产物的 identity 清册（Property 66 在写入侧的收口）。

    刻意**实测**而不是「拿 substrate 的清册加上我 minted 的那几个」：后者是自证式推导，
    「UUID 根本没写进去」时它照样给出正确答案。
    """
    entries = _read_entries(staged_bytes)
    with zipfile.ZipFile(output) as zf:
        region = resolve_managed_region(zf, contract=definitions.contract, binding=binding)
        xml = entries[region.sheet_part].decode("utf-8")
        raw: dict[int, str] = {}
        shared = _shared_strings(entries)
        for row in region.row_span:
            view = _cell_view(xml, f"{region.uuid_column}{row}")
            raw[row] = "" if view is None else _cell_text(view, shared)
        return read_runtime_identity_inventory(
            zf,
            region=region,
            binding=binding,
            raw_uuid_by_row=raw,
            limits=limits,
        )


def _cell_text(view: _CellView, shared: Sequence[str]) -> str:
    if 't="s"' in view.attrs:
        index = re.search(r"<v>(\d+)</v>", view.body)
        if index is not None and int(index.group(1)) < len(shared):
            return shared[int(index.group(1))].strip()
        return ""
    inline = re.search(r"<t[^>]*>(.*?)</t>", view.body, re.S)
    if inline is not None:
        return _xml_unescape(inline.group(1)).strip()
    value = re.search(r"<v>(.*?)</v>", view.body, re.S)
    return _xml_unescape(value.group(1)).strip() if value else ""
