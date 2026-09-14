/**
 * g0DiffSourceManifest — G0 两张差异核对表源模板列清单（契约守卫基准）
 *
 * 源模板：backend/wp_templates/G/G0 投资循环函证.xlsx
 *   - 函证差异核对表G0-3（证券投资）：17 列，数量/市价/公允价值（账面·回函·差异）三维
 *   - 函证差异核对表G0-4(非证券投资)：15 列，持股比例/投资金额/投资条款（账面·回函·差异）三维
 *
 * 每列 { field, label, dim?, source_cell } 逐列对源模板 R5/R6 表头核对（M0 硬前置）。
 * source_cell 为源 xlsx R6 单元格列字母（差异列 K/L/M 为自动派生）。
 * 源外增强字段（source 无对应列）集中登记于 SECURITIES_SOURCE_EXTRA / NONSECURITIES_SOURCE_EXTRA。
 */

export interface G0DiffColumnSpec {
  field: string
  label: string
  /** 三维分组：'booked' 账面① / 'reply' 回函② / 'diff' 差异③ / undefined 通用 */
  dim?: 'booked' | 'reply' | 'diff'
  /** 源模板 R6 列字母 */
  source_cell: string
  /** 语义：text / enum / number / amount / ratio（百分点）/ term（条款文本） */
  kind: 'text' | 'enum' | 'number' | 'amount' | 'ratio' | 'term'
  /** 自动派生列（差异=账面−回函，只读） */
  derived?: boolean
}

// ─── G0-3 证券投资 17 列（源模板 A..Q） ──────────────────────────────────────
export const SECURITIES_DIFF_COLUMNS: G0DiffColumnSpec[] = [
  { field: 'confirm_index', label: '询证函索引号', source_cell: 'A', kind: 'text' },
  { field: 'security_name', label: '证券名称', dim: 'booked', source_cell: 'B', kind: 'text' },
  { field: 'fund_account', label: '资金账号', dim: 'booked', source_cell: 'C', kind: 'text' },
  { field: 'account_holder', label: '开户名称', dim: 'booked', source_cell: 'D', kind: 'text' },
  { field: 'booked_qty', label: '账面数量', dim: 'booked', source_cell: 'E', kind: 'number' },
  { field: 'booked_unit_fv', label: '账面市价（单价）', dim: 'booked', source_cell: 'F', kind: 'amount' },
  { field: 'booked_market_value', label: '账面余额', dim: 'booked', source_cell: 'G', kind: 'amount', derived: true },
  { field: 'confirmed_qty', label: '回函数量', dim: 'reply', source_cell: 'H', kind: 'number' },
  { field: 'confirmed_unit_fv', label: '回函市价（单价）', dim: 'reply', source_cell: 'I', kind: 'amount' },
  { field: 'confirmed_market_value', label: '回函公允价值', dim: 'reply', source_cell: 'J', kind: 'amount', derived: true },
  { field: 'qty_diff', label: '差异数量', dim: 'diff', source_cell: 'K', kind: 'number', derived: true },
  { field: 'fv_diff', label: '差异市价（单价）', dim: 'diff', source_cell: 'L', kind: 'amount', derived: true },
  { field: 'market_value_diff', label: '差异公允价值', dim: 'diff', source_cell: 'M', kind: 'amount', derived: true },
  { field: 'diff_reason', label: '差异原因', dim: 'diff', source_cell: 'N', kind: 'enum' },
  { field: 'support_evidence', label: '相关支持性证据', dim: 'diff', source_cell: 'O', kind: 'text' },
  { field: 'need_adjust', label: '是否需要调账', dim: 'diff', source_cell: 'P', kind: 'enum' },
  { field: 'remark', label: '备注', source_cell: 'Q', kind: 'text' },
]

/** G0-3 源外增强字段（源模板 17 列无对应，保留不删，Requirement 1.4/6.3） */
export const SECURITIES_SOURCE_EXTRA: { field: string; label: string; reason: string }[] = [
  { field: 'security_code', label: '证券代码', reason: '既有实现增强，便于唯一定位证券；源模板 G0-3 无此列' },
  { field: 'security_type', label: '证券类型', reason: '既有实现增强（股票/基金/债券/其他）；源模板 G0-3 无此列' },
  { field: 'verify_conclusion', label: '核实结论', reason: '既有实现增强，便于记录逐笔核实结论；源模板 G0-3 无此列' },
  { field: 'adjustment_note', label: '调账说明', reason: '既有自由文本，作为「是否需要调账」判断列(need_adjust)的说明保留；旧数据迁移用' },
]

// ─── G0-4 非证券投资 15 列（源模板 A..O） ────────────────────────────────────
export const NONSECURITIES_DIFF_COLUMNS: G0DiffColumnSpec[] = [
  { field: 'confirm_index', label: '询证函索引号', source_cell: 'A', kind: 'text' },
  { field: 'entity_name', label: '被投资单位名称', dim: 'booked', source_cell: 'B', kind: 'text' },
  { field: 'booked_ratio', label: '账面持股比例', dim: 'booked', source_cell: 'C', kind: 'ratio' },
  { field: 'booked_amount', label: '账面投资金额', dim: 'booked', source_cell: 'D', kind: 'amount' },
  { field: 'booked_term', label: '账面其他投资限制/投资条款', dim: 'booked', source_cell: 'E', kind: 'term' },
  { field: 'reply_ratio', label: '回函持股比例', dim: 'reply', source_cell: 'F', kind: 'ratio' },
  { field: 'reply_amount', label: '回函投资金额', dim: 'reply', source_cell: 'G', kind: 'amount' },
  { field: 'reply_term', label: '回函其他投资限制/投资条款', dim: 'reply', source_cell: 'H', kind: 'term' },
  { field: 'ratio_diff', label: '差异比例', dim: 'diff', source_cell: 'I', kind: 'ratio', derived: true },
  { field: 'amount_diff', label: '差异金额', dim: 'diff', source_cell: 'J', kind: 'amount', derived: true },
  { field: 'term_match', label: '投资条款差异', dim: 'diff', source_cell: 'K', kind: 'enum' },
  { field: 'diff_reason', label: '差异原因', dim: 'diff', source_cell: 'L', kind: 'enum' },
  { field: 'support_evidence', label: '相关支持性证据', dim: 'diff', source_cell: 'M', kind: 'text' },
  { field: 'need_adjust', label: '是否需要调账', dim: 'diff', source_cell: 'N', kind: 'enum' },
  { field: 'remark', label: '备注', source_cell: 'O', kind: 'text' },
]

/** G0-4 源外增强字段（三维模型的辅助字段，非源模板列，不作为渲染列） */
export const NONSECURITIES_SOURCE_EXTRA: { field: string; label: string; reason: string }[] = [
  { field: 'term_diff_note', label: '投资条款差异说明', reason: '当 term_match=不一致 时的差异说明；源模板 K 为单列，本字段为可选补充数据不单独成列' },
  { field: 'adj_ref_index', label: '调整分录索引', reason: '需要调账时跳转 AJE 的索引；源模板 G0-4 无此列（下游联动用）' },
]

/** 需求列举的 G0-3 现缺列（Requirement 1.1）——用于守卫「已补齐」 */
export const SECURITIES_PREVIOUSLY_MISSING = [
  'confirm_index',
  'fund_account',
  'account_holder',
  'support_evidence',
] as const

// ─── 派生格格式化语义（Task 3 / Requirement 3） ────────────────────────────────

/**
 * 按 `field` 反查该列的 `kind`。
 *
 * 🔴 为什么需要它：两张差异表的三个/两个派生列此前一律 `{{ row.xxx }}` 裸渲染
 *    —— 浏览器实测（2026-08-04，项目 `2aa00f57`）「差异公允价值」显示 `3200`
 *    而非 `3,200.00`，违反平台「金额格式单一真源」铁律；同时「差异数量」
 *    与「差异比例」**不能**套金额格式（数量无小数、比例是百分点）。
 *    本函数把「哪列是金额」的判定收敛到 manifest 这一处，组件不再各写一份。
 *
 * 🔴 本函数是 `g0DiffSourceManifest.ts` 由「只有自己的测试引用」转为真实生产
 *    消费方的接线点（改造前它是第 4 个零消费方模块）。
 *
 * @param table 'securities' = G0-4 证券差异（目录索引号）；'nonSecurities' = G0-5
 * @param field 列字段名
 * @returns 该列 kind；字段不在 manifest 中时返回 `undefined`（调用方按非金额处理，
 *          绝不猜成金额 —— 猜错会把数量/比例也加上千分符与两位小数）
 */
export function diffColumnKind(
  table: 'securities' | 'nonSecurities',
  field: string,
): G0DiffColumnSpec['kind'] | undefined {
  const cols = table === 'securities' ? SECURITIES_DIFF_COLUMNS : NONSECURITIES_DIFF_COLUMNS
  return cols.find((c) => c.field === field)?.kind
}

/**
 * 判「该派生格是否按金额格式化」。
 *
 * 只有 `kind === 'amount'` 为真：`number`（数量）/`ratio`（百分点）/`term`/`text`/`enum`
 * 全部为假。**未登记字段一律为假**（宁缺勿造，见 `diffColumnKind` 注释）。
 */
export function isDiffAmountColumn(
  table: 'securities' | 'nonSecurities',
  field: string,
): boolean {
  return diffColumnKind(table, field) === 'amount'
}
