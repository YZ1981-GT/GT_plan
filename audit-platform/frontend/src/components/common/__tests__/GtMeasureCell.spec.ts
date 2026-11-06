import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GtMeasureCell from '../GtMeasureCell.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

beforeEach(() => {
  setActivePinia(createPinia())
  const prefs = useDisplayPrefsStore()
  prefs.setUnit('wan')
  prefs.setDecimals(2)
  prefs.setShowZero(true)
})

describe('GtMeasureCell', () => {
  it.each([
    ['amount', null, 10000, '1.00'],
    ['quantity', null, 10000.125, '10,000.125'],
    ['count', null, 12, '12'],
    ['exchange_rate', null, 7.1234567, '7.123457'],
    ['unit_price', null, 10000.5, '10,000.5'],
    ['ratio', 'fraction', 0.2, '20.00%'],
    ['ratio', 'percent_points', 20, '20.00%'],
    ['text', null, '10000', '10000'],
  ] as const)('%s / %s 不混用金额除数', (kind, ratioScale, value, expected) => {
    const wrapper = mount(GtMeasureCell, { props: { kind, ratioScale, value } as any })
    expect(wrapper.text()).toBe(expected)
    expect(wrapper.attributes('data-gt-value')).toBe(String(value))
  })

  it('未登记数值按元口径展示，不按万元缩放', () => {
    expect(mount(GtMeasureCell, { props: { value: 10000 } }).text()).toBe('10,000.00')
  })

  it('只有 amount 消费变动高亮；非金额负数仍可红色显示', () => {
    const amount = mount(GtMeasureCell, { props: { kind: 'amount', value: 200, priorValue: 100 } })
    const count = mount(GtMeasureCell, { props: { kind: 'count', value: -2, priorValue: -1 } })
    expect(amount.classes()).toContain('gt-amount--highlight')
    expect(count.classes()).not.toContain('gt-amount--highlight')
    expect(count.classes()).toContain('gt-amount--negative')
  })
})
