/**
 * 数据节点「单体项目报表 / 附注」面板的纯逻辑（spec consol-autotree-linkage-closure R6）。
 *
 * 左树选中数据节点（本部单体户、单体母公司户、子公司、分公司）时，合并页右侧直接读该企业单体项目的
 * 报表（`GET /api/reports/{pid}/{year}/{type}`）与附注（`GET /api/disclosure-notes/{pid}/{year}[/{section}]`），
 * 只读呈现；没有单体项目、无权查看、尚未生成时给中文说明，不拿合并口径数据冒充。
 */
import { fmtAmount } from '@/utils/formatters'
import { columnDepth, columnLeaves, type NoteColNode } from './consolNoteColumns'

export type StandaloneState = 'no_project' | 'forbidden' | 'not_generated' | 'failed' | 'matrix' | null
export type StandaloneMode = 'report' | 'note'

/** 矩阵格式的报表（权益变动表、资产减值准备表）：面板不展开，请进入该企业项目查看 */
export const MATRIX_REPORT_TYPES: ReadonlySet<string> = new Set(['equity_statement', 'impairment_provision'])

export function standaloneStateText(state: StandaloneState, mode: StandaloneMode): string {
  switch (state) {
    case 'no_project': return '该企业本年度没有单体项目，无法显示单体报表与附注'
    case 'forbidden': return '你不是该企业单体项目的成员，无权查看其报表与附注'
    case 'not_generated': return mode === 'report' ? '该企业单体项目尚未生成报表' : '该企业单体项目尚未生成附注'
    case 'failed': return '读取该企业单体项目数据失败，请稍后重试'
    case 'matrix': return '权益变动表、资产减值准备表为矩阵格式，请进入该企业项目查看'
    default: return ''
  }
}

/** 项目下拉列表一次最多取的条数（与 stores/project 的 loadProjectOptions 一致）；达到上限 = 可能被截断 */
export const PROJECT_OPTIONS_PAGE_SIZE = 200

/**
 * 进入 / 查看其他项目前的前端预检（只用于提示，权限仍由目标接口判定）：不在本人可见项目内 ⇒ 无权。
 * 列表为空（未加载 / 读取失败）或达到分页上限（可能被截断）时不拦，避免把有权的项目误判成无权。
 */
export function projectVisibleInOptions(options: ReadonlyArray<{ id: string }> | null | undefined, projectId: string): boolean {
  if (!Array.isArray(options) || !options.length || options.length >= PROJECT_OPTIONS_PAGE_SIZE) return true
  return options.some((p) => p.id === projectId)
}

/** 接口错误 → 面板状态（403 无权、404 未生成；其余为读取失败） */
export function stateFromError(err: any): StandaloneState {
  const status = err?.response?.status ?? err?.status
  if (status === 403) return 'forbidden'
  if (status === 404) return 'not_generated'
  return 'failed'
}

function hasAmount(v: unknown): boolean {
  return v !== null && v !== undefined && v !== ''
}

/** 报表接口在未生成时返回模板行次（金额全空）⇒ 视为尚未生成，不显示一张全空的表冒充结果 */
export function reportNotGenerated(rows: ReadonlyArray<Record<string, unknown>> | null | undefined): boolean {
  const list = Array.isArray(rows) ? rows : []
  return !list.some((r) => hasAmount(r.current_period_amount) || hasAmount(r.prior_period_amount))
}

export interface HeadCell {
  label: string
  colspan: number
  rowspan: number
}

function leafCount(node: NoteColNode): number {
  return node.children?.length ? node.children.reduce((s, c) => s + leafCount(c), 0) : 1
}

/** 列树 → 多级表头的各行格子（分组跨列、叶子跨到最底行），供只读表格直接渲染 `<thead>` */
export function headerRows(nodes: NoteColNode[]): HeadCell[][] {
  const depth = columnDepth(nodes)
  const rows: HeadCell[][] = Array.from({ length: depth }, () => [])
  const visit = (node: NoteColNode, level: number) => {
    if (node.children?.length) {
      rows[level].push({ label: node.label, colspan: leafCount(node), rowspan: 1 })
      node.children.forEach((child) => visit(child, level + 1))
    } else {
      rows[level].push({ label: node.label, colspan: 1, rowspan: depth - level })
    }
  }
  nodes.forEach((node) => visit(node, 0))
  return rows
}

/** 叶子列的表头下标（自左而右；0 = 标签列） */
export function leafIndexes(nodes: NoteColNode[]): number[] {
  return columnLeaves(nodes).map((n) => n.headerIdx ?? 0)
}

function isNumeric(v: unknown): boolean {
  if (typeof v === 'number') return Number.isFinite(v)
  return typeof v === 'string' && v.trim() !== '' && /^-?\d+(\.\d+)?$/.test(v.trim().replace(/,/g, ''))
}

/** 单元格文字：第 0 列 = 行名；数字按千分位两位小数（0 显示「-」，与平台金额口径一致）；文字原样 */
export function noteCellText(row: { label?: unknown; values?: unknown[] } | null | undefined, headerIdx: number): string {
  if (!row) return ''
  if (headerIdx === 0) return String(row.label ?? '')
  const v = Array.isArray(row.values) ? row.values[headerIdx - 1] : undefined
  if (v === null || v === undefined || v === '') return ''
  if (isNumeric(v)) return fmtAmount(typeof v === 'string' ? v.replace(/,/g, '') : v)
  return String(v)
}

/** 合计 / 小计行加粗 */
export function isTotalRow(row: { is_total?: unknown; row_type?: unknown } | null | undefined): boolean {
  if (!row) return false
  return row.is_total === true || row.row_type === 'total' || row.row_type === 'subtotal'
}

/** 附注正文可能是富文本：只读面板只显示纯文字（不渲染库里的 HTML） */
export function plainText(html: string | null | undefined): string {
  const s = String(html ?? '')
  if (!s.trim()) return ''
  if (!/[<&]/.test(s)) return s.trim()
  if (typeof DOMParser !== 'undefined') {
    const withBreaks = s.replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|div|li|h\d)>/gi, '\n')
    return (new DOMParser().parseFromString(withBreaks, 'text/html').body.textContent || '').replace(/\n{3,}/g, '\n\n').trim()
  }
  return s.replace(/<[^>]+>/g, '').trim()
}

export interface NoteSectionItem {
  note_section: string
  section_title: string
  sort_order?: number | null
  has_data?: boolean
  status?: string | null
}

/** 附注目录按模板顺序；默认选中第一个有数据的章节 */
export function sortNoteSections<T extends NoteSectionItem>(list: ReadonlyArray<T> | null | undefined): T[] {
  return [...(Array.isArray(list) ? list : [])].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
}

export function firstSectionWithData(list: ReadonlyArray<NoteSectionItem>): string | null {
  return (list.find((s) => s.has_data) || list[0])?.note_section ?? null
}
