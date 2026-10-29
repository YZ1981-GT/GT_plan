import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), resolveUri: vi.fn(), resolveFormula: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post } }))
vi.mock('@/services/acnr/useAcnr', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/acnr/useAcnr')>()
  return { ...actual, useAcnr: () => ({
    resolveUri: h.resolveUri, resolveFormula: h.resolveFormula,
    listSheets: vi.fn().mockResolvedValue([]), listCells: vi.fn().mockResolvedValue([]), clearCache: vi.fn(),
  }) }
})

import { useAddressRegistry } from '../addressRegistry'

async function boundStore() {
  setActivePinia(createPinia())
  h.get.mockResolvedValueOnce({ data: { items: [] } })
  const store = useAddressRegistry()
  await store.refresh('pid-1', 2025, 'soe')
  return store
}

beforeEach(() => vi.clearAllMocks())

describe('addressRegistry 对 ACNR 版本锁 409 fail-closed', () => {
  it.each(['snapshot_missing', 'snapshot_invalid', 'lock_failed'])('%s：resolve 与 validate 都不请求 legacy', async (error) => {
    const terminal = { found: false, error, reason: `中文原因-${error}` }
    h.resolveUri.mockResolvedValue(terminal)
    h.resolveFormula.mockResolvedValue(terminal)
    const store = await boundStore()
    h.get.mockClear()
    h.post.mockClear()

    await expect(store.resolve('wp://E1/E1-14#C10')).resolves.toEqual(expect.objectContaining({
      found: false, error, reason: `中文原因-${error}`,
    }))
    await expect(store.validate("WP('E1','E1-14','C10')")).resolves.toEqual({
      valid: false,
      issues: [{ ref: "WP('E1','E1-14','C10')", message: `中文原因-${error}` }],
      formula: "WP('E1','E1-14','C10')",
    })
    expect(h.get).not.toHaveBeenCalled()
    expect(h.post).not.toHaveBeenCalled()
  })

  it('普通 miss 仍请求 legacy', async () => {
    h.resolveUri.mockResolvedValue({ found: false, error: 'not_found' })
    const store = await boundStore()
    // boundStore 里的 refresh 已经发过一次 GET（加载地址表），与上面三例一样先清掉再数
    h.get.mockClear()
    h.get.mockResolvedValueOnce({ data: { found: false, uri: 'wp://X/X#A1' } })
    await store.resolve('wp://X/X#A1')
    expect(h.get).toHaveBeenCalledTimes(1)
    expect(h.get.mock.calls[0][1]).toEqual(expect.objectContaining({
      params: expect.objectContaining({ uri: 'wp://X/X#A1', project_id: 'pid-1' }),
    }))
  })
})
