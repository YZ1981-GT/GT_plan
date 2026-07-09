/**
 * useK6Impairment — K6-5 减值测试（孰低法，23行）
 *
 * Spec: .kiro/specs/k6-held-for-sale/
 * Task: 3.4
 * Requirements: 5.1-5.6
 *
 * 职责：
 * - 管理减值测试行：项目/账面价值/公允价值/预计出售费用/公允价值净额(公式)/
 *   减值金额(公式)/已计提减值/本期应补提/结论
 * - 公允价值净额 = 公允价值 - 预计出售费用
 * - 减值金额 = MAX(0, 账面价值 - 公允价值净额)（孰低法）
 * - 本期应补提 = 减值金额 - 已计提减值
 * - 与K6-1审定减值准备交叉验证
 * - JSON打包存储
 *
 * Prefix: "K6-5-"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcFairValueNet,
  calcImpairment,
  calcAdditionalProvision,
} from './useK6ImpairmentEngine'
import { calcSubtotal } from './useK6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K6ImpairmentRow {
  rowId: string
  seqNo: number
  assetName: string          // 项目（资产名称或处置组）
  bookValue: number          // 账面价值
  fairValue: number          // 公允价值
  sellingCost: number        // 预计出售费用
  fairValueNet: number       // 公允价值净额（公式）
  impairmentAmount: number   // 减值金额（公式：孰低法）
  existingProvision: number  // 已计提减值准备
  additionalProvision: number // 本期应补提（公式）
  conclusion: string         // 结论
  remark: string
}

export interface K6ImpairmentSubtotals {
  bookValue: number
  fairValueNet: number
  impairmentAmount: number
  existingProvision: number
  additionalProvision: number
  count: number
}

export interface UseK6ImpairmentParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K6-5-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK6Impairment(params: UseK6ImpairmentParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const impairmentRows = ref<K6ImpairmentRow[]>([])
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { impairmentRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        impairmentRows.value = parsed.map(_normalizeRow)
      } else {
        impairmentRows.value = []
      }
    } catch {
      impairmentRows.value = []
    }
  }

  function _normalizeRow(raw: any, idx?: number): K6ImpairmentRow {
    const bookValue = Number(raw.bookValue) || 0
    const fairValue = Number(raw.fairValue) || 0
    const sellingCost = Number(raw.sellingCost) || 0
    const fairValueNet = calcFairValueNet(fairValue, sellingCost)
    const impairmentAmount = calcImpairment(bookValue, fairValueNet)
    const existingProvision = Number(raw.existingProvision) || 0
    const additionalProvision = calcAdditionalProvision(impairmentAmount, existingProvision)

    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      assetName: raw.assetName ?? '',
      bookValue,
      fairValue,
      sellingCost,
      fairValueNet,
      impairmentAmount,
      existingProvision,
      additionalProvision,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K6ImpairmentRow): void {
    row.fairValueNet = calcFairValueNet(row.fairValue, row.sellingCost)
    row.impairmentAmount = calcImpairment(row.bookValue, row.fairValueNet)
    row.additionalProvision = calcAdditionalProvision(row.impairmentAmount, row.existingProvision)
  }

  function recalcAll(): void {
    for (const row of impairmentRows.value) _recalcRow(row)
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotals: ComputedRef<K6ImpairmentSubtotals> = computed(() => {
    const r = impairmentRows.value
    return {
      bookValue: calcSubtotal(r.map(x => x.bookValue)),
      fairValueNet: calcSubtotal(r.map(x => x.fairValueNet)),
      impairmentAmount: calcSubtotal(r.map(x => x.impairmentAmount)),
      existingProvision: calcSubtotal(r.map(x => x.existingProvision)),
      additionalProvision: calcSubtotal(r.map(x => x.additionalProvision)),
      count: r.length,
    }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = impairmentRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add ───────────────────────────────────────────────────────

  async function addRow(assetName?: string): Promise<void> {
    let name = assetName
    if (!name) {
      try {
        const { ElMessageBox } = await import('element-plus')
        const { value } = await ElMessageBox.prompt(
          '请输入资产名称',
          '新增减值测试行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX固定资产',
            inputValidator: (val) => (!val?.trim() ? '名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return
      }
    }
    if (!name) return

    const newRow: K6ImpairmentRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: impairmentRows.value.length + 1,
      assetName: name,
      bookValue: 0,
      fairValue: 0,
      sellingCost: 0,
      fairValueNet: 0,
      impairmentAmount: 0,
      existingProvision: 0,
      additionalProvision: 0,
      conclusion: '',
      remark: '',
    }
    impairmentRows.value.push(newRow)
    _persist()
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= impairmentRows.value.length) return
    impairmentRows.value.splice(idx, 1)
    impairmentRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    impairmentRows.value = data.map((raw, i) => {
      const row = _normalizeRow(raw, i)
      _recalcRow(row)
      return row
    })
    _persist()
  }

  // ─── 统计方法（供跨sheet交叉验证） ────────────────────────────────────────

  /** 减值合计（供K6-1审定表减值列交叉验证） */
  function getImpairmentTotal(): number {
    return subtotals.value.impairmentAmount
  }

  /** 应补提合计 */
  function getAdditionalProvisionTotal(): number {
    return subtotals.value.additionalProvision
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(impairmentRows.value) })
    saveResponse('K6-5-impairment-total', { remark: String(getImpairmentTotal()) })
  }

  // ─── Save Conclusion ───────────────────────────────────────────────────────

  async function saveConclusion(): Promise<void> {
    await saveResponse('K6-5-audit-conclusion', { remark: auditConclusion.value })
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => {
    _loadRows()
    const val = allResponses.value.get('K6-5-audit-conclusion')
    auditConclusion.value = val?.remark ?? val?.conclusion ?? ''
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    impairmentRows,
    subtotals,
    auditConclusion,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    getImpairmentTotal,
    getAdditionalProvisionTotal,
    saveConclusion,
  }
}
