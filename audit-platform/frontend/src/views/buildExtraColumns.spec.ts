/**
 * Property 6: 前端动态列 = 本批 extra_fields 键并集
 * Feature: ledger-raw-extra-column-display (Task 3.2)
 *
 * 覆盖：
 *  - 多行 extra_fields 键的并集
 *  - 保持首次出现顺序
 *  - 重复键去重
 *  - 空 items 数组 → []
 *  - 部分行无 extra_fields（undefined / 缺字段）→ 跳过不报错
 *  - 全部行 extra_fields 为 {} → []
 */
import { describe, it, expect } from 'vitest'
import { buildExtraColumns, visibleExtraColumns, fmtExtraCell } from './ledgerExtraColumns'

describe('buildExtraColumns', () => {
  it('多行 extra_fields 键取并集', () => {
    const items = [
      { extra_fields: { 备注: 'a', 经办人: 'b' } },
      { extra_fields: { 经办人: 'c', 内部编号: 'd' } },
    ]
    expect(buildExtraColumns(items)).toEqual(['备注', '经办人', '内部编号'])
  })

  it('保持键首次出现的顺序（不按字母/字典序）', () => {
    const items = [
      { extra_fields: { zeta: 1, alpha: 2 } },
      { extra_fields: { mid: 3 } },
    ]
    expect(buildExtraColumns(items)).toEqual(['zeta', 'alpha', 'mid'])
  })

  it('重复键去重（同键只出现一次）', () => {
    const items = [
      { extra_fields: { k1: 1 } },
      { extra_fields: { k1: 2 } },
      { extra_fields: { k1: 3, k2: 4 } },
    ]
    expect(buildExtraColumns(items)).toEqual(['k1', 'k2'])
  })

  it('空 items 数组 → []', () => {
    expect(buildExtraColumns([])).toEqual([])
  })

  it('部分行缺 extra_fields（undefined / 缺字段）→ 跳过不报错', () => {
    const items = [
      { extra_fields: { a: 1 } },
      {}, // 缺 extra_fields
      { extra_fields: undefined }, // 显式 undefined
      { extra_fields: { b: 2 } },
    ]
    expect(buildExtraColumns(items as Array<{ extra_fields?: Record<string, unknown> }>)).toEqual([
      'a',
      'b',
    ])
  })

  it('全部行 extra_fields 为 {} → []', () => {
    const items = [{ extra_fields: {} }, { extra_fields: {} }, { extra_fields: {} }]
    expect(buildExtraColumns(items)).toEqual([])
  })

  it('null items（防御）→ []', () => {
    expect(buildExtraColumns(null as unknown as [])).toEqual([])
  })
})

/**
 * Task 8.1*：额外列显隐过滤 visibleExtraColumns(allKeys, prefs)
 *  - 未在 prefs 的键默认显示；prefs[k] === false 才隐藏；保持原顺序。
 */
describe('visibleExtraColumns', () => {
  it('无 prefs → 全部显示（保持顺序）', () => {
    expect(visibleExtraColumns(['a', 'b', 'c'])).toEqual(['a', 'b', 'c'])
  })

  it('prefs[k] === false 的键被隐藏，其余保留原顺序', () => {
    expect(visibleExtraColumns(['a', 'b', 'c'], { b: false })).toEqual(['a', 'c'])
  })

  it('未在 prefs 中的键默认显示（true）', () => {
    expect(visibleExtraColumns(['a', 'b'], { a: true })).toEqual(['a', 'b'])
  })

  it('prefs[k] 显式 true 不隐藏', () => {
    expect(visibleExtraColumns(['x', 'y'], { x: true, y: false })).toEqual(['x'])
  })

  it('空 allKeys / null 防御 → []', () => {
    expect(visibleExtraColumns([])).toEqual([])
    expect(visibleExtraColumns(null as unknown as string[])).toEqual([])
  })
})

/**
 * Task 8.3*：额外列单元格值格式化 fmtExtraCell(v) —— 非标量防御。
 */
describe('fmtExtraCell', () => {
  it('null / undefined → 空串', () => {
    expect(fmtExtraCell(null)).toBe('')
    expect(fmtExtraCell(undefined)).toBe('')
  })

  it('标量原样字符串化', () => {
    expect(fmtExtraCell('审核通过')).toBe('审核通过')
    expect(fmtExtraCell(123)).toBe('123')
    expect(fmtExtraCell(0)).toBe('0')
    expect(fmtExtraCell(false)).toBe('false')
  })

  it('object → JSON.stringify（不再 [object Object]）', () => {
    expect(fmtExtraCell({ a: 1, b: '张三' })).toBe('{"a":1,"b":"张三"}')
    expect(fmtExtraCell({})).toBe('{}')
  })

  it('array → JSON.stringify', () => {
    expect(fmtExtraCell([1, 2, 3])).toBe('[1,2,3]')
    expect(fmtExtraCell([])).toBe('[]')
  })

  it('循环引用等无法序列化时降级为 String（不抛错）', () => {
    const obj: any = {}
    obj.self = obj
    expect(() => fmtExtraCell(obj)).not.toThrow()
    expect(typeof fmtExtraCell(obj)).toBe('string')
  })
})

/**
 * Task 7.2: 修复复制到剪贴板的 [object Object] 回归
 *
 * 覆盖：
 *  - 复制行 keys 不含 extra_fields / raw_extra 对象本身（不再 [object Object]）
 *  - extra_fields 业务键展开为额外制表符列（表头 + 数据行）
 *  - 缺失额外键写空
 *  - 内部字段（_ 前缀 / excludeKeys）被排除
 *  - 空 rows → 空表
 */
import { buildClipboardTable } from './ledgerExtraColumns'

describe('buildClipboardTable', () => {
  const EXCLUDE = ['id', 'project_id', 'raw_extra', 'extra_fields']

  it('extra_fields 业务键展开为额外列（表头 + 数据行），不输出 [object Object]', () => {
    const rows = [
      { voucher_no: '0001', debit: 100, extra_fields: { 状态: '已审核', 复核人: '张三' } },
      { voucher_no: '0002', debit: 200, extra_fields: { 状态: '已过账', 复核人: '李四' } },
    ]
    const { header, lines, baseKeys, extraKeys } = buildClipboardTable(rows, EXCLUDE)
    expect(baseKeys).toEqual(['voucher_no', 'debit'])
    expect(extraKeys).toEqual(['状态', '复核人'])
    expect(header).toBe('voucher_no\tdebit\t状态\t复核人')
    expect(lines[0]).toBe('0001\t100\t已审核\t张三')
    expect(lines[1]).toBe('0002\t200\t已过账\t李四')
    // 不含 extra_fields 对象本身，绝无 [object Object]
    expect(header).not.toContain('extra_fields')
    expect(lines.join('\n')).not.toContain('[object Object]')
  })

  it('缺失额外键写空（键并集，某行缺该键 → 空单元格）', () => {
    const rows = [
      { voucher_no: '0001', extra_fields: { 状态: '已审核' } },
      { voucher_no: '0002', extra_fields: { 备注: '调整' } },
    ]
    const { header, lines } = buildClipboardTable(rows, EXCLUDE)
    expect(header).toBe('voucher_no\t状态\t备注')
    expect(lines[0]).toBe('0001\t已审核\t') // 缺 备注 → 空
    expect(lines[1]).toBe('0002\t\t调整') // 缺 状态 → 空
  })

  it('内部字段（_ 前缀 + excludeKeys）被排除', () => {
    const rows = [
      { voucher_no: '0001', _type: 'normal', id: 'x', project_id: 'p', raw_extra: { a: 1 }, extra_fields: { 状态: 'ok' } },
    ]
    const { baseKeys, header } = buildClipboardTable(rows, EXCLUDE)
    expect(baseKeys).toEqual(['voucher_no'])
    expect(header).toBe('voucher_no\t状态')
    expect(header).not.toContain('raw_extra')
    expect(header).not.toContain('_type')
  })

  it('无 extra_fields 时仅固定列（视觉/行为不变）', () => {
    const rows = [{ voucher_no: '0001', debit: 100 }]
    const { header, lines, extraKeys } = buildClipboardTable(rows, EXCLUDE)
    expect(extraKeys).toEqual([])
    expect(header).toBe('voucher_no\tdebit')
    expect(lines[0]).toBe('0001\t100')
  })

  it('空 rows → 空表', () => {
    expect(buildClipboardTable([], EXCLUDE)).toEqual({ header: '', lines: [], baseKeys: [], extraKeys: [] })
  })
})

/**
 * Task 8.1*: 额外列显隐过滤纯函数 visibleExtraColumns（map-based prefs）
 * Task 8.3*: 额外列单元格非标量值防御 fmtExtraCell
 */
describe('visibleExtraColumns', () => {
  it('无 prefs → 全部显示（保持顺序）', () => {
    expect(visibleExtraColumns(['状态', '复核人', '备注'])).toEqual(['状态', '复核人', '备注'])
  })
  it('prefs[k]===false 隐藏该列，其余保留', () => {
    expect(visibleExtraColumns(['状态', '复核人', '备注'], { 复核人: false })).toEqual(['状态', '备注'])
  })
  it('prefs[k]===true 或未列出的键默认显示', () => {
    expect(visibleExtraColumns(['状态', '备注'], { 状态: true })).toEqual(['状态', '备注'])
  })
  it('空 allKeys → []', () => {
    expect(visibleExtraColumns([], { 状态: false })).toEqual([])
  })
})

describe('fmtExtraCell', () => {
  it('null / undefined → 空串', () => {
    expect(fmtExtraCell(null)).toBe('')
    expect(fmtExtraCell(undefined)).toBe('')
  })
  it('标量（string/number/bool）→ String', () => {
    expect(fmtExtraCell('已审核')).toBe('已审核')
    expect(fmtExtraCell(123)).toBe('123')
    expect(fmtExtraCell(true)).toBe('true')
  })
  it('对象 / 数组 → JSON.stringify（不再 [object Object]）', () => {
    expect(fmtExtraCell({ a: 1 })).toBe('{"a":1}')
    expect(fmtExtraCell([1, 2])).toBe('[1,2]')
    expect(fmtExtraCell({ a: 1 })).not.toContain('[object Object]')
  })
})
