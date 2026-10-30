/** 非「未变」的预审行可逐行确认：先持久化 `_gt.sv.ack*`，再幂等 PATCH 项目汇总（任务 17，需求 8.2）。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, provide, ref } from 'vue'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/utils/http', () => ({ default: { patch: vi.fn() } }))

import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import { survivalRequestOf, type VoucherRowMeta } from '../../composables/shared/voucherCheckFill'
import {
  __resetVoucherSurvivalRegistry,
  registerVoucherSurvivalHost,
  rememberVoucherSurvivalContext,
} from '../../composables/shared/voucherSurvivalRegistry'
import VoucherRowMetaTag from '../VoucherRowMetaTag.vue'

const patch = (http as unknown as { patch: ReturnType<typeof vi.fn> }).patch
const VK = JSON.stringify(['2025', 'T17', '2025-12-20', 'SV', 'M-1'])
const FP = JSON.stringify(['2025', 'T17', '2025-12-20', 'SV', 'M-1', '1002', 'C', '200.00', 0])
let unregister: () => void = () => undefined

afterEach(() => { unregister(); __resetVoucherSurvivalRegistry() })
beforeEach(() => {
  vi.clearAllMocks()
  __resetVoucherSurvivalRegistry()
  patch.mockResolvedValue({ data: { unacked: 0, ack_by: 'user-1', ack_at: 'server-time' } })
  const auth = useAuthStore()
  auth.$patch({ user: { id: 'user-1', username: 'editor', full_name: '审计员', email: 'x@test.com', role: 'auditor', is_active: true, created_at: '' } })
})

function meta(): VoucherRowMeta {
  return { vk: VK, lfp: FP, ph: 'preliminary', b: 'batch-1', src: ['engine'], pr: 'paired',
    sv: { status: 'modified', datasetId: 'dataset-new', checkId: 'check-1', detail: '原凭证仍在，但分录内容已变化' } }
}

describe('VoucherRowMetaTag 存续确认', () => {
  it('按钮写 ack 元数据、调用宿主 persist 后 PATCH 剩余数，标签变已确认', async () => {
    const current = ref<any>({ _gt: meta() })
    const persist = vi.fn().mockResolvedValue(undefined)
    unregister = registerVoucherSurvivalHost('wp-1', {
      collect: () => [{ request: survivalRequestOf(current.value), unsupported: false }],
      apply: () => false,
      acknowledge: (lfp, ackBy, ackAt) => {
        if (lfp !== FP) return false
        current.value = { ...current.value, _gt: { ...current.value._gt,
          sv: { ...current.value._gt.sv, ackBy, ackAt } } }
        return true
      },
      persist,
    })
    rememberVoucherSurvivalContext('wp-1', FP, 'check-1', 'dataset-new')

    const Parent = defineComponent({
      setup() {
        provide(WorkpaperRuntimeContextKey, {
          wpId: ref('wp-1'), projectId: ref('project-1'), wpCode: ref('J1'), year: ref(2025), readonly: ref(false),
        } as any)
        return () => h(VoucherRowMetaTag, { row: current.value, locked: true })
      },
    })
    const w = mount(Parent, { global: { plugins: [ElementPlus] } })
    expect(w.text()).toContain('分录已改')
    await w.get('[data-testid="ack-voucher-survival"]').trigger('click')
    await nextTick()
    await vi.waitFor(() => expect(patch).toHaveBeenCalledTimes(1))
    expect(persist).toHaveBeenCalledTimes(1)
    expect(patch).toHaveBeenCalledWith('/api/projects/project-1/sampling/interim-survival/check-1', {
      wp_id: 'wp-1', dataset_id: 'dataset-new', unacked: 0,
    }, expect.objectContaining({ _silent: true }))
    expect(w.text()).toContain('分录已改（已确认）')
    expect(w.find('[data-testid="ack-voucher-survival"]').exists()).toBe(false)
    w.unmount()
  })

  it('整张底稿只读时不提供确认按钮', () => {
    const Parent = defineComponent({
      setup() {
        provide(WorkpaperRuntimeContextKey, {
          wpId: ref('wp-1'), projectId: ref('project-1'), wpCode: ref('J1'), year: ref(2025), readonly: ref(true),
        } as any)
        return () => h(VoucherRowMetaTag, { row: { _gt: meta() }, locked: true })
      },
    })
    const w = mount(Parent, { global: { plugins: [ElementPlus] } })
    expect(w.text()).toContain('分录已改')
    expect(w.find('[data-testid="ack-voucher-survival"]').exists()).toBe(false)
    w.unmount()
  })
})
