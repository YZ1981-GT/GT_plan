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
import logging
import os
import re
import zipfile
import dataclasses
from dataclasses import dataclass, field as dataclass_field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Mapping, Sequence, Union

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
    # spec workpaper-sync-managed-row-convergence：
    #   * PROTECTED_MODES —— 收敛的清空分支要跳过受保护格（公式/auto_source 本就被
    #     roundtrip 豁免，清它只会毁模板）
    #   * is_template_skeleton_identity —— 模板骨架行不得当 stale 删除，与 roundtrip
    #     豁免共用同一真源
    PROTECTED_MODES,
    is_template_skeleton_identity,
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
    is_static_region,
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
    RowDeletionShift,
    plan_workbook_row_change_for_delete,
    plan_workbook_row_change_for_insert,
    # spec workpaper-sync-managed-row-convergence：受管行收敛的删行分支。
    # 🔴 该能力由 spec excel-workbook-wide-row-change-propagation 建成且测试全绿，
    #    但此前**生产零消费方**（本模块原先只 import insert 那一支）——本行是它的首个
    #    生产接线点，闭合「能力已建 ≠ 接线完整」这个平台反复出现的缺口形态。
    shrink_sheet_rows,
)
from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.merge import ValueNormalizationError, normalize_value

#: 位移载体协议：插行 `RowShiftPlan`、删行 `RowDeletionShift`，两者**鸭子兼容**
#: （`shift` / `unshift` / `count` / `insert_at`）。
#:
#: 🔴 消费侧一律按**协议（鸭子）**判、不按 `isinstance`：判方向用
#: `getattr(carrier, "deleted_rows", None)`。这个别名只为类型标注存在，
#: 运行期不做类型分派。与 `excel_extract.RowChangeCarrier` 同一处理。
RowChangeCarrier = Union[RowShiftPlan, RowDeletionShift]
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState, SyncDomainError

#: 降级/异常的可观测出口。本包既有约定（14 处 `logging.getLogger(__name__)`）。
logger = logging.getLogger(__name__)

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
    # 坐标索引（大表性能）
    "SheetCellIndex",
    "build_sheet_cell_index",
    "patch_sheet_xml_indexed",
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
    #: **整格清空**：只留 `<c r=".." s=".."/>`，无 `t`、无 `<v>`、无 `<is>`（保留样式）。
    #:
    #: 🔴 「清空」与「写空文本」在 OOXML 里是**两种不同的格**，混用会静默失败：
    #:    `inline_text` 对 `None` 与 `""` 都渲染成 `<is><t xml:space="preserve"></t></is>`
    #:    —— 一个**存在且值为空串**的格。extract 反读它得到 `""`（`xml:space="preserve"`
    #:    明确保留空串），于是 **cell 仍算有值** ⇒ 仍产出该字段的 key ⇒ roundtrip 判 `extra`。
    #:
    #:    这正是受管行收敛（6.8b）实测踩到的形态：清空 D4-1 R22 的 7 个字段后，6 个
    #:    amount 字段的 extra 消失了（`_render_number("")` 恰好落成 `<v></v>` 空数值节点，
    #:    openpyxl 读回 `None`），而 text 的 `label` **一个都没少** ⇒ 500 从 7 个 extra
    #:    降到 1 个就是卡在这里。amount 能工作是巧合而非设计（`<v></v>` 不是干净形态），
    #:    所以收敛对**所有** value_type 统一走本 kind，消除 text/number 的行为分叉。
    #:
    #:    先例同型：`boolean_literal` 对 `None` 也刻意落 `<c r=".."/>` 真空格而不是
    #:    `<v>0</v>`（后者把「未填」变成「填了 false」）。
    blank = "blank"
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

    #: 受管行收敛（spec workpaper-sync-managed-row-convergence）：substrate 上 store 已不
    #: 认领的受管行。**两者互斥**，由 6.8b 按「删后受管区还剩几行有身份数据行」分流：
    #:   * `stale_deleted` —— 剩 ≥1 行 ⇒ 删物理行（行号为**位移前**口径，降序删）
    #:   * `stale_cleared` —— 剩 0 行 ⇒ 只清 editable 字面值格（物理行与身份载体保留）
    #: 为空表示本次无收敛（store 未声明该 table，或两侧行集本就一致）。
    stale_deleted: tuple[int, ...] = ()
    stale_cleared: tuple[int, ...] = ()
    # ── 删行侧的位移声明（spec workpaper-sync-row-deletion-multi-region-propagation）──
    #: 本次删行的**位移载体**（`RowDeletionShift`）。`None` = 本次不删物理行。
    #:
    #: 🔴 **不复用 `workbook_row_change` 一个字段装两种声明**：`_apply_workbook_propagation`
    #: 与 `assert_shifted_footer_gates` 需要按 kind 分流（insert 走 `row_shift`、
    #: delete 走 `row_deletion`），共用一个字段就得在每个消费点做 `isinstance` 判断 ——
    #: 那是把 kind 信息从类型里挤到调用点，每个漏判的点都是一处静默错向。
    #:
    #: ⚠ 类型写 `Any` 与 `workbook_row_change` 同理（反向 import 会成环）。
    row_deletion: Any | None = None
    #: 本次删行要在**引用侧** sheet 与 `xl/workbook.xml` 上做的传播声明
    #: （`RowDeletionChangeSet`）。`None` = 零传播路径（产物与不产声明时逐字节相同）。
    deletion_change: Any | None = None
    #: 收敛被**降级**回清空分支的原因（可读文案）。空串 = 没降级。
    #:
    #: 🔴 必须可观测（进 `as_dict()`）：否则「删行功能上线了但在双向变更的 entry 上
    #: 从来没跑过」会成为一个看不见的空转 —— 那正是本平台反复踩的
    #: 「能力已建 ≠ 接线完整」的另一面（Requirement 9.2 / 9.6）。
    stale_clear_reason: str = ""
    #: 多 sheet：本次 materialize 的契约 ``sheet_key``（如 ``d42-managed``）。
    #: ``_refresh_gt_sync_runtime_binding`` 只重冻结本 sheet 的 ``GT_FOOTER_ROW_{TID}``，
    #: 避免 sibling 的 footer 键被主 sheet 插行误移位。
    managed_sheet_key: str | None = None
    #: 本次 materialize 的 region 物理 Excel Table displayName（如 ``GT_D41_MAIN_ROWS``）。
    #: 🔴 **同 sheet 双区**（一个 sheet_key 对应 N 个 template_id）时 sheet_key 不足以定位
    #: 本 region 的 ``GT_FOOTER_ROW_{TID}``；``_refresh_gt_sync_runtime_binding`` 用它经
    #: ``_GT_SYNC`` 的平行清册 ``GT_MANAGED_TABLES``/``GT_TEMPLATE_IDS`` 精确定位本区的
    #: per-template footer 键，只移位该键（不动 sibling 区）。
    managed_table_name: str | None = None

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
            # ── 收敛两分支 + 删行声明（Requirement 9.2 / 9.6：降级必须可读）──
            "stale_deleted": list(self.stale_deleted),
            "stale_cleared": list(self.stale_cleared),
            "stale_clear_reason": self.stale_clear_reason,
            "row_deletion": (
                None if self.row_deletion is None else self.row_deletion.as_dict()
            ),
            "deletion_change": (
                None if self.deletion_change is None else self.deletion_change.as_dict()
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


# ─────────────────────────────────────────────────────────────────────────
# 坐标索引（spec: workpaper-sync-materialize-large-table-performance）
# 把 O(N × 表体积) 的全表 re.search 换成「单次建索引 + O(1) 命中」。
# SheetCellIndex 是同一份 xml 字节的纯投影，不是第二套结构真源。
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SheetCellIndex:
    """sheet XML 的坐标 → span 索引。``view(coord)`` 与 ``_cell_view`` 逐字段等价。"""

    xml: str
    _spans: Mapping[str, tuple[int, int]]

    def span(self, coord: str) -> tuple[int, int] | None:
        return self._spans.get(coord)

    def view(self, coord: str) -> _CellView | None:
        span = self._spans.get(coord)
        if span is None:
            return None
        # 在切片上复用现有单格解析 —— 不再对整份 XML 全扫。
        sliced = self.xml[span[0] : span[1]]
        parsed = _cell_view(sliced, coord)
        if parsed is None:
            raise EditableCellWriteError(
                f"坐标索引键 {coord!r} 的 span 切片无法解析为单元格 —— "
                "索引与真实 XML 不一致，不得按索引静默返回错值"
            )
        # raw 必须指向**整份** xml 上的原文，供旧的 str.replace 路径与等价判据使用。
        if parsed.raw != sliced:
            raise EditableCellWriteError(
                f"坐标索引键 {coord!r} 的 span 切片与解析出的 raw 不一致"
            )
        return parsed


def build_sheet_cell_index(xml: str) -> SheetCellIndex:
    """一遍 ``re.finditer(_ANY_CELL_RE)`` 建 ``{coord: (start, end)}``。O(表体积)。"""
    spans: dict[str, tuple[int, int]] = {}
    for match in _ANY_CELL_RE.finditer(xml):
        letters = match.group(1) or match.group(3)
        row = match.group(2) or match.group(4)
        if not letters or not row:
            continue
        coord = f"{letters}{row}"
        # 同一坐标若重复出现，保留首次命中（与 ``_cell_view`` 的 search 首命中一致）。
        spans.setdefault(coord, match.span())
    return SheetCellIndex(xml=xml, _spans=MappingProxyType(spans))


def _cell_xml(*, coord: str, style: str, write: CellWrite) -> str:
    """按写入形态渲染一格。**恒带回原样式 `s=`**（AC 3.5：样式必须保留）。"""
    style_attr = f' s="{style}"' if style else ""
    if write.kind is CellWriteKind.blank:
        # 整格清空：无 `t`、无 `<v>`、无 `<is>`，**只保留样式**（AC 3.5）。
        # 不能退回 `inline_text` 写空串 —— 那是个「存在且值为空串」的格，extract 反读
        # 仍算有值 ⇒ 仍产 key（见 CellWriteKind.blank 注释的实测记录）。
        return f'<c r="{coord}"{style_attr}/>'
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
    """在 sheet XML 上定点写受管格。缺格按列序插入、缺行按行序插入。

    生产路径请走 :func:`patch_sheet_xml_indexed`（O(N + 表体积)）。本函数保留为
    逐字节等价的对照实现与变异靶心。
    """
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


def patch_sheet_xml_indexed(xml: str, writes: Sequence[CellWrite]) -> str:
    """与 :func:`_patch_sheet_xml` 逐字节等价，但用坐标索引 + 批量拼接。

    * 已存在的格：按 span 排序后一次性拼接，不再对每个写入 ``str.replace`` 重建整串；
    * 缺格/缺行：仍走 ``_insert_cell``（插入次数通常远小于已有格写入）。
    * 同一坐标多次写入时**最后一次**生效（与旧逐个 replace 语义一致）。
    """
    if not writes:
        return xml

    index = build_sheet_cell_index(xml)
    # coord → (span, new_fragment)；后写覆盖先写。
    replacements: dict[str, tuple[tuple[int, int], str]] = {}
    inserts: list[CellWrite] = []

    for write in writes:
        column = re.match(r"[A-Z]+", write.coord)
        row_match = re.search(r"\d+$", write.coord)
        if column is None or row_match is None:
            raise EditableCellWriteError(f"非法坐标 {write.coord!r}")
        span = index.span(write.coord)
        if span is not None:
            view = index.view(write.coord)
            assert view is not None  # span 存在 ⇒ view 必成功或已 fail visible
            if write.kind is CellWriteKind.cached_value_only:
                new = _replace_cached_value(view, write.value, write.formula_text)
            else:
                new = _cell_xml(coord=write.coord, style=view.style, write=write)
            replacements[write.coord] = (span, new)
            continue
        if write.kind is CellWriteKind.cached_value_only:
            raise ProtectedRegionWriteError(
                f"受保护公式格 {write.coord} 在 substrate 里不存在 —— 不得凭空造一个公式格"
                f"（stable key {write.stable_field_key!r}）"
            )
        inserts.append(write)

    if replacements:
        ordered = sorted(replacements.values(), key=lambda item: item[0][0])
        parts: list[str] = []
        cursor = 0
        for (start, end), fragment in ordered:
            if start < cursor:
                raise EditableCellWriteError(
                    "坐标索引写出的 span 发生重叠 —— 索引与真实 XML 不一致"
                )
            parts.append(xml[cursor:start])
            parts.append(fragment)
            cursor = end
        parts.append(xml[cursor:])
        xml = "".join(parts)

    for write in inserts:
        column = re.match(r"[A-Z]+", write.coord)
        row_match = re.search(r"\d+$", write.coord)
        assert column is not None and row_match is not None
        row = int(row_match.group(0))
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


def _template_ids_from_sheet_key(sheet_key: str) -> tuple[str, ...]:
    """sheet_key → 候选 TEMPLATE_ID（与 ``GT_FOOTER_ROW_{TID}`` 对齐）。

    常规 ``{tid.lower()}-managed``（如 ``d42-managed`` → ``D42``）。
    D4-25~28 前端锁死连字符形态 ``d4-25-managed``，而 instrumentation 写的是
    ``GT_FOOTER_ROW_D425``（无连字符）—— 去连字符紧凑形态必须一并尝试，否则会
    回退到主键 ``GT_FOOTER_ROW``（主 sheet footer），把兄弟表误判成 footer 下移。
    """
    raw = str(sheet_key).removesuffix("-managed").upper()
    compact = raw.replace("-", "")
    if compact and compact != raw:
        return (compact, raw)
    return (raw,) if raw else ()


def _template_id_for_table_name(
    runtime_binding: Mapping[str, str], table_name: str | None
) -> str | None:
    """物理 Excel Table displayName → 冻结 TEMPLATE_ID（用于取 ``GT_FOOTER_ROW_{TID}``）。

    🔴 **同 sheet 双区**（一个 ``sheet_key`` 对应 N 个 region/template_id）时，``sheet_key``
    不足以定位本 region 的 footer —— instrumentation 写的是 per-SPEC 键
    ``GT_FOOTER_ROW_{spec.template_id}``（如 D4-1 的 ``GT_FOOTER_ROW_D41MAIN`` /
    ``_D41OTHER``），而 ``sheet_key=d41-managed`` 经 :func:`_template_ids_from_sheet_key`
    只得到单个 ``D41``，两边对不上会回退裸 ``GT_FOOTER_ROW``（primary sheet 的行）→ 误判
    footer 下移。

    唯一在两侧都一致的桥梁是 ``instrument_workbook_bytes_multi`` 写进隐藏 ``_GT_SYNC`` 的
    **平行有序**清册 ``GT_MANAGED_TABLES`` = ``table_name,…`` 与 ``GT_TEMPLATE_IDS`` =
    ``template_id,…``（下标一一对应）。给定本 region 的物理 ``table_name``（=
    ``binding.table_name`` / ``region.table_name``），据此定位它在 ``GT_MANAGED_TABLES``
    的下标，取同下标的 ``GT_TEMPLATE_IDS`` 即本 region 的 template_id。

    单 region / 旧 artifact（无 ``GT_MANAGED_TABLES``/``GT_TEMPLATE_IDS``，或 table_name
    不在清册里）返回 ``None`` —— 调用方回退到既有 ``sheet_key`` 路径，行为逐字不变。
    """
    if not table_name:
        return None
    raw_tables = str(runtime_binding.get("GT_MANAGED_TABLES") or "").strip()
    raw_tids = str(runtime_binding.get("GT_TEMPLATE_IDS") or "").strip()
    if not raw_tables or not raw_tids:
        return None
    table_names = [t for t in raw_tables.split(",") if t]
    template_ids = [t for t in raw_tids.split(",") if t]
    if len(table_names) != len(template_ids):
        # 清册畸形（两列长度不齐）—— 不猜下标对应，交回 sheet_key 路径。
        return None
    try:
        idx = table_names.index(str(table_name))
    except ValueError:
        return None
    return template_ids[idx]


def _resolve_frozen_footer_row(
    runtime_binding: Mapping[str, str],
    *,
    sheet_key: str | None,
    table_name: str | None = None,
) -> str | None:
    """多 sheet：优先 ``GT_FOOTER_ROW_{TEMPLATE_ID}``；否则回退 ``GT_FOOTER_ROW``。

    🔴 **优先按 region 的物理 ``table_name`` 定位 template_id**（同 sheet 双区唯一正确的
    区分维度，见 :func:`_template_id_for_table_name`）。table_name 缺省或映射不到时，退回
    既有 ``sheet_key`` → template_id 路径（单 region-per-sheet 场景逐字不变），最后回退裸
    ``GT_FOOTER_ROW``。

    冻结值始终取自 ``_GT_SYNC`` 的**声明**（不从可见 marker 反推），漂移检测不被削弱。
    """
    region_tid = _template_id_for_table_name(runtime_binding, table_name)
    if region_tid is not None:
        keyed = runtime_binding.get(f"GT_FOOTER_ROW_{region_tid}")
        if keyed is not None:
            return keyed
    if sheet_key:
        for tid in _template_ids_from_sheet_key(str(sheet_key)):
            keyed = runtime_binding.get(f"GT_FOOTER_ROW_{tid}")
            if keyed is not None:
                return keyed
    return runtime_binding.get("GT_FOOTER_ROW")


def assert_footer_anchor_stable(
    *,
    entries: Mapping[str, bytes],
    sheet_part: str,
    contract: SyncContract,
    runtime_binding: Mapping[str, str],
    row_shift: RowChangeCarrier | None = None,
    table_key: str | None = None,
    table_name: str | None = None,
    search_from_row: int = 0,
) -> int | None:
    """footer 标记行必须与 representation 冻结的 `GT_FOOTER_ROW` 一致（AC 6.9 / 6.3）。

    判据用两个**互相独立**的载体交叉验证：

    * 可见侧 —— 契约 `footer_anchor` 的 marker 在 `search_column` 上的实际行号；
    * 冻结侧 —— Task 17 写进隐藏 `_GT_SYNC` 的 `GT_FOOTER_ROW`，由 Task 37 的
      :func:`~app.services.workpaper_sync.excel_extract.read_runtime_binding_pairs`
      读出后作为 `runtime_binding` 传进来（本模块不自己解析那张 sheet —— 首版抄了一份
      `r:id="(rId\\d+)"` 的 sheet 定位，而 Task 17 的关系 id 是 `rIdGTSYNC`，于是恒读空、
      把「sheet 定位失败」误报成「缺 GT_FOOTER_ROW」）。

    多 sheet 契约：传 `table_key` 时只用该表的 footer_anchor。冻结行的取用**优先按本
    region 的物理 `table_name`**（= `binding.table_name` / `region.table_name`）经隐藏
    `_GT_SYNC` 的平行清册 ``GT_MANAGED_TABLES``/``GT_TEMPLATE_IDS`` 定位 template_id，读
    ``GT_FOOTER_ROW_{TEMPLATE_ID}`` —— 这是**同 sheet 双区**（一个 sheet_key 对应 N 个
    region/template_id，如 D4-1 主营 `D41MAIN`=12 / 其他 `D41OTHER`=18）唯一正确的区分维度。
    `table_name` 缺省时退回 ``sheet_key`` → template_id 路径（``{tid.lower()}-managed``），
    最后回退主键 ``GT_FOOTER_ROW``（单 sheet / 旧 artifact 兼容），逐字不变。

    🔴 `search_from_row`：同 sheet 双区里可见侧同一 marker（``小计``）在每区各出现一次，
    不设下限会恒取第一处 → 给「其他」区判 footer 时误取「主营」区的 marker 行。传入本
    region 数据区首行（``region.first_row``）作可见侧搜索下限，冻结侧则按 `table_name`
    取本区的 ``GT_FOOTER_ROW_{TID}``，两侧同区对齐。默认 0（单 region 逐字不变）。

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
    sheet_for_table: Any = None
    table_for_key: Any = None
    if table_key is not None:
        for sheet in contract.sheets:
            for table in sheet.tables:
                if table.table_key == table_key:
                    sheet_for_table = sheet
                    table_for_key = table
                    break
            if table_for_key is not None:
                break
        if table_for_key is None:
            raise FooterAnchorDriftError(
                f"契约 {contract.contract_id} 没有 table_key={table_key!r} —— "
                "无法按 binding 取 footer_anchor"
            )
        if table_for_key.footer_anchor is None:
            return None
        anchor = table_for_key.footer_anchor
    else:
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
        xml,
        column=anchor.search_column,
        marker=anchor.marker,
        shared=shared,
        min_row=search_from_row,
    )
    if observed is None:
        raise FooterAnchorDriftError(
            f"契约声明的 footer marker {anchor.marker!r} 在列 {anchor.search_column} 上"
            "一处都找不到 —— footer anchor 是 AC 6.3 要求契约表达的结构之一，"
            "定位不到即结构漂移，不得按固定行号继续写"
        )
    frozen = _resolve_frozen_footer_row(
        runtime_binding,
        sheet_key=getattr(sheet_for_table, "sheet_key", None),
        table_name=table_name,
    )
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
    if expected is None:
        # 删行载体：footer 落在被删行上 ⇒ 受管区的 footer 自己被删了，那不是位移问题。
        raise FooterAnchorDriftError(
            f"footer 冻结行 {frozen_row} 落在本次声明的被删行集合 "
            f"{sorted(getattr(row_shift, 'deleted_rows', ()))} 里 —— footer 行不是数据行，"
            "删到它说明被删行集合越出了受管区（Requirement 7.3）"
        )
    if observed != expected:
        deleted_rows = getattr(row_shift, "deleted_rows", None)
        how = (
            f"删 {row_shift.count} 行（最上被删行 {min(deleted_rows)}）"
            if deleted_rows
            else f"插入点 {row_shift.insert_at}，插 {row_shift.count} 行"
        )
        raise FooterAnchorDriftError(
            f"footer marker {anchor.marker!r} 实测在第 {observed} 行，"
            f"representation 冻结的 GT_FOOTER_ROW={frozen_row}，"
            f"本次声明的预期位移 {expected - frozen_row:+d} 行（{how}）"
            f"⇒ 预期落在第 {expected} 行 —— 三者不一致即 footer 有**声明之外**的移动。"
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
    xml: str, *, column: str, marker: str, shared: Sequence[str], min_row: int = 0
) -> int | None:
    """在指定列上找 marker 文本所在行（支持 sharedString / inlineStr / str 三种载体）。

    🔴 OO 回写常把空格写成自闭合 ``<c r="A84" s="168"/>``。若 attrs 用 ``[^>]*``
    会把结尾 ``/`` 吃进 attrs、再拿后面第一个 ``</c>``（往往是下一行有文本的格）当
    本格闭合，footer marker 就被「吞掉」→ ``FooterAnchorDriftError``（G7 canary
    真栈：A84 自闭合吞掉 A85 的 footer）。attrs 不得跨越 ``/``；自闭合格直接跳过。

    🔴 ``min_row``：**同 sheet 双区**里同一 marker（如 ``小计``）会在每个 region 各出现
    一次（D4-1 主营 R12 / 其他 R18）。不设下限就恒取第一处（R12），给「其他」区判 footer
    时会把主营的 R12 当成它的 footer marker。传入本 region 数据区首行（``region.first_row``）
    作下限后，主营区从 R8 起搜到 R12、其他区从 R14 起搜跳过 R12 命中 R18 —— 各归各的。
    单 region 传 0（默认），行为逐字不变。
    """
    for match in re.finditer(
        r'<c r="'
        + re.escape(column)
        + r'(\d+)"(?P<attrs>[^>/]*)(?:/>|>(?P<body>.*?)</c>)',
        xml,
        re.S,
    ):
        row = int(match.group(1))
        attrs = match.group("attrs") or ""
        body = match.group("body")
        if body is None:
            continue
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
        if row < min_row:
            continue
        if text is not None and text.strip() == marker:
            return row
    return None


def assert_footer_formula_covers_managed_rows(
    *,
    entries: Mapping[str, bytes],
    sheet_part: str,
    footer_row: int,
    region: ManagedRegion,
    row_shift: RowChangeCarrier | None = None,
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
    * 🔴 **删行载体**（`RowDeletionShift`，spec workpaper-sync-row-deletion-…）：末行由
      `shift_range_end(region.last_row)` 求出（符号相反，照插行公式算会每次都假红），
      并**多一条上界**——区间终点仍停在删行前的受管末行 ⇒ A5 没收缩 ⇒ 抛。上界故意只
      认「恰等于老末行」这一形态，因为「合计区间是受管区超集」在真实模板里存在（H1）。
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
    #
    # 🔴 删行侧符号相反：`region.last_row + count` 会算出**比删行前还大**的末行，
    #    于是任何合计区间都「漏算」⇒ 每次删行都假红。删行侧用载体自己的区间终点公式
    #    `shift_range_end`（= `last_row - |{d ≤ last_row}|`，被删行都在区内 ⇒ 恒 `-count`），
    #    而不是在这里写 `- count`：区间终点的塌陷方向是载体的性质，散在调用点写就会漂。
    deleting = row_shift is not None and getattr(row_shift, "deleted_rows", None)
    if row_shift is None:
        effective_last_row = region.last_row
    elif deleting:
        effective_last_row = row_shift.shift_range_end(region.last_row)
    else:
        effective_last_row = region.last_row + row_shift.count
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
            if first > region.first_row:
                continue
            # 🔴 删行侧独有的**上界**：区间终点原本恰是受管末行、删行后却还停在老末行
            #    ⇒ A5 一处没收缩。此时合计把**已经上移到那一行的 footer 自己**算了进去
            #    （design A5 点名的错值）。
            #
            #    判据故意收窄到「终点恰等于删行**前**的受管末行」而不是「终点 > 新末行」：
            #    合计区间是受管区**超集**的形态真实存在（H1 模板 `SUM(I13:I27)` 而受管区
            #    到 26，已在 `pilot_h1_grouped_dynamic` 里登记）⇒ 宽口径会把它判成假红。
            if deleting and last == region.last_row and effective_last_row != region.last_row:
                raise FooterFormulaRangeError(
                    f"footer 格 {coord} 的公式 {view.formula_text!r} 区间终点仍在第 {last} 行，"
                    f"而本次声明删了 {row_shift.count} 行、受管末行已上移到第 "
                    f"{effective_last_row} 行 —— 区间没跟着收缩，合计会把上移到第 {last} 行的"
                    "footer 自己算进去（A5 未执行或未覆盖到本格）"
                )
            if last >= effective_last_row:
                continue
            raise FooterFormulaRangeError(
                f"footer 格 {coord} 的公式 {view.formula_text!r} 区间只到第 {last} 行，"
                f"而受管行区间已到第 {effective_last_row} 行"
                + (
                    f"（含本次声明的 {'-' if deleting else '+'}{row_shift.count} 行"
                    f"{'删除' if deleting else '插入'}）"
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
        normalized = normalize_value(field.value, spec.value_type)
    except ValueNormalizationError as exc:
        raise EditableCellWriteError(
            f"受管格 {coord}（{spec.stable_field_key}）的值 {field.value!r} 无法按 "
            f"{spec.value_type.value} 规范化: {exc} —— 不得写一个自己都读不懂的值"
        ) from exc
    # 🔴 json：`normalize_value` 返回的是 canonical **bytes**（`{"v": value}` 包裹，仅作
    #    比较口径的键）。它绝不能被 `inline_text` 的 `str(write.value)` 直接落盘 —— 那会写成
    #    Python bytes repr（带 `b'...'` 前缀），extract 读回该字符串后 `normalize_value` 再
    #    包一层 `{"v": "<那串>"}` ⇒ 与提交侧 `{"v": value}` 永远不等值（Property 65 假红：
    #    「提交 {} → 反读 'b\'{"v":{}}\''」，D4-30 custom_dimensions / D4-31 q1_relation 真栈实测）。
    #    落盘的应是 **value 自身**的 JSON 文本（`{}` / `[]` / `{"a":1}`），extract 侧对称
    #    `json.loads` 解回对象；两侧都持 Python 对象后，`normalize_value` 对称包裹即等值。
    #    仍用 normalize_value 先校验（拒 NaN/Infinity/非可序列化），只是落盘换成解包后的文本。
    if spec.value_type is ValueType.json:
        if field.value is None:
            return None
        return json.dumps(field.value, ensure_ascii=False, sort_keys=True)
    return normalized


def plan_managed_writes(
    *,
    projection: Projection,
    contract: SyncContract,
    binding: ExcelIdentityBinding,
    region: ManagedRegion,
    scan: RowIdentityScan | None,
    substrate_entries: Mapping[str, bytes],
    substrate_formulas: Mapping[str, str],
    runtime_binding: Mapping[str, str],
    intended_formulas: Mapping[str, str] | None = None,
) -> MaterializePlan:
    """算出「往哪些格写什么」。纯函数：不碰磁盘、不改 `substrate_entries`。

    静态受管区（:attr:`BindingKind.static_region`）走 :func:`_plan_static_writes` ——
    按绝对坐标直写，无 row_shift / footer 两门 / minted UUID / workbook 传播（`scan=None`）。

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
    if is_static_region(binding):
        return _plan_static_writes(
            projection=projection,
            contract=contract,
            binding=binding,
            region=region,
            substrate_entries=substrate_entries,
            substrate_formulas=substrate_formulas,
            intended_formulas=intended_formulas,
        )
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

    # ── 6.2b 受管行收敛：substrate 有物理行、而 store 已不认领的行 ──────────
    #
    # ═══ 为什么必须有这一步（spec workpaper-sync-managed-row-convergence）═══
    #
    # 6.2 的 `orphan` 只有**一个方向**：store 声明了、substrate 没物理行 ⇒ 插行。
    # 反方向（substrate 有物理行、store 已不声明）此前**无人处理** ⇒ 那些行永久留在
    # substrate，被 extract 反读出来，而 intended 里没有它们 ⇒ roundtrip 判 `extra` ⇒
    # `roundtrip_projection_mismatch` 恒 500，且孤儿只增不减（D4-2 实测累积出同一份业务
    # 数据的 **3 个副本**）。这就是「materialize 只插不删」的病根所在。
    #
    # ═══ 判据：与 overlay 严格对偶（不是新协议）═══
    #
    # `overlay_store_on_baseline_projection` 在**读**方向的规则是：
    #   store 声明了该 table → store 的行集为权威（丢弃 baseline 旧行）；
    #   store 没声明该 table → 保留 baseline 原样。
    # 本步是它在**写**方向的同一条规则：
    #   store 声明了该 table → 收敛 substrate 上 store 未列出的受管行；
    #   store 没声明该 table → **一律不碰**。
    # 两侧同规则才自洽（读方向丢掉的，写方向真的清掉）；而「没声明就不碰」保证本步永远
    # 是「少做」而非「多做」 —— 判据收窄的最坏后果是不收敛（回到 500），不会误删。
    #
    # 🔴 `table_key not in projection.row_keys` 与 `row_keys[table_key] == ()` 必须可分辨：
    #    前者是「store 没声明这张表」（不碰），后者是「store 声明了且为空」（该清空整表）。
    #    用 `in` 判断而不是 `get(...)` 取空值，正是为了不把两者混成一个。
    # 🔴 **模板预置骨架行不是 stale**（实测回归教训，Property 23/66）：
    #    instrumentation 为模板的每个受管行预生成 `GTROW-{template}-{row:04d}` 身份
    #    （`excel_instrumentation.row_uuid()`），它与运行期 mint 的 `GTROW-MINTED-` 前缀
    #    **刻意不同域**，正是为了「运行期新分配」与「模板预生成」可分辨
    #    （`excel_extract.MINTED_ROW_IDENTITY_PREFIX` 的 docstring）。
    #    这些骨架行「不在 store 的 row_keys 里」是**常态** —— store 只声明有业务数据的行，
    #    不代表用户删了行。首版判据漏了这个区分，把 `GTROW-D41MAIN-0009` 等骨架行判成
    #    stale 删掉 ⇒ `IdentityRetentionError: OO 往返后丢失 3 个 row identity`
    #    （test_d4_1_materialize_extract_realchain 4 红）。
    #
    #    判据 `contracts.is_template_skeleton_identity` 与 instrumentation 的生成规则同源，
    #    且与 roundtrip 豁免（`content_mutation._assert_roundtrip_equivalent`）**共用同一个**
    #    真源 —— 两处各写一份正则就是第二真源（症状分别是「误删模板行」与「误报 extra」，
    #    相距很远，漂移时极难归因）。
    stale_rows: dict[int, str] = {}
    if dynamic_table.table_key in projection.row_keys:
        wanted_set = set(wanted)
        stale_rows = {
            row: identity
            for row, identity in sorted(physical.items())
            if identity not in wanted_set
            and not is_template_skeleton_identity(identity)
        }

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
        table_key=dynamic_table.table_key,
        # 🔴 同 sheet 双区：按本 region 的物理 table_name 定位 per-region 冻结 footer，
        #    不靠 sheet_key（一个 sheet_key 对应两个 region 时不足以区分）；
        #    可见侧 marker 搜索也从本区数据首行起，避免命中另一区的同名 marker。
        table_name=binding.table_name,
        search_from_row=region.first_row,
    )
    anchor = dynamic_table.footer_anchor
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
    cell_index = build_sheet_cell_index(xml)
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
        view = cell_index.view(coord)
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

    # ── 6.8b 收敛动作：清空 stale 行的 editable 业务格（**不删物理行**）────────
    #
    # 🔴 清空必须保留**身份载体列**与**公式格**：
    #    清身份列 ⇒ 反读时该行 uuid 为空 ⇒ `_scan_row_identities` 按 tombstone 策略
    #    重新 mint 一个新身份 ⇒ 新身份不在 intended ⇒ 又一轮 `extra`（实测踩过）；
    #    清公式格 ⇒ 毁模板公式，且公式字段本就被 roundtrip 的 `PROTECTED_MODES` 豁免，
    #    不构成 extra，没有清它的必要。
    #
    # 另一条同源约束（实测于 D4-31）：该 entry 的受管区**就是一行**
    # （`table_ref='A5:K5'`）。任何把受管区行数减到 0 的动作都会让下一次 `extract` 抛
    # `IdentityCarrierMissingError`（「Table ref 覆盖的行区间内一个 row identity 都没
    # 反读到」，Requirement 6.15/6.20 的 fail-closed）—— 清空方案天然不触碰行数，
    # 这条边界自动满足。
    stale_cleared: tuple[int, ...] = ()
    stale_deleted: tuple[int, ...] = ()
    stale_clear_reason = ""
    row_deletion: Any | None = None
    deletion_change: Any | None = None

    # ═══ 6.8b 分流判定树（spec workpaper-sync-row-deletion-multi-region-propagation
    #     design § 删与插共存 4.2）═══
    #
    #     stale_rows 非空？
    #     ├─ 否 → 两个分支都空（现状）
    #     └─ 是 → 删后受管区剩余有身份数据行 <= 0 ？
    #             ├─ 是 → stale_cleared（容量归零；保住 IdentityCarrierMissingError 的结构前提）
    #             └─ 否 → 契约 row_convergence == delete ？
    #                     ├─ 否 → stale_cleared（**默认**，逐字节零回归）
    #                     └─ 是 → orphan 非空（删与插共存）？
    #                             ├─ 是 → stale_cleared ＋ 可观测降级原因
    #                             └─ 否 → stale_deleted（真正走删行）
    #
    # 🔴 顺序不可换：容量归零必须在契约门控**之前**判。反过来的话，一张已开启 delete 的
    #    表在「store 把整表清空」时会真的把受管区删空 ⇒ 下一次 extract 抛
    #    `IdentityCarrierMissingError`（Table ref 覆盖区间内一个 row identity 都没有）。
    #    那是个只在「全删」这一种输入上出现的 500，极难复现。
    #
    # 🔴 **不**在删行前口径重算 `insert_at`（Requirement 9.3）：共存时直接降级，
    #    不去把插入点往下挪。挪的那条路要求「删后重算插入点」，是独立能力，
    #    在这里凑会得到一个没有判据覆盖的行号。
    remaining_after_delete = len(physical) - len(stale_rows)
    if stale_rows:
        if remaining_after_delete <= 0:
            stale_clear_reason = (
                f"capacity_would_reach_zero: 受管区现有 {len(physical)} 个有身份物理行，"
                f"本次 stale {len(stale_rows)} 行 ⇒ 删完剩 {remaining_after_delete} 行，"
                "Table ref 覆盖区间内会一个 row identity 都不剩"
            )
        elif not dynamic_table.deletes_physical_rows:
            # 默认路径：契约没开启删行。**不写 reason** —— 这不是「降级」而是常态，
            # 写了反而让真正的降级在日志里淹没（Requirement 9.2 要的是降级可观测）。
            pass
        elif orphan:
            stale_clear_reason = (
                f"delete_with_insert_coexist: 本次同时有 {len(stale_rows)} 个 stale 行与 "
                f"{len(orphan)} 个 orphan 身份。插入点按删行**前**行号算，先插后删会被重编号、"
                "先删后插则插入点也要下移 ⇒ 共存下删行不安全，本次降级为清空"
                "（Requirement 9.1 / 9.2）"
            )
        else:
            row_deletion, deletion_change, stale_deleted = _plan_row_deletion(
                stale_rows=stale_rows,
                contract=contract,
                region=region,
                substrate_entries=substrate_entries,
            )
            # 🔴 删行侧**同样**需要这两个值，且不能沿用插行分支的（那一支此时必然没跑过，
            #    因为共存已在上面降级掉了 ⇒ 两者仍是初值 `()` / `""`）：
            #    * `total_formula_rows` —— A5 的合计区间收缩门控（Requirement 5.5：未声明
            #      即不改那条公式），不设的话「删受管末行」时合计区间不收缩，
            #      而 A7 的上界判据会在写盘前把它拦成 `FooterFormulaRangeError`；
            #    * `table_part` —— `_shrink_managed_table_ref` 的目标；不设则本表 ref
            #      不收缩，apply 期抛 `[convergence_table_ref_not_shrunk]`。
            #    两条都是 fail-closed（不会产出坏字节），但症状离真因很远，故在此显式接上。
            total_formula_rows, table_part = _resolve_total_rows_and_table_part(
                contract=contract,
                region=region,
                substrate_entries=substrate_entries,
                runtime_binding=runtime_binding,
                reject=lambda code, detail: RowSetDivergenceError(
                    f"[{code}] 本次要删的受管行 {list(stale_deleted[:3])}"
                    f"（共 {len(stale_deleted)} 行）不可安全执行：{detail}"
                ),
            )

    if stale_rows and not stale_deleted:
        # ═══ 为什么统一走「清空」而不删物理行（G2 裁决，实测驱动）═══
        #
        # 删物理行会牵动**一整套行号位移联动**，插行路径为此积累了专门处理：
        #   * `_shift_sibling_table_refs` —— 同 sheet 兄弟 Table 的 ref 位移
        #     （D4-1 是 main R8~R22 / other R25~R36 双区，删 main 区一行就动 other 区）
        #   * footer anchor 与 `GT_FOOTER_ROW` 重冻结、合计公式区间扩张
        #   * `_apply_workbook_propagation` —— definedName 与**引用侧 sheet** 的跨表公式行号
        # 删行要**全部对称实现**才安全。实测代价：只补了自己的 Table ref 收缩（未补兄弟 ref）
        # 就导致 other 区出现 uuid 空行 ⇒ 反读时 `_scan_row_identities` 按 tombstone 策略
        # 给它**重新 mint** `GTROW-MINTED-*` ⇒ 新身份不在 intended ⇒ 又一轮 `extra`。
        #
        # 而「清空业务格」**不动行号** ⇒ 一次性消除整类位移副作用（兄弟 ref / footer /
        # definedName / 跨 sheet 公式全都不受影响），且足以达成目的：实测 substrate 上
        # 「有身份但业务格全空」的 130 行中，**0 行**进 extracted ⇒ 清空即消除 extra。
        #
        # 代价（已知并接受）：substrate 留下空行，行数不精确跟随 store。这不影响正确性 ——
        # 行数不够时 6.2 的动态插行会补（`_plan_row_shift` 生产在用），空行也会被复用。
        #
        # 🔴 `stale_deleted` 与 apply 期的删行执行**保留但不启用**（`shrink_sheet_rows` /
        #    `_shrink_managed_table_ref` 仍在），留给后续独立 spec 补齐多区位移联动后再开。
        for row in sorted(stale_rows):
            for spec in dynamic_table.fields:
                if spec.cell is None or spec.cell.row_from != "row_identity":
                    continue
                if spec.mode in PROTECTED_MODES:
                    continue  # 公式/auto_source：保留（且本就被 roundtrip 豁免）
                column = _resolve_column(
                    spec, table=dynamic_table, region=region, binding=binding
                )
                writes.append(
                    CellWrite(
                        coord=f"{column}{row}",
                        # 🔴 必须是 `blank`（整格清空），**不是** `_write_kind_for(spec)` +
                        #    空串。后者对 text 字段渲染成 `<is><t xml:space="preserve"></t>
                        #    </is>` —— 一个「存在且值为空串」的格，extract 反读仍算有值 ⇒
                        #    仍产 key ⇒ extra 消不掉。实测：收敛 D4-1 R22 后 6 个 amount
                        #    字段的 extra 消失（`<v></v>` 恰好被读回 None）而 text 的
                        #    `label` 一个不少，500 就卡在这一个字段上。
                        kind=CellWriteKind.blank,
                        value=None,
                        stable_field_key=None,
                        row_key=stale_rows[row],
                        mode=spec.mode,
                    )
                )
        stale_cleared = tuple(sorted(stale_rows))

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

    _plan = MaterializePlan(
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
        managed_sheet_key=_sheet_key_for_table(contract, binding.table_key),
        managed_table_name=binding.table_name,
        stale_deleted=stale_deleted,
        stale_cleared=stale_cleared,
        stale_clear_reason=stale_clear_reason,
        row_deletion=row_deletion,
        deletion_change=deletion_change,
    )
    # ── 降级原因必须有**外部**消费方（复盘补，Requirement 9.2 / 9.6）────────────
    #
    # 🔴 复盘现算：`stale_clear_reason` 全仓 6 处引用**全在本模块自己**
    #    （字段定义 / as_dict / 三处赋值 / 一处传参）⇒ 生产**零外部消费方**。
    #    这个字段的存在理由恰恰是「降级必须可观测」（见字段 docstring），而
    #    「只写进一个没人读的 dataclass 字段」与不写没有区别 —— 用户看到的是
    #    「行删不掉但没人说为什么」，排查要从 materialize 计划期倒推。
    #
    # 这里发一条 WARNING 就是那个外部消费方：ops 能在日志里直接看到降级发生。
    # 刻意**不**加字段到 `MaterializeResult` / `ContentCommitReceipt` ——
    # 那两个是跨 adapter 的域契约，为一条可观测信息扩契约不划算（构造点与
    # 测试替身都要跟着改），而可观测性用日志是本包既有约定（14 处 getLogger）。
    if stale_clear_reason:
        logger.warning(
            "受管行收敛降级为「只清值」：table=%s sheet=%s stale=%d 行 原因=%s",
            binding.table_key,
            _sheet_key_for_table(contract, binding.table_key),
            len(stale_cleared),
            stale_clear_reason,
        )
    return _plan


def _resolve_total_rows_and_table_part(
    *,
    contract: SyncContract,
    region: ManagedRegion,
    substrate_entries: Mapping[str, bytes],
    runtime_binding: Mapping[str, str],
    reject: Any,
) -> tuple[tuple[int, ...], str]:
    """本区的「携带合计公式的行」与受管 Table 的 part —— **插行与删行共用**。

    spec: workpaper-sync-row-deletion-multi-region-propagation（Task 17.1）

    🔴 抽出来是因为删行侧也需要这两个值（`total_formula_rows` 给 A5 的合计收缩门控、
    `table_part` 给 `_shrink_managed_table_ref`），而它们的推导有两处**极易写错**的细节，
    各在插行侧踩过一次：

    * anchor 与冻结 footer 行号都必须绑定**本次的那张表**（`region.table_key` /
      `region.table_name`），不得取「跨全部 sheet 的第一张 footer 表」——
      combined 契约里那恒是 primary sheet，于是给 sibling 区算出来的是 primary 的行号；
    * 取的是**冻结声明**而不是现场搜 marker：从 substrate 观测的行号会把
      「footer 已经被人挪过」当成合法。

    抄第二份的症状是「删行侧合计不收缩 / Table ref 不收缩」，而那两条各自的 fail-closed
    会在很远的地方报出来。

    `reject` 由调用方传入，使两侧各自保留自己的 `error_code` 前缀与上下文文案
    （插行侧的消息里带 orphan 清单，删行侧带被删行清单）。
    """
    region_sheet_key = _sheet_key_for_table(contract, region.table_key)
    anchor = next(
        (
            table.footer_anchor
            for sheet in contract.sheets
            for table in sheet.tables
            if table.table_key == region.table_key and table.footer_anchor is not None
        ),
        None,
    )
    total_formula_rows: tuple[int, ...] = ()
    if anchor is not None and anchor.carries_total_formula:
        frozen = _resolve_frozen_footer_row(
            runtime_binding,
            sheet_key=region_sheet_key,
            table_name=region.table_name,
        )
        raw = str(frozen or "").strip()
        if not raw.isdigit():
            raise reject(
                "excel_row_shift_plan_range_invalid",
                "契约声明 footer 携带合计公式，但 runtime binding 的 "
                f"GT_FOOTER_ROW（sheet_key={region_sheet_key!r}）={raw!r} 不是行号 —— "
                "无从确定该扩张哪一行的区间",
            )
        total_formula_rows = (int(raw),)

    table_part = _managed_table_part(substrate_entries, table_name=region.table_name)
    if not table_part:
        raise reject(
            "excel_row_shift_table_part_missing",
            f"受管 Excel Table {region.table_name!r} 的 part 在 zip 里定位不到"
            f"（实测 {sorted(n for n in substrate_entries if n.startswith('xl/tables/'))}）—— "
            "插行后 Table ref 无从增长，新行会落在受管区域之外并被静默丢弃",
        )
    return total_formula_rows, table_part


def _plan_row_deletion(
    *,
    stale_rows: Mapping[int, str],
    contract: SyncContract,
    region: ManagedRegion,
    substrate_entries: Mapping[str, bytes],
) -> tuple[Any, Any, tuple[int, ...]]:
    """产出删行的**两份声明**（Requirement 1.11 / Property 4）。

    spec: workpaper-sync-row-deletion-multi-region-propagation（Task 17.1）

    🔴 两份声明必须**同时**产出，缺一不可：
    * `row_deletion`（`RowDeletionShift`）—— 行号位移载体，A1/A2/A5/A6/A7 都消费它；
    * `deletion_change`（`RowDeletionChangeSet`）—— 工作簿级引用的逐条改写声明（A3/A4）。

    只有前者 ⇒ definedName 与跨 sheet 公式不会被改写，产物里它们仍指向旧行号
    （多指一行或少指一行，取决于删的位置）；只有后者 ⇒ 物理行根本没删。
    apply 期对「少一份」有纵深防御断言，这里是正源。

    `deletion_change` 允许为 `None`：整本工作簿对本表**一处引用都没有**是合法形态
    （门面在返回 `None` 之前已把三道 fail-closed 跑完）。
    """
    deleted = tuple(sorted(stale_rows))

    def _reject(code: str, detail: str) -> RowSetDivergenceError:
        return RowSetDivergenceError(
            f"[{code}] 本次要删的受管行 {list(deleted[:3])}（共 {len(deleted)} 行）"
            f"不可安全执行：{detail}"
        )

    row_deletion = RowDeletionShift(
        deleted_rows=deleted,
        region_first_row=region.first_row,
        region_last_row=region.last_row,
    )
    deletion_change = plan_workbook_row_change_for_delete(
        substrate_entries,
        managed_sheet_name=region.sheet_name,
        managed_sheet_part=region.sheet_part,
        deleted_rows=deleted,
        region_first_row=region.first_row,
        region_last_row=region.last_row,
        # 🔴 留痕键取**行身份**（Requirement 1.9 / Property 6）：被删行必须能被审计追回，
        #    而 `stale_rows` 的值就是该行在 substrate 上的 row identity。
        row_uuids=dict(stale_rows),
    )
    # `_reject` 目前只被下面这条前提用到；保留它是为了让后续新增的拒绝理由有统一文案。
    if not deleted:
        raise _reject("convergence_delete_empty", "被删行集合为空")
    return row_deletion, deletion_change, deleted


def _plan_static_writes(
    *,
    projection: Projection,
    contract: SyncContract,
    binding: ExcelIdentityBinding,
    region: ManagedRegion,
    substrate_entries: Mapping[str, bytes],
    substrate_formulas: Mapping[str, str],
    intended_formulas: Mapping[str, str] | None = None,
) -> MaterializePlan:
    """静态受管区的写入计划（Requirement 4.1/4.2）：按绝对坐标直写。

    与动态 :func:`plan_managed_writes` 的差别（全部因「无动态行维度」而来）：
    * 无 dynamic_columns 绑定、无 row_shift、无 footer 两门、无 minted UUID、无 workbook 传播；
    * 受管 cell = 静态表 fields 的 `static_row` 绝对坐标；
    * 区内公式 cell（合计 / 毛利率）走 formula_mask 保护（与动态区受保护格同一 `_emit` 逻辑）；
    * definedName 不在 writes 里 → 写操作只碰受管值坐标 → definedName 原样保留（Requirement 4.4）。
    """
    _, static_tables = managed_tables_of(contract, binding=binding)
    xml = substrate_entries[region.sheet_part].decode("utf-8")
    cell_index = build_sheet_cell_index(xml)
    intended_map: Mapping[str, str] = (
        substrate_formulas if intended_formulas is None else intended_formulas
    )
    writes: list[CellWrite] = []
    preserved: dict[str, str] = {}

    for static_table in static_tables:
        for spec in static_table.fields:
            if spec.cell is None or spec.cell.static_row is None:
                continue
            column = _resolve_column(spec, table=static_table, region=region, binding=binding)
            coord = f"{column}{spec.cell.static_row}"
            key = spec.stable_field_key  # 静态字段无 {row_uuid} 实例化
            field = projection.get(key)
            if field is None:
                continue
            view = cell_index.view(coord)
            restore = ""
            if spec.mode is FieldMode.formula:
                if view is None or not view.has_formula:
                    raise ProtectedRegionWriteError(
                        f"契约把 {key!r} 声明为 formula，但 substrate 的 {coord} 没有公式 —— "
                        "契约/模板漂移，不得凭空写公式或当字面量覆盖（AC 6.6）"
                    )
                observed = substrate_formulas.get(key, view.formula_text or "")
                intended = intended_map.get(key, observed)
                preserved[key] = intended
                if intended and _formula_body(intended) != _formula_body(observed):
                    if not (view.formula_text or ""):
                        raise ProtectedRegionWriteError(
                            f"受保护格 {coord}（{key}）的公式与 base representation 不符"
                            f"（应为 {intended!r}，实测 {observed!r}）且是共享公式组成员 —— "
                            "必须人工裁决而不是悄悄写回一格（AC 6.6）"
                        )
                    restore = _formula_body(intended)
            elif spec.mode is FieldMode.auto_source:
                if view is not None and view.has_formula:
                    raise ProtectedRegionWriteError(
                        f"契约把 {key!r} 声明为 auto_source，但 substrate 的 {coord} 是公式 "
                        f"{view.formula_text!r} —— 写字面量会毁掉模板公式（AC 6.6 / 3.5）"
                    )
            elif view is not None and view.shared_ref and ":" in (view.shared_ref or ""):
                raise SharedFormulaMasterWriteError(
                    f"契约把 {key!r} 声明为 {spec.mode.value}，但 {coord} 是共享公式主格 "
                    f"(ref={view.shared_ref})—— 覆盖主格会让整组成员失效"
                )
            writes.append(
                CellWrite(
                    coord=coord,
                    kind=_write_kind_for(spec),
                    value=_normalised_write_value(field, spec, coord),
                    stable_field_key=key,
                    row_key="",
                    mode=spec.mode,
                    formula_text=restore,
                )
            )

    return MaterializePlan(
        sheet_part=region.sheet_part,
        sheet_name=region.sheet_name,
        writes=tuple(writes),
        preserved_formulas=dict(sorted(preserved.items())),
        dynamic_column_columns={},
        footer_marker_row=None,
        row_shift=None,
        total_formula_rows=(),
        table_part="",
        workbook_row_change=None,
        managed_sheet_key=_sheet_key_for_table(contract, binding.table_key),
        managed_table_name=None,
    )


def _sheet_key_for_table(contract: SyncContract, table_key: str) -> str | None:
    for sheet in contract.sheets:
        for table in sheet.tables:
            if table.table_key == table_key:
                return str(sheet.sheet_key)
    return None


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
    *, contract: SyncContract, insert_at: int, sheet_key: str | None = None
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

    多 sheet 合册：只检查**同一 sheet_key** 上的静态行。跨 sheet 的 static_row
    （如 D4-5 B11）不得挡住另一张 sheet（如 D4-31）在其自身行号上的插行。
    """
    return tuple(
        (spec.stable_field_key, f"{spec.cell.column}{spec.cell.static_row}")
        for sheet in contract.sheets
        if sheet_key is None or str(getattr(sheet, "sheet_key", "") or "") == sheet_key
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
    offenders = _static_rows_at_or_below(
        contract=contract,
        insert_at=insert_at,
        sheet_key=_sheet_key_for_table(contract, region.table_key),
    )
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

    # 🔴 多 sheet 契约：anchor 与 frozen footer row 都必须绑定**本次位移的那张表**
    #    （`region.table_key`），不得取「跨全部 sheet 的第一张 footer 表」。首版两处都偷懒：
    #    ① anchor = 第一张有 footer_anchor 的表 —— combined 契约里恒是 primary sheet（D42）；
    #    ② frozen row = 裸主键 `GT_FOOTER_ROW`（= primary sheet 的行）。
    #    于是给 sibling 表（D4-23 footer 在 24 行）算扩张时，`total_formula_rows` 塞进的是
    #    primary 的行号（31）。`shift_sheet_rows` 的 `is_total_row = block.row in {31}` 对
    #    sibling 的 24 行主格恒为假 ⇒ 合计公式**不扩张** ⇒ 位移后 footer 落在 36 行、公式仍是
    #    stale 的 `SUM(B12:B23)` ⇒ apply-phase gate `footer_formula_range_stale`。
    #    真实 D4-29 编辑触发（sheet_key=d4-29-managed），combined projection 里 D4-22/D4-23
    #    各有 12 个 orphan 行要插，此路径每次必炸。修复 = 用 `region.table_key` 定位本表的
    #    footer_anchor + 用 `_resolve_frozen_footer_row(sheet_key=...)` 取本表冻结行号。
    total_formula_rows, table_part = _resolve_total_rows_and_table_part(
        contract=contract,
        region=region,
        substrate_entries=substrate_entries,
        runtime_binding=runtime_binding,
        reject=_reject,
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

    # ── 阶段 0：受管行收敛的**删行**分支（spec workpaper-sync-managed-row-convergence）──
    #
    # 🔴 排在位移（阶段 1）**之前**，理由与「位移先于写格」同型：`plan.row_shift` 的
    #    `insert_at` 是按 `plan_managed_writes` 看到的**删行前**行号算的吗？不是 ——
    #    计划期的 `physical` / `row_of_identity` 都取自未删的 substrate，而 6.8b 只登记
    #    `stale_deleted`（行号也是删行前口径）。两者叠加时若先插后删，插入点会被删行
    #    重新编号 ⇒ 静默错位。先删后插则：删行按降序逐个执行（高行号先删，低行号不受
    #    影响），删完再按位移计划插 —— 但**插入点也需要按已删行数下移**。
    #
    #    ⚠ 因此本版**只支持「删行」与「插行」互斥出现**：两者同时非空时 fail-closed，
    #    不静默算一个可能错位的插入点。实测 D4 的收敛场景里 stale 与 orphan 不共存
    #    （store 要么在收缩要么在扩张），互斥假设成立；将来真遇到共存再按「删后重算
    #    insert_at」实现，那需要一条独立判据而不是在这里凑。
    if plan.stale_deleted and plan.row_shift is not None:
        raise RowSetDivergenceError(
            f"[convergence_delete_with_insert_unsupported] 本次计划同时要求删 "
            f"{len(plan.stale_deleted)} 行（{list(plan.stale_deleted[:3])}）与插 "
            f"{plan.row_shift.count} 行 —— 两者叠加会让插入点按删行前的行号算而错位；"
            "当前实现拒绝这种组合（不静默凑一个可能错位的 insert_at）"
        )
    if plan.stale_deleted:
        # ── 纵深防御：删行计划必须**同时**携带两份声明（Requirement 1.11）────────
        #
        # 🔴 计划期（6.8b）保证两者与 `stale_deleted` 同时产出；走到这里少一份说明计划期
        #    与 apply 口径漂移了。不抛的后果是「删了物理行但没做位移联动」——
        #    正是 G2 实测那条症状链（兄弟区空 UUID → 重新 mint → extra → 500）。
        if plan.row_deletion is None:
            raise RowSetDivergenceError(
                f"[convergence_delete_without_shift_carrier] 计划要删 "
                f"{len(plan.stale_deleted)} 行（{list(plan.stale_deleted[:3])}）却没有"
                "位移载体 `row_deletion` —— 多区位移联动无从执行，不得只删行不联动"
            )
        declared = tuple(plan.row_deletion.deleted_rows)
        if declared != tuple(sorted(plan.stale_deleted)):
            raise RowSetDivergenceError(
                f"[convergence_delete_carrier_mismatch] 位移载体声明删 {list(declared)}，"
                f"而计划的 stale_deleted 是 {sorted(plan.stale_deleted)} —— "
                "两份口径不一致时任何一侧的位移算术都会错，不得取其一"
            )
        # 按**降序**逐行删：先删高行号，低行号不受影响 ⇒ 无需在循环里重算行号。
        # （`shrink_sheet_rows` 每次删一个连续段；这里按单行降序调用是最保守的形态 ——
        #   连续段合并只是少几次调用，不改变结果，不值得为它引入区间合并的出错面。）
        for row in sorted(plan.stale_deleted, reverse=True):
            xml, _ = shrink_sheet_rows(xml, delete_at=row, count=1)
        # ── A5：受管 sheet **自己**的裸引用平移（含合计区间收缩）───────────
        #
        # 🔴 排在 `shrink_sheet_rows` 之后、Table ref 收缩之前：坐标属性已是删行后口径
        #    （本函数内部按 `unshift` 归一化回删行前再与契约行号比较），而公式文本此刻
        #    还是原样 —— 两相正交，但顺序固定下来便于判据锚定。
        xml, _bare_changed = _shift_managed_sheet_bare_refs(xml, plan=plan)
        # ── A8：受管 sheet 上**携带行号的结构块**平移（mergeCell / sqref / brk / …）──
        #
        # 🔴 spec 七条欠账之外的第八条，但 Requirement 6.2（`managed_sheet_structure`
        #    等价）要求它。不做的产物后果是合并单元格与数据验证**继续指向旧行**：
        #    用户看到「合并块错位一行」「下拉框落在错误的行上」。
        xml, _struct_changed = _shift_managed_sheet_structures(xml, plan=plan)
        # ── A1：Table ref 对称**收缩**（本表 + 同 sheet 兄弟表）─────────────
        # 不缩的话 ref 仍覆盖已删掉的行区间，反读时 `resolve_managed_region` 按旧区间
        # 找身份 ⇒ 尾部出现「空 UUID 行」，与 `IdentityCarrierMissingError` 同源。
        # 兄弟表的收缩在 `_shrink_managed_table_ref` 末尾对称调用（G2 症状链第一环）。
        entries = _shrink_managed_table_ref(
            entries, plan=plan, removed=len(plan.stale_deleted)
        )
        # ── A3/A4：引用侧 sheet 与 definedNames 的工作簿级传播（按声明逐条改）──
        #
        # 🔴 顺序与插行侧同理：排在写格**之前**，写格产生的新字节不进传播的输入，
        #    于是声明与实测的对账口径仍是「计划期冻结的那份」。
        entries = _apply_workbook_propagation(entries, plan=plan)
        # ── A2：隐藏 `_GT_SYNC` 的 runtime binding 重冻结（删行侧）───────────
        #
        # 🔴 不做的后果是**时间错位**的故障：这一次删行成功、**下一次** materialize 在
        #    计划期撞 `FooterAnchorDriftError`（可见侧 marker = 冻结值 − 删行数，而
        #    计划期要求两者严格相等）。与插行侧同相位（Table ref 已收缩、footer 已上移）。
        entries = _refresh_gt_sync_runtime_binding(
            entries, plan=plan, source_bytes=source_bytes
        )

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
    entries[plan.sheet_part] = patch_sheet_xml_indexed(xml, plan.writes).encode("utf-8")
    return _write_entries(entries), report


def remap_bare_a1_for_deletion(text: str, *, shift: Any, what: str) -> str:
    """把一段文本里的**裸** A1 行号按删行载体改写（端点方向感知）。

    spec: workpaper-sync-row-deletion-multi-region-propagation（A5 / A8 共用）

    ═══ 为什么不是直接 `remap_a1_rows(text, remap=shift.shift)` ═══

    区间**起点与终点塌陷方向相反**（见 `RowDeletionShift.shift_range_end` 的推导），
    而 `_rewrite_formula_refs` 对一段文本只收一个 `remap`。所以本函数：

    1. 用 `classify_bare_row_roles`（走 `remap_a1_rows` 的记录型 remap，与执行口径恒等）
       分出这段文本里哪些裸行号是区间起点、哪些是终点；
    2. 基础 `remap` 用**起点**口径（`shift_range_start`）；
    3. 对**落在被删行上的区间终点**再用 `extend_end_at`/`extend_by` 做一次精确修正
       （修正量恒为 `-1`，因为 `|{d<=t}| - |{d<t}| == 1` 当 `t ∈ D`）。

    🔴 三种分不清角色的形态一律 **fail-closed**（不得挑一个静默改写）：
    角色未知 / 同时是起点与终点 / 一段文本里有 ≥2 个被删的终点
    （`extend_end_at` 一次只接受一个）。

    Args:
        what: 出错时点名用（坐标或 `tag@attr`），让归因不必翻代码。
    """
    from app.services.workpaper_sync.excel_row_shift import _rewrite_formula_refs
    from app.services.workpaper_sync.excel_workbook_row_change import (
        classify_bare_row_roles,
    )

    if not text.strip():
        return text
    deleted = set(shift.deleted_rows)
    rows, heads, tails = classify_bare_row_roles(text)
    at_risk = rows & deleted
    override_at: int | None = None
    if at_risk:
        unclassified = at_risk - heads - tails
        if unclassified:
            # 🔴 归因要准：`classify_bare_row_roles` 对**区间**恒同时产出起点与终点，
            #    所以「既不是起点也不是终点」⇔ 它是个**裸单格**引用。单格引用指向被删行
            #    就是悬空（Excel 里是 `#REF!`），不是「角色分不清」。
            #    首版把这一类报成 role_unknown，实测在 D3-4 上打出来（`B16` 的
            #    `B11-B13-B14-B15-B16` 删 r=15）—— 看着像分类器不够聪明，其实是那一行
            #    **本来就不该删**。正确的拦点在计划期 `find_bare_dangling_rows`；
            #    走到这里说明调用方绕过了门面，所以这条错误要把拦点名字说出来。
            raise RowSetDivergenceError(
                f"[convergence_bare_ref_dangling_single_cell] {what} 的 {text!r} 里裸"
                f"**单格**引用 {sorted(unclassified)} 指向被删行 ⇒ 删完即 #REF!。"
                "这一行不可删；计划期的 `find_bare_dangling_rows` 就是拦它的 —— "
                "走到 apply 说明绕过了 `plan_workbook_row_change_for_delete` 门面"
            )
        ambiguous = at_risk & heads & tails
        if ambiguous:
            raise RowSetDivergenceError(
                f"[convergence_bare_ref_role_ambiguous] {what} 的 {text!r} 里裸行号 "
                f"{sorted(ambiguous)} 同时是某区间的起点与另一区间的终点 —— "
                "一个 remap 表达不了两个方向，不得挑一个"
            )
        deleted_tails = sorted(at_risk & tails)
        if len(deleted_tails) > 1:
            raise RowSetDivergenceError(
                f"[convergence_bare_ref_multi_tail] {what} 的 {text!r} 有 "
                f"{len(deleted_tails)} 个落在被删行上的区间终点 {deleted_tails} —— "
                "改写器一次只接受一个终点修正，不得只修其中一个"
                "（另一个会静默多覆盖一行）"
            )
        if deleted_tails:
            override_at = deleted_tails[0]
    if override_at is None:
        new_text, _hits = _rewrite_formula_refs(text, remap=shift.shift_range_start)
        return new_text
    new_text, _hits = _rewrite_formula_refs(
        text,
        remap=shift.shift_range_start,
        extend_end_at=override_at,
        # 终点方向修正：两个公式在被删行上恰差 1。
        extend_by=shift.shift_range_end(override_at) - override_at,
    )
    return new_text


STRUCTURE_ATTRS_OWNED_BY_SHRINK: Final[frozenset[tuple[str, str]]] = frozenset(
    {("dimension", "ref")}
)
"""A8 **必须跳过**的 `(tag, attr)` —— 它们的属主是 `shrink_sheet_rows`，不是 A8。

spec: workpaper-sync-row-deletion-multi-region-propagation（design 勘误节 E.7）

🔴 实测踩过：`dimension@ref` 同时出现在
:data:`excel_row_shift.STRUCTURE_ROW_BEARING_ATTRS`（因为它确实携带行号，verifier 要
归一化它）**和** `shrink_sheet_rows` 的改写范围里。A8 照着派生表无脑遍历 ⇒ 同一个属性
被**收缩两次**：D1-8 `A1:AD38` 先被 `shrink_sheet_rows` 改成 `A1:AD37`（正确），再被
A8 改成 `A1:AD36`（错），verify 侧 `unshift` 只能还原一次 ⇒ `managed_sheet_structure`
判漂移，而真实后果是 `<dimension>` 比实际行数少一行。

所以「派生表是单一真源」这句话要补一个限定：它是**「哪些属性携带行号」**的单一真源，
不是**「谁负责改它」**的。后者需要本表显式登记。
判据：`test_row_deletion_verify_normalisation.py::TestStructureAttrOwnership`
（正向证明 `shrink_sheet_rows` 真的改它 + 反向证明 A8 真的不碰它）。
"""


def _shift_managed_sheet_structures(xml: str, *, plan: MaterializePlan) -> tuple[str, int]:
    """A8：受管 sheet 上**携带行号的结构块**随删行平移。

    spec: workpaper-sync-row-deletion-multi-region-propagation（design 勘误节 E.7）

    ═══ 🔴 这是 spec 七条欠账之外的**第八条**，但 Requirement 6.2 要求它 ═══

    `shrink_sheet_rows` 只改 `<row r=>` / `<c r=>` / `<dimension>`；插行侧的
    `shift_sheet_rows` 另有阶段 C/D 处理 `mergeCell@ref` / `dataValidation@sqref` /
    `conditionalFormatting@sqref` / `hyperlink@ref` / `autoFilter@ref` / `brk@id` /
    `formula1|formula2|sqref` 文本 —— 删行侧**一个都没有**。

    实测（D1-8，删 r=16 或 r=21）：`mergeCells` 的 `N24:N25` 与 `dataValidations` 的
    `sqref="A14:A21 A26:A33"` 逐字未变 ⇒ `verify_unmanaged_regions` 的
    `managed_sheet_structure` 当场判漂移（Requirement 6.2 过不去）。
    产物侧的真实后果是合并单元格与数据验证**继续指向旧行**：
    用户看到的是「合并块错位一行」「下拉框落在错误的行上」。

    ═══ 单一真源 ═══

    「哪些 tag 的哪个属性/文本携带行号」不在本模块手写第二份 —— 用
    `excel_row_shift` 从 :data:`ROW_BEARING_STRUCTURES` **派生**的三张表
    （`STRUCTURE_ROW_BEARING_ATTRS` / `STRUCTURE_BARE_ROW_ATTRS` /
    `STRUCTURE_ROW_BEARING_TEXT_TAGS`），**与 verifier 的归一化用的是同一批表**。
    加新结构时只要清单里加一项，两侧同时生效。

    🔴 但派生表只是**「哪些属性携带行号」**的真源，不是**「谁负责改它」**的 ——
    属主另有一方的项登记在 :data:`STRUCTURE_ATTRS_OWNED_BY_SHRINK`，本函数跳过它们，
    否则同一属性被收缩两次（实测 `dimension@ref` 正是如此）。

    Returns:
        `(新 XML, 改动处数)`
    """
    from app.services.workpaper_sync.excel_row_shift import (
        STRUCTURE_BARE_ROW_ATTRS,
        STRUCTURE_ROW_BEARING_ATTRS,
        STRUCTURE_ROW_BEARING_TEXT_TAGS,
    )

    shift = plan.row_deletion
    assert shift is not None, "调用方保证"
    changed = 0

    def _one_range(value: str, *, what: str) -> str:
        """`sqref` 可含多个空格分隔的区间 ⇒ 逐区间改写（与插行侧 `_shift_sqref` 同纪律）。

        🔴 必须逐段：整串喂进去时一段的终点修正会作用到另一段上。
        """
        parts = [p for p in value.split() if p]
        if len(parts) <= 1:
            return remap_bare_a1_for_deletion(value, shift=shift, what=what)
        return " ".join(
            remap_bare_a1_for_deletion(part, shift=shift, what=what) for part in parts
        )

    # ── ① 属性里是 A1 引用的项（mergeCell@ref / dataValidation@sqref / …）────
    for tag, attrs in STRUCTURE_ROW_BEARING_ATTRS.items():
        for attr in attrs:
            if (tag, attr) in STRUCTURE_ATTRS_OWNED_BY_SHRINK:
                continue
            pattern = re.compile(
                rf"(<(?:\w+:)?{re.escape(tag)}\b[^>]*?\b{re.escape(attr)}=\")([^\"]*)(\")"
            )

            def _sub(match: re.Match[str], _tag: str = tag, _attr: str = attr) -> str:
                nonlocal changed
                value = match.group(2)
                if not value:
                    return match.group(0)
                new_value = _one_range(value, what=f"{_tag}@{_attr}")
                if new_value == value:
                    return match.group(0)
                changed += 1
                return f"{match.group(1)}{new_value}{match.group(3)}"

            xml = pattern.sub(_sub, xml)

    # ── ② 属性里是**裸行号整数**的项（brk@id）────────────────────────────
    for tag, attrs in STRUCTURE_BARE_ROW_ATTRS.items():
        for attr in attrs:
            pattern = re.compile(
                rf"(<(?:\w+:)?{re.escape(tag)}\b[^>]*?\b{re.escape(attr)}=\")(\d+)(\")"
            )

            def _sub_bare(match: re.Match[str], _tag: str = tag, _attr: str = attr) -> str:
                nonlocal changed
                row = int(match.group(2))
                # `brk@id` 是**分页位置**（单个行号），按存活行语义映射；
                # 落在被删行上时塌到上一存活行（分页点不该凭空下移）。
                new_row = shift.shift(row)
                if new_row is None:
                    new_row = shift.shift_range_end(row)
                if new_row == row:
                    return match.group(0)
                changed += 1
                return f"{match.group(1)}{new_row}{match.group(3)}"

            xml = pattern.sub(_sub_bare, xml)

    # ── ③ 元素**文本**是 A1 区间的项（formula1 / formula2 / xm:sqref）──────
    for tag in sorted(STRUCTURE_ROW_BEARING_TEXT_TAGS):
        # 🔴 允许命名空间前缀：`<xm:sqref>` 是 x14 扩展的常见形态；不带前缀的正则会把
        #    `<xm:sqref>` 的尾巴匹配成 `<sqref>` 并把文本当属性吞掉（插行侧实测踩过）。
        pattern = re.compile(
            rf"(<(?:\w+:)?{re.escape(tag)}(?:\s[^>]*)?>)(.*?)(</(?:\w+:)?{re.escape(tag)}>)",
            re.S,
        )

        def _sub_text(match: re.Match[str], _tag: str = tag) -> str:
            nonlocal changed
            body = match.group(2)
            if not body.strip():
                return match.group(0)
            new_body = _one_range(body, what=f"{_tag}@text")
            if new_body == body:
                return match.group(0)
            changed += 1
            return f"{match.group(1)}{new_body}{match.group(3)}"

        xml = pattern.sub(_sub_text, xml)

    return xml, changed


def _shift_managed_sheet_bare_refs(xml: str, *, plan: MaterializePlan) -> tuple[str, int]:
    """A5：受管 sheet **自己**的裸引用随删行平移（含合计区间收缩）。

    spec: workpaper-sync-row-deletion-multi-region-propagation（Requirement 5）

    ═══ 为什么这一条是真欠账（Task 1.2 已实测）═══

    `shrink_sheet_rows` 只 `re.sub` 了 `<row r=>` / `<c r=>` 两个属性与 `<dimension>`，
    公式文本**一个字不动**；而 `propagate_reference_side` 是 `qualified_only=True`
    ⇒ 裸 `SUM(B7:B25)` 无人处理。实测：删 r=20 后合计公式与注入的 `B22*2` 都逐字不变，
    而坐标属性确实上移 ⇒ 判据非空转。

    不做的后果（design A5）：D4-1 main 区 R8~R22、footer 在 R23、合计是裸 `SUM(B8:B22)`。
    删 R22 后物理区变 R8~R21、footer 上移到 R22，而公式仍是 `B8:B22`
    ⇒ **合计把 footer 自己算进去** ⇒ Excel 循环引用；即便不报循环也是静默多算一行。

    ═══ 三条实现纪律 ═══

    1. **走 `excel_row_shift._rewrite_formula_refs` 这一个改写器**（`remap_a1_rows` 的同一入口），
       不新写行号改写器；**不复用 `shift_sheet_rows`** —— 上游明文「那个函数的语义是造新行
       + 下移，共用会让两边的边界条件互相干扰」。
    2. **区间首尾方向相反** ⇒ 基础 `remap` 用起点口径（`shift_range_start`），
       对**落在被删行上的区间终点**再用 `extend_end_at`/`extend_by` 做一次精确修正。
       修正量恒为 `-1`（`|{d<=t}| - |{d<t}| == 1` 当 `t ∈ D`）。
       现算语料：受管 sheet 上裸区间 **633** 处、末行落在受管区内 **576** 处、
       末行恰等于受管区末行 **377** 处（其中 **376** 在 footer 行）⇒ 这条修正是主路径，
       不是边角。
    3. **Requirement 5.5**：受管区**下方**的行（footer）若契约未声明 `carries_total_formula`
       （即不在 `plan.total_formula_rows` 里），它的公式**一个字都不改** —— 与插行侧
       「未声明即不扩张、让 `assert_footer_formula_covers_managed_rows` 去拦」对称。

    🔴 调用点在 `shrink_sheet_rows` **之后**（Task 12.1），所以 `<c r=>` 已是删行后行号
    ⇒ 与契约行号（删行**前**口径）比较前必须 `unshift` 回去。

    Returns:
        `(新 XML, 被改写的公式条数)`
    """
    from app.services.workpaper_sync.excel_workbook_row_change import (
        classify_bare_row_roles,
    )

    shift = plan.row_deletion
    assert shift is not None, "调用方保证"
    region_last = int(shift.region_last_row)
    total_rows = {int(r) for r in plan.total_formula_rows}
    changed = 0

    def _rewrite_text(text: str, *, coord: str, below_region: bool) -> str:
        nonlocal changed
        if not text.strip():
            return text
        _rows, _heads, tails = classify_bare_row_roles(text)
        # ── Requirement 5.5 的门控，**按公式**而不是按格 ──────────────────────
        #
        # 🔴 首版把门控写成「受管区下方的行 ∧ 未声明 ⇒ 整格不改」，太宽了：同一 sheet 上
        #    **兄弟区**的数据行与 footer 也全在本区下方，于是它们一条都不平移
        #    ⇒ 实测 D1-8 删 r=16 后兄弟区 footer `SUM(E26:E33)` 逐字未变（应为
        #    `SUM(E25:E32)`），verify 的 `managed_sheet_unmanaged_cells` 当场判漂移。
        #
        # 正确口径：Requirement 5.5 保护的是「**本区的**合计区间」——
        # 判据是「该公式含一个裸区间、其末行恰等于本区末行」。别的公式照常平移
        # （Requirement 5.1：受管 sheet 内指向被删行之下的裸引用都要平移）。
        if below_region and region_last in tails and region_last not in total_rows:
            return text
        new_text = remap_bare_a1_for_deletion(
            text, shift=shift, what=f"受管 sheet 的 {coord} 公式"
        )
        if new_text != text:
            changed += 1
        return new_text

    def _one_cell(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        body = match.group("body")
        if body is None or "<f" not in body:
            return match.group(0)
        coord_match = re.search(r'\br="(?P<coord>[A-Z]+)(?P<row>\d+)"', attrs)
        if coord_match is None:
            return match.group(0)
        # `<c r=>` 已是删行**后**行号 ⇒ 归一化回删行前口径再与契约比较。
        row_before = shift.unshift(int(coord_match.group("row")))
        coord = f"{coord_match.group('coord')}{coord_match.group('row')}"
        below_region = row_before > region_last
        gated = below_region and row_before not in total_rows
        new_body = re.sub(
            r"<f\b[^>]*>(?P<text>.*?)</f>",
            lambda m: m.group(0).replace(
                m.group("text"),
                _rewrite_text(m.group("text"), coord=coord, below_region=gated),
            )
            if (m.group("text") or "").strip()
            else m.group(0),
            body,
            flags=re.S,
        )
        if new_body == body:
            return match.group(0)
        return f"<c{attrs}>{new_body}</c>"

    from app.services.workpaper_sync.excel_workbook_row_change import (
        _CELL_WITH_BODY_RE,
    )

    return _CELL_WITH_BODY_RE.sub(_one_cell, xml), changed


def _apply_workbook_propagation(
    entries: dict[str, bytes], *, plan: MaterializePlan
) -> dict[str, bytes]:
    """按 `plan.workbook_row_change` 的**声明**改引用侧 sheet 与 definedNames。

    🔴 **逐条按声明改，不重跑扫描。** 计划期已经把「改哪些位置、改成什么」冻结进
    `PropagationEntry`；这里若重新扫一遍再改，apply 与 plan 就成了两个真源，
    而 `verify_unmanaged_regions` 的归一化只认 plan 那一份 ⇒ 任何不一致都会表现为
    「验证判漂移」而真因是「apply 没按声明做」。

    两个声明字段都为 `None` 时逐字节不动（零传播路径）。

    ═══ 删行侧（A3/A4）═══

    删行的声明放在 `plan.deletion_change`（`RowDeletionChangeSet`），与插行的
    `plan.workbook_row_change` **分开两个字段** —— 共用一个字段就得在每个消费点做
    `isinstance` 判断，那是把 kind 信息从类型里挤到调用点。

    🔴 本函数的**替换算法逐字未变**（含 `&apos;` 四候选形态与单次扫描）：删行只是把
    另一份声明喂进来。两种声明都只暴露 `.propagations`，下游一行都不必改。
    """
    change = plan.workbook_row_change
    if change is not None and plan.deletion_change is not None:
        raise RowSetDivergenceError(
            "[convergence_two_propagation_declarations] 同时存在插行与删行两份传播声明 —— "
            "6.8b 的分流保证两者互斥，走到这里说明计划期与 apply 口径漂移了"
        )
    if change is None:
        change = plan.deletion_change
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
        # 🔴 候选顺序含**单引号→&apos; 的转义形态**：definedName / 公式里的 sheet 名
        #    单引号在 workbook.xml 里序列化为 `&apos;`（如 `&apos;境外销售收入检查D4-26&apos;`），
        #    而计划期 `ref_before` 由 `_unescape`(html.unescape) 还原成**裸单引号** `'`。
        #    `_escape` 只转义 `& < >`（不转单引号），于是裸 `'` 的候选在 `&apos;` 序列化的
        #    workbook.xml 里 `count()` 恒为 0 → 误报 PropagationDriftError（D4-26 Print_Area
        #    33→34、FOOTER_ANCHOR 30→31 两处真栈）。补一个 `'`→`&apos;` 的候选即对齐序列化。
        def _apos(s: str) -> str:
            return s.replace("'", "&apos;")

        # 🔴 **单次扫描、同时替换**，不是逐对 `text.replace()` 串行改。
        #
        #    串行改有一个会双重位移的真缺陷：位移计划里同一 part 常同时含
        #    **相邻行**的两条声明（D1-4 实测 `B23→B24` 与 `B24→B25` 并存，
        #    B/C/K/L 四列各一对）。串行时 `B23→B24` 先执行，文本里**新产生**一个
        #    `B24`，紧接着 `B24→B25` 就把原有的和新产生的**一起**改掉 ⇒ 每对多命中
        #    1 次，8 条声明实际改了 12 处，最后以 `PropagationDriftError`
        #    「声明 8 处实际改了 12 处」报出来 —— 报错本身是对的（它拦住了坏写盘），
        #    但归因会被带向「artifact 在两相之间被动过」，而真因是本函数的替换顺序。
        #
        #    单次扫描下替换产物不再参与匹配：`B23` → `B24`（不再被重扫）、
        #    原有 `B24` → `B25`，applied == declared == 8。
        #
        #    候选形态的选取仍**基于替换前的原文**（`text.count`），与串行版一致；
        #    正则候选按长度降序排列，保持「长的先匹配」（`!A2` ⊂ `!A25`）这条既有语义
        #    —— `re` 的交替是最左优先、同位置按候选顺序，故降序排列即等价。
        import re as _re

        # 🔴 候选还要含**数字字符引用（NCR）编码的 sheet 名**：某些 Excel 保存路径把公式里
        #    的 CJK sheet 名序列化成 `&#26126;&#32454;&#34920;`（如 L6 的 附注国企/检查表L6-4，
        #    `'明细表L6-2'!P20-SUM(...)`），而计划期 `ref_before` 由解码后的 XML 得到裸中文
        #    `'明细表L6-2'!P20`。前四种候选（含 `&apos;`）都只覆盖单引号转义，不覆盖 NCR ⇒
        #    裸中文的 `count()` 在 NCR 序列化的 sheet.xml 里恒为 0 → 误报 PropagationDriftError
        #    （L6 附注国企 sheet5 P20/Q20/R20/S20 四条真栈）。补 NCR 候选即对齐该序列化形态。
        #    NCR 只编码非 ASCII 字符（与 openpyxl/Excel 写法一致），ASCII（引号/列标/行号/`!`）不动。
        def _ncr(s: str) -> str:
            return "".join(ch if ord(ch) < 128 else f"&#{ord(ch)};" for ch in s)

        replacements: dict[str, str] = {}
        for before, after in sorted(pairs, key=lambda kv: len(kv[0]), reverse=True):
            for cand_before, cand_after in (
                (_apos(_escape(before)), _apos(_escape(after))),
                (_escape(before), _escape(after)),
                (_apos(before), _apos(after)),
                (before, after),
                # NCR 形态（CJK sheet 名被编码成 &#N;）；与上面单引号/转义候选正交。
                (_apos(_ncr(before)), _apos(_ncr(after))),
                (_ncr(before), _ncr(after)),
            ):
                if text.count(cand_before):
                    # 同一 cand_before 被两条声明共用时保留首个映射（与串行版
                    # 「第一条替换掉之后第二条就找不到了」的可见结果一致）。
                    replacements.setdefault(cand_before, cand_after)
                    break
        if replacements:
            ordered = sorted(replacements, key=len, reverse=True)
            pattern = _re.compile("|".join(_re.escape(k) for k in ordered))
            counter = {"n": 0}

            def _swap(match: _re.Match[str]) -> str:
                counter["n"] += 1
                return replacements[match.group(0)]

            text = pattern.sub(_swap, text)
            applied += counter["n"]
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

    ═══ 删行分支（spec workpaper-sync-row-deletion-multi-region-propagation A7）═══

    门原为 `if plan.row_shift is None: return None` ⇒ **删行后一相都不复核**。
    A2（runtime binding 重冻结）与 A5（裸引用平移）里任何一处算错，都要等到**下一次**
    materialize 才以别的症状冒出来（计划期 `assert_footer_anchor_stable` 的
    `FooterAnchorDriftError`），归因要跨两次物化 —— 上游正是为此把这一相立成独立的
    第二相，该论点在删行侧同样成立、只是符号相反。

    改为「**两个位移载体都空**才 return」。两个判据函数都按载体鸭子分流，算术在各自
    函数里（不在这里写 if，写两遍就会漂）。
    """
    carrier = plan.row_shift if plan.row_shift is not None else plan.row_deletion
    if carrier is None:
        return None
    entries = _read_entries(staged_bytes)
    footer_row = assert_footer_anchor_stable(
        entries=entries,
        sheet_part=plan.sheet_part,
        contract=contract,
        runtime_binding=runtime_binding,
        row_shift=carrier,
        table_key=region.table_key,
        # 同 sheet 双区：apply 后复核同样按 region 的物理 table_name 取本区冻结 footer，
        # 可见侧 marker 从本区数据首行起搜（位移不改 first_row）。
        table_name=region.table_name,
        search_from_row=region.first_row,
    )
    if footer_row is None:
        return None
    anchor = next(
        (
            table.footer_anchor
            for sheet in contract.sheets
            for table in sheet.tables
            if table.table_key == region.table_key and table.footer_anchor is not None
        ),
        None,
    )
    assert_footer_formula_covers_managed_rows(
        entries=entries,
        sheet_part=plan.sheet_part,
        footer_row=footer_row,
        region=region,
        row_shift=carrier,
        carries_total_formula=bool(anchor and anchor.carries_total_formula),
    )
    return footer_row


def _sheet_table_parts(entries: Mapping[str, bytes], *, sheet_part: str) -> tuple[str, ...]:
    """该 sheet 关联的**全部** Excel Table part（走 worksheet rels，OOXML 标准关联）。

    用 rels 而不是「扫 `xl/tables/*.xml` 再比 sheet 名」：Table part 里没有所属 sheet 的
    信息，sheet→table 的唯一权威关联就是 worksheet 的 `<tableParts>` / rels。
    """
    import posixpath

    rels = (
        f"{posixpath.dirname(sheet_part)}/_rels/{posixpath.basename(sheet_part)}.rels"
    )
    raw = entries.get(rels)
    if raw is None:
        return ()
    xml = raw.decode("utf-8", errors="replace")
    out: list[str] = []
    for match in re.finditer(r"<Relationship\b[^>]*/?>", xml):
        tag = match.group(0)
        type_attr = re.search(r'\bType="([^"]*)"', tag)
        target_attr = re.search(r'\bTarget="([^"]*)"', tag)
        if type_attr is None or target_attr is None:
            continue
        if not type_attr.group(1).rstrip("/").endswith("/table"):
            continue
        part = posixpath.normpath(
            posixpath.join(posixpath.dirname(sheet_part), target_attr.group(1))
        )
        out.append(part.lstrip("/"))
    return tuple(out)


#: Excel Table 的 `ref="A7:W25"` 形态 —— **四个** ref 改写器共用这一个。
#:
#: 🔴 收敛成常量的理由不是「少打几个字」：`_shift_sibling_table_refs` /
#: `_grow_managed_table_ref` / `_shrink_managed_table_ref` / `_shrink_sibling_table_refs`
#: 四处必须看到**同一批** `ref`。各写一份字面量时，任何一处的形态收窄（比如把
#: `[A-Z]{1,3}` 写成 `[A-Z]{1,2}`）只会让**那一处**漏掉宽表，而症状落在很远的地方
#: （反读时尾部空 UUID 行 → 重新 mint → `extra`），归因极难。
_TABLE_REF_RE: Final[re.Pattern[str]] = re.compile(
    r'(?P<prefix>\bref=")(?P<ref>[A-Z]{1,3}\d+:[A-Z]{1,3}\d+)"'
)


def _rewrite_table_ref_rows(
    xml: str, *, remap_head: Callable[[int], int], remap_tail: Callable[[int], int]
) -> tuple[str, int]:
    """把 XML 里每个 Table `ref` 的首尾**行**分量按两个 remap 改写。

    只改行分量、列跨度逐字保留（`assert_identity_inventory_retained` 只锁列跨度，
    「行区间随插删行变化属合法」；`_classify_parts` 又把 `xl/tables/**` 整类排除）。

    首尾各给一个 remap 而不是一个：插行侧本 binding 的末行边界是 `>= insert_at - 1`
    （追加插行要把新行包进来），而首行是 `shift.shift`；删行侧的兄弟表首尾都走同一个
    `remap(row)`。两个入参让这些差异留在**调用方**，改写循环只有一份。

    Returns:
        `(新 XML, 改动的 ref 处数)`
    """
    changed = 0

    def _one(match: re.Match[str]) -> str:
        nonlocal changed
        head, tail = match.group("ref").split(":", 1)
        head_col = re.sub(r"\d", "", head)
        tail_col = re.sub(r"\d", "", tail)
        head_row = int(re.sub(r"\D", "", head) or 0)
        tail_row = int(re.sub(r"\D", "", tail) or 0)
        new_head_row = remap_head(head_row)
        new_tail_row = remap_tail(tail_row)
        if (new_head_row, new_tail_row) == (head_row, tail_row):
            return match.group(0)
        changed += 1
        return (
            f'{match.group("prefix")}{head_col}{new_head_row}:'
            f'{tail_col}{new_tail_row}"'
        )

    return _TABLE_REF_RE.sub(_one, xml), changed


def _shift_sibling_table_refs(
    entries: dict[str, bytes], *, plan: MaterializePlan, own_part: str
) -> tuple[dict[str, bytes], int]:
    """把**同 sheet 其它** Excel Table 的 `ref` 按插行位移。

    ═══ 为什么必须做（真栈实测的 500）═══

    D4-1 审定表在**同一张 sheet** 上有两个受管区：主营 `GT_D41_MAIN_ROWS`（W 列，
    `A7:W11`）/ 其他 `GT_D41_OTHER_ROWS`（X 列，`A14:X17`）。主营段派生行多于模板占位时
    要插行；「任一 binding 需插行」会让单趟写入 decline，回落**逐趟链式**路径
    （`adapters/excel.py`：上一趟产物当下一趟 substrate）。

    此前本模块只更新 `plan.table_part`（**本 binding** 那一个 Table part），于是主营那趟
    插完行后，其他区的数据行下移了而它的 `ref` 逐字不动 ⇒ 其他区那趟按旧 `ref` 读 14..17，
    那里已经是主营区的新行、X 列无 UUID ⇒ `resolved_sheet_by=None` ⇒
    `IdentityCarrierMissingError`（且文案误报契约首张表 `d42-managed`，现场像是 D4-2 坏了）。

    ⚠️ 兄弟表的末行边界是 `>= insert_at`，**不是**本 binding 的 `>= insert_at - 1`：
    后者表达「追加插行紧贴本表末行 ⇒ 本表要把新行包进来」，那是本 binding 独有的语义。
    对兄弟表，`tail_row == insert_at - 1` 意味着它末行正好在插入点上方一行，新行不属于它，
    **不得**扩张。`shift.shift()` 天然给出这个边界（`row < insert_at` 原样返回），
    所以首末行各调一次即可同时覆盖三种情形：整体下移 / 跨插入点扩张 / 完全在上方不动。

    判据：`tests/workpaper_sync/test_sibling_table_ref_row_shift.py`
    """
    shift = plan.row_shift
    assert shift is not None, "调用方保证"
    siblings = [
        p
        for p in _sheet_table_parts(entries, sheet_part=plan.sheet_part)
        if p != own_part and p in entries
    ]
    total = 0
    for part in siblings:
        xml = entries[part].decode("utf-8")
        xml_new, changed = _rewrite_table_ref_rows(
            xml, remap_head=shift.shift, remap_tail=shift.shift
        )
        if changed:
            entries[part] = xml_new.encode("utf-8")
            total += changed
    # 🔴 **不**断言 total > 0：兄弟表完全位于插入点**上方**时一处都不该动，那是正确行为
    #    （与本 binding 的 `table_ref_not_grown` 判据不同 —— 那里 0 处改动确实是缺陷）。
    return entries, total


def _grow_managed_table_ref(
    entries: dict[str, bytes], *, plan: MaterializePlan
) -> dict[str, bytes]:
    """把受管 Excel Table 的 `ref` 末行按 `plan.row_shift.count` 长上去。

    只改 `ref` 的**行**分量，列跨度逐字保留 —— `assert_identity_inventory_retained`
    只锁列跨度，「行区间随插删行变化属合法」。`_classify_parts` 又把 `xl/tables/**`
    整类排除，所以这不是未管理区域漂移。

    Table part 在计划期就已定位（`_plan_row_shift` → `_managed_table_part`），
    这里不再现搜 —— 现搜等于把「定位失败」推到写盘期，而那时已经有字节落地了。

    🔴 本 binding 的 Table 之外，**同 sheet 的兄弟 Table** 也必须位移，否则同 sheet 多受管区
    底稿（D4-1 主营/其他、D4-9 本期/上期、D4-20 三区、D4-34、D4-36）在上区插行后会让下区
    的 `ref` 与实际数据错位 —— 见 :func:`_shift_sibling_table_refs` 的完整根因说明。
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

    def _grow_tail(tail_row: int) -> int:
        # 末行：两种形态**同一个算式**，判据是 `tail_row >= insert_at - 1`
        #   ① `tail_row >= insert_at`      → 末行被推下去 ⇒ +count（位移）
        #   ② `tail_row == insert_at - 1`  → **追加插行**：新行紧贴 Table 末行之后，
        #                                     Table 必须长上去把它们包进来 ⇒ +count（增长）
        # 🔴 首版写成 `if tail_row < insert_at: 不动`，把形态 ② 判成了「不动」——
        #    而追加插行**恰好**总是形态 ②（`insert_at = 最后一个数据行 + 1`），
        #    于是每一次真实插行都撞「ref 一处都没长」。
        return tail_row + shift.count if tail_row >= shift.insert_at - 1 else tail_row

    # 首行：落在插入点及其之下 ⇒ 整体下移（`plan.shift` 自带这个边界）。
    xml_new, changed = _rewrite_table_ref_rows(
        xml, remap_head=shift.shift, remap_tail=_grow_tail
    )
    if not changed:
        raise RowSetDivergenceError(
            f"[excel_row_shift_table_ref_not_grown] Table part {part} 的 ref 一处都没长"
            f"（插入点 {shift.insert_at}，插 {shift.count} 行，实测 ref: "
            f"{re.findall(r'ref=\"[^\"]+\"', xml)[:3]}）—— 新行会落在受管区域之外，"
            "反读时静默丢数据"
        )
    entries[part] = xml_new.encode("utf-8")
    # 同 sheet 的兄弟 Table（下方的整体下移 / 跨插入点的扩张 / 上方的不动）。
    entries, _sibling_changes = _shift_sibling_table_refs(
        entries, plan=plan, own_part=part
    )
    return entries


def _shrink_managed_table_ref(
    entries: dict[str, bytes], *, plan: MaterializePlan, removed: int
) -> dict[str, bytes]:
    """受管 Excel Table 的 `ref` 末行按已删行数**收缩**（`_grow_managed_table_ref` 的对称件）。

    spec: workpaper-sync-managed-row-convergence（Requirement 4 更正 6 AC 8）

    ═══ 为什么必须收缩 ═══

    `shrink_sheet_rows` 只删 sheet 里的 `<row>`，**不动** `xl/tables/*.xml` 的 `ref`。
    不收缩的后果与「把受管区删空」同源：ref 仍声明着已经不存在的行区间 ⇒ 反读时
    `resolve_managed_region` 按旧区间找身份 ⇒ 尾部出现空 UUID 行 ⇒
    `IdentityCarrierMissingError`（「Table ref 覆盖的行区间内一个 row identity 都没反读到」
    的邻近形态，实测于 D4-31）。

    与 grow 的差异刻意只有一处：末行 `-removed` 而不是 `+count`。首行**一律不动** ——
    删的都是受管区内的数据行（判据保证 stale ⊆ 受管区内的物理身份行），首行是表头/区首
    锚点，删数据行不该动它。

    🔴 只改**行**分量、列跨度逐字保留（与 grow 同：`assert_identity_inventory_retained`
    只锁列跨度，「行区间随插删行变化属合法」；`_classify_parts` 把 `xl/tables/**` 整类
    排除，故这不是未管理区域漂移）。
    """
    if removed <= 0:
        return entries
    part = plan.table_part
    if not part or part not in entries:
        raise RowSetDivergenceError(
            f"[convergence_table_part_missing] 计划里的 Table part {part!r} 不在 zip 里 —— "
            "删行后 Table ref 无从收缩，ref 会继续覆盖已删区间并在反读时判身份缺失"
        )
    xml = entries[part].decode("utf-8")
    head_rows = [
        int(re.sub(r"\D", "", m.group("ref").split(":", 1)[0]) or 0)
        for m in _TABLE_REF_RE.finditer(xml)
    ]

    def _shrink_tail(tail_row: int) -> int:
        new_tail_row = tail_row - removed
        # 🔴 收缩不得把 ref 缩成「末行 < 首行」：那等于把受管区删空，而 6.8b 的分级判定
        #    本应已经拦住这种情形（剩 0 行走清空分支）。走到这里说明判定与实际删除量
        #    不一致 ⇒ fail closed，不写出一个坏 ref。
        floor = min(head_rows) if head_rows else 1
        if new_tail_row < floor:
            raise RowSetDivergenceError(
                f"[convergence_table_ref_underflow] 收缩 {removed} 行会让 Table ref "
                f"的末行 {new_tail_row} 落到首行 {floor} 之上 —— "
                "受管区被删空，6.8b 的容量分级本应改走清空分支"
            )
        return new_tail_row

    # 首行**一律不动** —— 删的都是受管区内的数据行（判据保证 stale ⊆ 受管区内的物理
    # 身份行），首行是表头/区首锚点，删数据行不该动它。
    xml_new, changed = _rewrite_table_ref_rows(
        xml, remap_head=lambda row: row, remap_tail=_shrink_tail
    )
    if not changed:
        raise RowSetDivergenceError(
            f"[convergence_table_ref_not_shrunk] Table part {part} 的 ref 一处都没缩"
            f"（已删 {removed} 行，实测 ref: "
            f"{re.findall(r'ref=\"[^\"]+\"', xml)[:3]}）—— ref 会继续覆盖已删区间，"
            "反读时判身份缺失"
        )
    entries[part] = xml_new.encode("utf-8")
    # 🔴 A1：同 sheet **兄弟** Table 的 `ref` 也必须收缩（本表之外那些）。
    #    不收缩的后果是 G2 实测那条症状链的第一环 —— 完整根因见
    #    :func:`_shrink_sibling_table_refs`。
    entries, _sibling_changes = _shrink_sibling_table_refs(
        entries, plan=plan, own_part=part
    )
    return entries


def _shrink_sibling_table_refs(
    entries: dict[str, bytes], *, plan: MaterializePlan, own_part: str
) -> tuple[dict[str, bytes], int]:
    """把**同 sheet 其它** Excel Table 的 `ref` 按删行收缩（`_shift_sibling_table_refs` 的对称件）。

    spec: workpaper-sync-row-deletion-multi-region-propagation（Requirement 2 / A1）

    ═══ 为什么必须做（G2 实测症状链的第一环）═══

    D4-1 审定表同 sheet 两个受管区：main `GT_D41_MAIN_ROWS` / other `GT_D41_OTHER_ROWS`。
    删 main 区一行 ⇒ 物理上 other 区整体**上移**一行，而 other 的 `ref` 逐字不动
    ⇒ `resolve_managed_region` 按旧 `ref` 算出的 `region.row_span` **头部少一行、尾部多一行**
    ⇒ `excel_extract` 在多出来的那一行读到空 UUID
    ⇒ `_scan_row_identities` 按 `delete_policy=tombstone`（B11：139/153 个 table 都是它）
       走 `assign_new_id` ⇒ `mint_row_identity` 产 `GTROW-MINTED-*`
    ⇒ 新身份不在 `intended` ⇒ **又一轮 `extra`** ⇒ `roundtrip_projection_mismatch` 500。

    ═══ 🔴 与本表的两处刻意差异 ═══

    1. **首尾都要动。** 本表（:func:`_shrink_managed_table_ref`）首行一律不动，因为删的是
       它自己区内的数据行、首行是区首锚点；兄弟表整块在删除点**下方**，首尾都要上移。
       判据用**统一的** `remap(row)`，不写两个 if —— 写两个 if 就会出现「首行用 A 边界、
       末行用 B 边界」这类只在某种布局下才暴露的错位。
    2. **一处都没缩时不抛。** 兄弟表完全位于被删行**上方**时零改动是正确行为
       （与 `_shift_sibling_table_refs` 同纪律，也与本表的 `table_ref_not_shrunk` 相反 ——
       那里 0 处改动确实是缺陷，因为删的行就在它区内）。

    走 :func:`_sheet_table_parts`（worksheet rels）取同 sheet 的 Table 清单，
    **不**扫 `xl/tables/*` 猜归属：Table part 里没有所属 sheet 的信息。
    """
    shift = plan.row_deletion
    assert shift is not None, "调用方保证"
    siblings = [
        p
        for p in _sheet_table_parts(entries, sheet_part=plan.sheet_part)
        if p != own_part and p in entries
    ]

    def _remap(row: int) -> int:
        """统一的兄弟表行映射：区间端点语义（被删行塌到相邻存活行）。

        兄弟区整块在删除点之外，端点落在被删行上意味着「删的行跨进了兄弟区」——
        那是 6.8b 的 stale ⊆ 本区受管行这条前提被破坏。用端点语义而不是 `shift`
        （会返回 `None`）让这种情形退化成一个**保守**的行号而不是崩在这里；
        真正的拦截在计划期（`RowDeletionShift` 构造时的区内校验）。
        """
        return shift.shift_range_start(row)

    total = 0
    for part in siblings:
        xml = entries[part].decode("utf-8")
        xml_new, changed = _rewrite_table_ref_rows(
            xml, remap_head=_remap, remap_tail=_remap
        )
        if changed:
            entries[part] = xml_new.encode("utf-8")
            total += changed
    return entries, total


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

    🔴 两个位移载体都为空时调用方不会进来（与 `_grow_managed_table_ref` 同相）。

    ═══ 删行侧（spec workpaper-sync-row-deletion-multi-region-propagation / A2）═══

    本函数原为 **insert-only**（首行取 `plan.row_shift` 并断言非空）。删行时那 7 个被重写的
    键一个都不动 ⇒ **下一次** materialize 在计划期就撞 `assert_footer_anchor_stable` 的
    `FooterAnchorDriftError`（可见侧 marker 实测 = 冻结值 − 删行数，而 `row_shift is None`
    分支要求两者严格相等）。症状是「删行这次成功了、下次点在线编辑起 500」——
    时间差让根因极难归位，这是 A2 必须与 A1 同批落地的理由。

    修法是**抽位移载体协议**：insert 传 `RowShiftPlan`、delete 传 `RowDeletionShift`，
    两者鸭子兼容。🔴 insert 分支的算术**逐字未变**（零回归按定义成立）。
    `same_sheet_tids` 的推导**原样复用**下面那一段（worksheet rels → 兄弟 Table
    `displayName` → `GT_MANAGED_TABLES`/`GT_TEMPLATE_IDS` 平行清册）—— 抄第二份就会把
    那一段踩过的「把『同 sheet 兄弟』和『不同 sheet』混成一类」这个坑复制过来。

    Spec: published-representation-production-path-and-lane-adjudication
          + workpaper-sync-row-deletion-multi-region-propagation
    """
    # ── 位移载体二选一（两者互斥，由 6.8b 的分流保证）──────────────────────
    shift = plan.row_shift if plan.row_shift is not None else plan.row_deletion
    assert shift is not None, "调用方保证"
    #: True = 删行载体。判据用**成员存在性**而不是 `isinstance`：`excel_row_shift` 反向
    #: import 本模块会成环，而 `RowDeletionShift` 的 `deleted_rows` 是它独有的成员。
    deleting = getattr(shift, "deleted_rows", None) is not None

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
    managed_sheet_key = str(getattr(plan, "managed_sheet_key", None) or "").strip() or None
    managed_table_name = str(getattr(plan, "managed_table_name", None) or "").strip() or None
    # 🔴 同 sheet 双区：优先按本 region 的物理 table_name 经 `_GT_SYNC` 平行清册
    #    (`GT_MANAGED_TABLES`/`GT_TEMPLATE_IDS`) 取 per-region template_id（D41MAIN / D41OTHER）。
    #    这样 D4-1 主营插行只移位 `GT_FOOTER_ROW_D41MAIN`，不误动 `GT_FOOTER_ROW_D41OTHER`。
    #    映射不到（单 region / 旧 artifact）再退回 sheet_key → 紧凑 TEMPLATE_ID（D425），
    #    避免 `d4-25-managed` → `D4-25` 对不上 `GT_FOOTER_ROW_D425`。
    managed_tid = _template_id_for_table_name(pair_map, managed_table_name)
    if managed_tid is None:
        managed_tid = (
            _template_ids_from_sheet_key(managed_sheet_key)[0]
            if managed_sheet_key
            else None
        )
    # 🔴 **同 sheet 兄弟区的 footer 也必须移位**：插行是物理的，同一张 sheet 上位于插入点
    #    下方的一切都会下移，兄弟区的 footer 不例外。
    #    此前这里只放行 `GT_FOOTER_ROW_{managed_tid}`，注释写「D4-1 主营插行只移位
    #    `_D41MAIN`，不误动 `_D41OTHER`」—— 那句话把「同 sheet 兄弟」和「不同 sheet」
    #    混成一类了。不同 sheet（D42 插行 vs D43）确实不该动，同 sheet 却必须动，
    #    否则其他区那一趟会撞 `FooterAnchorDriftError`（实测：D4-1 主营插 7 行后
    #    其他区 footer 物理在 25 行，而冻结值仍是 18）。
    #    同 sheet 的判定不靠 sheet_key 猜，走 worksheet rels → 兄弟 Table displayName →
    #    `GT_MANAGED_TABLES`/`GT_TEMPLATE_IDS` 平行清册这条已有的权威桥梁。
    same_sheet_tids: set[str] = {managed_tid} if managed_tid else set()
    for sib_part in _sheet_table_parts(entries, sheet_part=plan.sheet_part):
        raw_sib = entries.get(sib_part)
        if raw_sib is None:
            continue
        sib_xml = raw_sib.decode("utf-8", errors="replace")
        sib_name = None
        for attr in ("displayName", "name"):
            found = _re.search(rf'\b{attr}="([^"]*)"', sib_xml)
            if found is not None:
                sib_name = found.group(1)
                break
        sib_tid = _template_id_for_table_name(pair_map, sib_name)
        if sib_tid:
            same_sheet_tids.add(sib_tid)

    def _row_after(row: int, *, what: str) -> int:
        """单个**行号**键的重冻结值。insert 与 delete 共用这一个出口。

        🔴 删行侧要处理 `shift(row) is None`（该行被删了）。`_GT_SYNC` 里的行号键指的都是
        受管区末行 / footer 行，它们**不该**落在被删行上（stale ⊆ 受管区内的数据行、
        footer 在区外）。真落上了说明计划期的区间声明与实际删除量不一致 ⇒ fail-closed，
        不把一个塌陷后的行号冻结下来（那会在下一次 materialize 变成 footer 漂移）。
        """
        if not deleting:
            return shift.shift(row)  # type: ignore[return-value]
        got = shift.shift(row)
        if got is None:
            raise RowSetDivergenceError(
                f"[excel_row_shift_binding_row_deleted] runtime binding 的 {what}={row} "
                f"落在被删行 {list(shift.deleted_rows)} 上 —— 受管区结构坐标不该指向被删行，"
                "不得把塌陷后的行号冻结进 representation"
            )
        return got

    # ── 本趟是不是 primary sheet ──────────────────────────────────────────
    #
    # `GT_ROW_UUID_LAST_ROW` / `GT_MANAGED_RANGE` / `GT_MANAGED_TABLE_REF` / `GT_FOOTER_ROW`
    # 这四个键是 **workbook 全局**的，值取自 instrumentation 的 **primary** sheet
    # （实测 D1 册：`GT_MANAGED_TABLE=GT_D13_ROWS` / `GT_MANAGED_RANGE=A11:O20` /
    #  `GT_ROW_UUID_LAST_ROW=20` 全是 D1-3 那张表的坐标，其余 sheet 走
    #  `GT_FOOTER_ROW_{TID}` 平行清册）。
    #
    # 🔴 **删行侧必须按 primary 门控这三个键**，插行侧的无条件重写在删行侧不安全：
    #    插行时 primary 的行号更小（`tail_row >= insert_at - 1` 恒不成立）⇒ 算术碰不到它；
    #    删行时方向相反 —— D1-8 删它自己的首数据行 14 会让 `shift_range_end(20)` 变 19，
    #    把 **D1-3** 的受管区末行凭空缩掉一行。那会在下一次物化 D1-3 时表现为
    #    footer/区间漂移，而现场看起来完全与 D1-8 无关。
    #
    # ⚠ 插行分支**逐字不变**（零回归按定义成立）；插行侧的同款无条件重写属**既有**形态，
    #   本 spec 不改它（改了会动插行的冻结字节），只在此登记：见判据
    #   `test_insert_side_global_keys_stay_unconditional`。
    _first_tid_key = next((k for k, _ in pairs if k.startswith("GT_FOOTER_ROW_")), None)
    is_primary_trip = (
        managed_tid is None
        or _first_tid_key is None
        or _first_tid_key == f"GT_FOOTER_ROW_{managed_tid}"
    )

    new_pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in pairs:
        seen.add(key)
        if key == "GT_ROW_UUID_LAST_ROW":
            if deleting and not is_primary_trip:
                new_value = value
            elif deleting:
                # UUID 区间末行是**区间端点** ⇒ 走端点语义（被删行塌到上一存活行）。
                # 不能走 `_row_after`：删受管末行恰好是最常见的收敛形态
                # （用户从 HTML 表尾部删行），那时 `shift` 返回 `None`。
                new_value = str(shift.shift_range_end(old_last_row))
            else:
                # 末行同样适用「追加插行紧贴末行之后 ⇒ 必须包进来」的边界（见
                # `_grow_managed_table_ref` 的同名算式），与 Table ref 增长保持同源。
                new_value = str(old_last_row + shift.count if old_last_row >= shift.insert_at - 1 else old_last_row)
        elif key == "GT_FOOTER_ROW" and old_footer_row is not None:
            # 主键跟 instrumentation 的 primary sheet；仅本趟是 primary 时才移位。
            # （判定已上提为 `is_primary_trip`，两侧共用同一条口径。）
            if is_primary_trip:
                new_value = str(_row_after(old_footer_row, what=key))
            else:
                new_value = value
        elif key.startswith("GT_FOOTER_ROW_") and managed_tid is not None:
            # 只重冻结**本 sheet**（含同 sheet 兄弟区）的 per-template footer 键
            # —— D42 插行不得动 D43（不同 sheet），但 D41MAIN 插行必须动 D41OTHER（同 sheet）。
            # 各键实际移不移由载体按它自己的行号与变更点的关系决定：
            # 插入点上方的兄弟 footer 原样返回，下方的 +count；删行侧同理给负向。
            if key.removeprefix("GT_FOOTER_ROW_") in same_sheet_tids:
                old_keyed = _to_int(value, what=key, required=False)
                new_value = (
                    str(_row_after(old_keyed, what=key))
                    if old_keyed is not None
                    else value
                )
            else:
                new_value = value
        elif key in ("GT_MANAGED_RANGE", "GT_MANAGED_TABLE_REF"):
            if deleting and not is_primary_trip:
                new_value = value
            else:
                new_value = _remap_range_string(value, shift) if value else value
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
    # 🔴 删行侧 `count` 取**负**：累计位移必须可回落，否则「插 3 行又删 3 行」会被记成
    #    累计 +6，而模板升级重放会按那个假累计量把行数放大一倍。
    signed_count = -shift.count if deleting else shift.count
    total_inserted += signed_count

    # ── 结构指纹 ────────────────────────────────────────────────────────────
    #
    # 🔴 **插行分支逐字未变**（含它原有的一处不自洽：非 primary 趟上面把 `GT_FOOTER_ROW`
    #    保留旧值，而这里按位移算 —— 那是既有形态，改它会动插行的冻结字节，本 spec 不碰，
    #    只登记，见判据 `test_insert_side_fingerprint_arithmetic_is_untouched`）。
    #
    # 🔴 **删行分支喂的是重冻结后的那两个值**，与上面的 primary 门控同源：
    #    另算一遍会让「非 primary 趟保留旧键值、指纹却按位移算」这种不自洽在删行侧复现，
    #    而删行侧的方向使它**数值可达**（插行侧靠行号大小巧合碰不到）。
    if deleting:
        _frozen = dict(new_pairs)
        fp_last_row = int(str(_frozen.get("GT_ROW_UUID_LAST_ROW") or "0") or 0)
        fp_footer_row = (
            int(str(_frozen.get("GT_FOOTER_ROW") or "0") or 0)
            if old_footer_row is not None
            else 0
        )
    else:
        fp_last_row = old_last_row + (
            shift.count if old_last_row >= shift.insert_at - 1 else 0
        )
        fp_footer_row = (
            shift.shift(old_footer_row) if old_footer_row is not None else 0
        )
    fingerprint = _structure_fingerprint(
        last_row=fp_last_row,
        footer_row=fp_footer_row,
        uuid_col=uuid_col,
        table_ref=table_ref,
    )

    # `GT_LAST_SHIFT` 的形态逐字不变（`{变更点}|{行数}|{累计}`），只是删行侧行数为负。
    change_at = min(shift.deleted_rows) if deleting else shift.insert_at
    for extra in (
        ("GT_LAST_SHIFT", f"{change_at}|{signed_count}|{total_inserted}"),
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


def _remap_range_string(raw: str, shift: Any) -> str:
    """`A13:AM24` 形态 → 按位移载体的方向改写首尾**行**分量。

    ═══ 为什么是**一个**函数按方向分流，不是两份 ═══

    抄第二份（`_shrink_range_string`）会让「首行边界」这条规则有两个真源。而这条规则恰好
    是插行侧踩过坑的地方（`tail_row >= insert_at - 1` 的追加插行形态），复制过去就把坑
    也复制了。分流点只有一处：`deleted_rows` 是否存在。

    * **insert** —— 算术**逐字未变**（见下面原 docstring）；
    * **delete** —— 首行走 `shift_range_start`、末行走 `shift_range_end`
      （两者塌陷方向相反，见 `RowDeletionShift.shift_range_end` 的推导）。
    """
    import re as _re

    m = _re.match(
        r"^(?P<hc>[A-Z]{1,3})(?P<hr>\d+):(?P<tc>[A-Z]{1,3})(?P<tr>\d+)$", raw.strip()
    )
    if m is None:
        raise RowSetDivergenceError(
            f"[excel_row_shift_range_invalid] runtime binding 的受管区 {raw!r} 不是 A1 区间"
            " —— 无从按行变更改写"
        )
    head_row = int(m.group("hr"))
    tail_row = int(m.group("tr"))
    if getattr(shift, "deleted_rows", None) is not None:
        new_head = shift.shift_range_start(head_row)
        new_tail = shift.shift_range_end(tail_row)
        if new_tail < new_head:
            raise RowSetDivergenceError(
                f"[excel_row_shift_range_underflow] 删行让受管区 {raw!r} 缩成 "
                f"{new_head}..{new_tail}（末行在首行之上）—— 受管区被删空，"
                "6.8b 的容量分级本应改走清空分支"
            )
        return f"{m.group('hc')}{new_head}:{m.group('tc')}{new_tail}"
    return _grow_range_string(raw, shift)


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


@dataclass(frozen=True)
class MaterializePlanStep:
    """一个 binding 的**写入计划**（还没碰盘）。

    spec: oo-single-pass-materialize-and-room-leave · Requirement 1

    做成显式对象是为了让「算计划」与「落盘」之间有一条缝：多 binding 底稿原先逐 binding
    各跑一次完整的 `materialize_projection`，把上一趟的产物当下一趟的输入 ⇒ 同一本工作簿
    被全量解析 `N × 2` 次（`data_only=True/False` 两个视图各一次；D4 实测 39 binding /
    substrate 链上 **78 次** `openpyxl.load_workbook`，另有 5 次固定开销落在 BytesIO 上 ⇒
    合计 83）。有了这条缝，`materialize_projection_single_pass` 才能「全部计划只解析一次
    substrate、全部写入合成一趟」—— 落地后同一 entry 的 substrate 解析 78 → **2**。
    """

    binding: ExcelIdentityBinding
    plan: MaterializePlan
    strategy: WriteStrategyDecision
    substrate_view: Any
    runtime_binding: Mapping[str, Any]


def _plan_materialize_step(
    *,
    substrate: Path,
    projection: Projection,
    definitions: FrozenEntryDefinitions,
    binding: ExcelIdentityBinding,
    substrate_role: SubstrateRole | str,
    substrate_kind: ArtifactKind | str,
    substrate_state: ArtifactState | str,
    source_bytes: bytes,
    capability: ExcelWriteCapability | None,
    intended_formulas: Mapping[str, str] | None,
    limits: SyncLimits,
    retain_identity_inventory: bool,
) -> MaterializePlanStep:
    """`materialize_projection` 的第 4~6 步（读 substrate identity → 裁决策略 → 算计划）。

    **唯一实现**：单趟路径与逐趟路径都走它，避免「两条路径各算一份计划」那种最难查的漂移。
    """
    substrate_view = extract_projection(
        artifact=substrate,
        definitions=definitions,
        binding=binding,
        substrate_role=substrate_role,
        artifact_kind=substrate_kind,
        artifact_state=substrate_state,
        limits=limits,
        retain_identity_inventory=retain_identity_inventory,
    )
    entries = _read_entries(source_bytes)
    # 同一份 substrate 字节：entries + runtime binding 共用一次 zip 打开，不再
    # `ZipFile(substrate)` 二次读盘（Wave 2 / Requirement 1.4）。
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as zf:
        runtime_binding = read_runtime_binding_pairs(
            zf, metadata_sheet=binding.metadata_sheet
        )
    strategy = select_write_strategy(artifact=substrate, capability=capability)
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
    return MaterializePlanStep(
        binding=binding,
        plan=plan,
        strategy=strategy,
        substrate_view=substrate_view,
        runtime_binding=runtime_binding,
    )


def _apply_step_to_bytes(
    *,
    source_bytes: bytes,
    step: MaterializePlanStep,
    definitions: FrozenEntryDefinitions,
) -> tuple[bytes, ShiftReport | None]:
    """把一个计划应用到**字节**上（zip 级定点改写），含位移后 footer 门。

    位移门刻意在返回前跑：调用方尚未落盘，门不过就零产物（Property 9 的文件侧）。
    """
    staged, shift_report = apply_plan_zip_with_report(source_bytes, step.plan)
    if step.plan.row_shift is not None or step.plan.row_deletion is not None:
        # 🔴 apply 后的**位移后**相：这才是 Requirement 7.1「实测 == 冻结 + 预期位移」与
        #    7.4「用位移后区间求值」真正成立的地方。
        #
        # 🔴 删行载体也要进来（spec workpaper-sync-row-deletion-… A7）：原来只看
        #    `row_shift` ⇒ 删行后一相都不复核，A2/A5 算错要等下一次物化才冒出来。
        #    这里与 `assert_shifted_footer_gates` 内部的门**必须同时**放开 —— 只改一处的
        #    话另一处照旧 return None，看起来接线了其实空转。
        assert_shifted_footer_gates(
            staged_bytes=staged,
            plan=step.plan,
            contract=definitions.contract,
            region=step.substrate_view.region,
            runtime_binding=step.runtime_binding,
        )
    return staged, shift_report


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
    retain_identity_inventory: bool = True,
    compute_structure_hash: bool = True,
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

    source_bytes = substrate.read_bytes()
    step = _plan_materialize_step(
        substrate=substrate,
        projection=projection,
        definitions=definitions,
        binding=binding,
        substrate_role=substrate_role,
        substrate_kind=substrate_kind,
        substrate_state=substrate_state,
        source_bytes=source_bytes,
        capability=capability,
        intended_formulas=intended_formulas,
        limits=lim,
        retain_identity_inventory=retain_identity_inventory,
    )
    substrate_view = step.substrate_view
    strategy = step.strategy
    plan = step.plan

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
            # 位移后 footer 门在 `_apply_step_to_bytes` 内、落盘之前跑（Property 9 文件侧）。
            staged, shift_report = _apply_step_to_bytes(
                source_bytes=source_bytes, step=step, definitions=definitions
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
            # 🔴 ROI-2（多 sheet 性能）：非终趟的 structure_hash 在 adapter.materialize 的
            #    多 binding 循环里**必被丢弃**（只保留 last_result.structure_hash），且最终值
            #    还会被 ContentMutationService._projection_structure_hash 按观测器同构口径覆盖
            #    （BP-30）。故非终趟跳过整簿 normalized_structure_hash（每趟 ~1.4s×34≈52s）是
            #    纯删死算，不改任何被消费的值。终趟/单 binding 仍照算（compute_structure_hash=True）。
            #    占位用 staged 字节 sha256（已算，合法 64-hex，满足 MaterializeResult 非空校验），
            #    它永不被消费（下游只读终趟的 structure_hash）。
            structure_hash=(
                normalized_structure_hash(staged_bytes)
                if compute_structure_hash
                else hashlib.sha256(staged_bytes).hexdigest()
            ),
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


@dataclass(frozen=True)
class SinglePassMaterializeOutcome:
    """单趟物化的产物。

    只带调用方**真会消费**的三样：主 binding 的完整 outcome（含真实 identity 清册）、
    各 binding 的 workbook 位移声明（要合并成一份给 verify）、各 binding 的受管字段数
    （要累加成 `managed_field_count`）。不给 sibling 编一份假清册 —— `ExcelMaterializeOutcome`
    的 `staged_identity_inventory` 不是可空字段，塞 `None` 或塞产物摘要都是伪造身份。
    """

    primary: ExcelMaterializeOutcome
    workbook_row_changes: tuple[Any, ...]
    per_binding_field_counts: Mapping[str, int]


class SinglePassDeclined(Exception):
    """单趟写入不适用于本次输入 —— 调用方必须回落逐趟链式路径。

    刻意用异常而不是返回 `None`：`None` 在调用点极易被当成「成功但没产物」，而这里的语义
    是「我什么都没做，你去走另一条路」。异常带上原因，便于在真库上统计回落比例。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


#: 跨 binding 同格写入的**冲突判据面**（design 附录 A.6 第 1 条 / requirements 1.1，
#: 2026-09-22 拍板：decline 条件从「坐标碰撞」收紧为「坐标碰撞**且** payload 冲突」）。
#:
#: 刻意**不含** `coord`（它是分组键，同格才比）也**不含** `row_key`：`row_key` 是行身份
#: 元数据，不进落盘字节 —— 两方 row_key 不同而其余全同时，写出的 XML 逐字节相同，仍是恒等
#: 覆盖。把它塞进判据面会让 D4 那 4 格良性重叠重新被误判成冲突。
_WRITE_PAYLOAD_FIELDS: Final[tuple[str, ...]] = (
    "kind",
    "value",
    "stable_field_key",
    "mode",
    "formula_text",
)

#: `C38` / `$C$38` → 行列。只用于把碰撞清单排成确定序（先行后列）。
_A1_COORD: Final[re.Pattern[str]] = re.compile(r"^\$?([A-Z]{1,3})\$?(\d+)$")


def coord_sort_key(coord: str) -> tuple[int, str, str]:
    """`C38` → `(38, 'C', 'C38')`：先行后列的**确定性**排序键。

    非 A1 形态退化成 `(0, "", coord)` —— 仍然确定，且不会与真坐标混序。

    🔴 它是「碰撞清单确定性」的唯一实现：`analyze_d4_binding_dependencies.py` 的 D1 报告
    与本模块的 decline 原因必须同一个排序口径，否则同一批碰撞在审计证据里与生产日志里
    顺序不同，对不上账。
    """
    found = _A1_COORD.match(coord)
    if found is None:
        return (0, "", coord)
    return (int(found.group(2)), found.group(1), coord)


def _write_payload(write: CellWrite) -> tuple[str, ...]:
    """一处写入在**冲突判据**下的 payload（与 :data:`_WRITE_PAYLOAD_FIELDS` 同序）。

    `value` 取 `repr` 而不是值本身：`0` / `0.0` / `Decimal('0')` 在 `==` 下相等，落盘字节
    却不同 —— 用 `==` 比会把两个**不同**的写入判成恒等覆盖，单趟就会悄悄改变产物。
    这与 `analyze_d4_binding_dependencies._write_signature` 的 `value_repr` 同口径。
    """
    return (
        write.kind.value,
        repr(write.value),
        write.stable_field_key,
        "" if write.mode is None else str(write.mode),
        write.formula_text,
    )


def _cross_binding_payload_conflicts(
    steps: Sequence[MaterializePlanStep],
) -> tuple[str, ...]:
    """跨 binding 同坐标写入里 **payload 不同**的那些格 —— 排序后的**完整**清单。

    spec: oo-single-pass-materialize-and-room-leave · design 附录 A.3 / A.6

    ═══ 为什么判据是「payload 不同」而不是「坐标相交」═══

    同一个 sheet part 上有多个受管区是常态；同一格被两个 binding 各写一遍也是常态 ——
    `managed_tables_of` 对**静态表**的归属规则是「静态表没有行身份，同 sheet 的每个 binding
    都把它纳入自己的受管坐标」（有意的安全方向：静态格被每个 binding 都当受管 ⇒ 没有任何
    一趟会把它误判成 unmanaged drift）。D4-9 的表级标量表 `customer_totals` 因此被
    `customer_current_rows` / `customer_prior_rows` 两个 binding 各写一遍，落在
    `sheet14.xml` 的 `C24`/`E24`/`C38`/`E38` 共 4 格（真库实测，见附录 A.3）。

    这 4 格两方写入的 payload **逐字段相同**、两种顺序 apply 后 sheet part **逐字节相同**
    ⇒ 「谁最后写」是恒等操作。按旧的「坐标相交即 decline」判据，D4 这个**需求 1.5 指名的
    entry** 会被整体挡在单趟之外，单趟优化对它一点都吃不到。收紧后 D4 可以合并。

    真正不能合并的是「同坐标 + payload 不同」：那时结果取决于谁最后写，而链式顺序在单趟里
    无法复现。这一条按**运行时可判**的形态写（逐对求交 + payload 比对），不是「D4 没问题所以
    都没问题」—— 别的 entry 完全可能出现两个不同 `stable_field_key` 争同一格。

    ═══ 为什么必须排序 + 完整 ═══

    旧实现按 `for coord in set(plan.coords)` 遍历、命中第一处即抛 ⇒ 报的列号随进程 str hash
    种子变（真库上见过 `C38` 与 `E38` 两种），而且抛第一处之后剩下的碰撞看不见。真库要能统计
    回落比例与回落**原因**（需求 3.3），原因就必须是确定的、完整的。
    """
    # part → coord → table_key → payload。同一 binding 在同一格写多次 ⇒ 取**最后一次**，
    # 与 apply 的 last-writer-wins 同相：那是它自己覆盖自己，链式路径也是这个结果。
    index: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {}
    for step in steps:
        part = str(step.plan.sheet_part)
        table_key = str(step.binding.table_key)
        for write in step.plan.writes:
            index.setdefault(part, {}).setdefault(write.coord, {})[table_key] = (
                _write_payload(write)
            )

    conflicts: list[str] = []
    for part in sorted(index):
        for coord in sorted(index[part], key=coord_sort_key):
            writers = index[part][coord]
            if len(writers) < 2:
                continue
            payloads = {key: writers[key] for key in sorted(writers)}
            if len(set(payloads.values())) == 1:
                # 恒等覆盖：两方写的是同一份字节 ⇒ 顺序无关 ⇒ 可合并，不是冲突。
                continue
            # 差异字段按 `_WRITE_PAYLOAD_FIELDS` 的**声明序**列出（已是固定序，无需再排）。
            differing = [
                name
                for offset, name in enumerate(_WRITE_PAYLOAD_FIELDS)
                if len({payload[offset] for payload in payloads.values()}) > 1
            ]
            per_writer = "，".join(
                f"{key}[" + " ".join(
                    f"{name}={payloads[key][offset]}"
                    for offset, name in enumerate(_WRITE_PAYLOAD_FIELDS)
                    if name in differing
                ) + "]"
                for key in payloads
            )
            conflicts.append(
                f"{part}!{coord} 被 {list(payloads)} 写且 payload 不同"
                f"（差异字段 {differing}）：{per_writer}"
            )
    return tuple(conflicts)


def _payload_conflict_decline_reason(conflicts: Sequence[str]) -> str:
    """把完整碰撞清单拼成 `SinglePassDeclined.reason`。

    拆成独立函数只为让判据测试断言**生产那一份**字符串，而不是在测试里再抄一遍格式 ——
    抄一遍的话「原因里漏了一格」这种缺陷两边会一起错。
    """
    return (
        f"跨 binding 同坐标写入 payload 冲突 {len(conflicts)} 格"
        f"（完整清单，按 part+行列排序）：" + " ｜ ".join(conflicts)
    )


def materialize_projection_single_pass(
    *,
    substrate: Path,
    projection: Projection,
    output: Path,
    definitions: FrozenEntryDefinitions,
    bindings: Sequence[ExcelIdentityBinding],
    primary_table_key: str,
    substrate_role: SubstrateRole | str,
    substrate_kind: ArtifactKind | str,
    substrate_state: ArtifactState | str,
    capability: ExcelWriteCapability | None = None,
    limits: SyncLimits | None = None,
) -> SinglePassMaterializeOutcome:
    """多 binding 底稿的**单趟**物化：全部计划只解析一次 substrate，全部写入合成一趟。

    spec: oo-single-pass-materialize-and-room-leave · Requirement 1 / 2

    ═══ 它替掉了什么 ═══

    逐趟链式路径（`ExcelSyncAdapter` 的多 binding 循环）把上一趟的产物写成临时文件、当下一趟
    的输入，于是同一本工作簿被全量解析 `N × 2` 次（两个视图 `data_only=True/False` 是两个缓存
    键）。D4 营业收入实测 **39 binding / 79 次 `openpyxl.load_workbook`**，`adapter.materialize`
    42.8s 的绝大部分就在这里。单趟路径让 39 份计划共用同一份 substrate 字节 ⇒ 解析 1 次。

    ═══ 什么时候**不**适用（显式 decline，不硬撑）═══

    1. **openpyxl 全量重写策略**：它按文件改写（`apply_plan_openpyxl(substrate, ...)`），
       不吃字节流；而且它与结构性插行本就互斥。
    2. **任一计划需要结构性插行**（`plan.row_shift is not None`）：插行会位移**其它** sheet 的
       definedName 与引用侧公式（`merge_workbook_row_change_propagations` 合并的正是这些
       传播）。逐趟路径里后一趟是在「已位移」的字节上算计划的；单趟路径全部计划都算在
       原始字节上 ⇒ 位移一旦发生，后面的计划坐标就是陈旧的。这条不是保守，是正确性。
    3. **两个 binding 写同一格、且写入 payload 不同**（`kind`/`value`/`stable_field_key`/
       `mode`/`formula_text` 任一项不同）：那时结果取决于谁最后写，而链式顺序在单趟里无法
       复现。⚠️ 判据**不是**「坐标相交」—— 同格但 payload 逐字段相同是恒等覆盖（真库 D4 的
       `sheet14.xml!C24/E24/C38/E38` 共 4 格正是这种，源于静态表被同 sheet 两个 binding
       共同持有），按坐标相交 decline 会把需求 1.5 指名的 D4 整体挡在单趟之外。完整论证见
       :func:`_cross_binding_payload_conflicts`（design 附录 A.3 / A.6）。

    decline 时抛 :class:`SinglePassDeclined`，调用方回落逐趟路径 —— 慢但语义与改动前逐字相同。
    原因串是**确定的、完整的**（碰撞集合排序后全量入册）：真库要能统计回落比例与原因
    （需求 3.3），抽样报一格既不可复现也统计不出来。

    ═══ 写入顺序 ═══

    单趟内按 `bindings` 的**契约声明序**写（`steps` 与 `bindings` 同序，全程不经 `set`/`dict`
    的偶然序）。附录 A.4 实测「本契约下任何顺序都得同一份字节」，但声明序仍是唯一可复现的
    顺序 —— 依赖「顺序无所谓」去用偶然序，等于把一条会被契约变更打破的假设写进实现。

    返回**逐 binding** 的 outcome（顺序与 `bindings` 一致）：调用方要按 binding 取
    `row_shift` / `workbook_row_change` / `managed_field_count`，把它们压成一个会丢信息。
    """
    lim = limits or load_limits()
    assert_engine_entry_definitions(definitions)
    assert_substrate_usable(
        role=substrate_role, artifact_kind=substrate_kind, artifact_state=substrate_state
    )
    assert_output_outside_template_library(output)
    if not bindings:
        raise SinglePassDeclined("binding 集合为空")

    source_bytes = substrate.read_bytes()
    steps: list[MaterializePlanStep] = []
    for binding in bindings:
        step = _plan_materialize_step(
            substrate=substrate,
            projection=projection,
            definitions=definitions,
            binding=binding,
            substrate_role=substrate_role,
            substrate_kind=substrate_kind,
            substrate_state=substrate_state,
            source_bytes=source_bytes,
            capability=capability,
            intended_formulas=None,
            limits=lim,
            retain_identity_inventory=(binding.table_key == primary_table_key),
        )
        if step.strategy.strategy is ExcelWriteStrategy.openpyxl_roundtrip:
            raise SinglePassDeclined(
                f"binding {binding.table_key} 的写入策略是 openpyxl 全量重写（按文件改写）"
            )
        if step.plan.row_shift is not None:
            raise SinglePassDeclined(
                f"binding {binding.table_key} 需要结构性插行（row_shift）—— "
                "插行会位移其它 sheet 的 definedName/引用公式，后续计划必须在位移后的字节上算"
            )
        steps.append(step)

    # 🔴 同一个 sheet part 上有**多个**受管区是常态（D4-20 的 current_returns + provision
    #    都在 sheet26），同一**格**被两个 binding 各写一遍也是常态（静态表按 `managed_tables_of`
    #    的归属规则被同 sheet 的每个 binding 共同持有）。两者都能合并 —— 逐 step 在前一 step
    #    产出的字节上应用（`staged` 串联）就是正确顺序。真正不能合并的只有「同格 + 写入
    #    payload 不同」：那时结果取决于谁最后写，链式顺序在单趟里无法复现。判据的完整理由、
    #    为什么不是「坐标相交」、为什么必须排序报完整集合，见
    #    `_cross_binding_payload_conflicts` 的 docstring（design 附录 A.3 / A.6）。
    conflicts = _cross_binding_payload_conflicts(steps)
    if conflicts:
        raise SinglePassDeclined(_payload_conflict_decline_reason(conflicts))

    tmp = output.with_name(output.name + ".materializing")
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = source_bytes
    reports: list[ShiftReport | None] = []
    try:
        for step in steps:
            staged, report = _apply_step_to_bytes(
                source_bytes=staged, step=step, definitions=definitions
            )
            reports.append(report)
        tmp.write_bytes(staged)
        os.replace(tmp, output)
    finally:
        # 门失败 / 写失败 ⇒ 盘上不留半成品（Property 9 的文件侧；`output` 本就没被创建）。
        if tmp.exists():
            tmp.unlink()

    staged_bytes = output.read_bytes()
    primary_step = next(
        (step for step in steps if step.binding.table_key == primary_table_key), None
    )
    if primary_step is None:
        raise SinglePassDeclined(
            f"binding 集合里没有主表 {primary_table_key} —— 主 binding 的 identity 清册"
            "是下游观测器唯一认的那一份，缺它不能落盘"
        )
    # identity 清册只反读主 binding：observer/_frozen_anchors 只锚主表，sibling 的 digest 会
    # 写成另一张表的清册并与观测器重算结果漂移（D4 rematerialize 实测 169→253）。
    inventory = _staged_identity_inventory(
        staged_bytes=staged_bytes,
        output=output,
        definitions=definitions,
        binding=primary_step.binding,
        limits=lim,
    )
    primary = ExcelMaterializeOutcome(
        result=MaterializeResult(
            output_path=output,
            document_type=definitions.contract.document_type,
            artifact_sha256=hashlib.sha256(staged_bytes).hexdigest(),
            # structure_hash 是 workbook 级；单趟只有一份产物 ⇒ 只算一次（逐趟路径里非终趟
            # 那 34 次整簿指纹早已被证明是死算，见 ROI-2 注释）。
            structure_hash=normalized_structure_hash(staged_bytes),
            identity_inventory_sha256=inventory.inventory_digest,
            managed_field_count=sum(len(step.plan.field_writes) for step in steps),
            # 单趟路径在任一 binding 需要插行时就已 decline ⇒ 这三项恒为「无位移」。
            # 照实填 `plan` 里的值而不是写死 None：万一 decline 判据被改松，这里会立刻
            # 把真实位移声明带出去，而不是静默丢掉它。
            row_shift=primary_step.plan.row_shift,
            total_formula_rows=primary_step.plan.total_formula_rows,
            workbook_row_change=primary_step.plan.workbook_row_change,
        ),
        plan=primary_step.plan,
        strategy=primary_step.strategy,
        substrate_view=primary_step.substrate_view,
        staged_identity_inventory=inventory,
        intended_formulas=dict(sorted(primary_step.plan.preserved_formulas.items())),
        shift_report=next((r for r in reports if r is not None), None),
    )
    return SinglePassMaterializeOutcome(
        primary=primary,
        workbook_row_changes=tuple(
            step.plan.workbook_row_change
            for step in steps
            if step.plan.workbook_row_change is not None
        ),
        per_binding_field_counts={
            step.binding.table_key: len(step.plan.field_writes) for step in steps
        },
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
        cell_index = build_sheet_cell_index(xml)
        raw: dict[int, str] = {}
        shared = _shared_strings(entries)
        for row in region.row_span:
            view = cell_index.view(f"{region.uuid_column}{row}")
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
