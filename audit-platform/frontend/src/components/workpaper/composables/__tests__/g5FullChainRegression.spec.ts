/**
 * G5 全链路回归：阶段同步保 V2、IE nest/flat、存储契约、写回
 */
import { describe, it, expect } from 'vitest'
import {
  applyStageUpdatesToRows,
  parseG510Payload,
} from '../useG5ImpairmentCalc'
import {
  G5_ITEM_IDS,
  buildCanonicalPayload,
  readCanonicalRaw,
  parseCanonicalJson,
} from '../g5StorageContract'
import { G5_IMPORTABLE_SHEETS } from '../useG5ImportExport'
import { evaluateG5SuiteStatus } from '../g5SuiteStatus'
import { buildG52RollForward, buildG53RollForward, buildAmortizationRollForward, buildG510RollForward } from '../useG5PriorYearRollForward'


describe('G5 full-chain regression', () => {
  it('G5-9→G5-10 sync preserves V2 credit/aging groups', () => {
    const existing = parseG510Payload({
      version: 2,
      singleRows: [
        {
          rowId: 's1',
          label: '债务人A',
          stageGroup: 'Stage1',
          auditedBalance: 100,
          lossRate: 0.01,
          expectedProvision: 1,
          bookProvision: 1,
          basis: '',
        },
      ],
      creditGroups: [
        {
          groupId: 'cg1',
          groupName: '组合1',
          rows: [{ segmentId: 'c1', label: 'AAA', balance: 50, rate: 0.02, provision: 1 }],
        },
      ],
      agingGroups: [],
    })
    const applied = applyStageUpdatesToRows(existing, [
      { debtor: '债务人A', auditStage: 'Stage2' },
      { debtor: '债务人B', auditStage: 'Stage3' },
    ])
    expect(applied.payload.version).toBe(2)
    expect(applied.payload.singleRows.find((r) => r.label === '债务人A')?.stageGroup).toBe('Stage2')
    expect(applied.payload.singleRows.some((r) => r.label === '债务人B')).toBe(true)
    expect(applied.payload.creditGroups[0].groupName).toBe('组合1')
    expect(applied.payload.creditGroups.length).toBeGreaterThan(0)
    // 不得只写 legacy rows 投影：完整 V2 可再解析
    const reparsed = parseG510Payload(JSON.parse(JSON.stringify(applied.payload)))
    expect(reparsed.version).toBe(2)
    expect(reparsed.creditGroups[0].groupName).toBe('组合1')
    expect(reparsed.singleRows.find((r) => r.label === '债务人A')?.stageGroup).toBe('Stage2')
  })

  it('canonical payload prefers conclusion over remark', () => {
    const payload = buildCanonicalPayload(G5_ITEM_IDS.G5_5_ROWS, { groups: [{ projectName: 'A' }] })
    expect(payload.conclusion).toBeTruthy()
    expect(payload.remark).toBe(payload.conclusion)
    expect(readCanonicalRaw({ conclusion: '{"ok":1}', remark: '{"old":1}' })).toBe('{"ok":1}')
    expect(parseCanonicalJson<{ groups: any[] }>(payload)?.groups[0].projectName).toBe('A')
  })

  it('IE catalog excludes G5-9/G5-10 (backend unsupported)', () => {
    expect(G5_IMPORTABLE_SHEETS).toHaveLength(9)
    const codes = G5_IMPORTABLE_SHEETS.map((s) => s.code)
    expect(codes).toEqual([
      'G5-1', 'G5-2', 'G5-3', 'G5-4', 'G5-5', 'G5-6', 'G5-7', 'G5-11', 'G5-12',
    ])
    expect(codes).not.toContain('G5-9')
    expect(codes).not.toContain('G5-10')
  })

  it('suite status flags G5-4 imbalance and G5-11 gate', () => {
    const map = new Map<string, any>([
      ['G5-4-rows', {
        item_id: 'G5-4-rows',
        conclusion: JSON.stringify([
          { debitAmount: 100, creditAmount: 40 },
        ]),
      }],
      ['G5-11-rows', {
        item_id: 'G5-11-rows',
        conclusion: JSON.stringify({
          reversal: [{ reversalAmount: 50, accumulatedProvision: 20 }],
          writeoff: [],
        }),
      }],
      ['G5-2-rows', {
        item_id: 'G5-2-rows',
        conclusion: JSON.stringify([
          { netAmount: 100, agingAudited: { within1: 60 }, agingTotal: 60 },
        ]),
      }],
    ])
    const statuses = evaluateG5SuiteStatus(map)
    expect(statuses.find((s) => s.code === 'G5-4')?.balance).toBe(false)
    expect(statuses.find((s) => s.code === 'G5-11')?.gate).toBe(false)
    expect(statuses.find((s) => s.code === 'G5-2')?.gate).toBe(false)
  })

  it('prior-year builders protect populated openings unless forced', () => {
    const priorG52 = [{
      id: 'd1',
      debtorName: '甲',
      contractNo: 'C1',
      agingAudited: { within1y: 100 },
    }]
    const currentG52 = [{
      id: 'd1',
      debtorName: '甲',
      contractNo: 'C1',
      agingPrior: { within1y: 10 },
      agingAudited: {},
    }]
    const skip = buildG52RollForward(priorG52, currentG52, false)
    expect(skip.changedRows).toBe(0)
    expect(skip.skippedRows).toBe(1)
    const forced = buildG52RollForward(priorG52, currentG52, true)
    expect(forced.changedRows).toBe(1)
    expect(forced.rows[0].agingPrior.within1y).toBe(100)

    const priorG53 = [{
      id: 'b1',
      category: 'individual',
      item: '甲',
      openingUnadjusted: 80,
      openingAdjustment: 0,
      provisionIncrease: 20,
      otherIncrease: 0,
      reversal: 0,
      writeOff: 0,
      otherDecrease: 0,
      closingAdjustment: 0,
    }]
    const currentG53 = [{
      id: 'b1',
      category: 'individual',
      item: '甲',
      openingUnadjusted: 5,
    }]
    expect(buildG53RollForward(priorG53, currentG53, false).skippedRows).toBe(1)
    const g53 = buildG53RollForward(priorG53, currentG53, true)
    expect(g53.rows[0].openingUnadjusted).toBe(100)
  })

  it('amortization roll-forward carries last closing to first opening', () => {
    const prior = {
      groups: [{
        projectName: '租赁A',
        periods: [
          { periodNo: 1, closingReceivable: 90, closingUnrealized: 8 },
          { periodNo: 2, closingReceivable: 80, closingUnrealized: 5 },
        ],
      }],
    }
    const current = {
      groups: [{
        projectName: '租赁A',
        periods: [{ periodNo: 1, openingReceivable: 0, openingUnrealized: 0 }],
      }],
    }
    const out = buildAmortizationRollForward(prior, current, false)
    expect(out.changedRows).toBe(1)
    expect((out.envelope.groups as any[])[0].periods[0].openingReceivable).toBe(80)
    expect((out.envelope.groups as any[])[0].periods[0].openingUnrealized).toBe(5)

    const skip = buildAmortizationRollForward(prior, {
      groups: [{
        projectName: '租赁A',
        periods: [{ periodNo: 1, openingReceivable: 1, openingUnrealized: 0 }],
      }],
    }, false)
    expect(skip.skippedRows).toBe(1)
  })

  it('G5-10 roll-forward sets bookProvision from prior book/expected', () => {
    const prior = {
      version: 2,
      singleRows: [{
        rowId: 's1',
        label: '债务人A',
        auditedBalance: 100,
        expectedProvision: 99, // parse 后会按余额×率重算，优先用 bookProvision
        bookProvision: 12,
        lossRate: 0.1,
      }],
      creditGroups: [],
      agingGroups: [],
    }
    const current = {
      version: 2,
      singleRows: [{
        rowId: 's1',
        label: '债务人A',
        auditedBalance: 120,
        expectedProvision: 15,
        bookProvision: 0,
        lossRate: 0.1,
      }],
      creditGroups: [],
      agingGroups: [],
    }
    const out = buildG510RollForward(prior, current, false)
    expect(out.changedRows).toBe(1)
    expect(out.payload.singleRows[0].bookProvision).toBe(12)
    expect(out.payload.creditGroups.length).toBeGreaterThan(0)
  })

  it('parseRowsRemark accepts response objects preferring conclusion', async () => {
    const { parseRowsRemark } = await import('../g5CrossHelpers')
    const rows = parseRowsRemark({
      conclusion: JSON.stringify([{ id: 1 }]),
      remark: JSON.stringify([{ id: 2 }]),
    })
    expect(rows).toEqual([{ id: 1 }])
    expect(parseRowsRemark({ remark: JSON.stringify([{ id: 3 }]) })).toEqual([{ id: 3 }])
  })

  it('parseG5Bool treats 否/FALSE as false', async () => {
    const { parseG5Bool } = await import('../useG5BalanceDetail')
    expect(parseG5Bool('否')).toBe(false)
    expect(parseG5Bool('FALSE')).toBe(false)
    expect(parseG5Bool('是')).toBe(true)
    expect(parseG5Bool(true)).toBe(true)
    expect(parseG5Bool('')).toBe(false)
  })
})
