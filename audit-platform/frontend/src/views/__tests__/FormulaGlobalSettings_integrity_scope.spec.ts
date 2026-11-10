/** 候选页范围与并发回归：只挂载生产页，驱动真实子组件事件及生产 submit 回调。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'
import ElementPlus from 'element-plus'
import type { Definition, GlobalSlot, SyncPreview } from '@/composables/formula/useFormulaSettings'

const { api, route, msg } = vi.hoisted(() => ({
  api: { domains: vi.fn(), global: vi.fn(), previewGlobal: vi.fn(), publishGlobal: vi.fn(), publishes: vi.fn() },
  route: { query: {} as Record<string, string> },
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: api }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }))
vi.mock('element-plus', async (importOriginal) => ({
  ...await importOriginal<Record<string, unknown>>(), ElMessage: msg,
}))

import FormulaGlobalSettings from '../FormulaGlobalSettings.vue'
import FormulaDefinitionEditDialog from '@/components/formula/settings/FormulaDefinitionEditDialog.vue'
import FormulaPublishPreviewDialog from '@/components/formula/settings/FormulaPublishPreviewDialog.vue'

const A = 'soe_standalone'
const B = 'listed_standalone'
const SLOT = 'balance_sheet:BS-002'
const DOMAINS = [
  { key: 'report', label: '报表公式', scope_kind: 'standard', wired: true,
    scopes: [{ value: A, label: '国企单体' }, { value: B, label: '上市单体' }],
    exec_fields: ['formula'], desc_fields: [] },
  { key: 'note', label: '附注公式', scope_kind: 'template_type', wired: true,
    scopes: [{ value: 'soe', label: '国企版' }], exec_fields: ['formula'], desc_fields: [] },
]
function response(domain = 'report', scope = A, version = 7) {
  const row: GlobalSlot = { slot_key: SLOT, label: `${scope}货币资金`, layer: 'global',
    definition: { formula: scope === A ? '10' : '20' }, version, structure: { row_number: 2 } }
  return { domain, scope, can_edit: true, slots: [row] }
}
function preview(scope = A): SyncPreview {
  return { domain: 'report', scope, changes: [], version_problems: [], summary: {}, items: [], marker: scope }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const payload = () => ({ decisions: { project_choices: {}, conflict_choices: {}, default_conflict: 'ask' as const }, note: '' })

const pages: Array<{ unmount: () => void }> = []
function mountPage() {
  const w = shallowMount(FormulaGlobalSettings, { global: { plugins: [ElementPlus], renderStubDefaultSlot: false,
    stubs: { ElTabs: { template: '<div><slot /></div>' }, ElTabPane: { template: '<section><slot /></section>' },
      // 父页成功后调用其真实 expose.load；不能让自动浅桩把这一契约变成 undefined。
      FormulaPublishRecords: false },
  } })
  pages.push(w)
  return w
}
type Page = ReturnType<typeof mountPage>
const state = (w: Page) => (w.vm as any).$.setupState
function publishDialog(w: Page) {
  // 发布记录也嵌有候选审核预览，按父组件身份选当前页自己的会话，不能拿第一个同名弹窗。
  return w.findAllComponents(FormulaPublishPreviewDialog)
    .find((dialog) => (dialog.vm as any).$.parent.uid === (w.vm as any).$.uid)
}
function listener(w: { vm: unknown }, key: string): (...args: any[]) => any {
  const callback = (w.vm as any).$.vnode.props[key]
  expect(typeof callback).toBe('function')
  return callback
}
async function openEditor(w: Page, row: GlobalSlot = state(w).slots[0]) {
  state(w).openEdit(row)
  await nextTick()
  const editor = w.findComponent(FormulaDefinitionEditDialog)
  expect(editor.exists()).toBe(true)
  expect(editor.props('modelValue')).toBe(true)
  return editor
}
async function stage(w: Page, formula: string) {
  const editor = await openEditor(w)
  editor.vm.$emit('save', { formula })
  await nextTick()
  expect(state(w).staged.get(SLOT)?.definition).toEqual({ formula })
}
async function showPreview(w: Page) {
  await state(w).onPreview()
  await nextTick()
  const dialog = publishDialog(w)!
  expect(dialog.exists()).toBe(true)
  expect(dialog.props('modelValue')).toBe(true)
  return dialog
}
async function switchScope(w: Page, value: string) {
  state(w).scope = value
  await state(w).onScopeChange()
  await nextTick()
}
afterEach(() => { for (const w of pages.splice(0)) w.unmount() })
beforeEach(() => {
  vi.resetAllMocks()
  route.query = { domain: 'report', scope: A }
  api.domains.mockResolvedValue({ domains: DOMAINS, is_admin: true })
  api.global.mockImplementation(async (domain: string, scope: string) => response(domain, scope))
  api.previewGlobal.mockImplementation(async (_domain: string, body: { scope: string }) => preview(body.scope))
  api.publishGlobal.mockResolvedValue({ publish_id: '发布成功', changed_project_count: 1, summary: { pending_total: 0 } })
  api.publishes.mockResolvedValue({ items: [] })
})

describe('全局公式范围与并发完整性', () => {
  it.each(['scope', 'domain'] as const)('同 slot 同版本：旧编辑保存与关闭回调不能跨 %s 写进新会话', async (kind) => {
    const w = mountPage()
    await flushPromises()
    const oldEditor = await openEditor(w)
    const oldSave = listener(oldEditor, 'onSave')
    const oldClose = listener(oldEditor, 'onUpdate:modelValue')
    const oldVersion = oldEditor.props('definition')
    if (kind === 'scope') await switchScope(w, B)
    else { state(w).domainKey = 'note'; await state(w).onDomainChange() }
    const currentEditor = await openEditor(w)
    expect(state(w).slots[0].version).toBe(7)
    expect(currentEditor.props('definition')).not.toEqual(oldVersion)
    oldSave({ formula: '过期会话' })
    oldClose(false)
    await nextTick()
    expect(state(w).staged.size).toBe(0)
    expect(w.findComponent(FormulaDefinitionEditDialog).props('modelValue')).toBe(true)
    currentEditor.vm.$emit('save', { formula: '新范围值' })
    await nextTick()
    const dialog = await showPreview(w)
    expect(await dialog.props('submit')(payload())).toBe(true)
    expect(api.publishGlobal).toHaveBeenCalledTimes(1)
    expect(api.publishGlobal).toHaveBeenCalledWith(kind === 'scope' ? 'report' : 'note', expect.objectContaining({
      scope: kind === 'scope' ? B : 'soe', changes: [expect.objectContaining({
        slot_key: SLOT, expected_version: 7, definition: { formula: '新范围值' },
      })],
    }))
  })

  it('相同范围重开编辑器：旧保存和随后关闭事件不能作用于新编辑器', async () => {
    const w = mountPage()
    await flushPromises()
    const first = await openEditor(w)
    const oldSave = listener(first, 'onSave')
    const oldClose = listener(first, 'onUpdate:modelValue')
    const second = await openEditor(w)
    oldSave({ formula: '111' })
    oldClose(false)
    await nextTick()
    expect(state(w).staged.size).toBe(0)
    expect(w.findComponent(FormulaDefinitionEditDialog).props('modelValue')).toBe(true)
    second.vm.$emit('save', { formula: '222' })
    await nextTick()
    expect(state(w).staged.get(SLOT).definition).toEqual({ formula: '222' })
  })

  it('旧预览的 submit 和关闭事件不能转发到新范围同位同版本的预览', async () => {
    const w = mountPage()
    await flushPromises()
    await stage(w, '101')
    const oldDialog = await showPreview(w)
    const oldSubmit = oldDialog.props('submit')
    const oldClose = listener(oldDialog, 'onUpdate:modelValue')
    await switchScope(w, B)
    await stage(w, '202')
    const current = await showPreview(w)
    expect(current.props('title')).not.toEqual(oldDialog.props('title'))
    expect(await oldSubmit(payload())).toBe(false)
    oldClose(false)
    await nextTick()
    expect(api.publishGlobal).not.toHaveBeenCalled()
    expect(publishDialog(w)!.props('modelValue')).toBe(true)
    expect(await current.props('submit')(payload())).toBe(true)
    expect(api.publishGlobal).toHaveBeenCalledWith('report', expect.objectContaining({
      scope: B, changes: [expect.objectContaining({ definition: { formula: '202' }, expected_version: 7 })],
    }))
  })

  it.each([
    ['成功先回', false, false], ['失败先回', true, false], ['成功后回', false, true], ['失败后回', true, true],
  ] as const)('切范围后旧加载%s：数据、错误与 finally 都不干扰新加载', async (_name, fail, newFirst) => {
    const w = mountPage()
    await flushPromises()
    const old = deferred<ReturnType<typeof response>>()
    const current = deferred<ReturnType<typeof response>>()
    api.global.mockImplementationOnce(() => old.promise).mockImplementationOnce(() => current.promise)
    const oldLoad = state(w).loadSlots()
    state(w).scope = B
    const currentLoad = state(w).onScopeChange()
    if (newFirst) { current.resolve(response('report', B, 9)); await currentLoad }
    if (fail) old.reject({ response: { status: 500, data: { detail: '旧请求失败' } } })
    else old.resolve(response('report', A, 8))
    await oldLoad
    expect(state(w).loading).toBe(!newFirst)
    expect(state(w).slots).toEqual(newFirst ? response('report', B, 9).slots : [])
    expect(msg.error).not.toHaveBeenCalled()
    if (!newFirst) { current.resolve(response('report', B, 9)); await currentLoad }
    expect(state(w).slots).toEqual(response('report', B, 9).slots)
    expect(state(w).loading).toBe(false)
  })

  it('同范围重复加载按请求顺序只认最新一次', async () => {
    const w = mountPage()
    await flushPromises()
    const old = deferred<ReturnType<typeof response>>()
    const current = deferred<ReturnType<typeof response>>()
    api.global.mockImplementationOnce(() => old.promise).mockImplementationOnce(() => current.promise)
    const oldLoad = state(w).loadSlots()
    const currentLoad = state(w).loadSlots()
    old.resolve(response('report', A, 8))
    await oldLoad
    expect(state(w).loading).toBe(true)
    expect(state(w).slots[0].version).toBe(7)
    current.resolve(response('report', A, 9))
    await currentLoad
    expect(state(w).slots[0].version).toBe(9)
    expect(state(w).loading).toBe(false)
  })

  it('A→B→A 后即使范围和版本相同，也不能接受第一代加载', async () => {
    const w = mountPage()
    await flushPromises()
    const old = deferred<ReturnType<typeof response>>()
    api.global.mockImplementationOnce(() => old.promise)
    const oldLoad = state(w).loadSlots()
    await switchScope(w, B)
    await switchScope(w, A)
    const current = state(w).slots
    old.resolve(response('report', A, 99))
    await oldLoad
    expect(state(w).slots).toBe(current)
    expect(state(w).slots[0].version).toBe(7)
  })

  it.each([false, true])('旧预览迟到（失败=%s）不重开弹窗、不清新加载状态', async (fail) => {
    const w = mountPage()
    await flushPromises()
    await stage(w, '101')
    const old = deferred<SyncPreview>()
    const current = deferred<SyncPreview>()
    api.previewGlobal.mockImplementationOnce(() => old.promise).mockImplementationOnce(() => current.promise)
    const oldPreview = state(w).onPreview()
    await switchScope(w, B)
    await stage(w, '202')
    const currentPreview = state(w).onPreview()
    if (fail) old.reject({ response: { status: 500 } })
    else old.resolve(preview(A))
    await oldPreview
    await nextTick()
    expect(state(w).previewLoading).toBe(true)
    expect(state(w).previewVisible).toBe(false)
    expect(state(w).preview).toBeNull()
    expect(msg.error).not.toHaveBeenCalled()
    current.resolve(preview(B))
    await currentPreview
    await nextTick()
    expect(state(w).previewLoading).toBe(false)
    expect(publishDialog(w)!.props('preview')).toMatchObject({ scope: B })
    expect(publishDialog(w)!.props('modelValue')).toBe(true)
  })

  it.each(['edit', 'delete', 'clear'] as const)('%s 使旧预览和已捕获提交失效，必须重新预览', async (action) => {
    const w = mountPage()
    await flushPromises()
    await stage(w, '101')
    const old = await showPreview(w)
    const oldSubmit = old.props('submit')
    if (action === 'edit') await stage(w, '303')
    else if (action === 'delete') state(w).stageDelete(state(w).slots[0])
    else state(w).clearStaged()
    await nextTick()
    expect(publishDialog(w)).toBeUndefined()
    expect(await oldSubmit(payload())).toBe(false)
    expect(api.publishGlobal).not.toHaveBeenCalled()
    if (action === 'clear') await stage(w, '404')
    const current = await showPreview(w)
    expect(await oldSubmit(payload())).toBe(false)
    expect(await current.props('submit')(payload())).toBe(true)
    expect(api.publishGlobal.mock.calls[0][1].changes[0].definition).toEqual(
      action === 'delete' ? null : { formula: action === 'edit' ? '303' : '404' })
  })

  it('旧预览已被新预览取代后，旧结果不能覆盖新结果', async () => {
    const w = mountPage()
    await flushPromises()
    await stage(w, '101')
    const old = deferred<SyncPreview>()
    const current = deferred<SyncPreview>()
    api.previewGlobal.mockImplementationOnce(() => old.promise).mockImplementationOnce(() => current.promise)
    const oldPreview = state(w).onPreview()
    const currentPreview = state(w).onPreview()
    current.resolve({ ...preview(A), marker: '最新' })
    await currentPreview
    old.resolve({ ...preview(A), marker: '已过期' })
    await oldPreview
    await nextTick()
    expect(publishDialog(w)!.props('preview')).toMatchObject({ marker: '最新' })
    expect(state(w).previewLoading).toBe(false)
  })

  it('发布在途切范围且新暂存后，旧成功和旧关闭事件不能清新篮', async () => {
    const w = mountPage()
    await flushPromises()
    await stage(w, '101')
    const old = await showPreview(w)
    const oldSubmit = old.props('submit')
    const oldClose = listener(old, 'onUpdate:modelValue')
    const pending = deferred<{ changed_project_count: number }>()
    api.publishGlobal.mockImplementationOnce(() => pending.promise)
    const publish = oldSubmit(payload())
    await switchScope(w, B)
    await stage(w, '202')
    const loadCount = api.global.mock.calls.length
    pending.resolve({ changed_project_count: 1 })
    expect(await publish).toBe(true)
    oldClose(false)
    await nextTick()
    expect(state(w).staged.get(SLOT)).toMatchObject({ definition: { formula: '202' }, expected_version: 7 })
    expect(api.global).toHaveBeenCalledTimes(loadCount)
    expect(state(w).slots).toEqual(response('report', B).slots)
    const current = await showPreview(w)
    oldClose(false)
    await nextTick()
    expect(publishDialog(w)!.props('modelValue')).toBe(true)
    expect(await current.props('submit')(payload())).toBe(true)
    expect(api.publishGlobal.mock.calls.map((call) => call[1].scope)).toEqual([A, B])
  })

  it('当前发布 409 丢弃旧版本并实际重读；旧确认无法重试，须重新编辑预览', async () => {
    const w = mountPage()
    await flushPromises()
    await stage(w, '101')
    const old = await showPreview(w)
    const oldSubmit = old.props('submit')
    const staleId = state(w).previewSession.snapshot.requestId
    const reload = deferred<ReturnType<typeof response>>()
    api.global.mockImplementationOnce(() => reload.promise)
    api.publishGlobal.mockRejectedValueOnce({ response: { status: 409, data: { detail: '版本已变化' } } })
    const loadsBefore = api.global.mock.calls.length
    const publish = oldSubmit(payload())
    await flushPromises()
    expect(state(w).staged.size).toBe(0)
    expect(state(w).previewSession).toBeNull()
    expect(state(w).loading).toBe(true)
    expect(api.global).toHaveBeenCalledTimes(loadsBefore + 1)
    state(w).openEdit(state(w).slots[0])
    expect(state(w).editSession).toBeNull()
    reload.resolve(response('report', A, 8))
    expect(await publish).toBe(false)
    expect(await oldSubmit(payload())).toBe(false)
    expect(msg.warning).toHaveBeenCalledWith('版本已变化')
    expect(state(w).slots[0].version).toBe(8)
    await stage(w, '303')
    const current = await showPreview(w)
    expect(state(w).previewSession.snapshot.requestId).not.toBe(staleId)
    expect(await oldSubmit(payload())).toBe(false)
    expect(await current.props('submit')(payload())).toBe(true)
    expect(api.publishGlobal.mock.calls.map((call) => call[1].changes[0].expected_version)).toEqual([7, 8])
  })

  it('预览和发布冻结定义、结构、版本与请求号；500 重试不重拼当前 Map', async () => {
    const w = mountPage()
    await flushPromises()
    const row = reactive({ ...response().slots[0], structure: { row_number: 2 } })
    const editor = await openEditor(w, row)
    const definition: Definition = reactive({ formula: '101', nested: { label: '原说明' } })
    editor.vm.$emit('save', definition)
    await nextTick()
    definition.formula = '999'
    definition.nested.label = '编辑器后来改动'
    const dialog = await showPreview(w)
    const submit = dialog.props('submit')
    const expected = [{ slot_key: SLOT, label: row.label, definition: { formula: '101', nested: { label: '原说明' } },
      expected_version: 7, structure: { row_number: 2 } }]
    expect(api.previewGlobal.mock.calls[0]).toEqual(['report', { scope: A, changes: expected }])
    state(w).staged.get(SLOT).definition.formula = '888'
    state(w).staged.get(SLOT).structure.row_number = 99
    row.version = 90
    row.structure.row_number = 90
    api.publishGlobal.mockRejectedValueOnce({ response: { status: 500 } })
    const firstPayload = payload()
    expect(await submit(firstPayload)).toBe(false)
    expect(state(w).previewVisible).toBe(true)
    expect(state(w).staged.size).toBe(1)
    firstPayload.decisions.default_conflict = 'keep' as any
    expect(await submit(payload())).toBe(true)
    const [first, second] = api.publishGlobal.mock.calls.map((call) => call[1])
    expect(first).toMatchObject({ scope: A, changes: expected, decisions: payload().decisions })
    expect(second).toMatchObject({ scope: A, changes: expected, decisions: payload().decisions })
    expect(first.request_id).toBeTruthy()
    expect(second.request_id).toBe(first.request_id)
    expect(msg.error).toHaveBeenCalledWith('发布失败')
  })

  it('同一 submit 在途重复点击只发一个发布请求，失败后可用同号重试', async () => {
    const w = mountPage()
    await flushPromises()
    await stage(w, '101')
    const dialog = await showPreview(w)
    const submit = dialog.props('submit')
    const pending = deferred<never>()
    api.publishGlobal.mockImplementationOnce(() => pending.promise)
    const first = submit(payload())
    expect(await submit(payload())).toBe(false)
    expect(api.publishGlobal).toHaveBeenCalledTimes(1)
    pending.reject({ response: { status: 500 } })
    expect(await first).toBe(false)
    expect(await submit(payload())).toBe(true)
    expect(api.publishGlobal).toHaveBeenCalledTimes(2)
    expect(api.publishGlobal.mock.calls[1][1].request_id).toBe(api.publishGlobal.mock.calls[0][1].request_id)
  })

  it('旧范围发布 409 不清新范围暂存、不重读且不把旧错误冒给新会话', async () => {
    const w = mountPage()
    await flushPromises()
    await stage(w, '101')
    const dialog = await showPreview(w)
    const pending = deferred<never>()
    api.publishGlobal.mockImplementationOnce(() => pending.promise)
    const publish = dialog.props('submit')(payload())
    await switchScope(w, B)
    await stage(w, '202')
    const loadsBefore = api.global.mock.calls.length
    pending.reject({ response: { status: 409 } })
    expect(await publish).toBe(false)
    expect(state(w).staged.get(SLOT).definition).toEqual({ formula: '202' })
    expect(api.global).toHaveBeenCalledTimes(loadsBefore)
    expect(msg.warning).not.toHaveBeenCalledWith('数据已被他人修改，请刷新后重试')
    expect(msg.error).not.toHaveBeenCalled()
  })
})
