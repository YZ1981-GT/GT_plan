import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.fn()
vi.mock('@/utils/http', () => ({ default: { post: (...args: any[]) => post(...args) } }))

import {
  contractEvidenceOf,
  refreshContractEvidence,
  requestContractEvidence,
  resetContractEvidenceIndexForTest,
} from '../useContractEvidenceIndex'

// 通过公开同步读取函数验证缓存；该函数也负责首次登记。
describe('useContractEvidenceIndex', () => {
  beforeEach(() => {
    resetContractEvidenceIndexForTest()
    post.mockReset()
  })

  it('同一轮多个合同键合成一次请求，空结果也缓存', async () => {
    const k1 = '["A","甲"]'
    const k2 = '["B","乙"]'
    post.mockResolvedValueOnce({ data: { evidence: { [k1]: [{ working_paper_id: 'w2', attachments: [] }] } } })
    requestContractEvidence('p1', 'w1', k1)
    requestContractEvidence('p1', 'w1', k2)
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][0]).toBe('/api/projects/p1/workpapers/w1/evidence/contract-query')
    expect(post.mock.calls[0][1].keys).toEqual([k1, k2])
    expect(contractEvidenceOf('p1', 'w1', k1)).toHaveLength(1)
    expect(contractEvidenceOf('p1', 'w1', k2)).toEqual([])
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('失败进入显式错误态且不自动重试风暴；显式刷新覆盖旧值', async () => {
    const key = '["A","甲"]'
    post.mockRejectedValueOnce(new Error('offline'))
    requestContractEvidence('p1', 'w1', key)
    await flushPromises()
    expect(contractEvidenceOf('p1', 'w1', key)).toEqual([])
    post.mockResolvedValueOnce({ data: { evidence: { [key]: [{ working_paper_id: 'w2', attachments: [{ id: 'a1' }] }] } } })
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1) // 错误态不会在每次模板求值时自动重试
    await refreshContractEvidence('p1', 'w1', [key])
    expect(post).toHaveBeenCalledTimes(2)
    expect(contractEvidenceOf('p1', 'w1', key)[0].attachments[0].id).toBe('a1')

    post.mockResolvedValueOnce({ data: { evidence: { [key]: [] } } })
    await refreshContractEvidence('p1', 'w1', [key])
    expect(contractEvidenceOf('p1', 'w1', key)).toEqual([])
  })

  it('晚到旧响应不能覆盖新刷新结果', async () => {
    const key = '["A","甲"]'
    let releaseOld!: (value: any) => void
    post.mockImplementationOnce(() => new Promise(resolve => { releaseOld = resolve }))
    requestContractEvidence('p1', 'w1', key)
    await Promise.resolve()
    post.mockResolvedValueOnce({ data: { evidence: { [key]: [{ working_paper_id: 'new', attachments: [] }] } } })
    await refreshContractEvidence('p1', 'w1', [key])
    releaseOld({ data: { evidence: { [key]: [{ working_paper_id: 'old', attachments: [] }] } } })
    await flushPromises()
    expect(contractEvidenceOf('p1', 'w1', key)[0].working_paper_id).toBe('new')
  })
})


describe('合同证据缓存生命周期', () => {
  beforeEach(() => {
    resetContractEvidenceIndexForTest()
    post.mockReset()
  })

  it('TTL 过期后重新查询；项目 reset 清除旧项目缓存', async () => {
    const { eventBus } = await import('@/utils/eventBus')
    let now = 1_000
    const clock = vi.spyOn(Date, 'now').mockImplementation(() => now)
    const key = '["A","甲"]'
    post.mockResolvedValue({ data: { evidence: {} } })
    requestContractEvidence('p1', 'w1', key)
    await flushPromises()
    requestContractEvidence('p1', 'w1', key)
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    now += 60_001
    requestContractEvidence('p1', 'w1', key)
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(2)
    eventBus.emit('project:reset', { reason: 'switch', projectId: 'p1' })
    requestContractEvidence('p1', 'w1', key)
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(3)
    clock.mockRestore()
  })
})
