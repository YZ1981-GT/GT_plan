/**
 * useK3LargeAmount — K3-4 大额其他应付款情况分析表（8公式）
 *
 * Spec: .kiro/specs/k3-other-payables/
 * Task: 3.4
 * Requirements: 4.1-4.4
 *
 * 职责：
 * - 从K3-2明细筛选大额其他应付款
 * - 每行：占比=余额/合计
 * - 按金额降序排列
 * - 与K3-2明细联动GtIndexChip跳转
 * - 可配阈值
 *
 * 科目：2241 其他应付款（**贷方/负债类**）
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { calcProportion, calcSubtotal } from './useK3FormulaEngine'
import type { K3DetailRow } from './useK3Detail'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K3LargeAmountRow {
  rowId: string
  seqNo: number
  counterparty: string          // 往来对象
  endBalance: number            // 期末余额
  proportion: number | null     // 占比=单项余额/合计（公式）
  nature: string                // 性质
  formationReason: string       // 形成原因
  repaymentDate: string         // 预计偿付时间
  isLongOutstanding: boolean    // 是否长期挂账
  followUpAction: string        // 后续核查
  /** 关联回K3-2 rowId用于GtIndexChip跳转 */
  sourceRowId: string
}

export interface UseK3LargeAmountParams {
  allResponses: Ref<Map<string, any>>
  detailTotal: ComputedRef<number>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K3-4-rows'
const ITEM_ID_THRESHOLD = 'K3-4-threshold'

/** 默认大额阈值（元），可由用户调整 */
const DEFAULT_THRESHOLD = 100000

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK3LargeAmount(params: UseK3LargeAmountParams) {
  const { allResponses, detailTotal } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const largeRows = ref<K3LargeAmountRow[]>([])
  const threshold = ref<number>(DEFAULT_THRESHOLD)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    // 阈值
    const thresholdItem = allResponses.value.get(ITEM_ID_THRESHOLD)
    const tv = Number(thresholdItem?.remark)
    if (Number.isFinite(tv) && tv > 0) threshold.value = tv

    // 行数据
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? null
    if (!raw) { largeRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        largeRows.value = parsed.map(_normalizeRow)
      }
    } catch {
      largeRows.value = []
    }
  }

  function _normalizeRow(raw: any, idx?: number): K3LargeAmountRow {
    return {
      rowId: raw.rowId ?? `lr-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      counterparty: raw.counterparty ?? '',
      endBalance: Number(raw.endBalance) || 0,
      proportion: null, // 由 recalc 计算
      nature: raw.nature ?? '',
      formationReason: raw.formationReason ?? '',
      repaymentDate: raw.repaymentDate ?? '',
      isLongOutstanding: Boolean(raw.isLongOutstanding),
      followUpAction: raw.followUpAction ?? '',
      sourceRowId: raw.sourceRowId ?? '',
    }
  }

  // ─── Recalc 占比 (Req 4.2) ─────────────────────────────────────────────────

  function _recalcProportions(): void {
    const total = detailTotal.value || calcSubtotal(largeRows.value.map(r => r.endBalance))
    for (const row of largeRows.value) {
      row.proportion = calcProportion(row.endBalance, total)
    }
  }

  // ─── 从K3-2明细初始化 (Req 4.4 联动) ───────────────────────────────────────

  function initFromDetail(items: K3DetailRow[]): void {
    largeRows.value = items
      .filter(d => Math.abs(d.endBalance) >= threshold.value)
      .sort((a, b) => Math.abs(b.endBalance) - Math.abs(a.endBalance))
      .map((d, i): K3LargeAmountRow => ({
        rowId: `lr-${d.rowId}`,
        seqNo: i + 1,
        counterparty: d.counterparty,
        endBalance: d.endBalance,
        proportion: null,
        nature: d.nature,
        formationReason: d.formationReason,
        repaymentDate: d.repaymentDate,
        isLongOutstanding: d.agingOver3Y > 0,
        followUpAction: '',
        sourceRowId: d.rowId,
      }))
    _recalcProportions()
  }

  // ─── 按金额降序排列 (Req 4.3) ──────────────────────────────────────────────

  function sortByAmount(): void {
    largeRows.value.sort((a, b) => Math.abs(b.endBalance) - Math.abs(a.endBalance))
    largeRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _recalcProportions()
  }

  // ─── 大额合计 ──────────────────────────────────────────────────────────────

  const largeTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(largeRows.value.map(r => r.endBalance))
  })

  const largeTotalProportion: ComputedRef<number | null> = computed(() => {
    return calcProportion(largeTotal.value, detailTotal.value)
  })

  // ─── Init from allResponses ────────────────────────────────────────────────

  function initFromResponses(): void {
    _load()
    _recalcProportions()
  }

  // ─── Watch ─────────────────────────────────────────────────────────────────

  // 初始加载
  _load()
  _recalcProportions()

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    largeRows,
    threshold,
    largeTotal,
    largeTotalProportion,
    initFromDetail,
    initFromResponses,
    sortByAmount,
  }
}
