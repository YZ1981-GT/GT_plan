/**
 * API 路径 — 项目、向导、分配
 */

// ─── 项目 ───────────────────────────────────────────────────────────────────

export const projects = {
  list: '/api/projects',
  listWithProgress: '/api/projects/list-with-progress',
  detail: (id: string) => `/api/projects/${id}`,
  wizard: (id: string) => `/api/projects/${id}/wizard`,
  childCompanies: (id: string) => `/api/projects/${id}/child-companies`,
  signReadiness: (id: string) => `/api/projects/${id}/sign-readiness`,
  consistencyCheck: {
    run: (id: string) => `/api/projects/${id}/consistency-check/run`,
    get: (id: string) => `/api/projects/${id}/consistency-check`,
  },
  subsequentEvents: (id: string) => `/api/projects/${id}/subsequent-events`,
  knowledge: (id: string) => `/api/projects/${id}/knowledge`,
  workHours: (id: string) => `/api/projects/${id}/work-hours`,
  assignments: (id: string) => `/api/projects/${id}/assignments`,
  myAssignments: '/api/projects/my/assignments',
  communications: {
    list: (id: string) => `/api/projects/${id}/communications`,
    detail: (id: string, commId: string) => `/api/projects/${id}/communications/${commId}`,
    commitmentUpdate: (id: string, commId: string, commitId: string) => `/api/projects/${id}/communications/${commId}/commitments/${commitId}`,
  },
  findingsSummary: (id: string) => `/api/projects/${id}/findings-summary`,
  riskSummary: (id: string) => `/api/projects/${id}/risk-summary`,
  costOverview: (id: string) => `/api/projects/${id}/cost-overview`,
} as const

// ─── 项目管理 ───────────────────────────────────────────────────────────────

export const projectMgmt = {
  timeline: (pid: string) => `/api/projects/${pid}/timeline`,
  timelineComplete: (pid: string, tid: string) => `/api/projects/${pid}/timeline/${tid}/complete`,
  workHours: (pid: string) => `/api/projects/${pid}/work-hours`,
  budgetHours: (pid: string) => `/api/projects/${pid}/budget-hours`,
} as const

// ─── 项目配置中心 ────────────────────────────────────────────────────────────

export const projectConfig = {
  get: (pid: string) => `/api/projects/${pid}/config`,
  update: (pid: string) => `/api/projects/${pid}/config`,
  reviewConfig: {
    get: (pid: string) => `/api/projects/${pid}/review-config`,
    update: (pid: string) => `/api/projects/${pid}/review-config`,
  },
} as const

// ─── 项目工单 ───────────────────────────────────────────────────────────────

export const projectIssues = {
  list: (pid: string) => `/api/projects/${pid}/issues`,
  detail: (pid: string, issueId: string) => `/api/projects/${pid}/issues/${issueId}`,
} as const
