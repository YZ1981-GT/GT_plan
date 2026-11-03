/**
 * 底稿短链 `/workpapers/:wpId` 的定位（spec acnr-foundation-defect-closure T16 / RV7.5-01）。
 *
 * ACNR 产出的跳转路由是 `/workpapers/{wp_id}?sheet=…`（目录 jump_route_template、resolver 缺省、acnr_targets 回落
 * 父底稿），AI 提及、证据治理也产出 `/workpapers/{id}`；前端编辑器路由是 `/projects/:projectId/workpapers/:wpId/edit`。
 * 短链页经 `GET /api/acnr/workpapers/{wp_id}/locate`（按底稿 id 查所属项目、项目 readonly 鉴权）拿到项目后，
 * 用 `workpaperEditorRoute`（编辑器路由唯一构造处）生成目标并 `router.replace`；查询串（sheet / cell 等，编辑器按
 * `route.query.sheet` / `route.query.cell` 定位）原样带过去。失败时只给中文原因、不跳转（不会形成重定向循环）。
 */
import type { LocationQuery } from 'vue-router'
import { api } from '@/services/apiProxy'
import { workpaperEditorRoute } from '@/composables/useWorkpaperNavigation'

export interface WorkpaperLocation {
  wp_id: string
  project_id: string
  wp_code?: string | null
}

export type ShortLinkResult =
  | { ok: true; target: ReturnType<typeof workpaperEditorRoute> }
  | { ok: false; reason: string; hint: string }

export const SHORT_LINK_TEXT = {
  forbidden: { reason: '无权访问该底稿所属的项目', hint: '请联系项目经理把你加入该项目，或返回上一页。' },
  notFound: { reason: '底稿不存在', hint: '链接可能已过期，或底稿已被删除；可进入项目列表重新查找。' },
  recycled: { reason: '底稿已移入回收站', hint: '可在项目的回收站中恢复后再打开。' },
  projectRecycled: { reason: '底稿所属项目已移入回收站', hint: '可在回收站中恢复该项目后再打开。' },
  invalid: { reason: '链接中的底稿编号无效', hint: '请返回上一页重新打开。' },
  failed: { reason: '暂时无法打开底稿', hint: '请检查网络后刷新重试，或返回上一页。' },
} as const

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** 查询串转成字符串字典（数组取首个、空值丢弃），原样交给编辑器路由。 */
export function shortLinkQuery(query: LocationQuery): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(query)) {
    const first = Array.isArray(v) ? v[0] : v
    if (first !== null && first !== undefined && first !== '') out[k] = String(first)
  }
  return out
}

function failureOf(e: unknown): { reason: string; hint: string } {
  const resp = (e as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  const status = resp?.status
  if (status === 403) return SHORT_LINK_TEXT.forbidden
  if (status === 404) return SHORT_LINK_TEXT.notFound
  if (status === 410) {
    // 项目整体移入回收站时底稿行不标删，后端用不同的错误码区分（RV7.6-01）：恢复的是项目，不是底稿
    const detail = resp?.data?.detail
    const code = detail && typeof detail === 'object' ? (detail as { error_code?: unknown }).error_code : undefined
    return code === 'PROJECT_IN_RECYCLE_BIN' ? SHORT_LINK_TEXT.projectRecycled : SHORT_LINK_TEXT.recycled
  }
  if (status === 422) return SHORT_LINK_TEXT.invalid
  return SHORT_LINK_TEXT.failed
}

/** 定位底稿并生成编辑器目标路由；失败返回中文原因与下一步。 */
export async function resolveShortLink(wpId: string, query: LocationQuery): Promise<ShortLinkResult> {
  if (!UUID_RE.test(wpId)) return { ok: false, ...SHORT_LINK_TEXT.invalid }
  try {
    const loc = await api.get<WorkpaperLocation>(`/api/acnr/workpapers/${encodeURIComponent(wpId)}/locate`,
      { _silent: true } as any)
    if (!loc?.project_id) return { ok: false, ...SHORT_LINK_TEXT.failed }
    const q = shortLinkQuery(query)
    return { ok: true, target: workpaperEditorRoute(loc.project_id, wpId, Object.keys(q).length ? q : undefined) }
  } catch (e) {
    return { ok: false, ...failureOf(e) }
  }
}
