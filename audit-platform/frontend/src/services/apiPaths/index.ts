/**
 * API 路径集中管理 — 按业务域拆分后的统一入口
 *
 * 所有子模块按域分组，此文件统一 re-export 并组装 API 聚合对象。
 */

export { projects, projectMgmt, projectConfig, projectIssues } from './project'

export {
  trialBalance, adjustments, materiality, misstatements,
  sampling, aging, ledger, accountChart, accountMapping,
  reportLineMapping, columnMappings, dataLifecycle, importIntelligence,
  ledgerImportValidationRules, tAccounts, formula, dataValidation, fineChecks,
} from './accounting'

export {
  reports, reportConfig, reportMapping, noteTemplates, consolNoteSections,
  cfsWorksheet, disclosureNotes, auditReport, exportTask, reportFormatTemplates,
  reportReview, noteLocks, noteGroupTemplate, noteCustomSections,
  consolidation, consolWorksheetData,
} from './report'

export {
  workpapers, wpReviews, wpMapping, wpAI, wpFineRules, wpManuals,
  wpDependencies, workpaperSummary, templates, procedures, reviews,
  templateLibrary, templateLibraryMgmt, customTemplates, sharedConfig,
  excelHtml, jobs,
} from './workpaper'

export {
  staff, workHours, notifications, pbc, confirmations,
  annotations, reviewConversations, forum, events, presence,
  sync, independenceDeclarations, my,
} from './collaboration'

export {
  auth, users, system, recycleBin, knowledge, knowledgeLibrary,
  dashboard, auditLogs, ai, aiModels, aiProject, admin,
  aiPlugins, gtCoding, regulatory, processRecord, attachments,
  partner, qcDashboard, qcRules, qcInspections, qcCases,
  qcAnnualReports, qcAuditLogCompliance, qcArchiveReadiness,
  governance, eqcr, signatures, rotation, archive, subsequentEvents,
  goingConcern, riskAssessments, auditPrograms, findings, managementLetter,
  linkage, linkageBus, conflictGuard, chainWorkflow, dataLock,
  addressRegistry, customQuery, systemDicts, adminLogs,
} from './system'

// ─── 聚合导出（便于 import { API } from '@/services/apiPaths'） ─────────────

import {
  projects, projectMgmt, projectConfig, projectIssues,
} from './project'
import {
  trialBalance, adjustments, materiality, misstatements,
  sampling, aging, ledger, accountChart, accountMapping,
  reportLineMapping, columnMappings, dataLifecycle, importIntelligence,
  ledgerImportValidationRules, tAccounts, formula, dataValidation, fineChecks,
} from './accounting'
import {
  reports, reportConfig, reportMapping, noteTemplates, consolNoteSections,
  cfsWorksheet, disclosureNotes, auditReport, exportTask, reportFormatTemplates,
  reportReview, noteLocks, noteGroupTemplate, noteCustomSections,
  consolidation, consolWorksheetData,
} from './report'
import {
  workpapers, wpReviews, wpMapping, wpAI, wpFineRules, wpManuals,
  wpDependencies, workpaperSummary, templates, procedures, reviews,
  templateLibrary, templateLibraryMgmt, customTemplates, sharedConfig,
  excelHtml, jobs,
} from './workpaper'
import {
  staff, workHours, notifications, pbc, confirmations,
  annotations, reviewConversations, forum, events, presence,
  sync, independenceDeclarations, my,
} from './collaboration'
import {
  auth, users, system, recycleBin, knowledge, knowledgeLibrary,
  dashboard, auditLogs, ai, aiModels, aiProject, admin,
  aiPlugins, gtCoding, regulatory, processRecord, attachments,
  partner, qcDashboard, qcRules, qcInspections, qcCases,
  qcAnnualReports, qcAuditLogCompliance, qcArchiveReadiness,
  governance, eqcr, signatures, rotation, archive, subsequentEvents,
  goingConcern, riskAssessments, auditPrograms, findings, managementLetter,
  linkage, linkageBus, conflictGuard, chainWorkflow, dataLock,
  addressRegistry, customQuery, systemDicts, adminLogs,
} from './system'

export const API = {
  projects, trialBalance, adjustments, materiality, misstatements,
  reports, reportConfig, reportMapping, noteTemplates, consolNoteSections,
  cfsWorksheet, disclosureNotes, auditReport, exportTask,
  workpaperSummary, events, consolidation, consolWorksheetData,
  workpapers, wpReviews, wpMapping, wpAI, wpFineRules, wpManuals,
  wpDependencies, templates, formula, sampling, staff, users, auth,
  notifications, system, recycleBin, knowledge, knowledgeLibrary, dashboard, annotations,
  procedures, reviews, sync, auditLogs, projectMgmt, archive,
  subsequentEvents, pbc, confirmations, goingConcern, riskAssessments,
  auditPrograms, findings, managementLetter, reviewConversations,
  forum, reportReview, ai, aiModels, aiProject, processRecord,
  attachments, ledger, tAccounts, sharedConfig, customTemplates,
  templateLibrary, reportFormatTemplates, excelHtml, importIntelligence,
  addressRegistry, workHours, aging, regulatory, aiPlugins, gtCoding,
  dataValidation, fineChecks, projectIssues, ledgerImportValidationRules,
  accountChart, accountMapping, reportLineMapping, columnMappings, dataLifecycle, independenceDeclarations,
  admin, my, partner, qcDashboard, qcRules, qcInspections, qcCases,
  qcAnnualReports, qcAuditLogCompliance, qcArchiveReadiness,
  jobs, governance, eqcr, signatures, rotation,
  presence, linkage, linkageBus, conflictGuard, chainWorkflow, projectConfig,
  noteLocks, dataLock, noteGroupTemplate, noteCustomSections,
  templateLibraryMgmt,
  customQuery, systemDicts, adminLogs,
} as const

export default API
