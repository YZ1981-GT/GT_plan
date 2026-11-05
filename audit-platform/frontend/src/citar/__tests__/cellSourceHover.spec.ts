/**
 * 悬浮来源卡片（spec citar-cell-source-hover R1 / R2）：卡片渲染、悬停时序与缓存、链接换算、格子定位只消费一次。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import CitarSourceCard from '../components/CitarSourceCard.vue'
import { cellSourceLink, localSource, savePendingTaxLocate, signText, takePendingTaxLocate, type CellSource } from '../cellSource'
import { useCellSourceHover, type CellSourceCardState } from '../useCellSourceHover'

const src = (over: Partial<CellSource> = {}): CellSource => ({
  ...localSource('rule', '科目余额表（导入数，不含审计调整）· 本期贷方发生额', '1000'),
  items: [
    { label: '605101 出租固定资产收入', detail: '映射到 6051 其他业务收入', amount: '800', sign: '1', link: { page: 'balance', code: '605101' } },
    { label: '605102 租金', detail: null, amount: '200', sign: '1', link: null },
    { label: '调整分录 AJE-1', detail: '补确认', amount: '-300', sign: '0', link: { page: 'adjustments', group: 'g1' } },
  ],
  linear: true,
  total: '1000',
  notes: ['以下已批准调整分录涉及本格科目，未计入本格'],
  ...over,
})

const state = (source: CellSource | null, over: Partial<CellSourceCardState> = {}): CellSourceCardState => ({
  visible: true, key: 'k', source, loading: false, error: '', anchor: { left: 10, top: 10, right: 60, bottom: 30 }, ...over,
})

describe('CitarSourceCard', () => {
  it('列出计入合计的项、合计 ＝ 格值；不计入的项单列；点链接交回页面', async () => {
    const w = mount(CitarSourceCard, { props: { state: state(src()), label: '2-02 D10 出租固定资产收入' } })
    const text = w.text()
    expect(text).toContain('智能取数')
    expect(text).toContain('2-02 D10 出租固定资产收入')
    expect(text).toContain('合计 1,000.00')
    expect(text).toContain('＝ 格值')
    const lists = w.findAll('.src-card__items')
    expect(lists[0].findAll('li')).toHaveLength(2)
    expect(lists[1].text()).toContain('调整分录 AJE-1')
    await w.findAll('.src-card__link')[0].trigger('click')
    expect(w.emitted('open')?.[0]).toEqual([{ page: 'balance', code: '605101' }])
  })

  it('对不上时写差额；非线性不做合计；手工值显示自动值与差额', () => {
    const bad = mount(CitarSourceCard, { props: { state: state(src({ total: '900', diff: '-100' })) } })
    expect(bad.find('.src-card__total--bad').text()).toContain('与格值差 -100.00')
    const nonlinear = mount(CitarSourceCard, { props: { state: state(src({ linear: false, total: null })) } })
    expect(nonlinear.find('.src-card__total').exists()).toBe(false)
    const manual = mount(CitarSourceCard, {
      props: { state: state(src({ kind: 'manual', manual: { value: '1500', auto: '1000', by_name: '编制人甲', at: '2026-11-05T02:03:00Z' } })) },
    })
    expect(manual.text()).toContain('手工值 1,500.00，自动值 1,000.00（差 500.00）')
    expect(manual.text()).toContain('编制人甲')
    expect(manual.find('.src-card__value').text()).toBe('1,500.00')
  })

  it('加载中 / 失败', () => {
    expect(mount(CitarSourceCard, { props: { state: state(null, { loading: true }) } }).text()).toContain('正在读取数据来源')
    expect(mount(CitarSourceCard, { props: { state: state(null, { error: '权限不足' }) } }).text()).toContain('权限不足')
    expect(mount(CitarSourceCard, { props: { state: state(null, { visible: false }) } }).find('.src-card').exists()).toBe(false)
  })
})

function host(load: () => Promise<Record<string, CellSource>>, disabled?: (k: string) => boolean) {
  let api: ReturnType<typeof useCellSourceHover>
  const C = defineComponent({
    setup() {
      const el = ref<HTMLElement | null>(null)
      api = useCellSourceHover(el, { load, resolve: (k, all) => all?.[k] ?? (all ? null : localSource('none', '…')), disabled })
      return () => h('table', { ref: el }, [h('tbody', [h('tr', [
        h('td', { 'data-src': 'A' }, 'a'), h('td', { 'data-src': 'B' }, 'b'), h('td', {}, 'x'),
      ])])])
    },
  })
  const w = mount(C, { attachTo: document.body })
  return { w, api: () => api! }
}

describe('useCellSourceHover', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('停 400ms 才弹；整表来源只请求一次并缓存；invalidate 后重取', async () => {
    const load = vi.fn().mockResolvedValue({ A: src(), B: src({ value: '5' }) })
    const { w, api } = host(load)
    const [a, b] = w.findAll('td')
    await a.trigger('mouseover')
    vi.advanceTimersByTime(399)
    expect(api().card.value.visible).toBe(false)
    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(api().card.value.visible).toBe(true)
    expect(api().card.value.source?.value).toBe('1000')
    await a.trigger('mouseout', { relatedTarget: b.element })
    await b.trigger('mouseover')
    vi.advanceTimersByTime(400)
    await flushPromises()
    expect(api().card.value.source?.value).toBe('5')
    expect(load).toHaveBeenCalledTimes(1)
    api().invalidate()
    expect(api().card.value.visible).toBe(false)
    await a.trigger('mouseover')
    vi.advanceTimersByTime(400)
    await flushPromises()
    expect(load).toHaveBeenCalledTimes(2)
    w.unmount()
  })

  it('移出后 200ms 内移入卡片不关；Esc 关闭；编辑中的格子不弹', async () => {
    const { w, api } = host(vi.fn().mockResolvedValue({ A: src() }), k => k === 'B')
    const [a, b, plain] = w.findAll('td')
    await a.trigger('mouseover')
    vi.advanceTimersByTime(400)
    await flushPromises()
    await a.trigger('mouseout', { relatedTarget: plain.element })
    vi.advanceTimersByTime(100)
    api().onCardEnter()
    vi.advanceTimersByTime(300)
    expect(api().card.value.visible).toBe(true)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(api().card.value.visible).toBe(false)
    await b.trigger('mouseover')
    vi.advanceTimersByTime(500)
    await flushPromises()
    expect(api().card.value.visible).toBe(false)
    w.unmount()
  })

  it('请求失败时卡片写明原因', async () => {
    const { w, api } = host(vi.fn().mockRejectedValue({ response: { data: { detail: '权限不足' } } }))
    await w.findAll('td')[0].trigger('mouseover')
    vi.advanceTimersByTime(400)
    await flushPromises()
    expect(api().card.value.error).toBe('权限不足')
    w.unmount()
  })

  it('指针停在格子上时表格刷新（invalidate）：不用挪鼠标，400ms 后照常弹出；Esc 关过的不再自动弹', async () => {
    const load = vi.fn().mockResolvedValue({ A: src() })
    const { w, api } = host(load)
    const a = w.findAll('td')[0]
    await a.trigger('mouseover')
    api().invalidate() // 取值回来、来源作废：指针没动，浏览器不会再发 mouseover
    vi.advanceTimersByTime(400)
    await flushPromises()
    expect(api().card.value.visible).toBe(true)
    expect(api().card.value.key).toBe('A')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    api().invalidate()
    vi.advanceTimersByTime(500)
    await flushPromises()
    expect(api().card.value.visible).toBe(false)

    // 离开格子后刷新也不弹
    await a.trigger('mouseover')
    await a.trigger('mouseout', { relatedTarget: document.body })
    api().invalidate()
    vi.advanceTimersByTime(500)
    await flushPromises()
    expect(api().card.value.visible).toBe(false)
    w.unmount()
  })
})

describe('链接换算与格子定位', () => {
  it('cellSourceLink：新页面与沿用的页面', () => {
    expect(cellSourceLink({ page: 'workpaper', code: '2-02', ref: 'D10' })).toEqual({ segment: 'workpapers', query: {} })
    expect(cellSourceLink({ page: 'tax_return', code: 'A100000' })).toEqual({ segment: 'tax-return', query: {} })
    expect(cellSourceLink({ page: 'adjustments', group: 'g1' })).toEqual({ segment: 'adjustments', query: { locate: 'g1' } })
    expect(cellSourceLink({ page: 'reports', report_type: 'income_statement', code: 'IS-001' }))
      .toEqual({ segment: 'reports', query: { tab: 'income_statement', locate: 'IS-001' } })
    expect(cellSourceLink({ page: 'balance', code: '605101' })).toEqual({ segment: 'ledger-query', query: { tab: 'balance', locate: '605101' } })
  })

  it('待定位的格子只消费一次，且只给对应的表', () => {
    savePendingTaxLocate('p1', { domain: 'tax_return', code: 'A100000', sheet: 'A100000', ref: 'D3' })
    expect(takePendingTaxLocate('p1', 'workpaper')).toBeNull()
    expect(takePendingTaxLocate('p1', 'tax_return')).toEqual({ domain: 'tax_return', code: 'A100000', sheet: 'A100000', ref: 'D3' })
    expect(takePendingTaxLocate('p1', 'tax_return')).toBeNull()
  })

  it('signText', () => {
    expect([signText('1'), signText('-1'), signText('0'), signText('2'), signText('-0.25')]).toEqual(['+', '−', null, '+ ×2', '− ×0.25'])
  })
})
