/**
 * 账务查询悬浮来源（spec citar-cell-source-hover R6）：列来源 + 行来源合成一张卡片；科目余额表金额格带来源键；
 * 页面补出的上级行按下级合计（本地算，不请求行来源）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { cellSourceLink, localSource, mergeLedgerSources } from '../cellSource'

const h = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.get, put: vi.fn(), post: vi.fn() } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {}, params: { projectId: 'p1' } }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/composables/useManualEditPermission', () => ({
  MANUAL_EDIT_DENIED_TIP: '无权修改', useManualEditPermission: () => ({ canManualEdit: ref(false) }),
}))
vi.mock('../citarLedgerEdits', () => ({
  editBalanceRow: vi.fn(), restoreLedgerRow: vi.fn(), parseMoneyInput: Number, fetchManualEdits: vi.fn().mockResolvedValue([]),
}))

import CitarBalanceTab from '../components/CitarBalanceTab.vue'
import CitarImportJobDetail from '../components/CitarImportJobDetail.vue'
import CitarSourceCard from '../components/CitarSourceCard.vue'

describe('mergeLedgerSources', () => {
  it('列表头 + 行上舍弃的映射值合成；行有问题时带上', () => {
    const col = localSource('import', '导入的科目余额表', null, {
      items: [{ label: '余额表.xlsx · 余额表 ·「科目名称」', detail: '映射为「科目名称」（用户确认）', amount: null, sign: '1', link: null }],
    })
    const row = localSource('import', '本行导入时的情况', null, {
      items: [{ label: '未采用「科目名称」：备用金', detail: null, amount: null, sign: '0', link: null }],
      issue: '同一字段映射了多列',
    })
    const m = mergeLedgerSources(col, row, '现金')!
    expect(m.value).toBe('现金')
    expect(m.items.map(i => i.label)).toEqual(['余额表.xlsx · 余额表 ·「科目名称」', '未采用「科目名称」：备用金'])
    expect(m.issue).toBe('同一字段映射了多列')
  })

  it('人工修改写成说明，卡片标为手工修改', () => {
    const row = localSource('manual', '本行人工修改过', null, {
      manual: { value: null, auto: null, by_name: '甲', at: '2026-11-05T08:30:00', note: '导入原值：期末 8' },
    })
    const m = mergeLedgerSources(localSource('import', '导入的科目余额表'), row, '10')!
    expect(m.kind).toBe('manual')
    expect(m.manual).toBeNull()
    expect(m.notes[0]).toBe('人工修改过：甲 · 2026-11-05 08:30；导入原值：期末 8')
  })

  it('两边都没有返回 null', () => {
    expect(mergeLedgerSources(null, null, '1')).toBeNull()
  })
})

const bal = (over: Record<string, unknown>) => ({
  account_code: '1002', account_name: '银行存款', level: 1, opening_balance: 0, debit_amount: 0, credit_amount: 0,
  closing_balance: 0, opening_direction: 'debit', closing_direction: 'debit', ...over,
})

describe('科目余额表悬浮来源', () => {
  beforeEach(() => {
    h.get.mockReset()
    h.get.mockImplementation((url: string) => {
      if (url.includes('cell-sources')) {
        return Promise.resolve({ year: 2025, cells: { 'col:closing': localSource('import', '导入的科目余额表（由 甲 导入）', null) }, notices: [] })
      }
      return Promise.resolve([
        bal({ account_code: '1002', account_name: '银行存款', closing_balance: 300, _is_synthetic: true }),
        bal({ id: 'r1', account_code: '100201', account_name: '工行', level: 2, closing_balance: 100 }),
        bal({ id: 'r2', account_code: '100202', account_name: '建行', level: 2, closing_balance: 200 }),
      ])
    })
  })
  afterEach(() => vi.useRealTimers())

  async function hover(w: ReturnType<typeof mount>, key: string) {
    vi.useFakeTimers()
    await w.find(`[data-src="${key}"]`).trigger('mouseover')
    vi.advanceTimersByTime(400)
    vi.useRealTimers()
    await flushPromises()
  }

  it('导入行：列来源；补出的上级行：按下级合计 ＝ 格值', async () => {
    const w = mount(CitarBalanceTab, { props: { projectId: 'p1', year: 2025, entityName: '甲' }, attachTo: document.body })
    await flushPromises()
    await hover(w, 'r1|closing')
    expect(w.find('.src-card').text()).toContain('导入的科目余额表（由 甲 导入）')
    expect(w.find('.src-card').text()).toContain('100201 工行 · 期末余额')
    await hover(w, 'syn:1002|closing')
    const text = w.find('.src-card').text()
    expect(text).toContain('按下级末级科目合计补出')
    expect(text).toContain('100201 工行')
    expect(text).toContain('100202 建行')
    expect(text).toContain('＝ 格值')
    w.unmount()
  })

  it('点映射项：交给账务查询页跳转；有科目正在修改时先挡下（R9）', async () => {
    const link = { page: 'ledger_import' as const, code: 'job-1', ref: '余额表.xlsx|余额表|6' }
    h.get.mockImplementation((url: string) => {
      if (url.includes('cell-sources')) {
        return Promise.resolve({ year: 2025, cells: { 'col:closing': localSource('import', '导入的科目余额表', null, {
          items: [{ label: '余额表.xlsx · 余额表 ·「期末余额」', detail: '映射为「期末余额」（用户确认）', amount: null, sign: '1', link }],
        }) }, notices: [] })
      }
      return Promise.resolve([bal({ id: 'r1', account_code: '100201', account_name: '工行', level: 2, closing_balance: 100 })])
    })
    const w = mount(CitarBalanceTab, { props: { projectId: 'p1', year: 2025, entityName: '甲' }, attachTo: document.body })
    await flushPromises()
    await hover(w, 'r1|closing')
    await w.find('.src-card__link').trigger('click')
    expect(w.emitted('open-source')).toEqual([[link]])
    expect(w.find('.src-card').exists()).toBe(false)

    ;(w.vm as any).$.setupState.editingId = 'r1'
    await flushPromises()
    // 编辑中的格子本就不弹卡片：直接发卡片的 open 事件，验证跳转被挡下
    w.findComponent(CitarSourceCard).vm.$emit('open', link)
    expect(w.emitted('open-source')).toHaveLength(1)
    w.unmount()
  })
})

describe('cellSourceLink：导入记录', () => {
  it('带作业 ⇒ 数据导入页 ?job=&locate=；不带 ⇒ 只进数据导入页', () => {
    expect(cellSourceLink({ page: 'ledger_import', code: 'job-1', ref: '余额表.xlsx|余额表|6' }))
      .toEqual({ segment: 'ledger-import', query: { job: 'job-1', locate: '余额表.xlsx|余额表|6' } })
    expect(cellSourceLink({ page: 'ledger_import', code: 'job-1' })).toEqual({ segment: 'ledger-import', query: { job: 'job-1' } })
    expect(cellSourceLink({ page: 'ledger_import' })).toEqual({ segment: 'ledger-import', query: {} })
  })
})

describe('导入记录详情', () => {
  const VIEW = {
    job: { id: 'job-1', year: 2025, status: 'completed', status_label: '已完成', created_at: '2026-11-04T08:00:00', completed_at: null, created_by_name: 'admin' },
    dataset: { id: 'ds', status: 'active', status_label: '当前生效', is_current: true, records: [{ label: '科目余额表', count: 287 }] },
    file_retained: false,
    has_mapping_record: true,
    sheets: [{
      file: '余额表.xlsx', sheet: '余额表', table_type: 'balance', table_label: '科目余额表', confirmed_by_user: true,
      columns: [
        { column_index: 0, column_letter: 'A', header: '科目编号', field: 'account_code', field_label: '科目编码', locate: '余额表.xlsx|余额表|0' },
        { column_index: 6, column_letter: 'G', header: '本年借方', field: 'debit_amount', field_label: '借方发生额', locate: '余额表.xlsx|余额表|6' },
      ],
    }],
  }

  // 花括号：表达式体会把 mockReset 返回的 mock 当成 teardown 交给 vitest，每例后再调一次（memory 前端三坑①）
  beforeEach(() => {
    h.get.mockReset()
  })

  it('按文件 / sheet 列出原表头 → 字段，高亮定位的那一列；写明原文件已清理', async () => {
    h.get.mockResolvedValue(VIEW)
    const w = mount(CitarImportJobDetail, { props: { projectId: 'p1', jobId: 'job-1', locate: '余额表.xlsx|余额表|6' }, attachTo: document.body })
    await flushPromises()
    expect(h.get.mock.calls[0][0]).toBe('/api/projects/p1/ledger-import/jobs/job-1/mappings')
    const text = w.text()
    expect(text).toContain('余额表.xlsx · 余额表')
    expect(text).toContain('当前生效')
    expect(text).toContain('科目余额表 287 行')
    expect(text).toContain('原文件已在导入后清理')
    const located = w.findAll('tr.citar-located')
    expect(located).toHaveLength(1)
    expect(located[0].text()).toContain('G')
    expect(located[0].text()).toContain('本年借方')
    expect(located[0].text()).toContain('借方发生额')
    w.unmount()
  })

  it('作业不存在 / 不属于本项目：写明原因', async () => {
    h.get.mockRejectedValue({ response: { status: 404 } })
    const w = mount(CitarImportJobDetail, { props: { projectId: 'p1', jobId: 'x' } })
    await flushPromises()
    expect(w.text()).toContain('没有找到这次导入的记录')
    w.unmount()
  })
})
