/**
 * L8-2 明细表与权威模板 明细表L8-2 逐格同式（spec oo-writeback-template-parity-closure R2）。
 *
 * 模板事实（逐格实测）：
 *   派生行 R11 = R9 − R10、R13 = R11 − R12、R20 = R17 − R18 − R19：1~12 月与 O / P 列都按同式，
 *   R20 另有 T / U / V；
 *   合计 R22：X22 = X13 + X14 − X15 + X16 + X20 + X21（W22 = T22 + U22 + V22）；
 *   占比 R = IF(Q=0, 0, Q / $Q$22)，单元格格式 0.00%（比值）。
 * 原先：R13 读未计算的 R11（恒为 −利息收入）、派生行调整列恒 0、合计把 13 行全加、占比 ×100 且不落库。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn().mockResolvedValue({ value: '银行手续费' }) },
}))

import {
  calcL82Totals,
  computeL8DetailRows,
  createL8DefaultRows,
  makeEmptyL8Row,
  useL8Detail,
  type L8DetailRow,
} from '../useL8Detail'
import { isL82DerivedAmountField, isL82DerivedRowKey, l82TemplateRowId } from '../../l8/core/l8DetailRowIdentity'

/** 骨架下标（0 起）：R9=0 … R21=12 */
const R = (excelRow: number) => excelRow - 9

function skeleton(fill: Record<number, Partial<L8DetailRow>>): L8DetailRow[] {
  const rows = createL8DefaultRows()
  for (const [excelRow, patch] of Object.entries(fill)) {
    const i = R(Number(excelRow))
    rows[i] = { ...rows[i], ...patch }
  }
  return rows
}

function months(first: number): L8DetailRow['monthly'] {
  return [first, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
}

describe('L8-2 派生行按模板跨行算', () => {
  const rows = computeL8DetailRows(skeleton({
    9: { monthly: months(1000), aje: 50, rje: 5 },
    10: { monthly: months(300), aje: 10, rje: 1 },
    12: { monthly: months(100), aje: 20, rje: 2 },
    17: { monthly: months(400), aje: 40, rje: 4, priorUnadjusted: 900, priorAje: 9, priorRje: 1 },
    18: { monthly: months(150), aje: 15, rje: 2, priorUnadjusted: 200, priorAje: 2, priorRje: 0 },
    19: { monthly: months(50), aje: 5, rje: 1, priorUnadjusted: 100, priorAje: 1, priorRje: 0 },
  }))

  it('R11 = R9 − R10：月度与 O / P 列（O11 = O9 − O10）', () => {
    const r11 = rows[R(11)]
    expect(isL82DerivedRowKey(r11.key)).toBe(true)
    expect(r11.monthly[0]).toBe(700)
    expect(r11.aje).toBe(40)
    expect(r11.rje).toBe(4)
    expect(r11.periodAudited).toBe(744)
  })

  it('R13 = R11 − R12 取算好的 R11（原先读未计算的 R11，得 −100）', () => {
    const r13 = rows[R(13)]
    expect(r13.monthly[0]).toBe(600)
    expect(r13.aje).toBe(20)
    expect(r13.rje).toBe(2)
    expect(r13.periodAudited).toBe(622)
  })

  it('R20 = R17 − R18 − R19：月度、O / P 与上期 T / U / V', () => {
    const r20 = rows[R(20)]
    expect(r20.monthly[0]).toBe(200)
    expect(r20.aje).toBe(20)
    expect(r20.rje).toBe(1)
    expect(r20.priorUnadjusted).toBe(600)
    expect(r20.priorAje).toBe(6)
    expect(r20.priorRje).toBe(1)
    expect(r20.priorAudited).toBe(607)
  })

  it('派生行的调整列只读：R11 / R13 的 O、P，R20 另加 T、U、V；输入行与新增行可编辑', () => {
    expect(isL82DerivedAmountField(l82TemplateRowId(R(11)), 'aje')).toBe(true)
    expect(isL82DerivedAmountField(l82TemplateRowId(R(13)), 'rje')).toBe(true)
    expect(isL82DerivedAmountField(l82TemplateRowId(R(13)), 'priorUnadjusted')).toBe(false)
    expect(isL82DerivedAmountField(l82TemplateRowId(R(20)), 'priorRje')).toBe(true)
    expect(isL82DerivedAmountField(l82TemplateRowId(R(9)), 'aje')).toBe(false)
    expect(isL82DerivedAmountField('l82det-x', 'aje')).toBe(false)
  })
})

describe('L8-2 合计与占比按模板', () => {
  const rows = computeL8DetailRows([
    ...skeleton({
      9: { monthly: months(1000) },
      10: { monthly: months(300) },
      12: { monthly: months(100) },
      14: { monthly: months(80) },
      15: { monthly: months(30) },
      16: { monthly: months(20) },
      17: { monthly: months(400) },
      18: { monthly: months(150) },
      19: { monthly: months(50) },
      21: { monthly: months(10) },
    }),
    { ...makeEmptyL8Row('l82det-user', '银行手续费'), monthly: months(999) },
  ])

  it('合计 = R13 + R14 − R15 + R16 + R20 + R21（不是 13 行全加，新增行不计入）', () => {
    // R13 = (1000 − 300) − 100 = 600；R20 = 400 − 150 − 50 = 200
    expect(calcL82Totals(rows).periodAudited).toBe(600 + 80 - 30 + 20 + 200 + 10)
  })

  it('占比 = IF(Q=0,0,Q/Q22)，存比值（模板格式 0.00%）', () => {
    const total = 880
    expect(rows[R(13)].ratio).toBeCloseTo(600 / total, 12)
    expect(rows[R(15)].ratio).toBeCloseTo(30 / total, 12)
    expect(rows[R(11)].ratio).toBeCloseTo(700 / total, 12)
    expect(rows[R(20)].ratio).toBeCloseTo(200 / total, 12)
    expect(rows[13].ratio).toBeCloseTo(999 / total, 12)
    // Q = 0 ⇒ 0
    const r22Empty = computeL8DetailRows(createL8DefaultRows())
    expect(r22Empty.every(r => r.ratio === 0)).toBe(true)
  })

  it('上期合计 W22 同式', () => {
    const prior = computeL8DetailRows(skeleton({
      14: { priorUnadjusted: 50 },
      15: { priorUnadjusted: 20, priorAje: 5 },
      17: { priorUnadjusted: 300 },
      18: { priorUnadjusted: 100 },
    }))
    expect(calcL82Totals(prior).priorAudited).toBe(50 - 25 + 200)
  })
})

describe('L8-2 保存：落库算好的公式列，合计供 L8-1 勾稽', () => {
  function setup() {
    const calls: Array<{ key: string; payload: { remark: string } }> = []
    const formData = { debouncedSave: vi.fn((key: string, payload: { remark: string }) => calls.push({ key, payload })) }
    const detailRows = ref<L8DetailRow[]>(createL8DefaultRows())
    const api = useL8Detail(formData as never, detailRows)
    return { calls, detailRows, api }
  }

  it('L8-2-full-data 存占比（比值）与本期审定，派生行不进 store；netFinExpense = 模板合计', () => {
    const { calls, api } = setup()
    api.updateMonthly(R(14), 0, 300)
    api.updateMonthly(R(21), 0, 100)
    const saved = JSON.parse(calls.filter(c => c.key === 'L8-2-full-data').at(-1)!.payload.remark) as L8DetailRow[]
    expect(saved).toHaveLength(10)
    expect(saved.some(r => isL82DerivedRowKey(r.key))).toBe(false)
    const r14 = saved.find(r => r.key === l82TemplateRowId(R(14)))!
    expect(r14.periodAudited).toBe(300)
    expect(r14.ratio).toBeCloseTo(0.75, 12)
    expect(calls.filter(c => c.key === 'L8-2-netFinExpense').at(-1)!.payload.remark).toBe('400')
    expect(api.totalPeriodAudited.value).toBe(400)
  })

  it('派生行的调整列不接受编辑（UI 只读，updateRow 兜底）；新增行触发「不计入合计」提示', async () => {
    const { detailRows, api } = setup()
    api.updateRow(R(11), 'aje', 999)
    expect(detailRows.value[R(11)].aje).toBe(0)
    api.updateRow(R(9), 'aje', 10)
    expect(detailRows.value[R(9)].aje).toBe(10)
    expect(api.hasRowsOutsideTotal.value).toBe(false)
    await api.addRow()
    expect(api.hasRowsOutsideTotal.value).toBe(true)
  })
})
