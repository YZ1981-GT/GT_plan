import { describe, expect, it, vi } from 'vitest'

import { createChecklistCasClient } from './checklistCas'

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
          item_id: 'row-1', conclusion: null, remark: 'first', wp_ref: null, if_match: 'v1',
        }],
      },
      { _dedupe: false },
    )
    expect((put.mock.calls[1][1] as any).items[0].if_match).toBe('v2')
    expect(cas.version('row-1')).toBe('v3')
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
})
