import { describe, expect, it } from 'vitest'
import { evaluateG4SuiteStatus } from '../g4SuiteStatus'
import { buildCanonicalPayload, buildTextPayload, G4_ITEM_IDS } from '../g4StorageContract'
import type { ChecklistResponse } from '../useF1FormData'

function responseMap(items: ChecklistResponse[]): Map<string, ChecklistResponse> {
  return new Map(items.map((item) => [item.item_id, item]))
}

describe('evaluateG4SuiteStatus', () => {
  it('识别 G4-3 借贷平衡和结论完成', () => {
    const map = responseMap([
      buildCanonicalPayload(G4_ITEM_IDS.G4_3_ROWS, [
        { debitAmount: 100, creditAmount: 0 },
        { debitAmount: 0, creditAmount: 100 },
      ]),
      buildTextPayload('G4-3-audit-conclusion', '调整完整'),
    ])
    const status = evaluateG4SuiteStatus(map).find((item) => item.code === 'G4-3')!
    expect(status.hasData).toBe(true)
    expect(status.balance).toBe(true)
    expect(status.conclusionComplete).toBe(true)
    expect(status.tone).toBe('ok')
  })

  it('识别 G4-8 未解释差异', () => {
    const map = responseMap([
      buildCanonicalPayload(G4_ITEM_IDS.G4_8_ITEMS, [
        { variance: 10, varianceQuantity: 0, remark: '' },
      ]),
    ])
    const status = evaluateG4SuiteStatus(map).find((item) => item.code === 'G4-8')!
    expect(status.gate).toBe(false)
    expect(status.issues).toContain('质量闸门待处理')
  })

  it('识别 G4-12 闸门和 G4-13 异常说明/借贷平衡', () => {
    const map = responseMap([
      buildCanonicalPayload(G4_ITEM_IDS.G4_12_ROWS, {
        reversals: [{ reversalAmount: 20, accumulatedProvision: 10, isReasonable: '合理' }],
        writeOffs: [],
      }),
      buildCanonicalPayload(G4_ITEM_IDS.G4_13_ROWS, [
        { debitAmount: 80, creditAmount: 70, isAbnormal: true, abnormalNote: '' },
      ]),
    ])
    const statuses = evaluateG4SuiteStatus(map)
    expect(statuses.find((item) => item.code === 'G4-12')?.gate).toBe(false)
    expect(statuses.find((item) => item.code === 'G4-13')).toMatchObject({
      gate: false,
      balance: false,
    })
  })

  it('始终返回 G4A 与 G4-1 至 G4-13', () => {
    const statuses = evaluateG4SuiteStatus(new Map())
    expect(statuses).toHaveLength(14)
    expect(statuses[0].code).toBe('G4A')
    expect(statuses.at(-1)?.code).toBe('G4-13')
  })
})
