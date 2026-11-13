import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConsolTreeDiagnostic } from '@/services/consolidationApi'

const mocks = vi.hoisted(() => ({
  getWorksheetTree: vi.fn(),
  confirm: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/services/consolidationApi', () => ({
  getWorksheetTree: mocks.getWorksheetTree,
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: mocks.warning },
  ElMessageBox: { confirm: mocks.confirm },
}))

import {
  acknowledgedConflictSignature,
  conflictSessionKey,
  conflictSignature,
  confirmPushDespiteConflicts,
  rememberConflictSignature,
  shouldShowTreeConflicts,
  treeConflicts,
} from '../consolTreeConflicts'

function diagnostic(overrides: Partial<ConsolTreeDiagnostic> = {}): ConsolTreeDiagnostic {
  return {
    code: 'duplicate_project',
    message: '企业代码 911100002000000005 存在重复项目',
    company_code: '911100002000000005',
    node_key: null,
    level: 'warning',
    ...overrides,
  }
}

describe('consolTreeConflicts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  it('只筛选重复项目和关系冲突，不把其他企业树提示升级为弹窗', () => {
    const conflicts = treeConflicts([
      diagnostic(),
      diagnostic({ code: 'relation_conflict', message: '合并项目与单户项目关系不一致' }),
      diagnostic({ code: 'detached', message: '上级项目不存在' }),
      diagnostic({ code: 'relation_defaulted', message: '关系未填' }),
    ])

    expect(conflicts.map((item) => item.code)).toEqual(['duplicate_project', 'relation_conflict'])
  })

  it('诊断顺序变化不改变稳定签名，内容变化会改变签名', () => {
    const duplicate = diagnostic()
    const relation = diagnostic({ code: 'relation_conflict', message: '按单户项目取值' })

    expect(conflictSignature([duplicate, relation])).toBe(conflictSignature([relation, duplicate]))
    expect(conflictSignature([duplicate, relation])).not.toBe(
      conflictSignature([duplicate, { ...relation, message: '按合并项目取值' }]),
    )
    expect(conflictSessionKey('project-1', 2025)).toBe('gt:consol-tree-conflicts:project-1:2025')
  })

  it('会话存储按项目和年度保存已确认签名', () => {
    const signature = conflictSignature([diagnostic()])

    rememberConflictSignature('project-1', 2025, signature)

    expect(acknowledgedConflictSignature('project-1', 2025)).toBe(signature)
    expect(acknowledgedConflictSignature('project-2', 2025)).toBeNull()
    expect(acknowledgedConflictSignature('project-1', 2024)).toBeNull()
  })

  it('工作台首次加载冲突时弹出，确认后同签名不再弹，签名变化重新弹出', () => {
    const conflicts = [diagnostic()]
    const signature = conflictSignature(conflicts)

    expect(shouldShowTreeConflicts('project-1', 2025, conflicts)).toBe(true)
    rememberConflictSignature('project-1', 2025, signature)
    expect(shouldShowTreeConflicts('project-1', 2025, conflicts)).toBe(false)
    expect(shouldShowTreeConflicts('project-1', 2025, [
      { ...conflicts[0], message: '企业树按合并项目取值' },
    ])).toBe(true)
    expect(shouldShowTreeConflicts('project-1', 2025, [diagnostic({ code: 'detached' })])).toBe(false)
  })

  it('没有项目或只有其他诊断时不弹出', () => {
    expect(shouldShowTreeConflicts(null, 2025, [diagnostic()])).toBe(false)
    expect(shouldShowTreeConflicts('project-1', 2025, [diagnostic({ code: 'detached' })])).toBe(false)
  })

  it('没有冲突时不弹窗并允许推送', async () => {
    mocks.getWorksheetTree.mockResolvedValueOnce({ diagnostics: [{ code: 'detached' }] })

    await expect(confirmPushDespiteConflicts('project-1')).resolves.toBe(true)

    expect(mocks.confirm).not.toHaveBeenCalled()
    expect(mocks.warning).not.toHaveBeenCalled()
  })

  it('有冲突时确认继续推送，取消则阻止推送', async () => {
    mocks.getWorksheetTree.mockResolvedValueOnce({ diagnostics: [diagnostic()] })
    mocks.confirm.mockResolvedValueOnce('confirm')
    await expect(confirmPushDespiteConflicts('project-1')).resolves.toBe(true)
    expect(mocks.confirm).toHaveBeenCalledOnce()

    mocks.getWorksheetTree.mockResolvedValueOnce({ diagnostics: [diagnostic()] })
    mocks.confirm.mockRejectedValueOnce('cancel')
    await expect(confirmPushDespiteConflicts('project-1')).resolves.toBe(false)
  })

  it('读取诊断失败时放行推送并提示未能检查', async () => {
    mocks.getWorksheetTree.mockRejectedValueOnce(new Error('network down'))

    await expect(confirmPushDespiteConflicts('project-1')).resolves.toBe(true)

    expect(mocks.warning).toHaveBeenCalledWith('未能检查企业树冲突，已继续推送')
    expect(mocks.confirm).not.toHaveBeenCalled()
  })
})
