/**
 * useD4InvoiceCompare — D4-23 收入与开具发票金额比较分析 composable
 *
 * 固定12月行 + 合计行自动汇总
 * 自动计算：营业收入合计(D) / 开票金额合计(I) / 差异(J) —— 对应 FORMULA_MASK D,I,J
 * 持久化：item_id D4-23-rows / D4-23-note / D4-23-conclusion
 * 字段键与后端 phase5_d4_ipo_related_sheets D4-23 descriptor 的 json_path 逐字对齐；
 * 行身份 = month（ROW_IDENTITY_STORE_KEY_D423）。8 受管列 A/B/C/E/F/G/H/K。
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface InvoiceCompareRow {
  month: string                 // A 月份（行身份 ROW_IDENTITY_STORE_KEY_D423）
  mainRevenue: number | string  // B 主营业务收入
  otherRevenue: number | string // C 其他业务收入
  vatInvoiceAmount: number | string  // E 增值税发票金额
  vatInvoiceCount: number | string   // F 增值税发票份数
  plainInvoiceAmount: number | string // G 普通发票金额
  plainInvoiceCount: number | string  // H 普通发票份数
  indexNo: string               // K 索引号
  // 展示派生（不持久化、不进 projection，对应 FORMULA_MASK D/I/J）
  revenueTotal: number          // D = B + C（营业收入合计）
  invoiceTotal: number          // I = E + G（开票金额合计）
  diff: number                  // J = D - I（差异）
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
  const vat = parseNum(row.vatInvoiceAmount)
  const plain = parseNum(row.plainInvoiceAmount)
  row.invoiceTotal = vat + plain
  row.diff = row.revenueTotal - row.invoiceTotal
}

// ─── Composable ──────────────────────────────────────────────────────────────

function createEmptyRow(month: string): InvoiceCompareRow {
  return { month, mainRevenue: '', otherRevenue: '', vatInvoiceAmount: '', vatInvoiceCount: '', plainInvoiceAmount: '', plainInvoiceCount: '', indexNo: '', revenueTotal: 0, invoiceTotal: 0, diff: 0 }
}

export function useD4InvoiceCompare(options: UseD4InvoiceCompareOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options

  const rows = ref<InvoiceCompareRow[]>(MONTHS.map(m => createEmptyRow(m)))
  const auditNote = ref('')
  const auditConclusion = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load ───────────────────────────────────────────────────────────
  function loadData() {
    const resp = allResponses.value.get('D4-23-rows')
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

  watch(() => allResponses.value.get('D4-23-rows')?.remark, () => loadData(), { immediate: true })
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
    let mainSum = 0, otherSum = 0, vatSum = 0, vatCountTotal = 0, plainSum = 0, plainCountSum = 0
    for (const r of rows.value) {
      mainSum += parseNum(r.mainRevenue)
      otherSum += parseNum(r.otherRevenue)
      vatSum += parseNum(r.vatInvoiceAmount)
      vatCountTotal += parseNum(r.vatInvoiceCount)
      plainSum += parseNum(r.plainInvoiceAmount)
      plainCountSum += parseNum(r.plainInvoiceCount)
    }
    const revenueTotal = mainSum + otherSum
    const invoiceTotal = vatSum + plainSum
    return { mainSum, otherSum, revenueTotal, vatSum, vatCountTotal, plainSum, plainCountSum, invoiceTotal, diff: revenueTotal - invoiceTotal }
  })

  const diffCount = computed(() => rows.value.filter(r => r.diff !== 0).length)

  // ─── Persistence ────────────────────────────────────────────────────
  function persistAll() {
    allResponses.value.set('D4-23-rows', { item_id: 'D4-23-rows', conclusion: null, remark: JSON.stringify(rows.value) })
    allResponses.value.set('D4-23-note', { item_id: 'D4-23-note', conclusion: null, remark: auditNote.value })
    allResponses.value.set('D4-23-conclusion', { item_id: 'D4-23-conclusion', conclusion: null, remark: auditConclusion.value })
    debounceSave()
  }

  function debounceSave() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave() {
    const keys = ['D4-23-rows', 'D4-23-note', 'D4-23-conclusion']
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
