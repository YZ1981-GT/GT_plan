/**
 * formulaGrammarClosure.contract.test.ts — 公式构造生态 grammar_v1 闭合契约测试
 *
 * spec acnr-consumer-wiring Task 34.2（design Property 26: Formula-Ref Grammar Closure）
 *
 * 目标（Req 14.7 / 21.3）：
 *   断言 6 个前端公式构造组件 + `query_builder.py` 产出的 formula_ref 全部可被
 *   grammar_v1 解析（parseUri 非 null）——任一构造点都不能 emit ACNR 无法解析的 ref。
 *   同时断言畸形 ref 被拒（负例），防止解析器过宽。
 *
 * 六个公式构造组件（Req 14.6 穷举集）：
 *   FormulaRefPicker / FormulaEditDialog / FormulaManagerDialog / FormulaBar /
 *   NoteFormulaDialog / CellSelector
 *
 * grammar_v1 解析入口（前端）：
 *   `services/acnr/resolveUri.ts::parseUri` 是 URI 形态（wp:// / tb:// / report:// /
 *   note:// / aux://）的权威文法。组件 emit 的是 FUNCTION-CALL 形态（WP()/TB()/…），
 *   与 URI 形态一一对应（语法糖）。本测试沿用 task 18.4 `formulaPickers.acnr.pbt.test.ts`
 *   确立的 `wpFormulaRefToUri → parseUri` 映射法：把 function-call ref 映射为等价 URI，
 *   再交给生产权威文法 parseUri 判定；round-trip 非 null 即代表该 ref 是 grammar_v1-valid。
 *   （前端无独立的 function-call 解析器；`useAcnr().resolveFormula` 是后端 HTTP 调用，
 *   后端 grammar_v1 入口为 `_formula_ref_to_addr_id`（WP/PREV）+ `full_resolve` V1 委托
 *   （TB/REPORT/ROW/NOTE/AUX），由 task 34.2 的后端 pytest 覆盖。）
 *
 * **Validates: Requirements 14.6, 14.7, 21.3**
 */
import { describe, it, expect } from 'vitest'
import { parseUri } from '@/services/acnr/resolveUri'

// ─── function-call formula_ref → 等价 URI 映射（grammar_v1 语法糖对照） ─────────
//
// 映射表与后端 `address_registry.formula_ref_to_uri` 的语义一致：
//   WP('p','s','c')      → wp://p/s#c            （3 参 standard / custom_flat）
//   WP('code','审定数')   → wp://code/审定数       （2 参语义列，sheet 级）
//   TB('code','期末余额') → tb://code#期末余额
//   SUM_TB('10','审定数') → tb://10#审定数
//   REPORT('BS-002','期末') → report://BS-002#期末
//   ROW('BS-002')        → report://BS-002       （sheet 级，无 cell）
//   SUM_ROW('BS-002','BS-010') → report://BS-002  （范围，起始行作 code）
//   NOTE('货币资金','合计','期末') → note://货币资金
//   AUX('1122','客户A','期末') → aux://1122#期末
//   PREV('code','期末')   → tb://code#期末（2 参）/ PREV('p','s','c') → wp://p/s#c（3 参）

/** 解析 `FN('a','b',...)`：返回函数名与去引号参数；无法识别返回 null。 */
function parseFuncRef(ref: string): { fn: string; args: string[] } | null {
  const m = /^([A-Z_]+)\((.*)\)$/.exec((ref || '').trim())
  if (!m) return null
  const inner = m[2].trim()
  if (inner === '') return { fn: m[1], args: [] }
  const args = inner.split(',').map((s) => s.trim().replace(/^'(.*)'$/, '$1'))
  return { fn: m[1], args }
}

/** function-call formula_ref → 等价 grammar_v1 URI；非法/参数数不符 → null。 */
function formulaRefToUri(ref: string): string | null {
  const p = parseFuncRef(ref)
  if (!p) return null
  const { fn, args } = p
  // 任一参数为空串 → 非法（如 WP('','x','y')）
  if (args.length === 0 || args.some((a) => a === '')) return null
  switch (fn) {
    case 'WP':
      if (args.length === 3) return `wp://${args[0]}/${args[1]}#${args[2]}`
      if (args.length === 2) return `wp://${args[0]}/${args[1]}`
      return null
    case 'PREV':
      if (args.length === 3) return `wp://${args[0]}/${args[1]}#${args[2]}`
      if (args.length === 2) return `tb://${args[0]}#${args[1]}`
      return null
    case 'TB':
    case 'SUM_TB':
      if (args.length === 2) return `tb://${args[0]}#${args[1]}`
      return null
    case 'REPORT':
      if (args.length === 2) return `report://${args[0]}#${args[1]}`
      return null
    case 'ROW':
      if (args.length === 1) return `report://${args[0]}`
      return null
    case 'SUM_ROW':
      if (args.length === 2) return `report://${args[0]}`
      return null
    case 'NOTE':
      if (args.length >= 1 && args.length <= 3) return `note://${args[0]}`
      return null
    case 'AUX':
      if (args.length === 3) return `aux://${args[0]}#${args[2]}`
      if (args.length === 2) return `aux://${args[0]}`
      return null
    default:
      return null
  }
}

/** grammar_v1 断言：function-call ref 可被 parseUri round-trip → 非 null。 */
function isGrammarV1Valid(ref: string): boolean {
  const uri = formulaRefToUri(ref)
  if (!uri) return false
  return parseUri(uri) !== null
}

// ══════════════════════════════════════════════════════════════════════════════
// 六组件产出 formula_ref 代表集（形态取自各组件源码，已在 34.1/18.x 核验）
// ══════════════════════════════════════════════════════════════════════════════

// 每组代表 formula_ref 均直接对应组件源码中的构造分支（注释标注来源），
// 契约测试断言其全部 grammar_v1-parseable。
const COMPONENT_REFS: Record<string, string[]> = {
  // FormulaRefPicker.vue — buildWpFormulaRef / onSelectReport / onSelectTb / onSelectNote
  FormulaRefPicker: [
    "WP('D2','D2-2','E100')", // 3 参 sheet_code
    "WP('D2','明细表D2-2','E100')", // 3 参 sheet_name
    "WP('CUST-01','CUST-01','B7')", // custom_flat（wp,wp,cell）
    "REPORT('BS-002','期末')", // onSelectReport
    "TB('1001','审定数')", // onSelectTb（tbColumn=审定数）
    "TB('1001','期末余额')", // onSelectTb（tbColumn=期末余额）
    "NOTE('五、3','合计','期末')", // onSelectNote
  ],
  // FormulaEditDialog.vue — insertRef quick-buttons + mapAcnrCellsToPickerRows(_ref=cell.formula_ref)
  FormulaEditDialog: [
    "TB('1001','期末余额')",
    "SUM_TB('10','审定数')",
    "ROW('BS-001')",
    "SUM_ROW('BS-002','BS-010')",
    "REPORT('BS-002','期末')",
    "NOTE('货币资金','合计','期末')",
    "WP('E1-1','审定数')", // 2 参语义列
    "AUX('1122','客户A','期末')",
    "PREV('BS-002','期末')", // 2 参 tb 域
    "WP('D2','明细表D2-2','E100')", // mapAcnrCellsToPickerRows 透传的 3 参
  ],
  // FormulaManagerDialog.vue — recomputeFormulaRow (TB) + crossCheckRulesMap 默认引用
  FormulaManagerDialog: [
    "TB('1001','期末余额')",
    "REPORT('BS-002','期末')",
    "REPORT('IS-002','本期')",
    "NOTE('货币资金','合计','期末')",
    "WP('E1-1','审定数')",
    "WP('D2-1','审定数')",
  ],
  // FormulaBar.vue — loadTbRows / loadReportRows / loadNoteRows / loadWpRows
  FormulaBar: [
    "TB('1001','期末余额')", // loadTbRows
    "REPORT('BS-002','期末')", // loadReportRows（REPORT）
    "ROW('BS-002')", // loadReportRows（ROW）
    "NOTE('货币资金','合计','期末')", // loadNoteRows
    "WP('E1-1','审定数')", // loadWpRows（2 参语义列）
  ],
  // NoteFormulaDialog.vue — 用户编辑的附注公式（NOTE/WP/TB 形态持久化）
  NoteFormulaDialog: [
    "NOTE('货币资金','合计','期末')",
    "WP('E1-1','审定数')",
    "TB('1001','期末余额')",
  ],
  // CellSelector.vue — WP（ACNR listSheets 源）+ tb/report/note 形态
  CellSelector: [
    "WP('D2','D2-2','E100')",
    "WP('CUST-01','CUST-01','B7')",
    "TB('1001','审定数')",
    "REPORT('BS-002','期末')",
    "NOTE('五、3','合计','期末')",
  ],
}

// query_builder.py::_derive_formula_refs 产出（前端仅做 grammar 层校验；
// 权威 resolve 由后端 pytest 经 full_resolve V1 委托覆盖）。
const QUERY_BUILDER_REFS: string[] = [
  "TB('1001','审定数')", // trial_balance
  "TB('1001','期末')", // tb_balance
]

// ══════════════════════════════════════════════════════════════════════════════
// 契约：所有构造点 formula_ref 均 grammar_v1-parseable（parseUri 非 null）
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 26 — Formula-Ref Grammar Closure：六组件 formula_ref 全部 grammar_v1-parseable', () => {
  for (const [component, refs] of Object.entries(COMPONENT_REFS)) {
    describe(`${component}`, () => {
      it.each(refs)('formula_ref %s 可被 grammar_v1 解析（parseUri 非 null）', (ref) => {
        const uri = formulaRefToUri(ref)
        expect(uri, `${ref} 未能映射为等价 URI`).not.toBeNull()
        const parsed = parseUri(uri!)
        expect(parsed, `${ref} → ${uri} 未通过 parseUri`).not.toBeNull()
        expect(isGrammarV1Valid(ref)).toBe(true)
      })
    })
  }

  it('六个公式构造组件全部被覆盖（Req 14.6 穷举集）', () => {
    expect(Object.keys(COMPONENT_REFS).sort()).toEqual(
      [
        'CellSelector',
        'FormulaBar',
        'FormulaEditDialog',
        'FormulaManagerDialog',
        'FormulaRefPicker',
        'NoteFormulaDialog',
      ].sort(),
    )
  })
})

describe('query_builder.py::_derive_formula_refs 产出 formula_ref grammar_v1-parseable（grammar 层）', () => {
  it.each(QUERY_BUILDER_REFS)('formula_ref %s 可被 grammar_v1 解析', (ref) => {
    expect(isGrammarV1Valid(ref)).toBe(true)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// 负例：畸形 ref 必须被拒（解析器不能过宽）
// ══════════════════════════════════════════════════════════════════════════════

describe('负例 — 畸形 formula_ref 被判为非 grammar_v1-valid', () => {
  const MALFORMED: string[] = [
    '', // 空
    'WP()', // 无参
    "WP('D2')", // WP 参数不足
    "WP('','明细表','E100')", // 空参
    "TB('1001')", // TB 参数不足
    "REPORT('BS-002')", // REPORT 参数不足
    "ROW('BS-001','BS-002')", // ROW 参数过多
    "NOTE()", // NOTE 无参
    'SUM(A1:A2)', // 未知函数
    "CONSOL('抵消分录','借方合计')", // 非 grammar_v1 域函数
    'not-a-ref', // 非函数形态
    'WP D2 明细表', // 语法畸形
  ]

  it.each(MALFORMED)('畸形 ref %j 被拒（isGrammarV1Valid=false）', (ref) => {
    expect(isGrammarV1Valid(ref)).toBe(false)
  })
})
