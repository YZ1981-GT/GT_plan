/**
 * useH1DepreciationAlloc — H1-13 折旧分配 composable
 *
 * AllocRow 11列 + 分配比例计算 + 核对行
 * 从H1-12取数 + D5/K8/K9 GtIndexChip跳转
 * EventBus发布'h1:depreciation-allocated'
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.13
 * Requirements: 12.1-12.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal, calcProportion } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AllocRow {
  rowId: string
  category: string             // 资产分类
  department: string           // 使用部门
  expenseAccount: string       // 对应费用科目(制造费用/管理费用/销售费用)
  depAmount: number            // 折旧金额
  allocRate: number            // 分配比例(%)
  allocToManufacture: number   // 分配至制造费用
  allocToAdmin: number         // 分配至管理费用
  allocToSales: number         // 分配至销售费用
  bookAmount: number           // 账面金额
  difference: number           // 差异
  remark: string
}

/** 核对行结构 */
export interface ReconciliationRow {
  label: string
  calculated: number
  book: number
  difference: number
  targetWpCode: string          // 跳转目标底稿编码
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-13'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1DepreciationAlloc(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    crossSheetDepTotal?: Ref<number>
    crossSheetByCategory?: Ref<Record<string, number>>
    onSave?: (itemId: string, value: any) => void
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<AllocRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    if (item?.remark) {
      try {
        const parsed = JSON.parse(item.remark)
        rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow) : []
      } catch { rows.value = [] }
    } else { rows.value = [] }

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const i = allResponses.value.get(itemId)
    return (i?.remark ?? i?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): AllocRow {
    return {
      rowId: raw.rowId ?? `alloc-${Math.random().toString(36).slice(2, 10)}`,
      category: raw.category ?? '',
      department: raw.department ?? '',
      expenseAccount: raw.expenseAccount ?? '',
      depAmount: Number(raw.depAmount) || 0,
      allocRate: Number(raw.allocRate) || 0,
      allocToManufacture: Number(raw.allocToManufacture) || 0,
      allocToAdmin: Number(raw.allocToAdmin) || 0,
      allocToSales: Number(raw.allocToSales) || 0,
      bookAmount: Number(raw.bookAmount) || 0,
      difference: Number(raw.difference) || 0,
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 合计 + 分配比例重算 ────────────────────────────────────────

  const totalDepAmount = computed(() => calcSubtotal(rows.value.map((r) => r.depAmount)))
  const totalManufacture = computed(() => calcSubtotal(rows.value.map((r) => r.allocToManufacture)))
  const totalAdmin = computed(() => calcSubtotal(rows.value.map((r) => r.allocToAdmin)))
  const totalSales = computed(() => calcSubtotal(rows.value.map((r) => r.allocToSales)))
  const totalBook = computed(() => calcSubtotal(rows.value.map((r) => r.bookAmount)))
  const totalDifference = computed(() => calcSubtotal(rows.value.map((r) => r.difference)))

  // ─── Computed: 核对行 ──────────────────────────────────────────────────────

  const reconciliationRows = computed<ReconciliationRow[]>(() => {
    const depFromH12 = options?.crossSheetDepTotal?.value ?? 0
    return [
      {
        label: '折旧合计 vs H1-12',
        calculated: totalDepAmount.value,
        book: depFromH12,
        difference: totalDepAmount.value - depFromH12,
        targetWpCode: 'H1-12',
      },
      {
        label: '制造费用 vs D5',
        calculated: totalManufacture.value,
        book: 0,  // 从D5取数（外部传入）
        difference: totalManufacture.value,
        targetWpCode: 'D5',
      },
      {
        label: '管理费用 vs K8',
        calculated: totalAdmin.value,
        book: 0,
        difference: totalAdmin.value,
        targetWpCode: 'K8',
      },
      {
        label: '销售费用 vs K9',
        calculated: totalSales.value,
        book: 0,
        difference: totalSales.value,
        targetWpCode: 'K9',
      },
    ]
  })

  // ─── updateCell + 自动重算 ─────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof AllocRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value

    // 重算分配比例
    const total = totalDepAmount.value || 1
    row.allocRate = calcProportion(row.depAmount, total) ?? 0

    // 重算差异
    const allocTotal = row.allocToManufacture + row.allocToAdmin + row.allocToSales
    row.difference = allocTotal - row.bookAmount

    _persist()
  }

  function addRow(category?: string): void {
    const newRow: AllocRow = {
      rowId: `alloc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      category: category ?? '',
      department: '',
      expenseAccount: '',
      depAmount: 0,
      allocRate: 0,
      allocToManufacture: 0,
      allocToAdmin: 0,
      allocToSales: 0,
      bookAmount: 0,
      difference: 0,
      remark: '',
    }
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      _persist()
    }
  }

  // ─── EventBus: 发布折旧分配结果 ───────────────────────────────────────────

  function publishAllocated(): void {
    options?.onPublishEvent?.('h1:depreciation-allocated', {
      wp_code: 'H1',
      totalManufacture: totalManufacture.value,
      totalAdmin: totalAdmin.value,
      totalSales: totalSales.value,
      byCategory: rows.value.reduce((acc, r) => {
        acc[r.category] = { manufacture: r.allocToManufacture, admin: r.allocToAdmin, sales: r.allocToSales }
        return acc
      }, {} as Record<string, any>),
    })
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
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

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    auditNote,
    auditConclusion,
    totalDepAmount,
    totalManufacture,
    totalAdmin,
    totalSales,
    totalBook,
    totalDifference,
    reconciliationRows,
    updateCell,
    addRow,
    removeRow,
    publishAllocated,
    saveNote,
    saveConclusion,
  }
}

export default useH1DepreciationAlloc
