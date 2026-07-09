/**
 * H2 在建工程 — 公式引擎（纯函数，无副作用）
 * 科目：1604在建工程（借方/资产类）
 * 核心特征：三角勾稽期末=期初+增加-减少-转固（比H1多"转固"扣减维度）
 * Spec: .kiro/specs/h2-construction-in-progress/
 */

// ---------- 基础公式 ----------

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末余额（借方科目1604）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/** 在建工程期末余额：期末 = 期初 + 增加 - 减少 - 转固 */
export function calcCipEndBalance(begin: number, increase: number, decrease: number, transfer: number): number {
  return begin + increase - decrease - transfer
}

/**
 * 三角勾稽校验（含转固扣减）：
 * 差额 = 期末 - (期初 + 增加 - 减少 - 转固)
 * 返回0表示勾稽平衡，非0表示存在差异
 */
export function calcTriangleWithTransfer(
  begin: number,
  increase: number,
  decrease: number,
  transfer: number,
  end: number,
): number {
  return end - (begin + increase - decrease - transfer)
}

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

// ---------- 分析公式 ----------

/** 完工率(%) = 累计投入 / 预算 × 100；预算为0时返回null */
export function calcCompletionRate(accumulated: number, budget: number): number | null {
  if (budget === 0) return null
  return (accumulated / budget) * 100
}

/** 超预算率(%) = (实际 - 预算) / 预算 × 100；预算为0时返回null */
export function calcOverBudgetRate(actual: number, budget: number): number | null {
  if (budget === 0) return null
  return ((actual - budget) / budget) * 100
}

/** 造价差异率(%) = (实际 - 预算) / 预算 × 100；预算为0时返回null */
export function calcCostDiffRate(actual: number, budget: number): number | null {
  if (budget === 0) return null
  return ((actual - budget) / budget) * 100
}

// ---------- 工期公式 ----------

/**
 * 工期超期天数 = 实际日期 - 计划日期（天数差）
 * 若实际 ≤ 计划则返回0（不存在超期）
 * 日期格式：YYYY-MM-DD 或任何可被 Date.parse 解析的字符串
 */
export function calcOverdueDays(actualDate: string, plannedDate: string): number {
  const actual = new Date(actualDate)
  const planned = new Date(plannedDate)
  const diffMs = actual.getTime() - planned.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  return diffDays >= 0 ? diffDays : 0
}

// ---------- 转固条件判定 ----------

/**
 * CAS4转固五条件全满足判定
 * conditions数组长度应为5（实体建造完成/达到设计要求/试运转合格/竣工决算已办或可确定/已投入使用或可使用）
 * 全部为true时返回true
 */
export function calcTransferCondition(conditions: boolean[]): boolean {
  return conditions.every(c => c === true)
}

// ---------- 借贷平衡 ----------

/**
 * 借贷平衡检查
 * 比较借方合计与贷方合计，使用小epsilon容差处理浮点精度
 * 返回true表示平衡
 */
export function isBalanced(entries: { debit: number; credit: number }[]): boolean {
  const totalDebit = entries.reduce((sum, e) => sum + e.debit, 0)
  const totalCredit = entries.reduce((sum, e) => sum + e.credit, 0)
  const EPSILON = 1e-6
  return Math.abs(totalDebit - totalCredit) < EPSILON
}
