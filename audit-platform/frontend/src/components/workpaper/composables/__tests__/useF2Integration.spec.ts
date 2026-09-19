/**
 * F2 跨 sheet 联动 + 导入导出 round-trip 集成测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useF2CrossSheet } from '../useF2CrossSheet'
import { calcEndAmount, calcSubtotal, calcNetValue } from '../useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from '../useF2FormData'

function detailRow(closingAmt: number, openingAmt = 0, increaseAmt = 0, decreaseAmt = 0) {
  return {
    id: String(Math.random()),
    itemName: '测试品',
    openingQty: 0,
    openingAmt,
    increaseQty: 0,
    increaseAmt,
    decreaseQty: 0,
    decreaseAmt,
    closingQty: 0,
    closingAmt,
    unitPrice: 0,
    agingLt1: 0,
    aging1to2: 0,
    aging2to3: 0,
    agingGt3: 0,
    agingTotal: 0,
  }
}

function setDetailRows(map: Map<string, ChecklistResponse>, sheet: string, rows: unknown[]) {
  map.set(`${sheet}-rows`, {
    item_id: `${sheet}-rows`,
    conclusion: null,
    remark: JSON.stringify(rows),
  })
}

describe('useF2Integration', () => {
  it('明细 F2-3 + F2-4 期末金额聚合至 crossSheet 总合计', () => {
    const map = new Map<string, ChecklistResponse>()
    setDetailRows(map, 'F2-3', [detailRow(100), detailRow(50)])
    setDetailRows(map, 'F2-4', [detailRow(200)])

    const cross = useF2CrossSheet({
      allResponses: ref(map),
      projectContext: ref({}),
    })

    expect(cross.detailGrandTotal.value).toBe(350)
    expect(cross.categorySummaries.value.find((s) => s.sheetCode === 'F2-3')?.closingAmt).toBe(150)
    expect(cross.categorySummaries.value.find((s) => s.sheetCode === 'F2-4')?.closingAmt).toBe(200)
  })

  it('明细→审定 grossCrossValidation 在一致时为 null', () => {
    const map = new Map<string, ChecklistResponse>()
    setDetailRows(map, 'F2-3', [detailRow(500)])
    const cross = useF2CrossSheet({
      allResponses: ref(map),
      projectContext: ref({}),
    })
    expect(cross.grossCrossValidation(500)).toBeNull()
    expect(cross.grossCrossValidation(600)).toContain('差异')
  })

  it('import round-trip: 行 JSON 序列化后 closingAmt 公式仍成立', () => {
    const row = detailRow(0, 100, 50, 20)
    row.closingAmt = calcEndAmount(row.openingAmt, row.increaseAmt, row.decreaseAmt)
    const parsed = JSON.parse(JSON.stringify([row]))
    expect(parsed[0].closingAmt).toBe(130)
    expect(calcSubtotal(parsed.map((r: { closingAmt: number }) => r.closingAmt))).toBe(130)
  })

  it('多 sheet 汇总 rowKey 与 F2-1 类别对齐', () => {
    const map = new Map<string, ChecklistResponse>()
    setDetailRows(map, 'F2-7', [detailRow(88)])
    const cross = useF2CrossSheet({
      allResponses: ref(map),
      projectContext: ref({}),
    })
    const outsourced = cross.categorySummaries.value.find((s) => s.rowKey === 'outsourced-processing')
    expect(outsourced?.sheetCode).toBe('F2-7')
    expect(outsourced?.closingAmt).toBe(88)
  })

  it('Property 11: 净值 = 原值 - 跌价（公式链）', () => {
    const gross = 1000
    const impairment = 120
    expect(calcNetValue(gross, impairment)).toBeCloseTo(880, 3)
    const detailClosing = calcSubtotal([500, 380])
    expect(calcNetValue(detailClosing, impairment)).toBeCloseTo(760, 3)
  })

  it('F2-1 审定 gross 与明细合计联动校验', () => {
    const map = new Map<string, ChecklistResponse>()
    setDetailRows(map, 'F2-3', [detailRow(300)])
    setDetailRows(map, 'F2-5', [detailRow(200)])
    const cross = useF2CrossSheet({
      allResponses: ref(map),
      projectContext: ref({}),
    })
    expect(cross.detailGrandTotal.value).toBe(500)
    expect(cross.grossCrossValidation(500)).toBeNull()
    expect(cross.grossCrossValidation(480)).toContain('差异')
  })
})
