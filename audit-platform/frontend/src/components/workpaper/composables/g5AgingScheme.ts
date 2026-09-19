/**
 * g5AgingScheme — G5 账龄口径统一解析与迁移
 *
 * 目标：G5-2 / G5-10 / 上市·国企附注共享同一套 segment key 与切换规则。
 * - 3年 / 5年：复用项目级 PRESET_SEGMENTS
 * - 自定义：稳定 key（custom-0…），2–10 段
 * - 5年→3年：y3to4 + y4to5 + over5（及既有 over3）汇入 over3
 * - 3年→5年：over3 汇入 over5，不自动拆分中间段
 */
import {
  PRESET_SEGMENTS,
  type AgingPreset,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import type { AgingData } from '@/composables/useAgingMigration'

export type G5AgingPreset = AgingPreset

/** G5-10 源模板双标签（账龄/逾期），仅展示用 */
export const G5_DISPLAY_LABEL_FIVE_YEAR: Record<string, string> = {
  within1: '1年以内/未逾期',
  y1to2: '1-2年/逾期30天以内',
  y2to3: '2-3年/逾期31-90天',
  y3to4: '3-4年/逾期91天-1年',
  y4to5: '4-5年/逾期1-2年',
  over5: '5年以上/逾期2年以上',
}

export const G5_DISPLAY_LABEL_THREE_YEAR: Record<string, string> = {
  within1: '1年以内(含1年)',
  y1to2: '1-2年(含2年)',
  y2to3: '2-3年(含3年)',
  over3: '3年以上',
}

/** 切换到目标段时，从哪些旧 key 汇总金额 */
const ROLLUP_SOURCES: Record<string, string[]> = {
  // 5→3：长账龄并入 3 年以上
  over3: ['over3', 'y3to4', 'y4to5', 'over5'],
  // 3→5：无法拆分时保守并入 5 年以上
  over5: ['over5', 'over3', 'y3to4', 'y4to5'],
}

export function labelsToG5CustomSegments(labels: string[]): AgingSegment[] {
  return labels
    .map((l) => l.trim())
    .filter(Boolean)
    .slice(0, 10)
    .map((label, i) => ({
      key: `custom-${i}`,
      label,
      dayFrom: 0,
      dayTo: null,
    }))
}

export function resolveG5AgingSegments(
  preset: G5AgingPreset,
  customLabels: string[] = [],
): AgingSegment[] {
  if (preset === 'CUSTOM') {
    const segs = labelsToG5CustomSegments(customLabels)
    return segs.length >= 2 ? segs : PRESET_SEGMENTS.FIVE_YEAR.map((s) => ({ ...s }))
  }
  return (PRESET_SEGMENTS[preset] || PRESET_SEGMENTS.FIVE_YEAR).map((s) => ({ ...s }))
}

/** G5-10 展示标签：预设用双标签，自定义用段名 */
export function resolveG5DisplaySegments(
  preset: G5AgingPreset,
  customLabels: string[] = [],
): AgingSegment[] {
  const base = resolveG5AgingSegments(preset, customLabels)
  if (preset === 'CUSTOM') return base
  const overlay =
    preset === 'THREE_YEAR' ? G5_DISPLAY_LABEL_THREE_YEAR : G5_DISPLAY_LABEL_FIVE_YEAR
  return base.map((s) => ({ ...s, label: overlay[s.key] || s.label }))
}

function toNum(val: unknown): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * 按目标 segments 重映射账龄金额；已知长短账龄切换走汇总，避免总额丢失。
 */
export function remapAgingDataWithAggregation(
  agingData: AgingData | null | undefined,
  newSegments: AgingSegment[],
): AgingData {
  const old: AgingData = agingData && typeof agingData === 'object' ? agingData : {}
  const result: AgingData = {}
  const consumed = new Set<string>()

  for (const seg of newSegments) {
    const sources = ROLLUP_SOURCES[seg.key]
    if (sources) {
      // 仅当旧数据含需汇总的源 key 时启用 rollup（避免 CUSTOM 误伤）
      const hasRollupSource = sources.some((k) => k !== seg.key && k in old)
      if (hasRollupSource || seg.key in old) {
        let sum = 0
        for (const k of sources) {
          sum += toNum(old[k])
          consumed.add(k)
        }
        result[seg.key] = sum
        continue
      }
    }
    result[seg.key] = toNum(old[seg.key])
    consumed.add(seg.key)
  }
  return result
}

export function remapRowAgingWithAggregation(
  row: {
    agingPrior?: AgingData
    agingCurrent?: AgingData
    agingAudited?: AgingData
    [key: string]: unknown
  },
  newSegments: AgingSegment[],
  isThreePeriod = true,
): {
  agingPrior: AgingData
  agingCurrent: AgingData
  agingAudited: AgingData
} {
  return {
    agingPrior: remapAgingDataWithAggregation(row.agingPrior, newSegments),
    agingCurrent: isThreePeriod
      ? remapAgingDataWithAggregation(row.agingCurrent, newSegments)
      : remapAgingDataWithAggregation(row.agingCurrent || {}, newSegments),
    agingAudited: remapAgingDataWithAggregation(row.agingAudited, newSegments),
  }
}

export interface G5AgingBandLike {
  id: string
  bandKey: string
  label: string
  kind: 'band' | 'total'
  endBalance: number
  endProvision: number
  priorBalance: number
  priorProvision: number
}

function emptyBandAmounts() {
  return { endBalance: 0, endProvision: 0, priorBalance: 0, priorProvision: 0 }
}

/**
 * 附注组合账龄行：按目标 segments 重建 band 行，金额按 key/rollup 保留。
 */
export function remapDisclosureAgingRows(
  rows: G5AgingBandLike[],
  newSegments: AgingSegment[],
  uid: (prefix: string) => string = (p) =>
    `${p}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
): G5AgingBandLike[] {
  const bands = rows.filter((r) => r.kind === 'band')
  const byKey = new Map(bands.map((b) => [b.bandKey, b]))

  const pick = (keys: string[]) => {
    const amt = emptyBandAmounts()
    for (const k of keys) {
      const hit = byKey.get(k)
      if (!hit) continue
      amt.endBalance += toNum(hit.endBalance)
      amt.endProvision += toNum(hit.endProvision)
      amt.priorBalance += toNum(hit.priorBalance)
      amt.priorProvision += toNum(hit.priorProvision)
    }
    return amt
  }

  const nextBands: G5AgingBandLike[] = newSegments.map((seg) => {
    const sources = ROLLUP_SOURCES[seg.key]
    const hasRollup =
      sources && sources.some((k) => k !== seg.key && byKey.has(k))
    const amt = hasRollup
      ? pick(sources!)
      : (() => {
          const hit = byKey.get(seg.key)
          return hit
            ? {
                endBalance: toNum(hit.endBalance),
                endProvision: toNum(hit.endProvision),
                priorBalance: toNum(hit.priorBalance),
                priorProvision: toNum(hit.priorProvision),
              }
            : emptyBandAmounts()
        })()
    return {
      id: uid(`age-${seg.key}`),
      bandKey: seg.key,
      label: seg.label,
      kind: 'band' as const,
      ...amt,
    }
  })

  const sum = (field: keyof ReturnType<typeof emptyBandAmounts>) =>
    Math.round(nextBands.reduce((s, r) => s + toNum(r[field]), 0) * 100) / 100

  nextBands.push({
    id: uid('age-total'),
    bandKey: 'total',
    label: '合计',
    kind: 'total',
    endBalance: sum('endBalance'),
    endProvision: sum('endProvision'),
    priorBalance: sum('priorBalance'),
    priorProvision: sum('priorProvision'),
  })
  return nextBands
}

export function validateCustomAgingLabels(labels: string[]): string | null {
  const cleaned = labels.map((l) => l.trim()).filter(Boolean)
  if (cleaned.length < 2) return '自定义账龄至少需要 2 段'
  if (cleaned.length > 10) return '自定义账龄最多 10 段'
  const seen = new Set<string>()
  for (const l of cleaned) {
    if (seen.has(l)) return `账龄段名称重复：${l}`
    seen.add(l)
  }
  return null
}
