import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { createChecklistDraftStore } from '../checklistDraftStore'
import {
  clearChecklistDraftsOnLogout,
  checklistDraftKey,
  userScopedWorkpaperDraftKey,
} from '@/composables/workpaper/checklistDraftStorage'

beforeEach(() => sessionStorage.setItem('user', JSON.stringify({ id: 'user-1' })))
afterEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})

describe('checklist strict-CAS 草稿仓', () => {
  it('持久化 payload 与原始 baseVersion，并按当前底稿和 item 归属隔离', () => {
    const versions = new Map([['G9-a', 'v1'], ['G9-b', 'v2']])
    const drafts = createChecklistDraftStore({
      namespace: 'strict-cas-draft',
      wpId: () => 'wp-1',
      ownsItem: (itemId) => itemId.startsWith('G9-'),
      versionOf: (itemId) => versions.get(itemId),
    })

    drafts.store([
      { item_id: 'G9-a', conclusion: 'Y', remark: '本地 A' },
      { item_id: 'other-a', conclusion: 'N', remark: '不属于本表单' },
    ])

    expect(drafts.restore()).toEqual([
      { item: { item_id: 'G9-a', conclusion: 'Y', remark: '本地 A' }, baseVersion: 'v1' },
    ])
    expect(localStorage.getItem('strict-cas-draft:user-1:wp-1:other-a')).toBeNull()
  })

  it('清除时仍按 item 归属隔离，不能删除同一 namespace 中其他 formData 的草稿', () => {
    const g1Drafts = createChecklistDraftStore({
      namespace: 'strict-cas-draft',
      wpId: () => 'wp-1',
      ownsItem: (itemId) => itemId.startsWith('G1-'),
      versionOf: () => 'v1',
    })
    g1Drafts.store([{ item_id: 'G1-a', conclusion: null, remark: 'G1 草稿' }])
    localStorage.setItem('strict-cas-draft:user-1:wp-1:G3-a', JSON.stringify({
      item: { item_id: 'G3-a', conclusion: null, remark: 'G3 草稿' },
      baseVersion: 'v1',
    }))

    g1Drafts.clear([
      { item_id: 'G1-a', conclusion: null, remark: 'G1 草稿' },
      { item_id: 'G3-a', conclusion: null, remark: '不属于 G1' },
    ])

    expect(localStorage.getItem('strict-cas-draft:user-1:wp-1:G1-a')).toBeNull()
    expect(localStorage.getItem('strict-cas-draft:user-1:wp-1:G3-a')).toContain('G3 草稿')
  })

  it('只在成功后清除对应草稿，且保留旧格式草稿供调用方 fail-closed 裁决', () => {
    const drafts = createChecklistDraftStore({
      namespace: 'strict-cas-draft',
      wpId: () => 'wp-1',
      ownsItem: () => true,
      versionOf: () => 'v1',
    })
    drafts.store([{ item_id: 'a', conclusion: null, remark: 'A' }])
    localStorage.setItem('strict-cas-draft:user-1:wp-1:legacy', JSON.stringify({
      item_id: 'legacy', conclusion: null, remark: '旧草稿',
    }))

    drafts.clear([{ item_id: 'a', conclusion: null, remark: 'A' }])

    expect(localStorage.getItem('strict-cas-draft:user-1:wp-1:a')).toBeNull()
    expect(drafts.restore()).toEqual([
      { item: { item_id: 'legacy', conclusion: null, remark: '旧草稿' } },
    ])
  })
})


describe('checklist 草稿身份隔离', () => {
  it('草稿键绑定当前用户，没有已知身份时 fail-closed', () => {
    expect(checklistDraftKey('strict-cas-draft', 'wp-1', 'G1-a')).toBe('strict-cas-draft:user-1:wp-1:G1-a')
    expect(userScopedWorkpaperDraftKey('gt:stocktake-draft', ['project-1', 'wp-1', 'stocktake_A']))
      .toBe('gt:stocktake-draft:user-1:project-1:wp-1:stocktake_A')
    sessionStorage.removeItem('user')
    expect(checklistDraftKey('strict-cas-draft', 'wp-1', 'G1-a')).toBeNull()
  })

  it('登出清理所有受管新旧草稿键，保留无关的本地设置', () => {
    localStorage.setItem('strict-cas-draft:user-1:wp-1:G1-a', 'new')
    localStorage.setItem('strict-cas-draft:wp-1:G1-a', 'legacy')
    localStorage.setItem('g9-draft:user-2:wp-1:G9-a', 'other-user')
    localStorage.setItem('g7-main-draft:legacy-wp:G7-a', 'legacy-g7')
    localStorage.setItem('h10-draft:legacy-wp:H10-a', 'legacy-h10')
    localStorage.setItem('gt:stocktake-draft:legacy', 'legacy-stocktake')
    localStorage.setItem('gt:h-stocktake-draft:legacy', 'legacy-h-stocktake')
    localStorage.setItem('gt_wp_offline_wp_sheet', 'offline')
    localStorage.setItem('gt_wp_offline_index', 'offline-index')
    localStorage.setItem('theme', 'dark')

    clearChecklistDraftsOnLogout()

    expect(localStorage.getItem('strict-cas-draft:user-1:wp-1:G1-a')).toBeNull()
    expect(localStorage.getItem('strict-cas-draft:wp-1:G1-a')).toBeNull()
    expect(localStorage.getItem('g9-draft:user-2:wp-1:G9-a')).toBeNull()
    expect(localStorage.getItem('g7-main-draft:legacy-wp:G7-a')).toBeNull()
    expect(localStorage.getItem('h10-draft:legacy-wp:H10-a')).toBeNull()
    expect(localStorage.getItem('gt:stocktake-draft:legacy')).toBeNull()
    expect(localStorage.getItem('gt:h-stocktake-draft:legacy')).toBeNull()
    expect(localStorage.getItem('gt_wp_offline_wp_sheet')).toBeNull()
    expect(localStorage.getItem('gt_wp_offline_index')).toBeNull()
    expect(localStorage.getItem('theme')).toBe('dark')
  })
})


it('切换登录用户后不会恢复前一用户的未提交草稿', () => {
  const userOne = createChecklistDraftStore({
    namespace: 'strict-cas-draft',
    wpId: () => 'wp-1',
    ownsItem: () => true,
    versionOf: () => 'v1',
  })
  userOne.store([{ item_id: 'G1-a', conclusion: null, remark: '用户一草稿' }])

  sessionStorage.setItem('user', JSON.stringify({ id: 'user-2' }))
  const userTwo = createChecklistDraftStore({
    namespace: 'strict-cas-draft',
    wpId: () => 'wp-1',
    ownsItem: () => true,
    versionOf: () => 'v1',
  })

  expect(userTwo.restore()).toEqual([])
  expect(userOne.restore()).toEqual([])
  sessionStorage.setItem('user', JSON.stringify({ id: 'user-1' }))
  expect(userOne.restore()).toMatchObject([{ item: { remark: '用户一草稿' } }])
})


it('原子拒绝批次的草稿持久化需要确认标记，普通新编辑会覆盖该标记', () => {
  const drafts = createChecklistDraftStore({
    namespace: 'strict-cas-draft',
    wpId: () => 'wp-1',
    ownsItem: () => true,
    versionOf: () => 'v1',
  })
  const item = { item_id: 'G1-a', conclusion: null, remark: '冲突内容' }
  drafts.markRecoveryRequired([item])
  expect(drafts.restore()).toEqual([{ item, baseVersion: 'v1', requiresConfirmation: true }])

  drafts.store([{ ...item, remark: '用户再次编辑' }])
  expect(drafts.restore()).toEqual([{
    item: { ...item, remark: '用户再次编辑' },
    baseVersion: 'v1',
  }])
})


it('同一底稿的一条损坏草稿不能阻断后续有效草稿恢复', () => {
  const drafts = createChecklistDraftStore({
    namespace: 'strict-cas-draft',
    wpId: () => 'wp-1',
    ownsItem: () => true,
    versionOf: () => 'v1',
  })
  localStorage.setItem('strict-cas-draft:user-1:wp-1:broken', '{not-json')
  drafts.store([{ item_id: 'valid', conclusion: 'Y', remark: '可恢复内容' }])

  expect(drafts.restore()).toEqual([{
    item: { item_id: 'valid', conclusion: 'Y', remark: '可恢复内容' },
    baseVersion: 'v1',
  }])
})