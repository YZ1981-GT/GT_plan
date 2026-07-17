/**
 * useF2SubcontractCheck — F2-35 委托加工物资核查（三表）
 */
import { ref, computed, watch, onBeforeUnmount, getCurrentInstance, type Ref } from 'vue'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  emptySubBasic,
  emptySubSupplier1,
  emptySubSupplier2,
  calcSubClosing,
  calcSubtotal,
  type SubcontractBasicRow,
  type SubcontractSupplier1Row,
  type SubcontractSupplier2Row,
} from './useF2InspectionCheckFormulas'

export function useF2SubcontractSheet(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const sheetCode = 'F2-35' as const

  const basicRows = ref<SubcontractBasicRow[]>([emptySubBasic(1)])
  const supplier1Rows = ref<SubcontractSupplier1Row[]>([emptySubSupplier1(1)])
  const supplier2Rows = ref<SubcontractSupplier2Row[]>([emptySubSupplier2(1)])
  const auditNote = ref('')
  const meta = ref<Record<string, string>>({
    entityName: '',
    cutoffDate: '',
    sampleNote: '',
    processNote: '',
  })

  function loadArr<T>(key: string, fallback: T[]): T[] {
    const raw = readValRowJson(opts.allResponses.value.get(key))
    if (!raw) return fallback
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) && parsed.length ? parsed : fallback
    } catch {
      return fallback
    }
  }

  function load(): void {
    basicRows.value = loadArr(`${sheetCode}-basic-rows`, [emptySubBasic(1)]).map((r) => ({
      ...r,
      closing: calcSubClosing(r),
    }))
    supplier1Rows.value = loadArr(`${sheetCode}-supplier1-rows`, [emptySubSupplier1(1)])
    supplier2Rows.value = loadArr(`${sheetCode}-supplier2-rows`, [emptySubSupplier2(1)])
    // 兼容旧单表数据：若新表空且旧 F2-35-rows 有内容，提示性迁到 supplier2
    const legacy = loadArr<Record<string, unknown>>(`${sheetCode}-rows`, [])
    if (
      supplier2Rows.value.length <= 1
      && !supplier2Rows.value[0]?.processor
      && legacy.length
      && (legacy[0].party || legacy[0].itemName)
    ) {
      supplier2Rows.value = legacy.map((r, i) => ({
        ...emptySubSupplier2(i + 1),
        processor: String(r.party || ''),
        contractNo: String(r.docNo || ''),
        issueCost: Number(r.amount || 0) || 0,
        remark: String(r.remark || r.itemName || ''),
        indexRef: String(r.voucherNo || ''),
      }))
    }
    auditNote.value = opts.allResponses.value.get(`${sheetCode}-note`)?.remark || ''
    try {
      const mr = opts.allResponses.value.get(`${sheetCode}-meta`)?.remark
      if (mr) meta.value = { ...meta.value, ...JSON.parse(mr) }
    } catch { /* ignore */ }
  }

  watch(
    () => [
      opts.allResponses.value.get(`${sheetCode}-basic-rows`)?.remark,
      opts.allResponses.value.get(`${sheetCode}-supplier1-rows`)?.remark,
      opts.allResponses.value.get(`${sheetCode}-supplier2-rows`)?.remark,
    ],
    () => load(),
    { immediate: true },
  )

  const unrecoveredCount = computed(() =>
    supplier2Rows.value.filter((r) => r.issueCost > 0 && r.recoverCost + 0.01 < r.issueCost).length,
  )
  const feeTotal = computed(() => calcSubtotal(supplier1Rows.value.map((r) => r.feeAmount)))
  const closingTotal = computed(() => calcSubtotal(basicRows.value.map((r) => r.closing)))

  function flushSave(): void {
    const keys = [
      `${sheetCode}-basic-rows`,
      `${sheetCode}-supplier1-rows`,
      `${sheetCode}-supplier2-rows`,
      `${sheetCode}-note`,
      `${sheetCode}-meta`,
    ]
    const items = keys.map((k) => opts.allResponses.value.get(k)).filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items } }))
  }

  function schedulePersist(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function setJson(key: string, data: unknown): void {
    opts.allResponses.value.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(data) })
    schedulePersist()
  }

  function persistAll(): void {
    if (readonly.value) return
    setJson(`${sheetCode}-basic-rows`, basicRows.value)
    setJson(`${sheetCode}-supplier1-rows`, supplier1Rows.value)
    setJson(`${sheetCode}-supplier2-rows`, supplier2Rows.value)
  }

  function updateMeta(patch: Record<string, string>): void {
    if (readonly.value) return
    meta.value = { ...meta.value, ...patch }
    opts.allResponses.value.set(`${sheetCode}-meta`, {
      item_id: `${sheetCode}-meta`, conclusion: null, remark: JSON.stringify(meta.value),
    })
    schedulePersist()
  }

  function updateBasic(id: string, patch: Partial<SubcontractBasicRow>): void {
    if (readonly.value) return
    basicRows.value = basicRows.value.map((r) => {
      if (r.id !== id) return r
      const merged = { ...r, ...patch }
      merged.closing = calcSubClosing(merged)
      return merged
    })
    persistAll()
  }

  function updateSupplier1(id: string, patch: Partial<SubcontractSupplier1Row>): void {
    if (readonly.value) return
    supplier1Rows.value = supplier1Rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persistAll()
  }

  function updateSupplier2(id: string, patch: Partial<SubcontractSupplier2Row>): void {
    if (readonly.value) return
    supplier2Rows.value = supplier2Rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persistAll()
  }

  function addBasic(): void {
    if (readonly.value) return
    basicRows.value = [...basicRows.value, emptySubBasic(basicRows.value.length + 1)]
    persistAll()
  }
  function addSupplier1(): void {
    if (readonly.value) return
    supplier1Rows.value = [...supplier1Rows.value, emptySubSupplier1(supplier1Rows.value.length + 1)]
    persistAll()
  }
  function addSupplier2(): void {
    if (readonly.value) return
    supplier2Rows.value = [...supplier2Rows.value, emptySubSupplier2(supplier2Rows.value.length + 1)]
    persistAll()
  }

  function removeBasic(id: string): void {
    if (readonly.value || basicRows.value.length <= 1) return
    basicRows.value = basicRows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }
  function removeSupplier1(id: string): void {
    if (readonly.value || supplier1Rows.value.length <= 1) return
    supplier1Rows.value = supplier1Rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }
  function removeSupplier2(id: string): void {
    if (readonly.value || supplier2Rows.value.length <= 1) return
    supplier2Rows.value = supplier2Rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(`${sheetCode}-note`, { item_id: `${sheetCode}-note`, conclusion: null, remark: val })
    schedulePersist()
  })

  if (getCurrentInstance()) {
    onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })
  }

  return {
    sheetCode,
    title: '委托加工物资核查表',
    meta,
    updateMeta,
    basicRows,
    supplier1Rows,
    supplier2Rows,
    auditNote,
    unrecoveredCount,
    feeTotal,
    closingTotal,
    updateBasic,
    updateSupplier1,
    updateSupplier2,
    addBasic,
    addSupplier1,
    addSupplier2,
    removeBasic,
    removeSupplier1,
    removeSupplier2,
  }
}
