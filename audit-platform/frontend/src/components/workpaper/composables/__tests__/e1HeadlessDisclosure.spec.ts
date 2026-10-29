import { shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), emit: vi.fn(), warning: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: h.emit, on: vi.fn(), off: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: h.warning, error: vi.fn(), info: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmtAmount: (value: number) => String(value) }),
}))
vi.mock('@/composables/useAuditContext', () => ({ useAuditContext: () => ({ year: { value: 2025 } }) }))
vi.mock('../useDisclosureAutoSync', () => ({
  useDisclosureAutoSync: () => ({ scheduleAutoSync: vi.fn(), cancelPending: vi.fn() }),
}))
vi.mock('../useE1AiGenerate', () => ({
  useE1AiGenerate: () => ({ generateText: vi.fn(), isGenerating: { value: false } }),
}))
vi.mock('../hostApplicableStandards', () => ({
  useHostApplicableStandards: (options: any) => ({ value: options.explicit() ?? [] }),
}))

import E1TabDisclosure from '../../e1/E1TabDisclosure.vue'
import { e1HeadlessProvider } from '../e1HeadlessDisclosure'
import {
  E1_DISCLOSURE_SHEET_NAME,
  E1_MAIN_TABLE,
  E1_RESTRICTED_TABLE,
} from '../e1NoteSectionMap'
import { E1_FX_TABLE } from '../e1FxNoteSectionMap'
import { e1NoteTextKey, e1NoteTexts } from '../e1DisclosureScope'

type Variant = 'listed' | 'soe'
const PROJECT = 'project-1'
const WP = 'wp-1'
const SYNC_URL = `/api/projects/${PROJECT}/disclosure-notes/sync-from-workpaper`

const STUBS = Object.fromEntries([
  'el-alert', 'el-button', 'el-card', 'el-collapse', 'el-collapse-item', 'el-dropdown',
  'el-dropdown-item', 'el-dropdown-menu', 'el-empty', 'el-icon', 'el-input',
  'el-input-number', 'el-option', 'el-result', 'el-segmented', 'el-select', 'el-table',
  'el-table-column', 'el-tag', 'el-tooltip', 'GtIndexChip', 'WpAmountInput',
  'WpDisclosureConsistencyPanel',
].map(name => [name, true]))

function response(item_id: string, remark: unknown) {
  return { item_id, remark: typeof remark === 'string' ? remark : JSON.stringify(remark), conclusion: null }
}

function foreignState() {
  const group = {
    id: 'cash', groupId: 'cash', item: '库存现金：', currency: '', isGroup: true,
    indent: false, endForeign: 0, endRate: 0, openForeign: 0, openRate: 0,
  }
  const usd = {
    id: 'usd', groupId: 'cash', item: '美元', currency: '美元', isGroup: false,
    indent: true, endForeign: 100, endRate: 7.2, openForeign: 80, openRate: 7.1,
  }
  return { mode: 'detailed', simpleRows: [], detailedRows: [group, usd] }
}

function fixtures(variant: Variant) {
  const rows = [
    response(`E1-disclosure-${variant}-foreign-currency`, foreignState()),
    response(`E1-disclosure-${variant}-restricted`, [{
      id: 'restricted_custom_1', bucketKey: 'custom:保证金', label: '保证金',
      openingAmount: 20, endingAmount: 30, reason: '开票保证金', codes: [], fromFourTable: false,
    }]),
    response(`E1-disclosure-${variant}-restricted-map`, {}),
    response(`E1-disclosure-${variant}-restricted-seq`, '1'),
  ]
  const first = e1NoteTexts(variant)[0]
  rows.push(response(e1NoteTextKey(variant, first.key), `${variant} 受限及境外款项说明`))
  return rows
}

function htmlData() {
  return {
    restricted_prefill: {
      leaves: [], bucketDefs: [], source: { report_row_code: 'BS-002', chart_available: true },
    },
  }
}
function success(body: any) {
  const rows = Object.entries(body.sub_table_data ?? {})
    .filter(([key, value]) => !key.startsWith('_') && Array.isArray(value))
    .reduce((sum, [, value]) => sum + (value as unknown[]).length, 0)
  return {
    data: {
      success: true, section_id: body.section_id, rows_synced: rows,
      row_scope_unresolved: [], row_scope_unresolved_reasons: {}, push_kept: [],
    },
  }
}

function mapOf(variant: Variant) {
  return new Map(fixtures(variant).map(item => [item.item_id, item]))
}

async function tabPayloads(variant: Variant): Promise<any[]> {
  const responses = mapOf(variant)
  h.post.mockImplementation(async (_url: string, body: any) => success(body))
  const wrapper = shallowMount(E1TabDisclosure as any, {
    props: {
      wpId: WP,
      projectId: PROJECT,
      allResponses: responses,
      saveImmediate: vi.fn(async () => {}),
      debouncedSave: vi.fn(async () => {}),
      isReadonly: false,
      sheetName: E1_DISCLOSURE_SHEET_NAME[variant],
      variant,
      htmlData: htmlData(),
      applicableStandards: [`${variant}_standalone`],
    },
    global: { stubs: STUBS },
  })
  try {
    h.post.mockClear()
    await (wrapper.vm as any).$.setupState.syncToDisclosureNotes()
    return h.post.mock.calls
      .filter(([url]) => url === SYNC_URL)
      .map(([, body]) => body)
  } finally {
    wrapper.unmount()
  }
}

async function providerPayloads(variant: Variant): Promise<{ payloads: any[]; result: any }> {
  h.get.mockImplementation(async (url: string) => {
    if (url.endsWith('/checklist-responses')) return fixtures(variant)
    if (url.endsWith('/render-config')) {
      return { sheets: [{ sheet_name: E1_DISCLOSURE_SHEET_NAME[variant], html_data: htmlData() }] }
    }
    return {}
  })
  h.post.mockImplementation(async (_url: string, body: any) => success(body))
  h.post.mockClear()
  h.put.mockClear()
  h.emit.mockClear()
  const result = await e1HeadlessProvider({
    projectId: PROJECT, wpId: WP, wpCode: 'E1', year: 2025, variant,
    applicableStandards: [`${variant}_standalone`],
  })
  return {
    payloads: h.post.mock.calls.filter(([url]) => url === SYNC_URL).map(([, body]) => body),
    result,
  }
}

beforeEach(() => {
  for (const mock of Object.values(h)) mock.mockReset()
})

describe.each<Variant>(['listed', 'soe'])('E1 %s 真实 Tab / headless 等价', (variant) => {
  it('共享恢复与 builder 对非零 fixture 产出逐字节相同请求', async () => {
    const fromTab = await tabPayloads(variant)
    const { payloads: fromProvider, result } = await providerPayloads(variant)
    expect(JSON.stringify(fromProvider)).toBe(JSON.stringify(fromTab))
    expect(fromProvider).toHaveLength(variant === 'listed' ? 4 : 3)
    expect(result.sections).toHaveLength(fromProvider.length)
    expect(h.put).not.toHaveBeenCalled()
    expect(h.emit).not.toHaveBeenCalled()

    const main = fromProvider.find(payload =>
      payload.section_id === (variant === 'listed' ? '五、1' : '八、1'))
    expect(main).toBeDefined()
    expect(main.sub_table_data[E1_MAIN_TABLE]).toBeUndefined()
    expect(main.sub_table_data[E1_RESTRICTED_TABLE]).toHaveLength(2)
    expect(main.year).toBe(2025)
    expect(fromProvider.some(payload => payload.sub_table_data[E1_FX_TABLE])).toBe(true)
  })
})
describe('E1 无来源、明确空与 row_scope 失败语义', () => {
  it('无保存状态且 render-config 只有空 source 时零写入，不推默认零或删除', async () => {
    h.get.mockImplementation(async (url: string) => url.endsWith('/render-config')
      ? { sheets: [{ sheet_name: E1_DISCLOSURE_SHEET_NAME.listed, html_data: {
          restricted_prefill: { leaves: [], bucketDefs: [], source: {} },
        } }] }
      : [])
    const result = await e1HeadlessProvider({
      projectId: PROJECT, wpId: WP, wpCode: 'E1', year: 2025, variant: 'listed',
      applicableStandards: ['listed_standalone'],
    })
    expect(result.sections).toEqual([])
    expect(h.post).not.toHaveBeenCalled()
  })

  it('受限四表预填只从目标 sheet.html_data 读取，作为唯一来源也能生成非零载荷', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url.endsWith('/checklist-responses')) return []
      return { sheets: [{ sheet_name: E1_DISCLOSURE_SHEET_NAME.soe, html_data: {
        restricted_prefill: {
          leaves: [{
            code: '1002.01', name: '银行承兑保证金', opening: 11, closing: 22,
            slot: 'bank', autoBucket: 'guarantee',
          }],
          bucketDefs: [{ key: 'guarantee', label: '保证金', isPlatformExtra: false, displayOrder: 1 }],
          source: { report_row_code: 'BS-002', chart_available: true },
        },
      } }] }
    })
    h.post.mockImplementation(async (_url: string, body: any) => success(body))
    await e1HeadlessProvider({
      projectId: PROJECT, wpId: WP, wpCode: 'E1', year: 2025, variant: 'soe',
      applicableStandards: ['soe_standalone'],
    })
    expect(h.post.mock.calls.length).toBeGreaterThan(0)
    const main = h.post.mock.calls.map(([, body]) => body)
      .find(body => body.section_id === '八、1')
    expect(main.sub_table_data[E1_RESTRICTED_TABLE][0]).toMatchObject({
      label: '保证金', end_amount: 22, prior_amount: 11,
    })
  })

  it('明确保存空受限表与无来源不同：只发送主章节删除语义', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url.endsWith('/checklist-responses')) {
        return [response('E1-disclosure-soe-restricted', [])]
      }
      return { sheets: [{ sheet_name: E1_DISCLOSURE_SHEET_NAME.soe, html_data: {} }] }
    })
    h.post.mockImplementation(async (_url: string, body: any) => success(body))
    const result = await e1HeadlessProvider({
      projectId: PROJECT, wpId: WP, wpCode: 'E1', year: 2025, variant: 'soe',
      applicableStandards: ['soe_standalone'],
    })
    expect(h.post).toHaveBeenCalledTimes(1)
    const body = h.post.mock.calls[0][1]
    expect(body.sub_table_data._removed_table_keys).toEqual([E1_RESTRICTED_TABLE])
    expect(body.sub_table_data[E1_MAIN_TABLE]).toBeUndefined()
    expect(result.sections[0].section).toBe('八、1')
  })

  it('未归类叶子不被误当成权威空，不触发删除', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url.endsWith('/checklist-responses')) return []
      return { sheets: [{ sheet_name: E1_DISCLOSURE_SHEET_NAME.soe, html_data: {
        restricted_prefill: {
          leaves: [{ code: '1002.01', name: '待判断账户', opening: 10, closing: 20, slot: 'bank', autoBucket: null }],
          bucketDefs: [], source: { report_row_code: 'BS-002', chart_available: true },
        },
      } }] }
    })
    const result = await e1HeadlessProvider({
      projectId: PROJECT, wpId: WP, wpCode: 'E1', year: 2025, variant: 'soe',
      applicableStandards: ['soe_standalone'],
    })
    expect(result.sections).toEqual([])
    expect(h.post).not.toHaveBeenCalled()
  })

  it('row_scope_unresolved 在离屏结果中按失败回报并保留具体原因', async () => {
    h.get.mockImplementation(async (url: string) => {
      if (url.endsWith('/checklist-responses')) return fixtures('listed')
      return { sheets: [{ sheet_name: E1_DISCLOSURE_SHEET_NAME.listed, html_data: htmlData() }] }
    })
    h.post.mockImplementation(async (_url: string, body: any) => ({ data: {
      success: true,
      section_id: body.section_id,
      rows_synced: 0,
      row_scope_unresolved: body.sub_table_data?._row_scope ? [Object.keys(body.sub_table_data._row_scope)[0]] : [],
      row_scope_unresolved_reasons: { [E1_FX_TABLE]: '模板缺段首码' },
      push_kept: [],
    } }))
    const result = await e1HeadlessProvider({
      projectId: PROJECT, wpId: WP, wpCode: 'E1', year: 2025, variant: 'listed',
      applicableStandards: ['listed_standalone'],
    })
    const failed = result.sections.filter((item: any) => item.error)
    expect(failed.length).toBeGreaterThan(0)
    expect(failed.some((item: any) => item.error.includes('模板缺段首码'))).toBe(true)
  })
})
