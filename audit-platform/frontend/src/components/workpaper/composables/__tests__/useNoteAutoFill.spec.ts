// @vitest-environment jsdom
/**
 * useNoteAutoFill SDK 契约测试（P2）。
 * 锁定：初始 pull、审定事件刷新、accountCode 过滤、卸载清理。
 */
import { describe, it, expect, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { eventBus } from '@/utils/eventBus'
import { useNoteAutoFill, parseNoteNumber } from '../useNoteAutoFill'

function mountWith(opts: any) {
  const Comp = defineComponent({
    setup() {
      const api = useNoteAutoFill(opts)
      return { api }
    },
    render() {
      return h('div')
    },
  })
  return mount(Comp)
}

describe('parseNoteNumber', () => {
  it('区分 null 与 0', () => {
    expect(parseNoteNumber(null)).toBeNull()
    expect(parseNoteNumber('')).toBeNull()
    expect(parseNoteNumber('abc')).toBeNull()
    expect(parseNoteNumber(0)).toBe(0)
    expect(parseNoteNumber('12.5')).toBe(12.5)
  })
})

describe('useNoteAutoFill', () => {
  it('onMounted 初始 pull 取数', () => {
    const map = ref(new Map<string, any>([['M7-1-total-audited', { remark: '900' }]]))
    const onRefresh = vi.fn()
    mountWith({
      allResponses: map,
      sources: { total: 'M7-1-total-audited' },
      onRefresh,
    })
    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(onRefresh.mock.calls[0][0]).toEqual({ total: 900 })
  })

  it('substantive:adjudicated 命中 accountCode → 刷新', async () => {
    vi.useFakeTimers()
    const map = ref(new Map<string, any>([['M7-1-total-audited', { remark: '100' }]]))
    const onRefresh = vi.fn()
    mountWith({
      allResponses: map,
      sources: { total: 'M7-1-total-audited' },
      accountCodes: ['4201'],
      onRefresh,
      debounceMs: 50,
    })
    onRefresh.mockClear()
    map.value = new Map([['M7-1-total-audited', { remark: '200' }]])
    eventBus.emit('substantive:adjudicated', {
      accountCode: '4201',
      auditedAmount: 200,
      wpCode: 'M7',
      timestamp: 1,
    })
    await vi.advanceTimersByTimeAsync(60)
    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(onRefresh.mock.calls[0][0]).toEqual({ total: 200 })
    vi.useRealTimers()
  })

  it('accountCode 不命中 → 不刷新', async () => {
    vi.useFakeTimers()
    const map = ref(new Map<string, any>([['x', { remark: '1' }]]))
    const onRefresh = vi.fn()
    mountWith({
      allResponses: map,
      sources: { x: 'x' },
      accountCodes: ['4201'],
      onRefresh,
      debounceMs: 50,
    })
    onRefresh.mockClear()
    eventBus.emit('substantive:adjudicated', {
      accountCode: '9999',
      auditedAmount: 1,
      wpCode: 'ZZ',
      timestamp: 1,
    })
    await vi.advanceTimersByTimeAsync(60)
    expect(onRefresh).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('无 accountCodes → 任意审定事件都刷新', async () => {
    vi.useFakeTimers()
    const map = ref(new Map<string, any>([['x', { remark: '1' }]]))
    const onRefresh = vi.fn()
    mountWith({ allResponses: map, sources: { x: 'x' }, onRefresh, debounceMs: 50 })
    onRefresh.mockClear()
    eventBus.emit('substantive:adjudicated', {
      accountCode: 'anything',
      auditedAmount: 1,
      wpCode: 'ZZ',
      timestamp: 1,
    })
    await vi.advanceTimersByTimeAsync(60)
    expect(onRefresh).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })

  it('reload 在 pull 前调用', async () => {
    vi.useFakeTimers()
    const order: string[] = []
    const map = ref(new Map<string, any>([['x', { remark: '1' }]]))
    mountWith({
      allResponses: map,
      sources: { x: 'x' },
      reload: async () => { order.push('reload') },
      onRefresh: () => order.push('refresh'),
      debounceMs: 50,
    })
    order.length = 0
    eventBus.emit('substantive:adjudicated', { accountCode: 'a', auditedAmount: 1, wpCode: 'z', timestamp: 1 })
    await vi.advanceTimersByTimeAsync(60)
    expect(order).toEqual(['reload', 'refresh'])
    vi.useRealTimers()
  })

  it('卸载后不再响应事件', async () => {
    vi.useFakeTimers()
    const map = ref(new Map<string, any>([['x', { remark: '1' }]]))
    const onRefresh = vi.fn()
    const wrapper = mountWith({ allResponses: map, sources: { x: 'x' }, onRefresh, debounceMs: 50 })
    onRefresh.mockClear()
    wrapper.unmount()
    eventBus.emit('substantive:adjudicated', { accountCode: 'a', auditedAmount: 1, wpCode: 'z', timestamp: 1 })
    await vi.advanceTimersByTimeAsync(60)
    expect(onRefresh).not.toHaveBeenCalled()
    vi.useRealTimers()
  })
})
