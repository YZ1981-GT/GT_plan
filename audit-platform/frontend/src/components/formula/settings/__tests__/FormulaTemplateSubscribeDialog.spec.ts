/**
 * FormulaTemplateSubscribeDialog —— 订阅 / 退订公式模板（spec formula-global-settings-sync，R13.3 / R13.5 / R13.10）
 *
 * 守护：未订阅时列出可见模板，订阅先预览再带冲突决策提交（只采用模板 / 保留本项目两种）；
 * 已订阅时显示版本与落后提示，退订可选「保留为本项目适配」或「回到全局」，都先预览；
 * 成功后发出 changed 并刷新。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'

const { api, msg } = vi.hoisted(() => ({
  api: {
    domains: vi.fn(), subscriptions: vi.fn(), templates: vi.fn(),
    subscribePreview: vi.fn(), subscribe: vi.fn(), unsubscribePreview: vi.fn(), unsubscribe: vi.fn(),
  },
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: api }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg }
})

import FormulaTemplateSubscribeDialog from '../FormulaTemplateSubscribeDialog.vue'

const DialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue" class="dlg"><slot /><slot name="footer" /></div>',
})
const PreviewStub = defineComponent({
  name: 'FormulaPublishPreviewDialog',
  props: ['modelValue', 'preview', 'submit', 'conflictOptions', 'defaultConflict', 'allowDefer', 'hint'],
  template: '<div class="preview-stub" />',
})
const TPL = {
  id: 't1', name: '本所国企口径', description: null, share_scope: 'firm', share_scope_label: '事务所',
  owner_user_id: null, owner_project_id: null, applicable_scope: 'soe_standalone', domains: ['report'],
  version: 3, status: 'active', can_manage: false, updated_at: null,
}
const DECISIONS = { project_choices: {}, conflict_choices: { 'p1|balance_sheet:BS-002': 'keep' }, default_conflict: 'adopt' }

function mountDialog() {
  return mount(FormulaTemplateSubscribeDialog, {
    props: { modelValue: true, projectId: 'p1', defaultDomain: 'report' },
    global: { plugins: [ElementPlus], stubs: { ElDialog: DialogStub, FormulaPublishPreviewDialog: PreviewStub } },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.domains.mockResolvedValue({ domains: [{ key: 'report', label: '报表公式', wired: true }], is_admin: false })
  api.subscriptions.mockResolvedValue({ items: [] })
  api.templates.mockResolvedValue({ items: [TPL], is_admin: false })
  api.subscribePreview.mockResolvedValue({ template_id: 't1', template_version: 3, domain: 'report', summary: {}, items: [] })
  api.subscribe.mockResolvedValue({ summary: {}, items: [] })
  api.unsubscribePreview.mockResolvedValue({ template_id: 't1', domain: 'report', mode: 'keep', kept: 4, summary: {}, items: [] })
  api.unsubscribe.mockResolvedValue({ summary: {}, items: [] })
})

describe('订阅', () => {
  it('列出该域可见模板；订阅先预览，冲突只给「采用模板 / 保留本项目」，默认采用', async () => {
    const w = mountDialog()
    await flushPromises()
    expect(api.templates).toHaveBeenCalledWith({ domain: 'report' })
    const vm = w.vm as any
    await vm.onSubscribePreview(TPL)
    expect(api.subscribePreview).toHaveBeenCalledWith('p1', { template_id: 't1', domain: 'report' })
    const preview = w.findComponent(PreviewStub)
    expect(preview.props('conflictOptions').map((o: any) => o.value)).toEqual(['adopt', 'keep'])
    expect(preview.props('defaultConflict')).toBe('adopt')
    expect(preview.props('allowDefer')).toBe(false)
    w.unmount()
  })

  it('确认订阅：带决策提交，成功发出 changed 并刷新订阅状态', async () => {
    const w = mountDialog()
    await flushPromises()
    const vm = w.vm as any
    await vm.onSubscribePreview(TPL)
    const before = api.subscriptions.mock.calls.length
    expect(await vm.onSubmit({ decisions: DECISIONS })).toBe(true)
    expect(api.subscribe).toHaveBeenCalledWith('p1', { template_id: 't1', domain: 'report', decisions: DECISIONS })
    expect(w.emitted('changed')?.[0]).toEqual(['report'])
    expect(api.subscriptions.mock.calls.length).toBe(before + 1)
    w.unmount()
  })

  it('订阅失败：不关预览（返回 false）并提示原因', async () => {
    api.subscribe.mockRejectedValueOnce({ response: { status: 409, data: { detail: { message: '本项目已订阅其他模板' } } } })
    const w = mountDialog()
    await flushPromises()
    const vm = w.vm as any
    await vm.onSubscribePreview(TPL)
    expect(await vm.onSubmit({ decisions: DECISIONS })).toBe(false)
    expect(msg.error).toHaveBeenCalledWith('本项目已订阅其他模板')
    w.unmount()
  })
})

describe('退订', () => {
  beforeEach(() => {
    api.subscriptions.mockResolvedValue({ items: [{
      domain: 'report', template_id: 't1', template_name: '本所国企口径', template_version: 2, current_version: 3,
      pinned: false, behind: true,
    }] })
  })

  it('已订阅：显示订阅版本与落后提示，不再列模板', async () => {
    const w = mountDialog()
    await flushPromises()
    expect(w.html()).toContain('本项目已订阅「本所国企口径」v2')
    expect(w.html()).toContain('模板已更新到 v3')
    expect((w.vm as any).current?.template_id).toBe('t1')
    w.unmount()
  })

  it('保留为本项目适配：预览给出保留条数，确认后按 keep 退订', async () => {
    const w = mountDialog()
    await flushPromises()
    const vm = w.vm as any
    await vm.onUnsubscribePreview()
    expect(api.unsubscribePreview).toHaveBeenCalledWith('p1', { domain: 'report', mode: 'keep' })
    expect(w.findComponent(PreviewStub).props('hint')).toContain('将保留 4 处模板公式')
    expect(await vm.onSubmit({ decisions: DECISIONS })).toBe(true)
    expect(api.unsubscribe).toHaveBeenCalledWith('p1', { domain: 'report', mode: 'keep', decisions: DECISIONS })
    w.unmount()
  })

  it('回到全局：按 global 预览与退订，冲突选项为「回到全局 / 保留本项目」', async () => {
    api.unsubscribePreview.mockResolvedValueOnce({ template_id: 't1', domain: 'report', mode: 'global', summary: {}, items: [] })
    const w = mountDialog()
    await flushPromises()
    const vm = w.vm as any
    vm.unsubscribeMode = 'global'
    await vm.onUnsubscribePreview()
    expect(api.unsubscribePreview).toHaveBeenCalledWith('p1', { domain: 'report', mode: 'global' })
    expect(w.findComponent(PreviewStub).props('conflictOptions').map((o: any) => o.label)).toEqual(['回到全局', '保留本项目'])
    await vm.onSubmit({ decisions: DECISIONS })
    expect(api.unsubscribe).toHaveBeenCalledWith('p1', { domain: 'report', mode: 'global', decisions: DECISIONS })
    w.unmount()
  })
})
