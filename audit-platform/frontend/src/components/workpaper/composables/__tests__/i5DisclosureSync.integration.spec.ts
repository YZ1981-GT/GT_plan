/**
 * I5 附注 ↔ 审定双向勾稽集成测试
 */
import { describe, it, expect } from 'vitest'
import { reconcileI5DisclosureVsAdj } from '../wpDisclosureAdjReconcile'
import {
  aggregateI5DetailForDisclosure,
  summarizeI5Disclosure,
} from '../i5DisclosureModel'
import {
  buildI5ListedSubTableData,
  buildI5ListedSyncPayloads,
} from '../i5DisclosureSyncPayload'

describe('I5 disclosure ↔ adjudication sync', () => {
  it('明细聚合 → 附注载荷 → 与审定合计勾稽一致', () => {
    const detailRows = [
      {
        projectName: '预付土地出让金',
        category: '预付土地出让金',
        endBalance: 100000,
        netValue: 100000,
        beginBalance: 80000,
      },
      {
        projectName: '合同资产',
        category: '合同资产',
        endBalance: 50000,
        netValue: 45000,
        beginBalance: 40000,
      },
    ]
    const discRows = aggregateI5DetailForDisclosure(detailRows)
    const summary = summarizeI5Disclosure(discRows)
    expect(summary.endBookValue).toBe(145000)

    const adjRows = [
      { projectName: '预付土地出让金', endBalance: 100000, audited: 100000 },
      { projectName: '合同资产', endBalance: 45000, audited: 45000 },
    ]
    const map = new Map<string, any>([
      ['I5-adj-rows', { remark: JSON.stringify(adjRows) }],
      ['I5-disc-listed-rows', { remark: JSON.stringify(discRows) }],
    ])
    const recon = reconcileI5DisclosureVsAdj(map)
    expect(recon.hasBoth).toBe(true)
    expect(recon.matched).toBe(true)

    const subTable = buildI5ListedSubTableData({ rows: discRows })
    expect(subTable['其他非流动资产']?.length).toBeGreaterThan(0)

    const payloads = buildI5ListedSyncPayloads('wp-i5', ['上市'], { rows: discRows })
    expect(payloads.length).toBeGreaterThan(0)
    expect(payloads[0].section_id).toContain('31')
  })

  it('附注与审定不一致时 reconcile 报错', () => {
    const map = new Map<string, any>([
      ['I5-adj-rows', { remark: JSON.stringify([{ audited: 100 }]) }],
      ['I5-disc-listed-rows', { remark: JSON.stringify([{ endBookValue: 90, item: 'X' }]) }],
    ])
    const recon = reconcileI5DisclosureVsAdj(map)
    expect(recon.hasBoth).toBe(true)
    expect(recon.matched).toBe(false)
  })
})
