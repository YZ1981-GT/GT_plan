import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useD7Procedure } from '../useD7Procedure'
import { D7_PROCEDURE_STEPS_CONFIG } from '../d7Constants'
import { resolveD7SheetCode } from '../useD7SheetRouting'

describe('useD7Procedure', () => {
  it('默认 8 个程序步骤', () => {
    const allResponses = ref(new Map())
    const saveImmediate = async () => {}
    const { procedureSteps, totalCount } = useD7Procedure(allResponses, saveImmediate)
    expect(totalCount.value).toBe(D7_PROCEDURE_STEPS_CONFIG.length)
    expect(procedureSteps.value[0].stepName).toBe('获取明细')
    expect(procedureSteps.value[7].stepName).toBe('结论')
  })
})

describe('resolveD7SheetCode', () => {
  it('目录 sheet 路由到 D7', () => {
    expect(resolveD7SheetCode('底稿目录')).toBe('D7')
  })

  it('审定表 D7 路由到 D7-1', () => {
    expect(resolveD7SheetCode('合同负债审定表D7-1')).toBe('D7-1')
  })

  it('程序表路由到 D7A', () => {
    expect(resolveD7SheetCode('合同负债审计程序表D7A')).toBe('D7A')
  })
})
