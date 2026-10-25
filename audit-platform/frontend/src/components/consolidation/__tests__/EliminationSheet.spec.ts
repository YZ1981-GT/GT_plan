/**
 * 合并抵消分录明细表（spec consol-elimination-single-source-push 任务 10.4 / 需求 1~2）
 *
 * - 只读分录表：明细行、合计三行、按状态的操作；下级合并项目承载的行只读并给前往链接；
 * - 新增分录用共用表单（归属 = hosted_nodes 下拉）；
 * - 待生成：挂载即 dry_run 预演（只声明负责的来源、只带这些来源的分组）；生成会删草稿时先二次确认；
 * - 旧版自定义行：提示条 + 转为草稿分录；
 * - 不再调用旧同步路径（不写 consol_worksheet_data['elimination']、不逐行 POST）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

const { api, confirm, mockPush, message } = vi.hoisted(() => ({
  api: {
    getEliminationTreeLines: vi.fn(),
    generateEliminationsFromWorksheet: vi.fn(),
    getLegacyEliminationSheet: vi.fn(),
    convertLegacyEliminationSheet: vi.fn(),
    getWorksheetAccounts: vi.fn(),
    reviewElimination: vi.fn(),
    deleteElimination: vi.fn(),
    createElimination: vi.fn(),
    updateElimination: vi.fn(),
  } as Record<string, ReturnType<typeof vi.fn>>,
  confirm: {
    confirmDangerous: vi.fn(),
    confirmDelete: vi.fn(),
    promptRejectReason: vi.fn(),
  },
  mockPush: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/consolidationApi', () => Object.fromEntries(
  Object.keys(api).map((k) => [k, (...a: any[]) => api[k](...a)]),
))
vi.mock('@/utils/confirm', () => ({
  confirmDangerous: (...a: any[]) => confirm.confirmDangerous(...a),
  confirmDelete: (...a: any[]) => confirm.confirmDelete(...a),
  promptRejectReason: (...a: any[]) => confirm.promptRejectReason(...a),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mockPush }) }))
vi.mock('element-plus', () => ({ ElMessage: message }))
vi.mock('@/composables/useExcelIO', () => ({ exportData: vi.fn() }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmt: (v: unknown) => (v == null ? '—' : String(v)), fontConfig: { tableFont: '12px' } }),
}))

import EliminationSheet from '../worksheets/EliminationSheet.vue'

// 依赖注入式表格替身：逐行渲染列插槽
const Table = defineComponent({
  props: ['data'],
  provide() { return { rows: () => (this as any).data || [] } },
  setup(_, { slots, attrs }) { return () => h('div', { class: 'tbl', 'data-testid': (attrs as any)['data-testid'] }, slots.default?.()) },
})
const Column = defineComponent({
  inject: ['rows'],
  props: ['label'],
  setup(props, { slots }) {
    return function (this: any) {
      return h('div', { class: 'col', 'data-label': props.label },
        this.rows().map((row: any, i: number) => h('div', { class: 'cell' }, slots.default?.({ row, $index: i }))))
    }
  },
})
const Btn = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit, attrs }) {
    return () => h('button', { 'data-testid': (attrs as any)['data-testid'], disabled: (attrs as any).disabled, onClick: () => emit('click') }, slots.default?.())
  },
})
const Pass = (tag: string) => defineComponent({
  setup(_, { slots, attrs }) {
    return () => h(tag, { 'data-testid': (attrs as any)['data-testid'] }, [slots.title?.(), slots.default?.()])
  },
})
const FormStub = defineComponent({
  props: ['modelValue', 'targets', 'entry', 'accounts'],
  setup(p) { return () => (p.modelValue ? h('div', { 'data-testid': 'form-stub', 'data-targets': JSON.stringify(p.targets) }) : null) },
})
const STUBS = {
  'el-table': Table, 'el-table-column': Column, 'el-button': Btn, 'el-link': Btn,
  'el-alert': Pass('div'), 'el-tag': Pass('span'), 'el-tooltip': Pass('span'),
  GtAmountCell: defineComponent({ props: ['value'], setup: (p) => () => h('span', { class: 'amt' }, String(p.value ?? '')) }),
  ConsolElimEntryForm: FormStub,
}

const TOTALS = {
  all: { debit: '160.00', credit: '160.00', difference: '0.00', entry_count: 2 },
  approved: { debit: '100.00', credit: '100.00', difference: '0.00', entry_count: 1 },
  counted: { debit: '100.00', credit: '100.00', difference: '0.00', entry_count: 1 },
}
function line(entryNo: string, extra: Record<string, unknown> = {}) {
  return {
    entry_id: `id-${entryNo}`, entry_no: entryNo, origin: null, origin_label: '手工录入', origin_key: null,
    node_key: 'G:consol_elim', node_label: '某集团（合并差额）', branch_entity_code: null,
    host_project_id: 'p-g', host_project_name: '某集团', readonly: false,
    entry_type: 'internal_ar_ap', entry_type_label: '内部往来抵销', description: '往来', review_status: 'draft',
    review_status_label: '草稿', counted: false, orphan_reason: null, related_company_codes: [],
    line_index: 1, line_count: 2, account_code: '2202', account_name: '应付账款', debit: '60.00', credit: '0.00',
    ...extra,
  }
}
const ROWS = [
  line('IA-001'),
  line('IA-001', { line_index: 2, account_code: '1122', account_name: '应收账款', debit: '0.00', credit: '60.00' }),
  line('EQ-001', { review_status: 'approved', review_status_label: '已审批', counted: true, line_count: 1, entry_type: 'equity' }),
  line('IA-009', { host_project_id: 'p-a', host_project_name: '甲公司', readonly: true, line_count: 1 }),
]
const HOSTED = [
  { node_key: 'G:consol_elim', label: '某集团（合并差额）', branch_entity_code: null },
  { node_key: 'G:branch_elim', label: '某集团（母分差额）', branch_entity_code: 'G' },
]
function dryResult(extra: Record<string, unknown> = {}) {
  return {
    year: 2025, standard: 'soe_consolidated', dry_run: true, created: 1, updated: 0, unchanged: 0, discarded: 0,
    deleted: 0, blocked: [], changed_after_review: [], deleted_entries: [], warnings: [],
    groups: [{
      origin: 'ws_internal_trade', origin_label: '内部交易', origin_key: 'internal_trade:revenue', action: 'created',
      entry_id: null, entry_no: null, review_status: null, entry_type: 'internal_trade', entry_type_label: '内部交易抵销',
      description: '内部交易收入与成本抵销', related_company_codes: ['A', 'B'], debit_total: '5.00', credit_total: '5.00',
      lines: [
        { index: 1, subject: '营业收入', detail: null, direction: 'debit', amount: '5.00', account_code: '6001', account_name: '主营业务收入', source: '本集团科目', note: '按「主营业务收入」匹配', in_report: true, warning: null, reason: null },
        { index: 2, subject: '营业成本', detail: null, direction: 'credit', amount: '5.00', account_code: '6401', account_name: '主营业务成本', source: '本集团科目', note: null, in_report: true, warning: null, reason: null },
      ],
      reasons: [], warnings: [],
    }],
    ...extra,
  }
}
const GROUPS = [
  { origin: 'ws_internal_trade', origin_key: 'internal_trade:revenue', description: 'x', lines: [], related_company_codes: [] },
  { origin: 'ws_equity_sim', origin_key: 'equity_sim:step1:A', description: 'y', lines: [], related_company_codes: [] },
]

function mountSheet(props: Record<string, unknown> = {}) {
  return mount(EliminationSheet, {
    props: { projectId: 'p-g', year: 2025, sourceGroups: GROUPS, sourceOrigins: ['ws_internal_trade'], ...props },
    global: { stubs: STUBS, directives: { loading: {} } },
  })
}

describe('EliminationSheet', () => {
  beforeEach(() => {
    Object.values(api).forEach((f) => f.mockReset())
    Object.values(confirm).forEach((f) => f.mockReset())
    confirm.confirmDangerous.mockResolvedValue(undefined)
    confirm.confirmDelete.mockResolvedValue(undefined)
    confirm.promptRejectReason.mockResolvedValue('需核对')
    Object.values(message).forEach((f) => f.mockClear())
    mockPush.mockClear()
    api.getEliminationTreeLines.mockResolvedValue({ year: 2025, project_id: 'p-g', rows: ROWS, hosted_nodes: HOSTED, totals: TOTALS })
    api.generateEliminationsFromWorksheet.mockImplementation((_pid: string, body: any) =>
      Promise.resolve(body.dry_run ? dryResult() : { ...dryResult(), dry_run: false }))
    api.getLegacyEliminationSheet.mockResolvedValue({ ...dryResult(), custom_row_count: 0, skipped_zero_rows: 0, group_count: 0, pending: 0, message: '没有旧版自定义抵销行', groups: [] })
    api.getWorksheetAccounts.mockResolvedValue({ year: 2025, accounts: [] })
    api.reviewElimination.mockResolvedValue({})
    api.deleteElimination.mockResolvedValue(undefined)
  })

  it('挂载：读明细行与合计三行；预演只声明负责的来源、只带这些来源的分组（dry_run，不写库）', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    expect(api.getEliminationTreeLines).toHaveBeenCalledWith('p-g', 2025)
    expect(wrapper.find('[data-testid="elim-total-all"]').text()).toContain('全部分录（2 笔）')
    expect(wrapper.find('[data-testid="elim-total-counted"]').text()).toContain('计入合并数（1 笔）')
    expect(wrapper.find('[data-testid="elim-total-counted"]').text()).toContain('✓ 平衡')
    const [pid, body, opts] = api.generateEliminationsFromWorksheet.mock.calls[0]
    expect(pid).toBe('p-g')
    expect(body).toMatchObject({ year: 2025, dry_run: true, origins: ['ws_internal_trade'] })
    expect(body.groups.map((g: any) => g.origin_key)).toEqual(['internal_trade:revenue'])
    expect(opts).toEqual({ silent: true })
    expect(wrapper.find('[data-testid="elim-pending-summary"]').text()).toBe('共 1 组，将新建 1')
    expect(wrapper.find('[data-testid="elim-pending-missing"]').text()).toContain('模拟权益法、内部往来表尚无已保存的数据')
    expect(wrapper.find('[data-testid="elim-pending-action-0"]').text()).toBe('将新建')
  })

  it('按状态给操作：草稿可提交 / 删除，已审批可撤销审批；只读行给前往链接无操作', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    expect(wrapper.find('[data-testid="elim-sheet-submit-IA-001"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="elim-sheet-delete-IA-001"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="elim-sheet-revoke-EQ-001"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="elim-sheet-submit-EQ-001"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="elim-sheet-submit-IA-009"]').exists()).toBe(false)

    // 撤销审批须二次确认：取消 ⇒ 不调接口
    confirm.confirmDangerous.mockRejectedValueOnce(new Error('cancel'))
    await wrapper.find('[data-testid="elim-sheet-revoke-EQ-001"]').trigger('click')
    await flushPromises()
    expect(confirm.confirmDangerous.mock.calls[0][0].message).toContain('撤销分录 EQ-001 的审批')
    expect(api.reviewElimination).not.toHaveBeenCalled()

    await wrapper.find('[data-testid="elim-sheet-revoke-EQ-001"]').trigger('click')
    await flushPromises()
    expect(confirm.confirmDangerous).toHaveBeenCalledTimes(2)
    expect(api.reviewElimination).toHaveBeenCalledWith('id-EQ-001', 'p-g', { action: 'revoke' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(api.getEliminationTreeLines.mock.calls.length).toBeGreaterThanOrEqual(2)

    await wrapper.find('[data-testid="elim-sheet-delete-IA-001"]').trigger('click')
    await flushPromises()
    expect(confirm.confirmDelete).toHaveBeenCalledWith('分录 IA-001')
    expect(api.deleteElimination).toHaveBeenCalledWith('id-IA-001', 'p-g')

    await wrapper.find('[data-testid="elim-sheet-goto-IA-009"]').trigger('click')
    expect(mockPush).toHaveBeenCalledWith({ path: '/projects/p-a/consolidation', query: { year: '2025' } })
  })

  it('新增分录：共用表单，归属节点下拉 = 本项目承载的差额节点', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    await wrapper.find('[data-testid="elim-sheet-new"]').trigger('click')
    await flushPromises()
    expect(JSON.parse(wrapper.find('[data-testid="form-stub"]').attributes('data-targets')!)).toEqual(HOSTED)
    expect(api.getWorksheetAccounts).toHaveBeenCalledWith('p-g', 2025)
  })

  it('生成草稿分录：会删除草稿时先二次确认；取消则不写库；确认后真生成（dry_run=false）并刷新', async () => {
    api.generateEliminationsFromWorksheet.mockImplementation((_pid: string, body: any) => Promise.resolve(body.dry_run
      ? dryResult({ deleted: 1, deleted_entries: [{ origin: 'ws_internal_trade', origin_key: 'internal_trade:unrealized', entry_id: 'x', entry_no: 'UP-003', review_status: 'draft' }] })
      : { ...dryResult(), dry_run: false, created: 1, deleted: 1 }))
    const wrapper = mountSheet()
    await flushPromises()
    expect(wrapper.find('[data-testid="elim-pending-summary"]').text()).toContain('将删除草稿 1 笔')

    confirm.confirmDangerous.mockRejectedValueOnce(new Error('cancel'))
    await wrapper.find('[data-testid="elim-pending-generate"]').trigger('click')
    await flushPromises()
    expect(api.generateEliminationsFromWorksheet.mock.calls.filter((c) => !c[1].dry_run)).toHaveLength(0)

    await wrapper.find('[data-testid="elim-pending-generate"]').trigger('click')
    await flushPromises()
    expect(confirm.confirmDangerous.mock.calls.at(-1)?.[0].message).toContain('UP-003')
    const real = api.generateEliminationsFromWorksheet.mock.calls.filter((c) => !c[1].dry_run)
    expect(real).toHaveLength(1)
    expect(real[0][1]).toMatchObject({ dry_run: false, origins: ['ws_internal_trade'] })
    expect(message.success).toHaveBeenCalledWith('已生成草稿分录：新建 1 笔、删除 1 笔')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('没有可写入的变化 ⇒「生成草稿分录」禁用；预演失败在页面上说明（403 给权限提示）', async () => {
    api.generateEliminationsFromWorksheet.mockResolvedValue(dryResult({ created: 0, groups: [{ ...dryResult().groups[0], action: 'unchanged' }] }))
    const w1 = mountSheet()
    await flushPromises()
    expect(w1.find('[data-testid="elim-pending-generate"]').attributes('disabled')).toBeDefined()
    expect(w1.find('[data-testid="elim-pending-table"]').exists()).toBe(false)

    api.generateEliminationsFromWorksheet.mockRejectedValue({ response: { status: 403 } })
    const w2 = mountSheet()
    await flushPromises()
    expect(w2.find('[data-testid="elim-pending-summary"]').text()).toBe('需要本项目的编辑权限才能预览与生成草稿分录')
  })

  it('旧版自定义行：提示条 + 转为草稿分录（确认后调用转入接口）', async () => {
    api.getLegacyEliminationSheet.mockResolvedValue({
      ...dryResult(), custom_row_count: 3, skipped_zero_rows: 0, group_count: 2, pending: 2,
      message: '检测到旧版自定义抵销行 3 条，旧版数据未参与合并计算',
    })
    api.convertLegacyEliminationSheet.mockResolvedValue({
      ...dryResult(), dry_run: false, created: 2, custom_row_count: 3, skipped_zero_rows: 0, group_count: 2, pending: 0,
      message: '检测到旧版自定义抵销行 3 条，旧版数据未参与合并计算',
    })
    const wrapper = mountSheet()
    await flushPromises()
    expect(wrapper.find('[data-testid="elim-legacy-banner"]').text()).toContain('检测到旧版自定义抵销行 3 条，旧版数据未参与合并计算')
    await wrapper.find('[data-testid="elim-legacy-convert"]').trigger('click')
    await flushPromises()
    expect(api.convertLegacyEliminationSheet).toHaveBeenCalledWith('p-g', 2025)
    expect(message.success).toHaveBeenCalledWith('已转入 2 笔草稿分录')
    expect(wrapper.find('[data-testid="elim-legacy-convert"]').exists()).toBe(false)
  })

  it('来源分组变化 ⇒ 去抖后重新预演', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSheet()
      await flushPromises()
      const before = api.generateEliminationsFromWorksheet.mock.calls.length
      await wrapper.setProps({ sourceGroups: [GROUPS[0], { ...GROUPS[0], origin_key: 'internal_trade:unrealized' }] })
      await wrapper.setProps({ sourceGroups: [GROUPS[0]] })
      vi.advanceTimersByTime(700)
      await flushPromises()
      expect(api.generateEliminationsFromWorksheet.mock.calls.length).toBe(before + 1)
    } finally {
      vi.useRealTimers()
    }
  })
})
