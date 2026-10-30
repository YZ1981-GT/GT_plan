/**
 * 附注表格列树（spec note-pull-header-formula-closure R4 / F8）：任意层表头、与后端标题行库同一读法。
 * 原缺陷：`multi_header` 三层时中间层整组丢掉（列消失）；`columns[].group` 不认；平表头里的「/」被当层级拆。
 */
import { describe, expect, it } from 'vitest'
import { buildNoteColumnTree, noteColumnDepth, noteColumnLeaves, noteColumnPaths } from '../noteColumnTree'

// 国企 八、5「按坏账准备计提方法分类」底稿 / Word 同形：期间 / 账面余额·坏账准备 / 金额·比例
const THREE_LEVEL = {
  headers: ['类别', '金额', '比例(%)', '金额', '预期信用损失率(%)', '账面价值', '金额', '比例(%)', '金额', '预期信用损失率(%)', '账面价值'],
  multi_header: [
    ['类别', '期末数', '', '', '', '', '期初数', '', '', '', ''],
    ['', '账面余额', '', '坏账准备', '', '账面价值', '账面余额', '', '坏账准备', '', '账面价值'],
    ['', '金额', '比例(%)', '金额', '预期信用损失率(%)', '', '金额', '比例(%)', '金额', '预期信用损失率(%)', ''],
  ],
}

describe('noteColumnTree', () => {
  it('三层 multi_header：中间层不丢，每个叶子都在', () => {
    const tree = buildNoteColumnTree(THREE_LEVEL)
    expect(tree.map((n) => n.label)).toEqual(['类别', '期末数', '期初数'])
    expect(tree[1].children!.map((n) => n.label)).toEqual(['账面余额', '坏账准备', '账面价值'])
    expect(tree[1].children![0].children).toEqual([{ label: '金额', headerIdx: 1 }, { label: '比例(%)', headerIdx: 2 }])
    expect(tree[1].children![2], '跨两行的「账面价值」是叶子').toEqual({ label: '账面价值', headerIdx: 5 })
    expect(noteColumnLeaves(tree).map((n) => n.headerIdx)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(noteColumnDepth(tree)).toBe(3)
  })

  it('树形 / 平铺 _column_groups 都认；两行 multi_header 时叶子名取末行', () => {
    const table = {
      headers: ['项目', 'a', 'b', 'c'],
      multi_header: [['项目', '本期增减', '', '期末'], ['', '增加', '减少', '']],
      _column_groups: [{ group: '本期增减', children: [{ group: '', start: 1, span: 2 }] }],
    }
    expect(buildNoteColumnTree(table)).toEqual([
      { label: '项目', headerIdx: 0 },
      { label: '本期增减', children: [{ label: '增加', headerIdx: 1 }, { label: '减少', headerIdx: 2 }] },
      { label: 'c', headerIdx: 3 },
    ])
  })

  it('columns[].group（同步来的披露表）按「/」拆层；叶子去掉重复的分组前缀', () => {
    const table = {
      headers: ['类别', '期末余额/账面余额/金额', '比例', '金额'],
      columns: [
        { key: 'label', label: '类别', is_label: true },
        { key: 'a', label: '金额', group: '期末余额/账面余额' },
        { key: 'b', label: '比例', group: '期末余额/账面余额' },
        { key: 'c', label: '金额', group: '期末余额/坏账准备' },
      ],
    }
    const tree = buildNoteColumnTree(table)
    expect(tree[1]).toEqual({ label: '期末余额', children: [
      { label: '账面余额', children: [{ label: '金额', headerIdx: 1 }, { label: '比例', headerIdx: 2 }] },
      { label: '坏账准备', children: [{ label: '金额', headerIdx: 3 }] },
    ] })
  })

  it('平表头里的「/」是字面，不拆；<br/> 换行标记去掉', () => {
    const table = { headers: ['项目', '递延所得税资产/负债', '转回或收回前累计<br/>已计提坏账准备金额'] }
    expect(buildNoteColumnTree(table)).toEqual([
      { label: '项目', headerIdx: 0 },
      { label: '递延所得税资产/负债', headerIdx: 1 },
      { label: '转回或收回前累计已计提坏账准备金额', headerIdx: 2 },
    ])
  })

  it('不相邻的同名分组各自成组；没有表头 ⇒ 空', () => {
    const paths = noteColumnPaths({
      headers: ['项目', 'x', 'y', 'z'],
      _column_groups: [{ group: 'A', start: 1, span: 1 }, { group: 'B', start: 2, span: 1 }, { group: 'A', start: 3, span: 1 }],
    })
    expect(paths).toEqual([['项目'], ['A', 'x'], ['B', 'y'], ['A', 'z']])
    expect(buildNoteColumnTree({ headers: [] })).toEqual([])
  })
})
