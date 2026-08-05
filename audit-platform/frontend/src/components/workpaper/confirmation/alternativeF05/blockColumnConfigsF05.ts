/**
 * blockColumnConfigsF05.ts — F0-5 预付及采购替代程序四区块列配置
 * 列结构对齐 requirements.md Requirement 2.5（openpyxl F0-5 62×28）
 */
import type { BlockType } from '../alternativeD05/alternativeD05Types'
import type { BlockColumnDef, BlockConfig } from '../alternativeD05/blockColumnConfigs'

const BLOCK1_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'voucher_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '记账凭证', align: 'right' },
  { field: 'inbound_date_no', label: '日期/编号', width: 110, type: 'text', group: '入库单' },
  { field: 'inbound_product', label: '品名', width: 100, type: 'text', group: '入库单' },
  { field: 'inbound_unit', label: '单位', width: 70, type: 'text', group: '入库单', align: 'center' },
  { field: 'inbound_qty', label: '数量', width: 80, type: 'number', group: '入库单', align: 'right' },
  { field: 'invoice_date_no', label: '日期/编号', width: 110, type: 'text', group: '采购发票' },
  { field: 'invoice_counterparty', label: '对手方', width: 120, type: 'text', group: '采购发票' },
  { field: 'invoice_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '采购发票', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

const BLOCK2_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'voucher_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '记账凭证', align: 'right' },
  { field: 'approval_date_no', label: '日期/编号', width: 110, type: 'text', group: '付款审批单' },
  { field: 'approval_ok', label: '是否恰当审批', width: 100, type: 'text', group: '付款审批单', align: 'center' },
  { field: 'bank_date', label: '日期', width: 90, type: 'date', group: '银行回单' },
  { field: 'bank_payee', label: '收款方', width: 120, type: 'text', group: '银行回单' },
  { field: 'bank_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '银行回单', align: 'right' },
  { field: 'contract_vendor', label: '合同供应商', width: 120, type: 'text', group: '合同' },
  { field: 'contract_amount', label: '合同金额', width: 110, type: 'number', render: 'amount', group: '合同', align: 'right' },
  { field: 'prepay_ratio', label: '预付比例', width: 90, type: 'text', group: '合同', align: 'center' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

const BLOCK3_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'payment_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '记账凭证', align: 'right' },
  { field: 'approval_date_no', label: '日期/编号', width: 110, type: 'text', group: '付款审批单' },
  { field: 'approval_ok', label: '是否恰当审批', width: 100, type: 'text', group: '付款审批单', align: 'center' },
  { field: 'bank_date', label: '日期', width: 90, type: 'date', group: '银行回单' },
  { field: 'bank_payee', label: '收款方', width: 120, type: 'text', group: '银行回单' },
  { field: 'bank_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '银行回单', align: 'right' },
  { field: 'invoice_date_no', label: '日期/编号', width: 110, type: 'text', group: '采购发票' },
  { field: 'invoice_counterparty', label: '对手方', width: 120, type: 'text', group: '采购发票' },
  { field: 'invoice_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '采购发票', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

const BLOCK4_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'voucher_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '记账凭证', align: 'right' },
  { field: 'inbound_date_no', label: '日期/编号', width: 110, type: 'text', group: '入库单' },
  { field: 'inbound_product', label: '品名', width: 100, type: 'text', group: '入库单' },
  { field: 'inbound_unit', label: '单位', width: 70, type: 'text', group: '入库单', align: 'center' },
  { field: 'inbound_qty', label: '数量', width: 80, type: 'number', group: '入库单', align: 'right' },
  { field: 'contract_date_no', label: '日期/编号', width: 110, type: 'text', group: '合同' },
  { field: 'contract_vendor', label: '供应商', width: 120, type: 'text', group: '合同' },
  { field: 'contract_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '合同', align: 'right' },
  { field: 'invoice_date_no', label: '日期/编号', width: 110, type: 'text', group: '采购发票' },
  { field: 'invoice_counterparty', label: '对手方', width: 120, type: 'text', group: '采购发票' },
  { field: 'invoice_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '采购发票', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

export const BLOCK_COLUMN_CONFIGS_F05: Record<string, BlockConfig> = {
  block1: {
    blockType: 'block1',
    title: '1、预付账款期后收货检查',
    columns: BLOCK1_COLUMNS,
    tips: ['①检查期后收货与采购发票、入库单核对'],
  },
  block2: {
    blockType: 'block2',
    title: '2、预付账款期末余额支持性证据',
    columns: BLOCK2_COLUMNS,
    tips: ['②检查合同、付款审批、银行回单等支持性证据'],
  },
  block3: {
    blockType: 'block3',
    title: '3、本期付款检查',
    columns: BLOCK3_COLUMNS,
  },
  block4: {
    blockType: 'block4',
    title: '4、本期采购入库证据',
    columns: BLOCK4_COLUMNS,
  },
}

export function getSumFieldsF05(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_F05[blockType]
  if (!config) return []
  return config.columns.filter((c) => c.sumField).map((c) => c.field)
}

export function getGroupsF05(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_F05[blockType]
  if (!config) return []
  const groups = new Set<string>()
  for (const col of config.columns) {
    if (col.group) groups.add(col.group)
  }
  return [...groups]
}

export type { BlockType }
