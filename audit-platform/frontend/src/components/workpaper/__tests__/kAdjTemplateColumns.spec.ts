/**
 * K3 ~ K7「调整分录汇总」按模板接列（spec oo-writeback-template-parity-closure R3 批 B2c）。
 *
 * 模板十列（六册逐字相同）：调整事项说明 / 类别 / 报表项目 / 科目名称 / 附注项目 / …… / 借方调整金额 /
 * 贷方调整金额 / 索引 / 备注。契约逐列声明了，前端原来缺 类别 / 报表项目 / 附注项目 / 索引（K5 另缺备注、
 * 借贷两列契约接 debitAmount / creditAmount 而前端存 debit / credit，K7 只缺类别、「类别」列放的是 AJE / RJE），
 * OO 侧填的回到 HTML、下一次保存就被擦掉（载入时只挑已知字段）。本文件钉：
 *   1. 表单列序前段 = 模板列序（模板没有的 类型 / 科目代码 / 编制人 … 排在后面）；
 *   2. 契约每个字段绑的键，表单里那一列的标签就是模板表头（键名对上而列错位也会红）；
 *   3. 载入保留未知键、类别缺键按类型给缺省、改类型时缺省值跟着换（用户改过的不动）、新行带四列；
 *   4. K5 / K6 合计行按列 prop 落在借贷两列下（K5 原按位置落到「摘要」「借方」下）；
 *   5. K2（借方科目 / 贷方科目分列，与模板单科目行不同构，R2 待裁）载入至少不丢 OO 侧填的模板列。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount, flushPromises } from '@vue/test-utils'
import {
  K_ADJ_CATEGORY_OPTIONS, defaultKAdjCategory, followEntryTypeCategory, newKAdjTemplateFields, readKAdjTemplateFields,
} from '../composables/kAdjTemplateFields'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
  ElMessageBox: { prompt: vi.fn(async () => ({ value: '新增分录' })), confirm: vi.fn(async () => 'confirm') },
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(async () => ({ data: {} })), post: vi.fn(async () => ({ data: {} })) } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(async () => []), post: vi.fn(async () => ({})), put: vi.fn(async () => ({})) } }))
vi.mock('@/composables/useAuditContext', () => ({ useAuditContext: () => ({ year: { value: 2025 } }) }))
vi.mock('@/components/workpaper/composables/useAdjustmentCentralSync', async () => {
  const { ref } = await import('vue')
  return {
    CENTRAL_STATUS_LABELS: {},
    useAdjustmentCentralSync: () => ({ centralStatus: ref(null), syncing: ref(false), syncToCentral: vi.fn(), refreshStatus: vi.fn() }),
  }
})
const ieStub = () => ({ exportTemplate: vi.fn(), exportData: vi.fn(), importData: vi.fn(async () => null) })
vi.mock('@/components/workpaper/composables/useK3ImportExport', () => ({ useK3ImportExport: ieStub }))
vi.mock('@/components/workpaper/composables/useK4ImportExport', () => ({ useK4ImportExport: ieStub }))
vi.mock('@/components/workpaper/composables/useK6ImportExport', () => ({ useK6ImportExport: ieStub }))
vi.mock('@/components/workpaper/composables/useK7ImportExport', () => ({ useK7ImportExport: ieStub }))

const REPO = resolve(__dirname, '../../../../../..')
const TEMPLATE_ORDER = ['调整事项说明', '类别', '报表项目', '科目名称', '附注项目', '借方调整金额', '贷方调整金额', '索引', '备注']

interface Case {
  cycle: string
  vue: string
  contract: string
  itemId: string
  debitKey: string
  creditKey: string
  idLabel: string
  newReportItem: string
  load: () => Promise<any>
}
const CASES: Case[] = [
  { cycle: 'K3', vue: 'k3/core/K3TabAdjustment.vue', contract: 'k3.other_payables_adjustment.json', itemId: 'K3-3-adj-entries', debitKey: 'debitAmount', creditKey: 'creditAmount', idLabel: '序号', newReportItem: '其他应付款', load: () => import('../k3/core/K3TabAdjustment.vue') },
  { cycle: 'K4', vue: 'k4/core/K4TabAdjustment.vue', contract: 'k4.other_current_liabilities_adjustment.json', itemId: 'K4-3-adj-entries', debitKey: 'debitAmount', creditKey: 'creditAmount', idLabel: '编号', newReportItem: '其他流动负债', load: () => import('../k4/core/K4TabAdjustment.vue') },
  { cycle: 'K5', vue: 'k5/core/K5TabAdjustment.vue', contract: 'k5.provisions_adjustment.json', itemId: 'K5-3-entries', debitKey: 'debit', creditKey: 'credit', idLabel: '序号', newReportItem: '预计负债', load: () => import('../k5/core/K5TabAdjustment.vue') },
  { cycle: 'K6', vue: 'k6/core/K6TabAdjustment.vue', contract: 'k6.held_for_sale_adjustment.json', itemId: 'K6-3-adj-entries', debitKey: 'debitAmount', creditKey: 'creditAmount', idLabel: '序', newReportItem: '持有待售资产', load: () => import('../k6/core/K6TabAdjustment.vue') },
  { cycle: 'K7', vue: 'k7/core/K7TabAdjustment.vue', contract: 'k7.deferred_income_adjustment.json', itemId: 'K7-3-adj-entries', debitKey: 'debitAmount', creditKey: 'creditAmount', idLabel: '序号', newReportItem: '递延收益', load: () => import('../k7/core/K7TabAdjustment.vue') },
]

/** 分录表（`:data="entries"` 到 `</el-table>`）逐列的块，按出现顺序。 */
function columnChunks(vue: string): string[] {
  const src = readFileSync(resolve(__dirname, '..', vue), 'utf-8')
  const start = src.indexOf(':data="entries"')
  expect(start, `${vue} 找不到 :data="entries"`).toBeGreaterThan(0)
  const body = src.slice(start, src.indexOf('</el-table>', start))
  return body.split('<el-table-column').slice(1)
}
const labelOf = (chunk: string) => /^[^>]*?\blabel="([^"]*)"/.exec(chunk)?.[1] ?? ''
const propOf = (chunk: string) => /^[^>]*?\bprop="([^"]*)"/.exec(chunk)?.[1]
function contractFields(file: string, itemId: string): Array<{ key: string; header: string }> {
  const c = JSON.parse(readFileSync(resolve(REPO, 'backend/data/workpaper_sync_contracts', file), 'utf-8'))
  return c.sheets.flatMap((s: any) => s.tables ?? []).flatMap((t: any) => t.fields)
    .filter((f: any) => f.store_item_id === itemId && f.header_text !== '……')
    .map((f: any) => ({ key: f.json_pointer.split('/').pop(), header: f.header_text }))
}
const LABEL_ALIAS: Record<string, string> = { '类别（报表调整/账项调整/其他）': '类别' }

describe.each(CASES)('$cycle 调整分录汇总表单', (c) => {
  it('列序：编号列之后前段 = 模板列序', () => {
    const labels = columnChunks(c.vue).map(labelOf).filter((l) => l && l !== '操作')
    expect(labels[0]).toBe(c.idLabel)
    expect(labels.slice(1, 1 + TEMPLATE_ORDER.length)).toEqual(TEMPLATE_ORDER)
  })
  it('契约列 ↔ 表单列：契约绑的键，表单那一列的标签就是模板表头', () => {
    const ui = new Map<string, string>()
    for (const chunk of columnChunks(c.vue)) {
      const key = /\brow\.(\w+)/.exec(chunk)?.[1]
      if (key && !ui.has(key)) ui.set(key, labelOf(chunk))
    }
    const fields = contractFields(c.contract, c.itemId)
    expect(fields.map((f) => f.key)).toEqual(
      ['summary', 'category', 'reportItem', 'accountName', 'noteItem', c.debitKey, c.creditKey, 'indexRef', 'remark'])
    const bad = fields
      .filter(({ key, header }) => ui.get(key) !== (LABEL_ALIAS[header] ?? header))
      .map(({ key, header }) => `${key}：模板「${header}」 表单「${ui.get(key) ?? '（没有这一列）'}」`)
    expect(bad).toEqual([])
  })
})

describe('kAdjTemplateFields', () => {
  it('类别缺省按类型：重分类 = 报表调整，其余 = 账项调整', () => {
    expect(K_ADJ_CATEGORY_OPTIONS).toEqual(['报表调整', '账项调整', '其他'])
    expect(defaultKAdjCategory('RJE')).toBe('报表调整')
    expect(defaultKAdjCategory('AJE')).toBe('账项调整')
    expect(defaultKAdjCategory(undefined)).toBe('账项调整')
  })
  it('载入：缺键给缺省，空串（用户清空）照留，其余三列缺省空', () => {
    expect(readKAdjTemplateFields({ entryType: 'RJE' })).toEqual({ category: '报表调整', reportItem: '', noteItem: '', indexRef: '' })
    expect(readKAdjTemplateFields({ entryType: 'RJE', category: '' }).category).toBe('')
    expect(readKAdjTemplateFields({ category: '其他', reportItem: '甲', noteItem: '乙', indexRef: 'K-1' }))
      .toEqual({ category: '其他', reportItem: '甲', noteItem: '乙', indexRef: 'K-1' })
  })
  it('新行 / 改类型', () => {
    expect(newKAdjTemplateFields('RJE', '预计负债')).toEqual({ category: '报表调整', reportItem: '预计负债', noteItem: '', indexRef: '' })
    const e = { category: '账项调整' }
    followEntryTypeCategory(e, 'AJE', 'RJE')
    expect(e.category).toBe('报表调整')
    const kept = { category: '其他' }
    followEntryTypeCategory(kept, 'AJE', 'RJE')
    expect(kept.category).toBe('其他')
  })
})

const stubs = {
  GtIndexChip: true, CycleImportExportDropdown: true,
  'el-alert': true, 'el-button': true, 'el-card': true, 'el-dropdown': true, 'el-dropdown-item': true,
  'el-dropdown-menu': true, 'el-empty': true, 'el-icon': true, 'el-input': true, 'el-input-number': true,
  'el-option': true, 'el-select': true, 'el-table': true, 'el-table-column': true, 'el-tag': true,
}
async function mountCase(c: Case, rows: unknown[]) {
  const comp = (await c.load()).default
  const allResponses = new Map<string, any>([[c.itemId, { item_id: c.itemId, conclusion: null, remark: JSON.stringify(rows) }]])
  const w = mount(comp, {
    props: { wpId: 'wp-k', projectId: 'p-k', allResponses, isReadonly: false },
    global: { stubs, provide: { openReviewDialog: () => {} } },
  })
  await flushPromises()
  return w
}
function lastSaved(w: any, itemId: string): any[] {
  const saves = (w.emitted('save') ?? []).filter((args: any[]) => args[0] === itemId)
  expect(saves.length, `${itemId} 没有保存`).toBeGreaterThan(0)
  return JSON.parse(saves[saves.length - 1][1].remark)
}

describe.each(CASES)('$cycle 分录行：载入 / 改类型 / 新行', (c) => {
  beforeEach(() => { vi.clearAllMocks() })
  it('载入保留未知键与模板四列，类别缺键按类型给缺省，空串照留', async () => {
    const w = await mountCase(c, [
      { id: 'e1', entryType: 'RJE', summary: '重分类', accountName: '甲', [c.debitKey]: 100, reportItem: '报表甲',
        noteItem: '附注乙', indexRef: 'K-1', remark: '备', placeholder: 'OO 侧填的' },
      { id: 'e2', entryType: 'AJE', summary: '调账', category: '', [c.creditKey]: 100 },
    ])
    const vm = w.vm as any
    expect(vm.entries[0]).toMatchObject({
      category: '报表调整', reportItem: '报表甲', noteItem: '附注乙', indexRef: 'K-1', remark: '备',
      placeholder: 'OO 侧填的', [c.debitKey]: 100,
    })
    expect(vm.entries[1].category).toBe('')
  })
  it('改类型：类别是旧缺省值就跟着换，用户改过的不动；保存带上未知键', async () => {
    const w = await mountCase(c, [{ id: 'e1', entryType: 'RJE', summary: '重分类', placeholder: 'OO 侧填的' }])
    const vm = w.vm as any
    vm.updateCell('e1', 'entryType', 'AJE')
    expect(vm.entries[0].category).toBe('账项调整')
    vm.updateCell('e1', 'category', '其他')
    vm.updateCell('e1', 'entryType', 'RJE')
    expect(vm.entries[0].category).toBe('其他')
    expect(lastSaved(w, c.itemId)[0]).toMatchObject({ entryType: 'RJE', category: '其他', placeholder: 'OO 侧填的' })
  })
  it('新增分录带 类别（按类型缺省）/ 报表项目 / 附注项目 / 索引', async () => {
    const w = await mountCase(c, [])
    await (w.vm as any).handleAddEntry()
    await flushPromises()
    const saved = lastSaved(w, c.itemId)
    expect(saved).toHaveLength(1)
    expect(saved[0]).toMatchObject({ category: '账项调整', reportItem: c.newReportItem, noteItem: '', indexRef: '' })
  })
})

describe('K2 分录行（借方科目 / 贷方科目分列，与模板单科目行不同构，R2 待裁）', () => {
  it('载入保留本表不显示的模板列，下一次保存不擦掉', async () => {
    const k2: Case = { ...CASES[0], cycle: 'K2', itemId: 'K2-3-adj-entries', load: () => import('../k2/core/K2TabAdjustment.vue') }
    const oo = { category: '账项调整', reportItem: '其他流动资产', accountName: '待摊费用', noteItem: '附注甲', indexRef: 'K2-5', remark: '备', placeholder: 'OO 侧填的' }
    const w = await mountCase(k2, [{ id: 'e1', entryType: 'AJE', summary: '摊销', debitAccount: '销售费用', debitAmount: 10, ...oo }])
    ;(w.vm as any).updateCell('e1', 'summary', '摊销调整')
    expect(lastSaved(w, 'K2-3-adj-entries')[0]).toMatchObject({ summary: '摊销调整', debitAccount: '销售费用', ...oo })
  })
})

describe.each(CASES.filter((c) => c.cycle === 'K5' || c.cycle === 'K6'))('$cycle 合计行', (c) => {
  it('借贷合计按列 prop 落在「借方调整金额」「贷方调整金额」下，其余列空', async () => {
    const chunks = columnChunks(c.vue)
    const columns = chunks.map((ch) => ({ property: propOf(ch) }))
    const labels = chunks.map(labelOf)
    const w = await mountCase(c, [
      { id: 'e1', entryType: 'AJE', summary: '甲', [c.debitKey]: 100 },
      { id: 'e2', entryType: 'AJE', summary: '乙', [c.debitKey]: 50, [c.creditKey]: 150 },
    ])
    const vm = w.vm as any
    const out: string[] = vm.getSummary({ columns, data: vm.entries })
    const at = (label: string) => out[labels.indexOf(label)]
    expect(out[0]).toBe('合计')
    expect(at('借方调整金额')).toBe('150.00')
    expect(at('贷方调整金额')).toBe('150.00')
    const others = out.filter((_, i) => i > 0 && !['借方调整金额', '贷方调整金额'].includes(labels[i]))
    expect(others.every((v) => v === '')).toBe(true)
  })
})
