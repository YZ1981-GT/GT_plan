/**
 * 母公司附注章节取数溯源（Task 13 前端消费方）。
 *
 * 后端 `disclosure_engine._attach_parent_source_meta` 在**表级** table_data 上落两个键：
 *
 * - `_parent_company_source`：三项溯源 `{source_project_name, source_company_code, source_scope}`
 * - `parent_project_missing`：`true` = 本项目未建母公司单体 ⇒ 金额留空（不是 0）
 *
 * 🔴 键名是**跨前后端契约**，单一真源在后端 `parent_company_note_sections.py` 的
 * `PARENT_SOURCE_META_KEY` / `PARENT_PROJECT_MISSING_KEY`；本文件的常量由
 * `parentCompanyNoteSource.spec.ts` 读那份 py 源码交叉锁死，改一侧必打红。
 *
 * 🔴 三态而非布尔（与平台「is_stale / pre_existing 一律三态」同族）：
 *   `none`（非母公司章，横幅不渲染）/ `missing`（母公司单体缺失，灰态提示）/
 *   `resolved`（已定位到来源项目，展示三项溯源）。
 *   把 `missing` 与 `none` 合并会让「未建母公司单体」静默无提示，用户看到空表
 *   会以为是自己没填。
 */

/** 后端 `PARENT_SOURCE_META_KEY` 的镜像（交叉锁死，勿手改）。 */
export const PARENT_SOURCE_META_KEY = '_parent_company_source'

/** 后端 `PARENT_PROJECT_MISSING_KEY` 的镜像（交叉锁死，勿手改）。 */
export const PARENT_PROJECT_MISSING_KEY = 'parent_project_missing'

/** 后端 `PARENT_SOURCE_META_KEYS` 的镜像（溯源三项，顺序即展示顺序）。 */
export const PARENT_SOURCE_META_FIELDS = [
  'source_project_name',
  'source_company_code',
  'source_scope',
] as const

export type ParentSourceState = 'none' | 'missing' | 'resolved'

export interface ParentCompanySourceView {
  /** 三态；`none` 时其余字段无意义，调用方据此决定是否渲染。 */
  state: ParentSourceState
  /** 来源项目名（母公司单体项目）。 */
  projectName: string | null
  /** 来源项目企业代码。 */
  companyCode: string | null
  /** 来源口径的中文标签；未定位到时为 null。 */
  scopeLabel: string | null
}

/** 口径英文值 → 中文标签（UI 全中文化铁律；未知值原样透出便于排查）。 */
export function parentScopeLabel(scope: unknown): string | null {
  if (scope === 'standalone') return '单体（母公司）'
  if (scope === 'consolidated') return '合并'
  if (typeof scope === 'string' && scope.trim()) return scope
  return null
}

/**
 * 从表级 table_data 抽出母公司取数溯源视图。
 *
 * 判定顺序：先看 `parent_project_missing`（缺失优先，此时 `source_scope` 后端置 null），
 * 再看 `_parent_company_source` 是否含至少一项非空。两个键都没有 → `none`。
 */
export function readParentCompanySource(table: unknown): ParentCompanySourceView {
  const blank: ParentCompanySourceView = {
    state: 'none',
    projectName: null,
    companyCode: null,
    scopeLabel: null,
  }
  if (!table || typeof table !== 'object') return blank
  const t = table as Record<string, unknown>

  const meta = t[PARENT_SOURCE_META_KEY]
  const m = meta && typeof meta === 'object' ? (meta as Record<string, unknown>) : null

  const missing =
    t[PARENT_PROJECT_MISSING_KEY] === true ||
    (m ? m[PARENT_PROJECT_MISSING_KEY] === true : false)

  const projectName = typeof m?.source_project_name === 'string' ? m.source_project_name : null
  const companyCode = typeof m?.source_company_code === 'string' ? m.source_company_code : null
  const scopeLabel = parentScopeLabel(m?.source_scope)

  if (missing) {
    return { state: 'missing', projectName, companyCode, scopeLabel: null }
  }
  if (m && (projectName || companyCode || scopeLabel)) {
    return { state: 'resolved', projectName, companyCode, scopeLabel }
  }
  return blank
}

/** 溯源横幅正文（`resolved` 态）。缺项按「—」占位，不隐藏整条。 */
export function parentCompanySourceSummary(view: ParentCompanySourceView): string {
  if (view.state !== 'resolved') return ''
  const name = view.projectName || '—'
  const code = view.companyCode || '—'
  const scope = view.scopeLabel || '—'
  return `本章数据取自母公司单体项目「${name}」（企业代码 ${code}，口径 ${scope}）`
}

/** 缺失态提示文案（与后端 INFO 日志同口径：合并项目尚未建单体是合法状态）。 */
export const PARENT_PROJECT_MISSING_TEXT =
  '本项目未建母公司单体，母公司附注金额留空（非零余额）。在同一企业代码、同一年度下新建单体口径项目后可自动取数。'
