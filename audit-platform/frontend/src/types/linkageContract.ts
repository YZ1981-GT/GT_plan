export type SourceType = 'trial_balance' | 'ledger' | 'audit_sheet' | 'workpaper' | 'adjustment' | 'report' | 'note' | 'attachment' | 'ai'
export type TargetType = SourceType
export type LinkageStatus = 'current' | 'stale' | 'conflict' | 'manual_override'
export type LinkageConfidence = 'system' | 'manual' | 'ai_suggested' | 'ai_confirmed'

export interface LinkageContract {
  source_type: SourceType
  source_id: string
  source_cell?: string | null
  target_type: TargetType
  target_id: string
  target_cell?: string | null
  amount?: string | null
  basis?: string | null
  status: LinkageStatus
  confidence: LinkageConfidence
  route?: string | null
  audit_log_id?: string | null
}
