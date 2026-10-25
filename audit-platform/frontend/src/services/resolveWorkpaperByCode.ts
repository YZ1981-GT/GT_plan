/**
 * 按 wp_code 解析项目内底稿实例 id。
 *
 * 🔴 历史缺陷（2026-10-01 真浏览器实测）：N4/N5 跨底稿取数与平台联动跳转调
 * `GET /api/projects/{pid}/wp-index/by-code/{code}` —— **后端从未有过这个路由**（恒 404）。
 * 调用方全部 `catch {}` 吞掉 ⇒ N4 从来读不到 N2 计提额、N5 从来读不到 N1/N3/I6/I2/利润表、
 * 按编码的联动跳转恒返回 null，且没有任何报错可见。
 *
 * 对齐平台既有约定入口（20+ 处在用）：`GET /api/custom-query/wp-id-by-code?project_id=&wp_code=`，
 * 响应（apiProxy 已剥信封）`{ wp_id }`；底稿不存在时 404。
 * 🔴 必须用 `@/services/apiProxy` 的 `api`（直接返回业务数据），`@/utils/http` 返回
 *    AxiosResponse，`res.wp_id` 恒 undefined（GtConfirmationSummary 已踩过）。
 */
import { api } from '@/services/apiProxy'

/** 端点（与平台其余调用方同一个） */
export const WP_ID_BY_CODE_URL = '/api/custom-query/wp-id-by-code'

export interface ResolvedWorkpaper {
  wpId: string
}

/**
 * 解析底稿实例；不存在 / 请求失败均返回 null（调用方按「未编制」处理）。
 * `silent` 默认 true：跨底稿取数是后台补充，失败不该弹全局错误。
 */
export async function resolveWorkpaperByCode(
  projectId: string,
  wpCode: string,
  silent = true,
): Promise<ResolvedWorkpaper | null> {
  if (!projectId || !wpCode) return null
  try {
    const data: any = await api.get(WP_ID_BY_CODE_URL, {
      params: { project_id: projectId, wp_code: wpCode },
      ...(silent ? { _silent: true } : {}),
    } as any)
    return data?.wp_id ? { wpId: String(data.wp_id) } : null
  } catch {
    return null
  }
}
