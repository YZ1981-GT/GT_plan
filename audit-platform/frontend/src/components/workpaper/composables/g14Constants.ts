/** G14 信用减值损失 — 固定行（与 xlsx 审定表/明细表一致） */
export interface G14LineDef {
  rowKey: string
  label: string
  provisionAccount: string
}

export const G14_LINE_ITEMS: G14LineDef[] = [
  { rowKey: 'notes', label: '应收票据坏账损失', provisionAccount: '应收票据坏账准备' },
  { rowKey: 'ar', label: '应收账款坏账损失', provisionAccount: '应收账款坏账准备' },
  { rowKey: 'rfin', label: '应收款项融资坏账损失', provisionAccount: '应收款项融资坏账准备' },
  { rowKey: 'othar', label: '其他应收款坏账损失', provisionAccount: '其他应收款坏账准备' },
  { rowKey: 'debt', label: '债权投资减值损失', provisionAccount: '债权投资减值准备' },
  { rowKey: 'othdebt', label: '其他债权投资减值损失', provisionAccount: '其他综合收益-信用减值准备' },
  { rowKey: 'ltar', label: '长期应收款坏账损失', provisionAccount: '长期应收款坏账准备' },
  { rowKey: 'guarantee', label: '财务担保预计损失', provisionAccount: '预计负债' },
  { rowKey: 'other', label: '其他', provisionAccount: '' },
]

export const G14_ACCOUNT_CODE = '6702'
export const G14_CHANGE_RATE_THRESHOLD = 0.3

/** G14-2 各行 ECL 交叉验证默认索引（跳转对应科目底稿） */
export const G14_ECL_CROSS_REF: Record<string, string> = {
  notes: 'wp:D1-1',
  ar: 'wp:D2-1',
  rfin: 'wp:D5-1',
  othar: 'wp:F1-1',
  debt: 'wp:G4-1',
  othdebt: 'wp:G4-1',
  ltar: 'wp:G5-1',
  guarantee: '',
  other: '',
}

/** 附注披露（上市）— 与 xlsx 行 8–16 一致，复用 G14-2 明细 rowKey */
export const G14_DISCLOSURE_LISTED_ROWS = G14_LINE_ITEMS

/** 附注披露（国企）— 与 xlsx 行 8–11 一致（坏账损失合并披露） */
export const G14_DISCLOSURE_SOE_ROWS = [
  { rowKey: 'bad_debt', label: '坏账损失' },
  { rowKey: 'debt', label: '债权投资减值损失' },
  { rowKey: 'othdebt', label: '其他债权投资减值损失' },
  { rowKey: 'other', label: '其他' },
] as const

/** 国企「坏账损失」行对应的 G14-2 明细 rowKey 汇总源 */
export const G14_SOE_BAD_DEBT_SOURCES = ['notes', 'ar', 'rfin', 'othar', 'ltar', 'guarantee'] as const

export const G14_DISCLOSURE_FORMULA_MAP = [
  { field: '附注合计-本期', source: 'G14-1审定表', formula: 'SUM(currentAudited) = G14-adj-tb', account: '6702' },
  { field: '附注各行-本期', source: 'G14-2明细', formula: 'listed: 1:1 rowKey; SOE: bad_debt=Σ坏账源行', account: '6702' },
  { field: '附注合计-上期', source: 'G14-adj-prior', formula: 'priorAudited 各固定行', account: '6702' },
  { field: 'ECL交叉验证', source: 'G14-2核对列', formula: '与 D1/D2/D5/G4/G5 索引联动', account: '-' },
] as const
