/**
 * useH8CrossSheet — H8 使用权资产跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('H8-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射：
 * - H8-1 审定合计 vs H8-2 明细合计（Req 2.5）
 * - H8 初始计量 vs H9 初始确认（CAS21核心：H8=H9+直接费用-激励，±1元容差）（Req 2.6, 11.1-11.4）
 * - H8-8 折旧合计 vs H8-1 累计折旧本期计提（Req 6.6）
 * - H8-9 分配合计 vs H8-8 折旧合计（费用借方闭环）
 * - H8-3 调整分录 → H8-1 AJE/RJE（1901/1902 净额）
 *
 * 科目：1901使用权资产（借方/资产类）+ 累计折旧（贷方/备抵类）
 * CAS21：H8初始计量 = H9租赁负债初始确认 + 初始直接费用 - 租赁激励
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.2
 * Requirements: 2.5, 2.6, 6.6, 11.1-11.4
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcAssetEndBalance, calcContraEndBalance } from './useH8FormulaEngine'
import { calcInitialMeasurement } from './useH8CAS21Engine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 跨sheet校验结果（通用） */
export interface CrossSheetCheck {
  /** 差额（来源A - 来源B） */
  diff: number
  /** 是否匹配（|diff| < 0.01） */
  isMatch: boolean
}

/** H8-H9联动校验结果 */
export interface H8H9LinkageCheck {
  /** 差额：H8初始计量 - (H9初始确认 + 直接费用 - 激励) 还原后与H9对比 */
  diff: number
  /** 是否一致（CAS21允许±1元尾差容差） */
  isConsistent: boolean
  /** 校验说明消息 */
  message: string
}

/** 按合同号的 H8↔H9 初始计量差额行 */
export interface H8H9ContractVarianceRow {
  contractNo: string
  assetName: string
  h8Initial: number
  h9Initial: number
  directCost: number
  incentive: number
  expected: number
  diff: number
}

/**
 * 按合同号勾稽 H8-2 与 H9-2（或行内 h9Initial）。
 * 仅返回 |diff| > 1 的行（CAS21 尾差容差）。
 */
export function buildH8H9ContractVariance(
  h8Rows: Array<Record<string, any>>,
  h9Rows: Array<Record<string, any>> = [],
): H8H9ContractVarianceRow[] {
  const h9ByContract = new Map<string, number>()
  for (const r of h9Rows) {
    const no = String(r.contractNo || r.contractId || '').trim()
    if (!no) continue
    const amt = _getNum(
      r.auditedBegin ?? r.beginBalance ?? r.h9InitialAmount ?? r.initialLiability ?? r.initialAmount,
    )
    h9ByContract.set(no, (h9ByContract.get(no) || 0) + amt)
  }

  const out: H8H9ContractVarianceRow[] = []
  for (const r of h8Rows) {
    const contractNo = String(r.contractNo || r.contractId || '').trim()
    if (!contractNo) continue
    const directCost = _getNum(r.directCost)
    const incentive = _getNum(r.incentive)
    const h9FromRow = _getNum(r.h9Initial ?? r.h9InitialAmount)
    const h9Initial = h9ByContract.has(contractNo) ? (h9ByContract.get(contractNo) || 0) : h9FromRow
    const h8Initial = _getNum(
      r.initialAmount ?? r.costIncLease ?? r.rouAmount ?? r.costBeginAud,
    )
    const expected = calcInitialMeasurement(h9Initial, directCost, incentive)
    const diff = h8Initial - expected
    if (h9Initial === 0 && h8Initial === 0 && directCost === 0 && incentive === 0) continue
    if (Math.abs(diff) <= 1) continue
    out.push({
      contractNo,
      assetName: String(r.assetName || ''),
      h8Initial,
      h9Initial,
      directCost,
      incentive,
      expected,
      diff,
    })
  }
  return out
}

/** H8-3 → H8-1 调整净额同步 */
export interface H83AdjustmentSync {
  rowCount: number
  /** 1901 使用权资产账项净额（借−贷） */
  rouCostAjeNet: number
  rouCostRjeNet: number
  /** 1902 累计折旧账项净额 */
  rouDepAjeNet: number
  rouDepRjeNet: number
}

/** H8-1 审定表汇总数据 */
export interface H8AdjudicationTotals {
  /** 使用权资产原值审定合计 */
  costAuditedTotal: number
  /** 累计折旧审定合计 */
  depAuditedTotal: number
  /** 原值期初合计 */
  costBeginTotal: number
  /** 原值借方发生合计 */
  costDebitTotal: number
  /** 原值贷方发生合计 */
  costCreditTotal: number
  /** 折旧期初合计 */
  depBeginTotal: number
  /** 折旧借方发生合计（转回/处置） */
  depDebitTotal: number
  /** 折旧贷方发生合计（本期计提） */
  depCreditTotal: number
  /** 折旧本期计提 */
  depCurrentProvision: number
}

/** H8-2 明细行原始 JSON 结构 */
export interface H8DetailRowRaw {
  rowId?: string
  contractNo?: string       // 租赁合同号
  assetName?: string        // 承租资产
  lessor?: string           // 出租方
  startDate?: string        // 起始日
  endDate?: string          // 到期日
  h9Initial?: number        // H9租赁负债初始确认
  directCost?: number       // 初始直接费用
  incentive?: number        // 租赁激励
  initialAmount?: number    // 入账值（H9+直接-激励）
  accDep?: number           // 累计折旧
  currentDep?: number       // 本期计提
  netValue?: number         // 期末净值
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从 allResponses 获取指定 item_id 的数值（存储在 remark 字段）
 * 兼容 remark 为数字串 / JSON 数字 / 对象包一层 value
 */
function _getResponseNum(allResponses: Map<string, any>, itemId: string): number {
  const resp = allResponses.get(itemId)
  if (resp == null) return 0
  if (typeof resp === 'number') return _getNum(resp)
  if (typeof resp === 'string') return _getNum(resp)
  const raw = resp?.remark ?? resp?.conclusion ?? resp?.value
  return _getNum(raw)
}

/** 多键兜底读取数值（按优先级） */
function _getResponseNumAny(allResponses: Map<string, any>, keys: string[]): number {
  for (const k of keys) {
    const n = _getResponseNum(allResponses, k)
    if (n !== 0) return n
  }
  return 0
}

/**
 * 判断差额是否匹配（精度阈值0.01）
 */
function _checkMatch(diff: number): CrossSheetCheck {
  return {
    diff,
    isMatch: Math.abs(diff) < 0.01,
  }
}

function _parseRows(raw: unknown): any[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

function _isRouCostAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1901' || c.startsWith('1901')
}

function _isRouDepAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1902' || c.startsWith('1902')
}

function _isRjeRow(r: any): boolean {
  const cat = String(r?.category || '')
  const et = String(r?.entryType || r?.adjustType || '').toUpperCase()
  return cat === '报表调整' || et === 'RJE' || cat.includes('报表') || cat.includes('重分类')
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8CrossSheet(allResponses: Ref<Map<string, any>>) {
  // ═══════════════════════════════════════════════════════════════════════════
  // 解析各 sheet 行数据（从 allResponses 读取 JSON 行数组）
  // ═══════════════════════════════════════════════════════════════════════════

  /** H8-2 明细行数据 */
  const detailRows = computed<H8DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('H8-2-rows')
    return safeParseRows<H8DetailRowRaw>(resp?.remark)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // H8-1 审定表汇总值（从 allResponses 直接读取汇总 item）
  // ═══════════════════════════════════════════════════════════════════════════

  /** H8-1 审定表各合计值 */
  const adjudicationTotals: ComputedRef<H8AdjudicationTotals> = computed(() => {
    const map = allResponses.value
    return {
      costAuditedTotal: _getResponseNum(map, 'H8-1-cost-audited-total'),
      depAuditedTotal: _getResponseNum(map, 'H8-1-dep-audited-total'),
      costBeginTotal: _getResponseNum(map, 'H8-1-cost-begin-total'),
      costDebitTotal: _getResponseNum(map, 'H8-1-cost-debit-total'),
      costCreditTotal: _getResponseNum(map, 'H8-1-cost-credit-total'),
      depBeginTotal: _getResponseNum(map, 'H8-1-dep-begin-total'),
      depDebitTotal: _getResponseNum(map, 'H8-1-dep-debit-total'),
      depCreditTotal: _getResponseNum(map, 'H8-1-dep-credit-total'),
      depCurrentProvision: _getResponseNum(map, 'H8-1-dep-current-provision'),
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // H8-2 明细表合计
  // ═══════════════════════════════════════════════════════════════════════════

  /** H8-2 明细表入账值合计（从行数据或汇总 item 获取） */
  const detailTotal = computed<number>(() => {
    // 优先从汇总 item 读取（H8-2 组件保存时写入）
    const summaryVal = _getResponseNumAny(allResponses.value, [
      'H8-2-initial-total',
      'H8-2-detail-total',
    ])
    if (summaryVal !== 0) return summaryVal

    // fallback：从明细行聚合入账值 / 原值审定期末
    let total = 0
    for (const row of detailRows.value) {
      total += _getNum(row.initialAmount ?? row.costEndAud ?? row.rouAmount)
    }
    return total
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // H8-8 折旧测算合计
  // ═══════════════════════════════════════════════════════════════════════════

  /** H8-8 折旧测算表本期折旧合计（从汇总 item 获取） */
  const depreciationTotal = computed<number>(() => {
    const primary = _getResponseNum(allResponses.value, 'H8-8-depreciation-total')
    if (primary !== 0) return primary
    return _getResponseNum(allResponses.value, 'H8-8-dep-total')
  })

  /** H8-9 分配合计（优先汇总 item，否则从矩阵行聚合） */
  const allocationTotal = computed<number>(() => {
    const summary = _getResponseNum(allResponses.value, 'H8-9-alloc-total')
    if (summary !== 0) return summary
    const resp = allResponses.value.get('H8-9-alloc-rows')
    const rows = safeParseRows<any>(resp?.remark)
    let total = 0
    for (const r of rows) {
      // 新矩阵
      if (r?.category != null || r?.operatingCost != null || r?.admin != null) {
        total +=
          _getNum(r.operatingCost ?? r.productionCost) +
          _getNum(r.manufacturing) +
          _getNum(r.selling) +
          _getNum(r.admin) +
          _getNum(r.rd) +
          _getNum(r.other)
        continue
      }
      // 旧比例结构
      total += _getNum(r.allocAmount)
    }
    return total
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // H9 租赁负债相关值（从 allResponses 读取 H9 数据）
  // ═══════════════════════════════════════════════════════════════════════════

  /** H9 租赁负债初始确认金额（多键兜底 + H9-2 明细汇总） */
  const h9InitialLiability = computed<number>(() => {
    const map = allResponses.value
    const fromKey = _getResponseNumAny(map, [
      'H9-1-initial-liability',
      'H9-initial-recognition',
      'H8-h9-initial-recognition',
      'H9-1-liability-audited',
    ])
    if (fromKey !== 0) return fromKey
    // fallback：H9-2 明细审定期初 / 期初合计
    const rows = safeParseRows<any>(map.get('H9-2-rows')?.remark)
    let total = 0
    for (const r of rows) {
      total += _getNum(r.auditedBegin ?? r.beginBalance ?? r.h9InitialAmount ?? r.initialLiability)
    }
    return total
  })

  /** H8 初始计量总额（使用权资产入账值，CAS21核心） */
  const h8InitialMeasurement = computed<number>(() => {
    const map = allResponses.value
    const fromKey = _getResponseNumAny(map, [
      'H8-initial-measurement',
      'H8-2-initial-total',
      'H8-6-initial-measurement',
      'H8-1-cost-audited-total',
    ])
    if (fromKey !== 0) return fromKey
    return detailTotal.value
  })

  /** H8 初始直接费用合计 */
  const h8DirectCostTotal = computed<number>(() => {
    const summaryVal = _getResponseNumAny(allResponses.value, [
      'H8-direct-cost-total',
      'H8-6-direct-cost',
    ])
    if (summaryVal !== 0) return summaryVal
    let total = 0
    for (const row of detailRows.value) {
      total += _getNum(row.directCost)
    }
    return total
  })

  /** H8 租赁激励合计 */
  const h8IncentiveTotal = computed<number>(() => {
    const summaryVal = _getResponseNumAny(allResponses.value, [
      'H8-incentive-total',
      'H8-6-incentive',
    ])
    if (summaryVal !== 0) return summaryVal
    let total = 0
    for (const row of detailRows.value) {
      total += _getNum(row.incentive)
    }
    return total
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 1. adjudicationVsDetail — H8-1审定合计 vs H8-2明细合计（Req 2.5）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H8-1 使用权资产原值审定合计 与 H8-2 明细入账值合计 的交叉验证。
   * 两者应一致（diff=0），不一致时显示黄色警告。
   *
   * 公式：diff = H8-1原值审定合计 - H8-2明细入账值合计
   * isMatch: |diff| < 0.01
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheck> = computed(() => {
    const adjTotal = adjudicationTotals.value.costAuditedTotal
    const detTotal = detailTotal.value
    return _checkMatch(adjTotal - detTotal)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. h8VsH9Linkage — H8初始计量 vs H9初始确认（CAS21核心，Req 2.6, 11.1-11.4）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * CAS21核心联动验证：
   * H8使用权资产 = H9租赁负债初始确认 + 初始直接费用 - 租赁激励
   *
   * 验证公式：
   * expected = calcInitialMeasurement(h9Initial, directCost, incentive)
   * diff = H8实际初始计量 - expected
   * isConsistent: |diff| ≤ 1（允许±1元尾差容差，四舍五入差异）
   *
   * 正向验证：H8初始 应等于 H9初始+直接费用-激励
   * 反向验证：H8初始-直接费用+激励 应≈ H9初始
   */
  const h8VsH9Linkage: ComputedRef<H8H9LinkageCheck> = computed(() => {
    const h8Initial = h8InitialMeasurement.value
    const h9Initial = h9InitialLiability.value
    const directCost = h8DirectCostTotal.value
    const incentive = h8IncentiveTotal.value

    // 正向：H8应等于多少？
    const expectedH8 = calcInitialMeasurement(h9Initial, directCost, incentive)
    const diff = h8Initial - expectedH8

    // CAS21允许尾差±1元（实务中四舍五入差异）
    const isConsistent = Math.abs(diff) <= 1

    // 生成校验消息
    let message: string
    if (h9Initial === 0 && h8Initial === 0) {
      message = 'H9租赁负债数据未加载，暂无法校验'
    } else if (isConsistent) {
      message = 'H8与H9联动一致（CAS21：H8=H9+直接费用-激励）'
    } else {
      message = `H8与H9不一致，差额：${diff.toFixed(2)}元，请检查（H8=${h8Initial.toFixed(2)}，H9初始=${h9Initial.toFixed(2)}，直接费用=${directCost.toFixed(2)}，激励=${incentive.toFixed(2)}）`
    }

    return { diff, isConsistent, message }
  })

  /** 按合同号差额（仅 |diff|>1） */
  const h8H9ContractVariance: ComputedRef<H8H9ContractVarianceRow[]> = computed(() => {
    const h9Rows = safeParseRows<any>(allResponses.value.get('H9-2-rows')?.remark)
    return buildH8H9ContractVariance(detailRows.value as any[], h9Rows)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. depreciationVsAdjudication — H8-8折旧合计 vs H8-1累计折旧本期计提（Req 6.6）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H8-8 折旧测算表本期折旧合计 与 H8-1 累计折旧本期计提（贷方发生额）的交叉验证。
   * H8-8 测算的折旧应等于 H8-1 审定表中累计折旧贷方发生额（本期计提）。
   *
   * 公式：diff = H8-8折旧合计 - H8-1累计折旧本期计提
   * isMatch: |diff| < 0.01
   */
  const depreciationVsAdjudication: ComputedRef<CrossSheetCheck> = computed(() => {
    const depTotal = depreciationTotal.value
    const adjDepProvision = adjudicationTotals.value.depCurrentProvision
    return _checkMatch(depTotal - adjDepProvision)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3b. allocationVsDepreciation — H8-9分配合计 vs H8-8折旧合计
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H8-9 费用分配合计应等于 H8-8 本期折旧合计（累计折旧贷方 → 费用借方闭环）。
   * diff = H8-9分配合计 - H8-8折旧合计
   */
  const allocationVsDepreciation: ComputedRef<CrossSheetCheck> = computed(() => {
    return _checkMatch(allocationTotal.value - depreciationTotal.value)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3c. h83AdjustmentSync — H8-3 调整分录 → H8-1 AJE/RJE（1901/1902）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 从 H8-3 调整分录汇总读取 1901/1902 账项/报表净额，供 H8-1 回写。
   * 兼容 Excel「类别=账项调整/报表调整/其他」与旧存档 adjustType AJE/RJE、debit/credit。
   * 优先读 H8-3-rows；若无行则回退 H8-3-aje-net / H8-3-rje-net 等汇总 key。
   */
  const h83AdjustmentSync: ComputedRef<H83AdjustmentSync> = computed(() => {
    const resp = allResponses.value.get('H8-3-rows')
    const rows = _parseRows(resp?.remark ?? resp?.conclusion)
    if (rows.length > 0) {
      let rouCostAjeNet = 0
      let rouCostRjeNet = 0
      let rouDepAjeNet = 0
      let rouDepRjeNet = 0
      for (const r of rows) {
        const debit = _getNum(r.debitAmount ?? r.debit)
        const credit = _getNum(r.creditAmount ?? r.credit)
        const net = debit - credit
        const code = String(r.accountCode || '')
        if (_isRouCostAccount(code)) {
          if (_isRjeRow(r)) rouCostRjeNet += net
          else rouCostAjeNet += net
        }
        if (_isRouDepAccount(code)) {
          if (_isRjeRow(r)) rouDepRjeNet += net
          else rouDepAjeNet += net
        }
      }
      return { rowCount: rows.length, rouCostAjeNet, rouCostRjeNet, rouDepAjeNet, rouDepRjeNet }
    }
    return {
      rowCount: 0,
      rouCostAjeNet: _getResponseNum(allResponses.value, 'H8-3-aje-net'),
      rouCostRjeNet: _getResponseNum(allResponses.value, 'H8-3-rje-net'),
      rouDepAjeNet: _getResponseNum(allResponses.value, 'H8-3-dep-aje-net'),
      rouDepRjeNet: _getResponseNum(allResponses.value, 'H8-3-dep-rje-net'),
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 4. disclosureAutoFill — H8-1 → 附注自动取数
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * 从 H8-1 审定表聚合数据供附注披露自动填充：
   * - disc_cost_audited: 使用权资产原值审定合计
   * - disc_dep_audited: 累计折旧审定合计
   * - disc_cost_begin: 原值期初合计
   * - disc_cost_end: 原值期末合计（calcAssetEndBalance）
   * - disc_dep_begin: 折旧期初合计
   * - disc_dep_end: 折旧期末合计（calcContraEndBalance）
   * - disc_dep_provision: 本期计提折旧
   * - disc_net_value: 净值合计
   * - disc_detail_total: H8-2明细入账值合计
   * - disc_depreciation_total: H8-8折旧测算合计
   */
  const disclosureAutoFill: ComputedRef<Record<string, number>> = computed(() => {
    const adj = adjudicationTotals.value

    // 使用公式引擎计算期末余额
    const costEnd = calcAssetEndBalance(adj.costBeginTotal, adj.costDebitTotal, adj.costCreditTotal)
    const depEnd = calcContraEndBalance(adj.depBeginTotal, adj.depDebitTotal, adj.depCreditTotal)
    const impairAudited = _getResponseNum(allResponses.value, 'H8-1-impair-audited-total')

    return {
      disc_cost_audited: adj.costAuditedTotal,
      disc_dep_audited: adj.depAuditedTotal,
      disc_impair_audited: impairAudited,
      disc_cost_begin: adj.costBeginTotal,
      disc_cost_end: costEnd,
      disc_cost_debit: adj.costDebitTotal,
      disc_cost_credit: adj.costCreditTotal,
      disc_dep_begin: adj.depBeginTotal,
      disc_dep_end: depEnd,
      disc_dep_debit: adj.depDebitTotal,
      disc_dep_credit: adj.depCreditTotal,
      disc_dep_provision: adj.depCurrentProvision,
      disc_net_value: costEnd - depEnd - impairAudited,
      disc_detail_total: detailTotal.value,
      disc_depreciation_total: depreciationTotal.value,
      disc_allocation_total: allocationTotal.value,
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Return
  // ═══════════════════════════════════════════════════════════════════════════

  return {
    // H8-1审定合计 vs H8-2明细合计（Req 2.5）
    adjudicationVsDetail,
    // H8初始计量 vs H9初始确认（CAS21核心，Req 2.6, 11.1-11.4）
    h8VsH9Linkage,
    // 按合同号差额（仅 |diff|>1）
    h8H9ContractVariance,
    // H8-8折旧合计 vs H8-1累计折旧本期计提（Req 6.6）
    depreciationVsAdjudication,
    // H8-9分配合计 vs H8-8折旧合计
    allocationVsDepreciation,
    // H8-3 调整分录 → H8-1 AJE/RJE（1901/1902）
    h83AdjustmentSync,
    // H8-1 → 附注自动取数
    disclosureAutoFill,
    // 中间computed（供子组件直接使用）
    adjudicationTotals,
    detailTotal,
    depreciationTotal,
    allocationTotal,
    h9InitialLiability,
    h8InitialMeasurement,
    h8DirectCostTotal,
    h8IncentiveTotal,
    detailRows,
  }
}

export default useH8CrossSheet
