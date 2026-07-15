/**
 * navigateToCycleSheet — 同项目函证套件内跨表跳转
 * wp-id-by-code → WorkpaperEditor；可选附带 confirm_index query 供定位
 */
import type { Router } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/http'

export async function navigateToCycleSheet(options: {
  router: Router
  projectId?: string
  targetWpCode: string
  confirmIndex?: string
}): Promise<boolean> {
  const { router, projectId, targetWpCode, confirmIndex } = options
  if (!projectId?.trim()) {
    ElMessage.warning('缺少项目上下文，无法跳转')
    return false
  }
  if (!targetWpCode?.trim()) {
    ElMessage.warning('缺少目标底稿编码')
    return false
  }
  try {
    const res = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: targetWpCode },
      _silent: true,
    } as any)
    const wpId = (res as any)?.wp_id
    if (!wpId) {
      ElMessage.info(`未找到 ${targetWpCode} 底稿`)
      return false
    }
    await router.push({
      name: 'WorkpaperEditor',
      params: { projectId, wpId },
      query: confirmIndex ? { confirm_index: confirmIndex } : undefined,
    })
    return true
  } catch (e: any) {
    ElMessage.warning(`打开 ${targetWpCode} 失败：` + (e?.message || '未知错误'))
    return false
  }
}
