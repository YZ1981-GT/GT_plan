/**
 * 合并页前端缓存键（spec consol-node-key-isolation-and-shared-context 任务 5.3，需求 4.5 / 5.4，设计 §七、P9）。
 *
 * 缓存键四维：project / year / nodeKey / report-or-template。
 * - 作用域键 scope = `${projectId}:${year}:${nodeKey}`，nodeKey 本身形如 `{企业代码}:{角色}`（内部含冒号）。
 * - 报表键 = `${scope}:${reportType}:${templateType}`（第四维 = 报表类型 + 模板口径）。
 * - 附注键 = `${scope}:notes:${templateType}`（第四维 = notes + 模板口径）。
 *
 * 精确清理（clearPrefix）：以 `${scope}:` 为前缀匹配，**尾部冒号是必需的身份边界**。
 * node_key 的角色是前缀族（`consol` 是 `consol_elim` 的前缀），若漏掉尾冒号，
 * 清 `A:consol` 会误伤同企业的 `A:consol_elim` 节点缓存。尾冒号保证
 * `5:2025:A:consol_elim:...` 不以 `5:2025:A:consol:` 开头（其后一字符是 `_` 而非 `:`）。
 * 该不变量由 consolCacheKeys.spec.ts 的正反双向用例守护，禁止去掉尾冒号。
 */

/** 可清理的报表类型（与报表 tab 口径一致）。 */
export const CLEARABLE_REPORT_TYPES = [
  'balance_sheet',
  'income_statement',
  'cash_flow_statement',
  'equity_statement',
  'cash_flow_supplement',
  'impairment_provision',
] as const

/** 模板口径（国企 / 上市）。 */
export const TEMPLATE_STANDARDS = ['soe', 'listed'] as const

/** 作用域键：project / year / nodeKey 三维身份。 */
export function cacheScopeKey(projectId: string | number, year: number, nodeKey: string): string {
  return `${projectId}:${year}:${nodeKey}`
}

/** 报表缓存键：scope + reportType + templateType（四维）。 */
export function reportCacheKey(
  projectId: string | number,
  year: number,
  nodeKey: string,
  reportType: string,
  templateType: string,
): string {
  return `${cacheScopeKey(projectId, year, nodeKey)}:${reportType}:${templateType}`
}

/** 附注缓存键：scope + notes + templateType（四维）。 */
export function noteCacheKey(
  projectId: string | number,
  year: number,
  nodeKey: string,
  templateType: string,
): string {
  return `${cacheScopeKey(projectId, year, nodeKey)}:notes:${templateType}`
}

/** 节点清理前缀：尾冒号是身份边界，不得去掉。 */
export function clearPrefix(projectId: string | number, year: number, nodeKey: string): string {
  return `${cacheScopeKey(projectId, year, nodeKey)}:`
}

/**
 * 精确清理指定节点缓存：仅删除属于该 (project, year, nodeKey) 作用域的键，
 * 不波及同企业其他角色节点、不波及其他项目/年度。原地修改传入的两个 Map。
 *
 * @param types 可选：缺省或含 `all_reports` ⇒ 清该节点全部报表；含 `notes` ⇒ 清该节点附注；
 *              否则按逐个报表类型 × 模板口径精确删除。
 */
export function clearNodeCache(
  reportCache: Map<string, unknown>,
  noteCache: Map<string, unknown>,
  projectId: string | number,
  year: number,
  nodeKey: string,
  types?: string[],
): void {
  const prefix = clearPrefix(projectId, year, nodeKey)

  if (!types || types.includes('all_reports')) {
    for (const key of [...reportCache.keys()]) {
      if (key.startsWith(prefix)) reportCache.delete(key)
    }
  } else {
    for (const t of types) {
      if ((CLEARABLE_REPORT_TYPES as readonly string[]).includes(t)) {
        for (const standard of TEMPLATE_STANDARDS) {
          reportCache.delete(`${prefix}${t}:${standard}`)
        }
      }
    }
  }

  if (!types || types.includes('notes')) {
    const notePrefix = `${prefix}notes:`
    for (const key of [...noteCache.keys()]) {
      if (key.startsWith(notePrefix)) noteCache.delete(key)
    }
  }
}
