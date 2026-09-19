/**
 * e1NegativeBalance — E1 负余额判定与提示文案（纯函数，零 Vue 依赖）。
 *
 * **为什么需要单独一份真源**
 *
 * 货币资金期末为负是**真实语义**而不是脏数据 —— `tb_balance` 是「无符号绝对值 +
 * 方向列」形态，叶子聚合按方向带符号求和后，资金池归集户 / 内部结算户 / 透支额度户
 * 会得到负的期末余额（真实库实证：项目 `a7fc75e5` 银行存款期末 −297,771,168.89，
 * 38 个账户，账户级合计与 `tb_balance` 叶子合计 diff = 0.00 ⇒ 取数是对的）。
 *
 * 🔴 **一律不取绝对值**（Property 27）：套 `abs()` 会让「叶子和 == 父额」的勾稽从
 * diff=0 变成两倍差异，把正确取数打成错数；而审计上负余额本身就是需要披露/重分类
 * 判断的信号（可能应列报为「短期借款」或「其他应付款」），抹掉符号等于隐藏问题。
 *
 * 故本模块只做两件事：**判定**（哪些槽/账户为负）与**提示文案**（提醒审计师核实性质），
 * **不改任何金额** —— 本文件自身禁止出现 `Math.abs`（守卫源码级断言）。
 *
 * spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/
 *       Requirements 8.5 / Property 27（Task 17）
 */

/** 判定阈值 —— 与后端 `e1_bank_accounts.TOLERANCE` 同量级（0.005 元）。 */
export const NEGATIVE_TOLERANCE = 0.005

/**
 * 负余额提示文案（中文只在此处一份，组件与守卫共用）。
 *
 * 🔴 **中性归因**：负余额不是「取数错误」——文案只陈述语义并要求核实性质，
 * 不得出现「取数错误/数据错误」这类指控（审计场景里误指控比不提示更坏）。
 */
const NEGATIVE_HINT =
  '负数是「贷方性质」的真实语义（常见于资金池归集户、内部结算户或透支额度），' +
  '平台如实显示、不取绝对值；请核实该户性质，判断是否应重分类至' +
  '「短期借款」或「其他应付款」列报。'

/** 负余额账户（判定输出，金额原样保留）。 */
export interface E1NegativeAccount {
  /** 展示标签 —— 账号优先，缺失时退回科目码（不产出空标签） */
  label: string
  accountCode: string
  /** 期末余额 —— **负值本身**，不是绝对值 */
  closing: number
}

/** 负余额语义槽（两侧金额各自保留，便于对照哪一侧为负）。 */
export interface E1NegativeSlot {
  slot: string
  label: string
  accountSum: number
  leafSum: number
}

/** 判定入参：账户行的最小形状（与 `e1BankAccountPrefill.E1AccountRow` 结构兼容）。 */
interface AccountLike {
  accountCode?: unknown
  accountNo?: unknown
  closing?: unknown
}

/** 判定入参：槽勾稽行的最小形状（与溯源面板 `reconcileRows` 结构兼容）。 */
interface SlotLike {
  slot?: unknown
  label?: unknown
  accountSum?: unknown
  leafSum?: unknown
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 是否为「显著为负」（超出容差）。
 *
 * 🔴 用容差而不是裸 `< 0` —— 浮点求和会产生 `-1e-12` 这类噪声，
 * 裸判会让正常的零余额账户莫名触发负余额提示。非数值输入一律不算负（不抛）。
 */
export function isNegativeAmount(v: unknown): boolean {
  const n = Number(v)
  if (!Number.isFinite(n)) return false
  return n < -NEGATIVE_TOLERANCE
}

/**
 * 挑出期末为负的账户。
 *
 * `unassigned` 同样纳入 —— 它们进 E1-10 银行账户完整性核对，
 * 「科目定位未覆盖」不代表可以不看余额方向。
 */
export function pickNegativeAccounts(
  assigned: readonly AccountLike[],
  unassigned: readonly AccountLike[] = [],
): E1NegativeAccount[] {
  return [...assigned, ...unassigned]
    .filter((r) => isNegativeAmount(r?.closing))
    .map((r) => {
      const code = String(r?.accountCode ?? '')
      const no = String(r?.accountNo ?? '')
      return {
        label: no || code,
        accountCode: code,
        // 🔴 原样保留负值
        closing: num(r?.closing),
      }
    })
}

/** 挑出期末为负的语义槽（账户级合计或叶子合计**任一**为负即命中）。 */
export function pickNegativeSlots(slots: readonly SlotLike[]): E1NegativeSlot[] {
  return (slots ?? [])
    .filter((s) => isNegativeAmount(s?.accountSum) || isNegativeAmount(s?.leafSum))
    .map((s) => ({
      slot: String(s?.slot ?? ''),
      label: String(s?.label ?? s?.slot ?? ''),
      accountSum: num(s?.accountSum),
      leafSum: num(s?.leafSum),
    }))
}

/**
 * 提示文案。
 *
 * 零参调用返回通用文案；传入判定结果时在前面补一句「哪些槽/几个账户为负」，
 * 组件直接渲染返回值即可（模板里**不得**再抄一份文案）。
 */
export function negativeBalanceHint(
  slots: readonly E1NegativeSlot[] = [],
  accounts: readonly E1NegativeAccount[] = [],
): string {
  const parts: string[] = []
  if (slots.length) parts.push(`语义槽（${slots.map((s) => s.label).join('、')}）`)
  if (accounts.length) parts.push(`账户（${accounts.length} 个）`)
  const subject = parts.length ? `存在期末余额为负的${parts.join('与')}。` : ''
  return `${subject}${NEGATIVE_HINT}`
}
