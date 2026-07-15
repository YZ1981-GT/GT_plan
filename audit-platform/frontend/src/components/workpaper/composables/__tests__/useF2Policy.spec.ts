/**
 * useF2Policy — F2-16 pack v2 + legacy migration
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useF2Policy } from '../useF2Policy'
import type { ChecklistResponse } from '../useF2FormData'

describe('useF2Policy F2-16 rebuild', () => {
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

  it('defaults to 6 Excel policy rows + empty cost process', () => {
    const p = setup()
    expect(p.policyRows.value).toHaveLength(6)
    expect(p.policyRows.value.map((r) => r.key)).toEqual([
      'pricing', 'nrv', 'impairment', 'count', 'amort', 'wip',
    ])
    expect(p.costProcess.value.processFlow).toBe('')
    expect(p.auditNote.value).toBe('')
  })

  it('persists updates to F2-16-policy as version 2 JSON', () => {
    const map = new Map<string, ChecklistResponse>()
    const p = useF2Policy({ allResponses: ref(map), isReadonly: ref(false) })
    p.updatePolicyRow('count', 'methodAdopted', '永续盘存制')
    p.updatePolicyRow('count', 'compliesStandard', '是')
    p.updateCostProcess('processFlow', '机加工→装配→入库')
    p.auditNote.value = '已核对政策与流程'
    p.auditConclusion.value = 'A、未见异常。'

    const stored = map.get('F2-16-policy')?.remark
    expect(stored).toBeTruthy()
    const parsed = JSON.parse(stored!)
    expect(parsed.version).toBe(2)
    expect(parsed.policyRows.find((r: any) => r.key === 'count').compliesStandard).toBe('是')
    expect(parsed.costProcess.processFlow).toContain('装配')
    expect(parsed.auditNote).toContain('政策')
    expect(parsed.auditConclusion).toContain('未见异常')
  })

  it('migrates legacy section cards into v2 rows', () => {
    const legacy = JSON.stringify([
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
    const p = setup(legacy)
    const pricing = p.policyRows.value.find((r) => r.key === 'pricing')!
    expect(pricing.methodAdopted).toBe('先进先出法')
    expect(pricing.consistentlyAdopted).toBe('否')
    expect(pricing.remark).toContain('管理层变更')
  })

  it('counts non-compliant and inconsistent rows', () => {
    const p = setup()
    p.updatePolicyRow('pricing', 'compliesStandard', '否')
    p.updatePolicyRow('nrv', 'consistentlyAdopted', '否')
    expect(p.nonCompliantCount.value).toBe(1)
    expect(p.inconsistentCount.value).toBe(1)
    expect(p.changedCount.value).toBe(1)
  })
})
