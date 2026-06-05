/**
 * 项目显示名称工具函数
 * 根据 report_scope 和同企业同年度项目共存情况，为项目名追加后缀
 *
 * 规则（Property 9）：
 * - consolidated → 追加"（合并）"
 * - standalone 且同 company_code+audit_year 下存在非删除的 consolidated 项目 → 追加"（母公司）"
 * - 其它 → 无后缀
 */

export interface ProjectForDisplay {
  name?: string | null
  client_name?: string | null
  company_code?: string | null
  audit_year?: number | null
  report_scope?: string | null
  is_deleted?: boolean
}

/**
 * 预计算合并项目 key 集合，供 getProjectDisplayName 使用
 * 调用方在项目列表变化时调用一次，后续每行 O(1) lookup
 */
export function buildConsolidatedKeySet(allProjects: ProjectForDisplay[]): Set<string> {
  const keys = new Set<string>()
  for (const p of allProjects) {
    if (
      !p.is_deleted &&
      p.report_scope === 'consolidated' &&
      p.company_code != null &&
      p.audit_year != null
    ) {
      keys.add(`${p.company_code}:${p.audit_year}`)
    }
  }
  return keys
}

/**
 * 获取项目显示名称（含后缀）
 * @param project 当前项目
 * @param allProjects 当前可见的全部项目列表（用于判断母公司后缀）
 * @param consolidatedKeys 可选预计算的合并项目 key 集合（O(1) lookup），不传则内部 O(N) 扫描
 */
export function getProjectDisplayName(
  project: ProjectForDisplay,
  allProjects: ProjectForDisplay[],
  consolidatedKeys?: Set<string>
): string {
  const baseName = project.name || project.client_name || ''

  if (project.report_scope === 'consolidated') {
    return baseName + '（合并）'
  }

  if (project.report_scope === 'standalone') {
    if (project.company_code != null && project.audit_year != null) {
      const key = `${project.company_code}:${project.audit_year}`
      const hasConsolidated = consolidatedKeys
        ? consolidatedKeys.has(key)
        : allProjects.some(
            (p) =>
              p !== project &&
              !p.is_deleted &&
              p.report_scope === 'consolidated' &&
              p.company_code === project.company_code &&
              p.audit_year === project.audit_year
          )
      if (hasConsolidated) {
        return baseName + '（母公司）'
      }
    }
  }

  return baseName
}
