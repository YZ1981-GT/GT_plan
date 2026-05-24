/**
 * useRangePaginator — 大 range 前端分页逻辑
 *
 * - rows > 100 → 启用分页（默认 pageSize=100）
 * - rows > 5000 → 强制分页 + 禁用「全部展开」
 * - 切页 = allRows.slice((page-1)*size, page*size)，纯前端切片不重发请求
 * - 「全部展开」→ 确认对话框警告后 pageSize = rows.length
 *
 * Validates: Requirements 11.1, 11.5
 * Feature: advanced-query-enhancements-p1p2, Property 22: Pagination threshold enforcement
 */

import { ref, computed } from 'vue'

export const PAGINATION_THRESHOLD = 100
export const FORCE_PAGINATION_THRESHOLD = 5000
export const DEFAULT_PAGE_SIZE = 100
export const PAGE_SIZE_OPTIONS = [50, 100, 200, 500] as const

export interface PaginatorState {
  /** 是否启用分页 */
  paginationEnabled: boolean
  /** 是否强制分页（禁用全部展开） */
  forcePagination: boolean
  /** 是否禁用全部展开按钮 */
  expandAllDisabled: boolean
  /** 当前页码（1-based） */
  currentPage: number
  /** 每页行数 */
  pageSize: number
  /** 总行数 */
  totalRows: number
  /** 当前页数据切片 */
  pageData: any[]
  /** 总页数 */
  totalPages: number
}

/**
 * 纯函数：判断分页状态
 */
export function getPaginationState(totalRows: number, pageSize: number = DEFAULT_PAGE_SIZE): {
  paginationEnabled: boolean
  forcePagination: boolean
  expandAllDisabled: boolean
} {
  const paginationEnabled = totalRows > PAGINATION_THRESHOLD
  const forcePagination = totalRows > FORCE_PAGINATION_THRESHOLD
  const expandAllDisabled = forcePagination
  return { paginationEnabled, forcePagination, expandAllDisabled }
}

/**
 * 纯函数：获取当前页数据切片
 */
export function getPageSlice<T>(allRows: T[], page: number, pageSize: number): T[] {
  const start = (page - 1) * pageSize
  const end = start + pageSize
  return allRows.slice(start, end)
}

/**
 * Vue composable：响应式分页器
 */
export function useRangePaginator<T = any>() {
  const allRows = ref<T[]>([]) as { value: T[] }
  const currentPage = ref(1)
  const pageSize = ref(DEFAULT_PAGE_SIZE)

  const totalRows = computed(() => allRows.value.length)

  const paginationState = computed(() =>
    getPaginationState(totalRows.value, pageSize.value)
  )

  const paginationEnabled = computed(() => paginationState.value.paginationEnabled)
  const forcePagination = computed(() => paginationState.value.forcePagination)
  const expandAllDisabled = computed(() => paginationState.value.expandAllDisabled)

  const totalPages = computed(() =>
    Math.ceil(totalRows.value / pageSize.value) || 1
  )

  const pageData = computed(() =>
    paginationEnabled.value
      ? getPageSlice(allRows.value, currentPage.value, pageSize.value)
      : allRows.value
  )

  function setData(rows: T[]) {
    allRows.value = rows
    currentPage.value = 1
  }

  function goToPage(page: number) {
    currentPage.value = Math.max(1, Math.min(page, totalPages.value))
  }

  function setPageSize(size: number) {
    pageSize.value = size
    currentPage.value = 1
  }

  /**
   * 全部展开：将 pageSize 设为总行数（需先确认）
   */
  function expandAll() {
    if (expandAllDisabled.value) return
    pageSize.value = totalRows.value
    currentPage.value = 1
  }

  return {
    allRows,
    currentPage,
    pageSize,
    totalRows,
    totalPages,
    paginationEnabled,
    forcePagination,
    expandAllDisabled,
    pageData,
    setData,
    goToPage,
    setPageSize,
    expandAll,
  }
}
