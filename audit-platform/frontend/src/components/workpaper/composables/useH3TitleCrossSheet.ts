/**
 * useH3TitleCrossSheet — H3-12 产权核对跨底稿联动
 * H3-2 / H3-9 / L1-8 / 附注受限 / 完整性勾稽 / 反向同步 / 抽样
 */
import http from '@/utils/http'
import { useAcnr } from '@/services/acnr/useAcnr'
import { extractH32Assets } from './useH3RentalCrossSheet'
import type { TitleRow } from './h3TitleRowModel'
import {
  addSourceTag,
  buildRestrictionDisclosureText,
  isAreaAnomaly,
  nameSimilarity,
  normalizeTitleRow,
  normName,
  recomputeTitleRow,
  suggestMatchConsistent,
} from './h3TitleRowModel'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H32TitleSeed {
  rowId: string
  assetName: string
  assetCode: string
  location: string
  bookArea: number
  bookValue: number
  certName: string
  certPurpose: string
}

export interface H39TitleSeed {
  rowId: string
  assetName: string
  location: string
  titleCertNo: string
  bookArea: number
  bookValue: number
  actualPurpose: string
}

export interface L1PledgeSeed {
  assetName: string
  bookValue: number
  guaranteedLoan: number
  ownershipVerified: string
}

export interface TitleImportResult {
  added: number
  updated: number
  skipped: number
  message: string
}

export interface CompletenessCheck {
  code: string
  label: string
  status: 'ok' | 'warn' | 'error' | 'info'
  detail: string
}

export interface SamplePlan {
  sampledCount: number
  coveragePct: number
  totalValue: number
  sampledValue: number
  message: string
}

const H39_KEY = 'H3-9-stocktake-rows'
const H32_COST_KEY = 'H3-2-cost-rows'
const H32_FAIR_KEY = 'H3-2-fair-rows'
const DISC_LISTED_KEY = 'H3-disc-listed-text-restriction'
const DISC_SOE_KEY = 'H3-disc-soe-text-soe-restriction'

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

function _isBlankStr(v: unknown): boolean {
  return !String(v ?? '').trim()
}

function _isZeroNum(v: unknown): boolean {
  return !(Number(v) > 0)
}

function _recomputeTitleRow(row: TitleRow): void {
  recomputeTitleRow(row)
  if (!row.matchConsistent || row.matchConsistent === '是' || row.matchConsistent === '否') {
    row.matchConsistent = suggestMatchConsistent(row)
  }
}

export function mapAssetTypeToCertName(assetType: string): string {
  const t = (assetType || '').trim()
  if (/土地|使用权/.test(t)) return '土地使用权证'
  if (/房屋|建筑|写字楼|商铺|厂房/.test(t)) return '不动产权证书'
  return t ? `${t}权属证明` : '不动产权证书'
}

export function mapAssetTypeToPurpose(assetType: string): string {
  const t = (assetType || '').trim()
  if (/土地/.test(t)) return '投资性房地产-土地'
  if (/房屋|建筑/.test(t)) return '投资性房地产-出租'
  return '投资性房地产'
}

function _costBookValue(row: any): number {
  const end = Number(row.costEnd) || 0
  const original = Number(row.originalCost) || 0
  return end > 0 ? end : original
}

/** 按名称模糊匹配，可选坐落+面积辅助 */
export function findBestTitleMatch(
  titleRows: TitleRow[],
  candidate: { assetName: string; location?: string; bookArea?: number },
): TitleRow | undefined {
  let best: TitleRow | undefined
  let bestScore = 0
  for (const row of titleRows) {
    let score = nameSimilarity(row.assetName, candidate.assetName)
    if (score <= 0 && candidate.location && row.location) {
      const locSim = nameSimilarity(row.location, candidate.location)
      if (locSim >= 0.8 && candidate.bookArea && row.bookArea) {
        const areaDiff = Math.abs(row.bookArea - candidate.bookArea)
        if (areaDiff <= Math.max(1, row.bookArea * 0.02)) score = 0.6
      }
    }
    if (score > bestScore) {
      bestScore = score
      best = row
    }
  }
  return bestScore >= 0.6 ? best : undefined
}

export function extractH32TitleSeeds(
  getValue: (id: string) => unknown,
  measurementModel: 'cost' | 'fair_value' = 'cost',
): H32TitleSeed[] {
  const key = measurementModel === 'fair_value' ? H32_FAIR_KEY : H32_COST_KEY
  const rows = _parseJsonRows(getValue(key))
  return rows
    .filter((r) => (r?.assetName || '').trim())
    .map((r) => {
      const assetType = String(r.assetType || '').trim()
      const rowId = String(r.rowId || '')
      return {
        rowId,
        assetName: String(r.assetName || '').trim(),
        assetCode: rowId.replace(/^(dc|df)-/, '').slice(0, 12) || '',
        location: String(r.location || '').trim(),
        bookArea: Number(r.area) || 0,
        bookValue: measurementModel === 'fair_value'
          ? (Number(r.fairValueEnd) || Number(r.fairValueBegin) || 0)
          : _costBookValue(r),
        certName: mapAssetTypeToCertName(assetType),
        certPurpose: mapAssetTypeToPurpose(assetType),
      }
    })
}

export function extractH39TitleSeeds(getValue: (id: string) => unknown): H39TitleSeed[] {
  const rows = _parseJsonRows(getValue(H39_KEY))
  return rows
    .filter((r) => (r?.assetName || '').trim())
    .map((r) => ({
      rowId: String(r.rowId || ''),
      assetName: String(r.assetName || '').trim(),
      location: String(r.location || '').trim(),
      titleCertNo: String(r.titleCertNo || '').trim(),
      bookArea: Number(r.area) || 0,
      bookValue: Number(r.bookValue) || 0,
      actualPurpose: String(r.purpose || '').trim(),
    }))
}

/** 解析 L1-plg-{n}-{field} 动态行 */
export function parseL1PledgeRowsFromMap(items: Array<{ item_id?: string; remark?: string | null; conclusion?: string | null }>): L1PledgeSeed[] {
  const pattern = /^L1-plg-(\d+)-(\w+)$/
  const rows: L1PledgeSeed[] = []
  for (const item of items) {
    const match = String(item.item_id || '').match(pattern)
    if (!match) continue
    const idx = parseInt(match[1], 10)
    const field = match[2]
    while (rows.length < idx) {
      rows.push({ assetName: '', bookValue: 0, guaranteedLoan: 0, ownershipVerified: '' })
    }
    const row = rows[idx - 1]
    const val = item.remark || item.conclusion || ''
    if (field === 'assetName' || field === 'ownershipVerified') {
      ;(row as any)[field] = val
    } else if (field === 'bookValue' || field === 'guaranteedLoan' || field === 'pledgeRatio') {
      const n = parseFloat(String(val))
      if (field !== 'pledgeRatio') (row as any)[field] = isNaN(n) ? 0 : n
    }
  }
  return rows.filter((r) => (r.assetName || '').trim())
}

export async function fetchL1PledgeSeeds(projectId: string): Promise<{ seeds: L1PledgeSeed[]; message: string }> {
  if (!projectId) return { seeds: [], message: '无项目上下文，无法加载 L1' }
  const { resolveInstance } = useAcnr()
  try {
    const inst = await resolveInstance(projectId, 'L1', 'L1-8')
    const wpId = inst?.found ? inst.wp_id : undefined
    if (!wpId) {
      // 回退：尝试 L1 主底稿
      const inst2 = await resolveInstance(projectId, 'L1', 'L1')
      const wpId2 = inst2?.found ? inst2.wp_id : undefined
      if (!wpId2) return { seeds: [], message: '未找到 L1/L1-8 底稿实例' }
      const { data } = await http.get(`/api/workpapers/${wpId2}/checklist-responses`, { _silent: true } as any)
      const list: any[] = Array.isArray(data) ? data : (data?.data ?? data?.items ?? [])
      const seeds = parseL1PledgeRowsFromMap(list)
      return {
        seeds,
        message: seeds.length ? `已从 L1 加载 ${seeds.length} 项抵质押资产` : 'L1 中暂无抵质押检查行',
      }
    }
    const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(data) ? data : (data?.data ?? data?.items ?? [])
    const seeds = parseL1PledgeRowsFromMap(list)
    return {
      seeds,
      message: seeds.length ? `已从 L1-8 加载 ${seeds.length} 项抵质押资产` : 'L1-8 中暂无抵质押检查行',
    }
  } catch {
    return { seeds: [], message: 'L1 抵质押数据加载失败' }
  }
}

function _applyH32Seed(row: TitleRow, seed: H32TitleSeed, overwrite: boolean): number {
  let changed = 0
  const setStr = (field: keyof TitleRow, value: string) => {
    if (!value) return
    if (overwrite || _isBlankStr((row as any)[field])) {
      if ((row as any)[field] !== value) changed++
      ;(row as any)[field] = value
    }
  }
  const setNum = (field: keyof TitleRow, value: number) => {
    if (!(value > 0)) return
    if (overwrite || _isZeroNum((row as any)[field])) {
      if ((row as any)[field] !== value) changed++
      ;(row as any)[field] = value
    }
  }
  setStr('assetName', seed.assetName)
  setStr('assetCode', seed.assetCode)
  setStr('location', seed.location)
  setNum('bookArea', seed.bookArea)
  setNum('bookValue', seed.bookValue)
  setStr('certName', seed.certName)
  setStr('certPurpose', seed.certPurpose)
  if (_isBlankStr(row.actualPurpose)) setStr('actualPurpose', seed.certPurpose)
  if (changed) {
    addSourceTag(row, 'H3-2')
    _recomputeTitleRow(row)
  }
  return changed > 0 ? 1 : 0
}

function _applyH39Seed(row: TitleRow, seed: H39TitleSeed, overwrite: boolean): number {
  let changed = 0
  const setStr = (field: keyof TitleRow, value: string) => {
    if (!value) return
    if (overwrite || _isBlankStr((row as any)[field])) {
      if ((row as any)[field] !== value) changed++
      ;(row as any)[field] = value
    }
  }
  const setNum = (field: keyof TitleRow, value: number) => {
    if (!(value > 0)) return
    if (overwrite || _isZeroNum((row as any)[field])) {
      if ((row as any)[field] !== value) changed++
      ;(row as any)[field] = value
    }
  }
  setStr('assetName', seed.assetName)
  setStr('location', seed.location)
  setStr('titleCertNo', seed.titleCertNo)
  setNum('bookArea', seed.bookArea)
  setNum('bookValue', seed.bookValue)
  setStr('actualPurpose', seed.actualPurpose)
  if (seed.titleCertNo && _isBlankStr(row.certStatus)) {
    row.certStatus = '已办证'
    changed++
  }
  if (changed) {
    addSourceTag(row, 'H3-9')
    _recomputeTitleRow(row)
  }
  return changed > 0 ? 1 : 0
}

export function importTitleRowsFromH32(
  titleRows: TitleRow[],
  seeds: H32TitleSeed[],
  mode: 'addNew' | 'fillEmpty' = 'addNew',
  overwrite = false,
): TitleImportResult {
  if (!seeds.length) {
    return { added: 0, updated: 0, skipped: 0, message: 'H3-2 明细暂无资产，请先编制 H3-2' }
  }
  const existingNames = new Set(titleRows.map((r) => normName(r.assetName)).filter(Boolean))
  let added = 0
  let updated = 0
  let skipped = 0

  if (mode === 'addNew') {
    for (const seed of seeds) {
      const key = normName(seed.assetName)
      if (!key || existingNames.has(key) || findBestTitleMatch(titleRows, seed)) {
        skipped++
        continue
      }
      const row = normalizeTitleRow({
        rowId: `tt-h32-${seed.rowId || Date.now()}`,
        seq: titleRows.length + 1,
        assetName: seed.assetName,
        assetCode: seed.assetCode,
        location: seed.location,
        bookArea: seed.bookArea,
        bookValue: seed.bookValue,
        certName: seed.certName,
        certPurpose: seed.certPurpose,
        actualPurpose: seed.certPurpose,
        sourceTags: 'H3-2',
      })
      titleRows.push(row)
      existingNames.add(key)
      added++
    }
    return {
      added, updated, skipped,
      message: added ? `已从 H3-2 新增 ${added} 行产权核对记录` : 'H3-2 资产均已存在于本表，未新增',
    }
  }

  for (const seed of seeds) {
    const row = findBestTitleMatch(titleRows, seed)
    if (!row) { skipped++; continue }
    if (_applyH32Seed(row, seed, overwrite)) updated++
    else skipped++
  }
  return {
    added: 0, updated, skipped,
    message: updated ? `已从 H3-2 ${overwrite ? '覆盖同步' : '补全'} ${updated} 行账面信息` : '无需从 H3-2 补全',
  }
}

export function importTitleRowsFromH39(
  titleRows: TitleRow[],
  seeds: H39TitleSeed[],
  mode: 'addNew' | 'fillEmpty' = 'fillEmpty',
  overwrite = false,
): TitleImportResult {
  if (!seeds.length) {
    return { added: 0, updated: 0, skipped: 0, message: 'H3-9 盘点暂无记录，请先编制 H3-9' }
  }
  const existingNames = new Set(titleRows.map((r) => normName(r.assetName)).filter(Boolean))
  let added = 0
  let updated = 0
  let skipped = 0

  if (mode === 'addNew') {
    for (const seed of seeds) {
      const key = normName(seed.assetName)
      if (!key || existingNames.has(key) || findBestTitleMatch(titleRows, seed)) {
        skipped++
        continue
      }
      const row = normalizeTitleRow({
        rowId: `tt-h39-${seed.rowId || Date.now()}`,
        seq: titleRows.length + 1,
        assetName: seed.assetName,
        location: seed.location,
        titleCertNo: seed.titleCertNo,
        bookArea: seed.bookArea,
        bookValue: seed.bookValue,
        actualPurpose: seed.actualPurpose,
        certStatus: seed.titleCertNo ? '已办证' : '',
        sourceTags: 'H3-9',
      })
      titleRows.push(row)
      existingNames.add(key)
      added++
    }
    return {
      added, updated, skipped,
      message: added ? `已从 H3-9 新增 ${added} 行` : 'H3-9 资产均已存在于本表，未新增',
    }
  }

  for (const seed of seeds) {
    const row = findBestTitleMatch(titleRows, seed)
    if (!row) { skipped++; continue }
    if (_applyH39Seed(row, seed, overwrite)) updated++
    else skipped++
  }
  return {
    added: 0, updated, skipped,
    message: updated ? `已从 H3-9 ${overwrite ? '覆盖同步' : '补全'} ${updated} 行` : '无需从 H3-9 同步',
  }
}

/** L1 抵质押 → H3-12 抵押字段 */
export function syncMortgageFromL1(
  titleRows: TitleRow[],
  seeds: L1PledgeSeed[],
  overwrite = false,
): TitleImportResult & { unmatched: string[] } {
  if (!seeds.length) {
    return { added: 0, updated: 0, skipped: 0, unmatched: [], message: 'L1 无抵质押数据' }
  }
  let updated = 0
  let skipped = 0
  const unmatched: string[] = []
  const matchedH12 = new Set<string>()

  for (const seed of seeds) {
    const row = findBestTitleMatch(titleRows, seed)
    if (!row) {
      unmatched.push(seed.assetName)
      skipped++
      continue
    }
    let changed = 0
    if (overwrite || _isBlankStr(row.isRestricted)) {
      row.isRestricted = '是'
      changed++
    }
    if ((overwrite || _isZeroNum(row.mortgageValue)) && seed.guaranteedLoan > 0) {
      row.mortgageValue = seed.guaranteedLoan
      changed++
    }
    if (_isBlankStr(row.mortgageNature) || overwrite) {
      row.mortgageNature = row.mortgageNature || '抵押'
      changed++
    }
    if (_isBlankStr(row.refIndex) || overwrite) {
      row.refIndex = 'L1-8'
      changed++
    }
    if (seed.ownershipVerified && (_isBlankStr(row.remark) || overwrite)) {
      row.remark = [row.remark, `L1权属核验:${seed.ownershipVerified}`].filter(Boolean).join('；')
      changed++
    }
    if (changed) {
      addSourceTag(row, 'L1')
      matchedH12.add(row.rowId)
      updated++
    } else skipped++
  }

  // H3-12 已标受限但 L1 无对应
  const l1OnlyWarn = titleRows.filter(
    (r) => r.isRestricted === '是' && !matchedH12.has(r.rowId) && !(r.sourceTags || '').includes('L1'),
  )

  const parts = [
    updated ? `已匹配同步 ${updated} 行抵押信息` : '未匹配到可同步行',
    unmatched.length ? `L1有抵押但本表无对应：${unmatched.slice(0, 5).join('、')}${unmatched.length > 5 ? '…' : ''}` : '',
    l1OnlyWarn.length ? `本表受限但未匹配L1：${l1OnlyWarn.length} 项` : '',
  ].filter(Boolean)

  return { added: 0, updated, skipped, unmatched, message: parts.join('；') }
}

export function importTitleRowsFromAll(
  titleRows: TitleRow[],
  getValue: (id: string) => unknown,
  measurementModel: 'cost' | 'fair_value' = 'cost',
): TitleImportResult {
  const h32 = extractH32TitleSeeds(getValue, measurementModel)
  const h39 = extractH39TitleSeeds(getValue)
  if (!h32.length && !h39.length) {
    return { added: 0, updated: 0, skipped: 0, message: 'H3-2 与 H3-9 均无可用数据' }
  }
  const r1 = h32.length ? importTitleRowsFromH32(titleRows, h32, 'addNew') : { added: 0, updated: 0, skipped: 0, message: '' }
  const r2 = h32.length ? importTitleRowsFromH32(titleRows, h32, 'fillEmpty') : { added: 0, updated: 0, skipped: 0, message: '' }
  const r3 = h39.length ? importTitleRowsFromH39(titleRows, h39, 'fillEmpty') : { added: 0, updated: 0, skipped: 0, message: '' }
  return {
    added: r1.added,
    updated: r2.updated + r3.updated,
    skipped: r1.skipped + r2.skipped + r3.skipped,
    message: [r1.message, r2.message, r3.message].filter(Boolean).join('；') || '联动完成，无变更',
  }
}

/** 完整性勾稽 */
export function buildCompletenessChecks(
  titleRows: TitleRow[],
  getValue: (id: string) => unknown,
  measurementModel: 'cost' | 'fair_value' = 'cost',
): CompletenessCheck[] {
  const h32 = extractH32TitleSeeds(getValue, measurementModel)
  const h39 = extractH39TitleSeeds(getValue)
  const checks: CompletenessCheck[] = []

  const h32Count = h32.length
  const h12Count = titleRows.filter((r) => normName(r.assetName)).length
  checks.push({
    code: 'row-count',
    label: '行数一致',
    status: !h32Count ? 'info' : (h32Count === h12Count ? 'ok' : 'warn'),
    detail: !h32Count ? 'H3-2 暂无资产' : `H3-2 ${h32Count} 项 / H3-12 ${h12Count} 项`,
  })

  const h32Area = h32.reduce((s, r) => s + r.bookArea, 0)
  const h12Area = titleRows.reduce((s, r) => s + (Number(r.bookArea) || 0), 0)
  const areaOk = Math.abs(h32Area - h12Area) <= Math.max(1, h32Area * 0.01)
  checks.push({
    code: 'area-sum',
    label: '面积合计',
    status: !h32Count ? 'info' : (areaOk ? 'ok' : 'warn'),
    detail: `H3-2 ${h32Area.toFixed(2)}㎡ / H3-12 ${h12Area.toFixed(2)}㎡`,
  })

  const h32Val = h32.reduce((s, r) => s + r.bookValue, 0)
  const h12Val = titleRows.reduce((s, r) => s + (Number(r.bookValue) || 0), 0)
  const valOk = Math.abs(h32Val - h12Val) <= Math.max(1, h32Val * 0.01)
  checks.push({
    code: 'value-sum',
    label: '原值/公允合计',
    status: !h32Count ? 'info' : (valOk ? 'ok' : 'warn'),
    detail: `H3-2 ${h32Val.toLocaleString('zh-CN')} / H3-12 ${h12Val.toLocaleString('zh-CN')}`,
  })

  const missingFromStocktake = h39.filter((s) => !findBestTitleMatch(titleRows, s))
  checks.push({
    code: 'stocktake-cover',
    label: '盘点覆盖',
    status: !h39.length ? 'info' : (missingFromStocktake.length ? 'warn' : 'ok'),
    detail: !h39.length
      ? 'H3-9 暂无盘点'
      : (missingFromStocktake.length
        ? `${missingFromStocktake.length} 项盘点资产未纳入产权核对`
        : `H3-9 ${h39.length} 项均已覆盖`),
  })

  const certNos = titleRows.map((r) => (r.titleCertNo || '').trim()).filter(Boolean)
  const dup = certNos.filter((c, i) => certNos.indexOf(c) !== i)
  const uniqueDups = [...new Set(dup)]
  checks.push({
    code: 'cert-unique',
    label: '产权证唯一',
    status: uniqueDups.length ? 'error' : 'ok',
    detail: uniqueDups.length ? `重复证号：${uniqueDups.slice(0, 3).join('、')}` : '未见重复产权证号',
  })

  const pendingCert = titleRows.filter((r) => r.certStatus === '办证中')
  checks.push({
    code: 'cert-pending',
    label: '办证中',
    status: pendingCert.length ? 'warn' : 'ok',
    detail: pendingCert.length ? `${pendingCert.length} 项办证中，须说明进度` : '无办证中资产',
  })

  return checks
}

/** 反向同步：H3-12 产权证号 → H3-9 */
export function syncTitleCertToH39(
  titleRows: TitleRow[],
  getValue: (id: string) => unknown,
  setValue: (id: string, value: any) => void,
  overwrite = false,
): TitleImportResult {
  const raw = _parseJsonRows(getValue(H39_KEY))
  if (!raw.length) {
    return { added: 0, updated: 0, skipped: 0, message: 'H3-9 暂无盘点行，无法回写' }
  }
  let updated = 0
  let skipped = 0
  for (const st of raw) {
    const hit = findBestTitleMatch(titleRows, {
      assetName: String(st.assetName || ''),
      location: String(st.location || ''),
      bookArea: Number(st.area) || 0,
    })
    if (!hit || !hit.titleCertNo) { skipped++; continue }
    const empty = !String(st.titleCertNo || '').trim()
    if (overwrite || empty) {
      st.titleCertNo = hit.titleCertNo
      if (!String(st.location || '').trim() && hit.location) st.location = hit.location
      updated++
    } else skipped++
  }
  if (updated) setValue(H39_KEY, raw)
  return {
    added: 0, updated, skipped,
    message: updated ? `已回写 H3-9 产权证号 ${updated} 行` : '无需回写 H3-9',
  }
}

/** 同步受限说明至附注 */
export function syncRestrictedToDisclosure(
  titleRows: TitleRow[],
  setValue: (id: string, value: any) => void,
): { count: number; message: string } {
  const text = buildRestrictionDisclosureText(titleRows)
  setValue(DISC_LISTED_KEY, text)
  setValue(DISC_SOE_KEY, text)
  const count = titleRows.filter((r) => r.isRestricted === '是' || r.mortgageValue > 0).length
  return {
    count,
    message: count
      ? `已同步 ${count} 项权利限制至上市/国企附注「限制及担保」`
      : '已写入「未见重大权利限制」至附注',
  }
}

/** 预填证载面积=账面面积并标记待核实 */
export function fillCertAreaFromBook(titleRows: TitleRow[]): number {
  let n = 0
  for (const row of titleRows) {
    if (!(row.bookArea > 0)) continue
    if (row.certArea > 0 && !row.certAreaPending) continue
    row.certArea = row.bookArea
    row.certAreaPending = true
    _recomputeTitleRow(row)
    n++
  }
  return n
}

/**
 * 抽样：按账面价值降序覆盖 targetCoverage（默认80%），不足时补随机项至 minCount
 */
export function applySamplePlan(
  titleRows: TitleRow[],
  opts: { targetCoverage?: number; minCount?: number } = {},
): SamplePlan {
  const targetCoverage = opts.targetCoverage ?? 0.8
  const minCount = opts.minCount ?? Math.min(5, titleRows.length)
  titleRows.forEach((r) => { r.sampled = false })
  const totalValue = titleRows.reduce((s, r) => s + Math.abs(Number(r.bookValue) || 0), 0)
  const sorted = [...titleRows].sort((a, b) => Math.abs(b.bookValue) - Math.abs(a.bookValue))
  let sampledValue = 0
  const picked = new Set<string>()
  for (const row of sorted) {
    if (totalValue > 0 && sampledValue / totalValue >= targetCoverage && picked.size >= minCount) break
    row.sampled = true
    picked.add(row.rowId)
    sampledValue += Math.abs(Number(row.bookValue) || 0)
  }
  // 随机补足
  const rest = titleRows.filter((r) => !picked.has(r.rowId))
  for (let i = rest.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [rest[i], rest[j]] = [rest[j], rest[i]]
  }
  for (const row of rest) {
    if (picked.size >= minCount && (totalValue === 0 || sampledValue / totalValue >= targetCoverage)) break
    row.sampled = true
    picked.add(row.rowId)
    sampledValue += Math.abs(Number(row.bookValue) || 0)
  }
  const coveragePct = totalValue > 0 ? (sampledValue / totalValue) * 100 : 0
  return {
    sampledCount: picked.size,
    coveragePct,
    totalValue,
    sampledValue,
    message: `已抽样 ${picked.size} 项，覆盖账面价值 ${coveragePct.toFixed(1)}%`,
  }
}

/** 减值关注提示：权属异常/权利受限/办证中/面积异常 */
export function buildImpairmentHints(titleRows: TitleRow[]): string[] {
  const hints: string[] = []
  for (const r of titleRows) {
    const reasons: string[] = []
    if (r.isAuditEntity === '否') reasons.push('权属非被审计单位')
    if (r.isRestricted === '是') reasons.push('权利受限')
    if (r.certStatus === '办证中') reasons.push('办证中')
    if (r.hasDispute === '是') reasons.push('权属纠纷')
    if (isAreaAnomaly(r.certArea, r.bookArea)) reasons.push('面积异常')
    if (reasons.length) hints.push(`${r.assetName || '未命名'}：${reasons.join('、')} → 建议关注减值/H3-10`)
  }
  return hints
}

export function applyAuditeeDefaults(titleRows: TitleRow[], auditeeName: string): number {
  if (!auditeeName.trim()) return 0
  let n = 0
  for (const row of titleRows) {
    if (_isBlankStr(row.bookOwner)) { row.bookOwner = auditeeName; n++ }
    if (_isBlankStr(row.certOwner)) { row.certOwner = auditeeName; n++ }
    if (_isBlankStr(row.isAuditEntity)) { row.isAuditEntity = '是'; n++ }
  }
  return n
}

export function countH32Assets(
  getValue: (id: string) => unknown,
  measurementModel: 'cost' | 'fair_value' = 'cost',
): number {
  return extractH32Assets(getValue, measurementModel).length
}
