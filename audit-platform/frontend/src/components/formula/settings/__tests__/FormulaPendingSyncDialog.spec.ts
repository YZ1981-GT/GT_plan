/**
 * FormulaPendingSyncDialog —— 项目待确认弹窗（spec formula-global-settings-sync，R5 / design §13）
 *
 * 守护：进入项目自动弹一次（同会话同项目不再弹，角标常驻）；切项目时上一个项目晚到的响应不覆盖；
 * 逐条 / 批量决策提交（带上游版本，手工修改带定义）；事项已被新发布更新（409 STALE）时刷新重确认；
 * 只读成员（403）给出明确提示。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import ElementPlus from 'element-plus'

const { api, msg } = vi.hoisted(() => ({
  api: { pending: vi.fn(), resolve: vi.fn(), domains: vi.fn() },
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: api }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg }
})

import FormulaPendingSyncDialog from '../FormulaPendingSyncDialog.vue'

const DialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div v-if="modelValue" class="dlg"><slot /><slot name="footer" /></div>',
})

function item(id: string, over: Record<string, unknown> = {}) {
  return {
    id, project_id: 'p1', domain: 'report', slot_key: `balance_sheet:BS-00${id}`, slot_label: `货币资金${id}`,
    reason: 'conflict', reason_label: '冲突', upstream_origin: 'global', upstream_origin_label: '全局设置',
    upstream_template_id: null, base_definition: { formula: 'A' }, upstream_definition: { formula: 'B' },
    upstream_deleted: false, local_definition: { formula: 'C', formula_category: 'auto_calc' },
    base_formula: 'A', upstream_formula: 'B', local_formula: 'C', upstream_version: 5, publish_id: 'pub',
    created_at: null, updated_at: null, ...over,
  }
}

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

function mountDialog(projectId: string): VueWrapper<any> {
  return mount(FormulaPendingSyncDialog, {
    props: { projectId },
    global: { plugins: [ElementPlus], stubs: { ElDialog: DialogStub } },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  api.domains.mockResolvedValue({
    domains: [{ key: 'report', label: '报表公式', exec_fields: ['formula', 'formula_category'], desc_fields: [] }],
    is_admin: false,
  })
  api.pending.mockResolvedValue({ project_id: 'p1', count: 2, items: [item('1'), item('2')] })
  api.resolve.mockResolvedValue({ resolved: [] })
})

describe('进入项目自动弹出：同会话同项目只弹一次', () => {
  it('有待确认 → 自动弹出并显示角标；同项目再次进入不再自动弹，角标仍在', async () => {
    const w1 = mountDialog('p1')
    await flushPromises()
    expect(w1.vm.visible).toBe(true)
    expect(w1.find('[data-testid="formula-pending-badge"]').exists()).toBe(true)
    w1.unmount()

    const w2 = mountDialog('p1')
    await flushPromises()
    expect(w2.vm.visible).toBe(false)
    expect(w2.vm.count).toBe(2)
    expect(w2.find('[data-testid="formula-pending-badge"]').exists()).toBe(true)
    w2.unmount()
  })

  it('没有待确认 → 不弹、不显示角标', async () => {
    api.pending.mockResolvedValue({ project_id: 'p1', count: 0, items: [] })
    const w = mountDialog('p1')
    await flushPromises()
    expect(w.vm.visible).toBe(false)
    expect(w.find('[data-testid="formula-pending-badge"]').exists()).toBe(false)
    w.unmount()
  })

  it('切项目：上一个项目晚到的响应丢弃，弹窗随之关闭', async () => {
    const slow = deferred<any>()
    api.pending.mockImplementation((pid: string) => (pid === 'p1'
      ? slow.promise
      : Promise.resolve({ project_id: 'p2', count: 1, items: [item('9', { project_id: 'p2' })] })))
    const w = mountDialog('p1')
    await w.setProps({ projectId: 'p2' })
    await flushPromises()
    slow.resolve({ project_id: 'p1', count: 2, items: [item('1'), item('2')] })
    await flushPromises()
    expect(w.vm.items.map((i: any) => i.id)).toEqual(['9'])
    w.unmount()
  })
})

describe('处理待确认', () => {
  it('逐条选择后提交：带上游版本；手工修改带合并后的定义；成功后刷新并发出 resolved', async () => {
    const w = mountDialog('p1')
    await flushPromises()
    const [a, b] = w.vm.items
    w.vm.setChoice(a, 'keep')
    w.vm.setChoice(b, 'custom')
    w.vm.custom[b.id].formula = 'D'
    api.pending.mockResolvedValue({ project_id: 'p1', count: 0, items: [] })
    await w.vm.onSubmit()
    await flushPromises()

    expect(api.resolve).toHaveBeenCalledWith('p1', [
      { item_id: '1', choice: 'keep', upstream_version: 5 },
      { item_id: '2', choice: 'custom', upstream_version: 5, custom_definition: { formula: 'D', formula_category: 'auto_calc' } },
    ])
    expect(w.emitted('resolved')?.[0]).toEqual([['report']])
    expect(w.vm.visible).toBe(false)
    w.unmount()
  })

  it('批量「全部采用新定义」后只提交一次，未选择的不提交', async () => {
    const w = mountDialog('p1')
    await flushPromises()
    w.vm.setAll('adopt')
    await nextTick()
    expect(w.vm.chosenCount).toBe(2)
    await w.vm.onSubmit()
    expect(api.resolve).toHaveBeenCalledTimes(1)
    expect(api.resolve.mock.calls[0][1].map((r: any) => r.choice)).toEqual(['adopt', 'adopt'])
    w.unmount()
  })

  it('事项已被新的发布更新（409 STALE）→ 提示并刷新列表', async () => {
    api.resolve.mockRejectedValueOnce({
      response: { status: 409, data: { detail: { error_code: 'FORMULA_SYNC_ITEM_STALE', message: '已更新' } } },
    })
    const w = mountDialog('p1')
    await flushPromises()
    w.vm.setAll('adopt')
    const callsBefore = api.pending.mock.calls.length
    await w.vm.onSubmit()
    await flushPromises()
    expect(msg.warning).toHaveBeenCalledWith('有事项已被新的发布更新，已刷新列表，请重新确认')
    expect(api.pending.mock.calls.length).toBe(callsBefore + 1)
    w.unmount()
  })

  it('只读成员（403）→ 明确提示需要编辑权限', async () => {
    api.resolve.mockRejectedValueOnce({ response: { status: 403, data: { detail: '无权' } } })
    const w = mountDialog('p1')
    await flushPromises()
    w.vm.setAll('keep')
    await w.vm.onSubmit()
    expect(msg.warning).toHaveBeenCalledWith('只读成员可以查看，处理需要本项目的编辑权限')
    w.unmount()
  })
})
