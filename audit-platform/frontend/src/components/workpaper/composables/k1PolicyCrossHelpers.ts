/**
 * K1-6 政策检查 ↔ K1-8 测算 ↔ K2 账龄损失率 跨表辅助
 */
import { parseK18Payload, type K1BadDebtCalcPayloadV2, type K1CalcLineRow } from './useK1BadDebtCalcSheet'
import { K18_STORAGE_KEY } from './k1CrossHelpers'
import { parseNum } from './useD2FormulaEngine'

export const K1_K2_AGING_LOSS_RATE_KEY = 'K1-k2-aging-loss-rates'

export interface K1K2AgingLossRateRow {
  id: string
  agingBucket: string
  historicalRate: number
  adjustedRate: number
  remark: string
}

export const DEFAULT_K2_AGING_BUCKETS = [
  '1年以内', '1-2年', '2-3年', '3-4年', '4-5年', '5年以上',
] as const

export interface K16K18ComboMatch {
  k16Basis: string
  k18GroupName: string
  section: 'credit' | 'aging' | 'single'
}

export interface K16K18ComboConsistency {
  k16Names: string[]
  k18Names: string[]
  matched: K16K18ComboMatch[]
  onlyInK16: string[]
  onlyInK18: string[]
  isConsistent: boolean
  hasK18Data: boolean
}

function newId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

export function normalizeComboName(name: string): string {
  let s = String(name || '').trim()
  // 仅剥离「组合N：名称」中的前缀，保留纯「组合1」作标识
  s = s.replace(/^其他应收款组合\d*[:：]\s*(.+)$/i, '$1')
  s = s.replace(/^组合\d+[:：]\s*(.+)$/i, '$1')
  s = s.replace(/^组合\d+\s+(.+)$/i, '$1')
  return s
    .replace(/[/／、]/g, '')
    .replace(/和|与/g, '')
    .replace(/\s+/g, '')
    .toLowerCase()
}

/** 账龄段匹配：兼容 K1-8「1年以内/未逾期」与 K2「1年以内」 */
export function normalizeAgingBucket(name: string): string {
  const primary = String(name || '').trim().split(/[/／(（]/)[0]
  return normalizeComboName(primary)
}

export function agingBucketsMatch(a: string, b: string): boolean {
  const na = normalizeAgingBucket(a)
  const nb = normalizeAgingBucket(b)
  if (!na || !nb) return false
  if (na === nb) return true
  return na.includes(nb) || nb.includes(na)
}

export function comboNamesMatch(a: string, b: string): boolean {
  const na = normalizeComboName(a)
  const nb = normalizeComboName(b)
  if (!na || !nb) return false
  if (na === nb) return true
  return na.includes(nb) || nb.includes(na)
}

export function seedK2AgingLossRates(): K1K2AgingLossRateRow[] {
  return DEFAULT_K2_AGING_BUCKETS.map((agingBucket) => ({
    id: newId('k2lr'),
    agingBucket,
    historicalRate: 0,
    adjustedRate: 0,
    remark: '',
  }))
}

export function parseK2AgingLossRates(raw: unknown): K1K2AgingLossRateRow[] {
  if (!raw) return seedK2AgingLossRates()
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!Array.isArray(parsed) || parsed.length === 0) return seedK2AgingLossRates()
    return parsed.map((r: any) => ({
      id: String(r.id || newId('k2lr')),
      agingBucket: String(r.agingBucket ?? r.bucket ?? ''),
      historicalRate: parseNum(r.historicalRate),
      adjustedRate: parseNum(r.adjustedRate ?? r.historicalRate),
      remark: String(r.remark ?? ''),
    }))
  } catch {
    return seedK2AgingLossRates()
  }
}

/** 从 K1-8 提取组合/分组名称 */
export function extractK18GroupNames(map: Map<string, any>): Array<{ name: string; section: 'credit' | 'aging' | 'single' }> {
  const raw = map.get(K18_STORAGE_KEY)?.remark ?? map.get(K18_STORAGE_KEY)?.value
  if (!raw) return []
  const payload = parseK18Payload(raw)
  const out: Array<{ name: string; section: 'credit' | 'aging' | 'single' }> = []
  for (const g of payload.creditGroups) {
    const name = String(g.groupName || '').trim()
    if (name) out.push({ name, section: 'credit' })
  }
  for (const g of payload.agingGroups) {
    const name = String(g.groupName || '').trim()
    if (name) out.push({ name, section: 'aging' })
  }
  const hasSingle = payload.singleRows.some((r) => !r.archived && (r.label || r.auditedBalance > 0))
  if (hasSingle) out.push({ name: '单项计提', section: 'single' })
  return out
}

/** K1-6 组合 vs K1-8 分组名称勾稽 */
export function computeK16K18ComboConsistency(
  k16Bases: string[],
  k18Groups: Array<{ name: string; section: 'credit' | 'aging' | 'single' }>,
): K16K18ComboConsistency {
  const k16Names = k16Bases.map((b) => b.trim()).filter(Boolean)
  const k18Names = k18Groups.map((g) => g.name)
  const matched: K16K18ComboMatch[] = []
  const usedK18 = new Set<number>()

  for (const basis of k16Names) {
    const idx = k18Groups.findIndex((g, i) => !usedK18.has(i) && comboNamesMatch(basis, g.name))
    if (idx >= 0) {
      usedK18.add(idx)
      matched.push({ k16Basis: basis, k18GroupName: k18Groups[idx].name, section: k18Groups[idx].section })
    }
  }

  const onlyInK16 = k16Names.filter((b) => !matched.some((m) => m.k16Basis === b))
  const onlyInK18 = k18Names.filter((_, i) => !usedK18.has(i))

  return {
    k16Names,
    k18Names,
    matched,
    onlyInK16,
    onlyInK18,
    isConsistent: k18Names.length === 0 || (onlyInK16.length === 0 && onlyInK18.length === 0),
    hasK18Data: k18Names.length > 0,
  }
}

/** 从 K1-8 分组名称同步至 K1-6（保留已有 basis 的分析字段） */
export function mergeCombosFromK18(
  existing: Array<{ id: string; basis: string; method: string; remark: string }>,
  k18Groups: Array<{ name: string; section: 'credit' | 'aging' | 'single' }>,
): { combos: typeof existing; added: number; updated: number } {
  let added = 0
  let updated = 0
  const combos = existing.map((c) => ({ ...c }))

  for (const g of k18Groups) {
    if (g.section === 'single') continue
    const hit = combos.find((c) => comboNamesMatch(c.basis, g.name))
    if (hit) {
      if (hit.basis !== g.name) {
        hit.basis = g.name
        updated++
      }
    } else {
      combos.push({
        id: newId('combo'),
        basis: g.name,
        method: g.section === 'credit' ? '固定比例' : '账龄分析法',
        remark: '',
      })
      added++
    }
  }

  return { combos, added, updated }
}

function recalcLine(row: K1CalcLineRow): K1CalcLineRow {
  const expected = Math.round(parseNum(row.auditedBalance) * parseNum(row.lossRate) * 100) / 100
  const diff = Math.round((expected - parseNum(row.bookProvision)) * 100) / 100
  return { ...row, expectedProvision: expected, difference: diff }
}

/** 将 K2 账龄损失率推送至 K1-8 账龄组合（按账龄段 label 匹配） */
export function applyK2RatesToK18Payload(
  payload: K1BadDebtCalcPayloadV2,
  k2Rates: K1K2AgingLossRateRow[],
  matches: K16K18ComboMatch[],
): { payload: K1BadDebtCalcPayloadV2; updatedCells: number } {
  const rateByBucket = new Map<string, number>()
  for (const r of k2Rates) {
    const rate = r.adjustedRate > 0 ? r.adjustedRate : r.historicalRate
    if (rate > 0) rateByBucket.set(normalizeAgingBucket(r.agingBucket), rate)
  }

  let updatedCells = 0
  const next = JSON.parse(JSON.stringify(payload)) as K1BadDebtCalcPayloadV2

  for (const m of matches.filter((x) => x.section === 'aging')) {
    const group = next.agingGroups.find((g) => comboNamesMatch(g.groupName, m.k18GroupName))
    if (!group) continue
    for (let i = 0; i < group.rows.length; i++) {
      const row = group.rows[i]
      if (row.archived) continue
      const rate = rateByBucket.get(normalizeAgingBucket(row.label))
      if (rate != null && rate > 0 && Math.abs(row.lossRate - rate) >= 0.0001) {
        group.rows[i] = recalcLine({ ...row, lossRate: rate })
        updatedCells++
      }
    }
  }

  return { payload: next, updatedCells }
}

/** 从 K1-8 账龄组合回填 K2 损失率（历史=当前 K1-8 损失率） */
export function pullK2RatesFromK18(
  map: Map<string, any>,
  matches: K16K18ComboMatch[],
): K1K2AgingLossRateRow[] {
  const raw = map.get(K18_STORAGE_KEY)?.remark
  if (!raw) return seedK2AgingLossRates()
  const payload = parseK18Payload(raw)
  const buckets = seedK2AgingLossRates()
  const bucketMap = new Map(buckets.map((b) => [normalizeAgingBucket(b.agingBucket), { ...b }]))

  for (const m of matches.filter((x) => x.section === 'aging')) {
    const group = payload.agingGroups.find((g) => comboNamesMatch(g.groupName, m.k18GroupName))
    if (!group) continue
    for (const row of group.rows) {
      if (row.archived || row.lossRate <= 0) continue
      const key = normalizeAgingBucket(row.label)
      const existing = bucketMap.get(key)
      if (existing) {
        existing.historicalRate = row.lossRate
        if (existing.adjustedRate <= 0) existing.adjustedRate = row.lossRate
        existing.remark = `取自 K1-8「${group.groupName}」`
      } else {
        bucketMap.set(key, {
          id: newId('k2lr'),
          agingBucket: row.label,
          historicalRate: row.lossRate,
          adjustedRate: row.lossRate,
          remark: `取自 K1-8「${group.groupName}」`,
        })
      }
    }
  }

  return Array.from(bucketMap.values())
}
