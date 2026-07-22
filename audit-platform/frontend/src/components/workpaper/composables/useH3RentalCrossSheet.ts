/**
 * useH3RentalCrossSheet — H3-14 跨底稿联动（纯解析/取数，无行模型依赖）
 */
import http from '@/utils/http'
import { useAcnr } from '@/services/acnr/useAcnr'

// ─── Types ───────────────────────────────────────────────────────────────────

export type RentalAssetCategory = 'building' | 'land'

export interface H32AssetSeed {
  rowId: string
  assetName: string
  assetType: string
  area: number
  category: RentalAssetCategory
}

export interface D43RentalItem {
  rowId: string
  item: string
  currentAudited: number
  priorAudited: number
}

export interface D43RentalAggregate {
  totalCurrent: number
  totalPrior: number
  items: D43RentalItem[]
  loaded: boolean
  message: string
}

// ─── Constants ─────────────────────────────────────────────────────────────────

/** D4-3 项目名称中视为「租金/租赁」相关的关键词 */
export const RENTAL_D43_KEYWORDS = [
  '租金',
  '租赁',
  '出租',
  '投资性房地产',
  '经营租赁',
  '租出',
] as const

const H32_COST_KEY = 'H3-2-cost-rows'
const H32_FAIR_KEY = 'H3-2-fair-rows'
const D43_STORAGE_KEY = 'D4-3-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _parseJsonRows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

function _normName(s: string): string {
  return (s || '').trim().toLowerCase()
}

/** H3-2 资产类型 → H3-14 类别 */
export function mapH32AssetTypeToCategory(assetType: string): RentalAssetCategory {
  const t = (assetType || '').trim()
  if (/土地|使用权/.test(t)) return 'land'
  return 'building'
}

export function isRentalRelatedD43Item(item: string): boolean {
  const text = (item || '').trim()
  if (!text) return false
  return RENTAL_D43_KEYWORDS.some((kw) => text.includes(kw))
}

function _calcD43Audited(row: any): { current: number; prior: number } {
  const current = Number(row.currentAudited)
    || (Number(row.currentUnadjusted) || 0) + (Number(row.currentAdjustment) || 0)
  const prior = Number(row.priorAudited)
    || (Number(row.priorUnadjusted) || 0) + (Number(row.priorAdjustment) || 0)
  return { current, prior }
}

/** 从本底稿 allResponses 解析 H3-2 资产种子 */
export function extractH32Assets(
  getValue: (id: string) => unknown,
  measurementModel: 'cost' | 'fair_value' = 'cost',
): H32AssetSeed[] {
  const key = measurementModel === 'fair_value' ? H32_FAIR_KEY : H32_COST_KEY
  const raw = getValue(key)
  const rows = _parseJsonRows(raw)
  return rows
    .filter((r) => (r?.assetName || '').trim())
    .map((r) => ({
      rowId: String(r.rowId || ''),
      assetName: String(r.assetName || '').trim(),
      assetType: String(r.assetType || '').trim(),
      area: Number(r.area) || 0,
      category: mapH32AssetTypeToCategory(String(r.assetType || '')),
    }))
}

/** 从 D4-3 行中筛出租金相关项目 */
export function aggregateD43RentalRows(rows: any[]): D43RentalAggregate {
  const items: D43RentalItem[] = []
  for (const row of rows) {
    const item = String(row.item || '').trim()
    if (!isRentalRelatedD43Item(item)) continue
    const { current, prior } = _calcD43Audited(row)
    items.push({
      rowId: String(row.rowId || item),
      item,
      currentAudited: current,
      priorAudited: prior,
    })
  }
  const totalCurrent = items.reduce((s, r) => s + r.currentAudited, 0)
  const totalPrior = items.reduce((s, r) => s + r.priorAudited, 0)
  return {
    totalCurrent,
    totalPrior,
    items,
    loaded: true,
    message: items.length
      ? `D4-3 租金相关 ${items.length} 项，本期审定合计 ${totalCurrent.toFixed(2)}`
      : 'D4-3 中未找到租金/租赁相关项目（请检查项目名称是否含「租金」「租赁」等）',
  }
}

/** 按名称匹配 D4-3 项目与 H3-14 资产行 */
export function matchD43ItemToContract(
  assetName: string,
  items: D43RentalItem[],
): D43RentalItem | undefined {
  const name = _normName(assetName)
  if (!name) return undefined
  return items.find((it) => {
    const item = _normName(it.item)
    return item === name || item.includes(name) || name.includes(item)
  })
}

/** 跨项目拉取 D4-3 行（ACNR 解析 D4 底稿实例） */
export async function fetchD43RowsFromProject(projectId: string): Promise<D43RentalAggregate> {
  if (!projectId) {
    return {
      totalCurrent: 0,
      totalPrior: 0,
      items: [],
      loaded: false,
      message: '无项目上下文，无法加载 D4-3',
    }
  }
  const { resolveInstance } = useAcnr()
  try {
    const inst = await resolveInstance(projectId, 'D4', 'D4-3')
    const wpId = inst?.found ? inst.wp_id : undefined
    if (!wpId) {
      return {
        totalCurrent: 0,
        totalPrior: 0,
        items: [],
        loaded: false,
        message: '未找到 D4-3 底稿实例（请确认项目已生成营业收入底稿）',
      }
    }
    const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(data) ? data : (data?.data ?? data?.items ?? [])
    const hit = list.find((r) => r?.item_id === D43_STORAGE_KEY)
    const rows = _parseJsonRows(hit?.remark)
    return aggregateD43RentalRows(rows)
  } catch {
    return {
      totalCurrent: 0,
      totalPrior: 0,
      items: [],
      loaded: false,
      message: 'D4-3 数据加载失败',
    }
  }
}
