/**
 * useH2ReviewRecord — H2-6 在建工程按项目审核记录
 *
 * 对齐致同模板「在建工程－XX项目-XX子项目审核记录」：
 * 1 项目综合描述 → 2 资料/合同核对 → 3 历年发生额 → 4 本期发生额查验
 * → 5 利息资本化 → 6 状态查验 → 7 长期挂账 → 8 关联方 → 9 受限/减值
 *
 * 多项目：records[] 一行一工程；弹窗编辑单条；可从 H2-2 带入并联动风险标记。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type YesNoNa = '' | 'yes' | 'no' | 'na'
export type UsableState = '' | 'yes' | 'no' | 'partial'

/** 历年发生额一行 */
export interface H2YearBalanceRow {
  rowId: string
  /** 年份标签：开工年度 / 中间年 / 本年 / 合计 */
  yearLabel: string
  year: string
  begin: number
  debit: number
  credit: number
  end: number
}

/** 单工程审核记录（对应 Excel 一份 H2-6） */
export interface H2ProjectReviewRecord {
  rowId: string
  /** 工程项目名称（主项目） */
  projectName: string
  /** 子项目名称 */
  subProjectName: string
  /** 来源 H2-2 行 id（同步用） */
  sourceDetailRowId: string

  // 1、项目综合描述
  projectDescription: string

  // 2、资料及合同核对
  docCheckIndex: string
  docCheckNote: string
  contractCheckIndex: string
  contractCheckNote: string

  // 3、历年发生额
  yearBalances: H2YearBalanceRow[]

  // 4、本期发生额查验（勾稽 H2-8）
  additionCheckIndex: string
  additionCheckNote: string

  // 5、利息资本化审核（勾稽 H2-10/H2-11）
  interestCapIndex: string
  interestCapNote: string

  // 6、状态查验
  assetExists: YesNoNa
  assetExistsNote: string
  /** 现状描述：进度、是否达预定可使用状态、是否停工 */
  statusDescription: string
  reachedUsableState: UsableState
  isSuspended: boolean
  /** 已达可用但未转固（高风险） */
  transferRisk: boolean

  // 7、是否长期挂账
  isLongTermOutstanding: YesNoNa
  longTermNote: string
  /** 无发生额年数（≥1 关注） */
  noMovementYears: number | null

  // 8、有无关联方交易（勾稽 H2-17）
  hasRelatedParty: YesNoNa
  relatedPartyNote: string
  relatedPartyIndex: string

  // 9a、是否受限
  isRestricted: YesNoNa
  restrictedNote: string

  // 9b、是否存在减值（勾稽 H2-15）
  hasImpairment: YesNoNa
  impairmentIndex: string
  impairmentNote: string

  // 账面快照（自 H2-2 带入，便于汇总与风险判断）
  cipBegin: number
  cipIncrease: number
  cipDecrease: number
  cipEnd: number
  completionRate: number | null
  contractor: string
  supervisor: string

  /** 本工程核查结论草稿 */
  projectConclusion: string
  remark: string
}

/** H2-5 按工程快照 */
export interface H25ProjectSnapshot {
  found: boolean
  name: string
  allConditionsMet: boolean
  condition5: boolean
  transferDate: string
  transferAmount: number
  timelyTransfer: boolean | null
  delayDays: number
  difference: number
}

/** H2-13 按工程快照（多行取汇总） */
export interface H213ProjectSnapshot {
  found: boolean
  name: string
  readyForUse: '是' | '否' | ''
  constructionStatus: string
  stopDuration: string
  stopReason: string
  progressDesc: string
  result: string
  visibleProgress: number | null
  rowCount: number
}

export interface ReconcileIssue {
  code: string
  level: 'error' | 'warn' | 'info'
  message: string
  source: 'H2-5' | 'H2-13' | '交叉'
}

export interface ProjectReconcileResult {
  h25: H25ProjectSnapshot | null
  h213: H213ProjectSnapshot | null
  issues: ReconcileIssue[]
  /** 建议回填到 H2-6 的字段（空字段优先 / 状态类可覆盖） */
  suggestedPatch: Partial<H2ProjectReviewRecord>
}

export interface H2ReviewSignature {
  preparedBy: string
  preparedDate: string
  reviewedBy: string
  reviewedDate: string
}

export interface H2ReviewRiskSummary {
  total: number
  filled: number
  transferRisk: number
  longTerm: number
  relatedParty: number
  impairment: number
  suspended: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const RECORDS_KEY = 'H2-6-records'
const LEGACY_ITEMS_KEY = 'H2-6-items'
const LEGACY_BASIC_KEY = 'H2-6-basic-info'
const SIGNATURE_KEY = 'H2-6-signature'
const CONCLUSION_KEY = 'H2-6-conclusion'
const NOTE_KEY = 'H2-6-audit-note'

export const H2_6_SECTION_TIPS: Record<string, string> = {
  s1: '概述工程性质、建设地点、合同主体、预算与工期等，便于后续程序勾稽。',
  s2: '资料核对表与合同核对表分别索引；差异在备注中说明。',
  s3: '历年发生额应与明细账、H2-2 勾稽；合计行期末=各年勾稽后余额。',
  s4: '本期借方发生额查验详见增加检查表 H2-8；索引与抽凭结论交叉引用。',
  s5: '利息资本化审核详见 H2-10（无专门借款）或 H2-11（有专门借款）。',
  s6: '结合现场观察与在建工程明细，关注已达预定可使用状态但未转固、以及长期停工。',
  s7: '重点关注一年以上无发生额的在建工程；说明原因及拟采取程序。',
  s8: '核对增减是否涉及关联方工程承包、管理等；授权、定价公允性及披露。',
  s9a: '结合贷款卡、专项借款/债券资金来源，判断是否抵押/担保及披露。',
  s9b: '减值迹象与测算详见 H2-15/H2-16；此处记录结论与索引。',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _uid(prefix = 'row'): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function emptyYearBalances(): H2YearBalanceRow[] {
  return [
    { rowId: _uid('yb'), yearLabel: '开工年度', year: '', begin: 0, debit: 0, credit: 0, end: 0 },
    { rowId: _uid('yb'), yearLabel: '…', year: '', begin: 0, debit: 0, credit: 0, end: 0 },
    { rowId: _uid('yb'), yearLabel: '本年', year: '', begin: 0, debit: 0, credit: 0, end: 0 },
    { rowId: _uid('yb'), yearLabel: '合计', year: '', begin: 0, debit: 0, credit: 0, end: 0 },
  ]
}

export function createEmptyRecord(partial?: Partial<H2ProjectReviewRecord>): H2ProjectReviewRecord {
  return {
    rowId: _uid('prj'),
    projectName: '',
    subProjectName: '',
    sourceDetailRowId: '',
    projectDescription: '',
    docCheckIndex: '',
    docCheckNote: '',
    contractCheckIndex: '',
    contractCheckNote: '',
    yearBalances: emptyYearBalances(),
    additionCheckIndex: 'H2-8',
    additionCheckNote: '',
    interestCapIndex: 'H2-10/H2-11',
    interestCapNote: '',
    assetExists: '',
    assetExistsNote: '',
    statusDescription: '',
    reachedUsableState: '',
    isSuspended: false,
    transferRisk: false,
    isLongTermOutstanding: '',
    longTermNote: '',
    noMovementYears: null,
    hasRelatedParty: '',
    relatedPartyNote: '',
    relatedPartyIndex: 'H2-17',
    isRestricted: '',
    restrictedNote: '',
    hasImpairment: '',
    impairmentIndex: 'H2-15',
    impairmentNote: '',
    cipBegin: 0,
    cipIncrease: 0,
    cipDecrease: 0,
    cipEnd: 0,
    completionRate: null,
    contractor: '',
    supervisor: '',
    projectConclusion: '',
    remark: '',
    ...partial,
  }
}

/** 填写完整度 0–100（核心核查点） */
export function calcFillProgress(r: H2ProjectReviewRecord): number {
  const checks: boolean[] = [
    !!r.projectName.trim(),
    !!r.projectDescription.trim(),
    !!(r.docCheckIndex.trim() || r.docCheckNote.trim() || r.contractCheckIndex.trim()),
    r.yearBalances.some(y => y.begin !== 0 || y.debit !== 0 || y.credit !== 0 || y.end !== 0),
    !!(r.additionCheckIndex.trim() || r.additionCheckNote.trim()),
    !!(r.interestCapNote.trim() || r.interestCapIndex.trim()),
    r.assetExists !== '' || !!r.statusDescription.trim(),
    r.isLongTermOutstanding !== '',
    r.hasRelatedParty !== '',
    r.isRestricted !== '' || r.hasImpairment !== '',
    !!r.projectConclusion.trim(),
  ]
  const done = checks.filter(Boolean).length
  return Math.round((done / checks.length) * 100)
}

/** 单工程风险标签 */
export function calcRiskFlags(r: H2ProjectReviewRecord): string[] {
  const flags: string[] = []
  if (r.transferRisk || (r.reachedUsableState === 'yes' && r.cipEnd > 0)) {
    flags.push('未转固')
  }
  if (r.isSuspended) flags.push('停工')
  if (r.isLongTermOutstanding === 'yes' || (r.noMovementYears != null && r.noMovementYears >= 1)) {
    flags.push('长期挂账')
  }
  if (r.hasRelatedParty === 'yes') flags.push('关联方')
  if (r.isRestricted === 'yes') flags.push('受限')
  if (r.hasImpairment === 'yes') flags.push('减值')
  if (r.cipEnd > 0 && r.cipIncrease === 0 && r.cipDecrease === 0) {
    if (!flags.includes('长期挂账')) flags.push('本期无发生')
  }
  return flags
}

function normalizeYearBalances(raw: unknown): H2YearBalanceRow[] {
  if (!Array.isArray(raw) || raw.length === 0) return emptyYearBalances()
  return raw.map((y: any) => ({
    rowId: y.rowId || _uid('yb'),
    yearLabel: String(y.yearLabel ?? ''),
    year: String(y.year ?? ''),
    begin: _num(y.begin),
    debit: _num(y.debit),
    credit: _num(y.credit),
    end: _num(y.end),
  }))
}

function normalizeRecord(raw: any): H2ProjectReviewRecord {
  const base = createEmptyRecord()
  if (!raw || typeof raw !== 'object') return base
  return {
    ...base,
    rowId: raw.rowId || base.rowId,
    projectName: String(raw.projectName ?? ''),
    subProjectName: String(raw.subProjectName ?? ''),
    sourceDetailRowId: String(raw.sourceDetailRowId ?? ''),
    projectDescription: String(raw.projectDescription ?? ''),
    docCheckIndex: String(raw.docCheckIndex ?? ''),
    docCheckNote: String(raw.docCheckNote ?? ''),
    contractCheckIndex: String(raw.contractCheckIndex ?? ''),
    contractCheckNote: String(raw.contractCheckNote ?? ''),
    yearBalances: normalizeYearBalances(raw.yearBalances),
    additionCheckIndex: String(raw.additionCheckIndex ?? 'H2-8'),
    additionCheckNote: String(raw.additionCheckNote ?? ''),
    interestCapIndex: String(raw.interestCapIndex ?? 'H2-10/H2-11'),
    interestCapNote: String(raw.interestCapNote ?? ''),
    assetExists: (['yes', 'no', 'na', ''].includes(raw.assetExists) ? raw.assetExists : '') as YesNoNa,
    assetExistsNote: String(raw.assetExistsNote ?? ''),
    statusDescription: String(raw.statusDescription ?? ''),
    reachedUsableState: (['yes', 'no', 'partial', ''].includes(raw.reachedUsableState)
      ? raw.reachedUsableState
      : '') as UsableState,
    isSuspended: !!raw.isSuspended,
    transferRisk: !!raw.transferRisk,
    isLongTermOutstanding: (['yes', 'no', 'na', ''].includes(raw.isLongTermOutstanding)
      ? raw.isLongTermOutstanding
      : '') as YesNoNa,
    longTermNote: String(raw.longTermNote ?? ''),
    noMovementYears: raw.noMovementYears == null || raw.noMovementYears === ''
      ? null
      : _num(raw.noMovementYears),
    hasRelatedParty: (['yes', 'no', 'na', ''].includes(raw.hasRelatedParty)
      ? raw.hasRelatedParty
      : '') as YesNoNa,
    relatedPartyNote: String(raw.relatedPartyNote ?? ''),
    relatedPartyIndex: String(raw.relatedPartyIndex ?? 'H2-17'),
    isRestricted: (['yes', 'no', 'na', ''].includes(raw.isRestricted) ? raw.isRestricted : '') as YesNoNa,
    restrictedNote: String(raw.restrictedNote ?? ''),
    hasImpairment: (['yes', 'no', 'na', ''].includes(raw.hasImpairment) ? raw.hasImpairment : '') as YesNoNa,
    impairmentIndex: String(raw.impairmentIndex ?? 'H2-15'),
    impairmentNote: String(raw.impairmentNote ?? ''),
    cipBegin: _num(raw.cipBegin),
    cipIncrease: _num(raw.cipIncrease),
    cipDecrease: _num(raw.cipDecrease),
    cipEnd: _num(raw.cipEnd),
    completionRate: raw.completionRate == null || raw.completionRate === ''
      ? null
      : _num(raw.completionRate),
    contractor: String(raw.contractor ?? ''),
    supervisor: String(raw.supervisor ?? ''),
    projectConclusion: String(raw.projectConclusion ?? ''),
    remark: String(raw.remark ?? ''),
  }
}

function _parseJsonFromMap(map: Map<string, any>, itemId: string): any {
  const item = map.get(itemId)
  if (!item) return null
  const raw = item.remark ?? item.conclusion
  if (!raw) return null
  if (typeof raw === 'object') return raw
  try { return JSON.parse(raw) } catch { return null }
}

function _normName(s: string): string {
  return String(s || '').trim().replace(/\s+/g, '').toLowerCase()
}

function _nameMatch(a: string, b: string): boolean {
  const na = _normName(a)
  const nb = _normName(b)
  if (!na || !nb) return false
  return na === nb || na.includes(nb) || nb.includes(na)
}

function _asBool(v: unknown): boolean {
  if (typeof v === 'boolean') return v
  if (v === '是' || v === 'true' || v === 1 || v === '1') return true
  return false
}

/** 从 allResponses 解析某工程的 H2-5 快照 */
export function pickH25Snapshot(map: Map<string, any>, projectName: string): H25ProjectSnapshot | null {
  const rows = _parseJsonFromMap(map, 'H2-5-rows')
  if (!Array.isArray(rows) || !projectName.trim()) return null
  const hit = rows.find((r: any) => _nameMatch(String(r.name ?? ''), projectName))
  if (!hit) return { found: false, name: projectName, allConditionsMet: false, condition5: false, transferDate: '', transferAmount: 0, timelyTransfer: null, delayDays: 0, difference: 0 }
  const condition5 = _asBool(hit.condition5)
  const allConditionsMet = hit.allConditionsMet != null
    ? _asBool(hit.allConditionsMet)
    : [_asBool(hit.condition1), _asBool(hit.condition2), _asBool(hit.condition3), _asBool(hit.condition4), condition5].every(Boolean)
  let timelyTransfer: boolean | null = null
  if (hit.timelyTransfer === true || hit.timelyTransfer === '是' || hit.timelyTransfer === 'true') timelyTransfer = true
  else if (hit.timelyTransfer === false || hit.timelyTransfer === '否' || hit.timelyTransfer === 'false') timelyTransfer = false
  else if (allConditionsMet && !String(hit.transferDate ?? '').trim()) timelyTransfer = false
  return {
    found: true,
    name: String(hit.name ?? projectName),
    allConditionsMet,
    condition5,
    transferDate: String(hit.transferDate ?? ''),
    transferAmount: _num(hit.transferAmount),
    timelyTransfer,
    delayDays: _num(hit.delayDays),
    difference: _num(hit.difference),
  }
}

/** 从 allResponses 解析某工程的 H2-13 快照（同名多行合并） */
export function pickH213Snapshot(map: Map<string, any>, projectName: string): H213ProjectSnapshot | null {
  const rows = _parseJsonFromMap(map, 'H2-13-rows')
  if (!Array.isArray(rows) || !projectName.trim()) return null
  const hits = rows.filter((r: any) => _nameMatch(String(r.name ?? r.projectName ?? ''), projectName))
  if (!hits.length) {
    return {
      found: false, name: projectName, readyForUse: '', constructionStatus: '',
      stopDuration: '', stopReason: '', progressDesc: '', result: '', visibleProgress: null, rowCount: 0,
    }
  }
  const readyYes = hits.some((r: any) => r.readyForUse === '是')
  const readyNo = hits.some((r: any) => r.readyForUse === '否')
  const stopped = hits.some((r: any) =>
    r.constructionStatus === '停工' || !!String(r.stopDuration ?? '').trim() || !!String(r.stopReason ?? '').trim(),
  )
  const finished = hits.some((r: any) => r.constructionStatus === '完工')
  const deficit = hits.find((r: any) => String(r.result ?? '').includes('盘亏'))
  const surplus = hits.find((r: any) => String(r.result ?? '').includes('盘盈'))
  const withProgress = hits.find((r: any) => String(r.progressDesc ?? '').trim())
  const withVis = hits.find((r: any) => r.visibleProgress != null && r.visibleProgress !== '')
  const withStop = hits.find((r: any) => String(r.stopDuration ?? '').trim() || String(r.stopReason ?? '').trim())
  let result = '账实相符'
  if (deficit) result = String(deficit.result)
  else if (surplus) result = String(surplus.result)
  else if (hits[0]?.result) result = String(hits[0].result)

  return {
    found: true,
    name: String(hits[0].name ?? hits[0].projectName ?? projectName),
    readyForUse: readyYes ? '是' : readyNo ? '否' : '',
    constructionStatus: stopped ? '停工' : finished ? '完工' : (hits[0].constructionStatus || '施工中'),
    stopDuration: String(withStop?.stopDuration ?? ''),
    stopReason: String(withStop?.stopReason ?? ''),
    progressDesc: String(withProgress?.progressDesc ?? ''),
    result,
    visibleProgress: withVis?.visibleProgress == null ? null : _num(withVis.visibleProgress),
    rowCount: hits.length,
  }
}

/**
 * H2-6 ↔ H2-5/H2-13 状态自动勾稽
 * - H2-13 达可用 / 停工 / 盘亏 与 H2-6 状态字段比对
 * - H2-5 五条件/转固时点与 H2-6 未转固风险比对
 */
export function reconcileProjectStatus(
  record: H2ProjectReviewRecord,
  map: Map<string, any>,
): ProjectReconcileResult {
  const h25 = pickH25Snapshot(map, record.projectName)
  const h213 = pickH213Snapshot(map, record.projectName)
  const issues: ReconcileIssue[] = []
  const suggestedPatch: Partial<H2ProjectReviewRecord> = {}

  if (!h25) {
    issues.push({ code: 'h25-missing-sheet', level: 'info', message: '未读取到 H2-5 转固检查数据', source: 'H2-5' })
  } else if (!h25.found) {
    issues.push({ code: 'h25-no-row', level: 'info', message: 'H2-5 无本工程行（可能尚未转固检查或未抽样）', source: 'H2-5' })
  } else {
    if (h25.condition5 || h25.allConditionsMet) {
      if (record.reachedUsableState === 'no') {
        issues.push({
          code: 'h25-usable-mismatch',
          level: 'error',
          message: `H2-5 判定已达可使用/五条件满足，但本表「达预定可用」为否`,
          source: '交叉',
        })
      } else if (record.reachedUsableState === '') {
        suggestedPatch.reachedUsableState = 'yes'
        issues.push({ code: 'h25-usable-suggest', level: 'warn', message: '建议按 H2-5 将「达预定可用」同步为「是」', source: 'H2-5' })
      }
    }
    const notTransferred = h25.allConditionsMet && !h25.transferDate && record.cipEnd > 0
    const delayed = h25.timelyTransfer === false
    if (notTransferred || delayed) {
      if (!record.transferRisk) {
        suggestedPatch.transferRisk = true
        issues.push({
          code: 'h25-transfer-risk',
          level: 'error',
          message: notTransferred
            ? 'H2-5：五条件已满足但无转固日期，且账面仍有余额 → 应标记未转固风险'
            : `H2-5：转固不及时（延迟 ${h25.delayDays} 天）→ 应关注未转固/延迟转固`,
          source: 'H2-5',
        })
      }
    }
    if (Math.abs(h25.difference) > 0.01) {
      issues.push({
        code: 'h25-amount-diff',
        level: 'warn',
        message: `H2-5 转固金额与 H1 入账差异 ${h25.difference.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
        source: 'H2-5',
      })
    }
  }

  if (!h213) {
    issues.push({ code: 'h213-missing-sheet', level: 'info', message: '未读取到 H2-13 盘点检查数据', source: 'H2-13' })
  } else if (!h213.found) {
    issues.push({ code: 'h213-no-row', level: 'info', message: 'H2-13 无本工程抽盘行（可能未纳入抽盘样本）', source: 'H2-13' })
  } else {
    if (h213.readyForUse === '是') {
      if (record.reachedUsableState === 'no') {
        issues.push({
          code: 'h213-usable-mismatch',
          level: 'error',
          message: 'H2-13 现场判断已达预定可使用状态，但本表为「否」',
          source: '交叉',
        })
      } else if (record.reachedUsableState === '' || record.reachedUsableState === 'partial') {
        suggestedPatch.reachedUsableState = 'yes'
        issues.push({ code: 'h213-usable-suggest', level: 'warn', message: '建议按 H2-13 将「达预定可用」同步为「是」', source: 'H2-13' })
      }
      if (record.cipEnd > 0 && !record.transferRisk) {
        suggestedPatch.transferRisk = true
        issues.push({
          code: 'h213-transfer-risk',
          level: 'warn',
          message: 'H2-13 已达可用且账面仍有余额 → 建议标记未转固风险（并核对 H2-5）',
          source: '交叉',
        })
      }
    } else if (h213.readyForUse === '否' && record.reachedUsableState === 'yes') {
      issues.push({
        code: 'h213-usable-conflict',
        level: 'error',
        message: 'H2-13 现场判断未达可使用，但本表为「是」——请核实',
        source: '交叉',
      })
    }

    if (h213.constructionStatus === '停工') {
      if (!record.isSuspended) {
        suggestedPatch.isSuspended = true
        issues.push({ code: 'h213-stop-suggest', level: 'warn', message: 'H2-13 为停工，建议本表勾选停工', source: 'H2-13' })
      }
      if (record.hasImpairment === '') {
        suggestedPatch.hasImpairment = 'yes'
        issues.push({ code: 'h213-impair-suggest', level: 'warn', message: '停工工程建议关注减值（→H2-15）', source: 'H2-13' })
      }
    }

    if (String(h213.result).includes('盘亏')) {
      if (record.assetExists === 'yes') {
        issues.push({
          code: 'h213-deficit-exists',
          level: 'error',
          message: 'H2-13 盘亏，但本表「是否存在」为是——请核实',
          source: '交叉',
        })
      } else if (record.assetExists === '') {
        suggestedPatch.assetExists = 'no'
        issues.push({ code: 'h213-deficit-suggest', level: 'warn', message: 'H2-13 盘亏，建议「是否存在」填否并说明', source: 'H2-13' })
      }
    } else if (String(h213.result).includes('相符') || h213.result === '账实相符') {
      if (record.assetExists === '') {
        suggestedPatch.assetExists = 'yes'
      }
    }

    // 现状描述空时，用 H2-13 进度/停工拼草稿
    if (!record.statusDescription.trim()) {
      const parts: string[] = []
      if (h213.progressDesc) parts.push(h213.progressDesc)
      if (h213.visibleProgress != null) parts.push(`形象进度约 ${h213.visibleProgress}%`)
      if (h213.constructionStatus === '停工') {
        parts.push(`停工${h213.stopDuration ? `（${h213.stopDuration}）` : ''}${h213.stopReason ? `：${h213.stopReason}` : ''}`)
      }
      if (h213.readyForUse) parts.push(`现场判断达预定可使用状态：${h213.readyForUse}`)
      if (parts.length) {
        suggestedPatch.statusDescription = parts.join('；')
        issues.push({ code: 'h213-status-fill', level: 'info', message: '可用 H2-13 进度/停工描述回填现状', source: 'H2-13' })
      }
    }

    if (!record.assetExistsNote.trim() && h213.found) {
      suggestedPatch.assetExistsNote = `H2-13 抽盘结果：${h213.result}（共 ${h213.rowCount} 行）`
    }
  }

  // H2-5 与 H2-13 交叉：一方达可用另一方否
  if (h25?.found && h213?.found) {
    if (h25.condition5 && h213.readyForUse === '否') {
      issues.push({
        code: 'h25-h213-usable-conflict',
        level: 'error',
        message: 'H2-5 条件5（可使用）与 H2-13 现场「未达可使用」冲突',
        source: '交叉',
      })
    }
    if (!h25.condition5 && !h25.allConditionsMet && h213.readyForUse === '是' && record.cipEnd > 0) {
      issues.push({
        code: 'h213-ahead-h25',
        level: 'warn',
        message: 'H2-13 已达可用，但 H2-5 尚未勾选可使用/五条件——请补做转固时点检查',
        source: '交叉',
      })
    }
  }

  return { h25, h213, issues, suggestedPatch }
}

/** 将勾稽建议合并进记录（状态类可覆盖；描述类仅填空） */
export function applyReconcileSuggestions(
  record: H2ProjectReviewRecord,
  result: ProjectReconcileResult,
): H2ProjectReviewRecord {
  const p = result.suggestedPatch
  const next = { ...record }
  if (p.reachedUsableState != null && (next.reachedUsableState === '' || next.reachedUsableState === 'partial')) {
    next.reachedUsableState = p.reachedUsableState
  }
  if (p.transferRisk === true) next.transferRisk = true
  if (p.isSuspended === true) next.isSuspended = true
  if (p.hasImpairment && next.hasImpairment === '') next.hasImpairment = p.hasImpairment
  if (p.assetExists && next.assetExists === '') next.assetExists = p.assetExists
  if (p.statusDescription && !next.statusDescription.trim()) next.statusDescription = p.statusDescription
  if (p.assetExistsNote && !next.assetExistsNote.trim()) next.assetExistsNote = p.assetExistsNote
  return applyLogicHints(next)
}

function _ynLabel(v: YesNoNa | UsableState, map: Record<string, string> = { yes: '是', no: '否', na: '不适用', partial: '部分' }): string {
  if (!v) return '未填'
  return map[v] || v
}

function _fmtAmt(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 一键生成本工程结论草稿（规则模板，含 H2-5/H2-13 勾稽摘要） */
export function buildProjectConclusionDraft(
  record: H2ProjectReviewRecord,
  reconcile?: ProjectReconcileResult | null,
): string {
  const name = record.projectName || '（未命名工程）'
  const sub = record.subProjectName ? `／${record.subProjectName}` : ''
  const flags = calcRiskFlags(record)
  const lines: string[] = [
    `【${name}${sub}】在建工程核查结论草稿`,
    `账面：期初 ${_fmtAmt(record.cipBegin)}，本期增加 ${_fmtAmt(record.cipIncrease)}，本期减少 ${_fmtAmt(record.cipDecrease)}，期末 ${_fmtAmt(record.cipEnd)}`
      + (record.completionRate != null ? `；完工进度约 ${record.completionRate.toFixed(1)}%` : '') + '。',
  ]

  if (record.projectDescription.trim()) {
    lines.push(`1. 项目概况：${record.projectDescription.trim()}`)
  }
  lines.push(
    `2. 资料/合同：资料索引 ${record.docCheckIndex || '—'}；合同索引 ${record.contractCheckIndex || '—'}。`,
  )
  const cur = record.yearBalances.find(y => y.yearLabel === '本年')
  if (cur) {
    lines.push(`3. 本年发生额：借方 ${_fmtAmt(cur.debit)}，贷方 ${_fmtAmt(cur.credit)}，期末 ${_fmtAmt(cur.end)}。`)
  }
  lines.push(`4. 本期发生额查验：见 ${record.additionCheckIndex || 'H2-8'}${record.additionCheckNote ? `。${record.additionCheckNote}` : '。'}`)
  lines.push(`5. 利息资本化：见 ${record.interestCapIndex || 'H2-10/H2-11'}${record.interestCapNote ? `。${record.interestCapNote}` : '。'}`)

  const statusParts = [
    `存在性 ${_ynLabel(record.assetExists)}`,
    `达预定可用 ${_ynLabel(record.reachedUsableState)}`,
    record.isSuspended ? '停工' : '未停工',
    record.transferRisk ? '存在未转固风险' : '未见未转固风险',
  ]
  lines.push(`6. 状态查验：${statusParts.join('；')}${record.statusDescription ? `。${record.statusDescription}` : '。'}`)

  if (reconcile?.h213?.found) {
    lines.push(
      `   （H2-13）抽盘 ${reconcile.h213.rowCount} 行，结果 ${reconcile.h213.result}；`
        + `达可用 ${reconcile.h213.readyForUse || '未填'}；施工状态 ${reconcile.h213.constructionStatus || '—'}。`,
    )
  } else {
    lines.push('   （H2-13）本工程未见抽盘记录或底稿未取数。')
  }
  if (reconcile?.h25?.found) {
    lines.push(
      `   （H2-5）五条件${reconcile.h25.allConditionsMet ? '已' : '未'}全部满足；`
        + `转固日 ${reconcile.h25.transferDate || '无'}；`
        + `及时转固 ${reconcile.h25.timelyTransfer == null ? '未判定' : reconcile.h25.timelyTransfer ? '是' : '否'}。`,
    )
  } else {
    lines.push('   （H2-5）本工程未见转固检查行或底稿未取数。')
  }

  lines.push(
    `7. 长期挂账：${_ynLabel(record.isLongTermOutstanding)}`
      + (record.noMovementYears != null ? `（无发生约 ${record.noMovementYears} 年）` : '')
      + (record.longTermNote ? `。${record.longTermNote}` : '。'),
  )
  lines.push(
    `8. 关联方：${_ynLabel(record.hasRelatedParty, { yes: '有', no: '无', na: '不适用' })}`
      + (record.relatedPartyNote ? `。${record.relatedPartyNote}` : '。'),
  )
  lines.push(
    `9. 受限 ${_ynLabel(record.isRestricted)}；减值 ${_ynLabel(record.hasImpairment)}`
      + (record.impairmentNote ? `。${record.impairmentNote}` : '。'),
  )

  const errs = (reconcile?.issues || []).filter(i => i.level === 'error')
  const warns = (reconcile?.issues || []).filter(i => i.level === 'warn')
  if (errs.length || warns.length) {
    lines.push('【勾稽关注】')
    for (const i of [...errs, ...warns]) {
      lines.push(`- [${i.source}/${i.level === 'error' ? '差异' : '提示'}] ${i.message}`)
    }
  }

  if (flags.length) {
    lines.push(`风险标记：${flags.join('、')}。`)
  }

  if (errs.length) {
    lines.push('审计意见草稿：本工程存在与 H2-5/H2-13 的状态勾稽差异或未转固/账实异常，建议完成差异核实及必要调整/披露后再定稿。')
  } else if (flags.includes('未转固') || flags.includes('停工') || flags.includes('长期挂账') || flags.includes('减值')) {
    lines.push('审计意见草稿：本工程存在未转固/停工/长期挂账/减值等关注事项，已索引相关底稿；除上述事项外，其余认定在所有重大方面可接受。')
  } else {
    lines.push('审计意见草稿：经核查，本工程在建工程的存在性、完整性与计价在所有重大方面公允；状态与 H2-5/H2-13 未见重大勾稽差异。')
  }

  return lines.join('\n')
}

/** 根据账面发生额自动建议长期挂账 / 转固风险 */
export function applyLogicHints(r: H2ProjectReviewRecord): H2ProjectReviewRecord {
  const next = { ...r }
  // 本期无借/贷且期末有余额 → 建议关注长期挂账
  if (next.cipEnd > 0 && next.cipIncrease === 0 && next.cipDecrease === 0) {
    if (next.isLongTermOutstanding === '') next.isLongTermOutstanding = 'yes'
    if (next.noMovementYears == null) next.noMovementYears = 1
  }
  // 达预定可使用且仍有余额 → 转固风险
  if (next.reachedUsableState === 'yes' && next.cipEnd > 0) {
    next.transferRisk = true
  }
  // 停工 → 关注减值
  if (next.isSuspended && next.hasImpairment === '') {
    next.hasImpairment = 'yes'
  }
  return next
}

function recalcYearTotal(balances: H2YearBalanceRow[]): H2YearBalanceRow[] {
  const rows = balances.map(b => ({ ...b }))
  const totalIdx = rows.findIndex(r => r.yearLabel === '合计')
  if (totalIdx < 0) return rows
  const others = rows.filter((_, i) => i !== totalIdx)
  const total = rows[totalIdx]
  // 合计：借方/贷方求和；期初取开工年度；期末取本年（或最后非合计行）
  total.debit = others.reduce((s, r) => s + r.debit, 0)
  total.credit = others.reduce((s, r) => s + r.credit, 0)
  const start = others.find(r => r.yearLabel === '开工年度') || others[0]
  const current = others.find(r => r.yearLabel === '本年') || others[others.length - 1]
  total.begin = start?.begin ?? 0
  total.end = current?.end ?? 0
  return rows
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2ReviewRecord(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  const records = ref<H2ProjectReviewRecord[]>([])
  const signature = ref<H2ReviewSignature>({
    preparedBy: '',
    preparedDate: '',
    reviewedBy: '',
    reviewedDate: '',
  })
  const conclusion = ref('')
  const auditNote = ref('')
  const filterRisk = ref('')
  const filterKeyword = ref('')

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function initFromAllResponses(): void {
    const raw = _getJson(RECORDS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      records.value = raw.map(normalizeRecord)
    } else {
      // 兼容旧版：basicInfo + reviewItems → 尽量迁移为一条记录
      const bi = _getJson(LEGACY_BASIC_KEY)
      const items = _getJson(LEGACY_ITEMS_KEY)
      if (bi || (Array.isArray(items) && items.length)) {
        const migrated = createEmptyRecord({
          projectName: bi?.projectName ?? '',
          contractor: bi?.constructionUnit ?? '',
          supervisor: bi?.supervisorUnit ?? '',
          projectDescription: Array.isArray(items)
            ? items.map((it: any) => `${it.subject || ''}：${it.opinion || it.content || ''}`).join('\n')
            : '',
        })
        records.value = [migrated]
      } else {
        records.value = []
      }
    }

    const sig = _getJson(SIGNATURE_KEY)
    if (sig && typeof sig === 'object') {
      signature.value = {
        preparedBy: sig.preparedBy ?? '',
        preparedDate: sig.preparedDate ?? '',
        reviewedBy: sig.reviewedBy ?? '',
        reviewedDate: sig.reviewedDate ?? '',
      }
    }

    conclusion.value = _getString(CONCLUSION_KEY)
    const noteRaw = options.allResponses.value.get(NOTE_KEY)
    auditNote.value = (noteRaw?.remark ?? noteRaw?.conclusion ?? '') as string
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  /** H2-2 工程列表（含账面数） */
  const detailProjects = computed(() => {
    const resp = options.allResponses.value.get('H2-2-rows')
    const raw = resp?.remark ?? resp?.conclusion
    if (!raw) return [] as Array<{
      rowId: string
      name: string
      cipBegin: number
      cipIncrease: number
      cipDecrease: number
      cipEnd: number
      completionRate: number | null
      contractor: string
      supervisor: string
    }>
    try {
      const rows = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (!Array.isArray(rows)) return []
      return rows
        .filter((r: any) => r?.name)
        .map((r: any) => ({
          rowId: String(r.rowId ?? ''),
          name: String(r.name ?? ''),
          cipBegin: _num(r.cipBegin ?? r.beginAudited),
          cipIncrease: _num(r.increaseTotal),
          cipDecrease: _num(r.decrease) + _num(r.transferAmount) + _num(r.transferOut),
          cipEnd: _num(r.cipEnd ?? r.endAudited),
          completionRate: r.completionRate == null || r.completionRate === ''
            ? null
            : _num(r.completionRate),
          contractor: String(r.contractor ?? ''),
          supervisor: String(r.supervisor ?? ''),
        }))
    } catch {
      return []
    }
  })

  const projectList: ComputedRef<string[]> = computed(() =>
    detailProjects.value.map(p => p.name),
  )

  const filteredRecords: ComputedRef<H2ProjectReviewRecord[]> = computed(() => {
    let list = records.value
    const kw = filterKeyword.value.trim()
    if (kw) {
      list = list.filter(r =>
        r.projectName.includes(kw)
        || r.subProjectName.includes(kw)
        || r.projectDescription.includes(kw),
      )
    }
    const risk = filterRisk.value
    if (risk) {
      list = list.filter(r => calcRiskFlags(r).includes(risk))
    }
    return list
  })

  const riskSummary: ComputedRef<H2ReviewRiskSummary> = computed(() => {
    const list = records.value
    return {
      total: list.length,
      filled: list.filter(r => calcFillProgress(r) >= 80).length,
      transferRisk: list.filter(r => calcRiskFlags(r).includes('未转固')).length,
      longTerm: list.filter(r => calcRiskFlags(r).includes('长期挂账') || calcRiskFlags(r).includes('本期无发生')).length,
      relatedParty: list.filter(r => calcRiskFlags(r).includes('关联方')).length,
      impairment: list.filter(r => calcRiskFlags(r).includes('减值')).length,
      suspended: list.filter(r => calcRiskFlags(r).includes('停工')).length,
    }
  })

  function _persistRecords(): void {
    if (!options.onSave) return
    options.onSave(RECORDS_KEY, records.value)
  }

  function addRecord(partial?: Partial<H2ProjectReviewRecord>): H2ProjectReviewRecord {
    if (options.isReadonly.value) return createEmptyRecord()
    const rec = createEmptyRecord(partial)
    records.value.push(rec)
    _persistRecords()
    return rec
  }

  function removeRecord(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = records.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      records.value.splice(idx, 1)
      _persistRecords()
    }
  }

  function updateRecord(rowId: string, patch: Partial<H2ProjectReviewRecord>): void {
    if (options.isReadonly.value) return
    const idx = records.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    let next = normalizeRecord({ ...records.value[idx], ...patch, rowId })
    if (patch.yearBalances) {
      next.yearBalances = recalcYearTotal(normalizeYearBalances(patch.yearBalances))
    }
    next = applyLogicHints(next)
    records.value[idx] = next
    _persistRecords()
  }

  /** 弹窗整单回写 */
  function saveRecordDraft(draft: H2ProjectReviewRecord): void {
    if (options.isReadonly.value) return
    let next = applyLogicHints(normalizeRecord(draft))
    next.yearBalances = recalcYearTotal(next.yearBalances)
    const idx = records.value.findIndex(r => r.rowId === next.rowId)
    if (idx === -1) {
      records.value.push(next)
    } else {
      records.value[idx] = next
    }
    _persistRecords()
  }

  /** 从 H2-2 同步：已有工程更新账面快照；新增工程补行 */
  function syncFromH22(): { added: number; updated: number } {
    if (options.isReadonly.value) return { added: 0, updated: 0 }
    let added = 0
    let updated = 0
    for (const p of detailProjects.value) {
      const exist = records.value.find(
        r => r.sourceDetailRowId === p.rowId || r.projectName === p.name,
      )
      if (exist) {
        const yb = [...exist.yearBalances]
        const cur = yb.find(y => y.yearLabel === '本年')
        if (cur) {
          cur.begin = p.cipBegin
          cur.debit = p.cipIncrease
          cur.credit = p.cipDecrease
          cur.end = p.cipEnd
        }
        updateRecord(exist.rowId, {
          sourceDetailRowId: p.rowId || exist.sourceDetailRowId,
          projectName: p.name,
          cipBegin: p.cipBegin,
          cipIncrease: p.cipIncrease,
          cipDecrease: p.cipDecrease,
          cipEnd: p.cipEnd,
          completionRate: p.completionRate,
          contractor: p.contractor || exist.contractor,
          supervisor: p.supervisor || exist.supervisor,
          yearBalances: recalcYearTotal(yb),
        })
        updated++
      } else {
        const yb = emptyYearBalances()
        const cur = yb.find(y => y.yearLabel === '本年')!
        cur.begin = p.cipBegin
        cur.debit = p.cipIncrease
        cur.credit = p.cipDecrease
        cur.end = p.cipEnd
        const rec = createEmptyRecord({
          projectName: p.name,
          sourceDetailRowId: p.rowId,
          cipBegin: p.cipBegin,
          cipIncrease: p.cipIncrease,
          cipDecrease: p.cipDecrease,
          cipEnd: p.cipEnd,
          completionRate: p.completionRate,
          contractor: p.contractor,
          supervisor: p.supervisor,
          yearBalances: recalcYearTotal(yb),
          isLongTermOutstanding: p.cipEnd > 0 && p.cipIncrease === 0 && p.cipDecrease === 0 ? 'yes' : '',
          noMovementYears: p.cipEnd > 0 && p.cipIncrease === 0 && p.cipDecrease === 0 ? 1 : null,
        })
        records.value.push(rec)
        added++
      }
    }
    if (added || updated) _persistRecords()
    return { added, updated }
  }

  function saveConclusion(text: string): void {
    conclusion.value = text
    options.onSave?.(CONCLUSION_KEY, text)
  }

  function saveAuditNote(text: string): void {
    auditNote.value = text
    options.onSave?.(NOTE_KEY, text)
  }

  function saveSignature(sig: Partial<H2ReviewSignature>): void {
    if (options.isReadonly.value) return
    Object.assign(signature.value, sig)
    options.onSave?.(SIGNATURE_KEY, signature.value)
  }

  function setFilterRisk(v: string): void {
    filterRisk.value = v
  }

  function setFilterKeyword(v: string): void {
    filterKeyword.value = v
  }

  /** 单工程与 H2-5/H2-13 勾稽 */
  function reconcileRecord(record: H2ProjectReviewRecord): ProjectReconcileResult {
    return reconcileProjectStatus(record, options.allResponses.value)
  }

  return {
    records,
    signature,
    conclusion,
    auditNote,
    filterRisk,
    filterKeyword,
    projectList,
    detailProjects,
    filteredRecords,
    riskSummary,
    addRecord,
    removeRecord,
    updateRecord,
    saveRecordDraft,
    syncFromH22,
    saveConclusion,
    saveAuditNote,
    saveSignature,
    setFilterRisk,
    setFilterKeyword,
    reconcileRecord,
    initFromAllResponses,
    // 兼容旧调用方（已废弃字段）
    basicInfo: computed(() => ({
      projectName: records.value[0]?.projectName ?? '',
      projectLocation: '',
      constructionUnit: records.value[0]?.contractor ?? '',
      supervisorUnit: records.value[0]?.supervisor ?? '',
      contractAmount: 0,
      reviewDate: signature.value.preparedDate,
      reviewer: signature.value.preparedBy,
    })),
    reviewItems: computed(() => [] as any[]),
    filteredItems: computed(() => [] as any[]),
    abnormalCount: computed(() => riskSummary.value.transferRisk + riskSummary.value.longTerm),
    filterProject: filterKeyword,
    setFilterProject: setFilterKeyword,
    updateBasicInfo: () => {},
    addReviewItem: () => {},
    removeReviewItem: () => {},
    updateReviewItem: () => {},
  }
}

export default useH2ReviewRecord
