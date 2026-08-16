/**
 * l0SheetMeta — L0 sheet「定位值 / 展示值」分离的跨前后端交叉锁死守卫
 *
 * spec: l0-confirmation-source-alignment，Task 19（Property 28 ~ 32）
 *
 * 判据真源 = `backend/tests/test_l0_source_template_facts.py`（openpyxl 直读
 * `backend/wp_templates/L/L0 债务循环函证.xlsx`）。本守卫**读后端源码抽常量**
 * 与前端 `l0SheetRegistry.ts` 双向比对 —— 这是防「改一侧漏一侧」的唯一可靠手段。
 *
 * 🔴 为什么必须读后端源码而不是各写一份期望值：
 *    各写一份 = 双真源，两侧漂移时守卫仍全绿（memory 已记的假绿范式）。
 *
 * 🔴 `REPO_ROOT` 用**双哨兵具体文件**向上查找：
 *    单哨兵不够稳（将来子目录出现同名文件即误停）；目录做哨兵会被
 *    `audit-platform/backend/app/routers`（历史遗留空目录）骗停。
 */

import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  L0_SHEET_REGISTRY,
  L0_CONFIRMATION_SHEETS,
  L0_SHEET_NAMES,
  L0_VISIBLE_SHEET_COUNT,
  L0_HIDDEN_SHEET_NAME,
  l0SheetRef,
  l0IndexTooltip,
  type L0SheetKey,
} from '../l0SheetRegistry'

// ─── REPO_ROOT 定位（双哨兵具体文件） ────────────────────────────────────────

const SENTINELS = [
  'backend/tests/test_l0_source_template_facts.py',
  'backend/wp_templates/L/L0 债务循环函证.xlsx',
]

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    if (SENTINELS.every((s) => fs.existsSync(path.join(dir, s)))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(
    `REPO_ROOT 定位失败：从 ${__dirname} 向上未找到全部哨兵 ${SENTINELS.join(' + ')}`,
  )
}

const REPO_ROOT = findRepoRoot()
const FACTS_PY = path.join(REPO_ROOT, 'backend/tests/test_l0_source_template_facts.py')

// ─── 从后端源码抽常量（ASCII 括号/方括号配对，源文中的全角括号不参与配对） ──

function stripPyComments(src: string): string {
  return src
    .split('\n')
    .map((line) => {
      // 行内 `#` 之前若有奇数个引号则不是注释；L0 常量区无此形态，直接按首个 # 截断
      const i = line.indexOf('#')
      return i >= 0 ? line.slice(0, i) : line
    })
    .join('\n')
}

/** 抽 `NAME = [ ... ]` 的字符串字面量列表（按 ASCII 方括号配对，避免行尾正则受 CRLF 影响） */
function pyStrList(src: string, name: string): string[] {
  const decl = new RegExp(`^${name}\\s*=\\s*\\[`, 'm')
  const m = decl.exec(src)
  if (!m) throw new Error(`后端常量未找到：${name}`)
  const open = src.indexOf('[', m.index)
  let depth = 0
  let end = -1
  for (let i = open; i < src.length; i += 1) {
    const ch = src[i]
    if (ch === '[') depth += 1
    else if (ch === ']') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  if (end < 0) throw new Error(`后端常量方括号未配对：${name}`)
  const body = src.slice(open + 1, end)
  return Array.from(body.matchAll(/"([^"]*)"/g)).map((x) => x[1])
}

/** 抽 `NAME = [(a, b, c), ...]` 的元组列表（每个元组内的字符串按序取出） */
function pyTupleList(src: string, name: string): string[][] {
  const decl = new RegExp(`^${name}\\s*=\\s*\\[`, 'm')
  const m = decl.exec(src)
  if (!m) throw new Error(`后端常量未找到：${name}`)
  const open = src.indexOf('[', m.index)
  let depth = 0
  let end = -1
  for (let i = open; i < src.length; i += 1) {
    const ch = src[i]
    if (ch === '[') depth += 1
    else if (ch === ']') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  if (end < 0) throw new Error(`后端常量方括号未配对：${name}`)
  const body = src.slice(open + 1, end)
  const out: string[][] = []
  for (const tm of body.matchAll(/\(([^)]*)\)/g)) {
    out.push(Array.from(tm[1].matchAll(/"([^"]*)"/g)).map((x) => x[1]))
  }
  return out
}

const FACTS_SRC_RAW = fs.readFileSync(FACTS_PY, 'utf-8')
const FACTS_SRC = stripPyComments(FACTS_SRC_RAW)

const BE_VISIBLE_SHEETS = pyStrList(FACTS_SRC, 'EXPECTED_VISIBLE_SHEETS')
const BE_HIDDEN_SHEETS = pyStrList(FACTS_SRC, 'EXPECTED_HIDDEN_SHEETS')
const BE_INDEX_ROWS = pyTupleList(FACTS_SRC, 'INDEX_SHEET_ROWS')
const BE_TYPOS = pyTupleList(FACTS_SRC, 'SOURCE_TEMPLATE_TYPOS')
const BE_CORRECT_REFS = pyTupleList(FACTS_SRC, 'CORRECT_INDEX_REFS')

// ─── 解析器自检（防「抽取失效 → 断言空转」） ────────────────────────────────

describe('L0SheetMeta: 后端常量解析器自检', () => {
  it('抽取结果非空且规模符合预期', () => {
    expect(BE_VISIBLE_SHEETS).toHaveLength(9)
    expect(BE_HIDDEN_SHEETS).toHaveLength(1)
    expect(BE_INDEX_ROWS).toHaveLength(8)
    expect(BE_TYPOS.length).toBeGreaterThanOrEqual(4)
    expect(BE_CORRECT_REFS).toHaveLength(1)
  })

  it('对不存在的常量必须 throw（不得静默返回空数组）', () => {
    expect(() => pyStrList(FACTS_SRC, 'NO_SUCH_CONSTANT_XYZ')).toThrow(/未找到/)
    expect(() => pyTupleList(FACTS_SRC, 'NO_SUCH_TUPLE_XYZ')).toThrow(/未找到/)
  })

  it('stripPyComments 确实剥掉了注释（反向自检）', () => {
    // 后端文件里有 `#:` 形式的 Sphinx 注释，剥前必须存在、剥后必须消失
    expect(FACTS_SRC_RAW).toContain('#:')
    expect(FACTS_SRC).not.toContain('#:')
  })
})

// ─── Property 28：注册表 sheetName ↔ 源模板 9 张可见 sheet 双射 ──────────────

describe('L0SheetMeta Property 28: 定位值与源模板可见 sheet 双射', () => {
  it('L0_SHEET_NAMES 与后端 EXPECTED_VISIBLE_SHEETS 逐位相等', () => {
    expect([...L0_SHEET_NAMES]).toEqual(BE_VISIBLE_SHEETS)
  })

  it('数量锚点 L0_VISIBLE_SHEET_COUNT 与两侧一致', () => {
    expect(L0_VISIBLE_SHEET_COUNT).toBe(BE_VISIBLE_SHEETS.length)
    expect(L0_SHEET_NAMES).toHaveLength(L0_VISIBLE_SHEET_COUNT)
  })

  it('注册表非 null 项的 sheetName 无重复', () => {
    const names = [...L0_SHEET_NAMES]
    expect(new Set(names).size).toBe(names.length)
  })

  it('hidden sheet 不在定位值集合内', () => {
    expect(L0_HIDDEN_SHEET_NAME).toBe(BE_HIDDEN_SHEETS[0])
    expect(L0_SHEET_NAMES).not.toContain(L0_HIDDEN_SHEET_NAME)
  })
})

// ─── Property 29：展示值 = 底稿目录索引号 ───────────────────────────────────

describe('L0SheetMeta Property 29: 展示值取自底稿目录索引号', () => {
  const beIndexLabels = BE_INDEX_ROWS.map((r) => r[1])

  it('八个函证槽位的 indexLabel 与底稿目录 F4:F11 逐字相等', () => {
    const feLabels = Object.entries(L0_SHEET_REGISTRY)
      .filter(([k]) => k !== 'directory')
      .map(([, ref]) => ref?.indexLabel ?? null)
      .filter((v): v is string => !!v)
    expect(feLabels).toEqual(beIndexLabels)
  })

  it('directory 槽位不参与索引号比对（它不是函证表）', () => {
    expect(L0_SHEET_REGISTRY.directory?.indexLabel).toBe('底稿目录')
    expect(beIndexLabels).not.toContain('底稿目录')
  })

  it('展示值一律 L0 前缀，不得残留 F0（源模板 tab 笔误不得渗进展示层）', () => {
    for (const label of beIndexLabels) {
      expect(label.startsWith('L0')).toBe(true)
      expect(label).not.toMatch(/F0/)
    }
  })
})

// ─── Property 30：笔误必须显式登记，不得静默改写 ────────────────────────────

describe('L0SheetMeta Property 30: 索引号笔误显式登记', () => {
  it('程序表 tab 名保留源模板笔误字面 F0A（定位值不得被"修正"）', () => {
    // 改 tab 名会打断 workpaper_sheet_classification 与既有数据；
    // 后端 resolve_program_template_code 已能从 F0A + L0 解析到 L0A。
    expect(L0_SHEET_REGISTRY.program?.sheetName).toBe('函证程序表F0A')
    expect(BE_VISIBLE_SHEETS).toContain('函证程序表F0A')
  })

  it('程序表槽位带 indexTypoNote，且同时提到源字面与目录裁决值', () => {
    const note = L0_SHEET_REGISTRY.program?.indexTypoNote ?? ''
    expect(note.length).toBeGreaterThan(8)
    expect(note).toContain('F0A')
    expect(note).toContain('L0A')
  })

  it('无笔误的槽位不得带 indexTypoNote（防批量塞注释稀释信号）', () => {
    for (const [key, ref] of Object.entries(L0_SHEET_REGISTRY)) {
      if (!ref || key === 'program') continue
      expect(ref.indexTypoNote, `${key} 不应有笔误说明`).toBeUndefined()
    }
  })

  it('后端笔误登记含 sheet_name 一条，且正确值为 L0A', () => {
    const sheetTypo = BE_TYPOS.find((t) => t[0].startsWith('sheet_name:'))
    expect(sheetTypo).toBeDefined()
    expect(sheetTypo?.[1]).toBe('F0A')
    expect(sheetTypo?.[2]).toBe('L0A')
  })

  it('另两处笔误是列标签/交叉引用，不在本注册表（各归其位）', () => {
    // L0-1!V6 / L0-2!AA6 属 confirmationColumnSpec 的 label override 半径。
    const locs = BE_TYPOS.map((t) => t[0])
    expect(locs).toContain('L0-1!V6')
    expect(locs).toContain('L0-2!AA6')
    const src = fs.readFileSync(
      path.join(
        REPO_ROOT,
        'audit-platform/frontend/src/components/workpaper/confirmation/l0-confirmation/l0SheetRegistry.ts',
      ),
      'utf-8',
    )
    // 注册表可以在注释里提到它们（说明归属），但不得把它们做成 sheet 槽位
    const slotKeys = Object.keys(L0_SHEET_REGISTRY)
    expect(slotKeys).not.toContain('L0-1!V6')
    expect(src).toContain('l0SheetRegistry')
  })

  it('L0-1!S33 的（L0-6）是正确索引号，不得被登记成笔误', () => {
    expect(BE_CORRECT_REFS[0][1]).toBe('L0-6')
    const typoLocs = BE_TYPOS.map((t) => t[0])
    expect(typoLocs).not.toContain('L0-1!S33')
  })
})

// ─── Property 31：L0 无此表的槽位一律 null，不得编造 ────────────────────────

describe('L0SheetMeta Property 31: 缺表槽位为 null', () => {
  it('diffChecklist / altSecondary / diffSecurities 三槽为 null', () => {
    expect(L0_SHEET_REGISTRY.diffChecklist).toBeNull()
    expect(L0_SHEET_REGISTRY.altSecondary).toBeNull()
    expect(L0_SHEET_REGISTRY.diffSecurities).toBeNull()
  })

  it('diffChecklist 为 null 与 hidden sheet 事实一致', () => {
    // 源模板确有该 sheet，但它是 hidden → 不渲染（R5.1）
    expect(BE_HIDDEN_SHEETS).toContain('函证差异检查表（示例）')
    expect(L0_SHEET_REGISTRY.diffChecklist).toBeNull()
  })

  it('l0SheetRef 对缺表槽位返回 null 而非 undefined', () => {
    expect(l0SheetRef('diffChecklist')).toBeNull()
    expect(l0SheetRef('altSecondary')).toBeNull()
  })

  it('非 null 槽位的 sheetName 必须非空串', () => {
    for (const [key, ref] of Object.entries(L0_SHEET_REGISTRY)) {
      if (!ref) continue
      expect(ref.sheetName, `${key}.sheetName`).toBeTruthy()
      expect(ref.indexLabel, `${key}.indexLabel`).toBeTruthy()
    }
  })
})

// ─── Property 32：注册表冻结 + 槽位子集与 meta 对齐 ─────────────────────────

describe('L0SheetMeta Property 32: 冻结与槽位子集', () => {
  it('L0_SHEET_REGISTRY 已 Object.freeze', () => {
    expect(Object.isFrozen(L0_SHEET_REGISTRY)).toBe(true)
  })

  it('L0_CONFIRMATION_SHEETS 剔除 directory 且其余键完全一致', () => {
    const full = Object.keys(L0_SHEET_REGISTRY).sort()
    const sub = Object.keys(L0_CONFIRMATION_SHEETS).sort()
    expect(sub).not.toContain('directory')
    expect(sub).toEqual(full.filter((k) => k !== 'directory'))
  })

  it('L0_CONFIRMATION_SHEETS 与 cycleConfirmationMeta.L0 的 *Code 逐槽一致', () => {
    const metaSrc = fs.readFileSync(
      path.join(
        REPO_ROOT,
        'audit-platform/frontend/src/components/workpaper/confirmation/coordination/cycleConfirmationMeta.ts',
      ),
      'utf-8',
    )
    const m = /\bL0:\s*\{([\s\S]{0,900}?)\n\s*\},/.exec(metaSrc)
    expect(m, 'cycleConfirmationMeta 里未找到 L0 段').toBeTruthy()
    const block = m![1]

    const pairs: Array<[keyof typeof L0_CONFIRMATION_SHEETS, string]> = [
      ['summary', 'summaryCode'],
      ['entityVerify', 'entityVerifyCode'],
      ['followup', 'followupCode'],
      ['diff', 'diffCode'],
      ['diffChecklist', 'diffChecklistCode'],
      ['diffSecurities', 'diffSecuritiesCode'],
      ['altPrimary', 'altPrimaryCode'],
      ['altSecondary', 'altSecondaryCode'],
      ['reliability', 'reliabilityCode'],
      ['fraud', 'fraudCode'],
    ]

    for (const [slot, field] of pairs) {
      const fm = new RegExp(`${field}:\\s*(null|'([^']*)')`).exec(block)
      expect(fm, `${field} 未在 L0 段找到`).toBeTruthy()
      const metaVal = fm![1] === 'null' ? null : fm![2]
      const ref = L0_CONFIRMATION_SHEETS[slot]
      // meta 存的是索引号（展示值），注册表的 indexLabel 应与之相等；
      // 两侧同为 null 表示 L0 无此表。
      expect(ref ? ref.indexLabel : null, `${slot} vs ${field}`).toBe(metaVal)
    }
  })

  it('l0IndexTooltip 只在有笔误时追加说明，其余原样返回', () => {
    const base = '底稿索引号'
    const withTypo = l0IndexTooltip(L0_SHEET_REGISTRY.program!, base)
    expect(withTypo).toContain(base)
    expect(withTypo).toContain('L0A')
    expect(withTypo.length).toBeGreaterThan(base.length)

    const noTypo = l0IndexTooltip(L0_SHEET_REGISTRY.summary!, base)
    expect(noTypo).toBe(base)
  })

  it('L0SheetKey 类型覆盖注册表全部键（编译期 + 运行期双证）', () => {
    const keys: L0SheetKey[] = Object.keys(L0_SHEET_REGISTRY) as L0SheetKey[]
    expect(keys).toContain('directory')
    expect(keys).toContain('program')
    expect(keys.length).toBe(Object.keys(L0_SHEET_REGISTRY).length)
  })
})
