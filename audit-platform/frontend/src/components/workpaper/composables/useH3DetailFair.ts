/**
 * useH3DetailFair — H3-2 明细表（公允价值模式）composable
 *
 * 列结构对齐源 Excel H3-2（公允价值模式，31列）
 * 区段1: 基本信息（序号/资产名称/类别/位置/面积/取得日期/期初公允）
 * 区段2: 公允变动（增减日期/方式/凭证号/对方科目/本期增加/本期减少/转入/转出/
 *                  公允价值变动/公允价值来源/评估依据/期末公允）
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.7
 * Requirements: 3.1-3.9
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcFairEndBalance, calcSubtotal, calcAuditedAmount } from './useH3FormulaEngine'
import { isStandardH3Category, normalizeH3Category, H3_ASSET_CATEGORIES } from './h3CategoryMap'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailFairRow {
  rowId: string
  seq: number                   // 序号（自动）
  // 区段1: 基本信息
  assetName: string             // 资产名称
  assetType: string             // 类别：房屋及建筑物 / 土地使用权 / 其他
  location: string              // 位置/地址
  area: number                  // 面积(㎡)
  acquireDate: string           // 取得日期
  fairValueBegin: number        // 期初公允价值
  // 区段2: 公允变动
  changeDate: string            // 增减日期
  changeType: string            // 增减方式
  voucherNo: string             // 凭证号
  counterAccount: string        // 对方科目
  fairIncrease: number          // 本期增加
  fairDecrease: number          // 本期减少
  transferIn: number            // 转入
  transferOut: number           // 转出
  fairValueChange: number       // 公允价值变动（正/负均可）
  fairValueSource: string       // 公允价值来源（活跃市场报价/评估机构报告/其他）
  appraisalBasis: string        // 评估依据（市场法/收益法/成本法）
  fairValueEnd: number          // 期末公允（公式）
  // 区段3: 审定调整
  fairUnadj: number             // 公允未审数（默认=期末公允）
  fairAje: number
  fairRje: number
  fairAudited: number           // 公允审定=未审+AJE+RJE
  fvChangeUnadj: number         // 公允变动未审
  fvChangeAje: number
  fvChangeRje: number
  fvChangeAudited: number
  // 披露辅助
  ownershipRestricted: string   // 是否权属受限：是/否
  mortgaged: string             // 是否抵押/质押：是/否
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID = 'H3-2-fair-rows'

export const FAIR_VALUE_SOURCE_OPTIONS = [
  '活跃市场报价', '评估机构报告', '近期交易价格', '参考可比资产', '其他',
]

export const APPRAISAL_BASIS_OPTIONS = ['市场法', '收益法', '成本法', '']

export const FAIR_CHANGE_TYPE_OPTIONS = [
  '购入', '自建完工转入', '自用转投资', '在建转投资',
  '处置', '转为自用', '转出', '公允价值变动', '其他',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH3DetailFair(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const rows = ref<DetailFairRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map((r, i) => _normalize(r, i)) : []
  }

  function _normalize(raw: any, idx = 0): DetailFairRow {
    const begin = Number(raw.fairValueBegin) || 0
    const inc = Number(raw.fairIncrease) || 0
    const dec = Number(raw.fairDecrease) || 0
    const transIn = Number(raw.transferIn) || 0
    const transOut = Number(raw.transferOut) || 0
    const transfer = transIn - transOut
    const change = Number(raw.fairValueChange) || 0
    const end = calcFairEndBalance(begin, inc, dec, transfer, change)
    const fairUnadj = raw.fairUnadj != null ? Number(raw.fairUnadj) || 0 : end
    const fairAje = Number(raw.fairAje) || 0
    const fairRje = Number(raw.fairRje) || 0
    const fairAudited = calcAuditedAmount(fairUnadj, fairAje, fairRje)
    const fvChangeUnadj = raw.fvChangeUnadj != null ? Number(raw.fvChangeUnadj) || 0 : change
    const fvChangeAje = Number(raw.fvChangeAje) || 0
    const fvChangeRje = Number(raw.fvChangeRje) || 0
    const fvChangeAudited = calcAuditedAmount(fvChangeUnadj, fvChangeAje, fvChangeRje)
    return {
      rowId: raw.rowId ?? `df-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? idx + 1,
      assetName: raw.assetName ?? '',
      assetType: String(raw.assetType || raw.category || '').trim() || '其他',
      location: raw.location ?? '',
      area: Number(raw.area) || 0,
      acquireDate: raw.acquireDate ?? '',
      fairValueBegin: begin,
      changeDate: raw.changeDate ?? '',
      changeType: raw.changeType ?? '',
      voucherNo: raw.voucherNo ?? '',
      counterAccount: raw.counterAccount ?? '',
      fairIncrease: inc,
      fairDecrease: dec,
      transferIn: transIn,
      transferOut: transOut,
      fairValueChange: change,
      fairValueSource: raw.fairValueSource ?? '',
      appraisalBasis: raw.appraisalBasis ?? '',
      fairValueEnd: end,
      fairUnadj,
      fairAje,
      fairRje,
      fairAudited,
      fvChangeUnadj,
      fvChangeAje,
      fvChangeRje,
      fvChangeAudited,
      ownershipRestricted: raw.ownershipRestricted ?? '',
      mortgaged: raw.mortgaged ?? '',
      remark: raw.remark ?? '',
    }
  }

  function addRow(assetName: string): void {
    const newRow = _normalize({ assetName, rowId: `df-${Date.now()}` }, rows.value.length)
    rows.value.push(newRow)
    _reseq()
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    _reseq()
    _persist()
  }

  function _reseq(): void {
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function updateCell(rowId: string): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    row.assetType = normalizeH3Category(row.assetType)
    row.area = Number(row.area) || 0
    row.fairValueBegin = Number(row.fairValueBegin) || 0
    row.fairIncrease = Number(row.fairIncrease) || 0
    row.fairDecrease = Number(row.fairDecrease) || 0
    row.transferIn = Number(row.transferIn) || 0
    row.transferOut = Number(row.transferOut) || 0
    row.fairValueChange = Number(row.fairValueChange) || 0
    row.fairUnadj = Number(row.fairUnadj) || 0
    row.fairAje = Number(row.fairAje) || 0
    row.fairRje = Number(row.fairRje) || 0
    row.fvChangeUnadj = Number(row.fvChangeUnadj) || 0
    row.fvChangeAje = Number(row.fvChangeAje) || 0
    row.fvChangeRje = Number(row.fvChangeRje) || 0
    const transfer = row.transferIn - row.transferOut
    row.fairValueEnd = calcFairEndBalance(
      row.fairValueBegin, row.fairIncrease, row.fairDecrease, transfer, row.fairValueChange,
    )
    row.fairAudited = calcAuditedAmount(row.fairUnadj, row.fairAje, row.fairRje)
    row.fvChangeAudited = calcAuditedAmount(row.fvChangeUnadj, row.fvChangeAje, row.fvChangeRje)
    _persist()
  }

  /** 将账面期末/变动带入未审数 */
  function seedUnadjFromBook(): void {
    for (const row of rows.value) {
      row.fairUnadj = row.fairValueEnd
      row.fvChangeUnadj = row.fairValueChange
      row.fairAudited = calcAuditedAmount(row.fairUnadj, row.fairAje, row.fairRje)
      row.fvChangeAudited = calcAuditedAmount(row.fvChangeUnadj, row.fvChangeAje, row.fvChangeRje)
    }
    _persist()
  }

  const subtotal = computed(() => ({
    area: calcSubtotal(rows.value.map((r) => r.area)),
    fairValueBegin: calcSubtotal(rows.value.map((r) => r.fairValueBegin)),
    fairIncrease: calcSubtotal(rows.value.map((r) => r.fairIncrease)),
    fairDecrease: calcSubtotal(rows.value.map((r) => r.fairDecrease)),
    transferIn: calcSubtotal(rows.value.map((r) => r.transferIn)),
    transferOut: calcSubtotal(rows.value.map((r) => r.transferOut)),
    fairValueChange: calcSubtotal(rows.value.map((r) => r.fairValueChange)),
    fairValueEnd: calcSubtotal(rows.value.map((r) => r.fairValueEnd)),
    fairUnadj: calcSubtotal(rows.value.map((r) => r.fairUnadj)),
    fairAje: calcSubtotal(rows.value.map((r) => r.fairAje)),
    fairRje: calcSubtotal(rows.value.map((r) => r.fairRje)),
    fairAudited: calcSubtotal(rows.value.map((r) => r.fairAudited)),
    fvChangeUnadj: calcSubtotal(rows.value.map((r) => r.fvChangeUnadj)),
    fvChangeAje: calcSubtotal(rows.value.map((r) => r.fvChangeAje)),
    fvChangeRje: calcSubtotal(rows.value.map((r) => r.fvChangeRje)),
    fvChangeAudited: calcSubtotal(rows.value.map((r) => r.fvChangeAudited)),
  }))

  /** 按资产类别小计 */
  const categorySubtotals = computed(() => {
    const buckets: Record<string, { fairValueEnd: number; fairValueChange: number; count: number }> = {}
    for (const cat of H3_ASSET_CATEGORIES) buckets[cat] = { fairValueEnd: 0, fairValueChange: 0, count: 0 }

    for (const r of rows.value) {
      const key = normalizeH3Category(r.assetType)
      buckets[key].fairValueEnd += r.fairValueEnd
      buckets[key].fairValueChange += r.fairValueChange
      buckets[key].count += 1
    }

    return Object.entries(buckets)
      .filter(([, v]) => v.count > 0)
      .map(([category, v]) => ({ category, ...v }))
  })

  const unmatchedCategory = computed(() => {
    let unmatchedCount = 0
    let unmatchedEnd = 0
    for (const r of rows.value) {
      if (!isStandardH3Category(r.assetType)) {
        unmatchedCount++
        unmatchedEnd += r.fairValueEnd
      }
    }
    return { unmatchedCount, unmatchedEnd }
  })

  const restrictedCount = computed(() =>
    rows.value.filter((r) => r.ownershipRestricted === '是').length,
  )
  const mortgagedCount = computed(() =>
    rows.value.filter((r) => r.mortgaged === '是').length,
  )

  /** 交叉验证：明细期末公允合计 vs H3-1 公允审定表审定合计 */
  const crossValidationDiff = computed(() => {
    const h31 = getValue('H3-1-fair-rows')
    if (!Array.isArray(h31) || h31.length === 0) return 0
    const h31Audited = h31.reduce((sum: number, r: any) => sum + (Number(r?.audited) || 0), 0)
    const detailSide = subtotal.value.fairAudited || subtotal.value.fairValueEnd
    return detailSide - h31Audited
  })

  function _persist(): void {
    setValue(ITEM_ID, rows.value)
  }

  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    rows,
    subtotal,
    categorySubtotals,
    unmatchedCategory,
    restrictedCount,
    mortgagedCount,
    crossValidationDiff,
    addRow,
    removeRow,
    updateCell,
    seedUnadjFromBook,
    loadRows,
  }
}

export default useH3DetailFair
