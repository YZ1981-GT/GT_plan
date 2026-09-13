"""D4-17/18/19/20 导入导出字段规格（源核定单一真源）

本模块是 D4-17（截止·账到单据）、D4-18（截止·单据到账）、D4-19（销售折扣与折让）、
D4-20（销售退货，含 provision/current/post 三个明细 sheet）四类底稿的
**列头 ↔ 前端英文 key 映射 + 派生字段 + 方向语义**的唯一真源。

来源（源核定 gate，Task 1）：
    backend/wp_templates/D/D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx
    · sheet '营业收入截止测试（账到单据）D4-17'  R11/R12 两级表头
    · sheet '营业收入截止测试（单据到账）D4-18'  R11/R12（发货单在前）
    · sheet '销售折扣与折让检查D4-19'            R11/R12
    · sheet '销售退货检查表 D4-20'               R24(重新测算) / R32-33(本期) / R38-39(期后)

设计约束（Spec Requirements 1.1-1.5 / 2.3）：
    · 源 xlsx 是唯一列头/结构真源；未知列拒绝或人工映射，禁止默归"其他"。
    · 录入字段逐字段一致；派生字段（isCutoff/discountRate/shouldProvide/diff）
      **不信任文件值，导入时忽略、由公式重算**。
    · 截止方向：D4-17=凭证在前发货单在后；D4-18=发货单在前凭证在后。item_id 不变。
    · D4-20 主 sheet 无单一存储 → 死配置，须显式拒绝，不得 generic 静默写孤儿键。

字段规格结构 `FieldSpec`：
    header:  源 xlsx 列头（去空白后精确匹配，导入列头校验用）
    key:     前端 rows[].{key}（往返身份，逐字段一致的锚点）
    kind:    'str' | 'float' | 'derived'
             derived 字段导入时忽略文件值、导出时由公式重算填入
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    header: str
    key: str
    kind: str  # 'str' | 'float' | 'derived'


@dataclass(frozen=True)
class SheetIoSpec:
    sheet_code: str
    item_id: str
    fields: tuple[FieldSpec, ...]
    # 源 xlsx sheet 名（源核定锚点，守卫直读校验用）
    source_sheet_name: str

    @property
    def headers(self) -> list[str]:
        return [f.header for f in self.fields]

    @property
    def input_fields(self) -> tuple[FieldSpec, ...]:
        """录入字段（非 derived）：往返逐字段一致的判据集合。"""
        return tuple(f for f in self.fields if f.kind != "derived")

    @property
    def derived_keys(self) -> tuple[str, ...]:
        return tuple(f.key for f in self.fields if f.kind == "derived")


# ═══════════════════════════════════════════════════════════════════════════════
# D4-17 截止测试（账到单据）：记账凭证在前 → 发货单在后
# ═══════════════════════════════════════════════════════════════════════════════
D4_17_SPEC = SheetIoSpec(
    sheet_code="D4-17",
    item_id="D4-17-rows",
    source_sheet_name="营业收入截止测试（账到单据）D4-17",
    fields=(
        FieldSpec("凭证日期", "voucherDate", "str"),
        FieldSpec("凭证编号", "voucherNo", "str"),
        FieldSpec("凭证品名", "voucherProduct", "str"),
        FieldSpec("凭证数量", "voucherQty", "str"),
        FieldSpec("凭证金额", "voucherAmount", "float"),
        FieldSpec("发货单日期", "deliveryDate", "str"),
        FieldSpec("发货单编号", "deliveryNo", "str"),
        FieldSpec("发货单品名", "deliveryProduct", "str"),
        FieldSpec("发货单数量", "deliveryQty", "str"),
        FieldSpec("发货单金额", "deliveryAmount", "float"),
        FieldSpec("是否跨期", "isCutoff", "derived"),
        FieldSpec("备注", "remark", "str"),
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# D4-18 截止测试（单据到账）：发货单在前 → 记账凭证在后
# ═══════════════════════════════════════════════════════════════════════════════
D4_18_SPEC = SheetIoSpec(
    sheet_code="D4-18",
    item_id="D4-18-rows",
    source_sheet_name="营业收入截止测试（单据到账）D4-18",
    fields=(
        FieldSpec("发货单日期", "deliveryDate", "str"),
        FieldSpec("发货单编号", "deliveryNo", "str"),
        FieldSpec("发货单品名", "deliveryProduct", "str"),
        FieldSpec("发货单数量", "deliveryQty", "str"),
        FieldSpec("发货单金额", "deliveryAmount", "float"),
        FieldSpec("凭证日期", "voucherDate", "str"),
        FieldSpec("凭证编号", "voucherNo", "str"),
        FieldSpec("凭证品名", "voucherProduct", "str"),
        FieldSpec("凭证数量", "voucherQty", "str"),
        FieldSpec("凭证金额", "voucherAmount", "float"),
        FieldSpec("是否跨期", "isCutoff", "derived"),
        FieldSpec("备注", "remark", "str"),
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# D4-19 销售折扣与折让检查：16 字段（含 derived discountRate）
# ═══════════════════════════════════════════════════════════════════════════════
D4_19_SPEC = SheetIoSpec(
    sheet_code="D4-19",
    item_id="D4-19-rows",
    source_sheet_name="销售折扣与折让检查D4-19",
    fields=(
        FieldSpec("客户名称", "customerName", "str"),
        FieldSpec("折扣或折让类型", "discountType", "str"),
        FieldSpec("收入金额", "revenueAmount", "float"),
        FieldSpec("折扣或折让金额", "discountAmount", "float"),
        FieldSpec("折扣或折让比例", "discountRate", "derived"),
        FieldSpec("折扣或折让原因", "reason", "str"),
        FieldSpec("凭证日期", "voucherDate", "str"),
        FieldSpec("凭证编号", "voucherNo", "str"),
        FieldSpec("会计科目", "accountSubject", "str"),
        FieldSpec("明细科目", "detailSubject", "str"),
        FieldSpec("借方金额", "debitAmount", "float"),
        FieldSpec("贷方金额", "creditAmount", "float"),
        FieldSpec("审批日期", "approvalDate", "str"),
        FieldSpec("审批人", "approver", "str"),
        FieldSpec("备注", "remark", "str"),
    ),
)

# ═══════════════════════════════════════════════════════════════════════════════
# D4-20 重新测算产品退货金额（provision）：derived shouldProvide/diff
# ═══════════════════════════════════════════════════════════════════════════════
D4_20_PROVISION_SPEC = SheetIoSpec(
    sheet_code="D4-20-provision",
    item_id="D4-20-provision",
    source_sheet_name="销售退货检查表 D4-20",
    fields=(
        FieldSpec("产品名称", "productName", "str"),
        FieldSpec("计提基数", "base", "float"),
        FieldSpec("计提比例", "rate", "float"),
        FieldSpec("应计提金额", "shouldProvide", "derived"),
        FieldSpec("账面已计提金额", "alreadyProvided", "float"),
        FieldSpec("差异金额", "diff", "derived"),
        FieldSpec("差异原因", "diffReason", "str"),
    ),
)

# D4-20 本期/期后退货明细共用列结构（记账凭证 7 列 + 退货单 5 列 + 3 尾列）
_RETURN_DETAIL_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("凭证日期", "voucherDate", "str"),
    FieldSpec("凭证编号", "voucherNo", "str"),
    FieldSpec("业务内容", "bizContent", "str"),
    FieldSpec("科目名称", "subjectName", "str"),
    FieldSpec("二级明细", "detailSubject", "str"),
    FieldSpec("借方金额", "debitAmount", "float"),
    FieldSpec("贷方金额", "creditAmount", "float"),
    FieldSpec("客户名称", "customerName", "str"),
    FieldSpec("产品名称", "productName", "str"),
    FieldSpec("退货数量", "returnQty", "str"),
    FieldSpec("退货金额", "returnAmount", "float"),
    FieldSpec("退货原因", "returnReason", "str"),
    FieldSpec("是否涉及诉讼", "hasLitigation", "str"),
    FieldSpec("是否异常", "isAbnormal", "str"),
    FieldSpec("索引号", "indexRef", "str"),
)

# 前端存储 item_id = D4-20-current-returns / D4-20-post-returns（不是 -current/-post）
D4_20_CURRENT_SPEC = SheetIoSpec(
    sheet_code="D4-20-current",
    item_id="D4-20-current-returns",
    source_sheet_name="销售退货检查表 D4-20",
    fields=_RETURN_DETAIL_FIELDS,
)

D4_20_POST_SPEC = SheetIoSpec(
    sheet_code="D4-20-post",
    item_id="D4-20-post-returns",
    source_sheet_name="销售退货检查表 D4-20",
    fields=_RETURN_DETAIL_FIELDS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 注册表：sheet_code → SheetIoSpec
# ═══════════════════════════════════════════════════════════════════════════════
CUTOFF_RETURN_SPECS: dict[str, SheetIoSpec] = {
    s.sheet_code: s
    for s in (
        D4_17_SPEC,
        D4_18_SPEC,
        D4_19_SPEC,
        D4_20_PROVISION_SPEC,
        D4_20_CURRENT_SPEC,
        D4_20_POST_SPEC,
    )
}

# 主 D4-20 sheet 无单一存储：显式死配置拒绝（Requirement 1.4）
D4_20_MAIN_DEAD_SHEET = "D4-20"
D4_20_MAIN_DEAD_MESSAGE = (
    "D4-20 销售退货检查表为六区结构（政策/总况/评估/重新测算/本期退货/期后退货），"
    "无单一数据存储，无法整表导入导出。请分别使用："
    "「重新测算表」(D4-20-provision)、「本期退货明细」(D4-20-current)、"
    "「期后退货明细」(D4-20-post)。"
)


def get_io_spec(sheet_code: str) -> SheetIoSpec | None:
    """返回 sheet 的 IO 规格；未登记返回 None。"""
    return CUTOFF_RETURN_SPECS.get(sheet_code)
