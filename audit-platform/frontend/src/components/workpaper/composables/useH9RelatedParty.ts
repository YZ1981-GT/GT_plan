/**
 * useH9RelatedParty — H9-6 关联方筛选视图 composable
 *
 * 从H9-2(S列="是")和H9-3(T列="是")过滤出关联方租赁：
 * 合同号 | 出租方 | 关联关系 | 年租金 | 市场租金 | 价差率 | 备注
 *
 * 功能：
 * - 从H9-2/H9-3自动筛选关联方行
 * - 价差率自动计算 = (年租金-市场租金)/市场租金×100%
 * - 价差率>10%红色高亮标记
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 3.4
 * Requirements: 5.2-5.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcPriceDiffRate, calcSubtotal } from './useH9FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H9-6 关联方行 */
export interface H9RelatedPartyRow {
  rowId: string
  /** 合同号 */
  contractNo: string
  /** 出租方 */
  lessor: string
  /** 关联关系描述 */
  relationship: string
  /** 来源：H9-2(租赁负债明细)/H9-3(融资费用明细) */
  source: 'H9-2' | 'H9-3'
  /** 年租金(实际) */
  actualRent: number
  /** 市场租金(可比) */
  marketRent: number
  /** 价差率(%) */
  priceDiffRate: number
  /** 是否异常（价差率>10%） */
  isAbnormal: boolean
  /** 租赁期 */
  leaseTerm: number
  /** 负债余额(期末) */
  liabilityBalance: number
  /** 备注 */
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H9-6-rows'
const DIFF_THRESHOLD = 10 // 价差率阈值10%

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9RelatedParty(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H9RelatedPartyRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any): H9RelatedPartyRow {
    const actual = Number(raw.actualRent) || 0
    const market = Number(raw.marketRent) || 0
    const rate = calcPriceDiffRate(actual, market)

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      contractNo: raw.contractNo ?? '',
      lessor: raw.lessor ?? '',
      relationship: raw.relationship ?? '',
      source: raw.source === 'H9-3' ? 'H9-3' : 'H9-2',
      actualRent: actual,
      marketRent: market,
      priceDiffRate: rate,
      isAbnormal: Math.abs(rate) > DIFF_THRESHOLD,
      leaseTerm: Number(raw.leaseTerm) || 0,
      liabilityBalance: Number(raw.liabilityBalance) || 0,
      remark: raw.remark ?? '',
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    // 优先从自身持久化数据加载
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
      return
    }
    // 否则从H9-2和H9-3自动筛选关联方
    _syncFromDetails()
  }

  /** 从H9-2(S列=是)和H9-3(T列=是)自动筛选关联方 */
  function _syncFromDetails(): void {
    const autoRows: H9RelatedPartyRow[] = []

    // 从H9-2筛选
    const h9DetailData = _getJson('H9-2-rows')
    if (Array.isArray(h9DetailData)) {
      h9DetailData
        .filter((r: any) => r.isRelatedParty === '是')
        .forEach((r: any) => {
          autoRows.push(_normalizeRow({
            contractNo: r.contractNo,
            lessor: r.lessor,
            source: 'H9-2',
            leaseTerm: r.leaseTerm,
            liabilityBalance: r.endBalance || r.beginBalance,
          }))
        })
    }

    // 从H9-3筛选
    const h9FinanceData = _getJson('H9-3-rows')
    if (Array.isArray(h9FinanceData)) {
      h9FinanceData
        .filter((r: any) => r.isRelatedParty === '是')
        .forEach((r: any) => {
          // 避免重复（已从H9-2加入的合同号不再重复添加）
          const exists = autoRows.some(existing => existing.contractNo === r.contractNo)
          if (!exists) {
            autoRows.push(_normalizeRow({
              contractNo: r.contractNo,
              lessor: r.lessor,
              source: 'H9-3',
            }))
          }
        })
    }

    rows.value = autoRows
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 筛选视图 ────────────────────────────────────────────────────

  /** 关联方行（已包含价差率） */
  const relatedPartyRows: ComputedRef<H9RelatedPartyRow[]> = computed(() => rows.value)

  /** 异常行（价差率>10%） */
  const abnormalRows: ComputedRef<H9RelatedPartyRow[]> = computed(() =>
    rows.value.filter(r => r.isAbnormal),
  )

  /** 关联方租赁负债合计 */
  const totalLiability: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.liabilityBalance)),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const textFields = ['contractNo', 'lessor', 'relationship', 'remark']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    const numVal = Number(value) || 0
    switch (field) {
      case 'actualRent': row.actualRent = numVal; break
      case 'marketRent': row.marketRent = numVal; break
      case 'leaseTerm': row.leaseTerm = numVal; break
      case 'liabilityBalance': row.liabilityBalance = numVal; break
      default: return
    }

    // 重算价差率
    row.priceDiffRate = calcPriceDiffRate(row.actualRent, row.marketRent)
    row.isAbnormal = Math.abs(row.priceDiffRate) > DIFF_THRESHOLD
    _persist()
  }

  /** 手动刷新：从H9-2/H9-3重新筛选 */
  function refreshFromDetails(): void {
    _syncFromDetails()
    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId, contractNo: r.contractNo, lessor: r.lessor,
      relationship: r.relationship, source: r.source,
      actualRent: r.actualRent, marketRent: r.marketRent,
      leaseTerm: r.leaseTerm, liabilityBalance: r.liabilityBalance, remark: r.remark,
    }))
    onSave(ROWS_KEY, toPersist)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, relatedPartyRows, abnormalRows, totalLiability,
    updateCell, refreshFromDetails, save, load,
  }
}

export default useH9RelatedParty
