/**
 * 挂凭弹窗：一张凭证挂多张底稿（spec voucher-identity-writeback-and-audit-phase 任务 14，需求 5.1）
 *
 * - 底稿多选；推荐底稿（按凭证涉及的科目）默认勾选；每张底稿只列一次（推荐的列在 ⭐ 组，不在循环组重复）；
 * - 一次提交走批量接口：凭证 × 底稿、不带阶段；
 * - 有失败：弹窗不关，列出哪张凭证挂哪张底稿没成、为什么；仍有挂上的照样通知宿主刷新标识；
 * - 全部挂上：多张底稿关窗提示，只选一张底稿时才询问是否跳转；
 * - 「凭证 × 底稿」超过 500 个组合：按钮禁用并提示；整单失败（无编辑权限）提示原因。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('@/services/workpaperApi', () => ({ listWorkpapersPaged: vi.fn() }))

import http from '@/utils/http'
import { listWorkpapersPaged } from '@/services/workpaperApi'
import AttachVoucherToWpDialog from '../AttachVoucherToWpDialog.vue'

const post = http.post as unknown as ReturnType<typeof vi.fn>
const listWps = listWorkpapersPaged as unknown as ReturnType<typeof vi.fn>
const PID = 'p-1'
const FY0012 = { voucherNo: '0012', voucherDate: '2025-01-20', voucherType: 'FY', accountCode: '2211.01.99.04' }
const CODES = ['1002', '2211.01.99.04', '6602.01.99']
const KEY = '["2025","重庆医药集团四川物流有限公司","2025-01-20","FY","0012"]'
const WPS = [
  { wp_id: 'wp-e1', wp_code: 'E1', wp_name: '货币资金' },
  { wp_id: 'wp-j1', wp_code: 'J1', wp_name: '应付职工薪酬' },
  { wp_id: 'wp-k9', wp_code: 'K9', wp_name: '管理费用' },
  { wp_id: 'wp-d2', wp_code: 'D2', wp_name: '应收账款' },
  { wp_id: 'wp-x', wp_code: 'D5', wp_name: '未生成', wp_generated: false },
]

const LIVE: VueWrapper[] = []
beforeEach(() => {
  post.mockReset()
  listWps.mockReset()
  listWps.mockResolvedValue({ items: WPS, total: WPS.length })
})
afterEach(() => {
  while (LIVE.length) LIVE.pop()!.unmount()
  vi.restoreAllMocks()
})

function result(wp: string, status: 'created' | 'existed' | 'failed', over: Record<string, unknown> = {}) {
  return { voucher_no: '0012', voucher_date: '2025-01-20', voucher_type: 'FY', voucher_key: KEY,
    working_paper_id: wp, wp_code: WPS.find(w => w.wp_id === wp)?.wp_code ?? null, status, ...over }
}

async function open(vouchers = [FY0012]) {
  const w = mount(AttachVoucherToWpDialog, {
    props: { modelValue: false, projectId: PID, year: 2025, vouchers, allAccountCodes: CODES },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  LIVE.push(w)
  await w.setProps({ modelValue: true })
  await flushPromises()
  return w
}

const select = (w: VueWrapper) => w.findComponent({ name: 'ElSelect' })
const selected = (w: VueWrapper) => select(w).props('modelValue') as string[]
/** 弹窗 append-to-body：DOM 不在 wrapper 里，按组件找「挂入底稿」按钮 */
const primary = (w: VueWrapper) => w.findAllComponents({ name: 'ElButton' }).find(b => b.props('type') === 'primary')!

describe('底稿多选与推荐默认勾选', () => {
  it('推荐底稿默认勾选；每张底稿只列一次；未生成的不列', async () => {
    const w = await open()
    expect(selected(w)).toEqual(['wp-e1', 'wp-j1', 'wp-k9'])
    const groups = w.findAllComponents({ name: 'ElOptionGroup' }).map(g => g.props('label'))
    expect(groups[0]).toBe('⭐ 推荐底稿（3）')
    const values = w.findAllComponents({ name: 'ElOption' }).map(o => o.props('value'))
    expect([...values].sort()).toEqual(['wp-d2', 'wp-e1', 'wp-j1', 'wp-k9'])
  })
})

describe('批量提交', () => {
  it('凭证 × 所选底稿一次提交，不带阶段；全部挂上关窗提示，不询问跳转', async () => {
    const success = vi.spyOn(ElMessage, 'success')
    const confirmBox = vi.spyOn(ElMessageBox, 'confirm')
    const w = await open()
    select(w).vm.$emit('update:modelValue', ['wp-e1', 'wp-j1'])
    await flushPromises()
    post.mockResolvedValueOnce({ data: { results: [result('wp-e1', 'created'), result('wp-j1', 'existed')],
      created: 1, existed: 1, failed: 0, phase: 'final' } })
    await primary(w).trigger('click')
    await flushPromises()
    const [url, body, opts] = post.mock.calls[0]
    expect(url).toBe(`/api/projects/${PID}/ledger/sample-vouchers/batch`)
    expect(body).toEqual({
      year: 2025,
      vouchers: [{ voucher_no: '0012', voucher_date: '2025-01-20', voucher_type: 'FY', company_code: null,
        account_code: '2211.01.99.04' }],
      working_paper_ids: ['wp-e1', 'wp-j1'], note: '序时账挂入', source: 'ledger',
    })
    expect((opts as { _silent?: boolean })._silent).toBe(true)
    expect(w.emitted('attached')?.[0]?.[0]).toEqual({ count: 1, existed: 1, workpaperId: 'wp-e1',
      workpaperIds: ['wp-e1', 'wp-j1'], voucherKeys: [KEY] })
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([false])
    expect(success).toHaveBeenCalledWith(expect.stringContaining('1 张凭证 × 2 张底稿'))
    expect(confirmBox).not.toHaveBeenCalled()
  })

  it('有失败：弹窗不关并列出原因；挂上的照样通知宿主刷新', async () => {
    vi.spyOn(ElMessage, 'warning')
    const w = await open()
    post.mockResolvedValueOnce({ data: { results: [
      result('wp-e1', 'created'),
      result('wp-j1', 'failed', { error_code: 'ATTACH_WRITE_FAILED', reason: '这一条没写进去（数据库拒绝）' }),
      result('wp-k9', 'failed', { wp_code: null, error_code: 'WP_NOT_IN_PROJECT', reason: '目标底稿不在本项目' }),
    ], created: 1, existed: 0, failed: 2 } })
    await primary(w).trigger('click')
    await flushPromises()
    const box = document.querySelector('[data-testid="attach-failures"]')
    expect(box?.textContent).toContain('2 条没挂上')
    expect(box?.textContent).toContain('2025-01-20 FY-0012')
    expect(box?.textContent).toContain('J1：这一条没写进去（数据库拒绝）')
    expect(box?.textContent).toContain('K9：目标底稿不在本项目')
    expect(w.emitted('update:modelValue')).toBeUndefined()
    expect(w.emitted('attached')?.[0]?.[0]).toMatchObject({ count: 1, voucherKeys: [KEY] })
  })

  it('只选一张底稿：全部挂上后询问是否跳转', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValueOnce('confirm' as never)
    const w = await open()
    select(w).vm.$emit('update:modelValue', ['wp-j1'])
    await flushPromises()
    post.mockResolvedValueOnce({ data: { results: [result('wp-j1', 'created')], created: 1, existed: 0, failed: 0 } })
    await primary(w).trigger('click')
    await flushPromises()
    expect(w.emitted('navigateToWp')?.[0]?.[0]).toEqual({ workpaperId: 'wp-j1', wpCode: 'J1', wpName: '应付职工薪酬' })
  })

  it('无编辑权限整单失败：提示原因，不通知宿主', async () => {
    const error = vi.spyOn(ElMessage, 'error')
    const w = await open()
    post.mockRejectedValueOnce({ response: { status: 403 } })
    await primary(w).trigger('click')
    await flushPromises()
    expect(error).toHaveBeenCalledWith('挂凭失败：没有本项目的编辑权限')
    expect(w.emitted('attached')).toBeUndefined()
  })

  it('「凭证 × 底稿」超过 500 个组合：按钮禁用并提示，不发请求', async () => {
    const many = Array.from({ length: 168 }, (_, i) => ({ ...FY0012, voucherNo: String(i).padStart(4, '0') }))
    const w = await open(many) // 168 × 3 张推荐底稿 = 504
    expect(primary(w).props('disabled')).toBe(true)
    expect(document.body.textContent).toContain('一次最多挂 500 个「凭证 × 底稿」组合（当前 504 个）')
    expect(post).not.toHaveBeenCalled()
  })
})
