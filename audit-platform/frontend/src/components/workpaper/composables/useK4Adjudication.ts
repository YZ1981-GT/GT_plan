/**
 * useK4Adjudication — K4-1 审定表逻辑（21行×14列，负债类72公式）
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理审定表状态：项目/期初/贷方/借方/期末/未审/AJE/RJE/审定数/变动率/备注
 * - 使用 useK4FormulaEngine 的 calcAuditedAmount, calcLiabilityEndBalance, calcChangeRate
 * - 三角勾稽校验（期末=期初+贷方-借方）
 * - Computed: 期末/审定数/变动率 由输入列派生
 * - Save to checklist_responses with prefix "K4-1-"
 * - Integration: writebackTB(2245) on audited change
 *
 * 科目：2245 其他流动负债（**贷方/负债类**）
 * ⚠️ 负债类！期末=期初+贷方-借方（与资产类相反）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcTriangleReconciliation,
  calcChangeRate,
  calcSubtotal,
} from './useK4FormulaEngine'
import type { K4TbData } from './useK4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K4AdjRow {
  rowKey: string
  label: string
  begin: number        // 期初余额
  credit: number       // 本期贷方发生额（增加，负债增加在贷方）
  debit: number        // 本期借方发生额（减少，负债减少在借方）
  end: number          // 期末余额（公式：期初+贷-借）
  unadjusted: number   // 未审数
  aje: number          // AJE
  rje: number          // RJE
  audited: number      // 审定数（公式：未审+AJE+RJE）
  changeRate: number | null  // 变动率
  remark: string
}

export interface K4ReconciliationResult {
  diff: number
  isBalanced: boolean
}

export interface UseK4AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  tbData: Ref<K4TbData>
  saveResponse: Function
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVal(map: Map<string, any>, itemId: string): string {
  const item = map.get(itemId)
  if (!item) return ''
  return item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')
}

function num(map: Map<string, any>, itemId: string): number {
  const v = getVal(map, itemId)
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── 预设行标签（K4-1 审定表21行） ─────────────────────────────────────────────

// 对齐致同源模板 K4-1 审定表项目行（4 类型 + 其他）
const ROW_LABELS = [
  '短期应付债券',
  '政府补助',
  '待转销项税额',
  '应付退货款',
  '其他',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK4Adjudication(params: UseK4AdjudicationParams) {
  const { allResponses, tbData, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const auditConclusion = ref('')

  // ─── 构建行数据（负债类！期末=期初+贷-借） ────────────────────────────────────

  function buildRow(rowKey: string, label: string): K4AdjRow {
    const id = `K4-1-${rowKey}`
    const begin = num(allResponses.value, `${id}-begin`)
    const credit = num(allResponses.value, `${id}-credit`)
    const debit = num(allResponses.value, `${id}-debit`)
    // 负债类！期末=期初+贷方-借方
    const end = calcLiabilityEndBalance(begin, credit, debit)
    const unadjusted = num(allResponses.value, `${id}-unadj`)
    const aje = num(allResponses.value, `${id}-aje`)
    const rje = num(allResponses.value, `${id}-rje`)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const prior = num(allResponses.value, `${id}-prior-audited`)
    const changeRate = calcChangeRate(audited, prior)
    const remark = getVal(allResponses.value, `${id}-remark`)
    return { rowKey, label, begin, credit, debit, end, unadjusted, aje, rje, audited, changeRate, remark }
  }

  // ─── 行数据 ────────────────────────────────────────────────────────────────

  const rows: ComputedRef<K4AdjRow[]> = computed(() => {
    const count = num(allResponses.value, 'K4-1-row-count') || ROW_LABELS.length
    const result: K4AdjRow[] = []
    for (let i = 0; i < count; i++) {
      const label = getVal(allResponses.value, `K4-1-r${i}-label`) || ROW_LABELS[i] || `项目${i + 1}`
      result.push(buildRow(`r${i}`, label))
    }
    return result
  })

  // ─── 合计行 ────────────────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<K4AdjRow> = computed(() => {
    const r = rows.value
    const s = (fn: (row: K4AdjRow) => number) => calcSubtotal(r.map(fn))
    const audited = s(row => row.audited)
    const priorTotal = s(row => num(allResponses.value, `K4-1-${row.rowKey}-prior-audited`))
    return {
      rowKey: 'subtotal',
      label: '合计',
      begin: s(row => row.begin),
      credit: s(row => row.credit),
      debit: s(row => row.debit),
      end: s(row => row.end),
      unadjusted: s(row => row.unadjusted),
      aje: s(row => row.aje),
      rje: s(row => row.rje),
      audited,
      changeRate: calcChangeRate(audited, priorTotal),
      remark: '',
    }
  })

  // ─── 三角勾稽校验 (Req 2.4) ─────────────────────────────────────────────────

  const reconciliation: ComputedRef<K4ReconciliationResult> = computed(() => {
    const row = subtotalRow.value
    // 负债类：增加=贷方 减少=借方
    const diff = calcTriangleReconciliation(row.begin, row.credit, row.debit, row.end)
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── 从 allResponses 初始化审计说明 ────────────────────────────────────────

  function initFromResponses(): void {
    auditConclusion.value = getVal(allResponses.value, 'K4-1-audit-conclusion')
  }

  // ─── 保存全部 ──────────────────────────────────────────────────────────────

  async function saveAll(): Promise<void> {
    // 保存审计结论
    await saveResponse('K4-1-audit-conclusion', { remark: auditConclusion.value })
    // 保存审定数合计供跨sheet使用
    await saveResponse('K4-1-audited-total', { remark: String(subtotalRow.value.audited) })
    // 保存本期借方/贷方合计供 K4-4 检查比例联动
    await saveResponse('K4-1-subtotal-debit', { remark: String(subtotalRow.value.debit) })
    await saveResponse('K4-1-subtotal-credit', { remark: String(subtotalRow.value.credit) })
  }

  // ─── 获取审定数合计（供TB回写） ────────────────────────────────────────────

  function getAuditedTotal(): number {
    return subtotalRow.value.audited
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    subtotalRow,
    auditConclusion,
    reconciliation,
    initFromResponses,
    saveAll,
    getAuditedTotal,
  }
}
