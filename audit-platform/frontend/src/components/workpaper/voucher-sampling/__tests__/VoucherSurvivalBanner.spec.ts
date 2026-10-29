/**
 * 底稿级预审样本存续核对横幅（任务 17，需求 8）。
 * 年审 + 预审行才显示；当前账套未核对时 POST 四步核对、写回 registry 并持久化；
 * 变化状态 / 未确认数与缺 lfp 旧行如实显示；无 active 账套、只读、读取失败不误放行。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))

import http from '@/utils/http'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import {
  __resetVoucherSurvivalRegistry,
  notifyVoucherSurvivalRowsChanged,
  registerVoucherSurvivalHost,
  type SurvivalCheckWire,
  type SurvivalRequestRow,
} from '../../composables/shared/voucherSurvivalRegistry'
import VoucherSurvivalBanner from '../VoucherSurvivalBanner.vue'

const mockHttp = http as unknown as { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> }
const mounted: VueWrapper[] = []
let unregister: () => void = () => undefined
let statusBody: any

const request: SurvivalRequestRow = {
  row_key: 'fp-1', lfp: 'fp-1', vk: 'vk-1', account_code: '1001', side: 'D', amount: '100.00',
  previous_dataset_id: null, previous_status: null, acknowledged: false,
}
const result: SurvivalCheckWire = {
  check_id: 'check-1', dataset_id: 'dataset-new', checked_by: 'user-1', checked_at: '2026-10-29T00:00:00Z',
  total: 1, unchanged: 0, modified: 1, renumbered: 0, deleted: 0, unacked: 1,
  results: [{ row_key: 'fp-1', lfp: 'fp-1', status: 'modified', acknowledged: false }],
}

function register(rows: Array<{ request: SurvivalRequestRow | null; unsupported: boolean }> = [{ request, unsupported: false }]) {
  const persist = vi.fn().mockResolvedValue(undefined)
  unregister = registerVoucherSurvivalHost('wp-1', {
    collect: () => rows,
    apply: (wire) => {
      const r = wire.results[0]
      if (rows[0]?.request && r) {
        rows[0].request.previous_dataset_id = wire.dataset_id
        rows[0].request.previous_status = r.status
        rows[0].request.acknowledged = r.acknowledged
      }
      return true
    },
    acknowledge: () => false,
    persist,
  })
  return persist
}

function mountBanner(over: Record<string, unknown> = {}) {
  const w = mount(VoucherSurvivalBanner, {
    props: { projectId: 'project-1', workpaperId: 'wp-1', year: 2025, readonly: false, ...over },
    global: { plugins: [ElementPlus] },
  })
  mounted.push(w)
  return w
}

beforeEach(() => {
  vi.clearAllMocks()
  __resetProjectAuditPhaseCache()
  __resetVoucherSurvivalRegistry()
  statusBody = { year: 2025, active_dataset_id: 'dataset-new', check: null }
  mockHttp.get.mockImplementation((url: string) => {
    if (url.includes('/audit-phase')) return Promise.resolve({ data: { current_audit_phase: 'final', can_edit: true } })
    if (url.includes('/interim-survival/status')) return Promise.resolve({ data: { data: statusBody } })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
  mockHttp.post.mockImplementation(() => {
    statusBody = { year: 2025, active_dataset_id: 'dataset-new', check: result }
    return Promise.resolve({ data: { data: result } })
  })
})

afterEach(() => {
  unregister()
  mounted.splice(0).forEach(w => w.unmount())
  __resetVoucherSurvivalRegistry()
})

describe('VoucherSurvivalBanner', () => {
  it('未核对时显示横幅；一键核对发完整行、写回并持久化，显示变化和未确认数', async () => {
    const persist = register()
    const w = mountBanner()
    await flushPromises()
    expect(w.get('[data-testid="voucher-survival-banner"]').text()).toContain('预审样本需在当前账套核对（1 条）')
    await w.get('[data-testid="run-interim-survival"]').trigger('click')
    await flushPromises()
    expect(mockHttp.post).toHaveBeenCalledWith('/api/projects/project-1/sampling/interim-survival', {
      wp_id: 'wp-1', year: 2025, rows: [request],
    }, expect.objectContaining({ _silent: true }))
    expect(persist).toHaveBeenCalledTimes(1)
    expect(w.text()).toContain('预审样本核对发现变化，尚有 1 条未确认')
    expect(w.text()).toContain('分录已改 1')
    expect(w.get('[data-testid="run-interim-survival"]').text()).toBe('重新核对')
  })

  it('缺 lfp 的预审旧行单独报数；无 active 账套时按钮不出现', async () => {
    statusBody = { year: 2025, active_dataset_id: null, check: null }
    register([{ request: null, unsupported: true }])
    const w = mountBanner()
    await flushPromises()
    expect(w.text()).toContain('本年度没有已激活账套')
    expect(w.text()).toContain('1 条预审旧行缺分录指纹，无法自动核对')
    expect(w.find('[data-testid="run-interim-survival"]').exists()).toBe(false)
  })

  it('项目预审阶段不显示；年审只读时可看但不能执行', async () => {
    register()
    mockHttp.get.mockImplementation((url: string) => {
      if (url.includes('/audit-phase')) return Promise.resolve({ data: { current_audit_phase: 'preliminary' } })
      return Promise.resolve({ data: { data: statusBody } })
    })
    const preliminary = mountBanner()
    await flushPromises()
    expect(preliminary.find('[data-testid="voucher-survival-banner"]').exists()).toBe(false)
    preliminary.unmount()

    __resetProjectAuditPhaseCache()
    mockHttp.get.mockImplementation((url: string) => url.includes('/audit-phase')
      ? Promise.resolve({ data: { current_audit_phase: 'final' } })
      : Promise.resolve({ data: { data: statusBody } }))
    const readonly = mountBanner({ readonly: true })
    await flushPromises()
    expect(readonly.get('[data-testid="run-interim-survival"]').attributes('disabled')).toBeDefined()
  })

  it('连续行刷新合并为 single-flight，不让相同 GET 互相取消', async () => {
    register()
    let release: (value: unknown) => void = () => undefined
    let active = 0
    let maxActive = 0
    let statusCalls = 0
    mockHttp.get.mockImplementation((url: string) => {
      if (url.includes('/audit-phase')) return Promise.resolve({ data: { current_audit_phase: 'final' } })
      statusCalls += 1
      active += 1
      maxActive = Math.max(maxActive, active)
      if (statusCalls === 1) return new Promise(resolve => { release = (value) => { active -= 1; resolve(value) } })
      active -= 1
      return Promise.resolve({ data: { data: statusBody } })
    })
    const w = mountBanner()
    await vi.waitFor(() => expect(statusCalls).toBe(1))
    notifyVoucherSurvivalRowsChanged()
    notifyVoucherSurvivalRowsChanged()
    notifyVoucherSurvivalRowsChanged()
    await flushPromises()
    expect(statusCalls).toBe(1)
    release({ data: { data: statusBody } })
    await vi.waitFor(() => expect(statusCalls).toBe(2))
    expect(maxActive).toBe(1)
    w.unmount()
  })

  it('status 读取失败显示失败，不当成无需核对', async () => {
    register()
    mockHttp.get.mockImplementation((url: string) => url.includes('/audit-phase')
      ? Promise.resolve({ data: { current_audit_phase: 'final' } })
      : Promise.reject(new Error('network')))
    const w = mountBanner()
    await flushPromises()
    expect(w.text()).toContain('预审样本存续状态读取失败')
    expect(w.text()).toContain('当前未把读取失败当成“无需核对”')
  })
})


describe('平台级接线（源码）', () => {
  const renderer = readFileSync(resolve(process.cwd(), 'src/components/workpaper/GtWpRenderer.vue'), 'utf-8')
  const fill = readFileSync(resolve(process.cwd(), 'src/components/workpaper/composables/shared/voucherCheckFill.ts'), 'utf-8')

  it('GtWpRenderer 在所有 HTML 宿主之上只挂一个底稿级横幅，并传只读与年度', () => {
    const tag = renderer.slice(renderer.indexOf('<VoucherSurvivalBanner'), renderer.indexOf('/>', renderer.indexOf('<VoucherSurvivalBanner')))
    expect(tag).toContain(':project-id="runtimeProjectId"')
    expect(tag).toContain(':workpaper-id="wpId"')
    expect(tag).toContain(':year="preparationYear"')
    expect(tag).toContain(':readonly="effectiveReadonly"')
  })

  it('62 个宿主共用的 useVoucherCheckFill 注册 refs，并在读入 / 回填 / 撤销后通知横幅', () => {
    expect(fill).toContain('registerVoucherSurvivalHost(wpId')
    expect(fill).toContain('collect: collectSurvivalRows')
    expect(fill).toContain('apply: applySurvival')
    expect(fill).toContain('acknowledge: acknowledgeSurvival')
    expect(fill.match(/notifyVoucherSurvivalRowsChanged\(\)/g)?.length).toBeGreaterThanOrEqual(3)
  })
})
