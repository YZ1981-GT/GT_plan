/**
 * useK1Detail — K1-2 明细表逻辑
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 36列 3区段Tab: 基础/账龄/减值
 * - 6个账龄区间: 1年内/1-2年/2-3年/3-4年/4-5年/5年以上
 * - 动态行 CRUD + 统计(笔数/合计/3年以上占比)
 * - 与K1-1审定表合计交叉验证
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal, calcProportion } from './useK1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K1DetailRow {
  id: string
  /** 基础区段 */
  seq: number
  counterparty: string
  nature: string
  relatedParty: string
  beginBalance: number
  endBalance: number
  /** 账龄区段 */
  aging1y: number       // 1年内
  aging1to2: number     // 1-2年
  aging2to3: number     // 2-3年
  aging3to4: number     // 3-4年
  aging4to5: number     // 4-5年
  aging5plus: number    // 5年以上
  agingTotal: number    // 账龄合计（公式）
  /** 减值区段 */
  stage: 1 | 2 | 3
  badDebtProvision: number
  netValue: number
  voucherNo: string
  conclusion: string
  remark: string
}

export interface K1DetailStats {
  totalCount: number
  totalEndBalance: number
  over3YearRatio: number | null
}

export interface UseK1DetailOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const AGING_BUCKETS = ['aging1y', 'aging1to2', 'aging2to3', 'aging3to4', 'aging4to5', 'aging5plus'] as const

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1Detail(opts: UseK1DetailOpts) {
  const { allResponses } = opts

  // ─── 行数据 ────────────────────────────────────────────────────────────────

  const rows = ref<K1DetailRow[]>([])

  /** 从 allResponses 加载行数据(JSON打包存储) */
  function loadRows(): void {
    const raw = allResponses.value.get('K1-2-detail-rows')?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) ? parsed : []
    } catch { rows.value = [] }
  }

  /** 行的账龄合计（公式） */
  function calcAgingTotal(row: K1DetailRow): number {
    return calcSubtotal(AGING_BUCKETS.map(k => row[k]))
  }

  // ─── 动态行 CRUD ───────────────────────────────────────────────────────────

  function addRow(counterparty: string): K1DetailRow {
    const newRow: K1DetailRow = {
      id: `K1-2-r-${Date.now()}`,
      seq: rows.value.length + 1,
      counterparty,
      nature: '',
      relatedParty: '否',
      beginBalance: 0,
      endBalance: 0,
      aging1y: 0, aging1to2: 0, aging2to3: 0,
      aging3to4: 0, aging4to5: 0, aging5plus: 0,
      agingTotal: 0,
      stage: 1,
      badDebtProvision: 0,
      netValue: 0,
      voucherNo: '',
      conclusion: '',
      remark: '',
    }
    rows.value.push(newRow)
    return newRow
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    // 重新编号
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function updateRow(id: string, field: keyof K1DetailRow, value: any): void {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    // 自动重算账龄合计
    row.agingTotal = calcAgingTotal(row)
    // 自动重算净值
    row.netValue = row.endBalance - row.badDebtProvision
  }

  // ─── 统计 ──────────────────────────────────────────────────────────────────

  const stats: ComputedRef<K1DetailStats> = computed(() => {
    const totalCount = rows.value.length
    const totalEndBalance = calcSubtotal(rows.value.map(r => r.endBalance))
    const over3YearAmount = calcSubtotal(rows.value.map(r => r.aging3to4 + r.aging4to5 + r.aging5plus))
    const over3YearRatio = calcProportion(over3YearAmount, totalEndBalance)
    return { totalCount, totalEndBalance, over3YearRatio }
  })

  // ─── 账龄勾稽 ─────────────────────────────────────────────────────────────

  const agingMismatches: ComputedRef<string[]> = computed(() => {
    const issues: string[] = []
    for (const row of rows.value) {
      const agingSum = calcAgingTotal(row)
      if (Math.abs(agingSum - row.endBalance) > 0.01) {
        issues.push(`${row.counterparty}: 账龄合计${agingSum} ≠ 期末${row.endBalance}`)
      }
    }
    return issues
  })

  // ─── 3年以上高亮行 ──────────────────────────────────────────────────────────

  function isOver3Years(row: K1DetailRow): boolean {
    return (row.aging3to4 + row.aging4to5 + row.aging5plus) > 0
  }

  // ─── 序列化 ────────────────────────────────────────────────────────────────

  function serializeRows(): string {
    return JSON.stringify(rows.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    stats,
    agingMismatches,
    loadRows,
    addRow,
    removeRow,
    updateRow,
    isOver3Years,
    serializeRows,
  }
}
