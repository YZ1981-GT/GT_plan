/**
 * e0RestrictedToE1.ts — E0-3/E0-6 受限标记 → E1 ②表联动纯函数
 *
 * 设计（e0-confirmation-completion §6, R9）：
 * - 来源：E0-3 O列「是否存在冻结、担保或其他使用限制（如是，请注明）」= 是
 *         E0-6 K列「是否被用于担保或存在其他使用限制」= 是
 * - 落点：E1 ②表「受限制的货币资金明细」
 * - 单向：只从 E0 读、只往 E1 写，不反向
 * - 手工优先：E1 侧已有同账号行不被静默覆盖
 * - E0-6 受限行的落点由用户点选（其他货币资金 vs 交易性金融资产等）
 */

/** E0 受限候选行（E0-3 来源） */
export interface E0RestrictedCandidate {
  /** 来源清单标识 */
  source: 'E0-3' | 'E0-6'
  /** E0-3 G列 银行账号 / E0-6 D列 产品名称 */
  accountNo: string
  /** E0-3 D列 开户银行 / E0-6 C列 开户行名称及收件人 */
  bankName: string
  /** E0-3 K列 账户余额（原币）/ E0-6 H列 产品净值 */
  amount: number
  /** E0-3 O列 / E0-6 K列 具体说明文字（「如是，请注明」的内容） */
  reason: string
  /** 索引号 */
  confirmIndex?: string
  /** E0-6 专属：核算科目归属（由用户点选） */
  accountingTarget?: 'other_monetary' | 'financial_asset' | undefined
}

/** E1 侧已有受限行（简化接口，只需 accountNo 做匹配） */
export interface E1RestrictedRowLike {
  accountNo?: string
  bankName?: string
  amount?: number
  reason?: string
}

/** merge plan 结果 */
export interface E0RestrictedMergePlan {
  /** 新增行（E1 侧无同账号行） */
  additions: E0RestrictedCandidate[]
  /** 冲突行（E1 侧已有同账号行且金额不同） */
  conflicts: Array<{ candidate: E0RestrictedCandidate; existing: E1RestrictedRowLike }>
  /** 跳过行（E1 侧已有且金额相同 = 幂等） */
  skipped: E0RestrictedCandidate[]
}

/**
 * 从 E0-3 行集中收集受限候选。
 * @param e03Rows - E0-3 的原始行数据（key=列名）
 */
export function collectE03Restricted(e03Rows: Record<string, unknown>[]): E0RestrictedCandidate[] {
  const result: E0RestrictedCandidate[] = []
  for (const raw of e03Rows) {
    const restricted = String(raw['是否存在冻结、担保或其他使用限制（如是，请注明）'] ?? '').trim()
    if (!restricted || restricted === '否') continue
    const accountNo = String(raw['银行账号'] ?? '').trim()
    if (!accountNo) continue
    result.push({
      source: 'E0-3',
      accountNo,
      bankName: String(raw['开户银行'] ?? '').trim(),
      amount: Number(raw['账户余额（原币）']) || 0,
      reason: restricted === '是' ? '' : restricted, // 「是」无具体说明，否则取实际文字
      confirmIndex: String(raw['索引号'] ?? '').trim() || undefined,
    })
  }
  return result
}

/**
 * 从 E0-6 行集中收集受限候选。
 * @param e06Rows - E0-6 的原始行数据（key=列名）
 */
export function collectE06Restricted(e06Rows: Record<string, unknown>[]): E0RestrictedCandidate[] {
  const result: E0RestrictedCandidate[] = []
  for (const raw of e06Rows) {
    const restricted = String(raw['是否被用于担保或存在其他使用限制'] ?? '').trim()
    if (!restricted || restricted === '否') continue
    const productName = String(raw['产品名称'] ?? '').trim()
    if (!productName) continue
    result.push({
      source: 'E0-6',
      accountNo: productName, // 理财产品的「账号位」= 产品名称
      bankName: String(raw['开户行名称及收件人'] ?? '').trim(),
      amount: Number(raw['产品净值']) || 0,
      reason: restricted === '是' ? '' : restricted,
      confirmIndex: String(raw['索引号'] ?? '').trim() || undefined,
      accountingTarget: undefined, // 待用户点选
    })
  }
  return result
}

/**
 * 规划 E0 受限候选行与 E1 既有行的合并。
 * 手工优先 / 幂等 / 冲突弹确认。
 */
export function planE1RestrictedMerge(
  candidates: readonly E0RestrictedCandidate[],
  existing: readonly E1RestrictedRowLike[],
): E0RestrictedMergePlan {
  const additions: E0RestrictedCandidate[] = []
  const conflicts: E0RestrictedMergePlan['conflicts'] = []
  const skipped: E0RestrictedCandidate[] = []

  const existingByAccount = new Map<string, E1RestrictedRowLike>()
  for (const row of existing) {
    if (row.accountNo) {
      existingByAccount.set(row.accountNo, row)
    }
  }

  for (const candidate of candidates) {
    // E0-6 未指定落点 → 进「待归属」清单，不自动落任一处
    if (candidate.source === 'E0-6' && !candidate.accountingTarget) {
      // 不在 additions/conflicts/skipped 中 → 调用方需单独处理
      continue
    }

    const match = existingByAccount.get(candidate.accountNo)
    if (!match) {
      additions.push(candidate)
    } else if (Math.abs((match.amount ?? 0) - candidate.amount) < 0.01) {
      skipped.push(candidate)
    } else {
      conflicts.push({ candidate, existing: match })
    }
  }

  return { additions, conflicts, skipped }
}

/**
 * 收集需要用户裁决落点的 E0-6 受限行（accountingTarget 未设置）。
 */
export function pendingE06Decisions(candidates: readonly E0RestrictedCandidate[]): E0RestrictedCandidate[] {
  return candidates.filter((c) => c.source === 'E0-6' && !c.accountingTarget)
}
