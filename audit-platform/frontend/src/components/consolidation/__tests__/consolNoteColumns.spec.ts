/**
 * 数据节点只读面板的附注列树（spec consol-autotree-linkage-closure R6）：任意层表头，与单体附注编辑器列树同一读法。
 *
 * - 三层 multi_header 中间层不丢；树形 / 平铺 _column_groups、columns[].group 都认；平表头里的「/」是字面；
 * - 四份附注模板（单体 / 合并 × 国企 / 上市）全部表格：每列恰好一个叶子、表头格子铺满表头区不重叠；
 * - 编辑器列树（views/composables/noteColumnTree.ts）存在时逐表对拍；它入库前该组跳过、入库后自动生效。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { buildColumnTree, columnDepth, columnLeaves, columnPaths, type NoteColNode } from '../composables/consolNoteColumns'
import { headerRows } from '../composables/consolEntityView'

// 国企 八、5「按坏账准备计提方法分类」底稿 / Word 同形：期间 / 账面余额·坏账准备 / 金额·比例
const THREE_LEVEL = {
  headers: ['类别', '金额', '比例(%)', '金额', '预期信用损失率(%)', '账面价值', '金额', '比例(%)', '金额', '预期信用损失率(%)', '账面价值'],
  multi_header: [
    ['类别', '期末数', '', '', '', '', '期初数', '', '', '', ''],
    ['', '账面余额', '', '坏账准备', '', '账面价值', '账面余额', '', '坏账准备', '', '账面价值'],
    ['', '金额', '比例(%)', '金额', '预期信用损失率(%)', '', '金额', '比例(%)', '金额', '预期信用损失率(%)', ''],
  ],
}

const TREE_GROUPS = {
  headers: ['项目', 'a', 'b', 'c'],
  multi_header: [['项目', '本期增减', '', '期末'], ['', '增加', '减少', '']],
  _column_groups: [{ group: '本期增减', children: [{ group: '', start: 1, span: 2 }] }],
}

const COLUMN_GROUPS = {
  headers: ['类别', '期末余额/账面余额/金额', '比例', '金额'],
  columns: [
    { key: 'label', label: '类别', is_label: true },
    { key: 'a', label: '金额', group: '期末余额/账面余额' },
    { key: 'b', label: '比例', group: '期末余额/账面余额' },
    { key: 'c', label: '金额', group: '期末余额/坏账准备' },
  ],
}

const SLASH_FLAT = { headers: ['项目', '递延所得税资产/负债', '转回或收回前累计<br/>已计提坏账准备金额'] }

const SPLIT_GROUPS = {
  headers: ['项目', 'x', 'y', 'z'],
  _column_groups: [{ group: 'A', start: 1, span: 1 }, { group: 'B', start: 2, span: 1 }, { group: 'A', start: 3, span: 1 }],
}

const TEMPLATE_FILES = [
  'note_template_soe.json',
  'note_template_listed.json',
  'consol_note_sections_soe.json',
  'consol_note_sections_listed.json',
]

/** 模板里所有带 headers 的表格（含嵌套子表） */
function templateTables(): Array<{ file: string; table: any }> {
  const out: Array<{ file: string; table: any }> = []
  const walk = (file: string, obj: unknown) => {
    if (Array.isArray(obj)) { obj.forEach((v) => walk(file, v)); return }
    if (!obj || typeof obj !== 'object') return
    const rec = obj as Record<string, unknown>
    if (Array.isArray(rec.headers) && rec.headers.length) out.push({ file, table: rec })
    Object.values(rec).forEach((v) => walk(file, v))
  }
  for (const file of TEMPLATE_FILES) {
    walk(file, JSON.parse(readFileSync(resolve(process.cwd(), `../../backend/data/${file}`), 'utf8')))
  }
  return out
}

/** 按 HTML 表格的排布规则把表头格子放进 depth × width 的网格：越界 / 重叠 / 没铺满都算错 */
function headerCoverageError(nodes: NoteColNode[], width: number): string | null {
  const rows = headerRows(nodes)
  const depth = columnDepth(nodes)
  if (rows.length !== depth) return `表头行数 ${rows.length} ≠ 列树层数 ${depth}`
  const grid: boolean[][] = Array.from({ length: depth }, () => Array(width).fill(false))
  for (let r = 0; r < depth; r++) {
    let c = 0
    for (const cell of rows[r]) {
      while (c < width && grid[r][c]) c++
      if (c + cell.colspan > width || r + cell.rowspan > depth) return `第 ${r + 1} 行「${cell.label}」越界`
      for (let rr = r; rr < r + cell.rowspan; rr++) {
        for (let cc = c; cc < c + cell.colspan; cc++) {
          if (grid[rr][cc]) return `第 ${r + 1} 行「${cell.label}」与其他格子重叠`
          grid[rr][cc] = true
        }
      }
      c += cell.colspan
    }
  }
  return grid.every((row) => row.every(Boolean)) ? null : '表头区没有铺满'
}

describe('consolNoteColumns 列树', () => {
  it('三层 multi_header：中间层不丢，每个叶子都在', () => {
    const tree = buildColumnTree(THREE_LEVEL)
    expect(tree.map((n) => n.label)).toEqual(['类别', '期末数', '期初数'])
    expect(tree[1].children!.map((n) => n.label)).toEqual(['账面余额', '坏账准备', '账面价值'])
    expect(tree[1].children![0].children).toEqual([{ label: '金额', headerIdx: 1 }, { label: '比例(%)', headerIdx: 2 }])
    expect(tree[1].children![2]).toEqual({ label: '账面价值', headerIdx: 5 })
    expect(columnLeaves(tree).map((n) => n.headerIdx)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(columnDepth(tree)).toBe(3)
    // 跨两行的「账面价值」叶子跨到最底行；「类别」跨三行
    const rows = headerRows(tree)
    expect(rows[0][0]).toEqual({ label: '类别', colspan: 1, rowspan: 3 })
    expect(rows[1].find((c) => c.label === '账面价值')).toEqual({ label: '账面价值', colspan: 1, rowspan: 2 })
  })

  it('树形 / 平铺 / 列号 _column_groups 都认；两行 multi_header 时叶子名取末行', () => {
    expect(buildColumnTree(TREE_GROUPS)).toEqual([
      { label: '项目', headerIdx: 0 },
      { label: '本期增减', children: [{ label: '增加', headerIdx: 1 }, { label: '减少', headerIdx: 2 }] },
      { label: 'c', headerIdx: 3 },
    ])
    expect(columnPaths({ headers: ['项目', 'a', 'b'], _column_groups: [{ group: '本期', columns: [1, 2] }] }))
      .toEqual([['项目'], ['本期', 'a'], ['本期', 'b']])
    expect(columnPaths({ headers: ['项目', 'a'], _column_groups: [{ group: '本期', headerIdx: 1 }] })).toEqual([['项目'], ['本期', 'a']])
    // 平铺分组：叶子名去掉「分组/」前缀；列名与分组同名时不重复成两层
    expect(columnPaths({ headers: ['项目', '本期/金额', '期末'], _column_groups: [{ group: '本期', start: 1, span: 1 }, { group: '期末', start: 2, span: 1 }] }))
      .toEqual([['项目'], ['本期', '金额'], ['期末']])
  })

  it('columns[].group（同步来的披露表）按「/」拆层；叶子去掉重复的分组前缀', () => {
    expect(buildColumnTree(COLUMN_GROUPS)[1]).toEqual({ label: '期末余额', children: [
      { label: '账面余额', children: [{ label: '金额', headerIdx: 1 }, { label: '比例', headerIdx: 2 }] },
      { label: '坏账准备', children: [{ label: '金额', headerIdx: 3 }] },
    ] })
  })

  it('平表头里的「/」是字面，不拆；<br/> 换行标记去掉', () => {
    expect(buildColumnTree(SLASH_FLAT)).toEqual([
      { label: '项目', headerIdx: 0 },
      { label: '递延所得税资产/负债', headerIdx: 1 },
      { label: '转回或收回前累计已计提坏账准备金额', headerIdx: 2 },
    ])
  })

  it('不相邻的同名分组各自成组；没有表头 ⇒ 空', () => {
    expect(columnPaths(SPLIT_GROUPS)).toEqual([['项目'], ['A', 'x'], ['B', 'y'], ['A', 'z']])
    expect(buildColumnTree(SPLIT_GROUPS).map((n) => n.label)).toEqual(['项目', 'A', 'B', 'A'])
    expect(buildColumnTree({ headers: [] })).toEqual([])
    expect(headerRows([])).toEqual([])
  })

  it('四份附注模板全部表格：每列恰好一个叶子（自左而右）、表头格子铺满表头区不重叠', () => {
    const tables = templateTables()
    expect(tables.length).toBeGreaterThan(1000)
    const bad: string[] = []
    for (const { file, table } of tables) {
      const tree = buildColumnTree(table)
      const width = table.headers.length
      const leaves = columnLeaves(tree).map((n) => n.headerIdx)
      if (JSON.stringify(leaves) !== JSON.stringify(Array.from({ length: width }, (_v, i) => i))) {
        bad.push(`${file} ${table.name ?? table.section_id ?? ''}：叶子 ${JSON.stringify(leaves)}`)
        continue
      }
      const err = headerCoverageError(tree, width)
      if (err) bad.push(`${file} ${table.name ?? table.section_id ?? ''}：${err}`)
    }
    expect(bad).toEqual([])
  })
})

// 编辑器列树（另一份 spec 的产物）存在时才对拍；不存在时整组跳过（不是通过）
const editorModules = import.meta.glob('../../../views/composables/noteColumnTree.ts', { eager: true }) as Record<
  string,
  { buildNoteColumnTree?: (table: unknown) => NoteColNode[] }
>
const editorBuild = Object.values(editorModules)[0]?.buildNoteColumnTree

describe.skipIf(!editorBuild)('parity：与单体附注编辑器列树对拍（noteColumnTree.ts 存在时）', () => {
  it('样例表与四份模板全部表格逐表一致；不一致 ⇒ 编辑器列树已改读法，这里应改为直接复用它', () => {
    const samples = [THREE_LEVEL, TREE_GROUPS, COLUMN_GROUPS, SLASH_FLAT, SPLIT_GROUPS, { headers: [] }]
    const all = [...samples, ...templateTables().map((t) => t.table)]
    const diff = all.filter((table) => JSON.stringify(buildColumnTree(table)) !== JSON.stringify(editorBuild!(table)))
    expect(diff.map((t: any) => t.name ?? t.section_id ?? JSON.stringify(t.headers))).toEqual([])
  })
})
