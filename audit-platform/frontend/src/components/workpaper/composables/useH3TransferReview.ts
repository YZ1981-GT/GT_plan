/**
 * useH3TransferReview — H3-6 互转审核表 composable
 *
 * 四方向分区(自用→投资/投资→自用/在建→投资/存货→投资)
 * + 转换比例接入公式
 * + selfBookValue / investBookValue 字段分离
 * + H3-5 联动（替代原先无效的 EventBus 直发 H1）
 * + 重要性预警（比率 + 超阈值行列表）
 * + 计量模式切换自动重算
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.11
 * Requirements: 7.1-7.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  calcNetValue,
  applyConversionRatio,
  calcSelfToInvestCost,
  calcSelfToInvestFair,
  calcInvestToSelfFair,
  calcInvestToSelfCost,
  calcCipToInvestCost,
  calcCipToInvestFair,
  calcInventoryToInvestCost,
  calcInventoryToInvestFair,
  calcTransferDiff,
  isAboveMateriality,
  calcTransferRatio,
} from './useH3TransferEngine'
import { calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type TransferDirection =
  | 'selfToInvest'
  | 'investToSelf'
  | 'cipToInvest'
  | 'inventoryToInvest'

export type AssetCategory = 'building' | 'land' | 'cip' | 'inventory' | 'other'

export interface H3TransferRow {
  rowId: string
  direction: TransferDirection
  assetCategory: AssetCategory
  assetName: string
  conversionMethod: string
  transferDate: string
  /** 转换比例（%），100=全额转换，50=50%部分转换 */
  conversionRatio: number
  // 转出方（自用/在建/存货）原始价值 ①②③④
  originalValue: number
  accumulatedDepreciation: number
  impairmentProvision: number
  netValue: number          // ④=①-②-③ (公式)
  // 转入方（投资性房地产）成本模式 ⑤⑥⑦⑧
  investOriginal: number
  investAccumDepr: number
  investImpairment: number
  investNet: number         // ⑧=⑤-⑥-⑦ (公式)
  // 转出方账面净值（已应用比例），用于公允模式OCI/PL计算，不再与投资方账面混用
  selfBookValue: number     // = netValue × conversionRatio / 100
  // 投资方公允价值模式账面 ⑨（与 selfBookValue 完全独立）
  investBookValue: number
  fairValue: number         // ⑩ 转换日公允价值（已应用比例）
  area: number
  refUnitPrice: number
  refPriceSource: string
  // 公式结果
  entryValue: number        // 入账价值（已应用比例）
  ociAmount: number         // 其他综合收益（公允>账面，仅自用→投资公允模式）
  plAmount: number          // 当期损益影响（公允<账面 / 在建/存货→投资公允模式）
  transferOut: number       // 转出方金额（手工填写，用于勾稽验证）
  transferIn: number        // 转入方金额（手工填写，用于勾稽验证）
  transferAmount: number    // 实际转换金额（供H3-5联动及H3-1汇总）
  diff: number              // 转出-转入差额（=0时平衡）
  reason: string
  approvalDoc: string
  sourceWp: string
  sourceRef: string
  remark: string
}

export interface MaterialityWarning {
  rowId: string
  assetName: string
  direction: TransferDirection
  amount: number
}

const ITEM_ID = 'H3-6-transfer-rows'
const ITEM_MATERIALITY = 'H3-6-materiality-threshold'
const ITEM_ASSET_TOTAL = 'H3-6-asset-total'
// H3-5 联动 keys（写入增减检查表，替代原先无效的 EventBus 直发 H1）
const ITEM_H35_TRANSFER_SYNC = 'H3-5-transfer-sync'

export const CATEGORY_LABELS: Record<AssetCategory, string> = {
  building: '房屋、建筑物',
  land: '土地使用权',
  cip: '在建工程',
  inventory: '存货',
  other: '其他',
}

const DEFAULT_METHOD: Record<TransferDirection, string> = {
  selfToInvest: '自用转投资',
  investToSelf: '投资转自用',
  cipToInvest: '在建转投资',
  inventoryToInvest: '存货转投资',
}

const DEFAULT_SOURCE_WP: Record<TransferDirection, string> = {
  selfToInvest: 'H1',
  investToSelf: 'H1',
  cipToInvest: 'H2',
  inventoryToInvest: 'I',
}

export function useH3TransferReview(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
  measurementModel: Ref<string>
}) {
  const { allResponses, getValue, setValue, measurementModel } = params
  const rows = ref<H3TransferRow[]>([])

  // 重要性水平和资产总额（供比率预警使用）
  const materialityThreshold = ref(0)
  const assetTotal = ref(0)

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
    const mt = getValue(ITEM_MATERIALITY)
    if (typeof mt === 'number' && mt > 0) materialityThreshold.value = mt
    const at = getValue(ITEM_ASSET_TOTAL)
    if (typeof at === 'number' && at > 0) assetTotal.value = at
  }

  function saveMeta(): void {
    setValue(ITEM_MATERIALITY, materialityThreshold.value)
    setValue(ITEM_ASSET_TOTAL, assetTotal.value)
  }

  function _num(v: any): number {
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
  }

  function _normalize(raw: any): H3TransferRow {
    const dir: TransferDirection = raw.direction ?? 'selfToInvest'
    const isFair = measurementModel.value === 'fair_value'
    const ratio = _num(raw.conversionRatio) || 100

    // 转出方净值
    const original = _num(raw.originalValue)
    const accDep = _num(raw.accumulatedDepreciation)
    const impairment = _num(raw.impairmentProvision)
    let netFull = calcNetValue(original, accDep, impairment)
    if (netFull === 0 && _num(raw.netValue) !== 0) netFull = _num(raw.netValue)

    // 转入方（投资性房地产）成本模式分解
    const invOrig = _num(raw.investOriginal)
    const invDep = _num(raw.investAccumDepr)
    const invImp = _num(raw.investImpairment)
    let invNet = calcNetValue(invOrig, invDep, invImp)
    if (invNet === 0 && _num(raw.investNet) !== 0) invNet = _num(raw.investNet)

    // 已应用比例的自用方账面（独立字段，不再用 bookValue 混用）
    const selfBook = _num(raw.selfBookValue) || applyConversionRatio(netFull, ratio)
    // 投资方公允模式账面（⑨，完全独立）
    const investBook = _num(raw.investBookValue) || invNet
    // 转换日公允价值（已应用比例存储，录入时直接填写比例后的数值）
    const fair = _num(raw.fairValue)

    let entry = 0
    let oci = 0
    let pl = 0

    if (dir === 'selfToInvest') {
      if (isFair) {
        const r = calcSelfToInvestFair(selfBook, fair || selfBook)
        oci = r.oci
        pl = r.pl
        entry = fair || selfBook
        if (invNet === 0) invNet = selfBook
      } else {
        entry = calcSelfToInvestCost(netFull, ratio)
        if (invOrig === 0 && invDep === 0 && invImp === 0) invNet = entry
      }
    } else if (dir === 'investToSelf') {
      entry = isFair
        ? calcInvestToSelfFair(fair || investBook, ratio)
        : calcInvestToSelfCost(investBook || selfBook, ratio)
    } else if (dir === 'cipToInvest') {
      if (isFair) {
        const r = calcCipToInvestFair(netFull, fair, ratio)
        entry = r.entryValue
        pl = r.diff
      } else {
        entry = calcCipToInvestCost(netFull, ratio)
      }
    } else if (dir === 'inventoryToInvest') {
      if (isFair) {
        const r = calcInventoryToInvestFair(netFull, fair, ratio)
        entry = r.entryValue
        pl = r.pl
      } else {
        entry = calcInventoryToInvestCost(netFull, ratio)
      }
    }

    const out = _num(raw.transferOut)
    const inAmt = _num(raw.transferIn)
    const amount = _num(raw.transferAmount) || out || inAmt || entry

    const category: AssetCategory = raw.assetCategory
      ?? (dir === 'cipToInvest' ? 'cip' : dir === 'inventoryToInvest' ? 'inventory' : 'building')

    return {
      rowId: raw.rowId ?? `tr-${Math.random().toString(36).slice(2, 8)}`,
      direction: dir,
      assetCategory: category,
      assetName: raw.assetName ?? '',
      conversionMethod: raw.conversionMethod ?? DEFAULT_METHOD[dir],
      transferDate: raw.transferDate ?? '',
      conversionRatio: ratio,
      originalValue: original,
      accumulatedDepreciation: accDep,
      impairmentProvision: impairment,
      netValue: netFull,
      investOriginal: invOrig,
      investAccumDepr: invDep,
      investImpairment: invImp,
      investNet: invNet,
      selfBookValue: selfBook,
      investBookValue: investBook,
      fairValue: fair,
      area: _num(raw.area),
      refUnitPrice: _num(raw.refUnitPrice),
      refPriceSource: raw.refPriceSource ?? '',
      entryValue: entry,
      ociAmount: oci,
      plAmount: pl,
      transferOut: out,
      transferIn: inAmt,
      transferAmount: amount,
      diff: calcTransferDiff(out, inAmt),
      reason: raw.reason ?? '',
      approvalDoc: raw.approvalDoc ?? '',
      sourceWp: raw.sourceWp ?? DEFAULT_SOURCE_WP[dir],
      sourceRef: raw.sourceRef ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── 分方向视图 ─────────────────────────────────────────────────────────────
  const selfToInvestRows = computed(() => rows.value.filter((r) => r.direction === 'selfToInvest'))
  const investToSelfRows = computed(() => rows.value.filter((r) => r.direction === 'investToSelf'))
  const cipToInvestRows = computed(() => rows.value.filter((r) => r.direction === 'cipToInvest'))
  const inventoryToInvestRows = computed(() => rows.value.filter((r) => r.direction === 'inventoryToInvest'))

  const hasImbalance = computed(() => rows.value.some((r) => Math.abs(r.diff) > 0.01))

  // ─── 汇总 + 重要性预警 ───────────────────────────────────────────────────────
  const totalSummary = computed(() => {
    const fromH1 = calcSubtotal(selfToInvestRows.value.map((r) => r.transferAmount))
    const toH1 = calcSubtotal(investToSelfRows.value.map((r) => r.transferAmount))
    const fromH2 = calcSubtotal(cipToInvestRows.value.map((r) => r.transferAmount))
    const fromInventory = calcSubtotal(inventoryToInvestRows.value.map((r) => r.transferAmount))
    const totalIn = fromH1 + fromH2 + fromInventory
    const netTransfer = totalIn - toH1
    const ociTotal = calcSubtotal(rows.value.map((r) => r.ociAmount))
    const plTotal = calcSubtotal(rows.value.map((r) => r.plAmount))
    const imbalanceCount = rows.value.filter((r) => Math.abs(r.diff) > 0.01).length

    // 重要性预警
    const mt = materialityThreshold.value
    const materialityWarnings: MaterialityWarning[] = mt > 0
      ? rows.value
          .filter((r) => isAboveMateriality(r.transferAmount, mt))
          .map((r) => ({
            rowId: r.rowId,
            assetName: r.assetName,
            direction: r.direction,
            amount: r.transferAmount,
          }))
      : []

    // 转换金额占资产总额比率
    const at = assetTotal.value
    const transferRatio = calcTransferRatio(totalIn, at)

    return {
      fromH1, toH1, fromH2, fromInventory,
      totalIn, netTransfer,
      ociTotal, plTotal,
      imbalanceCount,
      materialityWarnings,
      transferRatio,
    }
  })

  // ─── CRUD ────────────────────────────────────────────────────────────────────
  function addRow(direction: TransferDirection): void {
    const catMap: Record<TransferDirection, AssetCategory> = {
      selfToInvest: 'building',
      investToSelf: 'building',
      cipToInvest: 'cip',
      inventoryToInvest: 'inventory',
    }
    rows.value.push(_normalize({ direction, assetCategory: catMap[direction], rowId: `tr-${Date.now()}` }))
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(index: number, field: keyof H3TransferRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    ;(row as any)[field] = typeof value === 'number' ? value : (Number(value) || value)
    Object.assign(row, _normalize({ ...row }))
    _persist()
  }

  function updateTransferRow(_direction: string, _index: number, row: any): void {
    const target = row?.rowId ? rows.value.find((r) => r.rowId === row.rowId) : null
    if (!target) return
    Object.assign(target, _normalize({ ...target, ...row }))
    _persist()
  }

  // ─── H3-5 联动（修正：写入增减检查表而非直接发给H1） ──────────────────────────
  /**
   * 将 H3-6 互转事项同步到 H3-5 增减检查表的"转入"/"转出"快照，
   * 供 H3-5 composable 读取，进而由 H3-5→H1/H2 的 EventBus 完成最终联动。
   * 数据格式：{ selfToInvest: [...], investToSelf: [...], cipToInvest: [...], inventoryToInvest: [...] }
   */
  function _syncToH35(): void {
    const snapshot = {
      selfToInvest: selfToInvestRows.value.map((r) => ({
        assetName: r.assetName,
        transferDate: r.transferDate,
        amount: r.transferAmount,
        changeType: '自用转入',
      })),
      investToSelf: investToSelfRows.value.map((r) => ({
        assetName: r.assetName,
        transferDate: r.transferDate,
        amount: r.transferAmount,
        changeType: '转出',
      })),
      cipToInvest: cipToInvestRows.value.map((r) => ({
        assetName: r.assetName,
        transferDate: r.transferDate,
        amount: r.transferAmount,
        changeType: '在建转入',
      })),
      inventoryToInvest: inventoryToInvestRows.value.map((r) => ({
        assetName: r.assetName,
        transferDate: r.transferDate,
        amount: r.transferAmount,
        changeType: '存货转入',
      })),
    }
    setValue(ITEM_H35_TRANSFER_SYNC, snapshot)
  }

  /** @deprecated H3-6 不再直接向 H1/H2 发事件；保留签名供旧调用处兼容 */
  function publishTransferEvents(): void {
    _syncToH35()
  }

  // ─── 持久化 ──────────────────────────────────────────────────────────────────
  function _persist(): void {
    const payload = rows.value.map((r) => ({
      ...r,
      transferAmount: r.transferAmount || r.transferOut || r.transferIn || r.entryValue,
    }))
    setValue(ITEM_ID, payload)
    _syncToH35()
  }

  watch(allResponses, () => loadRows(), { immediate: true })
  watch(measurementModel, () => {
    rows.value = rows.value.map((r) => _normalize({ ...r }))
    _persist()
  })

  return {
    rows,
    selfToInvestRows, investToSelfRows, cipToInvestRows, inventoryToInvestRows,
    hasImbalance, totalSummary, CATEGORY_LABELS,
    materialityThreshold, assetTotal, saveMeta,
    addRow, removeRow, updateCell, updateTransferRow, publishTransferEvents, loadRows,
  }
}

export default useH3TransferReview
