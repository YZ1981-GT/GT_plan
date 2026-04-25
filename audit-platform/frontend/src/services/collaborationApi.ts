
/**
 * 协作与质控 API 服务层
 */
import http from '@/utils/http'

// Auth
export const authApi = {
  login: (username: string, password: string) =>
    http.post('/api/auth/login', { username, password }),
  refresh: (refresh_token: string) =>
    http.post('/api/auth/refresh', { refresh_token }),
  logout: () => http.post('/api/auth/logout'),
  me: () => http.get('/api/auth/me'),
}

// Notifications
export const notificationApi = {
  list: (params?: { unread_only?: boolean; skip?: number; limit?: number }) =>
    http.get('/api/notifications', { params }),
  unreadCount: () => http.get('/api/notifications/unread-count'),
  markRead: (id: string) => http.post(`/api/notifications/${id}/read`),
  markAllRead: () => http.post('/api/notifications/read-all'),
  delete: (id: string) => http.delete(`/api/notifications/${id}`),
}

// Projects & Users
export const projectApi = {
  list: () => http.get('/api/projects'),
  get: (id: string) => http.get(`/api/projects/${id}`),
  create: (data: any) => http.post('/api/projects', data),
  update: (id: string, data: any) => http.put(`/api/projects/${id}`, data),
  delete: (id: string) => http.delete(`/api/projects/${id}`),
}

export const userApi = {
  list: (params?: any) => http.get('/api/users', { params }),
  get: (id: string) => http.get(`/api/users/${id}`),
  invite: (projectId: string, data: any) =>
    http.post(`/api/projects/${projectId}/users`, data),
  remove: (projectId: string, userId: string) =>
    http.delete(`/api/projects/${projectId}/users/${userId}`),
  updateRole: (projectId: string, userId: string, data: any) =>
    http.patch(`/api/projects/${projectId}/users/${userId}`, data),
}

// Reviews
export const reviewApi = {
  create: (data: { workpaper_id: string; project_id: string; review_level: number }) =>
    http.post('/api/reviews', data),
  list: (workpaperId: string) =>
    http.get(`/api/reviews/workpaper/${workpaperId}`),
  pending: (params?: any) =>
    http.get('/api/reviews/pending', { params }),
  start: (reviewId: string) =>
    http.post(`/api/reviews/${reviewId}/start`),
  approve: (reviewId: string, data?: { comments?: string; reply_text?: string }) =>
    http.post(`/api/reviews/${reviewId}/approve`, data),
  reject: (reviewId: string, data: { comments: string }) =>
    http.post(`/api/reviews/${reviewId}/reject`, data),
}

// Sync
export const syncApi = {
  status: (projectId: string) =>
    http.get(`/api/sync/status/${projectId}`),
  lock: (projectId: string) =>
    http.post(`/api/sync/lock/${projectId}`),
  unlock: (projectId: string) =>
    http.post(`/api/sync/unlock/${projectId}`),
  sync: (projectId: string, syncType?: string) =>
    http.post(`/api/sync/sync/${projectId}`, null, { params: { sync_type: syncType } }),
  detectConflict: (projectId: string, localData: any, serverData: any) =>
    http.post(`/api/sync-conflicts/${projectId}/detect`, { local_data: localData, server_data: serverData }),
  resolveConflict: (projectId: string, data: any) =>
    http.post(`/api/sync-conflicts/${projectId}/resolve`, data),
  conflictHistory: (projectId: string) =>
    http.get(`/api/sync-conflicts/${projectId}/history`),
}

// Audit logs
export const auditLogApi = {
  list: (params?: any) =>
    http.get('/api/audit-logs', { params }),
}

// Project management
export const projectMgmtApi = {
  createMilestone: (projectId: string, data: any) =>
    http.post(`/api/projects/${projectId}/timeline`, data),
  getTimeline: (projectId: string) =>
    http.get(`/api/projects/${projectId}/timeline`),
  completeMilestone: (projectId: string, timelineId: string) =>
    http.post(`/api/projects/${projectId}/timeline/${timelineId}/complete`),
  logWorkHours: (projectId: string, data: any) =>
    http.post(`/api/projects/${projectId}/work-hours`, data),
  getWorkHours: (projectId: string, params?: any) =>
    http.get(`/api/projects/${projectId}/work-hours`, { params }),
  setBudget: (projectId: string, data: any) =>
    http.post(`/api/projects/${projectId}/budget-hours`, data),
  getBudget: (projectId: string) =>
    http.get(`/api/projects/${projectId}/budget-hours`),
}

// Archive
export const archiveApi = {
  initChecklist: (projectId: string) =>
    http.post(`/api/archive/${projectId}/checklist/init`),
  getChecklist: (projectId: string) =>
    http.get(`/api/archive/${projectId}/checklist`),
  completeItem: (projectId: string, itemId: string, notes?: string) =>
    http.post(`/api/archive/${projectId}/checklist/${itemId}/complete`, null, { params: { notes } }),
  archive: (projectId: string) =>
    http.post(`/api/archive/${projectId}/archive`),
  exportPdf: (projectId: string, data?: { password?: string }) =>
    http.post(`/api/archive/${projectId}/export-pdf`, data),
  requestModification: (projectId: string, data: any) =>
    http.post(`/api/archive/${projectId}/modifications`, data),
  approveModification: (projectId: string, modId: string, comments?: string) =>
    http.post(`/api/archive/${projectId}/modifications/${modId}/approve`, null, { params: { comments } }),
  rejectModification: (projectId: string, modId: string, comments?: string) =>
    http.post(`/api/archive/${projectId}/modifications/${modId}/reject`, null, { params: { comments } }),
}

// Subsequent Events
export const subsequentEventApi = {
  createEvent: (projectId: string, data: any) =>
    http.post(`/api/subsequent-events/${projectId}/events`, data),
  getEvents: (projectId: string) =>
    http.get(`/api/subsequent-events/${projectId}/events`),
  initChecklist: (projectId: string) =>
    http.post(`/api/subsequent-events/${projectId}/checklist/init`),
  getChecklist: (projectId: string) =>
    http.get(`/api/subsequent-events/${projectId}/checklist`),
  completeChecklistItem: (projectId: string, itemId: string, notes?: string) =>
    http.post(`/api/subsequent-events/${projectId}/checklist/${itemId}/complete`, null, { params: { notes } }),
}

// PBC
export const pbcApi = {
  createItem: (projectId: string, data: any) =>
    http.post(`/api/pbc/${projectId}/items`, data),
  getItems: (projectId: string) =>
    http.get(`/api/pbc/${projectId}/items`),
  updateStatus: (projectId: string, itemId: string, data: any) =>
    http.patch(`/api/pbc/${projectId}/items/${itemId}/status`, null, { params: data }),
  pendingReminders: (projectId: string) =>
    http.get(`/api/pbc/${projectId}/pending-reminders`),
}

// Confirmations
export const confirmationApi = {
  create: (projectId: string, data: any) =>
    http.post(`/api/confirmations/${projectId}/confirmations`, data),
  list: (projectId: string) =>
    http.get(`/api/confirmations/${projectId}/confirmations`),
  generateLetter: (projectId: string, confId: string, data: any) =>
    http.post(`/api/confirmations/${projectId}/confirmations/${confId}/letter`, data),
  recordResult: (projectId: string, confId: string, data: any) =>
    http.post(`/api/confirmations/${projectId}/confirmations/${confId}/result`, data),
  createSummary: (projectId: string, data: any) =>
    http.post(`/api/confirmations/${projectId}/summary`, data),
}

// Going Concern
export const goingConcernApi = {
  init: (projectId: string) =>
    http.post(`/api/going-concern/${projectId}/init`),
  createEvaluation: (projectId: string, data?: any) =>
    http.post(`/api/going-concern/${projectId}/evaluation`, data),
  getEvaluation: (projectId: string) =>
    http.get(`/api/going-concern/${projectId}/evaluation`),
  updateEvaluation: (projectId: string, gcId: string, data: any) =>
    http.patch(`/api/going-concern/${projectId}/evaluation/${gcId}`, data),
  getIndicators: (projectId: string, gcId: string) =>
    http.get(`/api/going-concern/${projectId}/evaluation/${gcId}/indicators`),
  updateIndicator: (projectId: string, gcId: string, indId: string, data: any) =>
    http.patch(`/api/going-concern/${projectId}/evaluation/${gcId}/indicators/${indId}`, data),
}

// Risk Assessment
export const riskApi = {
  list: (projectId: string) =>
    http.get(`/api/risk-assessments/projects/${projectId}/risk-assessments`),
  create: (projectId: string, data: any) =>
    http.post(`/api/risk-assessments/projects/${projectId}/risk-assessments`, data),
  updateResponse: (projectId: string, assessmentId: string, data: any) =>
    http.put(`/api/risk-assessments/projects/${projectId}/risk-assessments/${assessmentId}/response`, data),
  verifyCoverage: (projectId: string, assessmentId: string) =>
    http.post(`/api/risk-assessments/projects/${projectId}/risk-assessments/${assessmentId}/verify-coverage`),
  getRiskMatrix: (projectId: string) =>
    http.get(`/api/risk-assessments/projects/${projectId}/risk-matrix`),
  getOverallRisk: (projectId: string) =>
    http.get(`/api/risk-assessments/projects/${projectId}/overall-risk`),
}

// Audit Program
export const auditProgramApi = {
  list: (projectId: string) =>
    http.get(`/api/audit-programs/projects/${projectId}/audit-programs`),
  create: (projectId: string, data: any) =>
    http.post(`/api/audit-programs/projects/${projectId}/audit-programs`, data),
  listProcedures: (projectId: string) =>
    http.get(`/api/audit-programs/projects/${projectId}/procedures`),
  createProcedure: (projectId: string, programId: string, data: any) =>
    http.post(`/api/audit-programs/projects/${projectId}/procedures`, data, { params: { program_id: programId } }),
  updateProcedureStatus: (projectId: string, procedureId: string, data: any) =>
    http.put(`/api/audit-programs/programs/${projectId}/procedures/${procedureId}`, data),
  linkWorkpaper: (projectId: string, procedureId: string, data: any) =>
    http.post(`/api/audit-programs/programs/${projectId}/procedures/${procedureId}/link-workpaper`, data),
  getCoverageReport: (programId: string) =>
    http.get(`/api/audit-programs/programs/${programId}/coverage-report`),
}

// Audit Finding
export const findingApi = {
  list: (projectId: string) =>
    http.get(`/api/findings/projects/${projectId}/findings`),
  create: (projectId: string, data: any) =>
    http.post(`/api/findings/projects/${projectId}/findings`, data),
  update: (findingId: string, data: any) =>
    http.put(`/api/findings/${findingId}`, data),
  linkToAdjustment: (findingId: string, adjustmentId: string) =>
    http.post(`/api/findings/${findingId}/link-adjustment`, { adjustment_id: adjustmentId }),
}

// Management Letter
export const managementLetterApi = {
  list: (projectId: string) =>
    http.get(`/api/management-letter/projects/${projectId}/management-letter-items`),
  create: (projectId: string, data: any) =>
    http.post(`/api/management-letter/projects/${projectId}/management-letter-items`, data),
  updateFollowUp: (itemId: string, data: any) =>
    http.put(`/api/management-letter/items/${itemId}/follow-up`, data),
  carryForward: (projectId: string, data: { source_project_id: string }) =>
    http.post(`/api/management-letter/projects/${projectId}/carry-forward`, data),
  get: (itemId: string) =>
    http.get(`/api/management-letter/items/${itemId}`),
}
