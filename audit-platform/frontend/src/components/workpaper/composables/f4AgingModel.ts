/**
 * f4AgingModel — F4 应付账款账龄纯函数（段驱动单一真源的派生逻辑）
 *
 * Spec: .kiro/specs/f4-aging-enum-unification/
 *
 * F4 账龄两期：`agingCurrent`（期末未审账龄，源表 N:Q）、`agingAudited`（期末审定账龄，U:X），
 * **无期初账龄**；段来自项目账龄配置（`useAgingConfig(projectId,'F4')`，3年段/5年段/自定义）。
 *
 * 设计要点：
 * - F4-1 审定表按账龄区块 rowKey 沿用既有存储键（3 年段 → within1year/1to2year/2to3year/3yearplus），
 *   映射表未覆盖的段直接用段 key（Property 8）。
 * - `aging-other` 是 F4 特有**残差行**（承接明细账龄合计与期末余额差额、未按账龄拆分的 RJE），
 *   不是账龄段：不参与段映射、**不计入「1 年以上」**，但仍进小计与交叉核对（Property 5）。
 * - 「1 年以上」段集合按 `dayFrom >= 366` 从生效段派生，禁止硬编码档位（Property 4）。
 */
import type { AgingSegment } from '@/composables/useAgingConfig'
import type { AgingData } from '@/composables/useAgingMigration'

/** F4 账龄期间：期末未审 / 期末审定（F4 无期初账龄） */
export type F4AgingPeriod = 'current' | 'audited'

/** 期间 → 行内 nested 字段名 */
export const F4_AGING_FIELD: Record<F4AgingPeriod, 'agingCurrent' | 'agingAudited'> = {
  current: 'agingCurrent',
  audited: 'agingAudited',
}

/** F4-1 按账龄区块残差行（其他/未分类）——不是账龄段 */
export const F4_RESIDUAL_ROW_KEY = 'aging-other'
export const F4_RESIDUAL_ROW_LABEL = '其他/未分类'

/**
 * 段 key → F4-1 既有 rowKey 映射（3 年段沿用迁移前存储键，实现零数据迁移）。
 * 未覆盖的段（y3to4/y4to5/over5/自定义）直接用段 key。
 */
export const LEGACY_AGING_ROWKEY: Record<string, string> = {
  within1: 'within1year',
  y1to2: '1to2year',
  y2to3: '2to3year',
  over3: '3yearplus',
}

/**
 * F4 明细/检查表账龄文案（逐字取自源 xlsx `明细表F4-2` N10:Q10「1年以下/1～2年/２～3年/3年以上」，
 * 3 年段沿用迁移前 F4 用词，避免披露/检查表文案回归）。
 *
 * 5 年段三档按同一「X～Y年」构词延伸——不加会退回账龄配置 `seg.label`（「3-4年」半角连字符），
 * 与前 4 档用词分裂。分组按段 **key**，此处仅影响展示与下拉选项文案；
 * `extractOverOneYearRows` 另保留 `seg.label` 兜底匹配，故既有存量数据不失配。
 *
 * 注意平台内 F4 有三套账龄用词，各有权威源，不要相互"修正"：
 * - 本表（明细/检查表）：`1～2年`
 * - `useF4Adjudication.LEGACY_AGING_LABEL`（F4-1 审定表 / 国企披露表）：`1至2年（含2年）`
 * - `f4NoteSectionMap.F4_NOTE_AGING_LABEL`（附注模块）：`1至2年`
 */
export const LEGACY_AGING_TEXT: Record<string, string> = {
  within1: '1年以内',
  y1to2: '1～2年',
  y2to3: '2～3年',
  over3: '3年以上',
  y3to4: '3～4年',
  y4to5: '4～5年',
  over5: '5年以上',
}

/** 段 → F4 展示用账龄文案 */
export function f4AgingLabel(seg: AgingSegment): string {
  return LEGACY_AGING_TEXT[String(seg?.key)] ?? String(seg?.label ?? '')
}

/** 段 key → F4-1 rowKey（Property 8：3 年段恒为既有 4 键；其它段恒为段 key） */
export function f4AgingRowKey(segKey: string): string {
  return LEGACY_AGING_ROWKEY[segKey] ?? segKey
}

/** 「1 年以上」段 key 集合（dayFrom >= 366，Property 4） */
export function overOneYearKeys(segments: readonly AgingSegment[]): string[] {
  return (segments ?? []).filter((seg) => Number(seg?.dayFrom) >= 366).map((seg) => String(seg.key))
}

/** 「1 年以上」段对应的 F4-1 rowKey 集合（残差行不在其中） */
export function overOneYearRowKeys(segments: readonly AgingSegment[]): string[] {
  return overOneYearKeys(segments).map(f4AgingRowKey)
}

function toNum(val: unknown): number {
  if (val == null) return 0
  const num = Number(val)
  return Number.isFinite(num) ? num : 0
}

/**
 * F4 旧扁平字段名（段 key → 字段名），仅 3 年段 4 档有一一对应字段。
 * 用于 nested 缺该段键时的 legacy 回退读取，以及兼容层派生。
 */
const LEGACY_FLAT_FIELD: Record<F4AgingPeriod, Record<string, string>> = {
  current: {
    within1: 'unadjustedAgingLt1',
    y1to2: 'unadjustedAging1to2',
    y2to3: 'unadjustedAging2to3',
    over3: 'unadjustedAgingGt3',
  },
  audited: {
    within1: 'auditedAgingLt1',
    y1to2: 'auditedAging1to2',
    y2to3: 'auditedAging2to3',
    over3: 'auditedAgingGt3',
  },
}

/**
 * 读某行某期间某段金额：**nested 优先**，nested 缺该键时回退 legacy 扁平字段（Property 2）。
 */
export function f4AgingValue(row: any, period: F4AgingPeriod, segKey: string): number {
  const nested = row?.[F4_AGING_FIELD[period]]
  if (nested && typeof nested === 'object' && nested[segKey] !== undefined) {
    return toNum(nested[segKey])
  }
  const flatKey = LEGACY_FLAT_FIELD[period][segKey]
  return flatKey ? toNum(row?.[flatKey]) : 0
}

/** 单行某期间在给定段集合上的合计（用于双账龄勾稽，Property 7） */
export function sumRowAging(row: any, period: F4AgingPeriod, segKeys: readonly string[]): number {
  return (segKeys ?? []).reduce((sum, key) => sum + f4AgingValue(row, period, key), 0)
}

/**
 * 多行按段聚合（Property 1：等于逐行逐段求和）。
 * 返回 `Record<segKey, number>`，未出现的段补 0。
 */
export function aggregateAgingBySegments(
  rows: readonly any[],
  period: F4AgingPeriod,
  segKeys: readonly string[],
): Record<string, number> {
  const out: Record<string, number> = {}
  for (const key of segKeys ?? []) out[key] = 0
  for (const row of rows ?? []) {
    for (const key of segKeys ?? []) {
      out[key] += f4AgingValue(row, period, key)
    }
  }
  return out
}

/**
 * 兼容层：从 nested 派生 3 年段扁平字段（供尚未迁移的读取方 / 导出兼容）。
 *
 * - within1 / y1to2 / y2to3 一一对应；
 * - `Gt3` = 所有 `dayFrom >= 1096` 段之和（3 年段下恰等于 over3，故 3 年段逐字节不变；
 *   5 年段/自定义下为「3 年以上」的汇总投影，仅兼容用，不作为权威值）。
 */
export function projectLegacyFlatAging(
  row: any,
  period: F4AgingPeriod,
  segments: readonly AgingSegment[],
): Record<string, number> {
  const fields = LEGACY_FLAT_FIELD[period]
  const out: Record<string, number> = {
    [fields.within1]: 0,
    [fields.y1to2]: 0,
    [fields.y2to3]: 0,
    [fields.over3]: 0,
  }
  for (const seg of segments ?? []) {
    const key = String(seg.key)
    const value = f4AgingValue(row, period, key)
    if (key === 'within1' || key === 'y1to2' || key === 'y2to3') {
      out[fields[key]] += value
    } else if (Number(seg.dayFrom) >= 1096) {
      out[fields.over3] += value
    } else {
      // 1 年以内/1-3 年区间内的自定义段：按 dayFrom 归入最接近的兼容档位
      if (Number(seg.dayFrom) >= 731) out[fields.y2to3] += value
      else if (Number(seg.dayFrom) >= 366) out[fields.y1to2] += value
      else out[fields.within1] += value
    }
  }
  return out
}

/** 为给定段集合创建全零 nested 账龄对象 */
export function createEmptyF4Aging(segments: readonly AgingSegment[]): AgingData {
  const out: AgingData = {}
  for (const seg of segments ?? []) out[String(seg.key)] = 0
  return out
}
