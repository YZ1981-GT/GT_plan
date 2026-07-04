/**
 * blockColumnConfigsG06.ts — G0-6 投资循环替代程序四区块列配置
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

const BLOCK1_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'stmt_date', label: '对账单日期', width: 100, type: 'date', group: '检查证据' },
  { field: 'holding_variety', label: '持仓品种', width: 100, type: 'text', group: '检查证据' },
  { field: 'holding_qty', label: '数量', width: 80, type: 'number', group: '检查证据', align: 'right' },
  { field: 'market_value', label: '市值', width: 110, type: 'number', sumField: true, group: '检查证据', align: 'right' },
  { field: 'custody_confirm', label: '托管确认函', width: 110, type: 'text', group: '检查证据' },
  { field: 'custody_date', label: '确认日期', width: 90, type: 'date', group: '检查证据' },
  { field: 'csd_query_date', label: '中登查询日', width: 100, type: 'date', group: '检查证据' },
  { field: 'holding_consistent', label: '持仓一致性', width: 100, type: 'text', group: '检查证据', align: 'center' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
]

const BLOCK2_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'dividend_announce_date', label: '分红公告日期', width: 110, type: 'date', group: '检查证据' },
  { field: 'dividend_per_share', label: '每股股利', width: 90, type: 'number', group: '检查证据', align: 'right' },
  { field: 'dividend_receivable', label: '应收股利金额', width: 110, type: 'number', sumField: true, group: '检查证据', align: 'right' },
  { field: 'bank_receipt_date', label: '银行回单日期', width: 110, type: 'date', group: '检查证据' },
  { field: 'received_amount', label: '到账金额', width: 110, type: 'number', sumField: true, group: '检查证据', align: 'right' },
  { field: 'dividend_tax', label: '红利税扣缴', width: 100, type: 'number', group: '检查证据', align: 'right' },
  { field: 'net_received', label: '实收金额', width: 110, type: 'number', group: '检查证据', align: 'right' },
  { field: 'dividend_diff', label: '差异', width: 90, type: 'number', group: '检查证据', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
]

const BLOCK3_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'trade_confirm_date', label: '交易确认单日期', width: 120, type: 'date', group: '检查证据' },
  { field: 'sell_qty', label: '卖出数量', width: 90, type: 'number', group: '检查证据', align: 'right' },
  { field: 'trade_price', label: '成交价', width: 90, type: 'number', group: '检查证据', align: 'right' },
  { field: 'trade_amount', label: '成交金额', width: 110, type: 'number', sumField: true, group: '检查证据', align: 'right' },
  { field: 'original_cost', label: '原始成本', width: 110, type: 'number', group: '检查证据', align: 'right' },
  { field: 'disposal_gain', label: '处置损益', width: 110, type: 'number', group: '检查证据', align: 'right' },
  { field: 'fee', label: '手续费', width: 90, type: 'number', group: '检查证据', align: 'right' },
  { field: 'net_income', label: '净收入', width: 110, type: 'number', group: '检查证据', align: 'right' },
  { field: 'bank_received', label: '银行到账', width: 110, type: 'number', group: '检查证据', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
]

const BLOCK4_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'quote_source', label: '报价来源', width: 110, type: 'text', group: '检查证据' },
  { field: 'quote_date', label: '报价日期', width: 90, type: 'date', group: '检查证据' },
  { field: 'quote_value', label: '报价值', width: 110, type: 'number', group: '检查证据', align: 'right' },
  { field: 'valuation_model', label: '估值模型', width: 110, type: 'text', group: '检查证据' },
  { field: 'valuation_assumption', label: '估值假设', width: 110, type: 'text', group: '检查证据' },
  { field: 'fv_level', label: 'Level层级', width: 90, type: 'select', group: '检查证据', align: 'center' },
  { field: 'book_vs_quote_diff', label: '账面vs报价差异', width: 120, type: 'number', group: '检查证据', align: 'right' },
  { field: 'reasonableness', label: '合理性判断', width: 110, type: 'text', group: '检查证据' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
]

export const BLOCK_COLUMN_CONFIGS_G06: Record<string, BlockConfig> = {
  block1: {
    blockType: 'block1',
    title: '①持仓证明检查',
    columns: BLOCK1_COLUMNS,
  },
  block2: {
    blockType: 'block2',
    title: '②投资收益/股利收入证据',
    columns: BLOCK2_COLUMNS,
  },
  block3: {
    blockType: 'block3',
    title: '③投资处置收益证据',
    columns: BLOCK3_COLUMNS,
  },
  block4: {
    blockType: 'block4',
    title: '④公允价值佐证',
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
