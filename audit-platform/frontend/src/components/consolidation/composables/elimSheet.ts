/**
 * 合并抵消分录明细表的纯逻辑（spec consol-elimination-single-source-push 任务 10 / 需求 1~2）。
 *
 * 明细表只读分录表（唯一来源）：一行 = 一笔分录的一条明细；分录级列（编号、来源、归属、类型、说明、状态、操作）
 * 跨该分录的明细行合并显示。「待生成」区展示工作底稿来源分组的预演结果（后端 dry_run），生成后变草稿分录。
 */
import type {
  ElimTreeLine,
  EliminationEntry,
  GenerateAction,
  GenerateFromWorksheetResult,
  GenerateGroupResult,
} from '@/services/consolidationApi'

/** 同一分录的明细行（后端保证相邻且按 line_index 递增） */
export function linesOfEntry(rows: ReadonlyArray<ElimTreeLine>, entryId: string): ElimTreeLine[] {
  return rows.filter((r) => r.entry_id === entryId)
}

/** 明细行 → 分录（修改表单回填用）；明细无法识别的占位行（无科目）不回填 */
export function entryFromLines(lines: ReadonlyArray<ElimTreeLine>, year: number | null): EliminationEntry | null {
  const first = lines[0]
  if (!first) return null
  const real = lines.filter((l) => l.account_code)
  return {
    id: first.entry_id,
    project_id: first.host_project_id,
    entry_no: first.entry_no,
    year: year ?? 0,
    entry_type: first.entry_type,
    description: first.description,
    related_company_codes: first.related_company_codes,
    branch_entity_code: first.branch_entity_code,
    review_status: first.review_status,
    debit_amount: '0',
    credit_amount: '0',
    origin: first.origin,
    origin_key: first.origin_key,
    lines: real.map((l) => ({
      account_code: l.account_code || '',
      account_name: l.account_name,
      debit_amount: l.debit || '0',
      credit_amount: l.credit || '0',
    })),
  }
}

/** 分录级列合并：首行跨 line_count 行，其余行隐藏（el-table span-method 返回值） */
export function entrySpan(row: Pick<ElimTreeLine, 'line_index' | 'line_count'>): { rowspan: number; colspan: number } {
  if (row.line_index > 1) return { rowspan: 0, colspan: 0 }
  return { rowspan: Math.max(1, row.line_count || 1), colspan: 1 }
}

// ─── 待生成（生成接口的预演 / 执行结果）────────────────────────────────────────

const ACTION_TEXT: Record<GenerateAction, { dry: string; done: string; tag: 'success' | 'warning' | 'danger' | 'info' | 'primary' }> = {
  created: { dry: '将新建', done: '已新建', tag: 'success' },
  updated: { dry: '将更新', done: '已更新', tag: 'primary' },
  unchanged: { dry: '无变化', done: '无变化', tag: 'info' },
  blocked: { dry: '不能生成', done: '未生成', tag: 'danger' },
  review_locked: { dry: '已提交审批，未改动', done: '已提交审批，未改动', tag: 'warning' },
  empty: { dry: '无金额', done: '无金额', tag: 'info' },
  discarded: { dry: '已删除，不再转入', done: '已删除，不再转入', tag: 'info' },
}

export function actionLabel(action: string, dryRun: boolean): string {
  const t = ACTION_TEXT[action as GenerateAction]
  return t ? (dryRun ? t.dry : t.done) : action
}

export function actionTagType(action: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  return ACTION_TEXT[action as GenerateAction]?.tag || 'info'
}

export interface PendingSummary {
  groups: number
  created: number
  updated: number
  unchanged: number
  blocked: number
  reviewLocked: number
  deleted: number
  /** 有可写入的变化（新建 / 更新 / 删除草稿）⇒ 「生成草稿分录」可点 */
  actionable: boolean
}

export function pendingSummary(result: GenerateFromWorksheetResult | null | undefined): PendingSummary {
  const groups = result?.groups || []
  const count = (a: string) => groups.filter((g) => g.action === a).length
  const s = {
    groups: groups.length,
    created: count('created'),
    updated: count('updated'),
    unchanged: count('unchanged'),
    blocked: count('blocked'),
    reviewLocked: count('review_locked'),
    deleted: result?.deleted_entries?.length || 0,
  }
  return { ...s, actionable: s.created + s.updated + s.deleted > 0 }
}

/** 预演摘要一句话（待生成区标题下） */
export function pendingSummaryText(s: PendingSummary): string {
  if (!s.groups && !s.deleted) return '工作底稿暂无待生成的抵销'
  const parts = [`共 ${s.groups} 组`]
  if (s.created) parts.push(`将新建 ${s.created}`)
  if (s.updated) parts.push(`将更新 ${s.updated}`)
  if (s.unchanged) parts.push(`无变化 ${s.unchanged}`)
  if (s.blocked) parts.push(`不能生成 ${s.blocked}`)
  if (s.reviewLocked) parts.push(`已提交审批未改动 ${s.reviewLocked}`)
  if (s.deleted) parts.push(`将删除草稿 ${s.deleted} 笔`)
  return parts.join('，')
}

/** 分组级原因（借贷不平、类型不符等）：已在对应来源行上显示的逐行原因不重复列 */
export function groupReasons(group: Pick<GenerateGroupResult, 'reasons' | 'lines'>): string[] {
  const lineReasons = new Set(group.lines.map((l) => l.reason).filter(Boolean))
  return group.reasons.filter((r) => !lineReasons.has(r))
}

/** 将删除的草稿（来源数据已不再产出）：生成前须二次确认 */
export function deletionConfirmText(result: GenerateFromWorksheetResult): string {
  const nos = (result.deleted_entries || []).map((d) => d.entry_no).filter(Boolean)
  if (!nos.length) return ''
  const shown = nos.slice(0, 10).join('、') + (nos.length > 10 ? ` 等 ${nos.length} 笔` : '')
  return `以下草稿分录的来源数据已不再产出，生成时将删除：${shown}。确认继续？`
}

/** 生成完成后的提示 */
export function generateResultText(result: GenerateFromWorksheetResult): string {
  const parts: string[] = []
  if (result.created) parts.push(`新建 ${result.created} 笔`)
  if (result.updated) parts.push(`更新 ${result.updated} 笔`)
  if (result.deleted) parts.push(`删除 ${result.deleted} 笔`)
  const head = parts.length ? `已生成草稿分录：${parts.join('、')}` : '草稿分录无变化'
  const tail: string[] = []
  if (result.blocked?.length) tail.push(`${result.blocked.length} 组不能生成，原因见待生成区`)
  if (result.changed_after_review?.length) tail.push(`${result.changed_after_review.length} 笔已提交审批的分录来源数据已变化，未改动`)
  return tail.length ? `${head}；${tail.join('；')}` : head
}

// ─── 导出 ────────────────────────────────────────────────────────────────────

export const EXPORT_COLUMNS = [
  { key: 'entry_no', header: '分录编号', width: 14 },
  { key: 'origin_label', header: '来源', width: 12 },
  { key: 'node_label', header: '归属节点', width: 20 },
  { key: 'entry_type_label', header: '类型', width: 14 },
  { key: 'account_code', header: '科目编码', width: 12 },
  { key: 'account_name', header: '科目名称', width: 20 },
  { key: 'debit', header: '借方', width: 16 },
  { key: 'credit', header: '贷方', width: 16 },
  { key: 'description', header: '说明', width: 30 },
  { key: 'review_status_label', header: '状态', width: 10 },
  { key: 'counted_label', header: '计入合并', width: 10 },
  { key: 'host_project_name', header: '承载项目', width: 20 },
] as const

export function exportRows(rows: ReadonlyArray<ElimTreeLine>): Record<string, string | number | null>[] {
  return rows.map((r) => ({
    entry_no: r.entry_no,
    origin_label: r.origin_label,
    node_label: r.node_label || (r.orphan_reason ? `（未归属）${r.orphan_reason}` : ''),
    entry_type_label: r.entry_type_label,
    account_code: r.account_code,
    account_name: r.account_name,
    // 导出给数字（Excel 可求和）；金额文本是到分的规范值
    debit: r.debit === null ? null : Number(r.debit),
    credit: r.credit === null ? null : Number(r.credit),
    description: r.description,
    review_status_label: r.review_status_label,
    counted_label: r.counted ? '是' : '否',
    host_project_name: r.host_project_name,
  }))
}
