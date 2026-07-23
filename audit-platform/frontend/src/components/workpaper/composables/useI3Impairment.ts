/**
 * useI3Impairment — I3-6 商誉减值测试（CGU分摊 + 少数股东商誉粗化 + 先冲商誉）
 *
 * 核心逻辑（对齐致同 I3-6 Excel 底稿 / CAS8）：
 * 1. 账面价值粗化：合计(1) = A(资产组账面) + B1(母公司商誉) + B2(未确认少数股东商誉)
 * 2. 可收回金额(2) = MAX(公允价值减处置费用①, 使用价值②)，或手工覆盖
 * 3. 减值准备 = MAX((1)-(2), 0)
 * 4. 分摊两步法：先冲全额商誉(B1+B2)→剩余按其他资产账面比例分摊
 * 5. 合并报表确认商誉减值 = 商誉分摊减值 × B1/(B1+B2)（仅母公司份额）
 * 6. 商誉减值不可转回
 *
 * 兼容：旧字段 goodwillAmount 视为 B1；无 B2 时行为与改造前一致。
 *
 * 持久化：CGU行 "I3-6-rows"；定性/专家/风险等另存独立 key。
 *
 * Spec: .kiro/specs/i3-goodwill/ Task 3.5 / Requirements 5.1-5.5
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem } from './useI3FormData'
import { calcImpairmentAllocation, calcSubtotal } from './useI3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** CGU内其他资产 */
export interface OtherAsset {
  name: string
  bookValue: number
  /** 可选：单项可收回金额，用于第二分摊下限（CAS8 §23） */
  recoverableAmount?: number | null
}

/** 其他资产分摊明细 */
export interface OtherAllocation {
  name: string
  amount: number
}

/**
 * I3-6 CGU行（减值测试）
 * A/B1/B2 对齐 Excel「账面价值(1)」结构
 */
export interface CguRow {
  rowId: string
  /** 资产组(CGU)名称 */
  cguName: string
  /**
   * A：对应资产组账面价值（合并报表层面，不含商誉）
   * 若未单独录入，回退为 Σ(otherAssets.bookValue)
   */
  assetGroupCarrying: number
  /**
   * B1：分摊的商誉账面价值（母公司份额）
   * 兼容旧字段 goodwillAmount
   */
  goodwillB1: number
  /** B2：未确认的少数股东商誉 */
  minorityB2: number
  /**
   * @deprecated 兼容旧 API / 旧持久化：等价于 goodwillB1
   */
  goodwillAmount: number
  /** 其他资产列表（展开明细 & 第二分摊基数） */
  otherAssets: OtherAsset[]
  /** ① 公允价值减处置费用后的净额（可选） */
  fairValueLessCost: number | null
  /** ② 预计未来现金流量现值 / 使用价值（可选） */
  valueInUse: number | null
  /**
   * 可收回金额(2)：优先 = MAX(①,②)；若均未填则用手工值
   * 兼容旧数据直接存此字段
   */
  recoverableAmount: number
  /** 减值原因及说明 */
  impairmentReason: string
  /** computed: 合计(1)=A+B1+B2 */
  cguBookValue: number
  /** computed: 减值金额 = MAX(cguBookValue - recoverableAmount, 0) */
  impairmentAmount: number
  /**
   * computed: 第一分摊—冲减全额商誉(B1+B2)
   * = MIN(impairmentAmount, B1+B2)
   */
  goodwillImpairment: number
  /**
   * computed: 合并报表确认的商誉减值（仅母公司份额）
   * = goodwillImpairment × B1/(B1+B2)；B2=0 时等于 goodwillImpairment
   */
  consolidatedGwImpairment: number
  /** computed: 第二分摊—其他资产按比例 */
  otherAllocations: OtherAllocation[]
}

/** CGU合计行 */
export interface CguSummary {
  totalAssetGroupCarrying: number
  totalGoodwillB1: number
  totalMinorityB2: number
  totalGoodwill: number
  totalOtherAssets: number
  totalCguBookValue: number
  totalRecoverable: number
  totalImpairment: number
  totalGoodwillImpairment: number
  /** 合并报表应确认商誉减值合计 */
  totalConsolidatedGwImpairment: number
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

function _getNullableNum(val: any): number | null {
  if (val == null || val === '') return null
  const n = Number(val)
  return Number.isFinite(n) ? n : null
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

/**
 * 可收回金额：有①或②时取孰高；否则用手工 recoverableAmount
 */
export function resolveRecoverableAmount(row: {
  fairValueLessCost?: number | null
  valueInUse?: number | null
  recoverableAmount?: number | null
}): number {
  const fv = row.fairValueLessCost
  const viu = row.valueInUse
  const hasFv = fv != null && Number.isFinite(fv)
  const hasViu = viu != null && Number.isFinite(viu)
  if (hasFv || hasViu) {
    return Math.max(hasFv ? Number(fv) : 0, hasViu ? Number(viu) : 0)
  }
  return Math.max(_getNum(row.recoverableAmount), 0)
}

/**
 * 合并报表确认商誉减值 = 全额商誉减值 × B1/(B1+B2)
 */
export function calcConsolidatedGwImpairment(
  goodwillImpairment: number,
  goodwillB1: number,
  minorityB2: number,
): number {
  const totalGw = goodwillB1 + minorityB2
  if (goodwillImpairment <= 0 || totalGw <= 0) return 0
  if (minorityB2 <= 0) return goodwillImpairment
  return (goodwillImpairment * goodwillB1) / totalGw
}

// ─── Core Calculation ────────────────────────────────────────────────────────

/**
 * 重算单行 CGU：
 * 1. A = assetGroupCarrying（若为0且有 otherAssets，回退 Σother）
 * 2. 合计(1) = A + B1 + B2
 * 3. 可收回(2) = resolveRecoverableAmount
 * 4. 减值 = MAX((1)-(2), 0)
 * 5. 先冲全额商誉(B1+B2)，再分摊其他资产
 * 6. 合并确认 = 商誉减值 × B1/(B1+B2)
 */
function _recalcCguRow(row: CguRow): void {
  // 同步兼容字段
  row.goodwillAmount = row.goodwillB1

  const otherTotal = calcSubtotal(row.otherAssets.map(a => a.bookValue))
  // A：优先显式录入；未录且存在其他资产明细时用明细合计
  const A = row.assetGroupCarrying > 0
    ? row.assetGroupCarrying
    : (otherTotal > 0 ? otherTotal : row.assetGroupCarrying)

  // 若显式 A 与明细合计不一致且明细非空，账面仍以显式 A 为准（明细仅作第二分摊基数）
  const effectiveA = A
  row.cguBookValue = effectiveA + row.goodwillB1 + row.minorityB2

  row.recoverableAmount = resolveRecoverableAmount(row)

  row.impairmentAmount = Math.max(row.cguBookValue - row.recoverableAmount, 0)

  // 第一分摊基数 = 全额商誉 B1+B2（粗化后）
  const fullGoodwill = row.goodwillB1 + row.minorityB2
  const allocation = calcImpairmentAllocation(
    row.impairmentAmount,
    fullGoodwill,
    row.otherAssets,
  )

  row.goodwillImpairment = allocation.goodwillImpairment
  row.otherAllocations = allocation.otherAllocations
  row.consolidatedGwImpairment = calcConsolidatedGwImpairment(
    row.goodwillImpairment,
    row.goodwillB1,
    row.minorityB2,
  )
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3Impairment(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
    /** I3-7 → 可收回金额合计（兼容） */
    recoverableByCgu?: ComputedRef<Record<string, number>>
    /** I3-7 → 公允净额 + 使用价值明细 */
    recoverableDetailByCgu?: ComputedRef<Record<string, {
      fairValueLessDisposal?: number
      valueInUse?: number
      recoverableAmount?: number
    }>>
  },
) {
  const cguRows = ref<CguRow[]>([])

  function _loadCguRows(): void {
    const resp = allResponses.value.get(ITEM_ID_CGU_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    cguRows.value = _safeParseRows<any>(raw).map(_normalizeCguRow)
  }

  function _normalizeCguRow(raw: any): CguRow {
    // 兼容：goodwillAmount → B1；assetGroupCarrying 缺省时由 otherAssets 推导
    const goodwillB1 = _getNum(raw.goodwillB1 ?? raw.goodwillAmount)
    const minorityB2 = _getNum(raw.minorityB2)
    const otherAssets: OtherAsset[] = Array.isArray(raw.otherAssets)
      ? raw.otherAssets.map((a: any) => ({
          name: String(a.name ?? ''),
          bookValue: _getNum(a.bookValue),
          recoverableAmount: a.recoverableAmount != null ? _getNum(a.recoverableAmount) : null,
        }))
      : []
    const otherTotal = calcSubtotal(otherAssets.map(a => a.bookValue))
    const assetGroupCarrying = raw.assetGroupCarrying != null
      ? _getNum(raw.assetGroupCarrying)
      : otherTotal

    const fairValueLessCost = _getNullableNum(raw.fairValueLessCost)
    const valueInUse = _getNullableNum(raw.valueInUse)
    const recoverableAmount = _getNum(raw.recoverableAmount)

    const row: CguRow = {
      rowId: raw.rowId ?? _genRowId(),
      cguName: raw.cguName ?? '',
      assetGroupCarrying,
      goodwillB1,
      minorityB2,
      goodwillAmount: goodwillB1,
      otherAssets,
      fairValueLessCost,
      valueInUse,
      recoverableAmount,
      impairmentReason: String(raw.impairmentReason ?? ''),
      cguBookValue: 0,
      impairmentAmount: 0,
      goodwillImpairment: 0,
      consolidatedGwImpairment: 0,
      otherAllocations: [],
    }
    _recalcCguRow(row)
    return row
  }

  const cguSummary: ComputedRef<CguSummary> = computed(() => {
    let totalAssetGroupCarrying = 0
    let totalGoodwillB1 = 0
    let totalMinorityB2 = 0
    let totalOtherAssets = 0
    let totalCguBookValue = 0
    let totalRecoverable = 0
    let totalImpairment = 0
    let totalGoodwillImpairment = 0
    let totalConsolidatedGwImpairment = 0
    let totalOtherImpairment = 0

    for (const row of cguRows.value) {
      const otherTotal = calcSubtotal(row.otherAssets.map(a => a.bookValue))
      const A = row.assetGroupCarrying > 0 ? row.assetGroupCarrying : otherTotal
      totalAssetGroupCarrying += A
      totalGoodwillB1 += row.goodwillB1
      totalMinorityB2 += row.minorityB2
      totalOtherAssets += otherTotal
      totalCguBookValue += row.cguBookValue
      totalRecoverable += row.recoverableAmount
      totalImpairment += row.impairmentAmount
      totalGoodwillImpairment += row.goodwillImpairment
      totalConsolidatedGwImpairment += row.consolidatedGwImpairment
      totalOtherImpairment += calcSubtotal(row.otherAllocations.map(a => a.amount))
    }

    return {
      totalAssetGroupCarrying,
      totalGoodwillB1,
      totalMinorityB2,
      totalGoodwill: totalGoodwillB1,
      totalOtherAssets,
      totalCguBookValue,
      totalRecoverable,
      totalImpairment,
      totalGoodwillImpairment,
      totalConsolidatedGwImpairment,
      totalOtherImpairment,
    }
  })

  /**
   * 供 I3-1 审定表「本期减少(减值)」：合并报表确认的商誉减值（母公司份额）
   */
  const totalGoodwillImpairment: ComputedRef<number> = computed(() => {
    return cguSummary.value.totalConsolidatedGwImpairment
  })

  const impairedRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of cguRows.value) {
      if (row.impairmentAmount > 0) ids.add(row.rowId)
    }
    return ids
  })

  function addCguRow(params: {
    cguName: string
    assetGroupCarrying?: number
    goodwillB1?: number
    goodwillAmount?: number
    minorityB2?: number
    otherAssets?: OtherAsset[]
    fairValueLessCost?: number | null
    valueInUse?: number | null
    recoverableAmount?: number
    impairmentReason?: string
  }): CguRow {
    const goodwillB1 = params.goodwillB1 ?? params.goodwillAmount ?? 0
    const otherAssets = params.otherAssets ?? []
    const otherTotal = calcSubtotal(otherAssets.map(a => a.bookValue))
    const row: CguRow = {
      rowId: _genRowId(),
      cguName: params.cguName,
      assetGroupCarrying: params.assetGroupCarrying ?? otherTotal,
      goodwillB1,
      minorityB2: params.minorityB2 ?? 0,
      goodwillAmount: goodwillB1,
      otherAssets,
      fairValueLessCost: params.fairValueLessCost ?? null,
      valueInUse: params.valueInUse ?? null,
      recoverableAmount: params.recoverableAmount ?? 0,
      impairmentReason: params.impairmentReason ?? '',
      cguBookValue: 0,
      impairmentAmount: 0,
      goodwillImpairment: 0,
      consolidatedGwImpairment: 0,
      otherAllocations: [],
    }
    _recalcCguRow(row)
    cguRows.value.push(row)
    _persist()
    return row
  }

  function removeCguRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= cguRows.value.length) return
    cguRows.value.splice(rowIndex, 1)
    _persist()
  }

  function updateGoodwillAmount(rowIndex: number, value: number): void {
    updateGoodwillB1(rowIndex, value)
  }

  function updateGoodwillB1(rowIndex: number, value: number): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.goodwillB1 = Math.max(value, 0)
    row.goodwillAmount = row.goodwillB1
    _recalcCguRow(row)
    _persist()
  }

  function updateMinorityB2(rowIndex: number, value: number): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.minorityB2 = Math.max(value, 0)
    _recalcCguRow(row)
    _persist()
  }

  function updateAssetGroupCarrying(rowIndex: number, value: number): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.assetGroupCarrying = Math.max(value, 0)
    _recalcCguRow(row)
    _persist()
  }

  function updateRecoverableAmount(rowIndex: number, value: number): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    // 手工覆盖：清空①②，直接写 recoverable
    row.fairValueLessCost = null
    row.valueInUse = null
    row.recoverableAmount = Math.max(value, 0)
    _recalcCguRow(row)
    _persist()
  }

  function updateFairValueLessCost(rowIndex: number, value: number | null): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.fairValueLessCost = value == null ? null : Math.max(value, 0)
    _recalcCguRow(row)
    _persist()
  }

  function updateValueInUse(rowIndex: number, value: number | null): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.valueInUse = value == null ? null : Math.max(value, 0)
    _recalcCguRow(row)
    _persist()
  }

  function updateImpairmentReason(rowIndex: number, reason: string): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.impairmentReason = reason
    _persist()
  }

  function updateCguName(rowIndex: number, name: string): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.cguName = name
    _persist()
  }

  /** 其他资产明细是 A 的构成；维护明细时同步 A，保证粗化账面与分摊基数一致 */
  function _syncAssetGroupFromOtherAssets(row: CguRow): void {
    row.assetGroupCarrying = calcSubtotal(row.otherAssets.map(a => a.bookValue))
  }

  function addOtherAsset(rowIndex: number, asset: OtherAsset): void {
    const row = cguRows.value[rowIndex]
    if (!row) return
    row.otherAssets.push({
      name: asset.name,
      bookValue: Math.max(asset.bookValue, 0),
      recoverableAmount: asset.recoverableAmount ?? null,
    })
    _syncAssetGroupFromOtherAssets(row)
    _recalcCguRow(row)
    _persist()
  }

  function removeOtherAsset(rowIndex: number, assetIndex: number): void {
    const row = cguRows.value[rowIndex]
    if (!row || assetIndex < 0 || assetIndex >= row.otherAssets.length) return
    row.otherAssets.splice(assetIndex, 1)
    _syncAssetGroupFromOtherAssets(row)
    _recalcCguRow(row)
    _persist()
  }

  function updateOtherAsset(
    rowIndex: number,
    assetIndex: number,
    field: keyof OtherAsset,
    value: string | number | null,
  ): void {
    const row = cguRows.value[rowIndex]
    if (!row || assetIndex < 0 || assetIndex >= row.otherAssets.length) return
    const asset = row.otherAssets[assetIndex]
    if (field === 'name') {
      asset.name = String(value ?? '')
    } else if (field === 'bookValue') {
      asset.bookValue = Math.max(_getNum(value), 0)
      _syncAssetGroupFromOtherAssets(row)
    } else if (field === 'recoverableAmount') {
      asset.recoverableAmount = value == null || value === '' ? null : Math.max(_getNum(value), 0)
    }
    _recalcCguRow(row)
    _persist()
  }

  function recalcAll(): void {
    for (const row of cguRows.value) {
      _recalcCguRow(row)
    }
    _persist()
  }

  function syncRecoverableFromI3_7(): { changed: number } {
    const detailMap = options?.recoverableDetailByCgu?.value
    const rcMap = options?.recoverableByCgu?.value
    if (
      (!detailMap || Object.keys(detailMap).length === 0)
      && (!rcMap || Object.keys(rcMap).length === 0)
    ) {
      return { changed: 0 }
    }

    let changed = 0
    for (const row of cguRows.value) {
      if (!row.cguName) continue
      const detail = detailMap?.[row.cguName]
      if (detail) {
        const fv = detail.fairValueLessDisposal != null && Number(detail.fairValueLessDisposal) > 0
          ? Number(detail.fairValueLessDisposal)
          : null
        const viu = detail.valueInUse != null && Number(detail.valueInUse) > 0
          ? Number(detail.valueInUse)
          : (detail.recoverableAmount != null && Number(detail.recoverableAmount) > 0
            ? Number(detail.recoverableAmount)
            : null)
        const fvChanged = row.fairValueLessCost !== fv
        const viuChanged = row.valueInUse !== viu
        if (fvChanged || viuChanged) {
          row.fairValueLessCost = fv
          row.valueInUse = viu
          _recalcCguRow(row)
          changed++
        }
        continue
      }
      if (rcMap && rcMap[row.cguName] != null) {
        const newVal = Math.max(rcMap[row.cguName], 0)
        if (row.valueInUse !== newVal) {
          row.valueInUse = newVal
          _recalcCguRow(row)
          changed++
        }
      }
    }

    if (changed > 0) _persist()
    return { changed }
  }

  function _persist(): void {
    options?.onSave?.(ITEM_ID_CGU_ROWS, cguRows.value)
  }

  function importCguRows(rows: Partial<CguRow>[]): void {
    cguRows.value = rows.map(_normalizeCguRow)
    _persist()
  }

  function exportCguRows(): CguRow[] {
    return [...cguRows.value]
  }

  watch(allResponses, () => {
    _loadCguRows()
  }, { immediate: true })

  if (options?.recoverableByCgu || options?.recoverableDetailByCgu) {
    watch(
      () => [
        options.recoverableDetailByCgu?.value,
        options.recoverableByCgu?.value,
      ],
      () => {
        syncRecoverableFromI3_7()
      },
      { deep: true },
    )
  }

  return {
    cguRows,
    cguSummary,
    totalGoodwillImpairment,
    impairedRowIds,
    addCguRow,
    removeCguRow,
    updateGoodwillAmount,
    updateGoodwillB1,
    updateMinorityB2,
    updateAssetGroupCarrying,
    updateRecoverableAmount,
    updateFairValueLessCost,
    updateValueInUse,
    updateImpairmentReason,
    updateCguName,
    addOtherAsset,
    removeOtherAsset,
    updateOtherAsset,
    recalcAll,
    syncRecoverableFromI3_7,
    importCguRows,
    exportCguRows,
  }
}

export default useI3Impairment
