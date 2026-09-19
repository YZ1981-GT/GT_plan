/**
 * 损益类审定表行模型（K8~K13 共用）。
 *
 * 🔴 **消灭 `unadjustedDebit` / `unadjustedCredit` 双列**：损益类在含年末结转损益的
 * 全年账上 `debit == credit`（恒零），双列并列只会误导审计师以为有净额差异。
 * 改为单一 `unadjusted`（由后端 `pl_occurrence.build_occurrence_prefill` 按方向侧
 * 归一后下发），审定表只展一列「本期发生额」。
 *
 * 前端 `calcIncomeStatementOccurrence(debit, credit)` 6 份复制品同步退役，
 * 改为恒等函数（入参即结果，因为对侧已被后端置 0）。
 *
 * spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
 *       复盘建议 ① / Property 7
 */

/**
 * 损益类审定表行（单列口径）。
 *
 * `unadjusted` = 后端 `build_occurrence_prefill` 按报表口径归一后的本期发生额
 * （费用类保留符号 / 收益类取绝对值）。
 */
export interface PlAdjRow {
  rowKey: string
  /** 费用明细项目名 / 子科目名 */
  projectName: string
  /** 本期发生额（未审，单列） */
  unadjusted: number
  /** 审计调整分录净额 */
  aje: number
  /** 重分类调整分录净额 */
  rje: number
  /** 审定数 = unadjusted + aje + rje */
  audited: number
  /** 上年审定数（同比基准） */
  priorAmount: number
  /** 同比变动额 */
  yoyChange: number
  /** 同比变动率（null = 分母为 0） */
  yoyChangeRate: number | null
  /** 备注 */
  remark: string
  /** 是否可编辑（手工行 / 四表行均可编辑） */
  isEditable: boolean
}

/** 合计行 */
export interface PlAdjSubtotalRow {
  label: string
  unadjusted: number
  aje: number
  rje: number
  audited: number
  priorAmount: number
  yoyChange: number
  yoyChangeRate: number | null
}

/** 四表预填行（后端 `adjudication_prefill` 的单条） */
export interface PlAdjPrefillRow {
  name: string
  code?: string
  /** 本期发生额（单列，已归一） */
  unadjusted: number
  /** 审定数初始 = unadjusted（无 AJE/RJE 时成立） */
  audited: number
}

// ─── 纯函数 ─────────────────────────────────────────────────────────────────

/**
 * 审定数 = 未审 + AJE + RJE。
 *
 * 🔴 入参逐个过 `parseNum`，**不用** `(v || 0)`：见 `parseNum` 的注释，数字字符串会被
 * `|| 0` 原样带进算式变成字符串拼接。改瘦前 6 个 `useK*FormulaEngine.ts` 各自的
 * `calcAuditedAmount` 正是 `parseNum(u) + parseNum(a) + parseNum(r)`，收敛到本模块时
 * 这层加固被丢掉了 —— 这里补回来。
 */
export function calcPlAudited(unadjusted: unknown, aje: unknown, rje: unknown): number {
  return parseNum(unadjusted) + parseNum(aje) + parseNum(rje)
}
/**
 * `calcPlAudited` 的**同一实现**，保留改瘦前 K8~K13 引擎的导出名。
 *
 * 两个名字不是两份实现：`calcPlAudited` 服务 `PlAdjRow` 行模型，`calcAuditedAmount`
 * 是 6 个引擎对外的历史 API（消费方与既有测试都按这个名字 import）。
 */
export function calcAuditedAmount(unadjusted: unknown, aje: unknown, rje: unknown): number {
  return calcPlAudited(unadjusted, aje, rje)
}

/** 同比变动额 */
export function calcPlYoyChange(audited: number, priorAmount: number): number {
  return parseNum(audited) - parseNum(priorAmount)
}

/** 同比变动率（分母为 0 返 null） */
export function calcPlYoyRate(audited: number, priorAmount: number): number | null {
  const prior = parseNum(priorAmount)
  if (Math.abs(prior) < 0.005) return null
  return (parseNum(audited) - prior) / prior
}

/** 小计求和 */
export function calcPlSubtotal(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}

/**
 * 🔴 **兼容性桥接**：旧前端期望 `(unadjustedDebit, unadjustedCredit)` 双列，
 * 后端已把发生额放方向侧、对侧置 0，故 `debit - credit`（费用）或
 * `credit - debit`（收益）的结果就是 `unadjusted` 本身。
 *
 * 此函数供尚未改造的组件过渡用，新代码直接读 `unadjusted` 不要走这里。
 * 一个月后可删。
 */
export function legacyCalcIncomeStatementOccurrence(
  debitOrCredit: number,
  creditOrDebit: number,
): number {
  // 后端保证其中一侧为 0，减法等于非零侧
  return parseNum(debitOrCredit) - parseNum(creditOrDebit)
}

/**
 * 安全数值解析：`null` / `undefined` / 空串 / 非数字 / `NaN` / `Infinity` → `0`。
 *
 * 🔴 这里是 K8~K13 的**单一真源**，本模块所有纯函数的入参都过它。曾经用的
 * **不等价**：数字字符串 `'12'` 是 truthy，`v || 0` 会把它原样带进算式变成字符串
 * 拼接（`'12' + 0 === '120'`），而 `parseNum('12') === 12`。所以凡是入参可能来自
 * `allResponses` / JSON 反序列化的地方必须走本函数，不要图省事写 `|| 0`。
 *
 * 6 个 `useK*FormulaEngine.ts` 只做 re-export，不各自复制实现。
 */
export function parseNum(val: string | number | null | undefined | unknown): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}