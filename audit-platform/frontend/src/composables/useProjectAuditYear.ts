/**
 * 项目审计年度 —— 写请求用的单一来源（spec audit-year-calendar-fallback-ratchet R0 / 任务 0.2）
 *
 * 取 `GET /api/projects/{id}` 的 `audit_year`（后端 resolve_project_audit_year：审计年度 → 审计期末 → 审计期初 → 向导 → 项目名后缀），
 * 与 render-config 读程序表字段覆盖用的是同一个项目年度。
 * - 不取 store：`setCurrentYear` 会把 `auditYear` 改成用户切换的年度。
 * - 不取 GtWpRenderer 的 `preparationYear`：它永不为空（最后兜底去年）。
 * - 取不到 ⇒ null；写请求据此不发并提示，绝不按日历猜（原写法「路由年度 → 今年」让 2025 年度项目在 2026 年写进 2026，刷新后看不到）。
 * - 请求带 `_dedupe:false`：页面里常有同址的 GET（如程序表加载项目信息），GET 去重会取消先发的那一个；
 *   带 `_silent`：错误提示由这里给（失败与「没填年度」分开说）。
 */
import { ref, toValue, type MaybeRefOrGetter } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { resolveAuditYearFromProject } from '@/utils/resolveAuditYear'

export const MISSING_AUDIT_YEAR_MESSAGE = '未设置审计年度，请先在项目基本信息中填写'

export interface AuditYearLookup {
  year: number | null
  /** 请求失败（与「项目没填年度」区分提示） */
  failed: boolean
}

export async function fetchProjectAuditYear(projectId: string): Promise<AuditYearLookup> {
  if (!projectId) return { year: null, failed: false }
  try {
    const res: any = await api.get(`/api/projects/${projectId}`, { _dedupe: false, _silent: true } as any)
    return { year: resolveAuditYearFromProject(res?.data ?? res), failed: false }
  } catch {
    return { year: null, failed: true }
  }
}

export function warnAuditYearUnavailable(lookup: AuditYearLookup, action = '保存'): void {
  ElMessage.warning(lookup.failed
    ? `读取项目审计年度失败，本次${action}未提交，请稍后重试`
    : `${MISSING_AUDIT_YEAR_MESSAGE}（本次${action}未提交）`)
}

/** 非组件场景（如循环底稿的「回填程序表」函数）：每次现取，取不到即提示并返回 null */
export async function requireProjectAuditYear(projectId: string, action = '保存'): Promise<number | null> {
  const lookup = await fetchProjectAuditYear(projectId)
  if (lookup.year == null) warnAuditYearUnavailable(lookup, action)
  return lookup.year
}

/** 组件内：按实例缓存非空结果（换项目重取；null 不缓存 —— 用户填了年度后下一次就能写） */
export function useProjectAuditYear(projectId: MaybeRefOrGetter<string>) {
  const auditYear = ref<number | null>(null)
  let cachedFor = ''
  let inflight: { pid: string; promise: Promise<AuditYearLookup> } | null = null

  function lookup(): Promise<AuditYearLookup> {
    const pid = toValue(projectId) || ''
    if (!pid) return Promise.resolve({ year: null, failed: false })
    if (cachedFor === pid && auditYear.value != null) return Promise.resolve({ year: auditYear.value, failed: false })
    if (inflight?.pid === pid) return inflight.promise
    const promise = (async () => {
      const result = await fetchProjectAuditYear(pid)
      if (result.year != null && (toValue(projectId) || '') === pid) {
        auditYear.value = result.year
        cachedFor = pid
      }
      return result
    })()
    inflight = { pid, promise }
    const clear = () => { if (inflight?.promise === promise) inflight = null }
    void promise.then(clear, clear)
    return promise
  }

  async function ensureAuditYear(): Promise<number | null> {
    return (await lookup()).year
  }

  async function requireAuditYear(action = '保存'): Promise<number | null> {
    const result = await lookup()
    if (result.year == null) warnAuditYearUnavailable(result, action)
    return result.year
  }

  return { auditYear, ensureAuditYear, requireAuditYear }
}
