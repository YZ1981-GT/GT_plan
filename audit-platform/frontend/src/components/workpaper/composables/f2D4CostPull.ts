/**
 * F2 出库结转 ↔ D4 营业成本 跨底稿勾稽
 *
 * 审计意义：存货本期出库（贷方发出）结转形成主营业务成本 6401。
 * F2 明细表出库合计（结转成本）应与利润表/D4 营业成本审定发生额勾稽一致；
 * 差异（超存货账面 × 容差）需查明：出库未结转成本、成本多结转、跨期错配、
 * 委托加工 / 生产领用未纳入等。
 *
 * 数据源（稳健口径）：试算表唯一入口 `fetchTrialBalanceRows`（6401 及其明细科目）
 *   —— 6401 为损益成本类，试算表金额即本期单边发生额（借方）：优先审定数，没有则未审数
 *   （不用余额表借贷：含年末结转分录时两侧相等）。
 *
 * 优雅降级：科目缺失 / 无数据 → status='empty'；请求失败 → status='error'。
 */
import { fetchTrialBalanceRows, tbSumUnder, type TrialBalanceRow } from '@/services/trialBalanceRows'
/** 主营业务成本科目（默认 6401） */
export const OPERATING_COST_ACCOUNT = '6401'

export interface OperatingCostPullResult {
  status: 'ok' | 'empty' | 'error'
  message: string
  /** 6401 主营业务成本审定发生额 */
  operatingCost: number
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 纯函数：从试算表行提取指定科目（及其明细科目）的本期发生额，与报表 TB('6401') 同口径。
 * 损益类试算表金额是单边发生额（成本取借方）：优先审定数之和，没有审定数时回退未审数之和。
 * 原先读端点不返回的 account_code / debit_amount / credit_amount ⇒ 恒 0。
 */
export function extractOperatingCost(rowsRaw: unknown, accountCode = OPERATING_COST_ACCOUNT): number {
  const list = (Array.isArray(rowsRaw) ? rowsRaw : []) as TrialBalanceRow[]
  return tbSumUnder(list, accountCode, 'audited_amount') ?? tbSumUnder(list, accountCode, 'unadjusted_amount') ?? 0
}

/**
 * 拉取同项目 6401 营业成本审定发生额，供 F2 出库结转勾稽。
 * @param projectId 项目 ID
 * @param year 审计年度
 * @param accountCode 成本科目（默认 6401）
 */
export async function pullOperatingCost(
  projectId: string,
  year: number,
  accountCode = OPERATING_COST_ACCOUNT,
): Promise<OperatingCostPullResult> {
  const base: OperatingCostPullResult = { status: 'error', message: '', operatingCost: 0 }
  if (!projectId) return { ...base, message: '缺少 projectId' }
  if (!year || !Number.isFinite(Number(year))) return { ...base, message: '缺少有效审计年度' }

  try {
    const { rows: items } = await fetchTrialBalanceRows(projectId, { year, accountPrefix: accountCode })
    const operatingCost = extractOperatingCost(items, accountCode)
    if (items.length === 0) {
      return { status: 'empty', message: `试算表暂无 ${accountCode} 主营业务成本数据`, operatingCost: 0 }
    }
    if (operatingCost === 0) {
      return {
        status: 'empty',
        message: `${accountCode} 主营业务成本审定发生额为 0，请确认试算表已审定`,
        operatingCost: 0,
      }
    }
    return {
      status: 'ok',
      message: `已取 ${accountCode} 营业成本审定发生额 ${operatingCost.toLocaleString('zh-CN')}`,
      operatingCost,
    }
  } catch (e: any) {
    return { ...base, status: 'error', message: e?.message || '拉取营业成本失败' }
  }
}

export interface CostCarryforwardReconcile {
  /** F2 出库结转合计（发出成本） */
  outboundTotal: number
  /** D4 / 6401 营业成本审定发生额 */
  operatingCost: number
  /** 期末存货账面（结转比对上下文，原值回显） */
  invBalance: number
  diff: number
  /** |diff| ≤ 容差 视为勾稽一致 */
  matched: boolean
  /** 容差 = 存货余额(invBalance) × tolPct，绝对下限 1 元（Req 3.3） */
  tolerance: number
}

/**
 * 纯函数：出库结转 vs 营业成本 勾稽。
 * - diff = outboundTotal − operatingCost
 * - 容差 = 存货余额(invBalance) × tolPct（默认 tolPct=5%，Req 3.3「存货余额的 5%」），
 *   绝对下限 1 元（invBalance 为 0 时避免零容差）
 * - matched = |diff| ≤ 容差
 */
export function buildCostCarryforwardReconcile(
  outboundTotal: number,
  operatingCost: number,
  invBalance: number,
  tolPct = 0.05,
): CostCarryforwardReconcile {
  const ob = parseNum(outboundTotal)
  const oc = parseNum(operatingCost)
  const ib = parseNum(invBalance)
  const diff = ob - oc
  // 容差 = 存货余额(invBalance) × tolPct（Req 3.3「存货余额的 5%」），绝对下限 1 元
  const tolerance = Math.max(Math.abs(ib) * parseNum(tolPct), 1)
  return {
    outboundTotal: ob,
    operatingCost: oc,
    invBalance: ib,
    diff,
    matched: Math.abs(diff) <= tolerance,
    tolerance,
  }
}
