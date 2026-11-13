/** R3：真实目录组件 + 挂起传输层；执行结果以本轮隔离验证记录为准。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import type { CheckCatalogQuery, CheckRuleSource } from '@/composables/formula/useFormulaSettings'

const mocked = vi.hoisted(() => ({ checkRules: vi.fn() }))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: mocked }))
import FormulaCheckCatalog from '../FormulaCheckCatalog.vue'

enableAutoUnmount(afterEach)
afterEach(() => { vi.restoreAllMocks() })
type Reply = { sources: CheckRuleSource[]; total: number }
type Props = { initialSource?: string; projectId?: string | null; year?: number | null }
const FIRST = 'report_builtin'
const SECOND = 'cross_check_global'
function source(key: string, text = '当前规则'): CheckRuleSource {
  return { key, label: `来源-${key}`, category: '报表', runs_in: '校验入口', editable: false,
    edit_where: '', files: [], from_db: false, rule_count: 1, error: null, execution: 'wired',
    result_table: 'cross_check_results', last_run: { at: null, status: 'passed', counts: { pass: 1 }, year: 2025 },
    last_run_note: `${text}历史`, matched: 1,
    rules: [{ id: `规则-${text}`, label: text, expression: '1 = 1', severity: 'logic_check', severity_label: '勾稽', scope: '报表' }] }
}
const detail = (key: string, text: string): Reply => ({ sources: [source(key, text)], total: 2 })
const listing = (): Reply => ({ sources: [FIRST, SECOND].map((key) => ({ ...source(key), rules: undefined, matched: undefined })), total: 2 })
function deferred() {
  let resolve!: (value: Reply) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<Reply>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}
const requests: Array<ReturnType<typeof deferred> & { params: CheckCatalogQuery }> = []
beforeEach(() => {
  requests.length = 0
  mocked.checkRules.mockReset().mockImplementation((params: CheckCatalogQuery = {}) => {
    const pending = deferred()
    requests.push({ ...pending, params: { ...params } })
    return pending.promise
  })
  vi.spyOn(ElMessage, 'error').mockImplementation(() => ({}) as any)
})
const mountCatalog = (props: Props = {}) => mount(FormulaCheckCatalog, { props, global: { plugins: [ElementPlus] } })
async function ready() {
  const w = mountCatalog({ projectId: 'p1', year: 2025 })
  requests[0].resolve(listing()); await flushPromises()
  requests[1].resolve(detail(FIRST, '原项目规则')); await flushPromises()
  return w
}
async function search(w: ReturnType<typeof mountCatalog>, keyword: string) {
  await w.get('input[data-testid="fcc-search"]').setValue(keyword)
  await w.get('[data-testid="fcc-search-btn"]').trigger('click')
}
function expectCleared(w: ReturnType<typeof mountCatalog>) {
  expect(w.find('[data-testid="fcc-head"]').exists()).toBe(false)
  expect(w.findAll('[data-testid^="fcc-history-"]')).toHaveLength(0)
  expect(w.get('[data-testid="fcc-rules"]').text()).not.toContain('原项目规则')
  expect(w.attributes('aria-busy')).toBe('true')
}

describe('目录所有查询形态都使用当前上下文', () => {
  it('来源清单、首来源、切换来源、搜索及清空搜索都透传项目和年度', async () => {
    const w = await ready()
    expect(requests.map((r) => r.params)).toEqual([
      { project_id: 'p1', year: 2025 }, { project_id: 'p1', year: 2025, source: FIRST },
    ])
    await w.get(`[data-testid="fcc-src-${SECOND}"]`).trigger('click')
    requests[2].resolve(detail(SECOND, '另一来源')); await flushPromises()
    await search(w, '  金额  ')
    requests[3].resolve(detail(SECOND, '搜索命中')); await flushPromises()
    await search(w, '')
    requests[4].resolve(detail(SECOND, '恢复所选')); await flushPromises()
    expect(requests.slice(2).map((r) => r.params)).toEqual([
      { project_id: 'p1', year: 2025, source: SECOND }, { project_id: 'p1', year: 2025, q: '金额' },
      { project_id: 'p1', year: 2025, source: SECOND },
    ])
    expect(w.get('[data-testid="fcc-head"]').text()).toContain(`来源-${SECOND}`)
  })

  it.each([
    [{}, {}], [{ projectId: 'p1', year: null }, { project_id: 'p1' }],
    [{ projectId: null, year: 2024 }, { year: 2024 }], [{ projectId: '', year: undefined }, {}],
  ] as Array<[Props, CheckCatalogQuery]>)('省略空上下文 %j，不补系统年度', async (props, context) => {
    const w = mountCatalog(props)
    expect(requests[0].params).toEqual(context)
    requests[0].resolve(listing()); await flushPromises()
    expect(requests[1].params).toEqual({ ...context, source: FIRST })
    requests[1].resolve(detail(FIRST, '定义规则')); await flushPromises()
    if (!props.projectId) expect(w.get('[data-testid="fcc-history-report_builtin"]').text()).toContain('未指定项目')
  })
})

describe('项目与年度切换同步清空，迟到响应失效', () => {
  it.each(['项目', '年度'] as const)('%s 变化清空旧规则/历史；旧清单不能再派生来源请求', async (kind) => {
    const w = await ready()
    await w.setProps(kind === '项目' ? { projectId: 'p2' } : { year: 2024 })
    expectCleared(w)
    expect(w.findAll('[data-testid^="fcc-src-"]')).toHaveLength(0)
    expect(w.text()).not.toContain('原项目规则历史')
    await w.setProps(kind === '项目' ? { projectId: 'p3' } : { year: 2023 })
    const context = kind === '项目' ? { project_id: 'p3', year: 2025 } : { project_id: 'p1', year: 2023 }
    expect(requests[3].params).toEqual(context)
    requests[3].resolve(listing()); await flushPromises()
    expect(requests[4].params).toEqual({ ...context, source: FIRST })
    requests[2].resolve({ sources: [source('obsolete', '迟到清单')], total: 99 }); await flushPromises()
    expect(requests).toHaveLength(5)
    expect(w.text()).not.toContain('迟到清单')
    expect(w.attributes('aria-busy')).toBe('true')
    requests[4].resolve(detail(FIRST, '新上下文')); await flushPromises()
    expect(w.get('[data-testid="fcc-rules"]').text()).toContain('新上下文')
    expect(w.attributes('aria-busy')).toBe('false')
  })

  it.each(['成功', '失败'] as const)('旧来源迟到%s不能改新结果、弹错或结束新 loading', async (outcome) => {
    const w = await ready()
    await w.get(`[data-testid="fcc-src-${SECOND}"]`).trigger('click')
    await w.setProps({ projectId: 'p2' })
    expectCleared(w)
    requests[3].resolve(listing()); await flushPromises()
    expect(requests[4].params).toEqual({ project_id: 'p2', year: 2025, source: SECOND })
    if (outcome === '成功') requests[2].resolve(detail(SECOND, '迟到旧规则'))
    else requests[2].reject(new Error('迟到旧错误'))
    await flushPromises()
    expect(w.text()).not.toContain('迟到旧规则')
    expect(w.find('[data-testid="fcc-request-error"]').exists()).toBe(false)
    expect(ElMessage.error).not.toHaveBeenCalled()
    expect(w.find('[data-testid="fcc-loading"]').exists()).toBe(true)
    expect(w.attributes('aria-busy')).toBe('true')
    requests[4].resolve(detail(SECOND, '新项目规则')); await flushPromises()
    expect(w.text()).toContain('新项目规则历史')
    expect(w.attributes('aria-busy')).toBe('false')
  })
})

describe('来源与搜索使用同一请求代际', () => {
  it.each(['成功', '失败'] as const)('旧来源%s不能覆盖后选来源', async (outcome) => {
    const w = await ready()
    await w.get(`[data-testid="fcc-src-${SECOND}"]`).trigger('click')
    await w.get(`[data-testid="fcc-src-${FIRST}"]`).trigger('click')
    requests[3].resolve(detail(FIRST, '最后所选来源')); await flushPromises()
    if (outcome === '成功') requests[2].resolve(detail(SECOND, '过时来源'))
    else requests[2].reject(new Error('过时来源失败'))
    await flushPromises()
    expect(w.get('[data-testid="fcc-head"]').text()).toContain(`来源-${FIRST}`)
    expect(w.text()).toContain('最后所选来源历史')
    expect(w.text()).not.toContain('过时来源')
    expect(w.find('[data-testid="fcc-request-error"]').exists()).toBe(false)
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it.each(['成功', '失败'] as const)('旧搜索%s不能覆盖后一次搜索', async (outcome) => {
    const w = await ready()
    await search(w, '旧关键词')
    await search(w, '新关键词')
    requests[3].resolve(detail(SECOND, '最新命中')); await flushPromises()
    if (outcome === '成功') requests[2].resolve(detail(FIRST, '过时命中'))
    else requests[2].reject(new Error('过时搜索失败'))
    await flushPromises()
    expect(w.text()).toContain('搜索「新关键词」')
    expect(w.text()).toContain('最新命中历史')
    expect(w.text()).not.toContain('过时命中')
    expect(w.findAll('[data-testid^="fcc-evidence-"]')).toHaveLength(1)
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('搜索取代挂起的来源；清空搜索恢复选择，迟到搜索不能重新进入搜索态', async () => {
    const w = await ready()
    await w.get(`[data-testid="fcc-src-${SECOND}"]`).trigger('click')
    await search(w, '金额')
    requests[3].resolve(detail(FIRST, '搜索结果')); await flushPromises()
    requests[2].resolve(detail(SECOND, '迟到来源')); await flushPromises()
    expect(w.text()).toContain('搜索「金额」')
    expect(w.text()).not.toContain('迟到来源')
    await search(w, '晚到搜索')
    await search(w, '')
    expect(requests[5].params).toEqual({ project_id: 'p1', year: 2025, source: SECOND })
    requests[5].resolve(detail(SECOND, '清空后选择')); await flushPromises()
    requests[4].resolve(detail(FIRST, '晚到命中')); await flushPromises()
    expect(w.find('[data-testid="fcc-head"]').exists()).toBe(true)
    expect(w.text()).toContain('清空后选择历史')
    expect(w.text()).not.toContain('搜索「')
    expect(w.text()).not.toContain('晚到命中')
  })
})

describe('保留查询意图与当前错误的生命周期', () => {
  it('切年度重跑已提交搜索；只输入但未提交的文字不悄悄成为新查询', async () => {
    const w = await ready()
    await search(w, '已提交')
    requests[2].resolve(detail(FIRST, '旧年命中')); await flushPromises()
    await w.get('input[data-testid="fcc-search"]').setValue('尚未提交')
    await w.setProps({ year: 2024 })
    expectCleared(w)
    expect(w.text()).not.toContain('旧年命中历史')
    requests[3].resolve(listing()); await flushPromises()
    expect(requests[4].params).toEqual({ project_id: 'p1', year: 2024, q: '已提交' })
    requests[4].resolve(detail(SECOND, '本年命中')); await flushPromises()
    expect(w.text()).toContain('搜索「已提交」')
    expect((w.get('input[data-testid="fcc-search"]').element as HTMLInputElement).value).toBe('尚未提交')
  })

  it.each(['清单', '来源', '搜索'] as const)('当前%s读取失败显示错误而非无历史，并在下次请求同步清掉', async (stage) => {
    const w = stage === '清单' ? mountCatalog({ projectId: 'p1', year: 2025 }) : await ready()
    if (stage === '来源') await w.get(`[data-testid="fcc-src-${SECOND}"]`).trigger('click')
    if (stage === '搜索') await search(w, '金额')
    const failed = requests.at(-1)!
    failed.reject(new Error('当前合成读取失败')); await flushPromises()
    expect(w.get('[data-testid="fcc-request-error"]').text()).toContain('读取失败，未取得当前查询的规则与历史；不能据此认定通过')
    expect(w.findAll('[data-testid^="fcc-evidence-"]')).toHaveLength(0)
    expect(w.attributes('aria-busy')).toBe('false')
    expect(ElMessage.error).toHaveBeenCalledTimes(1)
    await w.setProps({ year: 2024 })
    expect(w.find('[data-testid="fcc-request-error"]').exists()).toBe(false)
    expect(w.attributes('aria-busy')).toBe('true')
    const listIndex = requests.length - 1
    requests[listIndex].resolve(listing()); await flushPromises()
    const recovered = requests[listIndex + 1]
    recovered.resolve(detail(recovered.params.source ?? FIRST, '恢复读取')); await flushPromises()
    expect(w.text()).toContain('恢复读取历史')
    expect(w.attributes('aria-busy')).toBe('false')
  })

  it('所选来源在响应中缺失是读取错误，不能借用另一个来源的历史', async () => {
    const w = await ready()
    await w.get(`[data-testid="fcc-src-${SECOND}"]`).trigger('click')
    requests[2].resolve(detail(FIRST, '不相关摘要')); await flushPromises()
    expect(w.find('[data-testid="fcc-request-error"]').exists()).toBe(true)
    expect(w.findAll('[data-testid^="fcc-evidence-"]')).toHaveLength(0)
    expect(w.text()).not.toContain('不相关摘要')
    expect(ElMessage.error).toHaveBeenCalledTimes(1)
  })
})

describe('卸载后无副作用', () => {
  it.each([
    ['清单', '成功'], ['清单', '失败'], ['来源', '成功'], ['来源', '失败'], ['搜索', '成功'], ['搜索', '失败'],
  ] as const)('%s迟到%s不能再请求或发错误提示', async (stage, outcome) => {
    const w = stage === '清单' ? mountCatalog({ projectId: 'p1', year: 2025 }) : await ready()
    if (stage === '来源') await w.get(`[data-testid="fcc-src-${SECOND}"]`).trigger('click')
    if (stage === '搜索') await search(w, '金额')
    const pending = requests.at(-1)!
    const before = requests.length
    w.unmount()
    if (outcome === '成功') pending.resolve(stage === '清单' ? listing() : detail(FIRST, '卸载后内容'))
    else pending.reject(new Error('卸载后的合成错误'))
    await flushPromises()
    expect(requests).toHaveLength(before)
    expect(ElMessage.error).not.toHaveBeenCalled()
  })
})
