import { describe, expect, it, vi } from 'vitest'

import {
  createChecklistCasClient,
  isChecklistDraftAccessDenied,
  isNonRetryableChecklistSaveError,
  makeChecklistDraft,
  readChecklistDraft,
} from './checklistCas'

describe('checklistCas', () => {
  it('sends the remembered version and advances only from server receipts', async () => {
    const put = vi.fn()
      .mockResolvedValueOnce({
        data: [{ item_id: 'row-1', version: 'v2', remark: 'first' }],
      })
      .mockResolvedValueOnce({
        items: [{ item_id: 'row-1', updated_at: 'v3', remark: 'second' }],
      })
    const cas = createChecklistCasClient(put)
    cas.remember({ data: [{ item_id: 'row-1', version: 'v1' }] })

    await cas.save({ wpId: 'wp-1', projectId: 'project-1', items: [{ item_id: 'row-1', remark: 'first' }] })
    await cas.save({ wpId: 'wp-1', projectId: 'project-1', items: [{ item_id: 'row-1', remark: 'second' }] })

    expect(put).toHaveBeenNthCalledWith(
      1,
      '/api/workpapers/wp-1/checklist-responses',
      {
        project_id: 'project-1',
        require_if_match: true,
        items: [{
          item_id: 'row-1', conclusion: null, remark: 'first', if_match: 'v1',
        }],
      },
      { _dedupe: false },
    )
    expect((put.mock.calls[1][1] as any).items[0].if_match).toBe('v2')
    expect(cas.version('row-1')).toBe('v3')
  })

  it('只在调用方显式传入时发送 wp_ref，保留“省略”与“清空”的语义差异', async () => {
    const put = vi.fn().mockResolvedValue({ data: [] })
    const cas = createChecklistCasClient(put)

    await cas.save({
      wpId: 'wp-1',
      items: [{ item_id: 'row-1', remark: '只改备注' }],
    })
    await cas.save({
      wpId: 'wp-1',
      items: [{ item_id: 'row-1', wp_ref: null }],
    })

    const omitted = (put.mock.calls[0][1] as any).items[0]
    const explicitNull = (put.mock.calls[1][1] as any).items[0]
    expect(omitted).not.toHaveProperty('wp_ref')
    expect(explicitNull).toMatchObject({ item_id: 'row-1', wp_ref: null })
  })

  it('allows a new item without fabricating a version but keeps strict mode enabled', async () => {
    const put = vi.fn().mockResolvedValue({
      data: [{ item_id: 'new-row', version: 'v1' }],
    })
    const cas = createChecklistCasClient(put)

    await cas.save({ wpId: 'wp-2', items: [{ item_id: 'new-row', conclusion: 'Y' }] })

    const body = put.mock.calls[0][1] as any
    expect(body.require_if_match).toBe(true)
    expect(body.items[0]).not.toHaveProperty('if_match')
    expect(cas.version('new-row')).toBe('v1')
  })

  it('does not advance the baseline when the server rejects the write', async () => {
    const conflict = Object.assign(new Error('版本冲突'), { response: { status: 409 } })
    const put = vi.fn().mockRejectedValue(conflict)
    const cas = createChecklistCasClient(put)
    cas.remember([{ item_id: 'row-1', version: 'v1' }])

    await expect(cas.save({
      wpId: 'wp-3', items: [{ item_id: 'row-1', remark: 'local' }],
    })).rejects.toBe(conflict)

    expect(cas.version('row-1')).toBe('v1')
  })

  it('identifies deterministic 4xx rejections that must not be retried', () => {
    for (const status of [409, 428, 423, 422, '403']) {
      expect(isNonRetryableChecklistSaveError({ response: { status } })).toBe(true)
    }
    expect(isNonRetryableChecklistSaveError({ response: { status: 500 } })).toBe(false)
    expect(isNonRetryableChecklistSaveError(new Error('网络断开'))).toBe(false)
  })

  it('identifies authentication failures that must not restore local drafts', () => {
    expect(isChecklistDraftAccessDenied({ response: { status: 401 } })).toBe(true)
    expect(isChecklistDraftAccessDenied({ response: { status: '403' } })).toBe(true)
    expect(isChecklistDraftAccessDenied({ response: { status: 409 } })).toBe(false)
    expect(isChecklistDraftAccessDenied(new Error('network'))).toBe(false)
  })

  it('保留被原子拒绝批次的人工确认标记，页面重建后仍禁止自动重放', () => {
    const draft = makeChecklistDraft(
      { item_id: 'row-1', conclusion: 'Y', remark: '待处理' },
      'version-before-conflict',
      true,
    )
    expect(readChecklistDraft<typeof draft.item>(JSON.parse(JSON.stringify(draft)))).toEqual(draft)
  })

  it('serializes the local payload together with its original CAS baseline', () => {
    const draft = makeChecklistDraft(
      { item_id: 'row-1', conclusion: 'Y', remark: '本地修改' },
      'version-before-conflict',
    )
    expect(readChecklistDraft<typeof draft.item>(JSON.parse(JSON.stringify(draft)))).toEqual(draft)
    // 旧格式没有基线时不能凭空伪造版本，调用方应避免自动覆盖当前服务器行。
    expect(readChecklistDraft({ item_id: 'legacy', remark: '旧草稿' })).toEqual({
      item: { item_id: 'legacy', remark: '旧草稿' },
    })
  })
})
