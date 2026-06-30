/**
 * useD7FormulaEngine — D7 合同负债共享纯函数公式引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * 覆盖合同负债（科目2205/贷方/负债类）的全部公式计算需求。
 *
 * 核心特色：
 *   - 贷方科目：期末余额 = 期初审定 + 贷方发生 - 借方发生（贷增借减）
 *   - 双区块审定表：按性质分类 + 按账龄分类（含"减：计入其他非流动负债"扣减行）
 *   - 合同负债合计 = 小计 - 非流动负债扣减
 *   - 按性质聚合 / 按账龄聚合 / Top10排序
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Requirements: 1.4, 2.3, 2.4, 2.5, 2.6, 5.4, 9.4, 11.3
 */

// ─── 类型定义 ──────────────────────────────────────────────────────────────────

/** 明细表D7-2行结构（聚合函数所需最小字段） */
export interface DetailRow {
  natureType: string       // 款项性质（预收货款/开发项目预收款/预收工程款/其他）
  endAudited: number       // 期末审定数
  endAging1: number        // 审定账龄-1年以下
  endAging2: number        // 审定账龄-1~2年
  endAging3: number        // 审定账龄-2~3年
  endAging4: number        // 审定账龄-3年以上
  [key: string]: unknown   // 允许额外字段
}

/** 按账龄聚合结果 */
export interface AgingAggregation {
  within1Year: number      // 1年以内(含1年)
  year1to2: number         // 1至2年(含2年)
  year2to3: number         // 2至3年(含3年)
  over3Years: number       // 3年以上
}

// ─── 数值解析 ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/空串/NaN/Infinity → 0
 *
 * 审计底稿中大量字段可能为空或无效值，统一转为数字 0 以确保公式运算不出 NaN。
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  if (!isFinite(n)) return 0
  return n
}

// ─── 贷方科目核心公式 ─────────────────────────────────────────────────────────

/**
 * 贷方科目期末余额 = 期初 + 贷方发生 - 借方发生
 *
 * D7核心公式，适用于D7-2明细表期末余额、D7-6关联方期末余额等。
 * 贷方科目特征：贷方增加、借方减少。与D3预收账款完全相同。
 */
export function calcCreditEndBalance(opening: number, credit: number, debit: number): number {
  return opening + credit - debit
}

// ─── 审定表基础公式 ──────────────────────────────────────────────────────────

/**
 * 审定数 = 未审 + AJE + RJE
 *
 * 通用审定金额计算，适用于D7-1/D7-2所有审定列。
 */
export function calcAuditedAmount(unadjusted: number, aje: number, rje: number): number {
  return unadjusted + aje + rje
}

// ─── 变动分析公式 ─────────────────────────────────────────────────────────────

/**
 * 变动额 = 期末审定 - 期初审定
 *
 * 注意参数顺序：(prior, current)，返回 current - prior。
 */
export function calcChangeAmount(prior: number, current: number): number {
  return current - prior
}

/**
 * 变动率计算，含期初=0特殊处理：
 * - 期初=0 且 期末=0 → ''（无意义，不显示）
 * - 期初=0（且期末≠0）→ 'N/A'（无法计算百分比变动）
 * - 其他 → (期末 - 期初) / 期初
 */
export function calcChangeRate(prior: number, current: number): number | '' | 'N/A' {
  if (prior === 0 && current === 0) return ''
  if (prior === 0) return 'N/A'
  return (current - prior) / prior
}

/**
 * 变动率绝对值是否超阈值
 *
 * 空串或'N/A'返回 false（无法判定），数值型取绝对值与阈值比较。
 * 适用于30%阈值高亮判定（变动率>30%红色高亮）。
 */
export function isChangeRateExceeding(rate: number | '' | 'N/A', threshold: number): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}

// ─── 合计/小计公式 ──────────────────────────────────────────────────────────

/**
 * 合计 = SUM(明细行数组)
 *
 * 通用求和，适用于D7-1各区块小计/D7-2合计/D7-5合计/D7-6合计。
 */
export function calcSubtotal(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0)
}

/**
 * 合同负债合计 = 小计 - 计入其他非流动负债的合同负债
 *
 * D7审定表"按性质分类"区块的合同负债合计行公式。
 * "减：计入其他非流动负债的合同负债"为扣减行（浅蓝色背景可编辑）。
 */
export function calcContractLiabilityTotal(subtotal: number, nonCurrentDeduction: number): number {
  return subtotal - nonCurrentDeduction
}

// ─── 聚合公式（跨Sheet数据映射）─────────────────────────────────────────────

/**
 * 按性质聚合：从明细行按款项性质分组SUM指定字段
 *
 * D7-2 → D7-1 "按性质分类"区块的核心聚合逻辑。
 * 按 natureType 分组后对指定 field 求和。
 */
export function aggregateByNature(rows: DetailRow[], field: string): Record<string, number> {
  const result: Record<string, number> = {}
  for (const row of rows) {
    const key = row.natureType || '其他'
    const value = typeof row[field] === 'number' ? (row[field] as number) : 0
    result[key] = (result[key] || 0) + value
  }
  return result
}

/**
 * 按账龄聚合：从明细行按审定账龄4段列SUM
 *
 * D7-2 → D7-1 "按账龄分类"区块的核心聚合逻辑。
 * 分别对 endAging1~endAging4 四列求和。
 */
export function aggregateByAging(rows: DetailRow[]): AgingAggregation {
  let within1Year = 0
  let year1to2 = 0
  let year2to3 = 0
  let over3Years = 0
  for (const row of rows) {
    within1Year += row.endAging1 || 0
    year1to2 += row.endAging2 || 0
    year2to3 += row.endAging3 || 0
    over3Years += row.endAging4 || 0
  }
  return { within1Year, year1to2, year2to3, over3Years }
}

// ─── 排序公式（分析表D7-4）─────────────────────────────────────────────────

/**
 * Top N 排序：按指定字段降序取前N
 *
 * D7-4分析表"期末Top10债务人"的排序逻辑。
 * 返回新数组，不修改原数组。
 */
export function topNByField<T>(rows: T[], field: keyof T, n: number): T[] {
  return [...rows]
    .sort((a, b) => {
      const va = typeof a[field] === 'number' ? (a[field] as number) : 0
      const vb = typeof b[field] === 'number' ? (b[field] as number) : 0
      return vb - va
    })
    .slice(0, n)
}
