import { computed, type ComputedRef } from 'vue'
import { useDisplayPrefsStore, type TableDensity } from '@/stores/displayPrefs'

/**
 * 虚拟表格与普通表格共用的密度指标。
 *
 * `displayPrefs.densityConfig` 是密度的唯一配置来源；这里把 CSS 字符串
 * 转成 Element Plus Table V2 需要的数字，避免各页面再次硬编码行高。
 */
export interface TableDensityMetrics {
  density: ComputedRef<TableDensity>
  rowHeight: ComputedRef<number>
  estimatedRowHeight: ComputedRef<number>
  headerHeight: ComputedRef<number>
  remountKey: ComputedRef<string>
}

function toPixels(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export function useTableDensityMetrics(): TableDensityMetrics {
  const displayPrefs = useDisplayPrefsStore()
  const density = computed(() => displayPrefs.density)
  const rowHeight = computed(() => toPixels(displayPrefs.densityConfig.rowHeight, 40))

  return {
    density,
    rowHeight,
    estimatedRowHeight: rowHeight,
    // Table V2 的表头也随密度重挂载，避免切换后表头与数据行错位。
    headerHeight: rowHeight,
    // 字号也会影响内容测量，因此必须触发行高/列宽重新初始化。
    remountKey: computed(() => `${displayPrefs.fontSize}:${density.value}`),
  }
}
