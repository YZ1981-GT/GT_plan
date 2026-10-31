/**
 * 调整大厅操作（spec adjustment-hall-entry-review-closure 需求 4 / 5.2）：按状态 × 权限的可用动作、批量拆分、
 * 结果提示、错误文案，以及通过 / 撤回复核 / 撤回提交的请求与刷新。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const api = vi.hoisted(() => ({
  reviewAdjustmentsBatch: vi.fn(),
  revokeAdjustmentReview: vi.fn(),
  withdrawAdjustmentSubmission: vi.fn(),
  batchDeleteAdjustments: vi.fn(),
  deleteAdjustment: vi.fn(),
  createAdjustment: vi.fn(),
  convertAjeToMisstatement: vi.fn(),
}))
const ui = vi.hoisted(() => ({ message: vi.fn(), confirmDangerous: vi.fn(), emit: vi.fn() }))

vi.mock('@/services/auditPlatformApi', () => api)
vi.mock('element-plus', () => {
  const ElMessage: any = (opts: unknown) => ui.message(opts)
  for (const t of ['success', 'warning', 'info', 'error']) ElMessage[t] = (opts: unknown) => ui.message({ type: t, opts })
  return { ElMessage }
})
vi.mock('@/utils/confirm', () => ({
  confirmDangerous: ui.confirmDangerous, confirmDelete: vi.fn(), confirmConvert: vi.fn(),
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: ui.emit } }))
vi.mock('@/utils/operationHistory', () => ({ operationHistory: { execute: (op: any) => op.execute() } }))

import {
  adjustmentErrorMessage, flowResultMessage, reportAdjustmentError, rowActions, splitEligible, useAdjustmentHallActions,
  withDescriptions, type HallPerms,
} from '../useAdjustmentHallActions'

const ALL: HallPerms = { writable: true, edit: true, review: true }
const EDIT_ONLY: HallPerms = { writable: true, edit: true, review: false }
const REVIEW_ONLY: HallPerms = { writable: true, edit: false, review: true }
const row = (status: string, extra: Record<string, unknown> = {}) =>
  ({ entry_group_id: `g-${status}`, adjustment_no: `AJE-${status}`, adjustment_type: 'aje', review_status: status, ...extra })
const sorted = (s: Set<string>) => [...s].sort()

beforeEach(() => {
  vi.clearAllMocks()
  ui.confirmDangerous.mockResolvedValue(undefined)
})

describe('rowActions：状态 × 权限', () => {
  it.each([
    ['draft', ALL, ['approve', 'delete', 'edit', 'submit']],
    ['draft', EDIT_ONLY, ['delete', 'edit', 'submit']],
    ['pending_review', ALL, ['approve', 'reject', 'withdraw']],
    ['pending_review', EDIT_ONLY, ['withdraw']],
    ['pending_review', REVIEW_ONLY, ['approve', 'reject']],
    ['rejected', EDIT_ONLY, ['convert', 'delete', 'edit', 'submit']],
    ['rejected', REVIEW_ONLY, []],
    ['approved', ALL, ['revoke']],
    ['approved', EDIT_ONLY, []],
  ])('%s + %o ⇒ %o', (status, perms, expected) => {
    expect(sorted(rowActions(row(status), perms))).toEqual(expected)
  })

  it('项目不可写（已归档）⇒ 什么都不能做', () => {
    expect(rowActions(row('draft'), { ...ALL, writable: false }).size).toBe(0)
  })

  it('底稿来源不能在大厅改明细；已转错报 / 重分类不再出「转错报」', () => {
    expect(rowActions(row('draft', { origin: 'workpaper' }), ALL).has('edit')).toBe(false)
    expect(rowActions(row('rejected', { converted_to_misstatement_id: 'm1' }), ALL).has('convert')).toBe(false)
    expect(rowActions(row('rejected', { adjustment_type: 'rje' }), ALL).has('convert')).toBe(false)
  })

  it('splitEligible 按动作拆可做 / 跳过', () => {
    const rows = [row('draft'), row('pending_review'), row('approved')]
    expect(splitEligible(rows, 'submit', ALL)).toMatchObject({ eligible: [rows[0]], skipped: 2 })
    expect(splitEligible(rows, 'approve', ALL).eligible).toEqual([rows[0], rows[1]])
  })
})

describe('提示文案', () => {
  it('批量结果：成功数、逐笔失败原因、通知了谁', () => {
    const res = flowResultMessage({
      succeeded: [{ entry_group_id: 'a' }, { entry_group_id: 'b' }],
      failed: [{ entry_group_id: 'c', adjustment_no: 'AJE-003', reason: '当前为「已批准」，不能提交复核' }],
      notified: [{ user_id: 'u1', name: '张三', kind: 'reviewer' }, { user_id: 'u1', name: '张三', kind: 'reviewer' }],
    }, '提交复核')
    expect(res.type).toBe('warning')
    expect(res.message).toBe('已提交复核 2 笔；1 笔未处理（AJE-003：当前为「已批准」，不能提交复核）；已通知 张三')
    expect(flowResultMessage({ succeeded: [], failed: [{ entry_group_id: 'c', adjustment_no: null, reason: 'x' }], notified: [] }, '通过').type)
      .toBe('error')
  })

  it('权限码转人话；423 合并锁发锁定态事件', () => {
    const forbidden = { response: { status: 403, data: { detail: { error_code: 'PROJECT_PERMISSION_REQUIRED', permission: 'adjustment:review' } } } }
    expect(adjustmentErrorMessage(forbidden)).toBe('没有复核调整分录的权限')
    reportAdjustmentError({ response: { status: 423, data: { detail: '项目已被合并锁定' } } }, '通过')
    expect(ui.emit).toHaveBeenCalledWith('consol-lock:detected', {})
    reportAdjustmentError({ response: { status: 400, data: { detail: '分录不存在' } } }, '撤回提交')
    expect(ui.message).toHaveBeenLastCalledWith({ type: 'error', opts: expect.objectContaining({ message: '撤回提交失败：分录不存在' }) })
  })
})

describe('useAdjustmentHallActions', () => {
  function setup() {
    const onChanged = vi.fn()
    const actions = useAdjustmentHallActions({ projectId: ref('p1'), year: ref(2025), onChanged })
    return { actions, onChanged }
  }

  it('单笔通过走批量端点、不弹确认；成功后刷新', async () => {
    api.reviewAdjustmentsBatch.mockResolvedValue({ succeeded: [{ entry_group_id: 'g-draft' }], failed: [], notified: [] })
    const { actions, onChanged } = setup()
    expect(await actions.approve([row('draft')])).toBe(true)
    expect(ui.confirmDangerous).not.toHaveBeenCalled()
    expect(api.reviewAdjustmentsBatch).toHaveBeenCalledWith('p1', { entry_group_ids: ['g-draft'], status: 'approved' })
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it('批量通过先确认，取消则不发请求', async () => {
    ui.confirmDangerous.mockRejectedValueOnce(new Error('cancel'))
    const { actions } = setup()
    expect(await actions.approve([row('draft'), row('pending_review')])).toBe(false)
    expect(api.reviewAdjustmentsBatch).not.toHaveBeenCalled()
  })

  it('驳回带统一原因与逐笔原因', async () => {
    api.reviewAdjustmentsBatch.mockResolvedValue({ succeeded: [{ entry_group_id: 'g-pending_review' }], failed: [], notified: [] })
    const { actions } = setup()
    await actions.reject([row('pending_review')], '比例不对', { 'g-pending_review': '账龄不对' })
    expect(api.reviewAdjustmentsBatch).toHaveBeenCalledWith('p1', {
      entry_group_ids: ['g-pending_review'], status: 'rejected', reason: '比例不对', reasons: { 'g-pending_review': '账龄不对' },
    })
  })

  it('撤回复核逐笔调，一笔失败不影响其余，失败原因进提示', async () => {
    api.revokeAdjustmentReview
      .mockResolvedValueOnce({ notified: [{ user_id: 'u1', name: '李四', kind: 'preparer' }] })
      .mockRejectedValueOnce({ response: { status: 400, data: { detail: '当前状态「草稿」，不允许撤回' } } })
    const { actions, onChanged } = setup()
    const ok = await actions.revoke([row('approved'), { ...row('approved'), entry_group_id: 'g2', adjustment_no: 'AJE-2' }], '复核意见变更')
    expect(ok).toBe(true)
    expect(api.revokeAdjustmentReview).toHaveBeenNthCalledWith(1, 'p1', 'g-approved', { reason: '复核意见变更' })
    expect(ui.message).toHaveBeenCalledWith(expect.objectContaining({
      type: 'warning', message: '已撤回复核 1 笔；1 笔未处理（AJE-2：当前状态「草稿」，不允许撤回）；已通知 李四',
    }))
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it('撤回提交失败显示后端原因，不刷新', async () => {
    api.withdrawAdjustmentSubmission.mockRejectedValue({ response: { status: 400, data: { detail: { error_code: 'WITHDRAW_BLOCKED', message: '只有待复核的分录可以撤回提交' } } } })
    const { actions, onChanged } = setup()
    expect(await actions.withdraw(row('pending_review'))).toBe(false)
    expect(ui.message).toHaveBeenLastCalledWith({ type: 'error', opts: expect.objectContaining({ message: '撤回提交失败：只有待复核的分录可以撤回提交' }) })
    expect(onChanged).not.toHaveBeenCalled()
  })
})

describe('withDescriptions（导入 / 保存回执只有编号，摘要从列表补齐）', () => {
  it('按分录组 id 补上摘要；列表里没有的保持没有摘要（不编造）', () => {
    const rows = [
      { entry_group_id: 'g1', adjustment_no: 'AJE-003' },
      { entry_group_id: 'g2', adjustment_no: 'AJE-004' },
      { entry_group_id: 'gX', adjustment_no: 'AJE-009' },
    ]
    const entries = [
      { entry_group_id: 'g1', description: '补提存货跌价准备' },
      { entry_group_id: 'g2', description: '无编号自动分组（应收重分类计提）' },
      { entry_group_id: 'g3', description: '不相关的一笔' },
    ]
    expect(withDescriptions(rows, entries)).toEqual([
      { entry_group_id: 'g1', adjustment_no: 'AJE-003', description: '补提存货跌价准备' },
      { entry_group_id: 'g2', adjustment_no: 'AJE-004', description: '无编号自动分组（应收重分类计提）' },
      { entry_group_id: 'gX', adjustment_no: 'AJE-009' },
    ])
  })

  it('列表里摘要为空时按空值补（不会退回「找不到」的形态）', () => {
    expect(withDescriptions([{ entry_group_id: 'g1' }], [{ entry_group_id: 'g1', description: null }]))
      .toEqual([{ entry_group_id: 'g1', description: null }])
  })

  it('不改原数组与原对象', () => {
    const rows = [{ entry_group_id: 'g1', adjustment_no: 'AJE-003' }]
    const out = withDescriptions(rows, [{ entry_group_id: 'g1', description: '甲' }])
    expect(rows[0]).toEqual({ entry_group_id: 'g1', adjustment_no: 'AJE-003' })
    expect(out[0]).not.toBe(rows[0])
  })
})
