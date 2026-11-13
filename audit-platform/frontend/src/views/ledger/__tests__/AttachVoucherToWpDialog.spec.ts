/**
 * 挂凭弹窗：一张凭证挂多张底稿 + 结果视图
 * （spec voucher-identity-writeback-and-audit-phase 任务 14 需求 5.1；voucher-workflow-linkage-lineage-closure R3.2）
 *
 * - 底稿多选；推荐底稿（按凭证涉及的科目）默认勾选；每张底稿只列一次；未生成的不列；
 * - 一次提交走批量接口：凭证 × 底稿、不带阶段；
 * - 提交后不论成败都进结果视图：逐张底稿列新挂 / 已挂 / 失败与原因；结果没回编码的底稿用候选清单补；
 * - 有挂上的底稿才有「打开底稿」：点了先关弹窗再交宿主跳转；「继续挂入」回选择视图并保留所选底稿；
 * - 「凭证 × 底稿」超过 500 个组合：按钮禁用并提示；整单失败（无编辑权限）提示原因、留在选择视图。
 *
 * 2026-11-03：弹窗在 v1.0.53 改用 `listWorkpapersAll` 取底稿，本文件仍 mock `listWorkpapersPaged` ⇒ 底稿列表恒空、
 * 5 例在 HEAD 上就红（推荐勾选为空、按钮禁用）；随本次改写一并改正。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessage, ElMessageBox } from 'element-plus'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('@/services/workpaperApi', () => ({ listWorkpapersAll: vi.fn() }))

import http from '@/utils/http'
import { listWorkpapersAll } from '@/services/workpaperApi'
import AttachVoucherToWpDialog from '../AttachVoucherToWpDialog.vue'

const post = http.post as unknown as ReturnType<typeof vi.fn>
const listWps = listWorkpapersAll as unknown as ReturnType<typeof vi.fn>
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
  listWps.mockResolvedValue(WPS)
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
/** 选择视图的「挂入底稿」按钮（弹窗 append-to-body：DOM 不在 wrapper 里，按组件找） */
const submitButton = (w: VueWrapper) => w.findAllComponents({ name: 'ElButton' })
  .find(b => b.props('type') === 'primary' && b.text().startsWith('挂入底稿'))!
const q = (sel: string) => document.querySelector<HTMLElement>(sel)
const qa = (sel: string) => [...document.querySelectorAll<HTMLElement>(sel)]

async function submit(w: VueWrapper, response: unknown) {
  post.mockResolvedValueOnce({ data: response })
  await submitButton(w).trigger('click')
  await flushPromises()
}

describe('底稿多选与推荐默认勾选', () => {
  it('推荐底稿默认勾选；每张底稿只列一次；未生成的不列', async () => {
    const w = await open()
    expect(listWps).toHaveBeenCalledWith(PID)
    expect(selected(w)).toEqual(['wp-e1', 'wp-j1', 'wp-k9'])
    const groups = w.findAllComponents({ name: 'ElOptionGroup' }).map(g => g.props('label'))
    expect(groups[0]).toBe('⭐ 推荐底稿（3）')
    const values = w.findAllComponents({ name: 'ElOption' }).map(o => o.props('value'))
    expect([...values].sort()).toEqual(['wp-d2', 'wp-e1', 'wp-j1', 'wp-k9'])
  })
})

describe('批量提交与结果视图', () => {
  it('凭证 × 所选底稿一次提交，不带阶段；全部挂上进结果视图、不弹确认框', async () => {
    const confirmBox = vi.spyOn(ElMessageBox, 'confirm')
    const w = await open()
    select(w).vm.$emit('update:modelValue', ['wp-e1', 'wp-j1'])
    await flushPromises()
    await submit(w, { results: [result('wp-e1', 'created'), result('wp-j1', 'existed')],
      created: 1, existed: 1, failed: 0, phase: 'final' })
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
    expect(w.emitted('update:modelValue')).toBeUndefined() // 不自动关
    expect(q('[data-testid="attach-results"]')?.textContent).toContain('1 张凭证 × 2 张底稿：新挂 1 条，之前已挂 1 条')
    const rows = qa('[data-testid="attach-result-row"]').map(r => r.textContent?.replace(/\s+/g, ' ').trim())
    expect(rows[0]).toContain('E1 货币资金')
    expect(rows[0]).toContain('新挂 1 · 已挂 0 · 失败 0')
    expect(rows[1]).toContain('J1 应付职工薪酬')
    expect(rows[1]).toContain('新挂 0 · 已挂 1 · 失败 0')
    expect(qa('[data-testid="attach-result-open"]')).toHaveLength(2)
    expect(confirmBox).not.toHaveBeenCalled()
  })

  it('有失败：逐张底稿列原因；没回编码的底稿用候选清单补；全失败的底稿没有「打开底稿」', async () => {
    const w = await open()
    await submit(w, { results: [
      result('wp-e1', 'created'),
      result('wp-j1', 'failed', { error_code: 'ATTACH_WRITE_FAILED', reason: '这一条没写进去（数据库拒绝）' }),
      result('wp-k9', 'failed', { wp_code: null, error_code: 'WP_NOT_WRITABLE', reason: '你不能编辑这张底稿' }),
    ], created: 1, existed: 0, failed: 2 })
    expect(q('[data-testid="attach-results"]')?.textContent).toContain('2 条没挂上')
    const rows = qa('[data-testid="attach-result-row"]')
    expect(rows).toHaveLength(3)
    expect(rows[1].textContent).toContain('2025-01-20 FY-0012：这一条没写进去（数据库拒绝）')
    expect(rows[2].textContent).toContain('K9 管理费用')
    expect(rows[2].textContent).toContain('你不能编辑这张底稿')
    expect(rows.map(r => !!r.querySelector('[data-testid="attach-result-open"]'))).toEqual([true, false, false])
    expect(w.emitted('attached')?.[0]?.[0]).toMatchObject({ count: 1, voucherKeys: [KEY] })
  })

  it('「打开底稿」：先关弹窗，再交宿主跳转', async () => {
    const w = await open()
    select(w).vm.$emit('update:modelValue', ['wp-j1'])
    await flushPromises()
    await submit(w, { results: [result('wp-j1', 'created')], created: 1, existed: 0, failed: 0 })
    q('[data-testid="attach-result-open"]')!.click()
    await flushPromises()
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([false])
    expect(w.emitted('navigateToWp')?.[0]?.[0]).toEqual({ workpaperId: 'wp-j1', wpCode: 'J1', wpName: '应付职工薪酬' })
  })

  it('「继续挂入」回到选择视图并保留所选底稿；「完成」关闭', async () => {
    const w = await open()
    await submit(w, { results: [result('wp-e1', 'created')], created: 1, existed: 0, failed: 0 })
    q('[data-testid="attach-continue"]')!.click()
    await flushPromises()
    expect(q('[data-testid="attach-results"]')).toBeNull()
    expect(selected(w)).toEqual(['wp-e1', 'wp-j1', 'wp-k9'])
    await submit(w, { results: [result('wp-e1', 'existed')], created: 0, existed: 1, failed: 0 })
    q('[data-testid="attach-done"]')!.click()
    await flushPromises()
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('无编辑权限整单失败：提示原因、留在选择视图，不通知宿主', async () => {
    const error = vi.spyOn(ElMessage, 'error')
    const w = await open()
    post.mockRejectedValueOnce({ response: { status: 403 } })
    await submitButton(w).trigger('click')
    await flushPromises()
    expect(error).toHaveBeenCalledWith('挂凭失败：没有本项目的编辑权限')
    expect(w.emitted('attached')).toBeUndefined()
    expect(q('[data-testid="attach-results"]')).toBeNull()
  })

  it('「凭证 × 底稿」超过 500 个组合：按钮禁用并提示，不发请求', async () => {
    const many = Array.from({ length: 168 }, (_, i) => ({ ...FY0012, voucherNo: String(i).padStart(4, '0') }))
    const w = await open(many) // 168 × 3 张推荐底稿 = 504
    expect(submitButton(w).props('disabled')).toBe(true)
    expect(document.body.textContent).toContain('一次最多挂 500 个「凭证 × 底稿」组合（当前 504 个）')
    expect(post).not.toHaveBeenCalled()
  })
})
