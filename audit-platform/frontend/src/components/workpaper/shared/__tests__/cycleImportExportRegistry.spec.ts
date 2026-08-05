/**
 * cycleImportExportRegistry — F2 监盘 f2-st 与后端 _F2_ST_SPECS 对齐
 *   + G0/H0 函证枢纽 sheet key 与后端 `_SHEET_NAME_MAP` 双向锁死（见文件末尾）
 */
import { readFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

import { describe, it, expect } from 'vitest'
import { CYCLE_IMPORT_EXPORT } from '../cycleImportExportRegistry'

/**
 * 仓库根 —— 用**哨兵文件**向上查找，禁写死回退级数。
 *
 * 🔴 两条已实证的坑（memory 铁律）：
 *    ① 写死级数（如 `'../../../../../../..'`）在目录层数不同的守卫间照抄必 ENOENT，
 *       且症状是「文件级失败」而非断言失败 —— 极易被当噪声跳过，整份守卫从未执行过。
 *    ② 哨兵必须是**具体文件**不能是目录：`backend/app/routers` 目录在
 *       `audit-platform/` 层也存在（历史遗留空目录）→ 会提前停在错误的根上。
 */
function findRepoRoot(): string {
  let dir = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
  for (let i = 0; i < 12; i++) {
    if (existsSync(resolve(dir, 'backend/app/routers/wp_render_strategies/_g0_confirmation_import_export.py'))) {
      return dir
    }
    dir = dirname(dir)
  }
  throw new Error('未找到仓库根（哨兵文件缺失）—— 守卫必须打红而不是静默跳过')
}

const REPO_ROOT = findRepoRoot()

describe('cycleImportExportRegistry f2-st', () => {
  it('f2-st 包含 F2-24/25/26 及双表变体', () => {
    const entry = CYCLE_IMPORT_EXPORT['f2-st']
    expect(entry.apiPrefix).toBe('f2-st')
    expect([...entry.sheets]).toEqual(['F2-24', 'F2-24-count', 'F2-25', 'F2-25-floor', 'F2-26', 'F2-26-after'])
  })

  it('f2-st 不包含 F2-21', () => {
    expect(CYCLE_IMPORT_EXPORT['f2-st'].sheets).not.toContain('F2-21')
  })

  it('f2 main 不包含监盘 sheet', () => {
    const main = CYCLE_IMPORT_EXPORT.f2.sheets
    for (const code of ['F2-21', 'F2-22', 'F2-23', 'F2-24', 'F2-25', 'F2-26']) {
      expect(main).not.toContain(code)
    }
  })
})

describe('cycleImportExportRegistry f4', () => {
  it('f4 F4-7 对齐后端五段 sheet 名', () => {
    const sheets = CYCLE_IMPORT_EXPORT.f4.sheets
    expect(sheets).toContain('F4-7-payment-window')
    expect(sheets).toContain('F4-7-estimated-inbound')
    expect(sheets).toContain('F4-7-unprocessed-invoice')
    expect(sheets).toContain('F4-7-subsequent-payment')
    expect(sheets).toContain('F4-7-subsequent-increase')
    expect(sheets).not.toContain('F4-7-purchase')
    expect(sheets).not.toContain('F4-7-inbound')
    expect(sheets).not.toContain('F4-7-invoice')
  })
})

describe('cycleImportExportRegistry f5', () => {
  it('f5 sheets 与后端 _F5_SPECS 对齐', () => {
    expect([...CYCLE_IMPORT_EXPORT.f5.sheets]).toEqual([
      'F5-2', 'F5-3', 'F5-4', 'F5-5', 'F5-6', 'F5-8',
    ])
    expect(CYCLE_IMPORT_EXPORT.f5.apiPrefix).toBe('f5')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// G0 / H0 函证枢纽：sheet key 与后端 `_SHEET_NAME_MAP` 双向锁死
//
// spec: confirmation-orphan-and-amount-format-closure，Task 4（Property 5）
//
// 🔴 背景（本 spec 立项时的判断被勘查推翻，此处留证防再次"纠正"）：
//    立项时把 `sheets: ['G0-3S', 'G0-6']` 当成错值 —— 理由是 memory 已记
//    「`wp_index` 实测无 `G0-3S`」+ G0 目录索引号是 `G0-4`（证券差异）。
//    但逐个读后端 `_g0_confirmation_import_export.py` 后确认：`G0-3S` 是
//    **该 API 自己的 sheet 参数键**（`?sheet=G0-3S`），后端 `_SHEET_NAME_MAP`
//    再把它翻成源模板真实 tab 名 `函证差异核对表G0-3（证券投资）`。
//    它既不是 wp_code、也不是展示索引号 → **改值会直接打断导入导出三端点**。
//    故本守卫锁「前端键集 == 后端键集」，而不是锁「键集 == 目录索引号」。
const BACKEND_IE_MODULES: Record<string, string> = {
  g0: '_g0_confirmation_import_export.py',
  h0: '_h0_confirmation_import_export.py',
}

/**
 * 剥掉 Python 注释（带字符串状态，`#` 在字符串内不算注释起点）。
 *
 * 🔴 为什么必须剥：被注释掉的 map 条目（`# "G0-9X": "旧键",`）会被裸正则数成真键
 *    → 前后端键集比对凭空多一个键，守卫报的是自己解析缺陷而非真实漂移。
 *    本函数自带反向自检（见 `stripComments 反向自检` 用例，用**内联 fixture**
 *    而不是真实文件的注释 —— 真实注释日后可能被清理掉，自检会静默空转）。
 */
function stripPyComments(src: string): string {
  let out = ''
  let quote: string | null = null
  for (let i = 0; i < src.length; i++) {
    const c = src[i]
    if (quote) {
      out += c
      if (c === '\\') {
        out += src[i + 1] ?? ''
        i++
      } else if (c === quote) {
        quote = null
      }
      continue
    }
    if (c === '"' || c === "'") {
      quote = c
      out += c
      continue
    }
    if (c === '#') {
      while (i < src.length && src[i] !== '\n') i++
      out += '\n'
      continue
    }
    out += c
  }
  return out
}

/**
 * 抽 Python 字典字面量的体，用 **ASCII 花括号配对**定位收尾。
 *
 * 🔴 禁用 `\)\n` / `\n\}` 这类行尾敏感正则：CRLF/LF 差异会让它**静默不命中**，
 *    表现为「后端未找到常量」而不是断言失败。
 */
function extractPyDictBody(src: string, name: string): string {
  const clean = stripPyComments(src)
  const decl = clean.indexOf(`${name}:`)
  if (decl < 0) throw new Error(`未在源码中找到 ${name} 的声明（解析失效即打红，不静默空转）`)
  const open = clean.indexOf('{', decl)
  if (open < 0) throw new Error(`${name} 声明后未找到 '{'`)
  let depth = 0
  for (let i = open; i < clean.length; i++) {
    if (clean[i] === '{') depth++
    else if (clean[i] === '}') {
      depth--
      if (depth === 0) return clean.slice(open + 1, i)
    }
  }
  throw new Error(`${name} 的花括号未配对`)
}

/** 从后端 py 抽 `_SHEET_NAME_MAP` 的 key→tab 名（源码级交叉锁死，不靠人工抄一份） */
function backendSheetMap(moduleFile: string): Record<string, string> {
  const path = resolve(REPO_ROOT, 'backend/app/routers/wp_render_strategies', moduleFile)
  const body = extractPyDictBody(readFileSync(path, 'utf-8'), '_SHEET_NAME_MAP')
  const map: Record<string, string> = {}
  for (const m of body.matchAll(/"([^"]+)"\s*:\s*"([^"]+)"/g)) map[m[1]] = m[2]
  // 抽取结果必须非空 —— 否则「键集相等」会在两侧都空时假绿
  expect(Object.keys(map).length, `${moduleFile} 的 _SHEET_NAME_MAP 抽取为空`).toBeGreaterThan(0)
  return map
}

function backendSheetKeys(moduleFile: string): string[] {
  return Object.keys(backendSheetMap(moduleFile))
}

describe('cycleImportExportRegistry — G0/H0 与后端 sheet key 双向锁死', () => {
  for (const [cycle, moduleFile] of Object.entries(BACKEND_IE_MODULES)) {
    it(`${cycle} 前端 sheets 与后端 _SHEET_NAME_MAP 键集逐字相等`, () => {
      const feKeys = [...(CYCLE_IMPORT_EXPORT[cycle]?.sheets ?? [])]
      const beKeys = backendSheetKeys(moduleFile)
      expect(feKeys.length, `${cycle} 未登记在 registry`).toBeGreaterThan(0)
      expect([...feKeys].sort()).toEqual([...beKeys].sort())
    })

    it(`${cycle} apiPrefix 与后端模块前缀一致`, () => {
      expect(CYCLE_IMPORT_EXPORT[cycle]?.apiPrefix).toBe(cycle)
    })
  }

  it('G0-3S 是 API sheet key 而非 wp_code —— 注释已留证，防后来者按索引号"纠正"', () => {
    const src = readFileSync(
      resolve(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper/shared/cycleImportExportRegistry.ts'),
      'utf-8',
    )
    // 键值本身不许变
    expect(CYCLE_IMPORT_EXPORT.g0.sheets).toContain('G0-3S')
    // 且必须有说明「它是 API 参数键、不是 wp_code / 不是展示索引号」
    expect(src).toMatch(/G0-3S/)
    expect(src).toMatch(/API/)
    expect(src).toMatch(/wp_code/)
  })

  /**
   * 这条把「`G0-3S` 是 API key 而不是 wp_code」从**注释里的说法**变成**机器可验事实**：
   * 后端把它翻成源模板真实 tab 名（带全角括号）。若它真是 wp_code，就不会有这层翻译。
   */
  it('_SHEET_NAME_MAP[G0-3S] 映射到源模板真实 tab 名（全角括号）', () => {
    const map = backendSheetMap('_g0_confirmation_import_export.py')
    expect(map['G0-3S']).toBe('函证差异核对表G0-3（证券投资）')
    expect(map['G0-6']).toBe('替代程序检查表G0-6')
    // tab 名用全角括号（源模板事实）；若某天被"顺手改成"半角，这里先红
    expect(map['G0-3S']).toContain('（')
    expect(map['G0-3S']).not.toContain('(')
  })

  it('反向自检：必然不存在的 sheet 值不在后端键集内，且键集非空（防正则失效空转）', () => {
    const keys = backendSheetKeys('_g0_confirmation_import_export.py')
    expect(keys.length).toBeGreaterThan(0)
    expect(keys).not.toContain('G0-9X-DOES-NOT-EXIST')
    expect(CYCLE_IMPORT_EXPORT.g0.sheets).not.toContain('G0-9X-DOES-NOT-EXIST')
  })

  it('反向自检：抽一个必然不存在的 map 名必须抛错（证明抽取不是恒真）', () => {
    const src = readFileSync(
      resolve(REPO_ROOT, 'backend/app/routers/wp_render_strategies/_g0_confirmation_import_export.py'),
      'utf-8',
    )
    expect(() => extractPyDictBody(src, '_SHEET_NAME_MAP_DOES_NOT_EXIST')).toThrow()
  })

  /**
   * 🔴 用**内联 fixture** 而不是真实文件的注释：真实注释日后可能被清理，
   *    拿它做自检会静默空转（守卫看着绿、其实什么都没验）。
   */
  it('反向自检：stripComments 生效 —— 被注释掉的条目不得被数成真键', () => {
    const fixture = [
      '_SHEET_NAME_MAP: dict[str, str] = {',
      '    "A-1": "真实表A",  # 行尾注释里也有 "X-9": "假表"',
      '    # "B-2": "被注释掉的表",',
      '    "C-3": "标题里带#号的表",',
      '}',
    ].join('\n')
    const body = extractPyDictBody(fixture, '_SHEET_NAME_MAP')
    const keys = [...body.matchAll(/"([^"]+)"\s*:\s*"([^"]+)"/g)].map((m) => m[1])
    expect(keys).toEqual(['A-1', 'C-3'])
    expect(keys).not.toContain('B-2')
    expect(keys).not.toContain('X-9')
    // 不剥注释的朴素做法必然多抓 —— 证明 stripComments 不是空操作
    const naive = [...fixture.matchAll(/"([^"]+)"\s*:\s*"([^"]+)"/g)].map((m) => m[1])
    expect(naive).toContain('B-2')
  })
})
