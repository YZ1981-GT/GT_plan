/**
 * formulaBarSourceRefs.spec.ts — 公式栏取数弹窗插入的引用写法（spec formula-governance-coverage-closure R6）
 *
 * 地址库的附注 / 报表条目自带登记好的引用写法（formula_ref）：
 *  - NOTE 第一参是附注章节编号（如「八、1」），列名是附注表头（如「期末余额」）——
 *    原先拿地址标签（「附注 > 货币资金 > …」）当章节、写死「期末」，插入的公式保存即判悬空、求值取不到数；
 *  - REPORT 按「行次 × 期间」逐条登记（资产负债表 期末 / 期初，利润表 本期 / 上期），直接用登记写法；
 *  - ROW / SUM_ROW 只取本期，按行次去重。
 * 宿主页没加载地址库时先按本项目 + 年度 + 模板加载；旧端点回退改用真实的附注目录接口（原写的 /tree 不存在）。
 * 另外，FormulaBar 的每个挂载点都必须显式声明执行器（缺省按底稿求值器门控，放在附注编辑器里就会放行附注执行器不认的函数）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { parse } from '@vue/compiler-sfc'

if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

const NOTE_ENTRIES = [
  { note_section: '八、1', label: '附注 > 货币资金 > 货币资金 > 合计 > 期末余额', formula_ref: "NOTE('八、1','合计','期末余额')" },
]
const { store, apiGet } = vi.hoisted(() => ({
  store: {
    loaded: true,
    tbAddresses: [] as any[],
    reportAddresses: [
      { row_code: 'BS-002', label: '资产负债表 > 货币资金 > 期末', formula_ref: "REPORT('BS-002','期末')" },
      { row_code: 'BS-002', label: '资产负债表 > 货币资金 > 期初', formula_ref: "REPORT('BS-002','期初')" },
      { row_code: 'IS-001', label: '利润表 > 营业收入 > 本期', formula_ref: "REPORT('IS-001','本期')" },
    ],
    noteAddresses: [] as any[],
    refresh: undefined as any,
  },
  apiGet: vi.fn(),
}))

vi.mock('@/stores/addressRegistry', () => ({ useAddressRegistry: () => store }))
vi.mock('@/services/acnr/useAcnr', () => ({ useAcnr: () => ({}) }))
vi.mock('@/services/apiProxy', () => ({ api: { get: apiGet, post: vi.fn() } }))

import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import FormulaBar from '../FormulaBar.vue'

const CELL = {
  cell: 'B5', address: '表!B5', value: null, formula: null, formula_type: null, formula_desc: null,
  fetch_rule_id: null, merge: null, is_merged: false,
}

async function rowsFor(fn: string, extra: Record<string, unknown> = {}): Promise<any[]> {
  const w = mount(FormulaBar, {
    props: { visible: true, cellInfo: CELL, projectId: 'p1', executor: 'note_executor', ...extra },
    global: { plugins: [ElementPlus, createPinia()] },
  })
  await (w.vm as any).pickSource(fn)
  await flushPromises()
  return (w.vm as any).sourceRows
}

beforeEach(() => {
  store.loaded = true
  store.noteAddresses = [...NOTE_ENTRIES]
  store.refresh = undefined
  apiGet.mockReset()
  apiGet.mockResolvedValue([])
})

describe('公式栏取数弹窗的引用写法', () => {
  it('NOTE 用地址库登记的写法：章节编号 + 附注表头列名', async () => {
    expect((await rowsFor('NOTE')).map((r) => r._ref)).toEqual(["NOTE('八、1','合计','期末余额')"])
  })

  it('REPORT 按期间逐条用登记写法；ROW / SUM_ROW 按行次去重只取本期', async () => {
    expect((await rowsFor('REPORT')).map((r) => r._ref)).toEqual([
      "REPORT('BS-002','期末')", "REPORT('BS-002','期初')", "REPORT('IS-001','本期')",
    ])
    expect((await rowsFor('ROW', { executor: 'wp_evaluator' })).map((r) => r._ref)).toEqual(["ROW('BS-002')", "ROW('IS-001')"])
  })

  it('宿主没加载地址库时先按本项目 + 年度 + 模板加载', async () => {
    store.loaded = false
    store.refresh = vi.fn(async () => { store.loaded = true })
    const rows = await rowsFor('NOTE', { year: 2025, templateType: 'listed' })
    expect(store.refresh).toHaveBeenCalledWith('p1', 2025, 'listed')
    expect(rows.map((r) => r._ref)).toEqual(["NOTE('八、1','合计','期末余额')"])
  })

  it('地址库加载不到时回退附注目录接口，章节用编号', async () => {
    store.loaded = false
    store.refresh = vi.fn(async () => {})
    apiGet.mockResolvedValue([{ note_section: '五、1', section_title: '货币资金' }])
    const rows = await rowsFor('NOTE', { year: 2025 })
    expect(apiGet.mock.calls.map((c) => c[0])).toEqual(['/api/disclosure-notes/p1/2025'])
    expect(rows.map((r) => r._ref)).toEqual(["NOTE('五、1','合计','期末余额')"])
  })
})

// ── 每个 FormulaBar 挂载点显式声明执行器 ───────────────────────────────────────

const SRC = resolve(__dirname, '../../..')

function vueFiles(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name !== 'node_modules' && name !== '__tests__') out.push(...vueFiles(p))
    } else if (name.endsWith('.vue')) {
      out.push(p)
    }
  }
  return out
}

function formulaBarMounts(): Array<{ file: string; executor: string | null; bound: string[] }> {
  const found: Array<{ file: string; executor: string | null; bound: string[] }> = []
  const walk = (node: any, file: string) => {
    if (node?.type === 1 && (node.tag === 'FormulaBar' || node.tag === 'formula-bar')) {
      const attr = (node.props || []).find((p: any) => p.type === 6 && p.name === 'executor')
      const bound = (node.props || []).find((p: any) => p.type === 7 && p.arg?.content === 'executor')
      const boundNames = (node.props || []).filter((p: any) => p.type === 7 && p.name === 'bind').map((p: any) => p.arg?.content)
      found.push({ file, executor: attr ? attr.value?.content ?? '' : bound ? `:${bound.exp?.content}` : null, bound: boundNames })
    }
    for (const child of node?.children || []) walk(child, file)
  }
  for (const file of vueFiles(SRC)) {
    const text = readFileSync(file, 'utf-8')
    if (!text.includes('FormulaBar') && !text.includes('formula-bar')) continue
    const ast = parse(text).descriptor.template?.ast
    if (ast) walk(ast, relative(SRC, file).replace(/\\/g, '/'))
  }
  return found
}

describe('FormulaBar 挂载点', () => {
  it('每个挂载点都显式传 executor；附注结构编辑器按附注执行器门控', () => {
    const mounts = formulaBarMounts()
    expect(mounts.length).toBeGreaterThan(0) // 防空转
    for (const m of mounts) expect(m.executor, `${m.file} 的 FormulaBar 未声明执行器`).toBeTruthy()
    const se = mounts.find((m) => m.file === 'components/formula/StructureEditor.vue')
    expect(se?.executor).toBe('note_executor')
    // 地址库按项目 + 年度 + 模板加载：结构编辑器把三者都传下去
    expect(se?.bound).toEqual(expect.arrayContaining(['project-id', 'year', 'template-type']))
  })
})
