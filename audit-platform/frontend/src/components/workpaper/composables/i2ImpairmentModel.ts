/**
 * i2ImpairmentModel — I2-15 减值准备测试纯函数
 *
 * 对齐致同「减值准备测试表 I2-15」Excel：
 *   有迹象① → 是否测试 → ②账面 → ③公允净额 / ④DCF现值
 *   → ⑤=MAX(③,④) → ⑥=MAX(②−⑤,0) → ⑧=⑥−⑦（可正补提/负冲回）
 *
 * 与 I1-12 差异：开发支出底稿按事务所模板允许⑧为负（冲回）；
 * 无「寿命不确定须每年测试」闸门，以减值迹象驱动须测试。
 */

export type I2Yn = 'Y' | 'N' | ''

export interface I2ImpairmentTestRow {
  rowId: string
  /** 开发支出项目名称 */
  name: string
  /** 是否存在减值迹象 */
  hasIndication: I2Yn
  /** ① 减值迹象描述 */
  indicationDesc: string
  /** 是否进行减值测试（有迹象则须测；可手工强制） */
  needTest: boolean
  /** ② 账面价值（资本化期末−摊销，不含减值） */
  bookValue: number
  /** ③ 公允价值减去处置费用的净额 */
  fairValueLessDisposal: number
  /** ④ 预计未来现金流量现值 */
  dcfValue: number
  /** ⑤ 可收回金额 = MAX(③,④)；无须测试时为 0 */
  recoverableAmount: number
  /** ⑥ 期末应计提减值 = MAX(②−⑤, 0) */
  shouldProvision: number
  /** ⑦ 期末账面已计提减值 */
  alreadyProvided: number
  /** ⑧ 本期应补提或冲回 = ⑥ − ⑦（正=补提，负=冲回） */
  difference: number
  /** 工作底稿索引号 */
  indexRef: string
  /** 备注 */
  remark: string
  /** 行结论：无需测试/无需计提/需补提/应冲回 */
  conclusion: string
  /** 是否关联 I2-16 */
  linkedToDcf: boolean
  /** 来源 I2-2 行 id */
  sourceDetailRowId?: string
}

export interface I2ImpairmentSummary {
  totalBookValue: number
  totalFairValue: number
  totalDcf: number
  totalRecoverable: number
  totalShouldProvision: number
  totalAlreadyProvided: number
  totalDifference: number
  /** ⑧>0 合计 */
  totalSupplement: number
  /** ⑧<0 合计（绝对值） */
  totalReversal: number
}

export interface I2ImpPrepValidation {
  ok: boolean
  messages: string[]
}

function _getNum(val: unknown): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _yn(v: unknown): I2Yn {
  const s = String(v ?? '').trim().toUpperCase()
  if (s === 'Y' || s === '是' || s === '√' || s === 'TRUE' || s === '1') return 'Y'
  if (s === 'N' || s === '否' || s === '×' || s === 'FALSE' || s === '0') return 'N'
  return ''
}

export function genI2ImpRowId(prefix = 'i2imp15'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * 是否测试：Excel 中与「有迹象」分列。
 * - 有迹象(Y) → 默认须测
 * - 无迹象(N) → 默认不测（仍可用 manualNeedTest 强制测）
 * - 未填 → 尊重手工 needTest
 */
export function resolveI2NeedTest(hasIndication: I2Yn, manualNeedTest?: boolean): boolean {
  if (hasIndication === 'Y') return true
  if (hasIndication === 'N') return Boolean(manualNeedTest)
  return Boolean(manualNeedTest)
}

/** ⑤ = needTest ? MAX(③,④) : 0 */
export function calcI2ImpairmentRecoverable(
  fairValueLessDisposal: number,
  dcfValue: number,
  needTest: boolean,
): number {
  if (!needTest) return 0
  return Math.max(_getNum(fairValueLessDisposal), _getNum(dcfValue))
}

/** ⑥ = needTest ? MAX(②−⑤, 0) : 0 */
export function calcI2RequiredImpairment(
  bookValue: number,
  recoverableAmount: number,
  needTest: boolean,
): number {
  if (!needTest) return 0
  return Math.max(_getNum(bookValue) - _getNum(recoverableAmount), 0)
}

/** ⑧ = ⑥ − ⑦ */
export function calcI2ImpairmentAdjustment(shouldProvision: number, alreadyProvided: number): number {
  return _getNum(shouldProvision) - _getNum(alreadyProvided)
}

export function suggestI2ImpairmentConclusion(row: Pick<
  I2ImpairmentTestRow,
  'needTest' | 'difference' | 'shouldProvision' | 'alreadyProvided'
>): string {
  if (!row.needTest) return '无需测试'
  if (Math.abs(row.difference) < 0.005) {
    return row.shouldProvision < 0.005 && row.alreadyProvided < 0.005 ? '无需计提' : '计提适当'
  }
  if (row.difference > 0) return '需补提'
  return '应冲回'
}

export function recomputeI2ImpairmentRow(
  row: I2ImpairmentTestRow,
  opts?: { refreshConclusion?: boolean },
): I2ImpairmentTestRow {
  const hasIndication = _yn(row.hasIndication)
  const needTest = resolveI2NeedTest(hasIndication, row.needTest)

  const bookValue = _getNum(row.bookValue)
  const fairValueLessDisposal = _getNum(row.fairValueLessDisposal)
  const dcfValue = _getNum(row.dcfValue)
  const recoverableAmount = calcI2ImpairmentRecoverable(fairValueLessDisposal, dcfValue, needTest)
  const shouldProvision = calcI2RequiredImpairment(bookValue, recoverableAmount, needTest)
  const alreadyProvided = _getNum(row.alreadyProvided)
  // 未测试时⑧不计算（避免「无迹象却显示应冲回」的噪声）
  const difference = needTest
    ? calcI2ImpairmentAdjustment(shouldProvision, alreadyProvided)
    : 0
  const indicationDesc = hasIndication === 'N' ? '' : (row.indicationDesc || '')
  const auto = suggestI2ImpairmentConclusion({ needTest, difference, shouldProvision, alreadyProvided })
  const conclusion = opts?.refreshConclusion || !row.conclusion?.trim()
    ? auto
    : row.conclusion

  return {
    ...row,
    hasIndication,
    needTest,
    bookValue,
    fairValueLessDisposal,
    dcfValue,
    recoverableAmount,
    shouldProvision,
    alreadyProvided,
    difference,
    indicationDesc,
    conclusion,
  }
}

export function emptyI2ImpairmentRow(partial?: Partial<I2ImpairmentTestRow>): I2ImpairmentTestRow {
  return recomputeI2ImpairmentRow({
    rowId: partial?.rowId ?? genI2ImpRowId(),
    name: '',
    hasIndication: '',
    indicationDesc: '',
    needTest: false,
    bookValue: 0,
    fairValueLessDisposal: 0,
    dcfValue: 0,
    recoverableAmount: 0,
    shouldProvision: 0,
    alreadyProvided: 0,
    difference: 0,
    indexRef: '',
    remark: '',
    conclusion: '',
    linkedToDcf: false,
    ...partial,
  })
}

/** 兼容旧版扁平字段（仅 recoverableAmount，无③④拆分） */
export function normalizeI2ImpairmentRow(raw: any): I2ImpairmentTestRow {
  const fair = _getNum(raw.fairValueLessDisposal)
  const dcf = _getNum(raw.dcfValue)
  const legacyRecoverable = _getNum(raw.recoverableAmount)
  // 旧数据只有合计可收回：记入④，③=0，便于公式链仍可用
  const fairValueLessDisposal = fair
  const dcfValue = dcf > 0 || fair > 0 ? dcf : legacyRecoverable

  let hasIndication = _yn(raw.hasIndication)
  // 旧数据无迹象字段：若已有可收回/应计提，视为须测试
  const legacyNeed = Boolean(raw.needTest) || legacyRecoverable > 0 || _getNum(raw.shouldProvision) > 0
  if (!hasIndication && legacyNeed) hasIndication = 'Y'

  return recomputeI2ImpairmentRow({
    rowId: raw.rowId ?? genI2ImpRowId(),
    name: String(raw.name ?? '').trim(),
    hasIndication,
    indicationDesc: String(raw.indicationDesc ?? ''),
    needTest: legacyNeed || hasIndication === 'Y',
    bookValue: _getNum(raw.bookValue),
    fairValueLessDisposal,
    dcfValue,
    recoverableAmount: 0,
    shouldProvision: 0,
    alreadyProvided: _getNum(raw.alreadyProvided),
    difference: 0,
    indexRef: String(raw.indexRef ?? ''),
    remark: String(raw.remark ?? ''),
    conclusion: String(raw.conclusion ?? ''),
    linkedToDcf: Boolean(raw.linkedToDcf),
    sourceDetailRowId: raw.sourceDetailRowId ? String(raw.sourceDetailRowId) : undefined,
  })
}

export function summarizeI2Impairment(rows: I2ImpairmentTestRow[]): I2ImpairmentSummary {
  const s: I2ImpairmentSummary = {
    totalBookValue: 0,
    totalFairValue: 0,
    totalDcf: 0,
    totalRecoverable: 0,
    totalShouldProvision: 0,
    totalAlreadyProvided: 0,
    totalDifference: 0,
    totalSupplement: 0,
    totalReversal: 0,
  }
  for (const r of rows) {
    s.totalBookValue += r.bookValue
    s.totalFairValue += r.fairValueLessDisposal
    s.totalDcf += r.dcfValue
    s.totalRecoverable += r.recoverableAmount
    s.totalShouldProvision += r.shouldProvision
    s.totalAlreadyProvided += r.alreadyProvided
    s.totalDifference += r.difference
    if (r.difference > 0.005) s.totalSupplement += r.difference
    if (r.difference < -0.005) s.totalReversal += -r.difference
  }
  return s
}

export function validateI2ImpairmentPrep(rows: I2ImpairmentTestRow[]): I2ImpPrepValidation {
  const messages: string[] = []
  for (const r of rows) {
    if (!r.name && !r.bookValue && !r.needTest) continue
    if (r.hasIndication === 'Y' && !r.indicationDesc.trim()) {
      messages.push(`「${r.name || r.rowId}」有减值迹象但未填写①迹象描述`)
    }
    if (!r.needTest && r.alreadyProvided > 0.01) {
      messages.push(`「${r.name || r.rowId}」未进行减值测试但账面已计提减值 ${r.alreadyProvided.toFixed(2)}，请核实`)
    }
    if (r.needTest) {
      if (!/I2-16/i.test(r.indexRef || '') && r.linkedToDcf === false && r.recoverableAmount <= 0) {
        messages.push(`「${r.name || r.rowId}」须进行减值测试，请完成 I2-16 可收回测算并回填，或手工录入③④`)
      }
      if (r.bookValue > 0 && r.recoverableAmount <= 0) {
        messages.push(`「${r.name || r.rowId}」须测试但⑤可收回金额尚未测算`)
      }
    }
  }
  return { ok: messages.length === 0, messages }
}

/**
 * 从 I2-2 明细带入：②=资本化期末−摊销（净值+已提减值），⑦=已提减值
 */
export function seedRowsFromI2Detail(detailRows: any[]): I2ImpairmentTestRow[] {
  const out: I2ImpairmentTestRow[] = []
  for (const r of detailRows ?? []) {
    const name = String(r?.projectName || r?.name || '').trim()
    if (!name || name === '合计') continue
    const capEnd = _getNum(r.capEndAmount)
    const amort = _getNum(r.capAmortization)
    const impair = _getNum(r.capImpairment)
    const net = _getNum(r.capNetValue)
    // ② 不含减值的账面价值
    const bookValue = capEnd > 0 || amort > 0
      ? Math.max(capEnd - amort, 0)
      : (net + impair) || _getNum(r.auditedEnd) || _getNum(r.bookValue)
    out.push(emptyI2ImpairmentRow({
      name,
      bookValue,
      alreadyProvided: impair,
      sourceDetailRowId: String(r.rowId ?? ''),
      remark: '自I2-2带入',
      indexRef: '',
    }))
  }
  return out
}

/**
 * 构建减值补提调整分录提示文案（借：资产减值损失／贷：开发支出减值准备）
 * supplement ≤ 0 时返回空字符串（无需提示）
 */
export function buildI2ImpairmentAdjustmentHint(supplement: number): string {
  const n = _getNum(supplement)
  if (n <= 0.005) return ''
  const amt = n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `建议调整分录：借：资产减值损失 ${amt}；贷：开发支出减值准备 ${amt}。`
}

/** 推送给父级（如 K11 资产减值损失汇总）的 `impairment:calculated` CustomEvent detail */
export interface I2ImpairmentEventDetail {
  wpCode: string
  wp_code: string
  sheetCode: string
  totalRequiredProvision: number
  amount: number
  label: string
  impairmentAmount: number
}

/** 构建 impairment:calculated 事件 detail（纯函数，便于单测） */
export function buildI2ImpairmentEventDetail(summary: I2ImpairmentSummary): I2ImpairmentEventDetail {
  return {
    wpCode: 'I2',
    wp_code: 'I2',
    sheetCode: 'I2-15',
    totalRequiredProvision: summary.totalSupplement,
    amount: summary.totalSupplement,
    label: '本期补提⑧',
    impairmentAmount: summary.totalShouldProvision,
  }
}

/** 编制提示（对齐 Excel 底栏 CAS1321 指引） */
export const I2_15_PROCEDURE_HINTS: string[] = [
  '检查减值测试方法是否与企业会计准则一致，重点关注折现率、预测期现金流及终值假设。',
  '结合市场调研、商业计划及管理层访谈，评估资本化项目的商业可行性与减值迹象识别是否充分。',
  '与管理层讨论市场前景及关键假设；必要时评价外部专家工作（参照 CAS 1301）。',
  '将上年估计与本年实际结果对比，执行追溯复核，关注管理层偏向。',
  '依据 CAS 1321《会计估计和相关披露的审计》及 CAS6/CAS8 形成审计结论。',
]
