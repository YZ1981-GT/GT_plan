/**
 * D4 营业收入/营业成本 披露数据模型引擎
 *
 * 源模板 `D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx`
 * 上市 `附注披露信息（上市公司）` / 国企 `附注披露信息（国企）`
 *
 * 三类列引擎：
 * 1.（1）（2）（3）（8）— 5 列两级表头（label + 本期发生额{收入,成本} + 上期发生額{收入,成本}）
 * 2.（4）分解信息 — 列转置 + 动态类别列，列 key 使用稳定标识 `{slot}_{seq}`
 *    （H7 范式：类别默认名可能重复，用 label 会撞键）
 * 3.（6）与剩余履约义务有关的信息 — 动态年度列 + 合计派生列
 *
 * 🔴 `buildD4*Columns` 函数零入参可调（平台 `disclosureColumnsCoverage.spec.ts` sweep）。
 * 🔴 所有列定义声明 `group` 或 `flat`（Property 13: 列头表态完备）。
 * 🔴 D4 不引入账龄档位（源模板 8 小节均无账龄维度，Property 28）。
 *
 * spec: d4-four-table-extraction-and-disclosure-alignment (Task 5.1)
 * Requirements: 4.1, 4.2, 4.4, 4.5, 4.7
 */
import type { ColumnDef } from './disclosureColumnDefs'

// ═══════════════════════════════════════════════════════════════════════════════
// §1 Tables（1）（2）（3）（8）— 5 列两级表头引擎
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * D4 两期数据列变体（区分叶子列名差异）。
 *
 * 源模板实证：
 * - （1）主表/（2）按行业/（8）试运行：叶子列 `收入`/`成本`
 * - （3）按地区 listed：叶子列 `主营业务收入`/`主营业务成本`
 * - （3）按地区 soe：叶子列 `收入`/`成本`
 */
export type D4TwoPeriodVariant =
  | 'main'          // （1）（2）（8）
  | 'region_listed' // （3）上市
  | 'region_soe'    // （3）国企

const LEAF_LABELS: Record<D4TwoPeriodVariant, { revenue: string; cost: string }> = {
  main: { revenue: '收入', cost: '成本' },
  region_listed: { revenue: '主营业务收入', cost: '主营业务成本' },
  region_soe: { revenue: '收入', cost: '成本' },
}

/**
 * 构建（1）（2）（3）（8）5 列两级表头列定义。
 *
 * 5 列 = label + 本期发生额{收入, 成本} + 上期发生额{收入, 成本}
 * 使用 group 声明两级表头结构。
 *
 * 零入参调用返回默认 `main` 变体（供 disclosureColumnsCoverage sweep）。
 */
export function buildD4TwoPeriodColumns(variant: D4TwoPeriodVariant = 'main'): ColumnDef[] {
  const leaves = LEAF_LABELS[variant]
  return [
    // 🔴 不得标 `flat: true`：`flat` 语义是「本表为单级表头」且标在**任意一列即对整表
    // 生效**（见 `disclosureColumnDefs.ColumnDef.flat`）。本表数据列带 `group`
    // （本期发生额 / 上期发生额）是**两级**表头，同表并存即矛盾声明 —— 后端会因 flat
    // 跳过分组处理，两级表头渲染不出来（两组「收入/成本」看不出属于本期还是上期）。
    // 🔴 标签列头取附注模板 `headers[0]` 字面 = `项目`（**无空格**）。
    // 原写「项 目」（中间一个空格）与模板不一致 ⇒ 同步后表头错位；该缺陷此前被
    // `d4NoteSubtableContract` 的 `columnsPending` 豁免掩盖（那条豁免的理由已被
    // 后端源码证伪，见该 spec 顶部说明），移除豁免后 P5 立刻暴露。
    { key: 'label', label: '项目', is_label: true },
    { key: 'endRevenue', label: leaves.revenue, format: 'amount', group: '本期发生额' },
    { key: 'endCost', label: leaves.cost, format: 'amount', group: '本期发生额' },
    { key: 'priorRevenue', label: leaves.revenue, format: 'amount', group: '上期发生额' },
    { key: 'priorCost', label: leaves.cost, format: 'amount', group: '上期发生额' },
  ]
}

/** 两期表行数据接口 */
export interface D4TwoPeriodRow {
  label: string
  endRevenue: number | null
  endCost: number | null
  priorRevenue: number | null
  priorCost: number | null
}

// ═══════════════════════════════════════════════════════════════════════════════
// §2 Table（4）— 列转置 + 动态类别列（稳定 key `{slot}_{seq}`）
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * （4）分解信息表的类别定义。
 *
 * 源模板（4）结构（openpyxl 合并区实证）：
 *   B45:I45 合并「本期发生额」→ 4 个分类类别（B46:C46 消费品 / D46:E46 汽车 / …）
 *   每类别下辖 `收入`/`成本` 两个叶子列。
 *   行 = `在某一时点确认`/`在某一时段确认`/`租赁收入`。
 *
 * 🔴 列 key 用稳定的 `{slot}_{seq}`，不能用 label（H7 范式）——
 * 默认类别名可能重复（如用户加两个都叫「其他」的类别），用 label 会撞键。
 */
export interface D4TransposeCategory {
  /** 稳定标识 `{slot}_{seq}`；删中间项不重排，不与已删 key 冲突 */
  key: string
  /** 类别名称（审计师可改名），如 `消费品`/`汽车`/`能源`/`其他` */
  label: string
}

/** 源模板默认 4 类别（B46:I46） */
export const D4_DEFAULT_CATEGORIES: readonly D4TransposeCategory[] = [
  { key: 'cat_1', label: '消费品' },
  { key: 'cat_2', label: '汽车' },
  { key: 'cat_3', label: '能源' },
  { key: 'cat_4', label: '其他' },
]

/**
 * 为动态类别分配下一个不冲突的 key。
 *
 * 取现有 key 的最大 seq + 1（不复用已删除的 seq），保证新增列不与历史数据错位。
 */
export function nextD4CategoryKey(categories: readonly D4TransposeCategory[]): string {
  const prefix = 'cat_'
  let max = 0
  for (const c of categories) {
    if (!c.key.startsWith(prefix)) continue
    const seq = Number(c.key.slice(prefix.length))
    if (Number.isFinite(seq) && seq > max) max = seq
  }
  return `${prefix}${max + 1}`
}

/**
 * 构建（4）分解信息列转置列定义。
 *
 * 列结构 = label + 每类别{收入, 成本} + 合计{收入, 成本}
 * 类别列用 `{categoryKey}_revenue`/`{categoryKey}_cost` 作 key（稳定、不撞）。
 * 使用 group 声明分组（类别 label 为父表头）。
 *
 * 零入参调用使用默认类别列表（供 disclosureColumnsCoverage sweep）。
 */
export function buildD4TransposeColumns(
  categories: readonly D4TransposeCategory[] = D4_DEFAULT_CATEGORIES,
): ColumnDef[] {
  const cols: ColumnDef[] = [
    // 同上：下面按 category 逐个 push 的列都带 `group: cat.label`，本表是两级表头，
    // 不得标 `flat`（会让后端跳过分组，各类别的「收入/成本」失去父表头归属）。
    // 标签列头同样取模板字面 `项目`（无空格）。
    { key: 'label', label: '项目', is_label: true },
  ]

  for (const cat of categories) {
    cols.push(
      { key: `${cat.key}_revenue`, label: '收入', format: 'amount', group: cat.label },
      { key: `${cat.key}_cost`, label: '成本', format: 'amount', group: cat.label },
    )
  }

  // 🔴 **没有横向合计列** —— 源 xlsx 实证（上市 R44~R56 / 国企 R37~R49）该表
  // 只有 9 列（label + 4 类别 × 收入/成本），合计是**行**（上市 R56 `=B52+B48`）。
  // 改造前这里自造了 `total_revenue`/`total_cost` 两列，使推送给附注的列比源模板
  // 多两列（Task 31 已移除）。底稿内部若需横向核对，用
  // `d4RevenueSegmentColumns.segmentRowAcrossCategories`，它不进列定义。

  return cols
}

/** （4）分解信息行数据接口（检查项作行，类别作列） */
export interface D4TransposeRow {
  label: string
  /** 各类别的 `{categoryKey}_revenue` / `{categoryKey}_cost` 字段 */
  [field: string]: string | number | null
}

/**
 * @deprecated Task 31 起退役 —— 行集真源是
 * `d4RevenueSegmentColumns.D4_SEGMENT_ROWS`（9 行，与源 xlsx 逐行对齐）。
 *
 * 本常量只有 3 项，丢了两个业务父行、空可扩行与合计行；且「在某一时点确认 /
 * 在某一时段确认」在源模板里**各出现两次**（主营业务下 + 其他业务下），
 * 单一字符串数组无法表达归属 ⇒ 单元格无法定位到正确的行。
 *
 * 保留仅为让存量引用可编译；新代码禁用（守卫 `d4SegmentRowAlignment.spec.ts`
 * 断言生产代码不再引用它）。
 */
export const D4_TRANSPOSE_CHECK_ITEMS = [
  '在某一时点确认',
  '在某一时段确认',
  '租赁收入',
] as const

// ═══════════════════════════════════════════════════════════════════════════════
// §3 Table（6）— 动态年度列 + 合计派生
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 构建（6）与剩余履约义务有关的信息列定义。
 *
 * 源模板结构（上市 R66~R71）：
 *   `年 度` + 年度列（由审计年度派生：`{auditYear+1}年` / `{auditYear+2}年`）+ `合计`
 *   行 = 合同描述（动态，用户可增减）
 *
 * 🔴 年度列由审计年度派生，禁止硬编码年份（Req 4.7 / Property 15）。
 * 🔴 合计列为派生列（各年度列之和），key 固定 `total`。
 *
 * 零入参调用使用默认审计年度 2025（供 disclosureColumnsCoverage sweep）。
 *
 * @param auditYear - 审计年度（如 2025），年度列为 `{auditYear+1}年`/`{auditYear+2}年`
 */
export function buildD4ObligationColumns(auditYear: number = 2025): ColumnDef[] {
  const year1 = auditYear + 1
  const year2 = auditYear + 2

  return [
    { key: 'label', label: '年度', is_label: true, flat: true },
    { key: `year_${year1}`, label: `${year1}年`, format: 'amount', flat: true },
    { key: `year_${year2}`, label: `${year2}年`, format: 'amount', flat: true },
    { key: 'total', label: '合计', format: 'amount', flat: true },
  ]
}

/**
 * 派生合计列值（各年度列之和）。
 *
 * @param row - 行数据对象
 * @param auditYear - 审计年度
 * @returns 合计值（全 null 时返回 null）
 */
export function deriveObligationTotal(
  row: Record<string, unknown>,
  auditYear: number,
): number | null {
  const year1Key = `year_${auditYear + 1}`
  const year2Key = `year_${auditYear + 2}`
  const v1 = typeof row[year1Key] === 'number' ? (row[year1Key] as number) : null
  const v2 = typeof row[year2Key] === 'number' ? (row[year2Key] as number) : null

  if (v1 === null && v2 === null) return null
  return Math.round(((v1 ?? 0) + (v2 ?? 0)) * 100) / 100
}

/** （6）义务行数据接口 */
export interface D4ObligationRow {
  label: string
  /** 动态年度字段 `year_{YYYY}` */
  [yearField: string]: string | number | null
}

/**
 * 获取（6）表的年度列 key 列表（不含 label 和 total）。
 * 用于前端遍历年度列做合计派生。
 */
export function getObligationYearKeys(auditYear: number): string[] {
  return [`year_${auditYear + 1}`, `year_${auditYear + 2}`]
}
