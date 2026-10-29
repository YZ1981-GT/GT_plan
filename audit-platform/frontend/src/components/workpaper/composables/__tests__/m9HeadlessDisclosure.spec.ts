/** M9 两版模板行、持久化恢复、真实 Tab 与离屏 provider 的非零等价。 */
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(),
  httpGet: vi.fn(), httpPost: vi.fn(), httpPut: vi.fn(),
  eventOn: vi.fn(), eventOff: vi.fn(), eventEmit: vi.fn(),
  success: vi.fn(), warning: vi.fn(), error: vi.fn(), alert: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet, post: h.apiPost, put: h.apiPut } }))
vi.mock('@/utils/http', () => ({ default: { get: h.httpGet, post: h.httpPost, put: h.httpPut } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: h.eventOn, off: h.eventOff, emit: h.eventEmit } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: h.success, warning: h.warning, error: h.error },
  ElMessageBox: { alert: h.alert },
}))

import M9TabDisclosureListed from '../../m9/core/M9TabDisclosureListed.vue'
import M9TabDisclosureSoe from '../../m9/core/M9TabDisclosureSoe.vue'
import { m9HeadlessProvider } from '../m9HeadlessDisclosure'
import { restoreM9ListedRows, restoreM9SoeRows } from '../m9DisclosureForm'
import { M9_LISTED_SUBTABLE, M9_SOE_SUBTABLE } from '../m9NoteSectionMap'

const PROJECT = 'p-m9'
const WP = 'wp-m9'
const URL = `/api/projects/${PROJECT}/disclosure-notes/sync-from-workpaper`
const J = JSON.stringify
type Variant = 'listed' | 'soe'

function response(item_id: string, remark: string | number) {
  return { item_id, conclusion: null, remark: String(remark) }
}

const LISTED_LABELS = [
  '一、不能重分类进损益的其他综合收益',
  '1.重新计量设定受益计划变动额', '2.权益法下不能转损益的其他综合收益',
  '3.其他权益工具投资公允价值变动', '4.企业自身信用风险公允价值变动',
  '二、将重分类进损益的其他综合收益', '1.权益法下可转损益的其他综合收益',
  '2.其他债权投资公允价值变动', '3.金融资产重分类计入其他综合收益的金额',
  '4.其他债权投资信用减值准备', '5.现金流量套期储备',
  '6.外币财务报表折算差额', '其他综合收益合计',
]
const SOE_LABELS = [
  '一、以后不能重分类进损益的其他综合收益',
  '1、重新计量设定受益计划变动额', '2、权益法下不能转损益的其他综合收益',
  '3、其他权益工具投资公允价值变动', '4、企业自身信用风险公允价值变动',
  '5、不能转损益的保险合同金融变动（金融企业适用）', '6、其他',
  '二、将重分类进损益的其他综合收益',
  '1、权益法下可转损益的其他综合收益', '减：前期计入其他综合收益当期转入损益', '小计',
  '2、其他债权投资公允价值变动', '减：前期计入其他综合收益当期转入损益', '小计',
  '3、金融资产重分类计入其他综合收益的金额', '减：前期计入其他综合收益当期转入损益', '小计',
  '4、其他债权投资信用减值准备', '减：前期计入其他综合收益当期转入损益', '小计',
  '5、现金流量套期储备', '减：转为被套期项目初始确认金额的调整额',
  '前期计入其他综合收益当期转入损益', '小计',
  '6、外币财务报表折算差额', '减：前期计入其他综合收益当期转入损益', '小计',
  '7、可转损益的保险合同金融变动（金融企业适用）', '减：前期计入其他综合收益当期转入损益', '小计',
  '8、可转损益的分出再保险合同金融变动（金融企业适用）', '减：前期计入其他综合收益当期转入损益', '小计',
  '9、自用房地产或作为存货的房地产转换为以公允价值计量的投资性房地产在转换日公允价值大于账面价值部分',
  '减：前期计入其他综合收益当期转入损益', '小计',
  '10、多次交易分步处置子公司股权构成一揽子交易的，丧失控制权之前各次交易处置价款与对应净资产账面价值份额的差额',
  '减：前期计入其他综合收益当期转入损益', '小计',
  '11、其他', '减：前期计入其他综合收益当期转入损益的净额', '小计',
  '三、其他综合收益合计',
]

function responses(variant: Variant) {
  if (variant === 'listed') return [
    response('M9-disclosure-listed-balanceSheet-nonReclass-defined-benefit-priorYearAmount', 100),
    response('M9-disclosure-listed-balanceSheet-nonReclass-defined-benefit-preTaxAmount', 40),
    response('M9-disclosure-listed-balanceSheet-nonReclass-defined-benefit-transferToPl', 3),
    response('M9-disclosure-listed-balanceSheet-nonReclass-defined-benefit-taxEffect', 5),
    response('M9-disclosure-listed-balanceSheet-nonReclass-defined-benefit-afterTaxMinority', 2),
    response('M9-disclosure-listed-incomeStatement-reclass-translation-priorYearAmount', 200),
    response('M9-disclosure-listed-incomeStatement-reclass-translation-preTaxAmount', 60),
    response('M9-disclosure-listed-incomeStatement-reclass-translation-transferToPl', 7),
    response('M9-disclosure-listed-incomeStatement-reclass-translation-taxEffect', 9),
    response('M9-disclosure-listed-incomeStatement-reclass-translation-afterTaxMinority', 4),
    response('M9-disclosure-listed-remark', '上市其他综合收益说明'),
    response('M9-disclosure-listed-transfer', '上市转出说明'),
  ]
  return [
    response('M9-disclosure-soe-nonReclass-defined-benefit-beginBalance', 100),
    response('M9-disclosure-soe-nonReclass-defined-benefit-priorTaxEffect', 10),
    response('M9-disclosure-soe-nonReclass-defined-benefit-preTaxAmount', 35),
    response('M9-disclosure-soe-nonReclass-defined-benefit-taxEffect', 5),
    response('M9-disclosure-soe-reclass-cashflow-hedge-beginBalance', 200),
    response('M9-disclosure-soe-reclass-cashflow-hedge-priorTaxEffect', 20),
    response('M9-disclosure-soe-reclass-cashflow-hedge-preTaxAmount', 80),
    response('M9-disclosure-soe-reclass-cashflow-hedge-taxEffect', 8),
    response('M9-disclosure-soe-reclass-cashflow-hedge-transferToPL', 12),
    response('M9-disclosure-soe-capital', '国有资本说明'),
    response('M9-disclosure-soe-transfer', '国企转出说明'),
    response('M9-disclosure-soe-conclusion', '审计结论不进入附注正文'),
  ]
}

const STUBS = Object.fromEntries([
  'el-button', 'el-card', 'el-icon', 'el-input', 'el-table', 'el-table-column', 'el-tag',
  'el-radio-group', 'el-radio-button', 'el-descriptions', 'el-descriptions-item', 'WpAmountInput',
].map((name) => [name, true]))

async function fromTab(variant: Variant) {
  const fixture = responses(variant)
  h.apiGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? fixture : {})
  const Tab = variant === 'listed' ? M9TabDisclosureListed : M9TabDisclosureSoe
  const wrapper = shallowMount(Tab as any, {
    props: { wpId: WP, projectId: PROJECT, isReadonly: false, applicableStandards: [`${variant}_standalone`] },
    global: { stubs: STUBS },
  })
  try {
    await flushPromises()
    expect(h.httpPost).not.toHaveBeenCalled()
    const state = (wrapper.vm as any).$.setupState
    h.httpPost.mockClear()
    await state.syncToDisclosureNotes()
    return h.httpPost.mock.calls.find(([url]) => url === URL)?.[1]
  } finally {
    wrapper.unmount()
  }
}

async function fromProvider(variant: Variant) {
  h.httpGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? responses(variant) : {})
  h.httpPost.mockClear()
  const out = await m9HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'M9', year: 2025, variant,
    applicableStandards: [`${variant}_standalone`],
  })
  expect(out.sections[0].section).toBe(variant === 'listed' ? '五、57' : '八、79')
  expect(h.httpPut).not.toHaveBeenCalled()
  expect(h.apiPut).not.toHaveBeenCalled()
  return h.httpPost.mock.calls.find(([url]) => url === URL)?.[1]
}
beforeEach(() => {
  vi.useFakeTimers()
  for (const fn of Object.values(h)) fn.mockReset()
  h.httpPost.mockImplementation(async (_url: string, body: any) => ({
    section_id: body.section_id,
    rows_synced: Object.values(body.sub_table_data)
      .filter(Array.isArray).reduce((sum: number, rows: any) => sum + rows.length, 0),
    push_kept: [],
  }))
  h.apiPut.mockResolvedValue({})
})

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
})

describe.each(['listed', 'soe'] as const)('M9 %s', (variant) => {
  it('真实 Tab 与 provider 的非零请求体逐字节相同，且行名逐行对齐模板', async () => {
    const tab = await fromTab(variant)
    const provider = await fromProvider(variant)
    expect(J(provider)).toBe(J(tab))
    const tables = provider.sub_table_data
    const tableRows = variant === 'listed'
      ? [tables[M9_LISTED_SUBTABLE.balanceSheet], tables[M9_LISTED_SUBTABLE.incomeStatement]]
      : [tables[M9_SOE_SUBTABLE.main]]
    for (const rows of tableRows) {
      expect(rows.map((row: any) => row.label)).toEqual(variant === 'listed' ? LISTED_LABELS : SOE_LABELS)
      expect(rows.flatMap((row: any) => Object.values(row))
        .some((value: unknown) => typeof value === 'number' && value !== 0)).toBe(true)
    }
    if (variant === 'listed') {
      expect(tableRows[0][1].pre_tax).toBe(40)
      expect(tableRows[1].find((row: any) => row.label.includes('外币财务报表'))?.pre_tax).toBe(60)
      expect(J(tableRows[0])).not.toBe(J(tableRows[1]))
    } else {
      expect(tableRows[0]).toHaveLength(43)
      expect(tableRows[0].find((row: any) => row.label === '三、其他综合收益合计').end_pre_tax).toBe(103)
    }
  })
})

it('旧位置键只作为两张上市表的初始值，新稳定键可让两表继续独立', () => {
  const map = new Map([
    ['M9-disclosure-listed-nonReclass-0-preTaxAmount', response('legacy', 11)],
    ['M9-disclosure-listed-incomeStatement-nonReclass-defined-benefit-preTaxAmount', response('stable', 22)],
  ])
  expect(restoreM9ListedRows(map, 'balanceSheet', 'nonReclass')[0].preTaxAmount).toBe(11)
  expect(restoreM9ListedRows(map, 'incomeStatement', 'nonReclass')[0].preTaxAmount).toBe(22)
})

it('国企旧位置键可读回，并补齐独立的上期所得税字段', () => {
  const map = new Map([
    ['M9-disclosure-soe-reclass-0-beginBalance', response('old-begin', 31)],
    ['M9-disclosure-soe-reclass-0-priorTaxEffect', response('old-tax', 6)],
  ])
  const row = restoreM9SoeRows(map, 'reclass')[0]
  expect([row.beginBalance, row.priorTaxEffect]).toEqual([31, 6])
})
async function mountListed(isReadonly: boolean) {
  h.apiGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? responses('listed') : {})
  const wrapper = shallowMount(M9TabDisclosureListed as any, {
    props: { wpId: WP, projectId: PROJECT, isReadonly, applicableStandards: ['listed_standalone'] },
    global: { stubs: STUBS },
  })
  await flushPromises()
  h.httpPost.mockClear()
  h.apiPut.mockClear()
  return wrapper
}

it('上市真实编辑入口会合批自动同步，卸载会取消待执行请求', async () => {
  const wrapper = await mountListed(false)
  const state = (wrapper.vm as any).$.setupState
  state.updateNonReclassRow(0, 'preTaxAmount', 501)
  state.updateNonReclassRow(0, 'taxEffect', 51)
  await vi.advanceTimersByTimeAsync(800)
  await flushPromises()
  expect(h.httpPost.mock.calls.filter(([url]) => url === URL)).toHaveLength(1)
  h.httpPost.mockClear()
  state.updateReclassRow(0, 'preTaxAmount', 601)
  wrapper.unmount()
  await vi.advanceTimersByTimeAsync(800)
  expect(h.httpPost).not.toHaveBeenCalled()
})

it('只读态直接调用编辑入口也不写底稿、不发附注同步', async () => {
  const wrapper = await mountListed(true)
  ;(wrapper.vm as any).$.setupState.updateNonReclassRow(0, 'preTaxAmount', 701)
  await vi.advanceTimersByTimeAsync(800)
  await flushPromises()
  expect(h.apiPut).not.toHaveBeenCalled()
  expect(h.httpPost).not.toHaveBeenCalled()
  wrapper.unmount()
})
