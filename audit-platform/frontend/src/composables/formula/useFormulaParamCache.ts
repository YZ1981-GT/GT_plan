/**
 * 公式参数值补全——动态数据缓存（科目列表 / 底稿编码列表）。
 * spec: formula-input-param-completion · Task 2
 */
import api from '@/services/apiProxy'
import type { CandidateItem } from './formulaParamCandidates'

/** 按 projectId 缓存的科目列表 */
const accountCache = new Map<string, CandidateItem[]>()

/** 正在加载的请求（防并发重复） */
const pendingRequests = new Map<string, Promise<CandidateItem[]>>()

/**
 * 获取项目的科目代码列表（带缓存）。
 * 从 GET /api/projects/{id}/trial-balance 提取 standard_account_code + account_name。
 */
export async function loadAccountCodes(projectId: string): Promise<CandidateItem[]> {
  if (!projectId) return []

  // 命中缓存
  const cached = accountCache.get(projectId)
  if (cached) return cached

  // 防并发重复请求
  const pending = pendingRequests.get(projectId)
  if (pending) return pending

  const promise = (async () => {
    try {
      const data = await api.get(`/api/projects/${projectId}/trial-balance`, {
        params: { limit: 2000 },
      }) as any
      const rows = Array.isArray(data) ? data : (data?.items || [])
      const items: CandidateItem[] = rows
        .filter((r: any) => r.standard_account_code)
        .map((r: any) => ({
          value: r.standard_account_code,
          label: `${r.standard_account_code} - ${r.account_name || ''}`.trim(),
        }))
      // 去重（同科目可能多行）
      const seen = new Set<string>()
      const unique = items.filter(it => {
        if (seen.has(it.value)) return false
        seen.add(it.value)
        return true
      })
      accountCache.set(projectId, unique)
      return unique
    } catch {
      return []
    } finally {
      pendingRequests.delete(projectId)
    }
  })()

  pendingRequests.set(projectId, promise)
  return promise
}

/** 清除缓存（项目切换时调用） */
export function clearParamCache(projectId?: string) {
  if (projectId) {
    accountCache.delete(projectId)
  } else {
    accountCache.clear()
  }
}
