/**
 * API 路径 — 底稿管理、模板、复核、审计程序
 */

// ─── 底稿管理 ───────────────────────────────────────────────────────────────

export const workpapers = {
  list: (pid: string) => `/api/projects/${pid}/working-papers`,
  myLead: (pid: string) => `/api/projects/${pid}/my-lead-workpapers`,
  detail: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}`,
  download: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/download`,
  downloadPack: (pid: string) => `/api/projects/${pid}/working-papers/download-pack`,
  templateDownload: (pid: string, wpCode: string) => `/api/projects/${pid}/wp-templates/${wpCode}/download`,
  templatePreviewPdf: (pid: string, wpCode: string) => `/api/projects/${pid}/wp-templates/${wpCode}/preview-pdf`,
  templateDownloadAll: (pid: string) => `/api/projects/${pid}/wp-templates/download-all`,
  templateList: (pid: string) => `/api/projects/${pid}/wp-templates/list`,
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
  // ─── 自定义底稿（componentType=custom）───
  // 注意：这四个端点**不带 project 前缀**（挂在 /api/workpapers/{wpId} 下），
  // 与上面 project-scoped 的路径不同族，勿"顺手"补 pid。
  // spec: custom-workpaper-dual-mode-formula-and-batch
  customCells: (wpId: string) => `/api/workpapers/${wpId}/custom-cells`,
  customRefreshProjection: (wpId: string) => `/api/workpapers/${wpId}/custom-refresh-projection`,
  formulas: (wpId: string) => `/api/workpapers/${wpId}/formulas`,
  formulaDetail: (wpId: string, formulaId: string) => `/api/workpapers/${wpId}/formulas/${formulaId}`,
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
  /** S-4 (proposal-remaining-18 task 5.4)：在底稿全部历史版本 parsed_data.cells 中模糊搜索值 */
  searchVersions: (wpId: string) => `/api/working-papers/${wpId}/versions/search`,
  univerData: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/univer-data`,
  univerSave: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/univer-save`,
  exportPdf: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/export-pdf`,
  recalc: (pid: string, wpId: string) => `/api/projects/${pid}/working-papers/${wpId}/recalc`,
  remind: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/remind`,
  escalateToPartner: (pid: string) => `/api/projects/${pid}/workpapers/escalate-to-partner`,
  procedures: {
    list: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/procedures`,
    complete: (pid: string, wpId: string, procId: string) => `/api/projects/${pid}/workpapers/${wpId}/procedures/${procId}/complete`,
    trim: (pid: string, wpId: string, procId: string) => `/api/projects/${pid}/workpapers/${wpId}/procedures/${procId}/trim`,
    custom: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/procedures/custom`,
    copyFromPrior: (pid: string, wpId: string) => `/api/projects/${pid}/workpapers/${wpId}/procedures/copy-from-prior`,
  },
  crossCheck: {
    execute: (pid: string) => `/api/projects/${pid}/cross-check/execute`,
    results: (pid: string) => `/api/projects/${pid}/cross-check/results`,
    rules: (pid: string) => `/api/projects/${pid}/cross-check/rules`,
    customRule: (pid: string) => `/api/projects/${pid}/cross-check/rules/custom`,
  },
  prerequisiteStatus: (pid: string, wpCode: string) =>
    `/api/projects/${pid}/workpapers/prerequisite-status?wp_code=${encodeURIComponent(wpCode)}`,
  procedureStatus: (pid: string, wpId: string) =>
    `/api/projects/${pid}/working-papers/${wpId}/procedure-status`,
  procedureCategories: (wpId: string) => `/api/workpapers/${wpId}/procedure-categories`,
  aiReviewQuestions: (wpId: string) => `/api/workpapers/${wpId}/ai/review-questions`,
  aiReviewReply: (wpId: string) => `/api/workpapers/${wpId}/ai/review-reply`,
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
  stepMapping: (wpId: string) => `/api/workpapers/${wpId}/step-mapping`,
  mappingRules: '/api/workpapers/mapping-rules',
  mappingRulesCustom: '/api/workpapers/mapping-rules/custom',
  references: (wpId: string) => `/api/workpapers/${wpId}/references`,
  validationRules: (wpId: string) => `/api/workpapers/${wpId}/validation-rules`,
  staleChain: (wpId: string) => `/api/workpapers/${wpId}/stale-chain`,
  prefillContext: (pid: string) => `/api/projects/${pid}/workpapers/prefill-context`,
  dependencyGraph: '/api/workpapers/dependency-graph',
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

// ─── 底稿跨企业汇总 ─────────────────────────────────────────────────────────

export const workpaperSummary = {
  generate: (pid: string) => `/api/projects/${pid}/workpaper-summary`,
  export: (pid: string) => `/api/projects/${pid}/workpaper-summary/export`,
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

// ─── 审计程序 ───────────────────────────────────────────────────────────────

export const procedures = {
  list: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}`,
  /** @deprecated 已下线（410）→ 改用 procedureRowTasks.trimPreview/trimApply */
  trim: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}/trim`,
  init: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}/init`,
  custom: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}/custom`,
  /** @deprecated 已下线（410）→ 改用 procedureRowTasks.trimPreview/trimApply 构造 canonical entries */
  applyScheme: (pid: string, cycle: string) => `/api/projects/${pid}/procedures/${cycle}/apply-scheme`,
  /** @deprecated 已下线（410）→ 改用 workpaperLeads */
  assign: (pid: string) => `/api/projects/${pid}/procedures/assign`,
  /**
   * 裁剪三维判据上下文（只读，Task 9）：风险 / 重要性 / 数据存在性 + 完整性覆盖 + 底稿录入探测。
   *
   * 独立路径段 `procedure-scope`，避免被 `/procedures/{cycle}` 捕获。
   * 任一维度取数失败 → 该维度置 null/空 + `degradations` 记一条；`degradations` 是
   * 前端摘要降级标注的**唯一来源**（前端不再自行判断某维度是不是空的）。
   */
  trimDecisionContext: (pid: string) =>
    `/api/projects/${pid}/procedure-scope/trim-decision-context`,
} as const

// ─── 底稿主编（procedure-mainline-convergence 需求 5）────────────────────────

export const workpaperLeads = {
  /** PUT：批量设置/清除底稿主编（替代旧 procedures.assign） */
  set: (pid: string) => `/api/projects/${pid}/workpaper-leads`,
} as const

// ─── 程序行任务（procedure-delegation-notification / Task 12，V105 真源） ─────────

export const procedureRowTasks = {
  // 项目级"我的程序任务"分页查询（纯读）
  listByProject: (pid: string) => `/api/projects/${pid}/procedure-row-tasks`,
  // 跨项目"我的程序任务"分页查询（纯读）
  listMine: () => `/api/my/procedure-row-tasks`,
  // 单任务详情 + 深链定位 key（纯读）
  detail: (pid: string, taskId: string) => `/api/projects/${pid}/procedure-row-tasks/${taskId}`,
  // 单一状态机入口：状态转换（POST，携带 request_id + expected 版本）
  transition: (pid: string, taskId: string) => `/api/projects/${pid}/procedure-row-tasks/${taskId}/transitions`,
  // 两层裁剪 / 方案 preview-apply（Task 6，一次性 preview 凭证 + 真实 applied/unchanged/conflict）
  trimPreview: (pid: string) => `/api/projects/${pid}/procedure-trim/preview`,
  trimApply: (pid: string) => `/api/projects/${pid}/procedure-trim/apply`,
  trimSaveScheme: (pid: string) => `/api/projects/${pid}/procedure-trim/schemes`,
  trimRowNotApplicable: (pid: string, taskId: string) => `/api/projects/${pid}/procedure-trim/rows/${taskId}/not-applicable`,
  trimRowRestore: (pid: string, taskId: string) => `/api/projects/${pid}/procedure-trim/rows/${taskId}/restore`,
  /**
   * 驳回裁剪建议（procedure-trimming-and-delegation-intelligence Task 13）。
   *
   * 只写 `procedure_instances.suggestion_state.rejected`，**不动 status/skip_reason** ——
   * 驳回的语义是「不接受这个建议」，程序仍按原状保留，故不走 canonical trim。
   */
  trimRejectSuggestions: (pid: string) => `/api/projects/${pid}/procedure-trim/suggestions/reject`,
  /**
   * 完整性敏感清单的项目级覆盖（procedure-trimming-and-delegation-intelligence Task 14 / R5.5~R5.7）。
   *
   * 同一路径三个方法：`GET` 读回全部覆盖（含理由与最后修改留痕）、`PUT` 写一条
   * （`Y`/`N` 都算已表态，理由必填）、`DELETE {cycle}` 撤销该循环的覆盖使其退回平台默认。
   *
   * 🔴 撤销是 **DELETE 删行**而不是 `PUT` 写空 —— 读取侧以「该循环是否出现在返回里」
   * 区分「已表态」与「未覆盖」，写空串会让两态都表现为未覆盖却多一条脏记录。
   */
  trimCompletenessScope: (pid: string) => `/api/projects/${pid}/procedure-trim/completeness-scope`,
  trimCompletenessScopeItem: (pid: string, cycle: string) =>
    `/api/projects/${pid}/procedure-trim/completeness-scope/${encodeURIComponent(cycle)}`,
  /**
   * 附注反向联动（Task 21 / R13.1~R13.3）：程序整体裁剪 → 附注章节标「本期不适用」。
   *
   * `GET` 只读预览（要 `?year=`），`POST .../apply` 落库。
   *
   * 🔴 后端**只写** `disclosure_notes.is_empty`（附注侧既有的唯一不适用真源）+ 一条
   * `template_lineage` provenance 面包屑。不新建不适用字段、不删章节、不动
   * `table_data` —— 另建一套会让附注树标记与 Word 导出结果漂移。
   * 🔴 apply 请求体**只有 year**：标注哪些章节由后端按当下裁剪状态派生，不由前端
   * 传清单（传清单会与并发会话改过的裁剪状态脱节，把已恢复执行的循环标成不适用）。
   */
  trimNoteLinkage: (pid: string) => `/api/projects/${pid}/procedure-trim/note-linkage`,
  trimNoteLinkageApply: (pid: string) => `/api/projects/${pid}/procedure-trim/note-linkage/apply`,
  // 三粒度委派 preview-apply（Task 8，materialize 前置 + 一次性 preview 凭证）
  delegationPreview: (pid: string) => `/api/projects/${pid}/procedure-delegations/preview`,
  delegationApply: (pid: string) => `/api/projects/${pid}/procedure-delegations/apply`,
  // 成员负载批量视图（只读）：口径与 preview 的 membership_load.active_task_count 一致
  delegationMemberLoads: (pid: string) => `/api/projects/${pid}/procedure-delegations/member-loads`,
  // 显式物化 job（delegation preview 前置；job 失败不产生 preview）
  materialize: (pid: string) => `/api/projects/${pid}/procedure-row-tasks/materialize`,
  materializeJob: (pid: string) => `/api/projects/${pid}/procedure-row-tasks/materialize-jobs`,
  materializeJobStatus: (pid: string, jobId: string) => `/api/projects/${pid}/procedure-row-tasks/materialize-jobs/${jobId}`,
  // 程序行一级复核（Task 13，ReviewConversation + IssueTicket）
  conversation: (pid: string, taskId: string) => `/api/projects/${pid}/procedure-row-tasks/${taskId}/conversation`,
  messages: (pid: string, taskId: string) => `/api/projects/${pid}/procedure-row-tasks/${taskId}/messages`,
  closeIssue: (pid: string, taskId: string, issueId: string) => `/api/projects/${pid}/procedure-row-tasks/${taskId}/issues/${issueId}/close`,
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

// ─── 模板库管理 ─────────────────────────────────────────────────────────────

export const templateLibraryMgmt = {
  formulaCoverage: '/api/template-library-mgmt/formula-coverage',
  prefillFormulas: '/api/template-library-mgmt/prefill-formulas',
  crossWpReferences: '/api/template-library-mgmt/cross-wp-references',
  seedStatus: '/api/template-library-mgmt/seed-status',
  seedAll: '/api/template-library-mgmt/seed-all',
  versionInfo: '/api/template-library-mgmt/version-info',
  formulaAcnrMigration: '/api/template-library-mgmt/formula-acnr-migration',

  // ─── 模板覆盖层（spec excel-template-override-layer-and-onlyoffice-template-editor）──
  // 权威目录 backend/wp_templates/ 运行时只读；编辑产物落覆盖层并版本化。
  // 挂在 templateLibraryMgmt 下而不是新开一个导出对象 —— 后者要同步改 apiPaths/index.ts
  // 的三处 re-export 列表，那是三个并发会话都在改的文件。
  overrideResolution: (wpCode: string) =>
    `/api/wp-template-overrides/${encodeURIComponent(wpCode)}/resolution`,
  overrideVersions: (wpCode: string) =>
    `/api/wp-template-overrides/${encodeURIComponent(wpCode)}/versions`,
  overrideEditSession: (wpCode: string) =>
    `/api/wp-template-overrides/${encodeURIComponent(wpCode)}/edit-session`,
  overrideUpload: (wpCode: string) =>
    `/api/wp-template-overrides/${encodeURIComponent(wpCode)}/upload`,
  overridePromote: (wpCode: string, versionId: string) =>
    `/api/wp-template-overrides/${encodeURIComponent(wpCode)}/versions/${versionId}/promote`,
  overrideDeleteCurrent: (wpCode: string) =>
    `/api/wp-template-overrides/${encodeURIComponent(wpCode)}/current`,
} as const

// ─── 自定义模板 ─────────────────────────────────────────────────────────────

export const customTemplates = {
  list: '/api/custom-templates',
  detail: (id: string) => `/api/custom-templates/${id}`,
  validate: (id: string) => `/api/custom-templates/${id}/validate`,
  publish: (id: string) => `/api/custom-templates/${id}/publish`,
  copy: (id: string) => `/api/custom-templates/${id}/copy`,
} as const

// ─── 共享配置模板 ───────────────────────────────────────────────────────────

export const sharedConfig = {
  templates: '/api/shared-config/templates',
  detail: (id: string) => `/api/shared-config/templates/${id}`,
  apply: '/api/shared-config/apply',
  references: (pid: string) => `/api/shared-config/references/${pid}`,
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

// ─── 底稿 Job ───────────────────────────────────────────────────────────────

export const jobs = {
  status: (pid: string, jobId: string) => `/api/projects/${pid}/jobs/${jobId}`,
  retry: (pid: string, jobId: string) => `/api/projects/${pid}/jobs/${jobId}/retry`,
} as const
