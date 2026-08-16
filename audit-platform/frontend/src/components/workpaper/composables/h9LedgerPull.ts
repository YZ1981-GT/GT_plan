/**
 * h9LedgerPull — H9-2 租赁负债明细从序时账(`tb_ledger`)取数
 *
 * 复用 K8/K9 expenseLedgerMonthlyPull 范式（纯前端游标分页 GET /ledger/entries/{code}）
 * 按出租方(account_name 末段) 聚合贷方增加/借方减少/期末余额
 *
 * 科目方向：租赁负债 贷方/负债类
 *   - 贷方(credit_amount) = 本期增加(利息确认)
 *   - 借方(debit_amount) = 本期偿还(租金支付)
 *   - 期末 = 期初 + 贷方 - 借方
 *
 * 🔴 2026-08-09 纠正（浏览器实测发现）：原实现把序时账科目写死 **`2205`** ——
 *    那是**合同负债**（D7 循环 `BS-047`），不是租赁负债。租赁负债真族是
 *    `2601`（旧族）/ `2651`（新族），且两族在真实库里逐项目互斥
 *    （9 个项目里 5 个用新族）⇒ 按 `2205` 拉取在**任何**项目都取不到租赁负债分录，
 *    只可能取到别的循环的数（该客户若有合同负债则更坏：H9-2 出现 D7 的出租方）。
 *    现改为按 `h9Scope` 的双族兜底码逐码拉取并合并，运行态可由调用方传 render 下发的码。
 *
 * 数据源：GET /api/projects/{pid}/ledger/entries/{code}?year={year}&page=1&page_size=500
 * 按 account_name 末段(出租方名称) 聚合
 *
 * spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/ Task 18
 */
import { api } from '@/services/apiProxy'

import { h9Scope } from './hCycleAccountScope'

export interface H9LedgerRow {
  /** 出租方名称（从 account_name 末段提取） */
  lessor: string
  /** 本期偿还（借方发生额，正数） */
  repayment: number
  /** 本期利息确认（贷方发生额，正数） */
  interestAccrued: number
  /** 合计：期末余额增减净额 = 贷方 - 借方 */
  netChange: number
}

/**
 * 从 account_name 提取出租方名称
 * 如 "2651.01.001 XX物业公司" → "XX物业公司"
 * 或 "租赁负债_XX物业公司" → "XX物业公司"
 */
function _extractLessorName(accountName: string): string {
  if (!accountName) return '未命名'
  const trimmed = accountName.trim()
  // 模式1：科目编码后空格 "2651.01.001 XX物业公司"
  const spaceIdx = trimmed.lastIndexOf(' ')
  if (spaceIdx > 0 && spaceIdx < trimmed.length - 1) {
    return trimmed.slice(spaceIdx + 1)
  }
  // 模式2：下划线分隔 "租赁负债_XX物业公司"
  const underIdx = trimmed.lastIndexOf('_')
  if (underIdx > 0 && underIdx < trimmed.length - 1) {
    return trimmed.slice(underIdx + 1)
  }
  // 模式3：纯名称
  return trimmed
}

/** 租赁负债序时账科目码（双族并取；真源 = 后端 `dual_family_codes.py` 的前端镜像） */
export const H9_LEDGER_ACCOUNT_CODES: readonly string[] = h9Scope.def.slotFallbacks.gross

/**
 * 从序时账拉取租赁负债科目的分录并按出租方聚合。
 *
 * @param projectId 项目ID
 * @param year 审计年度
 * @param codes 科目码（缺省 = 双族兜底码；运行态可传 render 下发的 `tb_source_codes` 码）
 * @returns 按出租方聚合的行（合并同名出租方；多族分录按出租方名合并）
 */
export async function fetchH9LedgerByLessor(
  projectId: string,
  year: number,
  codes: readonly string[] = H9_LEDGER_ACCOUNT_CODES,
): Promise<H9LedgerRow[]> {
  if (!projectId || !year) return []
  // 空码列表时绝不退回写死码（宁缺勿造：本项目无该科目就是没有）
  if (!codes.length) return []

  const aggregation = new Map<string, { repayment: number; interestAccrued: number }>()

  for (const code of codes) {
    let page = 1
    const pageSize = 500
    let hasMore = true

    while (hasMore) {
      try {
        const res = await api.get(`/api/projects/${projectId}/ledger/entries/${code}`, {
          params: { year, page, page_size: pageSize },
          _silent: true,
        } as any)

        const data = res?.data ?? res
        const entries: any[] = Array.isArray(data?.items ?? data)
          ? (data?.items ?? data)
          : []

        if (entries.length === 0) {
          hasMore = false
          break
        }

        for (const entry of entries) {
          const accountName = String(entry.account_name ?? entry.accountName ?? '')
          const lessor = _extractLessorName(accountName)
          const debit = Math.abs(Number(entry.debit_amount ?? entry.debitAmount ?? 0))
          const credit = Math.abs(Number(entry.credit_amount ?? entry.creditAmount ?? 0))

          const existing = aggregation.get(lessor) || { repayment: 0, interestAccrued: 0 }
          // 借方 = 偿还；贷方 = 利息确认
          existing.repayment += debit
          existing.interestAccrued += credit
          aggregation.set(lessor, existing)
        }

        if (entries.length < pageSize) {
          hasMore = false
        } else {
          page += 1
        }
      } catch {
        hasMore = false
      }
    }
  }

  // 转换为结果数组，跳过借贷均为零的空户
  const result: H9LedgerRow[] = []
  for (const [lessor, agg] of aggregation) {
    if (agg.repayment < 0.005 && agg.interestAccrued < 0.005) continue
    result.push({
      lessor,
      repayment: agg.repayment,
      interestAccrued: agg.interestAccrued,
      netChange: agg.interestAccrued - agg.repayment,
    })
  }

  // 按偿还金额降序
  result.sort((a, b) => b.repayment - a.repayment)
  return result
}

/**
 * 将序时账聚合行合并到 H9-2 明细行
 * 同名出租方覆盖偿还/利息金额（仅填空值），新出租方追加行
 *
 * @param existingRows 现有 H9-2 行（按引用只读）
 * @param ledgerRows 序时账聚合行
 * @returns 合并后的新行数组（不修改原数组）
 */
export function mergeH9LedgerRows(
  existingRows: readonly any[],
  ledgerRows: H9LedgerRow[],
): any[] {
  const merged = existingRows.map(r => ({ ...r }))
  const existingNames = new Set(merged.map(r => String(r.lessor || '').trim().toLowerCase()))

  for (const lr of ledgerRows) {
    const nameKey = lr.lessor.trim().toLowerCase()
    const existing = merged.find(r => String(r.lessor || '').trim().toLowerCase() === nameKey)

    if (existing) {
      // 仅填空值（手工已录不覆盖）
      if (!existing.repayment && lr.repayment) existing.repayment = lr.repayment
      if (!existing.interestAccrued && lr.interestAccrued) existing.interestAccrued = lr.interestAccrued
    } else {
      // 新增行
      merged.push({
        lessor: lr.lessor,
        repayment: lr.repayment,
        interestAccrued: lr.interestAccrued,
        contractNo: '',
        assetDesc: '',
        ibrRate: 0,
        leaseTerm: 0,
        beginBalance: 0,
        beginAje: 0,
        repayAje: 0,
        interestAje: 0,
        reclassification: 0,
        dueWithin1Y: 0,
        due1To2Y: 0,
        due2To3Y: 0,
        dueOver3Y: 0,
        isRelatedParty: '否',
        isConfirmed: '否',
        isTerminated: '否',
        terminationDate: '',
        terminatedFromH8: false,
      })
    }
  }

  return merged
}
