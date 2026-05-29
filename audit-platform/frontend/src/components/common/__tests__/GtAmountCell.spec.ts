/**
 * GtAmountCell — Decimal 化单元测试（V3 Req 2.7）
 *
 * 验证内容：
 * - 显示格式化（千分位 + 小数位 + 单位换算）
 * - 负数红色（gt-amount--negative）
 * - 变动阈值高亮（gt-amount--highlight）
 * - 单位切换（元 → 万元 → 千元）
 * - 边界：null / undefined / 空串 / 0 / 极小 / 极大
 * - 浮点误差规避：1234.567 / 10000、0.1 + 0.2 等典型反例
 * - 公共 API 不变：value / clickable / comment / priorValue / @click
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import GtAmountCell from '../GtAmountCell.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// el-tooltip stub：仅渲染 slot，避免 popper 测试环境噪音
const STUBS = {
  'el-tooltip': {
    name: 'ElTooltip',
    template: '<span class="el-tooltip-stub"><slot /></span>',
    props: ['content', 'placement', 'showAfter', 'hideAfter', 'effect', 'popperClass'],
  },
}

function makeWrapper(props: Record<string, unknown> = {}) {
  return mount(GtAmountCell, {
    props: props as any,
    global: { stubs: STUBS },
  })
}

/** displayPrefs Store 持久化到 localStorage，测试之间需重置防止串扰 */
function resetPrefs() {
  localStorage.clear()
  setActivePinia(createPinia())
  const prefs = useDisplayPrefsStore()
  prefs.setUnit('wan')
  prefs.setDecimals(2)
  prefs.setShowZero(false)
  prefs.setNegativeRed(true)
  prefs.setHighlightThreshold(0.2)
}

describe('GtAmountCell — 公共 API 不变', () => {
  beforeEach(() => {
    resetPrefs()
  })

  it('clickable=false 时点击不 emit', async () => {
    const wrapper = makeWrapper({ value: 100 })
    await wrapper.find('.gt-amount-cell').trigger('click')
    expect(wrapper.emitted('click')).toBeUndefined()
  })

  it('clickable=true 时点击 emit click 事件，载荷为原值', async () => {
    const wrapper = makeWrapper({ value: '1234.56', clickable: true })
    await wrapper.find('.gt-amount-cell').trigger('click')
    const events = wrapper.emitted('click')
    expect(events).toBeTruthy()
    expect(events![0]).toEqual(['1234.56'])
  })

  it('null / undefined / 空串 → "-"', () => {
    const w1 = makeWrapper({ value: null })
    const w2 = makeWrapper({ value: undefined })
    const w3 = makeWrapper({ value: '' })
    expect(w1.text()).toBe('-')
    expect(w2.text()).toBe('-')
    expect(w3.text()).toBe('-')
  })

  it('非法字符串（如 "abc"）→ "-"', () => {
    const w = makeWrapper({ value: 'abc' })
    expect(w.text()).toBe('-')
  })
})

describe('GtAmountCell — 单位切换（Decimal 化）', () => {
  beforeEach(() => {
    resetPrefs()
  })

  it('元单位：1234567.89 直接千分位展示', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setDecimals(2)
    const w = makeWrapper({ value: 1234567.89 })
    expect(w.text()).toBe('1,234,567.89')
  })

  it('万元单位：1234567.89 → 123.46（4 舍 5 入到 2 位）', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('wan')
    prefs.setDecimals(2)
    const w = makeWrapper({ value: 1234567.89 })
    // 1234567.89 / 10000 = 123.456789 → 四舍五入 2 位 = 123.46
    expect(w.text()).toBe('123.46')
  })

  it('千元单位：1234567.89 → 1,234.57', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('qian')
    prefs.setDecimals(2)
    const w = makeWrapper({ value: 1234567.89 })
    expect(w.text()).toBe('1,234.57')
  })

  it('单位切换响应式：万元 → 元 → 万元', async () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('wan')
    prefs.setDecimals(2)
    const w = makeWrapper({ value: 1000000 })
    expect(w.text()).toBe('100.00')

    prefs.setUnit('yuan')
    await nextTick()
    expect(w.text()).toBe('1,000,000.00')

    prefs.setUnit('wan')
    await nextTick()
    expect(w.text()).toBe('100.00')
  })

  it('小数位数响应式：2 位 → 4 位', async () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('wan')
    prefs.setDecimals(2)
    const w = makeWrapper({ value: 1234567.89 })
    expect(w.text()).toBe('123.46')

    prefs.setDecimals(4)
    await nextTick()
    // 1234567.89 / 10000 = 123.456789 → 保留 4 位 = 123.4568
    expect(w.text()).toBe('123.4568')
  })
})

describe('GtAmountCell — 负数色彩与零值', () => {
  beforeEach(() => {
    resetPrefs()
  })

  it('负数携带 gt-amount--negative class', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setNegativeRed(true)
    const w = makeWrapper({ value: -500 })
    expect(w.find('.gt-amount-cell').classes()).toContain('gt-amount--negative')
    expect(w.text()).toBe('-500.00')
  })

  it('negativeRed=false 时负数不携带 negative class', async () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setNegativeRed(false)
    const w = makeWrapper({ value: -500 })
    await nextTick()
    expect(w.find('.gt-amount-cell').classes()).not.toContain('gt-amount--negative')
  })

  it('零值 + showZero=false → "-"（审计惯例）', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setShowZero(false)
    const w = makeWrapper({ value: 0 })
    expect(w.text()).toBe('-')
  })

  it('零值 + showZero=true → "0.00"', async () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setShowZero(true)
    const w = makeWrapper({ value: 0 })
    await nextTick()
    expect(w.text()).toBe('0.00')
  })
})

describe('GtAmountCell — 变动阈值高亮', () => {
  beforeEach(() => {
    resetPrefs()
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setHighlightThreshold(0.2)
  })

  it('上期 100、本期 130 → 变动 30% 超阈值 → 高亮', () => {
    const w = makeWrapper({ value: 130, priorValue: 100 })
    expect(w.find('.gt-amount-cell').classes()).toContain('gt-amount--highlight')
  })

  it('上期 100、本期 110 → 变动 10% 未超阈值 → 不高亮', () => {
    const w = makeWrapper({ value: 110, priorValue: 100 })
    expect(w.find('.gt-amount-cell').classes()).not.toContain('gt-amount--highlight')
  })

  it('上期 0、本期 100 → 新增科目 → 高亮', () => {
    const w = makeWrapper({ value: 100, priorValue: 0 })
    expect(w.find('.gt-amount-cell').classes()).toContain('gt-amount--highlight')
  })

  it('上期 0、本期 0 → 不高亮', () => {
    const w = makeWrapper({ value: 0, priorValue: 0 })
    expect(w.find('.gt-amount-cell').classes()).not.toContain('gt-amount--highlight')
  })

  it('priorValue=null → 不高亮（无对比基准）', () => {
    const w = makeWrapper({ value: 100, priorValue: null })
    expect(w.find('.gt-amount-cell').classes()).not.toContain('gt-amount--highlight')
  })

  it('阈值=0（关闭）时不再高亮', async () => {
    const prefs = useDisplayPrefsStore()
    prefs.setHighlightThreshold(0)
    const w = makeWrapper({ value: 1000, priorValue: 100 })
    await nextTick()
    expect(w.find('.gt-amount-cell').classes()).not.toContain('gt-amount--highlight')
  })

  it('Decimal 阈值边界：变动率 19.999...% < 20% 不高亮（无浮点误差）', () => {
    // 上期 1000，本期 1199.99 → 变动率 = 199.99 / 1000 = 0.19999 < 0.2
    const w = makeWrapper({ value: 1199.99, priorValue: 1000 })
    expect(w.find('.gt-amount-cell').classes()).not.toContain('gt-amount--highlight')
  })

  it('Decimal 阈值边界：变动率恰好 20% 应高亮（≥ 阈值）', () => {
    const w = makeWrapper({ value: 1200, priorValue: 1000 })
    expect(w.find('.gt-amount-cell').classes()).toContain('gt-amount--highlight')
  })
})

describe('GtAmountCell — 浮点误差规避（Decimal 核心价值）', () => {
  beforeEach(() => {
    resetPrefs()
  })

  it('1234.567 / 10000（万元）→ 0.12（无浮点尾巴）', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('wan')
    prefs.setDecimals(2)
    const w = makeWrapper({ value: 1234.567 })
    // Number 计算：1234.567 / 10000 = 0.1234567 → toFixed(2) = '0.12'（巧合无误差）
    // Decimal 计算：同样 = '0.12'，但保证更深小数位下的稳定性
    expect(w.text()).toBe('0.12')
  })

  it('1234.567 / 10000 保留 6 位小数 → 0.123457（四舍五入）', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('wan')
    prefs.setDecimals(6)
    const w = makeWrapper({ value: 1234.567 })
    expect(w.text()).toBe('0.123457')
  })

  it('字符串 "0.1" + 字符串 "0.2"（典型 0.1+0.2≠0.3 的反例场景）— 单值传入精确显示', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setDecimals(2)
    // 直接传入 '0.30'，Decimal 不会引入浮点误差
    const w = makeWrapper({ value: '0.30' })
    expect(w.text()).toBe('0.30')
  })

  it('极小金额：0.001 元单位、4 位小数 → "0.0010"', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setDecimals(4)
    const w = makeWrapper({ value: 0.001 })
    expect(w.text()).toBe('0.0010')
  })

  it('极大金额：10^15 元 → 万元单位、2 位小数（不丢精度）', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('wan')
    prefs.setDecimals(2)
    // 字符串传入避免 number 字面量越过 Number.MAX_SAFE_INTEGER（9.007×10^15）
    const w = makeWrapper({ value: '1000000000000000' })
    // / 10000 = 100,000,000,000.00
    expect(w.text()).toBe('100,000,000,000.00')
  })

  it('字符串科学计数法：1.23e6 → 元单位 1,230,000.00', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setUnit('yuan')
    prefs.setDecimals(2)
    const w = makeWrapper({ value: '1.23e6' })
    expect(w.text()).toBe('1,230,000.00')
  })
})

describe('GtAmountCell — clickable hover 类', () => {
  beforeEach(() => {
    resetPrefs()
  })

  it('clickable=true 时携带 gt-amount-cell--clickable 类', () => {
    const w = makeWrapper({ value: 100, clickable: true })
    expect(w.find('.gt-amount-cell').classes()).toContain('gt-amount-cell--clickable')
  })

  it('clickable=false 时不携带该类', () => {
    const w = makeWrapper({ value: 100, clickable: false })
    expect(w.find('.gt-amount-cell').classes()).not.toContain('gt-amount-cell--clickable')
  })
})
