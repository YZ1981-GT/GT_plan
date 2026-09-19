/**
 * useL8InterestEngine — L8 利息支出测算引擎（纯函数）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * ─── L8利息汇聚终点 ───
 * L8财务费用是L筹资循环的利息汇聚终点：
 * - L1 短期借款利息
 * - L3 长期借款利息
 * - L4 应付债券利息费用
 * - L5 未确认融资费用摊销
 * 全部汇聚到L8利息支出测算。
 * ─────────────────────
 *
 * 本引擎覆盖：
 * - 汇总各来源利息（L1/L3/L4/L5）
 * - 测算vs账面差异
 * - 可扣除利息（非金融机构，本金×基准利率×天数/360）
 * - 超标利息（账载-可扣除）
 *
 * Spec: .kiro/specs/l8-financial-expenses/ Task 2.2
 * Requirements: 4.5-4.6, 5.2-5.3, 8.5-8.6
 */

import { parseNum } from './useL8FormulaEngine'

// ─── 1. 汇总各来源利息 ─────────────────────────────────────

/**
 * 汇总各来源利息（Property P5）
 *
 * 汇聚L筹资循环全部利息来源：
 * - L1 短期借款利息测算
 * - L3 长期借款利息测算
 * - L4 应付债券利息费用
 * - L5 未确认融资费用摊销
 *
 * 来源：EventBus 订阅 'l1:interest-calculated' / 'l3:interest-calculated'
 *       / 'l4:interest-calculated' / 'l5:amortization-calculated'
 *
 * @param l1 - L1短期借款利息
 * @param l3 - L3长期借款利息
 * @param l4 - L4应付债券利息费用
 * @param l5 - L5未确认融资费用摊销
 * @returns 测算利息支出合计
 */
export function aggregateInterest(l1: number, l3: number, l4: number, l5: number): number {
  return parseNum(l1) + parseNum(l3) + parseNum(l4) + parseNum(l5)
}

// ─── 2. 测算vs账面差异 ─────────────────────────────────────

/**
 * 计算测算利息支出与账面利息支出的差异
 *
 * 差异 = 测算利息 - 账面利息
 * 正值表示测算大于账面（可能有利息未入账）
 * 负值表示账面大于测算（可能多计利息）
 *
 * 当 |差异| > 阈值时，前端红色高亮（Requirements 4.7）
 *
 * @param estimated - 测算利息支出合计（aggregateInterest结果）
 * @param booked - 账面利息支出（从L8-2明细/审定取）
 * @returns 差异金额
 */
export function calcInterestDiff(estimated: number, booked: number): number {
  return parseNum(estimated) - parseNum(booked)
}

// ─── 3. 可扣除利息（非金融机构） ────────────────────────────

/**
 * 计算可扣除利息（Property P6）
 *
 * 非金融机构借款利息税前扣除限额：
 *   可扣除利息 = 本金 × 同期金融机构基准利率 × 天数 / 360
 *
 * ⚠️ 使用360天制（税务扣除限额计算）
 * 注意与L3/L5的实际利息计算（365天制）不同！
 * 此处是税法规定的扣除上限，按同期金融机构利率×360天制计算。
 *
 * 来源：L8-4 非金融机构利息支出测算表
 * 依据：企业所得税法实施条例第38条
 *
 * @param principal - 借款本金
 * @param benchmarkRate - 同期金融机构基准利率（年化，如0.0435表示4.35%）
 * @param days - 借款天数
 * @returns 可扣除利息金额
 */
export function calcDeductibleInterest(principal: number, benchmarkRate: number, days: number): number {
  return parseNum(principal) * parseNum(benchmarkRate) * parseNum(days) / 360
}

// ─── 4. 超标利息 ────────────────────────────────────────────

/**
 * 计算超标利息（Property P7）
 *
 * 超标利息 = 账载利息 - 可扣除利息
 * 正值表示超过税前扣除限额，需做纳税调增（橙色提示）
 * 零或负值表示未超标，无需税务调整
 *
 * 来源：L8-4 非金融机构利息支出测算表
 *
 * @param booked - 账载利息（实际支付/计提利息）
 * @param deductible - 可扣除利息（calcDeductibleInterest结果）
 * @returns 超标利息金额
 */
export function calcExcessInterest(booked: number, deductible: number): number {
  return parseNum(booked) - parseNum(deductible)
}

// ─── 5. 超标判断 ────────────────────────────────────────────

/**
 * 判断是否存在超标利息（税务调整提示）
 *
 * @param excessAmount - calcExcessInterest 返回值
 * @returns true表示需要橙色高亮提示税务调整
 */
export function hasExcessInterest(excessAmount: number): boolean {
  return parseNum(excessAmount) > 0
}

// ─── 6. 差异是否超阈值 ──────────────────────────────────────

/**
 * 判断测算vs账面差异是否超阈值
 *
 * @param diff - calcInterestDiff 返回值
 * @param threshold - 阈值金额（绝对值）
 * @returns true表示差异超阈值，需红色高亮
 */
export function isInterestDiffExceeding(diff: number, threshold: number): boolean {
  return Math.abs(parseNum(diff)) > parseNum(threshold)
}
