/**
 * useNoteContentTemplate：预检 / 保存载荷与后端严格 schema 一致（第二轮复盘 #6a）。
 *
 * 首版预检只发 query `year`、无 body（后端已改为 SnapshotPreviewRequest ⇒ 422）；
 * 保存失败按 detail 字符串 includes('STALE') 判断（后端改为 {error_code} 后恒不命中）。
 *
 * #6c：请求一律 `_silent`（全局拦截器不再另弹一次，422 也不会漏出 pydantic 英文）；
 * 列表失败清空旧列表并留错误态（选择器据此显示「加载失败 + 重试」而非「暂无模板」）；
 * 只有最后一次列表请求能落状态（被去重取消的旧请求不得覆盖新结果）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const post = vi.fn()
const get = vi.fn()
const warning = vi.fn()
const error = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { post: (...a: unknown[]) => post(...a), get: (...a: unknown[]) => get(...a), delete: vi.fn() },
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: (...a: unknown[]) => warning(...a), error: (...a: unknown[]) => error(...a) },
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn() } }))

import { useNoteContentTemplate } from '../useNoteContentTemplate'

const INPUT = { year: 2025, name: '  全套模板 ', description: '', ownerScope: 'group' as const }

function http500() {
  return Object.assign(new Error('Request failed with status code 500'), { response: { status: 500, data: '' } })
}

beforeEach(() => {
  post.mockReset()
  get.mockReset()
  warning.mockReset()
  error.mockReset()
})

describe('useNoteContentTemplate', () => {
  it('预检发 JSON body（无正文、无来源 owner），名称去首尾空白；请求静默全局拦截器', async () => {
    const t = useNoteContentTemplate({ projectId: ref('p1') })
    post.mockResolvedValueOnce({ snapshot_digest: 'd'.repeat(64), quality_summary: { total: 3 } })
    await t.previewSnapshot(INPUT)
    expect(post).toHaveBeenCalledWith('/api/projects/p1/note-content-templates/snapshot-preview',
      { year: 2025, name: '全套模板', description: null, owner_scope: 'group' }, { _silent: true })
  })

  it('保存携 digest；来源变化 STALE_SNAPSHOT ⇒ 只提示一次「重新预检」并返回 null', async () => {
    const t = useNoteContentTemplate({ projectId: ref('p1') })
    post.mockRejectedValueOnce(Object.assign(new Error('409'), {
      response: { status: 409, data: { detail: { error_code: 'STALE_SNAPSHOT', message: '来源附注在预检后已变化' } } },
    }))
    expect(await t.saveTemplate(INPUT, 'd'.repeat(64))).toBeNull()
    expect(post.mock.calls[0][1]).toEqual({ year: 2025, name: '全套模板', description: null, owner_scope: 'group',
      snapshot_digest: 'd'.repeat(64) })
    expect(post.mock.calls[0][2]).toEqual({ _silent: true })
    expect(t.lastError.value?.code).toBe('STALE_SNAPSHOT')
    expect(warning).toHaveBeenCalledWith('来源附注在预检后已变化，请重新预检')
    expect(error).not.toHaveBeenCalled()
  })

  it('列表分页参数与 total；append 追加下一页', async () => {
    const t = useNoteContentTemplate({ projectId: ref('p1') })
    get.mockResolvedValueOnce({ items: [{ id: 't1', name: '甲' }], total: 2 })
      .mockResolvedValueOnce({ items: [{ id: 't2', name: '乙' }], total: 2 })
    await t.fetchTemplates(1, 0)
    expect(get).toHaveBeenCalledWith('/api/projects/p1/note-content-templates',
      { params: { limit: 1, offset: 0 }, _silent: true })
    await t.fetchTemplates(1, 1, { append: true })
    expect(t.templates.value.map(i => i.id)).toEqual(['t1', 't2'])
    expect(t.total.value).toBe(2)
  })

  it('列表失败：只弹一次中文提示（不漏 axios 英文）、清空旧列表、留错误态；重载成功清除错误', async () => {
    const t = useNoteContentTemplate({ projectId: ref('p1') })
    get.mockResolvedValueOnce({ items: [{ id: 't1', name: '甲' }], total: 1 })
    await t.fetchTemplates()
    get.mockRejectedValueOnce(http500())
    await t.fetchTemplates()
    expect(error).toHaveBeenCalledTimes(1)
    expect(error).toHaveBeenCalledWith('模板列表加载失败（HTTP 500）')
    expect([t.templates.value.length, t.total.value]).toEqual([0, 0])
    expect(t.lastError.value?.message).toBe('模板列表加载失败（HTTP 500）')
    get.mockResolvedValueOnce({ items: [{ id: 't1', name: '甲' }], total: 1 })
    await t.fetchTemplates()
    expect(t.lastError.value).toBeNull()
    expect(t.templates.value).toHaveLength(1)
  })

  it('旧列表请求被新请求取代（去重取消）⇒ 不弹错、不覆盖新结果、不提前结束加载态', async () => {
    const t = useNoteContentTemplate({ projectId: ref('p1') })
    let rejectOld!: (e: unknown) => void
    let resolveNew!: (v: unknown) => void
    get.mockImplementationOnce(() => new Promise((_r, rej) => { rejectOld = rej }))
      .mockImplementationOnce(() => new Promise((res) => { resolveNew = res }))
    const first = t.fetchTemplates()
    const second = t.fetchTemplates()
    rejectOld(Object.assign(new Error('canceled'), { code: 'ERR_CANCELED', name: 'CanceledError' }))
    await first
    expect(t.loading.value).toBe(true)
    expect(t.lastError.value).toBeNull()
    resolveNew({ items: [{ id: 't9', name: '新' }], total: 1 })
    await second
    expect(t.templates.value.map(i => i.id)).toEqual(['t9'])
    expect(t.loading.value).toBe(false)
    expect(error).not.toHaveBeenCalled()
  })

  it('新请求先返回后，迟到的旧请求（成功或失败）都不得覆盖新结果', async () => {
    const t = useNoteContentTemplate({ projectId: ref('p1') })
    const settle: Array<{ ok: (v: unknown) => void; ko: (e: unknown) => void }> = []
    get.mockImplementation(() => new Promise((ok, ko) => { settle.push({ ok, ko }) }))
    const stale1 = t.fetchTemplates()
    const stale2 = t.fetchTemplates()
    const latest = t.fetchTemplates()
    settle[2].ok({ items: [{ id: 'new', name: '新' }], total: 1 })
    await latest
    settle[0].ok({ items: [{ id: 'old', name: '旧' }], total: 1 })
    settle[1].ko(http500())
    await Promise.all([stale1, stale2])
    expect(t.templates.value.map(i => i.id)).toEqual(['new'])
    expect(t.lastError.value).toBeNull()
    expect(error).not.toHaveBeenCalled()
  })
})
