/**
 * 分录汇总表（spec consol-autotree-linkage-closure R9 前端 / 任务 19）
 *
 * - 挂载即按项目 / 年度读 entry-summary（每次进入本表都重读）；暴露 load 供分录变化 / 推送后重读；
 * - 金额只展示后端值（同合并试算口径），含草稿净额与已审批不同的格高亮；
 * - 与合并试算对账：一致给标签，不一致列科目；已落库试算过期 ⇒「重新推送」走合并页统一入口；
 * - 未归属分录单列；加载失败给中文原因。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

const { getConsolEntrySummary, emitSpy } = vi.hoisted(() => ({
  getConsolEntrySummary: vi.fn(),
  emitSpy: vi.fn(),
}))
vi.mock('@/services/consolidationApi', () => ({ getConsolEntrySummary: (...a: any[]) => getConsolEntrySummary(...a) }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: (...a: any[]) => emitSpy(...a), on: vi.fn(), off: vi.fn() } }))

import EntrySummarySheet from '../worksheets/EntrySummarySheet.vue'

const Table = defineComponent({
  props: ['data'],
  provide() { return { rows: () => (this as any).data || [] } },
  setup(_, { slots, attrs }) { return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, slots.default?.()) },
})
const Column = defineComponent({
  inject: ['rows'],
  props: ['label', 'prop'],
  setup(props, { slots }) {
    return function (this: any) {
      return h('div', { 'data-label': props.label }, this.rows().map((r: any) =>
        h('div', { class: 'cell' }, slots.default ? slots.default({ row: r }) : String(r[props.prop] ?? ''))))
    }
  },
})
const Btn = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit, attrs }) {
    return () => h('button', { 'data-testid': (attrs as any)['data-testid'], onClick: () => emit('click') }, slots.default?.())
  },
})
const Pass = defineComponent({
  props: ['title'],
  setup(p, { slots, attrs }) {
    return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, [p.title, slots.default?.(), slots.title?.()])
  },
})
const Amount = defineComponent({ props: ['value'], setup(p) { return () => h('span', { class: 'amt' }, String(p.value ?? '')) } })
const STUBS = {
  'el-table': Table, 'el-table-column': Column, 'el-button': Btn, 'el-alert': Pass, 'el-tag': Pass,
  'el-select': Pass, 'el-option': true, GtAmountCell: Amount,
}

function summary(extra: Record<string, unknown> = {}) {
  return {
    year: 2025,
    rows: [
      { node_key: 'G:consol_elim', node_label: '某集团（差额户）', hosted_here: true, account_code: '1122', account_name: '应收账款',
        entry_type: 'internal_ar_ap', type_label: '内部往来抵消', measure: 'elimination', debit: '0.00', credit: '100.00',
        net: '-100.00', draft_net: '-130.00', entry_count: 1 },
      { node_key: 'A:consol_elim', node_label: '甲公司（差额户）', hosted_here: false, account_code: '2202', account_name: '应付账款',
        entry_type: 'internal_ar_ap', type_label: '内部往来抵消', measure: 'elimination', debit: '100.00', credit: '0.00',
        net: '-100.00', draft_net: '-100.00', entry_count: 1 },
    ],
    by_type: [{ entry_type: 'internal_ar_ap', type_label: '内部往来抵消', debit: '100.00', credit: '100.00', net: '-200.00', draft_net: '-230.00', entry_count: 1 }],
    totals: { debit: '100.00', credit: '100.00', difference: '0.00', balanced: true, entry_count: 1 },
    reconcile: { matched: true, mismatches: [], persisted_stale: false, stale_accounts: [] },
    orphans: [],
    warnings: [],
    ...extra,
  }
}

function mountSheet(props: Record<string, unknown> = {}) {
  return mount(EntrySummarySheet, {
    props: { projectId: 'p-g', year: 2025, ...props },
    global: { stubs: STUBS, directives: { loading: {} } },
  })
}

describe('EntrySummarySheet 分录汇总表', () => {
  beforeEach(() => {
    getConsolEntrySummary.mockReset().mockResolvedValue(summary())
    emitSpy.mockReset()
  })

  it('挂载即按项目 / 年度读取，展示后端金额；含草稿净额不同的格高亮，下级项目录入的差额户标出', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    expect(getConsolEntrySummary).toHaveBeenCalledWith('p-g', 2025)
    const rows = wrapper.find('[data-testid="es-rows"]')
    expect(rows.text()).toContain('某集团（差额户）')
    expect(rows.text()).toContain('1122 应收账款')
    expect(rows.text()).toContain('-130.00')
    // 第一行含草稿 -130 ≠ 已审批 -100 ⇒ 高亮；第二行相同不高亮；类型合计行同理
    expect(rows.findAll('.es-draft-diff')).toHaveLength(1)
    expect(wrapper.find('[data-testid="es-by-type"]').findAll('.es-draft-diff')).toHaveLength(1)
    expect(rows.text()).toContain('在下级合并项目录入')
    expect(wrapper.find('[data-testid="es-balance"]').text()).toBe('借贷平衡')
    expect(wrapper.find('[data-testid="es-reconcile-ok"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="es-mismatch"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="es-warnings"]').exists()).toBe(false)
  })

  it('已落库试算过期 ⇒ 提示并可「重新推送」（合并页统一入口）；对账不一致列出科目；未归属分录单列', async () => {
    getConsolEntrySummary.mockResolvedValueOnce(summary({
      totals: { debit: '100.00', credit: '90.00', difference: '10.00', balanced: false, entry_count: 1 },
      reconcile: {
        matched: false, persisted_stale: true, stale_accounts: ['1122'],
        mismatches: [{ account_code: '1122', account_name: '应收账款', summary_adjustment: '0.00', trial_adjustment: '0.00',
          summary_elimination: '-100.00', trial_elimination: '-90.00' }],
      },
      orphans: [{ entry_no: 'CE-009', reason: '分录涉及的企业不在企业树中', review_status: 'approved', review_status_label: '已审批' }],
      warnings: ['已落库的合并试算与当前分录不一致（1 个科目），请重新推送', '分录 CE-002（内部往来抵消，草稿）使相关科目余额同时增加，借贷方向可能录反'],
    }))
    const wrapper = mountSheet()
    await flushPromises()
    const warn = wrapper.find('[data-testid="es-warnings"]')
    expect(warn.text()).toContain('需关注 2 项')
    expect(warn.text()).toContain('借贷方向可能录反')
    await wrapper.find('[data-testid="es-repush"]').trigger('click')
    expect(emitSpy).toHaveBeenCalledWith('consol-request-push')
    expect(wrapper.find('[data-testid="es-balance"]').text()).toBe('借贷不平：差额 10.00')
    expect(wrapper.find('[data-testid="es-mismatch"]').text()).toContain('-90.00')
    expect(wrapper.find('[data-testid="es-reconcile-ok"]').exists()).toBe(false)
    const orphans = wrapper.find('[data-testid="es-orphans"]')
    expect(orphans.text()).toContain('CE-009')
    expect(orphans.text()).toContain('已审批')
  })

  it('没有过期时不出「重新推送」；加载失败给中文原因；暴露的 load 重新读取', async () => {
    getConsolEntrySummary.mockResolvedValueOnce(summary({ warnings: ['1 笔分录找不到归属的差额节点，未计入（见未归属分录）'] }))
    const wrapper = mountSheet()
    await flushPromises()
    expect(wrapper.find('[data-testid="es-warnings"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="es-repush"]').exists()).toBe(false)

    getConsolEntrySummary.mockRejectedValueOnce(new Error('网络异常'))
    await (wrapper.vm as any).load()
    await flushPromises()
    expect(getConsolEntrySummary).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="es-error"]').text()).toContain('分录汇总表加载失败：网络异常')
    expect(wrapper.find('[data-testid="es-rows"]').exists()).toBe(false)
  })

  it('「前往合并抵消分录」切到明细表；项目或年度变化重读', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    await wrapper.find('[data-testid="es-goto-elim"]').trigger('click')
    expect(wrapper.emitted('goto-sheet')?.[0]).toEqual(['elimination'])
    await wrapper.setProps({ year: 2026 })
    await flushPromises()
    expect(getConsolEntrySummary).toHaveBeenLastCalledWith('p-g', 2026)
  })

  it('迟到的旧响应不覆盖新结果', async () => {
    let resolveOld!: (v: unknown) => void
    getConsolEntrySummary.mockImplementationOnce(() => new Promise((r) => { resolveOld = r }))
    const wrapper = mountSheet()
    getConsolEntrySummary.mockResolvedValueOnce(summary({ by_type: [], rows: [] }))
    await (wrapper.vm as any).load()
    await flushPromises()
    resolveOld(summary())
    await flushPromises()
    expect(wrapper.find('[data-testid="es-rows"]').text()).not.toContain('某集团（差额户）')
  })
})
