/**
 * F2 监盘 — 字段/行持久化 + F2-21 旧表迁移
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, ref } from 'vue'
import {
  PendingWritesFlushError,
  flushPendingWrites,
} from '../../sync/pendingWrites'
import { useF2StocktakeQuestionnaire } from '../useF2StocktakeQuestionnaire'
import {
  useF2StocktakeFields,
  useF2StocktakeRows,
  migrateF21RowsToFields,
  dispatchF2StocktakeSave,
  F2_STOCKTAKE_SAVE_TIMEOUT_MS,
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

  it('字段 flusher 注册到平台屏障，并等待父保存明确完成', async () => {
    const allResponses = ref(makeMap({ 'F2-22-fields': '{}', 'F2-22-note': '' }))
    let detail: { items: ChecklistResponse[]; accept?: () => void; resolve: () => void } | undefined
    const handler = (event: Event) => {
      detail = (event as CustomEvent).detail
      // 真实宿主 handleSave 第一步就同步 accept；不 accept 即「没人听」会立即失败
      detail?.accept?.()
    }
    window.addEventListener('f2-stocktake:save-items', handler)
    const scope = effectScope()
    try {
      let fields!: ReturnType<typeof useF2StocktakeFields>
      scope.run(() => {
        fields = useF2StocktakeFields({
          fieldsKey: 'F2-22-fields',
          noteKey: 'F2-22-note',
          fieldIds: ['entity'],
          allResponses,
          isReadonly: ref(false),
        })
      })
      fields.updateField('entity', '屏障内保存')
      let settled = false
      const barrier = flushPendingWrites().then(() => { settled = true })
      await Promise.resolve()
      expect(detail?.items[0].remark).toContain('屏障内保存')
      expect(settled).toBe(false)
      detail?.resolve()
      await barrier
      expect(settled).toBe(true)
    } finally {
      scope.stop()
      window.removeEventListener('f2-stocktake:save-items', handler)
    }
  })

  it('父保存 reject 会让平台屏障失败，不能由 8 秒超时伪装成功', async () => {
    const allResponses = ref(makeMap({ 'F2-22-fields': '{}', 'F2-22-note': '' }))
    const handler = (event: Event) => {
      ;(event as CustomEvent).detail.reject(new Error('监盘 PUT 失败'))
    }
    window.addEventListener('f2-stocktake:save-items', handler)
    const scope = effectScope()
    try {
      let fields!: ReturnType<typeof useF2StocktakeFields>
      scope.run(() => {
        fields = useF2StocktakeFields({
          fieldsKey: 'F2-22-fields',
          noteKey: 'F2-22-note',
          fieldIds: ['entity'],
          allResponses,
          isReadonly: ref(false),
        })
      })
      fields.updateField('entity', '失败值')
      await expect(flushPendingWrites()).rejects.toBeInstanceOf(PendingWritesFlushError)
    } finally {
      scope.stop()
      window.removeEventListener('f2-stocktake:save-items', handler)
    }
  })

  it('F2-21 过渡只读只冻结输入，不阻止已编辑问卷刷盘', async () => {
    const allResponses = ref(makeMap({ 'F2-21-fields': '{}', 'F2-21-note': '' }))
    const interactionReadonly = ref(false)
    const businessReadonly = ref(false)
    const saved: ChecklistResponse[][] = []
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail
      saved.push(detail.items)
      detail.resolve()
    }
    window.addEventListener('f2-stocktake:save-items', handler)
    const scope = effectScope()
    try {
      let questionnaire!: ReturnType<typeof useF2StocktakeQuestionnaire>
      scope.run(() => {
        questionnaire = useF2StocktakeQuestionnaire({
          allResponses,
          isReadonly: interactionReadonly,
          businessReadonly,
        })
      })
      questionnaire.updateAnswer('q1', '已编辑')
      interactionReadonly.value = true
      await flushPendingWrites()
      expect(saved).toHaveLength(1)
      expect(saved[0].find((item) => item.item_id === 'F2-21-fields')?.remark)
        .toContain('已编辑')
    } finally {
      scope.stop()
      window.removeEventListener('f2-stocktake:save-items', handler)
    }
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
  it('F2-25 行 flusher 也进入平台屏障并等待父保存', async () => {
    const allResponses = ref(makeMap({
      'F2-25-rows': JSON.stringify([{ id: 'r1', itemName: '旧值' }]),
      'F2-25-note': '',
    }))
    let detail: { items: ChecklistResponse[]; accept?: () => void; resolve: () => void } | undefined
    const handler = (event: Event) => {
      detail = (event as CustomEvent).detail
      detail?.accept?.()
    }
    window.addEventListener('f2-stocktake:save-items', handler)
    const scope = effectScope()
    try {
      let sheet!: ReturnType<typeof useF2StocktakeRows<{ id: string; itemName: string }>>
      scope.run(() => {
        sheet = useF2StocktakeRows({
          rowsKey: 'F2-25-rows',
          noteKey: 'F2-25-note',
          allResponses,
          emptyRow: () => ({ id: 'new', itemName: '' }),
        })
      })
      sheet.updateRow('r1', { itemName: '最新抽盘值' })
      const barrier = flushPendingWrites()
      await Promise.resolve()
      expect(detail?.items.find((item) => item.item_id === 'F2-25-rows')?.remark)
        .toContain('最新抽盘值')
      detail?.resolve()
      await barrier
    } finally {
      scope.stop()
      window.removeEventListener('f2-stocktake:save-items', handler)
    }
  })

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

// ─── 「没人听」与「在处理」必须分开（design §8 残留 7） ──────────────────────
describe('dispatchF2StocktakeSave 的 accept 回执', () => {
  it('没有监听方时立即失败，不等满 8 秒', async () => {
    vi.useFakeTimers()
    try {
      const promise = dispatchF2StocktakeSave([
        { item_id: 'F2-22-fields', conclusion: null, remark: '{}' },
      ])
      // 一个时钟都不推进：没人 accept 就应该已经 reject
      await expect(promise).rejects.toThrow(/没有组件接收保存请求/)
    } finally {
      vi.useRealTimers()
    }
  })

  it('已 accept 但不应答时，仍按原 8 秒超时失败（这才是「在处理但卡住」）', async () => {
    vi.useFakeTimers()
    const handler = (event: Event) => { (event as CustomEvent).detail.accept?.() }
    window.addEventListener('f2-stocktake:save-items', handler)
    try {
      const promise = dispatchF2StocktakeSave([
        { item_id: 'F2-22-fields', conclusion: null, remark: '{}' },
      ])
      const probe = { settled: false, error: undefined as unknown }
      void promise.then(
        () => { probe.settled = true },
        (err) => { probe.settled = true; probe.error = err },
      )
      await vi.advanceTimersByTimeAsync(F2_STOCKTAKE_SAVE_TIMEOUT_MS - 100)
      expect(probe.settled).toBe(false)
      await vi.advanceTimersByTimeAsync(200)
      expect(probe.settled).toBe(true)
      expect(String((probe.error as Error)?.message)).toContain('等待超时')
    } finally {
      window.removeEventListener('f2-stocktake:save-items', handler)
      vi.useRealTimers()
    }
  })

  it('accept 后立刻 resolve 的正常路径不受影响', async () => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail
      detail.accept?.()
      detail.resolve?.()
    }
    window.addEventListener('f2-stocktake:save-items', handler)
    try {
      await expect(dispatchF2StocktakeSave([
        { item_id: 'F2-22-fields', conclusion: null, remark: '{}' },
      ])).resolves.toBeUndefined()
    } finally {
      window.removeEventListener('f2-stocktake:save-items', handler)
    }
  })

  it('空清单直接 resolve，不派发事件也不需要 accept', async () => {
    const handler = vi.fn()
    window.addEventListener('f2-stocktake:save-items', handler)
    try {
      await expect(dispatchF2StocktakeSave([])).resolves.toBeUndefined()
      expect(handler).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener('f2-stocktake:save-items', handler)
    }
  })
})
