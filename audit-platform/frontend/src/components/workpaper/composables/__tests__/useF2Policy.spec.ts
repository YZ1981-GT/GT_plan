/**
 * useF2Policy — F2-16 会计政策（与 useF2Policy / F2TabPolicy 现行 API 对齐）
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useF2Policy } from '../useF2Policy'
import type { ChecklistResponse } from '../useF2FormData'

describe('useF2Policy F2-16', () => {
  let handler: EventListener

  beforeEach(() => {
    handler = (() => {}) as EventListener
    window.addEventListener('f2:save-items', handler)
  })

  afterEach(() => {
    window.removeEventListener('f2:save-items', handler)
  })

  function setup(remark?: string) {
    const map = new Map<string, ChecklistResponse>()
    if (remark != null) {
      map.set('F2-16-policy', { item_id: 'F2-16-policy', conclusion: null, remark })
    }
    return useF2Policy({ allResponses: ref(map), isReadonly: ref(false) })
  }

  it('defaults to 5 policy sections', () => {
    const p = setup()
    expect(p.sections.value).toHaveLength(5)
    expect(p.sections.value.map((r) => r.key)).toEqual([
      'classification', 'initial', 'pricing', 'impairment', 'count',
    ])
    expect(p.policyConclusion.value).toBe('')
  })

  it('persists section updates to F2-16-policy JSON', () => {
    const map = new Map<string, ChecklistResponse>()
    const p = useF2Policy({ allResponses: ref(map), isReadonly: ref(false) })
    p.updateSection('count', 'policyDesc', '永续盘存制')
    p.updateSection('count', 'isChanged', '是')
    p.updateConclusion('A、未见异常。')

    const stored = map.get('F2-16-policy')?.remark
    expect(stored).toBeTruthy()
    const parsed = JSON.parse(stored!)
    expect(Array.isArray(parsed)).toBe(true)
    expect(parsed.find((r: any) => r.key === 'count').policyDesc).toContain('永续')
    expect(map.get('F2-16-conclusion')?.remark).toContain('未见异常')
  })

  it('hydrates saved section cards', () => {
    const saved = JSON.stringify([
      {
        key: 'pricing',
        title: '发出存货计价方法',
        policyDesc: '先进先出法',
        isChanged: '是',
        changeReason: '管理层变更',
        auditEval: '变更依据不足',
        indexRef: '',
      },
    ])
    const p = setup(saved)
    const pricing = p.sections.value.find((r) => r.key === 'pricing')!
    expect(pricing.policyDesc).toBe('先进先出法')
    expect(pricing.isChanged).toBe('是')
    expect(pricing.changeReason).toContain('管理层变更')
  })

  it('counts changed rows', () => {
    const p = setup()
    p.updateSection('pricing', 'isChanged', '是')
    expect(p.changedCount.value).toBe(1)
  })
})
