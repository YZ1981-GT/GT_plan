/**
 * useI5Detail — I5-2 其他非流动资产明细表（对齐致同 Excel 滚动勾稽）
 *
 * Excel 结构（A1:P48）：
 *   未审数 B–E（期末=期初+增−减）
 *   期初调整 F–G（账项 / 重分类）
 *   账项调整 H–I（本期增/减）
 *   重分类调整 J–K（本期增/减）
 *   审定数 L–O：
 *     L=B+F+G  M=C+H+J  N=D+I+K  O=L+M−N
 *   三层：原值 → 减值准备 → 净值(=原值−减值)
 *
 * HTML 区段：
 *   0 原值未审 | 1 原值调整与审定 | 2 减值准备 | 3 净值与索引
 *
 * 兼容旧 26 列三区段字段（beginBalance/increase/…），由净值审定回写，
 * 供 I5-1 / CrossSheet / 一致性检查继续读取。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcAssetEndBalance, calcSubtotal } from './useI5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 单层滚动金额块（未审 → 调整 → 审定） */
export interface I5RollAmounts {
  unadjOpening: number
  unadjIncrease: number
  unadjDecrease: number
  /** 公式：期初+增加−减少 */
  unadjEnding: number
  /** 期初调整·账项 F */
  openingAje: number
  /** 期初调整·重分类 G */
  openingRje: number
  /** 账项调整·本期增加 H */
  ajeIncrease: number
  /** 账项调整·本期减少 I */
  ajeDecrease: number
  /** 重分类调整·本期增加 J */
  rjeIncrease: number
  /** 重分类调整·本期减少 K */
  rjeDecrease: number
  /** 公式 L=B+F+G */
  auditedOpening: number
  /** 公式 M=C+H+J */
  auditedIncrease: number
  /** 公式 N=D+I+K */
  auditedDecrease: number
  /** 公式 O=L+M−N */
  auditedEnding: number
}

export interface I5DetailRow {
  rowId: string
  /** 项目名称（Excel A 列） */
  projectName: string
  /** @deprecated 别名 → projectName */
  name: string
  /** 模板内置行（可改名但默认骨架） */
  isBuiltin: boolean
  /** 跨底稿索引提示，如 D7 / M12 / G2-13 */
  indexRef: string
  remark: string

  gross: I5RollAmounts
  impairment: I5RollAmounts

  // ── 旧字段别名（回写净值审定，供下游）──
  /** @deprecated → net.auditedOpening */
  beginBalance: number
  /** @deprecated → net.auditedIncrease */
  increase: number
  /** @deprecated → net.auditedDecrease */
  decrease: number
  /** @deprecated → net.auditedEnding */
  endBalance: number
  /** @deprecated → net.unadjEnding */
  unadjusted: number
  category: string
  incurredDate: string
  maturityDate: string
  /** 剩余月数（可选；不填则按 maturityDate 推算） */
  remainingMonths: number | null
  summary: string
  contractNo: string
  counterparty: string
  indexNo: string
  increaseReason: string
  decreaseReason: string
  originalAmount: number
  accumulatedAmount: number
  netValue: number
  voucherRef: string
  voucherDate: string
  checkMethod: string
  checkResult: string
  conclusion: string
  isAbnormal: boolean
  reviewMark: string
  status: string
}

export type I5DetailSection = 0 | 1 | 2 | 3

export const I5_DETAIL_SECTION_LABELS = [
  '原值未审',
  '原值调整与审定',
  '减值准备',
  '净值与索引',
] as const

export const I5_2_OBJECTIVES = [
  '复核其他非流动资产确认和会计处理的正确性。',
  '通过未审→期初调整/账项/重分类→审定滚动，核实各类别原值、减值及净值。',
  '核对合同资产/合同成本流动性分类，并与相关专项底稿索引勾稽。',
] as const

export const I5_2_PREP_NOTES = [
  '本表按「原值 → 减值准备 → 净值」三层编制；净值各列 = 原值 − 减值（与 Excel 一致）。',
  '未审期末 = 期初 + 本期增加 − 本期减少；审定期初 = 未审期初 + 期初账项调整 + 期初重分类调整。',
  '审定增加 = 未审增加 + 账项增加 + 重分类增加；审定减少 = 未审减少 + 账项减少 + 重分类减少；审定期末 = 审定期初 + 审定增加 − 审定减少。',
  '合同资产、合同取得成本、合同履约成本、应收退货成本须按 CAS14 判断流动性，一年以上部分才列示于本表。',
] as const

export const I5_2_CAS14_TIPS = [
  '「合同资产」与「合同负债」应按履约义务与客户付款关系列示；同一合同下以净额列示。净额为借方的，按流动性在「合同资产」或「其他非流动资产」填列，并扣除合同资产减值准备。',
  '也可设置「合同结算」科目：借方余额按流动性列「合同资产/其他非流动资产」，贷方余额列「合同负债/其他非流动负债」。',
  '合同取得成本：初始确认时摊销期限超过一年或一个正常营业周期的，在「其他非流动资产」列示，并扣除减值准备。',
  '合同履约成本：摊销期限超过一年或一个正常营业周期的，在「其他非流动资产」列示（一年以内通常列存货），并扣除减值准备。',
  '应收退货成本：一年或一个正常营业周期内出售的列「其他流动资产」，否则列「其他非流动资产」。',
] as const

export interface I5DetailSubtotals {
  grossUnadjEnding: number
  grossAuditedEnding: number
  impAuditedEnding: number
  netUnadjEnding: number
  netAuditedOpening: number
  netAuditedIncrease: number
  netAuditedDecrease: number
  netAuditedEnding: number
  // legacy
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  originalAmount: number
  accumulatedAmount: number
  netValue: number
}

export interface I5DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'formula' | 'chip'
  tooltip?: string
  /** nested path under row, e.g. gross.unadjOpening */
  path?: string
}

export interface I5RollWarning {
  rowId: string
  projectName: string
  layer: 'gross' | 'impairment' | 'net'
  kind: 'unadj' | 'audited' | 'negative' | 'imp_gt_gross'
  message: string
}

export interface I5BuiltinCategory {
  name: string
  indexRef: string
  navigateHint?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'I5-2-rows'
const TOL = 0.05

/** 对齐 Excel A11:A21 默认项目 + 跨表索引（Q 列） */
export const I5_BUILTIN_CATEGORIES: I5BuiltinCategory[] = [
  { name: '预付土地出让金', indexRef: '' },
  { name: '预付工程款', indexRef: '' },
  { name: '预付房屋、设备款', indexRef: '' },
  { name: '无形资产预付款', indexRef: '' },
  { name: '预付投资款', indexRef: '' },
  { name: '委托贷款', indexRef: '' },
  { name: '合同资产', indexRef: 'D7', navigateHint: 'D7 合同资产' },
  { name: '合同取得成本', indexRef: 'M12', navigateHint: 'M12 合同取得成本及减值准备' },
  { name: '合同履约成本', indexRef: 'G2-13', navigateHint: 'G2-13 合同履约成本' },
  { name: '应收退货成本', indexRef: '' },
]

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

function generateRowId(): string {
  return `i52-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function emptyI5RollAmounts(partial?: Partial<I5RollAmounts>): I5RollAmounts {
  return {
    unadjOpening: 0,
    unadjIncrease: 0,
    unadjDecrease: 0,
    unadjEnding: 0,
    openingAje: 0,
    openingRje: 0,
    ajeIncrease: 0,
    ajeDecrease: 0,
    rjeIncrease: 0,
    rjeDecrease: 0,
    auditedOpening: 0,
    auditedIncrease: 0,
    auditedDecrease: 0,
    auditedEnding: 0,
    ...partial,
  }
}

/** Excel 滚动公式 */
export function recalcI5RollAmounts(block: I5RollAmounts): void {
  block.unadjOpening = _num(block.unadjOpening)
  block.unadjIncrease = _num(block.unadjIncrease)
  block.unadjDecrease = _num(block.unadjDecrease)
  block.openingAje = _num(block.openingAje)
  block.openingRje = _num(block.openingRje)
  block.ajeIncrease = _num(block.ajeIncrease)
  block.ajeDecrease = _num(block.ajeDecrease)
  block.rjeIncrease = _num(block.rjeIncrease)
  block.rjeDecrease = _num(block.rjeDecrease)

  block.unadjEnding = _round2(calcAssetEndBalance(
    block.unadjOpening,
    block.unadjIncrease,
    block.unadjDecrease,
  ))
  block.auditedOpening = _round2(block.unadjOpening + block.openingAje + block.openingRje)
  block.auditedIncrease = _round2(block.unadjIncrease + block.ajeIncrease + block.rjeIncrease)
  block.auditedDecrease = _round2(block.unadjDecrease + block.ajeDecrease + block.rjeDecrease)
  block.auditedEnding = _round2(calcAssetEndBalance(
    block.auditedOpening,
    block.auditedIncrease,
    block.auditedDecrease,
  ))
}

export function subtractI5Roll(a: I5RollAmounts, b: I5RollAmounts): I5RollAmounts {
  const out = emptyI5RollAmounts({
    unadjOpening: _round2(a.unadjOpening - b.unadjOpening),
    unadjIncrease: _round2(a.unadjIncrease - b.unadjIncrease),
    unadjDecrease: _round2(a.unadjDecrease - b.unadjDecrease),
    openingAje: _round2(a.openingAje - b.openingAje),
    openingRje: _round2(a.openingRje - b.openingRje),
    ajeIncrease: _round2(a.ajeIncrease - b.ajeIncrease),
    ajeDecrease: _round2(a.ajeDecrease - b.ajeDecrease),
    rjeIncrease: _round2(a.rjeIncrease - b.rjeIncrease),
    rjeDecrease: _round2(a.rjeDecrease - b.rjeDecrease),
  })
  recalcI5RollAmounts(out)
  // 净值期末用原值期末−减值期末，避免分列相减后三角漂移
  out.unadjEnding = _round2(a.unadjEnding - b.unadjEnding)
  out.auditedOpening = _round2(a.auditedOpening - b.auditedOpening)
  out.auditedIncrease = _round2(a.auditedIncrease - b.auditedIncrease)
  out.auditedDecrease = _round2(a.auditedDecrease - b.auditedDecrease)
  out.auditedEnding = _round2(a.auditedEnding - b.auditedEnding)
  return out
}

export function getI5NetRoll(row: I5DetailRow): I5RollAmounts {
  return subtractI5Roll(row.gross, row.impairment)
}

/** 回写旧字段别名（I5-1 / CrossSheet 读净值审定） */
export function syncI5DetailLegacyAliases(row: I5DetailRow): void {
  const net = getI5NetRoll(row)
  row.name = row.projectName
  row.beginBalance = net.auditedOpening
  row.increase = net.auditedIncrease
  row.decrease = net.auditedDecrease
  row.endBalance = net.auditedEnding
  row.unadjusted = net.unadjEnding
  row.netValue = net.auditedEnding
  row.originalAmount = row.gross.auditedEnding
  row.accumulatedAmount = row.impairment.auditedEnding
  row.category = row.category || row.projectName
  row.indexNo = row.indexNo || row.indexRef
}

export function emptyI5DetailRow(partial?: Partial<I5DetailRow>): I5DetailRow {
  const row: I5DetailRow = {
    rowId: generateRowId(),
    projectName: '',
    name: '',
    isBuiltin: false,
    indexRef: '',
    remark: '',
    gross: emptyI5RollAmounts(),
    impairment: emptyI5RollAmounts(),
    beginBalance: 0,
    increase: 0,
    decrease: 0,
    endBalance: 0,
    unadjusted: 0,
    category: '',
    incurredDate: '',
    maturityDate: '',
    remainingMonths: null,
    summary: '',
    contractNo: '',
    counterparty: '',
    indexNo: '',
    increaseReason: '',
    decreaseReason: '',
    originalAmount: 0,
    accumulatedAmount: 0,
    netValue: 0,
    voucherRef: '',
    voucherDate: '',
    checkMethod: '',
    checkResult: '',
    conclusion: '',
    isAbnormal: false,
    reviewMark: '',
    status: '未检查',
  }
  if (partial) Object.assign(row, partial)
  if (partial?.gross) row.gross = emptyI5RollAmounts(partial.gross)
  if (partial?.impairment) row.impairment = emptyI5RollAmounts(partial.impairment)
  recalcI5DetailRow(row)
  return row
}

function _migrateLegacyRoll(raw: any): Partial<I5RollAmounts> {
  return {
    unadjOpening: _num(raw.unadjOpening ?? raw.beginBalance ?? raw.期初),
    unadjIncrease: _num(raw.unadjIncrease ?? raw.increase ?? raw.本期增加 ?? raw.增加),
    unadjDecrease: _num(raw.unadjDecrease ?? raw.decrease ?? raw.本期减少 ?? raw.减少),
    openingAje: _num(raw.openingAje ?? raw.期初账项调整),
    openingRje: _num(raw.openingRje ?? raw.期初重分类调整),
    ajeIncrease: _num(raw.ajeIncrease ?? raw.账项增加),
    ajeDecrease: _num(raw.ajeDecrease ?? raw.账项减少),
    rjeIncrease: _num(raw.rjeIncrease ?? raw.重分类增加),
    rjeDecrease: _num(raw.rjeDecrease ?? raw.重分类减少),
  }
}

export function normalizeI5DetailRow(raw: any): I5DetailRow {
  if (!raw || typeof raw !== 'object') return emptyI5DetailRow()

  const projectName = _str(raw.projectName || raw.name || raw.项目).trim()
  const builtin = I5_BUILTIN_CATEGORIES.find((c) => c.name === projectName)

  let gross: I5RollAmounts
  let impairment: I5RollAmounts

  if (raw.gross && typeof raw.gross === 'object') {
    gross = emptyI5RollAmounts(raw.gross)
    impairment = emptyI5RollAmounts(raw.impairment || {})
  } else if (raw.layer === 'impairment') {
    gross = emptyI5RollAmounts()
    impairment = emptyI5RollAmounts(_migrateLegacyRoll(raw))
  } else {
    gross = emptyI5RollAmounts(_migrateLegacyRoll(raw))
    impairment = emptyI5RollAmounts(
      raw.impairment && typeof raw.impairment === 'object'
        ? raw.impairment
        : {
            unadjOpening: _num(raw.impUnadjOpening),
            unadjIncrease: _num(raw.impUnadjIncrease),
            unadjDecrease: _num(raw.impUnadjDecrease),
            openingAje: _num(raw.impOpeningAje),
            openingRje: _num(raw.impOpeningRje),
            ajeIncrease: _num(raw.impAjeIncrease),
            ajeDecrease: _num(raw.impAjeDecrease),
            rjeIncrease: _num(raw.impRjeIncrease),
            rjeDecrease: _num(raw.impRjeDecrease),
          },
    )
  }

  return emptyI5DetailRow({
    rowId: _str(raw.rowId) || generateRowId(),
    projectName,
    name: projectName,
    isBuiltin: raw.isBuiltin === true || !!builtin,
    indexRef: _str(raw.indexRef || raw.indexNo || builtin?.indexRef || ''),
    remark: _str(raw.remark ?? raw.备注),
    gross,
    impairment,
    category: _str(raw.category),
    incurredDate: _str(raw.incurredDate),
    maturityDate: _str(raw.maturityDate ?? raw.dueDate),
    remainingMonths: raw.remainingMonths != null && raw.remainingMonths !== ''
      ? _num(raw.remainingMonths)
      : null,
    summary: _str(raw.summary),
    contractNo: _str(raw.contractNo),
    counterparty: _str(raw.counterparty),
    indexNo: _str(raw.indexNo || raw.indexRef || ''),
    increaseReason: _str(raw.increaseReason),
    decreaseReason: _str(raw.decreaseReason),
    voucherRef: _str(raw.voucherRef),
    voucherDate: _str(raw.voucherDate),
    checkMethod: _str(raw.checkMethod),
    checkResult: _str(raw.checkResult),
    conclusion: _str(raw.conclusion),
    isAbnormal: raw.isAbnormal === true,
    reviewMark: _str(raw.reviewMark),
    status: _str(raw.status) || '未检查',
  })
}

export function recalcI5DetailRow(row: I5DetailRow): void {
  if (!row.gross) row.gross = emptyI5RollAmounts()
  if (!row.impairment) row.impairment = emptyI5RollAmounts()
  const g = row.gross
  const hasGross = [g.unadjOpening, g.unadjIncrease, g.unadjDecrease, g.openingAje, g.openingRje,
    g.ajeIncrease, g.ajeDecrease, g.rjeIncrease, g.rjeDecrease].some((n) => Math.abs(_num(n)) > 0.005)
  if (!hasGross && (row.beginBalance || row.increase || row.decrease)) {
    g.unadjOpening = _num(row.beginBalance)
    g.unadjIncrease = _num(row.increase)
    g.unadjDecrease = _num(row.decrease)
  }
  recalcI5RollAmounts(row.gross)
  recalcI5RollAmounts(row.impairment)
  if (!row.projectName && row.name) row.projectName = row.name
  if (!row.name) row.name = row.projectName
  syncI5DetailLegacyAliases(row)
}

export function collectI5RollWarnings(rows: I5DetailRow[]): I5RollWarning[] {
  const warnings: I5RollWarning[] = []
  for (const row of rows) {
    const name = row.projectName || '未命名'
    for (const layer of ['gross', 'impairment'] as const) {
      const block = row[layer]
      const expectUnadj = _round2(calcAssetEndBalance(block.unadjOpening, block.unadjIncrease, block.unadjDecrease))
      if (Math.abs(expectUnadj - block.unadjEnding) > TOL) {
        warnings.push({
          rowId: row.rowId,
          projectName: name,
          layer,
          kind: 'unadj',
          message: `${layer === 'gross' ? '原值' : '减值'}未审期末不平（期望 ${expectUnadj}）`,
        })
      }
      const expectAud = _round2(calcAssetEndBalance(block.auditedOpening, block.auditedIncrease, block.auditedDecrease))
      if (Math.abs(expectAud - block.auditedEnding) > TOL) {
        warnings.push({
          rowId: row.rowId,
          projectName: name,
          layer,
          kind: 'audited',
          message: `${layer === 'gross' ? '原值' : '减值'}审定期末不平（期望 ${expectAud}）`,
        })
      }
    }
    if (row.impairment.auditedEnding - row.gross.auditedEnding > TOL) {
      warnings.push({
        rowId: row.rowId,
        projectName: name,
        layer: 'impairment',
        kind: 'imp_gt_gross',
        message: '减值审定期末大于原值审定期末',
      })
    }
    const net = getI5NetRoll(row)
    if (net.auditedEnding < -TOL) {
      warnings.push({
        rowId: row.rowId,
        projectName: name,
        layer: 'net',
        kind: 'negative',
        message: `净值审定期末为负（${net.auditedEnding}）`,
      })
    }
  }
  return warnings
}

export function buildI5DetailConclusionDraft(opts: {
  rowCount: number
  netAuditedEnding: number
  grossAuditedEnding: number
  impAuditedEnding: number
  warningCount: number
}): string {
  const parts = [
    `其他非流动资产明细表共 ${opts.rowCount} 个类别；原值审定合计 ${opts.grossAuditedEnding.toFixed(2)}，减值 ${opts.impAuditedEnding.toFixed(2)}，净值 ${opts.netAuditedEnding.toFixed(2)}。`,
  ]
  if (opts.warningCount > 0) {
    parts.push(`存在 ${opts.warningCount} 处滚动/减值勾稽提示，已复核处理。`)
  } else {
    parts.push('未审→调整→审定滚动勾稽平衡，净值=原值−减值。')
  }
  parts.push('合同相关项目已按 CAS14 关注流动性分类及跨底稿索引。')
  return parts.join('')
}

export function createI5BuiltinRows(): I5DetailRow[] {
  return I5_BUILTIN_CATEGORIES.map((c) => emptyI5DetailRow({
    projectName: c.name,
    name: c.name,
    isBuiltin: true,
    indexRef: c.indexRef,
    indexNo: c.indexRef,
  }))
}

// ─── Column defs ─────────────────────────────────────────────────────────────

function col(
  key: string,
  label: string,
  width: number,
  opts: Partial<I5DetailColumn> & { path?: string } = {},
): I5DetailColumn {
  return {
    key,
    label,
    width,
    editable: opts.editable ?? false,
    type: opts.type ?? 'text',
    tooltip: opts.tooltip,
    path: opts.path,
  }
}

const GROSS_UNADJ_COLS: I5DetailColumn[] = [
  col('projectName', '项目', 160, { editable: true, type: 'text' }),
  col('gross.unadjOpening', '未审期初', 120, { editable: true, type: 'number', path: 'gross.unadjOpening' }),
  col('gross.unadjIncrease', '未审增加', 120, { editable: true, type: 'number', path: 'gross.unadjIncrease' }),
  col('gross.unadjDecrease', '未审减少', 120, { editable: true, type: 'number', path: 'gross.unadjDecrease' }),
  col('gross.unadjEnding', '未审期末', 120, {
    type: 'formula', path: 'gross.unadjEnding', tooltip: '未审期末=期初+增加−减少',
  }),
]

const GROSS_ADJ_COLS: I5DetailColumn[] = [
  col('projectName', '项目', 140, { type: 'text' }),
  col('gross.openingAje', '期初账项调整', 120, { editable: true, type: 'number', path: 'gross.openingAje' }),
  col('gross.openingRje', '期初重分类调整', 130, { editable: true, type: 'number', path: 'gross.openingRje' }),
  col('gross.ajeIncrease', '账项增加', 110, { editable: true, type: 'number', path: 'gross.ajeIncrease' }),
  col('gross.ajeDecrease', '账项减少', 110, { editable: true, type: 'number', path: 'gross.ajeDecrease' }),
  col('gross.rjeIncrease', '重分类增加', 110, { editable: true, type: 'number', path: 'gross.rjeIncrease' }),
  col('gross.rjeDecrease', '重分类减少', 110, { editable: true, type: 'number', path: 'gross.rjeDecrease' }),
  col('gross.auditedOpening', '审定期初', 120, {
    type: 'formula', path: 'gross.auditedOpening', tooltip: '审定期初=未审期初+期初账项+期初重分类',
  }),
  col('gross.auditedIncrease', '审定增加', 110, {
    type: 'formula', path: 'gross.auditedIncrease', tooltip: '审定增加=未审增加+账项增加+重分类增加',
  }),
  col('gross.auditedDecrease', '审定减少', 110, {
    type: 'formula', path: 'gross.auditedDecrease', tooltip: '审定减少=未审减少+账项减少+重分类减少',
  }),
  col('gross.auditedEnding', '审定期末', 120, {
    type: 'formula', path: 'gross.auditedEnding', tooltip: '审定期末=审定期初+审定增加−审定减少',
  }),
]

const IMP_COLS: I5DetailColumn[] = [
  col('projectName', '项目', 140, { type: 'text' }),
  col('impairment.unadjOpening', '未审期初', 110, { editable: true, type: 'number', path: 'impairment.unadjOpening' }),
  col('impairment.unadjIncrease', '未审增加', 110, { editable: true, type: 'number', path: 'impairment.unadjIncrease' }),
  col('impairment.unadjDecrease', '未审减少', 110, { editable: true, type: 'number', path: 'impairment.unadjDecrease' }),
  col('impairment.unadjEnding', '未审期末', 110, {
    type: 'formula', path: 'impairment.unadjEnding', tooltip: '减值未审期末=期初+增加−减少',
  }),
  col('impairment.openingAje', '期初账项', 100, { editable: true, type: 'number', path: 'impairment.openingAje' }),
  col('impairment.openingRje', '期初重分类', 100, { editable: true, type: 'number', path: 'impairment.openingRje' }),
  col('impairment.ajeIncrease', '账项增', 100, { editable: true, type: 'number', path: 'impairment.ajeIncrease' }),
  col('impairment.ajeDecrease', '账项减', 100, { editable: true, type: 'number', path: 'impairment.ajeDecrease' }),
  col('impairment.rjeIncrease', '重分类增', 100, { editable: true, type: 'number', path: 'impairment.rjeIncrease' }),
  col('impairment.rjeDecrease', '重分类减', 100, { editable: true, type: 'number', path: 'impairment.rjeDecrease' }),
  col('impairment.auditedEnding', '审定期末', 120, {
    type: 'formula', path: 'impairment.auditedEnding', tooltip: '减值审定期末（完整滚动公式）',
  }),
]

const NET_COLS: I5DetailColumn[] = [
  col('projectName', '项目', 160, { type: 'text' }),
  col('net.unadjEnding', '未审净值期末', 130, {
    type: 'formula', path: 'net.unadjEnding', tooltip: '净值未审期末=原值未审期末−减值未审期末',
  }),
  col('net.auditedOpening', '审定净值期初', 130, {
    type: 'formula', path: 'net.auditedOpening', tooltip: '净值审定期初=原值−减值',
  }),
  col('net.auditedIncrease', '审定净值增加', 130, {
    type: 'formula', path: 'net.auditedIncrease', tooltip: '净值审定增加=原值−减值',
  }),
  col('net.auditedDecrease', '审定净值减少', 130, {
    type: 'formula', path: 'net.auditedDecrease', tooltip: '净值审定减少=原值−减值',
  }),
  col('net.auditedEnding', '审定净值期末', 130, {
    type: 'formula', path: 'net.auditedEnding', tooltip: '净值审定期末=原值审定期末−减值审定期末',
  }),
  col('maturityDate', '到期日', 110, {
    editable: true,
    type: 'text',
    tooltip: 'YYYY-MM-DD；用于 I5-3 一年内到期重分类草稿筛选',
  }),
  col('remainingMonths', '剩余月数', 90, {
    editable: true,
    type: 'number',
    tooltip: '可选；不填则按到期日与审计截止日(12/31)推算',
  }),
  col('indexRef', '跨表索引', 100, { editable: true, type: 'text' }),
  col('remark', '备注', 180, { editable: true, type: 'text' }),
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI5Detail(
  allResponses: Ref<Map<string, any>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<I5DetailRow[]>([])
  const activeSection = ref<I5DetailSection>(0)
  const activeRowIndex = ref<number>(-1)

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) {
      rows.value = createI5BuiltinRows()
      return
    }
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed) && parsed.length > 0) {
        const byName = new Map<string, I5DetailRow>()
        for (const rawRow of parsed) {
          const layer = _str(rawRow?.layer)
          const name = _str(rawRow?.projectName || rawRow?.name).trim()
          if (layer === 'net' || name === '合计') continue
          if (layer === 'impairment' && name && byName.has(name)) {
            const existing = byName.get(name)!
            existing.impairment = emptyI5RollAmounts(_migrateLegacyRoll(rawRow))
            recalcI5DetailRow(existing)
            continue
          }
          if (layer === 'gross' && name && byName.has(name)) {
            const existing = byName.get(name)!
            existing.gross = emptyI5RollAmounts(_migrateLegacyRoll(rawRow))
            recalcI5DetailRow(existing)
            continue
          }
          const normalized = normalizeI5DetailRow(rawRow)
          if (!normalized.projectName) continue
          if (byName.has(normalized.projectName) && layer) {
            const existing = byName.get(normalized.projectName)!
            if (layer === 'impairment') existing.impairment = normalized.impairment
            else existing.gross = normalized.gross
            recalcI5DetailRow(existing)
          } else {
            byName.set(normalized.projectName, normalized)
          }
        }
        let list = [...byName.values()]
        for (const c of I5_BUILTIN_CATEGORIES) {
          if (!list.some((r) => r.projectName === c.name)) {
            list.push(emptyI5DetailRow({
              projectName: c.name,
              name: c.name,
              isBuiltin: true,
              indexRef: c.indexRef,
            }))
          }
        }
        const order = new Map(I5_BUILTIN_CATEGORIES.map((c, i) => [c.name, i]))
        list = list.sort((a, b) => {
          const ia = order.has(a.projectName) ? order.get(a.projectName)! : 1000
          const ib = order.has(b.projectName) ? order.get(b.projectName)! : 1000
          if (ia !== ib) return ia - ib
          return a.projectName.localeCompare(b.projectName, 'zh')
        })
        rows.value = list
      } else {
        rows.value = createI5BuiltinRows()
      }
    } catch {
      rows.value = createI5BuiltinRows()
    }
  }

  function _persist(): void {
    for (const r of rows.value) recalcI5DetailRow(r)
    options?.onSave?.(ITEM_ID_ROWS, JSON.stringify(rows.value))
  }

  const subtotals: ComputedRef<I5DetailSubtotals> = computed(() => {
    const list = rows.value
    const grossUnadjEnding = calcSubtotal(list.map((r) => r.gross.unadjEnding))
    const grossAuditedEnding = calcSubtotal(list.map((r) => r.gross.auditedEnding))
    const impAuditedEnding = calcSubtotal(list.map((r) => r.impairment.auditedEnding))
    const nets = list.map(getI5NetRoll)
    const netUnadjEnding = calcSubtotal(nets.map((n) => n.unadjEnding))
    const netAuditedOpening = calcSubtotal(nets.map((n) => n.auditedOpening))
    const netAuditedIncrease = calcSubtotal(nets.map((n) => n.auditedIncrease))
    const netAuditedDecrease = calcSubtotal(nets.map((n) => n.auditedDecrease))
    const netAuditedEnding = calcSubtotal(nets.map((n) => n.auditedEnding))
    return {
      grossUnadjEnding,
      grossAuditedEnding,
      impAuditedEnding,
      netUnadjEnding,
      netAuditedOpening,
      netAuditedIncrease,
      netAuditedDecrease,
      netAuditedEnding,
      beginBalance: netAuditedOpening,
      increase: netAuditedIncrease,
      decrease: netAuditedDecrease,
      endBalance: netAuditedEnding,
      originalAmount: grossAuditedEnding,
      accumulatedAmount: impAuditedEnding,
      netValue: netAuditedEnding,
    }
  })

  const rollWarnings = computed(() => collectI5RollWarnings(rows.value))

  const sections = [
    { key: 0 as I5DetailSection, label: '原值未审', columns: GROSS_UNADJ_COLS },
    { key: 1 as I5DetailSection, label: '原值调整与审定', columns: GROSS_ADJ_COLS },
    { key: 2 as I5DetailSection, label: '减值准备', columns: IMP_COLS },
    { key: 3 as I5DetailSection, label: '净值与索引', columns: NET_COLS },
  ]

  const activeColumns = computed(() =>
    sections.find((s) => s.key === activeSection.value)?.columns ?? GROSS_UNADJ_COLS,
  )

  function switchSection(section: I5DetailSection): void {
    activeSection.value = section
  }

  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  function getCellValue(row: I5DetailRow, col: I5DetailColumn): any {
    if (col.path?.startsWith('net.')) {
      const net = getI5NetRoll(row)
      const field = col.path.slice(4) as keyof I5RollAmounts
      return net[field]
    }
    if (col.path?.startsWith('gross.')) {
      return (row.gross as any)[col.path.slice(6)]
    }
    if (col.path?.startsWith('impairment.')) {
      return (row.impairment as any)[col.path.slice(11)]
    }
    return (row as any)[col.key]
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return

    if (field.startsWith('gross.')) {
      ;(row.gross as any)[field.slice(6)] = value
    } else if (field.startsWith('impairment.')) {
      ;(row.impairment as any)[field.slice(11)] = value
    } else if (field === 'projectName' || field === 'name') {
      row.projectName = String(value ?? '')
      row.name = row.projectName
    } else {
      ;(row as any)[field] = value
    }
    recalcI5DetailRow(row)
    _persist()
  }

  async function addRow(): Promise<void> {
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入其他非流动资产项目名称',
        '新增明细类别',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：预付特许权使用费',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            if (rows.value.some((r) => r.projectName === val.trim())) return '该项目已存在'
            return true
          },
        },
      )
      if (!name?.trim()) return
      const newRow = emptyI5DetailRow({
        projectName: name.trim(),
        name: name.trim(),
        isBuiltin: false,
      })
      rows.value.push(newRow)
      activeRowIndex.value = rows.value.length - 1
      _persist()
    } catch {
      // cancel
    }
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    const row = rows.value[idx]
    if (row.isBuiltin) {
      rows.value[idx] = emptyI5DetailRow({
        projectName: row.projectName,
        name: row.projectName,
        isBuiltin: true,
        indexRef: row.indexRef || I5_BUILTIN_CATEGORIES.find((c) => c.name === row.projectName)?.indexRef || '',
      })
    } else {
      rows.value.splice(idx, 1)
    }
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
    _persist()
  }

  function importRows(importedData: any[]): void {
    const mapped = (importedData || [])
      .map(normalizeI5DetailRow)
      .filter((r) => r.projectName && r.projectName !== '合计')
    if (!mapped.length) {
      rows.value = createI5BuiltinRows()
    } else {
      rows.value = mapped
      for (const c of I5_BUILTIN_CATEGORIES) {
        if (!rows.value.some((r) => r.projectName === c.name)) {
          rows.value.push(emptyI5DetailRow({
            projectName: c.name,
            name: c.name,
            isBuiltin: true,
            indexRef: c.indexRef,
          }))
        }
      }
    }
    for (const r of rows.value) recalcI5DetailRow(r)
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
    _persist()
  }

  function exportRows(): I5DetailRow[] {
    return rows.value.map((r) => {
      recalcI5DetailRow(r)
      return { ...r, gross: { ...r.gross }, impairment: { ...r.impairment } }
    })
  }

  function recalcAll(): void {
    for (const r of rows.value) recalcI5DetailRow(r)
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    rows,
    activeSection,
    activeRowIndex,
    subtotals,
    rollWarnings,
    activeColumns,
    sections,
    switchSection,
    setActiveRow,
    getCellValue,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    exportRows,
  }
}

export default useI5Detail
