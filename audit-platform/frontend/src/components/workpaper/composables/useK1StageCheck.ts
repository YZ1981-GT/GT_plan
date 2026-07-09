/**
 * useK1StageCheck — K1-7 三阶段划分检查
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.4
 * Requirements: 5.1-5.5
 *
 * 职责：
 * - 63行: 往来对象/余额/信用风险判定/阶段(公式)
 * - Stage 3红色/Stage 2橙色/Stage 1默认
 * - 与K1-2明细阶段列联动
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { determineStage } from './useK1ECLEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K1StageRow {
  id: string
  counterparty: string
  endBalance: number
  isSignificantIncrease: boolean  // 信用风险是否显著增加
  isImpaired: boolean             // 是否已发生信用减值
  stage: 1 | 2 | 3               // 划分阶段（公式）
  priorStage: 1 | 2 | 3          // 上期阶段
  changeNote: string              // 变动说明
}

export interface K1StageSummary {
  stage1Count: number
  stage2Count: number
  stage3Count: number
  stage1Total: number
  stage2Total: number
  stage3Total: number
}

export interface UseK1StageCheckOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1StageCheck(opts: UseK1StageCheckOpts) {
  const { allResponses } = opts

  const rows = ref<K1StageRow[]>([])

  // ─── 加载行数据 ────────────────────────────────────────────────────────────

  function loadRows(): void {
    const raw = allResponses.value.get('K1-7-stage-rows')?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) ? parsed.map(recalcStage) : []
    } catch { rows.value = [] }
  }

  /** 根据判定条件重算阶段 */
  function recalcStage(row: K1StageRow): K1StageRow {
    row.stage = determineStage(row.isImpaired, row.isSignificantIncrease)
    return row
  }

  // ─── 行更新 ────────────────────────────────────────────────────────────────

  function updateRow(id: string, field: keyof K1StageRow, value: any): void {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    // 重算阶段
    row.stage = determineStage(row.isImpaired, row.isSignificantIncrease)
  }

  function addRow(counterparty: string, endBalance: number): K1StageRow {
    const newRow: K1StageRow = {
      id: `K1-7-r-${Date.now()}`,
      counterparty,
      endBalance,
      isSignificantIncrease: false,
      isImpaired: false,
      stage: 1,
      priorStage: 1,
      changeNote: '',
    }
    rows.value.push(newRow)
    return newRow
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
  }

  // ─── 行样式 ────────────────────────────────────────────────────────────────

  function getRowStyle(row: K1StageRow): string {
    if (row.stage === 3) return 'background-color: #fde2e2' // 红色
    if (row.stage === 2) return 'background-color: #fdf0e2' // 橙色
    return ''
  }

  // ─── 统计 ──────────────────────────────────────────────────────────────────

  const summary: ComputedRef<K1StageSummary> = computed(() => {
    const s: K1StageSummary = { stage1Count: 0, stage2Count: 0, stage3Count: 0, stage1Total: 0, stage2Total: 0, stage3Total: 0 }
    for (const row of rows.value) {
      if (row.stage === 1) { s.stage1Count++; s.stage1Total += row.endBalance }
      else if (row.stage === 2) { s.stage2Count++; s.stage2Total += row.endBalance }
      else { s.stage3Count++; s.stage3Total += row.endBalance }
    }
    return s
  })

  // ─── 与K1-2联动 ───────────────────────────────────────────────────────────

  /** 同步阶段到 K1-2 明细的 stage 列 */
  function syncStagesToDetail(): Map<string, 1 | 2 | 3> {
    const map = new Map<string, 1 | 2 | 3>()
    for (const row of rows.value) {
      map.set(row.counterparty, row.stage)
    }
    return map
  }

  // ─── 序列化 ────────────────────────────────────────────────────────────────

  function serializeRows(): string {
    return JSON.stringify(rows.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    summary,
    loadRows,
    addRow,
    removeRow,
    updateRow,
    getRowStyle,
    syncStagesToDetail,
    serializeRows,
  }
}
