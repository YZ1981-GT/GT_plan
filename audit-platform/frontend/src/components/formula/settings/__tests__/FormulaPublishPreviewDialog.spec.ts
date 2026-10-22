/**
 * FormulaPublishPreviewDialog + FormulaConflictTable —— 发布前影响预览与决策（spec formula-global-settings-sync，R3 / R4.1）
 *
 * 守护：只列冲突条目；逐条 / 批量决策以 `{条目 key → 处理}` 回传；逐项目「本次应用 / 暂缓」（冻结项目不可选）；
 * 提交的 decisions 与后端 Decisions 同形；版本不一致时禁止提交；换一份预览从默认开始；只读决策（提交候选）不带选择。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import ElementPlus from 'element-plus'
import FormulaPublishPreviewDialog from '../FormulaPublishPreviewDialog.vue'
import FormulaConflictTable from '../FormulaConflictTable.vue'

const DialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue" class="dlg"><slot /><slot name="footer" /></div>',
})
const stubs = { ElDialog: DialogStub }

function plan(key: string, category: string, over: Record<string, unknown> = {}) {
  const [pid, slot] = key.split('|')
  return {
    key, project_id: pid, project_name: `项目${pid}`, frozen: false, slot_key: slot, label: slot,
    category, category_label: category, base_formula: 'A', new_formula: 'B', local_formula: 'C', ...over,
  }
}

const PREVIEW = {
  domain: 'report', scope: 'soe_standalone',
  changes: [{ slot_key: 'balance_sheet:BS-002', label: '货币资金', old: { formula: 'A' }, new: { formula: 'B' }, old_version: 3, new_version: 4 }],
  version_problems: [],
  summary: {
    counts: { conflict: 2, follow: 1, frozen: 1 }, affected_project_count: 3, conflict_count: 2, pending_total: 0,
    projects: [
      { project_id: 'p1', name: '项目p1', frozen: false, counts: { conflict: 1 }, pending: 0, changed: false },
      { project_id: 'p2', name: '项目p2', frozen: false, counts: { conflict: 1, follow: 1 }, pending: 0, changed: false },
      { project_id: 'p3', name: '项目p3', frozen: true, counts: { frozen: 1 }, pending: 0, changed: false },
    ],
  },
  items: [
    plan('p1|balance_sheet:BS-002', 'conflict'),
    plan('p2|balance_sheet:BS-002', 'conflict'),
    plan('p2|balance_sheet:BS-003', 'follow'),
    plan('p3|balance_sheet:BS-002', 'frozen', { frozen: true }),
  ],
}

describe('FormulaConflictTable', () => {
  it('只列冲突；逐条与批量决策按条目 key 回传', async () => {
    const w = mount(FormulaConflictTable, {
      props: {
        items: PREVIEW.items as any, modelValue: {},
        choices: [{ value: 'adopt', label: '采用' }, { value: 'keep', label: '保留' }],
      },
      global: { plugins: [ElementPlus] },
    })
    expect((w.vm as any).conflicts.map((i: any) => i.key)).toEqual(['p1|balance_sheet:BS-002', 'p2|balance_sheet:BS-002'])
    ;(w.vm as any).setOne('p1|balance_sheet:BS-002', 'keep')
    expect(w.emitted('update:modelValue')?.[0]).toEqual([{ 'p1|balance_sheet:BS-002': 'keep' }])
    await w.find('[data-testid="fct-all-adopt"]').trigger('click')
    expect(w.emitted('update:modelValue')?.[1]).toEqual([{
      'p1|balance_sheet:BS-002': 'adopt', 'p2|balance_sheet:BS-002': 'adopt',
    }])
    w.unmount()
  })
})

describe('FormulaPublishPreviewDialog', () => {
  let submit: ReturnType<typeof vi.fn>
  beforeEach(() => { submit = vi.fn(async () => true) })

  function open(props: Record<string, unknown> = {}) {
    return mount(FormulaPublishPreviewDialog, {
      props: { modelValue: true, preview: PREVIEW as any, submit, ...props },
      global: { plugins: [ElementPlus], stubs },
    })
  }

  it('默认：冲突交项目确认、项目全部应用；提交后关窗', async () => {
    const w = open()
    await w.find('[data-testid="formula-publish-submit"]').trigger('click')
    await flushPromises()
    expect(submit).toHaveBeenCalledWith({
      decisions: { project_choices: {}, conflict_choices: {}, default_conflict: 'ask' }, note: '',
    })
    expect(w.emitted('update:modelValue')?.[0]).toEqual([false])
    w.unmount()
  })

  it('逐项目暂缓 + 冲突决策 + 说明：原样进 decisions；「全部暂缓」跳过冻结项目', async () => {
    const w = open()
    const vm = w.vm as any
    vm.setAllProjects('defer')
    vm.setProject('p2', 'apply')
    vm.conflictChoices = { 'p1|balance_sheet:BS-002': 'adopt' }
    vm.note = '  统一口径  '
    await vm.onSubmit()
    expect(submit).toHaveBeenCalledWith({
      decisions: {
        project_choices: { p1: 'defer', p2: 'apply' },
        conflict_choices: { 'p1|balance_sheet:BS-002': 'adopt' },
        default_conflict: 'ask',
      },
      note: '统一口径',
    })
    w.unmount()
  })

  it('变更行没有逐公式位版本（模板发布 / 设为全局）：不显示整列「— → —」的版本列', async () => {
    const headers = async (w: ReturnType<typeof open>) => {
      await flushPromises()
      return w.findAll('th').map((t) => t.text().trim())
    }
    const withVersion = open()
    expect(await headers(withVersion)).toContain('版本')
    withVersion.unmount()
    const tplChanges = [{ slot_key: 'balance_sheet:BS-002', label: '货币资金', old: { formula: 'A' }, new: { formula: 'B' }, deleted: false }]
    const template = open({ preview: { ...PREVIEW, changes: tplChanges } })
    const hs = await headers(template)
    expect(hs).toContain('新定义')
    expect(hs).not.toContain('版本')
    template.unmount()
  })

  it('提交失败（返回 false）不关窗', async () => {
    submit.mockResolvedValueOnce(false)
    const w = open()
    await (w.vm as any).onSubmit()
    expect(w.emitted('update:modelValue')).toBeUndefined()
    w.unmount()
  })

  it('版本不一致：禁止提交', async () => {
    const w = open({ preview: { ...PREVIEW, version_problems: [{ slot_key: 'x', reason: 'conflict' }] } })
    expect(w.find('[data-testid="formula-publish-submit"]').attributes('disabled')).toBeDefined()
    w.unmount()
  })

  it('换一份预览：上一次的勾选清空', async () => {
    const w = open()
    const vm = w.vm as any
    vm.setProject('p1', 'defer')
    vm.conflictChoices = { 'p1|balance_sheet:BS-002': 'keep' }
    await w.setProps({ preview: { ...PREVIEW } as any })
    await nextTick()
    expect(vm.projectChoices).toEqual({})
    expect(vm.conflictChoices).toEqual({})
    w.unmount()
  })

  it('只读决策（提交全局候选）：不带任何选择', async () => {
    const w = open({ readonlyDecisions: true })
    const vm = w.vm as any
    vm.setProject('p1', 'defer')
    vm.conflictChoices = { 'p1|balance_sheet:BS-002': 'adopt' }
    await vm.onSubmit()
    expect(submit.mock.calls[0][0].decisions).toEqual({ project_choices: {}, conflict_choices: {}, default_conflict: 'ask' })
    w.unmount()
  })
})
