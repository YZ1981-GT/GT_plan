/**
 * useD4CompletenessCheck — D4-15 营业收入完整性检查表 composable
 * 三维度交叉核对：发货单 × 发票 × 记账凭证
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DimensionFields {
  date: string; number: string; productName: string; quantity: string; amount: number
}

export interface CompletenessItem {
  id: string
  indexNo: string
  delivery: DimensionFields
  invoice: DimensionFields
  voucher: DimensionFields
  isConsistent: boolean | null
  remark: string
  attachmentId?: string
  attachmentName?: string
  ocrStatus?: 'none' | 'processing' | 'done' | 'failed'
}

export interface UseD4CompletenessCheckOptions {
  wpId: Ref<string>; projectId: Ref<string>
  allResponses: Ref<Map<string, any>>; isReadonly: Ref<boolean>
}

// ─── Pure functions (exported for testing) ───────────────────────────────────
export function checkConsistency(item: CompletenessItem): boolean {
  const amounts = [item.delivery.amount, item.invoice.amount, item.voucher.amount].filter(a => a > 0)
  if (amounts.length < 2) return true
  const amountsMatch = amounts.every(a => a === amounts[0])

  const names = [item.delivery.productName, item.invoice.productName, item.voucher.productName].filter(n => n.trim() !== '')
  const namesMatch = names.length < 2 || names.every(n => n === names[0])

  const qtys = [item.delivery.quantity, item.invoice.quantity, item.voucher.quantity].filter(q => q.trim() !== '')
  const qtysMatch = qtys.length < 2 || qtys.every(q => q === qtys[0])

  return amountsMatch && namesMatch && qtysMatch
}

/** Re-index completeness items sequentially. */
export function reindexCompletenessItems(items: CompletenessItem[]): void {
  items.forEach((item, i) => { item.indexNo = `D4-15-${i + 1}` })
}

/** Map OCR extracted fields to a specific dimension. */
export function mapOcrToCompleteness(
  extractedFields: Record<string, any>, dimension: 'delivery' | 'invoice' | 'voucher',
): Record<string, any> {
  const validKeys = ['date', 'number', 'productName', 'quantity', 'amount']
  const result: Record<string, any> = {}
  for (const [key, val] of Object.entries(extractedFields)) {
    if (validKeys.includes(key) && val != null && val !== '') result[key] = val
  }
  return result
}

// ─── Composable ──────────────────────────────────────────────────────────────

function createEmptyDimension(): DimensionFields {
  return { date: '', number: '', productName: '', quantity: '', amount: 0 }
}

export function useD4CompletenessCheck(options: UseD4CompletenessCheckOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options

  const items = ref<CompletenessItem[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load ───────────────────────────────────────────────────────────
  function loadItems() {
    const resp = allResponses.value.get('D4-15-items')
    if (resp?.remark) {
      try {
        const parsed = JSON.parse(resp.remark)
        if (Array.isArray(parsed) && parsed.length) { items.value = parsed; return }
      } catch { /* fallback empty */ }
    }
    items.value = []
  }

  function loadNoteConclusion() {
    auditNote.value = allResponses.value.get('D4-15-note')?.remark || ''
    auditConclusion.value = allResponses.value.get('D4-15-conclusion')?.remark || ''
  }

  watch(() => allResponses.value.get('D4-15-items')?.remark, () => loadItems(), { immediate: true })
  watch(() => allResponses.value.get('D4-15-note')?.remark, () => loadNoteConclusion(), { immediate: true })

  // ─── CRUD ───────────────────────────────────────────────────────────
  function addItem(label?: string): CompletenessItem {
    const item: CompletenessItem = {
      id: `c-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      indexNo: '',
      delivery: createEmptyDimension(),
      invoice: createEmptyDimension(),
      voucher: createEmptyDimension(),
      isConsistent: null,
      remark: label || '',
    }
    items.value.push(item)
    reindexCompletenessItems(items.value)
    persistAll()
    return item
  }

  function removeItem(id: string) {
    if (isReadonly.value) return
    items.value = items.value.filter(i => i.id !== id)
    reindexCompletenessItems(items.value)
    persistAll()
  }

  function updateField(id: string, dimension: 'delivery' | 'invoice' | 'voucher' | 'remark', field: string, value: any) {
    if (isReadonly.value) return
    const item = items.value.find(i => i.id === id)
    if (!item) return

    if (dimension === 'remark') {
      item.remark = value
    } else {
      const dim = item[dimension] as any
      if (dim) dim[field] = value
    }

    // Auto-recalculate consistency
    item.isConsistent = checkConsistency(item)
    persistAll()
  }

  // ─── Stats ──────────────────────────────────────────────────────────
  const itemCount = computed(() => items.value.length)
  const totalAmount = computed(() => items.value.reduce((sum, i) => sum + (i.delivery.amount || 0), 0))
  const consistentCount = computed(() => items.value.filter(i => i.isConsistent === true).length)
  const inconsistentCount = computed(() => items.value.filter(i => i.isConsistent === false).length)

  // ─── Persistence (debounce 2s) ───────────────────────────────────────
  function persistAll() {
    allResponses.value.set('D4-15-items', {
      item_id: 'D4-15-items',
      conclusion: null,
      remark: JSON.stringify(items.value),
    })
    allResponses.value.set('D4-15-note', {
      item_id: 'D4-15-note',
      conclusion: null,
      remark: auditNote.value,
    })
    allResponses.value.set('D4-15-conclusion', {
      item_id: 'D4-15-conclusion',
      conclusion: null,
      remark: auditConclusion.value,
    })
    debounceSave()
  }

  function debounceSave() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave() {
    const keys = ['D4-15-items', 'D4-15-note', 'D4-15-conclusion']
    const savedItems = keys.map(k => allResponses.value.get(k)).filter(Boolean)
    window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: savedItems } }))
  }

  function updateAuditNote(val: string) {
    if (isReadonly.value) return
    auditNote.value = val
    persistAll()
  }

  function updateAuditConclusion(val: string) {
    if (isReadonly.value) return
    auditConclusion.value = val
    persistAll()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  // ─── Return ─────────────────────────────────────────────────────────
  return {
    items, auditNote, auditConclusion,
    itemCount, totalAmount, consistentCount, inconsistentCount,
    addItem, removeItem, updateField, updateAuditNote, updateAuditConclusion, loadItems,
  }
}

export default useD4CompletenessCheck