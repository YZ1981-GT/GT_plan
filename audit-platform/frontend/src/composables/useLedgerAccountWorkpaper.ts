/**
 * 余额表右键「跳转到底稿（审定表）」：科目 → 映射表里的审定表 → 本项目已生成的所在底稿，
 * 用 ?sheet= 定位到审定表页。
 */
import type { Router } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { workpaperEditorRoute } from '@/composables/useWorkpaperNavigation'

interface AccountWorkpaperItem {
  wp_code: string
  wp_name: string
  kind: string
  host_wp_code: string | null
  wp_id: string | null
}

export async function openAccountWorkpaper(router: Router, projectId: string, accountCode: unknown): Promise<void> {
  const code = String(accountCode ?? '').trim()
  if (!code || !projectId) return
  let items: AccountWorkpaperItem[] = []
  try {
    const data: any = await api.get(P_ledger.accountWorkpapers(projectId), {
      params: { account_code: code }, _silent: true,
    } as any)
    items = data?.items ?? []
  } catch (e: any) {
    handleApiError(e, '查找科目对应底稿')
    return
  }
  if (!items.length) {
    ElMessage.info(`科目 ${code} 在底稿映射表中没有对应的底稿`)
    return
  }
  // 审定表优先（后端已排序）；审定表没生成时退到该科目其他已生成的底稿，并说明
  const audit = items.find((i) => i.kind === 'audit_determination' && i.wp_id)
  const fallback = audit ? null : items.find((i) => i.wp_id)
  const target = audit ?? fallback
  if (target?.wp_id) {
    if (fallback) {
      const wanted = items.find((i) => i.kind === 'audit_determination')
      ElMessage.info(`${wanted ? `${wanted.wp_code} ${wanted.wp_name}` : '审定表'}尚未生成，已打开 ${target.wp_code} ${target.wp_name}`)
    }
    // 审定表常是主册里的一个 sheet：?sheet=审定表编码 定位（对不上时编辑器落默认页）
    const query: Record<string, string> = target.wp_code !== target.host_wp_code ? { sheet: target.wp_code } : {}
    router.push(workpaperEditorRoute(projectId, target.wp_id, query))
    return
  }
  const first = items[0]
  ElMessage.warning(`${first.wp_code} ${first.wp_name}尚未生成，已转到底稿目录`)
  router.push({ name: 'WorkpaperList', params: { projectId }, query: { highlight: first.wp_code } })
}
