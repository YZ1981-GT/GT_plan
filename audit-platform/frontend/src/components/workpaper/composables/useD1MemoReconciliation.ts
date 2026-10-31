/**
 * useD1MemoReconciliation — D1-7 备查簿核对 composable
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 4.1
 *
 * 职责：
 * - 管理 31 列票据备查簿宽表（bankRows 银行承兑 / commercialRows 商业承兑动态行）
 * - 「审计核对」区 Q~W（年初余额 / 本期收到 / 本期背书 / 本期到期承兑 / 本期贴现 /
 *   年末持有票据余额 / 期末未到期背书或贴现金额）按权威模板行公式计算、只读（deriveMemoRow）
 * - 小计/合计 computed（bankSubtotal / commercialSubtotal / grandTotal，SUM 所有数值列）
 * - 核对区 computed（reconciliationRows 3行：备查簿合计 / 明细账D1-2 / 差异，模板 R28~R31 四列）
 *   - 明细账行通过纯 computed 从同一 allResponses Map 跨 sheet 取 D1-2 数据
 * - 贴现背书统计 computed（endorsedStats）与「贴现、票据已背书未到期明细」（模板 G28~H34）
 * - 差异检测 computed（hasDifference）
 * - 截止日期 / 审计说明 / 审计结论（cutoffDate / auditNote / auditConclusion）
 * - 动态行 CRUD（addRow / removeRow / updateCell）
 * - 序列化/反序列化（JSON ↔ checklist_responses remark），debounce 2s 自动保存
 * - respect isReadonly（只读时所有写操作 no-op）
 *
 * 跨 Sheet 取数说明（明细账 D1-2 映射，模板 B30 / C30 / D30 / E30）：
 *   D1-2（按类别原值明细）的行以 `D1-cat-rows` 为 item_id、JSON 数组存于 remark 字段
 *   （见 useD1DetailCategory.ts）。备查簿是被审计单位自己的登记，与账面未审数核对：
 *     明细账.期初余额 ← sum(priorUnadjusted)   = D1-2 B14 期初未审数
 *     明细账.本期增加 ← sum(currentIncrease)   = D1-2 F14
 *     明细账.本期减少 ← sum(currentDecrease)   = D1-2 G14
 *     明细账.期末余额 = 期初 + 增加 - 减少       = 模板 E30 = B30 + C30 - D30
 *   原先取期初审定 / 期末审定（含审计调整），与模板不符；且把 D1-2 的本期减少整笔对到
 *   「本期到期」、背书 / 贴现对 0，备查簿有背书或贴现时三列恒报差异
 *   （spec oo-writeback-template-parity-closure R2）。
 *
 * Requirements: 4.1-4.8, 5.1-5.6, 6.1-6.5, 13.2, 13.5, 13.6, 13.7
 */
import { newUuid } from '@/utils/uuid'
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import {
  parseNum,
  calcSubtotal,
  calcCurrentUnadjusted,
  calcMemoCurrentReceived,
  calcMemoEndingBalance,
  calcMemoOpeningBalance,
  calcMemoStatusMovements,
  calcUnexpiredEndorsedDiscounted,
  normalizeMemoStatus,
  suggestCreditRating,
  suggestDerecognized,
  isDateBefore,
} from './useD1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface MemoRow {
  rowId: string
  rowType: 'fixed' | 'dynamic' | 'summary'
  category: 'bank' | 'commercial'  // 所属分类
  // 基本信息区 (8列)
  noteType: string        // 票据类型（银行承兑/商业承兑）
  noteNumber: string      // 票据号
  receivedDate: string    // 收到日期
  endorser: string        // 前手
  issueDate: string       // 出票日
  issuer: string          // 出票人
  acceptor: string        // 承兑人
  amount: number          // 金额
  // 流转区 (6列)
  maturityDate: string    // 到期日
  transferDate: string    // 流转日
  status: string          // 状态
  endorsee: string        // 被背书人
  discountBank: string    // 贴现银行
  discountInterest: number // 贴现息
  // 金额区 (9列)
  isPledged: string       // 是否质押
  isDiscountedEndorsed: string // 审计日已贴现背书
  beginningBalance: number  // 年初余额
  currentReceived: number   // 本期收到
  currentEndorsed: number   // 本期背书
  currentMatured: number    // 本期到期承兑
  currentDiscounted: number // 本期贴现
  endingBalance: number     // 年末余额
  unexpiredEndorsedDiscounted: number // 期末未到期背书贴现
  // 审定区 (8列)
  isDerecognized: string    // 是否终止确认
  creditRating: string      // 信用评级
  auditedFinancing: number  // 审定应收款项融资
  auditedNotes: number      // 审定应收票据
  relatedParty: string      // 关联关系
  isOverdue: string         // 是否逾期
  overdueTransferAmount: number // 逾期转应收金额
  remarkText: string        // 备注
  attachmentId: string      // OCR附件ID
  attachmentName: string    // OCR附件名
  ocrStatus: string         // OCR状态: none/processing/done/failed
}

/** 核对区一行（模板 A28:E31：期初余额 / 本期增加额 / 本期减少额 / 期末余额） */
export interface ReconciliationRow {
  label: string           // '备查簿合计' | '明细账(D1-2)' | '差异'
  beginningBalance: number
  currentIncrease: number
  currentDecrease: number
  endingBalance: number
}

/** 「贴现、票据已背书未到期明细」一行（模板 G28:I33，按 W 列分是否终止确认汇总） */
export interface UnexpiredSummaryRow {
  category: string
  derecognized: number
  notDerecognized: number
}

export interface MemoRowWarning {
  rowId: string
  noteNumber: string
  messages: string[]
}

export interface UseD1MemoReconciliationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const MEMO_ROWS_KEY = 'D1-memo-rows'          // 存 {bankRows:[...], commercialRows:[...]} JSON
const CUTOFF_KEY = 'D1-memo-cutoff-date'
const PROCEDURES_KEY = 'D1-memo-procedures'
const NOTE_KEY = 'D1-memo-note'
const CONCLUSION_KEY = 'D1-memo-conclusion'

/** D1-2 按类别原值明细表存储 key（跨 sheet 取数来源，见 useD1DetailCategory.ts） */
const D1_CAT_ROWS_KEY = 'D1-cat-rows'

/** MemoRow 全部数值字段（用于 SUM / parseNum / 空行工厂） */
const NUMERIC_FIELDS: Array<keyof MemoRow> = [
  'amount',
  'discountInterest',
  'beginningBalance',
  'currentReceived',
  'currentEndorsed',
  'currentMatured',
  'currentDiscounted',
  'endingBalance',
  'unexpiredEndorsedDiscounted',
  'auditedFinancing',
  'auditedNotes',
  'overdueTransferAmount',
]

/** MemoRow 全部字符串字段 */
const STRING_FIELDS: Array<keyof MemoRow> = [
  'noteType',
  'noteNumber',
  'receivedDate',
  'endorser',
  'issueDate',
  'issuer',
  'acceptor',
  'maturityDate',
  'transferDate',
  'status',
  'endorsee',
  'discountBank',
  'isPledged',
  'isDiscountedEndorsed',
  'isDerecognized',
  'creditRating',
  'relatedParty',
  'isOverdue',
  'remarkText',
  'attachmentId',
  'attachmentName',
  'ocrStatus',
]

/** 模板「审计核对」区 Q~W 的公式列：只读，由 deriveMemoRow 计算，updateCell 不接受 */
export const MEMO_DERIVED_FIELDS: ReadonlySet<string> = new Set<keyof MemoRow>([
  'beginningBalance',
  'currentReceived',
  'currentEndorsed',
  'currentMatured',
  'currentDiscounted',
  'endingBalance',
  'unexpiredEndorsedDiscounted',
])

/** 模板 G29:G32 四个分类与对应的 SUMIFS 条件（K 票据状态 + A 票据类型） */
const UNEXPIRED_MATRIX: ReadonlyArray<{ label: string; status: string; noteType: string }> = [
  { label: '已背书未到期银行承兑汇票', status: '背书', noteType: '银行承兑汇票' },
  { label: '已背书未到期商业承兑汇票', status: '背书', noteType: '商业承兑汇票' },
  { label: '已贴现未到期银行承兑汇票', status: '贴现', noteType: '银行承兑汇票' },
  { label: '已贴现未到期商业承兑汇票', status: '贴现', noteType: '商业承兑汇票' },
]

/** 金额比较容差（分）：合计是浮点累加，按分判差异 */
const CENT = 0.005

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成动态行 ID */
function generateRowId(): string {
  return `dynamic-${newUuid()}`
}

/** 空 MemoRow 工厂：所有数值字段 0、字符串字段 ''、全新 rowId */
export function emptyMemoRow(
  category: 'bank' | 'commercial',
  rowType: 'fixed' | 'dynamic' | 'summary' = 'dynamic',
): MemoRow {
  return {
    rowId: generateRowId(),
    rowType,
    category,
    noteType: category === 'bank' ? '银行承兑汇票' : '商业承兑汇票',
    noteNumber: '',
    receivedDate: '',
    endorser: '',
    issueDate: '',
    issuer: '',
    acceptor: '',
    amount: 0,
    maturityDate: '',
    transferDate: '',
    status: '',
    endorsee: '',
    discountBank: '',
    discountInterest: 0,
    isPledged: '',
    isDiscountedEndorsed: '',
    beginningBalance: 0,
    currentReceived: 0,
    currentEndorsed: 0,
    currentMatured: 0,
    currentDiscounted: 0,
    endingBalance: 0,
    unexpiredEndorsedDiscounted: 0,
    isDerecognized: '',
    creditRating: '',
    auditedFinancing: 0,
    auditedNotes: 0,
    relatedParty: '',
    isOverdue: '',
    overdueTransferAmount: 0,
    remarkText: '',
    attachmentId: '',
    attachmentName: '',
    ocrStatus: 'none',
  }
}

/** 反序列化单行：安全转换所有字段类型 */
function deserializeRow(raw: any, category: 'bank' | 'commercial'): MemoRow {
  const row = emptyMemoRow(category, raw?.rowType === 'fixed' ? 'fixed' : 'dynamic')
  if (raw && typeof raw.rowId === 'string' && raw.rowId) row.rowId = raw.rowId
  for (const f of STRING_FIELDS) {
    if (raw && typeof raw[f] === 'string') (row as any)[f] = raw[f]
  }
  for (const f of NUMERIC_FIELDS) {
    if (raw && raw[f] !== undefined) (row as any)[f] = parseNum(raw[f])
  }
  row.status = normalizeMemoStatus(row.status)
  return row
}

/** 序列化单行：保留全部字段（数值+字符串） */
function serializeRow(row: MemoRow): any {
  const data: any = {
    rowId: row.rowId,
    rowType: row.rowType,
    category: row.category,
  }
  for (const f of STRING_FIELDS) data[f] = (row as any)[f]
  for (const f of NUMERIC_FIELDS) data[f] = (row as any)[f]
  return data
}

/** 构建某分类的合计行（SUM 所有数值列） */
function buildSummaryRow(
  rows: MemoRow[],
  category: 'bank' | 'commercial',
  label: string,
): MemoRow {
  const summary = emptyMemoRow(category, 'summary')
  summary.rowId = `summary-${category}`
  summary.noteType = label
  for (const f of NUMERIC_FIELDS) {
    ;(summary as any)[f] = calcSubtotal(rows.map((r) => (r as any)[f] as number))
  }
  return summary
}

/**
 * 按权威模板 Q~W 行公式重算一行（纯函数，不改入参）：
 * Q 年初余额 / R 本期收到 / S 本期背书 / T 本期到期承兑 / U 本期贴现 /
 * V 年末持有票据余额 / W 期末未到期背书或贴现金额，公式见 useD1FormulaEngine。
 */
export function deriveMemoRow(row: MemoRow, cutoff: string): MemoRow {
  const next = { ...row }
  next.beginningBalance = calcMemoOpeningBalance(next.amount, next.receivedDate, cutoff)
  next.currentReceived = calcMemoCurrentReceived(next.amount, next.beginningBalance)
  const movement = calcMemoStatusMovements(next.amount, next.status)
  next.currentEndorsed = movement.endorsed
  next.currentMatured = movement.matured
  next.currentDiscounted = movement.discounted
  next.endingBalance = calcMemoEndingBalance(
    next.beginningBalance,
    next.currentReceived,
    movement.endorsed,
    movement.matured,
    movement.discounted,
  )
  next.unexpiredEndorsedDiscounted = calcUnexpiredEndorsedDiscounted(
    movement.endorsed,
    movement.discounted,
    next.maturityDate,
    next.transferDate,
    cutoff,
  )
  return next
}

/** 对单行应用联动（状态 → 贴现背书标记 / 终止确认建议，承兑人 → 信用评级，逾期）后重算公式列 */
function applyRowLinkage(row: MemoRow, cutoff: string, changedField?: string): MemoRow {
  const next = { ...row }

  if (changedField === 'status') {
    if (next.status === '贴现' || next.status === '背书') next.isDiscountedEndorsed = '是'
    if (!next.isDerecognized) {
      const suggested = suggestDerecognized(next.status, next.acceptor, next.noteType)
      if (suggested) next.isDerecognized = suggested
    }
  }

  if ((changedField === 'acceptor' || changedField === 'noteType') && !next.creditRating) {
    next.creditRating = suggestCreditRating(next.acceptor, next.noteType)
  }

  if (cutoff && next.maturityDate && next.status === '未到期') {
    next.isOverdue = isDateBefore(next.maturityDate, cutoff) ? '是' : '否'
  }

  return deriveMemoRow(next, cutoff)
}

function collectRowWarnings(row: MemoRow, cutoff: string): string[] {
  const warnings: string[] = []
  const endorsedOrDiscounted = row.status === '贴现' || row.status === '背书'
  if (!row.noteNumber?.trim()) warnings.push('票据号未填写')
  if (!row.maturityDate && endorsedOrDiscounted) {
    warnings.push('贴现/背书票据缺少到期日')
  }
  if (cutoff && row.maturityDate && isDateBefore(row.maturityDate, cutoff) && row.status === '未到期') {
    warnings.push('到期日早于截止日期但状态仍为未到期')
  }
  if (endorsedOrDiscounted && !row.isDiscountedEndorsed) {
    warnings.push('状态为贴现/背书但「审计日已贴现背书」未标记')
  }
  return warnings
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1MemoReconciliation(options: UseD1MemoReconciliationOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const cutoffDate = ref<string>('')
  const bankRows = ref<MemoRow[]>([])
  const commercialRows = ref<MemoRow[]>([])
  const auditProcedures = ref<string>('')
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')
  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loading')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  /** 读入行并按截止日期重算公式列（存量里的旧状态值 / 手填过的公式列在这里统一按模板口径） */
  function loadMemoRows(cutoff: string): { bank: MemoRow[]; commercial: MemoRow[] } {
    const raw = allResponses.value.get(MEMO_ROWS_KEY)?.remark
    if (!raw) return { bank: [], commercial: [] }
    try {
      const parsed = JSON.parse(raw)
      const bankRaw = Array.isArray(parsed?.bankRows) ? parsed.bankRows : []
      const commercialRaw = Array.isArray(parsed?.commercialRows) ? parsed.commercialRows : []
      return {
        bank: bankRaw.map((r: any) => deriveMemoRow(deserializeRow(r, 'bank'), cutoff)),
        commercial: commercialRaw.map((r: any) => deriveMemoRow(deserializeRow(r, 'commercial'), cutoff)),
      }
    } catch {
      return { bank: [], commercial: [] }
    }
  }

  function loadFromResponses(): void {
    cutoffDate.value = allResponses.value.get(CUTOFF_KEY)?.remark ?? ''
    const { bank, commercial } = loadMemoRows(cutoffDate.value)
    bankRows.value = bank
    commercialRows.value = commercial
    auditProcedures.value = allResponses.value.get(PROCEDURES_KEY)?.remark ?? ''
    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
  }

  // Initial load
  loadFromResponses()

  // Watch allResponses for external changes (other tabs / OO sync)
  watch(
    () => [
      allResponses.value.get(MEMO_ROWS_KEY)?.remark,
      allResponses.value.get(CUTOFF_KEY)?.remark,
      allResponses.value.get(PROCEDURES_KEY)?.remark,
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    ([newRows, newCutoff, newProcedures, newNote, newConclusion]) => {
      // 截止日期先行：年初余额（Q）与期末未到期背书或贴现金额（W）都依赖它
      let cutoffChanged = false
      if (newCutoff !== undefined && (newCutoff ?? '') !== cutoffDate.value) {
        cutoffDate.value = newCutoff ?? ''
        cutoffChanged = true
      }
      if (newRows !== undefined && newRows !== serializeMemoRows()) {
        const { bank, commercial } = loadMemoRows(cutoffDate.value)
        bankRows.value = bank
        commercialRows.value = commercial
      } else if (cutoffChanged) {
        bankRows.value = bankRows.value.map((r) => deriveMemoRow(r, cutoffDate.value))
        commercialRows.value = commercialRows.value.map((r) => deriveMemoRow(r, cutoffDate.value))
      }
      if (newProcedures !== undefined && newProcedures !== auditProcedures.value) {
        auditProcedures.value = newProcedures ?? ''
      }
      if (newNote !== undefined && newNote !== auditNote.value) {
        auditNote.value = newNote ?? ''
      }
      if (newConclusion !== undefined && newConclusion !== auditConclusion.value) {
        auditConclusion.value = newConclusion ?? ''
      }
    },
  )

  // ─── Serialization ───────────────────────────────────────────────────────

  function serializeMemoRows(): string {
    return JSON.stringify({
      bankRows: bankRows.value.map(serializeRow),
      commercialRows: commercialRows.value.map(serializeRow),
    })
  }

  // ─── Debounce Save ───────────────────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistToResponses()
    }, 2000)
  }

  function persistToResponses(): void {
    const items: ChecklistItem[] = [
      { item_id: MEMO_ROWS_KEY, conclusion: null, remark: serializeMemoRows() },
      { item_id: CUTOFF_KEY, conclusion: null, remark: cutoffDate.value || null },
      { item_id: PROCEDURES_KEY, conclusion: null, remark: auditProcedures.value || null },
      { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value || null },
      { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value || null },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    saveImmediate(items)
  }

  // ─── Subtotals / Grand Total (computed) ──────────────────────────────────

  const bankSubtotal: ComputedRef<MemoRow> = computed(() =>
    buildSummaryRow(bankRows.value, 'bank', '银行承兑小计'),
  )

  const commercialSubtotal: ComputedRef<MemoRow> = computed(() =>
    buildSummaryRow(commercialRows.value, 'commercial', '商业承兑小计'),
  )

  const grandTotal: ComputedRef<MemoRow> = computed(() => {
    const summary = emptyMemoRow('bank', 'summary')
    summary.rowId = 'summary-grand'
    summary.noteType = '合计'
    for (const f of NUMERIC_FIELDS) {
      ;(summary as any)[f] =
        ((bankSubtotal.value as any)[f] as number) +
        ((commercialSubtotal.value as any)[f] as number)
    }
    return summary
  })

  // ─── Cross-Sheet 明细账 (D1-2) 取数 (computed) ────────────────────────────

  /**
   * 从 allResponses 的 D1-cat-rows 读取 D1-2 未审数（模板 B30 / C30 / D30 取 D1-2 B14 / F14 / G14）。
   * 返回 null 表示 D1-2 数据不存在/解析失败（核对区显示占位 + crossSheetStatus='error'）。
   */
  const detailLedgerRow: ComputedRef<ReconciliationRow | null> = computed(() => {
    const raw = allResponses.value.get(D1_CAT_ROWS_KEY)?.remark
    if (!raw) return null
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return null
      let beginningBalance = 0
      let currentIncrease = 0
      let currentDecrease = 0
      for (const r of parsed) {
        beginningBalance += parseNum(r?.priorUnadjusted)
        currentIncrease += parseNum(r?.currentIncrease)
        currentDecrease += parseNum(r?.currentDecrease)
      }
      return {
        label: '明细账(D1-2)',
        beginningBalance,
        currentIncrease,
        currentDecrease,
        // 模板 E30 = B30 + C30 - D30（= D1-2 H14 期末未审数）
        endingBalance: calcCurrentUnadjusted(beginningBalance, currentIncrease, currentDecrease),
      }
    } catch {
      return null
    }
  })

  // 跨 sheet 状态跟随 detailLedgerRow 结果更新
  watch(
    detailLedgerRow,
    (row) => {
      crossSheetStatus.value = row === null ? 'error' : 'loaded'
    },
    { immediate: true },
  )

  // ─── Reconciliation Area (computed) ──────────────────────────────────────

  /** 模板 R29：期初 = Q25，本期增加 = R25，本期减少 = S25 + T25 + U25，期末 = 期初 + 增加 - 减少 */
  const reconciliationRows: ComputedRef<ReconciliationRow[]> = computed(() => {
    const gt = grandTotal.value
    const memoDecrease = gt.currentEndorsed + gt.currentMatured + gt.currentDiscounted
    const memoTotal: ReconciliationRow = {
      label: '备查簿合计',
      beginningBalance: gt.beginningBalance,
      currentIncrease: gt.currentReceived,
      currentDecrease: memoDecrease,
      endingBalance: gt.beginningBalance + gt.currentReceived - memoDecrease,
    }

    // D1-2 明细账行；无数据时占位为全 0
    const ledger: ReconciliationRow = detailLedgerRow.value ?? {
      label: '明细账(D1-2)',
      beginningBalance: 0,
      currentIncrease: 0,
      currentDecrease: 0,
      endingBalance: 0,
    }

    const diff: ReconciliationRow = {
      label: '差异',
      beginningBalance: memoTotal.beginningBalance - ledger.beginningBalance,
      currentIncrease: memoTotal.currentIncrease - ledger.currentIncrease,
      currentDecrease: memoTotal.currentDecrease - ledger.currentDecrease,
      endingBalance: memoTotal.endingBalance - ledger.endingBalance,
    }

    return [memoTotal, ledger, diff]
  })

  /** 差异按分判断（合计是浮点累加，尾差不算差异） */
  const hasDifference: ComputedRef<boolean> = computed(() => {
    const diff = reconciliationRows.value[2]
    if (!diff) return false
    return [diff.beginningBalance, diff.currentIncrease, diff.currentDecrease, diff.endingBalance]
      .some((v) => Math.abs(v) >= CENT)
  })

  // ─── 贴现背书统计（= 合计行 U25 / S25） ──────────────────────────────────

  const endorsedStats: ComputedRef<{ discountedTotal: number; endorsedTotal: number }> = computed(() => ({
    discountedTotal: grandTotal.value.currentDiscounted,
    endorsedTotal: grandTotal.value.currentEndorsed,
  }))

  const allDataRows: ComputedRef<MemoRow[]> = computed(() => [
    ...bankRows.value,
    ...commercialRows.value,
  ])

  /**
   * 「贴现、票据已背书未到期明细」（模板 G29:I32）：
   * SUMIFS(W, X="是"/"否", K=状态, A=票据类型)，按「是否终止确认」分两列。
   */
  const unexpiredSummaryRows: ComputedRef<UnexpiredSummaryRow[]> = computed(() =>
    UNEXPIRED_MATRIX.map(({ label, status, noteType }) => {
      let derecognized = 0
      let notDerecognized = 0
      for (const r of allDataRows.value) {
        if (r.status !== status || r.noteType !== noteType) continue
        if (r.isDerecognized === '是') derecognized += r.unexpiredEndorsedDiscounted
        else if (r.isDerecognized === '否') notDerecognized += r.unexpiredEndorsedDiscounted
      }
      return { category: label, derecognized, notDerecognized }
    }),
  )

  /** 模板 H33 / I33 合计 */
  const unexpiredSummaryTotal: ComputedRef<UnexpiredSummaryRow> = computed(() => ({
    category: '合计',
    derecognized: calcSubtotal(unexpiredSummaryRows.value.map((r) => r.derecognized)),
    notDerecognized: calcSubtotal(unexpiredSummaryRows.value.map((r) => r.notDerecognized)),
  }))

  /** 模板 H34 勾稽 = W25 - H33 - I33（非 0 说明有期末未到期背书/贴现的票据没判断是否终止确认） */
  const unexpiredCheckDiff: ComputedRef<number> = computed(() =>
    grandTotal.value.unexpiredEndorsedDiscounted
      - unexpiredSummaryTotal.value.derecognized
      - unexpiredSummaryTotal.value.notDerecognized,
  )

  const rowWarnings: ComputedRef<MemoRowWarning[]> = computed(() => {
    const cutoff = cutoffDate.value
    return allDataRows.value
      .map((row) => ({
        rowId: row.rowId,
        noteNumber: row.noteNumber,
        messages: collectRowWarnings(row, cutoff),
      }))
      .filter((w) => w.messages.length > 0)
  })

  const warningCount = computed(() => rowWarnings.value.length)

  // ─── Row CRUD ────────────────────────────────────────────────────────────

  /** 在指定分类末尾新增一个空动态行 */
  function addRow(category: 'bank' | 'commercial'): void {
    if (isReadonly.value) return
    const newRow = emptyMemoRow(category, 'dynamic')
    if (category === 'bank') {
      bankRows.value = [...bankRows.value, newRow]
    } else {
      commercialRows.value = [...commercialRows.value, newRow]
    }
    scheduleSave()
  }

  /** 删除动态行（从 bank/commercial 任一列表移除） */
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    if (bankRows.value.some((r) => r.rowId === rowId)) {
      bankRows.value = bankRows.value.filter((r) => r.rowId !== rowId)
      scheduleSave()
      return
    }
    if (commercialRows.value.some((r) => r.rowId === rowId)) {
      commercialRows.value = commercialRows.value.filter((r) => r.rowId !== rowId)
      scheduleSave()
    }
  }

  /** 编辑单元格 → 数值字段 parseNum → debounce 保存（公式列 Q~W 只读，忽略写入） */
  function updateCell(rowId: string, field: string, value: string | number): void {
    if (isReadonly.value) return
    if (MEMO_DERIVED_FIELDS.has(field)) return

    const applyTo = (list: Ref<MemoRow[]>): boolean => {
      const idx = list.value.findIndex((r) => r.rowId === rowId)
      if (idx === -1) return false
      const row = { ...list.value[idx] }
      if (field === 'status') {
        row.status = normalizeMemoStatus(value)
      } else if (NUMERIC_FIELDS.includes(field as keyof MemoRow)) {
        ;(row as any)[field] = parseNum(value)
      } else if (STRING_FIELDS.includes(field as keyof MemoRow)) {
        ;(row as any)[field] = String(value)
      } else {
        return false
      }
      const linked = applyRowLinkage(row, cutoffDate.value, field)
      const newRows = [...list.value]
      newRows[idx] = linked
      list.value = newRows
      return true
    }

    if (applyTo(bankRows) || applyTo(commercialRows)) {
      scheduleSave()
    }
  }

  // ─── 截止日期 / 审计说明 / 审计结论 ───────────────────────────────────────

  /** 更新截止日期（日期字段走 debounce，见 Req 13.5） */
  function setCutoffDate(value: string): void {
    if (isReadonly.value) return
    cutoffDate.value = value
    const relink = (rows: MemoRow[]) =>
      rows.map((r) => applyRowLinkage(r, value))
    bankRows.value = relink(bankRows.value)
    commercialRows.value = relink(commercialRows.value)
    scheduleSave()
  }

  function saveAuditProcedures(text: string): void {
    if (isReadonly.value) return
    auditProcedures.value = text
    scheduleSave()
  }

  function saveAuditNote(text: string): void {
    if (isReadonly.value) return
    auditNote.value = text
    scheduleSave()
  }

  function saveAuditConclusion(text: string): void {
    if (isReadonly.value) return
    auditConclusion.value = text
    scheduleSave()
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      persistToResponses()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    cutoffDate,
    bankRows,
    commercialRows,
    bankSubtotal,
    commercialSubtotal,
    grandTotal,
    reconciliationRows,
    hasDifference,
    endorsedStats,
    unexpiredSummaryRows,
    unexpiredSummaryTotal,
    unexpiredCheckDiff,
    allDataRows,
    rowWarnings,
    warningCount,
    crossSheetStatus,
    auditProcedures,
    auditNote,
    auditConclusion,
    addRow,
    removeRow,
    updateCell,
    setCutoffDate,
    saveAuditProcedures,
    saveAuditNote,
    saveAuditConclusion,
  }
}

export default useD1MemoReconciliation
