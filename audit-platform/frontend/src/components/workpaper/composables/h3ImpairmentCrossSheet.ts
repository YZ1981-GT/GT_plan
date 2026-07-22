/**
 * H3-10 减值跨表联动纯函数
 * - H3-2 明细 → ②账面价值 / ⑦已计提
 * - H3-9 盘点 → 减值关注线索
 * - K11 资产减值损失勾稽
 */

export const H3_10_CATEGORY_BUILDING = '房屋、建筑物'
export const H3_10_CATEGORY_LAND = '土地使用权'
export const H3_10_CATEGORY_CIP = '在建工程'

export const ITEM_H32_COST_ROWS = 'H3-2-cost-rows'
export const ITEM_H39_STOCKTAKE_ROWS = 'H3-9-stocktake-rows'
export const ITEM_H310_STOCKTAKE_CONCERNS = 'H3-10-stocktake-concerns'
export const ITEM_H310_SUPPLEMENT_TOTAL = 'H3-10-supplement-total'

/** K11-2 投资性房地产类别键（与 useK11CrossSheet / GtK11AssetImpairmentLoss 一致） */
export const K11_IP_CATEGORY_KEY = 'investment-property'

/** H3 ↔ K11 勾稽用 item_id（优先级与 H1-14 reconcileWithK11 对齐） */
export const K11_H3_ITEM_IDS = {
  /** K11-2 明细表本期发生额（首选） */
  occurrence: `K11-2-${K11_IP_CATEGORY_KEY}-occurrence`,
  /** CrossSheet 源底稿金额（EventBus / H3-10 回写） */
  sourceAmount: `K11-2-${K11_IP_CATEGORY_KEY}-source-amount`,
  /** 通用源底稿键（impairment:calculated 写入） */
  sourceWpAmount: 'K11-source-H3-amount',
  /** K11-2 明细 JSON 行（兜底解析 H3 行） */
  detailRows: 'K11-2-detail-rows',
} as const

export const K11_H3_AMOUNT_CANDIDATES: ReadonlyArray<{ id: string; label: string }> = [
  { id: K11_H3_ITEM_IDS.occurrence, label: K11_H3_ITEM_IDS.occurrence },
  { id: K11_H3_ITEM_IDS.sourceAmount, label: K11_H3_ITEM_IDS.sourceAmount },
  { id: K11_H3_ITEM_IDS.sourceWpAmount, label: K11_H3_ITEM_IDS.sourceWpAmount },
  { id: K11_H3_ITEM_IDS.detailRows, label: 'K11-2 明细(投资性房地产行)' },
]

export interface H32DetailSeed {
  rowId: string
  assetName: string
  assetType: string
  category: string
  /** ② 账面（原值−累计折旧，未扣减值） */
  bookValue: number
  /** ⑦ 已计提减值准备期末 */
  alreadyProvided: number
}

export interface StocktakeImpairmentConcern {
  source: 'H3-9'
  assetName: string
  reason: string
  bookValue: number
  suggest: 'impairment'
  checkRowId: string
}

export interface K11ReconcileResult {
  h10Supplement: number
  k11Amount: number | null
  diff: number | null
  isMatch: boolean
  source: string
  message: string
}

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

export function mapH32TypeToH310Category(assetType: string): string {
  const t = (assetType || '').trim()
  if (/在建|工程/.test(t)) return H3_10_CATEGORY_CIP
  if (/土地|使用权/.test(t)) return H3_10_CATEGORY_LAND
  return H3_10_CATEGORY_BUILDING
}

/** ② 账面：原值−累计折旧（未扣减值） */
export function bookValueFromH32Row(raw: any): number {
  const cost = Number(raw.costEnd) || Number(raw.originalCost) || 0
  const dep = Number(raw.accDepEnd) || 0
  const gross = cost - dep
  if (gross > 0) return gross
  const net = Number(raw.netValue) || 0
  const imp = Number(raw.impairmentEnd) || 0
  return net + imp
}

export function alreadyProvidedFromH32Row(raw: any): number {
  return Number(raw.impairmentEnd) || 0
}

export function parseH32CostDetailRows(getValue: (id: string) => unknown): H32DetailSeed[] {
  const rows = _parseJsonRows(getValue(ITEM_H32_COST_ROWS))
  return rows
    .filter((r) => (r?.assetName || '').trim())
    .map((r) => ({
      rowId: String(r.rowId || ''),
      assetName: String(r.assetName || '').trim(),
      assetType: String(r.assetType || '').trim(),
      category: mapH32TypeToH310Category(String(r.assetType || '')),
      bookValue: bookValueFromH32Row(r),
      alreadyProvided: alreadyProvidedFromH32Row(r),
    }))
}

/** 从 H3-9 盘点行收集应推送至 H3-10 的减值关注 */
export function collectStocktakeImpairmentConcerns(
  rows: {
    rowId: string
    assetName: string
    leaseStatus?: string
    qualityStatus?: string
    physicalStatus?: string
    result?: string
    conclusion?: string
    bookValue?: number
    bookAmount?: number
    remark?: string
    diffReason?: string
  }[],
): StocktakeImpairmentConcern[] {
  const out: StocktakeImpairmentConcern[] = []
  for (const r of rows) {
    const vacant = r.leaseStatus === '空置'
    const idle = r.qualityStatus === '闲置'
    const damaged = r.qualityStatus === '毁损' || r.qualityStatus === '待处置'
    const deficit = r.result === '盘亏'
    const mismatch = r.conclusion === '不符' || (r.result && r.result !== '账实相符' && r.result !== '盘盈')
    const phys = (r.physicalStatus || '').trim()
    const physBad = /毁损|损坏|报废|陈旧|坍塌|渗漏/.test(phys)
    if (!vacant && !idle && !damaged && !deficit && !mismatch && !physBad) continue
    const parts = [
      vacant ? '空置' : '',
      idle ? '闲置' : '',
      damaged ? (r.qualityStatus || '') : '',
      deficit ? '盘亏' : '',
      mismatch && r.result ? r.result : '',
      physBad ? phys : '',
      r.diffReason || '',
      r.remark || '',
    ].filter(Boolean)
    const book = Number(r.bookValue) || Number(r.bookAmount) || 0
    out.push({
      source: 'H3-9',
      assetName: r.assetName || '未命名',
      reason: parts.join(' / ') || '盘点异常',
      bookValue: book,
      suggest: 'impairment',
      checkRowId: r.rowId,
    })
  }
  return out
}

export function parseStocktakeConcernPayload(raw: unknown): StocktakeImpairmentConcern[] {
  if (!raw || typeof raw !== 'object') return []
  const items = (raw as any).items
  return Array.isArray(items) ? items : []
}

/** 从 K11 checklist 响应中解析投资性房地产减值本期发生额 */
export function extractK11InvestmentPropertyAmount(list: any[]): { amount: number | null; source: string } {
  const byId = (id: string) => {
    const item = list.find((r) => r.item_id === id)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (raw == null || raw === '') return null
    if (typeof raw === 'string' && raw.trim().startsWith('[')) {
      try {
        const rows = JSON.parse(raw)
        if (!Array.isArray(rows)) return null
        const ip = rows.filter((r: any) => {
          const cat = String(r.assetCategory || r.impairmentItem || r.projectName || '')
          const wp = String(r.sourceWp || '')
          return wp === 'H3' || cat.includes('投资性房地产')
        })
        if (!ip.length) return null
        return ip.reduce(
          (s: number, r: any) => s + (Number(r.currentOccurrence ?? r.currentProvision ?? r.sourceAmount) || 0),
          0,
        )
      } catch {
        return null
      }
    }
    if (typeof raw === 'object' && raw !== null && Array.isArray((raw as any).items)) {
      const ip = (raw as any).items.filter((r: any) => {
        const cat = String(r.assetCategory || r.impairmentItem || '')
        return String(r.sourceWp || '') === 'H3' || cat.includes('投资性房地产')
      })
      if (!ip.length) return null
      return ip.reduce((s: number, r: any) => s + (Number(r.currentOccurrence ?? r.sourceAmount) || 0), 0)
    }
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  }

  const candidates = K11_H3_AMOUNT_CANDIDATES
  for (const c of candidates) {
    const v = byId(c.id)
    if (v != null) return { amount: v, source: c.label }
  }
  return { amount: null, source: '' }
}
