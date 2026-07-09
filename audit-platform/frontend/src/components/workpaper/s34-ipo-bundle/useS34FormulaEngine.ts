/**
 * useS34FormulaEngine.ts — S34 子检查表公式引擎（纯函数）
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/ Task 7.2
 * Requirements: 5.2, 5.5
 *
 * 设计原则：
 * - 纯函数 composable，无副作用
 * - 支持 SUM 范围求和、安全除法、占比计算
 * - 公式单元格始终 readonly（不可手工覆盖）
 * - 导出所有纯函数供 PBT Property 8 测试
 *
 * 核心公式（S34-16-1 第三方回款情况检查表）：
 * - E19 = SUM(E8:E18)  营业收入合计
 * - F19 = SUM(F8:F18)  第三方代付合计
 * - C23 = E19           营业收入总额（引用）
 * - C24 = F19           第三方代付总额（引用）
 * - C25 = C24 / C23     第三方回款占比
 */

// ─── Types ───

export interface FormulaCell {
  /** 行索引（0-based） */
  row: number
  /** 列标识 */
  col: string
  /** 人类可读公式描述 */
  formula: string
  /** 计算函数：接收数据网格，返回计算值（null 表示除零/无效） */
  compute: (data: Record<string, number | null>[]) => number | null
  /** 公式单元格始终只读 */
  readonly: true
}

export interface FormulaResult {
  /** "row:col" → 计算值 */
  [cellKey: string]: number | null
}

// ─── 核心纯函数 ───

/**
 * 安全数值解析：null/undefined/NaN/空 → 0
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * 通用 SUM：对数值数组求和
 * Property 8 核心：SUM([]) = 0，SUM(values) = Σvalues
 */
export function sumRange(values: number[]): number {
  return values.reduce((acc, v) => acc + v, 0)
}

/**
 * 安全除法：分母为 0 时返回 null（避免 Infinity/NaN）
 * Property 8 核心：denominator=0 → null，否则 numerator/denominator
 */
export function safeDivide(numerator: number, denominator: number): number | null {
  if (denominator === 0) return null
  return numerator / denominator
}

/**
 * 占比计算：numerator / denominator × 100（百分比形式）
 * 分母为 0 → null
 */
export function calcRatio(numerator: number, denominator: number): number | null {
  if (denominator === 0) return null
  return (numerator / denominator) * 100
}

/**
 * 从数据网格中提取某列某行范围的数值数组
 * @param data 行记录数组
 * @param col 列标识
 * @param startRow 起始行（0-based，含）
 * @param endRow 结束行（0-based，含）
 */
export function extractColumnRange(
  data: Record<string, number | null>[],
  col: string,
  startRow: number,
  endRow: number,
): number[] {
  const result: number[] = []
  for (let i = startRow; i <= endRow && i < data.length; i++) {
    result.push(parseNum(data[i]?.[col]))
  }
  return result
}

/**
 * 获取单个单元格值
 */
export function getCellValue(
  data: Record<string, number | null>[],
  row: number,
  col: string,
): number {
  if (row < 0 || row >= data.length) return 0
  return parseNum(data[row]?.[col])
}

// ─── S34-16-1 公式定义 ───

/**
 * S34-16-1 第三方回款情况检查表 公式定义
 *
 * 源模板结构（27行×14列）：
 * - 行8~18（0-based: 7~17）：明细数据行（E列=营业收入，F列=第三方代付金额）
 * - 行19（0-based: 18）：合计行（E19=SUM(E8:E18)，F19=SUM(F8:F18)）
 * - 行23（0-based: 22）：C23 = 营业收入总额 = E19
 * - 行24（0-based: 23）：C24 = 第三方代付总额 = F19
 * - 行25（0-based: 24）：C25 = 第三方回款占比 = C24/C23
 */
export const S34_16_1_FORMULAS: FormulaCell[] = [
  {
    row: 18,
    col: 'E',
    formula: '=SUM(E8:E18)',
    compute: (data) => sumRange(extractColumnRange(data, 'E', 7, 17)),
    readonly: true,
  },
  {
    row: 18,
    col: 'F',
    formula: '=SUM(F8:F18)',
    compute: (data) => sumRange(extractColumnRange(data, 'F', 7, 17)),
    readonly: true,
  },
  {
    row: 22,
    col: 'C',
    formula: '=E19 (营业收入总额)',
    compute: (data) => sumRange(extractColumnRange(data, 'E', 7, 17)),
    readonly: true,
  },
  {
    row: 23,
    col: 'C',
    formula: '=F19 (第三方代付总额)',
    compute: (data) => sumRange(extractColumnRange(data, 'F', 7, 17)),
    readonly: true,
  },
  {
    row: 24,
    col: 'C',
    formula: '=C24/C23 (第三方回款占比)',
    compute: (data) => {
      const c23 = sumRange(extractColumnRange(data, 'E', 7, 17))
      const c24 = sumRange(extractColumnRange(data, 'F', 7, 17))
      return safeDivide(c24, c23)
    },
    readonly: true,
  },
]

// ─── S34-16-2 公式定义（同行业第三方回款对比表） ───

/**
 * S34-16-2 同行业第三方回款对比表（9个占比公式）
 * 行结构为对比型：每行含"收入金额"和"第三方代付金额"，占比 = 代付/收入
 */
export const S34_16_2_FORMULAS: FormulaCell[] = Array.from({ length: 9 }, (_, i) => ({
  row: 7 + i,
  col: 'G',
  formula: `=F${8 + i}/E${8 + i} (占比)`,
  compute: (data: Record<string, number | null>[]) => {
    const revenue = parseNum(data[7 + i]?.['E'])
    const thirdParty = parseNum(data[7 + i]?.['F'])
    return safeDivide(thirdParty, revenue)
  },
  readonly: true as const,
}))

// ─── 通用公式计算引擎 ───

/**
 * 计算所有公式值，返回 "row:col" → 计算结果 的映射
 *
 * Property 8 核心：对任意合法数据网格，汇总公式应等于纯函数计算结果，且不受手工覆盖影响
 *
 * @param data 数据网格（行记录数组）
 * @param formulaDefs 公式定义列表
 * @returns 单元格键→计算值 的映射
 */
export function computeFormulas(
  data: Record<string, number | null>[],
  formulaDefs: FormulaCell[],
): FormulaResult {
  const result: FormulaResult = {}
  for (const def of formulaDefs) {
    const key = `${def.row}:${def.col}`
    result[key] = def.compute(data)
  }
  return result
}

/**
 * 获取公式单元格位置集合（用于标记只读）
 * 返回 Set<"row:col">
 */
export function getReadonlyCells(formulaDefs: FormulaCell[]): Set<string> {
  return new Set(formulaDefs.map((def) => `${def.row}:${def.col}`))
}

/**
 * 判断某单元格是否为公式单元格（只读）
 */
export function isFormulaCell(
  row: number,
  col: string,
  formulaDefs: FormulaCell[],
): boolean {
  return formulaDefs.some((def) => def.row === row && def.col === col)
}

// ─── S34-34-1/2 判断列公式模式（工厂函数） ───

/**
 * 创建条件判断公式（用于 S34-34-1/2 自然人客户/供应商检查表的判断列）
 * 模式：IF(某列有值, '是', '否') 或 IF(金额>阈值, '异常', '正常')
 *
 * @param row 行索引
 * @param col 判断结果列
 * @param sourceCol 判据列
 * @param threshold 阈值（默认 0，即有值即为"是"）
 */
export function createThresholdFormula(
  row: number,
  col: string,
  sourceCol: string,
  threshold = 0,
): FormulaCell {
  return {
    row,
    col,
    formula: `=IF(${sourceCol}${row + 1}>${threshold}, 1, 0)`,
    compute: (data) => {
      const val = parseNum(data[row]?.[sourceCol])
      return val > threshold ? 1 : 0
    },
    readonly: true,
  }
}

// ─── S34-20-1 占比公式模式（工厂函数） ───

/**
 * 创建占比公式（用于 S34-20-1 重要劳务外包公司分析的占比列）
 * 模式：某行值 / 合计行值
 *
 * @param row 数据行
 * @param col 占比列
 * @param valueCol 数值列
 * @param totalRow 合计行
 */
export function createRatioFormula(
  row: number,
  col: string,
  valueCol: string,
  totalRow: number,
): FormulaCell {
  return {
    row,
    col,
    formula: `=${valueCol}${row + 1}/${valueCol}${totalRow + 1} (占比)`,
    compute: (data) => {
      const value = parseNum(data[row]?.[valueCol])
      const total = parseNum(data[totalRow]?.[valueCol])
      return safeDivide(value, total)
    },
    readonly: true,
  }
}

// ─── S34-25-1 核查范围公式 ───

/**
 * S34-25-1 第三方资金流水核查范围（4个公式：汇总行求和）
 */
export function createSumFormula(
  row: number,
  col: string,
  startRow: number,
  endRow: number,
): FormulaCell {
  return {
    row,
    col,
    formula: `=SUM(${col}${startRow + 1}:${col}${endRow + 1})`,
    compute: (data) => sumRange(extractColumnRange(data, col, startRow, endRow)),
    readonly: true,
  }
}
