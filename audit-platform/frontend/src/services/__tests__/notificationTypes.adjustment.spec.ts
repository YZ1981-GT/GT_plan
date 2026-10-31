/**
 * 调整分录复核类通知的跳转（spec adjustment-hall-entry-review-closure 需求 4.5）：点通知 → 调整大厅 ?focus= 定位该分录，
 * 带分录年度；待复核 / 已驳回带状态筛选。协作通知仍是 ?group=（打开协作对话框）。
 */
import { describe, expect, it } from 'vitest'
import { NOTIFICATION_LABELS, NOTIFICATION_TYPES as T, getNotificationJumpRoute } from '../notificationTypes'

const META = { project_id: 'p1', object_id: 'g1', year: 2025 }

describe('调整分录通知跳转', () => {
  it.each([
    [T.ADJ_REVIEW_SUBMITTED, '/projects/p1/adjustments?focus=g1&year=2025&status=pending_review'],
    [T.ADJ_REVIEW_REJECTED, '/projects/p1/adjustments?focus=g1&year=2025&status=rejected'],
    [T.ADJ_REVIEW_APPROVED, '/projects/p1/adjustments?focus=g1&year=2025'],
    [T.ADJ_REVIEW_REVOKED, '/projects/p1/adjustments?focus=g1&year=2025'],
    [T.ADJ_APPROVED_IMPACT, '/projects/p1/adjustments?focus=g1&year=2025'],
    [T.ADJ_SYNC_ARRIVED, '/projects/p1/adjustments?focus=g1&year=2025'],
    [T.ADJ_COLLAB_ASSIGNED, '/projects/p1/adjustments?group=g1'],
  ])('%s', (type, expected) => {
    expect(getNotificationJumpRoute(type, META)).toBe(expected)
  })

  it('底稿推送带受影响底稿时跳底稿工作台；没有项目不跳', () => {
    expect(getNotificationJumpRoute(T.ADJ_SYNC_ARRIVED, { ...META, affected_wp_codes: ['D2'] }))
      .toBe('/projects/p1/workpapers?view=workbench&highlight=D2')
    expect(getNotificationJumpRoute(T.ADJ_REVIEW_SUBMITTED, { object_id: 'g1' })).toBeFalsy()
  })

  it('新类型都有中文名', () => {
    for (const t of [T.ADJ_REVIEW_SUBMITTED, T.ADJ_REVIEW_APPROVED, T.ADJ_REVIEW_REJECTED, T.ADJ_REVIEW_REVOKED,
      T.ADJ_APPROVED_IMPACT, T.ADJ_SYNC_ARRIVED]) {
      expect(NOTIFICATION_LABELS[t]).toMatch(/[\u4e00-\u9fa5]/)
    }
  })
})
