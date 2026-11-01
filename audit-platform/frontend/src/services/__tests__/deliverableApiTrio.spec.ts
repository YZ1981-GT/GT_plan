import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api }))

import { createTrioJob, getTrioHistory, getTrioItemAttempts } from '../deliverableApi'

describe('正式三件套 API 契约', () => {
  beforeEach(() => vi.clearAllMocks())

  it('创建任务把 year 放 query，body 保持空对象', async () => {
    api.post.mockResolvedValue({ job_id: 'j1', status: 'succeeded' })
    await createTrioJob('p1', 2025)
    expect(api.post).toHaveBeenCalledWith(
      '/api/projects/p1/deliverables/trio',
      {},
      { params: { year: 2025 }, _silent: true },
    )
  })

  it('历史与尝试列表按后端 envelope 单层解包', async () => {
    api.get.mockResolvedValueOnce({ jobs: [{ id: 'j1' }] })
      .mockResolvedValueOnce({ item_id: 'i1', attempts: [{ id: 'a1' }] })
    expect(await getTrioHistory('p1', 2025)).toEqual([{ id: 'j1' }])
    expect(await getTrioItemAttempts('p1', 'i1')).toEqual([{ id: 'a1' }])
  })

  it('交付中心主按钮不再调用旧 full-deliverables', () => {
    const source = readFileSync(resolve(__dirname, '../../views/DeliverableCenter.vue'), 'utf8')
    expect(source).toContain('createTrioJob(')
    expect(source).toContain('checkTrioReadiness(')
    expect(source).not.toContain('createFullDeliverables(')
  })
})
