/**
 * 附注行级合并 fail-closed 的提示文案（单一真源）。
 *
 * 后端 `sync-from-workpaper` 在段边界解析失败时**跳过该表写入**（fail closed），
 * 并返回：
 * - `row_scope_unresolved: string[]` —— 哪几张表没同步成功
 * - `row_scope_unresolved_reasons: Record<string, string>` —— **为什么**（逐表）
 *
 * 🔴 只报表名说不出为什么。三种成因的修法完全不同：
 *   1. 项目适用准则没填 ⇒ 定不了模板变体（去项目设置改）
 *   2. 底稿声明的表名与附注模板不一致（改底稿或改模板）
 *   3. 附注模板缺段首行标记 `report_row_code`（跑对应的 `fix_note_*` 幂等脚本）
 * 而审计师看不到后端日志 —— 所以原因必须显示在界面上。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
 *       Requirements 11.3 / Property 40
 */

/** 后端未给原因时的兜底（不许静默省略 —— 那等于回到「只知道失败」）。 */
function fallbackReason(table: string): string {
  return `${table}：段边界解析失败（后端未给出原因，请联系管理员查服务端日志）`
}

/**
 * 拼装提示文案。**无失败时返回 `null`**（调用方据此决定是否弹提示）。
 *
 * @param what 业务说法，如「外币货币性项目」「受限资产」
 * @param unresolved 后端 `row_scope_unresolved`
 * @param reasons 后端 `row_scope_unresolved_reasons`
 */
export function rowScopeFailureMessage(
  what: string,
  unresolved?: string[] | null,
  reasons?: Record<string, string> | null,
): string | null {
  const tables = (unresolved || []).filter((t) => typeof t === 'string' && t)
  if (!tables.length) return null
  const map = reasons || {}
  const detail = tables.map((t) => map[t] || fallbackReason(t))
  return `${what}未能同步：${detail.join('；')}`
}
