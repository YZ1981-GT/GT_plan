/**
 * useH1CrossSheet — H1 固定资产跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('H1-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射：
 * - H1-2 明细 → H1-1 审定（按分类聚合原值/折旧/减值合计）
 * - H1-3 调整 → H1-1 审定（AJE/RJE同步）
 * - H1-12 折旧 → H1-13 分配（按分类聚合折旧额）
 *
 * 注：H1-4 闲置→H1-14 减值改由 EventBus `h1:idle-impairment-sign` 主动预警 + H1-14
 * 自身 parseIdleAssetsFromH4 拉取；附注自动取数改由上市/国企附注 tab 专用 seed。
 * 原 idleAssetsForImpairment / disclosureAutoFill computed 已废弃删除（无消费者）。
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.2
 * Requirements: 17.1-17.9
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { readH12BranchRows } from './h1H12BranchKeys'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** H1-2 明细行原始 JSON 结构 */
export interface H1DetailRowRaw {
  rowId?: string
  category?: string           // 资产分类
  name?: string              // 资产名称
  originalCostBegin?: number // 原值期初
  originalCostIncrease?: number
  originalCostDecrease?: number
  originalCostEnd?: number   // 原值期末
  accDepBegin?: number       // 累计折旧期初
  accDepProvision?: number   // 本期计提
  accDepReversal?: number    // 本期转回
  accDepEnd?: number         // 累计折旧期末
  impairmentBegin?: number   // 减值准备期初
  impairmentProvision?: number
  impairmentReversal?: number
  impairmentEnd?: number     // 减值准备期末
  netValue?: number
}

/** H1-3 调整分录行原始 JSON 结构（对齐 Excel：类别=账项调整/报表调整/其他） */
export interface H1AdjustmentRowRaw {
  rowId?: string
  description?: string       // 调整事项说明
  category?: string          // 账项调整 / 报表调整 / 其他
  entryType?: string         // AJE / RJE（可由 category 派生）
  reportItem?: string
  accountCode?: string
  accountName?: string
  noteItem?: string
  summary?: string
  debitAmount?: number       // 借方调整金额
  creditAmount?: number      // 贷方调整金额
  counterAccount?: string
  indexRef?: string
  remark?: string
}

/** H1-12 折旧测算行原始 JSON 结构 */
export interface H1DepreciationRowRaw {
  rowId?: string
  category?: string          // 资产分类
  originalCost?: number
  salvageRate?: number
  usefulLife?: number
  annualDepreciation?: number
  periodDepreciation?: number  // 本期折旧合计（旧字段）
  periodTotal?: number         // 本期折旧合计（H1-12 新引擎）
  accDepEnd?: number
  bookDepreciation?: number    // 账面折旧
  difference?: number
}

/** 跨sheet详细合计结构 */
export interface DetailTotals {
  originalCost: number
  accDep: number
  impairment: number
}

/** 审定数从明细汇总 */
export interface AdjudicationFromDetail {
  costAudited: number
  depAudited: number
  impairAudited: number
}

/** 折旧分配按分类结构 */
export interface DepreciationForAlloc {
  byCategory: Record<string, number>
  total: number
}

/** 调整分录同步结构 */
export interface AdjustmentSync {
  totalAje: number
  totalRje: number
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
 * 从 allResponses Map 中获取指定 item_id 的 remark，并尝试解析为数值
 */
function _getNumFromMap(map: Map<string, ChecklistItem>, itemId: string): number {
  const item = map.get(itemId)
  if (!item) return 0
  const raw = item.remark ?? item.conclusion
  return _getNum(raw)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1CrossSheet(allResponses: Ref<Map<string, any>>) {
  // ─── 解析 H1-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<H1DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('H1-2-rows')
    return safeParseRows<H1DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 H1-3 调整分录行数据 ──────────────────────────────────────────

  const adjustmentRows = computed<H1AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('H1-3-rows')
    return safeParseRows<H1AdjustmentRowRaw>(resp?.remark)
  })

  // ─── 解析 H1-12 折旧测算行数据（优先活动分支键，兼容旧 H1-12-rows）────

  const depreciationRows = computed<H1DepreciationRowRaw[]>(() => {
    return readH12BranchRows(allResponses.value).rows as H1DepreciationRowRaw[]
  })

  // ─── detailTotals: H1-2 按分类聚合原值/折旧/减值（Req 17.1）───────────

  /**
   * 从 H1-2 明细行聚合合计：
   * - originalCost: 所有行的 originalCostEnd 之和
   * - accDep: 所有行的 accDepEnd 之和
   * - impairment: 所有行的 impairmentEnd 之和
   */
  const detailTotals: ComputedRef<DetailTotals> = computed(() => {
    let originalCost = 0
    let accDep = 0
    let impairment = 0

    for (const row of detailRows.value) {
      // 优先审定口径（对齐源模板与 H1-1 勾稽）
      originalCost += _getNum(row.costEndAud ?? row.originalCostEnd)
      accDep += _getNum(row.depEndAud ?? row.accDepEnd)
      impairment += _getNum(row.impairEndAud ?? row.impairmentEnd)
    }

    return { originalCost, accDep, impairment }
  })

  // ─── adjudicationFromDetail: H1-2 合计 → H1-1（Req 17.1）──────────────

  /**
   * H1-2 明细合计供 H1-1 审定表交叉验证：
   * - costAudited: 原值合计（=H1-1原值小计审定数）
   * - depAudited: 折旧合计（=H1-1折旧小计审定数）
   * - impairAudited: 减值合计（=H1-1减值小计审定数）
   */
  const adjudicationFromDetail: ComputedRef<AdjudicationFromDetail> = computed(() => {
    const totals = detailTotals.value
    return {
      costAudited: totals.originalCost,
      depAudited: totals.accDep,
      impairAudited: totals.impairment,
    }
  })

  // ─── depreciationForAlloc: H1-12 → H1-13 按分类折旧额（Req 17.1）─────

  /**
   * 从 H1-12 折旧测算行按资产分类聚合本期折旧合计，供 H1-13 分配表使用。
   * byCategory: { '房屋建筑物': 120000, '运输设备': 80000, ... }
   * total: 所有分类折旧之和
   */
  const depreciationForAlloc: ComputedRef<DepreciationForAlloc> = computed(() => {
    const byCategory: Record<string, number> = {}
    let total = 0

    for (const row of depreciationRows.value) {
      const cat = row.category || '未分类'
      const amount = _getNum(row.periodTotal ?? row.periodDepreciation)
      byCategory[cat] = (byCategory[cat] || 0) + amount
      total += amount
    }

    return { byCategory, total }
  })

  // ─── adjustmentSync: H1-3 AJE/RJE → H1-1（Req 17.7）──────────────────

  /**
   * 从 H1-3 调整分录汇总 AJE/RJE 合计金额，同步到 H1-1 审定表对应列。
   * - totalAje: 账项调整（或 entryType=AJE）净额（借方-贷方）之和
   * - totalRje: 报表调整（或 entryType=RJE）净额之和
   * 兼容 Excel「类别=账项调整/报表调整/其他」与旧存档 AJE/RJE。
   */
  const adjustmentSync: ComputedRef<AdjustmentSync> = computed(() => {
    let totalAje = 0
    let totalRje = 0

    for (const row of adjustmentRows.value) {
      const debit = _getNum(row.debitAmount)
      const credit = _getNum(row.creditAmount)
      // 资产类借方科目：借方增加/贷方减少 → 净额 = 借方 - 贷方
      const netAmount = debit - credit
      const cat = String(row.category || '').trim()
      const isRje = cat === '报表调整' || row.entryType === 'RJE'
      const isAje = !isRje && (
        cat === '账项调整' || cat === '其他' || cat === '' || row.entryType === 'AJE' || !row.entryType
      )

      if (isRje) {
        totalRje += netAmount
      } else if (isAje) {
        totalAje += netAmount
      }
    }

    return { totalAje, totalRje }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // H1-2 → H1-1 明细合计
    detailTotals,
    // H1-2 合计 → H1-1 审定表交叉验证
    adjudicationFromDetail,
    // H1-12 → H1-13 折旧分配
    depreciationForAlloc,
    // H1-3 → H1-1 AJE/RJE同步
    adjustmentSync,
  }
}

export default useH1CrossSheet
