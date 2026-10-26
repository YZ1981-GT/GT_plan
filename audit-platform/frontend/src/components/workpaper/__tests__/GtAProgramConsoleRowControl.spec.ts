/**
 * 控制台行级控制（spec procedure-trim-generation-delegation-chain 需求 6 / 7，任务 15~17）：
 * 受限用户只有派给自己的行可编辑（其余只读并显示执行人）；新增程序给可改全部行的人，批量裁剪 / 裁剪选项只给委派人；
 * 裁剪 / 恢复先落到程序行任务，成功才改页面、失败保持原状；没有任务又不是模板程序的行只在页面上标记。
 * 表格按行真实渲染（el-table 桩把每一行交给各列的作用域插槽），断言看的是渲染结果。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, inject, provide } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessage } from 'element-plus'
import * as fs from 'node:fs'
import * as path from 'node:path'

const rowApi = vi.hoisted(() => ({
  setApplicability: vi.fn(), getAccess: vi.fn(), ensureTask: vi.fn(), preview: vi.fn(), apply: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'proj-001' }, query: {} }) }))
// 写字段覆盖取项目审计年度（audit-year R0）：项目详情给出 2025，其余接口空
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(async (url: string) => (url === '/api/projects/proj-001' ? { audit_year: 2025 } : [])),
    post: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock('@/composables/useWpOnboardingGuide', () => ({
  useWpOnboardingGuide: () => ({ showGuide: { value: false }, guideSteps: { value: [] }, triggerGuide: vi.fn() }),
}))
vi.mock('@/components/workpaper/GtAuditFlowGraph.vue', () => ({ default: { name: 'GtAuditFlowGraph', template: '<div />' } }))
vi.mock('@/services/commonApi', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  setProgramRowApplicability: rowApi.setApplicability,
  getProgramRowAccess: rowApi.getAccess,
  ensureProgramRowTask: rowApi.ensureTask,
  previewProcedureDelegation: rowApi.preview,
  applyProcedureDelegation: rowApi.apply,
}))
vi.mock('@/services/staffApi', () => ({ listAssignments: vi.fn().mockResolvedValue([]) }))

import GtAProgramConsole from '../GtAProgramConsole.vue'

const SHEET = '应收账款实质性程序表D2A'
const RowScope = defineComponent({
  props: { row: { type: Object, required: true } },
  setup(props, { slots }) {
    provide('stubRow', props.row)
    return () => h('div', { class: 'stub-row', 'data-no': String((props.row as any).program_no) }, slots.default?.())
  },
})
const passthrough = (tag: string) => defineComponent({
  name: tag, inheritAttrs: false,
  setup(_, { slots }) { return () => h('div', { class: tag }, [slots.default?.(), slots.dropdown?.(), slots.footer?.()]) },
})
const TAGS = [...new Set([...fs.readFileSync(path.resolve(__dirname, '../GtAProgramConsole.vue'), 'utf-8')
  .matchAll(/<(el-[a-z-]+)/g)].map((m) => m[1]))]
const STUBS: Record<string, any> = {
  ...Object.fromEntries(TAGS.map((t) => [t, passthrough(t)])),
  'el-table': defineComponent({
    props: { data: { type: Array, default: () => [] } },
    setup(props, { slots }) {
      return () => h('div', { class: 'el-table' },
        (props.data as any[]).map((row) => h(RowScope, { row, key: row.id }, { default: () => slots.default?.() })))
    },
  }),
  'el-table-column': defineComponent({
    props: ['type', 'label'],
    setup(props, { slots }) {
      const row = inject<any>('stubRow', null)
      return () => h('div', { class: props.type === 'selection' ? 'col-selection' : 'col', 'data-label': props.label },
        row && slots.default ? slots.default({ row }) : [])
    },
  }),
  'el-input': { template: '<textarea class="el-input" />', props: ['modelValue'] },
  'el-dropdown-item': { template: '<div class="el-dropdown-item" :data-command="command"><slot /></div>', props: ['command'] },
  'el-dialog': { template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>', props: ['modelValue'] },
  GtAProgramLinkedChips: true, GtGridSheet: true, WpInlinePopup: true, ProcedureReviewPanel: true,
}

const PROGRAMS = [
  { id: 'row-1', program_no: 1, program_desc: '核对明细表', program_category: '常规★', status: 'completed' },
  { id: 'row-2', program_no: 2, program_desc: '函证', program_category: '常规★', status: 'in_progress' },
  { id: 'row-3', program_no: 3, program_desc: '关联方', program_category: '常规★', status: 'not_applicable', trim_reason: '非 IPO' },
  { id: 'row-4', program_no: 4, program_desc: '期后回款', program_category: '常规★', status: 'pending' },
  { id: 'custom-1', program_no: 5, program_desc: '自加', program_category: '常规★', status: 'pending' },
]
const access = (over: Record<string, unknown> = {}) => ({
  full_power: true, can_trim: true, own_program_nos: [], assignees: {}, template_code: 'D2A', ...over,
})

async function mountConsole() {
  const wrapper = mount(GtAProgramConsole, {
    props: { wpId: 'wp-001', sheetName: SHEET, schema: {}, htmlData: { programs: JSON.parse(JSON.stringify(PROGRAMS)), trim_decisions: [] } },
    global: { stubs: STUBS },
  })
  await flushPromises()
  const row = (no: number) => wrapper.find(`.stub-row[data-no="${no}"]`)
  return { wrapper, vm: wrapper.vm as any, row }
}

beforeEach(() => {
  setActivePinia(createPinia())
  rowApi.setApplicability.mockReset().mockResolvedValue({ changed: true })
  rowApi.getAccess.mockReset().mockResolvedValue(access())
  rowApi.ensureTask.mockReset()
  vi.spyOn(ElMessage, 'warning').mockImplementation((() => undefined) as any)
})
afterEach(() => { vi.restoreAllMocks() })

const summaryInput = (r: ReturnType<Awaited<ReturnType<typeof mountConsole>>['row']>) =>
  r.find('[data-label="执行说明"] textarea.el-input')
const statusCell = (r: ReturnType<Awaited<ReturnType<typeof mountConsole>>['row']>) => r.find('[data-label="状态"]')

describe('GtAProgramConsole — 行归属', () => {
  it('受限用户：只有派给自己的行可编辑，其余只读并显示执行人；不能新增、不能裁剪', async () => {
    rowApi.getAccess.mockResolvedValue(access({
      full_power: false, can_trim: false, own_program_nos: ['2'], assignees: { 2: '甲', 4: '乙' },
    }))
    const { wrapper, row } = await mountConsole()
    expect(rowApi.getAccess).toHaveBeenCalledWith('wp-001', SHEET)
    expect(summaryInput(row(2)).exists()).toBe(true)
    expect(statusCell(row(2)).find('.el-dropdown').exists()).toBe(true)
    expect(statusCell(row(2)).find('[data-command="not_applicable"]').exists()).toBe(false)
    for (const no of [1, 3, 4, 5]) {
      expect(summaryInput(row(no)).exists(), `第 ${no} 行`).toBe(false)
      expect(statusCell(row(no)).find('.el-dropdown').exists(), `第 ${no} 行`).toBe(false)
    }
    expect(statusCell(row(4)).text()).toContain('执行：乙')
    expect(statusCell(row(2)).text()).not.toContain('执行：')
    expect(wrapper.find('.col-selection').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('+ 新增程序')
  })

  it('主编（可改全部行、不是委派人）：全部行可编辑，已裁的行不能恢复，没有裁剪入口', async () => {
    rowApi.getAccess.mockResolvedValue(access({ can_trim: false }))
    const { wrapper, row } = await mountConsole()
    expect(summaryInput(row(4)).exists()).toBe(true)
    expect(statusCell(row(4)).find('.el-dropdown').exists()).toBe(true)
    expect(statusCell(row(4)).find('[data-command="not_applicable"]').exists()).toBe(false)
    expect(statusCell(row(3)).find('.el-dropdown').exists()).toBe(false)
    expect(wrapper.find('.col-selection').exists()).toBe(false)
    expect(wrapper.text()).toContain('+ 新增程序')
  })

  it('委派人有裁剪入口；不适用的行只给「恢复执行」不给下拉（R4）；读不到行归属 ⇒ 整表只读 + 原因 + 重试（R7）', async () => {
    const { wrapper, row } = await mountConsole()
    expect(statusCell(row(4)).find('[data-command="not_applicable"]').exists()).toBe(true)
    expect(statusCell(row(4)).find('[data-command="pending"]').exists()).toBe(true)
    expect(statusCell(row(3)).find('.el-dropdown').exists()).toBe(false)
    expect(restoreButton(row(3))).toBeTruthy()
    expect(restoreButton(row(4))).toBeUndefined()
    expect(wrapper.find('.col-selection').exists()).toBe(true)

    // 原先读不到按全权放开（服务端保存兜底）⇒ 页面上能改、保存时才被静默丢弃
    rowApi.getAccess.mockRejectedValue({ response: { status: 500, data: { detail: '服务暂不可用' } } })
    const fallback = await mountConsole()
    expect(summaryInput(fallback.row(4)).exists()).toBe(false)
    expect(statusCell(fallback.row(4)).find('.el-dropdown').exists()).toBe(false)
    expect(restoreButton(fallback.row(3))).toBeUndefined()
    expect(fallback.wrapper.find('.col-selection').exists()).toBe(false)
    expect(fallback.wrapper.text()).not.toContain('+ 新增程序')
    // el-alert 是透传桩（不带 class）⇒ 按文字找
    const alerts = fallback.wrapper.findAll('.el-alert').map((w) => w.text())
    expect(alerts.some((t) => t.includes('无法读取本表的行级权限（服务暂不可用）') && t.includes('重试'))).toBe(true)
  })
})

// el-button 是透传桩（不绑事件）⇒ 取组件实例，点击 = 调它收到的 onClick
const delegateButton = (r: ReturnType<Awaited<ReturnType<typeof mountConsole>>['row']>) =>
  statusCell(r).findAllComponents({ name: 'el-button' }).find((b: { text(): string }) => b.text() === '委派')

describe('GtAProgramConsole — 逐行委派（程序行任务开关关闭也可用，spec procedure-chain-followup-closure R2.2）', () => {
  it('委派人：未裁剪的模板行都有「委派」；已裁剪的行、自加的行没有；显示已委派的执行人', async () => {
    rowApi.getAccess.mockResolvedValue(access({ assignees: { 2: '甲' } }))
    const { row } = await mountConsole()
    for (const no of [1, 2, 4]) expect(delegateButton(row(no)), `第 ${no} 行`).toBeTruthy()
    for (const no of [3, 5]) expect(delegateButton(row(no)), `第 ${no} 行`).toBeUndefined()
    expect(statusCell(row(2)).text()).toContain('执行：甲')
  })

  it('不是委派人（受限用户 / 主编）没有「委派」', async () => {
    rowApi.getAccess.mockResolvedValue(access({ can_trim: false }))
    const { row } = await mountConsole()
    for (const no of [1, 2, 4]) expect(delegateButton(row(no)), `第 ${no} 行`).toBeUndefined()
  })

  it('点「委派」⇒ 按底稿 + 表名 + 程序号取 / 建这一行的任务，再打开委派对话框', async () => {
    rowApi.ensureTask.mockResolvedValue({
      task_ids: ['t-4'], created: true, template_code: 'D2A', program_no: '4', assignee_staff_id: null, reviewer_staff_id: null,
    })
    const { vm, row } = await mountConsole()
    await (delegateButton(row(4))!.vm.$attrs as any).onClick()
    await flushPromises()
    expect(rowApi.ensureTask).toHaveBeenCalledWith('proj-001', 'wp-001', SHEET, 4)
    expect(vm.delegateDialog).toMatchObject({ visible: true })
    expect(vm.delegateDialog.row.task_ids).toEqual(['t-4'])
  })

  it('委派应用成功 ⇒ 重新读行归属（开关关闭时执行人来自行归属接口，否则页面上仍是旧执行人）', async () => {
    rowApi.ensureTask.mockResolvedValue({
      task_ids: ['t-4'], created: true, template_code: 'D2A', program_no: '4', assignee_staff_id: null, reviewer_staff_id: null,
    })
    rowApi.preview.mockResolvedValue({ preview_id: 'pv-1', summary: { targets: 1 } })
    rowApi.apply.mockResolvedValue({ applied: 1 })
    vi.spyOn(ElMessage, 'success').mockImplementation((() => undefined) as any)
    const { vm, row } = await mountConsole()
    await (delegateButton(row(4))!.vm.$attrs as any).onClick()
    await flushPromises()
    vm.delegateDialog.assigneeId = 's-1'
    await vm.runDelegatePreview()
    const before = rowApi.getAccess.mock.calls.length
    await vm.runDelegateApply()
    await flushPromises()
    expect(rowApi.apply).toHaveBeenCalledTimes(1)
    expect(rowApi.getAccess.mock.calls.length).toBeGreaterThan(before)
  })
})

const httpError = (status: number, detail: unknown) => ({ response: { status, data: { detail } } })
const restoreButton = (r: ReturnType<Awaited<ReturnType<typeof mountConsole>>['row']>) =>
  r.find('[data-label="裁剪/灰显说明"]').findAllComponents({ name: 'el-button' })
    .find((b: { text(): string }) => b.text() === '恢复执行')
const byNo = (vm: any, no: number) => vm.programs.find((p: any) => p.program_no === no)

describe('GtAProgramConsole — 按行裁剪 / 恢复先落到程序行任务', () => {
  it('裁剪成功才改页面；失败保持原状并提示（不再先改页面再保存）', async () => {
    const { vm, wrapper } = await mountConsole()
    vm.handleStatusChange(byNo(vm, 4), 'not_applicable')
    vm.trimForm.reason = '本期无期后回款'
    rowApi.setApplicability.mockRejectedValueOnce(httpError(403, '项目授权失败：委派角色不足'))
    await vm.confirmTrim()
    expect(byNo(vm, 4).status).toBe('pending')
    expect(wrapper.emitted('program-trim')).toBeUndefined()
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('只有项目经理 / 合伙人可以裁剪或恢复程序'))

    await vm.confirmTrim()
    expect(rowApi.setApplicability).toHaveBeenLastCalledWith('proj-001', 'wp-001', 'trim', expect.objectContaining({
      sheet_name: SHEET, program_no: '4', reason: '本期无期后回款',
    }))
    expect([byNo(vm, 4).status, byNo(vm, 4).trim_reason]).toEqual(['not_applicable', '本期无期后回款'])
    expect(wrapper.emitted('program-trim')).toHaveLength(1)
  })

  it('没有任务又不是模板程序的行（422 row_trim_unsupported）只在页面上标记', async () => {
    const { vm } = await mountConsole()
    vm.handleStatusChange(byNo(vm, 5), 'not_applicable')
    vm.trimForm.reason = '自加程序不做了'
    rowApi.setApplicability.mockRejectedValueOnce(httpError(422, { error: 'row_trim_unsupported', message: '第 5 条…' }))
    await vm.confirmTrim()
    expect(byNo(vm, 5).status).toBe('not_applicable')
    expect(ElMessage.warning).not.toHaveBeenCalled()
  })

  it('恢复执行（R4）：先调恢复接口，成功才改回待执行、清掉裁剪理由并提示重新委派；失败不动；下拉改状态不碰细裁接口', async () => {
    vi.spyOn(ElMessage, 'success').mockImplementation((() => undefined) as any)
    const { vm, row } = await mountConsole()
    rowApi.setApplicability.mockRejectedValueOnce(httpError(409, '已复核任务不可取消'))
    await vm.restoreProgramRow(byNo(vm, 3))
    expect([byNo(vm, 3).status, byNo(vm, 3).trim_reason]).toEqual(['not_applicable', '非 IPO'])
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('已复核任务不可取消'))

    rowApi.setApplicability.mockResolvedValueOnce({ changed: true, requires_reassign: true, previous_assignees: ['甲'] })
    await (restoreButton(row(3))!.vm.$attrs as any).onClick()
    await flushPromises()
    expect(rowApi.setApplicability).toHaveBeenLastCalledWith('proj-001', 'wp-001', 'restore',
      expect.objectContaining({ sheet_name: SHEET, program_no: '3' }))
    expect([byNo(vm, 3).status, byNo(vm, 3).trim_reason]).toEqual(['pending', ''])
    expect(ElMessage.success).toHaveBeenCalledWith('已恢复执行，原执行人已清除（原执行人：甲），请重新委派')

    rowApi.setApplicability.mockClear()
    await vm.handleStatusChange(byNo(vm, 4), 'completed')
    expect(rowApi.setApplicability).not.toHaveBeenCalled() // 普通状态切换不碰细裁接口
    expect(byNo(vm, 4).status).toBe('completed')
  })

  it('批量裁剪逐行落库，只改成功的行，失败的逐条提示', async () => {
    const { vm, wrapper } = await mountConsole()
    vm.selectedIds = ['row-2', 'row-4']
    vm.batchTrimForm.reason = '本项目不涉及'
    rowApi.setApplicability.mockImplementation(async (_p: string, _w: string, _a: string, body: any) => {
      if (body.program_no === '2') throw httpError(409, '已复核任务不可取消')
      return { changed: true }
    })
    await vm.confirmBatchTrim()
    expect(rowApi.setApplicability.mock.calls.map((c: any[]) => c[3].program_no)).toEqual(['2', '4'])
    expect(byNo(vm, 2).status).toBe('in_progress')
    expect([byNo(vm, 4).status, byNo(vm, 4).trim_reason]).toEqual(['not_applicable', '本项目不涉及'])
    expect(wrapper.emitted('program-trim')).toEqual([[{ programId: 'row-4', reason: '本项目不涉及' }]])
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.stringContaining('第 2 条：已复核任务不可取消'))
    expect(vm.selectedIds).toEqual([])
  })
})
