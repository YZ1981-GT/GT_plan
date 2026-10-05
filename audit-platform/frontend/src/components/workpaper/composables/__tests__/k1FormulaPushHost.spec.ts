/**
 * K1 宿主与公式推送的配套（spec chain-closure-phase3-push-rollout 任务 14 · 需求 6.3）
 *
 * - 根宿主保留完整保存集合，公式推送独占键分类仅用于提示条接线。
 * - formula.pushed 只在本底稿源值实际变化时提示；
 * - 载入最新数据只替换被后台推送改过的条目；
 * - 根宿主保留完整保存链路、SSE 订阅和提示条接线。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref, defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const hostMocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  httpGet: vi.fn(),
  httpPost: vi.fn(),
  httpPut: vi.fn(),
  close: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: hostMocks.apiGet, put: hostMocks.apiPut },
}))

vi.mock('@/utils/http', () => ({
  default: {
    get: hostMocks.httpGet,
    post: hostMocks.httpPost,
    put: hostMocks.httpPut,
  },
}))

vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: vi.fn(() => ({ close: hostMocks.close })),
}))

vi.mock('../../k1/core/K1TabAdjudication.vue', () => ({
  __esModule: true,
  default: defineComponent({
    name: 'K1TabAdjudicationProbe',
    emits: ['save'],
    data: () => ({
      saveIds: [
        'K1-2-detail-rows',
        'K1-1-receivable-r0-begin',
        'K1-1-receivable-r0-unadj',
        'K1-1-fs-interest',
        'K1-1-audited-net',
        'K1-1-receivable-r0-remark',
      ],
    }),
    template: `
      <div data-test="k1-adjudication-probe">
        <button
          v-for="itemId in saveIds"
          :key="itemId"
          :data-item-id="itemId"
          @click="$emit('save', itemId, { remark: itemId })"
        />
      </div>
    `,
  }),
}))

import GtK1OtherReceivables from '../../GtK1OtherReceivables.vue'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import {
  isK1BackendOwnedKey,
  k1AdjudicationSaveItemIds,
  k1SaveItemIds,
} from '../k1BackendOwnedKeys'
import { k1PushNotice, k1PushedRows } from '../k1FormulaPushNotice'

beforeEach(() => {
  vi.clearAllMocks()
  hostMocks.apiPut.mockImplementation(async (_url: string, body: any) => ({ data: body.items }))
  hostMocks.httpGet.mockResolvedValue({ data: { healthy: false } })
  hostMocks.httpPost.mockResolvedValue({ data: { imported_count: 0 } })
})

const elementPlusStubs = {
  'el-skeleton': true,
  'el-button': true,
  'el-alert': true,
  'el-segmented': true,
  'el-tag': true,
  'el-tooltip': true,
}

describe('K1 保存键集合', () => {
  it.each([
    'K1-1-nature-gross-n0-begin',
    'K1-1-nature-gross-n4-unadj',
    'K1-1-nature-prov-n2-begin',
    'K1-1-nature-prov-n3-unadj',
    'K1-1-receivable-r0-begin',
    'K1-1-receivable-r3-unadj',
    'K1-1-baddebt-r1-begin',
    'K1-1-baddebt-r2-unadj',
    'K1-1-fs-interest',
    'K1-1-fs-dividend',
    'K1-1-fs-other-total',
    'K1-1-audited-receivable',
    'K1-1-audited-baddebt',
    'K1-1-audited-net',
  ])('%s 是公式推送识别的后端独占键', (id) => {
    expect(isK1BackendOwnedKey(id)).toBe(true)
  })

  it.each([
    'K1-1-nature-gross-n0-debit',
    'K1-1-nature-gross-n0-remark',
    'K1-1-receivable-r0-prior-unadj',
    'K1-1-receivable-r0-aje',
    'K1-1-receivable-r0-rje',
    'K1-1-aging-gross-a0-begin',
    'K1-1-receivable-r4-begin',
    'K1-1-fs-interest-note',
    'K1-2-detail-rows',
    'K1-1-audit-note',
  ])('%s 不是公式推送独占键', (id) => {
    expect(isK1BackendOwnedKey(id)).toBe(false)
  })

  it('K1 保存集合保留用户键和公式推送键', () => {
    const ids = [
      'K1-2-detail-rows',
      'K1-1-receivable-r0-remark',
      'K1-1-receivable-r0-unadj',
      'K1-1-audited-net',
      'K1-1-fs-interest',
    ]
    expect(k1SaveItemIds(ids)).toEqual(ids)
  })

  it('K1-1 审定表保存集合也保留完整输入集合', () => {
    const ids = ['K1-1-receivable-r0-unadj', 'K1-1-audited-net', 'K1-1-audit-note']
    expect(k1AdjudicationSaveItemIds(ids)).toEqual(ids)
  })

  it('完整保存集合进入真实 persistence 请求', async () => {
    const itemIds = [
      'K1-1-fs-interest',
      'K1-1-receivable-r0-unadj',
      'K1-1-receivable-r0-remark',
      'K1-1-audited-net',
    ]
    const persistence = useChecklistPersistence({ wpId: ref('wp-k1'), projectId: ref('project-k1') })
    for (const itemId of k1SaveItemIds(itemIds)) {
      await persistence.save(itemId, { remark: '用户输入' })
    }

    expect(hostMocks.apiPut.mock.calls.map((call) => (call[1] as any).items[0].item_id)).toEqual(itemIds)
    expect(hostMocks.apiPut.mock.calls.every((call) => (call[1] as any).project_id === 'project-k1')).toBe(true)
  })
})

describe('K1 根宿主真实保存链路', () => {
  it('真实挂载后，K1-2 同步、四表带入、FS 手填和审定合计都发出 PUT', async () => {
    const wrapper = mount(GtK1OtherReceivables, {
      props: {
        wpId: 'wp-k1-host',
        projectId: 'project-k1-host',
        sheetName: 'K1-1 审定表',
        year: 2025,
        htmlData: {
          responses_snapshot: [{
            item_id: 'K1-2-detail-rows',
            remark: JSON.stringify([{ counterparty: '客户A', endBalance: 100 }]),
            conclusion: null,
          }],
          tb_values: { receivable_unadjusted: 1000 },
        },
      },
      global: {
        stubs: elementPlusStubs,
      },
    })

    await flushPromises()
    const probe = wrapper.findComponent({ name: 'K1TabAdjudicationProbe' })
    expect(probe.exists()).toBe(true)

    const saves = [
      ['K1-2-detail-rows', 'K1-2同步'],
      ['K1-1-receivable-r0-begin', '四表带入'],
      ['K1-1-receivable-r0-unadj', '四表带入未审数'],
      ['K1-1-fs-interest', 'FS手填'],
      ['K1-1-audited-net', '发布后审定合计'],
      ['K1-1-receivable-r0-remark', '用户手填'],
    ] as const
    for (const [itemId] of saves) {
      await probe.find(`[data-item-id="${itemId}"]`).trigger('click')
    }
    await flushPromises()

    const calls = hostMocks.apiPut.mock.calls.filter(([url]) => url === '/api/workpapers/wp-k1-host/checklist-responses')
    expect(calls).toHaveLength(saves.length)
    expect(calls.map((call) => (call[1] as any).items[0].item_id)).toEqual(saves.map(([itemId]) => itemId))
    expect(calls.every((call) => (call[1] as any).project_id === 'project-k1-host')).toBe(true)
    expect(calls.map((call) => (call[1] as any).items[0].remark)).toEqual(saves.map(([itemId]) => itemId))

    wrapper.unmount()
  })
})


describe('K1 formula.pushed 提示条', () => {
  const evt = (over: Record<string, unknown> = {}) => ({
    project_id: 'p',
    year: 2025,
    run_id: 'run-k1-1',
    dry_run: false,
    wp_ids: ['wp-k1'],
    stages: ['source', 'derived'],
    changed_items: [
      'K1-1-receivable-r0-begin',
      'K1-1-fs-other-total',
      'K1-1-audited-net',
    ],
    ...over,
  })

  it('本底稿后端独占源值有写入 ⇒ 提示，条数只算后端独占键', () => {
    expect(k1PushNotice(evt(), 'wp-k1')).toEqual({
      runId: 'run-k1-1',
      count: 3,
      itemIds: [
        'K1-1-receivable-r0-begin',
        'K1-1-fs-other-total',
        'K1-1-audited-net',
      ],
    })
  })

  it.each([
    ['别的底稿', evt({ wp_ids: ['wp-other'] })],
    ['只有派生值变化', evt({ stages: ['derived'] })],
    ['只有附注变化', evt({ stages: ['note'] })],
    ['试跑', evt({ dry_run: true })],
    ['没有改过的条目', evt({ changed_items: [] })],
    ['只有用户键变化', evt({ changed_items: ['K1-1-receivable-r0-remark'] })],
    ['载荷异常', null],
  ])('%s ⇒ 不提示', (_name, event) => {
    expect(k1PushNotice(event, 'wp-k1')).toBeNull()
  })

  it('载入最新数据只替换推送改过的条目，用户其它编辑不动', () => {
    const server = [
      { item_id: 'K1-1-receivable-r0-begin', remark: '后台新值', conclusion: null },
      { item_id: 'K1-1-receivable-r0-remark', remark: '服务端旧备注', conclusion: null },
    ]
    expect(k1PushedRows(server, ['K1-1-receivable-r0-begin'])).toEqual([server[0]])
  })
})

describe('K1 宿主接线（源码级防回退）', () => {
  const src = readFileSync(resolve(__dirname, '../../GtK1OtherReceivables.vue'), 'utf-8')

  it('根宿主保存入口把原始 itemId 交给 persistence.save', () => {
    expect(src).not.toContain("import { k1SaveItemIds } from './composables/k1BackendOwnedKeys'")
    expect(src).toContain('persistence.save(itemId, toChecklistPatch(value))')
    expect(src).not.toContain('if (!persistableItemId) return')
  })

  it('订阅 formula.pushed、卸载时关闭，并提供中文后台更新提示条', () => {
    expect(src).toMatch(/subscribeProjectEvent\(props\.projectId, 'formula\.pushed'/)
    expect(src).toContain('_pushSub.close()')
    expect(src).toContain('后台已按公式推送更新')
    expect(src).toContain('载入最新数据')
    expect(src).toContain('k1PushedRows(rows, notice.itemIds)')
  })
})
