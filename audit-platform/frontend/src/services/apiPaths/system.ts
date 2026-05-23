/**
 * API 路径 — 认证、用户、系统设置、健康检查、知识库、AI、管理、治理
 */

// ─── 认证 ───────────────────────────────────────────────────────────────────

export const auth = {
  login: '/api/auth/login',
  refresh: '/api/auth/refresh',
  logout: '/api/auth/logout',
  me: '/api/auth/me',
  register: '/api/auth/register',
} as const

// ─── 用户 ───────────────────────────────────────────────────────────────────

export const users = {
  list: '/api/users',
  me: '/api/users/me',
  detail: (id: string) => `/api/users/${id}`,
  privateStorage: {
    list: (uid: string) => `/api/users/${uid}/private-storage`,
    quota: (uid: string) => `/api/users/${uid}/private-storage/quota`,
    upload: (uid: string) => `/api/users/${uid}/private-storage/upload`,
    download: (uid: string, name: string) => `/api/users/${uid}/private-storage/${name}/download`,
    delete: (uid: string, name: string) => `/api/users/${uid}/private-storage/${name}`,
  },
} as const

// ─── 系统设置 ───────────────────────────────────────────────────────────────

export const system = {
  settings: '/api/settings',
  health: '/api/settings/health',
  featureFlags: {
    check: (flag: string) => `/api/feature-flags/check/${flag}`,
    maturity: '/api/feature-flags/maturity',
  },
} as const

// ─── 回收站 ─────────────────────────────────────────────────────────────────

export const recycleBin = {
  list: '/api/recycle-bin',
  stats: '/api/recycle-bin/stats',
  restore: (id: string) => `/api/recycle-bin/${id}/restore`,
  delete: (id: string) => `/api/recycle-bin/${id}`,
  empty: '/api/recycle-bin/empty',
} as const

// ─── 知识库 ─────────────────────────────────────────────────────────────────

export const knowledge = {
  category: (cat: string) => `/api/knowledge/${cat}`,
  upload: (cat: string) => `/api/knowledge/${cat}/upload`,
  doc: (cat: string, docId: string) => `/api/knowledge/${cat}/${docId}`,
  search: '/api/knowledge/search',
  libraries: '/api/knowledge/libraries',
} as const

// ─── 知识库文件管理 ─────────────────────────────────────────────────────────

export const knowledgeLibrary = {
  tree: '/api/knowledge-library/tree',
  search: '/api/knowledge-library/search',
  folders: '/api/knowledge-library/folders',
  folderDocuments: (folderId: string) => `/api/knowledge-library/folders/${folderId}/documents`,
  folderUpload: (folderId: string) => `/api/knowledge-library/folders/${folderId}/upload`,
  folderRename: (folderId: string) => `/api/knowledge-library/folders/${folderId}/rename`,
  folderDelete: (folderId: string) => `/api/knowledge-library/folders/${folderId}`,
  documentDetail: (docId: string) => `/api/knowledge-library/documents/${docId}`,
  documentDownload: (docId: string) => `/api/knowledge-library/documents/${docId}/download`,
  documentPreview: (docId: string) => `/api/knowledge-library/documents/${docId}/preview`,
  documentMove: (docId: string) => `/api/knowledge-library/documents/${docId}/move`,
} as const

// ─── 看板 ───────────────────────────────────────────────────────────────────

export const dashboard = {
  overview: '/api/dashboard/overview',
  projectProgress: '/api/dashboard/project-progress',
  staffWorkload: '/api/dashboard/staff-workload',
  riskAlerts: '/api/dashboard/risk-alerts',
  groupProgress: '/api/dashboard/group-progress',
  hoursHeatmap: '/api/dashboard/hours-heatmap',
  projectStaffHours: '/api/dashboard/project-staff-hours',
  staffDetail: '/api/dashboard/staff-detail',
  availableStaff: '/api/dashboard/available-staff',
  statsTrend: '/api/dashboard/stats/trend',
  statsCompare: '/api/dashboard/stats/compare',
  manager: {
    overview: '/api/dashboard/manager/overview',
    assignmentStatus: '/api/dashboard/manager/assignment-status',
    projectsOverview: '/api/dashboard/manager/projects-overview',
  },
} as const

// ─── 审计日志 ───────────────────────────────────────────────────────────────

export const auditLogs = {
  list: '/api/audit-logs',
} as const

// ─── AI ─────────────────────────────────────────────────────────────────────

export const ai = {
  health: '/api/ai/health',
  models: {
    list: '/api/ai/models',
    activate: (id: string) => `/api/ai/models/${id}/activate`,
  },
  evaluate: '/api/ai/evaluate',
  analyticalReview: '/api/ai/analytical-review',
  noteDraft: '/api/ai/note-draft',
  workpaperReview: '/api/ai/workpaper-review',
  ocr: {
    batchUpload: '/api/ai/ocr/batch-upload',
    taskStatus: (taskId: string) => `/api/ai/ocr/task/${taskId}`,
  },
  chat: {
    message: '/api/ai/chat/message',
    messageStream: '/api/ai/chat/message/stream',
    sessions: '/api/ai/chat/sessions',
    deleteSession: (id: string) => `/api/ai/chat/sessions/${id}`,
    fileAnalysis: '/api/ai/chat/file-analysis',
    folderAnalysis: '/api/ai/chat/folder-analysis',
    knowledge: {
      search: '/api/ai/chat/knowledge/search',
      list: '/api/ai/chat/knowledge',
      delete: (id: string) => `/api/ai/chat/knowledge/${id}`,
    },
  },
  nl: {
    parse: '/api/ai/nl/parse',
    execute: '/api/ai/nl/execute',
    analyzeFile: '/api/ai/nl/analyze-file',
    analyzeFolder: '/api/ai/nl/analyze-folder',
    analyzeFolderStatus: (taskId: string) => `/api/ai/nl/analyze-folder/${taskId}`,
    comparePbc: '/api/ai/nl/compare-pbc',
  },
} as const

// ─── AI 模型配置 ────────────────────────────────────────────────────────────

export const aiModels = {
  list: '/api/ai-models',
  detail: (id: string) => `/api/ai-models/${id}`,
  activate: (id: string) => `/api/ai-models/${id}/activate`,
  health: '/api/ai-models/health',
  seed: '/api/ai-models/seed',
} as const

// ─── AI 项目级 ──────────────────────────────────────────────────────────────

export const aiProject = {
  documents: {
    upload: (pid: string) => `/api/projects/${pid}/documents/upload`,
    list: (pid: string) => `/api/projects/${pid}/documents`,
    extracted: (pid: string, docId: string) => `/api/projects/${pid}/documents/${docId}/extracted`,
    extractedField: (pid: string, docId: string, fieldId: string) =>
      `/api/projects/${pid}/documents/${docId}/extracted/${fieldId}`,
    match: (pid: string, docId: string) => `/api/projects/${pid}/documents/${docId}/match`,
  },
  contracts: {
    upload: (pid: string) => `/api/projects/${pid}/contracts/upload`,
    list: (pid: string) => `/api/projects/${pid}/contracts`,
    analyze: (pid: string, cId: string) => `/api/projects/${pid}/contracts/${cId}/analyze`,
    crossReference: (pid: string, cId: string) => `/api/projects/${pid}/contracts/${cId}/cross-reference`,
    summary: (pid: string) => `/api/projects/${pid}/contracts/summary`,
    batchUpload: '/api/projects/upload-contracts/batch',
    extracted: (cId: string) => `/api/projects/contracts/${cId}/extracted`,
    confirmClause: (cId: string, clauseId: string) => `/api/projects/contracts/${cId}/extracted/${clauseId}/confirm`,
    linkWorkpaper: (cId: string) => `/api/projects/contracts/${cId}/link-workpaper`,
    links: (cId: string) => `/api/projects/contracts/${cId}/links`,
    unlinkWorkpaper: (linkId: string) => `/api/projects/contracts/links/${linkId}`,
    taskStatus: (taskId: string) => `/api/projects/contracts/task/${taskId}`,
  },
  evidenceChain: {
    verify: (pid: string, chainType: string) => `/api/projects/${pid}/evidence-chain/${chainType}`,
    bankAnalysis: (pid: string) => `/api/projects/${pid}/evidence-chain/bank-analysis`,
    get: (pid: string) => `/api/projects/${pid}/evidence-chain`,
    summary: (pid: string, chainType: string) => `/api/projects/${pid}/evidence-chain/summary/${chainType}`,
  },
  aiContent: {
    list: (pid: string) => `/api/projects/${pid}/ai-content`,
    confirm: (pid: string, contentId: string) => `/api/projects/${pid}/ai-content/${contentId}/confirm`,
    summary: (pid: string) => `/api/projects/${pid}/ai-content/summary`,
    pendingCount: (pid: string) => `/api/projects/${pid}/ai-content/pending-count`,
  },
  confirmationAI: {
    addressVerify: (pid: string) => `/api/projects/${pid}/confirmations/ai/address-verify`,
    ocrReply: (pid: string, confId: string) => `/api/projects/${pid}/confirmations/${confId}/ai/ocr-reply`,
    mismatchAnalysis: (pid: string) => `/api/projects/${pid}/confirmations/ai/mismatch-analysis`,
    checks: (pid: string) => `/api/projects/${pid}/confirmations/ai/checks`,
    confirmCheck: (pid: string, checkId: string) => `/api/projects/${pid}/confirmations/ai/checks/${checkId}/confirm`,
    run: (pid: string, confId: string) => `/api/projects/${pid}/confirmations/${confId}/ai/run`,
    confirmAddress: (pid: string, addressId: string) => `/api/projects/${pid}/confirmations/ai/address/${addressId}/confirm`,
  },
  chatHistory: (pid: string) => `/api/projects/${pid}/chat/history`,
  knowledgeIndex: {
    build: (pid: string) => `/api/projects/${pid}/knowledge/index/build`,
    status: (pid: string) => `/api/projects/${pid}/knowledge/index/status`,
  },
} as const

// ─── 性能监控 ───────────────────────────────────────────────────────────────

export const admin = {
  performanceStats: '/api/admin/performance-stats',
  slowQueries: '/api/admin/slow-queries',
  performanceMetrics: '/api/admin/performance-metrics',
  importEventHealth: '/api/admin/import-event-health',
  importEventReplay: '/api/admin/import-event-replay',
  llmMetrics: '/api/admin/llm-metrics',
} as const

// ─── 其他 ───────────────────────────────────────────────────────────────────

export const aiPlugins = { list: '/api/ai-plugins' } as const
export const gtCoding = { list: '/api/gt-coding' } as const

// ─── 监管备案 ───────────────────────────────────────────────────────────────

export const regulatory = {
  filings: '/api/regulatory/filings',
  retry: (id: string) => `/api/regulatory/filings/${id}/retry`,
  archivalStandard: '/api/regulatory/archival-standard',
  cicpaReport: '/api/regulatory/cicpa-report',
} as const

// ─── 过程记录 ───────────────────────────────────────────────────────────────

export const processRecord = {
  editHistory: (pid: string, wpId: string) => `/api/process-record/projects/${pid}/workpapers/${wpId}/edit-history`,
  attachments: (pid: string, wpId: string) => `/api/process-record/projects/${pid}/workpapers/${wpId}/attachments`,
  attachmentWorkpapers: (attachmentId: string) => `/api/process-record/attachments/${attachmentId}/workpapers`,
  linkAttachment: '/api/process-record/link-attachment',
  pendingAIContent: (pid: string) => `/api/process-record/projects/${pid}/ai-content/pending`,
  confirmAIContent: (contentId: string) => `/api/process-record/ai-content/${contentId}/confirm`,
  aiCheck: (pid: string, wpId: string) => `/api/process-record/projects/${pid}/workpapers/${wpId}/ai-check`,
} as const

// ─── 附件 ───────────────────────────────────────────────────────────────────

export const attachments = {
  list: (pid: string) => `/api/projects/${pid}/attachments`,
  search: '/api/attachments/search',
  upload: (pid: string) => `/api/projects/${pid}/attachments/upload`,
  classify: (pid: string) => `/api/projects/${pid}/attachments/classify`,
  preview: (id: string) => `/api/attachments/${id}/preview`,
  /** Office 文件高保真预览：后端 LibreOffice 转 PDF（503 时前端降级到下载提示） */
  previewPdf: (id: string) => `/api/attachments/${id}/preview-pdf`,
  download: (id: string) => `/api/attachments/${id}/download`,
  associate: (id: string) => `/api/attachments/${id}/associate`,
  ocrStatus: (id: string) => `/api/attachments/${id}/ocr-status`,
} as const

/** Office 在线预览健康探测（决定是否展示 iframe） */
export const officePreview = {
  health: '/api/office-preview/health',
} as const

// ─── 合伙人 ─────────────────────────────────────────────────────────────────

export const partner = {
  overview: '/api/partner/overview',
  teamEfficiency: '/api/partner/team-efficiency',
  workpaperReadiness: (pid: string) => `/api/projects/${pid}/partner/workpaper-readiness`,
  dashboardSummary: (pid: string) => `/api/projects/${pid}/dashboard/summary`,
} as const

// ─── 质控看板 ───────────────────────────────────────────────────────────────

export const qcDashboard = {
  overview: (pid: string) => `/api/projects/${pid}/qc-dashboard/overview`,
  staffProgress: (pid: string) => `/api/projects/${pid}/qc-dashboard/staff-progress`,
  projectRating: (pid: string, year: number) => `/api/qc/projects/${pid}/rating/${year}`,
  openIssues: (pid: string) => `/api/projects/${pid}/qc-dashboard/open-issues`,
  archiveReadiness: (pid: string) => `/api/projects/${pid}/qc-dashboard/archive-readiness`,
  reviewerMetrics: '/api/qc/reviewer-metrics',
  clientQualityTrend: (clientName: string) => `/api/qc/clients/${encodeURIComponent(clientName)}/quality-trend`,
} as const

// ─── 质控规则管理 ───────────────────────────────────────────────────────────

export const qcRules = {
  list: '/api/qc/rules',
  detail: (ruleId: string) => `/api/qc/rules/${ruleId}`,
  dryRun: (ruleId: string) => `/api/qc/rules/${ruleId}/dry-run`,
  versions: (ruleId: string) => `/api/qc/rules/${ruleId}/versions`,
} as const

// ─── 质控抽查 ───────────────────────────────────────────────────────────────

export const qcInspections = {
  list: '/api/qc/inspections',
  detail: (id: string) => `/api/qc/inspections/${id}`,
  verdict: (inspId: string, itemId: string) => `/api/qc/inspections/${inspId}/items/${itemId}/verdict`,
  report: (inspId: string) => `/api/qc/inspections/${inspId}/report`,
  publishAsCase: (inspId: string, itemId: string) => `/api/qc/inspections/${inspId}/items/${itemId}/publish-as-case`,
} as const

// ─── 质控案例库 ─────────────────────────────────────────────────────────────

export const qcCases = {
  list: '/api/qc/cases',
  detail: (caseId: string) => `/api/qc/cases/${caseId}`,
} as const

// ─── 质控年报 ───────────────────────────────────────────────────────────────

export const qcAnnualReports = {
  list: '/api/qc/annual-reports',
  generate: '/api/qc/annual-reports',
  download: (reportId: string) => `/api/qc/annual-reports/${reportId}/download`,
} as const

// ─── 质控日志合规 ───────────────────────────────────────────────────────────

export const qcAuditLogCompliance = {
  findings: '/api/qc/audit-log-compliance/findings',
  run: '/api/qc/audit-log-compliance/run',
  findingStatus: (findingId: string) => `/api/qc/audit-log-compliance/findings/${findingId}/status`,
  summary: '/api/qc/audit-log-compliance/summary',
} as const

// ─── 归档就绪 ───────────────────────────────────────────────────────────────

export const qcArchiveReadiness = {
  check: '/api/qc/archive-readiness',
} as const

// ─── 门禁引擎 + 任务树 + 取证版本链 ────────────────────────────────────────

export const governance = {
  gate: { evaluate: '/api/gate/evaluate' },
  sod: { check: '/api/sod/check' },
  trace: {
    replay: (traceId: string) => `/api/trace/${traceId}/replay`,
    query: '/api/trace',
  },
  taskTree: {
    list: '/api/task-tree',
    stats: '/api/task-tree/stats',
    status: (nodeId: string) => `/api/task-tree/${nodeId}/status`,
    reassign: '/api/task-tree/reassign',
  },
  taskEvents: {
    list: '/api/task-events',
    replay: '/api/task-events/replay',
  },
  issues: {
    list: '/api/issues',
    fromConversation: '/api/issues/from-conversation',
    status: (issueId: string) => `/api/issues/${issueId}/status`,
    escalate: (issueId: string) => `/api/issues/${issueId}/escalate`,
  },
  versionLine: (pid: string) => `/api/version-line/${pid}`,
  exportIntegrity: (exportId: string) => `/api/exports/${exportId}/integrity`,
  offline: {
    detectConflicts: '/api/offline/conflicts/detect',
    resolveConflict: '/api/offline/conflicts/resolve',
    listConflicts: '/api/offline/conflicts',
  },
  consistency: {
    replay: '/api/consistency/replay',
    report: (pid: string) => `/api/consistency/report/${pid}`,
  },
} as const

// ─── EQCR 独立复核（Round 5） ───────────────────────────────────────────────

export const eqcr = {
  projects: '/api/eqcr/projects',
  projectOverview: (pid: string) => `/api/eqcr/projects/${pid}/overview`,
  materiality: (pid: string) => `/api/eqcr/projects/${pid}/materiality`,
  estimates: (pid: string) => `/api/eqcr/projects/${pid}/estimates`,
  relatedParties: (pid: string) => `/api/eqcr/projects/${pid}/related-parties`,
  goingConcern: (pid: string) => `/api/eqcr/projects/${pid}/going-concern`,
  opinionType: (pid: string) => `/api/eqcr/projects/${pid}/opinion-type`,
  opinions: '/api/eqcr/opinions',
  opinionDetail: (opinionId: string) => `/api/eqcr/opinions/${opinionId}`,
  relatedPartyDetail: (pid: string, partyId: string) =>
    `/api/eqcr/projects/${pid}/related-parties/${partyId}`,
  relatedPartyTransactions: (pid: string) =>
    `/api/eqcr/projects/${pid}/related-party-transactions`,
  relatedPartyTransactionDetail: (pid: string, txnId: string) =>
    `/api/eqcr/projects/${pid}/related-party-transactions/${txnId}`,
  shadowCompute: '/api/eqcr/shadow-compute',
  shadowComputations: (pid: string) => `/api/eqcr/projects/${pid}/shadow-computations`,
  notes: (pid: string) => `/api/eqcr/projects/${pid}/notes`,
  noteDetail: (pid: string, noteId: string) => `/api/eqcr/projects/${pid}/notes/${noteId}`,
  noteShare: (noteId: string) => `/api/eqcr/notes/${noteId}/share-to-team`,
  memoPreview: (pid: string) => `/api/eqcr/projects/${pid}/memo/preview`,
  memoGenerate: (pid: string) => `/api/eqcr/projects/${pid}/memo`,
  memoSave: (pid: string) => `/api/eqcr/projects/${pid}/memo`,
  memoFinalize: (pid: string) => `/api/eqcr/projects/${pid}/memo/finalize`,
  memoExport: (pid: string, format = 'docx') => `/api/eqcr/projects/${pid}/memo/export?format=${format}`,
  memoVersions: (pid: string) => `/api/eqcr/projects/${pid}/memo/versions`,
  timeSummary: (pid: string) => `/api/eqcr/projects/${pid}/time-summary`,
  approve: (pid: string) => `/api/eqcr/projects/${pid}/approve`,
  unlockOpinion: (pid: string) => `/api/eqcr/projects/${pid}/unlock-opinion`,
  independence: {
    check: '/api/eqcr/independence/annual/check',
    questions: '/api/eqcr/independence/annual/questions',
    submit: '/api/eqcr/independence/annual/submit',
  },
  componentAuditors: (pid: string) => `/api/eqcr/projects/${pid}/component-auditors`,
  priorYearComparison: (pid: string) => `/api/eqcr/projects/${pid}/prior-year-comparison`,
  linkPriorYear: (pid: string) => `/api/eqcr/projects/${pid}/link-prior-year`,
  metrics: '/api/eqcr/metrics',
  snapshot: (pid: string) => `/api/projects/${pid}/eqcr/snapshot`,
  snapshotRefresh: (pid: string) => `/api/projects/${pid}/eqcr/snapshot/refresh`,
} as const

// ─── 签字流水线 ─────────────────────────────────────────────────────────────

export const signatures = {
  sign: '/api/signatures/sign',
  workflow: (pid: string) => `/api/projects/${pid}/signature-workflow`,
  list: (objectType: string, objectId: string) => `/api/signatures/${objectType}/${objectId}`,
  verify: (sigId: string) => `/api/signatures/${sigId}/verify`,
  revoke: (sigId: string) => `/api/signatures/${sigId}/revoke`,
} as const

// ─── 合伙人轮换检查 ────────────────────────────────────────────────────────

export const rotation = {
  check: '/api/rotation/check',
  overrides: '/api/rotation/overrides',
} as const

// ─── 归档 ───────────────────────────────────────────────────────────────────

export const archive = {
  checklist: {
    init: (pid: string) => `/api/projects/${pid}/archive/checklist/init`,
    get: (pid: string) => `/api/projects/${pid}/archive/checklist`,
    complete: (pid: string, itemId: string) => `/api/projects/${pid}/archive/checklist/${itemId}/complete`,
  },
  orchestrate: (pid: string) => `/api/projects/${pid}/archive/orchestrate`,
  job: (pid: string, jobId: string) => `/api/projects/${pid}/archive/jobs/${jobId}`,
  retry: (pid: string, jobId: string) => `/api/projects/${pid}/archive/jobs/${jobId}/retry`,
  exportPdf: (pid: string) => `/api/projects/${pid}/archive/export-pdf`,
  modifications: {
    request: (pid: string) => `/api/projects/${pid}/archive/modifications`,
    approve: (pid: string, modId: string) => `/api/projects/${pid}/archive/modifications/${modId}/approve`,
    reject: (pid: string, modId: string) => `/api/projects/${pid}/archive/modifications/${modId}/reject`,
  },
} as const

// ─── 期后事项 ───────────────────────────────────────────────────────────────

export const subsequentEvents = {
  events: (pid: string) => `/api/subsequent-events/${pid}/events`,
  checklist: {
    init: (pid: string) => `/api/subsequent-events/${pid}/checklist/init`,
    get: (pid: string) => `/api/subsequent-events/${pid}/checklist`,
    complete: (pid: string, itemId: string) => `/api/subsequent-events/${pid}/checklist/${itemId}/complete`,
  },
} as const

// ─── 持续经营 ───────────────────────────────────────────────────────────────

export const goingConcern = {
  init: (pid: string) => `/api/going-concern/${pid}/init`,
  evaluation: (pid: string) => `/api/going-concern/${pid}/evaluation`,
  evaluationDetail: (pid: string, gcId: string) => `/api/going-concern/${pid}/evaluation/${gcId}`,
  indicators: (pid: string, gcId: string) => `/api/going-concern/${pid}/evaluation/${gcId}/indicators`,
  indicatorDetail: (pid: string, gcId: string, indId: string) =>
    `/api/going-concern/${pid}/evaluation/${gcId}/indicators/${indId}`,
} as const

// ─── 风险评估 ───────────────────────────────────────────────────────────────

export const riskAssessments = {
  list: (pid: string) => `/api/risk-assessments/projects/${pid}/risk-assessments`,
  detail: (pid: string, aId: string) => `/api/risk-assessments/projects/${pid}/risk-assessments/${aId}`,
  response: (pid: string, aId: string) => `/api/risk-assessments/projects/${pid}/risk-assessments/${aId}/response`,
  verifyCoverage: (pid: string, aId: string) => `/api/risk-assessments/projects/${pid}/risk-assessments/${aId}/verify-coverage`,
  riskMatrix: (pid: string) => `/api/risk-assessments/projects/${pid}/risk-matrix`,
  overallRisk: (pid: string) => `/api/risk-assessments/projects/${pid}/overall-risk`,
} as const

// ─── 审计方案 ───────────────────────────────────────────────────────────────

export const auditPrograms = {
  list: (pid: string) => `/api/audit-programs/projects/${pid}/audit-programs`,
  procedures: (pid: string) => `/api/audit-programs/projects/${pid}/procedures`,
  procedureStatus: (pid: string, procId: string) => `/api/audit-programs/programs/${pid}/procedures/${procId}`,
  linkWorkpaper: (pid: string, procId: string) => `/api/audit-programs/programs/${pid}/procedures/${procId}/link-workpaper`,
  coverageReport: (programId: string) => `/api/audit-programs/programs/${programId}/coverage-report`,
} as const

// ─── 审计发现 ───────────────────────────────────────────────────────────────

export const findings = {
  list: (pid: string) => `/api/findings/projects/${pid}/findings`,
  detail: (id: string) => `/api/findings/${id}`,
  linkAdjustment: (id: string) => `/api/findings/${id}/link-adjustment`,
} as const

// ─── 管理建议书 ─────────────────────────────────────────────────────────────

export const managementLetter = {
  list: (pid: string) => `/api/management-letter/projects/${pid}/management-letter-items`,
  detail: (itemId: string) => `/api/management-letter/items/${itemId}`,
  followUp: (itemId: string) => `/api/management-letter/items/${itemId}/follow-up`,
  carryForward: (pid: string) => `/api/management-letter/projects/${pid}/carry-forward`,
} as const

// ─── Linkage（联动指示器 + 影响预判） ────────────────────────────────────────

export const linkage = {
  tbRowAdjustments: (pid: string, rowCode: string) => `/api/projects/${pid}/linkage/tb-row/${encodeURIComponent(rowCode)}/adjustments`,
  tbRowWorkpapers: (pid: string, rowCode: string) => `/api/projects/${pid}/linkage/tb-row/${encodeURIComponent(rowCode)}/workpapers`,
  impactPreview: (pid: string) => `/api/projects/${pid}/linkage/impact-preview`,
  changeHistory: (pid: string, rowCode: string) => `/api/projects/${pid}/linkage/change-history/${encodeURIComponent(rowCode)}`,
} as const

// ─── Linkage Bus ────────────────────────────────────────────────────────────

export const linkageBus = {
  graph: '/api/linkage-bus/graph',
  resolve: '/api/linkage-bus/resolve',
  impact: '/api/linkage-bus/impact',
  override: '/api/linkage-bus/override',
  headerRule: '/api/linkage-bus/header-rule',
  auditLog: '/api/linkage-bus/audit-log',
  health: '/api/linkage-bus/health',
  formulaUsage: '/api/linkage-bus/formula-usage',
  formulasFor: '/api/linkage-bus/formulas-for',
  cellDetail: '/api/linkage-bus/cell-detail',
} as const

// ─── Conflict Guard ─────────────────────────────────────────────────────────

export const conflictGuard = {
  lock: (pid: string, entryGroupId: string) => `/api/projects/${pid}/adjustments/${entryGroupId}/lock`,
  heartbeat: (pid: string, entryGroupId: string) => `/api/projects/${pid}/adjustments/${entryGroupId}/lock/heartbeat`,
  unlock: (pid: string, entryGroupId: string) => `/api/projects/${pid}/adjustments/${entryGroupId}/lock`,
} as const

// ─── 全链路工作流 ───────────────────────────────────────────────────────────

export const chainWorkflow = {
  executeFullChain: (pid: string) => `/api/projects/${pid}/workflow/execute-full-chain`,
  progress: (pid: string, executionId: string) => `/api/projects/${pid}/workflow/progress/${executionId}`,
  executions: (pid: string) => `/api/projects/${pid}/workflow/executions`,
  retry: (pid: string, executionId: string) => `/api/projects/${pid}/workflow/retry/${executionId}`,
  consistencyCheck: (pid: string) => `/api/projects/${pid}/workflow/consistency-check`,
  compare: (pid: string, executionId: string) => `/api/projects/${pid}/workflow/compare/${executionId}`,
  dataHealth: (pid: string) => `/api/projects/${pid}/workflow/data-health`,
  notesSyncFromReport: (pid: string) => `/api/projects/${pid}/workflow/notes/sync-from-report`,
  notesTrimAndSort: (pid: string) => `/api/projects/${pid}/workflow/notes/trim-and-sort`,
  batchExecute: '/api/workflow/batch-execute',
} as const

// ─── 数据锁定与快照 ─────────────────────────────────────────────────────────

export const dataLock = {
  lock: (pid: string) => `/api/projects/${pid}/data-lock/lock`,
  unlock: (pid: string) => `/api/projects/${pid}/data-lock/unlock`,
  snapshot: (pid: string) => `/api/projects/${pid}/data-lock/snapshot`,
  snapshots: (pid: string) => `/api/projects/${pid}/data-lock/snapshots`,
  status: (pid: string) => `/api/projects/${pid}/data-lock/status`,
} as const

// ─── 地址坐标注册表 ─────────────────────────────────────────────────────────

export const addressRegistry = {
  search: '/api/address-registry',
  stats: '/api/address-registry/stats',
  resolve: '/api/address-registry/resolve',
  validate: '/api/address-registry/validate',
  jump: '/api/address-registry/jump',
  invalidate: '/api/address-registry/invalidate',
  v2: {
    stats: '/api/address-registry/v2/stats',
    resolve: '/api/address-registry/v2/resolve',
    anchors: '/api/address-registry/v2/anchors',
    staleImpact: '/api/address-registry/v2/stale-impact',
    dependencies: '/api/address-registry/v2/dependencies',
    notifyCellChange: '/api/address-registry/v2/notify-cell-change',
  },
} as const

// ─── 自定义查询 ─────────────────────────────────────────────────────────────

export const customQuery = {
  indicators: '/api/custom-query/indicators',
  execute: '/api/custom-query/execute',
  templates: '/api/custom-query/templates',
  templateDetail: (id: string) => `/api/custom-query/templates/${id}`,
} as const

// ─── 系统枚举字典 ───────────────────────────────────────────────────────────

export const systemDicts = {
  list: '/api/system/dicts',
  usageCount: (key: string) => `/api/system/dicts/${key}/usage-count`,
  items: (key: string) => `/api/system/dicts/${key}/items`,
  itemDetail: (key: string, value: string) => `/api/system/dicts/${key}/items/${value}`,
} as const
// ─── MT-8 日志集中查看（admin only） ────────────────────────────────────────

export const adminLogs = {
  recent: '/api/admin/logs',
} as const
