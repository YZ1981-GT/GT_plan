/**
 * sheetIdentityMatch.spec.ts — Task 1.2 / ADR-FMC-01 右栏串页修复单测
 *
 * 验收判据（tasks.md Task 1.2）：
 *   - 逐一构造报告反例断言不串页：E1-1 vs E1-10/14/15、D2-1 vs D2-10/12。
 *   - 缺结构身份行断言被 fail-closed 排除（不退 includes）。
 *   - 变异反证：注入 includes 旧逻辑 / 注入 E1-10 串页行，对应反例用例应打红；
 *     未注入时不命中（反向断言）。
 */
import { describe, it, expect } from 'vitest'
import {
  normalizeSheetKey,
  normalizeSheetCode,
  extractSheetCodeFromName,
  matchRowToSelectedSheet,
  sheetCodeEquals,
} from '../sheetIdentityMatch'

// ── 报告反例：当前 sheet 是 E1-1 / D2-1 时不得混入 E1-10/14/15、D2-10/12 的公式 ──
// 这几组是 §1 #1 实测的真实串页对（E1-1 ⊂ E1-10 等的子串关系正是旧 includes 的病灶）。
const SPILL_PAIRS: Array<[string, string]> = [
  ['E1-1', 'E1-10'],
  ['E1-1', 'E1-14'],
  ['E1-1', 'E1-15'],
  ['D2-1', 'D2-10'],
  ['D2-1', 'D2-12'],
]

describe('normalizeSheetKey — 与后端 stable_key.normalize_sheet_key 同口径', () => {
  it('剥前导中文排序前缀 + 子序号（「五、1 审定表D2-1」→「审定表D2-1」）', () => {
    expect(normalizeSheetKey('五、1 审定表D2-1')).toBe('审定表D2-1')
  })

  it('剥阿拉伯数字 / 括号序号前缀', () => {
    expect(normalizeSheetKey('1. 货币资金')).toBe('货币资金')
    expect(normalizeSheetKey('（一）货币资金')).toBe('货币资金')
  })

  it('折叠全角空格为单个半角空格 + trim', () => {
    expect(normalizeSheetKey('　审定表　D2-1　')).toBe('审定表 D2-1')
  })

  it('大小写敏感（保留 wp_code 大小写）', () => {
    expect(normalizeSheetKey('审定表D2-1')).toBe('审定表D2-1')
  })

  it('正文以数字开头不被当子序号吞掉（「一、0」→「0」）', () => {
    expect(normalizeSheetKey('一、0')).toBe('0')
  })

  it('空/未定义 → 空串', () => {
    expect(normalizeSheetKey('')).toBe('')
    expect(normalizeSheetKey(null)).toBe('')
    expect(normalizeSheetKey(undefined)).toBe('')
  })
})

describe('normalizeSheetCode — 结构化编码归一', () => {
  it('trim + 小写 + 破折号/下划线统一', () => {
    expect(normalizeSheetCode(' E1-1 ')).toBe('e1-1')
    expect(normalizeSheetCode('E1_1')).toBe('e1-1')
    expect(normalizeSheetCode('E1—1')).toBe('e1-1')
  })

  it('剥 wp-/sheet- 前缀', () => {
    expect(normalizeSheetCode('wp-E1-1')).toBe('e1-1')
    expect(normalizeSheetCode('sheet-D2-1')).toBe('d2-1')
  })
})

describe('extractSheetCodeFromName — 从展示名提取结构化编码（边界锚定，禁子串）', () => {
  it('整体即编码', () => {
    expect(extractSheetCodeFromName('E1-1')).toBe('e1-1')
  })

  it('末尾编码 token（前有非字母数字边界）', () => {
    expect(extractSheetCodeFromName('货币资金审定表 E1-1')).toBe('e1-1')
  })

  it('不把 E1-10 的末段误当 E1-1', () => {
    // 「...e1-10」整体就是结构化编码 e1-10，提取结果必须是 e1-10（而非 e1-1）
    expect(extractSheetCodeFromName('银行账户核对表E1-10')).toBe('e1-10')
  })

  it('纯中文/无结构编码 → 空串（fail-closed）', () => {
    expect(extractSheetCodeFromName('货币资金')).toBe('')
    expect(extractSheetCodeFromName('')).toBe('')
  })
})

describe('matchRowToSelectedSheet — 报告反例：当前 sheet 不得串页', () => {
  it.each(SPILL_PAIRS)('选中 %s 时，%s 的行不命中（禁 includes 串页）', (selected, other) => {
    // sheet_name 维度（wp_formula items 典型形态：sheet_name 带编码）
    expect(matchRowToSelectedSheet({ sheet_name: `审定表${other}` }, selected)).toBe(false)
    // sheet_codes 维度（surfaced 典型形态：结构化编码数组）
    expect(matchRowToSelectedSheet({ sheet_codes: [other] }, selected)).toBe(false)
    // stable_sheet_key 维度（需选中 sheet key 参与；两键不等 → false）
    expect(
      matchRowToSelectedSheet({ stable_sheet_key: `审定表${other}` }, selected, `审定表${selected}`),
    ).toBe(false)
  })

  it.each(SPILL_PAIRS)('选中 %s 时，本页 %s 自身的行命中（反向断言：精确相等放行）', (selected) => {
    expect(matchRowToSelectedSheet({ sheet_name: `审定表${selected}` }, selected)).toBe(true)
    expect(matchRowToSelectedSheet({ sheet_codes: [selected] }, selected)).toBe(true)
    expect(
      matchRowToSelectedSheet({ stable_sheet_key: `审定表${selected}` }, selected, `审定表${selected}`),
    ).toBe(true)
  })
})

describe('matchRowToSelectedSheet — fail-closed 排除（禁退回 includes）', () => {
  it('行无任何可解析结构身份 → 排除', () => {
    expect(matchRowToSelectedSheet({ sheet_name: '货币资金' }, 'E1-1')).toBe(false)
    expect(matchRowToSelectedSheet({}, 'E1-1')).toBe(false)
    expect(matchRowToSelectedSheet({ sheet_name: '' }, 'E1-1')).toBe(false)
  })

  it('选中 sheet 本身无结构身份 → 排除（无从归属）', () => {
    expect(matchRowToSelectedSheet({ sheet_codes: ['E1-1'] }, '')).toBe(false)
    expect(matchRowToSelectedSheet({ sheet_codes: ['E1-1'] }, null)).toBe(false)
  })

  it('空 sheet_codes 数组 → 不命中具体编码（工作簿级，调用方另行恒显示）', () => {
    expect(matchRowToSelectedSheet({ sheet_codes: [] }, 'E1-1')).toBe(false)
  })

  it('stable_sheet_key 维度优先：选中 key 存在时仅比 key，不回退编码串页', () => {
    // 行有 stable_sheet_key 且选中 key 存在 → 走维度 1 精确等值；两键相等放行
    expect(
      matchRowToSelectedSheet({ stable_sheet_key: '审定表E1-1' }, 'E1-1', '审定表E1-1'),
    ).toBe(true)
    // 两键不等即排除，不因 sheet_codes 另有命中而放行（维度 1 短路）
    expect(
      matchRowToSelectedSheet(
        { stable_sheet_key: '审定表E1-10', sheet_codes: ['E1-1'] },
        'E1-1',
        '审定表E1-1',
      ),
    ).toBe(false)
  })
})

describe('sheetCodeEquals — 编码精确等值（surfaced 逐项）', () => {
  it('归一后精确相等命中', () => {
    expect(sheetCodeEquals('E1-1', 'e1-1')).toBe(true)
    expect(sheetCodeEquals('E1_1', 'E1-1')).toBe(true)
  })

  it.each(SPILL_PAIRS)('%s 与 %s 不相等（禁子串）', (a, b) => {
    expect(sheetCodeEquals(a, b)).toBe(false)
    expect(sheetCodeEquals(b, a)).toBe(false)
  })

  it('任一侧空 → false（fail-closed）', () => {
    expect(sheetCodeEquals('', 'E1-1')).toBe(false)
    expect(sheetCodeEquals('E1-1', null)).toBe(false)
  })
})

// ────────────────────────────────────────────────────────────────────────────
// 变异反证（tasks.md Task 1.2「变异反证」）：
//   证明「若把旧 includes 子串逻辑注入回来，报告反例会打红」。
//   做法：在测试内重建旧 matchSheetCode 的 includes 语义（legacy mutant），断言它对
//   同一组反例会**错误地命中**（即若生产代码退回该逻辑，上面的反例用例必然打红）；
//   同时反向断言当前生产函数对同一组反例**不命中**（未注入时不命中）。
// ────────────────────────────────────────────────────────────────────────────
describe('变异反证 — 注入旧 includes 逻辑应使反例命中（生产函数不命中）', () => {
  // 旧 matchSheetCode 的病灶逻辑（a === b || a.includes(b) || b.includes(a)）。
  function legacyIncludesMatch(actual: string, expected: string): boolean {
    const a = normalizeSheetCode(actual)
    const b = normalizeSheetCode(expected)
    if (!a || !b) return false
    return a === b || a.includes(b) || b.includes(a)
  }

  it.each(SPILL_PAIRS)('变异体（includes）错误命中 %s⊂%s —— 坐实注入即打红', (selected, other) => {
    // 变异体：选中 E1-1 时，E1-10 的编码会被 includes 误判为命中（这正是旧 bug）。
    expect(legacyIncludesMatch(other, selected)).toBe(true)
    // 反向断言：生产结构化精确等值对同一反例不命中（未注入时不命中）。
    expect(sheetCodeEquals(other, selected)).toBe(false)
    expect(matchRowToSelectedSheet({ sheet_codes: [other] }, selected)).toBe(false)
  })

  it('变异体会把串页行当成本页行；生产函数把它 fail-closed 排除', () => {
    // 注入一条 E1-10 串页行，选中 E1-1：
    const spillRow = { sheet_name: '银行账户核对表E1-10', sheet_codes: ['E1-10'] }
    // 变异体（对 sheet_codes 用 includes）会命中：
    expect(spillRow.sheet_codes.some((c) => legacyIncludesMatch(c, 'E1-1'))).toBe(true)
    // 生产函数精确等值 → 不命中（反向断言）：
    expect(matchRowToSelectedSheet(spillRow, 'E1-1')).toBe(false)
    // 本页 E1-1 行仍命中（确保不是全盘排除）：
    expect(matchRowToSelectedSheet({ sheet_codes: ['E1-1'] }, 'E1-1')).toBe(true)
  })
})
