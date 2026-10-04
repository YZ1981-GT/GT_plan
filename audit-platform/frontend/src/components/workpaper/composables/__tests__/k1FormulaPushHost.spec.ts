/**
 * K1 宿主与公式推送的配套（spec chain-closure-phase3-push-rollout 任务 14 · 需求 6.3）
 *
 * - 公式推送独占的 K1-1 系统键不能随普通前端保存回写；
 * - formula.pushed 只在本底稿源值实际变化时提示；
 * - 载入最新数据只替换被后台推送改过的条目；
 * - 根宿主保留过滤、SSE 订阅和提示条接线。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref } from 'vue'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), put: vi.fn() },
}))

import { api } from '@/services/apiProxy'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import {
  isK1BackendOwnedKey,
  k1SaveItemIds,
} from '../k1BackendOwnedKeys'
import { k1PushNotice, k1PushedRows } from '../k1FormulaPushNotice'

describe('K1 后端独占键不回写', () => {
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
  ])('%s 是后端独占键', (id) => {
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
  ])('%s 不是后端独占键（用户可编辑、账龄动态行或其它 sheet）', (id) => {
    expect(isK1BackendOwnedKey(id)).toBe(false)
  })

  it('普通 K1 保存保留用户键，过滤所有后端独占键', () => {
    const ids = [
      'K1-2-detail-rows',
      'K1-1-receivable-r0-remark',
      'K1-1-receivable-r0-unadj',
      'K1-1-audited-net',
      'K1-1-fs-interest',
    ]
    expect(k1SaveItemIds(ids)).toEqual([
      'K1-2-detail-rows',
      'K1-1-receivable-r0-remark',
    ])
  })

  it('根宿主保存过滤后的真实 persistence 请求不含 K1 后端独占键', async () => {
    vi.mocked(api.put).mockImplementation(async (_url, body: any) => ({ data: body.items }))
    const persistence = useChecklistPersistence({ wpId: ref('wp-k1'), projectId: ref('project-k1') })
    for (const itemId of k1SaveItemIds([
      'K1-1-fs-interest',
      'K1-1-receivable-r0-remark',
    ])) {
      await persistence.save(itemId, { remark: '用户输入' })
    }

    const savedIds = vi.mocked(api.put).mock.calls.map((call) => (call[1] as any).items[0].item_id)
    expect(savedIds).toEqual(['K1-1-receivable-r0-remark'])
    expect(savedIds.filter(isK1BackendOwnedKey)).toEqual([])
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

  it('保存前调用 K1 过滤函数，后端独占键不会进入 persistence.save', () => {
    expect(src).toContain("import { k1SaveItemIds } from './composables/k1BackendOwnedKeys'")
    expect(src).toContain('const [persistableItemId] = k1SaveItemIds([itemId])')
    expect(src).toContain('if (!persistableItemId) return')
    expect(src).toContain('persistence.save(persistableItemId, toChecklistPatch(value))')
  })

  it('订阅 formula.pushed、卸载时关闭，并提供中文后台更新提示条', () => {
    expect(src).toMatch(/subscribeProjectEvent\(props\.projectId, 'formula\.pushed'/)
    expect(src).toContain('_pushSub.close()')
    expect(src).toContain('后台已按公式推送更新')
    expect(src).toContain('载入最新数据')
    expect(src).toContain('k1PushedRows(rows, notice.itemIds)')
  })
})
