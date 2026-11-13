/**
 * CustomQueryDialog.entry.spec.ts — 弹窗的入口预选与说明（advanced-query-linkage-closure 任务 31；R10.3、R10.5）
 *
 * - 每次打开都套用布局给的 initialSource（原先只在它变化时套用：同一页再开一次、或用户换过源后再开，预选不生效，变异 B11-f）；
 * - 入口说明 initialNotice（模板库附注按钮：模板章节号与项目附注编号不同）显示在结果区上方，用户换数据源即清除（变异 B11-g），
 *   关闭弹窗也清除；
 * - 「导出全部」按本次查询的快照导出（B10 评审非阻塞 #1）：查询后换了数据源、改了选区但没重新查询，文件名与筛选仍按上一次查询。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))
const downloadMock = vi.hoisted(() => vi.fn())
vi.mock('@/utils/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/http')>()),
  default: { get: vi.fn().mockResolvedValue({ data: [], headers: {} }), post: vi.fn() },
  downloadFile: downloadMock,
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), resolve: vi.fn(() => ({ href: '/x' })) }),
  useRoute: () => ({ params: {}, query: {} }),
}))
vi.mock('@/services/commonApi', () => ({
  listProjectsWithProgress: vi.fn().mockResolvedValue([{ id: 'p1', name: '【测试】项目一', audit_year: 2025 }]),
}))
vi.mock('@/composables/useQueryBuilderAccess', async () => {
  const { computed } = await import('vue')
  return { useQueryBuilderAccess: () => ({ canUseBuilder: computed(() => true), builderDisabledReason: computed(() => '') }) }
})
vi.mock('@/views/AdvancedQueryBuilder.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ props: { embedded: Boolean, projectId: String, year: Number }, setup: () => () => h('div') }) }
})
vi.mock('@/components/query/SheetCellRangePicker.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ props: ['modelValue', 'wpCode', 'sheetName', 'projectId', 'year'], setup: () => () => h('div') }) }
})
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return { ...actual, ElMessage: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }) }
})

import ElementPlus from 'element-plus'
import CustomQueryDialog from '../CustomQueryDialog.vue'
import { TEMPLATE_NOTE_NOTICE } from '../queryEntryContext'

const RESULT = {
  rows: [{ standard_account_code: '1001', account_name: '库存现金', audited_amount: 100 }],
  columns: ['standard_account_code', 'account_name', 'audited_amount'], total: 1, meta: {},
}

let wrapper: VueWrapper<any> | null = null
async function mountDialog(props: Record<string, unknown> = {}): Promise<VueWrapper<any>> {
  wrapper = mount(CustomQueryDialog, {
    props: { modelValue: true, projectId: 'p1', year: 2025, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  }) as unknown as VueWrapper<any>
  await flushPromises()
  return wrapper
}
const notice = () => document.body.querySelector('[data-testid="cq-entry-notice"]') as HTMLElement | null

beforeEach(() => {
  sessionStorage.clear()
  apiMocks.get.mockReset().mockResolvedValue({})
  apiMocks.post.mockReset().mockImplementation((url: string) =>
    Promise.resolve(url === '/api/custom-query/execute' ? RESULT : { issues: [] }))
  downloadMock.mockReset().mockResolvedValue({})
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('入口预选（R10.3）', () => {
  it('打开即选中布局给的数据源；用户换过源后关了再开，仍按入口预选', async () => {
    const w = await mountDialog({ initialSource: 'tb_detail' })
    expect(w.vm.selectedSource).toBe('tb_detail')
    w.vm.selectedSource = 'account_balance'
    await flushPromises()
    await w.setProps({ modelValue: false })
    await flushPromises()
    await w.setProps({ modelValue: true })
    await flushPromises()
    expect(w.vm.selectedSource, '同一入口再开一次应重新预选').toBe('tb_detail')
  })

  it('没有入口预选（非项目页 / 工作台）：不改动当前数据源', async () => {
    const w = await mountDialog({ projectId: '', year: null })
    expect(w.vm.selectedSource).toBe('report_balance_sheet')
    expect(notice()).toBeNull()
  })
})

describe('入口说明（R10.5，AQ-38）', () => {
  it('附注模板：落附注目录并显示编号体系提示；换数据源即清除', async () => {
    const w = await mountDialog({ initialSource: 'disclosure', initialNotice: TEMPLATE_NOTE_NOTICE })
    expect(w.vm.selectedSource).toBe('disclosure')
    expect(notice()?.textContent).toContain(TEMPLATE_NOTE_NOTICE)
    w.vm.selectedSource = 'tb_detail'
    await flushPromises()
    expect(notice(), '换了数据源，说明不再适用').toBeNull()
  })

  it('关闭弹窗即清除说明；不带说明的入口不显示', async () => {
    const w = await mountDialog({ initialSource: 'disclosure', initialNotice: TEMPLATE_NOTE_NOTICE })
    expect(notice()).not.toBeNull()
    await w.setProps({ modelValue: false, initialNotice: undefined, initialSource: 'tb_detail' })
    await flushPromises()
    expect(w.vm.entryNotice).toBeNull()
    await w.setProps({ modelValue: true })
    await flushPromises()
    expect(notice()).toBeNull()
  })
})

/** 试算表 1002 右键「按此查询明细」带来的入口（形状同 QueryDetailEntry.spec 的事件载荷） */
const W6_ENTRY = {
  kind: 'tb_row', projectId: 'p1', year: 2025, source: 'ledger_entries',
  filters: { account_code: '1002' }, label: '试算表 1002 银行存款',
  switches: [{ source: 'account_balance', label: '科目余额' }],
}
const executeCalls = () => apiMocks.post.mock.calls.filter(([url]) => url === '/api/custom-query/execute')

describe('业务页入口（W6，ADR-AQL-20）：打开即套用并查询一次', () => {
  it('首次挂载时已可见且带入口（布局首次打开才挂载本弹窗）：照样立即查询，不抛 TDZ', async () => {
    // 2026-11-04 候选栈浏览器实测：immediate watch 注册在 templateRun 等声明之前 ⇒ 这里抛
    // 「Cannot access 'templateRun' before initialization」、被 void 吞掉，只套了上下文、一次都没查。
    const rejections: unknown[] = []
    const onRejection = (reason: unknown) => { rejections.push(reason) }
    process.on('unhandledRejection', onRejection)
    try {
      const w = await mountDialog({ entry: W6_ENTRY })
      await flushPromises()
      expect(rejections, String(rejections[0])).toEqual([])
      const calls = executeCalls()
      expect(calls).toHaveLength(1)
      expect(calls[0][1]).toMatchObject({
        project_id: 'p1', year: 2025, source: 'ledger_entries', filters: { account_code: '1002' },
      })
      expect(w.vm.hasQueried).toBe(true)
      expect(w.vm.queryEntry.entry.value?.label).toBe('试算表 1002 银行存款')
    } finally {
      process.off('unhandledRejection', onRejection)
    }
  })

  it('已挂载（关着）后再带入口打开：同样只查一次', async () => {
    const w = await mountDialog({ modelValue: false })
    expect(executeCalls()).toHaveLength(0)
    await w.setProps({ modelValue: true, entry: W6_ENTRY })
    await flushPromises()
    expect(executeCalls()).toHaveLength(1)
    expect(executeCalls()[0][1]).toMatchObject({ source: 'ledger_entries', filters: { account_code: '1002' } })
  })
})

describe('查询定义变化使旧结果失效', () => {
  it('查询后换数据源但没重新查询：旧结果不可继续导出', async () => {
    const w = await mountDialog({ initialSource: 'report_income_statement' })
    await w.vm.executeQuery()
    await flushPromises()
    expect(w.vm.canExport).toBe(true)
    w.vm.selectedSource = 'tb_detail'
    await flushPromises()
    expect(w.vm.canExport).toBe(false)
    expect(w.vm.hasQueried).toBe(false)
    await w.vm.exportAll()
    expect(downloadMock).not.toHaveBeenCalled()
  })
})
