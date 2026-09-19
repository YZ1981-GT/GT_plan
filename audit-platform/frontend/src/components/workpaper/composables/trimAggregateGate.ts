/**
 * 裁剪建议汇总闸（纯函数，零 Vue 依赖、零 IO）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 8
 * 守卫: `__tests__/trimAggregateGate.spec.ts`
 * Property 10（只计重要性类且按科目去重）/ Property 11（阈值方向）
 *
 * ## 它解决的审计问题
 *
 * 准则要求「汇总考虑错报」：若干**各自**低于实际执行重要性的科目，其错报**汇总**
 * 起来可能远超财务报表层面可容忍的水平。所以「逐科目建议裁剪」这个动作在批量
 * 应用之前必须过一道汇总闸 —— 建议裁掉的那批科目金额合计若已达到实际执行重要性，
 * 就不能一次性批量确认，必须退回让审计师逐条判断哪些确实可以不做程序。
 *
 * 这也是 `procedureTrimDecision` 对重要性维度只产 `suggest_trim`、永不 `auto_trim`
 * 的下半段：单科目判据说「这一个小」，汇总闸说「这一堆加起来不小」，两者缺一
 * 都会让重要性维度变成放行阀。
 *
 * ## 三条极易被「优化」掉的约束
 *
 * 三条都配了守卫与变异检验，因为它们被改掉之后功能表面上仍然正常工作 ——
 * 闸门只是从「偶尔拦一次」变成「恒亮」或「恒不亮」，随后就会被当成误报关掉。
 *
 * 1. **只计重要性类理由码**（`below_trivial` / `below_materiality`）。`no_data`
 *    是数据存在性判据的自动裁剪结果，金额恒 0 或极小，把它纳入只增噪声不增
 *    信号；一旦闸门在正常项目上恒亮，审计师就会停止相信它。
 * 2. **按科目名去重**。同一科目往往有多个程序被同时建议裁剪（一个科目下十几张
 *    底稿是常态），不去重会让合计虚高数倍，同样把闸门推向恒亮。汇总闸比较的是
 *    「科目金额之和」而不是「程序条数 × 科目金额」。
 * 3. **判据是 `>=` 而非 `>`**。恰好等于实际执行重要性时，准则上已属「可能超过
 *    可容忍水平」，放过它就是放过边界。
 *
 * ## 术语约定
 *
 * 平台既有 `GtB50RiskAssessment.vue` 用两三字母缩写命名重要性字段，且与审计通用
 * 含义正好相反。故本模块一律用数据库字段名全称：`performanceMateriality` =
 * 实际执行重要性。财务报表整体层面的重要性水平不作为汇总闸阈值 —— 它是报表整体
 * 评价基准，而这里判断的是「这批被建议裁剪的科目错报汇总起来是否已不可容忍」，
 * 口径必须与单科目判据一致，故本模块的输入类型里压根没有它。
 */

// ═══════════════════════════════════════════════════════════════════════════
// 类型
// ═══════════════════════════════════════════════════════════════════════════

/** 参与汇总的单条裁剪建议。 */
export interface AggregateGateItem {
  /** 科目名称，去重键 */
  accountName: string
  /** 科目余额；贷方性质科目为负，按绝对值参与汇总 */
  amount: number
  /** 结构化裁剪理由码；仅重要性类计入汇总 */
  reasonCode: string
}

export interface AggregateGateResult {
  /** 重要性缺失时为 false（无比较基准，闸门不适用） */
  applicable: boolean
  /** 去重后计入汇总的科目个数 */
  distinctAccountCount: number
  /** 按科目去重后的绝对值合计 */
  totalAmount: number
  /** 比较基准 = 实际执行重要性；不可用时为 null */
  threshold: number | null
  /** 是否阻断批量确认：`threshold !== null && totalAmount >= threshold` */
  blocked: boolean
  /** 面向审计师的一句话说明，含判据数值 */
  narrative: string
}

export interface AggregateGateInput {
  items: AggregateGateItem[]
  /** 实际执行重要性；`null` = 本项目尚未设置，闸门不适用 */
  performanceMateriality: number | null
}

// ═══════════════════════════════════════════════════════════════════════════
// 常量与小工具
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 计入汇总的理由码集合。
 *
 * 🔴 不能改成「全部裁剪建议」：`no_data` 等其他理由码是事实判断类自动裁剪，
 * 与「金额小所以不做」不是同一件事，纳入汇总会让闸门恒亮进而被当误报关掉。
 */
const MATERIALITY_REASON_CODES: ReadonlySet<string> = new Set([
  'below_trivial',
  'below_materiality',
])

/** 金额格式化（千分符 + 两位小数），纯函数、不依赖任何 store 或区域设置。 */
function formatAmount(value: number): string {
  if (!Number.isFinite(value)) return String(value)
  const negative = value < 0
  const fixed = Math.abs(value).toFixed(2)
  const dot = fixed.indexOf('.')
  const intPart = fixed.slice(0, dot)
  const decPart = fixed.slice(dot + 1)
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}.${decPart}`
}

/** 该金额是否可参与数值汇总（非有限值一律按 0 计，不污染合计）。 */
function toComparableAbs(value: unknown): number {
  const num = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(num)) return 0
  return Math.abs(num)
}

function normalizeAccountName(value: unknown): string {
  return String(value ?? '').trim()
}

// ═══════════════════════════════════════════════════════════════════════════
// 汇总闸
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 对一批裁剪建议做汇总闸校验。
 *
 * 步骤固定为「过滤理由码 → 按科目去重 → 绝对值合计 → 与实际执行重要性比较」，
 * 顺序不可调换：先合计后去重等于不去重，先去重后过滤会让 `no_data` 抢占某科目
 * 的去重槽位从而把该科目的重要性类金额挤掉。
 *
 * @param args.items 逐程序的裁剪建议（同科目多条是常态）
 * @param args.performanceMateriality 实际执行重要性；`null` 表示该维度不可用
 */
export function evaluateAggregateGate(args: {
  items: AggregateGateItem[]
  performanceMateriality: number | null
}): AggregateGateResult {
  const items = Array.isArray(args?.items) ? args.items : []
  const rawThreshold = args?.performanceMateriality
  const threshold = typeof rawThreshold === 'number' && Number.isFinite(rawThreshold)
    ? rawThreshold
    : null

  // 按科目去重：Map 保留首次出现的金额。
  //
  // 🔴 必须用 Map/Set 做去重，不能写成裸 reduce 求和 —— 同一科目下多张底稿的
  // 程序会被同时建议裁剪，累加会让合计虚高数倍。同科目不同金额时取首次出现那条
  // （同一科目只有一个余额，出现分歧属上游取数问题，此处不做平均也不取最大）。
  const byAccount = new Map<string, number>()
  for (const item of items) {
    if (!item) continue
    if (!MATERIALITY_REASON_CODES.has(String(item.reasonCode ?? ''))) continue
    const account = normalizeAccountName(item.accountName)
    if (byAccount.has(account)) continue
    byAccount.set(account, toComparableAbs(item.amount))
  }

  let totalAmount = 0
  for (const amount of byAccount.values()) totalAmount += amount
  const distinctAccountCount = byAccount.size

  // 🔴 判据是 `>=` 不是 `>`：恰好等于实际执行重要性时，准则上已属「可能超过
  // 可容忍水平」，放过它就是放过边界。
  const blocked = threshold !== null && totalAmount >= threshold

  return {
    applicable: threshold !== null,
    distinctAccountCount,
    totalAmount,
    threshold,
    blocked,
    narrative: buildNarrative({ distinctAccountCount, totalAmount, threshold, blocked }),
  }
}

function buildNarrative(args: {
  distinctAccountCount: number
  totalAmount: number
  threshold: number | null
  blocked: boolean
}): string {
  const { distinctAccountCount, totalAmount, threshold, blocked } = args
  const scope = `本次建议裁剪科目 ${distinctAccountCount} 个（已按科目去重），`
    + `金额合计 ${formatAmount(totalAmount)} 元`

  if (threshold === null) {
    return `${scope}。本项目尚未设置实际执行重要性，汇总闸缺少比较基准，`
      + '故不阻断批量确认；请先在重要性水平底稿中设置后再行汇总评估。'
  }

  const compare = `实际执行重要性 ${formatAmount(threshold)} 元`
  if (blocked) {
    return `${scope}，已达到${compare}。`
      + '准则要求汇总考虑错报 —— 这批科目各自金额虽小，汇总错报可能超过可容忍水平，'
      + '故不得一次性批量确认，请逐条判断哪些科目确实可以不实施实质性程序。'
  }
  return `${scope}，低于${compare}，汇总错报敞口在可容忍范围内，可批量确认。`
}
