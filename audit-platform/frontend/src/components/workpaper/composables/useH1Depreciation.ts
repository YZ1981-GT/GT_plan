/**
 * useH1Depreciation — H1-12 折旧测算 composable
 *
 * depreciationBranch状态(A/B/C) + 3分支共用行数据
 * 调用DepreciationEngine计算 + 月度累计 + 差异
 * 从H1-2取数(资产参数) + EventBus发布结果
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.12
 * Requirements: 11.1-11.13
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import {
  calcStraightLine,
  calcDoubleDeclining,
  calcSumOfYears,
  calcUnitsOfProduction,
  calcDepreciationWithImpairment,
  isMonotonicallyIncreasing,
} from './useH1DepreciationEngine'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DepreciationBranch = 'A' | 'B' | 'C'  // A=不含减值直线 B=含减值 C=多次减值

/** 折旧测算行（3分支共用） */
export interface DepreciationRow {
  rowId: string
  category: string                // 资产分类
  originalCost: number            // 原值
  salvageRate: number             // 残值率
  usefulLife: number              // 使用年限(年)
  elapsedMonths: number           // 已使用月数
  depMethod: string               // 折旧方法
  // 计算结果
  monthlyDep: number              // 月折旧额
  monthly: number[]               // 1~12月折旧（数组12项）
  periodTotal: number             // 本期计提合计
  accDepBegin: number             // 累计折旧期初
  accDepEnd: number               // 累计折旧期末
  bookDepreciation: number        // 账面折旧
  difference: number              // 差异
  // B分支: 含减值
  impairmentAmount: number        // 减值准备
  postImpairmentNetValue: number  // 减值后净值
  postImpairmentMonthlyDep: number // 减值后月折旧
  // C分支: 多次减值
  impairmentEvents: ImpairmentEvent[]
}

/** 减值事件（C分支用） */
export interface ImpairmentEvent {
  eventDate: string               // 减值时点
  amount: number                  // 减值金额
  remainingLife: number           // 剩余年限
  newMonthlyDep: number           // 新月折旧
}

/** 折旧汇总 */
export interface DepreciationSummary {
  calculatedTotal: number         // 测算折旧合计
  bookTotal: number               // 账面折旧合计
  totalDifference: number         // 总差异
  diffRate: number                // 差异率(%)
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-12'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Depreciation(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    crossSheetDetailRows?: Ref<any[]>
    onSave?: (itemId: string, value: any) => void
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const branch = ref<DepreciationBranch>('A')
  const rows = ref<DepreciationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const branchItem = allResponses.value.get(`${ITEM_PREFIX}-branch`)
    if (branchItem?.remark) {
      branch.value = (branchItem.remark as DepreciationBranch) || 'A'
    }

    const rowItem = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    if (rowItem?.remark) {
      try {
        const parsed = JSON.parse(rowItem.remark)
        rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow) : []
      } catch { rows.value = [] }
    } else { rows.value = [] }

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): DepreciationRow {
    return {
      rowId: raw.rowId ?? `dep-${Math.random().toString(36).slice(2, 10)}`,
      category: raw.category ?? '',
      originalCost: Number(raw.originalCost) || 0,
      salvageRate: Number(raw.salvageRate) || 0,
      usefulLife: Number(raw.usefulLife) || 0,
      elapsedMonths: Number(raw.elapsedMonths) || 0,
      depMethod: raw.depMethod ?? '直线法',
      monthlyDep: Number(raw.monthlyDep) || 0,
      monthly: Array.isArray(raw.monthly) ? raw.monthly.map(Number) : new Array(12).fill(0),
      periodTotal: Number(raw.periodTotal) || 0,
      accDepBegin: Number(raw.accDepBegin) || 0,
      accDepEnd: Number(raw.accDepEnd) || 0,
      bookDepreciation: Number(raw.bookDepreciation) || 0,
      difference: Number(raw.difference) || 0,
      impairmentAmount: Number(raw.impairmentAmount) || 0,
      postImpairmentNetValue: Number(raw.postImpairmentNetValue) || 0,
      postImpairmentMonthlyDep: Number(raw.postImpairmentMonthlyDep) || 0,
      impairmentEvents: Array.isArray(raw.impairmentEvents) ? raw.impairmentEvents : [],
    }
  }

  // ─── 折旧计算引擎调用 ─────────────────────────────────────────────────────

  function recalcRow(row: DepreciationRow): void {
    const { originalCost, salvageRate, usefulLife, elapsedMonths, depMethod } = row
    const totalMonths = usefulLife * 12
    let monthlyAmt = 0

    switch (depMethod) {
      case '直线法':
        monthlyAmt = calcStraightLine(originalCost, salvageRate, usefulLife)
        break
      case '双倍余额递减法': {
        const netValue = originalCost - row.accDepBegin
        monthlyAmt = calcDoubleDeclining(netValue, usefulLife, elapsedMonths, totalMonths)
        break
      }
      case '年数总和法': {
        const remainYears = usefulLife - Math.floor(elapsedMonths / 12)
        monthlyAmt = calcSumOfYears(originalCost, salvageRate, usefulLife, remainYears)
        break
      }
      case '工作量法':
        // 工作量法需要额外参数，此处保留月折旧不变
        monthlyAmt = row.monthlyDep
        break
      default:
        monthlyAmt = calcStraightLine(originalCost, salvageRate, usefulLife)
    }

    // B分支：含减值后重算
    if (branch.value === 'B' && row.impairmentAmount > 0) {
      const postImpNet = originalCost - row.accDepBegin - row.impairmentAmount
      row.postImpairmentNetValue = postImpNet
      row.postImpairmentMonthlyDep = calcDepreciationWithImpairment(
        originalCost, salvageRate, usefulLife, row.impairmentAmount, elapsedMonths,
      )
      monthlyAmt = row.postImpairmentMonthlyDep
    }

    row.monthlyDep = monthlyAmt
    row.monthly = new Array(12).fill(monthlyAmt)
    row.periodTotal = calcSubtotal(row.monthly)
    row.accDepEnd = row.accDepBegin + row.periodTotal
    row.difference = row.bookDepreciation - row.periodTotal
  }

  /** 批量重算所有行 */
  function recalcAll(): void {
    for (const row of rows.value) {
      recalcRow(row)
    }
    _persist()
  }

  // ─── Computed: 汇总 ────────────────────────────────────────────────────────

  const summary = computed<DepreciationSummary>(() => {
    const calculatedTotal = calcSubtotal(rows.value.map((r) => r.periodTotal))
    const bookTotal = calcSubtotal(rows.value.map((r) => r.bookDepreciation))
    const totalDifference = bookTotal - calculatedTotal
    const diffRate = calculatedTotal > 0 ? (totalDifference / calculatedTotal * 100) : 0
    return { calculatedTotal, bookTotal, totalDifference, diffRate }
  })

  /** 单调性校验：月累计应递增 */
  const monotonicityWarnings = computed(() => {
    return rows.value.filter((row) => {
      const accumulated = row.monthly.reduce<number[]>((acc, val, i) => {
        acc.push((acc[i - 1] ?? 0) + val)
        return acc
      }, [])
      return !isMonotonicallyIncreasing(accumulated, [])
    }).map((r) => r.rowId)
  })

  // ─── updateCell ────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof DepreciationRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    recalcRow(row)
    _persist()
  }

  function setBranch(b: DepreciationBranch): void {
    branch.value = b
    options?.onSave?.(`${ITEM_PREFIX}-branch`, b)
    recalcAll()
  }

  // ─── EventBus: 发布折旧计算结果 ───────────────────────────────────────────

  function publishDepreciationCalculated(): void {
    options?.onPublishEvent?.('h1:depreciation-calculated', {
      wp_code: 'H1',
      branch: branch.value,
      calculatedTotal: summary.value.calculatedTotal,
      byCategory: _aggregateByCategory(),
    })
  }

  function _aggregateByCategory(): Record<string, number> {
    const map: Record<string, number> = {}
    for (const row of rows.value) {
      const cat = row.category || '未分类'
      map[cat] = (map[cat] || 0) + row.periodTotal
    }
    return map
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    branch,
    rows,
    auditNote,
    auditConclusion,
    summary,
    monotonicityWarnings,
    setBranch,
    updateCell,
    recalcRow,
    recalcAll,
    publishDepreciationCalculated,
    saveNote,
    saveConclusion,
  }
}

export default useH1Depreciation
