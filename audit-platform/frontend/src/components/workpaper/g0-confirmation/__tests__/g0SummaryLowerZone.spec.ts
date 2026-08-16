/**
 * g0SummaryLowerZone.spec.ts — G0-1 下区四块 + 样本选择 6 项守卫
 *
 * spec: g0-confirmation-source-alignment，Task 8/9/13
 *
 * Property 8  —— 下区文字与源模板逐字一致，且「跨格拼接」只有 X21+X22 一处
 * Property 9  —— 样本选择 6 项字段与替代程序族 `SamplingConfig` 同源、旧字段零丢失
 * Property 31 —— 6 项由 `isG0` 门控，其余六枢纽仍渲染 4 项（含反向自检）
 * Property 13 —— 新建件均有非测试消费方（零消费方 = 未交付）
 * 双真源守卫 —— `G0SummaryLowerZone.vue` 不得录入任何 sampling 字段
 *
 * 🔴 裁决者 = 源模板 xlsx 本体（SheetJS 直读），不是任何中间产物。
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import XLSX from 'xlsx'
import { describe, expect, it } from 'vitest'

import {
  CONVERGENCE_TARGET,
  G0_AI_SECTIONS,
  G0_AUDIT_NOTE_DEFS,
  G0_CONCLUSION_KEY,
  G0_LEGACY_SAMPLING_FIELD_MAP,
  G0_LOWER_ITEM_IDS,
  G0_LOWER_KEY_PREFIX,
  G0_LOWER_ZONE_BLOCKS,
  G0_LOWER_ZONE_TEXTS,
  G0_PREPARATION_NOTES,
  G0_REF_CONCLUSIONS,
  G0_REF_CONCLUSION_HEADING,
  G0_SAMPLE_SELECTION_DEFS,
  G0_SAMPLE_SELECTION_HINTS,
  G0_SOURCE_REF_PREFIX,
  g0AuditNoteItemId,
  getG0LowerBlock,
} from '../g0SummaryLowerZone'
import ConfirmationSampling from '../../confirmation/ConfirmationSampling.vue'

// ─── 仓库根：哨兵**文件**向上查找（不写死回退层数） ──────────────────────────
// 🔴 哨兵必须是具体文件 —— 用目录会在 `audit-platform/` 层提前命中（那里有历史遗留同名空目录）。

const SENTINEL = join('.kiro', 'steering', 'memory.md')

function findRepoRoot(from: string): string {
  let cur = from
  for (let i = 0; i < 12; i++) {
    if (existsSync(join(cur, SENTINEL))) return cur
    const up = dirname(cur)
    if (up === cur) break
    cur = up
  }
  throw new Error(`[g0SummaryLowerZone.spec] 未找到仓库根（哨兵 ${SENTINEL}），起点 ${from}`)
}

const REPO_ROOT = findRepoRoot(__dirname)
const FRONTEND_SRC = resolve(__dirname, '../../../..')
const G0_XLSX = join(REPO_ROOT, 'backend', 'wp_templates', 'G', 'G0 投资循环函证.xlsx')
const SHEET_SUMMARY = '函证结果汇总表G0-1'

const LOWER_TS = readFileSync(resolve(__dirname, '../g0SummaryLowerZone.ts'), 'utf-8')
const LOWER_VUE = readFileSync(resolve(__dirname, '../G0SummaryLowerZone.vue'), 'utf-8')
const SAMPLING_VUE = readFileSync(
  resolve(__dirname, '../../confirmation/ConfirmationSampling.vue'),
  'utf-8',
)
const SUMMARY_VUE = readFileSync(
  resolve(__dirname, '../../confirmation/GtConfirmationSummary.vue'),
  'utf-8',
)

// ─── 源模板读取 ──────────────────────────────────────────────────────────────

const wb = XLSX.readFile(G0_XLSX)
const ws = wb.Sheets[SHEET_SUMMARY]

function cell(coord: string): string {
  const v = ws?.[coord]?.v
  return v === undefined || v === null ? '' : String(v)
}

// ─── 源码读取工具 ────────────────────────────────────────────────────────────

/** 去注释（块注释 + 行注释 + HTML 注释），保留字符串字面量 */
function stripComments(s: string): string {
  return s
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 按花括号配对截取函数体（不用固定字符窗口，避免溢出到下一个函数） */
function functionBody(src: string, name: string): string {
  const decl = src.indexOf(`function ${name}(`)
  expect(decl, `未找到 function ${name}`).toBeGreaterThan(-1)
  const open = src.indexOf('{', decl)
  expect(open, `function ${name} 未找到函数体起始 {`).toBeGreaterThan(-1)
  let depth = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) return src.slice(open + 1, i)
    }
  }
  throw new Error(`function ${name} 花括号未配对`)
}

// ─── 环境自检（防守卫本身空转） ───────────────────────────────────────────────

describe('守卫自检', () => {
  it('仓库根与源模板可定位，且 sheet 存在', () => {
    expect(existsSync(G0_XLSX), `源模板不存在: ${G0_XLSX}`).toBe(true)
    expect(wb.SheetNames).toContain(SHEET_SUMMARY)
    expect(wb.SheetNames.length).toBe(10)
  })

  it('SheetJS 读到的是中文原文（不是空/乱码占位）', () => {
    expect(cell('C19')).toBe('一、函证情况')
    expect(cell('C19').length).toBe(6)
  })

  it('stripComments 对内联 fixture 有效（不依赖真实文件恰好含反例）', () => {
    const fixture = [
      'const a = 1 // 注释里的 v-model="sample_size"',
      '/* 块注释 test_scope */',
      '<!-- HTML 注释 test_scope -->',
      `const b = 'keep test_population'`,
    ].join('\n')
    const out = stripComments(fixture)
    expect(out).not.toContain('注释里的')
    expect(out).not.toContain('块注释')
    expect(out).not.toContain('HTML 注释')
    expect(out).toContain(`'keep test_population'`)
  })

  it('functionBody 用花括号配对截取（内联 fixture 反向自检）', () => {
    const fixture = 'function target() {\n  if (x) { y() }\n  return 1\n}\nfunction other() { return 2 }'
    const body = functionBody(fixture, 'target')
    expect(body).toContain('return 1')
    expect(body).not.toContain('return 2')
  })

  it('四个源文件均已读到非空内容', () => {
    for (const [name, src] of [
      ['g0SummaryLowerZone.ts', LOWER_TS],
      ['G0SummaryLowerZone.vue', LOWER_VUE],
      ['ConfirmationSampling.vue', SAMPLING_VUE],
      ['GtConfirmationSummary.vue', SUMMARY_VUE],
    ] as const) {
      expect(src.length, `${name} 读取为空`).toBeGreaterThan(500)
    }
  })
})

// ─── Property 8: 下区文字与源模板逐字一致 ─────────────────────────────────────

describe('Property 8: 下区四块文字与源模板逐字一致且跨格已合并', () => {
  it('四块锚点与标题逐字（C19 / J19 / S19 / C30）', () => {
    expect(G0_LOWER_ZONE_BLOCKS.map((b) => b.anchor)).toEqual(['C19', 'J19', 'S19', 'C30'])
    for (const b of G0_LOWER_ZONE_BLOCKS) {
      expect(cell(b.anchor), `块 ${b.key} 锚点 ${b.anchor}`).toBe(b.title)
    }
  })

  it('「二、样本选择」块声明为不在本组件渲染（归 Task 13）', () => {
    expect(getG0LowerBlock('sample_selection').renderedHere).toBe(false)
    for (const key of ['matrix', 'audit_note', 'conclusion'] as const) {
      expect(getG0LowerBlock(key).renderedHere).toBe(true)
    }
  })

  it('审计说明 5 项：每项 title 与**单一**源格逐字相等', () => {
    expect(G0_AUDIT_NOTE_DEFS.length).toBe(5)
    expect(G0_AUDIT_NOTE_DEFS.map((d) => d.titleAnchor)).toEqual(['S20', 'X20', 'S24', 'S25', 'S28'])
    for (const d of G0_AUDIT_NOTE_DEFS) {
      expect(d.titleAnchor).not.toContain('+') // title 永远单格
      expect(cell(d.titleAnchor), `第 ${d.seq} 项标题`).toBe(d.title)
    }
  })

  it('审计说明 title 序号连续 1..5 且与文字前缀一致', () => {
    G0_AUDIT_NOTE_DEFS.forEach((d, i) => {
      expect(d.seq).toBe(i + 1)
      expect(d.title.startsWith(`${d.seq}、`)).toBe(true)
    })
  })

  it('全下区**唯一**需要拼接的 hint 是 X21+X22', () => {
    const concatenated = G0_LOWER_ZONE_TEXTS.filter((t) => t.anchor.includes('+'))
    expect(concatenated.length).toBe(1)
    expect(concatenated[0].role).toBe('hint')
    expect(concatenated[0].anchor).toBe('X21+X22')
    expect(concatenated[0].text).toBe(cell('X21') + cell('X22'))
  })

  it('拼接结果不以标点开头（防半句话），且两半确实是被拆开的一句', () => {
    const hint = G0_AUDIT_NOTE_DEFS.find((d) => d.seq === 2)!.hint!
    expect(hint).toBe(cell('X21') + cell('X22'))
    expect(/^[，。、；：！？）」』\]),.;:!?]/.test(hint)).toBe(false)
    expect(cell('X21').endsWith('人民币')).toBe(true)
    expect(cell('X22').startsWith('（）万元')).toBe(true)
  })

  it('S26 是独立提示语（单格），未与 S25 拼接', () => {
    const d4 = G0_AUDIT_NOTE_DEFS.find((d) => d.seq === 4)!
    expect(d4.hintAnchor).toBe('S26')
    expect(d4.hint).toBe(cell('S26'))
    expect(d4.title).toBe(cell('S25'))
  })

  it('反向自检：禁止的错误拼接不会出现在任何声明里', () => {
    const wrongMismatch = cell('S25') + cell('S26') // 「4、针对不符事项的程序如果回函中…」
    const wrongError = cell('X20') + cell('X21') + cell('X22')
    const allTexts = [
      ...G0_LOWER_ZONE_TEXTS.map((t) => t.text),
      ...G0_AUDIT_NOTE_DEFS.map((d) => d.title),
      ...G0_AUDIT_NOTE_DEFS.map((d) => d.hint ?? ''),
    ]
    expect(wrongMismatch.length).toBeGreaterThan(20) // 自检：反例本身非空
    expect(allTexts).not.toContain(wrongMismatch)
    expect(allTexts).not.toContain(wrongError)
  })

  it('只有 role==="hint" 的条目允许多格拼接', () => {
    for (const t of G0_LOWER_ZONE_TEXTS) {
      if (t.role === 'title') expect(t.anchor, `${t.key} 标题不得拼接`).not.toContain('+')
    }
  })

  it('每条 source_ref == "G0-1!" + anchor（防两字段漂移）', () => {
    for (const t of G0_LOWER_ZONE_TEXTS) {
      expect(t.source_ref).toBe(`${G0_SOURCE_REF_PREFIX}${t.anchor}`)
    }
    for (const b of G0_LOWER_ZONE_BLOCKS) {
      expect(b.source_ref).toBe(`${G0_SOURCE_REF_PREFIX}${b.anchor}`)
    }
    for (const r of G0_REF_CONCLUSIONS) {
      expect(r.source_ref).toBe(`${G0_SOURCE_REF_PREFIX}${r.anchor}`)
    }
  })

  it('参考结论 A/B/C 的**内容取自 B 列**，A 列只是标签', () => {
    expect(G0_REF_CONCLUSIONS.map((r) => r.anchor)).toEqual(['B55', 'B56', 'B57'])
    expect(G0_REF_CONCLUSIONS.map((r) => r.labelAnchor)).toEqual(['A55', 'A56', 'A57'])
    for (const r of G0_REF_CONCLUSIONS) {
      expect(cell(r.anchor), `参考结论 ${r.code} 内容`).toBe(r.text)
      expect(cell(r.labelAnchor), `参考结论 ${r.code} 标签`).toBe(`${r.code}、`)
      // 反向自检：A 列确实不是内容（长度恰为 2 个字符的标签）
      expect(cell(r.labelAnchor).length).toBe(2)
    }
    expect(cell(G0_REF_CONCLUSION_HEADING.anchor)).toBe(G0_REF_CONCLUSION_HEADING.text)
  })

  it('编制说明每一行与源格逐字相等', () => {
    for (const note of G0_PREPARATION_NOTES) {
      for (const line of note.lines) {
        expect(cell(line.anchor), `${note.key} @ ${line.anchor}`).toBe(line.text)
      }
    }
  })

  it('函证注意事项 8 条取自 **B44:B51**（A43 只是标题）', () => {
    const cautions = G0_PREPARATION_NOTES.find((n) => n.key === 'confirmation_cautions')!
    const anchors = cautions.lines.map((l) => l.anchor)
    expect(anchors[0]).toBe('A43')
    expect(cell('A43')).toBe('2、函证注意事项：')
    expect(anchors.slice(1)).toEqual(['B44', 'B45', 'B46', 'B47', 'B48', 'B49', 'B50', 'B51'])
    // 反向自检：A44..A51 是空的 —— 只扫 A 列的探针会整段漏掉这 8 条
    for (const c of ['A44', 'A45', 'A46', 'A47', 'A48', 'A49', 'A50', 'A51']) {
      expect(cell(c), `${c} 应为空（8 条正文在 B 列）`).toBe('')
    }
    // 8 条均以 ①..⑧ 序号开头
    const marks = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧']
    cautions.lines.slice(1).forEach((l, i) => {
      expect(l.text.startsWith(marks[i])).toBe(true)
    })
  })

  it('准则 1312 六项的全角缩进逐字保留（A38~A42）', () => {
    const std = G0_PREPARATION_NOTES.find((n) => n.key === 'sample_selection_standard')!
    const byAnchor = new Map(std.lines.map((l) => [l.anchor, l.text]))
    expect(byAnchor.get('A37')!.startsWith('（一）')).toBe(true) // 第一项无缩进（源模板事实）
    for (const c of ['A38', 'A39', 'A40', 'A41', 'A42']) {
      expect(byAnchor.get(c)!.startsWith('\u3000\u3000'), `${c} 应保留两个全角空格`).toBe(true)
      expect(byAnchor.get(c)).toBe(cell(c))
    }
  })

  it('声明了 CONVERGENCE_TARGET（收敛 spec 靠 grep 定位副本）', () => {
    expect(CONVERGENCE_TARGET).toBe('confirmation-summary-lower-zone-convergence')
    expect(LOWER_VUE).toContain('confirmation-summary-lower-zone-convergence')
  })

  it('下区录入键与既有 sampling/矩阵键均不冲突（R3.11）', () => {
    expect(G0_LOWER_KEY_PREFIX).toBe('G0-1-lower-')
    expect(G0_LOWER_ITEM_IDS.length).toBe(6) // 5 段审计说明 + 1 结论
    expect(new Set(G0_LOWER_ITEM_IDS).size).toBe(G0_LOWER_ITEM_IDS.length)
    for (const id of G0_LOWER_ITEM_IDS) {
      expect(id.startsWith(G0_LOWER_KEY_PREFIX)).toBe(true)
      expect(id).not.toBe('G0-1-sampling')
      expect(id.startsWith('G0-1-matrix-')).toBe(false)
    }
    expect(g0AuditNoteItemId(3)).toBe('G0-1-lower-audit-note-3')
    expect(G0_CONCLUSION_KEY).toBe('G0-1-lower-conclusion')
  })

  it('复核入口真挂：5 段 + 结论各有 GtReviewTrigger 的 section-id', () => {
    expect(LOWER_VUE).toContain('GtReviewTrigger')
    const clean = stripComments(LOWER_VUE)
    expect(clean).toContain(':section-id="d.reviewSectionId"')
    expect(clean).toContain('CONCLUSION_REVIEW_SECTION_ID')
    G0_AUDIT_NOTE_DEFS.forEach((d) => {
      expect(d.reviewSectionId).toBe(`G0-1-audit-note-${d.seq}`)
    })
    expect(G0_AI_SECTIONS.length).toBe(6)
    expect(new Set(G0_AI_SECTIONS).size).toBe(6)
  })

  it('编制说明以只读折叠（details）展示，不让审计师翻源 xlsx（R3.10）', () => {
    const clean = stripComments(LOWER_VUE)
    expect(clean).toContain('<details')
    expect(clean).toContain('PREPARATION_NOTES')
  })

  it('取数错误有渲染出口（不能只收集不显示）', () => {
    const clean = stripComments(LOWER_VUE)
    expect(clean).toContain('bookErrors')
    expect(/v-if="bookErrors\.length"/.test(clean)).toBe(true)
    expect(clean).toContain('diagnostics?.errors')
  })

  it('账面金额可编辑走 WpAmountInput，且组件不用 el-input-number', () => {
    const clean = stripComments(LOWER_VUE)
    expect(clean).toContain('WpAmountInput')
    expect(clean).not.toContain('el-input-number')
  })

  it('fmtAmount 走 store 成员（禁模块级命名导入）', () => {
    expect(LOWER_VUE).not.toMatch(/import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from\s*'@\/stores\/displayPrefs'/)
    expect(LOWER_VUE).toContain('displayPrefs.fmtAmount(')
    expect(LOWER_VUE).toContain('useDisplayPrefsStore()')
  })

  it('模板属性不含中文引号（U+201C/201D 会让 Vite 编译崩溃）', () => {
    const templateEnd = LOWER_VUE.indexOf('</template>')
    const tpl = LOWER_VUE.slice(0, templateEnd)
    expect(/[\u201c\u201d]/.test(tpl)).toBe(false)
  })

  it('组件不在取数结果上补 ?? 0（会把「无此科目」压成假 0）', () => {
    const clean = stripComments(LOWER_VUE)
    expect(clean).not.toMatch(/bookAmounts\s*\?\?\s*\{\}/)
    expect(clean).not.toMatch(/tb_amount\s*\?\?\s*0/)
  })
})

// ─── 双真源守卫：下区组件不得录入 sampling 字段 ───────────────────────────────

const SIX_SAMPLING_FIELDS = [
  'test_population',
  'specific_samples',
  'sampling_population',
  'sample_size',
  'sampling_method',
  'sampling_process',
] as const

describe('双真源守卫: G0SummaryLowerZone.vue 不承担样本选择录入', () => {
  it('组件源码不含 6 个 sampling 字段任一的 v-model', () => {
    const clean = stripComments(LOWER_VUE)
    for (const f of SIX_SAMPLING_FIELDS) {
      expect(new RegExp(`v-model[^=]*="[^"]*\\b${f}\\b`).test(clean), `不应 v-model 绑定 ${f}`).toBe(false)
      expect(new RegExp(`v-model[^=]*='[^']*\\b${f}\\b`).test(clean)).toBe(false)
    }
  })

  it('组件不渲染「二、样本选择」块（不引用 sample_selection 声明）', () => {
    const clean = stripComments(LOWER_VUE)
    expect(clean).not.toContain('G0_SAMPLE_SELECTION_DEFS')
    expect(clean).not.toContain('G0_SAMPLE_SELECTION_HINTS')
    expect(clean).not.toContain("getG0LowerBlock('sample_selection')")
  })

  it('反向自检：这 6 个字段确实被另一处（ConfirmationSampling）消费', () => {
    expect(SAMPLING_VUE).toContain('G0_SAMPLE_SELECTION_DEFS')
    expect(SAMPLING_VUE).toContain('G0_SAMPLE_SELECTION_HINTS')
  })

  it('6 项文字真源只导出一份（组件不抄第二份中文）', () => {
    for (const def of G0_SAMPLE_SELECTION_DEFS) {
      expect(SAMPLING_VUE, `不得在组件里抄 placeholder: ${def.field}`).not.toContain(def.placeholder)
      expect(LOWER_VUE).not.toContain(def.placeholder)
    }
    for (const h of G0_SAMPLE_SELECTION_HINTS) {
      expect(SAMPLING_VUE).not.toContain(h.text)
    }
  })
})

// ─── Property 9: 样本选择 6 项与替代程序族同源 ────────────────────────────────

/** `SamplingConfig` 的 5 个同义字段（源自 alternativeD05Types.ts） */
const SAMPLING_CONFIG_SHARED = [
  'specific_samples',
  'sampling_population',
  'sample_size',
  'sampling_method',
  'sampling_process',
] as const

describe('Property 9: 样本选择 6 项字段与 SamplingConfig 同源', () => {
  it('6 项字段集合 == SamplingConfig 5 字段 ∪ {test_population}', () => {
    const declared = G0_SAMPLE_SELECTION_DEFS.map((d) => d.field)
    expect(declared.length).toBe(6)
    expect(new Set(declared).size).toBe(6)
    for (const f of SAMPLING_CONFIG_SHARED) {
      expect(declared, `缺少 SamplingConfig 字段 ${f}`).toContain(f)
    }
    expect(declared).toContain('test_population')
    expect(new Set(declared)).toEqual(new Set([...SAMPLING_CONFIG_SHARED, 'test_population']))
  })

  it('SamplingConfig 真源里确有这 5 个字段（跨文件交叉锁死）', () => {
    const typesSrc = readFileSync(
      resolve(__dirname, '../../confirmation/alternativeD05/alternativeD05Types.ts'),
      'utf-8',
    )
    const iface = typesSrc.slice(
      typesSrc.indexOf('export interface SamplingConfig'),
      typesSrc.indexOf('BalanceSummary'),
    )
    expect(iface.length).toBeGreaterThan(100)
    for (const f of SAMPLING_CONFIG_SHARED) {
      expect(iface, `SamplingConfig 应含 ${f}`).toContain(`${f}?:`)
    }
    // 反向自检：test_scope 确实存在于 SamplingConfig（证明「不复用它」是有意选择）
    expect(iface).toContain('test_scope?:')
    expect(iface).not.toContain('test_population?:')
  })

  it('test_population ≠ test_scope，且组件不使用 test_scope', () => {
    const declared = G0_SAMPLE_SELECTION_DEFS.map((d) => String(d.field))
    expect(declared).not.toContain('test_scope')
    expect(stripComments(SAMPLING_VUE)).not.toContain('test_scope')
    expect(stripComments(LOWER_TS)).not.toContain("'test_scope'")
  })

  it('旧 4 字段**每个都有落点**（数据零丢失）', () => {
    const legacyRendered = ['sampling_method', 'sampling_size', 'sampling_criteria', 'sampling_conclusion']
    for (const old of legacyRendered) {
      expect(Object.keys(G0_LEGACY_SAMPLING_FIELD_MAP), `旧字段 ${old} 无落点`).toContain(old)
      expect(G0_LEGACY_SAMPLING_FIELD_MAP[old]).toBeTruthy()
    }
    expect(G0_LEGACY_SAMPLING_FIELD_MAP.sampling_size).toBe('sample_size')
    expect(G0_LEGACY_SAMPLING_FIELD_MAP.sampling_criteria).toBe('specific_samples')
    expect(G0_LEGACY_SAMPLING_FIELD_MAP.sampling_method).toBe('sampling_method')
    // 源模板无对应项 → 作源外增强字段原样保留（不迁移不丢弃）
    expect(G0_LEGACY_SAMPLING_FIELD_MAP.sampling_conclusion).toBe('sampling_conclusion')
  })

  it('组件的读回映射与声明一致（花括号配对截 valueOf 函数体）', () => {
    const body = functionBody(SAMPLING_VUE, 'valueOf')
    expect(body).toContain('LEGACY_FALLBACK')
    // 旧值回落只在新字段为空时生效（手工新值优先）
    expect(body).toMatch(/own\s*!==\s*undefined/)
    const clean = stripComments(SAMPLING_VUE)
    const fbBlock = clean.slice(clean.indexOf('LEGACY_FALLBACK'), clean.indexOf('function valueOf'))
    expect(fbBlock).toContain('sampling_size')
    expect(fbBlock).toContain('sampling_criteria')
  })

  it('6 项标签与 placeholder 逐字取自源模板（J 列 / K 列）', () => {
    expect(G0_SAMPLE_SELECTION_DEFS.map((d) => d.labelAnchor)).toEqual([
      'J20', 'J21', 'J22', 'J23', 'J25', 'J26',
    ])
    expect(G0_SAMPLE_SELECTION_DEFS.map((d) => d.placeholderAnchor)).toEqual([
      'K20', 'K21', 'K22', 'K23', 'K25', 'K26',
    ])
    for (const d of G0_SAMPLE_SELECTION_DEFS) {
      // 源模板标签带尾冒号，声明侧去掉
      expect(cell(d.labelAnchor), `标签 ${d.labelAnchor}`).toBe(`${d.label}：`)
      expect(cell(d.placeholderAnchor), `placeholder ${d.placeholderAnchor}`).toBe(d.placeholder)
    }
  })

  it('K24 / K27 作只读补充提示，未混进 placeholder', () => {
    expect(G0_SAMPLE_SELECTION_HINTS.map((h) => h.anchor)).toEqual(['K24', 'K27'])
    for (const h of G0_SAMPLE_SELECTION_HINTS) {
      expect(cell(h.anchor)).toBe(h.text)
    }
    // 反向自检：不得与 K23/K26 拼成 placeholder
    const sizeDef = G0_SAMPLE_SELECTION_DEFS.find((d) => d.field === 'sample_size')!
    const procDef = G0_SAMPLE_SELECTION_DEFS.find((d) => d.field === 'sampling_process')!
    expect(sizeDef.placeholder).not.toContain('样本计算器')
    expect(procDef.placeholder).not.toContain('抽样工具中的样本选择过程')
  })

  it('抽样方法做成点选（源 K25 本就是斜杠分隔备选项）', () => {
    const m = G0_SAMPLE_SELECTION_DEFS.find((d) => d.field === 'sampling_method')!
    expect(m.options).toEqual(['随机选样', '系统选样', '货币单元抽样', '随意选样'])
    expect(cell('K25').split('/')).toEqual([...m.options!])
  })
})

// ─── Property 31: isG0 门控 ──────────────────────────────────────────────────

describe('Property 31: 样本选择 6 项由 isG0 门控且六枢纽渲染不变', () => {
  it('源码级：存在 cycle prop 与 isG0 判定', () => {
    const clean = stripComments(SAMPLING_VUE)
    expect(clean).toMatch(/cycle\?\:\s*ConfirmCycle/)
    expect(clean).toMatch(/const\s+isG0\s*=\s*computed\(\(\)\s*=>\s*props\.cycle\s*===\s*'G0'\)/)
  })

  /**
   * 🔴 改写记录（k0-confirmation-source-alignment Task 10，2026-08-07）
   *
   * 原断言按**门控表达式字面** `<el-form v-if="isG0"` 定位 6 项块。K0 收口后该门控
   * 归一为 `v-if="useSourceSix"`（G0 与 K0 共用同一表单块，各自 import 自己的文字真源），
   * 原字面必然找不到 ⇒ 这是「守卫锁了实现细节而非行为」，不是回归。
   *
   * 改为：门控存在性 + 与 `v-else` 互斥 + **`useSourceSix` 由 `isG0` 参与计算**
   * （后者才是 R3.6.2 的实质要求：G0 走 6 项、未声明的枢纽走 4 项）。
   * 挂载渲染那两条（`cycle="G0"` → 6 项 / `cycle="D0"` → 4 项）是行为级判据，未受影响。
   */
  it('源码级：6 项渲染块由门控守住、4 项在 v-else 分支（互斥），且门控由 isG0 参与计算', () => {
    const clean = stripComments(SAMPLING_VUE)
    const gateIdx = clean.indexOf('<el-form v-if="useSourceSix"')
    const elseIdx = clean.indexOf('<el-form v-else')
    expect(gateIdx, '未找到 6 项块的门控 el-form（v-if="useSourceSix"）').toBeGreaterThan(-1)
    expect(elseIdx, '未找到 v-else 的既有 4 项 el-form').toBeGreaterThan(gateIdx)
    const gateBlock = clean.slice(gateIdx, elseIdx)
    // 6 项块遍历归一后的 defs（G0/K0 各自的文字真源在 script 里归一）
    expect(gateBlock).toContain('sourceSixDefs')
    // 🔴 门控必须真的由 isG0 决定（否则 G0 走不进 6 项分支）
    expect(clean).toMatch(/useSourceSix\s*=\s*computed\(\(\)\s*=>\s*sourceSixDefs\.value\.length\s*>\s*0\)/)
    expect(clean).toMatch(/if\s*\(isG0\.value\)/)
    expect(clean).toContain('G0_SAMPLE_DEFS')
    // 4 项分支不得出现 6 项字段
    const legacyBlock = clean.slice(elseIdx)
    for (const f of ['test_population', 'sampling_population', 'sampling_process']) {
      expect(legacyBlock, `既有 4 项分支不应出现 ${f}`).not.toContain(f)
    }
  })

  it('源码级：门控只在渲染层 —— emit 不按枢纽分叉（R3.6.3）', () => {
    const clean = stripComments(SAMPLING_VUE)
    // 模板内 isG0 只出现在两处门控（v-if / 若有额外使用即打红）
    const occurrences = (clean.match(/isG0/g) ?? []).length
    // 1 次 computed 声明 + 1 次 v-if 使用
    expect(occurrences).toBe(2)
    // emit 语句里不含 cycle / isG0 条件
    const emits = clean.match(/\$emit\('update',[^)]*\)/g) ?? []
    expect(emits.length).toBeGreaterThanOrEqual(5)
    for (const e of emits) {
      expect(e).not.toContain('isG0')
      expect(e).not.toContain('cycle')
    }
  })

  it('宿主确实传了 cycle（且 prop 名从 defineProps 动态抽取比对）', () => {
    // 从被调组件 defineProps 抽合法 prop 名（传不存在的 prop = 静默失效）
    const propsBlock = SAMPLING_VUE.slice(
      SAMPLING_VUE.indexOf('defineProps<{'),
      SAMPLING_VUE.indexOf('defineEmits<{'),
    )
    expect(propsBlock.length).toBeGreaterThan(50)
    const legalProps = new Set(
      [...stripComments(propsBlock).matchAll(/^\s{2}(\w+)\??\:/gm)].map((m) => m[1]),
    )
    expect(legalProps.has('cycle'), `defineProps 未声明 cycle：${[...legalProps].join(',')}`).toBe(true)

    // 调用点属性 ⊆ 合法 prop 名
    const callIdx = SUMMARY_VUE.indexOf('<ConfirmationSampling')
    expect(callIdx).toBeGreaterThan(-1)
    const callBlock = SUMMARY_VUE.slice(callIdx, SUMMARY_VUE.indexOf('/>', callIdx))
    expect(callBlock).toContain(':cycle="confirmCycle"')
    // 只取 prop 位（`:x=` 与裸 `x=`）—— `@x=` 是事件监听，不参与 prop 名比对
    const passed = [
      ...callBlock.matchAll(/(^|\s)(:?)([a-z][a-z0-9-]*)=/g),
    ]
      .filter((m) => !m[0].includes('@'))
      .map((m) => m[3])
    expect(passed.length).toBeGreaterThan(2) // 自检：确实抽到了 prop
    const camel = (s: string) => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase())
    for (const p of passed) {
      if (p.startsWith('v-') || ['key', 'ref', 'class', 'style'].includes(p)) continue
      expect(legalProps.has(camel(p)), `传了不存在的 prop: ${p}`).toBe(true)
    }
  })

  it('挂载渲染：cycle="G0" 显示源模板 6 项（+1 源外增强）', () => {
    const wrapper = mount(ConfirmationSampling, {
      props: { data: {}, readonly: false, dictData: {}, cycle: 'G0' as const },
      global: { plugins: [ElementPlus] },
    })
    const labels = wrapper.findAll('.el-form-item__label').map((n) => n.text().replace(/：$/, ''))
    const sourceLabels = G0_SAMPLE_SELECTION_DEFS.map((d) => d.label)
    for (const l of sourceLabels) expect(labels, `缺少 ${l}`).toContain(l)
    expect(sourceLabels.filter((l) => labels.includes(l)).length).toBe(6)
    // 源外增强字段仍在（数据零丢失）
    expect(labels).toContain('抽样结论')
    // 既有 4 项用词不应同时出现
    expect(labels).not.toContain('抽样方式')
    expect(labels).not.toContain('选样标准')
    wrapper.unmount()
  })

  it('挂载渲染：cycle="D0" 显示既有 4 项（六枢纽零回归）', () => {
    const wrapper = mount(ConfirmationSampling, {
      props: { data: {}, readonly: false, dictData: {}, cycle: 'D0' as const },
      global: { plugins: [ElementPlus] },
    })
    const labels = wrapper.findAll('.el-form-item__label').map((n) => n.text().replace(/：$/, ''))
    expect(labels).toEqual(['抽样方式', '样本量', '选样标准', '抽样结论'])
    expect(labels.length).toBe(4)
    for (const d of G0_SAMPLE_SELECTION_DEFS) {
      if (d.label === '抽样方法') continue // 与既有「抽样方式」用词不同，无需排除
      expect(labels).not.toContain(d.label)
    }
    wrapper.unmount()
  })

  it('cycle 缺省按非 G0 处理（绝不默认 G0）', () => {
    const wrapper = mount(ConfirmationSampling, {
      props: { data: {}, readonly: false, dictData: {} },
      global: { plugins: [ElementPlus] },
    })
    const labels = wrapper.findAll('.el-form-item__label').map((n) => n.text().replace(/：$/, ''))
    expect(labels).toEqual(['抽样方式', '样本量', '选样标准', '抽样结论'])
    wrapper.unmount()
  })

  /**
   * 🔴 改写记录（同上，2026-08-07）：门控字面由 `v-if="isG0"` 归一为
   * `v-if="useSourceSix"`（G0/K0 共用表单块）。反向自检的**实质**不变：
   * 「删掉门控 → 未声明 6 项的枢纽（D0）也会渲染 6 项」，故仍断言
   * 门控只有一个条件、无 `v-show`、块内不含第二层枢纽条件。
   */
  it('反向自检：门控是两分支唯一区别 —— 去掉门控则 D0 必渲染 6 项', () => {
    const clean = stripComments(SAMPLING_VUE)
    const gateIdx = clean.indexOf('<el-form v-if="useSourceSix"')
    expect(gateIdx).toBeGreaterThan(-1)
    const formTag = clean.slice(gateIdx, clean.indexOf('>', gateIdx))
    expect(formTag).toContain('v-if="useSourceSix"')
    expect(formTag).not.toContain('v-show')
    // 该块内不存在第二层枢纽条件（否则删门控也未必出现 6 项，反向自检会失效）
    const elseIdx = clean.indexOf('<el-form v-else')
    const gateBlock = clean.slice(gateIdx, elseIdx)
    expect(gateBlock).not.toContain('isG0')
    expect(gateBlock).not.toContain('isK0')
    expect(gateBlock.match(/useSourceSix/g)!.length).toBe(1)
    // 🔴 门控本身必须是纯长度判定（不含枢纽白名单以外的旁路条件）
    expect(clean).not.toMatch(/useSourceSix\s*=\s*computed\(\(\)\s*=>\s*true\)/)
  })

  it('R3.6.3：cycle="D0" 下 6 项字段数据不被组件丢弃', () => {
    const data = { sampling_population: '组合A', test_population: '总体X', sampling_size: '15 笔' }
    const wrapper = mount(ConfirmationSampling, {
      props: { data, readonly: false, dictData: {}, cycle: 'D0' as const },
      global: { plugins: [ElementPlus] },
    })
    // 渲染层不显示，但数据对象原样保留（`sampling` 整体 JSON 往返）
    expect(wrapper.props('data')).toMatchObject(data)
    wrapper.unmount()
  })
})

// ─── Property 13: 非测试消费方存在性 ─────────────────────────────────────────

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) {
      if (name === '__tests__' || name === 'node_modules') continue
      walk(p, out)
    } else if (/\.(ts|vue)$/.test(name) && name !== 'components.d.ts') {
      out.push(p)
    }
  }
  return out
}

describe('Property 13: 新建件均有真实（非测试）消费方', () => {
  const files = walk(join(FRONTEND_SRC, 'components', 'workpaper'))

  it('扫描到足量源文件（防扫描器空转）', () => {
    expect(files.length).toBeGreaterThan(200)
  })

  it('g0SummaryLowerZone.ts 有非测试消费方', () => {
    const consumers = files.filter(
      (f) => !f.endsWith('g0SummaryLowerZone.ts') && readFileSync(f, 'utf-8').includes('g0SummaryLowerZone'),
    )
    expect(consumers.length, '零消费方即视为未交付').toBeGreaterThan(0)
  })

  it('G0SummaryLowerZone.vue 有非测试消费方', () => {
    const consumers = files.filter(
      (f) => !f.endsWith('G0SummaryLowerZone.vue') && readFileSync(f, 'utf-8').includes('G0SummaryLowerZone'),
    )
    expect(consumers.length, '零消费方即视为未交付').toBeGreaterThan(0)
    expect(consumers.some((f) => f.endsWith('GtConfirmationSummary.vue'))).toBe(true)
  })

  it('宿主以 v-if="isG0" 门控挂载（其余六枢纽模板不受影响）', () => {
    const clean = stripComments(SUMMARY_VUE)
    expect(clean).toContain('<G0SummaryLowerZone')
    const idx = clean.indexOf('<G0SummaryLowerZone')
    const tag = clean.slice(idx, clean.indexOf('/>', idx))
    expect(tag).toContain('v-if="isG0"')
    expect(clean).toMatch(/const\s+isG0\s*=\s*computed\(\(\)\s*=>\s*confirmCycle\.value\s*===\s*'G0'\)/)
  })

  it('宿主拉录入值走已持久化端点（不取 responses_snapshot，防 prefill 种子伪装手工值）', () => {
    const clean = stripComments(SUMMARY_VUE)
    const body = functionBody(clean, 'loadG0Responses')
    expect(body).toContain('/checklist-responses')
    expect(body).toContain('/api/workpapers/')
    expect(body).not.toContain('responses_snapshot')
  })

  it('E0 / H0 下区副本一行未改（D-2 红线，导出符号集合锚定）', () => {
    const e0 = readFileSync(resolve(__dirname, '../../confirmation/e0SummaryLowerZone.ts'), 'utf-8')
    const h0 = readFileSync(resolve(__dirname, '../../confirmation/h0SummaryLowerZone.ts'), 'utf-8')
    // H0 侧的关键导出仍在（若被本 spec 改动/删除会打红）
    for (const sym of [
      'H0_LOWER_ZONE_BLOCKS',
      'H0_SAMPLE_SELECTION_FIELDS',
      'H0_AUDIT_NOTE_SECTIONS',
      'H0_REFERENCE_CONCLUSIONS',
      'H0_LOWER_ZONE_TEXTS',
    ]) {
      expect(h0, `H0 导出 ${sym} 不应被改动`).toContain(`export const ${sym}`)
    }
    expect(e0.length).toBeGreaterThan(500)
    // 两侧都不得引用 G0 的声明（各自一份，互不引用）
    expect(h0).not.toContain('g0SummaryLowerZone')
    expect(e0).not.toContain('g0SummaryLowerZone')
  })
})

// ─── 下区录入持久化路径（2026-08-04 G0 浏览器实测暴露，Task 23） ──────────────

/**
 * 🔴🔴 平台级 P0，**已在 H0 与 G0 上各实测复现一次** —— 故守卫**参数化覆盖全部枢纽**，
 * 不再一个循环写一份（H0 那条只钉了 `handleH0LowerSave`，G0 侧因此漏网）。
 *
 * 机理：`confirmation-summary` 的宿主 save 处理器把 `emit('save', payload)` 的载荷
 * **整体**写成该 sheet 的 `parsed_data.html_data[sheetName]`。下区录入是 itemId 维度的
 * `{itemId, value}` → 整张 sheet 的载荷（含 `_format` 与全部函证行）被两个字段顶掉
 * → 下次打开退化成「此底稿使用旧格式，仅支持只读查看」。
 *
 * G0 实测证据（项目 2aa00f57 / wp b09ec83f）：
 *   html_data['函证结果汇总表G0-1'] == {"value":"未见异常。","itemId":"G0-1-lower-conclusion"}
 */
describe('Task 23: 全部枢纽的下区录入必须走 checklist-responses PUT', () => {
  const clean = stripComments(SUMMARY_VUE)

  /** 从模板里扫出所有下区组件的 @save 处理器名 —— 新增枢纽自动纳入，不靠人工登记 */
  const lowerZoneHandlers = Array.from(
    clean.matchAll(/<[A-Z]\w*SummaryLowerZone[\s\S]*?@save="(\w+)"/g),
  ).map((m) => m[1])

  it('扫描到 ≥2 个下区 @save 处理器（反向自检：正则失效则空转）', () => {
    expect(lowerZoneHandlers.length).toBeGreaterThanOrEqual(2)
    expect(lowerZoneHandlers).toContain('handleG0LowerSave')
    expect(lowerZoneHandlers).toContain('handleH0LowerSave')
  })

  it.each(lowerZoneHandlers.length ? lowerZoneHandlers : ['handleG0LowerSave'])(
    '%s 直接 PUT /api/.../checklist-responses，且不得 emit(save)',
    (name) => {
      const body = functionBody(clean, name)
      expect(body, `${name} 必须打 checklist-responses`).toContain('/checklist-responses')
      expect(body, `${name} 必须用 http.put`).toMatch(/http\.put\(/)
      // emit('save') 会让宿主整体覆盖 sheet 载荷 → 函证行全丢 + 退化只读
      expect(body, `${name} 不得 emit('save')`).not.toMatch(/emit\(\s*['"]save['"]/)
      // /api 前缀漏了会打到 dev server 拿回 index.html（200 + HTML）静默无效
      expect(body).toMatch(/['"`]\/api\/workpapers\//)
    },
  )

  it('反向自检：改造前的写法（emit save）确实会被本守卫判红', () => {
    const legacy = `function handleXLowerSave(itemId, value) {\n  emit('save', { itemId, value })\n}`
    const body = functionBody(legacy, 'handleXLowerSave')
    expect(body).toMatch(/emit\(\s*['"]save['"]/)
    expect(body).not.toContain('/checklist-responses')
  })
})
