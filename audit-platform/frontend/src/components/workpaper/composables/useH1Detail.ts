/**
 * useH1Detail — H1-2 明细表 composable
 *
 * DetailRow 54列完整定义 + 4区段分组配置
 * 行内公式（原值期末/折旧期末/减值期末/净值）
 * subtotalRow + crossValidation（vs H1-1）
 * addRow(弹窗命名)/removeRow/updateCell
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.4
 * Requirements: 3.1-3.12
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import {
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcSubtotal,
} from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表行（54列精简为核心字段，4区段拆分） */
export interface DetailRow {
  rowId: string
  // ── 区段1: 基础信息 ──
  category: string              // 资产分类
  name: string                  // 资产名称
  assetNo: string               // 资产编号
  acquisitionDate: string       // 入账日期
  usefulLife: number            // 使用年限(年)
  salvageRate: number           // 残值率
  depMethod: string             // 折旧方法
  location: string              // 存放地点
  department: string            // 使用部门
  quantity: number              // 数量
  unit: string                  // 单位
  spec: string                  // 规格型号
  supplier: string              // 供应商
  // ── 区段2: 原值变动 ──
  originalCostBegin: number     // 原值期初
  originalCostIncrease: number  // 本期增加
  originalCostDecrease: number  // 本期减少
  originalCostEnd: number       // 原值期末（公式）
  increaseReason: string        // 增加原因
  decreaseReason: string        // 减少原因
  // ── 区段3: 折旧 ──
  accDepBegin: number           // 累计折旧期初
  accDepProvision: number       // 本期计提
  accDepReversal: number        // 本期转回(处置冲减)
  accDepEnd: number             // 累计折旧期末（公式）
  annualDep: number             // 年折旧额
  monthlyDep: number            // 月折旧额
  netValue: number              // 净值（公式）
  // ── 区段4: 减值 ──
  impairmentBegin: number       // 减值准备期初
  impairmentProvision: number   // 本期计提减值
  impairmentReversal: number    // 本期转回减值
  impairmentEnd: number         // 减值准备期末（公式）
  impairmentReason: string      // 减值原因
  recoverableAmount: number     // 可收回金额
  // ── 其他 ──
  remark: string
}

/** 4区段配置 */
export interface SegmentConfig {
  key: string
  label: string
  fields: (keyof DetailRow)[]
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-2'

/** 4区段分组定义 */
export const SEGMENT_CONFIGS: SegmentConfig[] = [
  {
    key: 'basic',
    label: '基础信息',
    fields: ['category', 'name', 'assetNo', 'acquisitionDate', 'usefulLife', 'salvageRate', 'depMethod', 'location', 'department', 'quantity', 'unit', 'spec', 'supplier'],
  },
  {
    key: 'cost',
    label: '原值变动',
    fields: ['originalCostBegin', 'originalCostIncrease', 'originalCostDecrease', 'originalCostEnd', 'increaseReason', 'decreaseReason'],
  },
  {
    key: 'depreciation',
    label: '折旧',
    fields: ['accDepBegin', 'accDepProvision', 'accDepReversal', 'accDepEnd', 'annualDep', 'monthlyDep', 'netValue'],
  },
  {
    key: 'impairment',
    label: '减值',
    fields: ['impairmentBegin', 'impairmentProvision', 'impairmentReversal', 'impairmentEnd', 'impairmentReason', 'recoverableAmount'],
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Detail(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    crossSheetCostAudited?: Ref<number>
    crossSheetDepAudited?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<DetailRow[]>([])
  const activeSegment = ref<string>('basic')
  const selectedRowId = ref<string | null>(null)
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    const raw = item?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow) : []
    } catch { rows.value = [] }

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): DetailRow {
    const r: DetailRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      category: raw.category ?? '',
      name: raw.name ?? '',
      assetNo: raw.assetNo ?? '',
      acquisitionDate: raw.acquisitionDate ?? '',
      usefulLife: Number(raw.usefulLife) || 0,
      salvageRate: Number(raw.salvageRate) || 0,
      depMethod: raw.depMethod ?? '直线法',
      location: raw.location ?? '',
      department: raw.department ?? '',
      quantity: Number(raw.quantity) || 1,
      unit: raw.unit ?? '台',
      spec: raw.spec ?? '',
      supplier: raw.supplier ?? '',
      originalCostBegin: Number(raw.originalCostBegin) || 0,
      originalCostIncrease: Number(raw.originalCostIncrease) || 0,
      originalCostDecrease: Number(raw.originalCostDecrease) || 0,
      originalCostEnd: 0,
      increaseReason: raw.increaseReason ?? '',
      decreaseReason: raw.decreaseReason ?? '',
      accDepBegin: Number(raw.accDepBegin) || 0,
      accDepProvision: Number(raw.accDepProvision) || 0,
      accDepReversal: Number(raw.accDepReversal) || 0,
      accDepEnd: 0,
      annualDep: Number(raw.annualDep) || 0,
      monthlyDep: Number(raw.monthlyDep) || 0,
      netValue: 0,
      impairmentBegin: Number(raw.impairmentBegin) || 0,
      impairmentProvision: Number(raw.impairmentProvision) || 0,
      impairmentReversal: Number(raw.impairmentReversal) || 0,
      impairmentEnd: 0,
      impairmentReason: raw.impairmentReason ?? '',
      recoverableAmount: Number(raw.recoverableAmount) || 0,
      remark: raw.remark ?? '',
    }
    // 计算公式列
    _recalcRow(r)
    return r
  }

  /** 重算行内公式列 */
  function _recalcRow(row: DetailRow): void {
    row.originalCostEnd = calcAssetEndBalance(row.originalCostBegin, row.originalCostIncrease, row.originalCostDecrease)
    row.accDepEnd = calcContraEndBalance(row.accDepBegin, row.accDepReversal, row.accDepProvision)
    row.impairmentEnd = calcContraEndBalance(row.impairmentBegin, row.impairmentReversal, row.impairmentProvision)
    row.netValue = calcNetValue(row.originalCostEnd, row.accDepEnd, row.impairmentEnd)
  }

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotalRow = computed<Partial<DetailRow>>(() => ({
    rowId: 'subtotal',
    category: '合计',
    name: '',
    originalCostBegin: calcSubtotal(rows.value.map((r) => r.originalCostBegin)),
    originalCostIncrease: calcSubtotal(rows.value.map((r) => r.originalCostIncrease)),
    originalCostDecrease: calcSubtotal(rows.value.map((r) => r.originalCostDecrease)),
    originalCostEnd: calcSubtotal(rows.value.map((r) => r.originalCostEnd)),
    accDepBegin: calcSubtotal(rows.value.map((r) => r.accDepBegin)),
    accDepProvision: calcSubtotal(rows.value.map((r) => r.accDepProvision)),
    accDepReversal: calcSubtotal(rows.value.map((r) => r.accDepReversal)),
    accDepEnd: calcSubtotal(rows.value.map((r) => r.accDepEnd)),
    impairmentBegin: calcSubtotal(rows.value.map((r) => r.impairmentBegin)),
    impairmentProvision: calcSubtotal(rows.value.map((r) => r.impairmentProvision)),
    impairmentReversal: calcSubtotal(rows.value.map((r) => r.impairmentReversal)),
    impairmentEnd: calcSubtotal(rows.value.map((r) => r.impairmentEnd)),
    netValue: calcSubtotal(rows.value.map((r) => r.netValue)),
  }))

  // ─── Computed: 交叉验证H1-1 ───────────────────────────────────────────────

  const crossValidation = computed(() => {
    const costFromAdj = options?.crossSheetCostAudited?.value ?? 0
    const depFromAdj = options?.crossSheetDepAudited?.value ?? 0
    const costTotal = subtotalRow.value.originalCostEnd ?? 0
    const depTotal = subtotalRow.value.accDepEnd ?? 0
    return {
      costDiff: costTotal - costFromAdj,
      depDiff: depTotal - depFromAdj,
      hasCostWarning: Math.abs(costTotal - costFromAdj) > 0.01,
      hasDepWarning: Math.abs(depTotal - depFromAdj) > 0.01,
    }
  })

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  /** 添加行（需先弹窗输入名称） */
  function addRow(name: string, category?: string): void {
    const newRow: DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      category: category ?? '',
      name,
      assetNo: '',
      acquisitionDate: '',
      usefulLife: 0,
      salvageRate: 0,
      depMethod: '直线法',
      location: '',
      department: '',
      quantity: 1,
      unit: '台',
      spec: '',
      supplier: '',
      originalCostBegin: 0,
      originalCostIncrease: 0,
      originalCostDecrease: 0,
      originalCostEnd: 0,
      increaseReason: '',
      decreaseReason: '',
      accDepBegin: 0,
      accDepProvision: 0,
      accDepReversal: 0,
      accDepEnd: 0,
      annualDep: 0,
      monthlyDep: 0,
      netValue: 0,
      impairmentBegin: 0,
      impairmentProvision: 0,
      impairmentReversal: 0,
      impairmentEnd: 0,
      impairmentReason: '',
      recoverableAmount: 0,
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

  function updateCell(rowId: string, field: keyof DetailRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
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

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    activeSegment,
    selectedRowId,
    auditNote,
    auditConclusion,
    // Computed
    subtotalRow,
    crossValidation,
    // CRUD
    addRow,
    removeRow,
    updateCell,
    // Save
    saveNote,
    saveConclusion,
    // Config
    SEGMENT_CONFIGS,
  }
}

export default useH1Detail
