/**
 * VoucherDispositionButton — 凭证检查异常行的「处置」（spec voucher-workflow-linkage-lineage-closure R7）
 *
 * - 只在本行判为异常、底稿可编辑、不是年审锁定行、取得到底稿编码时出；
 * - 记入未更正错报：金额必填且 > 0，事件载荷带底稿编码、分录指纹里的科目、金额、类型与凭证描述；
 * - 去调整分录：打开本项目调整分录页。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, provide, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({ runtimeKey: Symbol('runtime-test'), emit: vi.fn() }))
vi.mock('@/components/workpaper/composables/useWorkpaperScaffold', () => ({ WorkpaperRuntimeContextKey: mocks.runtimeKey }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: mocks.emit, on: vi.fn(), off: vi.fn() } }))

import VoucherDispositionButton from '../VoucherDispositionButton.vue'

const VK = JSON.stringify(['2025', '001', '2025-01-07', 'FY', '0003'])
const LFP = JSON.stringify(['2025', '001', '2025-01-07', 'FY', '0003', '1122.01', 'D', '1000.00', 0])
const abnormalRow = (over: Record<string, unknown> = {}) => ({
  voucherNo: '0003', isAbnormal: '是', _gt: { vk: VK, lfp: LFP, src: ['engine'] }, ...over,
})

const stubs = {
  'el-popover': { template: '<div class="popover"><slot name="reference" /><div class="panel"><slot /></div></div>' },
  'el-button': {
    inheritAttrs: false,
    props: ['disabled', 'type'],
    emits: ['click'],
    template: '<button :data-testid="$attrs[\'data-testid\']" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
  },
  'el-input-number': {
    inheritAttrs: false,
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :data-testid="$attrs[\'data-testid\']" :value="modelValue ?? \'\'" @input="$emit(\'update:modelValue\', $event.target.value === \'\' ? undefined : Number($event.target.value))" />',
  },
  'el-radio-group': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="radios" :data-value="modelValue"><slot /></div>',
  },
  'el-radio-button': { props: ['value'], template: '<span class="radio" :data-value="value"><slot /></span>' },
  'router-link': { props: ['to'], template: '<a class="router-link" :data-testid="$attrs[\'data-testid\']" :data-to="JSON.stringify(to)"><slot /></a>' },
}

function mountButton(opts: { row?: unknown; readonly?: boolean; locked?: boolean; wpCode?: string } = {}) {
  const Host = defineComponent({
    setup() {
      provide(mocks.runtimeKey, { wpId: ref('wp-1'), wpCode: ref(opts.wpCode ?? 'D2'), readonly: ref(!!opts.readonly) })
      return () => h(VoucherDispositionButton, { row: opts.row ?? abnormalRow(), projectId: 'p1', locked: opts.locked })
    },
  })
  return mount(Host, { global: { stubs } })
}

beforeEach(() => mocks.emit.mockReset())

describe('何时出现', () => {
  it('异常行、可编辑、有底稿编码：出「处置」', async () => {
    const w = mountButton()
    await flushPromises()
    expect(w.find('[data-testid="voucher-disposition"]').exists()).toBe(true)
  })

  it.each([
    ['正常行', { row: abnormalRow({ isAbnormal: '否' }) }],
    ['未判定行', { row: { voucherNo: '0003', _gt: { vk: VK } } }],
    ['底稿只读', { readonly: true }],
    ['年审锁定的预审行', { locked: true }],
    ['取不到底稿编码', { wpCode: '' }],
  ])('%s：不出', async (_label, opts) => {
    const w = mountButton(opts as any)
    await flushPromises()
    expect(w.find('[data-testid="voucher-disposition"]').exists()).toBe(false)
  })
})

describe('记入未更正错报', () => {
  it('金额必填且 > 0：没填或填 0 不能记入、不发事件', async () => {
    const w = mountButton()
    await flushPromises()
    const push = w.get('[data-testid="voucher-disposition-push"]')
    expect(push.attributes('disabled')).toBeDefined()
    await w.get('[data-testid="voucher-disposition-amount"]').setValue('0')
    expect(push.attributes('disabled')).toBeDefined()
    await push.trigger('click')
    expect(mocks.emit).not.toHaveBeenCalled()
  })

  it('载荷带底稿编码、指纹里的科目、金额、类型与凭证描述', async () => {
    const w = mountButton()
    await flushPromises()
    expect(w.text()).toContain('凭证 2025-01-07 FY-0003 抽查异常')
    expect(w.text()).toContain('科目：1122.01')
    await w.get('[data-testid="voucher-disposition-amount"]').setValue('1234.5')
    ;(w.findComponent(VoucherDispositionButton).vm as any).kind = 'judgmental'
    await flushPromises()
    await w.get('[data-testid="voucher-disposition-push"]').trigger('click')
    expect(mocks.emit).toHaveBeenCalledTimes(1)
    expect(mocks.emit).toHaveBeenCalledWith('a13:push-misstatement', {
      wpCode: 'D2', accountCode: '1122.01', amount: 1234.5, misstatementType: 'judgmental',
      description: '凭证 2025-01-07 FY-0003 抽查异常',
    })
  })

  it('分录指纹缺失：科目为空，照样能记入（错报汇总里再补）', async () => {
    const w = mountButton({ row: abnormalRow({ _gt: { vk: VK } }) })
    await flushPromises()
    expect(w.text()).toContain('科目：未识别')
    await w.get('[data-testid="voucher-disposition-amount"]').setValue('10')
    await w.get('[data-testid="voucher-disposition-push"]').trigger('click')
    expect(mocks.emit.mock.calls[0][1]).toMatchObject({ accountCode: null, amount: 10, misstatementType: 'factual' })
  })
})

it('载荷经错报桥归一为一笔：描述不再追加凭证号，类型保留（同分录同金额同类型去重靠这几个字段）', async () => {
  const { normalizeMisstatementPushPayload } = await import('@/composables/useA13MisstatementBridge')
  const drafts = normalizeMisstatementPushPayload({
    wpCode: 'D2', accountCode: '1122.01', amount: 1234.5, misstatementType: 'judgmental',
    description: '凭证 2025-01-07 FY-0003 抽查异常',
  })
  expect(drafts).toEqual([{
    wpCode: 'D2', description: '凭证 2025-01-07 FY-0003 抽查异常', accountCode: '1122.01', accountName: null,
    amount: 1234.5, indexRef: '', misstatementType: 'judgmental',
  }])
})

it('去调整分录：打开本项目调整分录页', async () => {
  const w = mountButton()
  await flushPromises()
  const link = w.get('[data-testid="voucher-disposition-adjust"]')
  expect(JSON.parse(link.attributes('data-to')!)).toEqual({ name: 'Adjustments', params: { projectId: 'p1' } })
})
