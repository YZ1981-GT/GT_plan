import { afterEach, describe, expect, it, vi } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), put: vi.fn() },
}))

import { api } from '@/services/apiProxy'
import { decodeRemark, encodeRemark } from './remarkCodec'
import { useChecklistPersistence } from './useChecklistPersistence'

/**
 * `-0` 不是 JSON 可表示的值（`JSON.stringify(-0) === "0"`），任何经过 JSON
 * 序列化的往返都会把 `-0` 归一为 `0`。它落在“忠实 JSON 往返”属性的有效域之外，
 * 故从生成器中排除，避免把 JSON 规范限制误报为编解码 bug。
 */
function hasNegativeZero(value: unknown): boolean {
  if (typeof value === 'number') return Object.is(value, -0)
  if (Array.isArray(value)) return value.some(hasNegativeZero)
  if (value && typeof value === 'object') return Object.values(value).some(hasNegativeZero)
  return false
}

function isReservedLegacyEnvelope(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const keys = Object.keys(value)
  if (keys.length !== 1 || keys[0] !== 'remark') return false
  const remark = (value as { remark: unknown }).remark
  if (typeof remark !== 'string') return false
  try {
    JSON.parse(remark)
    return true
  } catch {
    return false
  }
}

function installSuccessfulApi(): void {
  vi.mocked(api.put).mockImplementation(async (_url, body: any) =>
    body.items.map((item: any) => ({ ...item, version: `v-${item.item_id}` })),
  )
}

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('Property 3: remark 编解码往返', () => {
  /** **Validates: Requirements 3.4** */
  it('P3 对任意业务 JSON 值往返等价且新写为直接单层值', () => {
    const values = fc.jsonValue().filter((value) => !isReservedLegacyEnvelope(value) && !hasNegativeZero(value))
    fc.assert(fc.property(values, (value) => {
      const encoded = encodeRemark(value)
      expect(decodeRemark(encoded)).toEqual(value)
      expect(JSON.parse(encoded)).toEqual(value)
      expect(isReservedLegacyEnvelope(JSON.parse(encoded))).toBe(false)
    }), { numRuns: 20 })
  })
  it('兼容历史双层 remark 包装且普通 remark 业务对象不丢字段', () => {
    const value = { rows: [{ amount: 12.5 }], note: '中文' }
    expect(decodeRemark(JSON.stringify({ remark: JSON.stringify(value) }))).toEqual(value)
    expect(decodeRemark({ remark: JSON.stringify(value) })).toEqual(value)
    expect(decodeRemark(encodeRemark({ remark: '普通业务字段' }))).toEqual({ remark: '普通业务字段' })
  })
})

describe('Property 4: 防抖隔离与最后写胜出', () => {
  /** **Validates: Requirements 3.5, 3.8** */
  it('P4 同 item 只提交最后值，不同 item 各自提交', async () => {
    vi.useFakeTimers()
    await fc.assert(fc.asyncProperty(
      fc.array(fc.string(), { minLength: 2, maxLength: 8 }),
      fc.array(fc.string(), { minLength: 1, maxLength: 5 }),
      async (updatesA, updatesB) => {
        vi.clearAllMocks()
        installSuccessfulApi()
        const persistence = useChecklistPersistence({ wpId: ref('wp-pbt'), debounceMs: 50 })
        for (let index = 0; index < Math.max(updatesA.length, updatesB.length); index += 1) {
          if (index < updatesA.length) persistence.saveDebounced('item-a', { remark: updatesA[index] })
          if (index < updatesB.length) persistence.saveDebounced('item-b', { remark: updatesB[index] })
        }
        await vi.runAllTimersAsync()
        const payloads = vi.mocked(api.put).mock.calls.map((call) => (call[1] as any).items[0])
        expect(payloads.filter((item) => item.item_id === 'item-a')).toEqual([
          expect.objectContaining({ remark: updatesA.at(-1) }),
        ])
        expect(payloads.filter((item) => item.item_id === 'item-b')).toEqual([
          expect.objectContaining({ remark: updatesB.at(-1) }),
        ])
      },
    ), { numRuns: 20 })
  })

  it('flush/cancel 只作用于指定 item', async () => {
    vi.useFakeTimers()
    installSuccessfulApi()
    const persistence = useChecklistPersistence({ wpId: ref('wp-unit'), debounceMs: 50 })
    persistence.saveDebounced('flush-me', { remark: 'saved' })
    persistence.saveDebounced('cancel-me', { remark: 'discarded' })
    await persistence.flush('flush-me')
    persistence.cancel('cancel-me')
    await vi.runAllTimersAsync()
    const ids = vi.mocked(api.put).mock.calls.map((call) => (call[1] as any).items[0].item_id)
    expect(ids).toEqual(['flush-me'])
    expect(persistence.stateOf('flush-me').status).toBe('saved')
    expect(persistence.stateOf('cancel-me').status).toBe('idle')
  })
})
describe('Property 5: 保存状态真实性', () => {
  /** **Validates: Requirements 3.6, 3.9** */
  it('P5 失败不标 saved，未变输入重试成功后收敛', async () => {
    await fc.assert(fc.asyncProperty(fc.string(), async (remark) => {
      vi.clearAllMocks()
      vi.mocked(api.put)
        .mockRejectedValueOnce(new Error('temporary failure'))
        .mockImplementationOnce(async (_url, body: any) => [
          { ...body.items[0], version: 'version-2' },
        ])
      const persistence = useChecklistPersistence({ wpId: ref('wp-pbt') })

      await expect(persistence.save('retry-item', { remark })).rejects.toThrow('temporary failure')
      expect(persistence.stateOf('retry-item').status).toBe('error')
      expect(persistence.stateOf('retry-item').status).not.toBe('saved')
      expect(persistence.responses.value.get('retry-item')?.remark).toBe(remark)

      await persistence.save('retry-item', { remark })
      expect(persistence.stateOf('retry-item')).toMatchObject({
        status: 'saved', serverVersion: 'version-2',
      })
      expect(persistence.responses.value.get('retry-item')?.remark).toBe(remark)
    }), { numRuns: 20 })
  })
})
