/**
 * useH2DecreaseCheck — H2-9 在建工程减少检查 composable
 *
 * 对齐致同模板「在建工程减少检查表」编制逻辑：
 * 一、审计目标 → 二、样本选取 → 三、测试（转入固定资产 / 其他减少 + 审批/验收关键证据）
 * → 检查比例（勾稽 H2-2）→ 四、审计说明 → 五、审计结论 → 提示（暂估转固/延迟转固）
 *
 * 增强：验收 vs 转固差异、证据缺口校验、暂估决算 AJE 推送 H2-3（重复推送替换旧草稿）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH2FormulaEngine'
import {
  H23_ROWS_KEY,
  H29_EVIDENCE_GAP_MARKER,
  buildEvidenceGapH23Row,
  collectDecreaseEvidenceGaps,
  mergeEvidenceGapRowsToH23,
} from './h2EvidenceGapPush'

// ─── Types ───────────────────────────────────────────────────────────────────

export type H2DecreaseType =
  | '转入固定资产'
  | '报废'
  | '毁损'
  | '出售'
  | '其他'
  | ''

export interface H2DecreaseRowFlags {
  rowId: string
  name: string
  /** 验收金额 − 转入固定资产金额 */
  acceptanceDiff: number
  hasAcceptanceDiff: boolean
  missingApproval: boolean
  missingStamps: boolean
  highInterestRatio: boolean
  provisionalNeedsSettlement: boolean
  messages: string[]
}

export interface H2DecreaseRow {
  rowId: string
  seq: number
  name: string
  decreaseDate: string
  voucherNo: string
  decreaseType: H2DecreaseType
  transferToFaAmount: number
  transferInterestCap: number
  otherDecreaseAmount: number
  otherInterestCap: number
  approvalRef: string
  isApproved: string
  acceptanceDate: string
  acceptanceAmount: number
  stampEngineering: string
  stampContractor: string
  stampSupervisor: string
  otherEvidence: string
  queryNo: string
  isAbnormal: string
  isProvisional: string
  isRelatedParty: string
  relatedPartyName: string
  relationship: string
  disposalIncome: number
  auditConclusion: string
  indexRef: string
  samplingStatus: '待检查' | '已检查' | '已确认' | ''
  remark: string
}

export interface H2DecreaseSamplingParams {
  populationAmount: number
  transferPopulation: number
  otherPopulation: number
  samplingMethod: string
  sampleSize: number
  coverageRate: number
  materialityLevel: number
  specificSampleNote: string
}

export interface LinkedDecreaseTotal {
  amount: number
  transfer: number
  other: number
  source: 'H2-2' | ''
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-9-rows'
const PARAMS_KEY = 'H2-9-sampling-params'
const NOTE_KEY = 'H2-9-audit-note'
const CONCLUSION_KEY = 'H2-9-audit-conclusion'
const DETAIL_ROWS_KEY = 'H2-2-rows'

/** H2-3 自动草稿标记（重复推送时先清理） */
export const H29_AJE_MARKER = 'H2-9-aje-auto'

const ACCEPTANCE_DIFF_FLOOR = 100
const INTEREST_RATIO_WARN = 0.5

// ─── Pure helpers（导出供单测） ──────────────────────────────────────────────

function _rowDecreaseTotal(row: Pick<H2DecreaseRow, 'transferToFaAmount' | 'otherDecreaseAmount'>): number {
  return (Number(row.transferToFaAmount) || 0) + (Number(row.otherDecreaseAmount) || 0)
}

export function calcAcceptanceDiff(row: Pick<H2DecreaseRow, 'acceptanceAmount' | 'transferToFaAmount'>): number {
  const acc = Number(row.acceptanceAmount) || 0
  const fa = Number(row.transferToFaAmount) || 0
  if (acc <= 0 || fa <= 0) return 0
  return Math.round((acc - fa) * 100) / 100
}

export function isMaterialAcceptanceDiff(diff: number, materialityLevel: number): boolean {
  const abs = Math.abs(diff)
  if (abs < 0.01) return false
  const threshold = materialityLevel > 0
    ? Math.max(materialityLevel * 0.01, ACCEPTANCE_DIFF_FLOOR)
    : ACCEPTANCE_DIFF_FLOOR
  return abs >= threshold
}

export function evaluateRowFlags(row: H2DecreaseRow, materialityLevel: number): H2DecreaseRowFlags {
  const transfer = Number(row.transferToFaAmount) || 0
  const acceptanceDiff = calcAcceptanceDiff(row)
  const hasAcceptanceDiff = isMaterialAcceptanceDiff(acceptanceDiff, materialityLevel)
  const missingApproval = transfer > 0 && row.isApproved !== '是'
  const missingStamps = transfer > 0 && (
    row.stampEngineering !== '是'
    || row.stampContractor !== '是'
    || row.stampSupervisor !== '是'
  )
  const interest = Number(row.transferInterestCap) || 0
  const highInterestRatio = transfer > 0 && interest / transfer > INTEREST_RATIO_WARN
  const provisionalNeedsSettlement =
    row.isProvisional === '是'
    && transfer > 0
    && (Number(row.acceptanceAmount) || 0) > 0
    && Math.abs(acceptanceDiff) >= 0.01

  const messages: string[] = []
  if (hasAcceptanceDiff || provisionalNeedsSettlement) {
    messages.push(`验收与转固差异 ${acceptanceDiff.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`)
  }
  if (missingApproval) messages.push('审批未确认恰当')
  if (missingStamps) messages.push('验收盖章不全')
  if (highInterestRatio) messages.push('利息资本化占比偏高')
  if (provisionalNeedsSettlement) messages.push('暂估转固可按决算差额调整成本')

  return {
    rowId: row.rowId,
    name: row.name,
    acceptanceDiff,
    hasAcceptanceDiff,
    missingApproval,
    missingStamps,
    highInterestRatio,
    provisionalNeedsSettlement,
    messages,
  }
}

/**
 * 暂估决算 / 验收差异调整分录草稿（不调已提折旧）：
 * 差额>0：借固定资产 / 贷在建工程
 * 差额<0：借在建工程 / 贷固定资产
 */
export function buildSettlementAjePair(opts: {
  projectName: string
  diff: number
  seqStart: number
  kind: 'provisional' | 'acceptance'
}): Array<{
  rowId: string
  seq: number
  description: string
  category: '账项调整'
  entryType: 'AJE'
  reportItem: string
  accountCode: string
  accountName: string
  summary: string
  debit: number
  credit: number
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}> {
  const diff = Math.round(opts.diff * 100) / 100
  if (Math.abs(diff) < 0.01) return []
  const name = opts.projectName.trim() || '在建工程'
  const abs = Math.abs(diff)
  const isUp = diff > 0
  const kindLabel = opts.kind === 'provisional' ? '暂估转固决算调整' : '验收与转固差异调整'
  const desc = `${kindLabel}-${name}（差额${diff.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，不调折旧）`
  const baseId = `h29-aje-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  const codeA = isUp ? '1601' : '1604'
  const codeB = isUp ? '1604' : '1601'
  const nameA = isUp ? '固定资产' : '在建工程'
  const nameB = isUp ? '在建工程' : '固定资产'
  const reportA = isUp ? '固定资产' : '在建工程'
  const reportB = isUp ? '在建工程' : '固定资产'
  return [
    {
      rowId: `${baseId}-a`,
      seq: opts.seqStart,
      description: desc,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: reportA,
      accountCode: codeA,
      accountName: nameA,
      summary: desc,
      debit: abs,
      credit: 0,
      debitAmount: abs,
      creditAmount: 0,
      indexRef: 'H2-9',
      remark: H29_AJE_MARKER,
    },
    {
      rowId: `${baseId}-b`,
      seq: opts.seqStart + 1,
      description: desc,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: reportB,
      accountCode: codeB,
      accountName: nameB,
      summary: desc,
      debit: 0,
      credit: abs,
      debitAmount: 0,
      creditAmount: abs,
      indexRef: 'H2-9',
      remark: H29_AJE_MARKER,
    },
  ]
}

function _migrateLegacyFields(r: any): Partial<H2DecreaseRow> {
  const hasNew =
    r.transferToFaAmount != null
    || r.otherDecreaseAmount != null
    || r.voucherNo != null
    || r.approvalRef != null
  if (hasNew) return {}

  const original = Number(r.originalValue) || 0
  const reason = String(r.decreaseReason ?? '')
  const isTransfer = reason === '转出' || reason === '转入固定资产'
  return {
    decreaseType: (isTransfer
      ? '转入固定资产'
      : reason === '报废' || reason === '毁损' || reason === '出售'
        ? reason
        : reason
          ? '其他'
          : '') as H2DecreaseType,
    transferToFaAmount: isTransfer ? original : 0,
    otherDecreaseAmount: !isTransfer && original ? original : 0,
    approvalRef: r.approvalDoc ?? '',
    isApproved: r.approvalDoc ? '是' : '',
    disposalIncome: Number(r.disposalIncome) || 0,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2DecreaseCheck(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  const rows = ref<H2DecreaseRow[]>([])
  const samplingParams = ref<H2DecreaseSamplingParams>({
    populationAmount: 0,
    transferPopulation: 0,
    otherPopulation: 0,
    samplingMethod: '货币单元抽样',
    sampleSize: 0,
    coverageRate: 0,
    materialityLevel: 0,
    specificSampleNote: '',
  })
  const auditNote = ref('')
  const auditConclusion = ref('')
  const populationManual = ref(false)

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(r: any, idx: number): H2DecreaseRow {
    const legacy = _migrateLegacyFields(r)
    return {
      rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: r.seq ?? (idx + 1),
      name: r.name ?? '',
      decreaseDate: r.decreaseDate ?? '',
      voucherNo: r.voucherNo ?? '',
      decreaseType: (legacy.decreaseType ?? r.decreaseType ?? '') as H2DecreaseType,
      transferToFaAmount: Number(legacy.transferToFaAmount ?? r.transferToFaAmount) || 0,
      transferInterestCap: Number(r.transferInterestCap) || 0,
      otherDecreaseAmount: Number(legacy.otherDecreaseAmount ?? r.otherDecreaseAmount) || 0,
      otherInterestCap: Number(r.otherInterestCap) || 0,
      approvalRef: String(legacy.approvalRef ?? r.approvalRef ?? r.approvalDoc ?? ''),
      isApproved: String(legacy.isApproved ?? r.isApproved ?? ''),
      acceptanceDate: r.acceptanceDate ?? '',
      acceptanceAmount: Number(r.acceptanceAmount) || 0,
      stampEngineering: r.stampEngineering ?? '',
      stampContractor: r.stampContractor ?? '',
      stampSupervisor: r.stampSupervisor ?? '',
      otherEvidence: r.otherEvidence ?? '',
      queryNo: r.queryNo ?? '',
      isAbnormal: r.isAbnormal ?? '',
      isProvisional: r.isProvisional ?? '',
      isRelatedParty: r.isRelatedParty ?? '',
      relatedPartyName: r.relatedPartyName ?? '',
      relationship: r.relationship ?? '',
      disposalIncome: Number(legacy.disposalIncome ?? r.disposalIncome) || 0,
      auditConclusion: r.auditConclusion ?? '',
      indexRef: r.indexRef ?? '',
      samplingStatus: r.samplingStatus ?? '',
      remark: r.remark ?? '',
    }
  }

  const linkedDecrease: ComputedRef<LinkedDecreaseTotal> = computed(() => {
    const data = _getJson(DETAIL_ROWS_KEY)
    if (!Array.isArray(data) || data.length === 0) {
      return { amount: 0, transfer: 0, other: 0, source: '' }
    }
    let transfer = 0
    let other = 0
    for (const r of data) {
      transfer += Number(r.transferAmount) || 0
      other += Number(r.decrease) || Number(r.transferOut) || 0
    }
    const amount = transfer + other
    return amount > 0 || transfer > 0 || other > 0
      ? { amount, transfer, other, source: 'H2-2' as const }
      : { amount: 0, transfer: 0, other: 0, source: '' }
  })

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    rows.value = Array.isArray(data) && data.length > 0 ? data.map(_normalizeRow) : []

    const params = _getJson(PARAMS_KEY)
    if (params && typeof params === 'object') {
      samplingParams.value = {
        populationAmount: Number(params.populationAmount) || 0,
        transferPopulation: Number(params.transferPopulation) || 0,
        otherPopulation: Number(params.otherPopulation) || 0,
        samplingMethod: params.samplingMethod ?? '货币单元抽样',
        sampleSize: Number(params.sampleSize) || 0,
        coverageRate: Number(params.coverageRate) || 0,
        materialityLevel: Number(params.materialityLevel) || 0,
        specificSampleNote: params.specificSampleNote ?? '',
      }
      populationManual.value = Boolean(params.populationManual)
    }

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  const transferSampleTotal = computed(() => calcSubtotal(rows.value.map(r => r.transferToFaAmount)))
  const otherSampleTotal = computed(() => calcSubtotal(rows.value.map(r => r.otherDecreaseAmount)))
  const sampleTotal = computed(() => transferSampleTotal.value + otherSampleTotal.value)
  const interestCapSampleTotal = computed(() =>
    calcSubtotal(rows.value.map(r => (Number(r.transferInterestCap) || 0) + (Number(r.otherInterestCap) || 0))),
  )

  const coverageRate = computed(() => {
    const pop = samplingParams.value.populationAmount
    if (!pop || pop <= 0) return 0
    return (sampleTotal.value / pop) * 100
  })
  const transferCoverageRate = computed(() => {
    const pop = samplingParams.value.transferPopulation
    if (!pop || pop <= 0) return 0
    return (transferSampleTotal.value / pop) * 100
  })
  const otherCoverageRate = computed(() => {
    const pop = samplingParams.value.otherPopulation
    if (!pop || pop <= 0) return 0
    return (otherSampleTotal.value / pop) * 100
  })

  const anomalyCount = computed(() =>
    rows.value.filter(r => r.isAbnormal === '是' || r.auditConclusion === '需调整' || r.auditConclusion === '存疑').length,
  )
  const provisionalCount = computed(() => rows.value.filter(r => r.isProvisional === '是').length)

  const rowFlags = computed(() =>
    rows.value.map(r => evaluateRowFlags(r, samplingParams.value.materialityLevel)),
  )
  const rowFlagsMap = computed(() => {
    const m = new Map<string, H2DecreaseRowFlags>()
    for (const f of rowFlags.value) m.set(f.rowId, f)
    return m
  })
  const acceptanceDiffCount = computed(() =>
    rowFlags.value.filter(f => f.hasAcceptanceDiff || f.provisionalNeedsSettlement).length,
  )
  const evidenceGapCount = computed(() =>
    rowFlags.value.filter(f => f.missingApproval || f.missingStamps).length,
  )

  const pushableSettlementRows = computed(() => {
    const out: Array<{ row: H2DecreaseRow; flags: H2DecreaseRowFlags }> = []
    for (const row of rows.value) {
      const flags = rowFlagsMap.value.get(row.rowId)
      if (!flags) continue
      if (flags.provisionalNeedsSettlement || flags.hasAcceptanceDiff) {
        out.push({ row, flags })
      }
    }
    return out
  })
  const pushableSettlementAmount = computed(() =>
    pushableSettlementRows.value.reduce((s, x) => s + Math.abs(x.flags.acceptanceDiff), 0),
  )

  const pushableEvidenceGapRows = computed(() => {
    const out: Array<{ row: H2DecreaseRow; flags: H2DecreaseRowFlags; gaps: string[] }> = []
    for (const row of rows.value) {
      const flags = rowFlagsMap.value.get(row.rowId)
      if (!flags) continue
      const gaps = collectDecreaseEvidenceGaps(flags)
      if (gaps.length > 0) out.push({ row, flags, gaps })
    }
    return out
  })

  const typeStats = computed(() => {
    const stats: Record<string, { count: number; amount: number }> = {}
    for (const row of rows.value) {
      const key = row.decreaseType || (row.transferToFaAmount > 0 ? '转入固定资产' : '其他减少')
      if (!stats[key]) stats[key] = { count: 0, amount: 0 }
      stats[key].count++
      stats[key].amount += _rowDecreaseTotal(row)
    }
    return stats
  })

  const summary = computed(() => ({
    totalRows: rows.value.length,
    sampleTotal: sampleTotal.value,
    transferSampleTotal: transferSampleTotal.value,
    otherSampleTotal: otherSampleTotal.value,
    interestCapSampleTotal: interestCapSampleTotal.value,
    coverageRate: coverageRate.value,
    transferCoverageRate: transferCoverageRate.value,
    otherCoverageRate: otherCoverageRate.value,
    anomalyCount: anomalyCount.value,
    provisionalCount: provisionalCount.value,
    acceptanceDiffCount: acceptanceDiffCount.value,
    evidenceGapCount: evidenceGapCount.value,
    pushableSettlementAmount: pushableSettlementAmount.value,
    populationAmount: samplingParams.value.populationAmount,
  }))

  const originalTotal = sampleTotal
  const lossTotal = computed(() => 0)
  const netLossTotal = computed(() => 0)
  const reasonStats = typeStats

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value.push(_normalizeRow({}, rows.value.length))
    _persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      rows.value.splice(idx, 1)
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      _persist()
    }
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const numFields = [
      'transferToFaAmount', 'transferInterestCap',
      'otherDecreaseAmount', 'otherInterestCap',
      'acceptanceAmount', 'disposalIncome',
    ]
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    if (row.transferInterestCap > row.transferToFaAmount) {
      row.transferInterestCap = row.transferToFaAmount
    }
    if (row.otherInterestCap > row.otherDecreaseAmount) {
      row.otherInterestCap = row.otherDecreaseAmount
    }
    _persist()
  }

  function fillSamplingResults(samples: Array<{ rowId: string; status: string }>): void {
    for (const s of samples) {
      const row = rows.value.find(r => r.rowId === s.rowId)
      if (row) row.samplingStatus = s.status as H2DecreaseRow['samplingStatus']
    }
    samplingParams.value.sampleSize = rows.value.length
    options.onSave?.(PARAMS_KEY, {
      ...samplingParams.value,
      populationManual: populationManual.value,
      coverageRate: coverageRate.value,
      sampleSize: rows.value.length,
    })
    _persist()
  }

  function updateSamplingParams(params: Partial<H2DecreaseSamplingParams & { populationManual?: boolean }>): void {
    if (options.isReadonly.value) return
    if (params.populationAmount != null || params.transferPopulation != null || params.otherPopulation != null) {
      populationManual.value = true
    }
    if (params.populationManual != null) populationManual.value = params.populationManual
    Object.assign(samplingParams.value, params)
    options.onSave?.(PARAMS_KEY, {
      ...samplingParams.value,
      populationManual: populationManual.value,
      coverageRate: coverageRate.value,
    })
  }

  function syncPopulationFromH22(): boolean {
    if (options.isReadonly.value) return false
    const linked = linkedDecrease.value
    if (!linked.source || linked.amount <= 0) return false
    populationManual.value = false
    samplingParams.value.populationAmount = linked.amount
    samplingParams.value.transferPopulation = linked.transfer
    samplingParams.value.otherPopulation = linked.other
    options.onSave?.(PARAMS_KEY, {
      ...samplingParams.value,
      populationManual: false,
      coverageRate: coverageRate.value,
    })
    return true
  }

  /**
   * 将验收差异/暂估决算差额推送为 H2-3 AJE 草稿。
   * 重复推送会先清理旧自动草稿（remark=H2-9-aje-auto）。
   */
  function pushSettlementAjeToH23(): {
    ok: boolean
    added: number
    amount: number
    message: string
  } {
    if (options.isReadonly.value) {
      return { ok: false, added: 0, amount: 0, message: '只读模式' }
    }
    const toPush = pushableSettlementRows.value
    if (toPush.length === 0) {
      return {
        ok: false,
        added: 0,
        amount: 0,
        message: '无可推送项：请填写验收金额且与转固金额存在差异（暂估转固或超阈值差异）',
      }
    }

    let existing: any[] = []
    const raw = _getJson(H23_ROWS_KEY)
    if (Array.isArray(raw)) existing = raw
    existing = existing.filter((r: any) => r?.remark !== H29_AJE_MARKER)

    let seq = existing.reduce((m: number, r: any) => Math.max(m, Number(r.seq) || 0), 0) + 1
    const newRows: any[] = []
    for (const { row, flags } of toPush) {
      const kind = row.isProvisional === '是' ? 'provisional' as const : 'acceptance' as const
      const pair = buildSettlementAjePair({
        projectName: row.name,
        diff: flags.acceptanceDiff,
        seqStart: seq,
        kind,
      })
      newRows.push(...pair)
      seq += pair.length
      if (!row.auditConclusion || row.auditConclusion === '无异常') {
        row.auditConclusion = '需调整'
      }
      if (row.isAbnormal !== '是') row.isAbnormal = '是'
    }

    options.onSave?.(H23_ROWS_KEY, [...existing, ...newRows].map((r, i) => ({ ...r, seq: i + 1 })))
    _persist()

    const amount = toPush.reduce((s, x) => s + Math.abs(x.flags.acceptanceDiff), 0)
    return {
      ok: true,
      added: newRows.length,
      amount,
      message: `已向 H2-3 推送 ${newRows.length} 条 AJE 草稿（调整合计 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，不调折旧）；重复推送会替换旧自动草稿`,
    }
  }

  /**
   * 将转固样本证据缺口推送为 H2-3 索引说明行（类别「其他」，无金额）。
   * 重复推送会先清理旧自动草稿（remark=H2-9-evidence-gap-auto）。
   */
  function pushEvidenceGapsToH23(): {
    ok: boolean
    added: number
    message: string
  } {
    if (options.isReadonly.value) {
      return { ok: false, added: 0, message: '只读模式' }
    }
    const toPush = pushableEvidenceGapRows.value
    if (toPush.length === 0) {
      return { ok: false, added: 0, message: '无可推送项：转固样本审批与验收盖章均已确认' }
    }

    let existing: any[] = []
    const raw = _getJson(H23_ROWS_KEY)
    if (Array.isArray(raw)) existing = raw

    let seq = existing.reduce((m: number, r: any) => Math.max(m, Number(r.seq) || 0), 0) + 1
    const newRows = toPush.map(({ row, gaps }) => {
      const built = buildEvidenceGapH23Row({
        sourceSheet: 'H2-9',
        projectName: row.name,
        sampleLabel: `样本#${row.seq}`,
        gaps,
        seq: seq++,
        marker: H29_EVIDENCE_GAP_MARKER,
      })
      if (!row.auditConclusion || row.auditConclusion === '无异常') {
        row.auditConclusion = '存疑'
      }
      if (row.isAbnormal !== '是' && gaps.length > 0) row.isAbnormal = '是'
      return built
    })

    const merged = mergeEvidenceGapRowsToH23(existing, newRows, H29_EVIDENCE_GAP_MARKER)
    options.onSave?.(H23_ROWS_KEY, merged.map((r, i) => ({ ...r, seq: i + 1 })))
    _persist()

    return {
      ok: true,
      added: newRows.length,
      message: `已向 H2-3 推送 ${newRows.length} 条证据缺口说明（索引 H2-9）；重复推送会替换旧自动草稿`,
    }
  }

  function autoMarkAnomalies(): number {
    if (options.isReadonly.value) return 0
    let n = 0
    for (const row of rows.value) {
      const f = rowFlagsMap.value.get(row.rowId)
      if (!f) continue
      if (f.hasAcceptanceDiff || f.provisionalNeedsSettlement || f.missingApproval) {
        if (row.isAbnormal !== '是') {
          row.isAbnormal = '是'
          n++
        }
        if (!row.auditConclusion || row.auditConclusion === '无异常') {
          row.auditConclusion = (f.hasAcceptanceDiff || f.provisionalNeedsSettlement) ? '需调整' : '存疑'
        }
      }
    }
    if (n > 0) _persist()
    return n
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function _persist(): void {
    if (!options.onSave) return
    options.onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId,
      seq: r.seq,
      name: r.name,
      decreaseDate: r.decreaseDate,
      voucherNo: r.voucherNo,
      decreaseType: r.decreaseType,
      transferToFaAmount: r.transferToFaAmount,
      transferInterestCap: r.transferInterestCap,
      otherDecreaseAmount: r.otherDecreaseAmount,
      otherInterestCap: r.otherInterestCap,
      approvalRef: r.approvalRef,
      isApproved: r.isApproved,
      acceptanceDate: r.acceptanceDate,
      acceptanceAmount: r.acceptanceAmount,
      stampEngineering: r.stampEngineering,
      stampContractor: r.stampContractor,
      stampSupervisor: r.stampSupervisor,
      otherEvidence: r.otherEvidence,
      queryNo: r.queryNo,
      isAbnormal: r.isAbnormal,
      isProvisional: r.isProvisional,
      isRelatedParty: r.isRelatedParty,
      relatedPartyName: r.relatedPartyName,
      relationship: r.relationship,
      disposalIncome: r.disposalIncome,
      originalValue: _rowDecreaseTotal(r),
      approvalDoc: r.approvalRef,
      decreaseReason: r.decreaseType === '转入固定资产' ? '转出' : (r.decreaseType || ''),
      auditConclusion: r.auditConclusion,
      indexRef: r.indexRef,
      samplingStatus: r.samplingStatus,
      remark: r.remark,
    })))
    samplingParams.value.sampleSize = rows.value.length
    options.onSave?.(PARAMS_KEY, {
      ...samplingParams.value,
      populationManual: populationManual.value,
      coverageRate: coverageRate.value,
      sampleSize: rows.value.length,
    })
  }

  return {
    rows,
    samplingParams,
    auditNote,
    auditConclusion,
    populationManual,
    linkedDecrease,
    transferSampleTotal,
    otherSampleTotal,
    sampleTotal,
    interestCapSampleTotal,
    coverageRate,
    transferCoverageRate,
    otherCoverageRate,
    anomalyCount,
    provisionalCount,
    acceptanceDiffCount,
    evidenceGapCount,
    rowFlags,
    rowFlagsMap,
    pushableSettlementRows,
    pushableSettlementAmount,
    pushableEvidenceGapRows,
    typeStats,
    summary,
    originalTotal,
    lossTotal,
    netLossTotal,
    reasonStats,
    checkedAmount: sampleTotal,
    addRow,
    removeRow,
    updateCell,
    fillSamplingResults,
    updateSamplingParams,
    syncPopulationFromH22,
    pushSettlementAjeToH23,
    pushEvidenceGapsToH23,
    autoMarkAnomalies,
    saveNote,
    saveConclusion,
    initFromAllResponses,
  }
}

export default useH2DecreaseCheck
