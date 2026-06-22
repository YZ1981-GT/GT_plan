/**
 * blockColumnConfigs.ts — D0-5 四区块列配置
 *
 * 每个区块由 CheckBlock.vue 消费，按 blockType 读取对应列定义渲染。
 * 列结构严格对应致同 2025 修订版 D0-5 模板：
 *   block1: 期后结转（~16 列）
 *   block2: 期末余额证据（~16 列）
 *   block3: 本期收款（~14 列）
 *   block4: 本期出库证据（~30 列）
 *
 * 设计要点：
 * - group: 分组表头（5 色轮转着色）
 * - sumField: 标记哪些列参与合计行计算
 * - width: 列宽（px）
 * - editable: 是否可编辑（只读列如合计不可编辑）
 * - type: 'text' | 'number' | 'select' | 'date'
 */

import type { BlockType } from './alternativeD05Types'

export interface BlockColumnDef {
  /** 列字段 key（对应 CheckRow 的动态字段） */
  field: string
  /** 列标题 */
  label: string
  /** 列宽 px */
  width?: number
  /** 最小列宽 */
  minWidth?: number
  /** 数据类型 */
  type?: 'text' | 'number' | 'select' | 'date'
  /** 是否参与合计 */
  sumField?: boolean
  /** 分组表头名称（同 group 的列合并表头） */
  group?: string
  /** 是否可编辑（默认 true） */
  editable?: boolean
  /** 是否固定列 */
  fixed?: boolean
  /** 对齐方式 */
  align?: 'left' | 'center' | 'right'
  /** placeholder 提示 */
  placeholder?: string
  /** tooltip 提示（底部提示就近落位） */
  tooltip?: string
}

export interface BlockConfig {
  /** 区块类型 */
  blockType: BlockType
  /** 区块标题 */
  title: string
  /** 区块列定义 */
  columns: BlockColumnDef[]
  /** 底部提示文本（就近落位） */
  tips?: string[]
}

// ─── 区块① 合同负债检查-检查期后结转 ────────────────────────────────────────

const BLOCK1_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  // 记账凭证分组
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'detail_account', label: '明细科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'debit_amount', label: '借方金额', width: 110, type: 'number', sumField: true, group: '记账凭证', align: 'right' },
  // 客户验收单/出库单分组
  { field: 'delivery_date_no', label: '日期/编号', width: 110, type: 'text', group: '客户验收单/出库单' },
  { field: 'delivery_qty', label: '数量', width: 80, type: 'number', group: '客户验收单/出库单', align: 'right' },
  { field: 'delivery_sign', label: '签字、签章信息', width: 130, type: 'text', group: '客户验收单/出库单' },
  // 销售发票分组
  { field: 'invoice_receiver', label: '收票方名称', width: 120, type: 'text', group: '销售发票' },
  { field: 'invoice_amount', label: '金额', width: 110, type: 'number', sumField: true, group: '销售发票', align: 'right' },
  // 其他
  { field: 'other_evidence', label: '……', width: 100, type: 'text', group: '其他证据' },
  // 索引/异常
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

// ─── 区块② 合同负债检查-形成期末余额的支持性证据 ─────────────────────────────

const BLOCK2_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  // 记账凭证分组
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'detail_account', label: '明细科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'credit_amount', label: '贷方金额', width: 110, type: 'number', sumField: true, group: '记账凭证', align: 'right' },
  // 银行收款凭单分组
  { field: 'bank_payer', label: '付款方', width: 120, type: 'text', group: '银行收款凭单' },
  { field: 'bank_amount', label: '金额', width: 110, type: 'number', sumField: true, group: '银行收款凭单', align: 'right' },
  // 合同分组
  { field: 'contract_customer', label: '客户名称', width: 120, type: 'text', group: '合同' },
  { field: 'contract_amount', label: '合同金额', width: 110, type: 'number', group: '合同', align: 'right' },
  { field: 'prepay_ratio', label: '预收比例', width: 90, type: 'text', group: '合同', align: 'center' },
  // 其他
  { field: 'other_evidence', label: '……', width: 100, type: 'text', group: '其他证据' },
  // 索引/异常
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

// ─── 区块③ 销售检查-本期收款检查 ─────────────────────────────────────────────

const BLOCK3_COLUMNS: BlockColumnDef[] = [
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

// ─── 区块④ 销售检查-本期出库的支持性证据检查 ──────────────────────────────────

const BLOCK4_COLUMNS: BlockColumnDef[] = [
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
  // 索引/异常/说明
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
  { field: 'other_note', label: '其他支持性文件或说明', width: 160, type: 'text' },
]

// ─── 导出统一配置 ───────────────────────────────────────────────────────────

export const BLOCK_COLUMN_CONFIGS: Record<string, BlockConfig> = {
  block1: {
    blockType: 'block1',
    title: '1、合同负债检查-检查期后结转',
    columns: BLOCK1_COLUMNS,
    tips: ['①检查本期付款、期后收货或回收'],
  },
  block2: {
    blockType: 'block2',
    title: '2、合同负债检查-形成期末余额的合同、订单、银行收款凭单等支持性证据检查',
    columns: BLOCK2_COLUMNS,
    tips: [
      '②检查原始凭证：合同、订货单、发票或收据、银行回单、支票存根等',
    ],
  },
  block3: {
    blockType: 'block3',
    title: '3、销售检查-本期收款检查',
    columns: BLOCK3_COLUMNS,
  },
  block4: {
    blockType: 'block4',
    title: '4、销售检查-本期出库的合同、出库单、运输单、验收单等支持性证据检查',
    columns: BLOCK4_COLUMNS,
    tips: [
      '②检查原始凭证：合同、订货单、发票或收据、银行回单、支票存根等',
    ],
  },
}

/**
 * 获取区块中参与合计的字段列表
 */
export function getSumFields(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS[blockType]
  if (!config) return []
  return config.columns.filter((c) => c.sumField).map((c) => c.field)
}

/**
 * 获取区块分组表头（用于 5 色轮转着色）
 */
export function getGroups(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS[blockType]
  if (!config) return []
  const groups = new Set<string>()
  for (const col of config.columns) {
    if (col.group) groups.add(col.group)
  }
  return [...groups]
}
