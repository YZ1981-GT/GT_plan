/**
 * API 路径 — 试算表、调整分录、重要性、未更正错报
 */

// ─── 试算表 ─────────────────────────────────────────────────────────────────

export const trialBalance = {
  get: (pid: string) => `/api/projects/${pid}/trial-balance`,
  recalc: (pid: string) => `/api/projects/${pid}/trial-balance/recalc`,
  consistencyCheck: (pid: string) => `/api/projects/${pid}/trial-balance/consistency-check`,
  export: (pid: string) => `/api/projects/${pid}/trial-balance/export`,
  summaryWithAdjustments: (pid: string) => `/api/projects/${pid}/trial-balance/summary-with-adjustments`,
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
  exportTemplate: (pid: string) => `/api/projects/${pid}/adjustments/export-template`,
  convertToMisstatement: (pid: string, groupId: string) => `/api/projects/${pid}/adjustments/${groupId}/convert-to-misstatement`,
  /** AdjustmentImpactPreview 实时影响预览（POST line_items[]） */
  previewImpact: (pid: string) => `/api/projects/${pid}/adjustments/preview-impact`,
  /** 底稿调整汇聚到集中登记（workpaper-adjustment-centralization） */
  syncFromWorkpaper: (pid: string) => `/api/projects/${pid}/adjustments/sync-from-workpaper`,
  /** 按 source_ref 回流集中登记复核状态 */
  bySourceRef: (pid: string) => `/api/projects/${pid}/adjustments/by-source-ref`,
  // ── 协作接力（adjustment-collaboration-and-propagation） ──
  collabAssign: (pid: string, groupId: string) => `/api/projects/${pid}/adjustments/${groupId}/collaboration/assign`,
  collabByGroup: (pid: string, groupId: string) => `/api/projects/${pid}/adjustments/${groupId}/collaboration`,
  collabInbox: (pid: string) => `/api/projects/${pid}/adjustments/collaboration/inbox`,
  collabAcknowledge: (pid: string, cid: string) => `/api/projects/${pid}/adjustments/collaboration/${cid}/acknowledge`,
  collabContribute: (pid: string, cid: string) => `/api/projects/${pid}/adjustments/collaboration/${cid}/contribute`,
  collabConfirm: (pid: string, cid: string) => `/api/projects/${pid}/adjustments/collaboration/${cid}/confirm`,
  collabReject: (pid: string, cid: string) => `/api/projects/${pid}/adjustments/collaboration/${cid}/reject`,
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
  recheckThreshold: (pid: string) => `/api/projects/${pid}/misstatements/recheck-threshold`,
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

// ─── 账龄分析 ───────────────────────────────────────────────────────────────

export const aging = {
  presets: '/api/aging/presets',
  config: (pid: string) => `/api/projects/${pid}/aging/config`,
  calculate: (pid: string) => `/api/projects/${pid}/aging/calculate`,
} as const

// ─── 穿透查询 ───────────────────────────────────────────────────────────────

export const ledger = {
  balance: (pid: string) => `/api/projects/${pid}/ledger/balance`,
  entries: (pid: string, code: string) => `/api/projects/${pid}/ledger/entries/${encodeURIComponent(code)}`,
  openingBalance: (pid: string, code: string) => `/api/projects/${pid}/ledger/opening-balance/${encodeURIComponent(code)}`,
  voucher: (pid: string, voucherNo: string) => `/api/projects/${pid}/ledger/voucher/${encodeURIComponent(voucherNo)}`,
  // 挂凭到底稿（序时账 ↔ 底稿凭证检查联动）
  sampleVoucher: (pid: string) => `/api/projects/${pid}/ledger/sample-voucher`,
  sampledVouchers: (pid: string) => `/api/projects/${pid}/ledger/sampled-vouchers`,
  sampledVoucherDelete: (pid: string, id: string) => `/api/projects/${pid}/ledger/sampled-vouchers/${encodeURIComponent(id)}`,
  years: (pid: string) => `/api/projects/${pid}/ledger/years`,
  validate: (pid: string) => `/api/projects/${pid}/ledger/validate`,
  smartPreview: (pid: string) => `/api/projects/${pid}/ledger/smart-preview`,
  smartImport: (pid: string) => `/api/projects/${pid}/ledger/smart-import`,
  auxBalance: (pid: string, code: string) => `/api/projects/${pid}/ledger/aux-balance/${code}`,
  auxBalanceDetail: (pid: string) => `/api/projects/${pid}/ledger/aux-balance-detail`,
  auxBalanceSummary: (pid: string) => `/api/projects/${pid}/ledger/aux-balance-summary`,
  auxBalancePaged: (pid: string) => `/api/projects/${pid}/ledger/aux-balance-paged`,
  auxEntries: (pid: string, code: string) => `/api/projects/${pid}/ledger/aux-entries/${code}`,
  auxByTriplet: (pid: string) => `/api/projects/${pid}/ledger/aux/by-triplet`,
  auxSummary: (pid: string) => `/api/projects/${pid}/ledger/aux-summary`,
  balanceTree: (pid: string) => `/api/projects/${pid}/ledger/balance-tree`,
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
    v2Detect: (pid: string) => `/api/projects/${pid}/ledger-import/detect`,
    v2Submit: (pid: string) => `/api/projects/${pid}/ledger-import/submit`,
    v2Stream: (pid: string, jobId: string) => `/api/projects/${pid}/ledger-import/jobs/${jobId}/stream`,
    v2Diagnostics: (pid: string, jobId: string) => `/api/projects/${pid}/ledger-import/jobs/${jobId}/diagnostics`,
    v2Cancel: (pid: string, jobId: string) => `/api/projects/${pid}/ledger-import/jobs/${jobId}/cancel`,
    v2Retry: (pid: string, jobId: string) => `/api/projects/${pid}/ledger-import/jobs/${jobId}/retry`,
    v2Resume: (pid: string, jobId: string) => `/api/projects/${pid}/ledger-import/jobs/${jobId}/resume`,
    v2Takeover: (pid: string, jobId: string) => `/api/projects/${pid}/ledger-import/jobs/${jobId}/takeover`,
    activeJob: (pid: string) => `/api/projects/${pid}/ledger-import/active-job`,
    datasetsHistory: (pid: string) => `/api/projects/${pid}/ledger-import/datasets/history`,
    datasetForceUnbind: (pid: string, dsId: string) => `/api/projects/${pid}/ledger-import/datasets/${dsId}/force-unbind`,
    rawExtraFields: (pid: string) => `/api/projects/${pid}/ledger/raw-extra-fields`,
  },
  data: {
    summary: (pid: string) => `/api/projects/${pid}/ledger-data/summary`,
    delete: (pid: string) => `/api/projects/${pid}/ledger-data`,
    incrementalDetect: (pid: string) => `/api/projects/${pid}/ledger-data/incremental/detect`,
    incrementalApply: (pid: string) => `/api/projects/${pid}/ledger-data/incremental/apply`,
    trash: (pid: string) => `/api/projects/${pid}/ledger-data/trash`,
    restore: (pid: string) => `/api/projects/${pid}/ledger-data/restore`,
    dedup: (pid: string) => `/api/projects/${pid}/ledger-data/dedup`,
  },
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
  fixBadDebt: (pid: string) => `/api/projects/${pid}/report-line-mapping/fix-bad-debt`,
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

// ─── 账表导入校验规则 ───────────────────────────────────────────────────────

export const ledgerImportValidationRules = {
  list: '/api/ledger-import/validation-rules',
  detail: (code: string) => `/api/ledger-import/validation-rules/${code}`,
} as const

// ─── T型账户 ────────────────────────────────────────────────────────────────

export const tAccounts = {
  list: (pid: string) => `/api/projects/${pid}/t-accounts`,
  detail: (pid: string, id: string) => `/api/projects/${pid}/t-accounts/${id}`,
  entries: (pid: string, id: string) => `/api/projects/${pid}/t-accounts/${id}/entries`,
  calculate: (pid: string, id: string) => `/api/projects/${pid}/t-accounts/${id}/calculate`,
} as const

// ─── 公式 ───────────────────────────────────────────────────────────────────

export const formula = {
  execute: '/api/formula/execute',
  batchExecute: '/api/formula/batch-execute',
} as const

// ─── 公式审计日志（变更时间线） ──────────────────────────────────────────────

export const formulaAuditLog = {
  /** GET /api/formula-audit-log/{project_id}/{year}?module=&row_code=&limit= */
  list: (pid: string, year: number) => `/api/formula-audit-log/${pid}/${year}`,
  /** POST /api/formula-audit-log/{project_id}/{year} — 记录一条日志 */
  create: (pid: string, year: number) => `/api/formula-audit-log/${pid}/${year}`,
  /** POST /api/formula-audit-log/{project_id}/{year}/rollback — 一键回滚 */
  rollback: (pid: string, year: number) => `/api/formula-audit-log/${pid}/${year}/rollback`,
} as const

// ─── 数据校验 ───────────────────────────────────────────────────────────────

export const dataValidation = {
  run: (pid: string) => `/api/projects/${pid}/data-validation`,
  fix: (pid: string) => `/api/projects/${pid}/data-validation/fix`,
  export: (pid: string) => `/api/projects/${pid}/data-validation/export`,
} as const

// ─── 精细化检查 ─────────────────────────────────────────────────────────────

export const fineChecks = {
  summary: (pid: string) => `/api/projects/${pid}/fine-checks/summary`,
} as const

// ─── 审计检查复核（audit-check-review-gate-hardening） ────────────────────────

export const auditChecks = {
  /** 合并后的统一检查项 + 新鲜度 + 项目汇总（升级版，替代 fineChecks.summary） */
  summary: (pid: string) => `/api/projects/${pid}/audit-checks/summary`,
  /** 主动触发审计检查重算（body 可选 { wp_id } 单张，不传重算项目全部） */
  recompute: (pid: string) => `/api/projects/${pid}/audit-checks/recompute`,
  /** 复核签认（POST 记录一次 / GET 读最近一次；只提示不阻断） */
  signoff: (pid: string) => `/api/projects/${pid}/audit-checks/signoff`,
  /** 导出审计检查结果为 xlsx（RFC5987 中文名，留痕） */
  export: (pid: string) => `/api/projects/${pid}/audit-checks/export`,
} as const
