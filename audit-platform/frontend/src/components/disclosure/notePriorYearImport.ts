/**
 * 上年附注导入（spec consol-note-header-library-and-node-reaggregate R6.6，design §15.6）：上年 Word 表格期末 → 本年期初列。
 *
 * 同一端点三种方式：`preview` 只返回逐表规划（不写）；`apply` 按用户逐表确认写入（重传同一文件 + 预览给的文件指纹，
 * 服务端不存临时文件，文件变了 409）；`auto` 是原端点行为（只写自动认出的表，界面不用）。
 * 本模块是纯函数 + 请求封装，弹窗只管展示：默认只勾「自动认出」的表；改选上年表时列对应取服务端为该表算好的
 * （上年本节的表），其他章节的表没有现成对应，要逐列指定。只填空格、不覆盖已有值由服务端保证。
 */
import { api } from '@/services/apiProxy'
import { disclosureNotes as P_notes } from '@/services/apiPaths'
import { silent } from '@/composables/useNoteTextBatch'

export type PlanStatus = 'auto' | 'needs_confirm' | 'no_source'
export type PlanMethod = 'name' | 'single_table' | 'position' | 'structure'

export interface ColumnRef { col: number; label: string }

export interface PriorTableInfo {
  id: string
  /** 所在上年标题（文档开头没有标题时为空串） */
  section: string
  caption: string
  /** 数据列（不含第 0 列行名） */
  columns: ColumnRef[]
  row_count: number
}

export interface TablePlanItem {
  /** `附注 id:表序号` */
  key: string
  note_id: string
  note_section: string
  section_title: string
  table_index: number
  table_name: string
  /** 本年表期初一侧的金额列（从上年期末一侧取数） */
  opening_columns: ColumnRef[]
  status: PlanStatus
  reason: string | null
  method: PlanMethod | null
  prior_table_id: string | null
  /** 本年列号（字符串键） → 上年列号 */
  col_map: Record<string, number>
  /** 上年同一节里的表 */
  candidates: string[]
  candidate_maps: Record<string, Record<string, number>>
  /** 按服务端选的表能填进的空格数 */
  fillable: number
  /** 有列对应的候选表各能填进的空格数（行名对不上 / 本年已有值 ⇒ 0）；一列都对不上的表不在里面 */
  candidate_fillable: Record<string, number>
}

export interface PriorYearSummary {
  matched: number
  unmatched: number
  matched_sections: string[]
  /** 上年有内容、本年附注里没有对应的标题（前 20 个） */
  unmatched_sections: string[]
  total_prior_sections: number
}

export interface PriorYearPreview extends PriorYearSummary {
  status: 'preview'
  file_sha256: string
  counts: Record<PlanStatus, number>
  tables: TablePlanItem[]
  /** 会填入上年正文的章节数（内容模板写过的不算） */
  text_sections: number
  prior_tables: PriorTableInfo[]
}

export interface PriorYearApplied extends PriorYearSummary {
  status: 'success'
  filled_cells: number
  tables_written: number
  text_filled: number
  pending_tables: number
  no_source_tables: number
  /** 真被改写的章节（编辑器据此刷新） */
  changed_sections: string[]
}

/** 文档解析不出内容 / 本年附注未生成：服务端以 200 + status=error 返回（不是 HTTP 错误） */
export interface PriorYearRefused { status: 'error'; message: string }

/** 用户对一张本年表的确认 */
export interface TableChoice {
  include: boolean
  priorTableId: string | null
  /** 本年列号（字符串键） → 上年列号；null = 这一列不导入 */
  colMap: Record<string, number | null>
  /** 手动改过列对应（可填格数以写入结果为准） */
  manual: boolean
}

export interface Decision { key: string; prior_table_id: string; col_map: Record<string, number> }

export const STATUS_ORDER: readonly PlanStatus[] = ['needs_confirm', 'auto', 'no_source']

export const STATUS_META: Record<PlanStatus, { label: string; type: 'success' | 'warning' | 'info' }> = {
  auto: { label: '自动认出', type: 'success' },
  needs_confirm: { label: '待确认', type: 'warning' },
  no_source: { label: '上年没有', type: 'info' },
}

export const METHOD_LABELS: Record<PlanMethod, string> = {
  name: '按表名',
  single_table: '本节唯一一张表',
  position: '按表的位置',
  structure: '按表头结构',
}

// ── 纯函数 ──────────────────────────────────────────────────────────────────

/** 期初列逐列取 ``known`` 里的上年列，没有的记 null（不导入） */
function colMapOf(item: TablePlanItem, known: Record<string, number> | undefined): Record<string, number | null> {
  return Object.fromEntries(item.opening_columns.map(c => [String(c.col), known?.[String(c.col)] ?? null]))
}

/** 预览后的初始确认：只勾自动认出的表，上年表与列对应取服务端选的 */
export function initialChoices(preview: PriorYearPreview): Record<string, TableChoice> {
  return Object.fromEntries(preview.tables.map(item => [item.key, {
    include: item.status === 'auto',
    priorTableId: item.prior_table_id,
    colMap: colMapOf(item, item.col_map),
    manual: false,
  }]))
}

/** 改选上年表（null = 不导入）：上年本节的表用服务端为它算好的列对应，其他表逐列待指定 */
export function switchPriorTable(item: TablePlanItem, tid: string | null): TableChoice {
  return {
    include: tid !== null,
    priorTableId: tid,
    colMap: colMapOf(item, tid ? item.candidate_maps[tid] : undefined),
    manual: false,
  }
}

/** 逐列指定（priorCol = null ⇒ 这一列不导入） */
export function setColumn(choice: TableChoice, col: number, priorCol: number | null): TableChoice {
  return { ...choice, colMap: { ...choice.colMap, [String(col)]: priorCol }, manual: true }
}

/** 按当前确认能填进的空格数；手动改过列或选的是其他章节的表 ⇒ null（以写入结果为准） */
export function fillableOf(item: TablePlanItem, choice: TableChoice | undefined): number | null {
  if (!choice?.priorTableId || choice.manual) return null
  return item.candidate_fillable[choice.priorTableId] ?? null
}

export function tableLabel(item: TablePlanItem): string {
  const title = [item.note_section, item.section_title].filter(Boolean).join(' ')
  return `${title} · ${item.table_name || `第 ${item.table_index + 1} 张表`}`
}

/** 上年表下拉项：所在标题 ·（与标题不同时）表名（截断）· 行数 ·（已知时）可填格数 */
export function priorTableLabel(table: PriorTableInfo, item: TablePlanItem): string {
  const caption = table.caption.length > 30 ? `${table.caption.slice(0, 30)}…` : table.caption
  const section = table.section || '（文档开头）'
  const fill = item.candidate_fillable[table.id]
  return [section, ...(caption && caption !== table.section ? [caption] : []), `${table.row_count} 行`,
    ...(fill === undefined ? [] : [`可填 ${fill} 格`])].join(' · ')
}

/** 选了上年表且至少指定了一列 */
export function hasMappedColumn(choice: TableChoice | undefined): boolean {
  return !!choice?.priorTableId && Object.values(choice.colMap).some(v => typeof v === 'number')
}

/** 「期初余额 ← 期末余额；期初坏账准备 ← 不导入」 */
export function columnsText(item: TablePlanItem, choice: TableChoice | undefined, prior: PriorTableInfo | undefined): string {
  return item.opening_columns.map((c) => {
    const p = choice?.colMap[String(c.col)]
    const label = p == null ? '不导入' : (prior?.columns.find(x => x.col === p)?.label || `第 ${p} 列`)
    return `${c.label} ← ${label}`
  }).join('；')
}

/** 勾选的表 → 提交给服务端的逐表确认；勾了却没选上年表 / 没指定任何列的列为问题（不能写入） */
export function toDecisions(preview: PriorYearPreview, choices: Record<string, TableChoice>):
  { decisions: Decision[]; problems: string[] } {
  const decisions: Decision[] = []
  const problems: string[] = []
  for (const item of preview.tables) {
    const choice = choices[item.key]
    if (!choice?.include) continue
    const colMap = Object.fromEntries(Object.entries(choice.colMap)
      .filter((pair): pair is [string, number] => typeof pair[1] === 'number'))
    if (!choice.priorTableId) problems.push(`${tableLabel(item)}：没有选上年表`)
    else if (!Object.keys(colMap).length) problems.push(`${tableLabel(item)}：没有指定任何列`)
    else decisions.push({ key: item.key, prior_table_id: choice.priorTableId, col_map: colMap })
  }
  return { decisions, problems }
}

export function previewSummary(preview: PriorYearPreview): string {
  const sections = `章节对上 ${preview.matched} 节`
    + (preview.unmatched ? `，上年另有 ${preview.unmatched} 节在本年附注里没有对应` : '')
  const c = preview.counts
  return `${sections}；有期初列的表：自动认出 ${c.auto} 张、待确认 ${c.needs_confirm} 张、上年没有 ${c.no_source} 张`
}

/** 写入回执；``chosen`` = 提交的表数（没填进任何格的表单独说明原因） */
export function appliedText(result: PriorYearApplied, chosen: number): string {
  const parts: string[] = []
  if (result.text_filled) parts.push(`正文 ${result.text_filled} 节`)
  if (result.filled_cells) parts.push(`表格 ${result.tables_written} 张（${result.filled_cells} 格）`)
  let text = parts.length ? `已导入${parts.join('、')}` : '没有导入任何内容'
  const idle = chosen - result.tables_written
  if (idle > 0) text += `；${idle} 张表没有可填的空格（行名对不上或本年这些格已有值）`
  return text
}

// ── 请求（静默全局拦截器：错误由调用方经 notifyBatchError 中文化后只提示一次） ─────────────────

function post<T>(projectId: string, year: number, mode: 'preview' | 'apply', file: File,
  fields: Record<string, string> = {}): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  for (const [name, value] of Object.entries(fields)) form.append(name, value)
  return api.post<T>(P_notes.importPriorYear(projectId), form, silent({ params: { year, mode } }))
}

export function previewPriorYear(projectId: string, year: number, file: File) {
  return post<PriorYearPreview | PriorYearRefused>(projectId, year, 'preview', file)
}

/** 按确认写入：重传同一文件，带预览给的文件指纹 */
export function applyPriorYear(projectId: string, year: number, file: File, fileSha256: string,
  decisions: Decision[], importText: boolean) {
  return post<PriorYearApplied | PriorYearRefused>(projectId, year, 'apply', file, {
    decisions: JSON.stringify(decisions), file_sha256: fileSha256, import_text: String(importText),
  })
}
