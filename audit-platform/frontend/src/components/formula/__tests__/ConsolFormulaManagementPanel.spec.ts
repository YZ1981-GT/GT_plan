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
  formula_version: 3,
}
const NOTE_ROW = {
  id: 'n1', template_type: 'soe', section_id: '五-1-1', row_index: 0, col_index: 1,
  row_label: '库存现金', col_name: '期末余额', position: '第 1 行 · 期末余额（库存现金）',
  formula: "TB('1001','期末余额')", source: 'seed', source_label: '自动种子',
  description: null, updated_at: null, updated_by: null, version: 2,
}
function noteList(canEditGlobal = true) {
  return {
    template_type: 'soe', count: 1, can_edit_global: canEditGlobal,
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

  // 格内编辑（spec excel-style-table-editing 5.5）：每格提交先记下，攒成一批确认一次 → 同一行合并成一次 PUT → 推送一次
  it('同一行三格提交：界面先显示新值，确认一次、一次 PUT（合并三格）、写成功才推送一次', async () => {
    const wrapper = create({ mode: 'report' })
    await flushPromises()
    const s = state(wrapper)
    const row = s.reportRows[0]
    s.onCellEdit(row, 'formula', "TB('1002','期末余额')")
    s.onCellEdit(row, 'formula_category', 'logic_check')
    s.onCellEdit(row, 'formula_description', '新说明')
    expect(s.cellValue(row, 'formula')).toBe("TB('1002','期末余额')")
    expect(row.formula).toBe("TB('1001','期末余额')") // 保存成功前不改行
    await s.flushCellEdits()
    expect(confirmDangerous).toHaveBeenCalledTimes(1)
    expect(confirmDangerous).toHaveBeenCalledWith(expect.objectContaining({ title: '修改合并报表公式确认' }))
    // 公式版本原样带回（后端 CAS：缺失 428、已被他人修改 409）
    expect(api.put.mock.calls).toEqual([['/api/report-config/bs-1', {
      formula: "TB('1002','期末余额')", formula_category: 'logic_check', formula_description: '新说明',
      expected_version: 3, project_id: 'p1', year: 2025, template_type: 'soe',
    }]])
    expect(service.pushConsolidation.mock.calls).toEqual([['p1', 2025, 'formula_changed']])
    expect(row).toMatchObject({ formula: "TB('1002','期末余额')", formula_category: 'logic_check', formula_description: '新说明' })
    wrapper.unmount()
  })

  it('只改一格：其余两格按行上的值带上；清空公式存 null', async () => {
    const wrapper = create({ mode: 'report' })
    await flushPromises()
    const s = state(wrapper)
    s.onCellEdit(s.reportRows[0], 'formula', '')
    await s.flushCellEdits()
    expect(api.put.mock.calls[0][1]).toMatchObject({ formula: null, formula_category: 'auto_calc', formula_description: '原说明' })
    expect(s.reportRows[0].formula).toBeNull()
    wrapper.unmount()
  })

  it('提交 200ms 后自动保存；改回原值不算修改（零确认零请求）', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = create({ mode: 'report' })
      await flushPromises()
      const s = state(wrapper)
      const row = s.reportRows[0]
      s.onCellEdit(row, 'formula', "TB('1001','期末余额')") // 与行上的值相同
      s.onCellEdit(row, 'formula_description', '原说明')
      await vi.advanceTimersByTimeAsync(300)
      expect(confirmDangerous).not.toHaveBeenCalled()
      expect(api.put).not.toHaveBeenCalled()

      s.onCellEdit(row, 'formula_description', '改了')
      await vi.advanceTimersByTimeAsync(199)
      expect(api.put).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(1)
      await flushPromises()
      expect(api.put).toHaveBeenCalledTimes(1)
      expect(row.formula_description).toBe('改了')
      wrapper.unmount()
    } finally { vi.useRealTimers() }
  })

  it('保存后采用响应里的新版本号，连续第二次保存不会带旧版本撞 409', async () => {
    const wrapper = create({ mode: 'report' })
    await flushPromises()
    const s = state(wrapper)
    api.put.mockResolvedValueOnce({ formula_version: 4 })
    s.onCellEdit(s.reportRows[0], 'formula', "TB('1002','期末余额')")
    await s.flushCellEdits()
    s.onCellEdit(s.reportRows[0], 'formula', "TB('1003','期末余额')")
    await s.flushCellEdits()
    expect(api.put.mock.calls.map(([, body]) => body.expected_version)).toEqual([3, 4])
    wrapper.unmount()
  })

  it('取消影响确认时零 PUT/零推送且格子退回原值；推送失败不回滚已保存公式并单独提示', async () => {
    const wrapper = create({ mode: 'report' })
    await flushPromises()
    const s = state(wrapper)
    const row = s.reportRows[0]
    s.onCellEdit(row, 'formula', "TB('9999','期末余额')")
    confirmDangerous.mockRejectedValueOnce(new Error('cancel'))
    await s.flushCellEdits()
    expect(api.put).not.toHaveBeenCalled()
    expect(service.pushConsolidation).not.toHaveBeenCalled()
    expect(s.cellValue(row, 'formula')).toBe("TB('1001','期末余额')")

    service.pushConsolidation.mockRejectedValueOnce(new Error('push failed'))
    s.onCellEdit(row, 'formula', 'ROW(\'BS-001\')')
    await s.flushCellEdits()
    expect(api.put).toHaveBeenCalledTimes(1)
    expect(row.formula).toBe("ROW('BS-001')")
    expect(messages.warning).toHaveBeenCalledWith(expect.stringContaining('公式已保存，但合并推送启动失败'))
    wrapper.unmount()
  })

  it('一批多行：确认一次、各行各一次 PUT、推送一次；保存失败的行退回服务器上的值', async () => {
    api.get.mockImplementation(async () => [
      { ...REPORT_ROW },
      { ...REPORT_ROW, id: 'bs-2', row_code: 'BS-003', row_name: '交易性金融资产', formula: "TB('1101','期末余额')", formula_version: 7 },
    ])
    const wrapper = create({ mode: 'report' })
    await flushPromises()
    const s = state(wrapper)
    const [a, b] = s.reportRows
    api.put.mockImplementation(async (url: string) => {
      if (url.endsWith('/bs-2')) throw new Error('409')
      return { formula_version: 4 }
    })
    s.onCellEdit(a, 'formula', "TB('1002','期末余额')")
    s.onCellEdit(b, 'formula', "TB('1102','期末余额')")
    await s.flushCellEdits()
    expect(confirmDangerous).toHaveBeenCalledTimes(1)
    expect(api.put.mock.calls.map(([url, body]) => [url, body.formula, body.expected_version])).toEqual([
      ['/api/report-config/bs-1', "TB('1002','期末余额')", 3],
      ['/api/report-config/bs-2', "TB('1102','期末余额')", 7],
    ])
    expect(service.pushConsolidation).toHaveBeenCalledTimes(1)
    expect(a.formula).toBe("TB('1002','期末余额')")
    expect(s.cellValue(b, 'formula')).toBe("TB('1101','期末余额')")
    wrapper.unmount()
  })

  it('整批都保存失败：不推送', async () => {
    const wrapper = create({ mode: 'report' })
    await flushPromises()
    const s = state(wrapper)
    api.put.mockRejectedValueOnce(new Error('409'))
    s.onCellEdit(s.reportRows[0], 'formula', "TB('1002','期末余额')")
    await s.flushCellEdits()
    expect(api.put).toHaveBeenCalledTimes(1)
    expect(service.pushConsolidation).not.toHaveBeenCalled()
    expect(s.cellValue(s.reportRows[0], 'formula')).toBe("TB('1001','期末余额')")
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
    state(wrapper).onCellEdit(state(wrapper).noteRows[0], 'formula', "TB('1002','期末余额')")
    state(wrapper).onCellEdit(state(wrapper).noteRows[0], 'description', '人工修订')
    await state(wrapper).flushCellEdits()
    expect(confirmDangerous).toHaveBeenCalledWith(expect.objectContaining({ title: '修改合并附注公式确认' }))
    expect(service.updateConsolNoteFormula.mock.calls).toEqual([['n1', {
      formula: "TB('1002','期末余额')", description: '人工修订', expected_version: 2,
    }]])
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
    expect(service.deleteConsolNoteFormula).toHaveBeenCalledWith('n1', 2)
    expect(service.pushConsolidation).toHaveBeenCalledTimes(1)
    expect(confirmDangerous).toHaveBeenCalledWith(expect.objectContaining({ confirmText: '确认删除' }))
    wrapper.unmount()
  })

  it('审计员只读：不能进入编辑、删除或种子化', async () => {
    service.listConsolNoteFormulas.mockResolvedValue(noteList(false))
    const wrapper = create({ mode: 'note' })
    await flushPromises()
    expect(state(wrapper).canManage).toBe(false)
    state(wrapper).onCellEdit(state(wrapper).noteRows[0], 'formula', "TB('1002','期末余额')")
    await state(wrapper).flushCellEdits()
    await state(wrapper).removeNoteRow(state(wrapper).noteRows[0])
    await state(wrapper).reseed()
    expect(Object.keys(state(wrapper).pending)).toEqual([])
    expect(confirmDangerous).not.toHaveBeenCalled()
    expect(service.updateConsolNoteFormula).not.toHaveBeenCalled()
    expect(service.deleteConsolNoteFormula).not.toHaveBeenCalled()
    expect(service.reseedConsolNoteFormulas).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('ADR-CNS-02 can_edit_global 能力字段', () => {
  it('can_edit_global=true：canManage 为真，编辑功能可用', async () => {
    service.listConsolNoteFormulas.mockResolvedValue(noteList(true))
    const wrapper = create({ mode: 'note', noteSection: '五-1-1' })
    await flushPromises()
    expect(state(wrapper).canManage).toBe(true)
    // 功能验证：admin 能进入编辑
    state(wrapper).onCellEdit(state(wrapper).noteRows[0], 'formula', "TB('1002','期末余额')")
    expect(Object.keys(state(wrapper).pending)).toHaveLength(1)
    wrapper.unmount()
  })

  it('can_edit_global=false：canManage 为假，编辑功能被拒', async () => {
    service.listConsolNoteFormulas.mockResolvedValue(noteList(false))
    const wrapper = create({ mode: 'note', noteSection: '五-1-1' })
    await flushPromises()
    expect(state(wrapper).canManage).toBe(false)
    // 编辑被拒
    state(wrapper).onCellEdit(state(wrapper).noteRows[0], 'formula', "TB('1002','期末余额')")
    expect(Object.keys(state(wrapper).pending)).toEqual([])
    wrapper.unmount()
  })

  it('can_edit_global 未返回（旧后端兼容）：canManage 缺省 false', async () => {
    service.listConsolNoteFormulas.mockResolvedValue({
      template_type: 'soe', count: 0, sections: [],
    })
    const wrapper = create({ mode: 'note' })
    await flushPromises()
    expect(state(wrapper).canManage).toBe(false)
    wrapper.unmount()
  })

  it('报表模式不受 can_edit_global 影响：canManage 始终为真', async () => {
    service.listConsolNoteFormulas.mockResolvedValue(noteList(false))
    const wrapper = create({ mode: 'report' })
    await flushPromises()
    expect(state(wrapper).canManage).toBe(true)
    wrapper.unmount()
  })

  it('提示文案只提 admin 不提 partner/manager', async () => {
    service.listConsolNoteFormulas.mockResolvedValue(noteList(false))
    const wrapper = create({ mode: 'note', noteSection: '五-1-1' })
    await flushPromises()
    const html = wrapper.html()
    expect(html).toContain('只有管理员可以修改合并附注公式')
    expect(html).not.toContain('合伙人')
    expect(html).not.toContain('经理')
    wrapper.unmount()
  })
})

describe('ADR-CNS-02 源码守卫', () => {
  it('组件源码不得包含角色名字面量集合（禁 managerRoles / Set 写法）', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const src = fs.readFileSync(
      path.resolve(__dirname, '../ConsolFormulaManagementPanel.vue'), 'utf-8',
    )
    // 不能有 Set(['admin', ... ]) 或类似角色名集合
    expect(src).not.toMatch(/new\s+Set\s*\(\s*\[.*?['"]admin['"]/s)
    expect(src).not.toMatch(/managerRoles/)
    // 检查不出现 partner/manager 作为角色判定
    expect(src).not.toMatch(/['"]partner['"]\s*[,\])]/)
    expect(src).not.toMatch(/['"]manager['"]\s*[,\])]/)
  })
})
