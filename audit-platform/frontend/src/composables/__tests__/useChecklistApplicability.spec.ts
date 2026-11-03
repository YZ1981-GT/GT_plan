/**
 * 核对表章节适用性确认（spec attachment-archive-and-a-class-evidence 走查实测，A30 归档检查表）：
 * 原先只存改过的章节 ⇒ 首次弹窗直接确认「全部适用」什么都不存，之后每次打开都再弹。
 */
import { describe, it, expect, vi } from 'vitest'
import { useChecklistApplicability } from '../useChecklistApplicability'

function setup(readonly = false) {
  const markPending = vi.fn()
  const scheduleSave = vi.fn()
  const api = useChecklistApplicability({
    readonly: () => readonly, markPending, scheduleSave, sectionIds: () => ['S-A', 'S-B', 'S-C'],
  })
  return { api, markPending, scheduleSave }
}

describe('useChecklistApplicability · confirmApplicability', () => {
  it('没改过的章节按「适用」一并落库，改过的保持', () => {
    const { api, markPending, scheduleSave } = setup()
    api.showApplicabilityDialog.value = true
    api.toggleSectionApplicability('S-B') // 改成不适用
    api.confirmApplicability()
    expect(api.showApplicabilityDialog.value).toBe(false)
    expect(api.sectionApplicability.value).toEqual({ 'S-A': true, 'S-B': false, 'S-C': true })
    expect(markPending.mock.calls.map((c) => c[0]).sort()).toEqual(['TOC-S-A', 'TOC-S-B', 'TOC-S-C'])
    expect(scheduleSave).toHaveBeenCalledTimes(1)
  })

  it('只读：关弹窗、不标记不保存', () => {
    const { api, markPending, scheduleSave } = setup(true)
    api.showApplicabilityDialog.value = true
    api.confirmApplicability()
    expect(api.showApplicabilityDialog.value).toBe(false)
    expect(api.sectionApplicability.value).toEqual({})
    expect(markPending).not.toHaveBeenCalled()
    expect(scheduleSave).not.toHaveBeenCalled()
  })
})
