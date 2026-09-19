/**
 * useK6Detail — K6-2 明细表逻辑（15列12公式，40行动态行）
 *
 * Spec: .kiro/specs/k6-held-for-sale/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 管理明细行：序号/处置组或资产名称/类别/账面原值/累计折旧摊销/减值准备/
 *   账面价值(公式)/公允价值净额/持有待售确认日/预计出售日/凭证/结论
 * - 账面价值=原值-累计折旧摊销-减值准备
 * - 合计行与K6-1审定表交叉验证
 * - 动态行新增（ElMessageBox.prompt）+ 导入导出
 * - 底部统计：处置组数/账面价值合计
 * - JSON打包存储（避免逐行存大量数据）
 *
 * Prefix: "K6-2-"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcBookValue, calcSubtotal } from './useK6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K6DetailRow {
  rowId: string
  seqNo: number
  assetName: string           // 处置组或资产名称
  category: string            // 类别（固定资产/无形资产等）
  costValue: number           // 账面原值
  accumulatedDep: number      // 累计折旧摊销
  impairmentProvision: number // 减值准备
  bookValue: number           // 账面价值（公式：原值-折旧-减值）
  fairValue: number           // 公允价值
  sellingCost: number         // 预计出售费用
  fairValueNet: number        // 公允价值净额
  recognitionDate: string     // 持有待售确认日
  expectedSaleDate: string    // 预计出售日
  voucherRef: string          // 凭证号
  conclusion: string          // 结论
  remark: string
}

export interface K6DetailSubtotals {
  costValue: number
  accumulatedDep: number
  impairmentProvision: number
  bookValue: number
  count: number
}

export interface UseK6DetailParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K6-2-rows'

const CATEGORY_OPTIONS = [
  '固定资产',
  '无形资产',
  '在建工程',
  '使用权资产',
  '投资性房地产',
  '长期股权投资',
  '其他',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK6Detail(params: UseK6DetailParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const detailRows = ref<K6DetailRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { detailRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        detailRows.value = parsed.map(_normalizeRow)
      } else {
        detailRows.value = []
      }
    } catch {
      detailRows.value = []
    }
  }

  function _normalizeRow(raw: any, idx?: number): K6DetailRow {
    const costValue = Number(raw.costValue) || 0
    const accumulatedDep = Number(raw.accumulatedDep) || 0
    const impairmentProvision = Number(raw.impairmentProvision) || 0
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      assetName: raw.assetName ?? '',
      category: raw.category ?? '',
      costValue,
      accumulatedDep,
      impairmentProvision,
      bookValue: calcBookValue(costValue, accumulatedDep, impairmentProvision),
      fairValue: Number(raw.fairValue) || 0,
      sellingCost: Number(raw.sellingCost) || 0,
      fairValueNet: Number(raw.fairValueNet) || 0,
      recognitionDate: raw.recognitionDate ?? '',
      expectedSaleDate: raw.expectedSaleDate ?? '',
      voucherRef: raw.voucherRef ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K6DetailRow): void {
    row.bookValue = calcBookValue(row.costValue, row.accumulatedDep, row.impairmentProvision)
    // 公允价值净额 = 公允价值 - 出售费用
    row.fairValueNet = row.fairValue - row.sellingCost
  }

  function recalcAll(): void {
    for (const row of detailRows.value) _recalcRow(row)
  }

  // ─── Subtotals (Req 3.5: 底部统计) ────────────────────────────────────────

  const subtotals: ComputedRef<K6DetailSubtotals> = computed(() => {
    const r = detailRows.value
    return {
      costValue: calcSubtotal(r.map(x => x.costValue)),
      accumulatedDep: calcSubtotal(r.map(x => x.accumulatedDep)),
      impairmentProvision: calcSubtotal(r.map(x => x.impairmentProvision)),
      bookValue: calcSubtotal(r.map(x => x.bookValue)),
      count: r.length,
    }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = detailRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add (Req 3.4: ElMessageBox.prompt) ────────────────────────

  async function addRow(assetName?: string): Promise<void> {
    let name = assetName
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入处置组或资产名称',
          '新增明细行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX子公司处置组',
            inputValidator: (val) => (!val?.trim() ? '名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return // 用户取消
      }
    }
    if (!name) return

    const newRow: K6DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: detailRows.value.length + 1,
      assetName: name,
      category: '',
      costValue: 0,
      accumulatedDep: 0,
      impairmentProvision: 0,
      bookValue: 0,
      fairValue: 0,
      sellingCost: 0,
      fairValueNet: 0,
      recognitionDate: '',
      expectedSaleDate: '',
      voucherRef: '',
      conclusion: '',
      remark: '',
    }
    detailRows.value.push(newRow)
    _persist()
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= detailRows.value.length) return
    detailRows.value.splice(idx, 1)
    detailRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Reorder ───────────────────────────────────────────────────────────────

  function reorderRow(fromIdx: number, toIdx: number): void {
    if (fromIdx < 0 || fromIdx >= detailRows.value.length) return
    if (toIdx < 0 || toIdx >= detailRows.value.length) return
    const [moved] = detailRows.value.splice(fromIdx, 1)
    detailRows.value.splice(toIdx, 0, moved)
    detailRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    detailRows.value = data.map((raw, i) => {
      const row = _normalizeRow(raw, i)
      _recalcRow(row)
      return row
    })
    _persist()
  }

  // ─── 统计方法（供跨sheet交叉验证） ────────────────────────────────────────

  /** 明细表账面价值合计（供K6-1审定表交叉验证） */
  function getDetailBookValueTotal(): number {
    return subtotals.value.bookValue
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(detailRows.value) })
    saveResponse('K6-2-detail-total', { remark: String(getDetailBookValueTotal()) })
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    detailRows,
    subtotals,
    categoryOptions: CATEGORY_OPTIONS,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    reorderRow,
    importRows,
    getDetailBookValueTotal,
  }
}
