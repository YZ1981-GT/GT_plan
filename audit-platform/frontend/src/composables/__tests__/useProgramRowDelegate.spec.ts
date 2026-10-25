/**
 * 程序行委派对话框（从 GtAProgramConsole.vue 抽出的 useProgramRowDelegate；扩权重试另见
 * GtAProgramConsoleScopeRetry.spec.ts）：打开时带出现执行人 / 复核人并只加载一次团队；预览只发一次、
 * 记下凭证 / 请求号 / 有效期；应用成功关窗并刷新 overlay，409 作废凭证要求重新预览。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  preview: vi.fn(), apply: vi.fn(), listAssignments: vi.fn(), handleApiError: vi.fn(), ensureTask: vi.fn(),
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/commonApi', () => ({
  previewProcedureDelegation: mocks.preview, applyProcedureDelegation: mocks.apply,
  ensureProgramRowTask: mocks.ensureTask,
}))
vi.mock('@/services/staffApi', () => ({ listAssignments: mocks.listAssignments }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: mocks.handleApiError }))
vi.mock('element-plus', () => ({ ElMessage: mocks.msg, ElMessageBox: { prompt: vi.fn() } }))
vi.mock('@/components/workpaper/composables/procedureConsoleOverlay', () => ({ newRequestId: () => 'req-fixed' }))

import { useProgramRowDelegate } from '../useProgramRowDelegate'

const ROW = { task_id: 't1', assignee_staff_id: 's-old', reviewer_staff_id: null, lock_version: 3 }

function setup() {
  const onApplied = vi.fn()
  return { onApplied, d: useProgramRowDelegate({ projectId: () => 'p1', onApplied }) }
}

beforeEach(() => {
  vi.clearAllMocks()
  for (const fn of [mocks.preview, mocks.apply, mocks.listAssignments]) fn.mockReset()
  mocks.listAssignments.mockResolvedValue([
    { staff_id: 's1', staff_name: '甲', role: 'auditor' },
    { staff_id: 's2', staff_name: '', role: 'qc' },
    { staff_id: null, staff_name: '无人员档案', role: 'manager' },
  ])
})

describe('useProgramRowDelegate', () => {
  it('打开：带出现执行人 / 复核人；团队只加载一次（角色显示中文，没有中文的照原样）', async () => {
    const { d } = setup()
    d.openDelegate(ROW)
    await vi.waitFor(() => expect(d.teamMembers.value).toHaveLength(2))
    expect(d.delegateDialog.value).toMatchObject({ visible: true, assigneeId: 's-old', reviewerId: '', previewId: '' })
    expect(d.teamMembers.value).toEqual([
      { staff_id: 's1', staff_name: '甲', role_label: '审计员' },
      { staff_id: 's2', staff_name: 's2', role_label: 'qc' },
    ])
    d.openDelegate(ROW)
    expect(mocks.listAssignments).toHaveBeenCalledTimes(1)
  })

  it('预览：没选执行人只提示；选了 ⇒ 按行发预览，记下凭证 / 请求号 / 有效期', async () => {
    const { d } = setup()
    d.openDelegate({ ...ROW, assignee_staff_id: null })
    await d.runDelegatePreview()
    expect(mocks.preview).not.toHaveBeenCalled()
    expect(mocks.msg.warning).toHaveBeenCalledWith('请选择程序执行人')

    mocks.preview.mockResolvedValue({ preview_id: 'pv-1', expires_at: '2026-10-25T10:00:00Z', summary: { targets: 1 } })
    d.delegateDialog.value.assigneeId = 's1'
    await d.runDelegatePreview()
    expect(mocks.preview).toHaveBeenCalledWith('p1', {
      selector: { kind: 'row', task_ids: ['t1'] }, assignee_staff_id: 's1', reviewer_staff_id: null,
    })
    expect(d.delegateDialog.value).toMatchObject({ previewId: 'pv-1', reqId: 'req-fixed', ttl: '2026-10-25T10:00:00Z', loading: false })
  })

  it('应用成功 ⇒ 关窗并刷新 overlay；409 ⇒ 作废凭证、要求重新预览、弹窗不关', async () => {
    const { d, onApplied } = setup()
    d.openDelegate(ROW)
    Object.assign(d.delegateDialog.value, { previewId: 'pv-1', reqId: 'req-1', previewStats: { status: 'ready' } })
    mocks.apply.mockResolvedValueOnce({ applied: 1 })
    await d.runDelegateApply()
    expect(mocks.apply).toHaveBeenCalledWith('p1', 'pv-1', 'req-1', {
      selector: { kind: 'row', task_ids: ['t1'] }, assignee_staff_id: 's-old', reviewer_staff_id: null,
    }, { silent: true })
    expect(d.delegateDialog.value.visible).toBe(false)
    expect(onApplied).toHaveBeenCalledTimes(1)

    d.openDelegate(ROW)
    Object.assign(d.delegateDialog.value, { previewId: 'pv-2', reqId: 'req-2', previewStats: { status: 'ready' } })
    mocks.apply.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'preview_consumed' } } })
    await d.runDelegateApply()
    expect(mocks.msg.warning).toHaveBeenCalledWith('预览已失效（过期/一次消费/目标版本变化），请重新预览')
    expect(d.delegateDialog.value).toMatchObject({ visible: true, previewId: '', previewStats: null, loading: false })
    expect(onApplied).toHaveBeenCalledTimes(1)
    expect(mocks.handleApiError).not.toHaveBeenCalled()
  })
})

describe('useProgramRowDelegate — 逐行委派（行上没有任务字段，spec procedure-chain-followup-closure R2.2）', () => {
  function setupRow() {
    return useProgramRowDelegate({
      projectId: () => 'p1', onApplied: vi.fn(), wpId: () => 'wp-1', sheetName: () => '固定资产实质性程序表H1A',
    })
  }

  it('先按底稿 + 表名 + 程序号取 / 建任务，再打开对话框；同一程序号的新旧任务一起委派', async () => {
    mocks.ensureTask.mockResolvedValue({
      task_ids: ['t-new', 't-old'], created: true, template_code: 'H1A', program_no: '2',
      assignee_staff_id: 's-old', reviewer_staff_id: null,
    })
    mocks.preview.mockResolvedValue({ preview_id: 'pv-1', summary: { targets: 2 } })
    const d = setupRow()
    await d.openDelegateForProgramRow({ program_no: 2 })
    expect(mocks.ensureTask).toHaveBeenCalledWith('p1', 'wp-1', '固定资产实质性程序表H1A', 2)
    expect(d.delegateDialog.value).toMatchObject({ visible: true, assigneeId: 's-old' })
    d.delegateDialog.value.assigneeId = 's1'
    await d.runDelegatePreview()
    expect(mocks.preview).toHaveBeenCalledWith('p1', {
      selector: { kind: 'row', task_ids: ['t-new', 't-old'] }, assignee_staff_id: 's1', reviewer_staff_id: null,
    })
  })

  it('建任务被拒（自加的行 422 / 已裁剪 409 / 非委派人 403）⇒ 提示原因，不打开对话框', async () => {
    const err = { response: { status: 409, data: { detail: { error: 'row_trimmed', message: '这一行已裁剪为不适用' } } } }
    mocks.ensureTask.mockRejectedValue(err)
    const d = setupRow()
    await d.openDelegateForProgramRow({ program_no: 3 })
    expect(mocks.handleApiError).toHaveBeenCalledWith(err, '委派')
    expect(d.delegateDialog.value.visible).toBe(false)
  })
})


it('预览目标为 0 时显示服务端原因，确认按钮路径不调用 apply', async () => {
  const { d } = setup()
  d.openDelegate(ROW)
  mocks.preview.mockResolvedValue({
    preview_id: 'pv-zero',
    summary: { targets: 0 },
    hint: '所选底稿都已裁剪或在回收站，不能委派',
  })
  await d.runDelegatePreview()
  expect(d.delegateDialog.value.previewStats?.hint).toContain('都已裁剪')

  await d.runDelegateApply()
  expect(mocks.apply).not.toHaveBeenCalled()
  expect(mocks.msg.warning).toHaveBeenCalledWith('所选底稿都已裁剪或在回收站，不能委派')
  expect(d.delegateDialog.value.visible).toBe(true)
})
