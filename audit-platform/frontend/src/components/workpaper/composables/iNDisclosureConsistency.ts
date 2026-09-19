/**
 * I 循环六组披露表勾稽引擎（纯函数，无 Vue 依赖）
 *
 * 规则全取源模板 Excel 公式，不自造审计判断。
 *
 * | 循环 | 科目 | 勾稽规则 |
 * |---|---|---|
 * | I1 无形资产 | 1701/1702/1703 | 四层派生（carrying = cost − amort − impair）+ 合计列=SUM(各分类列) |
 * | I2 开发支出 | 5301 | 期末G = 期初B + 增加C + D − 减少E − F |
 * | I3 商誉 | 1711 | 期末H = 期初B + 增C + D + E − 减F − G |
 * | I4 长期待摊费用 | 1801 | 期末F = 期初B + 增加C − 摊销D − 其他减少E |
 * | I5 其他非流动资产 | 1901 | 账面价值D = 账面余额B − 减值准备C |
 * | I6 研发费用 | 6602 | 无公式勾稽（平表，仅合计行 = Σ 明细行） |
 *
 * 容差 0.01 元（委托平台共用 `WP_CHECK_TOLERANCE`）。
 * 缺数据（null）→ skip 不误报。
 *
 * spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/ Task 6.5
 */

import {
  eqCheck,
  nz,
  summarizeChecks,
  sumNullable,
  type NullableAmount,
  type WpCheckResult,
  type WpCheckSummary,
} from './shared/disclosureConsistency'

// ─── I1 无形资产 ──────────────────────────────────────────────────────────────

/**
 * I1 四层派生行数据（源模板列转置结构：列 = 分类，行 = 变动项目）
 * 每列（分类）有四层：账面原值 / 累计摊销 / 减值准备 / 账面价值
 */
export interface I1CategoryLayer {
  /** 分类标识 */
  key: string
  /** 账面原值期末 */
  costEnd: NullableAmount
  /** 累计摊销期末 */
  amortEnd: NullableAmount
  /** 减值准备期末 */
  impairEnd: NullableAmount
  /** 账面价值期末 */
  carryingEnd: NullableAmount
}

/**
 * I1 整表汇总行（合计列）
 */
export interface I1TotalColumn {
  costEnd: NullableAmount
  amortEnd: NullableAmount
  impairEnd: NullableAmount
  carryingEnd: NullableAmount
}

/**
 * I1 勾稽：四层派生 + 合计列 = SUM(各分类列)
 *
 * 源模板公式：
 * - 账面价值 = 账面原值 − 累计摊销 − 减值准备（每一列独立成立）
 * - 合计列 = SUM(各分类列)（每一层独立成立）
 */
export function checkI1Consistency(
  categories: readonly I1CategoryLayer[],
  totals: I1TotalColumn,
): WpCheckSummary {
  const checks: WpCheckResult[] = []

  // 1. 每个分类的四层派生：carrying = cost - amort - impair
  for (const cat of categories) {
    const cost = nz(cat.costEnd)
    const amort = nz(cat.amortEnd)
    const impair = nz(cat.impairEnd)
    const carrying = nz(cat.carryingEnd)
    const computed = cost !== null && amort !== null && impair !== null
      ? Math.round((cost - amort - impair) * 100) / 100
      : null
    checks.push(eqCheck(
      `${cat.key}：账面价值 = 原值 − 摊销 − 减值`,
      `源模板公式：账面价值(期末) = 账面原值(期末) − 累计摊销(期末) − 减值准备(期末)`,
      carrying,
      computed,
      ['Note:五、19', 'Note:八、19'],
    ))
  }

  // 2. 合计列四层派生
  const tCost = nz(totals.costEnd)
  const tAmort = nz(totals.amortEnd)
  const tImpair = nz(totals.impairEnd)
  const tCarrying = nz(totals.carryingEnd)
  const tComputed = tCost !== null && tAmort !== null && tImpair !== null
    ? Math.round((tCost - tAmort - tImpair) * 100) / 100
    : null
  checks.push(eqCheck(
    '合计列：账面价值 = 原值 − 摊销 − 减值',
    '源模板公式：合计列账面价值(期末) = 合计列原值(期末) − 合计列摊销(期末) − 合计列减值(期末)',
    tCarrying,
    tComputed,
    ['Note:五、19', 'Note:八、19'],
  ))

  // 3. 合计列 = SUM(各分类列)（四层各一条）
  const sumCost = sumNullable(categories.map((c) => c.costEnd))
  const sumAmort = sumNullable(categories.map((c) => c.amortEnd))
  const sumImpair = sumNullable(categories.map((c) => c.impairEnd))
  const sumCarrying = sumNullable(categories.map((c) => c.carryingEnd))

  checks.push(eqCheck(
    '账面原值：合计 = Σ各分类',
    '源模板公式：合计列(账面原值期末) = SUM(各分类列(账面原值期末))',
    tCost,
    sumCost,
    [],
  ))
  checks.push(eqCheck(
    '累计摊销：合计 = Σ各分类',
    '源模板公式：合计列(累计摊销期末) = SUM(各分类列(累计摊销期末))',
    tAmort,
    sumAmort,
    [],
  ))
  checks.push(eqCheck(
    '减值准备：合计 = Σ各分类',
    '源模板公式：合计列(减值准备期末) = SUM(各分类列(减值准备期末))',
    tImpair,
    sumImpair,
    [],
  ))
  checks.push(eqCheck(
    '账面价值：合计 = Σ各分类',
    '源模板公式：合计列(账面价值期末) = SUM(各分类列(账面价值期末))',
    tCarrying,
    sumCarrying,
    [],
  ))

  return summarizeChecks(checks)
}

// ─── I2 开发支出 ──────────────────────────────────────────────────────────────

/**
 * I2 开发支出行：期末G = 期初B + 增加C + D − 减少E − F
 *
 * 源模板列：B期初余额 / C本期研发支出增加 / D其他增加 / E确认为无形资产 / F其他减少 / G期末余额
 */
export interface I2Row {
  beginBalance: NullableAmount   // B 期初余额
  rdIncrease: NullableAmount     // C 本期研发支出增加
  otherIncrease: NullableAmount  // D 其他增加
  toIntangible: NullableAmount   // E 确认为无形资产（减少）
  otherDecrease: NullableAmount  // F 其他减少
  endBalance: NullableAmount     // G 期末余额
}

/**
 * I2 勾稽：期末 = 期初 + 增加C + D − 减少E − F
 */
export function checkI2Consistency(rows: readonly I2Row[]): WpCheckSummary {
  const checks: WpCheckResult[] = []

  // 逐行检查
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]
    const b = nz(r.beginBalance)
    const c = nz(r.rdIncrease)
    const d = nz(r.otherIncrease)
    const e = nz(r.toIntangible)
    const f = nz(r.otherDecrease)
    const g = nz(r.endBalance)
    const computed = b !== null && c !== null && d !== null && e !== null && f !== null
      ? Math.round((b + c + d - e - f) * 100) / 100
      : null
    checks.push(eqCheck(
      `第${i + 1}行：期末 = 期初+增C+D−减E−F`,
      '源模板公式：期末余额G = 期初余额B + 本期研发支出增加C + 其他增加D − 确认为无形资产E − 其他减少F',
      g,
      computed,
      ['Note:五、20', 'Note:八、20'],
    ))
  }

  // 合计行（所有行之和的勾稽）
  if (rows.length > 1) {
    const sumEnd = sumNullable(rows.map((r) => r.endBalance))
    const sumBegin = sumNullable(rows.map((r) => r.beginBalance))
    const sumC = sumNullable(rows.map((r) => r.rdIncrease))
    const sumD = sumNullable(rows.map((r) => r.otherIncrease))
    const sumE = sumNullable(rows.map((r) => r.toIntangible))
    const sumF = sumNullable(rows.map((r) => r.otherDecrease))
    const computedTotal = sumBegin !== null && sumC !== null && sumD !== null && sumE !== null && sumF !== null
      ? Math.round((sumBegin + sumC + sumD - sumE - sumF) * 100) / 100
      : null
    checks.push(eqCheck(
      '合计：期末 = 期初+增C+D−减E−F',
      '源模板公式：合计行期末 = Σ(期初+增C+D−减E−F)',
      sumEnd,
      computedTotal,
      [],
    ))
  }

  return summarizeChecks(checks)
}

// ─── I3 商誉 ─────────────────────────────────────────────────────────────────

/**
 * I3 商誉行：期末H = 期初B + 增C + D + E − 减F − G
 *
 * 源模板列：B期初余额 / C企业合并形成 / D其他增加 / E减值准备转回 /
 *           F处置或其他减少 / G本期计提减值 / H期末余额
 */
export interface I3Row {
  beginBalance: NullableAmount   // B 期初余额
  mergerIncrease: NullableAmount // C 企业合并形成
  otherIncrease: NullableAmount  // D 其他增加
  impairReversal: NullableAmount // E 减值准备转回
  disposal: NullableAmount       // F 处置或其他减少
  impairProvision: NullableAmount// G 本期计提减值
  endBalance: NullableAmount     // H 期末余额
}

/**
 * I3 勾稽：期末 = 期初 + C + D + E − F − G
 */
export function checkI3Consistency(rows: readonly I3Row[]): WpCheckSummary {
  const checks: WpCheckResult[] = []

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]
    const b = nz(r.beginBalance)
    const c = nz(r.mergerIncrease)
    const d = nz(r.otherIncrease)
    const e = nz(r.impairReversal)
    const f = nz(r.disposal)
    const g = nz(r.impairProvision)
    const h = nz(r.endBalance)
    const computed = b !== null && c !== null && d !== null && e !== null && f !== null && g !== null
      ? Math.round((b + c + d + e - f - g) * 100) / 100
      : null
    checks.push(eqCheck(
      `第${i + 1}行：期末 = 期初+C+D+E−F−G`,
      '源模板公式：期末余额H = 期初余额B + 企业合并C + 其他增加D + 减值转回E − 处置减少F − 本期计提减值G',
      h,
      computed,
      ['Note:五、21', 'Note:八、21'],
    ))
  }

  if (rows.length > 1) {
    const sumH = sumNullable(rows.map((r) => r.endBalance))
    const sumB = sumNullable(rows.map((r) => r.beginBalance))
    const sumC = sumNullable(rows.map((r) => r.mergerIncrease))
    const sumD = sumNullable(rows.map((r) => r.otherIncrease))
    const sumE = sumNullable(rows.map((r) => r.impairReversal))
    const sumF = sumNullable(rows.map((r) => r.disposal))
    const sumG = sumNullable(rows.map((r) => r.impairProvision))
    const computedTotal = sumB !== null && sumC !== null && sumD !== null && sumE !== null && sumF !== null && sumG !== null
      ? Math.round((sumB + sumC + sumD + sumE - sumF - sumG) * 100) / 100
      : null
    checks.push(eqCheck(
      '合计：期末 = 期初+C+D+E−F−G',
      '源模板公式：合计行期末 = Σ(期初+C+D+E−F−G)',
      sumH,
      computedTotal,
      [],
    ))
  }

  return summarizeChecks(checks)
}

// ─── I4 长期待摊费用 ──────────────────────────────────────────────────────────

/**
 * I4 长期待摊费用行：期末F = 期初B + 增加C − 摊销D − 其他减少E
 *
 * 源模板列：B期初余额 / C本期增加 / D本期摊销 / E其他减少 / F期末余额
 */
export interface I4Row {
  beginBalance: NullableAmount   // B 期初余额
  increase: NullableAmount       // C 本期增加
  amortization: NullableAmount   // D 本期摊销
  otherDecrease: NullableAmount  // E 其他减少
  endBalance: NullableAmount     // F 期末余额
}

/**
 * I4 勾稽：期末 = 期初 + 增加 − 摊销 − 其他减少
 */
export function checkI4Consistency(rows: readonly I4Row[]): WpCheckSummary {
  const checks: WpCheckResult[] = []

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]
    const b = nz(r.beginBalance)
    const c = nz(r.increase)
    const d = nz(r.amortization)
    const e = nz(r.otherDecrease)
    const f = nz(r.endBalance)
    const computed = b !== null && c !== null && d !== null && e !== null
      ? Math.round((b + c - d - e) * 100) / 100
      : null
    checks.push(eqCheck(
      `第${i + 1}行：期末 = 期初+增−摊−减`,
      '源模板公式：期末余额F = 期初余额B + 本期增加C − 本期摊销D − 其他减少E',
      f,
      computed,
      ['Note:五、27', 'Note:八、27'],
    ))
  }

  if (rows.length > 1) {
    const sumF = sumNullable(rows.map((r) => r.endBalance))
    const sumB = sumNullable(rows.map((r) => r.beginBalance))
    const sumC = sumNullable(rows.map((r) => r.increase))
    const sumD = sumNullable(rows.map((r) => r.amortization))
    const sumE = sumNullable(rows.map((r) => r.otherDecrease))
    const computedTotal = sumB !== null && sumC !== null && sumD !== null && sumE !== null
      ? Math.round((sumB + sumC - sumD - sumE) * 100) / 100
      : null
    checks.push(eqCheck(
      '合计：期末 = 期初+增−摊−减',
      '源模板公式：合计行期末 = Σ(期初+增−摊−减)',
      sumF,
      computedTotal,
      [],
    ))
  }

  return summarizeChecks(checks)
}

// ─── I5 其他非流动资产 ────────────────────────────────────────────────────────

/**
 * I5 其他非流动资产行：账面价值D = 账面余额B − 减值准备C
 *
 * 源模板列：B账面余额 / C减值准备 / D账面价值
 */
export interface I5Row {
  endGross: NullableAmount       // B 账面余额（期末）
  endImpairment: NullableAmount  // C 减值准备（期末）
  endBookValue: NullableAmount   // D 账面价值（期末）
}

/**
 * I5 勾稽：账面价值 = 账面余额 − 减值准备
 */
export function checkI5Consistency(rows: readonly I5Row[]): WpCheckSummary {
  const checks: WpCheckResult[] = []

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i]
    const b = nz(r.endGross)
    const c = nz(r.endImpairment)
    const d = nz(r.endBookValue)
    const computed = b !== null && c !== null
      ? Math.round((b - c) * 100) / 100
      : null
    checks.push(eqCheck(
      `第${i + 1}行：账面价值 = 余额−减值`,
      '源模板公式：账面价值D = 账面余额B − 减值准备C',
      d,
      computed,
      ['Note:五、28', 'Note:八、29'],
    ))
  }

  // 合计行
  if (rows.length > 1) {
    const sumD = sumNullable(rows.map((r) => r.endBookValue))
    const sumB = sumNullable(rows.map((r) => r.endGross))
    const sumC = sumNullable(rows.map((r) => r.endImpairment))
    const computedTotal = sumB !== null && sumC !== null
      ? Math.round((sumB - sumC) * 100) / 100
      : null
    checks.push(eqCheck(
      '合计：账面价值 = 余额−减值',
      '源模板公式：合计行账面价值 = Σ账面余额 − Σ减值准备',
      sumD,
      computedTotal,
      [],
    ))
  }

  return summarizeChecks(checks)
}

// ─── I6 研发费用 ──────────────────────────────────────────────────────────────

/**
 * I6 研发费用行（平表，无公式勾稽，仅合计行 = Σ 明细行）
 */
export interface I6Row {
  amount: NullableAmount
}

/**
 * I6 勾稽：合计行 = Σ 明细行（无其它公式，源模板为平表结构）
 */
export function checkI6Consistency(
  detailRows: readonly I6Row[],
  totalAmount: NullableAmount,
): WpCheckSummary {
  const sum = sumNullable(detailRows.map((r) => r.amount))
  const checks: WpCheckResult[] = [
    eqCheck(
      '合计 = Σ各明细行',
      '源模板公式：合计金额 = SUM(各明细行金额)（I6 为平表结构，仅合计行勾稽）',
      totalAmount,
      sum,
      ['Note:三、研发费用'],
    ),
  ]
  return summarizeChecks(checks)
}
