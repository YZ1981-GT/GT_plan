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
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

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

  it('unreachable 在 manifest 里确实存在（AC 1.7 的分母不为空）', () => {
    const unreachable = WORKPAPER_SYNC_MANIFEST.filter(
      (entry) => entry.capability === 'unreachable',
    )
    expect(unreachable.length, '没有 unreachable entry ⇒ AC 1.7 的 ② 在空集上恒真').toBe(1)
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
  /** 已接单源的宿主（棘轮基线之外的那些）。只 import 不用 = 假接线。 */
  const WIRED_HOSTS = ['components/workpaper/GtM7SpecialReserve.vue']

  it.each(WIRED_HOSTS)('%s 的模式开关 v-if 绑在 presentation.showModeSwitch 上', (rel) => {
    const text = readFileSync(resolve(SRC, rel), 'utf-8')
    expect(text).toMatch(/useEntrySyncReadiness/)
    // el-segmented 的开标签内必须出现绑到 showModeSwitch 的 v-if
    const segmented = text.match(/<el-segmented[\s\S]{0,400}?>/g) ?? []
    expect(segmented.length, '宿主里找不到 el-segmented ⇒ 判据失锚').toBeGreaterThan(0)
    const gated = segmented.filter((tag) => /v-if="[^"]*showModeSwitch[^"]*"/.test(tag))
    expect(gated.length, `开关没绑 showModeSwitch：${segmented[0]?.slice(0, 120)}`).toBe(
      segmented.length,
    )
  })

  it('判据可伪证：把 v-if 换成恒真时必须认不出', () => {
    const tag = '<el-segmented v-if="true" :options="modeToggleOptions">'
    expect(/v-if="[^"]*showModeSwitch[^"]*"/.test(tag)).toBe(false)
    const real = '<el-segmented v-if="entrySync.presentation.value.showModeSwitch" :options="o">'
    expect(/v-if="[^"]*showModeSwitch[^"]*"/.test(real)).toBe(true)
  })
})
