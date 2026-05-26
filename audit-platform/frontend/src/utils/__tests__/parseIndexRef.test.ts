/**
 * parseIndexRef 单元测试
 *
 * Validates: Requirements 3.11.8 + 3.11.9 + 3.11.10
 *
 * 覆盖：
 * - 11 命名空间路由解析
 * - 4 层级跳转语义
 * - 9 种边缘 case
 * - 宽松模式底稿编码识别
 */
import { describe, it, expect } from 'vitest'
import {
  parseIndexRef,
  isValidNamespace,
  NAMESPACE_LAYER_MAP,
  type Namespace,
  type ResolvedIndexRef,
} from '../parseIndexRef'

describe('parseIndexRef - 11 命名空间路由解析（严格模式）', () => {
  it('wp: 主底稿编辑器', () => {
    const result = parseIndexRef('wp:D2')
    expect(result).toEqual({ ns: 'wp', layer: 3, target: 'D2' })
  })

  it('sheet: 同底稿 sheet 切换', () => {
    const result = parseIndexRef('sheet:D2-1')
    expect(result).toEqual({ ns: 'sheet', layer: 2, target: 'D2-1' })
  })

  it('cell: sheet + cell 高亮', () => {
    const result = parseIndexRef('cell:D2-1!B23')
    expect(result).toEqual({ ns: 'cell', layer: 1, target: 'D2-1!B23' })
  })

  it('Note: 附注模块（中文索引）', () => {
    const result = parseIndexRef('Note:五-1-1')
    expect(result).toEqual({ ns: 'Note', layer: 4, target: '五-1-1' })
  })

  it('TB: 试算表', () => {
    const result = parseIndexRef('TB:1122')
    expect(result).toEqual({ ns: 'TB', layer: 4, target: '1122' })
  })

  it('Adj: 调整分录', () => {
    const result = parseIndexRef('Adj:AJE-001')
    expect(result).toEqual({ ns: 'Adj', layer: 4, target: 'AJE-001' })
  })

  it('Att: 附件预览', () => {
    const result = parseIndexRef('Att:UUID-123')
    expect(result).toEqual({ ns: 'Att', layer: 4, target: 'UUID-123' })
  })

  it('EQCR: EQCR 工作台', () => {
    const result = parseIndexRef('EQCR:RID')
    expect(result).toEqual({ ns: 'EQCR', layer: 4, target: 'RID' })
  })

  it('Calc: 计算 dialog', () => {
    const result = parseIndexRef('Calc:depreciation')
    expect(result).toEqual({ ns: 'Calc', layer: 4, target: 'depreciation' })
  })

  it('Sample: 抽样工具', () => {
    const result = parseIndexRef('Sample:F2-VAL')
    expect(result).toEqual({ ns: 'Sample', layer: 4, target: 'F2-VAL' })
  })

  it('Confirm: 函证管理', () => {
    const result = parseIndexRef('Confirm:D0-001')
    expect(result).toEqual({ ns: 'Confirm', layer: 4, target: 'D0-001' })
  })
})

describe('parseIndexRef - 4 层级跳转语义', () => {
  it('Layer 1 (cell): cell 命名空间 → layer 1', () => {
    const result = parseIndexRef('cell:D2-1!B23')
    expect(result?.layer).toBe(1)
  })

  it('Layer 2 (sheet): sheet 命名空间 → layer 2', () => {
    const result = parseIndexRef('sheet:D2-1')
    expect(result?.layer).toBe(2)
  })

  it('Layer 3 (wp): wp 命名空间 → layer 3', () => {
    const result = parseIndexRef('wp:D2')
    expect(result?.layer).toBe(3)
  })

  it('Layer 4 (module): Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm → layer 4', () => {
    const moduleNamespaces: Namespace[] = ['Note', 'TB', 'Adj', 'Att', 'EQCR', 'Calc', 'Sample', 'Confirm']
    for (const ns of moduleNamespaces) {
      expect(NAMESPACE_LAYER_MAP[ns]).toBe(4)
    }
  })
})

describe('parseIndexRef - 宽松模式（底稿编码识别）', () => {
  it('主底稿编码 D2 → wp layer 3', () => {
    const result = parseIndexRef('D2')
    expect(result).toEqual({ ns: 'wp', layer: 3, target: 'D2' })
  })

  it('sheet 编码 D2-1 → sheet layer 2', () => {
    const result = parseIndexRef('D2-1')
    expect(result).toEqual({ ns: 'sheet', layer: 2, target: 'D2-1' })
  })

  it('多级 sheet 编码 D2-1-1 → sheet layer 2', () => {
    const result = parseIndexRef('D2-1-1')
    expect(result).toEqual({ ns: 'sheet', layer: 2, target: 'D2-1-1' })
  })

  it('字母后缀 D2A → sheet layer 2', () => {
    const result = parseIndexRef('D2A')
    expect(result).toEqual({ ns: 'sheet', layer: 2, target: 'D2A' })
  })

  it('E 循环 E1 → wp layer 3', () => {
    const result = parseIndexRef('E1')
    expect(result).toEqual({ ns: 'wp', layer: 3, target: 'E1' })
  })

  it('S 循环 S15 → wp layer 3', () => {
    const result = parseIndexRef('S15')
    expect(result).toEqual({ ns: 'wp', layer: 3, target: 'S15' })
  })

  it('cell 引用 D2-1!B23 → cell layer 1', () => {
    const result = parseIndexRef('D2-1!B23')
    expect(result).toEqual({ ns: 'cell', layer: 1, target: 'D2-1!B23' })
  })
})

describe('parseIndexRef - 9 种边缘 case', () => {
  // Case 1: 中文索引号
  it('中文索引号 Note:五-1-1 正常解析', () => {
    const result = parseIndexRef('Note:五-1-1')
    expect(result).toEqual({ ns: 'Note', layer: 4, target: '五-1-1' })
  })

  it('中文索引号 Note:五、(1)货币资金 正常解析', () => {
    const result = parseIndexRef('Note:五、(1)货币资金')
    expect(result).toEqual({ ns: 'Note', layer: 4, target: '五、(1)货币资金' })
  })

  // Case 2: 空格处理
  it('前后空格 trim 后匹配', () => {
    const result = parseIndexRef('  D2-1  ')
    expect(result).toEqual({ ns: 'sheet', layer: 2, target: 'D2-1' })
  })

  it('命名空间 target 前后空格 trim', () => {
    const result = parseIndexRef('TB:  1122  ')
    expect(result).toEqual({ ns: 'TB', layer: 4, target: '1122' })
  })

  // Case 3: 大小写归一化
  it('小写底稿编码归一化为大写', () => {
    const result = parseIndexRef('d2-1')
    expect(result).toEqual({ ns: 'sheet', layer: 2, target: 'D2-1' })
  })

  it('命名空间大小写不敏感', () => {
    const result = parseIndexRef('note:五-1-1')
    expect(result).toEqual({ ns: 'Note', layer: 4, target: '五-1-1' })
  })

  it('命名空间全大写', () => {
    const result = parseIndexRef('TB:1122')
    expect(result).toEqual({ ns: 'TB', layer: 4, target: '1122' })
  })

  it('命名空间混合大小写', () => {
    const result = parseIndexRef('eqcr:RID')
    expect(result).toEqual({ ns: 'EQCR', layer: 4, target: 'RID' })
  })

  // Case 4: 多目标 — parseIndexRef 本身返回单个解析结果
  // 多目标处理由 GtIndexChip 组件负责（split + 多次调用 parseIndexRef）
  it('多目标格式不在 parseIndexRef 范围内（返回 null）', () => {
    // "D2-1/D2-2/D2-3" 不匹配任何模式
    const result = parseIndexRef('D2-1/D2-2/D2-3')
    expect(result).toBeNull()
  })

  // Case 5: 不存在 — parseIndexRef 返回结构但 exists 由外部校验
  // 纯函数不做 API 调用，exists 字段由 GtIndexChip 组件设置
  it('解析成功但 exists 字段未设置（由外部校验）', () => {
    const result = parseIndexRef('wp:NONEXISTENT')
    expect(result).not.toBeNull()
    expect(result?.exists).toBeUndefined()
  })

  // Case 6: 被裁剪 — 同上，reason 由外部设置
  it('解析成功但 reason 字段未设置（由外部校验）', () => {
    const result = parseIndexRef('sheet:D2-TRIMMED')
    expect(result).not.toBeNull()
    expect(result?.reason).toBeUndefined()
  })

  // Case 7: 跨项目 — crossProject 由外部设置
  it('解析成功但 crossProject 字段未设置（由外部校验）', () => {
    const result = parseIndexRef('wp:D2')
    expect(result).not.toBeNull()
    expect(result?.crossProject).toBeUndefined()
  })

  // Case 8: GT_Custom — 返回 null（白名单跳过）
  it('GT_Custom 返回 null', () => {
    const result = parseIndexRef('GT_Custom')
    expect(result).toBeNull()
  })

  it('GT_Custom_Data 返回 null', () => {
    const result = parseIndexRef('GT_Custom_Data')
    expect(result).toBeNull()
  })

  it('gt_custom 大小写不敏感也返回 null', () => {
    const result = parseIndexRef('gt_custom')
    expect(result).toBeNull()
  })

  // Case 9: 空 sheet — 解析成功，empty 由外部设置
  it('解析成功但 empty 字段未设置（由外部校验）', () => {
    const result = parseIndexRef('sheet:D2-1')
    expect(result).not.toBeNull()
    expect(result?.empty).toBeUndefined()
  })
})

describe('parseIndexRef - 无效输入', () => {
  it('空字符串返回 null', () => {
    expect(parseIndexRef('')).toBeNull()
  })

  it('纯空格返回 null', () => {
    expect(parseIndexRef('   ')).toBeNull()
  })

  it('无效命名空间返回 null', () => {
    expect(parseIndexRef('Invalid:target')).toBeNull()
  })

  it('命名空间无 target 返回 null', () => {
    expect(parseIndexRef('TB:')).toBeNull()
  })

  it('命名空间 target 仅空格返回 null', () => {
    expect(parseIndexRef('TB:   ')).toBeNull()
  })

  it('不匹配任何模式的文本返回 null', () => {
    expect(parseIndexRef('hello world')).toBeNull()
  })

  it('T 开头不在 A-S 范围返回 null（T1 需通过严格模式 wp:T1 引用）', () => {
    // T(84) > S(83)，不在 [A-S] 范围内
    // T1 IPE 测试需通过严格模式 wp:T1 引用
    expect(parseIndexRef('T1')).toBeNull()
  })

  it('wp:T1 通过严格模式正常解析', () => {
    const result = parseIndexRef('wp:T1')
    expect(result).toEqual({ ns: 'wp', layer: 3, target: 'T1' })
  })

  it('Z 开头不在 A-S 范围返回 null', () => {
    expect(parseIndexRef('Z1')).toBeNull()
  })

  it('数字开头返回 null', () => {
    expect(parseIndexRef('123')).toBeNull()
  })
})

describe('isValidNamespace', () => {
  it('所有 11 个有效命名空间返回 true', () => {
    const validNs = ['wp', 'sheet', 'cell', 'Note', 'TB', 'Adj', 'Att', 'EQCR', 'Calc', 'Sample', 'Confirm']
    for (const ns of validNs) {
      expect(isValidNamespace(ns)).toBe(true)
    }
  })

  it('大小写不敏感', () => {
    expect(isValidNamespace('WP')).toBe(true)
    expect(isValidNamespace('note')).toBe(true)
    expect(isValidNamespace('tb')).toBe(true)
    expect(isValidNamespace('EQCR')).toBe(true)
  })

  it('无效命名空间返回 false', () => {
    expect(isValidNamespace('Invalid')).toBe(false)
    expect(isValidNamespace('')).toBe(false)
    expect(isValidNamespace('foo')).toBe(false)
  })
})

describe('NAMESPACE_LAYER_MAP', () => {
  it('包含全部 11 个命名空间', () => {
    expect(Object.keys(NAMESPACE_LAYER_MAP)).toHaveLength(11)
  })

  it('cell → 1, sheet → 2, wp → 3, 其余 → 4', () => {
    expect(NAMESPACE_LAYER_MAP.cell).toBe(1)
    expect(NAMESPACE_LAYER_MAP.sheet).toBe(2)
    expect(NAMESPACE_LAYER_MAP.wp).toBe(3)
    expect(NAMESPACE_LAYER_MAP.Note).toBe(4)
    expect(NAMESPACE_LAYER_MAP.TB).toBe(4)
    expect(NAMESPACE_LAYER_MAP.Adj).toBe(4)
    expect(NAMESPACE_LAYER_MAP.Att).toBe(4)
    expect(NAMESPACE_LAYER_MAP.EQCR).toBe(4)
    expect(NAMESPACE_LAYER_MAP.Calc).toBe(4)
    expect(NAMESPACE_LAYER_MAP.Sample).toBe(4)
    expect(NAMESPACE_LAYER_MAP.Confirm).toBe(4)
  })
})
