/**
 * EvidenceRef 统一证据引用类型 (与 backend EvidenceRef schema 对齐)
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
