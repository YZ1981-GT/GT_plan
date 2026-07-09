/**
 * I2 开发支出 — CAS6五条件资本化判断引擎（纯函数，无副作用）
 * 科目：1717开发支出（借方/资产类）
 *
 * CAS6第9条：企业内部研究开发项目的支出，应当区分研究阶段支出与开发阶段支出。
 * 开发阶段支出同时满足五条件时，才能确认为无形资产（资本化）。
 *
 * 五条件：
 *   ① 技术可行性（完成该无形资产使其能够使用或出售在技术上具有可行性）
 *   ② 完成意图（具有完成该无形资产并使用或出售的意图）
 *   ③ 使用或出售能力（无形资产产生经济利益的方式，能够证明运用该无形资产生产的产品存在市场或无形资产自身存在市场）
 *   ④ 未来经济利益（有足够的技术、财务资源和其他资源支持，以完成该无形资产的开发，并有能力使用或出售该无形资产）
 *   ⑤ 资源充足（归属于该无形资产开发阶段的支出能够可靠地计量）
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 */

// ---------- 类型定义 ----------

export interface CAS6Condition {
  id: 1 | 2 | 3 | 4 | 5
  name: string
  result: 'yes' | 'no' | 'na'
  evidence: string
}

export interface CapitalizationResult {
  isMet: boolean
  missingConditions: number[]
  conclusion: string
}

export interface ResearchSplitResult {
  isValid: boolean
  difference: number
}

// ---------- CAS6五条件名称常量 ----------

export const CAS6_CONDITION_NAMES: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: '技术可行性',
  2: '完成意图',
  3: '使用或出售能力',
  4: '未来经济利益',
  5: '资源充足',
}

// ---------- 核心函数 ----------

/**
 * 评估CAS6资本化五条件
 *
 * CAS6第9条规则：
 * - 五条件全部为"是"(yes) → isMet=true，结论"满足资本化条件"
 * - 任一条件为"否"(no) → isMet=false，结论列出缺失条件
 * - "不适用"(na) 不影响判断（忽略该条件）
 * - 全部为na或空数组 → isMet=false（无法在缺乏正面证据时确认资本化）
 *
 * @param conditions - CAS6五条件评估数组
 * @returns 评估结果（是否满足/缺失条件列表/中文结论）
 */
export function evaluateCapitalization(conditions: CAS6Condition[]): CapitalizationResult {
  // 空数组 → 无法资本化
  if (conditions.length === 0) {
    return {
      isMet: false,
      missingConditions: [],
      conclusion: '未填写任何条件，无法判断资本化',
    }
  }

  // 收集各类条件
  const yesConditions = conditions.filter(c => c.result === 'yes')
  const noConditions = conditions.filter(c => c.result === 'no')
  const naConditions = conditions.filter(c => c.result === 'na')

  // 所有条件均为na → 无正面证据，不能资本化
  if (naConditions.length === conditions.length) {
    return {
      isMet: false,
      missingConditions: [],
      conclusion: '所有条件均标记为不适用，无法确认资本化',
    }
  }

  // 任一条件为"否" → 不满足
  if (noConditions.length > 0) {
    const missingIds = noConditions.map(c => c.id).sort((a, b) => a - b)
    const missingNames = missingIds.map(id => `${CAS6_CONDITION_NAMES[id as 1 | 2 | 3 | 4 | 5]}`)
    return {
      isMet: false,
      missingConditions: missingIds,
      conclusion: `不满足资本化条件，缺失：${missingNames.join('、')}`,
    }
  }

  // 剩余情况：有至少一个yes，无no（其余可能是na）→ 满足
  if (yesConditions.length > 0) {
    return {
      isMet: true,
      missingConditions: [],
      conclusion: '满足资本化条件',
    }
  }

  // 不应到达此处，但防御性处理
  return {
    isMet: false,
    missingConditions: [],
    conclusion: '条件评估异常，请检查数据',
  }
}

// ---------- I6↔I2联动公式 ----------

/**
 * 研发总额 = I6费用化金额 + I2资本化金额
 * 用于I6↔I2双向校验 (VR-I6-01)
 *
 * @param expenseI6 - I6研发费用（费用化金额）
 * @param capitalizedI2 - I2开发支出（资本化金额）
 * @returns 研发总额
 */
export function calcResearchTotal(expenseI6: number, capitalizedI2: number): number {
  return expenseI6 + capitalizedI2
}

/**
 * 研发拆分有效性验证
 * 校验：费用化 + 资本化 = 研发总预算
 * 差额为0时有效，非0时拆分存在差异
 *
 * @param expenseI6 - I6费用化金额
 * @param capitalizedI2 - I2资本化金额
 * @param totalBudget - 研发总预算
 * @returns 验证结果（是否有效 + 差额）
 */
export function validateResearchSplit(
  expenseI6: number,
  capitalizedI2: number,
  totalBudget: number,
): ResearchSplitResult {
  const difference = totalBudget - (expenseI6 + capitalizedI2)
  const EPSILON = 1e-6
  return {
    isValid: Math.abs(difference) < EPSILON,
    difference,
  }
}
