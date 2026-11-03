/**
 * MyTemplatesDialog.spec.ts — 查询模板选择组件（advanced-query-linkage-closure 任务 33；R9.3~R9.5，AQ-16 / AQ-25）
 *
 * - 列表解包：apiProxy 已返回业务数据，读 `{templates, total}`（原先读 `resp.data?.templates` ⇒ 列表恒空，变异 B11-e）；
 * - 缓存按登录用户隔离，打开先显示缓存、同时向服务端重新取（回收站恢复后再打开即能读回）；
 * - 「载入」emit load(config, tpl)；页面版保存的模板 config 不含 source，按 data_source 载入（原先报「配置不完整」）；
 * - 「执行」只在 allowRun 时出现，有不可用原因时置灰；
 * - 删除：确认文案「删除后可在回收站恢复」（原先「不可恢复」，变异 B11-j），只有作者看得到删除按钮。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), delete: vi.fn() }))
// 命名导出 api 与默认导出不是同一个对象：组件用错导出即读不到列表（原先默认导入后再取 .data）
vi.mock('@/services/apiProxy', () => ({ api: apiMocks, default: { get: vi.fn().mockResolvedValue({ data: null }) } }))
const authHolder = vi.hoisted(() => ({ userId: 'u-1' }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => authHolder }))
const confirmMock = vi.hoisted(() => vi.fn())
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }),
    ElMessageBox: { confirm: confirmMock },
  }
})

import ElementPlus, { ElMessage } from 'element-plus'
import MyTemplatesDialog from '../MyTemplatesDialog.vue'
import { TEMPLATE_LIST_CACHE_KEY, writeTemplateCache } from '../queryTemplateCache'

const MINE = { id: 't1', name: '【测试】大额凭证', data_source: 'ledger_entries', scope: 'private', is_owner: true,
  config: { conditions: [{ field: 'debit_amount', op: 'gt', value: '100000000' }] }, updated_at: '2026-10-29T01:00:00' }
const SHARED = { id: 't2', name: '【测试】公开余额', data_source: 'account_balance', scope: 'public', is_owner: false,
  config: { source: 'account_balance' }, updated_at: '2026-10-28T08:00:00+00:00' }
const PARAM_TEMPLATE = { ...MINE, id: 't-param', name: '【测试】参数模板',
  config: { source: 'ledger_entries', conditions: [
    { field: 'line_amount', op: 'gte', value: { $param: 'materiality_performance' } },
  ] } }
const PRESET = { id: 'je_large_amount', name: '大额分录', category: '序时账', description: '按重要性查询',
  data_source: 'ledger_entries', params: ['materiality_performance'], read_only: true }
const RESOLVED = {
  id: PRESET.id, name: PRESET.name,
  config: { source: 'ledger_entries', condition_logic: 'and', conditions: [
    { field: 'line_amount', op: 'gte', value: '1000000', params: ['materiality_performance'] },
  ] },
  params: [{ key: 'materiality_performance', value: '1000000', basis: '本项目 2025 年度实际执行的重要性水平 1,000,000.00 元' }],
  notes: ['借、贷较大者，与抽凭同口径。'],
}

let wrapper: VueWrapper<any> | null = null
async function mountDialog(props: Record<string, unknown> = {}) {
  wrapper = mount(MyTemplatesDialog, {
    props: { modelValue: false, ...props }, global: { plugins: [ElementPlus] }, attachTo: document.body,
  }) as unknown as VueWrapper<any>
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  return wrapper
}
const items = () => Array.from(document.body.querySelectorAll('[data-testid="mtd-item"]')) as HTMLElement[]
const presetItems = () => Array.from(document.body.querySelectorAll('[data-testid="mtd-preset-item"]')) as HTMLElement[]
const button = (row: HTMLElement, id: string) => row.querySelector(`[data-testid="${id}"]`) as HTMLButtonElement | null

beforeEach(() => {
  sessionStorage.clear()
  authHolder.userId = 'u-1'
  apiMocks.get.mockReset().mockImplementation((url: string) => {
    if (url === '/api/custom-query/templates') return Promise.resolve({ templates: [MINE, SHARED], total: 2 })
    if (url === '/api/custom-query/template-presets') return Promise.resolve({ presets: [PRESET] })
    if (url === '/api/custom-query/template-presets/je_large_amount/resolve') return Promise.resolve(RESOLVED)
    if (url === '/api/custom-query/templates/t-param/resolve') return Promise.resolve({ ...RESOLVED, id: 't-param', name: PARAM_TEMPLATE.name })
    return Promise.resolve({})
  })
  apiMocks.delete.mockReset().mockResolvedValue(null)
  confirmMock.mockReset().mockResolvedValue('confirm')
  ;(ElMessage as any).success.mockClear()
  ;(ElMessage as any).warning.mockClear()
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('列表（R9.2）', () => {
  it('打开即取 {templates, total} 并列出；请求自管错误（_silent）', async () => {
    await mountDialog()
    expect(apiMocks.get).toHaveBeenCalledWith('/api/custom-query/templates', expect.objectContaining({ _silent: true }))
    expect(items().map((el) => el.querySelector('.gt-mtd-name')?.textContent?.trim())).toEqual(['【测试】大额凭证', '【测试】公开余额'])
    expect(items()[1].textContent).toContain('公开')
    expect(items()[0].textContent).not.toContain('NaN')
  })

  it('打开先显示本人的缓存，同时重新取（回收站恢复后再打开能读回）；别人的缓存不读', async () => {
    writeTemplateCache([SHARED], { owner: 'u-1' })
    let release: (v: unknown) => void = () => {}
    apiMocks.get.mockReturnValueOnce(new Promise((ok) => { release = ok }))
    await mountDialog()
    expect(items()).toHaveLength(1)
    release({ templates: [MINE, SHARED], total: 2 })
    await flushPromises()
    expect(items()).toHaveLength(2)
    wrapper!.unmount()
    document.body.innerHTML = ''
    authHolder.userId = 'u-2'
    apiMocks.get.mockReturnValueOnce(new Promise(() => {}))
    await mountDialog()
    expect(items(), '换了登录用户不读上一个人的缓存').toHaveLength(0)
  })

  it('取列表失败且没有缓存：显示中文原因', async () => {
    apiMocks.get.mockRejectedValueOnce(Object.assign(new Error('x'), {
      isAxiosError: true, response: { status: 500, data: { message: { message: '服务暂不可用' } }, headers: {} } }))
    await mountDialog()
    expect(document.body.querySelector('[data-testid="mtd-error"]')?.textContent).toContain('加载查询模板')
  })
})

describe('载入与执行（R9.3、R9.4）', () => {
  it('「载入」emit load(config, tpl) 并关闭；页面版模板没有 config.source 也能载入（按 data_source）', async () => {
    const w = await mountDialog()
    button(items()[0], 'mtd-load')!.click()
    await flushPromises()
    expect(w.emitted('load')?.[0]).toEqual([MINE.config, MINE])
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('没有数据源的模板：提示无法载入，不 emit', async () => {
    apiMocks.get.mockResolvedValueOnce({ templates: [{ ...MINE, data_source: '', config: {} }], total: 1 })
    const w = await mountDialog()
    button(items()[0], 'mtd-load')!.click()
    await flushPromises()
    expect(w.emitted('load')).toBeUndefined()
    expect((ElMessage as any).warning).toHaveBeenCalledWith('模板没有数据源，无法载入')
  })

  it('「执行」只在 allowRun 时出现；有不可用原因时置灰，可用时 emit run(tpl)', async () => {
    await mountDialog()
    expect(button(items()[0], 'mtd-run')).toBeNull()
    wrapper!.unmount()
    document.body.innerHTML = ''
    await mountDialog({ allowRun: true, runBlockedReason: '请先选择项目' })
    expect(button(items()[0], 'mtd-run')!.disabled).toBe(true)
    await wrapper!.setProps({ runBlockedReason: '' })
    button(items()[1], 'mtd-run')!.click()
    await flushPromises()
    expect(wrapper!.emitted('run')?.[0]).toEqual([SHARED])
  })
})

describe('删除进回收站（R9.5）', () => {
  it('只有作者有删除按钮；确认文案写明可在回收站恢复；删除后从列表移除并清缓存', async () => {
    await mountDialog()
    expect(button(items()[1], 'mtd-delete'), '不是作者不显示删除').toBeNull()
    sessionStorage.setItem(TEMPLATE_LIST_CACHE_KEY, '{"owner":"u-1","ts":1,"data":[]}')
    button(items()[0], 'mtd-delete')!.click()
    await flushPromises()
    expect(confirmMock.mock.calls[0][0]).toBe('确认删除模板「【测试】大额凭证」？删除后可在回收站恢复。')
    expect(apiMocks.delete).toHaveBeenCalledWith('/api/custom-query/templates/t1', expect.objectContaining({ _silent: true }))
    expect(items()).toHaveLength(1)
    expect(sessionStorage.getItem(TEMPLATE_LIST_CACHE_KEY)).toBeNull()
    expect((ElMessage as any).success.mock.calls.flat().join('')).toContain('可在回收站恢复')
  })

  it('取消确认不删', async () => {
    confirmMock.mockRejectedValueOnce('cancel')
    await mountDialog()
    button(items()[0], 'mtd-delete')!.click()
    await flushPromises()
    expect(apiMocks.delete).not.toHaveBeenCalled()
    expect(items()).toHaveLength(2)
  })
})

describe('系统预置与参数模板（W3）', () => {
  it('系统预置行只显示载入和另存，不显示编辑、删除或执行；载入先 resolve 并组合 notices', async () => {
    const w = await mountDialog({ projectId: 'p1', year: 2025, allowRun: true })
    const row = presetItems()[0]
    expect(row).toBeTruthy()
    expect(button(row, 'mtd-preset-load')).toBeTruthy()
    expect(button(row, 'mtd-preset-save-as')).toBeTruthy()
    expect(button(row, 'mtd-run')).toBeNull()
    expect(button(row, 'mtd-delete')).toBeNull()
    expect(row.querySelector('[data-testid="mtd-edit"]')).toBeNull()
    button(row, 'mtd-preset-load')!.click()
    await flushPromises()
    expect(apiMocks.get).toHaveBeenCalledWith('/api/custom-query/template-presets/je_large_amount/resolve',
      expect.objectContaining({ params: { project_id: 'p1', year: 2025 }, _silent: true }))
    expect(w.emitted('load')?.[0]).toEqual([
      RESOLVED.config,
      expect.objectContaining({ id: PRESET.id, name: PRESET.name, data_source: PRESET.data_source, read_only: true }),
      ['当前阈值：本项目 2025 年度实际执行的重要性水平 1,000,000.00 元', '借、贷较大者，与抽凭同口径。'],
    ])
  })

  it('无项目或年度时系统预置操作禁用，并给出明确中文原因', async () => {
    await mountDialog({ projectId: '', year: 2025 })
    expect(button(presetItems()[0], 'mtd-preset-load')!.disabled).toBe(true)
    expect(wrapper!.vm.resolveBlockedReason).toBe('请先选择项目')
    wrapper!.unmount()
    document.body.innerHTML = ''
    await mountDialog({ projectId: 'p1', year: null })
    expect(button(presetItems()[0], 'mtd-preset-save-as')!.disabled).toBe(true)
    expect(wrapper!.vm.resolveBlockedReason).toBe('请先选择审计年度')
  })

  it('另存系统预置同样先 resolve，并 emit save-as(config, item, notices)', async () => {
    const w = await mountDialog({ projectId: 'p1', year: 2025 })
    button(presetItems()[0], 'mtd-preset-save-as')!.click()
    await flushPromises()
    expect(w.emitted('save-as')?.[0]).toEqual([
      RESOLVED.config,
      expect.objectContaining({ id: PRESET.id, name: PRESET.name }),
      ['当前阈值：本项目 2025 年度实际执行的重要性水平 1,000,000.00 元', '借、贷较大者，与抽凭同口径。'],
    ])
  })

  it('含 $param 的用户模板载入先走用户模板 resolve；普通模板仍本地载入', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/api/custom-query/templates') return Promise.resolve({ templates: [PARAM_TEMPLATE, MINE], total: 2 })
      if (url === '/api/custom-query/template-presets') return Promise.resolve({ presets: [] })
      if (url === '/api/custom-query/templates/t-param/resolve') return Promise.resolve({ ...RESOLVED, id: 't-param' })
      return Promise.resolve({})
    })
    const w = await mountDialog({ projectId: 'p1', year: 2025 })
    button(items()[0], 'mtd-load')!.click()
    await flushPromises()
    expect(apiMocks.get).toHaveBeenCalledWith('/api/custom-query/templates/t-param/resolve',
      expect.objectContaining({ params: { project_id: 'p1', year: 2025 }, _silent: true }))
    expect(w.emitted('load')?.[0]?.[0]).toEqual(RESOLVED.config)
  })
})