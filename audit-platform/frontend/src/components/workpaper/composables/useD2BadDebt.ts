/**
 * useD2BadDebt — 坏账准备明细表D2-3核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 5.1
 *
 * 职责：
 * - BadDebtRow 类型定义（category/14列数值字段）
 * - individualRows/agingRows/customerTypeRows reactive（三分类，从 D2-bd-*-rows JSON remark加载）
 * - totalRow computed（SUM全部行各金额列）
 * - 期末未审数自动计算（= 期初审定 + 计提 + 转入 - 收回 - 转回 - 核销）
 * - eclDifference computed（= 坏账合计 - ECL测试总额）
 * - eclWarning computed（差异≠0 → 黄色警告字符串）
 * - addSubRow(category) / removeSubRow(rowId) 动态行管理
 * - updateCell + debounce 2s 保存
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 18.5
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  getAuditedAmount,
} from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface BadDebtRow {
  rowId: string
  category: 'individual' | 'aging' | 'customer-type'  // 存储分类（三类）
  label: string               // 债务人/组合名称
  isSubRow: boolean           // 子行(可展开)
  isFixed: boolean            // 分类汇总行不可删
  // 期初(4列)
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number        // = 未审+AJE+RJE
  // 本期增加(2列)
  currentProvision: number    // 计提
  currentOtherIncrease: number // 其他增加（源模板G列）
  // 本期减少(3列)
  currentReversal: number     // 转回
  currentWriteOff: number     // 核销
  currentOtherDecrease: number // 其他减少（源模板J列）
  // 期末(4列)
  currentUnadjusted: number   // = 期初审定+计提+其他增加-转回-核销-其他减少
  currentAje: number
  currentRje: number
  currentAudited: number      // = 期末未审+AJE+RJE
}

/** 需要SUM求和的金额字段列表 */
const NUMERIC_FIELDS: (keyof BadDebtRow)[] = [
  'priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited',
  'currentProvision', 'currentOtherIncrease',
  'currentReversal', 'currentWriteOff', 'currentOtherDecrease',
  'currentUnadjusted', 'currentAje', 'currentRje', 'currentAudited',
]

/** 两大分区对应的 allResponses key */
const CATEGORY_KEYS: Record<string, string> = {
  'individual': 'D2-bd-individual-rows',
  'aging': 'D2-bd-aging-rows',
  'customer-type': 'D2-bd-customer-rows',
}

/** 分类默认固定行标签 */
const CATEGORY_LABELS: Record<string, string> = {
  'individual': '按单项计提小计',
  'aging': '账龄组合小计',
  'customer-type': '客户类型组合小计',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成简易唯一ID */
function generateRowId(): string {
  return `bd-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

/** 创建空子行 */
function createEmptySubRow(category: BadDebtRow['category']): BadDebtRow {
  return {
    rowId: generateRowId(),
    category,
    label: '',
    isSubRow: true,
    isFixed: false,
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    currentProvision: 0,
    currentOtherIncrease: 0,
    currentReversal: 0,
    currentWriteOff: 0,
    currentOtherDecrease: 0,
    currentUnadjusted: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
  }
}

/**
 * 创建分类固定汇总行（不可删除）
 */
function createFixedRow(category: BadDebtRow['category']): BadDebtRow {
  return {
    rowId: `fixed-${category}`,
    category,
    label: CATEGORY_LABELS[category] || '小计',
    isSubRow: false,
    isFixed: true,
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    currentProvision: 0,
    currentOtherIncrease: 0,
    currentReversal: 0,
    currentWriteOff: 0,
    currentOtherDecrease: 0,
    currentUnadjusted: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
  }
}

/**
 * 行公式自动计算：
 * - priorAudited = priorUnadjusted + priorAje + priorRje
 * - currentUnadjusted = priorAudited + currentProvision + currentOtherIncrease
 *                       - currentReversal - currentWriteOff - currentOtherDecrease
 * - currentAudited = currentUnadjusted + currentAje + currentRje
 */
function recalcRow(row: BadDebtRow): BadDebtRow {
  row.priorAudited = getAuditedAmount(
    parseNum(row.priorUnadjusted),
    parseNum(row.priorAje),
    parseNum(row.priorRje)
  )
  row.currentUnadjusted =
    row.priorAudited
    + parseNum(row.currentProvision)
    + parseNum(row.currentOtherIncrease)
    - parseNum(row.currentReversal)
    - parseNum(row.currentWriteOff)
    - parseNum(row.currentOtherDecrease)
  row.currentAudited = getAuditedAmount(
    row.currentUnadjusted,
    parseNum(row.currentAje),
    parseNum(row.currentRje)
  )
  return row
}

/**
 * 解析JSON remark为行数组，确保每行含固定行+子行
 */
function parseRows(jsonStr: string | null | undefined, category: BadDebtRow['category']): BadDebtRow[] {
  if (!jsonStr) {
    return [createFixedRow(category)]
  }
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return [createFixedRow(category)]
    }
    const rows: BadDebtRow[] = parsed.map((raw: any) => {
      const row: BadDebtRow = {
        rowId: raw.rowId || generateRowId(),
        category,
        label: raw.label || '',
        isSubRow: raw.isSubRow === true,
        isFixed: raw.isFixed === true,
        priorUnadjusted: parseNum(raw.priorUnadjusted),
        priorAje: parseNum(raw.priorAje),
        priorRje: parseNum(raw.priorRje),
        priorAudited: parseNum(raw.priorAudited),
        currentProvision: parseNum(raw.currentProvision),
        currentOtherIncrease: parseNum(raw.currentOtherIncrease ?? raw.currentTransferIn),
        currentReversal: parseNum(raw.currentReversal),
        currentWriteOff: parseNum(raw.currentWriteOff),
        currentOtherDecrease: parseNum(raw.currentOtherDecrease),
        currentUnadjusted: parseNum(raw.currentUnadjusted),
        currentAje: parseNum(raw.currentAje),
        currentRje: parseNum(raw.currentRje),
        currentAudited: parseNum(raw.currentAudited),
      }
      return recalcRow(row)
    })
    // Ensure at least one fixed row exists
    const hasFixed = rows.some(r => r.isFixed)
    if (!hasFixed) {
      rows.push(createFixedRow(category))
    }
    return rows
  } catch {
    return [createFixedRow(category)]
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2BadDebt(options: UseD2BaseOptions & { eclTestTotal: Ref<number> }) {
  const { allResponses, isReadonly, eclTestTotal } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const individualRows = ref<BadDebtRow[]>([createFixedRow('individual')])
  const agingRows = ref<BadDebtRow[]>([createFixedRow('aging')])
  const customerTypeRows = ref<BadDebtRow[]>([createFixedRow('customer-type')])
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadRows(): void {
    const indResp = allResponses.value.get(CATEGORY_KEYS['individual'])
    individualRows.value = parseRows(indResp?.remark, 'individual')

    const agingResp = allResponses.value.get(CATEGORY_KEYS['aging'])
    agingRows.value = parseRows(agingResp?.remark, 'aging')

    const custResp = allResponses.value.get(CATEGORY_KEYS['customer-type'])
    customerTypeRows.value = parseRows(custResp?.remark, 'customer-type')
  }

  // Watch allResponses for initial load
  watch(
    () => [
      allResponses.value.get(CATEGORY_KEYS['individual'])?.remark,
      allResponses.value.get(CATEGORY_KEYS['aging'])?.remark,
      allResponses.value.get(CATEGORY_KEYS['customer-type'])?.remark,
    ],
    () => {
      // Only reload if all arrays have just the default fixed row (initial load)
      const isInitial =
        individualRows.value.length <= 1 && !individualRows.value.some(r => r.isSubRow)
        && agingRows.value.length <= 1 && !agingRows.value.some(r => r.isSubRow)
        && customerTypeRows.value.length <= 1 && !customerTypeRows.value.some(r => r.isSubRow)
      if (isInitial) {
        loadRows()
      }
    },
    { immediate: true }
  )

  // ─── All Rows (flat) ───────────────────────────────────────────────────

  /** 全部行（三分类合并），用于计算合计 */
  const allRows = computed<BadDebtRow[]>(() => {
    return [...individualRows.value, ...agingRows.value, ...customerTypeRows.value]
  })

  // ─── Total Row ─────────────────────────────────────────────────────────

  /**
   * 合计行：SUM全部行各金额列（不可编辑）
   * 注：只对子行和固定行求和（固定行=分类小计，但原始数据中固定行金额应由其子行SUM得到。
   * 此处合计行取全部行SUM，即各分类的固定小计行之和 或 全部子行之和。
   * 为避免重复计算，仅对子行求和；如果无子行则取固定行。）
   *
   * 设计简化：合计行 = 三个分类固定行的 SUM（固定行自身由子行决定）
   */
  const totalRow: ComputedRef<BadDebtRow> = computed(() => {
    // 取三个固定行（分类小计行）
    const fixedInd = individualRows.value.find(r => r.isFixed)
    const fixedAging = agingRows.value.find(r => r.isFixed)
    const fixedCust = customerTypeRows.value.find(r => r.isFixed)
    const fixedRows = [fixedInd, fixedAging, fixedCust].filter(Boolean) as BadDebtRow[]

    const result: BadDebtRow = {
      rowId: '__total__',
      category: 'individual', // arbitrary for total row
      label: '合计',
      isSubRow: false,
      isFixed: true,
      priorUnadjusted: 0,
      priorAje: 0,
      priorRje: 0,
      priorAudited: 0,
      currentProvision: 0,
      currentOtherIncrease: 0,
      currentReversal: 0,
      currentWriteOff: 0,
      currentOtherDecrease: 0,
      currentUnadjusted: 0,
      currentAje: 0,
      currentRje: 0,
      currentAudited: 0,
    }

    for (const field of NUMERIC_FIELDS) {
      (result as any)[field] = fixedRows.reduce(
        (sum, row) => sum + parseNum((row as any)[field]),
        0
      )
    }
    return result
  })

  // ─── Recalc Fixed Rows (category subtotals) ────────────────────────────

  /**
   * 重新计算分类固定行 = SUM该分类所有子行
   */
  function recalcFixedRow(rows: BadDebtRow[]): void {
    const fixedRow = rows.find(r => r.isFixed)
    if (!fixedRow) return
    const subRows = rows.filter(r => r.isSubRow)
    if (subRows.length === 0) {
      // 无子行时固定行保持自身值（允许直接编辑）
      return
    }
    for (const field of NUMERIC_FIELDS) {
      (fixedRow as any)[field] = subRows.reduce(
        (sum, row) => sum + parseNum((row as any)[field]),
        0
      )
    }
    // Recalc formula fields for fixed row
    recalcRow(fixedRow)
  }

  // ─── ECL Difference & Warning ──────────────────────────────────────────

  /**
   * ECL差异 = 坏账准备合计审定数 - ECL测试总额（D2-9）
   */
  const eclDifference: ComputedRef<number> = computed(() => {
    return totalRow.value.currentAudited - eclTestTotal.value
  })

  /**
   * ECL差异警告：差异≠0 → 黄色警告字符串；差异=0 → null
   */
  const eclWarning: ComputedRef<string | null> = computed(() => {
    const diff = eclDifference.value
    if (diff === 0) return null
    const sign = diff > 0 ? '+' : ''
    return `与D2-9 ECL测算差异: ${sign}${diff.toFixed(2)}元`
  })

  // ─── Row Management ────────────────────────────────────────────────────

  /**
   * 添加子行到指定分类（在固定行前插入）
   */
  function addSubRow(category: BadDebtRow['category']): void {
    if (isReadonly.value) return
    const newRow = createEmptySubRow(category)
    const targetRows = getRowsRef(category)
    // Insert before the fixed row
    const fixedIdx = targetRows.value.findIndex(r => r.isFixed)
    if (fixedIdx >= 0) {
      targetRows.value.splice(fixedIdx, 0, newRow)
    } else {
      targetRows.value.push(newRow)
    }
    recalcFixedRow(targetRows.value)
    debounceSave()
  }

  /**
   * 删除指定子行（不允许删除固定行）
   */
  function removeSubRow(rowId: string): void {
    if (isReadonly.value) return

    for (const category of ['individual', 'aging', 'customer-type'] as const) {
      const targetRows = getRowsRef(category)
      const idx = targetRows.value.findIndex(r => r.rowId === rowId)
      if (idx === -1) continue
      const row = targetRows.value[idx]
      if (row.isFixed) return  // Cannot delete fixed rows
      targetRows.value.splice(idx, 1)
      recalcFixedRow(targetRows.value)
      debounceSave()
      return
    }
  }

  // ─── Update Cell ───────────────────────────────────────────────────────

  /**
   * 编辑单元格 → 公式重算 → 更新分类小计 → debounce保存
   */
  function updateCell(rowId: string, field: string, value: number): void {
    if (isReadonly.value) return

    // Find row across all categories
    let foundRow: BadDebtRow | undefined
    let foundCategory: BadDebtRow['category'] | undefined

    for (const category of ['individual', 'aging', 'customer-type'] as const) {
      const targetRows = getRowsRef(category)
      const row = targetRows.value.find(r => r.rowId === rowId)
      if (row) {
        foundRow = row
        foundCategory = category
        break
      }
    }

    if (!foundRow || !foundCategory) return

    // Update the field value
    const key = field as keyof BadDebtRow
    if (key === 'label') {
      foundRow.label = String(value)
    } else if (NUMERIC_FIELDS.includes(key)) {
      ;(foundRow as any)[key] = parseNum(value)
    }

    // Recalc formula chain for this row
    recalcRow(foundRow)

    // Recalc fixed row subtotal if editing a sub-row
    if (foundRow.isSubRow) {
      recalcFixedRow(getRowsRef(foundCategory).value)
    }

    debounceSave()
  }

  // ─── Helpers ───────────────────────────────────────────────────────────

  function getRowsRef(category: BadDebtRow['category']): Ref<BadDebtRow[]> {
    switch (category) {
      case 'individual': return individualRows
      case 'aging': return agingRows
      case 'customer-type': return customerTypeRows
    }
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function serializeCategory(rows: BadDebtRow[]): string {
    return JSON.stringify(rows)
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    // Update allResponses Map for each category
    for (const category of ['individual', 'aging', 'customer-type'] as const) {
      const key = CATEGORY_KEYS[category]
      const json = serializeCategory(getRowsRef(category).value)
      allResponses.value.set(key, {
        item_id: key,
        conclusion: null,
        remark: json,
      })
    }
    // Dispatch save event
    dispatchSaveEvent()
  }

  /**
   * 触发保存事件（CustomEvent 'd2:save-items'，由 useD2FormData 监听处理）
   */
  function dispatchSaveEvent(): void {
    try {
      const items = (['individual', 'aging', 'customer-type'] as const).map(category => ({
        item_id: CATEGORY_KEYS[category],
        conclusion: null,
        remark: serializeCategory(getRowsRef(category).value),
      }))
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 三分类行数据
    individualRows,
    agingRows,
    customerTypeRows,

    // 合计行
    totalRow,

    // ECL差异检查
    eclDifference,
    eclWarning,

    // 行操作
    addSubRow,
    removeSubRow,
    updateCell,

    // 工具方法（供外部/测试使用）
    loadRows,
    serializeCategory,
  }
}

export default useD2BadDebt
