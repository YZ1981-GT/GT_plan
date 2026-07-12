/**
 * WpAmountCell — Unit tests
 *
 * Feature: platform-global-hardening
 * Requirements: 4.2, 4.7
 *
 * Tests:
 * 1. 渲染格式化金额值（正/负/null/0）
 * 2. 负数红字 CSS 类
 * 3. 变动指示器（priorValue 提供时显示）
 * 4. rawUnit 模式不做单位换算
 * 5. inject DisplayPrefs_Key 注入消费
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, computed, defineComponent } from 'vue'
import WpAmountCell from '../WpAmountCell.vue'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'

// ─── Mock displayPrefs store ───
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => mockStore,
}))

// Minimal mock matching DisplayPrefsContract interface
const mockStore = {
  amountUnit: ref('wan'),
  decimals: ref(2),
  negativeRed: ref(true),
  showZero: ref(false),
  highlightThreshold: ref(0.2),
  fmtAmount(v: any, opts?: { rawUnit?: boolean }): string {
    if (v == null) return '—'
    const n = typeof v === 'number' ? v : Number(v)
    if (isNaN(n)) return '—'
    if (opts?.rawUnit) {
      return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    }
    // 模拟万元换算
    const converted = n / 10000
    if (!mockStore.showZero.value && converted === 0) return '—'
    return converted.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  },
  fmt(v: any, opts?: { rawUnit?: boolean }) { return mockStore.fmtAmount(v, opts) },
  amountClass(v: any, priorValue?: any): string {
    const classes: string[] = []
    const n = typeof v === 'number' ? v : Number(v)
    if (!isNaN(n)) {
      if (mockStore.negativeRed.value && n < 0) classes.push('gt-amount--negative')
      if (mockStore.highlightThreshold.value > 0 && priorValue != null) {
        const prior = Number(priorValue)
        if (!isNaN(prior) && prior !== 0) {
          const changeRate = Math.abs((n - prior) / prior)
          if (changeRate >= mockStore.highlightThreshold.value) classes.push('gt-amount--highlight')
        }
      }
    }
    return classes.join(' ')
  },
  unitSuffix: computed(() => '万元'),
  unitDivisor: computed(() => 10000),
  fontConfig: computed(() => ({ tableFont: '13px', label: '标准' })),
}

describe('WpAmountCell', () => {
  // ─── 1. 格式化渲染 ───
  describe('格式化金额值', () => {
    it('null 值渲染为破折号', () => {
      const wrapper = mount(WpAmountCell, { props: { value: null } })
      expect(wrapper.find('.wp-amount-cell__value').text()).toBe('—')
    })

    it('正数格式化（万元换算）', () => {
      const wrapper = mount(WpAmountCell, { props: { value: 1000000 } })
      // 1000000 / 10000 = 100.00
      expect(wrapper.find('.wp-amount-cell__value').text()).toBe('100.00')
    })

    it('负数格式化', () => {
      const wrapper = mount(WpAmountCell, { props: { value: -500000 } })
      // -500000 / 10000 = -50.00
      expect(wrapper.find('.wp-amount-cell__value').text()).toBe('-50.00')
    })
  })

  // ─── 2. 负数红字 CSS 类 ───
  describe('负数红字', () => {
    it('负数应用 gt-amount--negative 类', () => {
      const wrapper = mount(WpAmountCell, { props: { value: -100000 } })
      expect(wrapper.find('.wp-amount-cell').classes()).toContain('gt-amount--negative')
    })

    it('正数不应用 gt-amount--negative 类', () => {
      const wrapper = mount(WpAmountCell, { props: { value: 100000 } })
      expect(wrapper.find('.wp-amount-cell').classes()).not.toContain('gt-amount--negative')
    })
  })

  // ─── 3. 变动指示器 ───
  describe('变动指示器（priorValue）', () => {
    it('无 priorValue 时不显示指示器', () => {
      const wrapper = mount(WpAmountCell, { props: { value: 100000 } })
      expect(wrapper.find('.wp-amount-cell__variance').exists()).toBe(false)
    })

    it('value > priorValue 时显示 ↑', () => {
      const wrapper = mount(WpAmountCell, { props: { value: 200000, priorValue: 100000 } })
      expect(wrapper.find('.wp-amount-cell__variance').text()).toBe('↑')
      expect(wrapper.find('.wp-amount-cell__variance--up').exists()).toBe(true)
    })

    it('value < priorValue 时显示 ↓', () => {
      const wrapper = mount(WpAmountCell, { props: { value: 50000, priorValue: 100000 } })
      expect(wrapper.find('.wp-amount-cell__variance').text()).toBe('↓')
      expect(wrapper.find('.wp-amount-cell__variance--down').exists()).toBe(true)
    })

    it('value === priorValue 时不显示指示器', () => {
      const wrapper = mount(WpAmountCell, { props: { value: 100000, priorValue: 100000 } })
      expect(wrapper.find('.wp-amount-cell__variance').exists()).toBe(false)
    })
  })

  // ─── 4. rawUnit 模式 ───
  describe('rawUnit 模式', () => {
    it('rawUnit=true 不做单位换算，直接格式化原始值', () => {
      const wrapper = mount(WpAmountCell, { props: { value: 12345.67, rawUnit: true } })
      // 不除以10000，直接格式化
      expect(wrapper.find('.wp-amount-cell__value').text()).toBe('12,345.67')
    })
  })

  // ─── 5. inject DisplayPrefs_Key ───
  describe('通过 inject(DisplayPrefs_Key) 消费', () => {
    it('从祖先注入获取 displayPrefs', () => {
      const customFmt = (v: any) => v == null ? '无' : `¥${v}`
      const customPrefs = {
        fmtAmount: customFmt,
        fmt: customFmt,
        amountClass: () => '',
      }

      const Wrapper = defineComponent({
        components: { WpAmountCell },
        setup() {
          // 通过 provide 注入自定义偏好
          return {}
        },
        template: '<WpAmountCell :value="999" />',
      })

      const wrapper = mount(Wrapper, {
        global: {
          provide: { [DisplayPrefs_Key as symbol]: customPrefs },
        },
      })

      expect(wrapper.find('.wp-amount-cell__value').text()).toBe('¥999')
    })
  })
})
