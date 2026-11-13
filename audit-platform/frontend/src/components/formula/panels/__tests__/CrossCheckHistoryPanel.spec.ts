import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElButton, ElTag } from 'element-plus'
import CrossCheckHistoryPanel from '../CrossCheckHistoryPanel.vue'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ default: { get } }))
vi.mock('@/composables/formula/useFormulaSettings', () => ({
  formulaErrorText: (_error: unknown, fallback: string) => fallback,
}))
function deferred<T = any>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const wrappers: ReturnType<typeof mount>[] = []
function create(props = { projectId: 'A', year: 2025 }) {
  const w = mount(CrossCheckHistoryPanel, { props, global: { plugins: [ElementPlus] } })
  wrappers.push(w)
  return w
}
const run = (run_id: string, issues: any[] = [], extra = {}) => ({
  run_id, status: 'executed', executed_count: issues.length, issue_count: 0,
  hint_count: 0, issues, ...extra,
})
const load = (w: ReturnType<typeof create>) => (w.vm as unknown as { load: () => Promise<void> }).load()
const busy = (w: ReturnType<typeof create>) => w.findComponent(ElButton).props('loading')
async function expand(w: ReturnType<typeof create>) {
  await w.get('.el-collapse-item__header').trigger('click')
  await flushPromises()
}
beforeEach(() => { get.mockReset() })
afterEach(() => { wrappers.splice(0).forEach((w) => w.unmount()) })

describe('历史面板：仅展示真实保留证据', () => {
  it('初始不取数，首次展开才读取；运行已执行不等于逐条通过', async () => {
    get.mockResolvedValue({ runs: [run('r0')] })
    const w = create()
    expect(get).not.toHaveBeenCalled()
    await expand(w)
    expect(get).toHaveBeenCalledExactlyOnceWith('/api/projects/A/formula/cross-check-history', {
      params: { year: 2025 }, _silent: true,
    })
    expect(w.text()).toContain('已执行')
    expect(w.text()).toContain('未返回逐条明细，不能据此判定全部通过')
    expect(w.findAllComponents(ElTag).map((t) => [t.text(), t.props('type')])).toEqual([['已执行', 'info']])
  })
  it('五态、原因与严重度独立；真零保留、非法金额不冒充零；部分明细仍展示', async () => {
    get.mockResolvedValue({ runs: [run('r1', [
      { rule_id: 'p', status: 'passed', severity: 'blocking', left_value: 0, right_value: '0', diff: 0 },
      { rule_id: 'f', status: 'failed', severity: 'info', left_value: null, right_value: '12oops', diff: null, reason: '实际不平' },
      { rule_id: 'n', status: 'not_executed', reason: '缺少期初数' },
      { rule_id: 'a', status: 'not_applicable', severity: 'info', reason: '本期不适用' },
      { rule_id: 'e', status: 'error', reason: '来源异常' },
    ], { issues_retained: false })] })
    const w = create()
    await expand(w)
    const tags = w.findAllComponents(ElTag).map((t) => [t.text(), t.props('type')])
    expect(tags).toEqual([
      ['已执行', 'info'], ['通过', 'success'], ['阻断', 'danger'],
      ['失败', 'info'], ['提示', 'info'], ['未执行（数据缺失）', 'warning'], ['警告', 'warning'],
      ['不适用', 'info'], ['提示', 'info'], ['检查异常', 'danger'], ['警告', 'warning'],
    ])
    for (const text of ['明细未完整保留', '不代表完整通过清单',
      '左值：0.00；右值：0.00；差额：0.00', '左值：—；右值：—；差额：—',
      '原因：实际不平', '原因：缺少期初数', '原因：本期不适用', '原因：来源异常']) {
      expect(w.text()).toContain(text)
    }
  })
  it('旧布尔仅缺状态时兼容；显式未知和 null 状态保持异常', async () => {
    get.mockResolvedValue({ runs: [run('legacy', [
      { rule_id: 'old-pass', details: { passed: true } },
      { rule_id: 'old-fail', passed: false, details: { reason: '旧明细原因', severity: 'info' } },
      { rule_id: 'unknown', status: 'unexpected', passed: true },
      { rule_id: 'null', status: null, passed: true },
    ])] })
    const w = create()
    await expand(w)
    const labels = w.findAllComponents(ElTag).map((t) => t.text())
    expect(labels).toEqual(['已执行', '通过', '警告', '失败', '提示', '检查异常', '警告', '检查异常', '警告'])
    expect(w.text()).toContain('原因：旧明细原因')
    expect(w.text()).toContain('接口未返回检查状态')
  })
  it('失败可刷新重试，重新读取不保留旧错误', async () => {
    get.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ runs: [run('retry')] })
    const w = create()
    await expand(w)
    expect(w.get('[data-testid="history-error"]').text()).toContain('执行历史读取失败，请重试')
    expect(busy(w)).toBe(false)
    await w.findComponent(ElButton).trigger('click')
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(w.find('[data-testid="history-error"]').exists()).toBe(false)
    expect(w.text()).toContain('已执行')
  })
})

describe('历史面板：上下文与请求代际隔离', () => {
  it.each([
    ['项目', { projectId: 'B', year: 2025 }],
    ['年度', { projectId: 'A', year: 2024 }],
  ] as const)('%s变化清旧；旧成功不覆盖且不清新 loading', async (_label, props) => {
    const old = deferred(), current = deferred()
    get.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    const w = create()
    await expand(w)
    await w.setProps(props)
    expect(get).toHaveBeenCalledTimes(2)
    old.resolve({ runs: [run('stale', [{ rule_id: '旧成功', status: 'passed' }])] })
    await flushPromises()
    expect(w.text()).not.toContain('旧成功')
    expect(busy(w)).toBe(true)
    current.resolve({ runs: [run('new', [{ rule_id: '本次数据', status: 'not_executed' }])] })
    await flushPromises()
    expect(w.text()).toContain('本次数据')
    expect(busy(w)).toBe(false)
  })
  it.each([
    ['项目', { projectId: 'B', year: 2025 }],
    ['年度', { projectId: 'A', year: 2024 }],
  ] as const)('%s变化后旧 reject/finally 不写错误、不结束新请求', async (_label, props) => {
    const old = deferred(), current = deferred()
    get.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    const w = create()
    await expand(w)
    await w.setProps(props)
    old.reject(new Error('stale rejection'))
    await flushPromises()
    expect(w.find('[data-testid="history-error"]').exists()).toBe(false)
    expect(busy(w)).toBe(true)
    current.resolve({ runs: [run('new', [{ rule_id: '新请求完成', status: 'passed' }])] })
    await flushPromises()
    expect(w.text()).toContain('新请求完成')
    expect(busy(w)).toBe(false)
  })
  it('A→B→A 不接受第一次 A 的结果，也不接受 B 的迟到错误', async () => {
    const a1 = deferred(), b = deferred(), a2 = deferred()
    get.mockReturnValueOnce(a1.promise).mockReturnValueOnce(b.promise).mockReturnValueOnce(a2.promise)
    const w = create()
    await expand(w)
    await w.setProps({ projectId: 'B' })
    await w.setProps({ projectId: 'A' })
    a1.resolve({ runs: [run('a1', [{ rule_id: '旧A', status: 'passed' }])] })
    b.reject(new Error('旧B失败'))
    await flushPromises()
    expect(w.text()).not.toContain('旧A')
    expect(w.find('[data-testid="history-error"]').exists()).toBe(false)
    expect(busy(w)).toBe(true)
    a2.resolve({ runs: [run('a2', [{ rule_id: '本次A', status: 'failed' }])] })
    await flushPromises()
    expect(w.text()).toContain('本次A')
    expect(busy(w)).toBe(false)
  })
  it('已有明细在上下文改变时立即清除，缺项目或年度时不请求', async () => {
    get.mockResolvedValueOnce({ runs: [run('old', [{ rule_id: '已显示旧数据', status: 'passed' }])] })
    const w = create()
    await expand(w)
    expect(w.text()).toContain('已显示旧数据')
    await w.setProps({ year: null })
    expect(w.text()).not.toContain('已显示旧数据')
    expect(get).toHaveBeenCalledTimes(1)
    await w.setProps({ projectId: undefined, year: 2025 })
    expect(get).toHaveBeenCalledTimes(1)
    expect(busy(w)).toBe(false)
  })
  it.each(['resolve', 'reject'] as const)('卸载后迟到 %s 不触发新请求或未处理异常', async (mode) => {
    const pending = deferred()
    get.mockReturnValueOnce(pending.promise)
    const w = create()
    const completion = load(w)
    w.unmount()
    wrappers.splice(wrappers.indexOf(w), 1)
    if (mode === 'resolve') pending.resolve({ runs: [run('late')] })
    else pending.reject(new Error('卸载后失败'))
    await expect(completion).resolves.toBeUndefined()
    expect(get).toHaveBeenCalledTimes(1)
  })
})
