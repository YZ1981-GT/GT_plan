/**
 * acnrDisplaySingleSource.spec.ts — 前端显示统一到目录 display_label（spec acnr-foundation-defect-closure T30，
 * 需求 12.1 / D10，design §13.2~13.3；含 RV7-02 停用 cell 同口径过滤）
 *
 * 一、守卫（TS 编译器 API 解析 `.ts` 与 `.vue` 的 `<script>`，`@vue/compiler-sfc` 取模板表达式再交 TS 解析）：
 *   - 登记文件里对 `.sheet_name` / `.semantic_label` / `.mapped_sheet_name` / `.account_name` 的属性读取（类型声明除外）
 *     必须逐处登记在 NON_DISPLAY_READS（试算表科目名、底稿公式行的 sheet_name 身份字段、目录身份匹配等，不拼 ACNR 显示名），
 *     多出一处（如某组件改回读 sheet_name 拼显示名）即红；登记了却已不存在也红（失效条目）。
 *     design §13.3 原写「登记文件中不出现这些读取」——这些文件里还有与 ACNR 显示无关的同名字段（试算表行的 account_name、
 *     底稿公式保存体的 sheet_name），一律禁止会误伤，故改为逐处登记（白名单，只许删）。`.account_name` 只在
 *     `sheetDisplayName.groupHeaderLabel` 读目录条目。
 *   - 全仓（非测试源码）不再有 `composeSheetLabelsForGroup` / `cleanSheetLabelName` 标识符。
 * 二、渲染（夹具 = 后端 `backend/tests/acnr/fixtures/display_contract.json`，与后端契约同一份）：地址树、公式选址器、
 *   取值结果区、索引 chip 的文本逐字包含夹具的 display_label / cell_label；T30 拍板规则 B 的 20 张不带序号；
 *   公式管理树（先滤掉编码等于底稿编码的 sheet）里 10 张非父级 sheet 的名字与 T29 时相同。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import ts from 'typescript'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'

if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

const SRC = resolve(__dirname)
const FIXTURE = JSON.parse(
  readFileSync(resolve(__dirname, '../../../backend/tests/acnr/fixtures/display_contract.json'), 'utf-8'),
) as {
  sheets: Array<{ addr_id: string; display_label: string; deprecated: boolean }>
  cells: Array<{ addr_id: string; cell_label: string; display_label: string; deprecated: boolean }>
  rule_b: Array<{ addr_id: string; is_parent_code: boolean; display_label: string; formula_manager_tree_label_t29?: string }>
}

// ─── mocks（渲染部分用；守卫部分只读源码）────────────────────────────────────
const { mockGet, mockBatch } = vi.hoisted(() => ({ mockGet: vi.fn(), mockBatch: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: (...a: unknown[]) => mockGet(...a), post: vi.fn() } }))
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: () => ({ close: () => {} }),
  isProjectStreamDegraded: () => false,
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p1' }, path: '/projects/p1/x', query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/services/acnr', () => ({
  useAcnr: () => ({ resolveIndexBatched: (...a: unknown[]) => mockBatch(...a), resolveInstance: vi.fn() }),
}))

// ─── 一、守卫 ────────────────────────────────────────────────────────────────

/** design §13.3 登记的 12 个文件（相对 src）。 */
const REGISTERED = [
  'services/acnr/sheetDisplayName.ts',
  'services/acnr/useAcnr.ts',
  'components/formula/FormulaManagerDialog.vue',
  'components/formula/FormulaEditDialog.vue',
  'components/formula/FormulaRefPicker.vue',
  'components/formula/CellSelector.vue',
  'components/formula/FormulaBar.vue',
  'components/formula/leftPanelAnchors.ts',
  'stores/addressRegistry.ts',
  'components/custom-query/CustomQueryFieldPicker.vue',
  'components/workpaper/GtIndexChip.vue',
  'components/custom-query/AcnrTargetResults.vue',
]
const WATCHED = new Set(['sheet_name', 'semantic_label', 'mapped_sheet_name', 'account_name'])

interface Read { file: string; owner: string; receiver: string; prop: string }
interface Allowed extends Read { count: number; reason: string }

/** 与 ACNR 显示名无关的同名字段读取（逐处登记，只许删）。owner = 所在顶层声明名（模板为 <template>）。 */
const NON_DISPLAY_READS: Allowed[] = [
  { file: 'services/acnr/sheetDisplayName.ts', owner: 'groupHeaderLabel', receiver: 'group.find((s) => s.account_name)', prop: 'account_name', count: 1, reason: '树父节点标题「{父级码} {科目简称}」（design §13.2 留在前端的唯一一处）' },
  { file: 'services/acnr/sheetDisplayName.ts', owner: 'groupHeaderLabel', receiver: 's', prop: 'account_name', count: 1, reason: '同上，找组内首个有简称的 sheet' },
  { file: 'components/formula/FormulaManagerDialog.vue', owner: 'matchesWpExtractionSheet', receiver: 'row', prop: 'sheet_name', count: 1, reason: '底稿公式行的结构身份字段（是否有 sheet_name 决定按身份匹配），不是显示' },
  { file: 'components/formula/FormulaManagerDialog.vue', owner: 'matchesSheetIdentity', receiver: 's', prop: 'sheet_name', count: 1, reason: '按目录 sheet_name 与别名做身份等值匹配，不是显示' },
  { file: 'components/formula/FormulaManagerDialog.vue', owner: 'loadWpFormulas', receiver: 'it', prop: 'sheet_name', count: 3, reason: '底稿公式（wp_formula）条目自带的 sheet_name，保存回源字段' },
  { file: 'components/formula/FormulaManagerDialog.vue', owner: 'currentRows', receiver: 'r', prop: 'account_name', count: 1, reason: '试算表行的科目名称' },
  { file: 'components/formula/FormulaManagerDialog.vue', owner: 'paramPickerTbItems', receiver: 'a', prop: 'account_name', count: 1, reason: '试算表地址的科目名称' },
  { file: 'components/formula/FormulaManagerDialog.vue', owner: 'onFormulaEditSave', receiver: 'row', prop: 'sheet_name', count: 1, reason: '底稿公式保存请求体 sheet_name（PUT /workpapers/{wp_id}/formulas 必填）' },
  { file: 'components/formula/FormulaManagerDialog.vue', owner: 'onSaveAllFormulas', receiver: 'row', prop: 'sheet_name', count: 1, reason: '同上（批量保存）' },
  { file: 'components/formula/FormulaEditDialog.vue', owner: 'openSourceBrowserForTB', receiver: 'r', prop: 'account_name', count: 1, reason: '试算表行的科目名称' },
  { file: 'components/formula/FormulaRefPicker.vue', owner: 'filteredTbRows', receiver: 'r', prop: 'account_name', count: 1, reason: '试算表行的科目名称（搜索）' },
  { file: 'components/formula/FormulaRefPicker.vue', owner: 'onSelectTb', receiver: 'row', prop: 'account_name', count: 1, reason: '试算表行的科目名称（插入标签）' },
  { file: 'components/formula/FormulaRefPicker.vue', owner: '<template>', receiver: 'row', prop: 'account_name', count: 1, reason: '试算表页签「科目名称」列' },
  { file: 'components/formula/CellSelector.vue', owner: 'filteredTbData', receiver: 'r', prop: 'account_name', count: 1, reason: '试算表行的科目名称（搜索）' },
  { file: 'components/formula/CellSelector.vue', owner: 'selectTbCell', receiver: 'row', prop: 'account_name', count: 1, reason: '试算表行的科目名称' },
  { file: 'components/formula/FormulaBar.vue', owner: 'loadTbRows', receiver: 'r', prop: 'account_name', count: 1, reason: '试算表行的科目名称' },
  { file: 'components/formula/leftPanelAnchors.ts', owner: 'buildCurrentSheetAnchorNodes', receiver: 'c', prop: 'semantic_label', count: 1, reason: '节点元信息 _semanticLabel 原样透传，显示用 cell_label' },
]

function ownerOf(node: ts.Node, sf: ts.SourceFile): string {
  let n: ts.Node = node
  while (n.parent && n.parent !== sf) n = n.parent
  if (ts.isFunctionDeclaration(n) && n.name) return n.name.text
  if (ts.isVariableStatement(n)) {
    const d = n.declarationList.declarations[0]
    if (d && ts.isIdentifier(d.name)) return d.name.text
  }
  return '<top>'
}

function inType(node: ts.Node): boolean {
  for (let p = node.parent; p; p = p.parent) if (ts.isTypeNode(p)) return true
  return false
}

function collectReads(file: string, code: string, owner: string | null, out: Read[]): void {
  const sf = ts.createSourceFile('x.ts', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const visit = (n: ts.Node) => {
    if (ts.isPropertyAccessExpression(n) && WATCHED.has(n.name.text) && !inType(n)) {
      out.push({ file, owner: owner ?? ownerOf(n, sf), receiver: n.expression.getText(sf).replace(/\s+/g, ' '), prop: n.name.text })
    }
    ts.forEachChild(n, visit)
  }
  visit(sf)
}

function templateExpressions(ast: any): string[] {
  const out: string[] = []
  const rec = (n: any) => {
    if (n.type === 5 && n.content?.content) out.push(n.content.content)
    for (const p of n.props || []) if (p.type === 7 && p.exp?.content) out.push(p.exp.content)
    for (const c of n.children || []) rec(c)
    for (const b of n.branches || []) rec(b)
  }
  rec(ast)
  return out
}

/** 解析一份源码（.ts 全文；.vue 的两个 script 块 + 模板表达式）。 */
export function scanSource(file: string, text: string): Read[] {
  const out: Read[] = []
  if (file.endsWith('.vue')) {
    const { descriptor } = parseSfc(text)
    for (const b of [descriptor.script, descriptor.scriptSetup]) if (b?.content) collectReads(file, b.content, null, out)
    if (descriptor.template?.ast) for (const e of templateExpressions(descriptor.template.ast)) collectReads(file, `(${e})`, '<template>', out)
  } else {
    collectReads(file, text, null, out)
  }
  return out
}

const keyOf = (r: Read) => `${r.file}|${r.owner}|${r.receiver}|${r.prop}`

function isTestPath(posix: string): boolean {
  return posix.endsWith('.spec.ts') || posix.endsWith('.test.ts') || posix.includes('/__tests__/') || posix.includes('/tests/')
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name !== 'node_modules') walk(p, out)
    } else if (name.endsWith('.ts') || name.endsWith('.vue')) out.push(p)
  }
  return out
}

function identifiersIn(code: string): Set<string> {
  const sf = ts.createSourceFile('x.ts', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const ids = new Set<string>()
  const visit = (n: ts.Node) => {
    if (ts.isIdentifier(n)) ids.add(n.text)
    ts.forEachChild(n, visit)
  }
  visit(sf)
  return ids
}

describe('守卫：显示名只读目录 display_label（T30）', () => {
  const reads = REGISTERED.flatMap((f) => scanSource(f, readFileSync(join(SRC, f), 'utf-8')))

  it('登记文件里的同名字段读取与 NON_DISPLAY_READS 逐处一致（多出即红、失效即红）', () => {
    const got = new Map<string, number>()
    for (const r of reads) got.set(keyOf(r), (got.get(keyOf(r)) || 0) + 1)
    const allowed = new Map(NON_DISPLAY_READS.map((a) => [keyOf(a), a.count]))
    const extra = [...got].filter(([k, n]) => n > (allowed.get(k) || 0)).map(([k, n]) => `${k} ×${n}`)
    const stale = [...allowed].filter(([k, n]) => (got.get(k) || 0) < n).map(([k, n]) => `${k} 登记 ×${n}、现有 ×${got.get(k) || 0}`)
    expect(extra, `未登记的显示字段读取（应改读 display_label / cell_label）：\n${extra.join('\n')}`).toEqual([])
    expect(stale, `登记失效：\n${stale.join('\n')}`).toEqual([])
  })

  it('.account_name 读目录条目只在 groupHeaderLabel；其余登记理由都不是 ACNR 显示', () => {
    for (const a of NON_DISPLAY_READS) {
      expect(a.reason.length).toBeGreaterThan(4)
      if (a.file === 'services/acnr/sheetDisplayName.ts') expect(a.owner).toBe('groupHeaderLabel')
    }
  })

  it('全仓非测试源码不再有 composeSheetLabelsForGroup / cleanSheetLabelName', () => {
    const hits: string[] = []
    for (const abs of walk(SRC)) {
      const posix = relative(SRC, abs).replace(/\\/g, '/')
      if (isTestPath(posix)) continue
      const text = readFileSync(abs, 'utf-8')
      if (!text.includes('composeSheetLabelsForGroup') && !text.includes('cleanSheetLabelName')) continue
      const codes = posix.endsWith('.vue')
        ? [parseSfc(text).descriptor.script?.content || '', parseSfc(text).descriptor.scriptSetup?.content || '']
        : [text]
      for (const c of codes) {
        const ids = identifiersIn(c)
        for (const name of ['composeSheetLabelsForGroup', 'cleanSheetLabelName']) if (ids.has(name)) hits.push(`${posix}: ${name}`)
      }
    }
    expect(hits).toEqual([])
  })

  it('扫描器自检（防空转）：脚本与模板里的读取都能抓到，类型声明不算', () => {
    const vue = '<template><span>{{ s.sheet_name }}</span><x :label="c.semantic_label" /></template>\n' +
      '<script setup lang="ts">\nconst f = (e: { mapped_sheet_name: string }) => e.mapped_sheet_name\ntype T = X["account_name"]\n</script>'
    const got = scanSource('x.vue', vue).map((r) => `${r.owner}|${r.receiver}.${r.prop}`)
    expect(got.sort()).toEqual(['<template>|c.semantic_label', '<template>|s.sheet_name', 'f|e.mapped_sheet_name'])
    expect(reads.length).toBe(NON_DISPLAY_READS.reduce((n, a) => n + a.count, 0))
  })

  it('公式管理树与公式编辑树、地址树都经 sortSheetsForGroup / groupHeaderLabel 取名', () => {
    for (const f of ['components/formula/FormulaManagerDialog.vue', 'components/formula/FormulaEditDialog.vue', 'services/acnr/useAcnr.ts']) {
      const text = readFileSync(join(SRC, f), 'utf-8')
      const code = f.endsWith('.vue') ? parseSfc(text).descriptor.scriptSetup?.content || '' : text
      const ids = identifiersIn(code)
      expect(ids.has('sortSheetsForGroup') && ids.has('groupHeaderLabel'), f).toBe(true)
    }
  })
})

// ─── 二、渲染（display_contract 夹具）────────────────────────────────────────

const parentOf = (addrId: string) => addrId.split('/')[0]
const codeOf = (addrId: string) => addrId.split('/')[1]

function sheetEntry(addrId: string, display_label: string) {
  return { addr_id: addrId, domain: 'wp', cycle: addrId[0], parent_wp_code: parentOf(addrId), sheet_code: codeOf(addrId),
    sheet_name: '模板名（不应显示）', display_label }
}
const LIVE_SHEETS = [...FIXTURE.sheets.filter((s) => !s.deprecated), ...FIXTURE.rule_b]
/** cell 所属 sheet 的显示名取 cell display_label 的「 › 」前半段（与后端 display.cell_labels 同口径） */
const CELL_PARENT_SHEETS = [...new Map(FIXTURE.cells.map((c) => [c.addr_id.split('/').slice(0, 2).join('/'),
  c.display_label.split(' › ')[0]] as const))].map(([a, l]) => ({ addr_id: a, display_label: l }))
const SHEET_ROWS = [...LIVE_SHEETS, ...CELL_PARENT_SHEETS].map((s) => sheetEntry(s.addr_id, s.display_label))
const CELL_SHEET = FIXTURE.cells[0].addr_id.split('/').slice(0, 2).join('/')
function cellEntry(c: (typeof FIXTURE.cells)[number]) {
  const [p, s, a] = c.addr_id.split('/')
  return { addr_id: c.addr_id, parent_addr_id: `${p}/${s}`, domain: 'wp', cell_address: a, semantic_label: '语义（不应单独显示）',
    formula_ref: `WP('${p}','${s}','${a}')`, cell_label: c.cell_label, display_label: c.display_label, deprecated: c.deprecated }
}
const CELL_ROWS = FIXTURE.cells.map(cellEntry)

function routeGet(url: string, opts?: any) {
  if (url === '/api/acnr/entries') return Promise.resolve({ data: SHEET_ROWS })
  if (url === '/api/acnr/anchors') {
    const sheet = `${opts?.params?.wp_code}/${opts?.params?.sheet}`
    return Promise.resolve({ data: CELL_ROWS.filter((c) => c.parent_addr_id === sheet) })
  }
  // 其余（地址库整库加载等）：空库
  return Promise.resolve({ data: { items: [], total: 0, returned: 0, truncated: false, truncated_domains: [] } })
}

describe('渲染：显示文本逐字等于夹具（T30）', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockGet.mockImplementation(routeGet)
    mockBatch.mockReset()
  })

  it('夹具覆盖规则 B 20 张与同组序号样本（防空转）', () => {
    expect(FIXTURE.rule_b).toHaveLength(20)
    expect(FIXTURE.sheets.some((s) => /（\d）$/.test(s.display_label))).toBe(true)
    expect(FIXTURE.rule_b.every((s) => !/（\d）$/.test(s.display_label))).toBe(true)
  })

  it('地址树（选址器 / 高级查询选字段）：sheet 节点 = display_label；规则 B 的 D1 与 D1-1 都不带序号', async () => {
    const { useAcnr } = await import('@/services/acnr/useAcnr')
    const tree = await useAcnr().buildAddressTree()
    const labels = new Map(tree.flatMap((g) => (g.children || []).map((c) => [c.addrId, c.label] as const)))
    for (const s of LIVE_SHEETS) expect(labels.get(s.addr_id)).toBe(s.display_label)
    expect(labels.get('D1/D1')).toBe('D1 应收票据审定表')
    expect(labels.get('D1/D1-1')).toBe('D1-1 应收票据审定表')
  })

  it('公式管理树口径（滤掉编码等于底稿编码的 sheet 后排序）：10 张非父级 sheet 名字与 T29 时相同', async () => {
    const { sortSheetsForGroup } = await import('@/services/acnr/sheetDisplayName')
    const rows = SHEET_ROWS.filter((s) => FIXTURE.rule_b.some((b) => b.addr_id === s.addr_id) && s.sheet_code !== s.parent_wp_code)
    const got = Object.fromEntries(sortSheetsForGroup(rows).map(({ entry, label }) => [entry.addr_id, label]))
    const want = Object.fromEntries(FIXTURE.rule_b.filter((b) => !b.is_parent_code).map((b) => [b.addr_id, b.formula_manager_tree_label_t29]))
    expect(Object.keys(want)).toHaveLength(10)
    expect(got).toEqual(want)
  })

  it('地址树 cell 叶子 = cell_label，停用 cell 不列（RV7-02 同一谓词）', async () => {
    const { useAcnr } = await import('@/services/acnr/useAcnr')
    const sheet = SHEET_ROWS.find((s) => s.addr_id === CELL_SHEET) || sheetEntry(CELL_SHEET, '')
    const nodes = await useAcnr().loadCellNodes(sheet as never)
    const want = FIXTURE.cells.filter((c) => !c.deprecated && c.addr_id.startsWith(`${CELL_SHEET}/`))
    expect(nodes.map((n) => n.label)).toEqual(want.map((c) => c.cell_label))
  })

  it('公式选址器：sheet 下拉 = display_label；单元格列 = cell_label；停用 cell 不列；将插入标签 = display_label', async () => {
    const ElementPlus = (await import('element-plus')).default
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())
    const FormulaRefPicker = (await import('@/components/formula/FormulaRefPicker.vue')).default
    const ElTableStub = defineComponent({
      name: 'ElTable', props: { data: { type: Array, default: () => [] } }, emits: ['row-click'],
      template: '<div class="el-table-stub"><slot /></div>',
    })
    const ElSelectStub = defineComponent({
      name: 'ElSelect', props: { modelValue: { type: [String, Number], default: '' } }, emits: ['update:modelValue', 'change'],
      template: '<div class="el-select-stub"><slot /></div>',
    })
    const ElOptionStub = defineComponent({ name: 'ElOption', props: { label: String, value: String }, template: '<i class="opt">{{ label }}</i>' })
    const ElDialogStub = defineComponent({ name: 'ElDialog', template: '<div><slot /><slot name="footer" /></div>' })
    const wrapper = mount(FormulaRefPicker, {
      props: { modelValue: true, reportRows: [], tbRows: [], noteRows: [] },
      global: { plugins: [ElementPlus], stubs: { ElDialog: ElDialogStub, ElTable: ElTableStub, ElSelect: ElSelectStub, ElOption: ElOptionStub, ElTableColumn: true } },
    })
    const { ElTabs } = await import('element-plus')
    wrapper.findComponent(ElTabs).vm.$emit('update:modelValue', 'wp')
    await flushPromises()
    const opts = wrapper.findAll('i.opt').map((o) => o.text())
    for (const s of LIVE_SHEETS) expect(opts).toContain(s.display_label)
    const select = wrapper.findAllComponents(ElSelectStub).find((s) => (s.vm as any).$attrs.placeholder === '选择底稿 Sheet')!
    select.vm.$emit('update:modelValue', CELL_SHEET)
    select.vm.$emit('change', CELL_SHEET)
    await flushPromises()
    const table = wrapper.findAllComponents(ElTableStub).find((t) => ((t.props('data') as any[])[0] || {}).cell_label !== undefined)!
    const rows = table.props('data') as any[]
    const live = FIXTURE.cells.filter((c) => !c.deprecated && c.addr_id.startsWith(`${CELL_SHEET}/`))
    expect(rows.map((r) => r.cell_label)).toEqual(live.map((c) => c.cell_label))
    table.vm.$emit('row-click', rows[0])
    await nextTick()
    expect(wrapper.text()).toContain(`底稿 ${live[0].display_label}`)
    wrapper.unmount()
  })

  it('地址库搜索（底稿域走 ACNR）：sheet / cell 标签 = display_label，停用 cell 不列（RV7-02 同一谓词）', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    setActivePinia(createPinia())
    const { useAddressRegistry } = await import('@/stores/addressRegistry')
    const store = useAddressRegistry()
    await store.refresh('p1', 2025, 'soe')
    const results = await store.search('应付票据', 'wp')
    const byUri = new Map(results.map((r) => [r.uri, r.label]))
    const live = FIXTURE.cells.find((c) => c.addr_id === 'F3/F3-5/B25')!
    const dead = FIXTURE.cells.find((c) => c.addr_id === 'F3/F3-6/E30')!
    expect(dead.deprecated).toBe(true)
    expect(byUri.get(live.addr_id)).toBe(live.display_label)
    expect(byUri.has(dead.addr_id)).toBe(false)
    expect(byUri.get('F3/F3-1')).toBe('F3-1 应付票据审定表')
    store.dispose()
  })

  it('取值结果区显示 display_label', async () => {
    const ElementPlus = (await import('element-plus')).default
    const AcnrTargetResults = (await import('@/components/custom-query/AcnrTargetResults.vue')).default
    const live = FIXTURE.cells.filter((c) => !c.deprecated)
    const items = live.map((c) => ({ input: c.addr_id, addr_id: c.addr_id, display_label: c.display_label, formula_ref: null,
      state: 'ok', value: 1, text: null, reason: null }))
    const wrapper = mount(AcnrTargetResults, {
      props: { block: { items, catalog_version: 'v', project_id: 'p1', year: 2025 } as any, projectId: 'p1' },
      global: { plugins: [ElementPlus], stubs: { GtIndexChip: true } },
    })
    await flushPromises()
    for (const c of live) expect(wrapper.text()).toContain(c.display_label)
    wrapper.unmount()
  })

  it('索引 chip 提示首行 = 解析结果的 display_label', async () => {
    const GtIndexChip = (await import('@/components/workpaper/GtIndexChip.vue')).default
    const target = FIXTURE.rule_b.find((b) => b.addr_id === 'D1/D1-1')!
    mockBatch.mockResolvedValue({ found: true, addr_id: target.addr_id, display_label: target.display_label })
    const Tip = defineComponent({ name: 'ElTooltip', props: ['content', 'disabled', 'placement'], template: '<div class="tip" :data-content="content"><slot /></div>' })
    const wrapper = mount(GtIndexChip, {
      props: { value: 'D1-1', validate: true },
      global: { components: { 'el-tooltip': Tip, 'el-tag': { template: '<span><slot /></span>' } } },
    })
    await flushPromises()
    const content = String(wrapper.find('.tip').attributes('data-content') || '')
    expect(content.split('\n')[0]).toBe(target.display_label)
    wrapper.unmount()
  })
})
