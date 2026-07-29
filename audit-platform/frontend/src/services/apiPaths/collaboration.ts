/**
 * API 路径 — 人员、工时、通知、PBC、函证、协作
 */

// ─── 人员 ───────────────────────────────────────────────────────────────────

export const staff = {
  list: '/api/staff',
  create: '/api/staff',
  detail: (id: string) => `/api/staff/${id}`,
  resume: (id: string) => `/api/staff/${id}/resume`,
  projects: (id: string) => `/api/staff/${id}/projects`,
  meStaffId: '/api/staff/me/staff-id',
  myTodos: '/api/staff/me/todos',
  workHours: (id: string) => `/api/staff/${id}/work-hours`,
  checkIn: (id: string) => `/api/staff/${id}/check-in`,
  checkIns: (id: string) => `/api/staff/${id}/check-ins`,
  handoverPreview: (id: string) => `/api/staff/${id}/handover/preview`,
  handover: (id: string) => `/api/staff/${id}/handover`,
  stats: '/api/staff/stats',
  exportTemplate: '/api/staff/export-template',
} as const

// ─── 工时 ───────────────────────────────────────────────────────────────────

export const workHours = {
  list: '/api/workhours',
  summary: '/api/workhours/summary',
  batchApprove: '/api/workhours/batch-approve',
  detail: (hourId: string) => `/api/work-hours/${hourId}`,
  editTimeSuggest: '/api/work-hours/edit-time-suggest',
  /** 智能填报建议（基于项目分配 + 历史工时推荐当日候选项） */
  aiSuggest: '/api/work-hours/ai-suggest',
  /** 跨项目工时条目查询（消除逐项目 N+1） */
  myEntries: '/api/my/work-hour-entries',
} as const

// ─── 工时条目（细粒度） ──────────────────────────────────────────────────────

export const workHourEntries = {
  list: (projectId: string) => `/api/projects/${projectId}/workhours`,
  create: (projectId: string) => `/api/projects/${projectId}/workhours`,
  detail: (projectId: string, entryId: string) => `/api/projects/${projectId}/workhours/${entryId}`,
  batchSubmit: (projectId: string) => `/api/projects/${projectId}/workhours/batch-submit`,
  summary: (projectId: string) => `/api/projects/${projectId}/workhours/summary`,
} as const

// ─── 通知 ───────────────────────────────────────────────────────────────────

export const notifications = {
  list: '/api/notifications',
  unreadCount: '/api/notifications/unread-count',
  read: (id: string) => `/api/notifications/${id}/read`,
  readAll: '/api/notifications/read-all',
  delete: (id: string) => `/api/notifications/${id}`,
} as const

// ─── PBC ────────────────────────────────────────────────────────────────────

export const pbc = {
  items: (pid: string) => `/api/pbc/${pid}/items`,
  itemStatus: (pid: string, itemId: string) => `/api/pbc/${pid}/items/${itemId}/status`,
  pendingReminders: (pid: string) => `/api/pbc/${pid}/pending-reminders`,
} as const

// ─── 函证 ───────────────────────────────────────────────────────────────────

export const confirmations = {
  list: (pid: string) => `/api/confirmations/${pid}/confirmations`,
  detail: (pid: string, confId: string) => `/api/confirmations/${pid}/confirmations/${confId}`,
  letter: (pid: string, confId: string) => `/api/confirmations/${pid}/confirmations/${confId}/letter`,
  result: (pid: string, confId: string) => `/api/confirmations/${pid}/confirmations/${confId}/result`,
  summary: (pid: string) => `/api/confirmations/${pid}/summary`,
} as const

// ─── 批注 ───────────────────────────────────────────────────────────────────

export const annotations = {
  list: (pid: string) => `/api/projects/${pid}/annotations`,
  create: (pid: string) => `/api/projects/${pid}/annotations`,
  update: (id: string) => `/api/annotations/${id}`,
} as const

// ─── 复核对话 ───────────────────────────────────────────────────────────────

export const reviewConversations = {
  list: '/api/review-conversations',
  detail: (id: string) => `/api/review-conversations/${id}`,
  messages: (id: string) => `/api/review-conversations/${id}/messages`,
  close: (id: string) => `/api/review-conversations/${id}/close`,
  export: (id: string) => `/api/review-conversations/${id}/export`,
  projectList: (pid: string) => `/api/review-conversations?project_id=${pid}`,
} as const

// ─── 论坛 ───────────────────────────────────────────────────────────────────

export const forum = {
  posts: '/api/forum/posts',
  comments: (postId: string) => `/api/forum/posts/${postId}/comments`,
  like: (postId: string) => `/api/forum/posts/${postId}/like`,
} as const

// ─── SSE 事件流 ─────────────────────────────────────────────────────────────

export const events = {
  stream: (pid: string) => `/api/projects/${pid}/events/stream`,
} as const

// ─── Presence（在线感知） ────────────────────────────────────────────────────

export const presence = {
  heartbeat: (pid: string) => `/api/projects/${pid}/presence/heartbeat`,
  online: (pid: string) => `/api/projects/${pid}/presence/online`,
  editing: (pid: string) => `/api/projects/${pid}/presence/editing`,
} as const

// ─── 同步 ───────────────────────────────────────────────────────────────────

export const sync = {
  status: (pid: string) => `/api/sync/status/${pid}`,
  lock: (pid: string) => `/api/sync/lock/${pid}`,
  unlock: (pid: string) => `/api/sync/unlock/${pid}`,
  sync: (pid: string) => `/api/sync/sync/${pid}`,
  conflicts: {
    detect: (pid: string) => `/api/sync-conflicts/${pid}/detect`,
    resolve: (pid: string) => `/api/sync-conflicts/${pid}/resolve`,
    history: (pid: string) => `/api/sync-conflicts/${pid}/history`,
  },
} as const

// ─── 独立性声明（项目级） ───────────────────────────────────────────────────

export const independenceDeclarations = {
  questions: '/api/independence/questions',
  list: (pid: string) => `/api/projects/${pid}/independence-declarations`,
  detail: (pid: string, declId: string) => `/api/projects/${pid}/independence-declarations/${declId}`,
  submit: (pid: string, declId: string) => `/api/projects/${pid}/independence-declarations/${declId}/submit`,
} as const

// ─── 我的（个人聚合） ────────────────────────────────────────────────────────

export const my = {
  pendingIndependence: '/api/my/pending-independence',
  reminders: '/api/my/reminders',
  unreadAnnotations: '/api/my/unread-annotations/count',
} as const
