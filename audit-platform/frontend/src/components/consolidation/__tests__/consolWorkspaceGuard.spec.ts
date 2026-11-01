import { describe, expect, it, vi } from 'vitest'
import { createConsolWorkspaceGuard } from '../composables/useConsolWorkspaceGuard'
import { useConsolWorksheetDrafts } from '../composables/useConsolWorksheetDrafts'
import { splitPersistedProjectionRows } from '../composables/consolProjectionDraft'

describe('合并工作区未保存协调器', () => {
  it('无未保存内容时直接执行切换', async () => {
    const guard = createConsolWorkspaceGuard()
    const action = vi.fn()
    guard.register({
      id: 'sheet', label: () => '工作表', contextKey: () => 'p:2025:info',
      isDirty: () => false, isSaving: () => false,
      save: vi.fn(async () => true), discard: vi.fn(),
    })

    expect(await guard.runTransition('切换', action)).toBe(true)
    expect(action).toHaveBeenCalledOnce()
    expect(guard.state.visible).toBe(false)
  })

  it('取消时不执行切换，放弃时恢复草稿后再执行', async () => {
    const guard = createConsolWorkspaceGuard()
    let dirty = true
    const discard = vi.fn(() => { dirty = false })
    guard.register({
      id: 'sheet', label: () => '基本信息表', contextKey: () => 'p:2025:info',
      isDirty: () => dirty, isSaving: () => false,
      save: vi.fn(async () => true), discard,
    })

    const cancelled = guard.runTransition('切换节点', vi.fn())
    expect(guard.state.labels).toEqual(['基本信息表'])
    guard.decide('cancel')
    expect(await cancelled).toBe(false)

    const action = vi.fn()
    const discarded = guard.runTransition('切换节点', action)
    guard.decide('discard')
    expect(await discarded).toBe(true)
    expect(discard).toHaveBeenCalledOnce()
    expect(action).toHaveBeenCalledOnce()
  })

  it('保存期间又编辑会继续串行补存，直到草稿稳定', async () => {
    const guard = createConsolWorkspaceGuard()
    let revision = 1
    let saved = 0
    const save = vi.fn(async () => {
      const attempt = revision
      if (attempt === 1) revision = 2
      saved = attempt
      return true
    })
    guard.register({
      id: 'note', label: () => '合并附注', contextKey: () => 'p:2025:n:s',
      isDirty: () => saved !== revision, isSaving: () => false,
      save, discard: vi.fn(),
    })

    const transition = guard.confirmTransition('重新汇总')
    guard.decide('save')
    expect(await transition).toBe(true)
    expect(save).toHaveBeenCalledTimes(2)
    expect(saved).toBe(2)
  })
})

describe('合并工作表草稿与汇总表读回', () => {
  it('按内容而非对象引用判断 dirty，保存和放弃都可恢复稳定状态', () => {
    const drafts = useConsolWorksheetDrafts()
    drafts.prime('info', [{ company_code: 'A', ratio: 60 }])
    drafts.update('info', [{ company_code: 'A', ratio: 60 }])
    expect(drafts.hasDirty.value).toBe(false)

    drafts.update('info', [{ company_code: 'A', ratio: 61 }])
    expect([...drafts.dirtyKeys.value]).toEqual(['info'])
    drafts.markSaved('info', [{ company_code: 'A', ratio: 61 }])
    expect(drafts.hasDirty.value).toBe(false)

    drafts.update('info', [{ company_code: 'A', ratio: 62 }])
    expect(drafts.discard('info')).toEqual([{ company_code: 'A', ratio: 61 }])
    expect(drafts.hasDirty.value).toBe(false)
  })

  it('把已保存汇总表拆成企业覆盖和手工行，不把自动列变成第二份分录事实', () => {
    const result = splitPersistedProjectionRows(
      [{ name: '甲公司', code: 'A' }],
      [
        { companyName: '甲公司', companyCode: 'A', elimCost: 30, _editable: true },
        { companyName: '特殊主体', postElimTotal: 9, _manual: true },
      ],
    )
    expect(result.overrides).toEqual({ 甲公司: { elimCost: 30 } })
    expect(result.manualRows).toEqual([
      { companyName: '特殊主体', postElimTotal: 9, _manual: true },
    ])
  })
})
