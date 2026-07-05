import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useD6Procedure } from '../useD6Procedure'
import { D6_PROCEDURE_STEPS_CONFIG } from '../d6Constants'
import { resolveD6SheetCode } from '../useD6SheetRouting'

describe('useD6Procedure', () => {
  it('默认 8 个程序步骤', () => {
    const allResponses = ref(new Map())
    const saveImmediate = async () => {}
    const { procedureSteps, totalCount } = useD6Procedure(allResponses, saveImmediate)
    expect(totalCount.value).toBe(D6_PROCEDURE_STEPS_CONFIG.length)
    expect(procedureSteps.value[0].stepName).toBe('获取明细')
    expect(procedureSteps.value[7].stepName).toBe('结论')
  })
})

describe('resolveD6SheetCode', () => {
  it('目录 sheet 路由到 D6', () => {
    expect(resolveD6SheetCode('底稿目录')).toBe('D6')
  })

  it('审定表 D6 路由到 D6-1', () => {
    expect(resolveD6SheetCode('合同资产审定表D6-1')).toBe('D6-1')
  })

  it('程序表路由到 D6A', () => {
    expect(resolveD6SheetCode('实质性程序表D6A')).toBe('D6A')
  })
})
