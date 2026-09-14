// Feature: procedure-delegation-visibility-isolation — Task 12（组件 C16 Frontend）
//
// 验证「底稿粗裁与委派」页两层委派呈现不串线（Req 12.x / design 组件 C16）：
//  - 底稿层主编（Workpaper_Lead = WorkingPaper.assigned_to）在粗裁表单独一列，读自己的真源
//    （getProcedures 返回的 assigned_to → onAssigneeChange 走 assignProcedures 主编真源）。
//  - 程序行执行人 / 操作复核人（Row_Assignee / Operation_Reviewer = ProcedureRowTask）在
//    「程序委派向导」里单独设置，走 preview/apply 行层真源，与主编列互不串线。
//  - 高阶复核（业务合伙人 / QC / EQCR）不得显示为程序行 reviewer（角色术语说明明确声明）。
//  - 两层状态相互独立：改一层不影响另一层的内存状态。
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ROLE_TERMS } from '@/components/workpaper/composables/procedureConsoleOverlay'

const mocks = vi.hoisted(() => ({
  getProcedures: vi.fn(),
  updateProcedureTrim: vi.fn(),
  canonicalTrimPreview: vi.fn(),
  canonicalTrimApply: vi.fn(),
  initProcedures: vi.fn(),
  addCustomProcedure: vi.fn(),
  applyProcedureScheme: vi.fn(),
  listProjects: vi.fn(),
  assignProcedures: vi.fn(),
  previewProcedureDelegation: vi.fn(),
  applyProcedureDelegation: vi.fn(),
  listAssignments: vi.fn(),
  messageSuccess: vi.fn(),
  messageWarning: vi.fn(),
  routerPush: vi.fn(),
}))

vi.mock('@/services/commonApi', () => ({
  getProcedures: mocks.getProcedures,
  updateProcedureTrim: mocks.updateProcedureTrim,
  canonicalTrimPreview: mocks.canonicalTrimPreview,
  canonicalTrimApply: mocks.canonicalTrimApply,
  initProcedures: mocks.initProcedures,
  addCustomProcedure: mocks.addCustomProcedure,
  applyProcedureScheme: mocks.applyProcedureScheme,
  listProjects: mocks.listProjects,
  assignProcedures: mocks.assignProcedures,
  previewProcedureDelegation: mocks.previewProcedureDelegation,
  applyProcedureDelegation: mocks.applyProcedureDelegation,
}))
vi.mock('@/services/staffApi', () => ({ listAssignments: mocks.listAssignments }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ currentRole: { value: 'manager' } }),
}))
vi.mock('@/composables/useAuditContext', () => ({
  useAuditContext: () => ({ year: { value: 2025 } }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-1' }, query: {} }),
  useRouter: () => ({ push: mocks.routerPush }),
  onBeforeRouteLeave: vi.fn(),
}))
vi.mock('element-plus', () => ({
  ElMessage: Object.assign(
    (..._a: any[]) => {},
    { success: mocks.messageSuccess, warning: mocks.messageWarning, error: vi.fn(), info: vi.fn() },
  ),
  ElMessageBox: { confirm: vi.fn().mockResolvedValue(true), prompt: vi.fn().mockResolvedValue({ value: 'x' }) },
}))

import ProcedureTrimming from '../ProcedureTrimming.vue'

// el-table / el-table-column 渲染 header + 每行 default，便于断言列头文案。
import { defineComponent, h, provide, inject, computed, type ComputedRef } from 'vue'
const rowsKey = Symbol('rows')
const ElTableStub = defineComponent({
  props: { data: { type: Array, default: () => [] } },
  setup(props, { slots }) {
    provide(rowsKey, computed(() => props.data as any[]))
    return () => h('table', { class: 'el-table-stub' }, slots.default?.())
  },
})
const ElTableColumnStub = defineComponent({
  props: { label: { type: String, default: '' } },
  setup(props, { slots }) {
    const rows = inject<ComputedRef<any[]>>(rowsKey, computed(() => []))
    return () => h('div', { class: 'el-col-stub' }, [
      h('div', { class: 'el-col-header' }, slots.header ? slots.header() : props.label),
      ...(slots.default ? rows.value.map((row, i) => h('div', { class: 'el-cell', key: i }, slots.default!({ row }))) : []),
    ])
  },
})

const passthrough = (cls: string) => ({ template: `<div class="${cls}"><slot /></div>` })
const stubs: Record<string, any> = {
  'el-table': ElTableStub,
  'el-table-column': ElTableColumnStub,
  'el-tabs': passthrough('el-tabs'),
  'el-tab-pane': passthrough('el-tab-pane'),
  'el-alert': { template: '<div class="el-alert"><slot name="title" /><slot /></div>' },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>' },
  'el-switch': { template: '<span class="el-switch" />' },
  'el-input': { template: '<input class="el-input" />' },
  'el-select': { template: '<div class="el-select"><slot /></div>' },
  'el-option': { template: '<div class="el-option" />' },
  'el-tooltip': { template: '<span class="el-tooltip"><slot name="content" /><slot /></span>' },
  'el-divider': { template: '<span />' },
  'el-progress': { template: '<span class="el-progress" />' },
  'el-dialog': { template: '<div class="el-dialog"><slot /><slot name="footer" /></div>' },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div class="el-form-item">{{ label }}<slot /></div>', props: ['label'] },
  'el-upload': { template: '<div><slot /></div>' },
  'el-descriptions': { template: '<div><slot /></div>' },
  'el-descriptions-item': { template: '<div><slot /></div>' },
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio': { template: '<label><slot /></label>' },
  'el-checkbox': { template: '<label><slot /></label>' },
  'el-checkbox-group': { template: '<div><slot /></div>' },
}

const PROC = {
  id: 'proc-1', procedure_code: 'D-01', procedure_name: '核对应收明细账',
  status: 'execute', assigned_to: 's-lead', wp_id: 'wp-1', wp_code: 'D2-1', is_custom: false,
}
const TEAM = [
  { staff_id: 's-lead', role: 'auditor' },
  { staff_id: 's-partner', role: 'partner' },
]

async function mountView() {
  mocks.getProcedures.mockResolvedValue([PROC])
  mocks.initProcedures.mockResolvedValue([PROC])
  mocks.listAssignments.mockResolvedValue(TEAM)
  mocks.listProjects.mockResolvedValue([{ id: 'project-1', project_name: '示例项目' }])
  const wrapper = mount(ProcedureTrimming, { global: { stubs } })
  await flushPromises()
  return wrapper
}

beforeEach(() => vi.clearAllMocks())

describe('ProcedureTrimming — 两层委派呈现不串线（Task 12）', () => {
  it('角色术语说明区分底稿层主编与程序行执行/操作复核，且高阶复核不显示为程序行 reviewer', async () => {
    const wrapper = await mountView()
    const text = wrapper.text()
    // 底稿层主编（粗裁）
    expect(text).toContain(ROLE_TERMS.workpaperLead) // 底稿主编
    // 程序行执行/操作复核（细裁）
    expect(text).toContain(ROLE_TERMS.procedureAssignee) // 程序执行人
    expect(text).toContain(ROLE_TERMS.operationReviewer) // 操作复核人
    // 高阶复核（业务合伙人/QC/EQCR）明确声明不在此显示为程序行复核人
    expect(text).toContain(ROLE_TERMS.highOrderReviewer)
    expect(text).toMatch(/不在此显示为程序行复核人/)
  })

  it('粗裁表有独立「底稿主编」列（Workpaper_Lead 真源），不出现「操作复核人」列', async () => {
    const wrapper = await mountView()
    const headers = wrapper.findAll('.el-col-header').map(h => h.text())
    // 底稿主编列存在（读自 getProcedures 的 assigned_to 主编真源）
    expect(headers.some(h => h.includes(ROLE_TERMS.workpaperLead))).toBe(true)
    // 粗裁表不把程序行执行/操作复核作为列（那是行层，走委派向导）
    expect(headers.some(h => h.includes(ROLE_TERMS.operationReviewer))).toBe(false)
    expect(headers.some(h => h.includes(ROLE_TERMS.procedureAssignee))).toBe(false)
  })

  it('程序委派向导（行层）单独设置执行人/操作复核人，走 ProcedureRowTask 真源', async () => {
    const wrapper = await mountView()
    // 打开委派向导
    const btn = wrapper.findAll('button.el-button').find(b => b.text().includes('程序委派向导'))
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    await flushPromises()
    const text = wrapper.text()
    // 向导表单含程序执行人 + 操作复核人（行层字段），与粗裁主编列分离
    expect(text).toContain(ROLE_TERMS.procedureAssignee)
    expect(text).toContain(ROLE_TERMS.operationReviewer)
  })

  it('两层状态互不串线：主编委派走 assignProcedures，行层委派走 preview/apply（不同真源）', async () => {
    mocks.assignProcedures.mockResolvedValue({})
    mocks.previewProcedureDelegation.mockResolvedValue({ status: 'ready', preview_id: 'pv-1', preview: { target_count: 1 } })
    const wrapper = await mountView()
    const vm = wrapper.vm as any

    // 主编层：更改底稿主编 → 只调用 assignProcedures（WorkingPaper.assigned_to 主编真源）
    const proc = vm.procedures[0]
    proc.assigned_to = 's-partner'
    await vm.onAssigneeChange(proc)
    await flushPromises()
    expect(mocks.assignProcedures).toHaveBeenCalledTimes(1)
    const [, payload] = mocks.assignProcedures.mock.calls[0]
    expect(payload[0]).toMatchObject({ procedure_id: 'proc-1', staff_id: 's-partner' })
    // 行层委派 API 未被主编操作触发（不串线）
    expect(mocks.previewProcedureDelegation).not.toHaveBeenCalled()
    expect(mocks.applyProcedureDelegation).not.toHaveBeenCalled()

    // 行层：委派向导 preview → 走 ProcedureRowTask 真源，且不回写主编列
    vm.delegateWizard.visible = true
    vm.delegateWizard.assigneeId = 's-lead'
    await vm.runDelegatePreview()
    await flushPromises()
    expect(mocks.previewProcedureDelegation).toHaveBeenCalledTimes(1)
    const [, body] = mocks.previewProcedureDelegation.mock.calls[0]
    expect(body.selector).toMatchObject({ kind: 'cycle' })
    expect(body.assignee_staff_id).toBe('s-lead')
    // 主编层未被行层操作改动（procedures[].assigned_to 仍是上一步设置的值）
    expect(vm.procedures[0].assigned_to).toBe('s-partner')
    // 行层 preview 未再触发主编委派
    expect(mocks.assignProcedures).toHaveBeenCalledTimes(1)
  })
})
