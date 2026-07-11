/**
 * useH3TransferReview — H3-6 互转审核表 composable
 *
 * 三方向分区(自用→投资/投资→自用/在建→投资) + 25公式
 * + 转出=转入验证 + EventBus联动H1/H2 + GtIndexChip跳转 + 方法论上下文
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.11
 * Requirements: 7.1-7.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  calcSelfToInvestFair,
  calcInvestToSelf,
  calcCipToInvestCost,
  calcCipToInvestFair,
  calcTransferDiff,
} from './useH3TransferEngine'
import { calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type TransferDirection = 'selfToInvest' | 'investToSelf' | 'cipToInvest'

export interface H3TransferRow {
  rowId: string
  direction: TransferDirection
  assetName: string
  transferDate: string
  bookValue: number           // 账面价值
  fairValue: number           // 转换日公允价值
  entryValue: number          // 入账价值（公式）
  ociAmount: number           // 其他综合收益
  plAmount: number            // 当期损益影响
  transferOut: number         // 转出金额
  transferIn: number          // 转入金额
  diff: number                // 差额（公式）
  sourceWp: string            // 来源底稿(H1/H2)
  sourceRef: string           // GtIndexChip跳转引用
  remark: string
}

const ITEM_ID = 'H3-6-transfer-rows'

export function useH3TransferReview(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
  measurementModel: Ref<string>
}) {
  const { allResponses, getValue, setValue, measurementModel } = params
  const rows = ref<H3TransferRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any): H3TransferRow {
    const dir = raw.direction ?? 'selfToInvest'
    const book = Number(raw.bookValue) || 0
    const fair = Number(raw.fairValue) || 0
    const out = Number(raw.transferOut) || 0
    const inAmt = Number(raw.transferIn) || 0
    let entry = Number(raw.entryValue) || 0
    let oci = 0
    let pl = 0

    if (dir === 'selfToInvest') {
      const r = calcSelfToInvestFair(book, fair)
      oci = r.oci; pl = r.pl
      entry = fair
    } else if (dir === 'investToSelf') {
      entry = calcInvestToSelf(fair)
    } else if (dir === 'cipToInvest') {
      if (measurementModel.value === 'fair_value') {
        const r = calcCipToInvestFair(book, fair)
        entry = r.entryValue; pl = r.diff
      } else {
        entry = calcCipToInvestCost(book)
      }
    }

    return {
      rowId: raw.rowId ?? `tr-${Math.random().toString(36).slice(2, 8)}`,
      direction: dir,
      assetName: raw.assetName ?? '',
      transferDate: raw.transferDate ?? '',
      bookValue: book,
      fairValue: fair,
      entryValue: entry,
      ociAmount: oci,
      plAmount: pl,
      transferOut: out,
      transferIn: inAmt,
      diff: calcTransferDiff(out, inAmt),
      sourceWp: raw.sourceWp ?? (dir === 'cipToInvest' ? 'H2' : 'H1'),
      sourceRef: raw.sourceRef ?? '',
      remark: raw.remark ?? '',
    }
  }

  /** 按方向分组 */
  const selfToInvestRows = computed(() => rows.value.filter((r) => r.direction === 'selfToInvest'))
  const investToSelfRows = computed(() => rows.value.filter((r) => r.direction === 'investToSelf'))
  const cipToInvestRows = computed(() => rows.value.filter((r) => r.direction === 'cipToInvest'))

  /** 差异行（diff≠0需红色高亮） */
  const hasImbalance = computed(() => rows.value.some((r) => Math.abs(r.diff) > 0.01))

  const totalSummary = computed(() => ({
    fromH1: calcSubtotal(selfToInvestRows.value.map((r) => r.transferIn)),
    toH1: calcSubtotal(investToSelfRows.value.map((r) => r.transferOut)),
    fromH2: calcSubtotal(cipToInvestRows.value.map((r) => r.transferIn)),
    ociTotal: calcSubtotal(rows.value.map((r) => r.ociAmount)),
    plTotal: calcSubtotal(rows.value.map((r) => r.plAmount)),
  }))

  function addRow(direction: TransferDirection): void {
    rows.value.push(_normalize({ direction, rowId: `tr-${Date.now()}` }))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    _persist()
  }

  function updateCell(index: number, field: keyof H3TransferRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : (Number(value) || value)
    // Recompute formulas
    const recalced = _normalize({ ...row })
    Object.assign(row, recalced)
    _persist()
  }

  /**
   * 行变更（组件按方向分组视图调用 updateTransferRow(direction, index, row)）。
   * 组件已 v-model 就地修改 row（与 rows 中同引用），此处按 rowId 定位后重算公式并持久化。
   */
  function updateTransferRow(_direction: string, _index: number, row: any): void {
    const target = row?.rowId ? rows.value.find((r) => r.rowId === row.rowId) : null
    if (!target) return
    const recalced = _normalize({ ...target })
    Object.assign(target, recalced)
    _persist()
  }

  /** EventBus发布互转事件 */
  function publishTransferEvents(): void {
    window.dispatchEvent(new CustomEvent('h3:transfer-from-h1', {
      detail: { rows: selfToInvestRows.value.concat(investToSelfRows.value) },
    }))
    window.dispatchEvent(new CustomEvent('h3:transfer-from-h2', {
      detail: { rows: cipToInvestRows.value },
    }))
  }

  function _persist(): void { setValue(ITEM_ID, rows.value) }
  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    rows, selfToInvestRows, investToSelfRows, cipToInvestRows,
    hasImbalance, totalSummary,
    addRow, removeRow, updateCell, updateTransferRow, publishTransferEvents, loadRows,
  }
}

export default useH3TransferReview
