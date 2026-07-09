/**
 * useN2MultiTaxEngine — N2 多税种测算引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 覆盖：城建税及附加 / 房产税（从价+从租）/ 土地增值税
 *
 * ─── 多税种测算逻辑 ───
 * 城建税:       (增值税+消费税) × 7%/5%/1%（市区/县城/其他）
 * 教育费附加:   (增值税+消费税) × 3%
 * 地方教育附加: (增值税+消费税) × 2%
 * 房产税从价:   原值 × (1 - 扣除比例) × 1.2%
 * 房产税从租:   租金收入 × 12%
 * 土地增值税:   增值额 × 税率 - 扣除项目 × 速算扣除系数
 *   四级累进: ≤50% → 30%/0%  |  50%~100% → 40%/5%
 *             100%~200% → 50%/15%  |  >200% → 60%/35%
 * 增值率:     增值额 / 扣除项目（deductItems=0 → return 0）
 * ─────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P5: 城建税及附加 = (增值税+消费税)×税率
 * - P6: 房产税从价 = 原值×(1-扣除比例)×1.2%
 * - P7: 土地增值税 = 增值额×税率 - 扣除项目×速算扣除系数
 * - P9: 增值率 = 增值额 / 扣除项目
 *
 * Spec: .kiro/specs/n2-taxes-payable/ Task 2.3
 * Requirements: 5.2, 6.2, 7.2, 7.4
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P5: 城建税及附加 ──────────────────────────────────────

/**
 * 计算城建税及附加（Property P5）
 *
 * 公式：城建税/教育费附加/地方教育附加 = (增值税 + 消费税) × 适用税率
 *
 * 适用税率：
 * - 城市维护建设税：市区 7% / 县城、镇 5% / 其他 1%
 * - 教育费附加：3%
 * - 地方教育附加：2%
 *
 * 来源：N2-8 其他税费测算表，计税依据取自 N2-6 增值税测算
 * 法规依据：《城市维护建设税法》《征收教育费附加的暂行规定》
 *
 * @param vat - 增值税（实际缴纳额，来自 N2-6 测算结果）
 * @param consumptionTax - 消费税（实际缴纳额）
 * @param rate - 适用税率（城建税 0.07/0.05/0.01；教育费附加 0.03；地方教育附加 0.02）
 * @returns 应交附加税额
 */
export function calcSurtax(vat: number, consumptionTax: number, rate: number): number {
  return (safe(vat) + safe(consumptionTax)) * safe(rate)
}

// ─── P6: 房产税从价 ────────────────────────────────────────

/**
 * 计算房产税从价计征（Property P6）
 *
 * 公式：应交房产税 = 房产原值 × (1 - 扣除比例) × 1.2%
 *
 * 扣除比例由各省/自治区/直辖市确定，一般为 10%~30%（即 0.10~0.30）。
 * 常见：北京30%、上海20%~30%、广东20%、浙江30%。
 *
 * 来源：N2-9 房产税测算表
 * 法规依据：《房产税暂行条例》第三条、第四条
 *
 * @param originalValue - 房产原值（原始购置价或重置完全价值）
 * @param deductRate - 扣除比例（0.10~0.30，各省规定）
 * @returns 年应交房产税（从价计征）
 */
export function calcPropertyTaxByValue(originalValue: number, deductRate: number): number {
  return safe(originalValue) * (1 - safe(deductRate)) * 0.012
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
 * 来源：N2-9 房产税测算表
 * 法规依据：《房产税暂行条例》第四条
 *
 * @param rentIncome - 年租金收入
 * @returns 年应交房产税（从租计征）
 */
export function calcPropertyTaxByRent(rentIncome: number): number {
  return safe(rentIncome) * 0.12
}

// ─── P7: 土地增值税 ────────────────────────────────────────

/**
 * 计算土地增值税（Property P7）
 *
 * 公式：应交土增税 = 增值额 × 适用税率 - 扣除项目金额 × 速算扣除系数
 *
 * 四级超率累进税率：
 * | 增值率        | 税率 | 速算扣除系数 |
 * |--------------|------|------------|
 * | ≤50%         | 30%  | 0%         |
 * | 50%~100%     | 40%  | 5%         |
 * | 100%~200%    | 50%  | 15%        |
 * | >200%        | 60%  | 35%        |
 *
 * 增值率 = 增值额 / 扣除项目金额
 * 增值额 = 转让房地产收入 - 扣除项目金额
 *
 * ⚠️ 本函数接收已确定的税率和速算扣除系数（由调用方根据增值率匹配）。
 * 完整流程：先调 calcAppreciationRate → 匹配税率档次 → 再调本函数。
 *
 * 来源：N2-10 土地增值税测算表
 * 法规依据：《土地增值税暂行条例》第七条
 *
 * @param appreciation - 增值额（转让收入 - 扣除项目金额）
 * @param taxRate - 适用税率（0.30/0.40/0.50/0.60）
 * @param deductItems - 扣除项目金额合计
 * @param quickDeductCoef - 速算扣除系数（0/0.05/0.15/0.35）
 * @returns 应交土地增值税
 */
export function calcLandVat(
  appreciation: number,
  taxRate: number,
  deductItems: number,
  quickDeductCoef: number,
): number {
  return safe(appreciation) * safe(taxRate) - safe(deductItems) * safe(quickDeductCoef)
}

// ─── P9: 增值率 ────────────────────────────────────────────

/**
 * 计算土地增值税增值率（Property P9）
 *
 * 公式：增值率 = 增值额 / 扣除项目金额
 *
 * 增值率用于匹配四级超率累进税率档次：
 * - ≤50%    → 税率30%，速算扣除系数0%
 * - 50%~100% → 税率40%，速算扣除系数5%
 * - 100%~200% → 税率50%，速算扣除系数15%
 * - >200%   → 税率60%，速算扣除系数35%
 *
 * ⚠️ 当扣除项目金额为0时返回0（避免除零错误）。
 *
 * 来源：N2-10 土地增值税测算表
 * 法规依据：《土地增值税暂行条例实施细则》第十条
 *
 * @param appreciation - 增值额（转让收入 - 扣除项目金额）
 * @param deductItems - 扣除项目金额合计（分母，=0时返回0）
 * @returns 增值率（如 0.45 表示 45%）
 */
export function calcAppreciationRate(appreciation: number, deductItems: number): number {
  const d = safe(deductItems)
  if (d === 0) return 0
  return safe(appreciation) / d
}
