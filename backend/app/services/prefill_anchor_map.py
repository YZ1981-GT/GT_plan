"""预设锚点 → `checklist_responses` 真实落点的**单一真源**（声明式）+ 机械取值层。

spec: .kiro/specs/prefill-wp-prev-resolution-repair/
      Task 5（映射真源骨架）/ Task 6（三种聚合纯函数 + 六态）/ Task 10（D 循环逐条对齐）

为什么需要这一层
----------------

``prefill_engine._resolve_wp_formula`` 的第三参（``WP('D2','明细表D2-2','期末合计')``
里的 ``期末合计``）是**中文业务锚点名**，而底稿录入值的真实存储键
``checklist_responses.item_id`` 是**英文 kebab 键**（``D2-detail-rows``）。
两侧零重叠（2026-08-07 逐个实证），是不同世代的独立命名空间 ⇒ 只能显式建映射。

映射本身是**会计判断**（哪个 item_id 的哪一列才是「期末合计」），故：

* 每条必须带 ``evidence``（实测列键 + 序列化位置），没有实证的条目不进表
* 取值层零会计判断、零启发式回退、**零公式复刻**

三条硬约束（全部来自实证，改动前必读）
------------------------------------

1. **键必须是三元组** —— 实测 34 对「同 ``(wp_code, cell_ref)`` 跨多个 sheet」
   （``F2 | 期末余额合计 | 12 sheets``），二元组键会把 12 张明细表塌成一条。
2. **只映射持久化列** —— ``useD1DetailCategory.serializeRows()`` 只写录入列，
   ``currentUnadjusted``/``currentAudited``/小计行都是前端 ``recalcRow``/``computed``
   产物、**不落库**；后端复刻那套公式就是双真源 ⇒ 派生列一律进 :data:`UNALIGNED`。
3. **六态可分辨** —— resolver 对外仍只返 ``Decimal | None``（零回归），但取值层返六态，
   否则「未编制」「未对齐」「确实为 0」混同，修完也不知道修没修好。

`期末合计` 的口径（Task 10 定案）
-------------------------------

审定表的取数格形如 ``未审数 = TB('1122','期末余额')`` + ``明细表D2-2期末合计 =
WP(...)``，两格并列供勾稽 ⇒ ``期末合计`` 一律指**期末未审合计**（未审口径），
不是审定后口径。故列键取 ``endBalance`` / ``endUnadjusted`` / ``currentUnadjusted``
这一族，**不取** ``*Audited``。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "AnchorAggregate",
    "AnchorSpec",
    "AnchorReadStatus",
    "AnchorReadResult",
    "ANCHOR_MAP",
    "UNALIGNED",
    "UNALIGNED_MAX",
    "OUT_OF_SCOPE_CYCLES",
    "OUT_OF_SCOPE_NON_WORKPAPER_TARGETS",
    "OUT_OF_SCOPE_CHANGES",
    "WP_IMPLEMENTATION_PATHS",
    "resolve_anchor",
    "parse_anchor_value",
    "read_anchor_value",
    "assert_map_consistent",
]


# ═══════════════════════════ 类型 ═══════════════════════════


class AnchorAggregate(str, Enum):
    """三种聚合语义（实测覆盖 D 循环全部可映射锚点）。"""

    #: 对 ``column`` 跨全部行求和（``期末合计`` 主体形态）
    SUM = "sum"
    #: ``column`` 本身是数值数组（``D4-2-rows.months[12]``）：行内求和后跨行求和
    SUM_LIST = "sum_list"
    #: 按 ``row_key`` 定位单行后取 ``column``（含小计行已落库的情形）
    ROW = "row"
    #: ``item_id`` 存的直接是标量（``column`` 传 ""）
    SCALAR = "scalar"


@dataclass(frozen=True)
class AnchorSpec:
    """一条锚点映射。

    :param item_id: ``checklist_responses.item_id``
    :param column: 行数组的列键；``aggregate=SCALAR`` 时传 ``""``
    :param aggregate: 聚合语义
    :param row_key: ``aggregate=ROW`` 时必填，其余形态必须为 ``None``
    :param exclude_row_keys: 求和时要排除的行（如已落库的小计行，防双算）
    :param evidence: 实证 —— 实测列键 + 它在哪个 composable 的序列化字段集里
    :param serializer_module: 该列所属前端序列化真源（Property 4 交叉锁死用）
    """

    item_id: str
    column: str
    aggregate: AnchorAggregate
    evidence: str
    serializer_module: str
    row_key: str | None = None
    exclude_row_keys: tuple[str, ...] = ()


class AnchorReadStatus(str, Enum):
    """六态 —— 把「未编制 / 未对齐 / 确实为 0」拆开。"""

    HIT = "hit"
    #: ``item_id`` 存在但值为空串 / 非数值 / 空数组
    EMPTY = "empty"
    #: 该 wp_code 在本项目无底稿（未生成，正常业务态）
    NO_WORKPAPER = "no_workpaper"
    #: 底稿存在但 ``item_id`` 未落库（明细表未编制）
    NO_ITEM = "no_item"
    #: 行数组里无该列键，或 ``ROW`` 形态下 ``row_key`` 未命中
    NO_COLUMN = "no_column"
    #: 三参组不在映射表（由调用方置入）
    UNALIGNED = "unaligned"


@dataclass(frozen=True)
class AnchorReadResult:
    status: AnchorReadStatus
    value: Decimal | None
    #: 溯源：item_id + 列键 + 聚合方式 + 参与行数（诊断脚本逐条打印）
    detail: str = ""


# ═══════════════════════════ 映射真源 ═══════════════════════════

_D1_BD = "audit-platform/frontend/src/components/workpaper/composables/useD1BadDebt.ts"
_D2_DETAIL = "audit-platform/frontend/src/components/workpaper/composables/useD2Detail.ts"
_D3_DETAIL = "audit-platform/frontend/src/components/workpaper/composables/useD3Detail.ts"
_D4_REV = "audit-platform/frontend/src/components/workpaper/composables/useD4RevenueDetail.ts"
_D4_OTHER = "audit-platform/frontend/src/components/workpaper/composables/useD4OtherRevenue.ts"
_D6_DETAIL = "audit-platform/frontend/src/components/workpaper/composables/useD6Detail.ts"
_D6_IMP = (
    "audit-platform/frontend/src/components/workpaper/composables/"
    "useD6ImpairmentDetail.ts"
)
_D7_DETAIL = "audit-platform/frontend/src/components/workpaper/composables/useD7Detail.ts"

#: ``(wp_code, sheet, cell_ref)`` → :class:`AnchorSpec`
#:
#: 🔴 键**必须**是三元组（Property 5）。sheet 不可省 —— 实测 ``D6 | 期末合计`` 就跨
#: ``明细表D6-2`` 与 ``合同资产减值准备明细表D6-3`` 两张 sheet，语义完全不同。
ANCHOR_MAP: dict[tuple[str, str, str], AnchorSpec] = {
    # ── D1 ──────────────────────────────────────────────────────────────────
    ("D1", "坏账准备明细表D1-4", "按票据种类小计-期末未审数"): AnchorSpec(
        item_id="D1-bd-notetype-rows",
        column="currentUnadjusted",
        aggregate=AnchorAggregate.SUM,
        evidence=(
            "item_id D1-bd-notetype-rows；currentUnadjusted 在 "
            "useD1BadDebt.serializeNoteTypeRows() 的 9 个持久化字段内（实测 keyed 集合），"
            "非派生列（派生的是 priorAudited/currentAudited）；源模板 D1-1!F12 引 D1-4!K23 小计"
        ),
        serializer_module=_D1_BD,
    ),
    # ── D2 ──────────────────────────────────────────────────────────────────
    ("D2", "明细表D2-2", "期末合计"): AnchorSpec(
        item_id="D2-detail-rows",
        column="endBalance",
        aggregate=AnchorAggregate.SUM,
        evidence=(
            "item_id D2-detail-rows；endBalance 在 useD2Detail.DetailRow 接口内且 "
            "serializeRows() 走 stripLegacyFlatKeys 整行保留（实测真实库 1260 行含该键、"
            "numeric_keys 命中）；期末未审口径与审定表 未审数=TB('1122','期末余额') 并列勾稽"
        ),
        serializer_module=_D2_DETAIL,
    ),
    # ── D3 ──────────────────────────────────────────────────────────────────
    ("D3", "预收账款明细表D3-2", "期末合计"): AnchorSpec(
        item_id="D3-det-rows",
        column="endUnadjusted",
        aggregate=AnchorAggregate.SUM,
        evidence=(
            "item_id D3-det-rows；endUnadjusted（Q列 =O+P）在 useD3Detail.DetailRow 内，"
            "其 persistRows() 注释明写 Keep computed fields in storage for crossSheet "
            "consumers 即整行落库；未审口径对齐审定表 未审数=TB('2203','期末余额')"
        ),
        serializer_module=_D3_DETAIL,
    ),
    # ── D4 ──────────────────────────────────────────────────────────────────
    ("D4", "主营业务收入明细表D4-2", "全年收入合计"): AnchorSpec(
        item_id="D4-2-rows",
        column="months",
        aggregate=AnchorAggregate.SUM_LIST,
        evidence=(
            "item_id D4-2-rows；months 是 12 元数值数组，在 useD4RevenueDetail."
            "StoredRevenueRow 的 7 个持久化字段内（实测真实库样本 months:[0]*12）；"
            "全年合计 = 行内 12 月求和后跨行求和，前端合计行是 computed 不落库"
        ),
        serializer_module=_D4_REV,
    ),
    ("D4", "其他业务收入明细表D4-3", "全年收入合计"): AnchorSpec(
        item_id="D4-3-rows",
        column="currentUnadjusted",
        aggregate=AnchorAggregate.SUM,
        evidence=(
            "item_id D4-3-rows；currentUnadjusted 在 useD4OtherRevenue.StoredOtherRow "
            "内且 persistRows() 直接 JSON.stringify(storedData)（实测真实库 4 行含该键）；"
            "currentAudited 是 calcAuditedWithAdj 派生故不取"
        ),
        serializer_module=_D4_OTHER,
    ),
    # ── D6 ──────────────────────────────────────────────────────────────────
    ("D6", "明细表D6-2", "期末合计"): AnchorSpec(
        item_id="D6-2-rows",
        column="endUnadjusted",
        aggregate=AnchorAggregate.SUM,
        evidence=(
            "item_id D6-2-rows；endUnadjusted（第17列 =10+15-16）在 useD6Detail.DetailRow "
            "内且 persistRows() 为 JSON.stringify(rows.value) 整行落库（实测 full_stringify）；"
            "未审口径对齐审定表 未审数=TB('1141','期末余额')"
        ),
        serializer_module=_D6_DETAIL,
    ),
    ("D6", "合同资产减值准备明细表D6-3", "期末合计"): AnchorSpec(
        item_id="D6-3-rows",
        column="endUnadjusted",
        aggregate=AnchorAggregate.SUM,
        evidence=(
            "item_id D6-3-rows；endUnadjusted 在 useD6ImpairmentDetail.ImpairmentDetailRow "
            "内，persistRows() 把 singleRows+groupRows 合并后整行 stringify（实测 "
            "full_stringify）；减值准备口径与 D6-1 区块二坏账小计对应"
        ),
        serializer_module=_D6_IMP,
    ),
    # ── D7 ──────────────────────────────────────────────────────────────────
    ("D7", "明细表D7-2", "期末合计"): AnchorSpec(
        item_id="D7-2-rows",
        column="endUnadjusted",
        aggregate=AnchorAggregate.SUM,
        evidence=(
            "item_id D7-2-rows；endUnadjusted 在 useD7Detail.DetailRow 内且 persistRows() "
            "为 JSON.stringify(rows.value)（实测真实库 1 行含 endUnadjusted 且在 "
            "numeric_keys 内）；未审口径对齐审定表 未审数=TB('2205','期末余额')"
        ),
        serializer_module=_D7_DETAIL,
    ),
}

#: 上限只许下调（Property 13）—— 防「对不齐就往清单里加一条」把清单当逃逸阀
UNALIGNED_MAX = 4

#: ``(wp_code, sheet, cell_ref)`` → 原因（≥20 字，带实证标记）
#:
#: 🔴 凡以「派生列」为原因的条目，理由中必须引用
#: ``OUT_OF_SCOPE_CHANGES['frontend_persist_derived_columns']``（Property 16），
#: 把「为什么对不齐」与「正解在哪」绑死，防清单变成无出口的黑洞。
UNALIGNED: dict[tuple[str, str, str], str] = {
    ("D1", "原值明细表（按类别）D1-2", "合计-期末未审数"): (
        "派生列：item_id D1-cat-rows 的 serializeRows() 只写 10 个录入字段"
        "（rowId/category/isFixed/prior*/current{Increase,Decrease,Aje,Rje}），"
        "currentUnadjusted 由 recalcRow() 加载时重算、「小计」是 computed subtotalRow，"
        "两者都不落库。后端复刻该公式即双真源。"
        "正解见 OUT_OF_SCOPE_CHANGES['frontend_persist_derived_columns']。"
    ),
    ("D1", "原值明细表（按类别）D1-2", "期末合计"): (
        "派生列：同上 item_id D1-cat-rows，目标列 currentAudited 亦由 recalcRow() 重算，"
        "不在 serializeRows() 的持久化字段集内（实测 keyed 集合无该键）。"
        "正解见 OUT_OF_SCOPE_CHANGES['frontend_persist_derived_columns']。"
    ),
    ("D2", "坏账准备明细表D2-3", "坏账准备期末余额"): (
        "行集分散在三个 item_id（D2-bd-individual-rows / D2-bd-aging-rows / "
        "D2-bd-customer-rows），且实测每个数组内**混有小计行**"
        "（rowId=fixed-aging / fixed-customer-type / fixed-individual，label 形如"
        "「按客户类型组合计提小计」）⇒ 跨三键求和会双算，只取小计行又需三键各取一行。"
        "需先裁决聚合口径（三键小计相加 vs 全量明细相加），属会计判断不由本 spec 猜。"
    ),
    ("D2", "审定表D2-1", "审定数"): (
        "二级链：目标是 D2-1 审定表自身的审定数，而该值由 useD2Adjudication 从 "
        "D2-detail-rows + D2-adj-total-aje/rje 现算（实测审定表持久化键只有 "
        "D2-adj-* 分项，无「审定数」标量）⇒ 取它等于在后端复刻审定表公式。"
        "正解见 OUT_OF_SCOPE_CHANGES['frontend_persist_derived_columns']。"
    ),
}

#: 范围外循环登记（Property 14）—— 其余 164 条 `WP()` 由各 per-cycle spec 按本机制补
OUT_OF_SCOPE_CYCLES: dict[str, str] = {
    "E": "E 循环 17 条 WP()，锚点集中在 E1 货币资金明细表；由 E 循环 per-cycle spec 按本机制补齐映射",
    "F": "F 循环 48 条 WP()（全库最多），F2 存货 11 张明细表共用「期末余额合计」跨 sheet；由 F 循环 spec 补",
    "G": "G 循环 42 条 WP()，涉 G1~G14 审定表与明细表联动；由 G 循环 per-cycle spec 补齐映射",
    "H": "H 循环 6 条 WP()，H1「审定数」跨 5 个 sheet 复用；由 h-cycle-extraction spec 按本机制补",
    "I": "I 循环 WP() 调用点为 0（其 34 条跨 sheet 复用集中在 PREV），无需对齐；PREV 整体范围外",
    "J": "J 循环 3 条 WP()，J1/J2 审定表与明细表联动；由 j-cycle per-cycle spec 补齐映射",
    "K": "K 循环 20 条 WP()，K2「期末余额合计」跨 2 sheet；由 k-cycle per-cycle spec 补齐映射",
    "L": "L 循环 WP() 调用点为 0（10 条全在 PREV）；PREV 跨年度整体属范围外，无需本 spec 处理",
    "M": "M 循环 3 条 WP()，M1 权益类审定表联动；由 m-cycle per-cycle spec 补齐映射",
    "N": "N 循环 16 条 WP()，N1~N5 递延所得税与税金审定表联动；由 n-cycle spec 补齐映射",
}

#: 🔴 **非底稿目标**登记（本轮复盘新增）——
#: `WP()` 的第一参并非总是 wp_code。实测预设里存在
#: ``WP('PL','利润表','净利润')`` / ``WP('PL','利润表','上期净利润')``
#: 两条（宿主均为 ``M6 明细表M6-2`` 的净利润格），其 target **`PL` 是利润表这张
#: 「报表」而不是底稿** ⇒ 经 ``wp_index`` JOIN + ``checklist_responses`` 的取值链
#: **结构上永远取不到**（`wp_index` 里没有 `PL` 这个 wp_code），而
#: :data:`OUT_OF_SCOPE_CYCLES` 按「循环字母」建键，也表达不了它。
#:
#: 这类目标的正解是**另一条 resolver**（读 `financial_report` / 复用 `report_config`
#: 的 `ROW()` 行码），与本 spec 的「底稿锚点」取值层是两套寻址空间，故显式登记为范围外。
#: 不登记的后果：它会永远静默落在 `resolve_anchor` 的「未对齐」分支里，
#: 与「D 循环某条漏登记」混在一起，无人知道它压根不该走这条链。
OUT_OF_SCOPE_NON_WORKPAPER_TARGETS: dict[str, str] = {
    "PL": (
        "利润表（报表，非底稿）。实测 2 条 WP('PL','利润表',{'净利润','上期净利润'})，"
        "宿主是 M6 明细表M6-2 的净利润格。`wp_index` 无 PL 这个 wp_code ⇒ 本 spec 的"
        "「wp_index JOIN + checklist_responses」取值链结构上取不到；正解是新增一条读"
        "financial_report / report_config ROW() 的 resolver，属另一 spec 的范围。"
    ),
}

#: 需另立 spec 的数据模型 / 前端变更（Property 16）
OUT_OF_SCOPE_CHANGES: dict[str, str] = {
    "prev_year_dimension": (
        "PREV() 跨年度定位需数据模型变更：working_paper 与 wp_index 实测**都没有 year 列**，"
        "底稿年度维度只在 project 层 ⇒ 需加 year 列或改走「同 company_code 的上年 project」"
        "反查。本 spec 只做 fail-closed（恒返 None），跨年度取数另立 spec。"
    ),
    "frontend_persist_derived_columns": (
        "让后端可取用派生值的正解 = 前端把派生列/小计另存为独立标量 item_id"
        "（如 D1-cat-subtotal-current-unadjusted），与既有 D1-ecl-total-* 三个标量同范式。"
        "在后端复刻 recalcRow()/computed 公式会产生双真源、且前端改公式后后端不会打红，"
        "故本 spec 宁缺勿造。属前端持久化契约变更，另立 spec。"
    ),
}

#: 两条 `WP` 实现路径的差异登记（Property 15）—— 防后来者"统一"时覆盖本 spec 的修复
WP_IMPLEMENTATION_PATHS: dict[str, str] = {
    "prefill_engine._resolve_wp_formula": (
        "三参 WP(wp_code, sheet, cell_ref)，经 ANCHOR_MAP 解析后读 "
        "checklist_responses(wp_id, item_id).remark，本 spec 修复的就是这一条"
    ),
    "formula_engine._handle_wp": (
        "读 ctx.wp_data（调用方预载的 dict），**第三参被静默忽略** ⇒ 与上者是两套独立"
        "寻址空间。二者语义不同，不得合并；改动任一侧都不会让另一侧打红，故此处显式登记。"
    ),
}


# ═══════════════════════════ import 期自检 ═══════════════════════════

#: `evidence` 必须命中的实证标记之一（Property 6）
_EVIDENCE_MARKERS = ("item_id", "serializeRows", "persistRows", "composable", "源模板")


def assert_map_consistent() -> None:
    """import 期自检（与平台既有 ``note_conversion_row_codes`` 同范式）。

    这些断言在 import 期跑，故任何往映射表里写非法条目的改动**立刻**在导入时炸，
    而不是等到某条公式求值时静默返 ``None``。
    """
    # 键集互斥（Property 3）
    overlap = set(ANCHOR_MAP) & set(UNALIGNED)
    if overlap:
        raise AssertionError(
            f"同一三参组不得既已对齐又在待对齐清单：{sorted(overlap)}"
        )

    # 键必须是三元组（Property 5）
    for table_name, table in (("ANCHOR_MAP", ANCHOR_MAP), ("UNALIGNED", UNALIGNED)):
        for key in table:
            if not (isinstance(key, tuple) and len(key) == 3):
                raise AssertionError(
                    f"{table_name} 的键必须是 (wp_code, sheet, cell_ref) 三元组，"
                    f"实际 {key!r}。实测 34 对 (wp_code, cell_ref) 跨 sheet 复用，"
                    "二元组键会让多张明细表塌成一条。"
                )

    for key, spec in ANCHOR_MAP.items():
        # evidence 质量闸（Property 6）
        if len(spec.evidence) < 20:
            raise AssertionError(f"{key} 的 evidence 少于 20 字：{spec.evidence!r}")
        if not any(m in spec.evidence for m in _EVIDENCE_MARKERS):
            raise AssertionError(
                f"{key} 的 evidence 未命中任一实证标记 {_EVIDENCE_MARKERS}，"
                "疑似「猜出来的」映射"
            )
        if not spec.serializer_module:
            raise AssertionError(f"{key} 缺 serializer_module（Property 4 交叉锁死依据）")

        # row_key 与 aggregate 的形态互斥
        if spec.aggregate is AnchorAggregate.ROW and not spec.row_key:
            raise AssertionError(f"{key} 声明 aggregate=ROW 但未给 row_key")
        if spec.aggregate is not AnchorAggregate.ROW and spec.row_key:
            raise AssertionError(
                f"{key} 的 aggregate={spec.aggregate.value} 不该带 row_key，"
                "非 ROW 形态的 row_key 会被静默忽略"
            )
        # SCALAR 不需要列键，其余形态必须有
        if spec.aggregate is AnchorAggregate.SCALAR and spec.column:
            raise AssertionError(f"{key} 是 SCALAR 形态，column 必须为空串")
        if spec.aggregate is not AnchorAggregate.SCALAR and not spec.column:
            raise AssertionError(f"{key} 的 aggregate={spec.aggregate.value} 必须给 column")

        # 不得越界对齐非 D 循环（Property 14）
        if not key[0].startswith("D"):
            raise AssertionError(
                f"{key} 的 wp_code 非 D 循环，本 spec 只交付 D 循环；"
                "其余循环见 OUT_OF_SCOPE_CYCLES"
            )

    # 待对齐清单规模上限（Property 13）
    if len(UNALIGNED) > UNALIGNED_MAX:
        raise AssertionError(
            f"UNALIGNED 有 {len(UNALIGNED)} 条，超过上限 {UNALIGNED_MAX}。"
            "上限只许下调 —— 对不齐就加一条会让清单变成逃逸阀。"
        )
    for key, reason in UNALIGNED.items():
        if len(reason) < 20:
            raise AssertionError(f"UNALIGNED[{key}] 的理由少于 20 字：{reason!r}")

    # 范围外登记（Property 16）：派生列原因必须指向正解
    for key, reason in UNALIGNED.items():
        if "派生列" in reason and "frontend_persist_derived_columns" not in reason:
            raise AssertionError(
                f"UNALIGNED[{key}] 以「派生列」为原因，但未引用 "
                "OUT_OF_SCOPE_CHANGES['frontend_persist_derived_columns']。"
                "「为什么对不齐」必须与「正解在哪」绑死。"
            )
    for required in ("prev_year_dimension", "frontend_persist_derived_columns"):
        if required not in OUT_OF_SCOPE_CHANGES:
            raise AssertionError(f"OUT_OF_SCOPE_CHANGES 缺 {required!r} 登记")
        if len(OUT_OF_SCOPE_CHANGES[required]) < 20:
            raise AssertionError(f"OUT_OF_SCOPE_CHANGES[{required!r}] 理由少于 20 字")


assert_map_consistent()


# ═══════════════════════════ 查表 ═══════════════════════════


def resolve_anchor(wp_code: str, sheet: str, cell_ref: str) -> AnchorSpec | None:
    """三参组 → :class:`AnchorSpec`；未对齐返 ``None``（调用方负责记 WARNING）。

    🔴 **不做任何模糊匹配** —— 不去空白、不忽略大小写、不按后缀。sheet 名的括号
    全半角差异是真实存在的（``附注披露信息(上市公司)`` vs ``（上市公司）``），
    归一化会让两个不同 sheet 撞进同一条映射。要支持新写法就显式再加一条。
    """
    return ANCHOR_MAP.get((wp_code, sheet, cell_ref))


# ═══════════════════════════ 两态解析（零 DB 纯函数）═══════════════════════════

#: `ROW` 形态匹配行标识时依次尝试的字段（实测覆盖 D 循环全部行数组形态）
_ROW_ID_FIELDS = ("rowId", "id", "label", "category", "noteType", "name")


def _to_decimal(raw: Any) -> Decimal | None:
    """数值化；非数值返 ``None``（**不当 0**，否则「脏数据」与「零」不可分）。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int, float)):
        try:
            return Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return None
    if isinstance(raw, str):
        text = raw.strip().replace(",", "")
        if not text:
            return None
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return None
    return None


def _row_identity(row: dict[str, Any]) -> tuple[str, ...]:
    """该行的全部候选标识值（按 :data:`_ROW_ID_FIELDS` 顺序）。"""
    out: list[str] = []
    for field in _ROW_ID_FIELDS:
        val = row.get(field)
        if isinstance(val, str) and val:
            out.append(val)
    return tuple(out)


def parse_anchor_value(raw: str | None, spec: AnchorSpec) -> AnchorReadResult:
    """把 ``checklist_responses.remark`` 按 ``spec`` 声明的聚合语义解析成金额。

    **零 DB 依赖** —— 便于单测与 PBT。

    六态映射：

    * ``raw`` 为 ``None`` ⇒ 调用方已判 ``NO_ITEM``，此处按 ``EMPTY`` 处理
    * 空串 / 非 JSON / 空数组 / 全部行非数值 ⇒ :attr:`AnchorReadStatus.EMPTY`
    * 列键不在任何行 / ``row_key`` 未命中 ⇒ :attr:`AnchorReadStatus.NO_COLUMN`
    * 其余 ⇒ :attr:`AnchorReadStatus.HIT`
    """
    if raw is None or not raw.strip():
        return AnchorReadResult(AnchorReadStatus.EMPTY, None, f"{spec.item_id} 值为空")

    if spec.aggregate is AnchorAggregate.SCALAR:
        val = _to_decimal(raw)
        if val is None:
            return AnchorReadResult(
                AnchorReadStatus.EMPTY,
                None,
                f"{spec.item_id} 标量值无法解析为数值：{raw[:40]!r}",
            )
        return AnchorReadResult(
            AnchorReadStatus.HIT, val, f"{spec.item_id}（标量）= {val}"
        )

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return AnchorReadResult(
            AnchorReadStatus.EMPTY,
            None,
            f"{spec.item_id} 不是合法 JSON（前 40 字：{raw[:40]!r}）",
        )

    rows = parsed if isinstance(parsed, list) else None
    if rows is None:
        # json-object 形态（如 D1-memo-rows）本 spec 不支持，映射表里不会出现
        return AnchorReadResult(
            AnchorReadStatus.EMPTY,
            None,
            f"{spec.item_id} 是 {type(parsed).__name__} 非行数组，本 spec 只支持标量与行数组",
        )
    if not rows:
        return AnchorReadResult(
            AnchorReadStatus.EMPTY, None, f"{spec.item_id} 行数组为空（未录入）"
        )

    dict_rows = [r for r in rows if isinstance(r, dict)]
    if not dict_rows:
        return AnchorReadResult(
            AnchorReadStatus.EMPTY, None, f"{spec.item_id} 行数组内无 dict 行"
        )

    # 列键存在性（先判，才能把「缺列」与「值为空」分开）
    if not any(spec.column in r for r in dict_rows):
        return AnchorReadResult(
            AnchorReadStatus.NO_COLUMN,
            None,
            f"{spec.item_id} 的 {len(dict_rows)} 行内均无列键 {spec.column!r}",
        )

    if spec.aggregate is AnchorAggregate.ROW:
        assert spec.row_key is not None  # assert_map_consistent 已保证
        for r in dict_rows:
            if spec.row_key in _row_identity(r):
                val = _to_decimal(r.get(spec.column))
                if val is None:
                    return AnchorReadResult(
                        AnchorReadStatus.EMPTY,
                        None,
                        f"{spec.item_id}[{spec.row_key}].{spec.column} 非数值",
                    )
                return AnchorReadResult(
                    AnchorReadStatus.HIT,
                    val,
                    f"{spec.item_id}[行 {spec.row_key}].{spec.column} = {val}",
                )
        # 🔴 未命中**不回退第一行** —— 静默取错行比取不到更坏
        return AnchorReadResult(
            AnchorReadStatus.NO_COLUMN,
            None,
            f"{spec.item_id} 的 {len(dict_rows)} 行内无行标识 {spec.row_key!r}"
            f"（候选字段 {_ROW_ID_FIELDS}），不回退第一行",
        )

    # SUM / SUM_LIST：跨行求和
    total = Decimal("0")
    counted = 0
    skipped_excluded = 0
    for r in dict_rows:
        if spec.exclude_row_keys and any(
            ident in spec.exclude_row_keys for ident in _row_identity(r)
        ):
            skipped_excluded += 1
            continue
        cell = r.get(spec.column)
        if spec.aggregate is AnchorAggregate.SUM_LIST:
            if not isinstance(cell, list):
                continue
            row_total = Decimal("0")
            row_counted = 0
            for item in cell:
                val = _to_decimal(item)
                if val is not None:
                    row_total += val
                    row_counted += 1
            if row_counted:
                total += row_total
                counted += 1
        else:
            val = _to_decimal(cell)
            if val is not None:
                total += val
                counted += 1

    if counted == 0:
        return AnchorReadResult(
            AnchorReadStatus.EMPTY,
            None,
            f"{spec.item_id}.{spec.column} 在 {len(dict_rows)} 行内无任何可解析数值"
            + (f"（另排除 {skipped_excluded} 个小计行）" if skipped_excluded else ""),
        )
    detail = (
        f"{spec.item_id}.{spec.column} [{spec.aggregate.value}] "
        f"{counted}/{len(dict_rows)} 行求和 = {total}"
    )
    if skipped_excluded:
        detail += f"（排除 {skipped_excluded} 个小计行防双算）"
    return AnchorReadResult(AnchorReadStatus.HIT, total, detail)


# ═══════════════════════════ 取值层（连库）═══════════════════════════


async def read_anchor_value(
    db: AsyncSession, project_id: UUID, wp_code: str, spec: AnchorSpec
) -> AnchorReadResult:
    """定位底稿 → 取 ``remark`` → :func:`parse_anchor_value`。

    **底稿定位经 ``wp_index`` JOIN**，不依赖 ``parsed_data['wp_code']``
    —— 该键实测仅 63/407 存在，依赖它对其余 344 个底稿必然取不到数。

    同一 wp_code 在项目下有多份记录时按 ``updated_at DESC, id ASC`` 取最近更新的一份
    （确定性选取；不带 ``ORDER BY`` 会依赖查询返回顺序，同一实参两次求值可能不同）。

    🔴 **``checklist_responses`` 的底稿外键列名是 ``wp_id``，不是 ``workpaper_id``**
    （实测全 10 列：id/project_id/**wp_id**/item_id/conclusion/remark/wp_ref/
    updated_by/created_at/updated_at，另有唯一约束 ``(wp_id, item_id)``）。
    本函数首版写 ``workpaper_id`` ⇒ PG 抛 ``UndefinedColumnError`` ⇒ 被
    ``_resolve_wp_formula`` 的 ``except Exception`` 吞成 WARNING ⇒ **整条修复恒返 None**，
    而单测（替身/纯函数）、``get_diagnostics``、源码守卫全绿。
    列名由 :class:`TestChecklistResponsesSchemaContract` 连库钉死。
    """
    row = (
        await db.execute(
            sa.text(
                """
                SELECT wp.id::text AS wp_id
                FROM working_paper wp
                JOIN wp_index wi ON wi.id = wp.wp_index_id
                WHERE wp.project_id = CAST(:pid AS uuid)
                  AND wp.is_deleted = false
                  AND wi.wp_code = :wp_code
                ORDER BY wp.updated_at DESC NULLS LAST, wp.id ASC
                LIMIT 1
                """
            ),
            {"pid": str(project_id), "wp_code": wp_code},
        )
    ).first()
    if row is None:
        return AnchorReadResult(
            AnchorReadStatus.NO_WORKPAPER,
            None,
            f"项目内无 wp_code={wp_code} 的底稿（未生成）",
        )
    wp_id = row[0]

    cell = (
        await db.execute(
            sa.text(
                """
                SELECT remark
                FROM checklist_responses
                WHERE wp_id = CAST(:wp_id AS uuid)
                  AND item_id = :item_id
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"wp_id": wp_id, "item_id": spec.item_id},
        )
    ).first()
    if cell is None:
        return AnchorReadResult(
            AnchorReadStatus.NO_ITEM,
            None,
            f"底稿 {wp_code} 存在但 item_id={spec.item_id} 未落库（未编制）",
        )

    return parse_anchor_value(cell[0], spec)
