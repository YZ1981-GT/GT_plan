/**
 * useG0FormulaEngine — G0 投资循环函证公式引擎（纯函数，可 PBT 验证）
 *
 * 🔴🔴 差异方向 = **账面 − 回函**（源模板表头 `差异③=①-②`，①账面 / ②回函）
 *
 * spec: g0-confirmation-source-alignment，Task 20（Requirement 10.2 / Property 27）
 *
 * 三个差异函数原先实现为「回函 − 账面」= **照抄了源模板 M 列的缺陷方向**。逐条实证：
 *   · `函证差异核对表G0-3（证券投资）!K5` 表头逐字 `差异③=①-②`
 *     （`B5=账面结存证券投资①` / `H5=证券投资回函②`）
 *   · 同组 `K7=E7-H7`（数量）、`L7=F7-I7`（单价）→ 账面 − 回函 ✓
 *   · `M7=J7-G7`（公允价值）→ 回函 − 账面 ✗ = **源模板唯一反向者**（已登记
 *     `g0SourceDefects.G0_SOURCE_DEFECTS#securities-mv-diff-direction`）
 *   · 姊妹表 `函证差异核对表G0-4(非证券投资)` 的 `I7=C7-F7`、`J7=D7-G7` 亦为账面 − 回函，
 *     且平台侧 `useG0DiffNonSecurities.recalcRow` 早已实现为 `booked − reply`
 *     → 纠正前**两张差异表方向互相矛盾**。
 *
 * 归档 spec 的取舍已明确：`g0-confirmation`（早期）需求 2.5/2.6/2.7 写「回函 − 账面」且把列序
 * 也读成「回函在前」；`g0-investment-diff-model`（后期）定「数值维度差异 = 账面 − 回函
 * （符号与口径固定）」但只在非证券表落地 → 证券表是早期误读的未修遗留，非深思决定。
 *
 * 🔴 形参顺序随之改为 `(booked, reply)`（账面在前，与源模板列序 ①② 一致）。调用方只有
 * `diffSecurities/composables/useDiffSecuritiesData.ts#recalcRow` 一处，已同步。
 * 派生值在 `initFromHtmlData` 读回时重算（`recalcRow`）→ 既有项目数据**无需迁移**，
 * 打开即按新方向显示；下游全部走 `Math.abs`（`hasDifference` / `metrics` / 推送阈值），
 * 符号翻转不影响差异判定与汇总。
 */

/** 数量差异 = 账面数量 − 回函数量（源 `K=E−H`） */
export function calcQuantityDiff(bookedQty: number, replyQty: number): number {
  return bookedQty - replyQty
}

/** 市价（单价）差异 = 账面单价 − 回函单价（源 `L=F−I`） */
export function calcFairValueDiff(bookedFV: number, replyFV: number): number {
  return bookedFV - replyFV
}

/**
 * 公允价值差异 = 账面余额 − 回函公允价值。
 * 源 `M=J−G` 方向写反（缺陷），此处按表头 `③=①−②` 与同组 K/L 的意图统一。
 */
export function calcMarketValueDiff(bookedMV: number, replyMV: number): number {
  return bookedMV - replyMV
}

export function calcDisposalGain(proceeds: number, cost: number, fee: number): number {
  const safeFee = fee < 0 ? 0 : fee
  return Math.round((proceeds - cost - safeFee) * 100) / 100
}

export function calcDividendDiff(declared: number, received: number, tax: number): number {
  return Math.round((declared - received - tax) * 100) / 100
}

export function hasDifference(qtyDiff: number, fvDiff: number): boolean {
  return Math.abs(qtyDiff) > 0 || Math.abs(fvDiff) > 0.01
}
