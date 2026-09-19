/**
 * useK1OverdueCheck — K1-10 长期未收回款项检查表
 */
import { ref } from 'vue'
import { describe, it, expect, vi } from 'vitest'
import { useK1OverdueCheck } from '../useK1OverdueCheck'
import { K1_DETAIL_STORAGE_KEY } from '../k1CrossHelpers'

function setup(
  rows: object[] = [],
  detailRows: object[] = [],
  legacy = false,
) {
  const map = new Map<string, any>()
  const payload = legacy
    ? JSON.stringify({ tables: { rows }, auditNote: '', conclusion: '', conclusionOption: '' })
    : JSON.stringify({ rows, auditNote: '', conclusion: '', conclusionOption: '' })
  map.set('K1-10-overdue', { item_id: 'K1-10-overdue', conclusion: null, remark: payload })
  if (detailRows.length) {
    map.set(K1_DETAIL_STORAGE_KEY, {
      item_id: K1_DETAIL_STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(detailRows),
    })
  }
  const saved = vi.fn()
  const overdue = useK1OverdueCheck({
    projectId: ref('proj-1'),
    allResponses: ref(map),
    onSave: (itemId, payload) => {
      map.set(itemId, { item_id: itemId, conclusion: null, remark: payload.remark })
      saved(itemId, payload)
    },
  })
  return { overdue, allResponses: map, saved }
}

describe('useK1OverdueCheck', () => {
  it('computes closing balance from opening + debit - credit', () => {
    const { overdue } = setup([
      {
        id: 'r1',
        seq: 1,
        debtorName: '甲公司',
        openingBalance: 1000,
        periodDebit: 200,
        periodCredit: 50,
        aging: '1-2年',
      },
    ])
    expect(overdue.dataRows.value[0].closingBalance).toBe(1150)
  })

  it('migrates legacy tables.rows format', () => {
    const { overdue } = setup(
      [{
        id: 'legacy-1',
        debtorName: '乙公司',
        beginBalance: 500,
        debit: 100,
        credit: 0,
        aging: '2-3年',
        reason: '纠纷',
        unrecoverable: '是',
        provision: 50,
      }],
      [],
      true,
    )
    const row = overdue.dataRows.value[0]
    expect(row.debtorName).toBe('乙公司')
    expect(row.openingBalance).toBe(500)
    expect(row.unrecoveredReason).toBe('纠纷')
    expect(row.isUncollectible).toBe('是')
    expect(row.provision).toBe(50)
  })

  it('summary includes subtotal row counts', () => {
    const { overdue } = setup([
      { id: 'r1', seq: 1, debtorName: 'A', openingBalance: 100, periodDebit: 0, periodCredit: 0, aging: '1-2年', isUncollectible: '是' },
      { id: 'r2', seq: 2, debtorName: 'B', openingBalance: 200, periodDebit: 0, periodCredit: 0, aging: '1年以内', litigation: '是' },
    ])
    expect(overdue.summary.value.openingBalance).toBe(300)
    expect(overdue.summary.value.longTermCount).toBe(1)
    expect(overdue.summary.value.uncollectibleCount).toBe(1)
    expect(overdue.summary.value.litigationCount).toBe(1)
    const sub = overdue.displayRows.value.find((r) => r.id === '__subtotal__')!
    expect(sub.debtorName).toBe('合计')
  })

  it('syncAuditedFromNet sets audited = closing - provision', () => {
    const { overdue } = setup([
      {
        id: 'r1',
        seq: 1,
        debtorName: '丙公司',
        openingBalance: 100,
        periodDebit: 0,
        periodCredit: 5,
        provision: 10,
        auditedBalance: 0,
      },
    ])
    overdue.syncAuditedFromNet('r1')
    expect(overdue.dataRows.value[0].auditedBalance).toBe(85)
  })

  it('imports long-term rows from K1-2 detail', () => {
    const { overdue } = setup([], [
      {
        id: 'd1',
        counterparty: '丁公司',
        nature: '押金',
        beginBalance: 800,
        endBalance: 800,
        badDebtProvision: 100,
        stage: 2,
        agingAudited: { within1: 0, y1to2: 800, y2to3: 0 },
        remark: '长期挂账',
      },
    ])
    const r = overdue.importFromDetail()
    expect(r.imported).toBe(1)
    const row = overdue.dataRows.value.find((x) => x.debtorName === '丁公司')!
    expect(row.provision).toBe(100)
    expect(row.businessDesc).toBe('押金')
    expect(row.unrecoveredReason).toBe('长期挂账')
    expect(row.sourceRowId).toBe('d1')
    expect(overdue.getStageSuggestion(row)).toBe('Stage2')
  })

  it('syncStagesToK17 upgrades existing K1-7 row', () => {
    const k7Rows = [{
      id: 'k7-1',
      counterparty: '戊公司',
      endBalance: 500,
      stage: 1,
      sectionOneChecks: [],
      sectionTwoChecks: [],
      sectionThreeChecks: [],
    }]
    const map = new Map<string, any>()
    map.set('K1-7-stage-rows', {
      item_id: 'K1-7-stage-rows',
      remark: JSON.stringify(k7Rows),
    })
    map.set('K1-10-overdue', {
      item_id: 'K1-10-overdue',
      remark: JSON.stringify({
        rows: [{
          id: 'r1',
          seq: 1,
          debtorName: '戊公司',
          openingBalance: 500,
          periodDebit: 0,
          periodCredit: 0,
          aging: '3年以上',
          isUncollectible: '是',
        }],
        auditNote: '',
        conclusion: '',
        conclusionOption: '',
      }),
    })
    const saved = vi.fn()
    const overdue = useK1OverdueCheck({
      projectId: ref('proj-1'),
      allResponses: ref(map),
      onSave: (itemId, payload) => {
        map.set(itemId, { item_id: itemId, remark: payload.remark })
        saved(itemId, payload)
      },
    })
    overdue.syncStagesToK17()
    const k7 = JSON.parse(map.get('K1-7-stage-rows')!.remark)
    expect(k7[0].stage).toBe(3)
  })

  it('provisionReconciliation detects row mismatch vs K1-8 single', () => {
    const map = new Map<string, any>()
    map.set('K1-10-overdue', {
      item_id: 'K1-10-overdue',
      remark: JSON.stringify({
        rows: [{
          id: 'r1',
          seq: 1,
          debtorName: '己公司',
          provision: 80,
        }],
        auditNote: '',
        conclusion: '',
        conclusionOption: '',
      }),
    })
    map.set('K1-8-bad-debt-calc', {
      item_id: 'K1-8-bad-debt-calc',
      remark: JSON.stringify({
        version: 2,
        singleRows: [{
          rowId: 'si1',
          label: '己公司',
          auditedBalance: 1000,
          lossRate: 0.1,
          expectedProvision: 100,
          bookProvision: 50,
          difference: 50,
        }],
        creditGroups: [],
        agingGroups: [],
        agingPreset: 'THREE_YEAR',
        customAgingLabels: [],
        creditPreset: 'DEFAULT',
        customCreditLabels: [],
      }),
    })
    const overdue = useK1OverdueCheck({
      projectId: ref('proj-1'),
      allResponses: ref(map),
      onSave: vi.fn(),
    })
    const recon = overdue.provisionReconciliation.value
    expect(recon.hasK18Data).toBe(true)
    expect(recon.rowMismatches).toHaveLength(1)
    expect(recon.rowMismatches[0].debtorName).toBe('己公司')
    expect(recon.rowMismatches[0].diffVsBook).toBe(30)
  })
})
