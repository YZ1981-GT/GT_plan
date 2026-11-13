import { describe, it, expect, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { setActivePinia, createPinia } from 'pinia';
import GtMeasureCell from '../GtMeasureCell.vue';
import { MeasureKind, RatioScale } from '@/types/measureKind';

describe('GtMeasureCell', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  describe('基本渲染', () => {
    it('应正确渲染金额', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 10000,
          kind: MeasureKind.AMOUNT
        }
      });

      expect(wrapper.text()).toBe('10,000.00');
      expect(wrapper.attributes('data-gt-value')).toBe('10000');
    });

    it('应应用等宽数字样式', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 100,
          kind: MeasureKind.AMOUNT
        }
      });

      const style = wrapper.attributes('style');
      expect(style).toContain('tabular-nums');
    });

    it('应有正确的 CSS 类', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 100,
          kind: MeasureKind.AMOUNT
        }
      });

      expect(wrapper.classes()).toContain('gt-measure-cell');
    });
  });

  describe('度量类型', () => {
    it('应正确显示 amount', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 10000,
          kind: MeasureKind.AMOUNT,
          decimals: 2
        }
      });

      expect(wrapper.text()).toBe('10,000.00');
    });

    it('应正确显示 ratio (fraction)', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 0.2,
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.FRACTION
        }
      });

      expect(wrapper.text()).toBe('20.00%');
    });

    it('应正确显示 ratio (percent_points)', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 20,
          kind: MeasureKind.RATIO,
          ratioScale: RatioScale.PERCENT_POINTS
        }
      });

      expect(wrapper.text()).toBe('20.00%');
    });

    it('应正确显示 count', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 100,
          kind: MeasureKind.COUNT
        }
      });

      expect(wrapper.text()).toBe('100');
    });

    it('应正确显示 quantity', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 10.123,
          kind: MeasureKind.QUANTITY
        }
      });

      expect(wrapper.text()).toBe('10.123');
    });

    it('应正确显示 exchange_rate', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 6.5432,
          kind: MeasureKind.EXCHANGE_RATE
        }
      });

      expect(wrapper.text()).toBe('6.5432');
    });

    it('应正确显示 unit_price', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 99.99,
          kind: MeasureKind.UNIT_PRICE
        }
      });

      expect(wrapper.text()).toBe('99.99');
    });

    it('应正确显示 text', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 'hello world',
          kind: MeasureKind.TEXT
        }
      });

      expect(wrapper.text()).toBe('hello world');
    });
  });

  describe('负数红色显示', () => {
    it('negativeRed=true 且值为负时应有红色类', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: -1000,
          kind: MeasureKind.AMOUNT,
          negativeRed: true
        }
      });

      expect(wrapper.classes()).toContain('text-red-500');
    });

    it('negativeRed=false 时不应有红色类', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: -1000,
          kind: MeasureKind.AMOUNT,
          negativeRed: false
        }
      });

      expect(wrapper.classes()).not.toContain('text-red-500');
    });

    it('值为正时不应有红色类', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 1000,
          kind: MeasureKind.AMOUNT,
          negativeRed: true
        }
      });

      expect(wrapper.classes()).not.toContain('text-red-500');
    });
  });

  describe('data-gt-value 属性', () => {
    it('应保存原始数值', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 1234.5678,
          kind: MeasureKind.AMOUNT
        }
      });

      expect(wrapper.attributes('data-gt-value')).toBe('1234.5678');
    });

    it('应保存 null 值', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: null,
          kind: MeasureKind.AMOUNT
        }
      });

      // null 会被转为空字符串
      expect(wrapper.attributes('data-gt-value')).toBe('');
    });

    it('应保存字符串值', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 'text value',
          kind: MeasureKind.TEXT
        }
      });

      expect(wrapper.attributes('data-gt-value')).toBe('text value');
    });
  });

  describe('空值处理', () => {
    it('showZero=true 应显示零值', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: null,
          kind: MeasureKind.AMOUNT,
          showZero: true
        }
      });

      expect(wrapper.text()).toBe('0.00');
    });

    it('showZero=false 应显示空', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: null,
          kind: MeasureKind.AMOUNT,
          showZero: false
        }
      });

      expect(wrapper.text()).toBe('');
    });
  });

  describe('props 默认值', () => {
    it('应使用正确的默认值', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 1000
        }
      });

      // kind=null, decimals=2, showZero=true, negativeRed=false
      // 未登记分支按元口径
      expect(wrapper.text()).toBe('1,000.00');
      expect(wrapper.classes()).not.toContain('text-red-500');
    });
  });

  describe('响应式更新', () => {
    it('value 变化应更新显示', async () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 1000,
          kind: MeasureKind.AMOUNT
        }
      });

      expect(wrapper.text()).toBe('1,000.00');

      await wrapper.setProps({ value: 2000 });
      expect(wrapper.text()).toBe('2,000.00');
    });

    it('kind 变化应更新格式', async () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 100,
          kind: MeasureKind.AMOUNT
        }
      });

      expect(wrapper.text()).toBe('100.00');

      await wrapper.setProps({ kind: MeasureKind.COUNT });
      expect(wrapper.text()).toBe('100');
    });

    it('negativeRed 变化应更新样式', async () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: -1000,
          kind: MeasureKind.AMOUNT,
          negativeRed: false
        }
      });

      expect(wrapper.classes()).not.toContain('text-red-500');

      await wrapper.setProps({ negativeRed: true });
      expect(wrapper.classes()).toContain('text-red-500');
    });
  });

  describe('边界情况', () => {
    it('应处理超大数值', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 1e10,
          kind: MeasureKind.AMOUNT
        }
      });

      expect(wrapper.text()).toBe('10,000,000,000.00');
    });

    it('应处理极小数值', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: 0.000001,
          kind: MeasureKind.QUANTITY
        }
      });

      expect(wrapper.text()).toBe('0.000001');
    });

    it('应处理字符串形式的数值', () => {
      const wrapper = mount(GtMeasureCell, {
        props: {
          value: '10000',
          kind: MeasureKind.AMOUNT
        }
      });

      expect(wrapper.text()).toBe('10,000.00');
    });
  });
});
