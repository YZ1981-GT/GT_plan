/**
 * g4StorageContract 单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  buildCanonicalPayload,
  buildTextPayload,
  parseCanonicalArray,
  parseCanonicalJson,
  readCanonicalRaw,
  resolveCreditLossAccount,
  G4_CREDIT_LOSS_ACCOUNT_DEFAULT,
  G4_CREDIT_LOSS_CONFIG_KEY,
} from '../g4StorageContract'
import type { ChecklistResponse } from '../useF1FormData'

describe('g4StorageContract', () => {
  it('conclusion 优先于 remark', () => {
    expect(readCanonicalRaw({ conclusion: '[1]', remark: '[2]' })).toBe('[1]')
    expect(readCanonicalRaw({ conclusion: null, remark: '[2]' })).toBe('[2]')
  })

  it('parseCanonicalArray 兼容 rows 包装', () => {
    expect(parseCanonicalArray({ conclusion: JSON.stringify([{ a: 1 }]) })).toEqual([{ a: 1 }])
    expect(parseCanonicalArray({
      conclusion: JSON.stringify({ rows: [{ a: 2 }] }),
    })).toEqual([{ a: 2 }])
  })

  it('buildCanonicalPayload 双写 conclusion+remark', () => {
    const p = buildCanonicalPayload('G4-3-rows', [{ id: '1' }])
    expect(p.item_id).toBe('G4-3-rows')
    expect(p.conclusion).toBe(JSON.stringify([{ id: '1' }]))
    expect(p.remark).toBe(p.conclusion)
  })

  it('buildTextPayload 仅写 remark', () => {
    const p = buildTextPayload('G4-1-adj-conclusion', '结论')
    expect(p.conclusion).toBeNull()
    expect(p.remark).toBe('结论')
  })

  it('resolveCreditLossAccount 默认 6702，可被配置覆盖', () => {
    expect(resolveCreditLossAccount(null)).toEqual(G4_CREDIT_LOSS_ACCOUNT_DEFAULT)
    const map = new Map<string, ChecklistResponse>()
    map.set(G4_CREDIT_LOSS_CONFIG_KEY, {
      item_id: G4_CREDIT_LOSS_CONFIG_KEY,
      conclusion: JSON.stringify({ code: '6701', name: '资产减值损失' }),
      remark: null,
    })
    expect(resolveCreditLossAccount(map).code).toBe('6701')
  })

  it('parseCanonicalJson 容错', () => {
    expect(parseCanonicalJson({ conclusion: 'not-json' })).toBeNull()
  })
})
