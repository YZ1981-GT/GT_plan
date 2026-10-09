/**
 * 合并页报表/附注缓存键。
 *
 * 缓存必须同时绑定项目、有效年度和企业树 node_key；同一企业出现在
 * 合并户、母公司户等不同角色时，不能因为 company_code 相同而共享结果。
 */

export function cacheScopeKey(projectId: string, year: number, nodeKey: string): string {
  return `${projectId}|${year}|${nodeKey}`
}

export function reportCacheKey(
  projectId: string,
  year: number,
  nodeKey: string,
  reportType: string,
  templateType: string,
): string {
  return `${cacheScopeKey(projectId, year, nodeKey)}|report|${reportType}|${templateType}`
}

export function noteCacheKey(
  projectId: string,
  year: number,
  nodeKey: string,
  templateType: string,
): string {
  return `${cacheScopeKey(projectId, year, nodeKey)}|note|${templateType}`
}

/**
 * 只清理指定节点的缓存。
 *
 * types 与刷新事件的类型保持一致：all_reports、具体报表类型、notes。
 * 未指定 types 时清理当前节点的报表和附注缓存；worksheet 等类型不影响
 * 目前仍是项目/年度级的工作底稿缓存。
 */
export function clearEntityCache(
  reportCache: Map<string, unknown>,
  noteCache: Map<string, unknown>,
  projectId: string,
  year: number,
  nodeKey: string,
  types?: string[],
): void {
  const scope = cacheScopeKey(projectId, year, nodeKey)
  const scopePrefix = `${scope}|`
  const requested = new Set(types || [])
  const clearAllReports = !types?.length || requested.has('all_reports')
  const clearNotes = !types?.length || requested.has('notes')
  const reportTypes = new Set(
    [...requested].filter((type) => type !== 'all_reports' && type !== 'notes' && type !== 'worksheet'),
  )

  if (clearAllReports || reportTypes.size) {
    for (const key of [...reportCache.keys()]) {
      if (!key.startsWith(`${scopePrefix}report|`)) continue
      if (clearAllReports || [...reportTypes].some((type) => key.startsWith(`${scopePrefix}report|${type}|`))) {
        reportCache.delete(key)
      }
    }
  }

  if (clearNotes) {
    for (const key of [...noteCache.keys()]) {
      if (key.startsWith(`${scopePrefix}note|`)) noteCache.delete(key)
    }
  }
}
