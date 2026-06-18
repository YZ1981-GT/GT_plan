/**
 * useWorkpaperNavigation — 统一底稿索引跳转 composable
 *
 * 输入索引号字符串（可含多个逗号分隔），解析为可点击链接数组。
 * 支持跳转到底稿编辑器、程序表 HTML 视图、报表模块、附注编辑器等。
 */
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useWorkpaperRegistry, type RegistryEntry } from './useWorkpaperRegistry'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface IndexRef {
  /** 原始索引号 */
  code: string
  /** 注册表条目（null 表示未注册） */
  entry: RegistryEntry | null
  /** 该底稿是否已生成（需异步检查，默认 true） */
  exists: boolean
}

interface ResolveResult {
  wpId: string | null
  exists: boolean
}

// ─── Virtual sub-code redirect (A16-1~7 → A16 + ?version=) ──────────────────

/** A16-1~7 是虚拟子码，不创建独立 WorkingPaper，导航时重定向至 A16 + ?version= */
const A16_VIRTUAL_RE = /^A16-[1-7]$/

// ─── Route resolvers by render_type ──────────────────────────────────────────

function resolveRoute(
  wpCode: string,
  entry: RegistryEntry,
  projectId: string,
  wpId: string | null,
): { name: string; params: Record<string, string>; query?: Record<string, string> } {
  const rt = entry.render_type

  if (rt === 'html_procedure' || rt === 'html_review') {
    // HTML 程序表/复核表 → 底稿编辑器（后续由编辑器按 render_type 切换渲染）
    if (wpId) {
      return { name: 'WorkpaperEditor', params: { projectId, wpId } }
    }
    return { name: 'WorkpaperList', params: { projectId }, query: { highlight: wpCode } }
  }

  if (rt === 'auto_report') {
    const mod = entry.module
    if (mod === 'report_analysis' || mod === 'consolidation') {
      return { name: 'FinancialReport', params: { projectId }, query: { tab: wpCode } }
    }
    if (mod === 'cf_verification') {
      return { name: 'FinancialReport', params: { projectId }, query: { tab: 'cf' } }
    }
    // fallback
    if (wpId) {
      return { name: 'WorkpaperEditor', params: { projectId, wpId } }
    }
    return { name: 'WorkpaperList', params: { projectId }, query: { highlight: wpCode } }
  }

  if (rt === 'univer' || rt === 'word_template') {
    if (wpId) {
      return { name: 'WorkpaperEditor', params: { projectId, wpId } }
    }
    return { name: 'WorkpaperList', params: { projectId }, query: { highlight: wpCode } }
  }

  if (rt === 'readonly_reference' || rt === 'signing') {
    if (wpId) {
      return { name: 'WorkpaperEditor', params: { projectId, wpId } }
    }
    return { name: 'WorkpaperList', params: { projectId }, query: { highlight: wpCode } }
  }

  // default fallback
  return { name: 'WorkpaperList', params: { projectId }, query: { highlight: wpCode } }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWorkpaperNavigation() {
  const router = useRouter()
  const registry = useWorkpaperRegistry()

  /**
   * 解析索引号字符串为可点击链接数组
   * 支持逗号/顿号分隔的多索引：'A1-13,A1-14' / 'A1-13、A1-14'
   */
  function parseIndexRefs(refStr: string): IndexRef[] {
    if (!refStr || !refStr.trim()) return []

    const codes = refStr
      .split(/[,、;；\s]+/)
      .map((s) => s.trim())
      .filter(Boolean)

    return codes.map((code) => {
      const entry = registry.lookup(code)
      return {
        code,
        entry,
        exists: true, // 默认假设存在，实际检查在 navigate 时异步做
      }
    })
  }

  /**
   * 跳转到指定 wp_code 对应的底稿/视图
   */
  async function navigateToWorkpaper(
    wpCode: string,
    projectId: string,
    year?: number,
  ) {
    // ─── 虚拟子码重定向：A16-1~7 → A16 + ?version= ───
    if (A16_VIRTUAL_RE.test(wpCode)) {
      await registry.load()
      // 解析 A16 父码的 wp_id
      try {
        const res = await api.get<ResolveResult>(
          `/api/workpapers/index-resolve/${encodeURIComponent('A16')}`,
          { params: { project_id: projectId } },
        )
        if (res.wpId) {
          router.push({
            path: `/projects/${projectId}/workpapers/${res.wpId}/edit`,
            query: { version: wpCode },
          })
          return
        }
      } catch {
        // fallback: 跳转到列表页
      }
      router.push({ name: 'WorkpaperList', params: { projectId }, query: { highlight: 'A16' } })
      return
    }

    // 确保注册表已加载
    await registry.load()

    const entry = registry.lookup(wpCode)
    if (!entry) {
      ElMessage.warning(`未知索引号 ${wpCode}`)
      return
    }

    // 尝试解析 wp_code → wp_id
    let wpId: string | null = null
    try {
      const res = await api.get<ResolveResult>(
        `/api/workpapers/index-resolve/${encodeURIComponent(wpCode)}`,
        { params: { project_id: projectId } },
      )
      wpId = res.wpId
      if (!res.exists) {
        ElMessage.warning('该底稿尚未生成')
        return
      }
    } catch {
      // API 不可用时降级 — 仍尝试跳转到列表页
    }

    const route = resolveRoute(wpCode, entry, projectId, wpId)
    router.push(route)
  }

  return {
    parseIndexRefs,
    navigateToWorkpaper,
  }
}
