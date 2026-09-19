/**
 * useSampleSizeEngine — 控制测试样本规模区间表纯函数
 *
 * 纯函数，无副作用、无 API 调用、确定性输出。
 * 按控制运行频率与运行总次数自动建议最小样本规模区间。
 * 源自致同 2025 修订版模板样本规模区间提示表。
 */

// ─── 类型定义 ───────────────────────────────────────────────

/** 固定区间（非百分比计算）的表条目 */
export interface FixedSampleSizeEntry {
  frequency: string
  label: string
  totalCount: number
  min: number
  max: number
}

/** 百分比区间（按运行总次数计算）的表条目 */
export interface PctSampleSizeEntry {
  frequency: string
  label: string
  totalRange: [number, number]
  minPct: number
  maxPct: number
  cap: number
}

/** 范围匹配但固定区间（如"每天多次"：总次数>250，固定 25~60）的表条目 */
export interface RangeFixedSampleSizeEntry {
  frequency: string
  label: string
  totalRange: [number, number]
  min: number
  max: number
}

export type SampleSizeEntry = FixedSampleSizeEntry | PctSampleSizeEntry | RangeFixedSampleSizeEntry

/** suggestSampleSize 返回结果 */
export interface SampleSizeResult {
  min: number
  max: number
  note?: string
}

// ─── 类型守卫 ───────────────────────────────────────────────

export function isPctEntry(entry: SampleSizeEntry): entry is PctSampleSizeEntry {
  return 'totalRange' in entry && 'minPct' in entry
}

export function isRangeFixedEntry(entry: SampleSizeEntry): entry is RangeFixedSampleSizeEntry {
  return 'totalRange' in entry && 'min' in entry && !('minPct' in entry)
}

export function isFixedEntry(entry: SampleSizeEntry): entry is FixedSampleSizeEntry {
  return 'totalCount' in entry
}

// ─── 样本规模区间表（源模板） ────────────────────────────────

/**
 * 控制运行频率 × 控制运行总次数 → 最小样本规模区间
 *
 * | 控制运行频率 | 控制运行总次数 | 测试的最小样本规模区间 |
 * |---|---|---|
 * | 每年1次 | 1 | 1 |
 * | 每季1次 | 4 | 2 |
 * | 每月1次 | 12 | 2～5 |
 * | 每周1次 | 52 | 5～15 |
 * | 介于每周1次与每天一次之间 | 53-249次 | 10%-20%（最多40） |
 * | 每天1次 | 250 | 20～40 |
 * | 每天多次 | 大于250次 | 25～60 |
 */
export const SAMPLE_SIZE_TABLE: SampleSizeEntry[] = [
  { frequency: '每年', label: '每年1次', totalCount: 1, min: 1, max: 1 },
  { frequency: '每季度', label: '每季1次', totalCount: 4, min: 2, max: 2 },
  { frequency: '每月', label: '每月1次', totalCount: 12, min: 2, max: 5 },
  { frequency: '每周', label: '每周1次', totalCount: 52, min: 5, max: 15 },
  { frequency: '每半月', label: '介于每周与每天之间', totalRange: [53, 249], minPct: 0.10, maxPct: 0.20, cap: 40 },
  { frequency: '每天', label: '每天1次', totalCount: 250, min: 20, max: 40 },
  { frequency: '每天多次', label: '每天多次', totalRange: [251, Infinity], min: 25, max: 60 },
]

// ─── 核心纯函数 ─────────────────────────────────────────────

/**
 * 根据控制运行频率与运行总次数建议最小样本规模区间
 *
 * @param frequency - 控制运行频率（如 '每年'/'每季度'/'每月'/'每周'/'每半月'/'每天'/'每天多次'）
 * @param totalCount - 控制运行总次数
 * @returns { min, max, note? } 建议样本规模区间
 */
export function suggestSampleSize(frequency: string, totalCount: number): SampleSizeResult {
  // 无效输入处理
  if (!frequency || totalCount <= 0) {
    return { min: 0, max: 0, note: '无法确定样本规模：请选择控制频率并输入有效运行总次数' }
  }

  // 按频率匹配表条目
  const entry = SAMPLE_SIZE_TABLE.find(e => e.frequency === frequency)

  if (!entry) {
    return { min: 0, max: 0, note: `未知控制频率"${frequency}"，请手动确定样本量` }
  }

  // 百分比区间：按 totalCount 计算，上限 cap
  if (isPctEntry(entry)) {
    const rawMin = Math.ceil(totalCount * entry.minPct)
    const rawMax = Math.ceil(totalCount * entry.maxPct)
    const min = Math.min(rawMin, entry.cap)
    const max = Math.min(rawMax, entry.cap)
    return {
      min,
      max,
      note: `按${Math.round(entry.minPct * 100)}%~${Math.round(entry.maxPct * 100)}%计算（最多${entry.cap}）`,
    }
  }

  // 范围匹配固定区间（如"每天多次"）
  if (isRangeFixedEntry(entry)) {
    return { min: entry.min, max: entry.max }
  }

  // 固定区间
  return { min: entry.min, max: entry.max }
}

// ─── 辅助函数 ───────────────────────────────────────────────

/** 返回频率选项列表（供 el-select 使用） */
export function getFrequencyOptions(): string[] {
  return SAMPLE_SIZE_TABLE.map(e => e.frequency)
}
