/**
 * F2 计价/跌价组 — 跨 sheet 集成测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { calcNRV, calcImpairmentProvision } from '../useF2InvValFormulaEngine'
import { readValRowJson } from '../useF2ValuationFormData'
import type { ChecklistResponse } from '../useF2ValuationFormData'

describe('useF2ValuationIntegration', () => {
  it('NRV 与跌价计提公式链', () => {
    const nrv = calcNRV(100, 10, 5, 3)
    expect(nrv).toBeCloseTo(82, 3)
    const provision = calcImpairmentProvision(90, nrv)
    expect(provision).toBeCloseTo(8, 3)
  })

  it('F2-47 行 JSON round-trip', () => {
    const rows = [{
      rowId: 'r1', seq: 1, itemName: '甲材料', qty: 10, unitCost: 5,
      bookCost: 50, sellingPrice: 4, completionCost: 0, sellingExpense: 0,
      tax: 0, nrv: 40, requiredProvision: 10, existingProvision: 8,
      additionalProvision: 2, reversal: 0, enterpriseDiff: 0, conclusion: '',
    }]
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-47-rows', { item_id: 'F2-47-rows', conclusion: null, remark: JSON.stringify(rows) })
    const raw = readValRowJson(map.get('F2-47-rows'))
    const parsed = JSON.parse(raw!)
    expect(parsed).toHaveLength(1)
    expect(parsed[0].itemName).toBe('甲材料')
    expect(parsed[0].requiredProvision).toBe(10)
  })

  it('F2-38 计价样本 rowKey 对齐', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-38-rows', {
      item_id: 'F2-38-rows',
      conclusion: null,
      remark: JSON.stringify([{ rowId: 'v1', seq: 1, itemName: 'A', qty: 1, unitCost: 10 }]),
    })
    const raw = readValRowJson(map.get('F2-38-rows'))
    const rows = JSON.parse(raw!)
    expect(rows[0].rowId).toBe('v1')
  })
})
