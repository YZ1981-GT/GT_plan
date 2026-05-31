/**
 * API 路径 — 报表、现金流量表、附注、审计报告、导出
 */

// ─── 财务报表 ───────────────────────────────────────────────────────────────

export const reports = {
  generate: '/api/reports/generate',
  get: (pid: string, year: number, type: string) => `/api/reports/${pid}/${year}/${type}`,
  drilldown: (pid: string, year: number, type: string, rowCode: string) =>
    `/api/reports/${pid}/${year}/${type}/drilldown/${rowCode}`,
  relatedWorkpapers: (pid: string, year: number, type: string, rowCode: string) =>
    `/api/reports/${pid}/${year}/${type}/${rowCode}/related-workpapers`,
  consistencyCheck: (pid: string, year: number) => `/api/reports/${pid}/${year}/consistency-check`,
  exportExcel: (pid: string, year: number, type: string) => `/api/reports/${pid}/${year}/${type}/export-excel`,
  export: (pid: string, year: number) => `/api/reports/${pid}/${year}/export`,
  lineComposition: (pid: string, lineCode: string) => `/api/projects/${pid}/reports/line-composition?line_code=${encodeURIComponent(lineCode)}`,
  multiYear: (pid: string, years: number[], reportType: string) =>
    `/api/projects/${pid}/reports/multi-year?years=${years.join(',')}&report_type=${reportType}`,
  // Sprint 4 Task 4.3: 反查所有引用此报表行的附注章节
  noteReferences: (pid: string, year: number, rowCode: string) =>
    `/api/financial-reports/${pid}/${year}/${encodeURIComponent(rowCode)}/note-references`,
} as const

// ─── 报表配置 ───────────────────────────────────────────────────────────────

export const reportConfig = {
  list: '/api/report-config',
  drillDown: '/api/report-config/drill-down',
  detail: (id: string) => `/api/report-config/${id}`,
  create: '/api/report-config',
  executeFormulasBatch: '/api/report-config/execute-formulas-batch',
  batchUpdate: '/api/report-config/batch-update',
  // 主模板回填 + 联动
  suggestToMaster: '/api/report-config/suggest-to-master',
  reviewCandidate: '/api/report-config/review-candidate',
  diffVsMaster: (projectId: string) => `/api/report-config/diff-vs-master/${projectId}`,
  applyMasterUpdate: '/api/report-config/apply-master-update',
  candidates: '/api/report-config/candidates',
  staleStatus: (projectId: string) => `/api/report-config/stale-status/${projectId}`,
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

// ─── 项目级自定义附注模板（Sprint 3 Task 3.2/3.4/3.5） ─────────────────────

export const noteCustomTemplate = {
  load: (pid: string) => `/api/projects/${pid}/note-template`,
  save: (pid: string) => `/api/projects/${pid}/note-template/save`,
  versions: (pid: string) => `/api/projects/${pid}/note-template/versions`,
  restore: (pid: string, version: number) =>
    `/api/projects/${pid}/note-template/restore?version=${version}`,
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
  clearFormulas: (pid: string, year: number, section: string) => `/api/disclosure-notes/${pid}/${year}/${section}/clear-formulas`,
  exportWord: (pid: string, year: number) => `/api/disclosure-notes/${pid}/${year}/export-word`,
  priorYear: (pid: string, year: number, section: string) => `/api/disclosure-notes/${pid}/${year}/${section}/prior-year`,
  relatedWorkpapers: (pid: string, year: number, section: string, rowCode: string) => `/api/notes/${pid}/${year}/${encodeURIComponent(section)}/row/${encodeURIComponent(rowCode)}/related-workpapers`,
  templateStructure: (pid: string, year: number, section: string) => `/api/disclosure-notes/${pid}/${year}/${section}/template-structure`,
  // Sprint 4 Task 4.4: 致同附注 Word 排版规范（21 项参数）
  formatConfig: '/api/disclosure-notes/format-config',
  ai: {
    generatePolicy: (pid: string) => `/api/disclosure-notes/${pid}/ai/generate-policy`,
    generateAnalysis: (pid: string) => `/api/disclosure-notes/${pid}/ai/generate-analysis`,
    rewrite: (pid: string) => `/api/disclosure-notes/${pid}/ai/rewrite`,
    complete: (pid: string) => `/api/disclosure-notes/${pid}/ai/complete`,
    checkCompleteness: (pid: string) => `/api/disclosure-notes/${pid}/ai/check-completeness`,
  },
  conversion: {
    preview: (pid: string) => `/api/projects/${pid}/notes/conversion/preview`,
    execute: (pid: string) => `/api/projects/${pid}/notes/conversion/execute`,
    rollback: (pid: string) => `/api/projects/${pid}/notes/conversion/rollback`,
  },
  importPriorYear: (pid: string) => `/api/projects/${pid}/notes/import-prior-year`,
  inheritPriorYear: (pid: string) => `/api/projects/${pid}/notes/inherit-prior-year`,
  crossReferences: (pid: string, year: number) => `/api/projects/${pid}/notes/cross-references?year=${year}`,
  crossReferencesUpdate: (pid: string, year: number) => `/api/projects/${pid}/notes/cross-references/update?year=${year}`,
  generateVariationAnalysis: (pid: string, year: number) => `/api/projects/${pid}/notes/generate-variation-analysis?year=${year}`,
  traceSource: (pid: string, cellId: string) => `/api/projects/${pid}/notes/trace-source?cell_id=${encodeURIComponent(cellId)}`,
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

// ─── 排版模板 ───────────────────────────────────────────────────────────────

export const reportFormatTemplates = {
  list: '/api/report-format-templates',
  create: '/api/report-format-templates',
} as const

// ─── 溯源 ───────────────────────────────────────────────────────────────────

export const reportReview = {
  trace: (pid: string, section: string) => `/api/report-review/${pid}/trace/${encodeURIComponent(section)}`,
} as const

// ─── 附注协作与锁定 ─────────────────────────────────────────────────────────

export const noteLocks = {
  acquire: (pid: string) => `/api/projects/${pid}/notes/locks/acquire`,
  release: (pid: string) => `/api/projects/${pid}/notes/locks/release`,
  forceRelease: (pid: string) => `/api/projects/${pid}/notes/locks/force-release`,
  heartbeat: (pid: string) => `/api/projects/${pid}/notes/locks/heartbeat`,
  active: (pid: string) => `/api/projects/${pid}/notes/locks/active`,
} as const

// ─── 集团模板 ───────────────────────────────────────────────────────────────

export const noteGroupTemplate = {
  save: (pid: string) => `/api/projects/${pid}/notes/group-template/save`,
  distribute: (pid: string) => `/api/projects/${pid}/notes/group-template/distribute`,
  detach: (pid: string) => `/api/projects/${pid}/notes/group-template/detach`,
  list: (pid: string) => `/api/projects/${pid}/notes/group-template/list`,
} as const

// ─── 自定义章节 ─────────────────────────────────────────────────────────────

export const noteCustomSections = {
  create: (pid: string) => `/api/projects/${pid}/notes/custom-sections/create`,
  saveAsTemplate: (pid: string) => `/api/projects/${pid}/notes/custom-sections/save-as-template`,
  applyTemplate: (pid: string) => `/api/projects/${pid}/notes/custom-sections/apply-template`,
  templates: (pid: string) => `/api/projects/${pid}/notes/custom-sections/templates`,
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
    // Phase 2 F3：重新汇总合并附注（消费子公司单体附注，V2 接线 → ReaggregateResponse）
    reaggregate: (pid: string, year: number) => `/api/consolidation/notes/${pid}/${year}/reaggregate`,
    // Phase 3：附注级合并穿透明细（disclosure_notes.consolidation_breakdown provenance）
    consolBreakdown: (pid: string, year: number, sectionId: string) =>
      `/api/consolidation/notes/${pid}/${year}/${sectionId}/consol-breakdown`,
  },
  reports: {
    list: (pid: string, year: number) => `/api/consolidation/reports/${pid}/${year}`,
    generate: '/api/consolidation/reports/generate',
    balanceCheck: (pid: string, year: number) => `/api/consolidation/reports/${pid}/${year}/balance-check`,
    // 报表级合并穿透明细（前瞻定义，依赖 Phase 2 后端端点；未就绪时组件降级为友好空态）
    consolBreakdown: (pid: string, year: number, accountCode: string) =>
      `/api/consolidation/report/${pid}/${year}/${accountCode}/consol-breakdown`,
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
  // Phase 2 F3（A5 一键级联刷新）：refresh-all 入队后台 worker 返回 job_id；
  // refresh-status 为 SSE 断开时的兜底查询（EH6）。SSE 进度走既有 events/stream。
  refreshAll: (pid: string, year: number) => `/api/consolidation/${pid}/${year}/refresh-all`,
  refreshStatus: (pid: string, year: number, jobId: string) =>
    `/api/consolidation/${pid}/${year}/refresh-status/${jobId}`,
} as const

// ─── 合并工作底稿数据 ───────────────────────────────────────────────────────

export const consolWorksheetData = {
  get: (pid: string, year: number, sheetKey: string) => `/api/consol-worksheet-data/${pid}/${year}/${sheetKey}`,
  listAll: (pid: string, year: number) => `/api/consol-worksheet-data/${pid}/${year}`,
} as const
