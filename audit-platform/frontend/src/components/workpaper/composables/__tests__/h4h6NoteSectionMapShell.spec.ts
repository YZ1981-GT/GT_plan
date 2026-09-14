/**
 * H4 / H6 薄壳映射交叉锁死守卫
 *
 * H4 与 H6 都**没有独立附注章节**：
 * - H4 工程物资 → 推 H2 在建工程章节（五、23 / 八、23）里的「工程物资」子表
 * - H6 固定资产清理 → 推 H1 固定资产章节（五、22 / 八、22）里的「固定资产清理」子表
 *
 * 因此两者的章节号真源分别在 `h2NoteSectionMap` / `h1NoteSectionMap`。
 * 但 `gen_note_wp_sync_registry.py` 用 **text-scan** 抽 `listed: '…'`，写
 * `export const H6_NOTE_SECTION = H1_NOTE_SECTION` 会让整条 wp_code 从
 * registry 消失（实测 H6 一直缺失、H4 因无 map 文件同样缺失，entries 62→64 才补齐）。
 *
 * 所以薄壳必须内联字面量 —— 双真源风险由本守卫消除。
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R4（Property 10）
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { H1_DISCLOSURE_SHEET_NAME, H1_LISTED_SUBTABLE, H1_NOTE_SECTION } from '../h1NoteSectionMap'
import {
  H2_DISCLOSURE_SHEET_NAME,
  H2_LISTED_SUBTABLE,
  H2_NOTE_SECTION,
  H2_SOE_SUBTABLE,
} from '../h2NoteSectionMap'
import {
  H4_DISCLOSURE_SHEET_NAME,
  H4_MATERIALS_SUBTABLE,
  H4_NOTE_SECTION,
  H4_SUMMARY_SUBTABLE,
  buildH4ListedSyncPayloads,
  buildH4SoeColumns,
  buildH4SoeSyncPayloads,
  resolveH4NoteSectionTarget,
} from '../h4NoteSectionMap'
import {
  H6_CLEARING_SUBTABLE,
  H6_DISCLOSURE_SHEET_NAME,
  H6_NOTE_SECTION,
  H6_SUMMARY_SUBTABLE,
} from '../h6NoteSectionMap'

const COMPOSABLES_DIR = resolve(__dirname, '..')

function src(file: string): string {
  return readFileSync(resolve(COMPOSABLES_DIR, file), 'utf-8')
}

/** 抽某常量的对象体（`export const X = { … }`），用于「内联字面量」断言 */
function constObjectBody(source: string, name: string): string | null {
  const i = source.indexOf(`export const ${name}`)
  if (i < 0) return null
  const eq = source.indexOf('=', i)
  if (eq < 0) return null
  const open = source.indexOf('{', eq)
  // `= H1_NOTE_SECTION` 形态：等号后到行尾没有 `{`
  const lineEnd = source.indexOf('\n', eq)
  if (open < 0 || (lineEnd >= 0 && open > lineEnd)) return null
  let depth = 0
  for (let k = open; k < source.length; k += 1) {
    if (source[k] === '{') depth += 1
    else if (source[k] === '}') {
      depth -= 1
      if (depth === 0) return source.slice(open, k + 1)
    }
  }
  return null
}

describe('H4 / H6 薄壳映射', () => {
  it('Property 10: H4 章节号与 sheet 名逐字等于 H2（共用章节）', () => {
    expect(H4_NOTE_SECTION.listed).toBe(H2_NOTE_SECTION.listed)
    expect(H4_NOTE_SECTION.soe).toBe(H2_NOTE_SECTION.soe)
    expect(H4_DISCLOSURE_SHEET_NAME.listed).toBe(H2_DISCLOSURE_SHEET_NAME.listed)
    expect(H4_DISCLOSURE_SHEET_NAME.soe).toBe(H2_DISCLOSURE_SHEET_NAME.soe)
  })

  it('Property 10: H6 章节号与 sheet 名逐字等于 H1（共用章节）', () => {
    expect(H6_NOTE_SECTION.listed).toBe(H1_NOTE_SECTION.listed)
    expect(H6_NOTE_SECTION.soe).toBe(H1_NOTE_SECTION.soe)
    expect(H6_DISCLOSURE_SHEET_NAME.listed).toBe(H1_DISCLOSURE_SHEET_NAME.listed)
    expect(H6_DISCLOSURE_SHEET_NAME.soe).toBe(H1_DISCLOSURE_SHEET_NAME.soe)
  })

  it('H4 / H6 的 X_NOTE_SECTION 必须是内联对象字面量（生成器 text-scan 硬约束）', () => {
    for (const [file, name] of [
      ['h4NoteSectionMap.ts', 'H4_NOTE_SECTION'],
      ['h6NoteSectionMap.ts', 'H6_NOTE_SECTION'],
      ['h4NoteSectionMap.ts', 'H4_DISCLOSURE_SHEET_NAME'],
      ['h6NoteSectionMap.ts', 'H6_DISCLOSURE_SHEET_NAME'],
    ] as const) {
      const body = constObjectBody(src(file), name)
      expect(body, `${file} 的 ${name} 不是内联对象字面量（写成标识符引用会让该 wp_code 从 registry 消失）`).toBeTruthy()
      expect(body, `${name} 缺 listed 字面量`).toMatch(/listed\s*:\s*['"]/)
      expect(body, `${name} 缺 soe 字面量`).toMatch(/soe\s*:\s*['"]/)
    }
  })

  it('常量对象体内不得写注释（注释里的 `listed: \'…\'` 会被生成器优先抓到）', () => {
    for (const [file, name] of [
      ['h4NoteSectionMap.ts', 'H4_NOTE_SECTION'],
      ['h6NoteSectionMap.ts', 'H6_NOTE_SECTION'],
      ['h4NoteSectionMap.ts', 'H4_DISCLOSURE_SHEET_NAME'],
      ['h6NoteSectionMap.ts', 'H6_DISCLOSURE_SHEET_NAME'],
    ] as const) {
      const body = constObjectBody(src(file), name) ?? ''
      expect(body, `${file}::${name} 对象体内含注释`).not.toMatch(/\/\/|\/\*/)
    }
  })

  it('反向自检：constObjectBody 对标识符引用形态返回 null', () => {
    const fixture = "export const X_NOTE_SECTION = Y_NOTE_SECTION\nexport const Z = { listed: 'a' }\n"
    expect(constObjectBody(fixture, 'X_NOTE_SECTION')).toBeNull()
    expect(constObjectBody(fixture, 'Z')).toContain("listed: 'a'")
  })

  it('H4 子表名委托 H2 真源，不自造字面量', () => {
    expect(H4_MATERIALS_SUBTABLE).toBe(H2_LISTED_SUBTABLE.materials)
    expect(H4_SUMMARY_SUBTABLE.listed).toBe(H2_LISTED_SUBTABLE.summary)
    expect(H4_SUMMARY_SUBTABLE.soe).toBe(H2_SOE_SUBTABLE.summary)
    // 薄壳源码不得出现子表名字面量（否则 H2 改名时静默产孤儿表）
    const s = src('h4NoteSectionMap.ts')
    expect(s).not.toContain(`'${H2_LISTED_SUBTABLE.materials}'`)
    expect(s).not.toContain(`'${H2_LISTED_SUBTABLE.summary}'`)
  })

  it('H6 子表名委托 H1 真源', () => {
    expect(H6_CLEARING_SUBTABLE).toBe(H1_LISTED_SUBTABLE.clearing)
    expect(H6_SUMMARY_SUBTABLE).toBe(H1_LISTED_SUBTABLE.summary)
  })

  it('H4 薄壳 re-export 真源 builder，不复制逻辑', () => {
    expect(typeof buildH4ListedSyncPayloads).toBe('function')
    expect(typeof buildH4SoeSyncPayloads).toBe('function')
    expect(typeof buildH4SoeColumns).toBe('function')
    const s = src('h4NoteSectionMap.ts')
    expect(s).toContain("from './h4DisclosureSyncPayload'")
    expect(s).toContain("from './h4SoeDisclosureSyncPayload'")
    // 薄壳内不得出现 push/payload 构造逻辑
    expect(s).not.toMatch(/sub_table_data|_sub_table_columns/)
  })

  it('resolveH4NoteSectionTarget 变体门与章节号正确', () => {
    expect(resolveH4NoteSectionTarget('soe', ['soe_standalone'])).toEqual({
      sectionId: H2_NOTE_SECTION.soe,
      sheetName: H2_DISCLOSURE_SHEET_NAME.soe,
      currentStandard: 'soe_standalone',
      chipValue: `Note:${H2_NOTE_SECTION.soe}`,
    })
    expect(resolveH4NoteSectionTarget('listed', ['soe_standalone'])).toBeNull()
  })
})
