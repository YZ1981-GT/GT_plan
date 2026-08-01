/**
 * useK1DetailAutoSeed 单测.
 *
 * spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
 * Requirements 1.7, 12.2 / Property 2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { post: vi.fn() },
}))

import http from '@/utils/http'
import {
  K1_DETAIL_ITEM_ID,
  shouldAutoSeedK1Detail,
  autoSeedK1DetailFromAux,
} from '../useK1DetailAutoSeed'

describe('shouldAutoSeedK1Detail', () => {
  it('缺失键 → true', () => {
    expect(shouldAutoSeedK1Detail(new Map())).toBe(true)
  })

  it('空数组 → true', () => {
    const m = new Map([[K1_DETAIL_ITEM_ID, { remark: JSON.stringify([]) }]])
    expect(shouldAutoSeedK1Detail(m)).toBe(true)
  })

  it('非法 JSON → true（保守：宁可尝试归集）', () => {
    const m = new Map([[K1_DETAIL_ITEM_ID, { remark: '{not json' }]])
    expect(shouldAutoSeedK1Detail(m)).toBe(true)
  })

  it('非数组对象 → true', () => {
    const m = new Map([[K1_DETAIL_ITEM_ID, { remark: JSON.stringify({ a: 1 }) }]])
    expect(shouldAutoSeedK1Detail(m)).toBe(true)
  })

  it('非空数组 → false（不覆盖已有数据）', () => {
    const m = new Map([[K1_DETAIL_ITEM_ID, { remark: JSON.stringify([{ id: '1' }]) }]])
    expect(shouldAutoSeedK1Detail(m)).toBe(false)
  })
})

describe('autoSeedK1DetailFromAux', () => {
  beforeEach(() => {
    vi.mocked(http.post).mockReset()
  })

  it('空表 + 无 wpId → 跳过', async () => {
    const reload = vi.fn()
    const out = await autoSeedK1DetailFromAux({ wpId: '', allResponses: new Map(), reload })
    expect(out.skipped).toBe(true)
    expect(reload).not.toHaveBeenCalled()
    expect(http.post).not.toHaveBeenCalled()
  })

  it('非空表 → 跳过，不调端点', async () => {
    const reload = vi.fn()
    const m = new Map([[K1_DETAIL_ITEM_ID, { remark: JSON.stringify([{ id: '1' }]) }]])
    const out = await autoSeedK1DetailFromAux({ wpId: 'wp-1', allResponses: m, reload })
    expect(out.skipped).toBe(true)
    expect(http.post).not.toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
  })

  it('空表 + 归集成功（imported>0） → 调端点一次 + reload 一次', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { data: { imported_count: 3, message: 'ok' } },
    })
    const reload = vi.fn().mockResolvedValue(undefined)
    const out = await autoSeedK1DetailFromAux({ wpId: 'wp-1', allResponses: new Map(), reload })
    expect(http.post).toHaveBeenCalledTimes(1)
    expect(http.post).toHaveBeenCalledWith(
      '/api/workpapers/wp-1/k1/import-aux-balance',
      null,
      expect.anything(),
    )
    expect(reload).toHaveBeenCalledTimes(1)
    expect(out).toEqual({ imported: 3, skipped: false, message: 'ok' })
  })

  it('空表 + 归集为 0 → 调端点但不 reload', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { data: { imported_count: 0, message: '未找到科目1221的辅助余额数据' } },
    })
    const reload = vi.fn()
    const out = await autoSeedK1DetailFromAux({ wpId: 'wp-1', allResponses: new Map(), reload })
    expect(reload).not.toHaveBeenCalled()
    expect(out.imported).toBe(0)
  })

  it('端点抛错 → 静默返回，不抛出、不调 reload', async () => {
    vi.mocked(http.post).mockRejectedValue(new Error('network down'))
    const reload = vi.fn()
    const out = await autoSeedK1DetailFromAux({ wpId: 'wp-1', allResponses: new Map(), reload })
    expect(out).toEqual({ imported: 0, skipped: false })
    expect(reload).not.toHaveBeenCalled()
  })
})
