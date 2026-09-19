/**
 * useI4Detail — 单元测试（未审→调整→审定滚动）
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useI4Detail,
  emptyI4DetailRow,
  normalizeI4DetailRow,
  recalcI4DetailRow,
  syncI4DetailLegacyAliases,
  collectI4RollWarnings,
  summarizeI4ByCategory,
  buildI4DetailConclusionDraft,
  I4_DETAIL_SECTION_LABELS,
  I4_2_OBJECTIVES,
  I4_2_PREP_NOTES,
} from '../useI4Detail'

function createAllResponses(data?: Record<string, any>) {
  const map = new Map<string, any>()
  if (data) {
    for (const [key, value] of Object.entries(data)) {
      map.set(key, {
        item_id: key,
        conclusion: null,
        remark: typeof value === 'string' ? value : JSON.stringify(value),
      })
    }
  }
  return ref(map)
}

describe('recalcI4DetailRow', () => {
  it('未审期末 = 期初+增−摊销−其他；审定 = 未审+调整', () => {
    const row = emptyI4DetailRow({
      projectName: '装修A',
      originalAmount: 1200,
      unadjOpening: 100,
      unadjIncrease: 200,
      unadjAmortization: 50,
      unadjOtherDecrease: 10,
      openingAdj: 5,
      ajeIncrease: 20,
      ajeAmortization: -5,
      ajeOtherDecrease: 0,
      totalMonths: 12,
      elapsedMonths: 3,
    })
    recalcI4DetailRow(row)
    expect(row.unadjEnding).toBe(240) // 100+200-50-10
    expect(row.auditedOpening).toBe(105)
    expect(row.auditedIncrease).toBe(220)
    expect(row.auditedAmortization).toBe(45)
    expect(row.auditedOtherDecrease).toBe(10)
    expect(row.auditedEnding).toBe(270) // 105+220-45-10
    expect(row.monthlyAmortization).toBe(100) // 1200/12
  })

  it('旧 beginBalance/currentIncrease 灌入未审并回写审定别名', () => {
    const row = emptyI4DetailRow({
      projectName: '旧行',
      beginBalance: 80,
      currentIncrease: 40,
      currentAmortization: 15,
      currentDecrease: 5,
      originalAmount: 0,
    })
    recalcI4DetailRow(row)
    expect(row.unadjOpening).toBe(80)
    expect(row.unadjIncrease).toBe(40)
    expect(row.unadjAmortization).toBe(15)
    expect(row.unadjOtherDecrease).toBe(5)
    expect(row.originalAmount).toBe(40)
    syncI4DetailLegacyAliases(row)
    expect(row.beginBalance).toBe(row.auditedOpening)
    expect(row.currentIncrease).toBe(row.auditedIncrease)
    expect(row.endBalance).toBe(row.auditedEnding)
  })
})

describe('normalizeI4DetailRow', () => {
  it('兼容旧 25 列字段', () => {
    const row = normalizeI4DetailRow({
      projectName: '办公室装修',
      beginBalance: 100,
      currentIncrease: 50,
      currentAmortization: 20,
      currentDecrease: 0,
      endBalance: 999, // 将被公式覆盖
      expenseType: '装修费',
      totalMonths: 24,
    })
    expect(row.unadjOpening).toBe(100)
    expect(row.unadjIncrease).toBe(50)
    expect(row.unadjEnding).toBe(130)
    expect(row.auditedEnding).toBe(130)
    expect(row.expenseType).toBe('装修费')
  })
})

describe('collectI4RollWarnings / category / conclusion', () => {
  it('勾稽平衡时无警告；类别小计与结论草稿可用', () => {
    const rows = [
      normalizeI4DetailRow({
        projectName: 'A1',
        category: '类别A',
        unadjOpening: 10,
        unadjIncrease: 0,
        unadjAmortization: 2,
        unadjOtherDecrease: 0,
      }),
      normalizeI4DetailRow({
        projectName: 'B1',
        category: '类别B',
        unadjOpening: 20,
        unadjIncrease: 30,
        unadjAmortization: 5,
        unadjOtherDecrease: 1,
      }),
    ]
    expect(collectI4RollWarnings(rows)).toHaveLength(0)
    const cats = summarizeI4ByCategory(rows)
    expect(cats).toHaveLength(2)
    expect(cats.find((c) => c.category === '类别A')?.count).toBe(1)

    const text = buildI4DetailConclusionDraft({
      rowCount: 2,
      auditedEnding: 52,
      unadjEnding: 52,
      warningCount: 0,
      categoryCount: 2,
    })
    expect(text).toContain('2 项')
    expect(text).toContain('开办费')
    expect(I4_2_OBJECTIVES[0]).toContain('明细账')
    expect(I4_2_PREP_NOTES.some((n) => n.includes('开办费'))).toBe(true)
    expect(I4_DETAIL_SECTION_LABELS).toHaveLength(4)
  })

  it('开办费余额触发风险提示', () => {
    const rows = [
      normalizeI4DetailRow({
        projectName: '筹建开办费',
        expenseType: '开办费',
        originalAmount: 50,
        unadjIncrease: 50,
      }),
    ]
    const warns = collectI4RollWarnings(rows)
    expect(warns.some((w) => w.kind === 'startup')).toBe(true)
  })
})

describe('useI4Detail', () => {
  beforeEach(() => {
    // no-op
  })

  it('从 I4-2-rows 加载并合计审定期末', () => {
    const allResponses = createAllResponses({
      'I4-2-rows': [
        {
          projectName: '装修',
          unadjOpening: 100,
          unadjIncrease: 50,
          unadjAmortization: 20,
          unadjOtherDecrease: 0,
        },
      ],
    })
    const { rows, subtotals } = useI4Detail(allResponses)
    expect(rows.value).toHaveLength(1)
    expect(subtotals.value.unadjEnding).toBe(130)
    expect(subtotals.value.auditedEnding).toBe(130)
    expect(subtotals.value.endBalance).toBe(130)
    expect(subtotals.value.currentIncrease).toBe(50)
  })

  it('updateCell 触发重算与别名回写', () => {
    const allResponses = createAllResponses({
      'I4-2-rows': [{ projectName: 'X', unadjOpening: 0, unadjIncrease: 100 }],
    })
    const saved: Array<{ id: string; val: string }> = []
    const { rows, updateCell } = useI4Detail(allResponses, {
      onSave: (id, val) => saved.push({ id, val: String(val) }),
    })
    updateCell(rows.value[0].rowId, 'unadjAmortization', 30)
    expect(rows.value[0].unadjEnding).toBe(70)
    expect(rows.value[0].currentAmortization).toBe(30)
    expect(saved.length).toBeGreaterThan(0)
  })
})
