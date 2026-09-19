/**
 * blockColumnConfigsK06.ts — K0-6 其他应付款替代程序四区块列配置
 *
 * 4区块：
 * ① 期后付款检查
 * ② 期末余额支持性证据
 * ③ 本期发生额检查
 * ④ 往来对账/协议证据
 *
 * Requirements: 3.5, 3.6, 3.7
 */
import type { BlockType } from '../alternativeD05/alternativeD05Types'
import type { BlockColumnDef, BlockConfig } from '../alternativeD05/blockColumnConfigs'

/** 记账凭证5列（左固定列，K0-5/K0-6共用） */
const VOUCHER_COLS: BlockColumnDef[] = [
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '记账凭证', align: 'right' },
]

/**
 * 区块①期后付款检查
 *
 * 🔴 源模板 `K0-6!A15:J16` 三段：记账凭证 / 付款审批单{日期/编号,是否经过恰当审批} /
 *    银行回单{日期,**收款方**,金额}。真源 `alternativeK05/k0AlternativeSourceFidelity.K06_BLOCK1_SOURCE`。
 *
 * label/group 对齐源模板（spec k0-confirmation-source-alignment R7.1，2026-08-07）：
 *   段头「付款审批」→「付款审批单」；叶子「付款审批单日期/编号」→「日期/编号」、
 *   「是否恰当审批」→「是否经过恰当审批」、「银行回单日期」→「日期」、「付款金额」→「金额」。
 *   **字段名一个不动**（既有项目已按此持久化，数据零丢失红线）。
 *
 * 🔴 `payee`「收款方」是**正确**的，SHALL NOT 改成「付款方」—— 其他应付款是期后**付出**
 *    款项，银行回单上的对方是收款方。K0-5（其他应收款、期后收回）那侧才是「付款方」。
 *    两侧统一即把业务方向搞反，守卫有反向自检。
 */
const BLOCK1_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'approvalDateNo', label: '日期/编号', width: 130, type: 'text', group: '付款审批单' },
  { field: 'isProperApproval', label: '是否经过恰当审批', width: 120, type: 'select', group: '付款审批单', align: 'center' },
  { field: 'receiptDate', label: '日期', width: 110, type: 'date', group: '银行回单' },
  { field: 'payee', label: '收款方', width: 120, type: 'text', group: '银行回单' },
  { field: 'paymentAmount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '银行回单', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

/**
 * 区块②期末余额支持性证据
 * 借款/收款审批单日期编号/是否恰当审批 | 借据/协议编号/对方单位/金额/索引号/是否异常
 */
const BLOCK2_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'loanApprovalDateNo', label: '收款审批单日期/编号', width: 140, type: 'text', group: '收款审批' },
  { field: 'loanIsProperApproval', label: '是否恰当审批', width: 100, type: 'select', group: '收款审批', align: 'center' },
  { field: 'agreementNo', label: '借据/协议编号', width: 120, type: 'text', group: '协议证据' },
  { field: 'counterparty', label: '对方单位', width: 120, type: 'text', group: '协议证据' },
  { field: 'agreementAmount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '协议证据', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

/**
 * 区块③本期发生额检查
 * 原始单据日期编号/事由 | 审批凭证/审批人/金额/索引号/是否异常
 */
const BLOCK3_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'docDateNo', label: '原始单据日期/编号', width: 140, type: 'text', group: '原始单据' },
  { field: 'docReason', label: '事由', width: 140, type: 'text', group: '原始单据' },
  { field: 'approvalVoucher', label: '审批凭证', width: 120, type: 'text', group: '审批' },
  { field: 'approver', label: '审批人', width: 100, type: 'text', group: '审批' },
  { field: 'approvalAmount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '审批', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

/**
 * 区块④往来对账/协议证据
 * 对账单日期/对方余额/本方余额/对账差异 | 往来协议编号/签订日期/索引号/是否异常
 */
const BLOCK4_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'reconcileDate', label: '对账单日期', width: 110, type: 'date', group: '往来对账' },
  { field: 'otherBalance', label: '对方余额', width: 110, type: 'number', render: 'amount', group: '往来对账', align: 'right' },
  { field: 'selfBalance', label: '本方余额', width: 110, type: 'number', render: 'amount', group: '往来对账', align: 'right' },
  { field: 'reconcileDiff', label: '对账差异', width: 110, type: 'number', render: 'amount', group: '往来对账', align: 'right', formula: true },
  { field: 'agreementNo', label: '往来协议编号', width: 120, type: 'text', group: '协议证据' },
  { field: 'signDate', label: '签订日期', width: 100, type: 'date', group: '协议证据' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

export const BLOCK_COLUMN_CONFIGS_K06: Record<string, BlockConfig> = {
  block1: {
    blockType: 'block1',
    title: '①期后付款检查',
    columns: BLOCK1_COLUMNS,
    tips: ['检查期后银行付款凭证，核实是否经过恰当审批，收款方与债务对象是否一致'],
  },
  block2: {
    blockType: 'block2',
    title: '②期末余额支持性证据',
    columns: BLOCK2_COLUMNS,
    tips: ['检查借款/收款审批手续和借据/协议等支持性证据'],
  },
  block3: {
    blockType: 'block3',
    title: '③本期发生额检查',
    columns: BLOCK3_COLUMNS,
    tips: ['检查本期新增其他应付款的原始单据及审批手续'],
  },
  block4: {
    blockType: 'block4',
    title: '④往来对账/协议证据',
    columns: BLOCK4_COLUMNS,
    tips: ['核对往来对账单，对账差异 = 本方余额 - 对方余额（虚线公式列）'],
  },
}

export function getBlockConfigK06(blockType: BlockType): BlockConfig {
  return BLOCK_COLUMN_CONFIGS_K06[blockType]
}

export function getSumFieldsK06(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_K06[blockType]
  if (!config) return []
  return config.columns.filter((c) => c.sumField).map((c) => c.field)
}

export function getGroupsK06(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_K06[blockType]
  if (!config) return []
  const groups = new Set<string>()
  for (const col of config.columns) {
    if (col.group) groups.add(col.group)
  }
  return [...groups]
}

export type { BlockType }
