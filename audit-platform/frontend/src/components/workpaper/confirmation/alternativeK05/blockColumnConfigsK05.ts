/**
 * blockColumnConfigsK05.ts — K0-5 其他应收款替代程序四区块列配置
 *
 * 4区块（对齐 requirements 2.5）：
 *   ① 期后收款检查
 *   ② 期末余额支持性证据
 *   ③ 本期发生额检查
 *   ④ 往来对账/协议证据
 *
 * 每区块左右视觉分组：记账凭证5列(fixed) | 检查证据N列(scrollable)
 */
import type { BlockType } from '../alternativeD05/alternativeD05Types'
import type { BlockColumnDef, BlockConfig } from '../alternativeD05/blockColumnConfigs'

/** 记账凭证通用5列（左侧 fixed） */
const VOUCHER_COLS: BlockColumnDef[] = [
  { field: 'voucher_date', label: '日期', width: 90, type: 'date', group: '记账凭证' },
  { field: 'voucher_no', label: '凭证编号', width: 100, type: 'text', group: '记账凭证' },
  { field: 'business_desc', label: '业务内容', width: 140, type: 'text', group: '记账凭证' },
  { field: 'counter_account', label: '对方科目', width: 100, type: 'text', group: '记账凭证' },
  { field: 'voucher_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '记账凭证', align: 'right' },
]

/**
 * ① 期后收款检查
 *
 * 🔴 源模板 `K0-5!A15:K16` 三段：记账凭证 / 银行回单{日期,**付款方**,金额} /
 *    支持性文件1{识别特征,信息1,信息2}。真源 `k0AlternativeSourceFidelity.K05_BLOCK1_SOURCE`。
 *
 * 两处对齐（spec k0-confirmation-source-alignment R7.1 / R7.2，2026-08-07）：
 *   - `receipt_payer` 的 label 由「收款方」改为「**付款方**」—— 其他应收款是期后**收回**
 *     款项，银行回单上的对方是付款方。K0-6（其他应付款、期后付出）那侧才是「收款方」，
 *     **两者不得统一**（统一即业务方向搞反，守卫有反向自检）。
 *   - 补齐源模板 `I15:K16` 的 `支持性文件1` 三列（改造前完全缺失 ⇒ 源模板要求的识别特征
 *     与两项信息无处录入）。
 *   - `receipt_date_no` 的**字段名保留**（既有项目已按此持久化），label 回归源模板「日期」；
 *     源模板银行回单只有「日期」单列，「/编号」是平台合成用词。
 *
 * 源外增强列 `post_receipt_ratio`（期后收回比例）保留 —— 它是平台对「期后收回比例」这一
 * 审计判断的量化位置，源模板无此列但红字 `O15` 授权「根据被审计单位具体情况修改」。
 */
const BLOCK1_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'receipt_date_no', label: '日期', width: 110, type: 'text', group: '银行回单' },
  { field: 'receipt_payer', label: '付款方', width: 120, type: 'text', group: '银行回单' },
  { field: 'receipt_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '银行回单', align: 'right' },
  { field: 'support1_feature', label: '识别特征', width: 120, type: 'text', group: '支持性文件1' },
  { field: 'support1_info1', label: '信息1', width: 110, type: 'text', group: '支持性文件1' },
  { field: 'support1_info2', label: '信息2', width: 110, type: 'text', group: '支持性文件1' },
  { field: 'post_receipt_ratio', label: '期后收回比例', width: 100, type: 'text', group: '汇总' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

/** ② 期末余额支持性证据 */
const BLOCK2_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'approval_date_no', label: '借款/垫款审批单日期编号', width: 150, type: 'text', group: '审批单' },
  { field: 'approval_proper', label: '是否恰当审批', width: 100, type: 'text', group: '审批单', align: 'center' },
  { field: 'agreement_no', label: '借据/协议编号', width: 120, type: 'text', group: '借据/协议' },
  { field: 'agreement_party', label: '对方单位', width: 120, type: 'text', group: '借据/协议' },
  { field: 'agreement_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '借据/协议', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

/** ③ 本期发生额检查 */
const BLOCK3_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'doc_date_no', label: '原始单据日期/编号', width: 130, type: 'text', group: '原始单据' },
  { field: 'doc_reason', label: '事由', width: 140, type: 'text', group: '原始单据' },
  { field: 'approval_voucher', label: '审批凭证', width: 100, type: 'text', group: '审批' },
  { field: 'approval_person', label: '审批人', width: 90, type: 'text', group: '审批' },
  { field: 'approval_amount', label: '金额', width: 110, type: 'number', render: 'amount', sumField: true, group: '审批', align: 'right' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

/** ④ 往来对账/协议证据 */
const BLOCK4_COLUMNS: BlockColumnDef[] = [
  { field: 'seq', label: '序号', width: 50, type: 'number', editable: false, fixed: true, align: 'center' },
  ...VOUCHER_COLS,
  { field: 'reconcile_date', label: '对账单日期', width: 100, type: 'date', group: '对账单' },
  { field: 'other_balance', label: '对方余额', width: 110, type: 'number', render: 'amount', sumField: true, group: '对账单', align: 'right' },
  { field: 'self_balance', label: '本方余额', width: 110, type: 'number', render: 'amount', sumField: true, group: '对账单', align: 'right' },
  { field: 'reconcile_diff', label: '对账差异', width: 110, type: 'formula', group: '对账单', align: 'right' },
  { field: 'agreement_no', label: '往来协议编号', width: 120, type: 'text', group: '往来协议' },
  { field: 'agreement_date', label: '签订日期', width: 100, type: 'date', group: '往来协议' },
  { field: 'ref_index', label: '索引号', width: 90, type: 'text' },
  { field: 'is_abnormal', label: '是否异常', width: 80, type: 'select', align: 'center' },
]

export const BLOCK_COLUMN_CONFIGS_K05: Record<string, BlockConfig> = {
  block1: {
    blockType: 'block1',
    title: '1、期后收款检查',
    columns: BLOCK1_COLUMNS,
    tips: ['①检查资产负债表日后收到的款项，与账面其他应收款核对'],
  },
  block2: {
    blockType: 'block2',
    title: '2、期末余额支持性证据',
    columns: BLOCK2_COLUMNS,
    tips: ['②检查借款/垫款审批单、借据/协议等支持性证据'],
  },
  block3: {
    blockType: 'block3',
    title: '3、本期发生额检查',
    columns: BLOCK3_COLUMNS,
    tips: ['③检查原始单据、审批凭证，验证发生额真实性'],
  },
  block4: {
    blockType: 'block4',
    title: '4、往来对账/协议证据',
    columns: BLOCK4_COLUMNS,
    tips: ['④与对方单位对账，核实往来余额差异；检查往来协议'],
  },
}

export function getBlockConfigK05(blockType: BlockType): BlockConfig {
  return BLOCK_COLUMN_CONFIGS_K05[blockType]
}

export function getSumFieldsK05(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_K05[blockType]
  if (!config) return []
  return config.columns.filter((c) => c.sumField).map((c) => c.field)
}

export function getGroupsK05(blockType: string): string[] {
  const config = BLOCK_COLUMN_CONFIGS_K05[blockType]
  if (!config) return []
  const groups = new Set<string>()
  for (const col of config.columns) {
    if (col.group) groups.add(col.group)
  }
  return [...groups]
}

export type { BlockType }
