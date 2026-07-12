/**
 * useD2DetailColumnPrefs — D2-2 明细表列显示偏好
 *
 * 功能：
 * - 用户自定义显示/隐藏列（checkbox 控制）
 * - "隐藏空列"一键功能（扫描当前数据，全行为 0/空的列自动隐藏）
 * - 预设方案快速切换：全部列 / 核心列 / 仅审定+账龄
 * - 偏好持久化到 checklist_responses（D2-detail-column-prefs）
 *
 * 设计原则：
 * - 列定义与 D2TabDetail.vue 的 el-table-column 结构对齐
 * - 不改变底层数据模型，仅控制 UI 渲染层的 v-if
 * - 账龄动态段列跟随 useAgingConfig 的 bands 自动适配
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { DetailRow } from './useD2Detail'
import type { AgingBand } from '@/composables/useAgingConfig'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ColumnDef {
  key: string          // 唯一标识（对应 DetailRow 字段名或 'aging-prior-{key}' 等）
  label: string        // 显示名称
  group: ColumnGroup   // 分组
  defaultVisible: boolean  // 默认是否显示
}

export type ColumnGroup =
  | '基础'
  | '期初'
  | '期初账龄'
  | '本期发生'
  | '期末未审'
  | '期末未审账龄'
  | '期末调整'
  | '期末审定'
  | '期末审定账龄'
  | '分类标记'
  | '其他'

export type PresetName = 'all' | 'core' | 'audited-aging' | 'custom'

export interface ColumnPreset {
  name: PresetName
  label: string
  description: string
  visibleKeys: string[] | 'all'
}

// ─── 固定列定义（不含动态账龄段） ────────────────────────────────────────────

const FIXED_COLUMNS: ColumnDef[] = [
  // 基础
  { key: 'seq', label: '序号', group: '基础', defaultVisible: true },
  { key: 'customerName', label: '客户名称', group: '基础', defaultVisible: true },
  { key: 'companyCode', label: '公司代码', group: '基础', defaultVisible: true },
  { key: 'relationType', label: '关联方类型', group: '基础', defaultVisible: true },
  // 期初
  { key: 'priorUnadjusted', label: '期初未审', group: '期初', defaultVisible: true },
  { key: 'priorAje', label: '期初AJE', group: '期初', defaultVisible: true },
  { key: 'priorRje', label: '期初RJE', group: '期初', defaultVisible: true },
  { key: 'priorAudited', label: '期初审定', group: '期初', defaultVisible: true },
  // 本期发生
  { key: 'debitOccurrence', label: '借方发生', group: '本期发生', defaultVisible: true },
  { key: 'creditOccurrence', label: '贷方发生', group: '本期发生', defaultVisible: true },
  { key: 'endBalance', label: '期末余额', group: '本期发生', defaultVisible: true },
  { key: 'reclassification', label: '重分类', group: '本期发生', defaultVisible: true },
  // 期末未审
  { key: 'currentUnadjusted', label: '期末未审', group: '期末未审', defaultVisible: true },
  // 期末调整
  { key: 'currentAje', label: '期末AJE', group: '期末调整', defaultVisible: true },
  { key: 'currentRje', label: '期末RJE', group: '期末调整', defaultVisible: true },
  // 期末审定
  { key: 'currentAudited', label: '期末审定', group: '期末审定', defaultVisible: true },
  // 分类标记
  { key: 'creditRiskClassification', label: '信用风险组合', group: '分类标记', defaultVisible: true },
  { key: 'groupName', label: '组合名称', group: '分类标记', defaultVisible: true },
  { key: 'isConfirmation', label: '函证', group: '分类标记', defaultVisible: true },
  // 其他
  { key: 'postPayment', label: '期后回款', group: '其他', defaultVisible: true },
  { key: 'remark', label: '备注', group: '其他', defaultVisible: true },
]

// ─── 预设方案 ────────────────────────────────────────────────────────────────

const PRESETS: ColumnPreset[] = [
  {
    name: 'all',
    label: '全部列',
    description: '显示完整底稿结构所有列',
    visibleKeys: 'all',
  },
  {
    name: 'core',
    label: '核心列',
    description: '序号+客户+关联方+期初审定+期末未审+期末审定+信用风险组合+函证',
    visibleKeys: [
      'seq', 'customerName', 'relationType',
      'priorAudited', 'currentUnadjusted', 'currentAudited',
      'creditRiskClassification', 'isConfirmation',
    ],
  },
  {
    name: 'audited-aging',
    label: '审定+账龄',
    description: '客户+期初审定+期末审定+全部审定账龄段',
    visibleKeys: [
      'seq', 'customerName',
      'priorAudited', 'currentAudited',
      // 审定账龄段动态追加（通过 _AGING_AUDITED_PREFIX 匹配）
    ],
  },
]

const _AGING_PRIOR_PREFIX = 'aging-prior-'
const _AGING_CURRENT_PREFIX = 'aging-current-'
const _AGING_AUDITED_PREFIX = 'aging-audited-'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2DetailColumnPrefs(options: {
  bands: Ref<AgingBand[]>
  rows: Ref<DetailRow[]>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
}) {
  const { bands, rows, allResponses, isReadonly } = options

  // ─── 完整列定义（固定列 + 动态账龄段） ──────────────────────────────────

  const allColumns: ComputedRef<ColumnDef[]> = computed(() => {
    const agingPriorCols: ColumnDef[] = bands.value.map(b => ({
      key: `${_AGING_PRIOR_PREFIX}${b.key}`,
      label: b.label,
      group: '期初账龄' as ColumnGroup,
      defaultVisible: true,
    }))
    const agingCurrentCols: ColumnDef[] = bands.value.map(b => ({
      key: `${_AGING_CURRENT_PREFIX}${b.key}`,
      label: b.label,
      group: '期末未审账龄' as ColumnGroup,
      defaultVisible: true,
    }))
    const agingAuditedCols: ColumnDef[] = bands.value.map(b => ({
      key: `${_AGING_AUDITED_PREFIX}${b.key}`,
      label: b.label,
      group: '期末审定账龄' as ColumnGroup,
      defaultVisible: true,
    }))

    // 插入到正确位置
    const result: ColumnDef[] = []
    for (const col of FIXED_COLUMNS) {
      result.push(col)
      // 期初审定后面插入期初账龄段
      if (col.key === 'priorAudited') result.push(...agingPriorCols)
      // 期末未审后面插入期末未审账龄段
      if (col.key === 'currentUnadjusted') result.push(...agingCurrentCols)
      // 期末审定后面插入期末审定账龄段
      if (col.key === 'currentAudited') result.push(...agingAuditedCols)
    }
    return result
  })

  // ─── 可见性状态 ────────────────────────────────────────────────────────

  const visibleKeys = ref<Set<string>>(new Set())
  const activePreset = ref<PresetName>('all')

  // ─── 初始化：从 allResponses 加载偏好 ──────────────────────────────────

  function loadPrefs(): void {
    const stored = allResponses.value.get('D2-detail-column-prefs')?.remark
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
    // 默认全部显示
    applyPreset('all')
  }

  // ─── 保存偏好 ──────────────────────────────────────────────────────────

  function savePrefs(): void {
    if (isReadonly.value) return
    const payload = JSON.stringify({
      preset: activePreset.value,
      visibleKeys: Array.from(visibleKeys.value),
    })
    allResponses.value.set('D2-detail-column-prefs', {
      item_id: 'D2-detail-column-prefs',
      conclusion: null,
      remark: payload,
    })
    // 不触发后端保存（列偏好仅前端 UI 控制，非审计数据）
  }

  // ─── 列可见性判定 ──────────────────────────────────────────────────────

  function isColumnVisible(key: string): boolean {
    return visibleKeys.value.has(key)
  }

  // ─── 切换单列 ──────────────────────────────────────────────────────────

  function toggleColumn(key: string, visible: boolean): void {
    if (visible) {
      visibleKeys.value.add(key)
    } else {
      visibleKeys.value.delete(key)
    }
    activePreset.value = 'custom'
    savePrefs()
  }

  // ─── 切换整组 ──────────────────────────────────────────────────────────

  function toggleGroup(group: ColumnGroup, visible: boolean): void {
    const groupCols = allColumns.value.filter(c => c.group === group)
    for (const col of groupCols) {
      if (visible) visibleKeys.value.add(col.key)
      else visibleKeys.value.delete(col.key)
    }
    activePreset.value = 'custom'
    savePrefs()
  }

  function isGroupVisible(group: ColumnGroup): boolean {
    const groupCols = allColumns.value.filter(c => c.group === group)
    return groupCols.every(c => visibleKeys.value.has(c.key))
  }

  function isGroupPartial(group: ColumnGroup): boolean {
    const groupCols = allColumns.value.filter(c => c.group === group)
    const visCount = groupCols.filter(c => visibleKeys.value.has(c.key)).length
    return visCount > 0 && visCount < groupCols.length
  }

  // ─── 预设方案应用 ──────────────────────────────────────────────────────

  function applyPreset(name: PresetName): void {
    activePreset.value = name
    const preset = PRESETS.find(p => p.name === name)
    if (!preset) return

    if (preset.visibleKeys === 'all') {
      visibleKeys.value = new Set(allColumns.value.map(c => c.key))
    } else {
      const keys = new Set(preset.visibleKeys)
      // "审定+账龄"预设自动追加所有审定账龄段
      if (name === 'audited-aging') {
        for (const col of allColumns.value) {
          if (col.key.startsWith(_AGING_AUDITED_PREFIX)) keys.add(col.key)
        }
      }
      visibleKeys.value = keys
    }
    savePrefs()
  }

  // ─── 隐藏空列（一键功能） ──────────────────────────────────────────────

  /**
   * 扫描当前数据行，将所有行该列值均为 0/空/""/null 的列自动隐藏。
   * 基础列（seq/customerName）始终保留不隐藏。
   */
  function hideEmptyColumns(): void {
    const alwaysKeep = new Set(['seq', 'customerName', 'companyCode', 'relationType'])
    const currentRows = rows.value

    if (currentRows.length === 0) return

    for (const col of allColumns.value) {
      if (alwaysKeep.has(col.key)) continue

      const isEmpty = currentRows.every(row => {
        const val = getColumnValue(row, col.key)
        return val === 0 || val === '' || val === null || val === undefined || val === '-' || val === false
      })

      if (isEmpty) {
        visibleKeys.value.delete(col.key)
      }
    }

    activePreset.value = 'custom'
    savePrefs()
  }

  /**
   * 从 DetailRow 中取指定列的值（处理嵌套 aging 字段）
   */
  function getColumnValue(row: DetailRow, key: string): unknown {
    if (key.startsWith(_AGING_PRIOR_PREFIX)) {
      const bandKey = key.slice(_AGING_PRIOR_PREFIX.length)
      return row.agingPrior?.[bandKey] ?? 0
    }
    if (key.startsWith(_AGING_CURRENT_PREFIX)) {
      const bandKey = key.slice(_AGING_CURRENT_PREFIX.length)
      return row.agingCurrent?.[bandKey] ?? 0
    }
    if (key.startsWith(_AGING_AUDITED_PREFIX)) {
      const bandKey = key.slice(_AGING_AUDITED_PREFIX.length)
      return row.agingAudited?.[bandKey] ?? 0
    }
    return (row as any)[key]
  }

  // ─── 可见列数统计 ──────────────────────────────────────────────────────

  const visibleCount = computed(() => visibleKeys.value.size)
  const totalCount = computed(() => allColumns.value.length)

  // ─── 分组列表（供 UI 渲染 checkbox group） ─────────────────────────────

  const groups: ComputedRef<ColumnGroup[]> = computed(() => {
    const seen = new Set<ColumnGroup>()
    for (const col of allColumns.value) {
      seen.add(col.group)
    }
    return Array.from(seen)
  })

  function getGroupColumns(group: ColumnGroup): ColumnDef[] {
    return allColumns.value.filter(c => c.group === group)
  }

  // ─── 监听 bands 变化重建可见集（保持新增段默认可见） ─────────────────────

  watch(bands, () => {
    // 新增的账龄段自动加入可见集
    for (const col of allColumns.value) {
      if (!visibleKeys.value.has(col.key) && col.defaultVisible && activePreset.value === 'all') {
        visibleKeys.value.add(col.key)
      }
    }
  })

  // ─── 初始加载 ──────────────────────────────────────────────────────────

  // 延迟到 allResponses 有数据后加载
  watch(
    () => allResponses.value.size,
    () => { if (visibleKeys.value.size === 0) loadPrefs() },
    { immediate: true },
  )

  return {
    // 列定义
    allColumns,
    groups,
    getGroupColumns,

    // 可见性
    isColumnVisible,
    toggleColumn,
    toggleGroup,
    isGroupVisible,
    isGroupPartial,
    visibleKeys,
    visibleCount,
    totalCount,

    // 预设
    activePreset,
    applyPreset,
    presets: PRESETS,

    // 功能
    hideEmptyColumns,
  }
}

export default useD2DetailColumnPrefs
