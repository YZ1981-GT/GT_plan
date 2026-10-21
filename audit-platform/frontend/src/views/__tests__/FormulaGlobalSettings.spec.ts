/**
 * FormulaGlobalSettings —— 全局公式设置页（spec formula-global-settings-sync，R2 / R3 / R4 / design §11）
 *
 * 守护：路由参数直达域 / 作用范围；非管理员只读（无编辑 / 发布入口）；管理员暂存修改 → 预览 → 发布：
 * 预览与发布用同一批变更、发布带版本号与固定请求号（重复提交不重复生效）；系统预设行新建全局不带版本；
 * 发布成功清空暂存并重取。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { api, route, msg } = vi.hoisted(() => ({
  api: { domains: vi.fn(), global: vi.fn(), previewGlobal: vi.fn(), publishGlobal: vi.fn(), publishes: vi.fn() },
  route: { query: {} as Record<string, string> },
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: api }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg }
})

import FormulaGlobalSettings from '../FormulaGlobalSettings.vue'

const DOMAINS = [
  { key: 'report', label: '报表公式', scope_kind: 'standard', wired: true,
    scopes: [{ value: 'soe_standalone', label: '国企单体' }, { value: 'listed_standalone', label: '上市单体' }],
    exec_fields: ['formula', 'formula_category'], desc_fields: ['formula_description'] },
  { key: 'note', label: '附注公式', scope_kind: 'template_type', wired: true,
    scopes: [{ value: 'soe', label: '国企版' }], exec_fields: ['formula'], desc_fields: [] },
]
const SLOTS = [
  { slot_key: 'balance_sheet:BS-002', label: '资产负债表 BS-002 货币资金', layer: 'global',
    definition: { formula: "TB('1001','期末余额')" }, version: 3, structure: { row_number: 2 } },
  { slot_key: 'balance_sheet:BS-099', label: '资产负债表 BS-099 预设行', layer: 'preset',
    definition: { formula: 'PRESET()' }, version: null, structure: null },
]

function mountPage() {
  return shallowMount(FormulaGlobalSettings, { global: { plugins: [ElementPlus], renderStubDefaultSlot: false } })
}
const state = (w: ReturnType<typeof mountPage>) => (w.vm as any).$.setupState

beforeEach(() => {
  vi.clearAllMocks()
  route.query = {}
  api.domains.mockResolvedValue({ domains: DOMAINS, is_admin: true })
  api.global.mockResolvedValue({ domain: 'report', scope: 'soe_standalone', can_edit: true, slots: SLOTS })
  api.previewGlobal.mockResolvedValue({ domain: 'report', scope: 'soe_standalone', changes: [], version_problems: [], summary: {}, items: [] })
  api.publishGlobal.mockResolvedValue({ publish_id: 'p', changed_project_count: 2, summary: { pending_total: 1 } })
})

describe('全局公式设置页', () => {
  it('路由参数直达指定域与作用范围；不合法的作用范围回落到该域第一个', async () => {
    route.query = { domain: 'report', scope: 'listed_standalone' }
    const w = mountPage()
    await flushPromises()
    expect(api.global).toHaveBeenCalledWith('report', 'listed_standalone')

    route.query = { domain: 'note', scope: 'listed_standalone' }
    const w2 = mountPage()
    await flushPromises()
    expect(api.global).toHaveBeenLastCalledWith('note', 'soe')
    w.unmount(); w2.unmount()
  })

  it('非管理员：只读（不显示编辑 / 发布），只能查看', async () => {
    api.domains.mockResolvedValue({ domains: DOMAINS, is_admin: false })
    const w = mountPage()
    await flushPromises()
    expect(state(w).isAdmin).toBe(false)
    expect(w.html()).toContain('只读：全局公式仅管理员可修改')
    w.unmount()
  })

  it('暂存 → 预览 → 发布：同一批变更、带版本号、预览与发布同一请求号；成功后清空暂存并重取', async () => {
    const w = mountPage()
    await flushPromises()
    const s = state(w)
    s.openEdit(SLOTS[0])
    s.onStage({ formula: "TB('1001','期末余额')+1" })
    s.openEdit(SLOTS[1])
    s.onStage({ formula: 'PRESET()*2' })
    await s.onPreview()
    expect(api.previewGlobal).toHaveBeenCalledWith('report', {
      scope: 'soe_standalone',
      changes: [
        expect.objectContaining({ slot_key: 'balance_sheet:BS-002', expected_version: 3 }),
        // 只有系统预设、还没有全局行 → 新建全局行，不带版本
        expect.objectContaining({ slot_key: 'balance_sheet:BS-099', expected_version: null }),
      ],
    })
    const loadsBefore = api.global.mock.calls.length
    api.publishGlobal.mockRejectedValueOnce({ response: { status: 500 } })
    const decisions = { project_choices: { p9: 'defer' }, conflict_choices: {}, default_conflict: 'ask' }
    expect(await s.onPublish({ decisions, note: '' })).toBe(false)
    expect(await s.onPublish({ decisions, note: '统一口径' })).toBe(true)
    const [first, second] = api.publishGlobal.mock.calls.map((c) => c[1])
    expect(second).toMatchObject({ scope: 'soe_standalone', decisions, note: '统一口径' })
    expect(second.changes).toHaveLength(2)
    expect(second.request_id).toBe(first.request_id)
    expect(s.staged.size).toBe(0)
    expect(api.global.mock.calls.length).toBe(loadsBefore + 1)
    expect(msg.success).toHaveBeenCalledWith(expect.stringContaining('1 处交项目确认'))
    w.unmount()
  })

  it('删除全局公式位：暂存为 definition=null 且带版本', async () => {
    const w = mountPage()
    await flushPromises()
    const s = state(w)
    s.stageDelete(SLOTS[0])
    await s.onPreview()
    expect(api.previewGlobal.mock.calls[0][1].changes).toEqual([
      { slot_key: 'balance_sheet:BS-002', definition: null, label: SLOTS[0].label, expected_version: 3 },
    ])
    w.unmount()
  })

  it('切换公式域：放弃未发布的暂存并提示', async () => {
    const w = mountPage()
    await flushPromises()
    const s = state(w)
    s.stageDelete(SLOTS[0])
    s.domainKey = 'note'
    await s.onDomainChange()
    expect(s.staged.size).toBe(0)
    expect(msg.warning).toHaveBeenCalledWith('切换公式域已放弃 1 处未发布的暂存')
    expect(api.global).toHaveBeenLastCalledWith('note', 'soe')
    w.unmount()
  })
})
