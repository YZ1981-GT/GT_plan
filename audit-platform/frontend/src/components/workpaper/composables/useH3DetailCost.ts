/**
 * useH3DetailCost — H3-2 明细表（成本模式）composable
 *
 * 列结构对齐源 Excel H3-2（成本模式，49列+）
 * 区段1: 基本信息（序号/资产名称/类别/位置/面积/取得日期）
 * 区段2: 增减转换（增减日期/方式/凭证号/对方科目/增减金额/转入/转出/期末原值）
 * 区段3: 折旧减值（折旧期初/本期计提/转回/折旧期末/减值期初/本期减值/减值期末/净值）
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.6
 * Requirements: 3.1-3.9
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal, calcAuditedAmount } from './useH3FormulaEngine'
import { isStandardH3Category, normalizeH3Category } from './h3CategoryMap'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailCostRow {
  rowId: string
  seq: number                 // 序号（自动）
  // 区段1: 基本信息
  assetName: string           // 资产名称
  assetType: string           // 类别：房屋及建筑物 / 土地使用权 / 其他
  location: string            // 位置/地址
  area: number                // 面积(㎡)
  acquireDate: string         // 取得日期
  originalCost: number        // 入账原值
  costBegin: number           // 原值期初
  // 区段2: 增减转换
  changeDate: string          // 增减日期
  changeType: string          // 增减方式（购入/自建转入/自用转入/处置/转出/其他）
  voucherNo: string           // 凭证号
  counterAccount: string      // 对方科目
  costIncrease: number        // 本期增加
  costDecrease: number        // 本期减少
  transferIn: number          // 转入（他科目转入，如H1→H3）
  transferOut: number         // 转出（转出至他科目）
  costEnd: number             // 期末原值（公式：期初+增加-减少+转入-转出）
  // 区段3: 折旧减值
  accDepBegin: number         // 累计折旧期初
  depProvision: number        // 本期计提
  depReversal: number         // 转回
  accDepEnd: number           // 累计折旧期末（公式：期初+计提-转回）
  impairmentBegin: number     // 减值准备期初
  impairmentProvision: number // 本期减值
  impairmentReversal: number  // 减值转回
  impairmentEnd: number       // 减值期末（公式：期初+计提-转回）
  netValue: number            // 净值（公式：期末原值-折旧期末-减值期末）
  // 区段4: 审定调整（未审/AJE/RJE/审定）
  costUnadj: number           // 原值未审数（默认=期末原值）
  costAje: number
  costRje: number
  costAudited: number         // 原值审定=未审+AJE+RJE
  depUnadj: number
  depAje: number
  depRje: number
  depAudited: number
  impairUnadj: number
  impairAje: number
  impairRje: number
  impairAudited: number
  netAudited: number          // 审定净值=原值审定-折旧审定-减值审定
  // 披露辅助
  ownershipRestricted: string // 是否权属受限：是/否
  mortgaged: string           // 是否抵押/质押：是/否
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID = 'H3-2-cost-rows'

export const CHANGE_TYPE_OPTIONS = [
  '购入', '自建完工转入', '自用转投资', '在建转投资',
  '处置', '转为自用', '转出', '其他',
]

export const ASSET_TYPE_OPTIONS = ['房屋及建筑物', '土地使用权', '其他']

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH3DetailCost(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const rows = ref<DetailCostRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map((r, i) => _normalize(r, i)) : []
  }

  function _normalize(raw: any, idx = 0): DetailCostRow {
    const costBegin = Number(raw.costBegin) || 0
    const costInc = Number(raw.costIncrease) || 0
    const costDec = Number(raw.costDecrease) || 0
    const transIn = Number(raw.transferIn) || 0
    const transOut = Number(raw.transferOut) || 0
    const costEnd = costBegin + costInc - costDec + transIn - transOut

    const depBegin = Number(raw.accDepBegin) || 0
    const depProv = Number(raw.depProvision) || 0
    const depRev = Number(raw.depReversal) || 0
    const depEnd = depBegin + depProv - depRev

    const impBegin = Number(raw.impairmentBegin) || 0
    const impProv = Number(raw.impairmentProvision) || 0
    const impRev = Number(raw.impairmentReversal) || 0
    const impEnd = impBegin + impProv - impRev

    const originalCost = Number(raw.originalCost) || costEnd
    const netValue = costEnd - depEnd - impEnd

    const costUnadj = raw.costUnadj != null ? Number(raw.costUnadj) || 0 : costEnd
    const costAje = Number(raw.costAje) || 0
    const costRje = Number(raw.costRje) || 0
    const costAudited = calcAuditedAmount(costUnadj, costAje, costRje)

    const depUnadj = raw.depUnadj != null ? Number(raw.depUnadj) || 0 : depEnd
    const depAje = Number(raw.depAje) || 0
    const depRje = Number(raw.depRje) || 0
    const depAudited = calcAuditedAmount(depUnadj, depAje, depRje)

    const impairUnadj = raw.impairUnadj != null ? Number(raw.impairUnadj) || 0 : impEnd
    const impairAje = Number(raw.impairAje) || 0
    const impairRje = Number(raw.impairRje) || 0
    const impairAudited = calcAuditedAmount(impairUnadj, impairAje, impairRje)
    const netAudited = costAudited - depAudited - impairAudited

    return {
      rowId: raw.rowId ?? `dc-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? idx + 1,
      assetName: raw.assetName ?? '',
      // 保留原始类别文本以便识别「非标准→归入其他」；空则默认其他
      assetType: String(raw.assetType || raw.category || '').trim() || '其他',
      location: raw.location ?? '',
      area: Number(raw.area) || 0,
      acquireDate: raw.acquireDate ?? '',
      originalCost,
      costBegin,
      changeDate: raw.changeDate ?? '',
      changeType: raw.changeType ?? '',
      voucherNo: raw.voucherNo ?? '',
      counterAccount: raw.counterAccount ?? '',
      costIncrease: costInc,
      costDecrease: costDec,
      transferIn: transIn,
      transferOut: transOut,
      costEnd,
      accDepBegin: depBegin,
      depProvision: depProv,
      depReversal: depRev,
      accDepEnd: depEnd,
      impairmentBegin: impBegin,
      impairmentProvision: impProv,
      impairmentReversal: impRev,
      impairmentEnd: impEnd,
      netValue,
      costUnadj,
      costAje,
      costRje,
      costAudited,
      depUnadj,
      depAje,
      depRje,
      depAudited,
      impairUnadj,
      impairAje,
      impairRje,
      impairAudited,
      netAudited,
      ownershipRestricted: raw.ownershipRestricted ?? '',
      mortgaged: raw.mortgaged ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(assetName: string): void {
    const newRow = _normalize({ assetName, rowId: `dc-${Date.now()}` }, rows.value.length)
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

  /**
   * 更新单元格并重算公式列
   */
  function updateCell(rowId: string): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    row.assetType = normalizeH3Category(row.assetType)
    row.area = Number(row.area) || 0
    row.originalCost = Number(row.originalCost) || 0
    row.costBegin = Number(row.costBegin) || 0
    row.costIncrease = Number(row.costIncrease) || 0
    row.costDecrease = Number(row.costDecrease) || 0
    row.transferIn = Number(row.transferIn) || 0
    row.transferOut = Number(row.transferOut) || 0
    row.accDepBegin = Number(row.accDepBegin) || 0
    row.depProvision = Number(row.depProvision) || 0
    row.depReversal = Number(row.depReversal) || 0
    row.impairmentBegin = Number(row.impairmentBegin) || 0
    row.impairmentProvision = Number(row.impairmentProvision) || 0
    row.impairmentReversal = Number(row.impairmentReversal) || 0
    row.costAje = Number(row.costAje) || 0
    row.costRje = Number(row.costRje) || 0
    row.depAje = Number(row.depAje) || 0
    row.depRje = Number(row.depRje) || 0
    row.impairAje = Number(row.impairAje) || 0
    row.impairRje = Number(row.impairRje) || 0
    row.costUnadj = Number(row.costUnadj) || 0
    row.depUnadj = Number(row.depUnadj) || 0
    row.impairUnadj = Number(row.impairUnadj) || 0
    // 重算公式
    row.costEnd = row.costBegin + row.costIncrease - row.costDecrease + row.transferIn - row.transferOut
    row.accDepEnd = row.accDepBegin + row.depProvision - row.depReversal
    row.impairmentEnd = row.impairmentBegin + row.impairmentProvision - row.impairmentReversal
    row.netValue = row.costEnd - row.accDepEnd - row.impairmentEnd
    row.costAudited = calcAuditedAmount(row.costUnadj, row.costAje, row.costRje)
    row.depAudited = calcAuditedAmount(row.depUnadj, row.depAje, row.depRje)
    row.impairAudited = calcAuditedAmount(row.impairUnadj, row.impairAje, row.impairRje)
    row.netAudited = row.costAudited - row.depAudited - row.impairAudited
    _persist()
  }

  /** 将账面期末带入未审数（覆盖已有未审） */
  function seedUnadjFromBook(): void {
    for (const row of rows.value) {
      row.costUnadj = row.costEnd
      row.depUnadj = row.accDepEnd
      row.impairUnadj = row.impairmentEnd
      row.costAudited = calcAuditedAmount(row.costUnadj, row.costAje, row.costRje)
      row.depAudited = calcAuditedAmount(row.depUnadj, row.depAje, row.depRje)
      row.impairAudited = calcAuditedAmount(row.impairUnadj, row.impairAje, row.impairRje)
      row.netAudited = row.costAudited - row.depAudited - row.impairAudited
    }
    _persist()
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotal = computed(() => ({
    area: calcSubtotal(rows.value.map((r) => r.area)),
    originalCost: calcSubtotal(rows.value.map((r) => r.originalCost)),
    costBegin: calcSubtotal(rows.value.map((r) => r.costBegin)),
    costIncrease: calcSubtotal(rows.value.map((r) => r.costIncrease)),
    costDecrease: calcSubtotal(rows.value.map((r) => r.costDecrease)),
    transferIn: calcSubtotal(rows.value.map((r) => r.transferIn)),
    transferOut: calcSubtotal(rows.value.map((r) => r.transferOut)),
    costEnd: calcSubtotal(rows.value.map((r) => r.costEnd)),
    accDepBegin: calcSubtotal(rows.value.map((r) => r.accDepBegin)),
    depProvision: calcSubtotal(rows.value.map((r) => r.depProvision)),
    depReversal: calcSubtotal(rows.value.map((r) => r.depReversal)),
    accDepEnd: calcSubtotal(rows.value.map((r) => r.accDepEnd)),
    impairmentBegin: calcSubtotal(rows.value.map((r) => r.impairmentBegin)),
    impairmentProvision: calcSubtotal(rows.value.map((r) => r.impairmentProvision)),
    impairmentReversal: calcSubtotal(rows.value.map((r) => r.impairmentReversal)),
    impairmentEnd: calcSubtotal(rows.value.map((r) => r.impairmentEnd)),
    netValue: calcSubtotal(rows.value.map((r) => r.netValue)),
    costUnadj: calcSubtotal(rows.value.map((r) => r.costUnadj)),
    costAje: calcSubtotal(rows.value.map((r) => r.costAje)),
    costRje: calcSubtotal(rows.value.map((r) => r.costRje)),
    costAudited: calcSubtotal(rows.value.map((r) => r.costAudited)),
    depUnadj: calcSubtotal(rows.value.map((r) => r.depUnadj)),
    depAje: calcSubtotal(rows.value.map((r) => r.depAje)),
    depRje: calcSubtotal(rows.value.map((r) => r.depRje)),
    depAudited: calcSubtotal(rows.value.map((r) => r.depAudited)),
    impairUnadj: calcSubtotal(rows.value.map((r) => r.impairUnadj)),
    impairAje: calcSubtotal(rows.value.map((r) => r.impairAje)),
    impairRje: calcSubtotal(rows.value.map((r) => r.impairRje)),
    impairAudited: calcSubtotal(rows.value.map((r) => r.impairAudited)),
    netAudited: calcSubtotal(rows.value.map((r) => r.netAudited)),
  }))

  /** 非标准类别（导入自由文本等）行数与原值期末合计 */
  const unmatchedCategory = computed(() => {
    let unmatchedCount = 0
    let unmatchedEnd = 0
    for (const r of rows.value) {
      if (!isStandardH3Category(r.assetType)) {
        unmatchedCount++
        unmatchedEnd += r.costEnd
      }
    }
    return { unmatchedCount, unmatchedEnd }
  })

  /** 按资产类别小计（房屋及建筑物 / 土地使用权 / 其他） */
  const categorySubtotals = computed(() => {
    const buckets: Record<string, { costEnd: number; accDepEnd: number; impairmentEnd: number; netValue: number; count: number }> = {}
    for (const cat of ASSET_TYPE_OPTIONS) {
      buckets[cat] = { costEnd: 0, accDepEnd: 0, impairmentEnd: 0, netValue: 0, count: 0 }
    }

    for (const r of rows.value) {
      const key = normalizeH3Category(r.assetType)
      buckets[key].costEnd += r.costEnd
      buckets[key].accDepEnd += r.accDepEnd
      buckets[key].impairmentEnd += r.impairmentEnd
      buckets[key].netValue += r.netValue
      buckets[key].count += 1
    }

    return Object.entries(buckets)
      .filter(([, v]) => v.count > 0)
      .map(([category, v]) => ({ category, ...v }))
  })

  const restrictedCount = computed(() =>
    rows.value.filter((r) => r.ownershipRestricted === '是').length,
  )
  const mortgagedCount = computed(() =>
    rows.value.filter((r) => r.mortgaged === '是').length,
  )

  // ─── 交叉验证：明细期末原值合计 vs H3-1 审定表原值审定合计 ──────────────────

  const crossValidationDiff = computed(() => {
    const h31 = getValue('H3-1-cost-original-rows')
    if (!Array.isArray(h31) || h31.length === 0) return 0
    const h31Audited = h31.reduce((sum: number, r: any) => sum + (Number(r?.audited) || 0), 0)
    // 优先用明细审定原值合计勾稽；无审定数据时回退账面期末
    const detailSide = subtotal.value.costAudited || subtotal.value.costEnd
    return detailSide - h31Audited
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    setValue(ITEM_ID, rows.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

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

export default useH3DetailCost
