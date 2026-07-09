/**
 * blockColumnConfigsH05.ts — H0-5 固定资产循环替代程序四区块列配置
 * Phase 0 对齐：替代程序H0-5 35×29（h0_structure_summary.json）
 */
import type { BlockType } from '../alternativeD05/alternativeD05Types'
import type { BlockColumnDef, BlockConfig } from '../alternativeD05/blockColumnConfigs'

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
  { field: 'accept_date_no', label: '验收单日期/编号', width: 120, type: 'text', group: '验收单' },
  { field: 'asset_name', label: '资产名称', width: 120, type: 'text', group: '验收单' },
  { field: 'asset_spec', label: '规格型号', width: 100, type: 'text', group: '验收单' },
  { field: 'asset_qty', label: '数量', width: 80, type: 'number', group: '验收单', align: 'right' },
  { field: 'title_cert_no', label: '权属证书编号', width: 120, type: 'text', group: '权属证据' },
  { field: 'title_owner', label: '权属人', width: 100, type: 'text', group: '权属证据' },
  { field: 'title_date', label: '取得日期', width: 100, type: 'date', group: '权属证据' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

const BLOCK2_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'contract_date_no', label: '合同日期/编号', width: 120, type: 'text', group: '采购合同' },
  { field: 'contract_vendor', label: '供应商', width: 120, type: 'text', group: '采购合同' },
  { field: 'contract_amount', label: '合同金额', width: 110, type: 'number', sumField: true, group: '采购合同', align: 'right' },
  { field: 'invoice_date_no', label: '发票日期/编号', width: 120, type: 'text', group: '采购发票' },
  { field: 'invoice_amount', label: '发票金额', width: 110, type: 'number', sumField: true, group: '采购发票', align: 'right' },
  { field: 'payment_date', label: '付款日期', width: 100, type: 'date', group: '付款凭证' },
  { field: 'payment_amount', label: '付款金额', width: 110, type: 'number', sumField: true, group: '付款凭证', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

const BLOCK3_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'req_date_no', label: '请购审批日期/编号', width: 130, type: 'text', group: '请购审批' },
  { field: 'req_approved', label: '是否恰当审批', width: 100, type: 'text', group: '请购审批', align: 'center' },
  { field: 'recv_date', label: '到货验收日期', width: 110, type: 'date', group: '到货验收' },
  { field: 'recv_asset_name', label: '资产名称', width: 120, type: 'text', group: '到货验收' },
  { field: 'recv_qty', label: '数量', width: 80, type: 'number', group: '到货验收', align: 'right' },
  { field: 'cap_date', label: '转固日期', width: 100, type: 'date', group: '转固' },
  { field: 'cap_cost', label: '原值', width: 110, type: 'number', sumField: true, group: '转固', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

const BLOCK4_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'mortgage_contract', label: '抵押合同编号', width: 120, type: 'text', group: '抵押担保' },
  { field: 'mortgage_holder', label: '抵押权人', width: 120, type: 'text', group: '抵押担保' },
  { field: 'mortgage_amount', label: '担保金额', width: 110, type: 'number', sumField: true, group: '抵押担保', align: 'right' },
  { field: 'lease_contract', label: '融资租赁合同编号', width: 130, type: 'text', group: '融资租赁' },
  { field: 'lease_lessor', label: '出租方', width: 120, type: 'text', group: '融资租赁' },
  { field: 'lease_term', label: '租赁期', width: 90, type: 'text', group: '融资租赁' },
  { field: 'warrant_no', label: '他项权证编号', width: 120, type: 'text', group: '权证' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

export const BLOCK_COLUMN_CONFIGS_H05: Record<string, BlockConfig> = {
  block1: {
    blockType: 'block1',
    title: '1、期后验收/权属证据检查',
    columns: BLOCK1_COLUMNS,
    tips: ['①检查期后验收单、权属证书与账面记录核对'],
  },
  block2: {
    blockType: 'block2',
    title: '2、期末余额支持性证据',
    columns: BLOCK2_COLUMNS,
    tips: ['②检查采购合同、发票、付款凭证等支持性证据'],
  },
  block3: {
    blockType: 'block3',
    title: '3、本期新增资产检查',
    columns: BLOCK3_COLUMNS,
    tips: ['③检查请购审批、到货验收、转固手续'],
  },
  block4: {
    blockType: 'block4',
    title: '4、抵押担保/融资租赁证据',
    columns: BLOCK4_COLUMNS,
    tips: ['④与 H1/L1/L3 抵质押信息交叉核对'],
  },
}

export function getBlockConfigH05(blockType: BlockType): BlockConfig {
  return BLOCK_COLUMN_CONFIGS_H05[blockType]
}

export function getSumFieldsH05(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_H05[blockType]
  if (!config) return []
  return config.columns.filter((c) => c.sumField).map((c) => c.field)
}

export function getGroupsH05(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_H05[blockType]
  if (!config) return []
  const groups = new Set<string>()
  for (const col of config.columns) {
    if (col.group) groups.add(col.group)
  }
  return [...groups]
}

export type { BlockType }
