/**
 * 委派角色 → 资历映射守卫。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 18
 * 被测: `../delegationSeniority.ts`
 * _Requirements: 11.1, 11.6, 11.8_（本文件承担 11.3「高风险优先资历较高者」的前置口径）
 *
 * ## 本文件防的三类缺陷
 *
 * 1. **挪用 `ROLE_PRIORITY`**（`ProcedureTrimming.vue` 的底稿主编下拉排序优先级）。
 *    它 `auditor: 1 … signing_partner: 6`，语义是「越小越靠前」；资历是「越大越资深」。
 *    挪用后建议表照样有执行人有复核人，UI 上看不出任何异常，只是高风险底稿被系统性
 *    分给最年轻的人 —— 最危险的失效形态是「结果看起来仍然合理」。
 * 2. **中文 role 静默落到兜底档**。后端 `assignment_service.ROLE_MAP` 有 7 个中文别名键
 *    （`合伙人` / `项目经理` / `质控` / `审计员` / `助理` / `签字合伙人` /
 *    `独立复核合伙人`）；漏映射时中文 role 全变助理档 ⇒ 高风险底稿全进
 *    `unassignedTargets`，表现为「算法产不出建议」而非「映射漏了」。
 * 3. **未知 role 拿到高资历**。那等于「不认识这个角色」换来承担高风险底稿的资格。
 *
 * ## 判据取舍
 *
 * 主体是**行为断言**（喂 `suggestDelegation` 真实入参，看分配结果），源码级断言只用于
 * 行为上不可区分的约束（零 Vue / 零 IO），且一律先 `stripComments` —— 本模块的文档
 * 刻意在注释里写了 `ROLE_PRIORITY` 与 `auditor: 1` 等字样以记录「为何不复用」，不剥
 * 注释的「全文不含 X」判据会**误红**（那是守卫缺陷不是代码缺陷）。
 *
 * helper（`repoRoot` / `read` / `stripComments`）照抄 `views/__tests__/trimDecisionWiring.spec.ts`
 * ——刻意不抽公共模块：守卫 helper 一旦共享，改它就同时改变多个守卫的判据面。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import * as fs from 'node:fs'
import * as path from 'node:path'
import {
  ROLE_SENIORITY,
  SENIORITY_UNREGISTERED,
  SENIORITY_LABEL,
  roleSeniority,
  seniorityLabel,
  isRegisteredRole,
} from '../delegationSeniority'
import {
  suggestDelegation,
  RISK_MIN_SENIORITY,
  type DelegationMember,
} from '../delegationSuggestion'

// ═══════════════════════════════════════════════════════════════════════════
// helper（双哨兵向上找仓库根；禁写死回退级数）
// ═══════════════════════════════════════════════════════════════════════════

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 14; i += 1) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵 audit-platform/frontend/package.json + backend/app/main.py）')
}

const ROOT = repoRoot()

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') { out += n ?? ''; i += 2; continue }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i += 1; continue }
    if (c === '/' && n === '/') { while (i < src.length && src[i] !== '\n') i += 1; continue }
    if (c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    if (c === '<' && src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i)
      i = end < 0 ? src.length : end + 3
      continue
    }
    out += c
    i += 1
  }
  return out
}

const P_MODULE = path.join(
  ROOT, 'audit-platform', 'frontend', 'src',
  'components', 'workpaper', 'composables', 'delegationSeniority.ts',
)
const P_TRIM_VUE = path.join(
  ROOT, 'audit-platform', 'frontend', 'src', 'views', 'ProcedureTrimming.vue',
)
const P_ROLE_MAP = path.join(ROOT, 'backend', 'app', 'services', 'assignment_service.py')

const MODULE_SRC = stripComments(read(P_MODULE))

describe('helper 自检（防判据空转）', () => {
  it('stripComments 剥注释保留字符串字面量', () => {
    const s = stripComments(`const a = 'partner' // 注释里写 ROLE_PRIORITY\n/* auditor: 1 */`)
    expect(s).toContain("'partner'")
    expect(s).not.toContain('注释里写')
    expect(s).not.toContain('auditor: 1')
  })

  it('扫描面非空：剥注释后的模块源码仍含常量声明（否则下面「不含 X」全空转）', () => {
    expect(MODULE_SRC).toContain('ROLE_SENIORITY')
    expect(MODULE_SRC).toContain('roleSeniority')
    expect(MODULE_SRC.length, '剥注释后源码过短，疑似 helper 把代码也剥了').toBeGreaterThan(400)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 1：刻度与 RISK_MIN_SENIORITY 咬合（这是「资历」有意义的前提）
// ═══════════════════════════════════════════════════════════════════════════

describe('判据 1: 资历刻度与风险门槛咬合', () => {
  it('合伙人/经理档可承担高风险，执行档不可（高风险不得由审计员独立执行）', () => {
    expect(roleSeniority('partner')).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.H)
    expect(roleSeniority('signing_partner')).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.H)
    expect(roleSeniority('eqcr')).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.H)
    expect(roleSeniority('manager')).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.H)
    expect(roleSeniority('qc')).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.H)
    // 🔴 审计员不得独立承担高风险底稿
    expect(roleSeniority('auditor')).toBeLessThan(RISK_MIN_SENIORITY.H)
  })

  it('执行档可承担中风险（中风险实质性测试是审计员主战场）', () => {
    expect(roleSeniority('auditor')).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.M)
  })

  it('助理档只能承担低风险与未评估（不得中风险）', () => {
    expect(roleSeniority('assistant')).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.L)
    expect(roleSeniority('assistant')).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.none)
    expect(roleSeniority('assistant')).toBeLessThan(RISK_MIN_SENIORITY.M)
    expect(roleSeniority('intern')).toBeLessThan(RISK_MIN_SENIORITY.M)
  })

  it('资历严格单调：合伙人 > 经理 > 执行 > 助理', () => {
    expect(roleSeniority('partner')).toBeGreaterThan(roleSeniority('manager'))
    expect(roleSeniority('manager')).toBeGreaterThan(roleSeniority('auditor'))
    expect(roleSeniority('auditor')).toBeGreaterThan(roleSeniority('assistant'))
  })

  it('合伙人档三角色同值（门槛最高只到 3，再细分无审计含义、只会让复核人抖动）', () => {
    expect(roleSeniority('partner')).toBe(roleSeniority('signing_partner'))
    expect(roleSeniority('partner')).toBe(roleSeniority('eqcr'))
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 2：🔴 不得与 ROLE_PRIORITY 同序（本文件的核心红线）
// ═══════════════════════════════════════════════════════════════════════════

describe('判据 2: 不得与 ProcedureTrimming.vue 的 ROLE_PRIORITY 同序', () => {
  /** 从裁剪页源码里抽出真实的 `ROLE_PRIORITY`（不写死一份副本，抽不到即红）。 */
  function extractRolePriority(): Record<string, number> {
    const src = stripComments(read(P_TRIM_VUE))
    const at = src.indexOf('const ROLE_PRIORITY')
    expect(at, 'ProcedureTrimming.vue 中未找到 ROLE_PRIORITY（守卫锚点失效）')
      .toBeGreaterThanOrEqual(0)
    const open = src.indexOf('{', at)
    const close = src.indexOf('}', open)
    expect(close, 'ROLE_PRIORITY 对象字面量未闭合').toBeGreaterThan(open)
    const body = src.slice(open + 1, close)
    const out: Record<string, number> = {}
    for (const m of body.matchAll(/([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(-?\d+)/g)) {
      out[m[1]] = Number(m[2])
    }
    return out
  }

  const PRIORITY = extractRolePriority()

  it('扫描面非空：真的抽到了 ROLE_PRIORITY 的多个键（否则下面的反向断言空转）', () => {
    expect(Object.keys(PRIORITY).length, '抽到的 ROLE_PRIORITY 键太少').toBeGreaterThanOrEqual(5)
    expect(PRIORITY).toHaveProperty('auditor')
    expect(PRIORITY).toHaveProperty('signing_partner')
  })

  /**
   * 🔴 本条记录一个**实证纠正**，并把它钉死。
   *
   * 流传的说法是「`ROLE_PRIORITY` 数值越小越靠前，语义方向与资历相反，挪用会让
   * 审计员被判为资历最高」。**源码不支持这个说法**：其已登记 6 键从 `auditor`(1)
   * 升到 `signing_partner`(6)，与资历**同向**，严格反序对数量为 0。
   *
   * 因此本条**不能**断言「存在反序对」（那会把一条假前提写成守卫，且必然假红）。
   * 改为双向锁死真实事实：①已登记键上两者同向（若哪天有人把 ROLE_PRIORITY 改成
   * 倒序，本条会打红并提醒重新评估本模块文档）②真正的反序在**兜底值**上，那是
   * 挪用的实际危害所在。
   */
  it('已登记键上两者同向（纠正「方向相反」的说法，若 ROLE_PRIORITY 改序则打红）', () => {
    const shared = Object.keys(PRIORITY).filter((r) => isRegisteredRole(r))
    expect(shared.length, '共有键太少，判据空转').toBeGreaterThanOrEqual(5)

    let inverted = 0
    let concordant = 0
    for (const a of shared) {
      for (const b of shared) {
        if (a === b) continue
        if (PRIORITY[a] < PRIORITY[b] && roleSeniority(a) > roleSeniority(b)) inverted += 1
        if (PRIORITY[a] < PRIORITY[b] && roleSeniority(a) < roleSeniority(b)) concordant += 1
      }
    }
    expect(concordant, '已登记键上无同向对，与实证不符').toBeGreaterThan(0)
    expect(
      inverted,
      '出现严格反序对 ⇒ ROLE_PRIORITY 已被改序，delegationSeniority.ts 的模块文档需重新评估',
    ).toBe(0)
  })

  it('🔴 真正的反序在兜底值：ROLE_PRIORITY 未登记=90（最高），本模块未登记=最低', () => {
    // 视图侧真实写法 `ROLE_PRIORITY[a.role || ''] ?? 90` —— 从源码里抽出那个兜底数字，
    // 不写死（改了要打红）。
    const src = stripComments(read(P_TRIM_VUE))
    const m = src.match(/ROLE_PRIORITY\[[^\]]*\]\s*\?\?\s*(\d+)/)
    expect(m, '未在裁剪页找到 ROLE_PRIORITY 的 ?? 兜底写法（锚点失效）').not.toBeNull()
    const priorityFallback = Number(m![1])

    const registeredMax = Math.max(...Object.values(PRIORITY))
    // 挪用的实际危害：未登记 role 在 ROLE_PRIORITY 口径下排在**所有**已登记角色之后/之上
    expect(
      priorityFallback,
      'ROLE_PRIORITY 兜底值不再高于全部已登记角色，本条判据的前提需重查',
    ).toBeGreaterThan(registeredMax)

    // 本模块方向相反：未登记 = 最低登记档，绝不换来承担高风险的资格
    const seniorityValues = Object.values(ROLE_SENIORITY)
    expect(SENIORITY_UNREGISTERED).toBe(Math.min(...seniorityValues))
    expect(roleSeniority('这个角色不存在')).toBe(SENIORITY_UNREGISTERED)
    expect(
      roleSeniority('这个角色不存在'),
      '未登记 role 达到了高风险门槛 ⇒ 不认识的角色换来了承担高风险底稿的资格',
    ).toBeLessThan(RISK_MIN_SENIORITY.H)
  })

  it('挪用会让项目经理接不到高风险底稿（中间档刻度错位，不报错只排错人）', () => {
    // manager 在 ROLE_PRIORITY 里是 2 < H 门槛 3；本模块给 3 恰好够
    expect(PRIORITY.manager).toBeLessThan(RISK_MIN_SENIORITY.H)
    expect(roleSeniority('manager')).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.H)

    const target = {
      wpIndexId: 'w1', wpCode: 'D1', cycle: 'D', risk: 'H' as const, rowCount: 4,
    }
    const correct = suggestDelegation({
      members: [{ staffId: 'm', name: '经理', seniority: roleSeniority('manager'), currentLoad: 0 }],
      targets: [target],
      riskDimensionAvailable: true,
    })
    expect(correct.assignments, '经理档应能承担高风险底稿').toHaveLength(1)

    const misused = suggestDelegation({
      members: [{ staffId: 'm', name: '经理', seniority: PRIORITY.manager, currentLoad: 0 }],
      targets: [target],
      riskDimensionAvailable: true,
    })
    expect(
      misused.assignments,
      '按 ROLE_PRIORITY 当资历后经理仍能接高风险 ⇒ 该场景无法证伪，判据无承重',
    ).toHaveLength(0)
    expect(misused.unassignedTargets).toHaveLength(1)
  })

  it('两字典不可互换：以 ROLE_PRIORITY 当资历会让高风险落到审计员', () => {
    const target = {
      wpIndexId: 'w1', wpCode: 'D1', cycle: 'D', risk: 'H' as const, rowCount: 10,
    }
    const members: DelegationMember[] = [
      { staffId: 'a', name: '审计员甲', seniority: roleSeniority('auditor'), currentLoad: 0 },
      { staffId: 'p', name: '合伙人乙', seniority: roleSeniority('signing_partner'), currentLoad: 0 },
    ]
    const good = suggestDelegation({ members, targets: [target], riskDimensionAvailable: true })
    expect(good.assignments).toHaveLength(1)
    expect(good.assignments[0].assigneeStaffId, '高风险底稿未落到资深者').toBe('p')

    // 替身：把 ROLE_PRIORITY 直接当资历用（这正是挪用会产生的形态）
    const misused: DelegationMember[] = [
      { staffId: 'a', name: '审计员甲', seniority: PRIORITY.auditor, currentLoad: 0 },
      { staffId: 'p', name: '合伙人乙', seniority: PRIORITY.signing_partner, currentLoad: 0 },
    ]
    const bad = suggestDelegation({ members: misused, targets: [target], riskDimensionAvailable: true })
    // 挪用后 auditor(1) < H 门槛(3) 会被排除，signing_partner(6) 仍合格 ⇒ 表面结果相同，
    // 但只要有人「按小=重要取反」就会翻转 —— 该形态必须显形：
    const inverted: DelegationMember[] = [
      { staffId: 'a', name: '审计员甲', seniority: 7 - PRIORITY.auditor, currentLoad: 0 },
      { staffId: 'p', name: '合伙人乙', seniority: 7 - PRIORITY.signing_partner, currentLoad: 0 },
    ]
    const flipped = suggestDelegation({ members: inverted, targets: [target], riskDimensionAvailable: true })
    expect(bad.assignments.length + flipped.assignments.length, '替身构造失效').toBeGreaterThan(0)
    if (flipped.assignments.length > 0) {
      expect(
        flipped.assignments[0].assigneeStaffId,
        '取反挪用后高风险底稿仍落到资深者 ⇒ 该场景无法证伪，判据无承重',
      ).toBe('a')
    }
  })

  it('源码级：本模块不引用 ROLE_PRIORITY（剥注释后）', () => {
    expect(
      MODULE_SRC.includes('ROLE_PRIORITY'),
      'delegationSeniority.ts 在代码（非注释）中引用了 ROLE_PRIORITY',
    ).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 3：中文别名与后端 ROLE_MAP 交叉锁死
// ═══════════════════════════════════════════════════════════════════════════

describe('判据 3: 中文角色别名与后端 ROLE_MAP 交叉锁死', () => {
  /** 从后端 py 源码抽 `ROLE_MAP` 的键（不写死副本，一侧新增另一侧未跟进即红）。 */
  function extractBackendRoleMapKeys(): string[] {
    const src = read(P_ROLE_MAP)
    const at = src.indexOf('ROLE_MAP: dict[str, tuple[ProjectUserRole, PermissionLevel]] = {')
    expect(at, 'assignment_service.py 中未找到 ROLE_MAP 声明（守卫锚点失效）')
      .toBeGreaterThanOrEqual(0)
    const open = src.indexOf('{', at)
    let depth = 0
    let end = -1
    for (let i = open; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1
      else if (src[i] === '}') {
        depth -= 1
        if (depth === 0) { end = i; break }
      }
    }
    expect(end, 'ROLE_MAP 字典未闭合').toBeGreaterThan(open)
    const body = src.slice(open + 1, end)
    return [...body.matchAll(/"([^"]+)"\s*:/g)].map((m) => m[1])
  }

  const BACKEND_KEYS = extractBackendRoleMapKeys()

  it('扫描面非空：抽到后端 ROLE_MAP 的全部键（含中文别名）', () => {
    expect(BACKEND_KEYS.length, '抽到的后端 ROLE_MAP 键太少').toBeGreaterThanOrEqual(12)
    expect(BACKEND_KEYS).toContain('合伙人')
    expect(BACKEND_KEYS).toContain('审计员')
  })

  it('🔴 后端 ROLE_MAP 的每个键都必须在本模块登记（漏一个 ⇒ 该 role 静默落助理档）', () => {
    const missing = BACKEND_KEYS.filter((k) => !isRegisteredRole(k))
    expect(missing, `后端 ROLE_MAP 有键未在 ROLE_SENIORITY 登记: ${missing.join('、')}`).toEqual([])
  })

  it('中英同义键资历相等（中文别名不得比英文键低一档）', () => {
    const pairs: [string, string][] = [
      ['partner', '合伙人'],
      ['signing_partner', '签字合伙人'],
      ['manager', '项目经理'],
      ['qc', '质控'],
      ['auditor', '审计员'],
      ['assistant', '助理'],
      ['eqcr', '独立复核合伙人'],
    ]
    for (const [en, zh] of pairs) {
      expect(roleSeniority(zh), `${zh} 与 ${en} 资历不等`).toBe(roleSeniority(en))
    }
  })

  it('中文别名真的走到对应档（不是靠兜底档凑巧相等）', () => {
    // 助理档兜底值恰为 1，若 `助理` 漏映射也会得到 1 ⇒ 用非助理档的中文键做决定性判据
    expect(roleSeniority('合伙人')).toBeGreaterThan(SENIORITY_UNREGISTERED)
    expect(roleSeniority('项目经理')).toBeGreaterThan(SENIORITY_UNREGISTERED)
    expect(roleSeniority('审计员')).toBeGreaterThan(SENIORITY_UNREGISTERED)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 4：未知 role 不得得到高资历
// ═══════════════════════════════════════════════════════════════════════════

describe('判据 4: 未登记 role 一律最低档', () => {
  it('空 / null / undefined / 空白一律兜底档', () => {
    expect(roleSeniority('')).toBe(SENIORITY_UNREGISTERED)
    expect(roleSeniority(null)).toBe(SENIORITY_UNREGISTERED)
    expect(roleSeniority(undefined)).toBe(SENIORITY_UNREGISTERED)
    expect(roleSeniority('   ')).toBe(SENIORITY_UNREGISTERED)
  })

  it('兜底档 = 最低登记档，且低于中风险门槛', () => {
    const registered = Object.values(ROLE_SENIORITY)
    expect(SENIORITY_UNREGISTERED).toBe(Math.min(...registered))
    expect(SENIORITY_UNREGISTERED).toBeLessThan(RISK_MIN_SENIORITY.M)
  })

  it('兜底档不低于低风险与未评估门槛（否则降级模式下一条建议都产不出）', () => {
    expect(SENIORITY_UNREGISTERED).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.L)
    expect(SENIORITY_UNREGISTERED).toBeGreaterThanOrEqual(RISK_MIN_SENIORITY.none)
  })

  it('PBT: 任意未登记字符串都不得达到高风险门槛', () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 24 }), (s) => {
        if (isRegisteredRole(s)) return true
        return roleSeniority(s) < RISK_MIN_SENIORITY.H
      }),
      { numRuns: 200 },
    )
  })

  it('大小写与空白归一（后端 role 拼写波动不该改变资历）', () => {
    expect(roleSeniority('PARTNER')).toBe(roleSeniority('partner'))
    expect(roleSeniority('  Manager  ')).toBe(roleSeniority('manager'))
    expect(roleSeniority('AuDiToR')).toBe(roleSeniority('auditor'))
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 5：纯函数 / 零依赖 / 标签齐备
// ═══════════════════════════════════════════════════════════════════════════

describe('判据 5: 纯函数、零 Vue 依赖、标签齐备', () => {
  it('无 vue / element-plus / http import（源码级；行为上不可区分故用源码判据）', () => {
    expect(/from\s+['"]vue['"]/.test(MODULE_SRC), '引入了 vue').toBe(false)
    expect(/from\s+['"]element-plus['"]/.test(MODULE_SRC), '引入了 element-plus').toBe(false)
    expect(/from\s+['"].*http['"]/.test(MODULE_SRC), '引入了 http').toBe(false)
    expect(/\bimport\s+/.test(MODULE_SRC), '本模块应零 import（纯常量+纯函数）').toBe(false)
  })

  it('ROLE_SENIORITY 被冻结（防运行时被就地改档）', () => {
    expect(Object.isFrozen(ROLE_SENIORITY)).toBe(true)
    expect(Object.isFrozen(SENIORITY_LABEL)).toBe(true)
  })

  it('每个出现过的资历值都有中文档位标签', () => {
    for (const v of new Set(Object.values(ROLE_SENIORITY))) {
      expect(SENIORITY_LABEL[v], `资历 ${v} 缺中文标签`).toBeTruthy()
    }
  })

  it('seniorityLabel 对未登记档位不抛且不返回空串', () => {
    expect(seniorityLabel(99)).toContain('99')
    expect(seniorityLabel(0)).not.toBe('')
  })

  it('幂等：同一入参多次调用结果相同（无内部可变状态）', () => {
    for (const r of ['partner', '审计员', 'zzz', '']) {
      expect(roleSeniority(r)).toBe(roleSeniority(r))
    }
  })
})
