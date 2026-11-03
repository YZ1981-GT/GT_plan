/**
 * 段四审计 F4-16：useConsolReportAddress / useFormulaScopeCatalog 不再用 try/catch 吞掉
 * useCurrentProjectId 的异常——取值上下文缺失由 useCurrentProjectId 内部按显式条件处理，
 * 真实错误必须冒出来，而不是被静默成「无项目、不订阅」。
 */
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/composables/useCurrentProjectId', () => ({
  useCurrentProjectId: () => {
    throw new Error('current-project-boom')
  },
}))

import { useFormulaScopeCatalog } from '@/composables/useFormulaScopeCatalog'
import { useConsolReportAddress } from '@/components/consolidation/composables/useConsolReportAddress'

describe('ACNR 消费方不吞 useCurrentProjectId 的异常', () => {
  it('useFormulaScopeCatalog 把异常原样抛出', () => {
    expect(() => useFormulaScopeCatalog()).toThrow('current-project-boom')
  })

  it('useConsolReportAddress 把异常原样抛出', () => {
    expect(() => useConsolReportAddress()).toThrow('current-project-boom')
  })
})
