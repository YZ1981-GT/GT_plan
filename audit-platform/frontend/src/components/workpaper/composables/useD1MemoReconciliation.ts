/**
 * useD1MemoReconciliation — D1-7 备查簿核对 composable
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 4.1
 *
 * 职责：
 * - 管理 31 列票据备查簿宽表（bankRows 银行承兑 / commercialRows 商业承兑动态行）
 * - 小计/合计 computed（bankSubtotal / commercialSubtotal / grandTotal，SUM 所有数值列）
 * - 核对区 computed（reconciliationRows 3行：备查簿合计 / 明细账D1-2 / 差异）
 *   - 明细账行通过纯 computed 从同一 allResponses Map 跨 sheet 取 D1-2 数据
 * - 贴现背书统计 computed（endorsedStats，SUMIFS 按状态汇总）
 * - 差异检测 computed（hasDifference）
 * - 截止日期 / 审计说明 / 审计结论（cutoffDate / auditNote / auditConclusion）
 * - 动态行 CRUD（addRow / removeRow / updateCell）
 * - 序列化/反序列化（JSON ↔ checklist_responses remark），debounce 2s 自动保存
 * - respect isReadonly（只读时所有写操作 no-op）
 *
 * 跨 Sheet 取数说明（明细账 D1-2 映射）：
 *   D1-2（按类别原值明细）的行以 `D1-cat-rows` 为 item_id、JSON 数组存于 remark 字段
 *   （见 useD1DetailCategory.ts）。序列化仅保存用户可编辑字段
 *   （priorUnadjusted/priorAje/priorRje/currentIncrease/currentDecrease/currentAje/currentRje），
 *   审定字段（priorAudited/currentUnadjusted/currentAudited）在加载时通过公式引擎重算。
 *   因此本 composable 读取 D1-cat-rows 后需用相同公式重建审定字段，映射如下：
 *     明细账.年初余额(beginningBalance) ← sum(priorAudited)   = sum(未审+AJE+RJE)
 *     明细账.本期增加(currentReceived)  ← sum(currentIncrease)
 *     明细账.本期减少(currentMatured)   ← sum(currentDecrease)  （作为"本期减少"代理列）
 *     明细账.期末余额(endingBalance)    ← sum(currentAudited)  = sum(期末未审+AJE+RJE)
 *     currentEndorsed / currentDiscounted ← 0（D1-2 不区分背书/贴现，置 0）
 *
 * Requirements: 4.1-4.8, 5.1-5.6, 6.1-6.5, 13.2, 13.5, 13.6, 13.7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import {
  parseNum,
  calcSubtotal,
  calcAuditedAmount,
  calcCurrentUnadjusted,
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
}

export interface ReconciliationRow {
  label: string           // '备查簿合计' | '明细账(D1-2)' | '差异'
  beginningBalance: number
  currentReceived: number
  currentEndorsed: number
  currentMatured: number
  currentDiscounted: number
  endingBalance: number
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
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成动态行 ID */
function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `dynamic-${crypto.randomUUID()}`
  }
  return `dynamic-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
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

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1MemoReconciliation(options: UseD1MemoReconciliationOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const cutoffDate = ref<string>('')
  const bankRows = ref<MemoRow[]>([])
  const commercialRows = ref<MemoRow[]>([])
  const auditNote = ref<string>('')
  const auditConclusion = ref<string>('')
  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loading')

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadMemoRows(): { bank: MemoRow[]; commercial: MemoRow[] } {
    const raw = allResponses.value.get(MEMO_ROWS_KEY)?.remark
    if (!raw) return { bank: [], commercial: [] }
    try {
      const parsed = JSON.parse(raw)
      const bankRaw = Array.isArray(parsed?.bankRows) ? parsed.bankRows : []
      const commercialRaw = Array.isArray(parsed?.commercialRows) ? parsed.commercialRows : []
      return {
        bank: bankRaw.map((r: any) => deserializeRow(r, 'bank')),
        commercial: commercialRaw.map((r: any) => deserializeRow(r, 'commercial')),
      }
    } catch {
      return { bank: [], commercial: [] }
    }
  }

  function loadFromResponses(): void {
    const { bank, commercial } = loadMemoRows()
    bankRows.value = bank
    commercialRows.value = commercial
    cutoffDate.value = allResponses.value.get(CUTOFF_KEY)?.remark ?? ''
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
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    ([newRows, newCutoff, newNote, newConclusion]) => {
      if (newRows !== undefined && newRows !== serializeMemoRows()) {
        const { bank, commercial } = loadMemoRows()
        bankRows.value = bank
        commercialRows.value = commercial
      }
      if (newCutoff !== undefined && newCutoff !== cutoffDate.value) {
        cutoffDate.value = newCutoff ?? ''
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
   * 从 allResponses 的 D1-cat-rows 读取 D1-2 数据并重建审定字段。
   * 返回 null 表示 D1-2 数据不存在/解析失败（核对区显示占位 + crossSheetStatus='error'）。
   */
  const detailLedgerRow: ComputedRef<ReconciliationRow | null> = computed(() => {
    const raw = allResponses.value.get(D1_CAT_ROWS_KEY)?.remark
    if (!raw) return null
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return null
      let beginningBalance = 0
      let currentReceived = 0
      let currentMatured = 0
      let endingBalance = 0
      for (const r of parsed) {
        // 与 useD1DetailCategory recalcRow 一致地重建审定字段
        const priorUnadjusted = parseNum(r?.priorUnadjusted)
        const priorAje = parseNum(r?.priorAje)
        const priorRje = parseNum(r?.priorRje)
        const currentIncrease = parseNum(r?.currentIncrease)
        const currentDecrease = parseNum(r?.currentDecrease)
        const currentAje = parseNum(r?.currentAje)
        const currentRje = parseNum(r?.currentRje)

        const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
        const currentUnadjusted = calcCurrentUnadjusted(priorAudited, currentIncrease, currentDecrease)
        const currentAudited = calcAuditedAmount(currentUnadjusted, currentAje, currentRje)

        beginningBalance += priorAudited
        currentReceived += currentIncrease
        currentMatured += currentDecrease
        endingBalance += currentAudited
      }
      return {
        label: '明细账(D1-2)',
        beginningBalance,
        currentReceived,
        currentEndorsed: 0,
        currentMatured,
        currentDiscounted: 0,
        endingBalance,
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

  const reconciliationRows: ComputedRef<ReconciliationRow[]> = computed(() => {
    const gt = grandTotal.value
    const memoTotal: ReconciliationRow = {
      label: '备查簿合计',
      beginningBalance: gt.beginningBalance,
      currentReceived: gt.currentReceived,
      currentEndorsed: gt.currentEndorsed,
      currentMatured: gt.currentMatured,
      currentDiscounted: gt.currentDiscounted,
      endingBalance: gt.endingBalance,
    }

    // D1-2 明细账行；无数据时占位为全 0
    const ledger: ReconciliationRow = detailLedgerRow.value ?? {
      label: '明细账(D1-2)',
      beginningBalance: 0,
      currentReceived: 0,
      currentEndorsed: 0,
      currentMatured: 0,
      currentDiscounted: 0,
      endingBalance: 0,
    }

    const diff: ReconciliationRow = {
      label: '差异',
      beginningBalance: memoTotal.beginningBalance - ledger.beginningBalance,
      currentReceived: memoTotal.currentReceived - ledger.currentReceived,
      currentEndorsed: memoTotal.currentEndorsed - ledger.currentEndorsed,
      currentMatured: memoTotal.currentMatured - ledger.currentMatured,
      currentDiscounted: memoTotal.currentDiscounted - ledger.currentDiscounted,
      endingBalance: memoTotal.endingBalance - ledger.endingBalance,
    }

    return [memoTotal, ledger, diff]
  })

  const hasDifference: ComputedRef<boolean> = computed(() => {
    const diff = reconciliationRows.value[2]
    if (!diff) return false
    return (
      diff.beginningBalance !== 0 ||
      diff.currentReceived !== 0 ||
      diff.currentEndorsed !== 0 ||
      diff.currentMatured !== 0 ||
      diff.currentDiscounted !== 0 ||
      diff.endingBalance !== 0
    )
  })

  // ─── 贴现背书统计 (SUMIFS, computed) ──────────────────────────────────────

  const endorsedStats: ComputedRef<{ discountedTotal: number; endorsedTotal: number }> = computed(() => {
    const allRows = [...bankRows.value, ...commercialRows.value]
    let discountedTotal = 0
    let endorsedTotal = 0
    for (const r of allRows) {
      if (r.status === '已贴现') discountedTotal += r.amount
      else if (r.status === '已背书') endorsedTotal += r.amount
    }
    return { discountedTotal, endorsedTotal }
  })

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

  /** 编辑单元格 → 数值字段 parseNum → debounce 保存 */
  function updateCell(rowId: string, field: string, value: string | number): void {
    if (isReadonly.value) return

    const applyTo = (list: Ref<MemoRow[]>): boolean => {
      const idx = list.value.findIndex((r) => r.rowId === rowId)
      if (idx === -1) return false
      const row = { ...list.value[idx] }
      if (NUMERIC_FIELDS.includes(field as keyof MemoRow)) {
        ;(row as any)[field] = parseNum(value)
      } else if (STRING_FIELDS.includes(field as keyof MemoRow)) {
        ;(row as any)[field] = String(value)
      } else {
        return false
      }
      const newRows = [...list.value]
      newRows[idx] = row
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
    crossSheetStatus,
    auditNote,
    auditConclusion,
    addRow,
    removeRow,
    updateCell,
    setCutoffDate,
    saveAuditNote,
    saveAuditConclusion,
  }
}

export default useD1MemoReconciliation
