// 项目平面列表 2 秒微缓存（runtime-performance-and-reload-hardening-followup R6.5）。
//
// `/projects` 不是全宽路由：DefaultLayout 同时挂 MiddleProjectList，正文又挂 Projects.vue，
// 两者 onMounted 会同时 GET 同一个 `/api/projects`。apiProxy 的 in-flight 共享帮不到 commonApi，
// 因为它走 http 且显式带 `{ params: undefined }`。这里统一单飞 + 2 秒缓存；任何项目集合/展示字段
// mutation 显式 invalidate，epoch 防止失效前的晚到响应重新填回陈旧缓存。
import http from '@/utils/http'
import { projects as projectPaths } from '@/services/apiPaths'

export const PROJECT_LIST_CACHE_TTL_MS = 2_000

let epoch = 0
let cached: any[] | null = null
let expiresAt = 0
let inflight: Promise<any[]> | null = null

function normalize(data: any): any[] {
  return Array.isArray(data) ? data : data?.items || []
}

function cloneRows(rows: any[]): any[] {
  return rows.map(row => ({ ...row }))
}

export function invalidateProjectListQuery(): void {
  epoch += 1
  cached = null
  expiresAt = 0
  // 不取消已发出的 HTTP；只让失效后的新调用不加入旧 promise，旧响应也不能回填缓存。
  inflight = null
}

export async function listProjectsShared(params?: Record<string, any>): Promise<any[]> {
  const cacheable = !params || Object.keys(params).length === 0
  if (!cacheable) {
    const { data } = await http.get(projectPaths.list, { params })
    return cloneRows(normalize(data))
  }

  const now = Date.now()
  if (cached && now < expiresAt) return cloneRows(cached)
  if (inflight) return cloneRows(await inflight)

  const mine = epoch
  const request = http.get(projectPaths.list).then(({ data }) => normalize(data))
  inflight = request
  try {
    const rows = await request
    if (mine === epoch) {
      cached = rows
      expiresAt = Date.now() + PROJECT_LIST_CACHE_TTL_MS
    }
    return cloneRows(rows)
  } finally {
    if (inflight === request) inflight = null
  }
}

/** 只供判据读取，不给业务逻辑依赖。 */
export function _projectListQueryState() {
  return { epoch, cached: cached !== null, expiresAt, inflight: inflight !== null }
}
