/**
 * 度量类型枚举与显示规则
 *
 * 七类 measure kind 的枚举定义和 RatioScale 枚举，用于跨层格式化统一。
 */

/**
 * 度量类型（七类）
 *
 * 用于统一前后端的数值格式化规则。各类型的显示规则见 formatMeasure 函数和 GtMeasureCell 组件。
 */
export enum MeasureKind {
  AMOUNT = 'amount',             // 金额：按项目金额单位和账号小数位格式化
  RATIO = 'ratio',               // 比例：固定2位小数 + %，根据 RatioScale 确定是否需要 ×100
  COUNT = 'count',               // 计数：0位小数，整数
  QUANTITY = 'quantity',         // 数量：原值有效小数位（最多6位）
  EXCHANGE_RATE = 'exchange_rate',  // 汇率：原值有效小数位（最多6位）
  UNIT_PRICE = 'unit_price',     // 单价：原值有效小数位（最多6位）
  TEXT = 'text'                  // 文本：原样输出，不做数值格式化
}

/**
 * 比例刻度类型
 *
 * 仅用于 ratio kind，决定原值如何转换为百分比显示：
 * - fraction: 原值是小数（如 0.2 表示 20%），显示时 ×100
 * - percent_points: 原值已是百分点（如 20 表示 20%），显示时不变
 *
 * 两种情况的除数（divisor）均为 1。
 */
export enum RatioScale {
  FRACTION = 'fraction',             // 小数形式：0.2 → 20.00%
  PERCENT_POINTS = 'percent_points'  // 百分点形式：20 → 20.00%
}

/**
 * 校验 ratio_scale 仅在 kind=ratio 时出现
 *
 * @param kind - 度量类型
 * @param ratioScale - 比例刻度（可选）
 * @throws {Error} 当 kind=ratio 时缺少 ratioScale，或其他 kind 带有 ratioScale
 */
export function validateRatioScale(
  kind: MeasureKind | null | undefined,
  ratioScale: RatioScale | null | undefined
): void {
  if (kind === MeasureKind.RATIO && ratioScale == null) {
    throw new Error('ratio kind 必须传递 ratioScale');
  }
  if (kind != null && kind !== MeasureKind.RATIO && ratioScale != null) {
    throw new Error(`${kind} kind 禁止传递 ratioScale`);
  }
}
