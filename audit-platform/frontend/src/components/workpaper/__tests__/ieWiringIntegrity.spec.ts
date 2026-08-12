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
