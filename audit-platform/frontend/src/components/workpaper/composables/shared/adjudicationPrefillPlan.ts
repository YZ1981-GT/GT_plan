/**
 * adjudicationPrefillPlan — 审定表「从四表库带入未审数」的**计划/应用**骨架（平台级共享件）。
 *
 * **为什么要抽出来**
 *
 * 各循环的行模型与持久化键各不相同（JSON 行存储 / 独立 itemId / 动态行 / 跨 sheet 聚合键），
 * 但「带入」这件事的四个关注点是**完全一样**的，而且每一条都对应一个已实测的缺陷形态：
 *
 * 1. **手工优先** —— 已有非空值且与四表不同时进 `conflicts` 交调用方弹确认，
 *    绝不静默覆盖（明细表已编制的数据优先于四表原始取数）。
 * 2. **幂等** —— 值已相同的格不产生写入（反复点按钮不该刷新 `updated_at`、不该触发同步）。
 * 3. **本项目无此科目 ≠ 该科目为 0** —— 未命中的槽进 `absentSlots`，界面如实说明，
 *    不写 0（E1 的「存放财务公司款项」实证：写 0 会把「不适用」伪装成「已核实为零」）。
 *
 *    🔴 **同一条口径有两个入口，早期只堵了前一个**：
 *    - 入口 A「槽未命中」→ `absentSlots`（本模块一直有）
 *    - 入口 B「**槽命中但四表金额为 0**」→ `zeroSkipped`（2026-08-15 补）
 *
 *    入口 B 的实证（I1-1 宜宾临港店 soe）：后端 `adjudication_prefill` 如实下发了
 *    3 段 × 6 类别 = 18 行，但该项目 `tb_balance` 无 17xx 余额，每行
 *    `opening/closing/increase/decrease` 全为 0。旧逻辑把这 18 个 0 当正常写入，
 *    toast 报「补填 18 格」——审计师据此以为已带入真实数据，实际是把
 *    「本项目无此科目余额」伪装成了「已核实为零」，与上面第 3 条自相矛盾。
 *    对照组「和平药房_2024」同一底稿期末 5,445,065.12（非零），证明后端取数无误、
 *    缺陷只在本模块的写入判定。
 *
 *    → 现在「当前格为空 + 四表金额为 0」进 `zeroSkipped` 不写入。审计师若确实要
 *    记录「已核实为零」，手工填 0 即可（手工优先原则本就允许）。
 * 4. **未能归类的金额不兜底** —— 进 `unclassified` 由审计师分配，绝不塞进「其他」行
 *    （K2 实测把三行坏账准备全堆进「其他」的根因）。
 *
 * 本模块是**纯函数、零 Vue 依赖**：不碰 store、不发请求、不弹框，便于单测与 PBT。
 * 「哪个金额进哪一格」这件带会计判断的事由各循环的声明文件决定
 * （G 循环 → `gCycleAdjudicationSeed.ts`）。
 *
 * spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
 *       Requirements 3.3, 3.4, 3.5 / Task 3.3
 */

/** 金额比较容差（分） */
export const PREFILL_TOLERANCE = 0.005

/** 待写入的一格 */
export interface AdjPrefillCell {
  /** 审定表行键（或跨 sheet 聚合键的行部分） */
  rowKey: string
  /** 列字段名（如 `openingUnadjusted` / `currentUnadjusted`） */
  field: string
  /** 四表口径金额 */
  amount: number
  /** 行中文名（提示文案与冲突清单用） */
  label: string
  /** 期间中文名（「期初未审」/「期末未审」/「本期未审」） */
  periodLabel: string
  /** 该格金额来自哪些四表科目（溯源展示） */
  sourceCodes?: string[]
}

/** 已有值与四表不一致的一格 */
export interface AdjPrefillConflict extends AdjPrefillCell {
  /** 当前已录入的值 */
  current: number
}

/** 无法归类到任何审定行的四表叶子 */
export interface AdjPrefillUnclassified {
  code: string
  name: string
  /** 期间口径对应的金额（资产负债类取期末，损益类取本期发生额） */
  amount: number
  /** 期初金额（损益类为 0） */
  opening: number
}

export interface AdjPrefillPlan {
  /** 当前为空 → 直接写入 */
  writes: AdjPrefillCell[]
  /** 已有值且不同 → 需用户确认 */
  conflicts: AdjPrefillConflict[]
  /** 四表已有值但当前值已相同 → 幂等跳过（计数用，便于提示「无需带入」） */
  identical: number
  /** 未能归类的叶子（交审计师分配，不兜底） */
  unclassified: AdjPrefillUnclassified[]
  /** 本项目无该科目的槽（如实说明，不写 0） */
  absentSlots: Array<{ slotKey: string; label: string }>
  /**
   * 四表金额为 0 且当前格为空 → **不写入**（见模块头第 3 条入口 B）。
   *
   * 与 `absentSlots` 的区别：`absentSlots` 是「声明的槽在四表里根本没有对应科目」，
   * 本桶是「科目行下发了但余额为 0」。两者都不该落 0，但提示文案不同，
   * 故分两个桶，便于界面如实区分。
   */
  zeroSkipped: AdjPrefillCell[]
}

/**
 * 当前值读取器。返回 `null` / `undefined` / `''` 视为**未填**。
 *
 * 调用方通常实现为「从 `checklist_responses` 或行 store 里读该格」。
 */
export type AdjCurrentReader = (cell: AdjPrefillCell) => number | string | null | undefined

function isBlank(v: number | string | null | undefined): boolean {
  return v === null || v === undefined || String(v).trim() === ''
}

/**
 * 生成带入计划（不执行任何写入）。
 *
 * @param cells 由循环声明推导出的待写入格
 * @param read 当前值读取器
 * @param extras 未归类叶子 / 缺失槽（由循环声明推导，原样透传给调用方）
 */
export function planAdjudicationPrefill(
  cells: readonly AdjPrefillCell[],
  read: AdjCurrentReader,
  extras: {
    unclassified?: readonly AdjPrefillUnclassified[]
    absentSlots?: ReadonlyArray<{ slotKey: string; label: string }>
  } = {},
): AdjPrefillPlan {
  const plan: AdjPrefillPlan = {
    writes: [],
    conflicts: [],
    identical: 0,
    unclassified: [...(extras.unclassified ?? [])],
    absentSlots: [...(extras.absentSlots ?? [])],
    zeroSkipped: [],
  }
  for (const cell of cells ?? []) {
    const cur = read(cell)
    if (isBlank(cur)) {
      // 🔴 入口 B：四表金额为 0 且当前空 → 不写 0（见模块头第 3 条）。
      // 空格显示与 0 在 UI 上都是「-」（fmtAmount 平台口径），写入没有信息增量，
      // 却会刷新 updated_at、触发附注同步、并让 toast 谎报「补填 N 格」。
      if (Math.abs(cell.amount) <= PREFILL_TOLERANCE) {
        plan.zeroSkipped.push(cell)
        continue
      }
      plan.writes.push(cell)
      continue
    }
    const curNum = Number(cur)
    if (!Number.isFinite(curNum)) {
      // 非数值的既有内容一律当「已录入」保护起来，交用户确认
      plan.conflicts.push({ ...cell, current: 0 })
      continue
    }
    if (Math.abs(curNum - cell.amount) <= PREFILL_TOLERANCE) {
      plan.identical += 1
      continue
    }
    plan.conflicts.push({ ...cell, current: curNum })
  }
  return plan
}

/** 填充方式：只补空值（默认，永不覆盖已录入）/ 连冲突项一起覆盖 */
export type AdjPrefillMode = 'fill-blank' | 'overwrite'

/** 计划 → 实际写入项 */
export function resolveAdjPrefillWrites(
  plan: AdjPrefillPlan,
  mode: AdjPrefillMode = 'fill-blank',
): AdjPrefillCell[] {
  return mode === 'overwrite' ? [...plan.writes, ...plan.conflicts] : [...plan.writes]
}

/** 计划是否有任何可执行动作（决定按钮禁用态） */
export function planHasWork(plan: AdjPrefillPlan): boolean {
  return plan.writes.length > 0 || plan.conflicts.length > 0
}

/** 计划摘要（toast 文案，全中文） */
export function describeAdjPrefillPlan(plan: AdjPrefillPlan): string {
  const parts: string[] = []
  if (plan.writes.length) parts.push(`补填 ${plan.writes.length} 格`)
  if (plan.conflicts.length) parts.push(`${plan.conflicts.length} 格与现有录入不一致`)
  if (plan.identical) parts.push(`${plan.identical} 格已一致（跳过）`)
  if (plan.unclassified.length) {
    parts.push(`${plan.unclassified.length} 个科目待归类`)
  }
  if (plan.absentSlots.length) {
    parts.push(`${plan.absentSlots.map((s) => s.label).join('、')} 本项目无此科目`)
  }
  if (plan.zeroSkipped.length) {
    // 🔴 不能说成「已带入」也不能说成「一致」：四表确实下发了这些行，但余额为 0。
    // 如实告知「未写入」+ 给出手工兜底路径，避免审计师误判已核实。
    parts.push(
      `${plan.zeroSkipped.length} 格四表余额为 0，未写入`
      + '（本项目该科目无余额；如需记录「已核实为零」请手工填 0）',
    )
  }
  return parts.length ? parts.join('；') : '四表数据与当前未审数一致，无需带入'
}

/** 冲突清单的确认框文案（最多列前 n 条） */
export function describeAdjPrefillConflicts(
  plan: AdjPrefillPlan,
  limit = 6,
): string {
  const shown = plan.conflicts.slice(0, limit).map(
    (c) => `· ${c.label} ${c.periodLabel}：现有 ${c.current} → 四表 ${c.amount}`,
  )
  const more = plan.conflicts.length > limit ? `\n…共 ${plan.conflicts.length} 格` : ''
  return shown.join('\n') + more
}
