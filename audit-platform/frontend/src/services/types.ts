// Shared TypeScript types for collaboration module
export interface ProjectUser {
  id: string
  username: string
  display_name: string | null
  role: string
  project_role: string
  assigned_cycles: string[]
}

export interface User {
  id: string
  username: string
  display_name: string | null
  email: string | null
  is_active: boolean
}

export interface Notification {
  id: string
  title: string
  content: string | null
  is_read: boolean
  created_at: string
  notification_type: string
  related_object_type: string | null
  related_object_id: string | null
}

export interface ReviewRecord {
  id: string
  workpaper_id: string
  project_id: string
  review_level: number
  review_status: string
  reviewer_id: string | null
  comments: string | null
  reply_text: string | null
  created_at: string
  updated_at: string
}

export interface AuditLog {
  id: string
  created_at: string
  user_id: string
  operation_type: string
  object_type: string | null
  object_id: string | null
  details: Record<string, any> | null
  ip_address: string | null
}

export interface SyncStatus {
  global_version: string
  sync_status: string
  is_locked: boolean
  last_synced_at: string | null
  locked_by: string | null
}
