/**
 * useK5Warranty — K5-4 产品质量保修检查表逻辑
 *
 * Spec: .kiro/specs/k5-provisions/
 * Task: 3.4
 * Requirements: 6.1-6.4
 *
 * 职责：
 * - 管理产品质量保修检查行（产品/销售收入/历史保修率/预计保修支出/期初/计提/使用/期末/结论）
 * - 公式：预计保修支出=销售收入×历史保修率
 * - 与K5-1产品质量保证行交叉验证
 * - AI辅助生成结论
 * - Save with prefix "K5-4-"
 *
 * 科目：2701 预计负债-产品质量保证（**贷方/负债类**）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcWarrantyProvision } from './useK5BestEstimateEngine'
import { calcLiabilityEndBalance, calcSubtotal } from './useK5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K5WarrantyRow {
  rowId: string
  seqNo: number
  productName: string         // 产品名称
  revenue: number             // 销售收入
  warrantyRate: number        // 历史保修率（小数，如0.02=2%）
  estimatedExpense: number    // 预计保修支出（公式：收入×保修率）
  beginBalance: number        // 期初余额
  periodProvision: number     // 本期计提
  periodUsed: number          // 本期使用（转销）
  endBalance: number          // 期末余额（公式：期初+计提-使用）
  conclusion: string          // 结论
  remark: string
}

export interface K5WarrantySubtotals {
  revenue: number
  estimatedExpense: number
  beginBalance: number
  periodProvision: number
  periodUsed: number
  endBalance: number
  count: number
}

export interface K5WarrantyCrossCheck {
  /** K5-4 期末合计 */
  warrantyTotal: number
  /** K5-1 产品质保行审定数（从allResponses读取） */
  adjudicationWarranty: number
  /** 差异 */
  diff: number
  /** 是否一致 */
  isMatch: boolean
}

export interface UseK5WarrantyParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K5-4-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5Warranty(params: UseK5WarrantyParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const warrantyRows = ref<K5WarrantyRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { warrantyRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        warrantyRows.value = parsed.map(_normalizeRow)
      } else {
        warrantyRows.value = []
      }
    } catch {
      warrantyRows.value = []
    }
  }

  function _normalizeRow(raw: any, idx?: number): K5WarrantyRow {
    const row: K5WarrantyRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      productName: raw.productName ?? '',
      revenue: Number(raw.revenue) || 0,
      warrantyRate: Number(raw.warrantyRate) || 0,
      estimatedExpense: 0,
      beginBalance: Number(raw.beginBalance) || 0,
      periodProvision: Number(raw.periodProvision) || 0,
      periodUsed: Number(raw.periodUsed) || 0,
      endBalance: 0,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
    _recalcRow(row)
    return row
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K5WarrantyRow): void {
    // 预计保修支出=销售收入×历史保修率
    row.estimatedExpense = calcWarrantyProvision(row.revenue, row.warrantyRate)
    // 负债类期末=期初+计提-使用
    row.endBalance = calcLiabilityEndBalance(row.beginBalance, row.periodProvision, row.periodUsed)
  }

  function recalcAll(): void {
    for (const row of warrantyRows.value) _recalcRow(row)
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotals: ComputedRef<K5WarrantySubtotals> = computed(() => {
    const r = warrantyRows.value
    return {
      revenue: calcSubtotal(r.map(x => x.revenue)),
      estimatedExpense: calcSubtotal(r.map(x => x.estimatedExpense)),
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      periodProvision: calcSubtotal(r.map(x => x.periodProvision)),
      periodUsed: calcSubtotal(r.map(x => x.periodUsed)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      count: r.length,
    }
  })

  // ─── 与K5-1交叉验证 (Req 6.3) ─────────────────────────────────────────────

  const crossCheck: ComputedRef<K5WarrantyCrossCheck> = computed(() => {
    const warrantyTotal = subtotals.value.endBalance
    // 从 allResponses 获取K5-1产品质保行审定数
    const adjItem = allResponses.value.get('K5-1-r0-audited') ?? allResponses.value.get('K5-1-warranty-audited')
    const adjVal = Number(adjItem?.remark ?? adjItem?.conclusion ?? 0) || 0
    const diff = warrantyTotal - adjVal
    return {
      warrantyTotal,
      adjudicationWarranty: adjVal,
      diff,
      isMatch: Math.abs(diff) < 0.01,
    }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = warrantyRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add ───────────────────────────────────────────────────────

  async function addRow(productName?: string): Promise<void> {
    let name = productName
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入产品名称',
          '新增产品质量保修行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX型号产品',
            inputValidator: (val) => (!val?.trim() ? '产品名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return
      }
    }
    if (!name) return

    const newRow: K5WarrantyRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: warrantyRows.value.length + 1,
      productName: name,
      revenue: 0,
      warrantyRate: 0,
      estimatedExpense: 0,
      beginBalance: 0,
      periodProvision: 0,
      periodUsed: 0,
      endBalance: 0,
      conclusion: '',
      remark: '',
    }
    warrantyRows.value.push(newRow)
    _persist()
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= warrantyRows.value.length) return
    warrantyRows.value.splice(idx, 1)
    warrantyRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    warrantyRows.value = data.map((raw, i) => _normalizeRow(raw, i))
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    saveResponse('4-rows', { remark: JSON.stringify(warrantyRows.value) })
    saveResponse('4-warranty-total', { remark: String(subtotals.value.endBalance) })
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    warrantyRows,
    subtotals,
    crossCheck,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
  }
}
