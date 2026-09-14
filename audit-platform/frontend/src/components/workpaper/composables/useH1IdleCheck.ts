/**
 * useH1IdleCheck — H1-4 闲置检查表 composable
 *
 * 对齐致同模板「闲置固定资产检查表」逻辑：
 * 目标 → 程序 → 未使用/不需用清单 → 减值迹象 → 说明/结论 → 联动 H1-14
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Requirements: 5.1-5.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 闲置类型：对应模板表①未使用 / 表②不需用 */
export type IdleType = 'unused' | 'unneeded'

/** 处置计划 */
export type DisposalPlan = 'idle' | 'dispose' | 'reuse' | ''

export interface IdleAssetRow {
  rowId: string
  seq: number
  /** 未使用 | 不需用 */
  idleType: IdleType
  category: string
  name: string
  assetNo: string
  originalCost: number
  accDep: number
  /** 减值准备（账面已计提） */
  impairmentProvision: number
  /** 净值 = 原值 - 累计折旧 - 减值准备（自动计算） */
  netValue: number
  idleStartDate: string
  idleEndDate: string
  /** 状况：完好/需维修/毁损/待报废等 */
  condition: string
  idleReason: string
  /** 是否按规定继续计提折旧 Y/N/NA */
  depContinued: string
  /** 本期折旧计提额（来自 H1-2，用于停提异常判断） */
  periodDepProvision: number
  /** 处置计划：继续闲置 / 计划处置 / 转为使用 */
  disposalSuggestion: DisposalPlan | string
  /** 是否已计提减值 Y/N（账面） */
  hasImpairment: string
  /** 本期减值金额（与减值准备可分别记录） */
  impairmentAmount: number
  remark: string
  /** 来源明细 rowId（H1-2 带入去重） */
  sourceDetailRowId?: string
}

export interface IdleStatistics {
  totalCount: number
  unusedCount: number
  unneededCount: number
  totalOriginalCost: number
  totalNetValue: number
  impairedTotal: number
  indicationCount: number
  /** 有迹象但未计提减值（需联动 H1-14） */
  indicationNotImpairedCount: number
  /** 疑似停提折旧异常项数 */
  depStopAnomalyCount: number
}

export interface DepStopWarning {
  rowId: string
  name: string
  assetNo: string
  level: 'error' | 'warning'
  message: string
}

export interface ImportFromDetailResult {
  added: number
  refreshed: number
  skipped: number
  candidates: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-4'
const MS_PER_DAY = 24 * 60 * 60 * 1000
/** 闲置满一年视为强减值迹象（CAS8 实务阈值） */
const IDLE_INDICATION_DAYS = 365

const PLAN_LABELS: Record<string, string> = {
  idle: '继续闲置',
  dispose: '计划处置',
  reuse: '转为使用',
}

// ─── Pure helpers（可单测）───────────────────────────────────────────────────

export function calcIdleNetValue(cost: number, accDep: number, provision: number): number {
  return Math.max(0, (Number(cost) || 0) - (Number(accDep) || 0) - (Number(provision) || 0))
}

export function idleDurationDays(startDate: string, asOf: Date = new Date()): number | null {
  if (!startDate) return null
  const start = new Date(startDate)
  if (Number.isNaN(start.getTime())) return null
  return Math.floor((asOf.getTime() - start.getTime()) / MS_PER_DAY)
}

/**
 * 减值迹象判定（CAS8 第5条 + 编制提示）：
 * - 计划处置 / 毁损待报废 → 有
 * - 闲置≥1年且无明确复用计划 → 有
 * - 明确转为使用且闲置未满1年、状况正常 → 无（可观察）
 * - 其余净值>0 的闲置资产 → 有（闲置本身属迹象，需评价是否测试）
 */
export function evaluateImpairmentIndication(row: Pick<
  IdleAssetRow,
  'netValue' | 'idleStartDate' | 'disposalSuggestion' | 'condition' | 'idleReason'
>, asOf: Date = new Date()): boolean {
  if ((Number(row.netValue) || 0) <= 0) return false

  const plan = String(row.disposalSuggestion || '').toLowerCase()
  const cond = String(row.condition || '')
  const reason = String(row.idleReason || '')

  if (plan === 'dispose' || plan.includes('处置') || plan.includes('报废')) return true
  if (/毁损|待报废|报废|严重损坏/.test(cond) || /毁损|待报废|报废/.test(reason)) return true

  const days = idleDurationDays(row.idleStartDate, asOf)
  const willReuse = plan === 'reuse' || plan.includes('复用') || plan.includes('转为使用')
  if (days != null && days >= IDLE_INDICATION_DAYS && !willReuse) return true

  // 明确短期闲置且有复用计划、状况完好 → 可不认定需立即测试
  if (willReuse && (days == null || days < IDLE_INDICATION_DAYS) && /完好|正常|良好/.test(cond)) {
    return false
  }

  // 默认：账面闲置且净值>0 → 存在迹象（需在说明中评价是否进一步测算）
  return true
}

export function planLabel(plan: string): string {
  return PLAN_LABELS[plan] || plan || '—'
}

/** H1-2 文本中识别闲置线索的关键词 */
const IDLE_TEXT_RE = /未使用|不需用|闲置|停用|暂未使用|暂时闲置|待处置|待报废|停产闲置/
const UNNEEDED_RE = /不需用|待处置|拟处置|拟报废|待报废/

function _detailTextBlob(d: Record<string, any>): string {
  return [
    d.category, d.name, d.assetName, d.remark, d.department, d.location,
    d.usageStatus, d.useStatus, d.status, d.assetStatus, d.decreaseReason, d.idleReason,
  ].map((x) => String(x ?? '')).join('|')
}

/** 判断 H1-2 明细行是否像闲置/未使用/不需用资产 */
export function isIdleDetailCandidate(d: Record<string, any>): boolean {
  if (!d || typeof d !== 'object') return false
  const cost = Number(d.originalCostEnd ?? d.originalCost ?? 0) || 0
  if (cost <= 0) return false
  const flag = d.idleFlag ?? d.isIdle ?? d.idle
  if (flag === true || flag === 'Y' || flag === 1 || flag === '1') return true
  const text = _detailTextBlob(d)
  return IDLE_TEXT_RE.test(text)
}

export function inferIdleTypeFromDetail(d: Record<string, any>): IdleType {
  const text = _detailTextBlob(d)
  if (UNNEEDED_RE.test(text)) return 'unneeded'
  return 'unused'
}

/** 是否已提足折旧（净值接近残值或接近 0） */
export function isFullyDepreciated(row: Pick<IdleAssetRow, 'originalCost' | 'accDep' | 'netValue' | 'impairmentProvision'>): boolean {
  const cost = Number(row.originalCost) || 0
  if (cost <= 0) return true
  const net = Number(row.netValue) || 0
  if (net <= cost * 0.05) return true
  const acc = Number(row.accDep) || 0
  return acc >= cost * 0.95
}

/**
 * 折旧停提异常（CAS4：闲置固定资产通常应继续计提折旧）：
 * - 明确勾选「否」且未提足 → error
 * - 本期计提为 0、净值仍大、未勾选「是」→ warning
 */
export function evaluateDepStopAnomaly(row: IdleAssetRow): DepStopWarning | null {
  const label = row.name || row.assetNo || '未命名资产'
  if (isFullyDepreciated(row)) return null

  const plan = String(row.disposalSuggestion || '')
  const cond = String(row.condition || '')
  // 待报废且已决策处置、净值很小以外的情况仍提示，但不把「计划处置」豁免——处置前一般仍应折旧

  if (row.depContinued === 'N') {
    return {
      rowId: row.rowId,
      name: label,
      assetNo: row.assetNo || '',
      level: 'error',
      message: `「${label}」标记为未继续计提折旧，但账面未提足（净值 ${Number(row.netValue).toLocaleString('zh-CN')}）。闲置固定资产通常应继续折旧，请核实会计政策或补提。`,
    }
  }

  const periodDep = Number(row.periodDepProvision)
  if (
    Number.isFinite(periodDep) &&
    periodDep <= 0.005 &&
    (Number(row.netValue) || 0) > 0 &&
    row.depContinued !== 'Y' &&
    row.depContinued !== 'NA'
  ) {
    const scrapish = /待报废|报废/.test(cond) || plan === 'dispose'
    return {
      rowId: row.rowId,
      name: label,
      assetNo: row.assetNo || '',
      level: scrapish ? 'warning' : 'warning',
      message: `「${label}」本期折旧计提为 0 且净值仍大于 0，疑似停提；请确认是否按规定继续计提折旧（CAS4）。`,
    }
  }

  return null
}

export function mapDetailRowToIdle(d: Record<string, any>, seq: number): IdleAssetRow {
  const originalCost = Number(d.originalCostEnd ?? d.originalCost ?? 0) || 0
  const accDep = Number(d.accDepEnd ?? d.accDep ?? 0) || 0
  const impairmentProvision = Number(d.impairmentEnd ?? d.impairmentProvision ?? d.impairment ?? 0) || 0
  const periodDepProvision = Number(d.accDepProvision ?? d.periodDepreciation ?? d.annualDep ?? 0) || 0
  const netValue = calcIdleNetValue(originalCost, accDep, impairmentProvision)
  const idleType = inferIdleTypeFromDetail(d)
  const text = _detailTextBlob(d)
  let depContinued = ''
  if (periodDepProvision > 0.005) depContinued = 'Y'
  else if (originalCost > 0 && !isFullyDepreciated({ originalCost, accDep, netValue, impairmentProvision })) {
    depContinued = '' // 待人工确认；异常引擎会提示
  } else if (isFullyDepreciated({ originalCost, accDep, netValue, impairmentProvision })) {
    depContinued = 'NA'
  }

  return {
    rowId: `idle-from-h12-${d.rowId || d.assetNo || seq}-${Date.now().toString(36).slice(-4)}`,
    seq,
    idleType,
    category: String(d.category ?? ''),
    name: String(d.name ?? d.assetName ?? ''),
    assetNo: String(d.assetNo ?? d.assetCode ?? ''),
    originalCost,
    accDep,
    impairmentProvision,
    netValue,
    idleStartDate: String(d.idleStartDate ?? ''),
    idleEndDate: '',
    condition: String(d.condition ?? ''),
    idleReason: IDLE_TEXT_RE.test(text)
      ? (String(d.idleReason || d.remark || '').trim() || 'H1-2 明细识别为闲置/未使用/不需用')
      : String(d.idleReason || ''),
    depContinued,
    periodDepProvision,
    disposalSuggestion: idleType === 'unneeded' ? 'dispose' : 'idle',
    hasImpairment: impairmentProvision > 0 ? 'Y' : 'N',
    impairmentAmount: impairmentProvision,
    remark: `来源:H1-2/${d.rowId || d.assetNo || ''}`,
    sourceDetailRowId: String(d.rowId ?? ''),
  }
}

export function draftIdleConclusion(input: {
  stats: IdleStatistics
  warnings: DepStopWarning[]
  rows: IdleAssetRow[]
}): string {
  const { stats, warnings, rows } = input
  if (!stats.totalCount) {
    return '本期未发现需专项记录的闲置/未使用/不需用固定资产，或相关余额已在其他程序中覆盖。建议结合监盘（H1-9/10/11）与明细分类复核予以确认。'
  }
  const parts: string[] = []
  parts.push(
    `本期检查闲置固定资产共 ${stats.totalCount} 项（未使用 ${stats.unusedCount}、不需用 ${stats.unneededCount}），` +
    `原值合计 ${stats.totalOriginalCost.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元，` +
    `净值合计 ${stats.totalNetValue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元。`,
  )
  if (stats.indicationCount > 0) {
    parts.push(
      `其中 ${stats.indicationCount} 项存在减值迹象` +
      (stats.indicationNotImpairedCount
        ? `（${stats.indicationNotImpairedCount} 项尚未计提减值，已/拟联动 H1-14 测算）`
        : '（相关减值已反映于账面）') +
      '。',
    )
  } else {
    parts.push('经评价，上述闲置资产暂未识别需追加减值测试的重大迹象，或已有充分依据支持账面计价。')
  }
  if (warnings.length) {
    parts.push(
      `发现 ${warnings.length} 项疑似未按规定继续计提折旧的情形，需核实会计政策并评估是否补提折旧调整。`,
    )
  } else {
    parts.push('抽查未见明显违反「闲置资产应继续计提折旧」的异常（或已注明 N/A）。')
  }
  const top = rows
    .filter((r) => evaluateImpairmentIndication(r) && r.hasImpairment !== 'Y')
    .slice(0, 3)
    .map((r) => r.name || r.assetNo)
    .filter(Boolean)
  if (top.length) {
    parts.push(`需关注未计提减值的主要项目：${top.join('、')}。`)
  }
  parts.push(
    '综上，除上述需跟进事项外，闲置固定资产的分类列报、折旧与减值相关会计处理在所有重大方面符合企业会计准则的规定。',
  )
  return parts.join('')
}

export function draftIdleNote(input: {
  stats: IdleStatistics
  warnings: DepStopWarning[]
  rows: IdleAssetRow[]
}): string {
  const { stats, warnings, rows } = input
  const lines: string[] = []
  lines.push(
    `①识别范围：自 H1-2 及监盘关注项汇总闲置/未使用/不需用固定资产 ${stats.totalCount} 项，` +
    `原值 ${stats.totalOriginalCost.toLocaleString('zh-CN')}、净值 ${stats.totalNetValue.toLocaleString('zh-CN')}。`,
  )
  lines.push(
    `②折旧：${warnings.length ? `关注 ${warnings.length} 项停提异常（详见警示）；` : '未见重大停提异常；'}` +
    '已核对是否按规定继续计提折旧。',
  )
  lines.push(
    `③减值迹象（CAS8）：有迹象 ${stats.indicationCount} 项，有迹象未计提 ${stats.indicationNotImpairedCount} 项` +
    (stats.indicationNotImpairedCount ? '，已提示引入 H1-14。' : '。'),
  )
  const sample = rows.slice(0, 5).map((r) => {
    const bits = [r.name || r.assetNo || '未命名']
    if (r.idleReason) bits.push(r.idleReason)
    return bits.join('/')
  })
  if (sample.length) lines.push(`④主要项目：${sample.join('；')}${rows.length > 5 ? ' 等。' : '。'}`)
  return lines.join('\n')
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1IdleCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<IdleAssetRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _loadRows(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    const raw = item?.remark
    if (!raw) {
      rows.value = []
    } else {
      try {
        const parsed = JSON.parse(raw)
        rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow) : []
      } catch {
        rows.value = []
      }
    }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeIdleType(raw: any): IdleType {
    const v = String(raw?.idleType ?? raw?.type ?? '').toLowerCase()
    if (v === 'unneeded' || v === '不需用' || v.includes('不需')) return 'unneeded'
    return 'unused'
  }

  function _normalizePlan(raw: any): string {
    const p = raw?.disposalSuggestion ?? raw?.plan ?? ''
    if (p === 'idle' || p === 'dispose' || p === 'reuse') return p
    if (String(p).includes('处置')) return 'dispose'
    if (String(p).includes('使用') || String(p).includes('复用')) return 'reuse'
    if (String(p).includes('闲置')) return 'idle'
    return p || ''
  }

  function _normalizeRow(raw: any, idx: number): IdleAssetRow {
    const originalCost = Number(raw.originalCost) || 0
    const accDep = Number(raw.accDep) || 0
    const impairmentProvision =
      Number(raw.impairmentProvision) ||
      Number(raw.impairment) ||
      (raw.hasImpairment === 'Y' ? Number(raw.impairmentAmount) || 0 : 0)
    const netFromBook = Number(raw.netValue)
    const netValue =
      Number.isFinite(netFromBook) && netFromBook > 0 && !raw.originalCost && !raw.accDep
        ? netFromBook
        : calcIdleNetValue(originalCost, accDep, impairmentProvision)

    return {
      rowId: raw.rowId ?? `idle-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      idleType: _normalizeIdleType(raw),
      category: raw.category ?? '',
      name: raw.name ?? '',
      assetNo: raw.assetNo ?? '',
      originalCost,
      accDep,
      impairmentProvision,
      netValue,
      idleStartDate: raw.idleStartDate ?? raw.idleDate ?? '',
      idleEndDate: raw.idleEndDate ?? '',
      condition: raw.condition ?? raw.status ?? '',
      idleReason: raw.idleReason ?? '',
      depContinued: raw.depContinued ?? '',
      periodDepProvision: Number(raw.periodDepProvision) || 0,
      disposalSuggestion: _normalizePlan(raw),
      hasImpairment: raw.hasImpairment ?? (impairmentProvision > 0 ? 'Y' : 'N'),
      impairmentAmount: Number(raw.impairmentAmount) || impairmentProvision || 0,
      remark: raw.remark ?? '',
      sourceDetailRowId: raw.sourceDetailRowId ?? '',
    }
  }

  function _recalcNet(row: IdleAssetRow): void {
    row.netValue = calcIdleNetValue(row.originalCost, row.accDep, row.impairmentProvision)
  }

  const depStopWarnings = computed<DepStopWarning[]>(() => {
    const out: DepStopWarning[] = []
    for (const r of rows.value) {
      const w = evaluateDepStopAnomaly(r)
      if (w) out.push(w)
    }
    return out
  })

  const statistics = computed<IdleStatistics>(() => {
    const list = rows.value
    const indicationRows = list.filter((r) => evaluateImpairmentIndication(r))
    return {
      totalCount: list.length,
      unusedCount: list.filter((r) => r.idleType === 'unused').length,
      unneededCount: list.filter((r) => r.idleType === 'unneeded').length,
      totalOriginalCost: calcSubtotal(list.map((r) => r.originalCost)),
      totalNetValue: calcSubtotal(list.map((r) => r.netValue)),
      impairedTotal: calcSubtotal(
        list.filter((r) => r.hasImpairment === 'Y').map((r) => r.impairmentAmount || r.impairmentProvision),
      ),
      indicationCount: indicationRows.length,
      indicationNotImpairedCount: indicationRows.filter((r) => r.hasImpairment !== 'Y').length,
      depStopAnomalyCount: depStopWarnings.value.length,
    }
  })

  /** 兼容旧 UI 命名 */
  function hasImpairmentIndication(row: IdleAssetRow): boolean {
    return evaluateImpairmentIndication(row)
  }

  function _parseH12Rows(): any[] {
    const item = allResponses.value.get('H1-2-rows')
    if (!item?.remark) return []
    try {
      const parsed = typeof item.remark === 'string' ? JSON.parse(item.remark) : item.remark
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  function _rowKey(r: { assetNo?: string; name?: string; sourceDetailRowId?: string }): string {
    if (r.sourceDetailRowId) return `src:${r.sourceDetailRowId}`
    if (r.assetNo) return `no:${r.assetNo}`
    return `name:${r.name || ''}`
  }

  /**
   * 从 H1-2 带入闲置/未使用/不需用科目余额（关键词+标记字段识别）。
   * 按资产编号/名称/来源行去重；已存在则刷新金额字段。
   */
  function importFromDetail(opts?: { replace?: boolean }): ImportFromDetailResult {
    const detail = _parseH12Rows()
    const candidates = detail.filter(isIdleDetailCandidate)
    if (opts?.replace) {
      rows.value = candidates.map((d, i) => mapDetailRowToIdle(d, i + 1))
      _persist()
      return { added: candidates.length, refreshed: 0, skipped: 0, candidates: candidates.length }
    }

    const keyMap = new Map(rows.value.map((r) => [_rowKey(r), r]))
    let added = 0
    let refreshed = 0
    let skipped = 0

    for (const d of candidates) {
      const mapped = mapDetailRowToIdle(d, rows.value.length + 1)
      const key = _rowKey({
        assetNo: mapped.assetNo,
        name: mapped.name,
        sourceDetailRowId: mapped.sourceDetailRowId || String(d.rowId ?? ''),
      })
      const hit = keyMap.get(key) || keyMap.get(`no:${mapped.assetNo}`) || keyMap.get(`name:${mapped.name}`)
      if (hit) {
        hit.category = mapped.category || hit.category
        hit.originalCost = mapped.originalCost
        hit.accDep = mapped.accDep
        hit.impairmentProvision = mapped.impairmentProvision
        hit.netValue = mapped.netValue
        hit.periodDepProvision = mapped.periodDepProvision
        hit.hasImpairment = mapped.hasImpairment
        hit.impairmentAmount = mapped.impairmentAmount
        if (!hit.idleReason) hit.idleReason = mapped.idleReason
        if (!hit.depContinued && mapped.depContinued) hit.depContinued = mapped.depContinued
        if (!String(hit.remark || '').includes('来源:H1-2')) {
          hit.remark = [hit.remark, mapped.remark].filter(Boolean).join('；')
        }
        hit.sourceDetailRowId = mapped.sourceDetailRowId || hit.sourceDetailRowId
        refreshed++
      } else {
        rows.value.push(mapped)
        keyMap.set(key, mapped)
        added++
      }
    }
    if (!candidates.length) skipped = detail.length
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
    return { added, refreshed, skipped, candidates: candidates.length }
  }

  function addRow(name: string, idleType: IdleType = 'unused'): void {
    const newRow: IdleAssetRow = {
      rowId: `idle-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1,
      idleType,
      category: '',
      name,
      assetNo: '',
      originalCost: 0,
      accDep: 0,
      impairmentProvision: 0,
      netValue: 0,
      idleStartDate: '',
      idleEndDate: '',
      condition: '',
      idleReason: '',
      depContinued: '',
      periodDepProvision: 0,
      disposalSuggestion: 'idle',
      hasImpairment: 'N',
      impairmentAmount: 0,
      remark: '',
    }
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      rows.value.forEach((r, i) => {
        r.seq = i + 1
      })
      _persist()
    }
  }

  function updateCell(rowId: string, field: keyof IdleAssetRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'originalCost' || field === 'accDep' || field === 'impairmentProvision') {
      _recalcNet(row)
    }
    if (field === 'impairmentProvision' && Number(value) > 0) {
      row.hasImpairment = 'Y'
      if (!row.impairmentAmount) row.impairmentAmount = Number(value) || 0
    }
    _persist()
  }

  function _persist(): void {
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function rowsByType(type: IdleType): IdleAssetRow[] {
    return rows.value.filter((r) => r.idleType === type)
  }

  function buildConclusionDraft(): string {
    return draftIdleConclusion({
      stats: statistics.value,
      warnings: depStopWarnings.value,
      rows: rows.value,
    })
  }

  function buildNoteDraft(): string {
    return draftIdleNote({
      stats: statistics.value,
      warnings: depStopWarnings.value,
      rows: rows.value,
    })
  }

  /**
   * 主动预警：将「有减值迹象且未计提减值」的闲置资产经 EventBus 推送，
   * H1-14/H1-15 减值测算据此高亮待处理项（对齐 EventBus 联动范式）。
   */
  function _publishIdleImpairmentSign(): void {
    const assets = rows.value
      .filter((r) => evaluateImpairmentIndication(r) && r.hasImpairment !== 'Y')
      .map((r) => ({
        name: r.name || r.assetNo || '未命名资产',
        assetNo: r.assetNo || '',
        netValue: Number(r.netValue) || 0,
      }))
    eventBus.emit('h1:idle-impairment-sign' as any, {
      wpId: wpId.value,
      projectId: projectId.value,
      count: assets.length,
      assets,
    })
  }

  watch(allResponses, () => _loadRows(), { immediate: true })
  // 迹象未计提数变化 → 推送预警（含清零场景，便于 H1-14 撤销提醒）
  watch(
    () => statistics.value.indicationNotImpairedCount,
    () => _publishIdleImpairmentSign(),
    { flush: 'post', immediate: true },
  )

  return {
    rows,
    auditNote,
    auditConclusion,
    statistics,
    depStopWarnings,
    hasImpairmentIndication,
    evaluateImpairmentIndication,
    evaluateDepStopAnomaly,
    addRow,
    removeRow,
    updateCell,
    importFromDetail,
    saveNote,
    saveConclusion,
    rowsByType,
    planLabel,
    idleDurationDays,
    buildConclusionDraft,
    buildNoteDraft,
  }
}

export default useH1IdleCheck
