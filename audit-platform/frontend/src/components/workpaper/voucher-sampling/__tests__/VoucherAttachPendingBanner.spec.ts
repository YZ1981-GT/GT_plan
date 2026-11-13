/**
 * 底稿顶部「待导入」提示（spec voucher-workflow-linkage-lineage-closure R3.6）
 *
 * - 有待导入凭证才显示，张数照后端；默认收起，从挂凭结果打开（from=voucher-attach）时默认展开；
 * - 展开后列前 5 张，有凭证键 + 科目的可在序时账打开，旧登记（没有凭证键）只列称呼；另有 n 张 / 没记日期的如实写；
 * - 读取失败、后端判断不了（judged=false）、0 张：不显示；
 * - 「本次不再提示」记在 sessionStorage（按底稿），重新挂载仍不显示；
 * - 宿主读入 / 导入后（存续核对注册表版本号变化）防抖重查。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const route = vi.hoisted(() => ({ query: {} as Record<string, string> }))
const push = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push }) }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import http from '@/utils/http'
import {
  __resetVoucherSurvivalRegistry,
  notifyVoucherSurvivalRowsChanged,
} from '../../composables/shared/voucherSurvivalRegistry'
import VoucherAttachPendingBanner from '../VoucherAttachPendingBanner.vue'

const get = http.get as unknown as ReturnType<typeof vi.fn>
const KEY = (no: string) => `["2025","主体","2025-03-05","记","${no}"]`
const mounted: VueWrapper[] = []

function pending(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    id: `sv-${i}`, voucher_key: i === 1 ? null : KEY(String(i).padStart(4, '0')),
    label: `2025-03-05 记-${String(i).padStart(4, '0')}`, voucher_no: String(i).padStart(4, '0'),
    voucher_date: '2025-03-05', account_code: '1002',
  }))
}

function status(over: Record<string, unknown> = {}) {
  return { data: { attached: 7, pending: pending(7), pending_count: 7, undetermined: 1, judged: true, ...over } }
}

async function mountBanner(props: Record<string, unknown> = {}) {
  const w = mount(VoucherAttachPendingBanner, {
    props: { projectId: 'p-1', workpaperId: 'wp-1', year: 2025, ...props },
    global: { plugins: [ElementPlus] },
  })
  mounted.push(w)
  await flushPromises()
  return w
}

beforeEach(() => {
  get.mockReset()
  push.mockReset()
  route.query = {}
  sessionStorage.clear()
  __resetVoucherSurvivalRegistry()
})
afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  vi.useRealTimers()
})

describe('显示条件', () => {
  it('有待导入：显示张数、默认收起；请求带年度、静默、不参与 GET 去重', async () => {
    get.mockResolvedValueOnce(status())
    const w = await mountBanner()
    expect(w.find('[data-testid="voucher-attach-pending-banner"]').text()).toContain('有 7 张凭证已从序时账挂到本底稿，尚未导入凭证检查表')
    expect(w.find('[data-testid="voucher-attach-pending-detail"]').exists()).toBe(false)
    const [url, cfg] = get.mock.calls[0]
    expect(url).toBe('/api/projects/p-1/ledger/workpapers/wp-1/attached-voucher-status')
    expect(cfg).toMatchObject({ params: { year: 2025 }, _silent: true, _dedupe: false })
  })

  it.each([
    ['0 张', status({ pending: [], pending_count: 0 })],
    ['后端判断不了', status({ judged: false })],
  ])('%s：不显示', async (_label, body) => {
    get.mockResolvedValueOnce(body)
    const w = await mountBanner()
    expect(w.find('[data-testid="voucher-attach-pending-banner"]').exists()).toBe(false)
  })

  it('读取失败：不显示（不把「不知道」说成「没导入」）', async () => {
    get.mockRejectedValueOnce(new Error('网络'))
    const w = await mountBanner()
    expect(w.find('[data-testid="voucher-attach-pending-banner"]').exists()).toBe(false)
  })

  it('没有审计年度：不发请求', async () => {
    const w = await mountBanner({ year: null })
    expect(get).not.toHaveBeenCalled()
    expect(w.find('[data-testid="voucher-attach-pending-banner"]').exists()).toBe(false)
  })
})

describe('展开与跳转', () => {
  it('从挂凭结果打开时默认展开：前 5 张、旧登记只列称呼、另有张数与没记日期的说明', async () => {
    route.query = { from: 'voucher-attach' }
    get.mockResolvedValueOnce(status())
    const w = await mountBanner()
    const detail = w.find('[data-testid="voucher-attach-pending-detail"]')
    expect(detail.exists()).toBe(true)
    expect(detail.findAll('li')).toHaveLength(5)
    expect(detail.findAll('[data-testid="voucher-attach-pending-ledger"]')).toHaveLength(4)
    expect(detail.text()).toContain('另有 2 张未列出')
    expect(detail.text()).toContain('另有 1 张旧挂凭没记凭证日期')
    await detail.find('[data-testid="voucher-attach-pending-ledger"]').trigger('click')
    expect(push).toHaveBeenCalledWith(expect.objectContaining({
      name: 'LedgerPenetration',
      query: expect.objectContaining({ level: 'voucher', account: '1002', voucher: '0000', voucherDate: '2025-03-05' }),
    }))
  })

  it('「查看」展开 / 「收起」收起', async () => {
    get.mockResolvedValueOnce(status())
    const w = await mountBanner()
    await w.find('[data-testid="voucher-attach-pending-toggle"]').trigger('click')
    expect(w.find('[data-testid="voucher-attach-pending-detail"]').exists()).toBe(true)
    await w.find('[data-testid="voucher-attach-pending-toggle"]').trigger('click')
    expect(w.find('[data-testid="voucher-attach-pending-detail"]').exists()).toBe(false)
  })
})

describe('关闭与重查', () => {
  it('「本次不再提示」按底稿记在 sessionStorage，重新挂载仍不显示', async () => {
    get.mockResolvedValue(status())
    const w = await mountBanner()
    await w.find('[data-testid="voucher-attach-pending-dismiss"]').trigger('click')
    expect(w.find('[data-testid="voucher-attach-pending-banner"]').exists()).toBe(false)
    expect(sessionStorage.getItem('gt:voucher-attach-pending-dismissed:wp-1')).toBe('1')
    const again = await mountBanner()
    expect(again.find('[data-testid="voucher-attach-pending-banner"]').exists()).toBe(false)
    const other = await mountBanner({ workpaperId: 'wp-2' })
    expect(other.find('[data-testid="voucher-attach-pending-banner"]').exists()).toBe(true)
  })

  it('宿主导入后（注册表版本号变化）防抖重查，导入完的不再显示', async () => {
    vi.useFakeTimers()
    get.mockResolvedValueOnce(status())
    const w = await mountBanner()
    expect(w.find('[data-testid="voucher-attach-pending-banner"]').exists()).toBe(true)
    get.mockResolvedValueOnce(status({ pending: [], pending_count: 0 }))
    notifyVoucherSurvivalRowsChanged()
    notifyVoucherSurvivalRowsChanged()
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(800)
    await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(w.find('[data-testid="voucher-attach-pending-banner"]').exists()).toBe(false)
  })
})
