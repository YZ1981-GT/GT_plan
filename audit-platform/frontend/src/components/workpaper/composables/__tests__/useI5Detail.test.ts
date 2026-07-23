/**
 * useI5Detail — 单元测试（原值|减值|净值 + 未审→调整→审定）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useI5Detail,
  emptyI5DetailRow,
  normalizeI5DetailRow,
  recalcI5DetailRow,
  syncI5DetailLegacyAliases,
  collectI5RollWarnings,
  buildI5DetailConclusionDraft,
  recalcI5RollAmounts,
  emptyI5RollAmounts,
  getI5NetRoll,
  I5_BUILTIN_CATEGORIES,
  I5_DETAIL_SECTION_LABELS,
  I5_2_OBJECTIVES,
  I5_2_PREP_NOTES,
  I5_2_CAS14_TIPS,
} from '../useI5Detail'
import { seedI5AdjudicationFromDetail } from '../i5AdjudicationModel'

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

describe('recalcI5RollAmounts / Excel 公式', () => {
  it('E=B+C−D；L=B+F+G；M=C+H+J；N=D+I+K；O=L+M−N', () => {
    const block = emptyI5RollAmounts({
      unadjOpening: 100,
      unadjIncrease: 50,
      unadjDecrease: 20,
      openingAje: 5,
      openingRje: -2,
      ajeIncrease: 10,
      ajeDecrease: 3,
      rjeIncrease: 4,
      rjeDecrease: 1,
    })
    recalcI5RollAmounts(block)
    expect(block.unadjEnding).toBe(130) // 100+50-20
    expect(block.auditedOpening).toBe(103) // 100+5-2
    expect(block.auditedIncrease).toBe(64) // 50+10+4
    expect(block.auditedDecrease).toBe(24) // 20+3+1
    expect(block.auditedEnding).toBe(143) // 103+64-24
  })
})

describe('净值 = 原值 − 减值', () => {
  it('各列相减且期末取原值期末−减值期末', () => {
    const row = emptyI5DetailRow({
      projectName: '合同资产',
      gross: emptyI5RollAmounts({ unadjOpening: 200, unadjIncrease: 100, unadjDecrease: 40 }),
      impairment: emptyI5RollAmounts({ unadjOpening: 20, unadjIncrease: 10, unadjDecrease: 5 }),
    })
    recalcI5DetailRow(row)
    const net = getI5NetRoll(row)
    expect(row.gross.unadjEnding).toBe(260)
    expect(row.impairment.unadjEnding).toBe(25)
    expect(net.unadjEnding).toBe(235)
    expect(net.auditedEnding).toBe(235)
    syncI5DetailLegacyAliases(row)
    expect(row.endBalance).toBe(235)
    expect(row.beginBalance).toBe(180) // 200-20
  })
})

describe('旧字段迁移', () => {
  it('扁平 beginBalance/increase/decrease 灌入原值未审', () => {
    const row = normalizeI5DetailRow({
      name: '预付工程款',
      beginBalance: 80,
      increase: 40,
      decrease: 10,
    })
    expect(row.projectName).toBe('预付工程款')
    expect(row.gross.unadjOpening).toBe(80)
    expect(row.gross.unadjIncrease).toBe(40)
    expect(row.gross.unadjDecrease).toBe(10)
    expect(row.gross.unadjEnding).toBe(110)
    expect(row.endBalance).toBe(110)
  })
})

describe('collectI5RollWarnings', () => {
  it('减值大于原值时告警', () => {
    const row = emptyI5DetailRow({
      projectName: '委托贷款',
      gross: emptyI5RollAmounts({ unadjOpening: 10 }),
      impairment: emptyI5RollAmounts({ unadjOpening: 50 }),
    })
    recalcI5DetailRow(row)
    const warns = collectI5RollWarnings([row])
    expect(warns.some((w) => w.kind === 'imp_gt_gross')).toBe(true)
  })
})

describe('useI5Detail 默认骨架', () => {
  it('空数据加载内置 10 类', () => {
    const { rows, sections } = useI5Detail(createAllResponses())
    expect(rows.value.length).toBe(I5_BUILTIN_CATEGORIES.length)
    expect(rows.value[0].projectName).toBe('预付土地出让金')
    expect(rows.value.find((r) => r.projectName === '合同资产')?.indexRef).toBe('D7')
    expect(sections).toHaveLength(4)
    expect(I5_DETAIL_SECTION_LABELS[0]).toBe('原值未审')
  })

  it('持久化后合计取净值审定', () => {
    const saved: string[] = []
    const map = createAllResponses()
    const { rows, subtotals, updateCell } = useI5Detail(map, {
      onSave: (_id, val) => saved.push(String(val)),
    })
    const target = rows.value.find((r) => r.projectName === '预付土地出让金')!
    updateCell(target.rowId, 'gross.unadjOpening', 1000)
    updateCell(target.rowId, 'gross.unadjIncrease', 200)
    updateCell(target.rowId, 'impairment.unadjOpening', 50)
    expect(subtotals.value.grossAuditedEnding).toBe(1200)
    expect(subtotals.value.impAuditedEnding).toBe(50)
    expect(subtotals.value.netAuditedEnding).toBe(1150)
    expect(subtotals.value.endBalance).toBe(1150)
    expect(saved.length).toBeGreaterThan(0)
  })
})

describe('seedI5AdjudicationFromDetail 读净值', () => {
  it('从 gross/impairment 带入净值审定', () => {
    const detail = [
      emptyI5DetailRow({
        projectName: '合同取得成本',
        gross: emptyI5RollAmounts({ unadjOpening: 500, unadjIncrease: 100 }),
        impairment: emptyI5RollAmounts({ unadjOpening: 30 }),
      }),
    ]
    for (const r of detail) recalcI5DetailRow(r)
    const seeded = seedI5AdjudicationFromDetail(detail)
    expect(seeded).toHaveLength(1)
    expect(seeded[0].beginBalance).toBe(470)
    expect(seeded[0].endBalance).toBe(570)
    expect(seeded[0].fromDetail).toBe(true)
  })
})

describe('文案常量', () => {
  it('目标/编制说明/CAS14 非空', () => {
    expect(I5_2_OBJECTIVES.length).toBeGreaterThanOrEqual(2)
    expect(I5_2_PREP_NOTES.length).toBeGreaterThanOrEqual(3)
    expect(I5_2_CAS14_TIPS.length).toBeGreaterThanOrEqual(4)
    const draft = buildI5DetailConclusionDraft({
      rowCount: 10,
      netAuditedEnding: 100,
      grossAuditedEnding: 120,
      impAuditedEnding: 20,
      warningCount: 0,
    })
    expect(draft).toContain('净值')
  })
})
