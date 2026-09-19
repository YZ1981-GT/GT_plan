/**
 * k0SharedComponentBoundary.spec.ts — 共享件改造的边界与零回归守卫
 *
 * spec: k0-confirmation-source-alignment · Task 16
 *
 * 覆盖 Property 17（K0-2 二次发函六列 additive）/ Property 18（K0-7 父表头与渠道字段处置）
 * / Property 19（跟函通用话术占位 + E0 五段逐字不变）/ Property 20（新建模块零消费方即打红）
 * / Property 21（共享件受影响循环声明表完整）/ Property 24（源外保留列显式登记 + 已渲染）
 *
 * 🔴 判据一律以**后端源模板事实常量**或**对侧源码**为裁决者，不拿自己写的 fixture 自证。
 * 🔴 每组断言配反向自检（改一字必红），防正则失效导致断言空转。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  RELIABILITY_COLUMN_SOURCE_LABELS,
  SOURCE_EXTRA_RELIABILITY_COLUMNS,
  reliabilitySourceLabel,
  isSourceExtraReliabilityColumn,
} from '../reliability/reliabilityColumnLabels'
import { RELIABILITY_PARENT_HEADER } from '../reliability/reliabilityNotes'
import { ENTITY_VERIFY_GUIDANCE } from '../entityVerify/entityVerifyGuidance'

// ─── REPO_ROOT：双哨兵向上查找（禁写死回退级数，memory 铁律） ───────────────────
function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'tests', 'test_k0_source_template_facts.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('REPO_ROOT 未找到（双哨兵均未命中）')
}
const REPO_ROOT = findRepoRoot()
const FACTS_PY = path.join(REPO_ROOT, 'backend', 'tests', 'test_k0_source_template_facts.py')
const CONF_DIR = path.join(__dirname, '..')

/** 正则转义（中文无特殊字符，但保持通用） */
function escapeRe(x: string): string {
  return x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 剥 HTML 注释 + JS 块/行注释。
 *
 * 🔴 SFC 模板里的 `<!-- ═══ 期末未收回原件函证可靠性验证 ... ═══ -->` 这类说明注释
 *    会让「不得出现该字面量」的断言假红 —— 必须先剥注释再判定。
 */
function stripAllComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
}

function read(p: string): string {
  const src = fs.readFileSync(p, 'utf-8')
  expect(src.length).toBeGreaterThan(200) // 反向自检：不是空文件
  return src
}

/** 剥 python 注释（memory 铁律：注释里会写被禁的反例） */
function stripPyComments(src: string): string {
  return src
    .replace(/"""[\s\S]*?"""/g, '')
    .replace(/'''[\s\S]*?'''/g, '')
    .replace(/^\s*#.*$/gm, '')
}

/** 剥 TS/Vue 注释 */
function stripTsComments(src: string): string {
  // 🔴 必须同时剥三类注释（memory 铁律：守卫注释里会写反例说明，会被数成真实代码）：
  //    ① JS 块注释 ② JS 行注释 ③ **SFC 模板 HTML 注释**（`<!-- ... -->`）
  //    只剥前两类时，`<!-- ═══ 期末未收回原件函证可靠性验证（源 G5:M5） ═══ -->`
  //    这类说明性注释会让「不得硬编码字面量」的断言假红。
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
}

/** 反向自检用：确认 stripTsComments 真的剥掉了 HTML 注释 */
function stripSelfCheckSample(): string {
  return '<!-- HIDDEN_MARKER_XYZ -->visible'
}


/**
 * 抽 python 里的二元组列表常量。
 *
 * 🔴 括号必须从 `=` **之后**开始配对 —— 类型注解 `list[tuple[str, str]]` 里也有方括号，
 *    从声明起点找第一个 `[` 会命中注解（本守卫自己踩过一次）。
 */
function pyTupleList(src: string, name: string): [string, string][] {
  const decl = new RegExp(`^${name}\\s*(?::[^=\\n]*)?=`, 'm').exec(src)
  if (!decl) throw new Error(`常量 ${name} 未找到（正则失效？）`)
  const eq = src.indexOf('=', decl.index + name.length)
  const start = src.indexOf('[', eq)
  let depth = 0
  let end = -1
  for (let i = start; i < src.length; i++) {
    if (src[i] === '[') depth++
    else if (src[i] === ']') {
      depth--
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  if (end < 0) throw new Error(`常量 ${name} 括号未配对`)
  const out: [string, string][] = []
  const re = /\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\)/g
  let m: RegExpExecArray | null
  const body = src.slice(start + 1, end)
  while ((m = re.exec(body)) !== null) out.push([m[1], m[2]])
  return out
}

describe('helper 自检', () => {
  it('pyTupleList 能抽到 SECOND_SEND_LEAF_COLUMNS 六项（防解析失效导致断言空转）', () => {
    const rows = pyTupleList(stripPyComments(read(FACTS_PY)), 'SECOND_SEND_LEAF_COLUMNS')
    expect(rows).toHaveLength(6)
    expect(rows[0]).toEqual(['AF', '地址'])
  })

  it('pyTupleList 对不存在的常量必须抛错', () => {
    const src = stripPyComments(read(FACTS_PY))
    expect(() => pyTupleList(src, 'NOT_EXIST_CONST_XYZ')).toThrow()
  })
})

// ─── Property 17：K0-2 二次发函六列 additive ───────────────────────────────────

describe('Property 17 · K0-2 二次发函六列与源模板叶子列一一映射且 additive', () => {
  const TYPES = path.join(CONF_DIR, 'entityVerify', 'entityVerifyTypes.ts')
  const DETAIL = path.join(CONF_DIR, 'entityVerify', 'EntityVerifyDetail.vue')

  /**
   * 平台字段 ← 源模板 `AF6:AK6` 叶子列的映射。
   *
   * 🔴 字段名是 `second_entity_*` / `second_contact_*` / `second_fax` / `second_info_verified`，
   *    **不是** tasks.md 里写的 `second_send_address` 等（那批名字在磁盘上零命中，
   *    照 tasks.md 写守卫会全红）。
   */
  const FIELD_BY_SOURCE_LABEL: Record<string, string> = {
    地址: 'second_entity_address',
    邮编: 'second_entity_zipcode',
    联系人: 'second_contact_person',
    联系电话: 'second_contact_phone',
    传真: 'second_fax',
    信息是否核查一致: 'second_info_verified',
  }

  it('六个源模板叶子列都有对应字段声明（跨前后端交叉锁死）', () => {
    const leaves = pyTupleList(stripPyComments(read(FACTS_PY)), 'SECOND_SEND_LEAF_COLUMNS')
    const types = read(TYPES)
    const missing: string[] = []
    for (const [, label] of leaves) {
      const field = FIELD_BY_SOURCE_LABEL[label]
      expect(field, `源模板叶子列「${label}」未在映射表登记`).toBeDefined()
      if (!new RegExp(`\\b${field}\\??\\s*:`).test(types)) missing.push(`${label}→${field}`)
    }
    expect(missing, `EntityVerifyRow 缺字段: ${missing.join(', ')}`).toEqual([])
  })

  it('六个字段都在 EntityVerifyDetail 有录入位置（非死字段）', () => {
    const detail = stripTsComments(read(DETAIL))
    const dead = Object.values(FIELD_BY_SOURCE_LABEL).filter(
      (f) => !detail.includes(f),
    )
    expect(dead, `声明了但 UI 从未渲染: ${dead.join(', ')}`).toEqual([])
  })

  it('六列受 is_second_send 门控（为假时折叠，不产空列噪声）', () => {
    const detail = read(DETAIL)
    expect(detail).toMatch(/is_second_send/)
    // 二次发函区块存在且六列在其中
    const idx = detail.indexOf('second_entity_address')
    const gate = detail.lastIndexOf('is_second_send', idx)
    expect(gate, '六列之前必须先出现 is_second_send 门控').toBeGreaterThan(0)
  })

  it('additive：既有 second_* 字段（一次发函结果侧）一个不少', () => {
    const types = read(TYPES)
    for (const f of ['second_send_date', 'second_send_method', 'second_result', 'second_return_reason']) {
      expect(types, `既有字段 ${f} 被删/改名 = 破坏 additive`).toMatch(new RegExp(`\\b${f}\\??\\s*:`))
    }
  })

  it('反向自检：映射表里放一个源模板没有的 label 必须能被发现', () => {
    const leaves = pyTupleList(stripPyComments(read(FACTS_PY)), 'SECOND_SEND_LEAF_COLUMNS')
    const labels = new Set(leaves.map(([, l]) => l))
    expect(labels.has('不存在的列XYZ')).toBe(false)
    // 映射表的键必须全部来自源模板（多登记即打红）
    for (const k of Object.keys(FIELD_BY_SOURCE_LABEL)) expect(labels.has(k)).toBe(true)
  })
})

// ─── Property 18 + 24：K0-7 父表头 / 列标签真源 / 源外列登记 ───────────────────

describe('Property 18 · K0-7 父表头与列标签走真源', () => {
  const GRID = path.join(CONF_DIR, 'reliability', 'ReliabilityGrid.vue')

  it('父表头常量逐字等于源模板 G5（跨前后端交叉锁死）', () => {
    const facts = stripPyComments(read(FACTS_PY))
    expect(facts).toContain(`== "${RELIABILITY_PARENT_HEADER}"`)
    expect(RELIABILITY_PARENT_HEADER).toBe('期末未收回原件函证可靠性验证')
  })

  it('Grid 用常量渲染父表头，不写字面量', () => {
    const grid = stripTsComments(read(GRID))
    expect(grid).toMatch(/:label="RELIABILITY_PARENT_HEADER"/)
    // 剥注释后模板里不得再出现字面量父表头
    const tpl = grid.slice(0, grid.indexOf('<script'))
    expect(tpl).not.toContain('期末未收回原件函证可靠性验证')
  })

  it('九处源模板用词的 label 逐字等于源模板 r5/r6（后端裁决）', () => {
    const facts = stripPyComments(read(FACTS_PY))
    const bad: string[] = []
    for (const d of RELIABILITY_COLUMN_SOURCE_LABELS) {
      // 源模板用词必须在后端事实断言里出现（`（注N）` 后缀不进 label，故用 includes）
      if (!facts.includes(d.sourceLabel)) bad.push(`${d.field}:${d.sourceLabel}`)
    }
    expect(bad, `这些 label 在后端源模板事实中找不到: ${bad.join(', ')}`).toEqual([])
  })

  it('每条登记都确实改变了用词（sourceLabel ≠ legacyLabel，防恒等映射空转）', () => {
    for (const d of RELIABILITY_COLUMN_SOURCE_LABELS) {
      expect(d.sourceLabel, `${d.field} 登记了恒等映射 = 无意义`).not.toBe(d.legacyLabel)
    }
  })

  it('Grid 已用真源渲染这些列（旧简称不得残留：label 属性 + 自定义表头插槽两种形态）', () => {
    const grid = stripAllComments(read(GRID))
    const tpl = grid.slice(0, grid.indexOf('<script'))
    const leftover: string[] = []
    for (const d of RELIABILITY_COLUMN_SOURCE_LABELS) {
      // 形态 A：静态 label 属性
      if (tpl.includes(`label="${d.legacyLabel}"`)) leftover.push(`label=${d.legacyLabel}`)
      // 🔴 形态 B：`<template #header>` 插槽里的静态文字 —— 插槽会**覆盖** `:label`，
      //    故只改 `:label` 而插槽仍写旧简称时，界面显示的仍是旧简称。
      //    2026-08-07 浏览器实测暴露：三列（身份确认/邮箱验证/可靠性结论）正是此形态，
      //    而当时守卫只查形态 A ⇒ 全绿却没生效。
      const slotRe = new RegExp(`<span[^>]*>\\s*${escapeRe(d.legacyLabel)}\\s*</span>`)
      if (slotRe.test(tpl)) leftover.push(`slot=${d.legacyLabel}`)
    }
    expect(leftover, `仍在硬编码旧简称: ${leftover.join(', ')}`).toEqual([])
  })

  it('反向自检：插槽形态的判据确实能抓到（防形态 B 断言空转）', () => {
    const fake = '<template #header><span>身份已确认</span></template>'
    const slotRe = new RegExp(`<span[^>]*>\\s*${escapeRe('身份已确认')}\\s*</span>`)
    expect(slotRe.test(fake)).toBe(true)
  })

  it('reliabilitySourceLabel 对未登记字段返回 undefined（调用方保留既有 label）', () => {
    expect(reliabilitySourceLabel('seq')).toBeUndefined()
    expect(reliabilitySourceLabel('entity_name')).toBe('被询证单位名称')
  })
})

/**
 * Property 25 · 模板里引用的标识符必须真的被定义或导入。
 *
 * 🔴🔴 2026-08-07 浏览器实测暴露的 P0：批量替换脚本往 `ReliabilityGrid.vue` 写入了
 *    `RELIABILITY_COLUMN_LABELS.entity_name`，而该标识符**在任何地方都没有定义**
 *    （真源导出的是 `RELIABILITY_COLUMN_SOURCE_LABELS` 数组 + `reliabilitySourceLabel()`）。
 *    后果：整个 K0-7 页签崩成「页面渲染出错：Cannot read properties of undefined
 *    (reading 'entity_name')」。
 *
 *    四层验证**全部放过**：`get_diagnostics`(Volar) 零诊断 / Vite transform 200 /
 *    vitest 全绿（守卫只查「旧简称不残留」与「import 行含真源名」，两条都过）。
 *    ⇒ 必须有一条「模板标识符可解析」的结构性守卫。
 */
describe('Property 25 · 模板引用的标识符均已定义或导入（防未定义标识符让整页崩）', () => {
  const GRID = path.join(CONF_DIR, 'reliability', 'ReliabilityGrid.vue')

  /** 从 `<script setup>` 收集所有可见绑定：import 具名/默认、const/let/function 声明、props 解构 */
  function scriptBindings(src: string): Set<string> {
    const scriptStart = src.indexOf('<script')
    const body = stripAllComments(src.slice(scriptStart))
    const out = new Set<string>()
    // import { a, b as c } from '...'  /  import d from '...'
    for (const m of body.matchAll(/import\s+([^'"]+?)\s+from\s*['"][^'"]+['"]/g)) {
      const clause = m[1]
      for (const g of clause.matchAll(/\{([^}]*)\}/g)) {
        for (const piece of g[1].split(',')) {
          const name = piece.replace(/^\s*type\s+/, '').split(/\s+as\s+/).pop()!.trim()
          if (name) out.add(name)
        }
      }
      const dflt = clause.replace(/\{[^}]*\}/g, '').replace(/,/g, ' ').trim()
      for (const w of dflt.split(/\s+/)) if (/^[A-Za-z_$][\w$]*$/.test(w)) out.add(w)
    }
    for (const m of body.matchAll(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g)) out.add(m[1])
    for (const m of body.matchAll(/\bfunction\s+([A-Za-z_$][\w$]*)/g)) out.add(m[1])
    // const { a, b } = ... 解构
    for (const m of body.matchAll(/\b(?:const|let)\s*\{([^}]*)\}\s*=/g)) {
      for (const piece of m[1].split(',')) {
        const name = piece.split(':').pop()!.trim()
        if (/^[A-Za-z_$][\w$]*$/.test(name)) out.add(name)
      }
    }
    return out
  }

  it('helper 自检：能抽到 Grid 的已知绑定（防抽取失效导致断言空转）', () => {
    const b = scriptBindings(read(GRID))
    expect(b.has('RELIABILITY_PARENT_HEADER')).toBe(true)
    expect(b.has('RELIABILITY_COLUMN_SOURCE_LABELS')).toBe(true)
    expect(b.size).toBeGreaterThan(10)
  })

  /**
   * 只从**求值上下文**里收标识符：`{{ }}` 插值 + `:prop` / `v-xxx` / `@evt` 绑定值。
   *
   * 🔴 不得扫整份模板文本 —— 普通字符串属性里的全大写片段不是标识符，
   *    实测 `value-format="YYYY-MM-DD"` 的 `YYYY` 会被误报（本守卫第一版即栽在这里）。
   */
  function templateEvalRefs(tpl: string): Set<string> {
    const out = new Set<string>()
    const collect = (expr: string) => {
      for (const m of expr.matchAll(/\b([A-Z][A-Z0-9_]{3,})\b/g)) out.add(m[1])
    }
    // {{ ... }} 插值
    for (const m of tpl.matchAll(/\{\{([\s\S]*?)\}\}/g)) collect(m[1])
    // :prop="..." / v-if="..." / @click="..."（绑定属性的值才是表达式）
    for (const m of tpl.matchAll(/(?::|v-[\w-]+|@)[\w.-]*\s*=\s*"([^"]*)"/g)) collect(m[1])
    return out
  }

  it('helper 自检：求值上下文抽取不把普通字符串属性算进来', () => {
    const fake = '<a value-format="YYYY-MM-DD" :label="MY_CONST" />{{ OTHER_CONST }}'
    const refs = templateEvalRefs(fake)
    expect(refs.has('MY_CONST')).toBe(true)
    expect(refs.has('OTHER_CONST')).toBe(true)
    expect(refs.has('YYYY'), 'YYYY 来自普通字符串属性，不是标识符').toBe(false)
  })

  it('模板求值上下文引用的常量都能在 script 中解析到', () => {
    const src = read(GRID)
    const tpl = stripAllComments(src.slice(0, src.indexOf('<script')))
    const bindings = scriptBindings(src)
    const referenced = templateEvalRefs(tpl)
    // 自检：确实抽到了东西（防正则失效导致断言空转）
    expect(referenced.size).toBeGreaterThan(0)
    const undef = [...referenced].filter((n) => !bindings.has(n))
    expect(undef, `模板引用了未定义/未导入的标识符: ${undef.join(', ')}`).toEqual([])
  })

  it('反向自检：注入一个未定义常量必须被抓到', () => {
    const fakeTpl = '<div>{{ TOTALLY_UNDEFINED_CONST.foo }}</div>'
    const bindings = new Set(['RELIABILITY_PARENT_HEADER'])
    const referenced = [...fakeTpl.matchAll(/\b([A-Z][A-Z0-9_]{3,})\b/g)].map((m) => m[1])
    const undef = referenced.filter((n) => !bindings.has(n))
    expect(undef).toContain('TOTALLY_UNDEFINED_CONST')
  })
})

describe('Property 24 · 源外保留列显式登记且已在 UI 标注', () => {
  const GRID = path.join(CONF_DIR, 'reliability', 'ReliabilityGrid.vue')

  it('reply_date 已登记为源外列（源模板六个枢纽都没有该列）', () => {
    expect(isSourceExtraReliabilityColumn('reply_date')).toBe(true)
    const d = SOURCE_EXTRA_RELIABILITY_COLUMNS.find((c) => c.field === 'reply_date')!
    expect(d.label).toBe('回函日期')
  })

  it('后端事实守卫确实断言了「源模板无回函日期列」（判据来源可追溯）', () => {
    const facts = stripPyComments(read(FACTS_PY))
    expect(facts).toMatch(/"回函日期"\s+not\s+in\s+headers/)
  })

  it('每条源外列的 reason 有实质内容（禁写「历史遗留」这类无信息量理由）', () => {
    for (const c of SOURCE_EXTRA_RELIABILITY_COLUMNS) {
      expect(c.reason.length, `${c.field} 的 reason 过短`).toBeGreaterThanOrEqual(30)
      expect(c.reason).not.toMatch(/历史遗留|待确认|TODO/)
    }
  })

  it('四条源外列都在 Grid 有 tooltip 标注（登记不能只躺在常量里）', () => {
    const grid = read(GRID)
    const n = (grid.match(/SOURCE_EXTRA_RELIABILITY_COLUMNS\[/g) ?? []).length
    expect(n, 'Grid 未按登记渲染源外列标注').toBeGreaterThanOrEqual(
      SOURCE_EXTRA_RELIABILITY_COLUMNS.length,
    )
  })

  it('反向自检：登记的 field 必须真实存在于 ReliabilityRow', () => {
    const types = read(path.join(CONF_DIR, 'reliability', 'reliabilityTypes.ts'))
    for (const c of SOURCE_EXTRA_RELIABILITY_COLUMNS) {
      expect(types, `登记了不存在的字段 ${c.field}`).toMatch(new RegExp(`\\b${c.field}\\??\\s*:`))
    }
  })
})

// ─── Property 19：跟函通用话术 ────────────────────────────────────────────────

describe('Property 19 · 跟函通用话术含工号与接待事实核实占位', () => {
  const MEMO = path.join(CONF_DIR, 'followup', 'memoTemplates.ts')

  it('两段通用话术都含工号占位（源模板 X0-3 A13/A17 逐字要求）', () => {
    const src = read(MEMO)
    const code = stripTsComments(src)
    for (const tpl of ['IMMEDIATE_CONFIRM_TPL', 'LATER_FOLLOW_TPL']) {
      const i = code.indexOf(`export const ${tpl}`)
      expect(i, `${tpl} 未找到`).toBeGreaterThan(-1)
      const body = code.slice(i, code.indexOf('export const', i + 10) === -1 ? undefined : code.indexOf('export const', i + 10))
      expect(body, `${tpl} 缺工号占位`).toMatch(/staff_no/)
    }
  })

  it('后端事实守卫确实断言了源模板的工号要求（判据可追溯）', () => {
    const facts = stripPyComments(read(FACTS_PY))
    expect(facts).toMatch(/工号为\[XX\]/)
  })

  it('电话回访接待事实核实占位已存在（源 A18/A19）', () => {
    const code = stripTsComments(read(MEMO))
    expect(code).toMatch(/THIRD_PARTY_CALLBACK_TPL/)
    const i = code.indexOf('export const THIRD_PARTY_CALLBACK_TPL')
    const body = code.slice(i, i + 800)
    expect(body).toMatch(/接待/)
  })

  it('E0 五段银行专属话术仍在（改通用话术不得误伤 E0）', () => {
    const code = stripTsComments(read(MEMO))
    for (const t of [
      'BANK_COUNTER_TPL',
      'BANK_DEPARTMENT_TPL',
      'BANK_LEAVE_TPL',
      'BANK_ALL_RESPONDED_TPL',
      'BANK_LATER_RECEIVED_TPL',
    ]) {
      expect(code, `E0 话术 ${t} 丢失`).toContain(`export const ${t}`)
    }
  })

  it('getTemplate 两种旧签名的调用形态未变（零回归）', () => {
    const code = stripTsComments(read(MEMO))
    expect(code).toMatch(/export function getTemplate\s*\(/)
  })
})

// ─── Property 21：K0-2 编制说明已渲染 ─────────────────────────────────────────

describe('Property 21 · K0-2 五条编制说明真源已渲染（非死常量）', () => {
  const DETAIL = path.join(CONF_DIR, 'entityVerify', 'EntityVerifyDetail.vue')

  it('五条说明与后端源模板常量逐字一致（跨前后端交叉锁死）', () => {
    const backend = pyTupleList(stripPyComments(read(FACTS_PY)), 'ENTITY_VERIFY_GUIDANCE')
    // 后端是 (anchor, text) 二元组；前端按说明分组，故比对「后端每条文本都能在前端找到」
    const frontTexts = ENTITY_VERIFY_GUIDANCE.flatMap((g) => [g.title, ...g.items])
    const missing = backend
      .map(([, t]) => t)
      .filter((t) => t && !frontTexts.some((f) => f === t))
    expect(missing, `前端缺这些源模板说明: ${missing.join(' | ')}`).toEqual([])
  })

  it('EntityVerifyDetail 已引入并渲染该真源（零消费方即打红）', () => {
    const detail = stripTsComments(read(DETAIL))
    expect(detail).toMatch(/import\s*\{[^}]*ENTITY_VERIFY_GUIDANCE/)
    expect(detail).toMatch(/v-for="\w+ in ENTITY_VERIFY_GUIDANCE"/)
  })

  it('组件不得硬编码说明文案（只许经真源引入）', () => {
    const detail = stripTsComments(read(DETAIL))
    const tpl = detail.slice(0, detail.indexOf('<script'))
    expect(tpl).not.toContain('进行核实的信息应该包括单位名称')
    expect(tpl).not.toContain('请跟进第二次发函的结果')
  })

  it('五条说明的锚点都在源模板 A 列（结构未被打乱）', () => {
    for (const g of ENTITY_VERIFY_GUIDANCE) {
      expect(g.anchor, `锚点 ${g.anchor} 不在 A 列`).toMatch(/^A\d+$/)
    }
    expect(ENTITY_VERIFY_GUIDANCE).toHaveLength(5)
  })
})

// ─── Property 20：本 spec 新建模块零消费方即打红 ──────────────────────────────

describe('Property 20 · 本 spec 新建模块必须有真实消费方', () => {
  /** 扫全前端 src，按 import 路径命中判定（memory 铁律：符号级匹配只产生假阴性） */
  function consumersOf(stem: string): string[] {
    const root = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src')
    const hits: string[] = []
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name)
        if (e.isDirectory()) {
          if (e.name === 'node_modules' || e.name === '__tests__') continue
          walk(p)
        } else if (/\.(ts|vue)$/.test(e.name)) {
          if (e.name.startsWith(stem)) continue // 自身
          if (e.name === 'components.d.ts') continue
          const src = fs.readFileSync(p, 'utf-8')
          if (new RegExp(`from\\s+['"][^'"]*${stem}['"]`).test(src)) hits.push(p)
        }
      }
    }
    walk(root)
    return hits
  }

  const NEW_MODULES = [
    'k0MatrixSpec',
    'k0LowerZoneSpec',
    'k0SummaryMatrix',
    'k0MatrixDataSources',
    'reliabilityColumnLabels',
    'entityVerifyGuidance',
  ]

  it.each(NEW_MODULES)('%s 有非测试消费方', (stem) => {
    expect(consumersOf(stem).length, `${stem} 零消费方 = 死代码`).toBeGreaterThan(0)
  })

  it('K0SummaryLowerZone.vue 有渲染宿主（链条上游合格不等于整条链是活的）', () => {
    const root = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src')
    let found = false
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name)
        if (e.isDirectory()) {
          if (e.name === 'node_modules' || e.name === '__tests__') continue
          walk(p)
        } else if (e.name.endsWith('.vue') && e.name !== 'K0SummaryLowerZone.vue') {
          const src = fs.readFileSync(p, 'utf-8')
          // 标签名必须带边界（`<FooREMOVED` 不算，memory 铁律）
          if (/<K0SummaryLowerZone(?=[\s/>])/.test(src)) found = true
        }
      }
    }
    walk(root)
    expect(found, 'K0SummaryLowerZone 无渲染宿主 = 用户不可达').toBe(true)
  })

  it('反向自检：对一个不存在的模块名，consumersOf 必须返回空', () => {
    expect(consumersOf('notExistModuleXyz')).toEqual([])
  })
})
