/**
 * 委派建议分配算法守卫。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 17
 * 被测: `../delegationSuggestion.ts`
 * _Requirements: 11.2, 11.3, 11.4, 11.5, 11.9, 11.10_
 *
 * ## 判据取舍
 *
 * 本文件的断言按「行为优先、源码级兜底」分两层：
 *
 * - **行为断言**（主体）：构造能让缺陷显形的输入。例如「负载未知按 0 处理」这个
 *   缺陷只在「有负载已知的成员且其负载 > 0」时才显形 —— 若只用单成员或全未知
 *   的输入，两种实现产出完全相同。
 * - **源码级断言**（兜底）：只用于行为上不可区分的约束（零 Vue 依赖 / 零 IO），
 *   且一律断言**形态**而非「标识符是否出现」—— 后者挡不住把条件改成 `if (false)`。
 *
 * ## SOD 这条为什么用单成员场景做决定性判据
 *
 * 多成员场景下，即便移除 `reviewerStaffId !== assigneeStaffId` 过滤，执行人也常
 * 因排序键落后而不会被选成复核人 ⇒ 变异不显形。单成员场景是唯一必然显形的形态：
 * 候选池里只剩执行人自己，去掉 SOD 过滤就一定会把他选成自己的复核人。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import * as fs from 'node:fs'
import * as path from 'node:path'

import {
  suggestDelegation,
  computeTargetWeight,
  RISK_COEFFICIENT,
  RISK_MIN_SENIORITY,
  ROW_COUNT_DIVISOR,
  WARNING_NO_RISK_MATCH,
  type DelegationMember,
  type DelegationTarget,
  type RiskLevel,
} from '../delegationSuggestion'

// ═══════════════════════════════════════════════════════════════════════════
// 源码定位（双哨兵，禁写死回退级数）
// ═══════════════════════════════════════════════════════════════════════════

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 14; i += 1) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵）')
}

const ROOT = repoRoot()
const P_MODULE = path.join(
  ROOT, 'audit-platform', 'frontend', 'src',
  'components', 'workpaper', 'composables', 'delegationSuggestion.ts',
)

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/** 剥注释（带字符串状态机，不被 `accept="image/*"` 一类内容骗）。 */
function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') {
        out += n ?? ''
        i += 2
        continue
      }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c
      out += c
      i += 1
      continue
    }
    if (c === '/' && n === '/') {
      while (i < src.length && src[i] !== '\n') i += 1
      continue
    }
    if (c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    out += c
    i += 1
  }
  return out
}

// ═══════════════════════════════════════════════════════════════════════════
// 构造 helper
// ═══════════════════════════════════════════════════════════════════════════

function member(
  staffId: string,
  seniority: number,
  currentLoad: number | null,
  name?: string,
): DelegationMember {
  return { staffId, name: name ?? `成员${staffId}`, seniority, currentLoad }
}

function target(
  wpIndexId: string,
  risk: RiskLevel,
  rowCount = 0,
  cycle = 'D',
): DelegationTarget {
  return { wpIndexId, wpCode: `WP-${wpIndexId}`, cycle, risk, rowCount }
}

function sum(values: number[]): number {
  return values.reduce((acc, v) => acc + v, 0)
}

// ═══════════════════════════════════════════════════════════════════════════
// helper 自检
// ═══════════════════════════════════════════════════════════════════════════

describe('helper 自检', () => {
  it('stripComments 剥注释保字面量', () => {
    const s = stripComments(`const a = 'H' // 注释里写 riskCoefficient`)
    expect(s).toContain("'H'")
    expect(s).not.toContain('注释里写')
  })

  it('被测源码可读且非空（防扫描面为空导致源码级断言空转）', () => {
    const src = stripComments(read(P_MODULE))
    expect(src.length).toBeGreaterThan(2000)
    expect(src).toContain('export function suggestDelegation')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 模块契约（行为上不可区分的约束才用源码级断言）
// ═══════════════════════════════════════════════════════════════════════════

describe('模块契约：纯函数、零 IO', () => {
  it('不依赖 vue、不含 IO', () => {
    const src = stripComments(read(P_MODULE))
    expect(/from\s+['"]vue['"]/.test(src), '不得 import vue').toBe(false)
    expect(
      /\bfetch\s*\(|\baxios\b|http\.(get|post|put|delete)|apiPaths|commonApi/.test(src),
      '不得含 IO / 网络调用',
    ).toBe(false)
    expect(/localStorage|sessionStorage|document\.|window\./.test(src), '不得触碰浏览器 API')
      .toBe(false)
  })

  it('禁用 pm / te / sat 作标识符（平台术语禁令）', () => {
    const src = stripComments(read(P_MODULE))
    expect(/\b(?:const|let|var|function)\s+(?:pm|te|sat)\b/.test(src), '禁用 pm/te/sat 变量名')
      .toBe(false)
    expect(/\b(?:pm|te|sat)\s*[:?]\s*(?:number|string|boolean)/.test(src), '禁用 pm/te/sat 字段名')
      .toBe(false)
  })

  it('返回值恒含七键', () => {
    const r = suggestDelegation({ members: [], targets: [], riskDimensionAvailable: true })
    for (const k of [
      'assignments', 'loadAfter', 'loadIncrement', 'unknownLoadStaffIds',
      'unassignedTargets', 'degraded', 'warnings',
    ]) {
      expect(Object.keys(r), `返回值缺少键 ${k}`).toContain(k)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 权重公式（变异 ③：去掉 riskCoefficient）
// ═══════════════════════════════════════════════════════════════════════════

describe('权重公式 weight = 1 + riskCoefficient + rowCount / 20', () => {
  it('riskCoefficient 取值：H 1.0 / M 0.5 / L 0.2 / null 0.3', () => {
    expect(RISK_COEFFICIENT.H).toBe(1.0)
    expect(RISK_COEFFICIENT.M).toBe(0.5)
    expect(RISK_COEFFICIENT.L).toBe(0.2)
    expect(RISK_COEFFICIENT.none).toBe(0.3)
  })

  it('未评估（0.3）的系数高于已评估为低风险（0.2）—— 有意为之，不得"修正"', () => {
    expect(
      RISK_COEFFICIENT.none > RISK_COEFFICIENT.L,
      '「未评估」的不确定性高于「已评估为低风险」，调低会让未填风险矩阵的项目负载被系统性低估',
    ).toBe(true)
  })

  it('行数为 0 时逐档取值（riskCoefficient 被抹掉即打红）', () => {
    expect(computeTargetWeight('H', 0)).toBeCloseTo(2.0, 6)
    expect(computeTargetWeight('M', 0)).toBeCloseTo(1.5, 6)
    expect(computeTargetWeight('L', 0)).toBeCloseTo(1.2, 6)
    expect(computeTargetWeight(null, 0)).toBeCloseTo(1.3, 6)
  })

  it('四档权重必须互不相等（去掉风险系数会让四档全部塌成同一值）', () => {
    const set = new Set([
      computeTargetWeight('H', 0),
      computeTargetWeight('M', 0),
      computeTargetWeight('L', 0),
      computeTargetWeight(null, 0),
    ])
    expect(set.size, '四个风险档的权重不得相同').toBe(4)
  })

  it('行数项按 rowCount / 20 计入', () => {
    expect(computeTargetWeight('L', 20)).toBeCloseTo(1.2 + 1, 6)
    expect(computeTargetWeight('H', 50)).toBeCloseTo(2.0 + 2.5, 6)
    expect(ROW_COUNT_DIVISOR).toBe(20)
  })

  it('assignment.weight 与 computeTargetWeight 同源', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 0), member('b', 3, 0)],
      targets: [target('t1', 'H', 40)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toHaveLength(1)
    expect(r.assignments[0].weight).toBeCloseTo(computeTargetWeight('H', 40), 6)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// SOD 硬约束（变异 ①）
// ═══════════════════════════════════════════════════════════════════════════

describe('SOD 硬约束：reviewerStaffId !== assigneeStaffId', () => {
  it('多成员场景下每条 assignment 都满足 SOD', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 0), member('b', 3, 1), member('c', 2, 0)],
      targets: [
        target('t1', 'H', 10), target('t2', 'M', 20),
        target('t3', 'L', 5), target('t4', null, 0),
      ],
      riskDimensionAvailable: true,
    })
    expect(r.assignments.length).toBeGreaterThan(0)
    for (const a of r.assignments) {
      expect(
        a.reviewerStaffId === null || a.reviewerStaffId !== a.assigneeStaffId,
        `底稿 ${a.wpCode} 违反 SOD：执行人与复核人同为 ${a.assigneeStaffId}`,
      ).toBe(true)
    }
  })

  it('【决定性】仅 1 名成员时复核人必须为 null 且记 warning（去掉 SOD 过滤即打红）', () => {
    const r = suggestDelegation({
      members: [member('solo', 5, 0, '张三')],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toHaveLength(1)
    expect(r.assignments[0].assigneeStaffId).toBe('solo')
    expect(
      r.assignments[0].reviewerStaffId,
      '宁可复核人为 null，也不得让执行人复核自己的工作',
    ).toBeNull()
    expect(r.assignments[0].reviewerName).toBeNull()
    expect(
      r.warnings.some((w) => w.includes('复核')),
      '单成员时必须记 warning 说明无法产生复核人',
    ).toBe(true)
  })

  it('执行人是唯一最高资历者时复核人仍不得是他自己', () => {
    // 资历 5 者唯一；若无 SOD 过滤，候选池里只有他（其余资历 < 5 全被门槛挡掉）
    const r = suggestDelegation({
      members: [member('top', 5, 0), member('low', 1, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toHaveLength(1)
    const a = r.assignments[0]
    expect(a.assigneeStaffId).toBe('top')
    expect(a.reviewerStaffId).not.toBe('top')
    expect(a.reviewerStaffId, '无「资历 ≥ 执行人」的他人时复核人应为 null').toBeNull()
  })

  it('复核人资历不低于执行人', () => {
    const r = suggestDelegation({
      members: [member('a', 1, 0), member('b', 2, 5), member('c', 4, 9)],
      targets: [target('t1', 'L', 0), target('t2', 'L', 0), target('t3', 'M', 0)],
      riskDimensionAvailable: true,
    })
    const byId = new Map(
      [member('a', 1, 0), member('b', 2, 5), member('c', 4, 9)].map((m) => [m.staffId, m]),
    )
    for (const a of r.assignments) {
      if (!a.reviewerStaffId) continue
      const rev = byId.get(a.reviewerStaffId)!
      const asg = byId.get(a.assigneeStaffId)!
      expect(
        rev.seniority >= asg.seniority,
        `底稿 ${a.wpCode} 复核人资历 ${rev.seniority} 低于执行人 ${asg.seniority}`,
      ).toBe(true)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 负载不变式（loadAfter 单调不减 / 总增量 == 权重之和）
// ═══════════════════════════════════════════════════════════════════════════

describe('负载不变式', () => {
  const members = [member('a', 3, 2), member('b', 3, 0), member('c', 4, 5)]
  const targets = [
    target('t1', 'H', 10), target('t2', 'M', 0),
    target('t3', 'L', 60), target('t4', null, 3), target('t5', 'M', 40),
  ]

  it('loadAfter 对每个成员单调不减（不低于其分配前负载）', () => {
    const r = suggestDelegation({ members, targets, riskDimensionAvailable: true })
    for (const m of members) {
      if (m.currentLoad === null) continue
      expect(
        r.loadAfter[m.staffId] >= m.currentLoad,
        `成员 ${m.staffId} 分配后负载 ${r.loadAfter[m.staffId]} 低于分配前 ${m.currentLoad}`,
      ).toBe(true)
    }
  })

  it('loadAfter 总增量等于所分配权重之和', () => {
    const r = suggestDelegation({ members, targets, riskDimensionAvailable: true })
    const baseline = sum(members.map((m) => m.currentLoad ?? 0))
    const after = sum(Object.values(r.loadAfter))
    const weights = sum(r.assignments.map((a) => a.weight))
    expect(after - baseline).toBeCloseTo(weights, 6)
  })

  it('loadIncrement 覆盖全部成员，其合计等于权重之和（含负载未知者）', () => {
    const withUnknown = [...members, member('d', 3, null)]
    const r = suggestDelegation({ members: withUnknown, targets, riskDimensionAvailable: true })
    expect(Object.keys(r.loadIncrement).sort()).toEqual(
      withUnknown.map((m) => m.staffId).sort(),
    )
    expect(sum(Object.values(r.loadIncrement)))
      .toBeCloseTo(sum(r.assignments.map((a) => a.weight)), 6)
  })

  it('loadAfter 只含负载已知的成员（不为未知基线编造 0）', () => {
    const r = suggestDelegation({
      members: [member('known', 3, 4), member('unknown', 3, null)],
      targets: [target('t1', 'M', 0), target('t2', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(Object.keys(r.loadAfter)).toEqual(['known'])
    expect(r.unknownLoadStaffIds).toEqual(['unknown'])
  })

  it('分配是累加的：同一人连续两次分配后负载反映两次权重', () => {
    const r = suggestDelegation({
      members: [member('solo', 5, 1)],
      targets: [target('t1', 'M', 0), target('t2', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toHaveLength(2)
    expect(r.loadAfter.solo).toBeCloseTo(1 + 1.5 + 1.5, 6)
  })

  it('负载均衡：两名同资历成员、四张同权重底稿应各分两张', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 0), member('b', 3, 0)],
      targets: [
        target('t1', 'M', 0), target('t2', 'M', 0),
        target('t3', 'M', 0), target('t4', 'M', 0),
      ],
      riskDimensionAvailable: true,
    })
    const counts = new Map<string, number>()
    for (const a of r.assignments) {
      counts.set(a.assigneeStaffId, (counts.get(a.assigneeStaffId) ?? 0) + 1)
    }
    expect(counts.get('a')).toBe(2)
    expect(counts.get('b')).toBe(2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 负载未知三态（变异 ④：按 0 处理）
// ═══════════════════════════════════════════════════════════════════════════

describe('负载未知（null）不得按 0 参与均衡', () => {
  it('【决定性】有负载已知的合格成员时不选负载未知者', () => {
    // 若把 null 当 0，unknownGuy 的负载(0) < busy 的负载(100) ⇒ 会被选中
    const r = suggestDelegation({
      members: [member('busy', 3, 100), member('unknownGuy', 3, null)],
      targets: [target('t1', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toHaveLength(1)
    expect(
      r.assignments[0].assigneeStaffId,
      '负载未知不等于负载为 0；负载已知的合格成员优先，否则工作会全堆给数据缺失者',
    ).toBe('busy')
  })

  it('负载未知者进 unknownLoadStaffIds 并记 warning', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 1), member('u1', 3, null, '李四'), member('u2', 3, null, '王五')],
      targets: [target('t1', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.unknownLoadStaffIds.sort()).toEqual(['u1', 'u2'])
    expect(r.warnings.some((w) => w.includes('负载未知'))).toBe(true)
    expect(r.warnings.some((w) => w.includes('李四') && w.includes('王五'))).toBe(true)
  })

  it('无负载已知的合格成员时才启用未知者（后备档）', () => {
    const r = suggestDelegation({
      members: [member('u', 3, null)],
      targets: [target('t1', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toHaveLength(1)
    expect(r.assignments[0].assigneeStaffId).toBe('u')
    expect(r.loadAfter.u, '负载未知者不进 loadAfter').toBeUndefined()
    expect(r.loadIncrement.u).toBeCloseTo(1.5, 6)
  })

  it('复核人同样优先取负载已知者', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 0), member('knownRev', 3, 50), member('unknownRev', 3, null)],
      targets: [target('t1', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments[0].reviewerStaffId).toBe('knownRev')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 降级标注（变异 ②：degraded 恒 false）
// ═══════════════════════════════════════════════════════════════════════════

describe('降级标注：riskDimensionAvailable === false', () => {
  it('degraded === true 且 warnings 含「未做风险匹配」', () => {
    const r = suggestDelegation({
      members: [member('a', 1, 0), member('b', 1, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: false,
    })
    expect(r.degraded).toBe(true)
    expect(
      r.warnings.some((w) => w.includes('未做风险匹配')),
      'warnings 必须含「未做风险匹配」字样',
    ).toBe(true)
    expect(r.warnings).toContain(WARNING_NO_RISK_MATCH)
  })

  it('riskDimensionAvailable === true 时 degraded === false 且无该 warning', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 0), member('b', 3, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.degraded).toBe(false)
    expect(r.warnings.some((w) => w.includes('未做风险匹配'))).toBe(false)
  })

  it('degraded ⟺ warnings 含「未做风险匹配」（双向等价，两侧都不得单独改）', () => {
    for (const available of [true, false]) {
      const r = suggestDelegation({
        members: [member('a', 3, 0), member('b', 3, 0)],
        targets: [target('t1', 'M', 0)],
        riskDimensionAvailable: available,
      })
      const flagged = r.warnings.some((w) => w.includes('未做风险匹配'))
      expect(
        r.degraded === flagged,
        `riskDimensionAvailable=${available} 时 degraded=${r.degraded} 与 warning=${flagged} 不等价`,
      ).toBe(true)
    }
  })

  it('降级时忽略资历门槛：H 风险底稿也能分给低资历成员（纯负载均衡）', () => {
    const r = suggestDelegation({
      members: [member('junior', 1, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: false,
    })
    expect(r.assignments, '降级时不按风险匹配资历，故不应因门槛而未分配').toHaveLength(1)
    expect(r.assignments[0].assigneeStaffId).toBe('junior')
    expect(r.unassignedTargets).toHaveLength(0)
  })

  it('降级时权重按 null 系数（0.3）计，与入参风险值无关', () => {
    const rh = suggestDelegation({
      members: [member('a', 1, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: false,
    })
    const rl = suggestDelegation({
      members: [member('a', 1, 0)],
      targets: [target('t1', 'L', 0)],
      riskDimensionAvailable: false,
    })
    expect(rh.assignments[0].weight).toBeCloseTo(1.3, 6)
    expect(rl.assignments[0].weight).toBeCloseTo(1.3, 6)
  })

  it('降级时 assignment.risk 仍如实回显入参声明值（供 UI 标注"该值未参与匹配"）', () => {
    const r = suggestDelegation({
      members: [member('a', 1, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: false,
    })
    expect(r.assignments[0].risk).toBe('H')
    expect(r.assignments[0].rationale).toContain('未做风险匹配')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// rationale
// ═══════════════════════════════════════════════════════════════════════════

describe('rationale 必须含判据数值', () => {
  it('每条 assignment 都有非空 rationale 且含数字', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 2), member('b', 4, 1)],
      targets: [target('t1', 'H', 40), target('t2', 'L', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments.length).toBeGreaterThan(0)
    for (const a of r.assignments) {
      expect(typeof a.rationale).toBe('string')
      expect(a.rationale.length, `底稿 ${a.wpCode} 的 rationale 不得为空`).toBeGreaterThan(10)
      expect(/\d/.test(a.rationale), 'rationale 必须含判据数值').toBe(true)
    }
  })

  it('rationale 含风险等级、资历、负载与权重四类判据数值', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 2, '张三'), member('b', 4, 1, '李四')],
      targets: [target('t1', 'H', 40)],
      riskDimensionAvailable: true,
    })
    const text = r.assignments[0].rationale
    expect(text, '应含风险等级').toMatch(/风险\s*高/)
    expect(text, '应含资历').toContain('资历')
    expect(text, '应含负载').toContain('负载')
    expect(text, '应含权重').toContain('权重')
    expect(text, '应含执行人姓名').toMatch(/张三|李四/)
  })

  it('rationale 不得只写「按负载均衡分配」（无判据数值等于没有理由）', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 0), member('b', 3, 0)],
      targets: [target('t1', 'M', 0)],
      riskDimensionAvailable: true,
    })
    const text = r.assignments[0].rationale.trim()
    expect(text).not.toBe('按负载均衡分配')
    expect(text.replace(/[^\d]/g, '').length, 'rationale 中的数字位数应足以承载判据')
      .toBeGreaterThan(2)
  })

  it('复核人留空时 rationale 说明原因', () => {
    const r = suggestDelegation({
      members: [member('solo', 5, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments[0].rationale).toContain('复核人留空')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 边界：成员为空 / 单成员 / 资历不足
// ═══════════════════════════════════════════════════════════════════════════

describe('边界：成员为空', () => {
  it('members 为空 ⇒ assignments 为空 + warnings 说明', () => {
    const r = suggestDelegation({
      members: [],
      targets: [target('t1', 'H', 0), target('t2', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toEqual([])
    expect(r.loadAfter).toEqual({})
    expect(r.loadIncrement).toEqual({})
    expect(r.warnings.length, '成员为空必须记 warning').toBeGreaterThan(0)
    expect(r.warnings.some((w) => w.includes('成员'))).toBe(true)
  })

  it('members 为空时全部目标进 unassignedTargets 并带原因', () => {
    const r = suggestDelegation({
      members: [],
      targets: [target('t1', 'H', 0), target('t2', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.unassignedTargets).toHaveLength(2)
    for (const u of r.unassignedTargets) {
      expect(u.reason.length).toBeGreaterThan(5)
    }
  })

  it('members 与 targets 都为空时不抛异常', () => {
    const r = suggestDelegation({ members: [], targets: [], riskDimensionAvailable: true })
    expect(r.assignments).toEqual([])
    expect(r.unassignedTargets).toEqual([])
  })

  it('targets 为空但有成员 ⇒ assignments 为空、loadAfter 等于分配前负载', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 7)],
      targets: [],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toEqual([])
    expect(r.loadAfter.a).toBe(7)
    expect(r.loadIncrement.a).toBe(0)
  })
})

describe('边界：只有一个成员', () => {
  it('无法产生复核人 ⇒ reviewer 为 null 并记 warning', () => {
    const r = suggestDelegation({
      members: [member('solo', 5, 3, '张三')],
      targets: [target('t1', 'H', 0), target('t2', 'M', 10)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toHaveLength(2)
    for (const a of r.assignments) {
      expect(a.reviewerStaffId).toBeNull()
      expect(a.reviewerName).toBeNull()
      expect(a.assigneeStaffId).toBe('solo')
    }
    expect(
      r.warnings.some((w) => w.includes('1 名成员') || w.includes('复核')),
      '必须 warning 说明单成员无法满足执行人 ≠ 复核人',
    ).toBe(true)
  })

  it('单成员仍正常累加负载（不因无复核人而跳过分配）', () => {
    const r = suggestDelegation({
      members: [member('solo', 5, 3)],
      targets: [target('t1', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.loadAfter.solo).toBeCloseTo(4.5, 6)
    expect(r.unassignedTargets).toHaveLength(0)
  })
})

describe('边界：资历不足以覆盖 H 风险', () => {
  it('无人满足 H 风险资历门槛 ⇒ 记 warning 但不硬塞', () => {
    const r = suggestDelegation({
      members: [member('j1', 1, 0), member('j2', 2, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments, '高风险底稿不得硬塞给资历不足者').toHaveLength(0)
    expect(r.unassignedTargets).toHaveLength(1)
    expect(r.unassignedTargets[0].risk).toBe('H')
    expect(r.unassignedTargets[0].reason).toContain('资历')
    expect(r.warnings.some((w) => w.includes('资历'))).toBe(true)
  })

  it('H 风险未分配时其余风险档正常分配（不整体放弃）', () => {
    const r = suggestDelegation({
      members: [member('j1', 1, 0), member('j2', 2, 0)],
      targets: [target('tH', 'H', 0), target('tM', 'M', 0), target('tL', 'L', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.unassignedTargets.map((u) => u.wpIndexId)).toEqual(['tH'])
    expect(r.assignments.map((a) => a.wpIndexId).sort()).toEqual(['tL', 'tM'])
  })

  it('未分配的目标不进 loadIncrement 合计（权重等式仍成立）', () => {
    const r = suggestDelegation({
      members: [member('j1', 1, 0)],
      targets: [target('tH', 'H', 0), target('tL', 'L', 0)],
      riskDimensionAvailable: true,
    })
    expect(sum(Object.values(r.loadIncrement)))
      .toBeCloseTo(sum(r.assignments.map((a) => a.weight)), 6)
  })

  it('资历门槛是绝对值：默认 H=3 / M=2 / L=1 / none=1', () => {
    expect(RISK_MIN_SENIORITY.H).toBe(3)
    expect(RISK_MIN_SENIORITY.M).toBe(2)
    expect(RISK_MIN_SENIORITY.L).toBe(1)
    expect(RISK_MIN_SENIORITY.none).toBe(1)
    expect(
      RISK_MIN_SENIORITY.H > RISK_MIN_SENIORITY.M
      && RISK_MIN_SENIORITY.M >= RISK_MIN_SENIORITY.L,
      '门槛须随风险等级单调不减',
    ).toBe(true)
  })

  it('可由入参覆盖门槛（项目组资历口径不同时）', () => {
    const r = suggestDelegation({
      members: [member('j', 1, 0), member('k', 1, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: true,
      minSeniorityByRisk: { H: 1 },
    })
    expect(r.assignments).toHaveLength(1)
    expect(r.unassignedTargets).toHaveLength(0)
  })

  it('【反向自检】门槛若按团队最高资历反推，本用例会变绿 —— 故须保持不硬塞', () => {
    // 团队最高资历 2 < H 门槛 3 ⇒ 必须未分配。
    // 若实现改成「团队里最高资历者即可承担 H」，assignments 会变成 1 条，该断言打红。
    const r = suggestDelegation({
      members: [member('j1', 2, 0), member('j2', 1, 0)],
      targets: [target('t1', 'H', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toHaveLength(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 稳定性与输入鲁健性
// ═══════════════════════════════════════════════════════════════════════════

describe('稳定性与输入鲁健性', () => {
  it('同一输入两次调用结果逐字段相同（可复算）', () => {
    const args = {
      members: [member('a', 3, 1), member('b', 3, 1), member('c', 5, 0)],
      targets: [target('t1', 'H', 10), target('t2', 'M', 10), target('t3', 'L', 10)],
      riskDimensionAvailable: true,
    }
    expect(JSON.stringify(suggestDelegation(args)))
      .toBe(JSON.stringify(suggestDelegation(args)))
  })

  it('不修改入参数组与对象（纯函数）', () => {
    const members = [member('a', 3, 1), member('b', 3, 2)]
    const targets = [target('t2', 'L', 0), target('t1', 'H', 0)]
    const snapshot = JSON.stringify({ members, targets })
    suggestDelegation({ members, targets, riskDimensionAvailable: true })
    expect(JSON.stringify({ members, targets })).toBe(snapshot)
  })

  it('风险降序处理：H 先于 M 先于 L', () => {
    const r = suggestDelegation({
      members: [member('a', 5, 0), member('b', 5, 0)],
      targets: [target('tL', 'L', 0), target('tM', 'M', 0), target('tH', 'H', 0)],
      riskDimensionAvailable: true,
    })
    expect(r.assignments.map((a) => a.wpIndexId)).toEqual(['tH', 'tM', 'tL'])
  })

  it('重复 staffId 按首次出现去重并记 warning', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 0), member('a', 5, 99)],
      targets: [target('t1', 'M', 0)],
      riskDimensionAvailable: true,
    })
    expect(Object.keys(r.loadAfter)).toEqual(['a'])
    expect(r.loadAfter.a).toBeCloseTo(1.5, 6)
    expect(r.warnings.some((w) => w.includes('重复'))).toBe(true)
  })

  it('非法数值（NaN 资历 / 负行数 / 负负载）不产生 NaN', () => {
    const r = suggestDelegation({
      members: [
        { staffId: 'a', name: 'A', seniority: Number.NaN, currentLoad: -5 },
        { staffId: 'b', name: 'B', seniority: 3, currentLoad: Number.NaN },
      ],
      targets: [{ wpIndexId: 't1', wpCode: 'W1', cycle: 'D', risk: 'L', rowCount: -10 }],
      riskDimensionAvailable: true,
    })
    for (const a of r.assignments) {
      expect(Number.isFinite(a.weight), 'weight 不得为 NaN').toBe(true)
    }
    for (const v of Object.values(r.loadAfter)) {
      expect(Number.isFinite(v), 'loadAfter 不得含 NaN').toBe(true)
    }
    for (const v of Object.values(r.loadIncrement)) {
      expect(Number.isFinite(v), 'loadIncrement 不得含 NaN').toBe(true)
    }
  })

  it('缺 wpIndexId 的目标被跳过（不产出无法定位的建议）', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 0), member('b', 3, 0)],
      targets: [
        { wpIndexId: '', wpCode: 'X', cycle: 'D', risk: 'M', rowCount: 0 },
        target('t1', 'M', 0),
      ],
      riskDimensionAvailable: true,
    })
    expect(r.assignments.map((a) => a.wpIndexId)).toEqual(['t1'])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// targets 按 wpIndexId 去重（确定性回归，钉死 PBT 偶发反例）
//
// 来历：`Property: 已分配 + 未分配 == 有效目标数（不丢不重）` 偶发打红
// （seed -986847725），反例 = `members: []` + 两条 `wpIndexId: 'v'` 的目标。
// 成因是 members 侧按 staffId 去重、targets 侧只过滤空值不去重，两侧口径不对称。
//
// 🔴 本组用例**不依赖随机种子**：PBT 只在恰好抽到重复 id 时才显形（`arbTarget`
//    的 wpIndexId 空间大，命中概率低），故「PBT 单次全绿」不构成该缺陷不存在的
//    证据。确定性用例是这条不变式的唯一稳定守卫。
// ═══════════════════════════════════════════════════════════════════════════

describe('targets 按 wpIndexId 去重', () => {
  it('【决定性】PBT 反例：members 为空 + 同 wpIndexId 两条 ⇒ 只产出一条未分配项', () => {
    // 反例逐字复现（seed -986847725）
    const r = suggestDelegation({
      members: [],
      targets: [
        { wpIndexId: 'v', wpCode: ' ', cycle: 'D', risk: 'H', rowCount: 0 },
        { wpIndexId: 'v', wpCode: ' ', cycle: 'D', risk: 'H', rowCount: 0 },
      ],
      riskDimensionAvailable: true,
    })
    expect(r.assignments.length + r.unassignedTargets.length, '有效目标数按 wpIndexId 去重后为 1')
      .toBe(1)
    const ids = r.unassignedTargets.map((u) => u.wpIndexId)
    expect(new Set(ids).size, 'unassignedTargets 内 wpIndexId 必须唯一').toBe(ids.length)
    expect(
      r.warnings.some((w) => w.includes('重复') && w.includes('wpIndexId')),
      'warnings 须如实记录重复目标（与 members 侧重复告警同构）',
    ).toBe(true)
  })

  it('【决定性】有成员时同 wpIndexId 重复只产出一条 assignment（走分配分支）', () => {
    const r = suggestDelegation({
      members: [member('a', 3, 0), member('b', 3, 0)],
      targets: [
        { wpIndexId: 'dup', wpCode: 'WP-dup', cycle: 'D', risk: 'M', rowCount: 0 },
        { wpIndexId: 'dup', wpCode: 'WP-dup', cycle: 'D', risk: 'M', rowCount: 0 },
      ],
      riskDimensionAvailable: true,
    })
    expect(r.assignments.map((a) => a.wpIndexId), '重复目标只产出一条建议').toEqual(['dup'])
    expect(r.unassignedTargets).toEqual([])
    expect(r.warnings.some((w) => w.includes('重复') && w.includes('wpIndexId'))).toBe(true)
    // 重复条不得被累加进负载（否则「分配后负载」虚高、均衡判断失真）
    expect(sum(Object.values(r.loadIncrement)))
      .toBeCloseTo(computeTargetWeight('M', 0), 6)
  })

  it('【决定性】去重发生在排序之前：首次出现胜出，不随排序漂移', () => {
    // 首条 L/0 行（权重 1.2）、次条 H/100 行（权重 7.0）。
    // 排序键含风险秩：若先排序再去重，H 那条会排到前面并胜出 ⇒ 断言打红。
    const r = suggestDelegation({
      members: [member('a', 5, 0), member('b', 5, 0)],
      targets: [
        { wpIndexId: 'same', wpCode: 'WP-first', cycle: 'D', risk: 'L', rowCount: 0 },
        { wpIndexId: 'same', wpCode: 'WP-second', cycle: 'E', risk: 'H', rowCount: 100 },
      ],
      riskDimensionAvailable: true,
    })
    expect(r.assignments).toHaveLength(1)
    expect(r.assignments[0].wpCode, '首次出现胜出').toBe('WP-first')
    expect(r.assignments[0].cycle).toBe('D')
    expect(r.assignments[0].risk).toBe('L')
    expect(r.assignments[0].weight).toBeCloseTo(computeTargetWeight('L', 0), 6)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// PBT（numRuns: 20，平台已下调例数）
// ═══════════════════════════════════════════════════════════════════════════

const PBT = { numRuns: 20 } as const

const arbMember = fc.record({
  staffId: fc.string({ minLength: 1, maxLength: 4 }).filter((s) => s.trim().length > 0),
  name: fc.string({ minLength: 1, maxLength: 6 }),
  seniority: fc.integer({ min: 0, max: 6 }),
  currentLoad: fc.oneof(fc.constant(null), fc.integer({ min: 0, max: 200 })),
})

const arbTarget = fc.record({
  wpIndexId: fc.string({ minLength: 1, maxLength: 5 }).filter((s) => s.trim().length > 0),
  wpCode: fc.string({ minLength: 1, maxLength: 6 }),
  cycle: fc.constantFrom('D', 'E', 'F', 'G', 'H', 'K', 'L'),
  risk: fc.constantFrom<RiskLevel>('H', 'M', 'L', null),
  rowCount: fc.integer({ min: 0, max: 500 }),
})

describe('PBT: 委派建议不变式', () => {
  it('Property: 每条 assignment 满足 reviewerStaffId !== assigneeStaffId', () => {
    fc.assert(
      fc.property(
        fc.array(arbMember, { maxLength: 6 }),
        fc.array(arbTarget, { maxLength: 8 }),
        fc.boolean(),
        (members, targets, available) => {
          const r = suggestDelegation({
            members, targets, riskDimensionAvailable: available,
          })
          for (const a of r.assignments) {
            expect(a.reviewerStaffId === null || a.reviewerStaffId !== a.assigneeStaffId).toBe(true)
          }
        },
      ),
      PBT,
    )
  })

  it('Property: loadAfter 单调不减且总增量等于所分配权重之和', () => {
    fc.assert(
      fc.property(
        fc.array(arbMember, { minLength: 1, maxLength: 6 }),
        fc.array(arbTarget, { maxLength: 8 }),
        fc.boolean(),
        (members, targets, available) => {
          const r = suggestDelegation({
            members, targets, riskDimensionAvailable: available,
          })
          // 单调不减（按去重后首次出现的基线比较）
          const baseline = new Map<string, number | null>()
          for (const m of members) {
            const id = String(m.staffId).trim()
            if (!id || baseline.has(id)) continue
            baseline.set(
              id,
              typeof m.currentLoad === 'number' && Number.isFinite(m.currentLoad)
                ? Math.max(0, m.currentLoad)
                : null,
            )
          }
          for (const [id, after] of Object.entries(r.loadAfter)) {
            const before = baseline.get(id)
            expect(before).not.toBeNull()
            expect(after >= (before as number) - 1e-9).toBe(true)
          }
          // 总增量 == 权重之和
          expect(sum(Object.values(r.loadIncrement)))
            .toBeCloseTo(sum(r.assignments.map((a) => a.weight)), 6)
          // loadAfter 侧的增量同样成立（仅计负载已知者）
          let knownBase = 0
          for (const id of Object.keys(r.loadAfter)) knownBase += baseline.get(id) as number
          let knownInc = 0
          for (const id of Object.keys(r.loadAfter)) knownInc += r.loadIncrement[id] ?? 0
          expect(sum(Object.values(r.loadAfter)) - knownBase).toBeCloseTo(knownInc, 6)
        },
      ),
      PBT,
    )
  })

  it('Property: degraded ⟺ riskDimensionAvailable === false ⟺ warnings 含「未做风险匹配」', () => {
    fc.assert(
      fc.property(
        fc.array(arbMember, { maxLength: 5 }),
        fc.array(arbTarget, { maxLength: 5 }),
        fc.boolean(),
        (members, targets, available) => {
          const r = suggestDelegation({
            members, targets, riskDimensionAvailable: available,
          })
          const flagged = r.warnings.some((w) => w.includes('未做风险匹配'))
          expect(r.degraded).toBe(!available)
          expect(flagged).toBe(!available)
        },
      ),
      PBT,
    )
  })

  it('Property: 已分配 + 未分配 == 有效目标数（不丢不重）', () => {
    fc.assert(
      fc.property(
        fc.array(arbMember, { maxLength: 5 }),
        fc.array(arbTarget, { maxLength: 8 }),
        (members, targets) => {
          const r = suggestDelegation({ members, targets, riskDimensionAvailable: true })
          const valid = targets.filter((t) => String(t.wpIndexId).trim() !== '')
          const ids = new Set(valid.map((t) => String(t.wpIndexId)))
          expect(r.assignments.length + r.unassignedTargets.length).toBe(ids.size)
          const seen = new Set<string>()
          for (const a of r.assignments) {
            expect(seen.has(a.wpIndexId)).toBe(false)
            seen.add(a.wpIndexId)
          }
          for (const u of r.unassignedTargets) {
            expect(seen.has(u.wpIndexId)).toBe(false)
            seen.add(u.wpIndexId)
          }
        },
      ),
      PBT,
    )
  })

  it('Property: 未降级时执行人资历必满足该风险门槛', () => {
    fc.assert(
      fc.property(
        fc.array(arbMember, { minLength: 1, maxLength: 6 }),
        fc.array(arbTarget, { maxLength: 8 }),
        (members, targets) => {
          const r = suggestDelegation({ members, targets, riskDimensionAvailable: true })
          const byId = new Map<string, number>()
          for (const m of members) {
            const id = String(m.staffId).trim()
            if (!id || byId.has(id)) continue
            byId.set(id, Number.isFinite(m.seniority) ? m.seniority : 0)
          }
          for (const a of r.assignments) {
            const key = a.risk === 'H' || a.risk === 'M' || a.risk === 'L' ? a.risk : 'none'
            expect(byId.get(a.assigneeStaffId)! >= RISK_MIN_SENIORITY[key]).toBe(true)
          }
        },
      ),
      PBT,
    )
  })

  it('Property: 每条 assignment 都有含数字的非空 rationale', () => {
    fc.assert(
      fc.property(
        fc.array(arbMember, { maxLength: 5 }),
        fc.array(arbTarget, { maxLength: 5 }),
        fc.boolean(),
        (members, targets, available) => {
          const r = suggestDelegation({
            members, targets, riskDimensionAvailable: available,
          })
          for (const a of r.assignments) {
            expect(a.rationale.length).toBeGreaterThan(10)
            expect(/\d/.test(a.rationale)).toBe(true)
          }
        },
      ),
      PBT,
    )
  })
})
