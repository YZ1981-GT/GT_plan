/**
 * fetchMaterialityConfig — 从 B15 重要性水平底稿自动取实际执行重要性（PM）
 *
 * 🔴 立项依据（2026-08-06 F0-4 浏览器实测）：
 * `useDiffReconcileData` 的 `materialityConfig` 原先**只**从底稿自身持久化载荷
 * （`htmlData.materiality_config`）读取，全文没有任何取数调用 → 新建/从未手工填过
 * 阈值的底稿一律显示「未配置」，而：
 *   ① UI 文案写着「默认从 B15 重要性水平底稿自动获取」= 承诺未兑现
 *   ② `DiffReconcileConclusion.vue` 的 `source === 'auto'` → 「自动取值」tag 分支
 *      **永远不可达**（全平台没有一处把 source 写成 'auto'）
 *   ③ 连带 `isOverMateriality()` 恒 false → 差异行不标红、看板「超重要性」恒 0、
 *      `DiffReconcileMaster` 的「推送 N 笔超重要性差异至 A13」按钮**永久 disabled**
 * 实测项目 `2aa00f57`：`GET /api/projects/{id}/materiality?year=2025` 返回 200 且
 * `performance_materiality = 26104487`，而 F0-4 界面显示「未配置」。
 *
 * 受益面 = D0-4 / E0-4 / F0-4 / G0-4 / H0-4 / K0-4 / L0-4 七个函证枢纽共用该组件。
 *
 * 🔴 用 `api`（`@/services/apiProxy`，**直接返回业务数据**）不用 `@/utils/http`
 * （后者返回 AxiosResponse 需 `.data`）—— 本 spec Task 20.1 / Task 33 两次踩过
 * 这个形态错配，两次方向还相反，且四层验证全绿只有浏览器能发现。
 */
import { api } from '@/services/apiProxy'
import type { MaterialityConfig } from '../diffReconcileTypes'

/** `/materiality` 端点响应里我们需要的字段（其余字段忽略） */
interface MaterialityResponse {
  performance_materiality?: number | string | null
}

/**
 * 判断底稿持久化载荷里是否已有可用的 PM 配置。
 *
 * 「已有」= 数值有效且 > 0。`0` / 负数 / NaN 视为未配置（与 `isOverMateriality`
 * 的 `pm == null || pm <= 0` 判据保持同一口径，避免两处标准不一致）。
 */
export function hasUsablePm(config: MaterialityConfig | null | undefined): boolean {
  const pm = config?.performance_materiality
  return typeof pm === 'number' && Number.isFinite(pm) && pm > 0
}

/**
 * 从 B15 拉取 PM。
 *
 * - 成功且 PM 有效 → 返回 `{ performance_materiality, is_overridden: false, source: 'auto' }`
 * - 项目未编制重要性水平（404）/ PM 为 0 或缺失 / 网络异常 → 返回 `null`
 *
 * **fail-open**：任何异常都返回 `null` 而不抛出 —— 取不到阈值时的正确行为是
 * 「不判超重要性」（`isOverMateriality` 恒 false + 单行「推送」按钮仍可用由审计师
 * 自行判断），而不是让整个底稿加载失败。
 */
export async function fetchMaterialityConfig(
  projectId: string | undefined,
  year: string | number | undefined,
): Promise<MaterialityConfig | null> {
  if (!projectId) return null

  try {
    const query = year ? `?year=${encodeURIComponent(String(year))}` : ''
    const raw = (await api.get(
      `/api/projects/${projectId}/materiality${query}`,
    )) as MaterialityResponse | null

    const pm = Number(raw?.performance_materiality)
    if (!Number.isFinite(pm) || pm <= 0) return null

    return { performance_materiality: pm, is_overridden: false, source: 'auto' }
  } catch {
    // 404（未编制重要性水平）与网络异常同等处理：不配置阈值
    return null
  }
}
