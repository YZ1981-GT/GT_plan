import { describe, expect, it, vi } from 'vitest'
import {
  useG5ImpairmentCalc,
  parseG510Payload,
  applyStageUpdatesToRows,
  syncGroupRows,
  resolveAgingSegments,
  G5_AGING_FIVE_YEAR,
  G5_CREDIT_TERM_SEGMENTS,
  migrateLegacyStageRows,
  type G5ImpairmentCalcRow,
} from '../useG5ImpairmentCalc'

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), info: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

describe('useG5ImpairmentCalc', () => {
  it('默认：5 年账龄双标签 + 信用期 4 段 + 两个账龄组合', () => {
    const calc = useG5ImpairmentCalc()
    expect(calc.agingPreset.value).toBe('FIVE_YEAR')
    expect(calc.agingSegments.value).toHaveLength(G5_AGING_FIVE_YEAR.length)
    expect(calc.creditSegments.value).toHaveLength(G5_CREDIT_TERM_SEGMENTS.length)
    expect(calc.agingGroups.value).toHaveLength(2)
    expect(calc.agingGroups.value[0].rows).toHaveLength(6)
    expect(calc.agingGroups.value[0].rows[0].label).toContain('未逾期')
  })

  it('应计提 = 余额 × 损失率；差异 = 应计提 − 账面', () => {
    const calc = useG5ImpairmentCalc()
    calc.addSingleRow('甲公司')
    const id = calc.singleRows.value[0].rowId
    calc.updateSingleCell(id, 'auditedBalance', 1000)
    calc.updateSingleCell(id, 'lossRate', 0.05)
    calc.updateSingleCell(id, 'bookProvision', 30)
    expect(calc.singleRows.value[0].expectedProvision).toBeCloseTo(50, 5)
    expect(calc.singleRows.value[0].difference).toBeCloseTo(20, 5)
  })

  it('切换 3 年段并保留同 key 已填数', () => {
    const calc = useG5ImpairmentCalc()
    const gid = calc.agingGroups.value[0].groupId
    const within = calc.agingGroups.value[0].rows.find((r) => r.segmentKey === 'within1')!
    calc.updateAgingCell(gid, within.rowId, 'auditedBalance', 500)
    calc.updateAgingCell(gid, within.rowId, 'lossRate', 0.01)
    expect(calc.setAgingPreset('THREE_YEAR')).toBe(true)
    expect(calc.agingPreset.value).toBe('THREE_YEAR')
    expect(calc.agingGroups.value[0].rows.filter((r) => !r.archived)).toHaveLength(4)
    expect(calc.agingGroups.value[0].rows[0].auditedBalance).toBe(500)
  })

  it('自定义账龄至少 2 段，成功后段数变化', () => {
    const calc = useG5ImpairmentCalc()
    expect(calc.setAgingPreset('CUSTOM', ['仅一段'])).toBe(false)
    expect(calc.setAgingPreset('CUSTOM', ['0-6月', '6-12月', '1年以上'])).toBe(true)
    expect(calc.agingPreset.value).toBe('CUSTOM')
    expect(calc.agingSegments.value).toHaveLength(3)
    expect(calc.agingGroups.value[0].rows.filter((r) => !r.archived)).toHaveLength(3)
  })

  it('自定义信用期段', () => {
    const calc = useG5ImpairmentCalc()
    expect(calc.setCreditPreset('CUSTOM', ['期内', '逾期'])).toBe(true)
    expect(calc.creditPreset.value).toBe('CUSTOM')
    expect(calc.creditSegments.value.map((s) => s.label)).toEqual(['期内', '逾期'])
  })

  it('旧 Stage 数组可迁移为单项行', () => {
    const legacy: G5ImpairmentCalcRow[] = [{
      id: 'old-1',
      seq: 1,
      debtor: '乙公司',
      stageGroup: 'Stage2',
      bookBalance: 2000,
      pvFutureCashFlow: 0,
      creditLossRate: 0.1,
      impairmentProvision: 200,
      bookValue: 1800,
      balanceAdjustment: 0,
      adjustedCreditLossRate: 0.1,
      impairmentAdjustment: 0,
      adjBookBalance: 2000,
      adjImpairment: 200,
      adjBookValue: 1800,
      priorImpairment: 0,
      currentProvision: 0,
      currentReversal: 0,
      differenceNote: '注',
    }]
    const migrated = migrateLegacyStageRows(legacy)
    expect(migrated).toHaveLength(1)
    expect(migrated[0].label).toBe('乙公司')
    expect(migrated[0].stageGroup).toBe('Stage2')
    expect(migrated[0].auditedBalance).toBe(2000)

    const payload = parseG510Payload(legacy)
    expect(payload.version).toBe(2)
    expect(payload.singleRows[0].label).toBe('乙公司')
  })

  it('G5-9 阶段同步写入单项并产出 V2 payload', () => {
    const applied = applyStageUpdatesToRows([], [
      { debtor: '丙公司', auditStage: 'Stage3' },
    ])
    expect(applied.count).toBe(1)
    expect(applied.payload.version).toBe(2)
    expect(applied.payload.singleRows[0].label).toBe('丙公司')
    expect(applied.payload.singleRows[0].stageGroup).toBe('Stage3')
  })

  it('syncGroupRows 5→3 将长账龄汇入 over3 且不归档已吸收段', () => {
    const oldSegs = resolveAgingSegments('FIVE_YEAR')
    const rows = oldSegs.map((s, i) => ({
      rowId: `r${i}`,
      label: s.label,
      segmentKey: s.key,
      auditedBalance: s.key === 'y4to5' ? 100 : 0,
      lossRate: s.key === 'y4to5' ? 0.2 : 0,
      expectedProvision: 0,
      bookProvision: 0,
      difference: 0,
      basis: '',
      indexRef: '',
    }))
    const next = syncGroupRows(rows, resolveAgingSegments('THREE_YEAR'))
    expect(next.filter((r) => !r.archived)).toHaveLength(4)
    expect(next.some((r) => r.archived && r.segmentKey === 'y4to5')).toBe(false)
    const over3 = next.find((r) => r.segmentKey === 'over3' && !r.archived)
    expect(over3?.auditedBalance).toBe(100)
  })

  it('从 G5-2/G5-3 灌数并推送差异至 G5-4', () => {
    const calc = useG5ImpairmentCalc()
    const allResponses = new Map<string, any>()
    allResponses.set('G5-2-rows', {
      item_id: 'G5-2-rows',
      remark: JSON.stringify([
        {
          debtorName: '甲公司',
          closingBalance: 1000,
          netAmount: 1000,
          agingAudited: { within1: 600, y1to2: 400 },
        },
      ]),
    })
    allResponses.set('G5-3-rows', {
      item_id: 'G5-3-rows',
      remark: JSON.stringify([
        {
          category: 'individual',
          item: '甲公司',
          openingUnadjusted: 0,
          openingAdjustment: 0,
          provisionIncrease: 40,
          otherIncrease: 0,
          reversal: 0,
          writeOff: 0,
          otherDecrease: 0,
          closingAdjustment: 0,
        },
        {
          category: 'portfolio',
          item: '组合1',
          openingUnadjusted: 10,
          openingAdjustment: 0,
          provisionIncrease: 0,
          otherIncrease: 0,
          reversal: 0,
          writeOff: 0,
          otherDecrease: 0,
          closingAdjustment: 0,
        },
      ]),
    })

    const pulled = calc.pullFromG52AndG53(allResponses)
    expect(pulled.singles).toBeGreaterThanOrEqual(1)
    expect(pulled.agingBands).toBeGreaterThanOrEqual(1)
    expect(pulled.bookIndividual).toBeGreaterThanOrEqual(1)

    const single = calc.singleRows.value.find((r) => r.label === '甲公司')!
    expect(single.auditedBalance).toBeCloseTo(1000, 5)
    expect(single.bookProvision).toBeCloseTo(40, 5)
    calc.updateSingleCell(single.rowId, 'lossRate', 0.1)
    expect(single.difference).toBeCloseTo(60, 5)

    const saves: Array<{ id: string; data: any }> = []
    const n = calc.pushDiffsToG54(allResponses, (id, data) => {
      saves.push({ id, data })
      allResponses.set(id, { item_id: id, ...data })
    })
    expect(n).toBeGreaterThanOrEqual(1)
    const adj = saves.find((s) => s.id === 'G5-4-rows')
    expect(adj).toBeTruthy()
    const rows = JSON.parse(String(adj!.data.remark))
    expect(rows.some((r: any) => String(r.remark).includes('来自G5-10测算'))).toBe(true)
    expect(rows[0].creditAmount + rows[0].debitAmount).toBeGreaterThan(0)
  })
})
