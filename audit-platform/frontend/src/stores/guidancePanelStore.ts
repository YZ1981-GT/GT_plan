/**
 * 底稿编制指导面板 Store
 *
 * 管理编制指导面板的展开/折叠状态、当前 Tab、底稿上下文、指引数据与加载态。
 * localStorage 持久化展开状态，sessionStorage 缓存 guidanceData（按 wp_code）。
 *
 * 用法：
 * ```ts
 * const store = useGuidancePanelStore()
 * store.open()
 * store.setWpContext({ wpId, wpCode, wpName, componentType, projectId, year })
 * await store.fetchGuidance()
 * ```
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface WpContext {
  wpId: string
  wpCode: string
  wpName: string
  componentType: string
  projectId: string
  year: number
  sheetCode?: string  // 多 sheet 底稿当前 sheet 的子码（如 D0-1），用于加载专属 guidance
}

export interface GuidanceSection {
  title: string
  items: string[]
}

export interface GuidanceResponse {
  wp_code: string
  wp_name: string
  source: 'template_sheet' | 'template_header' | 'static_json' | 'typed_fallback' | 'fallback'
  complexity: 'high' | 'medium' | 'low'
  ai_enabled: boolean
  guidance: {
    sections: GuidanceSection[]
    raw_text: string
  }
  recommended_questions: string[]
}

// ─── Constants ──────────────────────────────────────────────────────────────

const LS_KEY_OPEN = 'gt_guidance_panel_open'
const SS_KEY_PREFIX = 'gt_guidance_'

// ─── Helpers ────────────────────────────────────────────────────────────────

function loadOpenState(): boolean {
  try {
    const val = localStorage.getItem(LS_KEY_OPEN)
    return val === 'true'
  } catch { return false }
}

function saveOpenState(open: boolean) {
  try { localStorage.setItem(LS_KEY_OPEN, String(open)) } catch { /* ignore */ }
}

function loadCachedGuidance(wpCode: string): GuidanceResponse | null {
  try {
    const raw = sessionStorage.getItem(SS_KEY_PREFIX + wpCode)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return null
}

function saveCachedGuidance(wpCode: string, data: GuidanceResponse) {
  try { sessionStorage.setItem(SS_KEY_PREFIX + wpCode, JSON.stringify(data)) } catch { /* ignore */ }
}

// ─── Store ──────────────────────────────────────────────────────────────────

export const useGuidancePanelStore = defineStore('guidancePanel', () => {
  // ─── State ──────────────────────────────────────────────────────────────
  const isOpen = ref(loadOpenState())
  const activeTab = ref<'guidance' | 'ai'>('guidance')
  const wpContext = ref<WpContext | null>(null)
  const guidanceData = ref<GuidanceResponse | null>(null)
  const guidanceLoading = ref(false)
  const aiEnabled = ref(false)

  // 竞态防护
  const requestId = ref(0)
  const abortController = ref<AbortController | null>(null)

  // ─── Computed ───────────────────────────────────────────────────────────
  const sourceLabel = computed(() => {
    const map: Record<string, string> = {
      template_sheet: '模板提取',
      template_header: '模板提取',
      static_json: '知识库',
      fallback: '通用提示',
    }
    return map[guidanceData.value?.source || ''] || '通用提示'
  })

  const isFallback = computed(() => guidanceData.value?.source === 'fallback')

  // ─── Actions ────────────────────────────────────────────────────────────

  function toggle() {
    isOpen.value = !isOpen.value
    saveOpenState(isOpen.value)
  }

  function open() {
    isOpen.value = true
    saveOpenState(true)
  }

  function close() {
    isOpen.value = false
    saveOpenState(false)
  }

  function setActiveTab(tab: 'guidance' | 'ai') {
    activeTab.value = tab
  }

  function setWpContext(ctx: WpContext) {
    // 如果底稿或 sheet 切换了，重置数据+取消旧请求
    const changed = wpContext.value?.wpId !== ctx.wpId || wpContext.value?.sheetCode !== ctx.sheetCode
    wpContext.value = ctx

    if (changed) {
      // 取消进行中请求
      abortController.value?.abort()
      abortController.value = null

      // 清空旧数据
      guidanceData.value = null
      guidanceLoading.value = false

      // 尝试从 sessionStorage 加载缓存（key 含 sheetCode 以区分不同 sheet）
      const cacheKey = ctx.sheetCode ? `${ctx.wpCode}_${ctx.sheetCode}` : ctx.wpCode
      const cached = loadCachedGuidance(cacheKey)
      if (cached) {
        guidanceData.value = cached
        aiEnabled.value = cached.ai_enabled
      } else {
        // 无缓存 → 立即 fetch
        fetchGuidance()
      }
    }
  }

  async function fetchGuidance() {
    if (!wpContext.value) return

    const ctx = wpContext.value
    const currentRequestId = ++requestId.value

    // 取消上一个未完成请求
    abortController.value?.abort()
    const controller = new AbortController()
    abortController.value = controller

    guidanceLoading.value = true

    try {
      const params: Record<string, string> = {}
      if (ctx.sheetCode) params.sheet_code = ctx.sheetCode
      const queryStr = Object.keys(params).length
        ? '?' + new URLSearchParams(params).toString()
        : ''
      const data = await api.get<GuidanceResponse>(
        `/api/workpapers/${ctx.wpId}/guidance${queryStr}`,
        { signal: controller.signal },
      )

      // 竞态检查：只接受最新请求的结果
      if (requestId.value !== currentRequestId) return

      guidanceData.value = data
      aiEnabled.value = data.ai_enabled ?? false

      // 写入 sessionStorage 缓存（key 含 sheetCode 区分不同 sheet）
      const cacheKey = ctx.sheetCode ? `${ctx.wpCode}_${ctx.sheetCode}` : ctx.wpCode
      saveCachedGuidance(cacheKey, data)
    } catch (e: any) {
      // 被 abort 的请求静默忽略
      if (e?.name === 'AbortError' || e?.code === 'ERR_CANCELED') return
      // 竞态检查
      if (requestId.value !== currentRequestId) return
      // 其他错误：保持空态，面板显示 fallback
      guidanceData.value = null
    } finally {
      if (requestId.value === currentRequestId) {
        guidanceLoading.value = false
      }
    }
  }

  return {
    // state
    isOpen,
    activeTab,
    wpContext,
    guidanceData,
    guidanceLoading,
    aiEnabled,
    requestId,
    // computed
    sourceLabel,
    isFallback,
    // actions
    toggle,
    open,
    close,
    setActiveTab,
    setWpContext,
    fetchGuidance,
  }
})
