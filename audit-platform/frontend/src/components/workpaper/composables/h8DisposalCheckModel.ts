/**
 * H8-12 使用权资产/租赁负债减少检查表 — 对齐致同「减少检查表H8-12」
 *
 * 编制逻辑：目标认定 → 样本选取 → 测试（原值/累计折旧/减值/净值 + 终止损益 + 核对1–5）
 *          → 检查比例（勾稽 H8-2/H8-1 本期减少，防 #DIV/0!）→ 说明/结论
 * 平台增强：终止损益 = 负债余额 − 净值（CAS21）；H9 同步终止；提前退租违约金
 */

import { calcSubtotal } from './useH8FormulaEngine'
import { calcTerminationGainLoss } from './useH8CAS21Engine'

// ─── Options ─────────────────────────────────────────────────────────────────

/** 减少方式（对齐致同「减少方式」+ CAS21 终止场景） */
export const REDUCTION_METHOD_OPTS = [
  '到期终止',
  '提前退租',
  '购买选择权行权',
  '租赁变更减少范围',
  '转租终止',
  '其他',
] as const

export type ReductionMethod = (typeof REDUCTION_METHOD_OPTS)[number] | ''

export const SAMPLING_METHOD_OPTS = [
  '货币单元抽样',
  '随机抽样',
  '系统抽样',
  '判断抽样',
] as const

/**
 * 测试内容说明（核对内容 1–5）
 * 第5项补全致同模板空白：H9 同步终止 + 提前退租违约金
 */
export const H8_DISPOSAL_TEST_CONTENT_ITEMS = [
  '原始凭证是否齐全（终止协议/退租通知/审批文件/交接记录等）',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确（原值−累计折旧−减值=净值；终止损益=负债余额−净值）',
  '是否记录于恰当的会计期间（截止测试）',
  '租赁负债已同步终止确认（H9）；提前退租违约金/补偿已恰当确认',
] as const

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H8DisposalChecks {
  check1: boolean
  check2: boolean
  check3: boolean
  check4: boolean
  check5: boolean
}

export interface H8DisposalCheckRow {
  rowId: string
  seq: number
  /** 使用权资产类别 */
  assetCategory: string
  /** 资产编号 / 合同号 */
  contractNo: string
  /** 资产名称 / 承租资产 */
  assetName: string
  /** 减少方式 */
  reductionMethod: ReductionMethod
  /** @deprecated 兼容旧字段 */
  terminationReason: string
  reductionDate: string
  voucherNo: string
  oppositeAccount: string
  quantity: number
  /** 原值 */
  rouCost: number
  /** 累计折旧 */
  accDepreciation: number
  /** 减值准备 */
  impairmentProvision: number
  /** 净值 = 原值 − 累计折旧 − 减值准备（公式） */
  rouNetValue: number
  /** 租赁负债余额（终止日） */
  liabilityBalance: number
  /** 终止损益 = 负债余额 − 净值（公式，CAS21） */
  gainLoss: number
  /** 剩余租赁期（月） */
  remainingMonths: number
  /** 提前退租违约金 */
  earlyTermPenalty: number
  supportingDocs: string
  checks: H8DisposalChecks
  indexRef: string
  isAbnormal: string
  isRelatedParty: string
  relatedPartyName: string
  /** 是否已通知 H9 同步终止 */
  h9Synced: boolean
  approvalStatus: '已审批' | '待审批' | ''
  approver: string
  remark: string
}

export interface H8DisposalSamplingParams {
  /** 本期减少使用权资产原值合计（总体） */
  populationAmount: number
  samplingMethod: string
  specificSampleNote: string
  materialityLevel: number
}

export interface H8DisposalSummary {
  checkedCount: number
  /** 样本原值合计（检查比例分子） */
  checkedAmount: number
  /** 样本净值合计 */
  checkedNetValue: number
  coverageRate: number
  anomalyCount: number
  incompleteCheckCount: number
  unsyncedH9Count: number
  earlyTermWithoutPenaltyCount: number
  gainLossTotal: number
  gainCount: number
  lossCount: number
  issueCount: number
}

export interface LinkedRouDecrease {
  amount: number
  terminatedCount: number
  source: 'H8-1' | 'H8-2' | ''
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _bool(v: unknown): boolean {
  return v === true || v === 'Y' || v === 'y' || v === '是' || v === 1 || v === '1'
}

function _emptyChecks(): H8DisposalChecks {
  return { check1: false, check2: false, check3: false, check4: false, check5: false }
}

function _normChecks(raw: unknown): H8DisposalChecks {
  const base = _emptyChecks()
  if (!raw || typeof raw !== 'object') return base
  const o = raw as Record<string, unknown>
  return {
    check1: _bool(o.check1),
    check2: _bool(o.check2),
    check3: _bool(o.check3),
    check4: _bool(o.check4),
    check5: _bool(o.check5),
  }
}

function _normChecksFromRow(raw: any): H8DisposalChecks {
  if (raw?.checks) return _normChecks(raw.checks)
  return _normChecks({
    check1: raw?.check1,
    check2: raw?.check2,
    check3: raw?.check3,
    check4: raw?.check4,
    check5: raw?.check5,
  })
}

/** 旧终止原因 / 别名 → 规范减少方式 */
export function normalizeReductionMethod(raw: string): ReductionMethod {
  const m = (raw || '').trim()
  if ((REDUCTION_METHOD_OPTS as readonly string[]).includes(m)) return m as ReductionMethod
  const map: Record<string, ReductionMethod> = {
    到期: '到期终止',
    租赁到期: '到期终止',
    提前: '提前退租',
    双方协商: '提前退租',
    违约终止: '提前退租',
    不可抗力: '提前退租',
    行权购买: '购买选择权行权',
    购买: '购买选择权行权',
    变更减少: '租赁变更减少范围',
    范围减少: '租赁变更减少范围',
    转租: '转租终止',
  }
  return map[m] ?? (m ? '其他' : '')
}

/**
 * 净值 = 原值 − 累计折旧 − 减值准备
 * 对齐致同公式 M = J − K − L
 */
export function calcRouNetValue(row: Pick<H8DisposalCheckRow, 'rouCost' | 'accDepreciation' | 'impairmentProvision'>): number {
  return Math.round((_num(row.rouCost) - _num(row.accDepreciation) - _num(row.impairmentProvision)) * 100) / 100
}

/** 检查比例：总体≤0 时返回 0，避免 #DIV/0! */
export function calcCoverageRate(checkedAmount: number, population: number): number {
  if (population <= 0) return 0
  return Math.min(100, Math.round((checkedAmount / population) * 10000) / 100)
}

export function createEmptySamplingParams(): H8DisposalSamplingParams {
  return {
    populationAmount: 0,
    samplingMethod: '货币单元抽样',
    specificSampleNote: '',
    materialityLevel: 0,
  }
}

export function normalizeSamplingParams(raw: unknown): H8DisposalSamplingParams {
  const base = createEmptySamplingParams()
  if (!raw || typeof raw !== 'object') return base
  const o = raw as Record<string, unknown>
  return {
    populationAmount: _num(o.populationAmount),
    samplingMethod: String(o.samplingMethod ?? base.samplingMethod),
    specificSampleNote: String(o.specificSampleNote ?? ''),
    materialityLevel: _num(o.materialityLevel),
  }
}

export function getEvidenceHint(method: string): string {
  switch (normalizeReductionMethod(method)) {
    case '到期终止':
      return '到期通知/资产交还记录/终止确认分录'
    case '提前退租':
      return '退租协议/审批/违约金条款/收款或付款凭证'
    case '购买选择权行权':
      return '行权通知/购买合同/过户/固定资产入账索引'
    case '租赁变更减少范围':
      return '变更协议/重新计量底稿/H8-7 索引'
    case '转租终止':
      return '转租终止协议/原租赁终止确认依据'
    default:
      return '充分、适当的原始凭证与审批'
  }
}

/** 提前退租且未填违约金（含 0）时提示关注条款 */
export function isEarlyTermWithoutPenaltyNote(
  row: Pick<H8DisposalCheckRow, 'reductionMethod' | 'terminationReason' | 'earlyTermPenalty' | 'remark'>,
): boolean {
  const method = normalizeReductionMethod(row.reductionMethod || row.terminationReason || '')
  if (method !== '提前退租') return false
  if (_num(row.earlyTermPenalty) !== 0) return false
  // 备注已说明「无违约金」则不计入缺口
  const remark = String(row.remark ?? '')
  return !/无违约金|零违约金|免违约金|不收取违约金/.test(remark)
}

/** 核对内容 1–4 是否齐全（第5项与 H9/违约金场景相关） */
export function isCheckIncomplete(row: Pick<H8DisposalCheckRow, 'checks'>): boolean {
  const c = row.checks
  return !c.check1 || !c.check2 || !c.check3 || !c.check4
}

/** 到期终止时净值与负债应接近 0（正常摊销完毕） */
export function isMaturityNearZeroAnomaly(
  row: Pick<H8DisposalCheckRow, 'reductionMethod' | 'terminationReason' | 'rouNetValue' | 'liabilityBalance'>,
  materialityLevel: number,
): boolean {
  const method = normalizeReductionMethod(row.reductionMethod || row.terminationReason || '')
  if (method !== '到期终止') return false
  const threshold = materialityLevel > 0 ? Math.max(materialityLevel * 0.001, 1) : 100
  return Math.abs(_num(row.rouNetValue)) > threshold || Math.abs(_num(row.liabilityBalance)) > threshold
}

export function normalizeDisposalRow(raw: any, idx = 0): H8DisposalCheckRow {
  const method = normalizeReductionMethod(
    String(raw.reductionMethod ?? raw.terminationReason ?? ''),
  )
  const rouCost = _num(raw.rouCost ?? raw.originalCost)
  const accDepreciation = _num(raw.accDepreciation ?? raw.accumulatedDepreciation)
  const impairmentProvision = _num(raw.impairmentProvision ?? raw.impairment)
  // 若仅有旧数据净值而无原值拆分，保留净值并反推原值展示（原值=净值）
  let cost = rouCost
  let acc = accDepreciation
  let impair = impairmentProvision
  const legacyNet = _num(raw.rouNetValue)
  if (cost === 0 && acc === 0 && impair === 0 && legacyNet !== 0) {
    cost = legacyNet
  }
  const rouNetValue = calcRouNetValue({ rouCost: cost, accDepreciation: acc, impairmentProvision: impair })
  const liabilityBalance = _num(raw.liabilityBalance ?? raw.leaseliabilityBalance)

  return {
    rowId: raw.rowId ?? `h812-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    seq: raw.seq ?? idx + 1,
    assetCategory: String(raw.assetCategory ?? raw.category ?? ''),
    contractNo: String(raw.contractNo ?? raw.assetNo ?? ''),
    assetName: String(raw.assetName ?? ''),
    reductionMethod: method,
    terminationReason: method || String(raw.terminationReason ?? ''),
    reductionDate: String(raw.reductionDate ?? raw.terminationDate ?? ''),
    voucherNo: String(raw.voucherNo ?? ''),
    oppositeAccount: String(raw.oppositeAccount ?? ''),
    quantity: _num(raw.quantity) || 1,
    rouCost: cost,
    accDepreciation: acc,
    impairmentProvision: impair,
    rouNetValue,
    liabilityBalance,
    gainLoss: calcTerminationGainLoss(liabilityBalance, rouNetValue),
    remainingMonths: _num(raw.remainingMonths),
    earlyTermPenalty: _num(raw.earlyTermPenalty),
    supportingDocs: String(raw.supportingDocs ?? raw.approvalDoc ?? ''),
    checks: _normChecksFromRow(raw),
    indexRef: String(raw.indexRef ?? raw.h9TerminationRef ?? ''),
    isAbnormal: String(raw.isAbnormal ?? ''),
    isRelatedParty: String(raw.isRelatedParty ?? ''),
    relatedPartyName: String(raw.relatedPartyName ?? ''),
    h9Synced: _bool(raw.h9Synced) || String(raw.h9LinkageStatus ?? '') === '已同步',
    approvalStatus: (raw.approvalStatus === '已审批' || raw.approvalStatus === '待审批')
      ? raw.approvalStatus
      : '',
    approver: String(raw.approver ?? ''),
    remark: String(raw.remark ?? ''),
  }
}

export function recalcDisposalRow(row: H8DisposalCheckRow): void {
  row.rouNetValue = calcRouNetValue(row)
  row.gainLoss = calcTerminationGainLoss(row.liabilityBalance, row.rouNetValue)
  row.terminationReason = row.reductionMethod
  row.reductionMethod = normalizeReductionMethod(row.reductionMethod || row.terminationReason)
}

export function calcDisposalSummary(
  rows: H8DisposalCheckRow[],
  population: number,
  materialityLevel = 0,
): H8DisposalSummary {
  const checkedAmount = calcSubtotal(rows.map(r => r.rouCost))
  const checkedNetValue = calcSubtotal(rows.map(r => r.rouNetValue))
  const gainLossTotal = calcSubtotal(rows.map(r => r.gainLoss))
  const anomalyCount = rows.filter(r =>
    r.isAbnormal === '是' || r.isAbnormal === 'Y' || isMaturityNearZeroAnomaly(r, materialityLevel),
  ).length
  const incompleteCheckCount = rows.filter(isCheckIncomplete).length
  const unsyncedH9Count = rows.filter(r => !r.h9Synced).length
  const earlyTermWithoutPenaltyCount = rows.filter(isEarlyTermWithoutPenaltyNote).length
  return {
    checkedCount: rows.length,
    checkedAmount,
    checkedNetValue,
    coverageRate: calcCoverageRate(checkedAmount, population),
    anomalyCount,
    incompleteCheckCount,
    unsyncedH9Count,
    earlyTermWithoutPenaltyCount,
    gainLossTotal,
    gainCount: rows.filter(r => r.gainLoss > 0).length,
    lossCount: rows.filter(r => r.gainLoss < 0).length,
    issueCount: anomalyCount + incompleteCheckCount + unsyncedH9Count,
  }
}

/**
 * 从 H8-1 贷方 / H8-2 已终止行汇总本期减少总体（原值口径）
 * 优先 H8-1 原值贷方发生；否则汇总 H8-2 带终止日的入账值
 */
export function sumLinkedRouDecrease(
  costCreditTotal: number,
  detailRows: any[],
): LinkedRouDecrease {
  const credit = _num(costCreditTotal)
  if (credit > 0) {
    return { amount: Math.round(credit * 100) / 100, terminatedCount: 0, source: 'H8-1' }
  }
  let amount = 0
  let terminatedCount = 0
  for (const r of detailRows || []) {
    const termDate = String(r.terminationDate ?? '').trim()
    if (!termDate) continue
    terminatedCount += 1
    amount += _num(r.initialAmount ?? r.rouCost ?? r.h9InitialAmount)
  }
  amount = Math.round(amount * 100) / 100
  return {
    amount,
    terminatedCount,
    source: amount > 0 ? 'H8-2' : '',
  }
}

/**
 * 从 H8-2 已填终止日的明细行生成减少检查样本
 * 净值口径：入账值 − 累计折旧期末（减值另补）
 */
export function seedDisposalRowsFromH82(detailRows: any[]): H8DisposalCheckRow[] {
  const out: H8DisposalCheckRow[] = []
  for (const r of detailRows || []) {
    const termDate = String(r.terminationDate ?? '').trim()
    if (!termDate) continue
    const contractNo = String(r.contractNo ?? '').trim()
    const assetName = String(r.assetName ?? '').trim()
    if (!contractNo && !assetName) continue
    const cost = _num(r.initialAmount ?? r.rouCost ?? r.h9InitialAmount)
    const accDep = _num(r.accDepEnd ?? r.accDepreciation)
      || (_num(r.accDepBegin) + _num(r.depCurrentPeriod))
    const impair = _num(r.impairmentProvision ?? r.impairment)
    out.push(normalizeDisposalRow({
      contractNo,
      assetName: assetName || contractNo,
      assetCategory: String(r.assetCategory ?? r.leaseType ?? ''),
      reductionMethod: '提前退租',
      reductionDate: termDate,
      rouCost: cost,
      accDepreciation: accDep,
      impairmentProvision: impair,
      liabilityBalance: 0,
      remark: `自H8-2带入（终止日 ${termDate}）`,
      indexRef: 'H8-2',
      sourceDetailRowId: r.rowId,
    }))
  }
  return out
}

/**
 * 按合同号从 H9-2 匹配期末/审定期末负债余额写入⑦
 * 优先 auditedEnd / finalAudited，其次 endBalance
 */
export function mapLiabilityFromH9(
  rows: H8DisposalCheckRow[],
  h9Rows: any[],
): { rows: H8DisposalCheckRow[]; matched: number } {
  const byContract = new Map<string, number>()
  for (const d of h9Rows || []) {
    const cn = String(d.contractNo ?? '').trim()
    if (!cn) continue
    const pick =
      d.finalAudited != null && d.finalAudited !== '' ? d.finalAudited
        : d.auditedEnd != null && d.auditedEnd !== '' ? d.auditedEnd
          : d.endBalance != null && d.endBalance !== '' ? d.endBalance
            : d.liabilityBalance
    const bal = _num(pick)
    byContract.set(cn, (byContract.get(cn) || 0) + bal)
  }
  let matched = 0
  const next = rows.map((r) => {
    const cn = r.contractNo.trim()
    if (!cn || !byContract.has(cn)) return r
    matched += 1
    const row = { ...r, liabilityBalance: byContract.get(cn)! }
    recalcDisposalRow(row)
    return row
  })
  return { rows: next, matched }
}

/**
 * 合并带入：已有合同号保留核对勾选与手工填写，补账面与日期
 */
export function mergeSeededDisposalRows(
  existing: H8DisposalCheckRow[],
  seeded: H8DisposalCheckRow[],
): H8DisposalCheckRow[] {
  const byKey = new Map<string, H8DisposalCheckRow>()
  for (const r of existing) {
    const k = r.contractNo.trim() || r.rowId
    byKey.set(k, r)
  }
  const out: H8DisposalCheckRow[] = []
  const used = new Set<string>()
  for (const s of seeded) {
    const k = s.contractNo.trim() || s.rowId
    used.add(k)
    const prev = byKey.get(k)
    if (!prev) {
      out.push(s)
      continue
    }
    const merged: H8DisposalCheckRow = {
      ...s,
      rowId: prev.rowId,
      checks: { ...prev.checks },
      h9Synced: prev.h9Synced,
      liabilityBalance: prev.liabilityBalance || s.liabilityBalance,
      earlyTermPenalty: prev.earlyTermPenalty || s.earlyTermPenalty,
      supportingDocs: prev.supportingDocs || s.supportingDocs,
      voucherNo: prev.voucherNo || s.voucherNo,
      oppositeAccount: prev.oppositeAccount || s.oppositeAccount,
      isAbnormal: prev.isAbnormal || s.isAbnormal,
      isRelatedParty: prev.isRelatedParty || s.isRelatedParty,
      relatedPartyName: prev.relatedPartyName || s.relatedPartyName,
      remark: prev.remark || s.remark,
      indexRef: prev.indexRef || s.indexRef,
      reductionMethod: prev.reductionMethod || s.reductionMethod,
    }
    recalcDisposalRow(merged)
    out.push(merged)
  }
  // 保留既有但不在本次带入中的手工行
  for (const r of existing) {
    const k = r.contractNo.trim() || r.rowId
    if (!used.has(k)) out.push(r)
  }
  return out.map((r, i) => ({ ...r, seq: i + 1 }))
}

export function buildNoteDraft(summary: H8DisposalSummary, population: number): string {
  const lines = [
    `本期减少检查样本 ${summary.checkedCount} 笔，检查原值合计 ${summary.checkedAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，总体（本期减少） ${population.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，检查比例 ${summary.coverageRate.toFixed(2)}%。`,
    `样本净值合计 ${summary.checkedNetValue.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，终止损益合计 ${summary.gainLossTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}（收益 ${summary.gainCount} / 损失 ${summary.lossCount}）。`,
  ]
  if (population > 0 && summary.coverageRate < 20) {
    lines.push('检查比例偏低：已/拟扩大样本量，或说明判断抽样理由：________。')
  }
  if (summary.unsyncedH9Count > 0) {
    lines.push(`其中 ${summary.unsyncedH9Count} 笔尚未同步 H9 租赁负债终止确认，须补齐联动。`)
  }
  if (summary.earlyTermWithoutPenaltyCount > 0) {
    lines.push(`提前退租 ${summary.earlyTermWithoutPenaltyCount} 笔未填违约金：请核对合同条款，若确无违约金请在备注说明。`)
  }
  if (summary.anomalyCount > 0) {
    lines.push(`标记异常/到期仍有余额 ${summary.anomalyCount} 笔，详见备注及拟调整事项。`)
  }
  if (summary.incompleteCheckCount > 0) {
    lines.push(`核对内容 1–4 未全部勾选 ${summary.incompleteCheckCount} 笔，请补充测试记录。`)
  }
  lines.push('关注：终止损益=负债余额−使用权净值；到期终止净额应接近零；提前退租须同步确认违约金/补偿。')
  return lines.join('\n')
}

export function buildConclusionDraft(summary: H8DisposalSummary): string {
  if (summary.checkedCount === 0) {
    return '本期尚未抽取减少样本。完成样本选取与测试后，再就是否实现审计目标发表结论。'
  }
  if (summary.issueCount === 0) {
    return '经抽查，本期使用权资产/租赁负债减少相关原始凭证、账务处理及截止基本恰当，终止损益计算正确，H9 已同步终止确认；在已执行程序范围内，未发现重大异常。'
  }
  return `经抽查，发现 ${summary.issueCount} 项需关注事项（异常/核对未完/H9 未同步等），详见三、测试明细与四、审计说明；拟进一步追查或提出调整建议后，再就减少认定是否恰当发表最终结论。`
}
