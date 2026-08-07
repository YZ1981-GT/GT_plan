/**
 * 公式管理域 API 路径集中登记
 *
 * spec: formula-management-runtime-closure Task 14
 *   (Requirements 7.1, 7.2, 7.6 / Property 19)
 *
 * 🔴 **为什么要收敛**：公式端点散在 10 个后端 router，而前端 41 个 distinct URL
 * 里只有 14 个进了 `apiPaths`（`accounting.formula` / `accounting.formulaAuditLog`
 * / `report.*` / `system.linkageBus` / `workpaper.*`），其余 **27 个**以模板字符串
 * 硬编码在 18 个组件/composable 里。后果已实证：`useFormulaStatus.ts` 长期请求两个
 * **后端零命中**的端点（`/api/projects/{pid}/workpapers/{wpId}/formulas` 与
 * `.../prefill`），被 `catch` 吞成空结果，四层验证全绿 —— 改一个 prefix 要手工扫全仓。
 *
 * 🔴 **纯搬迁：URL 字符串逐字不变**（Task 14 红线）。任何"顺手规范化"
 * （补/删尾斜杠、统一 encodeURIComponent、合并相似路径）都属超范围，
 * 会把「零行为变化的搬迁」变成「需要回归的改动」。
 *
 * **范围**：`components/formula/**` 与 `composables/useFormula*.ts` 下的 17 个
 * distinct URL。以下**显式范围外**（R7.6，属各循环 spec）：
 * 6 个 `gN/hN/validate-formulas`（`/api/workpapers/{wpId}/{g8,g9,g10,g11,h10,l4,l5}/validate-formulas`）。
 *
 * **已在别处登记、本文件不重复**（避免双真源）：
 * - `accounting.formula.execute` / `.batchExecute`
 * - `accounting.formulaAuditLog.{list,create,rollback}`
 * - `report.*`（disclosure-notes 的 formulas / apply-formulas / clear-formulas 等）
 * - `workpaper.templateLibraryMgmt.*`（prefill-formulas / formula-coverage 等）
 */

// ─── 底稿公式（wp_formula 表，权威存储） ──────────────────────────────────────

export const wpFormula = {
  /** GET / PUT `/api/workpapers/{wp_id}/formulas` — 列出 / upsert 底稿公式 */
  list: (wpId: string) => `/api/workpapers/${wpId}/formulas`,
  /** PUT 同上（语义区分，便于阅读调用点） */
  upsert: (wpId: string) => `/api/workpapers/${wpId}/formulas`,
  /** DELETE `/api/workpapers/{wp_id}/formulas/{formula_id}` — 删除单条 */
  remove: (wpId: string, formulaId: string) =>
    `/api/workpapers/${wpId}/formulas/${formulaId}`,
} as const

// ─── 用户自定义公式（Wave 3 已收敛进 wp_formula 表，端点形状不变） ────────────

export const wpUserFormula = {
  /** GET / PUT `/api/workpapers/{wp_id}/user-formulas` */
  list: (wpId: string) => `/api/workpapers/${wpId}/user-formulas`,
  /** PUT 同上 */
  batchUpdate: (wpId: string) => `/api/workpapers/${wpId}/user-formulas`,
  /**
   * DELETE `/api/workpapers/{wp_id}/user-formulas/{cell_key}` — 恢复预设。
   *
   * 🔴 `cellKey` 形如 `sheet!A1`，**必须由调用方 `encodeURIComponent`**
   * （后端路由是 `{cell_key:path}`）。搬迁前两个调用点都是这么做的，
   * 此处保持「调用方编码」不变 —— 在本函数内编码会导致已编码的调用点二次编码。
   */
  restorePreset: (wpId: string, encodedCellKey: string) =>
    `/api/workpapers/${wpId}/user-formulas/${encodedCellKey}`,
  /** POST `/api/workpapers/{wp_id}/validate-formula` — 语法校验 + 预览 */
  validate: (wpId: string) => `/api/workpapers/${wpId}/validate-formula`,
} as const

// ─── 项目级公式（勾稽 / 自动生成） ────────────────────────────────────────────

export const projectFormula = {
  /**
   * GET `/api/projects/{project_id}/formula/report-cross-check?year=` —
   * 执行 7 条 logic_check 报表勾稽，返回 Issue_List。
   *
   * 搬迁前有**两个字面量副本**（`FormulaManagerDialog.vue` 用 `props.projectId`、
   * `useFormulaIssueHint.ts` 用 `projectId`），Task 14 收敛为本函数。
   */
  reportCrossCheck: (projectId: string) =>
    `/api/projects/${projectId}/formula/report-cross-check`,
  /**
   * POST `/api/projects/{project_id}/formula/auto-generate`
   *
   * 🔴 **后端未实现**（`auto_generate` 全后端只命中合并/CFS/科目映射三处）——
   * 这是**有意的前瞻占位**：`FormulaManagerDialog.vue` 的 catch 里显式判
   * `status === 404` → 提示「自动生成公式功能尚未启用…」。
   * 平台守卫 `formulaEndpointExistence.spec.ts` 已把它登记为唯一豁免条目
   * （含「后端未实现 + 前端有 404 降级」两个判据）。**删掉这条降级提示前先读那份守卫**。
   */
  autoGenerate: (projectId: string) =>
    `/api/projects/${projectId}/formula/auto-generate`,
} as const

// ─── 公式作用域目录（ACNR 地址目录） ──────────────────────────────────────────

export const formulaScope = {
  /** GET `/api/formula-scope/{project_id}/formulas?year=&domain=` */
  list: (projectId: string) => `/api/formula-scope/${projectId}/formulas`,
} as const

// ─── 公式预设库导入导出 ───────────────────────────────────────────────────────

/**
 * `/api/formula-management/import-export` 的 BASE。
 *
 * 🔴 它**本身不是完整端点**，真实请求是 `${BASE}/export-template` 等三个子路径。
 * 平台守卫按「后端某路由以该归一路径 + `/` 开头」判定其合法性（否则会误报未命中）。
 */
const IMPORT_EXPORT_BASE = '/api/formula-management/import-export'

export const formulaPresets = {
  /** POST `${BASE}/export-template` — 导出模板（首区块=编报说明） */
  exportTemplate: `${IMPORT_EXPORT_BASE}/export-template`,
  /** POST `${BASE}/export-data?page_key=` — 导出当前页面/模块已有公式 */
  exportData: `${IMPORT_EXPORT_BASE}/export-data`,
  /** POST `${BASE}/import-data` (multipart) — 上传 xlsx 逐条 full_resolve 校验 */
  importData: `${IMPORT_EXPORT_BASE}/import-data`,
  /** GET `/api/formula-management/reporting-instructions` */
  reportingInstructions: '/api/formula-management/reporting-instructions',
  /** GET `/api/formula-management/presets/inventory` */
  inventory: '/api/formula-management/presets/inventory',
  /** GET `/api/formula-management/presets/page?page_key=` */
  page: '/api/formula-management/presets/page',
  /** POST `/api/formula-management/presets/custom` */
  custom: '/api/formula-management/presets/custom',
  /** BASE（供需要自行拼接子路径的场景；新增子路径请在本对象登记而非拼字符串） */
  importExportBase: IMPORT_EXPORT_BASE,
} as const

// ─── 报表配置侧的公式（TB 明细公式） ─────────────────────────────────────────

export const reportConfigFormula = {
  /** GET / PUT `/api/report-config/tb-detail-formulas/{project_id}` */
  tbDetail: (projectId: string) =>
    `/api/report-config/tb-detail-formulas/${projectId}`,
} as const

// ─── 草稿刷新 / 刷新作用域（公式运行时协调器的两个前端入口） ──────────────────

export const draftRefresh = {
  /** GET `/api/workpapers/refresh-scopes` — 列出可刷新作用域（含 stale 计数） */
  scopes: '/api/workpapers/refresh-scopes',
  /** POST `/api/workpapers/draft-refresh` — 按作用域批量重算（返回 run_id + warnings） */
  run: '/api/workpapers/draft-refresh',
  /**
   * POST `/api/workpapers/draft-refresh/{run_id}/rollback` — 回滚一次刷新。
   *
   * `run_id` 由 `run` 的响应体给出，调用方直接透传（不需 encodeURIComponent，
   * 后端是 uuid 形态路径参数）。
   */
  rollback: (runId: string) => `/api/workpapers/draft-refresh/${runId}/rollback`,
} as const

// ─── 附注公式（章节级） ───────────────────────────────────────────────────────

export const noteFormula = {
  /** GET / PUT `/api/disclosure-notes/{pid}/{year}/{note_section}/formulas` */
  list: (projectId: string, year: number | string, noteSection: string) =>
    `/api/disclosure-notes/${projectId}/${year}/${noteSection}/formulas`,
  /** POST `/api/disclosure-notes/{pid}/{year}/{note_section}/apply-formulas` */
  apply: (projectId: string, year: number | string, noteSection: string) =>
    `/api/disclosure-notes/${projectId}/${year}/${noteSection}/apply-formulas`,
} as const

/** 公式域聚合（便于 `import { formulaApi } from '@/services/apiPaths/formula'`） */
export const formulaApi = {
  wpFormula,
  wpUserFormula,
  projectFormula,
  formulaScope,
  formulaPresets,
  reportConfigFormula,
  draftRefresh,
  noteFormula,
} as const
