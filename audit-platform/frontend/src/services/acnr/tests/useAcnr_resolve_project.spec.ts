/**
 * useAcnr 的 resolveFormula / resolveUri 带项目上下文（spec formula-fetch-followup-defect-closure R5.4）。
 *
 * 后端对试算表 / 报表 / 附注 / 辅助余额引用改为按项目数据判存在，不带项目只答「无法确认」（project_context_required）。
 * 原先这两个方法从不带 project_id；缓存键也不含项目 ⇒ 甲项目的「存在」会被乙项目命中。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({ default: { get: (...args: any[]) => mockGet(...args), post: vi.fn() } }))
vi.mock('vue', async () => ({ ...(await vi.importActual<typeof import('vue')>('vue')), onUnmounted: vi.fn() }))
;(globalThis as any).EventSource = class { addEventListener() {} close() {} }

async function freshAcnr(projectId?: string) {
  vi.resetModules()
  const { useAcnr } = await import('../useAcnr')
  return useAcnr(projectId)
}

describe('useAcnr resolve 带项目', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockGet.mockResolvedValue({ data: { found: true, uri: 'tb://1001#期末余额' } })
  })

  it('resolveFormula：显式项目 > 组合函数的项目；不带时不发 project_id', async () => {
    const acnr = await freshAcnr('pid-bound')
    await acnr.resolveFormula("TB('1001','期末余额')", 'pid-arg')
    expect(mockGet.mock.calls[0][1].params).toEqual({ formula_ref: "TB('1001','期末余额')", project_id: 'pid-arg' })
    await acnr.resolveFormula("TB('1002','期末余额')")
    expect(mockGet.mock.calls[1][1].params).toEqual({ formula_ref: "TB('1002','期末余额')", project_id: 'pid-bound' })
    const unbound = await freshAcnr()
    await unbound.resolveFormula("TB('1003','期末余额')")
    expect(mockGet.mock.calls[2][1].params).toEqual({ formula_ref: "TB('1003','期末余额')" })
  })

  it('resolveUri 同样带项目', async () => {
    const acnr = await freshAcnr()
    await acnr.resolveUri('tb://1001#期末余额', 'pid-1')
    expect(mockGet.mock.calls[0][1].params).toEqual({ uri: 'tb://1001#期末余额', project_id: 'pid-1' })
  })

  it('缓存按项目分开：甲项目的结果不给乙项目用', async () => {
    const acnr = await freshAcnr()
    await acnr.resolveFormula("TB('1001','期末余额')", 'pid-a')
    await acnr.resolveFormula("TB('1001','期末余额')", 'pid-a')
    expect(mockGet).toHaveBeenCalledTimes(1)
    await acnr.resolveFormula("TB('1001','期末余额')", 'pid-b')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it.each([
    ['ACNR_REGISTRY_SNAPSHOT_MISSING', 'snapshot_missing', '锁定快照缺失'],
    ['ACNR_REGISTRY_SNAPSHOT_INVALID', 'snapshot_invalid', '锁定快照损坏'],
    ['ACNR_REGISTRY_LOCK_FAILED', 'lock_failed', '目录版本锁失败'],
  ])('409 %s 保留终态分类与中文原因', async (wireCode, error, reason) => {
    mockGet.mockRejectedValue(Object.assign(new Error('409'), {
      response: { status: 409, data: { code: 409, error_code: wireCode, message: reason, detail: reason } },
    }))
    const acnr = await freshAcnr()
    await expect(acnr.resolveUri('wp://E1/E1-14#C10', 'pid-1')).resolves.toEqual({
      found: false, error, reason,
    })
    await expect(acnr.resolveFormula("WP('E1','E1-14','C10')", 'pid-1')).resolves.toEqual({
      found: false, error, reason,
    })
    await expect(acnr.resolveIndex('wp:E1', 'pid-1')).resolves.toEqual({
      found: false, error, reason,
    })
  })
})
