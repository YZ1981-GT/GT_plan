/**
 * useFraudRiskData — D0-8 舞弊风险评价表数据核心 composable
 *
 * 职责：
 * - 从 htmlData 初始化 items（_format: fraud-risk-d08-v1）
 * - 合并预置条目 + 已有数据（不覆盖用户已填内容）
 * - items CRUD（addItem / deleteItem / updateItem）
 * - 看板指标（metrics）
 * - 条件高亮判断（是=是 → 行高亮 / 应对空 → 橙）
 * - buildPayload 持久化
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  FraudRiskRow,
  FraudRiskSummary,
  FraudRiskConclusion,
  FraudRiskMetrics,
  FraudRiskPayload,
} from '../fraudRiskTypes'
import { PRESET_FRAUD_ITEMS } from '../fraudRiskPresets'

// ─── 工具函数 ────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function precise2(val: number): number {
  return Math.round(val * 100) / 100
}

// ─── Props / Return 接口 ─────────────────────────────────────────────────────

export interface UseFraudRiskDataProps {
  /** 响应式数据源（来自底稿的 htmlData） */
  htmlData: () => any
  /** 是否只读 */
  readonly: boolean
}

export interface UseFraudRiskDataReturn {
  items: Ref<FraudRiskRow[]>
  summary: Ref<FraudRiskSummary>
  conclusion: Ref<FraudRiskConclusion>
  isDirty: Ref<boolean>

  // CRUD
  addItem: () => FraudRiskRow
  deleteItem: (rowId: string) => void
  updateItem: (rowId: string, field: string, value: any) => void
  importItems: (newItems: FraudRiskRow[]) => void

  // 状态判断
  isHighlighted: (row: FraudRiskRow) => boolean
  needsCountermeasure: (row: FraudRiskRow) => boolean

  // 看板
  metrics: ComputedRef<FraudRiskMetrics>

  // 持久化
  buildPayload: () => FraudRiskPayload
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export function useFraudRiskData(props: UseFraudRiskDataProps): UseFraudRiskDataReturn {
  const items = ref<FraudRiskRow[]>([])
  const summary = ref<FraudRiskSummary>({})
  const conclusion = ref<FraudRiskConclusion>({})
  const isDirty = ref(false)

  // ─── 从 htmlData 初始化（合并预置+已有） ──────────────────────────────────

  function initFromHtmlData(data: any) {
    if (!data || !data._format) {
      // 无数据或旧格式 → 纯预置初始化
      items.value = initFromPreset()
      summary.value = {}
      conclusion.value = {}
      isDirty.value = false
      return
    }

    const existingItems: FraudRiskRow[] = Array.isArray(data.items) ? data.items : []
    items.value = mergePresetWithExisting(existingItems)
    summary.value = data.summary ?? {}
    conclusion.value = data.conclusion ?? {}
    isDirty.value = false
  }

  /** 纯预置初始化（首次加载） */
  function initFromPreset(): FraudRiskRow[] {
    return PRESET_FRAUD_ITEMS.map((preset) => ({
      _row_id: generateRowId(),
      seq: preset.seq,
      description: preset.description,
      is_exist: '' as const,
      source_ref: '',
      countermeasure: '',
      _preset: true,
      tooltip_key: preset.tooltip_key,
      _source: 'preset' as const,
    }))
  }

  /** 合并策略：预置条目以 seq 为键匹配，保留用户已填值不覆盖 */
  function mergePresetWithExisting(existing: FraudRiskRow[]): FraudRiskRow[] {
    const existingBySeq = new Map<number, FraudRiskRow>()
    const customItems: FraudRiskRow[] = []

    existing.forEach((item) => {
      if (item._preset) {
        existingBySeq.set(item.seq, item)
      } else {
        customItems.push(ensureRowId(item))
      }
    })

    // 预置条目：用户已有则保留，否则补充
    const presetRows: FraudRiskRow[] = PRESET_FRAUD_ITEMS.map((preset) => {
      const userRow = existingBySeq.get(preset.seq)
      if (userRow) {
        return ensureRowId({
          ...userRow,
          tooltip_key: preset.tooltip_key, // tooltip 始终取最新预置
          _preset: true,
        })
      }
      return {
        _row_id: generateRowId(),
        seq: preset.seq,
        description: preset.description,
        is_exist: '' as const,
        source_ref: '',
        countermeasure: '',
        _preset: true,
        tooltip_key: preset.tooltip_key,
        _source: 'preset' as const,
      }
    })

    return [...presetRows, ...customItems]
  }

  function ensureRowId(row: FraudRiskRow): FraudRiskRow {
    if (!row._row_id) return { ...row, _row_id: generateRowId() }
    return row
  }

  // 初始加载
  initFromHtmlData(props.htmlData())

  // 监听 htmlData 变化
  watch(
    () => props.htmlData(),
    (newData) => { initFromHtmlData(newData) },
    { deep: true }
  )

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addItem(): FraudRiskRow {
    const maxSeq = items.value.reduce((max, i) => Math.max(max, i.seq ?? 0), 0)
    const newItem: FraudRiskRow = {
      _row_id: generateRowId(),
      seq: maxSeq + 1,
      description: '',
      is_exist: '',
      source_ref: '',
      countermeasure: '',
      _preset: false,
      _source: 'manual',
    }
    items.value.push(newItem)
    isDirty.value = true
    return newItem
  }

  function deleteItem(rowId: string) {
    const idx = items.value.findIndex((i) => i._row_id === rowId)
    if (idx === -1) return
    // 预置条目不可删除（仅自定义可删）
    if (items.value[idx]._preset) return
    items.value.splice(idx, 1)
    isDirty.value = true
  }

  function updateItem(rowId: string, field: string, value: any) {
    const item = items.value.find((i) => i._row_id === rowId)
    if (!item) return
    ;(item as any)[field] = value
    isDirty.value = true
  }

  function importItems(newItems: FraudRiskRow[]) {
    const maxSeq = items.value.reduce((max, i) => Math.max(max, i.seq ?? 0), 0)
    newItems.forEach((item, i) => {
      item._row_id = generateRowId()
      item.seq = maxSeq + i + 1
      item._preset = false
      item._source = item._source || 'manual'
    })
    items.value.push(...newItems)
    isDirty.value = true
  }

  // ─── 条件高亮判断 ──────────────────────────────────────────────────────────

  function isHighlighted(row: FraudRiskRow): boolean {
    return row.is_exist === '是'
  }

  function needsCountermeasure(row: FraudRiskRow): boolean {
    return row.is_exist === '是' && !row.countermeasure?.trim()
  }

  // ─── 看板指标 ──────────────────────────────────────────────────────────────

  const metrics = computed<FraudRiskMetrics>(() => {
    const total = items.value.length
    const existItems = items.value.filter((i) => i.is_exist === '是')
    const existCount = existItems.length
    const withMeasure = existItems.filter((i) => !!i.countermeasure?.trim()).length
    const withoutMeasure = existCount - withMeasure
    const evaluated = items.value.filter((i) => i.is_exist && i.is_exist !== '').length
    const completionRate = total > 0 ? precise2((evaluated / total) * 100) : 0

    return {
      total_count: total,
      exist_count: existCount,
      with_measure_count: withMeasure,
      without_measure_count: withoutMeasure,
      completion_rate: completionRate,
    }
  })

  // ─── buildPayload ──────────────────────────────────────────────────────────

  function buildPayload(): FraudRiskPayload {
    return {
      _format: 'fraud-risk-d08-v1',
      items: items.value.map((item) => ({ ...item })),
      summary: { ...summary.value },
      conclusion: { ...conclusion.value },
    }
  }

  return {
    items,
    summary,
    conclusion,
    isDirty,

    addItem,
    deleteItem,
    updateItem,
    importItems,

    isHighlighted,
    needsCountermeasure,

    metrics,

    buildPayload,
  }
}
