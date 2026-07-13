/**
 * useK6GroupImpairment — K6-6 处置组减值测试（55行，13公式）
 *
 * Spec: .kiro/specs/k6-held-for-sale/
 * Task: 3.4
 * Requirements: 6.1-6.4
 *
 * 职责：
 * - 管理处置组减值测试行：处置组/组内资产/账面价值/组整体减值/
 *   分摊比例(公式)/分摊减值(公式)/分摊后账面/结论
 * - 处置组减值：先抵减商誉→余额按比例分摊至组内非流动资产
 * - 分摊比例 = 组内资产账面 / 组账面合计
 * - 动态行+与K6-5联动
 * - JSON打包存储
 *
 * Prefix: "K6-6-"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAllocationRatio,
  calcFairValueNet,
  calcImpairment,
  calcAdditionalProvision,
} from './useK6ImpairmentEngine'
import { calcSubtotal } from './useK6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** Part (一) 处置组减值测算行（对齐源模板：孰低法计算处置组应计提减值） */
export interface K6GroupMeasurementRow {
  rowId: string
  seqNo: number
  groupName: string            // 持有待售的处置组（子公司A/分公司B）
  bookValue: number            // 账面价值
  fairValue: number            // 公允价值
  fairValueBasis: string       // 公允价值确定依据
  sellingCost: number          // 出售费用
  fairValueNet: number         // 公允价值减出售费用后净额（公式）
  impairmentProvision: number  // 应计提减值准备（公式：MAX(0, 账面-净额)）
  existingProvision: number    // 账面期末减值准备
  additionalProvision: number  // 应补提或转回的减值准备（公式）
  remark: string
}

export interface K6GroupImpairmentRow {
  rowId: string
  seqNo: number
  groupName: string          // 处置组名称
  assetName: string          // 组内资产名称
  isGoodwill: boolean        // 是否为商誉
  bookValue: number          // 账面价值
  allocationRatio: number    // 分摊比例（公式）
  allocatedImpairment: number // 分摊减值金额（公式）
  bookAfterImpairment: number // 分摊后账面价值
  conclusion: string
  remark: string
}

export interface K6GroupImpairmentSummary {
  groupName: string
  groupBookTotal: number         // 组账面合计
  goodwillBook: number           // 组内商誉账面
  groupBookExGoodwill: number    // 组账面合计（不含商誉）
  groupImpairment: number        // 组整体减值金额
  goodwillDeduction: number      // 商誉抵减金额
  remainingAllocation: number    // 分摊至非流动资产的余额
}

export interface UseK6GroupImpairmentParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K6-6-rows'
const ITEM_ID_GROUP_META = 'K6-6-group-meta'
const ITEM_ID_MEASUREMENT = 'K6-6-measurement-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVal(map: Map<string, any>, itemId: string): string {
  const item = map.get(itemId)
  if (!item) return ''
  return item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK6GroupImpairment(params: UseK6GroupImpairmentParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const groupRows = ref<K6GroupImpairmentRow[]>([])
  /** 组整体减值金额（从K6-5联动或手动录入） */
  const groupImpairmentAmount = ref(0)
  const auditConclusion = ref('')

  // Part (一) 处置组减值测算行
  const measurementRows = ref<K6GroupMeasurementRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { groupRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        groupRows.value = parsed.map(_normalizeRow)
      } else {
        groupRows.value = []
      }
    } catch {
      groupRows.value = []
    }

    // 加载组元数据
    const metaItem = allResponses.value.get(ITEM_ID_GROUP_META)
    const metaRaw = metaItem?.remark ?? metaItem?.conclusion ?? ''
    if (metaRaw) {
      try {
        const meta = JSON.parse(metaRaw)
        groupImpairmentAmount.value = Number(meta.groupImpairment) || 0
      } catch { /* ignore */ }
    }

    // 加载 Part(一) 减值测算行
    const mItem = allResponses.value.get(ITEM_ID_MEASUREMENT)
    const mRaw = mItem?.remark ?? mItem?.conclusion ?? (typeof mItem === 'string' ? mItem : null)
    if (mRaw) {
      try {
        const parsed = JSON.parse(mRaw)
        measurementRows.value = Array.isArray(parsed) ? parsed.map(_normalizeMeasurementRow) : []
      } catch { measurementRows.value = [] }
    } else {
      measurementRows.value = []
    }
  }

  function _normalizeMeasurementRow(raw: any, idx?: number): K6GroupMeasurementRow {
    const bookValue = Number(raw.bookValue) || 0
    const fairValue = Number(raw.fairValue) || 0
    const sellingCost = Number(raw.sellingCost) || 0
    const fairValueNet = calcFairValueNet(fairValue, sellingCost)
    const impairmentProvision = calcImpairment(bookValue, fairValueNet)
    const existingProvision = Number(raw.existingProvision) || 0
    const additionalProvision = calcAdditionalProvision(impairmentProvision, existingProvision)
    return {
      rowId: raw.rowId ?? `m-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      groupName: raw.groupName ?? '',
      bookValue,
      fairValue,
      fairValueBasis: raw.fairValueBasis ?? '',
      sellingCost,
      fairValueNet,
      impairmentProvision,
      existingProvision,
      additionalProvision,
      remark: raw.remark ?? '',
    }
  }

  function _recalcMeasurementRow(row: K6GroupMeasurementRow): void {
    row.fairValueNet = calcFairValueNet(row.fairValue, row.sellingCost)
    row.impairmentProvision = calcImpairment(row.bookValue, row.fairValueNet)
    row.additionalProvision = calcAdditionalProvision(row.impairmentProvision, row.existingProvision)
  }

  function _normalizeRow(raw: any, idx?: number): K6GroupImpairmentRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      groupName: raw.groupName ?? '',
      assetName: raw.assetName ?? '',
      isGoodwill: raw.isGoodwill === true,
      bookValue: Number(raw.bookValue) || 0,
      allocationRatio: Number(raw.allocationRatio) || 0,
      allocatedImpairment: Number(raw.allocatedImpairment) || 0,
      bookAfterImpairment: Number(raw.bookAfterImpairment) || 0,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── 计算处置组摘要（Req 6.2：先抵商誉再按比例分摊） ─────────────────────

  const groupSummary: ComputedRef<K6GroupImpairmentSummary> = computed(() => {
    const rows = groupRows.value
    const goodwillRows = rows.filter(r => r.isGoodwill)
    const nonGoodwillRows = rows.filter(r => !r.isGoodwill)

    const groupBookTotal = calcSubtotal(rows.map(r => r.bookValue))
    const goodwillBook = calcSubtotal(goodwillRows.map(r => r.bookValue))
    const groupBookExGoodwill = calcSubtotal(nonGoodwillRows.map(r => r.bookValue))

    // 先抵商誉
    const goodwillDeduction = Math.min(groupImpairmentAmount.value, goodwillBook)
    const remainingAllocation = Math.max(0, groupImpairmentAmount.value - goodwillDeduction)

    return {
      groupName: rows[0]?.groupName ?? '',
      groupBookTotal,
      goodwillBook,
      groupBookExGoodwill,
      groupImpairment: groupImpairmentAmount.value,
      goodwillDeduction,
      remainingAllocation,
    }
  })

  // ─── Recalc（逐行计算分摊比例+分摊减值） ──────────────────────────────────

  function recalcAll(): void {
    const summary = groupSummary.value
    for (const row of groupRows.value) {
      if (row.isGoodwill) {
        // 商誉行：减值 = 商誉抵减金额（全额或部分）
        row.allocationRatio = 0
        row.allocatedImpairment = summary.goodwillDeduction
        row.bookAfterImpairment = row.bookValue - row.allocatedImpairment
      } else {
        // 非流动资产行：按比例分摊
        row.allocationRatio = calcAllocationRatio(row.bookValue, summary.groupBookExGoodwill)
        row.allocatedImpairment = summary.remainingAllocation * row.allocationRatio
        row.bookAfterImpairment = row.bookValue - row.allocatedImpairment
      }
    }
  }

  // ─── 已分摊减值合计（computed） ────────────────────────────────────────────

  const allocatedTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(groupRows.value.map(r => r.allocatedImpairment))
  })

  // ─── Part(一) 减值测算小计 ────────────────────────────────────────────────

  const measurementSubtotals: ComputedRef<{
    bookValue: number; fairValueNet: number; impairmentProvision: number
    existingProvision: number; additionalProvision: number; count: number
  }> = computed(() => {
    const r = measurementRows.value
    return {
      bookValue: calcSubtotal(r.map(x => x.bookValue)),
      fairValueNet: calcSubtotal(r.map(x => x.fairValueNet)),
      impairmentProvision: calcSubtotal(r.map(x => x.impairmentProvision)),
      existingProvision: calcSubtotal(r.map(x => x.existingProvision)),
      additionalProvision: calcSubtotal(r.map(x => x.additionalProvision)),
      count: r.length,
    }
  })

  // ─── 勾稽一致：Part(一)应计提减值合计 vs Part(二)已分摊合计 ────────────────

  const reconciliation: ComputedRef<{ measurement: number; allocated: number; diff: number; isBalanced: boolean }> = computed(() => {
    const measurement = measurementSubtotals.value.impairmentProvision
    const allocated = allocatedTotal.value
    const diff = Math.round((measurement - allocated) * 100) / 100
    return { measurement, allocated, diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── Part(一) 减值测算 CRUD ───────────────────────────────────────────────

  function updateMeasurementCell(rowId: string, field: string, value: any): void {
    const row = measurementRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcMeasurementRow(row)
    _persist()
  }

  async function addMeasurementRow(groupName?: string): Promise<void> {
    let name = groupName
    if (!name) {
      try {
        const { ElMessageBox } = await import('element-plus')
        const { value } = await ElMessageBox.prompt('请输入处置组名称', '新增处置组减值测算', {
          confirmButtonText: '确定', cancelButtonText: '取消',
          inputPlaceholder: '例如：子公司A / 分公司B',
          inputValidator: (val: string) => (!val?.trim() ? '名称不能为空' : true),
        })
        name = value?.trim()
      } catch { return }
    }
    if (!name) return
    measurementRows.value.push(_normalizeMeasurementRow({ groupName: name }, measurementRows.value.length))
    measurementRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  function removeMeasurementRow(idx: number): void {
    if (idx < 0 || idx >= measurementRows.value.length) return
    measurementRows.value.splice(idx, 1)
    measurementRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  /** 将 Part(一) 应计提减值合计设为组整体减值金额，驱动 Part(二) 分摊 */
  function syncMeasurementToAllocation(): void {
    setGroupImpairment(measurementSubtotals.value.impairmentProvision)
  }

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = groupRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    recalcAll()
    _persist()
  }

  // ─── 更新组整体减值金额 ───────────────────────────────────────────────────

  function setGroupImpairment(amount: number): void {
    groupImpairmentAmount.value = amount
    recalcAll()
    _persist()
  }

  // ─── Dynamic Row Add ───────────────────────────────────────────────────────

  async function addRow(assetName?: string): Promise<void> {
    let name = assetName
    if (!name) {
      try {
        const { ElMessageBox } = await import('element-plus')
        const { value } = await ElMessageBox.prompt(
          '请输入组内资产名称',
          '新增处置组资产',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX子公司固定资产',
            inputValidator: (val) => (!val?.trim() ? '名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return
      }
    }
    if (!name) return

    const newRow: K6GroupImpairmentRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: groupRows.value.length + 1,
      groupName: groupRows.value[0]?.groupName ?? '',
      assetName: name,
      isGoodwill: false,
      bookValue: 0,
      allocationRatio: 0,
      allocatedImpairment: 0,
      bookAfterImpairment: 0,
      conclusion: '',
      remark: '',
    }
    groupRows.value.push(newRow)
    recalcAll()
    _persist()
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= groupRows.value.length) return
    groupRows.value.splice(idx, 1)
    groupRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    recalcAll()
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    groupRows.value = data.map((raw, i) => _normalizeRow(raw, i))
    recalcAll()
    _persist()
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(groupRows.value) })
    saveResponse(ITEM_ID_MEASUREMENT, { remark: JSON.stringify(measurementRows.value) })
    saveResponse(ITEM_ID_GROUP_META, {
      remark: JSON.stringify({
        groupImpairment: groupImpairmentAmount.value,
      }),
    })
    saveResponse('K6-6-allocated-total', { remark: String(allocatedTotal.value) })
  }

  // ─── Save Conclusion ───────────────────────────────────────────────────────

  async function saveConclusion(): Promise<void> {
    await saveResponse('K6-6-audit-conclusion', { remark: auditConclusion.value })
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => {
    _loadRows()
    recalcAll()
    const val = allResponses.value.get('K6-6-audit-conclusion')
    auditConclusion.value = val?.remark ?? val?.conclusion ?? ''
  }, { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // Part(二) 分摊
    groupRows,
    groupImpairmentAmount,
    groupSummary,
    allocatedTotal,
    updateCell,
    setGroupImpairment,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    // Part(一) 减值测算
    measurementRows,
    measurementSubtotals,
    updateMeasurementCell,
    addMeasurementRow,
    removeMeasurementRow,
    syncMeasurementToAllocation,
    // 勾稽
    reconciliation,
    auditConclusion,
    saveConclusion,
  }
}
