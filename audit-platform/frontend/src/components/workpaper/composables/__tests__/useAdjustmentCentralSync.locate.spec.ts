/**
 * useAdjustmentCentralSync 的分录组定位（调整分录页「底稿 X」跳来源底稿，spec wp-deeplink-locate-residual-closure 需求 1.2）：
 * 挂载即登记、卸载即注销；item_id 是本页签分录组则认领并高亮分录表；按类型分组的页签先切到该类型，认不出还原原类型。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'

vi.mock('element-plus', () => ({
  ElMessage: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  ElMessageBox: { confirm: vi.fn() },
}))
vi.mock('@/services/auditPlatformApi', () => ({
  syncAdjustmentFromWorkpaper: vi.fn(),
  getAdjustmentBySourceRef: vi.fn(async () => ({})),
}))
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: vi.fn(() => ({ close: vi.fn() })),
}))

import { useAdjustmentCentralSync, type AdjustmentEntryType } from '../useAdjustmentCentralSync'
import { adjustmentEntryGroupRegistrationCount, locateAdjustmentEntryGroup } from '@/composables/adjustmentEntryGroupLocate'
import { GT_LOCATE_HIGHLIGHT_CLASS } from '@/composables/useCellLocate'

const wrappers: VueWrapper[] = []
afterEach(() => {
  while (wrappers.length) wrappers.pop()!.unmount()
  document.body.innerHTML = ''
})

function host(opts: { dual?: boolean; table?: boolean; fragment?: boolean; wpId?: string } = {}) {
  const activeType = ref<AdjustmentEntryType>('AJE')
  const Host = defineComponent({
    setup() {
      useAdjustmentCentralSync({
        projectId: ref('p1'),
        year: ref(2025),
        wpId: ref(opts.wpId ?? 'wp-1'),
        wpCode: opts.dual ? 'L1' : 'D4',
        itemId: opts.dual ? () => `L1-adj-${activeType.value}` : 'D4-4-rows',
        ...(opts.dual ? { entryType: activeType } : {}),
        buildLineItems: () => [],
        buildMeta: () => ({ description: '', adjustmentType: 'aje' }),
        autoSync: false,
      })
      return () => {
        const body = [h('div', { class: 'head' }, '调整分录汇总'), opts.table === false ? null : h('div', { class: 'el-table', id: 'entries' })]
        return opts.fragment ? [h('section', { id: 'first' }, body), h('div', { id: 'second' })] : h('div', { id: 'root' }, body)
      }
    },
  })
  const w = mount(Host, { attachTo: document.body })
  wrappers.push(w)
  return { w, activeType }
}

describe('useAdjustmentCentralSync 分录组定位', () => {
  it('单一分录组：认领本页签的 item_id 并高亮分录表；别的 item_id 不认', async () => {
    host()
    await nextTick()
    expect(locateAdjustmentEntryGroup('wp-1', 'D4-5-rows')).toBe(false)
    expect(locateAdjustmentEntryGroup('wp-1', 'D4-4-rows')).toBe(true)
    expect(document.querySelector('#entries')!.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    expect(locateAdjustmentEntryGroup('wp-2', 'D4-4-rows')).toBe(false)
  })

  it('按类型分组：切到 item_id 对应的类型；认不出的还原原类型', async () => {
    const { activeType } = host({ dual: true })
    await nextTick()
    expect(locateAdjustmentEntryGroup('wp-1', 'L1-adj-RJE')).toBe(true)
    expect(activeType.value).toBe('RJE')
    expect(locateAdjustmentEntryGroup('wp-1', 'L1-adj-XJE')).toBe(false)
    expect(activeType.value).toBe('RJE')
    expect(locateAdjustmentEntryGroup('wp-1', 'L2-adj-AJE')).toBe(false)
    expect(activeType.value).toBe('RJE')
    expect(locateAdjustmentEntryGroup('wp-1', 'L1-adj-AJE')).toBe(true)
    expect(activeType.value).toBe('AJE')
  })

  it('卸载即注销', async () => {
    const before = adjustmentEntryGroupRegistrationCount()
    const { w } = host()
    await nextTick()
    expect(adjustmentEntryGroupRegistrationCount()).toBe(before + 1)
    w.unmount()
    wrappers.pop()
    expect(adjustmentEntryGroupRegistrationCount()).toBe(before)
    expect(locateAdjustmentEntryGroup('wp-1', 'D4-4-rows')).toBe(false)
  })

  it('没有表格时高亮页签根元素；多根节点时取第一个元素里的表格', async () => {
    host({ table: false })
    await nextTick()
    expect(locateAdjustmentEntryGroup('wp-1', 'D4-4-rows')).toBe(true)
    expect(document.querySelector('#root')!.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    wrappers.pop()!.unmount()
    host({ fragment: true, wpId: 'wp-3' })
    await nextTick()
    expect(locateAdjustmentEntryGroup('wp-3', 'D4-4-rows')).toBe(true)
    expect(document.querySelector('#first #entries')!.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
  })
})
