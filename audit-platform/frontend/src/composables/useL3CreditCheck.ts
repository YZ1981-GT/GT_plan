/**
 * useL3CreditCheck — L3-4 征信报告核对 composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * 2026-07 复盘重建：
 * - 🔴 P0 修复：改为 JSON-array 存储（item_id `L3-credit-check-rows`，与后端导入导出一致）
 *   + 从 allResponses hydrate（此前 rows 为组件本地 ref([]) 从不加载 → 刷新数据丢失 + 导入导出断裂）
 * - 差异 = 征信借款余额 − 账面借款余额，差异≠0 红色高亮 + 要求差异说明
 * - 与 L3-2 明细合计交叉验证
 *
 * 存储字段（后端 _FIELD_MAPS['L3-4']）：bankName/creditLimit/usedCredit/creditBalance/
 *   bookBalance/difference/explanation/checkDate/remark
 * 组件内部字段保持 bank/usedLimit/diff/diffExplanation（模板兼容），序列化时映射为后端字段名。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { calcCreditDiff, calcSubtotal } from '@/composables/useL3FormulaEngine'
import type { useL3FormData, ChecklistResponse } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 征信核对行（组件内部字段名，模板兼容） */
export interface L3CreditCheckRow {
  bank: string
  creditLimit: number
  usedLimit: number
  creditBalance: number
  bookBalance: number
  diff: number
  diffExplanation: string
  checkDate?: string
  remark?: string
}

/** 征信核对计算结果行 */
export interface L3CreditCheckComputed extends L3CreditCheckRow {
  computedDiff: number
  hasDiffWarning: boolean
  needsExplanation: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DIFF_THRESHOLD = 0.01
/** 后端导入导出一致的 JSON 存储 item_id */
const ITEM_ROWS = 'L3-credit-check-rows'

// ─── 内部字段 ↔ 后端字段 映射 ────────────────────────────────────────────────

function toBackend(row: L3CreditCheckRow): Record<string, any> {
  return {
    bankName: row.bank || '',
    creditLimit: row.creditLimit || 0,
    usedCredit: row.usedLimit || 0,
    creditBalance: row.creditBalance || 0,
    bookBalance: row.bookBalance || 0,
    difference: parseFloat(calcCreditDiff(row.creditBalance, row.bookBalance).toFixed(2)),
    explanation: row.diffExplanation || '',
    checkDate: row.checkDate || '',
    remark: row.remark || '',
  }
}

function fromBackend(o: any): L3CreditCheckRow {
  const creditBalance = Number(o.creditBalance) || 0
  const bookBalance = Number(o.bookBalance) || 0
  return {
    bank: o.bankName ?? o.bank ?? '',
    creditLimit: Number(o.creditLimit) || 0,
    usedLimit: Number(o.usedCredit ?? o.usedLimit) || 0,
    creditBalance,
    bookBalance,
    diff: parseFloat(calcCreditDiff(creditBalance, bookBalance).toFixed(2)),
    diffExplanation: o.explanation ?? o.diffExplanation ?? '',
    checkDate: o.checkDate ?? '',
    remark: o.remark ?? '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL3CreditCheck(formData: ReturnType<typeof useL3FormData>) {
  const { allResponses, debouncedSave } = formData
  const rows: Ref<L3CreditCheckRow[]> = ref([])

  // ─── Hydrate（从 allResponses 解析 JSON，兼容 legacy 空） ──────────────────
  function hydrate(): void {
    const raw = allResponses.value.get(ITEM_ROWS)?.remark
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) rows.value = parsed.map(fromBackend)
    } catch { /* ignore malformed */ }
  }
  hydrate()
  // allResponses 异步加载完成后再水合一次（首次 mount 时 loadData 可能未返回）
  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (v) => { if (v && rows.value.length === 0) hydrate() },
  )

  function persist(): void {
    debouncedSave(ITEM_ROWS, { remark: JSON.stringify(rows.value.map(toBackend)) } as Partial<ChecklistResponse>)
  }

  // ─── 计算：每行差异 ──────────────────────────────────────────────────────
  const computedRows: ComputedRef<L3CreditCheckComputed[]> = computed(() =>
    rows.value.map(row => {
      const computedDiff = calcCreditDiff(row.creditBalance, row.bookBalance)
      const hasDiffWarning = Math.abs(computedDiff) > DIFF_THRESHOLD
      return {
        ...row,
        computedDiff: parseFloat(computedDiff.toFixed(2)),
        hasDiffWarning,
        needsExplanation: hasDiffWarning && (!row.diffExplanation || !row.diffExplanation.trim()),
      }
    }),
  )

  // ─── 合计 ────────────────────────────────────────────────────────────────
  const totalCreditBalance = computed(() =>
    parseFloat(calcSubtotal(rows.value.map(r => r.creditBalance)).toFixed(2)))
  const totalBookBalance = computed(() =>
    parseFloat(calcSubtotal(rows.value.map(r => r.bookBalance)).toFixed(2)))
  const totalDiff = computed(() =>
    parseFloat((totalCreditBalance.value - totalBookBalance.value).toFixed(2)))
  const warningCount = computed(() => computedRows.value.filter(r => r.hasDiffWarning).length)
  const pendingExplanationCount = computed(() => computedRows.value.filter(r => r.needsExplanation).length)

  // ─── 与 L3-2 交叉验证 ────────────────────────────────────────────────────
  function crossValidateWithDetail(detailTotalEndBalance: number): { diff: number; isConsistent: boolean } {
    const diff = parseFloat((totalBookBalance.value - detailTotalEndBalance).toFixed(2))
    return { diff, isConsistent: Math.abs(diff) <= DIFF_THRESHOLD }
  }

  // ─── 行操作 ──────────────────────────────────────────────────────────────
  function updateRow(index: number, field: keyof L3CreditCheckRow, value: string | number): void {
    if (index < 0 || index >= rows.value.length) return
    ;(rows.value[index] as any)[field] = value
    if (field === 'creditBalance' || field === 'bookBalance') {
      rows.value[index].diff = calcCreditDiff(rows.value[index].creditBalance, rows.value[index].bookBalance)
    }
    persist()
  }

  function addRow(bank: string): void {
    rows.value.push({
      bank, creditLimit: 0, usedLimit: 0, creditBalance: 0, bookBalance: 0,
      diff: 0, diffExplanation: '', checkDate: '', remark: '',
    })
    persist()
  }

  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    persist()
  }

  return {
    rows,
    computedRows,
    totalCreditBalance,
    totalBookBalance,
    totalDiff,
    warningCount,
    pendingExplanationCount,
    crossValidateWithDetail,
    addRow,
    removeRow,
    updateRow,
    hydrate,
  }
}

export default useL3CreditCheck
