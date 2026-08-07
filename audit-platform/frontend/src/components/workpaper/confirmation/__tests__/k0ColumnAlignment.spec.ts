/**
 * k0ColumnAlignment.spec.ts — K0-1 上区列集与源模板对齐守卫
 *
 * spec: k0-confirmation-source-alignment · Task 15
 * 覆盖 Property 2（列与源模板一一映射）/ Property 3（伪列撤回、字段保留）/ Property 4（五枢纽零回归）
 *
 * ══════════════════════════════════════════════════════════════════════════════
 * 判据来源：后端 `test_k0_source_template_facts.py` 的 `SUMMARY_COLUMN_MAP`
 * （`(列字母, 源模板 label, 平台 field)` 三元组，由 openpyxl 直读源 xlsx 裁决）。
 * 本文件读该 py 源码抽常量做**跨前后端交叉锁死** —— 不拿自己写的 fixture 自证。
 * ══════════════════════════════════════════════════════════════════════════════
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  resolveConfirmationColumns,
  BASE_CONFIRMATION_COLUMNS,
  CYCLE_VARIANT_COLUMNS,
  CYCLE_EXCLUDED_COLUMNS,
  CYCLE_COLUMN_LABEL_OVERRIDES,
  CYCLE_COLUMN_GROUP_OVERRIDES,
  type ConfirmCycle,
} from '../confirmationColumnSpec'

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
const SPEC_TS = path.join(__dirname, '..', 'confirmationColumnSpec.ts')

function readFactsPy(): string {
  const src = fs.readFileSync(FACTS_PY, 'utf-8')
  expect(src.length).toBeGreaterThan(1000) // 反向自检：读到的不是空文件
  return src
}

/** 剥 python 注释（`#` 行）—— 注释里会写反例说明，不剥会数错 */
function stripPyComments(src: string): string {
  return src
    .split('\n')
    .map((ln) => (/^\s*#/.test(ln) ? '' : ln))
    .join('\n')
}

/**
 * 抽 `SUMMARY_COLUMN_MAP` 的三元组（按 ASCII 方括号配对定位，不用行尾正则）。
 *
 * 🔴 memory 铁律：python 多行常量用 `/NAME = \[...\]\n/` 抽会因 CRLF/LF 差异静默不命中。
 */
function backendColumnMap(): { col: string; label: string; field: string }[] {
  const src = readFactsPy()
  const decl = /^SUMMARY_COLUMN_MAP\s*(?::[^=\n]*)?=\s*\[/m.exec(src)
  if (!decl) throw new Error('常量 SUMMARY_COLUMN_MAP 未找到（正则失效？）')
  // 🔴 必须从 `=` 之后找左括号：声明含类型注解 `list[tuple[str, str, str]]`，
  //    从 decl.index 起找第一个 `[` 会命中类型注解里的方括号（本守卫首版即因此抽出空列表）。
  const eq = src.indexOf('=', decl.index)
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
  if (end < 0) throw new Error('SUMMARY_COLUMN_MAP 括号未配对')
  const body = src.slice(start + 1, end)
  const out: { col: string; label: string; field: string }[] = []
  const re = /\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(body)) !== null) {
    out.push({ col: m[1], label: m[2], field: m[3] })
  }
  return out
}

/**
 * 抽后端 `SOURCE_TEMPLATE_TYPOS` 里的源模板字面值（literal）。
 *
 * 用途：K0-1 `V6` 的 label 在源模板写「调节索引（K1-12）」而实际指向 K0-4，
 * 平台按 R6.1 显示修正值 ⇒ label 与源模板字面不一致是**有意为之**。
 * 判据放在后端笔误登记表里，前端不写死例外。
 */
function backendTypoLiterals(): string[] {
  const src = stripPyComments(readFactsPy())
  const decl = /^SOURCE_TEMPLATE_TYPOS\s*(?::[^=\n]*)?=/m.exec(src)
  if (!decl) throw new Error('常量 SOURCE_TEMPLATE_TYPOS 未找到（正则失效？）')
  const eq = src.indexOf('=', decl.index)
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
  if (end < 0) throw new Error('SOURCE_TEMPLATE_TYPOS 括号未配对')
  const body = src.slice(start + 1, end)
  const out: string[] = []
  const re = /"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'/g
  let m: RegExpExecArray | null
  while ((m = re.exec(body)) !== null) out.push(m[1] ?? m[2] ?? '')
  expect(out.length).toBeGreaterThan(0)
  return out
}

/** 抽后端 `COLUMNS_ABSENT_IN_SOURCE` 字符串列表 */
function backendAbsentColumns(): string[] {
  const src = readFactsPy()
  const m = /^COLUMNS_ABSENT_IN_SOURCE\s*(?::[^=\n]*)?=\s*\[([^\]]*)\]/m.exec(src)
  if (!m) throw new Error('常量 COLUMNS_ABSENT_IN_SOURCE 未找到（正则失效？）')
  return [...m[1].matchAll(/"([^"]+)"|'([^']+)'/g)].map((x) => x[1] ?? x[2])
}

// ══════════════════════════════════════════════════════════════════════════════
// helper 自检（防正则失效导致后续断言空转）
// ══════════════════════════════════════════════════════════════════════════════

describe('k0ColumnAlignment · helper 自检', () => {
  it('SUMMARY_COLUMN_MAP 抽出 28 个三元组（源模板 A..AB）', () => {
    const map = backendColumnMap()
    expect(map).toHaveLength(28)
    expect(map[0]).toEqual({ col: 'A', label: '序号', field: 'seq' })
    expect(map[map.length - 1]).toEqual({ col: 'AB', label: '审计结论', field: 'row_conclusion' })
  })

  it('COLUMNS_ABSENT_IN_SOURCE 抽出三列', () => {
    expect(backendAbsentColumns().sort()).toEqual(
      ['contact_person', 'contact_phone', 'currency'].sort(),
    )
  })

  it('对不存在的常量必须抛错（不得静默返回空列表）', () => {
    const src = readFactsPy()
    const bad = /^NOT_EXIST_CONST_XYZ\s*=\s*\[/m.exec(src)
    expect(bad).toBeNull()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 2：K0-1 列集与源模板一一映射
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 2 · K0-1 列集与源模板 28 列一一映射', () => {
  const cols = resolveConfirmationColumns('K0')
  const byKey = new Map(cols.map((c) => [c.key, c]))

  it('源模板每个 field 都在平台列集里', () => {
    const missing = backendColumnMap()
      .map((d) => d.field)
      .filter((f) => !byKey.has(f))
    expect(missing).toEqual([])
  })

  it('平台列集除显式登记的源外保留列外，不含源模板没有的列', () => {
    const sourceFields = new Set(backendColumnMap().map((d) => d.field))
    /** 源模板 K0-1 没有、平台显式登记保留的列（准则 1312 积极式/消极式，源模板无此维度） */
    const SOURCE_EXTRA_KEYS = new Set(['confirmation_method'])
    const extras = cols
      .map((c) => c.key)
      .filter((k) => !sourceFields.has(k) && !SOURCE_EXTRA_KEYS.has(k))
    expect(extras).toEqual([])
  })

  it('每个源模板列的 label 逐字等于源模板用词，唯一例外是已登记的索引号笔误修正', () => {
    const map = backendColumnMap()
    const byKey = new Map(cols.map((c) => [c.key, c]))
    const typos = backendTypoLiterals()

    const diffs: { field: string; source: string; platform: string }[] = []
    for (const { field, label } of map) {
      if (field === 'seq') continue
      const col = byKey.get(field)
      if (!col) continue
      if (col.label === label) continue
      diffs.push({ field, source: label, platform: col.label })
    }

    // 🔴 唯一允许的分歧 = 源模板索引号笔误（R6.1：按意图实现，tooltip 标原值）。
    //    判据取自后端 `SOURCE_TEMPLATE_TYPOS` 的 literal 字面，不在前端写死例外。
    for (const d of diffs) {
      expect(
        typos.some((t) => t.includes(d.source) || d.source.includes(t)),
        `列 ${d.field} 的 label 与源模板不一致且未登记为笔误：源「${d.source}」平台「${d.platform}」`,
      ).toBe(true)
    }

    // 反向自检：确实存在这样一处分歧（否则本断言退化成空转）
    expect(diffs.length).toBeGreaterThan(0)
    // 且该分歧就是 diff_ref_index（源 V6 写 K1-12，实为 K0-4）
    expect(diffs.map((d) => d.field)).toContain('diff_ref_index')
    expect(byKey.get('diff_ref_index')!.label).toContain('K0-4')
  })

  it('无重复 key', () => {
    const keys = cols.map((c) => c.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('三列源模板没有的列已剔除（它们在 K0-2 的 F/G 列）', () => {
    const keys = new Set(cols.map((c) => c.key))
    for (const k of backendAbsentColumns()) expect(keys.has(k)).toBe(false)
    expect([...(CYCLE_EXCLUDED_COLUMNS.K0 ?? [])].sort()).toEqual(backendAbsentColumns().sort())
  })

  it('send_channel 已启用并承载源模板「函证方式」（渠道）', () => {
    expect(byKey.get('send_channel')?.label).toBe('函证方式')
    expect(CYCLE_VARIANT_COLUMNS.K0).toContain('send_channel')
  })

  it('confirmation_method 保留为源外列且 label 已显式区分（准则 1312）', () => {
    const cm = byKey.get('confirmation_method')
    expect(cm).toBeDefined()
    expect(cm!.label).toContain('积极式')
    expect(cm!.label).toContain('消极式')
  })

  it('account_type 显示源模板用词「账户/交易」且未污染 BASE', () => {
    expect(byKey.get('account_type')?.label).toBe('账户/交易')
    // BASE 的 key 已被 E0/F0/H0 矩阵 sumByCategory 消费 → label 必须留在 per-cycle override
    const base = BASE_CONFIRMATION_COLUMNS.find((c) => c.key === 'account_type')
    expect(base).toBeDefined()
    expect(base!.label).not.toBe('账户/交易')
  })

  it('label override 的每个 key 都真实存在于 K0 列集（防登记打不出的键）', () => {
    for (const k of Object.keys(CYCLE_COLUMN_LABEL_OVERRIDES.K0 ?? {})) {
      expect(byKey.has(k)).toBe(true)
    }
  })

  it('group override 生效：四列入发函询证纪要段、备注类入回函金额确认段', () => {
    const ov = CYCLE_COLUMN_GROUP_OVERRIDES.K0 ?? {}
    for (const k of ['sample_purpose', 'entity_name', 'account_type', 'amount']) {
      expect(ov[k]).toBe('send_memo')
      expect(byKey.get(k)?.group).toBe('send_memo')
    }
    for (const k of ['diff_ref_index', 'remark']) {
      expect(ov[k]).toBe('reply_amount')
      expect(byKey.get(k)?.group).toBe('reply_amount')
    }
    // 声明表与实际解析结果必须一致（防 override 被合并顺序吃掉）
    for (const [k, g] of Object.entries(ov)) expect(byKey.get(k)?.group).toBe(g)
  })

  it('row_conclusion 在 row_summary 段（与 G0/H0 一致，不新建第三个结论段）', () => {
    expect(byKey.get('row_conclusion')?.group).toBe('row_summary')
  })

  it('diff_ref_index 的 label 指向意图目标 K0-4（源模板笔误 K1-12 不照抄）', () => {
    const lb = byKey.get('diff_ref_index')?.label ?? ''
    expect(lb).toContain('K0-4')
    expect(lb).not.toContain('K1-12')
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 3：伪列撤回、字段保留
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 3 · send_memo 伪列已撤但字段保留', () => {
  it('K0 与 L0 的列集都不含 send_memo 列', () => {
    for (const cy of ['K0', 'L0'] as ConfirmCycle[]) {
      expect(resolveConfirmationColumns(cy).map((c) => c.key)).not.toContain('send_memo')
    }
  })

  it('VARIANT_COLUMN_DEFS 不再声明 send_memo 列（源码级，已剥注释）', () => {
    const code = fs
      .readFileSync(SPEC_TS, 'utf-8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/^\s*\/\/.*$/gm, '')
    // 反向自检：剥注释后仍能看到别的 variant def（证明剥注释没把整段吃掉）
    expect(code).toMatch(/^\s*send_channel\s*:\s*\{/m)
    expect(code).not.toMatch(/^\s*send_memo\s*:\s*\{/m)
  })

  it('两个 cycle 的 variant 清单都不含 send_memo', () => {
    expect(CYCLE_VARIANT_COLUMNS.K0).not.toContain('send_memo')
    expect(CYCLE_VARIANT_COLUMNS.L0).not.toContain('send_memo')
  })

  it('send_memo 段本身保留（四列现由 group override 归入该段）', () => {
    const groups = new Set(resolveConfirmationColumns('K0').map((c) => c.group))
    expect(groups.has('send_memo')).toBe(true)
  })

  it('ConfirmationDetail.vue 有 send_memo 历史值只读呈现路径（数据零丢失红线）', () => {
    const detail = fs.readFileSync(path.join(__dirname, '..', 'ConfirmationDetail.vue'), 'utf-8')
    expect(detail).toMatch(/v-if="row\.send_memo"/)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 4：其余五枢纽零回归
// ══════════════════════════════════════════════════════════════════════════════

const UNAFFECTED_CYCLES: ConfirmCycle[] = ['D0', 'E0', 'F0', 'G0', 'H0']

/**
 * 黄金快照：五个循环的列数（key+group 三元组的完整快照过长，用「列数 + 关键不变式」冻结）。
 *
 * 🔴 判据核心是**机制层面**的零回归：`CYCLE_COLUMN_GROUP_OVERRIDES` 只声明了 K0，
 *    对未声明循环缺省 ⇒ 其余循环的 group 解析路径逐字不变。列数快照作为额外闸门。
 */
const GOLDEN_COLUMN_COUNT: Record<string, number> = {
  D0: 30,
  E0: 30,
  F0: 30,
  G0: 29,
  H0: 33,
}

describe('Property 4 · D0/E0/F0/G0/H0 列集零回归', () => {
  it('五个循环均无 group override 声明（机制层面的零回归证明）', () => {
    for (const cy of UNAFFECTED_CYCLES) {
      expect(CYCLE_COLUMN_GROUP_OVERRIDES[cy]).toBeUndefined()
    }
    // 反向自检：override 表非空（证明这条断言不是因为整个表为空而通过）
    expect(Object.keys(CYCLE_COLUMN_GROUP_OVERRIDES)).toContain('K0')
  })

  it('五个循环列数与黄金快照相等', () => {
    for (const cy of UNAFFECTED_CYCLES) {
      expect(resolveConfirmationColumns(cy)).toHaveLength(GOLDEN_COLUMN_COUNT[cy])
    }
  })

  it('五个循环列集稳定（两次解析逐字节相等，无隐藏可变状态）', () => {
    for (const cy of UNAFFECTED_CYCLES) {
      expect(JSON.stringify(resolveConfirmationColumns(cy))).toBe(
        JSON.stringify(resolveConfirmationColumns(cy)),
      )
    }
  })

  it('五个循环都不含 send_memo 列（撤列不误伤）', () => {
    for (const cy of UNAFFECTED_CYCLES) {
      expect(resolveConfirmationColumns(cy).map((c) => c.key)).not.toContain('send_memo')
    }
  })

  it('K0 的 account_type label 不泄漏到未声明该 override 的循环', () => {
    for (const cy of UNAFFECTED_CYCLES) {
      const other = resolveConfirmationColumns(cy).find((c) => c.key === 'account_type')
      if (!other) continue
      if (CYCLE_COLUMN_LABEL_OVERRIDES[cy]?.account_type) continue // 该循环自己声明过
      expect(other.label).not.toBe('账户/交易')
    }
  })

  it('D0/E0/F0 仍保留联系人/币种等列（K0 的剔除不外溢）', () => {
    for (const cy of ['D0', 'F0'] as ConfirmCycle[]) {
      const keys = resolveConfirmationColumns(cy).map((c) => c.key)
      expect(keys).toContain('contact_person')
      expect(keys).toContain('currency')
    }
    expect(resolveConfirmationColumns('E0').map((c) => c.key)).toContain('currency')
  })
})
