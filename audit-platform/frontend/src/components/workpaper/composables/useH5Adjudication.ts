/**
 * useH5Adjudication — H5-1 审定表 composable
 *
 * 四区块(原值/折耗/减值/净值), 51公式, TB取数+回写
 * 三角勾稽实时校验 + 交叉验证H5-2
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 2.1-2.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcNetValue,
} from './useH5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjudicationRow {
  rowId: string
  category: string
  beginBalance: number
  debit: number
  credit: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  isSubtotal?: boolean
  isEditable?: boolean
}

export interface ReconciliationResult {
  layer: string
  difference: number
  isBalanced: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-1'

const DEFAULT_ASSET_CATEGORIES = [
  '油井资产', '气井资产', '管道设施', '集输处理设施', '钻井设备', '其他油气资产',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5Adjudication(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  crossSheetDetailCost?: Ref<number>
  crossSheetDetailDepletion?: Ref<number>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (auditedCost: number, auditedDepletion: number) => Promise<void>
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const { allResponses, onSave } = opts

  // ─── State ─────────────────────────────────────────────────────────────────

  const costRows = ref<AdjudicationRow[]>([])
  const depletionRows = ref<AdjudicationRow[]>([])
  const impairmentRows = ref<AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const costData = _getJson(`${ITEM_PREFIX}-cost-rows`)
    const deplData = _getJson(`${ITEM_PREFIX}-depletion-rows`)
    const impairData = _getJson(`${ITEM_PREFIX}-impairment-rows`)

    costRows.value = Array.isArray(costData) && costData.length > 0
      ? costData.map(_normalizeRow)
      : _buildDefaultRows(DEFAULT_ASSET_CATEGORIES, 'cost')

    depletionRows.value = Array.isArray(deplData) && deplData.length > 0
      ? deplData.map(_normalizeRow)
      : _buildDefaultRows(DEFAULT_ASSET_CATEGORIES, 'depletion')

    impairmentRows.value = Array.isArray(impairData) && impairData.length > 0
      ? impairData.map(_normalizeRow)
      : _buildDefaultRows(DEFAULT_ASSET_CATEGORIES, 'impairment')

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    const raw = item?.remark ?? item?.conclusion
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

  function _buildDefaultRows(categories: string[], block: 'cost' | 'depletion' | 'impairment'): AdjudicationRow[] {
    const prefix = block === 'cost' ? 'c' : block === 'depletion' ? 'd' : 'i'
    const subtotalLabel = block === 'cost' ? '油气资产-原值小计' : block === 'depletion' ? '累计折耗小计' : '减值准备小计'
    const rows: AdjudicationRow[] = categories.map((cat) => ({
      rowId: `row-${prefix}-${cat}`,
      category: cat,
      beginBalance: 0, debit: 0, credit: 0, endBalance: 0,
      unadjusted: 0, aje: 0, rje: 0, audited: 0,
      isSubtotal: false, isEditable: true,
    }))
    rows.push({
      rowId: `row-${prefix}-subtotal`,
      category: subtotalLabel,
      beginBalance: 0, debit: 0, credit: 0, endBalance: 0,
      unadjusted: 0, aje: 0, rje: 0, audited: 0,
      isSubtotal: true, isEditable: false,
    })
    return rows
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const costSubtotal = computed<AdjudicationRow>(() => {
    const detail = costRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 'row-c-subtotal', category: '油气资产-原值小计',
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      debit: calcSubtotal(detail.map((r) => r.debit)),
      credit: calcSubtotal(detail.map((r) => r.credit)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true, isEditable: false,
    }
  })

  const depletionSubtotal = computed<AdjudicationRow>(() => {
    const detail = depletionRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 'row-d-subtotal', category: '累计折耗小计',
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      debit: calcSubtotal(detail.map((r) => r.debit)),
      credit: calcSubtotal(detail.map((r) => r.credit)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true, isEditable: false,
    }
  })

  const impairmentSubtotal = computed<AdjudicationRow>(() => {
    const detail = impairmentRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 'row-i-subtotal', category: '减值准备小计',
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      debit: calcSubtotal(detail.map((r) => r.debit)),
      credit: calcSubtotal(detail.map((r) => r.credit)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true, isEditable: false,
    }
  })

  /** 油气资产净值 = 原值审定 - 累计折耗审定 - 减值准备审定 */
  const netValueAudited = computed(() =>
    calcNetValue(costSubtotal.value.audited, depletionSubtotal.value.audited, impairmentSubtotal.value.audited),
  )

  /** 三角勾稽校验 */
  const reconciliationResults = computed<ReconciliationResult[]>(() => {
    const cs = costSubtotal.value
    const ds = depletionSubtotal.value
    return [
      {
        layer: '原值',
        difference: calcTriangleReconciliation(cs.beginBalance, cs.debit, cs.credit, cs.endBalance),
        isBalanced: calcTriangleReconciliation(cs.beginBalance, cs.debit, cs.credit, cs.endBalance) === 0,
      },
      {
        layer: '累计折耗',
        difference: calcTriangleReconciliation(ds.beginBalance, ds.credit, ds.debit, ds.endBalance),
        isBalanced: calcTriangleReconciliation(ds.beginBalance, ds.credit, ds.debit, ds.endBalance) === 0,
      },
    ]
  })

  /** 交叉验证H5-2明细 */
  const crossValidation = computed(() => {
    const costFromDetail = opts.crossSheetDetailCost?.value ?? 0
    const deplFromDetail = opts.crossSheetDetailDepletion?.value ?? 0
    const costDiff = costSubtotal.value.audited - costFromDetail
    const deplDiff = depletionSubtotal.value.audited - deplFromDetail
    return {
      costDiff, deplDiff,
      hasCostWarning: Math.abs(costDiff) > 0.01,
      hasDepWarning: Math.abs(deplDiff) > 0.01,
    }
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(block: 'cost' | 'depletion' | 'impairment', rowId: string, field: keyof AdjudicationRow, value: number): void {
    const rows = block === 'cost' ? costRows.value : block === 'depletion' ? depletionRows.value : impairmentRows.value
    const row = rows.find((r) => r.rowId === rowId)
    if (!row || row.isSubtotal) return
    ;(row as any)[field] = value

    if (block === 'cost') {
      row.endBalance = calcAssetEndBalance(row.beginBalance, row.debit, row.credit)
    } else {
      // 备抵类（折耗+减值）：期末=期初+贷方-借方
      row.endBalance = calcContraEndBalance(row.beginBalance, row.debit, row.credit)
    }
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    _persist()
  }

  async function publishAdjudicated(): Promise<void> {
    const auditedCost = costSubtotal.value.audited
    const auditedDepl = depletionSubtotal.value.audited
    if (opts.onWritebackTB) await opts.onWritebackTB(auditedCost, auditedDepl)
    if (opts.onPublishEvent) {
      opts.onPublishEvent('substantive:adjudicated', {
        wp_code: 'H5', account_codes: ['1631', '1632'],
        cost_audited: auditedCost, depletion_audited: auditedDepl,
        net_value: netValueAudited.value,
      })
    }
  }

  function _persist(): void {
    onSave?.(`${ITEM_PREFIX}-cost-rows`, costRows.value.filter((r) => !r.isSubtotal))
    onSave?.(`${ITEM_PREFIX}-depletion-rows`, depletionRows.value.filter((r) => !r.isSubtotal))
    onSave?.(`${ITEM_PREFIX}-impairment-rows`, impairmentRows.value.filter((r) => !r.isSubtotal))
  }

  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    costRows, depletionRows, impairmentRows, auditNote, auditConclusion,
    costSubtotal, depletionSubtotal, impairmentSubtotal, netValueAudited,
    reconciliationResults, crossValidation,
    updateCell, publishAdjudicated, saveNote, saveConclusion,
  }
}
