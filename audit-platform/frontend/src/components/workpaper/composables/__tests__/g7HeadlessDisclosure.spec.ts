import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  apiPost: vi.fn(),
  httpGet: vi.fn(),
  httpPut: vi.fn(),
  httpPost: vi.fn(),
  schedule: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: h.apiGet, put: h.apiPut, post: h.apiPost },
}))
vi.mock('@/utils/http', () => ({
  default: { get: h.httpGet, put: h.httpPut, post: h.httpPost },
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fmtAmount: (value: number) => String(value) }),
}))
vi.mock('../useDisclosureAutoSync', () => ({
  useDisclosureAutoSync: () => ({ scheduleAutoSync: h.schedule, cancelPending: vi.fn() }),
}))
vi.mock('../useG7MainAiGenerate', () => ({
  useG7MainAiGenerate: () => ({
    aiAvailable: { value: false }, loading: { value: false }, generateAndConfirm: vi.fn(),
  }),
}))
vi.mock('../g7DisclosureCrossSheet', () => ({
  G7_SOURCE_SAVED_EVENT: 'g7:source-saved',
  loadG7DisclosureSources: vi.fn(async () => ({ sourcesHit: [] })),
  refreshListedTablesFromSources: vi.fn(() => []),
  refreshSoeTablesFromSources: vi.fn(() => []),
  collectDisclosureTruncations: vi.fn(() => []),
  formatTruncationHint: vi.fn(() => ''),
}))

import G7TabDisclosureListed from '../../g7-long-term-equity-main/disclosure/G7TabDisclosureListed.vue'
import G7TabDisclosureSOE from '../../g7-long-term-equity-main/disclosure/G7TabDisclosureSOE.vue'
import {
  createG7ListedDisclosureState,
} from '../../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  createG7SoeDisclosureState,
} from '../../g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'
import {
  G7_LISTED_RESPONSE_KEY,
  G7_SOE_RESPONSE_KEY,
  serialiseG7ListedState,
  serialiseG7SoeState,
} from '../g7DisclosureStateCodec'
import { g7HeadlessProvider } from '../g7HeadlessDisclosure'

type Variant = 'listed' | 'soe'
const PROJECT = 'project-1'
const WP = 'wp-1'
const URL = `/api/projects/${PROJECT}/disclosure-notes/sync-batch-from-workpaper`

const STUBS = Object.fromEntries([
  'el-button', 'el-card', 'el-collapse', 'el-collapse-item', 'el-dropdown',
  'el-dropdown-item', 'el-dropdown-menu', 'el-icon', 'el-input', 'el-input-number',
  'el-option', 'el-select', 'el-table', 'el-table-column', 'el-tag', 'el-tooltip',
  'G7DisclosureCell', 'GtIndexChip', 'GtReviewTrigger', 'WpDisclosureConsistencyPanel',
].map(name => [name, true]))

function fixture(variant: Variant) {
  if (variant === 'listed') {
    const state = createG7ListedDisclosureState()
    state.tables['investment-movement'][1].label = '甲合营企业'
    state.tables['investment-movement'][1].values.closingBook = 123.45
    state.texts['impairment-method'] = '上市长期资产减值测试说明'
    const slot = Object.keys(state.entitySlots ?? {})[0]
    if (slot) state.entitySlots![slot] = ['甲公司', '乙公司']
    return [{
      item_id: G7_LISTED_RESPONSE_KEY,
      remark: JSON.stringify(serialiseG7ListedState(state, '2026-10-29T00:00:00.000Z')),
      conclusion: null,
      version: 'v1',
    }]
  }
  const state = createG7SoeDisclosureState()
  state.tables['lte-classification'][0].values.closing = 456.78
  const narrative = G7_SOE_DISCLOSURE_SECTIONS.flatMap(section => section.narratives ?? [])[0]
  if (narrative) state.texts[narrative.id] = '国企合并范围变化说明'
  const slot = Object.keys(state.entitySlots ?? {})[0]
  if (slot) state.entitySlots![slot] = ['甲子公司', '乙子公司']
  return [{
    item_id: G7_SOE_RESPONSE_KEY,
    remark: JSON.stringify(serialiseG7SoeState(state, '2026-10-29T00:00:00.000Z')),
    conclusion: null,
    version: 'v1',
  }]
}
function batchReply(body: any) {
  const results = body.items.map((item: any) => ({
    success: true,
    section_id: item.section_id,
    synced_at: '2026-10-29T00:00:00Z',
    rows_synced: Object.entries(item.sub_table_data)
      .filter(([key, rows]) => !key.startsWith('_') && Array.isArray(rows))
      .reduce((sum, [, rows]) => sum + (rows as unknown[]).length, 0),
    texts_synced: 0,
    created: false,
    push_kept: [],
  }))
  return {
    success: true,
    sections_synced: results.length,
    rows_synced: results.reduce((sum: number, item: any) => sum + item.rows_synced, 0),
    texts_synced: 0,
    synced_at: '2026-10-29T00:00:00Z',
    results,
  }
}

async function tabRequest(variant: Variant): Promise<any> {
  const rows = fixture(variant)
  h.apiGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? rows : {})
  h.apiPut.mockResolvedValue({})
  h.apiPost.mockImplementation(async (_url: string, body: any) => batchReply(body))
  const Comp = variant === 'listed' ? G7TabDisclosureListed : G7TabDisclosureSOE
  const wrapper = shallowMount(Comp as any, {
    props: {
      wpId: WP,
      projectId: PROJECT,
      isReadonly: false,
      applicableStandards: [`${variant}_standalone`],
      htmlData: { project_context: { audit_year: 2025 } },
    },
    global: { stubs: STUBS },
  })
  try {
    await flushPromises()
    h.apiPut.mockClear()
    h.apiPost.mockClear()
    await (wrapper.vm as any).$.setupState.syncToDisclosureNotes()
    const call = h.apiPost.mock.calls.find(([url]) => url === URL)
    expect(call, `${variant} Tab 未发批量同步`).toBeTruthy()
    expect(h.apiPut, `${variant} 同步前应只保存一次底稿`).toHaveBeenCalledTimes(1)
    return call![1]
  } finally {
    wrapper.unmount()
  }
}

async function providerRequest(variant: Variant): Promise<{ body: any; out: any }> {
  h.httpGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? fixture(variant) : {})
  h.httpPost.mockImplementation(async (_url: string, body: any) => batchReply(body))
  h.httpPut.mockClear()
  h.httpPost.mockClear()
  h.apiPut.mockClear()
  const out = await g7HeadlessProvider({
    projectId: PROJECT,
    wpId: WP,
    wpCode: 'G7',
    year: 2025,
    variant,
    applicableStandards: [`${variant}_standalone`],
  })
  const calls = h.httpPost.mock.calls.filter(([url]) => url === URL)
  expect(calls, `${variant} provider 必须恰好一次 batch POST`).toHaveLength(1)
  expect(h.httpPut).not.toHaveBeenCalled()
  expect(h.apiPut).not.toHaveBeenCalled()
  return { body: calls[0][1], out }
}

beforeEach(() => {
  for (const mock of Object.values(h)) mock.mockReset()
})

describe.each<Variant>(['listed', 'soe'])('G7 %s 真实 Tab / headless 等价', (variant) => {
  it('非零存量与 entitySlots 恢复后，批量请求 JSON 逐字节相同', async () => {
    const fromTab = await tabRequest(variant)
    const { body: fromProvider, out } = await providerRequest(variant)
    expect(JSON.stringify(fromProvider)).toBe(JSON.stringify(fromTab))
    expect(out.sections).toHaveLength(fromProvider.items.length)
    expect(fromProvider.require_all_applied).toBe(true)
    expect(fromProvider.items.every((item: any) => !('_removed_table_keys' in item.sub_table_data))).toBe(true)
  })

  it('底稿保存失败时 Tab 不发送 batch，失败基线不会被推进', async () => {
    const rows = fixture(variant)
    h.apiGet.mockImplementation(async (url: string) => url.endsWith('/checklist-responses') ? rows : {})
    h.apiPut.mockRejectedValue(new Error('CAS conflict'))
    const Comp = variant === 'listed' ? G7TabDisclosureListed : G7TabDisclosureSOE
    const wrapper = shallowMount(Comp as any, {
      props: {
        wpId: WP, projectId: PROJECT, isReadonly: false,
        applicableStandards: [`${variant}_standalone`],
        htmlData: { project_context: { audit_year: 2025 } },
      },
      global: { stubs: STUBS },
    })
    try {
      await flushPromises()
      h.apiPost.mockClear()
      await (wrapper.vm as any).$.setupState.syncToDisclosureNotes()
      expect(h.apiPost).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })
})
describe('G7 章节与 owner 契约', () => {
  it('上市恰好 2 章节 / 15 表，两个章节均由 G7:listed 替换管理', async () => {
    const { body } = await providerRequest('listed')
    expect(body.items).toHaveLength(2)
    const tables = body.items.flatMap((item: any) =>
      Object.keys(item.sub_table_data).filter(key => !key.startsWith('_')),
    )
    expect(tables).toHaveLength(15)
    expect(body.items.every((item: any) =>
      item.owner_key === 'G7:listed' && item.replace_owned_tables === true,
    )).toBe(true)
  })

  it('国企恰好 14 章节 / 23 表；11 个表 owner，3 个纯叙述章节不声明 owner', async () => {
    const { body } = await providerRequest('soe')
    expect(body.items).toHaveLength(14)
    const tables = body.items.flatMap((item: any) =>
      Object.keys(item.sub_table_data).filter(key => !key.startsWith('_')),
    )
    expect(tables).toHaveLength(23)
    const tableOwners = body.items.filter((item: any) => item.replace_owned_tables)
    const narratives = body.items.filter((item: any) => !item.replace_owned_tables)
    expect(tableOwners).toHaveLength(11)
    expect(tableOwners.every((item: any) => item.owner_key === 'G7:soe')).toBe(true)
    expect(narratives).toHaveLength(3)
    expect(narratives.every((item: any) => item.owner_key === undefined)).toBe(true)
  })

  it('一次严格 batch 失败时，每个章节都回报失败且不退化为逐章节 POST', async () => {
    h.httpGet.mockResolvedValue(fixture('listed'))
    h.httpPost.mockRejectedValue(new Error('整批回滚'))
    const out = await g7HeadlessProvider({
      projectId: PROJECT, wpId: WP, wpCode: 'G7', year: 2025, variant: 'listed',
      applicableStandards: ['listed_standalone'],
    })
    expect(h.httpPost).toHaveBeenCalledTimes(1)
    expect(out.sections).toHaveLength(2)
    expect(out.sections.every(section => section.error === '整批回滚')).toBe(true)
  })

  it('没有可恢复的真实底稿状态时不推默认零骨架', async () => {
    h.httpGet.mockResolvedValue([])
    const out = await g7HeadlessProvider({
      projectId: PROJECT, wpId: WP, wpCode: 'G7', year: 2025, variant: 'soe',
      applicableStandards: ['soe_standalone'],
    })
    expect(out.sections).toEqual([])
    expect(h.httpPost).not.toHaveBeenCalled()
  })
})
