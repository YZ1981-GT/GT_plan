/**
 * g0SheetRegistry.spec.ts — G0 sheet 定位/展示分离守卫
 *
 * spec: g0-confirmation-source-alignment，Task 10
 * Property 14（定位值与展示值分离且不混用）
 * Property 15（sheet 注册 ↔ 源模板 ↔ wp_code_overrides 三向一致）
 *
 * 裁决者链条（本文件**不连库**）：
 *   源模板 xlsx  ──openpyxl──▶ backend/tests/test_g0_source_template_facts.py
 *                              （SHEET_NAMES 10 条 / DIRECTORY_ENTRIES 9 条）
 *                                      │ 交叉锁死
 *                                      ▼
 *                              g0SheetRegistry.ts（本守卫的被测件）
 *                                      │ 交叉锁死
 *                                      ▼
 *                     backend/app/data/wp_code_overrides.json 三条全名键
 *
 * 后端那份守卫自己是 openpyxl 直读源 xlsx 的，故它等价于「离线 fixture」，
 * 且它变了本守卫会跟着红 —— 两侧不可能各自漂移。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  G0_CONFIRMATION_SHEETS,
  G0_SHEET_NAMES,
  G0_SHEET_REGISTRY,
  G0_SOURCE_SHEET_COUNT,
  g0IndexTooltip,
  g0SheetRef,
  type G0SheetKey,
} from '../g0SheetRegistry'
import { locatorOf } from '../../confirmation/coordination/crossWorkpaperNavLocator'
import { resolveSheetNameByDeepLink } from '@/utils/normalizeSheetName'

// ─── REPO_ROOT：哨兵**文件**向上查找（禁写死回退级数） ───────────────────────
//
// 🔴 两个哨兵都必须是具体文件，不能用目录 —— `audit-platform/backend/app/routers`
//    是历史遗留空目录，用目录做哨兵会在 `audit-platform` 层提前停下。
const SENTINELS = [
  join('backend', 'app', 'data', 'wp_code_overrides.json'),
  join('backend', 'tests', 'test_g0_source_template_facts.py'),
] as const

function findRepoRoot(start: string): string {
  let dir = resolve(start)
  for (let i = 0; i < 20; i += 1) {
    if (SENTINELS.every((s) => existsSync(join(dir, s)))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能从 ${start} 向上找到同时含哨兵文件的仓库根：${SENTINELS.join(' + ')}`)
}

const REPO_ROOT = findRepoRoot(__dirname)
const BACKEND_FACTS = join(REPO_ROOT, 'backend', 'tests', 'test_g0_source_template_facts.py')
const OVERRIDES_JSON = join(REPO_ROOT, 'backend', 'app', 'data', 'wp_code_overrides.json')
const FRONTEND_SRC = join(REPO_ROOT, 'audit-platform', 'frontend', 'src')
const META_TS = join(
  FRONTEND_SRC,
  'components/workpaper/confirmation/coordination/cycleConfirmationMeta.ts',
)
const NAV_VUE = join(
  FRONTEND_SRC,
  'components/workpaper/confirmation/coordination/CrossWorkpaperNav.vue',
)
const REGISTRY_TS = join(FRONTEND_SRC, 'components/workpaper/g0-confirmation/g0SheetRegistry.ts')

/** 去注释（块 + 行 + HTML）—— 守卫与被守卫源码的注释里都写着反例字样，不剥必假红/假绿 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

// ─── 从后端事实守卫里抽源模板真源（不连库、不读 xlsx） ───────────────────────

function parseBackendSheetNames(): string[] {
  const src = readFileSync(BACKEND_FACTS, 'utf-8')
  const m = src.match(/SHEET_NAMES:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\(([\s\S]*?)\n\)/)
  if (!m) throw new Error('未能在后端事实守卫里定位 SHEET_NAMES（正则失效？）')
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1])
}

function parseBackendDirectoryIndexLabels(): string[] {
  const src = readFileSync(BACKEND_FACTS, 'utf-8')
  const m = src.match(/DIRECTORY_ENTRIES:\s*tuple\[[\s\S]*?\]\s*=\s*\(([\s\S]*?)\n\)/)
  if (!m) throw new Error('未能在后端事实守卫里定位 DIRECTORY_ENTRIES（正则失效？）')
  return [...m[1].matchAll(/\(\s*"[^"]*"\s*,\s*"([^"]+)"\s*\)/g)].map((x) => x[1])
}

/** 三处笔误的 (槽位, tab 名里的索引号, 底稿目录索引号) */
const TYPO_SLOTS: ReadonlyArray<[G0SheetKey, string, string]> = [
  ['diffSecurities', 'G0-3', 'G0-4'],
  ['diff', 'G0-4', 'G0-5'],
  ['fraud', 'F0-8', 'G0-8'],
]

const NON_NULL_KEYS = (Object.keys(G0_SHEET_REGISTRY) as G0SheetKey[]).filter(
  (k) => G0_SHEET_REGISTRY[k] !== null,
)

// ─── Property 14: 定位值与展示值分离且不混用 ─────────────────────────────────

describe('Property 14: 定位值（tab 名）与展示值（目录索引号）分离且不混用', () => {
  it('每条非空声明同时有 sheetName 与 indexLabel，且都非空串', () => {
    expect(NON_NULL_KEYS.length).toBe(G0_SOURCE_SHEET_COUNT)
    for (const key of NON_NULL_KEYS) {
      const ref = G0_SHEET_REGISTRY[key]!
      expect(typeof ref.sheetName, key).toBe('string')
      expect((ref.sheetName ?? '').trim().length, key).toBeGreaterThan(0)
      expect(ref.indexLabel.trim().length, key).toBeGreaterThan(0)
    }
  })

  it('G0 无此表的两个槽显式为 null（不编造 sheet）', () => {
    expect(G0_SHEET_REGISTRY.diffChecklist).toBeNull()
    expect(G0_SHEET_REGISTRY.altSecondary).toBeNull()
    expect(g0SheetRef('diffChecklist')).toBeNull()
  })

  it('三处笔误：indexLabel ≠ tab 名内的索引号片段，且 indexTypoNote 同时含两者', () => {
    for (const [slot, tabIndex, dirIndex] of TYPO_SLOTS) {
      const ref = g0SheetRef(slot)!
      // tab 名里确实带着那个笔误索引号
      expect(ref.sheetName, slot).toContain(tabIndex)
      // 展示值取底稿目录裁决值，与 tab 名内的索引号片段不同
      expect(ref.indexLabel, slot).toBe(dirIndex)
      expect(ref.indexLabel, slot).not.toBe(tabIndex)
      // 说明非空且把两个值都写出来（R6.3：不得静默改写）
      expect(ref.indexTypoNote, slot).toBeTruthy()
      expect(ref.indexTypoNote!, slot).toContain(tabIndex)
      expect(ref.indexTypoNote!, slot).toContain(dirIndex)
      expect(ref.indexTypoNote!.length, slot).toBeGreaterThan(15)
    }
  })

  it('无笔误的槽不得带 indexTypoNote（防说明泛滥成噪声）', () => {
    const typoKeys = new Set(TYPO_SLOTS.map(([s]) => s))
    for (const key of NON_NULL_KEYS) {
      if (typoKeys.has(key)) continue
      expect(G0_SHEET_REGISTRY[key]!.indexTypoNote, key).toBeUndefined()
    }
  })

  it('g0IndexTooltip 只在有笔误时追加说明（六枢纽由此不受影响）', () => {
    expect(g0IndexTooltip(g0SheetRef('summary')!, '函证汇总表')).toBe('函证汇总表')
    expect(g0IndexTooltip(g0SheetRef('diff')!, '差异调节表')).toContain('G0-5')
  })

  it('行为级：同工作簿跳转的载荷只用 sheetName，不用 label / indexLabel / wpCode', () => {
    // 🔴 2026-08-04 由「源码字面断言」改为「行为断言」：
    //    原断言写死 `emit('navigate-sheet', item.sheetName`，而 spec
    //    confirmation-orphan-and-amount-format-closure Task 5 把定位值计算抽成了
    //    纯函数 `locatorOf()`（`<script setup>` 不允许运行时 export，守卫要直接调它）。
    //    字面断言因此打红，但**不变式没变** —— 故改为直接验 `locatorOf` 的返回值，
    //    既跟着重构走，又比字面匹配强（字面存在 ≠ 值正确）。
    for (const key of NON_NULL_KEYS) {
      const ref = G0_SHEET_REGISTRY[key]!
      const locator = locatorOf({
        wpCode: ref.indexLabel,
        sheetName: ref.sheetName,
        sameWorkbook: true,
      })
      // G0 全部 10 张 sheet 都在同一工作簿 → 定位值必须是真实 tab 名
      expect(locator, key).toBe(ref.sheetName)
      // 绝不能把展示值（可能带源模板笔误）当定位值
      if (ref.indexLabel !== ref.sheetName) {
        expect(locator, key).not.toBe(ref.indexLabel)
      }
    }
    // 组件确实走 locatorOf 这一个出口（防有人绕开它另写一条 emit）
    const nav = stripComments(readFileSync(NAV_VUE, 'utf-8'))
    expect(nav).toContain("emit('navigate-sheet', locatorOf(item)")
    // 绝不能把展示值当定位值发出去
    expect(nav).not.toMatch(/navigate-sheet'\s*,\s*item\.(label|wpCode|indexLabel)/)
    const meta = stripComments(readFileSync(META_TS, 'utf-8'))
    // isSameWorkbookNavTarget 的判据只看 sheetName
    expect(meta).toMatch(/isSameWorkbookNavTarget[\s\S]{0,240}def\.sheetName/)
    // 定位值不得直接取自 `*Code` 展示字段或 indexLabel
    // （`sheetName: m.altSecondaryCode ? null : sheetNameOf(...)` 是**条件**不是取值，故要求
    //   `*Code` 后紧跟结束符才算违规）
    expect(meta).not.toMatch(/sheetName:\s*m\.\w+Code\s*[,}\n]/)
    expect(meta).not.toMatch(/sheetName:\s*[\w.]*indexLabel/)
  })

  it('反向自检：把展示索引号当定位值会解析到**另一张**表（故定位必须用 sheetName）', () => {
    const securities = g0SheetRef('diffSecurities')!
    // 展示值 'G0-4' 属于「证券投资」差异表，但深链按它解析会命中「非证券投资」那张
    const wrong = resolveSheetNameByDeepLink(G0_SHEET_NAMES, securities.indexLabel)
    expect(wrong).not.toBe(securities.sheetName)
    expect(wrong).toBe(g0SheetRef('diff')!.sheetName)
    // 用 sheetName 才能精确命中
    expect(resolveSheetNameByDeepLink(G0_SHEET_NAMES, securities.sheetName!)).toBe(
      securities.sheetName,
    )
  })

  it('反向自检：stripComments 确实剥掉注释里的反例（否则上面的断言全是空转）', () => {
    const fixture = `
      // emit('navigate-sheet', item.label, x)
      /* sheetName: def.indexLabel */
      <!-- navigate-sheet', item.wpCode -->
      const keep = "navigate-sheet"
    `
    const out = stripComments(fixture)
    expect(out).not.toContain('item.label')
    expect(out).not.toContain('def.indexLabel')
    expect(out).not.toContain('item.wpCode')
    expect(out).toContain('const keep = "navigate-sheet"')
  })
})

// ─── Property 15: 注册 ↔ 源模板 ↔ override 三向一致 ──────────────────────────

describe('Property 15: sheet 注册与源模板 / wp_code_overrides 三向一致', () => {
  const backendSheets = parseBackendSheetNames()
  const backendIndexes = parseBackendDirectoryIndexLabels()

  it('抽取结果非空且数量锚定（防正则失效导致断言空转）', () => {
    expect(backendSheets.length).toBe(G0_SOURCE_SHEET_COUNT)
    expect(backendIndexes.length).toBe(G0_SOURCE_SHEET_COUNT - 1) // 底稿目录自身无索引号
  })

  it('10 个 sheetName 与源模板 wb.sheetnames 逐字逐位相等', () => {
    expect([...G0_SHEET_NAMES]).toEqual(backendSheets)
  })

  it('9 个 indexLabel 与底稿目录 F4:F12 逐字逐位相等（索引号唯一裁决者）', () => {
    const labels = (Object.keys(G0_SHEET_REGISTRY) as G0SheetKey[])
      .filter((k) => k !== 'directory' && G0_SHEET_REGISTRY[k] !== null)
      .map((k) => G0_SHEET_REGISTRY[k]!.indexLabel)
    expect(labels).toEqual(backendIndexes)
  })

  it('wp_code_overrides.json 含三条含笔误的**全名键**（skip/尾码键不能替代）', () => {
    const overrides = JSON.parse(readFileSync(OVERRIDES_JSON, 'utf-8')) as Record<string, string>
    for (const [slot] of TYPO_SLOTS) {
      const full = g0SheetRef(slot)!.sheetName!
      expect(Object.prototype.hasOwnProperty.call(overrides, full), full).toBe(true)
      expect(String(overrides[full]).trim(), full).not.toBe('')
      expect(String(overrides[full]), full).not.toBe('skip')
    }
  })

  it('G0_CONFIRMATION_SHEETS 是 11 槽位子集且不含 directory（供 meta 使用）', () => {
    const keys = Object.keys(G0_CONFIRMATION_SHEETS)
    expect(keys).not.toContain('directory')
    expect(keys.length).toBe(Object.keys(G0_SHEET_REGISTRY).length - 1)
    expect(G0_CONFIRMATION_SHEETS.summary!.sheetName).toBe('函证结果汇总表G0-1')
  })

  it('反向自检：凭空造的 tab 名不在源模板清单里；且不存在的 G0-3S 未被当作 sheet', () => {
    expect(backendSheets).not.toContain('审定表G0-1')
    expect(G0_SHEET_NAMES).not.toContain('审定表G0-1')
    expect(G0_SHEET_NAMES.some((n) => n.includes('G0-3S'))).toBe(false)
    const registrySrc = stripComments(readFileSync(REGISTRY_TS, 'utf-8'))
    expect(registrySrc).not.toContain('G0-3S')
  })
})
