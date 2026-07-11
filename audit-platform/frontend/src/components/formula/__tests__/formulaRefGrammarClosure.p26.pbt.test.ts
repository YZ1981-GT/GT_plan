/**
 * formulaRefGrammarClosure.p26.pbt.test.ts — P26 公式构造点 grammar_v1 闭包 属性测试
 *
 * spec acnr-consumer-wiring · Task 34.5（Property 26，generative）
 *
 * **Property 26: Formula-Ref Grammar Closure**
 *   *For any* `formula_ref` produced by any of the six formula-construction
 *   components (FormulaRefPicker / FormulaEditDialog / FormulaManagerDialog /
 *   FormulaBar / NoteFormulaDialog / CellSelector), the ref SHALL parse under
 *   grammar_v1 (`parseUri` returns non-null) — 即任一构造点都不能 emit 一个
 *   ACNR 无法解析的 ref。
 *
 * 本测试是 task 34.2（example-based contract test）的 PROPERTY-based（generative）
 * 版本：随机生成六组件会 emit 的全部 formula_ref 形态，断言 EVERY 生成 ref 均可被
 * grammar_v1 权威文法 parseUri 解析（non-null）。
 *
 * 六组件 emit 的 formula_ref 形态（design §grammar_v1 三形态 + 五域）：
 *   - 3 参 cell:      WP('parent','sheet','cell')      ↔ wp://parent/sheet#cell
 *   - 2 参 语义列:    WP('wp_code','审定数')             ↔ wp://wp_code/审定数
 *   - custom_flat:    WP('wp_code','wp_code','cell')    ↔ wp://wp_code/wp_code#cell
 *   - TB 域:          TB('code','期末余额')              ↔ tb://code
 *   - REPORT 域:      REPORT('code','期末') / ROW('code')↔ report://code
 *   - NOTE 域:        NOTE('title','合计','期末')         ↔ note://title
 *
 * grammar_v1 权威解析器 = 生产实现 `parseUri`（resolveUri.ts）。校验器把公式函数
 * 形态转换为等价 URI 后交给 parseUri 判定 —— round-trip 成立即代表 formula_ref
 * 是 grammar_v1-valid。
 *
 * **Validates: Requirements 14.6, 14.7, 21.3**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { parseUri } from '@/services/acnr/resolveUri'

// ─── 公式函数 → URI 映射（grammar_v1 五域 + 三形态） ──────────────────────────
//
// 复用 task-18.4（formulaPickers.acnr.pbt.test.ts）的 wpFormulaRefToUri → parseUri
// 模式，并为 TB / REPORT / ROW / NOTE 提供 analogous 映射。

/** 解析 FUNC('a','b',...) 的实参列表；非该形态返回 null。 */
function parseFuncArgs(fn: string, ref: string): string[] | null {
  const re = new RegExp(`^${fn}\\((.*)\\)$`)
  const m = re.exec((ref || '').trim())
  if (!m) return null
  // 允许 0 实参（FUNC()）→ 返回空数组以便下游判非法
  if (m[1].trim() === '') return []
  return m[1].split(',').map((s) => s.trim().replace(/^'(.*)'$/, '$1'))
}

/** WP(...) → wp:// URI（standard 3参 / 语义列 2参 / custom_flat 3参同参标准语法） */
function wpFormulaRefToUri(ref: string): string | null {
  const args = parseFuncArgs('WP', ref)
  if (!args || args.length === 0 || args.some((a) => a === '')) return null
  if (args.length === 3) return `wp://${args[0]}/${args[1]}#${args[2]}`
  if (args.length === 2) return `wp://${args[0]}/${args[1]}`
  return null
}

/** TB('code','column') → tb://code（第二参=语义列，落 sheet/code 级） */
function tbFormulaRefToUri(ref: string): string | null {
  const args = parseFuncArgs('TB', ref)
  if (!args || args.length === 0 || args.some((a) => a === '')) return null
  // code 不能含 '#'（RE_TB code = [^#]+）
  if (args[0].includes('#')) return null
  return `tb://${args[0]}`
}

/** REPORT('code','col') / ROW('code') → report://code */
function reportFormulaRefToUri(ref: string): string | null {
  const args = parseFuncArgs('REPORT', ref) ?? parseFuncArgs('ROW', ref)
  if (!args || args.length === 0 || args.some((a) => a === '')) return null
  if (args[0].includes('#')) return null
  return `report://${args[0]}`
}

/** NOTE('title', ...) → note://title */
function noteFormulaRefToUri(ref: string): string | null {
  const args = parseFuncArgs('NOTE', ref)
  if (!args || args.length === 0 || args.some((a) => a === '')) return null
  return `note://${args[0]}`
}

/** 任一构造点 formula_ref → { domain } | null（null = 非 grammar_v1-valid）。 */
function parseAnyFormulaRef(ref: string): { domain: string } | null {
  const uri =
    wpFormulaRefToUri(ref) ??
    tbFormulaRefToUri(ref) ??
    reportFormulaRefToUri(ref) ??
    noteFormulaRefToUri(ref)
  if (!uri) return null
  const parsed = parseUri(uri) // ← 生产权威文法（grammar_v1）
  return parsed ? { domain: parsed.domain } : null
}

// ─── fast-check 生成器 ─────────────────────────────────────────────────────────

const ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

// wp_code：标准循环码（A-S）+ 数字，或自定义 alnum 码
const wpCodeArb = fc.oneof(
  fc
    .tuple(fc.constantFrom(...'ABCDEFGHIJKLMNS'.split('')), fc.integer({ min: 1, max: 99 }))
    .map(([l, n]) => `${l}${n}`),
  fc
    .array(fc.constantFrom(...(ALPHA.join('') + '0123456789').split('')), {
      minLength: 2,
      maxLength: 8,
    })
    .map((a) => a.join('')),
)
// sheet_code：wp_code + '-' + 数字（不含 '#'）
const sheetCodeArb = fc.tuple(wpCodeArb, fc.integer({ min: 1, max: 40 })).map(([w, n]) => `${w}-${n}`)
// A1 坐标
const cellArb = fc
  .tuple(fc.constantFrom(...ALPHA), fc.integer({ min: 1, max: 9999 }))
  .map(([c, r]) => `${c}${r}`)
// 语义列名（WP 2 参 / TB / REPORT 第二参）
const semanticColArb = fc.constantFrom('审定数', '未审数', '期初', '期末余额', '期末', '本期发生额')
// 会计科目编码（TB code）
const accountCodeArb = fc
  .tuple(fc.constantFrom('1', '2', '3', '4', '5', '6'), fc.integer({ min: 1, max: 9999 }))
  .map(([lead, n]) => `${lead}${String(n).padStart(3, '0')}`)
// 报表行码（REPORT/ROW code）
const reportCodeArb = fc
  .tuple(fc.constantFrom('BS', 'IS', 'CF', 'OE'), fc.integer({ min: 1, max: 999 }))
  .map(([p, n]) => `${p}-${String(n).padStart(3, '0')}`)
// 附注标题/编号（NOTE title）
const noteTitleArb = fc.oneof(
  fc.constantFrom('五、3', '七、1', '（三）', '八', '四-2', '货币资金', '应收账款'),
  fc
    .tuple(fc.constantFrom('三', '四', '五', '六', '七', '八', '九', '十'), fc.integer({ min: 1, max: 30 }))
    .map(([cn, n]) => `${cn}、${n}`),
)

// 六组件会 emit 的全部 formula_ref 形态（单一权威构造生成器）
const anyFormulaRefArb = fc.oneof(
  // 3 参 cell — FormulaRefPicker / FormulaEditDialog / FormulaBar / CellSelector
  fc.tuple(wpCodeArb, sheetCodeArb, cellArb).map(([p, s, c]) => `WP('${p}','${s}','${c}')`),
  // 2 参语义列 — FormulaManagerDialog / FormulaBar（WP(code,审定数)）
  fc.tuple(wpCodeArb, semanticColArb).map(([w, col]) => `WP('${w}','${col}')`),
  // custom_flat（3 参同码）— 自定义单 sheet 底稿
  fc.tuple(wpCodeArb, cellArb).map(([w, c]) => `WP('${w}','${w}','${c}')`),
  // TB 域 — FormulaBar / FormulaManagerDialog
  fc.tuple(accountCodeArb, semanticColArb).map(([code, col]) => `TB('${code}','${col}')`),
  // REPORT 域（2 参）— FormulaBar
  fc.tuple(reportCodeArb, semanticColArb).map(([code, col]) => `REPORT('${code}','${col}')`),
  // ROW 域（1 参）— FormulaBar
  fc.tuple(reportCodeArb).map(([code]) => `ROW('${code}')`),
  // NOTE 域（3 参）— NoteFormulaDialog / FormulaBar
  fc.tuple(noteTitleArb).map(([t]) => `NOTE('${t}','合计','期末')`),
)

// ══════════════════════════════════════════════════════════════════════════════
// Property 26 — Formula-Ref Grammar Closure
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 26 — Formula-Ref Grammar Closure（所有构造点 formula_ref 可被 grammar_v1 解析）', () => {
  it('任一六组件 emit 的 formula_ref 均 grammar_v1-valid（parseUri 非 null）', () => {
    fc.assert(
      fc.property(anyFormulaRefArb, (formulaRef) => {
        const parsed = parseAnyFormulaRef(formulaRef)
        expect(parsed, `formula_ref 未通过 grammar_v1 解析: ${formulaRef}`).not.toBeNull()
      }),
      { numRuns: 200 },
    )
  })

  it('WP 3 参 → wp 域且 round-trip 到 parent/sheet/cell', () => {
    fc.assert(
      fc.property(wpCodeArb, sheetCodeArb, cellArb, (p, s, c) => {
        const parsed = parseAnyFormulaRef(`WP('${p}','${s}','${c}')`)
        expect(parsed).not.toBeNull()
        expect(parsed!.domain).toBe('wp')
      }),
      { numRuns: 60 },
    )
  })

  it('WP custom_flat 3 参同码 → wp 域', () => {
    fc.assert(
      fc.property(wpCodeArb, cellArb, (w, c) => {
        expect(parseAnyFormulaRef(`WP('${w}','${w}','${c}')`)?.domain).toBe('wp')
      }),
      { numRuns: 50 },
    )
  })

  it('WP 2 参语义列 → wp 域', () => {
    fc.assert(
      fc.property(wpCodeArb, semanticColArb, (w, col) => {
        expect(parseAnyFormulaRef(`WP('${w}','${col}')`)?.domain).toBe('wp')
      }),
      { numRuns: 50 },
    )
  })

  it('TB 2 参 → tb 域', () => {
    fc.assert(
      fc.property(accountCodeArb, semanticColArb, (code, col) => {
        expect(parseAnyFormulaRef(`TB('${code}','${col}')`)?.domain).toBe('tb')
      }),
      { numRuns: 50 },
    )
  })

  it('REPORT 2 参 / ROW 1 参 → report 域', () => {
    fc.assert(
      fc.property(reportCodeArb, semanticColArb, (code, col) => {
        expect(parseAnyFormulaRef(`REPORT('${code}','${col}')`)?.domain).toBe('report')
        expect(parseAnyFormulaRef(`ROW('${code}')`)?.domain).toBe('report')
      }),
      { numRuns: 50 },
    )
  })

  it('NOTE 3 参 → note 域', () => {
    fc.assert(
      fc.property(noteTitleArb, (t) => {
        expect(parseAnyFormulaRef(`NOTE('${t}','合计','期末')`)?.domain).toBe('note')
      }),
      { numRuns: 50 },
    )
  })

  it('畸形/空构造 ref 被判为非 grammar_v1-valid（负向）', () => {
    for (const bad of [
      '',
      'WP()',
      "WP('D2')",
      'TB()',
      "REPORT()",
      'ROW()',
      'NOTE()',
      'SUM(A1:A2)',
      'not-a-ref',
      "WP('','','')",
      "TB('','审定数')",
    ]) {
      expect(parseAnyFormulaRef(bad), `期望非法: ${bad}`).toBeNull()
    }
  })
})
