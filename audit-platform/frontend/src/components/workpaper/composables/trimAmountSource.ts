/**
 * 裁剪判据的科目金额来源解析（纯函数，零 Vue 依赖、零 IO）。
 *
 * spec: procedure-trim-report-line-account-resolution — Task 10
 * Requirements: 5.1, 5.2, 6.2, 6.3
 * 守卫: `views/__tests__/trimAmountSourcePriority.spec.ts`
 *
 * ## 它解决什么
 *
 * 裁剪判据的重要性维度（决策内核档 7/8）需要「这条程序对应的科目余额」。改造前唯一的
 * 定位方式是**程序名 ↔ 科目名子串匹配**（`resolveAccountName`），在真实数据上大面积
 * 失效 —— 程序按**报表项目**组织（「货币资金 - 函证」），而 `ctx.accounts` 按
 * **明细科目名**索引（「银行存款」「其他货币资金」），两者是层级关系不是命名关系。
 * 实证 E 循环 5 条程序全部解析不出 ⇒ `accountAmount` 恒 `null` ⇒ 重要性档整体空转。
 *
 * 本模块把金额来源改为**报表行映射优先、科目名匹配兜底**：
 *
 * ```
 * ctx.report_line_amounts[wpCode]   ← 后端「程序 → 报表行 → 报表公式 → 金额」
 *   │ status === 'resolved' 且金额是有限数
 *   ├─ 命中 → source = 'report_line'（与报表页同一取数引擎，故金额与报表上那个数一致）
 *   └─ 未命中 ↓
 * resolveAccountName(p, ctx) → ctx.accounts[name].amount
 *   ├─ 命中 → source = 'account_name'（可靠性较低，界面须显式标注）
 *   └─ 未命中 → amount = null（与改造前逐字相同，决策内核据此跳过重要性维度）
 * ```
 *
 * ## 🔴 为什么必须是**唯一**取金额入口
 *
 * 改造前取金额有**两处各算一份**：`buildAndDecide`（喂决策内核）与 `toReviewRow`
 * （喂裁剪充分性复核视图）。两处当时口径相同故未分叉，但它们是两份实现 —— 给报表行
 * 加优先级时只改一处，复核视图就会显示旧口径金额，而**复核者无从知道该信哪个**
 * （R6.2 要求两处逐项相等）。故两处一律调本函数，守卫按「宿主里零处直接读
 * `ctx.accounts[...].amount`」的结构判据钉死。
 *
 * ## 🔴 为什么 `status !== 'resolved'` 时即便带了金额也不采用
 *
 * 后端约定非 `resolved` 态恒 `null`，但前端不能依赖对端守约 —— 一旦后端某个分支漏了
 * 置空（编造出 `0`），该程序会被误判成「低于任何阈值」而产生裁剪建议，
 * 而正确结论是「这个判据对它不可用」。门控写成 `status === 'resolved' && 有限数`
 * 是双保险，成本一行。
 */

import type { TrimDecisionContext, TrimReportLineAmount } from '@/services/commonApi'

/** 金额来源标识；`null` = 两个来源都未命中。 */
export type TrimAmountSource = 'report_line' | 'account_name' | null

export interface ResolvedTrimAmount {
  /** 可参与重要性比较的金额；`null` = 该维度对本程序不可用（**不是 0**） */
  amount: number | null
  source: TrimAmountSource
  /** 报表行溯源（`source === 'report_line'` 时非空；否则为 null） */
  reportLine: TrimReportLineAmount | null
  /** 科目名匹配到的科目名（供 B50 风险定位与复核视图展示；未命中为 null） */
  accountName: string | null
  /** 两来源都命中且金额不等时的差异描述（R5.2 溯源）；否则 null */
  divergence: string | null
}

/** 底稿编号归一：取首个「字母段 + 数字段」。与后端 `normalize_wp_code` 同语义。 */
const WP_CODE_PREFIX_RE = /^([A-Z]+\d+)/

function normalizeWpCode(raw: unknown): string {
  return String(raw ?? '').trim().toUpperCase().match(WP_CODE_PREFIX_RE)?.[1] || ''
}

/** 该金额是否可参与数值比较（`null` / NaN / Infinity 一律不可）。 */
function isComparableAmount(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/** 金额格式化（千分符 + 两位小数），纯函数、不依赖 store 或区域设置。 */
function formatAmount(value: number): string {
  if (!Number.isFinite(value)) return String(value)
  const negative = value < 0
  const fixed = Math.abs(value).toFixed(2)
  const dot = fixed.indexOf('.')
  const grouped = fixed.slice(0, dot).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}.${fixed.slice(dot + 1)}`
}

/**
 * 在 `ctx.report_line_amounts` 里定位本程序的报表行金额。
 *
 * 查找顺序：完整 `wp_code` → 归一后的底稿主码。后端按 `procedure_instances.wp_code`
 * 原样下发（含 `D2-1至D2-4` 这类区间型），故第一步通常直接命中；归一兜底是防后端
 * 将来改成按底稿主码下发时前端静默失配。
 */
function lookupReportLine(
  p: any, ctx: TrimDecisionContext,
): TrimReportLineAmount | null {
  const table = (ctx as any)?.report_line_amounts
  if (!table || typeof table !== 'object') return null
  const raw = String(p?.wp_code || p?.procedure_code || '').trim()
  const direct = raw ? table[raw] : undefined
  if (direct && typeof direct === 'object') return direct as TrimReportLineAmount
  const normalized = normalizeWpCode(raw)
  const byPrefix = normalized ? table[normalized] : undefined
  return (byPrefix && typeof byPrefix === 'object')
    ? byPrefix as TrimReportLineAmount
    : null
}

/**
 * 按科目名在判据上下文里定位该程序对应的科目名。
 *
 * 🔴 与宿主 `ProcedureTrimming.vue` 的 `resolveAccountName` **同语义的独立实现** ——
 * 那一份是宿主内部函数（vitest 无法 import），且本 spec 明确**不改它**
 * （它仍是复核视图定位科目名、委派侧匹配 B50 风险的唯一实现）。两份实现由
 * 守卫交叉锁死：宿主那份的函数体 md5 已冻结，本份的行为由本模块守卫覆盖，
 * 且宿主调用本模块时把它自己解析出的科目名**传进来**（见 `accountNameHint`），
 * 于是运行时只有一份结果生效，本份仅作为独立调用（如单测）的兜底。
 */
function matchAccountNameByProcedureName(p: any, ctx: TrimDecisionContext): string | null {
  const names = Object.keys(ctx?.accounts || {})
  if (!names.length) return null
  const procName = String(p?.procedure_name || '').trim()
  if (!procName) return null
  // 最长匹配优先：科目名越长越具体（「应收账款」优于「应收」）
  const sorted = [...names].sort((a, b) => b.length - a.length)
  for (const n of sorted) {
    if (n && procName.includes(n)) return n
  }
  return null
}

/**
 * 取该程序用于重要性判据的科目金额及其来源。
 *
 * @param p 程序实例行（读 `wp_code` / `procedure_code` / `procedure_name`）
 * @param ctx 判据上下文（读 `report_line_amounts` 与 `accounts`）
 * @param accountNameHint 宿主已解析出的科目名。宿主一律传入它自己
 *   `resolveAccountName` 的结果，使运行时只有一份科目名解析生效；
 *   `undefined` 时本模块用等价实现自行匹配（供单测与其它调用方）。
 */
export function resolveAccountAmount(
  p: any,
  ctx: TrimDecisionContext,
  accountNameHint?: string | null,
): ResolvedTrimAmount {
  const reportLine = lookupReportLine(p, ctx)
  const reportLineAmount = (reportLine && reportLine.status === 'resolved')
    ? reportLine.amount
    : null
  const reportLineOk = isComparableAmount(reportLineAmount)

  const accountName = accountNameHint !== undefined
    ? (accountNameHint ?? null)
    : matchAccountNameByProcedureName(p, ctx)
  const rawByName = accountName !== null
    ? Number((ctx?.accounts as any)?.[accountName]?.amount)
    : Number.NaN
  const byNameOk = isComparableAmount(rawByName)

  // 两来源都命中且金额不等 → 采用报表行值，留痕差异供溯源（R5.2）
  const divergence = (reportLineOk && byNameOk && reportLineAmount !== rawByName)
    ? `报表行 ${reportLine!.row_code || '(未知行)'}${reportLine!.row_name ? ` ${reportLine!.row_name}` : ''}`
      + ` 取数 ${formatAmount(reportLineAmount as number)} 元，`
      + `按科目名「${accountName}」匹配得 ${formatAmount(rawByName)} 元，`
      + '本次采用报表行取数（与报表页同口径）'
    : null

  if (reportLineOk) {
    return {
      amount: reportLineAmount as number,
      source: 'report_line',
      reportLine,
      accountName,
      divergence,
    }
  }
  if (byNameOk) {
    return {
      amount: rawByName,
      source: 'account_name',
      reportLine: null,
      accountName,
      divergence: null,
    }
  }
  return {
    amount: null,
    source: null,
    reportLine: null,
    accountName,
    divergence: null,
  }
}

/**
 * 决策内核 `reportLine` 入参的映射（snake_case → camelCase）。
 *
 * 只在 `source === 'report_line'` 时产出非 null —— 非 `resolved` 态的报表行信息
 * 不进 evidence，否则复核者会看到一个「有报表行但金额是科目名匹配来的」的混合态。
 */
export function toDecisionReportLine(resolved: ResolvedTrimAmount): {
  rowCode: string
  rowName: string
  formula: string | null
  standardCodes: string[]
} | null {
  const rl = resolved.source === 'report_line' ? resolved.reportLine : null
  if (!rl) return null
  return {
    rowCode: String(rl.row_code || ''),
    rowName: String(rl.row_name || ''),
    formula: rl.formula ?? null,
    standardCodes: Array.isArray(rl.standard_codes) ? rl.standard_codes.map(String) : [],
  }
}

/**
 * 汇总闸的**去重键**（单一真源，裁剪页与复核视图共用）。
 *
 * 🔴 为什么不能直接用科目名或 `wp_code`（浏览器实测暴露的缺陷）
 *
 * `evaluateAggregateGate` 按 `accountName` 去重，语义是「同一笔科目余额只算一次错报
 * 敞口」。报表行映射生效前，E 循环的科目名解析不出 ⇒ 退回 `wp_code` ⇒ 但那时金额也是
 * `null`（计 0）⇒ 合计恒 0、闸门不亮，缺陷被掩盖。
 *
 * 报表行映射生效后金额有了，而去重键仍是 `wp_code` ⇒ **同一个报表行的 4 条程序被当成
 * 4 个不同科目**：实测项目 E 循环 4 条程序都落 `BS-002 货币资金`（同一笔
 * 8,607,977.04），闸门却算成 34,431,908.16（虚高 4 倍）⇒ 超过实际执行重要性
 * 26,104,487.00 ⇒ **过度阻断批量确认**，审计师无法批量裁掉本该可以裁的程序。
 *
 * 正确的去重键 = 报表行编码（同一报表项目 = 同一笔余额）。退化顺序：
 * 报表行编码 → 科目名 → 底稿编号（后两者是报表行未命中时的兜底，语义较弱但总比无键好）。
 */
export function aggregateGateKey(
  evidence: { reportLine?: { rowCode?: string | null } | null } | null | undefined,
  accountName: unknown,
  wpCode: unknown,
): string {
  const rowCode = String(evidence?.reportLine?.rowCode || '').trim()
  if (rowCode) return rowCode
  const name = String(accountName ?? '').trim()
  if (name) return name
  return String(wpCode ?? '').trim()
}

/**
 * 金额来源的中文标签（界面标注与 `skip_reason` 规范文本共用，避免两处文案漂移）。
 */
export function amountSourceLabel(source: TrimAmountSource): string {
  if (source === 'report_line') return '报表行取数'
  if (source === 'account_name') return '科目名匹配'
  return ''
}

/**
 * 金额来源的溯源短语，追加到裁剪理由（`skip_reason`）里（R6.1）。
 *
 * 入参**扁平**而不是收 `ResolvedTrimAmount` —— 两个调用场景的数据形态不同：
 * 解析当场用 `ResolvedTrimAmount`（snake_case 的 `TrimReportLineAmount`），
 * 落库时用决策内核的 `TrimEvidence`（camelCase 的 `TrimReportLineTrace`，且**没有**
 * `accountName` 字段，须由调用方另传）。收扁平参数使两处共用**一套文案** ——
 * 各写一份必然漂移，而落库文本是给质控复核合伙人看的，两处不一致他无从判断。
 *
 * 空串表示无可追加内容 —— 调用方据此不拼接，避免产出「…（取自 ）」这种残缺文本。
 */
export function amountSourceTrace(args: {
  source: TrimAmountSource
  rowCode?: string | null
  rowName?: string | null
  formula?: string | null
  accountName?: string | null
}): string {
  if (args.source === 'report_line') {
    const code = String(args.rowCode || '').trim()
    const name = String(args.rowName || '').trim()
    const head = `取自报表行 ${code || '(未知行)'}${name ? ` ${name}` : ''}`
    const formula = String(args.formula || '').trim()
    return formula ? `${head}（${formula}）` : head
  }
  if (args.source === 'account_name') {
    const name = String(args.accountName || '').trim()
    return name ? `取自按科目名「${name}」匹配的试算表余额` : '取自按科目名匹配的试算表余额'
  }
  return ''
}

// 🔴 此处曾有 `traceArgsOf(resolved)`（把 `ResolvedTrimAmount` 映射成
//    `amountSourceTrace` 的入参）。复盘扫出它**零消费方** —— 宿主拼溯源文本时手上
//    只有决策内核的 `TrimEvidence`（camelCase、且无 accountName），走的是直接构造
//    扁平参数那条路，压根用不到它。按平台铁律「死代码立即删除」已移除；
//    留此说明是为了让后续会话不再"补回来"：需要从 ResolvedTrimAmount 拼溯源时，
//    直接调 `amountSourceTrace({ source, rowCode: rl?.row_code, ... })` 即可。
