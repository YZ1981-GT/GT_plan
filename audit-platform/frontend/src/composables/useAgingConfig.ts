/**
 * useAgingConfig — 项目级账龄配置 composable
 *
 * 统一为所有往来款明细表（D2/D3/F1/K1/K3/G5/G2）提供响应式的账龄段和列定义。
 *
 * 核心能力：
 * - GET /api/projects/{id}/aging/config 获取配置
 * - segments → bands 转换（生成 priorField/currentField/auditedField）
 * - per-project-session 缓存（key = projectId，EventBus 触发刷新）
 * - 监听 window event `aging-config:changed` 自动 refresh
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export type AgingPreset = 'THREE_YEAR' | 'FIVE_YEAR' | 'CUSTOM'

export interface AgingSegment {
  key: string        // 唯一标识 (e.g. "within1", "y1to2")
  label: string      // 显示名 (e.g. "1年以内", "1-2年")
  dayFrom: number    // 起始天数 (含)
  dayTo: number | null  // 结束天数 (含), null=无上限
}

export interface AgingBand {
  key: string           // segment key (唯一标识)
  label: string         // 显示名
  priorField: string    // 期初字段 key (e.g. "agingPrior.within1")
  currentField: string  // 期末未审字段 key (仅 3-period subjects 有)
  auditedField: string  // 期末审定字段 key
}

export interface UseAgingConfigReturn {
  segments: Ref<AgingSegment[]>       // 有序段列表
  bands: Ref<AgingBand[]>             // 列定义（供 el-table-column 渲染）
  preset: Ref<AgingPreset>            // 当前预设
  loading: Ref<boolean>
  refresh: () => Promise<void>        // 手动刷新
}

/** API 响应结构 */
interface AgingConfigResponse {
  preset: AgingPreset
  effective_segments: AgingSegment[]
  subject_overrides: Record<string, AgingPreset>
}

// ─── 3-period subjects（有 agingCurrent 字段） ────────────────────────────────

const THREE_PERIOD_SUBJECTS = new Set(['D2', 'K1', 'K3', 'G5', 'F1'])

// ─── Per-project-session 缓存 ─────────────────────────────────────────────────

interface CacheEntry {
  preset: AgingPreset
  segments: AgingSegment[]
  subjectOverrides: Record<string, AgingPreset>
}

const _cache = new Map<string, CacheEntry>()

// ─── segments → bands 转换（纯函数，可独立测试） ──────────────────────────────

/**
 * 将 segments 转换为 bands（列定义），根据 subject 决定是否生成 currentField
 */
export function segmentsToBands(segments: AgingSegment[], subject?: string): AgingBand[] {
  const isThreePeriod = subject ? THREE_PERIOD_SUBJECTS.has(subject) : true
  return segments.map((seg) => ({
    key: seg.key,
    label: seg.label,
    priorField: `agingPrior.${seg.key}`,
    currentField: isThreePeriod ? `agingCurrent.${seg.key}` : '',
    auditedField: `agingAudited.${seg.key}`,
  }))
}

/** 导出列头的账龄期间标签（与后端 AGING_PERIOD_LABELS 保持一致） */
export const AGING_EXPORT_PERIOD_LABELS = {
  prior: '期初',
  current: '期末未审',
  audited: '期末审定',
} as const

/**
 * 从 bands 生成导出账龄列头（供导出服务动态列头使用）。
 *
 * - 3-period subjects（D2/K1/K3/G5/F1）：每个 band 生成 3 列（期初/期末未审/期末审定）→ 3N 列
 * - 2-period subjects（D3）：每个 band 生成 2 列（期初/期末审定）→ 2N 列
 *
 * 列头顺序严格遵循 bands 数组顺序，并使用 band.label。
 * 列头格式：`{label}({periodLabel})`，例如 `1年以内(期初)`。
 *
 * 是否含「期末未审」列由 band.currentField 是否非空决定（segmentsToBands 已按 subject 设置）。
 *
 * Requirements: 8.1
 */
export function buildAgingExportHeaders(bands: AgingBand[], _subject?: string): string[] {
  const headers: string[] = []
  for (const band of bands) {
    headers.push(`${band.label}(${AGING_EXPORT_PERIOD_LABELS.prior})`)
    if (band.currentField) {
      headers.push(`${band.label}(${AGING_EXPORT_PERIOD_LABELS.current})`)
    }
    headers.push(`${band.label}(${AGING_EXPORT_PERIOD_LABELS.audited})`)
  }
  return headers
}

/**
 * 为指定 subject 创建空的 aging 数据对象（所有段初始化为 0）
 */
export function createEmptyAgingData(
  segments: AgingSegment[],
  subject?: string,
): { agingPrior: Record<string, number>; agingCurrent?: Record<string, number>; agingAudited: Record<string, number> } {
  const isThreePeriod = subject ? THREE_PERIOD_SUBJECTS.has(subject) : true
  const empty: Record<string, number> = {}
  for (const seg of segments) {
    empty[seg.key] = 0
  }
  const result: any = {
    agingPrior: { ...empty },
    agingAudited: { ...empty },
  }
  if (isThreePeriod) {
    result.agingCurrent = { ...empty }
  }
  return result
}

// ─── Composable 实现 ──────────────────────────────────────────────────────────

export function useAgingConfig(
  projectId: Ref<string>,
  subject?: string,
): UseAgingConfigReturn {
  const segments = ref<AgingSegment[]>([])
  const preset = ref<AgingPreset>('FIVE_YEAR')
  const loading = ref(false)

  const bands = computed<AgingBand[]>(() => segmentsToBands(segments.value, subject))

  // ── 从缓存或 API 加载配置 ─────────────────────────────────

  async function fetchConfig(): Promise<void> {
    const pid = projectId.value
    if (!pid) return

    // 缓存命中
    const cached = _cache.get(pid)
    if (cached) {
      _applyConfig(cached, pid)
      return
    }

    // API 拉取
    loading.value = true
    try {
      const res = await api.get<AgingConfigResponse>(
        `/api/projects/${pid}/aging/config`,
        { _silent: true } as any,
      )
      const entry: CacheEntry = {
        preset: res.preset,
        segments: res.effective_segments,
        subjectOverrides: res.subject_overrides || {},
      }
      _cache.set(pid, entry)
      _applyConfig(entry, pid)
    } catch (err: any) {
      // 加载失败：使用默认配置兜底（FIVE_YEAR）
      console.warn('[useAgingConfig] 加载失败，使用默认配置', err?.message)
      _applyDefault()
    } finally {
      loading.value = false
    }
  }

  function _applyConfig(entry: CacheEntry, _pid: string): void {
    // 如果有 subject override，使用覆盖配置
    if (subject && entry.subjectOverrides[subject]) {
      const overridePreset = entry.subjectOverrides[subject]
      preset.value = overridePreset
      // 预设覆盖时使用预定义段
      segments.value = PRESET_SEGMENTS[overridePreset] ?? entry.segments
    } else {
      preset.value = entry.preset
      segments.value = entry.segments
    }
  }

  function _applyDefault(): void {
    // 默认：D3/F1/D7 使用 THREE_YEAR，其他使用 FIVE_YEAR
    const defaultPreset: AgingPreset = (subject === 'D3' || subject === 'F1' || subject === 'D7')
      ? 'THREE_YEAR'
      : 'FIVE_YEAR'
    preset.value = defaultPreset
    segments.value = PRESET_SEGMENTS[defaultPreset]
  }

  // ── 手动刷新（清缓存后重拉） ────────────────────────────

  async function refresh(): Promise<void> {
    const pid = projectId.value
    if (pid) {
      _cache.delete(pid)
    }
    await fetchConfig()
  }

  // ── EventBus 监听 window event ─────────────────────────

  function _onConfigChanged(): void {
    refresh()
  }

  onMounted(() => {
    window.addEventListener('aging-config:changed', _onConfigChanged)
    fetchConfig()
  })

  onUnmounted(() => {
    window.removeEventListener('aging-config:changed', _onConfigChanged)
  })

  // ── projectId 变化时重新加载 ─────────────────────────────

  watch(projectId, (newId, oldId) => {
    if (newId && newId !== oldId) {
      fetchConfig()
    }
  })

  return {
    segments,
    bands,
    preset,
    loading,
    refresh,
  }
}

// ─── 预设段定义（前端兜底，与后端保持一致） ──────────────────────────────────

export const PRESET_SEGMENTS: Record<string, AgingSegment[]> = {
  THREE_YEAR: [
    { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
    { key: 'y1to2', label: '1-2年', dayFrom: 366, dayTo: 730 },
    { key: 'y2to3', label: '2-3年', dayFrom: 731, dayTo: 1095 },
    { key: 'over3', label: '3年以上', dayFrom: 1096, dayTo: null },
  ],
  FIVE_YEAR: [
    { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
    { key: 'y1to2', label: '1-2年', dayFrom: 366, dayTo: 730 },
    { key: 'y2to3', label: '2-3年', dayFrom: 731, dayTo: 1095 },
    { key: 'y3to4', label: '3-4年', dayFrom: 1096, dayTo: 1460 },
    { key: 'y4to5', label: '4-5年', dayFrom: 1461, dayTo: 1825 },
    { key: 'over5', label: '5年以上', dayFrom: 1826, dayTo: null },
  ],
}

/**
 * 使指定项目的缓存失效（供 AgingConfigDialog 保存后调用）
 */
export function invalidateAgingConfigCache(projectId: string): void {
  _cache.delete(projectId)
}

/**
 * 清空所有缓存（项目切换时调用）
 */
export function clearAgingConfigCache(): void {
  _cache.clear()
}
