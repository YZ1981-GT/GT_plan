/**
 * OnlyOffice 健康探针 —— 全平台**唯一**实现（端点 / 字段 / 缓存 / 并发去重四合一）。
 *
 * ═══ 为什么提到 `sync/` 层 ═══════════════════════════════════════════════════
 *
 * 这段逻辑原先长在 `d4/composables/useD4SyncMode.ts` 里。D4 把它收敛成单份是为了灭掉
 * 2026-09-21 那批 bug（5 处组件误用 `/api/onlyoffice/health` → 404、误读
 * `status==='healthy'` → 在线编辑永久锁死）。但它留在 `d4/` 目录下，别的循环要用就得
 * `import ... from '../../d4/composables/useD4SyncMode'` —— 跨循环反向依赖，实际结果是
 * **没人敢 import，各自再抄一遍**。仓库现状实证：`useG4SppiDualMode.ts` / `useL1DualMode.ts`
 * / `useL3DualMode.ts` 仍各自 `http.get('/api/workpapers/onlyoffice/health')`，共 5 处，
 * 且都没有 TTL 缓存 —— 切一张底稿打一次探针，正是「切页面不丝滑」的老根因。
 *
 * ⇒ 本模块把实现搬到与 `useWorkpaperSyncBridge` 同级的 `sync/` 公共层：任何循环
 *   （D4 / H / 后续 I~S）都平行 import，不再有「谁依赖谁」的方向问题。
 *   `useD4SyncMode` 改为从这里 re-export，**保持其对外 API 逐字不变**（它的 spec 仍
 *   从 `useD4SyncMode` 取 `fetchOnlyOfficeHealthy` / `__resetOoHealthCacheForTests`）。
 *
 * 🔴 本轮**不动** G4/L1/L3 那 5 处：它们属并发会话在飞的作业面（L 循环 spec 未提交）。
 *    登记为后续收敛点 —— 迁移动作是纯替换（删本地 `checkOoHealth` + import 本模块），
 *    但必须由持有那些文件的会话做，避免又一次互相覆盖。
 */
import http from '@/utils/http'

/**
 * 健康检查的**唯一正确端点 + 唯一正确字段**。
 *
 * 正确端点 `/api/workpapers/onlyoffice/health`，响应 `{ data: { healthy: boolean } }`。
 * 两层 `?? ` 兜底是因为平台 `ResponseWrapperMiddleware` 会把 2xx JSON 包成
 * `{code,message,data}` 信封，而 `http`（`utils/http`）返回的是**完整响应体**
 * ⇒ 真实路径是 `res.data.data.healthy`；`res.data.healthy` 那一层留给未包装/已解包的形态。
 * `_silent: true` 让拦截器不弹全局错误提示 —— 探针失败是正常降级，不该打扰用户。
 */
async function requestOnlyOfficeHealthy(): Promise<boolean> {
  try {
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    return (res.data?.data?.healthy ?? res.data?.healthy ?? false) as boolean
  } catch {
    return false
  }
}

/** 健康结果存活时长 —— 同一时段内多次切换底稿共用一份结果，不逐张重打。 */
export const OO_HEALTH_TTL_MS = 15_000

/** 模块级共享缓存（跨组件、跨循环实例）。 */
let ooHealthCache: { value: boolean; expiresAt: number } | null = null
/** 并发去重：多个组件几乎同时挂载时只发一次真实请求，其余等同一个 promise。 */
let ooHealthInFlight: Promise<boolean> | null = null

/**
 * 取 OnlyOffice 健康状态 —— 带模块级共享 TTL 缓存 + 并发去重。
 *
 * `forceRefresh`：用户**已经点了**「在线编辑」时的竞态兜底用 `true`。此时不能信一个
 * 可能刚好卡在过期边界的旧值挡住这次真实点击；仍写回缓存供后续命中，且仍走同一个
 * in-flight 去重（并发调用不会打两次请求）。
 */
export async function fetchOnlyOfficeHealthy(forceRefresh = false): Promise<boolean> {
  const now = Date.now()
  if (!forceRefresh && ooHealthCache && ooHealthCache.expiresAt > now) {
    return ooHealthCache.value
  }
  if (ooHealthInFlight) return ooHealthInFlight
  ooHealthInFlight = requestOnlyOfficeHealthy()
    .then(value => {
      ooHealthCache = { value, expiresAt: Date.now() + OO_HEALTH_TTL_MS }
      return value
    })
    .finally(() => { ooHealthInFlight = null })
  return ooHealthInFlight
}

/**
 * 仅供测试：清空模块级缓存 / in-flight 去重状态。
 *
 * 各用例各自 mock 独立的 http 响应与 resolve 时机，不清空会被上一个用例遗留的缓存值
 * 或悬挂 promise 污染。生产路径不调用 —— TTL 到期或 `forceRefresh` 已足够。
 */
export function __resetOoHealthCacheForTests(): void {
  ooHealthCache = null
  ooHealthInFlight = null
}
