/**
 * EvidenceRef 统一证据引用类型 (与 backend EvidenceRef schema 对齐)
 *
 * P0-2: 支持 attachment/workpaper_cell/report_paragraph/note_table/ai_output/deliverable
 */

export type EvidenceType =
  | 'attachment'
  | 'workpaper_cell'
  | 'report_paragraph'
  | 'note_table'
  | 'ai_output'
  | 'deliverable'

export interface EvidenceRef {
  evidence_type: EvidenceType
  evidence_id: string
  project_id: string
  year?: number | null
  label?: string | null
  route?: string | null
  hash?: string | null
  version?: string | null
}

/** 各 evidence_type 对应的前端路由模板 */
const ROUTE_TEMPLATES: Record<EvidenceType, string> = {
  attachment: '/projects/{project_id}/attachments/{evidence_id}',
  workpaper_cell: '/projects/{project_id}/workpapers/{evidence_id}',
  report_paragraph: '/projects/{project_id}/report/{evidence_id}',
  note_table: '/projects/{project_id}/notes/{evidence_id}',
  ai_output: '/projects/{project_id}/ai-content/{evidence_id}',
  deliverable: '/projects/{project_id}/deliverables/{evidence_id}',
}

/**
 * 解析 EvidenceRef 的前端跳转路由。
 * 若 ref.route 已有显式值则直接返回，否则按模板生成。
 */
export function resolveEvidenceRoute(ref: EvidenceRef): string {
  if (ref.route) return ref.route
  const template = ROUTE_TEMPLATES[ref.evidence_type] ?? ''
  return template
    .replace('{project_id}', ref.project_id)
    .replace('{evidence_id}', ref.evidence_id)
}

/** 所有合法 evidence_type 值列表 */
export const EVIDENCE_TYPES: EvidenceType[] = [
  'attachment',
  'workpaper_cell',
  'report_paragraph',
  'note_table',
  'ai_output',
  'deliverable',
]
