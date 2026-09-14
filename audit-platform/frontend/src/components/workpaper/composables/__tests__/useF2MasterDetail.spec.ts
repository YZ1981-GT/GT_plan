/**
 * useF2MasterDetail — 导入后 remark 变更应刷新实体列表
 */
import { describe, it, expect } from 'vitest'
import { ref, nextTick } from 'vue'
import { useF2MasterDetail } from '../useF2MasterDetail'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('useF2MasterDetail', () => {
  it('F2-70 导入后 remark 变更刷新左侧列表', async () => {
    const kind = ref<'supplier-info' | 'interview'>('supplier-info')
    const map = ref(new Map<string, ChecklistResponse>())
    const md = useF2MasterDetail({
      kind,
      allResponses: map,
      isReadonly: ref(true),
    })

    expect(md.entityList.value).toHaveLength(1)

    const imported = [{
      id: 's1',
      supplierName: '导入供应商',
      creditCode: '',
      legalRepresentative: '',
      registeredCapital: '',
      establishDate: '',
      businessScope: '',
      operatingAddress: '',
      employeeCount: 0,
      mainCustomers: '',
      financialStatus: '',
      cooperationYears: 0,
      transactionAmount: 0,
      checkMethod: '',
      checkConclusion: '',
    }]
    map.value = new Map([
      ['F2-70-entities', {
        item_id: 'F2-70-entities',
        conclusion: null,
        remark: JSON.stringify(imported),
      }],
    ])
    await nextTick()

    expect(md.entityList.value).toHaveLength(1)
    expect(md.entityList.value[0].supplierName).toBe('导入供应商')
    expect(md.currentId.value).toBe('s1')
  })
})
