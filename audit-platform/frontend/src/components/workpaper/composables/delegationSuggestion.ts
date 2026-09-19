/**
 * 委派建议分配算法（纯函数，零 Vue 依赖、零 IO）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 17
 * 守卫: `__tests__/delegationSuggestion.spec.ts`
 * 消费方: Task 18 的建议分配表组件（逐行展示 `rationale` 供审计师判断是否接受）
 *
 * ## 它解决的审计问题
 *
 * 改造前的委派是「一次一个循环给一个人」：现场经理在下拉里挑名字，看不到那个人
 * 已经背了多少任务，也没有任何机制保证高风险底稿落到资历够的人手上。结果是两类
 * 系统性偏差 —— 熟悉的人被反复指派（负载失衡），以及高风险领域由资历不足的助理
 * 独立执行（复核环节才发现，返工成本最高）。
 *
 * 本模块把「风险等级 → 资历门槛」与「加权负载 → 均衡」两条判据写成可复算的纯函数，
 * 并要求每条建议自带 `rationale`（含判据数值）。**它产出的是建议不是决定** ——
 * 审计师逐行可改可删，最终写入仍走既有 `ProcedureDelegationService` 的
 * preview → apply 两阶段（SOD 由后端 `assert_sod_distinct` 在两侧逐 task 双查，
 * 本模块的 SOD 约束是第一道而非唯一一道）。
 *
 * ## 算法（与 design 的四步一致）
 *
 * 1. 目标按风险等级降序（同级按行数降序、再按底稿编号升序，保证结果可复算）
 * 2. 逐张底稿选执行人：**资历满足该风险等级要求** 且 **当前加权负载最小**
 * 3. 复核人取「资历不低于执行人 且 非执行人本人」中负载最小者
 * 4. 把本张底稿的权重累加到执行人负载上，再处理下一张
 *
 * 权重 `weight = 1 + riskCoefficient + rowCount / 20`：基数 1 代表「一张底稿本身
 * 就是一份工作」，风险系数反映高风险底稿的工作量与判断强度，行数项反映数据量。
 *
 * ## 五条极易被后续会话「优化」掉的约束
 *
 * 五条都配了守卫与变异检验。它们的共同特征是：改掉之后功能表面上仍然工作，
 * 只是建议悄悄变得不可信 —— 而「建议看起来仍然合理」正是最危险的失效形态。
 *
 * 1. **`reviewerStaffId !== assigneeStaffId` 是硬约束（SOD，不相容职务分离）。**
 *    任何情况下不得违反：宁可 `reviewerStaffId` 为 `null` 并记 warning，也不能
 *    让执行人复核自己的工作 —— 那样的复核痕迹在质控与 EQCR 眼里等于没有复核，
 *    而底稿上却显示「已复核」，比明摆着缺复核人更坏。
 * 2. **负载未知是 `null` 不是 `0`，且不得按 0 参与均衡。** `0` 会被算法读成
 *    「这个人很空闲」，于是所有工作都堆给数据缺失的那个人 —— 恰好是最不该被
 *    堆工作的人（我们连他现在背了多少都不知道）。故负载未知的成员降为**后备档**：
 *    只有在没有任何负载已知的合格成员时才启用，且必须进 `warnings` 与
 *    `unknownLoadStaffIds` 如实暴露。
 * 3. **`riskCoefficient` 的 `null`（0.3）大于 `L`（0.2）不是笔误。** 「未评估」
 *    的不确定性高于「已评估为低风险」：前者可能是任何风险等级，后者是审计师
 *    已作出的判断。把 `null` 调到 0.2 或 0 会让未填风险矩阵的项目在负载上被
 *    系统性低估，进而把未评估领域堆给同一个人。
 * 4. **资历门槛是绝对值不是团队相对值。** 若按「团队里最高资历者即可承担 H 风险」
 *    推导门槛，那么任何团队都必然有人「够资历做高风险底稿」—— 而「本项目组
 *    资历不足以覆盖高风险领域」恰恰是必须暴露给项目负责人的事实（需要加派资深
 *    人员或升级复核层级），不能被算法自动抹平。故门槛取平台默认常量
 *    `RISK_MIN_SENIORITY`，且无人满足时**不硬塞**（该底稿进 `unassignedTargets`
 *    并记 warning）—— 把高风险底稿分给资历不足的人比不分配更坏，后者至少不会
 *    让复核环节误以为已有适当人员覆盖。
 * 5. **`degraded` 与「未做风险匹配」严格等价。** `riskDimensionAvailable === false`
 *    （B50 认定层次风险矩阵未填）时必须 `degraded = true` 且 warnings 明确写出
 *    「未做风险匹配」，并且**忽略入参里的风险值**（B50 未填时那些值不可信，
 *    拿它做匹配等于假装做了联动）。守卫按双向断言钉死这三者等价，防止出现
 *    「标注说做了风险匹配、实际没做」或反之。
 *
 * ## 两处与 tasks.md 字面描述的自洽性偏离（有意，已在守卫中锁死）
 *
 * - **`loadAfter` 只包含负载已知的成员**，负载未知者的分配增量在
 *   `loadIncrement` 里单列。理由：若给未知基线凑一个 0 再加增量，产出的
 *   「分配后负载 1.50」是个编造的绝对值，UI 无从区分它和真实的 1.50。
 *   「总增量等于所分配权重之和」这一不变式因此落在 `loadIncrement` 上
 *   （它覆盖全部成员，等式精确成立）。
 * - **复核工作量不计入 `loadAfter`**，只以 `REVIEW_ROTATION_UNIT` 计入复核人
 *   排序键做轮转。理由：`loadAfter` 要与后端下发的 `active_task_count`
 *   （执行人非终态任务数）同口径可比，混入复核轮转量会让 UI 的「分配后负载」
 *   失去与后端数值的可比性；而复核工作量确实存在，故用于排序避免「一个人
 *   复核全部底稿」。
 */

// ═══════════════════════════════════════════════════════════════════════════
// 类型
// ═══════════════════════════════════════════════════════════════════════════

/** 重大错报风险等级；`null` = B50 未对该科目作出评估。 */
export type RiskLevel = 'H' | 'M' | 'L' | null

/** 风险等级的字典键形态（`null` 在 Record 里写成 `'none'`）。 */
export type RiskKey = 'H' | 'M' | 'L' | 'none'

export interface DelegationMember {
  staffId: string
  name: string
  /** 资历等级，数值越大越资深 */
  seniority: number
  /** 当前非终态任务数；`null` = 负载未知（绝不可当 0 处理） */
  currentLoad: number | null
}

export interface DelegationTarget {
  wpIndexId: string
  wpCode: string
  cycle: string
  risk: RiskLevel
  rowCount: number
}

export interface DelegationAssignment {
  wpIndexId: string
  wpCode: string
  cycle: string
  risk: RiskLevel
  assigneeStaffId: string
  assigneeName: string
  /** 无合格复核人时为 `null`（SOD 硬约束优先于「凑一个复核人」） */
  reviewerStaffId: string | null
  reviewerName: string | null
  /** 本张底稿的加权工作量 */
  weight: number
  /** 为何这样分（含判据数值，供建议分配表逐行展示） */
  rationale: string
}

/** 未能分配的目标及原因（H 风险无人覆盖等）。 */
export interface UnassignedTarget {
  wpIndexId: string
  wpCode: string
  cycle: string
  risk: RiskLevel
  reason: string
}

export interface DelegationSuggestionInput {
  members: DelegationMember[]
  targets: DelegationTarget[]
  /**
   * B50 认定层次风险矩阵是否可用。
   *
   * `false` 时退化为纯负载均衡：忽略 `targets[].risk`、资历门槛按最低档，
   * 并置 `degraded = true` + warnings 含「未做风险匹配」。
   */
  riskDimensionAvailable: boolean
  /** 可选：覆盖平台默认资历门槛（项目组资历口径不同时使用） */
  minSeniorityByRisk?: Partial<Record<RiskKey, number>>
}

export interface DelegationSuggestionResult {
  assignments: DelegationAssignment[]
  /** 分配后加权负载；**只含负载已知的成员**（见模块文档「偏离」一节） */
  loadAfter: Record<string, number>
  /** 本次分配增量；覆盖全部被分配到工作的成员，等式判据落在此处 */
  loadIncrement: Record<string, number>
  /** 负载未知的成员（降为后备档、并如实暴露） */
  unknownLoadStaffIds: string[]
  /** 未能分配的目标（不硬塞） */
  unassignedTargets: UnassignedTarget[]
  /** 与「未做风险匹配」严格等价 */
  degraded: boolean
  warnings: string[]
}

// ═══════════════════════════════════════════════════════════════════════════
// 常量
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 风险系数（权重公式的第二项）。
 *
 * 🔴 `none`（未评估）= 0.3 高于 `L`（已评估为低风险）= 0.2，是有意为之：
 * 「未评估」的不确定性高于「已评估为低」。详见模块文档约束 3。
 */
export const RISK_COEFFICIENT: Readonly<Record<RiskKey, number>> = Object.freeze({
  H: 1.0,
  M: 0.5,
  L: 0.2,
  none: 0.3,
})

/**
 * 各风险等级要求的最低资历（平台默认值，可由入参覆盖）。
 *
 * 🔴 必须是绝对门槛，不得由团队最高资历反推 —— 否则「本项目组资历不足以覆盖
 * 高风险领域」这一必须暴露的事实会被算法自动抹平。详见模块文档约束 4。
 */
export const RISK_MIN_SENIORITY: Readonly<Record<RiskKey, number>> = Object.freeze({
  H: 3,
  M: 2,
  L: 1,
  none: 1,
})

/** 风险等级降序排序用的秩（越大越先分配）。 */
const RISK_RANK: Readonly<Record<RiskKey, number>> = Object.freeze({
  H: 3,
  M: 2,
  none: 1,
  L: 0,
})

/** 行数项的除数（`rowCount / 20`）。 */
export const ROW_COUNT_DIVISOR = 20

/**
 * 复核轮转单位：仅计入复核人排序键，**不计入 `loadAfter`**。
 * 详见模块文档「偏离」一节。
 */
export const REVIEW_ROTATION_UNIT = 0.5

/** warnings 里「未做风险匹配」的固定字样（守卫按此字样断言，勿改）。 */
export const WARNING_NO_RISK_MATCH =
  '未做风险匹配：本项目 B50 认定层次风险评估不可用，'
  + '本次建议仅按加权负载均衡分配，未按风险等级匹配执行人资历。'

// ═══════════════════════════════════════════════════════════════════════════
// 小工具（全部纯函数）
// ═══════════════════════════════════════════════════════════════════════════

function riskKeyOf(risk: RiskLevel): RiskKey {
  return risk === 'H' || risk === 'M' || risk === 'L' ? risk : 'none'
}

function riskLabel(risk: RiskLevel): string {
  if (risk === 'H') return '高'
  if (risk === 'M') return '中'
  if (risk === 'L') return '低'
  return '未评估'
}

/** 数值归一：非有限值一律回退到 `fallback`（不让 NaN 污染排序与合计）。 */
function toFiniteNumber(value: unknown, fallback: number): number {
  const num = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(num) ? num : fallback
}

/** 保留 4 位小数，抑制二进制浮点噪声（不改变数量级判断）。 */
function round4(value: number): number {
  return Math.round(value * 10000) / 10000
}

function fmt(value: number): string {
  return value.toFixed(2)
}

/** 计算单张底稿的加权工作量。 */
export function computeTargetWeight(risk: RiskLevel, rowCount: number): number {
  const coefficient = RISK_COEFFICIENT[riskKeyOf(risk)]
  const rows = Math.max(0, toFiniteNumber(rowCount, 0))
  return round4(1 + coefficient + rows / ROW_COUNT_DIVISOR)
}

interface MemberState {
  staffId: string
  name: string
  seniority: number
  /** `null` = 负载未知 */
  baseLoad: number | null
  /** 已累加的执行权重 */
  assignedWeight: number
  /** 本次已承担的复核次数（仅用于复核人轮转） */
  reviewCount: number
}

/** 归一后的目标（内部形态；`declaredRisk` 保留入参声明值供 UI 如实回显）。 */
interface TargetState {
  wpIndexId: string
  wpCode: string
  cycle: string
  declaredRisk: RiskLevel
  risk: RiskLevel
  rowCount: number
}

/** 执行/比较用的加权负载：负载未知时只反映本次增量（不假造 0 作基线）。 */
function comparableLoad(m: MemberState): number {
  return round4((m.baseLoad ?? 0) + m.assignedWeight)
}

/** 负载已知者优先（档 0），未知者为后备档（档 1）。 */
function loadTier(m: MemberState): number {
  return m.baseLoad === null ? 1 : 0
}

// ═══════════════════════════════════════════════════════════════════════════
// 主函数
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 产出建议分配表。
 *
 * @param input.members 项目组成员（`currentLoad` 为 `null` 表示负载未知）
 * @param input.targets 待分配底稿（一张底稿一条）
 * @param input.riskDimensionAvailable B50 风险维度是否可用；`false` 时退化为纯负载均衡
 * @param input.minSeniorityByRisk 可选，覆盖平台默认资历门槛
 */
export function suggestDelegation(
  input: DelegationSuggestionInput,
): DelegationSuggestionResult {
  const warnings: string[] = []
  const degraded = input?.riskDimensionAvailable !== true
  if (degraded) warnings.push(WARNING_NO_RISK_MATCH)

  const thresholds: Record<RiskKey, number> = {
    H: toFiniteNumber(input?.minSeniorityByRisk?.H, RISK_MIN_SENIORITY.H),
    M: toFiniteNumber(input?.minSeniorityByRisk?.M, RISK_MIN_SENIORITY.M),
    L: toFiniteNumber(input?.minSeniorityByRisk?.L, RISK_MIN_SENIORITY.L),
    none: toFiniteNumber(input?.minSeniorityByRisk?.none, RISK_MIN_SENIORITY.none),
  }

  // ── 成员归一（按 staffId 去重，保留首次出现）──────────────────────────────
  const rawMembers = Array.isArray(input?.members) ? input.members : []
  const members: MemberState[] = []
  const seen = new Set<string>()
  let duplicateCount = 0
  for (const m of rawMembers) {
    if (!m) continue
    const staffId = String(m.staffId ?? '').trim()
    if (!staffId) continue
    if (seen.has(staffId)) {
      duplicateCount += 1
      continue
    }
    seen.add(staffId)
    const rawLoad = m.currentLoad
    const baseLoad = typeof rawLoad === 'number' && Number.isFinite(rawLoad)
      ? Math.max(0, rawLoad)
      : null
    members.push({
      staffId,
      name: String(m.name ?? staffId),
      seniority: toFiniteNumber(m.seniority, 0),
      baseLoad,
      assignedWeight: 0,
      reviewCount: 0,
    })
  }
  if (duplicateCount > 0) {
    warnings.push(`成员清单中有 ${duplicateCount} 条重复 staffId，已按首次出现保留。`)
  }

  const unknownLoadStaffIds = members.filter((m) => m.baseLoad === null).map((m) => m.staffId)
  if (unknownLoadStaffIds.length > 0) {
    const names = members
      .filter((m) => m.baseLoad === null)
      .map((m) => m.name)
      .join('、')
    warnings.push(
      `以下成员当前负载未知（后端未下发或取数失败）：${names}。`
      + '负载未知不等于负载为 0，故这些成员仅在没有负载已知的合格成员时才被建议，'
      + '请先确认其在手任务量后再采用相关建议。',
    )
  }

  const byId = new Map<string, MemberState>()
  for (const m of members) byId.set(m.staffId, m)

  // ── 目标归一（按 wpIndexId 去重，保留首次出现）────────────────────────────
  //
  // 🔴 为什么必须去重（与 members 侧对称 —— 两侧口径不对称本身就是缺陷）：
  //    同一张底稿在入参里出现两次时，会产出两条针对同一底稿的建议，进而
  //    ① 委派对同一 `wp_index_id` 重复下发（本模块产出的 `wpIndexId` 直接进
  //       selector 的 `wp_index_ids`，后端按底稿粒度建 task，重复即重复分配）；
  //    ② Task 18 的建议分配表以 `wpIndexId` 作行键（`row-key="wpIndexId"`），
  //       重复键会让「改执行人 / 改复核人 / 移除行」这类编辑串行到错误的行上
  //       （同 key 复用节点，用户改 A 行看到 B 行变）。
  //
  // 🔴 去重必须发生在**排序之前**：排序键含 `wpIndexId`，先排后去重会让
  //    「首次出现胜出」的语义随排序结果漂移（同一份入参在不同风险/行数组合下
  //    留下的那一条会变），产出不可复算。
  //
  // 🔴 去重键必须**等于对外产出的 `wpIndexId` 值**（此处即 `String(t.wpIndexId)`，
  //    与既有归一逐字一致、不额外 trim）：键与产出值一旦不同，两条不同键的目标
  //    仍可能产出同一个 `wpIndexId`，行键碰撞与重复下发照旧发生。
  const rawTargets = Array.isArray(input?.targets) ? input.targets : []
  const targets: TargetState[] = []
  const seenTargets = new Set<string>()
  let duplicateTargetCount = 0
  for (const t of rawTargets) {
    if (!t) continue
    if (String(t.wpIndexId ?? '').trim() === '') continue
    const wpIndexId = String(t.wpIndexId)
    if (seenTargets.has(wpIndexId)) {
      duplicateTargetCount += 1
      continue
    }
    seenTargets.add(wpIndexId)
    // 🔴 降级时忽略入参风险值：B50 未填时那些值不可信，拿它做匹配等于假装做了联动。
    const effectiveRisk: RiskLevel = degraded ? null : (t.risk ?? null)
    targets.push({
      wpIndexId,
      wpCode: String(t.wpCode ?? ''),
      cycle: String(t.cycle ?? ''),
      declaredRisk: (t.risk ?? null) as RiskLevel,
      risk: effectiveRisk,
      rowCount: Math.max(0, toFiniteNumber(t.rowCount, 0)),
    })
  }
  if (duplicateTargetCount > 0) {
    warnings.push(
      `待分配底稿清单中有 ${duplicateTargetCount} 条重复 wpIndexId，已按首次出现保留。`,
    )
  }

  targets.sort((a, b) => {
    const rankDiff = RISK_RANK[riskKeyOf(b.risk)] - RISK_RANK[riskKeyOf(a.risk)]
    if (rankDiff !== 0) return rankDiff
    if (b.rowCount !== a.rowCount) return b.rowCount - a.rowCount
    if (a.wpCode !== b.wpCode) return a.wpCode < b.wpCode ? -1 : 1
    return a.wpIndexId < b.wpIndexId ? -1 : a.wpIndexId > b.wpIndexId ? 1 : 0
  })

  const assignments: DelegationAssignment[] = []
  const unassignedTargets: UnassignedTarget[] = []

  if (members.length === 0) {
    if (targets.length > 0) {
      warnings.push(
        `项目组成员清单为空，无法产生任何建议分配（待分配底稿 ${targets.length} 张）。`
        + '请先在项目成员管理中加入执行人与复核人后重新生成建议。',
      )
      for (const t of targets) {
        unassignedTargets.push({
          wpIndexId: t.wpIndexId,
          wpCode: t.wpCode,
          cycle: t.cycle,
          risk: t.declaredRisk,
          reason: '项目组成员清单为空，无可分配人员。',
        })
      }
    } else {
      warnings.push('项目组成员清单为空。')
    }
    return {
      assignments,
      loadAfter: {},
      loadIncrement: {},
      unknownLoadStaffIds,
      unassignedTargets,
      degraded,
      warnings,
    }
  }

  if (members.length === 1) {
    warnings.push(
      `项目组仅 1 名成员（${members[0].name}），无法在满足不相容职务分离（执行人 ≠ 复核人）`
      + '的前提下产生复核人，相关底稿的复核人留空并需另行指派。',
    )
  }

  // ── 逐张分配 ──────────────────────────────────────────────────────────────
  for (const t of targets) {
    const key = riskKeyOf(t.risk)
    const required = thresholds[key]
    const weight = computeTargetWeight(t.risk, t.rowCount)

    const qualified = members.filter((m) => m.seniority >= required)
    if (qualified.length === 0) {
      // 🔴 不硬塞：把高风险底稿分给资历不足的人比不分配更坏。
      const reason =
        `无成员资历满足${riskLabel(t.risk)}风险要求（要求资历 ≥ ${required}，`
        + `项目组最高资历 ${Math.max(...members.map((m) => m.seniority))}）。`
      unassignedTargets.push({
        wpIndexId: t.wpIndexId,
        wpCode: t.wpCode,
        cycle: t.cycle,
        risk: t.declaredRisk,
        reason,
      })
      warnings.push(
        `底稿 ${t.wpCode || t.wpIndexId} 未分配：${reason}`
        + '请加派资历满足要求的人员，或经项目负责人评估后调整该底稿的风险等级与复核层级。',
      )
      continue
    }

    const assignee = pickAssignee(qualified)
    const reviewer = pickReviewer(members, assignee)

    const loadBefore = comparableLoad(assignee)
    assignee.assignedWeight = round4(assignee.assignedWeight + weight)
    const loadAfterThis = comparableLoad(assignee)
    if (reviewer) reviewer.reviewCount += 1

    assignments.push({
      wpIndexId: t.wpIndexId,
      wpCode: t.wpCode,
      cycle: t.cycle,
      risk: t.declaredRisk,
      assigneeStaffId: assignee.staffId,
      assigneeName: assignee.name,
      reviewerStaffId: reviewer ? reviewer.staffId : null,
      reviewerName: reviewer ? reviewer.name : null,
      weight,
      rationale: buildRationale({
        degraded,
        target: t,
        required,
        weight,
        assignee,
        loadBefore,
        loadAfterThis,
        reviewer,
        memberCount: members.length,
      }),
    })
  }

  // ── 结果装配 ──────────────────────────────────────────────────────────────
  const loadAfter: Record<string, number> = {}
  const loadIncrement: Record<string, number> = {}
  for (const m of members) {
    if (m.baseLoad !== null) loadAfter[m.staffId] = comparableLoad(m)
    loadIncrement[m.staffId] = m.assignedWeight
  }

  return {
    assignments,
    loadAfter,
    loadIncrement,
    unknownLoadStaffIds,
    unassignedTargets,
    degraded,
    warnings,
  }

  // ── 内部：候选排序 ────────────────────────────────────────────────────────

  /**
   * 执行人：负载已知者优先 → 加权负载最小 → 资历较低者优先（不浪费资深人力，
   * 天然把高资历留给高风险底稿）→ staffId 升序（可复算）。
   */
  function pickAssignee(pool: MemberState[]): MemberState {
    return [...pool].sort((a, b) => {
      const tier = loadTier(a) - loadTier(b)
      if (tier !== 0) return tier
      const load = comparableLoad(a) - comparableLoad(b)
      if (Math.abs(load) > 1e-9) return load
      if (a.seniority !== b.seniority) return a.seniority - b.seniority
      return a.staffId < b.staffId ? -1 : a.staffId > b.staffId ? 1 : 0
    })[0]
  }

  /**
   * 复核人：资历不低于执行人 且 非执行人本人 → 负载已知者优先 → 排序键
   * （加权负载 + 已承担复核次数 × 轮转单位）最小 → 资历较高者优先（复核宁高不低）。
   *
   * 🔴 `m.staffId !== assignee.staffId` 是 SOD 硬约束，无合格人选返回 `null`。
   */
  function pickReviewer(pool: MemberState[], assignee: MemberState): MemberState | null {
    const candidates = pool.filter(
      (m) => m.staffId !== assignee.staffId && m.seniority >= assignee.seniority,
    )
    if (candidates.length === 0) return null
    return [...candidates].sort((a, b) => {
      const tier = loadTier(a) - loadTier(b)
      if (tier !== 0) return tier
      const ka = comparableLoad(a) + a.reviewCount * REVIEW_ROTATION_UNIT
      const kb = comparableLoad(b) + b.reviewCount * REVIEW_ROTATION_UNIT
      if (Math.abs(ka - kb) > 1e-9) return ka - kb
      if (a.seniority !== b.seniority) return b.seniority - a.seniority
      return a.staffId < b.staffId ? -1 : a.staffId > b.staffId ? 1 : 0
    })[0]
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// rationale
// ═══════════════════════════════════════════════════════════════════════════

function buildRationale(args: {
  degraded: boolean
  target: { wpCode: string; risk: RiskLevel; declaredRisk: RiskLevel; rowCount: number }
  required: number
  weight: number
  assignee: MemberState
  loadBefore: number
  loadAfterThis: number
  reviewer: MemberState | null
  memberCount: number
}): string {
  const {
    degraded, target, required, weight, assignee, loadBefore, loadAfterThis, reviewer, memberCount,
  } = args
  const coefficient = RISK_COEFFICIENT[riskKeyOf(target.risk)]

  const head = degraded
    ? '未做风险匹配（B50 风险评估不可用），按纯负载均衡分配'
    : `风险 ${riskLabel(target.declaredRisk)}（要求资历 ≥ ${required}）`

  const who = `执行人 ${assignee.name}（资历 ${assignee.seniority}，`
    + (assignee.baseLoad === null
      ? '当前负载未知、仅本次增量参与比较，为候选中最小'
      : `分配前加权负载 ${fmt(loadBefore)}，为合格候选中最小`)
    + '）'

  const weightText = `本底稿权重 ${fmt(weight)} = 1 + 风险系数 ${coefficient.toFixed(1)}`
    + ` + 行数 ${target.rowCount}/${ROW_COUNT_DIVISOR}`
  const after = assignee.baseLoad === null
    ? `分配后本次累计增量 ${fmt(loadAfterThis)}（基线未知）`
    : `分配后加权负载 ${fmt(loadAfterThis)}`

  const rev = reviewer
    ? `复核人 ${reviewer.name}（资历 ${reviewer.seniority} ≥ 执行人 ${assignee.seniority}，`
      + (reviewer.baseLoad === null
        ? '当前负载未知'
        : `加权负载 ${fmt(comparableLoad(reviewer))}`)
      + '）'
    : memberCount <= 1
      ? '复核人留空：项目组仅 1 名成员，无法在满足执行人 ≠ 复核人的前提下指派复核人'
      : `复核人留空：无「资历 ≥ ${assignee.seniority} 且非执行人本人」的候选，`
        + '不得由执行人复核自己的工作，须另行指派'

  return `${head}；${who}；${weightText}，${after}。${rev}。`
}
