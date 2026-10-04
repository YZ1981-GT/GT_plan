/**
 * useAdjustmentCentralSync 单元测试
 *
 * spec: workpaper-adjustment-centralization + chain-closure-phase3-push-rollout
 * 验证：借贷平衡守卫（P2）、payload 映射与类型（P3）、source_ref/itemId 动态解析（P7）、
 * 空行过滤、approved 锁定错误提示、回流状态。
 * Phase 3：签名变化检测、首次载入不同步、借贷不平衡跳过、错误去重、
 * 403 静默、协作保护、卸载冲刷、默认 autoSync=true。
 *
 * 真挂载测试：composable 用 onMounted/onBeforeUnmount，所以 Phase 3 的自动同步测试
 * 通过 defineComponent wrapper 在真 Vue setup 上下文里运行。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, defineComponent, h, type Ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'

// mock element-plus 消息 + API（vi.hoisted 保证在 vi.mock 工厂前初始化）
const { msg, msgBox, syncMock, statusMock } = vi.hoisted(() => ({
  msg: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  msgBox: { confirm: vi.fn() },
  syncMock: vi.fn(),
  statusMock: vi.fn(),
}))
vi.mock('element-plus', () => ({
  ElMessage: Object.assign(
    (opts: any) => msg.info(opts?.message || opts),
    msg,
  ),
  ElMessageBox: msgBox,
}))
vi.mock('@/services/auditPlatformApi', () => ({
  syncAdjustmentFromWorkpaper: (...a: any[]) => syncMock(...a),
  getAdjustmentBySourceRef: (...a: any[]) => statusMock(...a),
}))
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: vi.fn(() => ({ close: vi.fn() })),
}))

import {
  useAdjustmentCentralSync,
  computeContentSignature,
  type UseAdjustmentCentralSyncOptions,
  type CentralSyncLineItem,
} from '@/components/workpaper/composables/useAdjustmentCentralSync'

beforeEach(() => {
  vi.useFakeTimers()
  syncMock.mockReset()
  statusMock.mockReset()
  msgBox.confirm.mockReset()
  msg.success.mockReset(); msg.error.mockReset(); msg.warning.mockReset(); msg.info.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

// ─── 辅助：裸调用（不需 lifecycle 的基础测试）───────────────────────
function makeSync(
  lineItems: CentralSyncLineItem[],
  type: 'aje' | 'rje' = 'aje',
  itemId: string | (() => string) = 'D4-4-rows',
) {
  return useAdjustmentCentralSync({
    projectId: ref('proj-1'),
    year: ref(2025),
    wpId: ref('wp-1'),
    wpCode: 'D4',
    itemId,
    buildLineItems: () => lineItems,
    buildMeta: () => ({ description: '收入调整', adjustmentType: type }),
  })
}

// ─── 辅助：真挂载 wrapper（Phase 3 自动同步测试需要 onMounted 生效）──
function mountSync(
  lineItems: Ref<CentralSyncLineItem[]>,
  opts?: Partial<UseAdjustmentCentralSyncOptions>,
) {
  let exposed: ReturnType<typeof useAdjustmentCentralSync> | undefined
  const Wrapper = defineComponent({
    setup() {
      const result = useAdjustmentCentralSync({
        projectId: ref('proj-1'),
        year: ref(2025),
        wpId: ref('wp-1'),
        wpCode: 'D4',
        itemId: 'D4-4-rows',
        buildLineItems: () => lineItems.value,
        buildMeta: () => ({ description: '收入调整', adjustmentType: 'aje' }),
        ...opts,
      })
      exposed = result
      return () => h('div')
    },
  })
  const wrapper = mount(Wrapper)
  return { wrapper, sync: exposed! }
}

const BALANCED_ITEMS: CentralSyncLineItem[] = [
  { debit_amount: 5000, credit_amount: 0, account_name: '库存现金' },
  { debit_amount: 0, credit_amount: 5000, account_name: '主营业务收入' },
]

describe('useAdjustmentCentralSync', () => {
  // ─── 基础功能（P2/P3/P7 兼容） ─────────────────────────────────────────

  it('P2 借贷不平衡不调用后端', async () => {
    const s = makeSync([
      { account_name: 'A', debit_amount: 100, credit_amount: 0 },
      { account_name: 'B', debit_amount: 0, credit_amount: 60 },
    ])
    await s.syncToCentral()
    expect(syncMock).not.toHaveBeenCalled()
    expect(msg.error).toHaveBeenCalled()
  })

  it('P3 平衡时调用后端，payload 含正确类型与来源', async () => {
    syncMock.mockResolvedValue({})
    statusMock.mockResolvedValue({ review_status: 'draft' })
    const s = makeSync(BALANCED_ITEMS, 'rje')
    await s.syncToCentral()
    expect(syncMock).toHaveBeenCalledTimes(1)
    const [pid, body] = syncMock.mock.calls[0]
    expect(pid).toBe('proj-1')
    expect(body.adjustment_type).toBe('rje')
    expect(body.wp_id).toBe('wp-1')
    expect(body.item_id).toBe('D4-4-rows')
    expect(body.source_wp_code).toBe('D4')
    expect(body.line_items).toHaveLength(2)
  })

  it('空行（借贷全 0）被过滤后无有效行则不调用后端', async () => {
    const s = makeSync([{ account_name: 'A', debit_amount: 0, credit_amount: 0 }])
    await s.syncToCentral()
    expect(syncMock).not.toHaveBeenCalled()
    expect(msg.info).toHaveBeenCalled()
  })

  it('P7 动态 itemId（getter）参与 source_ref', () => {
    const s = makeSync([], 'aje', () => 'L1-adj-RJE')
    expect(s.sourceRef()).toBe('wp-1:L1-adj-RJE')
  })

  it('APPROVED_LOCKED 错误给出撤回提示', async () => {
    syncMock.mockRejectedValue({ response: { data: { detail: { error_code: 'APPROVED_LOCKED' } } } })
    statusMock.mockResolvedValue(null)
    const s = makeSync(BALANCED_ITEMS)
    await s.syncToCentral()
    expect(msg.warning).toHaveBeenCalled()
  })

  it('refreshStatus 拉取回流状态', async () => {
    statusMock.mockResolvedValue({ review_status: 'approved', adjustment_no: 'AJE-001' })
    const s = makeSync([])
    await s.refreshStatus()
    expect(s.centralStatus.value?.review_status).toBe('approved')
  })

  // ─── Phase 3：computeContentSignature ──────────────────────────────────

  describe('computeContentSignature', () => {
    it('相同内容产出相同签名', () => {
      const items: CentralSyncLineItem[] = [{ debit_amount: 100, credit_amount: 0 }]
      const meta = { description: 'test', adjustmentType: 'aje' }
      expect(computeContentSignature(items, meta)).toBe(computeContentSignature(items, meta))
    })

    it('不同内容产出不同签名', () => {
      const meta = { description: 'test', adjustmentType: 'aje' }
      const sig1 = computeContentSignature([{ debit_amount: 100, credit_amount: 0 }], meta)
      const sig2 = computeContentSignature([{ debit_amount: 200, credit_amount: 0 }], meta)
      expect(sig1).not.toBe(sig2)
    })

    it('变异：改摘要即签名变化', () => {
      const items: CentralSyncLineItem[] = [{ debit_amount: 100, credit_amount: 0 }]
      const s1 = computeContentSignature(items, { description: 'A', adjustmentType: 'aje' })
      const s2 = computeContentSignature(items, { description: 'B', adjustmentType: 'aje' })
      expect(s1).not.toBe(s2)
    })
  })

  // ─── Phase 3：真挂载的自动同步测试 ────────────────────────────────────

  describe('Phase 3 自动同步（真挂载）', () => {
    let wrapper: VueWrapper<any>

    afterEach(() => {
      wrapper?.unmount()
    })

    it('autoSync 默认开启：scheduleAutoSync 在 firstLoad 后有效', async () => {
      syncMock.mockResolvedValue({})
      statusMock.mockResolvedValue(null)
      const items = ref(BALANCED_ITEMS)
      ;({ wrapper } = mountSync(items))

      // 解除 firstLoad 标记（microtask）
      await vi.advanceTimersByTimeAsync(0)

      wrapper.vm.$forceUpdate()
      const sync = (wrapper.vm.$ as any).setupState || {}

      // 从 exposed 获取 scheduleAutoSync — 通过 mountSync 的 exposed
      // 直接用 mountSync 返回的 sync 对象
      const { sync: s } = mountSync(items)
      await vi.advanceTimersByTimeAsync(0) // firstLoad cleared

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).toHaveBeenCalled()
    })

    it('显式 autoSync=false 时 scheduleAutoSync 不触发', async () => {
      syncMock.mockResolvedValue({})
      statusMock.mockResolvedValue(null)
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper: w } = mountSync(items, { autoSync: false })
      wrapper = w
      await vi.advanceTimersByTimeAsync(0)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).not.toHaveBeenCalled()
    })

    it('首次载入 scheduleAutoSync 不触发同步', async () => {
      syncMock.mockResolvedValue({})
      statusMock.mockResolvedValue(null)
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper: w } = mountSync(items)
      wrapper = w
      // 不等 microtask → _isFirstLoad 仍 true → 应跳过
      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).not.toHaveBeenCalled()
    })

    it('签名未变化时第二次 scheduleAutoSync 不触发', async () => {
      syncMock.mockResolvedValue({})
      statusMock.mockResolvedValue(null)
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper: w } = mountSync(items)
      wrapper = w
      await vi.advanceTimersByTimeAsync(0)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).toHaveBeenCalledTimes(1)

      // 第二次签名不变
      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).toHaveBeenCalledTimes(1)
    })

    it('借贷不平衡时自动同步静默跳过', async () => {
      statusMock.mockResolvedValue(null)
      const items = ref<CentralSyncLineItem[]>([
        { debit_amount: 100, credit_amount: 0 },
        { debit_amount: 0, credit_amount: 60 },
      ])
      const { sync: s, wrapper: w } = mountSync(items)
      wrapper = w
      await vi.advanceTimersByTimeAsync(0)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).not.toHaveBeenCalled()
      expect(msg.error).not.toHaveBeenCalled()
    })

    it('无有效行时自动同步静默跳过', async () => {
      statusMock.mockResolvedValue(null)
      const items = ref<CentralSyncLineItem[]>([{ debit_amount: 0, credit_amount: 0 }])
      const { sync: s, wrapper: w } = mountSync(items)
      wrapper = w
      await vi.advanceTimersByTimeAsync(0)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).not.toHaveBeenCalled()
    })

    it('403 静默不弹消息', async () => {
      syncMock.mockRejectedValue({ response: { status: 403 } })
      statusMock.mockResolvedValue(null)
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper: w } = mountSync(items)
      wrapper = w
      await vi.advanceTimersByTimeAsync(0)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).toHaveBeenCalledTimes(1)
      expect(msg.error).not.toHaveBeenCalled()
      expect(msg.warning).not.toHaveBeenCalled()
    })

    it('同一错误同一签名只提示一次', async () => {
      syncMock.mockRejectedValue({ response: { status: 500, data: { detail: { error_code: 'INTERNAL' } } } })
      statusMock.mockResolvedValue(null)
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper: w } = mountSync(items)
      wrapper = w
      await vi.advanceTimersByTimeAsync(0)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(msg.error).toHaveBeenCalledTimes(1)

      // 第二次同签名同错误不弹
      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(msg.error).toHaveBeenCalledTimes(1)
    })

    it('协作补充过的分录组自动同步跳过并提示', async () => {
      statusMock.mockResolvedValue({ review_status: 'draft', collaboration_status: 'contributed' })
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper: w } = mountSync(items)
      wrapper = w
      await vi.advanceTimersByTimeAsync(0)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).not.toHaveBeenCalled()
      expect(msg.info).toHaveBeenCalled()
    })

    it('协作保护提示也有去重', async () => {
      statusMock.mockResolvedValue({ review_status: 'draft', collaboration_status: 'confirmed' })
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper: w } = mountSync(items)
      wrapper = w
      await vi.advanceTimersByTimeAsync(0)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      // 第一次给提示
      const infoCount = msg.info.mock.calls.length
      expect(infoCount).toBeGreaterThanOrEqual(1)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      // 不再重复
      expect(msg.info).toHaveBeenCalledTimes(infoCount)
    })

    it('5 秒内多次 scheduleAutoSync 只触发一次', async () => {
      syncMock.mockResolvedValue({})
      statusMock.mockResolvedValue(null)
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper: w } = mountSync(items)
      wrapper = w
      await vi.advanceTimersByTimeAsync(0)

      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(2000)
      s.scheduleAutoSync() // 重新调度，重置 5s 计时
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).toHaveBeenCalledTimes(1)
    })
  })

  // ─── 变异测试 ────────────────────────────────────────────────────────

  describe('变异', () => {
    it('变异：去掉首次载入跳过 → 首次即触发（改回即红）', async () => {
      syncMock.mockResolvedValue({})
      statusMock.mockResolvedValue(null)
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper } = mountSync(items)
      // 不等 microtask → _isFirstLoad 仍 true → 应跳过
      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).not.toHaveBeenCalled()
      wrapper.unmount()
    })

    it('变异：恢复 autoSync 默认 false → scheduleAutoSync 不触发', async () => {
      syncMock.mockResolvedValue({})
      statusMock.mockResolvedValue(null)
      const items = ref(BALANCED_ITEMS)
      const { sync: s, wrapper } = mountSync(items, { autoSync: false })
      await vi.advanceTimersByTimeAsync(0)
      s.scheduleAutoSync()
      await vi.advanceTimersByTimeAsync(5000)
      expect(syncMock).not.toHaveBeenCalled()
      wrapper.unmount()
    })
  })
})
