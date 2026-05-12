/**
 * 协作与质控 API 服务层
 */
import http from '@/utils/http'
import {
  auth, notifications, projects, users, reviews, sync, auditLogs,
  projectMgmt, archive, subsequentEvents, pbc, confirmations,
  goingConcern, riskAssessments, auditPrograms, findings,
  managementLetter,
} from './apiPaths'

// Auth
export const authApi = {
  login: (username: string, password: string) =>
    http.post(auth.login, { username, password }),
  refresh: (refresh_token: string) =>
    http.post(auth.refresh, { refresh_token }),
  logout: () => http.post(auth.logout),
  me: () => http.get(auth.me),
}

// Notifications
export const notificationApi = {
  list: (params?: { unread_only?: boolean; skip?: number; limit?: number }) =>
    http.get(notifications.list, { params }),
  unreadCount: () => http.get(notifications.unreadCount),
  markRead: (id: string) => http.post(notifications.read(id)),
  markAllRead: () => http.post(notifications.readAll),
  delete: (id: string) => http.delete(notifications.delete(id)),
}

// Projects & Users
export const projectApi = {
  list: () => http.get(projects.list),
  get: (id: string) => http.get(projects.detail(id)),
  create: (data: any) => http.post(projects.list, data),
  update: (id: string, data: any) => http.put(projects.detail(id), data),
  delete: (id: string) => http.delete(projects.detail(id)),
}

export const userApi = {
  list: (params?: any) => http.get(users.list, { params }),
  get: (id: string) => http.get(users.detail(id)),
  invite: (projectId: string, data: any) =>
    http.post(projects.assignments(projectId), data),
  remove: (projectId: string, userId: string) =>
    http.delete(`${projects.assignments(projectId)}/${userId}`),
  updateRole: (projectId: string, userId: string, data: any) =>
    http.patch(`${projects.assignments(projectId)}/${userId}`, data),
}

// Reviews
export const reviewApi = {
  create: (data: { workpaper_id: string; project_id: string; review_level: number }) =>
    http.post(reviews.create, data),
  list: (workpaperId: string) =>
    http.get(reviews.workpaper(workpaperId)),
  pending: (params?: any) =>
    http.get(reviews.pending, { params }),
  start: (reviewId: string) =>
    http.post(reviews.start(reviewId)),
  approve: (reviewId: string, data?: { comments?: string; reply_text?: string }) =>
    http.post(reviews.approve(reviewId), data),
  reject: (reviewId: string, data: { comments: string }) =>
    http.post(reviews.reject(reviewId), data),
}

// Sync
export const syncApi = {
  status: (projectId: string) =>
    http.get(sync.status(projectId)),
  lock: (projectId: string) =>
    http.post(sync.lock(projectId)),
  unlock: (projectId: string) =>
    http.post(sync.unlock(projectId)),
  sync: (projectId: string, syncType?: string) =>
    http.post(sync.sync(projectId), null, { params: { sync_type: syncType } }),
  detectConflict: (projectId: string, localData: any, serverData: any) =>
    http.post(sync.conflicts.detect(projectId), { local_data: localData, server_data: serverData }),
  resolveConflict: (projectId: string, data: any) =>
    http.post(sync.conflicts.resolve(projectId), data),
  conflictHistory: (projectId: string) =>
    http.get(sync.conflicts.history(projectId)),
}

// Audit logs
export const auditLogApi = {
  list: (params?: any) =>
    http.get(auditLogs.list, { params }),
}

// Project management
export const projectMgmtApi = {
  createMilestone: (projectId: string, data: any) =>
    http.post(projectMgmt.timeline(projectId), data),
  getTimeline: (projectId: string) =>
    http.get(projectMgmt.timeline(projectId)),
  completeMilestone: (projectId: string, timelineId: string) =>
    http.post(projectMgmt.timelineComplete(projectId, timelineId)),
  logWorkHours: (projectId: string, data: any) =>
    http.post(projectMgmt.workHours(projectId), data),
  getWorkHours: (projectId: string, params?: any) =>
    http.get(projectMgmt.workHours(projectId), { params }),
  setBudget: (projectId: string, data: any) =>
    http.post(projectMgmt.budgetHours(projectId), data),
  getBudget: (projectId: string) =>
    http.get(projectMgmt.budgetHours(projectId)),
}

// Archive
export const archiveApi = {
  initChecklist: (projectId: string) =>
    http.post(archive.checklist.init(projectId)),
  getChecklist: (projectId: string) =>
    http.get(archive.checklist.get(projectId)),
  completeItem: (projectId: string, itemId: string, notes?: string) =>
    http.post(archive.checklist.complete(projectId, itemId), null, { params: { notes } }),
  archive: (projectId: string) =>
    http.post(archive.orchestrate(projectId)),
  exportPdf: (projectId: string, data?: { password?: string }) =>
    http.post(archive.exportPdf(projectId), data),
  requestModification: (projectId: string, data: any) =>
    http.post(archive.modifications.request(projectId), data),
  approveModification: (projectId: string, modId: string, comments?: string) =>
    http.post(archive.modifications.approve(projectId, modId), null, { params: { comments } }),
  rejectModification: (projectId: string, modId: string, comments?: string) =>
    http.post(archive.modifications.reject(projectId, modId), null, { params: { comments } }),
}

// Subsequent Events
export const subsequentEventApi = {
  createEvent: (projectId: string, data: any) =>
    http.post(subsequentEvents.events(projectId), data),
  getEvents: (projectId: string) =>
    http.get(subsequentEvents.events(projectId)),
  initChecklist: (projectId: string) =>
    http.post(subsequentEvents.checklist.init(projectId)),
  getChecklist: (projectId: string) =>
    http.get(subsequentEvents.checklist.get(projectId)),
  completeChecklistItem: (projectId: string, itemId: string, notes?: string) =>
    http.post(subsequentEvents.checklist.complete(projectId, itemId), null, { params: { notes } }),
}

// PBC
export const pbcApi = {
  createItem: (projectId: string, data: any) =>
    http.post(pbc.items(projectId), data),
  getItems: (projectId: string) =>
    http.get(pbc.items(projectId)),
  updateStatus: (projectId: string, itemId: string, data: any) =>
    http.patch(pbc.itemStatus(projectId, itemId), null, { params: data }),
  pendingReminders: (projectId: string) =>
    http.get(pbc.pendingReminders(projectId)),
}

// Confirmations
export const confirmationApi = {
  create: (projectId: string, data: any) =>
    http.post(confirmations.list(projectId), data),
  list: (projectId: string) =>
    http.get(confirmations.list(projectId)),
  generateLetter: (projectId: string, confId: string, data: any) =>
    http.post(confirmations.letter(projectId, confId), data),
  recordResult: (projectId: string, confId: string, data: any) =>
    http.post(confirmations.result(projectId, confId), data),
  createSummary: (projectId: string, data: any) =>
    http.post(confirmations.summary(projectId), data),
}

// Going Concern
export const goingConcernApi = {
  init: (projectId: string) =>
    http.post(goingConcern.init(projectId)),
  createEvaluation: (projectId: string, data?: any) =>
    http.post(goingConcern.evaluation(projectId), data),
  getEvaluation: (projectId: string) =>
    http.get(goingConcern.evaluation(projectId)),
  updateEvaluation: (projectId: string, gcId: string, data: any) =>
    http.patch(goingConcern.evaluationDetail(projectId, gcId), data),
  getIndicators: (projectId: string, gcId: string) =>
    http.get(goingConcern.indicators(projectId, gcId)),
  updateIndicator: (projectId: string, gcId: string, indId: string, data: any) =>
    http.patch(goingConcern.indicatorDetail(projectId, gcId, indId), data),
}

// Risk Assessment
export const riskApi = {
  list: (projectId: string) =>
    http.get(riskAssessments.list(projectId)),
  create: (projectId: string, data: any) =>
    http.post(riskAssessments.list(projectId), data),
  updateResponse: (projectId: string, assessmentId: string, data: any) =>
    http.put(riskAssessments.response(projectId, assessmentId), data),
  verifyCoverage: (projectId: string, assessmentId: string) =>
    http.post(riskAssessments.verifyCoverage(projectId, assessmentId)),
  getRiskMatrix: (projectId: string) =>
    http.get(riskAssessments.riskMatrix(projectId)),
  getOverallRisk: (projectId: string) =>
    http.get(riskAssessments.overallRisk(projectId)),
}

// Audit Program
export const auditProgramApi = {
  list: (projectId: string) =>
    http.get(auditPrograms.list(projectId)),
  create: (projectId: string, data: any) =>
    http.post(auditPrograms.list(projectId), data),
  listProcedures: (projectId: string) =>
    http.get(auditPrograms.procedures(projectId)),
  createProcedure: (projectId: string, programId: string, data: any) =>
    http.post(auditPrograms.procedures(projectId), data, { params: { program_id: programId } }),
  updateProcedureStatus: (projectId: string, procedureId: string, data: any) =>
    http.put(auditPrograms.procedureStatus(projectId, procedureId), data),
  linkWorkpaper: (projectId: string, procedureId: string, data: any) =>
    http.post(auditPrograms.linkWorkpaper(projectId, procedureId), data),
  getCoverageReport: (programId: string) =>
    http.get(auditPrograms.coverageReport(programId)),
}

// Audit Finding
export const findingApi = {
  list: (projectId: string) =>
    http.get(findings.list(projectId)),
  create: (projectId: string, data: any) =>
    http.post(findings.list(projectId), data),
  update: (findingId: string, data: any) =>
    http.put(findings.detail(findingId), data),
  linkToAdjustment: (findingId: string, adjustmentId: string) =>
    http.post(findings.linkAdjustment(findingId), { adjustment_id: adjustmentId }),
}

// Management Letter
export const managementLetterApi = {
  list: (projectId: string) =>
    http.get(managementLetter.list(projectId)),
  create: (projectId: string, data: any) =>
    http.post(managementLetter.list(projectId), data),
  updateFollowUp: (itemId: string, data: any) =>
    http.put(managementLetter.followUp(itemId), data),
  carryForward: (projectId: string, data: { source_project_id: string }) =>
    http.post(managementLetter.carryForward(projectId), data),
  get: (itemId: string) =>
    http.get(managementLetter.detail(itemId)),
}
