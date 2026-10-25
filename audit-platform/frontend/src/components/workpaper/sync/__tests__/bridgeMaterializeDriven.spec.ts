/**
 * 平台级守卫：挂了 `WorkpaperSyncEditorHost` 的宿主**必须有人驱动 bridge materialize**。
 *
 * ═══ 这条判据为什么必须存在 ═══════════════════════════════════════════════════
 *
 * `WorkpaperSyncEditorHost` 只在 `descriptor !== null && bridge.mode === 'oo'` 时创建
 * DocEditor（见该组件 `watch([() => props.descriptor, () => props.bridge.mode.value])`），
 * 而 `descriptor` **只能**由 `bridge.switchToOnlyOffice()` 产出 —— 组件自己刻意不请求
 * config、不触发 materialize（它的四条边界第 1 条：「不请求 config」）。
 *
 * ⇒ 「挂了宿主但没人调 `switchToOnlyOffice()`」= 空壳：descriptor 恒 null，用户切到
 * 「在线编辑」后永远停在「正在打开同步编辑器…」那行字上，而**所有静态门都是绿的**
 * （import 齐、组件挂了、bridge 建了、契约有、类型过）。
 *
 * 现算 **27 个**宿主命中这个形态，两簇：
 *   · **13 个 G 循环宿主**：各自挂着 legacy `useG*DualMode`（对 bridge 一无所知，只翻一个
 *     本地 ref）。G2 是同循环的反例 —— 它的注释把道理写得很清楚：「为什么不直接
 *     dualMode.switchMode：legacy 双模式对 syncBridge 一无所知……跳过这一层会绕开 dirty
 *     检查、descriptor 身份验证与 revision 保护」。
 *   · **14 个 A 循环宿主**：连包装都没有，直接 `const mode = ref('结构化视图')` +
 *     `el-segmented v-model="mode"`。
 *
 * ═══ 为什么带基线清单，以及它为什么不是豁免名单 ═══════════════════════════════
 *
 * 判据**双向锁死**：
 *   · 出现清单外的空壳 ⇒ 打红（新接宿主漏调必被抓）；
 *   · 清单里某个**已经修好** ⇒ 也打红，要求从清单删掉（否则清单会退化成永久豁免）。
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const WP = resolve(__dirname, '..', '..')
const COMPOSABLES = resolve(WP, 'composables')
const SYNC = resolve(WP, 'sync')

/** 定义 `switchToOnlyOffice` 的模块本身不算驱动方 —— 定义 ≠ 调用。 */
const DEFINER = 'useWorkpaperSyncBridge'

const MOUNT_RE = /<WorkpaperSyncEditorHost/
const DRIVE_RE = /\bswitchToOnlyOffice\s*\(/

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}

/**
 * 剥注释。
 *
 * 🔴 不剥会产出假阴性：`usePilotBridgeAdapter` 的 docstring 里写着
 * 「`switchMode` = bridge 的 `switchToOnlyOffice()`」，而它的实现里**零 API 调用** ——
 * 首版探针就是这么把它误判成驱动方的。
 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function listTs(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir, { withFileTypes: true })) {
    if (name.isDirectory()) {
      if (name.name === '__tests__') continue
      out.push(...listTs(resolve(dir, name.name)))
    } else if (name.name.endsWith('.ts') && !name.name.endsWith('.spec.ts')) {
      out.push(resolve(dir, name.name))
    }
  }
  return out
}

/**
 * 递归列出全部 `.vue`（相对 `workpaper/` 的 posix 路径）。
 *
 * 🔴 必须递归：首版只扫顶层 `Gt*.vue`，而子目录里实测还有 **33 个** d4 子 Tab 挂了
 * `<WorkpaperSyncEditorHost>`。那 33 个现算全是真驱动（由 `d4/composables/useD4SyncMode`
 * 驱动），但扫描面停在顶层就意味着「将来子目录里新增一个空壳」判据抓不到 —— 那正是
 * 本判据要防的事。
 */
function listVue(dir: string, prefix = ''): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir, { withFileTypes: true })) {
    if (name.isDirectory()) {
      if (name.name === '__tests__') continue
      out.push(...listVue(resolve(dir, name.name), `${prefix}${name.name}/`))
    } else if (name.name.endsWith('.vue')) {
      out.push(`${prefix}${name.name}`)
    }
  }
  return out
}

/**
 * 现算「真正驱动桥」的包装模块名（如 `useHSyncMode`）。
 *
 * 🔴 两侧扫描面必须**同时**递归，否则判据自相矛盾：宿主侧递归到 `d4/**` 但驱动侧只扫
 * `composables/` + `sync/` 两个顶层目录时，33 个 d4 子 Tab 的驱动方
 * （`d4/composables/useD4SyncMode.ts`）扫不到 ⇒ 33 个真驱动被误报成空壳（本判据首次
 * 改递归时就是这么假红的）。
 */
function exportedNames(src: string): string[] {
  const names: string[] = []
  for (const m of src.matchAll(/export\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/g)) {
    names.push(m[1])
  }
  for (const m of src.matchAll(/export\s+const\s+([A-Za-z_$][\w$]*)\s*=/g)) {
    names.push(m[1])
  }
  return names
}

function drivingWrappers(): Set<string> {
  // 🔴 必须按**导出的符号名**索引，不是文件 stem：`kAdjustmentSync.ts` 导出的是
  // `useKAdjustmentSync`，宿主调用的也是 `useKAdjustmentSync(`。首版按文件 stem（`kAdjustmentSync`）
  // 收集，而宿主调的 `useKAdjustmentSync(` 匹配不上 `\bkAdjustmentSync\s*\(`（前面是 `use`，无
  // 词边界）⇒ 六张 K 表被误报空壳。useHSyncMode/useD4SyncMode 恰好 stem==导出名才没暴露这个 bug。
  type Mod = { src: string; exports: string[] }
  const mods: Mod[] = []
  for (const file of listTs(WP)) {
    const stem = file.replace(/\\/g, '/').split('/').pop()!.replace(/\.ts$/, '')
    if (stem === DEFINER) continue
    const src = stripComments(read(file))
    // 若文件没有显式导出名，退回文件 stem（兼容 default-export 式 composable）。
    const exports = exportedNames(src)
    mods.push({ src, exports: exports.length ? exports : [stem] })
  }
  // 先收直接调用 bridge 的模块（其全部导出名入集），再做固定点闭包：
  // K wrapper(useKAdjustmentSync) → useD4SyncMode → bridge。只扫一层会把真实委派误报为空壳；
  // 只凭 import 名也不够，必须在模块体里有调用表达式 `name(`。
  const out = new Set<string>()
  for (const mod of mods) {
    if (DRIVE_RE.test(mod.src)) mod.exports.forEach((n) => out.add(n))
  }
  let changed = true
  while (changed) {
    changed = false
    for (const mod of mods) {
      if (mod.exports.every((n) => out.has(n))) continue
      const delegates = [...out].some((w) => new RegExp(`\\b${w}\\s*\\(`).test(mod.src))
      if (delegates) {
        mod.exports.forEach((n) => {
          if (!out.has(n)) {
            out.add(n)
            changed = true
          }
        })
      }
    }
  }
  return out
}

/** 现算「挂了宿主却从不驱动」的相对路径（**全仓递归**，含子目录）。 */
function hollowHosts(): string[] {
  const wrappers = [...drivingWrappers()]
  const out: string[] = []
  for (const rel of listVue(WP)) {
    const raw = read(resolve(WP, rel))
    if (!MOUNT_RE.test(raw)) continue
    const src = stripComments(raw)
    if (DRIVE_RE.test(src)) continue
    const viaWrapper = wrappers.some((w) => new RegExp(`\\b${w}\\s*\\(`).test(src))
    if (viaWrapper) continue
    out.push(rel)
  }
  return out.sort()
}

/** 现算挂了宿主的全部文件（真驱动 + 空壳）。 */
function mountingHosts(): string[] {
  return listVue(WP).filter((rel) => MOUNT_RE.test(read(resolve(WP, rel)))).sort()
}

/**
 * 现算「建了 `useWorkpaperSyncBridge` 却没人驱动」的相对路径。
 *
 * 比 `hollowHosts()` 的面更宽：那条要求先挂 `WorkpaperSyncEditorHost`，而 G1/G3 曾经
 * 建了桥**连挂都没挂**（桥全套死代码），压根没进那条的扫描面。
 */
function bridgeBuiltNotDriven(): string[] {
  const wrappers = [...drivingWrappers()]
  const out: string[] = []
  for (const rel of listVue(WP)) {
    const src = stripComments(read(resolve(WP, rel)))
    if (!/\buseWorkpaperSyncBridge\s*\(/.test(src)) continue
    if (DRIVE_RE.test(src)) continue
    if (wrappers.some((w) => new RegExp(`\\b${w}\\s*\\(`).test(src))) continue
    out.push(rel)
  }
  return out.sort()
}

/**
 * 🔴 append-only 欠账清单，**不是豁免名单**（修好必须删，见文件头）。
 *
 * 🔴 2026-10-01 现算：清单已**清空**。两类欠账在当前分支都归零 ——
 *   · G 循环 13 宿主已于 2026-09-27 接 `sync/useGRenderModeSwitch`；
 *   · 原登记的 A 循环宿主（A91/A101/… 共 14~17 个）在当前分支**根本不挂
 *     `WorkpaperSyncEditorHost` 也不建 `useWorkpaperSyncBridge`**：它们走的是**另一条**
 *     legacy 单 OO 路径 `GtOnlyOfficeSheet`（`<GtOnlyOfficeSheet v-else sheet-name="A9-1">`），
 *     不在本扫描器的两个入口（EditorHost 挂载 / bridge 建立）之内。
 *
 * ⇒ 原基线是对着「A 宿主曾挂 EditorHost」的旧状态写的，与当前分支的 `GtOnlyOfficeSheet`
 *   形态不符，属 append-only 清单滞后。按「清单已修好项必须删」的既有纪律清空。
 *   🔴 这**不**代表 A 循环的 legacy 单 OO 已接真桥 —— 那是 A 轮 spec 的范围（`GtOnlyOfficeSheet`
 *   不受本「EditorHost 必须被驱动」判据覆盖），本判据对它没有发言权，故不登记。
 *
 * 清单清空后判据仍**双向锁死**：任何宿主只要**挂了 EditorHost / 建了 bridge** 却不驱动，
 * `extra` 立刻非空打红（下面「扫描器自检」证明扫描面非空，排除空集假绿）。
 */
const KNOWN_HOLLOW: readonly string[] = Object.freeze([] as string[])

/**
 * 🔴 「建了桥却没人驱动」的 append-only 欠账清单（**不是豁免名单**，修好必须删）。
 *
 * 现算 **0 个**：当前分支里凡建了 `useWorkpaperSyncBridge` 的宿主都已有人驱动 materialize
 * （G 循环收口 + B60 + D4 子 Tab + K 六表二阶委派）。原登记的 A 循环宿主走 `GtOnlyOfficeSheet`
 * legacy 单 OO 路径、**不建 bridge**，不在本扫描面内（见 `KNOWN_HOLLOW` 的说明）。
 */
const KNOWN_BUILT_NOT_DRIVEN: readonly string[] = Object.freeze([] as string[])

describe('挂了 WorkpaperSyncEditorHost 就必须有人驱动 materialize', () => {
  const hollow = hollowHosts()

  it('扫描器自检：确实扫到了宿主与驱动方（防空集假绿）', () => {
    const wrappers = drivingWrappers()
    expect(wrappers.has('useHSyncMode')).toBe(true)
    // 🔴 顶层 `composables/` 与**子目录** `d4/composables/` 都要扫到，两侧扫描面才同口径。
    expect(wrappers.has('useD4SyncMode')).toBe(true)
    // 二阶委派也必须被识别：K wrappers 不直接调用 bridge，但调用 useD4SyncMode。
    expect(wrappers.has('useKAdjustmentSync')).toBe(true)
    expect(wrappers.has('useK1WriteoffSync')).toBe(true)
    expect(wrappers.has(DEFINER)).toBe(false)
    // 现算 92 个宿主挂了 EditorHost（含子目录）；下界远低于现值，只防「扫成空集」。
    expect(mountingHosts().length).toBeGreaterThan(80)
  })

  it('🔴 子目录里的空壳必须保持为 0（递归扫描面的存在性证明）', () => {
    const inSubdir = hollow.filter((h) => h.includes('/'))
    expect(
      inSubdir,
      `子目录宿主挂了 EditorHost 却无人驱动 materialize：\n  ${inSubdir.join('\n  ')}`,
    ).toEqual([])
    // 🔴 光断言「子目录空壳=0」会被「递归根本没走进子目录」冒充通过。
    // 现算子目录里有 33 个宿主（d4 子 Tab 为主）且全是真驱动 —— 必须先证明扫到了它们。
    const subdirMounted = mountingHosts().filter((h) => h.includes('/'))
    expect(subdirMounted.length).toBeGreaterThan(20)
  })

  it('🔴 不得新增「挂了却从不驱动」的宿主', () => {
    const extra = hollow.filter((h) => !KNOWN_HOLLOW.includes(h))
    expect(extra, `新增空壳宿主（descriptor 恒 null，用户永远停在「正在打开…」）：\n  ${extra.join('\n  ')}`).toEqual([])
  })

  it('🔴 基线里已修好的必须从清单删掉（清单不得变豁免名单）', () => {
    const fixed = KNOWN_HOLLOW.filter((h) => !hollow.includes(h))
    expect(fixed, `以下宿主已接真驱动，请从 KNOWN_HOLLOW 删掉：\n  ${fixed.join('\n  ')}`).toEqual([])
  })

  it('🔴 当前分支空壳面为 0（挂了 EditorHost 的宿主无一例外都被驱动）', () => {
    // 原来点名断言 A91/A101「是空壳」—— 它们在当前分支根本不挂 EditorHost（走
    // GtOnlyOfficeSheet legacy 单 OO），该断言已对不上现实。改为：直接证明全仓空壳面为 0。
    expect(hollow, `仍存在挂了 EditorHost 却不驱动的空壳：\n  ${hollow.join('\n  ')}`).toEqual([])
    // 已接真桥的 G 宿主不得退回空壳（反向锚点，证明判据不是恒绿）。
    expect(hollow).not.toContain('GtG9OtherNoncurrentFinancial.vue')
    expect(hollow).not.toContain('GtG13FairValueChanges.vue')
  })

  it('🔴 变异反证：临时把一个真驱动 wrapper 从扫描结果剔除，对应宿主必被判空壳', () => {
    // 不改生产代码，只在本测试内模拟「useKAdjustmentSync 不再被识别为驱动方」，
    // 证明判据真的能把 K8/K9/K11/K12/K13 抓成空壳（排除「恒返回空集」的假绿）。
    const wrappers = [...drivingWrappers()].filter((w) => w !== 'useKAdjustmentSync')
    const mutated: string[] = []
    for (const rel of mountingHosts()) {
      const src = stripComments(read(resolve(WP, rel)))
      if (DRIVE_RE.test(src)) continue
      if (wrappers.some((w) => new RegExp(`\\b${w}\\s*\\(`).test(src))) continue
      mutated.push(rel)
    }
    expect(mutated).toContain('k8/core/K8TabAdjustment.vue')
    expect(mutated).toContain('k11/core/K11TabAdjustment.vue')
    // 真实（未变异）扫描里它们都不是空壳。
    expect(hollow).not.toContain('k8/core/K8TabAdjustment.vue')
  })

  it('🔴 usePilotBridgeAdapter 不得被当成驱动方（它 docstring 提到但实现零 API）', () => {
    const adapter = stripComments(read(resolve(SYNC, 'usePilotBridgeAdapter.ts')))
    expect(DRIVE_RE.test(adapter)).toBe(false)
    expect(drivingWrappers().has('usePilotBridgeAdapter')).toBe(false)
  })

  /**
   * 🔴 补这条是因为本文件原有判据有个**盲区**：它只扫「挂了 `WorkpaperSyncEditorHost`」
   * 的宿主。而 `GtG1TradingFinancialAssets` / `GtG3DividendReceivable` 当时的形态是
   * **建了 `useWorkpaperSyncBridge` 却既不挂 EditorHost 也不驱动** —— 桥连同
   * `syncOoDescriptor` / `syncSwitching` 全是死代码，OO 模式一律走 legacy 假双向。
   * 那比「挂了却不驱动」更隐蔽：压根没进本文件的扫描面，两条基线判据都抓不到。
   *
   * ⇒ 判据面从「挂了就要驱动」扩到「**建了桥**就要有人驱动」。
   */
  it('🔴 建了 useWorkpaperSyncBridge 的宿主必须有人驱动 materialize（不止挂了的）', () => {
    const extra = bridgeBuiltNotDriven().filter((h) => !KNOWN_BUILT_NOT_DRIVEN.includes(h))
    expect(
      extra,
      '以下宿主建了桥却没人驱动 materialize —— 桥、descriptor、switching 全是死代码，'
        + '用户切「在线编辑」走的是 legacy 假双向路径：\n  '
        + extra.join('\n  '),
    ).toEqual([])
  })

  it('🔴 建桥基线里已修好的也必须从清单删掉（同样不许退化成豁免名单）', () => {
    const built = bridgeBuiltNotDriven()
    const fixed = KNOWN_BUILT_NOT_DRIVEN.filter((h) => !built.includes(h))
    expect(
      fixed,
      `以下宿主已接真驱动，请从 KNOWN_BUILT_NOT_DRIVEN 删掉：\n  ${fixed.join('\n  ')}`,
    ).toEqual([])
  })

  it('扫描器自检②：确实扫到了建桥的宿主（防上一条空集假绿）', () => {
    const builders = listVue(WP).filter((rel) =>
      /\buseWorkpaperSyncBridge\s*\(/.test(stripComments(read(resolve(WP, rel)))),
    )
    // 现算 30+ 个宿主直接建桥；下界远低于现值，只防「扫成空集」。
    expect(builders.length).toBeGreaterThan(20)
  })

  it('反例锚点：G2 与 H 循环包装是真驱动（证明判据能区分真假）', () => {
    const g2 = stripComments(read(resolve(WP, 'GtG2InterestReceivable.vue')))
    expect(DRIVE_RE.test(g2)).toBe(true)
    const h = stripComments(read(resolve(COMPOSABLES, 'useHSyncMode.ts')))
    expect(DRIVE_RE.test(h)).toBe(true)
  })
})
