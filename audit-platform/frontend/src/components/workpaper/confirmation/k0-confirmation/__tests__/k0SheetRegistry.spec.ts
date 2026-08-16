/**
 * k0SheetRegistry.spec — K0 sheet 定位/展示分离 + 三条跨表引用索引号笔误
 *
 * spec: k0-confirmation-source-alignment，Task 12（Requirements 2.2 / 6.1 / 6.2）
 *
 * 判据真源两处，双向锁死：
 *   - 后端 `backend/tests/test_k0_source_template_facts.py::EXPECTED_VISIBLE_SHEETS`
 *     （openpyxl 直读源 xlsx，是 tab 名的唯一裁决者）
 *   - `k0LowerZoneSpec.K0_INDEX_TYPO_MAP`（笔误唯一真源；tooltip 文案必须由它派生）
 *
 * 🔴 读源码型断言一律先 `stripComments()` —— 本注册表的注释里如实写着被登记的
 *    源模板错值（`K1-12` / `K1-11` / `（K0-6）`），不剥注释会把说明文字数成真实声明。
 */

import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  K0_CONFIRMATION_SHEETS,
  K0_HIDDEN_SHEET_NAME,
  K0_SHEET_NAMES,
  K0_SHEET_REGISTRY,
  K0_VISIBLE_SHEET_COUNT,
  k0IndexTooltip,
  k0SheetRef,
} from '../k0SheetRegistry'
import { K0_INDEX_TYPO_MAP } from '../k0LowerZoneSpec'
import {
  buildCrossWorkpaperNavDefs,
  getCycleConfirmationMeta,
  isSameWorkbookNavTarget,
} from '../../coordination/cycleConfirmationMeta'

// ─── 仓库根定位：双哨兵具体文件向上查找（禁写死回退级数） ─────────────────────

function repoRoot(): string {
  let dir = path.resolve(__dirname)
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'tests', 'test_k0_source_template_facts.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    const up = path.dirname(dir)
    if (up === dir) break
    dir = up
  }
  throw new Error('[k0SheetRegistry.spec] 找不到仓库根（双哨兵均未命中）')
}

const ROOT = repoRoot()
const FACTS_PY = path.join(ROOT, 'backend', 'tests', 'test_k0_source_template_facts.py')
const REGISTRY_TS = path.join(__dirname, '..', 'k0SheetRegistry.ts')

const factsSrc = fs.readFileSync(FACTS_PY, 'utf-8')
const registrySrc = fs.readFileSync(REGISTRY_TS, 'utf-8')

/** 剥 TS 行注释与块注释（带字符串状态，避免吃掉 URL 与正则里的斜杠） */
function stripTsComments(src: string): string {
  let out = ''
  let i = 0
  let mode: 'code' | 'line' | 'block' | 'sq' | 'dq' | 'tpl' = 'code'
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (mode === 'code') {
      if (c === '/' && n === '/') { mode = 'line'; i += 2; continue }
      if (c === '/' && n === '*') { mode = 'block'; i += 2; continue }
      if (c === "'") mode = 'sq'
      else if (c === '"') mode = 'dq'
      else if (c === '`') mode = 'tpl'
      out += c; i++; continue
    }
    if (mode === 'line') { if (c === '\n') { mode = 'code'; out += c } ; i++; continue }
    if (mode === 'block') { if (c === '*' && n === '/') { mode = 'code'; i += 2; continue } i++; continue }
    // 字符串态
    if (c === '\\') { out += c + (n ?? ''); i += 2; continue }
    if ((mode === 'sq' && c === "'") || (mode === 'dq' && c === '"') || (mode === 'tpl' && c === '`')) {
      mode = 'code'
    }
    out += c; i++
  }
  return out
}

/** 从 python 源码抽一个字符串列表常量的元素（按 ASCII 方括号配对，不用固定字符窗口） */
function pyListStrings(src: string, name: string): string[] {
  const decl = new RegExp(`${name}\\s*(?::[^=\\n]*)?=\\s*\\[`).exec(src)
  if (!decl) throw new Error(`[k0SheetRegistry.spec] 后端未找到常量 ${name}（正则失效即空转）`)
  let i = decl.index + decl[0].length - 1
  let depth = 0
  const start = i
  for (; i < src.length; i++) {
    if (src[i] === '[') depth++
    else if (src[i] === ']') { depth--; if (depth === 0) break }
  }
  const body = src.slice(start, i + 1)
  return Array.from(body.matchAll(/"([^"\\]*)"|'([^'\\]*)'/g)).map((m) => m[1] ?? m[2])
}

const BACKEND_VISIBLE = pyListStrings(factsSrc, 'EXPECTED_VISIBLE_SHEETS')

// ─── Property A: 与后端源模板事实双向锁死 ─────────────────────────────────────

describe('K0 注册表 sheetName 与源 xlsx 可见 sheet 双向相等', () => {
  it('后端常量本身抽到了 10 条（防解析失效导致断言空转）', () => {
    expect(BACKEND_VISIBLE).toHaveLength(10)
    expect(BACKEND_VISIBLE[0]).toBe('底稿目录')
  })

  it('注册表 sheetName 集合 == 后端可见 sheet 集合（顺序亦同）', () => {
    expect([...K0_SHEET_NAMES]).toEqual(BACKEND_VISIBLE)
  })

  it('数量锚点与后端一致，且 hidden sheet 名逐字', () => {
    expect(K0_VISIBLE_SHEET_COUNT).toBe(BACKEND_VISIBLE.length)
    expect(K0_HIDDEN_SHEET_NAME).toBe('GT_Custom')
    // hidden sheet 绝不能出现在注册表里（它不渲染）
    expect(K0_SHEET_NAMES).not.toContain(K0_HIDDEN_SHEET_NAME)
  })

  it('K0 无此两表的槽位显式为 null（不得编造 tab 名）', () => {
    expect(k0SheetRef('diffChecklist')).toBeNull()
    expect(k0SheetRef('diffSecurities')).toBeNull()
  })

  it('每个非 null 槽位的 indexLabel 是 K0A / K0-1..K0-8 之一（展示值走底稿目录）', () => {
    const allowed = new Set(['底稿目录', 'K0A', ...Array.from({ length: 8 }, (_, i) => `K0-${i + 1}`)])
    for (const [key, ref] of Object.entries(K0_SHEET_REGISTRY)) {
      if (!ref) continue
      expect(allowed.has(ref.indexLabel), `${key} 的 indexLabel=${ref.indexLabel} 不在目录索引号集合内`).toBe(true)
    }
  })

  it('sheetName 与 indexLabel 必须不同（否则等于没接注册表，深链失效）', () => {
    for (const [key, ref] of Object.entries(K0_SHEET_REGISTRY)) {
      if (!ref || key === 'directory') continue
      expect(ref.sheetName, `${key} 的 sheetName 与 indexLabel 相同 = 仍是派生形态`).not.toBe(ref.indexLabel)
    }
  })
})

// ─── Property B: 三条笔误 tooltip 由真源派生 ─────────────────────────────────

describe('三条「跨表引用索引号笔误」有 tooltip 且由 K0_INDEX_TYPO_MAP 派生', () => {
  const SLOTS_WITH_TYPO = ['followup', 'diff', 'reliability'] as const

  it.each(SLOTS_WITH_TYPO)('%s 槽带 indexTypoNote 且含源出处/源字面/意图目标三要素', (slot) => {
    const ref = k0SheetRef(slot)!
    const note = ref.indexTypoNote ?? ''
    expect(note.length, `${slot} 缺 indexTypoNote`).toBeGreaterThan(10)
    const t = K0_INDEX_TYPO_MAP.find((x) => x.intended === ref.indexLabel)!
    expect(t, `${slot} 在笔误真源里没有对应条目`).toBeTruthy()
    expect(note, '缺源出处').toContain(t.sourceRef)
    expect(note, '缺源模板字面').toContain(t.literal)
    expect(note, '缺意图目标').toContain(t.intended)
  })

  it('恰好三个槽位带 indexTypoNote（防批量塞注释稀释信号）', () => {
    const withNote = Object.entries(K0_SHEET_REGISTRY)
      .filter(([, ref]) => !!ref?.indexTypoNote)
      .map(([k]) => k)
      .sort()
    expect(withNote).toEqual(['diff', 'followup', 'reliability'])
  })

  it('无笔误槽位不得带 indexTypoNote', () => {
    for (const [key, ref] of Object.entries(K0_SHEET_REGISTRY)) {
      if (!ref || (SLOTS_WITH_TYPO as readonly string[]).includes(key)) continue
      expect(ref.indexTypoNote, `${key} 不应有笔误说明`).toBeUndefined()
    }
  })

  it('注册表源码里不得抄第二份笔误文案（literal 只许经真源引入）', () => {
    const noc = stripTsComments(registrySrc)
    for (const t of K0_INDEX_TYPO_MAP) {
      expect(
        noc,
        `注册表代码区出现了硬编码的源模板字面「${t.literal}」= 双真源`,
      ).not.toContain(t.literal)
    }
    // 反向自检：这些字面确实出现在**注释**里（证明 stripComments 真的剥掉了东西）
    expect(registrySrc).toContain('K1-12')
    expect(noc).not.toContain('K1-12')
  })

  it('tooltip 拼装函数：有笔误时追加、无笔误时原样返回', () => {
    const withTypo = k0SheetRef('diff')!
    const noTypo = k0SheetRef('summary')!
    expect(k0IndexTooltip(withTypo, '差异调节表')).toContain('差异调节表（')
    expect(k0IndexTooltip(noTypo, '函证汇总表')).toBe('函证汇总表')
  })
})

// ─── Property C: 接线生效 + 其余循环零回归 ──────────────────────────────────

describe('cycleConfirmationMeta 已接 K0 注册表，其余四循环仍走派生', () => {
  it('K0 的 sheets 是真实 tab 名（不是 code 派生）', () => {
    const m = getCycleConfirmationMeta('K0')
    expect(m.cycle).toBe('K0')
    expect(m.sheets.summary?.sheetName).toBe('函证结果汇总表K0-1')
    expect(m.sheets.reliability?.sheetName).toBe('邮件传真回函可靠性验证K0-7')
    expect(m.sheets.fraud?.sheetName).toBe('函证程序舞弊风险评价表K0-8')
  })

  it('K0-1 等子 sheet 编码也能解析到同一份 meta', () => {
    for (const code of ['K0', 'K0-1', 'K0-5', 'K0-8']) {
      expect(getCycleConfirmationMeta(code).sheets.diff?.sheetName).toBe('函证差异调节表K0-4')
    }
  })

  it.each(['D0', 'E0', 'F0', 'H0'])('%s 仍是派生形态（sheetName === code），行为逐字不变', (cycle) => {
    const m = getCycleConfirmationMeta(cycle)
    for (const [slot, ref] of Object.entries(m.sheets)) {
      if (!ref || slot === 'program') continue
      expect(ref.sheetName, `${cycle}.${slot} 不应有 tab 名真源`).toBe(ref.indexLabel)
      expect(ref.indexTypoNote).toBeUndefined()
    }
  })

  it('K0 的 altSecondary / reliability / fraud 三槽有 tab 名 ⇒ 走同工作簿深链（可达性支点）', () => {
    const m = getCycleConfirmationMeta('K0')
    for (const slot of ['altSecondary', 'reliability', 'fraud'] as const) {
      const def = {
        wpCode: m.sheets[slot]!.indexLabel,
        label: m.sheets[slot]!.indexLabel,
        tooltip: '',
        sheetName: m.sheets[slot]!.sheetName,
      }
      expect(isSameWorkbookNavTarget(def), `${slot} 应走 ?sheet= 深链`).toBe(true)
    }
  })

  it('导航项：三条笔误说明出现在对应 tooltip 里', () => {
    const defs = buildCrossWorkpaperNavDefs('K0')
    const byLabel = new Map(defs.map((d) => [d.label, d]))
    for (const t of K0_INDEX_TYPO_MAP) {
      const d = byLabel.get(t.intended)
      expect(d, `导航项缺 ${t.intended}`).toBeTruthy()
      expect(d!.tooltip, `${t.intended} 的 tooltip 未标注源模板笔误`).toContain(t.sourceRef)
    }
  })

  it('反向自检：D0 的同名导航项 tooltip 不含任何笔误说明（证明上一条不是恒真）', () => {
    for (const d of buildCrossWorkpaperNavDefs('D0')) {
      expect(d.tooltip).not.toContain('源模板')
    }
  })
})

// ─── Property D: 模块初始化 smoke（循环依赖 / 真源缺条目会在此暴露） ────────────

describe('模块初始化 smoke', () => {
  it('注册表在 import 期已完成冻结且三条 tooltip 已成功派生', () => {
    // typoNoteFor 在 Object.freeze({...}) 求值期调用真源；若存在运行时循环依赖
    // 导致 K0_INDEX_TYPO_MAP 未初始化，import 本文件就会抛错，跑到这里即证明无循环。
    expect(Object.isFrozen(K0_SHEET_REGISTRY)).toBe(true)
    expect(Object.isFrozen(K0_CONFIRMATION_SHEETS)).toBe(true)
    expect(K0_INDEX_TYPO_MAP).toHaveLength(3)
    expect(Object.keys(K0_CONFIRMATION_SHEETS)).not.toContain('directory')
  })
})
