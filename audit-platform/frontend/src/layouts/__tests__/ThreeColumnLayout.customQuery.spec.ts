/**
 * ThreeColumnLayout.customQuery.spec.ts — 布局打开高级查询弹窗的入口上下文（advanced-query-linkage-closure 任务 31；
 * ADR-AQL-15，R10.1~R10.3、R10.5，AQ-22 / AQ-34 / AQ-37 / AQ-38）
 *
 * - 静态守卫（SFC 模板 AST）：弹窗的 `:year` 绑定 `customQueryYear`；公式管理与一键刷新的年度绑定仍含 `currentYear`
 *   （布局只为弹窗新增年度，`currentYear` 不动，变异 B11-b）；
 * - 接线：侧栏打开按当前页预选数据源；模板库事件带的项目优先于路由（原先被丢弃，变异 B11-a），事件带的模板口径源经
 *   `resolveTemplateLibrarySource` 映射（原先原样传、400 UNKNOWN_SOURCE，变异 #33），附注模板带出编号体系提示；
 *   关闭即丢弃事件；非项目页不给项目、年度留空（B10 评审非阻塞 #2）；模板库 URL 不带项目时页面自取的演示项目不进弹窗，
 *   带 `?project_id` 时采纳它（B11 评审 F1，变异 B11r-a）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { parse } from 'vue/compiler-sfc'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const { route, busOn, stubModule } = vi.hoisted(() => ({
  route: {
    name: 'TrialBalance' as string | undefined,
    path: '/projects/p1/trial-balance',
    params: { projectId: 'p1' } as Record<string, string>,
    query: {} as Record<string, string>,
  },
  busOn: [] as Array<[string, (payload?: unknown) => void]>,
  stubModule: async (name: string, props: string[] = []) => {
    const { defineComponent } = await import('vue')
    return { default: defineComponent({ name, props, emits: ['update:modelValue'], render: () => null }) }
  },
}))

// 路由在每例挂载前设好（布局的 computed 首次求值时读到）；同一例里只变事件 / 开合
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ username: 'admin', logout: vi.fn() }) }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ amountUnit: 'yuan', fontSize: 'md', decimals: 2, unitOptions: [], fontOptions: [] }),
}))
vi.mock('@/stores/roleContext', () => ({ useRoleContextStore: () => ({ effectiveRole: 'partner' }) }))
vi.mock('@/composables/useTheme', () => ({ useTheme: () => ({ isDark: false, toggle: vi.fn() }) }))
vi.mock('@/composables/useAdaptivePoll', () => ({
  useAdaptivePoll: () => ({ start: vi.fn(), poke: vi.fn(), dispose: vi.fn() }),
}))
vi.mock('@/services/sse/projectEventStream', () => ({ subscribeProjectEvent: () => ({ close: vi.fn() }), WILDCARD_EVENT: '*' }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({ trees: [], independents: [] }) } }))
vi.mock('@/services/auditPlatformApi', () => ({ getProject: vi.fn() }))
vi.mock('@/utils/operationHistory', () => ({ operationHistory: { undo: vi.fn() } }))
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: (name: string, fn: (payload?: unknown) => void) => { busOn.push([name, fn]) },
    off: vi.fn(),
  },
}))
vi.mock('@/components/formula/FormulaManagerDialog.vue', () => stubModule('FormulaManagerDialog', ['modelValue', 'projectId', 'year', 'scope']))
vi.mock('@/components/formula/GtRefreshScopeDialog.vue', () => stubModule('GtRefreshScopeDialog', ['projectId', 'year']))
vi.mock('@/components/query/CustomQueryDialog.vue', () => stubModule('CustomQueryDialog',
  ['modelValue', 'projectId', 'year', 'initialTab', 'initialSource', 'initialNotice']))
vi.mock('@/components/formula/settings/FormulaPendingSyncDialog.vue', () => stubModule('FormulaPendingSyncDialog', ['projectId']))
vi.mock('@/components/common/ShortcutHelpDialog.vue', () => stubModule('ShortcutHelpDialog'))
vi.mock('@/components/ai/DshPanel.vue', () => stubModule('DshPanel'))
vi.mock('@/shell/formula/WorkpaperPrimaryCapabilitiesHost.vue', () => stubModule('WorkpaperPrimaryCapabilitiesHost'))
vi.mock('@/components/DegradedBanner.vue', () => stubModule('DegradedBanner'))

import ThreeColumnLayout from '../ThreeColumnLayout.vue'
import { useProjectStore } from '@/stores/project'
import { TEMPLATE_NOTE_NOTICE } from '@/components/query/queryEntryContext'

const LAYOUT_SRC = readFileSync(resolve(__dirname, '../ThreeColumnLayout.vue'), 'utf-8')

function findElements(node: any, tag: string, out: any[] = []): any[] {
  if (node?.type === 1 && node.tag === tag) out.push(node)
  for (const child of node?.children ?? []) findElements(child, tag, out)
  return out
}
/** 元素上 `:year` 绑定的表达式原文 */
function yearBinding(tag: string): string {
  const [el] = findElements(parse(LAYOUT_SRC).descriptor.template!.ast, tag)
  expect(el, `${tag} 不在布局模板里`).toBeTruthy()
  const bind = el.props.find((p: any) => p.type === 7 && p.name === 'bind' && p.arg?.content === 'year')
  return String(bind?.exp?.content ?? '')
}

function mountLayout() {
  return shallowMount(ThreeColumnLayout, { global: { plugins: [ElementPlus], stubs: { 'router-view': true } } })
}
const dialogOf = (w: ReturnType<typeof mountLayout>) => w.findComponent({ name: 'CustomQueryDialog' })
function dialogState(w: ReturnType<typeof mountLayout>) {
  const d = dialogOf(w)
  return {
    open: d.props('modelValue'), projectId: d.props('projectId'), year: d.props('year'), tab: d.props('initialTab'),
    source: d.props('initialSource'), notice: d.props('initialNotice'),
  }
}
async function openFromSidebar(w: ReturnType<typeof mountLayout>) {
  await w.find('div.gt-nav-item[title="高级查询"]').trigger('click')
  await nextTick()
}
function emitOpenEvent(payload?: unknown) {
  const handler = busOn.find(([name]) => name === 'open-custom-query')?.[1]
  expect(handler, '布局没订阅 open-custom-query').toBeTypeOf('function')
  handler!(payload)
}

function setRoute(name: string | undefined, projectId: string | null, query: Record<string, string> = {}) {
  route.name = name
  route.params = projectId ? { projectId } : {}
  route.path = projectId ? `/projects/${projectId}/x` : '/projects'
  route.query = query
}

beforeEach(() => {
  setActivePinia(createPinia())
  setRoute('TrialBalance', 'p1')
  busOn.length = 0
  localStorage.clear()
})

describe('静态守卫：只给高级查询弹窗新增年度（AQ-22，ADR-AQL-15）', () => {
  it('弹窗 :year 绑定 customQueryYear；公式管理与一键刷新的年度绑定仍含 currentYear', () => {
    expect(yearBinding('CustomQueryDialog')).toBe('customQueryYear')
    expect(yearBinding('FormulaManagerDialog')).toContain('currentYear')
    expect(yearBinding('GtRefreshScopeDialog')).toContain('currentYear')
  })
})

describe('侧栏打开：按当前页预选（R10.3，AQ-34）', () => {
  it('试算表页：项目与年度随路由，预选试算表（科目）', async () => {
    setRoute('TrialBalance', 'p1', { year: '2024' })
    const w = mountLayout()
    await flushPromises()
    await openFromSidebar(w)
    expect(dialogState(w)).toEqual({
      open: true, projectId: 'p1', year: 2024, tab: 'basic', source: 'tb_detail', notice: undefined,
    })
  })

  it('报表页按 ?tab 预选报表源；路由不带年度时取项目 store 年度（页面所显示的年度）', async () => {
    setRoute('Reports', 'p1', { tab: 'income_statement' })
    useProjectStore().year = 2023
    const w = mountLayout()
    await flushPromises()
    await openFromSidebar(w)
    expect(dialogState(w)).toMatchObject({ projectId: 'p1', year: 2023, source: 'report_income_statement' })
  })

  it('非项目页：不给项目、不预选源；上一个项目的年度已随路由清掉，弹窗年度为空（B10 评审非阻塞 #2）', async () => {
    const store = useProjectStore()
    store.year = 2025
    setRoute('ProjectList', null)
    await store.syncFromRoute(route as any)
    expect(store.year).toBeNull()
    const w = mountLayout()
    await flushPromises()
    await openFromSidebar(w)
    expect(dialogState(w)).toMatchObject({ open: true, projectId: '', year: null, source: undefined })
  })
})

describe('模板库「📊 高级查询」事件（R10.1、R10.5，AQ-37 / AQ-38）', () => {
  it('事件带的项目优先于路由；该项目不是页面项目 ⇒ 年度留空交弹窗取该项目审计年度', async () => {
    setRoute('TrialBalance', 'p1', { year: '2025' })
    useProjectStore().year = 2025
    const w = mountLayout()
    await flushPromises()
    emitOpenEvent({ tab: 'basic', source: 'workpaper:D2|审定表D2-1', project_id: 'p2' })
    await nextTick()
    expect(dialogState(w)).toEqual({
      open: true, projectId: 'p2', year: null, tab: 'basic', source: 'workpaper:D2|审定表D2-1', notice: undefined,
    })
  })

  it('报表模板 report:<类型> 映射为报表源键（原先原样传给 execute ⇒ 400 UNKNOWN_SOURCE）', async () => {
    setRoute('TemplateLibraryMgmt', null, { project_id: 'p3' })
    const w = mountLayout()
    await flushPromises()
    emitOpenEvent({ tab: 'basic', source: 'report:balance_sheet', project_id: 'p3' })
    await nextTick()
    expect(dialogState(w)).toMatchObject({ projectId: 'p3', source: 'report_balance_sheet', notice: undefined })
  })

  it('模板库 URL 不带项目：底稿模板详情带来的演示项目不进弹窗，项目与年度都为空（B11 评审 F1，R10.1 / AQ-37）', async () => {
    const store = useProjectStore()
    store.year = 2025
    setRoute('TemplateLibraryMgmt', null)
    await store.syncFromRoute(route as any)
    const w = mountLayout()
    await flushPromises()
    // TemplateLibraryMgmt 的 ensureFallbackProject 取项目列表第一项 → WpTemplateDetail → TemplateLibraryButton 放进事件
    emitOpenEvent({ tab: 'basic', source: 'workpaper:E1', project_id: 'p-demo' })
    await nextTick()
    expect(dialogState(w)).toEqual({
      open: true, projectId: '', year: null, tab: 'basic', source: 'workpaper:E1', notice: undefined,
    })
  })

  it('模板库 URL 带 ?project_id：采纳该项目，年度留空交弹窗取它的审计年度；事件项目与路由不一致时取路由的', async () => {
    setRoute('TemplateLibraryMgmt', null, { project_id: 'p3', tab: 'wp-template' })
    const w = mountLayout()
    await flushPromises()
    emitOpenEvent({ tab: 'basic', source: 'workpaper:E1', project_id: 'p3' })
    await nextTick()
    expect(dialogState(w)).toMatchObject({ open: true, projectId: 'p3', year: null, source: 'workpaper:E1' })
    dialogOf(w).vm.$emit('update:modelValue', false)
    await nextTick()
    emitOpenEvent({ tab: 'basic', source: 'workpaper:E1', project_id: 'p-demo' })
    await nextTick()
    expect(dialogState(w)).toMatchObject({ open: true, projectId: 'p3', year: null })
  })

  it('附注模板落附注目录并带编号体系提示', async () => {
    setRoute('TemplateLibraryMgmt', null)
    const w = mountLayout()
    await flushPromises()
    emitOpenEvent({ tab: 'basic', source: 'note:五-1-1' })
    await nextTick()
    expect(dialogState(w)).toMatchObject({ projectId: '', source: 'disclosure', notice: TEMPLATE_NOTE_NOTICE })
  })

  it('关闭即丢弃事件：再从侧栏打开回到路由项目与按页预选', async () => {
    setRoute('TrialBalance', 'p1', { year: '2025' })
    const w = mountLayout()
    await flushPromises()
    emitOpenEvent({ tab: 'advanced', source: 'note:五-1-1', project_id: 'p2' })
    await nextTick()
    expect(dialogState(w)).toMatchObject({ projectId: 'p2', tab: 'advanced', source: 'disclosure' })
    dialogOf(w).vm.$emit('update:modelValue', false)
    await nextTick()
    expect(dialogState(w).open).toBe(false)
    await openFromSidebar(w)
    expect(dialogState(w)).toEqual({
      open: true, projectId: 'p1', year: 2025, tab: 'basic', source: 'tb_detail', notice: undefined,
    })
  })

  it('工作台快捷入口（事件不带载荷）：等同侧栏打开', async () => {
    setRoute('Adjustments', 'p1', { year: '2025' })
    const w = mountLayout()
    await flushPromises()
    emitOpenEvent(undefined)
    await nextTick()
    expect(dialogState(w)).toMatchObject({ open: true, projectId: 'p1', source: 'adj_aje' })
  })
})
