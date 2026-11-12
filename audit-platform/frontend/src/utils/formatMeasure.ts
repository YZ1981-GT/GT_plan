/**
 * 度量值格式化工具
 *
 * 按照 design §17 G4 的逐 kind 显示规则格式化各类度量值。
 */
import { Decimal } from 'decimal.js';
import { MeasureKind, RatioScale } from '@/types/measureKind';
import { useDisplayPrefsStore } from '@/stores/displayPrefs';

export interface FormatMeasureOptions {
  /** 度量类型 */
  kind?: MeasureKind | null;
  /** 比例刻度（仅 ratio 时必须） */
  ratioScale?: RatioScale | null;
  /** 账号小数位（amount 和未登记类型使用） */
  decimals?: number;
  /** 是否显示零值（默认：根据偏好设置） */
  showZero?: boolean;
  /** 负数是否显示为红色（默认：false，由组件处理样式） */
  negativeRed?: boolean;
}

/**
 * 格式化度量值
 *
 * 按照 design §17 G4 的规则：
 * - amount: 按金额单位和账号小数位格式化
 * - ratio: 固定2位小数 + %，fraction 先 ×100
 * - count: 0位小数（原值带小数时按 quantity 规则）
 * - quantity/exchange_rate/unit_price: 原值有效小数位（最多6位）
 * - text: 原样输出
 * - 未登记: 按元口径格式化
 *
 * @param value - 原始值
 * @param options - 格式化选项
 * @returns 格式化后的字符串
 */
export function formatMeasure(
  value: number | string | null | undefined,
  options: FormatMeasureOptions = {}
): string {
  // 处理空值
  if (value == null || value === '') {
    const { showZero = true } = options;
    if (showZero) {
      // 根据 kind 决定零值格式
      if (options.kind === MeasureKind.RATIO) {
        return '0.00%';
      } else if (options.kind === MeasureKind.COUNT) {
        return '0';
      }
      // amount 和其他类型使用账号小数位
      const decimals = options.decimals ?? 2;
      return formatNumber(0, decimals, true);
    }
    return '';
  }

  // text 类型原样输出
  if (options.kind === MeasureKind.TEXT) {
    return String(value);
  }

  // 转换为 Decimal 进行精确计算
  let decimal: Decimal;
  try {
    decimal = new Decimal(value);
  } catch {
    // 无法解析为数值时，按 text 处理并记录告警
    if (import.meta.env.DEV) {
      console.warn(`[formatMeasure] 无法解析为数值: ${value}, kind=${options.kind}`);
    }
    return String(value);
  }

  // 根据 kind 格式化
  switch (options.kind) {
    case MeasureKind.AMOUNT:
      return formatAmount(decimal, options.decimals);

    case MeasureKind.RATIO:
      return formatRatio(decimal, options.ratioScale!);

    case MeasureKind.COUNT:
      return formatCount(decimal);

    case MeasureKind.QUANTITY:
    case MeasureKind.EXCHANGE_RATE:
    case MeasureKind.UNIT_PRICE:
      return formatDecimalWithEffectiveScale(decimal);

    default:
      // 未登记分支：按元口径格式化
      return formatAmount(decimal, options.decimals, true);
  }
}

/**
 * 格式化金额（amount kind）
 */
function formatAmount(
  decimal: Decimal,
  accountDecimals?: number,
  isUnregistered = false
): string {
  const displayPrefs = useDisplayPrefsStore();
  const divisor = isUnregistered ? 1 : displayPrefs.unitDivisor;
  const decimals = accountDecimals ?? 2;

  const divided = decimal.dividedBy(divisor);
  return formatNumber(divided.toNumber(), decimals, true);
}

/**
 * 格式化比例（ratio kind）
 */
function formatRatio(decimal: Decimal, ratioScale: RatioScale): string {
  let percentValue: Decimal;

  if (ratioScale === RatioScale.FRACTION) {
    // 小数形式：0.2 → 20.00%
    percentValue = decimal.times(100);
  } else {
    // 百分点形式：20 → 20.00%
    percentValue = decimal;
  }

  // 固定2位小数
  const formatted = formatNumber(percentValue.toNumber(), 2, true);
  return `${formatted}%`;
}

/**
 * 格式化计数（count kind）
 */
function formatCount(decimal: Decimal): string {
  // 检查是否为整数
  if (!decimal.isInteger()) {
    // 原值带小数时按 quantity 规则显示并记录告警
    if (import.meta.env.DEV) {
      console.warn(`[formatMeasure] count 类型的值不是整数: ${decimal.toString()}`);
    }
    return formatDecimalWithEffectiveScale(decimal);
  }

  // 0位小数，整数
  return formatNumber(decimal.toNumber(), 0, true);
}

/**
 * 格式化带有效小数位的数值（quantity/exchange_rate/unit_price）
 *
 * 规则：原值的有效小数位（去掉尾零后的小数位数），最多6位
 */
function formatDecimalWithEffectiveScale(decimal: Decimal): string {
  // 获取原值字符串形式
  const strValue = decimal.toString();

  // 计算有效小数位数
  let effectiveDecimals = 0;
  if (strValue.includes('.')) {
    const decimalPart = strValue.split('.')[1];
    // 去掉尾零后的长度
    effectiveDecimals = decimalPart.replace(/0+$/, '').length;
  }

  // 最多6位
  const decimals = Math.min(effectiveDecimals, 6);

  // 如果超过6位，需要四舍五入
  let valueToFormat = decimal;
  if (effectiveDecimals > 6) {
    valueToFormat = decimal.toDecimalPlaces(6, Decimal.ROUND_HALF_UP);
  }

  return formatNumber(valueToFormat.toNumber(), decimals, true);
}

/**
 * 格式化数值（带千分位）
 *
 * @param value - 数值
 * @param decimals - 小数位数
 * @param useThousandSeparator - 是否使用千分位
 */
function formatNumber(
  value: number,
  decimals: number,
  useThousandSeparator: boolean
): string {
  const fixed = value.toFixed(decimals);

  if (!useThousandSeparator) {
    return fixed;
  }

  // 添加千分位
  const parts = fixed.split('.');
  const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return parts.length > 1 ? `${integerPart}.${parts[1]}` : integerPart;
}
