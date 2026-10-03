/**
 * 原生请求鉴权 token 的唯一读取入口
 *
 * 适用于绕过 `utils/http.ts` 拦截器的请求：原生 `fetch` / `XMLHttpRequest` /
 * `el-upload` 的 `:headers` / EventSource 的 `?token=` 查询参数。
 * 走 `api.*` / `http.*` 的请求**不需要**调用本模块（拦截器已附加 Authorization）。
 *
 * ## 为什么必须收口到这里
 *
 * `stores/auth.ts` 出于安全考虑把 token 从 localStorage 迁到 sessionStorage，
 * 并在迁移时**删除** localStorage 副本。此后凡是自己读 `localStorage.getItem('token')`
 * 的原生请求都恒拿到 null → 不带 Authorization → 后端 401，且多数调用点把失败吞掉，
 * 表现为「点了没反应 / 上传失败」而不是报错。知识库「新建文件夹后上传不了文档」
 * 即此根因（2026-09-29 Playwright 实测：同页 `api.get` 200，原生 XHR 上传 401）。
 *
 * 读取顺序与 `http.ts` 请求拦截器一致：auth store 为准；Pinia 尚未激活的极早期调用
 * 回退 sessionStorage（store 的每次写 token 都同步写 sessionStorage，两者恒一致）。
 *
 * 守卫：`src/__tests__/authTokenSingleSource.spec.ts` 禁止在本文件与
 * `stores/auth.ts`（一次性迁移逻辑）之外直接读写 token 存储。
 */
import { useAuthStore } from '@/stores/auth'

/** 当前 access token；未登录返回空串。 */
export function getAuthToken(): string {
  try {
    const token = useAuthStore().token
    if (token) return token
  } catch {
    // Pinia 未激活（应用挂载前调用）→ 回退 sessionStorage
  }
  try {
    return sessionStorage.getItem('token') || ''
  } catch {
    return ''
  }
}

/** 原生请求用的鉴权头；未登录返回空对象（不发送 `Bearer ` 空串）。 */
export function getAuthHeaders(): Record<string, string> {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
