/**
 * cycleImportExportRegistry — F2 监盘 f2-st 与后端 _F2_ST_SPECS 对齐
 *   + G0/H0 函证枢纽 sheet key 与后端 `_SHEET_NAME_MAP` 双向锁死（见文件末尾）
 */
import { readFileSync, existsSync, readdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

import { describe, it, expect } from 'vitest'
import { CYCLE_IMPORT_EXPORT, MANUAL_OVERRIDES } from '../cycleImportExportRegistry'
import {
  CATALOG_PREFIX_TOTAL,
  GENERATED_IMPORT_EXPORT,
  GENERATED_PREFIX_COUNT,
} from '../cycleImportExportRegistry.generated'

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

// ═══════════════════════════════════════════════════════════════════════════
// registry 三向锁死 —— Wave 1 Task 3
// spec: workpaper-import-export-lifecycle-closure（R4.1 / 4.2 / 4.3）
//
// ## 三向 = catalog ↔ registry ↔ 运行期真实端点
//
// 为什么不能只比两向：本轮实证发现 **catalog 与运行期路由两侧都曾有缺口**
// （catalog 声明 `g7-method` 而运行期是 `g7-equity-method`，15 个 sheet 因此
// 在批量导出里走 `skip_reason=no_adapter` 静默跳过）。只锁「registry ↔ catalog」
// 会把 catalog 自身的错值当成真源；只锁「registry ↔ 路由」会漏掉 catalog 缺口。
//
// ## 🔴 端点清单为什么必须由后端守卫提供而不是前端解析
//
// `wp_render_strategies/` 99 个 `*_import_export.py` 里 **63 个零 `@router.` 装饰器**
// —— 端点由 `create_cycle_import_export_router(api_prefix=...)` 在导入期生成。
// 前端无法靠读 py 源码数出端点（那是 memory 明令禁止的 grep 式守卫）。
// 故运行期端点集由后端 `backend/tests/test_ie_route_inventory.py` 负责锁死，
// 本文件只锁「registry 的 apiPrefix 必须能在 catalog 找到对应条目」这一向，
// 并断言 registry 不含已知死前缀（后端专属 router 未提供的那批）。
// ═══════════════════════════════════════════════════════════════════════════

/**
 * ACNR catalog（`backend/data/acnr/global_catalog.json`）里启用 I/E 的 sheet。
 *
 * 这是 `bulk_tab` 全链的路由真源：
 * `manifest_builder.build_manifest` → `wp_bulk_tab_export.list_export_sheets`
 * → `acnr.manifest.list_import_export` → `acnr.catalog.list_sheets`。
 * 前端 registry 若与它不同源，等于平台内并存两套 I/E 目录。
 */
function catalogIeEntries(): { sheetCode: string; apiPrefix: string; parentWpCode: string }[] {
  const path = resolve(REPO_ROOT, 'backend/data/acnr/global_catalog.json')
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as {
    sheets?: {
      sheet_code?: string
      parent_wp_code?: string
      import_export?: { enabled?: boolean; api_prefix?: string }
    }[]
  }
  const out: { sheetCode: string; apiPrefix: string; parentWpCode: string }[] = []
  for (const s of raw.sheets ?? []) {
    const ie = s.import_export
    if (!ie?.enabled || !ie.api_prefix) continue
    out.push({
      sheetCode: s.sheet_code ?? '',
      apiPrefix: ie.api_prefix,
      parentWpCode: s.parent_wp_code ?? '',
    })
  }
  return out
}

/**
 * 扫全部后端 I/E 模块，建 `api_prefix → sheet 键集` 映射（带缓存）。
 *
 * 🔴 为什么不按「前缀 → 模块名」的命名约定猜文件（本判据改过一轮）：
 * 约定并不成立 —— `f2-st` 的模块是 `_f2_stocktake_import_export.py`、
 * `f2-val` 是 `_f2_valuation_…`、`f2-spe` 是 `_f2_special_…`。
 * 按 `_f2_st_import_export.py` 去找必然 miss，导致 `F2-24-count` 等
 * 3 个真实存在的传输键被判成"不存在"（假红）。
 *
 * 改为**反向**：逐模块读出它自己声明的前缀，再把该模块里的 sheet 键归到该前缀下。
 * 前缀有两种声明形态，都要收：
 *   · 工厂族 `create_cycle_import_export_router(api_prefix='k5', …)`
 *   · 手写族 `@router.get('/api/workpapers/{wp_id}/f2-st/export-data')`
 */
let _backendMapCache: Map<string, Set<string>> | null = null

function backendPrefixToSheetKeys(): Map<string, Set<string>> {
  if (_backendMapCache) return _backendMapCache
  const dir = resolve(REPO_ROOT, 'backend/app/routers/wp_render_strategies')
  const out = new Map<string, Set<string>>()

  /** 从一份 py 源码里抽 sheet 键字面量。 */
  const keysOf = (src: string): Set<string> => {
    const keys = new Set<string>()
    // 形态一：wp_code 式传输键 `F2-14` / `F4-7-payment-window`
    for (const m of src.matchAll(/["']([A-Z]\d+(?:-[\w]+)+)["']/g)) keys.add(m[1])
    // 形态二：以模块常量声明的附注键 `SHEET_LISTED = "F2-note-listed"`
    //   这类键不出现在主模块里（主模块只 import 常量名），必须在定义处抽。
    for (const m of src.matchAll(
      /^\s*SHEET_\w*\s*(?::\s*str\s*)?=\s*["']([^"']+)["']/gm,
    )) {
      keys.add(m[1])
    }
    return keys
  }

  /**
   * 🔴 为什么要跟随一层相对 import（2026-08-12 实证，本函数第二轮修正）
   *
   * `_f2_disclosure_import_export.py` / `_j1_disclosure_import_export.py` 这类
   * **附注逻辑模块没有自己的路由声明**（沿用主模块既有三路由，刻意不新建 router）
   * ⇒ 它们的 `prefixes.size === 0` ⇒ 上一版在这里 `continue`，**整个文件被跳过**
   * ⇒ 它们定义的 `F2-note-listed` / `F2-note-soe` 永远抽不到
   * ⇒ registry 里登记这两个**后端真实支持**的键会被判成"不存在"（假红）。
   *
   * 实测：后端 `_f2_import_export._SUPPORTED_SHEETS` 共 21 键
   * （`set(_F2_SHEET_CONFIGS)` 18 + `{F2-1}` + `set(_DISCLOSURE_SHEETS)` 2），
   * 而旧抽键只拿到 19 个 —— 差的正好是两个附注键。
   *
   * ⇒ 改为：主模块（有前缀的）额外并入它 `from ._x import …` 的那些同目录模块的键。
   *   只跟一层，不做传递闭包 —— 够用且不会把无关模块的键混进来。
   */
  const srcCache = new Map<string, string>()
  const readSrc = (name: string): string => {
    let s = srcCache.get(name)
    if (s === undefined) {
      const full = resolve(dir, name)
      s = existsSync(full) ? stripPyComments(readFileSync(full, 'utf-8')) : ''
      srcCache.set(name, s)
    }
    return s
  }

  for (const name of readdirSync(dir)) {
    if (!name.endsWith('_import_export.py')) continue
    const src = readSrc(name)

    const prefixes = new Set<string>()
    for (const m of src.matchAll(/api_prefix\s*=\s*["']([^"']+)["']/g)) prefixes.add(m[1])
    for (const m of src.matchAll(
      /@router\.\w+\(\s*["']\/api\/workpapers\/\{wp_id\}\/([\w-]+)\//g,
    )) {
      prefixes.add(m[1])
    }
    if (prefixes.size === 0) continue

    const keys = keysOf(src)
    // 并入被本模块 import 的同目录模块（附注逻辑模块无路由声明，只能这样够到）
    for (const m of src.matchAll(/from\s+\.(\w+)\s+import/g)) {
      for (const k of keysOf(readSrc(`${m[1]}.py`))) keys.add(k)
    }
    if (keys.size === 0) continue

    for (const p of prefixes) {
      if (!out.has(p)) out.set(p, new Set())
      for (const k of keys) out.get(p)!.add(k)
    }
  }

  _backendMapCache = out
  return out
}

/**
 * 「工厂造了 router 但从未 include_router」的死前缀 —— **清单不在此处写死**。
 *
 * 它们在 `wp_render_strategies/_{x}_import_export.py` 里由工厂声明了
 * `api_prefix`，但 `router_registry` 从未注册 ⇒ 运行期零端点。这些前缀的能力
 * 实际由 `backend/app/routers/{name}.py` 专属 router 提供，且专属 router 的
 * URL 前缀往往**不同名**（`h9` → `h9-lease-liabilities`）。
 * ⇒ registry 抄工厂声明的 `api_prefix` 会得到 404 的前缀。本断言钉死这一点。
 *
 * 🔴 真源 = 后端守卫 `backend/tests/test_ie_route_inventory.py` 的
 *    `_TRULY_DEAD_FACTORY_PREFIXES` —— 那是**运行期路由表**实测出来的，前端启不了
 *    FastAPI，在这里抄一份必 stale。
 *
 * 抄一份的代价已实证一次（2026-08-15，spec `x3-adjustment-entry-import-export`
 * 任务 10.1）：这里曾写死 19 项（`h9`/`l2`/`l6`/`l7`/`l8`/`m1`~`m10`/`n1`~`n3`/`n5`）。
 * X-3 给其中 **16 个**短前缀补了形态 A 三态端点（宿主是
 * `_x3_adjustment_import_export`，**不是**同名工厂模块），后端基线已在任务 6.3
 * 同步下调到 3 项，而这里的字面量没跟着改 ⇒ 生成器把这 16 个前缀派生进 registry
 * 后，本判据把**正确的新增**打成红。清单一旦写死，就只有两种结局：锁死缺陷，
 * 或打红修复（memory 记的假绿第三源）。改成解析真源后，父 spec Task 25 下调死集
 * 时前端自动跟随。
 */
let _routeInventorySrc: string | null = null

function routeInventorySrc(): string {
  if (_routeInventorySrc === null) {
    _routeInventorySrc = stripPyComments(
      readFileSync(resolve(REPO_ROOT, 'backend/tests/test_ie_route_inventory.py'), 'utf-8'),
    )
  }
  return _routeInventorySrc
}

/**
 * 从后端守卫读 `<name> = frozenset({...})` 的字符串字面量集合。
 *
 * 🔴 抽不到必须**抛错**而不是返回空集：空集会让「死前缀不在 registry」恒绿。
 *    行首锚定 + 花括号配对（禁行尾敏感正则，CRLF/LF 差异会静默不命中）。
 */
function backendPrefixSet(name: string): readonly string[] {
  const src = routeInventorySrc()
  const decl = new RegExp(`^${name}\\s*=\\s*frozenset\\(`, 'm').exec(src)
  if (!decl) {
    throw new Error(`未在 test_ie_route_inventory.py 找到 ${name} 声明 —— 解析失效即打红，不静默空转`)
  }
  const open = src.indexOf('{', decl.index)
  if (open < 0) throw new Error(`${name} 的 frozenset( 之后未找到 '{'`)
  let depth = 0
  let body: string | null = null
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) {
        body = src.slice(open + 1, i)
        break
      }
    }
  }
  if (body === null) throw new Error(`${name} 的花括号未配对`)
  const out = [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1])
  if (out.length === 0) {
    throw new Error(`${name} 抽取为空 —— 两侧都空会让断言假绿，故直接打红`)
  }
  return out
}

/** 当前判据命中的死前缀（后端实测，X-3 施加后为 h9/l7/l8） */
const DEAD_FACTORY_PREFIXES: readonly string[] = backendPrefixSet('_TRULY_DEAD_FACTORY_PREFIXES')
/** X-3 施加前的死集（19 项）—— 只作结构自洽的分母，不当生效基线 */
const PRE_X3_DEAD_FACTORY_PREFIXES: readonly string[] = backendPrefixSet(
  '_PRE_X3_DEAD_FACTORY_PREFIXES',
)
/** X-3 补了形态 A 三态端点的 16 个短前缀 */
const X3_SHAPE_A_PREFIXES: readonly string[] = backendPrefixSet('_X3_SHAPE_A_PREFIXES')

describe('registry 三向锁死 — catalog 侧', () => {
  it('catalog I/E 条目非空（扫描面自检，防两侧都空时假绿）', () => {
    const entries = catalogIeEntries()
    expect(entries.length).toBeGreaterThan(200)
    const prefixes = new Set(entries.map((e) => e.apiPrefix))
    expect(prefixes.size).toBeGreaterThan(50)
  })

  it('registry 每个 apiPrefix 都能在 catalog 找到条目', () => {
    const catalogPrefixes = new Set(catalogIeEntries().map((e) => e.apiPrefix))
    const missing: string[] = []
    for (const [key, entry] of Object.entries(CYCLE_IMPORT_EXPORT)) {
      if (!catalogPrefixes.has(entry.apiPrefix)) missing.push(`${key}→${entry.apiPrefix}`)
    }
    expect(
      missing,
      `registry 的 apiPrefix 在 catalog 无对应条目（批量导出取不到路由元数据）: ${missing.join(', ')}`,
    ).toEqual([])
  })

  it('registry 不含已知死前缀（工厂声明但从未注册的那些）', () => {
    const used = new Set(Object.values(CYCLE_IMPORT_EXPORT).map((e) => e.apiPrefix))
    const dead = DEAD_FACTORY_PREFIXES.filter((p) => used.has(p))
    expect(
      dead,
      `registry 登记了运行期零端点的死前缀（会 404）: ${dead.join(', ')}\n`
      + '→ 这些前缀的能力由 backend/app/routers/{name}.py 专属 router 提供，'
      + 'URL 前缀常不同名（h9 → h9-lease-liabilities）',
    ).toEqual([])
  })

  /**
   * 🔴 X-3 的 16 个短前缀已在运行期被点亮 ⇒ 它们**必须**在 registry 里。
   *
   * 这条与上一条互为反向：上一条防「登记了 404 的前缀」，这条防「有端点却没登记」
   * （= 后端有能力、用户点不到，本 spec 的缺口本体）。判据落在**门面最终值**上，
   * 且要求它来自 `GENERATED_IMPORT_EXPORT` —— 手写塞进 `MANUAL_OVERRIDES` 也算没
   * 走真源（catalog 更新时会 stale）。
   */
  it('🔴 X-3 点亮的 16 个短前缀：不在死集内，且已由生成器派生进 registry', () => {
    expect(X3_SHAPE_A_PREFIXES.length, 'X-3 短前缀集抽取异常').toBe(16)

    const stillDead = X3_SHAPE_A_PREFIXES.filter((p) => DEAD_FACTORY_PREFIXES.includes(p))
    expect(
      stillDead,
      `以下前缀在运行期有形态 A 三态端点，却仍被算作死前缀: ${stillDead.join(', ')}\n`
      + '→ 后端 _TRULY_DEAD_FACTORY_PREFIXES 与实测不符，先核后端基线',
    ).toEqual([])

    const registered = new Set(Object.values(CYCLE_IMPORT_EXPORT).map((e) => e.apiPrefix))
    const missing = X3_SHAPE_A_PREFIXES.filter((p) => !registered.has(p))
    expect(
      missing,
      `以下 X-3 短前缀后端已注册三态端点，但 registry 未登记（下拉点不到）: ${missing.join(', ')}\n`
      + '→ 跑 python backend/scripts/fix/gen_cycle_import_export_registry.py --apply',
    ).toEqual([])

    const notGenerated = X3_SHAPE_A_PREFIXES.filter((p) => !(p in GENERATED_IMPORT_EXPORT))
    expect(
      notGenerated,
      `以下 X-3 短前缀不在生成文件里（疑被手写进 MANUAL_OVERRIDES，catalog 更新即 stale）: `
      + notGenerated.join(', '),
    ).toEqual([])
  })

  it('反向自检：死前缀清单来自后端真源、只许收缩、不得混入已点亮的前缀', () => {
    // 非空自检 —— 空清单会让「registry 不含死前缀」恒绿
    expect(DEAD_FACTORY_PREFIXES.length).toBeGreaterThan(0)
    // 分母自检：X-3 前的死集必须仍是 19 项（它是历史事实，不随施加变化）
    expect(PRE_X3_DEAD_FACTORY_PREFIXES.length).toBe(19)
    // 只许收缩：当前死集必须是 X-3 前死集的子集
    const notShrunk = DEAD_FACTORY_PREFIXES.filter(
      (p) => !PRE_X3_DEAD_FACTORY_PREFIXES.includes(p),
    )
    expect(
      notShrunk,
      `死集新增了 X-3 前不在册的前缀（疑有工厂模块被 include_router 漏了）: ${notShrunk.join(', ')}`,
    ).toEqual([])
    // 收缩量恰为已点亮的 16 个（多复活/少复活都要求裁决，不静默）
    const revived = PRE_X3_DEAD_FACTORY_PREFIXES.filter(
      (p) => !DEAD_FACTORY_PREFIXES.includes(p),
    ).sort()
    expect(revived, '死集收缩量与 X-3 的 16 个短前缀不吻合').toEqual(
      [...X3_SHAPE_A_PREFIXES].sort(),
    )
    // 这些前缀确实出现在工厂模块的 api_prefix 声明里（否则清单是凭空写的）
    const sample = [...DEAD_FACTORY_PREFIXES]
    for (const p of sample) {
      const file = resolve(
        REPO_ROOT,
        `backend/app/routers/wp_render_strategies/_${p}_import_export.py`,
      )
      expect(existsSync(file), `${file} 应存在（死代码模块仍在磁盘上）`).toBe(true)
      const src = stripPyComments(readFileSync(file, 'utf-8'))
      expect(src, `_${p}_import_export.py 应声明 api_prefix="${p}"`).toMatch(
        new RegExp(`api_prefix\\s*=\\s*["']${p}["']`),
      )
    }
  })
})

describe('registry 覆盖面', () => {
  it('registry 覆盖 catalog 全部启用前缀', () => {
    const catalogPrefixes = new Set(catalogIeEntries().map((e) => e.apiPrefix))
    const registered = new Set(Object.values(CYCLE_IMPORT_EXPORT).map((e) => e.apiPrefix))
    const uncovered = [...catalogPrefixes].filter((p) => !registered.has(p)).sort()
    expect(
      uncovered,
      `catalog 有 ${catalogPrefixes.size} 个启用前缀，registry 只登记 ${registered.size} 个，`
      + `缺 ${uncovered.length} 个：\n  ${uncovered.join(', ')}\n`
      + '→ 跑 python backend/scripts/fix/gen_cycle_import_export_registry.py --apply',
    ).toEqual([])
  })

  /**
   * registry 的 `sheets[]` 必须落在**真源并集**内：catalog 的 `sheet_code`
   * ∪ 后端 I/E 模块 specs 的键。
   *
   * 🔴 判据真源为什么是并集（2026-08-10 实证，本条判据改过一轮）：
   *
   * 初版只比 catalog 的 `sheet_code`，结果 F3/F4 的 **11 个复合变体键**
   * （`F3-7-debit` / `F4-8-credit` / `F4-7-*` …）全部假红 —— 它们**确实存在**
   * 于后端 specs（实测 `_f3_import_export` 16 键 / `_f4_import_export` 24 键），
   * 只是 catalog 只登记基础 `sheet_code`（f3 仅 `F3-2`~`F3-6`）。
   *
   * 更关键：`F3-7` 这个基础码在 catalog 里**根本不存在**，所以连
   * 「按 `startsWith(基础码 + '-')` 认变体」的兜底也救不了 —— 必须直接读后端。
   */
  it('registry sheets 里的键落在「catalog ∪ 后端 specs」真源内（不得凭 wp_code 推断）', () => {
    const byPrefix = new Map<string, Set<string>>()
    for (const e of catalogIeEntries()) {
      if (!byPrefix.has(e.apiPrefix)) byPrefix.set(e.apiPrefix, new Set())
      byPrefix.get(e.apiPrefix)!.add(e.sheetCode)
    }

    const backendKeysFor = (prefix: string): Set<string> =>
      backendPrefixToSheetKeys().get(prefix) ?? new Set<string>()

    // G0/H0 的键由 `_SHEET_NAME_MAP` 锁死（上方已有专门断言），此处豁免
    const TRANSPORT_KEY_CYCLES = new Set(['g0', 'h0'])

    const bad: string[] = []
    for (const [key, entry] of Object.entries(CYCLE_IMPORT_EXPORT)) {
      if (TRANSPORT_KEY_CYCLES.has(key)) continue
      const known = new Set([
        ...(byPrefix.get(entry.apiPrefix) ?? []),
        ...backendKeysFor(entry.apiPrefix),
      ])
      if (known.size === 0) continue // 该前缀无真源信息，由覆盖面断言负责
      for (const sheet of entry.sheets) {
        if (!known.has(sheet)) bad.push(`${key}/${sheet}`)
      }
    }
    expect(
      bad,
      `registry sheets 不在「catalog ∪ 后端 specs」内（端点会 400 不支持的sheet）: ${bad.join(', ')}`,
    ).toEqual([])
  })

  it('反向自检：后端 specs 抽键确实能抽到 F3/F4 变体键', () => {
    // 防上一条的 `backendKeysFor` 恒返空集 —— 那会让整条断言空转
    const src = stripPyComments(
      readFileSync(
        resolve(REPO_ROOT, 'backend/app/routers/wp_render_strategies/_f3_import_export.py'),
        'utf-8',
      ),
    )
    const keys = [...src.matchAll(/["']([A-Z]\d+(?:-[\w]+)+)["']/g)].map((m) => m[1])
    expect(keys, 'F3 后端模块未抽到任何 sheet 键 ⇒ 抽取正则失效').toContain('F3-7-debit')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 生成器 ↔ 门面 一致性（Task 13）
// ═══════════════════════════════════════════════════════════════════════════

describe('registry 门面 —— generated + MANUAL_OVERRIDES', () => {
  it('MANUAL_OVERRIDES 键集与生成器的 MANUAL_PREFIXES 逐字一致', () => {
    const genSrc = readFileSync(
      resolve(REPO_ROOT, 'backend/scripts/fix/gen_cycle_import_export_registry.py'),
      'utf-8',
    )
    const m = genSrc.match(/MANUAL_PREFIXES:\s*frozenset\[str\]\s*=\s*frozenset\(\{([^}]*)\}\)/s)
    expect(m, '未在生成器中找到 MANUAL_PREFIXES 声明').toBeTruthy()
    const pyKeys = [...(m![1].matchAll(/"([^"]+)"/g))].map((x) => x[1]).sort()
    const tsKeys = Object.keys(MANUAL_OVERRIDES).sort()
    expect(tsKeys, 'MANUAL_OVERRIDES 与生成器 MANUAL_PREFIXES 不一致 ⇒ 会两处都有或都没有').toEqual(pyKeys)
  })

  it('generated 与 MANUAL_OVERRIDES 键集互斥（同一前缀不得两处都登记）', () => {
    const overlap = Object.keys(GENERATED_IMPORT_EXPORT).filter(
      (k) => k in MANUAL_OVERRIDES,
    )
    expect(overlap, `前缀在两处重复登记: ${overlap.join(', ')}`).toEqual([])
  })

  it('门面 = generated ∪ MANUAL_OVERRIDES', () => {
    const expected = new Set([
      ...Object.keys(GENERATED_IMPORT_EXPORT),
      ...Object.keys(MANUAL_OVERRIDES),
    ])
    expect(new Set(Object.keys(CYCLE_IMPORT_EXPORT))).toEqual(expected)
  })

  /**
   * R4.6 零回归 —— 判据从「逐字节不变」改为「**不得丢键** + 新增须显式登记」。
   *
   * 🔴 为什么改（2026-08-12）
   *
   * 「逐字节不变」把改造前的值当成了正确性基线，而实测它**本身就有缺口**：
   * f2 当时只有 18 键（恰好等于 `_F2_SHEET_CONFIGS`），而后端
   * `_f2_import_export._SUPPORTED_SHEETS` 有 21 键 —— 少的 `F2-1` /
   * `F2-note-listed` / `F2-note-soe` 都是真实支持、且附注页早已挂了下拉的。
   * 于是这条守卫会**把修复打红、把缺陷锁死**，正是 memory 记的假绿第三源
   * 「守卫把错值当基线锁死（把真源改对反而打红）」。
   *
   * 零回归真正要防的是**丢键**（改造把既有能力弄没了），不是禁止补键。
   * 故：既有键必须仍在（子集断言）；多出来的键必须在 `INTENTIONAL_ADDITIONS`
   * 里写明依据，避免"允许新增"退化成"随便加"。
   */
  it('🔴 R4.6 零回归：既有 10 个 key 一个都不许丢，新增须显式登记', () => {
    // 立项基线（改造前 `CYCLE_IMPORT_EXPORT` 的全部内容，逐字抄录）
    const BASELINE: Record<string, string[]> = {
      f1: ['F1-2', 'F1-5', 'F1-6', 'F1-7', 'F1-7-credit', 'F1-7-post'],
      f2: ['F2-3', 'F2-4', 'F2-5', 'F2-6', 'F2-7', 'F2-8', 'F2-9', 'F2-10', 'F2-11',
           'F2-12', 'F2-13', 'F2-14', 'F2-19', 'F2-20', 'F2-29', 'F2-30', 'F2-31', 'F2-32'],
      'f2-val': ['F2-33', 'F2-34', 'F2-35', 'F2-38', 'F2-39', 'F2-40', 'F2-41',
                 'F2-42', 'F2-43', 'F2-44', 'F2-47', 'F2-48', 'F2-49', 'F2-52'],
      'f2-spe': ['F2-55', 'F2-56', 'F2-57', 'F2-58', 'F2-61', 'F2-62', 'F2-63', 'F2-64',
                 'F2-65', 'F2-66', 'F2-67', 'F2-68', 'F2-69', 'F2-70', 'F2-71', 'F2-72'],
      'f2-st': ['F2-24', 'F2-24-count', 'F2-25', 'F2-25-floor', 'F2-26', 'F2-26-after'],
      f3: ['F3-2', 'F3-3', 'F3-4', 'F3-5', 'F3-6', 'F3-7-debit', 'F3-7-credit', 'F3-7-subsequent'],
      f4: ['F4-2', 'F4-3', 'F4-5', 'F4-6', 'F4-7-payment-window', 'F4-7-estimated-inbound',
           'F4-7-unprocessed-invoice', 'F4-7-subsequent-payment', 'F4-7-subsequent-increase',
           'F4-8-debit', 'F4-8-credit', 'F4-9'],
      f5: ['F5-2', 'F5-3', 'F5-4', 'F5-5', 'F5-6', 'F5-8'],
      g0: ['G0-3S', 'G0-6'],
      h0: ['H0-5'],
    }
    /**
     * 立项基线之后**有依据补进去**的键。每条都必须能在后端白名单里查到。
     *
     * f2（3 键）：后端 `_f2_import_export._SUPPORTED_SHEETS` =
     *   `set(_F2_SHEET_CONFIGS)`(18) | `{'F2-1'}` | `set(_DISCLOSURE_SHEETS)`(2) = 21。
     *   立项值只覆盖了中间那 18 个，漏掉审定表 `F2-1` 与两个附注键；而
     *   `F2TabDisclosureListed/Soe.vue` 早已挂着 `sheet="F2-note-listed|soe"` 的下拉
     *   ⇒ 属「后端支持 + 前端有入口 + registry 不认」，批量场景枚举不到。
     *
     * 🔴 `F2-18` 不在此列且不得加：它**不在**后端白名单（多区段分析表无 I/E
     *    适配器）。`F2TabOverallAnalysis.vue` 曾挂过，点击必 400，已删除。
     */
    const INTENTIONAL_ADDITIONS: Record<string, string[]> = {
      f2: ['F2-1', 'F2-note-listed', 'F2-note-soe'],
    }

    for (const [key, sheets] of Object.entries(BASELINE)) {
      const entry = CYCLE_IMPORT_EXPORT[key]
      expect(entry, `既有 key ${key} 在门面中消失`).toBeTruthy()
      expect(entry.apiPrefix, `${key} 的 apiPrefix 变了`).toBe(key)

      const actual = [...entry.sheets]
      const lost = sheets.filter((s) => !actual.includes(s))
      expect(lost, `${key} 丢了既有 sheet 键（R4.6 零回归被破坏）: ${lost.join(', ')}`)
        .toEqual([])

      const allowed = new Set([...sheets, ...(INTENTIONAL_ADDITIONS[key] ?? [])])
      const undeclared = actual.filter((s) => !allowed.has(s))
      expect(
        undeclared,
        `${key} 多出未登记的 sheet 键: ${undeclared.join(', ')}\n`
        + '→ 补键必须先在后端白名单核实，再写进 INTENTIONAL_ADDITIONS 并注明依据',
      ).toEqual([])
    }
  })

  /**
   * 🔴 `MANUAL_OVERRIDES` 后置覆盖**真生效**的行为判据。
   *
   * 判「文件里还有这个符号」是没用的（假绿第②源）：门面若写成
   * `{ ...MANUAL_OVERRIDES }` 被漏掉、或某天生成器不再排除 `MANUAL_PREFIXES`
   * 而由 generated 反向覆盖，符号依旧在，值却变了。
   * 故这里判**对象恒等**（`===`）：门面里那 10 个 key 拿到的必须就是
   * `MANUAL_OVERRIDES` 里的那个对象本身 —— 对象展开只拷引用，恒等即证明
   * 最终值来自 overrides，而不是别处的同名副本。
   */
  it('🔴 MANUAL_OVERRIDES 后置覆盖生效：门面里那 10 个 key 的值是 overrides 的对象本身', () => {
    const keys = Object.keys(MANUAL_OVERRIDES)
    expect(keys.length, 'MANUAL_OVERRIDES 键数变了（与生成器 MANUAL_PREFIXES 双向锁死）').toBe(10)
    for (const k of keys) {
      expect(CYCLE_IMPORT_EXPORT[k], `${k} 在门面中缺席 ⇒ overrides 没被展开进去`).toBeTruthy()
      expect(
        CYCLE_IMPORT_EXPORT[k],
        `${k} 的门面值不是 MANUAL_OVERRIDES 的对象 ⇒ 被别处覆盖了（传输层键会丢）`,
      ).toBe(MANUAL_OVERRIDES[k])
      expect(k in GENERATED_IMPORT_EXPORT, `${k} 两处都登记 ⇒ 覆盖顺序变成活风险`).toBe(false)
    }
  })

  it('覆盖面较改造前显著扩大（10 → catalog 全量）', () => {
    expect(Object.keys(CYCLE_IMPORT_EXPORT).length).toBeGreaterThan(50)
    // MANUAL_OVERRIDES 键数与生成器 `MANUAL_PREFIXES` 双向锁死，改一处必改另一处。
    expect(Object.keys(MANUAL_OVERRIDES).length).toBe(10)
  })

  it('生成文件声明的 catalog 前缀总数与实测一致', () => {
    const catalogPrefixes = new Set(catalogIeEntries().map((e) => e.apiPrefix))
    expect(CATALOG_PREFIX_TOTAL).toBe(catalogPrefixes.size)
    expect(GENERATED_PREFIX_COUNT).toBe(Object.keys(GENERATED_IMPORT_EXPORT).length)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 未登记打红 + 显式豁免表（Task 15 / R4.4 / R4.5 / R4.7）
//
// ## 🔴 豁免表为什么不在前端另抄一份
//
// 缺口前缀的裁决理由已在 `backend/scripts/fix/fix_acnr_catalog_ie_gap.py` 的
// `GAP_REGISTRY` 里（28 条，每条带理由）。前端再抄一份 = 两处真源，
// 改一处忘一处正是本 spec 一直在修的病。
//
// 故本组守卫**直接读那个 Python 字典**并与运行期端点交叉核对：
//   运行期三态齐全前缀  ⊆  registry ∪ GAP_REGISTRY
// 少一个都打红 ⇒ 「后端新增能力但两边都没登记」无法静默逃逸（R4.4）。
// ═══════════════════════════════════════════════════════════════════════════

/** 从 Python 脚本读 `GAP_REGISTRY` 的键与理由（单一真源，不在 TS 里复制） */
function gapRegistry(): Map<string, string> {
  const src = readFileSync(
    resolve(REPO_ROOT, 'backend/scripts/fix/fix_acnr_catalog_ie_gap.py'),
    'utf-8',
  )
  const m = src.match(/GAP_REGISTRY:\s*dict\[str,\s*str\]\s*=\s*\{([\s\S]*?)\n\}/)
  expect(m, '未在 fix_acnr_catalog_ie_gap.py 中找到 GAP_REGISTRY 声明').toBeTruthy()
  const out = new Map<string, string>()
  // 形如  "d1-ecl": "无 bulk 适配器；…",
  for (const e of m![1].matchAll(/"([^"]+)":\s*(?:\(\s*)?"([^"]*)"/g)) {
    out.set(e[1], e[2])
  }
  return out
}

/**
 * 运行期三态齐全的前缀集 —— 由后端守卫产出的快照文件读取。
 *
 * 🔴 前端无法启动 FastAPI，所以不能自己枚举 `app.routes`。改为读后端守卫
 * `test_ie_route_inventory.py` 里的**基线常量**（那是连库/运行期实证过的数），
 * 并断言两侧数量一致 —— 这样后端数变了前端必须同步，不会各自漂移。
 */
function runtimeFull3Count(): number {
  const src = readFileSync(
    resolve(REPO_ROOT, 'backend/tests/test_ie_route_inventory.py'),
    'utf-8',
  )
  const m = src.match(/_BASE_FULL3_PREFIXES\s*=\s*(\d+)/)
  expect(m, '未在后端守卫中找到 _BASE_FULL3_PREFIXES 基线').toBeTruthy()
  return Number(m![1])
}

describe('未登记打红与显式豁免（R4.4 / R4.5 / R4.7）', () => {
  it('GAP_REGISTRY 可解析且非空（扫描面自检）', () => {
    const gap = gapRegistry()
    expect(gap.size).toBeGreaterThan(20)
    // 每条都要有非空理由
    const noReason = [...gap.entries()].filter(([, v]) => !v.trim()).map(([k]) => k)
    expect(noReason, `以下豁免条目无理由（R4.7 要求写明）: ${noReason.join(', ')}`).toEqual([])
  })

  it('🔴 运行期前缀 ⊆ registry ∪ GAP_REGISTRY（后端新增未登记即打红）', () => {
    const registered = new Set(Object.values(CYCLE_IMPORT_EXPORT).map((e) => e.apiPrefix))
    const exempt = new Set(gapRegistry().keys())
    const covered = registered.size + exempt.size
    const runtimeTotal = runtimeFull3Count()

    // 两者之和必须 ≥ 运行期总数（允许 registry 含 catalog 里的传输键变体导致略多）
    expect(
      covered,
      `运行期有 ${runtimeTotal} 个三态齐全前缀，而 registry(${registered.size}) `
      + `+ 豁免表(${exempt.size}) 只覆盖 ${covered} 个 ⇒ 有前缀既未登记也未豁免。\n`
      + '→ 要么跑生成器补 registry，要么在 GAP_REGISTRY 写明不补的理由',
    ).toBeGreaterThanOrEqual(runtimeTotal)
  })

  it('豁免表与 registry 互斥（同一前缀不得既登记又豁免）', () => {
    const registered = new Set(Object.values(CYCLE_IMPORT_EXPORT).map((e) => e.apiPrefix))
    const both = [...gapRegistry().keys()].filter((p) => registered.has(p))
    expect(
      both,
      `以下前缀既在 registry 又在豁免表（语义矛盾）: ${both.join(', ')}`,
    ).toEqual([])
  })

  it('豁免条目数有上限且只许下调', () => {
    // 2026-08-10 实证基线：28 条（23 无适配器 + 4 抽不出 item_id + 1 无模块）
    const CAP = 28
    expect(
      gapRegistry().size,
      '豁免条目数超过基线 ⇒ 新增了未登记缺口，或有人往豁免表里塞本该修的项',
    ).toBeLessThanOrEqual(CAP)
  })

  it('🔴 R4.5：registry 不得登记后端不存在的 apiPrefix', () => {
    // 判据 = catalog（生成器真源）∪ 后端模块声明的前缀
    const catalogPrefixes = new Set(catalogIeEntries().map((e) => e.apiPrefix))
    const backendPrefixes = new Set(backendPrefixToSheetKeys().keys())
    const bogus: string[] = []
    for (const [key, entry] of Object.entries(CYCLE_IMPORT_EXPORT)) {
      if (!catalogPrefixes.has(entry.apiPrefix) && !backendPrefixes.has(entry.apiPrefix)) {
        bogus.push(`${key}→${entry.apiPrefix}`)
      }
    }
    expect(
      bogus,
      `registry 登记了后端不存在的 apiPrefix（点了会 404）: ${bogus.join(', ')}`,
    ).toEqual([])
  })

  it('反向自检：编造的前缀确实不在任何真源里', () => {
    const catalogPrefixes = new Set(catalogIeEntries().map((e) => e.apiPrefix))
    const backendPrefixes = new Set(backendPrefixToSheetKeys().keys())
    const fake = 'zz-not-a-real-prefix'
    expect(catalogPrefixes.has(fake)).toBe(false)
    expect(backendPrefixes.has(fake)).toBe(false)
  })

  it('豁免理由必须说清"为什么不补"而非空话', () => {
    // 判据：理由须含可归因的关键词之一（适配器 / item_id / 模块 / 半径 / 覆盖）
    const vague: string[] = []
    for (const [prefix, reason] of gapRegistry()) {
      if (!/适配器|item_id|模块|半径|覆盖|人工核|专用/.test(reason)) {
        vague.push(`${prefix}: ${reason}`)
      }
    }
    expect(vague, `以下豁免理由过于空泛，无法判断何时该移出: ${vague.join(' | ')}`).toEqual([])
  })

  it('无适配器类豁免必须显式提到适配器（防理由与实情脱节）', () => {
    const gap = gapRegistry()
    // 这批是实证的「无 bulk 适配器」前缀，理由里必须点明
    const noAdapterSamples = [
      'h9-lease-liabilities',
      'm10-other-equity-instruments',
      'n5-income-tax-expense',
    ]
    for (const p of noAdapterSamples) {
      const reason = gap.get(p)
      expect(reason, `${p} 应在豁免表内`).toBeTruthy()
      expect(reason, `${p} 的理由未点明缺适配器: ${reason}`).toMatch(/适配器/)
    }
  })
})
