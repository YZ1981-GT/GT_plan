/**
 * pushG8FvDiffToAdjustment — 幂等覆盖
 */
import { describe, it, expect, vi } from 'vitest'
import {
  buildG8FvAdjFingerprint,
  pushG8FvDiffToAdjustment,
  G8_ADJ_KEY,
} from '../g8CrossHelpers'

describe('pushG8FvDiffToAdjustment idempotent', () => {
  it('生成稳定指纹', () => {
    const a = buildG8FvAdjFingerprint('甲公司公允差异', 1000, 'G8-4')
    const b = buildG8FvAdjFingerprint('甲公司公允差异', 1000, 'G8-4')
    expect(a).toBe(b)
    expect(a).toContain('fvfp:G8-4:')
  })

  it('重复推送同一差异不叠行', () => {
    const saves: Array<{ id: string; remark: string }> = []
    const responses = new Map<string, any>()
    const debouncedSave = (id: string, data: any) => {
      saves.push({ id, remark: String(data.remark || '') })
      responses.set(id, { remark: data.remark })
    }

    const items = [{ summary: '甲公司公允差异', amount: 500 }]
    const n1 = pushG8FvDiffToAdjustment(responses, debouncedSave, items)
    expect(n1).toBe(1)

    const afterFirst = JSON.parse(responses.get(G8_ADJ_KEY).remark)
    expect(afterFirst).toHaveLength(2) // 1503 + OCI

    const n2 = pushG8FvDiffToAdjustment(responses, debouncedSave, items)
    expect(n2).toBe(1)
    const afterSecond = JSON.parse(responses.get(G8_ADJ_KEY).remark)
    expect(afterSecond).toHaveLength(2) // 覆盖而非叠加
  })

  it('不同金额可并存', () => {
    const responses = new Map<string, any>()
    const debouncedSave = (id: string, data: any) => {
      responses.set(id, { remark: data.remark })
    }
    pushG8FvDiffToAdjustment(responses, debouncedSave, [{ summary: '甲', amount: 100 }])
    pushG8FvDiffToAdjustment(responses, debouncedSave, [{ summary: '甲', amount: 200 }])
    const rows = JSON.parse(responses.get(G8_ADJ_KEY).remark)
    expect(rows).toHaveLength(4)
  })
})
