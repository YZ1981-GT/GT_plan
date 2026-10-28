/**
 * 程序表执行人改的状态 / 执行说明写到读取方读的位置 —— spec audit-year-calendar-fallback-ratchet R0 / 任务 0.3
 *
 * 原写法：年度 = 路由 year → 今年，scope = `procedure_table:` + sheetName（整册嵌入没传 ⇒ A1）。
 * render-config 按项目审计年度 + 表码读 ⇒ 刷新后看不到。现在：年度取项目审计年度，scope 取 render-config 回传的 override_scope。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const warn = vi.hoisted(() => vi.fn())
const routeQuery = vi.hoisted(() => ({ year: '2026' }))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-001' }, query: routeQuery }),
}))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ElMessage: { warning: warn, error: vi.fn(), success: vi.fn(), info: vi.fn() },
}))
const rowApi = vi.hoisted(() => ({ setApplicability: vi.fn(), getAccess: vi.fn() }))
vi.mock('@/services/commonApi', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  setProgramRowApplicability: rowApi.setApplicability,
  getProgramRowAccess: rowApi.getAccess,
}))
vi.mock('@/composables/useWpOnboardingGuide', () => ({
  useWpOnboardingGuide: () => ({ showGuide: { value: false }, guideSteps: { value: [] }, triggerGuide: vi.fn() }),
}))
vi.mock('@/components/workpaper/GtAuditFlowGraph.vue', () => ({
  default: { name: 'GtAuditFlowGraph', template: '<div />' },
}))

import GtAProgramConsole from '../GtAProgramConsole.vue'

let projectYear: number | null = 2025
let renderConfig: any = null

beforeEach(() => {
  setActivePinia(createPinia())
  projectYear = 2025
  renderConfig = null
  api.get.mockReset().mockImplementation(async (url: string) => {
    if (url === '/api/projects/proj-001') return { id: 'proj-001', audit_year: projectYear }
    if (url.includes('/render-config')) return renderConfig ?? {}
    return []
  })
  api.post.mockReset().mockResolvedValue({})
  warn.mockReset()
  rowApi.setApplicability.mockReset().mockResolvedValue({ changed: true })
  rowApi.getAccess.mockReset().mockResolvedValue({
    full_power: true, can_trim: true, own_program_nos: [], assignees: {}, template_code: 'H1A',
  })
})

const ROWS = [
  { id: 'row-1', program_no: 1, program_desc: '获取固定资产明细表', program_category: '', status: 'pending' },
  { id: 'row-2', program_no: 2, program_desc: '实地监盘', program_category: '', status: 'pending', execution_summary: '' },
]

function mountConsole(props: Record<string, unknown>) {
  return mount(GtAProgramConsole, {
    props: { wpId: 'wp-001', schema: {}, ...props } as any,
    global: { stubs: { GtAuditFlowGraph: true, 'el-table': true, 'el-table-column': true, 'el-dialog': true } },
  })
}

function overridePosts() {
  return api.post.mock.calls.filter(c => c[0] === '/api/workpapers/field-overrides').map(c => c[1])
}

describe('GtAProgramConsole 字段覆盖写入位置', () => {
  it('状态 / 执行说明按 override_scope + 项目审计年度写（不取路由 year=2026 / 今年）', async () => {
    const wrapper = mountConsole({
      sheetName: 'H1A',
      htmlData: { programs: ROWS, trim_decisions: [], override_scope: 'procedure_table:H1A' },
    })
    await flushPromises()
    const vm = wrapper.vm as any
    await vm.handleStatusChange(vm.programs[1], 'in_progress')
    vm.programs[1].execution_summary = '再补一句'
    await vm.saveExecutionSummary(vm.programs[1])
    await flushPromises()
    expect(overridePosts()).toEqual([
      { project_id: 'proj-001', year: 2025, scope: 'procedure_table:H1A', item_key: '2', field: 'status', value: 'in_progress' },
      { project_id: 'proj-001', year: 2025, scope: 'procedure_table:H1A', item_key: '2', field: 'execution_summary', value: '再补一句' },
    ])
  })

  it('整册嵌入（没传 sheetName）⇒ 用自加载 render-config 回传的 scope，不再写进 A1', async () => {
    renderConfig = { sheets: [{ html_data: { programs: ROWS, override_scope: 'procedure_table:A15' } }] }
    const wrapper = mountConsole({ sheetName: '', htmlData: { programs: [], trim_decisions: [] } })
    await flushPromises()
    const vm = wrapper.vm as any
    await vm.handleStatusChange(vm.programs[0], 'completed')
    await flushPromises()
    expect(overridePosts().map(b => `${b.scope}@${b.year}`)).toEqual(['procedure_table:A15@2025'])
  })

  it('html_data 没有程序行时的兜底拉取带项目审计年度；年度取不到就不传（由后端定，不猜今年）', async () => {
    mountConsole({ sheetName: 'H1A', htmlData: { programs: [], trim_decisions: [] } })
    await flushPromises()
    const fallback = () => api.get.mock.calls.filter(c => String(c[0]).includes('/procedure-tables/'))
    expect(fallback().map(c => c[1])).toEqual([{ params: { year: 2025 } }])

    api.get.mockClear()
    projectYear = null
    mountConsole({ sheetName: 'H1A', htmlData: { programs: [], trim_decisions: [] } })
    await flushPromises()
    expect(fallback().map(c => c[1])).toEqual([{ params: {} }])
  })

  it('项目没填审计年度 ⇒ 不发请求并提示', async () => {
    projectYear = null
    const wrapper = mountConsole({
      sheetName: 'H1A',
      htmlData: { programs: ROWS, trim_decisions: [], override_scope: 'procedure_table:H1A' },
    })
    await flushPromises()
    const vm = wrapper.vm as any
    await vm.handleStatusChange(vm.programs[0], 'completed')
    await flushPromises()
    expect(overridePosts()).toEqual([])
    expect(warn).toHaveBeenCalledWith('未设置审计年度，请先在项目基本信息中填写（本次保存未提交）')
  })
})

// ─── 变异验证：确认 scope / 年度 / 兜底行为的守卫在被需要的地方起作用 ─────────────
describe('变异：年度与 scope 不可回退到旧写法', () => {
  it('MO1: 写入年度只用项目审计年度，路由 year=2026 不被采用', async () => {
    routeQuery.year = '2026'
    projectYear = 2025
    mountConsole({
      sheetName: 'H1A',
      htmlData: { programs: ROWS, trim_decisions: [], override_scope: 'procedure_table:H1A' },
    })
    await flushPromises()
    const vm = (mountConsole({
      sheetName: 'H1A',
      htmlData: { programs: ROWS, trim_decisions: [], override_scope: 'procedure_table:H1A' },
    })).vm as any
    await flushPromises()
    await vm.handleStatusChange(vm.programs[0], 'completed')
    await flushPromises()
    const posts = overridePosts()
    expect(posts.length).toBeGreaterThan(0)
    // 所有写入必须使用项目审计年度 2025，不是路由的 2026
    for (const body of posts) {
      expect(body.year).toBe(2025)
      expect(body.year).not.toBe(2026)
    }
  })

  it('MO2: scope 以 override_scope 为准，不拿 sheetName 拼接', async () => {
    const wrapper = mountConsole({
      sheetName: '固定资产审计程序表H1A',
      htmlData: { programs: ROWS, trim_decisions: [], override_scope: 'procedure_table:H1A' },
    })
    await flushPromises()
    const vm = wrapper.vm as any
    await vm.handleStatusChange(vm.programs[0], 'completed')
    await flushPromises()
    const posts = overridePosts()
    expect(posts.length).toBeGreaterThan(0)
    // scope 必须是 override_scope 回传的，不是前端自己拼的 `procedure_table:固定资产审计程序表H1A`
    for (const body of posts) {
      expect(body.scope).toBe('procedure_table:H1A')
      expect(body.scope).not.toContain('固定资产')
    }
  })

  it('MO3: 兜底拉取程序行不传今年年度（年度取不到时 params 不含 year）', async () => {
    projectYear = null
    mountConsole({ sheetName: 'H1A', htmlData: { programs: [], trim_decisions: [] } })
    await flushPromises()
    const fallbackCalls = api.get.mock.calls.filter(c => String(c[0]).includes('/procedure-tables/'))
    expect(fallbackCalls.length).toBeGreaterThan(0)
    // 年度取不到时，params 里不应有 year（由后端用单一来源决定），也不应出现今年
    const thisYear = new Date().getFullYear()
    for (const call of fallbackCalls) {
      const params = call[1]?.params || {}
      expect(params).not.toHaveProperty('year', thisYear)
      expect(params).toEqual({})
    }
  })

  it('MO4: 写入失败时不会用 undefined/null 作为年度发请求', async () => {
    projectYear = null
    const wrapper = mountConsole({
      sheetName: 'H1A',
      htmlData: { programs: ROWS, trim_decisions: [], override_scope: 'procedure_table:H1A' },
    })
    await flushPromises()
    const vm = wrapper.vm as any
    await vm.handleStatusChange(vm.programs[0], 'completed')
    await flushPromises()
    // 不应有任何 field-overrides POST（年度取不到不发请求）
    expect(overridePosts()).toEqual([])
    // 检查不存在 year 为 null / undefined / NaN 的调用
    for (const call of api.post.mock.calls) {
      if (call[0] === '/api/workpapers/field-overrides') {
        expect(call[1].year).not.toBeNull()
        expect(call[1].year).not.toBeUndefined()
        expect(call[1].year).not.toBeNaN()
      }
    }
  })
})
