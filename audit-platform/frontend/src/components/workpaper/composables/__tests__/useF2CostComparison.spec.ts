/**
 * useF2CostComparison — F2-20 pack v2（功能参照 F2-18）
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useF2CostComparison } from '../useF2CostComparison'
import type { ChecklistResponse } from '../useF2FormData'

describe('useF2CostComparison F2-20 rebuild', () => {
  beforeEach(() => {
    window.addEventListener('f2:save-items', () => {})
  })
  afterEach(() => {
    window.removeEventListener('f2:save-items', () => {})
  })

  it('defaults year labels, threshold and one empty row', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const c = useF2CostComparison({ allResponses: map, isReadonly: ref(false) })
    expect(c.yearLabels.value).toEqual(['本年', '上年'])
    expect(c.pack.value.anomalyThreshold).toBe(0.2)
    expect(c.enrichedRows.value).toHaveLength(1)
    expect(c.notes.value).toEqual({ note: '', abnormalReason: '' })
  })

  it('computes totals and fluctuation rates with zero-safe denominator', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const c = useF2CostComparison({ allResponses: map, isReadonly: ref(false) })
    const id = c.enrichedRows.value[0].rowId
    c.updateCell(id, 'productName', '产品A')
    c.updateCell(id, 'currentMaterial', 120)
    c.updateCell(id, 'currentLabor', 40)
    c.updateCell(id, 'currentOverhead', 40)
    c.updateCell(id, 'priorMaterial', 100)
    c.updateCell(id, 'priorLabor', 50)
    c.updateCell(id, 'priorOverhead', 50)

    const row = c.enrichedRows.value[0]
    expect(row.currentTotal).toBe(200)
    expect(row.priorTotal).toBe(200)
    expect(row.matRate).toBe(20)
    expect(row.laborRate).toBe(-20)
    expect(row.totalRate).toBe(0)
    expect(c.totals.value.currentTotal).toBe(200)
  })

  it('auto-flags anomaly when total rate exceeds threshold and abnormal is empty', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const c = useF2CostComparison({ allResponses: map, isReadonly: ref(false) })
    const id = c.enrichedRows.value[0].rowId
    c.updateCell(id, 'currentMaterial', 130)
    c.updateCell(id, 'priorMaterial', 100)
    // totals 130 vs 100 → +30% > 20%
    const row = c.enrichedRows.value[0]
    expect(row.autoAnomaly).toBe(true)
    expect(row.isAnomaly).toBe(true)
    expect(c.anomalyCount.value).toBe(1)

    c.updateCell(id, 'abnormal', '否')
    expect(c.enrichedRows.value[0].isAnomaly).toBe(false)
  })

  it('persists version 2 pack with notes + yearLabels', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const c = useF2CostComparison({ allResponses: map, isReadonly: ref(false) })
    c.updateYearLabel(0, '2025年')
    c.updateYearLabel(1, '2024年')
    c.updateThreshold(0.15)
    c.updateNotes('note', '已比较主要产品单位成本')
    c.updateNotes('abnormalReason', '产品A材料涨价见F2-61')
    c.conclusion.value = 'A、未见异常。'

    const stored = map.value.get('F2-20-pack')?.remark
    expect(stored).toBeTruthy()
    const parsed = JSON.parse(stored!)
    expect(parsed.version).toBe(2)
    expect(parsed.yearLabels).toEqual(['2025年', '2024年'])
    expect(parsed.anomalyThreshold).toBe(0.15)
    expect(parsed.notes.note).toContain('单位成本')
    expect(parsed.notes.abnormalReason).toContain('F2-61')
    expect(parsed.auditConclusion).toContain('未见异常')
  })

  it('migrates flat auditNote from legacy pack shape', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    map.value.set('F2-20-pack', {
      item_id: 'F2-20-pack',
      conclusion: null,
      remark: JSON.stringify({
        version: 2,
        rows: [{
          rowId: 'r1',
          productName: '旧产品',
          currentMaterial: 10,
          currentLabor: 0,
          currentOverhead: 0,
          priorMaterial: 8,
          priorLabor: 0,
          priorOverhead: 0,
          abnormal: '',
          indexRef: '',
        }],
        auditNote: '旧版单栏说明',
        auditConclusion: 'A、未见异常。',
        anomalyThreshold: 0.2,
      }),
    })
    const c = useF2CostComparison({ allResponses: map, isReadonly: ref(false) })
    expect(c.notes.value.note).toBe('旧版单栏说明')
    expect(c.enrichedRows.value[0].productName).toBe('旧产品')
    expect(c.conclusion.value).toContain('未见异常')
  })
})
