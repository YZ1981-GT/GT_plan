/**
 * 导入导出 dropdown 接线完整性守卫 —— Wave 4 Task 17
 * spec: workpaper-import-export-lifecycle-closure（R5.2 / 5.3 / 5.4）
 *
 * ## 为什么 get_diagnostics 全绿不能作为接线正确的证据
 *
 * memory 铁律：**Vue 传不存在的 prop / 绑不存在的字段 = 静默失效**，Volar /
 * vitest / get_diagnostics / HEAD-swap 四层全查不出，只有浏览器挂载才暴露。
 *
 * 本次接线实测踩到的两个真实陷阱，都是「四层全绿」的：
 *
 * ① **子组件 `emit('imported')` 但父宿主不绑 `@imported`** ⇒ 导入成功、后端已写库，
 *    但 `allResponses` 不重载 ⇒ 用户看到的还是旧数据，且**没有任何报错**。
 *    这不是类型错误（Vue 允许 emit 未被监听的事件），所以 Volar 不管。
 *
 * ② **`emit('imported')` 但本组件没 `defineEmits` 声明 `imported`** ⇒ 同样不报错，
 *    `emit` 在运行时把它当未声明事件发出，父组件若用 `@imported` 仍能收到，
 *    但 TS 类型丢失、且 `defineEmits` 一旦被后人重写就会静默断链。
 *
 * ⇒ 故守卫判据必须是**三点闭环**，缺一即红：
 *    (a) 子 Tab 挂了 dropdown，且 api-prefix / sheet 在 registry 中真实存在
 *    (b) 子 Tab 的 defineEmits 声明了 imported（当它 emit 上抛时）
 *    (c) 该 Tab 的父宿主在**它自己的标签块内**绑了 @imported
 *
 * ## 判据不用「字符存在」
 *
 * memory 记的假绿三源之一是「grep 式守卫只查字符串存在」。故 (c) 不是查父文件
 * 里有没有 `@imported` 这几个字，而是**定位到该子组件的那一个标签块**再查 ——
 * 否则父组件只要在别的 Tab 上绑过一次就会让全部 Tab 蒙混过关。
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { basename, dirname, relative, resolve } from 'node:path'

import { describe, it, expect } from 'vitest'

import { CYCLE_IMPORT_EXPORT } from '../shared/cycleImportExportRegistry'

// ═══════════════════════════════════════════════════════════════════════════
// 仓库根 —— 哨兵文件向上查找（禁写死回退级数）
// ═══════════════════════════════════════════════════════════════════════════

function findRepoRoot(): string {
  let dir = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
  for (let i = 0; i < 12; i++) {
    if (
      existsSync(
        resolve(dir, 'backend/app/routers/wp_render_strategies/_cycle_import_export_common.py'),
      )
    ) {
      return dir
    }
    dir = dirname(dir)
  }
  throw new Error('未找到仓库根（哨兵文件缺失）—— 守卫必须打红而不是静默跳过')
}

const REPO_ROOT = findRepoRoot()
const WP_ROOT = resolve(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper')

const DROPDOWN = 'CycleImportExportDropdown'

// ═══════════════════════════════════════════════════════════════════════════
// 文件收集
// ═══════════════════════════════════════════════════════════════════════════

function walkVue(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = resolve(dir, name)
    if (statSync(full).isDirectory()) {
      if (name === '__tests__' || name === 'node_modules') continue
      walkVue(full, acc)
    } else if (name.endsWith('.vue')) {
      acc.push(full)
    }
  }
  return acc
}

const VUE_FILES = walkVue(WP_ROOT)
const VUE_TEXT = new Map<string, string>(
  VUE_FILES.map((f) => [f, readFileSync(f, 'utf-8')]),
)

// ═══════════════════════════════════════════════════════════════════════════
// 开标签提取 —— 引号感知，避免属性值里的 '>' 提前截断
// ═══════════════════════════════════════════════════════════════════════════

function extractOpenTags(text: string, tagName: string): string[] {
  const out: string[] = []
  const needle = `<${tagName}`
  let idx = text.indexOf(needle)
  while (idx !== -1) {
    // 排除 <FooBar 命中 <Foo 的情况
    const nextCh = text[idx + needle.length]
    if (nextCh && /[A-Za-z0-9_-]/.test(nextCh)) {
      idx = text.indexOf(needle, idx + 1)
      continue
    }
    let i = idx + needle.length
    let quote: string | null = null
    while (i < text.length) {
      const ch = text[i]
      if (quote) {
        if (ch === quote) quote = null
      } else if (ch === '"' || ch === "'") {
        quote = ch
      } else if (ch === '>') {
        break
      }
      i++
    }
    out.push(text.slice(idx, i + 1))
    idx = text.indexOf(needle, i)
  }
  return out
}

/** 静态字面量属性：`api-prefix="f2"`。动态绑定 `:api-prefix="expr"` 不算。 */
function attrOf(tag: string, attr: string): string | null {
  const m = tag.match(new RegExp(`(?:^|\\s)${attr}\\s*=\\s*"([^"]*)"`))
  return m ? m[1] : null
}

/**
 * 是否为动态绑定属性（`:api-prefix="expr"` / `v-bind:sheet="expr"`）。
 *
 * 🔴 守卫第一版把这类挂载点当成「缺 api-prefix/sheet 属性」打红，共 10 处
 * （`f2/shared/F2SheetToolbar.vue`、`f5-cost-of-sales/F5Tab*.vue`、
 * `GtF4AccountsPayable.vue`、`f2/detail/F2DetailSheet.vue`、
 * `f2/inspection/F2CutoffSheet.vue`）。那是**守卫自身的 ANCHOR-MISS**，不是代码缺陷：
 * 共享工具栏/通用表格组件本就必须由上游传入前缀与 sheet。
 *
 * 动态值无法静态求值 ⇒ 从「必须在 registry 中」的静态校验里豁免，
 * 但仍要求 ①组件真被注册 ②`@imported` 有处理，这两条与取值方式无关。
 */
function hasDynamicAttr(tag: string, attr: string): boolean {
  return new RegExp(`(?:^|\\s)(?::|v-bind:)${attr}\\s*=`).test(tag)
}

// ═══════════════════════════════════════════════════════════════════════════
// 采集所有 dropdown 挂载点
// ═══════════════════════════════════════════════════════════════════════════

interface Mount {
  file: string
  rel: string
  apiPrefix: string | null
  sheet: string | null
  /** 前缀或 sheet 由上游动态传入（共享工具栏/通用表格），静态校验豁免 */
  dynamic: boolean
  importedHandler: string | null
  emitsUpward: boolean
  hasImportStmt: boolean
  declaresImportedEmit: boolean
}

const MOUNTS: Mount[] = []
for (const [file, text] of VUE_TEXT) {
  const tags = extractOpenTags(text, DROPDOWN)
  if (tags.length === 0) continue

  // 组件是否真被注册（普通 import 或 defineAsyncComponent）
  const hasImportStmt =
    new RegExp(`import\\s+${DROPDOWN}\\s+from`).test(text) ||
    new RegExp(`const\\s+${DROPDOWN}\\s*=\\s*defineAsyncComponent`).test(text)

  // defineEmits 是否声明了 imported —— 两种风格都认：
  //   元组风格  defineEmits<{ imported: [] }>()
  //   签名风格  defineEmits<{ (e: 'imported'): void }>()
  const emitsBlock =
    text.match(/defineEmits<\{[\s\S]*?\}>\(\)/)?.[0] ?? ''
  const declaresImportedEmit =
    /(^|[\s{;])imported\s*:/.test(emitsBlock) || /'imported'/.test(emitsBlock)

  for (const tag of tags) {
    const handler = attrOf(tag, '@imported')
    const dynamic =
      hasDynamicAttr(tag, 'api-prefix') || hasDynamicAttr(tag, 'sheet')
    MOUNTS.push({
      file,
      rel: relative(WP_ROOT, file).replace(/\\/g, '/'),
      apiPrefix: attrOf(tag, 'api-prefix'),
      sheet: attrOf(tag, 'sheet'),
      dynamic,
      importedHandler: handler,
      emitsUpward: !!handler && /emit\(\s*'imported'\s*\)/.test(handler),
      hasImportStmt,
      declaresImportedEmit,
    })
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 父宿主查找 —— 谁 import 了这个 .vue，且在它的标签块上绑了 @imported
// ═══════════════════════════════════════════════════════════════════════════

interface ParentBinding {
  parents: string[]
  boundParents: string[]
  unboundParents: string[]
}

function findParentBindings(childFile: string): ParentBinding {
  const childBase = basename(childFile) // e.g. H5TabDetail.vue
  const childStem = childBase.replace(/\.vue$/, '')
  const parents: string[] = []
  const boundParents: string[] = []
  const unboundParents: string[] = []

  for (const [file, text] of VUE_TEXT) {
    if (file === childFile) continue
    // 以 import 路径为准（符号名判据只产生假阴性）
    if (!text.includes(`/${childBase}`) && !text.includes(`'./${childBase}`)) {
      // 兼容同目录 import './X.vue' 与子目录 import './a/X.vue'
      if (!new RegExp(`import\\([^)]*${childStem}\\.vue`).test(text)) continue
    }
    const rel = relative(WP_ROOT, file).replace(/\\/g, '/')
    parents.push(rel)
    const tags = extractOpenTags(text, childStem)
    const anyBound = tags.some((t) => attrOf(t, '@imported') !== null)
    if (tags.length === 0) {
      // import 了但模板里没用 ⇒ 不是渲染宿主，不计入
      parents.pop()
      continue
    }
    if (anyBound) boundParents.push(rel)
    else unboundParents.push(rel)
  }
  return { parents, boundParents, unboundParents }
}

// ═══════════════════════════════════════════════════════════════════════════
// 守卫
// ═══════════════════════════════════════════════════════════════════════════

describe('导入导出 dropdown 接线完整性（Task 17）', () => {
  it('至少覆盖已接线的循环数（防止接线被整体回退）', () => {
    const prefixes = new Set(MOUNTS.map((m) => m.apiPrefix))
    // h7 / k12 / k5 / l4（本轮）+ g13 / g14（存量）。h5 不在此列 —— 见下方
    // 「非路径形态前缀」断言：它的端点是 `/api/h5/*`，挂 dropdown 必 404。
    for (const expected of ['g13', 'g14', 'h7', 'k12', 'k5', 'l4']) {
      expect(prefixes, `循环 ${expected} 的 dropdown 挂载点消失了`).toContain(expected)
    }
  })

  /**
   * 🔴 非路径形态前缀禁挂 dropdown（2026-08-12 实证，本轮真实返工点）
   *
   * `CycleImportExportDropdown` 只会拼**路径形态**
   * `/api/workpapers/{wp_id}/{prefix}/{export-template|export-data|import-data}`。
   *
   * 实测运行期路由表 2113 条：registry 的 72 个前缀里 **70 个三态全可达**，
   * 只有 `h5` 与 `n4` 一条都不可达 —— 它们的真实端点是第三形态
   * `/api/{prefix}/*`（wp_id 走 body / Form，不在路径里），分别由
   * `app/routers/h5_oil_gas_assets.py` 与 n4 的专属 router 提供；
   * 对应的 `_h5_import_export.py` / `_n4_import_export.py` 工厂虽声明了路径形态，
   * 但从未 `include_router` ⇒ 路径形态根本不存在。
   *
   * 本轮曾误给 H5TabDetail / H5TabAdjustment 挂上 dropdown（get_diagnostics 全绿、
   * vitest 全绿，因为这两层都不校验 URL 是否可达），已回退。此断言把它钉死。
   *
   * 清单与后端守卫 `backend/tests/test_ie_prefix_reachability.py` 双向锁死：
   * 那边从真实 FastAPI 路由表算出不可达集合，这边禁止它们出现在挂载点里。
   */
  it('🔴 非路径形态前缀（h5 / n4）禁止挂 dropdown（必 404）', () => {
    const NON_PATH_FORM_PREFIXES = ['h5', 'n4']
    const bad = MOUNTS.filter(
      (m) => m.apiPrefix && NON_PATH_FORM_PREFIXES.includes(m.apiPrefix),
    ).map((m) => `${m.rel} → api-prefix="${m.apiPrefix}"（真实端点是 /api/${m.apiPrefix}/*）`)
    expect(bad).toEqual([])
  })

  it('静态挂载点都声明了 api-prefix 与 sheet', () => {
    const bad = MOUNTS.filter((m) => !m.dynamic && (!m.apiPrefix || !m.sheet))
    expect(bad.map((b) => b.rel)).toEqual([])
  })

  /**
   * 🔴 判据是「端点真实存在」，registry 只是主要来源之一（2026-08-12 修正）
   *
   * 第一版写「静态 prefix 必须在 registry 中」，被 `j1` 打红 2 处
   * （`j1/core/J1TabDisclosureListed.vue` / `J1TabDisclosureSoe.vue`）。
   * 查证后那**不是死按钮**：
   *   · 后端 `_j1_import_export` 的三端点在 `router_registry/workpaper.py` 真实
   *     include（非死工厂），合法键 12 个由 `SHEET_TYPES` 白名单校验
   *   · registry 有意不收 j1 —— 它是 GAP_REGISTRY 的显式豁免项，理由
   *     「specs 抽取失败，需人工核 item_id 后另补」，而补 catalog 必须填 item_id，
   *     猜错 = 数据错位，故本 spec 裁决「不猜 item_id」，保持豁免
   *
   * ⇒ 合法状态有两种：①已登记 registry ②在 GAP_REGISTRY 豁免**且后端端点真注册**。
   *   把守卫放松成「只要在豁免表就放过」是放水；额外校验「真注册」才是行为判据 ——
   *   19 个死工厂前缀同样不在 registry，但它们**没有**注册，仍会被这条打红。
   */
  it('🔴 静态 api-prefix 要么在 registry，要么是「豁免且后端真注册」', () => {
    const known = new Set(Object.keys(CYCLE_IMPORT_EXPORT))
    const gapSrc = readFileSync(
      resolve(REPO_ROOT, 'backend/scripts/fix/fix_acnr_catalog_ie_gap.py'),
      'utf-8',
    )
    const registrySrc = readFileSync(
      resolve(REPO_ROOT, 'backend/app/router_registry/workpaper.py'),
      'utf-8',
    )

    const unknown = [
      ...new Set(
        MOUNTS.filter((m) => !m.dynamic && m.apiPrefix && !known.has(m.apiPrefix)).map(
          (m) => m.apiPrefix as string,
        ),
      ),
    ]

    const violations: string[] = []
    for (const p of unknown) {
      // ① 必须在 GAP_REGISTRY 里有豁免条目（含非空理由）
      const exempt = new RegExp(`["']${p}["']\\s*:\\s*["'][^"']+["']`).test(gapSrc)
      // ② 且后端确实注册了它的 router（否则就是死按钮）
      const registered =
        new RegExp(`_${p}_import_export\\s+import\\s+router`).test(registrySrc) &&
        new RegExp(`\\b${p}_import_export\\b`).test(registrySrc)
      if (!exempt || !registered) {
        violations.push(
          `api-prefix="${p}" 既不在 registry，` +
            `GAP_REGISTRY 豁免=${exempt}，后端已注册=${registered}`,
        )
      }
    }
    expect(violations).toEqual([])
  })

  it('反向自检：豁免+已注册的放行路径确实被走到（否则上一条恒绿）', () => {
    // 防「unknown 恒为空 ⇒ 上一条空转」。当前实证：j1 走这条路径。
    const known = new Set(Object.keys(CYCLE_IMPORT_EXPORT))
    const unknown = [
      ...new Set(
        MOUNTS.filter((m) => !m.dynamic && m.apiPrefix && !known.has(m.apiPrefix)).map(
          (m) => m.apiPrefix as string,
        ),
      ),
    ]
    expect(unknown, '若为空，说明放行分支未被覆盖，上一条断言退化为空转').toContain('j1')
  })

  it('🔴 静态 sheet 必须在该 prefix 的 registry sheets 中（否则后端 400 死按钮）', () => {
    // 本轮真实抓到：`F2TabOverallAnalysis.vue` 挂 `sheet="F2-18"`，而后端
    // `_f2_import_export._SUPPORTED_SHEETS`（21 键）不含它 ⇒ 点击必 400
    // 「不支持的sheet」。registry 与后端对齐后，这条守卫即可把死按钮钉出来。
    const bad: string[] = []
    for (const m of MOUNTS) {
      if (m.dynamic || !m.apiPrefix || !m.sheet) continue
      const entry = (CYCLE_IMPORT_EXPORT as Record<string, { sheets: readonly string[] }>)[
        m.apiPrefix
      ]
      if (!entry) continue
      if (!entry.sheets.includes(m.sheet)) {
        bad.push(
          `${m.rel} → api-prefix="${m.apiPrefix}" sheet="${m.sheet}" ` +
            `(registry sheets: ${entry.sheets.join(',')})`,
        )
      }
    }
    expect(bad).toEqual([])
  })

  it('动态挂载点数量不得增长（防止靠改成动态绑定绕过静态校验）', () => {
    // 2026-08-12 实证 10 个：f2/shared/F2SheetToolbar、f2/detail/F2DetailSheet、
    // f2/inspection/F2CutoffSheet、f5-cost-of-sales/F5Tab*（6 个）、GtF4AccountsPayable。
    // 这些是共享工具栏/通用表格，前缀与 sheet 必须由上游传入，属正当动态。
    // 一旦有人把某个具体 Tab 的静态属性改成动态以躲开 registry 校验，此数会涨。
    const dyn = MOUNTS.filter((m) => m.dynamic).map((m) => m.rel)
    expect(dyn.length, `动态挂载点：${dyn.join(', ')}`).toBeLessThanOrEqual(10)
  })

  it('挂了 dropdown 的组件必须真的注册了它（import / defineAsyncComponent）', () => {
    const bad = [...new Set(MOUNTS.filter((m) => !m.hasImportStmt).map((m) => m.rel))]
    expect(bad).toEqual([])
  })

  it('emit 上抛 imported 的组件必须在 defineEmits 中声明它', () => {
    const bad = [
      ...new Set(
        MOUNTS.filter((m) => m.emitsUpward && !m.declaresImportedEmit).map((m) => m.rel),
      ),
    ]
    expect(bad).toEqual([])
  })

  it('每个挂载点都处理了 @imported（不处理 = 导入后视图不刷新）', () => {
    const bad = MOUNTS.filter((m) => m.importedHandler === null).map((m) => m.rel)
    expect(bad).toEqual([])
  })

  it('🔴 emit 上抛 imported 的组件，其每个渲染宿主都必须绑定 @imported', () => {
    // 这是本轮真实踩到的静默失效：子 emit、父不听 ⇒ 导入成功但视图不刷新。
    const violations: string[] = []
    const upward = [...new Set(MOUNTS.filter((m) => m.emitsUpward).map((m) => m.file))]
    for (const file of upward) {
      const { parents, boundParents, unboundParents } = findParentBindings(file)
      const rel = relative(WP_ROOT, file).replace(/\\/g, '/')
      if (parents.length === 0) {
        violations.push(`${rel} → 无渲染宿主（emit 出去没人可能听到）`)
        continue
      }
      for (const p of unboundParents) {
        violations.push(`${rel} → 宿主 ${p} 未绑定 @imported`)
      }
      expect(boundParents.length).toBeGreaterThan(0)
    }
    expect(violations).toEqual([])
  })

  /**
   * 本轮接线的最终清单 —— **8 条**，从最初设想的 11 条两次收缩，两次都是实证驳回：
   *
   * ① h5 的 2 条撤销：h5 端点是非路径形态 `/api/h5/*`，挂 dropdown 必 404
   *    （运行期 2113 条路由里 `/api/workpapers/{wp_id}/h5/*` 完全不存在）。
   * ② L4-3 的 1 条撤销：l4 后端三端点**不接受 sheet 参数**，FastAPI 静默丢弃它
   *    ⇒ 在 L4-3 页导出会拿到与 L4-2 相同的内容，不报错但结果错。
   *
   * 另有两处不能按「-2 明细 / -3 调整」惯例套：
   *    · L4-2 的宿主是 `L4TabDetail`；`L4TabAdjustment` 绑的是 L4-4 而非 L4-3
   *    · H7-2 有成本/公允双版本（`measurementModel` 分支），两个都必须挂
   */
  it('本轮接线的 8 个 Tab 逐一闭环（sheet ↔ 宿主 精确对账）', () => {
    const EXPECTED: Array<[string, string, string]> = [
      ['h7', 'H7-2', 'h7/core/H7TabDetailCost.vue'],
      ['h7', 'H7-2', 'h7/core/H7TabDetailFair.vue'],
      ['h7', 'H7-3', 'h7/core/H7TabAdjustment.vue'],
      ['k12', 'K12-2', 'k12/core/K12TabDetail.vue'],
      ['k12', 'K12-3', 'k12/core/K12TabAdjustment.vue'],
      ['k5', 'K5-2', 'k5/core/K5TabDetail.vue'],
      ['k5', 'K5-3', 'k5/core/K5TabAdjustment.vue'],
      ['l4', 'L4-2', 'l4/core/L4TabDetail.vue'],
    ]
    const actual = new Set(MOUNTS.map((m) => `${m.apiPrefix}|${m.sheet}|${m.rel}`))
    const missing = EXPECTED.filter(
      ([p, s, f]) => !actual.has(`${p}|${s}|${f}`),
    ).map(([p, s, f]) => `${f} 应挂 ${p}/${s}`)
    expect(missing).toEqual([])
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// GS5 挂载宿主 + GS10 读回宿主 —— X-3 调整分录汇总表（16 张）
// spec: x3-adjustment-entry-import-export —— 任务 1.6（R6.3 / R6.4 / R6.8 / R10.1 / R10.5）
// ═════════════════════════════════════════════════════════════════════════════
//
// ## 为什么扩这个文件而不是另建一个
//
// 挂载点扫描（`extractOpenTags` / `attrOf` / `hasDynamicAttr`）与父宿主查找的实现
// 都在本文件里。另建一份就有第二个口径，改一处漏一处。本节 **append-only**：
// 上方 12 例（父 spec Task 17 交付）一字不动。
//
// ## GS5 的判据为什么不能用 `text.includes('CycleImportExportDropdown')`
//
// 父 spec 已经踩过「加个调用但仍用硬写文案渲染照样绿」。只 `import` 不渲染、
// 或把挂载写在 `<!-- -->` 注释里、或字符串里出现组件名，全都会让「含某字符串」判绿。
// 故本节先按**标签配对 + 深度计数**取出 SFC 的 `<template>` 块（Vue 的 slot
// `<template #default>` 会嵌套，正则截不出来），剔除 HTML 注释，再在**渲染树内**找标签。
//
// ## GS10 的判据为什么不查「文件里有没有 restoreEntries」
//
// 16 张的读回宿主符号实测有 6 种形态（`restoreEntries` / `_restoreEntries` /
// composable 的 `loadFromResponses` / `computed` 里的 `.get(常量)` / `onMounted` 里的
// `getField('3','entries')` / 迭代 `entries()` + `startsWith && endsWith`），
// 查符号名等于给每张 sheet 抄一份白名单，改名即假绿。
//
// 判据改为**键面对称性**（design E21 的原始方法）：在该 sheet 的读回面
// （tab + `use{X}Adjustment.ts` + `use{X}FormData.ts` 的键链）里解析出全部
// entries 键族，再看是否至少有一族出现在**读取位置**。写入有、读取无 ⇒ 只写不读。
// 键族由源码解析得出，不来自任何清单 ⇒ 不受清单尚未落值影响（清单落值在任务 2.1）。
//
// ## 预期红绿（design §C8 / E21）
//
// · GS5 → **16 红**（16 张一张都没挂 dropdown，Wave 8 任务 11.1 施加）
// · GS10 → **4 红**（`L6-3` / `M1-3` / `M2-3` / `M9-3` 零读回路径，Wave 2 任务 4.2 补齐）
// · 其余为锚点/现状登记/反向自检，全绿；现状登记条目的**反转点写在断言消息里**。

// ─────────────────────────────────────────────────────────────────────────────
// 作业面（spec 声明值，用户裁决 1：16 张，无 pending_manual）
// 短前缀 / X-3 码 / tab 路径一律**从循环码派生**，不另抄映射表。
// ─────────────────────────────────────────────────────────────────────────────

const X3_CYCLES: readonly string[] = [
  'L2',
  'L6',
  'M1',
  'M2',
  'M3',
  'M4',
  'M5',
  'M6',
  'M7',
  'M8',
  'M9',
  'M10',
  'N1',
  'N2',
  'N3',
  'N5',
]

/** `M10` → `m10`（后端短前缀，design §C2/C3 的目标态取值） */
function x3ShortPrefix(cycle: string): string {
  return cycle.toLowerCase()
}

/** `M10` → `M10-3` */
function x3SheetCode(cycle: string): string {
  return `${cycle}-3`
}

/** `M10` → `<WP_ROOT>/m10/core/M10TabAdjustment.vue` */
function x3TabFile(cycle: string): string {
  return resolve(WP_ROOT, cycle.toLowerCase(), 'core', `${cycle}TabAdjustment.vue`)
}

function x3Rel(file: string): string {
  return relative(WP_ROOT, file).replace(/\\/g, '/')
}

/**
 * 🔴 现状登记（design E21 / `Deviation_Registry` G10）—— **只许缩小**。
 *
 * 原值 `['L6-3', 'M1-3', 'M2-3', 'M9-3']`（Wave 0 实测的四张只写不读）。Wave 2 任务 4.2
 * （design §C5a）给这四张的 `use{X}Adjustment.ts` 补了 `loadFromResponses` 后，下方
 * 「已补齐但仍在基线」那条按设计打红并要求同步下调 ⇒ **2026-08-14 清空为空数组**
 * （四张实测均已有读回表达式，`read_source` 归入 `formData.allResponses`）。
 *
 * 清空是**判据收紧**、不是放宽：数组一空，「新增只写不读」那条断言的容忍集也随之为空
 * —— 此后任何一张 X-3 退回只写不读都会立刻打红；同时下方 `read_source` 三分类的期望值
 * 由算式自动变为 16 − 0 − 2 = 14，无须手改数字。
 *
 * ⚠️ 本基线只登记「前端是否存在读回表达式」。四张的 `onMounted` 接线仍在任务 11.1；
 * 界面真能显示导入行（R6.5 / R6.7）要到 11.1 才成立，`Deviation_Registry` G10 的
 * `baseline_count` 亦按其 `owner_spec` 在任务 11.2 下调（现在就下调 = 假绿）。
 */
const X3_READBACK_ABSENT_BASELINE: readonly string[] = []

/** design §storage_field 机制归类：读回源为 `props.allResponses`（⇒ `@imported` 必须重载**父宿主**） */
const X3_PROPS_READ_SOURCE_EXPECTED: readonly string[] = ['N2-3', 'N3-3']

// ─────────────────────────────────────────────────────────────────────────────
// 真源装载
// ─────────────────────────────────────────────────────────────────────────────

interface CatalogSheet {
  addr_id: string
  sheet_code: string
  sheet_name?: string
  cycle?: string
  class_code?: string
  import_export?: { enabled?: boolean; api_prefix?: string; item_id?: string } | null
}

const CATALOG_SHEETS: CatalogSheet[] = (
  JSON.parse(
    readFileSync(resolve(REPO_ROOT, 'backend/data/acnr/global_catalog.json'), 'utf-8'),
  ) as { sheets: CatalogSheet[] }
).sheets

const CATALOG_BY_SHEET_CODE = new Map<string, CatalogSheet>()
for (const s of CATALOG_SHEETS) {
  if (!CATALOG_BY_SHEET_CODE.has(s.sheet_code)) CATALOG_BY_SHEET_CODE.set(s.sheet_code, s)
}

interface LedgerKeyFamilies {
  per_field?: { prefix?: string; suffixes?: string[] }
  data?: { prefix?: string; suffix?: string }
}
interface LedgerSheet {
  read_family?: string
  key_family?: string
  key_families?: LedgerKeyFamilies
  item_id?: string | null
}

const LEDGER = JSON.parse(
  readFileSync(resolve(REPO_ROOT, 'backend/data/adjustment_ie_contract.json'), 'utf-8'),
) as { sheets: Record<string, LedgerSheet>; exempt: Record<string, unknown> }

// ─────────────────────────────────────────────────────────────────────────────
// SFC / JS 结构解析 —— 一律标签或括号配对，禁固定字符窗口、禁跨行 `\n` 锚点
// ─────────────────────────────────────────────────────────────────────────────

/** 从 `<tag` 的起点找到该开标签的 `>` 下标（引号感知，属性值里的 `>` 不算） */
function tagEndIndex(text: string, openIdx: number): number {
  let i = openIdx
  let quote: string | null = null
  while (i < text.length) {
    const ch = text[i]
    if (quote) {
      if (ch === quote) quote = null
    } else if (ch === '"' || ch === "'") {
      quote = ch
    } else if (ch === '>') {
      return i
    }
    i++
  }
  return text.length - 1
}

/** 同长空白替换（保留行号与偏移） */
function blankOut(text: string, from: number, to: number): string {
  const chunk = text.slice(from, to).replace(/[^\n]/g, ' ')
  return text.slice(0, from) + chunk + text.slice(to)
}

/** 剔除 `<script>` / `<style>` 块（同长空白填充，保留行号） */
function withoutScriptAndStyle(text: string): string {
  let out = text
  for (const tag of ['script', 'style']) {
    const openRe = new RegExp(`<${tag}(?=[\\s>])`, 'g')
    let m: RegExpExecArray | null
    while ((m = openRe.exec(out)) !== null) {
      const close = out.indexOf(`</${tag}>`, m.index)
      const end = close === -1 ? out.length : close + `</${tag}>`.length
      out = blankOut(out, m.index, end)
      openRe.lastIndex = m.index
    }
  }
  return out
}

/** 只保留 `<script>` 块正文（其余同长空白），供 JS 层扫描用 */
function scriptOnly(text: string): string {
  let out = text.replace(/[^\n]/g, ' ')
  const openRe = /<script(?=[\s>])/g
  let m: RegExpExecArray | null
  while ((m = openRe.exec(text)) !== null) {
    const bodyStart = tagEndIndex(text, m.index) + 1
    const close = text.indexOf('</script>', bodyStart)
    const bodyEnd = close === -1 ? text.length : close
    out = out.slice(0, bodyStart) + text.slice(bodyStart, bodyEnd) + out.slice(bodyEnd)
    openRe.lastIndex = bodyEnd
  }
  return out
}

/** 剔除 HTML 注释（注释里的挂载不是渲染树的一部分） */
function withoutHtmlComments(text: string): string {
  let out = text
  let idx = out.indexOf('<!--')
  while (idx !== -1) {
    const end = out.indexOf('-->', idx)
    const to = end === -1 ? out.length : end + 3
    out = blankOut(out, idx, to)
    idx = out.indexOf('<!--', to)
  }
  return out
}

/**
 * 取 SFC 顶层 `<template>` 块的正文（渲染树）。
 *
 * 深度计数是必需的：Vue 的具名插槽写法 `<template #default>` 会嵌套，
 * 用 `/<template>([\s\S]*)<\/template>/` 这类正则要么截短要么吞掉整个文件。
 * 返回 null = 该文件没有 SFC 模板块（守卫据此打红，不静默跳过）。
 */
function sfcTemplateBlock(text: string): string | null {
  const scrubbed = withoutHtmlComments(withoutScriptAndStyle(text))
  const marks: Array<{ at: number; open: boolean; end: number }> = []
  const openRe = /<template(?=[\s>])/g
  let m: RegExpExecArray | null
  while ((m = openRe.exec(scrubbed)) !== null) {
    marks.push({ at: m.index, open: true, end: tagEndIndex(scrubbed, m.index) })
  }
  const closeRe = /<\/template\s*>/g
  while ((m = closeRe.exec(scrubbed)) !== null) {
    marks.push({ at: m.index, open: false, end: m.index + m[0].length - 1 })
  }
  marks.sort((a, b) => a.at - b.at)

  let depth = 0
  let bodyStart = -1
  for (const mark of marks) {
    if (mark.open) {
      if (depth === 0) bodyStart = mark.end + 1
      depth++
    } else {
      depth--
      if (depth === 0 && bodyStart !== -1) return scrubbed.slice(bodyStart, mark.at)
      if (depth < 0) return null
    }
  }
  return null
}

/**
 * 剥 JS 注释（同长空白，保留行号）。字符串 / 模板串 / 正则字面量内的
 * `//` 与 `/*` 不得当注释剥掉，否则键字面量会被吞。
 */
function stripJsComments(src: string): string {
  const out: string[] = []
  let i = 0
  let prevSig = ''
  while (i < src.length) {
    const ch = src[i]
    const nxt = i + 1 < src.length ? src[i + 1] : ''
    if (ch === '/' && nxt === '/') {
      while (i < src.length && src[i] !== '\n') {
        out.push(' ')
        i++
      }
      continue
    }
    if (ch === '/' && nxt === '*') {
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) {
        out.push(src[i] === '\n' ? '\n' : ' ')
        i++
      }
      out.push(' ', ' ')
      i += 2
      continue
    }
    if (ch === "'" || ch === '"' || ch === '`') {
      out.push(ch)
      i++
      while (i < src.length) {
        if (src[i] === '\\') {
          out.push(src[i], src[i + 1] ?? '')
          i += 2
          continue
        }
        out.push(src[i])
        if (src[i] === ch) {
          i++
          break
        }
        i++
      }
      prevSig = ch
      continue
    }
    if (ch === '/' && '(,=:[!&|?{};+return'.includes(prevSig)) {
      // 正则字面量（启发式：前一个有效字符是运算符/分隔符）
      out.push(ch)
      i++
      while (i < src.length) {
        if (src[i] === '\\') {
          out.push(src[i], src[i + 1] ?? '')
          i += 2
          continue
        }
        out.push(src[i])
        if (src[i] === '/') {
          i++
          break
        }
        i++
      }
      prevSig = '/'
      continue
    }
    out.push(ch)
    if (!/\s/.test(ch)) prevSig = ch
    i++
  }
  return out.join('')
}

/** `(` 起点 → 括号内文本 + `)` 下标（引号感知） */
function balancedParen(src: string, openIdx: number): { text: string; end: number } | null {
  let depth = 0
  let i = openIdx
  let quote: string | null = null
  while (i < src.length) {
    const ch = src[i]
    if (quote) {
      if (ch === '\\') {
        i += 2
        continue
      }
      if (ch === quote) quote = null
    } else if (ch === "'" || ch === '"' || ch === '`') {
      quote = ch
    } else if (ch === '(') {
      depth++
    } else if (ch === ')') {
      depth--
      if (depth === 0) return { text: src.slice(openIdx + 1, i), end: i }
    }
    i++
  }
  return null
}

/** `{` 起点 → 花括号内文本（引号感知） */
function balancedBrace(src: string, openIdx: number): string | null {
  let depth = 0
  let i = openIdx
  let quote: string | null = null
  while (i < src.length) {
    const ch = src[i]
    if (quote) {
      if (ch === '\\') {
        i += 2
        continue
      }
      if (ch === quote) quote = null
    } else if (ch === "'" || ch === '"' || ch === '`') {
      quote = ch
    } else if (ch === '{') {
      depth++
    } else if (ch === '}') {
      depth--
      if (depth === 0) return src.slice(openIdx + 1, i)
    }
    i++
  }
  return null
}

/**
 * 取函数体（先跳参数列表，再跳返回类型注解里的 `<...>`）。
 *
 * 🔴 不能取「`function f` 之后第一个 `{`」：TS 返回类型注解
 * `): Promise<{ a: number }> {` 会让第一个 `{` 落在类型里。
 */
function functionBody(src: string, fnName: string): string | null {
  const re = new RegExp(`function\\s+${fnName}\\s*\\(`, 'g')
  const m = re.exec(src)
  if (!m) return null
  const paren = balancedParen(src, m.index + m[0].length - 1)
  if (!paren) return null
  let i = paren.end + 1
  let angle = 0
  while (i < src.length) {
    const ch = src[i]
    if (ch === '<') angle++
    else if (ch === '>') angle--
    else if (ch === '{' && angle <= 0) return balancedBrace(src, i)
    i++
  }
  return null
}

/** 收集 `const X = 'literal'` 形态的字符串常量（模块级与函数级都收） */
function collectStringConsts(src: string): Map<string, string> {
  const consts = new Map<string, string>()
  const re = /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*(['"])([^'"\\\n]*)\2/g
  let m: RegExpExecArray | null
  while ((m = re.exec(src)) !== null) {
    if (!consts.has(m[1])) consts.set(m[1], m[3])
  }
  return consts
}

/**
 * 键表达式 → 键模式。`${…}` 归约为 `*`（行序号等运行期变量），
 * 能从常量表解析的标识符替换为其字面量值。无法解析返回 null。
 */
function resolveKeyExpr(expr: string, consts: Map<string, string>): string | null {
  const t = expr.trim()
  const lit = /^(['"])([^'"\\]*)\1$/.exec(t)
  if (lit) return lit[2]
  if (t.startsWith('`') && t.endsWith('`') && t.length >= 2) {
    const body = t.slice(1, -1)
    const filled = body.replace(/\$\{([^{}]*)\}/g, (_all, inner: string) => {
      const name = inner.trim()
      return consts.has(name) ? (consts.get(name) as string) : '*'
    })
    return filled.replace(/\*+/g, '*')
  }
  if (/^[A-Za-z_$][\w$]*$/.test(t) && consts.has(t)) return consts.get(t) as string
  return null
}

// ─────────────────────────────────────────────────────────────────────────────
// GS10 读回面探针
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 该 sheet 的 entries 键模式判据（含 design E19 的双前缀变体 `L6-L6-3-…`、
 * E20 的第 11 个后缀 `ociBlock`）。
 *
 * 显式排除两类非数据键：复核键 `{X}-3-adjustment` / `{X}-3-调整分录`、
 * 审计说明键 `{X}-3-adjustment-note` / `{X}-3-adjustmentNote` —— 它们不含
 * `-entries` / `-entry-*-`，故本正则天然不收。中央同步键另在调用处剔除（G11）。
 */
function x3EntriesKeyRe(cycle: string): RegExp {
  const c = cycle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`^(?:${c}-)?${c}-3-(?:entries$|entry-\\*-)`)
}

interface ReadSite {
  file: string
  pattern: string
  /** `get` = `.get(键)` · `iterate` = `startsWith && endsWith` · `getField` = 跨文件键链 */
  kind: 'get' | 'iterate' | 'getField'
  /** 读取源表达式，决定 `@imported` 该重载谁（`props.allResponses` ⇒ 父宿主） */
  source: string
}

interface ReadBackProbe {
  cycle: string
  sheetCode: string
  /** 读回面各文件（tab + 业务 composable），已确认被 tab import */
  surface: string[]
  /** 读回面里解析出的全部 entries 键模式（写入位置 + 读取位置） */
  keyPatterns: string[]
  readSites: ReadSite[]
  /** 键链（形态 ④）解析失败的记录 —— 不得静默放过 */
  chainFailures: string[]
  /** 中央同步键被剔除的次数（G11 反向自检用） */
  centralSyncExcluded: number
}

function readSurfaceFiles(cycle: string): { files: string[]; missingImports: string[] } {
  const tab = x3TabFile(cycle)
  const files = [tab]
  const missingImports: string[] = []
  const tabText = VUE_TEXT.get(tab) ?? (existsSync(tab) ? readFileSync(tab, 'utf-8') : '')
  const businessComposable = resolve(WP_ROOT, 'composables', `use${cycle}Adjustment.ts`)
  if (existsSync(businessComposable)) {
    // 判据是 tab 真的 import 了它（改名/搬走 ⇒ 不计入读回面，而不是照旧扫）
    if (new RegExp(`use${cycle}Adjustment`).test(tabText)) files.push(businessComposable)
    else missingImports.push(`use${cycle}Adjustment.ts 存在但 ${cycle}TabAdjustment.vue 未 import`)
  }
  return { files, missingImports }
}

/** 形态 ④ 键链：`use{X}FormData.ts` 的 `ITEM_PREFIX` + `getField/setField` 体内的 itemId 模板 */
function formDataKeyChain(
  cycle: string,
): { prefix: string; templates: Record<'getField' | 'setField', string | null> } | null {
  const file = resolve(WP_ROOT, 'composables', `use${cycle}FormData.ts`)
  if (!existsSync(file)) return null
  const src = stripJsComments(readFileSync(file, 'utf-8'))
  const prefix = collectStringConsts(src).get('ITEM_PREFIX')
  if (prefix === undefined) return null
  const templates: Record<'getField' | 'setField', string | null> = {
    getField: null,
    setField: null,
  }
  for (const fn of ['getField', 'setField'] as const) {
    const body = functionBody(src, fn)
    if (!body) continue
    const tm = /const\s+itemId\s*=\s*`([^`]*)`/.exec(body)
    templates[fn] = tm ? tm[1] : null
  }
  return { prefix, templates }
}

function probeReadBack(cycle: string): ReadBackProbe {
  const sheetCode = x3SheetCode(cycle)
  const kre = x3EntriesKeyRe(cycle)
  const { files } = readSurfaceFiles(cycle)
  const keyPatterns = new Set<string>()
  const readSites: ReadSite[] = []
  const chainFailures: string[] = []
  let centralSyncExcluded = 0

  const chain = formDataKeyChain(cycle)

  for (const file of files) {
    const raw = existsSync(file) ? readFileSync(file, 'utf-8') : ''
    const jsRegion = file.endsWith('.vue') ? scriptOnly(raw) : raw
    const src = stripJsComments(jsRegion)
    const consts = collectStringConsts(src)
    const rel = x3Rel(file)

    // G11：`useAdjustmentCentralSync({ itemId: 'N5-3-entries' })` 的中央同步键
    // 与真数据键同名不同源 —— 整段剔除，不得被当成读/写路径。
    const excluded: Array<[number, number]> = []
    const csRe = /useAdjustmentCentralSync\s*\(/g
    let cm: RegExpExecArray | null
    while ((cm = csRe.exec(src)) !== null) {
      const arg = balancedParen(src, cm.index + cm[0].length - 1)
      if (arg) excluded.push([cm.index, arg.end])
    }
    const isExcluded = (pos: number): boolean => excluded.some(([a, b]) => pos >= a && pos <= b)

    // ① 全部键字面量（写入位置 + 读取位置）
    const strRe = /(['"`])(?:\\.|(?!\1)[\s\S])*?\1/g
    let sm: RegExpExecArray | null
    while ((sm = strRe.exec(src)) !== null) {
      if (isExcluded(sm.index)) {
        const v = resolveKeyExpr(sm[0], consts)
        if (v && kre.test(v)) centralSyncExcluded++
        continue
      }
      const v = resolveKeyExpr(sm[0], consts)
      if (v && kre.test(v)) keyPatterns.add(v)
    }

    // ② 读取位置 a) `<responses>.get(键)`
    const getRe = /([\w$]+(?:\.[\w$]+)*)\.get\s*\(/g
    let gm: RegExpExecArray | null
    while ((gm = getRe.exec(src)) !== null) {
      const recv = gm[1]
      if (!/(^|\.)(allResponses|responses)(\.value)?$/.test(recv)) continue
      if (isExcluded(gm.index)) continue
      const arg = balancedParen(src, gm.index + gm[0].length - 1)
      if (!arg) continue
      const v = resolveKeyExpr(arg.text, consts)
      if (v && kre.test(v)) {
        keyPatterns.add(v)
        readSites.push({ file: rel, pattern: v, kind: 'get', source: recv })
      }
    }

    // ③ 读取位置 b) 同一条件表达式内的 `startsWith(前缀) && endsWith(后缀)`
    for (const line of src.split('\n')) {
      const a = /startsWith\s*\(([^()]*)\)/.exec(line)
      const b = /endsWith\s*\(([^()]*)\)/.exec(line)
      if (!a || !b) continue
      const pa = resolveKeyExpr(a[1], consts)
      const pb = resolveKeyExpr(b[1], consts)
      if (!pa || !pb) continue
      const v = `${pa}*${pb}`.replace(/\*+/g, '*')
      if (kre.test(v)) {
        keyPatterns.add(v)
        readSites.push({
          file: rel,
          pattern: v,
          kind: 'iterate',
          source: /allResponses/.test(line) ? 'allResponses' : 'responses',
        })
      }
    }

    // ④ 读取/写入位置 c) 形态 ④ 跨文件键链 `formData.getField('3','entries')`
    for (const fn of ['getField', 'setField'] as const) {
      const callRe = new RegExp(
        `([\\w$]+(?:\\.[\\w$]+)*)\\.${fn}\\s*\\(\\s*(['"])([^'"]*)\\2\\s*,\\s*(['"])([^'"]*)\\4`,
        'g',
      )
      let fm: RegExpExecArray | null
      while ((fm = callRe.exec(src)) !== null) {
        if (isExcluded(fm.index)) continue
        if (!chain) {
          chainFailures.push(`${rel}: ${fn}('${fm[3]}','${fm[5]}') 无法解析 —— use${cycle}FormData.ts 的 ITEM_PREFIX 缺失或改名`)
          continue
        }
        const tmpl = chain.templates[fn]
        if (!tmpl) {
          chainFailures.push(`${rel}: ${fn} 在 use${cycle}FormData.ts 里没有 \`const itemId = \`...\`\` 键拼装表达式`)
          continue
        }
        const v = tmpl
          .replace(/\$\{ITEM_PREFIX\}/g, chain.prefix)
          .replace(/\$\{sheet\}/g, fm[3])
          .replace(/\$\{field\}/g, fm[5])
        if (/\$\{/.test(v)) {
          chainFailures.push(`${rel}: ${fn} 的键模板 \`${tmpl}\` 含未知占位，解析后仍是 ${v}`)
          continue
        }
        if (!kre.test(v)) continue
        keyPatterns.add(v)
        if (fn === 'getField') {
          readSites.push({ file: rel, pattern: v, kind: 'getField', source: `${fm[1]}.getField` })
        }
      }
    }
  }

  return {
    cycle,
    sheetCode,
    surface: files.map(x3Rel),
    keyPatterns: [...keyPatterns].sort(),
    readSites,
    chainFailures,
    centralSyncExcluded,
  }
}

const X3_PROBES: ReadBackProbe[] = X3_CYCLES.map(probeReadBack)
const X3_PROBE_BY_SHEET = new Map(X3_PROBES.map((p) => [p.sheetCode, p]))

/** 读回覆盖的后缀集：`M4-3-entry-*-data` → `data`；单键 JSON → 空集 */
function coveredSuffixes(probe: ReadBackProbe): string[] {
  const out = new Set<string>()
  for (const site of probe.readSites) {
    const m = /\*-(.+)$/.exec(site.pattern)
    if (m) out.add(m[1])
  }
  return [...out].sort()
}

/** 读回源分类（design §storage_field 机制归类的 `read_source` 列） */
function readSourceOf(probe: ReadBackProbe): 'props.allResponses' | 'formData.allResponses' | 'none' {
  if (probe.readSites.length === 0) return 'none'
  return probe.readSites.some((s) => s.source.startsWith('props.'))
    ? 'props.allResponses'
    : 'formData.allResponses'
}

// ─────────────────────────────────────────────────────────────────────────────
// GS5 挂载探针（渲染树内）
// ─────────────────────────────────────────────────────────────────────────────

interface X3MountProbe {
  cycle: string
  sheetCode: string
  rel: string
  exists: boolean
  templateFound: boolean
  /** 文件里有 import / defineAsyncComponent 语句 */
  hasImportStmt: boolean
  /** 渲染树内的 dropdown 开标签（注释与 `<script>` 内的不算） */
  renderTags: string[]
  /** 全文出现次数（含注释/脚本）—— 用于把「只 import 不渲染」讲清楚 */
  rawOccurrences: number
}

function probeX3Mount(cycle: string): X3MountProbe {
  const file = x3TabFile(cycle)
  const exists = existsSync(file)
  const text = exists ? (VUE_TEXT.get(file) ?? readFileSync(file, 'utf-8')) : ''
  const tpl = exists ? sfcTemplateBlock(text) : null
  return {
    cycle,
    sheetCode: x3SheetCode(cycle),
    rel: x3Rel(file),
    exists,
    templateFound: tpl !== null,
    hasImportStmt:
      new RegExp(`import\\s+${DROPDOWN}\\s+from`).test(text) ||
      new RegExp(`const\\s+${DROPDOWN}\\s*=\\s*defineAsyncComponent`).test(text),
    renderTags: tpl === null ? [] : extractOpenTags(tpl, DROPDOWN),
    rawOccurrences: text.split(DROPDOWN).length - 1,
  }
}

const X3_MOUNTS: X3MountProbe[] = X3_CYCLES.map(probeX3Mount)

/** 渲染了指定子组件的父宿主（判据落在父的**渲染树**里，不是「文件含子组件名」） */
function x3ParentHosts(childFile: string): Array<{
  rel: string
  tags: string[]
  bindsImported: boolean
  passesAllResponses: boolean
}> {
  const childStem = basename(childFile).replace(/\.vue$/, '')
  const hosts: Array<{
    rel: string
    tags: string[]
    bindsImported: boolean
    passesAllResponses: boolean
  }> = []
  for (const [file, text] of VUE_TEXT) {
    if (file === childFile) continue
    if (!text.includes(childStem)) continue
    const tpl = sfcTemplateBlock(text)
    if (tpl === null) continue
    const tags = extractOpenTags(tpl, childStem)
    if (tags.length === 0) continue
    hosts.push({
      rel: x3Rel(file),
      tags,
      bindsImported: tags.some((t) => attrOf(t, '@imported') !== null),
      passesAllResponses: tags.some(
        (t) => hasDynamicAttr(t, 'all-responses') || attrOf(t, 'all-responses') !== null,
      ),
    })
  }
  return hosts
}

// ═════════════════════════════════════════════════════════════════════════════

describe('GS5 · X-3 dropdown 挂载宿主（任务 1.6，R6.3 / R6.4 / R6.8）', () => {
  it('反空转锚点：16 个 {X}TabAdjustment.vue 都找得到、都被扫描面覆盖、模板块可解析', () => {
    expect(X3_CYCLES.length, '作业面必须是 16 张（用户裁决 1）').toBe(16)
    const vueSet = new Set(VUE_FILES)
    const problems: string[] = []
    for (const p of X3_MOUNTS) {
      if (!p.exists) problems.push(`${p.rel} 不存在`)
      else if (!vueSet.has(x3TabFile(p.cycle))) problems.push(`${p.rel} 未进 walkVue 扫描面`)
      else if (!p.templateFound) problems.push(`${p.rel} 解析不出 SFC <template> 块`)
    }
    expect(
      problems,
      '扫描面缺失会让下面「未挂 dropdown」的判定退化成空转（扫到 0 个文件 ⇒ 违规集恒空）',
    ).toEqual([])
    expect(X3_MOUNTS.filter((p) => p.templateFound).length).toBe(16)
  })

  it('反空转锚点：16 张 X-3 在 catalog 里都有条目（sheet 属性的真源）', () => {
    const missing = X3_CYCLES.map(x3SheetCode).filter((code) => !CATALOG_BY_SHEET_CODE.has(code))
    expect(missing, 'catalog 查不到 ⇒ sheet 属性无真源可比，双向锁死断言会空转').toEqual([])
    const badClass = X3_CYCLES.map(x3SheetCode).filter(
      (code) => CATALOG_BY_SHEET_CODE.get(code)?.class_code !== 'F-调整分录',
    )
    expect(badClass, 'class_code 不是 F-调整分录 ⇒ 作业面清单与 catalog 分叉').toEqual([])
  })

  it('🔴 16 个 X-3 Tab 必须在 <template> 渲染树内挂 CycleImportExportDropdown', () => {
    const unmounted = X3_MOUNTS.filter((p) => p.renderTags.length === 0).map(
      (p) =>
        `${p.rel}（sheet=${p.sheetCode} 期望 api-prefix=${x3ShortPrefix(p.cycle)}）` +
        `：渲染树内 0 个 ${DROPDOWN}` +
        `［import 语句=${p.hasImportStmt}，全文出现 ${p.rawOccurrences} 次］`,
    )
    expect(
      unmounted,
      '以下 X-3 底稿没有导入导出入口 —— 尚未实现（Wave 8 任务 11.1）。\n' +
        '判据是**渲染树内**有开标签：只 import 不渲染、写在 <!-- --> 里、' +
        '或只在 <script> 字符串里出现，一律判未挂。\n' +
        unmounted.map((u) => `  ${u}`).join('\n'),
    ).toEqual([])
  })

  it('🔴 已挂载的 X-3 dropdown：api-prefix == 派生短前缀、sheet == catalog sheet_code', () => {
    const violations: string[] = []
    let checked = 0
    for (const p of X3_MOUNTS) {
      const expectedPrefix = x3ShortPrefix(p.cycle)
      const expectedSheet = CATALOG_BY_SHEET_CODE.get(p.sheetCode)?.sheet_code
      for (const tag of p.renderTags) {
        checked++
        const apiPrefix = attrOf(tag, 'api-prefix')
        const sheet = attrOf(tag, 'sheet')
        if (hasDynamicAttr(tag, 'api-prefix') || hasDynamicAttr(tag, 'sheet')) {
          violations.push(
            `${p.rel}：X-3 是具体底稿页，api-prefix / sheet 必须是静态字面量（动态绑定绕过静态校验）`,
          )
          continue
        }
        if (apiPrefix !== expectedPrefix) {
          violations.push(`${p.rel}：api-prefix="${apiPrefix}"，期望 "${expectedPrefix}"`)
        }
        if (sheet !== expectedSheet) {
          violations.push(`${p.rel}：sheet="${sheet}"，期望 catalog sheet_code "${expectedSheet}"`)
        }
      }
    }
    expect(violations).toEqual([])
    // Wave 8 任务 11.1 挂载后收紧为恰好 16：少于 16 = 有张掉了（上一条先红），
    // 多于 16 = 某张挂了两个入口（用户会看到两个「导入导出 ▾」，且两个 sheet 可能不同）。
    expect(checked, '已挂载的 X-3 dropdown 数必须恰好等于作业面张数').toBe(
      X3_CYCLES.length,
    )
  })

  it('🔴 反向锁死：16 张 X-3 的 catalog import_export.api_prefix 必须逐条等于派生短前缀', () => {
    const withIe: string[] = []
    const mismatched: string[] = []
    for (const cycle of X3_CYCLES) {
      const entry = CATALOG_BY_SHEET_CODE.get(x3SheetCode(cycle))
      const declared = entry?.import_export?.api_prefix
      if (!declared) continue
      withIe.push(x3SheetCode(cycle))
      if (declared !== x3ShortPrefix(cycle)) {
        mismatched.push(`${x3SheetCode(cycle)}：catalog api_prefix="${declared}"，派生短前缀="${x3ShortPrefix(cycle)}"`)
      }
    }
    expect(
      mismatched,
      'catalog 登记的 api_prefix 与本守卫用于校验前端挂载点的短前缀分叉 ⇒ 前端挂对了后端也 404',
    ).toEqual([])
    const notRegistered = X3_CYCLES.map(x3SheetCode).filter((c) => !withIe.includes(c))
    expect(
      withIe.length,
      '16 张 X-3 必须在 catalog 全部登记 import_export.api_prefix（任务 9.1 已施加，' +
        '任务 11.1 据此把本条从「现状 0」翻成目标态）。\n' +
        `已登记 ${withIe.length}/${X3_CYCLES.length}：${withIe.join(',') || '（无）'}\n` +
        `未登记 ${notRegistered.length} 条：${notRegistered.join(',') || '（无）'}\n` +
        '→ 分母取 X3_CYCLES.length 不内联 16（作业面变动时不留第二份数字）；' +
        '上面 mismatched 那条只对已登记的生效，故本条是它的反空转闸门。',
    ).toBe(X3_CYCLES.length)
  })

  it('反向自检：渲染树判据对「只 import 不渲染 / 注释里挂 / 脚本内出现 / sheet 写错」四种情形的判定', () => {
    const importOnly = `
<template>
  <div class="x"><el-button>导出</el-button></div>
</template>
<script setup lang="ts">
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
</script>`
    const commentedOut = `
<template>
  <div>
    <!-- <CycleImportExportDropdown api-prefix="m4" sheet="M4-3" /> -->
  </div>
</template>
<script setup lang="ts">
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
</script>`
    const inScriptStringOnly = `
<template><div /></template>
<script setup lang="ts">
const marker = '<CycleImportExportDropdown api-prefix="m4" sheet="M4-3" />'
</script>`
    const insideSlot = `
<template>
  <el-table>
    <el-table-column>
      <template #default="{ row }">
        <CycleImportExportDropdown api-prefix="m4" sheet="M4-3" @imported="reload" />
      </template>
    </el-table-column>
  </el-table>
</template>
<script setup lang="ts">
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
</script>`
    const wrongSheet = `
<template>
  <CycleImportExportDropdown api-prefix="m4" sheet="M4-2" @imported="reload" />
</template>`

    const tagsIn = (sfc: string): string[] => {
      const tpl = sfcTemplateBlock(sfc)
      return tpl === null ? [] : extractOpenTags(tpl, DROPDOWN)
    }

    expect(tagsIn(importOnly), '只 import 不渲染必须判未挂').toEqual([])
    expect(tagsIn(commentedOut), '注释里的挂载必须判未挂').toEqual([])
    expect(tagsIn(inScriptStringOnly), '<script> 字符串里的组件名必须判未挂').toEqual([])
    // 插槽内是真渲染树 —— 深度计数必须认它（正则截 <template> 会漏）
    expect(tagsIn(insideSlot).length, '具名插槽内的挂载是渲染树的一部分').toBe(1)
    expect(attrOf(tagsIn(insideSlot)[0], 'sheet')).toBe('M4-3')
    // sheet 写错必须被属性比对抓到
    expect(attrOf(tagsIn(wrongSheet)[0], 'sheet')).toBe('M4-2')
    expect(attrOf(tagsIn(wrongSheet)[0], 'sheet')).not.toBe(x3SheetCode('M4'))
  })
})

describe('GS10 · X-3 读回宿主（任务 1.6，design E21 / §C5a）', () => {
  it('反空转锚点：16 张读回面可解析、各能解析出 entries 键族', () => {
    const noKeys = X3_PROBES.filter((p) => p.keyPatterns.length === 0).map(
      (p) => `${p.sheetCode}（读回面：${p.surface.join(' + ')}）`,
    )
    expect(
      noKeys,
      '解析不出任何 entries 键族 ⇒ 下面「只写不读」的判定恒空变绿。\n' +
        '→ 要么键提取实现失效（注释剥离/常量解析/键链改坏），要么前端键面真的搬走了',
    ).toEqual([])
    // 逐 sheet 下界：单键 JSON 族 1 条、逐字段族 ≥10 条
    const tooFew = X3_PROBES.filter((p) => p.keyPatterns.length < 1).map((p) => p.sheetCode)
    expect(tooFew).toEqual([])
    const totalKeys = X3_PROBES.reduce((s, p) => s + p.keyPatterns.length, 0)
    expect(
      totalKeys,
      `16 张合计解析出 ${totalKeys} 个键模式（下界 100，只许上调）：` +
        X3_PROBES.map((p) => `${p.sheetCode}=${p.keyPatterns.length}`).join(' '),
    ).toBeGreaterThanOrEqual(100)
  })

  it('反空转锚点：形态 ④ 键链（ITEM_PREFIX + itemId 模板）无解析失败', () => {
    const failures = X3_PROBES.flatMap((p) => p.chainFailures.map((f) => `${p.sheetCode}: ${f}`))
    expect(
      failures,
      '键链解析失败必须打红（不得静默当「该 sheet 没有读回」）—— 否则改名 ITEM_PREFIX 会被误判成缺陷',
    ).toEqual([])
    const viaChain = X3_PROBES.filter((p) => p.readSites.some((s) => s.kind === 'getField'))
    expect(
      viaChain.map((p) => p.sheetCode),
      '形态 ④ 键链必须至少覆盖 N5-3（否则该分支是死代码，改坏也没人发现）',
    ).toContain('N5-3')
  })

  it('🔴 ∀16 张必须存在读回路径（read_family != NONE）', () => {
    const absent = X3_PROBES.filter((p) => p.readSites.length === 0).map(
      (p) =>
        `${p.sheetCode}：写入 ${p.keyPatterns.length} 个键族、读取 0 个` +
        `（读回面 ${p.surface.join(' + ')}）`,
    )
    const absentCodes = X3_PROBES.filter((p) => p.readSites.length === 0)
      .map((p) => p.sheetCode)
      .sort()
    const baseline = [...X3_READBACK_ABSENT_BASELINE].sort()

    // 先把「有没有新增只写不读」和「基线是否该下调」分开讲清楚
    const newlyBroken = absentCodes.filter((c) => !baseline.includes(c))
    expect(
      newlyBroken,
      '新增「只写不读」sheet（用户填完刷新即看不见）：' + newlyBroken.join(','),
    ).toEqual([])
    const fixed = baseline.filter((c) => !absentCodes.includes(c))
    expect(
      fixed,
      `以下 sheet 的读回路径已补齐，但仍登记在 X3_READBACK_ABSENT_BASELINE：${fixed.join(',')}\n` +
        '→ 这是 Wave 2 任务 4.2（design §C5a）的施加信号：把已补齐的从基线移除' +
        '（全部补齐则改为空数组），并同步把 Deviation_Registry G10 的 baseline_count 下调。',
    ).toEqual([])

    expect(
      absent,
      '以下 X-3 的界面读回路径缺失 —— 尚未实现（Wave 2 任务 4.2）：\n' +
        absent.map((a) => `  ${a}`).join('\n') +
        '\n（design E21：导入接口返 200、库里有数据，用户刷新页面照样空表 ⇒ R6.5 / R6.7 不可满足）',
    ).toEqual([])
  })

  /**
   * 🔴 登记数判据 = 「16 张必须全部登记」，**不是**「当前实测数」（2026-08-13 修正）
   *
   * 首版写 `.toBe(0)` 并在标题里写「现状 0/16 未登记」，那是把**当时的实测值当基线锁死**
   * （memory 假绿三源第③条的镜像）。任务 2.1 批次 1 把 5 张（`L2-3` / `L6-3` / `M1-3` /
   * `M2-3` / `M3-3`）正确迁入 `sheets` 段后，本条以 `5 !== 0` **被动变红** ——
   * 被动变红 ≠ 先打红：它红的理由是「有人开始干活了」，而不是「目标态未达成」。
   *
   * ⇒ 判据改为目标态：登记数必须等于作业面张数（`X3_PROBES.length`，由上方
   *   反空转锚点钉死 == 16）。今天 5 ≠ 16 仍红（红的理由正确 = 还有 11 张没迁），
   *   任务 2.1 全部迁完当刻自动转绿，**无须再手改这个数字**。
   *   分母取 `X3_PROBES.length` 而不内联 16，避免作业面变动时留第二份数字。
   */
  it('🔴 读回覆盖的后缀集 == 清单 key_families 登记集（16 张必须全部登记）', () => {
    const registered: string[] = []
    const violations: string[] = []
    for (const p of X3_PROBES) {
      const entry = LEDGER.sheets[p.sheetCode]
      if (!entry?.key_families || !entry.read_family) continue
      registered.push(p.sheetCode)
      const readFamily = entry.read_family
      if (readFamily === 'none') continue
      let expectedSuffixes: string[] = []
      if (readFamily === 'per_field') {
        expectedSuffixes = [...(entry.key_families.per_field?.suffixes ?? [])].sort()
      } else if (readFamily === 'data') {
        const s = entry.key_families.data?.suffix
        expectedSuffixes = s ? [s.replace(/^-/, '')] : []
      } else if (readFamily === 'single_json') {
        expectedSuffixes = []
      } else {
        violations.push(`${p.sheetCode}：清单 read_family="${readFamily}" 不是已知取值`)
        continue
      }
      const actual = coveredSuffixes(p)
      if (JSON.stringify(actual) !== JSON.stringify(expectedSuffixes)) {
        violations.push(
          `${p.sheetCode}：读回覆盖后缀 [${actual.join(',')}]，清单 ${readFamily} 登记 [${expectedSuffixes.join(',')}]`,
        )
      }
    }
    expect(
      violations,
      '读回函数覆盖的后缀集与清单登记集分叉 ⇒ 导入的某些字段永远读不回界面（design §C5a 第 2 条）',
    ).toEqual([])
    const unregistered = X3_PROBES.map((p) => p.sheetCode).filter((c) => !registered.includes(c))
    expect(
      registered.length,
      '16 张 X-3 必须全部迁入 adjustment_ie_contract.json 的 sheets 段并登记 ' +
        'key_families + read_family —— 尚未完成（Wave 1 任务 2.1）。\n' +
        `已登记 ${registered.length}/${X3_PROBES.length}：${registered.join(',') || '（无）'}\n` +
        `未登记 ${unregistered.length} 条：${unregistered.join(',') || '（无）'}\n` +
        '→ 未登记的那些张，上面的后缀集比对对它们是空转（无登记值可比）；' +
        '全部登记后本条转绿且比对对 16 张全部生效（比对器本身已由下一条合成夹具证明是活的）。',
    ).toBe(X3_PROBES.length)
  })

  it('反向自检：后缀集比对器与「只写不读」判据都是活的（合成夹具）', () => {
    // ① 后缀集比对器：同一读回覆盖面对不同清单登记值必须给出不同结论
    const fakeProbe: ReadBackProbe = {
      cycle: 'ZZ',
      sheetCode: 'ZZ-3',
      surface: [],
      keyPatterns: ['ZZ-3-entry-*-data'],
      readSites: [{ file: 'x', pattern: 'ZZ-3-entry-*-data', kind: 'get', source: 'allResponses' }],
      chainFailures: [],
      centralSyncExcluded: 0,
    }
    expect(coveredSuffixes(fakeProbe)).toEqual(['data'])
    const perFieldProbe: ReadBackProbe = {
      ...fakeProbe,
      readSites: ['type', 'desc'].map((s) => ({
        file: 'x',
        pattern: `ZZ-3-entry-*-${s}`,
        kind: 'get' as const,
        source: 'allResponses',
      })),
    }
    expect(coveredSuffixes(perFieldProbe)).toEqual(['desc', 'type'])
    expect(coveredSuffixes(perFieldProbe)).not.toEqual(['data'])

    // ② 「只写不读」判据：写入位置的键不算读取位置
    const writeOnly = `
const ITEM_PREFIX = 'ZZ-'
function _triggerSave(n: number): void {
  debouncedSave(\`ZZ-3-entry-\${n}-desc\`, { remark: 'x' })
}`
    const withRead = `${writeOnly}
function restore(allResponses: Map<string, any>): void {
  const r = allResponses.get(\`ZZ-3-entry-\${1}-desc\`)
  void r
}`
    const kre = x3EntriesKeyRe('ZZ')
    const scanReads = (src: string): number => {
      const s = stripJsComments(src)
      const consts = collectStringConsts(s)
      let n = 0
      const re = /([\w$]+(?:\.[\w$]+)*)\.get\s*\(/g
      let m: RegExpExecArray | null
      while ((m = re.exec(s)) !== null) {
        if (!/(^|\.)(allResponses|responses)(\.value)?$/.test(m[1])) continue
        const arg = balancedParen(s, m.index + m[0].length - 1)
        if (!arg) continue
        const v = resolveKeyExpr(arg.text, consts)
        if (v && kre.test(v)) n++
      }
      return n
    }
    expect(scanReads(writeOnly), '只有写入 ⇒ 读取位置 0 个（这正是 E21 四张的态）').toBe(0)
    expect(scanReads(withRead), '加了 .get(键) ⇒ 必须被判为读取位置').toBe(1)

    // ③ 注释里的读回不算（否则把注释掉的旧实现当成读回路径）
    const commentedRead = `${writeOnly}
// const r = allResponses.get(\`ZZ-3-entry-\${1}-desc\`)`
    expect(scanReads(commentedRead), '注释里的 .get 必须被剥掉').toBe(0)
  })

  it('🔴 read_source 分类与 design 登记双向锁死（props.allResponses ⇒ 重载父宿主）', () => {
    const propsSourced = X3_PROBES.filter((p) => readSourceOf(p) === 'props.allResponses')
      .map((p) => p.sheetCode)
      .sort()
    expect(
      propsSourced,
      'read_source 实测集合与 design §storage_field 机制归类分叉：' +
        `实测 [${propsSourced.join(',')}]，design 登记 [${X3_PROPS_READ_SOURCE_EXPECTED.join(',')}]\n` +
        '→ 这两张的读回源是父宿主下发的 props，@imported 只重载 Tab 自身对它们无效',
    ).toEqual([...X3_PROPS_READ_SOURCE_EXPECTED].sort())
    // 其余有读回的 sheet 必须是 formData 源（防「分类器恒返 props」）
    //
    // 🔴 期望值 = 作业面总数 − 零读回（`none`）− props 源（2026-08-13 修正算式）
    //   首版写 `12 - ABSENT + PROPS - 2`（求得 8，实测 10）—— 那是**把错值当基线锁死**
    //   造出的假红：`12` 与 `- 2` 两个字面量都没有对应语义（既非张数也非分类数），
    //   连「三类之和 == 16」这个恒等式都不成立。
    //   正解是恒等式的移项：`none` + `props` + `formData` == `X3_PROBES.length`。
    //   两个基线常量在算式里各出现一次 ⇒ 任务 4.2 把 `X3_READBACK_ABSENT_BASELINE`
    //   清空后期望值自动变 14，无须再手改。
    const formDataSourced = X3_PROBES.filter((p) => readSourceOf(p) === 'formData.allResponses')
    const expectedFormDataSourced =
      X3_PROBES.length - X3_READBACK_ABSENT_BASELINE.length - X3_PROPS_READ_SOURCE_EXPECTED.length
    expect(
      formDataSourced.length,
      '读回源三分类必须满足「零读回 + props 源 + formData 源 == 作业面张数」：\n' +
        `  作业面 ${X3_PROBES.length} − 零读回基线 ${X3_READBACK_ABSENT_BASELINE.length} ` +
        `− props 源 ${X3_PROPS_READ_SOURCE_EXPECTED.length} = ${expectedFormDataSourced}\n` +
        `  实测 formData 源 ${formDataSourced.length} 张：` +
        `${formDataSourced.map((p) => p.sheetCode).join(',')}\n` +
        '→ 不等即：分类器把某些 sheet 归错类（恒返同一类），或某张的读回状态变了而基线未同步',
    ).toBe(expectedFormDataSourced)
  })

  it('🔴 N2-3 / N3-3 必须有父宿主，且父宿主真的下发 all-responses', () => {
    const violations: string[] = []
    for (const code of X3_PROPS_READ_SOURCE_EXPECTED) {
      const probe = X3_PROBE_BY_SHEET.get(code)
      expect(probe, `${code} 不在作业面探针里`).toBeTruthy()
      const hosts = x3ParentHosts(x3TabFile((probe as ReadBackProbe).cycle))
      if (hosts.length === 0) {
        violations.push(`${code}：无渲染宿主 ⇒ props.allResponses 永远是空 Map`)
        continue
      }
      for (const h of hosts) {
        if (!h.passesAllResponses) {
          violations.push(`${code}：宿主 ${h.rel} 渲染了它但未下发 all-responses`)
        }
      }
    }
    expect(violations).toEqual([])
  })

  it('🔴 N2-3 / N3-3 已挂 dropdown，其父宿主必须绑 @imported（挂载后实判）', () => {
    const violations: string[] = []
    let mounted = 0
    for (const code of X3_PROPS_READ_SOURCE_EXPECTED) {
      const probe = X3_PROBE_BY_SHEET.get(code) as ReadBackProbe
      const mount = X3_MOUNTS.find((m) => m.sheetCode === code)
      if (!mount || mount.renderTags.length === 0) continue
      mounted++
      for (const h of x3ParentHosts(x3TabFile(probe.cycle))) {
        if (!h.bindsImported) {
          violations.push(
            `${code}：宿主 ${h.rel} 未绑 @imported —— 该 sheet 读 props.allResponses，` +
              '只重载 Tab 自身看不到导入结果（R6.5）',
          )
        }
      }
    }
    expect(violations).toEqual([])
    expect(
      mounted,
      'N2-3 / N3-3 必须都已挂 dropdown（任务 11.1 施加）—— 只有挂上了，上面的' +
        '「宿主必须绑 @imported」才是实判而非条件式空转。\n' +
        `实测已挂载 ${mounted} 张，期望 ${X3_PROPS_READ_SOURCE_EXPECTED.length} 张。\n` +
        '→ 期望值取 X3_PROPS_READ_SOURCE_EXPECTED.length 不内联 2：props 源清单变动时自动跟随。',
    ).toBe(X3_PROPS_READ_SOURCE_EXPECTED.length)
  })

  it('反向自检：父宿主 @imported 绑定判据是活的（合成夹具）', () => {
    const childTag = 'N2TabAdjustment'
    const unbound = `
<template>
  <div><N2TabAdjustment :all-responses="allResponses" :wp-id="wpId" /></div>
</template>`
    const bound = `
<template>
  <div><N2TabAdjustment :all-responses="allResponses" @imported="reload" /></div>
</template>`
    const boundOnAnotherChild = `
<template>
  <div>
    <N2TabDetail @imported="reload" />
    <N2TabAdjustment :all-responses="allResponses" />
  </div>
</template>`
    const inspect = (sfc: string) => {
      const tpl = sfcTemplateBlock(sfc) ?? ''
      const tags = extractOpenTags(tpl, childTag)
      return {
        tags: tags.length,
        binds: tags.some((t) => attrOf(t, '@imported') !== null),
        passes: tags.some((t) => hasDynamicAttr(t, 'all-responses')),
      }
    }
    expect(inspect(unbound)).toEqual({ tags: 1, binds: false, passes: true })
    expect(inspect(bound)).toEqual({ tags: 1, binds: true, passes: true })
    // 🔴 别的子组件上绑过 @imported 不算 —— 判据必须定位到该子组件自己的标签块
    expect(inspect(boundOnAnotherChild).binds, '父组件在别的 Tab 上绑过不算').toBe(false)
  })

  it('🔴 中央同步键不得被当作读回路径（design G11 / E12→E17）', () => {
    const n5 = X3_PROBE_BY_SHEET.get('N5-3') as ReadBackProbe
    expect(n5, 'N5-3 不在作业面探针里').toBeTruthy()
    expect(
      n5.centralSyncExcluded,
      "N5TabAdjustment 里的 'N5-3-entries' 字面量属 useAdjustmentCentralSync 的中央同步键，" +
        '与真数据键同名不同源，必须被剔除；剔除数为 0 说明剔除逻辑没生效（或该调用被搬走）',
    ).toBeGreaterThanOrEqual(1)
    expect(
      n5.readSites.map((s) => s.kind),
      "N5-3 的读回必须来自形态 ④ 键链（getField），而不是 tab 内同名的中央同步字面量",
    ).toContain('getField')
    expect(
      n5.readSites.every((s) => s.kind === 'getField'),
      `N5-3 读回位置形态：${JSON.stringify(n5.readSites)}`,
    ).toBe(true)
  })
})

describe('GS5b · X-3 的 @imported → 读回可追溯（任务 11.1，R6.5 / R6.7）', () => {
  /**
   * 🔴 为什么「挂上 dropdown + 存在读回表达式」两条各自为真还不够
   *
   * GS5 证明渲染树里有入口，GS10 证明该 sheet 存在读回表达式 —— 但两者**可以互不相连**：
   * `@imported="() => {}"`、或处理器只弹一句成功提示、或只 `loadData()` 却不重跑读回，
   * 三种写法都能让 GS5 与 GS10 双绿，而用户导入后界面照旧（R6.7 的原文：接口返 200
   * **不构成**通过判据）。这正是 memory 记的假绿第①源「additive 注入即死代码」。
   *
   * 判据（不查符号名、不列白名单）：
   *   · 处理器是 `emit('imported')` ⇒ 读回源在父宿主，要求**每个渲染宿主**都绑 @imported
   *   · 否则处理器必须是本 Tab 内定义的函数，且函数体同时具备
   *       ① 一次数据重载（`loadData(` / `selfLoad(` / `reload*(`）
   *       ② 一次**与 onMounted 共用**的读回调用（或该读回由 read surface 内
   *          `watch(...allResponses...)` 反应式驱动 —— L2-3 就是这一形态）
   *   ②的「与 onMounted 共用」是行为判据：onMounted 那条路径已由 GS10 证明真读得到键，
   *   处理器复用同一个函数 ⇒ 导入后走的就是同一条读回；删掉它即打红。
   */
  interface ImportedWiring {
    cycle: string
    sheetCode: string
    mounted: boolean
    handler: string | null
    upward: boolean
    reloadCalls: string[]
    sharedReadbackCalls: string[]
    reactiveDriver: boolean
    hostsUnbound: string[]
    hostCount: number
  }

  /**
   * 函数体内的被调用标识符（末段名）。
   *
   * 🔴 必须剔控制流关键字：`if (` / `for (` / `catch (` 也长得像调用，若不剔，
   * 「处理器体里有 if、onMounted 里也有 if」就会被算成「共用读回调用」⇒ 判据恒真。
   */
  const NON_CALL_KEYWORDS = new Set([
    'if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'function',
    'await', 'do', 'else', 'new', 'delete', 'void', 'in', 'of',
  ])

  function calleeNames(body: string): string[] {
    const out = new Set<string>()
    const re = /([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(/g
    let m: RegExpExecArray | null
    while ((m = re.exec(body)) !== null) {
      const seg = m[1].split('.')
      const name = seg[seg.length - 1]
      if (!NON_CALL_KEYWORDS.has(name)) out.add(name)
    }
    return [...out]
  }

  function importedWiring(cycle: string): ImportedWiring {
    const sheetCode = x3SheetCode(cycle)
    const mount = X3_MOUNTS.find((m) => m.sheetCode === sheetCode) as X3MountProbe
    const tab = x3TabFile(cycle)
    const raw = existsSync(tab) ? readFileSync(tab, 'utf-8') : ''
    const src = stripJsComments(scriptOnly(raw))
    const handler = mount.renderTags.length
      ? attrOf(mount.renderTags[0], '@imported')
      : null
    const upward = !!handler && /emit\(\s*'imported'\s*\)/.test(handler)

    // 处理器函数体（handler 是标识符时才取；内联箭头/表达式一律按体=自身处理）
    const ident = handler && /^[A-Za-z_$][\w$]*$/.test(handler.trim())
      ? handler.trim()
      : null
    const body = ident ? (functionBody(src, ident) ?? '') : (handler ?? '')
    const onMountedBody = (() => {
      const m = /onMounted\s*\(/.exec(src)
      if (!m) return ''
      const arg = balancedParen(src, m.index + m[0].length - 1)
      return arg ? arg.text : ''
    })()

    const reloadCalls = calleeNames(body).filter((n) =>
      /^(loadData|selfLoad|reload[\w$]*|refreshResponses)$/.test(n),
    )
    const onMountedCalls = new Set(calleeNames(onMountedBody))
    const sharedReadbackCalls = calleeNames(body).filter(
      (n) =>
        !/^(loadData|selfLoad|reload[\w$]*)$/.test(n) &&
        (onMountedCalls.has(n) || n === "loadFromResponses"),
    )

    // 反应式驱动：read surface 内存在 watch(...allResponses...) —— L2-3 形态
    const { files } = readSurfaceFiles(cycle)
    const reactiveDriver = files.some((f) => {
      const t = existsSync(f) ? readFileSync(f, 'utf-8') : ''
      const s = stripJsComments(f.endsWith('.vue') ? scriptOnly(t) : t)
      const wre = /watch\s*\(/g
      let wm: RegExpExecArray | null
      while ((wm = wre.exec(s)) !== null) {
        const arg = balancedParen(s, wm.index + wm[0].length - 1)
        if (arg && /allResponses/.test(arg.text)) return true
      }
      return false
    })

    const hosts = x3ParentHosts(tab)
    return {
      cycle,
      sheetCode,
      mounted: mount.renderTags.length > 0,
      handler,
      upward,
      reloadCalls,
      sharedReadbackCalls,
      reactiveDriver,
      hostsUnbound: hosts.filter((h) => !h.bindsImported).map((h) => h.rel),
      hostCount: hosts.length,
    }
  }

  const X3_WIRING: ImportedWiring[] = X3_CYCLES.map(importedWiring)

  it('反空转锚点：16 张都已挂载且 @imported 有非空处理器', () => {
    const bad = X3_WIRING.filter((w) => !w.mounted || !w.handler).map(
      (w) => `${w.sheetCode}：mounted=${w.mounted} handler=${w.handler}`,
    )
    expect(
      bad,
      '未挂载或没有 @imported 处理器 ⇒ 下面的可追溯判定退化为空转',
    ).toEqual([])
    expect(X3_WIRING.length).toBe(X3_CYCLES.length)
  })

  it('🔴 16 张的 @imported 处理器必须可追溯到读回（否则导入后界面照旧）', () => {
    const violations: string[] = []
    for (const w of X3_WIRING) {
      if (w.upward) {
        if (w.hostCount === 0) {
          violations.push(`${w.sheetCode}：emit 上抛但无渲染宿主 ⇒ 没人重载 allResponses`)
        }
        for (const h of w.hostsUnbound) {
          violations.push(`${w.sheetCode}：宿主 ${h} 未绑 @imported ⇒ 上抛无人接`)
        }
        continue
      }
      if (w.reloadCalls.length === 0) {
        violations.push(
          `${w.sheetCode}：处理器 ${w.handler} 体内没有数据重载调用` +
            '（loadData / selfLoad / reload*）⇒ 读的还是导入前的 responses'
        )
      }
      if (w.sharedReadbackCalls.length === 0 && !w.reactiveDriver) {
        violations.push(
          `${w.sheetCode}：处理器 ${w.handler} 体内既没有与 onMounted 共用的读回调用，` +
            'read surface 里也没有 watch(...allResponses...) 反应式读回 ⇒ 导入后不重渲染'
        )
      }
    }
    expect(
      violations,
      'R6.7：导入接口返 200 不构成通过判据 —— 处理器必须真把导入结果读回界面：\n' +
        violations.map((v) => `  ${v}`).join('\n'),
    ).toEqual([])
  })

  it('现状登记：读回驱动形态分布（props 上抛 2 / 反应式 1 / 共用调用 13）', () => {
    const upward = X3_WIRING.filter((w) => w.upward).map((w) => w.sheetCode).sort()
    const shared = X3_WIRING.filter((w) => !w.upward && w.sharedReadbackCalls.length > 0)
    const reactiveOnly = X3_WIRING.filter(
      (w) => !w.upward && w.sharedReadbackCalls.length === 0 && w.reactiveDriver,
    ).map((w) => w.sheetCode)
    expect(upward, "props.allResponses 源必须与 design 登记一致").toEqual(
      [...X3_PROPS_READ_SOURCE_EXPECTED].sort(),
    )
    expect(
      reactiveOnly,
      'L2-3 的读回由 useL2Adjustment 内 watch(allResponses) 驱动（无显式 restore 调用）；' +
        '若这里多出别的 sheet，说明它的显式读回调用被删了而反应式兜底把红吃掉了',
    ).toEqual(['L2-3'])
    expect(
      shared.length + reactiveOnly.length + upward.length,
      '三形态之和必须等于作业面张数（不等 ⇒ 有 sheet 落在任何一类之外）',
    ).toBe(X3_CYCLES.length)
  })

  it('反向自检：可追溯判据对四种残缺处理器的判定（合成夹具）', () => {
    const wire = (body: string, onMounted: string) => {
      const src = stripJsComments(`
async function handleImported(): Promise<void> {
${body}
}
onMounted(async () => {
${onMounted}
})`)
      const b = functionBody(src, 'handleImported') ?? ''
      const om = (() => {
        const m = /onMounted\s*\(/.exec(src)
        if (!m) return ''
        const a = balancedParen(src, m.index + m[0].length - 1)
        return a ? a.text : ''
      })()
      const onMountedCalls = new Set(calleeNames(om))
      return {
        reload: calleeNames(b).filter((n) => /^(loadData|selfLoad|reload[\w$]*)$/.test(n)),
        shared: calleeNames(b).filter(
          (n) =>
            !/^(loadData|selfLoad|reload[\w$]*)$/.test(n) &&
            (onMountedCalls.has(n) || n === 'loadFromResponses'),
        ),
      }
    }
    const om = '  await formData.loadData()\n  restoreEntries()'
    // ① 空处理器 ⇒ 既无 reload 也无读回
    expect(wire('  /* noop */', om)).toEqual({ reload: [], shared: [] })
    // ② 只弹提示 ⇒ 仍判缺 reload 与读回
    expect(wire("  ElMessage.success('导入成功')", om)).toEqual({ reload: [], shared: [] })
    // ③ 只 reload 不读回 ⇒ shared 为空（这是最隐蔽的一种：库里有数据、界面不更新）
    expect(wire('  await formData.loadData()', om).shared).toEqual([])
    // ④ reload + 与 onMounted 共用读回 ⇒ 两项都非空
    const ok = wire('  await formData.loadData()\n  restoreEntries()', om)
    expect(ok.reload).toContain('loadData')
    expect(ok.shared).toContain('restoreEntries')
    // ⑤ 调了个 onMounted 里没有的名字 ⇒ 不算共用读回（防「随便调个函数就算读回」）
    expect(wire('  await formData.loadData()\n  somethingElse()', om).shared).toEqual([])
  })
})
