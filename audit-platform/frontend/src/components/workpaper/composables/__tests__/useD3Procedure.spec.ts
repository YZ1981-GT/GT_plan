import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useD3Procedure } from '../useD3Procedure'

describe('useD3Procedure', () => {
  it('默认 8 个程序步骤', () => {
    const allResponses = ref(new Map())
    const saveImmediate = async () => {}
    const { procedureSteps, totalCount } = useD3Procedure(allResponses, saveImmediate)
    expect(totalCount.value).toBe(8)
    expect(procedureSteps.value[0].stepName).toBe('获取明细')
    expect(procedureSteps.value[7].stepName).toBe('结论')
  })
})
