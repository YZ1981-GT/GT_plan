/**
 * useH8LeaseTerm — H8-5 租赁期的确定（对齐致同 Excel 段落型 52 行）
 *
 * CAS21 第14-17条：
 * 租赁期 = 不可撤销期间
 *   + 续租选择权涵盖期间（合理确定将行使）
 *   + 终止选择权涵盖期间（合理确定将不行使）
 *
 * Excel 结构：
 *   §1 租赁期确定（签订→开始日 / 开始日 / 不可撤销 / 续租 / 购买 → 确定的租赁期）
 *   §2.1 重大事件触发重新评估（改良/定制/经营决策 → 自动结论）
 *   §2.2 按重新评估结果修改租赁期（四情形 → 重新确定的租赁期）
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/ Task 3.4 | Req 4.2, 4.4
 */
import { ref, computed, watch, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type YesNo = '是' | '否' | ''
export type IncludeFlag = '包含' | '不包含' | '待判断' | ''

/** 单份合同的租赁期确定记录（对齐 Excel H8-5） */
export interface H8LeaseTermRecord {
  recordId: string
  contractNo: string

  // ── §1 租赁期的确定 ──
  /** (1) 签订日至开始日 — 合同信息；准则固定不包含 */
  signingToCommencementInfo: string
  /** (2) 租赁期开始日 — 合同信息；准则固定包含 */
  commencementInfo: string
  commencementDate: string

  /** (3) 不可撤销期间 */
  nonCancellableInfo: string
  nonCancellableMonths: number
  /** 仅出租人有权终止 → 该期间属不可撤销，包含 */
  lessorOnlyTerminate: YesNo
  /** 仅承租人有权终止 */
  lesseeOnlyTerminate: YesNo
  /** 合理确定将不行使终止选择权（仅承租人有权时） */
  lesseeReasonablyCertainNotTerminate: YesNo
  /** 双方均可无重大罚金终止 → 租赁不再可强制执行，不包含 */
  bothCanTerminateNoPenalty: YesNo
  /** 终止选择权涵盖期间（月）— 合理确定不行使时计入 */
  terminationOptionMonths: number

  /** (4) 续租选择权 */
  renewalInfo: string
  renewalMonths: number
  renewalReasonablyCertain: YesNo

  /** (5) 购买选择权 */
  purchaseOptionInfo: string
  purchaseReasonablyCertain: YesNo

  /** 确定的租赁期（月）— 可手填覆盖；空则用公式推算 */
  determinedLeaseTermMonths: number
  termEndDate: string
  indexRef: string

  // ── §2.1 重新评估触发（承租人可控范围内重大事件）──
  majorImprovement: YesNo
  majorCustomization: YesNo
  relatedBusinessDecision: YesNo

  // ── §2.2 根据重新评估结果修改租赁期 ──
  /** (1) 实际行使了以前未纳入的选择权 */
  exercisedOptionNotIncluded: YesNo
  /** (2) 未行使以前已纳入的选择权 */
  didNotExerciseIncludedOption: YesNo
  /** (3) 事件强制行使以前未纳入的选择权 */
  eventForcesExercise: YesNo
  /** (4) 事件禁止行使以前已纳入的选择权 */
  eventPreventsExercise: YesNo
  redeterminedInfo: string
  redeterminedLeaseTermMonths: number

  explanation: string
  conclusion: '是' | '否' | '不适用' | ''
}

// ─── Tip catalog（Excel 蓝字提示 → 弹窗，避免主表拥挤）─────────────────────

export interface H8LeaseTermTip {
  id: string
  title: string
  paragraphs: string[]
  jumps?: Array<{ label: string; sheet: string }>
}

export const H8_LEASE_TERM_TIPS: H8LeaseTermTip[] = [
  {
    id: 'definition',
    title: '租赁期定义（CAS21）',
    paragraphs: [
      '租赁期是指承租人有权使用租赁资产且不可撤销的期间。',
      '承租人有续租选择权，即有权选择续租该资产，且合理确定将行使该选择权的，租赁期还应当包含续租选择权涵盖的期间。',
      '承租人有终止租赁选择权，即有权选择终止租赁该资产，且合理确定将不行使该选择权的，租赁期应当包含终止租赁选择权涵盖的期间。',
      '租赁期自租赁期开始日起算（出租人使租赁资产可供承租人使用之日）。签订日至开始日之间的期间不计入租赁期。',
    ],
    jumps: [
      { label: 'H8-4 租赁识别', sheet: 'H8-4' },
      { label: 'H8-6 初始及后续计量', sheet: 'H8-6' },
    ],
  },
  {
    id: 'flowchart',
    title: '租赁期构成示意',
    paragraphs: [
      '租赁期 = 不可撤销期间',
      '　　＋ 续租选择权涵盖期间（合理确定将行使）',
      '　　＋ 终止选择权涵盖期间（合理确定将不行使）',
      '例外：若承租人与出租人均有权选择终止租赁，且均无需支付重大罚金，则该租赁不再可强制执行——自该时可终止时点起不纳入租赁期。',
    ],
  },
  {
    id: 'item1',
    title: '（1）签订日至开始日',
    paragraphs: [
      '合同签订日与租赁期开始日之间的期间：承租人尚未获得使用权，准则明确不包含在租赁期内。',
      '请在「合同信息」列记录签订日、计划开始日及间隔说明，便于与合同原件勾稽。',
    ],
  },
  {
    id: 'item2',
    title: '（2）租赁期开始日',
    paragraphs: [
      '租赁期开始日：出租人使租赁资产可供承租人使用的日期。自该日起租赁期开始计算，应当包含。',
      '实务注意：装修免租期若已获得资产控制权，通常仍属租赁期开始之后，需结合合同判断。',
    ],
  },
  {
    id: 'item3',
    title: '（3）不可撤销期间与终止权',
    paragraphs: [
      '不可撤销期间：租赁合同不可撤销的期间。',
      '仅出租人有权终止租赁：该选择权涵盖的期间仍视为不可撤销期间的一部分，应当包含。',
      '仅承租人有权终止租赁：应当评估承租人是否合理确定将不行使终止选择权。合理确定不行使时，租赁期应包括终止选择权涵盖的期间。',
      '双方均有权选择终止且无需支付重大罚金：租赁不再可强制执行，自可终止时点起不包含在租赁期内。',
      '评估「合理确定」时，应考虑：资产对经营的重要性、重大租赁资产改良、迁移/替换成本、定制化程度、过往行使历史、相关经营决策等（详见续租因素提示）。',
    ],
  },
  {
    id: 'item4',
    title: '（4）续租选择权 — 合理确定',
    paragraphs: [
      '存在续租选择权时，应评估承租人是否合理确定将行使该选择权。合理确定行使的，租赁期包含续租选择权涵盖的期间。',
      '需综合评估所有相关事实和情况所提供的经济利益，包括但不限于：',
      '① 相较于终止选择权，续租/购买选择权相关的合同条款与条件（如行权价格相对市价）；',
      '② 在合同期内进行的重大租赁资产改良；',
      '③ 与终止租赁相关的成本（谈判、搬迁、寻找替代资产、残值担保等）；',
      '④ 租赁资产对承租人经营活动的重要程度（是否专用、位置是否关键）；',
      '⑤ 与行使选择权相关的条件成就的可能性；',
      '⑥ 承租人过往是否习惯行使类似选择权，以及终止同类租赁时是否发生过经营损失。',
    ],
  },
  {
    id: 'item5',
    title: '（5）购买选择权',
    paragraphs: [
      '承租人有购买选择权且合理确定将行使的，通常意味着租赁期覆盖至预期取得所有权时点；后续折旧年限应结合资产剩余使用寿命（见 H8-8）。',
      '购买选择权的行权可能性评估因素与续租选择权类似。',
    ],
    jumps: [{ label: 'H8-8 折旧测算', sheet: 'H8-8' }],
  },
  {
    id: 'reassess',
    title: '§2 重新评估租赁期',
    paragraphs: [
      '发生重大事件或变化，且该事件或变化在承租人可控范围内、影响承租人是否合理确定将行使续租/购买选择权或不行使终止选择权时，承租人应当重新评估该判断，并根据重新评估结果调整租赁期。',
      '常见触发：①重大租赁资产改良；②对租赁资产的重大定制化改造；③直接相关的经营决策（如决定行使续租、决定处置相关业务单元等）。',
      'Excel 结论公式：任一触发为「是」→「应当重新评估是否合理确定将行使续租选择权、购买选择权或不行使终止租赁选择权」；否则「无需重新评估」。',
    ],
    jumps: [
      { label: 'H8-6 重新计量', sheet: 'H8-6' },
      { label: 'H8-7 租赁变更', sheet: 'H8-7' },
    ],
  },
  {
    id: 'modify',
    title: '§2.2 按重新评估结果修改租赁期',
    paragraphs: [
      '出现下列情形之一时，承租人应当修改租赁期：',
      '（1）承租人实际行使了以前未纳入租赁期的选择权（续租/购买等）；',
      '（2）承租人未行使以前已纳入租赁期的选择权；',
      '（3）发生了强制承租人行使以前未纳入租赁期的选择权的事件；',
      '（4）发生了禁止承租人行使以前已纳入租赁期的选择权的事件。',
      '重新确定租赁期后，应同步更新 H8-6 租赁负债/使用权资产计量，并视情形评估是否构成 H8-7 租赁变更。',
    ],
    jumps: [
      { label: '跳转 H8-6 计量', sheet: 'H8-6' },
      { label: '跳转 H8-7 变更', sheet: 'H8-7' },
    ],
  },
]

// ─── Constants ───────────────────────────────────────────────────────────────

const RECORDS_KEY = 'H8-5-records'
/** H8-6 计量参数（跨表回写目标） */
export const H86_PARAMS_KEY = 'H8-6-params'
/** H8-8 折旧行（跨表回写目标） */
export const H88_DEP_ROWS_KEY = 'H8-8-dep-rows'
/** H8-13 简化处理检查行 */
export const H813_ROWS_KEY = 'H8-13-rows'

/** CAS21：≤12 月且不含合理确定行使的购买选择权，才可作为短期租赁候选 */
export function isShortTermLeaseCandidate(r: Pick<
  H8LeaseTermRecord,
  | 'nonCancellableMonths' | 'renewalMonths' | 'renewalReasonablyCertain'
  | 'terminationOptionMonths' | 'lesseeReasonablyCertainNotTerminate'
  | 'bothCanTerminateNoPenalty' | 'determinedLeaseTermMonths' | 'redeterminedLeaseTermMonths'
  | 'purchaseReasonablyCertain'
>): boolean {
  if (r.purchaseReasonablyCertain === '是') return false
  const months = resolveEffectiveLeaseTermMonths(r as H8LeaseTermRecord)
  return months > 0 && months <= 12
}

export interface H85ToH813SyncResult {
  ok: boolean
  reason?: string
  updated: number
  added: number
  skippedPurchaseOption: number
  details: Array<{ contractNo: string; months: number; action: 'updated' | 'added' }>
}

/**
 * 将 H8-5 短期候选写入/更新 H8-13 行（纯函数）。
 * - 已有同合同号：仅更新 leaseTermMonths（及备注标记）
 * - 无匹配：新增检查行骨架
 */
export function upsertH85ShortTermIntoH813Rows<T extends {
  rowId?: string
  contractNo: string
  leaseTermMonths: number
  remark?: string
  assetName?: string
  commencementDate?: string
}>(
  existingRows: T[],
  candidates: H85TermOption[],
  opts?: { onlyContractNo?: string; addMissing?: boolean },
): { rows: any[]; updated: number; added: number; details: H85ToH813SyncResult['details'] } {
  const only = opts?.onlyContractNo?.trim()
  const addMissing = opts?.addMissing !== false
  const next = existingRows.map(r => ({ ...r }))
  let updated = 0
  let added = 0
  const details: H85ToH813SyncResult['details'] = []
  const tag = '已与H8-5同步租赁期'

  for (const c of candidates) {
    if (c.months <= 0 || c.months > 12) continue
    if (only && c.contractNo !== only) continue
    const idx = next.findIndex(r => String(r.contractNo || '').trim() === c.contractNo)
    if (idx >= 0) {
      const row = next[idx] as any
      if (row.leaseTermMonths !== c.months) {
        row.leaseTermMonths = c.months
        updated++
        details.push({ contractNo: c.contractNo, months: c.months, action: 'updated' })
      }
      const remark = String(row.remark || '')
      if (!remark.includes(tag)) {
        row.remark = remark ? `${remark}；${tag}` : tag
      }
    } else if (addMissing) {
      next.push({
        rowId: `h813-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
        contractNo: c.contractNo,
        assetName: '',
        lessor: '',
        assetCategory: '',
        leaseTermMonths: c.months,
        annualRental: 0,
        newAssetValue: 0,
        monthlyRent: 0,
        accrualMonths: Math.min(c.months, 12),
        bookExpense: 0,
        expenseAmount: 0,
        expenseAccount: '',
        reconciled: '',
        conclusion: '',
        remark: `来源:H8-5短期候选；${tag}`,
      } as any)
      added++
      details.push({ contractNo: c.contractNo, months: c.months, action: 'added' })
    }
  }

  return { rows: next, updated, added, details }
}

export interface H85TermOption {
  recordId: string
  contractNo: string
  months: number
  conclusion: string
  commencementDate?: string
  termEndDate?: string
}

/** 从 H8-5 records 解析可选租赁期列表（纯函数；H8-6/H8-8 共用） */
export function listLeaseTermsFromH85Raw(data: any): H85TermOption[] {
  if (!Array.isArray(data)) return []
  return data.map((r: any, i: number) => {
    const months = resolveEffectiveLeaseTermMonths({
      nonCancellableMonths: Number(r.nonCancellableMonths ?? r.nonCancellableTerm) || 0,
      renewalMonths: Number(r.renewalMonths ?? r.renewalOptionTerm) || 0,
      renewalReasonablyCertain: r.renewalReasonablyCertain ?? r.isRenewalReasonablyCertain ?? '',
      terminationOptionMonths: Number(r.terminationOptionMonths ?? r.terminationOptionTerm) || 0,
      lesseeReasonablyCertainNotTerminate: r.lesseeReasonablyCertainNotTerminate
        ?? (r.isTerminationReasonablyCertain === '否' ? '是'
          : r.isTerminationReasonablyCertain === '是' ? '否' : ''),
      bothCanTerminateNoPenalty: r.bothCanTerminateNoPenalty ?? '',
      determinedLeaseTermMonths: Number(r.determinedLeaseTermMonths ?? r.finalLeaseTerm) || 0,
      redeterminedLeaseTermMonths: Number(r.redeterminedLeaseTermMonths) || 0,
    } as H8LeaseTermRecord)
    return {
      recordId: String(r.recordId ?? `idx-${i}`),
      contractNo: String(r.contractNo ?? ''),
      months,
      conclusion: String(r.conclusion ?? ''),
      commencementDate: String(r.commencementDate ?? ''),
      termEndDate: String(r.termEndDate ?? ''),
    }
  }).filter(o => o.contractNo)
}

/** 按合同号或默认策略选取一条（优先有结论且月数>0） */
export function pickH85TermOption(
  options: H85TermOption[],
  contractNo?: string,
): H85TermOption | null {
  if (!options.length) return null
  if (contractNo?.trim()) {
    return options.find(o => o.contractNo === contractNo.trim()) ?? null
  }
  const withTerm = options.filter(o => o.months > 0)
  if (!withTerm.length) return null
  return withTerm.find(o => o.conclusion === '是') ?? withTerm[0]
}

export interface H85ToH86SyncResult {
  ok: boolean
  reason?: string
  contractNo?: string
  months?: number
  previousMonths?: number
  /** ≤12 月：提示关注短期租赁简化（H8-13） */
  shortTermHint?: boolean
}

export interface H85ToH88SyncResult {
  ok: boolean
  reason?: string
  /** 更新的折旧行数 */
  updated: number
  /** H8-5 有租期但 H8-8 无匹配合同号 */
  unmatchedContracts: string[]
  /** 已同步明细 */
  details: Array<{ contractNo: string; months: number; rowCount: number }>
}

/** 按合同号把 H8-5 有效租赁期写入折旧行（纯函数） */
export function applyH85TermsToDepRows<T extends {
  contractNo: string
  leaseTermMonths: number
  startDate?: string
  remark?: string
}>(
  rows: T[],
  termsByContract: Map<string, H85TermOption>,
  opts?: { onlyContractNo?: string; fillStartDate?: boolean },
): { rows: T[]; updated: number; unmatchedContracts: string[]; details: H85ToH88SyncResult['details'] } {
  const only = opts?.onlyContractNo?.trim()
  const fillStart = opts?.fillStartDate !== false
  const next = rows.map(r => ({ ...r }))
  let updated = 0
  const detailMap = new Map<string, { contractNo: string; months: number; rowCount: number }>()

  for (const row of next) {
    const key = String(row.contractNo || '').trim()
    if (!key) continue
    if (only && key !== only) continue
    const term = termsByContract.get(key)
    if (!term || term.months <= 0) continue

    let touched = false
    if (row.leaseTermMonths !== term.months) {
      row.leaseTermMonths = term.months
      touched = true
    }
    if (fillStart && term.commencementDate && !String(row.startDate || '').trim()) {
      row.startDate = term.commencementDate
      touched = true
    }
    if (!touched) continue

    const tag = '已与H8-5同步租赁期'
    const remark = String(row.remark || '')
    if (!remark.includes(tag)) {
      row.remark = remark ? `${remark}；${tag}` : tag
    }
    updated++
    const d = detailMap.get(key) ?? { contractNo: key, months: term.months, rowCount: 0 }
    d.rowCount++
    detailMap.set(key, d)
  }

  const unmatchedContracts: string[] = []
  for (const [cn, term] of termsByContract) {
    if (only && cn !== only) continue
    if (term.months <= 0) continue
    if (!next.some(r => String(r.contractNo || '').trim() === cn)) {
      unmatchedContracts.push(cn)
    }
  }

  return {
    rows: next,
    updated,
    unmatchedContracts,
    details: [...detailMap.values()],
  }
}

/** 纯函数：把有效租赁期写入 H8-6 params（保留其余字段） */
export function mergeLeaseTermIntoH86Params(
  existing: Record<string, any> | null | undefined,
  months: number,
  contractNo: string,
): Record<string, any> {
  const base = existing && typeof existing === 'object' ? { ...existing } : {}
  return {
    leaseLiabilityInitial: Number(base.leaseLiabilityInitial) || 0,
    directCost: Number(base.directCost) || 0,
    incentive: Number(base.incentive) || 0,
    discountRate: Number(base.discountRate) || 0,
    leaseTermMonths: Math.max(0, Math.round(Number(months) || 0)),
    rentalPerPeriod: Number(base.rentalPerPeriod) || 0,
    paymentTiming: base.paymentTiming === '期初' ? '期初' : '期末',
    leaseTermSourceContract: contractNo || '',
    leaseTermSyncedFrom: 'H8-5',
  }
}

export function calcLeaseTermMonths(r: Pick<
  H8LeaseTermRecord,
  | 'nonCancellableMonths'
  | 'renewalMonths'
  | 'renewalReasonablyCertain'
  | 'terminationOptionMonths'
  | 'lesseeReasonablyCertainNotTerminate'
  | 'bothCanTerminateNoPenalty'
>): number {
  if (r.bothCanTerminateNoPenalty === '是') {
    // 双方可无重大罚金终止：仅保留至可终止前的不可撤销部分（由编制人填 nonCancellableMonths）
    return Math.max(Number(r.nonCancellableMonths) || 0, 0)
  }
  let term = Math.max(Number(r.nonCancellableMonths) || 0, 0)
  if (r.renewalReasonablyCertain === '是') {
    term += Math.max(Number(r.renewalMonths) || 0, 0)
  }
  // CAS21：合理确定不行使终止权 → 计入终止选择权涵盖期间
  if (r.lesseeReasonablyCertainNotTerminate === '是') {
    term += Math.max(Number(r.terminationOptionMonths) || 0, 0)
  }
  return Math.max(term, 0)
}

/** Excel C29：任一重大事件为「是」→ 应当重新评估 */
export function calcReassessmentConclusion(
  majorImprovement: YesNo,
  majorCustomization: YesNo,
  relatedBusinessDecision: YesNo,
): string {
  if (majorImprovement === '是' || majorCustomization === '是' || relatedBusinessDecision === '是') {
    return '应当重新评估是否合理确定将行使续租选择权、购买选择权或不行使终止租赁选择权'
  }
  if (
    majorImprovement === '否'
    && majorCustomization === '否'
    && relatedBusinessDecision === '否'
  ) {
    return '无需重新评估'
  }
  return '待填写触发情形后自动判定'
}

export function resolveEffectiveLeaseTermMonths(r: H8LeaseTermRecord): number {
  if (r.redeterminedLeaseTermMonths > 0) return r.redeterminedLeaseTermMonths
  if (r.determinedLeaseTermMonths > 0) return r.determinedLeaseTermMonths
  return calcLeaseTermMonths(r)
}

export function needsTermModification(r: H8LeaseTermRecord): boolean {
  return (
    r.exercisedOptionNotIncluded === '是'
    || r.didNotExerciseIncludedOption === '是'
    || r.eventForcesExercise === '是'
    || r.eventPreventsExercise === '是'
  )
}

function emptyRecord(contractNo: string, id: string): H8LeaseTermRecord {
  return {
    recordId: id,
    contractNo,
    signingToCommencementInfo: '',
    commencementInfo: '',
    commencementDate: '',
    nonCancellableInfo: '',
    nonCancellableMonths: 0,
    lessorOnlyTerminate: '',
    lesseeOnlyTerminate: '',
    lesseeReasonablyCertainNotTerminate: '',
    bothCanTerminateNoPenalty: '',
    terminationOptionMonths: 0,
    renewalInfo: '',
    renewalMonths: 0,
    renewalReasonablyCertain: '',
    purchaseOptionInfo: '',
    purchaseReasonablyCertain: '',
    determinedLeaseTermMonths: 0,
    termEndDate: '',
    indexRef: '',
    majorImprovement: '',
    majorCustomization: '',
    relatedBusinessDecision: '',
    exercisedOptionNotIncluded: '',
    didNotExerciseIncludedOption: '',
    eventForcesExercise: '',
    eventPreventsExercise: '',
    redeterminedInfo: '',
    redeterminedLeaseTermMonths: 0,
    explanation: '',
    conclusion: '',
  }
}

/** 兼容旧版精简字段（续租/终止简单加减） */
function migrateLegacy(raw: any, id: string): H8LeaseTermRecord {
  const base = emptyRecord(String(raw.contractNo ?? ''), id)
  const nonCancellable = Number(raw.nonCancellableTerm ?? raw.nonCancellableMonths) || 0
  const renewal = Number(raw.renewalOptionTerm ?? raw.renewalMonths) || 0
  const termination = Number(raw.terminationOptionTerm ?? raw.terminationOptionMonths) || 0
  const renewalCertain = (raw.isRenewalReasonablyCertain ?? raw.renewalReasonablyCertain ?? '') as YesNo
  // 旧版「合理确定行使终止」并扣减 → 迁移为「合理确定不行使」取反语义需人工复核；
  // 若旧版为「是」(行使终止)，则不计入终止期；若为「否」，视为可能应计入，置空待填。
  const oldTermCertain = raw.isTerminationReasonablyCertain as YesNo | undefined

  return {
    ...base,
    nonCancellableMonths: nonCancellable,
    renewalMonths: renewal,
    renewalReasonablyCertain: renewalCertain === '是' || renewalCertain === '否' ? renewalCertain : '',
    terminationOptionMonths: termination,
    lesseeReasonablyCertainNotTerminate:
      oldTermCertain === '否' ? '是' : oldTermCertain === '是' ? '否' : '',
    determinedLeaseTermMonths: Number(raw.finalLeaseTerm) || 0,
    explanation: String(raw.explanation ?? ''),
    conclusion: (raw.conclusion ?? '') as H8LeaseTermRecord['conclusion'],
  }
}

function normalizeRecord(raw: any): H8LeaseTermRecord {
  const id = raw.recordId ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  // 旧版特征字段
  if (
    raw.nonCancellableTerm != null
    || raw.isRenewalReasonablyCertain != null
    || raw.isTerminationReasonablyCertain != null
  ) {
    const migrated = migrateLegacy(raw, id)
    if (!migrated.determinedLeaseTermMonths) {
      migrated.determinedLeaseTermMonths = calcLeaseTermMonths(migrated)
    }
    return migrated
  }

  const blank = emptyRecord(String(raw.contractNo ?? ''), id)
  const rec: H8LeaseTermRecord = { ...blank }
  for (const key of Object.keys(blank) as (keyof H8LeaseTermRecord)[]) {
    if (raw[key] === undefined || raw[key] === null) continue
    ;(rec as any)[key] = raw[key]
  }
  rec.recordId = id
  rec.contractNo = String(raw.contractNo ?? '')

  const numKeys: (keyof H8LeaseTermRecord)[] = [
    'nonCancellableMonths', 'renewalMonths', 'terminationOptionMonths',
    'determinedLeaseTermMonths', 'redeterminedLeaseTermMonths',
  ]
  for (const k of numKeys) {
    ;(rec as any)[k] = Number(rec[k]) || 0
  }
  return rec
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8LeaseTerm(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const records = ref<H8LeaseTermRecord[]>([])

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _generateId(): string {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  }

  function load(): void {
    const data = _getJson(RECORDS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      records.value = data.map(normalizeRecord)
    } else {
      records.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  const completedCount = computed(() =>
    records.value.filter(r => r.conclusion !== '').length,
  )

  const avgLeaseTerm = computed(() => {
    if (records.value.length === 0) return 0
    const total = records.value.reduce((s, r) => s + resolveEffectiveLeaseTermMonths(r), 0)
    return Math.round(total / records.value.length)
  })

  const reassessmentNeededCount = computed(() =>
    records.value.filter(r =>
      calcReassessmentConclusion(r.majorImprovement, r.majorCustomization, r.relatedBusinessDecision)
        .startsWith('应当'),
    ).length,
  )

  /** 短期租赁候选（≤12月且无合理确定购买选择权） */
  const shortTermCandidates = computed(() =>
    records.value.filter(r => isShortTermLeaseCandidate(r)),
  )

  const shortTermCandidateCount = computed(() => shortTermCandidates.value.length)

  function addRecord(contractNo: string): void {
    if (!contractNo?.trim()) return
    records.value.push(emptyRecord(contractNo.trim(), _generateId()))
    _persist()
  }

  function deleteRecord(recordId: string): void {
    const idx = records.value.findIndex(r => r.recordId === recordId)
    if (idx === -1) return
    records.value.splice(idx, 1)
    _persist()
  }

  function updateField(recordId: string, field: string, value: any): void {
    const record = records.value.find(r => r.recordId === recordId)
    if (!record) return

    const numFields = [
      'nonCancellableMonths', 'renewalMonths', 'terminationOptionMonths',
      'determinedLeaseTermMonths', 'redeterminedLeaseTermMonths',
    ]
    if (numFields.includes(field)) {
      ;(record as any)[field] = Number(value) || 0
    } else {
      ;(record as any)[field] = value == null ? '' : String(value)
    }

    // 双方均可终止：清空「合理确定不行使」以免矛盾
    if (field === 'bothCanTerminateNoPenalty' && record.bothCanTerminateNoPenalty === '是') {
      record.lesseeReasonablyCertainNotTerminate = ''
    }

    // 若未手填确定租赁期，用公式回填建议值（不覆盖已有手填）
    if (
      field !== 'determinedLeaseTermMonths'
      && field !== 'redeterminedLeaseTermMonths'
      && !record.determinedLeaseTermMonths
    ) {
      // 保持 0，由 UI 展示「建议值」；避免静默覆盖手填
    }

    _persist()
  }

  /** 用公式结果写入「确定的租赁期」 */
  function applySuggestedTerm(recordId: string): void {
    const record = records.value.find(r => r.recordId === recordId)
    if (!record) return
    record.determinedLeaseTermMonths = calcLeaseTermMonths(record)
    _persist()
  }

  /**
   * 将指定合同有效租赁期回写 H8-6-params.leaseTermMonths，并保留其余计量参数。
   * 成功后派发 h8:lease-term-synced 供计量页刷新提示。
   */
  function pushLeaseTermToH86(recordId: string): H85ToH86SyncResult {
    const record = records.value.find(r => r.recordId === recordId)
    if (!record) return { ok: false, reason: '未找到合同记录' }
    const months = resolveEffectiveLeaseTermMonths(record)
    if (months <= 0) {
      return { ok: false, reason: '有效租赁期为 0，请先确定租赁期或采用建议值' }
    }
    if (!onSave) return { ok: false, reason: '无法保存（只读或未挂载 onSave）' }

    const existing = _getJson(H86_PARAMS_KEY)
    const previousMonths = Number(existing?.leaseTermMonths) || 0
    const next = mergeLeaseTermIntoH86Params(existing, months, record.contractNo)
    onSave(H86_PARAMS_KEY, next)

    // 若本记录尚未填「确定的租赁期」，同步落盘建议值，避免仅回写下游
    if (!record.determinedLeaseTermMonths && !record.redeterminedLeaseTermMonths) {
      record.determinedLeaseTermMonths = months
      _persist()
    }

    const result: H85ToH86SyncResult = {
      ok: true,
      contractNo: record.contractNo,
      months,
      previousMonths,
      shortTermHint: months <= 12,
    }
    try {
      window.dispatchEvent(new CustomEvent('h8:lease-term-synced', {
        detail: { source: 'H8-5', ...result },
      }))
    } catch { /* SSR / 非浏览器 */ }
    return result
  }

  /**
   * 按合同号将有效租赁期回写 H8-8 折旧行（leaseTermMonths；空 startDate 时补开始日）。
   * @param recordId 指定单份合同；省略则同步全部有有效租期的合同
   */
  function pushLeaseTermToH88(recordId?: string): H85ToH88SyncResult {
    if (!onSave) {
      return { ok: false, reason: '无法保存（只读或未挂载 onSave）', updated: 0, unmatchedContracts: [], details: [] }
    }

    const targets = recordId
      ? records.value.filter(r => r.recordId === recordId)
      : records.value
    if (!targets.length) {
      return { ok: false, reason: '未找到合同记录', updated: 0, unmatchedContracts: [], details: [] }
    }

    const termsByContract = new Map<string, H85TermOption>()
    for (const r of targets) {
      const months = resolveEffectiveLeaseTermMonths(r)
      if (months <= 0 || !r.contractNo.trim()) continue
      termsByContract.set(r.contractNo.trim(), {
        recordId: r.recordId,
        contractNo: r.contractNo.trim(),
        months,
        conclusion: r.conclusion,
        commencementDate: r.commencementDate,
        termEndDate: r.termEndDate,
      })
    }
    if (!termsByContract.size) {
      return {
        ok: false,
        reason: '有效租赁期为 0，请先确定租赁期或采用建议值',
        updated: 0,
        unmatchedContracts: [],
        details: [],
      }
    }

    const raw = _getJson(H88_DEP_ROWS_KEY)
    const list = Array.isArray(raw) ? raw : []
    if (!list.length) {
      return {
        ok: false,
        reason: 'H8-8 尚无折旧行，请先从 H8-2 带入后再同步',
        updated: 0,
        unmatchedContracts: [...termsByContract.keys()],
        details: [],
      }
    }

    const onlyContractNo = recordId ? targets[0]?.contractNo : undefined
    const applied = applyH85TermsToDepRows(list, termsByContract, { onlyContractNo })
    if (applied.updated > 0) {
      onSave(H88_DEP_ROWS_KEY, applied.rows)
    }

    const result: H85ToH88SyncResult = {
      ok: applied.updated > 0 || applied.unmatchedContracts.length === 0,
      reason: applied.updated === 0
        ? (applied.unmatchedContracts.length
          ? `H8-8 无匹配合同：${applied.unmatchedContracts.join('、')}`
          : '租赁期已与 H8-5 一致，无需更新')
        : undefined,
      updated: applied.updated,
      unmatchedContracts: applied.unmatchedContracts,
      details: applied.details,
    }
    if (applied.updated > 0) {
      try {
        window.dispatchEvent(new CustomEvent('h8:lease-term-synced', {
          detail: { source: 'H8-5→H8-8', ...result },
        }))
      } catch { /* ignore */ }
    }
    return result
  }

  /**
   * 将短期租赁候选（≤12月、无购买选择权）推送到 H8-13：
   * 已有合同更新租期；缺失则新增检查行骨架。
   */
  function pushShortTermToH813(recordId?: string): H85ToH813SyncResult {
    if (!onSave) {
      return {
        ok: false, reason: '无法保存（只读或未挂载 onSave）',
        updated: 0, added: 0, skippedPurchaseOption: 0, details: [],
      }
    }

    const pool = recordId
      ? records.value.filter(r => r.recordId === recordId)
      : records.value

    let skippedPurchaseOption = 0
    const candidates: H85TermOption[] = []
    for (const r of pool) {
      const months = resolveEffectiveLeaseTermMonths(r)
      if (months <= 0) continue
      if (r.purchaseReasonablyCertain === '是') {
        if (months <= 12) skippedPurchaseOption++
        continue
      }
      if (months > 12) continue
      if (!r.contractNo.trim()) continue
      candidates.push({
        recordId: r.recordId,
        contractNo: r.contractNo.trim(),
        months,
        conclusion: r.conclusion,
        commencementDate: r.commencementDate,
        termEndDate: r.termEndDate,
      })
    }

    if (!candidates.length) {
      return {
        ok: false,
        reason: skippedPurchaseOption
          ? '含购买选择权的租赁不属于短期租赁（CAS21），未推送'
          : '无短期租赁候选（有效租赁期≤12月）',
        updated: 0,
        added: 0,
        skippedPurchaseOption,
        details: [],
      }
    }

    const raw = _getJson(H813_ROWS_KEY)
    const list = Array.isArray(raw) ? raw : []
    const onlyContractNo = recordId ? pool[0]?.contractNo : undefined
    const applied = upsertH85ShortTermIntoH813Rows(list, candidates, {
      onlyContractNo,
      addMissing: true,
    })

    if (applied.updated + applied.added > 0) {
      onSave(H813_ROWS_KEY, applied.rows)
    }

    const result: H85ToH813SyncResult = {
      ok: applied.updated + applied.added > 0,
      reason: applied.updated + applied.added === 0
        ? 'H8-13 已包含这些短期合同且租期一致'
        : undefined,
      updated: applied.updated,
      added: applied.added,
      skippedPurchaseOption,
      details: applied.details,
    }
    if (result.ok) {
      try {
        window.dispatchEvent(new CustomEvent('h8:lease-term-synced', {
          detail: { source: 'H8-5→H8-13', ...result },
        }))
      } catch { /* ignore */ }
    }
    return result
  }

  /** 读取 H8-6 当前租赁期，用于差异提示 */
  function readH86LeaseTermMonths(): number {
    const p = _getJson(H86_PARAMS_KEY)
    return Number(p?.leaseTermMonths) || 0
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(RECORDS_KEY, records.value.map(r => ({ ...r })))
  }

  return {
    records,
    completedCount,
    avgLeaseTerm,
    reassessmentNeededCount,
    shortTermCandidates,
    shortTermCandidateCount,
    addRecord,
    deleteRecord,
    updateField,
    applySuggestedTerm,
    pushLeaseTermToH86,
    pushLeaseTermToH88,
    pushShortTermToH813,
    readH86LeaseTermMonths,
    save,
    load,
    calcLeaseTermMonths,
    calcReassessmentConclusion,
    resolveEffectiveLeaseTermMonths,
    needsTermModification,
  }
}

export default useH8LeaseTerm
