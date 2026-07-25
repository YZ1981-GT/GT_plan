/**
 * useL3PledgeCheck — L3-8 抵质押资产检查 composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * 2026-07 复盘重建：
 * - 🔴 P0 修复：改为 JSON-array 存储（item_id `L3-pledge-check-rows`，与后端导入导出一致）
 *   + 从 allResponses hydrate（此前 rows 为组件本地 ref([]) 从不加载 → 刷新数据丢失 + 导入导出断裂）
 * - 担保比例 = 担保借款 / 账面价值 × 100%，>100% 红色警告（担保不足）
 * - 🆕 评估价值列（对齐源模板/后端字段 appraisalValue）
 *
 * 存储字段（后端 _FIELD_MAPS['L3-8']）：assetName/assetType/bookValue/appraisalValue/
 *   guaranteedLoan/pledgeRatio/ownershipProof/isRestricted/registrationDate/remark
 * 组件内部字段保持 ownershipVerified（模板兼容），序列化时映射后端字段名。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { calcPledgeRatio, calcSubtotal } from '@/composables/useL3FormulaEngine'
import type { useL3FormData, ChecklistResponse } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface L3PledgeCheckRow {
  assetName: string
  assetType: string
  bookValue: number
  appraisalValue: number
  guaranteedLoan: number
  pledgeRatio: number
  ownershipVerified: string
  appraisalDate: string
  remark: string
}

export interface L3PledgeCheckComputed extends L3PledgeCheckRow {
  computedRatio: number
  hasRatioWarning: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const RATIO_WARNING_THRESHOLD = 100
const ITEM_ROWS = 'L3-pledge-check-rows'

// ─── 内部字段 ↔ 后端字段 映射 ────────────────────────────────────────────────

function toBackend(row: L3PledgeCheckRow): Record<string, any> {
  return {
    assetName: row.assetName || '',
    assetType: row.assetType || '',
    bookValue: row.bookValue || 0,
    appraisalValue: row.appraisalValue || 0,
    guaranteedLoan: row.guaranteedLoan || 0,
    pledgeRatio: parseFloat(calcPledgeRatio(row.guaranteedLoan, row.bookValue).toFixed(2)),
    ownershipProof: row.ownershipVerified || '',
    isRestricted: '',
    registrationDate: row.appraisalDate || '',
    remark: row.remark || '',
  }
}

function fromBackend(o: any): L3PledgeCheckRow {
  return {
    assetName: o.assetName ?? '',
    assetType: o.assetType ?? '',
    bookValue: Number(o.bookValue) || 0,
    appraisalValue: Number(o.appraisalValue) || 0,
    guaranteedLoan: Number(o.guaranteedLoan) || 0,
    pledgeRatio: Number(o.pledgeRatio) || 0,
    ownershipVerified: o.ownershipProof ?? o.ownershipVerified ?? '',
    appraisalDate: o.registrationDate ?? o.appraisalDate ?? '',
    remark: o.remark ?? '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL3PledgeCheck(formData: ReturnType<typeof useL3FormData>) {
  const { allResponses, debouncedSave } = formData
  const rows: Ref<L3PledgeCheckRow[]> = ref([])

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
    debouncedSave(ITEM_ROWS, { remark: JSON.stringify(rows.value.map(toBackend)) } as Partial<ChecklistResponse>)
  }

  // ─── 计算：每行担保比例 ──────────────────────────────────────────────────
  const computedRows: ComputedRef<L3PledgeCheckComputed[]> = computed(() =>
    rows.value.map(row => {
      const computedRatio = calcPledgeRatio(row.guaranteedLoan, row.bookValue)
      return {
        ...row,
        computedRatio: parseFloat(computedRatio.toFixed(2)),
        hasRatioWarning: computedRatio > RATIO_WARNING_THRESHOLD,
      }
    }),
  )

  // ─── 统计 ────────────────────────────────────────────────────────────────
  const totalGuaranteedLoan = computed(() =>
    parseFloat(calcSubtotal(rows.value.map(r => r.guaranteedLoan)).toFixed(2)))
  const totalBookValue = computed(() =>
    parseFloat(calcSubtotal(rows.value.map(r => r.bookValue)).toFixed(2)))
  const totalAppraisalValue = computed(() =>
    parseFloat(calcSubtotal(rows.value.map(r => r.appraisalValue)).toFixed(2)))
  const overallRatio = computed(() =>
    parseFloat(calcPledgeRatio(totalGuaranteedLoan.value, totalBookValue.value).toFixed(2)))
  const warningCount = computed(() => computedRows.value.filter(r => r.hasRatioWarning).length)

  // ─── 行操作 ──────────────────────────────────────────────────────────────
  function updateRow(index: number, field: keyof L3PledgeCheckRow, value: string | number): void {
    if (index < 0 || index >= rows.value.length) return
    ;(rows.value[index] as any)[field] = value
    if (field === 'guaranteedLoan' || field === 'bookValue') {
      rows.value[index].pledgeRatio = calcPledgeRatio(rows.value[index].guaranteedLoan, rows.value[index].bookValue)
    }
    persist()
  }

  function addRow(assetName: string): void {
    rows.value.push({
      assetName, assetType: '', bookValue: 0, appraisalValue: 0, guaranteedLoan: 0,
      pledgeRatio: 0, ownershipVerified: '', appraisalDate: '', remark: '',
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
    totalGuaranteedLoan,
    totalBookValue,
    totalAppraisalValue,
    overallRatio,
    warningCount,
    addRow,
    removeRow,
    updateRow,
    hydrate,
  }
}

export default useL3PledgeCheck
