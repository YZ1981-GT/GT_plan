/**
 * useH1Adjudication — H1-1 审定表 composable
 *
 * 双区块固定行（原值分类+折旧分类+净值合计）
 * 三角勾稽实时校验（原值层+折旧层）
 * TB取数行 + 差异行 + 交叉验证H1-2
 * updateCell + publishAdjudicated（EventBus → TB回写）
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.3
 * Requirements: 2.1-2.12
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcNetValue,
} from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行（原值区块 或 折旧区块） */
export interface AdjudicationRow {
  rowId: string
  category: string            // 资产分类名
  beginBalance: number        // 期初余额
  debit: number               // 本期借方发生(增加)
  credit: number              // 本期贷方发生(减少)
  endBalance: number          // 期末余额（公式列）
  unadjusted: number          // 未审数
  aje: number                 // AJE调整
  rje: number                 // RJE重分类
  audited: number             // 审定数（公式列）
  isSubtotal?: boolean        // 小计行标记
  isEditable?: boolean        // 可编辑标记
}

/** 三角勾稽校验结果 */
export interface ReconciliationResult {
  layer: string               // '原值' | '累计折旧'
  difference: number          // 差额（0=平衡）
  isBalanced: boolean
}

/** 差异行 */
export interface DifferenceRow {
  label: string
  audited: number
  tbAmount: number
  difference: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认资产分类 */
const DEFAULT_COST_CATEGORIES = [
  '房屋及建筑物', '机器设备', '运输设备', '电子设备', '办公设备', '其他',
]

const ITEM_PREFIX = 'H1-1'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Adjudication(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    tbUnadjusted?: Ref<{ cost1601: number; dep1602: number }>
    crossSheetCostAudited?: Ref<number>
    crossSheetDepAudited?: Ref<number>
    onSave?: (itemId: string, value: any) => void
    onWritebackTB?: (auditedCost: number, auditedDep: number) => Promise<void>
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 原值区块行 */
  const costRows = ref<AdjudicationRow[]>([])
  /** 累计折旧区块行 */
  const depRows = ref<AdjudicationRow[]>([])
  /** 审计说明 */
  const auditNote = ref('')
  /** 审计结论 */
  const auditConclusion = ref('')

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadRows(): void {
    const costData = _getJson(`${ITEM_PREFIX}-cost-rows`)
    const depData = _getJson(`${ITEM_PREFIX}-dep-rows`)

    if (Array.isArray(costData) && costData.length > 0) {
      costRows.value = costData.map(_normalizeRow)
    } else {
      costRows.value = _buildDefaultRows(DEFAULT_COST_CATEGORIES, true)
    }

    if (Array.isArray(depData) && depData.length > 0) {
      depRows.value = depData.map(_normalizeRow)
    } else {
      depRows.value = _buildDefaultRows(DEFAULT_COST_CATEGORIES, false)
    }

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): AdjudicationRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      category: raw.category ?? '',
      beginBalance: Number(raw.beginBalance) || 0,
      debit: Number(raw.debit) || 0,
      credit: Number(raw.credit) || 0,
      endBalance: Number(raw.endBalance) || 0,
      unadjusted: Number(raw.unadjusted) || 0,
      aje: Number(raw.aje) || 0,
      rje: Number(raw.rje) || 0,
      audited: Number(raw.audited) || 0,
      isSubtotal: raw.isSubtotal ?? false,
      isEditable: raw.isEditable ?? true,
    }
  }

  function _buildDefaultRows(categories: string[], isCost: boolean): AdjudicationRow[] {
    const rows: AdjudicationRow[] = categories.map((cat) => ({
      rowId: `row-${isCost ? 'c' : 'd'}-${cat}`,
      category: cat,
      beginBalance: 0, debit: 0, credit: 0, endBalance: 0,
      unadjusted: 0, aje: 0, rje: 0, audited: 0,
      isSubtotal: false, isEditable: true,
    }))
    // 小计行
    rows.push({
      rowId: `row-${isCost ? 'c' : 'd'}-subtotal`,
      category: isCost ? '固定资产-原值小计' : '累计折旧小计',
      beginBalance: 0, debit: 0, credit: 0, endBalance: 0,
      unadjusted: 0, aje: 0, rje: 0, audited: 0,
      isSubtotal: true, isEditable: false,
    })
    return rows
  }

  // ─── Computed: 小计行 ──────────────────────────────────────────────────────

  const costSubtotal = computed<AdjudicationRow>(() => {
    const detail = costRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 'row-c-subtotal',
      category: '固定资产-原值小计',
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      debit: calcSubtotal(detail.map((r) => r.debit)),
      credit: calcSubtotal(detail.map((r) => r.credit)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true,
      isEditable: false,
    }
  })

  const depSubtotal = computed<AdjudicationRow>(() => {
    const detail = depRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 'row-d-subtotal',
      category: '累计折旧小计',
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      debit: calcSubtotal(detail.map((r) => r.debit)),
      credit: calcSubtotal(detail.map((r) => r.credit)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true,
      isEditable: false,
    }
  })

  /** 固定资产净值 = 原值小计审定 - 累计折旧小计审定 */
  const netValueAudited = computed(() =>
    calcNetValue(costSubtotal.value.audited, depSubtotal.value.audited, 0),
  )

  // ─── Computed: 三角勾稽校验 ────────────────────────────────────────────────

  const reconciliationResults = computed<ReconciliationResult[]>(() => {
    const cs = costSubtotal.value
    const ds = depSubtotal.value
    return [
      {
        layer: '原值',
        difference: calcTriangleReconciliation(cs.beginBalance, cs.debit, cs.credit, cs.endBalance),
        isBalanced: calcTriangleReconciliation(cs.beginBalance, cs.debit, cs.credit, cs.endBalance) === 0,
      },
      {
        layer: '累计折旧',
        // 备抵类：期末=期初+贷方(增加)-借方(减少)
        difference: calcTriangleReconciliation(ds.beginBalance, ds.credit, ds.debit, ds.endBalance),
        isBalanced: calcTriangleReconciliation(ds.beginBalance, ds.credit, ds.debit, ds.endBalance) === 0,
      },
    ]
  })

  // ─── Computed: TB差异行 ────────────────────────────────────────────────────

  const differenceRows = computed<DifferenceRow[]>(() => {
    const tb = options?.tbUnadjusted?.value ?? { cost1601: 0, dep1602: 0 }
    const costAudited = costSubtotal.value.audited
    const depAudited = depSubtotal.value.audited
    return [
      { label: '固定资产(1601)', audited: costAudited, tbAmount: tb.cost1601, difference: costAudited - tb.cost1601 },
      { label: '累计折旧(1602)', audited: depAudited, tbAmount: tb.dep1602, difference: depAudited - tb.dep1602 },
    ]
  })

  // ─── Computed: 交叉验证 H1-2 ──────────────────────────────────────────────

  const crossValidation = computed(() => {
    const costFromDetail = options?.crossSheetCostAudited?.value ?? 0
    const depFromDetail = options?.crossSheetDepAudited?.value ?? 0
    const costDiff = costSubtotal.value.audited - costFromDetail
    const depDiff = depSubtotal.value.audited - depFromDetail
    return {
      costDiff,
      depDiff,
      hasCostWarning: Math.abs(costDiff) > 0.01,
      hasDepWarning: Math.abs(depDiff) > 0.01,
    }
  })

  // ─── updateCell ────────────────────────────────────────────────────────────

  function updateCell(
    block: 'cost' | 'dep',
    rowId: string,
    field: keyof AdjudicationRow,
    value: number,
  ): void {
    const rows = block === 'cost' ? costRows.value : depRows.value
    const row = rows.find((r) => r.rowId === rowId)
    if (!row || row.isSubtotal) return

    ;(row as any)[field] = value

    // 自动重算公式列
    if (block === 'cost') {
      row.endBalance = calcAssetEndBalance(row.beginBalance, row.debit, row.credit)
    } else {
      row.endBalance = calcContraEndBalance(row.beginBalance, row.debit, row.credit)
    }
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)

    _persist()
  }

  // ─── publishAdjudicated（EventBus + TB回写）────────────────────────────────

  async function publishAdjudicated(): Promise<void> {
    const auditedCost = costSubtotal.value.audited
    const auditedDep = depSubtotal.value.audited

    // TB回写
    if (options?.onWritebackTB) {
      await options.onWritebackTB(auditedCost, auditedDep)
    }

    // EventBus发布
    if (options?.onPublishEvent) {
      options.onPublishEvent('substantive:adjudicated', {
        wp_code: 'H1',
        account_codes: ['1601', '1602'],
        cost_audited: auditedCost,
        dep_audited: auditedDep,
        net_value: netValueAudited.value,
      })
    }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(`${ITEM_PREFIX}-cost-rows`, costRows.value.filter((r) => !r.isSubtotal))
    save(`${ITEM_PREFIX}-dep-rows`, depRows.value.filter((r) => !r.isSubtotal))
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  // Watch allResponses for reloads
  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    costRows,
    depRows,
    auditNote,
    auditConclusion,
    // Computed
    costSubtotal,
    depSubtotal,
    netValueAudited,
    reconciliationResults,
    differenceRows,
    crossValidation,
    // Actions
    updateCell,
    publishAdjudicated,
    saveNote,
    saveConclusion,
  }
}

export default useH1Adjudication
