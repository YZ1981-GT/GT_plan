/**
 * useE1Analysis — E1-14 货币资金分析程序 composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 11.1
 *
 * 职责：
 * - 固定分析行（三年对比）：itemName, endingAmount(期末从E1-1跨sheet), openingAmount(期初),
 *   priorAmount(上年), changeAmount(ending-opening), changeRate(calcChangeRate),
 *   priorChangeAmount, priorChangeRate, varianceNote(textarea+AI)
 * - Cross-sheet: 从 allResponses 读取 'E1-adj-total-1001/1002/1012'（E1-1三科目期末审定数）
 * - >30% 红色高亮 (exceedsThreshold)
 * - 序列化/反序列化 → checklist_responses (item_id: 'E1-analysis-rows')
 * - Debounce 2s 自动保存
 *
 * Requirements: 9.1-9.3
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum, calcChange, calcChangeRate, exceedsThreshold } from './useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AnalysisRow {
  itemKey: string
  itemName: string
  endingAmount: number         // 期末金额 (from E1-1 cross-sheet)
  openingAmount: number        // 期初金额
  priorAmount: number          // 上年金额
  changeAmount: number         // 变动额 (readonly: ending - opening)
  changeRate: number | ''      // 变动率 (readonly: calcChangeRate)
  priorChangeAmount: number    // 上年变动额
  priorChangeRate: number | '' // 上年变动率
  varianceNote: string         // 变动原因分析 (textarea + AI)
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'E1-analysis-rows'

/** 固定分析项目行配置 */
const ANALYSIS_ITEMS = [
  { itemKey: 'cash', itemName: '库存现金', crossKey: 'E1-adj-total-1001' },
  { itemKey: 'bank', itemName: '银行存款', crossKey: 'E1-adj-total-1002' },
  { itemKey: 'other', itemName: '其他货币资金', crossKey: 'E1-adj-total-1012' },
] as const

/** 变动率高亮阈值 */
const CHANGE_RATE_THRESHOLD = 0.3

/** 用户输入字段 */
const USER_FIELDS = ['itemKey', 'openingAmount', 'priorAmount', 'priorChangeAmount', 'priorChangeRate', 'varianceNote']

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1Analysis(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  const isLoading = ref(false)

  // ─── Stored user-editable data ─────────────────────────────────────────

  interface StoredData {
    openingAmount: number
    priorAmount: number
    priorChangeAmount: number
    priorChangeRate: number | ''
    varianceNote: string
  }

  const storedMap = ref<Record<string, StoredData>>({})

  function loadFromResponses(): void {
    const response = allResponses.value.get(STORAGE_KEY)
    const raw = response?.remark
    if (!raw) {
      storedMap.value = {}
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) {
        storedMap.value = {}
        return
      }
      const map: Record<string, StoredData> = {}
      for (const r of parsed) {
        if (r.itemKey) {
          map[r.itemKey] = {
            openingAmount: parseNum(r.openingAmount),
            priorAmount: parseNum(r.priorAmount),
            priorChangeAmount: parseNum(r.priorChangeAmount),
            priorChangeRate: r.priorChangeRate === '' ? '' : parseNum(r.priorChangeRate),
            varianceNote: String(r.varianceNote || ''),
          }
        }
      }
      storedMap.value = map
    } catch {
      console.warn('[useE1Analysis] JSON parse failed, fallback to empty')
      storedMap.value = {}
    }
  }

  loadFromResponses()

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    (newRemark, oldRemark) => {
      if (newRemark !== oldRemark && newRemark !== serializeRows()) {
        loadFromResponses()
      }
    },
  )

  // ─── Cross-Sheet Data (期末从E1-1审定表) ────────────────────────────────

  function getEndingFromCrossSheet(crossKey: string): number {
    const resp = allResponses.value.get(crossKey)
    return parseNum(resp?.remark)
  }

  // ─── Rows Computed ─────────────────────────────────────────────────────

  const rows: ComputedRef<AnalysisRow[]> = computed(() => {
    return ANALYSIS_ITEMS.map(item => {
      const stored = storedMap.value[item.itemKey] || {
        openingAmount: 0,
        priorAmount: 0,
        priorChangeAmount: 0,
        priorChangeRate: '' as number | '',
        varianceNote: '',
      }

      const endingAmount = getEndingFromCrossSheet(item.crossKey)
      const changeAmount = calcChange(endingAmount, stored.openingAmount)
      const changeRate = calcChangeRate(changeAmount, stored.openingAmount)

      return {
        itemKey: item.itemKey,
        itemName: item.itemName,
        endingAmount,
        openingAmount: stored.openingAmount,
        priorAmount: stored.priorAmount,
        changeAmount,
        changeRate,
        priorChangeAmount: stored.priorChangeAmount,
        priorChangeRate: stored.priorChangeRate,
        varianceNote: stored.varianceNote,
      }
    })
  })

  // ─── Highlight Helpers ─────────────────────────────────────────────────

  function isRateExceeding(row: AnalysisRow): boolean {
    return exceedsThreshold(row.changeRate, CHANGE_RATE_THRESHOLD)
  }

  // ─── Serialization ─────────────────────────────────────────────────────

  function serializeRows(): string {
    const data = ANALYSIS_ITEMS.map(item => {
      const stored = storedMap.value[item.itemKey] || {}
      return { itemKey: item.itemKey, ...stored }
    })
    return JSON.stringify(data)
  }

  // ─── Debounce Save ─────────────────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistToResponses()
    }, 2000)
  }

  function persistToResponses(): void {
    const serialized = serializeRows()
    const items: ChecklistItem[] = [
      { item_id: STORAGE_KEY, conclusion: null, remark: serialized },
    ]
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: serialized })
    saveImmediate(items).catch(() => { /* silent */ })
  }

  // ─── Cell Update ───────────────────────────────────────────────────────

  function updateCell(itemKey: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const stored = storedMap.value[itemKey] || {
      openingAmount: 0, priorAmount: 0, priorChangeAmount: 0, priorChangeRate: '' as number | '', varianceNote: '',
    }
    const updated = { ...stored }
    if (field === 'varianceNote') {
      updated.varianceNote = String(value)
    } else if (field === 'openingAmount' || field === 'priorAmount' || field === 'priorChangeAmount') {
      ;(updated as any)[field] = parseNum(value)
    } else if (field === 'priorChangeRate') {
      updated.priorChangeRate = value === '' ? '' : parseNum(value)
    }
    storedMap.value = { ...storedMap.value, [itemKey]: updated }
    scheduleSave()
  }

  // ─── Hydration ─────────────────────────────────────────────────────────

  function hydrate(): void {
    isLoading.value = true
    try {
      loadFromResponses()
    } finally {
      isLoading.value = false
    }
  }

  // ─── Cleanup ───────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persistToResponses()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    rows,
    isLoading,
    isRateExceeding,
    updateCell,
    hydrate,
  }
}
