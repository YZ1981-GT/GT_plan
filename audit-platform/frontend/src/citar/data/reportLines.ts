/**
 * CITAR 余额表 / 序时账的列定义（移植自 CITAR src/app/report-lines.ts）。
 * 报表行次已改由平台报表配置（/api/reports）提供，这里只留表头列。
 */

/** 科目余额表的列定义（账务查询的科目余额表、试算平衡表的底稿取数余额表共用）。*/
export const TRIAL_BALANCE_COLUMNS = [
  { key: 'seq', label: '序号', numeric: false },
  { key: 'accountCode', label: '科目编码', numeric: false },
  { key: 'accountName', label: '科目名称', numeric: false },
  { key: 'openingDirection', label: '期初方向', numeric: false },
  { key: 'openingBalance', label: '期初余额', numeric: true },
  { key: 'periodDebit', label: '本期借方', numeric: true },
  { key: 'periodCredit', label: '本期贷方', numeric: true },
  { key: 'closingDirection', label: '期末方向', numeric: false },
  { key: 'closingBalance', label: '期末余额', numeric: true },
] as const

/** 序时账的列定义。*/
export const JOURNAL_COLUMNS = [
  { key: 'seq', label: '序号', numeric: false },
  { key: 'date', label: '日期', numeric: false },
  { key: 'voucherNo', label: '凭证号', numeric: false },
  { key: 'summary', label: '摘要', numeric: false },
  { key: 'accountCode', label: '科目编码', numeric: false },
  { key: 'accountName', label: '科目名称', numeric: false },
  { key: 'auxiliary', label: '辅助核算', numeric: false },
  { key: 'currency', label: '币种', numeric: false },
  { key: 'debit', label: '借方', numeric: true },
  { key: 'credit', label: '贷方', numeric: true },
] as const

/**
 * 审定科目余额表的列定义。
 *
 * 比未审表多四列调整栏:期初调整、借方审计调整、贷方审计调整,
 * 以及末列由「期末余额」改为「调整后期末余额」。
 * 调整值来自已批准的调整分录（平台暂无期初调整，按 0 列示）。
 *
 * 13 列横排约需 1500px,故按期初、本期、期末分三组,
 * 用两层表头表达「原值 + 调整 = 调整后」的关系。
 */
export type AuditedColumnGroup = {
  label: string
  columns: ReadonlyArray<{
    key: string
    label: string
    numeric: boolean
    /** 调整列。与原值列用底色区分,便于看出哪些由分录驱动。*/
    adjustment?: true
  }>
}

export const AUDITED_TRIAL_BALANCE_GROUPS: AuditedColumnGroup[] = [
  {
    label: '科目',
    columns: [
      { key: 'seq', label: '序号', numeric: false },
      { key: 'accountCode', label: '科目编码', numeric: false },
      { key: 'accountName', label: '科目名称', numeric: false },
    ],
  },
  {
    label: '期初',
    columns: [
      { key: 'openingDirection', label: '期初方向', numeric: false },
      { key: 'openingBalance', label: '期初余额', numeric: true },
      { key: 'openingAdjustment', label: '期初调整', numeric: true, adjustment: true },
      { key: 'adjustedOpeningBalance', label: '调整后期初余额', numeric: true },
    ],
  },
  {
    label: '本期',
    columns: [
      { key: 'periodDebit', label: '本期借方', numeric: true },
      { key: 'debitAdjustment', label: '借方审计调整', numeric: true, adjustment: true },
      { key: 'periodCredit', label: '本期贷方', numeric: true },
      {
        key: 'creditAdjustment',
        label: '贷方审计调整',
        numeric: true,
        adjustment: true,
      },
    ],
  },
  {
    label: '期末',
    columns: [
      { key: 'closingDirection', label: '期末方向', numeric: false },
      { key: 'adjustedClosingBalance', label: '调整后期末余额', numeric: true },
    ],
  },
]