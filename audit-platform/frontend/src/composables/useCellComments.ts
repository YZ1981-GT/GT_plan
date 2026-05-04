/**
 * 单元格批注与复核标记 composable
 * 对接 /api/cell-comments API，提供批注/复核的 CRUD 和状态管理
 */
import { ref } from 'vue'
import http from '@/utils/http'

export interface CellComment {
  id: string
  project_id: string
  year: number
  module: string
  sheet_key: string
  row_idx: number
  col_idx: number
  comment_type: 'comment' | 'review'
  comment: string
  status: string
  row_name: string
  col_name: string
  created_at?: string
  updated_at?: string
}

export function useCellComments(projectId: () => string, year: () => number, module: string) {
  const comments = ref<CellComment[]>([])
  const loading = ref(false)

  /** 加载模块下所有批注/复核 */
  async function loadComments(sheetKey?: string) {
    const pid = projectId()
    const y = year()
    if (!pid || !y) return
    loading.value = true
    try {
      const url = sheetKey
        ? `/api/cell-comments/${pid}/${y}/${module}/${sheetKey}`
        : `/api/cell-comments/${pid}/${y}/${module}`
      const { data } = await http.get(url)
      comments.value = Array.isArray(data) ? data : []
    } catch {
      comments.value = []
    } finally {
      loading.value = false
    }
  }

  /** 保存批注 */
  async function saveComment(params: {
    sheetKey: string
    rowIdx: number
    colIdx: number
    comment: string
    rowName?: string
    colName?: string
  }) {
    const pid = projectId()
    const y = year()
    if (!pid || !y) return null
    try {
      const { data } = await http.put(`/api/cell-comments/${pid}/${y}`, {
        module,
        sheet_key: params.sheetKey,
        row_idx: params.rowIdx,
        col_idx: params.colIdx,
        comment_type: 'comment',
        comment: params.comment,
        status: '',
        row_name: params.rowName || '',
        col_name: params.colName || '',
      })
      // 更新本地缓存
      const idx = comments.value.findIndex(
        c => c.row_idx === params.rowIdx && c.col_idx === params.colIdx
          && c.sheet_key === params.sheetKey && c.comment_type === 'comment'
      )
      if (idx >= 0) comments.value[idx] = data
      else comments.value.push(data)
      return data as CellComment
    } catch {
      return null
    }
  }

  /** 标记/取消复核 */
  async function toggleReview(params: {
    sheetKey: string
    rowIdx: number
    colIdx: number
    status: 'reviewed' | 'pending'
    rowName?: string
    colName?: string
  }) {
    const pid = projectId()
    const y = year()
    if (!pid || !y) return null
    try {
      const { data } = await http.put(`/api/cell-comments/${pid}/${y}`, {
        module,
        sheet_key: params.sheetKey,
        row_idx: params.rowIdx,
        col_idx: params.colIdx,
        comment_type: 'review',
        comment: '',
        status: params.status,
        row_name: params.rowName || '',
        col_name: params.colName || '',
      })
      const idx = comments.value.findIndex(
        c => c.row_idx === params.rowIdx && c.col_idx === params.colIdx
          && c.sheet_key === params.sheetKey && c.comment_type === 'review'
      )
      if (idx >= 0) comments.value[idx] = data
      else comments.value.push(data)
      return data as CellComment
    } catch {
      return null
    }
  }

  /** 删除批注 */
  async function deleteComment(commentId: string) {
    const pid = projectId()
    const y = year()
    if (!pid || !y) return false
    try {
      await http.delete(`/api/cell-comments/${pid}/${y}/${commentId}`)
      comments.value = comments.value.filter(c => c.id !== commentId)
      return true
    } catch {
      return false
    }
  }

  /** 查询某单元格是否有批注 */
  function hasComment(sheetKey: string, rowIdx: number, colIdx: number): boolean {
    return comments.value.some(
      c => c.sheet_key === sheetKey && c.row_idx === rowIdx
        && c.col_idx === colIdx && c.comment_type === 'comment'
    )
  }

  /** 查询某单元格是否已复核 */
  function isReviewed(sheetKey: string, rowIdx: number, colIdx: number): boolean {
    return comments.value.some(
      c => c.sheet_key === sheetKey && c.row_idx === rowIdx
        && c.col_idx === colIdx && c.comment_type === 'review' && c.status === 'reviewed'
    )
  }

  /** 获取某单元格的批注文本 */
  function getComment(sheetKey: string, rowIdx: number, colIdx: number): CellComment | undefined {
    return comments.value.find(
      c => c.sheet_key === sheetKey && c.row_idx === rowIdx
        && c.col_idx === colIdx && c.comment_type === 'comment'
    )
  }

  /** 生成单元格 CSS 类名（含批注/复核标记） */
  function commentCellClass(sheetKey: string, rowIdx: number, colIdx: number): string {
    const classes: string[] = []
    if (hasComment(sheetKey, rowIdx, colIdx)) classes.push('gt-cell--has-comment')
    if (isReviewed(sheetKey, rowIdx, colIdx)) classes.push('gt-cell--reviewed')
    return classes.join(' ')
  }

  /** 当前 sheet 的批注统计 */
  function sheetStats(sheetKey: string) {
    const sheetComments = comments.value.filter(c => c.sheet_key === sheetKey)
    return {
      commentCount: sheetComments.filter(c => c.comment_type === 'comment').length,
      reviewedCount: sheetComments.filter(c => c.comment_type === 'review' && c.status === 'reviewed').length,
    }
  }

  return {
    comments,
    loading,
    loadComments,
    saveComment,
    toggleReview,
    deleteComment,
    hasComment,
    isReviewed,
    getComment,
    commentCellClass,
    sheetStats,
  }
}
