/**
 * useK1BadDebt — K1-3 坏账准备明细逻辑
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.4
 * Requirements: 4.1-4.5
 *
 * 职责：
 * - 21公式 + 计提/转回/核销管理
 * - 三阶段转入转出矩阵
 * - 与K1-8测算交叉验证
 * - 与K1-1审定坏账准备合计一致
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { calcBadDebtEnd, calcProportion, calcSubtotal } from './useK1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K1BadDebtRow {
  id: string
  label: string
  beginBadDebt: number
  provision: number      // 本期计提
  reversal: number       // 本期转回
  writeoff: number       // 本期核销
  endBadDebt: number     // 期末坏账（公式: 期初+计提-转回-核销）
  provisionRate: number | null  // 计提比例
  receivableEnd: number  // 对应应收款期末（取自K1-2）
  stage: 1 | 2 | 3
  remark: string
}

export interface K1BadDebtCrossValidation {
  calcProvision: number   // K1-8测算应计提
  bookedProvision: number // 企业计提
  diff: number            // 差异
  isMatch: boolean        // |diff|<0.01
}

export interface UseK1BadDebtOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1BadDebt(opts: UseK1BadDebtOpts) {
  const { allResponses } = opts

  const rows = ref<K1BadDebtRow[]>([])

  // ─── 加载行数据 ────────────────────────────────────────────────────────────

  function loadRows(): void {
    const raw = allResponses.value.get('K1-3-baddebt-rows')?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) ? parsed.map(recalcRow) : []
    } catch { rows.value = [] }
  }

  function recalcRow(row: K1BadDebtRow): K1BadDebtRow {
    row.endBadDebt = calcBadDebtEnd(row.beginBadDebt, row.provision, row.reversal, row.writeoff)
    row.provisionRate = calcProportion(row.endBadDebt, row.receivableEnd)
    return row
  }

  // ─── 动态行 CRUD ───────────────────────────────────────────────────────────

  function addRow(label: string): K1BadDebtRow {
    const newRow: K1BadDebtRow = {
      id: `K1-3-r-${Date.now()}`,
      label,
      beginBadDebt: 0,
      provision: 0,
      reversal: 0,
      writeoff: 0,
      endBadDebt: 0,
      provisionRate: null,
      receivableEnd: 0,
      stage: 1,
      remark: '',
    }
    rows.value.push(newRow)
    return newRow
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
  }

  function updateRow(id: string, field: keyof K1BadDebtRow, value: any): void {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    // 重算
    row.endBadDebt = calcBadDebtEnd(row.beginBadDebt, row.provision, row.reversal, row.writeoff)
    row.provisionRate = calcProportion(row.endBadDebt, row.receivableEnd)
  }

  // ─── 合计 ──────────────────────────────────────────────────────────────────

  const totalEndBadDebt: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.endBadDebt))
  )

  const totalProvision: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.provision))
  )

  // ─── 三阶段转入转出矩阵 ────────────────────────────────────────────────────

  const stageMatrix: ComputedRef<Record<1 | 2 | 3, { count: number; total: number }>> = computed(() => {
    const matrix: Record<number, { count: number; total: number }> = { 1: { count: 0, total: 0 }, 2: { count: 0, total: 0 }, 3: { count: 0, total: 0 } }
    for (const row of rows.value) {
      matrix[row.stage].count++
      matrix[row.stage].total += row.endBadDebt
    }
    return matrix as Record<1 | 2 | 3, { count: number; total: number }>
  })

  // ─── 与K1-8测算交叉验证 ────────────────────────────────────────────────────

  const crossValidation: ComputedRef<K1BadDebtCrossValidation> = computed(() => {
    // K1-8 测算应计提合计
    const calcProvision = Number(allResponses.value.get('K1-8-calc-total-provision')?.remark) || 0
    const bookedProvision = totalEndBadDebt.value
    const diff = calcProvision - bookedProvision
    return { calcProvision, bookedProvision, diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── 序列化 ────────────────────────────────────────────────────────────────

  function serializeRows(): string {
    return JSON.stringify(rows.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    totalEndBadDebt,
    totalProvision,
    stageMatrix,
    crossValidation,
    loadRows,
    addRow,
    removeRow,
    updateRow,
    serializeRows,
  }
}
