/**
 * useG6EclImpairmentCalc — G6-12 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

vi.mock('element-plus', () => ({
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
  ElMessage: { success: vi.fn() },
}))

import {
  useG6EclImpairmentCalc,
  migrateImpairmentRow,
  createEmptyImpairmentRow,
} from '../useG6EclImpairmentCalc'
import { ElMessageBox } from 'element-plus'

describe('migrateImpairmentRow', () => {
  it('补齐 PV / 组合字段并兼容旧数据', () => {
    const row = migrateImpairmentRow(
      { id: 'a', investProject: '债A', amortizedCost: 1000, creditLossRate: 0.01 },
      1,
    )
    expect(row.pvFutureCashFlow).toBe(0)
    expect(row.creditGroupMethod).toBe('')
    expect(row.creditGroupName).toBe('')
    expect(row.amortizedCost).toBe(1000)
  })
})

describe('useG6EclImpairmentCalc — Stage1/2 损失率法', () => {
  it('③=①×②；⑥=⑤×②A+①×(②A−②)；⑨=⑦−⑧', async () => {
    const { rows, loadRows } = useG6EclImpairmentCalc()
    loadRows([
      createEmptyImpairmentRow({
        id: 'r1',
        seq: 1,
        investProject: 'A',
        stage: 'Stage1',
        stageGroup: 'Stage1',
        amortizedCost: 10_000_000,
        creditLossRate: 0.01,
        balanceAdjustment: 2_000_000,
        adjustedCreditLossRate: 0.02,
        adjRateTouched: true,
      }),
    ])
    await nextTick()
    const r = rows.value[0]
    expect(r.impairmentProvision).toBe(100_000)
    expect(r.bookValue).toBe(9_900_000)
    expect(r.impairmentAdjustment).toBe(140_000)
    expect(r.adjBalance).toBe(12_000_000)
    expect(r.adjImpairment).toBe(240_000)
    expect(r.adjBookValue).toBe(11_760_000)
  })
})

describe('useG6EclImpairmentCalc — Stage3 现值法', () => {
  it('PV>0 时按余额−PV 计提', () => {
    const { loadRows, rows } = useG6EclImpairmentCalc()
    loadRows([{
      id: '1',
      seq: 1,
      investProject: 'A',
      stage: 'Stage3',
      stageGroup: 'Stage3',
      amortizedCost: 1_000_000,
      pvFutureCashFlow: 700_000,
    } as any])
    expect(rows.value[0].impairmentProvision).toBe(300_000)
  })

  it('PV=0（零回收）仍按现值法全额计提，不退回损失率法', () => {
    const { loadRows, rows } = useG6EclImpairmentCalc()
    loadRows([{
      id: '1',
      seq: 1,
      investProject: '零回收',
      stage: 'Stage3',
      stageGroup: 'Stage3',
      amortizedCost: 500_000,
      pvFutureCashFlow: 0,
      creditLossRate: 0.05,
    } as any])
    expect(rows.value[0].impairmentProvision).toBe(500_000)
    expect(rows.value[0].bookValue).toBe(0)
  })

  it('③=①−PV；损失率反推；⑥倒挤', async () => {
    const { rows, loadRows } = useG6EclImpairmentCalc()
    loadRows([
      createEmptyImpairmentRow({
        id: 'r1',
        seq: 1,
        investProject: 'B',
        stage: 'Stage3',
        stageGroup: 'Stage3',
        amortizedCost: 1_000_000,
        pvFutureCashFlow: 700_000,
        balanceAdjustment: 0,
      }),
    ])
    await nextTick()
    const r = rows.value[0]
    expect(r.impairmentProvision).toBe(300_000)
    expect(r.creditLossRate).toBe(0.3)
    expect(r.bookValue).toBe(700_000)
    expect(r.adjImpairment).toBe(300_000)
    expect(r.impairmentAdjustment).toBe(0)
  })

  it('审定现值变化时倒挤 ⑥', async () => {
    const { rows, loadRows, updateRow } = useG6EclImpairmentCalc()
    loadRows([
      createEmptyImpairmentRow({
        id: 'r1',
        seq: 1,
        investProject: 'C',
        stage: 'Stage3',
        stageGroup: 'Stage3',
        amortizedCost: 1_000_000,
        pvFutureCashFlow: 800_000,
      }),
    ])
    await nextTick()
    updateRow('r1', 'adjustedPvFutureCashFlow', 700_000)
    await nextTick()
    const r = rows.value[0]
    // ③=200000；⑦=1000000；目标⑧=300000；⑥=100000
    expect(r.impairmentProvision).toBe(200_000)
    expect(r.adjImpairment).toBe(300_000)
    expect(r.impairmentAdjustment).toBe(100_000)
  })
})

describe('useG6EclImpairmentCalc — 本年计提/转回与公式保护', () => {
  it('本年计提/转回自动轧差且不可手改', async () => {
    const { rows, loadRows, updateRow } = useG6EclImpairmentCalc()
    loadRows([
      createEmptyImpairmentRow({
        id: 'r1',
        seq: 1,
        investProject: 'D',
        stage: 'Stage1',
        stageGroup: 'Stage1',
        amortizedCost: 1_000_000,
        creditLossRate: 0.05,
        priorImpairment: 10_000,
      }),
    ])
    await nextTick()
    // ⑧=50000 → 计提 40000
    expect(rows.value[0].currentProvision).toBe(40_000)
    expect(rows.value[0].currentReversal).toBe(0)
    updateRow('r1', 'currentReversal', 999 as any)
    expect(rows.value[0].currentReversal).toBe(0)
  })
})

describe('useG6EclImpairmentCalc — CRUD / 分组', () => {
  beforeEach(() => vi.clearAllMocks())

  it('addRow 成功', async () => {
    vi.mocked(ElMessageBox.prompt).mockResolvedValue({ value: '新债' } as any)
    const { rows, addRow } = useG6EclImpairmentCalc()
    await addRow('Stage2')
    expect(rows.value).toHaveLength(1)
    expect(rows.value[0].stage).toBe('Stage2')
    expect(rows.value[0].investProject).toBe('新债')
  })

  it('按 Stage 分组小计', async () => {
    const { loadRows, groupedRows } = useG6EclImpairmentCalc()
    loadRows([
      createEmptyImpairmentRow({
        id: '1', seq: 1, investProject: 'A', stage: 'Stage1', stageGroup: 'Stage1',
        amortizedCost: 100, creditLossRate: 0.1,
      }),
      createEmptyImpairmentRow({
        id: '2', seq: 2, investProject: 'B', stage: 'Stage3', stageGroup: 'Stage3',
        amortizedCost: 200, pvFutureCashFlow: 150,
      }),
    ])
    await nextTick()
    expect(groupedRows.value.stage1.rows).toHaveLength(1)
    expect(groupedRows.value.stage3.rows).toHaveLength(1)
    expect(groupedRows.value.grandTotal.amortizedCost).toBe(300)
    expect(groupedRows.value.grandTotal.impairmentProvision).toBe(60) // 10 + 50
  })
})
