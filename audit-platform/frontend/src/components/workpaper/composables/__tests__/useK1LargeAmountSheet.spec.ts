/**
 * useK1LargeAmountSheet — K1-5 大额其他应收款情况分析表
 */
import { ref } from 'vue'
import { describe, it, expect, vi } from 'vitest'
import { useK1LargeAmountSheet, K1_LARGE_LEGACY_ROWS_KEY } from '../useK1LargeAmountSheet'
import { K1_DETAIL_STORAGE_KEY } from '../k1CrossHelpers'

function setup(rows: object[] = [], detailRows: object[] = []) {
  const map = new Map<string, any>()
  map.set('K1-5-large-amount', {
    item_id: 'K1-5-large-amount',
    remark: JSON.stringify({ rows, auditNote: '', conclusion: '', conclusionOption: '' }),
  })
  if (detailRows.length) {
    map.set(K1_DETAIL_STORAGE_KEY, {
      item_id: K1_DETAIL_STORAGE_KEY,
      remark: JSON.stringify(detailRows),
    })
  }
  map.set('K1-2-end-subtotal', { item_id: 'K1-2-end-subtotal', remark: '10000' })
  const saved = vi.fn()
  const sheet = useK1LargeAmountSheet({
    allResponses: ref(map),
    onSave: (itemId, payload) => {
      map.set(itemId, { item_id: itemId, remark: payload.remark })
      saved(itemId, payload)
    },
  })
  return { sheet, map, saved }
}

describe('useK1LargeAmountSheet', () => {
  it('computes endUnaudited and bookValue from formula', () => {
    const { sheet } = setup([
      {
        id: 'r1',
        seq: 1,
        debtorName: '甲公司',
        openingBalance: 1000,
        periodDebit: 200,
        periodCredit: 50,
        provision: 100,
      },
    ])
    const row = sheet.dataRows.value[0]
    expect(row.endUnaudited).toBe(1150)
    expect(row.bookValue).toBe(1050)
  })

  it('importTopFromDetail picks top 10 excluding related parties', () => {
    const { sheet, map } = setup([], [
      { id: 'd1', counterparty: 'A公司', beginBalance: 100, endBalance: 5000, badDebtProvision: 50, relatedParty: '否', agingAudited: { y1to2: 5000 } },
      { id: 'd2', counterparty: 'B关联方', beginBalance: 0, endBalance: 9000, badDebtProvision: 0, relatedParty: '是' },
      { id: 'd3', counterparty: 'C公司', beginBalance: 200, endBalance: 3000, badDebtProvision: 30, relatedParty: '否', agingAudited: { within1: 3000 } },
    ])
    const r = sheet.importTopFromDetail(true)
    expect(r.imported).toBe(2)
    expect(r.skippedRelated).toBe(1)
    expect(sheet.dataRows.value.map((x) => x.debtorName)).toEqual(['A公司', 'C公司'])
    expect(map.has(K1_LARGE_LEGACY_ROWS_KEY)).toBe(true)
  })

  it('displayRows includes subtotal row', () => {
    const { sheet } = setup([
      { id: 'r1', seq: 1, debtorName: 'X', openingBalance: 100, periodDebit: 0, periodCredit: 0, provision: 10 },
    ])
    const sub = sheet.displayRows.value.find((r) => r.id === '__subtotal__')!
    expect(sub.debtorName).toBe('合计')
    expect(sub.endUnaudited).toBe(100)
  })

  it('B19 match flags suspects and applyB19Match marks isRelated', () => {
    const registry = ref(['北京华为技术有限公司'])
    const map = new Map<string, any>()
    map.set('K1-5-large-amount', {
      item_id: 'K1-5-large-amount',
      remark: JSON.stringify({
        rows: [
          { id: 'r1', seq: 1, debtorName: '华为技术', isRelated: false },
          { id: 'r2', seq: 2, debtorName: '普通公司', isRelated: false },
        ],
      }),
    })
    map.set('K1-2-end-subtotal', { item_id: 'K1-2-end-subtotal', remark: '10000' })
    const saved = vi.fn()
    const sheet = useK1LargeAmountSheet({
      allResponses: ref(map),
      relatedParties: registry,
      onSave: (itemId, payload) => {
        map.set(itemId, { item_id: itemId, remark: payload.remark })
        saved(itemId, payload)
      },
    })
    expect(sheet.b19SuspectRows.value).toHaveLength(1)
    expect(sheet.b19SuspectRows.value[0].debtorName).toBe('华为技术')
    const count = sheet.applyB19Match()
    expect(count).toBe(1)
    expect(sheet.dataRows.value.find((r) => r.id === 'r1')?.isRelated).toBe(true)
  })
})
