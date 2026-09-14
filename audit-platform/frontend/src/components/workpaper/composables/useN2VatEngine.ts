/**
 * useN2VatEngine — N2 增值税测算引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2221-01 应交增值税（N2-6 增值税测算表核心）
 *
 * ─── 增值税核心公式 ───
 * 应交增值税 = 销项税额 - (进项税额 - 进项转出)
 *
 * 销项税额 = 销售额 × 适用税率
 *   - 一般纳税人常见税率：13%（货物/加工修理）、9%（建筑/交通/不动产）、6%（服务/无形资产）
 *   - 小规模纳税人：3%（减按1%等优惠政策）
 *
 * 进项税额 = 取得的增值税专用发票注明税额（可抵扣部分）
 * 进项转出 = 用于非应税项目/免税/简易/集体福利/个人消费等不得抵扣的进项
 *
 * 税负率 = 应交增值税 / 销售额（衡量实际税负水平，行业对标分析）
 * ─────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P3: 销项税额 = 销售额 × 税率
 * - P4: 应交增值税 = 销项 - (进项 - 进项转出)
 * - 税负率分析（应交增值税 / 销售额）
 *
 * Spec: .kiro/specs/n2-taxes-payable/ Task 2.2
 * Requirements: 4.2, 4.6
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 销项税额 ──────────────────────────────────────────

/**
 * 计算销项税额（Property P3）
 *
 * 销项税额 = 销售额 × 适用税率
 *
 * 来源：N2-6 增值税测算表
 * 一般纳税人按适用税率（13%/9%/6%）计算销项；
 * 含税销售额需先做价税分离：销售额 = 含税金额 / (1 + 税率)
 * 本函数接收的 salesAmount 为不含税销售额。
 *
 * @param salesAmount - 不含税销售额（≥0）
 * @param taxRate - 适用税率（如 0.13 / 0.09 / 0.06 / 0.03）
 * @returns 销项税额
 */
export function calcOutputVat(salesAmount: number, taxRate: number): number {
  return safe(salesAmount) * safe(taxRate)
}

// ─── P4: 应交增值税 ────────────────────────────────────────

/**
 * 计算应交增值税（Property P4）
 *
 * 应交增值税 = 销项税额 - (进项税额 - 进项转出)
 *
 * 来源：N2-6 增值税测算表核心公式
 *
 * 逻辑说明：
 * - 销项税额：向下游收取的增值税（销售行为产生）
 * - 进项税额：从上游取得的可抵扣增值税（采购行为产生）
 * - 进项转出：原已抵扣但因用途变更(非应税/免税/福利等)需转出不得抵扣的进项
 * - 净进项 = 进项税额 - 进项转出（实际可抵扣额）
 * - 应交 = 销项 - 净进项
 *
 * ⚠️ 结果可能为负（留抵税额），表示当期进项大于销项，
 *    留抵税额可结转下期抵扣，不计为当期应缴纳。
 *
 * @param outputVat - 销项税额
 * @param inputVat - 进项税额（可抵扣）
 * @param inputTransferOut - 进项转出（不得抵扣部分）
 * @returns 应交增值税（负值为留抵）
 */
export function calcPayableVat(outputVat: number, inputVat: number, inputTransferOut: number): number {
  return safe(outputVat) - (safe(inputVat) - safe(inputTransferOut))
}

// ─── 增值税税负率 ──────────────────────────────────────────

/**
 * 计算增值税税负率
 *
 * 税负率 = 应交增值税 / 销售额
 *
 * 来源：N2-6 增值税测算表（税负率分析列）
 *
 * 用途：
 * - 与行业平均税负率对比，判断是否存在异常（税负率过低可能隐瞒收入或虚抵进项）
 * - 与申报表税负率核对一致性
 * - 作为审计分析性程序的关键指标
 *
 * ⚠️ 当销售额为 0 时返回 0（避免除零错误），
 *    此时审计人员需关注是否有实际业务但未确认收入。
 *
 * @param payableVat - 应交增值税
 * @param salesAmount - 销售额（分母）
 * @returns 税负率（如 0.05 表示 5%），销售额为 0 时返回 0
 */
export function calcVatBurdenRate(payableVat: number, salesAmount: number): number {
  const s = safe(salesAmount)
  if (s === 0) return 0
  return safe(payableVat) / s
}
