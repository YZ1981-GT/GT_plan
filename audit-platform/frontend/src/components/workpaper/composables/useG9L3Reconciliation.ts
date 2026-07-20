/**
 * useG9L3Reconciliation — G9-5 第三层次调节表（10 因子）
 *
 * 编制逻辑：对 Level3 资产逐项调节期初→期末；公式期末与企业报告勾稽；
 * 可从 G9-2（Level3 明细变动）/ G9-4（审定 FV）带入，减少手工录入。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum, calcL3Reconciliation, calcL3Variance, calcSubtotal } from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G9L3Row {
  rowId: string
  seq: number
  assetName: string
  openingFairValue: number
  purchaseAmount: number
  disposalAmount: number
  transferIn: number
  transferOut: number
  fvChangePL: number
  fvChangeOCI: number
  interestIncome: number
  impairmentLoss: number
  otherChanges: number
  /** 报告期末仍持有资产计入损益的当期未实现变动（CAS 39 披露项，不进期末公式） */
  unrealizedHeld: number
  reportedClosing: number
  /** 层次转入/转出原因、差异说明等 */
  remark?: string
  conclusion?: string
}

export type G9L3EnrichedRow = G9L3Row & {
  closingFairValue: number
  variance: number
  varianceHighlight: boolean
}

export interface G9UnrealizedHeldWarning {
  rowId: string
  assetName: string
  reason: string
}

/** 仍持有未实现合理性软校验（返回原因；无问题返回 null） */
export function checkG9UnrealizedHeld(r: {
  unrealizedHeld: number
  fvChangePL: number
  closingFairValue: number
}): string | null {
  const uh = parseNum(r.unrealizedHeld)
  const gainPl = parseNum(r.fvChangePL)
  const closing = parseNum(r.closingFairValue)
  if (Math.abs(uh) < 0.01) {
    if (Math.abs(closing) > 0.01 && Math.abs(gainPl) > 0.01) {
      return '有期末余额及 FV 损益变动，但未填仍持有未实现（请确认是否均为已实现）'
    }
    return null
  }
  if (Math.abs(closing) < 0.01) {
    return '期末余额为 0 但仍填有未实现损益变动'
  }
  if (Math.abs(uh) > Math.abs(gainPl) + 0.01) {
    return '仍持有未实现绝对值大于本期 FV 损益'
  }
  return null
}

const ITEM_ID_ROWS = 'G9-l3-rows'
const ITEM_ID_CONCLUSION = 'G9-l3-conclusion'
const DETAIL_ROWS_KEY = 'G9-detail-rows'
const FV_TEST_ROWS_KEY = 'G9-fv-test-rows'

export const G9_L3_FORMULA_HINT =
  '期末 = 期初 + 购入 − 处置 + 转入 − 转出 + FV(损益) + FV(OCI) + 利息 − 减值 + 其他'

function genId(): string {
  return `g9l3-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

function emptyRow(assetName: string, seq: number, rowId?: string): G9L3Row {
  return {
    rowId: rowId ?? genId(),
    seq,
    assetName,
    openingFairValue: 0,
    purchaseAmount: 0,
    disposalAmount: 0,
    transferIn: 0,
    transferOut: 0,
    fvChangePL: 0,
    fvChangeOCI: 0,
    interestIncome: 0,
    impairmentLoss: 0,
    otherChanges: 0,
    unrealizedHeld: 0,
    reportedClosing: 0,
    remark: '',
  }
}

function enrichRow(raw: G9L3Row): G9L3EnrichedRow {
  const closingFairValue = calcL3Reconciliation(
    raw.openingFairValue,
    raw.purchaseAmount,
    raw.disposalAmount,
    raw.transferIn,
    raw.transferOut,
    raw.fvChangePL,
    raw.fvChangeOCI,
    raw.interestIncome,
    raw.impairmentLoss,
    raw.otherChanges,
  )
  const variance = calcL3Variance(closingFairValue, raw.reportedClosing)
  return {
    ...raw,
    closingFairValue,
    variance,
    varianceHighlight: Math.abs(variance) > 0.01,
  }
}

function toPersistable(list: G9L3EnrichedRow[] | G9L3Row[]): G9L3Row[] {
  return list.map((r, i) => ({
    rowId: r.rowId,
    seq: i + 1,
    assetName: r.assetName,
    openingFairValue: parseNum(r.openingFairValue),
    purchaseAmount: parseNum(r.purchaseAmount),
    disposalAmount: parseNum(r.disposalAmount),
    transferIn: parseNum(r.transferIn),
    transferOut: parseNum(r.transferOut),
    fvChangePL: parseNum(r.fvChangePL),
    fvChangeOCI: parseNum(r.fvChangeOCI),
    interestIncome: parseNum(r.interestIncome),
    impairmentLoss: parseNum(r.impairmentLoss),
    otherChanges: parseNum(r.otherChanges),
    unrealizedHeld: parseNum(r.unrealizedHeld),
    reportedClosing: parseNum(r.reportedClosing),
    remark: r.remark ?? '',
  }))
}

function parseRows(json: string | null | undefined): G9L3EnrichedRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichRow({
      rowId: r.rowId || genId(),
      seq: i + 1,
      assetName: r.assetName ?? '',
      openingFairValue: parseNum(r.openingFairValue),
      purchaseAmount: parseNum(r.purchaseAmount),
      disposalAmount: parseNum(r.disposalAmount),
      transferIn: parseNum(r.transferIn),
      transferOut: parseNum(r.transferOut),
      fvChangePL: parseNum(r.fvChangePL),
      fvChangeOCI: parseNum(r.fvChangeOCI),
      interestIncome: parseNum(r.interestIncome),
      impairmentLoss: parseNum(r.impairmentLoss),
      otherChanges: parseNum(r.otherChanges),
      unrealizedHeld: parseNum(r.unrealizedHeld),
      reportedClosing: parseNum(r.reportedClosing),
      remark: r.remark ?? '',
    }))
  } catch {
    return []
  }
}

function isLevel3(level: unknown): boolean {
  const s = String(level ?? '').trim().toLowerCase()
  return s === 'level3' || s === 'l3' || s === '3' || s === '第三层次'
}

function parseJsonRows(raw: string | null | undefined): Array<Record<string, unknown>> {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function useG9L3Reconciliation(opts: {
  wpId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const conclusion = ref('')

  watch(() => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion, (v) => {
    conclusion.value = v ?? ''
  }, { immediate: true })

  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  const varianceRows = computed(() => rows.value.filter((r) => r.varianceHighlight))

  const unrealizedWarnings = computed<G9UnrealizedHeldWarning[]>(() =>
    rows.value
      .map((r) => {
        const reason = checkG9UnrealizedHeld(r)
        return reason
          ? { rowId: r.rowId, assetName: r.assetName || `第${r.seq}行`, reason }
          : null
      })
      .filter((x): x is G9UnrealizedHeldWarning => x != null),
  )

  const totals = computed(() => ({
    openingFairValue: calcSubtotal(rows.value.map((r) => r.openingFairValue)),
    purchaseAmount: calcSubtotal(rows.value.map((r) => r.purchaseAmount)),
    disposalAmount: calcSubtotal(rows.value.map((r) => r.disposalAmount)),
    transferIn: calcSubtotal(rows.value.map((r) => r.transferIn)),
    transferOut: calcSubtotal(rows.value.map((r) => r.transferOut)),
    fvChangePL: calcSubtotal(rows.value.map((r) => r.fvChangePL)),
    fvChangeOCI: calcSubtotal(rows.value.map((r) => r.fvChangeOCI)),
    interestIncome: calcSubtotal(rows.value.map((r) => r.interestIncome)),
    impairmentLoss: calcSubtotal(rows.value.map((r) => r.impairmentLoss)),
    otherChanges: calcSubtotal(rows.value.map((r) => r.otherChanges)),
    closingFairValue: calcSubtotal(rows.value.map((r) => r.closingFairValue)),
    unrealizedHeld: calcSubtotal(rows.value.map((r) => r.unrealizedHeld)),
    reportedClosing: calcSubtotal(rows.value.map((r) => r.reportedClosing)),
    variance: calcSubtotal(rows.value.map((r) => r.variance)),
  }))

  function persistRaw(list: G9L3Row[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(toPersistable(list)) })
  }

  function updateRow(rowId: string, field: keyof G9L3Row, value: unknown): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const patch: Partial<G9L3Row> = {}
      if (field === 'assetName' || field === 'remark') patch[field] = String(value ?? '')
      else patch[field] = parseNum(value) as never
      return { ...r, ...patch }
    })
    persistRaw(list)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入资产名称', '新增 L3 调节行')
      const name = (value ?? '').trim()
      if (!name) return
      persistRaw([...rows.value, emptyRow(name, rows.value.length + 1)])
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    persistRaw(rows.value.filter((r) => r.rowId !== rowId))
  }

  /** 按资产名称合并：已有行补空字段；新行追加 */
  function mergeByAssetName(incoming: G9L3Row[], sourceLabel: string): void {
    const byName = new Map(rows.value.map((r) => [r.assetName.trim(), r]))
    let added = 0
    let filled = 0
    const next: G9L3Row[] = toPersistable(rows.value)

    for (const src of incoming) {
      const name = src.assetName.trim()
      if (!name) continue
      const existing = byName.get(name)
      if (!existing) {
        next.push({ ...src, seq: next.length + 1, remark: src.remark || `自 ${sourceLabel} 带入` })
        byName.set(name, src)
        added += 1
        continue
      }
      const idx = next.findIndex((r) => r.assetName.trim() === name)
      if (idx < 0) continue
      const cur = next[idx]
      const merged: G9L3Row = { ...cur }
      let changed = false
      const numericKeys: (keyof G9L3Row)[] = [
        'openingFairValue', 'purchaseAmount', 'disposalAmount', 'transferIn', 'transferOut',
        'fvChangePL', 'fvChangeOCI', 'interestIncome', 'impairmentLoss', 'otherChanges',
        'unrealizedHeld', 'reportedClosing',
      ]
      for (const k of numericKeys) {
        if (parseNum(cur[k]) === 0 && parseNum(src[k] as number) !== 0) {
          ;(merged as any)[k] = src[k]
          changed = true
        }
      }
      if (!merged.remark && src.remark) {
        merged.remark = src.remark
        changed = true
      }
      if (changed) {
        next[idx] = merged
        filled += 1
      }
    }

    persistRaw(next)
    if (added === 0 && filled === 0) {
      ElMessage.info(`${sourceLabel} 无可带入的 Level3 项目，或已全部存在`)
    } else {
      ElMessage.success(`自 ${sourceLabel}：新增 ${added} 行，补填 ${filled} 行`)
    }
  }

  /**
   * 从 G9-2 明细带入 fairValueLevel=Level3 行。
   * 映射：期初审定→期初FV；增加/减少→购入/处置；FV变动按分类拆 PL/OCI；利息/减值；期末审定→企业报告。
   */
  function pullFromDetail(): void {
    if (opts.isReadonly.value) return
    const list = parseJsonRows(opts.allResponses.value.get(DETAIL_ROWS_KEY)?.remark)
    const l3 = list.filter((r) => isLevel3(r.fairValueLevel))
    if (!l3.length) {
      ElMessage.info('G9-2 中暂无公允价值层次为 Level3 的项目')
      return
    }
    const mapped: G9L3Row[] = []
    for (const src of l3) {
      const name = String(src.assetName ?? '').trim()
      if (!name) continue
      const classification = String(src.classification ?? src.measurementAttribute ?? '')
      const fv = parseNum(src.fvChangeAmount)
      const oci = parseNum(src.ociChange)
      const isFvtpl = /fvtpl|损益|交易/i.test(classification)
      const isFvoci = /fvoci|oci|综合收益/i.test(classification)
      const fvPl = isFvoci && !isFvtpl ? 0 : fv
      const closing = parseNum(src.closingAdjusted) || parseNum(src.closingBalance)
      const stillHeld = Math.abs(closing) > 0.01
      mapped.push({
        ...emptyRow(name, mapped.length + 1, src.rowId ? `d2-${src.rowId}` : undefined),
        openingFairValue: parseNum(src.openingAdjusted) || parseNum(src.openingBalance),
        purchaseAmount: parseNum(src.increaseAmount),
        disposalAmount: parseNum(src.decreaseAmount),
        fvChangePL: fvPl,
        fvChangeOCI: isFvoci ? (oci || fv) : oci,
        interestIncome: parseNum(src.interestIncome),
        impairmentLoss: parseNum(src.impairmentLoss),
        unrealizedHeld: stillHeld ? fvPl : 0,
        reportedClosing: closing,
        remark: '自 G9-2 Level3 带入',
      })
    }
    mergeByAssetName(mapped, 'G9-2')
  }

  /** 从 G9-4 公允价值测试带入 Level3 审定期末，用于勾稽「企业报告」 */
  function pullFromFairValueTest(): void {
    if (opts.isReadonly.value) return
    const list = parseJsonRows(opts.allResponses.value.get(FV_TEST_ROWS_KEY)?.remark)
    const l3 = list.filter((r) => isLevel3(r.fairValueLevel))
    if (!l3.length) {
      ElMessage.info('G9-4 中暂无 Level3 项目')
      return
    }
    const mapped: G9L3Row[] = []
    for (const src of l3) {
      const name = String(src.assetName ?? '').trim()
      if (!name) continue
      mapped.push({
        ...emptyRow(name, mapped.length + 1, src.rowId ? `fv-${src.rowId}` : undefined),
        reportedClosing: parseNum(src.closingAuditedFV),
        remark: '自 G9-4 Level3 带入',
      })
    }
    mergeByAssetName(mapped, 'G9-4')
  }

  function updateConclusion(v: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = v
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: v })
  }

  return {
    rows,
    totals,
    varianceRows,
    unrealizedWarnings,
    conclusion,
    updateRow,
    addRow,
    removeRow,
    pullFromDetail,
    pullFromFairValueTest,
    updateConclusion,
  }
}
