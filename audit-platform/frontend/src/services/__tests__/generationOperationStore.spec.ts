import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearGenerationOperation,
  generationRequestKey,
  loadGenerationOperation,
  newGenerationOperationId,
  rememberGenerationOperation,
} from '@/services/generationOperationStore'

describe('generationOperationStore', () => {
  beforeEach(() => sessionStorage.clear())

  it('请求键规范化编码顺序、大小写和重复项，并区分项目/年度/模板集', () => {
    const a = generationRequestKey({
      projectId: 'p1', templateSetId: 's1', year: 2025, codes: [' d2 ', 'A1', 'D2'],
    })
    const b = generationRequestKey({
      projectId: 'p1', templateSetId: 's1', year: 2025, codes: ['A1', 'D2'],
    })
    expect(a).toBe(b)
    expect(a).not.toBe(generationRequestKey({
      projectId: 'p1', templateSetId: 's1', year: 2024, codes: ['A1', 'D2'],
    }))
  })

  it('只为同项目同请求恢复 operation，清理不会误删另一个 id', () => {
    const value = {
      projectId: 'p1', operationId: 'op-1', requestKey: 'r1',
      templateSetId: 's1', year: 2025, codes: ['D2'], savedAt: 1,
    }
    rememberGenerationOperation(value)
    expect(loadGenerationOperation('p1', 'r1')).toEqual(value)
    expect(loadGenerationOperation('p1', 'other')).toBeNull()
    clearGenerationOperation('p1', 'other-op')
    expect(loadGenerationOperation('p1', 'r1')).toEqual(value)
    clearGenerationOperation('p1', 'op-1')
    expect(loadGenerationOperation('p1', 'r1')).toBeNull()
  })

  it('使用浏览器安全 UUID，不退化为 Math.random', () => {
    const randomUUID = vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue('00000000-0000-4000-8000-000000000001')
    expect(newGenerationOperationId()).toBe('00000000-0000-4000-8000-000000000001')
    expect(randomUUID).toHaveBeenCalledOnce()
  })
})
