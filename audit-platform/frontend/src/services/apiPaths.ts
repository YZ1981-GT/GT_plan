/**
 * API 路径集中管理 [R6.1]
 *
 * 按业务域分组定义所有 API 路径，消除 service 文件中的硬编码字符串。
 * 规则：
 *   - 静态路径用字符串常量
 *   - 动态路径用函数（参数名与后端路由一致）
 *   - query params 不在此处拼接，由调用方传入
 */

// ─── 项目 ───────────────────────────────────────────────────────────────────

export const projects = {
  list: '/api/projects',
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
  },
  findingsSummary: (id: string) => `/api/projects/${id}/findings-summary`,
  costOverview: (id: string) => `/api/projects/${id}/cost-overview`,
} as const

// ─── 试算表 ─────────────────────────────────────────────────────────────────

export const trialBalance = {
  get: (pid: string) => `/api/projects/${pid}/trial-balance`,
  recalc: (pid: string) => `/api/projects/${pid}/trial-balance/recalc`,
  consistencyCheck: (pid: string) => `/api/projects/${pid}/trial-balance/consistency-check`,
} as const

// ─── 调整分录 ───────────────────────────────────────────────────────────────

export const adjustments = {
  list: (pid: string) => `/api/projects/${pid}/adjustments`,
  create: (pid: string) => `/api/projects/${pid}/adjustments`,
  detail: (pid: string, groupId: string) => `/api/projects/${pid}/adjustments/${groupId}`,
  review: (pid: string, groupId: string) => `/api/projects/${pid}/adjustments/${groupId}/review`,
  batchCommit: (pid: string) => `/api/projects/${pid}/adjustments/batch-commit`,
  summary: (pid: string) => `/api/projects/${pid}/adjustments/summary`,
  accountDropdown: (pid: string) => `/api/projects/${pid}/adjustments/account-dropdown`,
  exportSummary: (pid: string) => `/api/projects/${pid}/adjustments/export-summary`,
  convertToMisstatement: (pid: string, groupId: string) => `/api/projects/${pid}/adjustments/${groupId}/convert-to-misstatement`,
} as const

// ─── 重要性 ─────────────────────────────────────────────────────────────────

export const materiality = {
  get: (pid: string) => `/api/projects/${pid}/materiality`,
  calculate: (pid: string) => `/api/projects/${pid}/materiality/calculate`,
  override: (pid: string) => `/api/projects/${pid}/materiality/override`,
  history: (pid: string) => `/api/projects/${pid}/materiality/history`,
  benchmark: (pid: string) => `/api/projects/${pid}/materiality/benchmark`,
} as const

// ─── 未更正错报 ─────────────────────────────────────────────────────────────

export const misstatements = {
  list: (pid: string) => `/api/projects/${pid}/misstatements`,
  create: (pid: string) => `/api/projects/${pid}/misstatements`,
  fromAje: (pid: string, groupId: string) => `/api/projects/${pid}/misstatements/from-aje/${groupId}`,
  detail: (pid: string, id: string) => `/api/projects/${pid}/misstatements/${id}`,
  summary: (pid: string) => `/api/projects/${pid}/misstatements/summary`,
} as const

// ─── 财务报表 ───────────────────────────────────────────────────────────────

export const reports = {
  generate: '/api/reports/generate',
  get: (pid: string, year: number, type: string) => `/api/reports/${pid}/${year}/${type}`,
  drilldown: (pid: string, year: number, type: string, rowCode: string) =>
    `/api/reports/${pid}/${year}/${type}/drilldown/${rowCode}`,
  consistencyCheck: (pid: string, year: number) => `/api/reports/${pid}/${year}/consistency-check`,
  exportExcel: (pid: string, year: number, type: string) => `/api/reports/${pid}/${year}/${type}/export-excel`,
  export: (pid: string, year: number) => `/api/reports/${pid}/${year}/export`,
} as const

// ─── 报表配置 ───────────────────────────────────────────────────────────────

export const reportConfig = {
  list: '/api/report-config',
  drillDown: '/api/report-config/drill-down',
  detail: (id: string) => `/api/report-config/${id}`,
  create: '/api/report-config',
  executeFormulasBatch: '/api/report-config/execute-formulas-batch',
  batchUpdate: '/api/report-config/batch-update',
} as const

// ─── 报表映射 ───────────────────────────────────────────────────────────────

export const reportMapping = {
  preset: (pid: string) => `/api/projects/${pid}/report-mapping/preset`,
  save: (pid: string) => `/api/projects/${pid}/report-mapping`,
} as const

// ─── 附注模板 ───────────────────────────────────────────────────────────────

export const noteTemplates = {
  list: (templateType: string) => `/api/note-templates/${templateType}`,
  presetFormulas: (templateType: string) => `/api/note-templates/preset-formulas/${templateType}`,
} as const

// ─── 合并附注 ───────────────────────────────────────────────────────────────

export const consolNoteSections = {
  list: (templateType: string) => `/api/consol-note-sections/${templateType}`,
  detail: (templateType: string, sectionId: string) => `/api/consol-note-sections/${templateType}/${sectionId}`,
  aggregate: (pid: string, year: number) => `/api/consol-note-sections/aggregate/${pid}/${year}`,
  refresh: (pid: string, year: number, sectionId: string) => `/api/consol-note-sections/refresh/${pid}/${year}/${sectionId}`,
  data: (pid: string, year: number, sectionId: string) => `/api/consol-note-sections/data/${pid}/${year}/${sectionId}`,
  applyFormulas: (pid: string, year: number) => `/api/consol-note-sections/apply-formulas/${pid}/${year}`,
  auditAll: (pid: string, year: number) => `/api/consol-note-sections/audit-all/${pid}/${year}`,
  audit: (pid: string, year: number, sectionId: string) => `/api/consol-note-sections/audit/${pid}/${year}/${sectionId}`,
} as const

// ─── 现金流量表工作底稿 ─────────────────────────────────────────────────────

export const cfsWorksheet = {
  generate: '/api/cfs-worksheet/generate',
  get: (pid: string, year: number) => `/api/cfs-worksheet/${pid}/${year}`,
  adjustments: {
    create: '/api/cfs-worksheet/adjustments',
    detail: (id: string) => `/api/cfs-worksheet/adjustments/${id}`,
  },
  reconciliation: (pid: string, year: number) => `/api/cfs-worksheet/${pid}/${year}/reconciliation`,
  autoGenerate: '/api/cfs-worksheet/auto-generate',
  indirectMethod: (pid: string, year: number) => `/api/cfs-worksheet/${pid}/${year}/indirect-method`,
  verify: (pid: string, year: number) => `/api/cfs-worksheet/${pid}/${year}/verify`,
} as const

// ─── 附注 ───────────────────────────────────────────────────────────────────

export const disclosureNotes = {
  generate: '/api/disclosure-notes/generate',
  tree: (pid: string, year: number) => `/api/disclosure-notes/${pid}/${year}`,
  detail: (pid: string, year: number, section: string) => `/api/disclosure-notes/${pid}/${year}/${section}`,
  update: (noteId: string) => `/api/disclosure-notes/${noteId}`,
  validate: (pid: string, year: number) => `/api/disclosure-notes/${pid}/${year}/validate`,
  validationResults: (pid: string, year: number) => `/api/disclosure-notes/${pid}/${year}/validation-results`,
  refreshFromWorkpapers: (pid: string, year: number) => `/api/disclosure-notes/${pid}/${year}/refresh-from-workpapers`,
  ai: {
    generatePolicy: (pid: string) => `/api/disclosure-notes/${pid}/ai/generate-policy`,
    generateAnalysis: (pid: string) => `/api/disclosure-notes/${pid}/ai/generate-analysis`,
    rewrite: (pid: string) => `/api/disclosure-notes/${pid}/ai/rewrite`,
    complete: (pid: string) => `/api/disclosure-notes/${pid}/ai/complete`,
    checkCompleteness: (pid: string) => `/api/disclosure-notes/${pid}/ai/check-completeness`,
  },
} as const

// ─── 审计报告 ───────────────────────────────────────────────────────────────

export const auditReport = {
  generate: '/api/audit-report/generate',
  get: (pid: string, year: number) => `/api/audit-report/${pid}/${year}`,
  paragraph: (reportId: string, section: string) => `/api/audit-report/${reportId}/paragraphs/${section}`,
  templates: '/api/audit-report/templates',
  status: (reportId: string) => `/api/audit-report/${reportId}/status`,
  refreshFinancialData: (pid: string, year: number) => `/api/audit-report/${pid}/${year}/refresh-financial-data`,
  exportWord: (pid: string, year: number) => `/api/audit-report/${pid}/${year}/export-word`,
} as const

// ─── 导出 ───────────────────────────────────────────────────────────────────

export const exportTask = {
  create: '/api/export/create',
  status: (taskId: string) => `/api/export/${taskId}/status`,
  download: (taskId: string) => `/api/export/${taskId}/download`,
  history: (pid: string) => `/api/export/${pid}/history`,
} as const

// ─── 底稿跨企业汇总 ─────────────────────────────────────────────────────────

export const workpaperSummary = {
  generate: (pid: string) => `/api/projects/${pid}/workpaper-summary`,
  export: (pid: string) => `/api/projects/${pid}/workpaper-summary/export`,
} as const

// ─── SSE 事件流 ─────────────────────────────────────────────────────────────

export const events = {
  stream: (pid: string) => `/api/projects/${pid}/events/stream`,
} as const

// ─── 合并报表 ───────────────────────────────────────────────────────────────

export const consolidation = {
  scope: {
    list: '/api/consolidation/scope',
    detail: (scopeId: string) => `/api/consolidation/scope/${scopeId}`,
    batch: '/api/consolidation/scope/batch',
    summary: '/api/consolidation/scope/summary',
  },
  trial: {
    list: '/api/consolidation/trial',
    recalculate: '/api/consolidation/trial/recalculate',
    consistencyCheck: '/api/consolidation/trial/consistency-check',
  },
  eliminations: {
    list: '/api/consolidation/eliminations',
    detail: (entryId: string) => `/api/consolidation/eliminations/${entryId}`,
    review: (entryId: string) => `/api/consolidation/eliminations/${entryId}/review`,
    summary: '/api/consolidation/eliminations/summary/year',
  },
  internalTrade: {
    trades: '/api/consolidation/internal-trade/trades',
    arap: '/api/consolidation/internal-trade/arap',
    matrix: '/api/consolidation/internal-trade/matrix',
  },
  componentAuditor: {
    auditors: '/api/consolidation/component-auditor/auditors',
    instructions: '/api/consolidation/component-auditor/instructions',
    results: {
      list: '/api/consolidation/component-auditor/results',
      detail: (resultId: string) => `/api/consolidation/component-auditor/results/${resultId}`,
    },
    dashboard: '/api/consolidation/component-auditor/dashboard',
  },
  goodwill: '/api/consolidation/goodwill',
  forex: '/api/consolidation/forex',
  minorityInterest: '/api/consolidation/minority-interest',
  notes: {
    list: (pid: string, year: number) => `/api/consolidation/notes/${pid}/${year}`,
    save: (pid: string, year: number) => `/api/consolidation/notes/${pid}/${year}/save`,
  },
  reports: {
    list: (pid: string, year: number) => `/api/consolidation/reports/${pid}/${year}`,
    generate: '/api/consolidation/reports/generate',
    balanceCheck: (pid: string, year: number) => `/api/consolidation/reports/${pid}/${year}/balance-check`,
  },
  worksheet: {
    tree: '/api/consolidation/worksheet/tree',
    recalc: '/api/consolidation/worksheet/recalc',
    aggregate: '/api/consolidation/worksheet/aggregate',
    drillCompanies: '/api/consolidation/worksheet/drill/companies',
    drillEliminations: '/api/consolidation/worksheet/drill/eliminations',
    drillTrialBalance: '/api/consolidation/worksheet/drill/trial-balance',
    pivot: '/api/consolidation/worksheet/pivot',
    pivotExport: '/api/consolidation/worksheet/pivot/export',
    pivotTemplates: '/api/consolidation/worksheet/pivot/templates',
  },
  lock: (pid: string) => `/api/consolidation/${pid}/lock`,
  unlock: (pid: string) => `/api/consolidation/${pid}/unlock`,
  lockStatus: (pid: string) => `/api/consolidation/${pid}/lock-status`,
  snapshots: (pid: string) => `/api/consolidation/${pid}/snapshots`,
} as const

// ─── 合并工作底稿数据 ───────────────────────────────────────────────────────

export const consolWorksheetData = {
  get: (pid: string, year: number, sheetKey: string) => `/api/consol-worksheet-data/${pid}/${year}/${sheetKey}`,
  listAll: (pid: string, year: number) => `/api/consol-worksheet-data/${pid}/${year}`,
} as const

// ─── 底稿管理 ───────────────────────────────────────────────────────────────

export const workpapers = {
  list: (pid: string) => `/api/projects/${pid}/working-papers`,
  detail: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}`,
  download: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/download`,
  downloadPack: (pid: string) => `/api/projects/${pid}/working-papers/download-pack`,
  upload: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/upload`,
  uploadFile: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/upload-file`,
  onlineSession: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/online-session`,
  status: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/status`,
  reviewStatus: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/review-status`,
  assign: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/assign`,
  prefill: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/prefill`,
  parse: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/parse`,
  submitReview: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/submit-review`,
  qcCheck: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/qc-check`,
  qcResults: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/qc-results`,
  editTime: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/edit-time`,
  crossLinks: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/cross-links`,
  syncProcedure: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/sync-procedure`,
  dependencies: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/dependencies`,
  structure: {
    get: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/structure`,
    rebuild: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/structure/rebuild`,
    html: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/structure/html`,
    addresses: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/structure/addresses`,
  },
  batchStructure: (pid: string) => `/api/projects/${pid}/workpapers/batch-structure`,
  createCustom: (pid: string) => `/api/projects/${pid}/working-papers/create-custom`,
  progress: (pid: string) => `/api/projects/${pid}/workpapers/progress`,
  overdue: (pid: string) => `/api/projects/${pid}/workpapers/overdue`,
  kanban: (pid: string) => `/api/projects/${pid}/working-papers-kanban`,
  batchAssign: (pid: string) => `/api/projects/${pid}/working-papers/batch-assign`,
  batchSubmit: (pid: string) => `/api/projects/${pid}/working-papers/batch-submit`,
  batchExport: (pid: string) => `/api/projects/${pid}/working-papers/batch-export`,
  wpIndex: (pid: string) => `/api/projects/${pid}/wp-index`,
  wpCrossRefs: (pid: string) => `/api/projects/${pid}/wp-cross-refs`,
  qcSummary: (pid: string) => `/api/projects/${pid}/qc-summary`,
  batchPrefill: (pid: string) => `/api/projects/${pid}/working-papers/batch-prefill`,
  generateFromCodes: (pid: string) => `/api/projects/${pid}/working-papers/generate-from-codes`,
  wpMappingTsj: (pid: string, accountName: string) => `/api/projects/${pid}/wp-mapping/tsj/${encodeURIComponent(accountName)}`,
  versions: (wpId: string) => `/api/workpapers/${wpId}/versions`,
  univerData: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/univer-data`,
  univerSave: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/univer-save`,
  exportPdf: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/export-pdf`,
} as const

// ─── 底稿复核批注 ───────────────────────────────────────────────────────────

export const wpReviews = {
  list: (wpId: string) => `/api/working-papers/${wpId}/reviews`,
  detail: (wpId: string, reviewId: string) => `/api/working-papers/${wpId}/reviews/${reviewId}`,
  reply: (wpId: string, reviewId: string) => `/api/working-papers/${wpId}/reviews/${reviewId}/reply`,
  resolve: (wpId: string, reviewId: string) => `/api/working-papers/${wpId}/reviews/${reviewId}/resolve`,
} as const

// ─── 底稿 WP-Account 映射 ──────────────────────────────────────────────────

export const wpMapping = {
  byAccount: (pid: string, code: string) => `/api/projects/${pid}/wp-mapping/by-account/${code}`,
  prefill: (pid: string, wpCode: string) => `/api/projects/${pid}/wp-mapping/prefill/${wpCode}`,
  all: (pid: string) => `/api/projects/${pid}/wp-mapping/all`,
  recommend: (pid: string) => `/api/projects/${pid}/wp-mapping/recommend`,
} as const

// ─── 底稿 AI ────────────────────────────────────────────────────────────────

export const wpAI = {
  generateExplanation: (pid: string, wpId: string) => `/api/projects/${pid}/wp-ai/${wpId}/generate-explanation`,
  confirmExplanation: (pid: string, wpId: string) => `/api/projects/${pid}/wp-ai/${wpId}/confirm-explanation`,
  refineExplanation: (pid: string, wpId: string) => `/api/projects/${pid}/wp-ai/${wpId}/refine-explanation`,
  reviewContent: (pid: string, wpId: string) => `/api/projects/${pid}/wp-ai/${wpId}/review-content`,
  aiFill: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/ai-fill`,
  chat: (wpId: string) => `/api/workpapers/${wpId}/ai/chat`,
  generateLedgerAnalysis: (pid: string) => `/api/workpapers/projects/${pid}/ai/generate-ledger-analysis`,
  recommendWorkpapers: (pid: string) => `/api/projects/${pid}/ai/recommend-workpapers`,
  annualDiffReport: (pid: string) => `/api/projects/${pid}/ai/annual-diff-report`,
} as const

// ─── 底稿精细化规则 ─────────────────────────────────────────────────────────

export const wpFineRules = {
  list: '/api/wp-fine-rules',
  detail: (wpCode: string) => `/api/wp-fine-rules/${wpCode}`,
  fineExtract: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/fine-extract`,
} as const

// ─── 底稿操作手册 ───────────────────────────────────────────────────────────

export const wpManuals = {
  list: '/api/wp-manuals',
  stats: '/api/wp-manuals/stats',
  cycle: (cycle: string) => `/api/wp-manuals/${cycle}`,
  manual: (cycle: string) => `/api/wp-manuals/${cycle}/manual`,
  context: (cycle: string) => `/api/wp-manuals/${cycle}/context`,
} as const

// ─── 底稿依赖关系 ───────────────────────────────────────────────────────────

export const wpDependencies = {
  cycleGraph: (cycle: string) => `/api/wp-dependencies/cycle/${cycle}`,
  cycles: '/api/wp-dependencies/cycles',
} as const

// ─── 模板管理 ───────────────────────────────────────────────────────────────

export const templates = {
  list: '/api/templates',
  create: '/api/templates',
  versions: (code: string) => `/api/templates/${code}/versions`,
  delete: (id: string) => `/api/templates/${id}`,
  sets: {
    list: '/api/template-sets',
    detail: (setId: string) => `/api/template-sets/${setId}`,
  },
} as const

// ─── 公式 ───────────────────────────────────────────────────────────────────

export const formula = {
  execute: '/api/formula/execute',
  batchExecute: '/api/formula/batch-execute',
} as const

// ─── 抽样 ───────────────────────────────────────────────────────────────────

export const sampling = {
  configs: {
    list: (pid: string) => `/api/projects/${pid}/sampling-configs`,
    detail: (pid: string, configId: string) => `/api/projects/${pid}/sampling-configs/${configId}`,
    calculate: (pid: string) => `/api/projects/${pid}/sampling-configs/calculate`,
  },
  records: {
    list: (pid: string) => `/api/projects/${pid}/sampling-records`,
    detail: (pid: string, recordId: string) => `/api/projects/${pid}/sampling-records/${recordId}`,
    musEvaluate: (pid: string, recordId: string) => `/api/projects/${pid}/sampling-records/${recordId}/mus-evaluate`,
  },
  cutoffTest: (pid: string) => `/api/projects/${pid}/sampling/cutoff-test`,
  agingAnalysis: (pid: string) => `/api/projects/${pid}/sampling/aging-analysis`,
  monthlyDetail: (pid: string) => `/api/projects/${pid}/sampling/monthly-detail`,
} as const

// ─── 人员 ───────────────────────────────────────────────────────────────────

export const staff = {
  list: '/api/staff',
  create: '/api/staff',
  detail: (id: string) => `/api/staff/${id}`,
  resume: (id: string) => `/api/staff/${id}/resume`,
  projects: (id: string) => `/api/staff/${id}/projects`,
  meStaffId: '/api/staff/me/staff-id',
  myAssignments: '/api/staff/my/assignments',
  myTodos: '/api/staff/me/todos',
  workHours: (id: string) => `/api/staff/${id}/work-hours`,
  checkIn: (id: string) => `/api/staff/${id}/check-in`,
  checkIns: (id: string) => `/api/staff/${id}/check-ins`,
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

// ─── 认证 ───────────────────────────────────────────────────────────────────

export const auth = {
  login: '/api/auth/login',
  refresh: '/api/auth/refresh',
  logout: '/api/auth/logout',
  me: '/api/auth/me',
  register: '/api/auth/register',
} as const

// ─── 通知 ───────────────────────────────────────────────────────────────────

export const notifications = {
  list: '/api/notifications',
  unreadCount: '/api/notifications/unread-count',
  read: (id: string) => `/api/notifications/${id}/read`,
  readAll: '/api/notifications/read-all',
  delete: (id: string) => `/api/notifications/${id}`,
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
  manager: {
    overview: '/api/dashboard/manager/overview',
    assignmentStatus: '/api/dashboard/manager/assignment-status',
  },
} as const

// ─── 批注 ───────────────────────────────────────────────────────────────────

export const annotations = {
  list: (pid: string) => `/api/projects/${pid}/annotations`,
  create: (pid: string) => `/api/projects/${pid}/annotations`,
  update: (id: string) => `/api/annotations/${id}`,
} as const

// ─── 审计程序 ───────────────────────────────────────────────────────────────

export const procedures = {
  list: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}`,
  trim: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}/trim`,
  init: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}/init`,
  custom: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}/custom`,
  applyScheme: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}/apply-scheme`,
} as const

// ─── 复核 ───────────────────────────────────────────────────────────────────

export const reviews = {
  create: '/api/reviews',
  workpaper: (wpId: string) => `/api/reviews/workpaper/${wpId}`,
  pending: '/api/reviews/pending',
  start: (id: string) => `/api/reviews/${id}/start`,
  approve: (id: string) => `/api/reviews/${id}/approve`,
  reject: (id: string) => `/api/reviews/${id}/reject`,
  inbox: {
    global: '/api/review-inbox',
    project: (pid: string) => `/api/projects/${pid}/review-inbox`,
  },
  batchReview: (pid: string) => `/api/projects/${pid}/batch-review`,
  progressBoard: (pid: string) => `/api/projects/${pid}/progress-board`,
  progressBrief: (pid: string) => `/api/projects/${pid}/progress-brief`,
  crossRefCheck: (pid: string) => `/api/projects/${pid}/cross-ref-check`,
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

// ─── 审计日志 ───────────────────────────────────────────────────────────────

export const auditLogs = {
  list: '/api/audit-logs',
} as const

// ─── 项目管理 ───────────────────────────────────────────────────────────────

export const projectMgmt = {
  timeline: (pid: string) => `/api/projects/${pid}/timeline`,
  timelineComplete: (pid: string, tid: string) => `/api/projects/${pid}/timeline/${tid}/complete`,
  workHours: (pid: string) => `/api/projects/${pid}/work-hours`,
  budgetHours: (pid: string) => `/api/projects/${pid}/budget-hours`,
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

// ─── PBC ────────────────────────────────────────────────────────────────────

/**
 * @deprecated R7+ 计划 — 后端当前为 stub 实现（返回 status: "developing"）。
 * 前端暂无对应页面，待 R7 正式开发时补充真实实现。
 */
export const pbc = {
  items: (pid: string) => `/api/pbc/${pid}/items`,
  itemStatus: (pid: string, itemId: string) => `/api/pbc/${pid}/items/${itemId}/status`,
  pendingReminders: (pid: string) => `/api/pbc/${pid}/pending-reminders`,
} as const

// ─── 函证 ───────────────────────────────────────────────────────────────────

/**
 * @deprecated R7+ 计划 — 后端当前为 stub 实现（返回 status: "developing"）。
 * 前端暂无对应页面，待 R7 正式开发时补充真实实现。
 */
export const confirmations = {
  list: (pid: string) => `/api/confirmations/${pid}/confirmations`,
  detail: (pid: string, confId: string) => `/api/confirmations/${pid}/confirmations/${confId}`,
  letter: (pid: string, confId: string) => `/api/confirmations/${pid}/confirmations/${confId}/letter`,
  result: (pid: string, confId: string) => `/api/confirmations/${pid}/confirmations/${confId}/result`,
  summary: (pid: string) => `/api/confirmations/${pid}/summary`,
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

// ─── 复核对话 ───────────────────────────────────────────────────────────────

export const reviewConversations = {
  list: '/api/review-conversations',
  detail: (id: string) => `/api/review-conversations/${id}`,
  messages: (id: string) => `/api/review-conversations/${id}/messages`,
  close: (id: string) => `/api/review-conversations/${id}/close`,
  export: (id: string) => `/api/review-conversations/${id}/export`,
  projectList: (pid: string) => `/api/projects/${pid}/review-conversations`,
} as const

// ─── 论坛 ───────────────────────────────────────────────────────────────────

export const forum = {
  posts: '/api/forum/posts',
  comments: (postId: string) => `/api/forum/posts/${postId}/comments`,
  like: (postId: string) => `/api/forum/posts/${postId}/like`,
} as const

// ─── 溯源 ───────────────────────────────────────────────────────────────────

export const reportReview = {
  trace: (pid: string, section: string) => `/api/report-review/${pid}/trace/${encodeURIComponent(section)}`,
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
  download: (id: string) => `/api/attachments/${id}/download`,
  associate: (id: string) => `/api/attachments/${id}/associate`,
  ocrStatus: (id: string) => `/api/attachments/${id}/ocr-status`,
} as const

// ─── 穿透查询 ───────────────────────────────────────────────────────────────

export const ledger = {
  balance: (pid: string) => `/api/projects/${pid}/ledger/balance`,
  entries: (pid: string, code: string) => `/api/projects/${pid}/ledger/entries/${encodeURIComponent(code)}`,
  openingBalance: (pid: string, code: string) => `/api/projects/${pid}/ledger/opening-balance/${encodeURIComponent(code)}`,
  voucher: (pid: string, voucherNo: string) => `/api/projects/${pid}/ledger/voucher/${encodeURIComponent(voucherNo)}`,
  years: (pid: string) => `/api/projects/${pid}/ledger/years`,
  validate: (pid: string) => `/api/projects/${pid}/ledger/validate`,
  smartPreview: (pid: string) => `/api/projects/${pid}/ledger/smart-preview`,
  smartImport: (pid: string) => `/api/projects/${pid}/ledger/smart-import`,
  auxBalance: (pid: string, code: string) => `/api/projects/${pid}/ledger/aux-balance/${code}`,
  auxBalanceDetail: (pid: string) => `/api/projects/${pid}/ledger/aux-balance-detail`,
  auxBalanceSummary: (pid: string) => `/api/projects/${pid}/ledger/aux-balance-summary`,
  auxBalancePaged: (pid: string) => `/api/projects/${pid}/ledger/aux-balance-paged`,
  auxEntries: (pid: string, code: string) => `/api/projects/${pid}/ledger/aux-entries/${code}`,
  auxSummary: (pid: string) => `/api/projects/${pid}/ledger/aux-summary`,
  exportBalance: (pid: string) => `/api/projects/${pid}/ledger/export-balance`,
  exportAuxBalance: (pid: string) => `/api/projects/${pid}/ledger/export-aux-balance`,
  exportLedger: (pid: string, code: string) => `/api/projects/${pid}/ledger/export-ledger/${encodeURIComponent(code)}`,
  import: {
    base: (pid: string) => `/api/projects/${pid}/ledger-import`,
    datasets: (pid: string) => `/api/projects/${pid}/ledger-import/datasets`,
    datasetsActive: (pid: string) => `/api/projects/${pid}/ledger-import/datasets/active`,
    datasetRollback: (pid: string, dsId: string) => `/api/projects/${pid}/ledger-import/datasets/${dsId}/rollback`,
    jobs: (pid: string) => `/api/projects/${pid}/ledger-import/jobs`,
    jobDetail: (pid: string, jobId: string) => `/api/projects/${pid}/ledger-import/jobs/${jobId}`,
    jobRetry: (pid: string, jobId: string) => `/api/projects/${pid}/ledger-import/jobs/${jobId}/retry`,
    jobCancel: (pid: string, jobId: string) => `/api/projects/${pid}/ledger-import/jobs/${jobId}/cancel`,
    activationRecords: (pid: string) => `/api/projects/${pid}/ledger-import/activation-records`,
    artifacts: (pid: string) => `/api/projects/${pid}/ledger-import/artifacts`,
  },
} as const

// ─── T型账户 ────────────────────────────────────────────────────────────────

export const tAccounts = {
  list: (pid: string) => `/api/projects/${pid}/t-accounts`,
  detail: (pid: string, id: string) => `/api/projects/${pid}/t-accounts/${id}`,
  entries: (pid: string, id: string) => `/api/projects/${pid}/t-accounts/${id}/entries`,
  calculate: (pid: string, id: string) => `/api/projects/${pid}/t-accounts/${id}/calculate`,
} as const

// ─── 共享配置模板 ───────────────────────────────────────────────────────────

export const sharedConfig = {
  templates: '/api/shared-config/templates',
  detail: (id: string) => `/api/shared-config/templates/${id}`,
  apply: '/api/shared-config/apply',
  references: (pid: string) => `/api/shared-config/references/${pid}`,
} as const

// ─── 自定义模板 ─────────────────────────────────────────────────────────────

export const customTemplates = {
  list: '/api/custom-templates',
  detail: (id: string) => `/api/custom-templates/${id}`,
  validate: (id: string) => `/api/custom-templates/${id}/validate`,
  publish: (id: string) => `/api/custom-templates/${id}/publish`,
  copy: (id: string) => `/api/custom-templates/${id}/copy`,
} as const

// ─── 模板库三层体系 ─────────────────────────────────────────────────────────

export const templateLibrary = {
  available: '/api/template-library/available',
  firm: '/api/template-library/firm',
  group: {
    create: '/api/template-library/group',
    list: (groupId: string) => `/api/template-library/group/${groupId}`,
  },
  project: {
    select: (pid: string) => `/api/template-library/projects/${pid}/select`,
    templates: (pid: string) => `/api/template-library/projects/${pid}/templates`,
    pull: (pid: string, templateId: string) => `/api/template-library/projects/${pid}/pull/${templateId}`,
  },
} as const

// ─── 排版模板 ───────────────────────────────────────────────────────────────

export const reportFormatTemplates = {
  list: '/api/report-format-templates',
  create: '/api/report-format-templates',
} as const

// ─── Excel↔HTML 互转 ────────────────────────────────────────────────────────

export const excelHtml = {
  uploadParse: (pid: string) => `/api/projects/${pid}/excel-html/upload-parse`,
  preview: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/preview/${fileStem}`,
  saveEdits: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/save-edits/${fileStem}`,
  confirmTemplate: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/confirm-template/${fileStem}`,
  syncFromOnlyoffice: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/sync-from-onlyoffice/${fileStem}`,
  module: {
    structure: (pid: string, mod: string) => `/api/projects/${pid}/excel-html/module/${mod}/structure`,
    html: (pid: string, mod: string) => `/api/projects/${pid}/excel-html/module/${mod}/html`,
    exportExcel: (pid: string, mod: string) => `/api/projects/${pid}/excel-html/module/${mod}/export-excel`,
    exportWord: (pid: string, mod: string) => `/api/projects/${pid}/excel-html/module/${mod}/export-word`,
  },
  lock: {
    acquire: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/lock/${fileStem}`,
    release: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/lock/${fileStem}`,
    refresh: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/lock/${fileStem}/refresh`,
  },
  versions: {
    list: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/versions/${fileStem}`,
    diff: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/versions/${fileStem}/diff`,
    rollback: (pid: string, fileStem: string, version: number) =>
      `/api/projects/${pid}/excel-html/versions/${fileStem}/rollback/${version}`,
  },
  executeFormulas: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/execute-formulas/${fileStem}`,
  cellInfo: (pid: string, fileStem: string) => `/api/projects/${pid}/excel-html/cell-info/${fileStem}`,
} as const

// ─── 账套导入 ───────────────────────────────────────────────────────────────

export const accountChart = {
  preview: (pid: string) => `/api/projects/${pid}/account-chart/preview`,
  importAsync: (pid: string) => `/api/projects/${pid}/account-chart/import-async`,
  importReset: (pid: string) => `/api/projects/${pid}/account-chart/import-reset`,
  client: (pid: string) => `/api/projects/${pid}/account-chart/client`,
  standard: (pid: string) => `/api/projects/${pid}/account-chart/standard`,
  batchUpdate: (pid: string) => `/api/projects/${pid}/account-chart/batch-update`,
} as const

// ─── 科目映射 ───────────────────────────────────────────────────────────────

export const accountMapping = {
  list: (pid: string) => `/api/projects/${pid}/mapping`,
  create: (pid: string) => `/api/projects/${pid}/mapping`,
  detail: (pid: string, mappingId: string) => `/api/projects/${pid}/mapping/${mappingId}`,
  autoMatch: (pid: string) => `/api/projects/${pid}/mapping/auto-match`,
  completionRate: (pid: string) => `/api/projects/${pid}/mapping/completion-rate`,
} as const

// ─── 报表行次映射 ───────────────────────────────────────────────────────────

export const reportLineMapping = {
  list: (pid: string) => `/api/projects/${pid}/report-line-mapping`,
  detail: (pid: string, id: string) => `/api/projects/${pid}/report-line-mapping/${id}`,
  confirm: (pid: string, id: string) => `/api/projects/${pid}/report-line-mapping/${id}/confirm`,
  aiSuggest: (pid: string) => `/api/projects/${pid}/report-line-mapping/ai-suggest`,
  batchConfirm: (pid: string) => `/api/projects/${pid}/report-line-mapping/batch-confirm`,
  referenceCopy: (pid: string) => `/api/projects/${pid}/report-line-mapping/reference-copy`,
} as const

// ─── 列映射 ─────────────────────────────────────────────────────────────────

export const columnMappings = {
  list: (pid: string) => `/api/projects/${pid}/column-mappings`,
  save: (pid: string) => `/api/projects/${pid}/column-mappings`,
  referenceProjects: (pid: string) => `/api/projects/${pid}/column-mappings/reference-projects`,
  referenceCopy: (pid: string) => `/api/projects/${pid}/column-mappings/reference-copy`,
} as const

// ─── 数据生命周期 ───────────────────────────────────────────────────────────

export const dataLifecycle = {
  importQueue: (pid: string) => `/api/data-lifecycle/import-queue/${pid}`,
} as const

// ─── 导入智能增强 ───────────────────────────────────────────────────────────

export const importIntelligence = {
  enhanceMapping: (pid: string) => `/api/projects/${pid}/import-intelligence/enhance-mapping`,
  qualityCheck: (pid: string) => `/api/projects/${pid}/import-intelligence/quality-check`,
  prepareIncremental: (pid: string) => `/api/projects/${pid}/import-intelligence/prepare-incremental`,
  overview: (pid: string) => `/api/projects/${pid}/import-intelligence/overview`,
} as const

// ─── 地址坐标注册表 ─────────────────────────────────────────────────────────

export const addressRegistry = {
  search: '/api/address-registry',
  stats: '/api/address-registry/stats',
  resolve: '/api/address-registry/resolve',
  validate: '/api/address-registry/validate',
  jump: '/api/address-registry/jump',
  invalidate: '/api/address-registry/invalidate',
} as const

// ─── 工时 ───────────────────────────────────────────────────────────────────

export const workHours = {
  list: '/api/workhours',
  summary: '/api/workhours/summary',
  batchApprove: '/api/workhours/batch-approve',
  detail: (hourId: string) => `/api/work-hours/${hourId}`,
  aiSuggest: '/api/work-hours/ai-suggest',
  editTimeSuggest: '/api/work-hours/edit-time-suggest',
} as const

// ─── 账龄分析 ───────────────────────────────────────────────────────────────

export const aging = {
  presets: '/api/aging/presets',
  config: (pid: string) => `/api/projects/${pid}/aging/config`,
  calculate: (pid: string) => `/api/projects/${pid}/aging/calculate`,
} as const

// ─── 监管备案 ───────────────────────────────────────────────────────────────

export const regulatory = {
  filings: '/api/regulatory/filings',
  retry: (id: string) => `/api/regulatory/filings/${id}/retry`,
  archivalStandard: '/api/regulatory/archival-standard',
  cicpaReport: '/api/regulatory/cicpa-report',
} as const

// ─── 其他 ───────────────────────────────────────────────────────────────────

export const aiPlugins = { list: '/api/ai-plugins' } as const
export const gtCoding = { list: '/api/gt-coding' } as const

// ─── 性能监控 ───────────────────────────────────────────────────────────────

export const admin = {
  performanceStats: '/api/admin/performance-stats',
  slowQueries: '/api/admin/slow-queries',
  performanceMetrics: '/api/admin/performance-metrics',
  importEventHealth: '/api/admin/import-event-health',
  importEventReplay: '/api/admin/import-event-replay',
} as const

// ─── 我的（个人聚合） ────────────────────────────────────────────────────────

export const my = {
  pendingIndependence: '/api/my/pending-independence',
  reminders: '/api/my/reminders',
  unreadAnnotations: '/api/my/unread-annotations/count',
} as const

// ─── 合伙人 ─────────────────────────────────────────────────────────────────

export const partner = {
  overview: '/api/partner/overview',
  teamEfficiency: '/api/partner/team-efficiency',
  workpaperReadiness: (pid: string) => `/api/projects/${pid}/partner/workpaper-readiness`,
} as const

// ─── 质控看板 ───────────────────────────────────────────────────────────────

export const qcDashboard = {
  overview: (pid: string) => `/api/projects/${pid}/qc-dashboard/overview`,
  staffProgress: (pid: string) => `/api/projects/${pid}/qc-dashboard/staff-progress`,
  openIssues: (pid: string) => `/api/projects/${pid}/qc-dashboard/open-issues`,
  archiveReadiness: (pid: string) => `/api/projects/${pid}/qc-dashboard/archive-readiness`,
  reviewerMetrics: '/api/qc/reviewer-metrics',
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

// ─── 底稿 Job ───────────────────────────────────────────────────────────────

export const jobs = {
  status: (pid: string, jobId: string) => `/api/projects/${pid}/jobs/${jobId}`,
  retry: (pid: string, jobId: string) => `/api/projects/${pid}/jobs/${jobId}/retry`,
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

// ─── 独立性声明（项目级） ───────────────────────────────────────────────────

export const independenceDeclarations = {
  questions: '/api/independence/questions',
  list: (pid: string) => `/api/projects/${pid}/independence-declarations`,
  detail: (pid: string, declId: string) => `/api/projects/${pid}/independence-declarations/${declId}`,
  submit: (pid: string, declId: string) => `/api/projects/${pid}/independence-declarations/${declId}/submit`,
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
  // 任务 7：关联方 CRUD
  relatedPartyDetail: (pid: string, partyId: string) =>
    `/api/eqcr/projects/${pid}/related-parties/${partyId}`,
  relatedPartyTransactions: (pid: string) =>
    `/api/eqcr/projects/${pid}/related-party-transactions`,
  relatedPartyTransactionDetail: (pid: string, txnId: string) =>
    `/api/eqcr/projects/${pid}/related-party-transactions/${txnId}`,
  // 任务 8/9：影子计算
  shadowCompute: '/api/eqcr/shadow-compute',
  shadowComputations: (pid: string) => `/api/eqcr/projects/${pid}/shadow-computations`,
  // 任务 10/11：独立复核笔记
  notes: (pid: string) => `/api/eqcr/projects/${pid}/notes`,
  noteDetail: (pid: string, noteId: string) => `/api/eqcr/projects/${pid}/notes/${noteId}`,
  noteShare: (noteId: string) => `/api/eqcr/notes/${noteId}/share-to-team`,
  // 任务 12：备忘录
  memoPreview: (pid: string) => `/api/eqcr/projects/${pid}/memo/preview`,
  memoGenerate: (pid: string) => `/api/eqcr/projects/${pid}/memo`,
  memoSave: (pid: string) => `/api/eqcr/projects/${pid}/memo`,
  memoFinalize: (pid: string) => `/api/eqcr/projects/${pid}/memo/finalize`,
  // 任务 13：工时/审批/解锁
  timeSummary: (pid: string) => `/api/eqcr/projects/${pid}/time-summary`,
  approve: (pid: string) => `/api/eqcr/projects/${pid}/approve`,
  unlockOpinion: (pid: string) => `/api/eqcr/projects/${pid}/unlock-opinion`,
  // 独立性声明
  independence: {
    check: '/api/eqcr/independence/annual/check',
    questions: '/api/eqcr/independence/annual/questions',
    submit: '/api/eqcr/independence/annual/submit',
  },
  // 组件审计师
  componentAuditors: (pid: string) => `/api/eqcr/projects/${pid}/component-auditors`,
  // 历年对比
  priorYearComparison: (pid: string) => `/api/eqcr/projects/${pid}/prior-year-comparison`,
  linkPriorYear: (pid: string) => `/api/eqcr/projects/${pid}/link-prior-year`,
  // 指标
  metrics: '/api/eqcr/metrics',
} as const

// ─── 签字流水线（Round 1 需求 4） ────────────────────────────────────────────

export const signatures = {
  sign: '/api/signatures/sign',
  workflow: (pid: string) => `/api/projects/${pid}/signature-workflow`,
  list: (objectType: string, objectId: string) => `/api/signatures/${objectType}/${objectId}`,
  verify: (sigId: string) => `/api/signatures/${sigId}/verify`,
  revoke: (sigId: string) => `/api/signatures/${sigId}/revoke`,
} as const

// ─── 合伙人轮换检查（Round 1 需求 11） ──────────────────────────────────────

export const rotation = {
  check: '/api/rotation/check',
  overrides: '/api/rotation/overrides',
} as const

// ─── 聚合导出（便于 import { API } from '@/services/apiPaths'） ─────────────

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
  accountChart, accountMapping, reportLineMapping, columnMappings, dataLifecycle, independenceDeclarations,
  admin, my, partner, qcDashboard, qcRules, qcInspections, qcCases,
  qcAnnualReports, qcAuditLogCompliance, qcArchiveReadiness,
  jobs, governance, eqcr, signatures, rotation,
} as const

export default API
