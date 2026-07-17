/**
 * useVisibilityWorkpaperList — 服务端强制可见性底稿列表消费层（前端）
 *
 * Feature: procedure-delegation-visibility-isolation · Task 12（组件 C16 Frontend）。
 * 仅消费服务端分页 envelope（Task 8 组件 C13），不在客户端做全量过滤/授权判定：
 *  - 分页/排序/过滤/统计全部来自服务端（Req 11.6/11.10–11.13）。
 *  - ``visibility_mode`` 与客户端角色/身份只作 UX 参数透传，绝不改变授权（Req 12.1–12.3 / P15）。
 *  - 状态拆分为 ``index_status`` / ``file_status`` 消费（Req 12.4/12.5）。
 *  - nullable wp（``wp_generated=false``）显示「底稿尚未生成」并禁用文件动作（Req 12.8/12.9）。
 *  - 收到 External_Not_Found（HTTP 404）统一显示「资源不存在或不可访问」，并清理已缓存的
 *    列表项/名称，绝不闪现缓存内容（Req 12.7）。
 *
 * 设计要点（design 组件 C16 / "Lists, editor, coverage and frontend"）：前端不是安全边界；
 * 此 composable 只负责正确消费服务端契约并驱动 UX 状态。
 */
import { ref, reactive, computed } from 'vue'
import {
  EXTERNAL_NOT_FOUND_MESSAGE,
  FILE_STATUS_NOT_GENERATED,
  type VisibilityWpItem,
  type WpListEnvelope,
  type WpListParams,
  type WpVisibilityStats,
} from '@/services/workpaperApi'

/** 服务端列表拉取器签名（listWorkpapersPaged / listMyLeadWorkpapers 均满足）。 */
export type WpEnvelopeFetcher = (
  projectId: string,
  params: WpListParams,
) => Promise<WpListEnvelope>

export interface VisibilityListFilters {
  audit_cycle?: string
  index_status?: string
  file_status?: string
  assigned_to?: string
}

export interface UseVisibilityWorkpaperListOptions {
  /** 初始每页大小（服务端范围 [1,100]）。 */
  pageSize?: number
  /** 初始排序字段（已登记：wp_code/audit_cycle/index_status/file_status/created_at/updated_at）。 */
  sort?: string
  sortDir?: 'asc' | 'desc'
}

const EMPTY_STATS: WpVisibilityStats = { by_index_status: {}, by_file_status: {} }

/**
 * @param fetcher 服务端分页拉取器（listWorkpapersPaged / listMyLeadWorkpapers）
 * @param projectIdRef 获取当前 project_id 的函数（响应式来源）
 */
export function useVisibilityWorkpaperList(
  fetcher: WpEnvelopeFetcher,
  projectIdRef: () => string,
  options: UseVisibilityWorkpaperListOptions = {},
) {
  const items = ref<VisibilityWpItem[]>([])
  const total = ref(0)
  const stats = ref<WpVisibilityStats>({ ...EMPTY_STATS })
  const page = ref(1)
  const pageSize = ref(options.pageSize ?? 20)
  const sort = ref(options.sort ?? 'wp_code')
  const sortDir = ref<'asc' | 'desc'>(options.sortDir ?? 'asc')
  const loading = ref(false)
  /** External_Not_Found 占位文案；非空时视图应显示占位、隐藏列表。 */
  const notFoundMessage = ref('')

  const filters = reactive<VisibilityListFilters>({})

  /** 清空所有缓存的列表项/名称/统计（Req 12.7：拒绝后不得闪现缓存内容）。 */
  function clearCache() {
    items.value = []
    total.value = 0
    stats.value = { ...EMPTY_STATS }
  }

  function isNotFound(err: any): boolean {
    return err?.response?.status === 404
  }

  /**
   * 拉取当前页。``visibility_mode`` 仅作 UX 透传（不改变服务端授权）。
   * 404 → 清缓存 + 设占位文案；其他错误 → 清缓存并抛出交由上层 handleApiError。
   */
  async function load(opts: { visibilityMode?: string } = {}) {
    const pid = projectIdRef()
    if (!pid) {
      clearCache()
      return
    }
    loading.value = true
    notFoundMessage.value = ''
    try {
      const params: WpListParams = {
        page: page.value,
        page_size: pageSize.value,
        sort: sort.value,
        sort_dir: sortDir.value,
      }
      if (filters.audit_cycle) params.audit_cycle = filters.audit_cycle
      if (filters.index_status) params.index_status = filters.index_status
      if (filters.file_status) params.file_status = filters.file_status
      if (filters.assigned_to) params.assigned_to = filters.assigned_to
      // 仅 UX 透传（Req 12.1–12.3）：服务端忽略之，授权只来自服务端身份。
      if (opts.visibilityMode) params.visibility_mode = opts.visibilityMode

      const env = await fetcher(pid, params)
      items.value = env.items
      total.value = env.total
      stats.value = env.stats
      page.value = env.page
      pageSize.value = env.page_size
    } catch (err: any) {
      // 拒绝/不可访问：统一占位 + 清缓存，绝不显示内部原因或旧缓存名称（Req 12.7）。
      clearCache()
      if (isNotFound(err)) {
        notFoundMessage.value = EXTERNAL_NOT_FOUND_MESSAGE
      } else {
        throw err
      }
    } finally {
      loading.value = false
    }
  }

  function reload() {
    page.value = 1
    return load()
  }

  function goToPage(p: number) {
    page.value = p
    return load()
  }

  function setSort(field: string, dir: 'asc' | 'desc' = 'asc') {
    sort.value = field
    sortDir.value = dir
    page.value = 1
    return load()
  }

  function setFilter<K extends keyof VisibilityListFilters>(key: K, value: VisibilityListFilters[K]) {
    filters[key] = value
    page.value = 1
    return load()
  }

  /** 底稿是否已生成 → 可执行文件动作（读取/下载/编辑）。nullable wp → false（Req 12.9）。 */
  function canOpen(item: VisibilityWpItem): boolean {
    return item.wp_generated === true && !!item.wp_id
  }

  /** nullable wp 的展示文案（Req 12.8）。 */
  const NOT_GENERATED_LABEL = '底稿尚未生成'

  const isEmpty = computed(() => !loading.value && items.value.length === 0 && !notFoundMessage.value)
  const hasNotFound = computed(() => !!notFoundMessage.value)

  return {
    // state
    items,
    total,
    stats,
    page,
    pageSize,
    sort,
    sortDir,
    loading,
    notFoundMessage,
    filters,
    // derived
    isEmpty,
    hasNotFound,
    // actions
    load,
    reload,
    goToPage,
    setSort,
    setFilter,
    clearCache,
    // helpers
    canOpen,
    NOT_GENERATED_LABEL,
    FILE_STATUS_NOT_GENERATED,
    EXTERNAL_NOT_FOUND_MESSAGE,
  }
}
