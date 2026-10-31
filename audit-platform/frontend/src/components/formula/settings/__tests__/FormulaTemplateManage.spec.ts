/**
 * 公式模板的保存与管理（spec formula-global-settings-sync，R13.1 / R13.2 / R13.4 / R13.6 / R13.7 / R13.9）
 *
 * FormulaTemplateSaveDialog：从本项目保存（默认只取本项目自己的公式，不传公式位；「全部有效公式」显式列出）、
 *   项目组 / 集团模板归属当前项目、事务所模板只给管理员、从全局保存须选适用范围。
 * FormulaTemplateDetailDrawer：并入全局提示 → 暂存 → 发布新版本（带模板版本号、同一请求号）；
 *   非管理员「设为全局」= 确认后提交候选（不预览）；删除先确认。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'

const { api, msg, confirm } = vi.hoisted(() => ({
  api: {
    domains: vi.fn(), effective: vi.fn(), createTemplate: vi.fn(), template: vi.fn(), templateVersions: vi.fn(),
    templateSubscribers: vi.fn(), templatePublishPreview: vi.fn(), templatePublish: vi.fn(),
    templatePromotePreview: vi.fn(), templatePromote: vi.fn(), deleteTemplate: vi.fn(), updateTemplate: vi.fn(),
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
    domain: 'report', slot_key: 'balance_sheet:BS-002', label: '货币资金', template_definition: { formula: 'A' },
    base_definition: { formula: 'A0' }, global_definition: { formula: 'G' }, global_version: 5, same_as_template: false,
  }],
}

beforeEach(() => {
  vi.clearAllMocks()
  api.domains.mockResolvedValue({ domains: DOMAINS, is_admin: false })
  api.effective.mockResolvedValue({ slots: [
    { slot_key: 'balance_sheet:BS-002', definition: { formula: 'A' }, disabled: false },
    { slot_key: 'balance_sheet:BS-003', definition: { formula: null }, disabled: true },
  ] })
  api.createTemplate.mockResolvedValue({ name: '本所口径', definitions: { report: [{}] } })
  api.template.mockResolvedValue(JSON.parse(JSON.stringify(DETAIL)))
  api.templateVersions.mockResolvedValue({ items: [] })
  api.templateSubscribers.mockResolvedValue({ items: [] })
  api.templatePublishPreview.mockResolvedValue({ template_id: 't1', version: 3, next_version: 4, changes: [], summary: {}, items: [] })
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

function mountDrawer(isAdmin = false) {
  return mount(FormulaTemplateDetailDrawer, {
    props: { modelValue: true, templateId: 't1', domains: DOMAINS as any, isAdmin },
    global: { plugins: [ElementPlus], stubs: { ElDrawer: DrawerStub, ElDialog: DialogStub, FormulaPublishPreviewDialog: PreviewStub } },
  })
}

describe('FormulaTemplateDetailDrawer', () => {
  it('并入全局：暂存当前全局定义 → 发布新版本带模板版本号与同一请求号', async () => {
    const w = mountDrawer()
    await flushPromises()
    const vm = w.vm as any
    vm.mergeAll()
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
