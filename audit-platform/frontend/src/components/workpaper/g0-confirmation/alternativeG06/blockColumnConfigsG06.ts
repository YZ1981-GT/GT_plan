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
  { field: 'voucher_amount', label: '金额', width: 110, type: 'number', sumField: true, group: '记账凭证', align: 'right' },
]

// ─── 区块① 初始投资协议检查 ─────────────────────────────────────────────────

const BLOCK1_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'investment_amount', label: '投资金额', width: 120, type: 'number', sumField: true, group: '初始投资协议', align: 'right' },
  { field: 'agreement_date', label: '协议日期', width: 100, type: 'date', group: '初始投资协议' },
  { field: 'agreement_no', label: '协议编号', width: 120, type: 'text', group: '初始投资协议' },
  { field: 'investee_name', label: '被投资单位', width: 140, type: 'text', group: '初始投资协议' },
  { field: 'invest_ratio', label: '持股比例', width: 90, type: 'text', group: '初始投资协议', align: 'center' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

// ─── 区块② 本期发生额检查（借贷拆表） ────────────────────────────────────────

const BLOCK2_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'trade_amount', label: '交易金额', width: 120, type: 'number', sumField: true, group: '本期发生额', align: 'right' },
  { field: 'trade_type', label: '交易类型', width: 110, type: 'text', group: '本期发生额' },
  { field: 'support_doc', label: '支持性证据', width: 130, type: 'text', group: '本期发生额' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

// ─── 区块③ 期后出售/赎回检查 ─────────────────────────────────────────────────

const BLOCK3_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'disposal_amount', label: '处置金额', width: 120, type: 'number', sumField: true, group: '期后出售/赎回', align: 'right' },
  { field: 'net_proceeds', label: '净收入', width: 110, type: 'number', group: '期后出售/赎回', align: 'right' },
  { field: 'trade_confirm_date', label: '交易确认单日期', width: 120, type: 'date', group: '期后出售/赎回' },
  { field: 'sell_qty', label: '卖出/赎回数量', width: 110, type: 'number', group: '期后出售/赎回', align: 'right' },
  { field: 'trade_price', label: '成交价', width: 90, type: 'number', group: '期后出售/赎回', align: 'right' },
  { field: 'trade_amount', label: '成交金额', width: 110, type: 'number', sumField: true, group: '期后出售/赎回', align: 'right' },
  { field: 'original_cost', label: '原始成本', width: 110, type: 'number', group: '期后出售/赎回', align: 'right' },
  { field: 'fee', label: '手续费', width: 90, type: 'number', group: '期后出售/赎回', align: 'right' },
  { field: 'disposal_gain', label: '处置损益', width: 110, type: 'number', editable: false, group: '期后出售/赎回', align: 'right' },
  { field: 'bank_received', label: '银行到账', width: 110, type: 'number', group: '期后出售/赎回', align: 'right' },
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
  { field: 'market_value', label: '市值', width: 110, type: 'number', sumField: true, group: '持仓证明', align: 'right' },
  { field: 'custody_confirm', label: '托管确认函', width: 110, type: 'text', group: '持仓证明' },
  { field: 'custody_date', label: '确认日期', width: 90, type: 'date', group: '持仓证明' },
  { field: 'csd_query_date', label: '中登查询日', width: 100, type: 'date', group: '持仓证明' },
  { field: 'holding_consistent', label: '持仓一致性', width: 100, type: 'text', group: '持仓证明', align: 'center' },
  // 股利收入
  { field: 'dividend_announce_date', label: '分红公告日期', width: 110, type: 'date', group: '股利收入' },
  { field: 'dividend_per_share', label: '每股股利', width: 90, type: 'number', group: '股利收入', align: 'right' },
  { field: 'dividend_receivable', label: '应收股利金额', width: 110, type: 'number', sumField: true, group: '股利收入', align: 'right' },
  { field: 'bank_receipt_date', label: '银行回单日期', width: 110, type: 'date', group: '股利收入' },
  { field: 'received_amount', label: '到账金额', width: 110, type: 'number', group: '股利收入', align: 'right' },
  { field: 'dividend_tax', label: '红利税扣缴', width: 100, type: 'number', group: '股利收入', align: 'right' },
  { field: 'net_received', label: '实收金额', width: 110, type: 'number', group: '股利收入', align: 'right' },
  { field: 'dividend_diff', label: '差异', width: 90, type: 'number', editable: false, group: '股利收入', align: 'right' },
  // 公允价值佐证
  { field: 'quote_source', label: '报价来源', width: 110, type: 'text', group: '公允价值佐证' },
  { field: 'quote_date', label: '报价日期', width: 90, type: 'date', group: '公允价值佐证' },
  { field: 'quote_value', label: '报价值', width: 110, type: 'number', group: '公允价值佐证', align: 'right' },
  { field: 'valuation_model', label: '估值模型', width: 110, type: 'text', group: '公允价值佐证' },
  { field: 'valuation_assumption', label: '估值假设', width: 110, type: 'text', group: '公允价值佐证' },
  { field: 'fv_level', label: 'Level层级', width: 90, type: 'select', group: '公允价值佐证', align: 'center' },
  { field: 'book_vs_quote_diff', label: '账面vs报价差异', width: 120, type: 'number', group: '公允价值佐证', align: 'right' },
  { field: 'reasonableness', label: '合理性判断', width: 110, type: 'text', group: '公允价值佐证' },
  // 通用交易金额（源外增强汇总合计列，manifest 保留）
  { field: 'trade_amount', label: '交易金额', width: 110, type: 'number', sumField: true, group: '公允价值佐证', align: 'right' },
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
