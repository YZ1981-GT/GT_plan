/**
 * useN4MultiTaxEngine — N4 多税种测算引擎（纯函数，与N2同源）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 各税种计税公式，与N2应交税费的useN2MultiTaxEngine同源复用。
 * N4侧用于"费用确认"金额验证：费用确认 = N2计提额。
 *
 * ─── 多税种测算逻辑（与N2同源） ───
 * 城建税:       (增值税+消费税) × 7%/5%/1%（市区/县城/其他）
 * 教育费附加:   (增值税+消费税) × 3%
 * 地方教育附加: (增值税+消费税) × 2%
 * 房产税从价:   原值 × (1 - 扣除比例) × 1.2%
 * 房产税从租:   租金收入 × 12%
 * 印花税:       计税金额 × 适用税率（按合同类型：购销0.3‰/租赁1‰/借款0.05‰等）
 * 土地使用税:   占地面积 × 单位税额
 * ─────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P4: 城建税及附加 = (增值税+消费税)×税率
 * - P5: 房产税从价 = 原值×(1-扣除比例)×1.2%
 * - P6: 印花税 = 计税金额×适用税率
 * - 房产税从租 = 租金收入×12%
 * - 土地使用税 = 占地面积×单位税额
 * - 费用确认差异 = N4费用确认额 - N2计提额
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/ Task 2.2
 * Requirements: 4.1-4.5
 *
 * Correctness Properties:
 * CP-N4-P4: calcSurtax(vat, ct, rate) === (vat + ct) × rate
 * CP-N4-P5: calcPropertyTaxByValue(ov, dr) === ov × (1 - dr) × 0.012
 * CP-N4-P6: calcStampTax(amt, rate) === amt × rate
 */

import { parseNum } from './useN4FormulaEngine'

// ─── CP-N4-P4: 城建税及附加 ────────────────────────────────

/**
 * 计算城建税及附加（Property P4）
 *
 * 公式：城建税/教育费附加/地方教育附加 = (增值税 + 消费税) × 适用税率
 *
 * 适用税率：
 * - 城市维护建设税：市区 7% / 县城、镇 5% / 其他地区 1%
 * - 教育费附加：3%
 * - 地方教育附加：2%
 *
 * N4侧用途：验证税金及附加费用确认与N2计提额一致。
 * 计税依据（增值税+消费税）取自N2应交税费测算结果。
 *
 * 法规依据：《城市维护建设税法》《征收教育费附加的暂行规定》
 *
 * @param vat - 增值税（实际缴纳额，来自N2测算结果）
 * @param consumptionTax - 消费税（实际缴纳额）
 * @param rate - 适用税率（城建税 0.07/0.05/0.01；教育费附加 0.03；地方教育附加 0.02）
 * @returns 应交附加税额（即N4应确认费用额）
 *
 * Validates: Requirements 4.1
 */
export function calcSurtax(vat: number, consumptionTax: number, rate: number): number {
  return (parseNum(vat) + parseNum(consumptionTax)) * parseNum(rate)
}

// ─── CP-N4-P5: 房产税从价 ──────────────────────────────────

/**
 * 计算房产税从价计征（Property P5）
 *
 * 公式：应交房产税 = 房产原值 × (1 - 扣除比例) × 1.2%
 *
 * 扣除比例由各省/自治区/直辖市确定，一般为 10%~30%（即 0.10~0.30）。
 * 常见：北京30%、上海20%~30%、广东20%、浙江30%。
 *
 * N4侧用途：验证房产税费用确认额=N2从价计征计提额。
 *
 * 法规依据：《房产税暂行条例》第三条、第四条
 *
 * @param originalValue - 房产原值（原始购置价或重置完全价值）
 * @param deductRate - 扣除比例（0.10~0.30，各省规定）
 * @returns 年应交房产税（从价计征，即N4应确认费用额）
 *
 * Validates: Requirements 4.2
 */
export function calcPropertyTaxByValue(originalValue: number, deductRate: number): number {
  return parseNum(originalValue) * (1 - parseNum(deductRate)) * 0.012
}

// ─── 房产税从租 ────────────────────────────────────────────

/**
 * 计算房产税从租计征
 *
 * 公式：应交房产税 = 租金收入 × 12%
 *
 * 适用于出租房产的情形。
 * 特殊：个人出租住房减按 4%（本函数使用标准企业税率 12%）。
 *
 * N4侧用途：验证从租房产税费用确认额=N2从租计征计提额。
 *
 * 法规依据：《房产税暂行条例》第四条
 *
 * @param rentIncome - 年租金收入
 * @returns 年应交房产税（从租计征）
 *
 * Validates: Requirements 4.2
 */
export function calcPropertyTaxByRent(rentIncome: number): number {
  return parseNum(rentIncome) * 0.12
}

// ─── CP-N4-P6: 印花税 ──────────────────────────────────────

/**
 * 计算印花税（Property P6）
 *
 * 公式：应交印花税 = 计税金额 × 适用税率
 *
 * 常见合同类型及税率（2022年7月《印花税法》实施后）：
 * - 买卖合同：价款的 0.3‰ (0.0003)
 * - 租赁合同：租金的 1‰ (0.001)
 * - 借款合同：借款金额的 0.05‰ (0.00005)
 * - 技术合同：价款/报酬的 0.3‰ (0.0003)
 * - 产权转移书据：价款的 0.5‰ (0.0005)
 * - 营业账簿：实收资本+资本公积的 0.25‰ (0.00025)
 *
 * N4侧用途：验证印花税费用确认额=N2计提额。
 * 计税金额取自对应合同/凭证金额。
 *
 * 法规依据：《印花税法》（2022年7月1日起施行）
 *
 * @param taxableAmount - 计税金额（合同金额/凭证金额等）
 * @param rate - 适用税率（如 0.0003/0.001/0.00005 等）
 * @returns 应交印花税（即N4应确认费用额）
 *
 * Validates: Requirements 4.3
 */
export function calcStampTax(taxableAmount: number, rate: number): number {
  return parseNum(taxableAmount) * parseNum(rate)
}

// ─── 土地使用税 ────────────────────────────────────────────

/**
 * 计算城镇土地使用税
 *
 * 公式：应交土地使用税 = 占地面积(㎡) × 单位税额(元/㎡)
 *
 * 单位税额按土地等级确定（从高到低）：
 * - 大城市：1.5~30 元/㎡
 * - 中等城市：1.2~24 元/㎡
 * - 小城市：0.9~18 元/㎡
 * - 县城/建制镇/工矿区：0.6~12 元/㎡
 *
 * N4侧用途：验证土地使用税费用确认额=N2计提额。
 *
 * 法规依据：《城镇土地使用税暂行条例》第四条、第五条
 *
 * @param area - 实际占用土地面积（平方米）
 * @param unitTax - 适用单位税额（元/平方米，由税务机关核定）
 * @returns 年应交土地使用税（即N4应确认费用额）
 *
 * Validates: Requirements 4.4
 */
export function calcLandUseTax(area: number, unitTax: number): number {
  return parseNum(area) * parseNum(unitTax)
}

// ─── 费用确认差异（N4 vs N2） ──────────────────────────────

/**
 * 计算费用确认差异
 *
 * 差异 = N4费用确认额 - N2计提额
 *
 * N4税金及附加（费用确认）应等于N2应交税费（本期计提额）。
 * 差异不为零时说明费用确认与计提不一致，需审计关注。
 *
 * 用途：
 * - N4-2明细表"差异"列
 * - N4 vs N2交叉验证红色差异标红
 *
 * @param expenseRecognized - N4本期费用确认额（税金及附加发生额）
 * @param accrualFromN2 - N2本期应交税费计提额（来自'tax-accrual:updated'事件）
 * @returns 差异金额（正=费用>计提，负=费用<计提，0=一致）
 *
 * Validates: Requirements 4.5, 6.3
 */
export function calcExpenseDiff(expenseRecognized: number, accrualFromN2: number): number {
  return parseNum(expenseRecognized) - parseNum(accrualFromN2)
}
