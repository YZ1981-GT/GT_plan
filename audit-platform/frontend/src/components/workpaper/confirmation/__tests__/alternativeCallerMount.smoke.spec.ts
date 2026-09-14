/**
 * alternativeCallerMount.smoke.spec.ts — 函证替代 caller 组件挂载冒烟（工厂收敛运行时验证）
 *
 * 背景（confirmation-alternative-factory-convergence）：八套 alternative composable 已收敛为
 * 工厂适配器。characterization 测试锁定 composable 行为、Vite transform 证明 import 可解析，
 * 但都无法覆盖「caller .vue 的 setup + 模板通过迁移后 composable 消费返回对象」这一运行时集成层
 * （ref 解包 / 命名导出 / 返回形状漂移导致的挂载崩溃只在真实挂载/浏览器暴露）。
 *
 * 本冒烟用 shallowMount 挂载真实 K06 / L05 caller（子组件自动 stub），跑真实迁移后 composable，
 * 断言：①setup 不抛（composable 构造 + refs 绑定 + computed 访问）②顶层模板表达式求值不崩
 * ③迁移后 composable 暴露的 caller 消费点（getPostPaymentRatio/getReconcileRatio/balanceSummary/
 *   buildPayload/companies…）存在且可用。
 */
import { shallowMount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// ─── http / apiProxy mock（K06 构造即 http.get render-config；L05 有 props.htmlData 走内存不发 http）──
const httpMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({
  default: {
    get: (...a: any[]) => httpMocks.get(...a),
    post: (...a: any[]) => httpMocks.post(...a),
    put: (...a: any[]) => httpMocks.put(...a),
  },
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...a: any[]) => httpMocks.get(...a), post: (...a: any[]) => httpMocks.post(...a) },
}))
// 导入导出 composable 依赖 http，stub 掉避免噪声
vi.mock('../../composables/useWorkpaperImportExport', () => ({
  useWorkpaperImportExport: () => ({
    exportTemplate: vi.fn(), exportData: vi.fn(), importData: vi.fn(),
  }),
}))

import GtConfirmationAlternativeK06 from '../alternativeK06/GtConfirmationAlternativeK06.vue'
import GtConfirmationAlternativeL05 from '../alternativeL05/GtConfirmationAlternativeL05.vue'

const K06_RENDER_CONFIG = {
  data: {
    data: {
      sheets: [
        {
          sheet_name: 'K0-6 其他应付款替代程序',
          html_data: {
            _format: 'alternative-k06-v1',
            companies: [
              {
                entity_name: '债权人甲',
                balance: { item_name: '其他应付款', closing_balance: 1000 },
                block1_rows: [{ paymentAmount: 200, is_abnormal: '否' }],
                block2_rows: [],
                block3_rows: [],
                block4_rows: [{ amount: 400, is_abnormal: '否' }],
                sampling: {},
                conclusion: {},
              },
            ],
          },
        },
      ],
    },
  },
}

beforeEach(() => {
  setActivePinia(createPinia())
  httpMocks.get.mockReset()
  httpMocks.post.mockReset()
  httpMocks.put.mockReset()
  httpMocks.get.mockImplementation((url: string) => {
    if (String(url).includes('render-config')) return Promise.resolve(K06_RENDER_CONFIG)
    if (String(url).includes('unreplied-entities')) return Promise.resolve({ data: [] })
    return Promise.resolve({ data: {} })
  })
  httpMocks.post.mockResolvedValue({ data: {} })
})

describe('GtConfirmationAlternativeK06 caller 挂载冒烟', () => {
  it('挂载不抛 + 加载 render-config 公司 + 顶层比例模板表达式求值（getPostPaymentRatio/getReconcileRatio）', async () => {
    const wrapper = shallowMount(GtConfirmationAlternativeK06, {
      props: {
        htmlData: { _format: 'alternative-k06-v1', companies: [] },
        sheetName: 'K0-6',
        wpId: 'wp-k06',
        projectId: 'proj-1',
        readonly: false,
      },
    })
    await flushPromises()

    // setup 未抛 + 组件渲染
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('[data-testid="k0-alternative-k06"]').exists()).toBe(true)

    // composical loadAll() 从 render-config 载入公司（迁移后仍走适配器 http，非工厂）
    const vm: any = wrapper.vm
    expect(vm.data.companies.value.length).toBe(1)
    expect(vm.data.companies.value[0].entity_name).toBe('债权人甲')

    // 迁移后 composable 的 caller 消费点存在且计算正确（顶层模板即读这些）
    const c = vm.data.companies.value[0]
    expect(vm.data.getPostPaymentRatio(c)).toBe(20)   // 200/1000*100
    expect(vm.data.getReconcileRatio(c)).toBe(40)      // 400/1000*100
    expect(vm.data.metrics.value.total_companies).toBe(1)

    // 顶层比例 DOM 渲染（模板 data.getPostPaymentRatio(selectedCompany) 求值未崩）
    expect(wrapper.html()).toContain('期后付款检查比例')

    // buildPayload 契约（handleSave 消费）
    const payload = vm.data.buildPayload()
    expect(payload._format).toBe('alternative-k06-v1')
    expect(payload.companies[0].balance.receipt_check_ratio).toBe(20)
    expect(payload.companies[0].balance.shipment_check_ratio).toBe(40)
  })
})

describe('GtConfirmationAlternativeL05 caller 挂载冒烟', () => {
  it('挂载不抛 + 内存 htmlData 载入 + balanceSummary/getBlockRows/buildPayload 消费点可用', async () => {
    const htmlData = {
      _format: 'alternative-l05-v1',
      companies: [
        {
          entity_name: '工商银行',
          balance: {
            item_name: '长期应付款/借款',
            opening_balance: 100,
            debit_amount: 20,
            credit_amount: 30,
            closing_balance: 1000,
          },
          block1_rows: [{ repayment_principal: 300, is_abnormal: '否' }],
          block2_rows: [],
          block3_rows: [{ voucher_amount: 500, is_abnormal: '否' }],
          block4_rows: [{ mortgage_amount: 400, is_abnormal: '否' }],
          sampling: {},
          conclusion: {},
        },
      ],
    }
    const wrapper = shallowMount(GtConfirmationAlternativeL05, {
      props: {
        htmlData,
        sheetName: 'L0-5',
        wpId: 'wp-l05',
        projectId: 'proj-1',
        readonly: false,
      },
      global: {
        // el-table 的默认 stub 会以「无作用域」调用列的 #default="{ row }" → 解构 undefined 崩，
        // 这是 shallowMount 的 harness 假阴性（真实 el-table 恒提供 row 作用域）。
        // 用不渲染插槽的 stub 规避，保留 setup() + composable 消费点的真实校验。
        stubs: {
          'el-table': { template: '<div class="el-table-stub" />' },
          'el-table-column': { template: '<div class="el-table-column-stub" />' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    const vm: any = wrapper.vm

    // 工厂 htmlData init 载入公司
    expect(vm.data.companies.value.length).toBe(1)

    // balanceSummary（L05 独有旁挂）消费点：currentLoan=block3.voucher 合计、比例基于 closing
    const s = vm.balanceSummary
    expect(s.closingBalance).toBe(1000)
    expect(s.currentLoan).toBe(500)
    expect(s.repaymentCheckRatio).toBe(30)   // 300/1000*100
    expect(s.mortgageCheckRatio).toBe(40)     // 400/1000*100

    // 命名比例 + emptyBase='zero'（Property 10）经 caller composable 可用
    const c = vm.data.companies.value[0]
    expect(vm.data.getRepaymentRatio(c)).toBe(30)
    expect(vm.data.getMortgageRatio(c)).toBe(40)
    expect(vm.data.getBlockRows(c, 'block1').length).toBe(1)

    // buildPayload 契约（debounceSave 消费）
    const payload = vm.data.buildPayload()
    expect(payload._format).toBe('alternative-l05-v1')
    expect(payload.companies[0].balance.receipt_check_ratio).toBe(30)
    expect(payload.companies[0].balance.shipment_check_ratio).toBe(40)
  })
})
