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

// ─── Property-Based Tests (fast-check PBT) ──────────────────────────────────
// Property 6: 跨底稿索引解析与跳转语义
// Validates: Requirements 3.11.8 + 3.11.9 + 3.11.10
//
// 8 sub-properties:
// 6a 合法输入返回结构      — `${ns}:${target}` → { ns, layer, target }
// 6b layer 决定性派生      — result.layer === NAMESPACE_LAYER_MAP[result.ns]
// 6c 非法输入返回 null     — parseIndexRef never throws on garbage input
// 6d 幂等性                — re-parsing result.target doesn't break
// 6e 空白容错              — leading/trailing whitespace preserves result
// 6f 大小写不敏感          — ns case variation → same canonical ns
// 6g loose mode 底稿编码   — [A-S]\d+(-\d+)*[A-Z]? → non-null wp/sheet
// 6h GT_Custom 跳过        — GT_Custom* (case-insensitive) → null

import fc from 'fast-check'

const VALID_NS_LIST = [
  'wp',
  'sheet',
  'cell',
  'Note',
  'TB',
  'Adj',
  'Att',
  'EQCR',
  'Calc',
  'Sample',
  'Confirm',
] as const

// Arbitrary: a valid canonical namespace (case-sensitive form from whitelist)
const arbNamespace = fc.constantFrom(...VALID_NS_LIST)

// Arbitrary: non-empty target with no colon (avoids strict-mode collision)
// and no leading/trailing whitespace (so we test trimming separately)
const arbTarget = fc
  .string({ minLength: 1, maxLength: 30 })
  .filter((s) => {
    const t = s.trim()
    return t.length > 0 && !t.includes(':')
  })
  .map((s) => s.trim())

// Arbitrary: workpaper code matching loose pattern [A-S]\d+(-\d+)*[A-Z]?
const arbWpCode = fc
  .tuple(
    fc.constantFrom('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'S'),
    fc.integer({ min: 1, max: 99 }),
    fc.array(fc.integer({ min: 1, max: 99 }), { maxLength: 3 }),
    fc.option(fc.constantFrom('A', 'B', 'C'), { nil: '' }),
  )
  .map(([cycle, num, subs, letter]) => {
    const subPart = subs.length > 0 ? '-' + subs.join('-') : ''
    // Letter suffix and hyphen subs are mutually exclusive in real codes,
    // but parser handles both — pick one to keep generation clean
    if (subs.length > 0) return `${cycle}${num}${subPart}`
    return `${cycle}${num}${letter}`
  })

describe('parseIndexRef - 属性测试 (fast-check PBT)', () => {
  // ─── Property 6a: 合法输入返回结构 ─────────────────────────────────────
  it('Property 6a: `${ns}:${target}` returns { ns, layer, target }', () => {
    fc.assert(
      fc.property(arbNamespace, arbTarget, (ns, target) => {
        const result = parseIndexRef(`${ns}:${target}`)
        expect(result).not.toBeNull()
        expect(result?.ns).toBe(ns)
        expect(result?.target).toBe(target)
        expect(result?.layer).toBe(NAMESPACE_LAYER_MAP[ns])
      }),
      { numRuns: 50 },
    )
  })

  // ─── Property 6b: layer 决定性派生 ─────────────────────────────────────
  it('Property 6b: result.layer === NAMESPACE_LAYER_MAP[result.ns]', () => {
    // Strict-mode inputs
    fc.assert(
      fc.property(arbNamespace, arbTarget, (ns, target) => {
        const result = parseIndexRef(`${ns}:${target}`)
        if (result !== null) {
          expect(result.layer).toBe(NAMESPACE_LAYER_MAP[result.ns])
        }
      }),
      { numRuns: 50 },
    )

    // Loose-mode inputs
    fc.assert(
      fc.property(arbWpCode, (code) => {
        const result = parseIndexRef(code)
        if (result !== null) {
          expect(result.layer).toBe(NAMESPACE_LAYER_MAP[result.ns])
          // Loose mode only ever produces wp/sheet/cell layers
          expect([1, 2, 3]).toContain(result.layer)
        }
      }),
      { numRuns: 50 },
    )
  })

  // ─── Property 6c: 非法输入返回 null（never throws） ────────────────────
  it('Property 6c: garbage input returns null (never throws)', () => {
    // Random strings that don't match any valid pattern (fast-check v4: `string` is Unicode-capable)
    const arbGarbage = fc.string({ maxLength: 40 }).filter((s) => {
      const t = s.trim()
      // Exclude strings that would match strict mode
      if (/^(wp|sheet|cell|Note|TB|Adj|Att|EQCR|Calc|Sample|Confirm):/i.test(t)) return false
      // Exclude strings that would match loose mode
      if (/^[A-S]\d+(?:-\d+)*[A-Z]?$/i.test(t)) return false
      // Exclude cell-with-bang form (e.g., D2-1!B23)
      if (t.includes('!')) {
        const parts = t.split('!')
        if (parts.length === 2 && /^[A-S]\d+(?:-\d+)*[A-Z]?$/i.test(parts[0].trim())) {
          return false
        }
      }
      return true
    })

    fc.assert(
      fc.property(arbGarbage, (input) => {
        // Should never throw
        const result = parseIndexRef(input)
        expect(result).toBeNull()
      }),
      { numRuns: 50 },
    )
  })

  // ─── Property 6d: 幂等性 — re-parsing result.target is safe ────────────
  it('Property 6d: re-parsing result.target never throws or recurses', () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 40 }), (input) => {
        // First call: never throws
        const first = parseIndexRef(input)
        // Second call on extracted target: never throws (may be null)
        const second = parseIndexRef(first?.target ?? '')
        // Either null or a well-formed ResolvedIndexRef
        if (second !== null) {
          expect(second.ns).toBeTruthy()
          expect(second.target).toBeTruthy()
          expect([1, 2, 3, 4]).toContain(second.layer)
          expect(second.layer).toBe(NAMESPACE_LAYER_MAP[second.ns])
        }
      }),
      { numRuns: 50 },
    )
  })

  // ─── Property 6e: 空白容错 ────────────────────────────────────────────
  it('Property 6e: leading/trailing whitespace preserves result (after trim)', () => {
    const arbWhitespace = fc.constantFrom(' ', '  ', '   ', '\t', ' \t ')

    fc.assert(
      fc.property(arbNamespace, arbTarget, arbWhitespace, arbWhitespace, (ns, target, lead, trail) => {
        const base = parseIndexRef(`${ns}:${target}`)
        const padded = parseIndexRef(`${lead}${ns}:${target}${trail}`)
        expect(padded).toEqual(base)
      }),
      { numRuns: 50 },
    )
  })

  // ─── Property 6f: 大小写不敏感（命名空间归一化） ───────────────────────
  it('Property 6f: ns case variations canonicalize to same ns', () => {
    fc.assert(
      fc.property(arbNamespace, arbTarget, (ns, target) => {
        const lower = parseIndexRef(`${ns.toLowerCase()}:${target}`)
        const upper = parseIndexRef(`${ns.toUpperCase()}:${target}`)
        const canonical = parseIndexRef(`${ns}:${target}`)

        expect(lower).not.toBeNull()
        expect(upper).not.toBeNull()
        expect(canonical).not.toBeNull()

        // All three return the same canonical ns
        expect(lower?.ns).toBe(canonical?.ns)
        expect(upper?.ns).toBe(canonical?.ns)
        // And the same layer (derived from ns)
        expect(lower?.layer).toBe(canonical?.layer)
        expect(upper?.layer).toBe(canonical?.layer)
      }),
      { numRuns: 50 },
    )
  })

  // ─── Property 6g: loose mode 底稿编码 ─────────────────────────────────
  it('Property 6g: [A-S]\\d+(-\\d+)*[A-Z]? returns non-null with ns ∈ {wp, sheet}', () => {
    fc.assert(
      fc.property(arbWpCode, (code) => {
        const result = parseIndexRef(code)
        expect(result).not.toBeNull()
        expect(['wp', 'sheet']).toContain(result?.ns)
        // Target is always uppercased in loose mode
        expect(result?.target).toBe(code.toUpperCase())
      }),
      { numRuns: 50 },
    )
  })

  // ─── Property 6h: GT_Custom 跳过 ──────────────────────────────────────
  it('Property 6h: GT_Custom* (case-insensitive) returns null', () => {
    const arbGtCustomSuffix = fc.string({ maxLength: 20 })
    const arbCasePrefix = fc.constantFrom(
      'GT_Custom',
      'gt_custom',
      'GT_CUSTOM',
      'Gt_Custom',
      'gT_cUsToM',
    )

    fc.assert(
      fc.property(arbCasePrefix, arbGtCustomSuffix, (prefix, suffix) => {
        const result = parseIndexRef(`${prefix}${suffix}`)
        expect(result).toBeNull()
      }),
      { numRuns: 50 },
    )
  })
})
