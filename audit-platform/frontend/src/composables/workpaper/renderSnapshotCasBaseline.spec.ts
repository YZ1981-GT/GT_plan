/**
 * render 快照里的 version 必须原样成为保存时的 if_match。
 *
 * K1~K13 与 D2 的宿主只用 render 快照建编辑基线（快照非空就不再 GET），保存走严格 CAS
 * （`require_if_match: true`）：快照不带版本时已有行一保存就 428。后端快照条目现带 `version`
 * （与 GET 回执同口径，见 backend/tests/test_render_snapshot_cas_version.py）；这里锁前端半边：
 * 快照 → hydrate → save 时 PUT 带 `if_match`，且不为补版本偷偷 GET（那会把编辑基线改写成当前版）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), put: vi.fn() },
}))

import { api } from '@/services/apiProxy'
import { collectChecklistResponses } from './checklistPersistenceHelpers'
import { useChecklistPersistence } from './useChecklistPersistence'

/** GtD2AccountsReceivable.vue 里 selfLoad 的函数体（快照 → hydrate 的映射写在这里）。 */
function d2SelfLoadBody(): string {
  const source = readFileSync(
    resolve(__dirname, '../../components/workpaper/GtD2AccountsReceivable.vue'),
    'utf-8',
  ).replace(/\r\n/g, '\n')
  const start = source.indexOf('async function selfLoad(')
  expect(start).toBeGreaterThan(-1)
  const end = source.indexOf('\n}\n', start)
  expect(end).toBeGreaterThan(start)
  return source.slice(start, end)
}

afterEach(() => {
  vi.clearAllMocks()
})

function putBody(): any {
  return vi.mocked(api.put).mock.calls[0][1]
}

describe('render 快照建编辑基线', () => {
  it('K 循环宿主：快照条目的 version 作为 if_match 发出', async () => {
    vi.mocked(api.put).mockResolvedValue({
      data: [{ item_id: 'K9-8-abnormal', remark: '新值', conclusion: null, version: 'v2' }],
    })
    const persistence = useChecklistPersistence({ wpId: ref('wp-k9') })
    persistence.hydrate(collectChecklistResponses(
      { 'K9-8-abnormal': { conclusion: '', remark: '旧值', version: 'v1' } },
    ))

    await persistence.save('K9-8-abnormal', { remark: '新值' })

    expect(putBody().require_if_match).toBe(true)
    expect(putBody().items[0]).toMatchObject({ item_id: 'K9-8-abnormal', if_match: 'v1' })
    expect(api.get).not.toHaveBeenCalled()
    expect(persistence.stateOf('K9-8-abnormal')).toMatchObject({ status: 'saved', serverVersion: 'v2' })
  })

  it('D2 宿主：快照转成数组（带 version / updated_at 两个字段）后同样进 if_match', async () => {
    vi.mocked(api.put).mockResolvedValue({
      data: [{ item_id: 'D2-vc-current-rows', remark: '[]', conclusion: null, version: 'v8' }],
    })
    // D2-7 凭证检查「本期增减变动」区的持久化键（useD2VoucherCheckEnhanced.saveToResponses）
    const snapshot: Record<string, Record<string, unknown>> = {
      'D2-vc-current-rows': { conclusion: '', remark: '[{"voucherNo":"0107"}]', version: 'v7' },
    }
    // 与 GtD2AccountsReceivable.selfLoad 的映射同形
    const items = Object.entries(snapshot).map(([itemId, entry]) => ({
      item_id: itemId,
      conclusion: (entry.conclusion as string | null) ?? null,
      remark: (entry.remark as string | null) ?? null,
      wp_ref: null,
      version: entry.version as string | undefined,
      updated_at: entry.updated_at as string | undefined,
    }))
    const persistence = useChecklistPersistence({ wpId: ref('wp-d2') })
    persistence.hydrate(items)

    await persistence.save('D2-vc-current-rows', { remark: '[]' })

    expect(putBody().items[0].if_match).toBe('v7')
    expect(api.get).not.toHaveBeenCalled()
  })

  it('D2 宿主的 selfLoad 把快照条目的 version / updated_at 原样带进 hydrate（上一条用例的映射与它同形）', () => {
    const body = d2SelfLoadBody()
    expect(body).toMatch(/version:\s*\(entry\?\.version\b/)
    expect(body).toMatch(/updated_at:\s*\(entry\?\.updated_at\b/)
    expect(body).toContain('formData.hydrate(items)')
  })

  it('快照里没有这一行的版本（新行）时不造 if_match', async () => {
    vi.mocked(api.put).mockResolvedValue({
      data: [{ item_id: 'K9-8-new', remark: '首次填写', conclusion: null, version: 'v1' }],
    })
    const persistence = useChecklistPersistence({ wpId: ref('wp-k9') })
    persistence.hydrate(collectChecklistResponses({ 'K9-8-other': { conclusion: '', remark: '已有' } }))

    await persistence.save('K9-8-new', { remark: '首次填写' })

    expect(putBody().require_if_match).toBe(true)
    expect(putBody().items[0]).not.toHaveProperty('if_match')
  })
})
