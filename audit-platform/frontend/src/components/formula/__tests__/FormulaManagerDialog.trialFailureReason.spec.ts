/**
 * 报表试算失败原因显示在界面上（spec formula-hub-integrity-closure 第 2 轮 A5；阶段 D 浏览器实测 ① 的部分通过项）。
 *
 * 原状：「⚡ 应用自动运算」55 条中 1 条失败时只提示「54 条成功，1 条失败」，失败行计算值显示「-」，失败原因
 * （如「ROW('BS-127')：引用的行次不存在或尚未计算」）只在响应里 —— onApplyFormulas 只存 value / trace。
 * 本文件挂载 FormulaManagerDialog（表格、列、提示框换成直接渲染行与插槽的桩，其余子组件照常桩掉），
 * 走真实 onApplyFormulas，读计算值列里渲染出的原因与提示里点名的行次。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { computed, defineComponent, h, inject, provide, type ComputedRef } from 'vue'
import ElementPlus from 'element-plus'

const { get, put, post, msg, scopeLoad, scopeGetRows, acnrListSheets, acnrListCells, getNoteTree } = vi.hoisted(() => {
  const fn: any = vi.fn()
  fn.warning = vi.fn(); fn.success = vi.fn(); fn.info = vi.fn(); fn.error = vi.fn()
  return {
    get: vi.fn(), put: vi.fn(), post: vi.fn(), msg: fn,
    scopeLoad: vi.fn(), scopeGetRows: vi.fn(() => []),
    acnrListSheets: vi.fn(), acnrListCells: vi.fn(), getNoteTree: vi.fn(),
  }
})
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg }
})
vi.mock('@/services/apiProxy', () => ({ api: { get, put, post } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/formula/FormulaEditDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/formula/FormulaHistoryTab.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/shared/SharedTemplatePicker.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/import/UnifiedImportDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteTree: getNoteTree }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmtAmount: (v: unknown) => String(v ?? '') }),
}))
vi.mock('@/stores/addressRegistry', () => ({ useAddressRegistry: () => ({ loaded: false, tbAddresses: [] }) }))
vi.mock('@/composables/useFormulaScopeCatalog', async () => {
  const { ref } = await import('vue')
  return {
    useFormulaScopeCatalog: () => ({
      loadScope: scopeLoad, resolveSources: vi.fn(async () => undefined), getScopeRows: scopeGetRows,
      loadGlobal: vi.fn(async () => ({})), resolveScopeSources: vi.fn(async () => undefined), allRows: ref([]),
      totalCount: ref(0), loading: ref(false),
      globalGrouped: ref({ note: [], consol_note: [], consol_worksheet: [], consol_report: [], report: [], tb: [],
        workpaper: [] }),
    }),
    SCOPE_LABEL_MAP: {},
  }
})
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    listSheets: acnrListSheets, listCells: acnrListCells, resolve: vi.fn(), resolveFormula: vi.fn(),
    resolveUri: vi.fn(), resolveAddr: vi.fn(), resolveIndex: vi.fn(), resolveInstance: vi.fn(),
  }),
}))
vi.mock('@/services/apiPaths', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, linkageBus: {}, formulaAuditLog: { list: '/api/formula-audit-logs' } }
})

import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'

// 表格桩：每列按表格数据逐行渲染默认插槽（真实 el-table 在 jsdom 里不渲染单元格内容）
const ROWS_KEY = Symbol('rows')
const ElTable = defineComponent({
  name: 'ElTable', props: { data: { type: Array, default: () => [] } },
  setup(props, { slots }) {
    provide(ROWS_KEY, computed(() => props.data as any[]))
    return () => h('div', { class: 'stub-table' }, slots.default?.())
  },
})
const ElTableColumn = defineComponent({
  name: 'ElTableColumn', props: { label: String, prop: String },
  setup(props, { slots }) {
    const rows = inject<ComputedRef<any[]>>(ROWS_KEY, computed(() => []))
    return () => h('div', { class: 'stub-col', 'data-label': props.label ?? '' }, rows.value.map((row, i) =>
      h('div', { class: 'stub-cell', 'data-row': row.row_code }, slots.default?.({ row, $index: i }))))
  },
})
const ElTooltip = defineComponent({
  name: 'ElTooltip',
  setup(_, { slots }) {
    return () => h('span', { class: 'stub-tooltip' }, [slots.default?.(), h('span', { class: 'stub-tooltip-content' },
      slots.content?.())])
  },
})
const ElDialog = defineComponent({
  name: 'ElDialog', setup(_, { slots }) { return () => h('div', { class: 'stub-dialog' }, slots.default?.()) },
})

const REASON = "ROW('BS-127')：引用的行次不存在或尚未计算"
const ROWS = [
  { id: 'r1', row_code: 'BS-001', row_name: '货币资金', formula: "TB('1001','期末余额')", formula_category: 'auto_calc' },
  { id: 'r2', row_code: 'BS-128', row_name: '合计', formula: "ROW('BS-127')", formula_category: 'auto_calc' },
]

function create() {
  return shallowMount(FormulaManagerDialog, {
    props: { modelValue: false, rows: [], scope: 'report', projectId: 'project-1', year: 2025, templateType: 'soe' },
    // 只有这四个组件渲染插槽（主表在 el-dialog 下的原生 div 里）；其余子组件照常桩掉、不渲染插槽
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false, stubs: { ElTable, ElTableColumn, ElTooltip, ElDialog } },
  })
}

function valueCell(w: ReturnType<typeof create>, rowCode: string) {
  const col = w.findAll('.stub-col').find(c => c.attributes('data-label') === '计算值')
  expect(col, '没有「计算值」列').toBeTruthy()
  const cell = col!.findAll('.stub-cell').find(c => c.attributes('data-row') === rowCode)
  expect(cell, `「计算值」列没有 ${rowCode}`).toBeTruthy()
  return cell!
}

describe('报表试算：失败原因显示在计算值提示里，提示点名失败行次', () => {
  beforeEach(() => {
    get.mockReset(); post.mockReset(); Object.values(msg).forEach((f: any) => f.mockReset?.())
    get.mockImplementation(async (url: string) => (String(url).includes('report-config/types') ? [] : {}))
    scopeLoad.mockReset(); scopeLoad.mockResolvedValue([])
    acnrListSheets.mockReset(); acnrListSheets.mockResolvedValue([])
    acnrListCells.mockReset(); acnrListCells.mockResolvedValue([])
    getNoteTree.mockReset(); getNoteTree.mockResolvedValue([])
  })

  it('1 条失败：失败行显示「-」与原因，成功行显示值、没有原因；提示里列出失败行次', async () => {
    const w = create()
    await w.setProps({ modelValue: true })
    for (let i = 0; i < 4; i++) await flushPromises()
    const s = (w.vm as any).$.setupState
    s.allRowsMap.balance_sheet = ROWS
    s.selectedNodeKey = 'report_balance_sheet'
    await flushPromises()
    post.mockResolvedValue({
      results: [
        { row_code: 'BS-001', value: 150, trace: [{ type: 'TB', code: '1001', value: '150' }], error: null },
        { row_code: 'BS-128', value: null, trace: [], error: REASON },
      ],
      row_values: { 'BS-001': 150 },
    })
    await s.onApplyFormulas()
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][1]).toMatchObject({ project_id: 'project-1', year: 2025 })
    const failed = valueCell(w, 'BS-128')
    expect(failed.find('[data-testid="formula-result-error"]').text()).toBe(`失败原因：${REASON}`)
    expect(failed.text()).toContain('-')
    const ok = valueCell(w, 'BS-001')
    expect(ok.find('[data-testid="formula-result-error"]').exists()).toBe(false)
    expect(ok.text()).toContain('150')
    expect(msg.warning).toHaveBeenCalledWith('执行完成：1 条成功，1 条失败（BS-128），失败原因见计算值提示')
    w.unmount()
  })
})
