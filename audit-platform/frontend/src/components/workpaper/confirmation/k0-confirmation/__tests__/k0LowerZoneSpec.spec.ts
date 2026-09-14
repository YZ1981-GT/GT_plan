/**
 * k0LowerZoneSpec.spec.ts — K0-1 下区四块声明守卫（Wave 2）
 *
 * spec: k0-confirmation-source-alignment · Task 7
 *   Property 9（下区新增键与既有键无交集）/ 10（审计说明 5 项逐字 + 两格句子合并）
 *   / 13（索引号笔误三条登记）
 *   Requirement 3.6~3.12 / 6.1 / 6.2
 *
 * 判据：**读对侧源码** —— 后端源模板事实守卫（`test_k0_source_template_facts.py`）
 * 与既有类型声明（`confirmationTypes.ts` / `alternativeD05Types.ts`）。
 * 每组断言配反向自检，防正则失效导致断言空转。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  CONVERGENCE_TARGET,
  K0_AUDIT_NOTES,
  K0_EXISTING_PAYLOAD_KEYS,
  K0_GUIDANCE_BLOCKS,
  K0_INDEX_TYPO_MAP,
  K0_LOWER_ZONE_BLOCKS,
  K0_LOWER_ZONE_PAYLOAD_KEYS,
  K0_REFERENCE_CONCLUSIONS,
  K0_SAMPLE_SELECTION,
  K0_SAMPLE_SELECTION_HINTS,
  getK0IndexTypo,
  getK0LowerBlock,
} from '../k0LowerZoneSpec'

const SENTINEL = 'backend/wp_templates/K/K0 管理循环函证.xlsx'

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(resolve(dir, SENTINEL))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未找到仓库根（哨兵 ${SENTINEL} 不存在于 ${__dirname} 的任一祖先）`)
}

const REPO_ROOT = findRepoRoot()
const factsSrc = readFileSync(
  resolve(REPO_ROOT, 'backend/tests/test_k0_source_template_facts.py'),
  'utf-8',
)
const LOWER_SPEC_TS = resolve(__dirname, '../k0LowerZoneSpec.ts')
const CONFIRM_TYPES_TS = resolve(__dirname, '../../confirmationTypes.ts')
const ALT_TYPES_TS = resolve(__dirname, '../../alternativeD05/alternativeD05Types.ts')

/** 从 python 源码取「常量名 = [ ... ]」块里的双引号字符串 */
function pyListStrings(src: string, constName: string): string[] {
  const at = src.indexOf(`${constName} = [`)
  expect(at, `后端未找到常量 ${constName}`).toBeGreaterThan(-1)
  const start = src.indexOf('[', at)
  let depth = 0
  let end = -1
  for (let i = start; i < src.length; i += 1) {
    if (src[i] === '[') depth += 1
    else if (src[i] === ']') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  expect(end, `${constName} 括号未配对`).toBeGreaterThan(start)
  return [...src.slice(start, end + 1).matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1])
}

/**
 * 抽 python 隐式拼接常量 `NAME = ( "a" "b" )` 的拼接结果。
 * 🔴 按 ASCII 括号配对定边界（源文字里的「（）」是全角，不参与配对），
 * 不用 `\)\n` 之类的行尾正则 —— 那会因 CRLF/LF 差异静默不命中（本守卫首版即如此）。
 */
function pyParenJoined(src: string, constName: string): string {
  const at = src.indexOf(`${constName} = (`)
  expect(at, `后端未找到常量 ${constName}`).toBeGreaterThan(-1)
  const start = src.indexOf('(', at)
  let depth = 0
  let end = -1
  for (let i = start; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1
    else if (src[i] === ')') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  expect(end, `${constName} 括号未配对`).toBeGreaterThan(start)
  const parts = [...src.slice(start, end + 1).matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1])
  expect(parts.length, `${constName} 未抽到字符串片段`).toBeGreaterThan(0)
  return parts.join('')
}

/** 抽 TS `interface X { ... }` 里的字段名（含 optional） */
function tsInterfaceFields(src: string, name: string): string[] {
  const at = src.indexOf(`interface ${name} {`)
  expect(at, `未找到 interface ${name}`).toBeGreaterThan(-1)
  const start = src.indexOf('{', at)
  let depth = 0
  let end = -1
  for (let i = start; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  expect(end, `interface ${name} 括号未配对`).toBeGreaterThan(start)
  const body = src.slice(start + 1, end)
  const stripped = body
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
  return [...stripped.matchAll(/(?:^|\n)\s*([A-Za-z_]\w*)\??\s*:/g)].map((m) => m[1])
}

const samplingDataFields = tsInterfaceFields(readFileSync(CONFIRM_TYPES_TS, 'utf-8'), 'SamplingData')
const notesDataFields = tsInterfaceFields(readFileSync(CONFIRM_TYPES_TS, 'utf-8'), 'NotesData')
const samplingConfigFields = tsInterfaceFields(readFileSync(ALT_TYPES_TS, 'utf-8'), 'SamplingConfig')

describe('helper 自检（防解析失效导致断言空转）', () => {
  it('三个既有类型都解析出非空字段集', () => {
    expect(samplingDataFields.length).toBeGreaterThan(5)
    expect(notesDataFields).toEqual([
      'note_general', 'note_exception', 'note_unreplied', 'note_alternative', 'note_other',
    ])
    // 🔴 6 → 7：`g0-confirmation-source-alignment` Task 14 additive 新增了
    //    `occurrence_sampling_scope`（G0-6 专属，源 `替代程序检查表G0-6!C15` 的
    //    「本期发生额」抽样标准 5 点选项）。本处只是 helper 的**防空转**自检，
    //    故按「≥ K0 实际消费的 6 个 且 6 个都在」断言，而不再钉死总数 ——
    //    否则任何枢纽 additive 加字段都会打红这条与它无关的用例。
    expect(samplingConfigFields.length).toBeGreaterThanOrEqual(6)
    expect(samplingConfigFields).toEqual(
      expect.arrayContaining([
        'test_scope',
        'specific_samples',
        'sampling_population',
        'sample_size',
        'sampling_method',
        'sampling_process',
      ]),
    )
  })

  it('对不存在的 interface / 常量会失败而不是静默返回空', () => {
    expect(() => tsInterfaceFields('x', 'NoSuchInterface')).toThrow()
    expect(() => pyListStrings(factsSrc, 'NO_SUCH_CONST')).toThrow()
    expect(() => pyParenJoined(factsSrc, 'NO_SUCH_PAREN_CONST')).toThrow()
  })

  it('pyParenJoined 能取到隐式拼接常量的完整结果（不受 CRLF/LF 影响）', () => {
    const joined = pyParenJoined(factsSrc, 'AUDIT_NOTE_HINT_X29_X30')
    expect(joined.startsWith('界定误差构成条件：')).toBe(true)
    expect(joined.endsWith('］')).toBe(true)
  })
})

// ─── 四块 ────────────────────────────────────────────────────────────────────

describe('Requirement 3.1: 四块锚点与标题逐字取自源模板', () => {
  it('四块 = C27 / I27 / S27 / C38', () => {
    expect(K0_LOWER_ZONE_BLOCKS.map((b) => [b.anchor, b.title])).toEqual([
      ['C27', '一、函证情况'],
      ['I27', '二、样本选择'],
      ['S27', '三、审计说明'],
      ['C38', '四、审计结论'],
    ])
  })

  it('与后端 LOWER_ZONE_BLOCKS 逐字一致（交叉锁死）', () => {
    const flat = pyListStrings(factsSrc, 'LOWER_ZONE_BLOCKS')
    for (const b of K0_LOWER_ZONE_BLOCKS) {
      expect(flat).toContain(b.anchor)
      expect(flat).toContain(b.title)
    }
  })

  it('sourceRef == `K0-1!` + anchor', () => {
    for (const b of K0_LOWER_ZONE_BLOCKS) expect(b.sourceRef).toBe(`K0-1!${b.anchor}`)
  })

  it('🔴 二、样本选择由 ConfirmationSampling 渲染（renderedHere=false，防双真源）', () => {
    expect(getK0LowerBlock('sample_selection').renderedHere).toBe(false)
    for (const key of ['matrix', 'audit_note', 'conclusion'] as const) {
      expect(getK0LowerBlock(key).renderedHere).toBe(true)
    }
  })

  it('未声明的块会抛错而非静默返回 undefined', () => {
    // @ts-expect-error 故意传非法 key
    expect(() => getK0LowerBlock('nope')).toThrow()
  })
})

// ─── 二、样本选择 6 项 ───────────────────────────────────────────────────────

describe('Requirement 3.6: 样本选择 6 项复用既有字段族，不新造', () => {
  it('恰 6 项，label 与锚点与源模板一致（I32 为空 → 锚点不连续）', () => {
    expect(K0_SAMPLE_SELECTION).toHaveLength(6)
    expect(K0_SAMPLE_SELECTION.map((s) => s.labelAnchor)).toEqual([
      'I28', 'I29', 'I30', 'I31', 'I33', 'I34',
    ])
    expect(K0_SAMPLE_SELECTION.map((s) => s.labelAnchor)).not.toContain('I32')
  })

  it('label + 「：」 能在后端 SAMPLE_SELECTION_CELLS 里找到（交叉锁死）', () => {
    const flat = pyListStrings(factsSrc, 'SAMPLE_SELECTION_CELLS')
    for (const s of K0_SAMPLE_SELECTION) {
      expect(flat).toContain(`${s.label}：`)
      expect(flat).toContain(s.labelAnchor)
    }
  })

  it('🔴 6 个 key 全部是 `SamplingData` 的既有字段（持久化真源）', () => {
    for (const s of K0_SAMPLE_SELECTION) {
      expect(samplingDataFields, `SamplingData 缺字段 ${s.key}`).toContain(s.key)
    }
  })

  it('🔴 6 个 key 里 5 个与替代程序族 `SamplingConfig` 同名；唯一例外显式登记', () => {
    const exceptions = K0_SAMPLE_SELECTION.filter((s) => !samplingConfigFields.includes(s.key))
    expect(exceptions.map((s) => s.key)).toEqual(['test_population'])
    // 例外项必须给出替代程序族的对位字段，且该字段确实存在
    expect(exceptions[0].legacyFamilyField).toBe('test_scope')
    expect(samplingConfigFields).toContain('test_scope')
    // 其余 5 项的 legacyFamilyField 就是自身
    for (const s of K0_SAMPLE_SELECTION) {
      if (s.key === 'test_population') continue
      expect(s.legacyFamilyField).toBe(s.key)
      expect(samplingConfigFields).toContain(s.key)
    }
  })

  it('🔴 不新造第二套字段名：`test_scope` 不得被加进 SamplingData', () => {
    expect(samplingDataFields).not.toContain('test_scope')
  })

  it('抽样方法是点选型（源模板 J33 本就是斜杠分隔的备选项）', () => {
    const method = K0_SAMPLE_SELECTION.find((s) => s.key === 'sampling_method')!
    expect(method.options).toEqual(['随机选样', '系统选样', '货币单元抽样', '随意选样'])
    // placeholder 就是源模板原串 → 选项应恰为它按斜杠拆分的结果
    expect(method.placeholder.split('/')).toEqual([...method.options!])
    // 其余 5 项不是点选型
    expect(K0_SAMPLE_SELECTION.filter((s) => s.options).map((s) => s.key)).toEqual(['sampling_method'])
  })

  it('「抽样过程」placeholder 是 J34+J35 拼接，不以半句话结尾', () => {
    const proc = K0_SAMPLE_SELECTION.find((s) => s.key === 'sampling_process')!
    expect(proc.placeholderAnchor).toBe('J34+J35')
    expect(proc.placeholder.endsWith('……')).toBe(true)
    expect(proc.placeholder).toContain('其他应付款选择XX个债权人')
  })

  it('两条只读提示语（J32 / J36）挂在正确的项上', () => {
    expect(K0_SAMPLE_SELECTION_HINTS.map((h) => [h.key, h.anchor])).toEqual([
      ['sample_size', 'J32'],
      ['sampling_process', 'J36'],
    ])
    for (const h of K0_SAMPLE_SELECTION_HINTS) {
      expect(K0_SAMPLE_SELECTION.some((s) => s.key === h.key)).toBe(true)
      expect(h.sourceRef).toBe(`K0-1!${h.anchor}`)
    }
  })
})

// ─── Property 10：三、审计说明 5 项 ──────────────────────────────────────────

describe('Property 10: 审计说明 5 项逐字 + 两格句子合并 + aliasOf 有效', () => {
  it('恰 5 项，seq 1..5，label 与锚点与源模板一致', () => {
    expect(K0_AUDIT_NOTES).toHaveLength(5)
    expect(K0_AUDIT_NOTES.map((n) => n.seq)).toEqual([1, 2, 3, 4, 5])
    expect(K0_AUDIT_NOTES.map((n) => n.labelAnchor)).toEqual(['S28', 'X28', 'S32', 'X32', 'S36'])
  })

  it('5 个 label 与后端 AUDIT_NOTE_TITLE_CELLS 逐字一致（交叉锁死）', () => {
    const flat = pyListStrings(factsSrc, 'AUDIT_NOTE_TITLE_CELLS')
    for (const n of K0_AUDIT_NOTES) {
      expect(flat).toContain(n.label)
      expect(flat).toContain(n.labelAnchor)
    }
  })

  it('🔴 K0 用半角句点序号 `N.`（G0/H0 是 `N、`，勿统一）', () => {
    for (const [i, n] of K0_AUDIT_NOTES.entries()) {
      expect(n.label.startsWith(`${i + 1}.`)).toBe(true)
      expect(n.label.startsWith(`${i + 1}、`)).toBe(false)
    }
  })

  it('第 2 项的 inlineHint = X29+X30 拼接，不以半句话结尾', () => {
    const n2 = K0_AUDIT_NOTES[1]
    expect(n2.inlineHintAnchor).toBe('X29+X30')
    expect(n2.inlineHint!.endsWith('］')).toBe(true)
    expect(n2.inlineHint).not.toMatch(/人民币$/)
    // 与后端常量逐字一致（交叉锁死）
    expect(n2.inlineHint).toBe(pyParenJoined(factsSrc, 'AUDIT_NOTE_HINT_X29_X30'))
  })

  it('第 3 项的 S33 是独立 hint，绝不与标题拼接（否则出错句）', () => {
    const n3 = K0_AUDIT_NOTES[2]
    expect(n3.inlineHintAnchor).toBe('S33')
    expect(n3.label).not.toContain(n3.inlineHint!)
    const m = factsSrc.match(/AUDIT_NOTE_HINT_S33 = "([^"]+)"/)
    expect(m).toBeTruthy()
    expect(n3.inlineHint).toBe(m![1])
  })

  it('第 3 项逐字保留源模板的「（K0-6）」笔误（顺手修正会让三向比对打红）', () => {
    expect(K0_AUDIT_NOTES[2].label).toContain('（K0-6）')
  })

  it('只有第 5 项声明 aliasOf，且目标存在于 NotesData', () => {
    const aliased = K0_AUDIT_NOTES.filter((n) => n.aliasOf)
    expect(aliased.map((n) => n.seq)).toEqual([5])
    expect(aliased[0].aliasOf).toBe('note_alternative')
    expect(notesDataFields).toContain(aliased[0].aliasOf!)
  })

  it('每项都有 aiSection 与 reviewSectionId，且各自唯一', () => {
    const ai = K0_AUDIT_NOTES.map((n) => n.aiSection)
    const rv = K0_AUDIT_NOTES.map((n) => n.reviewSectionId)
    expect(new Set(ai).size).toBe(5)
    expect(new Set(rv).size).toBe(5)
    for (const n of K0_AUDIT_NOTES) {
      expect(n.aiSection.startsWith('k0-summary-')).toBe(true)
      expect(n.reviewSectionId).toBe(`K0-1-audit-note-${n.seq}`)
    }
  })

  it('key 各自唯一且不与 NotesData 字段撞名（新键 ≠ 既有字段）', () => {
    const keys = K0_AUDIT_NOTES.map((n) => n.key)
    expect(new Set(keys).size).toBe(5)
    for (const k of keys) expect(notesDataFields).not.toContain(k)
  })
})

// ─── 四、审计结论 ────────────────────────────────────────────────────────────

describe('Requirement 3.10: 参考结论 A/B/C 取自 B 列', () => {
  it('三条，内容锚点在 B 列、标签锚点在 A 列', () => {
    expect(K0_REFERENCE_CONCLUSIONS.map((c) => [c.code, c.anchor, c.labelAnchor])).toEqual([
      ['A', 'B64', 'A64'],
      ['B', 'B65', 'A65'],
      ['C', 'B66', 'A66'],
    ])
  })

  it('文字与后端 REFERENCE_CONCLUSIONS 逐字一致（交叉锁死）', () => {
    const flat = pyListStrings(factsSrc, 'REFERENCE_CONCLUSIONS')
    for (const c of K0_REFERENCE_CONCLUSIONS) {
      expect(flat).toContain(c.text)
      expect(flat).toContain(c.anchor)
    }
  })

  it('文字里不含 `A、` 这类标签前缀（内容在 B 列，标签在 A 列）', () => {
    for (const c of K0_REFERENCE_CONCLUSIONS) {
      expect(c.text.startsWith(`${c.code}、`)).toBe(false)
    }
  })
})

// ─── 编制说明 ────────────────────────────────────────────────────────────────

describe('Requirement 3.11: 编制说明作只读方法论上下文', () => {
  it('准则 1312 第十条六项逐字（与后端交叉锁死）', () => {
    const flat = pyListStrings(factsSrc, 'STANDARD_1312_SELECTION_ITEMS')
    const block = K0_GUIDANCE_BLOCKS.find((b) => b.key === 'sample_selection_standard')!
    const six = block.lines.filter((l) => /^（[一二三四五六]）/.test(l.text))
    expect(six).toHaveLength(6)
    for (const l of six) {
      expect(flat).toContain(l.text)
      expect(flat).toContain(l.anchor)
    }
  })

  it('🔴 函证注意事项 8 条且锚点全在 B 列（只扫 A 列会整段漏掉）', () => {
    const flat = pyListStrings(factsSrc, 'CONFIRMATION_TIPS')
    const block = K0_GUIDANCE_BLOCKS.find((b) => b.key === 'confirmation_tips')!
    expect(block.lines).toHaveLength(8)
    for (const l of block.lines) {
      expect(l.anchor.startsWith('B')).toBe(true)
      expect(flat).toContain(l.text)
      expect(flat).toContain(l.anchor)
    }
  })

  it('含 A40 传真电邮提示与 A67 后附审计证据', () => {
    const anchors = K0_GUIDANCE_BLOCKS.flatMap((b) => b.lines.map((l) => l.anchor))
    expect(anchors).toContain('A40')
    expect(anchors).toContain('A67')
  })

  it('每条 line 都有非空 text 与锚点（防占位空行）', () => {
    for (const b of K0_GUIDANCE_BLOCKS) {
      expect(b.lines.length).toBeGreaterThan(0)
      for (const l of b.lines) {
        expect(l.text.trim().length).toBeGreaterThan(0)
        expect(l.anchor).toMatch(/^[A-Z]+\d+$/)
      }
    }
  })
})

// ─── Property 13：索引号笔误 ─────────────────────────────────────────────────

describe('Property 13: 索引号笔误三条登记且指向意图目标', () => {
  it('恰三条，intended 分别为 K0-4 / K0-7 / K0-3', () => {
    expect(K0_INDEX_TYPO_MAP).toHaveLength(3)
    expect(K0_INDEX_TYPO_MAP.map((t) => t.intended)).toEqual(['K0-4', 'K0-7', 'K0-3'])
  })

  it('literal 与后端 SOURCE_TEMPLATE_TYPOS 逐字一致（交叉锁死）', () => {
    const flat = pyListStrings(factsSrc, 'SOURCE_TEMPLATE_TYPOS')
    for (const t of K0_INDEX_TYPO_MAP) {
      expect(flat, `后端未登记 literal: ${t.literal}`).toContain(t.literal)
      expect(flat, `后端未登记 sourceRef: ${t.sourceRef}`).toContain(t.sourceRef)
      expect(flat).toContain(t.intended)
    }
  })

  it('反向自检：intended 不得等于 literal 里出现的索引号', () => {
    for (const t of K0_INDEX_TYPO_MAP) {
      expect(t.literal).not.toContain(t.intended)
    }
  })

  it('每条都有可读的判据说明（tooltip 第二行）', () => {
    for (const t of K0_INDEX_TYPO_MAP) {
      expect(t.note.length).toBeGreaterThanOrEqual(15)
      expect(t.note).toContain('笔误')
    }
  })

  it('按 sourceRef 可查；未登记的返回 undefined', () => {
    expect(getK0IndexTypo('核实被函证单位信息K0-2!AA6')!.intended).toBe('K0-3')
    expect(getK0IndexTypo('函证结果汇总表K0-1!A1')).toBeUndefined()
  })
})

// ─── Property 9：持久化键 ────────────────────────────────────────────────────

describe('Property 9: 下区四键与既有键无交集', () => {
  it('四个新键与五个既有键无交集', () => {
    const overlap = K0_LOWER_ZONE_PAYLOAD_KEYS.filter((k) =>
      (K0_EXISTING_PAYLOAD_KEYS as readonly string[]).includes(k),
    )
    expect(overlap).toEqual([])
    expect(K0_LOWER_ZONE_PAYLOAD_KEYS).toHaveLength(4)
  })

  it('四键全部以 `k0_` 前缀（与共享键可视区分）', () => {
    for (const k of K0_LOWER_ZONE_PAYLOAD_KEYS) expect(k.startsWith('k0_')).toBe(true)
  })

  it('aliasOf 项不落 `k0_audit_notes`（读写既有 notes 字段，不重复录入）', () => {
    const src = readFileSync(LOWER_SPEC_TS, 'utf-8')
    expect(src).toContain('aliasOf')
    expect(src).toMatch(/不落此处|只读引用/)
  })

  it('CONVERGENCE_TARGET 与 E0/H0/G0 下区副本同一标识', () => {
    expect(CONVERGENCE_TARGET).toBe('confirmation-summary-lower-zone-convergence')
  })
})
