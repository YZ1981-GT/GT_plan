/**
 * UI 诚实性总守卫（tasks 3.6）。
 *
 * spec workpaper-html-onlyoffice-bidirectional-writeback-closure
 * AC 1.4：入口未注册 adapter 或未过契约校验 ⇒ 不得显示「可双向回写」，且必须给可操作原因。
 * AC 1.5：纯 OO / 纯 HTML 入口只显示真实可用模式，不显示不可兑现的切换按钮。
 * AC 1.7：不可达旧桩不得有任何可用入口。
 *
 * 四条不变量（分母取 **generated manifest 全域**，不抽样）：
 *   ① `single_*` 不得长出双模式开关；
 *   ② `unreachable` 零可用模式、零开关；
 *   ③ 静态 bidirectional 但运行时未就绪（契约漂移等）⇒ 不得宣称双向，提示必须是 danger
 *      且带可操作原因；
 *   ④ `pending` 必须常显「两侧未互通」的原因，不得按目标态展示。
 *
 * 另有一条**接线闭合**判据：已接单源的宿主，其模式开关的 `v-if` 必须真的绑在
 * `presentation.showModeSwitch` 上 —— 只 import 单源却不用它是假接线，棘轮那条只看 import，
 * 看不出这个。
 *
 * 🔴 「blocked 不得发 materialize」**不在本文件**：那条必须真发请求才算验证，由
 * `useWorkpaperSyncBridge.spec.ts` 的三条用例承担（readiness 未过即拒 / readiness 失败
 * fail visible / readiness 必须早于第一个写请求）。这里不写跨文件的文本断言 —— 那种判据
 * 会被注释骗过，也证明不了请求真的没发出去。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  deriveEntrySyncPresentation,
  type EntrySyncLoadState,
} from '../entrySyncPresentation'
import { WORKPAPER_SYNC_MANIFEST } from '../workpaperSyncManifest.generated'
import type { EntrySyncReadiness } from '../workpaperSyncApi'

type Capability = EntrySyncReadiness['capability']

/** 按 capability 造一条「运行时一切正常」的 readiness —— 诚实性不该依赖运行时失败才成立。 */
function readiness(capability: Capability, patch: Partial<EntrySyncReadiness> = {}): EntrySyncReadiness {
  const modes: Record<string, readonly ('html' | 'oo')[]> = {
    bidirectional: ['html', 'oo'],
    single_html: ['html'],
    single_onlyoffice: ['oo'],
    unreachable: [],
  }
  return {
    entry_id: 'xlsx/probe',
    effective_entry_id: 'xlsx/probe',
    capability,
    adjudication_state: capability === null ? 'pending' : 'terminal',
    allowed_modes: capability === null ? ['html'] : (modes[capability] ?? ['html']),
    can_claim_bidirectional: capability === 'bidirectional',
    runtime: {
      ready: capability === 'bidirectional',
      adapter_id: capability === 'bidirectional' ? 'probe.adapter' : null,
      authority_model: 'projection_contract',
      definition_bundle_id: 'bundle',
      definition_bundle_sha256: 'a'.repeat(64),
      typed_slots_complete: capability === 'bidirectional',
      typed_slots: [],
      representation_id: 'representation',
      representation_generation: 1,
    },
    acceptance: {
      state: 'verified', stale: false, run_id: 'run',
      required_scenario_set_digest: 'b'.repeat(64),
    },
    reason: null,
    ...patch,
  }
}

const SETTLED: readonly EntrySyncLoadState[] = ['revalidating', 'ready']

/** manifest 全域里真实出现过的 capability 取值（含 null）。 */
const OBSERVED: readonly Capability[] = Array.from(
  new Set(
    WORKPAPER_SYNC_MANIFEST.filter((entry) => entry.independentEntry).map(
      (entry) => (entry.capability ?? null) as Capability,
    ),
  ),
)

describe('UI 诚实性总守卫 —— 分母是 manifest 全域', () => {
  it('分母非空，且 manifest 里真实出现的每种 capability 都被下面逐条覆盖', () => {
    const independent = WORKPAPER_SYNC_MANIFEST.filter((entry) => entry.independentEntry)
    expect(independent.length).toBeGreaterThan(100)
    // 🔴 现算事实（不是假设）：本 spec 的 Phase 1 把迁移中的入口统一落成
    //    `capability=null` + pending 三字段，**拒绝**继续用组件默认 `single_onlyoffice`
    //    ⇒ 当下 manifest 里 `single_html` / `single_onlyoffice` 条数为 0，
    //    真实出现的只有 `bidirectional` / `unreachable` / `null`。
    //    下面的 ①~④ 仍对**四种 capability 全测** —— 它们是 derive 函数的不变量，
    //    不该依赖「当下恰好有这种 entry」才成立（否则等 pending 裁决出 single_* 时，
    //    判据才第一次被走到，那正是最坏的时机）。
    expect(OBSERVED).toContain('bidirectional')
    expect(OBSERVED).toContain(null)
    const covered = new Set<Capability>([
      'bidirectional', 'single_html', 'single_onlyoffice', 'unreachable', null,
    ])
    const uncovered = OBSERVED.filter((capability) => !covered.has(capability))
    expect(uncovered, `manifest 出现了本文件未覆盖的 capability：${uncovered}`).toEqual([])
  })

  it('unreachable 已归零（AC 1.7 达成）且 ② 的判据不依赖它存在', () => {
    const unreachable = WORKPAPER_SYNC_MANIFEST.filter(
      (entry) => entry.capability === 'unreachable',
    )
    // 🔴 本条原先写 `toBe(1)`（「分母不为空」），那把**过渡态**写成了永久不变量：
    //    AC 1.7 的要求正是「不可达旧桩 SHALL 删除」，所以归零恰恰是它**达成**的标志。
    //    task 5.3 删掉 `GtG6OtherBondEcl.vue` 后 unreachable 由 1 → 0，原判据必红 ——
    //    而唯一的「修法」会是把旧桩加回来，让判据逼生产代码倒退。
    //
    //    ② 的真实不变量（unreachable ⇒ 零可用模式、零开关）由下面那条用**合成 readiness**
    //    直接验 derive 函数，不依赖 manifest 里恰好有这种 entry ⇒ 归零不会让它空转。
    expect(
      unreachable.length,
      'unreachable 又出现了 ⇒ 有新的不可达旧桩，AC 1.7 要求删除而不是登记',
    ).toBe(0)
  })

  it('① single_* 不得长出双模式开关，也不得宣称双向', () => {
    for (const capability of ['single_html', 'single_onlyoffice'] as const) {
      for (const state of SETTLED) {
        const got = deriveEntrySyncPresentation(readiness(capability), state)
        expect(got.showModeSwitch, `${capability}/${state}`).toBe(false)
        expect(got.canClaimBidirectional, `${capability}/${state}`).toBe(false)
        expect(got.canSwitchToOnlyOffice, `${capability}/${state}`).toBe(false)
      }
    }
    // 真实可用模式必须如实显示（不是一律关掉）
    expect(deriveEntrySyncPresentation(readiness('single_onlyoffice'), 'ready').showOnlyOffice).toBe(true)
    expect(deriveEntrySyncPresentation(readiness('single_html'), 'ready').showHtml).toBe(true)
  })

  it('② unreachable 零可用模式、零开关（AC 1.7）', () => {
    for (const state of SETTLED) {
      const got = deriveEntrySyncPresentation(readiness('unreachable'), state)
      expect(got, state).toMatchObject({
        showHtml: false,
        showOnlyOffice: false,
        showModeSwitch: false,
        canSwitchToHtml: false,
        canSwitchToOnlyOffice: false,
        canClaimBidirectional: false,
      })
    }
  })

  it('③ runtime contract drift 反例：静态 bidirectional 也不得宣称双向', () => {
    const drifted = readiness('bidirectional', {
      can_claim_bidirectional: false,
      allowed_modes: ['html'],
      runtime: { ...readiness('bidirectional').runtime, ready: false, adapter_id: null },
      reason: {
        code: 'CONTRACT_DRIFT',
        message: '同步契约声明的结构与已发布版本不一致。',
        next_action: '按「模板 → 插桩 → 契约 → bundle → representation」重新发布新 definitions。',
      },
    })
    const got = deriveEntrySyncPresentation(drifted, 'ready')
    expect(got.canClaimBidirectional).toBe(false)
    expect(got.showModeSwitch).toBe(false)
    expect(got.canSwitchToOnlyOffice).toBe(false)
    expect(got.noticeKind).toBe('danger')
    // 原因必须是后端那句可操作中文，不是笼统文案、也不是裸 reason code
    expect(got.noticeReason).toContain('重新发布新 definitions')
    expect(got.noticeReason).not.toMatch(/[A-Z]{3,}_[A-Z_]{3,}/)
  })

  it('④ pending 常显两侧未互通的原因，不按目标态展示', () => {
    for (const state of SETTLED) {
      const got = deriveEntrySyncPresentation(readiness(null), state)
      expect(got.canClaimBidirectional, state).toBe(false)
      expect(got.showModeSwitch, state).toBe(false)
      expect(got.noticeKind, state).not.toBe('none')
      expect(got.noticeSummary.length, state).toBeGreaterThan(0)
      expect(got.noticeReason.length, state).toBeGreaterThan(0)
    }
  })

  it('任何形态都不得出现笼统成功文案', () => {
    const banned = ['同步成功', '已同步', '双向已开启', '一切正常']
    const shapes: [Capability, EntrySyncLoadState][] = []
    for (const capability of OBSERVED) {
      for (const state of ['loading', 'revalidating', 'ready', 'error'] as EntrySyncLoadState[]) {
        shapes.push([capability, state])
      }
    }
    for (const [capability, state] of shapes) {
      const got = deriveEntrySyncPresentation(readiness(capability), state)
      const text = `${got.noticeLabel}${got.noticeSummary}${got.noticeReason}`
      for (const word of banned) {
        expect(text, `${capability}/${state}`).not.toContain(word)
      }
    }
  })
})

describe('接线闭合：已接单源的宿主必须真的用上 showModeSwitch', () => {
  const SRC = resolve(__dirname, '../../../..')

  // 🔴 原先这里是一份**手抄清单**（只有 `GtM7SpecialReserve.vue` 一条）。task 3.5 分批迁移后，
  //    真实已接单源的宿主有十几个，清单却一条没涨 ⇒ 这条判据声称覆盖「已接单源的宿主」，
  //    实际只看过其中一个，另外十几个的假接线它一律看不见。改为**现算**：
  //    「画了 segmented + 自身文本出现单源」即纳入，清单不可能再与代码漂移。
  // 🔴 带 `g` 标志的正则，`.test()` 会累进 `lastIndex`（有状态）⇒ 同一个对象反复 test 会
  //    交替返回 false。判存在用无标志版；取标签**不能**用正则（见下）。
  const SEGMENTED_TAG_ONE = /<el-segmented[\s\S]{0,400}?>/

  /**
   * 引号感知地截出 `<el-segmented ...>` 开标签全文。
   *
   * 🔴 原来这里用 `/<el-segmented[\s\S]{0,400}?>/g`。它会在**属性值内部的 `>`** 处提前
   * 截断 —— 模板里常见 `@change="(val: any) => …"`，那个 `=>` 的 `>` 就是截断点。
   * 现算全仓 349 个 `el-segmented` 标签里有 **26 个**被这样截断，其中 **3 个因此改变判定**：
   * `GtB60Bundle.vue`（2 处）与 `GtJ1EmployeeCompensation.vue`（1 处）的模式开关被残片
   * 判成「不是模式开关」⇒ 本判据会放过它们，分桶时还会把这两个宿主误列进「没有模式
   * 开关、可以豁免」。扫描器的截断不是精度问题，是会造成**错误豁免**的正确性问题。
   */
  function segmentedOpenTags(text: string): string[] {
    const out: string[] = []
    let i = 0
    for (;;) {
      i = text.indexOf('<el-segmented', i)
      if (i < 0) break
      let j = i + '<el-segmented'.length
      let quote: string | null = null
      while (j < text.length) {
        const ch = text[j]
        if (quote) {
          if (ch === quote) quote = null
        } else if (ch === '"' || ch === "'") {
          quote = ch
        } else if (ch === '>') {
          j += 1
          break
        }
        j += 1
      }
      out.push(text.slice(i, j))
      i = j
    }
    return out
  }
  const SINGLE_SOURCE = /useEntrySyncReadiness|entrySyncPresentation/
  /** HTML↔OO 这一组选项值（含「把标签当值」的 `'HTML'` / `'OnlyOffice'` 写法）。 */
  const MODE_OPTION_VALUES = new Set([
    'html', 'onlyoffice', 'oo', 'online-edit', 'structured', 'docx', 'excel',
    'HTML', 'OnlyOffice',
  ])
  /**
   * 中文标签直接当值（`['结构化视图', '在线编辑']`，可带 emoji 前缀）。
   *
   * 🔴 2026-11-04：与棘轮 2026-11-03 补的是同一形态（A 轮 AC-41）。这里原先只认英文 / 小写
   *    枚举 ⇒ `WorkpaperWordEditor.vue` 接单源后，它的 `genericModeOptions` 被解析成两个中文值、
   *    一个都不在上面的集合里 ⇒ 判成「不是模式开关」⇒ 本判据对这个宿主报「算不出模式开关」。
   */
  const ZH_ONLINE_EDIT_VALUE = /^[^'"\n]{0,8}在线编辑$/

  function walkVue(dir: string, out: string[]): string[] {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name)
      if (name === '__tests__' || name === 'node_modules') continue
      if (statSync(full).isDirectory()) walkVue(full, out)
      else if (name.endsWith('.vue')) out.push(full)
    }
    return out
  }

  function attrOf(tag: string, name: string): string | null {
    const m = new RegExp(`(?:^|\\s)${name}="([^"]*)"`).exec(tag)
    return m ? m[1] : null
  }

  /** 把 `:options` 表达式解成「选项值集合」：内联数组 / 同文件常量 / 一层别名。 */
  function resolveOptionValues(expr: string | null, text: string, depth = 0): Set<string> | null {
    if (!expr || depth > 2) return null
    const trimmed = expr.trim()
    const pick = (body: string): Set<string> => {
      const withValue = [...body.matchAll(/value:\s*['"]([^'"]+)['"]/g)].map((m) => m[1])
      if (withValue.length) return new Set(withValue)
      return new Set([...body.matchAll(/['"]([^'"]+)['"]/g)].map((m) => m[1]))
    }
    if (trimmed.startsWith('[')) return pick(trimmed)
    const ident = /^([A-Za-z_$][\w$]*)(?:\.value)?$/.exec(trimmed)
    if (!ident) return null
    const decl = new RegExp(`const\\s+${ident[1]}\\s*=\\s*`).exec(text)
    if (!decl) return null
    const rest = text.slice(decl.index + decl[0].length)
    if (rest.trimStart().startsWith('[')) {
      const off = rest.length - rest.trimStart().length
      let d = 0
      let k = off
      let q: string | null = null
      for (; k < rest.length; k += 1) {
        const c = rest[k]
        if (q) {
          if (c === q) q = null
        } else if (c === '"' || c === "'" || c === '`') q = c
        else if (c === '[') d += 1
        else if (c === ']') {
          d -= 1
          if (d === 0) {
            k += 1
            break
          }
        }
      }
      return pick(rest.slice(off, k))
    }
    const head = rest.slice(0, 300)
    // 平台共享的 HTML↔OO 选项工厂
    if (head.includes('dualModeHtmlOoOptions')) return new Set(['html', 'onlyoffice'])
    const alias = /^\s*([A-Za-z_$][\w$]*)\s*(?:$|\n|\/\/)/m.exec(head)
    if (alias && alias[1] !== ident[1]) return resolveOptionValues(alias[1], text, depth + 1)
    return null
  }

  /**
   * 这个 segmented 让用户选的是「HTML ↔ OnlyOffice」还是业务口径？
   *
   * 🔴 口径换过两次，两次错法相反，都被真实数据打红：
   *   v1「整个标签里出现模式值或模式绑定名」⇒ **假阳**：`GtH3InvestmentProperty.vue` 的
   *      `measurementModel`（成本法 / 公允价值，纯业务）因为外层写了
   *      `v-if="currentMode === 'html'"` 被判成模式开关 ⇒ 判据会逼着给业务控件套同步门。
   *   v2「只看标签内的值字面量」⇒ **假阴**：`GtCControlTest.vue` 的 `deviationViewMode`
   *      （structured↔online-edit = C 循环对 HTML↔OO 的叫法）和 `GtA51CashflowAudit.vue`
   *      的 `segOpts` 把选项放在常量里，标签内一个模式值都看不到 ⇒ 判据放过真模式开关。
   *
   * 现在按**选项语义**判，且只看 `:options`（不看 `v-if` —— 业务控件完全可以用模式做前置
   * 条件）：选项值能解析出来就按值判；解析不出来再退到「选项标识符里带 mode」。
   */
  function isModeSwitchTag(tag: string, text = ''): boolean {
    const opts = attrOf(tag, ':options')
    const values = resolveOptionValues(opts, text)
    if (values) {
      let hit = 0
      for (const v of values) if (MODE_OPTION_VALUES.has(v)) hit += 1
      // 「在线编辑」+ 至少一个别的视图 ⇒ 模式开关（中文标签当值的写法）
      if (values.size >= 2 && [...values].some((v) => ZH_ONLINE_EDIT_VALUE.test(v))) return true
      return hit >= 2
    }
    if (opts !== null && /mode/i.test(opts)) return true
    // 第三级回退：选项值与选项名都问不出时看**模型绑定名**。
    // 🔴 这里必须写 `/^mode$|Mode$/` 而不是 `/mode/i`：后者会命中 `measurementModel`
    //    里的 "Mode"（M-o-d-e-l 含 mode），把成本法/公允价值选择器又判成模式开关 ——
    //    也就是把 v1 的假阳换一种方式请回来。`viewMode` / `currentMode` / `dualMode`
    //    以 Mode 结尾，`measurementModel` / `depreciationBranch` 不。
    const model = attrOf(tag, 'v-model') ?? attrOf(tag, ':model-value')
    if (!model) return false
    const last = model.replace(/\.value$/, '').split('.').pop() ?? ''
    return /^mode$|Mode$/.test(last)
  }

  const wiredHosts = walkVue(SRC, [])
    .map((file) => relative(SRC, file).split('\\').join('/'))
    .filter((rel) => {
      const text = readFileSync(join(SRC, rel), 'utf-8')
      return SEGMENTED_TAG_ONE.test(text) && SINGLE_SOURCE.test(text)
    })
    .sort()

  it('分母不为空且含样板宿主（否则本判据在空集上恒绿）', () => {
    expect(wiredHosts, '一个已接单源的宿主都算不出 ⇒ 扫描器失锚').not.toEqual([])
    expect(wiredHosts).toContain('components/workpaper/GtM7SpecialReserve.vue')
  })

  it.each(wiredHosts)('%s 的模式开关 v-if 绑在 presentation.showModeSwitch 上', (rel) => {
    const text = readFileSync(join(SRC, rel), 'utf-8')
    expect(text).toMatch(SINGLE_SOURCE)
    const segmented = segmentedOpenTags(text)
    expect(segmented.length, '宿主里找不到 el-segmented ⇒ 判据失锚').toBeGreaterThan(0)
    // 🔴 只要求**模式开关**被门控。同一宿主里的业务分段器（如 L4 的债券分支选择器）
    //    不该被同步能力门控 —— 原先按 `segmented.length` 全量要求会把它们一起误伤。
    const modeTags = segmented.filter((tag) => isModeSwitchTag(tag, text))
    expect(modeTags.length, `算不出模式开关 ⇒ 判据失锚：${segmented[0]?.slice(0, 160)}`)
      .toBeGreaterThan(0)
    const gated = modeTags.filter((tag) => /v-if="[^"]*showModeSwitch[^"]*"/.test(tag))
    expect(gated.length, `开关没绑 showModeSwitch：${modeTags[0]?.slice(0, 160)}`).toBe(
      modeTags.length,
    )
  })

  it('判据可伪证：把 v-if 换成恒真时必须认不出', () => {
    const tag = '<el-segmented v-if="true" :options="modeToggleOptions">'
    expect(/v-if="[^"]*showModeSwitch[^"]*"/.test(tag)).toBe(false)
    const real = '<el-segmented v-if="entrySync.presentation.value.showModeSwitch" :options="o">'
    expect(/v-if="[^"]*showModeSwitch[^"]*"/.test(real)).toBe(true)
  })

  it('业务分段器判据可伪证：四种真实形态都要判对', () => {
    // ① 纯业务、选项名无 mode
    expect(
      isModeSwitchTag('<el-segmented v-model="bondBranch" :options="branchOptions" />'),
    ).toBe(false)
    // ② 模式开关、选项名带 mode 但解析不出值（`modeOptions` 多在 composable 里）
    expect(
      isModeSwitchTag('<el-segmented :model-value="d.currentMode.value" :options="d.modeOptions.value" />'),
    ).toBe(true)
    // ③ 🔴 v1 的假阳：业务控件外层用模式做前置条件，不得因此被当成模式开关
    const h3Business =
      '<el-segmented v-if="currentMode === \'html\'" v-model="measurementModel" :options="measurementOptions" />'
    const h3Text = "const measurementOptions = [{ label: '成本法', value: 'cost' }, { label: '公允价值', value: 'fair_value' }]"
    expect(isModeSwitchTag(h3Business, h3Text), 'v1 的假阳回来了').toBe(false)
    // ④ 🔴 v2 的假阴：选项放在常量里，标签内看不到模式值
    const cctMode = '<el-segmented v-model="deviationViewMode" :options="deviationModeOptions" />'
    const cctText =
      "const deviationModeOptions = [{ label: '结构化视图', value: 'structured' }, { label: '在线编辑', value: 'online-edit' }]"
    expect(isModeSwitchTag(cctMode, cctText), 'v2 的假阴回来了').toBe(true)
    // ⑤ 一层别名（A51 的 `const segOpts = modeOptions`）
    const a51 = '<el-segmented v-model="viewMode" :options="segOpts" />'
    const a51Text =
      "const modeOptions = [{ label: '结构化', value: 'structured' }, { label: 'Excel', value: 'excel' }]\nconst segOpts = modeOptions\n"
    expect(isModeSwitchTag(a51, a51Text), '别名链没跟上').toBe(true)
    // ⑥ 中文标签直接当值（WorkpaperWordEditor 的 `genericModeOptions`；可带 emoji 前缀）
    const zh = '<el-segmented v-model="genericViewMode" :options="genericModeOptions" />'
    expect(isModeSwitchTag(zh, "const genericModeOptions = ['结构化视图', '在线编辑']"), '中文标签当值认不出').toBe(true)
    expect(isModeSwitchTag(zh, "const genericModeOptions = ['结构化视图', '📊 在线编辑']")).toBe(true)
    // 反例：中文业务选项（没有「在线编辑」）不得被纳入
    expect(isModeSwitchTag(zh, "const genericModeOptions = ['按客户', '按产品']"), '中文业务分段器被误纳').toBe(false)
  })

  // 🔴 钉住标签截取方式：换回 `/<el-segmented[\s\S]{0,400}?>/` 一类正则会在属性值里的
  //    `>` 处提前截断（`@change="(v) => f(v)"`），残片让模式开关被判成非模式开关 ⇒
  //    本判据放过它、分桶还会把宿主误列进「可豁免」。这条用例就是防那次回退。
  it('标签截取必须引号感知（内联箭头函数里的 `>` 不得当成标签结束）', () => {
    // 属性顺序本就任意：把内联箭头函数放在**最前**，截断就会同时丢掉 `:options` 与
    // `:model-value`，三级判据全部失去依据 ⇒ 判定从「模式开关」翻成「业务分段器」。
    const tricky =
      '<el-segmented\n' +
      '  @change="(val: string) => dual.onModeChange(val)"\n' +
      '  :model-value="dual.currentMode.value"\n' +
      '  :options="dual.modeOptions.value"\n' +
      '/>\n' +
      '<p>后面的内容不该被吞进标签</p>'
    const tags = segmentedOpenTags(tricky)
    expect(tags.length).toBe(1)
    expect(tags[0].endsWith('/>'), `截出来的不是完整开标签：${tags[0]}`).toBe(true)
    expect(tags[0]).toContain('modeOptions')
    expect(tags[0], '把标签之后的正文也吞进来了').not.toContain('<p>')
    // 朴素正则在同一输入上会截断，丢掉 `:options` ⇒ 判定随之反转，这正是它的危害
    const naive = tricky.match(/<el-segmented[\s\S]{0,400}?>/)?.[0] ?? ''
    expect(naive.includes('modeOptions'), '朴素正则竟没截断 ⇒ 本用例失锚').toBe(false)
    expect(isModeSwitchTag(tags[0]), '完整标签应判为模式开关').toBe(true)
    expect(isModeSwitchTag(naive), '残片应判不出来 —— 这就是截断的危害').toBe(false)
  })
})
