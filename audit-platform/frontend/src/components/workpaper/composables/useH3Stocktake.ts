/**
 * useH3Stocktake — H3-9 盘点检查 composable
 *
 * StocktakeRow 13列 + 空置高亮 + 汇总统计(出租/空置/空置率)
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.14
 * Requirements: 10.1-10.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface StocktakeRow {
  rowId: string
  seq: number
  assetName: string
  location: string
  titleCertNo: string
  area: number                // 面积(㎡)
  purpose: string             // 用途(出租/增值)
  tenant: string              // 租户
  leaseStatus: string         // 租赁状态(已出租/空置/到期)
  physicalStatus: string      // 实物状态
  maintenance: string         // 维护情况
  bookValue: number           // 账面值
  conclusion: string          // 盘点结论
  remark: string
}

const ITEM_ID = 'H3-9-stocktake-rows'

export function useH3Stocktake(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params
  const rows = ref<StocktakeRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any, idx?: number): StocktakeRow {
    return {
      rowId: raw.rowId ?? `st-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      assetName: raw.assetName ?? '',
      location: raw.location ?? '',
      titleCertNo: raw.titleCertNo ?? '',
      area: Number(raw.area) || 0,
      purpose: raw.purpose ?? '',
      tenant: raw.tenant ?? '',
      leaseStatus: raw.leaseStatus ?? '',
      physicalStatus: raw.physicalStatus ?? '',
      maintenance: raw.maintenance ?? '',
      bookValue: Number(raw.bookValue) || 0,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  const summary = computed(() => {
    const total = rows.value.length
    const rented = rows.value.filter((r) => r.leaseStatus === '已出租').length
    const vacant = rows.value.filter((r) => r.leaseStatus === '空置').length
    const vacancyRate = total > 0 ? vacant / total : 0
    return { total, rented, vacant, vacancyRate }
  })

  /** 空置行索引（用于黄色高亮） */
  const vacantIndices = computed(() =>
    rows.value.reduce<number[]>((acc, r, i) => { if (r.leaseStatus === '空置') acc.push(i); return acc }, []),
  )

  function addRow(assetName: string): void {
    rows.value.push(_normalize({ assetName, seq: rows.value.length + 1 }))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(index: number, field: keyof StocktakeRow, value: any): void {
    const row = rows.value[index]
    if (row) { (row as any)[field] = value; _persist() }
  }

  /** 行变更：组件已 v-model 就地修改，持久化（组件调用 updateRow(index, row)） */
  function updateRow(index: number, _row?: any): void {
    if (!rows.value[index]) return
    _persist()
  }

  // ─── 汇总（组件 H3TabStocktakeCheck 使用） ────────────────────────────────────
  const rentedCount = computed(() => rows.value.filter((r) => r.leaseStatus === '已出租').length)
  const vacantCount = computed(() => rows.value.filter((r) => r.leaseStatus === '空置').length)
  /** 空置率（百分比，0-100） */
  const vacantRate = computed(() => {
    const total = rows.value.length
    return total > 0 ? (vacantCount.value / total) * 100 : 0
  })

  function _persist(): void { setValue(ITEM_ID, rows.value) }
  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    rows, summary, vacantIndices, addRow, removeRow, updateCell, updateRow, loadRows,
    rentedCount, vacantCount, vacantRate,
  }
}

export default useH3Stocktake
