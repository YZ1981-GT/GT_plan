/**
 * Univer 工作簿 → 未保存草稿正文的序列化守卫（spec chat-host-draft-overlay / Task 4）。
 *
 * 判据取向：模型需要的只是「哪个 sheet 的哪个格子是什么值」，所以断言的是**摊平结果**
 * 而不是 snapshot 原样 JSON —— 后者会把样式 / 合并 / 列宽全带上，一张真实底稿几 MB，
 * 而后端上限 20 万字符（超限 422、不裁剪）。
 */

import { describe, expect, it } from 'vitest'

import { columnLetter, serializeUniverDraft } from '../univerDraftContent'

function snapshot(sheets: Record<string, unknown>, sheetOrder?: string[]) {
  return { sheets, ...(sheetOrder ? { sheetOrder } : {}) }
}

describe('columnLetter — Excel 列号', () => {
  it.each([
    [0, 'A'],
    [1, 'B'],
    [25, 'Z'],
    [26, 'AA'],
    [27, 'AB'],
    [51, 'AZ'],
    [52, 'BA'],
    [701, 'ZZ'],
    [702, 'AAA'],
  ])('%i → %s', (index, expected) => {
    expect(columnLetter(index)).toBe(expected)
  })
})

describe('serializeUniverDraft — 只摊非空格子的值与公式', () => {
  it('按 sheetOrder 输出，格子按行列号排序，空值格跳过', () => {
    const text = serializeUniverDraft(snapshot({
      s2: { name: '审定表', cellData: { 0: { 1: { v: 200 } } } },
      s1: { name: '程序表', cellData: { 1: { 0: { v: '第二步' }, 2: { v: '' } }, 0: { 0: { v: '第一步' } } } },
    }, ['s1', 's2']))

    expect(text).toBe([
      '【程序表】',
      'A1=第一步',
      'A2=第二步',
      '【审定表】',
      'B1=200',
    ].join('\n'))
  })

  it('公式格同时给出公式与值（模型据此判断口径）', () => {
    const text = serializeUniverDraft(snapshot({
      s1: { name: '明细', cellData: { 4: { 2: { f: '=SUM(C1:C4)', v: 1200 } } } },
    }))
    expect(text).toBe(['【明细】', 'C5==SUM(C1:C4) → 1200'].join('\n'))
  })

  it('只有公式没有缓存值时只给公式', () => {
    const text = serializeUniverDraft(snapshot({
      s1: { name: '明细', cellData: { 0: { 0: { f: '=A2+1' } } } },
    }))
    expect(text).toBe(['【明细】', 'A1==A2+1'].join('\n'))
  })

  it('空工作簿 / 无 sheet / 非对象一律 null（不提供空草稿）', () => {
    for (const input of [
      null,
      undefined,
      'text',
      42,
      {},
      { sheets: null },
      { sheets: {} },
      // 有 sheet 但全是空格子
      snapshot({ s1: { name: '空表', cellData: {} } }),
      snapshot({ s1: { name: '空表', cellData: { 0: { 0: { v: '' }, 1: { v: '   ' } } } } }),
    ]) {
      expect(serializeUniverDraft(input)).toBeNull()
    }
  })

  it('sheet 没有名字时用 id 兜底（不丢整张表）', () => {
    const text = serializeUniverDraft(snapshot({ sheet0: { cellData: { 0: { 0: { v: 1 } } } } }))
    expect(text).toBe(['【sheet0】', 'A1=1'].join('\n'))
  })

  it('同一份 snapshot 两次序列化逐字相同（服务端按 sha256 判重）', () => {
    const input = snapshot({
      s1: { name: 'a', cellData: { 2: { 5: { v: 'x' }, 1: { v: 'y' } }, 0: { 0: { v: 'z' } } } },
      s2: { name: 'b', cellData: { 0: { 0: { v: 'w' } } } },
    })
    expect(serializeUniverDraft(input)).toBe(serializeUniverDraft(input))
  })

  it('行/列号升序由 JS 键序保证（插入顺序打乱也按数值升序输出）', () => {
    // 🔴 判据必须能区分「按数值升序」与「按插入顺序」：故意先写大号键。
    //    原先这里靠显式 `.sort()`，实测删掉 sort 零用例变红（ECMAScript 规定整数索引键
    //    按数值升序返回），因此 sort 是无作用代码已移除 —— 本条改为直接钉住那个语言保证。
    const text = serializeUniverDraft(snapshot({
      s1: {
        name: '明细',
        cellData: {
          10: { 0: { v: 'r11' } },
          2: { 3: { v: 'D3' }, 0: { v: 'A3' } },
          0: { 0: { v: 'A1' } },
        },
      },
    }))
    expect(text).toBe([
      '【明细】',
      'A1=A1',
      'A3=A3',
      'D3=D3',
      'A11=r11',
    ].join('\n'))
  })

  it('没有 sheetOrder 时按 sheet id 排序（顺序稳定）', () => {
    const text = serializeUniverDraft(snapshot({
      b: { name: 'B', cellData: { 0: { 0: { v: 2 } } } },
      a: { name: 'A', cellData: { 0: { 0: { v: 1 } } } },
    }))
    expect(text).toBe(['【A】', 'A1=1', '【B】', 'A1=2'].join('\n'))
  })

  it('超过上限时截断并显式说明（不静默丢内容）', () => {
    const cellData: Record<string, Record<string, { v: string }>> = {}
    for (let row = 0; row < 200; row += 1) {
      cellData[String(row)] = { 0: { v: `第 ${row} 行的很长的审计说明文字，用于撑爆上限` } }
    }
    const text = serializeUniverDraft(snapshot({ s1: { name: '明细', cellData } }), { maxChars: 500 })
    expect(text).not.toBeNull()
    expect(text!.length).toBeLessThan(700)
    expect(text).toContain('草稿超出上限')
  })

  it('对象型值按 JSON 输出（不出现 [object Object]）', () => {
    const text = serializeUniverDraft(snapshot({
      s1: { name: '明细', cellData: { 0: { 0: { v: { rich: 'x' } } } } },
    }))
    expect(text).toContain('{"rich":"x"}')
    expect(text).not.toContain('[object Object]')
  })
})
