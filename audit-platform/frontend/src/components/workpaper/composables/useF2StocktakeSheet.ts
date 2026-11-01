/**
 * useF2StocktakeSheet — F2 监盘通用行/字段持久化
 */
import { ref, watch, onBeforeUnmount, type InjectionKey, type Ref } from 'vue'
import { registerPendingFlusher } from '@/components/workpaper/sync/pendingWrites'
import type { ChecklistResponse } from './useF2StocktakeFormData'

export const F2_STOCKTAKE_BUSINESS_READONLY_KEY: InjectionKey<Readonly<Ref<boolean>>> =
  Symbol('f2-stocktake-business-readonly')

export interface F2StocktakeSaveDetail {
  items: ChecklistResponse[]
  resolve?: () => void
  reject?: (error: unknown) => void
}

/** 事件监听方必须显式 resolve/reject；超时按失败处理，不能把未落库伪装成成功。 */
export function dispatchF2StocktakeSave(items: ChecklistResponse[]): Promise<void> {
  if (!items.length) return Promise.resolve()
  return new Promise<void>((resolve, reject) => {
    let settled = false
    const timeout = setTimeout(() => {
      if (settled) return
      settled = true
      reject(new Error('监盘保存等待超时，请重试'))
    }, 8000)
    const finish = (error?: unknown) => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      if (error !== undefined) reject(error)
      else resolve()
    }
    const detail: F2StocktakeSaveDetail = {
      items,
      resolve: () => finish(),
      reject: (error) => finish(error),
    }
    window.dispatchEvent(new CustomEvent('f2-stocktake:save-items', { detail }))
  })
}

function genId(): string {
  return `st-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

/** 旧版 F2-21 地点行表 → 文本问卷字段（双读，不落库直至用户编辑） */
export function migrateF21RowsToFields(
  rowsRaw: string | null | undefined,
  existingFields: Record<string, string> | null | undefined,
): Record<string, string> | null {
  if (existingFields && Object.values(existingFields).some((v) => String(v || '').trim())) {
    return null
  }
  if (!rowsRaw) return null
  try {
    const rows = JSON.parse(rowsRaw) as Array<{
      location?: string
      inventoryType?: string
      sharePct?: string
      countDate?: string
    }>
    if (!Array.isArray(rows) || rows.length === 0) return null

    const scheduleLines = rows.map((r) => {
      const parts = [
        r.location,
        r.inventoryType,
        r.sharePct != null && r.sharePct !== '' ? `占比${r.sharePct}%` : '',
        r.countDate ? `盘点${r.countDate}` : '',
      ].filter(Boolean)
      return parts.join(' · ')
    })
    const warehouses = [...new Set(rows.map((r) => r.location).filter(Boolean))].join('\n')
    const types = [...new Set(rows.map((r) => r.inventoryType).filter(Boolean))].join('、')

    const patch: Record<string, string> = { countSchedule: scheduleLines.join('\n') }
    if (warehouses) patch.warehouses = warehouses
    if (types) patch.inventoryTypes = types
    return patch
  } catch {
    return null
  }
}

export function useF2StocktakeRows<T extends { id: string }>(opts: {
  rowsKey: string
  noteKey: string
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  emptyRow: () => T
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const rows = ref<T[]>([opts.emptyRow()])
  const auditNote = ref('')

  function load(): void {
    const raw = opts.allResponses.value.get(opts.rowsKey)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as T[]
        if (parsed.length) rows.value = parsed
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(opts.noteKey)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(opts.rowsKey)?.remark, load, { immediate: true })
  watch(() => opts.allResponses.value.get(opts.noteKey)?.remark, (v) => {
    if (v != null) auditNote.value = v
  }, { immediate: true })

  function flushSave(): Promise<void> {
    const items = [
      opts.allResponses.value.get(opts.rowsKey),
      opts.allResponses.value.get(opts.noteKey),
    ].filter(Boolean) as ChecklistResponse[]
    return dispatchF2StocktakeSave(items)
  }

  async function flushNow(): Promise<void> {
    opts.allResponses.value.set(opts.rowsKey, {
      item_id: opts.rowsKey, conclusion: null, remark: JSON.stringify(rows.value),
    })
    opts.allResponses.value.set(opts.noteKey, {
      item_id: opts.noteKey, conclusion: null, remark: auditNote.value,
    })
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    await flushSave()
  }

  async function flushPending(): Promise<void> {
    if (!debounceTimer) return
    clearTimeout(debounceTimer)
    debounceTimer = null
    await flushNow()
  }

  function persist(): void {
    opts.allResponses.value.set(opts.rowsKey, {
      item_id: opts.rowsKey, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      void flushSave().catch(() => undefined)
    }, 2000)
  }

  function updateRow(id: string, patch: Partial<T>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  function addRow(): void {
    if (readonly.value) return
    rows.value = [...rows.value, opts.emptyRow()]
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(opts.noteKey, { item_id: opts.noteKey, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      void flushSave().catch(() => undefined)
    }, 2000)
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      void flushSave().catch(() => undefined)
    }
  })

  registerPendingFlusher(flushPending)

  /**
   * Task 11: fillActualFromSample — 读 F2-25 抽盘结果，按名称匹配填入 F2-24 实盘数。
   * 适用于 rowsKey = 'F2-24-rows' 的场景（账面核对表）。
   * 返回 { matched, unmatched } 便于 UI 提示。
   */
  function fillActualFromSample(
    sampleRowsKey = 'F2-25-rows',
  ): { matched: number; unmatched: number } {
    if (readonly.value) return { matched: 0, unmatched: 0 }
    const sampleRaw = opts.allResponses.value.get(sampleRowsKey)?.remark
    if (!sampleRaw) return { matched: 0, unmatched: 0 }
    let sampleRows: Array<{ itemName?: string; sampleQty?: number; id?: string }>
    try {
      const parsed = JSON.parse(sampleRaw)
      sampleRows = Array.isArray(parsed) ? parsed : []
    } catch {
      return { matched: 0, unmatched: 0 }
    }
    if (!sampleRows.length) return { matched: 0, unmatched: 0 }

    // 按名称(小写去空白)索引抽盘数据
    const normalize = (s: string) => String(s ?? '').replace(/[\s\u3000]+/g, '').toLowerCase()
    const sampleByName: Map<string, number> = new Map()
    for (const sr of sampleRows) {
      const key = normalize(sr.itemName || '')
      if (!key) continue
      const qty = Number(sr.sampleQty) || 0
      sampleByName.set(key, (sampleByName.get(key) || 0) + qty)
    }

    let matched = 0
    let unmatched = 0
    const updated = rows.value.map((r: any) => {
      const key = normalize(r.itemName || '')
      if (!key) return r
      const actualQty = sampleByName.get(key)
      if (actualQty == null) {
        unmatched++
        return r
      }
      matched++
      // 填入 actualQty 并计算差异（不覆盖 varianceReason）
      const variance = actualQty - (Number(r.bookQty ?? r.erpQty) || 0)
      return { ...r, actualQty: actualQty, variance }
    })
    rows.value = updated as T[]
    persist()
    unmatched = sampleByName.size - matched
    return { matched, unmatched: Math.max(unmatched, 0) }
  }

  return { rows, auditNote, updateRow, addRow, removeRow, genId, flushNow, fillActualFromSample }
}

export function useF2StocktakeFields(opts: {
  fieldsKey: string
  noteKey: string
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  fieldIds: string[]
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const fields = ref<Record<string, string>>({})
  const auditNote = ref('')

  function load(): void {
    const raw = opts.allResponses.value.get(opts.fieldsKey)?.remark
    let parsed: Record<string, string> = {}
    if (raw) {
      try {
        parsed = JSON.parse(raw) as Record<string, string>
      } catch { /* ignore */ }
    }
    const base = Object.fromEntries(opts.fieldIds.map((id) => [id, '']))
    let merged = { ...base, ...parsed }

    if (opts.fieldsKey === 'F2-21-fields') {
      const legacyRows = opts.allResponses.value.get('F2-21-rows')?.remark
      const migrated = migrateF21RowsToFields(legacyRows, parsed)
      if (migrated) merged = { ...merged, ...migrated }
    }

    fields.value = merged
    auditNote.value = opts.allResponses.value.get(opts.noteKey)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(opts.fieldsKey)?.remark, load, { immediate: true })
  watch(
    () => opts.allResponses.value.get('F2-21-rows')?.remark,
    () => { if (opts.fieldsKey === 'F2-21-fields') load() },
  )

  function flushSave(): Promise<void> {
    const items = [
      opts.allResponses.value.get(opts.fieldsKey),
      opts.allResponses.value.get(opts.noteKey),
    ].filter(Boolean) as ChecklistResponse[]
    return dispatchF2StocktakeSave(items)
  }

  function persistFields(): void {
    opts.allResponses.value.set(opts.fieldsKey, {
      item_id: opts.fieldsKey, conclusion: null, remark: JSON.stringify(fields.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      void flushSave().catch(() => undefined)
    }, 2000)
  }

  /** 立即刷盘（切到在线编辑前必须调用，否则 2s debounce 未到会同步旧数据） */
  async function flushNow(): Promise<void> {
    opts.allResponses.value.set(opts.fieldsKey, {
      item_id: opts.fieldsKey, conclusion: null, remark: JSON.stringify(fields.value),
    })
    opts.allResponses.value.set(opts.noteKey, {
      item_id: opts.noteKey, conclusion: null, remark: auditNote.value,
    })
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    await flushSave()
  }

  async function flushPending(): Promise<void> {
    if (!debounceTimer) return
    clearTimeout(debounceTimer)
    debounceTimer = null
    await flushNow()
  }

  function updateField(id: string, val: string): void {
    if (readonly.value) return
    fields.value = { ...fields.value, [id]: val }
    persistFields()
  }

  /** 批量回写（AI 填入等），保留未覆盖字段，可继续二次编辑 */
  function applyFields(patch: Record<string, string>, optsApply?: { overwriteEmptyOnly?: boolean }): void {
    if (readonly.value) return
    const next = { ...fields.value }
    for (const [id, val] of Object.entries(patch)) {
      if (!opts.fieldIds.includes(id)) continue
      const text = (val ?? '').trim()
      if (!text) continue
      if (optsApply?.overwriteEmptyOnly && (next[id] || '').trim()) continue
      next[id] = text
    }
    fields.value = next
    persistFields()
    // AI 填入立即落库，不等 debounce
    void flushNow()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(opts.noteKey, { item_id: opts.noteKey, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      void flushSave().catch(() => undefined)
    }, 2000)
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      void flushSave().catch(() => undefined)
    }
  })

  registerPendingFlusher(flushPending)

  return { fields, auditNote, updateField, applyFields, flushNow }
}

export default useF2StocktakeRows
