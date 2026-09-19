/**
 * Unit Tests — K1-9 转回/核销检查表 composable
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useK1WriteoffCheck,
  getMissingK1ReversalFields,
  getMissingK1WriteoffFields,
  importWriteoffFromK13,
  loadK11RelatedPartyNames,
  syncWriteoffRelatedPartyFromK11,
  parseK13BadDebtRows,
  type K1ReversalRow,
  type K1WriteoffRow,
} from '../../../composables/useK1WriteoffCheck'
import { isReversalExceedsProvision } from '../../../composables/useD1WriteoffCheck'

function createComposable(responses: Record<string, any> = {}) {
  const map = new Map<string, any>(Object.entries(responses))
  const allResponses = ref(map)
  return { ...useK1WriteoffCheck({ allResponses: allResponses as any }), allResponses }
}

describe('useK1WriteoffCheck', () => {
  it('reversalTotal 正确合计', () => {
    const legacy = JSON.stringify({
      tables: {
        reversal: [
          { id: '1', unit: 'A', amount: 1000, accumProvision: 2000 },
          { id: '2', unit: 'B', amount: 500, accumProvision: 800 },
        ],
        writeoff: [],
      },
    })
    const { reversalTotal, load } = createComposable({ 'K1-9-writeoff': { remark: legacy } })
    load()
    expect(reversalTotal.value).toBe(1500)
  })

  it('与 K1-3 转回差异计算', () => {
    const k13 = JSON.stringify([
      { id: 'x', label: '客户A', reversal: 800, writeoff: 200 },
      { id: 'y', label: '客户B', reversal: 200, writeoff: 0 },
    ])
    const legacy = JSON.stringify({
      tables: { reversal: [{ id: '1', amount: 900 }], writeoff: [{ id: '2', amount: 150 }] },
    })
    const { load, reversalDiff, writeoffDiff, reversalConsistencyWarning } = createComposable({
      'K1-9-writeoff': { remark: legacy },
      'K1-3-baddebt-rows': { remark: k13 },
    })
    load()
    expect(reversalDiff.value).toBe(-100)
    expect(writeoffDiff.value).toBe(-50)
    expect(reversalConsistencyWarning.value).toContain('差异')
  })

  it('buildSavePayload 写出合计 keys', () => {
    const { reversalRows, writeoffRows, buildSavePayload, load } = createComposable()
    load()
    reversalRows.value = [{ id: '1', unit: '', reason: '', method: '', basis: '', amount: 300, accumProvision: 0, isReasonable: '', analysis: '', indexNo: '' }]
    writeoffRows.value = [{ id: '2', unit: '', nature: '', amount: 100, reason: '', procedure: '', relatedParty: '', isReasonable: '', analysis: '', indexNo: '' }]
    const { totals } = buildSavePayload()
    expect(totals.find((t) => t.item_id === 'K1-9-reversal-total')?.remark).toBe('300')
    expect(totals.find((t) => t.item_id === 'K1-9-writeoff-total')?.remark).toBe('100')
  })
})

describe('K1 行级校验', () => {
  it('转回金额超原计提预警', () => {
    expect(isReversalExceedsProvision(5000, 3000)).toBe(true)
    expect(isReversalExceedsProvision(1000, 3000)).toBe(false)
  })

  it('missingReversalFields: 有金额时 reason/analysis 必填', () => {
    const row: K1ReversalRow = {
      id: '1', unit: '', reason: '', method: '', basis: '', amount: 200,
      accumProvision: 0, isReasonable: '', analysis: '', indexNo: '',
    }
    expect(getMissingK1ReversalFields(row)).toEqual(['reason', 'reasonabilityAnalysis'])
  })

  it('missingWriteoffFields: 有金额时 reason/procedure/analysis 必填', () => {
    const row: K1WriteoffRow = {
      id: '1', unit: '', nature: '', amount: 100, reason: '', procedure: '',
      relatedParty: '', isReasonable: '', analysis: '', indexNo: '',
    }
    expect(getMissingK1WriteoffFields(row)).toEqual(['writeoffReason', 'writeoffProcedure', 'reasonabilityAnalysis'])
  })
})

describe('K1-3 / K1-11 跨表导入', () => {
  it('importWriteoffFromK13 按单位合并并带入关联方标记', () => {
    const k13 = parseK13BadDebtRows(JSON.stringify([
      { id: 'a', label: '甲公司', reversal: 1000, writeoff: 0, endBadDebt: 0, remark: '账龄组合' },
      { id: 'b', label: '乙公司', reversal: 0, writeoff: 500, endBadDebt: 0, remark: '押金' },
    ]))
    const reversal: K1ReversalRow[] = []
    const writeoff: K1WriteoffRow[] = []
    const k11 = new Set(['乙公司'])
    const r = importWriteoffFromK13(reversal, writeoff, k13, k11)
    expect(r.reversalAdded).toBe(1)
    expect(r.writeoffAdded).toBe(1)
    expect(reversal[0].unit).toBe('甲公司')
    expect(reversal[0].amount).toBe(1000)
    expect(writeoff[0].relatedParty).toBe('是')
  })

  it('syncWriteoffRelatedPartyFromK11 仅补「是」', () => {
    const map = new Map([['K1-11-related-party', {
      remark: JSON.stringify({ tables: { rows: [{ name: '关联方A' }] } }),
    }]])
    const names = loadK11RelatedPartyNames(map)
    const rows: K1WriteoffRow[] = [
      { id: '1', unit: '关联方A', nature: '', amount: 100, reason: '', procedure: '', relatedParty: '', isReasonable: '', analysis: '', indexNo: '' },
      { id: '2', unit: '第三方B', nature: '', amount: 200, reason: '', procedure: '', relatedParty: '否', isReasonable: '', analysis: '', indexNo: '' },
    ]
    expect(syncWriteoffRelatedPartyFromK11(rows, names)).toBe(1)
    expect(rows[0].relatedParty).toBe('是')
    expect(rows[1].relatedParty).toBe('否')
  })
})
