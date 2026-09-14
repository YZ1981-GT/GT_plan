/**
 * ProjectGanttChart 工具函数（M-1）
 *
 * 提取为独立模块以便单元测试导入（Vue SFC `<script setup>` 不支持 `export`）。
 * 循环色板取自 constants/cyclePalette.ts 单一真源。
 */

import { CYCLE_PALETTE, cycleColor } from '@/constants/cyclePalette'

/** 循环字母 → 颜色（从统一真源 re-export，保持现有 import 不破坏） */
export const CYCLE_COLOR_MAP: Record<string, string> = { ...CYCLE_PALETTE }

// re-export cycleColor 保持现有导出名
export { cycleColor }

/** 循环字母 → 中文名（图例用） */
export const CYCLE_NAME_MAP: Record<string, string> = {
  D: '销售收入', E: '货币资金', F: '采购存货', G: '投资',
  H: '固定资产', I: '无形资产', J: '职工薪酬', K: '管理费用',
  L: '筹资', M: '权益', N: '税费', other: '其他',
}

/**
 * 循环字母 → 图例标签（"D 销售收入"）
 * 未知字母仅返回字母本身
 */
export function cycleLabel(cycle: string): string {
  const key = String(cycle).toUpperCase()
  const name = CYCLE_NAME_MAP[key] ?? CYCLE_NAME_MAP.other
  return key === 'OTHER' ? name : `${key} ${name}`
}

/**
 * ISO 日期字符串 → 时间戳（毫秒）
 * - null/undefined/空字符串 → null
 * - 无效日期 → null
 */
export function toTimestamp(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = new Date(iso).getTime()
  return Number.isFinite(t) ? t : null
}

export interface ProjectGanttItem {
  project_id: string
  project_name: string
  start_date: string | null  // ISO date e.g. '2025-01-01'
  due_date: string | null    // ISO date
  overall_progress: number   // 0-100
  primary_cycle?: string | null
}

export interface GanttRow {
  index: number
  project_id: string
  project_name: string
  start: number
  end: number
  progress: number
  cycle: string
  color: string
}

/**
 * 把原始 ProjectGanttItem[] 转为有效的 GanttRow[]
 * - 过滤掉缺失/无效日期 / end <= start 的项
 * - progress 截断到 [0, 100]
 * - 按 start 升序，重排 index
 */
export function buildGanttRows(items: ProjectGanttItem[]): GanttRow[] {
  const rows: GanttRow[] = []
  items.forEach((p, i) => {
    const start = toTimestamp(p.start_date)
    const end = toTimestamp(p.due_date)
    if (start === null || end === null || end <= start) return
    rows.push({
      index: i,
      project_id: p.project_id,
      project_name: p.project_name,
      start,
      end,
      progress: Math.max(0, Math.min(100, p.overall_progress ?? 0)),
      cycle: (p.primary_cycle ?? 'other').toUpperCase(),
      color: cycleColor(p.primary_cycle),
    })
  })
  rows.sort((a, b) => a.start - b.start)
  return rows.map((r, i) => ({ ...r, index: i }))
}
