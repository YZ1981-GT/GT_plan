/**
 * 宿主取「适用准则」的守卫
 * （applicable-standards-frontend-wiring R3.2/R4.2 → -runtime-and-sync-guard R3/R5.1）
 *
 * 四件事：
 * 1. 共享 helper `resolveHostApplicableStandards` 的取值优先级与形态兼容
 * 2. composable `useHostApplicableStandards` 的三层优先级（Property 3）
 * 3. 🔴 宿主源码不得用 `(runtime as any)?.applicableStandards` 绕过类型系统直接读
 *    —— 上一轮守卫只匹配 `runtime?.applicableStandards`，I3/I5/I6 三个宿主用 `as any`
 *    强转绕过，死 fallback 一直留着
 * 4. 🔴 两条渲染路径（`GtWpRenderer` / `GtWorkpaperShell`）必须向 scaffold 传
 *    `applicableStandards`，否则 runtime 层恒空、门控又回到「恒空/恒开」
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import {
  resolveHostApplicableStandards,
  useHostApplicableStandards,
} from '../composables/hostApplicableStandards'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'

const WORKPAPER_DIR = resolve(__dirname, '..')

describe('resolveHostApplicableStandards', () => {
  it('project_context 优先（后端统一注入点）', () => {
    expect(
      resolveHostApplicableStandards({
        project_context: { applicable_standards: ['soe_standalone', 'soe'] },
        applicable_standards: ['listed_standalone'],
      }),
    ).toEqual(['soe_standalone', 'soe'])
  })

  it('projectContext（camel）次之，再到顶层 snake / camel', () => {
    expect(
      resolveHostApplicableStandards({ projectContext: { applicable_standards: ['listed'] } }),
    ).toEqual(['listed'])
    expect(resolveHostApplicableStandards({ applicable_standards: ['soe'] })).toEqual(['soe'])
    expect(resolveHostApplicableStandards({ applicableStandards: ['soe'] })).toEqual(['soe'])
  })

  it('🔴 v2 对象也能归一（I1~I6 历史下发形态）', () => {
    expect(
      resolveHostApplicableStandards({
        project_context: {
          applicable_standards: { entity_type: 'soe', scope: 'standalone', stage: 'normal' },
        },
      }),
    ).toEqual(['soe_standalone', 'soe', 'standalone'])
  })

  it('逗号串与 JSON 串兼容', () => {
    expect(resolveHostApplicableStandards({ applicable_standards: 'soe, listed' }))
      .toEqual(['soe', 'listed'])
    expect(resolveHostApplicableStandards({ applicable_standards: '["listed_standalone"]' }))
      .toEqual(['listed_standalone'])
  })

  it('缺字段返回 []（各循环的「空 = 全部适用」宽松回退不变）', () => {
    expect(resolveHostApplicableStandards(undefined)).toEqual([])
    expect(resolveHostApplicableStandards(null)).toEqual([])
    expect(resolveHostApplicableStandards({})).toEqual([])
  })

  it('显式 fallback 生效（宿主可先给 props 值）', () => {
    expect(resolveHostApplicableStandards({}, ['listed_standalone']))
      .toEqual(['listed_standalone'])
  })
})

// ─── Property 3：composable 三层优先级 ────────────────────────────────────────

/** 在给定 runtime 值下挂载一个使用 composable 的组件，返回其求值结果。 */
function evaluate(
  sources: Parameters<typeof useHostApplicableStandards>[0],
  runtimeValue?: string[],
): string[] {
  let out: string[] = []
  const Host = defineComponent({
    setup() {
      const std = useHostApplicableStandards(sources)
      return () => {
        out = std.value
        return h('div')
      }
    },
  })
  const provide: Record<symbol, unknown> = {}
  if (runtimeValue) {
    provide[WorkpaperRuntimeContextKey as unknown as symbol] = {
      applicableStandards: ref(runtimeValue),
    }
  }
  const wrapper = mount(Host, { global: { provide } })
  wrapper.unmount()
  return out
}

describe('useHostApplicableStandards（Property 3）', () => {
  it('explicit 非空 → 胜出', () => {
    expect(
      evaluate(
        {
          explicit: () => ['listed_standalone'],
          htmlData: () => ({ project_context: { applicable_standards: ['soe'] } }),
        },
        ['private'],
      ),
    ).toEqual(['listed_standalone'])
  })

  it('explicit 空 → 退到 htmlData', () => {
    expect(
      evaluate(
        {
          explicit: () => [],
          htmlData: () => ({ project_context: { applicable_standards: ['soe_standalone'] } }),
        },
        ['private'],
      ),
    ).toEqual(['soe_standalone'])
  })

  it('explicit / htmlData 都空 → 退到 runtime context', () => {
    expect(evaluate({ explicit: () => undefined, htmlData: () => ({}) }, ['soe_standalone', 'soe']))
      .toEqual(['soe_standalone', 'soe'])
  })

  it('三层皆空 / 无 runtime provide → []（不抛）', () => {
    expect(evaluate({})).toEqual([])
    expect(evaluate({ htmlData: () => null })).toEqual([])
  })

  it('每层都经归一（v2 对象 / 逗号串）', () => {
    expect(evaluate({ explicit: () => ({ entity_type: 'LISTED', scope: 'Standalone' }) }))
      .toEqual(['listed_standalone', 'listed', 'standalone'])
    expect(evaluate({ explicit: () => 'soe_standalone, soe' }))
      .toEqual(['soe_standalone', 'soe'])
  })
})

// ─── 源码守卫 ────────────────────────────────────────────────────────────────

describe('宿主源码守卫', () => {
  const hostFiles = readdirSync(WORKPAPER_DIR)
    .filter((f) => f.startsWith('Gt') && f.endsWith('.vue'))

  it('扫到宿主文件（防 glob 失效导致守卫空转）', () => {
    expect(hostFiles.length).toBeGreaterThan(20)
  })

  it('🔴 不得直接读 runtime 的 applicableStandards（含 as any 强转绕过）', () => {
    const offenders: string[] = []
    for (const f of hostFiles) {
      const src = readFileSync(resolve(WORKPAPER_DIR, f), 'utf-8')
      // 覆盖 `runtime?.applicableStandards` 与 `(runtime as any)?.applicableStandards`
      if (/(?:runtime|runtimeCtx|runtimeContext)(?:\s+as\s+any)?\)?\??\.applicableStandards/.test(src)) {
        offenders.push(f)
      }
    }
    expect(
      offenders,
      '宿主请改用 useHostApplicableStandards({ explicit, htmlData })，'
        + '它在 setup 作用域 inject runtime 并统一归一',
    ).toEqual([])
  })

  it('凡用到适用准则的宿主，都经共享 composable', () => {
    const offenders: string[] = []
    for (const f of hostFiles) {
      const src = readFileSync(resolve(WORKPAPER_DIR, f), 'utf-8')
      // 自己 computed 出 applicableStandards 却没接共享 composable → 又抄了一份取值链
      if (!/const applicableStandards = computed/.test(src)) continue
      if (!/useHostApplicableStandards|useH2ApplicableStandards|hostApplicableStandards/.test(src)) {
        offenders.push(f)
      }
    }
    expect(offenders).toEqual([])
  })
})

describe('两条渲染路径都要向 scaffold 传适用准则（R2.1 / R2.2）', () => {
  const read = (f: string) => readFileSync(resolve(WORKPAPER_DIR, f), 'utf-8')

  it('GtWpRenderer 传 render-config 顶层 applicable_standards', () => {
    const src = read('GtWpRenderer.vue')
    expect(src).toMatch(/applicableStandards:\s*runtimeApplicableStandards/)
    expect(src).toMatch(/applicable_standards/)
  })

  it('GtWorkpaperShell 暴露 prop 并透传', () => {
    const src = read('GtWorkpaperShell.vue')
    expect(src).toMatch(/applicableStandards\?:/)
    expect(src).toMatch(/applicableStandards:\s*toRef\(props,\s*'applicableStandards'\)/)
  })
})
