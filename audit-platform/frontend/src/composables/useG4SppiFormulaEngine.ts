/**
 * useG4SppiFormulaEngine — G4 债权投资(SPPI组) 公式引擎
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/
 * Task: 2.1
 * Requirements: 6.1~6.10
 *
 * 所有函数为纯函数（无副作用、无Vue响应式依赖、无外部状态），
 * 支持 fast-check PBT 验证。
 *
 * 函数清单：
 * - parseNum: 输入清洗（null/undefined/NaN/空串 → 0）
 * - determineBusinessModel: 业务模式分类（5布尔→AC/FVOCI/FVTPL/INCOMPLETE）
 * - determineSPPIConclusion: SPPI结论推导（4布尔→PASS/FAIL/FURTHER_ANALYSIS）
 * - calcInventoryTotal: 盘点总计 = 面值×数量(2dp)
 * - calcReportDateQuantity: 报表日数量 = 盘点日数量+增减
 * - calcReportDateTotal: 报表日总计 = 面值×数量(2dp)
 * - calcReconciliationVariance: 差异 = 报表日总计-账面总计(2dp)
 * - isReconciliationBalanced: 倒轧平衡 = |差异|<0.01
 * - calcSumColumn: 数组求和
 * - determineFinalClassification: 组合判定(业务模式+SPPI→最终分类)
 */

// ══════════════════════════════════════════════════════════
// parseNum — 输入清洗（null/undefined/NaN/空串 → 0）
// ══════════════════════════════════════════════════════════

/**
 * 安全数值转换：将任意输入转为有效数字
 * - null / undefined / '' / NaN / 非有限数 → 0
 * - 有效数字 → 原值
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ══════════════════════════════════════════════════════════
// 决策函数1: 业务模式分类（5布尔→分类结果）
// ══════════════════════════════════════════════════════════

export interface BusinessModelAnswers {
  q1: boolean | null  // 是否以收取合同现金流量为目标
  q2: boolean | null  // 是否存在出售活动
  q3: boolean | null  // 出售是否频繁且金额重大
  q4: boolean | null  // 是否同时以收取现金流和出售为目标
  q5: boolean | null  // 是否持有以获取公允价值变动
}

export type BusinessModelResult = 'AC' | 'FVOCI' | 'FVTPL' | 'INCOMPLETE'

/**
 * 业务模式决策逻辑：
 * - 任一答案为null → INCOMPLETE
 * - q5=true → FVTPL (持有以获取公允价值变动)
 * - q3=true → FVTPL (出售频繁且金额重大)
 * - q4=true → FVOCI (同时以收取现金流和出售为目标)
 * - q1=true && q2=false → AC (以收取合同现金流量为目标，且无出售活动)
 * - else → FVTPL
 */
export function determineBusinessModel(answers: BusinessModelAnswers): BusinessModelResult {
  const { q1, q2, q3, q4, q5 } = answers

  // 任一答案为null/undefined → INCOMPLETE
  if (q1 === null || q1 === undefined ||
      q2 === null || q2 === undefined ||
      q3 === null || q3 === undefined ||
      q4 === null || q4 === undefined ||
      q5 === null || q5 === undefined) {
    return 'INCOMPLETE'
  }

  // q5=true → FVTPL（持有以获取公允价值变动）
  if (q5) return 'FVTPL'
  // q3=true → FVTPL（出售频繁且金额重大）
  if (q3) return 'FVTPL'
  // q4=true → FVOCI（同时以收取现金流和出售为目标）
  if (q4) return 'FVOCI'
  // q1=true && q2=false → AC（以收取合同现金流量为目标，无出售活动）
  if (q1 && !q2) return 'AC'
  // else → FVTPL
  return 'FVTPL'
}

// ══════════════════════════════════════════════════════════
// 决策函数2: SPPI结论推导（4布尔→结论）
// ══════════════════════════════════════════════════════════

export type SPPIResult = 'PASS' | 'FAIL' | 'FURTHER_ANALYSIS'

/**
 * SPPI测试结论推导：
 * - hasEquityConversion=true OR hasLeverage=true → FAIL
 * - 全部为false → PASS
 * - 仅有earlyRedemption/extension → FURTHER_ANALYSIS
 */
export function determineSPPIConclusion(
  hasEarlyRedemption: boolean,
  hasExtension: boolean,
  hasEquityConversion: boolean,
  hasLeverage: boolean,
): SPPIResult {
  // 权益转换或杠杆 → 必FAIL
  if (hasEquityConversion || hasLeverage) return 'FAIL'
  // 仅提前回售或展期 → 需进一步分析
  if (hasEarlyRedemption || hasExtension) return 'FURTHER_ANALYSIS'
  // 全false → PASS
  return 'PASS'
}

// ══════════════════════════════════════════════════════════
// 公式1: 盘点总计 = 面值 × 数量（2dp）
// ══════════════════════════════════════════════════════════

/**
 * 计算盘点总计金额：面值 × 数量，保留2位小数
 */
export function calcInventoryTotal(faceValue: number, quantity: number): number {
  return Math.round(parseNum(faceValue) * parseNum(quantity) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 公式2: 报表日数量 = 盘点日数量 + 增减数量
// ══════════════════════════════════════════════════════════

/**
 * 计算报表日数量：盘点日数量 + 增减变动
 */
export function calcReportDateQuantity(countDateQty: number, change: number): number {
  return parseNum(countDateQty) + parseNum(change)
}

// ══════════════════════════════════════════════════════════
// 公式3: 报表日总计 = 报表日面值 × 报表日数量（2dp）
// ══════════════════════════════════════════════════════════

/**
 * 计算报表日总计金额：面值 × 数量，保留2位小数
 */
export function calcReportDateTotal(reportFaceValue: number, reportQuantity: number): number {
  return Math.round(parseNum(reportFaceValue) * parseNum(reportQuantity) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 公式4: 差异 = 报表日总计 - 账面结存总计（2dp）
// ══════════════════════════════════════════════════════════

/**
 * 计算倒轧差异：报表日总计 - 账面结存总计，保留2位小数
 */
export function calcReconciliationVariance(reportDateTotal: number, bookTotal: number): number {
  return Math.round((parseNum(reportDateTotal) - parseNum(bookTotal)) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 公式5: 倒轧平衡判定 — |差异| < 0.01
// ══════════════════════════════════════════════════════════

/**
 * 判断倒轧是否平衡：报表日总计与账面总计差异绝对值 < 0.01
 */
export function isReconciliationBalanced(reportDateTotal: number, bookTotal: number): boolean {
  return Math.abs(parseNum(reportDateTotal) - parseNum(bookTotal)) < 0.01
}

// ══════════════════════════════════════════════════════════
// 公式6: 合计行求和（数组元素之和）
// ══════════════════════════════════════════════════════════

/**
 * 对数组求和，每个元素通过parseNum清洗
 */
export function calcSumColumn(values: number[]): number {
  if (!values || values.length === 0) return 0
  return values.reduce((sum, v) => sum + parseNum(v), 0)
}

// ══════════════════════════════════════════════════════════
// 组合判定: SPPI + 业务模式 → 最终金融资产分类
// ══════════════════════════════════════════════════════════

/**
 * 最终金融资产分类中文标签
 */
export const FINAL_CLASSIFICATION_LABELS: Record<string, string> = {
  AC: '以摊余成本计量的金融资产',
  FVOCI: '以公允价值计量且其变动计入其他综合收益的金融资产',
  FVTPL: '以公允价值计量且其变动计入当期损益的金融资产',
}

/**
 * 组合判定逻辑：
 * - SPPI不通过(FAIL) → 一律 FVTPL
 * - SPPI通过(PASS) + AC → AC
 * - SPPI通过(PASS) + FVOCI → FVOCI
 * - 其他情况（FURTHER_ANALYSIS 或 FVTPL） → FVTPL
 */
export function determineFinalClassification(
  businessModel: 'AC' | 'FVOCI' | 'FVTPL',
  sppiResult: SPPIResult,
): string {
  // SPPI不通过 → 一律FVTPL
  if (sppiResult === 'FAIL') return FINAL_CLASSIFICATION_LABELS.FVTPL

  // SPPI通过且业务模式为AC → AC
  if (sppiResult === 'PASS' && businessModel === 'AC') return FINAL_CLASSIFICATION_LABELS.AC

  // SPPI通过且业务模式为FVOCI → FVOCI
  if (sppiResult === 'PASS' && businessModel === 'FVOCI') return FINAL_CLASSIFICATION_LABELS.FVOCI

  // 其他情况（FURTHER_ANALYSIS 或 业务模式为FVTPL）→ FVTPL
  return FINAL_CLASSIFICATION_LABELS.FVTPL
}
