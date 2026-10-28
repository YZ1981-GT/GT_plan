/**
 * SamplingPreviewDialog — 总体完整性校验就地放行（挂载测试）
 *
 * spec: voucher-sampling-reconcile-balance-source（R3.1 / R3.2）
 *
 * 用一个最小宿主模拟引擎：持有放行理由、按「≥10 字」计算 confirmBlockedReason，
 * 断言用户在**预览弹窗内**填写说明后「确认填充」由禁用变为可用（不必关闭预览）。
 */
import { describe, it, expect, afterEach } from 'vitest'
import { defineComponent, h, ref, computed, nextTick } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import SamplingPreviewDialog from '../SamplingPreviewDialog.vue'
import type { SampledVoucher } from '../../composables/useSamplingAlgorithms'

const ISSUE = '未执行总体完整性核对：科目余额表中无所选科目（1122）的行，无法确认样本取自完整总体'
const PRESETS = ['该科目无独立明细表，已与总账另行核对一致，确认抽样总体完整']
const LIVE: VueWrapper[] = []

afterEach(() => {
  while (LIVE.length) LIVE.pop()!.unmount()
})

function voucher(): SampledVoucher {
  return {
    voucherNo: '0892', voucherDate: '2025-01-24', summary: '销售收款', debitAmount: null,
    creditAmount: '22421.50', accountCode: '1122.01', accountName: '应收账款', counterpartAccount: null,
    voucherType: '主账簿', accountingPeriod: 1, checkResult: 'Y', abnormal: false, remark: '',
    selected: true, phase: 'final', editTrail: [],
  }
}

function baseProps(over: Record<string, unknown> = {}) {
  return {
    visible: true,
    vouchers: [voucher()],
    coverageStats: null,
    fillMode: 'append',
    selectedCount: 1,
    selectedDebitTotal: 0,
    selectedCreditTotal: 22421.5,
    phase: 'final',
    ...over,
  }
}

function mountDialog(props: Record<string, unknown>) {
  const w = mount(SamplingPreviewDialog, { props, global: { plugins: [ElementPlus] }, attachTo: document.body })
  LIVE.push(w)
  return w
}

/** 最小宿主：与引擎一致——理由 ≥10 字才解除阻断 */
function mountWithHost() {
  const reason = ref('')
  const Host = defineComponent({
    setup() {
      const blocked = computed(() => (reason.value.trim().length >= 10 ? null : `${ISSUE}（可直接在本窗口下方填写说明后继续）`))
      return () => h(SamplingPreviewDialog, {
        ...baseProps(),
        confirmBlockedReason: blocked.value,
        // 与引擎一致：核对问题本身不因填了理由而消失，放行块保持显示并转为「已填写」
        reconcileIssue: ISSUE,
        reconcileOverrideReason: reason.value,
        reconcilePresets: PRESETS,
        'onUpdate:reconcileOverrideReason': (v: string) => { reason.value = v },
      })
    },
  })
  const w = mount(Host, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  LIVE.push(w)
  return { w, reason }
}

const confirmBtn = (w: VueWrapper) => w.get('[data-testid="sampling-preview-confirm"]')
const block = (w: VueWrapper) => w.find('[data-testid="preview-reconcile-override"]')

describe('就地放行块的显示', () => {
  it('没有核对问题时不显示（旧调用点不传 prop 行为不变）', async () => {
    const w = mountDialog(baseProps())
    await flushPromises()
    expect(block(w).exists()).toBe(false)
  })

  it('有核对问题时显示原因与「还需 10 字」', async () => {
    const w = mountDialog(baseProps({ reconcileIssue: ISSUE, reconcileOverrideReason: '', reconcilePresets: PRESETS }))
    await flushPromises()
    expect(block(w).exists()).toBe(true)
    expect(block(w).text()).toContain(ISSUE)
    expect(block(w).text()).toContain('还需 10 字')
  })

  it('预置理由按钮把整句理由发给宿主', async () => {
    const w = mountDialog(baseProps({ reconcileIssue: ISSUE, reconcileOverrideReason: '', reconcilePresets: PRESETS }))
    await flushPromises()
    const btn = block(w).findAll('button').find(b => b.text() === PRESETS[0])
    expect(btn, '未渲染预置理由按钮').toBeTruthy()
    await btn!.trigger('click')
    expect(w.emitted('update:reconcile-override-reason')?.at(-1)).toEqual([PRESETS[0]])
  })
})

describe('在预览内填写说明 ⇒ 确认填充由禁用变为可用', () => {
  it('输入 9 字仍禁用，补到 10 字后可点击并发出 confirm', async () => {
    const { w, reason } = mountWithHost()
    await flushPromises()
    expect(confirmBtn(w).attributes('disabled')).toBeDefined()

    // el-input 把 data-* 透传到内部 <textarea> 本身（不在外层容器上）
    const textarea = w.get('textarea[data-testid="preview-reconcile-reason"]')
    await textarea.setValue('一二三四五六七八九')
    await nextTick()
    expect(reason.value).toBe('一二三四五六七八九')
    expect(confirmBtn(w).attributes('disabled')).toBeDefined()

    await textarea.setValue('一二三四五六七八九十')
    await nextTick()
    expect(confirmBtn(w).attributes('disabled')).toBeUndefined()
    expect(block(w).text()).toContain('已填写放行理由')

    await confirmBtn(w).trigger('click')
    const dialog = w.findComponent(SamplingPreviewDialog)
    expect(dialog.emitted('confirm')).toHaveLength(1)
  })
})
