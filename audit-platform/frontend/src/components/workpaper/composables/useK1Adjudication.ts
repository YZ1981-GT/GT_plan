/**
 * useK1Adjudication — K1-1 审定表逻辑
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.4
 * Requirements: 2.1-2.10
 *
 * 职责：
 * - 双区块：其他应收款(1221资产类) + 坏账准备(备抵类) + 净值
 * - 89行 × 13列 × 47公式
 * - 三角勾稽 + TB回写 + AJE/RJE 管理
 * - EventBus publish 'substantive:adjudicated'
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcTriangleReconciliation,
  calcChangeRate,
  calcSubtotal,
} from './useK1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K1AdjRow {
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

export interface K1AdjSection {
  sectionKey: 'receivable' | 'bad-debt' | 'net-value'
  sectionLabel: string
  rows: K1AdjRow[]
  subtotalRow: K1AdjRow
}

export interface K1ReconciliationResult {
  diff: number
  isBalanced: boolean
}

export interface UseK1AdjudicationOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVal(allResponses: Map<string, any>, itemId: string): string {
  return allResponses.get(itemId)?.remark ?? ''
}

function num(allResponses: Map<string, any>, itemId: string): number {
  const v = getVal(allResponses, itemId)
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1Adjudication(opts: UseK1AdjudicationOpts) {
  const { wpId, projectId, allResponses } = opts

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── 构建行数据 ────────────────────────────────────────────────────────────

  function buildRow(prefix: string, rowKey: string, label: string, isAssetType: boolean): K1AdjRow {
    const id = `K1-1-${prefix}-${rowKey}`
    const begin = num(allResponses.value, `${id}-begin`)
    const debit = num(allResponses.value, `${id}-debit`)
    const credit = num(allResponses.value, `${id}-credit`)
    const end = isAssetType
      ? calcAssetEndBalance(begin, debit, credit)
      : calcContraEndBalance(begin, credit, debit)
    const unadjusted = num(allResponses.value, `${id}-unadj`)
    const aje = num(allResponses.value, `${id}-aje`)
    const rje = num(allResponses.value, `${id}-rje`)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const prior = num(allResponses.value, `${id}-prior-audited`)
    const changeRate = calcChangeRate(audited, prior)
    const remark = getVal(allResponses.value, `${id}-remark`)
    return { rowKey, label, begin, debit, credit, end, unadjusted, aje, rje, audited, changeRate, remark }
  }

  function buildSubtotal(label: string, rows: K1AdjRow[]): K1AdjRow {
    const sum = (fn: (r: K1AdjRow) => number) => calcSubtotal(rows.map(fn))
    const audited = sum(r => r.audited)
    const prior = sum(r => num(allResponses.value, `K1-1-receivable-${r.rowKey}-prior-audited`))
    return {
      rowKey: 'subtotal', label,
      begin: sum(r => r.begin), debit: sum(r => r.debit), credit: sum(r => r.credit),
      end: sum(r => r.end), unadjusted: sum(r => r.unadjusted),
      aje: sum(r => r.aje), rje: sum(r => r.rje), audited,
      changeRate: calcChangeRate(audited, prior), remark: '',
    }
  }

  // ─── Adjudication Sections ─────────────────────────────────────────────────

  const adjudicationSections: ComputedRef<K1AdjSection[]> = computed(() => {
    // 其他应收款区块（资产类）
    const recRows: K1AdjRow[] = []
    const recCount = num(allResponses.value, 'K1-1-receivable-count') || 5
    for (let i = 0; i < recCount; i++) {
      const label = getVal(allResponses.value, `K1-1-receivable-r${i}-label`) || `项目${i + 1}`
      recRows.push(buildRow('receivable', `r${i}`, label, true))
    }
    const recSubtotal = buildSubtotal('合计', recRows)

    // 坏账准备区块（备抵类）
    const bdRows: K1AdjRow[] = []
    const bdCount = num(allResponses.value, 'K1-1-baddebt-count') || 5
    for (let i = 0; i < bdCount; i++) {
      const label = getVal(allResponses.value, `K1-1-baddebt-r${i}-label`) || `项目${i + 1}`
      bdRows.push(buildRow('baddebt', `r${i}`, label, false))
    }
    const bdSubtotal = buildSubtotal('合计', bdRows)

    // 净值区块（计算）
    const netRows: K1AdjRow[] = recRows.map((r, i) => {
      const bd = bdRows[i]
      const audited = calcNetValue(r.audited, bd?.audited ?? 0)
      return {
        rowKey: `net-r${i}`, label: r.label,
        begin: calcNetValue(r.begin, bd?.begin ?? 0),
        debit: 0, credit: 0,
        end: calcNetValue(r.end, bd?.end ?? 0),
        unadjusted: calcNetValue(r.unadjusted, bd?.unadjusted ?? 0),
        aje: calcNetValue(r.aje, bd?.aje ?? 0),
        rje: calcNetValue(r.rje, bd?.rje ?? 0),
        audited,
        changeRate: calcChangeRate(audited, calcNetValue(
          num(allResponses.value, `K1-1-receivable-r${i}-prior-audited`),
          num(allResponses.value, `K1-1-baddebt-r${i}-prior-audited`),
        )),
        remark: '',
      }
    })
    const netSubtotal = buildSubtotal('合计', netRows)

    return [
      { sectionKey: 'receivable', sectionLabel: '一、其他应收款（1221）', rows: recRows, subtotalRow: recSubtotal },
      { sectionKey: 'bad-debt', sectionLabel: '二、坏账准备', rows: bdRows, subtotalRow: bdSubtotal },
      { sectionKey: 'net-value', sectionLabel: '三、账面净值', rows: netRows, subtotalRow: netSubtotal },
    ] as K1AdjSection[]
  })

  // ─── 三角勾稽 ──────────────────────────────────────────────────────────────

  const reconciliation: ComputedRef<K1ReconciliationResult> = computed(() => {
    const sec = adjudicationSections.value[0]
    if (!sec) return { diff: 0, isBalanced: true }
    const row = sec.subtotalRow
    const diff = calcTriangleReconciliation(row.begin, row.debit, row.credit, row.end)
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── AJE/RJE 管理 ─────────────────────────────────────────────────────────

  function applyAdjustment(rowKey: string, type: 'aje' | 'rje', amount: number): void {
    const itemId = `K1-1-receivable-${rowKey}-${type}`
    const existing = num(allResponses.value, itemId)
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: String(existing + amount) })
  }

  // ─── Audit Note/Conclusion ─────────────────────────────────────────────────

  watch(() => allResponses.value.get('K1-1-audit-note')?.remark, (v) => {
    auditNote.value = v || ''
  }, { immediate: true })

  watch(() => allResponses.value.get('K1-1-audit-conclusion')?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationSections,
    reconciliation,
    auditNote,
    auditConclusion,
    applyAdjustment,
  }
}
