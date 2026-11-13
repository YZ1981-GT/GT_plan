/**
 * SamplingPreviewDialog — 只读、确认进行中与分页（spec voucher-workflow-linkage-lineage-closure R4.2 / R4.3）
 *
 * - 只读随引擎：能看样本，不能增删改、不能勾选、不能确认填充，并说明原因；
 * - 确认进行中：按钮转圈，再点不发 confirm（引擎那一层另有单飞，两层都挡）；
 * - 超过 100 行分页：每页 100 行，勾选按页同步，翻页不丢别页的勾选；分页时表头全选只管当前页。
 */
import { describe, it, expect, afterEach } from 'vitest'
import { reactive } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import SamplingPreviewDialog from '../SamplingPreviewDialog.vue'
import type { SampledVoucher } from '../../composables/useSamplingAlgorithms'

const LIVE: VueWrapper[] = []
afterEach(() => {
  while (LIVE.length) LIVE.pop()!.unmount()
})

function voucher(i: number): SampledVoucher {
  return {
    voucherNo: `V-${String(i).padStart(3, '0')}`, voucherDate: '2025-03-01', summary: `摘要${i}`, debitAmount: String(100 + i),
    creditAmount: null, accountCode: '1122', accountName: '应收账款', counterpartAccount: null,
    counterpartAccountName: null, isMultiAccount: false, voucherEntries: [],
    voucherType: '记', accountingPeriod: 3, checkResult: '', abnormal: false, remark: '',
    selected: true, phase: 'final', editTrail: [],
  }
}

/**
 * light：分页用例一页就是 100 行，每行两个下拉一个输入框，jsdom 里整页重渲染要几秒；
 * 分页与勾选只看表格行和勾选框，把行内录入控件换成桩（只读用例照常用真组件）。
 */
function mountDialog(over: Record<string, unknown> = {}, n = 1, light = false) {
  const vouchers = reactive(Array.from({ length: n }, (_, i) => voucher(i + 1))) as SampledVoucher[]
  const w = mount(SamplingPreviewDialog, {
    props: {
      visible: true, vouchers, coverageStats: null, fillMode: 'append', selectedCount: n,
      selectedDebitTotal: 0, selectedCreditTotal: 0, phase: 'final', ...over,
    },
    global: { plugins: [ElementPlus], stubs: light ? { ElSelect: true, ElOption: true, ElInput: true } : {} },
    attachTo: document.body,
  })
  LIVE.push(w)
  return { w, vouchers }
}

/** el-table 的表头全选走 10ms 防抖（store.toggleAllSelection = debounce(..., 10)） */
const afterHeaderDebounce = () => new Promise(r => setTimeout(r, 40))

const confirmButton = (w: VueWrapper) =>
  w.findAllComponents({ name: 'ElButton' }).find(b => b.attributes('data-testid') === 'sampling-preview-confirm')!
const bodyRows = (w: VueWrapper) => w.findAll('.el-table__body tbody tr.el-table__row')
const rowCheckbox = (w: VueWrapper, i: number) => bodyRows(w)[i].find('td .el-checkbox input[type="checkbox"]')
const headerTexts = (w: VueWrapper) => w.findAll('.el-table__header th').map(th => th.text().trim())

/** 绕过 disabled 直接触发按钮的 click 监听（验证 handleConfirm 自己的兜底，不靠按钮禁用） */
async function forceClickConfirm(w: VueWrapper) {
  confirmButton(w).vm.$emit('click', new MouseEvent('click'))
  await flushPromises()
}

describe('只读：能看不能改', () => {
  it('显示只读说明，隐藏增补 / 批量 / 删除，确认按钮禁用', async () => {
    const { w } = mountDialog({ readonly: true }, 3)
    await flushPromises()
    expect(w.find('[data-testid="sampling-preview-readonly"]').exists()).toBe(true)
    expect(w.text()).not.toContain('+ 追加凭证')
    expect(w.text()).not.toContain('填入勾选行')
    expect(headerTexts(w)).not.toContain('操作')
    expect(confirmButton(w).attributes('disabled')).toBeDefined()
  })

  it('行内下拉、备注与勾选框全部禁用；已选样本照常显示为勾上', async () => {
    const { w } = mountDialog({ readonly: true }, 3)
    await flushPromises()
    for (let i = 0; i < 3; i++) {
      const box = rowCheckbox(w, i)
      expect(box.attributes('disabled')).toBeDefined()
      expect((box.element as HTMLInputElement).checked).toBe(true)
    }
    const editable = w.findAll('.el-table__body input').filter(i => (i.element as HTMLInputElement).type !== 'checkbox')
    expect(editable.length).toBeGreaterThan(0)
    for (const input of editable) expect(input.attributes('disabled'), '只读时仍有可编辑输入').toBeDefined()
  })

  it('就地放行说明框只读，不出预置理由按钮', async () => {
    const { w } = mountDialog({ readonly: true, reconcileIssue: '未执行总体完整性核对', reconcilePresets: ['已与总账核对一致'] })
    await flushPromises()
    expect(w.get('textarea[data-testid="preview-reconcile-reason"]').attributes('disabled')).toBeDefined()
    expect(w.text()).not.toContain('已与总账核对一致')
  })

  it('绕过按钮禁用直接触发也不发 confirm', async () => {
    const { w } = mountDialog({ readonly: true })
    await flushPromises()
    await forceClickConfirm(w)
    expect(w.emitted('confirm')).toBeUndefined()
  })

  it('对照：非只读时同一触发方式发出 confirm，增补与删除列都在', async () => {
    const { w } = mountDialog({}, 3)
    await flushPromises()
    expect(w.find('[data-testid="sampling-preview-readonly"]').exists()).toBe(false)
    expect(w.text()).toContain('+ 追加凭证')
    expect(headerTexts(w)).toContain('操作')
    await forceClickConfirm(w)
    expect(w.emitted('confirm')).toHaveLength(1)
  })
})

describe('确认进行中：不重复提交', () => {
  it('按钮转圈且禁用，再触发不发 confirm', async () => {
    const { w } = mountDialog({ confirming: true })
    await flushPromises()
    const btn = confirmButton(w)
    expect(btn.classes()).toContain('is-loading')
    expect(btn.attributes('disabled')).toBeDefined()
    await forceClickConfirm(w)
    expect(w.emitted('confirm')).toBeUndefined()
  })

  it('进行中结束后可以再次确认', async () => {
    const { w } = mountDialog({ confirming: true })
    await flushPromises()
    await w.setProps({ confirming: false })
    await forceClickConfirm(w)
    expect(w.emitted('confirm')).toHaveLength(1)
  })
})

describe('超过 100 行分页', { timeout: 60_000 }, () => {
  it('100 行以内不分页', async () => {
    const { w } = mountDialog({}, 100, true)
    await flushPromises()
    expect(w.find('[data-testid="sampling-preview-pagination"]').exists()).toBe(false)
    expect(bodyRows(w)).toHaveLength(100)
  })

  it('150 行：第 1 页 100 行，第 2 页 50 行', async () => {
    const { w } = mountDialog({}, 150, true)
    await flushPromises()
    expect(w.find('[data-testid="sampling-preview-pagination"]').exists()).toBe(true)
    expect(bodyRows(w)).toHaveLength(100)
    expect(bodyRows(w)[0].text()).toContain('V-001')
    await w.get('[data-testid="sampling-preview-pagination"] .btn-next').trigger('click')
    await flushPromises()
    expect(bodyRows(w)).toHaveLength(50)
    expect(bodyRows(w)[0].text()).toContain('V-101')
  })

  it('勾选按页同步：取消第 1 页一行不动别页，翻回来仍是取消', async () => {
    const { w, vouchers } = mountDialog({}, 150, true)
    await flushPromises()
    await rowCheckbox(w, 1).setValue(false)
    await flushPromises()
    expect(vouchers[1].selected).toBe(false)
    expect(vouchers.filter(v => !v.selected)).toHaveLength(1)

    await w.get('[data-testid="sampling-preview-pagination"] .btn-next').trigger('click')
    await flushPromises()
    // 第 2 页按 selected 勾上（不是全空），别页勾选不受第 1 页操作影响
    expect((rowCheckbox(w, 0).element as HTMLInputElement).checked).toBe(true)
    expect(vouchers.slice(100).every(v => v.selected)).toBe(true)

    await w.get('[data-testid="sampling-preview-pagination"] .btn-prev').trigger('click')
    await flushPromises()
    expect((rowCheckbox(w, 1).element as HTMLInputElement).checked).toBe(false)
    expect((rowCheckbox(w, 0).element as HTMLInputElement).checked).toBe(true)
  })

  it('行内改动（填核查结果、打备注）不清掉本页勾选', async () => {
    // el-table 深度监听 data：当前页若是普通数组，任一行内改动都被当成换了数据、清空勾选
    const { w, vouchers } = mountDialog({}, 150, true)
    await flushPromises()
    const table = w.findComponent({ name: 'ElTable' }).vm as unknown as { getSelectionRows: () => SampledVoucher[] }
    expect(table.getSelectionRows()).toHaveLength(100)
    vouchers[3].checkResult = 'Y'
    vouchers[4].remark = '已核对原始单据'
    await flushPromises()
    expect(table.getSelectionRows()).toHaveLength(100)
    expect((rowCheckbox(w, 3).element as HTMLInputElement).checked).toBe(true)
    expect(vouchers.every(v => v.selected)).toBe(true)
  })

  it('删掉一行后当前页换数据，勾选按 selected 重新勾上', async () => {
    const { w, vouchers } = mountDialog({}, 150, true)
    await flushPromises()
    vouchers[7].selected = false
    await bodyRows(w)[0].find('.el-button--danger').trigger('click')
    await flushPromises()
    expect(vouchers).toHaveLength(149)
    expect(bodyRows(w)[0].text()).toContain('V-002')
    const table = w.findComponent({ name: 'ElTable' }).vm as unknown as { getSelectionRows: () => SampledVoucher[] }
    // 第 1 页现在是 V-002~V-101：V-008（原 vouchers[7]）未选，其余 99 行勾上
    expect(table.getSelectionRows()).toHaveLength(99)
    expect((rowCheckbox(w, 6).element as HTMLInputElement).checked).toBe(false)
  })

  it('分页时表头全选只管当前页，不通知引擎全选 / 全不选', async () => {
    const { w, vouchers } = mountDialog({}, 150, true)
    await flushPromises()
    await w.get('.el-table__header th .el-checkbox input[type="checkbox"]').setValue(false)
    await afterHeaderDebounce()
    await flushPromises()
    expect(w.emitted('toggle-select-all')).toBeUndefined()
    expect(vouchers.slice(0, 100).every(v => !v.selected)).toBe(true)
    expect(vouchers.slice(100).every(v => v.selected)).toBe(true)
  })

  it('对照：不分页时表头全选照旧通知引擎', async () => {
    const { w } = mountDialog({}, 3, true)
    await flushPromises()
    await w.get('.el-table__header th .el-checkbox input[type="checkbox"]').setValue(false)
    await afterHeaderDebounce()
    await flushPromises()
    expect(w.emitted('toggle-select-all')?.at(-1)).toEqual([false])
  })
})
