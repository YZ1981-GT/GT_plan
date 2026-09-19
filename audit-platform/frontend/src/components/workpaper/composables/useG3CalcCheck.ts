/**
 * useG3CalcCheck — G3-4 测算及检查表（三区段：增加测算 / 减少检查 / 期后收回）
 *
 * 编制逻辑对齐致同 Excel G3-4：
 *   ① 增加测算：应计 = 持股×DPS；差异 = 账面已计 − 测算
 *   ② 减少检查：本期减少 − 收现 − 其他减少
 *   ③ 期后收回：凭证抽查 + 核对勾选1–5 + 是否异常
 *
 * 存储：
 *   G3-4-calccheck-rows   — 被投资方行（①+②同粒度）
 *   G3-4-subsequent-rows  — 期后收回凭证行（1:N）
 *
 * 兼容：旧扁平 18 列（测算+凭证同行）自动迁移凭证字段 → subsequent
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import {
  parseNum,
  calcDividend,
  calcSubtotal,
} from './useG3DivRecFormulaEngine'
import { createEmptyG3AdjustmentRow, type G3AdjustmentRow } from './useG3Adjustment'
import { G3_ACCOUNT_CODE, G3_ADJUSTMENT_ROWS_KEY, G3_DETAIL_ROWS_KEY, G3_WP_CODE } from './g3Constants'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type CheckMark = '' | '√' | '—'
export type YesNo = '' | '是' | '否'

/** 被投资方行：增加测算 + 减少检查 */
export interface CalcCheckRow {
  id: string
  seq: number
  detailRowId: string
  investeeName: string
  // ① 增加测算
  shareholdingRatio: number
  sharesHeld: number
  dps: number
  investeeTotalDividend: number
  dividendPolicy: string
  declarationDate: string
  recordDate: string
  dividendDocNo: string
  calculatedDividend: number
  calcByRatio: number
  crossCheckDiff: number
  bookedAmount: number
  /** 测算差异 = 账面已计 − 测算（对齐 Excel ⑤） */
  calcVariance: number
  varianceReason: string
  indexNo: string
  skipDuplicate: YesNo
  // ② 减少检查
  periodDecrease: number
  cashReceived: number
  otherDecreaseAccount: string
  otherDecreaseAmount: number
  otherDecreaseReason: string
  decreaseDiff: number
  decreaseIndexNo: string
  decreaseRemark: string
}

/** ③ 期后收回检查行 */
export interface SubsequentRow {
  id: string
  seq: number
  investeeName: string
  voucherDate: string
  voucherNo: string
  summary: string
  counterAccount: string
  counterDetailAccount: string
  debitAmount: number
  creditAmount: number
  amount: number
  supportingDocs: string
  check1: CheckMark
  check2: CheckMark
  check3: CheckMark
  check4: CheckMark
  check5: CheckMark
  indexNo: string
  isAbnormal: YesNo
  abnormalNote: string
  samplingSource?: string
}

export interface CalcCheckColumn {
  prop: keyof CalcCheckRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'yn'
}

export interface SubsequentColumn {
  prop: keyof SubsequentRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'check' | 'yn'
}

export interface CalcCheckSegment {
  key: 'increase' | 'decrease' | 'subsequent'
  label: string
  columns: CalcCheckColumn[] | SubsequentColumn[]
}

// ─── Column Constants ────────────────────────────────────────────────────────

/** ① 增加测算 */
export const SEGMENT_INCREASE: CalcCheckColumn[] = [
  { prop: 'seq', label: '序号', width: 60, formula: true },
  { prop: 'investeeName', label: '被投资方', width: 160, type: 'text' },
  { prop: 'shareholdingRatio', label: '持股比例(%)', width: 110, type: 'number' },
  { prop: 'sharesHeld', label: '持股数量', width: 120, type: 'number' },
  { prop: 'dps', label: '每股股利', width: 100, type: 'number' },
  { prop: 'investeeTotalDividend', label: '被投资方分红总额', width: 140, type: 'number' },
  { prop: 'calculatedDividend', label: '应收股利(测算)', width: 130, type: 'number', formula: true },
  { prop: 'calcByRatio', label: '比例×总额验算', width: 130, type: 'number', formula: true },
  { prop: 'bookedAmount', label: '账面已计股利', width: 120, type: 'number' },
  { prop: 'calcVariance', label: '测算差异', width: 110, type: 'number', formula: true },
  { prop: 'declarationDate', label: '宣告日', width: 120, type: 'date' },
  { prop: 'dividendPolicy', label: '主要股利政策', width: 140, type: 'text' },
  { prop: 'dividendDocNo', label: '分红文件编号', width: 130, type: 'text' },
  { prop: 'varianceReason', label: '差异原因', width: 140, type: 'text' },
  { prop: 'indexNo', label: '索引号', width: 110, type: 'text' },
  { prop: 'skipDuplicate', label: '已在长投核实', width: 110, type: 'yn' },
]

/** ② 减少检查 */
export const SEGMENT_DECREASE: CalcCheckColumn[] = [
  { prop: 'seq', label: '序号', width: 60, formula: true },
  { prop: 'investeeName', label: '被投资方', width: 160, type: 'text' },
  { prop: 'shareholdingRatio', label: '持股比例(%)', width: 110, type: 'number' },
  { prop: 'periodDecrease', label: '本期减少', width: 120, type: 'number' },
  { prop: 'cashReceived', label: '收现金额', width: 120, type: 'number' },
  { prop: 'otherDecreaseAccount', label: '其他减少科目', width: 130, type: 'text' },
  { prop: 'otherDecreaseAmount', label: '其他减少金额', width: 120, type: 'number' },
  { prop: 'otherDecreaseReason', label: '其他减少原因', width: 140, type: 'text' },
  { prop: 'decreaseDiff', label: '减少差异', width: 110, type: 'number', formula: true },
  { prop: 'decreaseIndexNo', label: '索引号', width: 110, type: 'text' },
  { prop: 'decreaseRemark', label: '备注', width: 140, type: 'text' },
]

/** ③ 期后收回 */
export const SEGMENT_SUBSEQUENT: SubsequentColumn[] = [
  { prop: 'seq', label: '序号', width: 60, formula: true },
  { prop: 'investeeName', label: '被投资方', width: 140, type: 'text' },
  { prop: 'voucherDate', label: '日期', width: 120, type: 'date' },
  { prop: 'voucherNo', label: '凭证编号', width: 120, type: 'text' },
  { prop: 'summary', label: '业务内容', width: 150, type: 'text' },
  { prop: 'counterAccount', label: '对方科目', width: 110, type: 'text' },
  { prop: 'counterDetailAccount', label: '对方明细科目', width: 120, type: 'text' },
  { prop: 'debitAmount', label: '借方', width: 110, type: 'number' },
  { prop: 'creditAmount', label: '贷方', width: 110, type: 'number' },
  { prop: 'amount', label: '金额', width: 110, type: 'number', formula: true },
  { prop: 'supportingDocs', label: '支持性文件', width: 130, type: 'text' },
  { prop: 'check1', label: '1', width: 48, type: 'check' },
  { prop: 'check2', label: '2', width: 48, type: 'check' },
  { prop: 'check3', label: '3', width: 48, type: 'check' },
  { prop: 'check4', label: '4', width: 48, type: 'check' },
  { prop: 'check5', label: '5', width: 48, type: 'check' },
  { prop: 'indexNo', label: '索引号', width: 100, type: 'text' },
  { prop: 'isAbnormal', label: '是否异常', width: 90, type: 'yn' },
  { prop: 'abnormalNote', label: '异常说明', width: 140, type: 'text' },
]

export const G3_CALCCHECK_SEGMENTS: CalcCheckSegment[] = [
  { key: 'increase', label: '① 增加测算', columns: SEGMENT_INCREASE },
  { key: 'decrease', label: '② 减少检查', columns: SEGMENT_DECREASE },
  { key: 'subsequent', label: '③ 期后收回', columns: SEGMENT_SUBSEQUENT },
]

export const CHECK_CONTENT_HINTS = [
  '1. 原始凭证是否齐全',
  '2. 账载与原始凭证是否一致',
  '3. 会计处理是否正确',
  '4. 会计期间是否正确',
  '5. 与宣告/持股依据是否勾稽',
] as const

export const CHECK_MARK_OPTIONS: { value: CheckMark; label: string }[] = [
  { value: '√', label: '√' },
  { value: '—', label: '—' },
  { value: '', label: '空' },
]

export const YES_NO_OPTIONS: { value: YesNo; label: string }[] = [
  { value: '是', label: '是' },
  { value: '否', label: '否' },
  { value: '', label: '空' },
]

// ─── Storage Keys ────────────────────────────────────────────────────────────

export const DATA_KEY = 'G3-4-calccheck-rows'
export const SUBSEQUENT_KEY = 'G3-4-subsequent-rows'
const DETAIL_KEY = G3_DETAIL_ROWS_KEY
const ADJ_KEY = G3_ADJUSTMENT_ROWS_KEY
const ADJ_LEGACY_KEY = 'G3-3-adjustment-rows'

const VARIANCE_THRESHOLD = 100

/** 由审计年度推导默认资产负债表日（YYYY-12-31） */
export function defaultCutoffFromAuditYear(auditYear: number | string | null | undefined): string {
  const y = Number(auditYear)
  if (!Number.isFinite(y) || y < 1900) return ''
  return `${Math.trunc(y)}-12-31`
}

/** 期后抽凭会计年度 = 审计年度 + 1 */
export function subsequentSamplingYear(auditYear: number | string | null | undefined): number | null {
  const y = Number(auditYear)
  if (!Number.isFinite(y) || y < 1900) return null
  return Math.trunc(y) + 1
}

/** 日期字符串比较（YYYY-MM-DD）；非法日期返回 null */
export function compareDateStr(a: string, b: string): number | null {
  const da = (a || '').slice(0, 10)
  const db = (b || '').slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(da) || !/^\d{4}-\d{2}-\d{2}$/.test(db)) return null
  if (da < db) return -1
  if (da > db) return 1
  return 0
}

/** 凭证日 ≤ 截止日 → 非期后（含等于截止日） */
export function isNotSubsequentDate(voucherDate: string, cutoffDate: string): boolean {
  if (!cutoffDate) return false
  const cmp = compareDateStr(voucherDate, cutoffDate)
  return cmp !== null && cmp <= 0
}

// ─── Sum fields ──────────────────────────────────────────────────────────────

const ROW_SUM_FIELDS = [
  'calculatedDividend',
  'bookedAmount',
  'calcVariance',
  'periodDecrease',
  'cashReceived',
  'otherDecreaseAmount',
  'decreaseDiff',
] as const

export type CalcCheckTotals = Record<(typeof ROW_SUM_FIELDS)[number], number> & {
  subsequentAmount: number
  subsequentAbnormalCount: number
  subsequentCutoffInvalidCount: number
  varianceUnresolvedCount: number
  decreaseUnresolvedCount: number
  pushableVarianceCount: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(prefix = 'cc'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyRow(id: string, seq: number): CalcCheckRow {
  return {
    id,
    seq,
    detailRowId: '',
    investeeName: '',
    shareholdingRatio: 0,
    sharesHeld: 0,
    dps: 0,
    investeeTotalDividend: 0,
    dividendPolicy: '',
    declarationDate: '',
    recordDate: '',
    dividendDocNo: '',
    calculatedDividend: 0,
    calcByRatio: 0,
    crossCheckDiff: 0,
    bookedAmount: 0,
    calcVariance: 0,
    varianceReason: '',
    indexNo: '',
    skipDuplicate: '',
    periodDecrease: 0,
    cashReceived: 0,
    otherDecreaseAccount: '',
    otherDecreaseAmount: 0,
    otherDecreaseReason: '',
    decreaseDiff: 0,
    decreaseIndexNo: '',
    decreaseRemark: '',
  }
}

function emptySubsequent(id: string, seq: number): SubsequentRow {
  return {
    id,
    seq,
    investeeName: '',
    voucherDate: '',
    voucherNo: '',
    summary: '',
    counterAccount: '',
    counterDetailAccount: '',
    debitAmount: 0,
    creditAmount: 0,
    amount: 0,
    supportingDocs: '',
    check1: '',
    check2: '',
    check3: '',
    check4: '',
    check5: '',
    indexNo: '',
    isAbnormal: '',
    abnormalNote: '',
    samplingSource: undefined,
  }
}

function normalizeYn(v: unknown): YesNo {
  if (v === true || v === '是' || v === 'Y' || v === 'y') return '是'
  if (v === false || v === '否' || v === 'N' || v === 'n') return '否'
  return ''
}

function normalizeCheck(v: unknown): CheckMark {
  if (v === '√' || v === '✓' || v === 'Y' || v === 'y' || v === true) return '√'
  if (v === '—' || v === '-' || v === 'N' || v === 'n' || v === false) return '—'
  return ''
}

/** 公式链：增加测算 + 减少检查 */
export function enrichCalcRow(r: CalcCheckRow): CalcCheckRow {
  const sharesHeld = parseNum(r.sharesHeld)
  const dps = parseNum(r.dps)
  const ratio = parseNum(r.shareholdingRatio)
  const totalDiv = parseNum(r.investeeTotalDividend)
  const bookedAmount = parseNum(r.bookedAmount)
  const periodDecrease = parseNum(r.periodDecrease)
  const cashReceived = parseNum(r.cashReceived)
  const otherDecreaseAmount = parseNum(r.otherDecreaseAmount)

  const calculatedDividend = calcDividend(sharesHeld, dps)
  const calcByRatio = totalDiv > 0 ? (ratio / 100) * totalDiv : 0
  const crossCheckDiff = totalDiv > 0 ? calculatedDividend - calcByRatio : 0
  // 对齐 Excel：⑤ = 账面已计 − 测算
  const calcVariance = bookedAmount - calculatedDividend
  const decreaseDiff = periodDecrease - cashReceived - otherDecreaseAmount

  return {
    ...r,
    sharesHeld,
    dps,
    shareholdingRatio: ratio,
    investeeTotalDividend: totalDiv,
    bookedAmount,
    calculatedDividend,
    calcByRatio,
    crossCheckDiff,
    calcVariance,
    periodDecrease,
    cashReceived,
    otherDecreaseAmount,
    decreaseDiff,
    skipDuplicate: normalizeYn(r.skipDuplicate),
  }
}

export function enrichSubsequent(r: SubsequentRow): SubsequentRow {
  const debit = parseNum(r.debitAmount)
  const credit = parseNum(r.creditAmount)
  let amount = parseNum(r.amount)
  if (debit > 0 || credit > 0) {
    amount = debit > 0 ? debit : credit
  }
  return {
    ...r,
    debitAmount: debit,
    creditAmount: credit,
    amount,
    check1: normalizeCheck(r.check1),
    check2: normalizeCheck(r.check2),
    check3: normalizeCheck(r.check3),
    check4: normalizeCheck(r.check4),
    check5: normalizeCheck(r.check5),
    isAbnormal: normalizeYn(r.isAbnormal),
  }
}

/** 旧凭证区段字段（迁移后从主表剥离，避免重复迁移） */
const LEGACY_VOUCHER_KEYS = [
  'voucherDate',
  'voucherNo',
  'summary',
  'counterAccount',
  'amount',
  'receivingBank',
  'receiptDate',
  'reconciliationResult',
  'auditConclusion',
  'samplingSource',
] as const

/** 旧凭证区段字段是否有内容 */
function hasLegacyVoucher(p: Record<string, unknown>): boolean {
  return !!(
    p.voucherNo ||
    p.voucherDate ||
    p.samplingSource ||
    parseNum(p.amount as number) !== 0
  )
}

function stripLegacyVoucherFields<T extends Record<string, unknown>>(row: T): T {
  const next = { ...row }
  for (const k of LEGACY_VOUCHER_KEYS) {
    delete (next as Record<string, unknown>)[k]
  }
  return next
}

function migrateLegacyVoucher(p: Record<string, unknown>, seq: number): SubsequentRow {
  const amount = parseNum(p.amount as number)
  const receivingBank = String(p.receivingBank ?? '')
  const receiptDate = String(p.receiptDate ?? '')
  const supporting = [receivingBank && `收款银行:${receivingBank}`, receiptDate && `到账日:${receiptDate}`]
    .filter(Boolean)
    .join('；')
  const result = String(p.reconciliationResult ?? '')
  const conclusion = String(p.auditConclusion ?? '')
  return enrichSubsequent({
    ...emptySubsequent(generateId('sub'), seq),
    investeeName: String(p.investeeName ?? ''),
    voucherDate: String(p.voucherDate ?? ''),
    voucherNo: String(p.voucherNo ?? ''),
    summary: String(p.summary ?? ''),
    counterAccount: String(p.counterAccount ?? ''),
    debitAmount: amount,
    creditAmount: 0,
    amount,
    supportingDocs: supporting || result,
    abnormalNote: conclusion,
    isAbnormal: conclusion && /异常|不符|差异/.test(conclusion) ? '是' : '',
    samplingSource: p.samplingSource ? String(p.samplingSource) : undefined,
  })
}

function parseMainRows(raw: string | undefined): {
  rows: CalcCheckRow[]
  migratedSubsequent: SubsequentRow[]
  strippedLegacy: boolean
} {
  if (!raw) {
    return {
      rows: [enrichCalcRow(emptyRow(generateId(), 1))],
      migratedSubsequent: [],
      strippedLegacy: false,
    }
  }
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return {
        rows: [enrichCalcRow(emptyRow(generateId(), 1))],
        migratedSubsequent: [],
        strippedLegacy: false,
      }
    }
    const migratedSubsequent: SubsequentRow[] = []
    let strippedLegacy = false
    const rows = parsed.map((p, i) => {
      const rec = (p ?? {}) as Record<string, unknown>
      if (hasLegacyVoucher(rec)) {
        migratedSubsequent.push(migrateLegacyVoucher(rec, migratedSubsequent.length + 1))
        strippedLegacy = true
      }
      const cleaned = stripLegacyVoucherFields(rec)
      return enrichCalcRow({
        ...emptyRow(String(cleaned.id ?? generateId()), Number(cleaned.seq ?? i + 1)),
        ...cleaned,
        detailRowId: String(cleaned.detailRowId ?? ''),
        skipDuplicate: normalizeYn(cleaned.skipDuplicate),
        periodDecrease: parseNum(cleaned.periodDecrease as number),
        cashReceived: parseNum(cleaned.cashReceived as number),
        otherDecreaseAmount: parseNum(cleaned.otherDecreaseAmount as number),
      } as CalcCheckRow)
    })
    return { rows, migratedSubsequent, strippedLegacy }
  } catch {
    return {
      rows: [enrichCalcRow(emptyRow(generateId(), 1))],
      migratedSubsequent: [],
      strippedLegacy: false,
    }
  }
}

function parseSubsequentRows(raw: string | undefined, fallback: SubsequentRow[]): SubsequentRow[] {
  if (!raw) return fallback.length ? fallback : [enrichSubsequent(emptySubsequent(generateId('sub'), 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<SubsequentRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return fallback.length ? fallback : [enrichSubsequent(emptySubsequent(generateId('sub'), 1))]
    }
    return parsed.map((p, i) =>
      enrichSubsequent({
        ...emptySubsequent(String(p.id ?? generateId('sub')), Number(p.seq ?? i + 1)),
        ...p,
      } as SubsequentRow),
    )
  } catch {
    return fallback.length ? fallback : [enrichSubsequent(emptySubsequent(generateId('sub'), 1))]
  }
}

export function isVarianceExceeding(row: CalcCheckRow, threshold = VARIANCE_THRESHOLD): boolean {
  return Math.abs(row.calcVariance) > threshold
}

export function isDecreaseDiffExceeding(row: CalcCheckRow, threshold = VARIANCE_THRESHOLD): boolean {
  return Math.abs(row.decreaseDiff) > threshold
}

export function needsVarianceReason(row: CalcCheckRow): boolean {
  return isVarianceExceeding(row) && !row.varianceReason.trim() && !row.indexNo.trim()
}

export function needsDecreaseExplain(row: CalcCheckRow): boolean {
  return isDecreaseDiffExceeding(row) && !row.decreaseIndexNo.trim() && !row.decreaseRemark.trim()
}

export function isCrossCheckMismatch(row: CalcCheckRow): boolean {
  return parseNum(row.investeeTotalDividend) > 0 && Math.abs(row.crossCheckDiff) > 1
}

export function isSamplingRow(row: SubsequentRow): boolean {
  return !!row.samplingSource
}

export function isSubsequentAbnormal(row: SubsequentRow): boolean {
  return row.isAbnormal === '是'
}

export function isSubsequentCutoffInvalid(row: SubsequentRow, cutoffDate: string): boolean {
  if (!cutoffDate) return false
  if (!row.voucherDate) return false
  return isNotSubsequentDate(row.voucherDate, cutoffDate)
}

export function isPushableVariance(row: CalcCheckRow): boolean {
  return isVarianceExceeding(row) || isDecreaseDiffExceeding(row)
}

/**
 * 测算差异 → G3-3 借贷方向：
 * calcVariance = 账面 − 测算；>0 多计应收 → 贷记 1131；<0 少计 → 借记 1131
 */
export function buildAdjustmentDraftFromCalcRow(row: CalcCheckRow): G3AdjustmentRow | null {
  if (!isVarianceExceeding(row)) return null
  const amt = Math.abs(row.calcVariance)
  const draft = createEmptyG3AdjustmentRow()
  const overstated = row.calcVariance > 0
  return {
    ...draft,
    description: `G3-4 测算差异：${row.investeeName || '未命名'}（账面${overstated ? '高于' : '低于'}测算 ${amt.toFixed(2)}）`,
    category: '账项调整',
    reportItem: '应收股利',
    accountName: '应收股利',
    accountCode: '1131',
    debitAmount: overstated ? 0 : amt,
    creditAmount: overstated ? amt : 0,
    indexRef: row.indexNo || 'G3-4',
    remark: `src:G3-4-calc:${row.id}|${row.varianceReason || `测算 ${row.calculatedDividend} / 账面 ${row.bookedAmount}`}`,
  }
}

export function buildAdjustmentDraftFromDecreaseRow(row: CalcCheckRow): G3AdjustmentRow | null {
  if (!isDecreaseDiffExceeding(row)) return null
  const amt = Math.abs(row.decreaseDiff)
  const draft = createEmptyG3AdjustmentRow()
  // decreaseDiff = 本期减少 − 收现 − 其他；>0 减少未闭合（应收仍偏高）→ 贷记冲减
  const needCredit = row.decreaseDiff > 0
  return {
    ...draft,
    description: `G3-4 减少差异：${row.investeeName || '未命名'}（未闭合 ${amt.toFixed(2)}）`,
    category: '账项调整',
    reportItem: '应收股利',
    accountName: '应收股利',
    accountCode: '1131',
    debitAmount: needCredit ? 0 : amt,
    creditAmount: needCredit ? amt : 0,
    indexRef: row.decreaseIndexNo || 'G3-4',
    remark: `src:G3-4-dec:${row.id}|${row.decreaseRemark || row.otherDecreaseReason || ''}`,
  }
}

function pushSourceKey(kind: 'calc' | 'dec', rowId: string): string {
  return kind === 'calc' ? `src:G3-4-calc:${rowId}` : `src:G3-4-dec:${rowId}`
}

function alreadyPushed(existing: G3AdjustmentRow[], sourceKey: string): boolean {
  return existing.some((r) => String(r.remark || '').includes(sourceKey))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG3CalcCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  /** 资产负债表日 YYYY-MM-DD（期后校验用） */
  cutoffDate?: Ref<string>
}) {
  const cutoffRef = opts.cutoffDate
  const boot = parseMainRows(opts.allResponses.value.get(DATA_KEY)?.conclusion)
  const rows = ref<CalcCheckRow[]>(boot.rows)
  const subsequentRows = ref<SubsequentRow[]>(
    parseSubsequentRows(
      opts.allResponses.value.get(SUBSEQUENT_KEY)?.conclusion,
      boot.migratedSubsequent,
    ),
  )
  const segment = ref<CalcCheckSegment['key']>(G3_CALCCHECK_SEGMENTS[0].key)

  // 迁移：写入期后表；剥离主表旧凭证字段并回写，避免重复迁移
  if (!opts.isReadonly.value) {
    if (
      boot.migratedSubsequent.length > 0 &&
      !opts.allResponses.value.get(SUBSEQUENT_KEY)?.conclusion
    ) {
      opts.debouncedSave(SUBSEQUENT_KEY, {
        conclusion: JSON.stringify(subsequentRows.value),
      })
    }
    if (boot.strippedLegacy) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  function loadAll() {
    const next = parseMainRows(opts.allResponses.value.get(DATA_KEY)?.conclusion)
    rows.value = next.rows
    subsequentRows.value = parseSubsequentRows(
      opts.allResponses.value.get(SUBSEQUENT_KEY)?.conclusion,
      next.migratedSubsequent,
    )
  }

  watch(
    () => [
      opts.allResponses.value.get(DATA_KEY)?.conclusion,
      opts.allResponses.value.get(SUBSEQUENT_KEY)?.conclusion,
    ],
    ([mainRaw]) => {
      if (mainRaw) loadAll()
    },
  )

  const totals = computed<CalcCheckTotals>(() => {
    const out = {} as CalcCheckTotals
    for (const f of ROW_SUM_FIELDS) {
      out[f] = calcSubtotal(rows.value.map((r) => parseNum(r[f])))
    }
    const cutoff = cutoffRef?.value ?? ''
    out.subsequentAmount = calcSubtotal(subsequentRows.value.map((r) => parseNum(r.amount)))
    out.subsequentAbnormalCount = subsequentRows.value.filter((r) => r.isAbnormal === '是').length
    out.subsequentCutoffInvalidCount = subsequentRows.value.filter((r) =>
      isSubsequentCutoffInvalid(r, cutoff),
    ).length
    out.varianceUnresolvedCount = rows.value.filter(needsVarianceReason).length
    out.decreaseUnresolvedCount = rows.value.filter(needsDecreaseExplain).length
    out.pushableVarianceCount = rows.value.filter(isPushableVariance).length
    return out
  })

  function persistMain() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  function persistSubsequent() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(SUBSEQUENT_KEY, { conclusion: JSON.stringify(subsequentRows.value) })
    }
  }

  function updateRow(id: string, patch: Partial<CalcCheckRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichCalcRow({ ...r, ...patch }) : r))
    persistMain()
  }

  function updateSubsequentRow(id: string, patch: Partial<SubsequentRow>) {
    if (opts.isReadonly.value) return
    subsequentRows.value = subsequentRows.value.map((r) =>
      r.id === id ? enrichSubsequent({ ...r, ...patch }) : r,
    )
    persistSubsequent()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    if (segment.value === 'subsequent') {
      await addSubsequentRow()
      return
    }
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资方名称', '新增测算行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '被投资方名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [
        ...rows.value,
        enrichCalcRow({ ...emptyRow(generateId(), seq), investeeName: value }),
      ]
      persistMain()
    } catch {
      /* cancelled */
    }
  }

  async function addSubsequentRow() {
    if (opts.isReadonly.value) return
    const seq = subsequentRows.value.length + 1
    subsequentRows.value = [
      ...subsequentRows.value,
      enrichSubsequent(emptySubsequent(generateId('sub'), seq)),
    ]
    persistSubsequent()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value) return
    if (segment.value === 'subsequent') {
      if (subsequentRows.value.length <= 1) return
      subsequentRows.value = subsequentRows.value
        .filter((r) => r.id !== id)
        .map((r, i) => ({ ...r, seq: i + 1 }))
      persistSubsequent()
      return
    }
    if (rows.value.length <= 1) return
    rows.value = rows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistMain()
  }

  /**
   * 抽凭引擎集成 — 样本填入期后收回区段。
   * 若提供 cutoffDate，自动剔除凭证日 ≤ 截止日的样本（非期后）。
   */
  function fillFromSamples(
    samples: Partial<SubsequentRow>[],
    options?: { cutoffDate?: string },
  ): { filled: number; skippedCutoff: number } {
    if (opts.isReadonly.value || !samples.length) return { filled: 0, skippedCutoff: 0 }

    const cutoff = options?.cutoffDate ?? cutoffRef?.value ?? ''
    let skippedCutoff = 0
    const accepted = samples.filter((s) => {
      const d = String(s.voucherDate ?? '')
      if (cutoff && d && isNotSubsequentDate(d, cutoff)) {
        skippedCutoff++
        return false
      }
      return true
    })

    if (!accepted.length) {
      if (skippedCutoff) {
        ElMessage.warning(`已跳过 ${skippedCutoff} 笔截止日及以前凭证（非期后）`)
      }
      return { filled: 0, skippedCutoff }
    }

    const updated = [...subsequentRows.value]
    let nextSeq = updated.length + 1
    let filled = 0

    for (const sample of accepted) {
      const emptySlot = updated.find(
        (r) => !r.voucherNo && !r.voucherDate && !r.samplingSource && !r.amount,
      )

      const patch: Partial<SubsequentRow> = {
        investeeName: sample.investeeName ?? '',
        voucherDate: sample.voucherDate ?? '',
        voucherNo: sample.voucherNo ?? '',
        summary: sample.summary ?? '',
        counterAccount: sample.counterAccount ?? '',
        counterDetailAccount: sample.counterDetailAccount ?? '',
        debitAmount: parseNum(sample.debitAmount ?? sample.amount),
        creditAmount: parseNum(sample.creditAmount),
        supportingDocs: sample.supportingDocs ?? '',
        samplingSource: '抽凭引擎',
      }

      if (emptySlot) {
        const idx = updated.indexOf(emptySlot)
        updated[idx] = enrichSubsequent({ ...emptySlot, ...patch })
      } else {
        updated.push(
          enrichSubsequent({
            ...emptySubsequent(generateId('sub'), nextSeq),
            ...patch,
          }),
        )
        nextSeq++
      }
      filled++
    }

    subsequentRows.value = updated
    segment.value = 'subsequent'
    persistSubsequent()
    if (skippedCutoff) {
      ElMessage.warning(`已填入 ${filled} 笔；跳过 ${skippedCutoff} 笔截止日及以前凭证`)
    }
    return { filled, skippedCutoff }
  }

  /** 将测算/减少差异推送为 G3-3 调整草稿（不自动确认回写） */
  function pushVariancesToAdjustment(rowIds?: string[]): number {
    if (opts.isReadonly.value) return 0

    const targets = rows.value.filter(
      (r) => isPushableVariance(r) && (!rowIds || rowIds.includes(r.id)),
    )
    if (!targets.length) {
      ElMessage.info('无超过阈值的测算/减少差异可推送')
      return 0
    }

    let existing: G3AdjustmentRow[] = []
    const raw =
      opts.allResponses.value.get(ADJ_KEY)?.remark
      || opts.allResponses.value.get(ADJ_KEY)?.conclusion
      || opts.allResponses.value.get(ADJ_LEGACY_KEY)?.remark
      || opts.allResponses.value.get(ADJ_LEGACY_KEY)?.conclusion
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) existing = parsed
      } catch {
        existing = []
      }
    }

    const added: G3AdjustmentRow[] = []
    for (const r of targets) {
      const fromCalc = buildAdjustmentDraftFromCalcRow(r)
      if (fromCalc && !alreadyPushed(existing, pushSourceKey('calc', r.id))) {
        added.push(fromCalc)
      }
      const fromDec = buildAdjustmentDraftFromDecreaseRow(r)
      if (fromDec && !alreadyPushed(existing, pushSourceKey('dec', r.id))) {
        added.push(fromDec)
      }
    }
    if (!added.length) {
      ElMessage.info('差异草稿已存在于 G3-3，未重复推送')
      return 0
    }

    const json = JSON.stringify([...existing, ...added])
    opts.debouncedSave(ADJ_KEY, { remark: json, conclusion: json })

    for (const row of added) {
      try {
        eventBus.emit('adjustment:created', {
          wpCode: G3_WP_CODE,
          entryType: 'AJE',
          amount: Math.max(row.debitAmount, row.creditAmount),
          accountCode: G3_ACCOUNT_CODE,
          accountName: row.accountName,
          description: row.description,
          debitAmount: row.debitAmount,
          creditAmount: row.creditAmount,
          source: 'G3-4',
          timestamp: Date.now(),
        })
      } catch {
        /* silent */
      }
    }

    ElMessage.success(`已推送 ${added.length} 条差异草稿至 G3-3（请打开 G3-3 核对借贷并确认调整）`)
    return added.length
  }

  /**
   * 从 G3-2 同步主数据（upsert）；保留用户已填的入账/原因/减少核对等
   */
  function syncFromDetail(options?: { quiet?: boolean }): { added: number; updated: number } {
    if (opts.isReadonly.value) return { added: 0, updated: 0 }
    const quiet = !!options?.quiet

    const raw = opts.allResponses.value.get(DETAIL_KEY)?.conclusion
    if (!raw) {
      if (!quiet) ElMessage.warning('G3-2 明细尚无数据，请先填写明细表')
      return { added: 0, updated: 0 }
    }

    let detailList: Array<Record<string, unknown>> = []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) throw new Error('not array')
      detailList = parsed.filter((d) => String((d as { investeeName?: string }).investeeName ?? '').trim())
    } catch {
      if (!quiet) ElMessage.warning('G3-2 明细数据无法解析')
      return { added: 0, updated: 0 }
    }

    if (!detailList.length) {
      if (!quiet) ElMessage.warning('G3-2 无可同步的被投资方')
      return { added: 0, updated: 0 }
    }

    const byDetailId = new Map(rows.value.filter((r) => r.detailRowId).map((r) => [r.detailRowId, r]))
    const byName = new Map(
      rows.value
        .filter((r) => r.investeeName.trim())
        .map((r) => [r.investeeName.trim(), r]),
    )

    let added = 0
    let updated = 0
    const next = [...rows.value]
    // 清空仅占位空行（无名称且无金额）
    const isPlaceholder = (r: CalcCheckRow) =>
      !r.investeeName.trim() &&
      !r.bookedAmount &&
      !r.sharesHeld &&
      !r.periodDecrease &&
      !r.detailRowId

    for (const d of detailList) {
      const detailId = String(d.id ?? '')
      const name = String(d.investeeName ?? '').trim()
      const syncedFields: Partial<CalcCheckRow> = {
        detailRowId: detailId,
        investeeName: name,
        shareholdingRatio: parseNum(d.shareholdingRatio as number),
        sharesHeld: parseNum(d.sharesHeld as number),
        dps: parseNum(d.dps as number),
        investeeTotalDividend: parseNum(d.totalDividend as number),
        dividendPolicy: String(d.dividendPlan ?? ''),
        declarationDate: String(d.declarationDate ?? ''),
        recordDate: String(d.recordDate ?? ''),
      }

      let existing =
        (detailId && byDetailId.get(detailId)) ||
        byName.get(name)

      if (existing) {
        const idx = next.findIndex((r) => r.id === existing!.id)
        if (idx >= 0) {
          // 保留用户已填字段：bookedAmount / varianceReason / indexNo / 减少核对等
          next[idx] = enrichCalcRow({
            ...next[idx],
            ...syncedFields,
            // 减少：仅当本期减少仍为 0 时用 G3-2 已收预填
            periodDecrease:
              next[idx].periodDecrease > 0
                ? next[idx].periodDecrease
                : parseNum(d.receivedAmount as number),
            cashReceived:
              next[idx].cashReceived > 0
                ? next[idx].cashReceived
                : parseNum(d.receivedAmount as number),
          })
          updated++
        }
      } else {
        const seq = next.filter((r) => !isPlaceholder(r)).length + added + 1
        const newRow = enrichCalcRow({
          ...emptyRow(generateId(), seq),
          ...syncedFields,
          periodDecrease: parseNum(d.receivedAmount as number),
          cashReceived: parseNum(d.receivedAmount as number),
        })
        next.push(newRow)
        added++
      }
    }

    // 去掉纯占位空行
    const cleaned = next.filter((r) => !isPlaceholder(r) || next.length === 1)
    rows.value = cleaned.map((r, i) => ({ ...r, seq: i + 1 }))
    if (!rows.value.length) {
      rows.value = [enrichCalcRow(emptyRow(generateId(), 1))]
    }
    persistMain()
    if (!quiet) {
      ElMessage.success(`已从 G3-2 同步：更新 ${updated} 行，新增 ${added} 行（已保留入账/原因等手填项）`)
    }
    return { added, updated }
  }

  return {
    segments: G3_CALCCHECK_SEGMENTS,
    segment,
    rows,
    subsequentRows,
    totals,
    loadAll,
    persistAll: () => {
      persistMain()
      persistSubsequent()
    },
    updateRow,
    updateSubsequentRow,
    addRow,
    addSubsequentRow,
    removeRow,
    fillFromSamples,
    pushVariancesToAdjustment,
    syncFromDetail,
    isVarianceExceeding,
    isDecreaseDiffExceeding,
    needsVarianceReason,
    needsDecreaseExplain,
    isCrossCheckMismatch,
    isSamplingRow,
    isSubsequentAbnormal,
    isSubsequentCutoffInvalid,
    isPushableVariance,
  }
}

export default useG3CalcCheck
