import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { api, service, confirmDangerous, messages, roleState } = vi.hoisted(() => ({
  api: { get: vi.fn(), put: vi.fn() },
  service: {
    createConsolNoteFormula: vi.fn(), deleteConsolNoteFormula: vi.fn(),
    listConsolNoteFormulas: vi.fn(), pushConsolidation: vi.fn(),
    reseedConsolNoteFormulas: vi.fn(), updateConsolNoteFormula: vi.fn(),
  } as Record<string, ReturnType<typeof vi.fn>>,
  confirmDangerous: vi.fn(),
  messages: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  roleState: { effectiveRole: 'manager' },
}))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('@/services/consolidationApi', () => Object.fromEntries(
  Object.keys(service).map((key) => [key, (...args: any[]) => service[key](...args)]),
))
vi.mock('@/utils/confirm', () => ({ confirmDangerous }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: messages }
})
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { role: roleState.effectiveRole } }) }))
vi.mock('@/stores/roleContext', () => ({ useRoleContextStore: () => roleState }))
vi.mock('@/components/consolidation/ConsolPushPanel.vue', () => ({ default: { template: '<div data-testid="push-stub" />' } }))

import ConsolFormulaManagementPanel from '../ConsolFormulaManagementPanel.vue'
import {
  CONSOL_REPORT_TREE_ITEMS, consolReportNodeOfType, consolReportTypeOfNode, consolidatedStandard,
} from '../consolFormulaManagement'

const REPORT_ROW = {
  id: 'bs-1', row_code: 'BS-002', row_name: '货币资金',
  formula: "TB('1001','期末余额')", formula_category: 'auto_calc', formula_description: '原说明',
}
const NOTE_ROW = {
  id: 'n1', template_type: 'soe', section_id: '五-1-1', row_index: 0, col_index: 1,
  row_label: '库存现金', col_name: '期末余额', position: '第 1 行 · 期末余额（库存现金）',
  formula: "TB('1001','期末余额')", source: 'seed', source_label: '自动种子',
  description: null, updated_at: null, updated_by: null,
}
function noteList() {
  return {
    template_type: 'soe', count: 1,
    sections: [{ section_id: '五-1-1', title: '货币资金', parent_section: '五、报表科目', formulas: [{ ...NOTE_ROW }] }],
  }
}

function create(props: Record<string, unknown>) {
  return shallowMount(ConsolFormulaManagementPanel, {
    props: { mode: 'report', projectId: 'p1', year: 2025, templateType: 'soe', reportType: 'balance_sheet', ...props },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
}
const state = (wrapper: ReturnType<typeof create>) => (wrapper.vm as any).$.setupState

beforeEach(() => {
  api.get.mockReset(); api.put.mockReset()
  Object.values(service).forEach((fn) => fn.mockReset())
  Object.values(messages).forEach((fn) => fn.mockReset())
  confirmDangerous.mockReset(); confirmDangerous.mockResolvedValue(undefined)
  roleState.effectiveRole = 'manager'
  api.get.mockImplementation(async (url: string) =>
    String(url).includes('consol-note-sections')
      ? [{ label: '五、报表科目', children: [{ section_id: '五-1-1', title: '货币资金' }, { section_id: '五-2-1', title: '应收账款' }] }]
      : [{ ...REPORT_ROW }],
  )
  api.put.mockResolvedValue({})
  service.listConsolNoteFormulas.mockResolvedValue(noteList())
  service.updateConsolNoteFormula.mockImplementation(async (_id: string, payload: any) => ({
    ...NOTE_ROW, formula: payload.formula, description: payload.description, source: 'manual', source_label: '人工',
  }))
  service.createConsolNoteFormula.mockResolvedValue({ ...NOTE_ROW, id: 'n2' })
  service.deleteConsolNoteFormula.mockResolvedValue({ id: 'n1', deleted: true })
  service.reseedConsolNoteFormulas.mockResolvedValue({ inserted: 2, kept_manual: 1 })
  service.pushConsolidation.mockResolvedValue({ queued: true, message: '已开始推送', project_id: 'p1', year: 2025 })
})

describe('合并公式节点映射', () => {
  it('六类节点逐值映射真实 report_type，权益表不得漂成 equity_changes', () => {
    expect(CONSOL_REPORT_TREE_ITEMS).toHaveLength(6)
    expect(CONSOL_REPORT_TREE_ITEMS.map((item) => consolReportTypeOfNode(item.key))).toEqual([
      'balance_sheet', 'income_statement', 'cash_flow_statement',
      'equity_statement', 'cash_flow_supplement', 'impairment_provision',
    ])
    expect(consolReportNodeOfType('equity_statement')).toBe('consol_report_eq')
    expect(consolidatedStandard('listed')).toBe('listed_consolidated')
  })
})

describe('合并报表公式', () => {
  it('精确读取 `{tpl}_consolidated`，不请求 project 或 standalone 口径', async () => {
    const wrapper = create({ mode: 'report', reportType: 'equity_statement', templateType: 'listed' })
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith('/api/report-config', {
      params: { report_type: 'equity_statement', applicable_standard: 'listed_consolidated' },
    })
    expect(api.get.mock.calls.some(([, cfg]) => String(cfg?.params?.applicable_standard).includes('standalone'))).toBe(false)
    expect(state(wrapper).reportRows).toHaveLength(1)
    wrapper.unmount()
  })

  it('模板影响确认后 PUT；写成功才按 formula_changed 推送当前项目', async () => {
    const wrapper = create({ mode: 'report' })
    await flushPromises()
    state(wrapper).startReportEdit(state(wrapper).reportRows[0])
    state(wrapper).editFormula = "TB('1002','期末余额')"
    state(wrapper).editCategory = 'logic_check'
    state(wrapper).editDescription = '新说明'
    await state(wrapper).saveReportRow(state(wrapper).reportRows[0])
    expect(confirmDangerous).toHaveBeenCalledWith(expect.objectContaining({ title: '修改合并报表公式确认' }))
    expect(api.put).toHaveBeenCalledWith('/api/report-config/bs-1', {
      formula: "TB('1002','期末余额')", formula_category: 'logic_check', formula_description: '新说明',
      project_id: 'p1', year: 2025, template_type: 'soe',
    })
    expect(service.pushConsolidation).toHaveBeenCalledWith('p1', 2025, 'formula_changed')
    expect(state(wrapper).reportRows[0].formula).toBe("TB('1002','期末余额')")
    wrapper.unmount()
  })

  it('取消影响确认时零 PUT/零推送；推送失败不回滚已保存公式并单独提示', async () => {
    const wrapper = create({ mode: 'report' })
    await flushPromises()
    state(wrapper).startReportEdit(state(wrapper).reportRows[0])
    confirmDangerous.mockRejectedValueOnce(new Error('cancel'))
    await state(wrapper).saveReportRow(state(wrapper).reportRows[0])
    expect(api.put).not.toHaveBeenCalled()
    expect(service.pushConsolidation).not.toHaveBeenCalled()

    confirmDangerous.mockResolvedValueOnce(undefined)
    service.pushConsolidation.mockRejectedValueOnce(new Error('push failed'))
    state(wrapper).editFormula = 'ROW(\'BS-001\')'
    await state(wrapper).saveReportRow(state(wrapper).reportRows[0])
    expect(api.put).toHaveBeenCalledTimes(1)
    expect(state(wrapper).reportRows[0].formula).toBe("ROW('BS-001')")
    expect(messages.warning).toHaveBeenCalledWith(expect.stringContaining('公式已保存，但合并推送启动失败'))
    wrapper.unmount()
  })
})

describe('合并附注公式', () => {
  it('加载完整章节并按调用章节定位；修改返回人工来源并推送', async () => {
    const wrapper = create({ mode: 'note', noteSection: '五-1-1' })
    await flushPromises()
    expect(service.listConsolNoteFormulas).toHaveBeenCalledWith('soe')
    expect(state(wrapper).noteSectionOptions.map((item: any) => item.section_id)).toEqual(['五-1-1', '五-2-1'])
    expect(state(wrapper).selectedSectionId).toBe('五-1-1')
    state(wrapper).startNoteEdit(state(wrapper).noteRows[0])
    state(wrapper).editFormula = "TB('1002','期末余额')"
    state(wrapper).editDescription = '人工修订'
    await state(wrapper).saveNoteRow(state(wrapper).noteRows[0])
    expect(service.updateConsolNoteFormula).toHaveBeenCalledWith('n1', {
      formula: "TB('1002','期末余额')", description: '人工修订',
    })
    expect(state(wrapper).noteRows[0]).toMatchObject({ source: 'manual', source_label: '人工' })
    expect(service.pushConsolidation).toHaveBeenCalledWith('p1', 2025, 'formula_changed')
    wrapper.unmount()
  })

  it('新增把用户 1-based 行号转为 0-based；删除软删后都只推送一次', async () => {
    const wrapper = create({ mode: 'note', noteSection: '五-1-1' })
    await flushPromises()
    state(wrapper).createFormRef = { validate: vi.fn(async () => true) }
    Object.assign(state(wrapper).createForm, {
      rowNumber: 3, colIndex: 2, formula: "REPORT('BS-002')", description: '新增',
    })
    await state(wrapper).createNoteRow()
    expect(service.createConsolNoteFormula).toHaveBeenCalledWith({
      template_type: 'soe', section_id: '五-1-1', row_index: 2, col_index: 2,
      formula: "REPORT('BS-002')", description: '新增',
    })
    expect(service.pushConsolidation).toHaveBeenCalledTimes(1)

    service.pushConsolidation.mockClear()
    await state(wrapper).removeNoteRow(state(wrapper).noteRows[0])
    expect(service.deleteConsolNoteFormula).toHaveBeenCalledWith('n1')
    expect(service.pushConsolidation).toHaveBeenCalledTimes(1)
    expect(confirmDangerous).toHaveBeenCalledWith(expect.objectContaining({ confirmText: '确认删除' }))
    wrapper.unmount()
  })

  it('审计员只读：不能进入编辑、删除或种子化', async () => {
    roleState.effectiveRole = 'auditor'
    const wrapper = create({ mode: 'note' })
    await flushPromises()
    expect(state(wrapper).canManage).toBe(false)
    state(wrapper).startNoteEdit(state(wrapper).noteRows[0])
    await state(wrapper).removeNoteRow(state(wrapper).noteRows[0])
    await state(wrapper).reseed()
    expect(state(wrapper).editingId).toBeNull()
    expect(service.deleteConsolNoteFormula).not.toHaveBeenCalled()
    expect(service.reseedConsolNoteFormulas).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
