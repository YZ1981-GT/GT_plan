import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useD5Procedure } from '../useD5Procedure'
import { D5_PROCEDURE_STEPS_CONFIG } from '../d5Constants'
import { resolveD5SheetCode } from '../useD5SheetRouting'

describe('useD5Procedure', () => {
  it('默认 8 个程序步骤', () => {
    const allResponses = ref(new Map())
    const saveImmediate = async () => {}
    const { procedureSteps, totalCount } = useD5Procedure(allResponses, saveImmediate)
    expect(totalCount.value).toBe(D5_PROCEDURE_STEPS_CONFIG.length)
    expect(procedureSteps.value[0].stepName).toBe('获取明细')
    expect(procedureSteps.value[7].stepName).toBe('结论')
  })
})

describe('resolveD5SheetCode', () => {
  it('目录 sheet 路由到 D5', () => {
    expect(resolveD5SheetCode('底稿目录')).toBe('D5')
  })

  it('审定表 D5 路由到 D5-1', () => {
    expect(resolveD5SheetCode('审定表D5')).toBe('D5-1')
  })

  it('程序表路由到 D5A', () => {
    expect(resolveD5SheetCode('应收款项融资审计程序表D5A')).toBe('D5A')
  })
})
