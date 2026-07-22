/**
 * useD3DetailColumnPrefs — D3-2 预收账款明细表列显示偏好（2-period）
 *
 * 功能：
 * - 用户自定义显示/隐藏列（checkbox 控制）
 * - "隐藏空列"一键功能（扫描当前数据，全行为 0/空的列自动隐藏）
 * - 预设方案快速切换：全部列 / 核心列 / 审定+账龄
 * - 偏好持久化到 checklist_responses（D3-detail-column-prefs，仅前端 UI 控制）
 *
 * 设计原则：
 * - 列定义与 D3TabDetail.vue 的 el-table-column 结构对齐
 * - 不改变底层数据模型，仅控制 UI 渲染层的 v-if
 * - 账龄动态段列跟随 useAgingConfig 的 bands 自动适配（D3 为 2-period：期初账龄 + 期末审定账龄）
 * - customerName（对方单位名称）为行标识锚点，始终显示，不进入 checkbox 控制
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { DetailRow } from './useD3Detail'
import type { AgingBand } from '@/composables/useAgingConfig'

// ─── Types ───────────────────────────────────────────────────────────────────

export type D3ColumnGroup =
  | '基础'
  | '期初'
  | '期初账龄'
  | '本期发生'
  | '期末未审'
  | '期末调整'
  | '期末审定'
  | '期末审定账龄'
  | '其他'

export interface D3ColumnDef {
  key: string
  label: string
  group: D3ColumnGroup
  defaultVisible: boolean
}

export type D3PresetName = 'all' | 'core' | 'audited-aging' | 'custom'

export interface D3ColumnPreset {
  name: D3PresetName
  label: string
  description: string
  visibleKeys: string[] | 'all'
}

// ─── 固定列定义（不含动态账龄段；customerName 为锚点不列入） ──────────────────

const FIXED_COLUMNS: D3ColumnDef[] = [
  { key: 'companyCode', label: '公司代码', group: '基础', defaultVisible: true },
  { key: 'nature', label: '款项性质', group: '基础', defaultVisible: true },
  { key: 'relationType', label: '关联方类型', group: '基础', defaultVisible: true },
  // 期初
  { key: 'priorUnadjusted', label: '期初未审(E)', group: '期初', defaultVisible: true },
  { key: 'priorAdjustment', label: '期初调整(F)', group: '期初', defaultVisible: true },
  { key: 'priorReclass', label: '期初重分(G)', group: '期初', defaultVisible: true },
  { key: 'priorAudited', label: '期初审定(H)', group: '期初', defaultVisible: true },
  // 本期发生
  { key: 'debit', label: '借方(M)', group: '本期发生', defaultVisible: true },
  { key: 'credit', label: '贷方(N)', group: '本期发生', defaultVisible: true },
  { key: 'endBalance', label: '期末余额(O)', group: '本期发生', defaultVisible: true },
  // 期末未审
  { key: 'entityReclass', label: '重分类(P)', group: '期末未审', defaultVisible: true },
  { key: 'endUnadjusted', label: '期末未审(Q)', group: '期末未审', defaultVisible: true },
  // 期末调整
  { key: 'endAje', label: '期末AJE(R)', group: '期末调整', defaultVisible: true },
  { key: 'endRje', label: '期末RJE(S)', group: '期末调整', defaultVisible: true },
  // 期末审定
  { key: 'endAudited', label: '期末审定(T)', group: '期末审定', defaultVisible: true },
  // 其他
  { key: 'isConfirmed', label: '发函(Y)', group: '其他', defaultVisible: true },
  { key: 'postPeriodSettlement', label: '期后结转(Z)', group: '其他', defaultVisible: true },
  { key: 'remark', label: '备注', group: '其他', defaultVisible: true },
]

const PRESETS: D3ColumnPreset[] = [
  {
    name: 'all',
    label: '全部列',
    description: '显示完整底稿结构所有列',
    visibleKeys: 'all',
  },
  {
    name: 'core',
    label: '核心列',
    description: '款项性质+关联方+期初审定+期末未审+期末审定+发函',
    visibleKeys: [
      'nature', 'relationType',
      'priorAudited', 'endUnadjusted', 'endAudited', 'isConfirmed',
    ],
  },
  {
    name: 'audited-aging',
    label: '审定+账龄',
    description: '期初审定+期末审定+全部审定账龄段',
    visibleKeys: [
      'priorAudited', 'endAudited',
      // 审定账龄段动态追加（_AGING_AUDITED_PREFIX 匹配）
    ],
  },
]

const _AGING_PRIOR_PREFIX = 'aging-prior-'
const _AGING_AUDITED_PREFIX = 'aging-audited-'
const ITEM_ID = 'D3-detail-column-prefs'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD3DetailColumnPrefs(options: {
  bands: Ref<AgingBand[]>
  rows: Ref<DetailRow[]>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
}) {
  const { bands, rows, allResponses, isReadonly } = options

  // ─── 完整列定义（固定列 + 动态账龄段，2-period） ─────────────────────────

  const allColumns: ComputedRef<D3ColumnDef[]> = computed(() => {
    const agingPriorCols: D3ColumnDef[] = bands.value.map(b => ({
      key: `${_AGING_PRIOR_PREFIX}${b.key}`,
      label: `${b.label}(期初)`,
      group: '期初账龄' as D3ColumnGroup,
      defaultVisible: true,
    }))
    const agingAuditedCols: D3ColumnDef[] = bands.value.map(b => ({
      key: `${_AGING_AUDITED_PREFIX}${b.key}`,
      label: `${b.label}(期末审定)`,
      group: '期末审定账龄' as D3ColumnGroup,
      defaultVisible: true,
    }))

    const result: D3ColumnDef[] = []
    for (const col of FIXED_COLUMNS) {
      result.push(col)
      if (col.key === 'priorAudited') result.push(...agingPriorCols)
      if (col.key === 'endAudited') result.push(...agingAuditedCols)
    }
    return result
  })

  const visibleKeys = ref<Set<string>>(new Set())
  const activePreset = ref<D3PresetName>('all')

  function loadPrefs(): void {
    const stored = allResponses.value.get(ITEM_ID)?.remark
    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        if (parsed.preset) activePreset.value = parsed.preset
        if (Array.isArray(parsed.visibleKeys)) {
          visibleKeys.value = new Set(parsed.visibleKeys)
          return
        }
      } catch { /* fallback to all */ }
    }
    applyPreset('all')
  }

  function savePrefs(): void {
    if (isReadonly.value) return
    const payload = JSON.stringify({
      preset: activePreset.value,
      visibleKeys: Array.from(visibleKeys.value),
    })
    allResponses.value.set(ITEM_ID, {
      item_id: ITEM_ID,
      conclusion: null,
      remark: payload,
    })
    // 列偏好仅前端 UI 控制，非审计数据，不触发后端保存
  }

  function isColumnVisible(key: string): boolean {
    return visibleKeys.value.has(key)
  }

  function toggleColumn(key: string, visible: boolean): void {
    if (visible) visibleKeys.value.add(key)
    else visibleKeys.value.delete(key)
    activePreset.value = 'custom'
    savePrefs()
  }

  function toggleGroup(group: D3ColumnGroup, visible: boolean): void {
    const groupCols = allColumns.value.filter(c => c.group === group)
    for (const col of groupCols) {
      if (visible) visibleKeys.value.add(col.key)
      else visibleKeys.value.delete(col.key)
    }
    activePreset.value = 'custom'
    savePrefs()
  }

  function isGroupVisible(group: D3ColumnGroup): boolean {
    const groupCols = allColumns.value.filter(c => c.group === group)
    return groupCols.length > 0 && groupCols.every(c => visibleKeys.value.has(c.key))
  }

  function isGroupPartial(group: D3ColumnGroup): boolean {
    const groupCols = allColumns.value.filter(c => c.group === group)
    const visCount = groupCols.filter(c => visibleKeys.value.has(c.key)).length
    return visCount > 0 && visCount < groupCols.length
  }

  function applyPreset(name: D3PresetName): void {
    activePreset.value = name
    const preset = PRESETS.find(p => p.name === name)
    if (!preset) return

    if (preset.visibleKeys === 'all') {
      visibleKeys.value = new Set(allColumns.value.map(c => c.key))
    } else {
      const keys = new Set(preset.visibleKeys)
      if (name === 'audited-aging') {
        for (const col of allColumns.value) {
          if (col.key.startsWith(_AGING_AUDITED_PREFIX)) keys.add(col.key)
        }
      }
      visibleKeys.value = keys
    }
    savePrefs()
  }

  /**
   * 扫描当前数据行，将所有行该列值均为 0/空的列自动隐藏。
   * 锚点列（companyCode/nature/relationType）保留。
   */
  function hideEmptyColumns(): void {
    const alwaysKeep = new Set(['companyCode', 'nature', 'relationType'])
    const currentRows = rows.value
    if (currentRows.length === 0) return

    for (const col of allColumns.value) {
      if (alwaysKeep.has(col.key)) continue
      const isEmpty = currentRows.every(row => {
        const val = getColumnValue(row, col.key)
        return val === 0 || val === '' || val === null || val === undefined || val === '-' || val === false
      })
      if (isEmpty) visibleKeys.value.delete(col.key)
    }
    activePreset.value = 'custom'
    savePrefs()
  }

  function getColumnValue(row: DetailRow, key: string): unknown {
    if (key.startsWith(_AGING_PRIOR_PREFIX)) {
      return row.agingPrior?.[key.slice(_AGING_PRIOR_PREFIX.length)] ?? 0
    }
    if (key.startsWith(_AGING_AUDITED_PREFIX)) {
      return row.agingAudited?.[key.slice(_AGING_AUDITED_PREFIX.length)] ?? 0
    }
    return (row as any)[key]
  }

  const visibleCount = computed(() => visibleKeys.value.size)
  const totalCount = computed(() => allColumns.value.length)

  const groups: ComputedRef<D3ColumnGroup[]> = computed(() => {
    const seen = new Set<D3ColumnGroup>()
    for (const col of allColumns.value) seen.add(col.group)
    return Array.from(seen)
  })

  function getGroupColumns(group: D3ColumnGroup): D3ColumnDef[] {
    return allColumns.value.filter(c => c.group === group)
  }

  // 账龄段变化时，新增段在"全部"预设下自动可见
  watch(bands, () => {
    if (activePreset.value !== 'all') return
    for (const col of allColumns.value) {
      if (!visibleKeys.value.has(col.key) && col.defaultVisible) {
        visibleKeys.value.add(col.key)
      }
    }
  })

  watch(
    () => allResponses.value.size,
    () => { if (visibleKeys.value.size === 0) loadPrefs() },
    { immediate: true },
  )

  return {
    allColumns,
    groups,
    getGroupColumns,
    isColumnVisible,
    toggleColumn,
    toggleGroup,
    isGroupVisible,
    isGroupPartial,
    visibleKeys,
    visibleCount,
    totalCount,
    activePreset,
    applyPreset,
    presets: PRESETS,
    hideEmptyColumns,
  }
}

export default useD3DetailColumnPrefs
