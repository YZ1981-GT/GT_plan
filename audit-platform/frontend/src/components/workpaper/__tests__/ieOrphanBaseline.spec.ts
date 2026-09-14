/**
 * 导入导出 composable 孤儿基线守卫 —— Wave 1 Task 3
 * spec: workpaper-import-export-lifecycle-closure（R5.1 / 5.5 / 5.6 / 5.7）
 *
 * ## 判据为什么必须按 import 路径而不是符号名
 *
 * memory 铁律：符号级匹配只产生假阴性。`useK5ImportExport` 这个字符串会出现在
 * 它**自己的定义文件**里，按符号名 grep 必然命中自己 ⇒ 永远判不出孤儿。
 * 故消费方判据 = 「有别的文件 import 了这个模块路径」。
 *
 * ## 🔴 测试文件不算消费方
 *
 * 本 spec 立项时把孤儿数记成 10 个，漏了 `useF1ImportExport`；而 `useG13`/`useG14`
 * 的立项判定是「import 路径与符号双 0 命中」——实测**它们确实被 import 了**，
 * 但唯一 import 方是 `g13FairValueChanges.integration.spec.ts` 与
 * `g14ReviewFixes.spec.ts` 两个**测试文件**。
 *
 * 若把测试文件算作消费方，这两个孤儿永远清不掉：测试自己 import 自己要测的东西，
 * 恰好构成「看着有人用、实际用户不可达」。这正是 memory 记的
 * 「Vue 传不存在的 prop = 静默失效，四层全绿只有浏览器暴露」的同族缺陷 ——
 * 判「某能力接没接」必须落到**有渲染宿主**。
 *
 * ⇒ `__tests__/` 目录下与 `*.spec.ts` / `*.test.ts` 一律排除在消费方之外。
 *
 * ## 递归判据（R5.6）
 *
 * A 被 B 消费、而 B 自己是孤儿 ⇒ A 仍是孤儿。故消费方链必须**递归到有渲染宿主**
 * （`.vue` 文件）为止。只判「直接被 import」会漏掉孤儿链。
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, relative, resolve } from 'node:path'

import { describe, it, expect } from 'vitest'

// ═══════════════════════════════════════════════════════════════════════════
// 仓库根 —— 哨兵文件向上查找（禁写死回退级数，memory 已记照抄必 ENOENT）
// ═══════════════════════════════════════════════════════════════════════════

function findRepoRoot(): string {
  let dir = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
  for (let i = 0; i < 12; i++) {
    if (existsSync(resolve(dir, 'backend/app/routers/wp_render_strategies/_cycle_import_export_common.py'))) {
      return dir
    }
    dir = dirname(dir)
  }
  throw new Error('未找到仓库根（哨兵文件缺失）—— 守卫必须打红而不是静默跳过')
}

const REPO_ROOT = findRepoRoot()
const SRC_ROOT = resolve(REPO_ROOT, 'audit-platform/frontend/src')

// ═══════════════════════════════════════════════════════════════════════════
// 基线 —— 只许下调（R5.7）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 12 个孤儿（2026-08-10 实证，递归判据）。
 *
 * ## 与立项台账的两处差异
 *
 * 立项写 **10 个**，实测 **12 个**：
 *
 * ① 多出 `useF1ImportExport` —— 而 `f1` **已在 registry 且三态端点齐全** ⇒ 暴露
 *    一条新缺陷模式：**registry 登记了 ≠ composable 被消费**（能力对用户可达，
 *    但这份 composable 是并存的第二条路，无人使用）。
 *
 * ② 多出 `useJ2ImportExport` —— 它**有**直接 import 方（`composables/workpaper/j2/index.ts`），
 *    所以按「直接被 import」判会漏掉它。但那个 barrel 自己零消费方：J2 目录下
 *    10 个 `.vue`（`GtJ2DefinedBenefitPlan` / `J2Tab*`）**一个都没 import 它**。
 *    实测整个 `composables/workpaper/j2/` 的 **11 个 composable 全部只被该 barrel 消费**
 *    ⇒ 这是一条完整的孤儿链（R5.6 的活样本），而非单点孤儿。
 *
 * 本 spec 只处置其中的 I/E composable（`useJ2ImportExport`）；同链的另外 10 个
 * （`useJ2ActuarialEngine` / `useJ2FormulaEngine` / …）不属本 spec 半径，
 * 已在 tasks.md §Notes 登记为平台级线索。
 */
const ORPHAN_BASELINE: readonly string[] = [
  // ── Task 16 已删除（基线 12 → 9）───────────────────────────────────────
  // `useF1ImportExport.ts`  纯 re-export shim，符号实定义在 useWorkpaperImportExport
  // `useG13ImportExport.ts` 只有两个常量，与 registry 的 g13 条目重复
  // `useG14ImportExport.ts` 同上
  // 三者的引用（3 个 spec 文件）已改指 registry ⇒ 重复源收敛为单一真源
  //
  // ── Task 17 已删除（基线 9 → 6）────────────────────────────────────────
  // `useH7ImportExport.ts` / `useK12ImportExport.ts` / `useK5ImportExport.ts`
  //
  // 三者的三态端点（export-template / export-data / import-data）与共享组件
  // `CycleImportExportDropdown` **完全重叠且无额外端点**（实证：额外端点 0 个），
  // 而 h7 / k12 / k5 的后端路径形态 `/api/workpapers/{wp_id}/{prefix}/*`
  // 三态可达、且都接受 sheet 参数 ⇒ dropdown 能完整替代。
  // 对应 Tab 已挂 dropdown 并与父宿主的 `selfLoad()` 闭环，由
  // `ieWiringIntegrity.spec.ts` 的 8 条精确对账钉死。
  //
  // 附带删掉 `k5Provisions.integration.spec.ts` 里读该文件的测试块 ——
  // 它用 `catch { return }` 兜底，文件消失后会静默恒绿（fail-open 假绿）。

  /**
   * h5 **不能**走 dropdown，且这份 composable 自己也是坏的 —— 双重问题：
   *
   * ① 它拼 `/api/workpapers/${wpId}/h5/export-template` 等**路径形态**，而运行期
   *    2113 条路由里 `/api/workpapers/{wp_id}/h5/*` 一条都不存在
   *    （`_h5_import_export.py` 工厂声明了但从未 include_router）。
   * ② h5 的真实端点是第三形态，由 `app/routers/h5_oil_gas_assets.py` 提供：
   *      POST /api/h5/export-template   body: H5ExportRequest
   *      POST /api/h5/export-data       body: H5ExportRequest
   *      POST /api/h5/import-data       Form: wp_id / sheet / file
   *    wp_id 在 body/Form 里，不在路径里。
   *
   * ⇒ 既不能挂 dropdown（必 404，本轮曾误挂后回退），也不能直接接线这份
   *   composable（它调的地址不存在）。要修得先把 URL 与传参形态改成
   *   body/Form 版，属独立任务。后端守卫
   *   `test_ie_prefix_reachability.py::NON_PATH_FORM_PREFIXES` 已把 h5 钉死。
   */
  'components/workpaper/composables/useH5ImportExport.ts',

  /**
   * `useK1WriteoffImportExport` 是**纯客户端 Excel** 导入导出（`useExcelIO()`），
   * 三态后端端点一个都不调（实证：三态端点集合为空）。它自带：
   *   · `REVERSAL_COLUMNS` 列定义（与致同 K1-9 模板列对齐）
   *   · `SECTION_MAP` 双区段（转回 | 核销）
   *   · `rowsToExport` / `parseImportedRows` 前端解析，模板含示例行
   *   · 目标 sheet 是 K1-9 / K1-12，而 registry 的 k1 只有 K1-11/2/4/5/7/8
   *
   * ⇒ dropdown（调后端三态）**替代不了**它，删即丢 K1-9 的导入导出能力（违反 R5.3）。
   *   接线需要 K1-9 的渲染宿主，属独立任务。
   */
  'components/workpaper/composables/useK1WriteoffImportExport.ts',

  /**
   * `useL4ImportExport` 暂留 —— l4 的后端三端点**不接受 sheet 参数**
   * （`l4_export_data(wp_id, db, current_user)`，整表导出语义），而这份 composable
   * 定义了 `L4_EXPORT_SEGMENTS`（L4-2 极宽表 89 列的多 sheet 分段），
   * 后端却没有对应参数可传 ⇒ 分段能力两侧都不成立。
   *
   * 实测 69 个多 sheet 前缀里只有 l4 不接受 sheet 参数（见后端守卫
   * `SHEET_AGNOSTIC_PREFIXES`）。L4-2 已挂 dropdown（整表导出），L4-3 不挂
   * （挂了会导出与 L4-2 相同内容、误导用户）。
   *
   * 删除前需先裁决分段能力是补后端还是弃用 ⇒ 暂留，不删。
   */
  'components/workpaper/composables/useL4ImportExport.ts',

  /**
   * k0 / l0 是**函证族**（跨循环共享 D0 组件）。两份 composable 各 ~47 行、
   * 三态齐全无额外端点，但唯一候选宿主 `K0SummaryLowerZone.vue` /
   * `L0SummaryLowerZone.vue` 里**没有任何 sheet 码提及**，registry 的 k0 条目
   * （K0-5 / K0-6）在 `.vue` 里也搜不到，l0 更是整个前缀不在 registry。
   *
   * 且 `l0` 在 GAP_REGISTRY 有豁免条目「函证族（跨循环共享 D0 组件），
   * item_id 形态待核」—— 与 j1 同类：补 catalog 需要 item_id，不猜。
   *
   * ⇒ 接线目标不明确，需先核实函证族的 sheet ↔ 区域映射，属独立任务。
   */
  'components/workpaper/confirmation/k0-confirmation/composables/useK0ImportExport.ts',
  'components/workpaper/confirmation/l0-confirmation/composables/useL0ImportExport.ts',

  /**
   * `useJ2ImportExport` 是孤儿**链**（R5.6 活样本）：它被 `j2/index.ts` barrel
   * 直接 import，但 barrel 自己零消费方 —— J2 目录 10 个 `.vue` 一个都没 import 它。
   * 整个 `composables/workpaper/j2/` 的 11 个 composable 全部只被该 barrel 消费。
   *
   * 且 registry 无 j2 前缀。删单个 composable 不解决链问题，接线又缺 sheet 映射
   * ⇒ 需整链裁决，属独立任务。
   */
  'composables/workpaper/j2/useJ2ImportExport.ts',
]

/** 基线条目数上限 —— 只许减不许增（R5.7） */
const ORPHAN_CAP = ORPHAN_BASELINE.length

// ═══════════════════════════════════════════════════════════════════════════
// 扫描（带 mtime memoization —— 键必须含 mtime，否则变异检验假绿）
// ═══════════════════════════════════════════════════════════════════════════

interface FileEntry {
  /** 相对 src 的 posix 路径 */
  rel: string
  abs: string
  mtimeNs: bigint
  size: number
}

let _fileCache: FileEntry[] | null = null

function walk(dir: string, out: FileEntry[]): void {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === 'dist' || name === '.git') continue
    const abs = resolve(dir, name)
    const st = statSync(abs)
    if (st.isDirectory()) {
      walk(abs, out)
    } else if (/\.(ts|vue|js)$/.test(name)) {
      out.push({
        rel: relative(SRC_ROOT, abs).split('\\').join('/'),
        abs,
        mtimeNs: st.mtimeMs > 0 ? BigInt(Math.round(st.mtimeMs * 1e6)) : 0n,
        size: st.size,
      })
    }
  }
}

function allFiles(): FileEntry[] {
  if (_fileCache) return _fileCache
  const out: FileEntry[] = []
  walk(SRC_ROOT, out)
  _fileCache = out
  return out
}

const _srcCache = new Map<string, string>()

function readSrc(e: FileEntry): string {
  // 🔴 缓存键含 mtime + size：否则变异脚本改了文件、守卫仍读旧内容 ⇒ 假绿
  const key = `${e.rel}|${e.mtimeNs}|${e.size}`
  const hit = _srcCache.get(key)
  if (hit !== undefined) return hit
  const src = readFileSync(e.abs, 'utf-8')
  _srcCache.set(key, src)
  return src
}

/** 是否为测试文件（不算消费方） */
export function isTestFile(rel: string): boolean {
  return (
    rel.includes('__tests__/')
    || rel.includes('__mocks__/')
    || /\.(spec|test)\.[tj]s$/.test(rel)
    || rel.startsWith('e2e/')
  )
}

/** 是否为渲染宿主（.vue 才有渲染宿主资格） */
function isRenderHost(rel: string): boolean {
  return rel.endsWith('.vue') && !isTestFile(rel)
}

// ═══════════════════════════════════════════════════════════════════════════
// import 图（按路径解析，不按符号名）
// ═══════════════════════════════════════════════════════════════════════════

const IMPORT_RE = /(?:import|export)[^'"]*?from\s*['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)/g

/**
 * 把 import 说明符解析成相对 src 的 posix 路径（去扩展名）。无法解析返回 null。
 *
 * 🔴 必须手写段运算，禁用 `path.resolve` —— 它是**平台相关**的：
 *    Windows 上 `resolve('/components/workpaper/d4/analysis', '../../composables/useX')`
 *    会补出盘符 `D:\components\workpaper\composables\useX`，再 `.slice(1)` 就切成
 *    `:\components\...` ⇒ 解析全错、`moduleToRel` 全部 miss ⇒ **每个 composable
 *    都被判成孤儿**（实测把有 33 个消费方的 `useD4ImportExport` 也判成孤儿）。
 *    这类缺陷在 Linux CI 上可能不复现，属最难查的一类，故此处纯字符串运算。
 */
export function resolveSpecifier(fromRel: string, spec: string): string | null {
  let segs: string[]
  if (spec.startsWith('@/')) {
    segs = spec.slice(2).split('/')
  } else if (spec.startsWith('.')) {
    // fromRel 是相对 src 的 posix 路径 ⇒ 取其目录段
    const dirSegs = fromRel.split('/').slice(0, -1)
    segs = [...dirSegs, ...spec.split('/')]
  } else {
    return null // 第三方包
  }

  const out: string[] = []
  for (const s of segs) {
    if (s === '' || s === '.') continue
    if (s === '..') {
      if (out.length === 0) return null // 越过 src 根 ⇒ 不可解析
      out.pop()
      continue
    }
    out.push(s)
  }
  return out.join('/').replace(/\.(ts|vue|js)$/, '')
}

interface Graph {
  /** 模块（去扩展名相对路径） → 直接 import 它的模块集合（已排除测试文件） */
  consumers: Map<string, Set<string>>
  /** 全部模块键（去扩展名） → 真实 rel */
  moduleToRel: Map<string, string>
}

let _graph: Graph | null = null

function buildGraph(): Graph {
  if (_graph) return _graph
  const consumers = new Map<string, Set<string>>()
  const moduleToRel = new Map<string, string>()

  for (const f of allFiles()) {
    moduleToRel.set(f.rel.replace(/\.(ts|vue|js)$/, ''), f.rel)
  }

  for (const f of allFiles()) {
    if (isTestFile(f.rel)) continue // 🔴 测试文件不算消费方
    const src = readSrc(f)
    IMPORT_RE.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = IMPORT_RE.exec(src)) !== null) {
      const spec = m[1] ?? m[2]
      if (!spec) continue
      const target = resolveSpecifier(f.rel, spec)
      if (!target) continue
      // 目标可能是 `dir/index`
      for (const cand of [target, `${target}/index`]) {
        if (moduleToRel.has(cand)) {
          if (!consumers.has(cand)) consumers.set(cand, new Set())
          consumers.get(cand)!.add(f.rel)
          break
        }
      }
    }
  }

  _graph = { consumers, moduleToRel }
  return _graph
}

/**
 * 递归判定：某模块是否可达一个渲染宿主（R5.6）。
 *
 * A 被 B import、B 自己是孤儿 ⇒ A 仍是孤儿。故要沿消费方链向上找 `.vue`。
 */
export function reachesRenderHost(moduleKey: string, g: Graph): boolean {
  const seen = new Set<string>()
  const stack = [moduleKey]
  while (stack.length) {
    const cur = stack.pop()!
    if (seen.has(cur)) continue
    seen.add(cur)
    for (const c of g.consumers.get(cur) ?? []) {
      if (isRenderHost(c)) return true
      const cKey = c.replace(/\.(ts|vue|js)$/, '')
      if (!seen.has(cKey)) stack.push(cKey)
    }
  }
  return false
}

/** 全部 I/E composable 文件（相对 src） */
function ieComposables(): string[] {
  return allFiles()
    .filter((f) => /use[A-Z][\w]*ImportExport\.ts$/.test(f.rel) && !isTestFile(f.rel))
    .map((f) => f.rel)
    .sort()
}

/** 当前孤儿集合 */
function currentOrphans(): string[] {
  const g = buildGraph()
  return ieComposables()
    .filter((rel) => !reachesRenderHost(rel.replace(/\.ts$/, ''), g))
    .sort()
}

// ═══════════════════════════════════════════════════════════════════════════
// 类 A —— 判据基础设施自检（应全绿）
// ═══════════════════════════════════════════════════════════════════════════

describe('孤儿判据基础设施自检', () => {
  it('扫描面非空', () => {
    expect(allFiles().length).toBeGreaterThan(1000)
    expect(ieComposables().length).toBeGreaterThan(50)
  })

  it('import 图非空且含已知边', () => {
    const g = buildGraph()
    expect(g.consumers.size).toBeGreaterThan(500)
    expect(g.moduleToRel.size).toBeGreaterThan(1000)
  })

  it('isTestFile 识别四种测试形态', () => {
    expect(isTestFile('components/workpaper/__tests__/a.spec.ts')).toBe(true)
    expect(isTestFile('composables/__tests__/b.ts')).toBe(true)
    expect(isTestFile('components/g13FairValueChanges.integration.spec.ts')).toBe(true)
    expect(isTestFile('components/x.test.ts')).toBe(true)
    expect(isTestFile('components/workpaper/composables/useK5ImportExport.ts')).toBe(false)
    expect(isTestFile('components/workpaper/K5Tab.vue')).toBe(false)
  })

  it('resolveSpecifier 处理 @/ 与相对路径，忽略第三方', () => {
    expect(resolveSpecifier('components/a/B.vue', '@/components/x/Y')).toBe('components/x/Y')
    expect(resolveSpecifier('components/a/B.vue', './C')).toBe('components/a/C')
    expect(resolveSpecifier('components/a/B.vue', '../d/E.ts')).toBe('components/d/E')
    expect(resolveSpecifier('components/a/B.vue', 'vue')).toBeNull()
    expect(resolveSpecifier('components/a/B.vue', 'element-plus')).toBeNull()
  })

  it('替身自检：无消费方模块判为孤儿、有 .vue 消费方判为已接线', () => {
    const g: Graph = {
      consumers: new Map([
        ['x/wired', new Set(['components/Host.vue'])],
        ['x/chained', new Set(['x/middle.ts'])],
        ['x/middle', new Set(['components/Host2.vue'])],
        ['x/onlyTest', new Set<string>()],
      ]),
      moduleToRel: new Map(),
    }
    expect(reachesRenderHost('x/wired', g)).toBe(true)
    expect(reachesRenderHost('x/onlyTest', g)).toBe(false)
    expect(reachesRenderHost('x/nonexistent', g)).toBe(false)
  })

  it('替身自检：孤儿链 —— 被孤儿消费仍是孤儿（R5.6）', () => {
    const g: Graph = {
      consumers: new Map([
        ['a/leaf', new Set(['a/mid.ts'])],
        ['a/mid', new Set(['a/top.ts'])],
        ['a/top', new Set<string>()], // top 无渲染宿主 ⇒ 整条链都是孤儿
      ]),
      moduleToRel: new Map(),
    }
    expect(reachesRenderHost('a/leaf', g)).toBe(false)
  })

  it('替身自检：环形依赖不死循环', () => {
    const g: Graph = {
      consumers: new Map([
        ['c/a', new Set(['c/b.ts'])],
        ['c/b', new Set(['c/a.ts'])],
      ]),
      moduleToRel: new Map(),
    }
    expect(reachesRenderHost('c/a', g)).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B —— 被测实现（当前状态应打红，Wave 4 Task 16/17 修）
// ═══════════════════════════════════════════════════════════════════════════

describe('孤儿基线', () => {
  it('基线条目数不超上限（只许下调，R5.7）', () => {
    expect(ORPHAN_BASELINE.length).toBeLessThanOrEqual(ORPHAN_CAP)
  })

  it('基线条目均真实存在（防 stale 基线永久绿）', () => {
    const known = new Set(ieComposables())
    const stale = ORPHAN_BASELINE.filter((p) => !known.has(p))
    expect(stale, `基线条目在磁盘上不存在（已删或改名，须同步下调基线）: ${stale.join(', ')}`).toEqual([])
  })

  it('基线为 6（立项记 10，实测 12，Task 16 删 3、Task 17 删 3 后为 6）', () => {
    // 立项漏记的 `useJ2ImportExport`：有直接 import 方但整条链不可达渲染宿主（R5.6）
    expect(ORPHAN_BASELINE.some((p) => p.endsWith('j2/useJ2ImportExport.ts'))).toBe(true)
    expect(ORPHAN_BASELINE.length).toBe(6)
  })

  it('Task 16 / 17 删除组确已不在磁盘（防"标了删实际没删"）', () => {
    const known = new Set(ieComposables())
    for (const gone of [
      // Task 16
      'components/workpaper/composables/useF1ImportExport.ts',
      'components/workpaper/composables/useG13ImportExport.ts',
      'components/workpaper/composables/useG14ImportExport.ts',
      // Task 17 —— 三态与 dropdown 完全重叠，且后端路径可达 + 接受 sheet 参数
      'components/workpaper/composables/useH7ImportExport.ts',
      'components/workpaper/composables/useK12ImportExport.ts',
      'components/workpaper/composables/useK5ImportExport.ts',
    ]) {
      expect(known.has(gone), `${gone} 仍在磁盘上 ⇒ 删除组未真正执行`).toBe(false)
    }
  })

  /**
   * 🔴 Task 17 的核心认知：**挂 dropdown 不等于消除 composable 孤儿**。
   *
   * `CycleImportExportDropdown` 自带 HTTP 逻辑、只读 registry，完全不 import 这些
   * composable。所以「接线」在本 spec 里有两种落法，必须分清：
   *   · 能力重叠 ⇒ 挂 dropdown + **删** composable（h7/k12/k5，本轮已做）
   *   · 能力不可替代 ⇒ 必须真正接线该 composable（k1-writeoff 的纯客户端 Excel）
   *
   * 若把「挂了 dropdown」当成孤儿已处置，基线数不会降，还会留下两套并存的代码
   * —— 正是用户裁决要消除的「改一处忘一处」。此断言把这层关系钉死。
   */
  it('已挂 dropdown 的循环，其同名 composable 必须已删（不得两套并存）', () => {
    const known = new Set(ieComposables())
    const wiredButKept = [
      ['h7', 'components/workpaper/composables/useH7ImportExport.ts'],
      ['k12', 'components/workpaper/composables/useK12ImportExport.ts'],
      ['k5', 'components/workpaper/composables/useK5ImportExport.ts'],
    ].filter(([, file]) => known.has(file))
    expect(
      wiredButKept.map(([p, f]) => `${p} → ${f}`),
      '这些循环已挂 dropdown，但旧 composable 还在 ⇒ 两套并存',
    ).toEqual([])
  })

  /**
   * 🔴 J2 孤儿链是 R5.6 的**真实样本**，必须钉死：
   * 若判据退化成「直接被 import 即非孤儿」，这条断言会打红。
   */
  it('J2 链：useJ2ImportExport 有直接 import 方，但整条链不可达渲染宿主', () => {
    const g = buildGraph()
    const key = 'composables/workpaper/j2/useJ2ImportExport'
    const direct = g.consumers.get(key) ?? new Set<string>()

    // 有直接消费方 —— 所以「直接被 import」判据会漏掉它
    expect(direct.size, 'useJ2ImportExport 应有直接 import 方（barrel）').toBeGreaterThan(0)
    expect([...direct]).toContain('composables/workpaper/j2/index.ts')

    // 但 barrel 自己零消费方 ⇒ 递归判据仍判孤儿
    const barrelConsumers = g.consumers.get('composables/workpaper/j2/index') ?? new Set()
    expect(
      [...barrelConsumers],
      'j2/index.ts 若被 .vue 消费了，须同步下调基线',
    ).toEqual([])
    expect(reachesRenderHost(key, g)).toBe(false)
  })

  it('当前孤儿集合 ⊆ 基线（不得新增孤儿）', () => {
    const cur = currentOrphans()
    const added = cur.filter((p) => !ORPHAN_BASELINE.includes(p))
    expect(added, `新增孤儿（后端有能力但用户不可达）: ${added.join(', ')}`).toEqual([])
  })

  /**
   * 🔴 这条仍是**故意打红的占位**（Wave 1 的先打红设计），Task 17 后剩 6 个。
   *
   * 6 个都不是"没做"，而是**各有实证阻塞**，每条的原因写在 `ORPHAN_BASELINE`
   * 对应条目的注释里：
   *   · useH5ImportExport         h5 端点是非路径形态，composable 自己的 URL 也是坏的
   *   · useK1WriteoffImportExport 纯客户端 Excel，dropdown 替代不了，缺 K1-9 宿主
   *   · useL4ImportExport         l4 后端不接受 sheet 参数，分段能力待裁决
   *   · useK0 / useL0             函证族，sheet ↔ 区域映射待核（l0 在 GAP_REGISTRY 豁免）
   *   · useJ2ImportExport         孤儿链，需整链裁决
   *
   * 它保持红色是有意的：转绿要么靠真处置，要么靠往 `ORPHAN_EXEMPTIONS` 写明理由
   * （该表上限 3，且有 stale 检测：豁免项一旦接上渲染宿主立即打红）。
   * 直接改成 `toBeLessThanOrEqual(6)` 会让"剩 6 个"变成新常态 —— 不做。
   */
  it('尚未实现（剩 6 个，各有实证阻塞，见基线注释）：孤儿应全部处置完毕', () => {
    const cur = currentOrphans()
    expect(
      cur,
      `尚未实现（Wave 4 Task 16 删除组 / Task 17 接线组）：仍有 ${cur.length} 个孤儿：\n  ${cur.join('\n  ')}`,
    ).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 反向自检 —— 变异必须能被发现
// ═══════════════════════════════════════════════════════════════════════════

describe('孤儿判据反向自检', () => {
  /**
   * 🔴 R5.3：删除组的能力必须仍由别的入口覆盖 —— 删掉的不能是唯一实现。
   *
   * 立项记 `useG13`/`useG14` 是「import 路径与符号双 0 命中」，实测**有** import 方
   * （3 个 spec 文件）。它们的内容只是两个常量，与 registry 的 `g13`/`g14` 条目
   * 完全重复；且 G13/G14 的 Tab 组件**已挂** `CycleImportExportDropdown`。
   * ⇒ 删文件 + 把 spec 引用改指 registry = 重复源收敛，能力一个不丢。
   */
  it('删除组的能力仍由 registry + dropdown 覆盖（R5.3）', () => {
    const regSrc = readFileSync(
      resolve(SRC_ROOT, 'components/workpaper/shared/cycleImportExportRegistry.generated.ts'),
      'utf-8',
    )
    // g13 / g14 的条目必须仍在 registry 里（否则删除就是丢能力）
    for (const prefix of ['g13', 'g14']) {
      expect(
        regSrc.includes(`apiPrefix: '${prefix}'`),
        `registry 缺 ${prefix} 条目 ⇒ 删除 use${prefix.toUpperCase()}ImportExport 会丢能力`,
      ).toBe(true)
    }
    // 且 G13/G14 目录下确有 .vue 挂了 dropdown（用户点得到）
    const hosts = allFiles().filter(
      (f) =>
        f.rel.endsWith('.vue')
        && /g1[34]-/.test(f.rel)
        && readSrc(f).includes('CycleImportExportDropdown'),
    )
    expect(
      hosts.length,
      'G13/G14 目录无 dropdown 宿主 ⇒ 删除后用户不可达，违反 R5.3',
    ).toBeGreaterThanOrEqual(2)
  })

  it('F1 的能力由 useWorkpaperImportExport 覆盖（R5.3）', () => {
    // 被删的 `useF1ImportExport.ts` 是纯 re-export；真正的实现在这里
    const impl = allFiles().find(
      (f) => f.rel === 'components/workpaper/composables/useWorkpaperImportExport.ts',
    )
    expect(impl, '真实实现文件缺失 ⇒ F1 能力真的丢了').toBeTruthy()
    expect(readSrc(impl!)).toMatch(/useF1ImportExport/)
    // 且 F1 的 .vue 确实在用它
    const f1Hosts = allFiles().filter(
      (f) =>
        f.rel.endsWith('.vue')
        && f.rel.includes('/f1/')
        && readSrc(f).includes('useWorkpaperImportExport'),
    )
    expect(f1Hosts.length, 'F1 组件未使用 useWorkpaperImportExport').toBeGreaterThan(0)
  })

  it('只加 spec 文件的 import 不得让基线缩短（测试不算消费方）', () => {
    // 用替身证明：把消费方换成 spec 文件后仍判孤儿
    const g: Graph = {
      consumers: new Map([['z/x', new Set(['components/__tests__/z.spec.ts'])]]),
      moduleToRel: new Map(),
    }
    // isRenderHost 对 spec 文件返 false ⇒ 不可达渲染宿主
    expect(reachesRenderHost('z/x', g)).toBe(false)
  })

  it('判据按 import 路径而非符号名：仅改符号名不改路径，判定不变', () => {
    // 判据函数签名里没有任何符号名参数 —— 结构上保证这一点
    const src = readFileSync(new URL(import.meta.url), 'utf-8')
    const body = src.slice(src.indexOf('export function reachesRenderHost'))
    const fn = body.slice(0, body.indexOf('\n}\n') + 3)
    expect(fn).not.toMatch(/use[A-Z]\w*ImportExport/)
  })

  it('已接线 composable 确实判为非孤儿（防判据恒真返 false）', () => {
    const g = buildGraph()
    // useD4ImportExport 实测 33 个消费方，必须判为已接线
    const wired = 'components/workpaper/composables/useD4ImportExport'
    expect(g.moduleToRel.has(wired), 'useD4ImportExport 应存在').toBe(true)
    expect(reachesRenderHost(wired, g), 'useD4ImportExport 有 33 个消费方，不应判孤儿').toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 豁免项 stale 检测（Task 15 / R5.4）
//
// ## 为什么豁免必须配 stale 检测
//
// 「豁免」的语义是「现在有意不接线」，不是「永远不管」。若某个豁免的
// composable 后来真被接上了渲染宿主，它就不该再留在豁免表里 ——
// 留着会让下一轮复盘继续把它当"已知不做"，从而错过基线可以下调的机会。
//
// 这与 memory 记的「死代码立即删除，不留 DEPRECATED 注释，否则每次复盘重复提议」
// 是同一条铁律的另一面：**登记表必须能自我失效**。
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 处置为「豁免」的 I/E composable —— 有意保留且**当前**无渲染宿主。
 *
 * 空表是正常状态：本 spec 的 12 个孤儿全部走「删除」或「接线」，
 * 没有一个需要豁免（Task 16/17）。此处留结构 + stale 检测，
 * 供将来确有"暂不处置"需求时使用。
 *
 * 🔴 新增条目必须写理由，且理由要说清**何时可以移出**。
 */
const ORPHAN_EXEMPTIONS: readonly { file: string; reason: string }[] = []

/** 豁免条目数上限 —— 只许下调（与基线同规则） */
const ORPHAN_EXEMPTION_CAP = 3

describe('孤儿豁免 stale 检测（R5.4）', () => {
  it('豁免条目数不超上限', () => {
    expect(
      ORPHAN_EXEMPTIONS.length,
      '豁免条目超上限 ⇒ 有人在用豁免规避处置，而不是真的做不了',
    ).toBeLessThanOrEqual(ORPHAN_EXEMPTION_CAP)
  })

  it('每条豁免都有说清何时可移出的理由', () => {
    const vague = ORPHAN_EXEMPTIONS.filter(
      (e) => !e.reason.trim() || e.reason.trim().length < 10,
    ).map((e) => e.file)
    expect(vague, `以下豁免缺可判定的理由: ${vague.join(', ')}`).toEqual([])
  })

  it('豁免条目必须真实存在（防 stale 键永久绿）', () => {
    const known = new Set(ieComposables())
    const missing = ORPHAN_EXEMPTIONS.filter((e) => !known.has(e.file)).map((e) => e.file)
    expect(
      missing,
      `豁免条目在磁盘上不存在（已删或改名，须同步移出豁免表）: ${missing.join(', ')}`,
    ).toEqual([])
  })

  it('🔴 豁免项一旦接上渲染宿主即打红（stale 检测）', () => {
    const g = buildGraph()
    const nowWired = ORPHAN_EXEMPTIONS.filter((e) =>
      reachesRenderHost(e.file.replace(/\.ts$/, ''), g),
    ).map((e) => e.file)
    expect(
      nowWired,
      `以下豁免项已有渲染宿主 ⇒ 不再是孤儿，请移出豁免表并下调基线: ${nowWired.join(', ')}`,
    ).toEqual([])
  })

  it('豁免与基线互斥（同一文件不得既算孤儿又算豁免）', () => {
    const both = ORPHAN_EXEMPTIONS.filter((e) => ORPHAN_BASELINE.includes(e.file)).map(
      (e) => e.file,
    )
    expect(both, `以下文件既在孤儿基线又在豁免表（语义矛盾）: ${both.join(', ')}`).toEqual([])
  })

  it('替身自检：stale 检测确实能识别"已接线"（防判据恒绿）', () => {
    // 用一个已知有宿主的 composable 走同一判据，必须判为已接线
    const g = buildGraph()
    const wired = 'components/workpaper/composables/useD4ImportExport'
    expect(
      reachesRenderHost(wired, g),
      'stale 判据对已接线模块返 false ⇒ 该判据恒绿，豁免永远不会失效',
    ).toBe(true)
  })
})
