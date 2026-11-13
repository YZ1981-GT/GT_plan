/**
 * FormulaApplyScopeDialog —— 保存后选择应用范围（spec formula-global-settings-sync，R7 / R11.3）
 *
 * 守护：默认仅本项目（零请求）；非管理员看不到「设为全局」只能提交候选；应用到指定项目先拉可选项目、
 * 预览带目标项目；提交与预览同一请求号（重复提交不重复生效）；失败不关窗。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'

const { api, msg } = vi.hoisted(() => ({
  api: { applyTargets: vi.fn(), applyPreview: vi.fn(), apply: vi.fn(), domains: vi.fn() },
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: api }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg }
})

import FormulaApplyScopeDialog from '../FormulaApplyScopeDialog.vue'

const DialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue" class="dlg"><slot /><slot name="footer" /></div>',
})
const PreviewStub = defineComponent({
  name: 'FormulaPublishPreviewDialog',
  props: ['modelValue', 'preview', 'submit', 'allowDefer', 'readonlyDecisions', 'conflictOptions'],
  template: '<div class="preview-stub" />',
})

const DECISIONS = { project_choices: {}, conflict_choices: { 'p2|balance_sheet:BS-002': 'keep' }, default_conflict: 'ask' }

function open(props: Record<string, unknown> = {}) {
  return mount(FormulaApplyScopeDialog, {
    props: { modelValue: false, projectId: 'p1', domain: 'report', slotKeys: ['balance_sheet:BS-002'], ...props },
    global: { plugins: [ElementPlus], stubs: { ElDialog: DialogStub, FormulaPublishPreviewDialog: PreviewStub } },
  })
}

async function reopen(w: ReturnType<typeof open>) {
  await w.setProps({ modelValue: true })
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  api.applyTargets.mockResolvedValue({ items: [
    { project_id: 'p2', name: '乙公司', scope: 'soe_standalone', same_scope: true },
    { project_id: 'p3', name: '丙公司', scope: 'listed_standalone', same_scope: false },
  ] })
  api.applyPreview.mockResolvedValue({ domain: 'report', counts: { conflict: 1 }, conflict_count: 1, items: [] })
  api.apply.mockResolvedValue({ publish_id: 'x', changed_project_count: 1 })
  api.domains.mockResolvedValue({ domains: [
    { key: 'report', label: '报表公式', wired: true },
    { key: 'tb_detail', label: '试算表科目明细公式', wired: false, wired_reason: '试算表科目明细公式目前只保存、不参与计算：还没有任何计算读取这类公式' },
  ] })
})

describe('FormulaApplyScopeDialog', () => {
  it('默认仅本项目：完成即关窗，零请求', async () => {
    const w = open()
    await reopen(w)
    const vm = w.vm as any
    expect(vm.target).toBe('project')
    await vm.onPreview()
    expect(api.applyPreview).not.toHaveBeenCalled()
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([false])
    w.unmount()
  })

  it('非管理员：没有「设为全局」，只能提交为全局候选（只看影响不决策）', async () => {
    const w = open()
    await reopen(w)
    const html = w.html()
    expect(html).not.toContain('设为全局，并应用到全部项目')
    expect(html).toContain('提交为全局候选')
    const vm = w.vm as any
    vm.target = 'candidate'
    await vm.onPreview()
    expect(api.applyPreview).toHaveBeenCalledWith('p1', 'report', { target: 'candidate', slot_keys: ['balance_sheet:BS-002'], project_ids: [] })
    expect(w.findComponent(PreviewStub).props('readonlyDecisions')).toBe(true)
    w.unmount()
  })

  it('管理员：可设为全局（可逐项目暂缓）', async () => {
    const w = open({ canEditGlobal: true })
    await reopen(w)
    expect(w.html()).toContain('设为全局，并应用到全部项目')
    const vm = w.vm as any
    vm.target = 'global'
    await vm.onPreview()
    expect(w.findComponent(PreviewStub).props('allowDefer')).toBe(true)
    w.unmount()
  })

  it('应用到指定项目：先拉可选项目，预览与提交都带目标项目，且同一请求号', async () => {
    const w = open()
    await reopen(w)
    const vm = w.vm as any
    vm.target = 'projects'
    await flushPromises()
    expect(api.applyTargets).toHaveBeenCalledWith('p1', 'report')
    expect(vm.targets).toHaveLength(2)
    vm.projectIds = ['p2']
    await vm.onPreview()
    expect(api.applyPreview).toHaveBeenCalledWith('p1', 'report', { target: 'projects', slot_keys: ['balance_sheet:BS-002'], project_ids: ['p2'] })

    api.apply.mockRejectedValueOnce({ response: { status: 500 } })
    expect(await vm.onSubmit({ decisions: DECISIONS, note: '' })).toBe(false)
    expect(await vm.onSubmit({ decisions: DECISIONS, note: '' })).toBe(true)
    const [first, second] = api.apply.mock.calls.map((c) => c[2])
    expect(first).toMatchObject({ target: 'projects', project_ids: ['p2'], decisions: DECISIONS })
    expect(first.request_id).toBeTruthy()
    expect(second.request_id).toBe(first.request_id)
    expect(w.emitted('done')?.[0]).toEqual(['projects'])
    w.unmount()
  })

  // spec formula-management-repair-closure R3.1：未接入计算的域照常可应用，但显示后端说明
  it('未接入计算的域显示后端 wired_reason；已接入的域不提示', async () => {
    const w = open({ domain: 'tb_detail', slotKeys: ['1001'] })
    await reopen(w)
    expect(w.find('[data-testid="fas-not-wired"]').text())
      .toContain('试算表科目明细公式目前只保存、不参与计算：还没有任何计算读取这类公式')
    expect(w.html()).toContain('应用到指定项目')
    await w.setProps({ modelValue: false, domain: 'report' })
    await reopen(w)
    expect(w.find('[data-testid="fas-not-wired"]').exists()).toBe(false)
    w.unmount()
  })

  it('关掉再打开别的域：上一次晚到的域信息不覆盖本次', async () => {
    let release: (v: unknown) => void = () => {}
    api.domains.mockReturnValueOnce(new Promise((resolve) => { release = resolve }))
    const w = open({ domain: 'tb_detail', slotKeys: ['1001'] })
    await w.setProps({ modelValue: true })
    await w.setProps({ modelValue: false, domain: 'report' })
    await reopen(w)
    release({ domains: [{ key: 'tb_detail', wired: false, wired_reason: '旧' }, { key: 'report', wired: true }] })
    await flushPromises()
    expect(w.find('[data-testid="fas-not-wired"]').exists()).toBe(false)
    w.unmount()
  })

  it('应用到指定项目：回执里不会写入的不算「已应用」（R4：底稿域目标项目没有这张底稿）', async () => {
    api.apply.mockResolvedValueOnce({ publish_id: 'x', summary: { target_count: 1 },
      skipped: [{ project_id: 'p3', project_name: '丙公司', slot_key: 'D2|审定表D2-1|E8', reason: '该项目没有底稿 D2' }] })
    const w = open({ domain: 'wp', slotKeys: ['D2|审定表D2-1|E8'] })
    await reopen(w)
    const vm = w.vm as any
    vm.target = 'projects'
    await flushPromises()
    vm.projectIds = ['p2', 'p3']
    await vm.onPreview()
    expect(await vm.onSubmit({ decisions: DECISIONS, note: '' })).toBe(true)
    expect(msg.success).toHaveBeenCalledWith('已应用到 1 个项目，1 处未写入（原因见预览）')
    w.unmount()
  })

  it('域清单取不到：不提示，也不挡应用', async () => {
    api.domains.mockRejectedValueOnce(new Error('network'))
    const w = open({ domain: 'tb_detail', slotKeys: ['1001'] })
    await reopen(w)
    expect(w.find('[data-testid="fas-not-wired"]').exists()).toBe(false)
    expect(w.html()).toContain('提交为全局候选')
    w.unmount()
  })
})
