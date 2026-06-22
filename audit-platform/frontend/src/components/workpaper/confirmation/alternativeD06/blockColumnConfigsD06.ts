/**
 * blockColumnConfigsD06.ts — D0-6 四区块列配置（应收及销售替代程序）
 *
 * 每个区块由 CheckBlock.vue（复用 D0-5）消费，按 blockType 读取对应列定义渲染。
 * 列结构严格对应致同 2025 修订版 D0-6 模板：
 *   block1: 应收账款检查-形成期末余额的支持性证据（~25 列）
 *   block2: 应收账款检查-检查期后回款（~14 列）
 *   block3: 销售检查-本期出库证据（~20 列）
 *   block4: 销售检查-本期收款（~11 列）
 *
 * 设计要点：
 * - group: 分组表头（5 色轮转着色）
 * - sumField: 标记哪些列参与合计行计算
 * - width: 列宽（px）
 * - editable: 是否可编辑（只读列如合计不可编辑）
 * - type: 'text' | 'number' | 'select' | 'date'
 */

import type { BlockType } from '../alternativeD05/alternativeD05Types'
import type { BlockColumnDef, BlockConfig } from '../alternativeD05/blockColumnConfigs'

// ─── 区块① 应收账款检查-形成期末余额的订单/合同、出库单、运输单、验收单等支持性证据检查 ───

const BLOCK1_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  // 记账凭证分组
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'detail_account', label: '明细科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'debit_amount', label: '借方金额', width: 110, type: 'number', sumField: true, group: '记账凭证', align: 'right' },
  // 销售合同/销售订单分组
  { field: 'contract_no', label: '合同号', width: 110, type: 'text', group: '销售合同/销售订单' },
  // 出库单分组
  { field: 'outbound_no', label: '编号', width: 90, type: 'text', group: '出库单' },
  { field: 'outbound_product', label: '品名', width: 100, type: 'text', group: '出库单' },
  { field: 'outbound_qty', label: '数量', width: 70, type: 'number', group: '出库单', align: 'right' },
  { field: 'outbound_keeper', label: '仓库保管员', width: 100, type: 'text', group: '出库单' },
  { field: 'outbound_shipper', label: '发货人', width: 90, type: 'text', group: '出库单' },
  // 运输单分组
  { field: 'transport_qty', label: '运输数量', width: 80, type: 'number', group: '运输单', align: 'right' },
  { field: 'transport_company', label: '运输公司', width: 110, type: 'text', group: '运输单' },
  { field: 'transport_address', label: '运输地址', width: 130, type: 'text', group: '运输单' },
  // 客户验收单/出库单（发货单）分组
  { field: 'acceptance_amount', label: '确认金额', width: 110, type: 'number', sumField: true, group: '客户验收单/出库单', align: 'right' },
  { field: 'acceptance_signer', label: '签收人', width: 90, type: 'text', group: '客户验收单/出库单' },
  { field: 'acceptance_stamp_type', label: '盖章类型', width: 90, type: 'text', group: '客户验收单/出库单' },
  { field: 'acceptance_stamp_entity', label: '盖章单位', width: 110, type: 'text', group: '客户验收单/出库单' },
  // 销售发票分组
  { field: 'invoice_receiver', label: '收票方名称', width: 120, type: 'text', group: '销售发票' },
  { field: 'invoice_amount', label: '金额', width: 110, type: 'number', sumField: true, group: '销售发票', align: 'right' },
  // 其他
  { field: 'other_evidence', label: '……', width: 100, type: 'text', group: '其他证据' },
  // 索引/异常
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

// ─── 区块② 应收账款检查-检查期后回款情况 ────────────────────────────────────

const BLOCK2_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  // 记账凭证分组
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'detail_account', label: '明细科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'credit_amount', label: '贷方金额', width: 110, type: 'number', sumField: true, group: '记账凭证', align: 'right' },
  // 银行回单分组
  { field: 'bank_summary', label: '摘要', width: 120, type: 'text', group: '银行回单' },
  { field: 'bank_payer', label: '付款方', width: 120, type: 'text', group: '银行回单' },
  { field: 'bank_amount', label: '金额', width: 110, type: 'number', sumField: true, group: '银行回单', align: 'right' },
  // 承兑汇票分组
  { field: 'bill_endorser', label: '前手名称', width: 110, type: 'text', group: '承兑汇票' },
  { field: 'bill_issuer', label: '出票人', width: 110, type: 'text', group: '承兑汇票' },
  // 其他
  { field: 'other_evidence', label: '……', width: 100, type: 'text', group: '其他证据' },
  // 索引/异常
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

// ─── 区块③ 销售检查-本期销售出库的合同、出库单、运输单、验收单等支持性证据检查 ──

const BLOCK3_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  // 记账凭证分组
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '编号', width: 90, type: 'text', group: '记账凭证' },
  { field: 'product_name', label: '品名', width: 100, type: 'text', group: '记账凭证' },
  { field: 'product_qty', label: '数量', width: 70, type: 'number', group: '记账凭证', align: 'right' },
  { field: 'product_amount', label: '金额', width: 110, type: 'number', sumField: true, group: '记账凭证', align: 'right' },
  // 销售订单/销售合同分组
  { field: 'order_contract_no', label: '订单号/合同号', width: 120, type: 'text', group: '销售订单/销售合同' },
  // 出库单分组
  { field: 'outbound_keeper', label: '仓库保管员', width: 100, type: 'text', group: '出库单' },
  { field: 'outbound_shipper', label: '发货人', width: 90, type: 'text', group: '出库单' },
  // 运输单分组
  { field: 'transport_qty', label: '运输数量', width: 80, type: 'number', group: '运输单', align: 'right' },
  { field: 'transport_company', label: '运输公司', width: 110, type: 'text', group: '运输单' },
  { field: 'transport_address', label: '运输地址', width: 130, type: 'text', group: '运输单' },
  // 签收单分组
  { field: 'receipt_signer', label: '签收人', width: 90, type: 'text', group: '签收单' },
  { field: 'receipt_stamp_type', label: '盖章类型', width: 90, type: 'text', group: '签收单' },
  { field: 'receipt_stamp_entity', label: '盖章单位', width: 110, type: 'text', group: '签收单' },
  // 其他
  { field: 'other_evidence', label: '……', width: 100, type: 'text', group: '其他证据' },
  // 异常/说明
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
  { field: 'other_note', label: '其他支持性文件或说明', width: 160, type: 'text' },
]

// ─── 区块④ 销售检查-本期收款检查 ─────────────────────────────────────────────

const BLOCK4_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  // 记账凭证分组
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'receipt_amount', label: '金额', width: 110, type: 'number', sumField: true, group: '记账凭证', align: 'right' },
  // 银行回单分组
  { field: 'bank_payer', label: '付款方', width: 120, type: 'text', group: '银行回单' },
  // 销售发票分组
  { field: 'invoice_date_no', label: '日期/编号', width: 110, type: 'text', group: '销售发票' },
  { field: 'invoice_counterparty', label: '对手方名称', width: 120, type: 'text', group: '销售发票' },
  // 其他
  { field: 'other_evidence', label: '……', width: 100, type: 'text', group: '其他证据' },
  // 索引/异常
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

// ─── 导出统一配置 ───────────────────────────────────────────────────────────

export const BLOCK_COLUMN_CONFIGS_D06: Record<string, BlockConfig> = {
  block1: {
    blockType: 'block1',
    title: '1、应收账款检查-形成期末余额的订单/合同、出库单、运输单、验收单等支持性证据检查',
    columns: BLOCK1_COLUMNS,
    tips: [
      '②检查原始凭证：合同、订货单、发票或收据、银行回单、支票存根等',
      '根据被审计单位情况考虑是否对期末余额的形成进行检查',
    ],
  },
  block2: {
    blockType: 'block2',
    title: '2、应收账款检查-检查期后回款情况',
    columns: BLOCK2_COLUMNS,
    tips: ['①检查本期收款、期后回款'],
  },
  block3: {
    blockType: 'block3',
    title: '3、销售检查-本期销售出库的合同、出库单、运输单、验收单等支持性证据检查',
    columns: BLOCK3_COLUMNS,
    tips: [
      '②检查原始凭证：合同、订货单、发票或收据、银行回单、支票存根等',
    ],
  },
  block4: {
    blockType: 'block4',
    title: '4、销售检查-本期收款检查',
    columns: BLOCK4_COLUMNS,
    tips: ['①检查本期收款、期后回款'],
  },
}

/**
 * 获取 D0-6 区块中参与合计的字段列表
 */
export function getSumFieldsD06(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_D06[blockType]
  if (!config) return []
  return config.columns.filter((c) => c.sumField).map((c) => c.field)
}

/**
 * 获取 D0-6 区块分组表头（用于 5 色轮转着色）
 */
export function getGroupsD06(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_D06[blockType]
  if (!config) return []
  const groups = new Set<string>()
  for (const col of config.columns) {
    if (col.group) groups.add(col.group)
  }
  return [...groups]
}
