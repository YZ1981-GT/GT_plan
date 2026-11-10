/**
 * 公式模板的保存与管理（spec formula-global-settings-sync，R13.1 / R13.2 / R13.4 / R13.6 / R13.7 / R13.9）
 *
 * FormulaTemplateSaveDialog：从本项目保存（默认只取本项目自己的公式，不传公式位；「全部有效公式」显式列出）、
 *   项目组 / 集团模板归属当前项目、事务所模板只给管理员、从全局保存须选适用范围。
 * FormulaTemplateDetailDrawer：「全局已变」提示按四类处理（spec formula-management-repair-closure R6）——同步全局 / 移出模板
 *   = 暂存 → 发布新版本（带模板版本号、同一请求号）；保留模板 = 只更新基线（带模板版本 + 全局版本，不发新版本）；
 *   非管理员「设为全局」= 确认后提交候选（不预览）；删除先确认。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { copyTemplateValue, formulaTemplateCasApi, TemplatePreviewEvidenceError } from '@/services/formulaTemplateCas'
import ElementPlus from 'element-plus'

const { api, msg, confirm } = vi.hoisted(() => ({
  api: {
    domains: vi.fn(), effective: vi.fn(), createTemplate: vi.fn(), template: vi.fn(), templateVersions: vi.fn(),
    templateSubscribers: vi.fn(), templatePublishPreview: vi.fn(), templatePublish: vi.fn(),
    templatePromotePreview: vi.fn(), templatePromote: vi.fn(), deleteTemplate: vi.fn(), updateTemplate: vi.fn(),
    templateKeepBaseline: vi.fn(), templateRollbackPreview: vi.fn(), templateRollback: vi.fn(),
  },
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  confirm: { confirmDelete: vi.fn(), confirmDangerous: vi.fn() },
}))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: api }))
vi.mock('@/utils/confirm', () => confirm)
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg }
})

import FormulaTemplateSaveDialog from '../FormulaTemplateSaveDialog.vue'
import FormulaTemplateDetailDrawer from '../FormulaTemplateDetailDrawer.vue'

const DialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>',
})
const DrawerStub = defineComponent({
  name: 'ElDrawer',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue"><slot /></div>',
})
const PreviewStub = defineComponent({
  name: 'FormulaPublishPreviewDialog', props: ['modelValue', 'preview', 'submit'], template: '<div />',
})
const DOMAINS = [
  { key: 'report', label: '报表公式', wired: true, scope_kind: 'standard', scopes: [], exec_fields: ['formula'], desc_fields: [] },
  { key: 'note', label: '附注公式', wired: true, scope_kind: 'template_type', scopes: [], exec_fields: ['formula'], desc_fields: [] },
]
const DETAIL = {
  id: 't1', name: '本所口径', description: null, share_scope: 'team', share_scope_label: '项目组',
  owner_user_id: 'u1', owner_project_id: 'p1', applicable_scope: 'soe_standalone', domains: ['report'],
  version: 3, status: 'active', can_manage: true, updated_at: null, subscriber_count: 1,
  definitions: { report: [{ slot_key: 'balance_sheet:BS-002', label: '货币资金', definition: { formula: 'A' }, structure: {}, version: 3 }] },
  global_hints: [{
    domain: 'report', slot_key: 'balance_sheet:BS-002', label: '货币资金', kind: 'conflict', template_definition: { formula: 'A' },
    base_definition: { formula: 'A0' }, base_version: 4, global_definition: { formula: 'G' }, global_version: 5,
    same_as_template: false,
  }],
}
/** 四类提示各一条（spec formula-management-repair-closure R6.1） */
const HINTS = [
  { domain: 'report', slot_key: 'balance_sheet:BS-001', label: '甲', kind: 'follow', template_definition: { formula: 'A0' },
    base_definition: { formula: 'A0' }, base_version: 1, global_definition: { formula: 'G1' }, global_version: 2, same_as_template: false },
  { domain: 'report', slot_key: 'balance_sheet:BS-002', label: '乙', kind: 'same', template_definition: { formula: 'M' },
    base_definition: { formula: 'B0' }, base_version: 1, global_definition: { formula: 'M' }, global_version: 2, same_as_template: true },
  { domain: 'report', slot_key: 'balance_sheet:BS-003', label: '丙', kind: 'conflict', template_definition: { formula: 'X' },
    base_definition: { formula: 'C0' }, base_version: 1, global_definition: { formula: 'G3' }, global_version: 2, same_as_template: false },
  { domain: 'report', slot_key: 'balance_sheet:BS-004', label: '丁', kind: 'deleted', template_definition: { formula: 'D0' },
    base_definition: { formula: 'D0' }, base_version: 1, global_definition: null, global_version: null, same_as_template: false },
]

beforeEach(() => {
  for (const mock of [...Object.values(api), ...Object.values(msg), ...Object.values(confirm)]) mock.mockReset()
  api.domains.mockResolvedValue({ domains: DOMAINS, is_admin: false })
  api.effective.mockResolvedValue({ slots: [
    { slot_key: 'balance_sheet:BS-002', definition: { formula: 'A' }, disabled: false },
    { slot_key: 'balance_sheet:BS-003', definition: { formula: null }, disabled: true },
  ] })
  api.createTemplate.mockResolvedValue({ name: '本所口径', definitions: { report: [{}] } })
  api.template.mockResolvedValue(JSON.parse(JSON.stringify(DETAIL)))
  api.templateVersions.mockResolvedValue({ items: [] })
  api.templateSubscribers.mockResolvedValue({ items: [] })
  api.templatePublishPreview.mockResolvedValue({ template_id: 't1', version: 3, next_version: 4,
    preview_fingerprint: 'a'.repeat(64), changes: [], summary: {}, items: [] })
  api.templateRollbackPreview.mockResolvedValue({ template_id: 't1', version: 3, target_version: 1,
    preview_fingerprint: 'b'.repeat(64), changes: [], summary: {}, items: [] })
  api.templateRollback.mockResolvedValue({ version: 4 })
  api.templatePublish.mockResolvedValue({ version: 4 })
  api.templatePromote.mockResolvedValue({ candidate: { id: 'c1' } })
  confirm.confirmDangerous.mockResolvedValue(undefined)
  confirm.confirmDelete.mockResolvedValue(undefined)
  api.deleteTemplate.mockResolvedValue({ deleted: true })
})

function mountSave(props: Record<string, unknown> = {}) {
  return mount(FormulaTemplateSaveDialog, {
    props: { modelValue: false, projectId: 'p1', defaultDomain: 'report', defaultScope: 'soe_standalone', ...props },
    global: { plugins: [ElementPlus], stubs: { ElDialog: DialogStub } },
  })
}

describe('FormulaTemplateSaveDialog', () => {
  it('从本项目保存（默认）：只取本项目自己的公式，不传公式位；个人模板不带所属项目', async () => {
    const w = mountSave()
    await w.setProps({ modelValue: true })
    await flushPromises()
    const vm = w.vm as any
    vm.form.name = '本所口径'
    await vm.onSave()
    expect(api.createTemplate).toHaveBeenCalledWith({
      name: '本所口径', description: null, share_scope: 'personal', owner_project_id: null,
      applicable_scope: 'soe_standalone', source: 'project', source_project_id: 'p1', domains: ['report'], slot_keys: undefined,
    })
    expect(w.emitted('saved')).toHaveLength(1)
    w.unmount()
  })

  it('「全部有效公式」：显式列出公式位（跳过停用的）；项目组模板归属当前项目', async () => {
    const w = mountSave()
    await w.setProps({ modelValue: true })
    await flushPromises()
    const vm = w.vm as any
    Object.assign(vm.form, { name: '全量', slotMode: 'all', share_scope: 'team' })
    await vm.onSave()
    expect(api.effective).toHaveBeenCalledWith('p1', 'report')
    expect(api.createTemplate.mock.calls[0][0]).toMatchObject({
      share_scope: 'team', owner_project_id: 'p1', slot_keys: { report: ['balance_sheet:BS-002'] },
    })
    w.unmount()
  })

  it('非管理员看不到「事务所」；没有项目上下文时也没有「项目组 / 集团」', async () => {
    const w = mountSave({ projectId: '' })
    await w.setProps({ modelValue: true })
    await flushPromises()
    const values = (w.vm as any).shareOptions.map((o: any) => o.value)
    expect(values).toEqual(['personal'])
    expect((w.vm as any).form.source).toBe('global')
    w.unmount()
  })

  it('从全局保存须选适用范围：校验规则对「全局 + 空范围」报错，其余放行', async () => {
    // 🔴 直接验规则函数：本仓库 vitest 下 element-plus 被外部化加载，其 `import AsyncValidator` 走
    //    Node 的 ESM↔CJS 互操作拿到的不是构造器，el-form 的 validate() 会恒为通过（表单项以 undefined 拒绝，
    //    el-form 当成「没有错误」）—— 经 onSave 断言「不发请求」在这里是假绿。
    const w = mountSave({ projectId: '', defaultScope: '' })
    await w.setProps({ modelValue: true })
    await flushPromises()
    const vm = w.vm as any
    const rule = vm.rules.applicable_scope[0]
    const run = (value: string) => new Promise((resolve) => rule.validator({}, value, (e?: Error) => resolve(e?.message || 'ok')))
    expect(vm.form.source).toBe('global')
    expect(await run('')).toBe('从全局设置保存须选择适用范围')
    expect(await run('soe_standalone')).toBe('ok')
    vm.form.source = 'project'
    expect(await run('')).toBe('ok')
    w.unmount()
  })

  it('保存失败：提示后端原因', async () => {
    api.createTemplate.mockRejectedValueOnce({ response: { status: 400, data: { detail: { message: '没有可放进模板的公式' } } } })
    const w = mountSave()
    await w.setProps({ modelValue: true })
    await flushPromises()
    const vm = w.vm as any
    vm.form.name = 'x'
    await vm.onSave()
    expect(msg.error).toHaveBeenCalledWith('保存模板失败：没有可放进模板的公式')
    w.unmount()
  })
})

const casDrawers: Array<{ unmount: () => void }> = []
afterEach(() => { for (const w of casDrawers.splice(0)) w.unmount() })
function mountDrawer(isAdmin = false) {
  const w = mount(FormulaTemplateDetailDrawer, {
    props: { modelValue: true, templateId: 't1', domains: DOMAINS as any, isAdmin },
    global: { plugins: [ElementPlus], stubs: { ElDrawer: DrawerStub, ElDialog: DialogStub, FormulaPublishPreviewDialog: PreviewStub } },
  })
  casDrawers.push(w)
  return w
}

describe('FormulaTemplateDetailDrawer', () => {
  it('同步全局：暂存当前全局定义 → 发布新版本带模板版本号与同一请求号', async () => {
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    vm.syncHint(vm.hints[0])
    expect(vm.stagedCount).toBe(1)
    await vm.onPublishPreview()
    expect(api.templatePublishPreview).toHaveBeenCalledWith('t1', {
      expected_version: 3, changes: [{ domain: 'report', slot_key: 'balance_sheet:BS-002', definition: { formula: 'G' } }],
    })
    api.templatePublish.mockRejectedValueOnce({ response: { status: 500 } })
    const decisions = { project_choices: {}, conflict_choices: {}, default_conflict: 'ask' }
    expect(await vm.onSubmitPreview({ decisions, note: '' })).toBe(false)
    expect(await vm.onSubmitPreview({ decisions, note: '并入全局' })).toBe(true)
    const [first, second] = api.templatePublish.mock.calls.map((c) => c[1])
    expect(second).toMatchObject({ expected_version: 3, decisions, note: '并入全局' })
    expect(second.request_id).toBe(first.request_id)
    expect(vm.stagedCount).toBe(0)
    expect(w.emitted('changed')).toHaveLength(1)
    w.unmount()
  })

  // spec formula-management-repair-closure R6：按分类处理
  it('四类提示：一键同步只暂存「模板没改过」的；已一致的走保留模板；全局已删的不能同步、可移出', async () => {
    api.template.mockResolvedValue({ ...JSON.parse(JSON.stringify(DETAIL)), global_hints: HINTS })
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    expect(vm.hintSummary).toBe('模板未改，可直接同步 1 处、模板已与新全局一致 1 处、模板与新全局都改了 1 处、全局已删除该公式位 1 处')
    expect(w.find('[data-testid="ftd-sync-follow"]').text()).toContain('同步未改动的 1 处')
    expect(w.find('[data-testid="ftd-keep-same"]').text()).toContain('更新已一致的 1 处基线')
    vm.syncFollowHints()
    expect(vm.stagedChanges()).toEqual([{ domain: 'report', slot_key: 'balance_sheet:BS-001', definition: { formula: 'G1' } }])
    vm.syncHint(HINTS[3])
    expect(vm.stagedCount).toBe(1)
    vm.removeHint(HINTS[3])
    expect(vm.stagedChanges()).toContainEqual({ domain: 'report', slot_key: 'balance_sheet:BS-004', definition: null })
    w.unmount()
  })

  it('保留模板：带模板版本 + 各处看到的全局版本，不发新版本；成功后重取、去掉同一处的暂存', async () => {
    api.template.mockResolvedValue({ ...JSON.parse(JSON.stringify(DETAIL)), global_hints: HINTS })
    api.templateKeepBaseline.mockResolvedValue({ template_id: 't1', version: 3, kept: [] })
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    vm.syncHint(HINTS[2])
    const loads = api.template.mock.calls.length
    await vm.keepHints([HINTS[1], HINTS[2], HINTS[3]])
    expect(api.templateKeepBaseline).toHaveBeenCalledWith('t1', { expected_version: 3, items: [
      { domain: 'report', slot_key: 'balance_sheet:BS-002', expected_global_version: 2 },
      { domain: 'report', slot_key: 'balance_sheet:BS-003', expected_global_version: 2 },
      { domain: 'report', slot_key: 'balance_sheet:BS-004', expected_global_version: null }] })
    expect(api.templatePublish).not.toHaveBeenCalled()
    expect(vm.stagedCount).toBe(0)
    expect(api.template.mock.calls.length).toBe(loads + 1)
    expect(msg.success).toHaveBeenCalledWith('已保留模板定义，3 处提示已消除（未发新版本，订阅项目不受影响）')
    expect(w.emitted('changed')).toHaveLength(1)
    w.unmount()
  })

  it('保留模板时模板或全局又变了（409）：提示按最新情况重新确认并重取，不当成功', async () => {
    api.template.mockResolvedValue({ ...JSON.parse(JSON.stringify(DETAIL)), global_hints: HINTS })
    api.templateKeepBaseline.mockRejectedValueOnce({ response: { status: 409, data: { detail: {
      error_code: 'FORMULA_VERSION_CONFLICT', message: '「乙」的全局定义已再次变化，请刷新后重新确认' } } } })
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    const loads = api.template.mock.calls.length
    await vm.keepHints([HINTS[1]])
    expect(msg.warning).toHaveBeenCalledWith(expect.stringContaining('全局定义已再次变化'))
    expect(msg.success).not.toHaveBeenCalled()
    expect(api.template.mock.calls.length).toBe(loads + 1)
    expect(vm.keeping).toBe(false)
    w.unmount()
  })

  it('非管理员「设为全局」：确认后直接提交候选，不走预览', async () => {
    const w = mountDrawer(false)
    await flushPromises()
    await (w.vm as any).onPromote('report')
    expect(confirm.confirmDangerous).toHaveBeenCalled()
    expect(api.templatePromotePreview).not.toHaveBeenCalled()
    expect(api.templatePromote).toHaveBeenCalledWith('t1', expect.objectContaining({ domain: 'report' }))
    expect(msg.success).toHaveBeenCalledWith('已提交为全局候选，管理员审核通过后发布')
    w.unmount()
  })

  it('管理员「设为全局」：先预览影响', async () => {
    api.templatePromotePreview.mockResolvedValue({ items: [], summary: {} })
    const w = mountDrawer(true)
    await flushPromises()
    await (w.vm as any).onPromote('report')
    expect(api.templatePromotePreview).toHaveBeenCalledWith('t1', { domain: 'report' })
    expect(api.templatePromote).not.toHaveBeenCalled()
    w.unmount()
  })

  it('删除：先确认；取消则不删', async () => {
    const w = mountDrawer()
    await flushPromises()
    confirm.confirmDelete.mockRejectedValueOnce('cancel')
    await (w.vm as any).onDelete()
    expect(api.deleteTemplate).not.toHaveBeenCalled()
    await (w.vm as any).onDelete()
    expect(api.deleteTemplate).toHaveBeenCalledWith('t1', 3)
    w.unmount()
  })

  it('删除：版本冲突（409）提示并重取详情，不关抽屉（spec formula-hub-integrity-closure ADR-FHIC-11）', async () => {
    const w = mountDrawer()
    await flushPromises()
    const before = api.template.mock.calls.length
    api.deleteTemplate.mockRejectedValueOnce({ response: { status: 409, data: { detail: { message: '模板已被他人修改' } } } })
    await (w.vm as any).onDelete()
    await flushPromises()
    expect(api.template.mock.calls.length).toBe(before + 1)
    expect(w.emitted('changed')).toBeUndefined()
    w.unmount()
  })
})

// API 下一层 mock：Drawer、CAS helper 与 Vue watchers 均使用真实生产实现；不是 HTTP/PG 证据。
function deferred<T = any>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}
function previewEvidence(extra: Record<string, unknown> = {}) {
  return { template_id: 't1', version: 3, preview_fingerprint: 'a'.repeat(64),
    changes: [], summary: { projects: [], counts: {} }, items: [], ...extra }
}
function decisionsPayload() {
  return { decisions: { project_choices: { p1: 'defer' as const },
    conflict_choices: { 'report|p1|balance_sheet:BS-002': 'keep' as const }, default_conflict: 'ask' as const }, note: '合成测试说明' }
}
function previewSubmit(w: ReturnType<typeof mountDrawer>) {
  return w.getComponent(PreviewStub).props('submit') as (payload: ReturnType<typeof decisionsPayload>) => Promise<boolean>
}
async function preparedDrawer() {
  const w = mountDrawer()
  await flushPromises()
  const vm = w.vm as any
  vm.syncHint(vm.hints[0])
  await vm.onPublishPreview()
  await nextTick()
  expect(vm.previewVisible).toBe(true)
  expect(w.getComponent(PreviewStub).props('modelValue')).toBe(true)
  return { w, vm, submit: previewSubmit(w) }
}
function secondTemplate() {
  return { ...copyTemplateValue(DETAIL), id: 't2', name: '第二模板', version: 8 }
}

describe('模板 CAS helper 的真实证据校验与载荷透传', () => {
  it('有效 publish/rollback fingerprint 和完整提交体逐字段透传', async () => {
    const changes = [{ domain: 'report', slot_key: 's1', definition: { formula: '10' } }]
    const preview = await formulaTemplateCasApi.publishPreview('t1', { expected_version: 3, changes })
    const rollback = await formulaTemplateCasApi.rollbackPreview('t1', { expected_version: 3, target_version: 1 })
    const body = { expected_version: 3, changes, preview_fingerprint: preview.preview_fingerprint,
      ...decisionsPayload(), request_id: 'synthetic-request' }
    await formulaTemplateCasApi.publish('t1', body)
    expect(api.templatePublish).toHaveBeenCalledWith('t1', body)
    const { changes: _changes, ...common } = body
    const rollbackBody = { ...common, target_version: 1, preview_fingerprint: rollback.preview_fingerprint }
    await formulaTemplateCasApi.rollback('t1', rollbackBody)
    expect(api.templateRollback).toHaveBeenCalledWith('t1', rollbackBody)
    expect(api.templatePublishPreview).toHaveBeenCalledWith('t1', { expected_version: 3, changes })
    expect(api.templateRollbackPreview).toHaveBeenCalledWith('t1', { expected_version: 3, target_version: 1 })
  })

  it.each([
    ['无返回值', undefined], ['无指纹', previewEvidence({ preview_fingerprint: undefined })],
    ['短指纹', previewEvidence({ preview_fingerprint: 'abc' })],
    ['大写指纹', previewEvidence({ preview_fingerprint: 'A'.repeat(64) })],
    ['非十六进制', previewEvidence({ preview_fingerprint: 'g'.repeat(64) })],
    ['错误模板', previewEvidence({ template_id: 't2' })], ['错误版本', previewEvidence({ version: 4 })],
    ['字符串版本', previewEvidence({ version: '3' })],
  ])('%s：拒绝无效 publish 证据而非建立会话', async (_name, value) => {
    api.templatePublishPreview.mockResolvedValueOnce(value)
    const pending = formulaTemplateCasApi.publishPreview('t1', { expected_version: 3, changes: [] })
    await expect(pending).rejects.toBeInstanceOf(TemplatePreviewEvidenceError)
    await expect(pending).rejects.toThrow('模板预览缺少有效的版本证据')
    expect(api.templatePublish).not.toHaveBeenCalled()
  })

  it.each([
    ['版本证据', previewEvidence({ version: 4, target_version: 1 })],
    ['回滚目标', previewEvidence({ target_version: 2 })],
  ])('rollback %s 错误有专用类型且不触达写接口', async (reason, value) => {
    api.templateRollbackPreview.mockResolvedValueOnce(value)
    const pending = formulaTemplateCasApi.rollbackPreview('t1', { expected_version: 3, target_version: 1 })
    await expect(pending).rejects.toBeInstanceOf(TemplatePreviewEvidenceError)
    await expect(pending).rejects.toThrow(reason)
    expect(api.templateRollback).not.toHaveBeenCalled()
  })

  it('深复制嵌套 JSON，副本修改不改原定义和数组', () => {
    const original = { definitions: [{ formula: '10', metadata: { flags: ['a'] } }], removed: null }
    const copied = copyTemplateValue(original)
    expect(copied).toEqual(original)
    copied.definitions[0].metadata.flags.push('b')
    copied.definitions[0].formula = '20'
    expect(original).toEqual({ definitions: [{ formula: '10', metadata: { flags: ['a'] } }], removed: null })
  })
})

describe('真实 Drawer 的模板 preview → publish/rollback', () => {
  it('从真实发布按钮经 submit prop 发布，冻结指纹和版本且复制 decisions', async () => {
    const evidence = previewEvidence()
    api.templatePublishPreview.mockResolvedValueOnce(evidence)
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    vm.syncHint(vm.hints[0])
    await nextTick()
    await w.get('[data-testid="ftd-publish"]').trigger('click')
    await flushPromises()
    evidence.preview_fingerprint = 'f'.repeat(64)
    const payload = decisionsPayload()
    const gate = deferred()
    api.templatePublish.mockReturnValueOnce(gate.promise)
    const pending = previewSubmit(w)(payload)
    payload.decisions.project_choices.p1 = 'apply' as any
    payload.decisions.conflict_choices['report|p1|balance_sheet:BS-002'] = 'adopt' as any
    expect(api.templatePublish).toHaveBeenCalledWith('t1', expect.objectContaining({
      expected_version: 3, preview_fingerprint: 'a'.repeat(64), request_id: expect.any(String),
      decisions: decisionsPayload().decisions, changes: [
        { domain: 'report', slot_key: 'balance_sheet:BS-002', definition: { formula: 'G' } },
      ], note: '合成测试说明',
    }))
    api.template.mockResolvedValueOnce({ ...copyTemplateValue(DETAIL), version: 4 })
    gate.resolve({ version: 4 })
    expect(await pending).toBe(true)
    expect(vm.detail.version).toBe(4)
    expect(vm.previewVisible).toBe(false)
    expect(vm.previewSession).toBeNull()
    expect(vm.stagedCount).toBe(0)
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it.each(['publish', 'rollback'] as const)('%s 预览无效时旧会话也作废，不能提交', async (kind) => {
    const { w, vm, submit } = await preparedDrawer()
    if (kind === 'publish') api.templatePublishPreview.mockResolvedValueOnce(previewEvidence({ version: 4 }))
    else api.templateRollbackPreview.mockResolvedValueOnce(previewEvidence({ target_version: 2 }))
    await (kind === 'publish' ? vm.onPublishPreview() : vm.openRollback({ version: 1 }))
    expect(vm.previewVisible).toBe(false)
    expect(vm.previewSession).toBeNull()
    expect(await submit(decisionsPayload())).toBe(false)
    expect(api.templatePublish).not.toHaveBeenCalled()
    expect(api.templateRollback).not.toHaveBeenCalled()
    expect(msg.error).toHaveBeenCalledWith(expect.stringMatching(/版本证据|回滚目标/))
    expect(w.emitted('changed')).toBeUndefined()
  })
})

describe('真实 Drawer 的预览错误分类', () => {
  it.each([
    ['publish', '网络', { message: 'synthetic-offline' }, '发布预览失败：网络不通，请检查连接'],
    ['rollback', '网络', { message: 'synthetic-offline' }, '回滚预览失败：网络不通，请检查连接'],
    ['publish', '服务端', { response: { status: 400, data: { detail: { message: '合成发布预览拒绝' } } } },
      '发布预览失败：合成发布预览拒绝'],
    ['rollback', '服务端', { response: { status: 400, data: { detail: { message: '合成回滚预览拒绝' } } } },
      '回滚预览失败：合成回滚预览拒绝'],
  ] as const)('%s 的%s错误不误归为本地证据异常', async (kind, _source, error, message) => {
    const { w, vm, submit } = await preparedDrawer()
    const read = kind === 'publish' ? api.templatePublishPreview : api.templateRollbackPreview
    read.mockRejectedValueOnce(error)
    await (kind === 'publish' ? vm.onPublishPreview() : vm.openRollback({ version: 1 }))
    expect(msg.error).toHaveBeenCalledWith(message)
    expect(vm.previewVisible).toBe(false)
    expect(vm.previewSession).toBeNull()
    expect(await submit(decisionsPayload())).toBe(false)
    expect(api.templatePublish).not.toHaveBeenCalled()
    expect(api.templateRollback).not.toHaveBeenCalled()
    expect(w.emitted('changed')).toBeUndefined()
  })
})

describe('真实 Drawer 的编辑上下文与暂存快照', () => {
  it('编辑开始时冻结 domain，保存定义和预览请求都深复制', async () => {
    api.template.mockResolvedValueOnce({ ...copyTemplateValue(DETAIL), domains: ['report', 'note'] })
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    const row = vm.domainRows[0]
    vm.openEdit(row)
    row.definition.formula = 'SOURCE-LATER'
    expect(vm.editing.definition.formula).toBe('A')
    const input = { formula: '10', metadata: { fields: ['x'] } }
    vm.activeDomain = 'note'
    vm.onEditSave(input)
    input.formula = '20'
    input.metadata.fields.push('y')
    expect(vm.staged.has('note|balance_sheet:BS-002')).toBe(false)
    expect(vm.stagedChanges()).toEqual([{ domain: 'report', slot_key: 'balance_sheet:BS-002',
      definition: { formula: '10', metadata: { fields: ['x'] } } }])
    await vm.onPublishPreview()
    const sent = api.templatePublishPreview.mock.calls[0][1]
    const detached = vm.stagedChanges()
    detached[0].definition.formula = 'DETACHED'
    expect(vm.stagedChanges()[0].definition.formula).toBe('10')
    vm.staged.get('report|balance_sheet:BS-002').definition.metadata.fields.push('z')
    expect(sent.changes[0].definition).toEqual({ formula: '10', metadata: { fields: ['x'] } })
    expect(vm.previewVisible).toBe(false)
  })

  it('同步全局定义不持有 hint 原引用，后续预览使用原暂存副本', async () => {
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    vm.hints[0].global_definition.metadata = { flags: ['a'] }
    vm.syncHint(vm.hints[0])
    vm.hints[0].global_definition.formula = 'CHANGED'
    vm.hints[0].global_definition.metadata.flags.push('b')
    await vm.onPublishPreview()
    expect(api.templatePublishPreview.mock.calls[0][1].changes[0].definition)
      .toEqual({ formula: 'G', metadata: { flags: ['a'] } })
  })
})

describe('真实 Drawer 的预览失效边界', () => {
  it.each(['暂存嵌套变化', '放弃暂存', '移除公式', '取消预览', '关闭抽屉', '切换模板'])(
    '%s 使旧 preview 会话不可提交', async (action) => {
      const { w, vm, submit } = await preparedDrawer()
      const previousRequest = vm.previewSession.requestId
      if (action === '暂存嵌套变化') vm.staged.get('report|balance_sheet:BS-002').definition.formula = '30'
      if (action === '放弃暂存') vm.clearStaged()
      if (action === '移除公式') vm.stageDelete(vm.domainRows[0])
      if (action === '取消预览') w.getComponent(PreviewStub).vm.$emit('update:modelValue', false)
      if (action === '关闭抽屉') await w.setProps({ modelValue: false })
      if (action === '切换模板') {
        api.template.mockResolvedValueOnce(secondTemplate())
        await w.setProps({ templateId: 't2' })
      }
      await flushPromises()
      expect(vm.previewVisible).toBe(false)
      expect(vm.previewSession).toBeNull()
      expect(await submit(decisionsPayload())).toBe(false)
      expect(api.templatePublish).not.toHaveBeenCalled()
      expect(api.templateRollback).not.toHaveBeenCalled()
      if (action === '取消预览') {
        await vm.onPublishPreview()
        expect(vm.previewSession.requestId).not.toBe(previousRequest)
      }
    },
  )

  it.each(['version', 'applicable_scope'])('详情 %s 改变后拒绝旧会话', async (key) => {
    const { vm, submit } = await preparedDrawer()
    vm.detail[key] = key === 'version' ? 4 : 'listed_standalone'
    expect(await submit(decisionsPayload())).toBe(false)
    expect(vm.previewSession).toBeNull()
    expect(api.templatePublish).not.toHaveBeenCalled()
    expect(msg.warning).toHaveBeenCalledWith(expect.stringContaining('重新预览'))
  })
})

describe('真实 Drawer 的迟到 load/preview 结果隔离', () => {
  it.each(['详情', '历史与订阅'])('旧模板的%s晚到不覆盖新模板', async (stage) => {
    const late = deferred()
    if (stage === '详情') api.template.mockReturnValueOnce(late.promise)
    else api.templateVersions.mockReturnValueOnce(late.promise)
    const w = mountDrawer()
    await flushPromises()
    api.template.mockResolvedValueOnce(secondTemplate())
    api.templateVersions.mockResolvedValueOnce({ items: [{ version: 8, note: '第二模板历史' }] })
    api.templateSubscribers.mockResolvedValueOnce({ items: [{ project_id: 'p2', project_name: '第二订阅' }] })
    await w.setProps({ templateId: 't2' })
    await flushPromises()
    late.resolve(stage === '详情' ? copyTemplateValue(DETAIL) : { items: [{ version: 1, note: '旧历史' }] })
    await flushPromises()
    const vm = w.vm as any
    expect(vm.detail.id).toBe('t2')
    expect(vm.detail.version).toBe(8)
    expect(vm.versions).toEqual([{ version: 8, note: '第二模板历史' }])
    expect(vm.subscribers).toEqual([{ project_id: 'p2', project_name: '第二订阅' }])
    expect(vm.loading).toBe(false)
    expect(api.templateVersions.mock.calls.every(([id]) => id === 't1' || id === 't2')).toBe(true)
  })

  it.each(['publish', 'rollback'] as const)('%s 预览晚到不替换新模板的已打开预览', async (kind) => {
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    vm.syncHint(vm.hints[0])
    const late = deferred()
    if (kind === 'publish') api.templatePublishPreview.mockReturnValueOnce(late.promise)
    else api.templateRollbackPreview.mockReturnValueOnce(late.promise)
    const pending = kind === 'publish' ? vm.onPublishPreview() : vm.openRollback({ version: 1 })
    api.template.mockResolvedValueOnce(secondTemplate())
    await w.setProps({ templateId: 't2' })
    await flushPromises()
    vm.syncHint(vm.hints[0])
    api.templatePublishPreview.mockResolvedValueOnce(previewEvidence({ template_id: 't2', version: 8 }))
    await vm.onPublishPreview()
    const request = vm.previewSession.requestId
    late.resolve(previewEvidence({ target_version: 1 }))
    await pending
    expect(vm.previewSession).toMatchObject({ templateId: 't2', version: 8, requestId: request, kind: 'publish' })
    expect(vm.preview.template_id).toBe('t2')
    expect(vm.previewVisible).toBe(true)
    expect(msg.error).not.toHaveBeenCalled()
  })
})

describe('真实 Drawer 的预览请求序号', () => {
  it('同模板先发预览晚到，仍保留后发预览的 fingerprint/requestId', async () => {
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    vm.syncHint(vm.hints[0])
    const late = deferred()
    api.templatePublishPreview.mockReturnValueOnce(late.promise)
    const first = vm.onPublishPreview()
    api.templatePublishPreview.mockResolvedValueOnce(previewEvidence({ preview_fingerprint: 'c'.repeat(64) }))
    await vm.onPublishPreview()
    const request = vm.previewSession.requestId
    late.resolve(previewEvidence())
    await first
    expect(vm.previewSession).toMatchObject({ fingerprint: 'c'.repeat(64), requestId: request })
    await previewSubmit(w)(decisionsPayload())
    expect(api.templatePublish.mock.calls[0][1].preview_fingerprint).toBe('c'.repeat(64))
  })

  it.each(['暂存变化', '关闭抽屉'])('%s 后晚到的 preview 不重新开窗', async (action) => {
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    vm.syncHint(vm.hints[0])
    const late = deferred()
    api.templatePublishPreview.mockReturnValueOnce(late.promise)
    const pending = vm.onPublishPreview()
    if (action === '暂存变化') vm.staged.get('report|balance_sheet:BS-002').definition.formula = '40'
    else await w.setProps({ modelValue: false })
    late.resolve(previewEvidence())
    await pending
    expect(vm.previewSession).toBeNull()
    expect(vm.previewVisible).toBe(false)
    expect(vm.previewLoading).toBe(false)
    expect(await previewSubmit(w)(decisionsPayload())).toBe(false)
    expect(api.templatePublish).not.toHaveBeenCalled()
  })
})

describe('真实 Drawer 的回滚快照与可重试错误', () => {
  it('rollback 冻结 target/version/fingerprint，不携带 publish changes，成功保留暂存', async () => {
    const { w, vm } = await preparedDrawer()
    const row = { version: 1 }
    await vm.openRollback(row)
    row.version = 2
    vm.preview.target_version = 2
    vm.preview.preview_fingerprint = 'd'.repeat(64)
    await nextTick()
    expect(await previewSubmit(w)(decisionsPayload())).toBe(true)
    expect(api.templateRollback).toHaveBeenCalledWith('t1', expect.objectContaining({
      target_version: 1, expected_version: 3, preview_fingerprint: 'b'.repeat(64),
      request_id: expect.any(String), decisions: decisionsPayload().decisions,
    }))
    expect(api.templateRollback.mock.calls[0][1]).not.toHaveProperty('changes')
    expect(api.templatePublish).not.toHaveBeenCalled()
    expect(vm.stagedCount).toBe(1)
    expect(vm.previewVisible).toBe(false)
    expect(w.emitted('changed')).toHaveLength(1)
  })

  it.each(['publish', 'rollback'] as const)('%s 的 500 保留同 requestId/版本/指纹重试', async (kind) => {
    const { w, vm } = await preparedDrawer()
    if (kind === 'rollback') await vm.openRollback({ version: 1 })
    await nextTick()
    const write = kind === 'publish' ? api.templatePublish : api.templateRollback
    const loads = api.template.mock.calls.length
    write.mockRejectedValueOnce({ response: { status: 500 } })
    const submit = previewSubmit(w)
    expect(await submit(decisionsPayload())).toBe(false)
    expect(vm.previewVisible).toBe(true)
    expect(vm.submitting).toBe(false)
    expect(w.emitted('changed')).toBeUndefined()
    expect(api.template).toHaveBeenCalledTimes(loads)
    expect(await submit({ ...decisionsPayload(), note: '再次提交' })).toBe(true)
    const [first, retry] = write.mock.calls.map((call) => call[1])
    expect(retry).toEqual({ ...first, note: '再次提交' })
    expect(retry.request_id).toBeTruthy()
    expect(retry.preview_fingerprint).toBe((kind === 'publish' ? 'a' : 'b').repeat(64))
    expect(write).toHaveBeenCalledTimes(2)
    expect(w.emitted('changed')).toHaveLength(1)
  })
})

describe('真实 Drawer 的 CAS 拒绝后重读', () => {
  it.each([
    ['publish', 409], ['publish', 428], ['rollback', 409], ['rollback', 428],
  ] as const)('%s 返回 %s 作废会话并重读，重新预览才可再写', async (kind, status) => {
    const { w, vm } = await preparedDrawer()
    if (kind === 'rollback') await vm.openRollback({ version: 1 })
    const oldRequest = vm.previewSession.requestId
    const write = kind === 'publish' ? api.templatePublish : api.templateRollback
    write.mockRejectedValueOnce({ response: { status, data: { detail: { message: '版本证据失效' } } } })
    api.template.mockResolvedValueOnce({ ...copyTemplateValue(DETAIL), version: 4 })
    const loads = api.template.mock.calls.length
    const submit = previewSubmit(w)
    expect(await submit(decisionsPayload())).toBe(false)
    expect(api.template).toHaveBeenCalledTimes(loads + 1)
    expect(vm.detail.version).toBe(4)
    expect(vm.previewVisible).toBe(false)
    expect(vm.previewSession).toBeNull()
    expect(vm.stagedCount).toBe(1)
    expect(w.emitted('changed')).toBeUndefined()
    expect(msg.success).not.toHaveBeenCalled()
    expect(msg.warning).toHaveBeenCalledWith(expect.stringContaining('版本证据失效'))
    expect(await submit(decisionsPayload())).toBe(false)
    expect(write).toHaveBeenCalledTimes(1)
    const evidence = previewEvidence({ version: 4, target_version: 1, preview_fingerprint: 'e'.repeat(64) })
    if (kind === 'publish') api.templatePublishPreview.mockResolvedValueOnce(evidence)
    else api.templateRollbackPreview.mockResolvedValueOnce(evidence)
    await (kind === 'publish' ? vm.onPublishPreview() : vm.openRollback({ version: 1 }))
    expect(vm.previewSession.requestId).not.toBe(oldRequest)
    expect(await submit(decisionsPayload())).toBe(true)
    expect(write.mock.calls[1][1]).toMatchObject({ expected_version: 4, preview_fingerprint: 'e'.repeat(64) })
  })
})

describe('真实 Drawer 的迟到 submit 与提交互斥', () => {
  it.each([
    ['publish', '成功'], ['publish', '409'], ['rollback', '成功'], ['rollback', '500'],
  ] as const)('%s 提交%s晚到不改新模板、不发 changed 或重读', async (kind, outcome) => {
    const { w, vm } = await preparedDrawer()
    if (kind === 'rollback') await vm.openRollback({ version: 1 })
    const late = deferred()
    const write = kind === 'publish' ? api.templatePublish : api.templateRollback
    write.mockReturnValueOnce(late.promise)
    const pending = previewSubmit(w)(decisionsPayload())
    api.template.mockResolvedValueOnce(secondTemplate())
    await w.setProps({ templateId: 't2' })
    await flushPromises()
    const loads = api.template.mock.calls.length
    if (outcome === '成功') late.resolve({ version: 4 })
    else late.reject({ response: { status: Number(outcome) } })
    expect(await pending).toBe(false)
    expect(vm.detail.id).toBe('t2')
    expect(vm.detail.version).toBe(8)
    expect(vm.previewVisible).toBe(false)
    expect(vm.stagedCount).toBe(0)
    expect(vm.submitting).toBe(false)
    expect(api.template).toHaveBeenCalledTimes(loads)
    expect(w.emitted('changed')).toBeUndefined()
    expect(msg.success).not.toHaveBeenCalled()
    expect(msg.error).not.toHaveBeenCalled()
    expect(msg.warning).not.toHaveBeenCalled()
  })

  it.each(['publish', 'rollback'] as const)('%s 在途时拒绝第二次提交与所有暂存写操作', async (kind) => {
    const { w, vm } = await preparedDrawer()
    if (kind === 'rollback') await vm.openRollback({ version: 1 })
    const write = kind === 'publish' ? api.templatePublish : api.templateRollback
    const late = deferred()
    write.mockReturnValueOnce(late.promise)
    const before = vm.stagedChanges()
    const submit = previewSubmit(w)
    const pending = submit(decisionsPayload())
    expect(vm.submitting).toBe(true)
    expect(await submit(decisionsPayload())).toBe(false)
    vm.clearStaged(); vm.stageDelete(vm.domainRows[0]); vm.removeHint(vm.hints[0]); vm.syncHint(vm.hints[0])
    vm.onEditSave({ formula: 'MUST-NOT-WRITE' })
    await vm.openRollback({ version: 1 })
    await vm.onPublishPreview()
    expect(vm.stagedChanges()).toEqual(before)
    expect(write).toHaveBeenCalledTimes(1)
    late.resolve({ version: 4 })
    expect(await pending).toBe(true)
  })
})