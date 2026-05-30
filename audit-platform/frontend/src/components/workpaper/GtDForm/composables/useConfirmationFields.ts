/**
 * useConfirmationFields — 函证字段管理 composable
 *
 * 职责：
 * - 上下文字段数据（contextData）
 * - 阶段字段数据（stageData）+ setStageField
 * - formula 自动重算（variance_amount / variance_pct 等）
 * - 动态表格行管理（rows / handleAddRow / handleRemoveRow）
 * - 结论数据（conclusionData / onConclusionFieldChange）
 * - debounce save
 *
 * Validates: Requirements 5.2
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef, type Ref } from 'vue'
import type { StageDef, FieldDef } from './useConfirmationState'
import type { DFormData, FieldChangePayload } from '../GtDForm.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

type FieldType = 'text' | 'textarea' | 'number' | 'percent' | 'date' | 'enum'
type RenderHint = 'amount' | 'tag' | 'index_chip' | 'attachment_chip' | string

export interface ColumnDef {
  field: string
  label: string
  type?: FieldType
  enum?: string[]
  render?: RenderHint
  readonly?: boolean
  width?: number
  min?: number
  max?: number
  max_length?: number
  format?: string
  formula?: string
}

export interface DynamicTableSchema {
  start_row?: number
  end_row?: number | string
  header_row?: number
  add_row_button?: boolean
  max_rows?: number
  columns?: Record<string, ColumnDef>
}

export interface OverallOption {
  value: string
  label: string
  class?: 'success' | 'warning' | 'danger' | 'info'
  icon?: string
  description?: string
}

export interface ConclusionFieldDef {
  name: string
  label: string
  type?: string
  cell_after_table?: number
  max_length?: number
  required?: boolean
  hint?: string
  enum?: OverallOption[]
}

export interface CompositeConclusion {
  mode?: 'composite' | string
  audit_explanation_field?: ConclusionFieldDef
  overall_conclusion_field?: ConclusionFieldDef
}

export type TableRow = Record<string, any> & { _row_id?: string }

export interface ConfirmationData extends DFormData {
  context?: Record<string, any>
  workflow?: Record<string, Record<string, any>>
  active_stage?: string
  rows?: TableRow[]
  conclusion?: {
    audit_explanation?: string
    overall_conclusion?: string
  }
}

// ─── Params ──────────────────────────────────────────────────────────────────

export interface UseConfirmationFieldsParams {
  schema: () => any
  htmlData: () => DFormData
  emit: {
    (e: 'field-change', payload: FieldChangePayload): void
    (e: 'save', data: DFormData): void
  }
  readonly: () => boolean
  stages: ComputedRef<StageDef[]>
  activeStageNo: Ref<string>
  contextFields: ComputedRef<FieldDef[]>
  tableColumns: ComputedRef<ColumnDef[]>
  maxRows: ComputedRef<number>
}

// ─── Return ──────────────────────────────────────────────────────────────────

export interface UseConfirmationFieldsReturn {
  contextData: Ref<Record<string, any>>
  stageData: Ref<Record<string, Record<string, any>>>
  tableRows: Ref<TableRow[]>
  conclusionData: Ref<{ audit_explanation: string; overall_conclusion: string }>
  reachedMaxRows: ComputedRef<boolean>
  setStageField: (stageName: string, field: FieldDef, value: any) => void
  stageFieldValue: (stageName: string, field: FieldDef) => any
  handleAddRow: () => void
  handleRemoveRow: (idx: number) => void
  onCellChange: (row: TableRow, fieldName: string, idx: number) => void
  onContextFieldChange: (name: string) => void
  onConclusionFieldChange: (name: 'audit_explanation' | 'overall_conclusion') => void
  debounceSave: () => void
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function genRowId(): string {
  return `cw-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * Safe formula evaluator — 安全算术求值器（无 eval / 无 new Function）。
 *
 * 复盘改进 #6（2026-05-30）：原实现用 `new Function()` 执行公式字符串，
 * 即便有正则白名单仍存在 RCE 风险（schema 来源若被污染）。改为纯
 * tokenizer + 递归下降解析器（仅支持 + - * / 与括号 + 字段引用 + 数字字面量），
 * 完全不进入 JS 执行上下文，从根本上消除注入风险。
 *
 * 支持文法：
 *   expr   := term (('+' | '-') term)*
 *   term   := factor (('*' | '/') factor)*
 *   factor := number | identifier | '(' expr ')' | ('+' | '-') factor
 * 标识符从 ctx 取值（非有限数按 0 处理）；除零 / 非有限结果返回 null（不写入字段）。
 */
type Token =
  | { t: 'num'; v: number }
  | { t: 'id'; v: string }
  | { t: 'op'; v: '+' | '-' | '*' | '/' }
  | { t: 'lp' }
  | { t: 'rp' }

function tokenizeFormula(formula: string): Token[] | null {
  const tokens: Token[] = []
  let i = 0
  const n = formula.length
  while (i < n) {
    const ch = formula[i]
    if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') { i++; continue }
    if (ch === '+' || ch === '-' || ch === '*' || ch === '/') {
      tokens.push({ t: 'op', v: ch }); i++; continue
    }
    if (ch === '(') { tokens.push({ t: 'lp' }); i++; continue }
    if (ch === ')') { tokens.push({ t: 'rp' }); i++; continue }
    if (ch >= '0' && ch <= '9' || ch === '.') {
      let j = i + 1
      while (j < n && ((formula[j] >= '0' && formula[j] <= '9') || formula[j] === '.')) j++
      const num = Number(formula.slice(i, j))
      if (!Number.isFinite(num)) return null
      tokens.push({ t: 'num', v: num }); i = j; continue
    }
    if (/[a-zA-Z_]/.test(ch)) {
      let j = i + 1
      while (j < n && /[a-zA-Z0-9_]/.test(formula[j])) j++
      tokens.push({ t: 'id', v: formula.slice(i, j) }); i = j; continue
    }
    return null // 非法字符
  }
  return tokens
}

function evalFormula(formula: string, ctx: Record<string, any>): number | null {
  if (!formula || typeof formula !== 'string') return null
  const parsed = tokenizeFormula(formula)
  if (!parsed || parsed.length === 0) return null
  const tokens: Token[] = parsed

  let pos = 0
  const peek = (): Token | undefined => tokens[pos]

  function parseExpr(): number | null {
    let left = parseTerm()
    if (left === null) return null
    while (peek()?.t === 'op' && ((peek() as any).v === '+' || (peek() as any).v === '-')) {
      const op = (tokens[pos] as any).v as '+' | '-'
      pos++
      const right = parseTerm()
      if (right === null) return null
      left = op === '+' ? left + right : left - right
    }
    return left
  }

  function parseTerm(): number | null {
    let left = parseFactor()
    if (left === null) return null
    while (peek()?.t === 'op' && ((peek() as any).v === '*' || (peek() as any).v === '/')) {
      const op = (tokens[pos] as any).v as '*' | '/'
      pos++
      const right = parseFactor()
      if (right === null) return null
      if (op === '*') {
        left = left * right
      } else {
        if (right === 0) return null // 除零 → null（字段保持原值）
        left = left / right
      }
    }
    return left
  }

  function parseFactor(): number | null {
    const tok = peek()
    if (!tok) return null
    if (tok.t === 'op' && (tok.v === '+' || tok.v === '-')) {
      pos++
      const f = parseFactor()
      if (f === null) return null
      return tok.v === '-' ? -f : f
    }
    if (tok.t === 'num') { pos++; return tok.v }
    if (tok.t === 'id') {
      pos++
      const raw = ctx[tok.v]
      const num = Number(raw)
      return Number.isFinite(num) ? num : 0
    }
    if (tok.t === 'lp') {
      pos++
      const inner = parseExpr()
      if (inner === null) return null
      if (peek()?.t !== 'rp') return null
      pos++
      return inner
    }
    return null
  }

  const result = parseExpr()
  if (result === null) return null
  if (pos !== tokens.length) return null // 残留 token → 语法错误
  return Number.isFinite(result) ? result : null
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useConfirmationFields(params: UseConfirmationFieldsParams): UseConfirmationFieldsReturn {
  const {
    schema,
    htmlData,
    emit,
    readonly: isReadonly,
    stages,
    activeStageNo,
    contextFields,
    tableColumns,
    maxRows,
  } = params

  // ─── Refs ────────────────────────────────────────────────────────────────

  const contextData = ref<Record<string, any>>({})
  const stageData = ref<Record<string, Record<string, any>>>({})
  const tableRows = ref<TableRow[]>([])
  const conclusionData = ref<{
    audit_explanation: string
    overall_conclusion: string
  }>({
    audit_explanation: '',
    overall_conclusion: '',
  })

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Computed ────────────────────────────────────────────────────────────

  const reachedMaxRows = computed(() => tableRows.value.length >= maxRows.value)

  // ─── Formula application ─────────────────────────────────────────────────

  function applyFormulasForStage(stageName: string) {
    const stage = stages.value.find(s => s.stage === stageName)
    if (!stage) return
    const stageBucket = stageData.value[stageName] || {}
    for (const f of stage.fields || []) {
      if (f.readonly && f.formula) {
        const v = evalFormula(f.formula, stageBucket)
        if (v !== null) stageBucket[f.name] = v
      }
    }
    stageData.value[stageName] = { ...stageBucket }
  }

  // ─── Stage field accessors ───────────────────────────────────────────────

  function stageFieldValue(stageName: string, field: FieldDef): any {
    const bucket = stageData.value[stageName]
    return bucket ? bucket[field.name] : undefined
  }

  function setStageField(stageName: string, field: FieldDef, value: any) {
    if (!stageData.value[stageName]) stageData.value[stageName] = {}
    const oldValue = stageData.value[stageName][field.name]
    stageData.value[stageName][field.name] = value
    applyFormulasForStage(stageName)
    emit('field-change', {
      field_name: `workflow.${stageName}.${field.name}`,
      old_value: oldValue,
      new_value: value,
      cell: field.cell,
    })
    debounceSave()
  }

  // ─── Context field handlers ──────────────────────────────────────────────

  function onContextFieldChange(name: string) {
    emit('field-change', {
      field_name: `context.${name}`,
      old_value: undefined,
      new_value: contextData.value[name],
    })
    debounceSave()
  }

  // ─── Table row handlers ──────────────────────────────────────────────────

  function buildEmptyRow(): TableRow {
    const row: TableRow = { _row_id: genRowId() }
    for (const col of tableColumns.value) {
      if (col.type === 'number') row[col.field] = null
      else row[col.field] = ''
    }
    const seqCol = tableColumns.value.find(c => c.field === 'seq')
    if (seqCol) {
      row.seq = tableRows.value.length + 1
    }
    return row
  }

  function handleAddRow() {
    if (reachedMaxRows.value) return
    tableRows.value.push(buildEmptyRow())
    debounceSave()
  }

  function handleRemoveRow(idx: number) {
    tableRows.value.splice(idx, 1)
    const hasSeq = tableColumns.value.some(c => c.field === 'seq')
    if (hasSeq) {
      tableRows.value.forEach((r, i) => {
        r.seq = i + 1
      })
    }
    debounceSave()
  }

  function onCellChange(row: TableRow, fieldName: string, idx: number) {
    for (const col of tableColumns.value) {
      if (col.readonly && col.formula) {
        const v = evalFormula(col.formula, row)
        if (v !== null) row[col.field] = v
      }
    }
    emit('field-change', {
      field_name: `rows[${idx}].${fieldName}`,
      old_value: undefined,
      new_value: row[fieldName],
    })
    debounceSave()
  }

  // ─── Conclusion handlers ─────────────────────────────────────────────────

  function onConclusionFieldChange(name: 'audit_explanation' | 'overall_conclusion') {
    emit('field-change', {
      field_name: `conclusion.${name}`,
      old_value: undefined,
      new_value: conclusionData.value[name],
    })
    debounceSave()
  }

  // ─── Save payload + debounce ─────────────────────────────────────────────

  function buildSavePayload(): ConfirmationData {
    const payload: ConfirmationData = {
      ...(htmlData() || {}),
      context: { ...contextData.value },
      workflow: JSON.parse(JSON.stringify(stageData.value)),
      active_stage: activeStageNo.value,
      rows: tableRows.value.map(r => {
        const out: TableRow = {}
        if (r._row_id) out._row_id = r._row_id
        for (const col of tableColumns.value) {
          out[col.field] = r[col.field]
        }
        return out
      }),
      conclusion: { ...conclusionData.value },
    }
    return payload
  }

  function debounceSave() {
    if (isReadonly()) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      emit('save', buildSavePayload())
    }, 1500)
  }

  // ─── Init / Sync ─────────────────────────────────────────────────────────

  function initData() {
    const data = (htmlData() ?? {}) as ConfirmationData

    // Context fields
    const ctxIn = data.context && typeof data.context === 'object' ? data.context : {}
    const ctxOut: Record<string, any> = {}
    for (const f of contextFields.value) {
      const fallback = (f as any).default ?? ''
      ctxOut[f.name] = (ctxIn as Record<string, any>)[f.name] ?? fallback
    }
    contextData.value = ctxOut

    // Workflow stage data
    const wfIn = data.workflow && typeof data.workflow === 'object' ? data.workflow : {}
    const wfOut: Record<string, Record<string, any>> = {}
    for (const stage of stages.value) {
      const bucketIn = (wfIn as Record<string, Record<string, any>>)[stage.stage] || {}
      const bucketOut: Record<string, any> = {}
      for (const f of stage.fields || []) {
        bucketOut[f.name] = bucketIn[f.name] ?? (f.default ?? (f.type === 'number' || f.type === 'percent' ? null : ''))
      }
      wfOut[stage.stage] = bucketOut
    }
    stageData.value = wfOut

    // Apply formulas for all stages
    for (const stage of stages.value) {
      applyFormulasForStage(stage.stage)
    }

    // Active stage (update ref from state composable)
    if (typeof data.active_stage === 'string' && stages.value.some(s => s.stage === data.active_stage)) {
      activeStageNo.value = data.active_stage
    } else {
      activeStageNo.value = stages.value[0]?.stage ?? ''
    }

    // Table rows
    const rowsIn = Array.isArray(data.rows) ? data.rows : []
    tableRows.value = rowsIn.map((r): TableRow => {
      const cleaned: TableRow = { _row_id: r._row_id || genRowId() }
      for (const col of tableColumns.value) {
        if (Object.prototype.hasOwnProperty.call(r, col.field)) {
          cleaned[col.field] = r[col.field]
        } else if (col.type === 'number') {
          cleaned[col.field] = null
        } else {
          cleaned[col.field] = ''
        }
      }
      return cleaned
    })

    // Conclusion
    const c = data.conclusion && typeof data.conclusion === 'object' ? data.conclusion : {}
    conclusionData.value = {
      audit_explanation: typeof c.audit_explanation === 'string' ? c.audit_explanation : '',
      overall_conclusion: typeof c.overall_conclusion === 'string' ? c.overall_conclusion : '',
    }
  }

  initData()

  watch(
    () => htmlData(),
    () => { initData() },
    { deep: true }
  )

  watch(
    () => schema(),
    () => { initData() },
    { deep: true }
  )

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
  })

  return {
    contextData,
    stageData,
    tableRows,
    conclusionData,
    reachedMaxRows,
    setStageField,
    stageFieldValue,
    handleAddRow,
    handleRemoveRow,
    onCellChange,
    onContextFieldChange,
    onConclusionFieldChange,
    debounceSave,
  }
}
