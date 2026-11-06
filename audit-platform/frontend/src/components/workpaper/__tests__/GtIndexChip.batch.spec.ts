/**
 * 关联底稿 chip 批量解析（spec procedure-chain-hardening-and-java-contracts R15）—— 真实 useAcnr，只替换 http。
 *
 * 原先每个 chip 各发一条 GET /api/acnr/resolve：程序表一屏几十个 chip 就是几十条请求；同一编码出现多次时，
 * 同 URL 的并发 GET 被 utils/http 去重取消先发的那条，被取消的 chip 显示成「底稿不存在」。
 * 现在同一轮渲染合并成 POST /resolve-batch（每批 ≤50、同编码只解析一次、禁用的不解析），命中进 LRU。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: http }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-1' }, path: '/projects/proj-1/workpapers/wp-0/edit', query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import GtIndexChip from '../GtIndexChip.vue'
import {
  BATCH_RESOLVE_FAILED,
  RESOLVE_BATCH_LIMIT,
  invalidateModuleCache,
  resolveIndexBatched,
} from '@/services/acnr'

const components = {
  'el-tag': {
    props: ['type', 'effect', 'size'],
    template: '<span class="el-tag-stub" :data-type="type"><slot /></span>',
  },
  'el-tooltip': {
    props: ['content', 'disabled', 'placement'],
    template: '<div class="el-tooltip-stub" :data-content="content"><slot /></div>',
  },
  'el-dropdown': defineComponent({
    name: 'ElDropdownStub',
    emits: ['command'],
    template: '<div class="el-dropdown-stub"><slot /><slot name="dropdown" /></div>',
  }),
  'el-dropdown-menu': { template: '<div><slot /></div>' },
  'el-dropdown-item': { template: '<div><slot /></div>' },
}

function mountChips(chips: Array<{ value: string; disabled?: boolean; preventNavigate?: boolean }>) {
  const Parent = defineComponent({
    render: () => h('div', chips.map((c, i) => h(GtIndexChip, {
      key: i,
      value: c.value,
      disabled: c.disabled ?? false,
      preventNavigate: c.preventNavigate ?? false,
    }))),
  })
  return mount(Parent, { global: { components } })
}

/** 后端 /resolve-batch：等长结果数组，按 items 顺序 */
function okBatch() {
  http.post.mockImplementation(async (_url: string, body: { items: Array<{ index_ref: string }> }) => ({
    data: body.items.map((it) => ({ found: true, addr_id: it.index_ref.slice(3) })),
  }))
}

const types = (w: ReturnType<typeof mountChips>) => w.findAll('.el-tag-stub').map((t) => t.attributes('data-type'))

beforeEach(() => {
  http.get.mockReset()
  http.post.mockReset()
  invalidateModuleCache()
})

describe('GtIndexChip × resolveIndexBatched', () => {
  it('同一轮渲染的 chip 合并成一次批量请求：同编码只解析一次、禁用的不解析、不发单条 GET', async () => {
    okBatch()
    const w = mountChips([{ value: 'E1-1' }, { value: 'E1-1' }, { value: 'E1-2' }, { value: 'E1-3', disabled: true }])
    await flushPromises()
    expect(http.get).not.toHaveBeenCalled()
    expect(http.post).toHaveBeenCalledTimes(1)
    const [url, body, cfg] = http.post.mock.calls[0]
    expect(url).toBe('/api/acnr/resolve-batch')
    expect(body).toEqual({ items: [{ index_ref: 'wp:E1-1' }, { index_ref: 'wp:E1-2' }], project_id: 'proj-1' })
    expect(cfg).toMatchObject({ _silent: true })
    // 两个 E1-1 都拿到结果（原先同 URL 并发 GET 会取消一个，显示成灰色「底稿不存在」）
    expect(types(w)).toEqual(['primary', 'primary', 'primary', 'info'])
  })

  it(`超过 ${RESOLVE_BATCH_LIMIT} 个编码按批切分（后端每批 ≤50，超出 422）`, async () => {
    okBatch()
    mountChips(Array.from({ length: 60 }, (_, i) => ({ value: `D${i + 1}` })))
    await flushPromises()
    const sizes = http.post.mock.calls.map(([, body]) => body.items.length)
    expect(sizes).toEqual([RESOLVE_BATCH_LIMIT, 10])
  })

  it('命中进缓存：再挂同编码的 chip 不再请求；未命中不缓存', async () => {
    http.post.mockImplementation(async (_url: string, body: { items: Array<{ index_ref: string }> }) => ({
      data: body.items.map((it) => (it.index_ref === 'wp:E1-1' ? { found: true } : { found: false, error: 'ref_not_found' })),
    }))
    mountChips([{ value: 'E1-1' }, { value: 'E1-9' }])
    await flushPromises()
    expect(http.post).toHaveBeenCalledTimes(1)
    const w2 = mountChips([{ value: 'E1-1' }, { value: 'E1-9' }])
    await flushPromises()
    expect(http.post).toHaveBeenCalledTimes(2)
    expect(http.post.mock.calls[1][1].items).toEqual([{ index_ref: 'wp:E1-9' }])
    expect(types(w2)).toEqual(['primary', 'info'])
  })

  it('整批请求失败：每个 chip 显示「暂时无法校验」（不当成底稿不存在、不灰显），结果不缓存', async () => {
    http.post.mockRejectedValueOnce(Object.assign(new Error('HTTP 500'), { response: { status: 500 } }))
    const w = mountChips([{ value: 'E1-1' }, { value: 'E1-2' }])
    await flushPromises()
    expect(types(w)).toEqual(['danger', 'danger'])
    expect(w.findAll('.el-tooltip-stub').map((t) => t.attributes('data-content')))
      .toEqual(['暂时无法校验，仍可点击尝试跳转', '暂时无法校验，仍可点击尝试跳转'])
    okBatch()
    mountChips([{ value: 'E1-1' }])
    await flushPromises()
    expect(http.post).toHaveBeenCalledTimes(2)
  })

  it('项目中任一批次返回治理 409 后，已解析成功的同页 chip 也立即禁用', async () => {
    okBatch()
    const existing = mountChips([{ value: 'E1-1' }])
    await flushPromises()
    expect(types(existing)).toEqual(['primary'])

    const reason = '项目锁定快照缺失，无法按归档时的目录解析'
    http.post.mockRejectedValue(Object.assign(new Error('HTTP 409'), {
      response: {
        status: 409,
        data: { code: 409, error_code: 'ACNR_REGISTRY_SNAPSHOT_MISSING', message: reason },
      },
    }))
    mountChips([{ value: 'D2-1' }])
    await flushPromises()

    expect(types(existing)).toEqual(['info'])
    expect(existing.find('.el-tag-stub').attributes('tabindex')).toBe('-1')
    expect(existing.find('.el-tooltip-stub').attributes('data-content')).toBe(reason)
    await existing.find('.el-tag-stub').trigger('click')
    expect(existing.findComponent(GtIndexChip).emitted('click')).toBeUndefined()
  })

  it('目录治理 409 保留中文终态：chip fail-closed，不伪装成可继续跳转的批失败，也不缓存', async () => {
    const reason = '项目锁定的地址目录版本 20261001000000 快照内容损坏，请联系管理员恢复快照'
    http.post.mockRejectedValue(Object.assign(new Error('HTTP 409'), {
      response: {
        status: 409,
        data: { code: 409, error_code: 'ACNR_REGISTRY_SNAPSHOT_INVALID', message: reason },
      },
    }))
    const w = mountChips([{ value: 'E1-1' }, { value: 'E1-2' }])
    await flushPromises()

    // 终态走 not_exists（灰显、不可点击）且 tooltip 原样给后端中文原因；普通 5xx 才走 danger / 可重试。
    expect(types(w)).toEqual(['info', 'info'])
    expect(w.findAll('.el-tooltip-stub').map((t) => t.attributes('data-content'))).toEqual([reason, reason])
    expect(w.findAll('.el-tag-stub').map((t) => t.attributes('tabindex'))).toEqual(['-1', '-1'])

    // preventNavigate 原本无条件可点击，Adj 普通 miss 也有可点击例外；治理终态必须优先于两者。
    const inline = mount(GtIndexChip, {
      props: { value: 'Adj:AJ-1', preventNavigate: true },
      global: { components },
    })
    await flushPromises()
    await inline.find('.el-tag-stub').trigger('click')
    expect(inline.emitted('click')).toBeUndefined()
    expect(inline.find('.el-tag-stub').attributes('tabindex')).toBe('-1')

    // 多目标由 el-dropdown 的 command 进入另一条 handler；同一终态门禁也必须挡住。
    const multi = mount(GtIndexChip, {
      props: { value: 'E1-1/E1-2' },
      global: { components },
    })
    await flushPromises()
    multi.findComponent({ name: 'ElDropdownStub' }).vm.$emit('command', 'E1-2')
    await flushPromises()
    expect(multi.emitted('click')).toBeUndefined()

    okBatch()
    mountChips([{ value: 'E1-1' }])
    await flushPromises()
    // 初始 E1/E2 一批 + inline Adj + multi + 重新请求 E1：终态均不缓存。
    expect(http.post).toHaveBeenCalledTimes(4)
  })
})

describe('resolveIndexBatched', () => {
  it('同键在途共享；按项目分批；结果条数不足的项按整批失败处理', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    http.post.mockImplementation(async (_url: string, body: { items: Array<{ index_ref: string }>; project_id?: string }) => {
      await gate
      return { data: body.project_id === 'p1' ? [{ found: true, addr_id: 'A' }] : [] }
    })
    const a = resolveIndexBatched('wp:A1', 'p1')
    const b = resolveIndexBatched('wp:A1', 'p1')
    const c = resolveIndexBatched('wp:A1', 'p2')
    expect(a).toBe(b)
    await Promise.resolve()
    await Promise.resolve()
    expect(http.post).toHaveBeenCalledTimes(2)
    expect(http.post.mock.calls.map(([, body]) => body.project_id).sort()).toEqual(['p1', 'p2'])
    release()
    expect(await a).toEqual({ found: true, addr_id: 'A' })
    expect(await c).toEqual({ found: false, error: BATCH_RESOLVE_FAILED })
  })

  it('同项目旧批量成功晚于另一批 409 到达时，等待者只收到治理终态', async () => {
    let releaseOld!: () => void
    let markStarted!: () => void
    const gate = new Promise<void>((resolve) => { releaseOld = resolve })
    const started = new Promise<void>((resolve) => { markStarted = resolve })
    const terminal = Object.assign(new Error('HTTP 409'), {
      response: {
        status: 409,
        data: { code: 409, error_code: 'ACNR_REGISTRY_SNAPSHOT_INVALID', message: '锁定快照损坏' },
      },
    })
    http.post.mockImplementation(async (_url: string, body: { items: Array<{ index_ref: string }> }) => {
      if (body.items[0]?.index_ref === 'wp:E1') {
        markStarted()
        await gate
        return { data: [{ found: true, addr_id: 'E1/old', jump_route: '/old' }] }
      }
      throw terminal
    })

    const oldRequest = resolveIndexBatched('wp:E1', 'p1')
    await started
    await expect(resolveIndexBatched('wp:D2', 'p1')).resolves.toEqual({
      found: false, error: 'snapshot_invalid', reason: '锁定快照损坏',
    })
    releaseOld()
    await expect(oldRequest).resolves.toEqual({
      found: false, error: 'snapshot_invalid', reason: '锁定快照损坏',
    })

    okBatch()
    await expect(resolveIndexBatched('wp:E1', 'p1')).resolves.toMatchObject({ found: true })
    expect(http.post).toHaveBeenCalledTimes(3)
  })

  it('不合法的索引不排队、不请求', async () => {
    expect(await resolveIndexBatched('', 'p1')).toEqual({ found: false, error: 'invalid_index_ref' })
    await Promise.resolve()
    expect(http.post).not.toHaveBeenCalled()
  })

  it('在途期间缓存被整体失效：结果照样返回但不写缓存，之后同编码重新请求', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    http.post.mockImplementation(async () => {
      await gate
      return { data: [{ found: true, addr_id: 'X' }] }
    })
    const first = resolveIndexBatched('wp:B2', 'p1')
    await Promise.resolve()
    invalidateModuleCache()
    release()
    expect(await first).toEqual({ found: true, addr_id: 'X' })
    http.post.mockResolvedValue({ data: [{ found: true, addr_id: 'Y' }] })
    expect(await resolveIndexBatched('wp:B2', 'p1')).toEqual({ found: true, addr_id: 'Y' })
    expect(http.post).toHaveBeenCalledTimes(2)
  })
})
