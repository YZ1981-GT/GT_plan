/**
 * B22 迁移幂等契约测试 (Task 10.2, Property P7)
 *
 * 迁移逻辑定位（design.md §数据迁移 / §3）：
 *   `B22B-def-*`（缺陷 + 严重程度）→ B22C 结构的迁移是**前端逻辑**，位于
 *   `useB22CDesignEffectiveness.loadFromUpstream(b22aResponses, b22bResponses)`：
 *     - parseB22ADeficiencies 解析 B22A 设计无效/未实施 → 缺陷（按 matchKey）
 *     - parseB22BSeverities 读取旧 `B22B-def-{n}-source` + `B22B-def-{n}-severity`
 *     - 按 matchKey 将 B22B 严重程度映射到对应 B22C 缺陷，desc 去重（仅填空、不覆盖已编辑）
 *   后端 `_a91_deficiency_letter.py` 仅是 A9 读取真源（读 B22C/B22B），非迁移写入路径。
 *   故本幂等测试以前端 vitest 覆盖。
 *
 * Property 7（幂等）：迁移执行 N 次与执行 1 次结果一致 —— 无重复行、无严重程度漂移。
 *   Validates: Requirements 10.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), info: vi.fn(), success: vi.fn() },
}))

import {
  useB22CDesignEffectiveness,
  type ChecklistResponse,
} from '../composables/useB22CDesignEffectiveness'

// ─── Fixtures ────────────────────────────────────────────────────────────────

/**
 * B22A responses：产生 2 条缺陷（控制环境 T1 / 风险评估 T2），desc 非空以便 loadFromUpstream 去重生效。
 */
function makeB22AResponses(): ChecklistResponse[] {
  return [
    { item_id: 'B22A-T1-item-1-point', conclusion: null, remark: '控制环境关键控制点', wp_ref: null },
    { item_id: 'B22A-T1-item-1-conclusion', conclusion: '设计无效', remark: null, wp_ref: null },
    { item_id: 'B22A-T2-item-1-point', conclusion: null, remark: '风险评估关键控制点', wp_ref: null },
    { item_id: 'B22A-T2-item-1-conclusion', conclusion: '未实施', remark: null, wp_ref: null },
  ]
}

/**
 * 旧 B22B-def-* 缺陷 + 严重程度（迁移来源）。source 的 tab/subPanel/index 与 B22A 对齐，
 * 使 matchKey (`${tab}|${subPanel ?? ''}|${index}`) 命中。
 */
function makeB22BDefResponses(): ChecklistResponse[] {
  return [
    { item_id: 'B22B-def-count', conclusion: null, remark: '2', wp_ref: null },
    {
      item_id: 'B22B-def-1-source',
      conclusion: null,
      remark: JSON.stringify({ tab: 1, subPanel: null, index: 1 }),
      wp_ref: null,
    },
    { item_id: 'B22B-def-1-severity', conclusion: '重大缺陷', remark: null, wp_ref: null },
    {
      item_id: 'B22B-def-2-source',
      conclusion: null,
      remark: JSON.stringify({ tab: 2, subPanel: null, index: 1 }),
      wp_ref: null,
    },
    { item_id: 'B22B-def-2-severity', conclusion: '一般缺陷', remark: null, wp_ref: null },
  ]
}

/** 快照全部区块缺陷（desc + severity + 派生 isSignificant + isControlDeficiency） */
function snapshotBlocks(c: ReturnType<typeof useB22CDesignEffectiveness>) {
  return c.blocks.value.map((b) => ({
    key: b.key,
    defs: b.deficiencies.map((d) => ({
      desc: d.desc,
      severity: d.severity,
      isSignificant: d.isSignificant,
      isControlDeficiency: d.isControlDeficiency,
    })),
  }))
}

function totalDeficiencies(c: ReturnType<typeof useB22CDesignEffectiveness>): number {
  return c.blocks.value.reduce((sum, b) => sum + b.deficiencies.length, 0)
}

// ─── Tests ───────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockGet.mockResolvedValue([])
  mockPut.mockResolvedValue({})
})

describe('B22 迁移幂等 — B22B-def-* → B22C loadFromUpstream (P7)', () => {
  it('首次迁移：B22B 严重程度按 matchKey 正确映射进 B22C', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-1'), ref('proj-1'))
      const r = c.loadFromUpstream(makeB22AResponses(), makeB22BDefResponses())

      expect(r.added).toBe(2)

      const env = c.blocks.value.find((b) => b.key === 'env')!
      const risk = c.blocks.value.find((b) => b.key === 'risk')!
      expect(env.deficiencies).toHaveLength(1)
      expect(env.deficiencies[0].desc).toBe('控制环境关键控制点')
      expect(env.deficiencies[0].severity).toBe('重大缺陷')
      expect(env.deficiencies[0].isSignificant).toBe(true) // 重大 → 值得关注（派生）

      expect(risk.deficiencies).toHaveLength(1)
      expect(risk.deficiencies[0].desc).toBe('风险评估关键控制点')
      expect(risk.deficiencies[0].severity).toBe('一般缺陷')
      expect(risk.deficiencies[0].isSignificant).toBe(false) // 一般 → 非值得关注（派生）
    })
    scope.stop()
  })

  it('执行 N 次与执行 1 次结果一致（无重复、无漂移）', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-1'), ref('proj-1'))
      const b22a = makeB22AResponses()
      const b22b = makeB22BDefResponses()

      // 执行 1 次
      c.loadFromUpstream(b22a, b22b)
      const snap1 = snapshotBlocks(c)
      const total1 = totalDeficiencies(c)
      expect(total1).toBe(2)

      // 再执行 N 次
      for (let i = 0; i < 4; i++) {
        const rN = c.loadFromUpstream(b22a, b22b)
        expect(rN.added).toBe(0) // 已存在 desc → 去重跳过，无新增
      }

      const snapN = snapshotBlocks(c)
      const totalN = totalDeficiencies(c)

      // 无重复：总数稳定
      expect(totalN).toBe(total1)
      // 无漂移：全部区块缺陷内容（含严重程度）逐字一致
      expect(snapN).toEqual(snap1)
    })
    scope.stop()
  })

  it('仅存在旧 B22B-def-* 而无 B22A 对应缺陷时，迁移不产生孤儿缺陷（无来源即不写入）', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-1'), ref('proj-1'))
      // B22A 无任何缺陷（无 -conclusion=设计无效/未实施）
      const r = c.loadFromUpstream([], makeB22BDefResponses())
      expect(r.added).toBe(0)
      expect(totalDeficiencies(c)).toBe(0)

      // 再次执行仍为 0（幂等）
      const r2 = c.loadFromUpstream([], makeB22BDefResponses())
      expect(r2.added).toBe(0)
      expect(totalDeficiencies(c)).toBe(0)
    })
    scope.stop()
  })

  it('迁移不覆盖已编辑缺陷：手工改写严重程度后再迁移不回退', () => {
    const scope = effectScope()
    scope.run(() => {
      const c = useB22CDesignEffectiveness(ref('wp-1'), ref('proj-1'))
      const b22a = makeB22AResponses()
      const b22b = makeB22BDefResponses()

      c.loadFromUpstream(b22a, b22b)
      // 审计师手工把控制环境缺陷严重程度调低为「一般缺陷」
      c.setDeficiencyField('env', 0, 'severity', '一般缺陷')
      expect(c.blocks.value.find((b) => b.key === 'env')!.deficiencies[0].severity).toBe('一般缺陷')

      // 再次迁移（同源 B22B 仍为「重大缺陷」）：desc 去重跳过，不回退手工编辑
      const r = c.loadFromUpstream(b22a, b22b)
      expect(r.added).toBe(0)
      expect(c.blocks.value.find((b) => b.key === 'env')!.deficiencies[0].severity).toBe('一般缺陷')
      expect(totalDeficiencies(c)).toBe(2)
    })
    scope.stop()
  })
})
