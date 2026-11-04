/**
 * VoucherConclusionTag — 凭证检查行「来源」列的他稿结论（spec voucher-workflow-linkage-lineage-closure R6.1~R6.3）
 *
 * - 排除本底稿后：有异常 →「他稿异常」，有其他行 →「他稿 n」，没有 → 不显示；
 * - 点开逐底稿列编码、结论、行数，旧行注明认法，可打开该底稿（带返回当前页）；
 * - 查询失败显示「他稿结论加载失败」，点了重试（不显示成「无」）；行没有凭证身份不查；年度取凭证键自带的。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, provide, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { routeLocationKey } from 'vue-router'

const mocks = vi.hoisted(() => ({
  index: { entries: [] as any[], status: 'ready', partial: false, retry: vi.fn() },
  runtimeKey: Symbol('runtime-test'),
}))
vi.mock('@/components/workpaper/composables/useWorkpaperScaffold', () => ({ WorkpaperRuntimeContextKey: mocks.runtimeKey }))
vi.mock('@/composables/useVoucherConclusionIndex', async () => {
  const { computed } = await import('vue')
  return {
    useVoucherConclusionIndex: vi.fn(() => ({
      entries: computed(() => mocks.index.entries),
      status: computed(() => mocks.index.status),
      partial: computed(() => mocks.index.partial),
      retry: mocks.index.retry,
    })),
  }
})

import { useVoucherConclusionIndex } from '@/composables/useVoucherConclusionIndex'
import VoucherConclusionTag from '../VoucherConclusionTag.vue'

const VK = JSON.stringify(['2025', '001', '2025-01-07', 'FY', '0003'])
const ROW = { voucherNo: '0003', _gt: { vk: VK } }
const CURRENT = '/projects/p1/workpapers/wp-self/edit?sheet=a'

const stubs = {
  'el-popover': { template: '<div class="popover"><slot name="reference" /><div class="panel"><slot /></div></div>' },
  'el-button': {
    inheritAttrs: false,
    props: ['type', 'size', 'link'],
    emits: ['click'],
    template: '<button :data-testid="$attrs[\'data-testid\']" :title="$attrs.title" :data-type="type" @click="$emit(\'click\', $event)"><slot /></button>',
  },
  'el-tag': { props: ['type'], template: '<span class="tag" :data-type="type"><slot /></span>' },
  'router-link': { props: ['to'], template: '<a class="router-link" :data-to="JSON.stringify(to)"><slot /></a>' },
}

function mountTag(row: unknown = ROW) {
  const Host = defineComponent({
    setup() {
      provide(mocks.runtimeKey, { wpId: ref('wp-self'), readonly: ref(false) })
      provide(routeLocationKey, { fullPath: CURRENT } as any)
      return () => h(VoucherConclusionTag, { row, projectId: 'p1' })
    },
  })
  return mount(Host, { global: { stubs } })
}

const entry = (id: string, code: string, verdict: string, over: Record<string, unknown> = {}) => ({
  working_paper_id: id, wp_code: code, wp_name: `${code} 凭证检查`, verdict, rows: 2, legacy: false, ...over,
})

beforeEach(() => {
  mocks.index.entries = []
  mocks.index.status = 'ready'
  mocks.index.partial = false
  mocks.index.retry.mockReset()
  vi.mocked(useVoucherConclusionIndex).mockClear()
})

describe('标签', () => {
  it('排除本底稿后有异常 →「他稿异常」（危险色）', async () => {
    mocks.index.entries = [entry('wp-self', 'D2', 'normal'), entry('wp-e1', 'E1', 'normal'), entry('wp-k8', 'K8', 'abnormal')]
    const w = mountTag()
    await flushPromises()
    const tag = w.get('[data-testid="voucher-conclusion-tag"]')
    expect(tag.text()).toBe('他稿异常')
    expect(tag.attributes('data-type')).toBe('danger')
  })

  it('只有本底稿判了异常不算他稿异常；其余 →「他稿 n」', async () => {
    mocks.index.entries = [entry('wp-self', 'D2', 'abnormal'), entry('wp-e1', 'E1', 'normal'), entry('wp-k8', 'K8', 'unknown')]
    const w = mountTag()
    await flushPromises()
    const tag = w.get('[data-testid="voucher-conclusion-tag"]')
    expect(tag.text()).toBe('他稿 2')
    expect(tag.attributes('data-type')).toBe('info')
  })

  it('只有本底稿的行：不显示', async () => {
    mocks.index.entries = [entry('wp-self', 'D2', 'abnormal')]
    const w = mountTag()
    await flushPromises()
    expect(w.html()).not.toContain('他稿')
  })

  it('行没有凭证身份：不查、不显示', async () => {
    const w = mountTag({ voucherNo: '0003' })
    await flushPromises()
    expect(w.html()).not.toContain('他稿')
    const keyArg = vi.mocked(useVoucherConclusionIndex).mock.calls[0][2] as () => string | null
    expect(keyArg()).toBeNull()
  })

  it('年度取凭证键自带的（宿主给「来源」列的年度常是 0）', async () => {
    mountTag()
    await flushPromises()
    const yearArg = vi.mocked(useVoucherConclusionIndex).mock.calls[0][1] as () => number | null
    expect(yearArg()).toBe(2025)
  })

  it('查询失败：显示「他稿结论加载失败」，点了重试；无权时提示原因', async () => {
    mocks.index.status = 'error'
    const w = mountTag()
    await flushPromises()
    const err = w.get('[data-testid="voucher-conclusion-error"]')
    expect(err.text()).toBe('他稿结论加载失败')
    await err.trigger('click')
    expect(mocks.index.retry).toHaveBeenCalledTimes(1)
    mocks.index.status = 'forbidden'
    const w2 = mountTag()
    await flushPromises()
    expect(w2.get('[data-testid="voucher-conclusion-error"]').attributes('title')).toContain('无权查看')
  })
})

describe('弹层', () => {
  it('逐底稿列编码、结论、行数；旧行注明认法；截断提示；打开底稿带返回当前页', async () => {
    mocks.index.entries = [
      entry('wp-self', 'D2', 'abnormal'),
      entry('wp-e1', 'E1', 'normal', { rows: 1, legacy: true }),
      entry('wp-k8', 'K8', 'abnormal', { rows: 3 }),
    ]
    mocks.index.partial = true
    const w = mountTag()
    await flushPromises()
    const panel = w.get('[data-testid="voucher-conclusion-panel"]')
    const text = panel.text()
    expect(text).toContain('FY-0003')
    expect(text).toContain('E1 E1 凭证检查')
    expect(text).toContain('K8 K8 凭证检查')
    expect(text).toContain('3 行')
    expect(text).toContain('旧行按凭证号和日期认出')
    expect(text).toContain('结果可能不全')
    expect(text).not.toContain('D2 凭证检查')
    expect(panel.findAll('.tag').map((t) => [t.text(), t.attributes('data-type')])).toEqual([['正常', 'success'], ['异常', 'danger']])
    const links = panel.findAll('a.router-link').map((a) => JSON.parse(a.attributes('data-to') || '{}'))
    expect(links).toEqual([
      { name: 'WorkpaperEditor', params: { projectId: 'p1', wpId: 'wp-e1' }, query: { returnTo: CURRENT } },
      { name: 'WorkpaperEditor', params: { projectId: 'p1', wpId: 'wp-k8' }, query: { returnTo: CURRENT } },
    ])
  })
})
