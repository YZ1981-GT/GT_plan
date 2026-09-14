/**
 * useSamplingMethodologyPersist 守卫（sampling-compliance-closure Wave 3 Task 19 前置）
 *
 * Validates: Requirements 6.3
 * Properties: Property 15
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import { useSamplingMethodologyPersist } from '../useSamplingMethodologyPersist'
import { serializeMethodology, type SamplingMethodologySnapshot } from '../samplingFillTarget'

function makeMethodology(
  over: Partial<SamplingMethodologySnapshot> = {},
): SamplingMethodologySnapshot {
  return {
    samplingMethod: 'systematic',
    samplingInterval: '10000',
    sampleSize: 12,
    suggestedSampleSize: 12,
    tolerableMisstatement: 500000,
    expectedMisstatement: 0,
    confidenceLevel: 0.95,
    accountCodes: ['2203'],
    randomSeed: '42',
    batchId: 'batch-0001',
    datasetId: 'ds-0001',
    ...over,
  }
}

function setup(over: { readonly?: boolean } = {}) {
  const allResponses = ref(new Map<string, { remark?: string | null }>())
  const persist = vi.fn(async (itemId: string, remark: string) => {
    allResponses.value.set(itemId, { remark })
  })
  const api = useSamplingMethodologyPersist({
    wpCode: 'D3',
    allResponses,
    persist,
    isReadonly: computed(() => over.readonly === true),
  })
  return { allResponses, persist, api }
}

describe('键名', () => {
  it('按底稿编码构键', () => {
    expect(setup().api.methodologyItemKey.value).toBe('D3-sampling-methodology')
  })

  it('wpCode 为 ref 时随之变化', async () => {
    const wpCode = ref('F3')
    const api = useSamplingMethodologyPersist({
      wpCode,
      allResponses: ref(new Map()),
      persist: vi.fn(),
    })
    expect(api.methodologyItemKey.value).toBe('F3-sampling-methodology')
    wpCode.value = 'F4'
    await nextTick()
    expect(api.methodologyItemKey.value).toBe('F4-sampling-methodology')
  })
})

describe('落库', () => {
  it('写入后可读回，且经 allResponses 触发 computed 更新', async () => {
    const { api, persist } = setup()
    expect(api.methodology.value).toBeNull()
    const m = makeMethodology()
    await expect(api.persistMethodology(m)).resolves.toBe(true)
    expect(persist).toHaveBeenCalledWith('D3-sampling-methodology', serializeMethodology(m))
    expect(api.methodology.value).toEqual(m)
  })

  it('只读态不写库（复核锁定后不得改留痕）', async () => {
    const { api, persist } = setup({ readonly: true })
    await expect(api.persistMethodology(makeMethodology())).resolves.toBe(false)
    expect(persist).not.toHaveBeenCalled()
  })

  it('无实质内容不写空壳（「没抽过样」与「抽了没留痕」必须可区分）', async () => {
    const { api, persist } = setup()
    for (const bad of [null, undefined, {} as SamplingMethodologySnapshot]) {
      await expect(api.persistMethodology(bad)).resolves.toBe(false)
    }
    expect(persist).not.toHaveBeenCalled()
  })

  it('持久化抛错不被吞（静默失败会让审计师以为已留痕）', async () => {
    const allResponses = ref(new Map<string, { remark?: string | null }>())
    const api = useSamplingMethodologyPersist({
      wpCode: 'D3',
      allResponses,
      persist: () => {
        throw new Error('落库失败')
      },
    })
    await expect(api.persistMethodology(makeMethodology())).rejects.toThrow('落库失败')
  })
})

describe('读回', () => {
  it('脏 JSON 返回 null 而非半个对象（bar 据此不渲染）', () => {
    const { allResponses, api } = setup()
    allResponses.value.set('D3-sampling-methodology', { remark: '{bad json' })
    expect(api.methodology.value).toBeNull()
  })

  it('键不存在返回 null', () => {
    expect(setup().api.methodology.value).toBeNull()
  })

  it('不串键：别的底稿的方法学不会被读进来', async () => {
    const { allResponses, api } = setup()
    allResponses.value.set('F3-sampling-methodology', {
      remark: serializeMethodology(makeMethodology()),
    })
    expect(api.methodology.value).toBeNull()
  })
})
