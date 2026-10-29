/**
 * CustomQueryDialog.templates.spec.ts — 弹窗「📑 模板」（advanced-query-linkage-closure 任务 33；R9.3、R9.4，AQ-16 / AQ-25）
 *
 * 原先「📑 模板」只是跳到独立页（弹窗内选不了模板），模板选择组件 MyTemplatesDialog 零挂载。现在：
 * - 打开与页面版同一个选择组件；「载入」还原数据源、排序、每页行数，弹窗不能编辑的条件 / 列照样随查询发送并写明（变异 B11-i）；
 * - 「执行」按当前项目经服务端模板执行端点（`POST /templates/{id}/execute`，重新鉴权）取第 1 页，翻页仍走它（变异 B11-h）；
 *   改排序回到普通查询；导出全部带上模板条件；未选项目时「执行」不可用。
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
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ userId: 'u-1' }) }))
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
import MyTemplatesDialog from '../MyTemplatesDialog.vue'

const TPL = {
  id: 't-big', name: '【测试】大额凭证', data_source: 'ledger_entries', scope: 'private', is_owner: true,
  config: { year: 2023, project_id: 'p-other', condition_logic: 'and',
    conditions: [{ field: 'debit_amount', op: 'gt', value: '100000000' }], selected_columns: ['voucher_no', 'debit_amount'],
    sort_field: 'debit_amount', sort_order: 'desc', page_size: 200 },
  updated_at: '2026-10-29T01:00:00',
}
const RESULT = {
  rows: [{ voucher_no: '0223', debit_amount: 241944666.92 }], columns: ['voucher_no', 'debit_amount'], total: 450, meta: {},
}

let wrapper: VueWrapper<any> | null = null
async function mountDialog(props: Record<string, unknown> = {}) {
  wrapper = mount(CustomQueryDialog, {
    props: { modelValue: true, projectId: 'p1', year: 2025, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  }) as unknown as VueWrapper<any>
  await flushPromises()
  return wrapper
}
const $ = (sel: string) => document.body.querySelector(sel) as HTMLElement | null
const posts = (url: string) => apiMocks.post.mock.calls.filter((c) => c[0] === url)
async function pick(action: 'mtd-load' | 'mtd-run') {
  $('[data-testid="cq-templates"]')!.click()
  await flushPromises()
  const row = document.body.querySelector('[data-testid="mtd-item"]') as HTMLElement
  ;(row.querySelector(`[data-testid="${action}"]`) as HTMLElement).click()
  await flushPromises()
}

beforeEach(() => {
  sessionStorage.clear()
  apiMocks.get.mockReset().mockImplementation((url: string) =>
    Promise.resolve(url === '/api/custom-query/templates' ? { templates: [TPL], total: 1 } : {}))
  apiMocks.post.mockReset().mockImplementation((url: string) =>
    Promise.resolve(url.startsWith('/api/custom-query/') && url.endsWith('execute') ? RESULT : { issues: [] }))
  downloadMock.mockReset().mockResolvedValue({})
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('「📑 模板」（R9.3、R9.4）', () => {
  it('打开共用的模板选择组件（原先跳独立页），允许执行', async () => {
    const w = await mountDialog()
    $('[data-testid="cq-templates"]')!.click()
    await flushPromises()
    const picker = w.findComponent(MyTemplatesDialog)
    expect(picker.props()).toMatchObject({ modelValue: true, allowRun: true, runBlockedReason: '' })
    expect(document.body.querySelectorAll('[data-testid="mtd-item"]')).toHaveLength(1)
  })

  it('「载入」：还原数据源、排序、每页行数；条件与列随查询发送并写明；项目与年度不取模板里存的', async () => {
    const w = await mountDialog()
    await pick('mtd-load')
    expect(w.vm.selectedSource).toBe('ledger_entries')
    expect(w.vm.sortState).toEqual({ field: 'debit_amount', direction: 'desc' })
    expect(w.vm.pageSize).toBe(200)
    expect([w.vm.localProjectId, w.vm.localYear]).toEqual(['p1', 2025])
    expect($('[data-testid="cq-template-notice"]')?.textContent).toContain('1 条筛选条件')
    expect(posts('/api/custom-query/execute')).toHaveLength(0)
    await w.vm.executeQuery()
    await flushPromises()
    expect(posts('/api/custom-query/execute')[0][1]).toMatchObject({
      project_id: 'p1', year: 2025, source: 'ledger_entries', limit: 200, offset: 0,
      conditions: [{ field: 'debit_amount', op: 'gt', value: '100000000' }], condition_logic: 'and',
      columns: ['voucher_no', 'debit_amount'], sort: [{ field: 'debit_amount', direction: 'desc' }],
    })
    expect(w.vm.templateConfig).toMatchObject({ page_size: 200, conditions: TPL.config.conditions })
    // 换数据源：模板条件不再适用，提示消失、请求不再带
    w.vm.selectedSource = 'tb_detail'
    await flushPromises()
    expect($('[data-testid="cq-template-notice"]')).toBeNull()
    await w.vm.executeQuery()
    await flushPromises()
    expect(posts('/api/custom-query/execute').at(-1)![1]).not.toHaveProperty('conditions')
  })

  it('「执行」：经模板执行端点按当前项目取第 1 页，翻页仍走它；改排序回到普通查询；导出全部带模板条件', async () => {
    const w = await mountDialog()
    await pick('mtd-run')
    const runs = posts('/api/custom-query/templates/t-big/execute')
    expect(runs).toHaveLength(1)
    expect(runs[0][1]).toEqual({ project_id: 'p1', year: 2025, limit: 200, offset: 0 })
    expect(runs[0][2]).toMatchObject({ _silent: true })
    expect(posts('/api/custom-query/execute')).toHaveLength(0)
    expect(w.vm.resultTotal).toBe(450)
    expect($('[data-testid="cq-template-notice"]')?.textContent).toContain('按模板「【测试】大额凭证」执行')
    w.vm.page = 2
    w.vm.onPageChange()
    await flushPromises()
    expect(posts('/api/custom-query/templates/t-big/execute').at(-1)![1]).toMatchObject({ offset: 200, limit: 200 })
    await w.vm.exportAll()
    expect(downloadMock.mock.calls[0][1].data).toMatchObject({ source: 'ledger_entries',
      conditions: [{ field: 'debit_amount', op: 'gt', value: '100000000' }] })
    w.vm.onSortChange({ prop: 'voucher_no', order: 'ascending' })
    await flushPromises()
    expect(posts('/api/custom-query/templates/t-big/execute')).toHaveLength(2)
    expect(posts('/api/custom-query/execute').at(-1)![1]).toMatchObject({
      sort: [{ field: 'voucher_no', direction: 'asc' }], conditions: TPL.config.conditions, offset: 0 })
  })

  it('未选项目：「执行」不可用并说明原因', async () => {
    const w = await mountDialog({ projectId: '', year: null })
    $('[data-testid="cq-templates"]')!.click()
    await flushPromises()
    expect(w.findComponent(MyTemplatesDialog).props('runBlockedReason')).toBe('请先选择项目')
    expect((document.body.querySelector('[data-testid="mtd-run"]') as HTMLButtonElement).disabled).toBe(true)
  })
})
