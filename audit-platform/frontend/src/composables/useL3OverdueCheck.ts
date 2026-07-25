/**
 * useL3OverdueCheck — L3-7 逾期贷款检查 composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * 2026-07 复盘重建：
 * - 🔴 P0 修复：改为 JSON-array 存储（item_id `L3-overdue-check-rows`，与后端导入导出一致）
 *   + 从 allResponses hydrate（此前 rows 为组件本地 ref([]) 从不加载 → 刷新数据丢失 + 导入导出断裂）
 * - 逾期天数 = 报告日 − 到期日（>0 为逾期），橙/深橙/红分级高亮
 * - 🆕 逾期比例 = 逾期金额合计 / 长期借款审定数（对齐源模板，联动 L3-1）
 * - 五级风险分类（正常/关注/次级/可疑/损失）
 *
 * 存储字段（后端 _FIELD_MAPS['L3-7']）：contractNo/bankName/loanAmount/dueDate/reportDate/
 *   overdueDays/overdueAmount/isExtended/extendedDueDate/riskAssessment/remark
 * 组件内部字段保持 bank/riskEvaluation（模板兼容），序列化时映射后端字段名。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { calcOverdueDays } from '@/composables/useL3InterestEngine'
import { calcSubtotal } from '@/composables/useL3FormulaEngine'
import type { useL3FormData, ChecklistResponse } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type L3OverdueLevel = 'none' | 'low' | 'medium' | 'high'

export interface L3OverdueCheckRow {
  contractNo: string
  bank: string
  dueDate: string
  overdueDays: number
  overdueAmount: number
  isExtended: string
  riskEvaluation: string
  loanAmount?: number
  extendedDueDate?: string
  remark?: string
}

export interface L3OverdueCheckComputed extends L3OverdueCheckRow {
  computedOverdueDays: number
  overdueLevel: L3OverdueLevel
  isOverdue: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const OVERDUE_LOW_DAYS = 30
const OVERDUE_HIGH_DAYS = 90
const ITEM_ROWS = 'L3-overdue-check-rows'
/** L3-1 审定表期末审定合计（useL3Adjudication 同步写入） */
const ITEM_L3_1_AUDITED = 'L3-L3-1-adjudication-total'

// ─── 内部字段 ↔ 后端字段 映射 ────────────────────────────────────────────────

function toBackend(row: L3OverdueCheckRow, reportDate: string): Record<string, any> {
  return {
    contractNo: row.contractNo || '',
    bankName: row.bank || '',
    loanAmount: row.loanAmount || 0,
    dueDate: row.dueDate || '',
    reportDate,
    overdueDays: calcOverdueDays(row.dueDate, reportDate),
    overdueAmount: row.overdueAmount || 0,
    isExtended: row.isExtended || '',
    extendedDueDate: row.extendedDueDate || '',
    riskAssessment: row.riskEvaluation || '',
    remark: row.remark || '',
  }
}

function fromBackend(o: any): L3OverdueCheckRow {
  return {
    contractNo: o.contractNo ?? '',
    bank: o.bankName ?? o.bank ?? '',
    dueDate: o.dueDate ?? '',
    overdueDays: Number(o.overdueDays) || 0,
    overdueAmount: Number(o.overdueAmount) || 0,
    isExtended: o.isExtended ?? '',
    riskEvaluation: o.riskAssessment ?? o.riskEvaluation ?? '',
    loanAmount: Number(o.loanAmount) || 0,
    extendedDueDate: o.extendedDueDate ?? '',
    remark: o.remark ?? '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL3OverdueCheck(
  formData: ReturnType<typeof useL3FormData>,
  reportDate: string,
) {
  const { allResponses, debouncedSave } = formData
  const rows: Ref<L3OverdueCheckRow[]> = ref([])

  function hydrate(): void {
    const raw = allResponses.value.get(ITEM_ROWS)?.remark
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) rows.value = parsed.map(fromBackend)
    } catch { /* ignore */ }
  }
  hydrate()
  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (v) => { if (v && rows.value.length === 0) hydrate() },
  )

  function persist(): void {
    debouncedSave(ITEM_ROWS, { remark: JSON.stringify(rows.value.map(r => toBackend(r, reportDate))) } as Partial<ChecklistResponse>)
  }

  // ─── 计算：逾期天数+等级 ─────────────────────────────────────────────────
  const computedRows: ComputedRef<L3OverdueCheckComputed[]> = computed(() =>
    rows.value.map(row => {
      const computedOverdueDays = calcOverdueDays(row.dueDate, reportDate)
      const isOverdue = computedOverdueDays > 0
      let overdueLevel: L3OverdueLevel = 'none'
      if (isOverdue) {
        if (computedOverdueDays <= OVERDUE_LOW_DAYS) overdueLevel = 'low'
        else if (computedOverdueDays <= OVERDUE_HIGH_DAYS) overdueLevel = 'medium'
        else overdueLevel = 'high'
      }
      return { ...row, computedOverdueDays, overdueLevel, isOverdue }
    }),
  )

  // ─── 统计 ────────────────────────────────────────────────────────────────
  const overdueCount = computed(() => computedRows.value.filter(r => r.isOverdue).length)
  const totalOverdueAmount = computed(() =>
    parseFloat(calcSubtotal(computedRows.value.filter(r => r.isOverdue).map(r => r.overdueAmount)).toFixed(2)))
  const overdueSummary = computed<Record<L3OverdueLevel, number>>(() => {
    const s: Record<L3OverdueLevel, number> = { none: 0, low: 0, medium: 0, high: 0 }
    for (const row of computedRows.value) s[row.overdueLevel]++
    return s
  })

  // ─── 🆕 逾期比例 = 逾期金额合计 / 长期借款审定数（源模板核心指标，联动 L3-1） ───
  const l3AuditedTotal = computed(() => {
    const raw = allResponses.value.get(ITEM_L3_1_AUDITED)?.remark
    const n = Number(raw)
    return Number.isFinite(n) ? n : 0
  })
  const overdueRatio = computed(() => {
    const base = l3AuditedTotal.value
    if (!base || base === 0) return null   // null → UI 显示 "—"（审定数未填）
    return parseFloat(((totalOverdueAmount.value / base) * 100).toFixed(2))
  })

  // ─── 行操作 ──────────────────────────────────────────────────────────────
  function updateRow(index: number, field: keyof L3OverdueCheckRow, value: string | number): void {
    if (index < 0 || index >= rows.value.length) return
    ;(rows.value[index] as any)[field] = value
    if (field === 'dueDate') {
      rows.value[index].overdueDays = calcOverdueDays(value as string, reportDate)
    }
    persist()
  }

  function addRow(contractNo: string, bank?: string): void {
    rows.value.push({
      contractNo, bank: bank || '', dueDate: '', overdueDays: 0, overdueAmount: 0,
      isExtended: '', riskEvaluation: '', loanAmount: 0, extendedDueDate: '', remark: '',
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
    overdueCount,
    totalOverdueAmount,
    overdueSummary,
    l3AuditedTotal,
    overdueRatio,
    addRow,
    removeRow,
    updateRow,
    hydrate,
  }
}

export default useL3OverdueCheck
