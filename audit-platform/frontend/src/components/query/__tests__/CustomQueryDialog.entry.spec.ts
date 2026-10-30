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

describe('「导出全部」按本次查询的快照（B10 评审非阻塞 #1）', () => {
  it('查询后换了数据源但没重新查询：导出的数据源、筛选与文件名仍是上一次查询的', async () => {
    const w = await mountDialog({ initialSource: 'report_income_statement' })
    await w.vm.executeQuery()
    await flushPromises()
    w.vm.selectedSource = 'tb_detail'
    await flushPromises()
    await w.vm.exportAll()
    expect(downloadMock).toHaveBeenCalledTimes(1)
    const body = downloadMock.mock.calls[0][1].data
    expect(body).toMatchObject({ source: 'report_income_statement', filters: { report_type: 'income_statement' } })
    expect(body.file_name).toContain('利润表')
    expect(body.file_name).not.toContain('试算')
  })
})
