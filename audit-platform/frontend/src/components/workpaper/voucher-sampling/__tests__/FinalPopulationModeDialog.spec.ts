/**
 * 年审抽凭口径弹窗（spec voucher-identity-writeback-and-audit-phase 任务 15，需求 7.1）
 *
 * 两个选项都在；缺省选上次口径、首次 b；没有截止日时口径 a 不可选（上次选过 a 也改选 b）；
 * 显示预审批次数、样本数、挂凭数与截止日；确定返回所选口径，取消 / 关闭返回 false。
 */
import { describe, it, expect, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FinalPopulationModeDialog from '../FinalPopulationModeDialog.vue'
import { parsePhaseContext } from '../../composables/useFinalPopulationMode'

// 弹窗挂在 body 上：一例断言失败没走到 unmount 时，残留的弹窗会被下一例的查询先找到 ⇒ 每例后统一清理
const mounted: VueWrapper[] = []
afterEach(() => {
  mounted.splice(0).forEach((w) => w.unmount())
  document.body.innerHTML = ''
})

const ctx = (over: Record<string, unknown> = {}) => parsePhaseContext({
  current_audit_phase: 'final', interim_cutoff_date: '2025-06-30', effective_cutoff_date: '2025-06-30',
  cutoff_source: 'project', audit_period_end: '2025-12-31', interim_batch_count: 2, interim_sample_count: 25,
  interim_line_count: 25, interim_attach_count: 3, last_final_population_mode: null,
  requires_final_population_mode: true, default_final_population_mode: 'full_minus_interim', ...over,
})

async function openWith(context: ReturnType<typeof ctx>) {
  const wrapper = mount(FinalPopulationModeDialog, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  mounted.push(wrapper)
  const pending = (wrapper.vm as unknown as { open: (c: unknown) => Promise<unknown> }).open(context)
  await flushPromises()
  return { wrapper, pending }
}

const q = (sel: string) => document.body.querySelector(sel) as HTMLElement | null
const checked = (testid: string) => q(`[data-testid="${testid}"]`)?.classList.contains('is-checked') ?? false
const disabled = (testid: string) => q(`[data-testid="${testid}"]`)?.classList.contains('is-disabled') ?? false

describe('FinalPopulationModeDialog', () => {
  it('首次缺省 b，显示预审工作与截止日；确定返回 b', async () => {
    const { pending } = await openWith(ctx())
    expect(q('[data-testid="final-population-mode-dialog"]')).not.toBeNull()
    expect(checked('final-population-mode-b')).toBe(true)
    expect(checked('final-population-mode-a')).toBe(false)
    const summary = q('[data-testid="final-population-mode-summary"]')!.textContent!
    expect(summary).toContain('2 批')
    expect(summary).toContain('样本 25 条')
    expect(summary).toContain('挂凭 3 张')
    expect(summary).toContain('预审截止日 2025-06-30')
    expect(q('[data-testid="final-population-mode-a"]')!.textContent).toContain('2025-06-30')
    q('[data-testid="final-population-mode-confirm"]')!.click()
    expect(await pending).toBe('full_minus_interim')
  })

  it('缺省上次口径 a；改选 b 后确定返回 b', async () => {
    const { pending } = await openWith(ctx({ last_final_population_mode: 'remaining', default_final_population_mode: 'remaining' }))
    expect(checked('final-population-mode-a')).toBe(true)
    expect(q('[data-testid="final-population-mode-last"]')!.textContent).toContain('口径 a')
    ;(q('[data-testid="final-population-mode-b"] input') ?? q('[data-testid="final-population-mode-b"]'))!.click()
    await flushPromises()
    q('[data-testid="final-population-mode-confirm"]')!.click()
    expect(await pending).toBe('full_minus_interim')
  })

  it('没有截止日：口径 a 不可选，上次选 a 也落到 b；说明截止日来源', async () => {
    const { pending } = await openWith(ctx({
      interim_cutoff_date: null, effective_cutoff_date: null, cutoff_source: null,
      last_final_population_mode: 'remaining', default_final_population_mode: 'remaining',
    }))
    expect(disabled('final-population-mode-a')).toBe(true)
    expect(checked('final-population-mode-b')).toBe(true)
    expect(q('[data-testid="final-population-mode-a"]')!.textContent).toContain('请先在项目设置')
    const footer = Array.from(document.body.querySelectorAll('.el-dialog__footer button')) as HTMLElement[]
    footer.find((b) => b.textContent?.includes('取消'))!.click()
    expect(await pending).toBe(false)
  })

  it('截止日取自预审批次期间上限时如实说明', async () => {
    const { pending } = await openWith(ctx({ interim_cutoff_date: null, effective_cutoff_date: '2025-09-30',
      cutoff_source: 'interim_batches' }))
    expect(q('[data-testid="final-population-mode-summary"]')!.textContent).toContain('按预审批次期间上限 2025-09-30 计')
    expect(disabled('final-population-mode-a')).toBe(false)
    q('[data-testid="final-population-mode-confirm"]')!.click()
    expect(await pending).toBe('full_minus_interim')
  })
})
