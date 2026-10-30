/**
 * 企业树版本弹窗（spec consol-autotree-linkage-closure R1.4~R1.6；原「合并范围确认」）。
 *
 * - 合并计算不需要确认：弹窗只展示当前树、已记录版本（手动 / 推送时自动）与差异，可选「记录为新版本」（CAS）；
 * - 角色列与后端命名同口径（合并户 / 差额户 / 单体母公司户 …），按层级缩进；
 * - 向导（mode="created"）只预览自动生成的树，关闭即进入合并模块，不出现记录按钮；
 * - 旧的「确认当前合并范围」「新确认机制上线前已有合并数据」提示与死事件 attached 已删除。
 */
import fs from 'node:fs'
import path from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const { preview, confirm, message } = vi.hoisted(() => ({
  preview: vi.fn(),
  confirm: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))
vi.mock('@/services/consolScopeConfirmationApi', () => ({
  previewScopeConfirmation: (...a: any[]) => preview(...a),
  confirmScope: (...a: any[]) => confirm(...a),
}))
vi.mock('element-plus', () => ({ ElMessage: message }))

import ConsolScopeConfigDialog from '../ConsolScopeConfigDialog.vue'

const STUBS = {
  'el-dialog': { name: 'el-dialog', template: '<div v-if="modelValue" :data-title="title"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title'] },
  'el-table': { template: '<div data-testid="scope-table"><slot /></div>', props: ['data'] },
  'el-table-column': { template: '<div />' },
  'el-alert': { template: '<div data-testid="scope-alert">{{ title }}<slot /></div>', props: ['title'] },
  'el-empty': { template: '<div data-testid="scope-empty" :data-description="description" />', props: ['description'] },
  'el-button': { template: '<button><slot /></button>' },
  'el-tag': { template: '<span class="tag"><slot /></span>' },
}

function node(key: string, name: string, kind: string, children: any[] = [], extra: Record<string, unknown> = {}) {
  const [code, role] = key.split(':')
  return { node_key: key, company_code: code, company_name: name, display_name: name, role, kind, relation: null, children, ...extra }
}

function previewData(extra: Record<string, unknown> = {}) {
  const tree = node('G:consol', '某集团（合并户）', 'aggregate', [
    node('G:consol_elim', '某集团（差额户）', 'elim'),
    node('G:parent', '某集团（单体母公司户）', 'data'),
    node('A:subsidiary', '甲公司', 'data', [], { relation: 'subsidiary' }),
  ])
  return {
    project_id: 'g', year: 2025, report_scope: 'consolidated', revision: 3, fingerprint: 'fp-new', tree, nodes: [],
    diagnostics: [], confirmed: false, pending_confirmation: false, can_confirm: true, active_confirmation_id: 'c3',
    matches_recorded: false, recorded_revision: 3, recorded_mode: 'auto', recorded_at: '2026-10-26T02:00:00+00:00',
    structural_change: true,
    diff: { added: [{ node_key: 'A:subsidiary', label: '甲公司' }], removed: [], moved: [], changed: [], renamed: [], structural: true },
    ...extra,
  }
}

async function open(props: Record<string, unknown> = {}) {
  const wrapper = mount(ConsolScopeConfigDialog, {
    props: { modelValue: true, projectId: 'g', ...props }, global: { stubs: STUBS, directives: { loading: {} } },
  })
  wrapper.findComponent({ name: 'el-dialog' }).vm.$emit('open')
  await flushPromises()
  return wrapper
}

describe('ConsolScopeConfigDialog 企业树版本', () => {
  beforeEach(() => {
    preview.mockReset()
    confirm.mockReset()
    Object.values(message).forEach((f) => f.mockClear())
  })

  it('展示已记录版本与结构差异；角色按新命名、按层级缩进；可手动记录为新版本（CAS）', async () => {
    preview.mockResolvedValue(previewData())
    const wrapper = await open()
    expect(wrapper.find('[data-title]').attributes('data-title')).toBe('企业树版本')
    const version = wrapper.find('[data-testid="scope-version"]').text()
    expect(version).toContain('已记录版本 v3（推送时自动记录')
    expect(version).toContain('当前树结构已变化')
    expect(wrapper.text()).toContain('新增：甲公司')
    const members = (wrapper.vm as any).members
    expect(members.map((m: any) => [m.node_key, m.role_label, m.depth])).toEqual([
      ['G:consol', '合并户', 0], ['G:consol_elim', '差额户', 1], ['G:parent', '单体母公司户', 1], ['A:subsidiary', '子公司', 1],
    ])
    confirm.mockResolvedValue(previewData({ matches_recorded: true, recorded_revision: 4, recorded_mode: 'user', structural_change: false, diff: null }))
    await wrapper.find('[data-testid="record-version-btn"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith('g', { expected_fingerprint: 'fp-new', expected_revision: 3 })
    expect(message.success).toHaveBeenCalledWith('已记录为企业树版本 v4')
    expect(wrapper.emitted('recorded')).toHaveLength(1)
    expect(wrapper.find('[data-testid="record-version-btn"]').exists()).toBe(false)
  })

  it('当前树与已记录版本一致 / 尚未记录：不显示差异；只改名称不算结构变化', async () => {
    preview.mockResolvedValue(previewData({ matches_recorded: true, structural_change: false, diff: null }))
    const same = await open()
    expect(same.find('[data-testid="scope-version"]').text()).toContain('与当前树一致')
    expect(same.find('[data-testid="scope-diff"]').exists()).toBe(false)
    expect(same.find('[data-testid="record-version-btn"]').exists()).toBe(false)

    preview.mockResolvedValue(previewData({
      structural_change: false,
      diff: { added: [], removed: [], moved: [], changed: [], renamed: [{ node_key: 'A:subsidiary', from: '甲', to: '甲公司' }], structural: false },
    }))
    const renamed = await open()
    expect(renamed.find('[data-testid="scope-version"]').text()).toContain('当前树只改了名称')
    expect(renamed.text()).toContain('改名：甲 → 甲公司')

    preview.mockResolvedValue(previewData({ recorded_revision: 0, recorded_mode: null, recorded_at: null, diff: null }))
    const fresh = await open()
    expect(fresh.find('[data-testid="scope-version"]').text()).toContain('首次推送合并数时自动记录')
  })

  it('向导预览（mode=created）：只看自动生成的树，关闭按钮即进入合并模块，没有记录按钮', async () => {
    preview.mockResolvedValue(previewData())
    const wrapper = await open({ mode: 'created' })
    expect(wrapper.find('[data-title]').attributes('data-title')).toBe('企业树预览')
    expect(wrapper.find('[data-testid="scope-version"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="record-version-btn"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="scope-close-btn"]').text()).toBe('进入合并模块')
    expect(wrapper.text()).toContain('不需要确认')
  })

  it('没有下级时显示精确填写指引；版本冲突时提示刷新', async () => {
    preview.mockResolvedValue(previewData({ tree: node('G:consol', '某集团（合并户）', 'aggregate', [node('G:consol_elim', '某集团（差额户）', 'elim')]) }))
    const wrapper = await open()
    expect(wrapper.text()).toContain('请在各子公司/分公司项目的基本信息中把上级代码填为 G')
    confirm.mockRejectedValue({ response: { status: 409, data: { detail: { error_code: 'SCOPE_FINGERPRINT_CONFLICT', message: '企业树已变化' } } } })
    preview.mockResolvedValue(previewData())
    await wrapper.find('[data-testid="record-version-btn"]').trigger('click')
    await flushPromises()
    expect(message.warning).toHaveBeenCalledWith('企业树已变化，请检查后重新记录')
  })
})

describe('P12 生产接线守卫', () => {
  it('企业树版本弹窗不再有确认门、旧提示与死事件，也不走旧候选 / attach 流程', () => {
    const src = fs.readFileSync(path.resolve(__dirname, '../ConsolScopeConfigDialog.vue'), 'utf-8')
    expect(src).not.toContain('确认当前合并范围')
    expect(src).not.toContain('pending_legacy')
    expect(src).not.toMatch(/\battached\b/)
    expect(src).not.toContain('availableSubsidiaries')
    expect(src).not.toContain('attachSubsidiaries')
    expect(src).not.toContain('child_project_ids')
    expect(src).not.toContain('type="selection"')
    expect(src).toContain('请在各子公司/分公司项目的基本信息中把上级代码填为')
    const wizard = fs.readFileSync(path.resolve(__dirname, '../../../views/ProjectWizard.vue'), 'utf-8')
    expect(wizard).toContain('mode="created"')
    expect(wizard).not.toContain('@attached')
  })

  it('批量预览类型含 warnings 与关系/口径字段', () => {
    const src = fs.readFileSync(path.resolve(__dirname, '../BatchImportDialog.vue'), 'utf-8')
    const api = fs.readFileSync(path.resolve(__dirname, '../../../services/batchProjectImport.ts'), 'utf-8')
    expect(api).toContain('warnings: BatchWarning[]')
    expect(src).toContain('data.relation')
    expect(src).toContain('data.consolidatedProjectId')
    expect(src).toContain('data.standaloneProjectId')
    expect(src).toContain('v-if="validateResult.warnings?.length"')
    expect(src).toContain('validateResult.warnings')
  })
})
