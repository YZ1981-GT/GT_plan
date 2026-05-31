/**
 * M1 / CI 防退化 属性测试 — CI 基线单调性（Property 6）
 *
 * 背景：frontend-consistency-m1 的 4 项治理（T1 GtAmountCell / T2 ElMessage.error /
 *   T4 状态硬编码）都把"量化指标"写进 `.github/workflows/baselines.json` 的
 *   `_v3_coverage_guards`，并在 `.github/workflows/ci.yml` 的 frontend-build job 里
 *   用 grep + 阈值比较做防退化卡点。卡点对每个指标施加**方向约束**：
 *     - GtAmountCell-uses              只增不减（only-increase）→ measured < baseline 时 CI 失败
 *     - no-bare-amount-cell-violations 只减不增（only-decrease）→ measured > baseline 时 CI 失败（ESLint AST 精确口径，2026-05-30 复盘替代 align-right-cols 粗口径）
 *     - elmessage-error-in-catch       只减不增（only-decrease，目标 0）
 *     - status-hardcoding-5files       只减不增（only-decrease，目标 0）
 *
 * 本测试是 CI 卡点**决策函数**的纯逻辑属性测试（无组件挂载、无 grep、无文件扫描），
 * 把 ci.yml 的 shell 判定逻辑抽象成纯函数 `ciGuardPasses`，用 fast-check 证明其
 * 单调性语义，并校验 baselines.json 的 M1 字段值/方向与设计一致。
 *
 * Property 6 (Task 13.1): CI 基线单调性
 *   对任意 PR，GtAmountCell-uses 只增不减；no-bare-amount-cell-violations / elmessage-error-in-catch /
 *   status-hardcoding-5files 只减不增。任一方向违反则 CI 失败。
 *   **Validates: Requirements 3.3, 3.4, 5.4**
 *
 * 四组子断言：
 *   P6-a 守门决策函数正确性：only-increase ⟺ m >= b；only-decrease ⟺ m <= b。
 *   P6-b 单调退化检测：only-increase 任意 m < b 必失败；only-decrease 任意 m > b 必失败。
 *   P6-c 改进永远通过：only-increase 任意 m >= b 必通过；only-decrease 任意 m <= b 必通过。
 *   P6-d baselines.json 字段一致性：M1 四字段值/方向/target 与设计锁定值一致。
 *
 * 实施方案：vitest + fast-check（numRuns: 50，纯逻辑无挂载可放宽）。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// ── 守门决策函数（镜像 ci.yml frontend-build job 的 shell 判定逻辑） ──
//   only-increase（GtAmountCell-uses）：CI 中 `if measured < baseline then exit 1`
//     → 通过 ⟺ measured >= baseline
//   only-decrease（no-bare-amount-cell-violations / elmessage-error-in-catch / status-hardcoding-5files）：
//     CI 中 `if measured > baseline then exit 1`
//     → 通过 ⟺ measured <= baseline
type Direction = 'only-increase' | 'only-decrease'

function ciGuardPasses(measured: number, baseline: number, direction: Direction): boolean {
  if (direction === 'only-increase') return measured >= baseline
  if (direction === 'only-decrease') return measured <= baseline
  return false
}

// ── M1 指标 → 方向 映射（与 ci.yml + baselines.json 对齐） ──
interface MetricSpec {
  field: string
  direction: Direction
  /** 设计锁定的 baseline 值（来自 tasks.md Task 3.1 / Task 14） */
  expectedBaseline: number
  /** 若该指标有配套 target 字段则记录其期望值 */
  targetField?: string
  expectedTarget?: number
}

const M1_METRICS: readonly MetricSpec[] = [
  // 复盘修订（2026-05-30）：GtAmountCell-uses 口径统一为 105（grep 行数，与 CI guard 同口径）
  { field: 'GtAmountCell-uses', direction: 'only-increase', expectedBaseline: 105 },
  // align-right-cols 粗口径已降级 informational，CI 卡点改用 ESLint 精确 no-bare-amount-cell-violations
  { field: 'no-bare-amount-cell-violations', direction: 'only-decrease', expectedBaseline: 88 },
  {
    field: 'elmessage-error-in-catch',
    direction: 'only-decrease',
    expectedBaseline: 0,
    targetField: 'elmessage-error-in-catch-target',
    expectedTarget: 0,
  },
  {
    field: 'status-hardcoding-5files',
    direction: 'only-decrease',
    expectedBaseline: 4,
    targetField: 'status-hardcoding-5files-target',
    expectedTarget: 0,
  },
] as const

// ── 读取真实 baselines.json（仓库根 .github/workflows/baselines.json） ──
//   测试文件位于 audit-platform/frontend/src/__tests__/，到仓库根需上溯 4 层。
//   vitest ESM 下无 __dirname，用 import.meta.url + fileURLToPath 推导。
const __dirname = dirname(fileURLToPath(import.meta.url))
const BASELINES_PATH = resolve(__dirname, '../../../../.github/workflows/baselines.json')

interface CoverageGuards {
  [key: string]: unknown
}

function loadBaselines(): { guards: CoverageGuards } {
  const raw = readFileSync(BASELINES_PATH, 'utf-8')
  const json = JSON.parse(raw) as Record<string, unknown>
  const guards = json['_v3_coverage_guards'] as CoverageGuards
  return { guards }
}

describe('M1 Property 6: CI 基线单调性', () => {
  /**
   * P6-a — 守门决策函数正确性
   * ∀ measured, baseline：
   *   ciGuardPasses(m, b, 'only-increase') === (m >= b)
   *   ciGuardPasses(m, b, 'only-decrease') === (m <= b)
   * **Validates: Requirements 3.3, 3.4, 5.4**
   */
  it('(P6-a) 守门决策函数与 >=/<= 语义恒等', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100000 }),
        fc.integer({ min: 0, max: 100000 }),
        (measured, baseline) => {
          // only-increase ⟺ m >= b
          expect(ciGuardPasses(measured, baseline, 'only-increase')).toBe(measured >= baseline)
          // only-decrease ⟺ m <= b
          expect(ciGuardPasses(measured, baseline, 'only-decrease')).toBe(measured <= baseline)
        },
      ),
      { numRuns: 50 },
    )
  })

  /**
   * P6-b — 单调退化检测（治理目标：退化必被卡）
   * only-increase（GtAmountCell-uses）：任意 measured 严格小于 baseline → 守门失败。
   * only-decrease（align-right / catch 裸用 / 状态硬编码）：任意 measured 严格大于 baseline → 守门失败。
   * **Validates: Requirements 3.3, 3.4, 5.4**
   */
  it('(P6-b) 退化方向必被 CI 卡点拦截（only-increase 减少→fail / only-decrease 增加→fail）', () => {
    // only-increase 指标：measured = baseline - delta（delta > 0）→ 必失败
    fc.assert(
      fc.property(
        fc.integer({ min: 50, max: 100000 }), // baseline 保证有下降空间
        fc.integer({ min: 1, max: 50 }), // 严格减少量 delta < 0
        (baseline, delta) => {
          const measured = baseline - delta
          expect(
            ciGuardPasses(measured, baseline, 'only-increase'),
            `GtAmountCell-uses 退化 ${measured} < ${baseline} 应被卡`,
          ).toBe(false)
        },
      ),
      { numRuns: 50 },
    )

    // only-decrease 指标：measured = baseline + delta（delta > 0）→ 必失败
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100000 }),
        fc.integer({ min: 1, max: 50 }), // 严格增加量 delta > 0
        (baseline, delta) => {
          const measured = baseline + delta
          for (const direction of ['only-decrease'] as const) {
            expect(
              ciGuardPasses(measured, baseline, direction),
              `only-decrease 退化 ${measured} > ${baseline} 应被卡`,
            ).toBe(false)
          }
        },
      ),
      { numRuns: 50 },
    )
  })

  /**
   * P6-c — 改进永远通过（治理推进不应误伤）
   * only-increase：measured >= baseline（覆盖更多）→ 永远通过。
   * only-decrease：measured <= baseline（债务更少）→ 永远通过。
   * **Validates: Requirements 3.3, 3.4, 5.4**
   */
  it('(P6-c) 改进方向永远通过（only-increase 增加→pass / only-decrease 减少→pass）', () => {
    // only-increase：measured = baseline + delta（delta >= 0）→ 通过
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100000 }),
        fc.integer({ min: 0, max: 50 }), // delta >= 0（含持平边界）
        (baseline, delta) => {
          const measured = baseline + delta
          expect(
            ciGuardPasses(measured, baseline, 'only-increase'),
            `GtAmountCell-uses 改进 ${measured} >= ${baseline} 应通过`,
          ).toBe(true)
        },
      ),
      { numRuns: 50 },
    )

    // only-decrease：measured = baseline - delta（delta >= 0，钳制非负）→ 通过
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100000 }),
        fc.integer({ min: 0, max: 50 }),
        (baseline, delta) => {
          const measured = Math.max(0, baseline - delta)
          expect(
            ciGuardPasses(measured, baseline, 'only-decrease'),
            `only-decrease 改进 ${measured} <= ${baseline} 应通过`,
          ).toBe(true)
        },
      ),
      { numRuns: 50 },
    )

    // 边界：measured === baseline（持平）两个方向都应通过
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 100000 }), (b) => {
        expect(ciGuardPasses(b, b, 'only-increase')).toBe(true)
        expect(ciGuardPasses(b, b, 'only-decrease')).toBe(true)
      }),
      { numRuns: 50 },
    )
  })

  /**
   * P6-d — baselines.json 字段一致性
   * 真实读取 .github/workflows/baselines.json，断言 M1 四字段存在、值与设计锁定值一致、
   * 且 target 字段（catch 裸用 / 状态硬编码目标 0）就位。这是 CI 卡点"真源"的回归保护：
   * 若有人误改 baselines.json（如把 GtAmountCell-uses 调低绕过卡点），本断言立即失败。
   * **Validates: Requirements 3.3, 3.4, 5.4**
   */
  it('(P6-d) baselines.json M1 四字段值/方向/target 与设计锁定一致', () => {
    const { guards } = loadBaselines()

    for (const metric of M1_METRICS) {
      // 字段存在且为数字
      const actual = guards[metric.field]
      expect(typeof actual, `${metric.field} 应为数字`).toBe('number')
      // 值与设计锁定一致
      expect(actual, `${metric.field} 值应 === ${metric.expectedBaseline}`).toBe(
        metric.expectedBaseline,
      )

      // target 字段（若有）就位且为期望值
      if (metric.targetField) {
        const target = guards[metric.targetField]
        expect(typeof target, `${metric.targetField} 应为数字`).toBe('number')
        expect(target, `${metric.targetField} 应 === ${metric.expectedTarget}`).toBe(
          metric.expectedTarget,
        )
      }
    }
  })

  /**
   * P6-d 补充 — 用真实 baseline 跑守门函数（当前代码状态 = 持平/改进，应全部通过）
   * 把 baselines.json 的真实 baseline 喂给 ciGuardPasses，用"当前 = baseline"（持平场景）
   * 验证当前 spec 完成态下四道卡点全部 PASS（无退化），并显式验证退化场景被拦。
   * **Validates: Requirements 3.3, 3.4, 5.4**
   */
  it('(P6-d 补充) 真实 baseline 下持平通过、退化拦截', () => {
    const { guards } = loadBaselines()

    for (const metric of M1_METRICS) {
      const baseline = guards[metric.field] as number

      // 持平（measured === baseline）→ 通过
      expect(
        ciGuardPasses(baseline, baseline, metric.direction),
        `${metric.field} 持平应通过`,
      ).toBe(true)

      if (metric.direction === 'only-increase') {
        // 上升 +1 → 通过；下降 -1 → 拦截（baseline > 0 才有下降空间）
        expect(ciGuardPasses(baseline + 1, baseline, metric.direction)).toBe(true)
        if (baseline > 0) {
          expect(ciGuardPasses(baseline - 1, baseline, metric.direction)).toBe(false)
        }
      } else {
        // only-decrease：下降（钳制非负）→ 通过；上升 +1 → 拦截
        expect(ciGuardPasses(Math.max(0, baseline - 1), baseline, metric.direction)).toBe(true)
        expect(ciGuardPasses(baseline + 1, baseline, metric.direction)).toBe(false)
      }
    }
  })
})
