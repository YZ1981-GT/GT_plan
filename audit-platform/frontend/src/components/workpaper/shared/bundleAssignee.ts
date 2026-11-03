import type { WpIndexItem } from '@/services/workpaperApi'

/** S32–S35 bundle 页签展示所需的最小负责人信息。 */
export interface BundleAssignee {
  staffId: string
  displayName: string
}

const BUNDLE_CODE = /^S(?:32|33|34|35)-\d+/

/**
 * 从 wp_index 的只读 JOIN 结果构造负责人映射。
 * 仅接收已经生成的 S32–S35 子底稿；姓名缺失时依次退回用户名和 ID 前八位。
 */
export function buildBundleAssigneeMap(
  items: ReadonlyArray<Partial<WpIndexItem>>,
): Record<string, BundleAssignee> {
  const out: Record<string, BundleAssignee> = {}
  for (const item of items) {
    const code = String(item.wp_code || '')
    const staffId = String(item.assigned_to || '')
    if (!BUNDLE_CODE.test(code) || !item.wp_id || !staffId) continue
    const name = String(item.assigned_to_name || '').trim()
    const username = String(item.assigned_to_username || '').trim()
    const displayName = name || username || staffId.slice(0, 8)
    out[code] = { staffId, displayName }
  }
  return out
}
