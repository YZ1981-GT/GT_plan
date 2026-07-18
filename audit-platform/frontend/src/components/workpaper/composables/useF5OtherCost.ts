/**
 * useF5OtherCost — F5-3 其他业务成本明细表
 *
 * 源表逻辑（A–N）：
 *  项目 × (本期未审/账项/重分类/审定/结构比 + 上期同结构 + 变动额/率 + 备注)
 *  本期审定 = 未审+账项+重分类；结构比 = 审定/合计审定
 *  变动额 = 本期审定−上期审定；变动率按 Excel：上期审定=0 且变动=0→0%；=0且变动>0→100%
 *  预置 7 项固定科目 + 可扩展空白行；合计行纵向 SUM
 */
import { computed, ref, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
} from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5OtherCostOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface OtherCostRow {
  id: string
  item: string
  isFixed: boolean
  currentUnaudited: number
  currentAje: number
  currentRje: number
  currentAudited: number
  currentStructureRatio: number | 'N/A'
  priorUnaudited: number
  priorAje: number
  priorRje: number
  priorAudited: number
  priorStructureRatio: number | 'N/A'
  changeAmount: number
  changeRate: number | 'N/A'
  remark: string
}

interface StoredOtherCostRow {
  id: string
  item: string
  isFixed: boolean
  currentUnaudited: number
  currentAje: number
  currentRje: number
  priorUnaudited: number
  priorAje: number
  priorRje: number
  remark: string
}

export interface OtherCostTotalRow {
  currentUnaudited: number
  currentAje: number
  currentRje: number
  currentAudited: number
  currentStructureRatio: number | 'N/A'
  priorUnaudited: number
  priorAje: number
  priorRje: number
  priorAudited: number
  priorStructureRatio: number | 'N/A'
  changeAmount: number
  changeRate: number | 'N/A'
}

const STORAGE_KEY = 'F5-3-other-cost-rows'
const LEGACY_STORAGE_KEY = 'F5-3-rows'
const NOTE_KEY = 'F5-3-audit-note'
const CONCLUSION_KEY = 'F5-3-audit-conclusion'

/** 变动率绝对值超过此阈值标黄 */
export const F5_OTHER_COST_CHANGE_RATE_THRESHOLD = 30

/** 源表固定项目（R11–R17） */
export const F5_OTHER_COST_FIXED_ITEMS = [
  '出租固定资产',
  '出租无形资产',
  '出租包装物和商品',
  '销售材料',
  '用材料进行非货币性交换',
  '用材料进行债务重组',
  '与投资性房地产相关的支出（成本模式计量的投资性房地产计提的折旧，其他后续支出）',
] as const

/**
 * Excel 变动率：IF(AND(J=0,L=0),0, IF(AND(J=0,L>0),1, L/J))
 * 返回百分比数值（×100），与底稿其他表一致。
 */
export function calcF5OtherCostChangeRate(
  currentAudited: number,
  priorAudited: number,
): number | 'N/A' {
  const changeAmount = currentAudited - priorAudited
  if (priorAudited === 0) {
    if (changeAmount === 0) return 0
    if (changeAmount > 0) return 100
    return -100
  }
  return (changeAmount / priorAudited) * 100
}

export function emptyF5OtherCostRow(item = '', isFixed = false): StoredOtherCostRow {
  return {
    id: `oc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    item,
    isFixed,
    currentUnaudited: 0,
    currentAje: 0,
    currentRje: 0,
    priorUnaudited: 0,
    priorAje: 0,
    priorRje: 0,
    remark: '',
  }
}

export function defaultF5OtherCostRows(): StoredOtherCostRow[] {
  const fixed = F5_OTHER_COST_FIXED_ITEMS.map((item) => emptyF5OtherCostRow(item, true))
  const blanks = [emptyF5OtherCostRow('', false), emptyF5OtherCostRow('', false), emptyF5OtherCostRow('', false)]
  return [...fixed, ...blanks]
}

export function migrateF5OtherCostRows(jsonStr: string | null | undefined): StoredOtherCostRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => {
      const item = String(r?.item ?? r?.costItem ?? r?.label ?? '')
      const isFixed = Boolean(
        r?.isFixed
        ?? F5_OTHER_COST_FIXED_ITEMS.includes(item as (typeof F5_OTHER_COST_FIXED_ITEMS)[number]),
      )
      // 旧模型：currentAmount/priorAmount 无调整链 → 映射为未审数
      const currentUnaudited = parseNum(
        r?.currentUnaudited ?? r?.currentAmount ?? r?.currentAmt ?? r?.currentUnadjusted,
      )
      const priorUnaudited = parseNum(
        r?.priorUnaudited ?? r?.priorAmount ?? r?.priorAmt ?? r?.priorUnadjusted,
      )
      return {
        id: String(r?.id ?? r?.rowId ?? `oc-migrated-${i}`),
        item,
        isFixed,
        currentUnaudited,
        currentAje: parseNum(r?.currentAje),
        currentRje: parseNum(r?.currentRje),
        priorUnaudited,
        priorAje: parseNum(r?.priorAje),
        priorRje: parseNum(r?.priorRje),
        remark: String(r?.remark ?? ''),
      }
    })
  } catch {
    return []
  }
}

export function computeF5OtherCostRow(
  stored: StoredOtherCostRow,
  currentAuditedTotal: number,
  priorAuditedTotal: number,
): OtherCostRow {
  const currentAudited = calcAdjustedAmount(
    stored.currentUnaudited,
    stored.currentAje,
    stored.currentRje,
  )
  const priorAudited = calcAdjustedAmount(
    stored.priorUnaudited,
    stored.priorAje,
    stored.priorRje,
  )
  const changeAmount = calcChangeAmount(currentAudited, priorAudited)
  return {
    id: stored.id,
    item: stored.item,
    isFixed: stored.isFixed,
    currentUnaudited: stored.currentUnaudited,
    currentAje: stored.currentAje,
    currentRje: stored.currentRje,
    currentAudited,
    currentStructureRatio:
      currentAuditedTotal === 0 ? 'N/A' : (currentAudited / currentAuditedTotal) * 100,
    priorUnaudited: stored.priorUnaudited,
    priorAje: stored.priorAje,
    priorRje: stored.priorRje,
    priorAudited,
    priorStructureRatio:
      priorAuditedTotal === 0 ? 'N/A' : (priorAudited / priorAuditedTotal) * 100,
    changeAmount,
    changeRate: calcF5OtherCostChangeRate(currentAudited, priorAudited),
    remark: stored.remark,
  }
}

export function buildF5OtherCostTotal(rows: OtherCostRow[]): OtherCostTotalRow {
  let currentUnaudited = 0
  let currentAje = 0
  let currentRje = 0
  let priorUnaudited = 0
  let priorAje = 0
  let priorRje = 0
  for (const row of rows) {
    currentUnaudited += row.currentUnaudited
    currentAje += row.currentAje
    currentRje += row.currentRje
    priorUnaudited += row.priorUnaudited
    priorAje += row.priorAje
    priorRje += row.priorRje
  }
  const currentAudited = calcAdjustedAmount(currentUnaudited, currentAje, currentRje)
  const priorAudited = calcAdjustedAmount(priorUnaudited, priorAje, priorRje)
  const changeAmount = calcChangeAmount(currentAudited, priorAudited)
  return {
    currentUnaudited,
    currentAje,
    currentRje,
    currentAudited,
    currentStructureRatio: currentAudited === 0 ? 'N/A' : 100,
    priorUnaudited,
    priorAje,
    priorRje,
    priorAudited,
    priorStructureRatio: priorAudited === 0 ? 'N/A' : 100,
    changeAmount,
    changeRate: calcF5OtherCostChangeRate(currentAudited, priorAudited),
  }
}

export function useF5OtherCost(options: UseF5OtherCostOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastPersisted = ''

  const storedRows = ref<StoredOtherCostRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function rawJson(): string | null | undefined {
    return allResponses.value.get(STORAGE_KEY)?.remark
      ?? allResponses.value.get(LEGACY_STORAGE_KEY)?.remark
  }

  function loadRows(): void {
    const migrated = migrateF5OtherCostRows(rawJson())
    storedRows.value = migrated.length ? migrated : defaultF5OtherCostRows()
  }

  watch(() => rawJson(), (raw) => {
    if (raw && (raw === lastPersisted || raw === JSON.stringify(storedRows.value))) return
    loadRows()
  }, { immediate: true })

  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    ([note, conclusion]) => {
      auditNote.value = typeof note === 'string' ? note : ''
      auditConclusion.value = typeof conclusion === 'string' ? conclusion : ''
    },
    { immediate: true },
  )

  const auditedTotals = computed(() => {
    let current = 0
    let prior = 0
    for (const s of storedRows.value) {
      current += calcAdjustedAmount(s.currentUnaudited, s.currentAje, s.currentRje)
      prior += calcAdjustedAmount(s.priorUnaudited, s.priorAje, s.priorRje)
    }
    return { current, prior }
  })

  const rows: ComputedRef<OtherCostRow[]> = computed(() =>
    storedRows.value.map((s) =>
      computeF5OtherCostRow(s, auditedTotals.value.current, auditedTotals.value.prior),
    ),
  )

  const totalRow = computed(() => buildF5OtherCostTotal(rows.value))

  const significantChanges = computed(() =>
    rows.value.filter((row) => {
      if (!row.item.trim() && row.currentAudited === 0 && row.priorAudited === 0) return false
      return typeof row.changeRate === 'number'
        && Math.abs(row.changeRate) >= F5_OTHER_COST_CHANGE_RATE_THRESHOLD
    }),
  )

  function persist(): void {
    const json = JSON.stringify(storedRows.value)
    lastPersisted = json
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: json })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get(NOTE_KEY),
      allResponses.value.get(CONCLUSION_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items } }))
    }
  }

  function updateCell(id: string, key: string, value: number | string): void {
    if (readonly.value) return
    const row = storedRows.value.find((r) => r.id === id)
    if (!row) return
    if (key === 'item' || key === 'remark') {
      if (key === 'item' && row.isFixed) return
      ;(row as any)[key] = String(value ?? '')
    } else if ([
      'currentUnaudited', 'currentAje', 'currentRje',
      'priorUnaudited', 'priorAje', 'priorRje',
      // 旧字段别名
      'currentAmount', 'priorAmount',
    ].includes(key)) {
      const mapped =
        key === 'currentAmount' ? 'currentUnaudited'
          : key === 'priorAmount' ? 'priorUnaudited'
            : key
      ;(row as any)[mapped] = parseNum(value)
    }
    persist()
  }

  function addRow(item = ''): void {
    if (readonly.value) return
    storedRows.value.push(emptyF5OtherCostRow(item, false))
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const target = storedRows.value.find((r) => r.id === id)
    if (!target) return
    if (target.isFixed) {
      // 固定行清空金额，不删标签
      target.currentUnaudited = 0
      target.currentAje = 0
      target.currentRje = 0
      target.priorUnaudited = 0
      target.priorAje = 0
      target.priorRje = 0
      target.remark = ''
      persist()
      return
    }
    const next = storedRows.value.filter((r) => r.id !== id)
    storedRows.value = next.length ? next : defaultF5OtherCostRows()
    persist()
  }

  function isRowHighlighted(row: OtherCostRow): boolean {
    return typeof row.changeRate === 'number'
      && Math.abs(row.changeRate) >= F5_OTHER_COST_CHANGE_RATE_THRESHOLD
  }

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    rows,
    totalRow,
    significantChanges,
    auditNote,
    auditConclusion,
    updateCell,
    addRow,
    removeRow,
    isRowHighlighted,
    saveAuditNote,
    saveAuditConclusion,
    loadRows,
  }
}

export default useF5OtherCost
