/**
 * useK7Adjudication — K7-1 审定表逻辑（54行×13列，49公式，负债类）
 *
 * Spec: .kiro/specs/k7-deferred-income/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理审定表状态：项目/期初/本期增加(收到)/本期减少(分摊)/期末/未审/AJE/RJE/审定数/上期审定/变动率/变动原因
 * - 按"与资产相关/与收益相关"分组
 * - 负债类公式：期末=期初+收到-分摊 (calcLiabilityEndBalance)
 * - 审定数=未审+AJE+RJE (calcAuditedAmount)
 * - 合计行=calcSubtotal(group rows)
 * - 三角勾稽：endBalance should equal detailSubtotal (from cross-sheet)
 * - TB回写: when audited total changes, emit event to parent for writebackTB(2401)
 * - Virtual scroll hint: 54行
 *
 * 科目：2401 递延收益（**贷方/负债类**）
 * ⚠️ 负债类！期末=期初+收到(贷方增加)-分摊(借方减少)
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from './useK7FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K7AdjRow {
  rowKey: string
  project: string              // 补助项目名称
  group: '与资产相关' | '与收益相关'
  beginBalance: number         // 期初余额
  received: number             // 本期增加（收到/贷方）
  amortized: number            // 本期减少（分摊/借方）
  unadjustedEnd: number        // 期末余额（公式：期初+收到-分摊）
  unadj: number                // 未审数
  aje: number                  // AJE
  rje: number                  // RJE
  audited: number              // 审定数（公式：未审+AJE+RJE）
  priorAudited: number         // 上期审定数
  changeRate: number           // 变动率
  changeReason: string         // 变动原因
}

export interface K7AdjSubtotalRow {
  label: string
  beginBalance: number
  received: number
  amortized: number
  unadjustedEnd: number
  unadj: number
  aje: number
  rje: number
  audited: number
  priorAudited: number
}

export interface K7ReconciliationResult {
  /** 审定合计 - 明细期末合计 */
  diff: number
  isBalanced: boolean
}

export interface UseK7AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
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

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K7-1-rows'

/** 预设行标签 — 按"与资产相关/与收益相关"分组 */
const DEFAULT_ROWS: Array<{ project: string; group: K7AdjRow['group'] }> = [
  { project: '设备购置补助', group: '与资产相关' },
  { project: '厂房建设补助', group: '与资产相关' },
  { project: '技改项目补助', group: '与资产相关' },
  { project: '研发费用补助', group: '与收益相关' },
  { project: '稳岗补贴', group: '与收益相关' },
  { project: '其他收益类补助', group: '与收益相关' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK7Adjudication(params: UseK7AdjudicationParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K7AdjRow[]>([])
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? null
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed) && parsed.length > 0) {
          rows.value = parsed.map(_normalizeRow)
          _recalcAll()
          auditConclusion.value = getVal(allResponses.value, 'K7-1-audit-conclusion')
          return
        }
      } catch { /* fallthrough to default */ }
    }
    // 从 allResponses 单字段模式加载（兼容）
    rows.value = DEFAULT_ROWS.map((def, i) => _buildRowFromResponses(`r${i}`, def.project, def.group))
    auditConclusion.value = getVal(allResponses.value, 'K7-1-audit-conclusion')
  }

  function _normalizeRow(raw: any): K7AdjRow {
    const row: K7AdjRow = {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      project: raw.project ?? '',
      group: raw.group ?? '与资产相关',
      beginBalance: Number(raw.beginBalance) || 0,
      received: Number(raw.received) || 0,
      amortized: Number(raw.amortized) || 0,
      unadjustedEnd: 0,
      unadj: Number(raw.unadj) || 0,
      aje: Number(raw.aje) || 0,
      rje: Number(raw.rje) || 0,
      audited: 0,
      priorAudited: Number(raw.priorAudited) || 0,
      changeRate: 0,
      changeReason: raw.changeReason ?? '',
    }
    _recalcRow(row)
    return row
  }

  function _buildRowFromResponses(rowKey: string, project: string, group: K7AdjRow['group']): K7AdjRow {
    const id = `K7-1-${rowKey}`
    const begin = num(allResponses.value, `${id}-begin`)
    const received = num(allResponses.value, `${id}-received`)
    const amortized = num(allResponses.value, `${id}-amortized`)
    const unadj = num(allResponses.value, `${id}-unadj`)
    const aje = num(allResponses.value, `${id}-aje`)
    const rje = num(allResponses.value, `${id}-rje`)
    const priorAudited = num(allResponses.value, `${id}-prior`)
    const changeReason = getVal(allResponses.value, `${id}-reason`)

    const row: K7AdjRow = {
      rowKey, project, group,
      beginBalance: begin,
      received,
      amortized,
      unadjustedEnd: 0,
      unadj,
      aje,
      rje,
      audited: 0,
      priorAudited,
      changeRate: 0,
      changeReason,
    }
    _recalcRow(row)
    return row
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K7AdjRow): void {
    // 负债类：期末=期初+收到-分摊
    row.unadjustedEnd = calcLiabilityEndBalance(row.beginBalance, row.received, row.amortized)
    // 审定=未审+AJE+RJE
    row.audited = calcAuditedAmount(row.unadj, row.aje, row.rje)
    // 变动率 = (审定-上期审定)/|上期审定|
    row.changeRate = row.priorAudited !== 0
      ? (row.audited - row.priorAudited) / Math.abs(row.priorAudited)
      : 0
  }

  function _recalcAll(): void {
    for (const row of rows.value) _recalcRow(row)
  }

  // ─── 分组行 ────────────────────────────────────────────────────────────────

  const assetRelatedRows: ComputedRef<K7AdjRow[]> = computed(() =>
    rows.value.filter(r => r.group === '与资产相关'),
  )

  const incomeRelatedRows: ComputedRef<K7AdjRow[]> = computed(() =>
    rows.value.filter(r => r.group === '与收益相关'),
  )

  // ─── 合计行 ────────────────────────────────────────────────────────────────

  function _buildSubtotal(label: string, groupRows: K7AdjRow[]): K7AdjSubtotalRow {
    const s = (fn: (row: K7AdjRow) => number) => calcSubtotal(groupRows.map(fn))
    return {
      label,
      beginBalance: s(r => r.beginBalance),
      received: s(r => r.received),
      amortized: s(r => r.amortized),
      unadjustedEnd: s(r => r.unadjustedEnd),
      unadj: s(r => r.unadj),
      aje: s(r => r.aje),
      rje: s(r => r.rje),
      audited: s(r => r.audited),
      priorAudited: s(r => r.priorAudited),
    }
  }

  const assetSubtotal: ComputedRef<K7AdjSubtotalRow> = computed(() =>
    _buildSubtotal('与资产相关小计', assetRelatedRows.value),
  )

  const incomeSubtotal: ComputedRef<K7AdjSubtotalRow> = computed(() =>
    _buildSubtotal('与收益相关小计', incomeRelatedRows.value),
  )

  const grandTotal: ComputedRef<K7AdjSubtotalRow> = computed(() =>
    _buildSubtotal('合计', rows.value),
  )

  // ─── 三角勾稽校验 (Req 2.4, 2.5) ──────────────────────────────────────────

  /** 审定表合计 vs K7-2 明细表期末合计 */
  const reconciliation: ComputedRef<K7ReconciliationResult> = computed(() => {
    const auditedTotal = grandTotal.value.audited
    const detailEndTotal = num(allResponses.value, 'K7-2-detail-end-total')
    const diff = auditedTotal - detailEndTotal
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── 动态行新增（按分组） ──────────────────────────────────────────────────

  function addRow(project: string, group: K7AdjRow['group']): void {
    const newRow: K7AdjRow = {
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      project,
      group,
      beginBalance: 0,
      received: 0,
      amortized: 0,
      unadjustedEnd: 0,
      unadj: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      priorAudited: 0,
      changeRate: 0,
      changeReason: '',
    }
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(rowKey: string): void {
    const idx = rows.value.findIndex(r => r.rowKey === rowKey)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      _persist()
    }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
    // 同步审定合计到 allResponses 供 CrossSheet computed 链使用
    saveResponse('K7-1-audited-total', { remark: String(grandTotal.value.audited) })
  }

  // ─── Save All ──────────────────────────────────────────────────────────────

  async function saveAll(): Promise<void> {
    await saveResponse('K7-1-audit-conclusion', { remark: auditConclusion.value })
    _persist()
  }

  // ─── 公开方法 ──────────────────────────────────────────────────────────────

  /** 获取审定合计（供 TB 回写 2401 + CrossSheet） */
  function getAuditedTotal(): number {
    return grandTotal.value.audited
  }

  /** 获取分组审定数 */
  function getAssetRelatedAudited(): number {
    return assetSubtotal.value.audited
  }

  function getIncomeRelatedAudited(): number {
    return incomeSubtotal.value.audited
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    assetRelatedRows,
    incomeRelatedRows,
    assetSubtotal,
    incomeSubtotal,
    grandTotal,
    auditConclusion,
    reconciliation,
    updateCell,
    addRow,
    removeRow,
    initFromResponses,
    saveAll,
    getAuditedTotal,
    getAssetRelatedAudited,
    getIncomeRelatedAudited,
  }
}
