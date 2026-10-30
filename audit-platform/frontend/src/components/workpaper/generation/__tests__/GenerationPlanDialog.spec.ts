/**
 * GenerationPlanDialog 挂载测试（spec trim-generation-plan-linkage R2）：
 * 打开即读模板集与计划、循环按裁剪页顺序、只按循环勾选（没有可生成的不可勾）、未保存粗裁提醒、
 * 发送的编码 = 所选循环里「将生成」的、读取失败在弹窗内说明且不能生成、「去程序裁剪」交给宿主。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const mocks = vi.hoisted(() => ({
  sets: vi.fn(),
  plan: vi.fn(),
  generate: vi.fn(),
  operationStatus: vi.fn(),
  operationId: vi.fn(),
  message: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }),
  handleApiError: vi.fn(),
}))

vi.mock('@/services/generationPlanApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/generationPlanApi')>()
  return {
    ...actual,
    listGenerationTemplateSets: mocks.sets,
    getGenerationPlan: mocks.plan,
    getGenerationOperation: mocks.operationStatus,
    runGenerationOperation: mocks.generate,
  }
})
vi.mock('@/services/generationOperationStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/generationOperationStore')>()
  return { ...actual, newGenerationOperationId: mocks.operationId }
})
vi.mock('@/utils/errorHandler', () => ({ handleApiError: mocks.handleApiError }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return { ...actual, ElMessage: mocks.message }
})

import GenerationPlanDialog from '../GenerationPlanDialog.vue'
import { rememberGenerationOperation } from '@/services/generationOperationStore'

const LIVE: VueWrapper[] = []
afterEach(() => {
  while (LIVE.length) LIVE.pop()!.unmount()
  document.body.innerHTML = ''
  sessionStorage.clear()
})
beforeEach(() => {
  mocks.sets.mockReset()
  mocks.plan.mockReset()
  mocks.generate.mockReset()
  mocks.operationStatus.mockReset()
  mocks.operationId.mockReset()
  mocks.operationId.mockReturnValue('00000000-0000-4000-8000-000000000001')
  mocks.handleApiError.mockReset()
  mocks.message.success.mockReset()
  mocks.message.warning.mockReset()
})

const counts = (to_create: number, extra = {}) => ({
  total: to_create, to_create, existing: 0, in_recycle: 0, trimmed: 0, category_excluded: 0, ...extra,
})
const item = (wp_code: string, state: string) => ({
  wp_code, wp_name: `底稿${wp_code}`, state, decided_by: null, follows_children: false,
  category_applicable: true, category_reason: null, category_conflict: false,
})
const PLAN = {
  template_set: { id: 's1', set_name: '标准年审', code_count: 6 },
  business_category: { code: 'C', defaulted: true },
  totals: counts(4),
  cycles: [
    { cycle: 'A', trim_state: 'unconfirmed', confirmed_at: null, confirmed_by: null, counts: counts(1),
      programs: [], items: [item('A1', 'to_create')] },
    { cycle: 'D', trim_state: 'confirmed', confirmed_at: '2026-10-28T02:00:00+00:00', confirmed_by: '王经理',
      counts: counts(2, { total: 4, trimmed: 1, existing: 1 }), programs: [],
      items: [item('D0', 'existing'), item('D2', 'trimmed'), item('D4', 'to_create'), item('D4-5', 'to_create')] },
    { cycle: 'B', trim_state: 'not_initialized', confirmed_at: null, confirmed_by: null,
      counts: counts(0, { total: 1, in_recycle: 1 }), programs: [], items: [item('B5-1', 'in_recycle')] },
    { cycle: 'S', trim_state: 'not_initialized', confirmed_at: null, confirmed_by: null, counts: counts(1),
      programs: [], items: [item('S32', 'to_create')] },
  ],
}

async function open(props: Record<string, unknown> = {}) {
  const w = mount(GenerationPlanDialog, {
    props: { modelValue: false, projectId: 'p1', year: 2025, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  LIVE.push(w)
  await w.setProps({ modelValue: true })
  await flushPromises()
  await nextTick()
  return w
}

const rows = () => Array.from(document.body.querySelectorAll('.gt-gen-plan__row:not(.gt-gen-plan__row--head)'))
const rowOf = (label: string) => rows().find((r) => r.querySelector('.gt-gen-plan__cycle')?.textContent?.trim() === label)!
const buttonByText = (text: string) =>
  Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.trim().startsWith(text)) as HTMLButtonElement

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('GenerationPlanDialog', () => {
  beforeEach(() => {
    mocks.sets.mockResolvedValue([{ id: 's1', set_name: '标准年审', template_codes: [] }])
    mocks.plan.mockResolvedValue(JSON.parse(JSON.stringify(PLAN)))
  })

  it('打开即读计划；循环按裁剪页顺序；只默认勾初始循环；未保存粗裁提醒', async () => {
    await open({ initialCycle: 'D' })
    expect(mocks.plan).toHaveBeenCalledWith('p1', 's1')
    expect(rows().map((r) => r.querySelector('.gt-gen-plan__cycle')?.textContent?.trim()))
      .toEqual(['B 初步业务', 'D 收入', 'A 完成阶段', 'S 专项'])
    const text = document.body.textContent || ''
    expect(text).toContain('业务分类：C 类（项目未填写 A / B / C 业务分类，按 C 类判断）')
    expect(text).toContain('2 个循环的程序裁剪还没保存过')
    expect(text).toContain('已选 1 个循环，将生成 2 个底稿')
    expect(rowOf('B 初步业务').querySelector('.el-checkbox.is-disabled')).not.toBeNull()
    expect(rowOf('D 收入').querySelector('.el-checkbox.is-checked')).not.toBeNull()
    expect(rowOf('A 完成阶段').querySelector('.el-checkbox.is-checked')).toBeNull()
  })

  it('重开页面可从 sessionStorage 取回 terminal 原回执，不再发写请求', async () => {
    const operationId = '00000000-0000-4000-8000-000000000099'
    const receipt = { created: 1, count: 1, created_codes: ['D4'], operation_id: operationId, status: 'succeeded' }
    rememberGenerationOperation({
      projectId: 'p1', operationId, requestKey: 'old-request',
      templateSetId: 's1', year: 2025, codes: ['D4'], savedAt: 1,
    })
    mocks.operationStatus.mockResolvedValue({
      operation_id: operationId, status: 'succeeded', terminal: true, receipt,
    })
    const w = await open()
    expect(mocks.operationStatus).toHaveBeenCalledWith('p1', operationId)
    expect(mocks.generate).not.toHaveBeenCalled()
    expect(w.emitted('generated')?.[0]?.[0]).toEqual(receipt)
    expect(sessionStorage.length).toBe(0)
  })

  it('生成只发所选循环里「将生成」的编码，回执提示后关闭', async () => {
    mocks.generate.mockResolvedValue({ created: 3, count: 3 })
    const w = await open()
    expect(document.body.textContent).toContain('已选 3 个循环，将生成 4 个底稿')
    ;(rowOf('S 专项').querySelector('.el-checkbox input') as HTMLInputElement).click()
    await flushPromises()
    expect(document.body.textContent).toContain('已选 2 个循环，将生成 3 个底稿')
    buttonByText('生成 3 个底稿').click()
    await flushPromises()
    expect(mocks.generate).toHaveBeenCalledWith('p1', {
      templateSetId: 's1', year: 2025, codes: ['D4', 'D4-5', 'A1'],
      operationId: '00000000-0000-4000-8000-000000000001',
    })
    expect(mocks.message.success).toHaveBeenCalled()
    expect(w.emitted('generated')?.[0]?.[0]).toEqual({ created: 3, count: 3 })
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('失败后同一请求再次点击复用已持久化的 operation id', async () => {
    mocks.operationId
      .mockReturnValueOnce('00000000-0000-4000-8000-000000000011')
      .mockReturnValueOnce('00000000-0000-4000-8000-000000000022')
    mocks.generate.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce({ created: 4, count: 4 })
    await open()
    buttonByText('生成 4 个底稿').click()
    await flushPromises()
    buttonByText('生成 4 个底稿').click()
    await flushPromises()
    expect(mocks.operationId).toHaveBeenCalledTimes(1)
    expect(mocks.generate.mock.calls[0][1].operationId).toBe('00000000-0000-4000-8000-000000000011')
    expect(mocks.generate.mock.calls[1][1].operationId).toBe('00000000-0000-4000-8000-000000000011')
  })

  it('没有审计年度不发生成请求', async () => {
    await open({ year: null })
    buttonByText('生成 4 个底稿').click()
    await flushPromises()
    expect(mocks.generate).not.toHaveBeenCalled()
    expect(mocks.message.warning).toHaveBeenCalledWith('未设置审计年度，请先在项目基本信息中填写')
  })

  it('计划读不到：弹窗内说明原因，生成按钮不可用', async () => {
    mocks.plan.mockRejectedValue({
      response: { status: 503, data: { detail: { error: 'trim_scope_unavailable', message: '无法读取程序裁剪结果，已停止生成底稿，请稍后重试' } } },
    })
    await open()
    expect(document.body.textContent).toContain('生成计划读取失败：无法读取程序裁剪结果，已停止生成底稿，请稍后重试')
    expect(buttonByText('生成 0 个底稿').disabled).toBe(true)
  })

  it('「去程序裁剪」交给宿主并关闭弹窗', async () => {
    const w = await open()
    ;(rowOf('A 完成阶段').querySelector('.gt-gen-plan__ops .el-button--primary') as HTMLButtonElement).click()
    await flushPromises()
    expect(w.emitted('navigate-cycle')?.[0]).toEqual(['A'])
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('关闭后重开：第一次打开的模板集响应晚到不能接管新弹窗', async () => {
    const oldSets = deferred<any[]>()
    mocks.sets
      .mockImplementationOnce(() => oldSets.promise)
      .mockResolvedValueOnce([{ id: 's2', set_name: '第二次模板集', template_codes: [] }])
    const w = mount(GenerationPlanDialog, {
      props: { modelValue: false, projectId: 'p1', year: 2025 },
      global: { plugins: [ElementPlus] }, attachTo: document.body,
    })
    LIVE.push(w)
    await w.setProps({ modelValue: true })
    await nextTick()
    await w.setProps({ modelValue: false })
    await w.setProps({ modelValue: true })
    await flushPromises()
    expect(mocks.plan).toHaveBeenCalledTimes(1)
    expect(mocks.plan).toHaveBeenLastCalledWith('p1', 's2')

    oldSets.resolve([{ id: 'old', set_name: '过期模板集', template_codes: [] }])
    await flushPromises()
    expect(mocks.plan).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).not.toContain('过期模板集')
  })

  it('项目在弹窗打开时切换会启动新 epoch，只显示新项目计划', async () => {
    const oldPlan = deferred<any>()
    mocks.plan.mockImplementationOnce(() => oldPlan.promise).mockResolvedValueOnce(JSON.parse(JSON.stringify(PLAN)))
    const w = mount(GenerationPlanDialog, {
      props: { modelValue: true, projectId: 'p1', year: 2025 },
      global: { plugins: [ElementPlus] }, attachTo: document.body,
    })
    LIVE.push(w)
    await nextTick()
    await w.setProps({ projectId: 'p2' })
    await flushPromises()
    expect(mocks.plan).toHaveBeenLastCalledWith('p2', 's1')
    oldPlan.resolve({ ...PLAN, cycles: [] })
    await flushPromises()
    expect(rows()).not.toHaveLength(0)
  })

  it('生成中禁止关闭和跳转；父级强制关闭重开后旧回执不控制新弹窗', async () => {
    const pending = deferred<any>()
    mocks.generate.mockImplementationOnce(() => pending.promise)
    const w = await open()
    buttonByText('生成 4 个底稿').click()
    await nextTick()
    expect(buttonByText('取消').disabled).toBe(true)
    const trim = rowOf('A 完成阶段').querySelector('.gt-gen-plan__ops .el-button--primary') as HTMLButtonElement
    expect(trim.disabled).toBe(true)

    await w.setProps({ modelValue: false })
    await w.setProps({ modelValue: true })
    await flushPromises()
    pending.resolve({ created: 4, count: 4 })
    await flushPromises()
    expect(w.emitted('generated')).toBeUndefined()
    expect(mocks.message.success).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('生成底稿')
  })

  it('打开后权限被撤销时禁用提交，并给循环控件可访问名称；明细一次只展开一个循环', async () => {
    const w = await open({ canSubmit: false, disabledReason: '项目已归档，不能生成底稿' })
    expect(document.body.textContent).toContain('项目已归档，不能生成底稿')
    expect(buttonByText('生成 4 个底稿').disabled).toBe(true)
    expect(rowOf('D 收入').querySelector('[aria-label="选择D 收入循环"]')).not.toBeNull()

    const dDetail = rowOf('D 收入').querySelector('button[aria-label="展开D 收入明细"]') as HTMLButtonElement
    dDetail.click()
    await nextTick()
    expect(document.body.querySelectorAll('.gt-gen-plan__detail')).toHaveLength(1)
    const aDetail = rowOf('A 完成阶段').querySelector('button[aria-label="展开A 完成阶段明细"]') as HTMLButtonElement
    aDetail.click()
    await nextTick()
    expect(document.body.querySelectorAll('.gt-gen-plan__detail')).toHaveLength(1)
  })
})
