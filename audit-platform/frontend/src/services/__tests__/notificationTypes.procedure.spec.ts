// Feature: procedure-delegation-notification — Task 11 通知 metadata 驱动跳转
//
// 需求 10.8：跳转由 metadata 驱动（不解析中文 content）。
// 需求 9.5/9.6：有 wp_id → 底稿深链（带 task_id/sheet_key/definition_key）；无 wp_id → 我的程序任务页。
// 深链路由与 is_read 无关（已读/未读点击均可跳转）。
import { describe, it, expect } from 'vitest'
import { NOTIFICATION_TYPES, getNotificationJumpRoute } from '../notificationTypes'

describe('notificationTypes — 程序行任务 metadata 驱动跳转 (Task 11)', () => {
  it('有 wp_id：单任务通知跳底稿深链，携带 task_id/sheet_key/definition_key', () => {
    const route = getNotificationJumpRoute(NOTIFICATION_TYPES.PROCEDURE_TASK_ASSIGNED, {
      project_id: 'p1', wp_id: 'wp9', task_id: 't1', sheet_key: 'D2!A1', definition_key: 'def-1',
    })
    expect(route).toContain('/projects/p1/workpapers')
    expect(route).toContain('wp=wp9')
    expect(route).toContain('task_id=t1')
    expect(route).toContain(`sheet_key=${encodeURIComponent('D2!A1')}`)
    expect(route).toContain('definition_key=def-1')
  })

  it('无 wp_id（先委派后生成）：跳我的程序任务页', () => {
    const route = getNotificationJumpRoute(NOTIFICATION_TYPES.PROCEDURE_TASK_ASSIGNED, {
      project_id: 'p1', task_id: 't1', sheet_key: 'D2!A1', definition_key: 'def-1',
    })
    expect(route).toContain('/my-procedures')
    expect(route).toContain('project_id=p1')
  })

  it('批量委派摘要：跳我的程序任务页并带 batch/project 筛选', () => {
    const route = getNotificationJumpRoute(NOTIFICATION_TYPES.PROCEDURE_TASK_DELEGATION_BATCH, {
      kind: 'delegation_batch', batch_id: 'b1', project_id: 'p2',
      filter: { delegation_batch_id: 'b1', project_id: 'p2' },
    })
    expect(route).toContain('/my-procedures')
    expect(route).toContain('project_id=p2')
    expect(route).toContain('batch_id=b1')
  })

  it('reviewer_missing：跳我的程序任务页', () => {
    const route = getNotificationJumpRoute(NOTIFICATION_TYPES.PROCEDURE_TASK_REVIEWER_MISSING, {
      project_id: 'p3', task_id: 't2',
    })
    expect(route).toContain('/my-procedures')
    expect(route).toContain('project_id=p3')
  })

  it('复核消息通知：有 wp_id 走底稿深链', () => {
    const route = getNotificationJumpRoute(NOTIFICATION_TYPES.PROCEDURE_REVIEW_MESSAGE, {
      project_id: 'p1', wp_id: 'wp1', task_id: 't1', sheet_key: 's', definition_key: 'd',
    })
    expect(route).toContain('/projects/p1/workpapers')
    expect(route).toContain('task_id=t1')
  })

  it('路由由 metadata 决定，与 is_read 无关（同 metadata 得同一路由）', () => {
    const meta = { project_id: 'p1', wp_id: 'wp9', task_id: 't1', sheet_key: 's', definition_key: 'd' }
    const r1 = getNotificationJumpRoute(NOTIFICATION_TYPES.PROCEDURE_TASK_REVIEWED, meta)
    const r2 = getNotificationJumpRoute(NOTIFICATION_TYPES.PROCEDURE_TASK_REVIEWED, { ...meta })
    expect(r1).toBe(r2)
    expect(r1).toBeTruthy()
  })

  it('缺 metadata → 返回 null（不构造无效链接）', () => {
    expect(getNotificationJumpRoute(NOTIFICATION_TYPES.PROCEDURE_TASK_ASSIGNED, null)).toBeNull()
    expect(getNotificationJumpRoute(NOTIFICATION_TYPES.PROCEDURE_TASK_ASSIGNED, undefined)).toBeNull()
  })
})
