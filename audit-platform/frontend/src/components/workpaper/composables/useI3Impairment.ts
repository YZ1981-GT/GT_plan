/**
 * useI3Impairment — I3-6 商誉减值测试（CGU分摊 + 先冲商誉逻辑）
 *
 * 核心功能：
 * 1. CGU行管理（动态添加/删除资产组）
 * 2. 每个CGU：goodwill + otherAssets → cguBookValue(含商誉)
 * 3. recoverableAmount 来自 I3-7 DCF（通过 useI3CrossSheet 或手工输入）
 * 4. 减值 = MAX(cguBookValue - recoverableAmount, 0)
 * 5. 分摊规则（CAS8两步法）：
 *    Step 1: 先冲商誉 → goodwillImpairment = MIN(impairment, goodwillAmount)
 *    Step 2: 剩余 → 按其他资产账面比例分摊
 * 6. 约束：商誉减值不可转回（impairment ≥ 0）；goodwillImpairment ≤ goodwillAmount
 * 7. 总减值 computed → 供 I3-1 审定表"本期减少(减值)"列
 *
 * 持久化：
 * - CGU行: "I3-6-rows"（JSON数组存入 allResponses）
 *
 * 联动：
 * - I3-7 → recoverableAmount（由 useI3CrossSheet.recoverableByCgu 提供）
 * - I3-6 总减值 → I3-1 审定表 → TB 回写 1711
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 3.5
 * Requirements: 5.1-5.5
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem } from './useI3FormData'
import { calcImpairmentAllocation, calcSubtotal } from './useI3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** CGU内其他资产 */
export interface OtherAsset {
  name: string
  bookValue: number
}

/** 其他资产分摊明细 */
export interface OtherAllocation {
  name: string
  amount: number
}

/** I3-6 CGU行（减值测试）(Req 5.1) */
export interface CguRow {
  rowId: string
  /** 资产组(CGU)名称 */
  cguName: string
  /** 该CGU包含的商誉金额 */
  goodwillAmount: number
  /** 其他资产列表(name + bookValue) */
  otherAssets: OtherAsset[]
  /** computed: 资产组账面(含商誉) = goodwill + Σ(otherAssets.bookValue) */
  cguBookValue: number
  /** 可收回金额 (from I3-7 DCF 或手工输入) */
  recoverableAmount: number
  /** computed: 减值金额 = MAX(cguBookValue - recoverableAmount, 0) (Req 5.2) */
  impairmentAmount: number
  /** computed: 商誉分摊减值 = MIN(impairmentAmount, goodwillAmount) (Req 5.3) */
  goodwillImpairment: number
  /** computed: 其他资产分摊明细(按比例) (Req 5.3) */
  otherAllocations: OtherAllocation[]
}

/** CGU合计行 */
export interface CguSummary {
  totalGoodwill: number
  totalOtherAssets: number
  totalCguBookValue: number
  totalRecoverable: number
  totalImpairment: number
  totalGoodwillImpairment: number
  totalOtherImpairment: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_CGU_ROWS = 'I3-6-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _genRowId(): string {
  return `cgu-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _safeParseRows<T>(raw: string | null | undefined): T[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ─── Core Calculation ────────────────────────────────────────────────────────

/**
 * 重算单行 CGU 的减值分摊（CAS8两步法）：
 * 1. cguBookValue = goodwillAmount + Σ(otherAssets.bookValue)
 * 2. impairmentAmount = MAX(cguBookValue - recoverableAmount, 0)
 * 3. 调用 calcImpairmentAllocation 执行先冲商誉再分摊
 *
 * 约束：impairment ≥ 0（商誉减值不可转回 Req 5.4）
 */
function _recalcCguRow(row: CguRow): void {
  // Step 0: 资产组账面(含商誉) = 商誉 + 其他资产合计
  const otherTotal = calcSubtotal(row.otherAssets.map(a => a.bookValue))
  row.cguBookValue = row.goodwillAmount + otherTotal

  // Step 1: 减值金额 = MAX(账面 - 可收回, 0) (Req 5.2)
  // 商誉减值不可转回：不允许负数减值 (Req 5.4)
  row.impairmentAmount = Math.max(row.cguBookValue - row.recoverableAmount, 0)

  // Step 2: 分摊规则 — 先冲商誉再按比例分摊至其他资产 (Req 5.3)
  const allocation = calcImpairmentAllocation(
    row.impairmentAmount,
    row.goodwillAmount,
    row.otherAssets,
  )

  row.goodwillImpairment = allocation.goodwillImpairment
  row.otherAllocations = allocation.otherAllocations
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3Impairment(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    /** 保存回调（委托 useI3FormData.saveImmediate 或 setValue） */
    onSave?: (itemId: string, value: any) => void
    /** I3-7 可收回金额映射（按CGU名称），来自 useI3CrossSheet */
    recoverableByCgu?: ComputedRef<Record<string, number>>
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const cguRows = ref<CguRow[]>([])

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadCguRows(): void {
    const resp = allResponses.value.get(ITEM_ID_CGU_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    cguRows.value = _safeParseRows<any>(raw).map(_normalizeCguRow)
  }

  function _normalizeCguRow(raw: any): CguRow {
    const goodwillAmount = _getNum(raw.goodwillAmount)
    const otherAssets: OtherAsset[] = Array.isArray(raw.otherAssets)
      ? raw.otherAssets.map((a: any) => ({
          name: String(a.name ?? ''),
          bookValue: _getNum(a.bookValue),
        }))
      : []
    const recoverableAmount = _getNum(raw.recoverableAmount)

    const row: CguRow = {
      rowId: raw.rowId ?? _genRowId(),
      cguName: raw.cguName ?? '',
      goodwillAmount,
      otherAssets,
      cguBookValue: 0,
      recoverableAmount,
      impairmentAmount: 0,
      goodwillImpairment: 0,
      otherAllocations: [],
    }
    // 重算公式列
    _recalcCguRow(row)
    return row
  }

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  /** CGU合计行（所有CGU的汇总） */
  const cguSummary: ComputedRef<CguSummary> = computed(() => {
    let totalGoodwill = 0
    let totalOtherAssets = 0
    let totalCguBookValue = 0
    let totalRecoverable = 0
    let totalImpairment = 0
    let totalGoodwillImpairment = 0
    let totalOtherImpairment = 0

    for (const row of cguRows.value) {
      totalGoodwill += row.goodwillAmount
      totalOtherAssets += calcSubtotal(row.otherAssets.map(a => a.bookValue))
      totalCguBookValue += row.cguBookValue
      totalRecoverable += row.recoverableAmount
      totalImpairment += row.impairmentAmount
      totalGoodwillImpairment += row.goodwillImpairment
      totalOtherImpairment += calcSubtotal(row.otherAllocations.map(a => a.amount))
    }

    return {
      totalGoodwill,
      totalOtherAssets,
      totalCguBookValue,
      totalRecoverable,
      totalImpairment,
      totalGoodwillImpairment,
      totalOtherImpairment,
    }
  })

  /**
   * 总商誉减值金额（所有CGU的goodwillImpairment之和）。
   * 供 I3-1 审定表"本期减少(减值)"列引用。
   */
  const totalGoodwillImpairment: ComputedRef<number> = computed(() => {
    return cguSummary.value.totalGoodwillImpairment
  })

  /** 需警示的CGU行（减值金额>0的rowId集合，供红色高亮） */
  const impairedRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of cguRows.value) {
      if (row.impairmentAmount > 0) {
        ids.add(row.rowId)
      }
    }
    return ids
  })

  // ─── Actions: 行管理 ───────────────────────────────────────────────────────

  /**
   * 添加CGU行（动态新增资产组）。
   * 必须提供 cguName（弹 ElMessageBox.prompt 输入后再调用）。
   */
  function addCguRow(params: {
    cguName: string
    goodwillAmount?: number
    otherAssets?: OtherAsset[]
    recoverableAmount?: number
  }): CguRow {
    const row: CguRow = {
      rowId: _genRowId(),
      cguName: params.cguName,
      goodwillAmount: params.goodwillAmount ?? 0,
      otherAssets: params.otherAssets ?? [],
      cguBookValue: 0,
      recoverableAmount: params.recoverableAmount ?? 0,
      impairmentAmount: 0,
      goodwillImpairment: 0,
      otherAllocations: [],
    }
    _recalcCguRow(row)
    cguRows.value.push(row)
    _persist()
    return row
  }

  /**
   * 删除CGU行。
   */
  function removeCguRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= cguRows.value.length) return
    cguRows.value.splice(rowIndex, 1)
    _persist()
  }

  // ─── Actions: 字段更新 ─────────────────────────────────────────────────────

  /**
   * 更新CGU行的商誉金额并重算。
   */
  function updateGoodwillAmount(rowIndex: number, value: number): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.goodwillAmount = Math.max(value, 0) // 商誉≥0
    _recalcCguRow(row)
    _persist()
  }

  /**
   * 更新CGU行的可收回金额（手工输入覆盖I3-7联动）并重算。
   */
  function updateRecoverableAmount(rowIndex: number, value: number): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.recoverableAmount = Math.max(value, 0) // 可收回金额≥0
    _recalcCguRow(row)
    _persist()
  }

  /**
   * 更新CGU行的CGU名称。
   */
  function updateCguName(rowIndex: number, name: string): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.cguName = name
    _persist()
  }

  // ─── Actions: 其他资产管理 ─────────────────────────────────────────────────

  /**
   * 添加一个其他资产到指定CGU行。
   */
  function addOtherAsset(rowIndex: number, asset: OtherAsset): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.otherAssets.push({ name: asset.name, bookValue: Math.max(asset.bookValue, 0) })
    _recalcCguRow(row)
    _persist()
  }

  /**
   * 删除指定CGU行的某个其他资产。
   */
  function removeOtherAsset(rowIndex: number, assetIndex: number): void {
    const row = cguRows.value[rowIndex]
    if (!row || assetIndex < 0 || assetIndex >= row.otherAssets.length) return
    row.otherAssets.splice(assetIndex, 1)
    _recalcCguRow(row)
    _persist()
  }

  /**
   * 更新指定CGU行的某个其他资产字段。
   */
  function updateOtherAsset(
    rowIndex: number,
    assetIndex: number,
    field: keyof OtherAsset,
    value: string | number,
  ): void {
    const row = cguRows.value[rowIndex]
    if (!row || assetIndex < 0 || assetIndex >= row.otherAssets.length) return
    const asset = row.otherAssets[assetIndex]
    if (field === 'name') {
      asset.name = String(value)
    } else if (field === 'bookValue') {
      asset.bookValue = Math.max(_getNum(value), 0)
    }
    _recalcCguRow(row)
    _persist()
  }

  // ─── Actions: 全量重算 ─────────────────────────────────────────────────────

  /**
   * 重算所有CGU行（外部触发，如I3-7数据变化时）。
   */
  function recalcAll(): void {
    for (const row of cguRows.value) {
      _recalcCguRow(row)
    }
    _persist()
  }

  // ─── I3-7 → I3-6 联动：recoverableAmount 自动填入 ─────────────────────────

  /**
   * 从 I3-7 可收回金额结果（按CGU名称匹配）同步到 I3-6 各行的 recoverableAmount。
   * 匹配方式：cguName 完全相等。
   * 仅覆盖已有CGU行，不自动创建新行。
   */
  function syncRecoverableFromI3_7(): void {
    const rcMap = options?.recoverableByCgu?.value
    if (!rcMap || Object.keys(rcMap).length === 0) return

    let changed = false
    for (const row of cguRows.value) {
      if (row.cguName && rcMap[row.cguName] != null) {
        const newVal = Math.max(rcMap[row.cguName], 0)
        if (row.recoverableAmount !== newVal) {
          row.recoverableAmount = newVal
          _recalcCguRow(row)
          changed = true
        }
      }
    }

    if (changed) {
      _persist()
    }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(ITEM_ID_CGU_ROWS, cguRows.value)
  }

  // ─── Import / Export ───────────────────────────────────────────────────────

  /** 导入CGU行（覆盖） */
  function importCguRows(rows: Partial<CguRow>[]): void {
    cguRows.value = rows.map(_normalizeCguRow)
    _persist()
  }

  /** 导出CGU行 */
  function exportCguRows(): CguRow[] {
    return [...cguRows.value]
  }

  // ─── Watch: allResponses 变化时加载数据 ────────────────────────────────────

  watch(allResponses, () => {
    _loadCguRows()
  }, { immediate: true })

  // ─── Watch: I3-7 可收回金额变化时自动联动 ─────────────────────────────────

  if (options?.recoverableByCgu) {
    watch(options.recoverableByCgu, () => {
      syncRecoverableFromI3_7()
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // ── State ──
    cguRows,

    // ── Computed ──
    cguSummary,
    totalGoodwillImpairment,
    impairedRowIds,

    // ── Actions: 行管理 ──
    addCguRow,
    removeCguRow,

    // ── Actions: 字段更新 ──
    updateGoodwillAmount,
    updateRecoverableAmount,
    updateCguName,

    // ── Actions: 其他资产管理 ──
    addOtherAsset,
    removeOtherAsset,
    updateOtherAsset,

    // ── Actions: 全量重算 ──
    recalcAll,

    // ── Actions: I3-7联动 ──
    syncRecoverableFromI3_7,

    // ── Import/Export ──
    importCguRows,
    exportCguRows,
  }
}

export default useI3Impairment
