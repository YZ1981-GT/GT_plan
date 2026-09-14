// Feature: procedure-delegation-visibility-isolation — Task 12
// 验证前端可见性拒绝助手：统一占位、404 判定、深链只定位（Req 12.7/12.9）。
import { describe, it, expect, vi } from 'vitest'
import {
  EXTERNAL_NOT_FOUND_MESSAGE,
  isExternalNotFound,
  buildDeepLinkQuery,
  handleDeepLinkRejection,
} from '../visibilityAccess'

describe('visibilityAccess', () => {
  it('unified placeholder message is fixed and reveals no internal reason', () => {
    expect(EXTERNAL_NOT_FOUND_MESSAGE).toBe('资源不存在或不可访问')
    expect(EXTERNAL_NOT_FOUND_MESSAGE).not.toMatch(/not_found|cross_project|out_of_scope|denied|token/)
  })

  it('isExternalNotFound only matches HTTP 404', () => {
    expect(isExternalNotFound({ response: { status: 404 } })).toBe(true)
    expect(isExternalNotFound({ response: { status: 403 } })).toBe(false)
    expect(isExternalNotFound({ response: { status: 500 } })).toBe(false)
    expect(isExternalNotFound(new Error('network'))).toBe(false)
    expect(isExternalNotFound(undefined)).toBe(false)
  })

  it('buildDeepLinkQuery drops empty locators (only locates)', () => {
    expect(buildDeepLinkQuery({ wp: 'wp-1', task_id: 't1', sheet_key: 's1', definition_key: 'd1' }))
      .toEqual({ wp: 'wp-1', task_id: 't1', sheet_key: 's1', definition_key: 'd1' })
    // nullable wp → no wp key (不定位未生成底稿)
    expect(buildDeepLinkQuery({ wp: null, task_id: 't1' })).toEqual({ task_id: 't1' })
    expect(buildDeepLinkQuery({})).toEqual({})
  })

  it('handleDeepLinkRejection clears cache and returns the unified placeholder', () => {
    const clear = vi.fn()
    const msg = handleDeepLinkRejection(clear)
    expect(clear).toHaveBeenCalledTimes(1)
    expect(msg).toBe('资源不存在或不可访问')
  })
})
