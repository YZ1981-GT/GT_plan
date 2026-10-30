/**
 * E1-14 货币资金分析表：模板单元格 → 网页视图位置（spec wp-deeplink-cell-locate-closure 需求 4）。
 *
 * 行号、行标签、表头文字逐项取自模板「货币资金分析表E1-14」，后端用例
 * `backend/tests/test_e1_analysis_anchor_template_contract.py` 读模板逐格校验（模板改了即红）。
 * 网页三张表（E1TabAnalysis 的构成 / 其他货币资金 / 比例表）行顺序与模板一致；网页没有合计行、
 * 也没有上期 / 前期结构比与上期变动列 —— 这些位置定位到整行，合计行返回 null（由调用方提示「没有对应位置」）。
 */

export type E1AnalysisSection = 'composition' | 'other' | 'ratios'
export type E1AnalysisBlock = 'f3-2' | 'note' | 'conclusion'

export interface E1AnalysisAnchor {
  /** 'cell' 单元格；'row' 整行；'block' 提示 / 卡片 */
  kind: 'cell' | 'row' | 'block'
  /** 需要切到的区段页签（审计说明 / 结论卡片在页签外，无需切换） */
  section?: E1AnalysisSection
  table?: E1AnalysisSection
  rowIndex?: number
  columnLabel?: string
  block?: E1AnalysisBlock
}

interface TemplateColumn {
  /** 网页表头文字 */
  html: string
  /** 模板表头（headerRow 行同列）的文字，供后端用例核对 */
  template: string
}

interface TemplateTable {
  section: E1AnalysisSection
  headerRow: number
  rows: ReadonlyArray<{ row: number; templateLabel: string }>
  columns: Readonly<Record<string, TemplateColumn>>
}

/** 模板三张表（顺序 = 网页行顺序） */
export const E1_ANALYSIS_TEMPLATE_TABLES: readonly TemplateTable[] = [
  {
    section: 'composition',
    headerRow: 14,
    rows: [
      { row: 15, templateLabel: '库存现金' },
      { row: 16, templateLabel: '银行存款' },
      { row: 17, templateLabel: '其他货币资金' },
    ],
    columns: {
      C: { html: '本期金额', template: '金额' },
      D: { html: '本期结构比', template: '结构比' },
      E: { html: '上期金额', template: '金额' },
      G: { html: '前期金额', template: '金额' },
      I: { html: '本期变动率', template: '本期变动' },
    },
  },
  {
    section: 'other',
    headerRow: 21,
    rows: [
      { row: 22, templateLabel: '银行汇票存款' },
      { row: 23, templateLabel: '银行本票存款' },
      { row: 24, templateLabel: '信用证保证金存款' },
      { row: 25, templateLabel: '外埠存款' },
      { row: 26, templateLabel: '存出投资款' },
      { row: 27, templateLabel: '信用卡存款' },
      { row: 28, templateLabel: '支付宝、微信及其他' },
    ],
    columns: {
      C: { html: '本期金额', template: '金额' },
      E: { html: '上期金额', template: '金额' },
      G: { html: '前期金额', template: '金额' },
    },
  },
  {
    section: 'ratios',
    headerRow: 33,
    rows: [
      { row: 34, templateLabel: '银行存款÷资产总额' },
      { row: 35, templateLabel: '定期存款÷银行存款' },
      { row: 36, templateLabel: '（定期存款+大额存单）÷银行存款' },
      { row: 37, templateLabel: '受限货币资金÷货币资金' },
      { row: 38, templateLabel: '存放财务公司款项÷货币资金' },
      { row: 39, templateLabel: '货币资金÷贷款总额' },
      { row: 40, templateLabel: '定期存款÷贷款总额' },
      // 模板第 8 行是「……」占位，网页第 8 项为「银行存款÷货币资金（集中度）」
      { row: 41, templateLabel: '……' },
    ],
    columns: {
      C: { html: '本期', template: '=C13' },
      D: { html: '上期', template: '=E13' },
      E: { html: '前期', template: '=G13' },
      F: { html: '本期变动', template: '本期变动' },
      // H33:K33 合并，四列同一处
      H: { html: '差异原因及合理性', template: '差异原因及合理性解释' },
      I: { html: '差异原因及合理性', template: '' },
      J: { html: '差异原因及合理性', template: '' },
      K: { html: '差异原因及合理性', template: '' },
    },
  },
]

/** 模板里的文字块 → 网页提示 / 卡片（templatePrefix 为模板 A 列首行文字前缀） */
export const E1_ANALYSIS_TEMPLATE_BLOCKS: ReadonlyArray<{
  block: E1AnalysisBlock
  rows: readonly number[]
  section?: E1AnalysisSection
  templatePrefix: string
}> = [
  { block: 'f3-2', rows: [30], section: 'other', templatePrefix: '其他货币资金中银行承兑汇票保证金测算' },
  { block: 'note', rows: [43, 44, 45, 46, 47, 48], templatePrefix: '三、审计说明' },
  { block: 'conclusion', rows: [50], templatePrefix: '四、审计结论' },
]

const A1 = /^([A-Z]{1,3})(\d{1,5})$/

/** 模板单元格地址 → 网页位置；模板有、网页没有的位置返回 null */
export function resolveE1AnalysisAnchor(cellRef: string | null | undefined): E1AnalysisAnchor | null {
  const m = A1.exec(String(cellRef || '').trim().toUpperCase())
  if (!m) return null
  const [, column, rowText] = m
  const row = Number(rowText)
  for (const table of E1_ANALYSIS_TEMPLATE_TABLES) {
    const rowIndex = table.rows.findIndex((r) => r.row === row)
    if (rowIndex < 0) continue
    const col = table.columns[column]
    return col
      ? { kind: 'cell', section: table.section, table: table.section, rowIndex, columnLabel: col.html }
      : { kind: 'row', section: table.section, table: table.section, rowIndex }
  }
  const block = E1_ANALYSIS_TEMPLATE_BLOCKS.find((b) => b.rows.includes(row))
  return block ? { kind: 'block', section: block.section, block: block.block } : null
}

/** 在 E1TabAnalysis 根元素内找锚点元素（表格需带 data-e1-table，块需带 data-e1-anchor） */
export function findE1AnalysisAnchorElement(root: ParentNode, anchor: E1AnalysisAnchor): Element | null {
  if (anchor.kind === 'block') return root.querySelector(`[data-e1-anchor="${anchor.block}"]`)
  const table = root.querySelector(`[data-e1-table="${anchor.table}"]`)
  if (!table) return null
  const row = table.querySelectorAll('.el-table__body tr.el-table__row')[anchor.rowIndex ?? -1] ?? null
  if (!row || anchor.kind === 'row') return row
  const headers = Array.from(table.querySelectorAll('.el-table__header thead th'))
  const index = headers.findIndex((th) => (th.textContent || '').trim() === anchor.columnLabel)
  return index >= 0 ? row.children[index] ?? null : null
}
