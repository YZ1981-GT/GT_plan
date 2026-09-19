/**
 * useJ2ActuarialEngine — J2 设定受益计划 精算纯函数引擎
 *
 * 核心公式（CAS9 / IAS19 设定受益计划精算计量）：
 *   DBO期末 = DBO期初 + 当期服务成本 + 利息费用 + 精算损失 - 精算利得 - 已支付福利
 *   净负债 = DBO现值 - 计划资产公允价值
 *   利息成本 = 期初DBO × 折现率
 *   精算损益(OCI) = 精算假设变动引起的DBO变动
 *
 * 精算假设范围校验（审计实务ISA620合规）：
 *   折现率: 通常 2%~8%（参照国债到期收益率）
 *   薪酬增长率: 通常 3%~15%
 *   死亡率: 通常 0.01%~5%
 *   离职率: 通常 1%~30%
 *
 * 所有函数为纯函数，无副作用，便于 PBT 验证数学正确性。
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 4.1-4.6
 */

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface ActuarialAssumptions {
  discountRate: number       // 折现率（如 0.04 表示 4%）
  salaryGrowthRate: number   // 薪酬增长率（如 0.08 表示 8%）
  mortalityRate: number      // 死亡率（如 0.005 表示 0.5%）
  turnoverRate: number       // 离职率（如 0.10 表示 10%）
}

export interface AssumptionValidation {
  isValid: boolean
  warnings: string[]
}

export interface SensitivityResult {
  baseValue: number
  increasedValue: number     // 假设+50bp时DBO
  decreasedValue: number     // 假设-50bp时DBO
  increaseImpact: number     // 增加对DBO的影响额
  decreaseImpact: number     // 减少对DBO的影响额
}

// ─── DBO期末完整公式 ─────────────────────────────────────────────────────────

/**
 * DBO期末 = 期初 + 当期服务成本 + 利息费用 + 精算损失 - 精算利得 - 已支付福利
 *
 * CAS9: 设定受益义务现值的变动来源六要素分解。
 * 精算损失增加DBO，精算利得减少DBO。
 *
 * @param beginDBO 期初DBO现值 (≥0)
 * @param serviceCost 当期服务成本 (≥0)
 * @param interestCost 利息费用 (≥0)
 * @param actuarialLoss 精算损失（假设变动导致DBO增加） (≥0)
 * @param actuarialGain 精算利得（假设变动导致DBO减少） (≥0)
 * @param benefitsPaid 已支付福利 (≥0)
 * @returns DBO期末现值
 */
export function calcEndDBO(
  beginDBO: number,
  serviceCost: number,
  interestCost: number,
  actuarialLoss: number,
  actuarialGain: number,
  benefitsPaid: number,
): number {
  return beginDBO + serviceCost + interestCost + actuarialLoss - actuarialGain - benefitsPaid
}

// ─── 利息成本 ────────────────────────────────────────────────────────────────

/**
 * 利息成本 = 期初DBO × 折现率
 *
 * CAS9/IAS19: 利息费用反映设定受益义务因时间流逝的展开（unwinding）。
 * 折现率应参照高质量企业债券/国债到期收益率。
 *
 * @param beginDBO 期初DBO现值
 * @param discountRate 折现率（小数形式，如 0.04 = 4%）
 * @returns 利息费用
 */
export function calcInterestCost(beginDBO: number, discountRate: number): number {
  return beginDBO * discountRate
}

// ─── 净负债 ──────────────────────────────────────────────────────────────────

/**
 * 净负债(资产) = DBO现值 - 计划资产公允价值
 *
 * CAS9: 设定受益计划净负债=设定受益义务现值-计划资产公允价值。
 * 正值=净负债（列报在负债）；负值=净资产（列报在资产，受资产上限约束）。
 *
 * @param dbo DBO现值
 * @param planAssetsFV 计划资产公允价值
 * @returns 净负债（正值）或净资产（负值）
 */
export function calcNetLiability(dbo: number, planAssetsFV: number): number {
  return dbo - planAssetsFV
}

// ─── 精算损益 ────────────────────────────────────────────────────────────────

/**
 * 精算损益 = 实际DBO - 预期DBO
 *
 * 精算假设变动（折现率/薪酬增长/死亡率/离职率）导致DBO偏离预期。
 * 正值=精算损失（DBO超出预期）；负值=精算利得（DBO低于预期）。
 * CAS9规定精算损益计入OCI（其他综合收益），不得转损益。
 *
 * @param actualDBO 实际DBO（按新假设计算）
 * @param expectedDBO 预期DBO（按旧假设计算）
 * @returns 精算损益（正=损失，负=利得）
 */
export function calcActuarialGainLoss(actualDBO: number, expectedDBO: number): number {
  return actualDBO - expectedDBO
}

// ─── 精算假设范围校验 ────────────────────────────────────────────────────────

/**
 * 精算假设合理性校验（ISA620 专家利用合规）
 *
 * 审计实务中需评估精算假设是否在合理区间：
 * - 折现率: [0.02, 0.08]（2%~8%，参照国债/高质量企业债）
 * - 薪酬增长率: [0.03, 0.15]（3%~15%，含通胀+晋升）
 * - 死亡率: [0.0001, 0.05]（0.01%~5%，依年龄段）
 * - 离职率: [0.01, 0.30]（1%~30%，依行业/岗位）
 *
 * 超出范围不一定invalid（审计师需进一步评估合理性说明），但需发出警告。
 *
 * @param assumptions 精算假设参数
 * @returns 校验结果（isValid + warnings数组）
 */
export function validateAssumptions(assumptions: ActuarialAssumptions): AssumptionValidation {
  const warnings: string[] = []
  let isValid = true

  // ── 折现率 ──
  if (assumptions.discountRate <= 0 || assumptions.discountRate >= 1) {
    warnings.push('折现率必须在(0, 100%)范围内')
    isValid = false
  } else {
    if (assumptions.discountRate < 0.02) {
      warnings.push('折现率低于2%，偏低（请核实国债收益率参照）')
    }
    if (assumptions.discountRate > 0.08) {
      warnings.push('折现率超过8%，偏高（请核实选取依据）')
    }
  }

  // ── 薪酬增长率 ──
  if (assumptions.salaryGrowthRate <= 0 || assumptions.salaryGrowthRate >= 1) {
    warnings.push('薪酬增长率必须在(0, 100%)范围内')
    isValid = false
  } else {
    if (assumptions.salaryGrowthRate < 0.03) {
      warnings.push('薪酬增长率低于3%，偏低')
    }
    if (assumptions.salaryGrowthRate > 0.15) {
      warnings.push('薪酬增长率超过15%，偏高')
    }
  }

  // ── 死亡率 ──
  if (assumptions.mortalityRate <= 0 || assumptions.mortalityRate >= 1) {
    warnings.push('死亡率必须在(0, 100%)范围内')
    isValid = false
  } else {
    if (assumptions.mortalityRate > 0.05) {
      warnings.push('死亡率超过5%，偏高（请核实生命表来源）')
    }
  }

  // ── 离职率 ──
  if (assumptions.turnoverRate <= 0 || assumptions.turnoverRate >= 1) {
    warnings.push('离职率必须在(0, 100%)范围内')
    isValid = false
  } else {
    if (assumptions.turnoverRate > 0.30) {
      warnings.push('离职率超过30%，偏高（请核实行业特征）')
    }
  }

  return { isValid, warnings }
}

// ─── 敏感性分析 ──────────────────────────────────────────────────────────────

/**
 * 折现率敏感性分析（±50bp）
 *
 * IAS19/CAS9要求披露主要精算假设变动对DBO的敏感性。
 * 标准做法：折现率±50bp，观察DBO变动幅度。
 *
 * 简化模型：DBO ≈ 年金现值系数 × 未来给付现值
 * 折现率↑ → DBO↓（负相关）
 * 使用 Modified Duration 近似：ΔDBO ≈ -DBO × Duration × Δr
 * 此处 Duration 简化为等待期加权平均（averageDuration）
 *
 * @param currentDBO 当前DBO
 * @param averageDuration 平均久期(年)
 * @param basisPoints 变动基点数（默认50bp=0.005）
 * @returns 敏感性分析结果
 */
export function calcSensitivity(
  currentDBO: number,
  averageDuration: number,
  basisPoints: number = 0.005,
): SensitivityResult {
  // 折现率↑ → DBO↓
  const increaseImpact = -currentDBO * averageDuration * basisPoints
  // 折现率↓ → DBO↑
  const decreaseImpact = currentDBO * averageDuration * basisPoints

  return {
    baseValue: currentDBO,
    increasedValue: currentDBO + increaseImpact,
    decreasedValue: currentDBO + decreaseImpact,
    increaseImpact,
    decreaseImpact,
  }
}
