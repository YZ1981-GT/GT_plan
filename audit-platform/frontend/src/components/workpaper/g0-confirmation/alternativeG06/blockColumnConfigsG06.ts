/**
 * blockColumnConfigsG06.ts — G0-6 投资循环替代程序四区块列配置
 *
 * confirmation-alternative-structure-alignment Task 4.1（G06 区块对齐源三区）：
 * 从"持仓/股利/处置/公允价值"四并列区块，重构为对齐源模板 G0-6 的三区 + 源外增强：
 *   block1 = ①初始投资协议检查
 *   block2 = ②本期发生额检查（借贷拆表，splitByDirection）
 *   block3 = ③期后出售/赎回检查
 *   block4 = ④源外增强（合并原持仓/股利/公允价值列，保留原字段名以承接迁移数据）
 *
 * 说明：
 * - block2 的借贷拆表在渲染层实现（同 K05/K06/L05），CheckRow.direction 区分借/贷，
 *   本配置只提供列定义；工厂 getBlockTotalByDirection 按 direction 分组小计。
 * - block4 保留旧持仓/股利/公允价值全部字段名（holding_variety/market_value/
 *   dividend_receivable/received_amount/net_received/dividend_diff/quote_source/
 *   valuation_model/fv_level/book_vs_quote_diff 等），使 migrateLegacyBlocks 迁移
 *   过来的旧数据不丢失且列可显示（数据零丢失红线）。
 */
import type { BlockType } from '../../confirmation/alternativeD05/alternativeD05Types'
import type { BlockColumnDef, BlockConfig } from '../../confirmation/alternativeD05/blockColumnConfigs'

const VOUCHER_COLS: BlockColumnDef[] = [
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'voucher_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '记账凭证', align: 'right' },
]

// ─── 区块① 检查初始投资协议、公司章程等（源 A9；列取自 A10:E10） ─────────────
// 🔴 源模板该区**无记账凭证列**（A10:E10 只有 5 列）→ g0 spec R7.2 要求删掉此前塞入的
//    VOUCHER_COLS 5 列并补「投资条款」。旧字段名（agreement_date/agreement_no/
//    voucher_* 等）不从数据里删，只是不再作为列渲染（见 G06_SOURCE_EXTRA）。

const BLOCK1_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  { field: 'investee_name', label: '被投资单位', width: 160, type: 'text', group: '初始投资协议' },
  { field: 'invest_ratio', label: '投资比例', width: 100, type: 'text', group: '初始投资协议', align: 'center' },
  { field: 'investment_amount', label: '投资金额', width: 130, type: 'number', render: 'amount', sumField: true, group: '初始投资协议', align: 'right' },
  { field: 'investment_term', label: '投资条款', width: 200, type: 'text', group: '初始投资协议' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
]

// ─── 区块② 检查本期发生额（源 A15；借方 A16 / 贷方 A24，两区共用同一两级表头）──
// 源两级表头（R17/R18 与 R25/R26 逐字相同）：
//   记账凭证{日期|凭证编号|业务内容|对方科目|金额} + 支持性文件1{识别特征|信息1|信息2}
//   + 支持性文件2{识别特征|信息1|信息2} + `……` + 索引号 + 是否异常
// 🔴 `……` 是「可继续加支持性文件组」的占位列头，永远收不到数据 → 不建列（g0 spec R7.3）。
// 🔴 此前把支持性文件 1/2 的六列压成一个 `support_doc` 单列，旧值由
//    `migrateSupportDoc` 迁到 `support1_feature`（数据零丢失红线）。

const BLOCK2_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'support1_feature', label: '识别特征', width: 120, type: 'text', group: '支持性文件1' },
  { field: 'support1_info1', label: '信息1', width: 110, type: 'text', group: '支持性文件1' },
  { field: 'support1_info2', label: '信息2', width: 110, type: 'text', group: '支持性文件1' },
  { field: 'support2_feature', label: '识别特征', width: 120, type: 'text', group: '支持性文件2' },
  { field: 'support2_info1', label: '信息1', width: 110, type: 'text', group: '支持性文件2' },
  { field: 'support2_info2', label: '信息2', width: 110, type: 'text', group: '支持性文件2' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

// ─── 区块③ 检查期后是否被出售或赎回（源 A32；两级表头 R33/R34） ───────────────
// 源两级表头：记账凭证 5 列 + 投资协议/交易确认单/交割单{日期/编号|被投资单位名称|金额}
//   + 银行回单{日期/编号|付款方|金额} + `……` + 索引号 + 是否异常
// 裁决门 C = 保留源外增强列 → 源三组证据列在前，既有自造列并列在后（逐列登记于
// G06_SOURCE_EXTRA），不删任何字段。

const BLOCK3_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  // 源：投资协议/交易确认单/交割单
  { field: 'deal_doc_no', label: '日期/编号', width: 120, type: 'text', group: '投资协议/交易确认单/交割单' },
  { field: 'deal_investee_name', label: '被投资单位名称', width: 150, type: 'text', group: '投资协议/交易确认单/交割单' },
  { field: 'deal_amount', label: '金额', width: 120, type: 'number', render: 'amount', sumField: true, group: '投资协议/交易确认单/交割单', align: 'right' },
  // 源：银行回单
  { field: 'bank_slip_no', label: '日期/编号', width: 120, type: 'text', group: '银行回单' },
  { field: 'bank_payer', label: '付款方', width: 140, type: 'text', group: '银行回单' },
  { field: 'bank_slip_amount', label: '金额', width: 120, type: 'number', render: 'amount', sumField: true, group: '银行回单', align: 'right' },
  // 源外增强（裁决门 C = 保留；逐列登记于 G06_SOURCE_EXTRA）
  { field: 'disposal_amount', label: '处置金额', width: 120, type: 'number', render: 'amount', sumField: true, group: '源外增强·处置明细', align: 'right' },
  { field: 'net_proceeds', label: '净收入', width: 110, type: 'number', render: 'amount', group: '源外增强·处置明细', align: 'right' },
  { field: 'trade_confirm_date', label: '交易确认单日期', width: 120, type: 'date', group: '源外增强·处置明细' },
  { field: 'sell_qty', label: '卖出/赎回数量', width: 110, type: 'number', group: '源外增强·处置明细', align: 'right' },
  { field: 'trade_price', label: '成交价', width: 90, type: 'number', group: '源外增强·处置明细', align: 'right' },
  { field: 'trade_amount', label: '成交金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '源外增强·处置明细', align: 'right' },
  { field: 'original_cost', label: '原始成本', width: 110, type: 'number', render: 'amount', group: '源外增强·处置明细', align: 'right' },
  { field: 'fee', label: '手续费', width: 90, type: 'number', render: 'amount', group: '源外增强·处置明细', align: 'right' },
  { field: 'disposal_gain', label: '处置损益', width: 110, type: 'number', render: 'amount', editable: false, group: '源外增强·处置明细', align: 'right' },
  { field: 'bank_received', label: '银行到账', width: 110, type: 'number', render: 'amount', group: '源外增强·处置明细', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

// ─── 区块④ 源外增强（公允价值/持仓/股利） ────────────────────────────────────
// 合并原持仓证明 + 股利收入 + 公允价值佐证三区列，保留原字段名承接迁移数据。

const BLOCK4_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  // 持仓证明
  { field: 'stmt_date', label: '对账单日期', width: 100, type: 'date', group: '持仓证明' },
  { field: 'holding_variety', label: '持仓品种', width: 100, type: 'text', group: '持仓证明' },
  { field: 'holding_qty', label: '数量', width: 80, type: 'number', group: '持仓证明', align: 'right' },
  { field: 'market_value', label: '市值', width: 110, type: 'number', render: 'amount', sumField: true, group: '持仓证明', align: 'right' },
  { field: 'custody_confirm', label: '托管确认函', width: 110, type: 'text', group: '持仓证明' },
  { field: 'custody_date', label: '确认日期', width: 90, type: 'date', group: '持仓证明' },
  { field: 'csd_query_date', label: '中登查询日', width: 100, type: 'date', group: '持仓证明' },
  { field: 'holding_consistent', label: '持仓一致性', width: 100, type: 'text', group: '持仓证明', align: 'center' },
  // 股利收入
  { field: 'dividend_announce_date', label: '分红公告日期', width: 110, type: 'date', group: '股利收入' },
  { field: 'dividend_per_share', label: '每股股利', width: 90, type: 'number', group: '股利收入', align: 'right' },
  { field: 'dividend_receivable', label: '应收股利金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '股利收入', align: 'right' },
  { field: 'bank_receipt_date', label: '银行回单日期', width: 110, type: 'date', group: '股利收入' },
  { field: 'received_amount', label: '到账金额', width: 110, type: 'number', render: 'amount', group: '股利收入', align: 'right' },
  { field: 'dividend_tax', label: '红利税扣缴', width: 100, type: 'number', render: 'amount', group: '股利收入', align: 'right' },
  { field: 'net_received', label: '实收金额', width: 110, type: 'number', render: 'amount', group: '股利收入', align: 'right' },
  { field: 'dividend_diff', label: '差异', width: 90, type: 'number', render: 'amount', editable: false, group: '股利收入', align: 'right' },
  // 公允价值佐证
  { field: 'quote_source', label: '报价来源', width: 110, type: 'text', group: '公允价值佐证' },
  { field: 'quote_date', label: '报价日期', width: 90, type: 'date', group: '公允价值佐证' },
  { field: 'quote_value', label: '报价值', width: 110, type: 'number', render: 'amount', group: '公允价值佐证', align: 'right' },
  { field: 'valuation_model', label: '估值模型', width: 110, type: 'text', group: '公允价值佐证' },
  { field: 'valuation_assumption', label: '估值假设', width: 110, type: 'text', group: '公允价值佐证' },
  { field: 'fv_level', label: 'Level层级', width: 90, type: 'select', group: '公允价值佐证', align: 'center' },
  { field: 'book_vs_quote_diff', label: '账面vs报价差异', width: 120, type: 'number', render: 'amount', group: '公允价值佐证', align: 'right' },
  { field: 'reasonableness', label: '合理性判断', width: 110, type: 'text', group: '公允价值佐证' },
  // 通用交易金额（源外增强汇总合计列，manifest 保留）
  { field: 'trade_amount', label: '交易金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '公允价值佐证', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

export const BLOCK_COLUMN_CONFIGS_G06: Record<string, BlockConfig> = {
  block1: {
    blockType: 'block1',
    title: '①初始投资协议检查',
    columns: BLOCK1_COLUMNS,
  },
  block2: {
    blockType: 'block2',
    title: '②本期发生额检查',
    columns: BLOCK2_COLUMNS,
  },
  block3: {
    blockType: 'block3',
    title: '③期后出售/赎回检查',
    columns: BLOCK3_COLUMNS,
  },
  block4: {
    blockType: 'block4',
    title: '④源外增强（公允价值/持仓/股利）',
    columns: BLOCK4_COLUMNS,
  },
}

// ─── 表头字段（源 A5 / D5） ──────────────────────────────────────────────────

/**
 * 「会计科目：」下拉候选（源 G0-6!A5 只有标签无枚举）。
 * 取值 = G 循环八个投资科目（与 `g0SummaryMatrix.G0_MATRIX_CATEGORIES` 同序），
 * `allow-create` 允许审计师输入源外科目。
 */
export const G0_ACCOUNT_SUBJECT_OPTIONS: readonly string[] = Object.freeze([
  '交易性金融资产',
  '长期股权投资',
  '债权投资',
  '长期应收款',
  '其他债权投资',
  '其他权益工具投资',
  '其他非流动金融资产',
  '交易性金融负债',
])

// ─── 源外增强登记（裁决门 C = 保留；g0 spec R7.5 数据零丢失红线） ─────────────

export interface G06SourceExtraEntry {
  field: string
  label: string
  block: 'block1' | 'block2' | 'block3' | 'block4'
  reason: string
}

/**
 * 源模板 G0-6 之外的全部字段，逐条登记理由。
 *
 * 🔴 登记 ≠ 渲染：`block1` 的三条是**旧结构遗留字段**（重构后不再作为列渲染，
 * 但数据保留、导入导出仍可承接）；其余是仍在渲染的增强列。
 */
export const G06_SOURCE_EXTRA: readonly G06SourceExtraEntry[] = Object.freeze([
  // block1 旧结构遗留（源 A10:E10 无记账凭证列，重构时移除渲染）
  //
  // 🔴 记账凭证 5 列必须**逐列**登记，不能只登记 voucher_date 一条 —— Property 17 是
  //    按 BEFORE_FIELDS 逐字段查落点，漏一个就等于「该字段既不渲染也无归属」= 数据会丢。
  { field: 'voucher_date', label: '日期', block: 'block1', reason: '旧实现给区块①塞了记账凭证 5 列；源模板 A10:E10 无此列。字段保留承接既有数据，不再渲染' },
  { field: 'voucher_no', label: '凭证编号', block: 'block1', reason: '同族记账凭证列；源模板 A10:E10 只有 被投资单位/投资比例/投资金额/投资条款/索引号 5 列，凭证信息属区块②的检查对象。字段保留承接既有数据，不再渲染' },
  { field: 'business_desc', label: '业务内容', block: 'block1', reason: '同族记账凭证列；初始投资协议检查看的是协议条款而非记账业务摘要，源模板无此列。字段保留承接既有数据，不再渲染' },
  { field: 'counter_account', label: '对方科目', block: 'block1', reason: '同族记账凭证列；源模板区块①不涉及分录对方科目（那是区块②本期发生额的检查要素）。字段保留承接既有数据，不再渲染' },
  { field: 'voucher_amount', label: '金额', block: 'block1', reason: '同族记账凭证列；区块①的金额口径是源模板 C10「投资金额」（investment_amount），凭证金额易与之混淆。字段保留承接既有数据，不再渲染' },
  { field: 'agreement_date', label: '协议日期', block: 'block1', reason: '旧实现增强列；源模板无。保留承接既有数据，不再渲染' },
  { field: 'agreement_no', label: '协议编号', block: 'block1', reason: '旧实现增强列；源模板 D10 只有「投资条款」文字列，编号便于与 G0-1 的替代程序索引号 alt_ref_index 交叉定位到具体协议。保留承接既有数据，不再渲染' },
  { field: 'is_abnormal', label: '是否异常', block: 'block1', reason: '源模板 A10:E10 五列中无「是否异常」（该列只出现在区块②的 N17/N25 与区块③的 N33）—— 初始投资协议检查的产出是投资条款本身而非异常标记。字段保留承接既有数据，不再渲染' },

  // block2 旧结构遗留（源 A17:N18 的检查要素里无这两列）
  { field: 'trade_amount', label: '成交金额', block: 'block2', reason: '旧实现自造列；源模板区块②记账凭证组的金额列是 E18「金额」（voucher_amount），成交金额属区块③期后出售/赎回的处置口径。字段保留承接既有数据，不再渲染' },
  { field: 'trade_type', label: '交易类型', block: 'block2', reason: '旧实现自造列；源模板区块②按借方/贷方双区结构区分方向（splitByDirection），无需独立交易类型列。字段保留承接既有数据，不再渲染' },

  // block3 源外增强（裁决门 C = 保留并并列渲染）
  { field: 'disposal_amount', label: '处置金额', block: 'block3', reason: '源模板只有三组证据的「金额」列，本列是处置口径合计，便于与 G11/G13 投资收益核对' },
  { field: 'net_proceeds', label: '净收入', block: 'block3', reason: '扣除手续费后的净流入，源模板无但审计常用' },
  { field: 'trade_confirm_date', label: '交易确认单日期', block: 'block3', reason: '源模板「日期/编号」合一列，本列拆出日期便于期后事项截止判断' },
  { field: 'sell_qty', label: '卖出/赎回数量', block: 'block3', reason: '证券类投资需数量×价格双维度验算，源模板无' },
  { field: 'trade_price', label: '成交价', block: 'block3', reason: '证券类投资的单位成交价，与卖出/赎回数量相乘验算成交金额；源模板三组证据只给合计金额列，无单价维度' },
  { field: 'trade_amount', label: '成交金额', block: 'block3', reason: '= 数量×成交价，参与处置损益公式' },
  { field: 'original_cost', label: '原始成本', block: 'block3', reason: '处置损益公式的减项（处置损益 = 成交金额 − 原始成本 − 手续费）；源模板无此列' },
  { field: 'fee', label: '手续费', block: 'block3', reason: '处置损益公式的减项，同时解释成交金额与银行到账之间的差额；源模板无此列' },
  { field: 'disposal_gain', label: '处置损益', block: 'block3', reason: '派生列 = 成交金额 − 原始成本 − 手续费（只读）' },
  { field: 'bank_received', label: '银行到账', block: 'block3', reason: '与「银行回单·金额」互为验算，源模板只有后者' },

  // block4 整区为源外增强（源模板无第四区）
  { field: 'stmt_date', label: '对账单日期', block: 'block4', reason: '第四区整体是源外增强（持仓证明/股利收入/公允价值佐证），承接旧四并列区块迁移数据' },
  { field: 'holding_variety', label: '持仓品种', block: 'block4', reason: '持仓证明按品种列示，与 G0-1 上区 E 列「账户/交易」的品种维度对齐，便于按品种核对回函覆盖率' },
  { field: 'holding_qty', label: '数量', block: 'block4', reason: '托管对账单的持仓数量，与市值、单位报价三者验算（数量×报价 ?= 市值）' },
  { field: 'market_value', label: '市值', block: 'block4', reason: '持仓证明的市值合计，参与 inbound 检查比例；与账面公允价值核对以验证计价认定' },
  { field: 'custody_confirm', label: '托管确认函', block: 'block4', reason: '托管机构出具的确认函编号，是未回函投资项目「存在性」认定的替代证据之一' },
  { field: 'custody_date', label: '确认日期', block: 'block4', reason: '托管确认函出具日期，用于判断该证据是否覆盖资产负债表日（跨期则需追加程序）' },
  { field: 'csd_query_date', label: '中登查询日', block: 'block4', reason: '中国证券登记结算公司持仓查询日期，证券类投资最独立的第三方存在性证据' },
  { field: 'holding_consistent', label: '持仓一致性', block: 'block4', reason: '持仓证明数量与账面数量的一致性判断结论，是本区块替代程序的直接产出列' },
  { field: 'dividend_announce_date', label: '分红公告日期', block: 'block4', reason: '分红公告日期，用于判断股利收入确认期间是否正确（权责发生制的截止测试）' },
  { field: 'dividend_per_share', label: '每股股利', block: 'block4', reason: '每股股利，与持股数相乘验算应收股利金额，防止股利收入漏记或多记' },
  { field: 'dividend_receivable', label: '应收股利金额', block: 'block4', reason: '同上；参与 payment 检查比例' },
  { field: 'bank_receipt_date', label: '银行回单日期', block: 'block4', reason: '银行回单日期，用于判断股利实际到账期间与应收确认期间是否匹配（跨期即为截止差异）' },
  { field: 'received_amount', label: '到账金额', block: 'block4', reason: '银行回单的到账金额，参与 payment 检查比例；与应收股利、红利税三者勾稽' },
  { field: 'dividend_tax', label: '红利税扣缴', block: 'block4', reason: '红利税扣缴额，是「应收股利 − 实收金额」差额的唯一合理解释项，缺它则差异无法定性' },
  { field: 'net_received', label: '实收金额', block: 'block4', reason: '扣税后实收金额，与应收股利、红利税构成勾稽闭环（应收 − 税 ?= 实收）' },
  { field: 'dividend_diff', label: '差异', block: 'block4', reason: '派生列 = 应收股利 − 实收金额 − 红利税（只读）' },
  { field: 'quote_source', label: '报价来源', block: 'block4', reason: '公允价值报价来源（交易所收盘价 / 第三方估值机构 / 内部模型），是 Level 层级判定的依据' },
  { field: 'quote_date', label: '报价日期', block: 'block4', reason: '报价日期，用于判断估值时点与资产负债表日是否一致（时点差异是回函差异的常见原因）' },
  { field: 'quote_value', label: '报价值', block: 'block4', reason: '第三方报价值，与账面公允价值核对以验证计价认定，差异超重要性水平需追查' },
  { field: 'valuation_model', label: '估值模型', block: 'block4', reason: '无活跃市场报价时（Level2/Level3）所采用的估值模型，是估值合理性判断的前提' },
  { field: 'valuation_assumption', label: '估值假设', block: 'block4', reason: '估值关键假设（折现率 / 增长率等），Level3 公允价值的审计重点与管理层偏向风险所在' },
  { field: 'fv_level', label: 'Level层级', block: 'block4', reason: '公允价值层级（Level1/2/3），直接决定所需佐证的充分性标准与披露要求' },
  { field: 'book_vs_quote_diff', label: '账面vs报价差异', block: 'block4', reason: '账面公允价值与第三方报价值的差异额，超重要性水平即需追查并考虑是否推 A13 错报' },
  { field: 'reasonableness', label: '合理性判断', block: 'block4', reason: '对公允价值计量合理性的判断结论，是本区块替代程序的直接产出列（对应源模板 A43 审计结论的分项支撑）' },
  { field: 'trade_amount', label: '交易金额', block: 'block4', reason: '第四区的合计列（manifest 保留）' },
])

/** 源模板三区的列字段（用于守卫区分「源列」与「源外增强」） */
export const G06_SOURCE_FIELDS: Readonly<Record<'block1' | 'block2' | 'block3', readonly string[]>> =
  Object.freeze({
    block1: Object.freeze(['investee_name', 'invest_ratio', 'investment_amount', 'investment_term', 'ref_index']),
    block2: Object.freeze([
      'voucher_date', 'voucher_no', 'business_desc', 'counter_account', 'voucher_amount',
      'support1_feature', 'support1_info1', 'support1_info2',
      'support2_feature', 'support2_info1', 'support2_info2',
      'ref_index', 'is_abnormal',
    ]),
    block3: Object.freeze([
      'voucher_date', 'voucher_no', 'business_desc', 'counter_account', 'voucher_amount',
      'deal_doc_no', 'deal_investee_name', 'deal_amount',
      'bank_slip_no', 'bank_payer', 'bank_slip_amount',
      'ref_index', 'is_abnormal',
    ]),
  })

export function getSumFieldsG06(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_G06[blockType]
  if (!config) return []
  return config.columns.filter((c) => c.sumField).map((c) => c.field)
}

export function getGroupsG06(blockType: BlockType): string[] {
  const config = BLOCK_COLUMN_CONFIGS_G06[blockType]
  if (!config) return []
  const groups = new Set<string>()
  for (const col of config.columns) {
    if (col.group) groups.add(col.group)
  }
  return Array.from(groups)
}
