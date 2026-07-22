/**
 * H2-9 减少检查：验收差异 / 暂估决算 AJE 纯函数单测
 */
import { describe, expect, it } from 'vitest'
import {
  calcAcceptanceDiff,
  isMaterialAcceptanceDiff,
  evaluateRowFlags,
  buildSettlementAjePair,
  H29_AJE_MARKER,
  type H2DecreaseRow,
} from '../useH2DecreaseCheck'

function baseRow(partial: Partial<H2DecreaseRow> = {}): H2DecreaseRow {
  return {
    rowId: 'r1',
    seq: 1,
    name: '厂房工程',
    decreaseDate: '2025-06-30',
    voucherNo: '转001',
    decreaseType: '转入固定资产',
    transferToFaAmount: 1_000_000,
    transferInterestCap: 50_000,
    otherDecreaseAmount: 0,
    otherInterestCap: 0,
    approvalRef: 'SP-1',
    isApproved: '是',
    acceptanceDate: '2025-06-28',
    acceptanceAmount: 1_000_000,
    stampEngineering: '是',
    stampContractor: '是',
    stampSupervisor: '是',
    otherEvidence: '',
    queryNo: '',
    isAbnormal: '',
    isProvisional: '',
    isRelatedParty: '',
    relatedPartyName: '',
    relationship: '',
    disposalIncome: 0,
    auditConclusion: '',
    indexRef: '',
    samplingStatus: '',
    remark: '',
    ...partial,
  }
}

describe('calcAcceptanceDiff / isMaterialAcceptanceDiff', () => {
  it('both sides required', () => {
    expect(calcAcceptanceDiff({ acceptanceAmount: 0, transferToFaAmount: 100 })).toBe(0)
    expect(calcAcceptanceDiff({ acceptanceAmount: 100, transferToFaAmount: 0 })).toBe(0)
  })

  it('computes signed diff', () => {
    expect(calcAcceptanceDiff({ acceptanceAmount: 1_050_000, transferToFaAmount: 1_000_000 })).toBe(50_000)
    expect(calcAcceptanceDiff({ acceptanceAmount: 900_000, transferToFaAmount: 1_000_000 })).toBe(-100_000)
  })

  it('materiality threshold uses max(1% materiality, 100)', () => {
    expect(isMaterialAcceptanceDiff(50, 0)).toBe(false)
    expect(isMaterialAcceptanceDiff(100, 0)).toBe(true)
    // materiality 100000 → threshold max(1000, 100) = 1000
    expect(isMaterialAcceptanceDiff(500, 100_000)).toBe(false)
    expect(isMaterialAcceptanceDiff(1_000, 100_000)).toBe(true)
  })
})

describe('evaluateRowFlags', () => {
  it('flags provisional settlement when acceptance differs', () => {
    const f = evaluateRowFlags(
      baseRow({ isProvisional: '是', acceptanceAmount: 1_080_000 }),
      0,
    )
    expect(f.provisionalNeedsSettlement).toBe(true)
    expect(f.acceptanceDiff).toBe(80_000)
    expect(f.messages.some(m => m.includes('暂估'))).toBe(true)
  })

  it('flags missing approval and stamps', () => {
    const f = evaluateRowFlags(
      baseRow({ isApproved: '', stampEngineering: '否', stampContractor: '是', stampSupervisor: '是' }),
      0,
    )
    expect(f.missingApproval).toBe(true)
    expect(f.missingStamps).toBe(true)
  })

  it('flags high interest ratio', () => {
    const f = evaluateRowFlags(
      baseRow({ transferInterestCap: 600_000 }),
      0,
    )
    expect(f.highInterestRatio).toBe(true)
  })
})

describe('buildSettlementAjePair', () => {
  it('positive diff: Dr FA / Cr CIP', () => {
    const pair = buildSettlementAjePair({
      projectName: '厂房工程',
      diff: 50_000,
      seqStart: 1,
      kind: 'provisional',
    })
    expect(pair).toHaveLength(2)
    expect(pair[0].accountCode).toBe('1601')
    expect(pair[0].debit).toBe(50_000)
    expect(pair[1].accountCode).toBe('1604')
    expect(pair[1].credit).toBe(50_000)
    expect(pair[0].remark).toBe(H29_AJE_MARKER)
    expect(pair[0].description).toContain('不调折旧')
  })

  it('negative diff: Dr CIP / Cr FA', () => {
    const pair = buildSettlementAjePair({
      projectName: '厂房工程',
      diff: -20_000,
      seqStart: 3,
      kind: 'acceptance',
    })
    expect(pair[0].accountCode).toBe('1604')
    expect(pair[0].debit).toBe(20_000)
    expect(pair[1].accountCode).toBe('1601')
    expect(pair[1].credit).toBe(20_000)
  })

  it('zero diff yields empty', () => {
    expect(buildSettlementAjePair({
      projectName: 'x',
      diff: 0,
      seqStart: 1,
      kind: 'acceptance',
    })).toEqual([])
  })
})
