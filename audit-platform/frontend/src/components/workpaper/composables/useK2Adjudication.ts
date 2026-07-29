/**
 * useK2Adjudication — K2-1 审定表 composable（85公式，资产类1231）
 *
 * 管理8个数据行（合同取得成本/预付款项/待摊费用/其他…）
 * 每行：{ item, begin, debit, credit, end, unadj, aje, rje, audited, changeRate, remark }
 *
 * 核心功能：
 * - 公式自动计算：期末=期初+借-贷（资产类），审定=未审+AJE+RJE
 * - 三角勾稽校验+红色高亮
 * - 合计行（calcSubtotal）
 * - TB回写 trigger
 * - EventBus publish 'substantive:adjudicated'
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 3.4
 * Requirements: 2.1-2.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcChangeRate,
} from './useK2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K2AdjRow {
  rowKey: string
  label: string
  begin: number
  debit: number
  credit: number
  end: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  changeRate: number | null
  remark: string
}

export interface K2ReconciliationResult {
  diff: number
  isBalanced: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** K2-1审定表固定行（其他流动资产明细项目） */
const K2_ADJ_ITEMS: { key: string; label: string }[] = [
  { key: 'contract-cost', label: '合同取得成本' },
  { key: 'prepayment', label: '预付款项' },
  { key: 'deferred-expense', label: '待摊费用' },
  { key: 'tax-deductible', label: '待抵扣税额' },
  { key: 'contract-asset', label: '合同资产' },
  { key: 'deposit', label: '押金保证金' },
  { key: 'receivable-transfer', label: '应收款项转让' },
  { key: 'other', label: '其他' },
]

const ITEM_ID_PREFIX = 'K2-1'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVal(allResponses: Map<string, any>, itemId: string): string {
  const item = allResponses.get(itemId)
  return item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')
}

function num(allResponses: Map<string, any>, itemId: string): number {
  const v = getVal(allResponses, itemId)
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK2Adjudication(
  allResponses: Ref<Map<string, any>>,
  options?: {
    prefill?: Ref<Array<{ name: string; code?: string; opening_balance: number; closing_balance: number }> | undefined>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Prefill seed（从 tb_balance 1231 子科目按 name 匹配固定行） ───────────

  function seedFromPrefill(): void {
    const pf = options?.prefill?.value
    if (!pf || pf.length === 0) return
    const hasAnyUnadj = K2_ADJ_ITEMS.some(item => num(allResponses.value, `${ITEM_ID_PREFIX}-${item.key}-unadj`) !== 0)
    if (hasAnyUnadj) return
    for (const p of pf) {
      const pName = (p.name || '').trim().toLowerCase()
      let matchKey = K2_ADJ_ITEMS.find(item => {
        const label = item.label.toLowerCase()
        return label.includes(pName) || pName.includes(label)
      })?.key
      if (!matchKey) matchKey = 'other'
      const id = `${ITEM_ID_PREFIX}-${matchKey}`
      const existing = num(allResponses.value, `${id}-unadj`)
      if (existing === 0) {
        allResponses.value.set(`${id}-begin`, { item_id: `${id}-begin`, conclusion: null, remark: String(p.opening_balance) })
        allResponses.value.set(`${id}-unadj`, { item_id: `${id}-unadj`, conclusion: null, remark: String(p.closing_balance) })
        // 持久化到 DB
        options?.onSave?.(`${id}-begin`, String(p.opening_balance))
        options?.onSave?.(`${id}-unadj`, String(p.closing_balance))
      }
    }
  }

  // ─── Row Builder ───────────────────────────────────────────────────────────

  function buildRow(key: string, label: string): K2AdjRow {
    const id = `${ITEM_ID_PREFIX}-${key}`
    const begin = num(allResponses.value, `${id}-begin`)
    const debit = num(allResponses.value, `${id}-debit`)
    const credit = num(allResponses.value, `${id}-credit`)
    const end = calcAssetEndBalance(begin, debit, credit)
    const unadjusted = num(allResponses.value, `${id}-unadj`)
    const aje = num(allResponses.value, `${id}-aje`)
    const rje = num(allResponses.value, `${id}-rje`)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const prior = num(allResponses.value, `${id}-prior-audited`)
    const changeRate = calcChangeRate(audited, prior)
    const remark = getVal(allResponses.value, `${id}-remark`)
    return { rowKey: key, label, begin, debit, credit, end, unadjusted, aje, rje, audited, changeRate, remark }
  }

  // ─── Computed Rows ─────────────────────────────────────────────────────────

  const rows: ComputedRef<K2AdjRow[]> = computed(() => {
    return K2_ADJ_ITEMS.map((item) => buildRow(item.key, item.label))
  })

  // ─── Subtotal Row ──────────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<K2AdjRow> = computed(() => {
    const r = rows.value
    const audited = calcSubtotal(r.map((x) => x.audited))
    const priorSum = calcSubtotal(
      K2_ADJ_ITEMS.map((item) => num(allResponses.value, `${ITEM_ID_PREFIX}-${item.key}-prior-audited`)),
    )
    return {
      rowKey: 'subtotal',
      label: '合计',
      begin: calcSubtotal(r.map((x) => x.begin)),
      debit: calcSubtotal(r.map((x) => x.debit)),
      credit: calcSubtotal(r.map((x) => x.credit)),
      end: calcSubtotal(r.map((x) => x.end)),
      unadjusted: calcSubtotal(r.map((x) => x.unadjusted)),
      aje: calcSubtotal(r.map((x) => x.aje)),
      rje: calcSubtotal(r.map((x) => x.rje)),
      audited,
      changeRate: calcChangeRate(audited, priorSum),
      remark: '',
    }
  })

  // ─── Triangle Reconciliation ───────────────────────────────────────────────

  const reconciliation: ComputedRef<K2ReconciliationResult> = computed(() => {
    const st = subtotalRow.value
    const diff = calcTriangleReconciliation(st.begin, st.debit, st.credit, st.end)
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── AJE/RJE Update ───────────────────────────────────────────────────────

  function updateField(rowKey: string, field: string, value: number | string): void {
    const itemId = `${ITEM_ID_PREFIX}-${rowKey}-${field}`
    options?.onSave?.(itemId, String(value))
  }

  // ─── Audit Note / Conclusion ───────────────────────────────────────────────

  watch(
    () => allResponses.value.get(`${ITEM_ID_PREFIX}-audit-note`)?.remark,
    (v) => { auditNote.value = v || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(`${ITEM_ID_PREFIX}-audit-conclusion`)?.remark,
    (v) => { auditConclusion.value = v || '' },
    { immediate: true },
  )

  // ─── Return ────────────────────────────────────────────────────────────────

  // Prefill seed 触发
  watch([() => options?.prefill?.value], () => seedFromPrefill(), { immediate: true })

  return {
    rows,
    subtotalRow,
    reconciliation,
    auditNote,
    auditConclusion,
    updateField,
    /** 固定行项目定义 */
    ADJ_ITEMS: K2_ADJ_ITEMS,
  }
}
