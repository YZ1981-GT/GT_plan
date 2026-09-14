/**
 * sendListSpec.ts — E0 发函记录表声明式列 spec（前端唯一真源）
 *
 * 与后端 e0_send_list_source_manifest.json 交叉锁死（守卫 sendListSpec.spec.ts）。
 * 本文件逐字镜像 manifest 的 (cell, field, label, type, enum) 五元组，不抄第二份。
 *
 * @module e0-send-list-dedicated-components / Wave 3 Task 6
 */

export type SendListSheet = 'e03' | 'e04' | 'e05' | 'e06'

export interface SendListColumn {
  /** 源模板列字母，供守卫三向比对 */
  cell: string
  /** 业务 snake_case，存储键 */
  field: string
  /** 源模板逐字标签 */
  label: string
  /** 字段类型 */
  type: 'text' | 'enum' | 'date' | 'number'
  /** 枚举选项（type='enum' 时必填） */
  enum?: string[]
  /** 金额列标记（使用 WpAmountInput） */
  render?: 'amount'
  /** 建议列宽 px */
  width?: number
  /** 标注为平台增强（非源模板口径），如 account_type 枚举 */
  platformEnhanced?: true
  /** 源模板该列是 hidden 的，但平台显式化 */
  sourceHidden?: true
}

export interface SendListSpec {
  sheet: SendListSheet
  sheetName: string
  formatVersion: string
  componentType: string
  columns: SendListColumn[]
  /** E0-3/E0-4 = true（有「是否函证」列）；E0-5/E0-6 = false */
  hasConfirmFlag: boolean
  /** 仅 E0-3 支持 E1-3 上游取数 */
  supportsPrefill: boolean
  /** E0-3/E0-4 宽表需要列显隐设置 */
  columnToggle: boolean
}

// ─── E0-3 货币资金发函记录表 ──────────────────────────────────────────────────

const E03_COLUMNS: SendListColumn[] = [
  { cell: 'A', field: 'account_subject', label: '所属科目', type: 'text', width: 100 },
  { cell: 'B', field: 'index_no', label: '索引号', type: 'text', width: 80 },
  { cell: 'C', field: 'report_date', label: '报表截止日', type: 'date', width: 110 },
  { cell: 'D', field: 'bank_name', label: '开户银行', type: 'text', width: 160 },
  { cell: 'E', field: 'is_confirm', label: '是否函证', type: 'enum', enum: ['是', '否'], width: 80, sourceHidden: true },
  { cell: 'F', field: 'account_holder', label: '账户名称', type: 'text', width: 180 },
  { cell: 'G', field: 'bank_account', label: '银行账号', type: 'text', width: 180 },
  { cell: 'H', field: 'currency', label: '币种', type: 'text', width: 70 },
  { cell: 'I', field: 'interest_rate', label: '利率(%)', type: 'number', width: 80 },
  { cell: 'J', field: 'account_type', label: '账户类型', type: 'enum', enum: ['基本存款账户', '一般存款账户', '专用存款账户', '临时存款账户', '其他'], width: 120, platformEnhanced: true },
  { cell: 'K', field: 'balance_orig', label: '账户余额（原币）', type: 'number', render: 'amount', width: 140 },
  { cell: 'L', field: 'is_pooling', label: '是否属于资金归集（资金池或其他资金管理）账户', type: 'enum', enum: ['是', '否'], width: 100 },
  { cell: 'M', field: 'start_date', label: '起始日期', type: 'date', width: 110 },
  { cell: 'N', field: 'end_date', label: '终止日期', type: 'date', width: 110 },
  { cell: 'O', field: 'has_restriction', label: '是否存在冻结、担保或其他使用限制（如是，请注明）', type: 'enum', enum: ['是', '否'], width: 100 },
  { cell: 'P', field: 'remark', label: '备注', type: 'text', width: 200 },
]

// ─── E0-4 借款发函记录表 ──────────────────────────────────────────────────────

const E04_COLUMNS: SendListColumn[] = [
  { cell: 'A', field: 'account_subject', label: '所属科目', type: 'enum', enum: ['短期借款', '长期借款'], width: 100 },
  { cell: 'B', field: 'index_no', label: '索引号', type: 'text', width: 80 },
  { cell: 'C', field: 'report_date', label: '报表截止日', type: 'date', width: 110 },
  { cell: 'D', field: 'bank_name', label: '开户银行', type: 'text', width: 160 },
  { cell: 'E', field: 'is_confirm', label: '是否函证', type: 'enum', enum: ['是', '否'], width: 80, sourceHidden: true },
  { cell: 'F', field: 'borrower', label: '借款人名称', type: 'text', width: 160 },
  { cell: 'G', field: 'loan_account', label: '借款账号', type: 'text', width: 180 },
  { cell: 'H', field: 'currency', label: '币种', type: 'text', width: 70 },
  { cell: 'I', field: 'balance', label: '余额', type: 'number', render: 'amount', width: 140 },
  { cell: 'J', field: 'loan_date', label: '借款日期', type: 'date', width: 110 },
  { cell: 'K', field: 'maturity_date', label: '到期日期', type: 'date', width: 110 },
  { cell: 'L', field: 'interest_rate', label: '利率(%)', type: 'number', width: 80 },
  { cell: 'M', field: 'guarantor', label: '抵(质)押品/担保人', type: 'text', width: 160 },
  { cell: 'N', field: 'remark', label: '备注', type: 'text', width: 200 },
  { cell: 'O', field: 'loan_type', label: '借款类型', type: 'text', width: 100 },
  { cell: 'P', field: 'accrued_interest', label: '期末应付利息', type: 'number', render: 'amount', width: 120 },
]

// ─── E0-5 应付银行承兑汇票发函记录表 ─────────────────────────────────────────

const E05_COLUMNS: SendListColumn[] = [
  { cell: 'A', field: 'index_no', label: '索引号', type: 'text', width: 80 },
  { cell: 'B', field: 'report_date', label: '报表截止日', type: 'date', width: 110 },
  { cell: 'C', field: 'bank_name', label: '开户银行', type: 'text', width: 160 },
  { cell: 'D', field: 'bill_no', label: '银行承兑汇票号码', type: 'text', width: 180 },
  { cell: 'E', field: 'settlement_account', label: '结算账户账号', type: 'text', width: 160 },
  { cell: 'F', field: 'currency', label: '币种', type: 'text', width: 70 },
  { cell: 'G', field: 'face_amount', label: '票面金额', type: 'number', render: 'amount', width: 140 },
  { cell: 'H', field: 'issue_date', label: '出票日', type: 'date', width: 110 },
  { cell: 'I', field: 'maturity_date', label: '到期日', type: 'date', width: 110 },
  { cell: 'J', field: 'pledge', label: '抵（质）押品', type: 'text', width: 160 },
]

// ─── E0-6 理财产品发函记录表 ─────────────────────────────────────────────────

const E06_COLUMNS: SendListColumn[] = [
  { cell: 'A', field: 'index_no', label: '索引号', type: 'text', width: 80 },
  { cell: 'B', field: 'report_date', label: '报表截止日', type: 'date', width: 110 },
  { cell: 'C', field: 'bank_recipient', label: '开户行名称及收件人', type: 'text', width: 180 },
  { cell: 'D', field: 'product_name', label: '产品名称', type: 'text', width: 160 },
  { cell: 'E', field: 'product_type', label: '产品类型（封闭式/开放式）', type: 'enum', enum: ['封闭式', '开放式'], width: 120 },
  { cell: 'F', field: 'currency', label: '币种', type: 'text', width: 70 },
  { cell: 'G', field: 'holding_shares', label: '持有份额', type: 'number', width: 100 },
  { cell: 'H', field: 'net_value', label: '产品净值', type: 'number', render: 'amount', width: 140 },
  { cell: 'I', field: 'purchase_date', label: '购买日', type: 'date', width: 110 },
  { cell: 'J', field: 'maturity_date', label: '到期日', type: 'date', width: 110 },
  { cell: 'K', field: 'has_restriction', label: '是否被用于担保或存在其他使用限制', type: 'enum', enum: ['是', '否'], width: 100 },
]

// ─── 汇总导出 ────────────────────────────────────────────────────────────────

export const SEND_LIST_SPECS: Record<SendListSheet, SendListSpec> = {
  e03: {
    sheet: 'e03',
    sheetName: '货币资金发函记录表E0-3',
    formatVersion: 'send-list-e03-v1',
    componentType: 'confirmation-send-list-e03',
    columns: E03_COLUMNS,
    hasConfirmFlag: true,
    supportsPrefill: true,
    columnToggle: true,
  },
  e04: {
    sheet: 'e04',
    sheetName: '借款发函记录表E0-4',
    formatVersion: 'send-list-e04-v1',
    componentType: 'confirmation-send-list-e04',
    columns: E04_COLUMNS,
    hasConfirmFlag: true,
    supportsPrefill: false,
    columnToggle: true,
  },
  e05: {
    sheet: 'e05',
    sheetName: '应付银行承兑汇票发函记录表E0-5',
    formatVersion: 'send-list-e05-v1',
    componentType: 'confirmation-send-list-e05',
    columns: E05_COLUMNS,
    hasConfirmFlag: false,
    supportsPrefill: false,
    columnToggle: false,
  },
  e06: {
    sheet: 'e06',
    sheetName: '理财产品发函记录表E0-6',
    formatVersion: 'send-list-e06-v1',
    componentType: 'confirmation-send-list-e06',
    columns: E06_COLUMNS,
    hasConfirmFlag: false,
    supportsPrefill: false,
    columnToggle: false,
  },
}

/** 四张表的 sheet name → SendListSheet key */
export function sheetKeyOf(sheetName: string): SendListSheet | undefined {
  for (const [key, spec] of Object.entries(SEND_LIST_SPECS)) {
    if (spec.sheetName === sheetName) return key as SendListSheet
  }
  return undefined
}
