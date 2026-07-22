/**
 * 从 G1/G8/G9/G10/H3 源科目明细带入 G13-2 成本/累计FV/计入损益
 */
import { api } from '@/services/apiProxy'
import { parseNum } from './useG13FormulaEngine'
import { G13_SOURCE_INDEX_BY_BELONG } from './g13Constants'

export type G13SourceBelong = 'G1' | 'G8' | 'G9' | 'G10' | 'H3'

export interface G13SourcePullSeed {
  instrumentName: string
  belongAccount: G13SourceBelong
  instrumentType: string
  openingFairValue: number
  closingFairValue: number
  currentUnadjusted: number
  cost: number
  periodFvChange: number
  cumulativeFvChange: number
  fairValue: number
  amountInPl: number
  sourceIndex: string
  remark: string
}

/** 合并目标行最小字段（避免与 useG13Detail 循环依赖） */
export interface G13MergeTargetRow {
  rowId: string
  seq: number
  instrumentName: string
  belongAccount: string
  instrumentType: string
  openingFairValue: number
  closingFairValue: number
  currentUnadjusted: number
  adjustment: number
  cost: number
  periodFvChange: number
  cumulativeFvChange: number
  fairValue: number
  amountInPl: number
  sourceIndex: string
  crossVerification: string
  remark: string
  [key: string]: unknown
}

interface SourceSpec {
  wpCode: string
  itemId: string
  /** checklist 存 conclusion 还是 remark（G1 用 conclusion） */
  storage: 'conclusion' | 'remark' | 'either'
  map: (raw: Record<string, unknown>) => G13SourcePullSeed | null
}

function pickJson(item: { conclusion?: string | null; remark?: string | null } | undefined, storage: SourceSpec['storage']): unknown[] {
  if (!item) return []
  const tryParse = (s: string | null | undefined) => {
    if (!s) return null
    try {
      const p = JSON.parse(s)
      return Array.isArray(p) ? p : null
    } catch {
      return null
    }
  }
  if (storage === 'conclusion') return tryParse(item.conclusion) ?? []
  if (storage === 'remark') return tryParse(item.remark) ?? []
  return tryParse(item.remark) ?? tryParse(item.conclusion) ?? []
}

function mapG1(raw: Record<string, unknown>): G13SourcePullSeed | null {
  const name = String(raw.securityName ?? raw.instrumentName ?? '').trim()
  if (!name) return null
  const acctClass = String(raw.acctClass ?? '')
  const investType = String(raw.investType ?? '')
  const typeLabel =
    acctClass === 'designated_fvpl' ? '指定FVTPL'
      : investType === 'stock' ? '股票'
        : investType === 'bond' ? '债券'
          : investType === 'fund' ? '基金'
            : investType === 'derivative' ? '衍生工具'
              : '其他'
  const cost = parseNum(raw.auditedClosingCost ?? raw.closingCost ?? raw.initialCost ?? raw.openingCost)
  const periodFv = parseNum(raw.periodFvChange ?? raw.fairValueChange ?? raw.fvChangeInPL)
  const cumFv = parseNum(raw.auditedClosingCumulativeFv ?? raw.cumulativeFVChange ?? raw.closingCumulativeFv)
  const fairValue = parseNum(raw.auditedClosingFvTotal ?? raw.closingFairValue ?? raw.closingReported)
  const amountInPl = parseNum(raw.fvChangeInPL) || periodFv
  const opening = parseNum(raw.auditedOpeningFvTotal ?? raw.openingFairValue)
  return {
    instrumentName: name,
    belongAccount: 'G1',
    instrumentType: typeLabel,
    openingFairValue: opening,
    closingFairValue: fairValue || opening + periodFv,
    currentUnadjusted: amountInPl,
    cost,
    periodFvChange: periodFv,
    cumulativeFvChange: cumFv,
    fairValue: fairValue || cost + cumFv,
    amountInPl,
    sourceIndex: G13_SOURCE_INDEX_BY_BELONG.G1,
    remark: acctClass === 'designated_fvpl' ? '自 G1-2 带入（指定FVTPL）' : '自 G1-2 带入',
  }
}

function mapG8(raw: Record<string, unknown>): G13SourcePullSeed | null {
  const name = String(raw.investeeName ?? '').trim()
  if (!name) return null
  const periodFv = parseNum(raw.fvChangeAmount)
  const fairValue = parseNum(raw.fairValueTotal ?? raw.closingAdjusted ?? raw.closingBalance)
  const opening = parseNum(raw.openingAdjusted ?? raw.openingBalance)
  const cost = opening // G8 无单独成本列时以期初账面为成本近似
  const cumFv = fairValue - cost
  const designated = /指定/.test(String(raw.designationReason ?? ''))
  return {
    instrumentName: name,
    belongAccount: 'G8',
    instrumentType: designated ? '指定FVTPL' : '其他',
    openingFairValue: opening,
    closingFairValue: fairValue,
    currentUnadjusted: periodFv,
    cost,
    periodFvChange: periodFv,
    cumulativeFvChange: cumFv,
    fairValue,
    amountInPl: periodFv,
    sourceIndex: G13_SOURCE_INDEX_BY_BELONG.G8,
    remark: designated ? '自 G8-2 带入（指定）' : '自 G8-2 带入',
  }
}

function mapG9(raw: Record<string, unknown>): G13SourcePullSeed | null {
  const name = String(raw.assetName ?? '').trim()
  if (!name) return null
  const periodFv = parseNum(raw.fvChangeAmount)
  const fairValue = parseNum(raw.closingAdjusted ?? raw.closingBalance)
  const opening = parseNum(raw.openingAdjusted ?? raw.openingBalance)
  const cost = parseNum(raw.faceValueOrCost) || opening
  const cumFv = fairValue - cost
  const isDesignated = !!raw.isDesignated
  const instrumentType = String(raw.instrumentType || '').includes('衍生')
    ? (String(raw.classification || '').includes('负债') ? '衍生工具负债' : '衍生工具')
    : (isDesignated ? '指定FVTPL' : String(raw.instrumentType || '其他'))
  const belong: 'G9' = 'G9'
  return {
    instrumentName: name,
    belongAccount: belong,
    instrumentType,
    openingFairValue: opening,
    closingFairValue: fairValue,
    currentUnadjusted: periodFv,
    cost,
    periodFvChange: periodFv,
    cumulativeFvChange: cumFv,
    fairValue,
    amountInPl: periodFv,
    sourceIndex: G13_SOURCE_INDEX_BY_BELONG.G9,
    remark: isDesignated ? '自 G9-2 带入（指定）' : '自 G9-2 带入',
  }
}

function mapG10(raw: Record<string, unknown>): G13SourcePullSeed | null {
  const name = String(raw.liabilityName ?? '').trim()
  if (!name) return null
  const cost = parseNum(raw.closingInitialAmount ?? raw.openingInitialAmount)
  const cumFv = parseNum(raw.closingFvAccum)
  const periodFv = parseNum(raw.movementFvChange)
  const fairValue = parseNum(raw.closingFairValue ?? raw.closingAdjusted)
  const opening = parseNum(raw.openingFairValue ?? raw.openingAdjusted)
  const cat = String(raw.liabilityCategory ?? '')
  const typ = String(raw.liabilityType ?? '')
  const designated = /指定/.test(cat)
  const derivative = /衍生/.test(typ) || /衍生/.test(cat)
  const instrumentType = designated ? '指定FVTPL' : derivative ? '衍生工具负债' : (typ || '其他')
  return {
    instrumentName: name,
    belongAccount: 'G10',
    instrumentType,
    openingFairValue: opening,
    closingFairValue: fairValue,
    currentUnadjusted: periodFv,
    cost,
    periodFvChange: periodFv,
    cumulativeFvChange: cumFv,
    fairValue: fairValue || cost + cumFv,
    amountInPl: periodFv,
    sourceIndex: G13_SOURCE_INDEX_BY_BELONG.G10,
    remark: designated ? '自 G10-2 带入（指定）' : '自 G10-2 带入',
  }
}

function mapH3(raw: Record<string, unknown>): G13SourcePullSeed | null {
  const name = String(raw.assetName ?? '').trim()
  if (!name) return null
  const opening = parseNum(raw.fairValueBegin)
  const periodFv = parseNum(raw.fairValueChange)
  const fairValue = parseNum(raw.fairValueEnd) || opening + periodFv
  return {
    instrumentName: name,
    belongAccount: 'H3',
    instrumentType: '投资性房地产',
    openingFairValue: opening,
    closingFairValue: fairValue,
    currentUnadjusted: periodFv,
    cost: opening, // 公允模式以期初公允为成本锚点
    periodFvChange: periodFv,
    cumulativeFvChange: fairValue - opening,
    fairValue,
    amountInPl: periodFv,
    sourceIndex: G13_SOURCE_INDEX_BY_BELONG.H3,
    remark: '自 H3-2 公允明细带入',
  }
}

export const G13_SOURCE_PULL_SPECS: SourceSpec[] = [
  { wpCode: 'G1', itemId: 'G1-2-rows', storage: 'conclusion', map: mapG1 },
  { wpCode: 'G8', itemId: 'G8-detail-rows', storage: 'remark', map: mapG8 },
  { wpCode: 'G9', itemId: 'G9-detail-rows', storage: 'remark', map: mapG9 },
  { wpCode: 'G10', itemId: 'G10-detail-rows', storage: 'remark', map: mapG10 },
  { wpCode: 'H3', itemId: 'H3-2-fair-rows', storage: 'either', map: mapH3 },
]

async function resolveWpId(projectId: string, wpCode: string): Promise<string | null> {
  try {
    const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: wpCode },
      _silent: true,
    } as any)
    return (idRes as any)?.wp_id ?? (idRes as any)?.data?.wp_id ?? null
  } catch {
    return null
  }
}

async function loadChecklistItem(
  wpId: string,
  itemId: string,
): Promise<{ conclusion?: string | null; remark?: string | null } | null> {
  try {
    const res = await api.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    return list.find((r) => r.item_id === itemId) ?? null
  } catch {
    return null
  }
}

/** 拉取同项目源科目明细并映射为 G13-2 种子行 */
export async function fetchG13SourcePullSeeds(projectId: string): Promise<{
  seeds: G13SourcePullSeed[]
  bySource: Record<string, number>
  missing: string[]
}> {
  const seeds: G13SourcePullSeed[] = []
  const bySource: Record<string, number> = {}
  const missing: string[] = []

  for (const spec of G13_SOURCE_PULL_SPECS) {
    const wpId = await resolveWpId(projectId, spec.wpCode)
    if (!wpId) {
      missing.push(spec.wpCode)
      continue
    }
    const item = await loadChecklistItem(wpId, spec.itemId)
    const rows = pickJson(item ?? undefined, spec.storage)
    let n = 0
    for (const raw of rows) {
      if (!raw || typeof raw !== 'object') continue
      const seed = spec.map(raw as Record<string, unknown>)
      if (!seed) continue
      seeds.push(seed)
      n += 1
    }
    bySource[spec.wpCode] = n
  }

  return { seeds, bySource, missing }
}

function matchKey(name: string, belong: string): string {
  return `${belong}::${name.trim().toLowerCase()}`
}

export interface MergeG13SourceResult<T extends G13MergeTargetRow = G13MergeTargetRow> {
  rows: T[]
  added: number
  updated: number
  /** 本次带入触及的行（用于自动交叉验证统计） */
  touchedRowIds: string[]
}

/** 按 所属科目+名称 合并；空字段才用源数填充，避免覆盖已审定手工数 */
export function mergeG13SourceSeeds<T extends G13MergeTargetRow>(
  existing: T[],
  seeds: G13SourcePullSeed[],
  enrich: (raw: Partial<T> & { rowId: string }) => T,
  genId: () => string,
  opts?: { markCrossVerification?: boolean },
): MergeG13SourceResult<T> {
  const markCross = opts?.markCrossVerification !== false
  const next = existing.map((r) => ({ ...r })) as T[]
  const index = new Map<string, number>()
  next.forEach((r, i) => index.set(matchKey(r.instrumentName, r.belongAccount), i))
  const touched = new Set<string>()

  let added = 0
  let updated = 0

  for (const s of seeds) {
    const key = matchKey(s.instrumentName, s.belongAccount)
    const idx = index.get(key)
    if (idx == null) {
      const seq = next.length + 1
      let row = enrich({
        rowId: genId(),
        seq,
        instrumentName: s.instrumentName,
        belongAccount: s.belongAccount,
        instrumentType: s.instrumentType,
        openingFairValue: s.openingFairValue,
        closingFairValue: s.closingFairValue,
        currentUnadjusted: s.currentUnadjusted,
        adjustment: 0,
        cost: s.cost,
        periodFvChange: s.periodFvChange,
        cumulativeFvChange: s.cumulativeFvChange,
        fairValue: s.fairValue,
        amountInPl: s.amountInPl,
        sourceIndex: s.sourceIndex,
        crossVerification: 'pending',
        remark: s.remark,
      } as Partial<T> & { rowId: string })
      if (markCross) {
        const ok = (row as any).allReconciled !== false
        row = enrich({
          ...row,
          rowId: row.rowId,
          crossVerification: ok ? 'consistent' : 'inconsistent',
        } as Partial<T> & { rowId: string })
      }
      next.push(row)
      index.set(key, next.length - 1)
      touched.add(row.rowId)
      added += 1
      continue
    }

    const prev = next[idx]
    const patch: Partial<T> = {}
    const fillIfEmpty = (field: keyof G13MergeTargetRow, value: number | string) => {
      const cur = prev[field]
      if (typeof value === 'number') {
        if (parseNum(cur as number) === 0 && value !== 0) (patch as any)[field] = value
      } else if (!String(cur ?? '').trim() && value) {
        (patch as any)[field] = value
      }
    }
    fillIfEmpty('instrumentType', s.instrumentType)
    fillIfEmpty('openingFairValue', s.openingFairValue)
    fillIfEmpty('closingFairValue', s.closingFairValue)
    fillIfEmpty('currentUnadjusted', s.currentUnadjusted)
    fillIfEmpty('cost', s.cost)
    fillIfEmpty('periodFvChange', s.periodFvChange)
    fillIfEmpty('cumulativeFvChange', s.cumulativeFvChange)
    fillIfEmpty('fairValue', s.fairValue)
    fillIfEmpty('amountInPl', s.amountInPl)
    fillIfEmpty('sourceIndex', s.sourceIndex)
    if (!prev.remark?.includes('带入') && s.remark) {
      ;(patch as any).remark = prev.remark ? `${prev.remark}；${s.remark}` : s.remark
    }
    if (Object.keys(patch).length || markCross) {
      const merged = enrich({ ...prev, ...patch, rowId: prev.rowId })
      // 带入触及行：勾稽通过→一致；不通过→不一致；否则保持
      if (markCross) {
        const ok = (merged as any).allReconciled !== false
          && Math.abs(parseNum((merged as any).amountInPl) - parseNum((merged as any).currentAudited)) <= 0.01
        ;(merged as any).crossVerification = ok ? 'consistent' : 'inconsistent'
      }
      next[idx] = merged
      touched.add(prev.rowId)
      if (Object.keys(patch).length) updated += 1
    }
  }

  return {
    rows: next.map((r, i) => enrich({ ...r, rowId: r.rowId, seq: i + 1 })),
    added,
    updated,
    touchedRowIds: [...touched],
  }
}
