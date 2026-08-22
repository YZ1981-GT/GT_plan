/**
 * useAiMention — AI 面板 Mention 选择器状态与搜索逻辑
 *
 * 职责：
 * - `@` 触发搜索面板
 * - 防抖联查 /api/ai-chat/mentionable
 * - 多选 / 移除 / 类型过滤
 * - 搜索失败/超时/能力不可用 vs 成功空结果 明确区分（Property 13）
 *
 * Feature: dsh-agent-panel-integration / Task 15
 * Validates: Requirements 5.1, 5.4, 5.7, 5.9
 * Properties: 12, 13
 */
import { ref, computed, watch, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { AiHostRef } from '@/composables/useAiHostContext'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** 后端 MentionableItem 的前端镜像。 */
export interface MentionItem {
  type: MentionType
  id: string
  label: string
  sublabel: string
  jump_route: string
}

/** 支持的 mention 资源类型（镜像后端 MENTION_RESOURCE_TYPES）。 */
export type MentionType =
  | 'workpaper'
  | 'note'
  | 'report'
  | 'knowledge_doc'
  | 'knowledge_folder'
  | 'address'
  | 'attachment'

/** MentionType → 中文标签。 */
export const MENTION_TYPE_LABELS: Record<MentionType, string> = {
  workpaper: '底稿',
  note: '附注',
  report: '报表',
  knowledge_doc: '知识文档',
  knowledge_folder: '知识库',
  address: '地址坐标',
  attachment: '附件',
}

/** MentionType → Element Plus icon 名称。 */
export const MENTION_TYPE_ICONS: Record<MentionType, string> = {
  workpaper: 'Document',
  note: 'Memo',
  report: 'DataAnalysis',
  knowledge_doc: 'Reading',
  knowledge_folder: 'Folder',
  address: 'Location',
  attachment: 'Paperclip',
}

/**
 * 搜索请求状态（Property 13 要求 error 与 empty 可区分）。
 * - idle: 未搜索
 * - loading: 搜索中
 * - success: 成功（items.length >= 0）
 * - error: HTTP/timeout/网络失败
 * - unavailable: 服务能力不可用
 */
export type MentionSearchStatus = 'idle' | 'loading' | 'success' | 'error' | 'unavailable'

/**
 * 各类型级别的搜索状态信号（后端 `MentionTypeStatus` 枚举的镜像，由 vitest 对账）。
 *
 * `project_required` = 当前宿主没有项目绑定，该类型压根搜不了；与 `empty`
 * （真的搜了、没匹配）必须区分 —— 混用会让审计师在受限全局知识模式下看到
 * "无匹配结果"，误以为库里没有底稿/附注/报表。
 */
export type TypeSearchStatus =
  | 'success'
  | 'empty'
  | 'error'
  | 'unavailable'
  | 'timeout'
  | 'project_required'

/**
 * 必须有项目绑定才能搜索的类型（镜像后端 `PROJECT_REQUIRED_MENTION_TYPES`）。
 *
 * 知识文档/知识库**不在**此列：知识资产可跨项目共享，无项目绑定时仍可引用。
 */
export const PROJECT_REQUIRED_MENTION_TYPES: readonly MentionType[] = [
  'workpaper',
  'note',
  'report',
  'address',
] as const

/** 失败类型状态 → 中文原因短语（空态与降级提示共用同一条文案真源）。 */
const TYPE_FAILURE_HINTS: Record<string, string> = {
  project_required: '需要先绑定项目',
  error: '搜索失败',
  unavailable: '暂不可用',
  timeout: '搜索超时',
}

/** 该状态是否代表"没搜成"（区别于 success / empty）。 */
function isFailureStatus(status: TypeSearchStatus | undefined): boolean {
  return !!status && status in TYPE_FAILURE_HINTS
}

/**
 * 类型名列表 → 中文顿号串（`底稿、附注、报表`）。
 *
 * 按 `MENTION_TYPE_LABELS` 的声明顺序排（底稿→附注→报表→知识→地址坐标），
 * 而不是后端返回的字母序 —— 否则文案会读成"地址坐标、附注、报表、底稿"。
 */
const TYPE_DISPLAY_ORDER = Object.keys(MENTION_TYPE_LABELS) as MentionType[]

function joinTypeLabels(types: string[]): string {
  const rank = (t: string) => {
    const i = TYPE_DISPLAY_ORDER.indexOf(t as MentionType)
    return i < 0 ? TYPE_DISPLAY_ORDER.length : i
  }
  return [...types]
    .sort((a, b) => rank(a) - rank(b))
    .map((t) => MENTION_TYPE_LABELS[t as MentionType] ?? t)
    .join('、')
}

/**
 * 失败类型清单 → 面向审计师的中文原因（导出供测试直接断言）。
 *
 * 同一原因的类型合并成一句，避免"底稿需要先绑定项目、附注需要先绑定项目、…"的啰嗦串。
 */
export function buildFailureMessage(
  failed: readonly [string, TypeSearchStatus][],
): string {
  if (failed.length === 0) return ''

  const byStatus = new Map<TypeSearchStatus, string[]>()
  for (const [type, status] of failed) {
    const list = byStatus.get(status) ?? []
    list.push(type)
    byStatus.set(status, list)
  }

  const clauses: string[] = []
  for (const [status, types] of byStatus) {
    const names = joinTypeLabels(types)
    if (status === 'project_required') {
      clauses.push(`${names}需要先绑定项目才能引用`)
    } else {
      clauses.push(`${names}${TYPE_FAILURE_HINTS[status] ?? '不可用'}`)
    }
  }

  const detail = clauses.join('；')
  // 全是"需要项目"时补一句可操作指引（受限全局知识模式最常见）
  if (byStatus.size === 1 && byStatus.has('project_required')) {
    return `${detail}。请先从某个项目的底稿或报表页打开 AI 对话。`
  }
  return `${detail}。`
}

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

export interface UseAiMentionOptions {
  /** 当前宿主上下文（用于构建 mentionable 请求的 host_type/host_id/project_id/year） */
  host: Ref<AiHostRef | null>
  /** 防抖延迟（ms），默认 300 */
  debounceMs?: number
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useAiMention(options: UseAiMentionOptions) {
  const { host, debounceMs = 300 } = options

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  /** 面板是否打开 */
  const pickerOpen = ref(false)
  /** 当前搜索关键词（用户输入） */
  const searchQuery = ref('')
  /** 当前类型过滤器 */
  const typeFilter = ref<MentionType | null>(null)
  /** 搜索结果 */
  const items = ref<MentionItem[]>([])
  /** 搜索状态 */
  const searchStatus = ref<MentionSearchStatus>('idle')
  /** 各类型搜索状态 */
  const typeStatus = ref<Record<string, TypeSearchStatus>>({})
  /** 错误消息 */
  const errorMessage = ref('')
  /** 已选择的 mention 列表 */
  const selected = ref<MentionItem[]>([])

  // ---------------------------------------------------------------------------
  // Internal
  // ---------------------------------------------------------------------------

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let abortController: AbortController | null = null

  // ---------------------------------------------------------------------------
  // Computed
  // ---------------------------------------------------------------------------

  /** 搜索结果为空且已成功返回 */
  const isEmpty = computed(() => searchStatus.value === 'success' && items.value.length === 0)
  /** 搜索出错 */
  const isError = computed(() => searchStatus.value === 'error')
  /** 服务不可用 */
  const isUnavailable = computed(() => searchStatus.value === 'unavailable')
  /** 是否正在加载 */
  const isLoading = computed(() => searchStatus.value === 'loading')
  /** 已选 ID set（快速查重） */
  const selectedIds = computed(() => new Set(selected.value.map((s) => `${s.type}:${s.id}`)))

  /**
   * 部分类型失败时的降级提示（**有结果**也要提示，否则用户不知道有几类没搜）。
   *
   * 与 `errorMessage` 互补：`errorMessage` 用于"全军覆没"的空态，
   * 本提示用于"搜到一些、但某几类没搜成"。
   */
  const degradedHint = computed<string>(() => {
    if (searchStatus.value !== 'success') return ''
    const failed = (Object.entries(typeStatus.value) as [string, TypeSearchStatus][])
      .filter(([t, s]) => t !== 'attachment' && isFailureStatus(s))
    if (failed.length === 0) return ''
    return buildFailureMessage(failed)
  })

  /** 当前是否有类型因缺少项目绑定而不可用（供 UI 置灰对应 tab）。 */
  const projectBindingMissing = computed<boolean>(
    () => host.value?.projectId == null,
  )

  /**
   * 空态文案。
   *
   * 🔴 零结果时**不能**一律说"无匹配结果"：受限全局知识模式下最常见的情形是
   * 「四类项目资源压根没搜（project_required）+ 知识两类真的没匹配」——
   * 此时 failed(4) ≠ participating(6) 走不进失败态，空态若只说"无匹配结果"，
   * 用户仍会以为库里没有底稿/附注/报表。（浏览器实测抓出的缺口）
   */
  const emptyReason = computed<string>(() => {
    if (!isEmpty.value) return ''
    const hint = degradedHint.value
    return hint ? `未搜到匹配项。${hint}` : '无匹配结果'
  })

  // ---------------------------------------------------------------------------
  // Auth
  // ---------------------------------------------------------------------------

  function getToken(): string {
    try {
      return useAuthStore().token || ''
    } catch {
      return ''
    }
  }

  // ---------------------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------------------

  /** 执行 mention 搜索 */
  async function executeSearch(query: string, filter: MentionType | null): Promise<void> {
    // 取消进行中的请求
    abortController?.abort()
    abortController = new AbortController()

    const currentHost = host.value
    if (!currentHost || !currentHost.id) {
      searchStatus.value = 'error'
      errorMessage.value = '当前页面上下文无法确定，无法搜索引用资源。'
      items.value = []
      return
    }

    searchStatus.value = 'loading'
    errorMessage.value = ''

    const params = new URLSearchParams()
    params.set('query', query)
    params.set('host_type', currentHost.type)
    params.set('host_id', currentHost.id)
    if (currentHost.projectId) params.set('project_id', currentHost.projectId)
    if (currentHost.year != null) params.set('year', String(currentHost.year))
    if (filter) params.set('type_filter', filter)
    params.set('limit', '10')

    try {
      const res = await fetch(`/api/ai-chat/mentionable?${params.toString()}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
        signal: abortController.signal,
      })

      if (!res.ok) {
        if (res.status === 403 || res.status === 401) {
          searchStatus.value = 'unavailable'
          errorMessage.value = '当前账号无权搜索引用资源。'
        } else if (res.status === 429) {
          searchStatus.value = 'error'
          errorMessage.value = '搜索请求过于频繁，请稍后再试。'
        } else if (res.status === 503) {
          searchStatus.value = 'unavailable'
          errorMessage.value = '引用搜索服务暂不可用，请稍后再试。'
        } else {
          searchStatus.value = 'error'
          errorMessage.value = '搜索加载失败，请稍后重试。'
        }
        items.value = []
        return
      }

      const body = await res.json()
      const data = body?.data ?? body

      // 解析 type_status（Property 13：各类型级别状态）
      typeStatus.value = data.type_status ?? {}

      items.value = (data.items ?? []).map((item: any) => ({
        type: item.type as MentionType,
        id: item.id,
        label: item.label ?? '',
        sublabel: item.sublabel ?? '',
        jump_route: item.jump_route ?? '',
      }))

      // 🔴 单个类型的失败**不能**被吞成 success。
      // 旧实现只在「所有类型都 unavailable」时才报错，于是后端 4 个类型长期恒 error
      // （ORM 字段名写错）在界面上一律显示成"无匹配结果" —— 用户与开发都看不到真实原因。
      // 现在：零结果且参与的类型全部失败 ⇒ 按失败态渲染并给出精确中文原因。
      const entries = Object.entries(typeStatus.value) as [string, TypeSearchStatus][]
      // 只统计本次真正参与的类型（后端对 attachment 恒回 empty，不参与判定）
      const participating = entries.filter(([t]) => t !== 'attachment')
      const failed = participating.filter(([, s]) => isFailureStatus(s))

      if (items.value.length === 0 && failed.length > 0 && failed.length === participating.length) {
        searchStatus.value = 'unavailable'
        errorMessage.value = buildFailureMessage(failed)
        return
      }

      searchStatus.value = 'success'
    } catch (err: any) {
      if (err?.name === 'AbortError') return // 被取消的搜索忽略
      if (err?.message?.includes('timeout') || err?.name === 'TimeoutError') {
        searchStatus.value = 'error'
        errorMessage.value = '搜索超时，请稍后重试。'
      } else {
        searchStatus.value = 'error'
        errorMessage.value = '网络异常，搜索加载失败。'
      }
      items.value = []
    }
  }

  /** 防抖触发搜索 */
  function triggerSearch() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      executeSearch(searchQuery.value, typeFilter.value)
    }, debounceMs)
  }

  // ---------------------------------------------------------------------------
  // Selection
  // ---------------------------------------------------------------------------

  /** 选择一个 mention item（多选） */
  function selectItem(item: MentionItem) {
    const key = `${item.type}:${item.id}`
    if (selectedIds.value.has(key)) return // 已选
    selected.value = [...selected.value, item]
  }

  /** 移除已选 mention */
  function removeItem(item: MentionItem) {
    selected.value = selected.value.filter(
      (s) => !(s.type === item.type && s.id === item.id),
    )
  }

  /** 清除全部已选 */
  function clearSelection() {
    selected.value = []
  }

  /** 判断 item 是否已选 */
  function isSelected(item: MentionItem): boolean {
    return selectedIds.value.has(`${item.type}:${item.id}`)
  }

  // ---------------------------------------------------------------------------
  // Picker 控制
  // ---------------------------------------------------------------------------

  /** 打开选择器（由 `@` 触发） */
  function openPicker() {
    pickerOpen.value = true
    searchQuery.value = ''
    searchStatus.value = 'idle'
    items.value = []
    errorMessage.value = ''
  }

  /** 关闭选择器 */
  function closePicker() {
    pickerOpen.value = false
    abortController?.abort()
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
  }

  /** 切换类型过滤器 */
  function setTypeFilter(type: MentionType | null) {
    typeFilter.value = type
    triggerSearch()
  }

  // ---------------------------------------------------------------------------
  // Watchers
  // ---------------------------------------------------------------------------

  // 搜索关键词变化时防抖搜索
  watch(searchQuery, (val) => {
    if (pickerOpen.value) {
      if (val.trim() || typeFilter.value) {
        triggerSearch()
      } else {
        // 空查询且无过滤器时清空结果
        searchStatus.value = 'idle'
        items.value = []
      }
    }
  })

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  function dispose() {
    abortController?.abort()
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
  }

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    // State
    pickerOpen,
    searchQuery,
    typeFilter,
    items,
    searchStatus,
    typeStatus,
    errorMessage,
    selected,

    // Computed
    isEmpty,
    isError,
    isUnavailable,
    isLoading,
    selectedIds,
    degradedHint,
    projectBindingMissing,
    emptyReason,

    // Methods
    openPicker,
    closePicker,
    triggerSearch,
    selectItem,
    removeItem,
    clearSelection,
    isSelected,
    setTypeFilter,
    dispose,
  }
}
