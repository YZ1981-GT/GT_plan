/**
 * resolveLinkageRoute — 解析 LinkageContract 为可跳转路由
 *
 * P0 增强版：
 * - 支持 workpaper (wp_code/wp_id), report (row_code), note (section/cell)
 * - 支持 trial_balance, adjustment, ledger
 * - wp_code 通过 API 解析为 wp_id
 */
import { api } from '@/services/apiProxy'
import type { LinkageContract } from '@/types/linkageContract'

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * 解析 LinkageContract 为前端可跳转路由。
 *
 * @param contract - 联动契约
 * @param projectId - 当前项目 ID
 * @returns 解析后的路由字符串，或 null（无法解析）
 */
export async function resolveLinkageRoute(
  contract: LinkageContract,
  projectId: string,
): Promise<string | null> {
  // 优先使用预计算路由
  if (contract.route) return contract.route

  const { target_type, target_id, target_cell } = contract

  switch (target_type) {
    case 'workpaper': {
      if (UUID_PATTERN.test(target_id)) {
        return `/projects/${projectId}/workpapers/${target_id}`
      }
      // wp_code → wp_id 通过 API 解析
      try {
        const data: any = await api.get(
          `/api/projects/${projectId}/wp-index/by-code/${target_id}`,
        )
        const wpId = data?.working_paper_id || data?.wp_id || data?.id
        if (wpId) return `/projects/${projectId}/workpapers/${wpId}`
      } catch {
        /* wp_code not found */
      }
      return null
    }

    case 'report':
      return `/projects/${projectId}/reports?highlight=${target_id}`

    case 'note': {
      let route = `/projects/${projectId}/disclosure-notes?section=${target_id}`
      if (target_cell) {
        route += `&cell=${target_cell}`
      }
      return route
    }

    case 'trial_balance':
      return `/projects/${projectId}/trial-balance?highlight=${target_id}`

    case 'adjustment':
      return `/projects/${projectId}/adjustments?highlight=${target_id}`

    case 'ledger':
      return `/projects/${projectId}/ledger?account=${target_id}`

    default:
      return null
  }
}
