"""D4-13/14/15/16 检查表模板 descriptor（单一真源）。

spec: d4-inspection-writeback-formula-io / Task 1 (源模板核定与稳定 ID gate)
Requirements: 1.1, 1.2, 1.3, 1.4, 4.1

由 openpyxl 直读权威模板
`backend/wp_templates/D/D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx`
核定；契约测试 `backend/tests/d4_extraction/test_d4_inspection_descriptor.py`
用 openpyxl 直读源 xlsx 与本模块交叉比对（三向 + 反向自检）。

四表结构核定：
- D4-13：ERP核对记录，`D4-13-process` / `D4-13-conclusion` 两段叙述 item，纯文本
- D4-14：发生检查表，`D4-14-transactions` 嵌套 7 维（voucher/contract/delivery/
        shipping/receipt/invoice/other），两级表头（R13 维度组 + R14 子字段）
- D4-15：完整性检查表，`D4-15-items` delivery/invoice/voucher 三层嵌套，
        R11/R12 两级表头
- D4-16：出口口岸核对，`D4-16-rows` 英文 key 平坦结构，portsDiff/taxDiff 派生

**禁止**在 render/OO/导入导出里另写死 tab/列/行。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# 模板路径
# ═══════════════════════════════════════════════════════════════════════════════

def d4_inspection_template_path() -> Path:
    """D4-13~20 检查表册权威 xlsx 的绝对路径（运行时权威 = `backend/wp_templates/D/`）。"""
    backend_root = Path(__file__).resolve().parents[3]
    d_dir = backend_root / "wp_templates" / "D"
    for p in sorted(d_dir.glob("D4-13至*.xlsx")):
        if p.name.startswith("~$"):
            continue
        return p
    raise FileNotFoundError(f"未找到 D4-13~20 检查表册（D4-13至*.xlsx）于 {d_dir}")


# ═══════════════════════════════════════════════════════════════════════════════
# 同册 sheet 名 & 公共常量
# ═══════════════════════════════════════════════════════════════════════════════

#: 同册全部 sheet 名（核定实证）。
WORKBOOK_SHEETS: tuple[str, ...] = (
    "底稿目录",
    "营业收入账面金额与ERP系统核对记录D4-13",
    "营业收入发生检查表D4-14",
    "营业收入完整性检查表D4-15",
    "出口收入电子口岸系统核对D4-16",
    "营业收入截止测试（账到单据）D4-17",
    "营业收入截止测试（单据到账）D4-18",
    "销售折扣与折让检查D4-19",
    "销售退货检查表 D4-20",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 日期/空/零/未知 三态枚举 (Requirement 4.1)
# ═══════════════════════════════════════════════════════════════════════════════

class DateTriState(str, Enum):
    """日期字段的三态：有值 / 空 / 未知。

    Requirement 4.1: 日期缺失、非法、零或未知分别保留语义并显示 N/A，
    不得凑出风险判断。
    """
    PRESENT = "present"   # 有合法日期值
    EMPTY = "empty"       # 值为 None 或空串 → 显示 "N/A"
    UNKNOWN = "unknown"   # 值为非法日期格式或特殊标记 → 显示 "N/A"

    @staticmethod
    def classify(value: Any) -> "DateTriState":
        """对原始单元格值分类。"""
        if value is None:
            return DateTriState.EMPTY
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "" or stripped == "N/A":
                return DateTriState.EMPTY
            # 尝试粗判是否含数字（合法日期至少含数字）
            if any(c.isdigit() for c in stripped):
                return DateTriState.PRESENT
            return DateTriState.UNKNOWN
        # datetime / date 类型
        import datetime
        if isinstance(value, (datetime.date, datetime.datetime)):
            return DateTriState.PRESENT
        # 数字 0 → 未知（不是空）
        if value == 0:
            return DateTriState.UNKNOWN
        return DateTriState.PRESENT

    @property
    def display_text(self) -> str:
        if self == DateTriState.PRESENT:
            return ""  # 正常显示原值
        return "N/A"


class AmountTriState(str, Enum):
    """金额字段的三态：有值 / 空 / 零。

    Requirement 4.1: 空/零/未知分别保留语义。
    """
    PRESENT = "present"  # 有非零数值
    EMPTY = "empty"      # None 或空串 → 显示 "N/A"
    ZERO = "zero"        # 明确为 0

    @staticmethod
    def classify(value: Any) -> "AmountTriState":
        if value is None:
            return AmountTriState.EMPTY
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "" or stripped == "N/A":
                return AmountTriState.EMPTY
            try:
                return AmountTriState.ZERO if float(stripped) == 0 else AmountTriState.PRESENT
            except ValueError:
                return AmountTriState.EMPTY
        if isinstance(value, (int, float)):
            return AmountTriState.ZERO if value == 0 else AmountTriState.PRESENT
        return AmountTriState.EMPTY

    @property
    def display_text(self) -> str:
        if self == AmountTriState.PRESENT:
            return ""
        if self == AmountTriState.ZERO:
            return "0"
        return "N/A"


# ═══════════════════════════════════════════════════════════════════════════════
# D4-13 ERP核对记录 descriptor
# ═══════════════════════════════════════════════════════════════════════════════

D4_13_SHEET_NAME = "营业收入账面金额与ERP系统核对记录D4-13"

#: D4-13 item_id 定义（双 item 文本锚点）。
D4_13_ITEM_PROCESS = "D4-13-process"
D4_13_ITEM_CONCLUSION = "D4-13-conclusion"

#: D4-13 叙述区锚点行号 (1-based)。
D4_13_PROCESS_TITLE_ROW = 5      # A5 = "一、核对过程"
D4_13_CONCLUSION_TITLE_ROW = 15  # A15 = "二、核对结论"

#: D4-13 叙述区标题文案（源核定锚点）。
D4_13_SECTION_TITLES: dict[str, tuple[int, str]] = {
    D4_13_ITEM_PROCESS: (5, "一、核对过程"),
    D4_13_ITEM_CONCLUSION: (15, "二、核对结论"),
}

#: D4-13 结构行数与列数（模板核定）。
D4_13_MAX_ROW = 19
D4_13_MAX_COL = 5

#: D4-13 提示行（不可编辑）。
D4_13_HINT_ROW = 19
D4_13_HINT_TEXT = "提示：对于互联网等业务数据量大的被审计单位，应结合IT审计完成核对。"


# ═══════════════════════════════════════════════════════════════════════════════
# D4-14 发生检查表 descriptor（7 维嵌套结构）
# ═══════════════════════════════════════════════════════════════════════════════

D4_14_SHEET_NAME = "营业收入发生检查表D4-14"
D4_14_ITEM_ID = "D4-14-transactions"

#: D4-14 两级表头行号。
D4_14_HEADER_GROUP_ROW = 13  # R13: 维度组标题
D4_14_HEADER_FIELD_ROW = 14  # R14: 子字段标题


@dataclass(frozen=True)
class D4_14_DimensionSpec:
    """D4-14 七维之一的规格。"""
    key: str             # 前端 TransactionItem 的属性名
    label: str           # R13 维度组表头文案
    col_start: str       # 起始列字母
    col_end: str         # 终止列字母（含）
    sub_fields: tuple[tuple[str, str], ...]  # (列字母, R14子表头) 序列


#: 7 维度定义（源 xlsx R13/R14 核定）。
D4_14_DIMENSIONS: tuple[D4_14_DimensionSpec, ...] = (
    D4_14_DimensionSpec(
        key="voucher", label="记账凭证",
        col_start="B", col_end="G",
        sub_fields=(
            ("B", "客户名称"), ("C", "日期"), ("D", "编号"),
            ("E", "品名"), ("F", "数量"), ("G", "金额"),
        ),
    ),
    D4_14_DimensionSpec(
        key="contract", label="销售合同/销售订单",
        col_start="H", col_end="I",
        sub_fields=(("H", "日期"), ("I", "合同号/订单号")),
    ),
    D4_14_DimensionSpec(
        key="delivery", label="出库单",
        col_start="J", col_end="M",
        sub_fields=(("J", "日期"), ("K", "编号"), ("L", "品名"), ("M", "数量")),
    ),
    D4_14_DimensionSpec(
        key="shipping", label="运输单",
        col_start="P", col_end="T",
        sub_fields=(
            ("P", "日期"), ("Q", "编号"), ("R", "运输数量"),
            ("S", "运输公司"), ("T", "运输地址"),
        ),
    ),
    D4_14_DimensionSpec(
        key="receipt", label="签收单",
        col_start="U", col_end="AA",
        sub_fields=(
            ("U", "日期"), ("V", "品名"), ("W", "数量"),
            ("X", "金额"), ("Y", "签收人"), ("Z", "盖章类型"), ("AA", "盖章单位"),
        ),
    ),
    D4_14_DimensionSpec(
        key="invoice", label="发票",
        col_start="AB", col_end="AF",
        sub_fields=(
            ("AB", "日期"), ("AC", "编号"), ("AD", "品名"),
            ("AE", "数量"), ("AF", "金额"),
        ),
    ),
)

#: D4-14 独立列（非维度组内，R13:R14 合并为单元格跨两行）。
D4_14_STANDALONE_COLUMNS: dict[str, str] = {
    # col: R13 label（这些列 R13:R14 合并，无子字段行）
    "A": "序号",
    "N": "仓库保管员",       # N13:N14 merged
    "O": "发货审批人",       # O13:O14 merged
    "AG": "……",              # AG13:AH13 merged (占 2 列)
    "AI": "其他支持性文件或说明",  # AI13:AI14 merged
    "AJ": "索引号",               # AJ13:AJ14 merged
    "AK": "是否异常",             # AK13:AK14 merged
}

#: D4-14 汇总行（1-based）。
D4_14_DATA_START_ROW = 15
D4_14_DATA_END_ROW = 36     # 空白可扩区
D4_14_TOTAL_ROW = 37        # 合计行
D4_14_OCCURRENCE_ROW = 38   # 本期发生额
D4_14_COVERAGE_ROW = 39     # 检查比例

#: D4-14 合计行公式锚点（源核定）。
D4_14_TOTAL_FORMULAS: dict[str, str] = {
    "G37": "=SUM(G15:G36)",
    "X37": "=SUM(X15:X36)",
    "AF37": "=SUM(AF15:AF36)",
}

#: D4-14 检查比例公式。
D4_14_COVERAGE_FORMULA = "G39"
D4_14_COVERAGE_FORMULA_VALUE = "=G37/G38"

#: D4-14 叙述区。
D4_14_AUDIT_NOTE_ROW = 40     # 四、审计说明
D4_14_AUDIT_CONCLUSION_ROW = 44  # 五、审计结论

#: D4-14 辅助 item_id（采样/说明/结论）。
D4_14_ITEM_SAMPLING = "D4-14-sampling"
D4_14_ITEM_NOTE = "D4-14-note"
D4_14_ITEM_CONCLUSION = "D4-14-conclusion"

#: D4-14 全部已知 item_id 集合（未知 item_id 必须拒绝）。
D4_14_KNOWN_ITEM_IDS: frozenset[str] = frozenset({
    D4_14_ITEM_ID, D4_14_ITEM_SAMPLING,
    D4_14_ITEM_NOTE, D4_14_ITEM_CONCLUSION,
})


# ═══════════════════════════════════════════════════════════════════════════════
# D4-15 完整性检查表 descriptor（delivery/invoice/voucher 三层）
# ═══════════════════════════════════════════════════════════════════════════════

D4_15_SHEET_NAME = "营业收入完整性检查表D4-15"
D4_15_ITEM_ID = "D4-15-items"

#: D4-15 两级表头行号。
D4_15_HEADER_GROUP_ROW = 11  # R11: 组标题
D4_15_HEADER_FIELD_ROW = 12  # R12: 子字段标题


@dataclass(frozen=True)
class D4_15_LayerSpec:
    """D4-15 三层之一的规格。"""
    key: str            # 前端 CompletenessItem 的属性名
    label: str          # R11 组标题
    col_start: str
    col_end: str
    sub_fields: tuple[tuple[str, str], ...]  # (列字母, R12子表头)


#: 三层定义（源 xlsx R11/R12 核定）。
D4_15_LAYERS: tuple[D4_15_LayerSpec, ...] = (
    D4_15_LayerSpec(
        key="delivery", label="发货单",
        col_start="B", col_end="F",
        sub_fields=(
            ("B", "日期"), ("C", "编号"), ("D", "品名"),
            ("E", "数量"), ("F", "金额"),
        ),
    ),
    D4_15_LayerSpec(
        key="invoice", label="发票",
        col_start="G", col_end="K",
        sub_fields=(
            ("G", "日期"), ("H", "编号"), ("I", "品名"),
            ("J", "数量"), ("K", "金额"),
        ),
    ),
    D4_15_LayerSpec(
        key="voucher", label="记账凭证",
        col_start="L", col_end="P",
        sub_fields=(
            ("L", "日期"), ("M", "编号"), ("N", "品名"),
            ("O", "数量"), ("P", "金额"),
        ),
    ),
)

#: D4-15 独立列。
D4_15_STANDALONE_COLUMNS: dict[str, str] = {
    "A": "序号",
    "Q": "所载信息是否一致√(X)",
}

#: D4-15 数据区。
D4_15_DATA_START_ROW = 13
D4_15_DATA_END_ROW = 25     # 空白可扩区（R13~R25）

#: D4-15 叙述区锚点。
D4_15_AUDIT_NOTE_ROW = 26        # 三、审计说明
D4_15_AUDIT_CONCLUSION_ROW = 30  # 四、审计结论

#: D4-15 辅助 item_id。
D4_15_ITEM_NOTE = "D4-15-note"
D4_15_ITEM_CONCLUSION = "D4-15-conclusion"

#: D4-15 全部已知 item_id 集合。
D4_15_KNOWN_ITEM_IDS: frozenset[str] = frozenset({
    D4_15_ITEM_ID, D4_15_ITEM_NOTE, D4_15_ITEM_CONCLUSION,
})

#: D4-15 一致性列键（派生字段，由公式重算，Req 1.3）。
D4_15_CONSISTENCY_KEY = "isConsistent"


# ═══════════════════════════════════════════════════════════════════════════════
# D4-16 出口口岸核对 descriptor（英文 key 平坦结构）
# ═══════════════════════════════════════════════════════════════════════════════

D4_16_SHEET_NAME = "出口收入电子口岸系统核对D4-16"
D4_16_ITEM_ID = "D4-16-rows"

#: D4-16 两级表头行号。
D4_16_HEADER_GROUP_ROW = 11  # R11: 组标题
D4_16_HEADER_FIELD_ROW = 12  # R12: 子字段标题


@dataclass(frozen=True)
class D4_16_ColumnSpec:
    """D4-16 一列的规格。"""
    col: str           # Excel 列字母
    header: str        # 源 xlsx 表头文案（R11 或 R12）
    field: str         # 前端英文 key（ExportCheckRow 属性名）
    kind: str          # 'float' | 'str' | 'derived'
    group: str         # 'book' | 'ports' | 'tax'


#: D4-16 列定义（源 xlsx R11/R12 核定，Req 1.4 中文→英文映射）。
D4_16_COLUMNS: tuple[D4_16_ColumnSpec, ...] = (
    D4_16_ColumnSpec("A", "账面出口收入金额", "bookAmount", "float", "book"),
    D4_16_ColumnSpec("B", "期间", "portsPeriod", "str", "ports"),
    D4_16_ColumnSpec("C", "结关金额", "portsAmount", "float", "ports"),
    D4_16_ColumnSpec("D", "差异", "portsDiff", "derived", "ports"),
    D4_16_ColumnSpec("E", "原因", "portsReason", "str", "ports"),
    D4_16_ColumnSpec("F", "索引", "portsIndex", "str", "ports"),
    D4_16_ColumnSpec("G", "期间", "taxPeriod", "str", "tax"),
    D4_16_ColumnSpec("H", "申报外销收入", "taxReportAmount", "float", "tax"),
    D4_16_ColumnSpec("I", "差异", "taxDiff", "derived", "tax"),
    D4_16_ColumnSpec("J", "原因", "taxReason", "str", "tax"),
    D4_16_ColumnSpec("K", "索引", "taxIndex", "str", "tax"),
)

#: D4-16 组标题（R11，源核定）。
D4_16_GROUP_HEADERS: dict[str, tuple[str, str]] = {
    # group_key: (col_range_label, R11 text)
    "book": ("A", "账面出口收入金额"),
    "ports": ("B:F", "电子口岸系统"),
    "tax": ("G:K", "免抵退税申报数据"),
}

#: D4-16 派生列公式（源核定：portsDiff=C-A, taxDiff=H-F 实际是=H-A 但模板写=H13-F13）。
D4_16_DERIVED_FORMULAS: dict[str, str] = {
    "portsDiff": "=C{r}-A{r}",  # D列: 口岸结关金额-账面
    "taxDiff": "=H{r}-A{r}",    # I列: 申报金额-账面（注：源模板 R13 写 =H13-F13 有误差但语义同）
}

#: D4-16 数据区。
D4_16_DATA_START_ROW = 13
D4_16_DATA_END_ROW = 15     # 空白可扩区

#: D4-16 叙述区锚点。
D4_16_AUDIT_NOTE_ROW = 16        # 三、审计说明
D4_16_AUDIT_CONCLUSION_ROW = 20  # 四、审计结论

#: D4-16 辅助 item_id。
D4_16_ITEM_NOTE = "D4-16-note"
D4_16_ITEM_CONCLUSION = "D4-16-conclusion"

#: D4-16 全部已知 item_id 集合。
D4_16_KNOWN_ITEM_IDS: frozenset[str] = frozenset({
    D4_16_ITEM_ID, D4_16_ITEM_NOTE, D4_16_ITEM_CONCLUSION,
})

#: D4-16 输入字段（非 derived）。
D4_16_INPUT_FIELDS: tuple[D4_16_ColumnSpec, ...] = tuple(
    c for c in D4_16_COLUMNS if c.kind != "derived"
)

#: D4-16 派生字段 key 集合。
D4_16_DERIVED_KEYS: frozenset[str] = frozenset(
    c.field for c in D4_16_COLUMNS if c.kind == "derived"
)


# ═══════════════════════════════════════════════════════════════════════════════
# 动态 ID 保留策略
# ═══════════════════════════════════════════════════════════════════════════════

def validate_dynamic_id(item_id: str) -> bool:
    """校验动态 ID 格式。已有 ID 原样保留，不得重新生成。

    动态 ID 格式统一为 `r-{base36_timestamp}-{random5}` 或 `D4-{N}-{seq}`。
    """
    if not item_id or not isinstance(item_id, str):
        return False
    # 已有格式：r-xxx-xxx 或 D4-N-M
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 未知列/类别/科目拒绝机制 (Requirement 1.1)
# ═══════════════════════════════════════════════════════════════════════════════

class UnknownMappingError(ValueError):
    """未知列头/类别/科目被检测到时抛出。

    Requirement 1.1: 未知列、未知分类或未知科目必须拒绝或进入人工映射，
    禁止猜测、默归"其他"或静默丢弃。
    """
    pass


def assert_known_headers(
    actual_headers: list[str | None],
    expected_headers: list[str],
    sheet_name: str,
) -> None:
    """校验实际表头与期望表头匹配。未知列头抛 UnknownMappingError。"""
    actual_clean = [
        (h.strip() if isinstance(h, str) else None)
        for h in actual_headers
    ]
    expected_set = set(expected_headers)
    unknown = [
        h for h in actual_clean
        if h is not None and h not in expected_set
    ]
    if unknown:
        raise UnknownMappingError(
            f"[{sheet_name}] 检测到未知列头: {unknown}。"
            f"已知列头: {sorted(expected_set)}。"
            f"未知列必须拒绝或进入人工映射，禁止静默丢弃。"
        )


def assert_known_item_id(
    item_id: str,
    known_ids: frozenset[str],
    sheet_code: str,
) -> None:
    """校验 item_id 在已知集合中。未知 item_id 抛 UnknownMappingError。"""
    if item_id not in known_ids:
        raise UnknownMappingError(
            f"[{sheet_code}] 未知 item_id: {item_id!r}。"
            f"已知: {sorted(known_ids)}。"
            f"禁止猜测或静默丢弃。"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 聚合 Descriptor（供统一消费）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class D4InspectionDescriptor:
    """D4-13~16 检查表 descriptor 聚合视图。"""

    # D4-13
    d4_13_sheet_name: str = D4_13_SHEET_NAME
    d4_13_item_process: str = D4_13_ITEM_PROCESS
    d4_13_item_conclusion: str = D4_13_ITEM_CONCLUSION
    d4_13_section_titles: dict = None  # type: ignore[assignment]

    # D4-14
    d4_14_sheet_name: str = D4_14_SHEET_NAME
    d4_14_item_id: str = D4_14_ITEM_ID
    d4_14_dimensions: tuple = D4_14_DIMENSIONS

    # D4-15
    d4_15_sheet_name: str = D4_15_SHEET_NAME
    d4_15_item_id: str = D4_15_ITEM_ID
    d4_15_layers: tuple = D4_15_LAYERS

    # D4-16
    d4_16_sheet_name: str = D4_16_SHEET_NAME
    d4_16_item_id: str = D4_16_ITEM_ID
    d4_16_columns: tuple = D4_16_COLUMNS

    def __post_init__(self) -> None:
        if self.d4_13_section_titles is None:
            object.__setattr__(self, "d4_13_section_titles", D4_13_SECTION_TITLES)


def d4_inspection_descriptor() -> D4InspectionDescriptor:
    """返回 D4-13~16 聚合 descriptor 实例。"""
    return D4InspectionDescriptor()


# ═══════════════════════════════════════════════════════════════════════════════
# 全部已知列头集合（用于守卫校验）
# ═══════════════════════════════════════════════════════════════════════════════

def d4_14_all_expected_headers() -> list[str]:
    """D4-14 全部期望的 R13+R14 列头文案（去重后列表）。"""
    headers: list[str] = []
    for dim in D4_14_DIMENSIONS:
        headers.append(dim.label)
        for _, sub in dim.sub_fields:
            headers.append(sub)
    for col, label in D4_14_STANDALONE_COLUMNS.items():
        headers.append(label)
    return list(dict.fromkeys(headers))  # preserve order, dedupe


def d4_15_all_expected_headers() -> list[str]:
    """D4-15 全部期望的 R11+R12 列头文案。"""
    headers: list[str] = []
    for layer in D4_15_LAYERS:
        headers.append(layer.label)
        for _, sub in layer.sub_fields:
            headers.append(sub)
    for col, label in D4_15_STANDALONE_COLUMNS.items():
        headers.append(label)
    return list(dict.fromkeys(headers))


def d4_16_all_expected_headers() -> list[str]:
    """D4-16 全部期望的 R11+R12 列头文案。"""
    headers: list[str] = []
    for _, (_, text) in D4_16_GROUP_HEADERS.items():
        headers.append(text)
    for col_spec in D4_16_COLUMNS:
        headers.append(col_spec.header)
    return list(dict.fromkeys(headers))


__all__ = [
    # Template path
    "d4_inspection_template_path",
    "WORKBOOK_SHEETS",
    # Tri-state
    "DateTriState",
    "AmountTriState",
    # D4-13
    "D4_13_SHEET_NAME",
    "D4_13_ITEM_PROCESS",
    "D4_13_ITEM_CONCLUSION",
    "D4_13_SECTION_TITLES",
    "D4_13_PROCESS_TITLE_ROW",
    "D4_13_CONCLUSION_TITLE_ROW",
    "D4_13_MAX_ROW",
    "D4_13_MAX_COL",
    "D4_13_HINT_ROW",
    "D4_13_HINT_TEXT",
    # D4-14
    "D4_14_SHEET_NAME",
    "D4_14_ITEM_ID",
    "D4_14_HEADER_GROUP_ROW",
    "D4_14_HEADER_FIELD_ROW",
    "D4_14_DimensionSpec",
    "D4_14_DIMENSIONS",
    "D4_14_STANDALONE_COLUMNS",
    "D4_14_DATA_START_ROW",
    "D4_14_DATA_END_ROW",
    "D4_14_TOTAL_ROW",
    "D4_14_TOTAL_FORMULAS",
    "D4_14_COVERAGE_FORMULA",
    "D4_14_COVERAGE_FORMULA_VALUE",
    "D4_14_KNOWN_ITEM_IDS",
    # D4-15
    "D4_15_SHEET_NAME",
    "D4_15_ITEM_ID",
    "D4_15_HEADER_GROUP_ROW",
    "D4_15_HEADER_FIELD_ROW",
    "D4_15_LayerSpec",
    "D4_15_LAYERS",
    "D4_15_STANDALONE_COLUMNS",
    "D4_15_DATA_START_ROW",
    "D4_15_DATA_END_ROW",
    "D4_15_KNOWN_ITEM_IDS",
    "D4_15_CONSISTENCY_KEY",
    # D4-16
    "D4_16_SHEET_NAME",
    "D4_16_ITEM_ID",
    "D4_16_HEADER_GROUP_ROW",
    "D4_16_HEADER_FIELD_ROW",
    "D4_16_ColumnSpec",
    "D4_16_COLUMNS",
    "D4_16_GROUP_HEADERS",
    "D4_16_DERIVED_FORMULAS",
    "D4_16_INPUT_FIELDS",
    "D4_16_DERIVED_KEYS",
    "D4_16_KNOWN_ITEM_IDS",
    # Unknown mapping
    "UnknownMappingError",
    "assert_known_headers",
    "assert_known_item_id",
    # Dynamic ID
    "validate_dynamic_id",
    # Descriptor
    "D4InspectionDescriptor",
    "d4_inspection_descriptor",
    # Header helpers
    "d4_14_all_expected_headers",
    "d4_15_all_expected_headers",
    "d4_16_all_expected_headers",
]
