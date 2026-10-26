/**
 * 前置横幅随当前底稿编码请求（spec procedure-chain-hardening-and-java-contracts R9）：
 * 原先编辑器在 setup 时传 `.value` ⇒ 详情还没加载，每张底稿都按 E1 请求、看到的都是货币资金的前置。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { shallowMount } from '@vue/test-utils'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { get: (...a: any[]) => mockGet(...a) } }))

import { prerequisiteWpCode, usePrerequisiteStatus } from '../usePrerequisiteStatus'
import EditorBanners from '@/views/workpaper-editor/EditorBanners.vue'

const URL = '/api/projects/p1/workpapers/prerequisite-status'
const tick = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ items: [], overall: 'ready' })
})

describe('prerequisiteWpCode', () => {
  it.each([
    ['E1', 'E1'], ['E1-2', 'E1'], ['e1-3', 'E1'], ['E10', ''], ['D2-1', 'D2-1'], ['J1', 'J1'], ['H8', 'H8'], ['N3', 'N3'],
    ['A1', ''], ['B60', ''], ['C5', ''], ['S1', ''], ['', ''], [null, ''], [undefined, ''],
  ])('%s ⇒ %s', (code, want) => {
    expect(prerequisiteWpCode(code as any)).toBe(want)
  })
})

describe('usePrerequisiteStatus 接受 getter', () => {
  it('编码为空不请求；详情加载后按底稿编码请求；换底稿重取', async () => {
    const code = ref('')
    const st = usePrerequisiteStatus(() => 'p1', () => code.value)
    await nextTick()
    expect(mockGet).not.toHaveBeenCalled()
    expect([st.overall.value, st.loading.value]).toEqual(['ready', false])
    code.value = 'D2'
    await nextTick()
    expect(mockGet).toHaveBeenCalledWith(URL, { params: { wp_code: 'D2' } })
    code.value = 'H8'
    await nextTick()
    expect(mockGet.mock.calls.map((c) => c[1].params.wp_code)).toEqual(['D2', 'H8'])
  })

  it('详情对象换了、编码没变 ⇒ 不重复请求', async () => {
    const detail = ref({ wp_code: 'D2' })
    usePrerequisiteStatus(() => 'p1', () => prerequisiteWpCode(detail.value.wp_code))
    await nextTick()
    detail.value = { wp_code: 'D2' }
    await nextTick()
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('换了底稿后旧回执晚到 ⇒ 丢弃', async () => {
    let resolveOld: (v: unknown) => void = () => undefined
    mockGet.mockReset()
      .mockImplementationOnce(() => new Promise((r) => { resolveOld = r }))
      .mockResolvedValueOnce({ items: [{ wp_code: 'C6', wp_name: '固定资产循环控制测试', state: 'completed' }], overall: 'ready' })
    const code = ref('D2')
    const st = usePrerequisiteStatus(() => 'p1', () => code.value)
    code.value = 'H1'
    await nextTick()
    await tick()
    resolveOld({ items: [{ wp_code: 'B23-1', wp_name: '了解内部控制', state: 'pending' }], overall: 'blocked' })
    await tick()
    expect(st.items.value.map((i) => i.wp_code)).toEqual(['C6'])
    expect([st.overall.value, st.loading.value]).toEqual(['ready', false])
  })
})

describe('EditorBanners 前置横幅显示与请求同一判定', () => {
  const mk = (wpCode: string) => shallowMount(EditorBanners, {
    props: {
      projectId: 'p1', wpId: 'w1', wpDetail: { id: 'w1', wp_code: wpCode } as any, cycleType: {} as any,
      editLock: null, prerequisiteBanner: { type: 'error', message: 'x' },
      staleImpact: { affected: { value: [] }, totalAffected: { value: 0 } }, showStaleImpactPanel: false,
    },
  })
  it.each([['J1', true], ['E1-2', true], ['D2', true], ['A1', false], ['C5', false]])('%s ⇒ %s', (code, shown) => {
    expect((mk(code).vm as any).showPrereqBanner).toBe(shown)
  })
})
