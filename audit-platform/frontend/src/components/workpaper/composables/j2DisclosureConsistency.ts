/**
 * j2DisclosureConsistency — J2 披露内部勾稽检查（纯函数）
 *
 * 规则全取源模板 Excel 公式与 CAS 9 内建约束：
 *  ① 净负债 = DBO 义务现值 − 计划资产公允价值（期末逐行勾稽）
 *  ② 汇总表期末 = 期初 + 本期增加 − 本期减少
 *  ③ 变动表 五、期末余额 = 一 + 二 + 三 + 四（分组合计勾稽）
 *  ④ 计划资产构成合计 = Σ各分类
 *  ⑤ 到期分析合计 vs 汇总表期末（跨表交叉勾稽）
 *
 * 消费方：J2 两个披露 Tab 的勾稽面板（J2DisclosureConsistencyPanel）。
 */

export interface ConsistencyItem {
  label: string
  rule: string
  left: number
  right: number
  diff: number
  level: 'ok' | 'warning' | 'error'
  detail: string
  refs: string[]
}

export interface J2ConsistencySummary {
  checks: ConsistencyItem[]
  errorCount: number
  okCount: number
  allPass: boolean
}

const TOLERANCE = 0.01

function check(label: string, rule: string, left: number, right: number, refs: string[] = []): ConsistencyItem {
  const diff = Math.round((left - right) * 100) / 100
  const level = Math.abs(diff) <= TOLERANCE ? 'ok' : 'error'
  const detail = level === 'ok' ? '' : `差异 ${diff.toFixed(2)}`
  return { label, rule, left, right, diff, level, detail, refs }
}

function summarize(items: ConsistencyItem[]): J2ConsistencySummary {
  const errorCount = items.filter(i => i.level === 'error').length
  return {
    checks: items,
    errorCount,
    okCount: items.length - errorCount,
    allPass: errorCount === 0,
  }
}

/**
 * 国企版勾稽（合并表结构）
 */
export interface J2SoeConsistencyInput {
  /** 汇总表各行期末 */
  summaryEnds: { dbpNet: number; otherLtNet: number; termination: number; total: number }
  /** 变动表期末行各列 */
  changeEnd: { dbo: number; asset: number; net: number }
  /** 变动表按行加总（一+二+三+四）各列 */
  changeCalcEnd: { dbo: number; asset: number; net: number }
  /** 到期分析合计 */
  maturityTotal: number
  /** 计划资产构成合计（期末） */
  assetCompTotal: number
}

export function buildJ2SoeConsistency(input: J2SoeConsistencyInput): J2ConsistencySummary {
  const items: ConsistencyItem[] = []

  // ① 净负债 = DBO - 计划资产（期末）
  items.push(check(
    '净负债 = 义务现值 − 计划资产',
    'DBO期末 − 计划资产期末 = 净负债期末',
    input.changeEnd.dbo - input.changeEnd.asset,
    input.changeEnd.net,
    ['wp:J2-1'],
  ))

  // ③ 期末余额 = 一+二+三+四（DBO 列）
  items.push(check(
    'DBO 期末余额 = 一+二+三+四',
    '分组合计勾稽',
    input.changeCalcEnd.dbo,
    input.changeEnd.dbo,
  ))

  // ③ 期末余额 = 一+二+三+四（净负债列）
  items.push(check(
    '净负债期末 = 一+二+三+四',
    '分组合计勾稽',
    input.changeCalcEnd.net,
    input.changeEnd.net,
  ))

  // ⑤ 到期分析合计 vs 汇总表设定受益计划净负债期末
  if (input.maturityTotal !== 0) {
    items.push(check(
      '到期分析合计 vs 汇总净负债期末',
      '跨表交叉勾稽',
      input.maturityTotal,
      input.summaryEnds.dbpNet,
    ))
  }

  return summarize(items)
}

/**
 * 上市版勾稽（三张独立变动表）
 */
export interface J2ListedConsistencyInput {
  /** 汇总表小计（不含减一年内） */
  summarySubtotalEnd: number
  /** 汇总表合计（减一年内后） */
  summaryTotalEnd: number
  /** DBO 表期末行 */
  dboEnd: number
  /** 计划资产表期末行 */
  assetEnd: number
  /** 净负债表期末行 */
  netEnd: number
  /** 到期分析合计 */
  maturityTotal: number
  /** 计划资产构成合计（期末） */
  assetCompTotal: number
}

export function buildJ2ListedConsistency(input: J2ListedConsistencyInput): J2ConsistencySummary {
  const items: ConsistencyItem[] = []

  // ① 净负债 = DBO − 计划资产
  items.push(check(
    '净负债期末 = DBO期末 − 计划资产期末',
    'CAS 9 基本勾稽',
    input.dboEnd - input.assetEnd,
    input.netEnd,
    ['wp:J2-1'],
  ))

  // ④ 计划资产构成合计 vs 计划资产表期末
  if (input.assetCompTotal !== 0 || input.assetEnd !== 0) {
    items.push(check(
      '资产构成合计 = 计划资产期末',
      '(2)→(1) 跨表',
      input.assetCompTotal,
      input.assetEnd,
    ))
  }

  // ⑤ 到期分析合计 vs 汇总净负债
  if (input.maturityTotal !== 0) {
    items.push(check(
      '到期分析合计 vs 汇总期末',
      '跨表交叉勾稽',
      input.maturityTotal,
      input.summaryTotalEnd,
    ))
  }

  return summarize(items)
}
