/**
 * useD4InvoiceCompare — D4-23 收入与开具发票金额比较分析 composable
 *
 * 固定12月行 + 合计行自动汇总
 * 自动计算：营业收入合计 / 开票金额合计 / 差异
 * 持久化：item_id D4-23-data / D4-23-note / D4-23-conclusion
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface InvoiceCompareRow {
  month: string
  mainRevenue: number | string   // 主营业务收入
  otherRevenue: number | string  // 其他业务收入
  revenueTotal: number           // 营业收入合计（自动）
  vatAmount: number | string     // 增值税发票金额
  vatCount: number | string      // 增值税发票份数
  normalAmount: number | string  // 普通发票金额
  normalCount: number | string   // 普通发票份数
  invoiceTotal: number           // 申报开票金额合计（自动）
  diff: number                   // 差异（自动）
  indexRef: string               // 索引号
}

export interface UseD4InvoiceCompareOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
}

// ─── Pure functions ──────────────────────────────────────────────────────────

const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

export function parseNum(v: any): number {
  if (v === null || v === undefined || v === '') return 0
  const n = typeof v === 'string' ? parseFloat(v) : v
  return isNaN(n) ? 0 : n
}

export function calcRow(row: InvoiceCompareRow): void {
  const main = parseNum(row.mainRevenue)
  const other = parseNum(row.otherRevenue)
  row.revenueTotal = main + other
  const vat = parseNum(row.vatAmount)
  const normal = parseNum(row.normalAmount)
  row.invoiceTotal = vat + normal
  row.diff = row.revenueTotal - row.invoiceTotal
}

// ─── Composable ──────────────────────────────────────────────────────────────

function createEmptyRow(month: string): InvoiceCompareRow {
  return { month, mainRevenue: '', otherRevenue: '', revenueTotal: 0, vatAmount: '', vatCount: '', normalAmount: '', normalCount: '', invoiceTotal: 0, diff: 0, indexRef: '' }
}

export function useD4InvoiceCompare(options: UseD4InvoiceCompareOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options

  const rows = ref<InvoiceCompareRow[]>(MONTHS.map(m => createEmptyRow(m)))
  const auditNote = ref('')
  const auditConclusion = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load ───────────────────────────────────────────────────────────
  function loadData() {
    const resp = allResponses.value.get('D4-23-data')
    if (resp?.remark) {
      try {
        const parsed = JSON.parse(resp.remark)
        if (Array.isArray(parsed) && parsed.length === 12) {
          rows.value = parsed
          rows.value.forEach(r => calcRow(r))
          return
        }
      } catch { /* fallback */ }
    }
    rows.value = MONTHS.map(m => createEmptyRow(m))
  }

  function loadNoteConclusion() {
    auditNote.value = allResponses.value.get('D4-23-note')?.remark || ''
    auditConclusion.value = allResponses.value.get('D4-23-conclusion')?.remark || ''
  }

  watch(() => allResponses.value.get('D4-23-data')?.remark, () => loadData(), { immediate: true })
  watch(() => allResponses.value.get('D4-23-note')?.remark, () => loadNoteConclusion(), { immediate: true })

  // ─── Update ─────────────────────────────────────────────────────────
  function updateCell(monthIdx: number, field: keyof InvoiceCompareRow, value: any) {
    if (isReadonly.value) return
    const row = rows.value[monthIdx]
    if (!row) return
    ;(row as any)[field] = value
    calcRow(row)
    persistAll()
  }

  // ─── Stats ──────────────────────────────────────────────────────────
  const totals = computed(() => {
    let mainSum = 0, otherSum = 0, vatSum = 0, vatCountSum = 0, normalSum = 0, normalCountSum = 0
    for (const r of rows.value) {
      mainSum += parseNum(r.mainRevenue)
      otherSum += parseNum(r.otherRevenue)
      vatSum += parseNum(r.vatAmount)
      vatCountSum += parseNum(r.vatCount)
      normalSum += parseNum(r.normalAmount)
      normalCountSum += parseNum(r.normalCount)
    }
    const revenueTotal = mainSum + otherSum
    const invoiceTotal = vatSum + normalSum
    return { mainSum, otherSum, revenueTotal, vatSum, vatCountSum, normalSum, normalCountSum, invoiceTotal, diff: revenueTotal - invoiceTotal }
  })

  const diffCount = computed(() => rows.value.filter(r => r.diff !== 0).length)

  // ─── Persistence ────────────────────────────────────────────────────
  function persistAll() {
    allResponses.value.set('D4-23-data', { item_id: 'D4-23-data', conclusion: null, remark: JSON.stringify(rows.value) })
    allResponses.value.set('D4-23-note', { item_id: 'D4-23-note', conclusion: null, remark: auditNote.value })
    allResponses.value.set('D4-23-conclusion', { item_id: 'D4-23-conclusion', conclusion: null, remark: auditConclusion.value })
    debounceSave()
  }

  function debounceSave() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave() {
    const keys = ['D4-23-data', 'D4-23-note', 'D4-23-conclusion']
    const items = keys.map(k => allResponses.value.get(k)).filter(Boolean)
    window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
  }

  function updateAuditNote(val: string) { if (isReadonly.value) return; auditNote.value = val; persistAll() }
  function updateAuditConclusion(val: string) { if (isReadonly.value) return; auditConclusion.value = val; persistAll() }

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return {
    rows, auditNote, auditConclusion, totals, diffCount,
    updateCell, updateAuditNote, updateAuditConclusion, loadData,
  }
}

export default useD4InvoiceCompare
