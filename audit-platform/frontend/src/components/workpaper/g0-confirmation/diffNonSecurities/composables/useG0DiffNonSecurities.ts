/**
 * useG0DiffNonSecurities — G0-4(非证券) 三维差异核对数据 composable
 *
 * 三维差异计算（Requirement 2.1/2.2/2.3/7.1，Property 4）：
 *   - 数值维（投资金额）：amount_diff = booked_amount − reply_amount（符号固定）
 *   - 比例维（持股比例）：ratio_diff = booked_ratio − reply_ratio（百分点，scale=百分比数值）
 *   - 条款维（投资条款）：不做数值相减，term_match(一致/不一致) + term_diff_note 文本
 *
 * 旧数据兼容（Requirement 2.6，Property 7）：既有录在共享 diff-reconcile-v1 的非证券差异，
 *   hydrate 时映射到投资金额维（sent→booked_amount / reply→reply_amount / difference→amount_diff），
 *   持股比例维与条款维为空，不静默丢弃。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  NonSecuritiesDiffRow,
  NonSecuritiesDiffPayload,
  NonSecuritiesDiffMetrics,
} from '../nonSecuritiesDiffTypes'

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function toNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 精确两位小数（避浮点漂移） */
function round2(n: number): number {
  return Math.round(n * 100) / 100
}

/**
 * recalcRow — 三维差异派生（纯函数，Property 4）。
 * 金额/比例做带符号相减；条款维绝不相减（仅 term_match）。
 */
export function recalcRow(row: NonSecuritiesDiffRow): NonSecuritiesDiffRow {
  return {
    ...row,
    ratio_diff: round2(toNum(row.booked_ratio) - toNum(row.reply_ratio)),
    amount_diff: round2(toNum(row.booked_amount) - toNum(row.reply_amount)),
  }
}

/** 某行是否有差异（比例/金额任一 ≠0，或条款不一致） */
export function rowHasDiff(row: NonSecuritiesDiffRow): boolean {
  return Math.abs(toNum(row.ratio_diff)) > 0.001
    || Math.abs(toNum(row.amount_diff)) > 0.01
    || row.term_match === '不一致'
}

/**
 * hydrateFromReconcile — 旧共享 diff-reconcile-v1 payload → 非证券三维行（Property 7）。
 * 仅映射投资金额维，比例/条款维留空；不静默丢弃。纯函数，可单测。
 */
export function hydrateFromReconcile(data: any): NonSecuritiesDiffRow[] {
  if (!data || data._format !== 'diff-reconcile-v1' || !Array.isArray(data.rows)) return []
  return data.rows.map((r: any, i: number) =>
    recalcRow({
      _row_id: generateId(),
      seq: i + 1,
      confirm_index: r.confirm_index,
      entity_name: r.entity_name,
      booked_amount: r.sent_amount,
      reply_amount: r.reply_amount,
      diff_reason: r.diff_note,
      need_adjust: r.needs_adjustment ? '是' : undefined,
      adj_ref_index: r.adj_ref_index,
      support_evidence: r.support_evidence,
      remark: r.diff_note,
      _source: 'hydrated-from-reconcile',
    }),
  )
}

export interface UseG0DiffNonSecuritiesProps {
  htmlData: () => any
  readonly: boolean
}

export interface UseG0DiffNonSecuritiesReturn {
  rows: Ref<NonSecuritiesDiffRow[]>
  conclusion: Ref<string>
  auditNote: Ref<string>
  isDirty: Ref<boolean>
  metrics: ComputedRef<NonSecuritiesDiffMetrics>
  addRow: () => NonSecuritiesDiffRow
  deleteRow: (rowId: string) => void
  updateRow: (rowId: string, field: string, value: unknown) => void
  rowHasDiff: (row: NonSecuritiesDiffRow) => boolean
  hydrateLegacyReconcile: (data: any) => number
  buildPayload: () => NonSecuritiesDiffPayload
}

export function useG0DiffNonSecurities(props: UseG0DiffNonSecuritiesProps): UseG0DiffNonSecuritiesReturn {
  const rows = ref<NonSecuritiesDiffRow[]>([])
  const conclusion = ref('')
  const auditNote = ref('')
  const isDirty = ref(false)

  function ensureRowId(row: NonSecuritiesDiffRow): NonSecuritiesDiffRow {
    return row._row_id ? row : { ...row, _row_id: generateId() }
  }

  function initFromHtmlData(data: any) {
    if (data && data._format === 'diff-nonsecurities-v1') {
      rows.value = Array.isArray(data.rows)
        ? data.rows.map((r: NonSecuritiesDiffRow) => recalcRow(ensureRowId(r)))
        : []
      conclusion.value = data.conclusion || ''
      auditNote.value = data.audit_note || ''
      isDirty.value = false
      return
    }
    // 旧共享 diff-reconcile-v1（既有项目把非证券差异录在共享调节表）→ hydrate 到金额维
    if (data && data._format === 'diff-reconcile-v1') {
      rows.value = hydrateFromReconcile(data)
      conclusion.value = data.conclusion?.conclusion_text || ''
      auditNote.value = data.audit_note?.note_general || ''
      isDirty.value = false
      return
    }
    rows.value = []
    conclusion.value = ''
    auditNote.value = ''
    isDirty.value = false
  }

  initFromHtmlData(props.htmlData())
  watch(() => props.htmlData(), (d) => initFromHtmlData(d), { deep: true })

  function addRow(): NonSecuritiesDiffRow {
    const maxSeq = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    const newRow = recalcRow({ _row_id: generateId(), seq: maxSeq + 1, _source: 'manual' })
    rows.value.push(newRow)
    isDirty.value = true
    return newRow
  }

  function deleteRow(rowId: string) {
    rows.value = rows.value.filter((r) => r._row_id !== rowId)
    isDirty.value = true
  }

  function updateRow(rowId: string, field: string, value: unknown) {
    const idx = rows.value.findIndex((r) => r._row_id === rowId)
    if (idx < 0) return
    rows.value[idx] = recalcRow({ ...rows.value[idx], [field]: value })
    isDirty.value = true
  }

  /** 手工触发从旧共享 diff-reconcile-v1 hydrate（返回带入行数） */
  function hydrateLegacyReconcile(data: any): number {
    const mapped = hydrateFromReconcile(data)
    const existing = new Set(rows.value.map((r) => r.confirm_index).filter(Boolean))
    const deduped = mapped.filter((r) => !r.confirm_index || !existing.has(r.confirm_index))
    if (deduped.length) {
      rows.value.push(...deduped)
      isDirty.value = true
    }
    return deduped.length
  }

  const metrics = computed<NonSecuritiesDiffMetrics>(() => {
    let diffCount = 0
    let amountAbs = 0
    for (const row of rows.value) {
      if (rowHasDiff(row)) diffCount++
      amountAbs += Math.abs(toNum(row.amount_diff))
    }
    const total = rows.value.length
    return {
      total_count: total,
      diff_count: diffCount,
      no_diff_count: total - diffCount,
      amount_diff_abs_total: round2(amountAbs),
    }
  })

  function buildPayload(): NonSecuritiesDiffPayload {
    return {
      _format: 'diff-nonsecurities-v1',
      rows: rows.value.map(recalcRow),
      conclusion: conclusion.value,
      audit_note: auditNote.value,
    }
  }

  return {
    rows,
    conclusion,
    auditNote,
    isDirty,
    metrics,
    addRow,
    deleteRow,
    updateRow,
    rowHasDiff,
    hydrateLegacyReconcile,
    buildPayload,
  }
}
