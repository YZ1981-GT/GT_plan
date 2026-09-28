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
function drivingWrappers(): Set<string> {
  const out = new Set<string>()
  for (const file of listTs(WP)) {
    const stem = file.replace(/\\/g, '/').split('/').pop()!.replace(/\.ts$/, '')
    if (stem === DEFINER) continue
    if (DRIVE_RE.test(stripComments(read(file)))) out.add(stem)
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
 * 现存 14 个 A 循环宿主（纯本地 mode ref，连包装都没有）。
 *
 * 原先还有 13 个 G 循环宿主，已于 2026-09-27 全部接 `sync/useGRenderModeSwitch`
 * （受管 sheet 经桥的四分支协议、非受管委派 legacy），逐个从本清单删除。
 */
const KNOWN_HOLLOW: readonly string[] = Object.freeze([
  // ── A 循环：连包装都没有，`const mode = ref('结构化视图')` + v-model ──
  'GtA101GovernanceCommunication.vue',
  'GtA111SubsequentEventsInquiry.vue',
  'GtA121LegalConfirmation.vue',
  'GtA171AuditSummary.vue',
  'GtA1721Kam.vue',
  'GtA1731ConsultationExecution.vue',
  'GtA173ConsultationRecord.vue',
  'GtA174DisagreementRecord.vue',
  'GtA176ClosingMeeting.vue',
  'GtA177IndependenceDeclaration.vue',
  'GtA182RegulatoryCommunication.vue',
  'GtA271ItAuditMemo.vue',
  'GtA81OtherInfoRepresentation.vue',
  'GtA91DeficiencyLetter.vue',
].sort())

/**
 * 🔴 「建了桥却没人驱动」的 append-only 欠账清单（**不是豁免名单**，修好必须删）。
 *
 * 现算 **17 个**，全在 A 循环 —— 比 `KNOWN_HOLLOW` 那 14 个多出
 * `GtA112DualChecklist` / `GtA115DisclosureChecklist` / `GtA38GoodwillImpairment`
 * 三个：它们建了桥但连 `WorkpaperSyncEditorHost` 都没挂，所以原判据的扫描面扫不到。
 *
 * 这 17 个不在本轮（G 循环 + B60）范围：A 循环连 `*ManagedSheets` 受管声明清单都还没有，
 * 受管 sheet 身份无从派生。本清单只负责「锁住不恶化」并把欠账面记准。
 */
const KNOWN_BUILT_NOT_DRIVEN: readonly string[] = Object.freeze([
  'GtA101GovernanceCommunication.vue',
  'GtA111SubsequentEventsInquiry.vue',
  'GtA112DualChecklist.vue',
  'GtA115DisclosureChecklist.vue',
  'GtA121LegalConfirmation.vue',
  'GtA171AuditSummary.vue',
  'GtA1721Kam.vue',
  'GtA1731ConsultationExecution.vue',
  'GtA173ConsultationRecord.vue',
  'GtA174DisagreementRecord.vue',
  'GtA176ClosingMeeting.vue',
  'GtA177IndependenceDeclaration.vue',
  'GtA182RegulatoryCommunication.vue',
  'GtA271ItAuditMemo.vue',
  'GtA38GoodwillImpairment.vue',
  'GtA81OtherInfoRepresentation.vue',
  'GtA91DeficiencyLetter.vue',
].sort())

describe('挂了 WorkpaperSyncEditorHost 就必须有人驱动 materialize', () => {
  const hollow = hollowHosts()

  it('扫描器自检：确实扫到了宿主与驱动方（防空集假绿）', () => {
    const wrappers = drivingWrappers()
    expect(wrappers.has('useHSyncMode')).toBe(true)
    // 🔴 顶层 `composables/` 与**子目录** `d4/composables/` 都要扫到，两侧扫描面才同口径。
    expect(wrappers.has('useD4SyncMode')).toBe(true)
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

  it('正向对照：点名断言 A91 与 A101 确实被扫到（不是自证式相等）', () => {
    // 🔴 原来点名的是 G9 —— 它已接真桥，留着就是要求生产代码退回去。A 循环那 14 个
    //    才是当前真实的欠账面（连 `*ManagedSheets` 声明清单都没有）。
    expect(hollow).toContain('GtA91DeficiencyLetter.vue')
    expect(hollow).toContain('GtA101GovernanceCommunication.vue')
    // 已修好的不得再出现在空壳面里（与基线那条互为正反）。
    expect(hollow).not.toContain('GtG9OtherNoncurrentFinancial.vue')
    expect(hollow).not.toContain('GtG13FairValueChanges.vue')
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
