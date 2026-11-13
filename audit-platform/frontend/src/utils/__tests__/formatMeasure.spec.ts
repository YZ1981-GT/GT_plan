import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { formatMeasure } from '../formatMeasure';
import { MeasureKind, RatioScale } from '@/types/measureKind';

describe('formatMeasure', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  describe('空值处理', () => {
    it('应正确处理 null/undefined', () => {
      expect(formatMeasure(null)).toBe('0.00');
      expect(formatMeasure(undefined)).toBe('0.00');
      expect(formatMeasure('')).toBe('0.00');
    });

    it('ratio 类型的零值应返回 0.00%', () => {
      expect(
        formatMeasure(null, {
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.FRACTION
        })
      ).toBe('0.00%');
    });

    it('count 类型的零值应返回 0', () => {
      expect(formatMeasure(null, { kind: MeasureKind.COUNT })).toBe('0');
    });

    it('showZero=false 应返回空字符串', () => {
      expect(formatMeasure(null, { showZero: false })).toBe('');
    });
  });

  describe('text 类型', () => {
    it('应原样输出文本', () => {
      expect(formatMeasure('hello', { kind: MeasureKind.TEXT })).toBe('hello');
      expect(formatMeasure('123', { kind: MeasureKind.TEXT })).toBe('123');
      expect(formatMeasure('', { kind: MeasureKind.TEXT })).toBe('');
    });
  });

  describe('amount 类型', () => {
    it('应按元口径格式化（默认2位小数）', () => {
      expect(formatMeasure(10000, { kind: MeasureKind.AMOUNT })).toBe(
        '10,000.00'
      );
      expect(formatMeasure(1234.567, { kind: MeasureKind.AMOUNT })).toBe(
        '1,234.57'
      );
    });

    it('应支持自定义小数位', () => {
      expect(
        formatMeasure(10000, { kind: MeasureKind.AMOUNT, decimals: 0 })
      ).toBe('10,000');
      expect(
        formatMeasure(1234.5678, { kind: MeasureKind.AMOUNT, decimals: 4 })
      ).toBe('1,234.5678');
    });

    it('应正确处理负数', () => {
      expect(formatMeasure(-10000, { kind: MeasureKind.AMOUNT })).toBe(
        '-10,000.00'
      );
    });

    it('应正确处理零值', () => {
      expect(formatMeasure(0, { kind: MeasureKind.AMOUNT })).toBe('0.00');
    });
  });

  describe('ratio 类型', () => {
    it('fraction 刻度应乘以100', () => {
      // 0.2 → 20.00%
      expect(
        formatMeasure(0.2, {
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.FRACTION
        })
      ).toBe('20.00%');

      // 0.025 → 2.50%
      expect(
        formatMeasure(0.025, {
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.FRACTION
        })
      ).toBe('2.50%');
    });

    it('percent_points 刻度应保持原值', () => {
      // 20 → 20.00%
      expect(
        formatMeasure(20, {
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.PERCENT_POINTS
        })
      ).toBe('20.00%');

      // 2.5 → 2.50%
      expect(
        formatMeasure(2.5, {
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.PERCENT_POINTS
        })
      ).toBe('2.50%');
    });

    it('应固定2位小数', () => {
      expect(
        formatMeasure(0.12345, {
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.FRACTION
        })
      ).toBe('12.35%');

      expect(
        formatMeasure(12.3456, {
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.PERCENT_POINTS
        })
      ).toBe('12.35%');
    });

    it('应正确处理负比例', () => {
      expect(
        formatMeasure(-0.1, {
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.FRACTION
        })
      ).toBe('-10.00%');
    });
  });

  describe('count 类型', () => {
    it('整数应显示0位小数', () => {
      expect(formatMeasure(10, { kind: MeasureKind.COUNT })).toBe('10');
      expect(formatMeasure(1000, { kind: MeasureKind.COUNT })).toBe('1,000');
      expect(formatMeasure(0, { kind: MeasureKind.COUNT })).toBe('0');
    });

    it('带小数应按 quantity 规则显示', () => {
      // 并记录 DEV 告警（在真实环境中）
      expect(formatMeasure(10.5, { kind: MeasureKind.COUNT })).toBe('10.5');
      expect(formatMeasure(100.123, { kind: MeasureKind.COUNT })).toBe(
        '100.123'
      );
    });
  });

  describe('quantity 类型', () => {
    it('应保留有效小数位（最多6位）', () => {
      expect(formatMeasure(10.5, { kind: MeasureKind.QUANTITY })).toBe('10.5');
      expect(formatMeasure(10.123, { kind: MeasureKind.QUANTITY })).toBe(
        '10.123'
      );
      expect(formatMeasure(10.123456, { kind: MeasureKind.QUANTITY })).toBe(
        '10.123456'
      );
    });

    it('超过6位小数应四舍五入', () => {
      expect(formatMeasure(10.1234567, { kind: MeasureKind.QUANTITY })).toBe(
        '10.123457'
      );
      expect(formatMeasure(10.1234564, { kind: MeasureKind.QUANTITY })).toBe(
        '10.123456'
      );
    });

    it('应去掉尾零', () => {
      expect(formatMeasure(10.0, { kind: MeasureKind.QUANTITY })).toBe('10');
      expect(formatMeasure(10.1, { kind: MeasureKind.QUANTITY })).toBe('10.1');
      expect(formatMeasure(10.1000, { kind: MeasureKind.QUANTITY })).toBe(
        '10.1'
      );
    });

    it('整数应显示为整数', () => {
      expect(formatMeasure(100, { kind: MeasureKind.QUANTITY })).toBe('100');
    });
  });

  describe('exchange_rate 类型', () => {
    it('应保留有效小数位（最多6位）', () => {
      expect(formatMeasure(6.5, { kind: MeasureKind.EXCHANGE_RATE })).toBe(
        '6.5'
      );
      expect(
        formatMeasure(6.123456, { kind: MeasureKind.EXCHANGE_RATE })
      ).toBe('6.123456');
      expect(
        formatMeasure(6.1234567, { kind: MeasureKind.EXCHANGE_RATE })
      ).toBe('6.123457');
    });
  });

  describe('unit_price 类型', () => {
    it('应保留有效小数位（最多6位）', () => {
      expect(formatMeasure(99.99, { kind: MeasureKind.UNIT_PRICE })).toBe(
        '99.99'
      );
      expect(
        formatMeasure(99.123456, { kind: MeasureKind.UNIT_PRICE })
      ).toBe('99.123456');
      expect(
        formatMeasure(99.1234567, { kind: MeasureKind.UNIT_PRICE })
      ).toBe('99.123457');
    });
  });

  describe('未登记分支', () => {
    it('无 kind 时应按元口径格式化', () => {
      expect(formatMeasure(10000)).toBe('10,000.00');
      expect(formatMeasure(1234.567)).toBe('1,234.57');
    });

    it('应支持自定义小数位', () => {
      expect(formatMeasure(10000, { decimals: 0 })).toBe('10,000');
      expect(formatMeasure(1234.5678, { decimals: 4 })).toBe('1,234.5678');
    });
  });

  describe('边界情况', () => {
    it('应正确处理超大数值', () => {
      expect(formatMeasure(1e10, { kind: MeasureKind.AMOUNT })).toBe(
        '10,000,000,000.00'
      );
    });

    it('应正确处理极小数值', () => {
      expect(formatMeasure(0.000001, { kind: MeasureKind.QUANTITY })).toBe(
        '0.000001'
      );
    });

    it('应处理无法解析的值', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      expect(formatMeasure('invalid', { kind: MeasureKind.AMOUNT })).toBe(
        'invalid'
      );
      consoleSpy.mockRestore();
    });

    it('应正确处理字符串形式的数值', () => {
      expect(formatMeasure('10000', { kind: MeasureKind.AMOUNT })).toBe(
        '10,000.00'
      );
      expect(
        formatMeasure('0.2', {
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.FRACTION
        })
      ).toBe('20.00%');
    });
  });
});
