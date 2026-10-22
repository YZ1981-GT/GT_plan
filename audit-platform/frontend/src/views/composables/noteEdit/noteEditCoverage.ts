/**
 * noteEditCoverage — 覆盖集合（方法 + 路径模板）与章节拖拽排序路径
 *
 * 前端打包不能引用后端目录，本文件是 backend/data/authz/note_write_inventory.json
 * 覆盖集合的抄录。vitest 读该 JSON 逐条比对（多一条、少一条都打红）。
 *
 * Feature: partner-manager-edit-permission
 * Requirements: 1.9, 10.10
 */

// ── 类型 ─────────────────────────────────────────────────────────────────────

export interface CoverageEntry {
  /** HTTP 方法（大写） */
  method: string
  /** 路径模板（路径参数用 {} 占位，与 backend 清册格式一致） */
  pathTemplate: string
}

// ── 覆盖集合 ─────────────────────────────────────────────────────────────────

/**
 * 附注编辑门禁覆盖集合：category ∈ {E, I} 且 target_gate.kind == 'note_edit_gate'
 * 的端点。请求级守卫用它判断一个请求是否应被拦截。
 *
 * 更新步骤：重新生成 note_write_inventory.json 后抄录。
 */
export const COVERAGE_SET: readonly CoverageEntry[] = [
  { method: 'DELETE', pathTemplate: '/api/disclosure-notes/{}/{}/sections/{}' },
  { method: 'DELETE', pathTemplate: '/api/projects/{}/note-content-templates/{}' },
  { method: 'PATCH', pathTemplate: '/api/disclosure-notes/{}/{}/restore/{}' },
  { method: 'PATCH', pathTemplate: '/api/disclosure-notes/{}/{}/sections/{}' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/generate' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/auto-trim' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/offline-import/execute' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/pull-from-workpapers' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/refresh-all-bindings' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/refresh-from-workpapers' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/validate' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/{}/toggle-mode' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/{}/apply-formulas' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/{}/clear-formulas' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/{}/refresh-from-workpaper' },
  { method: 'POST', pathTemplate: '/api/disclosure-notes/{}/{}/{}/restore-auto' },
  { method: 'POST', pathTemplate: '/api/projects/{}/apply-group-baseline' },
  { method: 'POST', pathTemplate: '/api/projects/{}/data-lock/snapshot' },
  { method: 'POST', pathTemplate: '/api/projects/{}/disclosure-note-import/parse-knowledge' },
  { method: 'POST', pathTemplate: '/api/projects/{}/disclosure-note-import/parse-upload' },
  { method: 'POST', pathTemplate: '/api/projects/{}/disclosure-note-text-batch/apply' },
  { method: 'POST', pathTemplate: '/api/projects/{}/disclosure-note-text-batch/preview' },
  { method: 'POST', pathTemplate: '/api/projects/{}/note-content-templates' },
  { method: 'POST', pathTemplate: '/api/projects/{}/note-content-templates/snapshot-preview' },
  { method: 'POST', pathTemplate: '/api/projects/{}/note-template/restore' },
  { method: 'POST', pathTemplate: '/api/projects/{}/note-template/save' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/cross-references/update' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/custom-sections/apply-template' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/custom-sections/create' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/custom-sections/save-as-template' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/group-template/detach' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/group-template/save' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/import-prior-year' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/inherit-prior-year' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/locks/acquire' },
  { method: 'POST', pathTemplate: '/api/projects/{}/notes/locks/heartbeat' },
  { method: 'PUT', pathTemplate: '/api/disclosure-notes/findings/{}/confirm' },
  { method: 'PUT', pathTemplate: '/api/disclosure-notes/{}' },
  { method: 'PUT', pathTemplate: '/api/disclosure-notes/{}/sections/trim' },
  { method: 'PUT', pathTemplate: '/api/disclosure-notes/{}/wp-mapping' },
  { method: 'PUT', pathTemplate: '/api/disclosure-notes/{}/{}/{}/formulas' },
] as const

/**
 * 章节拖拽排序路径（死链但纳入守卫拦截范围，需求 10.10）
 */
export const DRAG_SORT_PATH: CoverageEntry = {
  method: 'PUT',
  pathTemplate: '/api/disclosure-notes/{}/{}/sections/{}/move',
}

// ── 匹配函数 ─────────────────────────────────────────────────────────────────

/**
 * 判断给定的 (method, url) 是否命中覆盖集合或拖拽排序路径。
 * method 大小写不敏感；url 只取路径部分（去掉 query string）；
 * 路径参数段（模板里的 {}）匹配任一段。
 */
export function matchesCoverage(method: string, url: string): boolean {
  const upperMethod = method.toUpperCase()
  const path = stripQuery(url)

  for (const entry of COVERAGE_SET) {
    if (upperMethod === entry.method && matchPath(path, entry.pathTemplate)) {
      return true
    }
  }

  if (upperMethod === DRAG_SORT_PATH.method && matchPath(path, DRAG_SORT_PATH.pathTemplate)) {
    return true
  }

  return false
}

// ── 内部辅助 ─────────────────────────────────────────────────────────────────

function stripQuery(url: string): string {
  const idx = url.indexOf('?')
  return idx >= 0 ? url.substring(0, idx) : url
}

function matchPath(actualPath: string, template: string): boolean {
  const actualSegments = actualPath.split('/').filter(Boolean)
  const templateSegments = template.split('/').filter(Boolean)

  if (actualSegments.length !== templateSegments.length) return false

  for (let i = 0; i < templateSegments.length; i++) {
    const ts = templateSegments[i]
    // {} 或 {param} 或 {param:path} — 匹配任一段
    if (ts.startsWith('{') && ts.endsWith('}')) continue
    // 精确匹配（含 encode 后的段）
    if (decodeURIComponent(actualSegments[i]) !== ts && actualSegments[i] !== ts) return false
  }
  return true
}
