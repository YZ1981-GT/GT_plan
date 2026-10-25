/**
 * 公式编辑弹窗的附注取数：按章节编号拼引用、请求真实的附注目录接口（spec formula-fetch-followup-defect-closure 7.2 浏览器实测发现）。
 *
 * 原状（逐条可打红）：
 * - 「NOTE」选择器请求 `/api/projects/{pid}/disclosure-notes/{yr}/tree`（不存在，恒 404）⇒ 列表恒空；即使有数据，
 *   引用也拿原始节点上不存在的 `row_name` / `title` 拼 ⇒ `NOTE('',…)`。
 * - 「数据源一览」的附注叶子按**标题**插入 `NOTE('货币资金',…)`；后端求值与保存校验都按章节编号取 ⇒ 恒取不到。
 * - 本项目附注未生成时，附注节点一直显示「加载中…」。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { get, getNoteTree, listSheets, msg } = vi.hoisted(() => ({
  get: vi.fn(), getNoteTree: vi.fn(), listSheets: vi.fn(),
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg }
})
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {} }) }))
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteTree: getNoteTree }))
vi.mock('@/services/acnr/useAcnr', () => ({ useAcnr: () => ({ listSheets, listCells: vi.fn(async () => []) }) }))
vi.mock('@/components/formula/FormulaDebugPanel.vue', () => ({ default: { template: '<div />' } }))

import FormulaEditDialog from '@/components/formula/FormulaEditDialog.vue'

const NOTES = [
  { note_section: '五、1', section_title: '货币资金', account_name: '货币资金' },
  { note_section: '五、2', section_title: '交易性金融资产', account_name: null },
  { note_section: '', section_title: '没有编号的节点' },
]

async function open() {
  const w = shallowMount(FormulaEditDialog, {
    props: { modelValue: false, row: { row_code: 'BS-002', row_name: '货币资金', formula: '' },
             projectId: 'p1', year: 2025 },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
  await w.setProps({ modelValue: true })
  for (let i = 0; i < 4; i++) await flushPromises()
  return { w, s: (w.vm as any).$.setupState }
}

const noteDomain = (s: any) => s.sourceTreeData.find((n: any) => n.key === 'note')
const noteLeaves = (s: any) => noteDomain(s).children.flatMap((ch: any) => ch.children || [ch])

describe('NOTE 选择器（快捷按钮）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listSheets.mockResolvedValue([])
    get.mockResolvedValue({})
    getNoteTree.mockResolvedValue(NOTES)
  })

  it('请求本项目附注目录接口，引用第一参是章节编号；没有编号的节点不列出', async () => {
    const { w, s } = await open()
    getNoteTree.mockClear()
    await s.openSourceBrowserForNote()
    expect(getNoteTree).toHaveBeenCalledWith('p1', 2025, expect.objectContaining({ _silent: true }))
    expect(get.mock.calls.map((c) => String(c[0])).filter((u) => u.includes('disclosure-notes'))).toEqual([])
    expect(s.sourceBrowserRows.map((r: any) => [r.row_code, r.row_name, r._ref])).toEqual([
      ['五、1', '货币资金', "NOTE('五、1','合计','期末')"],
      ['五、2', '交易性金融资产', "NOTE('五、2','合计','期末')"],
    ])
    s.onBrowserRowClick(s.sourceBrowserRows[0])
    expect(s.formulas[0].expression).toBe("NOTE('五、1','合计','期末')")
    w.unmount()
  })

  it('附注未生成（404）：列表为空并说明原因', async () => {
    const { w, s } = await open()
    getNoteTree.mockRejectedValue({ response: { status: 404 } })
    await s.openSourceBrowserForNote()
    expect(s.sourceBrowserRows).toEqual([])
    expect(msg.info).toHaveBeenCalledWith(expect.stringContaining('附注尚未生成'))
    w.unmount()
  })
})

describe('数据源一览的附注节点', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listSheets.mockResolvedValue([])
    get.mockResolvedValue({})
  })

  it('叶子按章节编号插入引用（不是标题）', async () => {
    getNoteTree.mockResolvedValue(NOTES)
    const { w, s } = await open()
    const leaves = noteLeaves(s)
    expect(leaves.map((l: any) => l._code)).toEqual(['五、1', '五、2'])
    s.onSourceNodeClick(leaves[0])
    expect(s.formulas[0].expression).toBe("NOTE('五、1','合计','期末')")
    w.unmount()
  })

  it('附注未生成：显示「尚未生成」，不是一直「加载中…」', async () => {
    getNoteTree.mockRejectedValue({ response: { status: 404 } })
    const { w, s } = await open()
    expect(noteDomain(s).children.map((c: any) => c.label)).toEqual(['本项目本年度附注尚未生成'])
    expect(msg.warning).not.toHaveBeenCalled()
    w.unmount()
  })
})
