/**
 * F2 监盘 — 字段/行持久化 + F2-21 旧表迁移
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useF2StocktakeFields,
  useF2StocktakeRows,
  migrateF21RowsToFields,
} from '../useF2StocktakeSheet'
import type { ChecklistResponse } from '../useF2StocktakeFormData'

function makeMap(entries: Record<string, string | null>): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()
  for (const [item_id, remark] of Object.entries(entries)) {
    map.set(item_id, { item_id, conclusion: null, remark })
  }
  return map
}

describe('migrateF21RowsToFields', () => {
  it('已有 fields 时不迁移', () => {
    const rows = JSON.stringify([{ location: 'A仓', inventoryType: '原材料', sharePct: '30', countDate: '2025-12-31' }])
    expect(migrateF21RowsToFields(rows, { countSchedule: '已有内容' })).toBeNull()
  })

  it('空 fields 时从 rows 生成 countSchedule / warehouses', () => {
    const rows = JSON.stringify([
      { location: 'A仓', inventoryType: '原材料', sharePct: '30', countDate: '2025-12-31' },
      { location: 'B仓', inventoryType: '产成品', sharePct: '70', countDate: '2026-01-02' },
    ])
    const patch = migrateF21RowsToFields(rows, {})
    expect(patch).not.toBeNull()
    expect(patch!.countSchedule).toContain('A仓')
    expect(patch!.countSchedule).toContain('B仓')
    expect(patch!.warehouses).toContain('A仓')
    expect(patch!.warehouses).toContain('B仓')
    expect(patch!.inventoryTypes).toContain('原材料')
  })
})

describe('useF2StocktakeFields', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('F2-21-fields 无数据时双读 F2-21-rows', () => {
    const legacy = JSON.stringify([
      { location: '主仓库', inventoryType: '库存商品', sharePct: '100', countDate: '2025-12-31' },
    ])
    const allResponses = ref(
      makeMap({ 'F2-21-rows': legacy, 'F2-21-note': '' }),
    )
    const { fields } = useF2StocktakeFields({
      fieldsKey: 'F2-21-fields',
      noteKey: 'F2-21-note',
      fieldIds: ['countSchedule', 'warehouses', 'inventoryTypes'],
      allResponses,
      isReadonly: ref(false),
    })
    expect(fields.value.countSchedule).toContain('主仓库')
    expect(fields.value.warehouses).toBe('主仓库')
  })

  it('updateField 触发 f2-stocktake:save-items', () => {
    const allResponses = ref(makeMap({ 'F2-22-fields': '{}', 'F2-22-note': '' }))
    const handler = vi.fn()
    window.addEventListener('f2-stocktake:save-items', handler)

    const { updateField } = useF2StocktakeFields({
      fieldsKey: 'F2-22-fields',
      noteKey: 'F2-22-note',
      fieldIds: ['entity'],
      allResponses,
      isReadonly: ref(false),
    })
    updateField('entity', '测试公司')
    vi.advanceTimersByTime(2000)
    expect(handler).toHaveBeenCalled()
    window.removeEventListener('f2-stocktake:save-items', handler)
  })
})

describe('useF2StocktakeRows', () => {
  it('从 remark JSON 加载行', () => {
    const rows = [{ id: 'r1', itemName: '钢材', bookQty: '10' }]
    const allResponses = ref(makeMap({
      'F2-24-rows': JSON.stringify(rows),
      'F2-24-note': '核对结论',
    }))
    const { rows: loaded, auditNote } = useF2StocktakeRows({
      rowsKey: 'F2-24-rows',
      noteKey: 'F2-24-note',
      allResponses,
      emptyRow: () => ({ id: 'new', itemName: '', bookQty: '' }),
    })
    expect(loaded.value).toHaveLength(1)
    expect(loaded.value[0].itemName).toBe('钢材')
    expect(auditNote.value).toBe('核对结论')
  })
})
