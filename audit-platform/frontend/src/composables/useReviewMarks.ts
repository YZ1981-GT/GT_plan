/**
 * useReviewMarks — 复核标记 CRUD composable
 *
 * 通过 cell_annotations API 管理复核标记（annotation_type='review_mark'），
 * 提供创建/查询/状态颜色/统计等功能。
 *
 * Foundation Sprint 1 Task 1.7
 */

import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

export type ReviewStatus = 'reviewed' | 'pending' | 'questioned'

export interface ReviewMark {
  id: string
  wp_id: string
  sheet_name: string
  cell_ref: string
  status: ReviewStatus
  content: string
  author_id: string
  author_name?: string
  created_at: string
  updated_at?: string
}

// 状态 → 颜色映射
const STATUS_COLOR_MAP: Record<ReviewStatus, string> = {
  reviewed: '#28A745',    // 绿色
  pending: '#6C757D',     // 灰色
  questioned: '#FFC23D',  // 橙色
}

/**
 * 复核标记 composable
 */
export function useReviewMarks(projectId: Ref<string>) {
  const marks = ref<ReviewMark[]>([])
  const loading = ref(false)

  /**
   * 创建复核标记
   */
  async function createReviewMark(
    wpId: string,
    sheetName: string,
    cellRef: string,
    status: ReviewStatus,
    comment: string = '',
  ): Promise<ReviewMark | null> {
    try {
      const data = await api.post(
        `/api/projects/${projectId.value}/cell-annotations`,
        {
          object_type: 'workpaper',
          object_id: wpId,
          cell_ref: cellRef,
          sheet_name: sheetName,
          annotation_type: 'review_mark',
          status,
          content: comment || `复核标记: ${status}`,
        },
      )
      const mark: ReviewMark = {
        id: data.id,
        wp_id: wpId,
        sheet_name: sheetName,
        cell_ref: cellRef,
        status,
        content: comment,
        author_id: data.author_id || '',
        created_at: data.created_at || new Date().toISOString(),
      }
      marks.value.push(mark)
      return mark
    } catch (e) {
      console.error('createReviewMark failed:', e)
      return null
    }
  }

  /**
   * 查询指定底稿的所有复核标记
   */
  async function getReviewMarks(wpId: string): Promise<ReviewMark[]> {
    loading.value = true
    try {
      const data = await api.get(
        `/api/projects/${projectId.value}/cell-annotations`,
        { params: { object_id: wpId, annotation_type: 'review_mark' } },
      )
      const items: ReviewMark[] = (data?.items || data || []).map((item: any) => ({
        id: item.id,
        wp_id: wpId,
        sheet_name: item.sheet_name || '',
        cell_ref: item.cell_ref || '',
        status: item.status || 'pending',
        content: item.content || '',
        author_id: item.author_id || '',
        author_name: item.author_name,
        created_at: item.created_at || '',
        updated_at: item.updated_at,
      }))
      marks.value = items
      return items
    } catch (e) {
      console.error('getReviewMarks failed:', e)
      return []
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取状态对应的指示器颜色
   */
  function getIndicatorColor(status: ReviewStatus): string {
    return STATUS_COLOR_MAP[status] || STATUS_COLOR_MAP.pending
  }

  /**
   * 复核统计
   */
  const reviewStats = computed(() => {
    const total = marks.value.length
    const reviewed = marks.value.filter(m => m.status === 'reviewed').length
    const questioned = marks.value.filter(m => m.status === 'questioned').length
    const pending = marks.value.filter(m => m.status === 'pending').length
    return { total, reviewed, questioned, pending }
  })

  /**
   * 删除复核标记
   */
  async function deleteReviewMark(markId: string): Promise<boolean> {
    try {
      await api.delete(
        `/api/projects/${projectId.value}/cell-annotations/${markId}`,
      )
      marks.value = marks.value.filter(m => m.id !== markId)
      return true
    } catch (e) {
      console.error('deleteReviewMark failed:', e)
      return false
    }
  }

  /**
   * 更新复核标记状态
   */
  async function updateReviewMark(
    markId: string,
    updates: { status?: ReviewStatus; content?: string },
  ): Promise<boolean> {
    try {
      await api.put(
        `/api/projects/${projectId.value}/cell-annotations/${markId}`,
        updates,
      )
      const idx = marks.value.findIndex(m => m.id === markId)
      if (idx >= 0) {
        if (updates.status) marks.value[idx].status = updates.status
        if (updates.content !== undefined) marks.value[idx].content = updates.content
      }
      return true
    } catch (e) {
      console.error('updateReviewMark failed:', e)
      return false
    }
  }

  return {
    marks,
    loading,
    createReviewMark,
    getReviewMarks,
    getIndicatorColor,
    reviewStats,
    deleteReviewMark,
    updateReviewMark,
  }
}
