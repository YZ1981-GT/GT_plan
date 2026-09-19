/**
 * D4 IPO 表间提取（inter_sheet）取数接线判据 —— AC 3.4「不填也有值」的落地证明。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Task 7 收口
 *
 * 🔴 为什么必须有这组判据（复盘实证的真实缺陷）：此前 `IPO_FORMULA_PRESETS` 的 7 条
 *    inter_sheet 只**声明**了 resolver 名，Property 13 也只校验「名字在后端注册表里」，
 *    于是「声明齐全、守卫全绿、运行时零调用」—— 金额列永远是 `newRow` 里硬置的 null，
 *    「表间提取」从未真正发生。本文件把判据落到**真的发了请求、真的按声明映射回填**上。
 *
 * 判据：
 *   - 按 resolver 分组只发一次请求（D4-28 三列共用 `d4_28_customer_balances`）
 *   - snake_case 返回字段 → camelCase 列 key 的映射正确（sales_amount → salesAmount）
 *   - resolver 返回 null → 列**保持空**，绝不写 0（「宁缺勿造」，0 会被误读成已核对为零）
 *   - overwrite=false 不覆盖用户已录入值；overwrite=true 覆盖
 *   - 多行同名只打一次后端（去重缓存）
 *   - 取数失败不抛、不清空已有值，fetchError 可见（fail-visible）
 *   - 回填后表内派生列（占比）跟着重算
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'

const getMock = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: unknown[]) => getMock(...args) },
  apiProxy: { get: (...args: unknown[]) => getMock(...args) },
  default: { get: (...args: unknown[]) => getMock(...args) },
}))

import { useIpoChecklistTab } from '../useIpoChecklistTab'

const PROJECT = 'proj-1'

/**
 * 挂载「父 provide → 子用 composable」。
 *
 * 🔴 必须分两层：Vue 的 `inject` 只沿**父链**查找，组件自己 `provide` 的键在它自己的
 *    `setup()` 里 inject 不到。写成一层会让 `d4AuditYear` 恒为 null、取数在「缺年度」
 *    分支静默早退 —— 判据会变成「断言没发请求」的假绿。
 */
function setupTab(
  sheetCode: 'D4-25' | 'D4-26' | 'D4-27' | 'D4-28',
  year: number | null = 2025,
  readonly = false,
) {
  const allResponses: Ref<Map<string, any>> = ref(new Map<string, any>())
  let api!: ReturnType<typeof useIpoChecklistTab>
  const Child = defineComponent({
    setup() {
      api = useIpoChecklistTab({
        sheetCode,
        wpId: ref('wp1'),
        projectId: ref(PROJECT),
        allResponses,
        isReadonly: ref(readonly),
      })
      return () => null
    },
  })
  const Parent = defineComponent({
    provide: { d4AuditYear: year },
    render: () => h(Child),
  })
  const wrapper = mount(Parent)
  return { api, wrapper }
}

beforeEach(() => {
  getMock.mockReset()
})

describe('inter_sheet 取数：真的发请求并按声明映射回填', () => {
  it('D4-25：sales_amount/ar_balance → salesAmount/arBalance，一个 resolver 一次请求', async () => {
    getMock.mockResolvedValue({ summary: 'x', sales_amount: 1234.567, ar_balance: 500 })
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [{ rowId: 'r1', seq: 1, customerName: '甲公司' } as any]

    const out = await api.refreshInterSheet({ overwrite: true })

    expect(getMock).toHaveBeenCalledTimes(1)
    const [url, cfg] = getMock.mock.calls[0] as [string, any]
    expect(url).toBe(`/api/projects/${PROJECT}/auto-data/d4_25_dealer_sales`)
    expect(cfg.params).toEqual({ year: 2025, customer_name: '甲公司' })
    // precision=2 → 四舍五入到分
    expect(api.rows.value[0].salesAmount).toBeCloseTo(1234.57, 4)
    expect(api.rows.value[0].arBalance).toBeCloseTo(500, 4)
    expect(out.filled).toBe(2)
    expect(out.failed).toBe(0)
    wrapper.unmount()
  })

  it('D4-28：三列由同一 resolver 一次取回（不发 3 次请求）', async () => {
    getMock.mockResolvedValue({
      summary: 'x', sales_amount: 100, ar_balance: 20, contract_liab_balance: 5,
    })
    const { api, wrapper } = setupTab('D4-28')
    api.rows.value = [{ rowId: 'r1', seq: 1, customerName: '乙公司' } as any]

    await api.refreshInterSheet({ overwrite: true })

    expect(getMock).toHaveBeenCalledTimes(1)
    expect(api.rows.value[0].salesAmount).toBeCloseTo(100, 4)
    expect(api.rows.value[0].arBalance).toBeCloseTo(20, 4)
    expect(api.rows.value[0].contractLiabBalance).toBeCloseTo(5, 4)
    wrapper.unmount()
  })

  it('D4-27：按 name 传参、annual_sales → annualSales', async () => {
    getMock.mockResolvedValue({ summary: 'x', annual_sales: 888 })
    const { api, wrapper } = setupTab('D4-27')
    api.rows.value = [{ rowId: 'r1', seq: 1, name: '陈某' } as any]

    await api.refreshInterSheet({ overwrite: true })

    const [, cfg] = getMock.mock.calls[0] as [string, any]
    expect(cfg.params.customer_name).toBe('陈某') // resolver 兼容 person_name/name/customer_name
    expect(api.rows.value[0].annualSales).toBeCloseTo(888, 4)
    wrapper.unmount()
  })
})

describe('「宁缺勿造」：null 保持空，绝不写 0', () => {
  it('resolver 返回 null 的字段 → 列保持原空值，不写 0', async () => {
    getMock.mockResolvedValue({ summary: '未匹配', sales_amount: null, ar_balance: null })
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [{ rowId: 'r1', seq: 1, customerName: '无账面客户', salesAmount: null } as any]

    const out = await api.refreshInterSheet({ overwrite: true })

    expect(api.rows.value[0].salesAmount).toBeNull()
    expect(api.rows.value[0].arBalance).toBeUndefined() // 从未被写过
    expect(out.filled).toBe(0)
    wrapper.unmount()
  })
})

describe('覆盖语义：overwrite=false 不动用户录入值', () => {
  it('已有手工值时 overwrite=false 跳过；overwrite=true 覆盖', async () => {
    getMock.mockResolvedValue({ summary: 'x', sales_amount: 999, ar_balance: null })
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [{ rowId: 'r1', seq: 1, customerName: '甲公司', salesAmount: 111 } as any]

    await api.refreshInterSheet({ overwrite: false })
    expect(api.rows.value[0].salesAmount).toBe(111) // 用户值不被自动取数抹掉

    await api.refreshInterSheet({ overwrite: true })
    expect(api.rows.value[0].salesAmount).toBeCloseTo(999, 4) // 显式刷新才覆盖
    wrapper.unmount()
  })
})

describe('去重与失败面', () => {
  it('多行同名只打一次后端（去重缓存）', async () => {
    getMock.mockResolvedValue({ summary: 'x', sales_amount: 10, ar_balance: 1 })
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [
      { rowId: 'r1', seq: 1, customerName: '同名公司' } as any,
      { rowId: 'r2', seq: 2, customerName: '同名公司' } as any,
    ]
    await api.refreshInterSheet({ overwrite: true })
    expect(getMock).toHaveBeenCalledTimes(1)
    expect(api.rows.value[1].salesAmount).toBeCloseTo(10, 4) // 第二行也回填了
    wrapper.unmount()
  })

  it('无名称的行不发请求（resolver 也会短路，省一次往返）', async () => {
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [{ rowId: 'r1', seq: 1, customerName: '   ' } as any]
    const out = await api.refreshInterSheet({ overwrite: true })
    expect(getMock).not.toHaveBeenCalled()
    expect(out.filled).toBe(0)
    wrapper.unmount()
  })

  it('请求抛错：不抛给调用方、不清空已有值、fetchError 可见（fail-visible）', async () => {
    getMock.mockRejectedValue(new Error('boom'))
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [{ rowId: 'r1', seq: 1, customerName: '甲公司', salesAmount: 777 } as any]

    const out = await api.refreshInterSheet({ overwrite: true })

    expect(out.failed).toBe(1)
    expect(api.rows.value[0].salesAmount).toBe(777) // 原值保留，未被清空/写 0
    expect(api.fetchError.value).toContain('取数失败')
    wrapper.unmount()
  })

  it('resolver 降级（_error:true）按失败计，不当成 0 回填', async () => {
    getMock.mockResolvedValue({ summary: '⚠️ 数据获取失败', _error: true })
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [{ rowId: 'r1', seq: 1, customerName: '甲公司' } as any]
    const out = await api.refreshInterSheet({ overwrite: true })
    expect(out.failed).toBe(1)
    expect(api.rows.value[0].salesAmount).toBeUndefined()
    expect(api.fetchError.value).toContain('取数失败')
    wrapper.unmount()
  })

  it('缺审计年度：不发请求且显式报错（不猜"当前年-1"）', async () => {
    const { api, wrapper } = setupTab('D4-25', null)
    api.rows.value = [{ rowId: 'r1', seq: 1, customerName: '甲公司' } as any]
    const out = await api.refreshInterSheet({ overwrite: true })
    expect(getMock).not.toHaveBeenCalled()
    expect(out.filled).toBe(0)
    expect(api.fetchError.value).toContain('审计年度')
    wrapper.unmount()
  })
})

describe('取数后表内派生列联动', () => {
  it('回填 salesAmount 后 D4-25 占比列自动重算', async () => {
    getMock.mockImplementation((_url: string, cfg: any) => {
      const name = cfg.params.customer_name
      return Promise.resolve({
        summary: 'x',
        sales_amount: name === '甲公司' ? 300 : 700,
        ar_balance: null,
      })
    })
    const { api, wrapper } = setupTab('D4-25')
    api.rows.value = [
      { rowId: 'r1', seq: 1, customerName: '甲公司' } as any,
      { rowId: 'r2', seq: 2, customerName: '乙公司' } as any,
    ]

    await api.refreshInterSheet({ overwrite: true })

    expect(api.rows.value[0].salesAmount).toBeCloseTo(300, 4)
    // 占比 = 300 / 1000（表间提取值进来后 intra_sheet 派生列必须跟着算）
    expect(api.rows.value[0].proportion).toBeCloseTo(0.3, 4)
    expect(api.rows.value[1].proportion).toBeCloseTo(0.7, 4)
    wrapper.unmount()
  })
})

describe('只读禁写', () => {
  it('isReadonly 时不取数（AC 2.8 同族：只读不得写入）', async () => {
    getMock.mockResolvedValue({ summary: 'x', sales_amount: 1, ar_balance: 1 })
    const { api, wrapper } = setupTab('D4-25', 2025, true)
    api.rows.value = [{ rowId: 'r1', seq: 1, customerName: '甲公司' } as any]
    const out = await api.refreshInterSheet({ overwrite: true })
    expect(getMock).not.toHaveBeenCalled()
    expect(out.filled).toBe(0)
    expect(api.rows.value[0].salesAmount).toBeUndefined()
    wrapper.unmount()
  })
})
