import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useD4Procedure } from '../useD4Procedure'
import { D4_PROCEDURE_STEPS_CONFIG } from '../d4Constants'

describe('useD4Procedure', () => {
  it('默认 9 个程序步骤', () => {
    const allResponses = ref(new Map())
    const saveImmediate = async () => {}
    const { procedureSteps, totalCount } = useD4Procedure(allResponses, saveImmediate)
    expect(totalCount.value).toBe(D4_PROCEDURE_STEPS_CONFIG.length)
    expect(procedureSteps.value[0].stepName).toBe('获取明细')
    expect(procedureSteps.value[8].stepName).toBe('结论')
  })
})
